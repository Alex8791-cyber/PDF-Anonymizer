"""Runde 3a, Paket „ausgabe-status“ – bestätigte Prüfbefunde zu Runde 3:

1. Ein hell gedruckter Scan, auf dem die OCR nichts liest (Ausfall, Zeitüberschreitung, Bleistift, Handschrift), endete
   als „fertig – keine personenbezogenen Daten gefunden“: das Maß „Seite ohne Tinte“ (tintenanteil, Pixel < 180) hielt
   gut lesbaren hellen Text für leer. Jetzt: _PRUEFEN mit Grund „kein Text lesbar“; ein OCR-Ausfall zählt immer.
2. Zielordner = Laufwerks- oder Freigabe-Wurzel: die Zuordnungsdatei (Original-Dateinamen) lag im Ordner, der
   hochgeladen wird, nur mit Hinweis. Jetzt: im Programmordner; liegt sie doch im Ausgabeordner, immer eine Warnung.
3. Eine alte Zuordnungsdatei in ANSI-Kodierung ließ die Schwärzung NACH dem Ablegen der Ausgabe abbrechen („OHNE
   Ausgabedatei“, obwohl anonym_NN.pdf existierte) – bei jeder weiteren Datei. Jetzt: jede Kodierung wird gelesen.
5. „Freigabe vor Weitergabe“ (Standard): eine Datei ohne Fund zeigte nur „Freigabe ausstehend“.
"""

import os
import random
import statistics
import sys
from pathlib import Path

import pymupdf as fitz
import pytest

from anonymisierer import analyse, dateien, gui, schwaerzung
from anonymisierer import gui_attrappen as attrappen
from anonymisierer import ocr as ocr_modul
from anonymisierer.analyse import analysiere_pdf
from anonymisierer.schwaerzung import schwaerze_pdf
from test_ausgabe_status import _mit_meldung
from test_gui import _prozesszustand, app, dialoge, root, starte_lauf, umgebung  # noqa: F401
from test_robustheit_analyse import (NAME, NEUTRAL, STANDARD, Attrappe, bildseite, codes, textseiten,
                                     woerter_aus_zeilen)

gui_test = pytest.mark.skipif(not os.environ.get("DISPLAY") and sys.platform != "win32",
                              reason="kein Display (DISPLAY nicht gesetzt)")

KUNDE = ["Versicherungsnehmer: Max Mustermann", "Hauptstrasse 12, 50667 Koeln", "IBAN DE89 3704 0044 0532 0130 00",
         "Geburtsdatum 02.09.1983", "Telefon 0171 2345678"]
KEIN_TEXT = "kein Text lesbar – nichts konnte geprüft werden"
SEITE_UNGELESEN = "Seite {}: kein Text erkannt bzw. Texterkennung fehlgeschlagen"
AUSFALL = "Seite 1: OCR fehlgeschlagen (Zeitüberschreitung) – Seite nicht lesbar, bitte selbst prüfen."


# ----------------------------------------------------------------------
# Hilfen: Scans aus Pixeln, OCR-Attrappen
# ----------------------------------------------------------------------
def _seite_als_bild(quelle_seite, dpi=150) -> fitz.Document:
    pix = quelle_seite.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    doc = fitz.open()
    seite = doc.new_page(width=quelle_seite.rect.width, height=quelle_seite.rect.height)
    seite.insert_image(seite.rect, stream=pix.tobytes("png"))
    return doc


def heller_scan(grau: int, zeilen=KUNDE, groesse=11, dpi=150) -> fitz.Document:
    """Ein Scan (nur ein Bild) mit Text im Grauwert `grau` – für Menschen gut lesbar."""
    quelle = fitz.open()
    s = quelle.new_page()
    for i, z in enumerate(zeilen):
        s.insert_text((60, 100 + 22 * i), z, fontsize=groesse, color=(grau / 255,) * 3)
    return _seite_als_bild(s, dpi)


def gezeichneter_scan(zeichnen, dpi=150) -> fitz.Document:
    quelle = fitz.open()
    s = quelle.new_page()
    zeichnen(s)
    return _seite_als_bild(s, dpi)


def papier_scan(papier=240, streuung=3.0, breite=827, hoehe=1169, jpeg=None, seed=1) -> fitz.Document:
    """Leere Seite wie vom Scanner: graues Papier mit Rauschen (normalverteilt), wahlweise als JPEG."""
    verteilung = statistics.NormalDist(papier, streuung)
    tabelle = bytes(max(0, min(255, round(verteilung.inv_cdf((i + 0.5) / 256)))) for i in range(256))
    daten = random.Random(seed).randbytes(breite * hoehe).translate(tabelle)
    pix = fitz.Pixmap(fitz.csGRAY, breite, hoehe, daten, False)
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_image(seite.rect, stream=pix.tobytes("jpeg", jpg_quality=jpeg) if jpeg else pix.tobytes("png"))
    return doc


def speichern(doc: fitz.Document, pfad: Path) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    doc.save(pfad)
    doc.close()
    return pfad


class OcrOhneWoerter:
    """OCR-Attrappe, die nichts liest: mit `ausfall` wie der Dienst nach einem endgültigen Ausfall (Warnung, kein Wort),
    sonst fehlerfrei ohne ein einziges Wort (Bleistift, Handschrift). `woerter_je_seite`: Seiten, die gelesen werden."""

    def __init__(self, ausfall: bool = False, woerter_je_seite=None, ausfall_seiten=None):
        self.ausfall = ausfall
        self.ausfall_seiten = ausfall_seiten
        self.woerter_je_seite = woerter_je_seite or {}
        self.hinweise: list = []

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, **_):
        if seite_nr0 in self.woerter_je_seite:
            return list(self.woerter_je_seite[seite_nr0]), None
        if self.ausfall and (self.ausfall_seiten is None or seite_nr0 in self.ausfall_seiten):
            return [], AUSFALL.replace("Seite 1", f"Seite {seite_nr0 + 1}")
        return [], None

    def abbrechen(self):
        pass

    def schliessen(self):
        pass


