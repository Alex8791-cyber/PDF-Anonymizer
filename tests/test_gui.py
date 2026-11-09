"""GUI-Tests (tkinter unter Xvfb). Ohne Display werden alle Tests übersprungen.

Die Engine (analysiere_pdf, schwaerze_pdf, OcrDienst) wird durch Fakes ersetzt, die Ergebnisse
in der Vertragsform liefern; ein Test läuft zusätzlich mit der echten Engine.
Screenshots landen in $PDF_ANONYMISIERER_SCREENSHOTS oder im pytest-Temp-Ordner (nicht im Repo).
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

import fitz
import pytest

from anonymisierer import __version__, dateien, gui

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
FUND_BEGRIFF = {"kategorie": "begriff", "anzeige": "IMMER-Begriff", "text": "Allianz", "ersatz": "[BEGRIFF]",
                "seiten": [1], "anzahl": 1, "kontext": "»Allianz« Lebensversicherungs-AG"}
OCR_CACHE = {0: [(10.0, 10.0, 50.0, 20.0, "Wort")]}


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
                 fehler: Exception | None = None, warnungen_je_datei: dict | None = None):
    """Baut eine analysiere_pdf-Attrappe mit Vertragssignatur und -rückgabe."""
    def analysiere_pdf(pdf_pfad, aktive, whitelist, immer_schwaerzen, melde=None, fortschritt=None,
                       abbruch=None, ocr=None):
        if fehler is not None:
            raise fehler
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


def fake_schwaerzung(aufrufe: list, treffer_null=(), fehler_fuer: dict | None = None, reste_fuer: dict | None = None):
    """Baut eine schwaerze_pdf-Attrappe: kopiert das PDF als anonym_NN.pdf in den Zielordner."""
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
        if pdf_pfad.name in treffer_null:
            ergebnis["warnungen"].append("Kein angehakter Fund konnte im Dokument lokalisiert werden "
                                         "– keine Ausgabedatei erzeugt.")
            return ergebnis
        ordner = Path(ziel_ordner) if ziel_ordner else pdf_pfad.parent / "anonymisiert"
        ordner.mkdir(parents=True, exist_ok=True)
        reste = list((reste_fuer or {}).get(pdf_pfad.name, []))
        n = 1
        while (ordner / f"anonym_{n:02d}.pdf").exists() or (ordner / f"anonym_{n:02d}_PRUEFEN.pdf").exists():
            n += 1
        ausgabe = ordner / (f"anonym_{n:02d}_PRUEFEN.pdf" if reste else f"anonym_{n:02d}.pdf")
        shutil.copy(pdf_pfad, ausgabe)
        ergebnis.update(ausgabe=ausgabe, treffer=len(funde), reste=reste)
        if reste:
            ergebnis["warnungen"].append(f"'{reste[0]}' ist noch auffindbar – bitte manuell prüfen!")
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
# M-01: gleiche Dateinamen in verschiedenen Ordnern
# ----------------------------------------------------------------------
def test_gleiche_dateinamen_in_zwei_ordnern_bekommen_je_eine_ausgabe(app, umgebung, monkeypatch, dialoge):
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
    assert (tmp / "KundeA" / "anonymisiert" / "anonym_01.pdf").exists()
    assert (tmp / "KundeB" / "anonymisiert" / "anonym_01.pdf").exists()
    # ocr_cache aus der Analyse und ein OcrDienst je Lauf werden durchgereicht, danach geschlossen
    assert aufrufe[0]["ocr_cache"] == OCR_CACHE
    assert isinstance(aufrufe[0]["ocr"], FakeOcr) and aufrufe[0]["ocr"] is aufrufe[1]["ocr"]
    assert all(o.geschlossen for o in FakeOcr.instanzen) and len(FakeOcr.instanzen) == 2
    protokoll = app.protokoll_text()
    assert "2 von 2 Datei(en) geschrieben" in protokoll
    assert f"KundeA/Police.pdf  →  {tmp / 'KundeA' / 'anonymisiert' / 'anonym_01.pdf'}" in protokoll
    assert sorted(app.letzte_ausgabeordner) == sorted([tmp / "KundeA" / "anonymisiert", tmp / "KundeB" / "anonymisiert"])
    assert dialoge.liste[-1][0] == "askyesno" and "2 von 2" in dialoge.liste[-1][2]


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
    assert (tmp / "ziel" / "anonym_01.pdf").exists()
    assert app.letzte_ausgabeordner == [tmp / "ziel"]


# ----------------------------------------------------------------------
# M-05: Layout auf verschiedenen Bildschirmen und Skalierungen
# ----------------------------------------------------------------------
def _display_wiederherstellen(display_vorher):
    """Tk setzt beim Öffnen mit screenName die Umgebungsvariable DISPLAY prozessweit um (Tcl-env-Verknüpfung);
    ohne Rücksetzen landen alle späteren Fenster auf dem anderen Display."""
    if display_vorher:
        os.environ["DISPLAY"] = display_vorher


def _display_1366():
    """Liefert den Namen eines 1366x768-Displays (startet bei Bedarf Xvfb :98) oder None."""
    if sys.platform == "win32":
        return None
    display_vorher = os.environ.get("DISPLAY")
    try:
        for versuch in range(2):
            try:
                probe = tk.Tk(screenName=":98")
                groesse = (probe.winfo_screenwidth(), probe.winfo_screenheight())
                probe.destroy()
                return ":98" if groesse == (1366, 768) else None
            except tk.TclError:
                if versuch or not shutil.which("Xvfb"):
                    return None
                subprocess.Popen(["Xvfb", ":98", "-screen", "0", "1366x768x24"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1.5)
        return None
    finally:
        _display_wiederherstellen(display_vorher)


def _screenshot_ordner(tmp_path_factory) -> Path:
    ordner = Path(os.environ.get("PDF_ANONYMISIERER_SCREENSHOTS")
                  or tmp_path_factory.getbasetemp() / "screenshots")
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def _beispielfunde_eintragen(app):
    pdf = Path(tempfile.gettempdir()) / "Kunden" / "Beispiel_Versicherungsschein.pdf"
    app.dateien.append(pdf)
    app._datei_zeile_einfuegen(pdf)
    app._beschriftungen_aktualisieren()
    app._baum_datei_fuellen(pdf, gui._analyse_ergebnis_vervollstaendigen(
        {"funde": [FUND_NAME, FUND_TEL, FUND_MAIL, FUND_BEGRIFF], "seiten": 2}, pdf))
    app._log("Analyse fertig: 4 Fund(e) in 1 Datei(en). Bitte Liste prüfen, dann schwärzen.", "ok")
    app._log("⚠ Beispiel.pdf: 1 Seite(n) per OCR gelesen – Ergebnis bitte besonders sorgfältig prüfen!", "warnung")
    app._start_knopf_aktualisieren()


@pytest.mark.parametrize("anzeige", ["standard", "1366x768"])
@pytest.mark.parametrize("skalierung", [1.3333, 1.6667, 2.0])
def test_layout_schwaerzen_knopf_und_protokoll_immer_sichtbar(anzeige, skalierung, umgebung, dialoge,
                                                                 tmp_path_factory):
    display = None
    display_vorher = os.environ.get("DISPLAY")
    if anzeige == "1366x768":
        display = _display_1366()
        if display is None:
            pytest.skip("kein 1366x768-Display (Xvfb :98) verfügbar")
    try:
        root = tk.Tk(screenName=display) if display else tk.Tk()
    except tk.TclError as fehler:
        pytest.skip(f"Tk kann kein Fenster öffnen: {fehler}")
    try:
        root.tk.willdispatch()
        root.tk.call("tk", "scaling", skalierung)
        app = gui.AnonymisiererApp(root, einstellungen={})
        _beispielfunde_eintragen(app)
        pumpe(root, timeout=0.3)
        root.update_idletasks()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        fenster_h, fenster_w = root.winfo_height(), root.winfo_width()
        assert fenster_w <= sw and fenster_h <= sh - 60, "Fenster passt nicht auf den Bildschirm"
        assert root.minsize() == gui.FENSTER_MINDESTMASS

        def lage(w):
            y0 = w.winfo_rooty() - root.winfo_rooty()
            return y0, y0 + w.winfo_height()

        for name, w in (("Schwärzen-Knopf", app.start_knopf), ("Abbrechen-Knopf", app.abbrechen_knopf),
                        ("Fortschritt", app.fortschritt), ("Protokoll", app.protokoll),
                        ("Fundliste", app.baum), ("Hinweiskasten", app.hinweis_kasten),
                        ("Drop-Zone", app.drop_zone)):
            assert w.winfo_ismapped(), f"{name} nicht sichtbar"
            oben, unten = lage(w)
            assert 0 <= oben and unten <= fenster_h, f"{name} ragt aus dem Fenster ({oben}..{unten} von {fenster_h})"
        assert app.start_knopf.winfo_height() >= 20
        mono = tkfont.Font(family=gui.SCHRIFT_MONO, size=9)
        assert app.protokoll.winfo_height() >= 3 * mono.metrics("linespace"), "Protokoll zu niedrig"
        assert app.baum.winfo_height() >= 2 * max(20, app.zeilenhoehe + 6), "Fundliste zu niedrig"
        # Zeilenhöhe folgt der Schrift
        rowheight = int(ttk_style_lookup(root, "Treeview", "rowheight"))
        assert rowheight >= app.zeilenhoehe + 4
        # Protokoll: letzte Zeile sichtbar (nicht auf eine leere Schlusszeile gesprungen)
        assert app.protokoll.get("end-2l", "end-1c").strip().startswith("⚠")
        # Analysieren-Knopf ist auf dem Standardbildschirm bei 100 % ohne Scrollen erreichbar
        if anzeige == "standard" and skalierung == 1.3333 and sh >= 1080:  # nur auf echtem FHD-Schirm
            # Geprueft wird die Nutzeranforderung (Knopf ohne Scrollen erreichbar), nicht die Bildlaufleiste:
            # ob der Einstellbereich scrollt, haengt von den Systemschriften ab (CI-Runner != Windows).
            oben, unten = lage(app.analyse_knopf)
            assert 0 <= oben and unten <= fenster_h, \
                f"Analysieren-Knopf bei FHD/100 % nicht ohne Scrollen sichtbar ({oben}..{unten} von {fenster_h})"
        _screenshot(root, display, _screenshot_ordner(tmp_path_factory) / f"layout_{anzeige}_{skalierung}.png")
    finally:
        try:
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

    # Doppelklick auf den Dateinamen: wählt die Datei aus, klappt nichts zu und schaltet nichts
    xe, ye, be, he = zellenbox(app, eltern, "#0")
    klick(app.baum, xe + be - 10, ye + he // 2, anzahl=2)
    assert app.baum.item(eltern, "open") in (True, 1, "true")
    assert [app._zustand(k) for k in kinder] == ["an", "aus", "an"]
    assert app.baum.selection() == (eltern,)
    assert str(pdf) in app.status_label.cget("text")

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

    vorher = list(app.dateien)
    app._pdfs_hinzufuegen([str(pdf_schreiben(tmp / "b.pdf"))])
    app.liste_leeren()
    app.datei_entfernen(str(pdf))
    app.analysieren()
    app.schwaerzen()
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

    # neue Datei nach der Analyse: Schwärzen verlangt erst eine Analyse der neuen Datei
    starte_lauf(app, app.analysieren)
    app._pdfs_hinzufuegen([str(pdf_schreiben(tmp / "b.pdf"))])
    app.schwaerzen()
    assert aufrufe == [] and dialoge.liste[-1][1] == "Erst analysieren"


# ----------------------------------------------------------------------
# M-10 / M-32: Ausnahme im Arbeits-Thread
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
    assert art == "warning" and titel == "Schwärzung abgeschlossen"
    assert "2 von 4 Datei(en) geschrieben" in text
    assert "b.pdf" in text and "lokalisiert" in text
    assert "c.pdf" in text and "anderen Programm" in text          # verständlich statt Traceback
    assert "_PRUEFEN" in text and "anonym_02_PRUEFEN.pdf" in text
    assert "PermissionError" in umgebung["fehlerlog"].read_text(encoding="utf-8")
    protokoll = app.protokoll_text()
    assert f"a.pdf  →  {tmp / 'anonymisiert' / 'anonym_01.pdf'}" in protokoll
    assert "✖ c.pdf" in protokoll and "⚠ b.pdf" in protokoll
    assert "noch auffindbar" in protokoll
    assert app.warnungen_anzahl >= 3
    assert str(app.ordner_knopf.cget("state")) == "normal"
    assert dialoge.liste[-1][0] == "askyesno"                         # ein Dialog am Ende, nicht je Datei
    assert sum(1 for a_, _, _ in dialoge.liste if a_ == "error") == 0
    app.ergebnisordner_oeffnen()
    assert umgebung["geoeffnet"] == [tmp / "anonymisiert"]


# ----------------------------------------------------------------------
# M-57 / M-17: 0 Funde, Warnungen, Protokoll
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
    assert app.warnungen_anzahl == 2                                  # je Lauf neu gezählt
    # die letzte Zeile ist sichtbar (kein Sprung auf eine leere Schlusszeile)
    assert app.protokoll.get("end-2l", "end-1c").strip() != ""


# ----------------------------------------------------------------------
# M-55: Einstellungen
# ----------------------------------------------------------------------
def test_einstellungen_werden_gespeichert_und_geladen(root, umgebung, dialoge, monkeypatch):
    app = gui.AnonymisiererApp(root)              # lädt aus dem (leeren) Temp-Pfad
    root.update()
    app.nie_feld.insert("1.0", "Müller & Söhne GmbH\nJörg Größmann")
    app.immer_feld.insert("1.0", "Projekt Phoenix")
    app.kategorie_vars["kfz"].set(True)
    app.kategorie_vars["email"].set(False)
    app.zielordner_aktiv.set(True)
    app.zielordner_var.set(str(umgebung["tmp"] / "ziel"))
    app.einstellungen_speichern()
    pfad = dateien.einstellungen_pfad()
    assert pfad.exists()
    daten = dateien.einstellungen_laden()
    assert daten["nie"] == ["Müller & Söhne GmbH", "Jörg Größmann"]
    assert daten["immer"] == ["Projekt Phoenix"]
    assert daten["kategorien"]["kfz"] is True and daten["kategorien"]["email"] is False
    assert daten["zielordner_aktiv"] is True and daten["version"] == __version__
    assert daten["maximiert"] or "x" in daten["fenster"]

    root2 = tk.Tk()
    try:
        root2.tk.willdispatch()
        app2 = gui.AnonymisiererApp(root2)
        root2.update()
        assert app2.nie_feld.get("1.0", "end").strip() == "Müller & Söhne GmbH\nJörg Größmann"
        assert app2.immer_feld.get("1.0", "end").strip() == "Projekt Phoenix"
        assert app2.kategorie_vars["kfz"].get() is True and app2.kategorie_vars["email"].get() is False
        assert app2.zielordner_var.get() == str(umgebung["tmp"] / "ziel") and app2.zielordner_aktiv.get()
        assert not app2.analyse_veraltet                      # das Vorbelegen zählt nicht als Änderung
        if not daten["maximiert"]:
            assert root2.geometry().split("+")[0] == daten["fenster"].split("+")[0]
    finally:
        root2.destroy()


def test_schliessen_speichert_einstellungen(app, umgebung, dialoge):
    app.nie_feld.insert("1.0", "Makler GmbH")
    app.schliessen()
    assert dateien.einstellungen_laden()["nie"] == ["Makler GmbH"]
    assert not fenster_existiert(app.root)


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
    assert any(app.baum.set(str(p), "kategorie").startswith("nicht analysiert") for p in pdfs)


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
# M-58: Dateiliste, Nicht-PDF, Entfernen
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


# ----------------------------------------------------------------------
# M-19 / M-64 / M-68: Wortwahl, Fenstertitel, DnD-Fallback
# ----------------------------------------------------------------------
def test_fenstertitel_und_texte(app):
    assert app.root.title() == f"PDF-Anonymisierer {__version__}"
    for text in (gui.UNTERTITEL, gui.HINWEISKASTEN, gui.GRENZEN_TEXT, app.untertitel.cget("text")):
        assert "gefahrlos" not in text.lower()
    assert "Pseudonymisierung" in gui.UNTERTITEL and "geprüft" in gui.UNTERTITEL
    for wort in ("Diagnosen", "Beruf", "Arbeitgeber", "Unterschriften", "Bilder", "Handschrift"):
        assert wort in app.hinweis_kasten.cget("text") and wort in gui.GRENZEN_TEXT
    assert "OneDrive" in app.hinweis_kasten.cget("text")
    assert app.baum.heading("seiten", "text") == "Seite(n)" and app.baum.heading("kontext", "text") == "Kontext"
    app.hilfe_grenzen()
    assert app.letzter_dialog[1] == "Was wird nicht erkannt?"


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


# ----------------------------------------------------------------------
# Echte Engine (aktueller Stand) über den Adapter – ohne Sprachmodell
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
    assert len(ausgaben) == 1
    assert "✔" in app.protokoll_text() and "1 von 1 Datei(en) geschrieben" in app.protokoll_text()
    with fitz.open(ausgaben[0]) as doc:
        rest = "".join(p.get_text() for p in doc)
    assert "DE89 3704 0044" not in rest and "max.mustermann@example.de" not in rest
