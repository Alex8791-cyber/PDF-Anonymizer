"""Muster-Erkennung (reguläre Ausdrücke mit Validierung), Kategorienliste und Schutzstufen.

Zwei Schnittstellen je Kategorie:

- ``finde_<x>(text) -> list[str]``: die Fundtexte so, wie sie im Text stehen (bisherige Schnittstelle).
- ``finde_<x>_stellen(text) -> list[tuple[int, int]]``: die Stellen (Start, Ende) im übergebenen Text –
  für Detektoren, die Spans liefern (Vertrag Abschnitt 2/3).
- ``stellen(kategorie, text) -> list[Stelle]``: alle Stellen einer Kategorie samt Sicherheit und Hinweis,
  auch die unsicheren (z. B. eine IBAN, deren Prüfziffer nicht stimmt – meist ein OCR-Lesefehler; sie wird
  trotzdem geschwärzt, nur mit geringerer Sicherheit). Die ``finde_*``-Funktionen liefern nur die sicheren.

Unicode (Vertrag 12.7): Text von außen kann NBSP, schmale Leerzeichen, sichtbare weiche Trennstriche
(U+00AD) oder geschützte Bindestriche (U+2011) enthalten (Windows-Schriften). Alle Muster laufen deshalb auf
dem normalisierten Text (``seitenmodell.normalisiere_text``, dieselbe Regel wie im Seitenmodell); die Stellen
werden auf den Eingabetext zurückgerechnet.

Die Muster laufen bewusst nicht über Zeilenumbrüche (Ausnahmen: IBAN und PLZ+Ort mit genau einem Umbruch,
Telefonnummern hinter einem Etikett, Daten mit ausgeschriebenem Monat und Aktenzeichen, die am Zeilenende
umbrechen), und alle Wiederholungen sind nach oben begrenzt, damit lange Zeilen nicht zu quadratischer Laufzeit
führen. Über den Spaltentrenner "\\t\\t" des Seitenmodells läuft kein Muster in eine Nachbarzelle (einzige Stelle
mit Trenner: eine reine PLZ-Zelle mit der Ort-Zelle daneben, siehe plz_ort_zellenpaar). Lesefehler-Toleranz für
OCR-Text (O/0, I/1, eingefügte Doppelpunkte …) liegt in detektoren/ocr_lesart.py – nur dort ist bekannt, welcher
Text aus der OCR stammt.

Außerdem: ``KATEGORIEN`` (Häkchen der Oberfläche), ``KATEGORIE_PRIORITAET`` und ``PROFILE`` (Schutzstufen,
Vertrag Abschnitt 9).
"""

import datetime
import re
from collections import Counter
from typing import NamedTuple


def _suche(muster, text, flags=0):
    return [m.group(0) for m in re.finditer(muster, text, flags)]


def _heute():
    return datetime.date.today()


def _eindeutig(treffer):
    """Doppelte Fundtexte entfernen, Reihenfolge beibehalten."""
    gesehen, aus = set(), []
    for t in treffer:
        if t not in gesehen:
            gesehen.add(t)
            aus.append(t)
    return aus


# ----------------------------------------------------------------------
# Wortgrenzen (Gutachten KQ-11: EINE Definition, deckungsgleich mit str.isalnum der Schwärzung)
# ----------------------------------------------------------------------
KEIN_WORTZEICHEN_DAVOR = r"(?<![^\W_])"
KEIN_WORTZEICHEN_DANACH = r"(?![^\W_])"


class Stelle(NamedTuple):
    """Fundstelle eines Musters: [start, ende) im Text, Sicherheit (None = Standard der Kategorie),
    streng=False für Funde, die nur mit Nachsicht passen (Prüfziffer falsch, Etikett fehlt …), und ein
    Hinweis für die Fundliste."""
    start: int
    ende: int
    sicherheit: float | None = None
    streng: bool = True
    hinweis: str | None = None


HINWEIS_PRUEFZIFFER = "Prüfziffer ungültig (Lesefehler?)"


# ----------------------------------------------------------------------
# Unicode-Normalisierung (Vertrag 12.7)
# ----------------------------------------------------------------------
# Zeichen, die die Normalisierung verändert (Gedanken-/Minusstrich nur zwischen Ziffern – sonst bleibt er, und der
# schnelle Weg ohne Normalisierung gilt)
_SONDER_RE = re.compile("[ ­  -‍‐‑    ⁠"
                        "　﻿０-９ﬀ-ﬆ]|(?<=[0-9])[‒–−](?=[0-9])")
_NORM_ZULETZT: list = [None, None]          # [Text, (Text, Abbildung)] – Detektoren fragen denselben Text mehrfach
_EINFACH = {**{c: " " for c in "      　"},
            **{chr(c): " " for c in range(0x2000, 0x200B)},
            **{c: "" for c in "​‌‍⁠﻿"},
            **{c: "-" for c in "‐‑‒–−"},
            **{chr(0xFF10 + i): str(i) for i in range(10)},
            "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st",
            "ﬆ": "st"}


def _normalisieren_einfach(text: str) -> tuple:
    """Rückfall ohne Seitenmodell: dieselben Zeichenregeln, zeichenweise."""
    teile, abbildung = [], []
    for i, c in enumerate(text):
        if c == "­":
            if i + 1 < len(text) and text[i + 1] == "\n":
                continue                                 # Silbentrennung am Zeilenende
            n = "-" if 0 < i and text[i - 1].isalnum() and i + 1 < len(text) and text[i + 1].isalnum() else ""
        else:
            n = _EINFACH.get(c, c)
        teile.append(n)
        abbildung.extend([i] * len(n))
    return "".join(teile), abbildung


def normalisieren(text: str) -> tuple:
    """(normalisierter Text, Abbildung) nach Vertrag 12.7. abbildung[i] = Index im Eingabetext, aus dem
    Zeichen i stammt (-1 = eingefügt); None, wenn der Text keine Sonderzeichen enthält (dann ist er schon
    normalisiert und wird unverändert zurückgegeben)."""
    if not text or not _SONDER_RE.search(text):
        return text, None
    if _NORM_ZULETZT[0] is text:
        return _NORM_ZULETZT[1]
    try:
        from .seitenmodell import normalisiere_text
        ergebnis = normalisiere_text(text)
    except Exception:  # pragma: no cover - Seitenmodell nicht ladbar
        ergebnis = _normalisieren_einfach(text)
    _NORM_ZULETZT[:] = [text, ergebnis]
    return ergebnis


def _zurueck(abbildung, s: int, e: int):
    """Stelle im normalisierten Text -> Stelle im Eingabetext (oder None)."""
    a = next((abbildung[i] for i in range(s, e) if abbildung[i] >= 0), None)
    b = next((abbildung[i] for i in range(e - 1, s - 1, -1) if abbildung[i] >= 0), None)
    if a is None or b is None or b < a:
        return None
    return a, b + 1


def _auf_eingabe(text: str, spannen_funktion) -> list:
    """Führt eine Spannen-Funktion auf dem normalisierten Text aus und rechnet die Stellen zurück."""
    if not text:
        return []
    norm, abbildung = normalisieren(text)
    roh = spannen_funktion(norm)
    if abbildung is None:
        return roh
    aus = []
    for st in roh:
        z = _zurueck(abbildung, st.start, st.ende)
        if z is not None:
            aus.append(st._replace(start=z[0], ende=z[1]))
    return aus


# ----------------------------------------------------------------------
# IBAN
# ----------------------------------------------------------------------
# Länge je Länderkürzel (Zeichen ohne Leerraum). Damit wird ein Kandidat genau
# auf die IBAN gekürzt, statt dass ein Folgewort (BIC, EUR, Jahreszahl) die
# Prüfsumme kippt.
IBAN_LAENGEN = {
    "DE": 22, "AT": 20, "CH": 21, "LI": 21, "LU": 20, "BE": 16, "NL": 18, "FR": 27,
    "IT": 27, "ES": 24, "PT": 25, "PL": 28, "CZ": 24, "SK": 24, "HU": 28, "DK": 18,
    "SE": 24, "NO": 15, "FI": 18, "IE": 22, "GB": 22, "HR": 21, "SI": 19, "RO": 24,
    "BG": 22, "GR": 27, "TR": 26, "EE": 20, "LV": 21, "LT": 20, "MT": 31, "CY": 28,
    "IS": 26, "MC": 27, "SM": 27, "AD": 24, "GI": 23, "FO": 18, "GL": 18, "UA": 29,
    "RS": 22, "BA": 20, "ME": 22, "MK": 19, "AL": 28, "MD": 24, "GE": 22, "IL": 23,
    "SA": 24, "AE": 23, "QA": 29, "KW": 30, "BH": 22, "TN": 24, "BR": 29,
}
# Länder, deren Kontoteil (BBAN) nur aus Ziffern besteht
_IBAN_NUR_ZIFFERN = {"DE", "AT", "BE", "DK", "FI", "NO", "SE", "PL", "CZ", "SK", "HU", "SI", "HR", "ES", "PT",
                     "LU", "EE", "LT", "RS", "BA", "ME", "MK", "TN", "IS", "FO", "GL", "IL", "AE", "SA", "TR"}
# typische OCR-Verleser in Ziffernfolgen
_OCR_ZIFFERN = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1", "i": "1",
                              "S": "5", "s": "5", "G": "6", "B": "8", "Z": "2", "z": "2"})


def _iban_gueltig(iban: str) -> bool:
    """Prüfziffern-Kontrolle (Modulo 97) — filtert Zufallstreffer heraus."""
    s = re.sub(r"\s", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    umgestellt = s[4:] + s[:4]
    zahl = "".join(str(int(z, 36)) for z in umgestellt)
    return int(zahl) % 97 == 1


def _iban_pruefen(kandidat: str) -> bool:
    """Prüfsumme — zusätzlich tolerant gegen typische OCR-Verleser (O statt 0, I/l statt 1)
    hinter dem Länderkürzel."""
    if _iban_gueltig(kandidat):
        return True
    kopf, rest = kandidat[:2], kandidat[2:]
    korrigiert = rest.replace("O", "0").replace("o", "0").replace("I", "1").replace("l", "1")
    return korrigiert != rest and _iban_gueltig(kopf + korrigiert)


_IBAN_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}(?:\s?[A-Za-z0-9]{4}){2,7}(?:\s?[A-Za-z0-9]{1,4})?(?![A-Za-z0-9])")
# Form einer IBAN mit OCR-verlesenen Prüfziffern ("DESG 9065 …" statt "DE56 9065 …")
_IBAN_OCR_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:DE|AT|CH|NL|BE|LU|FR|IT|ES|PL)[0-9OSGBZIl]{2}(?:[ \t]?[A-Za-z0-9]{4}){2,7}"
    r"(?:[ \t]?[A-Za-z0-9]{1,4})?(?![A-Za-z0-9])")
_IBAN_ETIKETT_DAVOR_RE = re.compile(r"(?i:iban|konto|bankverbindung)[^\n]{0,20}$")


def _iban_form_stark(kandidat: str, text: str, start: int) -> bool:
    """Sieht der Kandidat (Prüfziffer falsch) trotzdem eindeutig wie eine IBAN aus? Länderkürzel bekannt,
    Länge stimmt, Kontoteil (nach OCR-Korrektur) überwiegend Ziffern, und entweder in Vierergruppen
    geschrieben, hinter "IBAN"/"Konto" oder eine kompakte deutsche IBAN aus 20 Ziffern."""
    kompakt = re.sub(r"\s", "", kandidat)
    land = kompakt[:2].upper()
    if IBAN_LAENGEN.get(land) != len(kompakt):
        return False
    rest = kompakt[2:].translate(_OCR_ZIFFERN)
    if not rest[:2].isdigit():
        return False
    ziffern = sum(c.isdigit() for c in rest)
    if land in _IBAN_NUR_ZIFFERN:
        if ziffern < len(rest) - 1:
            return False
    elif ziffern < 0.6 * len(rest):
        return False
    gruppen = re.fullmatch(r"[A-Za-z0-9]{4}(?:[ \t][A-Za-z0-9]{4})+(?:[ \t][A-Za-z0-9]{1,4})?", kandidat)
    etikett = _IBAN_ETIKETT_DAVOR_RE.search(text[max(0, start - 30):start].rsplit("\n", 1)[-1])
    return bool(gruppen or etikett or (land == "DE" and kompakt[2:].isdigit()))


def _iban_kuerzen(kandidat: str, soll: int):
    """Ende (Index im Kandidaten) nach `soll` Zeichen ohne Leerraum, sonst None."""
    gezaehlt = 0
    for i, zeichen in enumerate(kandidat):
        if not zeichen.isspace():
            gezaehlt += 1
        if gezaehlt == soll:
            return i + 1
    return None


