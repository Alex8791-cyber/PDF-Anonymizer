"""OCR (Texterkennung für eingescannte PDFs) auf Basis des in PyMuPDF eingebauten Tesseract."""

import os
import sys
from pathlib import Path

import fitz  # PyMuPDF

def _tessdata_finden():
    """Sucht den Tesseract-Sprachdaten-Ordner an den üblichen Orten."""
    kandidaten = [os.environ.get("TESSDATA_PREFIX")]
    if sys.platform == "win32":
        kandidaten += [
            r"C:\Program Files\Tesseract-OCR\tessdata",
            r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
            str(Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tessdata"),
        ]
    else:
        kandidaten += ["/usr/share/tesseract-ocr/5/tessdata",
                       "/usr/share/tesseract-ocr/4.00/tessdata",
                       "/usr/share/tessdata"]
    for k in kandidaten:
        if k and Path(k).exists():
            os.environ["TESSDATA_PREFIX"] = k
            return k
    return None


def ist_scan_seite(seite) -> bool:
    """Erkennt Scan-Seiten: kein Text ODER ein Bild bedeckt >50 % der Seite
    (z. B. Scans mit Textstempel oder bereits eingefügten Platzhaltern)."""
    if not seite.get_text().strip():
        return True
    seiten_flaeche = abs(seite.rect)
    try:
        for info in seite.get_image_info():
            if abs(fitz.Rect(info["bbox"])) >= 0.5 * seiten_flaeche:
                return True
    except Exception:
        pass
    return False


def ocr_textpage(seite, melde=None):
    """
    Erzeugt per OCR eine durchsuchbare Textebene für eine Scan-Seite.
    Rückgabe: (textpage oder None, Warnung oder None)
    """
    tessdata = _tessdata_finden()
    if tessdata is None:
        return None, ("Tesseract-OCR ist nicht installiert — Scans können nicht "
                      "gelesen werden. Bitte Installieren.bat erneut ausführen.")
    if (Path(tessdata) / "deu.traineddata").exists():
        sprache, warnung = "deu", None
    elif (Path(tessdata) / "eng.traineddata").exists():
        sprache = "eng"
        warnung = ("Deutsche OCR-Sprachdatei fehlt — nutze Englisch "
                   "(Umlaute werden evtl. falsch erkannt).")
    else:
        return None, "Keine OCR-Sprachdatei gefunden — Installieren.bat erneut ausführen."
    try:
        tp = seite.get_textpage_ocr(language=sprache, dpi=300, full=True,
                                    tessdata=tessdata)
        return tp, warnung
    except Exception as e:
        return None, f"OCR fehlgeschlagen: {e}"
