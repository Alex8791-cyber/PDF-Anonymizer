"""Unscharfe Etiketten auf OCR-Text: ein Feldbezeichner der Wissensbasis (daten/etiketten_*.txt) zählt auch dann,
wenn die OCR ihn verlesen hat – "Name, Vomame:", "Kundenntimmer 76183905", "Geburtsdaturn:", "Anschrlft:".

Regeln (nur für OCR-Text – die Aufrufer prüfen die Quelle der Zeichen im Seitenmodell):
  * Es zählen nur TYPISCHE OCR-Lesefehler, für alle Arten von Etiketten gleich:
      - Ersetzung innerhalb einer Verwechslungsgruppe (i/l/j/t/f, n/m/u/h/r, e/c/o, v/y/w),
      - ein schmaler Strich zu viel oder zu wenig (i, l, j, t, f, r: "Verscherungsnchmer"),
      - Verwechslung mehrerer Zeichen: "rn"/"m", "cl"/"d", "vv"/"w", "ii"/"u", "ti"/"u" ("Vomame" = "Vorname").
    Ein Lesefehler bei Etikettwörtern unter 12 Buchstaben, zwei ab 12. Andere Abweichungen (fremde Buchstaben,
    Vertauschungen) machen ein anderes Wort: "Unfallart" ist kein verlesener "Unfallort", "Vertragssumme" keine
    "Vertragsnummer", "Patientenzimmer" keine "Patientennummer".
  * Nie für kurze Etiketten: Wörter unter 7 Buchstaben ("Name", "Ort", "Tel.", "Nr.") gelten nur exakt.
  * Nur großgeschriebene Wörter ("gehören" ist kein verlesenes "geboren").
  * Ein bekanntes Wort ist nie ein verlesenes Etikett: Allerweltswort, Vor-/Nachname, exaktes Etikettwort – und
    jedes Wort, das das Sprachmodell kennt (Wortvektor in de_core_news_md: "Schulter", "Pflege", "Patent",
    "Nachnahme", "Wasserzeichen", "Seitennummer"). OCR-Lesefehler sind fast nie echte Wörter. Ohne Sprachmodell
    gelten Personen- und Anschrift-Etiketten (Wert ohne feste Form) nur exakt.
  * Wörter für Beträge und Räume (…summe, …betrag, …zimmer, …kammer) sind nie verlesene Etiketten.
  * Das Etikett muss als Etikett stehen: Doppelpunkt dahinter, Zeilen-/Zellenende oder – bei Kennungen – eine
    Ziffernfolge dahinter ("Kundenntimmer 76183905").

Die Diakritika-Faltung der Wissensbasis gilt schon beim exakten Vergleich ("Gebürtsdatum" = "Geburtsdatum").
Verlesene Etiketten, die die KI für Namen hält ("Vomame:"), verwirft detektoren/ocr_lesart.py über
namen.verlesenes_etikett_statt_name – ebenfalls nur auf OCR-Text.
"""

from __future__ import annotations

import functools
import re

try:
    from .. import wissen as _wissen
except Exception:  # pragma: no cover - Wissensbasis fehlt
    _wissen = None

MIN_BUCHSTABEN = 7          # kürzere Etikettwörter nur exakt
LANG = 12                   # ab dieser Länge zwei Lesefehler
# Verwechslung mehrerer Zeichen (kostet 1): "Vomame" = "Vorname", "Kundenntimmer" = "Kundennummer"
_OCR_GRUPPEN = (("rn", "m"), ("cl", "d"), ("vv", "w"), ("ii", "u"), ("ti", "u"))
_WORT_RE = re.compile(r"[^\W\d_]+")
_ETIKETT_STELLUNG_RE = re.compile(r"[ \t]*(?:\([^()\n]{0,25}\)[ \t]*)?(?::|\t|\n|$)")
_ZIFFERN_DANACH_RE = re.compile(r"[ \t]*(?:-?[ \t]*(?:Nr\.?|Nummer)[ \t]*)?:?[ \t]*[A-Z]{0,4}[ \t./-]?\d{2}")
ARTEN = ("person", "kennung", "datum_geburt", "adresse", "kontakt", "vertragsdaten")
# Etiketten, deren Wert keine feste Form hat (Name, Ort, Straße): ohne Sprachmodell nur exakt
_OHNE_FESTE_FORM = frozenset({"person", "adresse"})
# Beträge und Räume: "Vertragssumme", "Erstattungsbetrag", "Dienstzimmer", "Versorgungskammer"
_KEIN_ETIKETT_ENDE = ("summe", "betrag", "zimmer", "kammer")
_UNTYPISCH = 3              # Kosten eines untypischen Schritts: mehr als je erlaubt


