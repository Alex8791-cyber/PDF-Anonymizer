#!/usr/bin/env python3
"""
PDF-Anonymisierer — Dokumente sicher für ChatGPT & Claude machen
=================================================================

Zweck: PDFs sollen an KI-Dienste (ChatGPT, Claude …) gegeben werden
können, ohne personenbezogene Daten preiszugeben. Das Programm findet
automatisch:

  • Namen von Personen        (KI-Erkennung, deutsches Sprachmodell)
  • Adressen                  (Straße + Hausnummer, PLZ + Ort)
  • IBANs                     (mit Prüfziffern-Kontrolle)
  • Telefonnummern
  • E-Mail-Adressen
  • Geburtsdaten              (Datumsangaben neben "geb." / "Geburtsdatum")
  • Vertrags-/Kunden-/Versicherungsschein-Nummern
  • Sozialversicherungsnummern & Steuer-IDs
  • Kfz-Kennzeichen

Ersetzt wird mit lesbaren Platzhaltern wie [PERSON A], [IBAN],
[ADRESSE] — so bleibt das Dokument für die KI verständlich
("Person A" bleibt im ganzen Dokument dieselbe Person!), aber ohne
echte Daten. Der Text wird dabei WIRKLICH aus der PDF entfernt.

WICHTIG: Vor dem Schwärzen zeigt das Programm eine Prüfliste aller
Funde. Keine automatische Erkennung ist perfekt — der Blick auf die
Liste (und stichprobenartig auf das Ergebnis) bleibt Pflicht!

Einmalige Vorbereitung: Installieren.bat doppelklicken
Starten: Desktop-Verknüpfung "PDF-Anonymisierer"

Dieses Skript ist nur der Startpunkt; die eigentliche Logik liegt im
Paket "anonymisierer" (muster, namen, analyse, ocr, schwaerzung, gui).
"""

import sys
import traceback
from pathlib import Path

# ----------------------------------------------------------------------
# Windows-Feinschliff
# ----------------------------------------------------------------------
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # scharfe Darstellung
    except Exception:
        pass


def _unbehandelter_fehler(typ, wert, tb):
    """Fehler in Logdatei schreiben (ohne Konsole wären sie unsichtbar)."""
    log = Path(__file__).with_name("fehler.log")
    with open(log, "a", encoding="utf-8") as f:
        f.write("".join(traceback.format_exception(typ, wert, tb)) + "\n")
    try:
        from tkinter import messagebox
        messagebox.showerror("Unerwarteter Fehler",
                             f"Es ist ein Fehler aufgetreten.\nDetails stehen in:\n{log}")
    except Exception:
        pass


sys.excepthook = _unbehandelter_fehler

# ----------------------------------------------------------------------
# Abhängigkeiten
# ----------------------------------------------------------------------
try:
    import fitz  # PyMuPDF  # noqa: F401
except ImportError:
    meldung = ("Das Paket 'PyMuPDF' fehlt.\n\n"
               "Bitte einmal 'Installieren.bat' ausführen.")
    print("FEHLER: " + meldung)
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _w = _tk.Tk(); _w.withdraw()
        _mb.showerror("PDF-Anonymisierer — Paket fehlt", meldung)
    except Exception:
        pass
    sys.exit(1)

# Öffentliche Namen für Skripte und Tests, die das Startskript importieren
from anonymisierer import __version__  # noqa: E402,F401
from anonymisierer.analyse import analysiere_pdf, analysiere_text  # noqa: E402,F401
from anonymisierer.dateien import sammle_pdfs  # noqa: E402,F401
from anonymisierer.gui import DND_VERFUEGBAR, AnonymisiererApp, main  # noqa: E402,F401
from anonymisierer.muster import KATEGORIEN  # noqa: E402,F401
from anonymisierer.namen import NAMEN_STOPPLISTE, finde_personen_ner, lade_ner  # noqa: E402,F401
from anonymisierer.ocr import ist_scan_seite, ocr_textpage  # noqa: E402,F401
from anonymisierer.schwaerzung import schwaerze_pdf  # noqa: E402,F401

if DND_VERFUEGBAR:
    from anonymisierer.gui import TkinterDnD  # noqa: E402,F401


if __name__ == "__main__":
    main()
