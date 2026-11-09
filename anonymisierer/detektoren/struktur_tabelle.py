"""Strukturregel »struktur.tabelle« (Vertrag Abschnitt 3): Spaltenkopf mit Etikett -> Werte der Spalte.

Ablauf je Seite (nur Lage, keine Zeichenspalten – Tabellenzellen sind im Seitenmodell oft eigene Zeilen,
OCR-Zeilen haben keine Tabulatoren, schräge Scans verschieben die Zeilen):

1. Reihen: Zeilen mit gleicher (geradegerückter) Höhe bilden eine Tabellenreihe.
2. Kopfreihe: mindestens zwei Kopfteile aus Etiketten der Wissensbasis bzw. neutralen Spaltenköpfen
   ("Sparte", "Beitrag"), mindestens ein Personen-, Kennungs-, Geburts-, Anschrift- oder Kontakt-Etikett,
   kein Wert in der Reihe. Zellen werden an Etiketten in Spalten geteilt ("Nr. Kunde (Name, Vorname)" ->
   "Nr." | "Kunde (Name, Vorname)", "Beitrag p.a. Ablauf" -> "Beitrag p.a." | "Ablauf").
3. Datenreihen darunter bis zum Tabellenende (große Lücke, Fließtext, neue Kopfreihe); Wörter werden der
   Spalte mit der größten x-Überlappung zugeordnet, Wörter ohne Überlappung erben die Spalte ihrer Zelle.
   Mehrzeilige Zellen und Seitenumbrüche (mit oder ohne wiederholten Kopf) werden fortgesetzt.
4. Werte je Spaltenart: Person -> Namen, Kennung -> vertrag (bzw. iban, kfz …), Geburt -> geburt (das
   Spaltenetikett entscheidet: Vertragsdaten wie "Beginn"/"Ablauf" bleiben stehen), Anschrift -> plzort /
   strasse, Kontakt -> telefon / email. Spalten OHNE Etikett: zeigen mindestens drei Werte dieselbe
   Kennungsform (Ziffern mit Buchstaben/Trennern, keine Beträge, Prozente, Daten, Postleitzahlen) und hat
   die Tabelle eine Personenspalte, sind es Kennungen (vertrag).
"""

from __future__ import annotations

import re
from bisect import bisect_left
from typing import NamedTuple

from . import Treffer, detektor
from .struktur import (_ORG_ROLLEN_RE, ALLE_KATEGORIEN, PARTIKEL, PII_ARTEN, SICHERHEIT_SPALTE, Lage, _wissen,
                       NR_VORSATZ_RE, datums_spannen, etikett_fuer_text, etiketten,
                       geburtsdatum_plausibel, ist_kennungsform, kennung_spanne, lage, muster_spannen,
                       namen_spanne, ort_spanne, plz_ort_spannen, strasse_spanne, ueberlappung, _muster,
                       _vergleichsform)

QUELLE = "struktur.tabelle"
_EINHEITEN = frozenset({"eur", "euro", "€", "%", "p.a.", "chf", "usd", "gbp", "mtl.", "monatlich", "jährlich",
                        "jährl.", "in", "(eur)", "(€)", "[eur]", "brutto", "netto", "ca."})


class Reihe(NamedTuple):
    y0: float
    y1: float
    zellen: tuple          # Zellen (struktur.Zelle) nach x
    zeilen: tuple          # Zeilen-IDs


class Spalte(NamedTuple):
    x0: float
    x1: float
    arten: frozenset       # Etikett-Arten des Kopfteils (leer = unbekannter Kopf)
    kategorie: str | None  # Kennungs-/Kontakt-Kategorie
    eintrag: str           # Etikett (Listeneintrag) bzw. Kopftext


