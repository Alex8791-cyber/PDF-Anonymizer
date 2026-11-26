"""Kammfelder und gesperrte Schrift: ein Zeichen je Kästchen ("M U S T E R M A N N", "D E ⇥⇥ 8 8 ⇥⇥ 9 8 8 6").

Formulare "bitte in Druckbuchstaben, je Kästchen ein Zeichen" stehen in der Textebene bzw. in der OCR-Lesung als
Folge einzelner Zeichen, getrennt durch ein Leerzeichen oder – über leere Kästchen und Gruppenlücken – durch den
Spaltentrenner. Kein Muster und keine Namensliste erkennt "M A R K O V I Ć" als Namen.

»struktur.kammfeld«: Folgen von mindestens drei Zeichen-Stücken (überwiegend einzelne Buchstaben/Ziffern, die OCR
klebt manchmal zwei zusammen: "M A G D E B U RG") werden zu einem Wert verbunden. Stehen die Kästchen weit
auseinander, trennt die Textebene jedes Zeichen wie eine Zelle ("W ⇥⇥ E ⇥⇥ B ⇥⇥ E ⇥⇥ R", ausgefüllte und
eingebrannte Kammfelder); eine solche Folge nur aus Zellen zählt nur mit gleicher Teilung (Kästchen gleicher Breite,
bei langen Folgen mit Gruppenlücken) – Tabellenspalten mit je einem Zeichen haben meist verschiedene Breiten – und als
Name nur aus Buchstaben mit einem Selbstlaut ("1 ⇥⇥ 2 ⇥⇥ 3" unter "Versicherte Person" ist kein Name). Die Kategorie
kommt vom Feldnamen
(in derselben Zeile links oder allein in der Zeile darüber: Name/Vorname -> namen, Geburtsdatum -> geburt,
Straße/Hausnummer -> strasse, PLZ/Ort -> plzort, Telefon/E-Mail, Kennungen nach ihrer Art); ohne Feldnamen zählt
nur, was sich selbst ausweist (IBAN mit stimmender Prüfsumme, Steuer-ID mit Prüfziffer). Geschwärzt wird die
ganze Zeichenfolge in der Zeile.

»struktur.kammfeld_scan« (Scans): Die OCR findet Kammfelder im Bild (anonymisierer/kammraster.py), entfernt ihre Linien
vor dem Lesen und gibt ihre Lage mit (Seite.kammfelder). Was die OCR in einem gefüllten Feld liest, ist dessen Wert – wie
gut es gelesen ist, spielt keine Rolle („R1ZZO“, „0 9 ı 9 8“): hinter einem Feldnamen für personenbezogene Angaben (links
in derselben Zeile oder darüber, auch verlesen) wird alles im Feld geschwärzt; ohne Feldnamen zählt nur, was sich
selbst ausweist. Was die OCR in einem gefüllten Feld gar nicht liest, meldet die Selbstkontrolle (restrisiko).
"""

from __future__ import annotations

import bisect
import re

from . import ALLE_PROFILE, Treffer, detektor
from .. import kammraster
from .struktur import ALLE_KATEGORIEN, etiketten, lage

QUELLE = "struktur.kammfeld"
_STUECK_RE = re.compile(r"\S+")
# Vorfilter je Seite: drei einzelne Zeichen, getrennt durch ein Leerzeichen oder einen Spaltentrenner
_VORFILTER_RE = re.compile(r"(?:(?<!\S)\S(?: |[ ]?\t\t[ ]?)){3}")
# … oder ein kurzer Wert hinter einem Spaltentrenner am Zeilenende ("Initialen ⇥⇥ K H", "Hausnr. ⇥⇥ 7"; Abnahme 5 A5-08)
_VORFILTER_KURZ_RE = re.compile(r"(?m)\t[ ]?[^\W_](?:(?: |[ ]?\t\t[ ]?)[^\W_])?[ \t]*$")
_SELBSTLAUT = frozenset("AEIOUÄÖÜYÀÁÂÃÅÈÉÊËÌÍÎÏÒÓÔÕØÙÚÛÆŒ")
_PLZ_ORT_ETIKETT_RE = re.compile(r"(?i)^(?:plz|postleitzahl|ort|wohnort|plz[ ,/]*ort|postleitzahl und ort)\.?:?$")
_ZEICHEN = re.compile(r"[^\W_]|[-/.]")


def _laeufe(text: str, start: int, ende: int) -> list:
    """[(s, e, wert)] gesperrter Folgen in text[start:ende]; wert ist verbunden (Kästchenlücken als Leerzeichen)."""
    stuecke = [(m.start(), m.end()) for m in _STUECK_RE.finditer(text, start, ende)]
    aus = []
    i = 0
    while i < len(stuecke):
        j = i
        folge = []
        while j < len(stuecke):
            s, e = stuecke[j]
            t = text[s:e]
            if len(t) > 2 or not all(_ZEICHEN.fullmatch(c) for c in t):
                break
            if folge:
                zwischen = text[folge[-1][1]:s]
                if zwischen not in (" ",) and not re.fullmatch(r"[ ]?\t\t[ ]?", zwischen):
                    break
            folge.append((s, e))
            j += 1
        einzel = sum(1 for s, e in folge if e - s == 1)
        if len(folge) >= 3 and einzel >= max(3, 0.6 * len(folge)) and \
                sum(1 for s, e in folge if any(c.isalnum() for c in text[s:e])) >= 3:
            teile = []
            for k, (s, e) in enumerate(folge):
                if k and "\t" in text[folge[k - 1][1]:s]:
                    teile.append(" ")
                teile.append(text[s:e])
            aus.append((folge[0][0], folge[-1][1], "".join(teile)))
            i = j
        else:
            i += 1
    return aus


_KURZ_RE = re.compile(r"(?<!\S)([^\W_])(?:(?: |[ ]?\t\t[ ]?)([^\W_]))?[ \t]*$")


def _kurzer_lauf(text: str, start: int, ende: int):
    """(s, e, wert) eines kurzen Kammfeld-Werts am Zeilenende – ein oder zwei einzelne Zeichen ("1 3", "8"), auch über
    einen Spaltentrenner ("1 ⇥⇥ 3", "L ⇥⇥ I": weit gesetzte Kästchen trennt die Textebene wie Zellen; Abnahme 4 AB4-17)
    – oder None. Für drei und mehr Zeichen gilt _laeufe; ein so kurzer Wert zählt nur hinter einem Feldnamen
    (kammfeld)."""
    m = _KURZ_RE.search(text, start, ende)
    if m is None:
        return None
    e = m.end(2) if m.group(2) else m.end(1)
    return m.start(1), e, re.sub(r"\s+", "", text[m.start(1):e])


# ein kurzer Wert (ein oder zwei einzelne Zeichen) vor dem nächsten Feldnamen derselben Zeile ("Name ⇥⇥ R ⇥⇥ E ⇥⇥
# Vorname ⇥⇥ A N N A"; Abnahme 5 A5-08)
_KURZ_VOR_FELD_RE = re.compile(r"(?<=\t)([^\W_])(?:(?: |[ ]?\t\t[ ]?)([^\W_]))?(?=[ ]?\t\t[ ]?[^\W\d_]{2,})")


def _kurze_laeufe(text: str, start: int, ende: int, laeufe: list) -> list:
    """[(s, e, wert, neu)] kurzer Kammfeld-Werte einer Zeile: am Zeilenende (_kurzer_lauf; mit gesperrten Folgen in der
    Zeile nur hinter der letzten) und vor dem nächsten Feldnamen (_KURZ_VOR_FELD_RE) außerhalb der Folgen – ob ein
    Feldname davor steht, prüft kammfeld. neu: einer der Fälle der Abnahme 5 (nicht am Zeilenende einer Zeile ohne
    gesperrte Folge)."""
    aus = []
    ende_lauf = max((e for _, e, _ in laeufe), default=start)
    k = _kurzer_lauf(text, ende_lauf, ende)
    if k is not None and (not laeufe or text[ende_lauf:k[0]].strip()):
        aus.append((*k, bool(laeufe)))
    for m in _KURZ_VOR_FELD_RE.finditer(text, start, ende):
        e = m.end(2) if m.group(2) else m.end(1)
        if any(s0 < e and m.start(1) < e0 for s0, e0, _ in laeufe) \
                or any(a < e and m.start(1) < b for a, b, _, _ in aus):
            continue
        aus.append((m.start(1), e, re.sub(r"\s+", "", text[m.start(1):e]), True))
    return aus


