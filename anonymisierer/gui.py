"""Grafische Oberfläche (tkinter): Dateien wählen, analysieren, Funde prüfen, schwärzen."""

import errno
import inspect
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
from .analyse import analysiere_pdf
from .muster import KATEGORIEN
from .namen import lade_ner
from .schwaerzung import schwaerze_pdf

try:
    from .ocr import OcrDienst
except ImportError:                      # ältere ocr.py ohne Prozess-Dienst
    OcrDienst = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_VERFUEGBAR = True
except ImportError:
    DND_FILES = TkinterDnD = None
    DND_VERFUEGBAR = False


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
UNTERTITEL_MINDESTHOEHE = 700       # bei 100 %; darunter wird der Untertitel ausgeblendet
OBEN_MINDESTHOEHE = 90              # bei 100 %, Mindesthöhe des scrollbaren Einstellbereichs
PROTOKOLL_ZEILEN = 5
PROTOKOLL_ZEILEN_KLEIN = 4
PROTOKOLL_MAX_ZEILEN = 5000

HAKEN = {"an": "☑", "aus": "☐", "teil": "⊟"}
SPALTEN = ("kategorie", "text", "seiten", "anzahl", "kontext", "ersatz")
# Spalte -> (Breite, Mindestbreite, dehnbar) bei 100 %
SPALTEN_MASSE = {"#0": (200, 150, False), "kategorie": (130, 105, False), "text": (170, 130, True),
                 "seiten": (60, 52, False), "anzahl": (55, 48, False), "kontext": (180, 140, True),
                 "ersatz": (95, 85, False)}
ANALYSE_TEXT = "  Analysieren – Funde anzeigen  "
START_TEXT = "  Schwärzen starten  "

UNTERTITEL = ("Ersetzt direkte Identifikatoren (Namen, IBAN, Adresse, Telefon …) durch Platzhalter wie "
              "[PERSON A] – eine Pseudonymisierung, keine vollständige Anonymisierung: Diagnosen, Beruf, "
              "Arbeitgeber, Beträge und Orte bleiben lesbar. Fundliste und Ergebnis müssen vor jeder "
              "Weitergabe geprüft werden.")
HINWEISKASTEN = ("Nicht erkannt werden: Diagnosen, Beruf, Arbeitgeber, Unterschriften, Bilder, Handschrift, "
                 "Freitext. Ausgaben in Cloud-Ordnern (OneDrive, Dropbox …) werden mitsynchronisiert. "
                 "Mehr: Hilfe → „Was wird nicht erkannt?“")
GRENZEN_TEXT = (
    "Das Programm ersetzt direkte Identifikatoren durch Platzhalter (Pseudonymisierung).\n\n"
    "NICHT erkannt werden:\n"
    "  • Diagnosen, Krankheiten, ICD-Codes, Medikamente\n"
    "  • Beruf, Arbeitgeber, Einkommen, Familienstand\n"
    "  • Unterschriften, Stempel, Handschrift\n"
    "  • Text in Bildern und Fotos, Logos (nur ganzseitige Scans werden per OCR gelesen)\n"
    "  • Freitext, aus dem eine Person erkennbar bleibt\n"
    "  • Dateinamen (die Ausgabe heißt neutral anonym_01.pdf; der Originalname steht in _zuordnung.txt)\n\n"
    "Pseudonymisierte Dokumente bleiben personenbezogene Daten. Für die Weitergabe an einen KI-Dienst "
    "braucht es weiterhin eine Rechtsgrundlage und in der Regel einen Auftragsverarbeitungsvertrag.\n\n"
    "Ausgaben in Ordnern, die mit OneDrive, Dropbox o. Ä. synchronisiert werden, landen ebenfalls in der "
    "Cloud. Per Dateidialog geöffnete Dateien merkt sich Windows unter „Zuletzt verwendet“."
)


# ----------------------------------------------------------------------
# Hilfsfunktionen (ohne Oberfläche)
# ----------------------------------------------------------------------
def _rufe(funktion, *args, **kwargs):
    """Ruft eine Engine-Funktion auf und lässt Schlüsselwort-Argumente weg, die sie nicht kennt."""
    try:
        parameter = inspect.signature(funktion).parameters
    except (TypeError, ValueError):
        return funktion(*args, **kwargs)
    if any(p.kind is p.VAR_KEYWORD for p in parameter.values()):
        return funktion(*args, **kwargs)
    return funktion(*args, **{k: v for k, v in kwargs.items() if k in parameter})


def _unterstuetzt(funktion, name) -> bool:
    try:
        parameter = inspect.signature(funktion).parameters
    except (TypeError, ValueError):
        return True
    return name in parameter or any(p.kind is p.VAR_KEYWORD for p in parameter.values())


def _analyse_ergebnis_vervollstaendigen(ergebnis, pdf: Path) -> dict:
    """Füllt fehlende Schlüssel auf (Vertragsform), damit die Oberfläche mit jeder Engine-Version arbeitet."""
    e = dict(ergebnis or {})
    e.setdefault("datei", pdf)
    e.setdefault("funde", [])
    e.setdefault("warnungen", [])
    e.setdefault("hinweise", [])
    e.setdefault("fehler", None)
    e.setdefault("seiten", 0)
    e.setdefault("ocr_seiten", 0)
    e.setdefault("ocr_cache", {})
    funde = []
    for fund in e["funde"] or []:
        f = dict(fund)
        f.setdefault("kategorie", "")
        f.setdefault("text", "")
        f.setdefault("ersatz", "")
        f.setdefault("anzeige", "IMMER-Begriff" if f["kategorie"] == "begriff" else (f["kategorie"] or "?"))
        f.setdefault("seiten", [])
        f.setdefault("anzahl", 1)
        f.setdefault("kontext", "")
        funde.append(f)
    e["funde"] = funde
    e["warnungen"] = [str(w) for w in (e["warnungen"] or [])]
    e["hinweise"] = [str(h) for h in (e["hinweise"] or [])]
    return e


