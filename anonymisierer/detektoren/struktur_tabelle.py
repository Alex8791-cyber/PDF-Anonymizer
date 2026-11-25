"""Strukturregel »struktur.tabelle« (Vertrag Abschnitt 3): Spaltenkopf mit Etikett -> Werte der Spalte.

Ablauf je Seite (nur Lage, keine Zeichenspalten – Tabellenzellen sind im Seitenmodell oft eigene Zeilen,
OCR-Zeilen haben keine Tabulatoren, schräge Scans verschieben die Zeilen):

1. Reihen: Zeilen mit gleicher (geradegerückter) Höhe bilden eine Tabellenreihe.
2. Kopfreihe: mindestens zwei Kopfteile aus Etiketten der Wissensbasis bzw. neutralen Spaltenköpfen
   ("Sparte", "Beitrag"), mindestens ein Personen-, Kennungs-, Geburts-, Anschrift- oder Kontakt-Etikett,
   kein Wert in der Reihe. Zellen werden an Etiketten in Spalten geteilt ("Nr. Kunde (Name, Vorname)" ->
   "Nr." | "Kunde (Name, Vorname)", "Beitrag p.a. Ablauf" -> "Beitrag p.a." | "Ablauf").
3. Datenreihen darunter bis zum Tabellenende (große Lücke, Fließtext, neue Kopfreihe, kleiner gesetzte Zeile aus
   Etiketten ohne Werte: die nächste Etikettzeile eines Kastenformulars); Wörter werden der Spalte mit der größten
   x-Überlappung zugeordnet, Wörter ohne Überlappung erben die Spalte ihrer Zelle. Seitenumbrüche (mit oder ohne
   wiederholten Kopf) werden fortgesetzt.
   Mehrzeilige Zellen (Zellumbruch in schmalen Spalten: "Eheleute" ⏎ "Gstettner", "Am Gänsbichl" ⏎ "4, 84453
   Mühldorf a. Inn"): eine Folgezeile gehört zur Zelle darüber, wenn sie keine neue Zeile der Tabelle beginnt – nur
   Personen- und Anschriftspalten belegt, jede davon schon in der ersten Zeile des Datensatzes, weniger belegte
   Spalten, keine Kennung, kein Datum, kein Betrag, Namensteile ohne Ziffern, kein größerer Abstand als zwischen
   den Reihen. Der Zellinhalt wird dann zusätzlich als Ganzes gelesen (Zeilen mit Leerzeichen verbunden); ein Wert
   über den Umbruch wird je Zeile eine Stelle (gruppe = der ganze Wert: ein Fund, das Bruchstück selbst wird nicht
   weitergegeben).
4. Werte je Spaltenart: Person -> Namen, Kennung -> vertrag (bzw. iban, kfz …), Geburt -> geburt (das
   Spaltenetikett entscheidet: Vertragsdaten wie "Beginn"/"Ablauf" bleiben stehen), Anschrift -> plzort /
   strasse, Kontakt -> telefon / email. Spalten OHNE Etikett: zeigen mindestens drei Werte dieselbe
   Kennungsform (Ziffern mit Buchstaben/Trennern, keine Beträge, Prozente, Daten, Postleitzahlen) und hat
   die Tabelle eine Personenspalte, sind es Kennungen (vertrag).
   Namen brauchen einen Beleg: einen Vor- oder Nachnamen der Wissensbasis, die Partnerspalte "Vorname", eine belegte
   Namensspalte – oder eine Anrede, einen Titel bzw. eine Personengruppe davor in der Zelle ("Eheleute Gstettner",
   "Erbengemeinschaft Ruhstorfer"); mit "und", "/" oder "&" verbundene Namen derselben Zelle teilen ihn ("Baltasar
   Wiesenhofer und Walburga Oberprieler").
"""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from typing import NamedTuple

from .. import kennungsformen
from .. import personenkontext
from . import Treffer, detektor
from .struktur import (_ANREDEN, _ORG_ROLLEN_RE, _ROH_FUNKTIONSWORT, _ROH_KEIN_WOHNORT, _ROH_ORTSZUSATZ,
                       ABKUERZUNG_RE, ALLE_KATEGORIEN, DATUMSWOERTER, PARTIKEL, PII_ARTEN, SICHERHEIT_SPALTE, Lage,
                       _wissen, NR_VORSATZ_RE, allgemein_hinter, allgemeiner_wert_passt, datums_spannen,
                       eigene_wertform, eigener_wert, etikett_fuer_text, etiketten, geburtsdatum_plausibel,
                       ist_kennungsform, kennung_spanne, lage, muster_spannen, namen_spanne, ort_spanne,
                       plz_ort_spannen, strasse_spanne, ueberlappung, wort_namensartig, _muster, _vergleichsform,
                       _wort_ist_titel, HAUSNUMMER_VOR_PLZ_RE, STRASSENNAME_ALLEIN_RE)

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
_ABKUERZUNG_RE = ABKUERZUNG_RE


