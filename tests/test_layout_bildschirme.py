"""Hauptfenster auf kleinen Laptop-Bildschirmen (Runde 3, Paket „vorschau-oberflaeche“) und die Prüfspalten der
Fundliste (Runde 3a).

Befund Runde 3: auf 1366x768 bei 150 % war der Einstellbereich nur 90 Pixel hoch – die Hinweiszeile zur
Dateiauswahl, die die NICHT geprüften Dateien nennt, lag unsichtbar darunter (bei 125 % halb sichtbar), die
Fundliste zeigte eine Zeile, und die erste Spalte schnitt „(Bild → PDF)“ / „(Kennwort entfernt)“ ab.

Befund Runde 3a: die Korrektur ließ die erste Spalte mit dem längsten Dateinamen samt Zusatz wachsen – auf Kosten
von „Gefundener Text“ und „Kontext“, die selbst auf 1920x1080 bei 100/150/200 % auf ihrer Mindestbreite standen: die
Kontextspalte zeigte den Fund nicht mehr, IBAN und E-Mail waren früher abgeschnitten, und von Hand verbreitern half
nicht. Jetzt gehen die Prüfspalten vor (gui.spalten_verteilen), und der Zusatz steht in der Kontextspalte der
Dateizeile.

Geprüft wird hier für 1366x768 bei 100/125/150 %, 1024x768 bei 100 % und 1920x1080 bei 100/150/200 % mit einer
typischen Auswahl (PDF, PDF mit Kennwort, Foto, Mail = nicht geprüft) und Funden:
  * Hinweiszeile, Drop-Zone und alle Knöpfe (Dateien, Liste, Aktionsleiste) liegen ohne Scrollen ganz im Fenster
    bzw. im sichtbaren Teil des Einstellbereichs; die Hinweiszeile ist weder seitlich noch unten abgeschnitten,
  * die Fundliste zeigt mindestens so viele ganze Zeilen wie angegeben (150 % auf 1366x768: drei),
  * die erste Spalte zeigt jeden Dateinamen vollständig oder in der Mitte gekürzt (Anfang und Endung bleiben); der
    Zusatz „Kennwort entfernt“ / „Bild → PDF“ steht vollständig sichtbar in der Kontextspalte der Dateizeile,
  * „Gefundener Text“ und „Kontext“: die erste Spalte ist nur dann breiter als ihr Entwurf, wenn beide ihre
    Komfortbreite haben; sonst bekommen beide allen übrigen Platz (wie vor Runde 3); der Fund steht im sichtbaren
    Teil der Kontextspalte,
  * keine Zeile des Einstellbereichs wird am unteren Rand mittendurch geschnitten, und die waagrechte
    Bildlaufleiste der Liste erscheint nur, wenn die Spalten nicht passen.
Dazu dieselben Bildschirme maximiert (so starten 1366x768 und 1920x1080 ab 125 % unter Windows; Xvfb hat keinen
Fenstermanager, die Größe wird gesetzt): bei 100 % sind IBAN, E-Mail und der Fund im Kontext ganz zu sehen und die
Dateinamen ungekürzt. Und: „Gefundener Text“ lässt sich von Hand breiter ziehen, die Breite bleibt bei einer
Höhenänderung stehen.
Die Skalierung wird wie in der App über „tk scaling“ nachgestellt (4/3 = Windows 100 %). Unter Linux laufen die Fälle
auf Xvfb-Displays der jeweiligen Größe (:98 = 1366x768, :97 = 1024x768; bei Bedarf gestartet); ohne Xvfb (Windows)
wird die Bildschirmgröße nachgestellt, wenn der echte Bildschirm groß genug ist, sonst wird mit Begründung
übersprungen. Ein Bildschirmfoto je Fall landet im Screenshot-Ordner (CI-Artefakt).
"""

