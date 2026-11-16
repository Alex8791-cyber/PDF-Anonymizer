"""Windows-Betrieb (Runde 3, Paket „vorschau-oberflaeche“):

  1. R-09 mit einem ECHTEN Pfad über 300 Zeichen: Eingangsprüfung (Ordner-Scan, Art nach Inhalt, Kennwort-Prüfung),
     Analyse (MuPDF öffnet die Datei; die OCR-Arbeitsprozesse lesen die Scan-Seite über denselben Pfad) und
     Schwärzung (Ausgabe speichern, Zuordnungsdatei schreiben) – einmal direkt über die Engine, einmal durch die
     Oberfläche mit echter Engine. Bisher gab es nur das Linux-Gegenstück (test_oberflaeche_eingang.py:
     test_linux_analogon_sehr_langer_pfad_wird_gemeldet); die Grenze MAX_PATH (260 Zeichen) gibt es nur unter
     Windows, deshalb laufen diese Tests auf dem Windows-CI (windows-latest) und werden sonst mit Begründung
     übersprungen. Zum Prüfen der Testlogik auf anderen Systemen: PDF_ANONYMISIERER_LANGPFAD_TEST=1 setzen (dort
     sind Pfade dieser Länge ohnehin erlaubt).
  2. Hilfetexte der OCR zur Sprachdatei: richtig für beide Betriebsarten (Skript: tessdata im Programmordner, EXE:
     _internal\\tessdata), nie „Installieren.bat“ (bringt die Sprachdatei nicht zurück) oder „neben dem Programm“ –
     dieselbe Abhilfe, die die Oberfläche für Hinweise der Engine in der EXE nennt (gui._text_fuer_exe, M-70).
"""

import os
import shutil
import sys
from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from anonymisierer import dateien, gui, ocr, schwaerzung
from anonymisierer.analyse import analysiere_pdf
from anonymisierer.schwaerzung import schwaerze_pdf

from conftest import braucht_ocr
from test_gui import app, dialoge, pumpe, root, starte_lauf, umgebung  # noqa: F401  (Fixtures)

NAME = "Max Mustermann"
IBAN = "DE89 3704 0044 0532 0130 00"
MINDESTLAENGE = 310          # Zeichen bis zum Ordner der Dateien; Dateiname und Ausgabeordner kommen dazu

nur_windows = pytest.mark.skipif(
    sys.platform != "win32" and not os.environ.get("PDF_ANONYMISIERER_LANGPFAD_TEST"),
    reason="R-09 betrifft die Windows-Grenze MAX_PATH (260 Zeichen): läuft auf dem Windows-CI (windows-latest); "
           "das Linux-Gegenstück prüft test_oberflaeche_eingang.py::test_linux_analogon_sehr_langer_pfad_wird_gemeldet")


# ----------------------------------------------------------------------
# Testdateien in einem Ordner mit über 300 Zeichen
# ----------------------------------------------------------------------
def langer_ordner(basis: Path) -> Path:
    """Ordner mit mindestens MINDESTLAENGE Zeichen (ohne „\\\\?\\“), angelegt über dateien.langpfad – so wie ein
    Kundenordner tief in OneDrive. Geliefert wird der gewöhnliche Pfad, wie ihn die Nutzerin auswählt."""
    pfad = Path(os.path.abspath(basis))
    nummer = 0
    while len(str(pfad)) < MINDESTLAENGE:
        pfad = pfad / f"Kunde_{nummer:02d}_Mustermann_Unterlagen_Lebensversicherung_2024"
        nummer += 1
    os.makedirs(dateien.langpfad(pfad), exist_ok=True)
    return pfad


def schreiben(pfad: Path, doc) -> Path:
    """PDF über den Langpfad schreiben (Python-Dateifunktionen; das Programm selbst speichert über MuPDF)."""
    Path(dateien.langpfad(pfad)).write_bytes(doc.tobytes())
    doc.close()
    return pfad


def textpdf(pfad: Path) -> Path:
    doc = fitz.open()
    seite = doc.new_page()
    for i, zeile in enumerate([f"Versicherungsnehmer: {NAME}", f"IBAN: {IBAN}", "Telefon: 0171 2345678"]):
        seite.insert_text((72, 100 + 20 * i), zeile, fontsize=12, fontname="helv")
    return schreiben(pfad, doc)


