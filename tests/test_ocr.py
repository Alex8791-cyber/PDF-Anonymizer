"""Tests für anonymisierer/ocr.py – Sprachdaten-Suche, Scan-Heuristik (M-04, M-51), OcrDienst
(M-21, M-28, M-29, M-30: Prozess-Pool mit Start-Methode "spawn", Fallback, Abbruch)."""

import concurrent.futures
import os
import sys
import threading
import time
from pathlib import Path

import pytest

import pymupdf as fitz

from conftest import braucht_ocr
from anonymisierer import ocr
from anonymisierer.ocr import (OcrDienst, _plausibilitaet, _tessdata_finden, bild_bereiche, ist_scan_seite,
                               ocr_noetig, ocr_textpage, woerter_zu_text)

NAME = "Max Mustermann"
ZEILEN = ["Versicherungsnehmer " + NAME, "IBAN DE89 3704 0044 0532 0130 00", "Kunden-Nr. 100245678 Stuttgart",
          "Sehr geehrter Herr Mustermann, vielen Dank für Ihre Nachricht."]


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------
def textseite_bild(zeilen=ZEILEN, dpi=200, winkel=0, fontsize=12):
    """Rendert Zeilen zu einem JPEG (optional gedreht) und liefert (bytes, Breite pt, Höhe pt, Wörter)."""
    doc = fitz.open()
    seite = doc.new_page()
    y = 100
    for z in zeilen:
        seite.insert_text((60, y), z, fontsize=fontsize, fontname="helv")
        y += 20
    woerter = [tuple(w[:5]) for w in seite.get_text("words")]
    pix = seite.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72).prerotate(winkel), colorspace=fitz.csRGB, alpha=False)
    bild = pix.tobytes("jpeg", jpg_quality=75)
    breite, hoehe = pix.width * 72 / dpi, pix.height * 72 / dpi
    doc.close()
    return bild, breite, hoehe, woerter


def scan_pdf(pfad, zeilen=ZEILEN, winkel=0, rotate=0, rect=None, extra=None):
    bild, breite, hoehe, woerter = textseite_bild(zeilen, winkel=winkel - rotate)
    doc = fitz.open()
    seite = doc.new_page(width=breite, height=hoehe)
    seite.insert_image(rect or seite.rect, stream=bild)
    if extra:
        extra(seite)
    if rotate:
        seite.set_rotation(rotate)
    doc.save(pfad)
    doc.close()
    return Path(pfad), woerter


def wort_rect(woerter, text):
    return next(fitz.Rect(w[:4]) for w in woerter if w[4] == text)


@pytest.fixture(scope="module")
def dienst():
    with OcrDienst(prozesse=2) as d:
        yield d


# ----------------------------------------------------------------------
# Sprachdaten
# ----------------------------------------------------------------------
def test_tessdata_suchreihenfolge(tmp_path, monkeypatch):
    projekt = tmp_path / "projekt"
    (projekt / "tessdata").mkdir(parents=True)
    (projekt / "tessdata" / "deu.traineddata").write_bytes(b"x")
    monkeypatch.setattr(ocr, "PROJEKTWURZEL", projekt)
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert _tessdata_finden() == str(projekt / "tessdata")
    assert os.environ["TESSDATA_PREFIX"] == str(projekt / "tessdata")
    # $TESSDATA_PREFIX gewinnt nur, wenn dort Sprachdaten liegen
    leer = tmp_path / "leer"
    leer.mkdir()
    monkeypatch.setenv("TESSDATA_PREFIX", str(leer))
    assert _tessdata_finden() == str(projekt / "tessdata")
    voll = tmp_path / "voll"
    voll.mkdir()
    (voll / "eng.traineddata").write_bytes(b"x")
    monkeypatch.setenv("TESSDATA_PREFIX", str(voll))
    assert _tessdata_finden() == str(voll)
    # PyInstaller: sys._MEIPASS/tessdata vor den Systempfaden, nach dem Projektordner
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    monkeypatch.setattr(ocr, "PROJEKTWURZEL", tmp_path / "gibt_es_nicht")
    frozen = tmp_path / "frozen"
    (frozen / "tessdata").mkdir(parents=True)
    (frozen / "tessdata" / "deu.traineddata").write_bytes(b"x")
    monkeypatch.setattr(sys, "_MEIPASS", str(frozen), raising=False)
    assert _tessdata_finden() == str(frozen / "tessdata")


def test_dienst_ohne_sprachdaten_warnt(monkeypatch):
    monkeypatch.setattr(ocr, "_tessdata_finden", lambda: None)
    d = OcrDienst(prozesse=1)
    woerter, warnung = d.woerter(Path("egal.pdf"), 0)
    assert woerter == [] and "tessdata" in warnung
    d.schliessen()