def _kopfteile(text: str, reihe: Reihe, ets: list, starts: list) -> list | None:
    """Kopfteile einer Reihe: [(x0, x1, Etikett|None, text)]; None, wenn die Reihe Werte enthält."""
    teile = []
    for zelle in reihe.zellen:
        inhalt = text[zelle.start:zelle.ende]
        if _WERTARTIG_RE.search(inhalt):
            return None
        labels = sorted(_etiketten_in(ets, starts, zelle.start, zelle.ende), key=lambda et: et.start)
        # Etiketten in Klammern teilen nicht ("Kunde (Name, Vorname)"), Einheiten auch nicht – die Klammern bis zum
        # Etikett laufend gezählt statt je Etikett vom Zellenanfang (linear auch bei langen Zellen, Abnahme 2 A2-12)
        teiler = []
        pos, offen = zelle.start, 0
        for et in labels:
            if et.start > pos:
                stueck = text[pos:et.start]
                offen += stueck.count("(") - stueck.count(")")
                pos = et.start
            if offen > 0:
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
        erste_je_start: dict = {}
        for t in teiler:
            erste_je_start.setdefault(t.start, t)
        teiler_starts = [t.start for t in teiler]
        gruppen: list = []
        for w in woerter:
            if w.start in erste_je_start or not gruppen:
                gruppen.append([w])
            else:
                gruppen[-1].append(w)
        for g in gruppen:
            et = erste_je_start.get(g[0].start)
            # Spaltenname aus einer Datenbank ("VN_PLZ", "KD_ORT", "VP_GEBDAT"): vorn die Rolle, hinten das Feld
            hinten = [t for t in teiler[bisect_right(teiler_starts, g[0].start):bisect_left(teiler_starts, g[-1].ende)]
                      if text[t.start - 1] == "_"]
            if et is not None and hinten:
                et = hinten[-1]
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
    unbekannt = [t for t in teile if t[2] is None]
    # ein einziges Etikett im Kopf genügt, wenn es eine Kennung benennt und die Reihe aus mindestens drei kurzen
    # Kopfwörtern besteht ("Gegenstand ⇥⇥ Kaufpreis ⇥⇥ Seriennummer": Stehlgutliste, Domänen-Befund 48) – die
    # Werte darunter prüft die Wertform der Kennung (keine Beträge, Daten, Mengen)
    nur_kennung = (len(mit_etikett) == 1 and len(teile) >= 3 and pii and pii[0][2].arten <= {"kennung"}
                   and all(len(inhalt.split()) <= 2 and inhalt.strip()[:1].isupper() for _, _, _, inhalt in unbekannt))
    if (len(mit_etikett) < 2 and not nur_kennung) or not pii:
        return None
    for _, _, _, inhalt in unbekannt:
        # unbekannte Kopfteile: kurz, ohne Namen ("Györi, Réka" ist ein Wert, kein Kopf)
        if "," in inhalt or len(inhalt.split()) > 3:
            return None
        if _ABKUERZUNG_RE.fullmatch(inhalt.strip()):
            continue                                 # Spaltenkürzel eines Exports ("VU", "ZW.", "BTR_BRUTTO")
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
        self.anker = frozenset()                      # belegte Spalten der ersten Zeile des letzten Datensatzes
        self.umbrochen: set = set()                   # (Spalte, Reihe) mit Folgezeilen (Zellumbruch)
        self.bis_ende = False                         # reicht bis an den unteren Seitenrand (Fortsetzung sicher)
        self.angekuendigt = False                     # eine Fortsetzung ist ausdrücklich angekündigt


# Hinweis auf eine Fortsetzung am Kopf der Folgeseite ("Fortsetzung", "Bestandsliste … – Seite 2", "Blatt 3 von 4",
# "Übertrag"): dann setzt sich eine Tabelle auch fort, die auf der Seite davor nicht bis an den Rand reichte
_FORTSETZUNG_RE = re.compile(r"(?i)(?<![\wäöüß])(?:fortsetzung|forts\.|fortgesetzt|übertrag|continued|"
                             r"(?:seite|blatt|page)[ \t]+\d{1,3}(?:[ \t]*(?:von|/|of)[ \t]*\d{1,3})?)(?![\wäöüß])")


# Ankündigung einer Fortsetzung unter dem Ende einer Tabelle ("Weitere Kinder siehe Folgeseite.", "Fortsetzung auf Seite
# 2", "siehe Rückseite", "Fortsetzung umseitig", "b. w."): die Tabelle setzt sich auf der nächsten Seite ohne Kopf fort
# (Nachprüfung NP-09, Abnahme N8). "umseitig" und "umstehend" nur in einer Fortsetzungsformel ("Fortsetzung umseitig",
# "Weitere Kinder umseitig") – nicht "Es gelten die Bedingungen umstehend." (Abnahme 2 A2-02)
_FORTSETZUNG_FOLGT_RE = re.compile(
    r"(?i)(?<![\wäöüß])(?:folgeseiten?|folgeblatt|nächsten?[ \t]+seite|naechsten?[ \t]+seite|rückseite|rueckseite|"
    r"(?:fortsetzung|forts\.|fortgesetzt|weitere[nrs]?(?:[ \t]+[^\s.;:,]{2,30}){0,3}?)[ \t]+(?:siehe[ \t]+|s\.[ \t]*)?"
    r"(?:umseitig|umstehend)|"
    r"nächste[sn]?[ \t]+blatt|fortsetzung[ \t]+(?:auf|siehe|s\.|folgt)|wird[ \t]+fortgesetzt|"
    r"(?:siehe|s\.|weiter[ \t]+(?:auf|mit))[ \t]+(?:seite|blatt|s\.)[ \t]*\d{1,3}|bitte[ \t]+wenden|b\.[ \t]?w\.)"
    r"(?![\wäöüß])")
# Eine Ankündigung ist eine Fortsetzungsformel ("Fortsetzung …", "Weitere Kinder siehe Folgeseite", "siehe Rückseite",
# "b. w.") oder eine kurze Zeile ("Folgeseite", "→ Rückseite") – nicht ein Satz über etwas anderes ("Die
# Tarifbausteine finden Sie auf der Folgeseite."; Abnahme 2 A2-02)
_FORTSETZUNG_FORMEL_RE = re.compile(r"(?i)(?<![\wäöüß])(?:fortsetzung|forts\.|fortgesetzt|weiter\w{0,3}|siehe|s\.|"
                                    r"bitte[ \t]+wenden|b\.[ \t]?w\.)(?![\wäöüß])")


def _fortsetzung_folgt(text: str, reihen: list, ende: int, erste: int) -> bool:
    """Kündigt eine Reihe am Ende der Tabelle (die letzten zwei Reihen ab erste, die Tabelle endet vor reihen[ende]) oder
    eine der drei Reihen darunter eine Fortsetzung auf der nächsten Seite an? Die Ankündigung kann als letzte Reihe in
    die Tabelle geraten sein ("Weitere Kinder siehe Folgeseite." unter der Spalte "Name")."""
    for r in reihen[max(erste, ende - 2):ende + 3]:
        for z in r.zellen:
            if _FORTSETZUNG_FOLGT_RE.search(text, z.start, z.ende) and (
                    _FORTSETZUNG_FORMEL_RE.search(text, z.start, z.ende) or len(text[z.start:z.ende].split()) <= 4):
                return True
    return False


def _namensbeleg_in(dok, tab: "_Tabelle") -> bool:
    """Steht in einer Personenspalte der Tabelle ein bekannter Vor- oder Nachname der Wissensbasis?"""
    for idx, sp in enumerate(tab.spalten):
        if "person" in sp.arten:
            for nr, s, e, _ in tab.werte[idx]:
                if _namensbeleg(dok.seiten[nr].text[s:e]):
                    return True
    return False


