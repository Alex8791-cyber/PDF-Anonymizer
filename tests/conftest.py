"""Gemeinsame Test-Einstellungen: Projektwurzel importierbar machen, Umgebungsprüfungen."""

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


braucht_modell = pytest.mark.skipif(not _modell_vorhanden(), reason="spaCy-Modell de_core_news_md fehlt")
braucht_ocr = pytest.mark.skipif(not _tessdata_vorhanden(), reason="Tesseract-Sprachdaten fehlen")


@pytest.fixture
def tmp_pdf_ordner(tmp_path):
    """Leerer Ordner für Test-PDFs."""
    return tmp_path