def _reihen(lg: Lage, ocr: bool | None = None) -> list:
    """Zeilen gleicher Höhe (Mitte innerhalb einer halben Zeichenhöhe) zu Reihen zusammenfassen – getrennt
    nach Textebene und OCR (eine Seite mit unsichtbarer Textebene UND OCR des Bildes enthält jede Reihe
    doppelt; gemischt würden die OCR-Bruchstücke die Kopfreihe zerstören)."""
    eintraege = []
    for zid, (x0, y0, x1, y1) in lg.zeilen_box.items():
        if ocr is not None and lg.zeilen_ocr.get(zid, False) != ocr:
            continue
        eintraege.append(((y0 + y1) / 2, y0, y1, zid))
    eintraege.sort()
    reihen = []
    aktuell = []
    for m, y0, y1, zid in eintraege:
        if aktuell:
            mitte = sum(e[0] for e in aktuell) / len(aktuell)
            hoehe = min(min(e[2] - e[1] for e in aktuell), y1 - y0)
            if abs(m - mitte) > max(0.45 * hoehe, 1.0):
                reihen.append(aktuell)
                aktuell = []
        aktuell.append((m, y0, y1, zid))
    if aktuell:
        reihen.append(aktuell)
    aus = []
    for r in reihen:
        zellen = sorted((c for _, _, _, zid in r for c in lg.zellen_je_zeile.get(zid, ())), key=lambda c: c.x0)
        aus.append(Reihe(min(e[1] for e in r), max(e[2] for e in r), tuple(zellen), tuple(e[3] for e in r)))
    return aus


def _etiketten_in(ets: list, starts: list, s: int, e: int) -> list:
    i = bisect_left(starts, s)
    aus = []
    while i < len(ets) and ets[i].start < e:
        aus.append(ets[i])
        i += 1
    return aus


_WERTARTIG_RE = re.compile(r"\d(?![\d ]*%)|@")          # Ziffern (außer "19 %") oder E-Mail: ein Wert


def _kopfteile(text: str, reihe: Reihe, ets: list, starts: list) -> list | None:
    """Kopfteile einer Reihe: [(x0, x1, Etikett|None, text)]; None, wenn die Reihe Werte enthält."""
    teile = []
    for zelle in reihe.zellen:
        inhalt = text[zelle.start:zelle.ende]
        if _WERTARTIG_RE.search(inhalt):
            return None
        labels = [et for et in _etiketten_in(ets, starts, zelle.start, zelle.ende)]
        # Etiketten in Klammern teilen nicht ("Kunde (Name, Vorname)"), Einheiten auch nicht
        teiler = []
        for et in labels:
            vorn = text[zelle.start:et.start]
            if vorn.count("(") > vorn.count(")"):
                continue
            if text[et.start:et.ende].casefold() in _EINHEITEN:
                continue
            teiler.append(et)
        woerter = zelle.woerter
        if not teiler:
            if len(woerter) > 4:
                return None                          # langer Text ohne Etikett: kein Kopf
            teile.append((zelle.x0, zelle.x1, None, inhalt))
            continue
        grenzen = [t.start for t in teiler]
        gruppen: list = []
        for w in woerter:
            neu = any(w.start == g for g in grenzen)
            if neu or not gruppen:
                gruppen.append([w])
            else:
                gruppen[-1].append(w)
        for g in gruppen:
            et = next((t for t in teiler if t.start == g[0].start), None)
            teile.append((min(w.x0 for w in g), max(w.x1 for w in g), et, text[g[0].start:g[-1].ende]))
    return teile


