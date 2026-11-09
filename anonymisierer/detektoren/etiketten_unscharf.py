"""Unscharfe Etiketten auf OCR-Text: ein Feldbezeichner der Wissensbasis (daten/etiketten_*.txt) zählt auch dann,
wenn die OCR ihn verlesen hat – "Name, Vomame:", "Kundenntimmer 76183905", "Versicherungsmummen".

Regeln (nur für OCR-Text – die Aufrufer prüfen die Quelle der Zeichen im Seitenmodell):
  * Editierabstand 1 (Vertauschung zweier Nachbarn zählt 1), bei Etikettwörtern ab 12 Buchstaben 2.
  * Typische OCR-Verwechslungen mehrerer Zeichen kosten ebenfalls nur 1: "rn"/"m", "cl"/"d", "vv"/"w"
    ("Vomame" = "Vorname").
  * Personen- und Anschrift-Etiketten (ihr Wert hat keine feste Form) nur mit typischem Lesefehler: eine
    Ersetzung zählt dort nur innerhalb der OCR-Verwechslungsgruppen (i/l/j/t/f, n/m/u/h/r, e/c/o, v/y/w) –
    "Unfallart" ist ein anderes Wort, kein verlesener "Unfallort".
  * Nie für kurze Etiketten: Wörter unter 7 Buchstaben ("Name", "Ort", "Tel.", "Nr.") gelten nur exakt.
  * Ein Wort, das selbst ein bekanntes Wort ist (Allerweltswort, Vor-/Nachname, exaktes Etikettwort), ist kein
    verlesenes Etikett ("Strasser" ist ein Name, nicht "Strasse").
  * Das Etikett muss als Etikett stehen: Doppelpunkt dahinter, Zeilen-/Zellenende oder – bei Kennungen – eine
    Ziffernfolge dahinter ("Kundenntimmer 76183905").

Die Diakritika-Faltung der Wissensbasis gilt schon beim exakten Vergleich ("Gebürtsdatum" = "Geburtsdatum").
"""

from __future__ import annotations

import functools
import re

try:
    from .. import wissen as _wissen
except Exception:  # pragma: no cover - Wissensbasis fehlt
    _wissen = None

MIN_BUCHSTABEN = 7          # kürzere Etikettwörter nur exakt
LANG = 12                   # ab dieser Länge Abstand 2
_OCR_GRUPPEN = (("rn", "m"), ("cl", "d"), ("vv", "w"))
_WORT_RE = re.compile(r"[^\W\d_]+")
_ETIKETT_STELLUNG_RE = re.compile(r"[ \t]*(?:\([^()\n]{0,25}\)[ \t]*)?(?::|\t|\n|$)")
_ZIFFERN_DANACH_RE = re.compile(r"[ \t]*(?:-?[ \t]*(?:Nr\.?|Nummer)[ \t]*)?:?[ \t]*[A-Z]{0,4}[ \t./-]?\d{2}")
ARTEN = ("person", "kennung", "datum_geburt", "adresse", "kontakt", "vertragsdaten")
# Etiketten, deren Wert keine feste Form hat (Name, Ort, Straße): nur mit typischem OCR-Lesefehler
_NUR_STRENG = frozenset({"person", "adresse"})


def _kanon(wort: str) -> str:
    for alt, neu in _OCR_GRUPPEN:
        wort = wort.replace(alt, neu)
    return wort


# Zeichen, die die OCR untereinander verwechselt (Striche, Bögen, Rundungen): Ersetzungen innerhalb einer Gruppe
# sind typische Lesefehler, andere ("Unfallart"/"Unfallort", "Patienten"/"Patientin") eher ein anderes Wort
_OCR_GRUPPE = {}
for _gruppe in ("iljtf", "nmuhr", "eco", "vyw"):
    for _c in _gruppe:
        _OCR_GRUPPE[_c] = _gruppe


def _ersetzung(a: str, b: str, streng: bool) -> int:
    if a == b:
        return 0
    if not streng:
        return 1
    return 1 if _OCR_GRUPPE.get(a) is not None and _OCR_GRUPPE.get(a) == _OCR_GRUPPE.get(b) else 2


def _abstand(a: str, b: str, grenze: int, streng: bool = False) -> int:
    """Damerau-Levenshtein (Vertauschung benachbarter Zeichen = 1) mit Abbruch über `grenze`. streng=True:
    Ersetzungen außerhalb der OCR-Verwechslungsgruppen kosten 2."""
    if abs(len(a) - len(b)) > grenze:
        return grenze + 1
    vorvorher = None
    vorher = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        aktuell = [i] + [0] * len(b)
        kleinste = aktuell[0]
        for j in range(1, len(b) + 1):
            wert = min(vorher[j] + 1, aktuell[j - 1] + 1, vorher[j - 1] + _ersetzung(a[i - 1], b[j - 1], streng))
            if (vorvorher is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]):
                wert = min(wert, vorvorher[j - 2] + 1)
            aktuell[j] = wert
            kleinste = min(kleinste, wert)
        if kleinste > grenze:
            return grenze + 1
        vorvorher, vorher = vorher, aktuell
    return vorher[-1]