class AusfallDienst(ocr_modul.OcrDienst):
    """Der echte OCR-Dienst, dessen Arbeiter endgültig ausfällt (Absturz bzw. Zeitüberschreitung nach den
    Wiederholungen): so läuft der echte Fehlerpfad von ergebnis() – Meldung OCR_FEHLER, kein Wort, das Ergebnis bleibt
    im Zwischenspeicher. Kein Hilfsprozess wird gestartet."""

    def vorab(self, *args, **kwargs):
        return 0

    def _warten(self, auftrag):
        raise RuntimeError("OCR-Prozess nicht verfügbar (Zeitüberschreitung)")


def gui_weg(pdf: Path, ocr, ziel: Path, mit_modell=True, freigabe=False) -> tuple:
    """Analyse und Schwärzung wie in der Oberfläche (gui._auftrag): nur angehakte Funde, Modell und Nebenkanäle."""
    e = analysiere_pdf(pdf, STANDARD, [], [], ocr=ocr)
    assert not e.get("fehler"), e.get("fehler")
    funde = [f for f in e["funde"] if not f.get("stellen") or any(st.get("an", True) for st in f["stellen"])]
    s = schwaerze_pdf(pdf, funde, ocr=ocr, ocr_cache=e.get("ocr_cache"), ziel_ordner=ziel,
                      modell=e["modell"] if mit_modell else None, nebenkanaele=e.get("nebenkanaele"),
                      freigabe_erforderlich=freigabe)
    return e, s


# ======================================================================
# 1. Heller Scan, auf dem die OCR nichts liest: nie „fertig“
# ======================================================================
@pytest.mark.parametrize("grau", [150, 160])
@pytest.mark.parametrize("ausfall", [False, True], ids=["nichts_gelesen", "ausfall"])
def test_heller_scan_ohne_ocr_woerter_endet_nie_fertig(tmp_path, grau, ausfall):
    """Befund 1: Grau 150/160 ist gut lesbar, das alte Maß (tintenanteil) hält die Seite aber für leer. Liefert die OCR
    keine Wörter, entsteht trotzdem eine _PRUEFEN-Ausgabe mit dem Grund „kein Text lesbar“ – mit und ohne Modell der
    Analyse, mit und ohne „Freigabe vor Weitergabe“ (dort nicht nur „Freigabe ausstehend“)."""
    pdf = speichern(heller_scan(grau), tmp_path / "Scan_Kunde.pdf")
    with fitz.open(pdf) as doc:
        assert analyse.tintenanteil(doc[0]) <= schwaerzung.TINTE_MIN          # der blinde Fleck des alten Maßes
        assert not analyse.seite_nachweislich_leer(doc[0])
    ocr = OcrOhneWoerter(ausfall=ausfall)
    for mit_modell in (True, False):
        for freigabe in (False, True):
            ziel = tmp_path / f"aus_{int(mit_modell)}{int(freigabe)}"
            e, s = gui_weg(pdf, ocr, ziel, mit_modell=mit_modell, freigabe=freigabe)
            assert "KEIN_TEXT" in codes(e) and e["funde"] == []
            assert s["ausgabe"] is not None and s["status"] == "pruefen", (mit_modell, freigabe, s["pruefen_gruende"])
            assert s["ausgabe"].name.endswith("_PRUEFEN.pdf")
            assert KEIN_TEXT in s["pruefen_gruende"] and SEITE_UNGELESEN.format(1) in s["pruefen_gruende"]
            assert "Freigabe ausstehend" not in s["pruefen_gruende"]
            assert any(m["code"] == "AUSGABE_PRUEFEN" and m["art"] == "warnung" for m in s["meldungen"])


def test_heller_scan_mit_echtem_ocr_ausfall_ist_pruefen(tmp_path):
    """Der echte Fehlerpfad des OCR-Dienstes (Arbeiter fällt endgültig aus): die Meldung OCR_FEHLER der Schwärzung
    selbst bleibt ein Grund – ein Ausfall wird nie als „leere Seite“ übergangen."""
    pdf = speichern(heller_scan(160), tmp_path / "Scan_Kunde.pdf")
    dienst = AusfallDienst()
    try:
        e, s = gui_weg(pdf, dienst, tmp_path / "aus")
    finally:
        dienst.schliessen()
    assert any(m["code"] == "OCR_FEHLER" and "fehlgeschlagen" in m["text"] for m in e["meldungen"])
    assert any(m["code"] == "OCR_FEHLER" and m["art"] == "warnung" for m in s["meldungen"])
    assert s["status"] == "pruefen" and KEIN_TEXT in s["pruefen_gruende"]
    assert SEITE_UNGELESEN.format(1) in s["pruefen_gruende"]


@pytest.mark.parametrize("ausfall", [False, True], ids=["nichts_gelesen", "ausfall"])
def test_heller_scan_auf_seite_zwei_macht_pruefen(tmp_path, ausfall):
    """Seitenvariante (gab es schon vor Runde 3): Seite 1 Text mit Fund, Seite 2 heller Scan ohne OCR-Wörter."""
    doc = fitz.open()
    seite = doc.new_page()
    for i, z in enumerate([f"Herrn {NAME}", "Hauptstraße 12", "50667 Köln", "", "Anlage: Schadenmeldung"]):
        seite.insert_text((60, 90 + 18 * i), z, fontsize=11)
    scan = heller_scan(160)
    doc.insert_pdf(scan)
    pdf = speichern(doc, tmp_path / "Brief_mit_Anlage.pdf")
    e, s = gui_weg(pdf, OcrOhneWoerter(ausfall=ausfall), tmp_path / "aus")
    assert e["funde"] and s["treffer"] > 0
    assert s["status"] == "pruefen" and SEITE_UNGELESEN.format(2) in s["pruefen_gruende"], s["pruefen_gruende"]