def _kopf_spalten(text: str, reihe: Reihe, ets: list, starts: list, breite: float = 600.0) -> list | None:
    teile = _kopfteile(text, reihe, ets, starts)
    if not teile or len(teile) < 2:
        return None
    teile.sort(key=lambda t: t[0])
    # Spalten einer Tabelle liegen beieinander; weit auseinander liegende Teile gehören zu verschiedenen
    # Spalten des Seitenlayouts (Anschriftfeld links, Informationsblock rechts)
    if any(b[0] - a[1] > 0.33 * breite for a, b in zip(teile, teile[1:])):
        return None
    mit_etikett = [t for t in teile if t[2] is not None]
    pii = [t for t in mit_etikett if t[2].arten & PII_ARTEN]
    if len(mit_etikett) < 2 or not pii:
        return None
    unbekannt = [t for t in teile if t[2] is None]
    for _, _, _, inhalt in unbekannt:
        # unbekannte Kopfteile: kurz, ohne Namen ("Györi, Réka" ist ein Wert, kein Kopf)
        if "," in inhalt or len(inhalt.split()) > 3:
            return None
        sp = namen_spanne(inhalt, 0, len(inhalt))
        if sp is not None and (sp.bekannt or sp.komma) and sp.ende - sp.start >= 0.7 * len(inhalt.strip()):
            return None
    spalten = []
    for x0, x1, et, inhalt in sorted(teile, key=lambda t: t[0]):
        if et is None:
            spalten.append(Spalte(x0, x1, frozenset(), None, inhalt))
        else:
            spalten.append(Spalte(x0, x1, et.arten, et.kategorie, et.eintrag))
    return spalten


def _kopf_zweizeilig(text: str, r1: Reihe, r2: Reihe, h: float, breite: float) -> list | None:
    """Kopf über zwei Zeilen ("Versicherungs-" / "nummer", "Geburts-" / "datum", "Kunden-" / "Nr."):
    Zellen beider Reihen werden je Spalte verbunden und als Ganzes in den Etiketten nachgeschlagen."""
    if r2.y0 - r1.y1 > 0.9 * h:
        return None
    spalten_roh: list = []                           # [x0, x1, [Texte]]
    for zelle in sorted(list(r1.zellen) + list(r2.zellen), key=lambda z: (z.y0, z.x0)):
        inhalt = text[zelle.start:zelle.ende]
        if _WERTARTIG_RE.search(inhalt) or len(inhalt.split()) > 4:
            return None
        for s in spalten_roh:
            if ueberlappung(zelle.x0, zelle.x1, s[0], s[1]) > 0:
                s[0], s[1] = min(s[0], zelle.x0), max(s[1], zelle.x1)
                s[2].append(inhalt)
                break
        else:
            spalten_roh.append([zelle.x0, zelle.x1, [inhalt]])
    if len(spalten_roh) < 2 or not any(len(s[2]) > 1 for s in spalten_roh):
        return None
    spalten = []
    for x0, x1, texte in sorted(spalten_roh):
        # Lesarten: Trennstrich entfällt ("Geburts-" + "datum") oder bleibt ("Kunden-" + "Nr.")
        lesarten = [texte[0]]
        for t in texte[1:]:
            neu = []
            for v in lesarten:
                if v.endswith("-"):
                    neu += [v[:-1] + t, v + t]
                else:
                    neu.append(v + " " + t)
            lesarten = neu
        et, verbunden = None, lesarten[0]
        for v in lesarten:
            et = etikett_fuer_text(v, mit_vertragsdaten=True)
            if et is not None:
                verbunden = v
                break
        if et is None:
            spalten.append(Spalte(x0, x1, frozenset(), None, verbunden))
        else:
            spalten.append(Spalte(x0, x1, et.arten, et.kategorie, et.eintrag))
    mit_etikett = [sp for sp in spalten if sp.arten]
    if len(mit_etikett) < 2 or not any(sp.arten & PII_ARTEN for sp in spalten):
        return None
    if any(b.x0 - a.x1 > 0.33 * breite for a, b in zip(spalten, spalten[1:])):
        return None
    return spalten


