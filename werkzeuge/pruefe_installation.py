#!/usr/bin/env python3
"""Zeigt für Rückfragen, womit das Programm auf diesem Rechner läuft.

Aufruf (im Programmordner):  python werkzeuge\\pruefe_installation.py
Die Ausgabe kann man bei Problemen kopieren und mitschicken. Es wird nichts verändert.

Exit-Code 0 = alles vorhanden, 1 = etwas fehlt oder passt nicht (steht in der Ausgabe).
"""

from __future__ import annotations

import importlib
import os
import platform
import struct
import sys
from importlib import metadata
from pathlib import Path

PROGRAMM_ORDNER = Path(__file__).resolve().parent.parent
PAKETE = ("pymupdf", "spacy", "tkinterdnd2", "de_core_news_md")


def _version(paket: str) -> str | None:
    try:
        return metadata.version(paket)
    except metadata.PackageNotFoundError:
        return None


def _importierbar(modul: str) -> tuple[bool, str]:
    try:
        importlib.import_module(modul)
        return True, "ok"
    except Exception as e:  # noqa: BLE001 - jede Ursache soll im Bericht stehen
        return False, f"{type(e).__name__}: {e}"


def python_bericht() -> tuple[list[str], list[str]]:
    zeilen, probleme = [], []
    bits = struct.calcsize("P") * 8
    zeilen.append(f"Python:        {platform.python_version()} ({bits}-Bit) – {sys.executable}")
    zeilen.append(f"System:        {platform.system()} {platform.release()} {platform.version()}")
    zeilen.append(f"Prozessor:     {platform.machine()}  "
                  f"(PROCESSOR_ARCHITECTURE={os.environ.get('PROCESSOR_ARCHITECTURE', '-')}, "
                  f"PROCESSOR_ARCHITEW6432={os.environ.get('PROCESSOR_ARCHITEW6432', '-')})")
    if bits != 64:
        probleme.append("32-Bit-Python: für PyMuPDF/spaCy gibt es keine passenden Pakete – "
                        "bitte 64-Bit-Python (x64) installieren.")
    if platform.machine().upper().startswith("ARM"):
        probleme.append("ARM64-Prozessor: PyMuPDF gibt es nur in einer älteren Version, "
                        "spaCy ggf. gar nicht – ARM64 wird nicht unterstützt.")
    if not (3, 10) <= sys.version_info[:2] < (3, 16):
        probleme.append(f"Python {platform.python_version()} wird nicht unterstützt (nötig: 3.10 bis 3.15).")
    pip = _version("pip")
    zeilen.append(f"pip:           {pip or 'FEHLT'}")
    if pip is None:
        probleme.append("pip fehlt – Python-Installation reparieren oder 'python -m ensurepip' ausführen.")
    return zeilen, probleme


def pakete_bericht() -> tuple[list[str], list[str]]:
    zeilen, probleme = [], []
    for paket in PAKETE:
        version = _version(paket)
        zeilen.append(f"{paket + ':':<20}{version or 'FEHLT'}")
        if version is None:
            probleme.append(f"Paket {paket} fehlt – Installieren.bat ausführen.")
    import warnings
    warnings.simplefilter("ignore")
    for modul in ("fitz", "spacy", "tkinter", "tkinterdnd2"):
        ok, info = _importierbar(modul)
        zeilen.append(f"import {modul + ':':<13}{info}")
        if not ok:
            probleme.append(f"'{modul}' lässt sich nicht importieren ({info}).")
    try:
        import spacy
        spacy.load("de_core_news_md", disable=["lemmatizer", "tagger"])
        zeilen.append("Sprachmodell:  de_core_news_md lädt")
    except Exception as e:  # noqa: BLE001
        zeilen.append(f"Sprachmodell:  FEHLER {type(e).__name__}: {e}")
        probleme.append("Das Sprachmodell de_core_news_md lässt sich nicht laden – "
                        "ohne Modell gibt es keine Namenserkennung.")
    return zeilen, probleme


def tessdata_bericht() -> tuple[list[str], list[str]]:
    zeilen, probleme = [], []
    kandidaten = [("Programmordner", PROGRAMM_ORDNER / "tessdata"),
                  ("TESSDATA_PREFIX", Path(os.environ["TESSDATA_PREFIX"]) if os.environ.get("TESSDATA_PREFIX") else None),
                  ("PyInstaller", Path(getattr(sys, "_MEIPASS", "")) / "tessdata" if getattr(sys, "_MEIPASS", None) else None)]
    gefunden = False
    for name, ordner in kandidaten:
        if ordner is None:
            zeilen.append(f"tessdata ({name}): nicht gesetzt")
            continue
        deu = ordner / "deu.traineddata"
        status = f"deu.traineddata {deu.stat().st_size // 1024} KB" if deu.exists() else "ohne deu.traineddata"
        zeilen.append(f"tessdata ({name}): {ordner} – {status}")
        gefunden = gefunden or deu.exists()
    try:
        from anonymisierer.ocr import _tessdata_finden
        zeilen.append(f"_tessdata_finden(): {_tessdata_finden()}")
    except Exception as e:  # noqa: BLE001
        zeilen.append(f"_tessdata_finden(): nicht prüfbar ({type(e).__name__}: {e})")
    if not gefunden:
        probleme.append("Keine deutsche OCR-Sprachdatei gefunden – Scans würden nur auf Englisch gelesen. "
                        "Der Ordner tessdata mit deu.traineddata gehört in den Programmordner.")
    return zeilen, probleme


def fehlerlog_bericht() -> list[str]:
    try:
        from anonymisierer.dateien import fehlerlog_pfad
        return [f"fehler.log:    {fehlerlog_pfad()}"]
    except Exception:  # noqa: BLE001 - ältere Stände ohne fehlerlog_pfad
        return [f"fehler.log:    neben dem Startskript ({PROGRAMM_ORDNER}) oder unter "
                f"%LOCALAPPDATA%\\PDF-Anonymisierer"]


def main() -> int:
    if str(PROGRAMM_ORDNER) not in sys.path:
        sys.path.insert(0, str(PROGRAMM_ORDNER))
    try:
        from anonymisierer import __version__
    except Exception:  # noqa: BLE001
        __version__ = "unbekannt"
    print(f"PDF-Anonymisierer {__version__} – Installationsprüfung")
    print(f"Programmordner: {PROGRAMM_ORDNER}")
    print("-" * 72)
    probleme: list[str] = []
    for bericht in (python_bericht, pakete_bericht, tessdata_bericht):
        zeilen, neue = bericht()
        print("\n".join(zeilen))
        probleme += neue
    print("\n".join(fehlerlog_bericht()))
    print("-" * 72)
    if probleme:
        print("PROBLEME:")
        for p in probleme:
            print(f"  - {p}")
        return 1
    print("Alles vorhanden – das Programm sollte laufen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
