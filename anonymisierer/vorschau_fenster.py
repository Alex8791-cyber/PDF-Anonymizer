"""Vorschau-Fenster (Vertrag Phase 2, Abschnitt 10): Seitenbild mit allen Fundstellen.

Vor dem Schwärzen („vorher“) zeigt es die geplante Schwärzung: rot = wird geschwärzt, grau gestrichelt =
nicht geschwärzt, blau = manuelle Markierung. Klick auf ein Wort schaltet die Stelle um bzw. schwärzt ein
nicht erkanntes Wort, ein gezogener Rahmen schwärzt einen Bereich (Text und Bildpixel), das Kontextmenü bietet
„überall in diesem Dokument schwärzen“ und „nicht schwärzen“. Hauptliste und Vorschau bleiben gleich, weil
alle Änderungen über die Hauptanwendung laufen.

Nach dem Schwärzen („nachher“) zeigt es die AUSGABE mit den Verdachtsstellen der Restrisiko-Prüfung (orange)
und bietet „Freigeben“, „Nachschwärzen“ und „Verwerfen“.

Seitenbild und Wortpositionen kommen aus der Engine (vorschau.seite_bild/vorschau_daten), sobald es sie gibt
und die Analyse ein Seitenmodell geliefert hat. Ohne Vorschau-Modul (oder wenn es scheitert) nimmt
gui_attrappen das Seitenmodell der Analyse direkt (Seite.woerter/rechtecke, Vertrag Abschnitt 1) – die Vorschau
zeigt dann ebenfalls genau die Stellen der Schwärzung – und nur ohne Seitenmodell eigene PyMuPDF-Wörter.
Die Ausgabe (nachher) wird immer aus dem Speicher gezeichnet, damit sie umbenannt und gelöscht werden kann.
"""

import base64
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import fitz  # PyMuPDF

from . import dateien
from . import gui_attrappen as attrappen

try:
    from . import vorschau as _engine_vorschau
except ImportError:                          # Engine ohne Vorschau-Modul: Attrappe
    _engine_vorschau = None

FARBE_SCHWAERZEN = "#dc2626"
FARBE_AUS = "#6b7280"
FARBE_MANUELL = "#2563eb"
FARBE_VERDACHT = "#ea580c"
FARBE_HINTERGRUND = "#e5e7eb"
FARBE_KARTE = "#ffffff"
FARBE_TEXT_GRAU = "#6b7280"
RAND = 12                     # Pixel um das Seitenbild
ZIEH_SCHWELLE = 6             # Pixel: ab dieser Bewegung ist ein Klick ein Rahmen
MIN_BEREICH_PT = 3.0          # kleinere Rahmen gelten als Klick
ZOOM_STUFEN = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0)
MAX_ZOOM = 5.0

HINWEIS_VORHER = ("Klick auf ein Wort: schwärzen an/aus · Rahmen ziehen: Bereich schwärzen · Rechtsklick: überall "
                  "schwärzen / nicht schwärzen · Bild auf/ab: Seite blättern")
HINWEIS_NACHHER = ("Ausgabe nach dem Schwärzen. Orange = Verdacht der Restrisiko-Prüfung. Markierte Verdachtsstellen "
                   "nachschwärzen – oder, wenn nichts Persönliches mehr zu sehen ist, „Freigeben“.")


def _engine_hat(name: str) -> bool:
    return _engine_vorschau is not None and hasattr(_engine_vorschau, name)


_ENGINE_FEHLER: set[str] = set()


def _engine_fehler(name: str):
    """Fehler im Vorschau-Modul der Engine: einmal je Funktion in fehler.log, die Vorschau macht mit der Attrappe
    weiter (dasselbe Seitenmodell, wenn die Analyse eins geliefert hat) – kein Absturz des Fensters."""
    if name not in _ENGINE_FEHLER:
        _ENGINE_FEHLER.add(name)
        dateien.fehler_protokollieren(*sys.exc_info())


def engine_zwischenspeicher_leeren():
    """Vorbereitete Dokumente im Vorschau-Modul der Engine freigeben (offene Datei-Handles: unter Windows ließe
    sich eine Datei sonst nicht umbenennen oder löschen)."""
    if _engine_hat("zwischenspeicher_leeren"):
        try:
            _engine_vorschau.zwischenspeicher_leeren()
        except Exception:
            _engine_fehler("zwischenspeicher_leeren")


def _vergroessert(rect, rand=1.0) -> fitz.Rect:
    r = fitz.Rect(rect)
    return fitz.Rect(r.x0 - rand, r.y0 - rand, r.x1 + rand, r.y1 + rand)


def _ueberlappt(wort_rect, bereich, anteil=0.3) -> bool:
    w = fitz.Rect(wort_rect)
    schnitt = w & fitz.Rect(bereich)
    flaeche = max(w.get_area(), 1e-6)
    return not schnitt.is_empty and schnitt.get_area() >= anteil * flaeche


def vorher_quelle_engine(app, pdf: Path) -> bool:
    """Seitenbild/Wörter der Engine nur, wenn sie es kann UND die Analyse ein Seitenmodell geliefert hat –
    sonst passen die Offsets nicht zusammen (dann Attrappe für Bild UND Wörter)."""
    ergebnis = app.analyse_ergebnisse.get(pdf)
    return (_engine_hat("vorschau_daten") and _engine_hat("seite_bild") and ergebnis is not None
            and ergebnis.get("modell") is not None)


MODELL_QUELLEN = ("engine", "modell")      # Vorschau-Daten, deren Offsets zum Seitenmodell der Engine gehören


def vorschau_daten_holen(app, pdf: Path, seite_nr0: int) -> dict:
    """vorschau_daten einer Seite mit Herkunft im Schlüssel "quelle": "engine" (Vorschau-Modul der Engine),
    "modell" (Seitenmodell der Analyse über die Attrappe) oder "attrappe" (eigene PyMuPDF-Wörter). Scheitert das
    Vorschau-Modul der Engine, übernimmt die Attrappe – die Herkunft sagt dann ehrlich, woher die Offsets sind."""
    ergebnis = app.analyse_ergebnisse[pdf]
    if vorher_quelle_engine(app, pdf):
        try:
            daten = dict(_engine_vorschau.vorschau_daten(ergebnis, seite_nr0))
            daten["quelle"] = "engine"
            return daten
        except Exception:
            _engine_fehler("vorschau_daten")
    daten = attrappen.vorschau_daten(ergebnis, seite_nr0)
    daten.setdefault("quelle", "attrappe")
    return daten