def _zuordnen(spalten: list, zelle, h: float) -> list:
    """Wörter einer Zelle den Spalten zuordnen -> [(spalten_index, start, ende)] zusammenhängender Teile."""
    zuordnung = []
    for w in zelle.woerter:
        beste, ueber = None, 0.0
        for i, sp in enumerate(spalten):
            u = ueberlappung(w.x0, w.x1, sp.x0 - 0.4 * h, sp.x1 + 0.4 * h)
            if u > ueber:
                beste, ueber = i, u
        zuordnung.append(beste)
    if all(z is None for z in zuordnung):
        # keine Überlappung: Spalte, in deren Bereich die Zelle beginnt (linksbündige Spalten)
        beste = None
        for i, sp in enumerate(spalten):
            if sp.x0 - 0.6 * h <= zelle.x0:
                beste = i
        if beste is None:
            return []
        naechste = spalten[beste + 1].x0 if beste + 1 < len(spalten) else float("inf")
        if zelle.x0 >= naechste - 0.6 * h:
            return []
        zuordnung = [beste] * len(zelle.woerter)
    else:
        # Wörter ohne Überlappung erben die Spalte des nächsten zugeordneten Worts der Zelle
        for k, z in enumerate(zuordnung):
            if z is None:
                links = next((zuordnung[j] for j in range(k - 1, -1, -1) if zuordnung[j] is not None), None)
                rechts = next((zuordnung[j] for j in range(k + 1, len(zuordnung)) if zuordnung[j] is not None), None)
                zuordnung[k] = links if links is not None else rechts
    teile = []
    for w, z in zip(zelle.woerter, zuordnung):
        if teile and teile[-1][0] == z:
            teile[-1] = (z, teile[-1][1], w.ende)
        else:
            teile.append((z, w.start, w.ende))
    return teile


def _ist_fliesstext(text: str, zelle, spalten: list) -> bool:
    """Eine Zelle mit Satzbau über mehrere Spalten (Absatz nach der Tabelle)."""
    inhalt = text[zelle.start:zelle.ende]
    woerter = inhalt.split()
    if len(woerter) < 6:
        return False
    klein = sum(1 for w in woerter if w[:1].islower())
    spannweite = sum(1 for sp in spalten if ueberlappung(zelle.x0, zelle.x1, sp.x0, sp.x1) > 0)
    return klein >= 3 and spannweite >= 2


class _Tabelle:
    def __init__(self, spalten: list, kopf: Reihe):
        self.spalten = spalten
        self.kopf = kopf
        self.werte: list = [[] for _ in spalten]      # je Spalte: [(seite_nr, start, ende, reihe_nr)]
        self.reihen = 0
        self.letzte_y1 = kopf.y1


def _datenreihen(text: str, reihen: list, i_kopf: int, tab: _Tabelle, h: float, nr: int, ist_kopf) -> int:
    """Liest Datenreihen ab reihen[i_kopf + 1]; liefert den Index der ersten Reihe nach der Tabelle."""
    spalten = tab.spalten
    links = min(sp.x0 for sp in spalten) - 2.5 * h
    rechts = max(sp.x1 for sp in spalten) + 6 * h
    abstand = None
    einzeln = 0
    vorige_y1 = reihen[i_kopf].y1 if i_kopf >= 0 else None
    i = i_kopf + 1
    while i < len(reihen):
        r = reihen[i]
        if vorige_y1 is not None:
            luecke = r.y0 - vorige_y1
            grenze = max(2.6 * h, 2.2 * abstand) if abstand else 3.2 * h
            if luecke > grenze:
                break
        if ist_kopf(r):
            break
        zellen = [z for z in r.zellen if z.x1 > links and z.x0 < rechts]
        if not zellen:
            break
        if any(_ist_fliesstext(text, z, spalten) for z in zellen):
            break
        if zellen[0].x0 < links + 1.0 and len(zellen) == 1 and len(text[zellen[0].start:zellen[0].ende].split()) > 4:
            break
        if any(_ETIKETT_DOPPELPUNKT_RE.search(text, z.start, z.ende) for z in zellen):
            break                                    # "Tarif: …": ein Formularblock nach der Tabelle
        teile = []
        for z in zellen:
            teile += [(idx, s, e) for idx, s, e in _zuordnen(spalten, z, h) if idx is not None]
        if not teile:
            break
        belegte = {idx for idx, _, _ in teile}
        if len(belegte) == 1:
            idx = next(iter(belegte))
            sp = spalten[idx]
            if sp.arten & PII_ARTEN:
                if not any(_wert_fuer_spalte(text, s, e, sp) for _, s, e in teile):
                    break                            # Zwischenüberschrift o. ä. in einer Personenspalte
            else:
                einzeln += 1
                if einzeln >= 2:
                    break
        else:
            einzeln = 0
        for idx, s, e in teile:
            tab.werte[idx].append((nr, s, e, tab.reihen))
        if vorige_y1 is not None:
            d = r.y0 - vorige_y1
            if d > 0:
                abstand = d if abstand is None else min(max(abstand, d), 2.0 * abstand)
        vorige_y1 = r.y1
        tab.reihen += 1
        i += 1
    tab.letzte_y1 = vorige_y1 or tab.letzte_y1
    return i