import contextlib
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
# maximiert: (Bildschirm, Breite, Höhe, tk scaling, Prozent, alles ganz zu sehen?) – Fenster = Bildschirm ohne
# Taskleiste und Titelleiste (TASKLEISTE)
MAXIMIERT = [
    ("1920x1080", 1920, 1080, 4 / 3, 100, True),
    ("1920x1080", 1920, 1080, 5 / 3, 125, False),
    ("1920x1080", 1920, 1080, 2.0, 150, False),
    ("1920x1080", 1920, 1080, 8 / 3, 200, False),
    ("1366x768", 1366, 768, 4 / 3, 100, True),
    ("1366x768", 1366, 768, 5 / 3, 125, False),
    ("1366x768", 1366, 768, 2.0, 150, False),
]
TASKLEISTE = 70
DISPLAYS = {(1366, 768): (":98",), (1024, 768): (":97",), (1920, 1080): (":96", ":99", ":95")}
_GESTARTET: list = []
# Funde mit Kontext wie aus der Engine (»Fund« mit Text davor und danach)
FUNDE = [("namen", "Name", "Max Mustermann", "[PERSON A]", "Sehr geehrter Herr »Max Mustermann«, wir"),
         ("telefon", "Telefonnummern", "0171 2345678", "[TELEFON]", "Tel. »0171 2345678«, E-Mail"),
         ("email", "E-Mail-Adressen", "max.mustermann@example.de", "[E-MAIL]",
          "erreichbar unter »max.mustermann@example.de« oder"),
         ("iban", "IBAN", "DE89 3704 0044 0532 0130 00", "[IBAN]",
          "Bankverbindung IBAN: »DE89 3704 0044 0532 0130 00« BIC"),
         ("adresse", "Anschrift", "Hauptstraße 12a", "[STRASSE]", "wohnhaft »Hauptstraße 12a«, 90402"),
         ("geburtsdatum", "Geburtsdatum", "02.09.1983", "[GEBURTSDATUM]", "geb. am »02.09.1983« in"),
         ("vertragsnummer", "Vertragsnummern", "LV-2024-887766", "[VERTRAG-NR]", "Schein-Nr. »LV-2024-887766« vom")]
# Innenabstand einer Zelle (links + rechts), großzügig gerechnet: ttk schneidet den Text am Zellenrand ab
ZELLENRAND = 10


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


def auswahl(ordner: Path, ohne_endung: bool = False) -> Path:
    """Typische Auswahl eines Maklers: Police (langer Name), PDF mit Kennwort, Ausweisfoto, eine Mail – auf Wunsch
    dazu eine PDF ohne Endung (Download aus einem Kundenportal)."""
    ordner.mkdir(parents=True)
    doc = fitz.open()
    doc.new_page().insert_text((60, 80), "Versicherungsnehmer: Max Mustermann", fontsize=11)
    doc.save(ordner / "Police_Lebensversicherung_Mustermann_Hauptvertrag_2024.pdf")
    doc.save(ordner / "Kontoauszug_Sparkasse_Nuernberg_Juni.pdf", encryption=fitz.PDF_ENCRYPT_AES_256,
             user_pw="geheim", owner_pw="geheim")
    if ohne_endung:
        doc.save(ordner / "Portal_Download")
    doc.close()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 260), False)
    pix.clear_with(235)
    (ordner / "Ausweis_Foto_Mustermann.jpg").write_bytes(pix.tobytes("jpg"))
    (ordner / "Mail_an_Makler_Rueckfrage.msg").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600)
    return ordner


def funde_eintragen(app):
    """Jede Datei bekommt dieselben sieben Funde (wie nach einer Analyse)."""
    for pdf in list(app.dateien):
        funde = [{"kategorie": k, "anzeige": a, "text": t, "ersatz": e, "seiten": [1], "anzahl": 1,
                  "kontext": c} for k, a, t, e, c in FUNDE]
        ergebnis = {"datei": pdf, "funde": funde, "warnungen": [], "hinweise": [], "fehler": None, "seiten": 2,
                    "ocr_seiten": 0, "ocr_cache": {}}
        app.analyse_ergebnisse[pdf] = ergebnis
        app._baum_datei_fuellen(pdf, ergebnis)
    app._start_knopf_aktualisieren()