def _iban_spannen(text: str) -> list:
    ergebnisse, pos = [], 0
    while True:
        m = _IBAN_RE.search(text, pos)
        if not m:
            break
        kandidat = m.group(0)
        soll = IBAN_LAENGEN.get(kandidat[:2].upper())
        if soll is None:
            if _iban_pruefen(kandidat):
                ergebnisse.append(Stelle(m.start(), m.end(), 1.0))
                pos = m.end()
            else:
                pos = m.start() + 1
            continue
        ende = _iban_kuerzen(kandidat, soll)
        if ende is not None and _iban_pruefen(kandidat[:ende]):
            ergebnisse.append(Stelle(m.start(), m.start() + ende, 1.0))
            pos = m.start() + ende          # direkt dahinter weitersuchen (zweite IBAN!)
        elif ende is not None and _iban_form_stark(kandidat[:ende], text, m.start()):
            ergebnisse.append(Stelle(m.start(), m.start() + ende, 0.6, False, HINWEIS_PRUEFZIFFER))
            pos = m.start() + ende
        else:
            pos = m.start() + 1
    # OCR: Prüfziffern als Buchstaben gelesen ("DESG 9065 3989 …")
    belegt = [(s.start, s.ende) for s in ergebnisse]
    for m in _IBAN_OCR_RE.finditer(text):
        if any(a < m.end() and m.start() < b for a, b in belegt):
            continue
        kandidat = m.group(0)
        ende = _iban_kuerzen(kandidat, IBAN_LAENGEN[kandidat[:2].upper()])
        if ende is not None and _iban_form_stark(kandidat[:ende], text, m.start()):
            ergebnisse.append(Stelle(m.start(), m.start() + ende, 0.6, False, HINWEIS_PRUEFZIFFER))
    ergebnisse.sort()
    return ergebnisse


def finde_iban_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _iban_spannen) if s.streng]


def finde_iban(text):
    return [text[s:e] for s, e in finde_iban_stellen(text)]


# ----------------------------------------------------------------------
# E-Mail
# ----------------------------------------------------------------------
_EMAIL_RE = re.compile(
    r"(?<![\w.\-+%])[\w.\-+%]{1,64}"
    r"(?:@|[ \t]?[\(\[][ \t]?at[ \t]?[\)\]][ \t]?)"            # auch "(at)"-Schreibweise
    r"[\w\-]{1,63}(?:\.[\w\-]{1,63}){0,4}\.[A-Za-z]{2,24}(?![\wäöüß])",
    re.IGNORECASE)
# OCR: Leerzeichen um "@" oder Punkte ("ionescu854@gmx . de") – nur mit bekannter Endung
_EMAIL_OCR_RE = re.compile(
    r"(?<![\w.\-+%])[\w.\-+%]{1,64}[ \t]?@[ \t]?[\w\-]{1,63}(?:[ \t]?\.[ \t]?[\w\-]{1,63}){0,3}[ \t]?\.[ \t]?"
    r"(?:de|com|net|org|eu|at|ch|info|biz|io|nl|fr|it|es|pl|tr|uk|co|me|email|online|mail|be|lu|dk|se|no|fi|"
    r"cz|hu|ro|gr|ru|us)(?![\wäöüß])", re.IGNORECASE)


def _email_spannen(text: str) -> list:
    aus = [Stelle(m.start(), m.end()) for m in _EMAIL_RE.finditer(text)]
    if "@" in text:
        belegt = [(s.start, s.ende) for s in aus]
        for m in _EMAIL_OCR_RE.finditer(text):
            if (" " in m.group(0) or "\t" in m.group(0)) and not any(a < m.end() and m.start() < b
                                                                     for a, b in belegt):
                aus.append(Stelle(m.start(), m.end(), 0.85))
        aus.sort()
    return aus


def finde_email_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _email_spannen) if s.streng]


def finde_email(text):
    return [text[s:e] for s, e in finde_email_stellen(text)]


# ----------------------------------------------------------------------
# Telefon
# ----------------------------------------------------------------------
_TEL_RE = re.compile(
    r"(?<![\w\-/])"                                        # nicht mitten in Kennungen (DE98ZZZ09999999999)
    r"(?:\+49[ \t\-/.]?(?:\(0\)[ \t]?)?(?:\d{2,5}|\(\d{2,5}\))"   # +49 911 / +49 (0) 171 / +49 (911)
    r"|\+(?!49)[1-9]\d{0,2}[ \t\-/.]?(?:\(0\)[ \t]?)?\d{1,5}"    # +33 6 12 … / +43 1 … (Ausland)
    r"|\((?:0|O)\d{1,5}\)"                                 # (0911)
    r"|(?:0|O(?=\d))(?:\d{1,5}|[ \t]\d{2,3})(?:[ \t]\d{2,3})?)"   # 0911 / 0 89 / 09 11 / 0049 911
    r"[ \t]*(?:[/\-–][ \t]*)?"                             # Trenner
    r"\d{2,}(?:[ \t\-/–]\d{2,})*"                          # Ziffergruppen — kein Zeilenumbruch
    r"(?:[ \t]?-[ \t]?\d{1,3})?"                           # Durchwahl -0 / -12
    r"(?!\d)")
# Service-/Sonderrufnummern (0800, 0180x, 0900, 0137/0138, 0190) gehören dem Unternehmen, nicht der Person
_TEL_SERVICE_RE = re.compile(r"^(?:\+49|0049|0)(?:800|180|900|137|138|190)\d")
_TEL_DATUM_RE = re.compile(r"^\d{1,2}[/.]\d{1,2}[/.](?:19|20)\d{2}$")
# Telefon hinter einem Etikett/Satz: Ziffergruppen auch über EINEN Zeilenumbruch und mit OCR-Punkten
_TEL_KONTEXT_RE = re.compile(
    r"(?i:(?<![\wäöüß])(?:tel(?:efon)?(?:nummer|nr)?|fon|mobil(?:nummer|funk)?|handy(?:nummer)?|fax|telefax|"
    r"rufnummer|rückrufnummer|erreichbar[ \t]+unter|erreichen[ \t]+sie[ \t]+(?:mich|uns|ihn|sie)[ \t]+unter|"
    r"(?:mich|uns)[ \t]+unter|unter[ \t]+der[ \t]+nummer|whatsapp|unter))\.?[ \t]*:?[ \t]*")
_TEL_LOSE_RE = re.compile(
    r"(?:\+\d{2,3}[ \t.\-/]{0,2}(?:\n[ \t]*)?(?:\(0\)[ \t]?)?|\(0\d{1,5}\)[ \t]?|0(?=[\d \n]))"
    r"(?:[\d \t./\-–()]|\n(?=[ \t]*[\d(])){2,40}")


# hinter dem Zeilenumbruch: Aufzählung ("6. Unfallhergang") oder Betrag ("45,90 EUR") statt Rest der Nummer
_AUFZAEHLUNG_DANACH_RE = re.compile(r"[.)][ \t]+[A-Za-zÄÖÜäöü]|,\d{1,2}(?!\d)")


def _ziffern(text: str) -> int:
    return sum(c.isdigit() for c in text) + text.count("O")


def _tel_gueltig(treffer: str) -> bool:
    if not 8 <= _ziffern(treffer) <= 15 or _TEL_DATUM_RE.match(treffer.replace("O", "0")):
        return False                                   # auch "O1/08/1966" (OCR: O statt 0) ist ein Datum
    return not _TEL_SERVICE_RE.match(re.sub(r"[ \t\-/–().\n]", "", treffer))


def _telefon_spannen(text: str) -> list:
    aus = []
    for m in _TEL_RE.finditer(text):
        if _tel_gueltig(m.group(0)):
            aus.append(Stelle(m.start(), m.end()))
    # hinter einem Etikett ("Tel.", "Mobil", "erreichen Sie mich unter"): auch über einen Umbruch
    belegt = [(s.start, s.ende) for s in aus]
    for k in _TEL_KONTEXT_RE.finditer(text):
        m = _TEL_LOSE_RE.match(text, k.end())
        if not m:
            continue
        roh = m.group(0)
        while roh and not roh[-1].isdigit():
            roh = roh[:-1]                                   # bis zur letzten Ziffer
        if "\n" in roh:
            # über den Umbruch nur echte Zifferngruppen, keine Aufzählung der Folgezeile ("6. Unfallhergang")
            vor, _, nach = roh.partition("\n")
            ende_nach = m.start() + len(roh)
            einzeln = re.fullmatch(r"[ \t]*\d{1,3}", nach) is not None      # nur EINE kurze Zahl in der Folgezeile
            if sum(c.isdigit() for c in nach) < 2 or (einzeln and _AUFZAEHLUNG_DANACH_RE.match(text, ende_nach)):
                roh = vor.rstrip(" \t./-–(")
                while roh and not roh[-1].isdigit():
                    roh = roh[:-1]
        s, e = m.start(), m.start() + len(roh)
        if roh.count("(") != roh.count(")") or roh.count("\n") > 1:
            continue
        if any(a <= s < b or a < e <= b for a, b in belegt):
            # vorhandenen Treffer über den Umbruch verlängern ("+49 (0)1511⏎6539102")
            for i, (a, b) in enumerate(belegt):
                if a <= s < b and e > b and _tel_gueltig(roh):
                    aus = [x for x in aus if (x.start, x.ende) != (a, b)]
                    aus.append(Stelle(s, e, 0.75))
                    belegt[i] = (s, e)
            continue
        if _tel_gueltig(roh):
            aus.append(Stelle(s, e, 0.7))
            belegt.append((s, e))
    aus.sort()
    return aus


def finde_telefon_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _telefon_spannen) if s.streng]


def finde_telefon(text):
    """Deutsche Schreibweisen: 0911 / 123 45 67, (0911) 123456, +49 (0) 171 2345678,
    0171-2345678, 0 89 / 12 34 56 78 … sowie Auslandsnummern mit +Vorwahl (Gutachten EQ-08).
    Mindestens 8, höchstens 15 Ziffern. Keine Service-Hotlines (0800 …, EQ-07), keine Datumsangaben
    (02/09/1983, EQ-14) und keine Ziffernfolgen mitten in Kennungen (DE98ZZZ0999…, EQ-06). Hinter einem
    Etikett ("Tel.", "Mobil", "erreichen Sie mich unter") darf die Nummer über einen Zeilenumbruch laufen."""
    return [text[s:e] for s, e in finde_telefon_stellen(text)]


# ----------------------------------------------------------------------
# Geburtsdatum
# ----------------------------------------------------------------------
_MONATE = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "mär": 3, "mrz": 3,
    "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8,
    "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10, "november": 11,
    "nov": 11, "dezember": 12, "dez": 12,
}
_MONAT_RE = "(?:" + "|".join(sorted((re.escape(m) for m in _MONATE), key=len, reverse=True)) + r")\.?"

_DATUM_RE = re.compile(
    r"(?<!\d)(?:"
    r"\d{1,2}\.[ \t]?\d{1,2}\.[ \t]?(?:19|20)?\d{2}"                 # 02.09.1983 / 2.9.83
    # 2. September 1983, auch über einen Umbruch: "27." ⏎ "Januar 1976"
    r"|\d{1,2}\.(?:[ \t]?|[ \t]*\n[ \t]*)" + _MONAT_RE + r"[ \t]?(?:19|20)\d{2}"
    r"|(?:19|20)\d{2}-\d{2}-\d{2}"                                    # 1983-09-02
    r"|\d{1,2}/\d{1,2}/(?:19|20)\d{2}"                                # 02/09/1983
    r")(?!\d)", re.IGNORECASE)

# Stichwörter groß/klein egal (Gutachten EQ-05: "Geboren am:", "GEBOREN", "GEB.-DATUM"); "geb" ohne Punkt
# nur klein vor Leerzeichen ("geb 02.09.1983"), damit "Geb" am Satzanfang nicht stört
_GEB_STICHWORT_RE = re.compile(
    r"(?<![\wäöüßÄÖÜ])(?:(?i:geb\.-?dat(?:um|\.)?|geburts-?[ \t]?datum|geb\.|geboren|geburtsdatum|geburtsdaten|"
    r"geburtstag|date[ \t]of[ \t]birth|né(?:e)?[ \t]le|nat[oa][ \t]il)"
    r"|geb(?=[ \t]))(?![\wäöüß])"
    r"|\*(?=[ \t]?\d)")
# Vertragsvokabular zwischen Stichwort und Datum -> kein Geburtsdatum
_GEB_STOPP_ZEILE_RE = re.compile(
    r"(?<![\wäöüß])(?:vom|ab|zum|seit|bis|am Ende)(?![\wäöüß])"
    r"|(?i:beginn|ablauf|fällig|gültig|kündig|datum|stand(?![\wäöüß])|rechnung|angebot|zahlung)")
_GEB_STOPP_FOLGE_RE = re.compile(
    r"(?<![\wäöüß])(?:vom|ab|zum|seit|bis|Beginn|Ablauf|Stand|Datum|fällig|gültig|Fälligkeit)(?![\wäöüß])")
# Jahrgang ("Jg. 1961", "Jahrgang 1961", "geb. 1961")
_JAHRGANG_RE = re.compile(
    r"(?<![\wäöüß])(?:(?i:jg\.|jahrgang|geb\.|geboren)[ \t]*(?:im[ \t]+jahr[ \t]+|in[ \t]+)?)"
    r"((?:19|20)\d{2})(?![\d/\-]|[.,]\d)")


def _datum_zerlegen(datum: str):
    """Liefert (Tag, Monat, Jahr) oder None."""
    d = datum.strip()
    m = re.fullmatch(r"(\d{1,2})\.[ \t]?(\d{1,2})\.[ \t]?(\d{2,4})", d)
    if m:
        t, mo, j = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{1,2})\.[ \t]*\n?[ \t]*([A-Za-zäöüÄÖÜ]+)\.?[ \t]?(\d{4})", d)
        if m:
            mo = _MONATE.get(m.group(2).lower())
            if mo is None:
                return None
            t, j = int(m.group(1)), int(m.group(3))
        else:
            m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", d)
            if m:
                j, mo, t = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", d)
                if not m:
                    return None
                t, mo, j = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if j < 100:
        j += 1900 if j > _heute().year % 100 else 2000
    return t, mo, j