_ETIKETT_DOPPELPUNKT_RE = re.compile(r"[A-Za-zÄÖÜäöüß)][ ]?:(?:[ \t]|$)")


def _wert_fuer_spalte(text: str, s: int, e: int, sp: Spalte) -> list:
    """Werte eines Zellteils nach der Art der Spalte (leer, wenn nichts Passendes darin steht)."""
    arten = sp.arten
    if "kennung" in arten:
        return _kennung(text, s, e, sp.kategorie)
    if "datum_geburt" in arten:
        v = _vergleichsform(sp.eintrag)
        if re.search(r"(?:ort|\bin)$", v) and not re.search(r"dat|tag", v):
            o = ort_spanne(text, s, e)
            return [(o[0], o[1], "plzort", None)] if o else []
        return _geburt(text, s, e)
    if "adresse" in arten:
        return _adresse(text, s, e, sp.eintrag)
    if "kontakt" in arten:
        return _kontakt(text, s, e, sp.kategorie)
    if "person" in arten:
        return _namen(text, s, e, nur_bekannt=bool(_ORG_ROLLEN_RE.match(sp.eintrag)))
    return []


# ----------------------------------------------------------------------
# Werte je Spaltenart
# ----------------------------------------------------------------------
_EINRICHTUNG_RE = re.compile(r"(?i)(?:krankenhaus|klinik|klinikum|kliniken|hospital|spital|stift|kirche|schule|"
                             r"apotheke|"
                             r"heim|zentrum|institut|universität|hochschule|kita|kindergarten|sanatorium|reha|"
                             r"(?<![\w])st\.|(?<![\w])sankt(?![\w]))")
_LAUFNUMMER_RE = re.compile(r"[ \t]*(?:\d{1,4}[.)]?|[-–•*])[ \t]+")


def _namen(text: str, s: int, e: int, nur_bekannt: bool = False) -> list:
    m = _LAUFNUMMER_RE.match(text, s, e)
    if m:
        s = m.end()
    aus = []
    pos = s
    sp = namen_spanne(text, pos, e)
    if sp is None and not _EINRICHTUNG_RE.search(text[s:e]):
        # Betriebswort vor dem Namen ("Physiotherapie Tran", "Praxis Dr. Haidari"): ein bis zwei Wörter überspringen;
        # Einrichtungen ("Krankenhaus St. Ansgar", "Apotheke am Markt") sind keine Personen
        for m in list(re.finditer(r"[ \t]+", text[s:e]))[:2]:
            kandidat = namen_spanne(text, s + m.end(), e)
            if kandidat is not None and kandidat.bekannt:
                sp, pos = kandidat, kandidat.start
                break
    while pos < e:
        if sp is None:
            sp = namen_spanne(text, pos, e)
        if sp is None or (nur_bekannt and not sp.bekannt and not sp.komma):
            break
        aus.append((sp.start, sp.ende, "namen", text[sp.start:sp.ende] if sp.woerter >= 2 else None))
        # weitere Namen in derselben Zelle ("Max Muster / Erika Muster")
        m = re.match(r"[ \t]*(?:/|;|&|und|,)[ \t]*", text[sp.ende:e])
        if not m or m.end() == 0:
            break
        pos = sp.ende + m.end()
        sp = None
    return aus