@contextlib.contextmanager
def hauptfenster(breite, hoehe, skalierung, umgebung, dialoge, monkeypatch, fenster=None, ohne_endung=False):
    """Hauptfenster auf einem Display dieser Größe (unter Windows nachgestellt) mit der typischen Auswahl und ihren
    Funden; liefert (root, app, display). fenster=(b, h): Fenstergröße vor dem Hinzufügen setzen (Maximieren
    nachstellen)."""
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
                pytest.skip(f"kein Display {breite}x{hoehe} (Xvfb) und der echte Bildschirm ({echt[0]}x{echt[1]}) "
                            f"ist kleiner – {breite}x{hoehe} lässt sich hier nicht nachstellen")
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
        if fenster:
            root.geometry(f"{fenster[0]}x{fenster[1]}+0+0")
            pumpe(root, timeout=0.4)
        app._pdfs_hinzufuegen([str(auswahl(umgebung["tmp"] / "Kunde Mustermann", ohne_endung))])
        funde_eintragen(app)
        pumpe(root, timeout=0.6)
        root.update_idletasks()
        root.update()
        yield root, app, display
    finally:
        try:
            if app is not None:
                app.beendet = True
            root.tk.call("tk", "scaling", skalierung_vorher)
            root.destroy()
        except tk.TclError:
            pass
        _display_wiederherstellen(display_vorher)


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


def spalten(app) -> dict:
    return {sp: app.baum.column(sp, "width") for sp in ("#0",) + gui.SPALTEN}


def sichtbar(app, text: str, breite: int) -> str:
    """Der Teil von text, der in eine Zelle dieser Breite passt (Schrift der Fundliste)."""
    n = len(text)
    while n and app.f_normal.measure(text[:n]) > breite - ZELLENRAND:
        n -= 1
    return text[:n]


def fundzeilen(app) -> dict:
    """{Kategorie: (Gefundener Text, Kontext)} der Fundzeilen der ersten Datei."""
    datei = app.baum.get_children("")[0]
    return {app.baum.set(k, "kategorie").lstrip("⚑⚕ "): (app.baum.set(k, "text"), app.baum.set(k, "kontext"))
            for k in app.baum.get_children(datei)}


def pruefspalten_pruefen(app):
    """Befund Runde 3a: die erste Spalte ist nur dann breiter als ihr Entwurf, wenn „Gefundener Text“ und „Kontext“
    ihre Komfortbreite haben; beide nie unter ihrer Mindestbreite; der Fund steht im sichtbaren Teil der
    Kontextspalte."""
    b = spalten(app)
    mindest = {sp: app.baum.column(sp, "minwidth") for sp in ("text", "kontext")}
    komfort = {sp: app._px(gui.SPALTEN_KOMFORT[sp]) for sp in ("text", "kontext")}
    assert mindest == {"text": app._px(130), "kontext": app._px(160)}, mindest
    for sp in ("text", "kontext"):
        assert b[sp] >= mindest[sp], (sp, b)
    if b["#0"] > app._px(gui.SPALTEN_MASSE["#0"][0]) + 1:
        assert b["text"] >= komfort["text"] - 1 and b["kontext"] >= komfort["kontext"] - 1, \
            f"erste Spalte {b['#0']} px breit, die Prüfspalten aber nur {b['text']}/{b['kontext']} px"
    _, kontext_name = fundzeilen(app)["Name"]
    assert "»Max" in sichtbar(app, kontext_name, b["kontext"]), \
        f"Kontextspalte ({b['kontext']} px) zeigt den Fund nicht: {sichtbar(app, kontext_name, b['kontext'])!r}"


def datei_zeilen_pruefen(app):
    """Erste Spalte: Name vollständig oder in der Mitte gekürzt (Anfang und Endung bleiben), passt in die Spalte;
    Zusatz („Kennwort entfernt“ / „Bild → PDF“) vollständig sichtbar in der Kontextspalte der Dateizeile."""
    breite0, breite_kontext = app.baum.column("#0", "width"), app.baum.column("kontext", "width")
    erwartet = {"Kontoauszug": (".pdf", "Kennwort entfernt"), "Ausweis": (".jpg", "Bild → PDF"),
                "Police": (".pdf", "")}
    for iid in app.zeilen:
        zeile = app.baum.item(iid, "text")
        anfang = next(a for a in erwartet if a in app.beschriftungen[iid])
        endung, zusatz = erwartet[anfang]
        name = zeile.split("  ", 1)[1]
        assert name.endswith(endung) and name[:4] == anfang[:4], zeile
        assert app.f_fett.measure(zeile) + app._px(gui.SPALTE0_EINZUG) <= breite0 + 1, (zeile, breite0)
        assert app.baum.set(iid, "kontext") == zusatz, (zeile, app.baum.set(iid, "kontext"))
        assert sichtbar(app, zusatz, breite_kontext) == zusatz, (zusatz, breite_kontext)
        if zusatz:                                   # Dialoge und Fenstertitel tragen den Zusatz hinter dem Namen
            assert app.beschriftungen[iid].endswith(f"({zusatz})")


