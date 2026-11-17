#!/usr/bin/env python3
"""
PDF-Anonymisierer — Dokumente für ChatGPT & Claude pseudonymisieren
===================================================================

Zweck: PDFs sollen an KI-Dienste (ChatGPT, Claude …) gegeben werden
können, ohne direkte personenbezogene Daten preiszugeben. Das Programm
findet automatisch unter anderem (vollständige Liste in der README):

  • Namen von Personen        (Sprachmodell, Namenslisten, Aufbau von
                               Briefen, Tabellen und Formularen)
  • Anschriften               (Straße + Hausnummer, PLZ + Ort; ab „Hoch“
                               auch Orte ohne PLZ und ausländische
                               Anschriften)
  • IBAN, BIC, Telefonnummern, E-Mail-Adressen, Geburtsdaten
  • Vertrags-, Kunden- und Versicherungsscheinnummern, Aktenzeichen
  • Sozialversicherungs-, Steuer-, Krankenversicherten- und
    Kindergeldnummern, Ausweis- und Passnummern
  • Kfz-Kennzeichen, Fahrzeug-Identnummern
  • Beruf und Arbeitgeber (ab Schutzstufe „Hoch“), Diagnosen und
    Medikamente (angehakt nur in „Maximal“)
  • Lichtbilder auf Ausweiskopien (nicht immer gefunden); in „Maximal“
    auch Bilder auf Textseiten und Fotobereiche auf Scans (mit Ausnahmen)

Ersetzt wird mit lesbaren Platzhaltern wie [PERSON A], [IBAN],
[ADRESSE] — so bleibt das Dokument für die KI verständlich
("Person A" bleibt im ganzen Dokument dieselbe Person!), aber ohne
die direkten Identifikatoren. Der Text wird dabei wirklich aus der PDF
entfernt. Das Ergebnis ist eine Pseudonymisierung: Beträge und andere
Kontextangaben bleiben lesbar, je nach Schutzstufe auch Diagnosen,
Beruf, Arbeitgeber und Orte.

WICHTIG: Vor dem Schwärzen zeigt das Programm eine Prüfliste aller
Funde; danach prüft es jede Ausgabe ein zweites Mal (Restrisiko-
Prüfung). Keine automatische Erkennung ist perfekt — jede Ausgabe in
der Vorschau zu prüfen bleibt Pflicht!

Einmalige Vorbereitung: Installieren.bat doppelklicken
Starten: Desktop-Verknüpfung "PDF-Anonymisierer" (ein zweiter Start meldet nur,
dass das Programm schon läuft)

Dieses Skript ist nur der Startpunkt; die eigentliche Logik liegt im
Paket "anonymisierer": Erkennung (muster, namen, wissen, detektoren,
kundenliste, analyse), Lesen der Seiten (seitenmodell, ocr), Schwärzen
und Prüfen der Ausgabe (schwaerzung, bilder, fotos, nebenkanaele,
restrisiko) sowie Oberfläche und Dateien (gui, gui_attrappen,
vorschau_fenster, vorschau, dateien).
"""

import multiprocessing
import sys

# ----------------------------------------------------------------------
# Windows-Feinschliff
# ----------------------------------------------------------------------
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # scharfe Darstellung; die Oberfläche skaliert selbst
    except Exception:
        pass

# Fehlerprotokoll (ohne Konsole wären Abstürze unsichtbar). Das Modul braucht keine Fremdpakete.
from anonymisierer import dateien as _dateien  # noqa: E402


def _unbehandelter_fehler(typ, wert, tb):
    """Fehler in die fehler.log schreiben (Ort: dateien.fehlerlog_pfad) und – falls möglich – melden."""
    pfad = _dateien.fehler_protokollieren(typ, wert, tb)
    try:
        from tkinter import messagebox
        ort = str(pfad) if pfad else "(Fehlerprotokoll konnte nicht geschrieben werden)"
        messagebox.showerror("Unerwarteter Fehler",
                             f"Es ist ein Fehler aufgetreten:\n{typ.__name__}: {str(wert)[:300]}\n\n"
                             f"Details stehen in:\n{ort}")
    except Exception:
        pass


sys.excepthook = _unbehandelter_fehler

# ----------------------------------------------------------------------
# Abhängigkeiten
# ----------------------------------------------------------------------
def _pymupdf_laden():
    """PyMuPDF unter dem zukunftssicheren Namen „pymupdf“ laden, sonst unter dem alten „fitz“ (M-37). Fehlt der
    alte Name einmal (er gilt als veraltet), läuft das Programm trotzdem."""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    return fitz


def _meldung_paket_fehlt() -> str:
    """Text, wenn PyMuPDF fehlt – in der EXE gibt es kein Installieren.bat (M-70)."""
    if getattr(sys, "frozen", False):
        return ("Ein Programmbestandteil (PyMuPDF) fehlt oder wurde vom Virenscanner entfernt.\n\n"
                "Bitte den Programmordner vollständig neu entpacken bzw. eine neue ZIP-Datei anfordern "
                "(ggf. die Quarantäne des Virenscanners prüfen).")
    return ("Das Paket 'PyMuPDF' fehlt.\n\n"
            "Bitte einmal 'Installieren.bat' ausführen.")


try:
    _pymupdf_laden()
except ImportError:
    meldung = _meldung_paket_fehlt()
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
from anonymisierer.dateien import (einstellungen_laden, einstellungen_speichern,  # noqa: E402,F401
                                   fehlerlog_pfad, oeffne_ordner, sammle_pdfs)
from anonymisierer.gui import DND_VERFUEGBAR, AnonymisiererApp, main  # noqa: E402,F401
from anonymisierer.muster import KATEGORIEN  # noqa: E402,F401
from anonymisierer.namen import NAMEN_STOPPLISTE, finde_personen_ner, lade_ner  # noqa: E402,F401
from anonymisierer.schwaerzung import schwaerze_pdf  # noqa: E402,F401
from anonymisierer.ocr import OcrDienst, _tessdata_finden, ocr_noetig  # noqa: E402,F401

try:   # nur noch für ältere Prüfskripte (Regression), entfällt mit der neuen OCR-Schicht
    from anonymisierer.ocr import ist_scan_seite  # noqa: E402,F401
except ImportError:
    pass

if DND_VERFUEGBAR:
    from anonymisierer.gui import TkinterDnD  # noqa: E402,F401


if __name__ == "__main__":
    multiprocessing.freeze_support()   # PyInstaller: Hilfsprozesse (OCR, Start-Methode "spawn")
    main()