def _namensbeleg(name: str) -> bool:
    """Enthält der Zellwert einen bekannten Vor- oder Nachnamen der Wissensbasis?"""
    if _wissen is None:
        return True
    for wort in re.findall(r"[^\W\d_][\w'’]*(?:-[^\W\d_][\w'’]*)*", name):
        if len(wort) < 2 or wort.casefold() in PARTIKEL:
            continue
        titel = wort.title() if wort.isupper() else wort
        try:
            if _wissen.ist_vorname(titel) or _wissen.ist_nachname(titel):
                return True
        except Exception:
            return True
    return False


def _kennung(text: str, s: int, e: int, kategorie: str | None) -> list:
    i = s
    while i < e and text[i] in " \t":
        i += 1
    m = NR_VORSATZ_RE.match(text, i, e)
    if m and m.end() < e:
        i = m.end()                                   # "Nr. KH 0815 4471 2" unter "Versicherungsschein-"
    sp = kennung_spanne(text, i, e, 3)
    if sp is None:
        return []
    kat = kategorie or "vertrag"
    if kat == "iban" and _muster is not None and not _muster.finde_iban(text[sp[0]:sp[1]]):
        kat = "vertrag"
    return [(sp[0], sp[1], kat, None)]


def _geburt(text: str, s: int, e: int) -> list:
    aus = []
    for a, b, d in datums_spannen(text, s, e):
        if geburtsdatum_plausibel(d):
            aus.append((a, b, "geburt", None))
    return aus


_ORT_KOPF_RE = re.compile(r"(?:^|\b)(?:ort|wohnort|stadt|city|geburtsort|gemeinde)$")
_PLZ_KOPF_RE = re.compile(r"^(?:plz|postleitzahl)$")
_STRASSE_KOPF_RE = re.compile(r"str|stra|hausn|street|anschrift|adresse")


def _adresse(text: str, s: int, e: int, eintrag: str) -> list:
    v = _vergleichsform(eintrag)
    aus = [(a, b, "plzort", None) for a, b in plz_ort_spannen(text, s, e)]
    sp = strasse_spanne(text, s, e)
    if sp and not any(a <= sp[0] < b for a, b, _, _ in aus):
        aus.append((sp[0], sp[1], "strasse", None))
    if aus:
        return aus
    if _PLZ_KOPF_RE.search(v):
        m = re.match(r"[ \t]*((?:(?:D|DE|A|CH)[-\s])?\d{4,5})(?![\w])", text[s:e])
        if m:
            return [(s + m.start(1), s + m.end(1), "plzort", None)]
    if _ORT_KOPF_RE.search(v) or "/" in eintrag or "plz" in v:
        sp = ort_spanne(text, s, e)
        if sp:
            return [(sp[0], sp[1], "plzort", None)]
    return []


def _kontakt(text: str, s: int, e: int, kategorie: str | None) -> list:
    aus = []
    if _muster is None:
        return aus
    if kategorie in (None, "email"):
        aus += [(a, b, "email", None) for a, b in muster_spannen(_muster.finde_email, text, s, e)]
    if kategorie in (None, "telefon"):
        aus += [(a, b, "telefon", None) for a, b in muster_spannen(_muster.finde_telefon, text, s, e)]
    return aus