def _kurz_passt(kategorie: str, wert: str) -> bool:
    """Passt ein kurzer Kammfeld-Wert zur Kategorie seines Feldnamens? Nur Hausnummern ("13", "7A", "8") und Namen
    aus zwei Buchstaben mit Selbstlaut ("LI") – Zählfelder, Kreuzchen und Kürzel hinter anderen Feldnamen nicht."""
    if kategorie == "strasse":
        return bool(re.fullmatch(r"\d[\dA-Za-z]?", wert))
    if kategorie == "namen":
        return len(wert) == 2 and _name_moeglich(wert)
    return False


def _kurz_scan(feld: dict, kompakt: str) -> bool:
    """Ist ein Kammfeld-Wert eines Scans kurz (bis zwei Zeichen)? Es zählt die größere Zahl: gelesene Buchstaben und
    Ziffern oder gefüllte Kästchen – die Texterkennung verliert in Kästchen Zeichen („LI“ als „L“ bei 300 dpi JPEG,
    eine Telefonnummer als „08“), dann ist der Wert so lang wie seine gefüllten Kästchen."""
    gefuellt = sum(1 for g in feld.get("gefuellt") or () if g)
    return max(sum(c.isalnum() for c in kompakt), gefuellt) <= 2


def _kurz_passt_scan(kategorie: str, wert: str) -> bool:
    """Wie _kurz_passt für Scans: hinter einem Feldnamen für Namen zählen auch ein Buchstabe und zwei Buchstaben ohne
    Selbstlaut – die Texterkennung kann den zweiten Buchstaben verloren haben („LI“ als „L“); Kreuzchen sind vorher
    ausgeschieden (kammraster.ausfuellhinweis)."""
    return _kurz_passt(kategorie, wert) or (kategorie == "namen" and wert.isalpha())


def _ets_index(ets: list):
    """(Anfänge, Enden) der Feldnamen einer Seite für die Suche per bisect – oder None, wenn die Liste nicht nach Lage
    geordnet und überlappungsfrei ist (struktur.etiketten liefert sie so; dann sucht der Aufrufer linear wie zuvor).
    Je Wert alle Feldnamen der Seite zu durchlaufen wuchs auf Seiten mit vielen Kammfeldern quadratisch (Abnahme 5,
    Wachstumstest)."""
    if any(a.ende > b.start for a, b in zip(ets, ets[1:])):
        return None
    adresse = [0]
    for et in ets:
        adresse.append(adresse[-1] + ("adresse" in et.arten))
    return [et.start for et in ets], [et.ende for et in ets], adresse


def _ets_zwischen(ets: list, idx, anfang: int, ende: int) -> list:
    """Die Feldnamen ganz in [anfang, ende) – in der Reihenfolge der Liste."""
    if idx is None:
        return [et for et in ets if anfang <= et.start and et.ende <= ende]
    return ets[bisect.bisect_left(idx[0], anfang):bisect.bisect_right(idx[1], ende)]


def _adresse_ab(ets: list, idx, anfang: int, vor: int) -> bool:
    """Beginnt in [anfang, vor) ein Feldname der Art Anschrift?"""
    if idx is None:
        return any(anfang <= et.start < vor and "adresse" in et.arten for et in ets)
    a, b = bisect.bisect_left(idx[0], anfang), bisect.bisect_left(idx[0], vor)
    return b > a and idx[2][b] - idx[2][a] > 0


def _letzte_zwei_davor(ets: list, idx, anfang: int, s: int) -> tuple:
    """(letzter, vorletzter) Feldname ganz in [anfang, s) – je None, wenn es ihn nicht gibt."""
    if idx is None:
        davor = [et for et in ets if anfang <= et.start and et.ende <= s]
        return (davor[-1] if davor else None), (davor[-2] if len(davor) > 1 else None)
    a, b = bisect.bisect_left(idx[0], anfang), bisect.bisect_right(idx[1], s)
    return (ets[b - 1] if b - 1 >= a else None), (ets[b - 2] if b - 2 >= a else None)


def _etikett_darueber(lg, ets: list, text: str, s: int, wert: str):
    """Feldname allein in der Zeile direkt über dem Wert. Stehen dort mehrere Feldnamen („Straße, Hausnr.“,
    „PLZ ⇥⇥ Ort“), zählt die Zeile nur, wenn alle dieselbe Kategorie ergeben – dann der waagerecht nächste."""
    zelle = lg.zelle_bei(s)
    if zelle is None:
        return None
    je_zeile = _etiketten_je_zeile(lg, ets)
    for zid in _zeilen_darueber(lg, zelle.zeile, zelle.hoehe)[:1]:
        kandidaten = je_zeile.get(zid, [])
        if len(kandidaten) == 1:
            return kandidaten[0]
        kategorien = {kategorie_fuer(et, text[et.start:et.ende], wert) for et in kandidaten}
        if len(kandidaten) > 1 and len(kategorien) == 1 and None not in kategorien:
            return min(kandidaten, key=lambda et: abs(lg.zelle_bei(et.start).x0 - zelle.x0))
    return None


def _etiketten_je_zeile(lg, ets: list) -> dict:
    """{Zeilen-ID: [Feldnamen]} – einmal je Seite und Feldnamen-Liste gebildet (je Wert sonst alle Feldnamen der Seite
    durchsucht: quadratisch auf Seiten mit vielen Kammfeldern; Abnahme 5, Wachstumstest)."""
    ablage = getattr(lg, "_kamm_ets_je_zeile", None)
    if ablage is not None and ablage[0] is ets:
        return ablage[1]
    je_zeile: dict = {}
    for et in ets:
        z = lg.zelle_bei(et.start)
        if z is not None:
            je_zeile.setdefault(z.zeile, []).append(et)
    try:
        lg._kamm_ets_je_zeile = (ets, je_zeile)
    except AttributeError:  # pragma: no cover
        pass
    return je_zeile


def _etikett_darunter(lg, ets: list, text: str, s: int, wert: str):
    """Feldname allein in der Zeile direkt unter dem Wert (Feldnamen unter den Kästchen; wie _etikett_darueber)."""
    zelle = lg.zelle_bei(s)
    if zelle is None:
        return None
    je_zeile = _etiketten_je_zeile(lg, ets)
    for zid in _zeilen_darunter(lg, zelle.zeile, zelle.hoehe)[:1]:
        kandidaten = je_zeile.get(zid, [])
        if len(kandidaten) == 1:
            return kandidaten[0]
        kategorien = {kategorie_fuer(et, text[et.start:et.ende], wert) for et in kandidaten}
        if len(kandidaten) > 1 and len(kategorien) == 1 and None not in kategorien:
            return min(kandidaten, key=lambda et: abs(lg.zelle_bei(et.start).x0 - zelle.x0))
    return None


def _zeilen_abstand(lg, et, s: int) -> float:
    """Senkrechter Abstand zwischen der Zeile des Feldnamens et und der Zeile des Werts bei s (Punkte)."""
    a, b = lg.zelle_bei(et.start), lg.zelle_bei(s)
    if a is None or b is None:
        return float("inf")
    ba, bb = lg.zeilen_box.get(a.zeile), lg.zeilen_box.get(b.zeile)
    if ba is None or bb is None:
        return float("inf")
    return max(ba[1] - bb[3], bb[1] - ba[3], 0.0)