def _geburtsdatum_plausibel(datum: str) -> bool:
    """Gültiges Datum, Jahr zwischen heute-110 und heute."""
    teile = _datum_zerlegen(datum)
    if not teile:
        return False
    t, mo, j = teile
    heute = _heute()
    if not (1 <= t <= 31 and 1 <= mo <= 12 and heute.year - 110 <= j <= heute.year):
        return False
    try:
        return datetime.date(j, mo, t) <= heute
    except ValueError:
        return False


def geburtsdatum_plausibel(datum: str) -> bool:
    """Öffentlich für Detektoren: gültiges Datum mit einem Jahr zwischen heute-110 und heute."""
    return _geburtsdatum_plausibel(datum)


_SPALTENKOPF_GEB_RE = re.compile(r"(?<![\wäöüß])(?:Geburtsdatum|Geb\.-?Dat\.?|Geb\.-?Datum)(?![\wäöüß])")


def _geburtsdaten_spalten(text):
    """Tabellenlayout: 'Geburtsdatum' als Spaltenkopf, Werte in den Folgezeilen in derselben Spalte
    (z. B. Versicherungsschein mit Personentabelle). Liefert Stellen."""
    ergebnisse = []
    if not _SPALTENKOPF_GEB_RE.search(text):
        return ergebnisse
    zeilen = text.split("\n")
    offsets, pos = [], 0
    for z in zeilen:
        offsets.append(pos)
        pos += len(z) + 1
    for i, zeile in enumerate(zeilen):
        for m in _SPALTENKOPF_GEB_RE.finditer(zeile):
            if _DATUM_RE.search(zeile, m.end()):
                continue                      # Wert steht in derselben Zeile -> Fenster-Regel
            spalte = m.start()
            leer = 0
            for j in range(i + 1, min(i + 60, len(zeilen))):
                folge = zeilen[j]
                if not folge.strip():
                    leer += 1
                    if leer > 1:
                        break
                    continue
                daten = [(d.start(), d.end()) for d in _DATUM_RE.finditer(folge)]
                if not daten:
                    break
                start, ende = min(daten, key=lambda p: abs(p[0] - spalte))
                if abs(start - spalte) > 12:
                    break
                if _geburtsdatum_plausibel(folge[start:ende]):
                    ergebnisse.append(Stelle(offsets[j] + start, offsets[j] + ende))
    return ergebnisse


def _geburt_spannen(text: str) -> list:
    ergebnisse = []
    for m in _GEB_STICHWORT_RE.finditer(text):
        if m.group(0) == "*":
            davor = text[:m.start()].rstrip()
            if davor and davor[-1].isdigit():
                continue                      # "5 * 14.03.2025" ist eine Multiplikation
        fenster = text[m.end():m.end() + 100]
        d = _DATUM_RE.search(fenster)
        if not d:
            continue
        zwischen = fenster[:d.start()]
        if len(zwischen) > 80 or any(c.isdigit() for c in zwischen):
            continue
        gleiche_zeile, _, folgezeilen = zwischen.partition("\n")
        if _GEB_STOPP_ZEILE_RE.search(gleiche_zeile) or _GEB_STOPP_FOLGE_RE.search(folgezeilen):
            continue
        if _geburtsdatum_plausibel(d.group(0)):
            ergebnisse.append(Stelle(m.end() + d.start(), m.end() + d.end()))
    for m in _JAHRGANG_RE.finditer(text):
        jahr = int(m.group(1))
        if _heute().year - 110 <= jahr <= _heute().year and not _DATUM_RE.match(text, m.start(1)):
            ergebnisse.append(Stelle(m.start(1), m.end(1), 0.7))
    ergebnisse.extend(_geburtsdaten_spalten(text))
    ergebnisse.sort()
    return ergebnisse


def finde_geburtsdaten_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _geburt_spannen) if s.streng]


def finde_geburtsdaten(text):
    """Datumsangaben bei 'geb.', 'geboren', 'Geburtsdatum', '*' … (groß/klein egal) in einem Fenster von
    bis zu 80 Zeichen (auch über Zeilenumbrüche, z. B. Formularlayouts), Jahrgänge ('Jg. 1961'), außerdem
    Tabellenspalten unter einem Spaltenkopf 'Geburtsdatum'. Formate TT.MM.JJJJ, T.M.JJ, TT/MM/JJJJ,
    JJJJ-MM-TT, 'T. Monat JJJJ'. Datumsangaben hinter Vertragsvokabular (vom, ab, seit, Beginn, Ablauf …)
    werden nicht als Geburtsdatum gewertet."""
    return _eindeutig([text[s:e] for s, e in finde_geburtsdaten_stellen(text)])


_ALLE_DATEN_RE = re.compile(r"\b\d{1,2}\.\s?\d{1,2}\.\s?(?:19|20)\d{2}\b")


def _datum_spannen(text: str) -> list:
    return [Stelle(m.start(), m.end()) for m in _ALLE_DATEN_RE.finditer(text)]


def finde_alle_daten_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _datum_spannen)]


def finde_alle_daten(text):
    """Optional: ALLE Datumsangaben (Vorsicht — auch Vertragsdaten!)."""
    return [text[s:e] for s, e in finde_alle_daten_stellen(text)]


# ----------------------------------------------------------------------
# Straße + Hausnummer
# ----------------------------------------------------------------------
def _gross_und_versal(woerter) -> str:
    """Alternation aus Wörtern in der angegebenen Schreibweise und in Versalien ("Am|AM")."""
    alle = []
    for w in woerter:
        for v in (w, w.upper()):
            if v not in alle:
                alle.append(v)
    return "(?:" + "|".join(sorted((re.escape(v).replace(r"\ ", r"(?:[ \t]+|[ \t]*\n[ \t]*)") for v in alle),
                                   key=len, reverse=True)) + ")"


_WORT = r"[A-ZÄÖÜ][\wäöüß]{0,40}(?:\.?-[\wäöüßA-ZÄÖÜ]{1,40}){0,4}\.?"
_SUFFIX_WORT = (r"(?i:Straße|Strasse|Str\.?|Weg|Platz|Allee|Ring|Gasse|Damm|Ufer|Chaussee|"
                r"Promenade|Markt|Steig|Pfad|Stieg)(?![A-Za-zäöüßÄÖÜ])")
_SUFFIX_ANGEHAENGT = (r"(?i:straße|strasse|str\.|str(?![\wäöüß])|weg|platz|gasse|allee|ring|damm|"
                      r"ufer|hof|steig|pfad|chaussee|promenade|markt|stieg)(?![A-Za-zäöüßÄÖÜ])")
_PRAEPOSITION = _gross_und_versal([
    "Am", "An der", "An dem", "An den", "Im", "In der", "In den", "In dem", "Auf dem", "Auf der", "Auf den",
    "Unter den", "Unter der", "Unter dem", "Hinter dem", "Hinter der", "Hinter den", "Zum", "Zur", "Zu den",
    "Bei der", "Bei den", "Beim", "Vor dem", "Vor der", "Vor den", "Über den", "Über dem", "Über der",
    "Neben der", "Neben dem", "Ober der", "Unterm", "Hinterm", "Vorm", "Auf'm", "Am Alten", "Zum Alten"])
# Adjektive vor Straßennamen ("Kleine Bergstraße 16", "Untere Grabenstraße 54", "Obere Hauptstr. 38d")
_STRASSEN_ADJEKTIV = _gross_und_versal([
    "Kleine", "Große", "Grosse", "Lange", "Alte", "Neue", "Obere", "Untere", "Hohe", "Breite", "Hintere",
    "Vordere", "Innere", "Äußere", "Mittlere", "Schöne", "Krumme", "Kurze", "Schmale", "Weiße", "Rote",
    "Grüne", "Schwarze", "Kleiner", "Großer", "Alter", "Neuer", "Oberer", "Unterer", "Hoher", "Langer",
    "Am", "An der", "Auf der", "Im"])
_KEIN_STRASSENWORT = (r"(?!(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|"
                      r"Dezember|Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag|Jahr|Jahre|"
                      r"Jahren|Monat|Monate|Monaten|Tag|Tage|Tagen|Woche|Wochen|Fall|Falle|Schadenfall|"
                      r"Leistungsfall|Todesfall|Versicherungsfall|Rahmen|Übrigen|Beispiel|Wesentlichen|"
                      r"Zeitraum|Durchschnitt|Vergleich|Ergebnis|Alter|Anhang|Anschluss|Auftrag|Namen|"
                      r"Sinne|Zweifel|Laufe|Wert|Betrag|Beitrag|Zeitpunkt|Umfang|Falle|Voraus|"
                      r"Zuge|Hinblick|Gegensatz|Vordergrund|Folgenden|Weiteren|Übrigen|Regelfall|"
                      r"Einzelfall|Zusammenhang|Vertrag|Tarif|Antrag|Abschnitt|Absatz|Punkt|Kapitel|"
                      r"Ende|Anfang|Moment|Augenblick|Schnitt|Minimum|Maximum|Grunde|Rest|Ganzen|"
                      r"Einzelnen|Allgemeinen|Besonderen|Nachgang|Vorfeld)(?![\wäöüß]))")
_KEINE_EINHEIT = (r"(?![ \t]*(?:Uhr|Jahre?n?|Monate?n?|Tage?n?|Wochen?|Prozent|%|EUR|Euro|€|km|Stunden?|"
                  r"Minuten?|Personen|Kinder|mal|Mio|Mrd|Stück|Jahres|Fahrzeuge|Punkte|Seiten?|Mitarbeiter|"
                  r"Prämien?|Raten?)(?![\wäöüß]))")
_HAUSNUMMER = (r"[ \t]*\d{1,4}(?:[ \t]?[a-hA-H](?![\wäöüß]))?"
               r"(?:[ \t]?[-–/][ \t]?\d{1,4}(?:[ \t]?[a-h](?![\wäöüß]))?)?(?![\wäöüß])")
_ARTIKEL_NAME = r"(?:der|des|am|an[ \t]+der|im|vom|zum|zur|vor[ \t]+dem|DER|DES|AM)"

_STRASSE_RE = re.compile(
    r"(?<![\wäöüß])(?:"
    # Am Bahnhof 3, Unter den Linden 1, An der Alten Mühle 4, ZUM STEINBRUCH 66, An den Eichen 140
    + _PRAEPOSITION + r"[ \t]+" + _KEIN_STRASSENWORT + _WORT + r"(?:[ \t]+" + _WORT + r"){0,2}"
    r"[ \t]+\d{1,3}(?![\d])(?:[ \t]?[a-hA-H](?![\wäöüß]))?" + _KEINE_EINHEIT +
    # Berliner Straße 5, Fürther Str. 120, Berliner Platz 1
    r"|" + _WORT + r"(?:[ \t]+" + _WORT + r")?[ \t]+" + _SUFFIX_WORT + _HAUSNUMMER +
    # Hauptstraße 12a, Von-der-Tann-Str. 3, Schillerstr.12, HAUPTSTRASSE 12, Kleine Bergstraße 16
    r"|(?:" + _STRASSEN_ADJEKTIV + r"[ \t]+)?[A-ZÄÖÜ][\wäöüß\-.]{0,60}?" + _SUFFIX_ANGEHAENGT + _HAUSNUMMER +
    # Platz der Republik 99 a, Straße der Einheit 5, Allee der Kosmonauten 12
    r"|(?:Platz|Straße|Strasse|Allee|Weg|Ring|Damm|Ufer|Markt|Chaussee|Promenade|Gasse|Steig|Pfad|Garten|Park)"
    r"[ \t]+" + _ARTIKEL_NAME + r"[ \t]+" + _WORT + r"(?:[ \t]+" + _WORT + r")?" + _HAUSNUMMER + _KEINE_EINHEIT +
    # Straße des 17. Juni 135
    r"|Straße des \d{1,2}\. [A-ZÄÖÜ][a-zäöü]+[ \t]+\d{1,4}(?![\wäöüß])"
    # Alt-Moabit 61, Alt-Tegel 3
    r"|Alt-[A-ZÄÖÜ][\wäöüß]{2,30}(?:-[A-ZÄÖÜ][\wäöüß]{1,30})?" + _HAUSNUMMER +
    # Postfach 10 11 12
    r"|Postfach[ \t]*\d{1,3}(?:[ \t]?\d{2,4}){0,3}(?!\d)"
    r")")
# "befuhr die Bundesstraße 7": Fahrbahn-Angabe mit Artikel davor, keine Anschrift (Gutachten EQ-12)
_FAHRBAHN_RE = re.compile(r"^(?:Bundes|Landes|Land|Kreis|Staats)stra(?:ß|ss)e[ \t]*\d{1,4}$")
_FAHRBAHN_DAVOR_RE = re.compile(r"(?:der|die|den|auf|über)[ \t]+$")


def _strasse_spannen(text: str) -> list:
    aus = []
    for m in _STRASSE_RE.finditer(text):
        if _FAHRBAHN_RE.match(m.group(0)) and _FAHRBAHN_DAVOR_RE.search(text[max(0, m.start() - 6):m.start()]):
            continue
        aus.append(Stelle(m.start(), m.end()))
    return aus


def finde_strasse_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _strasse_spannen) if s.streng]


def finde_strasse(text):
    return [text[s:e] for s, e in finde_strasse_stellen(text)]


