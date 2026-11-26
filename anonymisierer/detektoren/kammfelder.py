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

import re

from . import ALLE_PROFILE, Treffer, detektor
from .. import kammraster
from .struktur import ALLE_KATEGORIEN, etiketten, lage

QUELLE = "struktur.kammfeld"
_STUECK_RE = re.compile(r"\S+")
# Vorfilter je Seite: drei einzelne Zeichen, getrennt durch ein Leerzeichen oder einen Spaltentrenner
_VORFILTER_RE = re.compile(r"(?:(?<!\S)\S(?: |[ ]?\t\t[ ]?)){3}")
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


def _etikett_darueber(lg, ets: list, text: str, s: int, wert: str):
    """Feldname allein in der Zeile direkt über dem Wert. Stehen dort mehrere Feldnamen („Straße, Hausnr.“,
    „PLZ ⇥⇥ Ort“), zählt die Zeile nur, wenn alle dieselbe Kategorie ergeben – dann der waagerecht nächste."""
    zelle = lg.zelle_bei(s)
    if zelle is None:
        return None
    for zid in _zeilen_darueber(lg, zelle.zeile, zelle.hoehe)[:1]:
        kandidaten = [et for et in ets if lg.zelle_bei(et.start) is not None
                      and lg.zelle_bei(et.start).zeile == zid]
        if len(kandidaten) == 1:
            return kandidaten[0]
        kategorien = {kategorie_fuer(et, text[et.start:et.ende], wert) for et in kandidaten}
        if len(kandidaten) > 1 and len(kategorien) == 1 and None not in kategorien:
            return min(kandidaten, key=lambda et: abs(lg.zelle_bei(et.start).x0 - zelle.x0))
    return None


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
_TEIL_WERT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:tag|monat|jahr|tt|mm|jj|jjjj)\.?:?(?: |[ ]?\t\t[ ]?)[ \t]*"
                           r"([\dOoIlSBZ](?:(?: |[ ]?\t\t[ ]?|[.,|])?[\dOoIlSBZ]){0,3})(?![\d\wäöüß])")
# ein kurzes Stück vor dem ersten Teil-Feldnamen einer OCR-Zeile, das ein verlesener Kästchenwert ist: mit Ziffer oder
# Kästchenwand ("2,35,", "ala]")
_TEIL_VORN_WERT_RE = re.compile(r"[^\s]{1,8}")


def _teil_wert(m) -> bool:
    """Hat der Wert eines Teil-Feldnamens (_TEIL_WERT_RE) mindestens eine echte Ziffer ("O 1" ja, "So" nein)?"""
    return any(c.isdigit() for c in m.group(1))