def _kanon(wort: str) -> str:
    for alt, neu in _OCR_GRUPPEN:
        wort = wort.replace(alt, neu)
    return wort


# Zeichen, die die OCR untereinander verwechselt (Striche, Bögen, Rundungen): Ersetzungen innerhalb einer Gruppe
# sind typische Lesefehler, andere ("Unfallart"/"Unfallort", "Patienten"/"Patientin") ein anderes Wort
_OCR_GRUPPE = {}
for _gruppe in ("iljtf", "nmuhr", "eco", "vyw"):
    for _c in _gruppe:
        _OCR_GRUPPE[_c] = _gruppe
# schmale Striche, die die OCR verliert oder hinzuliest
_DUENN = frozenset("iljtfr")


def _ersetzung(a: str, b: str) -> int:
    if a == b:
        return 0
    return 1 if _OCR_GRUPPE.get(a) is not None and _OCR_GRUPPE.get(a) == _OCR_GRUPPE.get(b) else _UNTYPISCH


def _einfuegen(c: str) -> int:
    return 1 if c in _DUENN else _UNTYPISCH


def _abstand(a: str, b: str, grenze: int) -> int:
    """Gewichteter Editierabstand (nur typische OCR-Lesefehler kosten 1, alles andere mehr als erlaubt) mit Abbruch
    über `grenze`."""
    if abs(len(a) - len(b)) > grenze:
        return grenze + 1
    vorher = [0]
    for j in range(1, len(b) + 1):
        vorher.append(vorher[-1] + _einfuegen(b[j - 1]))
    for i in range(1, len(a) + 1):
        aktuell = [vorher[0] + _einfuegen(a[i - 1])] + [0] * len(b)
        kleinste = aktuell[0]
        for j in range(1, len(b) + 1):
            wert = min(vorher[j] + _einfuegen(a[i - 1]), aktuell[j - 1] + _einfuegen(b[j - 1]),
                       vorher[j - 1] + _ersetzung(a[i - 1], b[j - 1]))
            aktuell[j] = wert
            kleinste = min(kleinste, wert)
        if kleinste > grenze:
            return grenze + 1
        vorher = aktuell
    return min(vorher[-1], grenze + 1)


def ocr_abstand(wort: str, etikettwort: str, grenze: int = 2) -> int:
    """Anzahl typischer OCR-Lesefehler zwischen zwei (normalisierten) Wörtern; grenze + 1, wenn ein untypischer
    Schritt nötig ist oder es mehr Fehler sind. Verwechslungen mehrerer Zeichen ("rn"/"m") zählen 1."""
    d = _abstand(wort, etikettwort, grenze)
    ka, kb = _kanon(wort), _kanon(etikettwort)
    if (ka, kb) != (wort, etikettwort):
        d = min(d, _abstand(ka, kb, grenze) + 1)
    return min(d, grenze + 1)


def _abstand_einfach(a: str, b: str, grenze: int) -> int:
    """Gewöhnlicher Editierabstand (jeder Schritt 1) mit Abbruch über `grenze` – nur für die nachsichtige Prüfung
    langer Wörter (siehe etikettwort_fuer)."""
    if abs(len(a) - len(b)) > grenze:
        return grenze + 1
    vorher = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        aktuell = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            aktuell[j] = min(vorher[j] + 1, aktuell[j - 1] + 1, vorher[j - 1] + (a[i - 1] != b[j - 1]))
        if min(aktuell) > grenze:
            return grenze + 1
        vorher = aktuell
    return min(vorher[-1], grenze + 1)


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


