"""Kopfzeile eines Faxausdrucks: Absenderkennung und Faxnummer des Absenders.

Empfangsgeräte drucken über (oder unter) jede Seite eine Zeile mit Datum und Uhrzeit, der Absenderkennung (im
Gerät des Absenders eingestellt: Name, Praxis, Firma), seiner Faxnummer und einem Seitenzähler – in wechselnder
Reihenfolge und oft ohne Feldnamen:

    16.04.2025 14:32   MÜLLER HANS   FAX 0911 123456   S. 01/02
    Von: MÜLLER HANS  Fax: 0911 123456   An: Maklerbüro   16.04.2025 14:32   Seite 1 von 2
    0911 123456   MÜLLER HANS   16.04.2025 14:32   P.001

»struktur.faxkopf«: Eine Zeile im oberen oder unteren Seitenrand mit Uhrzeit, Seitenzähler und einem Fax-Merkmal
("Fax", "Von:", "P.001", "S. 01/02") wird in Abschnitte zerlegt (breite Lücken, Spaltentrenner, Feldnamen "Von:",
"Fax:", "An:", Datum, Uhrzeit, Seitenzähler). Ein Abschnitt aus Ziffern und Trennzeichen mit mindestens sechs
Ziffern ist die Faxnummer (telefon – auch wenn die OCR auf einem 1-Bit-Fax die führende 0 verliest), ein Abschnitt
aus ein bis vier Wörtern ohne Ziffern die Absenderkennung (namen). Der Empfänger ("An: …") bleibt stehen, ebenso
Kennung und Nummer einer Organisation (Rechtsform, Organisationswort, "…SERVICE", "…ABTEILUNG"): deren Faxkopf ist
keine Personenangabe. Eine Druckzeile "Gedruckt am 16.04.2025 14:32 – Seite 1 von 2" hat kein Fax-Merkmal.
"""

from __future__ import annotations

import re

from . import ALLE_PROFILE, Treffer, detektor

QUELLE = "struktur.faxkopf"

_UHRZEIT_RE = re.compile(r"(?<![\d:])(?:[01]?\d|2[0-3]):[0-5]\d(?![\d:])")
_ZAEHLER_RE = re.compile(r"(?i)(?<![\w])(?:S(?:eite)?\.?[ ]?\d{1,3}[ ]?(?:/|von)[ ]?\d{1,3}|P\.?[ ]?\d{3}|"
                         r"Seite[ ]\d{1,3}(?:[ ]von[ ]\S{1,3})?|Page[ ]\d{1,3}(?:/\d{1,3})?)(?![\w])")
_FAX_MERKMAL_RE = re.compile(r"(?i)(?<![\w])(?:tele)?fax(?![\w])|(?<![\w])von:|(?<![\w])P\.?[ ]?\d{3}(?![\w])|"
                             r"(?<![\w])S\.[ ]?\d{2}/\d{2}(?![\w])")
_DATUM_RE = re.compile(r"(?<![\d])\d{1,4}[./-]\d{1,2}[./-]\d{2,4}(?![\d])")
_FELDNAME_RE = re.compile(r"(?i)(?<![\w])(?:von|an|to|from|fax|telefax|tel|telefon)(?![\w])[ ]?[:.]?")
_LUECKE_RE = re.compile(r"\t+|[ ]{2,}")
_NUMMER_RE = re.compile(r"[+(]?[\dOoIlSBGZ][\dOoIlSBGZ ()/\-–.]{4,}[\dOoIlSBGZ]")
_ORGANISATION_RE = re.compile(r"(?i)service|abteilung|zentrale|versicherung|assekuranz|makler|kasse|bank|"
                              r"(?<![\w])(?:gmbh|ag|se|kg|vvag|e\.?v\.?)(?![\w])")
_WORT_RE = re.compile(r"[^\W\d_][^\W\d_'’.\-]*")
_RAND_OBEN, _RAND_UNTEN = 0.12, 0.9


def _ist_faxkopf(zeile: str) -> bool:
    return bool(_UHRZEIT_RE.search(zeile) and _ZAEHLER_RE.search(zeile) and _FAX_MERKMAL_RE.search(zeile))