def _werte_der_tabelle(dok, tab: _Tabelle) -> list:
    """Treffer aller Spalten einer Tabelle."""
    treffer = []
    hat_person = any("person" in sp.arten for sp in tab.spalten)
    vorname_idx = [i for i, sp in enumerate(tab.spalten) if "person" in sp.arten
                   and _vergleichsform(sp.eintrag) in ("vorname", "vornamen", "rufname", "first name", "given name")]
    for idx, sp in enumerate(tab.spalten):
        werte = tab.werte[idx]
        if not werte:
            continue
        arten = sp.arten
        roh = []          # (seite, start, ende, kategorie, gruppe, reihe)
        for nr, s, e, reihe in werte:
            text = dok.seiten[nr].text
            for a, b, kat, gruppe in _wert_fuer_spalte(text, s, e, sp):
                roh.append((nr, a, b, kat, gruppe, reihe))
        if not arten & PII_ARTEN and "vertragsdaten" not in arten:
            # Spalte ohne Personen-Etikett ("Nr.", unbekannter Kopf): Kennungsform in >= 3 Werten
            if hat_person:
                kandidaten = []
                nicht_leer = 0
                for nr, s, e, reihe in werte:
                    inhalt = dok.seiten[nr].text[s:e].strip()
                    if not inhalt:
                        continue
                    nicht_leer += 1
                    if ist_kennungsform(inhalt):
                        a = s + dok.seiten[nr].text[s:e].index(inhalt)
                        kandidaten.append((nr, a, a + len(inhalt), "vertrag", None, reihe))
                if len(kandidaten) >= 3 and len(kandidaten) >= 0.6 * nicht_leer:
                    roh.extend(kandidaten)
        for nr, a, b, kat, gruppe, reihe in roh:
            treffer.append((nr, a, b, kat, gruppe, reihe, idx))
    # Namen brauchen einen Beleg: ein bekannter Vor- oder Nachname in der Zelle – oder, bei getrennten Spalten
    # "Name" und "Vorname", in der Partnerzelle derselben Reihe ("von Schönau" neben "Silke").
    # "Berlin, Hamburg" in der Kundenspalte ist kein Name.
    paar_idx = {i for i, sp in enumerate(tab.spalten) if "person" in sp.arten
                and _vergleichsform(sp.eintrag) in ("name", "nachname", "familienname", "vorname", "vornamen",
                                                    "rufname", "first name", "given name", "last name", "surname")}
    belegt = set()
    belegt_paar = set()
    for k, t in enumerate(treffer):
        if t[3] == "namen" and _namensbeleg(dok.seiten[t[0]].text[t[1]:t[2]]):
            belegt.add(k)
            if t[6] in paar_idx:
                belegt_paar.add(t[5])
    treffer = [t for k, t in enumerate(treffer)
               if t[3] != "namen" or k in belegt or (t[6] in paar_idx and t[5] in belegt_paar)]
    # Personen über Spalten "Name" + "Vorname" derselben Reihe gruppieren
    if vorname_idx:
        je_reihe: dict = {}
        for t in treffer:
            if t[3] == "namen":
                je_reihe.setdefault(t[5], []).append(t)
        neu = []
        for t in treffer:
            if t[3] == "namen":
                teile = je_reihe.get(t[5], [])
                vor = [x for x in teile if x[6] in vorname_idx]
                nach = [x for x in teile if x[6] not in vorname_idx]
                if vor and nach:
                    v, n = vor[0], nach[0]
                    gruppe = (f"{dok.seiten[v[0]].text[v[1]:v[2]]} {dok.seiten[n[0]].text[n[1]:n[2]]}")
                    t = t[:4] + (gruppe,) + t[5:]
            neu.append(t)
        treffer = neu
    aus = []
    for nr, a, b, kat, gruppe, _, _ in treffer:
        aus.append(Treffer(dok.global_(nr, a), dok.global_(nr, b), kat, QUELLE, SICHERHEIT_SPALTE, gruppe))
    return aus