@functools.lru_cache(maxsize=1)
def _wortschatz():
    """(Schlüssel der Wortvektoren, Hash-Funktion) des Sprachmodells oder None (kein Modell, Modell ohne Vektoren)."""
    try:
        from ..namen import lade_ner
        nlp = lade_ner()
        if nlp is None:
            return None
        from spacy.strings import hash_string
        schluessel = nlp.vocab.vectors.key2row
        if not schluessel:
            return None                               # z. B. de_core_news_sm: keine Wortvektoren
    except Exception:
        return None
    return schluessel, hash_string


def sprachmodell_kennt(wort: str) -> bool | None:
    """Kennt das Sprachmodell das Wort (Wortvektor, auch klein oder mit großem Anfangsbuchstaben)? None ohne
    Wortschatz. Echte Wörter ("Schulter", "Vertragssumme") sind keine OCR-Lesefehler."""
    ws = _wortschatz()
    if ws is None:
        return None
    schluessel, h = ws
    for form in {wort, wort.lower(), wort[:1].upper() + wort[1:].lower()}:
        try:
            if h(form) in schluessel:
                return True
        except Exception:  # pragma: no cover - unerwartete Zeichen
            continue
    return False


@functools.lru_cache(maxsize=16384)
def etikettwort_fuer(wort: str, nachsichtig: bool = False):
    """(Etikettwort der Wissensbasis (normalisiert), Anzahl Lesefehler) für ein verlesenes OCR-Wort – oder None:
    bei exakter Übereinstimmung, bei bekannten Wörtern und Namen, bei kleingeschriebenen Wörtern, bei untypischen
    Abweichungen und wenn zwei Etikettwörter gleich gut passen (Regeln im Modulkopf).

    nachsichtig=True (nur für die Frage "verlesenes Etikett statt Name?", namen.verlesenes_etikett_statt_name): bei
    langen Wörtern (Wort und Etikettwort ab 12 Buchstaben, Komposita wie "Versicherungsnuarmmer") zählt jeder
    Lesefehler, nicht nur die typischen – Nachnamen dieser Länge, die nur zwei Zeichen neben einem Feldbezeichner
    liegen, gibt es praktisch nicht. Etiketten selbst (unscharfe_etiketten) bleiben streng."""
    if _wissen is None or not wort[:1].isupper():
        return None
    n = _wissen.normalisieren(wort)
    if len(n) < MIN_BUCHSTABEN - 1 or not n.isalpha() or n.endswith(_KEIN_ETIKETT_ENDE):
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
    beste, bester, gleichstand = None, 99, False
    for w in kandidaten:
        erlaubt = _erlaubt(w)
        d = ocr_abstand(n, w, erlaubt)
        if nachsichtig and d > erlaubt and len(n) >= LANG and len(w) >= LANG:
            d = min(_abstand_einfach(n, w, erlaubt), _abstand_einfach(_kanon(n), _kanon(w), erlaubt) + 1)
        if d == 0 or d > erlaubt:
            continue
        if d < bester:
            beste, bester, gleichstand = w, d, False
        elif d == bester and w != beste:
            gleichstand = True
    if beste is None or gleichstand:
        return None
    if sprachmodell_kennt(wort):
        return None                                   # ein echtes Wort, kein Lesefehler
    return beste, bester


def unscharfe_etiketten(text: str, start: int = 0, ende: int | None = None) -> list:
    """Etiketten der Wissensbasis mit einem OCR-Lesefehler im Bereich [start, ende) des Texts:
    [(start, ende, art, eintrag)] mit Offsets im Text. Nur Stellen mit Etikett-Stellung (siehe Modulkopf)."""
    if _wissen is None or not text:
        return []
    ende = len(text) if ende is None else ende
    aus = []
    mit_wortschatz = None
    for zm in re.finditer(r"[^\n]+", text[start:ende]):
        z0 = start + zm.start()
        zeile = zm.group(0)
        for wm in _WORT_RE.finditer(zeile):
            treffer = etikettwort_fuer(wm.group(0))
            if treffer is None:
                continue
            ziel = treffer[0]
            korrigiert = zeile[:wm.start()] + ziel + zeile[wm.end():]
            verschiebung = len(ziel) - (wm.end() - wm.start())
            for art in ARTEN:
                if art in _OHNE_FESTE_FORM:
                    if mit_wortschatz is None:
                        mit_wortschatz = _wortschatz() is not None
                    if not mit_wortschatz:
                        continue                      # ohne Sprachmodell: "Schulter" ließe sich nicht ausschließen
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
