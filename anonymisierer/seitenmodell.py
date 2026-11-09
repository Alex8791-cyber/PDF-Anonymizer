"""Seitenmodell: EIN logisches Textmodell für Analyse, Schwärzung und Selbstkontrolle.

Analyse, Schwärzung und Kontrolle der Ausgabe lesen ein PDF ausschließlich über dieses Modul:

    dokument_vorbereiten(doc)   Formularfelder lesen, einbrennen (bake), Seitendrehung entfernen,
                                ausgeblendete Ebenen sichtbar machen, /ActualText und /Alt entfernen
    dokument_aufbauen(doc, …)   Zeichen mit Koordinaten (Textebene, OCR, Bild-OCR) -> logischer Text
    seite_aufbauen(seite, …)    dasselbe für eine einzelne Seite (Selbstkontrolle der Ausgabe)
    dokument_aus_text(text)     Modell aus reinem Text (analysiere_text, Tests)
    ganzwort_stellen(…)         der gemeinsame Vergleicher (Ganzwort, Leerraum flexibel, drei Modi)

Regeln für den logischen Text (nur hier implementiert, für alle Nutzer identisch):
  * Zeichen in Lesereihenfolge aus get_text("rawdict") (Blöcke/Zeilen wie MuPDF), Zeilen durch "\\n".
    MuPDF zerlegt Tabellenzeilen und "Etikett   Wert"-Zeilen in eigene Zeilen je Zelle; Zeilen
    desselben Blocks auf derselben Grundlinie werden deshalb wieder zu EINER Zeile verbunden, getrennt
    durch zwei synthetische Tabulatoren ("\\t\\t" = Spaltengrenze, Abbildung -1).
  * Lücke > 1,5 x mittlere Zeichenbreite ohne Leerzeichen-Glyphe -> synthetisches "\\t".
  * Silbentrennung: Buchstabe + Trennstrich + Zeilenende + Kleinbuchstabe -> Trennstrich und Umbruch
    entfallen (verbunden[]); Großbuchstabe danach -> Bindestrich bleibt, nur der Umbruch entfällt
    ("Klein-Hoffmann"). Weiche Trennstriche (U+00AD) und Zeichen ohne Breite entfallen (verbunden[]).
  * Ligaturen (ﬀ ﬁ ﬂ ﬃ ﬄ ﬅ ﬆ) -> Einzelbuchstaben, alle auf dieselbe Glyphe abgebildet.
  * NBSP und andere Unicode-Leerzeichen -> " ", Unicode NFC (auch zerlegte Umlaute).
  * OCR: Wörter in Zeilen gruppiert, Zeichen = anteilige Teilrechtecke der Wortbox, Wörter durch " ",
    Zeilen durch "\\n"; OCR von Bildbereichen auf Textseiten als eigene Blöcke (quelle "bild").
  * Formularfelder (Widgets, vor bake() gelesen): der eingebrannte Wert steht im Modell direkt hinter
    seinem sichtbaren Etikett (gleiche Zeile links vom Feld, sonst darüber); Kammfelder ergeben EIN
    Wort. Dokument.felder liefert Feldname, Etikett, Wert und die Stelle im Seitentext.
  * Inhalte außerhalb des sichtbaren Seitenbereichs (CropBox) liefert MuPDF nicht; sie gehören nicht
    zum Modell und werden von der Schwärzung aus der Ausgabe ENTFERNT (Entscheidung zu Gutachten S-05).

Koordinaten: Seite nach page.remove_rotation() (bei Seiten mit /Rotate also in der gedrehten Ansicht).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from array import array
from bisect import bisect_left, bisect_right
from pathlib import Path
from typing import NamedTuple

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import ocr as _ocr

# ----------------------------------------------------------------------
# Konstanten
# ----------------------------------------------------------------------
TEXT_FLAGS = (fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
SEITENTRENNER = "\n\f\n"          # trennt die Seitentexte in Dokument.text
SPALTENTRENNER = "\t\t"           # synthetische Spaltengrenze (verbundene MuPDF-Zeilen, Formularwerte)
OCR_DPI = 300
OBERKANTE = 0.70                  # Schwärzungsrechteck: Anteil der Schriftgröße über der Grundlinie
UNTERKANTE = 0.02                 # … und unter der Grundlinie
OCR_RAND = 1.5                    # pt Rand um OCR-Wortboxen
LUECKE_TAB = 1.5                  # Lücke > 1,5 x mittlere Zeichenbreite ohne Leerzeichen -> "\t"
ETIKETT_ABSTAND = 250             # pt: so weit links vom Formularfeld darf sein Etikett stehen
ZEILEN_VEREINEN = True            # MuPDF-Zeilen gleicher Grundlinie eines Blocks verbinden

_LIGATUREN = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
              "ﬅ": "st", "ﬆ": "st"}
_OHNE_BREITE = frozenset("­​‌‍⁠﻿")
_TRENNSTRICHE = frozenset("-‐‑")
# Trennzeichen, die im Modus "kennung" zwischen Zeichengruppen flexibel sind ("DE89 3704" = "DE893704")
_KENNUNG_TRENNER = frozenset(" \t\n\r\f\v-./()‐‑–")
_KENNUNG_LAUF_RE = re.compile(r"[^\s\-./()‐‑–]+")
_NICHT_LEER_RE = re.compile(r"\S+")
_WORTLAUF_RE = re.compile(r"[^\W_]+")

MODI = ("name", "kennung", "begriff")
# Kategorie -> Vergleichsmodus (unbekannte Kategorien: "begriff")
KENNUNG_KATEGORIEN = frozenset({
    "iban", "email", "telefon", "vertrag", "svnr", "steuerid", "steuernr", "kvnr", "kindergeld", "kfz",
    "fin", "ausweis", "mandat", "bic", "kreditkarte", "geburt", "datum", "international",
})


def _rect_langsam(x0, y0, x1, y1):
    return fitz.Rect(x0, y0, x1, y1)


def _rect_schnell(x0, y0, x1, y1):
    """fitz.Rect ohne die (in PyMuPDF 2.x reine Python-)Argumentauswertung – ein Seitenmodell braucht
    zehntausende Rechtecke. Wird beim Import gegen den normalen Konstruktor geprüft."""
    r = _RECT_NEU(fitz.Rect)
    r.x0, r.y0, r.x1, r.y1 = float(x0), float(y0), float(x1), float(y1)
    return r


_RECT_NEU = fitz.Rect.__new__
try:
    _probe = _rect_schnell(1, 2, 3, 4)
    _rect = _rect_schnell if (_probe == fitz.Rect(1, 2, 3, 4) and abs(_probe) == 4.0
                              and (_probe | fitz.Rect(0, 0, 1, 1)) == fitz.Rect(0, 0, 3, 4)) else _rect_langsam
except Exception:  # anderes PyMuPDF-Innenleben: normaler Konstruktor
    _rect = _rect_langsam


def _box_von(rects):
    """Umschließendes Rechteck gültiger Rechtecke (ohne die langsame Rect-Vereinigung) oder None."""
    x0 = y0 = float("inf")
    x1 = y1 = float("-inf")
    for r in rects:
        if r.x1 > r.x0 and r.y1 > r.y0 and -1e6 < r.x0 < 1e6 and -1e6 < r.y0 < 1e6 and r.x1 < 1e6 and r.y1 < 1e6:
            if r.x0 < x0:
                x0 = r.x0
            if r.y0 < y0:
                y0 = r.y0
            if r.x1 > x1:
                x1 = r.x1
            if r.y1 > y1:
                y1 = r.y1
    if x1 < x0:
        return None
    return _rect(x0, y0, x1, y1)


def modus_fuer(kategorie: str) -> str:
    """Vergleichsmodus einer Kategorie: Namen "name", Kennungen/Daten "kennung", sonst "begriff"."""
    if kategorie == "namen":
        return "name"
    if kategorie in KENNUNG_KATEGORIEN:
        return "kennung"
    return "begriff"


class Abgebrochen(Exception):
    """Der Nutzer hat den Lauf abgebrochen (abbruch-Ereignis gesetzt)."""


# ----------------------------------------------------------------------
# Strukturtypen (Vertrag Abschnitt 1 und 12.1)
# ----------------------------------------------------------------------
class Zeichen(NamedTuple):
    c: str                 # genau ein Zeichen (die Glyphe, z. B. auch "ﬃ")
    rect: fitz.Rect        # Glyphenbox (Text) bzw. anteilige Wortbox (OCR)
    grundlinie: float      # y der Grundlinie (OCR: Unterkante der Wortbox)
    groesse: float         # Schriftgröße in pt (OCR: Höhe der Wortbox)
    zeile: int             # Zeilen-ID, eindeutig je Seite
    block: int             # Block-ID, eindeutig je Seite
    horizontal: bool
    quelle: str            # "text" | "ocr" | "bild"


class Zeile(NamedTuple):
    id: int
    block: int
    rect: fitz.Rect
    start: int             # Offset in Seite.text
    ende: int


class Block(NamedTuple):
    id: int
    rect: fitz.Rect
    zeilen: tuple
    quelle: str            # "text" | "ocr" | "bild"


class Feld(NamedTuple):
    seite: int             # 0-basiert
    name: str
    etikett: str           # sichtbarer Text links vom Feld bzw. darüber
    wert: str
    rect: fitz.Rect        # Feldrechteck (Koordinaten nach remove_rotation)
    start: int             # Stelle des eingebrannten Werts in Seite.text (-1, wenn nicht auffindbar)
    ende: int


# ----------------------------------------------------------------------
# Zeichen-Normalisierung (eine Regel für Seitentext und Suchtexte)
# ----------------------------------------------------------------------
_NORM_CACHE: dict = {}


def zeichen_normalisieren(c: str) -> str:
    """Glyphenzeichen -> Zeichen im logischen Text ('' = entfällt)."""
    n = _NORM_CACHE.get(c)
    if n is None:
        if c in _OHNE_BREITE:
            n = ""
        elif c in _LIGATUREN:
            n = _LIGATUREN[c]
        elif c == "\t":
            n = "\t"
        elif c.isspace():
            n = " "
        else:
            n = unicodedata.normalize("NFC", c)
        _NORM_CACHE[c] = n
    return n


_TRENN_LOESCHEN_RE = re.compile(r"(?<=[^\W\d_])[-‐‑][ \t]*\n[ \t\f]*(?=[^\W\d_])")


def suchtext_normalisieren(text: str) -> str:
    """Fundtext so normalisieren wie den Seitentext: Zeichenregeln (NFC, Ligaturen, Leerzeichen,
    weiche Trennstriche), Silbentrennung über einen Zeilenumbruch, Leerraum zusammengezogen."""
    if not text:
        return ""
    teile = []
    for c in unicodedata.normalize("NFC", text):
        if c == "\n":
            teile.append("\n")
        else:
            teile.append(zeichen_normalisieren(c))
    text = "".join(teile)

    def trennung(m):
        folgend = text[m.end()] if m.end() < len(text) else ""
        return "" if folgend.islower() else "-"
    text = _TRENN_LOESCHEN_RE.sub(trennung, text)
    return " ".join(text.split())


# ----------------------------------------------------------------------
# Vergleicher
# ----------------------------------------------------------------------
_FALT_CACHE: dict = {}


def _falte(c: str) -> str:
    """Groß-/Kleinschreibung einebnen: ß/ẞ -> 'ss', sonst ein Zeichen (längentreu)."""
    f = _FALT_CACHE.get(c)
    if f is None:
        if c.isspace():
            f = " "
        elif c in "ßẞ":
            f = "ss"
        else:
            f = c.casefold()
            if len(f) != 1:
                f = f[:1] or c
        _FALT_CACHE[c] = f
    return f


def _falte_text(teil: str, start: int, aus: list, pos: list):
    """Hängt den gefalteten Text eines Stücks ohne Leerraum an (mit Rückabbildung auf das Original)."""
    gefaltet = teil.casefold()
    if len(gefaltet) == len(teil) and "ß" not in teil:
        aus.append(gefaltet)
        pos.extend(range(start, start + len(teil)))
        return
    for j, c in enumerate(teil):
        f = _falte(c)
        aus.append(f)
        pos.extend([start + j] * len(f))


class _Nadel:
    """Vorbereiteter Suchtext für einen Modus."""
    __slots__ = ("gefaltet", "anfang_alnum", "ende_alnum", "gross", "genitiv", "trenner", "laenge_ok")

    def __init__(self, text: str, modus: str):
        n = suchtext_normalisieren(text)
        self.gross = ()
        self.genitiv = False
        self.trenner = ()
        if modus == "kennung":
            # Rand ohne Bedeutung (Klammern, Satzzeichen) abschneiden; "@" und "+" bleiben
            i, j = 0, len(n)
            while i < j and not (n[i].isalnum() or n[i] in "@+"):
                i += 1
            while j > i and not (n[j - 1].isalnum() or n[j - 1] in "@+"):
                j -= 1
            kern = n[i:j]
            teile, trenner = [], []
            vorher_trenner = False
            for c in kern:
                if c in _KENNUNG_TRENNER:
                    vorher_trenner = True
                    continue
                f = _falte(c)
                for k, fc in enumerate(f):
                    if teile:
                        trenner.append(vorher_trenner and k == 0)
                    teile.append(fc)
                vorher_trenner = False
            self.gefaltet = "".join(teile)
            self.trenner = tuple(trenner)        # trenner[k-1]: Trennzeichen vor Zeichen k
            kern_text = kern
        else:
            self.gefaltet = "".join(_falte(c) for c in n)
            kern_text = n
            if modus == "name":
                self.gross = tuple(lauf[0].isupper() for lauf in _WORTLAUF_RE.findall(n))
                letztes = n[-1:] or " "
                self.genitiv = letztes.isalpha() and letztes.lower() not in "sxzß"
        self.anfang_alnum = bool(kern_text) and kern_text[0].isalnum()
        self.ende_alnum = bool(kern_text) and kern_text[-1].isalnum()
        self.laenge_ok = any(c.isalnum() for c in kern_text)


class _Suchindex:
    """Je Text einmal: gefalteter Text mit zusammengezogenem Leerraum (Modi name/begriff) und ein
    'Skelett' ohne Trennzeichen (Modus kennung), beide mit Rückabbildung auf das Original. Treffer
    werden mit str.find gesucht und am Original bestätigt (keine Regex über den Gesamttext je Fund)."""

    def __init__(self, text: str):
        self.text = text
        falt, falt_pos = [], []
        letzte = 0
        for m in _NICHT_LEER_RE.finditer(text):
            if falt:                                # Leerraum zwischen zwei Stücken -> ein Leerzeichen
                falt.append(" ")
                falt_pos.append(letzte)
            _falte_text(m.group(0), m.start(), falt, falt_pos)
            letzte = m.end()
        self.falt = "".join(falt)
        self.falt_pos = falt_pos
        skel, skel_pos = [], []
        for m in _KENNUNG_LAUF_RE.finditer(text):
            _falte_text(m.group(0), m.start(), skel, skel_pos)
        self.skel = "".join(skel)
        self.skel_pos = skel_pos
        self._cache: dict = {}
        self._wortanfaenge: dict = {}      # Modus -> {erste 3 Zeichen: [Positionen von Wortanfängen]}

    _SCHLUESSEL_LAENGE = 3

    def _anfaenge(self, kennung: bool) -> dict:
        """Index der Wortanfänge im durchsuchten Text (nach den ersten Zeichen), damit eine Suche nur die
        Stellen prüft, an denen ihr erstes Wort steht – statt den ganzen Text je Fund (Gutachten PERF-01)."""
        index = self._wortanfaenge.get(kennung)
        if index is None:
            heu, pos = (self.skel, self.skel_pos) if kennung else (self.falt, self.falt_pos)
            text = self.text
            index = {}
            k = self._SCHLUESSEL_LAENGE
            for m in _WORTLAUF_RE.finditer(text):
                a = bisect_left(pos, m.start())
                if a < len(pos) and pos[a] == m.start():
                    index.setdefault(heu[a:a + k], []).append(a)
            self._wortanfaenge[kennung] = index
        return index

    def suche(self, fundtext: str, modus: str) -> list:
        schluessel = (fundtext, modus)
        treffer = self._cache.get(schluessel)
        if treffer is None:
            treffer = self._suchen(_nadel(fundtext, modus), modus)
            self._cache[schluessel] = treffer
        return treffer

    def suche_viele(self, fundtexte, modus: str) -> dict:
        """Viele Fundtexte auf einmal: Fundtexte mit denselben ersten Zeichen werden gemeinsam geprüft
        (je Kandidatenstelle ein Wörterbuch-Zugriff je vorkommender Länge) – linear auch dann, wenn
        tausende Nummern denselben Anfang haben (Vorwahl, IBAN-Bankleitzahl)."""
        ergebnis, gruppen = {}, {}
        k = self._SCHLUESSEL_LAENGE
        for t in dict.fromkeys(fundtexte):
            vorher = self._cache.get((t, modus))
            if vorher is not None:
                ergebnis[t] = vorher
                continue
            nadel = _nadel(t, modus)
            if nadel.anfang_alnum and len(nadel.gefaltet) >= k and nadel.laenge_ok:
                gruppen.setdefault(nadel.gefaltet[:k], []).append((t, nadel))
            else:
                ergebnis[t] = self.suche(t, modus)
        if not gruppen:
            return ergebnis
        heu = self.skel if modus == "kennung" else self.falt
        anfaenge = self._anfaenge(modus == "kennung")
        for schluessel, liste in gruppen.items():
            positionen = anfaenge.get(schluessel, ())
            nach_laenge: dict = {}
            for t, nadel in liste:
                nach_laenge.setdefault(len(nadel.gefaltet), {}).setdefault(nadel.gefaltet, []).append((t, nadel))
            kandidaten: dict = {}
            for laenge, je_text in nach_laenge.items():
                for a in positionen:
                    stueck = heu[a:a + laenge]
                    if stueck in je_text:
                        kandidaten.setdefault(stueck, []).append(a)
            for je_text in nach_laenge.values():
                for gefaltet, eintraege in je_text.items():
                    for t, nadel in eintraege:
                        treffer = self._pruefen(nadel, modus, kandidaten.get(gefaltet, ()))
                        self._cache[(t, modus)] = treffer
                        ergebnis[t] = treffer
        return ergebnis

    def _suchen(self, nadel: _Nadel, modus: str) -> list:
        if not nadel.gefaltet or not nadel.laenge_ok:
            return []
        heu = self.skel if modus == "kennung" else self.falt
        if nadel.anfang_alnum and len(nadel.gefaltet) >= self._SCHLUESSEL_LAENGE:
            # Kandidaten nur an Wortanfängen mit denselben ersten Zeichen
            nadel_text = nadel.gefaltet
            positionen = self._anfaenge(modus == "kennung").get(nadel_text[:self._SCHLUESSEL_LAENGE], ())
            if len(positionen) > 512:
                kandidaten = self._alle_vorkommen(heu, nadel_text)
            else:
                kandidaten = [a for a in positionen if heu.startswith(nadel_text, a)]
        else:
            kandidaten = self._alle_vorkommen(heu, nadel.gefaltet)
        return self._pruefen(nadel, modus, kandidaten)

    def _pruefen(self, nadel: _Nadel, modus: str, kandidaten) -> list:
        """Kandidaten (Positionen im durchsuchten Text, an denen die Nadel steht) am Original bestätigen."""
        text = self.text
        n = len(text)
        if modus == "kennung":
            heu, pos = self.skel, self.skel_pos
        else:
            heu, pos = self.falt, self.falt_pos
        lang = len(nadel.gefaltet)
        ergebnis = []
        for a in kandidaten:
            b = a + lang
            s, e = pos[a], pos[b - 1] + 1
            ok = True
            if a > 0 and pos[a - 1] == s:                 # Anfang mitten in einer Faltung (ß -> ss)
                ok = False
            elif b < len(pos) and pos[b] == pos[b - 1]:
                ok = False
            elif nadel.anfang_alnum and s > 0 and text[s - 1].isalnum():
                ok = False
            elif nadel.ende_alnum and e < n and text[e].isalnum():
                if (modus == "name" and nadel.genitiv and text[e] in "sS"
                        and (e + 1 == n or not text[e + 1].isalnum())):
                    e += 1
                else:
                    ok = False
            if ok and modus == "kennung" and nadel.trenner:
                ok = self._trenner_passen(nadel, a, heu, pos)
            if ok and modus == "name" and nadel.gross:
                laeufe = _WORTLAUF_RE.findall(text[s:e])
                if len(laeufe) == len(nadel.gross):
                    ok = all(lauf[0].isupper() or not gross for lauf, gross in zip(laeufe, nadel.gross))
            if ok:
                if ergebnis and s < ergebnis[-1][1]:
                    pass                                   # überlappt den vorigen Treffer
                else:
                    ergebnis.append((s, e))
        return ergebnis

    @staticmethod
    def _alle_vorkommen(heu: str, nadel: str):
        a = heu.find(nadel)
        while a >= 0:
            yield a
            a = heu.find(nadel, a + 1)

    @staticmethod
    def _trenner_passen(nadel: _Nadel, a: int, heu: str, pos: list) -> bool:
        """Modus kennung: Trennzeichen dürfen in der Art abweichen ("-" statt " "); fehlen oder
        hinzukommen dürfen sie nur zwischen Ziffern-Gruppen langer Kennungen (>= 8 Zeichen)."""
        lang_genug = len(nadel.gefaltet) >= 8
        for k, nadel_trenner in enumerate(nadel.trenner, start=1):
            text_trenner = pos[a + k] - pos[a + k - 1] > 1
            if text_trenner == nadel_trenner:
                continue
            if lang_genug and (heu[a + k - 1].isdigit() or heu[a + k].isdigit()):
                continue
            return False
        return True


_NADEL_CACHE: dict = {}


def _nadel(fundtext: str, modus: str) -> _Nadel:
    schluessel = (fundtext, modus)
    n = _NADEL_CACHE.get(schluessel)
    if n is None:
        if len(_NADEL_CACHE) > 50000:
            _NADEL_CACHE.clear()
        n = _NADEL_CACHE[schluessel] = _Nadel(fundtext, modus)
    return n


def _index_fuer(objekt) -> _Suchindex:
    if isinstance(objekt, str):
        return _Suchindex(objekt)
    idx = getattr(objekt, "_suchindex", None)
    if idx is None or idx.text is not objekt.text:
        idx = _Suchindex(objekt.text)
        try:
            objekt._suchindex = idx
        except AttributeError:
            pass
    return idx


def ganzwort_stellen(seite_oder_dokument, fundtext: str, modus: str = "name") -> list:
    """Alle Ganzwort-Stellen eines Fundtexts: [(start, ende)] im Text der Seite, des Dokuments
    (oder eines übergebenen str).

    - Leerraum im Fundtext passt auf beliebigen Leerraum (auch Zeilenumbruch, Tabulator).
    - Ganzwort: Zeichen davor/danach ist kein Buchstabe/keine Ziffer (str.isalnum()).
    - "name": Groß-/Kleinschreibung egal (auch ß = SS = ẞ), aber jedes Wort, das im Fundtext groß
      beginnt, muss auch im Dokument groß beginnen ("klein"/"groß" als Adjektiv bleiben stehen);
      Genitiv-s wird mitgenommen ("Mustermanns").
    - "kennung": Groß-/Kleinschreibung egal; Leerraum, Bindestrich, Punkt, Schrägstrich und Klammern
      zwischen Zeichengruppen sind austauschbar, zwischen Ziffern langer Kennungen auch verzichtbar
      ("DE89 3704" = "DE893704"); Ziffern exakt.
    - "begriff": wie eingegeben, Groß-/Kleinschreibung egal, Ganzwort.
    """
    if modus not in MODI:
        raise ValueError(f"unbekannter Vergleichsmodus: {modus!r}")
    if not fundtext or not fundtext.strip():
        return []
    return list(_index_fuer(seite_oder_dokument).suche(fundtext, modus))


def ganzwort_stellen_viele(seite_oder_dokument, fundtexte, modus: str = "name") -> dict:
    """Wie ganzwort_stellen für viele Fundtexte auf einmal: {fundtext: [(start, ende)]} – in Summe
    linear im Text (für die Weitergabe in der Analyse)."""
    if modus not in MODI:
        raise ValueError(f"unbekannter Vergleichsmodus: {modus!r}")
    texte = [t for t in fundtexte if t and t.strip()]
    ergebnis = _index_fuer(seite_oder_dokument).suche_viele(texte, modus)
    return {t: list(ergebnis.get(t, [])) for t in texte}


def fund_schluessel(text: str, modus: str) -> str:
    """Vergleichsschlüssel eines Fundtexts im Modus (gleiche Schlüssel = gleicher Fund)."""
    return _nadel(text, modus).gefaltet


# ----------------------------------------------------------------------
# Seite und Dokument
# ----------------------------------------------------------------------
class Seite:
    """Eine Seite des Modells: Zeichen mit Koordinaten und der logische Text mit Rückabbildung."""

    def __init__(self, nr, rect, zeichen, text, abbildung, verbunden, zeilen, bloecke, quelle, bilder,
                 wort_ids=None, ocr_boxen=None):
        self.nr = nr
        self.rect = fitz.Rect(rect)
        self.zeichen: list = zeichen
        self.text: str = text
        self.abbildung: list = abbildung
        self.verbunden: dict = verbunden
        self.zeilen: list = zeilen
        self.bloecke: list = bloecke
        self.quelle: str = quelle
        self.bilder: list = list(bilder or [])
        self.wort_ids: list = wort_ids if wort_ids is not None else [-1] * len(zeichen)
        self.ocr_boxen: list = ocr_boxen or []
        self.ocr_modus: str = "nein"          # "nein" | "seite" | "bilder"
        self.ocr_winkel = None                # erkannte Ausrichtung der Scan-Seite (Kontroll-OCR)
        self.ocr_woerter: int = 0             # Anzahl OCR-Wörter
        self.felder: list = []
        self._zeilen_start = [z.start for z in zeilen]
        self._fingerabdruck = None

    @property
    def fingerabdruck(self) -> str:
        """Hash über Text, Zeichenzahl, Glyphen und ihre Lage (Gleichheitsprüfung Analyse <-> Schwärzung)."""
        if self._fingerabdruck is None:
            self._fingerabdruck = _fingerabdruck_seite(self.text, self.zeichen)
        return self._fingerabdruck

    def __repr__(self):
        return f"<Seite {self.nr + 1}: {len(self.zeichen)} Zeichen, {len(self.zeilen)} Zeilen, {self.quelle}>"

    # -- Zuordnung Text <-> Glyphen --------------------------------------
    def glyphen(self, start: int, ende: int) -> list:
        """Glyphen-Indizes einer Textstelle, einschließlich entfallener Trennstriche/weicher Trennstriche."""
        idx = set()
        abb = self.abbildung
        for i in range(max(0, start), min(ende, len(abb))):
            g = abb[i]
            if g >= 0:
                idx.add(g)
        for g in list(idx):
            while g in self.verbunden:
                g = self.verbunden[g]
                if g in idx:
                    break
                idx.add(g)
        return sorted(idx)

    def rechtecke(self, start: int, ende: int) -> list:
        """Je Zeile der Stelle: (Schwärzungsrechteck, volle Box, Schriftgröße, Grundlinie oder None).

        Textebene: Rechteck von 0,70 x Schriftgröße über bis 0,02 x Schriftgröße unter der Grundlinie
        (Nachbarzeilen bleiben heil); über Bildern die volle Box + 1 pt (Pixel werden mitgelöscht).
        OCR: ganze Wortboxen der berührten Wörter + Rand (die Glyphenlage in der Box ist nur geschätzt)."""
        gruppen: dict = {}
        for g in self.glyphen(start, ende):
            gruppen.setdefault(self.zeichen[g].zeile, []).append(g)
        ergebnis = []
        for zid in sorted(gruppen):
            gs = gruppen[zid]
            erste = self.zeichen[gs[0]]
            if erste.quelle != "text":
                woerter = {self.wort_ids[g] for g in gs if self.wort_ids[g] >= 0}
                if not woerter:
                    continue
                box = _box_von(self.ocr_boxen[w] for w in woerter)
                if box is None:
                    continue
                r = fitz.Rect(box.x0 - OCR_RAND, box.y0 - OCR_RAND, box.x1 + OCR_RAND, box.y1 + OCR_RAND) & self.rect
                if r.is_empty:
                    continue
                ergebnis.append((r, fitz.Rect(box), box.height / 1.6, None))
                continue
            zs = [self.zeichen[g] for g in gs]
            sichtbar = [z for z in zs if not z.c.isspace() and _gueltig(z.rect)] or [z for z in zs if _gueltig(z.rect)]
            if not sichtbar:
                continue
            box = _box_von(z.rect for z in sichtbar)
            groesse = max(z.groesse for z in sichtbar)
            grundlinie = max(z.grundlinie for z in sichtbar)
            if all(z.horizontal for z in sichtbar) and groesse > 0:
                mit_groesse = [z for z in sichtbar if z.groesse > 0]
                oben = min(z.grundlinie - OBERKANTE * z.groesse for z in mit_groesse)
                unten = max(z.grundlinie + UNTERKANTE * z.groesse for z in mit_groesse)
                r = fitz.Rect(box.x0, max(box.y0, oben), box.x1, min(box.y1, unten))
                if r.is_empty or r.height < 0.3 * box.height:
                    r = fitz.Rect(box)
            else:
                r = fitz.Rect(box)
            if any(r.intersects(b) for b in self.bilder):
                # Text über einem Bild (z. B. unsichtbare Textebene eines Kopierers): Pixel ganz löschen
                r = fitz.Rect(box.x0 - 1, box.y0 - 1, box.x1 + 1, box.y1 + 1)
            ergebnis.append((r, fitz.Rect(box), groesse, grundlinie))
        return ergebnis

    def freiraum(self, start: int, ende: int, rect) -> tuple:
        """(x1 des vorigen, x0 des nächsten Buchstabens/Ziffer bzw. OCR-Worts) in der Zeile der Stelle –
        so weit darf ein Platzhalter wachsen; Satzzeichen dazwischen entfallen. None = frei."""
        eigene = set(self.glyphen(start, ende))
        if not eigene:
            return None, None
        zeilen_ids = {self.zeichen[g].zeile for g in eigene}
        links, rechts = [], []
        for zid in zeilen_ids:
            zeile = self.zeilen[zid] if zid < len(self.zeilen) else None
            if zeile is None:
                continue
            for g in self.glyphen(zeile.start, zeile.ende):
                if g in eigene:
                    continue
                z = self.zeichen[g]
                if not z.c.isalnum():
                    continue
                r = self.ocr_boxen[self.wort_ids[g]] if self.wort_ids[g] >= 0 else z.rect
                if r.x0 >= rect.x1 - 0.5:
                    rechts.append(r.x0)
                elif r.x1 <= rect.x0 + 0.5:
                    links.append(r.x1)
        return (max(links) if links else None), (min(rechts) if rechts else None)

    # -- Struktur ---------------------------------------------------------
    def zeile_von(self, pos: int):
        """Zeile, in der die Textposition liegt (bei Trennern die vorangehende Zeile)."""
        if not self.zeilen:
            return None
        i = bisect_right(self._zeilen_start, pos) - 1
        return self.zeilen[max(0, i)]

    def zeilen_im_bereich(self, rect) -> list:
        r = fitz.Rect(rect)
        return [z for z in self.zeilen if z.rect.intersects(r)]

    def woerter(self) -> list:
        """[(Rechteck, Text, start, ende)] aller Wörter (Folgen ohne Leerraum) der Seite."""
        aus = []
        for m in _NICHT_LEER_RE.finditer(self.text):
            teile = self.rechtecke(m.start(), m.end())
            box = _box_von(t[1] for t in teile)
            if box is None:
                continue
            aus.append((box, m.group(0), m.start(), m.end()))
        return aus

    def wort_an(self, punkt):
        """(start, ende) des Wortes unter einem Punkt (Seitenkoordinaten) oder None."""
        p = fitz.Point(punkt)
        for rect, _, start, ende in self.woerter():
            if rect.contains(p):
                return start, ende
        return None


class Dokument:
    """Das ganze Dokument: Seiten, verbundener Text (Seitentrenner "\\n\\f\\n"), Fingerabdruck, Felder."""

    def __init__(self, pfad, seiten: list, felder=None):
        self.pfad = Path(pfad) if pfad else None
        self.seiten = seiten
        self.felder: list = list(felder or [])
        self.seiten_start: list = []
        pos = 0
        for i, s in enumerate(seiten):
            if i:
                pos += len(SEITENTRENNER)
            self.seiten_start.append(pos)
            pos += len(s.text)
        self.text = SEITENTRENNER.join(s.text for s in seiten)
        self._fingerabdruck = None
        self.vorbereitung: dict = {}
        self.aus_text = False
        self.nie: list = []

    @property
    def fingerabdruck(self) -> str:
        """Hash über Seitenzahl und die Fingerabdrücke aller Seiten."""
        if self._fingerabdruck is None:
            h = hashlib.sha256(f"{len(self.seiten)}|".encode())
            for s in self.seiten:
                h.update(s.fingerabdruck.encode())
            self._fingerabdruck = h.hexdigest()
        return self._fingerabdruck

    def __repr__(self):
        return f"<Dokument {self.pfad.name if self.pfad else '(Text)'}: {len(self.seiten)} Seite(n)>"

    def seite(self, nr: int) -> Seite:
        return self.seiten[nr]

    def seite_von(self, pos: int) -> int:
        return max(0, bisect_right(self.seiten_start, pos) - 1)

    def lokal(self, start: int, ende: int) -> list:
        """[(seite_nr, lokal_start, lokal_ende)] einer Stelle im Dokumenttext (Seitentrenner fallen weg)."""
        aus = []
        if ende <= start:
            return aus
        for i in range(self.seite_von(start), len(self.seiten)):
            s0 = self.seiten_start[i]
            if s0 >= ende:
                break
            ls, le = max(start, s0) - s0, min(ende, s0 + len(self.seiten[i].text)) - s0
            if le > ls:
                aus.append((i, ls, le))
        return aus

    def global_(self, seite_nr: int, lokal_pos: int) -> int:
        return self.seiten_start[seite_nr] + lokal_pos


def _gueltig(r) -> bool:
    return r.x1 > r.x0 and r.y1 > r.y0 and -1e6 < r.x0 and r.x1 < 1e6 and -1e6 < r.y0 and r.y1 < 1e6


def _fingerabdruck_seite(text: str, zeichen: list) -> str:
    h = hashlib.sha256(f"{len(zeichen)}|{len(text)}|".encode())
    h.update(text.encode("utf-8", "surrogatepass"))
    werte = array("i", (int(round(v * 10)) if -1e8 < v < 1e8 else 0
                        for z in zeichen for v in (z.rect.x0, z.rect.y0)))
    h.update(werte.tobytes())
    h.update("".join(z.c for z in zeichen).encode("utf-8", "surrogatepass"))
    return h.hexdigest()


# ----------------------------------------------------------------------
# Rohzeilen (Zwischenstufe beim Aufbau)
# ----------------------------------------------------------------------
class _Rohzeile:
    """Eine Zeile vor dem Zusammensetzen: Inhalt = Rohzeichen (c, rect, grundlinie, groesse, wort_id)
    oder synthetische Zeichenketten (Spaltentrenner, Leerzeichen zwischen OCR-Wörtern)."""
    __slots__ = ("block", "inhalt", "horizontal", "quelle", "feld")

    def __init__(self, block, inhalt, horizontal=True, quelle="text"):
        self.block = block
        self.inhalt = inhalt
        self.horizontal = horizontal
        self.quelle = quelle
        self.feld = None                  # Index des Formularfelds, dessen Wert diese Zeile trägt

    def glyphen(self):
        return [el for el in self.inhalt if not isinstance(el, str)]

    def box(self):
        return _box_von(el[1] for el in self.inhalt if not isinstance(el, str))

    def grundlinie(self) -> float:
        werte = sorted(el[2] for el in self.inhalt if not isinstance(el, str) and not el[0].isspace())
        if not werte:
            werte = sorted(el[2] for el in self.inhalt if not isinstance(el, str))
        return werte[len(werte) // 2] if werte else 0.0

    def groesse(self) -> float:
        return max((el[3] for el in self.inhalt if not isinstance(el, str)), default=0.0)


def _mittlere_breite(zeichen) -> float:
    breiten = [r.width for c, r, *_ in zeichen if not c.isspace() and _gueltig(r) and r.width > 0]
    return sum(breiten) / len(breiten) if breiten else 0.0


def _textzeilen(seite, textpage=None) -> list:
    """Rohzeilen der Textebene (rawdict ohne Bilder), nur Zeichen im sichtbaren Seitenbereich."""
    try:
        if textpage is not None:
            rd = seite.get_text("rawdict", textpage=textpage)
        else:
            rd = seite.get_text("rawdict", flags=TEXT_FLAGS)
    except Exception:
        rd = {"blocks": []}
    sichtbar = seite.rect
    sx0, sy0, sx1, sy1 = sichtbar.x0 - 0.5, sichtbar.y0 - 0.5, sichtbar.x1 + 0.5, sichtbar.y1 + 0.5
    zeilen = []
    blocknr = -1
    for block in rd.get("blocks", ()):
        if block.get("type", 0) != 0:
            continue
        blocknr += 1
        for zeile in block.get("lines", ()):
            richtung = zeile.get("dir", (1, 0))
            horizontal = abs(richtung[1]) < 0.2 and zeile.get("wmode", 0) == 0
            roh = []
            breiten, n_breiten = 0.0, 0
            for span in zeile.get("spans", ()):
                groesse = float(span.get("size") or 0)
                for ch in span.get("chars", ()):
                    b = ch["bbox"]
                    mx, my = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                    if not (sx0 <= mx <= sx1 and sy0 <= my <= sy1):
                        continue
                    c = ch["c"]
                    roh.append((c, _rect(b[0], b[1], b[2], b[3]), float(ch["origin"][1]), groesse, -1))
                    if b[2] > b[0] and not c.isspace():
                        breiten += b[2] - b[0]
                        n_breiten += 1
            if not roh:
                continue
            inhalt = roh
            if horizontal and len(roh) > 1 and n_breiten:
                grenze = LUECKE_TAB * breiten / n_breiten
                inhalt = [roh[0]]
                for vor, akt in zip(roh, roh[1:]):
                    if akt[1].x0 - vor[1].x1 > grenze and not vor[0].isspace() and not akt[0].isspace():
                        inhalt.append("\t")
                    inhalt.append(akt)
            zeilen.append(_Rohzeile(blocknr, inhalt, horizontal, "text"))
    return zeilen


def _zeilen_vereinen(zeilen: list) -> list:
    """Aufeinanderfolgende MuPDF-Zeilen desselben Blocks auf derselben Grundlinie (Tabellenzellen,
    'Etikett    Wert') zu einer Zeile verbinden – mit Spaltentrenner bei breiter Lücke."""
    if not ZEILEN_VEREINEN:
        return zeilen
    aus = []
    v_box = v_grund = v_groesse = None        # Werte der letzten Zeile in aus (einmal berechnet)
    for z in zeilen:
        z_box = z.box()
        z_grund, z_groesse = z.grundlinie(), z.groesse()
        if aus and v_box is not None and z_box is not None:
            v = aus[-1]
            if (v.block == z.block and v.horizontal and z.horizontal and v.quelle == z.quelle == "text"
                    and v.feld is None and z.feld is None):
                groesse = max(v_groesse, z_groesse, 1.0)
                if abs(v_grund - z_grund) <= 0.25 * groesse and z_box.x0 >= v_box.x1 - 1.0:
                    luecke = z_box.x0 - v_box.x1
                    if luecke > 0.6 * groesse:
                        v.inhalt.append(SPALTENTRENNER)
                    elif luecke > 0.15 * groesse:
                        v.inhalt.append(" ")
                    v.inhalt.extend(z.inhalt)
                    v_box = _rect(min(v_box.x0, z_box.x0), min(v_box.y0, z_box.y0),
                                  max(v_box.x1, z_box.x1), max(v_box.y1, z_box.y1))
                    v_groesse = max(v_groesse, z_groesse)
                    continue
        aus.append(z)
        v_box, v_grund, v_groesse = z_box, z_grund, z_groesse
    return aus


# ----------------------------------------------------------------------
# OCR-Wörter -> Rohzeilen
# ----------------------------------------------------------------------
def woerter_zu_zeilen(woerter) -> list:
    """OCR-Wörter (5- oder 8-Tupel) zu Zeilen gruppieren: Liste von Zeilen (Wörter nach x sortiert).

    Bevorzugt ocr.woerter_zu_zeilen (eine Heuristik für alle). Sonst: 8-Tupel nach der Zeilennummer
    der OCR (Block, Zeile), 5-Tupel über die Lage – Toleranz aus dem Zeilenabstand der Seite statt aus
    der Worthöhe, Zeilenmitte als Mittelwert ohne Drift (Gutachten EQ-01: OCR-Wortkästen sind oft
    höher als der Zeilenabstand; eine höhenbasierte Toleranz verschmilzt Nachbarzeilen)."""
    woerter = [w for w in (woerter or []) if len(w) >= 5 and str(w[4]).strip()]
    if not woerter:
        return []
    fremd = getattr(_ocr, "woerter_zu_zeilen", None)
    if fremd is not None and fremd is not woerter_zu_zeilen:
        try:
            return [list(z) for z in fremd(woerter) if z]      # Lesefolge (auch gedrehte Scans) beibehalten
        except Exception:
            pass
    if all(len(w) >= 8 for w in woerter):
        # Zeilen und Wortfolge der OCR (Lesefolge, auch bei gedrehten Scans)
        gruppen: dict = {}
        for w in woerter:
            gruppen.setdefault((w[5], w[6]), []).append(w)
        return [sorted(gruppen[k], key=lambda w: w[7]) for k in sorted(gruppen)]
    mitten = sorted({round((w[1] + w[3]) / 2, 1) for w in woerter})
    hoehen = sorted(max(w[3] - w[1], 1.0) for w in woerter)
    toleranz = hoehen[len(hoehen) // 2] * 0.5
    abstaende = sorted(b - a for a, b in zip(mitten, mitten[1:]) if b - a > 1.5)
    if abstaende:
        toleranz = min(toleranz, abstaende[len(abstaende) // 2] * 0.45)
    toleranz = max(toleranz, 1.5)
    sortiert = sorted(woerter, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    zeilen, aktuelle, summe = [], [], 0.0
    for w in sortiert:
        m = (w[1] + w[3]) / 2
        if aktuelle and abs(m - summe / len(aktuelle)) > toleranz:
            zeilen.append(sorted(aktuelle, key=lambda x: x[0]))
            aktuelle, summe = [], 0.0
        aktuelle.append(w)
        summe += m
    if aktuelle:
        zeilen.append(sorted(aktuelle, key=lambda x: x[0]))
    return zeilen


def _ocr_zeilen(woerter, quelle: str, block_start: int, ocr_boxen: list) -> list:
    """Rohzeilen aus OCR-Wörtern; Blöcke über vertikale Lücken; Zeichen = anteilige Teilrechtecke."""
    zeilen = []
    block = block_start
    vorige = None
    for gruppe in woerter_zu_zeilen(woerter):
        boxen = [_rect(min(w[0], w[2]), min(w[1], w[3]), max(w[0], w[2]), max(w[1], w[3])) for w in gruppe]
        oben = min(b.y0 for b in boxen)
        unten = max(b.y1 for b in boxen)
        hoehe = max(unten - oben, 1.0)
        if vorige is not None and (oben - vorige[1] > 1.2 * hoehe or unten < vorige[0]):
            block += 1
        vorige = (oben, unten)
        inhalt = []
        for j, (w, box) in enumerate(zip(gruppe, boxen)):
            if j:
                inhalt.append(" ")
            wort_id = len(ocr_boxen)
            ocr_boxen.append(box)
            text = str(w[4])
            n = len(text)
            breite = box.width / n if n else box.width
            for i, c in enumerate(text):
                r = _rect(box.x0 + i * breite, box.y0, box.x0 + (i + 1) * breite, box.y1)
                inhalt.append((c, r, box.y1, box.y1 - box.y0, wort_id))
        zeilen.append(_Rohzeile(block, inhalt, True, quelle))
    return zeilen


# ----------------------------------------------------------------------
# Formularfelder
# ----------------------------------------------------------------------
def _feldzeilen_einordnen(zeilen: list, felder_roh: list) -> tuple:
    """Zieht die eingebrannten Werte der Formularfelder aus dem Seitentext (MuPDF hängt sie ans
    Seitenende) und stellt sie hinter ihr Etikett. Kammfelder werden zu EINEM Wort.
    Rückgabe: (Zeilen, {Feldindex: Etikett})."""
    etiketten: dict = {}
    if not felder_roh:
        return zeilen, etiketten
    for fi, feld in enumerate(felder_roh):
        r = fitz.Rect(feld["rect"])
        if r.is_empty or not feld.get("wert"):
            continue
        innen = fitz.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 1, r.y1 + 1)

        def drin(el, innen=innen):
            return not isinstance(el, str) and innen.contains(fitz.Point((el[1].x0 + el[1].x1) / 2,
                                                                           (el[1].y0 + el[1].y1) / 2))
        wert_kompakt = "".join(feld["wert"].split()).casefold()

        def gehoert_zum_wert(z, wert_kompakt=wert_kompakt):
            t = "".join(el[0] for el in z.glyphen() if not el[0].isspace()).casefold()
            return bool(t) and (t in wert_kompakt or wert_kompakt in t)
        feldzeilen = [z for z in zeilen if z.feld is None and z.quelle == "text" and z.glyphen()
                      and all(drin(el) for el in z.glyphen()) and gehoert_zum_wert(z)]
        if not feldzeilen:
            continue
        for z in feldzeilen:
            zeilen.remove(z)
        if feld.get("kamm"):
            glyphen = [el for z in feldzeilen for el in z.glyphen() if not el[0].isspace()]
            horizontal = feldzeilen[0].horizontal
            glyphen.sort(key=lambda el: (el[1].x0, el[1].y0) if horizontal else (el[1].y0, el[1].x0))
            feldzeilen = [_Rohzeile(feldzeilen[0].block, glyphen, horizontal, "text")]
        marke = -(fi + 2)                 # Glyphen des Feldwerts markieren (wort_id <= -2 = Feldindex)
        for z in feldzeilen:
            z.inhalt = [el if isinstance(el, str) else (el[0], el[1], el[2], el[3], marke) for el in z.inhalt]
            z.feld = fi
        # Etikett: dieselbe Zeile links vom Feld (nächstes Textstück), sonst die Zeile direkt darüber
        mitte_y = (r.y0 + r.y1) / 2
        beste, beste_x = None, None
        for z in zeilen:
            if z.feld is not None or z.quelle != "text" or not z.horizontal or not feldzeilen[0].horizontal:
                continue
            links = [el for el in z.glyphen() if el[1].x1 <= r.x0 + 2 and el[1].x0 >= r.x0 - ETIKETT_ABSTAND
                     and el[1].y0 - 2 <= mitte_y <= el[1].y1 + 2 and not el[0].isspace()]
            if links:
                x = max(el[1].x1 for el in links)
                if beste_x is None or x > beste_x:
                    beste, beste_x = z, x
        if beste is not None:
            links = sorted((el for el in beste.glyphen() if el[1].x1 <= r.x0 + 2
                            and el[1].y0 - 2 <= mitte_y <= el[1].y1 + 2), key=lambda el: el[1].x0)
            # nächstes zusammenhängendes Stück links vom Feld
            stueck = []
            for el in reversed(links):
                if stueck and stueck[-1][1].x0 - el[1].x1 > max(12.0, 1.2 * (el[3] or 10)):
                    break
                stueck.append(el)
            etiketten[fi] = "".join(el[0] for el in reversed(stueck)).strip()
            # Wert an der richtigen x-Position in die Etikett-Zeile einfügen
            ziel = beste.inhalt
            pos = len(ziel)
            for i, el in enumerate(ziel):
                if not isinstance(el, str) and el[1].x0 >= r.x0 - 0.5:
                    pos = i
                    break
            einfuegen = [SPALTENTRENNER] + feldzeilen[0].inhalt
            if pos < len(ziel):
                einfuegen.append(SPALTENTRENNER)
            ziel[pos:pos] = einfuegen
            i = zeilen.index(beste)
            for k, z in enumerate(feldzeilen[1:], start=1):
                zeilen.insert(i + k, z)
            continue
        # Etikett darüber (x-Überlappung, höchstens 1,5 Feldhöhen Abstand)
        darueber, abstand = None, None
        for z in zeilen:
            if z.feld is not None or z.quelle != "text":
                continue
            zb = z.box()
            if zb is None or zb.y1 > r.y0 + 1 or zb.x1 < r.x0 or zb.x0 > r.x1:
                continue
            d = r.y0 - zb.y1
            if d <= 1.5 * max(r.height, 10) and (abstand is None or d < abstand):
                darueber, abstand = z, d
        if darueber is not None:
            etiketten[fi] = "".join(el[0] for el in darueber.glyphen()).strip()
            i = zeilen.index(darueber)
            for k, z in enumerate(feldzeilen, start=1):
                zeilen.insert(i + k, z)
        else:
            zeilen.extend(feldzeilen)
    return zeilen, etiketten


# ----------------------------------------------------------------------
# Zusammensetzen
# ----------------------------------------------------------------------
def _verbinden(verbunden: dict, von: int, zu: int):
    """Glyphe `zu` (entfällt im Text) an Glyphe `von` hängen (Kette, falls `von` schon etwas trägt)."""
    gesehen = set()
    while von in verbunden and von not in gesehen:
        gesehen.add(von)
        von = verbunden[von]
    if von != zu:
        verbunden[von] = zu


def _umbruch_passt(zeichen: list, einheiten: list, ende: int, folge: list) -> bool:
    """Ist das Zeilenende bei einheiten[ende-1] ein echter Zeilenumbruch in den Folgetext? Die Folgezeile
    muss links vom Trennstrich beginnen und ungefähr dort, wo das getrennte Textstück (nach der letzten
    Spaltengrenze) beginnt – sonst ist es eine Tabellenzelle ("Versicherungsschein-" im Tabellenkopf)."""
    g_ende = einheiten[ende - 1][1]
    folge_g = next((g for ch, g in folge if g >= 0 and not ch.isspace()), None)
    if g_ende < 0 or folge_g is None:
        return True
    letzte, naechste = zeichen[g_ende], zeichen[folge_g]
    if not (letzte.horizontal and naechste.horizontal):
        return True
    k = ende - 1
    while k > 0 and einheiten[k - 1][0] != "\t":
        k -= 1
    seg_g = next((g for ch, g in einheiten[k:ende] if g >= 0 and not ch.isspace()), None)
    if seg_g is None:
        return True
    groesse = letzte.groesse or 10.0
    nx0 = naechste.rect.x0
    return nx0 < letzte.rect.x0 and nx0 >= zeichen[seg_g].rect.x0 - max(3 * groesse, 30.0)


def _zusammensetzen(zeilen: list) -> tuple:
    """Rohzeilen -> (zeichen, wort_ids, text, abbildung, verbunden, Zeilen, Blöcke, Feld-Glyphen)."""
    zeichen: list = []
    wort_ids: list = []
    verbunden: dict = {}
    einheiten_je_zeile = []
    feld_glyphen: dict = {}
    norm_cache = _NORM_CACHE
    neues_zeichen = Zeichen
    for zid, rz in enumerate(zeilen):
        einheiten = []           # (Textzeichen, Glyphenindex oder -1)
        weich_am_ende = False
        letzte = -1
        block, horizontal, quelle = rz.block, rz.horizontal, rz.quelle
        for el in rz.inhalt:
            if el.__class__ is str:
                einheiten.extend((ch, -1) for ch in el)
                continue
            c, rect, grund, groesse, wort_id = el
            g = len(zeichen)
            zeichen.append(neues_zeichen(c, rect, grund, groesse, zid, block, horizontal, quelle))
            if wort_id <= -2:                          # Glyphe eines Formularfeldwerts
                feld_glyphen.setdefault(-wort_id - 2, []).append(g)
                wort_id = -1
            wort_ids.append(wort_id)
            n = norm_cache.get(c)
            if n is None:
                n = zeichen_normalisieren(c)
            if len(n) == 1 and n.isalnum():          # häufigster Fall: Buchstabe/Ziffer
                einheiten.append((n, g))
                letzte = g
                weich_am_ende = False
                continue
            if not n:
                if letzte >= 0:
                    _verbinden(verbunden, letzte, g)
                weich_am_ende = c == "­"
                continue
            if (len(n) == 1 and unicodedata.combining(n) and einheiten and einheiten[-1][1] >= 0
                    and not einheiten[-1][0].isspace()):
                komp = unicodedata.normalize("NFC", einheiten[-1][0] + n)
                if len(komp) == 1:
                    einheiten[-1] = (komp, einheiten[-1][1])
                    _verbinden(verbunden, einheiten[-1][1], g)
                    continue
            for ch in n:
                einheiten.append((ch, g))
            letzte = g
            if not n.isspace():
                weich_am_ende = False
        einheiten_je_zeile.append((einheiten, weich_am_ende))

    text: list = []
    abb: list = []
    zeilen_aus: list = []
    ueberspringen = False            # führenden Leerraum der Folgezeile überspringen (nach Verbinden)
    for zid, (einheiten, weich) in enumerate(einheiten_je_zeile):
        rz = zeilen[zid]
        i0 = 0
        if ueberspringen:
            while i0 < len(einheiten) and einheiten[i0][0].isspace():
                i0 += 1
        ueberspringen = False
        einheiten = einheiten[i0:]
        verbindung = "\n"
        if zid + 1 < len(einheiten_je_zeile) and zeilen[zid + 1].quelle == rz.quelle:
            folge = einheiten_je_zeile[zid + 1][0]
            naechstes = next((ch for ch, _ in folge if not ch.isspace()), "")
            ende = len(einheiten)
            while ende > 0 and einheiten[ende - 1][0] in " \t":
                ende -= 1
            if naechstes.isalpha() and ende >= 1 and _umbruch_passt(zeichen, einheiten, ende, folge):
                if (ende >= 2 and einheiten[ende - 1][0] in _TRENNSTRICHE and einheiten[ende - 1][1] >= 0
                        and einheiten[ende - 2][0].isalpha()):
                    if naechstes.islower():
                        # Silbentrennung: Trennstrich und Umbruch entfallen
                        if einheiten[ende - 2][1] >= 0:
                            _verbinden(verbunden, einheiten[ende - 2][1], einheiten[ende - 1][1])
                        einheiten = einheiten[:ende - 1]
                    else:
                        einheiten = einheiten[:ende]        # "Klein-" + "Hoffmann": nur Umbruch weg
                    verbindung = ""
                elif weich and ende >= 1 and einheiten[ende - 1][0].isalpha():
                    einheiten = einheiten[:ende]
                    verbindung = ""
            if verbindung == "":
                ueberspringen = True
        start = len(text)
        for ch, g in einheiten:
            text.append(ch)
            abb.append(g)
        ende_pos = len(text)
        box = rz.box() or fitz.Rect()
        zeilen_aus.append(Zeile(zid, rz.block, box, start, ende_pos))
        if verbindung and zid + 1 < len(einheiten_je_zeile):
            text.append(verbindung)
            abb.append(-1)
    bloecke: dict = {}
    for z in zeilen_aus:
        b = bloecke.get(z.block)
        if b is None:
            bloecke[z.block] = [[z.rect], [z.id], zeilen[z.id].quelle]
        else:
            b[0].append(z.rect)
            b[1].append(z.id)
    block_liste = [Block(bid, _box_von(rs) or fitz.Rect(), tuple(ids), q)
                   for bid, (rs, ids, q) in sorted(bloecke.items())]
    return zeichen, wort_ids, "".join(text), abb, verbunden, zeilen_aus, block_liste, feld_glyphen


def _seite_aus_zeilen(nr, rect, zeilen, bilder=(), ocr_boxen=None, felder_roh=(), etiketten=None) -> Seite:
    zeichen, wort_ids, text, abb, verbunden, zeilen_aus, bloecke, feld_glyphen = _zusammensetzen(zeilen)
    quellen = {z.quelle for z in zeilen}
    if not quellen or quellen == {"text"}:
        quelle = "text"
    elif "text" in quellen:
        quelle = "gemischt"
    else:
        quelle = "ocr"
    seite = Seite(nr, rect, zeichen, text, abb, verbunden, zeilen_aus, bloecke, quelle, bilder,
                  wort_ids=wort_ids, ocr_boxen=ocr_boxen or [])
    # Formularfelder: Stelle des eingebrannten Werts im Seitentext
    if felder_roh:
        erste: dict = {}
        letzte: dict = {}
        for i, g in enumerate(abb):
            if g >= 0:
                erste.setdefault(g, i)
                letzte[g] = i
        etiketten = etiketten or {}
        for fi, feld in enumerate(felder_roh):
            gs = feld_glyphen.get(fi, [])
            positionen = [erste[g] for g in gs if g in erste] + [letzte[g] for g in gs if g in letzte]
            start, ende = (min(positionen), max(positionen) + 1) if positionen else (-1, -1)
            seite.felder.append(Feld(nr, feld.get("name") or "", etiketten.get(fi, ""), feld.get("wert") or "",
                                     fitz.Rect(feld["rect"]), start, ende))
    return seite


def seite_aufbauen(seite, nr: int, ocr_woerter=None, ocr_quelle: str = "ocr", felder_roh=(), bilder=None,
                   textpage=None) -> Seite:
    """Modell einer (vorbereiteten) PDF-Seite: Textebene, Formularwerte hinter ihren Etiketten,
    dahinter die OCR-Wörter (quelle "ocr" bei Scans, "bild" bei Bildbereichen einer Textseite)."""
    zeilen = _textzeilen(seite, textpage)
    zeilen, etiketten = _feldzeilen_einordnen(zeilen, list(felder_roh or []))
    zeilen = _zeilen_vereinen(zeilen)
    ocr_boxen: list = []
    if ocr_woerter:
        block_start = max((z.block for z in zeilen), default=-1) + 1
        zeilen += _ocr_zeilen(ocr_woerter, ocr_quelle, block_start, ocr_boxen)
    return _seite_aus_zeilen(nr, seite.rect, zeilen, bilder or [], ocr_boxen, felder_roh, etiketten)


# ----------------------------------------------------------------------
# Vorbereitung
# ----------------------------------------------------------------------
_PROPERTIES_NAME_RE = re.compile(rb"(/[^\s/<>\[\]()]+)\s+/[^\s/<>\[\]()]+\s+BDC")
_MARKIERUNGS_SCHLUESSEL_RE = re.compile(rb"/(?:ActualText|Alt)(?![A-Za-z0-9_])")
_XREF_RE = re.compile(rb"(\d+)\s+0\s+R")


def _pdf_string_ende(strom: bytes, i: int):
    """Ende (exklusiv) der PDF-Zeichenkette ab i: (…) mit Klammertiefe und Escapes oder <…>."""
    if strom[i:i + 1] == b"(":
        tiefe, j = 0, i
        while j < len(strom):
            c = strom[j:j + 1]
            if c == b"\\":
                j += 2
                continue
            if c == b"(":
                tiefe += 1
            elif c == b")":
                tiefe -= 1
                if tiefe == 0:
                    return j + 1
            j += 1
        return None
    if strom[i:i + 1] == b"<":
        j = strom.find(b">", i)
        return None if j < 0 else j + 1
    return None


def markierungen_entfernen(strom: bytes) -> bytes:
    """/ActualText (…) und /Alt (…) aus einem Inhaltsstrom entfernen (auch geschachtelte Klammern);
    benannte Properties hinter BDC (/Span /MC0 BDC) durch ein leeres Wörterbuch ersetzen – auch dort
    kann ActualText stehen (Gutachten S-06)."""
    teile, pos = [], 0
    for m in _MARKIERUNGS_SCHLUESSEL_RE.finditer(strom):
        if m.start() < pos:
            continue
        j = m.end()
        while j < len(strom) and strom[j:j + 1] in b" \t\r\n\x0c\x00":
            j += 1
        ende = _pdf_string_ende(strom, j)
        if ende is None:
            continue
        teile.append(strom[pos:m.start()])
        pos = ende
    teile.append(strom[pos:])
    return _PROPERTIES_NAME_RE.sub(rb"\1 <<>> BDC", b"".join(teile))


def _xobjekte_rekursiv(doc, seite) -> list:
    gesehen, stapel = [], []
    try:
        stapel = [x[0] for x in seite.get_xobjects()]
    except Exception:
        pass
    while stapel:
        x = stapel.pop()
        if x in gesehen or x <= 0:
            continue
        gesehen.append(x)
        try:
            art, wert = doc.xref_get_key(x, "Resources/XObject")
            if art == "xref":
                wert = doc.xref_object(int(wert.split()[0]))
            if art in ("dict", "xref"):
                stapel += [int(n) for n in _XREF_RE.findall(wert.encode("latin-1", "replace"))]
        except Exception:
            pass
    return gesehen


def _markierungen_bereinigen(doc) -> int:
    """Entfernt /ActualText und /Alt aus Seiteninhalten und allen (auch verschachtelten) Form-XObjects:
    beides kann Klartext tragen und lenkt die Textextraktion von den echten Glyphen weg."""
    geaendert = 0
    for seite in doc:
        for xref in list(seite.get_contents()) + _xobjekte_rekursiv(doc, seite):
            try:
                strom = doc.xref_stream(xref)
            except Exception:
                continue
            if strom and b"BDC" in strom:
                neu = markierungen_entfernen(strom)
                if neu != strom:
                    doc.update_stream(xref, neu)
                    geaendert += 1
    return geaendert


def _schluessel_vorhanden(doc, xref, schluessel) -> bool:
    try:
        return doc.xref_get_key(xref, schluessel)[0] != "null"
    except Exception:
        return False


def nebenkanaele_zaehlen(doc) -> dict:
    """Zähler der Nebenkanäle (vor dem Einbrennen ermittelt)."""
    z = {"formularfelder": 0, "anmerkungen": 0, "links": 0, "lesezeichen": 0, "anhaenge": 0,
         "miniaturbilder": 0, "ebenen": 0, "xfa": False}
    for nr in range(len(doc)):
        seite = doc[nr]
        try:
            z["formularfelder"] += sum(1 for _ in seite.widgets())
            z["anmerkungen"] += sum(1 for _ in seite.annots())
            z["links"] += len(seite.get_links())
            z["miniaturbilder"] += int(_schluessel_vorhanden(doc, seite.xref, "Thumb"))
        except Exception:
            pass
    try:
        z["lesezeichen"] = len(doc.get_toc())
        z["anhaenge"] = doc.embfile_count()
        z["ebenen"] = len(doc.get_ocgs())
        z["xfa"] = hat_xfa(doc)
    except Exception:
        pass
    return z


def hat_xfa(doc) -> bool:
    try:
        art, wert = doc.xref_get_key(doc.pdf_catalog(), "AcroForm/XFA")
        return art not in ("null", None) and wert not in ("null", "", None)
    except Exception:
        return False


_FELDTYPEN_MIT_TEXT = {"Text", "ComboBox", "ListBox"}
_KAMM = getattr(fitz, "PDF_TX_FIELD_IS_COMB", 1 << 24)


def _felder_lesen(doc) -> list:
    """Formularfelder mit Textwert (vor bake): Rechteck schon in Koordinaten NACH remove_rotation.
    Eigene Funktion, damit keine Widget-Objekte bis zum bake() leben (sonst brennt PyMuPDF die Werte
    doppelt ein)."""
    felder = []
    for nr in range(len(doc)):
        seite = doc[nr]
        matrix = seite.rotation_matrix
        for w in seite.widgets():
            try:
                typ = w.field_type_string
                wert = w.field_value
            except Exception:
                continue
            if typ not in _FELDTYPEN_MIT_TEXT or not isinstance(wert, str) or not wert.strip():
                continue
            felder.append({"seite": nr, "name": w.field_name or "", "wert": wert.strip(),
                           "rect": fitz.Rect(w.rect) * matrix,
                           "kamm": bool((w.field_flags or 0) & _KAMM) and bool(w.text_maxlen)})
    return felder


def _wortmenge(seite) -> set:
    return {(w[4], tuple(round(v, 1) for v in w[:4])) for w in seite.get_text("words")}


def _bildmenge(seite) -> set:
    try:
        return {tuple(round(v, 1) for v in i["bbox"]) for i in seite.get_image_info()}
    except Exception:
        return set()


def dokument_vorbereiten(doc) -> dict:
    """Gemeinsame Vorbereitung für Analyse UND Schwärzung (identisch, damit die Modelle gleich sind):
    Nebenkanäle zählen, Formularfelder lesen, Formularfelder/Anmerkungen einbrennen (bake), Seitendrehung
    entfernen, ausgeblendete Ebenen sichtbar machen (ihre Inhalte werden gemerkt), /ActualText und /Alt
    entfernen. Mehrfachaufruf ist unschädlich (das Ergebnis wird am Dokument gemerkt).

    Rückgabe: {"dokument", "zaehler", "felder_roh", "versteckt": {seite: [Rect]}, "rotation": {seite: Grad},
               "xfa", "bake_fehler", "markierungen"}.
    WICHTIG: Hat das PDF Ebenen (Optional Content), wird es danach einmal aus dem Speicher neu geöffnet –
    MuPDF legt die Sichtbarkeit beim Öffnen fest, und nur so sieht auch die Schwärzung die ausgeblendeten
    Inhalte. Aufrufer arbeiten deshalb mit info["dokument"] weiter (sonst dasselbe Objekt wie doc)."""
    vorher = getattr(doc, "_anon_vorbereitung", None)
    if vorher is not None:
        return vorher
    info = {"dokument": doc, "zaehler": nebenkanaele_zaehlen(doc), "felder_roh": [], "versteckt": {},
            "rotation": {}, "xfa": False, "bake_fehler": None, "markierungen": 0}
    info["xfa"] = bool(info["zaehler"].get("xfa"))
    try:
        info["felder_roh"] = _felder_lesen(doc)
    except Exception:
        info["felder_roh"] = []
    try:
        doc.bake()
    except Exception as e:  # ältere PyMuPDF-Version ohne bake()
        info["bake_fehler"] = str(e)
    for nr in range(len(doc)):
        seite = doc[nr]
        if seite.rotation:
            info["rotation"][nr] = seite.rotation
            seite.remove_rotation()
    # Ebenen VOR der Markierungs-Bereinigung: die löst benannte Properties (/OC /oc1 BDC) auf und
    # würde ausgeblendete Inhalte schon vor dem Vergleich sichtbar machen
    try:
        ebenen = bool(doc.get_ocgs())
    except Exception:
        ebenen = False
    if ebenen:
        vorher_mengen = {nr: (_wortmenge(doc[nr]), _bildmenge(doc[nr])) for nr in range(len(doc))}
        try:
            doc.xref_set_key(doc.pdf_catalog(), "OCProperties", "null")
            neu_doc = fitz.open("pdf", doc.tobytes(garbage=0))
        except Exception:
            neu_doc = doc
        for nr in range(len(neu_doc)):
            seite = neu_doc[nr]
            woerter, bilder = _wortmenge(seite), _bildmenge(seite)
            neu = [r for (t, r) in woerter if (t, r) not in vorher_mengen[nr][0]]
            neu += [r for r in bilder if r not in vorher_mengen[nr][1]]
            if neu:
                info["versteckt"][nr] = [fitz.Rect(r) + (-1, -1, 1, 1) for r in neu]
        info["dokument"] = neu_doc
    try:
        info["markierungen"] = _markierungen_bereinigen(info["dokument"])
    except Exception:
        pass
    for d in {id(doc): doc, id(info["dokument"]): info["dokument"]}.values():
        try:
            d._anon_vorbereitung = info
        except AttributeError:
            pass
    return info


# ----------------------------------------------------------------------
# OCR-Entscheidung (eine Heuristik für alle: ocr.py)
# ----------------------------------------------------------------------
def ocr_entscheidung(seite) -> str:
    """'nein' | 'seite' | 'bilder' (ocr.ocr_noetig; Rückfall auf ist_scan_seite)."""
    if hasattr(_ocr, "ocr_noetig"):
        return _ocr.ocr_noetig(seite)
    if hasattr(_ocr, "ist_scan_seite"):
        return "seite" if _ocr.ist_scan_seite(seite) else "nein"
    return "nein"


def bildbereiche(seite) -> list:
    """Relevante Bildbereiche der Seite (ocr.bild_bereiche; eine Schwelle für alle)."""
    if hasattr(_ocr, "bild_bereiche"):
        try:
            return list(_ocr.bild_bereiche(seite))
        except Exception:
            pass
    bereiche = []
    try:
        flaeche = abs(seite.rect)
        for info in seite.get_image_info():
            r = fitz.Rect(info["bbox"]) & seite.rect
            if not r.is_empty and abs(r) >= 0.01 * flaeche:
                bereiche.append(r)
    except Exception:
        pass
    return bereiche


# ----------------------------------------------------------------------
# Dokument aufbauen
# ----------------------------------------------------------------------
def _melden(liste, meldungen, art, code, text, seite=None):
    if liste is not None and text not in liste:
        liste.append(text)
    if meldungen is not None:
        meldungen.append({"art": art, "code": code, "text": text, "seite": seite})


def _ocr_holen(dienst, pfad, nr, clip=None):
    """(Wörter, Warnung, Winkel, Plausibilität, Meldungen des Dienstes) vom OCR-Dienst. Bevorzugt das
    vollständige Ergebnis (8-Tupel mit Zeilennummern der OCR), sonst woerter() (5-Tupel)."""
    ergebnis_fn = getattr(dienst, "ergebnis", None)
    if ergebnis_fn is not None:
        e = ergebnis_fn(pfad, nr, OCR_DPI, clip) if clip is not None else ergebnis_fn(pfad, nr, OCR_DPI)
        return (list(e.get("woerter") or []), e.get("warnung"), e.get("winkel"), e.get("plausibel"),
                e.get("meldungen"))
    if clip is not None:
        try:
            woerter, warnung = dienst.woerter(pfad, nr, OCR_DPI, clip=clip)
        except TypeError:                     # alter Dienst ohne clip
            woerter, warnung = dienst.woerter(pfad, nr)
    else:
        try:
            woerter, warnung = dienst.woerter(pfad, nr, OCR_DPI)
        except TypeError:
            woerter, warnung = dienst.woerter(pfad, nr)
    return list(woerter or []), warnung, None, None, None


def _ocr_warnung_melden(warnungen, meldungen, warnung, plausibel, anzahl, dienst_meldungen, nr):
    """Warnung des Dienstes als Text in die Warnungen (wie bisher) und strukturiert in die Meldungen –
    mit den Codes des Dienstes, sonst grob eingeordnet."""
    if warnungen is not None and warnung and warnung not in warnungen:
        warnungen.append(warnung)
    if meldungen is None:
        return
    if dienst_meldungen:
        for m in dienst_meldungen:
            if isinstance(m, dict) and m.get("code"):
                meldungen.append({"art": m.get("art", "warnung"), "code": m["code"], "text": m.get("text", ""),
                                  "seite": m.get("seite", nr)})
        return
    if not warnung:
        return
    if "unplausibel" in warnung or (plausibel is not None and plausibel < 0.4 and anzahl >= 5):
        code = "OCR_UNPLAUSIBEL"
    elif "gedreht" in warnung and "fehlgeschlagen" not in warnung:
        code = "OCR_GELESEN"
    else:
        code = "OCR_FEHLER"
    meldungen.append({"art": "warnung", "code": code, "text": warnung, "seite": nr})


def dokument_aufbauen(doc, pfad, ocr=None, ocr_cache=None, melde=None, fortschritt=None, abbruch=None,
                      warnungen=None, hinweise=None, *, meldungen=None, vorbereitung=None,
                      analyse_meldungen=True) -> Dokument:
    """Baut das Modell eines vorbereiteten Dokuments (dokument_vorbereiten wird sonst nachgeholt).

    ocr: OcrDienst (oder Attrappe mit woerter()); ocr_cache: {seite: Wörter} – wird benutzt und gefüllt
    (Wörter als Tupel (x0, y0, x1, y1, text[, block, zeile, wort])). warnungen/hinweise/meldungen: Listen,
    in die Meldungen zum Lesen (OCR) geschrieben werden; analyse_meldungen=False lässt die nur für die
    Analyse gedachten Hinweise weg (Schwärzung). Abbruch -> Ausnahme Abgebrochen."""
    pfad = Path(pfad) if pfad else None
    if vorbereitung is None:
        vorbereitung = dokument_vorbereiten(doc)
    doc = vorbereitung.get("dokument") or doc
    if ocr_cache is None:
        ocr_cache = {}
    felder_je_seite: dict = {}
    for feld in vorbereitung.get("felder_roh", []):
        felder_je_seite.setdefault(feld["seite"], []).append(feld)
    seiten = []
    felder = []
    ocr_fehlt_gemeldet = False
    gesamt = len(doc)
    entscheidungen: dict = {}
    vorab = getattr(ocr, "vorab", None)
    if vorab is not None and pfad is not None:
        # Scan-Seiten parallel einreihen (Gutachten PERF-05); ergebnis() wartet dann nur noch
        for nr in range(gesamt):
            entscheidungen[nr] = ocr_entscheidung(doc[nr])
        offen = [nr for nr, m in entscheidungen.items() if m == "seite" and nr not in ocr_cache]
        if offen:
            try:
                vorab(pfad, offen, OCR_DPI)
            except Exception:
                pass
    for nr in range(gesamt):
        if abbruch is not None and abbruch.is_set():
            raise Abgebrochen()
        if fortschritt:
            fortschritt(nr + 1, gesamt)
        seite = doc[nr]
        modus = entscheidungen.get(nr) or ocr_entscheidung(seite)
        bilder = bildbereiche(seite) if modus != "nein" else []
        woerter, winkel, quelle = None, None, "ocr"
        ocr_gelaufen, ocr_warnung = False, False
        if modus in ("seite", "bilder"):
            quelle = "ocr" if modus == "seite" else "bild"
            if nr in ocr_cache:
                woerter = list(ocr_cache[nr])
                bekannt = getattr(ocr, "winkel_falls_bekannt", None)
                if modus == "seite" and bekannt is not None and pfad is not None:
                    try:
                        winkel = bekannt(pfad, nr, OCR_DPI)
                    except Exception:
                        winkel = None
            elif ocr is None:
                if not ocr_fehlt_gemeldet:
                    _melden(warnungen, meldungen, "warnung", "BILDER_UNGEPRUEFT",
                            f"Seite {nr + 1} enthält Bilder/Scans, aber OCR ist nicht verfügbar — "
                            f"dort kann nichts automatisch erkannt werden.", nr)
                    ocr_fehlt_gemeldet = True
            else:
                woerter = []
                ocr_gelaufen = True
                if modus == "seite":
                    if melde:
                        melde(f"   OCR läuft: {pfad.name if pfad else ''}, Seite {nr + 1}/{gesamt} …")
                    w, warnung, winkel, plausibel, dienst_meldungen = _ocr_holen(ocr, pfad, nr)
                    woerter = w
                    if warnung == "Abgebrochen" and abbruch is not None and abbruch.is_set():
                        raise Abgebrochen()
                    if warnung or dienst_meldungen:
                        ocr_warnung = ocr_warnung or bool(warnung)
                        _ocr_warnung_melden(warnungen, meldungen, warnung, plausibel, len(w), dienst_meldungen, nr)
                else:
                    for bereich in bilder:
                        if abbruch is not None and abbruch.is_set():
                            raise Abgebrochen()
                        w, warnung, _, plausibel, dienst_meldungen = _ocr_holen(ocr, pfad, nr, clip=bereich)
                        woerter.extend(w)
                        if warnung == "Abgebrochen" and abbruch is not None and abbruch.is_set():
                            raise Abgebrochen()
                        if warnung or dienst_meldungen:
                            ocr_warnung = ocr_warnung or bool(warnung)
                            _ocr_warnung_melden(warnungen, meldungen, warnung, plausibel, len(w), dienst_meldungen, nr)
                if woerter:
                    ocr_cache[nr] = list(woerter)
        m = seite_aufbauen(seite, nr, ocr_woerter=woerter, ocr_quelle=quelle,
                           felder_roh=felder_je_seite.get(nr, ()), bilder=bilder)
        m.ocr_modus = modus
        m.ocr_winkel = winkel
        m.ocr_woerter = len(woerter or [])
        if analyse_meldungen and modus == "seite" and woerter is not None:
            if woerter:
                if len(woerter) < 25:
                    _melden(warnungen, meldungen, "warnung", "KAUM_LESBAR",
                            f"Seite {nr + 1} ist für die OCR kaum lesbar — dort kann NICHTS automatisch "
                            f"erkannt werden. Unbedingt manuell prüfen!", nr)
            elif ocr_gelaufen and not ocr_warnung:
                _melden(warnungen, meldungen, "warnung", "OCR_FEHLER",
                        f"Seite {nr + 1}: OCR hat keinen Text gelesen — bitte manuell prüfen!", nr)
        if analyse_meldungen and modus == "bilder" and woerter:
            _melden(hinweise, meldungen, "hinweis", "OCR_GELESEN",
                    f"Seite {nr + 1}: Text in Bildern per OCR gelesen und mitgeprüft.", nr)
        seiten.append(m)
        felder.extend(m.felder)
    dok = Dokument(pfad, seiten, felder)
    dok.vorbereitung = vorbereitung
    return dok


# ----------------------------------------------------------------------
# Modell aus reinem Text
# ----------------------------------------------------------------------
_ZEICHENBREITE = 6.0
_ZEILENHOEHE = 14.0


def dokument_aus_text(text: str) -> Dokument:
    """Modell aus reinem Text: eine Seite, Zeilen aus "\\n", Rechtecke synthetisch, quelle "text".
    Es gelten dieselben Zeichenregeln wie für PDF-Seiten (NFC, Ligaturen, Silbentrennung)."""
    zeilen = []
    roh_zeilen = (text or "").split("\n")
    breite = 50 + _ZEICHENBREITE * max((len(z) for z in roh_zeilen), default=0) + 50
    for j, zeile in enumerate(roh_zeilen):
        y = 50 + _ZEILENHOEHE * j
        inhalt = []
        for i, c in enumerate(zeile):
            x = 50 + _ZEICHENBREITE * i
            inhalt.append((c, _rect(x, y, x + _ZEICHENBREITE, y + 12), y + 10, 10.0, -1))
        zeilen.append(_Rohzeile(0, inhalt, True, "text"))
    rect = fitz.Rect(0, 0, max(595, breite), max(842, 100 + _ZEILENHOEHE * len(roh_zeilen)))
    seite = _seite_aus_zeilen(0, rect, zeilen)
    dok = Dokument(None, [seite])
    dok.aus_text = True
    return dok
