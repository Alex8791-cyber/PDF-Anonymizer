"""Grafische Oberfläche (tkinter): Dateien wählen, analysieren, Funde prüfen, schwärzen, Ausgaben freigeben.

Die Engine wird direkt nach Vertrag aufgerufen (CONTRACT/CONTRACT_V2). Neue Vertragsteile (Schutzstufen,
Kundenliste, Fundstellen, manuelle Bereiche, Freigabe, Vorschau, Meldungs-Codes) werden genutzt, sobald die
Engine sie anbietet (Signatur bzw. hasattr); bis dahin greifen die Attrappen in gui_attrappen.py. Fehlt der
Engine eine Fähigkeit, die der Nutzer anfordert, sagt die Oberfläche das – sie lässt nichts still weg.
"""

import errno
import inspect
import os
import re
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import fitz  # PyMuPDF

from . import __version__, dateien
from . import analyse as _analyse_modul
from . import gui_attrappen as attrappen
from . import muster as _muster_modul
from . import schwaerzung as _schwaerz_modul
from .analyse import analysiere_pdf
from .muster import KATEGORIEN
from .namen import lade_ner
from .ocr import OcrDienst
from .schwaerzung import schwaerze_pdf

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_VERFUEGBAR = True
except ImportError:
    DND_FILES = TkinterDnD = None
    DND_VERFUEGBAR = False

# Vertragsteile aus Phase 2: echte Engine, sonst Attrappe (12.5) bzw. None (Funktion entfällt)
weitergabe_anwenden = getattr(_analyse_modul, "weitergabe_anwenden", None)
LaufWissen = getattr(_analyse_modul, "LaufWissen", None)
freigeben = getattr(_schwaerz_modul, "freigeben", None) or attrappen.freigeben
verwerfen = getattr(_schwaerz_modul, "verwerfen", None) or attrappen.verwerfen
WARNUNG_KEIN_TREFFER = getattr(_schwaerz_modul, "WARNUNG_KEIN_TREFFER", attrappen.WARNUNG_KEIN_TREFFER)
PROFILE = getattr(_muster_modul, "PROFILE", None) or attrappen.PROFILE
try:
    from .kundenliste import Kundenliste
except ImportError:
    Kundenliste = attrappen.Kundenliste


# ----------------------------------------------------------------------
# Konstanten
# ----------------------------------------------------------------------
FARBE_HINTERGRUND = "#f4f5f7"
FARBE_KARTE = "#ffffff"
FARBE_AKZENT = "#1a5fb4"
FARBE_AKZENT_HELL = "#e8f0fb"
FARBE_TEXT = "#111827"
FARBE_TEXT_GRAU = "#6b7280"
FARBE_GRUEN = "#1a7f37"
FARBE_ROT = "#b91c1c"
FARBE_WARNUNG = "#b45309"
FARBE_HINWEIS_HINTERGRUND = "#fff7e6"
FARBE_HINWEIS_RAND = "#f0c36d"
FARBE_RAND = "#e5e7eb"

SCHRIFT = "Segoe UI"
SCHRIFT_MONO = "Consolas"
BASIS_SKALIERUNG = 4 / 3            # „tk scaling“ bei 96 dpi (Windows 100 %)
FENSTER_BREITE, FENSTER_HOEHE = 940, 940   # Entwurfsmaße bei 100 % (passt auf 1080p mit Taskleiste)
FENSTER_MINDESTMASS = (640, 520)
FENSTER_RAND_UNTEN = 140            # Platz für Taskleiste, Titelleiste und Menüleiste
FENSTER_KLEIN_HOEHE = 760           # darunter (bei 100 %) gilt das Fenster als klein: Protokoll kürzer
BAUM_MINDESTHOEHE = 120             # bei 100 %, damit die Fundliste nie ganz verschwindet
BAUM_ANTEIL = 0.45                  # Anteil des freien Platzes für die Fundliste (Arbeitsbereich, GR-02);
                                    # der Einstellbereich (einmal einstellen) scrollt bei Bedarf
KATEGORIE_SPALTEN = 3               # Häkchen-Gitter (4 Spalten schneiden bei 940 px Breite lange Namen ab)
KONTEXT_VORLAUF = 14                # Zeichen vor dem Fund in der Kontextspalte, damit der Fund sichtbar ist
UNTERTITEL_MINDESTHOEHE = 700       # bei 100 %; darunter wird der Untertitel ausgeblendet
OBEN_MINDESTHOEHE = 60              # bei 100 %, Mindesthöhe des scrollbaren Einstellbereichs (Titel + Drop-Zone)
PROTOKOLL_ZEILEN = 5
PROTOKOLL_ZEILEN_KLEIN = 3
PROTOKOLL_MAX_ZEILEN = 5000
VORLADEN_NACH_MS = 800              # spaCy-Modell so lange nach dem Start im Hintergrund laden (PERF-09)

HAKEN = {"an": "☑", "aus": "☐", "teil": "⊟"}
SPALTEN = ("kategorie", "text", "seiten", "anzahl", "kontext", "ersatz")
# Spalte -> (Breite, Mindestbreite, dehnbar) bei 100 %
SPALTEN_MASSE = {"#0": (185, 150, False), "kategorie": (130, 105, False), "text": (160, 130, True),
                 "seiten": (60, 52, False), "anzahl": (55, 48, False), "kontext": (210, 160, True),
                 "ersatz": (95, 85, False)}
ANALYSE_TEXT = "  Analysieren – Funde anzeigen  "
START_TEXT = "  Schwärzen starten  "
BAUM_HINWEIS = ("Kästchen (oder Leertaste) = Fund an/aus · Doppelklick auf eine Datei = Vorschau (dort per Klick "
               "oder Rahmen nachschwärzen) · Rechtsklick = mehr")
ANZEIGE_BEGRIFF_VORSCHAU = "Begriff (Vorschau)"
ANZEIGE_MANUELL = "Manuell (Vorschau)"
ANZEIGE_NACHSCHWAERZEN = "Manuell (Nachschwärzen)"
PLATZHALTER_MANUELL = attrappen.PLATZHALTER_MANUELL
PRUEFEN_ERKLAERUNG = ("„_PRUEFEN“ im Dateinamen heißt: noch nicht zur Weitergabe freigegeben – erst in der "
                      "Vorschau prüfen und dort „Freigeben“ drücken.")
STATUS_TEXT = {"fertig": "✔ fertig", "pruefen": "⚠ prüfen", "fehler": "✖ Fehler", "verworfen": "verworfen",
               "keine": "keine Ausgabe"}

_KATEGORIE_SCHLUESSEL = {eintrag[0] for eintrag in KATEGORIEN}
_NEUE_KATEGORIEN = bool(_KATEGORIE_SCHLUESSEL & {"beruf", "arbeitgeber", "diagnose", "medikament"})


def _texte_zur_engine(neue_kategorien: bool) -> tuple[str, str, str]:
    """Untertitel, Hinweiskasten und Hilfetext – wahrheitsgemäß für den Funktionsumfang der Engine (GR-09)."""
    if neue_kategorien:
        lesbar = "je nach Schutzstufe bleiben Diagnosen, Beruf, Arbeitgeber, Beträge und Orte lesbar"
        kasten = ("Nur je nach Schutzstufe erkannt: Diagnosen, Beruf, Arbeitgeber. Nicht erkannt werden: "
                  "Unterschriften, Handschrift, Freitext; Text in Bildern nur unsicher (OCR).")
        grenzen_kopf = "NICHT oder nur teilweise erkannt werden:\n"
        grenzen_umfang = ("  • Diagnosen, Krankheiten, Medikamente: nur bekannte Begriffe, geschwärzt erst in der "
                          "Schutzstufe „Maximal“ (sonst als Hinweis gemeldet)\n"
                          "  • Beruf, Arbeitgeber: nur mit Etikett oder Personenbezug (ab Schutzstufe „Hoch“); "
                          "Einkommen und Familienstand nicht\n")
    else:
        lesbar = "Diagnosen, Beruf, Arbeitgeber, Beträge und Orte bleiben lesbar"
        kasten = ("Nicht erkannt werden: Diagnosen, Beruf, Arbeitgeber, Unterschriften, Handschrift, Freitext; "
                  "Text in Bildern nur unsicher (OCR).")
        grenzen_kopf = "NICHT erkannt werden:\n"
        grenzen_umfang = ("  • Diagnosen, Krankheiten, ICD-Codes, Medikamente\n"
                          "  • Beruf, Arbeitgeber, Einkommen, Familienstand\n")
    untertitel = ("Ersetzt direkte Identifikatoren (Namen, IBAN, Adresse, Telefon …) durch Platzhalter wie "
                  f"[PERSON A] – eine Pseudonymisierung, keine vollständige Anonymisierung: {lesbar}. "
                  "Fundliste und Ergebnis müssen vor jeder Weitergabe geprüft werden.")
    hinweis = (kasten + " Ausgaben in Cloud-Ordnern (OneDrive, Dropbox …) werden mitsynchronisiert. "
               "Mehr: Hilfe → „Was wird nicht erkannt?“")
    grenzen = (
        "Das Programm ersetzt direkte Identifikatoren durch Platzhalter (Pseudonymisierung).\n\n"
        + grenzen_kopf + grenzen_umfang +
        "  • Unterschriften, Stempel, Handschrift\n"
        "  • Text in Bildern, Fotos und Logos wird per OCR nur unsicher gelesen (Handyfotos, geringe Auflösung)\n"
        "  • Freitext, aus dem eine Person erkennbar bleibt\n"
        "  • Dateinamen (die Ausgabe heißt neutral anonym_01.pdf; der Originalname steht in _zuordnung.txt)\n\n"
        "Deshalb: jede Ausgabe in der Vorschau prüfen (Doppelklick auf die Datei). Was dort noch zu sehen ist, "
        "per Klick oder Rahmen nachschwärzen.\n\n"
        "Pseudonymisierte Dokumente bleiben personenbezogene Daten. Für die Weitergabe an einen KI-Dienst "
        "braucht es weiterhin eine Rechtsgrundlage und in der Regel einen Auftragsverarbeitungsvertrag.\n\n"
        "Ausgaben in Ordnern, die mit OneDrive, Dropbox o. Ä. synchronisiert werden, landen ebenfalls in der "
        "Cloud. Per Dateidialog geöffnete Dateien merkt sich Windows unter „Zuletzt verwendet“."
    )
    return untertitel, hinweis, grenzen


UNTERTITEL, HINWEISKASTEN, GRENZEN_TEXT = _texte_zur_engine(_NEUE_KATEGORIEN)


# ----------------------------------------------------------------------
# Engine-Aufruf: Fähigkeiten, Ergebnisprüfung, Meldungs-Codes
# ----------------------------------------------------------------------
def _parameter(funktion) -> set | None:
    """Parameternamen einer Engine-Funktion; None, wenn sie beliebige Schlüsselwörter annimmt."""
    try:
        parameter = inspect.signature(funktion).parameters
    except (TypeError, ValueError):
        return None
    if any(p.kind is p.VAR_KEYWORD for p in parameter.values()):
        return None
    return set(parameter)


def kann(funktion, name: str) -> bool:
    """Kennt die Engine-Funktion den (neuen, optionalen) Parameter? Pflichtparameter aus Phase 1 werden
    immer direkt übergeben – ein umbenannter Parameter führt zu einem sichtbaren Fehler, nie zu Stille."""
    parameter = _parameter(funktion)
    return parameter is None or name in parameter


class Vertragsfehler(RuntimeError):
    """Die Engine hat ein Ergebnis geliefert, das nicht dem Vertrag entspricht."""


ANALYSE_PFLICHT = ("datei", "funde", "warnungen", "hinweise", "fehler", "seiten", "ocr_seiten", "ocr_cache")
FUND_PFLICHT = ("kategorie", "anzeige", "text", "ersatz", "seiten", "anzahl", "kontext")
SCHWAERZ_PFLICHT = ("ausgabe", "treffer", "warnungen", "hinweise", "reste", "fehler")


def _analyse_ergebnis_pruefen(ergebnis, pdf: Path) -> dict:
    """Prüft das Analyse-Ergebnis streng (KQ-07): fehlende Pflichtschlüssel sind ein Fehler, keine
    stille Entwarnung („0 Funde“)."""
    if not isinstance(ergebnis, dict):
        raise Vertragsfehler(f"analysiere_pdf lieferte {type(ergebnis).__name__} statt dict")
    fehlend = [k for k in ANALYSE_PFLICHT if k not in ergebnis]
    if fehlend:
        raise Vertragsfehler("analysiere_pdf: Ergebnis ohne " + ", ".join(fehlend))
    if not isinstance(ergebnis["funde"], list):
        raise Vertragsfehler("analysiere_pdf: „funde“ ist keine Liste")
    for nummer, fund in enumerate(ergebnis["funde"], 1):
        fehlend = [k for k in FUND_PFLICHT if k not in fund]
        if fehlend:
            raise Vertragsfehler(f"analysiere_pdf: Fund {nummer} ohne " + ", ".join(fehlend))
    ergebnis["datei"] = Path(ergebnis["datei"])
    ergebnis["warnungen"] = [str(w) for w in ergebnis["warnungen"] or []]
    ergebnis["hinweise"] = [str(h) for h in ergebnis["hinweise"] or []]
    return ergebnis


def _schwaerz_ergebnis_pruefen(ergebnis, pdf: Path) -> dict:
    if not isinstance(ergebnis, dict):
        raise Vertragsfehler(f"schwaerze_pdf lieferte {type(ergebnis).__name__} statt dict")
    fehlend = [k for k in SCHWAERZ_PFLICHT if k not in ergebnis]
    if fehlend:
        raise Vertragsfehler("schwaerze_pdf: Ergebnis ohne " + ", ".join(fehlend))
    if ergebnis["ausgabe"] is not None:
        ergebnis["ausgabe"] = Path(ergebnis["ausgabe"])
    ergebnis.setdefault("original", pdf)
    ergebnis["warnungen"] = [str(w) for w in ergebnis["warnungen"] or []]
    ergebnis["hinweise"] = [str(h) for h in ergebnis["hinweise"] or []]
    ergebnis["reste"] = [str(r) for r in ergebnis["reste"] or []]
    return ergebnis


def _fehler_ergebnis(pdf: Path, text: str) -> dict:
    """Analyse-Ergebnis für eine Datei, deren Analyse mit einer Ausnahme endete."""
    return {"datei": pdf, "funde": [], "warnungen": [], "hinweise": [], "fehler": text, "seiten": 0,
            "ocr_seiten": 0, "ocr_cache": {}}


def meldungs_codes(ergebnis: dict) -> set[str]:
    """Codes der strukturierten Meldungen (12.6). Liefert die Engine keine "meldungen", leitet die Attrappe
    sie aus den Texten ab – Entscheidungen der Oberfläche hängen nur an Codes (KQ-08)."""
    meldungen = ergebnis.get("meldungen")
    if meldungen is None:
        meldungen = attrappen.meldungen_aus_texten(ergebnis)
    return {str(m.get("code")) for m in meldungen if isinstance(m, dict) and m.get("code")}


# ----------------------------------------------------------------------
# Texte für den Nutzer
# ----------------------------------------------------------------------
_FEHLERTEXT_MUSTER = (
    (("permission denied", "zugriff verweigert", "errno 13", "winerror 5]", "winerror 32]",
      "used by another process", "von einem anderen prozess verwendet", "cannot remove file", "errno 1]",
      "errno 30]", "read-only file system"),
     "Ausgabedatei konnte nicht geschrieben werden – vermutlich ist sie in einem anderen Programm (PDF-Reader) "
     "geöffnet oder der Ordner ist schreibgeschützt. Bitte die Datei schließen oder einen anderen Zielordner "
     "wählen und erneut schwärzen."),
    (("file exists", "errno 17]", "winerror 183]", "bereits vorhanden", "not a directory", "errno 20]",
      "winerror 267]"),
     "Im Zielordner liegt bereits eine Datei mit dem Namen des Ausgabeordners („anonymisiert“) – bitte "
     "umbenennen oder einen anderen Zielordner wählen."),
    (("no space left", "errno 28]", "winerror 112]", "nicht genügend speicherplatz"),
     "Kein Speicherplatz mehr auf dem Laufwerk – bitte Platz schaffen oder anderen Zielordner wählen."),
    (("winerror 206]", "winerror 3]", "errno 36]", "file name too long"),
     "Der Dateipfad ist zu lang für Windows – bitte den Ordner näher an C:\\ kopieren oder einen kurzen "
     "Zielordner wählen."),
    (("as type pdf", "cannot open empty file", "no objects found", "not a pdf", "format error"),
     "Die Datei ist keine lesbare PDF-Datei (beschädigt, leer oder nur umbenannt) – bitte neu aus dem "
     "Ursprungsprogramm als PDF speichern."),
)


def _fehlertext_verstaendlich(text: str) -> str:
    """Übersetzt eine Fehlermeldung der Engine (auch deutsche Windows-Systemtexte) in eine Handlungsanweisung;
    die Systemmeldung bleibt gekürzt in Klammern erhalten (GR-04)."""
    tl = (text or "").lower()
    for muster, meldung in _FEHLERTEXT_MUSTER:
        if any(m in tl for m in muster):
            kurz = text if len(text) <= 120 else text[:117] + "…"
            return f"{meldung} (Systemmeldung: {kurz})"
    return text


def _verstaendliche_fehlermeldung(fehler: BaseException, pfad: Path | None = None) -> str:
    """Übersetzt eine Ausnahme in eine Handlungsanweisung."""
    text = str(fehler)
    if isinstance(fehler, PermissionError):
        return _FEHLERTEXT_MUSTER[0][1]
    if isinstance(fehler, (FileExistsError, NotADirectoryError)):
        return _FEHLERTEXT_MUSTER[1][1]
    if isinstance(fehler, OSError) and getattr(fehler, "errno", None) == errno.ENOSPC:
        return _FEHLERTEXT_MUSTER[2][1]
    if pfad is not None and sys.platform == "win32" and len(str(pfad)) > 240:
        return _FEHLERTEXT_MUSTER[3][1]
    uebersetzt = _fehlertext_verstaendlich(text)
    if uebersetzt != text:
        return uebersetzt
    return f"Unerwarteter Fehler ({type(fehler).__name__}: {text[:200]}) – Details stehen in fehler.log."


def _kontext_anzeige(kontext: str) -> str:
    """Kürzt den Vorlauf vor dem Fund, damit in der schmalen Kontextspalte der Fund selbst zu sehen ist (GR-05)."""
    kontext = str(kontext or "").replace("\n", " ")
    pos = kontext.find("»")
    if pos > KONTEXT_VORLAUF:
        return "…" + kontext[pos - KONTEXT_VORLAUF:].lstrip()
    return kontext


def _seitenzahl(pdf: Path) -> int:
    """Seitenzahl für den Fortschrittsbalken (1, wenn das PDF nicht lesbar ist)."""
    try:
        with fitz.open(pdf) as doc:
            return max(1, len(doc))
    except Exception:
        return 1


def _profil_name(name: str) -> str:
    return attrappen.PROFIL_ANZEIGE.get(name, name)