def _schwaerz_ergebnis_vervollstaendigen(ergebnis, pdf: Path) -> dict:
    e = dict(ergebnis or {})
    e.setdefault("original", pdf)
    e.setdefault("ausgabe", None)
    e.setdefault("treffer", 0)
    e.setdefault("uebersprungen", 0)
    e.setdefault("warnungen", [])
    e.setdefault("hinweise", [])
    e.setdefault("reste", [])
    e.setdefault("fehler", None)
    if e["ausgabe"] is not None:
        e["ausgabe"] = Path(e["ausgabe"])
    e["warnungen"] = [str(w) for w in (e["warnungen"] or [])]
    e["hinweise"] = [str(h) for h in (e["hinweise"] or [])]
    e["reste"] = [str(r) for r in (e["reste"] or [])]
    return e


def _verstaendliche_fehlermeldung(fehler: BaseException, pfad: Path | None = None) -> str:
    """Übersetzt typische Schreib-/Zugriffsfehler in eine Handlungsanweisung."""
    text = str(fehler)
    tl = text.lower()
    if (isinstance(fehler, PermissionError) or "permission denied" in tl or "cannot remove file" in tl
            or "zugriff verweigert" in tl or "used by another process" in tl or "errno 13" in tl
            or "cannot open" in tl and "output" in tl):
        return ("Ausgabedatei konnte nicht geschrieben werden – vermutlich ist sie in einem anderen Programm "
                "(PDF-Reader) geöffnet oder der Ordner ist schreibgeschützt. Bitte die Datei schließen oder "
                "einen anderen Zielordner wählen und erneut schwärzen.")
    if isinstance(fehler, (FileExistsError, NotADirectoryError)) or "file exists" in tl or "not a directory" in tl:
        return ("Im Zielordner liegt bereits eine Datei namens „anonymisiert“ – bitte umbenennen oder "
                "einen anderen Zielordner wählen.")
    if (isinstance(fehler, OSError) and getattr(fehler, "errno", None) == errno.ENOSPC) or "no space left" in tl:
        return "Kein Speicherplatz mehr auf dem Laufwerk – bitte Platz schaffen oder anderen Zielordner wählen."
    if "winerror 206" in tl or "winerror 3" in tl or (pfad is not None and sys.platform == "win32"
                                                        and len(str(pfad)) > 240):
        return ("Der Dateipfad ist zu lang für Windows – bitte den Ordner näher an C:\\ kopieren "
                "oder einen kurzen Zielordner wählen.")
    return f"Unerwarteter Fehler ({type(fehler).__name__}: {text[:200]}) – Details stehen in fehler.log."


def _seitenzahl(pdf: Path) -> int:
    """Seitenzahl für den Fortschrittsbalken (1, wenn das PDF nicht lesbar ist)."""
    try:
        with fitz.open(pdf) as doc:
            return max(1, len(doc))
    except Exception:
        return 1