# ----------------------------------------------------------------------
# PLZ + Ort
# ----------------------------------------------------------------------
_ORT_STOPP = (r"(?!(?:Tel|Telefon|Telefax|Fax|Mobil|Handy|E-Mail|Mail|Internet|Web|Deutschland|Germany|"
              r"Datum|Den|Am|Im|Vers|Versicherung|Versicherungen|Versicherungsnehmer|Versicherungsschein|"
              r"Versicherungsnummer|Herr|Herrn|Frau|Firma|Seite|Postfach|Euro|EUR|EURO|USD|CHF|Kilometer|Stück|"
              r"Prozent|Punkte|Meter|Liter|Jahre|Monate|Tage|Personen|Beginn|Nr|Sehr|Ihr|Ihre|Ihren|Ihrem|Ihrer|"
              r"Wir|Sie|Die|Der|Das|Dem|Des|Ein|Eine|Einen|Einem|Einer|Bitte|Mit|Vielen|Betreff|Betrifft|Sitz|"
              r"Gesamt|Summe|Zahlung|Zahlbar|Kontonummer|Konto|BLZ|IBAN|BIC|Vertrag|Kunden|Kunde|Antrag|"
              r"Rechnung|Vom|Bis|Ab|Zum|Zur|Und|Oder|Für|Bei|Von|Nach|Über|Unter|Zwischen|Beitrag|Stand|"
              r"Vertragsnummer|Kundennummer|Schaden|Leistung|Deckung|Fahrleistung|Laufzeit|Tarif|Police|"
              r"Angebot|Kennzeichen|Baujahr|Erstzulassung|Punkten|Teilnehmer|Mitarbeiter|Kinder|Zeichen|"
              r"Minuten|Stunden|Sekunden|Mio|Mrd|Tsd|Dollar|Franken|Pfund|Prämie|Zinsen|Monat|Jahr|Tag|"
              r"Uhr|Mal|Wert|Wohnfläche|Quadratmeter|Qm|Einwohner|Haushalte|Fahrzeuge|Verträge|Kunden|"
              r"Schäden|Fälle|Stunde|Minute|Zeilen|Seiten|Blatt|Exemplare|Ausfertigungen|Bytes|Kb|Mb|Gb|"
              r"Vorstand|Vorstände|Vorsitz|Vorsitzender|Vorsitzende|Aufsichtsrat|Aufsichtsratsvorsitzender|"
              r"Aufsichtsratsvorsitzende|Geschäftsführer|Geschäftsführerin|Geschäftsführung|Registergericht|"
              r"Amtsgericht|Handelsregister|HRB|HRA|USt|UStId|USt-IdNr|Steuernummer|Gläubiger|Bankverbindung|"
              r"Ust-IdNr|Umsatzsteuer|Finanzamt|Bank|Sparkasse)"
              r"(?![\wäöüß]))"
              r"(?![\wäöüß]{0,40}(?i:straße|strasse|str\.|weg|allee|gasse)(?![\wäöüß]))")
# Leerraum innerhalb einer Zelle: Leerzeichen und einzelne Tabulatoren, nie der Spaltentrenner "\t\t" des
# Seitenmodells (PLZ und Ort in Nachbarzellen gehören nicht zusammen, ein Ort läuft nicht in die Nachbarspalte)
_IN_ZELLE = r"(?:[ ]|\t(?!\t))"
_ORT_WORT = (r"(?:[A-ZÄÖÜ][a-zäöü]{1,2}\.|[A-ZÄÖÜ][\wäöüß]{1,30}(?:-[\wäöüßA-ZÄÖÜ]{1,30}){0,3}"
             r"|\([A-ZÄÖÜ][\wäöüß]{1,30}\)"
             r"|(?:[aivb]\.[ ]?d\.[ ]?)[A-ZÄÖÜ][\wäöüß]{1,30}\.?"
             r"|(?:am|an der|in der|bei|im|ob der|a\.[ ]?d\.|v\.[ ]?d\.|i\.[ ]?d\.|b\.|an)" + _IN_ZELLE
             + r"+[A-ZÄÖÜ][\wäöüß]{1,30})")
_PLZ_ORT_RE = re.compile(
    r"(?<![\d\-/,])"
    r"(?:(?:D|DE)[-\s]?(?!00)\d{5}|(?:A|CH|L|FL)[-\s]\d{4}|(?!00)\d{5})(?!\d)"
    r"(?:" + _IN_ZELLE + "+|" + _IN_ZELLE + r"*\n" + _IN_ZELLE + "*)"      # höchstens EIN Zeilenumbruch
    + _ORT_STOPP + _ORT_WORT + r"(?:" + _IN_ZELLE + "+" + _ORT_STOPP + _ORT_WORT + r"){0,3}(?![\wäöüß])")
_PLZ_ETIKETT_DAVOR_RE = re.compile(
    r"(?i:nr\.?|nummer|summe|betrag|wert|eur|€|euro|leistung|deckung|beitrag|fahrleistung|vertrag|"
    r"kunden|konto|zeichen|ref\.?|referenz|position|pos\.?|artikel|menge|anzahl|seite|blatt|"
    r"kennung|id|code|schlüssel|key|hrb|hra|gnr|vr|pr|registergericht|amtsgericht|handelsregister|"
    r"register|blz|bankleitzahl|steuer-?nr\.?|ust-?id(?:nr)?\.?)[ \t:.]*$")
# PLZ und Ort in zwei Nachbarzellen ("53285 ⇥⇥ Bonn": Tabelle mit Spalten PLZ | Ort, Formular mit Kästchen, breite
# OCR-Lücke): EINE Stelle über genau diesen einen Spaltentrenner – nur, wenn die PLZ-Zelle nur die PLZ und die
# Ort-Zelle nur den Ort enthält (Nachbarzellen wie "Kfz", "Spreewald" nimmt sie nie mit; die Schwärzung zeichnet je
# Zelle ein eigenes Rechteck)
_PLZ_ZELLE_ORT_RE = re.compile(
    r"(?:^|(?<=\t\t)|(?<=\n))[ ]*((?:(?:D|DE)[-\s]?)?(?!00)\d{5})[ ]*\t\t[ ]*"
    r"(" + _ORT_STOPP + _ORT_WORT + r"(?:" + _IN_ZELLE + "+" + _ORT_STOPP + _ORT_WORT + r"){0,3})(?![\wäöüß])"
    r"(?=[ ]*(?:\t\t|\n|$|,))")
# Registernummer statt PLZ: hinter HRB/HRA, Amtsgericht, Registergericht oder Handelsregister – auch mit dem Ort
# des Gerichts dazwischen ("Amtsgericht Frankfurt am Main 12345", "Registergericht: Amtsgericht Lübeck, 45650",
# OCR "HR B 16963", "HR8 16963") und über das Zeilenende ("… HRB" ⏎ "16963 …")
_PLZ_REGISTER_DAVOR_RE = re.compile(
    r"(?<![\wäöüß])(?i:HR[ ]?[AB8]|HRA|HRB|GnR|Amtsgericht|Registergericht|Handelsregister|Registerg\.)"
    r"(?:[ \t:.,/]+(?:[A-ZÄÖÜ][\wäöüß.\-]*|am|an|der|dem|im|in|i\.|a\.|d\.|v\.|b\.|HRA|HRB|Nr\.?)){0,5}"
    r"[ \t:.,/]*$")
_ORT_DATUM_DANACH_RE = re.compile(r"^[ \t]*,?[ \t]*(?:den[ \t]+|im[ \t]+|am[ \t]+)?\d{1,2}\.")
# OCR-Reste hinter dem Ort ("81675 München Bu", "95632 Wunsiedel Beer"): ein letztes kurzes Wort, das kein
# Ortsteil sein kann, wird abgeschnitten
_ORT_REST_RE = re.compile(r"[ \t]+[A-ZÄÖÜ][a-zäöü]{0,3}$")
# Weitere Wörter eines Ortsnamens. Ein Ort hat nur dann mehrere Wörter, wenn das erste ein Vorsatz ist
# ("Bad Homburg", "St. Ingbert", "Bergisch Gladbach", "Neu Wulmstorf"), ein Verbinder folgt ("am Main",
# "an der Havel", "v. d. Höhe", "i.d.OPf."), ein Zusatz in Klammern ("Halle (Saale)") oder ein Fluss/eine
# Landschaft ("Frankfurt Main"). Sonst gehört das nächste Wort nicht mehr zum Ort: eine per OCR zu einer
# Zeile verschmolzene Tabellenzeile "26122 Oldenburg Unfall Weserbergland" oder "03046 Cottbus BU R+V"
# darf Nachbarzellen nicht mitnehmen (sie würden an jeder Fundstelle mitgeschwärzt).
_ORT_VORSATZ = frozenset({
    "bad", "sankt", "neu", "alt", "groß", "gross", "klein", "hohen", "nieder", "ober", "unter", "mittel",
    "königs", "koenigs", "lutherstadt", "hansestadt", "ostseebad", "nordseebad", "seebad", "kurort", "markt",
    "schloß", "schloss", "stadt"})
_ORT_VERBINDER = frozenset({"am", "an", "der", "im", "in", "bei", "ob", "b.", "a.", "v.", "i.", "d.", "a.d.",
                            "v.d.", "i.d.", "ot", "ortsteil"})
_ORT_ZUSATZ = frozenset({
    "main", "oder", "saale", "havel", "lech", "neckar", "breisgau", "taunus", "pegnitz", "allgäu", "westerwald",
    "holstein", "ruhr", "rhein", "donau", "isar", "inn", "mosel", "lahn", "fulda", "weser", "elbe", "ems",
    "spree", "harz", "eifel", "hunsrück", "vogtland", "erzgebirge", "schwarzwald", "odenwald", "spessart",
    "rhön", "oberpfalz", "opf", "opf.", "ostfriesland", "dithmarschen", "uckermark", "altmark", "prignitz",
    "lausitz", "müritz", "weinstraße", "tauber", "aisch", "saar", "sieg", "lippe", "wupper", "nahe", "dill",
    "kinzig", "murg", "rems", "fils", "iller", "altmühl", "vils", "rott", "salzach", "ilm", "werra", "unstrut",
    "elster", "mulde", "neiße", "peene", "trave", "eider", "aller", "leine", "oker", "hunte", "hase", "vechte",
    "sachsen", "thüringen", "bayern", "hessen", "westfalen", "pfalz", "oldb", "oldb.", "württ", "württ.",
    "baden", "brsg", "brsg.", "obb", "obb.", "ndb", "ndb.", "ofr", "ofr.", "ufr", "ufr.", "mfr", "mfr."})


def _ort_wortzahl(woerter: list) -> int:
    """Wie viele der Wörter hinter der PLZ zum Ortsnamen gehören (mindestens das erste)."""
    anzahl = 1
    verbinder = False
    for i in range(1, len(woerter)):
        wort = woerter[i]
        k = wort.casefold()
        vorher = woerter[i - 1].casefold()
        if k in _ORT_VERBINDER:
            verbinder = True
            anzahl = i + 1
            continue
        if (verbinder or re.match(r"[aivb]\.d\.", k) or wort.startswith("(") or k.strip("().") in _ORT_ZUSATZ
                or vorher in _ORT_VORSATZ or vorher.endswith("isch")
                or re.fullmatch(r"[a-zäöü]{1,4}\.", vorher)):
            verbinder = False
            anzahl = i + 1
            continue
        break
    while anzahl > 1 and woerter[anzahl - 1].casefold() in _ORT_VERBINDER:
        anzahl -= 1                               # Verbinder ohne Ort dahinter gehört nicht dazu
    return anzahl


def _plz_davor_ausgeschlossen(text: str, s: int) -> bool:
    """Steht vor der Zahl an `s` ein Etikett (Nr., Betrag, Konto …) oder eine Registerangabe (HRB, Amtsgericht …)
    – auch am Ende der Zeile davor, wenn die Zahl eine Zeile beginnt? Dann ist sie keine PLZ."""
    if s > 0 and text[s - 1] == "." and text[max(0, s - 3):s] != "...":
        return True                                     # "1.23456 Name" – aber Füllpunkte "....45879 Ort" ja
    davor = text[max(0, s - 40):s].rsplit("\n", 1)[-1]
    if _PLZ_ETIKETT_DAVOR_RE.search(davor) or _PLZ_REGISTER_DAVOR_RE.search(text[max(0, s - 60):s].rsplit(
            "\n", 1)[-1]):
        return True
    if not davor.strip() and s > 0:
        # PLZ am Zeilenanfang: Registerangabe am Ende der Zeile davor ("Amtsgericht Freiburg HRB" ⏎ "16963 …")
        vorige = text[max(0, s - 80):s].rstrip(" \t")
        if vorige.endswith("\n") and _PLZ_REGISTER_DAVOR_RE.search(vorige[:-1].rsplit("\n", 1)[-1]):
            return True
    return False


