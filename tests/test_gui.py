"""GUI-Tests (tkinter unter Xvfb). Ohne Display werden alle Tests übersprungen.

Die Engine (analysiere_pdf, schwaerze_pdf, OcrDienst) wird durch Fakes ersetzt, die Ergebnisse in der
Vertragsform liefern – je eine Attrappe mit der Signatur aus Phase 1 (heutige Engine) und aus Phase 2
(CONTRACT_V2: Schutzstufe, Kundenliste, Seitenmodell, manuelle Bereiche, Freigabe, Meldungs-Codes).
Ein Test läuft zusätzlich mit der echten Engine. Screenshots landen in $PDF_ANONYMISIERER_SCREENSHOTS oder
im pytest-Temp-Ordner (nicht im Repo).
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import fitz
import pytest

from anonymisierer import __version__, dateien, gui
from anonymisierer import gui_attrappen as attrappen
from anonymisierer import schwaerzung

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY") and sys.platform != "win32",
                                reason="kein Display (DISPLAY nicht gesetzt)")

TEXT = ("Allianz Lebensversicherungs-AG\nSehr geehrter Herr Max Mustermann,\n"
        "Versicherungsschein-Nr.: LV-2024-887766\nIBAN: DE89 3704 0044 0532 0130 00\n"
        "geb. am 02.09.1983\nHauptstraße 12a, 90402 Nürnberg\n"
        "Tel. 0171 2345678, E-Mail max.mustermann@example.de\n")

FUND_TEL = {"kategorie": "telefon", "anzeige": "Telefonnummern", "text": "0171 2345678", "ersatz": "[TELEFON]",
            "seiten": [1], "anzahl": 1, "kontext": "Tel. »0171 2345678«, E-Mail"}
FUND_MAIL = {"kategorie": "email", "anzeige": "E-Mail-Adressen", "text": "max.mustermann@example.de",
             "ersatz": "[E-MAIL]", "seiten": [1], "anzahl": 1, "kontext": "E-Mail »max.mustermann@example.de«"}
FUND_NAME = {"kategorie": "namen", "anzeige": "Name", "text": "Max Mustermann", "ersatz": "[PERSON A]",
             "seiten": [1], "anzahl": 1, "kontext": "Herr »Max Mustermann«,"}
FUND_BEGRIFF = {"kategorie": "begriff", "anzeige": "Begriff (IMMER-Liste)", "text": "Allianz", "ersatz": "[BEGRIFF]",
                "seiten": [1], "anzahl": 1, "kontext": "»Allianz« Lebensversicherungs-AG"}
OCR_CACHE = {0: [(10.0, 10.0, 50.0, 20.0, "Wort")]}


class Verdacht(NamedTuple):
    """Wie restrisiko.Verdacht (Vertrag Abschnitt 7)."""
    seite: int
    start: int
    ende: int
    text: str
    grund: str
    rechtecke: list


# ----------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------
def pdf_schreiben(pfad: Path, text: str = TEXT, seiten: int = 1) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for _ in range(seiten):
        doc.new_page().insert_text((40, 60), text, fontsize=9, fontname="helv")
    doc.save(pfad)
    doc.close()
    return pfad


def ergebnis_mit(pdf: Path, funde, seiten=2, **mehr) -> dict:
    """Vollständiges Analyse-Ergebnis (Vertragsform) für Tests, die den Baum direkt füllen."""
    e = {"datei": pdf, "funde": [dict(f) for f in funde], "warnungen": [], "hinweise": [], "fehler": None,
         "seiten": seiten, "ocr_seiten": 0, "ocr_cache": {}}
    e.update(mehr)
    return e


def fenster_existiert(root) -> bool:
    try:
        return bool(root.winfo_exists())
    except tk.TclError:
        return False


def pumpe(root, bedingung=None, timeout=20.0) -> bool:
    """Treibt die Tk-Ereignisschleife, bis die Bedingung gilt (oder Zeit abgelaufen ist)."""
    ende = time.time() + timeout
    while True:
        root.update()
        if bedingung is None or bedingung():
            return True
        if time.time() > ende:
            return False
        time.sleep(0.01)


def zellenbox(app, eintrag, spalte, timeout=3.0):
    """Liefert die Zellenbox (x, y, b, h) eines sichtbaren Baumeintrags; wartet, bis Tk sie gezeichnet hat
    (unter Windows ist die Box direkt nach dem Einfügen noch leer)."""
    root = app.root
    app.baum.see(eintrag)
    ende = time.time() + timeout
    while True:
        root.update()
        box = app.baum.bbox(eintrag, spalte)
        if box:
            return box
        if time.time() > ende:
            raise AssertionError(f"Zellenbox von {eintrag!r}/{spalte} bleibt leer")
        time.sleep(0.02)


def starte_lauf(app, aktion, timeout=30.0):
    """Startet einen Lauf (aktion = app.analysieren / app.schwaerzen) und wartet auf sein Ende."""
    vorher = app.laeufe_beendet
    aktion()
    assert app.laeuft, "Lauf ist nicht gestartet"
    assert pumpe(app.root, lambda: app.laeufe_beendet > vorher, timeout=timeout), "Lauf ist nicht fertig geworden"
    pumpe(app.root, timeout=0.05)   # letzte after()-Aufrufe abarbeiten


class FakeOcr:
    """Ersatz für OcrDienst: zählt abbrechen()/schliessen()."""
    instanzen: list = []

    def __init__(self, prozesse=None):
        self.abgebrochen = False
        self.geschlossen = False
        FakeOcr.instanzen.append(self)

    def abbrechen(self):
        self.abgebrochen = True

    def schliessen(self):
        self.geschlossen = True


def fake_analyse(funde_je_datei: dict, seiten=2, pause=0.0, warten: threading.Event | None = None,
                 fehler: Exception | None = None, warnungen_je_datei: dict | None = None,
                 aufrufe: list | None = None, fehler_fuer: dict | None = None):
    """analysiere_pdf-Attrappe mit der Signatur aus Phase 1 (heutige Engine)."""
    def analysiere_pdf(pdf_pfad, aktive, whitelist, immer_schwaerzen, melde=None, fortschritt=None,
                       abbruch=None, ocr=None):
        if aufrufe is not None:
            aufrufe.append({"pdf": pdf_pfad, "aktive": set(aktive), "nie": list(whitelist),
                            "immer": list(immer_schwaerzen), "abbruch": abbruch, "ocr": ocr})
        if fehler is not None:
            raise fehler
        if fehler_fuer and pdf_pfad.name in fehler_fuer:
            raise fehler_fuer[pdf_pfad.name]
        ergebnis = {"datei": pdf_pfad, "funde": [], "warnungen": [], "hinweise": [], "fehler": None,
                    "seiten": seiten, "ocr_seiten": 0, "ocr_cache": dict(OCR_CACHE)}
        for s in range(1, seiten + 1):
            if warten is not None:
                warten.wait(10)
            if abbruch is not None and abbruch.is_set():
                ergebnis["fehler"] = "Abgebrochen"
                return ergebnis
            if pause:
                time.sleep(pause)
            if fortschritt:
                fortschritt(s, seiten)
        schluessel = f"{pdf_pfad.parent.name}/{pdf_pfad.name}"
        funde = funde_je_datei.get(schluessel, funde_je_datei.get(pdf_pfad.name, []))
        ergebnis["funde"] = [dict(f) for f in funde]
        ergebnis["warnungen"] = list((warnungen_je_datei or {}).get(pdf_pfad.name, []))
        if melde:
            melde(f"   {pdf_pfad.name} gelesen")
        return ergebnis
    return analysiere_pdf


def stellen_berechnen(pdf: Path, fund: dict) -> list[dict]:
    """Fundstellen (Vertrag Abschnitt 2) im Seitenmodell der Attrappe – so passen sie zur Attrappen-Vorschau."""
    stellen = []
    with fitz.open(pdf) as doc:
        anzahl = len(doc)
    for nr in range(anzahl):
        text = attrappen.seiten_modell(pdf, nr)["text"]
        suche, start = fund["text"].lower(), 0
        while True:
            pos = text.lower().find(suche, start)
            if pos < 0:
                break
            stellen.append({"seite": nr, "start": pos, "ende": pos + len(suche), "an": True})
            start = pos + 1
    return stellen


def fake_analyse_neu(funde_je_datei: dict, aufrufe: list | None = None, modell=False, mit_stellen=False,
                     meldungen_je_datei: dict | None = None, warnungen_je_datei: dict | None = None, seiten=1):
    """analysiere_pdf-Attrappe mit der Signatur aus Phase 2 (profil, kundenliste, lauf)."""
    def analysiere_pdf(pdf_pfad, aktive, whitelist, immer_schwaerzen, melde=None, fortschritt=None,
                       abbruch=None, ocr=None, profil="hoch", kundenliste=None, lauf=None):
        if aufrufe is not None:
            aufrufe.append({"pdf": pdf_pfad, "aktive": set(aktive), "immer": list(immer_schwaerzen),
                            "profil": profil, "kundenliste": kundenliste, "lauf": lauf, "abbruch": abbruch})
        if fortschritt:
            fortschritt(1, seiten)
        funde = []
        for i, f in enumerate(funde_je_datei.get(pdf_pfad.name, [])):
            f = dict(f, id=f"f{i + 1}")
            if mit_stellen:
                f["stellen"] = stellen_berechnen(pdf_pfad, f)
                f["anzahl"] = len(f["stellen"])
            funde.append(f)
        for begriff in immer_schwaerzen:
            if begriff.lower() in TEXT.lower():
                funde.append({"id": f"b{len(funde) + 1}", "kategorie": "begriff", "anzeige": "Begriff (IMMER-Liste)",
                              "text": begriff, "ersatz": "[BEGRIFF]", "seiten": [1], "anzahl": 1, "kontext": ""})
        ergebnis = {"datei": pdf_pfad, "funde": funde, "warnungen": list((warnungen_je_datei or {}).get(
                    pdf_pfad.name, [])), "hinweise": [], "fehler": None, "seiten": seiten, "ocr_seiten": 0,
                    "ocr_cache": {}, "profil": profil}
        if modell:
            ergebnis["modell"] = SimpleNamespace(pfad=pdf_pfad, fingerabdruck="x")
        if meldungen_je_datei is not None:
            ergebnis["meldungen"] = list(meldungen_je_datei.get(pdf_pfad.name, []))
        return ergebnis
    return analysiere_pdf


def _freie_ausgabe(ordner: Path, pruefen: bool) -> Path:
    n = 1
    while (ordner / f"anonym_{n:02d}.pdf").exists() or (ordner / f"anonym_{n:02d}_PRUEFEN.pdf").exists():
        n += 1
    return ordner / (f"anonym_{n:02d}_PRUEFEN.pdf" if pruefen else f"anonym_{n:02d}.pdf")


def fake_schwaerzung(aufrufe: list, treffer_null=(), fehler_fuer: dict | None = None, reste_fuer: dict | None = None,
                     fehlertext_fuer: dict | None = None):
    """schwaerze_pdf-Attrappe mit der Signatur aus Phase 1: kopiert das PDF als anonym_NN.pdf in den Zielordner."""
    def schwaerze_pdf(pdf_pfad, funde, melde=None, fortschritt=None, abbruch=None, ocr=None,
                      ocr_cache=None, ziel_ordner=None):
        aufrufe.append({"pdf": pdf_pfad, "texte": [f["text"] for f in funde], "ocr_cache": ocr_cache,
                        "ziel_ordner": ziel_ordner, "ocr": ocr})
        if fehler_fuer and pdf_pfad.name in fehler_fuer:
            raise fehler_fuer[pdf_pfad.name]
        if fortschritt:
            fortschritt(1, 1)
        ergebnis = {"original": pdf_pfad, "ausgabe": None, "treffer": 0, "uebersprungen": 0,
                    "warnungen": [], "hinweise": [], "reste": [], "fehler": None}
        if fehlertext_fuer and pdf_pfad.name in fehlertext_fuer:
            ergebnis["fehler"] = fehlertext_fuer[pdf_pfad.name]
            return ergebnis
        if pdf_pfad.name in treffer_null:
            ergebnis["warnungen"].append(schwaerzung.WARNUNG_KEIN_TREFFER)
            return ergebnis
        ordner = Path(ziel_ordner) if ziel_ordner else pdf_pfad.parent / "anonymisiert"
        ordner.mkdir(parents=True, exist_ok=True)
        reste = list((reste_fuer or {}).get(pdf_pfad.name, []))
        ausgabe = _freie_ausgabe(ordner, bool(reste))
        shutil.copy(pdf_pfad, ausgabe)
        with open(ordner / "_zuordnung.txt", "a", encoding="utf-8") as f:
            f.write(f"{ausgabe.name}  <-  {pdf_pfad.name}  (2026-01-01 10:00)\n")
        ergebnis.update(ausgabe=ausgabe, treffer=len(funde), reste=reste)
        if reste:
            ergebnis["warnungen"].append(f"'{reste[0]}' ist noch auffindbar – bitte manuell prüfen!")
        return ergebnis
    return schwaerze_pdf


def fake_schwaerzung_neu(aufrufe: list, verdacht_fuer: dict | None = None, meldungen: list | None = None,
                         treffer_null=(), warnung_bei_null: str | None = None):
    """schwaerze_pdf-Attrappe mit der Signatur aus Phase 2 (modell, manuelle_bereiche, manuelle_stellen,
    freigabe_erforderlich, profil); liefert status/verdacht/meldungen."""
    def schwaerze_pdf(pdf_pfad, funde, melde=None, fortschritt=None, abbruch=None, ocr=None, ocr_cache=None,
                      ziel_ordner=None, modell=None, manuelle_bereiche=None, manuelle_stellen=None,
                      freigabe_erforderlich=False, profil="hoch"):
        aufrufe.append({"pdf": pdf_pfad, "funde": [dict(f) for f in funde], "modell": modell,
                        "manuelle_bereiche": manuelle_bereiche, "manuelle_stellen": manuelle_stellen,
                        "freigabe_erforderlich": freigabe_erforderlich, "profil": profil, "ziel_ordner": ziel_ordner})
        if fortschritt:
            fortschritt(1, 1)
        ergebnis = {"original": pdf_pfad, "ausgabe": None, "treffer": 0, "uebersprungen": 0, "warnungen": [],
                    "hinweise": [], "reste": [], "fehler": None, "verdacht": [], "status": "fertig",
                    "stellen_geschwaerzt": 0, "stellen_nicht_lokalisiert": 0}
        if meldungen is not None:
            ergebnis["meldungen"] = list(meldungen)
        if pdf_pfad.name in treffer_null:
            if warnung_bei_null:
                ergebnis["warnungen"].append(warnung_bei_null)
            return ergebnis
        verdacht = list((verdacht_fuer or {}).get(pdf_pfad.name, []))
        pruefen = bool(freigabe_erforderlich or verdacht)
        ordner = Path(ziel_ordner) if ziel_ordner else pdf_pfad.parent / "anonymisiert"
        ordner.mkdir(parents=True, exist_ok=True)
        ausgabe = _freie_ausgabe(ordner, pruefen)
        shutil.copy(pdf_pfad, ausgabe)
        with open(ordner / "_zuordnung.txt", "a", encoding="utf-8") as f:
            f.write(f"{ausgabe.name}  <-  {pdf_pfad.name}  (2026-01-01 10:00)\n")
        anzahl = len(funde) + sum(len(v) for v in (manuelle_bereiche or {}).values()) + \
            sum(len(v) for v in (manuelle_stellen or {}).values())
        ergebnis.update(ausgabe=ausgabe, treffer=anzahl, stellen_geschwaerzt=anzahl, verdacht=verdacht,
                        status="pruefen" if pruefen else "fertig")
        return ergebnis
    return schwaerze_pdf


class Dialoge:
    """Fängt alle messagebox-Aufrufe ab (würden sonst blockieren) und protokolliert sie."""

    def __init__(self):
        self.liste: list[tuple] = []
        self.antwort = False     # Antwort auf askyesno/askokcancel

    def _fang(self, art):
        kurz = {"showinfo": "info", "showwarning": "warning", "showerror": "error"}.get(art, art)

        def f(titel=None, nachricht=None, **kw):
            self.liste.append((kurz, titel, nachricht))
            return self.antwort if art.startswith("ask") else "ok"
        return f

    def arten(self):
        return [d[0] for d in self.liste]

    def texte(self):
        return "\n".join(f"{t}\n{n}" for _, t, n in self.liste)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _prozesszustand(monkeypatch, tmp_path):
    """KQ-10: fehler.log nie in die Projektwurzel, threading.excepthook nach jedem Test zurück."""
    monkeypatch.setattr(dateien, "fehlerlog_pfad", lambda: tmp_path / "log" / "fehler.log")
    haken = threading.excepthook
    yield
    threading.excepthook = haken


@pytest.fixture
def dialoge(monkeypatch):
    d = Dialoge()
    for art in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel"):
        monkeypatch.setattr(gui.messagebox, art, d._fang(art))
    return d


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as fehler:
        pytest.skip(f"Tk kann kein Fenster öffnen: {fehler}")
    r.tk.willdispatch()      # Tests treiben Tk per update(); after() aus Threads braucht diesen Hinweis
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def umgebung(monkeypatch, tmp_path):
    """Einstellungen und Fehlerprotokoll in den Temp-Ordner, OCR-Dienst als Attrappe, kein echtes Ordner-Öffnen."""
    FakeOcr.instanzen.clear()
    monkeypatch.setattr(dateien, "einstellungen_pfad", lambda: tmp_path / "konfig" / "einstellungen.json")
    monkeypatch.setattr(dateien, "fehlerlog_pfad", lambda: tmp_path / "log" / "fehler.log")
    monkeypatch.setattr(gui, "OcrDienst", FakeOcr)
    geoeffnet = []
    monkeypatch.setattr(dateien, "oeffne_ordner", lambda p: geoeffnet.append(Path(p)) or True)
    attrappen.cache_leeren()
    return {"tmp": tmp_path, "geoeffnet": geoeffnet, "fehlerlog": tmp_path / "log" / "fehler.log"}


@pytest.fixture
def app(root, umgebung, dialoge):
    a = gui.AnonymisiererApp(root, einstellungen={})
    root.update()
    return a


def analysiere(app, pfade):
    app._pdfs_hinzufuegen([str(p) for p in pfade])
    starte_lauf(app, app.analysieren)


# ----------------------------------------------------------------------
# M-01: gleiche Dateinamen in verschiedenen Ordnern (+ Freigabe-Standard)
# ----------------------------------------------------------------------
def test_gleiche_dateinamen_in_zwei_ordnern_bekommen_je_eine_ausgabe(app, umgebung, monkeypatch, dialoge):
    """Mit der Phase-1-Signatur der Engine; „Freigabe erforderlich“ ist Standard (Vertrag 10): die Oberfläche
    markiert die Ausgaben deshalb selbst als _PRUEFEN (früher: anonym_01.pdf)."""
    tmp = umgebung["tmp"]
    a = pdf_schreiben(tmp / "KundeA" / "Police.pdf")
    b = pdf_schreiben(tmp / "KundeB" / "Police.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({
        "KundeA/Police.pdf": [FUND_NAME, FUND_TEL, FUND_MAIL],
        "KundeB/Police.pdf": [FUND_TEL]}))
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung(aufrufe))

    analysiere(app, [tmp])
    # Baumzeilen sind an den Pfad gebunden und zeigen den Ordner relativ zum Stamm
    assert set(app.baum.get_children("")) == {str(a), str(b)}
    assert app.beschriftungen[str(a)] == "KundeA/Police.pdf"
    assert app.beschriftungen[str(b)] == "KundeB/Police.pdf"
    assert app.baum.get_children(str(a)) == (f"{a}::0", f"{a}::1", f"{a}::2")
    assert app.baum.item(f"{a}::0", "values")[0] == "Name"
    assert "an" in app.baum.item(f"{a}::0", "tags")

    # In Datei A den zweiten Fund (Telefon) abwählen – B bleibt unberührt
    app._umschalten(f"{a}::1")
    assert app._zustand(f"{a}::1") == "aus" and app._zustand(str(a)) == "teil"
    assert app._zustand(f"{b}::0") == "an"

    starte_lauf(app, app.schwaerzen)
    assert [(c["pdf"], c["texte"]) for c in aufrufe] == [
        (a, ["Max Mustermann", "max.mustermann@example.de"]),
        (b, ["0171 2345678"])]
    ausgabe_a = tmp / "KundeA" / "anonymisiert" / "anonym_01_PRUEFEN.pdf"
    assert ausgabe_a.exists() and (tmp / "KundeB" / "anonymisiert" / "anonym_01_PRUEFEN.pdf").exists()
    assert not (tmp / "KundeA" / "anonymisiert" / "anonym_01.pdf").exists()
    assert "anonym_01_PRUEFEN.pdf  <-  Police.pdf" in (tmp / "KundeA" / "anonymisiert" / "_zuordnung.txt").read_text(
        encoding="utf-8")
    # ocr_cache aus der Analyse und ein OcrDienst je Lauf werden durchgereicht, danach geschlossen
    assert aufrufe[0]["ocr_cache"] == OCR_CACHE
    assert isinstance(aufrufe[0]["ocr"], FakeOcr) and aufrufe[0]["ocr"] is aufrufe[1]["ocr"]
    assert all(o.geschlossen for o in FakeOcr.instanzen) and len(FakeOcr.instanzen) == 2
    protokoll = app.protokoll_text()
    assert "2 von 2 Datei(en) geschrieben" in protokoll
    assert f"KundeA/Police.pdf  →  {ausgabe_a}" in protokoll
    assert sorted(app.letzte_ausgabeordner) == sorted([tmp / "KundeA" / "anonymisiert", tmp / "KundeB" / "anonymisiert"])
    # Ergebnisliste je Datei: Status „prüfen“ in der Dateizeile
    assert app.ausgaben[a]["status"] == "pruefen" and app.ausgaben[a]["pfad"] == ausgabe_a
    assert app.baum.set(str(a), "text") == "⚠ prüfen: anonym_01_PRUEFEN.pdf"
    # Abschlussdialog erklärt _PRUEFEN in einem Satz und bietet die Vorschau der ersten Datei an
    art, titel, text = dialoge.liste[-1]
    assert art == "askyesno" and "2 von 2" in text
    assert gui.PRUEFEN_ERKLAERUNG in text and "Vorschau von „KundeA/Police.pdf“ jetzt öffnen" in text


def test_gemeinsamer_zielordner_wird_uebergeben(app, umgebung, monkeypatch):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "in" / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL]}))
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung(aufrufe))
    app.zielordner_aktiv.set(True)
    app.zielordner_var.set(str(tmp / "ziel"))
    analysiere(app, [pdf])
    starte_lauf(app, app.schwaerzen)
    assert aufrufe[0]["ziel_ordner"] == tmp / "ziel"
    assert (tmp / "ziel" / "anonym_01_PRUEFEN.pdf").exists()
    assert app.letzte_ausgabeordner == [tmp / "ziel"]


# ----------------------------------------------------------------------
# M-05 / GR-01 / GR-02 / GR-06: Layout auf verschiedenen Bildschirmen und Skalierungen
# ----------------------------------------------------------------------
_XVFB_PROZESSE: list = []


def _display_wiederherstellen(display_vorher):
    """Tk setzt beim Öffnen mit screenName die Umgebungsvariable DISPLAY prozessweit um (Tcl-env-Verknüpfung);
    ohne Rücksetzen landen alle späteren Fenster auf dem anderen Display."""
    if display_vorher:
        os.environ["DISPLAY"] = display_vorher


def _display_groesse(name):
    display_vorher = os.environ.get("DISPLAY")
    try:
        probe = tk.Tk(screenName=name)
        groesse = (probe.winfo_screenwidth(), probe.winfo_screenheight())
        probe.destroy()
        return groesse
    except tk.TclError:
        return None
    finally:
        _display_wiederherstellen(display_vorher)


@pytest.fixture(scope="session")
def display_1366():
    """Name eines 1366x768-Displays (startet bei Bedarf Xvfb :98) oder None. Ein selbst gestartetes Xvfb
    wird am Ende der Sitzung wieder beendet (KQ-10)."""
    if sys.platform == "win32":
        yield None
        return
    groesse = _display_groesse(":98")
    if groesse is None and shutil.which("Xvfb"):
        prozess = subprocess.Popen(["Xvfb", ":98", "-screen", "0", "1366x768x24"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _XVFB_PROZESSE.append(prozess)
        for _ in range(30):
            time.sleep(0.1)
            groesse = _display_groesse(":98")
            if groesse:
                break
    yield ":98" if groesse == (1366, 768) else None
    while _XVFB_PROZESSE:
        prozess = _XVFB_PROZESSE.pop()
        prozess.terminate()
        try:
            prozess.wait(5)
        except subprocess.TimeoutExpired:
            prozess.kill()


def _screenshot_ordner(tmp_path_factory) -> Path:
    ordner = Path(os.environ.get("PDF_ANONYMISIERER_SCREENSHOTS")
                  or tmp_path_factory.getbasetemp() / "screenshots")
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def _beispielfunde_eintragen(app, anzahl=12):
    pdf = Path(tempfile.gettempdir()) / "Kunden" / "Beispiel_Versicherungsschein.pdf"
    app.dateien.append(pdf)
    app._datei_zeile_einfuegen(pdf)
    app._beschriftungen_aktualisieren()
    funde = [FUND_NAME, FUND_TEL, FUND_MAIL, FUND_BEGRIFF]
    funde += [dict(FUND_NAME, text=f"Person {i}", ersatz=f"[PERSON {chr(66 + i % 24)}]",
                   kontext=f"Sehr geehrte Frau Doktor »Person {i}« wohnt in") for i in range(anzahl - len(funde))]
    ergebnis = ergebnis_mit(pdf, funde)
    app.analyse_ergebnisse[pdf] = ergebnis
    app._baum_datei_fuellen(pdf, ergebnis)
    app._log("Analyse fertig: 12 Fund(e) in 1 Datei(en). Bitte Liste prüfen, dann schwärzen.", "ok")
    app._log("⚠ Beispiel.pdf: 1 Seite(n) per OCR gelesen – Ergebnis bitte besonders sorgfältig prüfen!", "warnung")
    app._start_knopf_aktualisieren()
    return pdf


def _sichtbare_zeilen(app) -> int:
    """Zahl der vollständig sichtbaren Fundzeilen im Baum."""
    hoehe = app.baum.winfo_height()
    zeilen = 0
    for datei in app.baum.get_children(""):
        for kind in app.baum.get_children(datei):
            box = app.baum.bbox(kind)
            if box and box[1] >= 0 and box[1] + box[3] <= hoehe:
                zeilen += 1
    return zeilen


@pytest.mark.parametrize("anzeige", ["standard", "1366x768"])
@pytest.mark.parametrize("skalierung", [1.3333, 1.6667, 2.0])
def test_layout_hauptknoepfe_protokoll_und_fundliste_sichtbar(anzeige, skalierung, umgebung, dialoge,
                                                                tmp_path_factory, display_1366):
    """GR-01: Analysieren und Schwärzen liegen beide in der unten verankerten Leiste und sind auf jedem
    Bildschirm ohne Scrollen sichtbar; GR-02: die Fundliste bekommt den größeren Teil (FHD/100 %: >= 5 Zeilen);
    GR-06: die Statuszeile hat die volle Leistenbreite."""
    display = None
    display_vorher = os.environ.get("DISPLAY")
    if anzeige == "1366x768":
        display = display_1366
        if display is None:
            pytest.skip("kein 1366x768-Display (Xvfb :98) verfügbar")
    try:
        root = tk.Tk(screenName=display) if display else tk.Tk()
    except tk.TclError as fehler:
        pytest.skip(f"Tk kann kein Fenster öffnen: {fehler}")
    # „tk scaling“ gilt je Display für alle Tk-Instanzen des Prozesses: danach zurücksetzen (KQ-10)
    skalierung_vorher = float(root.tk.call("tk", "scaling"))
    try:
        root.tk.willdispatch()
        root.tk.call("tk", "scaling", skalierung)
        app = gui.AnonymisiererApp(root, einstellungen={})
        _beispielfunde_eintragen(app)
        pumpe(root, timeout=0.4)
        root.update_idletasks()
        root.update()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        fenster_h, fenster_w = root.winfo_height(), root.winfo_width()
        assert fenster_w <= sw and fenster_h <= sh - 60, "Fenster passt nicht auf den Bildschirm"
        assert root.minsize() == gui.FENSTER_MINDESTMASS

        def lage(w):
            y0 = w.winfo_rooty() - root.winfo_rooty()
            return y0, y0 + w.winfo_height()

        for name, w in (("Analysieren-Knopf", app.analyse_knopf), ("Schwärzen-Knopf", app.start_knopf),
                        ("Abbrechen-Knopf", app.abbrechen_knopf), ("Fortschritt", app.fortschritt),
                        ("Statuszeile", app.status_label), ("Protokoll", app.protokoll),
                        ("Fundliste", app.baum), ("Hinweiskasten", app.hinweis_kasten),
                        ("Drop-Zone", app.drop_zone)):
            assert w.winfo_ismapped(), f"{name} nicht sichtbar"
            oben, unten = lage(w)
            assert 0 <= oben and unten <= fenster_h, f"{name} ragt aus dem Fenster ({oben}..{unten} von {fenster_h})"
        # beide Hauptknöpfe sitzen in der Aktionsleiste, nicht im scrollbaren Einstellbereich
        for knopf in (app.analyse_knopf, app.start_knopf):
            assert str(knopf).startswith(str(app.aktionsleiste)), "Hauptknopf nicht in der Aktionsleiste"
        assert app.start_knopf.winfo_height() >= 20 and app.analyse_knopf.winfo_height() >= 20
        mono = tkfont.Font(family=gui.SCHRIFT_MONO, size=9)
        assert app.protokoll.winfo_height() >= 3 * mono.metrics("linespace"), "Protokoll zu niedrig"
        assert app.baum.winfo_height() >= 2 * max(20, app.zeilenhoehe + 6), "Fundliste zu niedrig"
        # Statuszeile über die volle Leistenbreite (GR-06)
        assert app.status_label.winfo_width() >= 0.9 * (app.aktionsleiste.winfo_width() - 30)
        # Zeilenhöhe folgt der Schrift
        rowheight = int(ttk_style_lookup(root, "Treeview", "rowheight"))
        assert rowheight >= app.zeilenhoehe + 4
        # Protokoll: letzte Zeile sichtbar (nicht auf eine leere Schlusszeile gesprungen)
        assert app.protokoll.get("end-2l", "end-1c").strip().startswith("⚠")
        if anzeige == "standard" and skalierung == 1.3333 and sh >= 1080:   # nur auf echtem FHD-Schirm
            zeilen = _sichtbare_zeilen(app)
            assert zeilen >= 5, f"Fundliste zeigt bei FHD/100 % nur {zeilen} Fundzeilen"
        _screenshot(root, display, _screenshot_ordner(tmp_path_factory) / f"layout_{anzeige}_{skalierung}.png")
    finally:
        try:
            root.tk.call("tk", "scaling", skalierung_vorher)
            root.destroy()
        except tk.TclError:
            pass
        _display_wiederherstellen(display_vorher)


def ttk_style_lookup(root, stil, option):
    from tkinter import ttk
    return ttk.Style(root).lookup(stil, option)


def _screenshot(root, display, ziel: Path):
    if not shutil.which("scrot"):
        return
    root.update_idletasks()
    root.update()
    umgebung = dict(os.environ)
    if display:
        umgebung["DISPLAY"] = display
    try:
        subprocess.run(["scrot", "-o", str(ziel)], env=umgebung, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def test_statuszeile_kuerzt_lange_pfade_in_der_mitte(app):
    """GR-06: ein langer Pfad wird in der Mitte gekürzt, der Dateiname bleibt sichtbar."""
    app.root.update()
    lang = Path("/") / "/".join(f"Ordner_mit_langem_Namen_{i}" for i in range(12)) / "Police_Mustermann_LV-2024.pdf"
    text = app._pfad_passend(lang)
    assert text.endswith("Police_Mustermann_LV-2024.pdf") and "…" in text
    assert app.f_normal.measure(text) <= app.status_label.winfo_width()
    kurz = Path("/tmp/a.pdf")
    assert app._pfad_passend(kurz) == str(kurz)


# ----------------------------------------------------------------------
# M-54: Klickverhalten in der Fundliste
# ----------------------------------------------------------------------
_KLICK_ZEIT = [10_000]


def klick(widget, x, y, anzahl=1):
    """Klickfolge (Drücken + Loslassen) mit Zeitstempeln: Einzelklicks liegen 1 s auseinander,
    anzahl=2 erzeugt einen echten Doppelklick (50 ms Abstand), den Tk als <Double-Button-1> meldet."""
    _KLICK_ZEIT[0] += 1000
    for i in range(anzahl):
        zeit = _KLICK_ZEIT[0] + i * 50
        widget.event_generate("<Button-1>", x=x, y=y, time=zeit)
        widget.event_generate("<ButtonRelease-1>", x=x, y=y, time=zeit + 10)
    widget.update()


def test_einfachklick_schaltet_doppelklick_auf_kopf_und_dreieck_nicht(app, umgebung, monkeypatch):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_NAME, FUND_TEL, FUND_MAIL]}))
    analysiere(app, [pdf])
    root = app.root
    root.update_idletasks()
    eltern = str(pdf)
    kinder = app.baum.get_children(eltern)

    # Einfachklick in die Häkchen-Spalte eines Funds schaltet genau diesen Fund um
    x, y, b, h = zellenbox(app, kinder[1], "#0")
    klick(app.baum, x + b // 2, y + h // 2)
    assert app._zustand(kinder[1]) == "aus" and app._zustand(kinder[0]) == "an"
    assert app._zustand(eltern) == "teil"
    assert app.baum.item(kinder[1], "text") == gui.HAKEN["aus"]

    # Klick in eine andere Spalte (Gefundener Text) schaltet nichts
    x2, y2, b2, h2 = zellenbox(app, kinder[0], "text")
    klick(app.baum, x2 + 5, y2 + h2 // 2)
    assert app._zustand(kinder[0]) == "an"

    # Doppelklick auf die Kopfzeile: nichts ändert sich
    app.baum.focus(kinder[0])
    klick(app.baum, 30, 5, anzahl=2)
    assert [app._zustand(k) for k in kinder] == ["an", "aus", "an"]

    # Doppelklick auf den Dateinamen: wählt die Datei aus, klappt nichts zu, schaltet nichts – öffnet die Vorschau
    xe, ye, be, he = zellenbox(app, eltern, "#0")
    klick(app.baum, xe + be - 10, ye + he // 2, anzahl=2)
    assert app.baum.item(eltern, "open") in (True, 1, "true")
    assert [app._zustand(k) for k in kinder] == ["an", "aus", "an"]
    assert app.baum.selection() == (eltern,)
    assert str(pdf) in app.status_label.cget("text")
    pumpe(root, lambda: pdf in app.vorschauen, timeout=3)
    assert pdf in app.vorschauen and app.vorschauen[pdf].modus == "vorher"

    # Einfachklick auf das Häkchen der Dateizeile schaltet alle Funde der Datei
    klick(app.baum, xe + app._px(20) + 10, ye + he // 2)
    assert [app._zustand(k) for k in kinder] == ["an", "an", "an"] and app._zustand(eltern) == "an"

    # Klick auf das Dreieck der Dateizeile klappt zu, ohne Häkchen zu ändern
    klick(app.baum, xe + 8, ye + he // 2)
    assert [app._zustand(k) for k in kinder] == ["an", "an", "an"]

    # Leertaste schaltet die fokussierte Zeile; Dateizeile schaltet alle Kinder
    app.baum.item(eltern, open=True)
    app.baum.focus(kinder[1])
    app._taste_leer()
    assert app._zustand(kinder[1]) == "aus" and app._zustand(eltern) == "teil"
    app.baum.focus(eltern)
    app._taste_leer()
    assert [app._zustand(k) for k in kinder] == ["an", "an", "an"] and app._zustand(eltern) == "an"
    app._taste_leer()
    assert [app._zustand(k) for k in kinder] == ["aus", "aus", "aus"] and app._zustand(eltern) == "aus"
    assert str(app.start_knopf.cget("state")) == "disabled"
    # „alle an“ je Kategorie
    app.kategorie_setzen("Telefonnummern", "an")
    assert [app._zustand(k) for k in kinder] == ["aus", "an", "aus"] and app._zustand(eltern) == "teil"
    assert str(app.start_knopf.cget("state")) == "normal"
    app.alle_setzen("an")
    assert app._zustand(eltern) == "an"


def test_kontextspalte_zeigt_den_fund(app, umgebung):
    """GR-05: der Vorlauf vor dem Fund wird gekürzt, damit in der schmalen Spalte der Fund zu sehen ist; der
    vollständige Kontext steht nach Auswahl in der Statuszeile."""
    kontext = "Hamburger Straße 7 · 20007 Hamburg Frau Dr. »Ayşe Yılmaz-Schneider« Beraterin der Kanzlei"
    anzeige = gui._kontext_anzeige(kontext)
    assert anzeige.startswith("…") and anzeige.index("»") <= gui.KONTEXT_VORLAUF + 2
    assert gui._kontext_anzeige("Herr »Max«,") == "Herr »Max«,"
    pdf = _beispielfunde_eintragen(app)
    kind = f"{pdf}::0"
    assert app.baum.set(kind, "kontext") == gui._kontext_anzeige(FUND_NAME["kontext"])
    app.baum.selection_set(kind)
    app.root.update()
    assert "Kontext: Herr »Max Mustermann«," in app.status_label.cget("text")


# ----------------------------------------------------------------------
# M-34 / M-67: Sperre während des Laufs, Rücksetzen nach Änderung
# ----------------------------------------------------------------------
def test_eingaben_sind_waehrend_des_laufs_gesperrt(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    weiter = threading.Event()
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL]}, warten=weiter))
    app._pdfs_hinzufuegen([str(pdf)])
    app.analysieren()
    assert pumpe(app.root, lambda: app.laeuft, timeout=5)
    pumpe(app.root, timeout=0.2)
    assert str(app.analyse_knopf.cget("state")) == "disabled"
    assert str(app.start_knopf.cget("state")) == "disabled"
    assert str(app.abbrechen_knopf.cget("state")) == "normal"
    gesperrt = [w for w in app._sperrbar if str(w.cget("state")) != "disabled"]
    assert gesperrt == [], f"nicht gesperrt: {gesperrt}"
    assert str(app.immer_feld.cget("state")) == "disabled"
    assert str(app.kunden_entfernen_knopf.cget("state")) == "disabled"
    assert all(str(rb.cget("state")) == "disabled" for rb in app.profil_knoepfe.values())

    vorher = list(app.dateien)
    app._pdfs_hinzufuegen([str(pdf_schreiben(tmp / "b.pdf"))])
    app.liste_leeren()
    app.datei_entfernen(str(pdf))
    app.analysieren()
    app.schwaerzen()
    app.kundenliste_importieren(tmp / "x.csv")
    assert app.dateien == vorher
    assert dialoge.liste and all(a == "info" and "läuft noch" in t for a, t, _ in dialoge.liste)
    app.kategorie_vars["iban"].set(False)           # während des Laufs: kein Zurücksetzen
    assert not app.analyse_veraltet

    vorher = app.laeufe_beendet
    weiter.set()
    assert pumpe(app.root, lambda: app.laeufe_beendet > vorher, timeout=30)
    pumpe(app.root, timeout=0.05)
    assert str(app.analyse_knopf.cget("state")) == "normal"
    assert all(str(w.cget("state")) == "normal" for w in app._sperrbar)
    assert str(app.start_knopf.cget("state")) == "normal"
    assert str(app.abbrechen_knopf.cget("state")) == "disabled"


def test_kategorie_oder_liste_geaendert_setzt_ergebnisse_zurueck(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL, FUND_MAIL]}))
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung(aufrufe))
    analysiere(app, [pdf])
    assert str(app.start_knopf.cget("state")) == "normal"

    app.kategorie_vars["kfz"].set(True)
    assert app.analyse_veraltet and app.analyse_ergebnisse == {}
    assert app.baum.get_children(str(pdf)) == ()
    assert app.baum.set(str(pdf), "kategorie") == "erneut analysieren"
    assert str(app.start_knopf.cget("state")) == "disabled"
    assert "erneut analysieren" in app.protokoll_text()
    app.schwaerzen()
    assert aufrufe == [] and dialoge.liste[-1][1] == "Erneut analysieren"

    # erneut analysieren, dann NIE-Liste tippen -> wieder veraltet
    starte_lauf(app, app.analysieren)
    assert not app.analyse_veraltet and str(app.start_knopf.cget("state")) == "normal"
    app.nie_feld.insert("end", "Musterfirma")
    pumpe(app.root, timeout=0.1)
    assert app.analyse_veraltet and str(app.start_knopf.cget("state")) == "disabled"

    # Schutzstufe gewechselt -> ebenfalls veraltet
    starte_lauf(app, app.analysieren)
    app.profil_var.set("maximal")
    app._profil_gewaehlt()
    assert app.analyse_veraltet

    # neue Datei nach der Analyse: Schwärzen verlangt erst eine Analyse der neuen Datei
    starte_lauf(app, app.analysieren)
    app._pdfs_hinzufuegen([str(pdf_schreiben(tmp / "b.pdf"))])
    app.schwaerzen()
    assert aufrufe == [] and dialoge.liste[-1][1] == "Erst analysieren"


# ----------------------------------------------------------------------
# M-10 / M-32 / KQ-03 / KQ-07: Ausnahmen und Vertragsprüfung
# ----------------------------------------------------------------------
def test_ausnahme_im_analyse_thread_gibt_oberflaeche_frei_und_schreibt_log(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({}, fehler=RuntimeError("Simulierter ABI-Fehler")))
    analysiere(app, [pdf])
    assert not app.laeuft
    assert str(app.analyse_knopf.cget("state")) == "normal"
    assert app.analyse_knopf.cget("text") == gui.ANALYSE_TEXT
    log = umgebung["fehlerlog"]
    assert log.exists() and "Simulierter ABI-Fehler" in log.read_text(encoding="utf-8")
    assert ("error", "Unerwarteter Fehler") in [(a, t) for a, t, _ in dialoge.liste]
    assert str(log) in dialoge.texte()
    assert "Unerwarteter Fehler" in app.protokoll_text()
    assert FakeOcr.instanzen and FakeOcr.instanzen[-1].geschlossen
    assert app.warnungen_anzahl >= 1 and "Warnung" in app.warn_label.cget("text")


def test_analyse_faengt_fehler_je_datei_und_macht_weiter(app, umgebung, monkeypatch, dialoge):
    """KQ-03: eine Ausnahme in einer Datei bricht den Lauf nicht ab; die anderen Dateien werden analysiert,
    der Fehler einmal gemeldet, die Datei als Fehler (nicht „abgebrochen“) beschriftet."""
    tmp = umgebung["tmp"]
    pdfs = [pdf_schreiben(tmp / f"{n}.pdf") for n in ("a", "b", "c")]
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse(
        {"a.pdf": [FUND_TEL], "c.pdf": [FUND_MAIL]}, fehler_fuer={"b.pdf": TypeError("'NoneType' object is not "
                                                                                    "subscriptable")}))
    analysiere(app, pdfs)
    assert set(app.analyse_ergebnisse) == set(pdfs)
    assert len(app.analyse_ergebnisse[pdfs[0]]["funde"]) == 1 and len(app.analyse_ergebnisse[pdfs[2]]["funde"]) == 1
    status_b = app.baum.set(str(pdfs[1]), "kategorie")
    assert status_b.startswith("Fehler: Unerwarteter Fehler (TypeError") and "abgebrochen" not in status_b
    assert sum(1 for a, t, _ in dialoge.liste if t == "Unerwarteter Fehler") == 1
    assert "TypeError" in umgebung["fehlerlog"].read_text(encoding="utf-8")
    assert str(app.start_knopf.cget("state")) == "normal"


def test_vertragsbruch_der_engine_wird_sichtbar_statt_null_funde(app, umgebung, monkeypatch, dialoge):
    """KQ-07: ein Ergebnis ohne „funde“ ist ein Fehler (fehler.log + Meldung), keine stille Entwarnung; ein
    umbenannter Pflichtparameter (abbruch) führt zu einem Fehler statt still verschluckt zu werden."""
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", lambda *a, **k: {"datei": pdf, "fund": [FUND_TEL], "warnungen": [],
                                                                "hinweise": [], "fehler": None, "seiten": 1,
                                                                "ocr_seiten": 0, "ocr_cache": {}})
    analysiere(app, [pdf])
    assert app.baum.set(str(pdf), "kategorie").startswith("Fehler: Unerwarteter Fehler (Vertragsfehler")
    assert "funde" in umgebung["fehlerlog"].read_text(encoding="utf-8")
    assert app.letzter_dialog[0] in ("warning", "error")

    def ohne_abbruch(pdf_pfad, aktive, whitelist, immer_schwaerzen, melde=None, fortschritt=None, stopp=None,
                     ocr=None):
        raise AssertionError("darf nicht still ohne abbruch aufgerufen werden")
    monkeypatch.setattr(gui, "analysiere_pdf", ohne_abbruch)
    starte_lauf(app, app.analysieren)
    assert app.baum.set(str(pdf), "kategorie").startswith("Fehler: Unerwarteter Fehler (TypeError")
    for name in ("_rufe", "_unterstuetzt", "_analyse_ergebnis_vervollstaendigen", "_schwaerz_ergebnis_vervollstaendigen"):
        assert not hasattr(gui, name), f"Adapter {name} sollte entfernt sein"


def test_abbruch_und_ocr_werden_direkt_uebergeben(app, umgebung, monkeypatch):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    aufrufe = []
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL]}, aufrufe=aufrufe))
    analysiere(app, [pdf])
    assert isinstance(aufrufe[0]["abbruch"], threading.Event) and isinstance(aufrufe[0]["ocr"], FakeOcr)


def test_tk_callback_fehler_landet_im_log(app, umgebung, dialoge):
    try:
        raise ValueError("Callback kaputt")
    except ValueError:
        app.root.report_callback_exception(*sys.exc_info())
    assert "Callback kaputt" in umgebung["fehlerlog"].read_text(encoding="utf-8")
    assert dialoge.liste[-1][0] == "error"


def test_schwaerz_lauf_meldet_schreibfehler_verstaendlich_und_prueft_ausgaben(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    a = pdf_schreiben(tmp / "a.pdf")
    b = pdf_schreiben(tmp / "b.pdf")
    c = pdf_schreiben(tmp / "c.pdf")
    d = pdf_schreiben(tmp / "d.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL], "b.pdf": [FUND_TEL],
                                                             "c.pdf": [FUND_TEL], "d.pdf": [FUND_MAIL]}))
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung(
        aufrufe, treffer_null=("b.pdf",),
        fehler_fuer={"c.pdf": PermissionError(13, "Permission denied", str(tmp / "anonymisiert" / "anonym_02.pdf"))},
        reste_fuer={"d.pdf": ["max.mustermann@example.de"]}))
    analysiere(app, [a, b, c, d])
    starte_lauf(app, app.schwaerzen)

    art, titel, text = app.letzter_dialog
    assert art == "askyesno" and titel == "Schwärzung abgeschlossen"
    assert "2 von 4 Datei(en) geschrieben" in text
    assert "b.pdf" in text and "lokalisiert" in text
    assert "c.pdf" in text and "anderen Programm" in text          # verständlich statt Traceback
    assert "_PRUEFEN" in text and "anonym_02_PRUEFEN.pdf" in text
    assert "PermissionError" in umgebung["fehlerlog"].read_text(encoding="utf-8")
    protokoll = app.protokoll_text()
    assert f"a.pdf  →  {tmp / 'anonymisiert' / 'anonym_01_PRUEFEN.pdf'}" in protokoll
    assert "✖ c.pdf" in protokoll and "⚠ b.pdf" in protokoll
    assert "noch auffindbar" in protokoll
    assert app.warnungen_anzahl == 3                                   # b (kein Treffer), c (Fehler), d (Reste)
    assert app.baum.set(str(c), "text") == "✖ Fehler" and app.baum.set(str(b), "text") == "keine Ausgabe"
    assert str(app.ordner_knopf.cget("state")) == "normal"
    assert dialoge.liste[-1][0] == "askyesno"                         # ein Dialog am Ende, nicht je Datei
    assert sum(1 for a_, _, _ in dialoge.liste if a_ == "error") == 0
    app.ergebnisordner_oeffnen()
    assert umgebung["geoeffnet"] == [tmp / "anonymisiert"]


# ----------------------------------------------------------------------
# GR-04: Fehlertexte der Engine verständlich
# ----------------------------------------------------------------------
def test_fehlertexte_der_engine_werden_uebersetzt(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    for roh, erwartet in (
            ("[WinError 32] Der Prozess kann nicht auf die Datei zugreifen, da sie von einem anderen Prozess "
             "verwendet wird", "anderen Programm"),
            ("[WinError 183] Eine Datei kann nicht erstellt werden, wenn sie bereits vorhanden ist",
             "Im Zielordner liegt bereits eine Datei"),
            ("[Errno 28] No space left on device", "Kein Speicherplatz"),
            ("Konnte nicht geöffnet werden: Failed to open file 'x.pdf' as type pdf.", "keine lesbare PDF-Datei"),
            ("Cannot open empty file: filename='leer.pdf'", "keine lesbare PDF-Datei")):
        uebersetzt = gui._fehlertext_verstaendlich(roh)
        assert erwartet in uebersetzt and "(Systemmeldung:" in uebersetzt, roh
    assert gui._fehlertext_verstaendlich("Passwortgeschützt – übersprungen.") == "Passwortgeschützt – übersprungen."

    gut = pdf_schreiben(tmp / "gut.pdf")
    kaputt = tmp / "kaputt.pdf"
    kaputt.write_bytes(b"kein pdf")

    def analyse(pdf_pfad, aktive, whitelist, immer_schwaerzen, melde=None, fortschritt=None, abbruch=None, ocr=None):
        e = ergebnis_mit(pdf_pfad, [FUND_TEL] if pdf_pfad == gut else [], seiten=1)
        if pdf_pfad == kaputt:
            e["fehler"] = f"Konnte nicht geöffnet werden: Failed to open file '{kaputt}' as type pdf."
        return e
    monkeypatch.setattr(gui, "analysiere_pdf", analyse)
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung(aufrufe, fehlertext_fuer={
        "gut.pdf": f"Zielordner kann nicht angelegt werden ({tmp}/anonymisiert): [Errno 17] File exists: "
                   f"'{tmp}/anonymisiert'"}))
    analysiere(app, [gut, kaputt])
    assert "keine lesbare PDF-Datei" in app.letzter_dialog[2] and "Failed to open" in app.letzter_dialog[2]
    starte_lauf(app, app.schwaerzen)
    assert "Im Zielordner liegt bereits eine Datei mit dem Namen des Ausgabeordners" in app.letzter_dialog[2]


# ----------------------------------------------------------------------
# M-57 / M-17 / GR-07 / KQ-08: 0 Funde, Warnungen, Protokoll, Meldungs-Codes
# ----------------------------------------------------------------------
def test_null_funde_erklaert_und_sperrt_schwaerzen(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "scan.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse(
        {}, warnungen_je_datei={"scan.pdf": ["Kein Text lesbar — weder direkt noch per OCR."]}))
    analysiere(app, [pdf])
    assert str(app.start_knopf.cget("state")) == "disabled"
    art, titel, text = app.letzter_dialog
    assert art == "warning" and titel == "Keine Funde"
    assert "keine Ausgabedatei" in text and "kein Text lesbar" in text and "scan.pdf" in text
    assert app.baum.set(str(pdf), "kategorie").startswith("0 Funde – kein Text lesbar")
    assert "nichts zu schwärzen" in app.protokoll_text()


def test_null_funde_ohne_warnung_ist_info(app, umgebung, monkeypatch, dialoge):
    pdf = pdf_schreiben(umgebung["tmp"] / "avb.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({}))
    analysiere(app, [pdf])
    assert app.letzter_dialog[0] == "info" and "Bedingungswerk" in app.letzter_dialog[2]


def test_meldungs_codes_entscheiden_nicht_wortfetzen(app, umgebung, monkeypatch, dialoge):
    """KQ-08: liefert die Engine „meldungen“, zählen nur die Codes – nicht der Wortlaut der Warnungen."""
    tmp = umgebung["tmp"]
    scan = pdf_schreiben(tmp / "scan.pdf")
    text = pdf_schreiben(tmp / "text.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu(
        {}, warnungen_je_datei={"scan.pdf": ["Seite 1: unlesbar (neuer Wortlaut)"],
                                "text.pdf": ["Kein Text lesbar (nur Wortlaut, kein Code)"]},
        meldungen_je_datei={"scan.pdf": [{"art": "warnung", "code": "KEIN_TEXT", "text": "x", "seite": 0}],
                            "text.pdf": []}))
    analysiere(app, [scan, text])
    assert app.baum.set(str(scan), "kategorie").startswith("0 Funde – kein Text lesbar")
    assert not app.baum.set(str(text), "kategorie").startswith("0 Funde – kein Text lesbar")
    assert "ACHTUNG" in app.letzter_dialog[2] and "scan.pdf" in app.letzter_dialog[2]
    assert "  • text.pdf" not in app.letzter_dialog[2]

    # Schwärzung: Code KEIN_TREFFER -> keine zweite (kopierte) Warnung; ohne Code wird sie ergänzt
    assert gui.WARNUNG_KEIN_TREFFER is schwaerzung.WARNUNG_KEIN_TREFFER
    erg = {"ausgabe": None, "treffer": 0, "fehler": None, "warnungen": ["Nichts lokalisierbar (neuer Text)"],
           "hinweise": [], "reste": [], "meldungen": [{"art": "warnung", "code": "KEIN_TREFFER", "text": "",
                                                        "seite": None}], "_status": "keine"}
    app._schwaerz_protokollieren("x.pdf", erg)
    assert erg["warnungen"] == ["Nichts lokalisierbar (neuer Text)"]
    erg2 = dict(erg, warnungen=["etwas anderes"], meldungen=[])
    app._schwaerz_protokollieren("y.pdf", erg2)
    assert erg2["warnungen"][-1] == gui.WARNUNG_KEIN_TREFFER


def test_protokoll_bleibt_erhalten_und_warnungen_werden_gezaehlt(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse(
        {"a.pdf": [FUND_TEL]}, warnungen_je_datei={"a.pdf": ["1 Seite(n) per OCR gelesen.", "Seite 2 kaum lesbar."]}))
    analysiere(app, [pdf])
    assert app.warnungen_anzahl == 2
    assert app.warn_label.cget("text") == "⚠ 2 Warnung(en)/Fehler"
    assert app.letzter_dialog[0] == "warning" and "2 Warnung(en)" in app.letzter_dialog[2]
    starte_lauf(app, app.analysieren)
    protokoll = app.protokoll_text()
    assert protokoll.count("Analyse fertig") == 2
    assert protokoll.count("──── Analyse") == 2
    assert "Schutzstufe Hoch (Standard)" in protokoll
    assert app.warnungen_anzahl == 2                                  # je Lauf neu gezählt
    # die letzte Zeile ist sichtbar (kein Sprung auf eine leere Schlusszeile)
    assert app.protokoll.get("end-2l", "end-1c").strip() != ""


def test_warnzaehler_zaehlt_nur_echte_warnungen(app, umgebung, monkeypatch, dialoge):
    """GR-07: Auswahlmeldungen, Abbruch- und Fertig-Zeilen zählen nicht; eine Datei ohne Treffer zählt einmal."""
    tmp = umgebung["tmp"]
    foto = tmp / "foto.jpg"
    foto.write_bytes(b"x")
    pdf = pdf_schreiben(tmp / "a.pdf")
    app._pdfs_hinzufuegen([str(foto), str(pdf), str(tmp / "fehlt.pdf")])
    assert app.warnungen_anzahl == 0 and app.warn_label.cget("text") == ""
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung([], treffer_null=("a.pdf",)))
    analysiere(app, [])
    starte_lauf(app, app.schwaerzen)
    assert app.warnungen_anzahl == 1
    assert app.protokoll_text().count(gui.WARNUNG_KEIN_TREFFER) == 1

    # Abbruch der Analyse: keine Warnung einer Datei -> Zähler 0, Abbruch nicht doppelt im Protokoll
    pdfs = [pdf_schreiben(tmp / f"s{i}.pdf", seiten=3) for i in range(2)]
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({}, seiten=3, pause=0.15))
    app.liste_leeren()
    app._pdfs_hinzufuegen([str(p) for p in pdfs])
    app.analysieren()
    assert pumpe(app.root, lambda: float(app.fortschritt.cget("value")) >= 1, timeout=10)
    vorher = app.laeufe_beendet
    app.abbrechen()
    assert pumpe(app.root, lambda: app.laeufe_beendet > vorher, timeout=30)
    pumpe(app.root, timeout=0.05)
    assert app.warnungen_anzahl == 0 and app.warn_label.cget("text") == ""
    assert "Abbruch angefordert" in app.protokoll_text() and "Analyse abgebrochen" in app.protokoll_text()


# ----------------------------------------------------------------------
# M-55 / Schutzstufe / Freigabe-Einstellung
# ----------------------------------------------------------------------
def test_einstellungen_werden_gespeichert_und_geladen(root, umgebung, dialoge, monkeypatch):
    app = gui.AnonymisiererApp(root)              # lädt aus dem (leeren) Temp-Pfad
    root.update()
    assert app.profil_var.get() == "hoch" and app.freigabe_var.get() is True   # Standard
    app.nie_feld.insert("1.0", "Müller & Söhne GmbH\nJörg Größmann")
    app.immer_feld.insert("1.0", "Projekt Phoenix")
    app.kategorie_vars["kfz"].set(True)
    app.kategorie_vars["email"].set(False)
    assert app.profil_var.get() == "benutzerdefiniert"
    app.zielordner_aktiv.set(True)
    app.zielordner_var.set(str(umgebung["tmp"] / "ziel"))
    app.freigabe_var.set(False)
    # fremde Schlüssel auf der Festplatte (z. B. aus einer neueren Version) bleiben erhalten (GR-10)
    dateien.einstellungen_speichern({"fremd": 42})
    app.einstellungen_speichern()
    pfad = dateien.einstellungen_pfad()
    assert pfad.exists()
    daten = dateien.einstellungen_laden()
    assert daten["fremd"] == 42
    assert daten["nie"] == ["Müller & Söhne GmbH", "Jörg Größmann"]
    assert daten["immer"] == ["Projekt Phoenix"]
    assert daten["kategorien"]["kfz"] is True and daten["kategorien"]["email"] is False
    assert daten["profil"] == "benutzerdefiniert" and daten["basis_profil"] == "hoch"
    assert daten["zielordner_aktiv"] is True and daten["version"] == __version__
    assert daten["freigabe_erforderlich"] is False
    assert daten["maximiert"] or "x" in daten["fenster"]

    root2 = tk.Tk()
    try:
        root2.tk.willdispatch()
        app2 = gui.AnonymisiererApp(root2)
        root2.update()
        assert app2.nie_feld.get("1.0", "end").strip() == "Müller & Söhne GmbH\nJörg Größmann"
        assert app2.immer_feld.get("1.0", "end").strip() == "Projekt Phoenix"
        assert app2.kategorie_vars["kfz"].get() is True and app2.kategorie_vars["email"].get() is False
        assert app2.profil_var.get() == "benutzerdefiniert"
        assert app2.zielordner_var.get() == str(umgebung["tmp"] / "ziel") and app2.zielordner_aktiv.get()
        assert app2.freigabe_var.get() is False
        assert not app2.analyse_veraltet                      # das Vorbelegen zählt nicht als Änderung
        if not daten["maximiert"]:
            assert root2.geometry().split("+")[0] == daten["fenster"].split("+")[0]
    finally:
        root2.destroy()


def test_alte_einstellungen_ohne_schutzstufe(root, umgebung, dialoge):
    """Einstellungen aus Phase 1: unveränderte Standard-Kategorien -> Stufe „Hoch“; eigene Auswahl bleibt."""
    standard = {e[0]: bool(e[4]) for e in gui.KATEGORIEN}
    app = gui.AnonymisiererApp(root, einstellungen={"kategorien": standard})
    assert app.profil_var.get() == "hoch"
    app.root.destroy()
    eigene = dict(standard, iban=False)
    root2 = tk.Tk()
    try:
        app2 = gui.AnonymisiererApp(root2, einstellungen={"kategorien": eigene})
        assert app2.profil_var.get() == "benutzerdefiniert" and app2.kategorie_vars["iban"].get() is False
    finally:
        root2.destroy()


def test_schutzstufe_steuert_kategorien_und_wird_uebergeben(root, umgebung, dialoge, monkeypatch):
    profile = {"ausgewogen": {"aktive": {"namen", "iban"}},
               "hoch": {"aktive": {"namen", "iban", "email"}, "beschreibung": "Empfohlen (Test)."},
               "maximal": {"kategorien": ["namen", "iban", "email", "telefon"]}}
    monkeypatch.setattr(gui, "PROFILE", profile)
    app = gui.AnonymisiererApp(root, einstellungen={})
    root.update()
    assert app.profil_var.get() == "hoch" and app._aktive_kategorien() == {"namen", "iban", "email"}
    assert app.profil_beschreibung.cget("text") == "Empfohlen (Test)."
    app.profil_knoepfe["maximal"].invoke()
    assert app._aktive_kategorien() == {"namen", "iban", "email", "telefon"} and app.basis_profil == "maximal"
    app.profil_knoepfe["ausgewogen"].invoke()
    assert app._aktive_kategorien() == {"namen", "iban"}
    app.kategorie_vars["email"].set(True)          # passt jetzt zu „hoch“
    assert app.profil_var.get() == "hoch"
    app.kategorie_vars["kfz"].set(True)            # passt zu keiner Stufe
    assert app.profil_var.get() == "benutzerdefiniert" and app.basis_profil == "hoch"
    assert "„Hoch (Standard)“" in app.profil_beschreibung.cget("text")
    app.profil_knoepfe["benutzerdefiniert"].invoke()
    assert app._aktive_kategorien() == {"namen", "iban", "email", "kfz"}   # eigene Auswahl bleibt

    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    analyse_aufrufe, schwaerz_aufrufe = [], []
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_TEL]}, aufrufe=analyse_aufrufe))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(schwaerz_aufrufe))
    app.profil_knoepfe["maximal"].invoke()
    analysiere(app, [pdf])
    starte_lauf(app, app.schwaerzen)
    assert analyse_aufrufe[0]["profil"] == "maximal" and schwaerz_aufrufe[0]["profil"] == "maximal"
    assert analyse_aufrufe[0]["aktive"] == {"namen", "iban", "email", "telefon"}


def test_attrappen_profile_aus_den_kategorien():
    alle = {e[0] for e in gui.KATEGORIEN}
    standard = {e[0] for e in gui.KATEGORIEN if e[4]}
    for name in ("ausgewogen", "hoch", "maximal"):
        menge = attrappen.profil_kategorien(attrappen.PROFILE, name, alle)
        assert menge is not None and menge >= standard - {"beruf", "arbeitgeber", "international"}
        assert "datum" not in menge                     # „alle Datumsangaben“ gehört zu keiner Stufe
    assert attrappen.profil_kategorien({"hoch": ["iban", "unbekannt"]}, "hoch", alle) == {"iban"}
    assert attrappen.profil_kategorien({"hoch": {"aktiv": {"iban": True, "email": False}}}, "hoch", alle) == {"iban"}
    assert attrappen.profil_kategorien({}, "hoch", alle) is None
    objekt = SimpleNamespace(aktive=frozenset({"iban", "email"}), beschreibung="Test")
    assert attrappen.profil_kategorien({"hoch": objekt}, "hoch", alle) == {"iban", "email"}
    assert attrappen.profil_beschreibung({"hoch": objekt}, "hoch") == "Test"


def test_schliessen_speichert_einstellungen_und_gibt_prozesszustand_zurueck(app, umgebung, dialoge):
    """KQ-10: nach dem Schließen zeigt threading.excepthook nicht mehr auf die zerstörte App."""
    assert threading.excepthook == app._thread_excepthook
    app.nie_feld.insert("1.0", "Makler GmbH")
    app.schliessen()
    assert dateien.einstellungen_laden()["nie"] == ["Makler GmbH"]
    assert not fenster_existiert(app.root)
    assert threading.excepthook != app._thread_excepthook


# ----------------------------------------------------------------------
# M-40: Fortschritt je Seite, Abbrechen, Schließen-Rückfrage
# ----------------------------------------------------------------------
def test_fortschritt_je_seite_und_abbrechen(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdfs = [pdf_schreiben(tmp / f"{i}.pdf", seiten=3) for i in range(3)]
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({}, seiten=3, pause=0.08))
    app._pdfs_hinzufuegen([str(p) for p in pdfs])
    app.analysieren()
    assert pumpe(app.root, lambda: app.laeuft, timeout=5)
    assert pumpe(app.root, lambda: float(app.fortschritt.cget("value")) >= 1, timeout=10)
    assert int(float(app.fortschritt.cget("maximum"))) == 9                  # Seiten über alle Dateien
    assert "Seite" in app.status_label.cget("text")
    vorher = app.laeufe_beendet
    app.abbrechen()
    assert app.abbruch is not None and app.abbruch.is_set()
    assert FakeOcr.instanzen[-1].abgebrochen
    assert pumpe(app.root, lambda: app.laeufe_beendet > vorher, timeout=30)
    pumpe(app.root, timeout=0.05)
    assert "abgebrochen" in app.protokoll_text()
    assert FakeOcr.instanzen[-1].geschlossen
    assert str(app.start_knopf.cget("state")) == "disabled" and app.analyse_veraltet
    assert str(app.analyse_knopf.cget("state")) == "normal"
    assert any(app.baum.set(str(p), "kategorie") == "nicht analysiert (abgebrochen)" for p in pdfs)


def test_schliessen_fragt_waehrend_des_laufs(app, umgebung, monkeypatch, dialoge):
    pdf = pdf_schreiben(umgebung["tmp"] / "a.pdf")
    weiter = threading.Event()
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL]}, warten=weiter))
    app._pdfs_hinzufuegen([str(pdf)])
    app.analysieren()
    assert pumpe(app.root, lambda: app.laeuft, timeout=5)
    dialoge.antwort = False
    app.schliessen()
    assert fenster_existiert(app.root) and app.laeuft
    assert dialoge.liste[-1][0] == "askyesno" and "läuft noch" in dialoge.liste[-1][1]
    dialoge.antwort = True
    app.schliessen()
    assert not fenster_existiert(app.root)
    assert FakeOcr.instanzen[-1].abgebrochen
    weiter.set()


# ----------------------------------------------------------------------
# M-58 / GR-08 / GR-11: Dateiliste, Nicht-PDF, Entfernen, Drag & Drop, Zwischendateien
# ----------------------------------------------------------------------
def test_dateiliste_meldet_nicht_pdf_und_erlaubt_entfernen(app, umgebung, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "in" / "a.pdf")
    docx = tmp / "in" / "Brief.docx"
    docx.write_text("x")
    leer = tmp / "leer"
    leer.mkdir()
    app._pdfs_hinzufuegen([str(docx), str(pdf), str(leer)])
    hinweis = app.datei_hinweis.cget("text")
    assert "1 PDF-Datei(en) hinzugefügt" in hinweis and "übersprungen" in hinweis and "Ordner ohne PDF" in hinweis
    assert "Brief.docx" in app.protokoll_text()
    assert app.baum.get_children("") == (str(pdf),)
    assert app.baum.set(str(pdf), "kategorie") == "noch nicht analysiert"
    assert app.dateien == [pdf]
    app.datei_entfernen()                                   # ohne Auswahl: Hinweis
    assert dialoge.liste[-1][1] == "Keine Datei gewählt" and app.dateien == [pdf]
    app.baum.selection_set(str(pdf))
    app.root.update()
    assert str(pdf) in app.status_label.cget("text")        # voller Pfad in der Statuszeile
    app.datei_entfernen()
    assert app.dateien == [] and app.baum.get_children("") == ()
    assert "entfernt" in app.datei_hinweis.cget("text")


def test_drag_and_drop_mit_klammern_und_leerzeichen(app, umgebung):
    """GR-08: tkdnd liefert eine Tcl-Liste – geschweifte Klammern und Leerzeichen im Namen bleiben heil."""
    tmp = umgebung["tmp"]
    pfade = [pdf_schreiben(tmp / "Vertrag {Kunde} 2024.pdf"), pdf_schreiben(tmp / "Angebot {1.pdf"),
             pdf_schreiben(tmp / "mit Leerzeichen" / "Police Nr 1.pdf")]
    # Zeichenkette der Tcl-Liste, wie tkdnd sie liefert (Klammern/Leerzeichen gequotet)
    daten = app.root.tk.call("format", "%s", tuple(str(p) for p in pfade))
    assert isinstance(daten, str) and "\\{" in daten
    app._drop_ereignis(SimpleNamespace(data=daten))
    assert app.dateien == pfade
    assert "nicht gefunden" not in app.datei_hinweis.cget("text")


def test_zwischendateien_sind_keine_eingabe(app, umgebung):
    """GR-11: Reste einer abgebrochenen Schwärzung werden nicht als Eingabe-PDF aufgenommen."""
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "ziel" / "a.pdf")
    rest = pdf_schreiben(tmp / "ziel" / ".anonym_tmp_99999_ausgabe.pdf")
    app._pdfs_hinzufuegen([str(tmp / "ziel")])
    assert app.dateien == [pdf]
    app._pdfs_hinzufuegen([str(rest)])
    assert app.dateien == [pdf]
    assert "Zwischendatei" in app.protokoll_text()


def test_schwaerzen_raeumt_verwaiste_zwischendateien_auf(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    ziel = tmp / "anonymisiert"
    ziel.mkdir()
    verwaist = ziel / ".anonym_tmp_2147480000_ausgabe.pdf"   # PID, die es nicht gibt
    verwaist.write_bytes(b"%PDF")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung([]))
    analysiere(app, [pdf])
    starte_lauf(app, app.schwaerzen)
    assert not verwaist.exists()
    assert "verwaiste Zwischendatei" in app.protokoll_text()


# ----------------------------------------------------------------------
# GR-12: Ergebnisordner öffnen bei vielen Ausgabeordnern
# ----------------------------------------------------------------------
def test_viele_ausgabeordner_oeffnen_den_gemeinsamen_ordner(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdfs = [pdf_schreiben(tmp / "Kunden" / f"Kunde{c}" / "Police.pdf") for c in "ABCDE"]
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"Police.pdf": [FUND_TEL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung([]))
    analysiere(app, pdfs)
    starte_lauf(app, app.schwaerzen)
    assert len(app.letzte_ausgabeordner) == 5
    assert "5 Ausgabeordner unterhalb von" in app.letzter_dialog[2]
    app.ergebnisordner_oeffnen()
    assert umgebung["geoeffnet"] == [tmp / "Kunden"]
    assert "5 Ausgabeordner unterhalb von" in app.protokoll_text()


# ----------------------------------------------------------------------
# Freigabe-Einstellung und neue Engine-Parameter
# ----------------------------------------------------------------------
def test_neue_engine_parameter_werden_uebergeben(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    a = pdf_schreiben(tmp / "a.pdf")
    b = pdf_schreiben(tmp / "b.pdf")

    class FakeLauf:
        pass
    monkeypatch.setattr(gui, "LaufWissen", FakeLauf)
    analyse_aufrufe, schwaerz_aufrufe, weitergabe = [], [], []

    def weitergabe_anwenden(ergebnisse):
        weitergabe.append(list(ergebnisse))
        ergebnisse[1]["funde"].append(dict(FUND_NAME, id="w1", quellen=["weitergabe"]))
        return 1
    monkeypatch.setattr(gui, "weitergabe_anwenden", weitergabe_anwenden)
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_NAME], "b.pdf": [FUND_TEL]},
                                                                aufrufe=analyse_aufrufe, modell=True,
                                                                mit_stellen=True))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(schwaerz_aufrufe))
    analysiere(app, [a, b])
    assert all(isinstance(c["lauf"], FakeLauf) for c in analyse_aufrufe)
    assert analyse_aufrufe[0]["lauf"] is analyse_aufrufe[1]["lauf"]          # ein Lauf-Wissen je Lauf
    assert analyse_aufrufe[0]["profil"] == "hoch" and analyse_aufrufe[0]["kundenliste"] is None
    assert len(weitergabe) == 1 and len(weitergabe[0]) == 2
    assert app.baum.get_children(str(b)) == (f"{b}::0", f"{b}::1")          # Fund aus der Weitergabe ergänzt
    assert "Dokumentübergreifende Suche: 1 weitere" in app.protokoll_text()
    starte_lauf(app, app.schwaerzen)
    assert [c["freigabe_erforderlich"] for c in schwaerz_aufrufe] == [True, True]
    assert schwaerz_aufrufe[0]["modell"] is app.analyse_ergebnisse[a]["modell"]
    assert schwaerz_aufrufe[0]["funde"][0]["stellen"][0]["an"] is True
    assert schwaerz_aufrufe[0]["manuelle_bereiche"] is None and schwaerz_aufrufe[0]["manuelle_stellen"] is None
    assert app.ausgaben[a]["status"] == "pruefen"


def test_ohne_freigabe_pflicht_sind_ausgaben_fertig(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    aufrufe = []
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_TEL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(aufrufe))
    app.freigabe_var.set(False)
    analysiere(app, [pdf])
    starte_lauf(app, app.schwaerzen)
    assert aufrufe[0]["freigabe_erforderlich"] is False
    assert (tmp / "anonymisiert" / "anonym_01.pdf").exists() and app.ausgaben[pdf]["status"] == "fertig"
    assert app.baum.set(str(pdf), "text") == "✔ fertig: anonym_01.pdf"
    assert "Ergebnisordner jetzt öffnen?" in dialoge.liste[-1][2] and "_PRUEFEN" not in dialoge.liste[-1][2]


# ----------------------------------------------------------------------
# Kundenliste
# ----------------------------------------------------------------------
def test_kundenliste_importieren_anzeigen_uebergeben_entfernen(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    csv_datei = tmp / "kunden.csv"
    csv_datei.write_text("Name;Geburtsdatum;IBAN\nMax Mustermann;02.09.1983;DE89370400440532013000\n"
                         "Erika Musterfrau;01.01.1970;\n", encoding="utf-8")
    app.kundenliste_importieren(csv_datei)
    assert app.kundenliste is not None and app.kundenliste.anzahl_kunden == 2
    assert app.kunden_label.cget("text").startswith("2 Kunden geladen – gespeichert ohne Klartext")
    assert "noch nicht aktiv" in app.kunden_label.cget("text")          # Attrappe: ehrlich anzeigen
    gespeichert = dateien.kundenliste_pfad().read_text(encoding="utf-8")
    assert "Mustermann" not in gespeichert and "DE89" not in gespeichert
    assert str(app.kunden_entfernen_knopf.cget("state")) == "normal"

    # neue Engine: die Kundenliste wird an analysiere_pdf übergeben
    class EchteListe:
        anzahl_kunden = 3

        @staticmethod
        def laden(pfad=None):
            return EchteListe()
    monkeypatch.setattr(gui, "Kundenliste", EchteListe)
    aufrufe = []
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_TEL]}, aufrufe=aufrufe))
    app._kundenliste_laden()
    assert app.kunden_label.cget("text") == "3 Kunden geladen – gespeichert ohne Klartext"
    analysiere(app, [pdf_schreiben(tmp / "a.pdf")])
    assert isinstance(aufrufe[0]["kundenliste"], EchteListe)

    monkeypatch.setattr(gui, "Kundenliste", attrappen.Kundenliste)
    dialoge.antwort = True
    app.kundenliste_entfernen()
    assert app.kundenliste is None and not dateien.kundenliste_pfad().exists()
    assert app.kunden_label.cget("text").startswith("keine geladen")
    assert str(app.kunden_entfernen_knopf.cget("state")) == "disabled"
    assert app.analyse_veraltet                                          # Ergebnisse passen nicht mehr


def test_kundenliste_spaltenzuordnung_bei_unbekannten_kopfzeilen(app, umgebung, dialoge):
    tmp = umgebung["tmp"]
    csv_datei = tmp / "export.csv"
    csv_datei.write_text("Kd;Fam;Notiz\n4711;Meier;x\n4712;Schulze;y\n", encoding="cp1252")
    app.kundenliste_importieren(csv_datei)
    dialog = app.spalten_dialog
    assert dialog is not None and app.kundenliste is None
    assert dialog.kopf_var.get() is True and len(dialog.boxen) == 3
    dialog.bestaetigen()                                                  # nichts zugeordnet -> Meldung
    assert "mindestens eine Spalte" in dialog.meldung.cget("text")
    dialog.boxen[0].set(attrappen.MERKMALE["kundennummer"])
    dialog.boxen[1].set(attrappen.MERKMALE["nachname"])
    assert dialog.zuordnung() == {"kundennummer": "Kd", "nachname": "Fam"}
    dialog.bestaetigen()
    assert app.kundenliste is not None and app.kundenliste.anzahl_kunden == 2
    assert app.letzter_dialog[1] == "Kundenliste importiert"

    ohne_kopf = tmp / "ohne_kopf.csv"
    ohne_kopf.write_text("4711,Meier\n4712,Schulze\n4713,Weber\n", encoding="utf-8")
    app.kundenliste_importieren(ohne_kopf)
    dialog = app.spalten_dialog
    assert dialog.kopf_var.get() is False
    dialog.boxen[0].set(attrappen.MERKMALE["kundennummer"])
    assert dialog.zuordnung() == {"kundennummer": 0}
    dialog.bestaetigen()
    assert app.kundenliste.anzahl_kunden == 3


# ----------------------------------------------------------------------
# M-19 / M-64 / M-68 / GR-09: Wortwahl, Fenstertitel, DnD-Fallback
# ----------------------------------------------------------------------
def test_fenstertitel_und_texte(app):
    assert app.root.title() == f"PDF-Anonymisierer {__version__}"
    for text in (gui.UNTERTITEL, gui.HINWEISKASTEN, gui.GRENZEN_TEXT, app.untertitel.cget("text")):
        assert "gefahrlos" not in text.lower()
    assert "Pseudonymisierung" in gui.UNTERTITEL and "geprüft" in gui.UNTERTITEL
    for wort in ("Diagnosen", "Beruf", "Arbeitgeber", "Unterschriften", "Bilder", "Handschrift"):
        assert wort in app.hinweis_kasten.cget("text") and wort in gui.GRENZEN_TEXT
    assert "OneDrive" in app.hinweis_kasten.cget("text")
    # GR-09: Bild-OCR wird nicht verschwiegen, aber als unsicher bezeichnet
    assert "nur ganzseitige Scans" not in gui.GRENZEN_TEXT
    assert "nur unsicher" in gui.GRENZEN_TEXT and "nur unsicher (OCR)" in gui.HINWEISKASTEN
    assert app.baum.heading("seiten", "text") == "Seite(n)" and app.baum.heading("kontext", "text") == "Kontext"
    app.hilfe_grenzen()
    assert app.letzter_dialog[1] == "Was wird nicht erkannt?"


def test_texte_passen_zum_funktionsumfang_der_engine():
    alt = gui._texte_zur_engine(False)
    neu = gui._texte_zur_engine(True)
    assert "Diagnosen, Beruf, Arbeitgeber, Beträge und Orte bleiben lesbar" in alt[0]
    assert "je nach Schutzstufe" in neu[0] and "Maximal" in neu[2]


def test_main_faellt_ohne_tkdnd_auf_tk_zurueck(umgebung, dialoge, monkeypatch):
    class KaputteDnD:
        @staticmethod
        def Tk(*a, **k):
            raise RuntimeError("Unable to load tkdnd library")

    monkeypatch.setattr(gui, "TkinterDnD", KaputteDnD)
    monkeypatch.setattr(gui, "DND_VERFUEGBAR", True)
    app = gui.main(ereignisschleife=False)
    try:
        assert isinstance(app.root, tk.Tk) and gui.DND_VERFUEGBAR is False and not app.dnd_aktiv
        assert "nicht verfügbar" in app.drop_zone.cget("text")
        assert "tkdnd" in umgebung["fehlerlog"].read_text(encoding="utf-8")
    finally:
        app.root.destroy()


def test_zweiter_start_zeigt_hinweis_statt_zweitem_fenster(umgebung, dialoge, monkeypatch):
    """GR-10: Einzelinstanz-Sperre im Einstellungsordner; nach dem Schließen ist ein neuer Start möglich."""
    monkeypatch.setattr(gui, "DND_VERFUEGBAR", False)
    erste = gui.main(ereignisschleife=False)
    try:
        assert erste is not None and erste.instanz_sperre is not None and erste.instanz_sperre.aktiv
        assert (dateien.einstellungen_pfad().parent / dateien.SPERR_DATEI).exists()
        zweite = gui.main(ereignisschleife=False)
        assert zweite is None
        assert dialoge.liste[-1][1] == "PDF-Anonymisierer läuft bereits"
    finally:
        erste.schliessen()
    dritte = gui.main(ereignisschleife=False)
    try:
        assert dritte is not None
    finally:
        dritte.root.destroy()
    assert dritte.instanz_sperre is None                       # <Destroy> gibt die Sperre frei


def test_namenserkennung_wird_im_hintergrund_vorgeladen(umgebung, dialoge, monkeypatch):
    """PERF-09: das spaCy-Modell lädt kurz nach dem Start in einem Hintergrund-Thread; die Analyse wartet
    darauf statt ein zweites Mal gleichzeitig zu laden."""
    aufrufe, gleichzeitig, aktiv = [], [], [0]
    sperre = threading.Lock()

    def fake_lade_ner():
        with sperre:
            aktiv[0] += 1
            gleichzeitig.append(aktiv[0])
        aufrufe.append(threading.current_thread().name)
        time.sleep(0.4)
        with sperre:
            aktiv[0] -= 1
    monkeypatch.setattr(gui, "lade_ner", fake_lade_ner)
    monkeypatch.setattr(gui, "DND_VERFUEGBAR", False)
    monkeypatch.setattr(gui, "VORLADEN_NACH_MS", 50)
    app = gui.main(ereignisschleife=False)
    try:
        app.root.tk.willdispatch()
        assert pumpe(app.root, lambda: aufrufe, timeout=5)
        assert aufrufe == ["Modell-Vorladen"]
        assert app.status_label.cget("text") == "Namenserkennung wird vorbereitet …"
        pdf = pdf_schreiben(umgebung["tmp"] / "a.pdf")
        monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL]}))
        analysiere(app, [pdf])
        assert aufrufe == ["Modell-Vorladen", "Analyse"] and max(gleichzeitig) == 1
        assert app.vorladen_thread is not None and not app.vorladen_thread.is_alive()
    finally:
        app.root.destroy()


# ----------------------------------------------------------------------
# Echte Engine (aktueller Stand) – ohne Sprachmodell
# ----------------------------------------------------------------------
def test_kompletter_ablauf_mit_echter_engine(app, umgebung, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "echt" / "Vertrag.pdf")
    app.kategorie_vars["namen"].set(False)              # kein spaCy nötig
    analysiere(app, [pdf])
    ergebnis = app.analyse_ergebnisse[pdf]
    assert ergebnis["funde"], "echte Engine sollte IBAN/E-Mail/Telefon finden"
    texte = {f["text"] for f in ergebnis["funde"]}
    assert any("DE89" in t for t in texte) and any("@" in t for t in texte)
    assert all(set(f) >= {"kategorie", "anzeige", "text", "ersatz", "seiten", "anzahl", "kontext"}
               for f in ergebnis["funde"])
    assert str(app.start_knopf.cget("state")) == "normal"
    starte_lauf(app, app.schwaerzen, timeout=120)
    ausgaben = list((tmp / "echt" / "anonymisiert").glob("*.pdf"))
    assert len(ausgaben) == 1 and ausgaben[0].name == "anonym_01_PRUEFEN.pdf"
    assert "✔" in app.protokoll_text() and "1 von 1 Datei(en) geschrieben" in app.protokoll_text()
    with fitz.open(ausgaben[0]) as doc:
        rest = "".join(p.get_text() for p in doc)
    assert "DE89 3704 0044" not in rest and "max.mustermann@example.de" not in rest
    # Freigabe über die Attrappe bzw. schwaerzung.freigeben
    neu = app.ausgabe_freigeben(pdf)
    assert neu == tmp / "echt" / "anonymisiert" / "anonym_01.pdf" and neu.exists()
    zuordnung = (tmp / "echt" / "anonymisiert" / "_zuordnung.txt").read_text(encoding="utf-8")
    assert zuordnung.startswith("anonym_01.pdf  <-  Vertrag.pdf") and "PRUEFEN" not in zuordnung
    assert app.ausgaben[pdf]["status"] == "fertig"