# ----------------------------------------------------------------------
# Scan-Heuristik
# ----------------------------------------------------------------------
def test_ocr_noetig_faelle(tmp_path):
    bild, breite, hoehe, _ = textseite_bild()
    doc = fitz.open()
    # reiner Text
    s_text = doc.new_page()
    for i in range(12):
        s_text.insert_text((50, 80 + 14 * i), f"Zeile {i}: ausreichend sichtbarer Text auf dieser Seite, damit sie als Textseite gilt.", fontsize=10, fontname="helv")
    # leere Seite
    doc.new_page()
    # ganzseitiger Scan
    s_scan = doc.new_page(width=breite, height=hoehe)
    s_scan.insert_image(s_scan.rect, stream=bild)
    # Scan 45 % + Textstempel
    s_stempel = doc.new_page()
    s_stempel.insert_image(fitz.Rect(98, 100, 497, 664), stream=bild)
    s_stempel.insert_text((430, 50), "KOPIE", fontsize=22, fontname="helv", color=(1, 0, 0))
    # 4 Kacheln + Faxkopf
    s_kacheln = doc.new_page()
    for ix in range(2):
        for iy in range(2):
            s_kacheln.insert_image(fitz.Rect(ix * 297.5, iy * 421, (ix + 1) * 297.5, (iy + 1) * 421), stream=bild)
    s_kacheln.insert_text((40, 20), "07.11.2024 09:12  FAX 0711 123456  Kanzlei Mueller  S. 1/1", fontsize=7, fontname="helv")
    # Textseite mit kleinem Bild (Ausweiskopie, 10 %)
    s_bild = doc.new_page()
    for i in range(12):
        s_bild.insert_text((50, 80 + 14 * i), f"Zeile {i}: ausreichend sichtbarer Text auf dieser Seite, damit sie als Textseite gilt.", fontsize=10, fontname="helv")
    s_bild.insert_image(fitz.Rect(60, 300, 360, 470), stream=bild)
    # Textseite mit großem Foto (55 %) – M-51: KEIN Ganzseiten-Scan
    s_foto = doc.new_page()
    for i in range(12):
        s_foto.insert_text((50, 60 + 10 * i), f"Zeile {i}: Schadenmeldung mit Fotodokumentation, Versicherungsnehmer und Kennzeichen.", fontsize=8, fontname="helv")
    s_foto.insert_image(fitz.Rect(10, 200, 585, 680), stream=bild)
    # durchsuchbarer Scan: Bild + unsichtbare Textebene
    s_kopierer = doc.new_page(width=breite, height=hoehe)
    s_kopierer.insert_image(s_kopierer.rect, stream=bild)
    for i, z in enumerate(ZEILEN * 3):
        s_kopierer.insert_text((60, 100 + 20 * i), z, fontsize=12, fontname="helv", render_mode=3)
    pdf = tmp_path / "heuristik.pdf"
    doc.save(pdf)
    doc.close()
    doc = fitz.open(pdf)
    erwartet = ["nein", "nein", "seite", "seite", "seite", "bilder", "bilder", "seite"]
    ergebnis = [ocr_noetig(s) for s in doc]
    assert ergebnis == erwartet, ergebnis
    assert ist_scan_seite(doc[2]) and not ist_scan_seite(doc[0]) and not ist_scan_seite(doc[6])
    assert len(bild_bereiche(doc[4])) == 1, "Kacheln werden zu einem Bereich zusammengefasst"
    assert bild_bereiche(doc[0]) == []
    doc.close()


def test_plausibilitaet():
    gut = "Sehr geehrter Herr Mustermann, vielen Dank für Ihre Schadenmeldung vom 12.08.2024. IBAN DE89 3704 0044 S-TB 4711 90402 Nürnberg".split()
    # echte Tesseract-Ausgabe eines um 90° bzw. 180° gelesenen Scans
    salat = ("youyseN alyl In} Yueq uajeın ‘uuewlesjsnyy USPEYIS-ZIY uNSNEAIESqUIES oO uSgeU ɐɯɹǝʇsnW 'ǝpunʞ "
             "6/ | — ,ı 1S| “‘uuewJ9)snW XeN JoWysuSbunssydısıeN").split()
    assert _plausibilitaet(gut) >= 0.8
    assert _plausibilitaet(salat) < 0.4, _plausibilitaet(salat)
    assert _plausibilitaet([]) == 0.0