@pytest.mark.parametrize("bildschirm, breite, hoehe, skalierung, prozent, mindestzeilen", SZENARIEN,
                         ids=[f"{s[0]}_{s[4]}" for s in SZENARIEN])
def test_hinweiszeile_fundliste_und_knoepfe_ohne_scrollen(bildschirm, breite, hoehe, skalierung, prozent,
                                                         mindestzeilen, umgebung, dialoge, monkeypatch,
                                                         tmp_path_factory):
    with hauptfenster(breite, hoehe, skalierung, umgebung, dialoge, monkeypatch) as (root, app, display):
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
        summe = sum(spalten(app).values())
        if summe <= app.baum.winfo_width() - 2:
            assert not app.baum_roll_x.winfo_ismapped(), "Bildlaufleiste ohne Not – sie kostet eine Zeile"
        # erste Spalte: Dateiname passt (Anfang und Endung bleiben), der Zusatz steht ganz in der Kontextspalte
        datei_zeilen_pruefen(app)
        # Prüfspalten: nicht mehr auf der Mindestbreite, solange die erste Spalte mehr als ihren Entwurf hat
        pruefspalten_pruefen(app)
        # keine Zeile des Einstellbereichs am unteren Rand mittendurch geschnitten
        for karte in app.oben.pack_slaves():
            for kind in karte.pack_slaves():
                oben, unten, _, _ = lage(root, kind)
                assert not (oben < canvas_unten - 2 and unten > canvas_unten + 2), \
                    f"Zeile {kind} am Rand des Einstellbereichs halb abgeschnitten ({oben}..{unten}, {canvas_unten})"
        # großer Titel nur, wenn Platz ist; der Programmname steht immer in der Titelleiste
        assert app.titel.winfo_ismapped() == (fenster_h >= app._px(gui.FENSTER_KLEIN_HOEHE))
        assert root.title().startswith("PDF-Anonymisierer")


@pytest.mark.parametrize("bildschirm, breite, hoehe, skalierung, prozent, alles_ganz", MAXIMIERT,
                         ids=[f"{s[0]}_{s[4]}_maximiert" for s in MAXIMIERT])
def test_pruefspalten_im_maximierten_fenster(bildschirm, breite, hoehe, skalierung, prozent, alles_ganz,
                                             umgebung, dialoge, monkeypatch, tmp_path_factory):
    """Befund Runde 3a (maximiert: 1920x1080 bei 200 % zeigte 221/205 px statt 342/449, 1366x768 bei 125 % 150/197
    px): die erste Spalte wächst erst, wenn beide Prüfspalten ihre Komfortbreite haben. Bei 100 % reicht der Platz
    für alles: IBAN und E-Mail ganz in „Gefundener Text“, der ganze Fund im Kontext, die Dateinamen ungekürzt."""
    fenster = (breite, hoehe - TASKLEISTE)
    with hauptfenster(breite, hoehe, skalierung, umgebung, dialoge, monkeypatch, fenster=fenster) as \
            (root, app, display):
        _screenshot(root, display, _screenshot_ordner(tmp_path_factory) / f"layout_{bildschirm}_{prozent}_max.png")
        assert (root.winfo_width(), root.winfo_height()) == fenster
        assert sum(spalten(app).values()) <= app.baum.winfo_width() - 2 and not app.baum_roll_x.winfo_ismapped()
        datei_zeilen_pruefen(app)
        pruefspalten_pruefen(app)
        if alles_ganz:
            b = spalten(app)
            zeilen = fundzeilen(app)
            for kategorie in ("IBAN", "E-Mail-Adressen", "Vertragsnummern"):
                text, _ = zeilen[kategorie]
                assert sichtbar(app, text, b["text"]) == text, (kategorie, b["text"])
            _, kontext = zeilen["Name"]
            assert "»Max Mustermann«" in sichtbar(app, kontext, b["kontext"]), (kontext, b["kontext"])
            for iid in app.zeilen:
                assert "…" not in app.baum.item(iid, "text"), app.baum.item(iid, "text")