def offsets_vom_modell(app, pdf: Path, daten: dict | None = None) -> bool:
    """Gehören die Offsets der Vorschau-Wörter zum Seitenmodell der Engine (Vorschau-Modul der Engine oder das
    Seitenmodell aus der Analyse, Vertrag Abschnitte 1 und 8)? Nur dann wird ein angeklicktes Wort eine manuelle
    STELLE (Offsets, die die Schwärzung annimmt) – sonst wird es als Bereich (Rechteck) geschwärzt."""
    if pdf not in app.analyse_ergebnisse:
        return False
    if daten is None:
        daten = vorschau_daten_holen(app, pdf, 0)
    return daten.get("quelle") in MODELL_QUELLEN


def verdacht_zu_markierungen(app, pdf: Path, verdacht) -> list[dict]:
    """Verdacht der Ausgabe -> manuelle Markierung(en) im ORIGINAL („Nachschwärzen“): die Wörter des Originals
    unter den Verdachtsrechtecken als manuelle Stelle (nur mit dem Seitenmodell der Engine, sonst passen die
    Offsets nicht), sonst die Rechtecke selbst als manueller Bereich (Text und Bildpixel)."""
    seite = attrappen.verdacht_feld(verdacht, "seite")
    rechtecke = [fitz.Rect(r) for r in (attrappen.verdacht_feld(verdacht, "rechtecke") or [])]
    text = str(attrappen.verdacht_feld(verdacht, "text", "") or "")
    if seite is None or not rechtecke:
        return []
    daten = vorschau_daten_holen(app, pdf, int(seite)) if app.kann_manuelle_stellen() else None
    if daten is not None and offsets_vom_modell(app, pdf, daten):
        alle = sorted(daten["woerter"], key=lambda w: w[2])
        # Wörter unter dem Verdacht; direkt aufeinander folgende Wörter (kein anderes Wort dazwischen, egal wie
        # viel Leerraum das Seitenmodell zwischen ihnen hat) werden EINE Stelle
        laeufe: list[list] = []
        letzter = None
        for i, w in enumerate(alle):
            if not any(_ueberlappt(w[0], r) for r in rechtecke):
                continue
            if laeufe and letzter == i - 1:
                laeufe[-1].append(w)
            else:
                laeufe.append([w])
            letzter = i
        if laeufe:
            return [{"art": "stelle", "seite": int(seite), "start": lauf[0][2], "ende": lauf[-1][3],
                     "rechtecke": attrappen.rechtecke_zusammenfassen([w[0] for w in lauf]),
                     "text": " ".join(w[1] for w in lauf)} for lauf in laeufe]
    if app.kann_manuelle_bereiche():
        return [{"art": "bereich", "seite": int(seite), "rechtecke": [_vergroessert(r) for r in rechtecke],
                 "text": f"Verdacht: {text}"[:60]}]
    return []