def _rueckseiten_pdf(tmp_path, rueckseite: fitz.Document) -> tuple:
    """Seite 1 ein gut gelesener Scan (OCR-Wörter der Attrappe), Seite 2 eine leere Rückseite."""
    zeilen = [f"Versicherungsnehmer {NAME} wohnhaft in der Hauptstraße 12 in 10115 Berlin",
              "wir bestätigen den Eingang Ihrer Unterlagen und die Änderung Ihres Vertrags zum Monatsende",
              "Mit freundlichen Grüßen Ihre Muster Versicherung AG Abteilung Leistung"]
    doc = gezeichneter_scan(lambda s: s.draw_rect(fitz.Rect(40, 60, 560, 120), color=None, fill=(0, 0, 0)))
    doc.insert_pdf(rueckseite)
    return speichern(doc, tmp_path / "Scan_mit_Rueckseite.pdf"), woerter_aus_zeilen(zeilen)


@pytest.mark.parametrize("rueckseite", [lambda: gezeichneter_scan(lambda s: None), lambda: papier_scan(jpeg=60)],
                         ids=["weiss", "papier_mit_rauschen"])
def test_leere_rueckseite_ist_auch_mit_modell_kein_grund(tmp_path, rueckseite):
    """Die einzige Ausnahme der Statusregel: die OCR liest (fehlerfrei) nichts auf einer nachweislich leeren Seite –
    hier mit dem Modell der Analyse, dessen Meldung „OCR hat keinen Text gelesen“ die Ausnahme am Text erkennt (ändert
    sich der Text im Seitenmodell, schlägt dieser Test an; die Rückseite würde dann _PRUEFEN, nie still „fertig“)."""
    pdf, woerter = _rueckseiten_pdf(tmp_path, rueckseite())
    ocr = OcrOhneWoerter(woerter_je_seite={0: woerter})
    e, s = gui_weg(pdf, ocr, tmp_path / "aus")
    meldung = next(m for m in e["meldungen"] if m["code"] == "OCR_FEHLER" and m["seite"] == 1)
    assert schwaerzung.OCR_NICHTS_GELESEN in meldung["text"]
    assert not any(g.startswith("Seite 2") for g in s["pruefen_gruende"]), s["pruefen_gruende"]


def test_ocr_ausfall_auf_leerer_rueckseite_zaehlt_immer(tmp_path):
    """Ein Ausfall der OCR ist nie „nichts gelesen“ – auch nicht auf einer leeren Seite."""
    pdf, woerter = _rueckseiten_pdf(tmp_path, gezeichneter_scan(lambda s: None))
    ocr = OcrOhneWoerter(ausfall=True, woerter_je_seite={0: woerter}, ausfall_seiten={1})
    for mit_modell in (True, False):
        e, s = gui_weg(pdf, ocr, tmp_path / f"aus{int(mit_modell)}", mit_modell=mit_modell)
        assert s["status"] == "pruefen" and SEITE_UNGELESEN.format(2) in s["pruefen_gruende"], s["pruefen_gruende"]


def test_leerer_scan_ist_kein_text_und_pruefen(tmp_path):
    """Ein Scan ist nie „eine Datei nur aus leeren Seiten“ (sein Bild ist gezeichnet): ohne jeden Text bleibt es bei
    KEIN_TEXT und _PRUEFEN – auch wenn die Seite leer aussieht (Vorschlag der Prüfung: „Scans nie ausnehmen“)."""
    pdf = speichern(papier_scan(), tmp_path / "Scan_leer.pdf")
    for mit_modell in (True, False):
        e, s = gui_weg(pdf, OcrOhneWoerter(), tmp_path / f"aus{int(mit_modell)}", mit_modell=mit_modell)
        assert "KEIN_TEXT" in codes(e) and "LEERE_SEITEN" not in codes(e)
        assert s["status"] == "pruefen" and KEIN_TEXT in s["pruefen_gruende"], s["pruefen_gruende"]


def test_mass_nachweislich_leer():
    """Das Maß „nachweislich leer“ (Kalibrierung im Bericht): leere Seiten mit Scanner-Rauschen, JPEG-Artefakten und
    Staub bleiben leer; heller Text bis Grau 230, ein einzelnes helles Wort, eine Bleistift-Unterschrift und eine
    Lochung nicht. Eine Seite ohne jeden Inhalt ist immer leer."""
    leer = {
        "ohne_inhalt": fitz.open(),
        "weiss": gezeichneter_scan(lambda s: None),
        "papier_rauschen": papier_scan(papier=240, streuung=3),
        "papier_jpeg": papier_scan(papier=230, streuung=6, jpeg=40),
        "staub": gezeichneter_scan(lambda s: [s.draw_circle(fitz.Point(50 + 20 * i, 80 + 30 * i), 0.4, color=None,
                                                            fill=(0.2,) * 3) for i in range(20)]),
    }
    leer["ohne_inhalt"].new_page()

    def unterschrift(grau):
        def zeichnen(s):
            punkte = [fitz.Point(320 + 4 * i, 700 + 12 * ((i * 7) % 5 - 2)) for i in range(40)]
            for a, b in zip(punkte, punkte[1:]):
                s.draw_line(a, b, color=(grau / 255,) * 3, width=0.8)
        return zeichnen

    nicht_leer = {f"text_grau{g}": heller_scan(g) for g in (150, 160, 200, 215, 230)}
    nicht_leer["ein_wort_grau215"] = heller_scan(215, ["Mustermann"])
    nicht_leer["bleistift_unterschrift"] = gezeichneter_scan(unterschrift(190))
    nicht_leer["lochung"] = gezeichneter_scan(lambda s: [s.draw_circle(fitz.Point(30, y), 8, color=None,
                                                                       fill=(0.1,) * 3) for y in (300, 540)])
    for name, doc in leer.items():
        assert analyse.seite_nachweislich_leer(doc[0]), name
    for name, doc in nicht_leer.items():
        assert not analyse.seite_nachweislich_leer(doc[0]), name
    assert analyse.nur_leere_seiten(leer["ohne_inhalt"]) and not analyse.nur_leere_seiten(leer["weiss"])