def scanpdf(pfad: Path) -> Path:
    """Eine Scan-Seite (Text nur als Bild): die Analyse muss die OCR fragen."""
    vorlage = fitz.open()
    s = vorlage.new_page()
    for i, zeile in enumerate([f"Herr {NAME}", f"IBAN {IBAN}", "Hauptstrasse 12, 90402 Nuernberg"]):
        s.insert_text((60, 100 + 24 * i), zeile, fontsize=14, fontname="helv")
    pix = s.get_pixmap(dpi=200, colorspace=fitz.csRGB, alpha=False)
    bild = pix.tobytes("jpeg", jpg_quality=85)
    vorlage.close()
    doc = fitz.open()
    seite = doc.new_page(width=pix.width * 72 / 200, height=pix.height * 72 / 200)
    seite.insert_image(seite.rect, stream=bild)
    return schreiben(pfad, doc)


def text_der_ausgabe(pfad) -> str:
    with fitz.open(dateien.langpfad(pfad)) as doc:
        return " ".join(seite.get_text() for seite in doc)


def zuordnung_zu(ausgabe) -> str:
    """Inhalt der Zuordnungsdatei zur Ausgabe (Ort wie die Schwärzung ihn bestimmt, auch mit M-25)."""
    datei = schwaerzung.zuordnung_pfad(Path(ausgabe).parent)
    assert Path(dateien.langpfad(datei)).exists(), datei
    return Path(dateien.langpfad(datei)).read_text(encoding="utf-8")


def aufraeumen(basis: Path):
    """Lange Pfade löscht nur das Präfix zuverlässig (pytest räumt seinen Temp-Ordner ohne es auf)."""
    shutil.rmtree(dateien.langpfad(os.path.abspath(basis)), ignore_errors=True)


# ----------------------------------------------------------------------
# 1. R-09: echter Pfad über 300 Zeichen
# ----------------------------------------------------------------------
@nur_windows
@braucht_ocr
def test_langer_pfad_eingang_analyse_ocr_und_schwaerzung(tmp_path):
    basis = tmp_path / "Kunden"
    try:
        ordner = langer_ordner(basis)
        text = textpdf(ordner / "Police_Mustermann.pdf")
        scan = scanpdf(ordner / "Scan_Mustermann.pdf")
        assert len(str(text)) > 300 and len(str(scan)) > 300

        # Eingangsprüfung: Ordner-Scan findet beide, nichts „nicht lesbar“, Art nach Inhalt, kein Kennwort
        bericht = dateien.sammle_pdfs_bericht([str(ordner)])
        assert not bericht["nicht_lesbar"] and not bericht["fehlend"], bericht["gruende"]
        pdfs = {Path(dateien.ohne_langpfad(p)).name: p for p in bericht["pdfs"]}
        assert sorted(pdfs) == ["Police_Mustermann.pdf", "Scan_Mustermann.pdf"], bericht
        for pfad in pdfs.values():
            assert len(dateien.ohne_langpfad(pfad)) > 300
            if sys.platform == "win32":
                assert str(pfad).startswith("\\\\?\\"), pfad          # das Programm arbeitet mit dem Präfix
            assert dateien.datei_art(pfad) == "pdf" and dateien.fuer_engine_erlaubt("pdf")
            assert dateien.pdf_kennwort_noetig(pfad) is False

        with ocr.OcrDienst(prozesse=1) as dienst:
            for name, kategorie in (("Police_Mustermann.pdf", "iban"), ("Scan_Mustermann.pdf", "iban")):
                pdf = pdfs[name]
                # Analyse: MuPDF öffnet den langen Pfad; bei der Scan-Seite liest der OCR-Arbeitsprozess ihn
                e = analysiere_pdf(pdf, {"iban", "telefon"}, [], [NAME], ocr=dienst)
                assert e["fehler"] is None, (name, e["fehler"], e.get("meldungen"))
                gefunden = {(f["kategorie"], " ".join(f["text"].split())) for f in e["funde"]}
                assert (kategorie, IBAN) in gefunden or any(k == kategorie for k, _ in gefunden), (name, gefunden)
                assert any(NAME in f["text"] for f in e["funde"]), (name, gefunden)
                if name.startswith("Scan"):
                    assert e["ocr_seiten"] >= 1 and e["ocr_cache"], "die Scan-Seite wurde nicht per OCR gelesen"
                    assert not [m for m in e.get("meldungen", []) if m.get("code") == "OCR_FEHLER"], e["meldungen"]
                # Schwärzung: Ausgabe neben dem Original (Ordner „anonymisiert“), Zuordnungsdatei dazu
                s = schwaerze_pdf(pdf, e["funde"], ocr=dienst, ocr_cache=e["ocr_cache"], modell=e.get("modell"))
                assert s["fehler"] is None and s["ausgabe"], (name, s["fehler"], s.get("meldungen"))
                ausgabe = s["ausgabe"]
                assert len(dateien.ohne_langpfad(ausgabe)) > 300
                assert Path(dateien.langpfad(ausgabe)).exists()
                inhalt = text_der_ausgabe(ausgabe)
                assert NAME not in inhalt and "0532 0130" not in inhalt, (name, inhalt)
                assert f"{Path(ausgabe).name}  <-  {name}" in zuordnung_zu(ausgabe)
    finally:
        aufraeumen(basis)


