"""Grafische Oberfläche (tkinter)."""

import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .analyse import analysiere_pdf
from .dateien import sammle_pdfs
from .namen import lade_ner
from .muster import KATEGORIEN
from .schwaerzung import schwaerze_pdf

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_VERFUEGBAR = True
except ImportError:
    DND_VERFUEGBAR = False


def _unbehandelter_fehler(typ, wert, tb):
    """Wird vom Startskript gesetzt (sys.excepthook); hier nur Weiterleitung."""
    sys.excepthook(typ, wert, tb)


FARBE_HINTERGRUND = "#f4f5f7"
FARBE_KARTE = "#ffffff"
FARBE_AKZENT = "#1a5fb4"
FARBE_AKZENT_HELL = "#e8f0fb"
FARBE_TEXT_GRAU = "#6b7280"
FARBE_GRUEN = "#1a7f37"
FARBE_ROT = "#b91c1c"


class AnonymisiererApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF-Anonymisierer — Dokumente sicher für KI-Dienste machen")
        self.root.geometry("860x900")
        self.root.minsize(760, 780)
        self.root.configure(bg=FARBE_HINTERGRUND)

        self.dateien: list[Path] = []
        self.analyse_ergebnisse: dict = {}   # Pfad -> Ergebnis von analysiere_pdf
        self.laeuft = False

        self._baue_oberflaeche()

    # ------------------------------------------------------------------
    def _baue_oberflaeche(self):
        haupt = tk.Frame(self.root, bg=FARBE_HINTERGRUND, padx=20, pady=12)
        haupt.pack(fill="both", expand=True)

        tk.Label(haupt, text="PDF-Anonymisierer", font=("Segoe UI", 19, "bold"),
                 bg=FARBE_HINTERGRUND, fg="#111827").pack(anchor="w")
        tk.Label(haupt,
                 text="Findet personenbezogene Daten automatisch und ersetzt sie durch Platzhalter "
                      "([PERSON A], [IBAN] …) — für die gefahrlose Weitergabe an ChatGPT & Claude.",
                 font=("Segoe UI", 9), bg=FARBE_HINTERGRUND, fg=FARBE_TEXT_GRAU,
                 wraplength=800, justify="left").pack(anchor="w", pady=(0, 8))

        # ---------- Schritt 1: Dateien ----------
        karte1 = self._karte(haupt, "1  ·  PDF-Dateien", expand=False)
        drop_text = ("PDFs oder ganze Ordner hierher ziehen  (oder klicken zum Auswählen)"
                     if DND_VERFUEGBAR else
                     "Drag & Drop nicht verfügbar — bitte klicken zum Auswählen")
        self.drop_zone = tk.Label(karte1, text="⬇  " + drop_text,
                                  font=("Segoe UI", 10), bg=FARBE_AKZENT_HELL,
                                  fg=FARBE_AKZENT, height=2, cursor="hand2",
                                  highlightthickness=2, highlightbackground="#b9cfee")
        self.drop_zone.pack(fill="x", pady=(2, 6))
        self.drop_zone.bind("<Button-1>", lambda e: self.dateien_waehlen())
        if DND_VERFUEGBAR:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._drop_ereignis)

        zeile = tk.Frame(karte1, bg=FARBE_KARTE); zeile.pack(fill="x")
        self._knopf(zeile, "Dateien auswählen …", self.dateien_waehlen, True).pack(side="left")
        self._knopf(zeile, "Ordner auswählen …", self.ordner_waehlen, True).pack(side="left", padx=(6, 0))
        self.datei_hinweis = tk.Label(zeile, text="Noch keine Dateien.",
                                      font=("Segoe UI", 9), bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU)
        self.datei_hinweis.pack(side="left", padx=(12, 0))
        self._knopf(zeile, "Liste leeren", self.liste_leeren, True).pack(side="right")

        # ---------- Schritt 2: Was soll erkannt werden? ----------
        karte2 = self._karte(haupt, "2  ·  Was soll erkannt werden?", expand=False)
        gitter = tk.Frame(karte2, bg=FARBE_KARTE); gitter.pack(fill="x")
        self.kategorie_vars: dict[str, tk.BooleanVar] = {}
        for i, (schluessel, anzeige, _, _, standard) in enumerate(KATEGORIEN):
            var = tk.BooleanVar(value=standard)
            self.kategorie_vars[schluessel] = var
            tk.Checkbutton(gitter, text=anzeige, variable=var, font=("Segoe UI", 9),
                           bg=FARBE_KARTE, activebackground=FARBE_KARTE, anchor="w"
                           ).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 12))

        listen = tk.Frame(karte2, bg=FARBE_KARTE); listen.pack(fill="x", pady=(8, 0))
        links = tk.Frame(listen, bg=FARBE_KARTE); links.pack(side="left", fill="both", expand=True, padx=(0, 8))
        rechts = tk.Frame(listen, bg=FARBE_KARTE); rechts.pack(side="left", fill="both", expand=True)

        tk.Label(links, text="Zusätzlich IMMER schwärzen (ein Begriff pro Zeile):",
                 font=("Segoe UI", 9, "bold"), bg=FARBE_KARTE).pack(anchor="w")
        self.immer_feld = tk.Text(links, height=3, font=("Segoe UI", 9), relief="flat",
                                  highlightthickness=1, highlightbackground="#e5e7eb", bg="#fafafa")
        self.immer_feld.pack(fill="x")

        tk.Label(rechts, text="NIE schwärzen (z. B. eigene Firmen-/Beraternamen):",
                 font=("Segoe UI", 9, "bold"), bg=FARBE_KARTE).pack(anchor="w")
        self.nie_feld = tk.Text(rechts, height=3, font=("Segoe UI", 9), relief="flat",
                                highlightthickness=1, highlightbackground="#e5e7eb", bg="#fafafa")
        self.nie_feld.pack(fill="x")

        self.analyse_knopf = self._knopf(karte2, "  1. Analysieren — Funde anzeigen  ", self.analysieren)
        self.analyse_knopf.pack(anchor="w", pady=(8, 0))

        # ---------- Schritt 3: Prüfen & Schwärzen ----------
        karte3 = self._karte(haupt, "3  ·  Funde prüfen, dann schwärzen", expand=True)
        tk.Label(karte3, text="Doppelklick auf eine Zeile = Häkchen an/aus. Nur angehakte Funde werden ersetzt.",
                 font=("Segoe UI", 9), bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU).pack(anchor="w")

        baum_rahmen = tk.Frame(karte3, bg=FARBE_KARTE)
        baum_rahmen.pack(fill="both", expand=True, pady=(4, 6))
        spalten = ("kategorie", "text", "ersatz")
        self.baum = ttk.Treeview(baum_rahmen, columns=spalten, show="tree headings",
                                 selectmode="browse")
        self.baum.heading("#0", text="✓ / Datei")
        self.baum.heading("kategorie", text="Kategorie")
        self.baum.heading("text", text="Gefundener Text")
        self.baum.heading("ersatz", text="Wird ersetzt durch")
        self.baum.column("#0", width=200, anchor="w")
        self.baum.column("kategorie", width=140, anchor="w")
        self.baum.column("text", width=260, anchor="w")
        self.baum.column("ersatz", width=130, anchor="w")
        roll = ttk.Scrollbar(baum_rahmen, command=self.baum.yview)
        self.baum.configure(yscrollcommand=roll.set)
        self.baum.pack(side="left", fill="both", expand=True)
        roll.pack(side="right", fill="y")
        self.baum.bind("<Double-Button-1>", self._haken_umschalten)
        self.baum.bind("<space>", self._haken_umschalten)

        zeile3 = tk.Frame(karte3, bg=FARBE_KARTE); zeile3.pack(fill="x")
        self.start_knopf = self._knopf(zeile3, "  2. Schwärzen starten  ", self.schwaerzen)
        self.start_knopf.pack(side="left")
        self.start_knopf.config(state="disabled")
        self.fortschritt = ttk.Progressbar(zeile3, mode="determinate")
        self.fortschritt.pack(side="left", fill="x", expand=True, padx=(10, 0))

        self.protokoll = tk.Text(karte3, height=5, font=("Consolas", 9), relief="flat",
                                 highlightthickness=1, highlightbackground="#e5e7eb",
                                 bg="#fafafa", state="disabled", wrap="word")
        self.protokoll.pack(fill="x", pady=(6, 0))
        for stil, farbe in [("ok", FARBE_GRUEN), ("warnung", "#b45309"),
                            ("fehler", FARBE_ROT), ("grau", FARBE_TEXT_GRAU)]:
            self.protokoll.tag_configure(stil, foreground=farbe)

    # Oberflächen-Helfer ------------------------------------------------
    def _karte(self, eltern, titel, expand):
        rahmen = tk.Frame(eltern, bg=FARBE_KARTE, padx=14, pady=10,
                          highlightthickness=1, highlightbackground="#e5e7eb")
        rahmen.pack(fill="both" if expand else "x", expand=expand, pady=(0, 10))
        tk.Label(rahmen, text=titel, font=("Segoe UI", 11, "bold"),
                 bg=FARBE_KARTE, fg="#111827").pack(anchor="w", pady=(0, 4))
        return rahmen

    def _knopf(self, eltern, text, befehl, sekundaer=False):
        if sekundaer:
            return tk.Button(eltern, text=text, command=befehl, font=("Segoe UI", 9),
                             bg="#eef1f5", fg="#111827", relief="flat",
                             padx=10, pady=3, cursor="hand2", activebackground="#dde3ea")
        return tk.Button(eltern, text=text, command=befehl, font=("Segoe UI", 10, "bold"),
                         bg=FARBE_AKZENT, fg="white", relief="flat",
                         padx=12, pady=6, cursor="hand2",
                         activebackground="#134a8e", activeforeground="white")

    # Dateiauswahl ------------------------------------------------------
    def _drop_ereignis(self, ereignis):
        pfade = re.findall(r"\{([^}]*)\}|(\S+)", ereignis.data)
        self._pdfs_hinzufuegen([a or b for a, b in pfade])

    def dateien_waehlen(self):
        pfade = filedialog.askopenfilenames(title="PDF-Dateien auswählen",
                                            filetypes=[("PDF-Dateien", "*.pdf")])
        if pfade:
            self._pdfs_hinzufuegen(list(pfade))

    def ordner_waehlen(self):
        ordner = filedialog.askdirectory(title="Ordner mit PDFs auswählen")
        if ordner:
            self._pdfs_hinzufuegen([ordner])

    def _pdfs_hinzufuegen(self, pfade):
        for pdf in sammle_pdfs(pfade):
            if pdf not in self.dateien:
                self.dateien.append(pdf)
        self.datei_hinweis.config(text=f"{len(self.dateien)} PDF-Datei(en) ausgewählt."
                                  if self.dateien else "Noch keine Dateien.")

    def liste_leeren(self):
        self.dateien.clear()
        self.analyse_ergebnisse.clear()
        self.baum.delete(*self.baum.get_children())
        self.start_knopf.config(state="disabled")
        self.datei_hinweis.config(text="Noch keine Dateien.")

    # Analyse -----------------------------------------------------------
    def analysieren(self):
        if self.laeuft:
            return
        if not self.dateien:
            messagebox.showwarning("Keine Dateien", "Bitte zuerst PDF-Dateien auswählen.")
            return
        self.laeuft = True
        self.analyse_knopf.config(state="disabled", text="  Analysiere …  ")
        self.start_knopf.config(state="disabled")
        self.baum.delete(*self.baum.get_children())
        self._protokoll_leeren()
        self.fortschritt.config(value=0, maximum=len(self.dateien))

        aktive = {k for k, v in self.kategorie_vars.items() if v.get()}
        immer = [z.strip() for z in self.immer_feld.get("1.0", "end").splitlines() if z.strip()]
        nie = [z.strip() for z in self.nie_feld.get("1.0", "end").splitlines() if z.strip()]

        threading.Thread(target=self._analyse_lauf, args=(aktive, nie, immer),
                         daemon=True).start()

    def _analyse_lauf(self, aktive, nie, immer):
        # Sprachmodell einmal vorab laden (dauert beim ersten Mal einige Sekunden)
        if "namen" in aktive:
            self._log("Lade Namenserkennungs-Modell …", "grau")
            lade_ner()
        gesamt = 0
        for i, pdf in enumerate(self.dateien, 1):
            ergebnis = analysiere_pdf(pdf, aktive, nie, immer,
                                      melde=lambda t: self._log(t, "grau"))
            self.analyse_ergebnisse[pdf] = ergebnis
            if ergebnis["fehler"]:
                self._log(f"✖ {pdf.name}: {ergebnis['fehler']}", "fehler")
            for w in ergebnis["warnungen"]:
                self._log(f"⚠ {pdf.name}: {w}", "warnung")
            gesamt += len(ergebnis["funde"])
            self.root.after(0, self._baum_fuellen, pdf, ergebnis["funde"])
            self._fortschritt_setzen(i)
        self._log(f"Analyse fertig: {gesamt} Fund(e) in {len(self.dateien)} Datei(en). "
                  f"Bitte Liste prüfen, dann schwärzen.", "ok")
        self.root.after(0, self._analyse_fertig, gesamt)

    def _baum_fuellen(self, pdf, funde):
        eltern = self.baum.insert("", "end", text=f"☑  {pdf.name}", open=True,
                                  values=("", f"{len(funde)} Fund(e)", ""))
        for fund in funde:
            self.baum.insert(eltern, "end", text="☑",
                             values=(fund["anzeige"], fund["text"], fund["ersatz"]),
                             tags=("an",))

    def _analyse_fertig(self, gesamt):
        self.laeuft = False
        self.analyse_knopf.config(state="normal", text="  1. Analysieren — Funde anzeigen  ")
        if gesamt:
            self.start_knopf.config(state="normal")

    def _haken_umschalten(self, ereignis=None):
        eintrag = self.baum.focus()
        if not eintrag:
            return
        text = self.baum.item(eintrag, "text")
        neu = text.replace("☑", "☐") if "☑" in text else text.replace("☐", "☑")
        self.baum.item(eintrag, text=neu)
        # Bei einer Datei-Zeile: alle Kinder mit umschalten
        for kind in self.baum.get_children(eintrag):
            kt = self.baum.item(kind, "text")
            self.baum.item(kind, text="☑" if "☑" in neu else "☐")

    # Schwärzen ---------------------------------------------------------
    def schwaerzen(self):
        if self.laeuft:
            return
        auftraege = []  # (pdf, [funde])
        for datei_eintrag in self.baum.get_children():
            name = self.baum.item(datei_eintrag, "text").replace("☑", "").replace("☐", "").strip()
            pdf = next((p for p in self.dateien if p.name == name), None)
            if pdf is None:
                continue
            gewaehlt = []
            alle_funde = self.analyse_ergebnisse.get(pdf, {}).get("funde", [])
            kinder = self.baum.get_children(datei_eintrag)
            for kind, fund in zip(kinder, alle_funde):
                if "☑" in self.baum.item(kind, "text"):
                    gewaehlt.append(fund)
            if gewaehlt:
                auftraege.append((pdf, gewaehlt))
        if not auftraege:
            messagebox.showwarning("Nichts ausgewählt", "Es ist kein Fund angehakt.")
            return

        self.laeuft = True
        self.start_knopf.config(state="disabled", text="  Läuft …  ")
        self.fortschritt.config(value=0, maximum=len(auftraege))
        threading.Thread(target=self._schwaerz_lauf, args=(auftraege,), daemon=True).start()

    def _schwaerz_lauf(self, auftraege):
        gesamt, letzte_ausgabe = 0, None
        for i, (pdf, funde) in enumerate(auftraege, 1):
            try:
                ergebnis = schwaerze_pdf(pdf, funde,
                                         melde=lambda t: self._log(t, "grau"))
            except Exception:
                self._log(f"✖ {pdf.name}: Unerwarteter Fehler (siehe fehler.log)", "fehler")
                _unbehandelter_fehler(*sys.exc_info())
                self._fortschritt_setzen(i)
                continue
            gesamt += ergebnis["treffer"]
            if ergebnis["ausgabe"]:
                letzte_ausgabe = ergebnis["ausgabe"].parent
                self._log(f"✔ {pdf.name}: {ergebnis['treffer']} Stelle(n) ersetzt "
                          f"→ {ergebnis['ausgabe'].name}", "ok")
            for w in ergebnis["warnungen"]:
                self._log(f"⚠ {pdf.name}: {w}", "warnung")
            self._fortschritt_setzen(i)
        self._log("")
        self._log(f"Fertig: {gesamt} Stelle(n) ersetzt. Ergebnisse liegen im "
                  f"Unterordner \"anonymisiert\".", "ok")
        self._log("Bitte Ergebnis stichprobenartig öffnen und prüfen, bevor es "
                  "an einen KI-Dienst geht!", "warnung")
        self.root.after(0, self._schwaerzen_fertig)

    def _schwaerzen_fertig(self):
        self.laeuft = False
        self.start_knopf.config(state="normal", text="  2. Schwärzen starten  ")

    # Protokoll-Helfer (thread-sicher) ----------------------------------
    def _log(self, text, stil=None):
        def einfuegen():
            self.protokoll.config(state="normal")
            self.protokoll.insert("end", text + "\n", stil)
            self.protokoll.see("end")
            self.protokoll.config(state="disabled")
        self.root.after(0, einfuegen)

    def _protokoll_leeren(self):
        self.protokoll.config(state="normal")
        self.protokoll.delete("1.0", "end")
        self.protokoll.config(state="disabled")

    def _fortschritt_setzen(self, wert):
        self.root.after(0, lambda: self.fortschritt.config(value=wert))


def main():
    root = TkinterDnD.Tk() if DND_VERFUEGBAR else tk.Tk()
    AnonymisiererApp(root)
    root.mainloop()