def test_mass_nachweislich_leer_im_zweifel_nein():
    class Kaputt:
        rect = fitz.Rect(0, 0, 595, 842)

        def get_bboxlog(self):
            return [("fill-image", (0, 0, 595, 842))]

        def get_pixmap(self, **_):
            raise RuntimeError("Rendern unmöglich")
    assert analyse.seite_nachweislich_leer(Kaputt()) is False


# ----------------------------------------------------------------------
# Die zentrale Regel auch auf Scan-Seiten (Befund 1: ihre Tests liefen nur auf Textseiten – dort ist
# „leere_scanseiten“ leer, die Ausnahme wurde also nie an ihrer Grenze geprüft)
# ----------------------------------------------------------------------
NICHTS_GELESEN_SEITE_2 = {"art": "warnung", "code": "OCR_FEHLER", "seite": 1,
                          "text": "Seite 2: OCR hat keinen Text gelesen — bitte manuell prüfen!"}


def _text_und_leere_rueckseite(tmp_path, rueckseite=None) -> Path:
    """Seite 1 Text ohne Personendaten, Seite 2 ein Scan – standardmäßig die leere Rückseite (weißes Bild)."""
    doc = fitz.open(textseiten(tmp_path / "text.pdf", NEUTRAL))
    with fitz.open(rueckseite or bildseite(tmp_path / "rueckseite.pdf", tinte=False)) as scan:
        doc.insert_pdf(scan)
    return speichern(doc, tmp_path / "Brief_mit_Rueckseite.pdf")


def test_leere_rueckseite_ohne_meldung_ist_fertig(tmp_path):
    """Ausgangslage der folgenden Tests: die OCR liest auf der leeren Rückseite (fehlerfrei) nichts – kein Grund."""
    pdf = _text_und_leere_rueckseite(tmp_path)
    with fitz.open(pdf) as doc:
        assert analyse.seite_nachweislich_leer(doc[1]) and not analyse.seite_nachweislich_leer(doc[0])
    for mit_analyse in (False, True):
        e = analysiere_pdf(pdf, STANDARD, [], [], ocr=Attrappe()) if mit_analyse else None
        if e is not None:
            assert NICHTS_GELESEN_SEITE_2["text"] in [m["text"] for m in e["meldungen"]]
        s = schwaerze_pdf(pdf, [], ocr=Attrappe(), modell=e["modell"] if e else None,
                          ziel_ordner=tmp_path / f"aus{int(mit_analyse)}")
        assert s["status"] == "fertig" and s["pruefen_gruende"] == [], s["pruefen_gruende"]


@pytest.mark.parametrize("code", sorted(c for c, (leck, _) in analyse.WARNUNGS_CODES.items() if leck)
                         + ["UNBEKANNTE_WARNUNG"])
def test_jede_leckrelevante_warnung_auf_leerer_scanseite_macht_pruefen(tmp_path, monkeypatch, code):
    """Die Ausnahme der Statusregel ist eng: auf der nachweislich leeren Rückseite macht JEDE leckrelevante Warnung die
    Ausgabe _PRUEFEN – auch OCR_FEHLER, solange sie nicht „fehlerfrei nichts gelesen“ meldet."""
    pdf = _text_und_leere_rueckseite(tmp_path)
    _mit_meldung(monkeypatch, {"art": "warnung", "code": code, "text": f"Seite 2: Testmeldung {code}", "seite": 1})
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert s["ausgabe"] is not None and s["status"] == "pruefen", (code, s["pruefen_gruende"])
    assert any(g.startswith("Seite 2: ") for g in s["pruefen_gruende"]), s["pruefen_gruende"]


@pytest.mark.parametrize("code", sorted(analyse.FEHLER_CODES) + ["UNBEKANNTER_FEHLER"])
def test_jede_fehler_meldung_auf_leerer_scanseite_endet_nie_fertig(tmp_path, monkeypatch, code):
    pdf = _text_und_leere_rueckseite(tmp_path)
    _mit_meldung(monkeypatch, {"art": "fehler", "code": code, "text": f"Seite 2: Testfehler {code}", "seite": 1})
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert s["status"] != "fertig"
    if s["ausgabe"] is not None:
        assert s["status"] == "pruefen" and s["pruefen_gruende"]


@pytest.mark.parametrize("fall", ["leere_rueckseite", "andere_seite", "heller_scan", "als_fehler"])
def test_ausnahme_nichts_gelesen_nur_auf_nachweislich_leerer_seite(tmp_path, monkeypatch, fall):
    """„OCR hat (fehlerfrei) nichts gelesen“ ist nur auf der nachweislich leeren Seite kein Grund – nicht für eine
    andere Seite, nicht auf einem hellen Scan (Grau 160) und nicht als Meldung der Art „fehler“."""
    rueckseite = speichern(heller_scan(160), tmp_path / "hell.pdf") if fall == "heller_scan" else None
    pdf = _text_und_leere_rueckseite(tmp_path, rueckseite)
    meldung = dict(NICHTS_GELESEN_SEITE_2)
    if fall == "andere_seite":
        meldung.update(seite=0, text="Seite 1: OCR hat keinen Text gelesen — bitte manuell prüfen!")
    if fall == "als_fehler":
        meldung["art"] = "fehler"
    _mit_meldung(monkeypatch, meldung)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    if fall == "leere_rueckseite":
        assert s["status"] == "fertig" and s["pruefen_gruende"] == [], s["pruefen_gruende"]
    else:
        assert s["status"] == "pruefen" and s["pruefen_gruende"], (fall, s["pruefen_gruende"])