def ocr_abstand(wort: str, etikettwort: str, grenze: int = 2, streng: bool = False) -> int:
    """Abstand zweier (normalisierter) Wörter, OCR-Verwechslungen mehrerer Zeichen ("rn"/"m") kosten 1.
    streng=True: Ersetzungen außerhalb der OCR-Verwechslungsgruppen kosten 2 ("Unfallart" ist kein "Unfallort")."""
    d = _abstand(wort, etikettwort, grenze, streng)
    ka, kb = _kanon(wort), _kanon(etikettwort)
    if (ka, kb) != (wort, etikettwort) and ka != kb or (ka == kb and wort != etikettwort):
        d = min(d, _abstand(ka, kb, grenze, streng) + 1)
    return d


def _erlaubt(etikettwort: str) -> int:
    return 2 if len(etikettwort) >= LANG else 1


def _loeschungen(wort: str, tiefe: int) -> set:
    aus = {wort}
    rand = {wort}
    for _ in range(tiefe):
        neu = set()
        for w in rand:
            for i in range(len(w)):
                neu.add(w[:i] + w[i + 1:])
        aus |= neu
        rand = neu
    return aus


@functools.lru_cache(maxsize=1)
def _index() -> tuple:
    """(alle Etikettwörter normalisiert, Löschvarianten der kanonischen Form -> Etikettwörter)."""
    woerter = set()
    if _wissen is None:
        return frozenset(), {}
    for art in ARTEN:
        try:
            eintraege = _wissen.liste(f"etiketten_{art}")
        except Exception:
            continue
        for eintrag in eintraege:
            for w in _wissen.woerter(eintrag):
                woerter.add(_wissen.normalisieren(w))
    varianten: dict = {}
    for w in woerter:
        if len(w) < MIN_BUCHSTABEN or not w.isalpha():
            continue
        for v in _loeschungen(_kanon(w), _erlaubt(w)):
            varianten.setdefault(v, set()).add(w)
    return frozenset(woerter), varianten


@functools.lru_cache(maxsize=16384)
def etikettwort_fuer(wort: str):
    """(Etikettwort der Wissensbasis (normalisiert), Abstand, strenger Abstand) für ein verlesenes OCR-Wort – oder
    None (auch bei exakter Übereinstimmung, bei bekannten Wörtern und wenn zwei Etikettwörter gleich gut passen).
    Der strenge Abstand wertet Ersetzungen außerhalb der OCR-Verwechslungsgruppen doppelt."""
    if _wissen is None:
        return None
    n = _wissen.normalisieren(wort)
    if len(n) < MIN_BUCHSTABEN - 1 or not n.isalpha():
        return None
    woerter, varianten = _index()
    if n in woerter:
        return None
    try:
        titel = wort[:1].upper() + wort[1:].lower() if wort.isupper() else wort
        if _wissen.ist_allerweltswort(titel) or _wissen.ist_vorname(titel) or _wissen.ist_nachname(titel):
            return None
    except Exception:
        return None
    kandidaten = set()
    for v in _loeschungen(_kanon(n), 2 if len(n) >= LANG - 2 else 1):
        kandidaten |= varianten.get(v, set())
    beste, bester, gleichstand = None, (99, 99), False
    for w in kandidaten:
        erlaubt = _erlaubt(w)
        d = ocr_abstand(n, w, erlaubt)
        if d == 0 or d > erlaubt:
            continue
        guete = (ocr_abstand(n, w, erlaubt, streng=True), d)
        if guete < bester:
            beste, bester, gleichstand = w, guete, False
        elif guete == bester and w != beste:
            gleichstand = True
    if beste is None or gleichstand:
        return None
    return beste, bester[1], bester[0]


def unscharfe_etiketten(text: str, start: int = 0, ende: int | None = None) -> list:
    """Etiketten der Wissensbasis mit einem OCR-Lesefehler im Bereich [start, ende) des Texts:
    [(start, ende, art, eintrag)] mit Offsets im Text. Nur Stellen mit Etikett-Stellung (siehe Modulkopf)."""
    if _wissen is None or not text:
        return []
    ende = len(text) if ende is None else ende
    aus = []
    for zm in re.finditer(r"[^\n]+", text[start:ende]):
        z0 = start + zm.start()
        zeile = zm.group(0)
        for wm in _WORT_RE.finditer(zeile):
            treffer = etikettwort_fuer(wm.group(0))
            if treffer is None:
                continue
            ziel, abstand, streng = treffer
            korrigiert = zeile[:wm.start()] + ziel + zeile[wm.end():]
            verschiebung = len(ziel) - (wm.end() - wm.start())
            for art in ARTEN:
                if art in _NUR_STRENG and streng > _erlaubt(ziel):
                    continue                      # "Unfallart" ist kein verlesener "Unfallort"
                try:
                    vorkommen = _wissen.finde(korrigiert, f"etiketten_{art}")
                except Exception:
                    continue
                for v in vorkommen:
                    if not (v.start <= wm.start() and v.ende >= wm.start() + len(ziel)):
                        continue
                    s, e = z0 + v.start, z0 + v.ende - verschiebung
                    danach = text[e:min(len(text), e + 40)]
                    stellung = _ETIKETT_STELLUNG_RE.match(danach) is not None
                    if not stellung and not (art == "kennung" and _ZIFFERN_DANACH_RE.match(danach)):
                        continue
                    aus.append((s, e, art, v.eintrag))
    return aus