def _plz_ort_spannen(text: str) -> list:
    ergebnisse = []
    for m in _PLZ_ORT_RE.finditer(text):
        s, e = m.start(), m.end()
        if _plz_davor_ausgeschlossen(text, s):
            continue
        treffer = m.group(0)
        if "\n" in treffer:
            # Umbruch zwischen PLZ und Ort: Folgezeile darf keine Ort-Datum-Zeile sein
            if _ORT_DATUM_DANACH_RE.match(text[e:e + 30]):
                continue
        plz = re.match(r"\S+(?:\s+\d{4,5}(?!\S))?[ \t]*\n?[ \t]*", treffer) if treffer[:1].isalpha() else \
            re.match(r"\d+[ \t]*\n?[ \t]*", treffer)
        if plz:
            woerter = list(re.finditer(r"\S+", treffer[plz.end():]))
            anzahl = _ort_wortzahl([w.group(0) for w in woerter])
            if 0 < anzahl < len(woerter):
                e = s + plz.end() + woerter[anzahl - 1].end()
                treffer = text[s:e]
        rest = _ORT_REST_RE.search(treffer)
        if rest and len(treffer.split()) >= 3 and rest.group(0).strip() not in ("Bad", "St", "Neu", "Alt"):
            wort = rest.group(0).strip()
            if len(wort) <= 3 and not text[e:e + 1] in ("-", "."):
                e = s + rest.start()
        ergebnisse.append(Stelle(s, e))
    if "\t\t" in text:
        # PLZ-Zelle und Ort-Zelle nebeneinander: eine Stelle über genau den Trenner dazwischen
        belegt = [(st.start, st.ende) for st in ergebnisse]
        for m in _PLZ_ZELLE_ORT_RE.finditer(text):
            s = m.start(1)
            if any(a < m.end(2) and s < b for a, b in belegt) or _plz_davor_ausgeschlossen(text, s):
                continue
            woerter = list(re.finditer(r"\S+", m.group(2)))
            anzahl = _ort_wortzahl([w.group(0) for w in woerter])
            if anzahl < len(woerter):
                continue                                # die Zelle enthält mehr als einen Ort ("Mateusz Grabowski")
            ergebnisse.append(Stelle(s, m.start(2) + woerter[anzahl - 1].end(), 0.7))
        ergebnisse.sort()
    return ergebnisse


def plz_ort_zellenpaar(text: str, start: int, ende: int) -> bool:
    """Ist text[start:ende] eine PLZ-Zelle mit der ganzen Ort-Zelle daneben ("53285 ⇥⇥ Bonn")? Dann ist ihr
    Spaltentrenner der einzige erlaubte: PLZ + Ort reicht sonst nie über einen Spaltentrenner."""
    m = _ZELLENPAAR_RE.fullmatch(text, start, ende)
    if m is None:
        return False
    zeilenanfang = text.rfind("\n", 0, start) + 1
    zelle = text.rfind("\t\t", zeilenanfang, start)
    if text[(zelle + 2 if zelle >= 0 else zeilenanfang):start].strip(" "):
        return False                                    # vor der PLZ steht etwas in ihrer Zelle
    if not _ZELLENENDE_RE.match(text, ende):
        return False                                    # die Ort-Zelle geht weiter ("73610 ⇥⇥ Mateusz Grabowski")
    woerter = m.group(2).split()
    return _ort_wortzahl(woerter) == len(woerter)


_ZELLENPAAR_RE = re.compile(r"((?:(?:D|DE)[-\s]?)?\d{5})[ ]*\t\t[ ]*([^\t\n]+)")
_ZELLENENDE_RE = re.compile(r"[ ]*(?:\t\t|\n|,|$)")


def finde_plz_ort_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _plz_ort_spannen) if s.streng]


def finde_plz_ort(text):
    """PLZ + Ort, auch mehrteilig (Frankfurt am Main, Bad Homburg v. d. Höhe, St. Ingbert,
    Frankfurt (Oder), Neu-Ulm, Weiden i.d.OPf.), in Versalien (90402 NÜRNBERG) und mit Länderkürzel
    (D-90402, A-1010, CH-8001). Keine Beträge ('50000 Euro'), keine Registernummern ('HRB 16963',
    'Amtsgericht Lübeck, 45650') und keine Nummern vor einem Zeilenumbruch ('Vermittler-Nr. 55123 /
    Stuttgart, 14.03.2025'). Nie über einen Spaltentrenner in Nachbarzellen; nur eine reine PLZ-Zelle mit der
    Ort-Zelle daneben ('53285 ⇥⇥ Bonn') ist eine Stelle über genau diesen Trenner."""
    return [text[s:e] for s, e in finde_plz_ort_stellen(text)]


# ----------------------------------------------------------------------
# Vertrags-/Kunden-/Schein-Nummern (Etikett + Wert)
# ----------------------------------------------------------------------
_NR_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß])(?:"
    r"(?:Versicherungsschein|Versicherungs|Versicherten|Versicherung|[a-zäöü]{3,30}versicherung|Vers\.?|VS|"
    r"Vertrags?|Kunden|Kd\.?|"
    r"Schadens?|Schaden|Antrags?|Policen?|Police|Personal|Mitglieds?|Depot|Konto|Zulagen?|Vorgangs?|"
    r"Vorgang|Referenz|Tagebuch|Bearbeitungs|Schein|Partner|Vermittler|Bestands?|Auftrags?|Kassen|"
    r"Akten|Geschäfts|Fall|Leistungs|Versorgungs|Renten|Riester|Vorsorge|Zugangs|Registrier|Registrierungs|"
    r"Bestell|Rechnungs|Beleg|Rechnung|Mandanten|Patienten|Fahrgestell|Abrechnungs|Arzt)"
    r"(?:[ \t]*[-.]?[ \t]*\n?[ \t]*|-\n(?:[^\n]*\n){0,3}?)(?:Nr\.?|Nummer|nummer|No\.?)"  # auch "…schein-" ⏎ Zellen ⏎ "Nr."
    r"|Aktenzeichen|Referenz|Geschäftszeichen|Gz\.?|Unser Zeichen|Ihr Zeichen|(?-i:Az\.?|AZ|VSNR|VS-Nr\.?|LANR)"
    r")(?![\wäöüß])(?:[ \t]+(?:lautet|ist))?",
    re.IGNORECASE)
# Kennungen ohne "Nr." hinter einem Vertragswort ("Auszahlung aus Ihrem Vertrag 47.897.336.2",
# "Ihre Police LV-2018-933486"): nur Werte, die eindeutig wie eine Kennung aussehen
_KENNUNG_WORT_RE = re.compile(
    r"(?<![\wäöüß])(?i:(?:Ihr(?:em|es|er|en)?|unser(?:em|es|er|en)?|de[mnrs]|zu[mr]?|aus|mit|im|zu|für|"
    r"betrifft|betreff|betr\.)[ \t]+)?"
    r"(?:Vertrag(?:es|s)?|Versicherungsvertrag(?:es|s)?|Police|Versicherungsschein(?:es|s)?|Schadenfall(?:es|s)?|"
    r"Vorgang(?:es|s)?|Kundenkonto|Leistungsfall(?:es|s)?|Akte)(?![\wäöüß])[ \t]*:?[ \t]*")
_KENNUNG_WERT_RE = re.compile(r"[A-Z0-9][A-Z0-9\-./]{4,30}[A-Z0-9](?![\w\-/])")
_NR_TRENNER_RE = re.compile(r"([ \t]*)([:.]?)([ \t]*)")
_NR_TOKEN_SPERRE = {"BLZ", "BIC", "IBAN", "EUR", "USD", "CHF", "DM", "UHR", "KM", "TEL", "FAX", "NR",
                    "BZW", "UND", "AG", "KG", "SE", "EG", "VON", "VOM", "BIS", "AB", "GMBH", "MIO",
                    "MRD", "TSD", "CO", "QM", "ST", "STK", "KW", "PS", "CM", "MM", "KG", "LTR"}
_NR_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-./]*")
_NR_BETRAG_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{1,2}")
_NR_DATUM_RE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}-\d{2}-\d{2}")


def _nummern_token(token: str) -> bool:
    """Ein Token gehört zu einer Nummer, wenn es eine Ziffer enthält oder ein kurzes
    Großbuchstaben-Kürzel (LV, KH, AZ, O) ist — nie ein Wort, Betrag oder Datum."""
    if not _NR_TOKEN_RE.fullmatch(token):
        return False
    if token.upper() in _NR_TOKEN_SPERRE:
        return False
    if _NR_BETRAG_RE.fullmatch(token) or _NR_DATUM_RE.fullmatch(token):
        return False
    if any(c.isdigit() for c in token):
        return True
    return (len(token) <= 3 and token.isupper()) or token in _REGISTERZEICHEN


# Registerzeichen in Aktenzeichen von Gerichten und Staatsanwaltschaften ("92 Js 6010/24", "4 Ds 123/24")
_REGISTERZEICHEN = frozenset({"Js", "UJs", "Ds", "Cs", "Ls", "Gs", "Ks", "Ns", "Qs", "Ss", "Ws", "Bs", "Hs",
                              "AR", "VRs", "BRs", "Ca", "Sa", "Ta"})
# Aktenzeichen, das am Zeilenende umbricht ("Aktenzeichen 381 C" ⏎ "817/23) nahm den Unfall auf")
_AKTENZEICHEN_ANFANG_RE = re.compile(r"[ \t]*(\d{1,4}[ ]+(?:[A-Z]{1,3}|" + "|".join(sorted(
    ["Js", "UJs", "Ds", "Cs", "Ls", "Gs", "Ks", "Ns", "Qs", "Ss", "Ws", "Bs", "Hs", "VRs", "BRs", "Ca", "Sa", "Ta"],
    key=len, reverse=True)) + r"))[ \t]*$")
_AKTENZEICHEN_REST_RE = re.compile(r"[ \t]*(\d{1,6}/\d{2,4})(?![\d/])")


def _nummer_aus_zeile(zeile: str):
    """Liest vom Zeilenanfang die Nummern-Tokens (bis Wort, Satzzeichen, Doppel-Leerzeichen)."""
    abschnitt = re.split(r"[ \t]{2,}|\t", zeile)[0]
    tokens = []
    for roh in abschnitt.split(" "):
        token = roh.rstrip(".,;:)")
        if not token or not _nummern_token(token):
            break
        tokens.append(token)
        if token != roh:
            break                                 # Satzzeichen beendet den Wert
    while tokens and tokens[-1].isalpha():
        tokens.pop()                              # kein nacktes Kürzel am Ende
    wert = " ".join(tokens).strip("-/. ")
    ziffern = sum(c.isdigit() for c in wert)
    if ziffern < 3 or len(wert) < 4:
        return None
    return wert


def _nummer_in_folgezeilen(text, pos, spalte):
    """Tabellenlayout: Etikett als Spaltenkopf, Wert in einer der nächsten Zeilen —
    entweder eine Zeile, die nur aus der Nummer besteht, oder das Token an derselben Spalte.
    Liest höchstens fünf Zeilen (nicht den Rest des Dokuments, Gutachten PERF-07)."""
    ende = pos
    for _ in range(5):
        n = text.find("\n", ende + 1)
        if n < 0:
            ende = len(text)
            break
        ende = n
    zeilen = text[pos:ende].split("\n")[1:5]
    for zeile in zeilen:
        if not zeile.strip():
            continue
        if _NR_DATUM_RE.fullmatch(zeile.strip()):
            continue
        wert = _nummer_aus_zeile(zeile.strip())
        if wert and wert == zeile.strip().rstrip(".,;:"):
            return wert                           # ganze Zeile ist die Nummer
        for m in re.finditer(r"(?<![^\s])[^\s]+(?:[ \t][^\s]+)*?(?=[ \t]{2,}|$)", zeile):
            if abs(m.start() - spalte) <= 6:
                wert = _nummer_aus_zeile(m.group(0))
                if wert:
                    return wert
                break
    return None


_PLZ_ZEILE_RE = re.compile(r"\d{5}[ \t]+[A-ZÄÖÜ]")


def _nummer_am_folgezeilenanfang(text: str, zeilenende: int):
    """Fließtext mit Etikett am Zeilenende: der Wert beginnt die nächste Zeile ("Aktenzeichen⏎VU/2024/99344)
    nahm …", "Versicherungsschein-Nr.⏎Ai HR-2022-251237" mit einem kurzen OCR-Rest davor). Nur Werte mit
    mindestens fünf Ziffern – keine Jahreszahl, kein Datum, keine PLZ-Zeile."""
    if zeilenende >= len(text):
        return None
    n = text.find("\n", zeilenende + 1)
    zeile = text[zeilenende + 1:n if n >= 0 else len(text)].strip()
    if not zeile or _PLZ_ZEILE_RE.match(zeile):
        return None
    kandidaten = [zeile]
    teile = zeile.split(" ", 1)
    if len(teile) == 2 and re.fullmatch(r"[A-Za-zÄÖÜäöü]{1,2}", teile[0]) and not _nummern_token(teile[0]):
        kandidaten.append(teile[1].lstrip())      # kurzer OCR-Rest vor der Nummer
    for kandidat in kandidaten:
        wert = _nummer_aus_zeile(kandidat)
        if wert and sum(c.isdigit() for c in wert) >= 5 and not _NR_DATUM_RE.fullmatch(wert):
            return wert
    return None