# ======================================================================
# 2. Zuordnungsdatei bei Laufwerks- oder Freigabe-Wurzel
# ======================================================================
@pytest.fixture
def programmordner(tmp_path, monkeypatch):
    """Einstellungs- bzw. Programmordner im Temp-Ordner (Windows: APPDATA, sonst XDG_CONFIG_HOME)."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "appdata"))
    return dateien.zuordnungen_ordner()


def test_wurzel_hat_kein_daneben(tmp_path, programmordner):
    wurzel = Path(Path.cwd().anchor)                 # „/“ bzw. „C:\“ – wie E:\ oder \\server\freigabe\
    assert schwaerzung.ist_wurzel(wurzel)
    assert not schwaerzung.ist_wurzel(tmp_path) and not schwaerzung.ist_wurzel(Path("."))
    datei = schwaerzung.zuordnung_pfad(wurzel)
    assert datei.parent == programmordner and programmordner.is_relative_to(tmp_path)
    assert datei.name.startswith("_zuordnung_") and datei.suffix == ".txt"
    assert not schwaerzung.zuordnung_im_ausgabeordner(datei, wurzel)
    assert schwaerzung.zuordnung_im_ausgabeordner(wurzel / "_zuordnung.txt", wurzel)
    # der aktuelle Ordner („.“) ist kein Sonderfall: daneben, nicht darin
    assert schwaerzung.zuordnung_pfad(Path(".")) == Path.cwd().parent / f"_zuordnung_{Path.cwd().name}.txt"


def test_relativer_zielordner_zuordnung_daneben(tmp_path, monkeypatch):
    """Ein relativ eingetippter Zielordner („..“, „..\\Upload“): die Zuordnung liegt neben dem echten Ordner – nicht im
    aktuellen Ordner und nie im Zielordner selbst."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    monkeypatch.chdir(tmp_path / "a" / "b")
    assert schwaerzung.zuordnung_pfad(Path("..")) == tmp_path / "_zuordnung_a.txt"
    assert schwaerzung.zuordnung_pfad(Path("..") / "Upload") == tmp_path / "a" / "_zuordnung_Upload.txt"
    for ziel in (Path(".."), Path("..") / "Upload", Path(".")):
        assert not schwaerzung.zuordnung_im_ausgabeordner(schwaerzung.zuordnung_pfad(ziel), ziel)


def test_zuordnungen_ordner_liegt_neben_den_einstellungen(tmp_path, monkeypatch):
    """Der Programmordner der Zuordnungen folgt den Einstellungen (wie die Kundenliste) – eine Umleitung der
    Einstellungen (Tests, eigene Installation) leitet auch ihn um."""
    monkeypatch.setattr(dateien, "einstellungen_pfad", lambda: tmp_path / "konfig" / "einstellungen.json")
    assert dateien.zuordnungen_ordner() == tmp_path / "konfig" / "Zuordnungen"
    assert dateien.zuordnungen_ordner().parent == dateien.kundenliste_pfad().parent


def _als_wurzel(monkeypatch, ziel: Path):
    """Tut so, als sei `ziel` eine Laufwerkswurzel (E:\\ auf einem USB-Stick) – eine echte Wurzel ist im Test nicht
    beschreibbar."""
    echt = schwaerzung.ist_wurzel
    monkeypatch.setattr(schwaerzung, "ist_wurzel", lambda o: Path(o) == ziel or echt(o))


def test_schwaerzen_in_eine_wurzel_legt_die_zuordnung_in_den_programmordner(tmp_path, monkeypatch, programmordner):
    """Befund 2: Zielordner E:\\ – die Zuordnung (Original-Dateinamen) landete in E:\\, also im Ordner, der hochgeladen
    wird, mit bloßem Hinweis. Jetzt im Programmordner; eine alte _zuordnung.txt in der Wurzel wird dorthin übernommen
    (auch in ANSI-Kodierung) und aus der Wurzel gelöscht; Freigeben/Verwerfen führen die Datei dort nach."""
    ziel = tmp_path / "USB-Stick"
    ziel.mkdir()
    _als_wurzel(monkeypatch, ziel)
    (ziel / "_zuordnung.txt").write_bytes("anonym_01.pdf  <-  Antrag_Müller.pdf  (2026-01-01 10:00)\n".encode("cp1252"))
    (ziel / "anonym_01.pdf").write_bytes(b"%PDF-1.4 alt")
    pdf = textseiten(tmp_path / "Antrag_Mueller_Max.pdf", NEUTRAL)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe(), ziel_ordner=ziel, freigabe_erforderlich=True)
    assert s["fehler"] is None and s["ausgabe"].name == "anonym_02_PRUEFEN.pdf"
    assert sorted(p.name for p in ziel.iterdir()) == ["anonym_01.pdf", "anonym_02_PRUEFEN.pdf"]
    datei = schwaerzung.zuordnung_pfad(ziel)
    assert datei.parent == programmordner and datei.exists()
    zeilen = datei.read_text(encoding="utf-8").splitlines()
    assert zeilen[0].startswith("anonym_01.pdf  <-  Antrag_Müller.pdf")
    assert zeilen[1].startswith("anonym_02_PRUEFEN.pdf  <-  Antrag_Mueller_Max.pdf  (")
    meldung = next(m for m in s["meldungen"] if m["code"] == "ZUORDNUNG")
    assert meldung["art"] == "hinweis" and str(datei) in meldung["text"] and "Programmordner" in meldung["text"]
    neu = schwaerzung.freigeben(s["ausgabe"])
    assert datei.read_text(encoding="utf-8").splitlines()[1].startswith(f"{neu.name}  <-  Antrag_Mueller_Max.pdf")
    schwaerzung.verwerfen(neu)
    assert [z.split()[0] for z in datei.read_text(encoding="utf-8").splitlines()] == ["anonym_01.pdf"]


def test_zuordnung_im_ausgabeordner_ist_immer_eine_warnung(tmp_path, monkeypatch, programmordner):
    """Liegt die Zuordnungsdatei am Ende doch im Ausgabeordner – gleich aus welchem Grund (Programmordner nicht
    schreibbar, M-25 ausgeschaltet) –, ist das eine Warnung: die Oberfläche zeigt dann „ACHTUNG Zuordnungsdatei“."""
    ziel = tmp_path / "USB-Stick"
    ziel.mkdir()
    _als_wurzel(monkeypatch, ziel)
    (tmp_path / "gesperrt").write_text("keine Ordner hier")
    monkeypatch.setattr(dateien, "zuordnungen_ordner", lambda: tmp_path / "gesperrt" / "Zuordnungen")
    pdf = textseiten(tmp_path / "Antrag_Mueller_Max.pdf", NEUTRAL)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe(), ziel_ordner=ziel)
    meldung = next(m for m in s["meldungen"] if m["code"] == "ZUORDNUNG")
    assert meldung["art"] == "warnung" and "NICHT mit auswählen" in meldung["text"]
    assert (ziel / "_zuordnung.txt").exists() and s["status"] == "fertig"
    monkeypatch.setattr(schwaerzung, "ZUORDNUNG_NEBEN_AUSGABEORDNER", False)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe(), ziel_ordner=tmp_path / "anonymisiert")
    assert next(m for m in s["meldungen"] if m["code"] == "ZUORDNUNG")["art"] == "warnung"