def _teil_darueber(seite, lg, ets: list, text: str, s: int, e: int):
    """Übergeordnetes Etikett eines Werts, über dem allein ein Teil-Feldname steht ("Tag" ⏎ "2 5", "Jahr" ⏎ "2 0 1 6"):
    das nächste Etikett links in der Zeile des Werts bzw. des Teil-Feldnamens ("Geburtsdatum") – oder None."""
    zelle = lg.zelle_bei(s)
    box = _box(seite, s, e)
    if zelle is None or box is None:
        return None
    for zid in _zeilen_darueber(lg, zelle.zeile, zelle.hoehe)[:1]:
        teil = [w for w in lg.je_zeile.get(zid, ()) if kammraster.teil_etikett(text[w.start:w.ende])
                and abs(w.x0 - box[0]) <= 3.0 * max(box[3] - box[1], 6.0)]
        if not teil:
            return None
        tb = _box(seite, teil[0].start, teil[0].ende)
        beste, beste_x = None, None
        for et in ets:
            b = _box(seite, et.start, et.ende)
            if b is None or b[2] > box[0]:
                continue
            gleiche_zeile = min(b[3], box[3]) - max(b[1], box[1]) > 0.3 * (box[3] - box[1])
            teil_zeile = tb is not None and min(b[3], tb[3]) - max(b[1], tb[1]) > 0.3 * (tb[3] - tb[1])
            if (gleiche_zeile or teil_zeile) and (beste_x is None or b[2] > beste_x):
                beste, beste_x = et, b[2]
        return beste
    return None


def _nur_zellen(text: str, s: int, e: int) -> bool:
    """Trennt zwischen allen Zeichen-Stücken von text[s:e] ein Spaltentrenner (kein einzelnes Leerzeichen)?"""
    stuecke = [(m.start(), m.end()) for m in _STUECK_RE.finditer(text, s, e)]
    return all("\t" in text[a[1]:b[0]] for a, b in zip(stuecke, stuecke[1:]))


def gleiche_teilung(seite, text: str, s: int, e: int) -> bool:
    """Stehen die Zeichen-Stücke von text[s:e] in gleichem Abstand, wie in den Kästchen eines Kammfelds – alle
    Abstände höchstens 20 % über dem kleinsten, bei mindestens sechs Stücken auch mit Gruppenlücken (drei Viertel
    gleich, keiner über dem 2,5-Fachen)? Tabellenspalten mit je einem Zeichen haben meist verschiedene Breiten."""
    mitten = []
    for m in _STUECK_RE.finditer(text, s, e):
        g = seite.abbildung[m.start()] if m.start() < len(seite.abbildung) else -1
        if g < 0:
            return False
        r = seite.zeichen[g].rect
        mitten.append((r.x0 + r.x1) / 2)
    abstaende = [b - a for a, b in zip(mitten, mitten[1:])]
    if len(abstaende) < 2 or min(abstaende) <= 0:
        return False
    kleinster = min(abstaende)
    gleich = sum(1 for d in abstaende if d <= 1.2 * kleinster)
    if gleich == len(abstaende):
        return True
    return len(mitten) >= 6 and gleich >= 0.75 * len(abstaende) and max(abstaende) <= 2.5 * kleinster


def _name_moeglich(wert: str) -> bool:
    """Kann ein Kammfeld-Wert ein Name sein – nur Buchstaben (und Bindestrich/Apostroph), mindestens ein Selbstlaut?"""
    kompakt = wert.replace(" ", "")
    return (all(c.isalpha() or c in "-'’" for c in kompakt)
            and any(c.upper() in _SELBSTLAUT for c in kompakt))


def kategorie_fuer(et, etikett_text: str, wert: str) -> str | None:
    """Kategorie eines Werts hinter einem Feldnamen."""
    arten = et.arten
    if "person" in arten:
        return "namen"
    if "datum_geburt" in arten:
        return "geburt"
    if "kennung" in arten:
        return et.kategorie or "vertrag"
    if "kontakt" in arten:
        return et.kategorie or ("email" if "@" in wert else "telefon")
    if "adresse" in arten:
        return "plzort" if _PLZ_ORT_ETIKETT_RE.match(etikett_text.strip()) else "strasse"
    return None


def _ohne_etikett(wert: str) -> str | None:
    """Kategorie eines gesperrten Werts ohne Feldnamen: nur was sich selbst ausweist."""
    try:
        from .. import muster
    except Exception:  # pragma: no cover
        return None
    kompakt = wert.replace(" ", "")
    for kategorie in ("iban", "steuerid", "kvnr"):
        if any(s.streng and s.ende - s.start >= len(kompakt) - 1 for s in muster.stellen(kategorie, kompakt)):
            return kategorie
    return None


# Teil eines Datums hinter seinem Teil-Feldnamen in einer Zeile ("Geburtsdatum ⇥⇥ Tag ⇥⇥ 2 5 ⇥⇥ Monat 0 4 ⇥⇥ Jahr ⇥⇥ 2 0 1 6"):
# die Ziffern (auch gesperrt oder über Kästchenlücken) direkt hinter "Tag", "Monat", "Jahr", "TT", "MM", "JJJJ" – auf Scans
# auch so, wie die OCR Ziffern in Kästchen verliest ("Monat O 1", "Monat 0.4": O/o/I/l/S/B/Z, Punkt, Komma oder Wand
# zwischen den Ziffern); mindestens eine echte Ziffer prüft _teil_wert
# auch "Mon." (Abnahme 5 A5-08)
_TEIL_WERT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:tag|monat|mon|jahr|tt|mm|jj|jjjj)\.?:?(?: |[ ]?\t\t[ ]?)[ \t]*"
                           r"([\dOoIlSBZ](?:(?: |[ ]?\t\t[ ]?|[.,|])?[\dOoIlSBZ]){0,3})(?![\d\wäöüß])")
# ein kurzes Stück vor dem ersten Teil-Feldnamen einer OCR-Zeile, das ein verlesener Kästchenwert ist: mit Ziffer oder
# Kästchenwand ("2,35,", "ala]")
_TEIL_VORN_WERT_RE = re.compile(r"[^\s]{1,8}")


def _teil_wert(m) -> bool:
    """Hat der Wert eines Teil-Feldnamens (_TEIL_WERT_RE) mindestens eine echte Ziffer ("O 1" ja, "So" nein)?"""
    return any(c.isdigit() for c in m.group(1))


def _in_klammern(text: str, za: int, pos: int) -> bool:
    """Steht pos hinter einer offenen Klammer derselben Zeile (höchstens 40 Zeichen zurück)?"""
    vorn = text[max(za, pos - 40):pos]
    return vorn.rfind("(") > vorn.rfind(")")