@detektor(QUELLE, ALLE_KATEGORIEN)
def tabelle(dok, kontext):
    """Tabellen mit Spaltenköpfen: Werte der Personen-, Kennungs-, Geburts-, Anschrift- und Kontaktspalten."""
    treffer = []
    offen: dict = {}          # je Quelle: Tabelle, die bis zum Seitenende reichte (Fortsetzung)
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        if not text.strip():
            offen = {}
            continue
        lg = lage(seite)
        ets = etiketten(seite)
        starts = [et.start for et in ets]
        for ocr in ((False, True) if any(lg.zeilen_ocr.values()) else (None,)):
            reihen = _reihen(lg, ocr)
            neu, offen[ocr] = _seite_lesen(dok, nr, seite, lg, ets, starts, reihen, offen.get(ocr))
            treffer += neu
    return [t for t in treffer if t.kategorie in kontext.aktive or not kontext.aktive]


def _seite_lesen(dok, nr: int, seite, lg: Lage, ets: list, starts: list, reihen: list, offen):
    """Tabellen einer Seite (eine Quelle: Textebene oder OCR). Liefert (Treffer, offene Tabelle)."""
    text = seite.text
    h = lg.hoehe
    breite = lg.breite_seite
    treffer = []

    def ist_kopf(r):
        return _kopf_spalten(text, r, ets, starts, breite) is not None

    i = 0
    if offen is not None:
        # Seitenumbruch: ohne wiederholten Kopf die Reihen am Seitenanfang in den alten Spalten lesen
        vorn = reihen[:6]
        tab = None
        if not any(ist_kopf(r) for r in vorn):
            for i0 in range(len(vorn)):
                kandidat = _Tabelle(offen.spalten, reihen[i0])
                j = _datenreihen(text, reihen, i0 - 1, kandidat, h, nr, ist_kopf)
                if kandidat.reihen >= 2 and _passt_zur_tabelle(dok, kandidat):
                    treffer += _werte_der_tabelle(dok, kandidat)
                    tab, i = kandidat, j
                    break
        offen = tab if tab is not None and _bis_seitenende(lg, tab) else None
    while i < len(reihen):
        spalten = _kopf_spalten(text, reihen[i], ets, starts, breite)
        kopf_ende = i
        if spalten is None and i + 1 < len(reihen):
            spalten = _kopf_zweizeilig(text, reihen[i], reihen[i + 1], h, breite)
            kopf_ende = i + 1
        if spalten is None:
            i += 1
            continue
        tab = _Tabelle(spalten, reihen[kopf_ende])
        j = _datenreihen(text, reihen, kopf_ende, tab, h, nr, ist_kopf)
        if tab.reihen:
            treffer += _werte_der_tabelle(dok, tab)
            offen = tab if _bis_seitenende(lg, tab) else None
        i = max(j, i + 1)
    return treffer, offen


def _bis_seitenende(lg: Lage, tab: _Tabelle) -> bool:
    """Reicht die Tabelle bis an den unteren Seitenrand (nur Fußzeilen danach)?"""
    hoehe = lg.hoehe_seite
    return tab.letzte_y1 is not None and tab.letzte_y1 > hoehe * 0.72


def _passt_zur_tabelle(dok, neu: _Tabelle) -> bool:
    """Fortsetzung ohne Kopf: in mindestens zwei Personen-/Kennungs-/Geburtsspalten stehen Werte der
    passenden Form."""
    passend = 0
    for idx, sp in enumerate(neu.spalten):
        werte = neu.werte[idx]
        if not werte or not sp.arten & PII_ARTEN:
            continue
        nr, s, e, _ = werte[0]
        text = dok.seiten[nr].text
        if "kennung" in sp.arten and _kennung(text, s, e, sp.kategorie):
            passend += 1
        elif "datum_geburt" in sp.arten and _geburt(text, s, e):
            passend += 1
        elif "person" in sp.arten and _namen(text, s, e):
            passend += 1
        elif "adresse" in sp.arten and _adresse(text, s, e, sp.eintrag):
            passend += 1
    return passend >= 2