# ======================================================================
# 3. Alte Zuordnungsdatei in anderer Kodierung
# ======================================================================
@pytest.mark.parametrize("kodierung", ["cp1252", "utf-16", "utf-8-sig", "utf-8"])
def test_alte_zuordnung_in_jeder_kodierung_wird_uebernommen(tmp_path, kodierung):
    """Befund 3: Eine im Editor als ANSI (oder „Unicode“) gespeicherte _zuordnung.txt ließ jede Schwärzung in diesen
    Ordner nach dem Ablegen der Ausgabe abbrechen. Jetzt: übernommen, als UTF-8 neben den Ausgabeordner geschrieben."""
    ziel = tmp_path / "anonymisiert"
    ziel.mkdir()
    (ziel / "_zuordnung.txt").write_bytes("anonym_01.pdf  <-  Antrag_Müller.pdf  (2026-11-01 10:00)\n".encode(kodierung))
    (ziel / "anonym_01.pdf").write_bytes(b"%PDF-1.4 alt")
    for nr in (1, 2):
        pdf = textseiten(tmp_path / f"Antrag_{nr}.pdf", [f"Versicherungsnehmer: {NAME}"])
        e = analysiere_pdf(pdf, STANDARD, [], [])
        s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), modell=e["modell"])
        assert s["fehler"] is None and s["ausgabe"].name == f"anonym_0{nr + 1}.pdf" and s["ausgabe"].exists()
        assert not any(m["code"] == "ZUORDNUNG" and m["art"] == "warnung" for m in s["meldungen"])
    datei = tmp_path / "_zuordnung_anonymisiert.txt"
    zeilen = datei.read_bytes().decode("utf-8").splitlines()               # UTF-8, keine gemischte Kodierung
    assert zeilen[0] == "anonym_01.pdf  <-  Antrag_Müller.pdf  (2026-11-01 10:00)"
    assert [z.split()[0] for z in zeilen] == ["anonym_01.pdf", "anonym_02.pdf", "anonym_03.pdf"]
    assert not (ziel / "_zuordnung.txt").exists()


def test_zuordnung_daneben_in_ansi_wird_beim_anhaengen_utf8(tmp_path):
    """Auch die Datei neben dem Ordner kann jemand im Editor als ANSI gespeichert haben: beim nächsten Eintrag wird sie
    ganz nach UTF-8 umgeschrieben (sonst stünden zwei Kodierungen in einer Datei); Freigeben liest sie ebenso."""
    neben = tmp_path / "_zuordnung_anonymisiert.txt"
    neben.write_bytes("anonym_01.pdf  <-  Antrag_Jürgens.pdf  (2026-11-01 10:00)\n".encode("cp1252"))
    pdf = textseiten(tmp_path / "Brief_Köhler.pdf", NEUTRAL)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe(), freigabe_erforderlich=True)
    zeilen = neben.read_bytes().decode("utf-8").splitlines()
    assert zeilen[0].startswith("anonym_01.pdf  <-  Antrag_Jürgens.pdf")
    assert zeilen[1].startswith(f"{s['ausgabe'].name}  <-  Brief_Köhler.pdf")
    neben.write_bytes(neben.read_text(encoding="utf-8").encode("cp1252"))       # noch einmal im Editor als ANSI
    neu = schwaerzung.freigeben(s["ausgabe"])
    assert neben.read_bytes().decode("utf-8").splitlines()[1].startswith(f"{neu.name}  <-  Brief_Köhler.pdf")


def test_attrappe_liest_zuordnung_in_jeder_kodierung(tmp_path):
    ordner = tmp_path / "anonymisiert"
    ordner.mkdir()
    (ordner / "anonym_01_PRUEFEN.pdf").write_bytes(b"%PDF x")
    neben = tmp_path / "_zuordnung_anonymisiert.txt"
    neben.write_bytes("anonym_01_PRUEFEN.pdf  <-  Müller.pdf  (2026-01-01 10:00)\n".encode("cp1252"))
    neu = attrappen.freigeben(ordner / "anonym_01_PRUEFEN.pdf")
    assert neben.read_bytes().decode("utf-8") == f"{neu.name}  <-  Müller.pdf  (2026-01-01 10:00)\n"


def test_fehler_der_zuordnung_nach_dem_ablegen_bricht_nie_ab(tmp_path, monkeypatch):
    """Die Ausgabe liegt schon im Ordner: was immer beim Eintrag in die Zuordnung schiefgeht, wird eine Warnung
    ZUORDNUNG – nie eine Ausnahme (sonst hieß es „OHNE Ausgabedatei“, obwohl anonym_NN.pdf existiert)."""
    def kaputt(*args, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\xfc", 0, 1, "invalid start byte")
    monkeypatch.setattr(schwaerzung, "_zuordnung_anhaengen", kaputt)
    pdf = textseiten(tmp_path / "Antrag.pdf", NEUTRAL)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert s["fehler"] is None and s["ausgabe"] is not None and s["ausgabe"].exists() and s["status"] == "fertig"
    meldung = next(m for m in s["meldungen"] if m["code"] == "ZUORDNUNG")
    assert meldung["art"] == "warnung" and "nicht geschrieben" in meldung["text"]
    assert s["ausgabe"].name in meldung["text"] and "Antrag.pdf" in meldung["text"]


def test_freigeben_meldet_keinen_fehler_wenn_nur_die_zuordnung_klemmt(tmp_path, monkeypatch):
    """Freigeben hat die Datei schon umbenannt; scheitert danach nur das Nachführen der Zuordnung (Datei gesperrt),
    steht das in fehler.log – die Freigabe selbst gilt (die Oberfläche meldete sonst „Freigabe nicht möglich“)."""
    pdf = textseiten(tmp_path / "Antrag.pdf", NEUTRAL)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe(), freigabe_erforderlich=True)
    protokoll = []
    monkeypatch.setattr(dateien, "fehler_protokollieren", lambda *a: protokoll.append(a) or None)

    def gesperrt(*args, **kwargs):
        raise PermissionError("Datei wird von einem anderen Prozess verwendet")
    monkeypatch.setattr(schwaerzung, "_atomar_schreiben", gesperrt)
    neu = schwaerzung.freigeben(s["ausgabe"])
    assert neu.exists() and not s["ausgabe"].exists() and protokoll