def test_woerter_zu_text():
    acht = [(0, 0, 10, 10, "Hallo", 0, 0, 0), (12, 0, 20, 10, "Welt", 0, 0, 1), (0, 20, 10, 30, "Zeile", 0, 1, 0)]
    assert woerter_zu_text(acht) == "Hallo Welt\nZeile"
    fuenf = [(0, 0, 10, 10, "Hallo"), (12, 0, 20, 10, "Welt"), (0, 20, 10, 30, "Zeile")]
    assert woerter_zu_text(fuenf) == "Hallo Welt\nZeile"
    assert woerter_zu_text([]) == ""


# ----------------------------------------------------------------------
# OcrDienst: Prozess-Pool
# ----------------------------------------------------------------------
def test_dienst_laeuft_in_spawn_kindprozess(dienst):
    pid, methode, ist_kind = dienst.selbsttest()
    assert pid != os.getpid() and ist_kind
    assert methode == "spawn", "Windows-Standard muss auch unter Linux genutzt werden"
    assert not dienst.in_prozess


@braucht_ocr
def test_dienst_woerter_cache_und_text(tmp_path, dienst):
    pdf, erwartet = scan_pdf(tmp_path / "scan.pdf")
    woerter, warnung = dienst.woerter(pdf, 0)
    assert warnung is None
    texte = [w[4] for w in woerter]
    assert "Mustermann" in texte and "100245678" in texte
    soll = wort_rect(erwartet, "Mustermann")
    ist = next(fitz.Rect(w[:4]) for w in woerter if w[4] == "Mustermann")
    assert abs(ist.x0 - soll.x0) < 4 and abs(ist.x1 - soll.x1) < 4 and abs(ist.y1 - soll.y1) < 6, (ist, soll)
    aufrufe = []
    original = dienst._ausfuehren
    dienst._ausfuehren = lambda *a: aufrufe.append(a) or original(*a)
    try:
        woerter2, _ = dienst.woerter(pdf, 0)
        text = dienst.text(pdf, 0)
    finally:
        dienst._ausfuehren = original
    assert aufrufe == [], "zweiter Aufruf derselben Seite kommt aus dem Zwischenspeicher"
    assert woerter2 == woerter
    assert "Max Mustermann" in text and "\n" in text


@braucht_ocr
def test_dienst_erkennt_kopfstehenden_scan(tmp_path, dienst):
    pdf, erwartet = scan_pdf(tmp_path / "kopf.pdf", winkel=180)
    woerter, warnung = dienst.woerter(pdf, 0)
    assert warnung and "180°" in warnung, warnung
    texte = [w[4] for w in woerter]
    assert "Mustermann" in texte and "Stuttgart" in texte
    # Wort liegt dort, wo es im kopfstehenden Bild steht (Seite 595x842 um 180° gedreht)
    soll = wort_rect(erwartet, "Mustermann")
    doc = fitz.open(pdf)
    breite, hoehe = doc[0].rect.width, doc[0].rect.height
    doc.close()
    gedreht = fitz.Rect(breite - soll.x1, hoehe - soll.y1, breite - soll.x0, hoehe - soll.y0)
    ist = next(fitz.Rect(w[:4]) for w in woerter if w[4] == "Mustermann")
    assert abs(ist.x0 - gedreht.x0) < 5 and abs(ist.y0 - gedreht.y0) < 6, (ist, gedreht)


@braucht_ocr
def test_dienst_erkennt_seitlich_gedrehten_scan(tmp_path, dienst):
    pdf, _ = scan_pdf(tmp_path / "quer.pdf", winkel=90)
    woerter, warnung = dienst.woerter(pdf, 0)
    assert warnung and "gedreht" in warnung, warnung
    assert "Mustermann" in [w[4] for w in woerter]
    ist = next(fitz.Rect(w[:4]) for w in woerter if w[4] == "Mustermann")
    assert ist.height > ist.width, "seitliches Wort: Box ist höher als breit"


@braucht_ocr
def test_dienst_rotate_attribut_wird_herausgerechnet(tmp_path, dienst):
    """M-29: /Rotate 90 und 270 – Wörter in Koordinaten der Seite nach remove_rotation, nichts fehlt."""
    for rotate in (90, 270):
        pdf, erwartet = scan_pdf(tmp_path / f"rot{rotate}.pdf", rotate=rotate)
        woerter, warnung = dienst.woerter(pdf, 0)
        assert warnung is None, warnung
        texte = [w[4] for w in woerter]
        for t in ("Mustermann", "100245678", "Stuttgart", "Nachricht."):
            assert t in texte, (rotate, t, texte)
        soll = wort_rect(erwartet, "Mustermann")
        ist = next(fitz.Rect(w[:4]) for w in woerter if w[4] == "Mustermann")
        assert abs(ist.x0 - soll.x0) < 5 and abs(ist.y1 - soll.y1) < 6, (rotate, ist, soll)


