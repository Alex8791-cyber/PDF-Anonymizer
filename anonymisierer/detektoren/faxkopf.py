"""Kopfzeile eines Faxausdrucks: Absenderkennung und Faxnummer des Absenders.

Empfangsgeräte drucken über (oder unter) jede Seite eine Zeile mit Datum und Uhrzeit, der Absenderkennung (im
Gerät des Absenders eingestellt: Name, Praxis, Firma), seiner Faxnummer und einem Seitenzähler – in wechselnder
Reihenfolge, oft ohne Feldnamen und je nach Gerät mit Sekunden, AM/PM oder englischen Wörtern:

    16.04.2025 14:32   MÜLLER HANS   FAX 0911 123456   S. 01/02
    16.04.2025 14:32   MUELLER HANS   +49 911 123456   S. 1/2
    Von: MÜLLER HANS  Fax: 0911 123456   An: Maklerbüro   16.04.2025 14:32   Seite 1 von 2
    16/04/2025 14:32  FROM: MUELLER HANS  +49911123456  PAGE 01/02
    APR-16-2025 02:32PM   MUELLER HANS   0911 123456   P. 1/2
    16.04.2025 14:32:07   MUELLER HANS   Fax 0911 123456   Seite 1/2
    0911 123456   MÜLLER HANS   16.04.2025 14:32   P.001

»struktur.faxkopf«: Eine Zeile im oberen oder unteren Seitenrand mit Uhrzeit (auch mit Sekunden oder AM/PM) und
Seitenzähler ("S. 1/2", "Seite 1 von 2", "P. 1/2", "P.001", "Page 1 of 2", "Bl. 1/2") ist eine Faxkopfzeile, wenn sie
zusätzlich ein Fax-Merkmal ("Fax", "Von:", "From:", "To:") oder eine Rufnummer trägt – die Lage am Rand und der Aufbau
zählen, nicht der Wortlaut eines bestimmten Geräts. Sie wird in Abschnitte zerlegt (breite Lücken, Spaltentrenner,
Feldnamen, Datum, Uhrzeit, Seitenzähler und der Wechsel von Wörtern zu Ziffern). Ein Abschnitt aus Ziffern und
Trennzeichen mit mindestens sechs Ziffern ist die Faxnummer (telefon – auch wenn die OCR auf einem 1-Bit-Fax die
führende 0 verliest), ein Abschnitt aus ein bis vier Wörtern ohne Ziffern die Absenderkennung (namen). Der Empfänger
("An: …", "To: …") bleibt stehen, ebenso Kennung und Nummer einer Organisation: Rechtsform, Organisationswort
("…SERVICE", "…ABTEILUNG") oder ein Versicherer bzw. eine Organisation der Erlaubnisliste ("HUK-COBURG", "SIGNAL
IDUNA", "Debeka") – eine einwortige Kennung, die zugleich Nachname ist ("NÜRNBERGER"), gilt weiter als Person. Eine
Druckzeile "Gedruckt am 16.04.2025 14:32 – Seite 1 von 2" hat weder Fax-Merkmal noch Rufnummer.
"""

from __future__ import annotations

import re

from . import ALLE_PROFILE, Treffer, detektor

QUELLE = "struktur.faxkopf"

_UHRZEIT_RE = re.compile(r"(?<![\d:])(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:[ ]?[AaPp]\.?[Mm]\.?)?(?![\d:])")
_ZAEHLER_RE = re.compile(
    r"(?i)(?<![\w])(?:"
    r"(?:S(?:eite)?|P(?:age|g)?|Bl(?:att)?)\.?[ \t]*\d{1,3}[ \t]*(?:/|von|of|v\.)[ \t]*\d{1,3}"   # S. 1/2, Page 1 of 2
    r"|P\.?[ \t]*\d{3}(?:[ \t]*/[ \t]*\d{3})?"                                                    # P.001, P.001/002
    r"|(?:Seite|Page|Blatt)[ \t]+\d{1,3}"                                                         # Seite 1
    r")(?![\w])")
_FAX_MERKMAL_RE = re.compile(r"(?i)(?<![\w])(?:(?:tele)?fax|von:|from:|to:|an:)")
_DATUM_RE = re.compile(r"(?i)(?<![\d])(?:\d{1,4}[./-]\d{1,2}[./-]\d{2,4}|"
                       r"(?:jan|feb|mar|apr|may|mai|jun|jul|aug|sep|oct|okt|nov|dec|dez)[a-z]*[./ -]\d{1,2}[./ ,-]+"
                       r"\d{2,4})(?![\d])")
_FELDNAME_RE = re.compile(r"(?i)(?<![\w])(?:von|an|to|from|fax|telefax|tel|telefon|absender|sender|empfänger)"
                          r"(?![\w])[ ]?[:.]?")
_LUECKE_RE = re.compile(r"\t+|[ ]{2,}")
_NUMMER_RE = re.compile(r"[+(]?[\dOoIlSBGZ][\dOoIlSBGZ ()/\-–.]{4,}[\dOoIlSBGZ]")
# Wechsel von einem Wort ohne Ziffern zu einer Ziffernfolge (und umgekehrt) trennt Abschnitte auch bei einfachen
# Leerzeichen: "FROM: MUELLER HANS 0911 123456 TO: …"
_WECHSEL_RE = re.compile(r"(?<=[^\W\d_])[ ](?=[+(]?\d)|(?<=\d)[ ](?=[^\W\d_]{2})")
_ORGANISATION_RE = re.compile(r"(?i)service|abteilung|zentrale|versicherung|assekuranz|makler|kasse|bank|"
                              r"(?<![\w])(?:gmbh|ag|se|kg|vvag|e\.?v\.?)(?![\w])")