# ----------------------------------------------------------------------
# Dialog: Spalten der Kundenliste zuordnen
# ----------------------------------------------------------------------
class SpaltenDialog:
    """Zuordnung der CSV-Spalten zu Merkmalen der Kundenliste, wenn die Kopfzeile nicht erkannt wurde.
    Nicht blockierend: fertig(spalten) wird mit {merkmal: spaltenname | spaltenindex} aufgerufen."""

    NICHT = "— nicht verwenden —"

    def __init__(self, app, csv_pfad: Path, vorschau: dict, fertig):
        self.app = app
        self.fertig = fertig
        self.zeilen = vorschau["zeilen"]
        self.merkmale = dict(getattr(sys.modules.get(Kundenliste.__module__), "MERKMALE", None)
                             or attrappen.MERKMALE)
        breite = max((len(z) for z in self.zeilen), default=0)
        self.fenster = tk.Toplevel(app.root)
        self.fenster.title("Kundenliste – Spalten zuordnen")
        self.fenster.configure(bg=FARBE_KARTE)
        self.fenster.transient(app.root)
        rahmen = tk.Frame(self.fenster, bg=FARBE_KARTE, padx=14, pady=10)
        rahmen.pack(fill="both", expand=True)
        tk.Label(rahmen, text=f"Die Spalten von „{csv_pfad.name}“ wurden nicht erkannt. Bitte angeben, was in "
                              "welcher Spalte steht – mindestens Name, Nachname, Kundennummer, IBAN oder E-Mail.",
                 font=app.f_normal, bg=FARBE_KARTE, wraplength=app._px(560), justify="left").pack(anchor="w")
        erste = self.zeilen[0] if self.zeilen else []
        kopf_vermutet = len(self.zeilen) > 1 and not any(ch.isdigit() for ch in "".join(erste))
        self.kopf_var = tk.BooleanVar(value=kopf_vermutet)
        tk.Checkbutton(rahmen, text="Erste Zeile enthält Spaltenüberschriften (wird nicht importiert)",
                       variable=self.kopf_var, font=app.f_normal, bg=FARBE_KARTE,
                       activebackground=FARBE_KARTE).pack(anchor="w", pady=(6, 4))
        gitter = tk.Frame(rahmen, bg=FARBE_KARTE)
        gitter.pack(fill="x")
        auswahl = [self.NICHT] + list(self.merkmale.values())
        vorschlag = attrappen.spalten_erkennen(erste) if kopf_vermutet else {}
        index_zu_merkmal = {i: m for m, i in vorschlag.items()}
        self.boxen: list[ttk.Combobox] = []
        for i in range(breite):
            beispiele = [z[i] for z in self.zeilen[:4] if i < len(z) and z[i]]
            tk.Label(gitter, text=f"Spalte {i + 1}", font=app.f_fett, bg=FARBE_KARTE).grid(
                row=i, column=0, sticky="w", padx=(0, 8), pady=1)
            text = " · ".join(beispiele)[:60] or "(leer)"
            tk.Label(gitter, text=text, font=app.f_normal, bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU,
                     anchor="w", width=36).grid(row=i, column=1, sticky="w", padx=(0, 8))
            box = ttk.Combobox(gitter, values=auswahl, state="readonly", width=28)
            box.set(self.merkmale.get(index_zu_merkmal.get(i), self.NICHT))
            box.grid(row=i, column=2, sticky="w")
            self.boxen.append(box)
        self.meldung = tk.Label(rahmen, text="", font=app.f_normal, bg=FARBE_KARTE, fg=FARBE_ROT,
                                wraplength=app._px(560), justify="left")
        self.meldung.pack(anchor="w", pady=(6, 0))
        knoepfe = tk.Frame(rahmen, bg=FARBE_KARTE)
        knoepfe.pack(fill="x", pady=(8, 0))
        self.ok_knopf = app._knopf(knoepfe, "Importieren", self.bestaetigen)
        self.ok_knopf.pack(side="right")
        app._knopf(knoepfe, "Abbrechen", self.abbrechen, True).pack(side="right", padx=(0, 8))
        self.fenster.protocol("WM_DELETE_WINDOW", self.abbrechen)

    def zuordnung(self) -> dict | None:
        """{merkmal: spaltenname (mit Kopfzeile) | spaltenindex (ohne)} oder None (Meldung im Dialog)."""
        name_zu_merkmal = {v: k for k, v in self.merkmale.items()}
        gewaehlt: dict[str, int] = {}
        for i, box in enumerate(self.boxen):
            merkmal = name_zu_merkmal.get(box.get())
            if merkmal is None:
                continue
            if merkmal in gewaehlt:
                self.meldung.config(text=f"„{box.get()}“ ist mehreren Spalten zugeordnet – bitte nur einer.")
                return None
            gewaehlt[merkmal] = i
        if not any(m in gewaehlt for m in attrappen.STARKE_MERKMALE):
            self.meldung.config(text="Bitte mindestens eine Spalte mit Name, Nachname, Kundennummer, IBAN oder "
                                     "E-Mail zuordnen – sonst kann kein Kunde sicher erkannt werden.")
            return None
        if not self.kopf_var.get():
            return gewaehlt
        kopf = self.zeilen[0] if self.zeilen else []
        namen = {}
        for merkmal, i in gewaehlt.items():
            name = kopf[i] if i < len(kopf) else ""
            if not name or kopf.count(name) > 1:
                self.meldung.config(text="Die Spaltenüberschriften sind leer oder doppelt – bitte in der CSV-Datei "
                                         "eindeutige Überschriften vergeben oder „Erste Zeile enthält "
                                         "Spaltenüberschriften“ abwählen.")
                return None
            namen[merkmal] = name
        return namen

    def bestaetigen(self):
        spalten = self.zuordnung()
        if spalten is None:
            return
        self.fenster.destroy()
        self.fertig(spalten)

    def abbrechen(self):
        self.fenster.destroy()