def _vertrag_spannen(text: str) -> list:
    treffer = []       # (anfang, ende)
    for m in _NR_ETIKETT_RE.finditer(text):
        # nur der Zeilenanfang hinter dem Etikett zählt (begrenztes Fenster: eine sehr lange Zeile mit vielen
        # Etiketten würde sonst quadratische Laufzeit kosten, Gutachten EQ-17/PERF-07)
        zeilenende = text.find("\n", m.end())
        if zeilenende < 0:
            zeilenende = len(text)
        zeile = text[m.end():min(zeilenende, m.end() + 300)]
        trenner = _NR_TRENNER_RE.match(zeile)
        leerraum = trenner.group(1) + trenner.group(3)
        # Spaltenkopf: nichts mehr in der Zeile, oder ohne Doppelpunkt ein breiter Abstand
        rest = zeile[trenner.end():]
        breit = not trenner.group(2) and (len(leerraum) >= 2 or "\t" in leerraum)
        spaltenkopf = not rest.strip() or breit
        wert = None if spaltenkopf else _nummer_aus_zeile(rest)
        if wert is None and breit and rest.strip():
            # Tabellenzeile "Versicherungsnummer  LV-2024-887766  Beginn 01.10.2024": der Wert steht in
            # derselben Zeile hinter dem breiten Abstand (Gutachten EQ-09)
            wert = _nummer_aus_zeile(rest.lstrip(" \t"))
        if (wert is None or len(wert) <= 4) and not spaltenkopf and zeilenende < len(text):
            # Aktenzeichen über den Zeilenumbruch ("381 C" ⏎ "817/23"): Zahl + Registerzeichen am Zeilenende,
            # Aktennummer/Jahr am Anfang der Folgezeile
            a = _AKTENZEICHEN_ANFANG_RE.fullmatch(rest)
            b = _AKTENZEICHEN_REST_RE.match(text, zeilenende + 1) if a else None
            if a and b:
                wert = text[m.end() + trenner.end() + a.start(1):b.end(1)]
        if wert is None and spaltenkopf:
            zeilenanfang = text.rfind("\n", max(0, m.start() - 400), m.start()) + 1
            wert = _nummer_in_folgezeilen(text, m.start(), m.start() - zeilenanfang)
            if wert is None and not rest.strip() and text[zeilenanfang:m.start()].strip():
                # Etikett am Ende einer Fließtextzeile (kein Spaltenkopf: davor steht Text)
                wert = _nummer_am_folgezeilenanfang(text, zeilenende)
        if wert:
            anfang = text.find(wert, m.end())
            if anfang >= 0:
                treffer.append((anfang, anfang + len(wert)))
    # Kennung ohne "Nr." hinter einem Vertragswort
    for m in _KENNUNG_WORT_RE.finditer(text):
        w = _KENNUNG_WERT_RE.match(text, m.end())
        if not w:
            continue
        wert = w.group(0).rstrip(".-/")
        if (sum(c.isdigit() for c in wert) >= 5 and not _NR_DATUM_RE.fullmatch(wert)
                and not _NR_BETRAG_RE.fullmatch(wert) and not re.fullmatch(r"(?:19|20)\d{2}", wert)):
            treffer.append((w.start(), w.start() + len(wert)))
    # Werte, die in einem anderen Wert liegen ("345/24" in "12 AZ 345/24"), entfallen – ein Durchlauf über
    # die nach Anfang sortierten Treffer mit laufendem Maximum des Endes (Gutachten PERF-07)
    aus = []
    gesehen = set()
    max_ende = -1
    for a, e in sorted(treffer, key=lambda t: (t[0], -t[1])):
        if (a, e) in gesehen:
            continue
        gesehen.add((a, e))
        if max_ende < e:
            aus.append(Stelle(a, e))
        max_ende = max(max_ende, e)
    return aus


def finde_vertragsnummern_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _vertrag_spannen) if s.streng]


def finde_vertragsnummern(text):
    """Nummern hinter verräterischen Etiketten (Versicherungsnummer, Vers.-Nr., VS-Nr.,
    Schein-Nr., Kunden-Nr., Vorgangsnummer, Aktenzeichen, Referenz …), auch hinter breitem Abstand
    in derselben Zeile und hinter einem über Zellen umbrochenen Etikett (Gutachten EQ-09), sowie
    Kennungen ohne "Nr." hinter einem Vertragswort ("Ihr Vertrag 47.897.336.2"). Der Wert endet am
    Zeilenende, bei doppeltem Leerzeichen, Satzzeichen oder dem nächsten Wort; Spaltenköpfe
    ('Vertragsnummer | Beginn | Ablauf') nehmen die Nummer aus der Folgezeile."""
    return _eindeutig([text[s:e] for s, e in finde_vertragsnummern_stellen(text)])


# ----------------------------------------------------------------------
# Sozialversicherungs-/Rentenversicherungsnummer
# ----------------------------------------------------------------------
_SV_RE = re.compile(r"(?<![\dA-Za-z])\d{2}[ \t]?\d{6}[ \t]?[A-Za-z][ \t]?\d{3}(?![\dA-Za-z])")


def _svnr_spannen(text: str) -> list:
    return [Stelle(m.start(), m.end()) for m in _SV_RE.finditer(text)]


def finde_sv_nummer_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _svnr_spannen) if s.streng]


def finde_sv_nummer(text):
    return [text[s:e] for s, e in finde_sv_nummer_stellen(text)]


# ----------------------------------------------------------------------
# Steuer-ID (IdNr) und Steuernummer
# ----------------------------------------------------------------------
def _steuer_id_gueltig(nummer: str) -> bool:
    """Amtliche Prüfziffern-Kontrolle der Steuer-IdNr (§ 139b AO).
    Damit erkennen wir 11-stellige IDs auch OHNE Beschriftung davor,
    ohne zufällige Zahlenkolonnen zu erwischen."""
    z = re.sub(r"\D", "", nummer)
    if len(z) != 11 or z[0] == "0":
        return False
    produkt = 10
    for ziffer in z[:10]:
        summe = (int(ziffer) + produkt) % 10
        if summe == 0:
            summe = 10
        produkt = (2 * summe) % 11
    pruef = 11 - produkt
    if pruef == 10:
        pruef = 0
    return pruef == int(z[10])


def _steuer_id_struktur(nummer: str) -> bool:
    """Amtliche Strukturregel: In den ersten zehn Ziffern kommt genau eine Ziffer doppelt
    oder dreifach vor, alle anderen genau einmal (senkt die Zufallsrate von ~9 % auf ~1 %)."""
    z = re.sub(r"\D", "", nummer)
    mehrfach = [n for n in Counter(z[:10]).values() if n > 1]
    return len(mehrfach) == 1 and mehrfach[0] in (2, 3)


_STEUER_ID_ETIKETT_RE = re.compile(
    r"(?:Steuer[\s\-]?(?:Identifikationsnummer|IdNr\.?|ID|Id|id)|IdNr\.?|Identifikationsnummer|TIN)(?![A-Za-zäöü])"
    r"(?P<zwischen>[^\d\n]{0,12}?\n?[^\d\n]{0,12}?|[^\d\n:.;]{0,45}:[ \t]*)"
    r"(\d[\d ]{1,13}(?:\n[ \t]*)?[\d ]{0,13}\d)(?!\d)")


_ANDERES_ETIKETT_RE = re.compile(r"(?i:tel(?:efon)?|fax|mobil|handy|iban|konto|vertrag|kunden|versicherungs|"
                                 r"nr\.|nummer|datum|geb\.|geboren)")


def _steuerid_spannen(text: str) -> list:
    aus = []
    # 1) Mit Beschriftung — auch Formularlayouts wie "Identifikationsnummer (4)" mit bis zu 12 Zeichen
    #    zwischen Etikett und Nummer (inkl. Zeilenumbruch); die Prüfziffer bestimmt nur die Sicherheit
    for m in _STEUER_ID_ETIKETT_RE.finditer(text):
        if _ANDERES_ETIKETT_RE.search(m.group("zwischen")):
            continue                                    # "Steuer-ID und Telefon: 0911 …": Nummer des Telefons
        wert = m.group(2).strip()
        if sum(c.isdigit() for c in wert) != 11 or wert.count("\n") > 1:
            continue
        s = m.start(2) + (len(m.group(2)) - len(m.group(2).lstrip()))
        gueltig = _steuer_id_gueltig(wert)
        aus.append(Stelle(s, s + len(wert), 1.0 if gueltig else 0.8, True,
                          None if gueltig else HINWEIS_PRUEFZIFFER))
    # 2) Ohne Beschriftung: freistehende 11-stellige Nummer mit gültiger Prüfziffer + Struktur
    for m in re.finditer(r"(?<!\d)(\d{11})(?!\d)", text):
        if _steuer_id_gueltig(m.group(1)) and _steuer_id_struktur(m.group(1)):
            aus.append(Stelle(m.start(1), m.end(1), 1.0))
    aus.sort()
    return aus


def finde_steuer_id_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _steuerid_spannen) if s.streng]


def finde_steuer_id(text):
    return _eindeutig([text[s:e] for s, e in finde_steuer_id_stellen(text)])


_STEUERNR_FREI_RE = re.compile(r"(?<![\d/])\d{2,3}/\d{3,4}/\d{4,5}(?![\d/])")
_STEUERNR_ETIKETT_RE = re.compile(r"(?i:Steuernummer|Steuer-?Nr\.?|St\.-?Nr\.?|StNr\.?)[ \t]*:?[ \t]*"
                                  r"(\d{13}|\d{2,3}[ \t]\d{3,4}[ \t]\d{4,5}|\d{10,11})(?!\d)")
_UST_ID_RE = re.compile(r"(?i:USt[-\s]?Id(?:Nr)?\.?|Umsatzsteuer-?(?:Identifikationsnummer|ID|IdNr\.?))"
                        r"[ \t]*:?[ \t]*(DE[ \t]?\d{9})(?!\d)")
# Firmenzusammenhang einer USt-IdNr. (Fußzeile des Versicherers, Gutachten EQ-16): dann keine Person
_FIRMEN_KONTEXT_RE = re.compile(
    r"(?<![\wäöüß])(?:GmbH|AG|SE|KG|KGaA|OHG|mbH|e\.\s?V\.|eG|VVaG|a\.\s?G\.|gAG|Versicherung\w*|"
    r"Versicherer|Bank|Sparkasse|HRB|HRA|Registergericht|Amtsgericht|Handelsregister|Vorstand|Aufsichtsrat\w*|"
    r"Geschäftsführ\w*|Sitz(?:[ \t]+der[ \t]+Gesellschaft)?)(?![\wäöüß])|·")


def _steuernr_spannen(text: str) -> list:
    aus = [Stelle(m.start(), m.end()) for m in _STEUERNR_FREI_RE.finditer(text)]
    for m in _STEUERNR_ETIKETT_RE.finditer(text):
        aus.append(Stelle(m.start(1), m.end(1)))
    for m in _UST_ID_RE.finditer(text):
        # Zeile der Nummer und die zwei Zeilen davor: Firmenangaben -> USt-IdNr. der Firma, kein Personenbezug
        anfang = m.start()
        for _ in range(3):
            anfang = text.rfind("\n", 0, max(0, anfang - 1))
            if anfang < 0:
                anfang = 0
                break
        ende = text.find("\n", m.end())
        umgebung = text[anfang:ende if ende >= 0 else len(text)]
        if _FIRMEN_KONTEXT_RE.search(umgebung):
            continue
        aus.append(Stelle(m.start(1), m.end(1)))
    aus.sort()
    return aus


def finde_steuernummer_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _steuernr_spannen) if s.streng]


def finde_steuernummer(text):
    """Steuernummern 123/4567/8901 bzw. 12/345/67890 (auch ohne Etikett), 13-stellig oder
    mit Leerzeichen nur mit Etikett (Steuernummer, St.-Nr.), außerdem USt-IdNr. DE123456789 – aber nicht
    die USt-IdNr. einer Firma (Fußzeile mit Rechtsform, Registergericht, Vorstand …)."""
    return [text[s:e] for s, e in finde_steuernummer_stellen(text)]


# ----------------------------------------------------------------------
# Weitere Kennnummern
# ----------------------------------------------------------------------
_KINDERGELD_RE = re.compile(r"(?<![\dA-Za-z])\d{3}[ \t]?FK[ \t]?\d{6}(?![\dA-Za-z])", re.IGNORECASE)


def _kindergeld_spannen(text: str) -> list:
    return [Stelle(m.start(), m.end()) for m in _KINDERGELD_RE.finditer(text)]


def finde_kindergeldnummer_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _kindergeld_spannen) if s.streng]


def finde_kindergeldnummer(text):
    """Kindergeldnummern wie 009FK407160 (Format: 3 Ziffern + FK + 6 Ziffern)."""
    return [text[s:e] for s, e in finde_kindergeldnummer_stellen(text)]


_KVNR_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]\d{9}(?![A-Za-z0-9])")
_KVNR_ETIKETT_RE = re.compile(
    r"(?i:Krankenversichertennummer|Krankenversicherten-Nr\.?|Versichertennummer|Versicherten-Nr\.?|KVNR|"
    r"KV-Nr\.?|Versicherten-ID)[ \t]*:?[ \t]*([A-Z][ \t]?\d{3}[ \t]?\d{3}[ \t]?\d{3})(?![A-Za-z0-9])")


def _kvnr_pruefziffer_ok(nummer: str) -> bool:
    """Prüfziffer der Krankenversichertennummer (Buchstabe -> 01..26, Gewichte 1,2 wie Luhn)."""
    z = re.sub(r"\s", "", nummer)
    if not re.fullmatch(r"[A-Z]\d{9}", z):
        return False
    folge = f"{ord(z[0]) - 64:02d}" + z[1:9]
    summe = 0
    for i, c in enumerate(folge):
        p = int(c) * (1 if i % 2 == 0 else 2)
        summe += p // 10 + p % 10
    return summe % 10 == int(z[9])


def _kvnr_spannen(text: str) -> list:
    aus = [Stelle(m.start(), m.end(), 0.95 if _kvnr_pruefziffer_ok(m.group(0)) else 0.85)
           for m in _KVNR_RE.finditer(text)]
    belegt = {(s.start, s.ende) for s in aus}
    for m in _KVNR_ETIKETT_RE.finditer(text):
        if (m.start(1), m.end(1)) not in belegt:
            aus.append(Stelle(m.start(1), m.end(1), 0.9))
    aus.sort()
    return aus


def finde_kv_nummer_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _kvnr_spannen) if s.streng]