class VorschauFenster:
    """Toplevel mit Seitenbild, Markierungen und (nach dem Schwärzen) Freigabe-Knöpfen."""

    def __init__(self, app, pdf: Path, modus: str = "vorher", seite: int = 0, markieren=None):
        self.app = app
        self.pdf = Path(pdf)
        self.modus = None
        self.seite = 0
        self.seiten = 1
        self.zoom_stufe = 1.0                 # 1.0 = Seite auf Fensterbreite
        self.faktor = 1.0                     # pt -> Pixel des aktuellen Bilds
        self.markiert_fund = markieren
        self.gesperrt = bool(app.laeuft)
        self._bild = None
        self._bild_kennung = None
        self._daten: dict[int, dict] = {}     # Seite -> vorschau_daten (vorher)
        self._masse: dict[str, list] = {}     # Pfad -> Seitenrechtecke
        self._druck = None
        self._letzte_breite = 0
        self._zeichnen_geplant = None
        self.letztes_menue: list = []

        f = self.fenster = tk.Toplevel(app.root)
        f.configure(bg=FARBE_KARTE)
        f.protocol("WM_DELETE_WINDOW", self.schliessen)
        self._geometrie()
        self._baue()
        self.titel_setzen()
        f.bind("<Prior>", lambda e: self.blaettern(-1))
        f.bind("<Next>", lambda e: self.blaettern(1))
        f.bind("<Home>", lambda e: self.zeige_seite(0))
        f.bind("<End>", lambda e: self.zeige_seite(self.seiten - 1))
        f.bind("<plus>", lambda e: self.zoomen(1))
        f.bind("<KP_Add>", lambda e: self.zoomen(1))
        f.bind("<minus>", lambda e: self.zoomen(-1))
        f.bind("<KP_Subtract>", lambda e: self.zoomen(-1))
        f.update_idletasks()
        self.modus_wechseln(modus, seite=seite, markieren=markieren, erzwingen=True)
        self.sperren(self.gesperrt)
        self.nach_vorn()

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _geometrie(self):
        app, f = self.app, self.fenster
        sw, sh = f.winfo_screenwidth(), f.winfo_screenheight()
        breite = min(app._px(900), sw - 40)
        hoehe = min(app._px(1000), sh - app._px(90))
        x = min(max(0, app.root.winfo_rootx() + app._px(60)), max(0, sw - breite - 10))
        y = max(0, min(app.root.winfo_rooty(), sh - hoehe - 40))
        f.geometry(f"{breite}x{hoehe}+{x}+{y}")
        f.minsize(min(480, sw), min(420, sh))

    def _baue(self):
        app, f = self.app, self.fenster
        leiste = tk.Frame(f, bg=FARBE_KARTE, padx=8, pady=6)
        leiste.pack(side="top", fill="x")
        self.zurueck_knopf = app._knopf(leiste, "◀", lambda: self.blaettern(-1), True)
        self.zurueck_knopf.pack(side="left")
        self.seiten_label = tk.Label(leiste, text="Seite 1 / 1", font=app.f_fett, bg=FARBE_KARTE, width=12)
        self.seiten_label.pack(side="left", padx=4)
        self.vor_knopf = app._knopf(leiste, "▶", lambda: self.blaettern(1), True)
        self.vor_knopf.pack(side="left")
        app._knopf(leiste, "Fensterbreite", self.zoom_breite, True).pack(side="left", padx=(14, 0))
        app._knopf(leiste, "−", lambda: self.zoomen(-1), True).pack(side="left", padx=(4, 0))
        app._knopf(leiste, "+", lambda: self.zoomen(1), True).pack(side="left", padx=(4, 0))
        self.ergebnis_knopf = app._knopf(leiste, "Ergebnis (Ausgabe)", lambda: self.modus_wechseln("nachher"), True)
        self.ergebnis_knopf.pack(side="right")
        self.geplant_knopf = app._knopf(leiste, "Geplante Schwärzung", lambda: self.modus_wechseln("vorher"), True)
        self.geplant_knopf.pack(side="right", padx=(0, 6))

        legende = tk.Frame(f, bg=FARBE_KARTE, padx=8)
        legende.pack(side="top", fill="x")
        self.legende = legende
        self.legende_vorher = []
        for text, farbe in (("■ wird geschwärzt", FARBE_SCHWAERZEN), ("▭ nicht geschwärzt", FARBE_AUS),
                            ("■ manuell markiert", FARBE_MANUELL)):
            self.legende_vorher.append(tk.Label(legende, text=text, font=app.f_normal, fg=farbe, bg=FARBE_KARTE))
        self.legende_nachher = [
            tk.Label(legende, text="■ Verdacht nach dem Schwärzen", font=app.f_normal, fg=FARBE_VERDACHT,
                     bg=FARBE_KARTE),
            tk.Label(legende, text="graue Kästen mit [PLATZHALTER] = geschwärzt", font=app.f_normal,
                     fg=FARBE_AUS, bg=FARBE_KARTE)]

        # unten: Statuszeile + Schließen; darüber (nur nachher) die Verdachtsliste mit den Knöpfen
        unten = tk.Frame(f, bg=FARBE_KARTE, padx=8, pady=6)
        unten.pack(side="bottom", fill="x")
        app._knopf(unten, "Schließen", self.schliessen, True).pack(side="right")
        self.status_label = tk.Label(unten, text="", font=app.f_normal, bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU,
                                     anchor="w", justify="left", wraplength=app._px(700))
        self.status_label.pack(side="left", fill="x", expand=True)

        self.nachher_rahmen = tk.Frame(f, bg=FARBE_KARTE, padx=8, pady=4)
        knoepfe = tk.Frame(self.nachher_rahmen, bg=FARBE_KARTE)
        knoepfe.pack(side="right", fill="y", padx=(8, 0))
        self.freigeben_knopf = app._knopf(knoepfe, "  Freigeben  ", self.freigeben)
        self.freigeben_knopf.pack(fill="x")
        self.nachschwaerzen_knopf = app._knopf(knoepfe, "Markierte nachschwärzen", self.nachschwaerzen, True)
        self.nachschwaerzen_knopf.pack(fill="x", pady=(6, 0))
        self.verwerfen_knopf = app._knopf(knoepfe, "Verwerfen (Ausgabe löschen)", self.verwerfen, True)
        self.verwerfen_knopf.pack(fill="x", pady=(6, 0))
        liste_rahmen = tk.Frame(self.nachher_rahmen, bg=FARBE_KARTE)
        liste_rahmen.pack(side="left", fill="both", expand=True)
        self.verdacht_titel = tk.Label(liste_rahmen, text="Verdachtsstellen", font=app.f_fett, bg=FARBE_KARTE,
                                       anchor="w")
        self.verdacht_titel.pack(fill="x")
        self.verdacht_liste = tk.Listbox(liste_rahmen, height=4, selectmode="extended", font=app.f_normal,
                                         activestyle="none", exportselection=False)
        roll = ttk.Scrollbar(liste_rahmen, orient="vertical", command=self.verdacht_liste.yview)
        self.verdacht_liste.configure(yscrollcommand=roll.set)
        self.verdacht_liste.pack(side="left", fill="both", expand=True)
        roll.pack(side="right", fill="y")
        self.verdacht_liste.bind("<<ListboxSelect>>", self._verdacht_gewaehlt)

        # Warnzeile (nur sichtbar, wenn es etwas zu warnen gibt): Funde dieser Seite ohne Markierung
        self.warnzeile = tk.Label(f, text="", font=app.f_normal, bg=FARBE_KARTE, fg=FARBE_VERDACHT, anchor="w",
                                  justify="left", wraplength=app._px(860), padx=8)

        mitte = tk.Frame(f, bg=FARBE_HINTERGRUND)
        mitte.pack(side="top", fill="both", expand=True)
        self.mitte = mitte
        mitte.rowconfigure(0, weight=1)
        mitte.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(mitte, bg=FARBE_HINTERGRUND, highlightthickness=0, cursor="crosshair")
        roll_y = ttk.Scrollbar(mitte, orient="vertical", command=self.canvas.yview)
        roll_x = ttk.Scrollbar(mitte, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=roll_y.set, xscrollcommand=roll_x.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        roll_y.grid(row=0, column=1, sticky="ns")
        roll_x.grid(row=1, column=0, sticky="ew")
        c = self.canvas
        c.bind("<ButtonPress-1>", self._druecken)
        c.bind("<B1-Motion>", self._ziehen)
        c.bind("<ButtonRelease-1>", self._loslassen)
        c.bind("<Button-3>", self._rechtsklick)
        c.bind("<Configure>", self._canvas_geaendert)
        c.bind("<MouseWheel>", self._mausrad)
        c.bind("<Button-4>", self._mausrad)
        c.bind("<Button-5>", self._mausrad)

    # ------------------------------------------------------------------
    # Fensterzustand
    # ------------------------------------------------------------------
    def existiert(self) -> bool:
        try:
            return bool(self.fenster.winfo_exists())
        except tk.TclError:
            return False

    def nach_vorn(self):
        """Fenster nach vorn holen und ihm die Tastatur geben (Bild auf/ab, Pos1/Ende, +/-). Unter Windows bekam
        ein neues Vorschaufenster den Tastaturfokus nicht immer – die Blättertasten liefen dann ins Leere.
        Geöffnet wird die Vorschau nur auf Wunsch des Nutzers, das Fenster nimmt also keinem anderen Programm
        ungefragt den Fokus."""
        try:
            self.fenster.deiconify()
            self.fenster.lift()
            self.fenster.focus_force()
        except tk.TclError:
            pass

    def titel_setzen(self):
        name = self.app._anzeigename(self.pdf)
        if self.modus == "nachher" and self._ausgabe() is not None:
            titel = f"Prüfen – {self._ausgabe().name} ({name})"
        else:
            titel = f"Vorschau – {name}"
        try:
            self.fenster.title(titel)
        except tk.TclError:
            pass

    def schliessen(self, benachrichtigen: bool = True):
        if benachrichtigen and self.app.vorschauen.get(self.pdf) is self:
            self.app.vorschau_geschlossen(self.pdf)
        if not any(f is not self for f in self.app.vorschauen.values()):
            engine_zwischenspeicher_leeren()           # letzte Vorschau zu: vorbereitete Dokumente freigeben
        if self._zeichnen_geplant is not None:
            try:
                self.fenster.after_cancel(self._zeichnen_geplant)
            except tk.TclError:
                pass
        try:
            self.fenster.destroy()
        except tk.TclError:
            pass

    def status(self, text: str):
        try:
            self.status_label.config(text=text)
        except tk.TclError:
            pass

    def sperren(self, gesperrt: bool):
        """Während eines Laufs keine Änderungen (Klicks werden mit Hinweis abgewiesen)."""
        self.gesperrt = gesperrt
        self._knoepfe_aktualisieren()
        if gesperrt:
            self.status("Gerade läuft eine Analyse oder Schwärzung – Änderungen sind danach wieder möglich.")
        else:
            self.status(HINWEIS_VORHER if self.modus == "vorher" else HINWEIS_NACHHER)

    def _ausgabe(self) -> Path | None:
        eintrag = self.app.ausgaben.get(self.pdf)
        if not eintrag or eintrag.get("pfad") is None:
            return None
        return Path(eintrag["pfad"])

    def _verdacht(self) -> list:
        eintrag = self.app.ausgaben.get(self.pdf) or {}
        return list(eintrag.get("verdacht") or [])

    def _knoepfe_aktualisieren(self):
        hat_ausgabe = self.app.ausgabe_vorhanden(self.pdf)
        analysiert = self.pdf in self.app.analyse_ergebnisse
        status = (self.app.ausgaben.get(self.pdf) or {}).get("status")
        zustand = lambda ok: "normal" if ok and not self.gesperrt else "disabled"  # noqa: E731
        try:
            self.ergebnis_knopf.config(state=zustand(hat_ausgabe and self.modus != "nachher"))
            self.geplant_knopf.config(state=zustand(analysiert and self.modus != "vorher"))
            self.freigeben_knopf.config(state=zustand(hat_ausgabe and status == "pruefen"))
            self.verwerfen_knopf.config(state=zustand(hat_ausgabe))
            self.nachschwaerzen_knopf.config(state=zustand(hat_ausgabe and analysiert and bool(self._verdacht())))
        except tk.TclError:
            pass

    def modus_wechseln(self, modus: str, seite: int | None = None, markieren=None, erzwingen: bool = False):
        """„vorher“ (geplante Schwärzung des Originals) oder „nachher“ (Ausgabe mit Verdachtsstellen)."""
        if modus == "nachher" and not self.app.ausgabe_vorhanden(self.pdf):
            modus = "vorher"
        if modus == "vorher" and self.pdf not in self.app.analyse_ergebnisse:
            if self.app.ausgabe_vorhanden(self.pdf):
                modus = "nachher"
            else:
                self.schliessen()
                return
        gewechselt = modus != self.modus
        self.modus = modus
        if markieren is not None:
            self.markiert_fund = markieren
        self._daten.clear()
        if gewechselt or erzwingen:
            for label in self.legende_vorher + self.legende_nachher:
                label.pack_forget()
            for label in (self.legende_nachher if modus == "nachher" else self.legende_vorher):
                label.pack(side="left", padx=(0, 12))
            if modus == "nachher":
                # vor dem Seitenbereich packen, sonst nimmt dieser (expand) den ganzen Platz
                self.nachher_rahmen.pack(side="bottom", fill="x", before=self.mitte)
                self._verdachtsliste_fuellen()
            else:
                self.nachher_rahmen.pack_forget()
            self._bild_kennung = None
        elif modus == "nachher":
            self._verdachtsliste_fuellen()
        self.titel_setzen()
        self.seiten = self._seitenzahl()
        ziel = self.seite if seite is None else seite
        self.status(HINWEIS_VORHER if modus == "vorher" else HINWEIS_NACHHER)
        self._knoepfe_aktualisieren()
        self.zeige_seite(max(0, min(int(ziel or 0), self.seiten - 1)), erzwingen=True)

    # ------------------------------------------------------------------
    # Seiten, Zoom, Zeichnen
    # ------------------------------------------------------------------
    def _datei(self) -> Path:
        return self._ausgabe() if self.modus == "nachher" else self.pdf

    def _seitenmasse(self, pfad: Path) -> list:
        schluessel = str(pfad)
        if schluessel not in self._masse:
            with fitz.open(stream=Path(pfad).read_bytes(), filetype="pdf") as doc:
                self._masse[schluessel] = [fitz.Rect(s.rect) for s in doc]
        return self._masse[schluessel]

    def _seitenzahl(self) -> int:
        try:
            return max(1, len(self._seitenmasse(self._datei())))
        except Exception:
            return 1

    def blaettern(self, schritt: int):
        self.zeige_seite(self.seite + schritt)
        return "break"

    def zoom_breite(self):
        self.zoom_stufe = 1.0
        self.zeige_seite(self.seite, erzwingen=True)

    def zoomen(self, richtung: int):
        stufen = list(ZOOM_STUFEN)
        naechste = [s for s in stufen if (s > self.zoom_stufe + 1e-6 if richtung > 0 else s < self.zoom_stufe - 1e-6)]
        if naechste:
            self.zoom_stufe = min(naechste) if richtung > 0 else max(naechste)
            self.zeige_seite(self.seite, erzwingen=True)
        return "break"

    def _breiten_zoom(self) -> float:
        try:
            masse = self._seitenmasse(self._datei())[self.seite]
        except Exception:
            return 1.0
        breite = self.canvas.winfo_width()
        if breite < 50:
            breite = max(200, self.fenster.winfo_width() - 30)
        return max(0.2, (breite - 2 * RAND - 4) / max(masse.width, 1.0))

    def zeige_seite(self, nr: int, erzwingen: bool = False):
        if not self.existiert():
            return
        nr = max(0, min(int(nr), self.seiten - 1))
        if nr == self.seite and not erzwingen and self._bild is not None:
            return
        self.seite = nr
        self.seiten_label.config(text=f"Seite {nr + 1} / {self.seiten}")
        self.zurueck_knopf.config(state="normal" if nr > 0 else "disabled")
        self.vor_knopf.config(state="normal" if nr < self.seiten - 1 else "disabled")
        zoom = min(MAX_ZOOM, self._breiten_zoom() * self.zoom_stufe)
        datei = self._datei()
        kennung = (str(datei), nr, round(zoom, 3), self.modus)
        if kennung != self._bild_kennung:
            try:
                png, self.faktor = self._bild_holen(datei, nr, zoom)
                self._bild = tk.PhotoImage(master=self.canvas, data=base64.b64encode(png).decode("ascii"),
                                           format="png")
            except Exception as fehler:
                dateien.fehler_protokollieren(*sys.exc_info())
                self.canvas.delete("all")
                self.canvas.create_text(RAND, RAND, anchor="nw", fill="#b91c1c",
                                        text=f"Seite {nr + 1} konnte nicht dargestellt werden: {fehler}")
                self._bild = None
                self._bild_kennung = None
                return
            self._bild_kennung = kennung
            self.canvas.delete("all")
            self.canvas.create_image(RAND, RAND, image=self._bild, anchor="nw", tags=("seite",))
            self.canvas.configure(scrollregion=(0, 0, self._bild.width() + 2 * RAND, self._bild.height() + 2 * RAND))
            self._letzte_breite = self.canvas.winfo_width()
        self.markierungen_zeichnen()

    def _bild_holen(self, datei: Path, nr: int, zoom: float):
        """Seitenbild: vorher das Original (Engine, wenn sie Vorschau und Seitenmodell hat), nachher die AUSGABE
        immer aus dem Speicher (Attrappe) – ein offener Datei-Handle würde unter Windows „Freigeben“ (Umbenennen)
        und „Verwerfen“ (Löschen) verhindern."""
        if self.modus == "vorher" and vorher_quelle_engine(self.app, self.pdf):
            try:
                return _engine_vorschau.seite_bild(datei, nr, zoom)
            except Exception:
                _engine_fehler("seite_bild")
        return attrappen.seite_bild(datei, nr, zoom)

    def _canvas_geaendert(self, ereignis):
        if abs(ereignis.width - self._letzte_breite) < 8 or self._bild is None:
            return
        if self._zeichnen_geplant is not None:
            self.fenster.after_cancel(self._zeichnen_geplant)
        self._zeichnen_geplant = self.fenster.after(150, self._nach_groessenaenderung)

    def _nach_groessenaenderung(self):
        self._zeichnen_geplant = None
        if self.existiert():
            self.zeige_seite(self.seite, erzwingen=True)

    def _mausrad(self, ereignis):
        if getattr(ereignis, "num", None) == 4 or getattr(ereignis, "delta", 0) > 0:
            self.canvas.yview_scroll(-3, "units")
        else:
            self.canvas.yview_scroll(3, "units")
        return "break"

    # Koordinaten ---------------------------------------------------------
    def seite_zu_canvas(self, x: float, y: float) -> tuple[float, float]:
        return RAND + x * self.faktor, RAND + y * self.faktor

    def canvas_zu_seite(self, cx: float, cy: float) -> fitz.Point:
        return fitz.Point((cx - RAND) / self.faktor, (cy - RAND) / self.faktor)

    def punkt_fuer(self, x: float, y: float) -> tuple[int, int]:
        """Widget-Koordinaten (für event_generate) eines Seitenpunkts in pt."""
        cx, cy = self.seite_zu_canvas(x, y)
        return int(round(cx - self.canvas.canvasx(0))), int(round(cy - self.canvas.canvasy(0)))

    def _ereignis_punkt(self, ereignis) -> fitz.Point:
        return self.canvas_zu_seite(self.canvas.canvasx(ereignis.x), self.canvas.canvasy(ereignis.y))

    # Daten ---------------------------------------------------------------
    def daten(self, nr: int | None = None) -> dict:
        """vorschau_daten der Seite (vorher); gemerkt, bis sich Funde ändern."""
        nr = self.seite if nr is None else nr
        if nr not in self._daten:
            self._daten[nr] = vorschau_daten_holen(self.app, self.pdf, nr)
        return self._daten[nr]

    def fund_stellen(self, nr: int | None = None) -> list[tuple[fitz.Rect, int, int | None]]:
        """[(Rechteck, Fund-Index, Stellen-Index | None)] der Seite; Funde ohne Stellen in den Engine-Daten
        (z. B. „überall schwärzen“) werden über ihre Wörter gefunden (nur Anzeige)."""
        nr = self.seite if nr is None else nr
        ergebnis = self.app.analyse_ergebnisse.get(self.pdf)
        if not ergebnis:
            return []
        daten = self.daten(nr)
        funde = ergebnis["funde"]
        id_zu_index = {(f.get("id") or f"#{i}"): i for i, f in enumerate(funde)}
        eintraege, vertreten = [], set()
        for rect, fund_id, si, _an in daten.get("stellen", []):
            index = id_zu_index.get(fund_id)
            if index is None:
                continue
            eintraege.append((fitz.Rect(rect), index, si))
            vertreten.add(index)
        for index, fund in enumerate(funde):
            if index in vertreten or fund.get("stellen"):
                continue
            for _, _, rects in attrappen.stellen_suchen(daten.get("woerter", []), fund.get("text", "")):
                eintraege += [(r, index, None) for r in rects]
        return eintraege

    def ohne_markierung(self, nr: int | None = None) -> list[str]:
        """Funde, die laut Analyse auf dieser Seite stehen, hier aber keine Markierung haben (z. B. Teil eines
        längeren Worts) – werden im Fenster genannt statt still zu fehlen."""
        nr = self.seite if nr is None else nr
        ergebnis = self.app.analyse_ergebnisse.get(self.pdf)
        if not ergebnis:
            return []
        gezeigt = {index for _, index, _ in self.fund_stellen(nr)}

        def erwartet(fund) -> bool:
            if fund.get("stellen"):
                return any(s.get("seite") == nr for s in fund["stellen"])
            return nr + 1 in (fund.get("seiten") or [])
        return [f["text"] for i, f in enumerate(ergebnis["funde"]) if i not in gezeigt and erwartet(f)]

    def stelle_an(self, index: int, stelle_index) -> bool:
        ergebnis = self.app.analyse_ergebnisse.get(self.pdf)
        if not ergebnis:
            return False
        fund = ergebnis["funde"][index]
        if stelle_index is not None and self.app._fund_hat_stellen(self.pdf, fund):
            return bool(fund["stellen"][stelle_index].get("an", True))
        return self.app.fund_zustand(self.pdf, index) != "aus"

    def manuelle(self, nr: int | None = None) -> list[tuple[int, dict]]:
        nr = self.seite if nr is None else nr
        return [(mid, e) for mid, e in self.app.manuell.get(self.pdf, {}).items() if e["seite"] == nr]

    # Markierungen ---------------------------------------------------------
    def neu_zeichnen(self):
        """Nach Änderungen in der Hauptliste: Daten neu holen (Funde können dazugekommen sein), Markierungen."""
        if not self.existiert():
            return
        self._daten.clear()
        if self.modus == "vorher" and self.pdf not in self.app.analyse_ergebnisse:
            self.modus_wechseln("nachher")
            return
        if self.modus == "nachher":
            self._verdachtsliste_fuellen()
        self._knoepfe_aktualisieren()
        self.markierungen_zeichnen()

    def _rechteck(self, r, farbe, an: bool, breite=2, tags=()):
        x0, y0 = self.seite_zu_canvas(r.x0, r.y0)
        x1, y1 = self.seite_zu_canvas(r.x1, r.y1)
        optionen = {"outline": farbe, "width": breite, "tags": ("markierung",) + tuple(tags)}
        if an:
            try:
                return self.canvas.create_rectangle(x0, y0, x1, y1, fill=farbe, stipple="gray12", **optionen)
            except tk.TclError:                  # Plattform ohne Stipple
                return self.canvas.create_rectangle(x0, y0, x1, y1, **optionen)
        return self.canvas.create_rectangle(x0, y0, x1, y1, dash=(4, 3), **optionen)

    def markierungen_zeichnen(self):
        self.canvas.delete("markierung")
        if self._bild is None:
            return
        if self.modus == "vorher":
            erste_markiert = None
            for rect, index, si in self.fund_stellen():
                an = self.stelle_an(index, si)
                hervor = index == self.markiert_fund
                self._rechteck(rect, FARBE_SCHWAERZEN if an else FARBE_AUS, an, 4 if hervor else 2,
                               tags=("stelle", f"fund_{index}"))
                if hervor and erste_markiert is None:
                    erste_markiert = rect
            for mid, eintrag in self.manuelle():
                for r in eintrag["rechtecke"]:
                    self._rechteck(fitz.Rect(r), FARBE_MANUELL, eintrag.get("an", True), tags=("manuell", f"m_{mid}"))
            if erste_markiert is not None:
                self._sichtbar_machen(erste_markiert)
            self._warnzeile_setzen(self.ohne_markierung())
        else:
            self._warnzeile_setzen([])
        if self.modus == "nachher":
            auswahl = set(self.verdacht_liste.curselection())
            for i, v in enumerate(self._verdacht()):
                if attrappen.verdacht_feld(v, "seite") != self.seite:
                    continue
                for r in attrappen.verdacht_feld(v, "rechtecke") or []:
                    self._rechteck(_vergroessert(r), FARBE_VERDACHT, False, 4 if i in auswahl else 2,
                                   tags=("verdacht", f"v_{i}"))

    def _warnzeile_setzen(self, fehlend: list):
        if fehlend:
            liste = ", ".join(f"„{str(t).replace(chr(10), ' ')[:30]}“" for t in fehlend[:4])
            self.warnzeile.config(text=f"⚠ Auf dieser Seite ohne Markierung: {liste}" + (" …" if len(fehlend) > 4
                                                                                        else "")
                                  + " – die Schreibweise im Dokument weicht ab (z. B. Teil eines längeren Worts). "
                                    "Bitte selbst prüfen; die Kontrolle nach dem Schwärzen meldet nicht geschwärzte "
                                    "Reste.")
            if not self.warnzeile.winfo_manager():
                self.warnzeile.pack(side="top", fill="x", before=self.mitte)
        elif self.warnzeile.winfo_manager():
            self.warnzeile.pack_forget()

    def _sichtbar_machen(self, rect):
        """Scrollt so, dass das Rechteck sichtbar ist."""
        try:
            gesamt = self._bild.height() + 2 * RAND
            _, cy = self.seite_zu_canvas(rect.x0, rect.y0)
            sicht = self.canvas.winfo_height()
            if gesamt > sicht > 1:
                self.canvas.yview_moveto(max(0.0, (cy - sicht / 3) / gesamt))
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Maus: Klick, Rahmen, Kontextmenü
    # ------------------------------------------------------------------
    def treffer_an(self, punkt: fitz.Point):
        """Was liegt unter dem Punkt (Seitenkoordinaten)? ("bereich", mid) | ("manuell", mid) |
        ("stelle", Fund-Index, Stellen-Index) | ("wort", Wort) | None."""
        manuelle = self.manuelle()
        for mid, eintrag in manuelle:
            if eintrag["art"] == "bereich" and any(_vergroessert(r, 0.5).contains(punkt) for r in eintrag["rechtecke"]):
                return ("bereich", mid)
        for mid, eintrag in manuelle:
            if eintrag["art"] != "bereich" and any(_vergroessert(r).contains(punkt) for r in eintrag["rechtecke"]):
                return ("manuell", mid)
        unter = [(rect, index, si) for rect, index, si in self.fund_stellen() if _vergroessert(rect).contains(punkt)]
        if unter:
            # die kleinste Stelle gewinnt: ein Name in einer abgewählt angebotenen Diagnose („Diabetes … bei Herrn
            # Meier“) bekommt den Klick, nicht die umfassende Gesundheitsangabe
            rect, index, si = min(unter, key=lambda u: u[0].width * u[0].height)
            return ("stelle", index, si)
        for wort in self.daten().get("woerter", []):
            if _vergroessert(wort[0], 0.5).contains(punkt):
                return ("wort", wort)
        return None

    def _gesperrt_hinweis(self) -> bool:
        if self.gesperrt or self.app.laeuft:
            self.status("Gerade läuft eine Analyse oder Schwärzung – Änderungen sind danach wieder möglich.")
            return True
        return False

    def _druecken(self, ereignis):
        self._druck = (self.canvas.canvasx(ereignis.x), self.canvas.canvasy(ereignis.y))

    def _ziehen(self, ereignis):
        if self._druck is None or self.modus != "vorher":
            return
        x0, y0 = self._druck
        x1, y1 = self.canvas.canvasx(ereignis.x), self.canvas.canvasy(ereignis.y)
        self.canvas.delete("gummi")
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=FARBE_MANUELL, width=2, dash=(3, 2), tags=("gummi",))

    def _loslassen(self, ereignis):
        start, self._druck = self._druck, None
        self.canvas.delete("gummi")
        if start is None or self._bild is None:
            return
        ende = (self.canvas.canvasx(ereignis.x), self.canvas.canvasy(ereignis.y))
        if abs(ende[0] - start[0]) >= ZIEH_SCHWELLE or abs(ende[1] - start[1]) >= ZIEH_SCHWELLE:
            if self.modus == "vorher":
                a, b = self.canvas_zu_seite(*start), self.canvas_zu_seite(*ende)
                self.bereich_schwaerzen(fitz.Rect(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y)))
            return
        self.klick(self.canvas_zu_seite(*ende))

    def klick(self, punkt: fitz.Point):
        """Linksklick auf einen Seitenpunkt."""
        if self.modus == "nachher":
            self._verdacht_klick(punkt)
            return
        if self._gesperrt_hinweis():
            return
        treffer = self.treffer_an(punkt)
        if treffer is None:
            return
        art = treffer[0]
        if art == "bereich":
            self.status("Dieser Bereich wird vollständig geschwärzt (Text und Bild). Rechtsklick → „Bereich "
                        "entfernen“.")
        elif art == "manuell":
            self.app.manuell_umschalten(self.pdf, treffer[1])
        elif art == "stelle":
            _, index, si = treffer
            an = self.stelle_an(index, si)
            fund = self.app.analyse_ergebnisse[self.pdf]["funde"][index]
            if si is not None and self.app._fund_hat_stellen(self.pdf, fund):
                self.app.stelle_setzen(self.pdf, index, si, not an)
                self.status(f"Stelle „{fund['text']}“ {'wird nicht' if an else 'wird'} geschwärzt.")
            else:
                self.app.fund_setzen(self.pdf, index, not an)
                self.status(f"„{fund['text']}“ {'wird nirgends' if an else 'wird überall'} geschwärzt "
                            f"(dieser Fund gilt für alle seine Stellen).")
        elif art == "wort":
            self.wort_schwaerzen(treffer[1])

    def wort_schwaerzen(self, wort):
        """Nicht erkanntes Wort schwärzen: als manuelle Stelle (Engine mit Seitenmodell), sonst als manueller
        Bereich (Wortrechteck), sonst überall im Dokument (IMMER-Begriff für diesen Lauf)."""
        rect, text, start, ende = wort[0], wort[1], wort[2], wort[3]
        if self.app.kann_manuelle_stellen() and offsets_vom_modell(self.app, self.pdf, self.daten()):
            self.app.manuell_hinzufuegen(self.pdf, {"art": "stelle", "seite": self.seite, "start": start,
                                                    "ende": ende, "rechtecke": [fitz.Rect(rect)], "text": text})
            self.status(f"„{text}“ wird an dieser Stelle geschwärzt (Klick darauf nimmt es zurück).")
        elif self.app.kann_manuelle_bereiche():
            self.app.manuell_hinzufuegen(self.pdf, {"art": "bereich", "seite": self.seite,
                                                    "rechtecke": [_vergroessert(rect)], "text": text})
            self.status(f"„{text}“ wird an dieser Stelle geschwärzt (Klick darauf nimmt es zurück).")
        else:
            kern = text.strip(attrappen.SATZZEICHEN) or text
            self.app.begriff_ueberall(self.pdf, kern)
            self.status(f"„{kern}“ wird überall in diesem Dokument geschwärzt – einzelne Stellen kann diese "
                        f"Programmversion noch nicht schwärzen.")

    def bereich_schwaerzen(self, rect: fitz.Rect):
        if self._gesperrt_hinweis():
            return
        if rect.width < MIN_BEREICH_PT or rect.height < MIN_BEREICH_PT:
            return
        if not self.app.kann_manuelle_bereiche():
            self.status("Rahmen schwärzen kann diese Programmversion noch nicht – bitte Wörter anklicken oder den "
                        "Text in die IMMER-Liste eintragen.")
            return
        masse = self._seitenmasse(self.pdf)[self.seite]
        rect = rect & masse
        if rect.is_empty:
            return
        self.app.manuell_hinzufuegen(self.pdf, {"art": "bereich", "seite": self.seite, "rechtecke": [rect],
                                                "text": f"Bereich auf Seite {self.seite + 1}"})
        self.status("Bereich wird vollständig geschwärzt (Text und Bild). Rechtsklick darauf → „Bereich entfernen“.")

    def kontextmenue_eintraege(self, punkt: fitz.Point) -> list[tuple[str, object]]:
        """Einträge des Kontextmenüs an einem Seitenpunkt: [(Beschriftung, Befehl)]."""
        if self.modus != "vorher" or self.gesperrt or self.app.laeuft:
            return []
        pdf, app = self.pdf, self.app
        treffer = self.treffer_an(punkt)
        wort = next((w for w in self.daten().get("woerter", []) if _vergroessert(w[0], 0.5).contains(punkt)), None)
        eintraege: list[tuple[str, object]] = []
        if treffer and treffer[0] in ("bereich", "manuell"):
            mid = treffer[1]
            eintrag = app.manuell.get(pdf, {}).get(mid)
            if treffer[0] == "manuell" and eintrag is not None:
                eintraege.append(("Diese Stelle nicht schwärzen" if eintrag.get("an", True) else
                                  "Diese Stelle schwärzen", lambda: app.manuell_umschalten(pdf, mid)))
            eintraege.append(("Bereich entfernen" if treffer[0] == "bereich" else "Markierung entfernen",
                              lambda: app.manuell_entfernen(pdf, mid)))
        elif treffer and treffer[0] == "stelle":
            _, index, si = treffer
            fund = app.analyse_ergebnisse[pdf]["funde"][index]
            an = self.stelle_an(index, si)
            kurz = str(fund["text"]).replace("\n", " ")[:40]
            if si is not None and app._fund_hat_stellen(pdf, fund):
                eintraege.append(("Diese Stelle nicht schwärzen" if an else "Diese Stelle schwärzen",
                                  lambda: app.stelle_setzen(pdf, index, si, not an)))
            eintraege.append((f"„{kurz}“ nirgends schwärzen (ganzer Fund)", lambda: app.fund_setzen(pdf, index, False)))
            eintraege.append((f"„{kurz}“ überall schwärzen (ganzer Fund)", lambda: app.fund_setzen(pdf, index, True)))
        elif treffer and treffer[0] == "wort":
            eintraege.append(("Dieses Wort schwärzen", lambda: self.wort_schwaerzen(treffer[1])))
        if wort is not None:
            kern = wort[1].strip(attrappen.SATZZEICHEN) or wort[1]
            eintraege.append((f"„{kern}“ überall in diesem Dokument schwärzen",
                              lambda: (app.begriff_ueberall(pdf, kern),
                                       self.status(f"„{kern}“ wird überall in diesem Dokument geschwärzt."))))
        return eintraege

    def _rechtsklick(self, ereignis):
        eintraege = self.kontextmenue_eintraege(self._ereignis_punkt(ereignis))
        self.letztes_menue = eintraege
        if not eintraege:
            return
        menue = tk.Menu(self.fenster, tearoff=0)
        for text, befehl in eintraege:
            menue.add_command(label=text, command=befehl)
        try:
            menue.tk_popup(ereignis.x_root, ereignis.y_root)
        finally:
            menue.grab_release()

    # ------------------------------------------------------------------
    # Nach dem Schwärzen: Verdachtsliste, Freigeben, Nachschwärzen, Verwerfen
    # ------------------------------------------------------------------
    def _verdachtsliste_fuellen(self):
        liste = self.verdacht_liste
        liste.delete(0, "end")
        verdacht = self._verdacht()
        ausgabe = self._ausgabe()
        status = (self.app.ausgaben.get(self.pdf) or {}).get("status")
        for v in verdacht:
            seite = attrappen.verdacht_feld(v, "seite")
            text = str(attrappen.verdacht_feld(v, "text", "") or "").replace("\n", " ")
            grund = attrappen.verdacht_feld(v, "grund", "") or ""
            liste.insert("end", f"S. {int(seite) + 1 if seite is not None else '?'}: „{text[:50]}“ – {grund}")
        if verdacht:
            liste.selection_set(0, "end")
            self.verdacht_titel.config(text=f"{len(verdacht)} Verdachtsstelle(n) in {ausgabe.name if ausgabe else '?'}"
                                            f" – markierte werden nachgeschwärzt:")
        else:
            liste.insert("end", "Keine Verdachtsstellen gemeldet – bitte die Seiten trotzdem durchsehen.")
            liste.itemconfigure(0, foreground=FARBE_TEXT_GRAU)
            self.verdacht_titel.config(text=f"{ausgabe.name if ausgabe else 'Ausgabe'}"
                                            + (" – noch nicht freigegeben" if status == "pruefen" else
                                               " – freigegeben" if status == "fertig" else ""))

    def _verdacht_gewaehlt(self, ereignis=None):
        auswahl = self.verdacht_liste.curselection()
        verdacht = self._verdacht()
        if len(auswahl) == 1 and auswahl[0] < len(verdacht):
            seite = attrappen.verdacht_feld(verdacht[auswahl[0]], "seite")
            if seite is not None and int(seite) != self.seite:
                self.zeige_seite(int(seite))
                return
        self.markierungen_zeichnen()

    def _verdacht_klick(self, punkt):
        for i, v in enumerate(self._verdacht()):
            if attrappen.verdacht_feld(v, "seite") != self.seite:
                continue
            if any(_vergroessert(r, 2).contains(punkt) for r in attrappen.verdacht_feld(v, "rechtecke") or []):
                if i in self.verdacht_liste.curselection():
                    self.verdacht_liste.selection_clear(i)
                else:
                    self.verdacht_liste.selection_set(i)
                self.markierungen_zeichnen()
                return

    def freigeben(self):
        if self._gesperrt_hinweis():
            return
        ausgabe = self._ausgabe()
        if ausgabe is None:
            return
        offen = len(self._verdacht())
        text = f"„{ausgabe.name}“ zur Weitergabe freigeben? Danach heißt die Datei ohne „_PRUEFEN“."
        if offen:
            text += (f"\n\nEs gibt noch {offen} Verdachtsstelle(n). Nur freigeben, wenn dort nichts Persönliches "
                     f"mehr zu sehen ist – sonst erst „Markierte nachschwärzen“.")
        if not self.app._frage("Ausgabe freigeben", text, warnung=bool(offen), eltern=self.fenster):
            return
        neu = self.app.ausgabe_freigeben(self.pdf)
        if neu is None:
            return
        naechste = self.app.naechste_zu_pruefen(nach=self.pdf)
        if naechste is not None:
            self.datei_wechseln(naechste)
            self.status(f"„{neu.name}“ freigegeben. Weiter mit „{self.app._anzeigename(naechste)}“.")
        else:
            self.modus_wechseln("nachher")
            self.status(f"„{neu.name}“ freigegeben – alle Ausgaben dieses Laufs sind geprüft.")

    def datei_wechseln(self, pdf: Path, modus: str = "nachher"):
        """Dieses Fenster für die nächste zu prüfende Datei weiterverwenden."""
        anderes = self.app.vorschauen.get(pdf)
        if anderes is not None and anderes is not self:
            anderes.schliessen(benachrichtigen=False)
        if self.app.vorschauen.get(self.pdf) is self:
            self.app.vorschauen.pop(self.pdf, None)
        self.pdf = Path(pdf)
        self.app.vorschauen[self.pdf] = self
        self._masse.clear()
        self.markiert_fund = None
        self.modus = None
        self.modus_wechseln(modus, seite=0, erzwingen=True)

    def verwerfen(self):
        if self._gesperrt_hinweis():
            return
        ausgabe = self._ausgabe()
        if ausgabe is None:
            return
        if not self.app._frage("Ausgabe verwerfen", f"„{ausgabe.name}“ löschen? Das Original bleibt unverändert; "
                                                    f"die Datei kann danach neu geschwärzt werden.",
                               warnung=True, eltern=self.fenster):
            return
        if self.app.ausgabe_verwerfen(self.pdf):
            if self.pdf in self.app.analyse_ergebnisse:
                self.modus_wechseln("vorher")
                self.status(f"„{ausgabe.name}“ verworfen. Hier die geplante Schwärzung – nach Änderungen erneut "
                            f"„Schwärzen starten“.")
            else:
                self.schliessen()

    def nachschwaerzen(self):
        if self._gesperrt_hinweis():
            return
        verdacht = self._verdacht()
        auswahl = [i for i in self.verdacht_liste.curselection() if i < len(verdacht)]
        if not auswahl:
            self.status("Bitte zuerst eine oder mehrere Verdachtsstellen in der Liste markieren.")
            return
        if self.app.nachschwaerzen(self.pdf, [verdacht[i] for i in auswahl]):
            self.status(f"{len(auswahl)} Verdachtsstelle(n) werden nachgeschwärzt …")
        else:
            self.status("Nachschwärzen war nicht möglich – siehe Hinweis im Hauptfenster.")