def _datenreihen(text: str, reihen: list, i_kopf: int, tab: _Tabelle, h: float, nr: int, ist_kopf,
                 hat_etikett=None) -> int:
    """Liest Datenreihen ab reihen[i_kopf + 1]; liefert den Index der ersten Reihe nach der Tabelle.
    hat_etikett(start, ende): steht im Textbereich ein Etikett der Wissensbasis (für die Etikettzeile eines
    Kastenformulars, die die Tabelle beendet)."""
    spalten = tab.spalten
    links = min(sp.x0 for sp in spalten) - 2.5 * h
    rechts = max(sp.x1 for sp in spalten) + 6 * h
    abstand = None
    einzeln = 0
    groesse = None                                   # Schriftgröße der letzten Datenreihe
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
        kurz = text[zellen[0].start:zellen[0].ende].strip(" .,;:|-_")
        rest = bool(tab.reihen) and len(zellen) == 1 and len(kurz) <= 2
        if rest and not any(c.isdigit() for c in kurz):
            i += 1                                   # Rest der Texterkennung ("i", "|") zwischen zwei Datenreihen
            continue                                 # eines Scans: beendet die Tabelle nicht (s7 066)
        if any(_ist_fliesstext(text, z, spalten) for z in zellen):
            break
        if zellen[0].x0 < links + 1.0 and len(zellen) == 1 and len(text[zellen[0].start:zellen[0].ende].split()) > 4:
            break
        if (len(zellen) <= 2 or _ETIKETT_DOPPELPUNKT_RE.search(text, zellen[0].start, zellen[0].ende)) \
                and any(_ETIKETT_DOPPELPUNKT_RE.search(text, z.start, z.ende) for z in zellen):
            break                                    # "Tarif: …": ein Formularblock nach der Tabelle – nicht aber
            #                                          ein OCR-Rest mit Doppelpunkt mitten in einer vollen Reihe
            #                                          ("13 Mazur, Weronika | Abs: | 16.08.66 | …")
        if groesse is not None and hat_etikett is not None and _etikettzeile(text, zellen, groesse, hat_etikett):
            break                                    # nächste Etikettzeile eines Kastenformulars (Befund 93)
        teile = []
        for z in zellen:
            teile += [(idx, s, e) for idx, s, e in _zuordnen(spalten, z, h) if idx is not None]
        if not teile:
            break
        belegte = {idx for idx, _, _ in teile}
        luecke = r.y0 - vorige_y1 if vorige_y1 is not None else None
        if tab.reihen and _folgezeile(text, teile, belegte, tab, h, luecke, abstand, hat_etikett):
            # Zellumbruch: die Zeile setzt die Zellen des letzten Datensatzes fort (Befund 84) – auch eine kurze Ziffer
            # (die Hausnummer: "Zollhäuslweg" ⏎ "7"; Nachprüfung NP-16)
            for idx, s, e in teile:
                tab.werte[idx].append((nr, s, e, tab.reihen - 1))
                tab.umbrochen.add((idx, tab.reihen - 1))
            vorige_y1 = r.y1
            i += 1
            continue
        if rest:
            i += 1                                   # kurze Ziffer, die keine Zelle fortsetzt: Rest der Texterkennung
            continue                                 # ("|" als "1" gelesen)
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
        tab.anker = frozenset(belegte)
        groesse = _schriftgroesse(zellen)
        tab.reihen += 1
        i += 1
    tab.letzte_y1 = vorige_y1 or tab.letzte_y1
    return i


# ----------------------------------------------------------------------
# Zellumbruch (Befund 84) und Etikettzeilen eines Kastenformulars (Befund 93)
# ----------------------------------------------------------------------
_VERBINDER_VORN_RE = re.compile(r"(?:und|u\.|&|\+|/|,)[ \t]*", re.IGNORECASE)
_VERBINDER_RE = re.compile(r"[ \t]*(?:/|&|\+|,|und|u\.)[ \t]*$")