def _geteiltes_datum(seite, ets: list) -> list:
    """[(start, ende, kategorie)] der Teile eines Datums in Feldern für Tag, Monat und Jahr hinter einem
    übergeordneten Feldnamen für ein Geburtsdatum in derselben Zeile ("Geburtsdatum ⇥⇥ Tag ⇥⇥ 2 5 ⇥⇥ Monat 0 4 ⇥⇥ Jahr
    ⇥⇥ 2 0 1 6"; Abnahme 4 AB4-01) – jeder Teil allein ist kurz und sein Teil-Feldname sagt nichts über den Bezug.
    Ein anderer übergeordneter Feldname (Antragsdatum, Versicherungsbeginn) lässt die Teile stehen."""
    text = seite.text
    if "ag" not in text and "onat" not in text and "ahr" not in text and "TT" not in text:
        return []
    aus = []
    idx = _ets_index(ets)
    for z in seite.zeilen:
        teile = [m for m in _TEIL_WERT_RE.finditer(text, z.start, z.ende) if _teil_wert(m)]
        if not teile:
            continue
        # ein Feldname in Klammern ("Geburtsdatum (Fahrer)", "Geb.-Datum (Kind)") ergänzt den Feldnamen davor
        # (Abnahme 5 A5-08)
        davor = [et for et in _ets_zwischen(ets, idx, z.start, teile[0].start())
                 if not _in_klammern(text, z.start, et.start)]
        if davor:
            zwischen = text[davor[-1].ende:teile[0].start()]
            if "datum_geburt" not in davor[-1].arten \
                    or any(c.isalnum() for c in re.sub(r"\([^()\n]{0,30}\)", "", zwischen)):
                continue                              # anderer Feldname oder etwas anderes dazwischen
        else:
            if not _geburt_links(seite, ets, teile[0].start()):
                continue                              # Scan: der Feldname steht in derselben Reihe links davon
            vorn = text[z.start:teile[0].start()]
            kern = vorn.strip(" \t")
            if kern:
                # Schräglage: die OCR liest "Geburtsdatum ⇥⇥ Tag" und den Wert des Tags als Anfang einer anderen Zeile
                # derselben Reihe ("2,35, ⇥⇥ Monat 0.4 ⇥⇥ Jahr ⇥⇥ 2016", 150 dpi; Abnahme 4 AB4-01): ein kurzes Stück
                # mit Ziffer oder Kästchenwand vor dem ersten Teil-Feldnamen ist der Wert des Teils davor
                if not _TEIL_VORN_WERT_RE.fullmatch(kern) \
                        or not (any(c.isdigit() for c in kern) or any(c in "[]|" for c in kern)):
                    continue
                a0 = z.start + len(vorn) - len(vorn.lstrip(" \t"))
                aus.append((a0, a0 + len(kern), "geburt"))
        aus += [(m.start(1), m.end(1), "geburt") for m in teile]
    # Scan: die OCR liest Teil-Feldname und Wert als zwei Zeilen ("Tag" ⏎ "2 5"), beide in derselben Reihe – der Wert
    # rechts neben dem Teil-Feldnamen, der Geburts-Feldname links davon (Abnahme 4 AB4-01, Scan 200 dpi)
    zeilen = list(seite.zeilen)
    for a, b in zip(zeilen, zeilen[1:]):
        if not _TEIL_ALLEIN_RE.fullmatch(text, a.start, a.ende):
            continue
        m = _ZIFFERN_VORN_RE.match(text, b.start, b.ende)
        if m is None:
            continue
        ba, bb = _box(seite, a.start, a.ende), _box(seite, m.start(1), m.end(1))
        if ba is None or bb is None:
            continue
        h = max(ba[3] - ba[1], 4.0)
        if bb[0] >= ba[2] - 1.0 and bb[0] - ba[2] <= 6.0 * h and min(ba[3], bb[3]) - max(ba[1], bb[1]) > 0.3 * h \
                and _geburt_links(seite, ets, a.start):
            aus.append((m.start(1), m.end(1), "geburt"))
    return aus


# eine OCR-Zeile nur aus einem Teil-Feldnamen bzw. eine, die mit einer kurzen Ziffernfolge beginnt (ein bis vier
# Ziffern, auch mit Kästchenwänden "2|5" oder Leerzeichen dazwischen) – dahinter nichts, ein Tabulator oder der nächste
# Teil-Feldname ("2 5 Monat ⇥⇥ Jahr")
_TEIL_ALLEIN_RE = re.compile(r"(?i)[ \t]*(?:tag|monat|mon|jahr|tt|mm|jj|jjjj)\.?:?[ \t]*")
_ZIFFERN_VORN_RE = re.compile(r"(?i)[ \t|]*(\d(?:[ \t|]{0,3}\d){0,3})(?=[ \t|]*$|\t|[ \t|]+(?:tag|monat|mon|jahr|tt|mm|jj|jjjj)"
                              r"(?![\wäöüß]))")


def _geburt_links(seite, ets: list, pos: int) -> bool:
    """Steht links in derselben Reihe (Lage der Wörter, auf Scans liest die OCR die Reihe oft als eigene Zeilen) ein
    Feldname für ein Geburtsdatum vor der Textstelle pos?"""
    box = _box(seite, pos, pos + 1)
    if box is None:
        return False
    h = max(box[3] - box[1], 4.0)
    for et in ets:
        if "datum_geburt" not in et.arten:
            continue
        b = _box(seite, et.start, et.ende)
        if b is not None and b[2] <= box[0] + 1.0 and min(b[3], box[3]) - max(b[1], box[1]) > 0.3 * h:
            return True
    return False


@detektor(QUELLE, ALLE_KATEGORIEN, ALLE_PROFILE)
def kammfeld(dok, kontext):
    """Werte in Kammfeldern/gesperrter Schrift mit der Kategorie ihres Feldnamens."""
    treffer = []
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        if text.strip() and (not kontext.aktive or "geburt" in kontext.aktive):
            teil_ets = None
            if _TEIL_WERT_RE.search(text):
                teil_ets = [et for et in etiketten(seite) if et.arten]
                for s, e, kat in _geteiltes_datum(seite, teil_ets):
                    treffer.append(Treffer(dok.global_(nr, s), dok.global_(nr, e), kat, QUELLE, 0.85))
        vorfilter_alt = bool(_VORFILTER_RE.search(text))
        if not text.strip() or not (vorfilter_alt or _VORFILTER_KURZ_RE.search(text) or _KURZ_VOR_FELD_RE.search(text)):
            continue
        laeufe_je_zeile = []
        for z in seite.zeilen:
            laeufe = _laeufe(text, z.start, z.ende)
            for s, e, wert in laeufe:
                zellen = _nur_zellen(text, s, e)
                if zellen and not gleiche_teilung(seite, text, s, e):
                    continue                          # Tabellenzeile mit je einem Zeichen in Spalten
                laeufe_je_zeile.append((z, s, e, wert, zellen, False))
            # "1 3" unter "Hausnr.": nur mit Feldnamen (unten); auch hinter einer gesperrten Folge am Zeilenende
            # ("Straße ⇥⇥ B I R K E N W E G ⇥⇥ Nr. ⇥⇥ 6 ⇥⇥ 4") und vor dem nächsten Feldnamen ("Name ⇥⇥ R ⇥⇥ E ⇥⇥ Vorname
            # ⇥⇥ A N N A"; Abnahme 5 A5-08)
            for ks, ke, kwert, neu in _kurze_laeufe(text, z.start, z.ende, laeufe):
                laeufe_je_zeile.append((z, ks, ke, kwert, False, "neu" if neu else True))
        if not laeufe_je_zeile:
            continue
        lg = lage(seite)
        ets = [et for et in etiketten(seite) if et.arten]
        idx = _ets_index(ets)
        for z, s, e, wert, zellen, kurz in laeufe_je_zeile:
            # Feldname: links in derselben Zeile (das nächste davor) oder allein in einer Zeile darüber
            et_wahl, vorher = _letzte_zwei_davor(ets, idx, z.start, s)
            if et_wahl is not None and vorher is not None and kammraster.teil_etikett(text[et_wahl.start:et_wahl.ende]) \
                    and not any(c.isalnum() for c in text[vorher.ende:et_wahl.start]):
                et_wahl = vorher                      # "Geburt ⇥⇥ Datum ⇥⇥ 2 5 0 4 …": der übergeordnete Feldname
            if et_wahl is not None:
                zwischen = re.sub(r"\([^()\n]{0,30}\)", "", text[et_wahl.ende:s])     # "(TTMMJJJJ)", "(n)"
                # ein Teil-Feldname dazwischen gehört zum Feldnamen ("Geburt ⇥⇥ Datum ⇥⇥ 2 5 0 4 …"; AB4-01)
                zwischen = " ".join(w for w in zwischen.split() if not kammraster.teil_etikett(w))
                if any(c.isalnum() for c in zwischen):
                    et_wahl = None                    # zwischen Feldname und Wert steht noch etwas anderes
            teil_oben = False
            if et_wahl is None and not text[z.start:s].strip():
                et_wahl = _etikett_darueber(lg, ets, text, s, wert)
                # Feldname unter dem Feld ("Hausnr." unter den Kästchen, darüber der Feldname des Felds darüber): der
                # nähere zählt, ein Feldname ohne Personen- oder Anschriftart darüber nicht (Abnahme 5 A5-08, A5-07)
                unten = _etikett_darunter(lg, ets, text, s, wert)
                if unten is not None and (
                        et_wahl is None or kategorie_fuer(et_wahl, text[et_wahl.start:et_wahl.ende], wert) is None
                        or _zeilen_abstand(lg, unten, s) < _zeilen_abstand(lg, et_wahl, s)):
                    et_wahl = unten
                if et_wahl is None:
                    # Teil-Feldname darüber ("Tag" ⏎ "2 5"): der übergeordnete Feldname in der Zeile des Werts links
                    # oder in der Zeile darüber ("Geburtsdatum")
                    et_wahl = _teil_darueber(seite, lg, ets, text, s, e)
                    teil_oben = et_wahl is not None
            if et_wahl is not None:
                kat = kategorie_fuer(et_wahl, text[et_wahl.start:et_wahl.ende], wert)
            else:
                kat = None if kurz else _ohne_etikett(wert)
            if teil_oben and kat != "geburt":
                continue                              # Teil eines Datums nur unter einem Geburtsdatum
            et_text = text[et_wahl.start:et_wahl.ende] if et_wahl is not None else ""
            sonder = False
            if kurz and kat is None and et_wahl is not None \
                    and re.fullmatch(r"(?i)(?:nr|no|nummer)\.?:?", et_text.strip()) \
                    and _adresse_ab(ets, idx, z.start, et_wahl.start):
                kat = "strasse"                       # "Straße ⇥⇥ B I R K E N W E G ⇥⇥ Nr. ⇥⇥ 6 ⇥⇥ 4" (A5-08)
            if kurz and kat == "geburt" and re.search(r"(?i)ort", et_text) and len(wert) == 2 and _name_moeglich(wert):
                kat, sonder = "plzort", True          # "Geburtsort ⇥⇥ A U" (Abnahme 5 A5-08)
            if kurz and kat == "namen" and re.match(r"(?i)initial", et_text) and wert.isalpha():
                sonder = True                         # "Initialen ⇥⇥ K H"
            if kurz and not vorfilter_alt and kat == "strasse" and not re.search(r"(?i)haus|nr|nummer", et_text):
                continue                              # Seite nur mit kurzen Werten: Hausnummer, nicht "Etage ⇥⇥ 1 ⇥⇥ 2"
            if kurz == "neu" and kat == "strasse" and re.fullmatch(r"(?i)(?:nr|no|nummer)\.?:?", et_text.strip()) \
                    and not _adresse_ab(ets, idx, z.start, et_wahl.start):
                continue                              # "Nr." ohne Straße in der Zeile: eine Positionsnummer
            if kurz and (kat is None or not (sonder or _kurz_passt(kat, wert) or (teil_oben and wert.isdigit()))):
                continue                              # kurzer Wert nur als Hausnummer bzw. Name hinter Feldnamen
            if kat is None or (kontext.aktive and kat not in kontext.aktive):
                continue
            if zellen and kat == "namen" and not _name_moeglich(wert):
                continue                              # "Versicherte Person ⇥⇥ 1 ⇥⇥ 2 ⇥⇥ 3": Spaltenköpfe
            treffer.append(Treffer(dok.global_(nr, s), dok.global_(nr, e), kat, QUELLE,
                                   0.85 if et_wahl is not None else 0.9))
    return treffer