def abschnitte(zeile: str) -> list:
    """[(start, ende, feldname_davor)] der Abschnitte einer Faxkopfzeile (ohne Datum, Uhrzeit, Seitenzähler,
    Feldnamen und Lücken); feldname_davor ist der Feldname direkt vor dem Abschnitt in Kleinbuchstaben oder ""."""
    sperre = []
    for regel in (_DATUM_RE, _UHRZEIT_RE, _ZAEHLER_RE, _LUECKE_RE):
        sperre.extend((m.start(), m.end(), "") for m in regel.finditer(zeile))
    for m in _FELDNAME_RE.finditer(zeile):
        sperre.append((m.start(), m.end(), m.group(0).strip(" :.").casefold()))
    sperre.sort()
    aus = []
    pos, feld = 0, ""
    for a, b, name in sperre + [(len(zeile), len(zeile), "")]:
        if a > pos:
            s, e = pos, a
            while s < e and zeile[s] in " ‘’'\"„“,;:|":
                s += 1
            while e > s and zeile[e - 1] in " ‘’'\"„“,;:|":
                e -= 1
            if e > s:
                aus.append((s, e, feld))
                feld = ""
        if b > pos:
            pos = b
        if name:
            feld = name
    return aus


def faxkopf_werte(zeile: str) -> list:
    """[(start, ende, kategorie)] in einer Faxkopfzeile; [] wenn die Zeile keine ist oder eine Organisation sendet."""
    if not _ist_faxkopf(zeile):
        return []
    namen, nummern = [], []
    for s, e, feld in abschnitte(zeile):
        teil = zeile[s:e]
        if feld in ("an", "to"):
            continue                                  # Empfänger: das eigene Büro
        ziffern = sum(c.isdigit() for c in teil)
        if ziffern >= 6 and _NUMMER_RE.fullmatch(teil):
            nummern.append((s, e))
        elif ziffern == 0:
            woerter = _WORT_RE.findall(teil)
            if 1 <= len(woerter) <= 4 and sum(len(w) for w in woerter) >= 3:
                namen.append((s, e))
    if any(_ORGANISATION_RE.search(zeile[s:e]) for s, e in namen) or (not namen and not nummern):
        return []
    if not _namen_plausibel(zeile, namen):
        return []
    return [(s, e, "namen") for s, e in namen] + [(s, e, "telefon") for s, e in nummern]


def _namen_plausibel(zeile: str, namen: list) -> bool:
    """Mindestens ein Wort der Kennung ist weder Feldbezeichner noch Allerweltswort."""
    if not namen:
        return True
    try:
        from .struktur import ist_etikett_oder_allerwelt
    except Exception:  # pragma: no cover
        return True
    woerter = [w.strip(".") for s, e in namen for w in _WORT_RE.findall(zeile[s:e]) if len(w.strip(".")) >= 3]
    return any(not ist_etikett_oder_allerwelt(w) for w in woerter)


@detektor(QUELLE, {"namen", "telefon"}, ALLE_PROFILE)
def faxkopf(dok, kontext):
    """Absenderkennung und Faxnummer in der Kopf- bzw. Fußzeile eines Faxausdrucks."""
    treffer = []
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        if not text.strip() or not _UHRZEIT_RE.search(text):
            continue
        try:
            from .struktur import lage
            lg = lage(seite)
            hoehe = lg.hoehe_seite or 0.0
        except Exception:  # pragma: no cover
            lg, hoehe = None, 0.0
        zeilen = list(seite.zeilen)
        for i, z in enumerate(zeilen):
            box = lg.zeilen_box.get(z.id) if lg is not None else None
            if box is not None and hoehe > 0:
                if not (box[3] <= _RAND_OBEN * hoehe or box[1] >= _RAND_UNTEN * hoehe):
                    continue
            elif 2 <= i < len(zeilen) - 2:
                continue
            for s, e, kat in faxkopf_werte(text[z.start:z.ende]):
                if kontext.aktive and kat not in kontext.aktive:
                    continue
                treffer.append(Treffer(dok.global_(nr, z.start + s), dok.global_(nr, z.start + e), kat, QUELLE, 0.8,
                                       None))
    return treffer