# ----------------------------------------------------------------------
# Hauptfenster
# ----------------------------------------------------------------------
class AnonymisiererApp:
    """Hauptfenster: Dateien wählen, analysieren, Funde prüfen, schwärzen, in der Vorschau freigeben."""

    def __init__(self, root, einstellungen: dict | None = None, modell_vorladen: bool = False):
        self.root = root
        self.einstellungen = dict(einstellungen) if einstellungen is not None else dateien.einstellungen_laden()
        self.root.title(f"PDF-Anonymisierer {__version__}")
        self.root.configure(bg=FARBE_HINTERGRUND)

        self.dateien: list[Path] = []
        self.analyse_ergebnisse: dict[Path, dict] = {}   # Pfad -> Ergebnis von analysiere_pdf
        self.zeilen: dict[str, Path] = {}                # iid der Datei-Zeile -> Pfad
        self.beschriftungen: dict[str, str] = {}         # iid -> Anzeigename (relativ zum Stamm)
        self.manuell: dict[Path, dict[int, dict]] = {}   # Pfad -> {mid: manuelle Markierung aus der Vorschau}
        self._manuell_zaehler = 0
        self.lauf_immer: dict[Path, list[str]] = {}      # Pfad -> „überall in diesem Dokument schwärzen“
        self.ausgaben: dict[Path, dict] = {}             # Pfad -> {"pfad", "status", "verdacht", "ergebnis"}
        self.vorschauen: dict[Path, object] = {}         # Pfad -> offenes Vorschau-Fenster
        self.kundenliste = None
        self.laeuft = False
        self.lauf_art: str | None = None
        self.abbruch: threading.Event | None = None
        self.ocr = None
        self.analyse_veraltet = False
        self.warnungen_anzahl = 0
        self.letzte_ausgabeordner: list[Path] = []
        self.letzter_dialog: tuple | None = None         # (Art, Titel, Text) des letzten Dialogs
        self.laeufe_beendet = 0                          # Zähler abgeschlossener Läufe (für Tests/Skripte)
        self.beendet = False                             # Fenster wird geschlossen: keine Tk-Aufrufe mehr
        self.instanz_sperre = None                       # von main() gesetzt (Einzelinstanz, GR-10)
        self.basis_profil = attrappen.STANDARD_PROFIL
        self.vorladen_thread: threading.Thread | None = None
        self._ner_sperre = threading.Lock()              # lade_ner nie doppelt gleichzeitig (Vorladen/Analyse)
        self._hauptthread_fehler_gemeldet = False
        self._anpassung_laeuft = False
        self.dnd_aktiv = False
        self._sperrbar: list = []
        self._einstellungen_werden_gesetzt = False
        self._profil_wird_gesetzt = False
        self._anpassung_geplant = False
        self._alter_threading_haken = threading.excepthook

        self.skalierung = float(self.root.tk.call("tk", "scaling"))
        self.k = self.skalierung / BASIS_SKALIERUNG     # 1.0 = Windows 100 %
        self._schriften_anlegen()
        self._geometrie_setzen()
        self._baue_oberflaeche()
        self._menue_anlegen()
        self._einstellungen_anwenden()
        self._kundenliste_laden()

        self.root.protocol("WM_DELETE_WINDOW", self.schliessen)
        self.root.report_callback_exception = self._fehler_melden
        threading.excepthook = self._thread_excepthook
        self.root.bind("<Configure>", self._fenster_geaendert)
        self.root.bind("<Alt-a>", lambda e: self.analyse_knopf.invoke())
        self.root.bind("<Alt-s>", lambda e: self.start_knopf.invoke())
        self.root.bind("<Alt-v>", lambda e: self.vorschau_knopf.invoke())
        self.root.after_idle(self._oben_anpassen)
        if modell_vorladen:
            self.root.after(VORLADEN_NACH_MS, self.modell_vorladen)

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _schriften_anlegen(self):
        self.f_normal = tkfont.Font(family=SCHRIFT, size=9)
        self.f_fett = tkfont.Font(family=SCHRIFT, size=9, weight="bold")
        self.f_titel = (SCHRIFT, 19, "bold")
        self.f_karte = (SCHRIFT, 11, "bold")
        self.f_knopf = (SCHRIFT, 10, "bold")
        self.f_mono = (SCHRIFT_MONO, 9)
        self.zeilenhoehe = self.f_normal.metrics("linespace")
        stil = ttk.Style(self.root)
        stil.configure("Treeview", font=self.f_normal, rowheight=max(20, self.zeilenhoehe + 6))
        stil.configure("Treeview.Heading", font=self.f_fett)

    def _px(self, wert: int) -> int:
        """Entwurfsmaß (bei 100 %) in Bildschirmpixel umrechnen."""
        return max(1, round(wert * self.k))

    def _geometrie_setzen(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        breite = min(self._px(FENSTER_BREITE), max(FENSTER_MINDESTMASS[0], sw - 24))
        hoehe = min(self._px(FENSTER_HOEHE), max(FENSTER_MINDESTMASS[1], sh - FENSTER_RAND_UNTEN))
        self.root.minsize(*FENSTER_MINDESTMASS)
        geometrie = f"{breite}x{hoehe}"
        gespeichert = self.einstellungen.get("fenster")
        if isinstance(gespeichert, str):
            m = re.fullmatch(r"(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?", gespeichert)
            if m:
                b, h = int(m.group(1)), int(m.group(2))
                if FENSTER_MINDESTMASS[0] <= b <= sw and FENSTER_MINDESTMASS[1] <= h <= sh:
                    geometrie = f"{b}x{h}"
                    if m.group(3) and m.group(4):
                        x, y = int(m.group(3)), int(m.group(4))
                        if 0 <= x < sw - 100 and 0 <= y < sh - 100:
                            geometrie += f"+{x}+{y}"
        self.root.geometry(geometrie)
        self._start_hoehe = int(geometrie.split("x")[1].split("+")[0])
        # Kleine Bildschirme (Laptops mit 1366x768 oder hoher Skalierung): maximiert starten
        if sh - FENSTER_RAND_UNTEN < self._px(FENSTER_HOEHE) or self.einstellungen.get("maximiert"):
            self._maximieren()

    def _maximieren(self):
        try:
            self.root.state("zoomed")                   # Windows
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)   # Linux-Fenstermanager
            except tk.TclError:
                pass

    def _ist_maximiert(self) -> bool:
        try:
            if self.root.state() == "zoomed":
                return True
        except tk.TclError:
            pass
        try:
            return bool(self.root.attributes("-zoomed"))
        except tk.TclError:
            return False

    def _baue_oberflaeche(self):
        haupt = tk.Frame(self.root, bg=FARBE_HINTERGRUND, padx=16, pady=10)
        haupt.pack(fill="both", expand=True)
        self.haupt = haupt

        self.kopf = tk.Frame(haupt, bg=FARBE_HINTERGRUND)
        self.kopf.pack(fill="x")
        tk.Label(self.kopf, text="PDF-Anonymisierer", font=self.f_titel,
                 bg=FARBE_HINTERGRUND, fg=FARBE_TEXT).pack(anchor="w")
        self.untertitel = tk.Label(self.kopf, text=UNTERTITEL, font=self.f_normal, bg=FARBE_HINTERGRUND,
                                   fg=FARBE_TEXT_GRAU, wraplength=self._px(840), justify="left")
        self.untertitel.pack(anchor="w", pady=(0, 6))

        # Unten verankert (zuerst packen, damit sie nie abgeschnitten werden): Aktionsleiste, Protokoll
        self._baue_aktionsleiste(haupt)
        self._baue_protokoll(haupt)

        # Oben: scrollbarer Bereich mit Schritt 1 und 2
        self.oben_rahmen = tk.Frame(haupt, bg=FARBE_HINTERGRUND)
        self.oben_rahmen.pack(fill="x")
        self.oben_canvas = tk.Canvas(self.oben_rahmen, bg=FARBE_HINTERGRUND, highlightthickness=0, bd=0)
        self.oben_roll = ttk.Scrollbar(self.oben_rahmen, orient="vertical", command=self.oben_canvas.yview)
        self.oben_canvas.configure(yscrollcommand=self.oben_roll.set)
        self.oben_canvas.pack(side="left", fill="x", expand=True)
        self.oben = tk.Frame(self.oben_canvas, bg=FARBE_HINTERGRUND)
        self._oben_fenster = self.oben_canvas.create_window((0, 0), window=self.oben, anchor="nw")
        self.oben.bind("<Configure>", lambda e: self._anpassung_planen())
        self.oben_canvas.bind("<Configure>",
                              lambda e: self.oben_canvas.itemconfigure(self._oben_fenster, width=e.width))
        self.root.bind_all("<MouseWheel>", self._mausrad, add="+")
        self.root.bind_all("<Button-4>", self._mausrad, add="+")
        self.root.bind_all("<Button-5>", self._mausrad, add="+")

        self._baue_karte_dateien(self.oben)
        self._baue_karte_kategorien(self.oben)

        # Schritt 3 füllt den Rest
        self._baue_karte_funde(haupt)

    def _baue_aktionsleiste(self, eltern):
        leiste = tk.Frame(eltern, bg=FARBE_KARTE, padx=12, pady=6,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        leiste.pack(side="bottom", fill="x", pady=(6, 0))
        self.aktionsleiste = leiste
        # Statuszeile in eigener Zeile über die volle Breite (GR-06): zwischen Knöpfen und Warnzähler
        # wurde sie abgeschnitten.
        self.status_label = tk.Label(leiste, text="Bereit.", font=self.f_normal, bg=FARBE_KARTE,
                                     fg=FARBE_TEXT_GRAU, anchor="w")
        self.status_label.pack(side="bottom", fill="x", pady=(2, 0))
        knoepfe = tk.Frame(leiste, bg=FARBE_KARTE)
        knoepfe.pack(side="top", fill="x")
        # Beide Hauptaktionen in der unten verankerten Leiste (GR-01): der Analysieren-Knopf lag im
        # scrollbaren Einstellbereich und war auf 1366x768 nur nach Scrollen erreichbar.
        self.analyse_knopf = self._knopf(knoepfe, ANALYSE_TEXT, self.analysieren)
        self.analyse_knopf.pack(side="left")
        self.start_knopf = self._knopf(knoepfe, START_TEXT, self.schwaerzen)
        self.start_knopf.pack(side="left", padx=(8, 0))
        self.start_knopf.config(state="disabled")
        self.abbrechen_knopf = self._knopf(knoepfe, "Abbrechen", self.abbrechen, True)
        self.abbrechen_knopf.pack(side="left", padx=(8, 0))
        self.abbrechen_knopf.config(state="disabled")
        self.ordner_knopf = self._knopf(knoepfe, "Ergebnisordner öffnen", self.ergebnisordner_oeffnen, True)
        self.ordner_knopf.pack(side="left", padx=(8, 0))
        self.ordner_knopf.config(state="disabled")
        # Fortschritt und Warnzähler in eigener Zeile: in der Knopfzeile bekam der Balken bei breiten
        # Systemschriften (z. B. DejaVu Sans, 150 % Skalierung) keinen Platz mehr und verschwand.
        fortschritt_zeile = tk.Frame(leiste, bg=FARBE_KARTE)
        fortschritt_zeile.pack(side="top", fill="x", pady=(4, 0))
        self.warn_label = tk.Label(fortschritt_zeile, text="", font=self.f_fett, bg=FARBE_KARTE,
                                   fg=FARBE_WARNUNG)
        self.warn_label.pack(side="right", padx=(8, 0))
        self.fortschritt = ttk.Progressbar(fortschritt_zeile, mode="determinate")
        self.fortschritt.pack(side="left", fill="x", expand=True)

    def _baue_protokoll(self, eltern):
        rahmen = tk.Frame(eltern, bg=FARBE_KARTE, padx=8, pady=4,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        rahmen.pack(side="bottom", fill="x", pady=(6, 0))
        self.protokoll_rahmen = rahmen
        innen = tk.Frame(rahmen, bg=FARBE_KARTE)
        innen.pack(fill="x")
        self.protokoll = tk.Text(innen, height=PROTOKOLL_ZEILEN, width=40, font=self.f_mono, relief="flat",
                                 highlightthickness=1, highlightbackground=FARBE_RAND,
                                 bg="#fafafa", state="disabled", wrap="word")
        roll = ttk.Scrollbar(innen, orient="vertical", command=self.protokoll.yview)
        self.protokoll.configure(yscrollcommand=roll.set)
        self.protokoll.pack(side="left", fill="x", expand=True)
        roll.pack(side="right", fill="y")
        for stil, farbe in [("ok", FARBE_GRUEN), ("warnung", FARBE_WARNUNG), ("fehler", FARBE_ROT),
                            ("grau", FARBE_TEXT_GRAU), ("hinweis", FARBE_AKZENT), ("trenner", FARBE_TEXT_GRAU)]:
            self.protokoll.tag_configure(stil, foreground=farbe)

    def _baue_karte_dateien(self, eltern):
        karte1 = self._karte(eltern, "1 · PDF-Dateien")
        self.drop_zone = tk.Label(karte1, text="", font=(SCHRIFT, 10), bg=FARBE_AKZENT_HELL, fg=FARBE_AKZENT,
                                  height=1, pady=6, cursor="hand2", highlightthickness=2,
                                  highlightbackground="#b9cfee")
        self.drop_zone.pack(fill="x", pady=(2, 6))
        self.drop_zone.bind("<Button-1>", lambda e: self.dateien_waehlen())
        if DND_VERFUEGBAR and DND_FILES is not None:
            try:
                self.drop_zone.drop_target_register(DND_FILES)
                self.drop_zone.dnd_bind("<<Drop>>", self._drop_ereignis)
                self.dnd_aktiv = True
            except Exception:
                self.dnd_aktiv = False
        self.drop_zone.config(text="⬇  " + ("PDFs oder ganze Ordner hierher ziehen  (oder klicken zum Auswählen)"
                                            if self.dnd_aktiv else
                                            "Drag & Drop nicht verfügbar – klicken zum Auswählen"))

        zeile = tk.Frame(karte1, bg=FARBE_KARTE)
        zeile.pack(fill="x")
        k1 = self._knopf(zeile, "Dateien auswählen …", self.dateien_waehlen, True)
        k1.pack(side="left")
        k2 = self._knopf(zeile, "Ordner auswählen …", self.ordner_waehlen, True)
        k2.pack(side="left", padx=(6, 0))
        k3 = self._knopf(zeile, "Liste leeren", self.liste_leeren, True)
        k3.pack(side="right")
        self._sperrbar += [k1, k2, k3]
        self.datei_hinweis = tk.Label(zeile, text="Noch keine Dateien. Die Liste erscheint unten in Schritt 3.",
                                      font=self.f_normal, bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU, anchor="w")
        self.datei_hinweis.pack(side="left", padx=(12, 0), fill="x", expand=True)

        ziel = tk.Frame(karte1, bg=FARBE_KARTE)
        ziel.pack(fill="x", pady=(6, 0))
        self.zielordner_aktiv = tk.BooleanVar(value=False)
        self.zielordner_var = tk.StringVar(value="")
        zk = tk.Checkbutton(ziel, text="Alle Ergebnisse in einen gemeinsamen Zielordner:",
                            variable=self.zielordner_aktiv, font=self.f_normal, bg=FARBE_KARTE,
                            activebackground=FARBE_KARTE, anchor="w")
        zk.pack(side="left")
        self.zielordner_feld = tk.Entry(ziel, textvariable=self.zielordner_var, font=self.f_normal, width=28,
                                        relief="flat", highlightthickness=1, highlightbackground=FARBE_RAND)
        self.zielordner_feld.pack(side="left", fill="x", expand=True, padx=(6, 0))
        zb = self._knopf(ziel, "Wählen …", self.zielordner_waehlen, True)
        zb.pack(side="left", padx=(6, 0))
        self._sperrbar += [zk, self.zielordner_feld, zb]

        self.freigabe_var = tk.BooleanVar(value=True)
        fk = tk.Checkbutton(karte1, text="Freigabe vor Weitergabe erforderlich (Ausgaben heißen „_PRUEFEN“, bis "
                                         "sie in der Vorschau freigegeben sind – empfohlen)",
                            variable=self.freigabe_var, font=self.f_normal, bg=FARBE_KARTE,
                            activebackground=FARBE_KARTE, anchor="w", justify="left")
        fk.pack(fill="x", pady=(4, 0))
        self.freigabe_knopf = fk
        self._sperrbar.append(fk)

    def _baue_karte_kategorien(self, eltern):
        karte2 = tk.Frame(eltern, bg=FARBE_KARTE, padx=14, pady=8,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        karte2.pack(fill="x", pady=(0, 8))
        self.karte2 = karte2
        titelzeile = tk.Frame(karte2, bg=FARBE_KARTE)
        titelzeile.pack(fill="x", pady=(0, 2))
        tk.Label(titelzeile, text="2 · Was soll erkannt werden?", font=self.f_karte,
                 bg=FARBE_KARTE, fg=FARBE_TEXT).pack(side="left")
        tk.Label(titelzeile, text="→ danach unten „Analysieren“ drücken", font=self.f_normal,
                 bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU).pack(side="right")

        # Schutzstufe (Profil) über den Kategorien: die Häkchen folgen der Stufe
        stufe = tk.Frame(karte2, bg=FARBE_KARTE)
        stufe.pack(fill="x", pady=(2, 0))
        tk.Label(stufe, text="Schutzstufe:", font=self.f_fett, bg=FARBE_KARTE).pack(side="left")
        self.profil_var = tk.StringVar(value=attrappen.STANDARD_PROFIL)
        self.profil_knoepfe: dict[str, tk.Radiobutton] = {}
        for name in attrappen.PROFIL_REIHENFOLGE + (attrappen.BENUTZERDEFINIERT,):
            rb = tk.Radiobutton(stufe, text=_profil_name(name), value=name, variable=self.profil_var,
                                command=self._profil_gewaehlt, font=self.f_normal, bg=FARBE_KARTE,
                                activebackground=FARBE_KARTE)
            rb.pack(side="left", padx=(8, 0))
            self.profil_knoepfe[name] = rb
            self._sperrbar.append(rb)
        self.profil_beschreibung = tk.Label(karte2, text="", font=self.f_normal, bg=FARBE_KARTE,
                                            fg=FARBE_TEXT_GRAU, anchor="w", justify="left",
                                            wraplength=self._px(820))
        self.profil_beschreibung.pack(fill="x", pady=(0, 4))

        gitter = tk.Frame(karte2, bg=FARBE_KARTE)
        gitter.pack(fill="x")
        self.kategorie_vars: dict[str, tk.BooleanVar] = {}
        for i, eintrag in enumerate(KATEGORIEN):
            schluessel, anzeige = eintrag[0], eintrag[1]
            standard = bool(eintrag[4]) if len(eintrag) > 4 else True
            var = tk.BooleanVar(value=standard)
            self.kategorie_vars[schluessel] = var
            cb = tk.Checkbutton(gitter, text=anzeige, variable=var, font=self.f_normal,
                                bg=FARBE_KARTE, activebackground=FARBE_KARTE, anchor="w")
            cb.grid(row=i // KATEGORIE_SPALTEN, column=i % KATEGORIE_SPALTEN, sticky="w", padx=(0, 12))
            self._sperrbar.append(cb)
            var.trace_add("write", self._kategorie_geaendert)
        for spalte in range(KATEGORIE_SPALTEN):
            gitter.columnconfigure(spalte, weight=1)

        listen = tk.Frame(karte2, bg=FARBE_KARTE)
        listen.pack(fill="x", pady=(8, 0))
        links = tk.Frame(listen, bg=FARBE_KARTE)
        links.pack(side="left", fill="both", expand=True, padx=(0, 8))
        rechts = tk.Frame(listen, bg=FARBE_KARTE)
        rechts.pack(side="left", fill="both", expand=True)
        tk.Label(links, text="Zusätzlich IMMER schwärzen (ein Begriff pro Zeile):",
                 font=self.f_fett, bg=FARBE_KARTE).pack(anchor="w")
        self.immer_feld = tk.Text(links, height=2, width=30, font=self.f_normal, relief="flat", undo=False,
                                  highlightthickness=1, highlightbackground=FARBE_RAND, bg="#fafafa")
        self.immer_feld.pack(fill="x")
        tk.Label(rechts, text="NIE schwärzen (z. B. eigene Firmen-/Beraternamen):",
                 font=self.f_fett, bg=FARBE_KARTE).pack(anchor="w")
        self.nie_feld = tk.Text(rechts, height=2, width=30, font=self.f_normal, relief="flat", undo=False,
                                highlightthickness=1, highlightbackground=FARBE_RAND, bg="#fafafa")
        self.nie_feld.pack(fill="x")
        for feld in (self.immer_feld, self.nie_feld):
            feld.bind("<<Modified>>", self._text_geaendert)
            self._sperrbar.append(feld)

        kunden = tk.Frame(karte2, bg=FARBE_KARTE)
        kunden.pack(fill="x", pady=(6, 0))
        tk.Label(kunden, text="Kundenliste:", font=self.f_fett, bg=FARBE_KARTE).pack(side="left")
        self.kunden_entfernen_knopf = self._knopf(kunden, "Entfernen", self.kundenliste_entfernen, True)
        self.kunden_entfernen_knopf.pack(side="right")
        self.kunden_import_knopf = self._knopf(kunden, "Importieren …", self.kundenliste_importieren, True)
        self.kunden_import_knopf.pack(side="right", padx=(0, 6))
        self._sperrbar.append(self.kunden_import_knopf)
        self.kunden_label = tk.Label(kunden, text="", font=self.f_normal, bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU,
                                     anchor="w", justify="left")
        self.kunden_label.pack(side="left", padx=(8, 0), fill="x", expand=True)

    def _baue_karte_funde(self, eltern):
        karte3 = tk.Frame(eltern, bg=FARBE_KARTE, padx=14, pady=8,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        karte3.pack(fill="both", expand=True, pady=(0, 8))
        self.karte3 = karte3
        titelzeile = tk.Frame(karte3, bg=FARBE_KARTE)
        titelzeile.pack(fill="x")
        tk.Label(titelzeile, text="3 · Funde prüfen, dann schwärzen", font=self.f_karte,
                 bg=FARBE_KARTE, fg=FARBE_TEXT).pack(side="left")
        self.entfernen_knopf = self._knopf(titelzeile, "Datei aus Liste entfernen", self.datei_entfernen, True)
        self.entfernen_knopf.pack(side="right")
        b2 = self._knopf(titelzeile, "Alle aus", lambda: self.alle_setzen("aus"), True)
        b2.pack(side="right", padx=(0, 6))
        b1 = self._knopf(titelzeile, "Alle an", lambda: self.alle_setzen("an"), True)
        b1.pack(side="right", padx=(0, 6))
        self.vorschau_knopf = self._knopf(titelzeile, "Vorschau …", self.vorschau_auswahl, True)
        self.vorschau_knopf.pack(side="right", padx=(0, 6))
        self._sperrbar += [b1, b2, self.entfernen_knopf, self.vorschau_knopf]
        self.baum_hinweis = tk.Label(karte3, text=BAUM_HINWEIS, font=self.f_normal, bg=FARBE_KARTE,
                                     fg=FARBE_TEXT_GRAU, anchor="w", justify="left", wraplength=self._px(840))
        self.baum_hinweis.pack(anchor="w", fill="x")

        # Hinweiskasten zuerst unten verankern: wird das Fenster knapp, schrumpft die Fundliste, nicht der Hinweis
        self.hinweis_kasten = tk.Label(karte3, text=HINWEISKASTEN, font=self.f_normal, justify="left",
                                       anchor="w", bg=FARBE_HINWEIS_HINTERGRUND, fg="#7c4a03", padx=8, pady=3,
                                       highlightthickness=1, highlightbackground=FARBE_HINWEIS_RAND,
                                       wraplength=self._px(840))
        self.hinweis_kasten.pack(side="bottom", fill="x", pady=(2, 0))

        baum_rahmen = tk.Frame(karte3, bg=FARBE_KARTE)
        baum_rahmen.pack(fill="both", expand=True, pady=(2, 2))
        self.baum_rahmen = baum_rahmen
        baum_rahmen.rowconfigure(0, weight=1)
        baum_rahmen.columnconfigure(0, weight=1)
        self.baum = ttk.Treeview(baum_rahmen, columns=SPALTEN, show="tree headings",
                                 selectmode="browse", height=4)
        self.baum.heading("#0", text="Häkchen / Datei")
        self.baum.heading("kategorie", text="Kategorie")
        self.baum.heading("text", text="Gefundener Text")
        self.baum.heading("seiten", text="Seite(n)")
        self.baum.heading("anzahl", text="Anzahl")
        self.baum.heading("kontext", text="Kontext")
        self.baum.heading("ersatz", text="Ersatz")
        for spalte, (breite, mindest, dehnbar) in SPALTEN_MASSE.items():
            self.baum.column(spalte, width=self._px(breite), minwidth=self._px(mindest), stretch=dehnbar,
                             anchor="center" if spalte in ("seiten", "anzahl") else "w")
        roll_y = ttk.Scrollbar(baum_rahmen, orient="vertical", command=self.baum.yview)
        roll_x = ttk.Scrollbar(baum_rahmen, orient="horizontal", command=self.baum.xview)
        self.baum.configure(yscrollcommand=roll_y.set, xscrollcommand=roll_x.set)
        self.baum.grid(row=0, column=0, sticky="nsew")
        roll_y.grid(row=0, column=1, sticky="ns")
        roll_x.grid(row=1, column=0, sticky="ew")
        self.baum.tag_configure("aus", foreground=FARBE_TEXT_GRAU)
        self.baum.tag_configure("teil", foreground=FARBE_WARNUNG)
        self.baum.tag_configure("datei", font=self.f_fett)
        self.baum.bind("<Button-1>", self._baum_klick)
        self.baum.bind("<Double-Button-1>", self._baum_doppelklick)
        self.baum.bind("<Button-3>", self._kontextmenue)
        self.baum.bind("<space>", self._taste_leer)
        self.baum.bind("<Delete>", lambda e: self.datei_entfernen())
        self.baum.bind("<Return>", lambda e: self.vorschau_auswahl())
        self.baum.bind("<<TreeviewSelect>>", self._auswahl_geaendert)
        self.baum.bind("<Configure>", self._spalten_anpassen)

    def _spalten_anpassen(self, ereignis=None):
        """Dehnbare Spalten füllen die verfügbare Breite; reicht sie nicht, bleibt die Mindestbreite
        (dann hilft die horizontale Bildlaufleiste)."""
        try:
            verfuegbar = self.baum.winfo_width() - 4
        except tk.TclError:
            return
        if verfuegbar < 50:
            return
        fest = sum(self.baum.column(sp, "width") for sp, (_, _, dehnbar) in SPALTEN_MASSE.items() if not dehnbar)
        dehnbare = [sp for sp, (_, _, dehnbar) in SPALTEN_MASSE.items() if dehnbar]
        rest = verfuegbar - fest
        gesamt_entwurf = sum(SPALTEN_MASSE[sp][0] for sp in dehnbare)
        for sp in dehnbare:
            anteil = SPALTEN_MASSE[sp][0] / gesamt_entwurf
            breite = max(self._px(SPALTEN_MASSE[sp][1]), int(rest * anteil))
            self.baum.column(sp, width=breite)

    def _menue_anlegen(self):
        menue = tk.Menu(self.root)
        kunden = tk.Menu(menue, tearoff=0)
        kunden.add_command(label="Kundenliste importieren …", command=self.kundenliste_importieren)
        kunden.add_command(label="Kundenliste entfernen", command=self.kundenliste_entfernen)
        menue.add_cascade(label="Kundenliste", menu=kunden)
        hilfe = tk.Menu(menue, tearoff=0)
        hilfe.add_command(label="Was wird nicht erkannt?", command=self.hilfe_grenzen)
        hilfe.add_command(label="Ordner des Fehlerprotokolls öffnen", command=self.fehlerlog_oeffnen)
        hilfe.add_separator()
        hilfe.add_command(label="Über PDF-Anonymisierer …", command=self.hilfe_ueber)
        menue.add_cascade(label="Hilfe", menu=hilfe)
        self.menue = menue
        self.kunden_menue = kunden
        try:
            self.root.config(menu=menue)
        except tk.TclError:
            pass

    # Oberflächen-Helfer ------------------------------------------------
    def _karte(self, eltern, titel, expand=False):
        rahmen = tk.Frame(eltern, bg=FARBE_KARTE, padx=14, pady=8,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        rahmen.pack(fill="both" if expand else "x", expand=expand, pady=(0, 8))
        tk.Label(rahmen, text=titel, font=self.f_karte, bg=FARBE_KARTE, fg=FARBE_TEXT).pack(anchor="w", pady=(0, 2))
        return rahmen

    def _knopf(self, eltern, text, befehl, sekundaer=False):
        if sekundaer:
            knopf = tk.Button(eltern, text=text, command=befehl, font=self.f_normal,
                              bg="#eef1f5", fg=FARBE_TEXT, relief="flat",
                              padx=10, pady=3, cursor="hand2", activebackground="#dde3ea")
        else:
            knopf = tk.Button(eltern, text=text, command=befehl, font=self.f_knopf,
                              bg=FARBE_AKZENT, fg="white", relief="flat", padx=12, pady=6, cursor="hand2",
                              activebackground="#134a8e", activeforeground="white",
                              disabledforeground="#d1d5db")
        knopf.bind("<Return>", lambda e: knopf.invoke())
        return knopf

    def _anpassung_planen(self):
        if not self._anpassung_geplant:
            self._anpassung_geplant = True
            try:
                self.root.after_idle(self._oben_anpassen)
            except tk.TclError:
                self._anpassung_geplant = False

    def _oben_anpassen(self):
        """Höhe des scrollbaren Einstellbereichs so wählen, dass Fundliste, Protokoll und Leiste sichtbar bleiben."""
        self._anpassung_geplant = False
        if self.beendet:
            return
        if self._anpassung_laeuft:
            try:
                self.root.after(1, self._oben_anpassen)     # läuft gerade: später noch einmal (nicht verwerfen)
            except tk.TclError:
                pass
            return
        self._anpassung_laeuft = True
        try:
            if not self.oben.winfo_exists():
                return
            benoetigt = self.oben.winfo_reqheight()
            fenster_h = self.root.winfo_height()
            if fenster_h <= 1:                               # noch nicht dargestellt: Startgeometrie nehmen
                fenster_h = self._start_hoehe
            klein = fenster_h < self._px(FENSTER_KLEIN_HOEHE)
            if fenster_h < self._px(UNTERTITEL_MINDESTHOEHE):
                if self.untertitel.winfo_ismapped():
                    self.untertitel.pack_forget()
                    self.kopf.update_idletasks()
            elif not self.untertitel.winfo_ismapped():
                self.untertitel.pack(anchor="w", pady=(0, 6))
                self.kopf.update_idletasks()
            # kleines Fenster: Bedienhinweis über der Fundliste ausblenden (der Knopf „Vorschau …“ und die
            # Statuszeile nennen die Vorschau weiterhin) – jede Zeile zählt für die Fundliste
            if klein and self.baum_hinweis.winfo_manager():
                self.baum_hinweis.pack_forget()
            elif not klein and not self.baum_hinweis.winfo_manager():
                self.baum_hinweis.pack(anchor="w", fill="x", before=self.baum_rahmen)
            zeilen = PROTOKOLL_ZEILEN_KLEIN if klein else PROTOKOLL_ZEILEN
            if int(self.protokoll.cget("height")) != zeilen:
                self.protokoll.config(height=zeilen)
                self.protokoll_rahmen.update_idletasks()
            karte3_rand = max(0, self.karte3.winfo_reqheight() - self.baum_rahmen.winfo_reqheight())
            fest = (self.kopf.winfo_reqheight() + self.aktionsleiste.winfo_reqheight()
                    + self.protokoll_rahmen.winfo_reqheight() + karte3_rand + self._px(44))
            rest = fenster_h - fest
            # Die Fundliste ist der Arbeitsbereich (GR-02): fester Anteil des freien Platzes (mindestens
            # BAUM_MINDESTHOEHE); der Einstellbereich bekommt den Rest und scrollt bei Bedarf.
            baum_soll = max(self._px(BAUM_MINDESTHOEHE), int(rest * BAUM_ANTEIL))
            verfuegbar = rest - baum_soll
            hoehe = max(self._px(OBEN_MINDESTHOEHE), min(benoetigt, verfuegbar))
            self.oben_canvas.configure(height=hoehe,
                                       scrollregion=(0, 0, self.oben.winfo_reqwidth(), benoetigt))
            if benoetigt > hoehe + 2:
                if not self.oben_roll.winfo_ismapped():
                    self.oben_roll.pack(side="right", fill="y")
            else:
                self.oben_roll.pack_forget()
                self.oben_canvas.yview_moveto(0)
        except tk.TclError:
            pass
        finally:
            self._anpassung_laeuft = False

    def _fenster_geaendert(self, ereignis):
        if ereignis.widget is not self.root:
            return
        breite = max(300, ereignis.width - self._px(60))
        self.untertitel.config(wraplength=breite)
        self.hinweis_kasten.config(wraplength=max(300, breite - self._px(40)))
        self.profil_beschreibung.config(wraplength=max(300, breite - self._px(40)))
        self.baum_hinweis.config(wraplength=max(300, breite - self._px(40)))
        self._anpassung_planen()

    def _mausrad(self, ereignis):
        """Mausrad über dem Einstellbereich scrollt den Canvas (Text/Baum scrollen selbst)."""
        try:
            ziel = self.root.winfo_containing(ereignis.x_root, ereignis.y_root)
        except (tk.TclError, KeyError):
            return
        w = ziel
        while w is not None:
            if isinstance(w, (tk.Text, ttk.Treeview, tk.Listbox, tk.Entry)):
                return
            if w is self.oben_canvas:
                break
            w = getattr(w, "master", None)
        else:
            return
        if not self.oben_roll.winfo_ismapped():
            return
        if getattr(ereignis, "num", None) == 4 or getattr(ereignis, "delta", 0) > 0:
            self.oben_canvas.yview_scroll(-1, "units")
        else:
            self.oben_canvas.yview_scroll(1, "units")

    # ------------------------------------------------------------------
    # Dateiauswahl
    # ------------------------------------------------------------------
    def _drop_ereignis(self, ereignis):
        try:                                   # tkdnd liefert eine Tcl-Liste (Leerzeichen/Klammern gequotet, GR-08)
            pfade = list(self.root.tk.splitlist(ereignis.data))
        except tk.TclError:
            pfade = [a or b for a, b in re.findall(r"\{([^}]*)\}|(\S+)", ereignis.data)]
        self._pdfs_hinzufuegen(pfade)

    def dateien_waehlen(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        pfade = filedialog.askopenfilenames(title="PDF-Dateien auswählen",
                                            filetypes=[("PDF-Dateien", "*.pdf")], parent=self.root)
        if pfade:
            self._pdfs_hinzufuegen(list(pfade))

    def ordner_waehlen(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        ordner = filedialog.askdirectory(title="Ordner mit PDFs auswählen", parent=self.root)
        if ordner:
            self._pdfs_hinzufuegen([ordner])

    def zielordner_waehlen(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        ordner = filedialog.askdirectory(title="Gemeinsamen Zielordner wählen", parent=self.root)
        if ordner:
            self.zielordner_var.set(ordner)
            self.zielordner_aktiv.set(True)

    def _pdfs_hinzufuegen(self, pfade):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        bericht = dateien.sammle_pdfs_bericht(pfade)
        neu = 0
        for pdf in bericht["pdfs"]:
            if pdf not in self.dateien:
                self.dateien.append(pdf)
                self._datei_zeile_einfuegen(pdf)
                neu += 1
        self._beschriftungen_aktualisieren()

        # Meldungen zur Auswahl zählen nicht als Warnung eines Laufs (GR-07)
        teile = [f"{neu} PDF-Datei(en) hinzugefügt" if neu else "Keine neue PDF-Datei"]
        if bericht["uebersprungen"]:
            namen = ", ".join(p.name for p in bericht["uebersprungen"][:5])
            teile.append(f"{len(bericht['uebersprungen'])} übersprungen – keine PDF")
            self._log(f"⚠ Übersprungen (keine PDF-Datei; Fotos, Mails oder Office-Dateien bitte zuerst als "
                      f"PDF speichern): {namen}", "warnung", zaehlen=False)
        if bericht["ausgaben"]:
            teile.append(f"{len(bericht['ausgaben'])} bereits anonymisierte Datei(en) ausgelassen")
            self._log(f"ℹ {len(bericht['ausgaben'])} Datei(en) im Ordner sind bereits Ausgaben des Programms "
                      f"und wurden ausgelassen.", "hinweis")
        if bericht.get("zwischendateien"):
            self._log(f"ℹ {len(bericht['zwischendateien'])} Zwischendatei(en) einer abgebrochenen Schwärzung "
                      f"(.anonym_tmp_…) ignoriert – sie werden beim nächsten Schwärzen aufgeräumt.", "hinweis")
        if bericht["leere_ordner"]:
            namen = ", ".join(str(p) for p in bericht["leere_ordner"][:3])
            teile.append("Ordner ohne PDF-Dateien")
            self._log(f"⚠ Ordner enthält keine PDF-Dateien: {namen}", "warnung", zaehlen=False)
        if bericht["fehlend"]:
            teile.append(f"{len(bericht['fehlend'])} nicht gefunden")
            self._log("⚠ Nicht gefunden: " + ", ".join(str(p) for p in bericht["fehlend"][:3]), "warnung",
                      zaehlen=False)
        self.datei_hinweis.config(text="; ".join(teile) + f" · insgesamt {len(self.dateien)} Datei(en).")
        if neu and self.analyse_ergebnisse:
            self._log("ℹ Neue Dateien sind noch nicht analysiert – bitte erneut analysieren, bevor geschwärzt wird.",
                      "hinweis")
        self._status_dateien()
        self._start_knopf_aktualisieren()

    def _status_dateien(self):
        if not self.dateien:
            self._status("Bereit. Bitte PDF-Dateien hinzufügen (Schritt 1).")
        elif not self.analyse_ergebnisse:
            self._status(f"{len(self.dateien)} Datei(en) ausgewählt – jetzt unten „Analysieren“ drücken.")

    def _datei_vergessen(self, pdf: Path):
        """Alles zu einer Datei vergessen (Vorschau, manuelle Markierungen, Ausgabestatus)."""
        fenster = self.vorschauen.pop(pdf, None)
        if fenster is not None:
            fenster.schliessen(benachrichtigen=False)
        self.analyse_ergebnisse.pop(pdf, None)
        self.manuell.pop(pdf, None)
        self.lauf_immer.pop(pdf, None)
        self.ausgaben.pop(pdf, None)

    def liste_leeren(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        for pdf in list(self.dateien):
            self._datei_vergessen(pdf)
        self.dateien.clear()
        self.analyse_ergebnisse.clear()
        self.zeilen.clear()
        self.beschriftungen.clear()
        self.baum.delete(*self.baum.get_children())
        self.analyse_veraltet = False
        self.datei_hinweis.config(text="Noch keine Dateien. Die Liste erscheint unten in Schritt 3.")
        self._status_dateien()
        self._start_knopf_aktualisieren()

    def datei_entfernen(self, iid=None):
        """Entfernt eine Datei (die ausgewählte, falls keine angegeben) aus Liste und Baum."""
        if self.laeuft:
            self._laeuft_hinweis()
            return
        if iid is None:
            auswahl = self.baum.selection()
            if not auswahl:
                self._dialog("info", "Keine Datei gewählt",
                             "Bitte zuerst eine Datei in der Liste anklicken, dann „Datei aus Liste entfernen“.")
                return
            iid = auswahl[0]
        if iid not in self.zeilen:
            iid = self.baum.parent(iid)
        pdf = self.zeilen.pop(iid, None)
        if pdf is None:
            return
        self.beschriftungen.pop(iid, None)
        if pdf in self.dateien:
            self.dateien.remove(pdf)
        self._datei_vergessen(pdf)
        if self.baum.exists(iid):
            self.baum.delete(iid)
        self._beschriftungen_aktualisieren()
        self.datei_hinweis.config(text=f"„{pdf.name}“ entfernt · insgesamt {len(self.dateien)} Datei(en).")
        self._status_dateien()
        self._start_knopf_aktualisieren()

    # ------------------------------------------------------------------
    # Baum (Dateien, Funde, manuelle Markierungen)
    # ------------------------------------------------------------------
    def _datei_zeile_einfuegen(self, pdf: Path) -> str:
        iid = str(pdf)
        if not self.baum.exists(iid):
            self.baum.insert("", "end", iid=iid, text="", open=True,
                             values=("noch nicht analysiert", "", "", "", "", ""), tags=("datei", "aus"))
            self.zeilen[iid] = pdf
            self.beschriftungen[iid] = pdf.name
            self._zeilentext_setzen(iid)
        return iid

    def _beschriftungen_aktualisieren(self):
        """Dateinamen relativ zum gemeinsamen Stammordner anzeigen (KundeA/Police.pdf, KundeB/Police.pdf)."""
        stamm = dateien.gemeinsamer_stamm(self.dateien)
        ein_ordner = len({p.parent for p in self.dateien}) <= 1
        for iid, pdf in self.zeilen.items():
            if stamm is None or ein_ordner:
                name = pdf.name
            else:
                try:
                    name = pdf.relative_to(stamm).as_posix()
                except ValueError:
                    name = str(pdf)
            self.beschriftungen[iid] = name
            self._zeilentext_setzen(iid)
        for fenster in self.vorschauen.values():
            fenster.titel_setzen()

    def _anzeigename(self, pdf: Path) -> str:
        return self.beschriftungen.get(str(pdf), pdf.name)

    def _zustand(self, iid) -> str:
        tags = self.baum.item(iid, "tags")
        for zustand in ("an", "aus", "teil"):
            if zustand in tags:
                return zustand
        return "aus"

    def _zustand_setzen(self, iid, zustand):
        tags = [t for t in self.baum.item(iid, "tags") if t not in HAKEN]
        tags.append(zustand)
        self.baum.item(iid, tags=tuple(tags))
        self._zeilentext_setzen(iid)

    def _zeilentext_setzen(self, iid):
        zustand = self._zustand(iid)
        if iid in self.zeilen:
            self.baum.item(iid, text=f"{HAKEN[zustand]}  {self.beschriftungen.get(iid, '')}")
        else:
            self.baum.item(iid, text=HAKEN[zustand])

    def _eltern_ableiten(self, eltern):
        kinder = self.baum.get_children(eltern)
        if not kinder:
            zustand = "aus"
        else:
            zustaende = [self._zustand(k) for k in kinder]
            if all(z == "an" for z in zustaende):
                zustand = "an"
            elif all(z == "aus" for z in zustaende):
                zustand = "aus"
            else:
                zustand = "teil"
        self._zustand_setzen(eltern, zustand)

    @staticmethod
    def _kind_art(iid: str):
        """("fund", Index) | ("manuell", mid) | (None, None) für eine Kind-iid „<pfad>::<index>“/„<pfad>::m<mid>“."""
        teile = str(iid).rsplit("::", 1)
        if len(teile) != 2:
            return None, None
        teil = teile[1]
        if teil.startswith("m") and teil[1:].isdigit():
            return "manuell", int(teil[1:])
        if teil.isdigit():
            return "fund", int(teil)
        return None, None

    def einzelstellen_moeglich(self, pdf: Path, ergebnis: dict | None = None) -> bool:
        """Kann die Engine einzelne Fundstellen schwärzen? (Analyse lieferte ein Seitenmodell, die Schwärzung
        nimmt es an – Vertrag Abschnitt 5). Sonst gilt ein Fund immer an allen seinen Stellen."""
        ergebnis = self.analyse_ergebnisse.get(pdf) if ergebnis is None else ergebnis
        return bool(ergebnis) and ergebnis.get("modell") is not None and kann(schwaerze_pdf, "modell")

    def kann_manuelle_bereiche(self) -> bool:
        return kann(schwaerze_pdf, "manuelle_bereiche")

    def kann_manuelle_stellen(self) -> bool:
        return kann(schwaerze_pdf, "manuelle_stellen")

    def _fund_hat_stellen(self, pdf: Path, fund: dict, ergebnis: dict | None = None) -> bool:
        return (isinstance(fund.get("stellen"), list) and bool(fund["stellen"])
                and self.einzelstellen_moeglich(pdf, ergebnis))

    def fund_zustand(self, pdf: Path, index: int) -> str:
        """an | aus | teil – bei Einzelstellen aus den Stellen abgeleitet, sonst das Häkchen des Funds."""
        ergebnis = self.analyse_ergebnisse.get(pdf)
        if not ergebnis or not 0 <= index < len(ergebnis["funde"]):
            return "aus"
        fund = ergebnis["funde"][index]
        if self._fund_hat_stellen(pdf, fund):
            an = sum(1 for s in fund["stellen"] if s.get("an", True))
            return "an" if an == len(fund["stellen"]) else ("aus" if an == 0 else "teil")
        iid = f"{pdf}::{index}"
        return self._zustand(iid) if self.baum.exists(iid) else "an"

    def _fund_zeile_einfuegen(self, pdf: Path, index: int, fund: dict, zustand: str):
        iid = str(pdf)
        seiten = fund.get("seiten") or []
        seiten_text = ", ".join(str(s) for s in seiten[:6]) + (" …" if len(seiten) > 6 else "")
        anzeige = fund["anzeige"]
        if fund.get("hinweis"):
            anzeige = "⚑ " + anzeige                           # unsicherer Fund (Hinweis der Engine)
        self.baum.insert(iid, "end", iid=f"{iid}::{index}", text=HAKEN[zustand],
                         values=(anzeige, str(fund["text"]).replace("\n", " "), seiten_text,
                                 fund.get("anzahl", 1), _kontext_anzeige(fund.get("kontext", "")),
                                 fund["ersatz"]),
                         tags=("fund", zustand))

    def _manuell_zeile_einfuegen(self, pdf: Path, mid: int, eintrag: dict):
        anzeige = ANZEIGE_NACHSCHWAERZEN if eintrag.get("herkunft") == "nachschwaerzen" else ANZEIGE_MANUELL
        zustand = "an" if eintrag.get("an", True) else "aus"
        text = eintrag.get("text") or ("Bereich" if eintrag["art"] == "bereich" else "Stelle")
        self.baum.insert(str(pdf), "end", iid=f"{pdf}::m{mid}", text=HAKEN[zustand],
                         values=(anzeige, text, str(eintrag["seite"] + 1), 1,
                                 "Rahmen aus der Vorschau" if eintrag["art"] == "bereich" else "Klick in der Vorschau",
                                 PLATZHALTER_MANUELL),
                         tags=("manuell", zustand))

    def _baum_datei_fuellen(self, pdf: Path, ergebnis: dict):
        """Trägt die Funde einer Datei ein (Kind-iid = „<pfad>::<index>“, manuelle: „<pfad>::m<mid>“)."""
        if self.beendet:
            return
        iid = self._datei_zeile_einfuegen(pdf)
        self.baum.delete(*self.baum.get_children(iid))
        funde = ergebnis["funde"]
        for index, fund in enumerate(funde):
            zustand = "an"
            if self._fund_hat_stellen(pdf, fund, ergebnis):
                an = sum(1 for s in fund["stellen"] if s.get("an", True))
                zustand = "an" if an == len(fund["stellen"]) else ("aus" if an == 0 else "teil")
            self._fund_zeile_einfuegen(pdf, index, fund, zustand)
        for mid, eintrag in self.manuell.get(pdf, {}).items():
            self._manuell_zeile_einfuegen(pdf, mid, eintrag)
        codes = meldungs_codes(ergebnis)
        if ergebnis["fehler"]:
            status = f"Fehler: {ergebnis['fehler']}"
        elif not funde and codes & {"KEIN_TEXT", "KAUM_LESBAR"}:
            status = "0 Funde – kein Text lesbar!"
        else:
            status = f"{len(funde)} Fund(e)"
        if ergebnis["warnungen"]:
            status += f" · {len(ergebnis['warnungen'])} Warnung(en)"
        self.baum.set(iid, "kategorie", status)
        self.baum.set(iid, "seiten", str(ergebnis["seiten"]) if ergebnis["seiten"] else "")
        self.baum.set(iid, "anzahl", str(sum(f.get("anzahl", 1) for f in funde)) if funde else "")
        self._ausgabe_zeile_setzen(pdf)
        self._eltern_ableiten(iid)

    def _ausgabe_zeile_setzen(self, pdf: Path):
        """Status der Ausgabe (fertig / prüfen / Fehler) in der Dateizeile (Spalten Text und Kontext)."""
        iid = str(pdf)
        if not self.baum.exists(iid):
            return
        eintrag = self.ausgaben.get(pdf)
        if not eintrag:
            self.baum.set(iid, "text", "")
            self.baum.set(iid, "kontext", "")
            return
        status = STATUS_TEXT.get(eintrag["status"], eintrag["status"])
        ausgabe = eintrag.get("pfad")
        self.baum.set(iid, "text", f"{status}: {ausgabe.name}" if ausgabe is not None else status)
        self.baum.set(iid, "kontext", eintrag.get("grund", ""))

    def _baum_klick(self, ereignis):
        """Einfachklick in die Häkchen-Spalte schaltet um; Dreieck, Kopfzeile und Trenner bleiben Tk überlassen."""
        region = self.baum.identify_region(ereignis.x, ereignis.y)
        if region not in ("tree", "cell"):
            return None
        zeile = self.baum.identify_row(ereignis.y)
        if not zeile:
            return None
        if self.baum.identify_column(ereignis.x) != "#0":
            return None
        element = self.baum.identify_element(ereignis.x, ereignis.y)
        if element.endswith("indicator") and self.baum.get_children(zeile):
            return None
        if zeile in self.zeilen and not self._trifft_haken(zeile, ereignis.x):
            return None                 # Klick auf den Dateinamen: nur auswählen (Pfad anzeigen, Entfernen)
        self.baum.focus_set()           # Tastaturfokus für die Leertaste
        self.baum.selection_set(zeile)
        self.baum.focus(zeile)
        self._umschalten(zeile)
        return "break"

    def _trifft_haken(self, zeile, x) -> bool:
        """Liegt x (Baumkoordinate) auf dem Häkchen-Symbol einer Dateizeile?"""
        bbox = self.baum.bbox(zeile, "#0")
        if not bbox:
            return False
        einzug = self._px(20)                        # Platz des Aufklapp-Dreiecks
        haken_breite = self.f_fett.measure(HAKEN["an"] + "  ") + self._px(6)
        return bbox[0] + einzug - self._px(4) <= x <= bbox[0] + einzug + haken_breite

    def _baum_doppelklick(self, ereignis):
        zeile = self.baum.identify_row(ereignis.y)
        element = self.baum.identify_element(ereignis.x, ereignis.y)
        if zeile and element.endswith("indicator") and self.baum.get_children(zeile):
            return None                 # Dreieck: Tk klappt auf/zu
        if zeile and self.baum.identify_region(ereignis.x, ereignis.y) in ("tree", "cell"):
            if zeile in self.zeilen or self.baum.identify_column(ereignis.x) != "#0":
                self.root.after_idle(self._vorschau_fuer_zeile, zeile)
        return "break"                  # sonst nichts umschalten, nichts zuklappen

    def _taste_leer(self, ereignis=None):
        zeile = self.baum.focus()
        if zeile:
            self._umschalten(zeile)
        return "break"

    def _haken_umschalten(self, ereignis=None):
        """Umschalten der fokussierten Zeile (Tastatur / Skripte)."""
        return self._taste_leer(ereignis)

    def _umschalten(self, zeile):
        if self.laeuft or not self.baum.exists(zeile):
            return
        if zeile in self.zeilen:
            neu = "aus" if self._zustand(zeile) == "an" else "an"
            self._datei_setzen(zeile, neu)
            return
        pdf = self.zeilen.get(self.baum.parent(zeile))
        art, nummer = self._kind_art(zeile)
        if pdf is None or art is None:
            return
        if art == "fund":
            self.fund_setzen(pdf, nummer, self.fund_zustand(pdf, nummer) != "an")
        else:
            self.manuell_umschalten(pdf, nummer)

    def _kind_setzen(self, pdf: Path, kind: str, an: bool):
        """Fund- oder manuelle Zeile setzen, ohne Eltern/Knopf/Vorschau nachzuführen (für Sammelaktionen)."""
        art, nummer = self._kind_art(kind)
        if art == "fund":
            funde = self.analyse_ergebnisse[pdf]["funde"] if pdf in self.analyse_ergebnisse else []
            fund = funde[nummer] if 0 <= nummer < len(funde) else None
            if fund is not None and self._fund_hat_stellen(pdf, fund):
                for stelle in fund["stellen"]:
                    stelle["an"] = an
        elif art == "manuell":
            eintrag = self.manuell.get(pdf, {}).get(nummer)
            if eintrag is not None:
                eintrag["an"] = an
        self._zustand_setzen(kind, "an" if an else "aus")

    def _nach_aenderung(self, pdf: Path | None):
        """Nach jeder Änderung von Häkchen/Stellen: Elternzeile, Schwärzen-Knopf, offene Vorschau."""
        if pdf is not None and self.baum.exists(str(pdf)):
            self._eltern_ableiten(str(pdf))
        self._start_knopf_aktualisieren()
        fenster = self.vorschauen.get(pdf) if pdf is not None else None
        ziele = [fenster] if fenster is not None else (list(self.vorschauen.values()) if pdf is None else [])
        for f in ziele:
            f.neu_zeichnen()

    def fund_setzen(self, pdf: Path, index: int, an: bool):
        """Fund an allen Stellen an/aus (Hauptliste und Vorschau bleiben gleich)."""
        if self.laeuft:
            return
        iid = f"{pdf}::{index}"
        if not self.baum.exists(iid):
            return
        self._kind_setzen(pdf, iid, an)
        self._nach_aenderung(pdf)

    def stelle_setzen(self, pdf: Path, index: int, stelle_index: int, an: bool):
        """Eine einzelne Fundstelle an/aus (nur wenn die Engine Einzelstellen kann)."""
        if self.laeuft:
            return
        fund = self.analyse_ergebnisse[pdf]["funde"][index]
        if not self._fund_hat_stellen(pdf, fund):
            self.fund_setzen(pdf, index, an)
            return
        fund["stellen"][stelle_index]["an"] = an
        iid = f"{pdf}::{index}"
        if self.baum.exists(iid):
            self._zustand_setzen(iid, self.fund_zustand(pdf, index))
        self._nach_aenderung(pdf)

    def manuell_hinzufuegen(self, pdf: Path, eintrag: dict) -> int | None:
        """Neue manuelle Markierung aus der Vorschau: {"art": "stelle"|"bereich", "seite", "rechtecke",
        "start", "ende", "text", "herkunft"}; erscheint als eigene Zeile in der Fundliste."""
        if self.laeuft or pdf not in self.analyse_ergebnisse:
            return None
        self._manuell_zaehler += 1
        mid = self._manuell_zaehler
        eintrag = dict(eintrag)
        eintrag.setdefault("an", True)
        eintrag.setdefault("herkunft", "vorschau")
        self.manuell.setdefault(pdf, {})[mid] = eintrag
        if self.baum.exists(str(pdf)):
            self._manuell_zeile_einfuegen(pdf, mid, eintrag)
        self._nach_aenderung(pdf)
        return mid

    def manuell_umschalten(self, pdf: Path, mid: int):
        eintrag = self.manuell.get(pdf, {}).get(mid)
        if self.laeuft or eintrag is None:
            return
        self._kind_setzen(pdf, f"{pdf}::m{mid}", not eintrag.get("an", True))
        self._nach_aenderung(pdf)

    def manuell_entfernen(self, pdf: Path, mid: int):
        if self.laeuft:
            return
        if self.manuell.get(pdf, {}).pop(mid, None) is None:
            return
        iid = f"{pdf}::m{mid}"
        if self.baum.exists(iid):
            self.baum.delete(iid)
        self._nach_aenderung(pdf)

    def begriff_ueberall(self, pdf: Path, text: str) -> int | None:
        """„Überall in diesem Dokument schwärzen“: IMMER-Begriff für diesen Lauf (diese Datei). Wird sofort als
        Fund ergänzt (ohne „stellen“ – die Schwärzung sucht alle Vorkommen selbst) und bei einer erneuten
        Analyse dieser Datei als IMMER-Begriff mitgegeben. Liefert den Fund-Index."""
        text = " ".join(str(text).split())
        ergebnis = self.analyse_ergebnisse.get(pdf)
        if self.laeuft or not text or ergebnis is None:
            return None
        for index, fund in enumerate(ergebnis["funde"]):
            if fund["kategorie"] == "begriff" and fund["text"].casefold() == text.casefold():
                self.fund_setzen(pdf, index, True)
                return index
        begriffe = self.lauf_immer.setdefault(pdf, [])
        if text not in begriffe:
            begriffe.append(text)
        fund = {"id": f"vorschau_{len(ergebnis['funde']) + 1}", "kategorie": "begriff", "anzeige": ANZEIGE_BEGRIFF_VORSCHAU,
                "text": text, "ersatz": "[BEGRIFF]", "seiten": [], "anzahl": 1,
                "kontext": "in der Vorschau hinzugefügt", "quellen": ["vorschau"], "sicherheit": 1.0,
                "hinweis": None}
        ergebnis["funde"].append(fund)
        index = len(ergebnis["funde"]) - 1
        if self.baum.exists(str(pdf)):
            self._fund_zeile_einfuegen(pdf, index, fund, "an")
            # manuelle Zeilen bleiben am Ende der Liste
            for mid in self.manuell.get(pdf, {}):
                if self.baum.exists(f"{pdf}::m{mid}"):
                    self.baum.move(f"{pdf}::m{mid}", str(pdf), "end")
        self._log(f"ℹ {self._anzeigename(pdf)}: „{text}“ wird überall in diesem Dokument geschwärzt "
                  f"(IMMER-Begriff für diesen Lauf).", "hinweis")
        self._nach_aenderung(pdf)
        return index

    def _datei_setzen(self, iid, zustand):
        if self.laeuft or not self.baum.exists(iid):
            return
        pdf = self.zeilen.get(iid)
        for kind in self.baum.get_children(iid):
            self._kind_setzen(pdf, kind, zustand == "an")
        self._nach_aenderung(pdf)

    def alle_setzen(self, zustand):
        """Alle Funde aller Dateien an („an“) oder aus („aus“)."""
        if self.laeuft:
            return
        for iid in self.baum.get_children(""):
            self._datei_setzen(iid, zustand)

    def kategorie_setzen(self, anzeige, zustand):
        """Alle Funde einer Kategorie (Anzeigename) in allen Dateien an/aus."""
        if self.laeuft:
            return
        for iid in self.baum.get_children(""):
            pdf = self.zeilen.get(iid)
            for kind in self.baum.get_children(iid):
                if self.baum.set(kind, "kategorie").lstrip("⚑ ") == anzeige.lstrip("⚑ "):
                    self._kind_setzen(pdf, kind, zustand == "an")
            self._nach_aenderung(pdf)
        self._start_knopf_aktualisieren()

    def _kontextmenue(self, ereignis):
        zeile = self.baum.identify_row(ereignis.y)
        menue = tk.Menu(self.root, tearoff=0)
        if zeile:
            self.baum.selection_set(zeile)
            self.baum.focus(zeile)
            datei = zeile if zeile in self.zeilen else self.baum.parent(zeile)
            name = self.beschriftungen.get(datei, "")
            menue.add_command(label=f"Vorschau von „{name}“ öffnen",
                              command=lambda: self._vorschau_fuer_zeile(zeile))
            menue.add_separator()
            menue.add_command(label=f"Alle Funde von „{name}“ anhaken",
                              command=lambda: self._datei_setzen(datei, "an"))
            menue.add_command(label=f"Alle Funde von „{name}“ abhaken",
                              command=lambda: self._datei_setzen(datei, "aus"))
            if zeile not in self.zeilen:
                kategorie = self.baum.set(zeile, "kategorie")
                menue.add_separator()
                menue.add_command(label=f"Kategorie „{kategorie}“ überall anhaken",
                                  command=lambda: self.kategorie_setzen(kategorie, "an"))
                menue.add_command(label=f"Kategorie „{kategorie}“ überall abhaken",
                                  command=lambda: self.kategorie_setzen(kategorie, "aus"))
            menue.add_separator()
            menue.add_command(label="Datei aus der Liste entfernen", command=lambda: self.datei_entfernen(datei))
            menue.add_separator()
        menue.add_command(label="Alle an", command=lambda: self.alle_setzen("an"))
        menue.add_command(label="Alle aus", command=lambda: self.alle_setzen("aus"))
        try:
            menue.tk_popup(ereignis.x_root, ereignis.y_root)
        finally:
            menue.grab_release()

    def _auswahl_geaendert(self, ereignis=None):
        """Statuszeile: vollständiger Pfad der gewählten Datei bzw. vollständiger Kontext des Funds."""
        if self.laeuft:
            return
        auswahl = self.baum.selection()
        if not auswahl:
            return
        iid = auswahl[0]
        if iid in self.zeilen:
            self.status_label.config(text=f"Datei: {self._pfad_passend(self.zeilen[iid])}")
            return
        pdf = self.zeilen.get(self.baum.parent(iid))
        art, nummer = self._kind_art(iid)
        if art == "fund" and pdf in self.analyse_ergebnisse:
            fund = self.analyse_ergebnisse[pdf]["funde"][nummer]
            teile = [f"Seite(n) {', '.join(map(str, fund.get('seiten') or [])) or '?'}"]
            if fund.get("hinweis"):
                teile.append(f"Hinweis: {fund['hinweis']}")
            teile.append(f"Kontext: {str(fund.get('kontext', '')).replace(chr(10), ' ')}")
            self.status_label.config(text=" · ".join(teile))
        elif art == "manuell":
            self.status_label.config(text="Manuelle Markierung aus der Vorschau – Kästchen schaltet sie an/aus.")

    def _pfad_passend(self, pfad: Path) -> str:
        """Voller Pfad, wenn er in die Statuszeile passt; sonst in der Mitte gekürzt (Dateiname bleibt sichtbar)."""
        text = str(pfad)
        try:
            breite = self.status_label.winfo_width() - self.f_normal.measure("Datei: ") - 8
        except tk.TclError:
            return text
        if breite < 100 or self.f_normal.measure(text) <= breite:
            return text
        teile = pfad.parts
        kandidat = f"…{os.sep}{pfad.name}"
        for i in range(1, len(teile) - 1):
            versuch = str(Path(*teile[:i + 1])) + f"{os.sep}…{os.sep}{pfad.name}"
            if self.f_normal.measure(versuch) > breite:
                break
            kandidat = versuch
        return kandidat

    def _angehakte_funde(self) -> int:
        """Angehakte (auch teilweise) Funde und manuelle Markierungen aller Dateien."""
        return sum(1 for e in self.baum.get_children("") for k in self.baum.get_children(e)
                   if self._zustand(k) in ("an", "teil"))

    def _start_knopf_aktualisieren(self):
        aktiv = not self.laeuft and not self.analyse_veraltet and self._angehakte_funde() > 0
        self.start_knopf.config(state="normal" if aktiv else "disabled")

    # ------------------------------------------------------------------
    # Vorschau
    # ------------------------------------------------------------------
    def _vorschau_fuer_zeile(self, zeile):
        if not self.baum.exists(zeile):
            return
        if zeile in self.zeilen:
            self.vorschau_oeffnen(self.zeilen[zeile])
            return
        pdf = self.zeilen.get(self.baum.parent(zeile))
        art, nummer = self._kind_art(zeile)
        seite, markieren = None, None
        if art == "fund" and pdf in self.analyse_ergebnisse:
            fund = self.analyse_ergebnisse[pdf]["funde"][nummer]
            seiten = fund.get("seiten") or []
            stellen = fund.get("stellen") or []
            seite = stellen[0]["seite"] if stellen else (seiten[0] - 1 if seiten else None)
            markieren = nummer
        elif art == "manuell":
            eintrag = self.manuell.get(pdf, {}).get(nummer)
            seite = eintrag["seite"] if eintrag else None
        if pdf is not None:
            self.vorschau_oeffnen(pdf, seite=seite, modus="vorher", markieren=markieren)

    def vorschau_auswahl(self):
        """Knopf „Vorschau …“: Vorschau der gewählten Datei (sonst der ersten zu prüfenden bzw. ersten)."""
        auswahl = self.baum.selection()
        if auswahl:
            self._vorschau_fuer_zeile(auswahl[0])
            return
        zu_pruefen = [p for p in self.dateien if self.ausgaben.get(p, {}).get("status") == "pruefen"]
        kandidaten = zu_pruefen or [p for p in self.dateien if p in self.analyse_ergebnisse]
        if not kandidaten:
            self._dialog("info", "Vorschau", "Bitte zuerst Dateien hinzufügen und analysieren – dann zeigt die "
                                             "Vorschau jede Seite mit allen Fundstellen.")
            return
        self.vorschau_oeffnen(kandidaten[0])

    def ausgabe_vorhanden(self, pdf: Path) -> bool:
        eintrag = self.ausgaben.get(pdf)
        return bool(eintrag) and eintrag.get("pfad") is not None and eintrag["status"] in ("fertig", "pruefen") \
            and Path(eintrag["pfad"]).exists()

    def vorschau_oeffnen(self, pdf: Path, seite: int | None = None, modus: str | None = None, markieren=None):
        """Öffnet (oder holt nach vorn) das Vorschau-Fenster einer Datei. modus: "vorher" (geplante Schwärzung)
        oder "nachher" (Ausgabe mit Verdachtsstellen); ohne Angabe: Ausgabe, wenn sie noch zu prüfen ist."""
        from .vorschau_fenster import VorschauFenster
        if modus is None:
            modus = "nachher" if self.ausgabe_vorhanden(pdf) and (
                self.ausgaben[pdf]["status"] == "pruefen" or pdf not in self.analyse_ergebnisse) else "vorher"
        if modus == "nachher" and not self.ausgabe_vorhanden(pdf):
            modus = "vorher"
        if modus == "vorher" and pdf not in self.analyse_ergebnisse:
            self._dialog("info", "Vorschau", f"„{self._anzeigename(pdf)}“ ist noch nicht analysiert – bitte zuerst "
                                             f"unten „Analysieren“ drücken.")
            return None
        fenster = self.vorschauen.get(pdf)
        try:
            if fenster is not None and fenster.existiert():
                fenster.modus_wechseln(modus, seite=seite, markieren=markieren)
                fenster.nach_vorn()
                return fenster
            fenster = VorschauFenster(self, pdf, modus=modus, seite=seite or 0, markieren=markieren)
            if not fenster.existiert():
                return None
        except Exception as fehler:
            pfad = dateien.fehler_protokollieren(*sys.exc_info())
            self._dialog("error", "Vorschau nicht möglich",
                         f"Die Vorschau von „{self._anzeigename(pdf)}“ konnte nicht geöffnet werden:\n"
                         f"{_verstaendliche_fehlermeldung(fehler, pdf)}\n\nDetails: {pfad or 'fehler.log'}")
            return None
        self.vorschauen[pdf] = fenster
        return fenster

    def vorschau_geschlossen(self, pdf: Path):
        self.vorschauen.pop(pdf, None)

    def _vorschauen_schliessen(self):
        for fenster in list(self.vorschauen.values()):
            fenster.schliessen(benachrichtigen=False)
        self.vorschauen.clear()
        self._vorschau_dateien_freigeben()

    @staticmethod
    def _vorschau_dateien_freigeben(pfad: Path | None = None):
        """Zwischengespeicherte PDF-Dokumente der Vorschau (Attrappe und Vorschau-Modul der Engine) freigeben –
        vor dem Umbenennen/Löschen einer Ausgabe (unter Windows verhindert ein offener Handle beides)."""
        attrappen.cache_leeren(pfad)
        from .vorschau_fenster import engine_zwischenspeicher_leeren
        engine_zwischenspeicher_leeren()

    def naechste_zu_pruefen(self, nach: Path | None = None) -> Path | None:
        """Nächste Datei (in Listenreihenfolge nach „nach“), deren Ausgabe noch freigegeben werden muss."""
        reihe = [p for p in self.dateien if self.ausgabe_vorhanden(p) and self.ausgaben[p]["status"] == "pruefen"]
        if nach in self.dateien:
            spaeter = [p for p in reihe if self.dateien.index(p) > self.dateien.index(nach)]
            reihe = spaeter + [p for p in reihe if p not in spaeter]
        reihe = [p for p in reihe if p != nach]
        return reihe[0] if reihe else None

    def ausgabe_freigeben(self, pdf: Path) -> Path | None:
        """Ausgabe einer Datei freigeben (schwaerzung.freigeben bzw. Attrappe): _PRUEFEN entfällt."""
        eintrag = self.ausgaben.get(pdf)
        if self.laeuft or not eintrag or eintrag.get("pfad") is None:
            return None
        alt = Path(eintrag["pfad"])
        self._vorschau_dateien_freigeben(alt)
        try:
            neu = Path(freigeben(alt))
        except Exception as fehler:
            log = dateien.fehler_protokollieren(*sys.exc_info())
            self._dialog("error", "Freigabe nicht möglich",
                         f"„{alt.name}“ konnte nicht freigegeben werden:\n{_verstaendliche_fehlermeldung(fehler, alt)}"
                         + (f"\n\nDetails: {log}" if log else ""))
            return None
        eintrag.update(pfad=neu, status="fertig", grund="freigegeben", freigegeben=True)
        self._log(f"✔ {self._anzeigename(pdf)}: freigegeben  →  {neu}", "ok")
        self._ausgabe_zeile_setzen(pdf)
        self._status(f"„{self._anzeigename(pdf)}“ freigegeben: {neu.name}")
        return neu

    def ausgabe_verwerfen(self, pdf: Path) -> bool:
        """Ausgabe löschen (schwaerzung.verwerfen bzw. Attrappe) – das Original bleibt unberührt."""
        eintrag = self.ausgaben.get(pdf)
        if self.laeuft or not eintrag or eintrag.get("pfad") is None:
            return False
        alt = Path(eintrag["pfad"])
        self._vorschau_dateien_freigeben(alt)
        try:
            verwerfen(alt)
        except Exception as fehler:
            log = dateien.fehler_protokollieren(*sys.exc_info())
            self._dialog("error", "Verwerfen nicht möglich",
                         f"„{alt.name}“ konnte nicht gelöscht werden:\n{_verstaendliche_fehlermeldung(fehler, alt)}"
                         + (f"\n\nDetails: {log}" if log else ""))
            return False
        eintrag.update(pfad=None, status="verworfen", grund=f"{alt.name} gelöscht")
        self._log(f"ℹ {self._anzeigename(pdf)}: Ausgabe {alt.name} verworfen (gelöscht).", "hinweis")
        self._ausgabe_zeile_setzen(pdf)
        return True

    def nachschwaerzen(self, pdf: Path, verdachte: list) -> bool:
        """Verdachtsstellen der Ausgabe als manuelle Markierungen übernehmen und die Datei erneut schwärzen;
        die alte Ausgabe wird nach Erfolg verworfen. Liefert True, wenn der Lauf gestartet wurde."""
        eintrag = self.ausgaben.get(pdf)
        if self.laeuft or not eintrag or not verdachte or pdf not in self.analyse_ergebnisse:
            return False
        if not (self.kann_manuelle_stellen() or self.kann_manuelle_bereiche()):
            self._dialog("warning", "Nachschwärzen nicht möglich",
                         "Diese Programmversion kann noch keine einzelnen Stellen nachschwärzen. Bitte den Text "
                         "in die IMMER-Liste eintragen und erneut analysieren und schwärzen.")
            return False
        from .vorschau_fenster import verdacht_zu_markierungen
        neue = 0
        for verdacht in verdachte:
            for markierung in verdacht_zu_markierungen(self, pdf, verdacht):
                markierung["herkunft"] = "nachschwaerzen"
                if self.manuell_hinzufuegen(pdf, markierung) is not None:
                    neue += 1
        if not neue:
            fenster = self.vorschauen.get(pdf)
            self._dialog("warning", "Nachschwärzen nicht möglich",
                         "Für die markierten Stellen ist keine Lage auf der Seite bekannt (z. B. Text aus "
                         "einem Scan). Bitte in „Geplante Schwärzung“ einen Rahmen um die Stelle ziehen oder "
                         "den Text in die IMMER-Liste eintragen und erneut schwärzen.",
                         eltern=fenster.fenster if fenster is not None and fenster.existiert() else None)
            return False
        return self.schwaerzen(nur=[pdf], ersetzt=Path(eintrag["pfad"]))

    # ------------------------------------------------------------------
    # Einstellungen (Schutzstufe, Kategorien, Listen, Freigabe)
    # ------------------------------------------------------------------
    @staticmethod
    def _zeilen_aus(feld) -> list[str]:
        return [z.strip() for z in feld.get("1.0", "end").splitlines() if z.strip()]

    def profil_kategorien(self, name: str) -> set[str] | None:
        """Aktive Kategorien einer Schutzstufe (muster.PROFILE, sonst Attrappe)."""
        alle = set(self.kategorie_vars)
        menge = attrappen.profil_kategorien(PROFILE, name, alle)
        if menge is None:
            menge = attrappen.profil_kategorien(attrappen.PROFILE, name, alle)
        return menge

    def _aktive_kategorien(self) -> set[str]:
        return {k for k, v in self.kategorie_vars.items() if v.get()}

    def _profil_anwenden(self, name: str):
        """Häkchen auf die Kategorien der Schutzstufe setzen (ohne „Benutzerdefiniert“ auszulösen)."""
        menge = self.profil_kategorien(name)
        if menge is None:
            return
        self._profil_wird_gesetzt = True
        try:
            for schluessel, var in self.kategorie_vars.items():
                var.set(schluessel in menge)
        finally:
            self._profil_wird_gesetzt = False

    def _profil_beschreibung_anzeigen(self):
        name = self.profil_var.get()
        text = attrappen.profil_beschreibung(PROFILE, name, KATEGORIEN)
        if name == attrappen.BENUTZERDEFINIERT:
            text = (f"Eigene Auswahl der Kategorien (Erkennungsregeln der Stufe „{_profil_name(self.basis_profil)}“).")
        self.profil_beschreibung.config(text=text)

    def _profil_gewaehlt(self):
        """Radioknopf der Schutzstufe angeklickt."""
        name = self.profil_var.get()
        if name != attrappen.BENUTZERDEFINIERT:
            self.basis_profil = name
            self._profil_anwenden(name)
        self._profil_beschreibung_anzeigen()
        self._einstellung_geaendert()

    def _kategorie_geaendert(self, *_):
        """Häkchen einer Kategorie geändert: Stufe nachführen (passt die Auswahl zu keiner, „Benutzerdefiniert“)."""
        if not self._profil_wird_gesetzt and not self._einstellungen_werden_gesetzt:
            aktive = self._aktive_kategorien()
            aktuell = self.profil_var.get()
            if aktuell == attrappen.BENUTZERDEFINIERT or self.profil_kategorien(aktuell) != aktive:
                passend = [n for n in attrappen.PROFIL_REIHENFOLGE if self.profil_kategorien(n) == aktive]
                if aktuell in passend:
                    neu = aktuell
                elif passend:
                    neu = passend[0]
                else:
                    neu = attrappen.BENUTZERDEFINIERT
                if neu != attrappen.BENUTZERDEFINIERT:
                    self.basis_profil = neu
                self.profil_var.set(neu)
                self._profil_beschreibung_anzeigen()
        self._einstellung_geaendert()

    def _einstellungen_anwenden(self):
        e = self.einstellungen
        self._einstellungen_werden_gesetzt = True
        try:
            echte = attrappen.PROFIL_REIHENFOLGE
            profil = e.get("profil")
            basis = e.get("basis_profil")
            kategorien = e.get("kategorien") if isinstance(e.get("kategorien"), dict) else None
            if profil not in echte + (attrappen.BENUTZERDEFINIERT,):
                # ältere Einstellungen ohne Schutzstufe: unveränderter Standard -> neue Standardstufe,
                # eigene Auswahl bleibt „Benutzerdefiniert“
                standard = attrappen._standard_kategorien(KATEGORIEN)
                gespeichert = {k for k, v in (kategorien or {}).items() if v and k in self.kategorie_vars}
                if kategorien is None or gespeichert == (standard & set(self.kategorie_vars)):
                    profil = attrappen.STANDARD_PROFIL
                else:
                    profil = attrappen.BENUTZERDEFINIERT
            self.basis_profil = basis if basis in echte else (profil if profil in echte else attrappen.STANDARD_PROFIL)
            self.profil_var.set(profil)
            if profil == attrappen.BENUTZERDEFINIERT:
                self._profil_anwenden(self.basis_profil)
                for schluessel, var in self.kategorie_vars.items():
                    if kategorien and schluessel in kategorien:
                        var.set(bool(kategorien[schluessel]))
            else:
                self._profil_anwenden(profil)
            self._profil_beschreibung_anzeigen()
            for feld, schluessel in ((self.immer_feld, "immer"), (self.nie_feld, "nie")):
                werte = e.get(schluessel)
                if isinstance(werte, list):
                    feld.delete("1.0", "end")
                    feld.insert("1.0", "\n".join(str(w) for w in werte))
                feld.edit_modified(False)
            if isinstance(e.get("zielordner"), str):
                self.zielordner_var.set(e["zielordner"])
            self.zielordner_aktiv.set(bool(e.get("zielordner_aktiv", False)))
            self.freigabe_var.set(bool(e.get("freigabe_erforderlich", True)))
        finally:
            self._einstellungen_werden_gesetzt = False

    def _einstellungen_sammeln(self) -> dict:
        # Erst den Stand auf der Festplatte lesen und nur die eigenen Schlüssel überschreiben (GR-10)
        daten = dict(self.einstellungen)
        daten.update(dateien.einstellungen_laden())
        daten.update({
            "version": __version__,
            "profil": self.profil_var.get(),
            "basis_profil": self.basis_profil,
            "kategorien": {k: bool(v.get()) for k, v in self.kategorie_vars.items()},
            "immer": self._zeilen_aus(self.immer_feld),
            "nie": self._zeilen_aus(self.nie_feld),
            "zielordner": self.zielordner_var.get().strip(),
            "zielordner_aktiv": bool(self.zielordner_aktiv.get()),
            "freigabe_erforderlich": bool(self.freigabe_var.get()),
            "maximiert": self._ist_maximiert(),
        })
        if not daten["maximiert"]:
            try:
                daten["fenster"] = self.root.geometry()
            except tk.TclError:
                pass
        return daten

    def einstellungen_speichern(self):
        self.einstellungen = self._einstellungen_sammeln()
        if not dateien.einstellungen_speichern(self.einstellungen):
            self._log("⚠ Einstellungen konnten nicht gespeichert werden (Ordner nicht beschreibbar).", "warnung",
                      zaehlen=False)

    def _text_geaendert(self, ereignis):
        feld = ereignis.widget
        if feld.edit_modified():
            feld.edit_modified(False)
            self._einstellung_geaendert()

    def _einstellung_geaendert(self, *_):
        """Stufe, Kategorie, Liste oder Kundenliste geändert: eine vorhandene Analyse passt nicht mehr ->
        zurücksetzen (auch Vorschau-Fenster und manuelle Markierungen)."""
        if self._einstellungen_werden_gesetzt or self.laeuft or not self.analyse_ergebnisse:
            return
        self.analyse_veraltet = True
        self.analyse_ergebnisse.clear()
        markierungen = sum(len(m) for m in self.manuell.values())
        self.manuell.clear()
        # Vorschau der geplanten Schwärzung passt nicht mehr; eine noch zu prüfende Ausgabe bleibt sichtbar
        for pdf, fenster in list(self.vorschauen.items()):
            if self.ausgabe_vorhanden(pdf):
                fenster.modus_wechseln("nachher")
            else:
                fenster.schliessen()
        for iid in self.zeilen:
            if self.baum.exists(iid):
                self.baum.delete(*self.baum.get_children(iid))
                self.baum.set(iid, "kategorie", "erneut analysieren")
                self.baum.set(iid, "anzahl", "")
                self._zustand_setzen(iid, "aus")
        self._start_knopf_aktualisieren()
        self._status("Einstellungen geändert – bitte erneut analysieren.")
        self._log("ℹ Schutzstufe, Kategorien oder Listen wurden geändert – die Fundliste wurde zurückgesetzt. "
                  "Bitte erneut analysieren.", "hinweis")
        if markierungen:
            self._log(f"ℹ {markierungen} manuelle Markierung(en) aus der Vorschau wurden verworfen – bitte nach "
                      f"der Analyse erneut setzen.", "hinweis")

    # ------------------------------------------------------------------
    # Kundenliste
    # ------------------------------------------------------------------
    def _kundenliste_nutzbar(self) -> bool:
        return self.kundenliste is not None and kann(analysiere_pdf, "kundenliste") \
            and not getattr(self.kundenliste, "attrappe", False)

    def _kundenliste_laden(self):
        try:
            self.kundenliste = Kundenliste.laden(dateien.kundenliste_pfad())
        except Exception:
            self.kundenliste = None
            dateien.fehler_protokollieren(*sys.exc_info())
            self._log("⚠ Die gespeicherte Kundenliste konnte nicht gelesen werden – bitte erneut importieren.",
                      "warnung", zaehlen=False)
        self._kundenliste_anzeigen()

    def _kundenliste_anzeigen(self):
        if self.kundenliste is None:
            text = "keine geladen – optional den Kundenbestand (CSV) importieren, damit bekannte Kunden sicher " \
                   "erkannt werden"
        else:
            anzahl = int(getattr(self.kundenliste, "anzahl_kunden", 0))
            text = f"{anzahl} Kunden geladen – gespeichert ohne Klartext"
            if not self._kundenliste_nutzbar():
                text += " (Abgleich in dieser Programmversion noch nicht aktiv)"
        self.kunden_label.config(text=text)
        self._kunden_knoepfe_aktualisieren()

    def _kunden_knoepfe_aktualisieren(self):
        aktiv = not self.laeuft and self.kundenliste is not None
        self.kunden_entfernen_knopf.config(state="normal" if aktiv else "disabled")
        try:
            self.kunden_menue.entryconfigure(1, state="normal" if aktiv else "disabled")
        except tk.TclError:
            pass

    def kundenliste_importieren(self, pfad=None):
        """Menü/Knopf „Kundenliste importieren …“: CSV wählen, Spalten erkennen (sonst zuordnen lassen)."""
        if self.laeuft:
            self._laeuft_hinweis()
            return
        if pfad is None:
            pfad = filedialog.askopenfilename(
                title="Kundenliste (CSV) auswählen", parent=self.root,
                filetypes=[("CSV-Dateien", "*.csv *.txt"), ("Alle Dateien", "*.*")])
            if not pfad:
                return
        self._kundenliste_import(Path(pfad), None)

    def _kundenliste_import(self, pfad: Path, spalten: dict | None):
        self.spalten_dialog = None
        try:
            liste = Kundenliste.importieren(pfad) if spalten is None else Kundenliste.importieren(pfad, spalten)
        except (ValueError, KeyError, LookupError) as fehler:
            if spalten is None:
                self._spalten_zuordnen(pfad)
                return
            self._dialog("warning", "Kundenliste nicht importiert", f"Die Kundenliste konnte nicht importiert "
                                                                    f"werden:\n{fehler}")
            return
        except Exception as fehler:
            if spalten is None and "spalte" in type(fehler).__name__.lower():
                self._spalten_zuordnen(pfad)              # eigene Ausnahme der Engine für unbekannte Spalten
                return
            log = dateien.fehler_protokollieren(*sys.exc_info())
            self._dialog("error", "Kundenliste nicht importiert",
                         f"„{pfad.name}“ konnte nicht gelesen werden:\n{_verstaendliche_fehlermeldung(fehler, pfad)}"
                         + (f"\n\nDetails: {log}" if log else ""))
            return
        anzahl = int(getattr(liste, "anzahl_kunden", 0) or 0)
        if not anzahl:
            if spalten is None:
                self._spalten_zuordnen(pfad)
                return
            self._dialog("warning", "Kundenliste nicht importiert",
                         "In der CSV-Datei wurde kein Kunde gefunden (leere Spalten?). Es wurde nichts gespeichert.")
            return
        try:
            liste.speichern(dateien.kundenliste_pfad())
        except Exception as fehler:
            log = dateien.fehler_protokollieren(*sys.exc_info())
            self._dialog("error", "Kundenliste nicht gespeichert",
                         f"Die Kundenliste konnte nicht gespeichert werden:\n"
                         f"{_verstaendliche_fehlermeldung(fehler)}" + (f"\n\nDetails: {log}" if log else ""))
            return
        self.kundenliste = liste
        self._kundenliste_anzeigen()
        hinweis = "" if self._kundenliste_nutzbar() else (" Hinweis: Diese Programmversion nutzt die Kundenliste "
                                                           "noch nicht beim Analysieren.")
        self._log(f"✔ Kundenliste: {anzahl} Kunden importiert – gespeichert ohne Klartext (nur Prüfwerte). "
                  f"Die CSV-Datei selbst wurde nicht verändert.{hinweis}", "ok")
        self._einstellung_geaendert()
        self._dialog("info", "Kundenliste importiert",
                     f"{anzahl} Kunden geladen – gespeichert ohne Klartext.\n\nDas Programm merkt sich nur "
                     f"verschlüsselte Prüfwerte, keine Namen oder Nummern. Die CSV-Datei wurde nicht verändert und "
                     f"kann gelöscht werden, wenn sie sonst nicht gebraucht wird.{hinweis}")

    def _spalten_zuordnen(self, pfad: Path):
        try:
            vorschau = dateien.csv_vorschau(pfad)
        except (OSError, ValueError) as fehler:
            self._dialog("error", "Kundenliste nicht lesbar", f"„{pfad.name}“ ist keine lesbare CSV-Datei:\n{fehler}")
            return
        if not vorschau["zeilen"]:
            self._dialog("warning", "Kundenliste leer", f"„{pfad.name}“ enthält keine Daten.")
            return
        self.spalten_dialog = SpaltenDialog(self, pfad, vorschau,
                                            lambda spalten: self._kundenliste_import(pfad, spalten))

    def kundenliste_entfernen(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        pfad = dateien.kundenliste_pfad()
        if self.kundenliste is None and not pfad.exists():
            self._dialog("info", "Keine Kundenliste", "Es ist keine Kundenliste gespeichert.")
            return
        anzahl = int(getattr(self.kundenliste, "anzahl_kunden", 0) or 0) if self.kundenliste else 0
        if not self._frage("Kundenliste entfernen", f"Die gespeicherte Kundenliste ({anzahl} Kunden) wird "
                                                     f"gelöscht. Fortfahren?"):
            return
        try:
            if hasattr(Kundenliste, "entfernen"):
                Kundenliste.entfernen(pfad)
            elif pfad.exists():
                pfad.unlink()
        except OSError as fehler:
            self._dialog("error", "Kundenliste nicht entfernt", _verstaendliche_fehlermeldung(fehler, pfad))
            return
        self.kundenliste = None
        self._kundenliste_anzeigen()
        self._log("ℹ Kundenliste entfernt.", "hinweis")
        self._einstellung_geaendert()

    # ------------------------------------------------------------------
    # Lauf-Verwaltung (Sperren, Fortschritt, Abbruch)
    # ------------------------------------------------------------------
    def _eingaben_sperren(self, sperren: bool):
        zustand = "disabled" if sperren else "normal"
        for w in self._sperrbar:
            try:
                w.config(state=zustand)
            except tk.TclError:
                pass
        self.drop_zone.config(fg=FARBE_TEXT_GRAU if sperren else FARBE_AKZENT,
                              cursor="arrow" if sperren else "hand2")
        self._kunden_knoepfe_aktualisieren()
        for fenster in self.vorschauen.values():
            fenster.sperren(sperren)

    def _lauf_starten(self, art: str):
        self.laeuft = True
        self.lauf_art = art
        self.abbruch = threading.Event()
        self.ocr = None
        self.warnungen_anzahl = 0
        self._warnzaehler_anzeigen()
        self._eingaben_sperren(True)
        self.analyse_knopf.config(state="disabled", text="  Analysiere …  " if art == "analyse" else ANALYSE_TEXT)
        self.start_knopf.config(state="disabled", text="  Läuft …  " if art == "schwaerzen" else START_TEXT)
        self.abbrechen_knopf.config(state="normal")
        self.ordner_knopf.config(state="disabled")
        self.fortschritt.config(value=0, maximum=1)
        titel = "Analyse" if art == "analyse" else "Schwärzung"
        self._trenner(f"{titel} {datetime.now():%d.%m.%Y %H:%M:%S} · Schutzstufe {_profil_name(self.basis_profil)}")

    def _lauf_beenden(self):
        self.laeuft = False
        self.lauf_art = None
        self.laeufe_beendet += 1
        self.abbruch = None
        self.ocr = None
        self._eingaben_sperren(False)
        self.analyse_knopf.config(state="normal", text=ANALYSE_TEXT)
        self.start_knopf.config(text=START_TEXT)
        self.abbrechen_knopf.config(state="disabled")
        self.ordner_knopf.config(state="normal" if self.letzte_ausgabeordner else "disabled")
        self._start_knopf_aktualisieren()

    def _ocr_dienst_anlegen(self):
        """Ein OCR-Dienst je Lauf (im Arbeits-Thread angelegt, damit die Oberfläche nicht wartet)."""
        try:
            return OcrDienst()
        except Exception as fehler:
            self._log(f"⚠ OCR-Dienst konnte nicht gestartet werden ({fehler}) – OCR läuft ohne Hilfsprozesse.",
                      "warnung")
            return None

    @staticmethod
    def _ocr_schliessen(ocr):
        if ocr is None:
            return
        try:
            ocr.schliessen()
        except Exception:
            pass

    def abbrechen(self):
        if not self.laeuft or self.abbruch is None:
            return
        self.abbruch.set()
        ocr = self.ocr
        if ocr is not None:
            try:
                ocr.abbrechen()
            except Exception:
                pass
        self.abbrechen_knopf.config(state="disabled")
        self._status("Abbruch angefordert – die aktuelle Seite wird noch beendet …")
        self._log("Abbruch angefordert …", "warnung", zaehlen=False)

    def _laeuft_hinweis(self):
        self._dialog("info", "Lauf läuft noch",
                     "Gerade läuft noch eine Analyse oder Schwärzung. Bitte warten oder „Abbrechen“ drücken.")

    def schliessen(self):
        """Fenster schließen (Rückfrage, solange ein Lauf aktiv ist); Einstellungen sichern, Sperre freigeben."""
        if self.laeuft:
            antwort = messagebox.askyesno(
                "Lauf läuft noch",
                "Es läuft noch eine Analyse oder Schwärzung. Wirklich beenden?\n\n"
                "Bereits fertige Ausgabedateien bleiben erhalten; die aktuelle Datei wird nicht fertig.",
                icon="warning", parent=self.root)
            self.letzter_dialog = ("askyesno", "Lauf läuft noch", str(antwort))
            if not antwort:
                return
            self.abbrechen()
        try:
            self.einstellungen_speichern()
        except Exception:
            pass
        self.beendet = True
        self._aufraeumen()
        self.root.destroy()

    def _aufraeumen(self):
        """Prozessweite Zustände zurückgeben (KQ-10): threading.excepthook, Einzelinstanz-Sperre."""
        if threading.excepthook == self._thread_excepthook:
            threading.excepthook = self._alter_threading_haken
        if self.instanz_sperre is not None:
            self.instanz_sperre.freigeben()
            self.instanz_sperre = None
        try:
            self._vorschau_dateien_freigeben()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Namenserkennung vorladen (PERF-09)
    # ------------------------------------------------------------------
    def modell_vorladen(self):
        """Lädt das spaCy-Modell kurz nach dem Start im Hintergrund, damit der erste Klick auf „Analysieren“
        nicht hängt. Nur wenn Namen erkannt werden sollen und kein Lauf aktiv ist."""
        if self.beendet or self.laeuft or self.vorladen_thread is not None:
            return
        var = self.kategorie_vars.get("namen")
        if var is not None and not var.get():
            return
        vorher = self.status_label.cget("text")
        self.status_label.config(text="Namenserkennung wird vorbereitet …")

        def laden():
            try:
                with self._ner_sperre:
                    lade_ner()
            except Exception:
                dateien.fehler_protokollieren(*sys.exc_info())
            finally:
                self._im_hauptthread(self._vorladen_fertig, vorher)

        self.vorladen_thread = threading.Thread(target=laden, daemon=True, name="Modell-Vorladen")
        self.vorladen_thread.start()

    def _vorladen_fertig(self, vorher):
        if not self.laeuft and self.status_label.cget("text") == "Namenserkennung wird vorbereitet …":
            self.status_label.config(text=vorher if vorher and vorher != "Bereit." else "Bereit – Namenserkennung "
                                                                                       "geladen.")

    # ------------------------------------------------------------------
    # Analyse
    # ------------------------------------------------------------------
    def _analyse_zusatz(self) -> dict:
        """Optionale Vertragsparameter (Phase 2), soweit analysiere_pdf sie kennt."""
        zusatz = {}
        if kann(analysiere_pdf, "profil"):
            zusatz["profil"] = self.basis_profil
        if self.kundenliste is not None and kann(analysiere_pdf, "kundenliste"):
            zusatz["kundenliste"] = self.kundenliste
        return zusatz

    def analysieren(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        if not self.dateien:
            self._dialog("warning", "Keine Dateien", "Bitte zuerst PDF-Dateien auswählen (Schritt 1).")
            return
        self.einstellungen_speichern()
        aktive = self._aktive_kategorien()
        immer = self._zeilen_aus(self.immer_feld)
        nie = self._zeilen_aus(self.nie_feld)
        pdfs = list(self.dateien)                       # Kopie: der Thread arbeitet nie auf der Live-Liste
        immer_je_datei = {pdf: immer + [b for b in self.lauf_immer.get(pdf, []) if b not in immer] for pdf in pdfs}
        zusatz = self._analyse_zusatz()

        markierungen = sum(len(m) for m in self.manuell.values())
        self._vorschauen_schliessen()
        self.manuell.clear()
        self.analyse_ergebnisse = {}
        self.analyse_veraltet = False
        for iid in self.zeilen:
            self.baum.delete(*self.baum.get_children(iid))
            self.baum.set(iid, "kategorie", "wird analysiert …")
            self.baum.set(iid, "anzahl", "")
            self._zustand_setzen(iid, "aus")
        self._lauf_starten("analyse")
        if markierungen:
            self._log(f"ℹ {markierungen} manuelle Markierung(en) der letzten Vorschau wurden verworfen (neue "
                      f"Analyse) – bitte in der Vorschau erneut setzen.", "hinweis")
        if self.kundenliste is not None and "kundenliste" not in zusatz:
            self._log("ℹ Die Kundenliste wird von dieser Programmversion noch nicht beim Analysieren genutzt.",
                      "hinweis")
        self._status("Analyse startet …")
        threading.Thread(target=self._analyse_lauf, args=(pdfs, aktive, nie, immer_je_datei, zusatz, self.abbruch),
                         daemon=True, name="Analyse").start()

    def _analyse_lauf(self, pdfs, aktive, nie, immer_je_datei, zusatz, abbruch):
        ergebnisse: dict[Path, dict] = {}
        fehler_intern = None
        erster_fehler = None
        weitergabe_neu = 0
        ocr = None
        try:
            ocr = self._ocr_dienst_anlegen()
            self.ocr = ocr
            seiten = {pdf: _seitenzahl(pdf) for pdf in pdfs}
            gesamt_seiten = max(1, sum(seiten.values()))
            self._fortschritt_maximum(gesamt_seiten)
            if "namen" in aktive:
                self._status("Lade Namenserkennungs-Modell …")
                try:
                    with self._ner_sperre:              # wartet ggf. auf das Vorladen (PERF-09)
                        lade_ner()
                except Exception as fehler:
                    dateien.fehler_protokollieren(*sys.exc_info())
                    self._log(f"✖ Namenserkennung konnte nicht geladen werden ({type(fehler).__name__}: {fehler}) "
                              f"– Namen werden in diesem Lauf NICHT erkannt!", "fehler")
            lauf = None
            if LaufWissen is not None and kann(analysiere_pdf, "lauf"):
                try:
                    lauf = LaufWissen()
                except Exception:
                    dateien.fehler_protokollieren(*sys.exc_info())
            if lauf is not None:
                zusatz = dict(zusatz, lauf=lauf)
            basis = 0
            for nr, pdf in enumerate(pdfs, 1):
                if abbruch.is_set():
                    break
                name = self._anzeigename(pdf)
                self._status(f"Analyse: Datei {nr}/{len(pdfs)} – {name}")

                def fortschritt(seite, gesamt, _basis=basis, _nr=nr, _pdf=pdf, _name=name):
                    self._fortschritt_setzen(_basis + min(int(seite), seiten[_pdf]))
                    self._status(f"Analyse: Datei {_nr}/{len(pdfs)}, Seite {seite}/{gesamt} – {_name}")

                try:                                        # jede Datei für sich (KQ-03)
                    ergebnis = analysiere_pdf(pdf, aktive, nie, immer_je_datei[pdf],
                                              melde=lambda t: self._log(t, "grau"), fortschritt=fortschritt,
                                              abbruch=abbruch, ocr=ocr, **zusatz)
                    ergebnis = _analyse_ergebnis_pruefen(ergebnis, pdf)
                    if ergebnis["fehler"] and ergebnis["fehler"] != "Abgebrochen":
                        ergebnis["fehler"] = _fehlertext_verstaendlich(ergebnis["fehler"])
                except Exception as fehler:
                    log = dateien.fehler_protokollieren(*sys.exc_info())
                    if erster_fehler is None:
                        erster_fehler = (log, fehler)
                    ergebnis = _fehler_ergebnis(pdf, _verstaendliche_fehlermeldung(fehler, pdf))
                ergebnisse[pdf] = ergebnis
                self._analyse_protokollieren(name, ergebnis)
                self._im_hauptthread(self._datei_ergebnis_uebernehmen, pdf, ergebnis)
                basis += seiten[pdf]
                self._fortschritt_setzen(basis)
            if weitergabe_anwenden is not None and not abbruch.is_set():
                gute = [e for e in ergebnisse.values() if not e["fehler"]]
                if len(gute) > 1:
                    try:
                        weitergabe_neu = int(weitergabe_anwenden(gute) or 0)
                    except Exception:
                        dateien.fehler_protokollieren(*sys.exc_info())
                        self._log("⚠ Dokumentübergreifende Suche (Namen aus anderen Dateien dieses Laufs) ist "
                                  "fehlgeschlagen – Details in fehler.log. Die Funde je Datei bleiben gültig.",
                                  "warnung")
        except Exception:
            fehler_intern = sys.exc_info()
        finally:
            self._ocr_schliessen(ocr)
            self._im_hauptthread(self._analyse_fertig, pdfs, ergebnisse, abbruch.is_set(), fehler_intern,
                                 erster_fehler, weitergabe_neu)

    def _datei_ergebnis_uebernehmen(self, pdf: Path, ergebnis: dict):
        """Im Hauptthread: Ergebnis einer Datei übernehmen und ihre Funde eintragen."""
        self.analyse_ergebnisse[pdf] = ergebnis
        self._baum_datei_fuellen(pdf, ergebnis)

    def _analyse_protokollieren(self, name: str, ergebnis: dict):
        codes = meldungs_codes(ergebnis)
        abgebrochen = "ABGEBROCHEN" in codes
        if ergebnis["fehler"]:
            self._log(f"✖ {name}: {ergebnis['fehler']}", "fehler", zaehlen=not abgebrochen)
        for w in ergebnis["warnungen"]:
            if abgebrochen and w.strip() == "Abgebrochen":
                continue                                    # Abbruch nicht doppelt melden (GR-07)
            self._log(f"⚠ {name}: {w}", "warnung")
        for h in ergebnis["hinweise"]:
            self._log(f"ℹ {name}: {h}", "hinweis")
        if not abgebrochen:
            zusatz = f", {ergebnis['seiten']} Seite(n)" if ergebnis["seiten"] else ""
            if ergebnis["ocr_seiten"]:
                zusatz += f", davon {ergebnis['ocr_seiten']} per OCR"
            self._log(f"{name}: {len(ergebnis['funde'])} Fund(e){zusatz}", "grau")

    def _analyse_fertig(self, pdfs, ergebnisse, abgebrochen, fehler_intern, erster_fehler=None, weitergabe_neu=0):
        self.analyse_ergebnisse.update(ergebnisse)
        for pdf in pdfs:
            if pdf not in ergebnisse and str(pdf) in self.zeilen and self.baum.exists(str(pdf)):
                self.baum.set(str(pdf), "kategorie", "nicht analysiert (abgebrochen)" if abgebrochen
                              else "nicht analysiert")
        if weitergabe_neu:
            for pdf, ergebnis in ergebnisse.items():
                self._baum_datei_fuellen(pdf, ergebnis)
        self._lauf_beenden()
        if erster_fehler is not None:
            self._fehler_dialog(*erster_fehler)
        if fehler_intern:
            self._fehler_melden(*fehler_intern)
        if abgebrochen:
            self.analyse_veraltet = True
            self._start_knopf_aktualisieren()
            self._log("Analyse abgebrochen – Fundliste unvollständig. Bitte erneut analysieren.", "fehler",
                      zaehlen=False)
            self._status("Analyse abgebrochen – bitte erneut analysieren.")
            return
        if weitergabe_neu:
            self._log(f"ℹ Dokumentübergreifende Suche: {weitergabe_neu} weitere Stelle(n) mit Namen/Kennungen aus "
                      f"anderen Dateien dieses Laufs ergänzt.", "hinweis")

        gesamt = sum(len(e["funde"]) for e in ergebnisse.values())
        codes = {pdf: meldungs_codes(e) for pdf, e in ergebnisse.items()}
        ohne_text = [pdf for pdf, e in ergebnisse.items() if not e["funde"]
                     and codes[pdf] & {"KEIN_TEXT", "KAUM_LESBAR"}]
        gesundheit = [pdf for pdf in ergebnisse if "GESUNDHEITSDATEN" in codes[pdf]]
        mit_fehler = [(pdf, e["fehler"]) for pdf, e in ergebnisse.items() if e["fehler"]]
        mit_warnung = [(pdf, e["warnungen"]) for pdf, e in ergebnisse.items() if e["warnungen"]]

        if gesamt:
            self._log(f"Analyse fertig: {gesamt} Fund(e) in {len(ergebnisse)} Datei(en). "
                      f"Bitte Liste prüfen (Doppelklick = Vorschau), dann schwärzen.", "ok")
            self._status(f"{gesamt} Fund(e) in {len(ergebnisse)} Datei(en) – Liste prüfen (Doppelklick auf eine "
                         f"Datei = Vorschau), dann schwärzen.")
        else:
            self._log(f"Analyse fertig: 0 Funde in {len(ergebnisse)} Datei(en) – es gibt nichts zu schwärzen, "
                      f"es wird keine Ausgabedatei erzeugt.", "warnung" if ohne_text else "ok", zaehlen=False)
            self._status("Keine Funde – nichts zu schwärzen. Bitte Hinweise im Protokoll lesen.")

        zeilen = []
        art = "info"
        if gesamt == 0:
            zeilen.append("Es wurden keine personenbezogenen Daten erkannt. Es gibt nichts zu schwärzen, "
                          "deshalb bleibt der Schwärzen-Knopf aus und es wird keine Ausgabedatei erzeugt.")
            if ohne_text:
                art = "warning"
                zeilen.append("")
                zeilen.append("ACHTUNG – in diesen Dateien war kein Text lesbar (z. B. unlesbarer Scan). "
                              "Dort konnte NICHTS geprüft werden; diese Dateien nicht ungeprüft weitergeben:")
                zeilen += [f"  • {self._anzeigename(p)}" for p in ohne_text[:10]]
            else:
                zeilen.append("")
                zeilen.append("Mögliche Gründe: Das Dokument enthält keine Namen, IBANs, Adressen usw. "
                              "(z. B. ein Bedingungswerk), oder die Daten stehen in Bildern oder Handschrift. "
                              "Bitte das Dokument selbst durchsehen (Doppelklick = Vorschau).")
        if mit_fehler:
            art = "warning"
            zeilen.append("")
            zeilen.append("Nicht analysierbar:")
            zeilen += [f"  • {self._anzeigename(p)}: {f}" for p, f in mit_fehler[:10]]
        if gesundheit and self.basis_profil != "maximal":
            art = "warning"
            zeilen.append("")
            zeilen.append("Gesundheitsdaten (Art. 9 DSGVO) erkannt – sie bleiben in dieser Schutzstufe lesbar; "
                          "„Maximal“ schwärzt sie:")
            zeilen += [f"  • {self._anzeigename(p)}" for p in gesundheit[:10]]
        if self.warnungen_anzahl and gesamt:
            art = "warning"
            zeilen.insert(0, f"Die Analyse hat {gesamt} Fund(e) ergeben und {self.warnungen_anzahl} "
                             f"Warnung(en)/Fehler gemeldet (Details im Protokoll):")
            for p, ws in mit_warnung[:10]:
                zeilen.append(f"  • {self._anzeigename(p)}: {ws[0]}" + (f" (+{len(ws) - 1})" if len(ws) > 1 else ""))
        elif self.warnungen_anzahl and not gesamt and mit_warnung and not ohne_text:
            art = "warning"
            zeilen.append("")
            zeilen.append(f"{self.warnungen_anzahl} Warnung(en) – Details im Protokoll.")
        if zeilen:
            self._dialog(art, "Analyse abgeschlossen" if gesamt else "Keine Funde", "\n".join(zeilen))

    # ------------------------------------------------------------------
    # Schwärzen
    # ------------------------------------------------------------------
    def _zielordner(self):
        """(ok, Pfad|None): gewählter gemeinsamer Zielordner oder None (= neben dem Original)."""
        if not self.zielordner_aktiv.get():
            return True, None
        text = self.zielordner_var.get().strip()
        if not text:
            self._dialog("warning", "Zielordner fehlt",
                         "Bitte einen gemeinsamen Zielordner wählen oder die Option abschalten.")
            return False, None
        ziel = Path(text)
        try:
            ziel.mkdir(parents=True, exist_ok=True)
        except OSError as fehler:
            self._dialog("error", "Zielordner nicht nutzbar",
                         f"Der Zielordner kann nicht angelegt werden:\n{ziel}\n\n"
                         f"{_verstaendliche_fehlermeldung(fehler, ziel)}")
            return False, None
        return True, ziel

    def _auftrag(self, pdf: Path) -> dict | None:
        """Schwärz-Auftrag einer Datei aus den Häkchen: Funde (mit Stellen-Zuständen), manuelle Markierungen."""
        ergebnis = self.analyse_ergebnisse.get(pdf)
        if not ergebnis:
            return None
        funde = []
        for index, fund in enumerate(ergebnis["funde"]):
            if self.fund_zustand(pdf, index) == "aus":
                continue
            kopie = dict(fund)
            if self._fund_hat_stellen(pdf, fund):
                kopie["stellen"] = [dict(s) for s in fund["stellen"]]
            funde.append(kopie)
        bereiche: dict[int, list] = {}
        stellen: dict[int, list] = {}
        for eintrag in self.manuell.get(pdf, {}).values():
            if not eintrag.get("an", True):
                continue
            if eintrag["art"] == "bereich":
                bereiche.setdefault(eintrag["seite"], []).extend(fitz.Rect(r) for r in eintrag["rechtecke"])
            else:
                stellen.setdefault(eintrag["seite"], []).append(
                    (int(eintrag["start"]), int(eintrag["ende"]), PLATZHALTER_MANUELL))
        if not funde and not bereiche and not stellen:
            return None
        return {"pdf": pdf, "funde": funde, "ocr_cache": ergebnis.get("ocr_cache"),
                "modell": ergebnis.get("modell") if self.einzelstellen_moeglich(pdf) else None,
                "bereiche": bereiche, "stellen": stellen}

    def schwaerzen(self, nur: list | None = None, ersetzt: Path | None = None) -> bool:
        """Schwärzt alle angehakten Funde (bzw. nur die Dateien in „nur“, z. B. zum Nachschwärzen; die Ausgabe
        „ersetzt“ wird nach Erfolg verworfen). Liefert True, wenn ein Lauf gestartet wurde."""
        if self.laeuft:
            self._laeuft_hinweis()
            return False
        if self.analyse_veraltet:
            self._dialog("info", "Erneut analysieren",
                         "Schutzstufe, Kategorien, Listen oder Dateien wurden seit der letzten Analyse geändert. "
                         "Bitte zuerst erneut analysieren.")
            return False
        dateiliste = list(nur) if nur is not None else list(self.dateien)
        nicht_analysiert = [p for p in dateiliste if p not in self.analyse_ergebnisse]
        if nicht_analysiert:
            self._dialog("info", "Erst analysieren",
                         f"{len(nicht_analysiert)} Datei(en) sind noch nicht analysiert "
                         f"(z. B. {nicht_analysiert[0].name}). Bitte zuerst „Analysieren“ drücken.")
            return False
        auftraege = [a for a in (self._auftrag(p) for p in dateiliste) if a]
        if not auftraege:
            self._dialog("warning", "Nichts ausgewählt", "Es ist kein Fund angehakt – es gibt nichts zu schwärzen.")
            return False
        fehlt = []
        if any(a["bereiche"] for a in auftraege) and not self.kann_manuelle_bereiche():
            fehlt.append("Rahmen-Bereiche")
        if any(a["stellen"] for a in auftraege) and not self.kann_manuelle_stellen():
            fehlt.append("einzelne Stellen")
        if fehlt:
            self._dialog("error", "Nicht möglich", f"Diese Programmversion kann {' und '.join(fehlt)} aus der Vorschau "
                                                   f"nicht schwärzen. Bitte diese Markierungen entfernen oder als "
                                                   f"IMMER-Begriff eintragen.")
            return False
        if ersetzt is not None:
            ok, ziel_ordner = True, Path(ersetzt).parent
        else:
            ok, ziel_ordner = self._zielordner()
        if not ok:
            return False
        self.einstellungen_speichern()
        if nur is None:
            self.letzte_ausgabeordner = []
        freigabe = bool(self.freigabe_var.get())
        self._lauf_starten("schwaerzen")
        self._status("Schwärzung startet …")
        threading.Thread(target=self._schwaerz_lauf,
                         args=(auftraege, ziel_ordner, self.abbruch, freigabe, self.basis_profil, ersetzt),
                         daemon=True, name="Schwaerzung").start()
        return True

    def _schwaerz_lauf(self, auftraege, ziel_ordner, abbruch, freigabe=True, profil="hoch", ersetzt=None):
        ergebnisse: list[tuple[Path, dict]] = []
        fehler_intern = None
        erster_fehler = None
        ocr = None
        try:
            ocr = self._ocr_dienst_anlegen()
            self.ocr = ocr
            seiten = {a["pdf"]: _seitenzahl(a["pdf"]) for a in auftraege}
            self._fortschritt_maximum(max(1, sum(seiten.values())))
            ordner = {ziel_ordner} if ziel_ordner else {a["pdf"].parent / dateien.AUSGABE_ORDNER for a in auftraege}
            for o in sorted(ordner):
                entfernt = dateien.zwischendateien_aufraeumen(o)
                if entfernt:
                    self._log(f"ℹ {len(entfernt)} verwaiste Zwischendatei(en) einer abgebrochenen Schwärzung in "
                              f"{o} gelöscht.", "hinweis")
            basis = 0
            for nr, auftrag in enumerate(auftraege, 1):
                if abbruch.is_set():
                    break
                pdf = auftrag["pdf"]
                name = self._anzeigename(pdf)
                self._status(f"Schwärzung: Datei {nr}/{len(auftraege)} – {name}")

                def fortschritt(seite, gesamt, _basis=basis, _nr=nr, _pdf=pdf, _name=name):
                    self._fortschritt_setzen(_basis + min(int(seite), seiten[_pdf]))
                    self._status(f"Schwärzung: Datei {_nr}/{len(auftraege)}, Seite {seite}/{gesamt} – {_name}")

                kwargs = {"melde": lambda t: self._log(t, "grau"), "fortschritt": fortschritt, "abbruch": abbruch,
                          "ocr": ocr, "ocr_cache": auftrag["ocr_cache"], "ziel_ordner": ziel_ordner}
                if auftrag["modell"] is not None:
                    kwargs["modell"] = auftrag["modell"]
                if auftrag["bereiche"]:
                    kwargs["manuelle_bereiche"] = auftrag["bereiche"]
                if auftrag["stellen"]:
                    kwargs["manuelle_stellen"] = auftrag["stellen"]
                freigabe_engine = kann(schwaerze_pdf, "freigabe_erforderlich")
                if freigabe_engine:
                    kwargs["freigabe_erforderlich"] = freigabe
                if kann(schwaerze_pdf, "profil"):
                    kwargs["profil"] = profil
                try:
                    ergebnis = _schwaerz_ergebnis_pruefen(schwaerze_pdf(pdf, auftrag["funde"], **kwargs), pdf)
                    if ergebnis["fehler"] and ergebnis["fehler"] != "Abgebrochen":
                        ergebnis["fehler"] = _fehlertext_verstaendlich(ergebnis["fehler"])
                    if freigabe and not freigabe_engine:
                        self._freigabe_emulieren(ergebnis)
                    self._reste_verorten(ergebnis)
                except Exception as fehler:
                    log = dateien.fehler_protokollieren(*sys.exc_info())
                    if erster_fehler is None and not isinstance(fehler, OSError):
                        erster_fehler = (log, fehler)
                    ergebnis = {"original": pdf, "ausgabe": None, "treffer": 0, "uebersprungen": 0,
                                "warnungen": [], "hinweise": [], "reste": [],
                                "fehler": _verstaendliche_fehlermeldung(fehler, pdf)}
                ergebnis["_status"] = self._ausgabe_status(ergebnis)
                ergebnisse.append((pdf, ergebnis))
                self._schwaerz_protokollieren(name, ergebnis)
                basis += seiten[pdf]
                self._fortschritt_setzen(basis)
        except Exception:
            fehler_intern = sys.exc_info()
        finally:
            self._ocr_schliessen(ocr)
            self._im_hauptthread(self._schwaerzen_fertig, auftraege, ergebnisse, abbruch.is_set(), fehler_intern,
                                 erster_fehler, ersetzt)

    @staticmethod
    def _reste_verorten(ergebnis: dict):
        """Reste der Selbstkontrolle (nur Text) in der Ausgabe suchen: die Vorschau zeigt sie dann orange wie einen
        Verdacht und „Nachschwärzen“ erfasst sie (läuft im Arbeits-Thread)."""
        ausgabe = ergebnis.get("ausgabe")
        if not ergebnis["reste"] or ergebnis["fehler"] or ausgabe is None or not Path(ausgabe).exists():
            return
        try:
            ergebnis["_reste_verdacht"] = attrappen.reste_als_verdacht(ausgabe, ergebnis["reste"],
                                                                       ergebnis.get("verdacht") or [])
        except Exception:
            dateien.fehler_protokollieren(*sys.exc_info())

    @staticmethod
    def _freigabe_emulieren(ergebnis: dict):
        """Engine ohne freigabe_erforderlich: fertige Ausgabe selbst als _PRUEFEN markieren (Attrappe)."""
        ausgabe = ergebnis.get("ausgabe")
        if ergebnis["fehler"] or ausgabe is None or not Path(ausgabe).exists():
            return
        ergebnis["status"] = "pruefen"
        ergebnis["_freigabe_emuliert"] = True
        try:
            ergebnis["ausgabe"] = attrappen.als_pruefen_markieren(ausgabe)
        except OSError as fehler:
            ergebnis["warnungen"].append(f"Die Ausgabe konnte nicht als „_PRUEFEN“ markiert werden ({fehler}) – "
                                         f"sie ist trotzdem erst nach Prüfung in der Vorschau weiterzugeben.")

    @staticmethod
    def _ausgabe_status(ergebnis: dict) -> str:
        """fertig | pruefen | fehler | keine – die Engine meldet „status“ (Vertrag 5), sonst aus dem Namen."""
        ausgabe = ergebnis.get("ausgabe")
        if ergebnis["fehler"]:
            return "fehler"
        if ausgabe is None:
            return "keine"
        status = ergebnis.get("status")
        if "_PRUEFEN" in Path(ausgabe).name.upper() or ergebnis.get("reste") or ergebnis.get("verdacht") \
                or int(ergebnis.get("stellen_nicht_lokalisiert") or 0):
            return "pruefen"                           # im Zweifel prüfen, auch wenn „status“ anderes sagt
        return status if status in ("fertig", "pruefen") else "fertig"

    def _schwaerz_protokollieren(self, name: str, ergebnis: dict):
        codes = meldungs_codes(ergebnis)
        abgebrochen = "ABGEBROCHEN" in codes
        if (ergebnis["treffer"] == 0 and not ergebnis["fehler"] and ergebnis["ausgabe"] is None
                and "KEIN_TREFFER" not in codes):
            ergebnis["warnungen"].append(WARNUNG_KEIN_TREFFER)
        if ergebnis["fehler"]:
            self._log(f"✖ {name}: {ergebnis['fehler']}", "fehler", zaehlen=not abgebrochen)
        elif ergebnis["ausgabe"] is not None:
            zusatz = " – zu prüfen, dann in der Vorschau freigeben" if ergebnis["_status"] == "pruefen" else ""
            self._log(f"✔ {name}  →  {ergebnis['ausgabe']}  ({ergebnis['treffer']} Stelle(n) ersetzt){zusatz}", "ok")
        else:
            self._log(f"⚠ {name}: keine Ausgabedatei erzeugt.", "warnung", zaehlen=False)
        for w in ergebnis["warnungen"]:
            if abgebrochen and w.strip() == "Abgebrochen":
                continue
            self._log(f"⚠ {name}: {w}", "warnung")
        for h in ergebnis["hinweise"]:
            self._log(f"ℹ {name}: {h}", "hinweis")
        if ergebnis["reste"]:
            self._log(f"⚠ {name}: noch auffindbar: {', '.join(ergebnis['reste'][:5])} – Ausgabe prüfen!", "warnung",
                      zaehlen=False)
        verdacht = ergebnis.get("verdacht") or []
        if verdacht:
            self._log(f"⚠ {name}: {len(verdacht)} Verdachtsstelle(n) in der Ausgabe – in der Vorschau prüfen "
                      f"(nachschwärzen oder freigeben).", "warnung", zaehlen="VERDACHT" not in codes)
        nicht_lokalisiert = int(ergebnis.get("stellen_nicht_lokalisiert") or 0)
        if nicht_lokalisiert:
            self._log(f"✖ {name}: {nicht_lokalisiert} Fundstelle(n) konnten nicht lokalisiert werden – Ausgabe "
                      f"unbedingt prüfen!", "fehler", zaehlen="NICHT_LOKALISIERT" not in codes)

    def _grund(self, ergebnis: dict, status: str) -> str:
        if status == "fehler":
            return ergebnis["fehler"] or ""
        if status == "keine":
            return ergebnis["warnungen"][0] if ergebnis["warnungen"] else "kein Treffer"
        teile = []
        verdacht = ergebnis.get("verdacht") or []
        if verdacht:
            teile.append(f"{len(verdacht)} Verdachtsstelle(n)")
        if ergebnis["reste"]:
            teile.append(f"{len(ergebnis['reste'])} Fundtext(e) noch auffindbar")
        if int(ergebnis.get("stellen_nicht_lokalisiert") or 0):
            teile.append("Stellen nicht lokalisiert")
        if status == "pruefen" and not teile:
            teile.append("Freigabe ausstehend")
        return " · ".join(teile)

    def _schwaerzen_fertig(self, auftraege, ergebnisse, abgebrochen, fehler_intern, erster_fehler=None,
                           ersetzt=None):
        for pdf, e in ergebnisse:
            status = e.get("_status") or self._ausgabe_status(e)
            if status in ("fehler", "keine") and ersetzt is not None:
                continue                                  # Nachschwärzen gescheitert: alte Ausgabe bleibt gültig
            verdacht = list(e.get("verdacht") or []) + list(e.get("_reste_verdacht") or [])
            self.ausgaben[pdf] = {"pfad": e["ausgabe"], "status": status, "verdacht": verdacht,
                                  "ergebnis": e, "grund": self._grund(e, status)}
            self._ausgabe_zeile_setzen(pdf)
        geschrieben = [(pdf, e) for pdf, e in ergebnisse
                       if e["ausgabe"] is not None and Path(e["ausgabe"]).exists()]
        ohne_ausgabe = [(pdf, e) for pdf, e in ergebnisse
                        if not (e["ausgabe"] is not None and Path(e["ausgabe"]).exists())]
        verarbeitet = {pdf for pdf, _ in ergebnisse}
        nicht_verarbeitet = [a["pdf"] for a in auftraege if a["pdf"] not in verarbeitet]
        pruefen = [pdf for pdf, e in geschrieben if self.ausgaben.get(pdf, {}).get("status") == "pruefen"]
        ordner: list[Path] = list(self.letzte_ausgabeordner) if ersetzt is not None else []
        for _, e in geschrieben:
            if e["ausgabe"].parent not in ordner:
                ordner.append(e["ausgabe"].parent)
        self.letzte_ausgabeordner = ordner
        stellen = sum(e["treffer"] for _, e in geschrieben)
        self._lauf_beenden()
        if erster_fehler is not None:
            self._fehler_dialog(*erster_fehler)
        if fehler_intern:
            self._fehler_melden(*fehler_intern)
        if ersetzt is not None:
            if abgebrochen and not ergebnisse:
                self._status(f"Nachschwärzen abgebrochen – die bisherige Ausgabe {ersetzt.name} bleibt zu prüfen.")
            self._nachschwaerzen_fertig(ergebnisse, ersetzt, abgebrochen)
            return

        alles_gut = not ohne_ausgabe and not nicht_verarbeitet and not pruefen and not abgebrochen
        if abgebrochen:
            self._log("Schwärzung abgebrochen.", "fehler", zaehlen=False)
        self._log(f"Fertig: {len(geschrieben)} von {len(auftraege)} Datei(en) geschrieben, "
                  f"{stellen} Stelle(n) ersetzt.", "ok" if alles_gut else "warnung", zaehlen=False)
        for o in ordner:
            self._log(f"Ausgabeordner: {o}", "ok")
            if dateien.ist_cloud_ordner(o):
                self._log("ℹ Dieser Ordner wird von einem Cloud-Dienst synchronisiert – die Ausgabe landet "
                          "ebenfalls in der Cloud.", "hinweis")
        if pruefen:
            self._log(f"⚠ {len(pruefen)} Ausgabedatei(en) tragen „_PRUEFEN“ im Namen: in der Vorschau prüfen und "
                      f"freigeben (Doppelklick auf die Datei).", "warnung", zaehlen=False)
        self._log("Bitte jede Ausgabedatei prüfen, bevor sie an einen KI-Dienst geht – "
                  "das Programm pseudonymisiert nur direkte Identifikatoren.", "hinweis")
        self._status(f"Fertig: {len(geschrieben)} von {len(auftraege)} Datei(en) geschrieben, "
                     f"{stellen} Stelle(n) ersetzt." + ("" if alles_gut else " Bitte Hinweise beachten."))
        for pdf, fenster in list(self.vorschauen.items()):
            if self.ausgabe_vorhanden(pdf):
                fenster.modus_wechseln("nachher")

        zeilen = [f"{len(geschrieben)} von {len(auftraege)} Datei(en) geschrieben, {stellen} Stelle(n) ersetzt."]
        if abgebrochen:
            zeilen.append("Der Lauf wurde abgebrochen.")
        if ohne_ausgabe or nicht_verarbeitet:
            zeilen.append("")
            zeilen.append("OHNE Ausgabedatei (Original nicht weitergeben!):")
            for pdf, e in ohne_ausgabe[:10]:
                grund = e["fehler"] or (e["warnungen"][0] if e["warnungen"] else "kein Treffer")
                zeilen.append(f"  • {self._anzeigename(pdf)}: {grund}")
            for pdf in nicht_verarbeitet[:10]:
                zeilen.append(f"  • {self._anzeigename(pdf)}: nicht verarbeitet (abgebrochen)")
        if pruefen:
            zeilen.append("")
            zeilen.append(f"Zu prüfen: {len(pruefen)} Datei(en). {PRUEFEN_ERKLAERUNG}")
            for pdf in pruefen[:10]:
                eintrag = self.ausgaben[pdf]
                grund = eintrag.get("grund")
                zeilen.append(f"  • {self._anzeigename(pdf)} → {eintrag['pfad'].name}" + (f" ({grund})" if grund else ""))
            if len(pruefen) > 10:
                zeilen.append(f"  … und {len(pruefen) - 10} weitere")
        if self.warnungen_anzahl:
            zeilen.append("")
            zeilen.append(f"{self.warnungen_anzahl} Warnung(en)/Fehler – Details stehen im Protokoll.")
        if ordner:
            zeilen.append("")
            stamm = dateien.gemeinsamer_stamm(ordner) if len(ordner) > 3 else None
            if stamm is not None:
                zeilen.append(f"{len(ordner)} Ausgabeordner unterhalb von {stamm} (vollständige Liste im Protokoll).")
            else:
                zeilen.append("Ausgabeordner:")
                zeilen += [f"  {o}" for o in ordner[:5]]
                if len(ordner) > 5:
                    zeilen.append(f"  … und {len(ordner) - 5} weitere (siehe Protokoll)")
        zeilen.append("")
        zeilen.append("Bitte jede Ausgabedatei vor der Weitergabe prüfen.")
        art = "info" if alles_gut and not self.warnungen_anzahl else "warning"
        self._abschluss_dialog(art, "Schwärzung abgeschlossen", "\n".join(zeilen), ordner, pruefen)

    def _nachschwaerzen_fertig(self, ergebnisse, ersetzt: Path, abgebrochen: bool):
        """Ende eines Nachschwärz-Laufs: alte Ausgabe verwerfen, Vorschau auf die neue Ausgabe umstellen."""
        for pdf, e in ergebnisse:
            fenster = self.vorschauen.get(pdf)
            if e["ausgabe"] is not None and Path(e["ausgabe"]).exists() and not e["fehler"]:
                try:
                    self._vorschau_dateien_freigeben(ersetzt)
                    verwerfen(ersetzt)
                    self._log(f"ℹ {self._anzeigename(pdf)}: nachgeschwärzt → {e['ausgabe'].name} "
                              f"(alte Ausgabe {ersetzt.name} verworfen).", "ok")
                except Exception:
                    dateien.fehler_protokollieren(*sys.exc_info())
                    self._log(f"⚠ {self._anzeigename(pdf)}: alte Ausgabe {ersetzt.name} konnte nicht gelöscht "
                              f"werden – bitte von Hand löschen, sie ist NICHT nachgeschwärzt.", "warnung")
                self._status(f"Nachgeschwärzt: {e['ausgabe'].name} – bitte erneut prüfen.")
                if fenster is not None:
                    fenster.modus_wechseln("nachher")
            else:
                grund = e["fehler"] or (e["warnungen"][0] if e["warnungen"] else "keine Ausgabe")
                self._dialog("warning", "Nachschwärzen fehlgeschlagen",
                             f"„{self._anzeigename(pdf)}“ konnte nicht nachgeschwärzt werden: {grund}\n\n"
                             f"Die bisherige Ausgabe {ersetzt.name} bleibt unverändert und zu prüfen.")
                if fenster is not None:
                    fenster.neu_zeichnen()

    def _abschluss_dialog(self, art, titel, text, ordner, pruefen=()):
        self.letzter_dialog = (art, titel, text)
        if pruefen:
            erste = pruefen[0]
            frage = f"Vorschau von „{self._anzeigename(erste)}“ jetzt öffnen und prüfen?"
            if self._frage(titel, text + "\n\n" + frage, warnung=True):
                self.vorschau_oeffnen(erste, modus="nachher")
        elif ordner:
            if self._frage(titel, text + "\n\nErgebnisordner jetzt öffnen?", warnung=art == "warning"):
                self.ergebnisordner_oeffnen()
        else:
            self._dialog(art, titel, text)

    def ergebnisordner_oeffnen(self):
        ordner = list(self.letzte_ausgabeordner)
        if not ordner:
            self._dialog("info", "Kein Ergebnis", "Es wurde in dieser Sitzung noch keine Ausgabedatei erzeugt.")
            return
        if len(ordner) > 3:                                   # GR-12: nicht still nur die ersten drei
            stamm = dateien.gemeinsamer_stamm(ordner)
            if stamm is not None and dateien.oeffne_ordner(stamm):
                self._log(f"ℹ {len(ordner)} Ausgabeordner unterhalb von {stamm} – geöffnet wurde der gemeinsame "
                          f"Ordner (jeweils Unterordner „{dateien.AUSGABE_ORDNER}“).", "hinweis")
                return
            self._log(f"⚠ Geöffnet werden nur die ersten drei von {len(ordner)} Ausgabeordnern – alle stehen "
                      f"oben im Protokoll.", "warnung", zaehlen=False)
        for o in ordner[:3]:
            if not dateien.oeffne_ordner(o):
                self._log(f"⚠ Ordner konnte nicht geöffnet werden: {o}", "warnung", zaehlen=False)

    # ------------------------------------------------------------------
    # Hilfe
    # ------------------------------------------------------------------
    def hilfe_grenzen(self):
        self._dialog("info", "Was wird nicht erkannt?", GRENZEN_TEXT)

    def hilfe_ueber(self):
        self._dialog("info", "Über PDF-Anonymisierer",
                     f"PDF-Anonymisierer {__version__}\n\nPseudonymisiert PDFs lokal auf diesem Rechner "
                     f"(PyMuPDF, spaCy, Tesseract). Es werden keine Daten ins Internet übertragen.\n\n"
                     f"Fehlerprotokoll: {dateien.fehlerlog_pfad()}\n(enthält Dateinamen, aber keine Ordner und "
                     f"keine Dokumentinhalte)\nEinstellungen: {dateien.einstellungen_pfad()}")

    def fehlerlog_oeffnen(self):
        pfad = dateien.fehlerlog_pfad()
        try:
            pfad.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if not dateien.oeffne_ordner(pfad.parent):
            self._dialog("info", "Fehlerprotokoll", f"Das Fehlerprotokoll liegt hier:\n{pfad}")

    # ------------------------------------------------------------------
    # Fehler, Dialoge, Protokoll (thread-sicher)
    # ------------------------------------------------------------------
    def _dialog(self, art, titel, text, eltern=None):
        """Zeigt einen Hinweis (nur im Hauptthread aufrufen) und merkt ihn sich für Tests."""
        self.letzter_dialog = (art, titel, text)
        zeiger = {"info": messagebox.showinfo, "warning": messagebox.showwarning,
                  "error": messagebox.showerror}[art]
        try:
            zeiger(titel, text, parent=eltern or self.root)
        except tk.TclError:
            pass

    def _frage(self, titel, text, warnung=False, eltern=None) -> bool:
        """Ja/Nein-Frage (nur im Hauptthread); merkt sich den Text für Tests."""
        self.letzter_dialog = ("askyesno", titel, text)
        try:
            return bool(messagebox.askyesno(titel, text, icon="warning" if warnung else "question",
                                            parent=eltern or self.root))
        except tk.TclError:
            return False

    def _fehler_melden(self, typ, wert, tb):
        """Unerwartete Ausnahme (Tk-Callback oder Arbeits-Thread): fehler.log + Protokoll + Dialog."""
        try:
            pfad = dateien.fehler_protokollieren(typ, wert, tb)
        except Exception:
            pfad = None
        try:
            self._fehler_dialog(pfad, wert)
        except Exception:
            pass

    def _fehler_dialog(self, pfad, wert):
        ort = str(pfad) if pfad else "(das Fehlerprotokoll konnte nicht geschrieben werden)"
        self._log(f"✖ Unerwarteter Fehler: {type(wert).__name__}: {str(wert)[:200]} – Details: {ort}", "fehler")
        self._dialog("error", "Unerwarteter Fehler",
                     f"Es ist ein unerwarteter Fehler aufgetreten:\n{type(wert).__name__}: {str(wert)[:300]}\n\n"
                     f"Details stehen in:\n{ort}")

    def _thread_excepthook(self, args):
        """Sicherheitsnetz für Threads ohne eigene Fehlerbehandlung."""
        pfad = dateien.fehler_protokollieren(args.exc_type, args.exc_value, args.exc_traceback)
        self._im_hauptthread(self._fehler_dialog, pfad, args.exc_value)
        self._im_hauptthread(self._lauf_notfall_freigeben)

    def _lauf_notfall_freigeben(self):
        if self.laeuft:
            self._lauf_beenden()
            self._status("Lauf nach Fehler beendet.")

    def _im_hauptthread(self, funktion, *args):
        """Führt eine Funktion im Tk-Hauptthread aus (aus Arbeits-Threads aufrufbar; im Hauptthread sofort)."""
        if self.beendet:
            return                                      # Fenster wird geschlossen, Nachzügler verwerfen
        if threading.current_thread() is threading.main_thread():
            try:
                funktion(*args)
            except tk.TclError:
                pass                                    # Fenster bereits geschlossen
            return
        try:
            self.root.after(0, funktion, *args)
        except tk.TclError:
            pass                                        # Fenster bereits geschlossen
        except RuntimeError:
            # Hauptthread verarbeitet keine Ereignisse (kein mainloop): nicht still verschlucken, aber nur einmal melden
            if not self._hauptthread_fehler_gemeldet and not self.beendet:
                self._hauptthread_fehler_gemeldet = True
                dateien.fehler_protokollieren(*sys.exc_info())

    def _log(self, text, stil=None, zaehlen=True):
        """Protokollzeile; Stil „warnung“/„fehler“ zählt als Warnung einer Datei – außer zaehlen=False für
        eigene Statuszeilen (Abbruch, Fertig-Zeile, Zusammenfassungen; GR-07)."""
        if not text:
            return

        def einfuegen():
            if zaehlen and stil in ("warnung", "fehler"):
                self.warnungen_anzahl += 1
                self._warnzaehler_anzeigen()
            self.protokoll.config(state="normal")
            self.protokoll.insert("end", text + "\n", stil or ())
            zeilen = int(self.protokoll.index("end-1c").split(".")[0])
            if zeilen > PROTOKOLL_MAX_ZEILEN:
                self.protokoll.delete("1.0", f"{zeilen - PROTOKOLL_MAX_ZEILEN}.0")
            self.protokoll.see("end")
            self.protokoll.config(state="disabled")

        self._im_hauptthread(einfuegen)

    def _trenner(self, titel):
        self._log(f"──────── {titel} ────────", "trenner")

    def _warnzaehler_anzeigen(self):
        self.warn_label.config(text=f"⚠ {self.warnungen_anzahl} Warnung(en)/Fehler" if self.warnungen_anzahl else "")

    def _status(self, text):
        self._im_hauptthread(lambda: self.status_label.config(text=text))

    def _fortschritt_setzen(self, wert):
        self._im_hauptthread(lambda: self.fortschritt.config(value=wert))

    def _fortschritt_maximum(self, maximum):
        self._im_hauptthread(lambda: self.fortschritt.config(maximum=maximum, value=0))

    def protokoll_text(self) -> str:
        return self.protokoll.get("1.0", "end").rstrip("\n")


def _bereits_gestartet_melden():
    """Zweiter Start (GR-10): Hinweis statt eines zweiten Fensters."""
    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showinfo("PDF-Anonymisierer läuft bereits",
                            "Das Programm ist bereits geöffnet – bitte das vorhandene Fenster verwenden "
                            "(Taskleiste). Zwei gleichzeitige Fenster würden sich Einstellungen und "
                            "Ausgabenummern gegenseitig überschreiben.", parent=root)
    except tk.TclError:
        pass
    finally:
        root.destroy()


def main(ereignisschleife: bool = True):
    """Startet die Oberfläche (eine Instanz je Benutzer); ohne Drag & Drop, wenn die tkdnd-Bibliothek nicht
    lädt. Liefert die App bzw. None, wenn bereits eine Instanz läuft."""
    global DND_VERFUEGBAR
    sperre = dateien.instanz_sperren()
    if sperre is None:
        _bereits_gestartet_melden()
        return None
    root = None
    if DND_VERFUEGBAR and TkinterDnD is not None:
        try:
            root = TkinterDnD.Tk()
        except Exception as fehler:          # z. B. tkdnd-DLL fehlt oder vom Virenscanner blockiert
            DND_VERFUEGBAR = False
            dateien.fehler_protokollieren(type(fehler), fehler, fehler.__traceback__)
    if root is None:
        root = tk.Tk()
    app = AnonymisiererApp(root, modell_vorladen=True)
    app.instanz_sperre = sperre

    def zerstoert(ereignis):
        if ereignis.widget is root:
            app._aufraeumen()

    root.bind("<Destroy>", zerstoert, add="+")
    if ereignisschleife:
        root.mainloop()
    return app