def finde_kv_nummer(text):
    """Krankenversichertennummer: ein Großbuchstabe + 9 Ziffern (A123456789), mit Etikett auch in
    Gruppen geschrieben (A 123 456 789)."""
    return [text[s:e] for s, e in finde_kv_nummer_stellen(text)]


# Ausweise: Etikett + Wert, außerdem freistehend die amtlichen Formate mit gültiger Prüfziffer
_AUSWEIS_ETIKETT_RE = re.compile(
    r"(?i:(?:Personalausweis|Ausweis|Reisepass|Pass|Führerschein|Fuehrerschein|Aufenthaltstitel|"
    r"Aufenthaltserlaubnis|PA|FS|Dokument(?:en)?)[-\s]*\(?[ \t]*(?:Nr\.?|Nummer|nummer|No\.?|Number)|"
    r"Ausweisnummer|Passnummer|Führerscheinnummer|Dokumentennummer)"
    r"[ \t]*:?[ \t]*([A-Z0-9]{6,14})(?![A-Za-z0-9])")
_AUSWEIS_FREI_RE = re.compile(r"(?<![A-Za-z0-9])([CFGHJKLMNPRTVWXYZ0-9]{9})(\d)(?![A-Za-z0-9])")


def _icao_pruefziffer(zeichen: str) -> int:
    """Prüfziffer nach ICAO 9303 (Gewichte 7, 3, 1; Buchstaben A=10 … Z=35) – Personalausweis und Pass."""
    summe = 0
    gewichte = (7, 3, 1)
    for i, c in enumerate(zeichen):
        wert = int(c) if c.isdigit() else ord(c) - 55
        summe += wert * gewichte[i % 3]
    return summe % 10


def _ausweis_spannen(text: str) -> list:
    aus = []
    for m in _AUSWEIS_ETIKETT_RE.finditer(text):
        if any(c.isdigit() for c in m.group(1)):
            aus.append(Stelle(m.start(1), m.end(1)))
    belegt = [(s.start, s.ende) for s in aus]
    for m in _AUSWEIS_FREI_RE.finditer(text):
        kern = m.group(1)
        if any(a <= m.start() < b for a, b in belegt):
            continue
        buchstaben = sum(c.isalpha() for c in kern)
        if buchstaben < 1 or buchstaben > 6 or sum(c.isdigit() for c in kern) < 2:
            continue                                  # reine Zahlen oder Wörter sind keine Ausweisnummern
        if _icao_pruefziffer(kern) == int(m.group(2)):
            aus.append(Stelle(m.start(), m.end(), 0.8, False))
    aus.sort()
    return aus


def finde_ausweisnummer_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _ausweis_spannen) if s.streng]


def finde_ausweisnummer(text):
    """Personalausweis-/Reisepass-/Führerscheinnummer — mit Etikett (auch "Personalausweis (Nr. …)").
    Ohne Etikett erkennt nur die Detektor-Schnittstelle (stellen()) die amtlichen Formate (neuer
    Personalausweis/Reisepass: 9 Zeichen aus CFGHJKLMNPRTVWXYZ0-9 plus Prüfziffer)."""
    return [text[s:e] for s, e in finde_ausweisnummer_stellen(text)]


_MANDAT_ETIKETT_RE = re.compile(
    r"(?i:Mandatsreferenz(?:nummer|-?Nr\.?)?|Mandats-?Nr\.?|SEPA-?Mandat(?:s)?"
    r"[-\s]?(?:Nr\.?|Nummer|Referenz)?|Mandat-?ID)[ \t]*:?")
_MANDAT_WERT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-./+]{3,34}(?![A-Za-z0-9])")
_FUELL_REST_RE = re.compile(r"[a-z]{1,3}[.…]+(?=[ \t.…_:]|$)")


def _mandat_spannen(text: str) -> list:
    aus = []
    for m in _MANDAT_ETIKETT_RE.finditer(text):
        pos = m.end()
        # Füllpunkte, OCR-Reste und höchstens ein Umbruch zwischen Etikett und Wert
        fenster_ende = min(len(text), pos + 60)
        umbrueche = 0
        while pos < fenster_ende:
            c = text[pos]
            if c == "\n":
                umbrueche += 1
                if umbrueche > 1:
                    break
                pos += 1
            elif c in " \t.…_:":
                pos += 1
            elif _FUELL_REST_RE.match(text, pos):
                pos = _FUELL_REST_RE.match(text, pos).end()     # "nn." zwischen den Füllpunkten (OCR)
            else:
                w = _MANDAT_WERT_RE.match(text, pos)
                if w is None:
                    break
                wert = w.group(0).rstrip(".")
                if sum(c.isdigit() for c in wert) >= 2:
                    aus.append(Stelle(w.start(), w.start() + len(wert)))
                    break
                if wert.islower() and len(wert) <= 12:
                    pos = w.end()                       # OCR-Rest der Füllpunkte ("nnnnsan..")
                    continue
                break
    return aus


def finde_mandatsreferenz_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _mandat_spannen) if s.streng]


def finde_mandatsreferenz(text):
    """SEPA-Mandatsreferenz (bis 35 Zeichen) — nur mit Etikett; Füllpunkte und ein Zeilenumbruch
    zwischen Etikett und Wert sind erlaubt."""
    return [text[s:e] for s, e in finde_mandatsreferenz_stellen(text)]


_FIN_RE = re.compile(r"(?<![A-Za-z0-9])(?=[A-HJ-NPR-Z0-9]{0,16}\d)(?=[A-HJ-NPR-Z0-9]{0,16}[A-HJ-NPR-Z])"
                     r"[A-HJ-NPR-Z0-9]{17}(?![A-Za-z0-9])")


def _fin_spannen(text: str) -> list:
    return [Stelle(m.start(), m.end()) for m in _FIN_RE.finditer(text)]


def finde_fin_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _fin_spannen) if s.streng]


def finde_fin(text):
    """Fahrzeug-Identnummer (FIN/VIN): 17 Zeichen ohne I, O, Q, mit Buchstaben UND Ziffern."""
    return [text[s:e] for s, e in finde_fin_stellen(text)]


_BIC_LAENDER = {"DE", "AT", "CH", "LI", "LU", "FR", "IT", "ES", "NL", "BE", "PL", "GB", "IE", "DK",
                "SE", "NO", "FI", "PT", "CZ", "SK", "HU", "HR", "SI", "RO", "BG", "GR", "TR", "US",
                "CA", "EE", "LV", "LT", "MT", "CY", "IS", "MC", "UA", "RS", "BA", "AU", "JP", "CN"}
_BIC_WERT_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}([A-Z]{2})[A-Z0-9]{2}(?:[A-Z0-9]{3})?(?![A-Za-z0-9])")
_BIC_ETIKETT_RE = re.compile(r"(?i:(?<![\wäöüß])BIC|SWIFT(?:-?(?:Code|BIC))?)[ \t.:]*(?:\n[ \t]*)?"
                             r"([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)(?![A-Za-z0-9])")
# Freistehender BIC ohne Etikett und ohne IBAN: nur die eindeutige Form (11 Zeichen auf "XXX" oder mit
# Ziffer im Ortscode) – 8 Großbuchstaben allein könnten ein Wort sein
_BIC_FREI_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}([A-Z]{2})(?:[A-Z0-9]{2}XXX|[A-Z0-9]\d(?:[A-Z0-9]{3})?|"
                          r"\d[A-Z0-9](?:[A-Z0-9]{3})?)(?![A-Za-z0-9])")


def _bic_spannen(text: str) -> list:
    aus = [Stelle(m.start(1), m.end(1)) for m in _BIC_ETIKETT_RE.finditer(text)]
    belegt = {(s.start, s.ende) for s in aus}
    ibans = [s for s in _iban_spannen(text) if s.streng]
    for iban in ibans:
        fenster_ende = iban.ende
        for _ in range(2):                                 # gleiche und nächste Zeile
            n = text.find("\n", fenster_ende + 1)
            fenster_ende = n if n >= 0 else len(text)
        fenster_ende = min(fenster_ende, iban.ende + 60)
        for b in _BIC_WERT_RE.finditer(text, iban.ende, fenster_ende):
            if b.group(1) in _BIC_LAENDER and (b.start(), b.end()) not in belegt:
                aus.append(Stelle(b.start(), b.end()))
                belegt.add((b.start(), b.end()))
    for b in _BIC_FREI_RE.finditer(text):
        if b.group(1) in _BIC_LAENDER and (b.start(), b.end()) not in belegt:
            aus.append(Stelle(b.start(), b.end(), 0.7, False))
            belegt.add((b.start(), b.end()))
    aus.sort()
    return aus


def finde_bic_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _bic_spannen) if s.streng]


def finde_bic(text):
    """BIC/SWIFT — mit Etikett oder unmittelbar hinter einer IBAN (gleiche/nächste Zeile)."""
    return _eindeutig([text[s:e] for s, e in finde_bic_stellen(text)])


def _luhn_gueltig(nummer: str) -> bool:
    ziffern = [int(c) for c in re.sub(r"\D", "", nummer)]
    summe = 0
    for i, z in enumerate(reversed(ziffern)):
        if i % 2 == 1:
            z *= 2
            if z > 9:
                z -= 9
        summe += z
    return summe % 10 == 0


_KARTE_RE = re.compile(r"(?<![\d])(?:[23456]\d{3}(?:[ \-]?\d{4}){2}[ \-]?\d{1,4}(?:[ \-]?\d{1,3})?"
                       r"|3\d{3}[ \-]?\d{6}[ \-]?\d{5})(?![\d])")
_KARTE_KONTEXT_RE = re.compile(r"(?i:kreditkart|karten-?(?:nr|nummer)|kartennummer|visa|master\s?card|"
                               r"american\s+express|amex|maestro|diners|jcb|card)")
_IBAN_KOPF_DAVOR_RE = re.compile(r"[A-Za-z]{2}\d{2}[ \t]?$")


def _kreditkarte_spannen(text: str) -> list:
    aus = []
    for m in _KARTE_RE.finditer(text):
        k = m.group(0)
        if not 13 <= len(re.sub(r"\D", "", k)) <= 19:
            continue
        if _IBAN_KOPF_DAVOR_RE.search(text[max(0, m.start() - 6):m.start()]):
            continue                                       # Ziffergruppen einer IBAN
        if _luhn_gueltig(k):
            aus.append(Stelle(m.start(), m.end()))
        elif _KARTE_KONTEXT_RE.search(text[max(0, m.start() - 60):m.start()]):
            aus.append(Stelle(m.start(), m.end(), 0.6, False, HINWEIS_PRUEFZIFFER))
    return aus


def finde_kreditkarte_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _kreditkarte_spannen) if s.streng]


def finde_kreditkarte(text):
    """Kreditkartennummern (13-19 Ziffern in Gruppen, Luhn-Prüfsumme, Anfangsziffer 2-6)."""
    return [text[s:e] for s, e in finde_kreditkarte_stellen(text)]


# ----------------------------------------------------------------------
# Kfz-Kennzeichen
# ----------------------------------------------------------------------
# Abkürzungen, die KEINE Unterscheidungszeichen sind, aber in Versicherungstexten
# vor Kürzel + Zahl stehen (AVB KH 2008, DIN A 4, BMW X5 …)
_KFZ_SPERRE = {
    "AVB", "AKB", "AHB", "ABV", "AGB", "ARB", "AUB", "ABB", "ALB", "AVG", "BGB", "DIN", "ISO", "SGB", "VVG",
    "VAG", "HGB", "EWG", "VO", "KFZ", "PKW", "LKW", "SF", "PKV", "GKV", "DRV", "BMW", "VW", "KIA", "BYD",
    "GMC", "RAM", "AMG", "GTI", "TDI", "TSI", "TFSI", "GLC", "GLA", "GLE", "GLS", "CLA", "CLS", "SLK",
    "SUV", "ABS", "ESP", "PDF", "PIN", "TAN", "UID", "IBAN", "BIC", "BLZ", "VHV", "HUK", "DKV", "HDI",
    "WWK", "LVM", "AXA", "TEL", "FAX", "VON", "ZUM", "ZUR", "ICH", "SIE", "WIR", "DU", "EU", "UN", "USA",
    "EDV", "LCD", "LED", "USB", "GPS", "ADAC", "TÜV", "DEKRA", "GDV", "VVW", "BAV", "BU", "KV", "LV", "RV",
    "HUK", "ERGO", "AVB", "AKB", "SFR", "TKS", "KH", "VK", "TK",
    # römische Zahlen in Aktenzeichen/Gesetzen ("IV ZR 123/19", "II BvR 1", "SGB VI 2023", Gutachten EQ-13)
    "I", "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII",
}
# Hinweis: KH (Bad Kreuznach), VK (Völklingen), TK (Teltow? nein) stehen oben, weil sie in
# Versicherungstexten praktisch immer Sparten-Kürzel sind (KH = Kfz-Haftpflicht, VK = Vollkasko).
_KFZ_RE = re.compile(
    r"(?<![\wÄÖÜäöü\-])([A-ZÄÖÜ]{1,3})([-\s])([A-Z]{1,2})[ \t]?(\d{1,4})([EH])?"
    r"(?![\wäöüß])(?![ \t]*(?:Uhr|EUR|€|%|Prozent|km|Jahre|Monate|Tage|Punkte)(?![\wäöüß]))")
_KFZ_KLEIN_RE = re.compile(
    r"(?i:Kennzeichen)[ \t]*:?[ \t]*((?-i:[a-zäöü]{1,3}[-\s][a-z]{1,2}[ \t]?\d{1,4}[eh]?))(?![\wäöüß])")