def _zeilen_index(lg) -> tuple:
    """(Oberkanten, Unterkanten) der Zeilen von lg, je sortiert als [(y, zid)] – einmal je Seite gebildet, damit die
    Suche nach der Zeile darüber bzw. darunter nicht je Wert alle Zeilen durchläuft (Abnahme 5: Wachstumstest)."""
    idx = getattr(lg, "_kamm_zeilen_index", None)
    if idx is None:
        oben = sorted((b[1], z) for z, b in lg.zeilen_box.items())
        unten = sorted((b[3], z) for z, b in lg.zeilen_box.items())
        idx = ([y for y, _ in oben], [z for _, z in oben], [y for y, _ in unten], [z for _, z in unten])
        try:
            lg._kamm_zeilen_index = idx
        except AttributeError:  # pragma: no cover - Lage ohne Attribute
            pass
    return idx


def _zeilen_darunter(lg, zid: int, hoehe: float) -> list:
    """Zeilen-IDs direkt unter `zid` (nächste zuerst), höchstens gut zwei Zeilenhöhen entfernt."""
    box = lg.zeilen_box.get(zid)
    if box is None:
        return []
    h = max(hoehe, 6.0)
    oben_y, oben_z, _, _ = _zeilen_index(lg)
    kandidaten = []
    for i in range(bisect.bisect_left(oben_y, box[3] - 0.3 * h), bisect.bisect_right(oben_y, box[3] + 2.2 * h)):
        z2 = oben_z[i]
        b2 = lg.zeilen_box[z2]
        if z2 == zid:
            continue
        abstand = b2[1] - box[3]
        if min(box[2], b2[2]) - max(box[0], b2[0]) > -2 * h:
            kandidaten.append((abstand, z2))
    return [z2 for _, z2 in sorted(kandidaten)]


def _zeilen_darueber(lg, zid: int, hoehe: float) -> list:
    """Zeilen-IDs direkt über `zid` (nächste zuerst), höchstens gut zwei Zeilenhöhen entfernt."""
    box = lg.zeilen_box.get(zid)
    if box is None:
        return []
    h = max(hoehe, 6.0)
    _, _, unten_y, unten_z = _zeilen_index(lg)
    kandidaten = []
    for i in range(bisect.bisect_left(unten_y, box[1] - 2.2 * h), bisect.bisect_right(unten_y, box[1] + 0.3 * h)):
        z2 = unten_z[i]
        b2 = lg.zeilen_box[z2]
        if z2 == zid:
            continue
        abstand = box[1] - b2[3]
        if min(box[2], b2[2]) - max(box[0], b2[0]) > -2 * h:
            kandidaten.append((abstand, z2))
    return [z2 for _, z2 in sorted(kandidaten)]


# ----------------------------------------------------------------------
# Kammfelder auf Scans (Lage aus dem Bild, ocr.py/kammraster.py)
# ----------------------------------------------------------------------
QUELLE_SCAN = "struktur.kammfeld_scan"
FELD_RAND_PT = 1.5            # Zeichen mit der Mitte bis so weit außerhalb eines Felds gehören zu ihm
ETIKETT_LINKS_MAX_PT = 250.0  # Feldname links in derselben Zeile: höchstens so weit vor dem Feld
ETIKETT_OBEN_HOEHEN = 1.2     # Feldname darüber: Unterkante höchstens so viele Kästchenhöhen über dem Feld


def _woerter(seite) -> list:
    """[(start, ende, x0, y0, x1, y1)] der Wörter der Seite (Zeichenboxen; zwischengespeichert)."""
    zw = getattr(seite, "_kamm_woerter", None)
    if zw is not None and zw[0] is seite.text:
        return zw[1]
    aus = []
    abb, zeichen, text = seite.abbildung, seite.zeichen, seite.text
    for z in seite.zeilen:
        for m in _STUECK_RE.finditer(text, z.start, z.ende):
            rs = [zeichen[abb[i]].rect for i in range(m.start(), m.end()) if i < len(abb) and abb[i] >= 0]
            if rs:
                aus.append((m.start(), m.end(), min(r.x0 for r in rs), min(r.y0 for r in rs), max(r.x1 for r in rs),
                            max(r.y1 for r in rs)))
    try:
        seite._kamm_woerter = (seite.text, aus)
    except AttributeError:
        pass
    return aus


def _im_feld(w, feld) -> bool:
    """Mitte des Worts in einem Kästchen des Felds (kammraster.im_feld – nicht im Rahmen: ein schräg gelesenes Feld
    reicht mit seinem Rahmen in die Zeile darüber)."""
    return kammraster.im_feld(feld, (w[2] + w[4]) / 2.0, (w[3] + w[5]) / 2.0, rand_x=FELD_RAND_PT + 0.5,
                              rand_y=FELD_RAND_PT)


