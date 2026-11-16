"""Hauptfenster auf kleinen Laptop-Bildschirmen (Runde 3, Paket „vorschau-oberflaeche“).

Befund: auf 1366x768 bei 150 % war der Einstellbereich nur 90 Pixel hoch – die Hinweiszeile zur Dateiauswahl, die
die NICHT geprüften Dateien nennt, lag unsichtbar darunter (bei 125 % halb sichtbar), die Fundliste zeigte eine
Zeile, und die erste Spalte schnitt „(Bild → PDF)“ / „(Kennwort entfernt)“ ab.

Geprüft wird hier für 1366x768 bei 100/125/150 %, 1024x768 bei 100 % und 1920x1080 bei 100/150/200 % mit einer
typischen Auswahl (PDF, PDF mit Kennwort, Foto, Mail = nicht geprüft) und Funden:
  * Hinweiszeile, Drop-Zone und alle Knöpfe (Dateien, Liste, Aktionsleiste) liegen ohne Scrollen ganz im Fenster
    bzw. im sichtbaren Teil des Einstellbereichs; die Hinweiszeile ist weder seitlich noch unten abgeschnitten,
  * die Fundliste zeigt mindestens so viele ganze Zeilen wie angegeben (150 % auf 1366x768: drei),
  * die erste Spalte zeigt jeden Dateinamen samt Zusatz vollständig (lange Namen in der Mitte gekürzt),
  * keine Zeile des Einstellbereichs wird am unteren Rand mittendurch geschnitten, und die waagrechte
    Bildlaufleiste der Liste erscheint nur, wenn die Spalten nicht passen.
Die Skalierung wird wie in der App über „tk scaling“ nachgestellt (4/3 = Windows 100 %). Unter Linux laufen die Fälle
auf Xvfb-Displays der jeweiligen Größe (:98 = 1366x768, :97 = 1024x768; bei Bedarf gestartet); ohne Xvfb (Windows)
wird die Bildschirmgröße nachgestellt, wenn der echte Bildschirm groß genug ist, sonst wird mit Begründung
übersprungen. Ein Bildschirmfoto je Fall landet im Screenshot-Ordner (CI-Artefakt).
"""

import os
import shutil
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from anonymisierer import dateien, gui

from test_gui import (_display_groesse, _display_wiederherstellen, _prozesszustand, _screenshot,  # noqa: F401
                      _screenshot_ordner, dialoge, pumpe, umgebung)

# (Bildschirm, Breite, Höhe, tk scaling, Prozent, mindestens sichtbare Zeilen der Fundliste)
SZENARIEN = [
    ("1366x768", 1366, 768, 4 / 3, 100, 5),
    ("1366x768", 1366, 768, 5 / 3, 125, 4),
    ("1366x768", 1366, 768, 2.0, 150, 3),
    ("1024x768", 1024, 768, 4 / 3, 100, 5),
    ("1920x1080", 1920, 1080, 4 / 3, 100, 8),
    ("1920x1080", 1920, 1080, 2.0, 150, 6),
    ("1920x1080", 1920, 1080, 8 / 3, 200, 4),
]
DISPLAYS = {(1366, 768): (":98",), (1024, 768): (":97",), (1920, 1080): (":96", ":99", ":95")}
_GESTARTET: list = []
FUNDE = [("namen", "Name", "Max Mustermann", "[PERSON A]", "Sehr geehrter Herr »Max Mustermann«, wir"),
         ("telefon", "Telefonnummern", "0171 2345678", "[TELEFON]", "Tel. »0171 2345678«, E-Mail"),
         ("email", "E-Mail-Adressen", "max.mustermann@example.de", "[E-MAIL]", "E-Mail »max…«"),
         ("iban", "IBAN", "DE89 3704 0044 0532 0130 00", "[IBAN]", "IBAN: »DE89 3704 …« BIC"),
         ("adresse", "Anschrift", "Hauptstraße 12a", "[STRASSE]", "wohnhaft »Hauptstraße 12a«, 90402"),
         ("geburtsdatum", "Geburtsdatum", "02.09.1983", "[GEBURTSDATUM]", "geb. am »02.09.1983« in"),
         ("vertragsnummer", "Vertragsnummern", "LV-2024-887766", "[VERTRAG-NR]", "Schein-Nr. »LV-2024…«")]


