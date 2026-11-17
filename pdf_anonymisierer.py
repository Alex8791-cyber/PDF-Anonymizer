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
Paket "anonymisierer": Erkennung (muster, kennungsformen, namen, wissen,
detektoren, kundenliste, analyse), Lesen der Seiten (seitenmodell, ocr), Schwärzen
und Prüfen der Ausgabe (schwaerzung, bilder, fotos, nebenkanaele,
restrisiko) sowie Oberfläche und Dateien (gui, gui_attrappen, auftrag,
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


def _dll_ladefehler(fehler):
    """Die Ausnahme der Kette, mit der der Import an einer DLL scheiterte – „DLL load failed“ (Erweiterungsmodul)
    bzw. WinError 126/127 (Modul/Prozedur nicht gefunden) –, sonst None. Durchsucht die ganze Ausnahmekette: Der
    Rückfall auf den alten Namen „fitz“ verdeckt sonst die eigentliche Ursache."""
    gesehen = set()
    while fehler is not None and id(fehler) not in gesehen:
        gesehen.add(id(fehler))
        if isinstance(fehler, (ImportError, OSError)) and (
                "DLL load failed" in str(fehler) or getattr(fehler, "winerror", None) in (126, 127)):
            return fehler
        fehler = fehler.__cause__ or fehler.__context__
    return None


def _fremder_oserror(fehler):
    """Ein OSError der Ausnahmekette ohne DLL-Bezug (z. B. PermissionError durch eine Virenscanner-Sperre), sonst None.
    PyMuPDF fängt einen Fehler beim Laden von pymupdf.mupdf selbst ab und meldet „No module named 'mupdf'“ – der
    eigentliche Fehler steht dann nur in der Kette (Gegenprüfung Runde 5)."""
    if _dll_ladefehler(fehler) is not None:
        return None
    gesehen = set()
    while fehler is not None and id(fehler) not in gesehen:
        gesehen.add(id(fehler))
        if isinstance(fehler, OSError):
            return fehler
        fehler = fehler.__cause__ or fehler.__context__
    return None


def _meldung_paket_fehlt(fehler=None) -> str:
    """Text, wenn PyMuPDF fehlt oder sich nicht laden lässt – in der EXE gibt es kein Installieren.bat (M-70).
    Scheitert der Import an einer DLL, fehlt in der Skript-Version meist die Visual-C++-Laufzeit von Microsoft:
    PyMuPDF braucht msvcp140.dll und vcruntime140_1.dll. Python bringt vcruntime140_1.dll (ab 3.8.1, im Ordner von
    python.exe) selbst mit, msvcp140.dll nicht – die legt erst die „Visual C++ Redistributable“ in den
    Windows-Systemordner. Installieren.bat erneut auszuführen hilft dann nicht (die EXE hat die Laufzeit in ihrem
    Ordner)."""
    if getattr(sys, "frozen", False):
        return ("Ein Programmbestandteil (PyMuPDF) fehlt oder wurde vom Virenscanner entfernt.\n\n"
                "Bitte den Programmordner vollständig neu entpacken bzw. eine neue ZIP-Datei anfordern "
                "(ggf. die Quarantäne des Virenscanners prüfen).")
    ursache = _dll_ladefehler(fehler)
    if ursache is not None:
        return ("Das Paket 'PyMuPDF' ist installiert, lässt sich aber nicht laden (DLL load failed).\n\n"
                "Meist fehlt auf diesem Rechner die Visual-C++-Laufzeit von Microsoft oder sie ist veraltet: "
                "„Microsoft Visual C++ 2015-2022 Redistributable (x64)“. Abhilfe (einmalig, mit "
                "Administratorrechten):\n"
                "- in einer Eingabeaufforderung: winget install --id Microsoft.VCRedist.2015+.x64 -e\n"
                "- oder vc_redist.x64.exe von Microsoft laden und ausführen: "
                "https://aka.ms/vs/17/release/vc_redist.x64.exe\n\n"
                "Danach das Programm neu starten. Ohne Administratorrechte: die IT fragen oder die EXE-Version "
                "nutzen (sie bringt die Laufzeit mit).\n\n"
                f"Technische Meldung: {ursache}")
    return ("Das Paket 'PyMuPDF' fehlt.\n\n"
            "Bitte einmal 'Installieren.bat' ausführen.")


try:
    _pymupdf_laden()
except (ImportError, OSError) as _fehler:     # OSError: z. B. WinError 126 beim Laden einer DLL
    if _fremder_oserror(_fehler) is not None:
        # Ein OSError ohne DLL-Bezug (z. B. PermissionError, weil ein Virenscanner eine Paketdatei sperrt) ist kein
        # fehlendes Paket: „Paket fehlt“ nennte die falsche Ursache, und die Diagnose ginge verloren. Wie jeder
        # unerwartete Fehler: Traceback in die fehler.log, Dialog „Unerwarteter Fehler“ mit Details (sys.excepthook).
        raise
    meldung = _meldung_paket_fehlt(_fehler)
    try:
        print("FEHLER: " + meldung)
    except Exception:                         # Konsole ohne passende Kodierung: der Dialog folgt trotzdem
        pass
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _w = _tk.Tk(); _w.withdraw()
        _titel = "PyMuPDF lässt sich nicht laden" if _dll_ladefehler(_fehler) is not None else "Paket fehlt"
        _mb.showerror(f"PDF-Anonymisierer — {_titel}", meldung)
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