def spannen_im_feld(seite, feld) -> list:
    """[(start, ende)] der Textstücke (je Zeile zusammenhängend) aus Wörtern, deren Mitte im Feld liegt – ganze
    Wörter: ragt ein gelesenes Wort über den Rahmen (erster Buchstabe vor der ersten erkannten Wand), gehört es ganz
    dazu."""
    text = seite.text
    spannen: list = []
    for w in _woerter(seite):
        if not _im_feld(w, feld):
            continue
        if spannen and all(c in " \t" for c in text[spannen[-1][1]:w[0]]):
            spannen[-1][1] = w[1]
        else:
            spannen.append([w[0], w[1]])
    return [(a, b) for a, b in spannen]


def _box(seite, start: int, ende: int):
    rs = [seite.zeichen[seite.abbildung[i]].rect for i in range(start, ende)
          if i < len(seite.abbildung) and seite.abbildung[i] >= 0]
    if not rs:
        return None
    return (min(r.x0 for r in rs), min(r.y0 for r in rs), max(r.x1 for r in rs), max(r.y1 for r in rs))


def etikett_zum_feld(seite, feld, ets: list, felder: list = ()):
    """(Etikett, Text) des Feldnamens eines Kammfelds: ein Etikett der Seite im nächsten Text links in derselben Zeile
    bzw. in der nächsten Zeile darüber (etikett_text_zum_feld), sonst der verlesene Feldname dort (feldname_unscharf);
    (None, "") ohne Feldnamen."""
    s, e, lage_ = etikett_text_zum_feld(seite, feld, list(felder) or [feld])
    if s < 0:
        return None, ""
    drin = [et for et in ets if et.start >= s and et.ende <= e]
    if drin:
        if lage_ == "links":
            et = drin[-1]                         # das Etikett direkt vor dem Feld
        else:
            x0 = kammraster.kopfkasten(feld)[0]
            et = min(drin, key=lambda x: abs(((_box(seite, x.start, x.ende) or (x0,))[0]) - x0))
        return et, seite.text[et.start:et.ende]
    return _etikett_unscharf(seite, s, e)


def etikett_text_zum_feld(seite, feld, felder: list) -> tuple:
    """(start, ende, lage) des Texts, der als Feldname vor dem Feld steht: die Wörter links in derselben Zeile bis zur
    nächsten großen Lücke (lage "links"), sonst die nächste Zeile darüber über dem Anfang des Felds ("oben");
    (-1, -1, "") ohne solchen Text. Wörter in einem Feld zählen nicht. Es zählt der NÄCHSTE Text: ein verlesener
    Feldname wird nicht übersprungen (sonst bekäme das Feld den Namen des Felds darüber)."""
    x0, y0, _, y1 = kammraster.kopfkasten(feld)
    x1 = feld["rahmen"][2]
    hoehe = max(y1 - y0, 4.0)
    woerter = [w for w in _woerter(seite) if not any(_im_feld(w, f) for f in felder)]
    links = sorted((w for w in woerter if y0 - 0.2 * hoehe <= (w[3] + w[5]) / 2.0 <= y1 + 0.2 * hoehe
                    and w[4] <= x0 + FELD_RAND_PT and x0 - w[4] <= ETIKETT_LINKS_MAX_PT), key=lambda w: w[2])
    if links:
        gruppe = [links[-1]]
        for w in reversed(links[:-1]):
            if gruppe[0][2] - w[4] > 2.5 * max(w[5] - w[3], gruppe[0][5] - gruppe[0][3], 4.0):
                break
            gruppe.insert(0, w)
        return gruppe[0][0], gruppe[-1][1], "links"
    oben = [w for w in woerter if w[5] <= y0 + FELD_RAND_PT and y0 - w[5] <= ETIKETT_OBEN_HOEHEN * hoehe
            and x0 - 10.0 <= w[2] <= x0 + 0.5 * (x1 - x0)]
    # Feldname unter dem Feld ("[ 7 4 ]" ⏎ "Hausnr."): steht darunter Text näher am Feld als darüber, gehört er zum Feld
    # – der Text darüber ist dann der Feldname des Felds davor (Abnahme 5 A5-07)
    unten = [w for w in woerter if w[3] >= y1 - FELD_RAND_PT and w[3] - y1 <= ETIKETT_OBEN_HOEHEN * hoehe
             and x0 - 10.0 <= w[2] <= x0 + 0.5 * (x1 - x0)]
    if unten and (not oben or min(w[3] for w in unten) - y1 < y0 - max(w[5] for w in oben)) \
            and not kammraster.gehoert_zum_feld_darunter(feld, felder, min(w[3] for w in unten),
                                                         max(w[5] for w in unten)):
        naechstes = min(unten, key=lambda w: w[3])
        zeile = sorted((w for w in woerter if abs(w[3] - naechstes[3]) <= 0.5 * max(w[5] - w[3], 4.0)
                        and x0 - 10.0 <= w[2] <= x1), key=lambda w: w[2])
        return zeile[0][0], zeile[-1][1], "unten"
    if not oben:
        return -1, -1, ""
    naechstes = max(oben, key=lambda w: w[5])
    zeile = sorted((w for w in woerter if abs(w[5] - naechstes[5]) <= 0.5 * max(w[5] - w[3], 4.0)
                    and x0 - 10.0 <= w[2] <= x1), key=lambda w: w[2])
    return zeile[0][0], zeile[-1][1], "oben"


# Verlesene Feldnamen neben einem Kammfeld ("Vornameln)", "Versicherunesschein-Nr."): die Lage am Feld belegt, dass dort
# ein Feldname steht – er zählt deshalb schon mit größerer Abweichung als im Fließtext (etiketten_unscharf: nur typische
# Lesefehler) als das ähnlichste Listen-Etikett; kurze Feldnamen ("Ort", "PLZ") nur exakt
UNSCHARF_AEHNLICH = 0.8
UNSCHARF_MIN = 5
_FELD_ARTEN = ("person", "kennung", "datum_geburt", "adresse", "kontakt", "vertragsdaten")


def _feldname_text(text: str) -> str:
    t = re.sub(r"[(\[{][^()\[\]{}]{0,40}[)\]}]?", " ", text)
    return " ".join(t.replace(":", " ").split()).strip(" .,;-").casefold()


_LISTEN: dict = {}


def _feldnamen(art: str) -> tuple:
    if art not in _LISTEN:
        eintraege = ()
        try:
            from .. import wissen as _w
            eintraege = tuple(dict.fromkeys((_feldname_text(e), e) for e in _w.liste(f"etiketten_{art}")))
        except Exception:
            eintraege = ()
        _LISTEN[art] = tuple((k, e) for k, e in eintraege if len(k) >= UNSCHARF_MIN)
    return _LISTEN[art]