def _schriftgroesse(zellen) -> float:
    """Schriftgröße einer Reihe: Median der Wortgrößen (Textebene: Schriftgrad, OCR: Höhe der Wortkästen)."""
    hoehen = sorted(w.hoehe for z in zellen for w in z.woerter if w.hoehe > 0)
    return hoehen[len(hoehen) // 2] if hoehen else 0.0


def _etikettzeile(text: str, zellen: list, groesse: float, hat_etikett) -> bool:
    """Beginnt mit der Reihe ein neuer Kopf – die nächste Etikettzeile eines Kastenformulars ("Ausgeübter Beruf ⇥⇥
    Arbeitgeber" unter "Pflegehelferin ⇥⇥ Seniorenstift St. Josef", "Eintritt ⇥⇥ Steuer-ID ⇥⇥ Beitragsgruppe" unter
    der Wertzeile einer Entgeltabrechnung)? Kleiner gesetzt als die Datenreihe darüber, mindestens zwei Zellen, keine
    Ziffern (kein Wert, Datum, Betrag) und mindestens ein Etikett der Wissensbasis. Auch wenn sie selbst kein
    vollständiger Kopf ist: ihre Werte gehören nicht zu den Spalten darüber."""
    if len(zellen) < 2 or not groesse:
        return False
    eigen = _schriftgroesse(zellen)
    if not eigen or eigen > 0.85 * groesse:
        return False
    if any(_WERTARTIG_RE.search(text, z.start, z.ende) for z in zellen):
        return False
    return any(hat_etikett(z.start, z.ende) for z in zellen)


def _namensteil(inhalt: str) -> bool:
    """Kann der Zellinhalt einen Namen fortsetzen: ohne Ziffern und Doppelpunkt, nach einem Verbinder ("und", "&",
    "/") großgeschrieben ("Gstettner", "und Walburga", "Severin und Afra", "Schwarzenböck/Lechleitner") – jedes Wort
    großgeschrieben, ein Verbinder, eine Namenspartikel ("von") oder ein abgekürzter Titelteil ("med.")? Ein verlesenes
    Feld-Etikett ("Give natıes ’ Pronmms" zwischen den Feldern eines Ausweises) setzt keinen Namen fort."""
    if not inhalt or ":" in inhalt or any(c.isdigit() for c in inhalt):
        return False
    rest = inhalt[_VERBINDER_VORN_RE.match(inhalt).end():] if _VERBINDER_VORN_RE.match(inhalt) else inhalt
    woerter = rest.split()
    if not rest or not rest[0].isupper() or len(woerter) > 5:
        return False
    for wort in woerter:
        kern = wort.rstrip(",;")
        if not kern or kern[0].isupper() or kern.casefold() in PARTIKEL or _VERBINDER_RE.fullmatch(" " + kern):
            continue
        if kern.endswith(".") and kern[:-1].isalpha() and len(kern) <= 5:
            continue                                 # "Dr. med. dent."
        return False
    return True


def _folgezeile(text: str, teile: list, belegte: set, tab: _Tabelle, h: float, luecke, abstand,
                hat_etikett=None) -> bool:
    """Ist die Reihe die nächste Zeile der Zellen darüber (Zellumbruch in schmalen Spalten: "Eheleute" ⏎ "Gstettner",
    "Am Gänsbichl" ⏎ "4, 84453 Mühldorf a. Inn")? Nur, wenn sie keine neue Zeile der Tabelle beginnt: weniger belegte
    Spalten als die erste Zeile des Datensatzes und jede davon dort schon belegt (die Spaltenlage passt), nur
    Personen- und Anschriftspalten (keine Kennung, kein Datum, kein Betrag, keine Sparte – Spalten ohne
    Personenetikett beginnen den nächsten Vertrag), Namensteile ohne Ziffern, kein Feld-Etikett der Wissensbasis
    (das nächste Feld eines Ausweises: "JABLONSKI" ⏎ "Given names / Prénoms"), kein größerer Abstand als zwischen den
    Reihen."""
    anker = tab.anker
    if not anker or not belegte < anker:
        return False
    if luecke is not None and luecke > max(1.3 * abstand if abstand else 0.9 * h, 0.5 * h):
        return False
    if hat_etikett is not None and any(hat_etikett(s, e) for _, s, e in teile):
        return False
    for idx, s, e in teile:
        arten = tab.spalten[idx].arten
        inhalt = text[s:e].strip(" \t")
        if "person" in arten:
            if not _namensteil(inhalt):
                return False
        elif "adresse" in arten:
            if not inhalt or ":" in inhalt or not (inhalt[0].isupper() or inhalt[0].isdigit()):
                return False
        else:
            return False
    return True


def _verbunden(teile: list, dok) -> tuple:
    """Zellinhalt über mehrere Zeilen als ein Text: (text, [(seite, start, ende, versatz)]) – Zeilen mit Leerzeichen
    verbunden; ein Bindestrich am Zeilenende verbindet ohne Leerzeichen ("Schwarzenböck-" ⏎ "Lechleitner")."""
    stuecke = []
    aus = ""
    for nr, s, e, _ in teile:
        t = dok.seiten[nr].text
        while s < e and t[s] in " \t":
            s += 1
        while e > s and t[e - 1] in " \t":
            e -= 1
        if e <= s:
            continue
        if aus and not aus.endswith("-"):
            aus += " "
        stuecke.append((nr, s, e, len(aus)))
        aus += t[s:e]
    return aus, stuecke


def _zurueck(stuecke: list, a: int, b: int, text: str = "") -> list:
    """Spanne [a, b) im verbundenen Text -> [(seite, start, ende)] je Zeile; Leerzeichen und Satzzeichen am Rand
    eines Zeilenstücks entfallen ("Haberl," ⏎ "Josefa" -> "Haberl" und "Josefa")."""
    aus = []
    for nr, s, e, versatz in stuecke:
        lo, hi = max(a, versatz), min(b, versatz + (e - s))
        while text and hi > lo and text[lo] in " \t,;":
            lo += 1
        while text and hi > lo and text[hi - 1] in " \t,;":
            hi -= 1
        if hi > lo:
            aus.append((nr, s + lo - versatz, s + hi - versatz))
    return aus


_ETIKETT_DOPPELPUNKT_RE = re.compile(r"[A-Za-zÄÖÜäöüß)][ ]?:(?:[ \t]|$)")


def _wert_fuer_spalte(text: str, s: int, e: int, sp: Spalte, karten_tabelle: bool = False) -> list:
    """Werte eines Zellteils nach der Art der Spalte (leer, wenn nichts Passendes darin steht). karten_tabelle: die
    Tabelle hat eine Spalte für Kartennummern (dann ist "Prüfnr." die Kartenprüfnummer)."""
    arten = sp.arten
    if "kennung" in arten:
        return _kennung(text, s, e, sp.kategorie, sp.eintrag, karten_tabelle)
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
        namen = _namen(text, s, e, nur_bekannt=bool(_ORG_ROLLEN_RE.match(sp.eintrag)))
        if _ARBEITGEBER_KOPF_RE.match(_vergleichsform(sp.eintrag)):
            return _arbeitgeber(text, s, e) + namen
        return namen
    return []


# Spaltenköpfe für Vor- und Nachnamen, auch als Kürzel aus Exporten ("VORN.", "VN_NAME", "NACHNAME_VP")
_VORNAME_KOPF_RE = re.compile(r"^(?:(?:vn|vp|kd|kunde|vers|versicherte|mitversicherte|kind) )?"
                              r"(?:vorname|vornamen|vorn|rufname|first name|given names?)(?: (?:vn|vp|kd))?$")
_NAMEN_KOPF_RE = re.compile(r"^(?:(?:vn|vp|kd|kunde|vers|versicherte|mitversicherte|kind) )?"
                            r"(?:name|nachname|familienname|vorname|vornamen|vorn|rufname|first name|given names?|"
                            r"last name|surname)(?: (?:vn|vp|kd))?$")
# ganze Zelle als Name: ein bis vier Wörter aus Buchstaben (auch Versalien, Partikel), keine Ziffern
_GANZER_NAME_RE = re.compile(r"[ \t]*([A-ZÄÖÜ][A-Za-zÄÖÜäöüßÀ-ÿ'’\-]+(?:[ ][A-Za-zÄÖÜäöüßÀ-ÿ][A-Za-zÄÖÜäöüßÀ-ÿ'’\-]*){0,3})"
                             r"[ \t]*")
_ARBEITGEBER_KOPF_RE = re.compile(r"(?:arbeitgeber(?:in)?|dienstherr|beschaftigungsbetrieb|ausbildungsbetrieb|"
                                  r"beschaftigungsstelle)\b")


def _arbeitgeber(text: str, s: int, e: int) -> list:
    """Spalte "Arbeitgeber": der ganze Zellwert ist der Arbeitgeber (Kategorie "arbeitgeber"); Organisationen
    der Erlaubnisliste (Versicherer, Banken, Behörden) bleiben stehen, Ziffern- und Strichzellen auch."""
    while s < e and text[s] in " \t":
        s += 1
    while e > s and text[e - 1] in " \t,;":
        e -= 1                                        # Schlusspunkt bleibt ("e.V.", "Gebr.")
    wert = text[s:e]
    if len(wert) < 3 or not re.search(r"[A-Za-zÄÖÜäöüß]{2}", wert) or "\n" in wert:
        return []
    if _wissen is not None:
        try:
            if _wissen.ist_allowlist(wert):
                return []
        except Exception:
            pass
    return [(s, e, "arbeitgeber", None)]


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
    # Personenspalte: ein Wochentag oder Monat ist hier ein Name ("Freitag ⇥⇥ Peter ⇥⇥ 12.03.1975", Kind "Mai ⇥⇥
    # 24.05.2020"; Nachprüfung NP-06)
    sp = namen_spanne(text, pos, e, kalender=True)
    if sp is None and not _EINRICHTUNG_RE.search(text[s:e]):
        # Betriebswort vor dem Namen ("Physiotherapie Tran", "Praxis Dr. Haidari"): ein bis zwei Wörter überspringen;
        # Einrichtungen ("Krankenhaus St. Ansgar", "Apotheke am Markt") sind keine Personen. Hinter einer
        # Personengruppe ("Erbengemeinschaft Ruhstorfer") steht ein Familienname, auch ein unbekannter (den Beleg
        # prüft _werte_der_tabelle)
        for m in list(re.finditer(r"[ \t]+", text[s:e]))[:2]:
            kandidat = namen_spanne(text, s + m.end(), e)
            if kandidat is not None and (kandidat.bekannt or any(
                    personenkontext.personengruppe(w) for w in text[s:kandidat.start].split())):
                sp, pos = kandidat, kandidat.start
                break
    while pos < e:
        if sp is None:
            sp = namen_spanne(text, pos, e, kalender=True)
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


_ZELLWORT_RE = re.compile(r"[^\s,;/&+]+")
_KETTE_RE = re.compile(r"[ \t]*(?:/|&|\+|,|;|und|u\.)[ \t]*")


def _kontext_beleg(text: str, zs: int, a: int) -> bool:
    """Steht vor dem Namen in seiner Zelle eine Anrede, ein Titel oder eine Personengruppe – direkt oder über weitere
    Namen und Verbinder ("Eheleute Gstettner", "Eheleute Severin und Afra Gstettner", "Dr. Lechleitner",
    "Grundstücksgemeinschaft Schwarzenböck/Lechleitner")? Dann ist in einer Personenspalte auch ein unbekanntes Wort
    ein Name."""
    for m in reversed(list(_ZELLWORT_RE.finditer(text, zs, a))):
        w = m.group(0)
        k = w.casefold()
        if k in _ANREDEN or _wort_ist_titel(w) or personenkontext.personengruppe(w):
            return True
        if k in ("und", "u.") or k in PARTIKEL or (w[:1].isupper() and wort_namensartig(w.rstrip(".,"))):
            continue
        return False
    return False


def _zellwerte(text: str, s: int, e: int, sp: Spalte, karten_tabelle: bool = False) -> list:
    """Werte eines Zellteils wie _wert_fuer_spalte, je Wert mit Kontextbeleg: [(a, b, kategorie, gruppe, beleg)].
    beleg (nur Namen): eine Anrede, ein Titel oder eine Personengruppe davor in der Zelle – oder ein mit "und", "/",
    "&" verbundener Name derselben Zelle ist bekannt bzw. so belegt ("Baltasar Wiesenhofer und Walburga
    Oberprieler")."""
    gefunden = _wert_fuer_spalte(text, s, e, sp, karten_tabelle)
    if "person" not in sp.arten:
        return [(a, b, kat, gruppe, False) for a, b, kat, gruppe in gefunden]
    namen = sorted((a, b) for a, b, kat, _ in gefunden if kat == "namen")
    ketten, kette = [], []
    for a, b in namen:
        if kette and not _KETTE_RE.fullmatch(text, kette[-1][1], a):
            ketten.append(kette)
            kette = []
        kette.append((a, b))
    if kette:
        ketten.append(kette)
    belegt = set()
    for kette in ketten:
        if any(_kontext_beleg(text, s, a) or _namensbeleg(text[a:b]) for a, b in kette):
            belegt.update(kette)
    return [(a, b, kat, gruppe, kat == "namen" and (a, b) in belegt) for a, b, kat, gruppe in gefunden]


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


def _kennung(text: str, s: int, e: int, kategorie: str | None, eintrag: str = "", karten_tabelle: bool = False) -> list:
    i = s
    while i < e and text[i] in " \t":
        i += 1
    m = NR_VORSATZ_RE.match(text, i, e)
    if m and m.end() < e:
        i = m.end()                                   # "Nr. KH 0815 4471 2" unter "Versicherungsschein-"
    art = "cvc" if karten_tabelle and _muster is not None and _muster.pruefnummer_etikett(eintrag) \
        else eigene_wertform(eintrag)
    if art is not None:
        # eVB, Transferticket, Kartenprüfnummer ("Prüfnr." nur in einer Tabelle mit Kartennummer): eigene Wertform, in
        # einer Spalte ohne Ziffer nie (Status wie "ERTEILT"); unter einem Nummer-Etikett zusätzlich der allgemeine
        # Kennungsweg ("TT-123" unter "Transferticket-Nr.")
        eigen = [(w.start, w.ende, "kreditkarte" if art == "cvc" else w.kategorie, None)
                 for w in eigener_wert(text, i, e, art, kategorie, True, darunter=True, etikett=eintrag)]
        if eigen or not allgemein_hinter(eintrag):
            return eigen
        if art == "cvc":
            kategorie = "vertrag"
    if kategorie == "kfz" and art is None:
        # Kennzeichen-Spalte ("Kennzeichen", "Vers.-Kennzeichen"): jede Kennzeichenform – auch Versicherungs-
        # kennzeichen ("519 TWA") und Kompaktform ("ROKL2207"), Domänen-Befund 21
        sp = kennungsformen.kfz_wert(text, i, e)
        if sp is not None and not text[sp[1]:e].strip(" .,;)"):
            return [(sp[0], sp[1], "kfz", None)]
    # dieselbe Wertform wie hinter einem Etikett (kennungsformen.kennungswert): auch Tausenderpunkt-Gruppen unter einem
    # Nummer-Kopf ("12.345.678" unter "Vertragsnr.", "7.712.345" unter "Vertrag", Domänen-Befunde 1, 67, 90) und Codes
    # mit Trennern – keine Beträge, Versionsnummern und Zahlen mit Einheit; die Selbstkontrolle liest dieselbe Wertform
    # (restrisiko._spalten_kennungen)
    sp = kennungsformen.kennungswert(text, i, e, eintrag, nr=True) if art is None else kennung_spanne(text, i, e, 3)
    if sp is None or (art is not None and not allgemeiner_wert_passt(eintrag, text[sp[0]:sp[1]])):
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
_PLZ_KOPF_RE = re.compile(r"(?:^|\b)(?:plz|postleitzahl)$")
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
        if _ORT_KOPF_RE.search(v):
            # Spalte "Ort": die ganze Zelle ist der Ort ("ST. WENDEL", "LAUF A.D.PEGNITZ", "NEUSTADT AN DER
            # WEINSTRASSE") – ort_spanne kennt nicht jede Abkürzung und hört vor "AN DER" auf
            m = _GANZER_ORT_RE.fullmatch(text, s, e)
            if m and (sp is None or m.end(1) > sp[1]) and _ganzer_ort_plausibel(m.group(1)):
                return [(m.start(1), m.end(1), "plzort", None)]
        if sp:
            return [(sp[0], sp[1], "plzort", None)]
    return []


def _ganzer_ort_plausibel(wert: str) -> bool:
    """Ganze Zelle einer Ort-Spalte als Ort: kein Ereignis- oder Betriebsort ("Parkplatz Rewe-Markt", "Tiefgarage
    Altstadt" in einer Schadenliste), kein Funktionswort ("Werkstatt Ihrer Wahl"), kleingeschrieben nur Ortszusätze
    ("Frankfurt am Main")."""
    woerter = re.findall(r"[^\W\d_][^\W\d_'’\-]*", wert)
    for w in woerter:
        k = w.casefold()
        if k in _ROH_ORTSZUSATZ:
            continue
        if k in _ROH_KEIN_WOHNORT or k in _ROH_FUNKTIONSWORT or w[0].islower():
            return False
    return bool(woerter)


_GANZER_ORT_RE = re.compile(r"[ \t]*([A-ZÄÖÜ][A-Za-zÄÖÜäöüß.\-]*(?:[ \u00a0][A-Za-zÄÖÜäöüß(][A-Za-zÄÖÜäöüß.()\-]*){0,5})"
                            r"[ \t]*")


def _kontakt(text: str, s: int, e: int, kategorie: str | None) -> list:
    aus = []
    if _muster is None:
        return aus
    if kategorie in (None, "email"):
        aus += [(a, b, "email", None) for a, b in muster_spannen(_muster.finde_email, text, s, e)]
    if kategorie in (None, "telefon"):
        aus += [(a, b, "telefon", None) for a, b in muster_spannen(_muster.finde_telefon, text, s, e)]
    return aus


def _kartendaten_in_zellen(dok, tab: _Tabelle) -> bool:
    """Stehen in den Zellen der Tabelle Kartendaten (kennungsformen.kartendaten: "Visa", eine Kartennummer mit gültiger
    Prüfziffer)? Nur gefragt, wenn ein Spaltenkopf eine Prüfnummer sein kann."""
    if _muster is None or not any(_muster.pruefnummer_etikett(sp.eintrag) for sp in tab.spalten):
        return False
    return any(kennungsformen.kartendaten(dok.seiten[nr].text[s:e]) for werte in tab.werte for nr, s, e, _ in werte)


def _werte_der_tabelle(dok, tab: _Tabelle, im_etikett=None) -> list:
    """Treffer aller Spalten einer Tabelle. im_etikett(seite, start, ende): steht dort ein Feld-Etikett ("Given" in
    "Given names / Prénoms", "Nationality" zwischen den Feldern eines Ausweises)? Dann ist es kein Name."""
    treffer = []
    hat_person = any("person" in sp.arten for sp in tab.spalten)
    vorname_idx = [i for i, sp in enumerate(tab.spalten) if "person" in sp.arten
                   and _VORNAME_KOPF_RE.match(_vergleichsform(sp.eintrag))]
    namensspalte = {i for i, sp in enumerate(tab.spalten) if "person" in sp.arten
                    and _NAMEN_KOPF_RE.match(_vergleichsform(sp.eintrag))}
    ganze_zellen = []     # Zellen einer Namensspalte ohne lesbare Namensform ("FREITAG", "NUR", "Kaplan")
    # Tabelle mit Kartendaten: eine Spalte "Kartennummer"/"Kreditkarte" oder Kartendaten in den Zellen ("Karte ⇥⇥
    # Nummer ⇥⇥ Sicherheitscode" über "Visa ⇥⇥ 4111 1111 1111 1111 ⇥⇥ 739") – dann ist "Prüfnummer"/"Sicherheitscode"
    # im Kopf die Kartenprüfnummer
    karten_tabelle = any(sp.kategorie == "kreditkarte" and not (_muster is not None and (
        _muster.pruefnummer_etikett(sp.eintrag) or _muster.eigene_wertform(sp.eintrag))) for sp in tab.spalten) \
        or _kartendaten_in_zellen(dok, tab)
    for idx, sp in enumerate(tab.spalten):
        werte = tab.werte[idx]
        if not werte:
            continue
        arten = sp.arten
        roh = []          # (seite, start, ende, kategorie, gruppe, reihe, beleg)
        for nr, s, e, reihe in werte:
            text = dok.seiten[nr].text
            gefunden = _zellwerte(text, s, e, sp, karten_tabelle)
            for a, b, kat, gruppe, beleg in gefunden:
                roh.append((nr, a, b, kat, gruppe, reihe, beleg))
            if not gefunden and idx in namensspalte:
                m = _GANZER_NAME_RE.match(text, s, e)
                if m and not text[m.end():e].strip():
                    ganze_zellen.append((nr, m.start(1), m.end(1), "namen", None, reihe, idx, False))
        roh += _umbrochene_zellen(dok, tab, idx, sp, karten_tabelle)
        if "adresse" in arten:
            roh += _strasse_ueber_zwei_reihen(dok, werte)
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
                        kandidaten.append((nr, a, a + len(inhalt), "vertrag", None, reihe, False))
                if len(kandidaten) >= 3 and len(kandidaten) >= 0.6 * nicht_leer:
                    roh.extend(kandidaten)
        for nr, a, b, kat, gruppe, reihe, beleg in roh:
            treffer.append((nr, a, b, kat, gruppe, reihe, idx, beleg))
    # Namen brauchen einen Beleg: ein bekannter Vor- oder Nachname in der Zelle – oder, bei getrennten Spalten
    # "Name" und "Vorname", in der Partnerzelle derselben Reihe ("von Schönau" neben "Silke") – oder eine Anrede,
    # ein Titel bzw. eine Personengruppe davor in der Zelle (beleg aus _zellwerte: "Eheleute Gstettner").
    # "Berlin, Hamburg" in der Kundenspalte ist kein Name.
    paar_idx = set(namensspalte)
    belegt = set()
    belegt_paar: dict = {}                           # Reihe -> Namensspalten mit belegtem Namen
    belegt_je_spalte: dict = {}
    for k, t in enumerate(treffer):
        if t[3] == "namen" and _namensbeleg(dok.seiten[t[0]].text[t[1]:t[2]]):
            belegt.add(k)
            belegt_je_spalte[t[6]] = belegt_je_spalte.get(t[6], 0) + 1
            if t[6] in paar_idx:
                belegt_paar.setdefault(t[5], set()).add(t[6])

    def partner_belegt(t) -> bool:
        # die Partnerzelle ist eine ANDERE Namensspalte derselben Reihe – nicht die Folgezeile derselben Zelle
        # (ein verlesenes Feld-Etikett "Give natıes" über "JAROSLAW" ist kein Name)
        return t[6] in paar_idx and any(j != t[6] for j in belegt_paar.get(t[5], ()))
    # Eine Namensspalte, deren Zellen überwiegend bekannte Namen tragen, ist als solche belegt: dann zählen auch
    # unbekannte Namen ("FERESHTEH", "Tschernyschow") und Namen, die zugleich Wörter sind ("FREITAG", "NUR")
    sichere_spalten = set()
    for idx in namensspalte:
        nicht_leer = sum(1 for nr, s, e, _ in tab.werte[idx] if dok.seiten[nr].text[s:e].strip())
        if belegt_je_spalte.get(idx, 0) >= 3 and belegt_je_spalte[idx] >= 0.5 * max(1, nicht_leer):
            sichere_spalten.add(idx)
    # ein Wochentag oder Monat in einer Spalte "Name"/"Vorname" ist ein Name ("Mai ⇥⇥ 24.05.2020" unter "Vorname"),
    # auch ohne bekannten Namen in der Zeile (Nachprüfung NP-06)
    namens_kopf = {i for i, sp in enumerate(tab.spalten) if _NAMEN_KOPF_RE.match(_vergleichsform(sp.eintrag))}

    def kalendername(t) -> bool:
        return t[6] in namens_kopf and dok.seiten[t[0]].text[t[1]:t[2]].strip().casefold() in DATUMSWOERTER
    # Eine Reihe mit Geburtsdatum ist der Datensatz einer Person: ihre Namensspalten tragen Namen, auch unbekannte
    # ("Status ⇥⇥ Kreszentia ⇥⇥ 04.04.1944"; Nachprüfung NP-15)
    geburt_reihen = {t[5] for t in treffer if t[3] == "geburt"}
    treffer = [t for k, t in enumerate(treffer)
               if t[3] != "namen" or k in belegt or t[7] or partner_belegt(t) or t[6] in sichere_spalten
               or kalendername(t) or (t[6] in namensspalte and t[5] in geburt_reihen)]
    # Eine ganze Zelle der Namensspalte ohne Namensform ("Stand", "Summe", "Termin": Kopf- oder Allerweltswort) ist in
    # einer Datenzeile einer Person der Name: neben einem belegten Namen derselben Reihe ("Stand ⇥⇥ Ludmilla") oder
    # mit einem Geburtsdatum in der Reihe (Nachprüfung NP-15) – nicht als Leer- oder Verweiswort ("Keine Angabe")

    def ganze_zelle_belegt(t) -> bool:
        wort = dok.seiten[t[0]].text[t[1]:t[2]].split()[0].casefold()
        return wort not in kennungsformen.KEIN_NAMENSWERT and (partner_belegt(t) or t[5] in geburt_reihen)
    zeilen_beleg = {t[:3] for t in ganze_zellen if t[6] not in sichere_spalten and ganze_zelle_belegt(t)}
    treffer += [t for t in ganze_zellen if t[6] in sichere_spalten or t[:3] in zeilen_beleg]
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
    gesehen = {}
    for nr, a, b, kat, gruppe, *_ in treffer:
        if kat == "namen" and im_etikett is not None and im_etikett(nr, a, b) \
                and not ((nr, a, b) in zeilen_beleg
                         and not kennungsformen.personen_feld_etikett(dok.seiten[nr].text[a:b])):
            continue                                 # ein Feld-Etikett – außer als belegter Name einer Datenzeile
        # dieselbe Stelle aus der Zeile und aus der ganzen umbrochenen Zelle: einmal, mit der Gruppe des ganzen Werts
        schl = (nr, a, b, kat)
        if schl in gesehen:
            if gruppe and not aus[gesehen[schl]].gruppe:
                aus[gesehen[schl]] = aus[gesehen[schl]]._replace(gruppe=gruppe)
            continue
        gesehen[schl] = len(aus)
        aus.append(Treffer(dok.global_(nr, a), dok.global_(nr, b), kat, QUELLE, SICHERHEIT_SPALTE, gruppe))
    return aus


def _strasse_ueber_zwei_reihen(dok, werte: list) -> list:
    """Straßenname allein in einer Zelle der Anschriftspalte, die Hausnummer am Anfang der Zelle derselben Spalte in
    der nächsten Reihe ("Edelweißstraße" ⏎ "4, 83080 Oberaudorf"): brechen die Nachbarspalten ebenfalls um, liest die
    Tabelle zwei Reihen statt einer umbrochenen Zelle (Gegenprüfung LK-12, Probe tab03).
    [(seite, start, ende, kategorie, gruppe, reihe, beleg)]"""
    je_reihe: dict = {}
    for nr, s, e, reihe in werte:
        je_reihe.setdefault(reihe, []).append((nr, s, e))
    aus = []
    for reihe, teile in je_reihe.items():
        folge = je_reihe.get(reihe + 1)
        if len(teile) != 1 or not folge:
            continue
        nr, s, e = teile[0]
        text = dok.seiten[nr].text
        name = text[s:e].strip().rstrip(",").rstrip()
        if not name or not STRASSENNAME_ALLEIN_RE.fullmatch(name):
            continue
        nr2, s2, e2 = folge[0]
        text2 = dok.seiten[nr2].text
        m = HAUSNUMMER_VOR_PLZ_RE.match(text2, s2, e2)
        if m is None:
            continue
        plz = plz_ort_spannen(text2, m.end(), e2)
        if text2[m.end():e2].strip() and not (plz and plz[0][0] - m.end() <= 1):
            continue                                   # "4 Zimmer", "3. OG": keine Hausnummer vor PLZ und Ort
        a = s + text[s:e].index(name)
        gruppe = f"{name} {m.group(1)}"
        aus.append((nr, a, a + len(name), "strasse", gruppe, reihe, True))
        aus.append((nr2, m.start(1), m.end(1), "strasse", gruppe, reihe + 1, True))
    return aus


def _umbrochene_zellen(dok, tab: _Tabelle, idx: int, sp: Spalte, karten_tabelle: bool) -> list:
    """Zellen einer Spalte über mehrere Zeilen (Zellumbruch, Befund 84) als Ganzes gelesen:
    [(seite, start, ende, kategorie, gruppe, reihe, beleg)]. Ein Wert über den Umbruch ("Am Gänsbichl" ⏎ "4",
    "84347" ⏎ "Pfarrkirchen", "Afra" ⏎ "Gstettner") wird je Zeile eine Stelle mit dem ganzen Wert als Gruppe: bei
    Namen derselbe Personenschlüssel, sonst ein Fund ohne Weitergabe des Bruchstücks (analyse)."""
    aus = []
    for reihe in sorted(r for i, r in tab.umbrochen if i == idx):
        teile = [w for w in tab.werte[idx] if w[3] == reihe]
        verbunden, stuecke = _verbunden(teile, dok)
        if len(stuecke) < 2:
            continue
        for a, b, kat, gruppe, beleg in _zellwerte(verbunden, 0, len(verbunden), sp, karten_tabelle):
            orte = _zurueck(stuecke, a, b, verbunden)
            if len(orte) > 1:
                gruppe = verbunden[a:b] if kat != "namen" or not gruppe else gruppe
            for nr, s, e in orte:
                aus.append((nr, s, e, kat, gruppe, reihe, beleg))
    return aus


@detektor(QUELLE, ALLE_KATEGORIEN | {"arbeitgeber"})
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

    def hat_etikett(s, e):
        return bool(_etiketten_in(ets, starts, s, e))

    def im_etikett(n, a, b):
        # Feld-Etikett dieser Seite statt eines Werts – wie die Namensprüfung von restrisiko (im_etikett und
        # Etikettwörter): ein Wort eines mehrteiligen Etiketts ("Given" in "Given names") oder ein sicher erkanntes
        # Etikettwort, das kein Name der Wissensbasis ist ("Nationality"; "Richter" kann ein Familienname sein)
        if n != nr:
            return False
        for et in _etiketten_in(ets, starts, max(0, a - 80), b):
            if et.start <= a and b <= et.ende and (" " in et.eintrag.strip() or (
                    not et.unscharf and not _namensbeleg(text[a:b]))):
                return True
        return False

    i = 0
    if offen is not None:
        # Seitenumbruch: ohne wiederholten Kopf die Reihen am Seitenanfang in den alten Spalten lesen – wenn die
        # Tabelle davor bis an den Seitenrand reichte oder die neue Seite eine Fortsetzung ankündigt ("Fortsetzung",
        # "– Seite 2") und keine andere Tabelle dazwischen begann
        vorn = reihen[:6]
        tab = None
        if not any(ist_kopf(r) for r in vorn):
            for i0 in range(len(vorn)):
                oben = any(_FORTSETZUNG_RE.search(text, z.start, z.ende) for r in reihen[:i0 + 1] for z in r.zellen)
                if not offen.bis_ende and not oben:
                    continue
                kandidat = _Tabelle(offen.spalten, reihen[i0])
                j = _datenreihen(text, reihen, i0 - 1, kandidat, h, nr, ist_kopf, hat_etikett)
                # über den Reihen eine Überschrift ohne Hinweis auf die Fortsetzung ("Übersicht der gewählten
                # Tarifbausteine"): eine neue Tabelle, außer in den Personenspalten steht ein bekannter Name; ebenso
                # eine einzelne Reihe hinter einer Ankündigung (Abnahme 2 A2-02, N8)
                ueberschrift = not oben and any(len(r.zellen) == 1 for r in reihen[:i0])
                genug = kandidat.reihen >= 2 or (kandidat.reihen == 1 and (offen.angekuendigt or oben))
                if genug and _passt_zur_tabelle(dok, kandidat) \
                        and (not (ueberschrift or kandidat.reihen == 1) or _namensbeleg_in(dok, kandidat)):
                    treffer += _werte_der_tabelle(dok, kandidat, im_etikett)
                    tab, i = kandidat, j
                    break
        if tab is not None:
            tab.angekuendigt = _fortsetzung_folgt(text, reihen, i, 0)
            tab.bis_ende = _bis_seitenende(lg, tab) or tab.angekuendigt
        offen = tab
    while i < len(reihen):
        spalten = _kopf_spalten(text, reihen[i], ets, starts, breite)
        kopf_ende = i
        if spalten is None and i + 1 < len(reihen) and len(reihen[i].zellen) == 1 \
                and len(reihen[i + 1].zellen) >= 2 \
                and not any(c.isdigit() for z in reihen[i + 1].zellen for c in text[z.start:z.ende]) \
                and _kopf_spalten(text, reihen[i + 1], ets, starts, breite) is not None:
            # Überschrift aus einer Zelle über einem vollständigen Kopf ("Mitversicherte Personen" ⏎ "Name ⇥⇥ Vorname ⇥⇥
            # geb. am"): kein zweizeiliger Kopf – die Spalte "Name" bliebe sonst ohne ihr Etikett. Eine Reihe mit
            # Ziffern ist kein Kopf, sondern eine Datenreihe hinter einem zerrissenen Rest ("MEKONNEN" ⏎ "i" ⏎ "YAW ⇥⇥
            # 2019-04-18 ⇥⇥ mitversichertes Kind" auf einem Scan)
            i += 1
            continue
        if i + 1 < len(reihen) and (spalten is None or any(not sp.arten and sp.eintrag.rstrip().endswith("-")
                                                           for sp in spalten)):
            # Kopf über zwei Zeilen – auch, wenn die erste Zeile schon ein Kopf ist, aber eine ihrer Zellen umbricht
            # ("Kennzeichen ⇥⇥ Versicherungs- ⇥⇥ Vertrag" ⏎ "bestätigung"): dann zählt der zweizeilige Kopf, wenn er
            # mehr Spalten mit Etikett kennt
            zwei = _kopf_zweizeilig(text, reihen[i], reihen[i + 1], h, breite)
            if zwei is not None and (spalten is None or sum(1 for sp in zwei if sp.arten)
                                     > sum(1 for sp in spalten if sp.arten)):
                spalten, kopf_ende = zwei, i + 1
        if spalten is not None and kopf_ende == i + 1 and i + 2 < len(reihen):
            # Titelzeile über einem zweizeiligen Kopf ("Bestandsliste Kfz" ⏎ "Kennzeichen ⇥⇥ Versicherungs- ⇥⇥
            # Vertrag" ⏎ "bestätigung"): kennt der Kopf eine Zeile tiefer mehr Spalten mit Etikett, beginnt er dort
            tiefer = _kopf_zweizeilig(text, reihen[i + 1], reihen[i + 2], h, breite)
            if tiefer is not None and sum(1 for sp in tiefer if sp.arten) > sum(1 for sp in spalten if sp.arten):
                i += 1
                continue
        if spalten is None:
            i += 1
            continue
        tab = _Tabelle(spalten, reihen[kopf_ende])
        j = _datenreihen(text, reihen, kopf_ende, tab, h, nr, ist_kopf, hat_etikett)
        if tab.reihen:
            treffer += _werte_der_tabelle(dok, tab, im_etikett)
            tab.angekuendigt = _fortsetzung_folgt(text, reihen, j, kopf_ende + 1)
            tab.bis_ende = _bis_seitenende(lg, tab) or tab.angekuendigt
            offen = tab                               # die letzte Tabelle der Seite kann sich fortsetzen
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