@pytest.fixture(autouse=True)
def _temp_ordner(monkeypatch, tmp_path):
    """Arbeitskopien (Foto als PDF, entschlüsselte PDF) nie im echten Programmordner."""
    monkeypatch.setattr(dateien, "temp_basis", lambda: tmp_path / "programm_temp")
    monkeypatch.setattr(dateien, "_SITZUNG", None)
    monkeypatch.setattr(dateien, "_SITZUNG_BEENDET", False)
    yield
    dateien.sitzung_aufraeumen()


@pytest.fixture(scope="module", autouse=True)
def _xvfb_beenden():
    yield
    while _GESTARTET:
        prozess = _GESTARTET.pop()
        prozess.terminate()
        try:
            prozess.wait(5)
        except subprocess.TimeoutExpired:
            prozess.kill()


def display_fuer(breite: int, hoehe: int):
    """Name eines Displays genau dieser Größe (Linux/Xvfb; bei Bedarf gestartet) oder None."""
    if sys.platform == "win32":
        return None
    aktuell = os.environ.get("DISPLAY")
    kandidaten = [aktuell] if aktuell and _display_groesse(aktuell) == (breite, hoehe) else []
    kandidaten += list(DISPLAYS.get((breite, hoehe), ()))
    for name in kandidaten:
        groesse = _display_groesse(name)
        if groesse == (breite, hoehe):
            return name
        if groesse is None and shutil.which("Xvfb"):
            prozess = subprocess.Popen(["Xvfb", name, "-screen", "0", f"{breite}x{hoehe}x24"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _GESTARTET.append(prozess)
            for _ in range(40):
                time.sleep(0.1)
                if _display_groesse(name) == (breite, hoehe):
                    return name
    return None


def auswahl(ordner: Path) -> Path:
    """Typische Auswahl eines Maklers: Police (langer Name), PDF mit Kennwort, Ausweisfoto, eine Mail."""
    ordner.mkdir(parents=True)
    doc = fitz.open()
    doc.new_page().insert_text((60, 80), "Versicherungsnehmer: Max Mustermann", fontsize=11)
    doc.save(ordner / "Police_Lebensversicherung_Mustermann_Hauptvertrag_2024.pdf")
    doc.save(ordner / "Kontoauszug_Sparkasse_Nuernberg_Juni.pdf", encryption=fitz.PDF_ENCRYPT_AES_256,
             user_pw="geheim", owner_pw="geheim")
    doc.close()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 260), False)
    pix.clear_with(235)
    (ordner / "Ausweis_Foto_Mustermann.jpg").write_bytes(pix.tobytes("jpg"))
    (ordner / "Mail_an_Makler_Rueckfrage.msg").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600)
    return ordner


def lage(root, w) -> tuple[int, int, int, int]:
    """(oben, unten, links, rechts) relativ zum Fenster."""
    y0, x0 = w.winfo_rooty() - root.winfo_rooty(), w.winfo_rootx() - root.winfo_rootx()
    return y0, y0 + w.winfo_height(), x0, x0 + w.winfo_width()


def im_einstellbereich(app, w) -> bool:
    p = w
    while p is not None:
        if p is app.oben_canvas:
            return True
        p = getattr(p, "master", None)
    return False


def ganze_zeilen(app) -> int:
    hoehe = app.baum.winfo_height()
    zeilen = 0
    for datei in app.baum.get_children(""):
        for eintrag in [datei, *app.baum.get_children(datei)]:
            box = app.baum.bbox(eintrag)
            if box and box[1] >= 0 and box[1] + box[3] <= hoehe:
                zeilen += 1
    return zeilen


@pytest.mark.parametrize("bildschirm, breite, hoehe, skalierung, prozent, mindestzeilen", SZENARIEN,
                         ids=[f"{s[0]}_{s[4]}" for s in SZENARIEN])