# ======================================================================
# Oberfläche (echte Engine): Status, Abschlussdialog
# ======================================================================
@gui_test
@pytest.mark.parametrize("freigabe", [False, True], ids=["freigabe_aus", "freigabe_an"])
@pytest.mark.parametrize("ausfall", [False, True], ids=["nichts_gelesen", "ausfall"])
def test_gui_heller_scan_ohne_ocr_woerter_ist_pruefen(app, umgebung, dialoge, monkeypatch, ausfall, freigabe):
    """Befund 1 in der echten Oberfläche: der Analyse-Dialog kündigt „_PRUEFEN“ an – und so kommt es jetzt auch
    (vorher: „✔ fertig“, Kontext „keine personenbezogenen Daten gefunden“, im Abschluss „ohne Schwärzung („fertig“)“;
    mit „Freigabe vor Weitergabe“ (Standard) nur „Freigabe ausstehend“, ohne Hinweis auf die ungelesene Seite)."""
    if ausfall:
        monkeypatch.setattr(gui, "OcrDienst", AusfallDienst)
    else:
        monkeypatch.setattr(gui, "OcrDienst", lambda *a, **k: OcrOhneWoerter())
    tmp = umgebung["tmp"]
    pdf = speichern(heller_scan(160), tmp / "Kunde" / "Scan_Schadenmeldung.pdf")
    app.freigabe_var.set(freigabe)
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren, timeout=180)
    text = app.letzter_dialog[2]
    assert "kein Text lesbar" in text and "_PRUEFEN" in text
    # keine Entwarnung vorweg (vorher: „Es wurden keine personenbezogenen Daten erkannt – auf den Seiten gibt es nichts
    # zu schwärzen“ über dem ACHTUNG-Block)
    assert "keine personenbezogenen Daten erkannt" not in text and "nichts zu schwärzen" not in text
    assert text.startswith("In keiner Datei war Text lesbar") and "nichts geprüft" in app.status_label.cget("text")
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=180)
    eintrag = app.ausgaben[pdf]
    assert eintrag["status"] == "pruefen" and eintrag["pfad"].name.endswith("_PRUEFEN.pdf")
    assert app.baum.set(str(pdf), "text").startswith("⚠") and "kein Text lesbar" in eintrag["grund"]
    assert "Freigabe ausstehend" not in eintrag["grund"] and "keine personenbezogenen Daten" not in eintrag["grund"]
    text = app.letzter_dialog[2]
    assert "ohne Schwärzung" not in text and "Zu prüfen: 1 Datei(en)" in text and "kein Text lesbar" in text


@gui_test
def test_gui_analyse_trennt_lesbare_und_unlesbare_dateien(app, umgebung, dialoge, monkeypatch):
    """Eine AVB ohne Fund und ein heller Scan, den die OCR nicht liest: „nichts zu schwärzen“ gilt nur für die lesbare
    Datei, der ACHTUNG-Block nennt nur den Scan."""
    monkeypatch.setattr(gui, "OcrDienst", lambda *a, **k: OcrOhneWoerter())
    tmp = umgebung["tmp"]
    (tmp / "Kunde").mkdir()
    avb = textseiten(tmp / "Kunde" / "AVB_Hausrat.pdf", NEUTRAL)
    scan = speichern(heller_scan(160), tmp / "Kunde" / "Scan_Schadenmeldung.pdf")
    app._pdfs_hinzufuegen([str(avb), str(scan)])
    starte_lauf(app, app.analysieren, timeout=180)
    art, titel, text = app.letzter_dialog
    erster, *_ = text.split("\n\n")
    assert art == "warning" and erster.startswith("In den 1 Datei(en) mit lesbarem Text wurden keine")
    achtung = text.split("ACHTUNG", 1)[1]
    assert "Scan_Schadenmeldung.pdf" in achtung and "AVB_Hausrat.pdf" not in achtung


@gui_test
def test_gui_nebenkanal_und_unlesbarer_scan_nennt_beides(app, umgebung, dialoge, monkeypatch):
    """Heller Scan ohne lesbaren Text, aber mit einem Namen in den Dateieigenschaften: der Dialog nennt die
    versteckten Personendaten UND dass auf den Seiten nichts geprüft wurde (vorher nur die Nebenkanäle)."""
    monkeypatch.setattr(gui, "OcrDienst", lambda *a, **k: OcrOhneWoerter())
    tmp = umgebung["tmp"]
    doc = heller_scan(160)
    doc.set_metadata({"author": NAME, "title": f"Schadenmeldung {NAME}"})
    pdf = speichern(doc, tmp / "Kunde" / "Scan_Schadenmeldung.pdf")
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren, timeout=180)
    art, titel, text = app.letzter_dialog
    assert art == "warning" and "versteckten Teilen" in text
    assert "ACHTUNG – in diesen Dateien war kein Text lesbar" in text and "Scan_Schadenmeldung.pdf" in text
    assert "wurde nichts gefunden" not in text


