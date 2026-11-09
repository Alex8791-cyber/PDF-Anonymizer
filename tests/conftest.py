"""Gemeinsame Test-Einstellungen: Projektwurzel importierbar machen, Umgebungsprüfungen."""

import functools
import os
import sys
import unicodedata
import warnings
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
if str(WURZEL) not in sys.path:
    sys.path.insert(0, str(WURZEL))

warnings.filterwarnings("ignore", category=FutureWarning)  # "fitz" API deprecated (PyMuPDF 2.x)


def _modell_vorhanden() -> bool:
    try:
        import spacy
        spacy.load("de_core_news_md")
        return True
    except Exception:
        return False


def _tessdata_vorhanden() -> bool:
    try:
        from anonymisierer.ocr import _tessdata_finden
        return _tessdata_finden() is not None
    except Exception:
        return False


# Bevorzugte Schriften in fester Reihenfolge (gleiche Wahl bei jedem Lauf), danach jede andere installierte
# TrueType-Schrift: Ein Test wird nur übersprungen, wenn KEINE installierte Schrift die Zeichen hat.
_SCHRIFTEN = ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf", "times.ttf", "calibri.ttf", "tahoma.ttf", "verdana.ttf",
              "Arial.ttf")
_SCHRIFT_ORDNER = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF",
                   str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
                   str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Microsoft" / "Windows" / "Fonts"),
                   "/System/Library/Fonts/Supplemental", "/Library/Fonts", str(Path.home() / "Library" / "Fonts"))
_SCHRIFT_BAEUME = ("/usr/share/fonts", "/usr/local/share/fonts", str(Path.home() / ".local" / "share" / "fonts"),
                   str(Path.home() / ".fonts"))           # Linux: Schriften liegen in Unterordnern


def _schrift_kandidaten():
    gesehen = set()
    for ordner in _SCHRIFT_ORDNER:
        for name in _SCHRIFTEN:
            pfad = Path(ordner) / name
            if pfad.is_file() and pfad not in gesehen:
                gesehen.add(pfad)
                yield pfad
    for ordner, rekursiv in [(o, False) for o in _SCHRIFT_ORDNER] + [(o, True) for o in _SCHRIFT_BAEUME]:
        try:
            dateien = sorted((Path(ordner).rglob if rekursiv else Path(ordner).glob)("*"))
        except OSError:
            continue
        for pfad in dateien:
            if pfad.suffix.lower() == ".ttf" and pfad not in gesehen and pfad.is_file():
                gesehen.add(pfad)
                yield pfad


@functools.lru_cache(maxsize=None)
def _schrift_fuer(zeichen: frozenset):
    import pymupdf as fitz
    for pfad in _schrift_kandidaten():
        try:
            schrift = fitz.Font(fontfile=str(pfad))
            if all(schrift.has_glyph(ord(z)) for z in zeichen):
                return pfad
        except Exception:
            continue
    return None


def schrift_mit_zeichen(zeichen: str):
    """Pfad einer installierten TrueType-Schrift, die ALLE angegebenen Zeichen enthält (unter Linux DejaVu Sans,
    unter Windows Arial/Segoe UI/Calibri/…), sonst None. Für Tests, die Sonderzeichen wie das Versal-ß (ẞ),
    Ligaturen oder die Windows-Sonderzeichen (NBSP, weicher Trennstrich, U+2011) in eine PDF schreiben müssen –
    die eingebauten Base-14-Schriften kennen sie nicht. Steuerzeichen (z. B. Zeilenumbrüche) zählen nicht mit,
    man kann also ganze Testzeilen übergeben."""
    return _schrift_fuer(frozenset(z for z in zeichen if unicodedata.category(z) != "Cc"))


# Windows-Schriften (Arial, Segoe UI …) legen Leerzeichen und geschütztes Leerzeichen auf DIESELBE Glyphe, je nach
# Schrift auch Bindestrich, weichen Trennstrich und U+2010/U+2011. Die Textebene liefert dann für jede dieser Glyphen
# nur EINEN Codepunkt (MuPDF: den höchsten): Aus geschriebenem "Frau Groß" und "51-633867" wird beim Auslesen z. B.
# "Frau\xa0Groß" und "51\xad633867" bzw. "51\u2011633867"; mit DejaVu Sans (eigene Glyphen) bleibt es, wie es war.
_WINDOWS_TEXTEBENE = str.maketrans({"\xa0": " ", "\xad": "-", "\u2010": "-", "\u2011": "-"})


def textebene_angleichen(text: str) -> str:
    """Vereinheitlicht ausgelesenen Text für Vergleiche, die mit jeder Schrift dasselbe bedeuten sollen:
    geschütztes Leerzeichen -> Leerzeichen; weicher Trennstrich, U+2010 und U+2011 -> Bindestrich."""
    return text.translate(_WINDOWS_TEXTEBENE)


braucht_modell = pytest.mark.skipif(not _modell_vorhanden(), reason="spaCy-Modell de_core_news_md fehlt")
braucht_ocr = pytest.mark.skipif(not _tessdata_vorhanden(), reason="Tesseract-Sprachdaten fehlen")


@pytest.fixture
def tmp_pdf_ordner(tmp_path):
    """Leerer Ordner für Test-PDFs."""
    return tmp_path