def _geteiltes_datum(seite, ets: list) -> list:
    """[(start, ende, kategorie)] der Teile eines Datums in Feldern für Tag, Monat und Jahr hinter einem
    übergeordneten Feldnamen für ein Geburtsdatum in derselben Zeile ("Geburtsdatum ⇥⇥ Tag ⇥⇥ 2 5 ⇥⇥ Monat 0 4 ⇥⇥ Jahr
    ⇥⇥ 2 0 1 6"; Abnahme 4 AB4-01) – jeder Teil allein ist kurz und sein Teil-Feldname sagt nichts über den Bezug.
    Ein anderer übergeordneter Feldname (Antragsdatum, Versicherungsbeginn) lässt die Teile stehen."""
    text = seite.text
    if "ag" not in text and "onat" not in text and "ahr" not in text and "TT" not in text:
        return []
    aus = []
    for z in seite.zeilen:
        teile = [m for m in _TEIL_WERT_RE.finditer(text, z.start, z.ende) if _teil_wert(m)]
        if not teile:
            continue
        davor = [et for et in ets if z.start <= et.start and et.ende <= teile[0].start()]
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
_TEIL_ALLEIN_RE = re.compile(r"(?i)[ \t]*(?:tag|monat|jahr|tt|mm|jj|jjjj)\.?:?[ \t]*")
_ZIFFERN_VORN_RE = re.compile(r"(?i)[ \t|]*(\d(?:[ \t|]{0,3}\d){0,3})(?=[ \t|]*$|\t|[ \t|]+(?:tag|monat|jahr|tt|mm|jj|jjjj)"
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
        if not text.strip() or not _VORFILTER_RE.search(text):
            continue
        laeufe_je_zeile = []
        for z in seite.zeilen:
            laeufe = _laeufe(text, z.start, z.ende)
            for s, e, wert in laeufe:
                zellen = _nur_zellen(text, s, e)
                if zellen and not gleiche_teilung(seite, text, s, e):
                    continue                          # Tabellenzeile mit je einem Zeichen in Spalten
                laeufe_je_zeile.append((z, s, e, wert, zellen, False))
            kurz = None if laeufe else _kurzer_lauf(text, z.start, z.ende)
            if kurz is not None:                      # "1 3" unter "Hausnr.": nur mit Feldnamen (unten)
                laeufe_je_zeile.append((z, *kurz, False, True))
        if not laeufe_je_zeile:
            continue
        lg = lage(seite)
        ets = [et for et in etiketten(seite) if et.arten]
        for z, s, e, wert, zellen, kurz in laeufe_je_zeile:
            # Feldname: links in derselben Zeile (das nächste davor) oder allein in einer Zeile darüber
            et_wahl = None
            vorher = None
            for et in ets:
                if z.start <= et.start and et.ende <= s:
                    vorher, et_wahl = et_wahl, et     # das letzte Etikett vor dem Wert
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
            if kurz and (kat is None or not (_kurz_passt(kat, wert) or (teil_oben and wert.isdigit()))):
                continue                              # kurzer Wert nur als Hausnummer bzw. Name hinter Feldnamen
            if kat is None or (kontext.aktive and kat not in kontext.aktive):
                continue
            if zellen and kat == "namen" and not _name_moeglich(wert):
                continue                              # "Versicherte Person ⇥⇥ 1 ⇥⇥ 2 ⇥⇥ 3": Spaltenköpfe
            treffer.append(Treffer(dok.global_(nr, s), dok.global_(nr, e), kat, QUELLE,
                                   0.85 if et_wahl is not None else 0.9))
    return treffer


def _zeilen_darueber(lg, zid: int, hoehe: float) -> list:
    """Zeilen-IDs direkt über `zid` (nächste zuerst), höchstens gut zwei Zeilenhöhen entfernt."""
    box = lg.zeilen_box.get(zid)
    if box is None:
        return []
    h = max(hoehe, 6.0)
    kandidaten = []
    for z2, b2 in lg.zeilen_box.items():
        if z2 == zid:
            continue
        abstand = box[1] - b2[3]
        if -0.3 * h <= abstand <= 2.2 * h and min(box[2], b2[2]) - max(box[0], b2[0]) > -2 * h:
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


def _uebergeordnet(seite, feld, ets: list, felder: list = ()):
    x0, y0, x1, y1 = kammraster.kopfkasten(feld)
    hoehe = max(y1 - y0, 4.0)
    beste, beste_x = None, None
    for et in ets:
        b = _box(seite, et.start, et.ende)
        if b is None or any(kammraster.im_feld(f, (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0) for f in felder):
            continue
        mitte = (b[1] + b[3]) / 2.0
        if y0 - 0.3 * hoehe <= mitte <= y1 + 0.3 * hoehe and b[2] <= x0 + FELD_RAND_PT:
            if beste_x is None or b[2] > beste_x:
                beste, beste_x = et, b[2]
    if beste is not None:
        return beste
    oben = []
    for et in ets:
        b = _box(seite, et.start, et.ende)
        if b is None or not (b[3] <= y0 + FELD_RAND_PT and y0 - b[3] <= 3.0 * hoehe and b[0] <= x0 + hoehe):
            continue
        oben.append((y0 - b[3], -b[2], et))
    return min(oben, key=lambda t: (t[0], t[1]))[2] if oben else None


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
            if et is not None:
                kat = kategorie_fuer(et, etikett_text, wert)
            else:
                kat = _ohne_etikett(wert)
            if kat is None or (kontext.aktive and kat not in kontext.aktive):
                continue
            kompakt = re.sub(r"[\s|]+", "", wert)
            if _kurz_scan(feld, kompakt) and kat != "geburt" and not _kurz_passt_scan(kat, kompakt):
                continue                              # "DE" hinter "Staatsangehörigkeit": gemeldet (restrisiko)
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