@braucht_ocr
def test_dienst_clip_liefert_nur_bildbereich_ohne_textebene(tmp_path, dienst):
    bild, breite, hoehe, _ = textseite_bild(["Ausweis Erika Musterfrau", "geb. 12.08.1964"], fontsize=14)
    doc = fitz.open()
    seite = doc.new_page()
    for i in range(12):
        seite.insert_text((50, 80 + 14 * i), f"Zeile {i}: sichtbarer Text, der nicht als OCR-Wort erscheinen darf, {NAME}.", fontsize=10, fontname="helv")
    rect = fitz.Rect(60, 300, 360, 470)
    seite.insert_image(rect, stream=bild)
    pdf = tmp_path / "clip.pdf"
    doc.save(pdf)
    doc.close()
    woerter, warnung = dienst.woerter(pdf, 0, clip=rect)
    texte = [w[4] for w in woerter]
    assert "Musterfrau" in texte, texte
    assert all(rect.contains(fitz.Rect(w[:4])) or rect.intersects(fitz.Rect(w[:4])) for w in woerter)
    assert "Zeile" not in texte and "Mustermann." not in texte


def test_dienst_unplausible_seite_warnt(monkeypatch):
    d = OcrDienst(prozesse=1)
    d.in_prozess = True   # Worker direkt im Prozess, damit er sich ersetzen lässt
    salat = [(0, 0, 10, 10, t, 0, 0, i) for i, t in enumerate("USPEYIS-ZIY uNSNEAIESqUIES usßeuelun Jsıle Bueßulg oO uSgeU".split())]
    monkeypatch.setattr(ocr, "_ocr_worker", lambda *a, **k: {"woerter": salat, "winkel": 90, "plausibel": 0.1})
    monkeypatch.setattr(d, "sprache", "deu")
    monkeypatch.setattr(d, "tessdata", "/egal")
    woerter, warnung = d.woerter(Path("egal.pdf"), 3)
    assert len(woerter) == len(salat)
    assert "Seite 4" in warnung and "unplausibel" in warnung and "90°" in warnung
    d.schliessen()


def test_dienst_fallback_im_prozess(monkeypatch):
    def kaputt(*a, **k):
        raise OSError("kein Prozessstart möglich")

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", kaputt)
    d = OcrDienst(prozesse=1)
    pid, methode, ist_kind = d.selbsttest()
    assert pid == os.getpid() and not ist_kind
    assert d.in_prozess and any("Hauptprozess" in h for h in d.hinweise)
    d.schliessen()


@braucht_ocr
def test_dienst_abbrechen_und_zuruecksetzen(tmp_path, dienst):
    pdf, _ = scan_pdf(tmp_path / "abbruch.pdf", zeilen=ZEILEN * 8)   # dichte Seite -> längere OCR
    d = OcrDienst(prozesse=1)
    try:
        ergebnis = {}

        def arbeit():
            ergebnis["r"] = d.woerter(pdf, 0)

        t = threading.Thread(target=arbeit)
        start = time.perf_counter()
        t.start()
        time.sleep(0.3)
        d.abbrechen()
        t.join(timeout=15)
        assert not t.is_alive(), "Abbruch muss den wartenden Aufruf beenden"
        assert ergebnis["r"] == ([], "Abgebrochen")
        assert time.perf_counter() - start < 10
        assert d.woerter(pdf, 0) == ([], "Abgebrochen"), "nach Abbruch keine neuen Aufträge"
        d.zuruecksetzen()
        woerter, warnung = d.woerter(pdf, 0)
        assert "Mustermann" in [w[4] for w in woerter] and warnung is None
    finally:
        d.schliessen()


def test_dienst_context_manager_schliesst_pool():
    with OcrDienst(prozesse=1) as d:
        assert d.selbsttest() is not None
        assert d._pool is not None
    assert d._pool is None


# ----------------------------------------------------------------------
# Kompatibilität
# ----------------------------------------------------------------------
@braucht_ocr
def test_ocr_textpage_kompatibel(tmp_path):
    pdf, _ = scan_pdf(tmp_path / "kompat.pdf", rotate=90)
    doc = fitz.open(pdf)
    seite = doc[0]
    tp, warnung = ocr_textpage(seite)
    assert tp is not None and warnung is None
    assert seite.rotation == 0, "ocr_textpage dreht /Rotate-Seiten vorher gerade"
    assert "Mustermann" in seite.get_text(textpage=tp)
    doc.close()