@gui_test
def test_gui_leere_datei_kuendigt_kein_pruefen_an_und_ist_fertig(app, umgebung, dialoge):
    """Gegenstück: eine Datei nur aus leeren Seiten (nichts gezeichnet) – der Analyse-Dialog warnt nicht „kein Text
    lesbar … _PRUEFEN“, und die Ausgabe ist „fertig“ (Ankündigung und Ergebnis passen in beiden Fällen zusammen)."""
    tmp = umgebung["tmp"]
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    pdf = speichern(doc, tmp / "Kunde" / "Leer.pdf")
    app.freigabe_var.set(False)
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren, timeout=180)
    assert "kein Text lesbar" not in app.letzter_dialog[2] and "_PRUEFEN" not in app.letzter_dialog[2]
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=180)
    eintrag = app.ausgaben[pdf]
    assert eintrag["status"] == "fertig" and eintrag["grund"] == "keine personenbezogenen Daten gefunden"
    assert "Davon 1 ohne Schwärzung („fertig“)" in app.letzter_dialog[2]


@gui_test
def test_gui_zielordner_laufwerkswurzel_zuordnung_im_programmordner(app, umgebung, dialoge, monkeypatch):
    """Befund 2 in der echten Oberfläche: gemeinsamer Zielordner = Laufwerkswurzel (E:\\ eines USB-Sticks). Im Ordner,
    der hochgeladen wird, liegt nur die anonym_….pdf; die Zuordnung (mit dem Original-Dateinamen) steht im
    Programmordner neben den Einstellungen, das Protokoll nennt den Ort."""
    tmp = umgebung["tmp"]
    stick = tmp / "USB-Stick"
    stick.mkdir()
    _als_wurzel(monkeypatch, stick)
    (tmp / "Kunde").mkdir()
    pdf = textseiten(tmp / "Kunde" / "Antrag_Mueller_Max.pdf", [f"Herrn {NAME}", "Hauptstraße 12", "50667 Köln"])
    app.zielordner_var.set(str(stick))
    app.zielordner_aktiv.set(True)
    app.freigabe_var.set(False)
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren, timeout=180)
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=180)
    ausgabe = app.ausgaben[pdf]["pfad"]
    assert ausgabe.parent == stick and sorted(p.name for p in stick.iterdir()) == [ausgabe.name]
    datei = schwaerzung.zuordnung_pfad(stick)
    assert datei.parent == dateien.zuordnungen_ordner() and datei.is_relative_to(tmp)
    assert f"{ausgabe.name}  <-  Antrag_Mueller_Max.pdf" in datei.read_text(encoding="utf-8")
    assert "ACHTUNG Zuordnungsdatei" not in app.letzter_dialog[2]
    assert str(datei) in app.protokoll_text() and "Programmordner" in app.protokoll_text()


@gui_test
def test_gui_freigabe_an_datei_ohne_fund_sagt_was_los_ist(app, umgebung, dialoge):
    """Befund 5: Standard „Freigabe vor Weitergabe“ – eine AVB ohne Fund zeigte nur „Freigabe ausstehend“. Jetzt: der
    Grund nennt „keine personenbezogenen Daten gefunden“, der Abschluss zählt sie unter „ohne Schwärzung“ und sagt,
    dass _PRUEFEN-Dateien erst nach der Freigabe weitergegeben werden."""
    tmp = umgebung["tmp"]
    (tmp / "Kunde").mkdir()
    avb = textseiten(tmp / "Kunde" / "AVB_Hausrat.pdf", NEUTRAL)
    assert app.freigabe_var.get()                                       # Standard
    app._pdfs_hinzufuegen([str(avb)])
    starte_lauf(app, app.analysieren, timeout=180)
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=180)
    eintrag = app.ausgaben[avb]
    assert eintrag["status"] == "pruefen" and eintrag["pfad"].name.endswith("_PRUEFEN.pdf")
    assert eintrag["grund"] == "keine personenbezogenen Daten gefunden – Freigabe ausstehend"
    assert app.baum.set(str(avb), "kontext") == eintrag["grund"]
    text = app.letzter_dialog[2]
    assert "Davon 1 ohne Schwärzung" in text and "1 davon noch freizugeben" in text
    assert "nie das Original; „_PRUEFEN“-Dateien erst nach der Freigabe." in text
    assert "(keine personenbezogenen Daten gefunden – Freigabe ausstehend)" in text


@gui_test
def test_gui_alte_zuordnung_in_ansi_kein_fehlerdialog(app, umgebung, dialoge):
    """Befund 3 in der echten Oberfläche: vorher „Unerwarteter Fehler … UnicodeDecodeError“ und „OHNE Ausgabedatei –
    konnte nicht bearbeitet werden“, obwohl anonym_02.pdf existierte."""
    tmp = umgebung["tmp"]
    ordner = tmp / "Kunde" / "anonymisiert"
    ordner.mkdir(parents=True)
    (ordner / "_zuordnung.txt").write_bytes("anonym_01.pdf  <-  Antrag_Müller.pdf  (2026-11-01 10:00)\n"
                                            .encode("cp1252"))
    (ordner / "anonym_01.pdf").write_bytes(b"%PDF-1.4\n%alt\n")
    pdf = textseiten(tmp / "Kunde" / "Brief_Kunde.pdf", [f"Herrn {NAME}", "Hauptstraße 12", "50667 Köln"])
    app.freigabe_var.set(False)
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren, timeout=180)
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=180)
    titel, text = app.letzter_dialog[1], app.letzter_dialog[2]
    assert titel == "Schwärzung abgeschlossen" and "1 von 1 Datei(en) geschrieben" in text, text
    assert "OHNE Ausgabedatei" not in text and "ACHTUNG Zuordnungsdatei" not in text
    assert app.ausgaben[pdf]["pfad"].name == "anonym_02.pdf" and app.ausgaben[pdf]["pfad"].exists()
    assert "Unerwarteter Fehler" not in dialoge.texte() and "error" not in dialoge.arten()
    zeilen = (tmp / "Kunde" / "_zuordnung_anonymisiert.txt").read_text(encoding="utf-8").splitlines()
    assert zeilen[0].startswith("anonym_01.pdf  <-  Antrag_Müller.pdf") and zeilen[1].startswith("anonym_02.pdf")
