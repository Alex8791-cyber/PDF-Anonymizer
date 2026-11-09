"""Gemeinsame Test-Einstellungen: Projektwurzel importierbar machen, Umgebungsprüfungen."""

import os
import sys
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


_SCHRIFTEN = ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf", "times.ttf", "calibri.ttf", "tahoma.ttf", "verdana.ttf",
              "Arial.ttf")
_SCHRIFT_ORDNER = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF",
                   str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
                   "/System/Library/Fonts/Supplemental", "/Library/Fonts")


def schrift_mit_zeichen(zeichen: str):
    """Pfad einer installierten TrueType-Schrift, die ALLE angegebenen Zeichen enthält (unter Linux DejaVu Sans,
    unter Windows Arial/Segoe UI/…), sonst None. Für Tests, die Sonderzeichen wie das Versal-ß (ẞ) in eine PDF
    schreiben müssen – die eingebauten Base-14-Schriften kennen sie nicht."""
    import pymupdf as fitz
    for ordner in _SCHRIFT_ORDNER:
        for name in _SCHRIFTEN:
            pfad = Path(ordner) / name
            if not pfad.is_file():
                continue
            try:
                schrift = fitz.Font(fontfile=str(pfad))
            except Exception:
                continue
            if all(schrift.has_glyph(ord(z)) for z in zeichen):
                return pfad
    return None


braucht_modell = pytest.mark.skipif(not _modell_vorhanden(), reason="spaCy-Modell de_core_news_md fehlt")
braucht_ocr = pytest.mark.skipif(not _tessdata_vorhanden(), reason="Tesseract-Sprachdaten fehlen")


@pytest.fixture
def tmp_pdf_ordner(tmp_path):
    """Leerer Ordner für Test-PDFs."""
    return tmp_path