def feldname_unscharf(text: str):
    """(Art, Listen-Etikett) des ähnlichsten Feldnamens der Wissensbasis (Ähnlichkeit ab UNSCHARF_AEHNLICH) oder None."""
    import difflib
    t = _feldname_text(text)
    if len(t) < UNSCHARF_MIN:
        return None
    beste = None
    for art in _FELD_ARTEN:
        for klein, eintrag in _feldnamen(art):
            if abs(len(klein) - len(t)) > max(3, len(t) // 4):
                continue
            v = difflib.SequenceMatcher(None, t, klein)
            if v.real_quick_ratio() < UNSCHARF_AEHNLICH or v.quick_ratio() < UNSCHARF_AEHNLICH:
                continue
            r = v.ratio()
            if r >= UNSCHARF_AEHNLICH and (beste is None or r > beste[0]):
                beste = (r, art, eintrag)
    return (beste[1], beste[2]) if beste else None


def _etikett_unscharf(seite, s: int, e: int):
    """(Etikett, Listen-Etikett) aus einem verlesenen Feldnamen im Text [s, e) oder (None, "")."""
    from .struktur import Etikett, kennung_kategorie, kontakt_kategorie
    gefunden = feldname_unscharf(seite.text[s:e])
    if gefunden is None:
        return None, ""
    art, eintrag = gefunden
    kategorie = None
    if art == "kennung":
        kategorie = kennung_kategorie(eintrag)
        if kategorie is None:
            return None, ""
    elif art == "kontakt":
        kategorie = kontakt_kategorie(eintrag)
    return Etikett(s, e, frozenset({art}), kategorie, eintrag, True), eintrag


# Arten eines übergeordneten Feldnamens, die die Teile darunter (Tag, Monat, Jahr) zu Personenangaben machen
_PERSONEN_ARTEN = frozenset({"person", "datum_geburt", "adresse", "kontakt", "kennung"})


def uebergeordnetes_etikett(seite, feld, ets: list, felder: list = (), teilname: str = ""):
    """Etikett vor einem Feld mit Teil-Feldnamen (Tag, Monat, Jahr …; kammraster.teil_etikett): das nächste Etikett
    links in derselben Zeile außerhalb der Felder ("Geburtsdatum ⇥ Tag [..] Monat [..] Jahr [....]"), sonst eines in den
    beiden Zeilen darüber über dem Feld bzw. links davon – oder None (Abnahme 4 AB4-01). teilname "Datum"
    (kammraster.teil_ohne_datum falsch): nur ein Geburts-Feldname zählt – "Datum" unter "Name" ist das Datum der
    Unterschrift."""
    et = _uebergeordnet(seite, feld, ets, felder)
    if et is not None and teilname and not kammraster.teil_ohne_datum(teilname) and "datum_geburt" not in et.arten:
        return None
    return et


def _woerter_nach_hoehe(seite) -> tuple:
    """(Mitten, Indizes): die Wörter der Seite (_woerter) nach ihrer senkrechten Mitte sortiert – einmal je Seite, damit
    die Suche in einer Zeile nicht je Feld alle Wörter der Seite durchläuft (Abnahme 5, Wachstumstest)."""
    woerter = _woerter(seite)
    zw = getattr(seite, "_kamm_woerter_y", None)
    if zw is not None and zw[0] is woerter:
        return zw[1], zw[2]
    paare = sorted(((w[3] + w[5]) / 2.0, i) for i, w in enumerate(woerter))
    mitten, idx = [p[0] for p in paare], [p[1] for p in paare]
    try:
        seite._kamm_woerter_y = (woerter, mitten, idx)
    except AttributeError:  # pragma: no cover - Seite ohne Attribute
        pass
    return mitten, idx


def _felder_nach_hoehe(seite, felder) -> tuple:
    """(Oberkanten, Felder, größte Höhe): die Felder nach der Oberkante ihrer Kästchen sortiert – einmal je Seite und
    Feldliste (wie _woerter_nach_hoehe)."""
    zw = getattr(seite, "_kamm_felder_y", None)
    if zw is not None and zw[0] is felder:
        return zw[1]
    eintraege = []
    for f in felder:
        kaesten = f.get("kaesten") or ()
        if kaesten:
            eintraege.append((min(k[1] for k in kaesten), max(k[3] for k in kaesten), f))
    eintraege.sort(key=lambda e: e[0])
    idx = ([e[0] for e in eintraege], [e[2] for e in eintraege], max((e[1] - e[0] for e in eintraege), default=0.0))
    try:
        seite._kamm_felder_y = (felder, idx)
    except AttributeError:  # pragma: no cover - Seite ohne Attribute
        pass
    return idx


def _in_einem_feld(seite, felder, w) -> bool:
    """Liegt das Wort in einem der Felder (_im_feld) – geprüft nur gegen die Felder auf seiner Höhe?"""
    oben, sortiert, groesste = _felder_nach_hoehe(seite, felder)
    mitte = (w[3] + w[5]) / 2.0
    rand = FELD_RAND_PT + 0.5
    a = bisect.bisect_left(oben, mitte - groesste - rand)
    b = bisect.bisect_right(oben, mitte + rand)
    return any(_im_feld(w, f) for f in sortiert[a:b])


def _eigener_feldname(seite, feld, felder) -> bool:
    """Steht links vom Feld in seiner Zeile ein Wort außerhalb der Felder, das kein Teil-Feldname ist (der eigene
    Feldname der Zeile)? Über die nach Höhe sortierten Wörter und Felder der Seite (bisect), nicht je Feld über alle."""
    x0, y0, _, y1 = kammraster.kopfkasten(feld)
    hoehe = max(y1 - y0, 4.0)
    woerter = _woerter(seite)
    mitten, idx = _woerter_nach_hoehe(seite)
    for k in range(bisect.bisect_left(mitten, y0 - 0.3 * hoehe), bisect.bisect_right(mitten, y1 + 0.3 * hoehe)):
        w = woerter[idx[k]]
        if w[4] <= x0 + FELD_RAND_PT and any(c.isalpha() for c in seite.text[w[0]:w[1]]) \
                and not kammraster.teil_etikett(seite.text[w[0]:w[1]].strip(".:;,()")) \
                and not _in_einem_feld(seite, felder, w):
            return True
    return False


def _uebergeordnet(seite, feld, ets: list, felder: list = ()):
    x0, y0, x1, y1 = kammraster.kopfkasten(feld)
    hoehe = max(y1 - y0, 4.0)
    # Ein Teil-Feldname erbt zuerst vom Feldnamen davor in derselben Zeile, auch von einem ohne Personenbezug
    # ("Letzte Hauptuntersuchung ⇥ Jahr [2024]" unter "Fahrzeughalter (Name, Vorname)"; Abnahme 5 AB5U-03): steht links
    # in der Zeile Text außer Teil-Feldnamen, gilt nur ein Etikett dort – vom Feldnamen darüber erbt das Feld nur, wenn
    # die Zeile keinen eigenen hat
    eigener = _eigener_feldname(seite, feld, felder)
    beste, beste_x = None, None
    for et in ets:
        b = _box(seite, et.start, et.ende)
        if b is None or any(kammraster.im_feld(f, (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0) for f in felder):
            continue
        mitte = (b[1] + b[3]) / 2.0
        if y0 - 0.3 * hoehe <= mitte <= y1 + 0.3 * hoehe and b[2] <= x0 + FELD_RAND_PT:
            if beste_x is None or b[2] > beste_x:
                beste, beste_x = et, b[2]
    if beste is not None or eigener:
        return beste
    oben = []
    for et in ets:
        b = _box(seite, et.start, et.ende)
        if b is None or not (b[3] <= y0 + FELD_RAND_PT and y0 - b[3] <= 3.0 * hoehe and b[0] <= x0 + hoehe):
            continue
        oben.append((y0 - b[3], -b[2], et))
    return min(oben, key=lambda t: (t[0], t[1]))[2] if oben else None


# Feldname einer Hausnummer: nur er macht einen kurzen Wert unter einem Anschrift-Feldnamen zur Hausnummer – "Etage",
# "Stock", "Zimmer" nicht (Kammfeld-Probe der Abnahme 5, k04; wie die Regel der Textebene, "Etage ⇥⇥ 1 ⇥⇥ 2")
_HAUSNUMMER_ETIKETT_RE = re.compile(r"(?i)haus|nr|nummer|\bno\b")


@detektor(QUELLE_SCAN, ALLE_KATEGORIEN, ALLE_PROFILE)
def kammfeld_scan(dok, kontext):
    """Inhalt gefüllter Kammfelder auf Scans (Lage aus dem Bild) mit der Kategorie ihres Feldnamens. Ein Teil-Feldname
    (Tag, Monat, Jahr) gilt mit dem übergeordneten Feldnamen ("Geburtsdatum"; AB4-01); ein kurzer Wert (bis zwei
    Zeichen) nur als Hausnummer oder Name aus zwei Buchstaben – sonst meldet ihn die Selbstkontrolle –, ein Kreuzchen
    oder Ausfüllhinweis nie (AB4U-02/03)."""
    treffer = []
    for nr, seite in enumerate(dok.seiten):
        felder = [f for f in (getattr(seite, "kammfelder", None) or []) if any(f.get("gefuellt") or ())]
        if not felder:
            continue
        ets = [et for et in etiketten(seite) if et.arten]
        for feld in felder:
            spannen = spannen_im_feld(seite, feld)
            if not spannen:
                continue
            wert = " ".join(seite.text[a:b] for a, b in spannen)
            if kammraster.ausfuellhinweis(wert):
                continue                              # "TTMMJJJJ" im leeren Feld, Kreuzchen im Ankreuzraster
            et, etikett_text = etikett_zum_feld(seite, feld, ets, felder)
            if et is None:
                s_, e_, _ = etikett_text_zum_feld(seite, feld, felder)
                if s_ >= 0 and kammraster.teil_etikett(seite.text[s_:e_]):
                    et = uebergeordnetes_etikett(seite, feld, ets, felder, seite.text[s_:e_])
                    etikett_text = seite.text[et.start:et.ende] if et is not None else ""
                elif sum(c.isalpha() for c in wert) >= 3:
                    # eigener Feldname unlesbar ("Straße" als "See" gelesen) unter einem Feldnamen der Zeile für
                    # Personenangaben ("Anschrift ⇥ Straße [LINDENWEG] ⇥ Hausnr. [14]"): ein Wert mit Buchstaben gilt mit
                    # ihm (auf 0230782 über den Rohwert geschwärzt; Kammfeld-Probe der Abnahme 5, k04)
                    ueber = _uebergeordnet(seite, feld, ets, felder)
                    if ueber is not None and ueber.arten & _PERSONEN_ARTEN:
                        et, etikett_text = ueber, seite.text[ueber.start:ueber.ende]
            if et is not None:
                kat = kategorie_fuer(et, etikett_text, wert)
            else:
                kat = _ohne_etikett(wert)
            if kat is None or (kontext.aktive and kat not in kontext.aktive):
                continue
            kompakt = re.sub(r"[\s|]+", "", wert)
            hausnummer = kat == "strasse" and bool(_HAUSNUMMER_ETIKETT_RE.search(etikett_text or ""))
            if _kurz_scan(feld, kompakt) and kat != "geburt" and not _kurz_passt_scan(kat, kompakt) \
                    and not (hausnummer and any(c.isdigit() for c in kompakt)):
                # "DE" hinter "Staatsangehörigkeit": gemeldet (restrisiko); unter dem Feldnamen einer Hausnummer gilt
                # ein kurzer Wert mit einer Ziffer auch verlesen als Hausnummer ("27" als "2&1"; Kammfeld-Korpus
                # eigen505 der Abnahme 5, auf 0230782 geschwärzt)
                continue
            if _kurz_scan(feld, kompakt) and kat == "strasse" and not hausnummer:
                continue                              # "Lage der Wohnung ⇥ Etage [3]": keine Hausnummer, gemeldet
            for a, b in spannen:
                treffer.append(Treffer(dok.global_(nr, a), dok.global_(nr, b), kat, QUELLE_SCAN,
                                       0.8 if et is not None else 0.9))
    return treffer


def freie_werte(dok) -> list:
    """[(start, ende)] (global) der Werte gefüllter Kammfelder ohne Personenbezug: Feldname und Wertform passen
    (kammraster.wert_ohne_personenbezug – „Antragsdatum“ mit einem Datum, „Anzahl“ mit einer kleinen Zahl)."""
    aus = []
    for nr, seite in enumerate(dok.seiten):
        felder = [f for f in (getattr(seite, "kammfelder", None) or []) if any(f.get("gefuellt") or ())]
        ets = None
        for feld in felder:
            spannen = spannen_im_feld(seite, feld)
            if not spannen:
                continue
            s, e, _ = etikett_text_zum_feld(seite, feld, felder)
            if s < 0:
                continue
            wert = "".join(seite.text[a:b] for a, b in spannen)
            if kammraster.wert_ohne_personenbezug(seite.text[s:e], wert):
                if kammraster.teil_etikett(seite.text[s:e]):
                    # "Geburt ⇥ Datum [..]": der übergeordnete Feldname macht das Datum zur Personenangabe (AB4-01)
                    if ets is None:
                        ets = [et for et in etiketten(seite) if et.arten]
                    ueber = uebergeordnetes_etikett(seite, feld, ets, felder, seite.text[s:e])
                    if ueber is not None and ueber.arten & _PERSONEN_ARTEN:
                        continue
                aus += [(dok.global_(nr, a), dok.global_(nr, b)) for a, b in spannen]
    return aus


def teilfelder_mit_bezug(dok) -> list:
    """[(start, ende)] (global) der Werte gefüllter Kammfelder mit Teil-Feldnamen (Tag, Monat, Jahr) hinter einem
    übergeordneten Feldnamen für Personenangaben ("Geburtsdatum") – für die Selbstkontrolle und Tests."""
    aus = []
    for nr, seite in enumerate(dok.seiten):
        felder = [f for f in (getattr(seite, "kammfelder", None) or []) if any(f.get("gefuellt") or ())]
        if not felder:
            continue
        ets = [et for et in etiketten(seite) if et.arten]
        for feld in felder:
            s, e, _ = etikett_text_zum_feld(seite, feld, felder)
            if s < 0 or not kammraster.teil_etikett(seite.text[s:e]):
                continue
            et = uebergeordnetes_etikett(seite, feld, ets, felder, seite.text[s:e])
            if et is not None and et.arten & _PERSONEN_ARTEN:
                aus += [(dok.global_(nr, a), dok.global_(nr, b)) for a, b in spannen_im_feld(seite, feld)]
    return aus


def _feldname_spannen(dok) -> list:
    """[(start, ende)] (global) der Feldnamen (Etiketten der Seite) außerhalb der Kammfelder auf Seiten mit Kammfeldern."""
    aus = []
    for nr, seite in enumerate(dok.seiten):
        felder = getattr(seite, "kammfelder", None) or []
        if not felder:
            continue
        woerter = [w for w in _woerter(seite) if any(_im_feld(w, f) for f in felder)]
        for et in etiketten(seite):
            if et.arten and not any(w[0] < et.ende and et.start < w[1] for w in woerter):
                aus.append((dok.global_(nr, et.start), dok.global_(nr, et.ende)))
    return aus


def ohne_personenbezug(dok, treffer: list) -> list:
    """Treffer an Kammfeldern bereinigen (Scans; IMMER-Begriffe der Nutzerin bleiben unberührt):
      * ganz im Wert eines Kammfelds ohne Personenbezug (freie_werte): entfällt – eine achtstellige Zahl unter
        „Antragsdatum (TTMMJJJJ)“ ist keine Telefonnummer;
      * ein Treffer, der aus einem Feldwert über den Zeilenwechsel in den Feldnamen des nächsten Felds läuft
        ("37073⏎Wohnort": PLZ + vermeintlicher Ort), endet vor dem Feldnamen – Feldnamen sind keine Werte;
      * ein Namens-Treffer, der nur aus einem Feldnamen besteht ("Vorname", "Geburtsdatum" zwischen den Werten eines
        Kammfeld-Formulars, von der Namenserkennung für Namen gehalten), entfällt."""
    if not any(getattr(s, "kammfelder", None) for s in dok.seiten):
        return treffer
    frei = freie_werte(dok)
    namen = _feldname_spannen(dok)
    aus = []
    text = dok.text
    for t in treffer:
        if t.kategorie == "begriff":
            aus.append(t)
            continue
        if any(a <= t.start and t.ende <= b for a, b in frei):
            continue
        if t.kategorie == "namen" and any(a <= t.start and t.ende <= b for a, b in namen):
            continue
        for a, b in namen:
            if t.start < a < t.ende <= b and text[t.start:a].strip() and "\n" in text[t.start:a]:
                ende = a
                while ende > t.start and text[ende - 1].isspace():
                    ende -= 1
                t = t._replace(ende=ende)
                break
        aus.append(t)
    return aus