@nur_windows
@braucht_ocr
def test_langer_pfad_durch_die_oberflaeche(app, umgebung, dialoge, monkeypatch):
    """Wie die Nutzerin: Ordner hinzufügen, Analysieren, Schwärzen – mit echter Engine und echter OCR."""
    monkeypatch.setattr(gui, "OcrDienst", ocr.OcrDienst)            # die Testumgebung setzt sonst eine Attrappe
    basis = umgebung["tmp"] / "Kunden"
    try:
        ordner = langer_ordner(basis)
        textpdf(ordner / "Police_Mustermann.pdf")
        scanpdf(ordner / "Scan_Mustermann.pdf")
        app.kategorie_vars["namen"].set(False)                      # ohne Sprachmodell: der Name kommt aus IMMER
        app.immer_feld.insert("1.0", NAME)
        app._pdfs_hinzufuegen([str(ordner)])
        pumpe(app.root, timeout=0.2)
        assert sorted(Path(dateien.ohne_langpfad(p)).name for p in app.dateien) == ["Police_Mustermann.pdf",
                                                                                      "Scan_Mustermann.pdf"]
        assert not app.nicht_geprueft, app.nicht_geprueft
        hinweis = app.datei_hinweis.cget("text")
        assert "2 PDF-Datei(en) hinzugefügt" in hinweis and "nicht lesbar" not in hinweis, hinweis

        starte_lauf(app, app.analysieren, timeout=240)
        for pdf in app.dateien:
            ergebnis = app.analyse_ergebnisse[pdf]
            assert ergebnis["fehler"] is None, (pdf, ergebnis["fehler"])
            assert any(NAME in f["text"] for f in ergebnis["funde"]), (pdf, ergebnis["funde"])
        scan = next(p for p in app.dateien if Path(dateien.ohne_langpfad(p)).name.startswith("Scan"))
        assert app.analyse_ergebnisse[scan]["ocr_seiten"] >= 1

        dialoge.antwort = True
        starte_lauf(app, app.schwaerzen, timeout=240)
        for pdf in app.dateien:
            eintrag = app.ausgaben[pdf]
            ausgabe = eintrag["pfad"]
            assert ausgabe is not None and Path(dateien.langpfad(ausgabe)).exists(), eintrag
            assert Path(dateien.ohne_langpfad(ausgabe)).parent == Path(dateien.ohne_langpfad(ordner)) / "anonymisiert"
            assert NAME not in text_der_ausgabe(ausgabe)
            assert f"{Path(ausgabe).name}  <-  {Path(dateien.ohne_langpfad(pdf)).name}" in zuordnung_zu(ausgabe)
        protokoll = app.protokoll_text()
        assert "\\\\?\\" not in protokoll, "das Protokoll zeigt Pfade ohne das technische Präfix"
    finally:
        try:
            app.liste_leeren()                                     # Arbeitskopien und Liste freigeben
        except Exception:
            pass                                                   # der eigentliche Fehler bleibt sichtbar
        aufraeumen(basis)


# ----------------------------------------------------------------------
# 2. Hilfetexte zur OCR-Sprachdatei: Skript und EXE
# ----------------------------------------------------------------------
@pytest.mark.parametrize("exe", [False, True])
def test_ocr_hilfetexte_fuer_skript_und_exe(monkeypatch, tmp_path, exe):
    if exe:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        ordner = "_internal\\tessdata"
    else:
        monkeypatch.delattr(sys, "frozen", raising=False)
        ordner = "tessdata"
    nur_englisch = tmp_path / "nur_englisch"
    nur_englisch.mkdir()
    (nur_englisch / "eng.traineddata").write_bytes(b"x")
    leer = tmp_path / "leer"
    leer.mkdir()
    texte = [ocr._ocr_sprache(None)[1], ocr._ocr_sprache(str(nur_englisch))[1], ocr._ocr_sprache(str(leer))[1]]
    assert ocr._ocr_sprache(None)[0] is None and ocr._ocr_sprache(str(nur_englisch))[0] == "eng"
    for text in texte:
        assert f"im Programmordner unter {ordner} liegen" in text, text
        assert "neu entpacken" in text and "ZIP-Datei" in text, text
        assert "Installieren.bat" not in text and "neben dem Programm" not in text, text
        # die Übersetzung der Oberfläche (EXE) hat daran nichts mehr zu ändern – beide sagen dasselbe
        assert gui._text_fuer_exe(text) == text
        assert gui._anzeigetext(text) == text
    if not exe:
        assert "_internal" not in texte[0]