_WORT_RE = re.compile(r"[^\W\d_][^\W\d_'’.\-]*")
_RAND_OBEN, _RAND_UNTEN = 0.12, 0.9


def _ist_faxkopf(zeile: str) -> bool:
    """Uhrzeit, Seitenzähler und ein Fax-Merkmal oder eine Rufnummer (mindestens sechs Ziffern außerhalb von Datum,
    Uhrzeit und Seitenzähler)."""
    if not (_UHRZEIT_RE.search(zeile) and _ZAEHLER_RE.search(zeile)):
        return False
    if _FAX_MERKMAL_RE.search(zeile):
        return True
    rest = zeile
    for regel in (_DATUM_RE, _UHRZEIT_RE, _ZAEHLER_RE):
        rest = regel.sub(" ", rest)
    return any(sum(c.isdigit() for c in m.group(0)) >= 6 for m in _NUMMER_RE.finditer(rest))


def abschnitte(zeile: str) -> list:
    """[(start, ende, feldname_davor)] der Abschnitte einer Faxkopfzeile (ohne Datum, Uhrzeit, Seitenzähler,
    Feldnamen und Lücken); feldname_davor ist der Feldname direkt vor dem Abschnitt in Kleinbuchstaben oder ""."""
    sperre = []
    for regel in (_DATUM_RE, _UHRZEIT_RE, _ZAEHLER_RE, _LUECKE_RE, _WECHSEL_RE):
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


def _organisation(kennung: str) -> bool:
    """Kennung einer Organisation: Rechtsform/Organisationswort oder Erlaubnisliste (Versicherer, Behörden) – die
    ganze Kennung oder ein Wort darin, das kein Personenname ist, solange kein anderes Wort ein Vor- oder Nachname
    ist ("DEBEKA KOBLENZ" ja, "NÜRNBERGER HANS" nein, "NÜRNBERGER" allein nein: auch ein Nachname)."""
    if _ORGANISATION_RE.search(kennung):
        return True
    try:
        from .. import wissen
    except Exception:  # pragma: no cover
        return False
    woerter = [w.strip(".") for w in re.split(r"[ \t]+", kennung.strip()) if w.strip(".")]
    try:
        def name(w):
            return wissen.ist_vorname(w) or wissen.ist_nachname(w)
        if wissen.ist_allowlist(kennung) and not (len(woerter) == 1 and name(woerter[0])):
            return True
        org = [w for w in woerter if len(w) >= 3 and wissen.ist_allowlist(w) and not name(w)]
        return bool(org) and not any(name(w) for w in woerter if w not in org)
    except Exception:
        return False


# Wörter, die in keiner Absenderkennung einer Person stehen, wohl aber in Druck- und Fußzeilen ("Erstellt am",
# "gültig bis", "Mo-Fr 8:00 bis 18:00") – Namenspartikel wie "von", "zu", "de" gehören nicht dazu
_KEIN_KENNUNGSWORT = frozenset("am um bis für mit im vom zum zur und oder auf aus bei nach per ab seit durch über "
                               "unter gegen".split())


def _kennung_plausibel(teil: str) -> bool:
    """Kann eine Wortgruppe die Absenderkennung sein? Kein Funktionswort, mindestens ein Wort, das weder
    Feldbezeichner noch Allerweltswort ist ("Vertrag", "Vorgang" allein sind Feldnamen einer Druckzeile)."""
    woerter = [w.strip(".") for w in _WORT_RE.findall(teil)]
    if any(w.casefold() in _KEIN_KENNUNGSWORT for w in woerter):
        return False
    try:
        from .struktur import ist_etikett_oder_allerwelt
    except Exception:  # pragma: no cover
        return True
    lang = [w for w in woerter if len(w) >= 3]
    return not lang or any(not ist_etikett_oder_allerwelt(w) for w in lang)


def faxkopf_werte(zeile: str) -> list:
    """[(start, ende, kategorie)] in einer Faxkopfzeile; [] wenn die Zeile keine ist oder eine Organisation sendet.
    Ohne Fax-Merkmal (erkannt nur an der Rufnummer) muss jede Wortgruppe der Zeile eine Kennung sein: eine Druck- oder
    Fußzeile "Erstellt am 16.04.2025 14:32   Vertrag 1234567890   Seite 1 von 2" ist kein Faxkopf."""
    if not _ist_faxkopf(zeile):
        return []
    merkmal = bool(_FAX_MERKMAL_RE.search(zeile))
    namen, nummern = [], []
    for s, e, feld in abschnitte(zeile):
        teil = zeile[s:e]
        if feld in ("an", "to", "empfänger"):
            continue                                  # Empfänger: das eigene Büro
        ziffern = sum(c.isdigit() for c in teil)
        if ziffern >= 6 and _NUMMER_RE.fullmatch(teil):
            nummern.append((s, e))
        elif ziffern == 0:
            woerter = _WORT_RE.findall(teil)
            if 1 <= len(woerter) <= 4 and sum(len(w) for w in woerter) >= 3:
                namen.append((s, e))
    if any(_organisation(zeile[s:e]) for s, e in namen) or (not namen and not nummern):
        return []
    plausibel = [(s, e) for s, e in namen if _kennung_plausibel(zeile[s:e])]
    if not merkmal and len(plausibel) < len(namen):
        return []
    namen = plausibel
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