def trenner_ziehen(app, spalte: str, weg: int):
    """Den rechten Rand der Spalte mit der Maus um weg Pixel ziehen – mit den Ereignissen, auf die ttk reagiert
    (Drücken auf dem Trenner in der Kopfzeile, Ziehen, Loslassen), also auch unter Windows ohne Hilfsprogramm."""
    baum = app.baum
    reihe = ("#0",) + gui.SPALTEN
    x = sum(baum.column(sp, "width") for sp in reihe[:reihe.index(spalte) + 1]) - 1
    y = next((y for y in range(2, 40) if baum.identify_region(x, y) == "separator"), None)
    assert y is not None, f"kein Trenner rechts von {spalte} bei x={x}"
    baum.event_generate("<ButtonPress-1>", x=x, y=y)
    for schritt in range(1, 11):
        baum.event_generate("<B1-Motion>", x=x + weg * schritt // 10, y=y)
        app.root.update()
    baum.event_generate("<ButtonRelease-1>", x=x + weg, y=y)
    pumpe(app.root, timeout=0.3)


def test_gefundener_text_laesst_sich_von_hand_verbreitern(umgebung, dialoge, monkeypatch):
    """Befund Runde 3a: von Hand verbreitern half nicht – ttk holt den Platz beim Loslassen aus den dehnbaren
    Spalten, „Kontext“ stand schon auf der Mindestbreite und die Dateispalte war nicht dehnbar. Jetzt: ein Zug am
    rechten Rand von „Gefundener Text“ (Startfenster 1920x1080 bei 100 %) nimmt sich den Spielraum von „Kontext“ und
    der Dateispalte bis zu deren Mindestbreite – dann ist die ganze IBAN zu sehen; die Dateinamen passen sich der
    schmaleren ersten Spalte an. Ändert sich nur die Höhe der Liste, bleiben die gezogenen Breiten; erst eine andere
    Breite verteilt neu."""
    with hauptfenster(1920, 1080, 4 / 3, umgebung, dialoge, monkeypatch) as (root, app, display):
        baum = app.baum
        vorher = spalten(app)
        spielraum = sum(vorher[sp] - baum.column(sp, "minwidth") for sp in ("#0", "kontext"))
        assert spielraum >= app._px(40), (vorher, "kein Spielraum – der Test prüfte nichts")
        iban, _ = fundzeilen(app)["IBAN"]
        assert sichtbar(app, iban, vorher["text"]) != iban            # vorher abgeschnitten

        trenner_ziehen(app, "text", app._px(300))
        nachher = spalten(app)
        assert nachher["text"] >= vorher["text"] + spielraum - 2, (vorher, nachher)
        assert sichtbar(app, iban, nachher["text"]) == iban, nachher["text"]
        if sum(nachher.values()) <= baum.winfo_width() - 2:
            # Tk 8.6.14: beim Loslassen („drop“) holt ttk den Platz aus den dehnbaren Spalten, die Summe bleibt
            assert nachher["kontext"] == baum.column("kontext", "minwidth") and \
                nachher["#0"] == baum.column("#0", "minwidth"), nachher
        else:                                       # Tk ohne „drop“: breiter als die Liste – dann mit Bildlaufleiste
            assert app.baum_roll_x.winfo_ismapped(), "Spalten breiter als die Liste, aber keine Bildlaufleiste"
        for iid in app.zeilen:                                            # Namen an die schmalere Spalte angepasst
            zeile = baum.item(iid, "text")
            assert app.f_fett.measure(zeile) + app._px(gui.SPALTE0_EINZUG) <= nachher["#0"] + 1, zeile

        # nur die Höhe ändert sich (Fenster niedriger): die gezogenen Breiten bleiben
        b, h, hoehe_liste = root.winfo_width(), root.winfo_height(), baum.winfo_height()
        root.geometry(f"{b}x{h - app._px(60)}")
        pumpe(root, timeout=0.5)
        assert baum.winfo_height() < hoehe_liste
        assert spalten(app) == nachher

        # andere Breite: neu verteilt, die Prüfspalten wieder nach spalten_verteilen
        root.geometry(f"{b + app._px(40)}x{h - app._px(60)}")
        pumpe(root, timeout=0.5)
        neu = spalten(app)
        assert neu != nachher and neu["#0"] > nachher["#0"]
        # die Liste ist gefüllt, ohne überzustehen (die App lässt 4 px Rand, ttk verteilt den Rest selbst)
        assert baum.winfo_width() - 6 <= sum(neu.values()) <= baum.winfo_width() - 2, (neu, baum.winfo_width())
        assert not app.baum_roll_x.winfo_ismapped()
        pruefspalten_pruefen(app)
        datei_zeilen_pruefen(app)


def test_zusatz_steht_in_der_kontextspalte_der_dateizeile(umgebung, dialoge, monkeypatch):
    """Befund Runde 3a: der Zusatz musste nicht mehr in die erste Spalte – „Kennwort entfernt“, „Bild → PDF“ und
    „PDF ohne Endung“ stehen in der (sonst leeren) Kontextspalte der Dateizeile: vor und nach der Analyse und nach
    dem Schwärzen ohne Besonderheit; nennt die Ausgabe einen Grund („prüfen“, Fehler), steht dort der Grund."""
    with hauptfenster(1920, 1080, 4 / 3, umgebung, dialoge, monkeypatch, ohne_endung=True) as (root, app, display):
        nach_name = {pdf.name: pdf for pdf in app.dateien}
        assert set(nach_name) == {"Police_Lebensversicherung_Mustermann_Hauptvertrag_2024.pdf",
                                  "Kontoauszug_Sparkasse_Nuernberg_Juni.pdf", "Ausweis_Foto_Mustermann.jpg",
                                  "Portal_Download"}
        erwartet = {"Police_Lebensversicherung_Mustermann_Hauptvertrag_2024.pdf": "",
                    "Kontoauszug_Sparkasse_Nuernberg_Juni.pdf": "Kennwort entfernt",
                    "Ausweis_Foto_Mustermann.jpg": "Bild → PDF", "Portal_Download": "PDF ohne Endung"}
        for name, zusatz in erwartet.items():
            assert app.baum.set(str(nach_name[name]), "kontext") == zusatz, name
        # neue Dateien: die Kontextspalte bleibt beim Neuaufbau der Beschriftungen richtig
        app._beschriftungen_aktualisieren()
        assert {n: app.baum.set(str(p), "kontext") for n, p in nach_name.items()} == erwartet

        konto = nach_name["Kontoauszug_Sparkasse_Nuernberg_Juni.pdf"]
        app.ausgaben[konto] = {"pfad": umgebung["tmp"] / "anonym_02_PRUEFEN.pdf", "status": "pruefen",
                               "verdacht": [], "ergebnis": {}, "grund": "Restrisiko: 1 Stelle bitte prüfen"}
        app._ausgabe_zeile_setzen(konto)
        assert app.baum.set(str(konto), "kontext") == "Restrisiko: 1 Stelle bitte prüfen"
        assert app.baum.set(str(konto), "text").endswith("anonym_02_PRUEFEN.pdf")
        app.ausgaben[konto] = {"pfad": umgebung["tmp"] / "anonym_02.pdf", "status": "fertig", "verdacht": [],
                               "ergebnis": {}, "grund": ""}
        app._ausgabe_zeile_setzen(konto)
        assert app.baum.set(str(konto), "kontext") == "Kennwort entfernt"
        del app.ausgaben[konto]
        app._ausgabe_zeile_setzen(konto)
        assert app.baum.set(str(konto), "kontext") == "Kennwort entfernt" and app.baum.set(str(konto), "text") == ""


# ----------------------------------------------------------------------
# Spaltenverteilung ohne Fenster nachgerechnet (Maße bei 100 %)
# ----------------------------------------------------------------------
def _vorher(verfuegbar: int) -> tuple[float, float]:
    """„Gefundener Text“ und „Kontext“ vor Runde 3 (759adca) – Maßstab des Befunds: erste Spalte fest 185 px, die
    Prüfspalten teilen sich den Rest im Verhältnis 160 : 210, nie unter 130 bzw. 160 px (ohne über die Liste
    hinauszuragen: wer die Mindestbreite bekommt, nimmt sie dem anderen)."""
    rest = verfuegbar - (185 + 130 + 60 + 55 + 95)
    text = rest * 160 / 370
    text = min(max(130, text), rest - 160) if rest >= 290 else 130
    return text, max(160, rest - text)


def test_spalten_verteilen_pruefspalten_vor_der_dateispalte():
    """Befund Runde 3a, ohne Fenster nachgerechnet: mit langen Dateinamen (wie Makler sie vergeben) bekamen
    „Gefundener Text“ und „Kontext“ nur noch ihre Mindestbreite (1920x1080 bei 100 %: 111/101 statt 145/191 px)."""
    masse, komfort, anteil = gui.SPALTEN_MASSE, gui.SPALTEN_KOMFORT, gui.SPALTE0_MAX_ANTEIL
    assert {sp: masse[sp][1] for sp in ("text", "kontext")} == {"text": 130, "kontext": 160}
    lang, kurz = 470, 120            # Platzbedarf in der ersten Spalte: „Police_Lebensversicherung_…_2024.pdf“, „Police.pdf“
    # Startfenster 1920x1080 bei 100 % (Liste 861 px): wie vor Runde 3
    b = gui.spalten_verteilen(861, masse, komfort, lang, anteil)
    assert (b["#0"], b["text"], b["kontext"]) == (185, 145, 191) and sum(b.values()) == 861
    # kurze Namen: die erste Spalte gibt bis zu ihrer Mindestbreite ab
    b = gui.spalten_verteilen(861, masse, komfort, kurz, anteil)
    assert b["#0"] == 150 and b["text"] > 145 and b["kontext"] > 191
    # maximiert (Liste 1839 px): erst Komfortbreite, dann die erste Spalte bis zum Namen, der Rest wieder an beide
    b = gui.spalten_verteilen(1839, masse, komfort, lang, anteil)
    assert b["#0"] == lang and b["text"] > komfort["text"] and b["kontext"] > komfort["kontext"]
    # zu schmal für alle Mindestbreiten: alle auf der Mindestbreite (dann rollt die Liste waagrecht)
    b = gui.spalten_verteilen(600, masse, komfort, lang, anteil)
    assert b == {sp: m for sp, (_, m, _) in masse.items()}

    mindest = sum(m for _, m, _ in masse.values())
    for bedarf0 in (kurz, 185, 300, lang, 900):
        letzte = None
        for verfuegbar in range(500, 2600, 3):
            b = gui.spalten_verteilen(verfuegbar, masse, komfort, bedarf0, anteil)
            assert set(b) == set(masse)
            assert all(b[sp] >= m for sp, (_, m, _) in masse.items()), (verfuegbar, bedarf0, b)
            if verfuegbar >= mindest:
                assert sum(b.values()) == verfuegbar, (verfuegbar, bedarf0, b)
            assert b["#0"] <= max(150, bedarf0), (verfuegbar, bedarf0, b)       # nie breiter als nötig
            if b["#0"] > 185:                                                     # nur in echten Restplatz
                assert b["text"] >= komfort["text"] and b["kontext"] >= komfort["kontext"], (verfuegbar, b)
            # nie schmaler als vor Runde 3 – außer beide haben schon ihre Komfortbreite
            text_vorher, kontext_vorher = _vorher(verfuegbar)
            assert b["text"] >= min(text_vorher, komfort["text"]) - 1, (verfuegbar, bedarf0, b, text_vorher)
            assert b["kontext"] >= min(kontext_vorher, komfort["kontext"]) - 1, (verfuegbar, bedarf0, b)
            # mehr Platz nimmt den Prüfspalten nie etwas weg
            if letzte is not None:
                assert b["text"] >= letzte["text"] and b["kontext"] >= letzte["kontext"], (verfuegbar, letzte, b)
            letzte = b


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