def test_hinweiszeile_fundliste_und_knoepfe_ohne_scrollen(bildschirm, breite, hoehe, skalierung, prozent,
                                                         mindestzeilen, umgebung, dialoge, monkeypatch,
                                                         tmp_path_factory):
    display = display_fuer(breite, hoehe)
    nachgestellt = display is None
    display_vorher = os.environ.get("DISPLAY")
    try:
        root = tk.Tk(screenName=display) if display else tk.Tk()
    except tk.TclError as fehler:
        pytest.skip(f"Tk kann kein Fenster öffnen: {fehler}")
    skalierung_vorher = float(root.tk.call("tk", "scaling"))
    app = None
    try:
        if nachgestellt:
            echt = (root.winfo_screenwidth(), root.winfo_screenheight())
            if echt[0] < breite or echt[1] < hoehe:
                pytest.skip(f"kein Display {bildschirm} (Xvfb) und der echte Bildschirm ({echt[0]}x{echt[1]}) ist "
                            f"kleiner – {bildschirm} lässt sich hier nicht nachstellen")
            # Bildschirmgröße nachstellen: das Fenster bekommt die Größe, die die App für diesen Bildschirm wählt
            root.winfo_screenwidth = lambda: breite
            root.winfo_screenheight = lambda: hoehe
            monkeypatch.setattr(gui.AnonymisiererApp, "_maximieren", lambda self: None)
        root.tk.willdispatch()
        root.tk.call("tk", "scaling", skalierung)
        app = gui.AnonymisiererApp(root, einstellungen={"hinweis_gelesen": True})
        monkeypatch.setattr(app, "_kennwort_abfragen", lambda pfad, fehlversuch=False: "geheim")
        dialoge.antwort = True                                   # Foto als PDF übernehmen
        pumpe(root, timeout=0.2)
        app._pdfs_hinzufuegen([str(auswahl(umgebung["tmp"] / "Kunde Mustermann"))])
        for pdf in list(app.dateien):
            funde = [{"kategorie": k, "anzeige": a, "text": t, "ersatz": e, "seiten": [1], "anzahl": 1,
                      "kontext": c} for k, a, t, e, c in FUNDE]
            ergebnis = {"datei": pdf, "funde": funde, "warnungen": [], "hinweise": [], "fehler": None, "seiten": 2,
                        "ocr_seiten": 0, "ocr_cache": {}}
            app.analyse_ergebnisse[pdf] = ergebnis
            app._baum_datei_fuellen(pdf, ergebnis)
        app._start_knopf_aktualisieren()
        pumpe(root, timeout=0.6)
        root.update_idletasks()
        root.update()
        _screenshot(root, display, _screenshot_ordner(tmp_path_factory) / f"layout_{bildschirm}_{prozent}.png")

        fenster_h, fenster_w = root.winfo_height(), root.winfo_width()
        assert fenster_w <= breite and fenster_h <= hoehe - 60, "Fenster passt nicht auf den Bildschirm"
        hinweis = app.datei_hinweis
        text = hinweis.cget("text")
        assert "NICHT geprüft" in text, text
        assert len(app.dateien) == 3 and len(app.nicht_geprueft) == 1

        # Hinweiszeile, Drop-Zone, alle Knöpfe: ganz im Fenster, im Einstellbereich ganz im sichtbaren Teil
        knoepfe = [w for w in app.datei_knoepfe.pack_slaves() if isinstance(w, tk.Button)]
        assert len(knoepfe) == 3
        liste_knoepfe = [w for w in app.vorschau_knopf.master.pack_slaves() if isinstance(w, tk.Button)]
        assert len(liste_knoepfe) == 4
        canvas_oben = app.oben_canvas.winfo_rooty() - root.winfo_rooty()
        canvas_unten = canvas_oben + app.oben_canvas.winfo_height()
        assert float(app.oben_canvas.yview()[0]) == 0.0, "der Einstellbereich ist nicht ganz nach oben gerollt"
        pruefen = [("Hinweiszeile", hinweis), ("Drop-Zone", app.drop_zone), ("Fundliste", app.baum),
                   ("Hinweiskasten", app.hinweis_kasten), ("Protokoll", app.protokoll),
                   ("Statuszeile", app.status_label), ("Fortschritt", app.fortschritt),
                   ("Analysieren", app.analyse_knopf), ("Schwärzen", app.start_knopf),
                   ("Abbrechen", app.abbrechen_knopf), ("Ergebnisordner", app.ordner_knopf)]
        pruefen += [(k.cget("text"), k) for k in knoepfe + liste_knoepfe]
        for name, w in pruefen:
            assert w.winfo_ismapped(), f"{name} nicht sichtbar"
            oben, unten, links, rechts = lage(root, w)
            assert 0 <= oben and unten <= fenster_h and 0 <= links and rechts <= fenster_w, \
                f"{name} ragt aus dem Fenster ({oben}..{unten}, {links}..{rechts} bei {fenster_w}x{fenster_h})"
            if im_einstellbereich(app, w):
                assert canvas_oben <= oben and unten <= canvas_unten, \
                    f"{name} nur nach Scrollen sichtbar ({oben}..{unten}, Einstellbereich {canvas_oben}..{canvas_unten})"
            if isinstance(w, (tk.Label, tk.Button)):
                assert w.winfo_reqwidth() <= w.winfo_width() + 2, f"{name} seitlich abgeschnitten"
        # Hinweiszeile: umgebrochen statt abgeschnitten, ganze Höhe sichtbar
        assert hinweis.winfo_height() >= hinweis.winfo_reqheight()
        # Fundliste: genug ganze Zeilen; waagrechte Bildlaufleiste nur, wenn die Spalten nicht passen
        zeilen = ganze_zeilen(app)
        assert zeilen >= mindestzeilen, f"Fundliste zeigt nur {zeilen} ganze Zeilen (mindestens {mindestzeilen})"
        spalten = sum(app.baum.column(sp, "width") for sp in ("#0",) + gui.SPALTEN)
        if spalten <= app.baum.winfo_width() - 2:
            assert not app.baum_roll_x.winfo_ismapped(), "Bildlaufleiste ohne Not – sie kostet eine Zeile"
        # erste Spalte: Dateiname samt Zusatz passt, der Zusatz steht da
        breite0 = app.baum.column("#0", "width")
        zusaetze = {"Kontoauszug": "(Kennwort entfernt)", "Ausweis": "(Bild → PDF)", "Police": ".pdf"}
        for iid in app.zeilen:
            zeile = app.baum.item(iid, "text")
            anfang = next(a for a in zusaetze if a in app.beschriftungen[iid])
            assert zeile.endswith(zusaetze[anfang]) and zeile.split("  ", 1)[1][:4] == anfang[:4], zeile
            assert app.f_fett.measure(zeile) + app._px(gui.SPALTE0_EINZUG) <= breite0 + 1, (zeile, breite0)
        # keine Zeile des Einstellbereichs am unteren Rand mittendurch geschnitten
        for karte in app.oben.pack_slaves():
            for kind in karte.pack_slaves():
                oben, unten, _, _ = lage(root, kind)
                assert not (oben < canvas_unten - 2 and unten > canvas_unten + 2), \
                    f"Zeile {kind} am Rand des Einstellbereichs halb abgeschnitten ({oben}..{unten}, {canvas_unten})"
        # großer Titel nur, wenn Platz ist; der Programmname steht immer in der Titelleiste
        assert app.titel.winfo_ismapped() == (fenster_h >= app._px(gui.FENSTER_KLEIN_HOEHE))
        assert root.title().startswith("PDF-Anonymisierer")
    finally:
        try:
            if app is not None:
                app.beendet = True
            root.tk.call("tk", "scaling", skalierung_vorher)
            root.destroy()
        except tk.TclError:
            pass
        _display_wiederherstellen(display_vorher)


def test_name_einpassen_behaelt_anfang_endung_und_zusatz():
    def messen(text):                  # 7 Pixel je Zeichen
        return 7 * len(text)
    voll = gui.name_einpassen("Kontoauszug_Sparkasse_Juni.pdf", " (Kennwort entfernt)", 1000, messen)
    assert voll == "Kontoauszug_Sparkasse_Juni.pdf (Kennwort entfernt)"
    kurz = gui.name_einpassen("Kontoauszug_Sparkasse_Juni.pdf", " (Kennwort entfernt)", 7 * 35, messen)
    assert kurz.endswith(".pdf (Kennwort entfernt)") and kurz.startswith("Kont") and "…" in kurz
    assert messen(kurz) <= 7 * 35
    assert gui.name_einpassen("Ausweis.jpg", " (Bild → PDF)", 7 * 5, messen) == "… (Bild → PDF)"
    ohne_endung = gui.name_einpassen("Portal_Download_ohne_Endung", "", 7 * 12, messen)
    assert ohne_endung.startswith("Port") and ohne_endung.endswith("ung") and len(ohne_endung) <= 12