# ----------------------------------------------------------------------
# Hauptfenster
# ----------------------------------------------------------------------
class AnonymisiererApp:
    """Hauptfenster: Dateien wählen, analysieren, Funde prüfen, schwärzen."""

    def __init__(self, root, einstellungen: dict | None = None):
        self.root = root
        self.einstellungen = dict(einstellungen) if einstellungen is not None else dateien.einstellungen_laden()
        self.root.title(f"PDF-Anonymisierer {__version__}")
        self.root.configure(bg=FARBE_HINTERGRUND)

        self.dateien: list[Path] = []
        self.analyse_ergebnisse: dict[Path, dict] = {}   # Pfad -> Ergebnis von analysiere_pdf
        self.zeilen: dict[str, Path] = {}                # iid der Datei-Zeile -> Pfad
        self.beschriftungen: dict[str, str] = {}         # iid -> Anzeigename (relativ zum Stamm)
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
        self._hauptthread_fehler_gemeldet = False
        self._anpassung_laeuft = False
        self.dnd_aktiv = False
        self._sperrbar: list = []
        self._einstellungen_werden_gesetzt = False
        self._anpassung_geplant = False

        self.skalierung = float(self.root.tk.call("tk", "scaling"))
        self.k = self.skalierung / BASIS_SKALIERUNG     # 1.0 = Windows 100 %
        self._schriften_anlegen()
        self._geometrie_setzen()
        self._baue_oberflaeche()
        self._menue_anlegen()
        self._einstellungen_anwenden()

        self.root.protocol("WM_DELETE_WINDOW", self.schliessen)
        self.root.report_callback_exception = self._fehler_melden
        threading.excepthook = self._thread_excepthook
        self.root.bind("<Configure>", self._fenster_geaendert)
        self.root.bind("<Alt-a>", lambda e: self.analyse_knopf.invoke())
        self.root.bind("<Alt-s>", lambda e: self.start_knopf.invoke())
        self.root.after_idle(self._oben_anpassen)

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
        leiste = tk.Frame(eltern, bg=FARBE_KARTE, padx=12, pady=8,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        leiste.pack(side="bottom", fill="x", pady=(6, 0))
        self.aktionsleiste = leiste
        self.start_knopf = self._knopf(leiste, START_TEXT, self.schwaerzen)
        self.start_knopf.pack(side="left")
        self.start_knopf.config(state="disabled")
        self.abbrechen_knopf = self._knopf(leiste, "Abbrechen", self.abbrechen, True)
        self.abbrechen_knopf.pack(side="left", padx=(8, 0))
        self.abbrechen_knopf.config(state="disabled")
        self.ordner_knopf = self._knopf(leiste, "Ergebnisordner öffnen", self.ergebnisordner_oeffnen, True)
        self.ordner_knopf.pack(side="left", padx=(8, 0))
        self.ordner_knopf.config(state="disabled")
        self.warn_label = tk.Label(leiste, text="", font=self.f_fett, bg=FARBE_KARTE, fg=FARBE_WARNUNG)
        self.warn_label.pack(side="right", padx=(8, 0))
        mitte = tk.Frame(leiste, bg=FARBE_KARTE)
        mitte.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.fortschritt = ttk.Progressbar(mitte, mode="determinate")
        self.fortschritt.pack(fill="x")
        self.status_label = tk.Label(mitte, text="Bereit.", font=self.f_normal, bg=FARBE_KARTE,
                                     fg=FARBE_TEXT_GRAU, anchor="w")
        self.status_label.pack(fill="x")

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
                                  height=2, cursor="hand2", highlightthickness=2, highlightbackground="#b9cfee")
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

    def _baue_karte_kategorien(self, eltern):
        karte2 = tk.Frame(eltern, bg=FARBE_KARTE, padx=14, pady=8,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        karte2.pack(fill="x", pady=(0, 8))
        titelzeile = tk.Frame(karte2, bg=FARBE_KARTE)
        titelzeile.pack(fill="x", pady=(0, 2))
        tk.Label(titelzeile, text="2 · Was soll erkannt werden?", font=self.f_karte,
                 bg=FARBE_KARTE, fg=FARBE_TEXT).pack(side="left")
        self.analyse_knopf = self._knopf(titelzeile, ANALYSE_TEXT, self.analysieren)
        self.analyse_knopf.pack(side="right")
        gitter = tk.Frame(karte2, bg=FARBE_KARTE)
        gitter.pack(fill="x")
        self.kategorie_vars: dict[str, tk.BooleanVar] = {}
        for i, (schluessel, anzeige, _, _, standard) in enumerate(KATEGORIEN):
            var = tk.BooleanVar(value=standard)
            self.kategorie_vars[schluessel] = var
            cb = tk.Checkbutton(gitter, text=anzeige, variable=var, font=self.f_normal,
                                bg=FARBE_KARTE, activebackground=FARBE_KARTE, anchor="w")
            cb.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 12))
            self._sperrbar.append(cb)
            var.trace_add("write", self._einstellung_geaendert)
        for spalte in range(3):
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
        self._sperrbar += [b1, b2, self.entfernen_knopf]
        tk.Label(karte3, text="Klick auf das Kästchen (oder Leertaste) = Fund an/aus. Nur angehakte Funde "
                              "werden ersetzt. Rechtsklick: alle Funde einer Datei oder Kategorie an/aus.",
                 font=self.f_normal, bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU, anchor="w").pack(anchor="w", fill="x")

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
        hilfe = tk.Menu(menue, tearoff=0)
        hilfe.add_command(label="Was wird nicht erkannt?", command=self.hilfe_grenzen)
        hilfe.add_command(label="Ordner des Fehlerprotokolls öffnen", command=self.fehlerlog_oeffnen)
        hilfe.add_separator()
        hilfe.add_command(label="Über PDF-Anonymisierer …", command=self.hilfe_ueber)
        menue.add_cascade(label="Hilfe", menu=hilfe)
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
            zeilen = PROTOKOLL_ZEILEN_KLEIN if klein else PROTOKOLL_ZEILEN
            if int(self.protokoll.cget("height")) != zeilen:
                self.protokoll.config(height=zeilen)
                self.protokoll_rahmen.update_idletasks()
            karte3_rand = max(0, self.karte3.winfo_reqheight() - self.baum_rahmen.winfo_reqheight())
            fest = (self.kopf.winfo_reqheight() + self.aktionsleiste.winfo_reqheight()
                    + self.protokoll_rahmen.winfo_reqheight() + karte3_rand + self._px(44))
            verfuegbar = fenster_h - fest - self._px(BAUM_MINDESTHOEHE)
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
        pfade = re.findall(r"\{([^}]*)\}|(\S+)", ereignis.data)
        self._pdfs_hinzufuegen([a or b for a, b in pfade])

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

        teile = [f"{neu} PDF-Datei(en) hinzugefügt" if neu else "Keine neue PDF-Datei"]
        if bericht["uebersprungen"]:
            namen = ", ".join(p.name for p in bericht["uebersprungen"][:5])
            teile.append(f"{len(bericht['uebersprungen'])} übersprungen – keine PDF")
            self._log(f"⚠ Übersprungen (keine PDF-Datei; Fotos, Mails oder Office-Dateien bitte zuerst als "
                      f"PDF speichern): {namen}", "warnung")
        if bericht["ausgaben"]:
            teile.append(f"{len(bericht['ausgaben'])} bereits anonymisierte Datei(en) ausgelassen")
            self._log(f"ℹ {len(bericht['ausgaben'])} Datei(en) im Ordner sind bereits Ausgaben des Programms "
                      f"und wurden ausgelassen.", "hinweis")
        if bericht["leere_ordner"]:
            namen = ", ".join(str(p) for p in bericht["leere_ordner"][:3])
            teile.append("Ordner ohne PDF-Dateien")
            self._log(f"⚠ Ordner enthält keine PDF-Dateien: {namen}", "warnung")
        if bericht["fehlend"]:
            teile.append(f"{len(bericht['fehlend'])} nicht gefunden")
            self._log("⚠ Nicht gefunden: " + ", ".join(str(p) for p in bericht["fehlend"][:3]), "warnung")
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
            self._status(f"{len(self.dateien)} Datei(en) ausgewählt – jetzt analysieren (Schritt 2).")

    def liste_leeren(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
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
        self.analyse_ergebnisse.pop(pdf, None)
        if self.baum.exists(iid):
            self.baum.delete(iid)
        self._beschriftungen_aktualisieren()
        self.datei_hinweis.config(text=f"„{pdf.name}“ entfernt · insgesamt {len(self.dateien)} Datei(en).")
        self._status_dateien()
        self._start_knopf_aktualisieren()

    # ------------------------------------------------------------------
    # Baum (Dateien und Funde)
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
            an = sum(1 for k in kinder if self._zustand(k) == "an")
            zustand = "an" if an == len(kinder) else ("aus" if an == 0 else "teil")
        self._zustand_setzen(eltern, zustand)

    def _baum_datei_fuellen(self, pdf: Path, ergebnis: dict):
        """Trägt die Funde einer Datei ein (Kind-iid = „<pfad>::<index>“)."""
        iid = self._datei_zeile_einfuegen(pdf)
        self.baum.delete(*self.baum.get_children(iid))
        funde = ergebnis["funde"]
        for index, fund in enumerate(funde):
            seiten = fund.get("seiten") or []
            seiten_text = ", ".join(str(s) for s in seiten[:6]) + (" …" if len(seiten) > 6 else "")
            self.baum.insert(iid, "end", iid=f"{iid}::{index}", text=HAKEN["an"],
                             values=(fund["anzeige"], fund["text"], seiten_text, fund.get("anzahl", 1),
                                     fund.get("kontext", ""), fund["ersatz"]),
                             tags=("fund", "an"))
        if ergebnis["fehler"]:
            status = f"Fehler: {ergebnis['fehler']}"
        elif not funde and any("Kein Text" in w or "kaum lesbar" in w for w in ergebnis["warnungen"]):
            status = "0 Funde – kein Text lesbar!"
        else:
            status = f"{len(funde)} Fund(e)"
        if ergebnis["warnungen"]:
            status += f" · {len(ergebnis['warnungen'])} Warnung(en)"
        self.baum.set(iid, "kategorie", status)
        self.baum.set(iid, "seiten", str(ergebnis["seiten"]) if ergebnis["seiten"] else "")
        self.baum.set(iid, "anzahl", str(sum(f.get("anzahl", 1) for f in funde)) if funde else "")
        self._eltern_ableiten(iid)

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
            for kind in self.baum.get_children(zeile):
                self._zustand_setzen(kind, neu)
            self._eltern_ableiten(zeile)
        else:
            neu = "aus" if self._zustand(zeile) == "an" else "an"
            self._zustand_setzen(zeile, neu)
            self._eltern_ableiten(self.baum.parent(zeile))
        self._start_knopf_aktualisieren()

    def _datei_setzen(self, iid, zustand):
        if self.laeuft or not self.baum.exists(iid):
            return
        for kind in self.baum.get_children(iid):
            self._zustand_setzen(kind, zustand)
        self._eltern_ableiten(iid)
        self._start_knopf_aktualisieren()

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
            for kind in self.baum.get_children(iid):
                if self.baum.set(kind, "kategorie") == anzeige:
                    self._zustand_setzen(kind, zustand)
            self._eltern_ableiten(iid)
        self._start_knopf_aktualisieren()

    def _kontextmenue(self, ereignis):
        zeile = self.baum.identify_row(ereignis.y)
        menue = tk.Menu(self.root, tearoff=0)
        if zeile:
            self.baum.selection_set(zeile)
            self.baum.focus(zeile)
            datei = zeile if zeile in self.zeilen else self.baum.parent(zeile)
            name = self.beschriftungen.get(datei, "")
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
        """Vollständiger Pfad der gewählten Datei in der Statuszeile (nur wenn kein Lauf aktiv ist)."""
        if self.laeuft:
            return
        auswahl = self.baum.selection()
        if not auswahl:
            return
        iid = auswahl[0] if auswahl[0] in self.zeilen else self.baum.parent(auswahl[0])
        pdf = self.zeilen.get(iid)
        if pdf is not None:
            self.status_label.config(text=f"Datei: {pdf}")

    def _angehakte_funde(self) -> int:
        return sum(1 for e in self.baum.get_children("") for k in self.baum.get_children(e)
                   if self._zustand(k) == "an")

    def _start_knopf_aktualisieren(self):
        aktiv = not self.laeuft and not self.analyse_veraltet and self._angehakte_funde() > 0
        self.start_knopf.config(state="normal" if aktiv else "disabled")

    # ------------------------------------------------------------------
    # Einstellungen
    # ------------------------------------------------------------------
    @staticmethod
    def _zeilen_aus(feld) -> list[str]:
        return [z.strip() for z in feld.get("1.0", "end").splitlines() if z.strip()]

    def _einstellungen_anwenden(self):
        e = self.einstellungen
        self._einstellungen_werden_gesetzt = True
        try:
            kategorien = e.get("kategorien")
            if isinstance(kategorien, dict):
                for schluessel, var in self.kategorie_vars.items():
                    if schluessel in kategorien:
                        var.set(bool(kategorien[schluessel]))
            for feld, schluessel in ((self.immer_feld, "immer"), (self.nie_feld, "nie")):
                werte = e.get(schluessel)
                if isinstance(werte, list):
                    feld.delete("1.0", "end")
                    feld.insert("1.0", "\n".join(str(w) for w in werte))
                feld.edit_modified(False)
            if isinstance(e.get("zielordner"), str):
                self.zielordner_var.set(e["zielordner"])
            self.zielordner_aktiv.set(bool(e.get("zielordner_aktiv", False)))
        finally:
            self._einstellungen_werden_gesetzt = False

    def _einstellungen_sammeln(self) -> dict:
        daten = dict(self.einstellungen)
        daten.update({
            "version": __version__,
            "kategorien": {k: bool(v.get()) for k, v in self.kategorie_vars.items()},
            "immer": self._zeilen_aus(self.immer_feld),
            "nie": self._zeilen_aus(self.nie_feld),
            "zielordner": self.zielordner_var.get().strip(),
            "zielordner_aktiv": bool(self.zielordner_aktiv.get()),
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
            self._log("⚠ Einstellungen konnten nicht gespeichert werden (Ordner nicht beschreibbar).", "warnung")

    def _text_geaendert(self, ereignis):
        feld = ereignis.widget
        if feld.edit_modified():
            feld.edit_modified(False)
            self._einstellung_geaendert()

    def _einstellung_geaendert(self, *_):
        """Kategorie oder Liste geändert: eine vorhandene Analyse passt nicht mehr -> zurücksetzen."""
        if self._einstellungen_werden_gesetzt or self.laeuft or not self.analyse_ergebnisse:
            return
        self.analyse_veraltet = True
        self.analyse_ergebnisse.clear()
        for iid in self.zeilen:
            if self.baum.exists(iid):
                self.baum.delete(*self.baum.get_children(iid))
                self.baum.set(iid, "kategorie", "erneut analysieren")
                self.baum.set(iid, "anzahl", "")
                self._zustand_setzen(iid, "aus")
        self._start_knopf_aktualisieren()
        self._status("Einstellungen geändert – bitte erneut analysieren.")
        self._log("ℹ Kategorien oder Listen wurden geändert – die Fundliste wurde zurückgesetzt. "
                  "Bitte erneut analysieren.", "hinweis")

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
        self._trenner(("Analyse" if art == "analyse" else "Schwärzung") + f" {datetime.now():%d.%m.%Y %H:%M:%S}")

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
        if OcrDienst is None:
            return None
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
        self._log("Abbruch angefordert …", "warnung")

    def _laeuft_hinweis(self):
        self._dialog("info", "Lauf läuft noch",
                     "Gerade läuft noch eine Analyse oder Schwärzung. Bitte warten oder „Abbrechen“ drücken.")

    def schliessen(self):
        """Fenster schließen (Rückfrage, solange ein Lauf aktiv ist); Einstellungen sichern."""
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
        self.root.destroy()

    # ------------------------------------------------------------------
    # Analyse
    # ------------------------------------------------------------------
    def analysieren(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        if not self.dateien:
            self._dialog("warning", "Keine Dateien", "Bitte zuerst PDF-Dateien auswählen (Schritt 1).")
            return
        self.einstellungen_speichern()
        aktive = {k for k, v in self.kategorie_vars.items() if v.get()}
        immer = self._zeilen_aus(self.immer_feld)
        nie = self._zeilen_aus(self.nie_feld)
        pdfs = list(self.dateien)                       # Kopie: der Thread arbeitet nie auf der Live-Liste

        self.analyse_ergebnisse = {}
        self.analyse_veraltet = False
        self.letzte_ausgabeordner = []
        for iid in self.zeilen:
            self.baum.delete(*self.baum.get_children(iid))
            self.baum.set(iid, "kategorie", "wird analysiert …")
            self.baum.set(iid, "anzahl", "")
            self._zustand_setzen(iid, "aus")
        self._lauf_starten("analyse")
        self._status("Analyse startet …")
        threading.Thread(target=self._analyse_lauf, args=(pdfs, aktive, nie, immer, self.abbruch),
                         daemon=True, name="Analyse").start()

    def _analyse_lauf(self, pdfs, aktive, nie, immer, abbruch):
        ergebnisse: dict[Path, dict] = {}
        fehler_intern = None
        ocr = None
        try:
            ocr = self._ocr_dienst_anlegen()
            self.ocr = ocr
            seiten = {pdf: _seitenzahl(pdf) for pdf in pdfs}
            gesamt_seiten = max(1, sum(seiten.values()))
            self._fortschritt_maximum(gesamt_seiten)
            if "namen" in aktive:
                self._status("Lade Namenserkennungs-Modell …")
                self._log("Lade Namenserkennungs-Modell …", "grau")
                try:
                    lade_ner()
                except Exception as fehler:
                    dateien.fehler_protokollieren(*sys.exc_info())
                    self._log(f"✖ Namenserkennung konnte nicht geladen werden ({type(fehler).__name__}: {fehler}) "
                              f"– Namen werden in diesem Lauf NICHT erkannt!", "fehler")
            basis = 0
            for nr, pdf in enumerate(pdfs, 1):
                if abbruch.is_set():
                    break
                name = self._anzeigename(pdf)
                self._status(f"Analyse: Datei {nr}/{len(pdfs)} – {name}")

                def fortschritt(seite, gesamt, _basis=basis, _nr=nr, _pdf=pdf, _name=name):
                    self._fortschritt_setzen(_basis + min(int(seite), seiten[_pdf]))
                    self._status(f"Analyse: Datei {_nr}/{len(pdfs)}, Seite {seite}/{gesamt} – {_name}")

                ergebnis = _rufe(analysiere_pdf, pdf, aktive, nie, immer,
                                 melde=lambda t: self._log(t, "grau"), fortschritt=fortschritt,
                                 abbruch=abbruch, ocr=ocr)
                ergebnis = _analyse_ergebnis_vervollstaendigen(ergebnis, pdf)
                ergebnisse[pdf] = ergebnis
                if ergebnis["fehler"]:
                    self._log(f"✖ {name}: {ergebnis['fehler']}", "fehler")
                for w in ergebnis["warnungen"]:
                    self._log(f"⚠ {name}: {w}", "warnung")
                for h in ergebnis["hinweise"]:
                    self._log(f"ℹ {name}: {h}", "hinweis")
                zusatz = f", {ergebnis['seiten']} Seite(n)" if ergebnis["seiten"] else ""
                if ergebnis["ocr_seiten"]:
                    zusatz += f", davon {ergebnis['ocr_seiten']} per OCR"
                self._log(f"{name}: {len(ergebnis['funde'])} Fund(e){zusatz}", "grau")
                self.root.after(0, self._baum_datei_fuellen, pdf, ergebnis)
                basis += seiten[pdf]
                self._fortschritt_setzen(basis)
        except Exception:
            fehler_intern = sys.exc_info()
        finally:
            self._ocr_schliessen(ocr)
            self._im_hauptthread(self._analyse_fertig, pdfs, ergebnisse, abbruch.is_set(), fehler_intern)

    def _analyse_fertig(self, pdfs, ergebnisse, abgebrochen, fehler_intern):
        self.analyse_ergebnisse.update(ergebnisse)
        for pdf in pdfs:
            if pdf not in ergebnisse and str(pdf) in self.zeilen and self.baum.exists(str(pdf)):
                self.baum.set(str(pdf), "kategorie", "nicht analysiert (abgebrochen)")
        self._lauf_beenden()
        if fehler_intern:
            self._fehler_melden(*fehler_intern)
        if abgebrochen:
            self.analyse_veraltet = True
            self._start_knopf_aktualisieren()
            self._log("Analyse abgebrochen – Fundliste unvollständig. Bitte erneut analysieren.", "fehler")
            self._status("Analyse abgebrochen – bitte erneut analysieren.")
            return

        gesamt = sum(len(e["funde"]) for e in ergebnisse.values())
        ohne_text = [pdf for pdf, e in ergebnisse.items() if not e["funde"]
                     and any("Kein Text" in w or "kaum lesbar" in w for w in e["warnungen"])]
        mit_fehler = [(pdf, e["fehler"]) for pdf, e in ergebnisse.items() if e["fehler"]]
        mit_warnung = [(pdf, e["warnungen"]) for pdf, e in ergebnisse.items() if e["warnungen"]]

        if gesamt:
            self._log(f"Analyse fertig: {gesamt} Fund(e) in {len(ergebnisse)} Datei(en). "
                      f"Bitte Liste prüfen, dann schwärzen.", "ok")
            self._status(f"{gesamt} Fund(e) in {len(ergebnisse)} Datei(en) – Liste prüfen, dann schwärzen.")
        else:
            self._log(f"Analyse fertig: 0 Funde in {len(ergebnisse)} Datei(en) – es gibt nichts zu schwärzen, "
                      f"es wird keine Ausgabedatei erzeugt.", "warnung" if ohne_text else "ok")
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
                              "Bitte das Dokument selbst durchsehen.")
        if mit_fehler:
            art = "warning"
            zeilen.append("")
            zeilen.append("Nicht analysierbar:")
            zeilen += [f"  • {self._anzeigename(p)}: {f}" for p, f in mit_fehler[:10]]
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
                         f"Der Zielordner kann nicht angelegt werden:\n{ziel}\n\n{fehler}")
            return False, None
        return True, ziel

    def schwaerzen(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        if self.analyse_veraltet:
            self._dialog("info", "Erneut analysieren",
                         "Kategorien, Listen oder Dateien wurden seit der letzten Analyse geändert. "
                         "Bitte zuerst erneut analysieren.")
            return
        nicht_analysiert = [p for p in self.dateien if p not in self.analyse_ergebnisse]
        if nicht_analysiert:
            self._dialog("info", "Erst analysieren",
                         f"{len(nicht_analysiert)} Datei(en) sind noch nicht analysiert "
                         f"(z. B. {nicht_analysiert[0].name}). Bitte zuerst „Analysieren“ drücken.")
            return
        auftraege = []   # (pdf, [funde], ocr_cache)
        for iid in self.baum.get_children(""):
            pdf = self.zeilen.get(iid)
            ergebnis = self.analyse_ergebnisse.get(pdf) if pdf is not None else None
            if not ergebnis:
                continue
            funde = ergebnis["funde"]
            gewaehlt = []
            for kind in self.baum.get_children(iid):
                if self._zustand(kind) != "an":
                    continue
                try:
                    index = int(kind.rsplit("::", 1)[1])
                except (IndexError, ValueError):
                    continue
                if 0 <= index < len(funde):
                    gewaehlt.append(funde[index])
            if gewaehlt:
                auftraege.append((pdf, gewaehlt, ergebnis.get("ocr_cache")))
        if not auftraege:
            self._dialog("warning", "Nichts ausgewählt", "Es ist kein Fund angehakt – es gibt nichts zu schwärzen.")
            return
        ok, ziel_ordner = self._zielordner()
        if not ok:
            return
        self.einstellungen_speichern()
        self.letzte_ausgabeordner = []
        self._lauf_starten("schwaerzen")
        self._status("Schwärzung startet …")
        threading.Thread(target=self._schwaerz_lauf, args=(auftraege, ziel_ordner, self.abbruch),
                         daemon=True, name="Schwaerzung").start()

    def _schwaerz_lauf(self, auftraege, ziel_ordner, abbruch):
        ergebnisse: list[tuple[Path, dict]] = []
        fehler_intern = None
        ocr = None
        try:
            ocr = self._ocr_dienst_anlegen()
            self.ocr = ocr
            seiten = {pdf: _seitenzahl(pdf) for pdf, _, _ in auftraege}
            self._fortschritt_maximum(max(1, sum(seiten.values())))
            if ziel_ordner is not None and not _unterstuetzt(schwaerze_pdf, "ziel_ordner"):
                self._log("⚠ Diese Programmversion kennt keinen gemeinsamen Zielordner – die Ausgaben landen "
                          "im Unterordner „anonymisiert“ neben den Originalen.", "warnung")
            basis = 0
            for nr, (pdf, funde, cache) in enumerate(auftraege, 1):
                if abbruch.is_set():
                    break
                name = self._anzeigename(pdf)
                self._status(f"Schwärzung: Datei {nr}/{len(auftraege)} – {name}")

                def fortschritt(seite, gesamt, _basis=basis, _nr=nr, _pdf=pdf, _name=name):
                    self._fortschritt_setzen(_basis + min(int(seite), seiten[_pdf]))
                    self._status(f"Schwärzung: Datei {_nr}/{len(auftraege)}, Seite {seite}/{gesamt} – {_name}")

                try:
                    ergebnis = _rufe(schwaerze_pdf, pdf, funde, melde=lambda t: self._log(t, "grau"),
                                     fortschritt=fortschritt, abbruch=abbruch, ocr=ocr,
                                     ocr_cache=cache, ziel_ordner=ziel_ordner)
                    ergebnis = _schwaerz_ergebnis_vervollstaendigen(ergebnis, pdf)
                except Exception as fehler:
                    dateien.fehler_protokollieren(*sys.exc_info())
                    ergebnis = _schwaerz_ergebnis_vervollstaendigen(
                        {"fehler": _verstaendliche_fehlermeldung(fehler, pdf)}, pdf)
                if (ergebnis["treffer"] == 0 and not ergebnis["fehler"] and ergebnis["ausgabe"] is None
                        and not any("lokalisiert" in w for w in ergebnis["warnungen"])):
                    ergebnis["warnungen"].append("Kein angehakter Fund konnte im Dokument lokalisiert werden "
                                                 "– keine Ausgabedatei erzeugt.")
                ergebnisse.append((pdf, ergebnis))
                if ergebnis["fehler"]:
                    self._log(f"✖ {name}: {ergebnis['fehler']}", "fehler")
                elif ergebnis["ausgabe"] is not None:
                    self._log(f"✔ {name}  →  {ergebnis['ausgabe']}  ({ergebnis['treffer']} Stelle(n) ersetzt)", "ok")
                else:
                    self._log(f"⚠ {name}: keine Ausgabedatei erzeugt.", "warnung")
                for w in ergebnis["warnungen"]:
                    self._log(f"⚠ {name}: {w}", "warnung")
                for h in ergebnis["hinweise"]:
                    self._log(f"ℹ {name}: {h}", "hinweis")
                if ergebnis["reste"] and not any("auffindbar" in w for w in ergebnis["warnungen"]):
                    self._log(f"⚠ {name}: noch auffindbar: {', '.join(ergebnis['reste'][:5])} – Ausgabe prüfen!",
                              "warnung")
                basis += seiten[pdf]
                self._fortschritt_setzen(basis)
        except Exception:
            fehler_intern = sys.exc_info()
        finally:
            self._ocr_schliessen(ocr)
            self._im_hauptthread(self._schwaerzen_fertig, auftraege, ergebnisse, abbruch.is_set(), fehler_intern)

    def _schwaerzen_fertig(self, auftraege, ergebnisse, abgebrochen, fehler_intern):
        geschrieben = [(pdf, e) for pdf, e in ergebnisse
                       if e["ausgabe"] is not None and Path(e["ausgabe"]).exists()]
        ohne_ausgabe = [(pdf, e) for pdf, e in ergebnisse
                        if not (e["ausgabe"] is not None and Path(e["ausgabe"]).exists())]
        verarbeitet = {pdf for pdf, _ in ergebnisse}
        nicht_verarbeitet = [pdf for pdf, _, _ in auftraege if pdf not in verarbeitet]
        pruefen = [e["ausgabe"] for _, e in geschrieben if "_PRUEFEN" in e["ausgabe"].name.upper() or e["reste"]]
        ordner: list[Path] = []
        for _, e in geschrieben:
            if e["ausgabe"].parent not in ordner:
                ordner.append(e["ausgabe"].parent)
        self.letzte_ausgabeordner = ordner
        stellen = sum(e["treffer"] for _, e in geschrieben)
        self._lauf_beenden()
        if fehler_intern:
            self._fehler_melden(*fehler_intern)

        alles_gut = not ohne_ausgabe and not nicht_verarbeitet and not pruefen and not abgebrochen
        if abgebrochen:
            self._log("Schwärzung abgebrochen.", "fehler")
        self._log(f"Fertig: {len(geschrieben)} von {len(auftraege)} Datei(en) geschrieben, "
                  f"{stellen} Stelle(n) ersetzt.", "ok" if alles_gut else "warnung")
        for o in ordner:
            self._log(f"Ausgabeordner: {o}", "ok")
            if dateien.ist_cloud_ordner(o):
                self._log("ℹ Dieser Ordner wird von einem Cloud-Dienst synchronisiert – die Ausgabe landet "
                          "ebenfalls in der Cloud.", "hinweis")
        if pruefen:
            self._log(f"⚠ {len(pruefen)} Ausgabedatei(en) enthalten noch auffindbare Fundtexte (Name endet "
                      f"auf _PRUEFEN) – unbedingt prüfen!", "warnung")
        self._log("Bitte jede Ausgabedatei öffnen und prüfen, bevor sie an einen KI-Dienst geht – "
                  "das Programm pseudonymisiert nur direkte Identifikatoren.", "hinweis")
        self._status(f"Fertig: {len(geschrieben)} von {len(auftraege)} Datei(en) geschrieben, "
                     f"{stellen} Stelle(n) ersetzt." + ("" if alles_gut else " Bitte Hinweise beachten."))

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
            zeilen.append("Noch auffindbare Fundtexte – diese Dateien unbedingt prüfen (_PRUEFEN):")
            zeilen += [f"  • {p.name}" for p in pruefen[:10]]
        if self.warnungen_anzahl:
            zeilen.append("")
            zeilen.append(f"{self.warnungen_anzahl} Warnung(en)/Fehler – Details stehen im Protokoll.")
        if ordner:
            zeilen.append("")
            zeilen.append("Ausgabeordner:" if len(ordner) > 1 else "Ausgabeordner:")
            zeilen += [f"  {o}" for o in ordner[:5]]
        zeilen.append("")
        zeilen.append("Bitte jede Ausgabedatei vor der Weitergabe öffnen und prüfen.")
        art = "info" if alles_gut and not self.warnungen_anzahl else "warning"
        self._abschluss_dialog(art, "Schwärzung abgeschlossen", "\n".join(zeilen), ordner)

    def _abschluss_dialog(self, art, titel, text, ordner):
        self.letzter_dialog = (art, titel, text)
        if ordner:
            antwort = messagebox.askyesno(titel, text + "\n\nErgebnisordner jetzt öffnen?",
                                          icon="warning" if art == "warning" else "info", parent=self.root)
            if antwort:
                self.ergebnisordner_oeffnen()
        else:
            self._dialog(art, titel, text)

    def ergebnisordner_oeffnen(self):
        if not self.letzte_ausgabeordner:
            self._dialog("info", "Kein Ergebnis", "Es wurde in dieser Sitzung noch keine Ausgabedatei erzeugt.")
            return
        for o in self.letzte_ausgabeordner[:3]:
            if not dateien.oeffne_ordner(o):
                self._log(f"⚠ Ordner konnte nicht geöffnet werden: {o}", "warnung")

    # ------------------------------------------------------------------
    # Hilfe
    # ------------------------------------------------------------------
    def hilfe_grenzen(self):
        self._dialog("info", "Was wird nicht erkannt?", GRENZEN_TEXT)

    def hilfe_ueber(self):
        self._dialog("info", "Über PDF-Anonymisierer",
                     f"PDF-Anonymisierer {__version__}\n\nPseudonymisiert PDFs lokal auf diesem Rechner "
                     f"(PyMuPDF, spaCy, Tesseract). Es werden keine Daten ins Internet übertragen.\n\n"
                     f"Fehlerprotokoll: {dateien.fehlerlog_pfad()}\nEinstellungen: {dateien.einstellungen_pfad()}")

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
    def _dialog(self, art, titel, text):
        """Zeigt einen Hinweis (nur im Hauptthread aufrufen) und merkt ihn sich für Tests."""
        self.letzter_dialog = (art, titel, text)
        zeiger = {"info": messagebox.showinfo, "warning": messagebox.showwarning,
                  "error": messagebox.showerror}[art]
        try:
            zeiger(titel, text, parent=self.root)
        except tk.TclError:
            pass

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

    def _log(self, text, stil=None):
        if not text:
            return

        def einfuegen():
            if stil in ("warnung", "fehler"):
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


def main(ereignisschleife: bool = True):
    """Startet die Oberfläche; ohne Drag & Drop, wenn die tkdnd-Bibliothek nicht lädt."""
    global DND_VERFUEGBAR
    root = None
    if DND_VERFUEGBAR and TkinterDnD is not None:
        try:
            root = TkinterDnD.Tk()
        except Exception as fehler:          # z. B. tkdnd-DLL fehlt oder vom Virenscanner blockiert
            DND_VERFUEGBAR = False
            dateien.fehler_protokollieren(type(fehler), fehler, fehler.__traceback__)
    if root is None:
        root = tk.Tk()
    app = AnonymisiererApp(root)
    if ereignisschleife:
        root.mainloop()
    return app