def _kfz_spannen(text: str) -> list:
    aus = []
    for m in _KFZ_RE.finditer(text):
        kuerzel, trenner, ziffern = m.group(1), m.group(2), m.group(4)
        if kuerzel in _KFZ_SPERRE:
            continue
        if trenner == "\n":
            continue                                     # kein Kennzeichen über einen Zeilenumbruch
        # "SGB VI 2023", "VVG AB 2008": Leerzeichen-Trenner + Jahreszahl -> kein Kennzeichen
        if trenner != "-" and len(ziffern) == 4 and ziffern[:2] in ("19", "20"):
            continue
        aus.append(Stelle(m.start(), m.end()))
    for m in _KFZ_KLEIN_RE.finditer(text):
        aus.append(Stelle(m.start(1), m.end(1)))
    aus.sort()
    return aus


def finde_kennzeichen_stellen(text):
    return [(s.start, s.ende) for s in _auf_eingabe(text, _kfz_spannen) if s.streng]


def finde_kennzeichen(text):
    """Deutsche Kfz-Kennzeichen (N-AB 1234, B-MW 1, M-X 1E, NM-XY 123, N AB 1234) —
    nicht aber Normen/Bedingungswerke/Typen (DIN EN 1234, AVB KH 2008, BMW X5, ISO 9001,
    römische Zahlen in Aktenzeichen wie "IV ZR 123/19")."""
    return [text[s:e] for s, e in finde_kennzeichen_stellen(text)]


# ----------------------------------------------------------------------
# Wissensbasierte Kategorien (Beruf, Arbeitgeber, Gesundheit, Ort, Ausland) – die Erkennung selbst steht
# in anonymisierer/detektoren/wissen_*.py; hier nur die Text-Schnittstelle für Formularfelder und Werkzeuge
# ----------------------------------------------------------------------
def _wissen_funktion(name):
    def finde(text):
        try:
            from .detektoren import wissen_kontext
        except Exception:  # pragma: no cover - Paket ohne Wissensdetektoren
            return []
        funktion = getattr(wissen_kontext, name, None)
        if funktion is None or not text:
            return []
        return [text[s.start:s.ende] for s in _auf_eingabe(text, lambda t: [Stelle(a, b) for a, b in funktion(t)])]
    finde.__name__ = f"finde_{name}"
    return finde


finde_berufe = _wissen_funktion("berufe_stellen")
finde_berufe.__doc__ = "Berufsangaben in Personenkontext (Beruf:, tätig als, ist … von Beruf)."
finde_arbeitgeber = _wissen_funktion("arbeitgeber_stellen")
finde_arbeitgeber.__doc__ = "Arbeitgeber in Personenkontext (Arbeitgeber:, beschäftigt bei) – nie Versicherer/Banken."
finde_diagnosen = _wissen_funktion("diagnosen_stellen")
finde_diagnosen.__doc__ = "Diagnosen, ICD-10-Codes und Körpermaße (Gesundheitsdaten, Art. 9 DSGVO)."
finde_medikamente = _wissen_funktion("medikamente_stellen")
finde_medikamente.__doc__ = "Medikamente mit Dosierung (Gesundheitsdaten, Art. 9 DSGVO)."
finde_orte = _wissen_funktion("orte_stellen")
finde_orte.__doc__ = "Orte ohne PLZ in Ort-Datum-Zeilen und als Geburtsort."
finde_ausland = _wissen_funktion("ausland_stellen")
finde_ausland.__doc__ = "Ausländische Anschriften (A, CH, NL, PL, IT, FR …) und Kennzeichen hinter einem Etikett."


# ----------------------------------------------------------------------
# Stellen je Kategorie (Detektor-Schnittstelle)
# ----------------------------------------------------------------------
SPANNEN = {
    "iban": _iban_spannen, "email": _email_spannen, "telefon": _telefon_spannen, "geburt": _geburt_spannen,
    "strasse": _strasse_spannen, "plzort": _plz_ort_spannen, "vertrag": _vertrag_spannen,
    "svnr": _svnr_spannen, "steuerid": _steuerid_spannen, "steuernr": _steuernr_spannen,
    "kvnr": _kvnr_spannen, "kindergeld": _kindergeld_spannen, "kfz": _kfz_spannen, "fin": _fin_spannen,
    "ausweis": _ausweis_spannen, "mandat": _mandat_spannen, "bic": _bic_spannen,
    "kreditkarte": _kreditkarte_spannen, "datum": _datum_spannen,
}
# Jede Text-Schnittstelle kennt ihre Kategorie: Detektoren nehmen dann die Stellen-Schnittstelle (wird eine
# Funktion in KATEGORIEN ersetzt, z. B. in Tests, fehlt das Merkmal und es gilt der Fundtext)
for _k, _f in (("iban", finde_iban), ("email", finde_email), ("telefon", finde_telefon),
               ("geburt", finde_geburtsdaten), ("strasse", finde_strasse), ("plzort", finde_plz_ort),
               ("vertrag", finde_vertragsnummern), ("svnr", finde_sv_nummer), ("steuerid", finde_steuer_id),
               ("steuernr", finde_steuernummer), ("kvnr", finde_kv_nummer), ("kindergeld", finde_kindergeldnummer),
               ("kfz", finde_kennzeichen), ("fin", finde_fin), ("ausweis", finde_ausweisnummer),
               ("mandat", finde_mandatsreferenz), ("bic", finde_bic), ("kreditkarte", finde_kreditkarte),
               ("datum", finde_alle_daten)):
    _f.kategorie = _k


def stellen(kategorie: str, text: str, nur_streng: bool = False) -> list:
    """Alle Stellen einer Muster-Kategorie im Text (Stelle mit Sicherheit/Hinweis), auch die unsicheren
    (Prüfziffer falsch …), es sei denn nur_streng=True. Leere Liste für unbekannte Kategorien."""
    funktion = SPANNEN.get(kategorie)
    if funktion is None:
        return []
    aus = _auf_eingabe(text, funktion)
    return [s for s in aus if s.streng] if nur_streng else aus


# ----------------------------------------------------------------------
# Kategorienliste
# ----------------------------------------------------------------------
# Reihenfolge = Reihenfolge der Häkchen in der Oberfläche
KATEGORIEN = [
    # (Schlüssel, Anzeigename, Platzhalter, Funktion, standardmäßig an?)
    ("namen",       "Personennamen (KI-Erkennung)",              None,               None,                  True),
    ("iban",        "IBANs",                                     "[IBAN]",           finde_iban,            True),
    ("email",       "E-Mail-Adressen",                           "[E-MAIL]",         finde_email,           True),
    ("telefon",     "Telefonnummern",                            "[TELEFON]",        finde_telefon,         True),
    ("geburt",      "Geburtsdaten",                              "[GEB-DATUM]",      finde_geburtsdaten,    True),
    ("strasse",     "Straße + Hausnummer, Postfach",             "[ADRESSE]",        finde_strasse,         True),
    ("plzort",      "PLZ + Ort",                                 "[PLZ ORT]",        finde_plz_ort,         True),
    ("vertrag",     "Vertrags-/Kunden-/Schein-/Aktenzeichen",    "[VERTRAGS-NR]",    finde_vertragsnummern, True),
    ("svnr",        "Sozialversicherungsnummern",                "[SV-NR]",          finde_sv_nummer,       True),
    ("steuerid",    "Steuer-IDs",                                "[STEUER-ID]",      finde_steuer_id,       True),
    ("steuernr",    "Steuernummern / USt-IdNr.",                 "[STEUER-NR]",      finde_steuernummer,    True),
    ("kvnr",        "Krankenversichertennummern",                "[KV-NR]",          finde_kv_nummer,       True),
    ("kindergeld",  "Kindergeldnummern",                         "[KINDERGELD-NR]",  finde_kindergeldnummer, True),
    ("kfz",         "Kfz-Kennzeichen",                           "[KENNZEICHEN]",    finde_kennzeichen,     True),
    ("fin",         "Fahrzeug-Identnummern (FIN)",               "[FIN]",            finde_fin,             True),
    ("ausweis",     "Ausweis-/Pass-/Führerscheinnummern",        "[AUSWEIS-NR]",     finde_ausweisnummer,   True),
    ("mandat",      "SEPA-Mandatsreferenzen",                    "[MANDATSREFERENZ]", finde_mandatsreferenz, True),
    ("bic",         "BIC (bei IBAN oder Etikett)",               "[BIC]",            finde_bic,             True),
    ("kreditkarte", "Kreditkartennummern",                       "[KREDITKARTE]",    finde_kreditkarte,     True),
    ("international", "Ausländische Anschriften und Kennzeichen", "[AUSLAND]",       finde_ausland,         True),
    ("ort",         "Orte ohne PLZ (Ort-Datum-Zeile, Geburtsort)", "[ORT]",          finde_orte,            True),
    ("beruf",       "Beruf (bei Personen)",                      "[BERUF]",          finde_berufe,          True),
    ("arbeitgeber", "Arbeitgeber (bei Personen)",                "[ARBEITGEBER]",    finde_arbeitgeber,     True),
    ("diagnose",    "Diagnosen, ICD-Codes (Gesundheitsdaten)",   "[DIAGNOSE]",       finde_diagnosen,       False),
    ("medikament",  "Medikamente (Gesundheitsdaten)",            "[MEDIKAMENT]",     finde_medikamente,     False),
    ("datum",       "ALLE Datumsangaben (Vorsicht!)",            "[DATUM]",          finde_alle_daten,      False),
]

# Findet dieselbe Zeichenkette in mehreren Kategorien, gewinnt die spezifischere
# (vorne in dieser Liste): eine SV-Nummer hinter "Versicherungsnummer" bleibt [SV-NR],
# eine Kontonummer mit führender 0 wird nicht zur [TELEFON].
KATEGORIE_PRIORITAET = [
    "iban", "steuerid", "svnr", "kvnr", "kindergeld", "steuernr", "fin", "kreditkarte", "bic",
    "ausweis", "mandat", "email", "geburt", "kfz", "strasse", "plzort", "international", "vertrag", "telefon",
    "diagnose", "medikament", "arbeitgeber", "beruf", "ort", "datum",
]

# ----------------------------------------------------------------------
# Schutzstufen (Vertrag Abschnitt 9)
# ----------------------------------------------------------------------
_KERN = {k for k, _, _, _, an in KATEGORIEN if an} - {"beruf", "arbeitgeber", "international", "ort"}
GESUNDHEIT = frozenset({"diagnose", "medikament"})
PROFILE = {
    "ausgewogen": {
        "aktive": frozenset(_KERN),
        "hinweis": GESUNDHEIT,                 # erkannt, aber nur gemeldet und abgewählt angeboten
        "beschreibung": "Direkte Kennungen: Namen, Anschrift, IBAN, Telefon, Nummern … – mehr Zusammenhang "
                        "für die KI. Gesundheitsdaten werden nur gemeldet.",
        "optionen": {"alle_geburtsdaten": False, "unbekannte_eigennamen": False, "bilder_schwaerzen": False},
    },
    "hoch": {
        "aktive": frozenset(_KERN | {"beruf", "arbeitgeber", "international", "ort"}),
        "hinweis": GESUNDHEIT,
        "beschreibung": "Empfohlen. Zusätzlich: Beruf, Arbeitgeber, ausländische Anschriften, Orte. "
                        "Gesundheitsdaten (Diagnosen, Medikamente) werden gemeldet und können angehakt werden.",
        "optionen": {"alle_geburtsdaten": False, "unbekannte_eigennamen": False, "bilder_schwaerzen": False},
    },
    "maximal": {
        "aktive": frozenset(_KERN | {"beruf", "arbeitgeber", "international", "ort"} | GESUNDHEIT),
        "hinweis": frozenset(),
        "beschreibung": "Größter Schutz, weniger Zusammenhang für die KI. Zusätzlich: Diagnosen, Medikamente, "
                        "alle plausiblen Geburtsdaten und unbekannte Eigennamen bei Personen.",
        "optionen": {"alle_geburtsdaten": True, "unbekannte_eigennamen": True, "bilder_schwaerzen": True},
    },
}
STANDARD_PROFIL = "hoch"


def profil(name: str | None) -> dict:
    """Eintrag einer Schutzstufe (unbekannt -> Standard „hoch“)."""
    return PROFILE.get(name or STANDARD_PROFIL) or PROFILE[STANDARD_PROFIL]


def hinweis_kategorien(profil_name: str | None, aktive) -> set:
    """Kategorien, die in dieser Schutzstufe erkannt, aber nur gemeldet und abgewählt angeboten werden
    (Gesundheitsdaten in „hoch“/„ausgewogen“) – ohne die, die die Nutzerin selbst angehakt hat."""
    return set(profil(profil_name).get("hinweis", ())) - set(aktive or ())


def option(profil_name: str | None, schluessel: str) -> bool:
    """Detektor-Option einer Schutzstufe (z. B. "alle_geburtsdaten")."""
    return bool(profil(profil_name).get("optionen", {}).get(schluessel, False))


# Hinweistexte je Quelle (für die Fundliste): Detektoren hängen ".lesefehler" an die Quelle, wenn die
# Prüfziffer nicht stimmt
QUELLEN_HINWEISE = {"lesefehler": HINWEIS_PRUEFZIFFER}


def quellen_hinweis(quelle: str) -> str | None:
    """Hinweis zu einer Treffer-Quelle ("muster.iban.lesefehler" -> "Prüfziffer ungültig (Lesefehler?)")."""
    return QUELLEN_HINWEISE.get((quelle or "").rsplit(".", 1)[-1])
