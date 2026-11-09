"""Tests für anonymisierer/ocr.py – Sprachdaten-Suche, Seiten-Heuristik (M-04, M-51, KQ-06, S-15, PERF-03,
KQ-12), Ausrichtung (S-01, PERF-02, S-08), Zeilenbildung (EQ-01), OcrDienst (M-21, M-28, M-29, M-30, GR-03,
S-09, KQ-05, S-10, PERF-05: Prozess-Pool mit Start-Methode "spawn", Eltern-Wächter, Absturzbehandlung,
vorab(), Abbruch, Cache)."""

import concurrent.futures
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

import pymupdf as fitz

from conftest import braucht_ocr
from anonymisierer import ocr
from anonymisierer.ocr import (OcrDienst, _ausrichtung_waehlen, _lesung_bewerten, _naechster_winkel,
                               _plausibilitaet, _tessdata_finden, bild_bereiche, ist_scan_seite, ocr_noetig,
                               ocr_textpage, seiten_pruefung, woerter_zu_text, woerter_zu_zeilen)

NAME = "Max Mustermann"
ZEILEN = ["Versicherungsnehmer " + NAME, "IBAN DE89 3704 0044 0532 0130 00", "Kunden-Nr. 100245678 Stuttgart",
          "Sehr geehrter Herr Mustermann, vielen Dank für Ihre Nachricht."]
# textreicher Brief (> 40 Wörter): genau hier versagte die alte Vokal-Heuristik (Gutachten S-01/PERF-02)
BRIEF = ["Versicherungsnehmer: Max Mustermann", "Lange Straße 7, 51429 Bergisch Gladbach",
         "Geburtsdatum: 02.09.1983", "IBAN: DE89 3704 0044 0532 0130 00", "",
         "Sehr geehrter Herr Mustermann,",
         "wir bestätigen den Eingang Ihrer Unterlagen vom 12.03.2025 und danken für",
         "Ihre Geduld. Die Prüfung dauert in der Regel zwei bis drei Wochen. Sollten",
         "noch Unterlagen fehlen, melden wir uns bei Ihnen. Den Beitrag in Höhe von",
         "89,50 EUR buchen wir wie gewohnt monatlich von Ihrem Konto ab.",
         "Bei Fragen erreichen Sie uns unter der bekannten Telefonnummer.", "",
         "Mit freundlichen Grüßen", "Sabine Krüger", "Kundenservice"]


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


def scan_pdf(pfad, zeilen=ZEILEN, winkel=0, rotate=0, rect=None, extra=None, dpi=200):
    bild, breite, hoehe, woerter = textseite_bild(zeilen, winkel=winkel - rotate, dpi=dpi)
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


def texte(woerter):
    return [w[4] for w in woerter]


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
    assert [m["code"] for m in d.ergebnis(Path("egal.pdf"), 0)["meldungen"]] == ["OCR_FEHLER"]
    d.schliessen()


# ----------------------------------------------------------------------
# Seiten-Heuristik: EINE Entscheidung für alle (KQ-06/S-15), Streifen/Kacheln (PERF-03), KQ-12
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
    # eine Quelle: ocr_noetig/bild_bereiche sind Sichten auf seiten_pruefung
    for s in doc:
        p = seiten_pruefung(s)
        assert p.modus == ocr_noetig(s) and p.bereiche == bild_bereiche(s) and p.meldungen == []
    doc.close()


def _streifen_scan(pfad, streifen: int, bild=None):
    """Ein Scanbild, zerlegt in `streifen` waagerechte Bänder (Fax-/GDI-Treiber, Gutachten PERF-03)."""
    bild = bild or textseite_bild(BRIEF, dpi=150)[0]
    pix = fitz.Pixmap(bild)
    doc = fitz.open()
    seite = doc.new_page()
    hoehe_px = pix.height / streifen
    for i in range(streifen):
        y0, y1 = int(i * hoehe_px), int((i + 1) * hoehe_px)
        if y1 <= y0:
            continue
        ziel = fitz.Rect(0, y0 * 842 / pix.height, 595, y1 * 842 / pix.height)
        seite.insert_image(ziel, pixmap=_band(pix, y0, y1))
    doc.save(pfad)
    doc.close()
    return Path(pfad)


def _band(pix, y0, y1):
    """Waagerechter Ausschnitt eines Pixmaps (Zeilen y0..y1) als eigenes Pixmap."""
    zeile = pix.stride
    daten = pix.samples[y0 * zeile:y1 * zeile]
    return fitz.Pixmap(pix.colorspace, pix.width, y1 - y0, daten, False)


@pytest.mark.parametrize("streifen", [8, 100, 150, 300])
def test_streifen_scan_gilt_als_scan(tmp_path, streifen):
    """PERF-03: auch 100-300 Streifen à < 1 % der Seite ergeben EINEN Bereich und den Modus "seite"."""
    pdf = _streifen_scan(tmp_path / f"streifen_{streifen}.pdf", streifen)
    doc = fitz.open(pdf)
    seite = doc[0]
    assert len(seite.get_image_info()) >= streifen * 0.9
    start = time.perf_counter()
    pruefung = seiten_pruefung(seite)
    dauer = time.perf_counter() - start
    assert pruefung.modus == "seite", pruefung
    assert len(pruefung.bereiche) == 1 and pruefung.bildanteil > 0.9
    assert dauer < 1.0, f"Zusammenfassen zu langsam: {dauer:.2f}s"
    doc.close()


def test_kleine_bilder_und_winzlinge(tmp_path):
    """S-15/KQ-06: Stempel-/Unterschriftsbild (0,5 % der Seite) zählt, Icons und Linien nicht."""
    bild = textseite_bild(["Erika Musterfrau"], dpi=150)[0]
    doc = fitz.open()
    seite = doc.new_page()
    for i in range(12):
        seite.insert_text((50, 80 + 14 * i), f"Zeile {i}: ausreichend sichtbarer Text auf dieser Seite, damit sie als Textseite gilt.", fontsize=10, fontname="helv")
    stempel = fitz.Rect(300, 600, 400, 630)              # 3000 pt² = 0,6 %
    seite.insert_image(stempel, stream=bild, keep_proportion=False)
    seite.insert_image(fitz.Rect(20, 20, 32, 32), stream=bild, keep_proportion=False)       # Icon 144 pt²
    seite.insert_image(fitz.Rect(50, 700, 550, 702), stream=bild, keep_proportion=False)    # Linie 2 pt hoch
    pdf = tmp_path / "klein.pdf"
    doc.save(pdf)
    doc.close()
    doc = fitz.open(pdf)
    pruefung = seiten_pruefung(doc[0])
    assert pruefung.modus == "bilder"
    assert len(pruefung.bereiche) == 1
    assert abs(pruefung.bereiche[0] & stempel) > 0.98 * abs(stempel), pruefung.bereiche
    doc.close()


def test_hintergrundbild_mit_text_wird_als_bildbereich_gelesen(tmp_path):
    """Ganzseitiges Hintergrundbild (Briefpapier) unter viel Text: "bilder" mit dem ganzen Bereich."""
    bild = textseite_bild(["Briefkopf Muster AG"], dpi=100)[0]
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_image(seite.rect, stream=bild)
    for i in range(20):
        seite.insert_text((50, 200 + 14 * i), f"Zeile {i}: Text über dem Hintergrundbild mit genug Zeichen für eine Textseite.", fontsize=10)
    pdf = tmp_path / "hintergrund.pdf"
    doc.save(pdf)
    doc.close()
    doc = fitz.open(pdf)
    pruefung = seiten_pruefung(doc[0])
    assert pruefung.modus == "bilder" and pruefung.bildanteil > 0.95
    doc.close()


def test_scan_mit_dms_fusszeile_bleibt_scan(tmp_path):
    """Scan mit eingeblendetem Textstempel (Eingangsstempel, DMS-Fußzeile < 200 Zeichen) bleibt "seite"."""
    def stempel(seite):
        seite.insert_text((30, seite.rect.height - 20), "Eingang 12.03.2025 – DMS-ID 4711-0815 – Seite 1 von 3",
                          fontsize=7)
    pdf, _ = scan_pdf(tmp_path / "dms.pdf", extra=stempel)
    doc = fitz.open(pdf)
    assert ocr_noetig(doc[0]) == "seite"
    doc.close()


def test_bildanalyse_fehler_entscheidet_vorsorglich_fuer_ocr(tmp_path, monkeypatch):
    """KQ-12: schlägt get_image_info fehl, gilt die ganze Seite als Bildbereich (OCR) – mit Meldung und
    Eintrag im Fehlerprotokoll, nie still "kein Bild"."""
    pdf, _ = scan_pdf(tmp_path / "scan.pdf", extra=lambda s: s.insert_text((30, 20), "KOPIE", fontsize=9))
    protokoll = []
    import anonymisierer.dateien as dateien
    monkeypatch.setattr(dateien, "fehler_protokollieren", lambda typ, wert, tb: protokoll.append(wert))

    def kaputt(self, *a, **k):
        raise RuntimeError("defektes Bild")

    monkeypatch.setattr(fitz.Page, "get_image_info", kaputt)
    doc = fitz.open(pdf)
    meldungen = []
    assert ocr_noetig(doc[0], meldungen) == "seite"
    assert [m["code"] for m in meldungen] == ["BILDER_UNGEPRUEFT"] and meldungen[0]["seite"] == 0
    pruefung = seiten_pruefung(doc[0])
    assert pruefung.bereiche == [doc[0].rect]
    assert protokoll and "defektes Bild" in str(protokoll[0])
    doc.close()


def test_zeichenanalyse_fehler_zaehlt_vorsorglich_null(tmp_path, monkeypatch):
    """KQ-12: auch ein Fehler beim Zählen der Textzeichen fällt auf "OCR" (0 Zeichen) zurück."""
    pdf, _ = scan_pdf(tmp_path / "scan.pdf")
    import anonymisierer.dateien as dateien
    monkeypatch.setattr(dateien, "fehler_protokollieren", lambda *a: None)

    def kaputt(self, *a, **k):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(fitz.Page, "get_texttrace", kaputt)
    monkeypatch.setattr(fitz.Page, "get_text", kaputt)
    doc = fitz.open(pdf)
    p = seiten_pruefung(doc[0])
    assert p.modus == "seite" and p.zeichen == 0 and p.meldungen[0]["code"] == "BILDER_UNGEPRUEFT"
    doc.close()


# ----------------------------------------------------------------------
# Plausibilität und Ausrichtung (S-01, PERF-02)
# ----------------------------------------------------------------------
# echte Tesseract-Ausgaben gedrehter Seiten (Buchstabensalat), aus den Gutachten-Messungen
SALAT_180 = ("BUNIBYIISIOAUSYUBIY H9INIOSUSPUNY uUEWJOH Haug USHNIH UOySNPUNa HN \"OJUOY Sluueyaq sun sep Ine "
             "YN3 09'782’| uayelsıa pun ynıdaß usgeßuy auy] uogey JM \"7202 Bunyelsisyanısbeunag ınz uohellsjun "
             "auyı an) yueg uajaın ‘YeMoN Neil aUyaaß ıyas").split()
SALAT_90 = ("_ (2) DD <<< Tr. ıI=Z SIEBETDEENEITSEIIIBRIITTIEEITTJAPESEETEUBE 8 BSi5 38575 E23 rg aSsSoSoloooaNso99 "
            "SS. os s9 SSSogoang S 333% 823% = SS 2 u ce < ©. 2. 7 >} arcar ® , < < Dom zz Do< e) 7020 pr zZ").split()


def test_plausibilitaet():
    gut = "Sehr geehrter Herr Mustermann, vielen Dank für Ihre Schadenmeldung vom 12.08.2024. IBAN DE89 3704 0044 S-TB 4711 90402 Nürnberg".split()
    # echte Tesseract-Ausgabe eines um 90° bzw. 180° gelesenen Scans
    salat = ("youyseN alyl In} Yueq uajeın ‘uuewlesjsnyy USPEYIS-ZIY uNSNEAIESqUIES oO uSgeU ɐɯɹǝʇsnW 'ǝpunʞ "
             "6/ | — ,ı 1S| “‘uuewJ9)snW XeN JoWysuSbunssydısıeN").split()
    assert _plausibilitaet(gut) >= 0.8
    assert _plausibilitaet(salat) < 0.4, _plausibilitaet(salat)
    assert _plausibilitaet([]) == 0.0
    # das neue Maß trennt dort, wo die alte Vokal-Heuristik 0,53-0,69 lieferte (S-01)
    assert _lesung_bewerten(SALAT_180)["quote"] < 0.03 and _lesung_bewerten(SALAT_90)["quote"] < 0.03
    assert _lesung_bewerten(" ".join(BRIEF).split())["quote"] > 0.3
    englisch = "Dear Mr Miller, thank you for your letter regarding the insurance claim of 12 March 2025.".split()
    assert _lesung_bewerten(englisch)["quote"] > 0.3, "fremdsprachige Seiten gelten nicht als verdreht"
    zahlen = "Datum Betrag 01.02.2025 1.287,60 EUR 04.02.2025 42,30 EUR 3,5% 09:12".split()
    assert _lesung_bewerten(zahlen)["quote"] > 0.6, "Daten/Beträge zählen als starke Wörter"


def _b(quote, treffer=None, tokens=100):
    treffer = round(quote * tokens) if treffer is None else treffer
    return {"quote": quote, "treffer": treffer, "tokens": tokens}


def test_ausrichtungsregeln_ohne_ocr():
    """0° zuerst; 180° immer, wenn 0° nicht klar ist; 90/270 nur, wenn weder 0° noch 180° plausibel ist;
    eine Drehung gewinnt nur deutlich (aufrechte Code-Tabellen bleiben bei 0°)."""
    assert _naechster_winkel({}) == 0
    assert _naechster_winkel({0: _b(0.3)}) is None                      # aufrecht: 1 Lauf
    assert _naechster_winkel({0: _b(0.0, tokens=3)}) is None             # fast leer: nichts auszurichten
    assert _naechster_winkel({0: _b(0.07)}) == 180                        # nicht klar -> 180° prüfen
    assert _naechster_winkel({0: _b(0.07), 180: _b(0.0)}) is None         # 0° plausibel -> kein 90/270
    assert _naechster_winkel({0: _b(0.0), 180: _b(0.5)}) is None
    assert _naechster_winkel({0: _b(0.0), 180: _b(0.01)}) == 90
    assert _naechster_winkel({0: _b(0.0), 180: _b(0.01), 90: _b(0.4)}) is None
    assert _naechster_winkel({0: _b(0.0), 180: _b(0.01), 90: _b(0.01)}) == 270
    assert _naechster_winkel({0: _b(0.0), 180: _b(0.0), 90: _b(0.0), 270: _b(0.0)}) is None
    assert _ausrichtung_waehlen({0: _b(0.0), 180: _b(0.5)}) == 180
    assert _ausrichtung_waehlen({0: _b(0.0), 180: _b(0.0), 90: _b(0.01), 270: _b(0.45)}) == 270
    assert _ausrichtung_waehlen({0: _b(0.2), 180: _b(0.3)}) == 0, "Drehung nicht deutlich besser"
    assert _ausrichtung_waehlen({0: _b(0.0), 180: _b(0.04, treffer=4)}) == 0, "Drehung selbst unplausibel"
    assert _ausrichtung_waehlen({0: _b(0.0), 180: _b(0.0), 90: _b(0.0), 270: _b(0.0)}) == 0


def test_kurze_probe_auf_salatseite_waehlt_keine_drehung():
    """Ein einziges starkes Wort in einer kurzen Probe genügt nur auf kurzen Seiten (Stempel, Notiz) –
    auf einer Handschrift-/Rauschseite mit 200 Salatwörtern darf ein zufälliges "den" in einer Probe mit
    3 Wörtern weder eine Drehung wählen noch die Warnung unterdrücken."""
    salatseite = {0: _b(0.01, treffer=2, tokens=200),
                  180: dict(_b(0.33, treffer=1, tokens=3), klein_erlaubt=False)}
    assert _naechster_winkel(salatseite) == 90
    assert _ausrichtung_waehlen(salatseite) == 0
    stempel = {0: _b(0.0, treffer=0, tokens=6), 180: dict(_b(0.2, treffer=1, tokens=5), klein_erlaubt=True)}
    assert _naechster_winkel(stempel) is None and _ausrichtung_waehlen(stempel) == 180


@pytest.fixture(scope="module")
def gedrehte_briefe(tmp_path_factory, dienst):
    """Textreiche Briefseiten als Scan, aufrecht/kopfstehend/seitlich – parallel per vorab() gelesen."""
    ordner = tmp_path_factory.mktemp("gedreht")
    pdfs = {}
    for winkel in (0, 180, 90, 270):
        pdfs[winkel], _ = scan_pdf(ordner / f"brief_{winkel}.pdf", zeilen=BRIEF, winkel=winkel, dpi=150)
    tabelle = ["Kfz-Haftpflicht  KH-2025-004711  SF 12  VK  TK", "GmbH & Co. KG  Vers.-Nr.  Kunden-Nr.  EUR  %",
               "AB12 CD34 EF56 GH78   4455/667788   300-771-882", "B-MK 4711   M-AB 123   HH-XY 99   LV   KH"]
    pdfs["tabelle"], _ = scan_pdf(ordner / "tabelle.pdf", zeilen=tabelle, dpi=150)
    for pfad in pdfs.values():
        dienst.vorab(pfad, [0])
    return pdfs


@braucht_ocr
def test_textreicher_kopfstehender_scan_wird_erkannt(gedrehte_briefe, dienst):
    """S-01/PERF-02: > 40 Wörter, alte Heuristik hielt 0° für plausibel (0,54-0,69) und las Salat."""
    erg = dienst.ergebnis(gedrehte_briefe[180], 0)
    assert erg["winkel"] == 180, erg["lesungen"]
    assert {"Mustermann", "Gladbach", "02.09.1983", "DE89"} <= set(texte(erg["woerter"]))
    assert "180°" in erg["warnung"]
    assert [m["code"] for m in erg["meldungen"]] == ["OCR_GELESEN"] and not erg["unplausibel"]
    assert dienst.winkel(gedrehte_briefe[180], 0) == 180
    assert dienst.winkel_falls_bekannt(gedrehte_briefe[180], 0) == 180


@braucht_ocr
@pytest.mark.parametrize("winkel", [90, 270])
def test_textreicher_seitlicher_scan_wird_erkannt(gedrehte_briefe, dienst, winkel):
    erg = dienst.ergebnis(gedrehte_briefe[winkel], 0)
    assert erg["winkel"] in (90, 270) and erg["winkel"] != 0
    assert {"Mustermann", "Gladbach", "DE89"} <= set(texte(erg["woerter"]))
    assert "gedreht" in erg["warnung"] and not erg["unplausibel"]
    # Wortkästen seitlicher Wörter stehen hochkant
    r = next(fitz.Rect(w[:4]) for w in erg["woerter"] if w[4] == "Mustermann")
    assert r.height > r.width
    # Zeilenbildung in Leserichtung: IBAN bleibt zusammen
    assert "IBAN: DE89 3704 0044 0532 0130 00" in woerter_zu_text(erg["woerter"], erg["winkel"])


@braucht_ocr
def test_aufrechte_seiten_ein_lauf(gedrehte_briefe, dienst):
    """Aufrechte Briefe und Code-Tabellen: genau ein OCR-Lauf, Winkel 0, keine Warnung (PERF-02)."""
    for schluessel in (0, "tabelle"):
        erg = dienst.ergebnis(gedrehte_briefe[schluessel], 0)
        assert erg["winkel"] == 0 and erg["laeufe"] == 1, (schluessel, erg["lesungen"])
        assert erg["warnung"] is None and erg["meldungen"] == []


@braucht_ocr
def test_kontroll_ocr_mit_winkel_des_originals(gedrehte_briefe, dienst):
    """S-08: Die Ausgabe eines kopfstehenden Scans enthält zu wenig Text, um die Ausrichtung neu zu bestimmen
    – text(..., winkel=w) liest in der Ausrichtung des Originals; mit 0° käme Salat heraus."""
    pdf = gedrehte_briefe[180]
    w = dienst.winkel_falls_bekannt(pdf, 0)
    assert w == 180
    richtig = dienst.text(pdf, 0, winkel=w)
    falsch = dienst.text(pdf, 0, winkel=0)
    assert "Max Mustermann" in richtig and "02.09.1983" in richtig
    assert "Mustermann" not in falsch
    assert dienst.ergebnis(pdf, 0, winkel=w)["laeufe"] == 1, "feste Ausrichtung: keine Suche"


@braucht_ocr
def test_unplausible_seite_meldet_ocr_unplausibel(tmp_path, dienst):
    """Rauschen ohne Text (Handschrift-/Foto-Ersatz): alle Ausrichtungen unplausibel -> OCR_UNPLAUSIBEL."""
    import random
    rnd = random.Random(3)
    doc = fitz.open()
    seite = doc.new_page()
    for _ in range(500):                 # Kritzel: zufällige kurze Striche wie Handschrift
        x, y = rnd.uniform(40, 550), rnd.uniform(60, 780)
        seite.draw_line((x, y), (x + rnd.uniform(-6, 6), y + rnd.uniform(-9, 9)), width=1.2)
    pix = seite.get_pixmap(dpi=150)
    scan = fitz.open()
    s = scan.new_page()
    s.insert_image(s.rect, pixmap=pix)
    pdf = tmp_path / "kritzel.pdf"
    scan.save(pdf)
    erg = dienst.ergebnis(pdf, 0)
    if len(erg["woerter"]) < ocr.MIN_TOKENS_WARNUNG:
        pytest.skip("Tesseract liest im Rauschen zu wenig Wörter für eine Plausibilitätsaussage")
    assert erg["unplausibel"] and "unplausibel" in erg["warnung"]
    assert "OCR_UNPLAUSIBEL" in [m["code"] for m in erg["meldungen"]]
    assert erg["winkel"] == 0


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
    codes = [m["code"] for m in d.ergebnis(Path("egal.pdf"), 3)["meldungen"]]
    assert codes == ["OCR_GELESEN", "OCR_UNPLAUSIBEL"]
    d.schliessen()


# ----------------------------------------------------------------------
# Zeilenbildung (EQ-01)
# ----------------------------------------------------------------------
# Echte OCR-Wörter (Ausschnitt, Gutachten EQ-01, Scan e_scan_brief_abrechnung): die Wortkästen sind ~20 pt
# hoch bei 9,6 pt Zeilenabstand – die alte Zeilenbildung verzahnte drei Zeilen und zerriss IBAN/Telefon.
EQ01_WOERTER = [
    (291.1, 235.7, 328.8, 254.9, '1.287,60'), (332.6, 235.7, 354.9, 254.9, 'EUR.'), (359.3, 235.7, 374.5, 254.9, 'Der'),
    (378.2, 235.7, 405.9, 254.9, 'Betrag'), (409.7, 235.7, 427.3, 254.9, 'wird'), (431.3, 235.7, 438.0, 254.9, 'in'),
    (441.8, 235.7, 457.4, 254.9, 'den'), (461.3, 235.7, 500.4, 254.9, 'nächsten'), (504.2, 235.7, 532.1, 254.9, 'Tagen'),
    (52.1, 245.3, 65.4, 265.0, 'auf'), (69.1, 245.3, 79.7, 265.0, 'Ihr'), (83.5, 245.3, 108.1, 265.0, 'Konto'),
    (112.3, 245.3, 134.4, 265.0, 'IBAN'), (138.5, 245.3, 162.1, 265.0, 'DE44'), (166.1, 245.3, 187.3, 265.0, '5001'),
    (190.8, 245.3, 212.1, 265.0, '0517'), (216.0, 245.3, 237.3, 265.0, '5407'), (241.0, 245.3, 262.2, 265.0, '3249'),
    (265.9, 245.3, 276.2, 265.0, '31'), (280.1, 245.3, 332.0, 265.0, 'überwiesen.'), (336.7, 245.3, 365.6, 265.0, 'Sollten'),
    (370.1, 245.3, 383.4, 265.0, 'Sie'), (387.4, 245.3, 417.5, 265.0, 'Fragen'), (421.4, 245.3, 451.0, 265.0, 'haben,'),
    (454.8, 245.3, 495.5, 265.0, 'erreichen'), (499.4, 245.3, 512.7, 265.0, 'Sie'), (516.7, 245.3, 532.9, 265.0, 'Ihre'),
    (52.1, 258.0, 132.7, 277.0, 'Ansprechpartnerin'), (137.0, 258.0, 156.4, 277.0, 'Frau'), (160.6, 258.0, 182.2, 277.0, 'Birgit'),
    (186.0, 258.0, 225.2, 277.0, 'Hofmann'), (229.2, 258.0, 251.0, 277.0, 'unter'), (254.2, 258.0, 286.7, 277.0, 'Telefon'),
    (290.6, 258.0, 306.3, 277.0, '089'), (310.3, 258.0, 356.4, 277.0, '2160-4477'), (360.7, 258.0, 380.1, 277.0, 'oder'),
    (383.5, 258.0, 397.2, 277.0, 'per'), (400.8, 258.0, 428.1, 277.0, 'E-Mail'), (431.8, 258.0, 442.0, 277.0, 'an'),
    (52.8, 265.9, 164.6, 285.4, 'k.nowak-service@vkb.de.'), (169.9, 265.9, 180.4, 285.4, 'Ihr'),
    (183.8, 265.9, 245.7, 285.4, 'Geburtsdatum'), (250.3, 265.9, 298.9, 285.4, '12.05.1965'), (302.9, 265.9, 329.1, 285.4, 'haben'),
    (54.0, 314.9, 66.7, 324.7, 'Mit'), (69.4, 314.9, 123.1, 324.7, 'freundlichen'), (127.0, 314.9, 160.0, 324.7, 'Grüßen')]


def test_woerter_zu_text():
    acht = [(0, 0, 10, 10, "Hallo", 0, 0, 0), (12, 0, 20, 10, "Welt", 0, 0, 1), (0, 20, 10, 30, "Zeile", 0, 1, 0)]
    assert woerter_zu_text(acht) == "Hallo Welt\nZeile"
    fuenf = [(0, 0, 10, 10, "Hallo"), (12, 0, 20, 10, "Welt"), (0, 20, 10, 30, "Zeile")]
    assert woerter_zu_text(fuenf) == "Hallo Welt\nZeile"
    assert woerter_zu_text([]) == "" and woerter_zu_zeilen([]) == []


def test_zeilenbildung_hohe_wortkaesten_eq01():
    zeilen = [" ".join(w[4] for w in z) for z in woerter_zu_zeilen(EQ01_WOERTER)]
    assert "auf Ihr Konto IBAN DE44 5001 0517 5407 3249 31 überwiesen. Sollten Sie Fragen haben, erreichen Sie Ihre" in zeilen
    assert "Ansprechpartnerin Frau Birgit Hofmann unter Telefon 089 2160-4477 oder per E-Mail an" in zeilen
    assert len(zeilen) == 5
    from anonymisierer.muster import finde_iban
    assert finde_iban(woerter_zu_text(EQ01_WOERTER)) == ["DE44 5001 0517 5407 3249 31"]
    # woerter_zu_text ist woerter_zu_zeilen, verbunden
    assert woerter_zu_text(EQ01_WOERTER) == "\n".join(zeilen)


def test_zeilenbildung_gedreht_und_8_tupel():
    """Gleiche Lesefolge, Koordinaten um 180°/90° gedreht (kopfstehender/seitlicher Scan): gleiche Zeilen."""
    soll = woerter_zu_text(EQ01_WOERTER)
    b, h = 595.0, 842.0
    kopf = [(b - w[2], h - w[3], b - w[0], h - w[1], w[4]) for w in EQ01_WOERTER]
    assert woerter_zu_text(kopf, winkel=180) == soll
    assert woerter_zu_text(kopf) == soll, "Ausrichtung aus der Lesefolge geschätzt"
    seitlich = [(w[1], b - w[2], w[3], b - w[0], w[4]) for w in EQ01_WOERTER]
    assert woerter_zu_text(seitlich) == soll
    # 8-Tupel: OCR-Zeilenwechsel trennt, Tabellenspalte derselben Höhe wird angehängt
    acht = [(48, 98, 90, 114, "Vers.-Nr.:", 2, 0, 0), (150, 98, 200, 114, "4455/667788", 2, 1, 0),
            (48, 108, 95, 129, "Behandler:", 2, 2, 0), (150, 108, 170, 129, "Dr.", 2, 3, 0),
            (173, 108, 200, 129, "Berger", 2, 3, 1)]
    assert woerter_zu_text(acht) == "Vers.-Nr.: 4455/667788\nBehandler: Dr. Berger"


def test_zeilenbildung_ohne_lesefolge():
    """5-Tupel, die NICHT in Lesefolge kommen (sortiert, gemischt): geometrischer Rückfall mit Toleranz aus
    dem Zeilenabstand liefert dieselben sauberen Zeilen."""
    import random
    woerter = [(50, 90, 100, 102, "IBAN"), (105, 90, 300, 102, "DE89"), (50, 70, 80, 82, "Max"),
               (85, 70, 150, 82, "Mustermann")]
    assert woerter_zu_text(woerter) == "Max Mustermann\nIBAN DE89"
    soll = woerter_zu_text(EQ01_WOERTER)
    for saat in range(6):
        gemischt = random.Random(saat).sample(EQ01_WOERTER, len(EQ01_WOERTER))
        assert woerter_zu_text(gemischt) == soll, saat


def test_zeilenbildung_schraeger_scan():
    """2° Schräglage: Zeilen driften über die Breite um mehr als den Zeilenabstand – sie bleiben trotzdem
    zusammen, weil nur benachbarte Wörter verglichen werden."""
    import math
    woerter = []
    for z in range(6):
        for i in range(10):
            x = 50 + i * 50
            y = 100 + z * 12 + x * math.tan(math.radians(2))
            woerter.append((x, y, x + 40, y + 10, f"w{z}{i}"))
    zeilen = woerter_zu_zeilen(woerter)
    assert len(zeilen) == 6 and all(len(z) == 10 for z in zeilen)
    assert [w[4] for w in zeilen[2]] == [f"w2{i}" for i in range(10)]


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
    assert "Mustermann" in texte(woerter) and "100245678" in texte(woerter)
    soll = wort_rect(erwartet, "Mustermann")
    ist = next(fitz.Rect(w[:4]) for w in woerter if w[4] == "Mustermann")
    assert abs(ist.x0 - soll.x0) < 4 and abs(ist.x1 - soll.x1) < 4 and abs(ist.y1 - soll.y1) < 6, (ist, soll)
    vorher = dienst.statistik["auftraege"]
    woerter2, _ = dienst.woerter(pdf, 0)
    text = dienst.text(pdf, 0)
    assert dienst.statistik["auftraege"] == vorher, "zweiter Aufruf derselben Seite kommt aus dem Zwischenspeicher"
    assert woerter2 == woerter
    assert "Max Mustermann" in text and "\n" in text


@braucht_ocr
def test_cache_haengt_am_inhalt_nicht_am_pfad(tmp_path, dienst):
    """Dieselbe Hilfsdatei wird für mehrere Dokumente nacheinander benutzt (Kontroll-OCR der Schwärzung):
    neuer Inhalt am selben Pfad, gleiche Größe -> neues Ergebnis, nie ein veralteter Treffer."""
    pfad = tmp_path / "ausgabe.pdf"

    def schreiben(text):
        doc = fitz.open()
        doc.new_page().insert_text((72, 100), text, fontsize=20, fontname="helv")
        doc.save(pfad)
        doc.close()

    schreiben("Erste Fassung Anton Alpha 1111")
    with open(pfad, "ab") as f:
        f.write(b"\n" * 64)                          # Reserve, damit beide Fassungen gleich groß werden
    a, _ = dienst.woerter(pfad, 0)
    st = pfad.stat()
    schreiben("Erste Fassung Berta Betaa 2222")
    with open(pfad, "ab") as f:
        f.write(b"\n" * (st.st_size - pfad.stat().st_size))
    os.utime(pfad, ns=(st.st_atime_ns, st.st_mtime_ns))   # grobe Zeitstempel (FAT, Netzlaufwerk)
    assert pfad.stat().st_size == st.st_size and pfad.stat().st_mtime_ns == st.st_mtime_ns
    b, _ = dienst.woerter(pfad, 0)
    assert "Alpha" in texte(a) and "Betaa" in texte(b) and "Alpha" not in texte(b)
    assert ocr._datei_fingerabdruck(pfad)[1] != 0


@braucht_ocr
def test_vorab_liest_parallel_und_fuellt_den_cache(tmp_path):
    """PERF-05: vorab() reiht mehrere Seiten ein, alle Arbeiter rechnen gleichzeitig; ergebnis() wartet nur."""
    pfad = tmp_path / "mehrseitig.pdf"
    doc = fitz.open()
    for i in range(4):
        bild, breite, hoehe, _ = textseite_bild(BRIEF + [f"Seite {i + 1} von 4"], dpi=150)
        s = doc.new_page(width=breite, height=hoehe)
        s.insert_image(s.rect, stream=bild)
    doc.save(pfad)
    doc.close()
    with OcrDienst(prozesse=2) as d:
        pool = d._pool_holen()                           # beide Arbeiter starten (Startzeit nicht mitmessen)
        for f in [pool.submit(time.sleep, 0.5) for _ in range(2)]:
            f.result()
        start = time.perf_counter()
        assert d.vorab(pfad, [0, 1, 2, 3]) == 4
        assert d.vorab(pfad, [0, 1]) == 0, "laufende Aufträge werden nicht doppelt eingereiht"
        eingereicht = d.statistik["auftraege"]
        ergebnisse = [d.ergebnis(pfad, nr) for nr in range(4)]
        parallel = time.perf_counter() - start
        assert d.statistik["auftraege"] == eingereicht, "ergebnis() reicht nichts neu ein"
        assert all(f"{nr + 1}" in texte(e["woerter"]) for nr, e in enumerate(ergebnisse))
        # Kontroll-OCR als Stapel mit fester Ausrichtung je Seite
        assert d.vorab(pfad, [0, 1], winkel={0: 0, 1: 180}) == 2
        assert d.ergebnis(pfad, 1, winkel=180)["winkel"] == 180
    with OcrDienst(prozesse=1) as d:
        d.selbsttest()
        start = time.perf_counter()
        for nr in range(4):
            d.ergebnis(pfad, nr)
        einzeln = time.perf_counter() - start
    assert parallel < einzeln * 0.85, (parallel, einzeln)


@braucht_ocr
def test_dienst_rotate_attribut_wird_herausgerechnet(tmp_path, dienst):
    """M-29: /Rotate 90 und 270 – Wörter in Koordinaten der Seite nach remove_rotation, nichts fehlt."""
    for rotate in (90, 270):
        pdf, erwartet = scan_pdf(tmp_path / f"rot{rotate}.pdf", rotate=rotate)
        woerter, warnung = dienst.woerter(pdf, 0)
        assert warnung is None, warnung
        for t in ("Mustermann", "100245678", "Stuttgart", "Nachricht."):
            assert t in texte(woerter), (rotate, t, texte(woerter))
        soll = wort_rect(erwartet, "Mustermann")
        ist = next(fitz.Rect(w[:4]) for w in woerter if w[4] == "Mustermann")
        assert abs(ist.x0 - soll.x0) < 5 and abs(ist.y1 - soll.y1) < 6, (rotate, ist, soll)


@braucht_ocr
def test_dienst_erkennt_kopfstehenden_scan(tmp_path, dienst):
    pdf, erwartet = scan_pdf(tmp_path / "kopf.pdf", winkel=180)
    woerter, warnung = dienst.woerter(pdf, 0)
    assert warnung and "180°" in warnung, warnung
    assert "Mustermann" in texte(woerter) and "Stuttgart" in texte(woerter)
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
    assert "Mustermann" in texte(woerter)
    ist = next(fitz.Rect(w[:4]) for w in woerter if w[4] == "Mustermann")
    assert ist.height > ist.width, "seitliches Wort: Box ist höher als breit"


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
    assert "Musterfrau" in texte(woerter), texte(woerter)
    assert all(rect.contains(fitz.Rect(w[:4])) or rect.intersects(fitz.Rect(w[:4])) for w in woerter)
    assert "Zeile" not in texte(woerter) and "Mustermann." not in texte(woerter)


@braucht_ocr
def test_textebene_mit_abweichender_lesung_bleibt_erhalten(tmp_path, dienst):
    """Ein OCR-Wort wird nur verworfen, wenn die Textebene an derselben Stelle GENAU dasselbe Wort hat.
    Hat sich die Textebene (z. B. eines Kopierers) verlesen, bleibt die OCR-Lesung des Bildes erhalten."""
    bild, breite, hoehe, _ = textseite_bild(["Kunde Mustermann Bergisch"], fontsize=16)
    doc = fitz.open()
    seite = doc.new_page()
    for i in range(12):
        seite.insert_text((50, 500 + 14 * i), f"Zeile {i}: sichtbarer Text, damit die Seite als Textseite gilt.", fontsize=10)
    rect = fitz.Rect(0, 0, breite, hoehe / 2)
    seite.insert_image(fitz.Rect(0, 0, breite, hoehe), stream=bild)
    # Textebene liegt über dem Bild: "Kunde" richtig, "Mustcrmann" verlesen
    seite.insert_text((60, 100), "Kunde Mustcrmann Bergisch", fontsize=16, fontname="helv", render_mode=0)
    pdf = tmp_path / "kopierer.pdf"
    doc.save(pdf)
    doc.close()
    woerter, _ = dienst.woerter(pdf, 0, clip=rect)
    assert "Mustermann" in texte(woerter), texte(woerter)
    assert "Kunde" not in texte(woerter), "identische Dublette der Textebene wird entfernt"


def test_dienst_fallback_im_prozess(monkeypatch):
    def kaputt(*a, **k):
        raise OSError("kein Prozessstart möglich")

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", kaputt)
    d = OcrDienst(prozesse=1)
    pid, methode, ist_kind = d.selbsttest()
    assert pid == os.getpid() and not ist_kind
    assert d.in_prozess and any("Hauptprozess" in h for h in d.hinweise)
    d.schliessen()


def test_pool_absturz_kein_fallback_im_hauptprozess():
    """KQ-05/S-10: Ein Auftrag, der den Arbeiter abstürzen lässt (Tesseract-Segfault), scheitert – auch
    beim zweiten und dritten Mal – mit RuntimeError; er läuft NIE im Oberflächenprozess. Danach
    arbeitet der Pool wieder normal in einem Kindprozess."""
    d = OcrDienst(prozesse=1)
    try:
        assert d.selbsttest()[2]
        for _ in range(3):
            with pytest.raises(RuntimeError, match="abgestürzt"):
                d._ausfuehren(os._exit, 3)                 # simulierter Absturz (überlebt der Test = kein Fallback)
        assert not d.in_prozess and d._pool_fehler is None
        pid, _, ist_kind = d._ausfuehren(ocr._ping_worker)
        assert pid != os.getpid() and ist_kind
        assert d.statistik["abstuerze"] >= 6
    finally:
        d.schliessen()


def test_absturz_wird_als_seitenwarnung_gemeldet(monkeypatch, tmp_path):
    """Absturz bei einer Seite: ergebnis() liefert Warnung + Meldung OCR_FEHLER, wiederholt die Seite nicht."""
    d = OcrDienst(prozesse=1)
    try:
        monkeypatch.setattr(d, "sprache", "deu")
        monkeypatch.setattr(d, "_auftrag_fuer", lambda *a: ocr._Auftrag(os._exit, (5,)))
        pfad = tmp_path / "egal.pdf"
        pfad.write_bytes(b"%PDF-1.4 egal")
        erg = d.ergebnis(pfad, 2)
        assert erg["woerter"] == [] and "Seite 3: OCR fehlgeschlagen" in erg["warnung"]
        assert [m["code"] for m in erg["meldungen"]] == ["OCR_FEHLER"]
        vorher = d.statistik["auftraege"]
        assert d.ergebnis(pfad, 2) is erg and d.statistik["auftraege"] == vorher
    finally:
        d.schliessen()


def test_pool_nicht_startbar_nach_absturz_faellt_auf_prozess_zurueck(monkeypatch):
    """Stirbt schon jeder Arbeiter beim Start (z. B. Virenscanner), ist der Pool nicht startbar: dann – und
    nur dann – läuft die OCR im eigenen Prozess (mit Hinweis)."""
    echter_pool = concurrent.futures.ProcessPoolExecutor

    def sterbender_pool(*a, **k):
        k["initializer"] = os._exit
        k["initargs"] = (7,)
        return echter_pool(*a, **k)

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", sterbender_pool)
    d = OcrDienst(prozesse=1)
    try:
        pid, _, ist_kind = d._ausfuehren(ocr._ping_worker)
        assert pid == os.getpid() and not ist_kind
        assert d.in_prozess and d._pool_fehler and any("Hauptprozess" in h for h in d.hinweise)
    finally:
        d.schliessen()


@pytest.mark.skipif(sys.platform == "win32" or not Path("/proc").exists(),
                    reason="Prozesszustand über /proc (Linux); der Wächter selbst ist plattformunabhängig")
def test_arbeiter_beenden_sich_wenn_der_elternprozess_stirbt(tmp_path):
    """GR-03/S-09: Hauptprozess wird hart beendet (Absturz, "Task beenden") – die Arbeiter folgen binnen
    Sekunden, statt als Waisen mit 100-180 MB weiterzuleben."""
    skript = tmp_path / "eltern.py"
    pids = tmp_path / "pids.txt"
    skript.write_text(textwrap.dedent(f"""
        import os, signal, sys, time
        sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})
        from anonymisierer.ocr import OcrDienst
        if __name__ == "__main__":
            d = OcrDienst(prozesse=2)
            d.selbsttest()
            d._ausfuehren(time.sleep, 0.1)
            open({str(pids)!r}, "w").write(" ".join(str(p.pid) for p in d._pool._processes.values()))
            os.kill(os.getpid(), signal.SIGKILL)
    """), encoding="utf-8")
    p = subprocess.run([sys.executable, "-W", "ignore", str(skript)], timeout=120)
    assert p.returncode == -signal.SIGKILL
    kinder = [int(x) for x in pids.read_text().split()]
    assert kinder

    def lebt(pid):
        try:
            zustand = Path(f"/proc/{pid}/status").read_text().split("State:")[1].split()[0]
        except (OSError, IndexError):
            return False
        return zustand not in ("Z", "X")

    ende = time.time() + 10
    while time.time() < ende and any(lebt(k) for k in kinder):
        time.sleep(0.2)
    lebende = [k for k in kinder if lebt(k)]
    for k in lebende:
        os.kill(k, signal.SIGKILL)
    assert not lebende, f"verwaiste Arbeiter: {lebende}"


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
        assert d.vorab(pdf, [0]) == 0
        d.zuruecksetzen()
        woerter, warnung = d.woerter(pdf, 0)
        assert "Mustermann" in texte(woerter) and warnung is None
    finally:
        d.schliessen()


@braucht_ocr
def test_abbrechen_beendet_vorab_auftraege(tmp_path):
    pdf, _ = scan_pdf(tmp_path / "dicht.pdf", zeilen=BRIEF * 3)
    d = OcrDienst(prozesse=1)
    try:
        d.selbsttest()
        prozesse = list(d._pool._processes.values())
        assert d.vorab(pdf, [0]) == 1
        time.sleep(0.3)
        d.abbrechen()
        assert d.ergebnis(pdf, 0)["warnung"] == "Abgebrochen"
        ende = time.time() + 10
        while time.time() < ende and any(p.is_alive() for p in prozesse):
            time.sleep(0.1)
        assert not any(p.is_alive() for p in prozesse), "laufende Tesseract-Arbeiter werden beendet"
    finally:
        d.schliessen()


def test_dienst_context_manager_schliesst_pool():
    with OcrDienst(prozesse=1) as d:
        assert d.selbsttest() is not None
        assert d._pool is not None
        prozesse = list(d._pool._processes.values())
    assert d._pool is None
    ende = time.time() + 10
    while time.time() < ende and any(p.is_alive() for p in prozesse):
        time.sleep(0.1)
    assert not any(p.is_alive() for p in prozesse)


def test_programmende_beendet_arbeiter_sofort(monkeypatch):
    """Beenden-Hook: laufende Aufträge halten das Programmende nicht auf (concurrent.futures würde warten)."""
    import weakref
    d = OcrDienst(prozesse=1)
    assert d in list(ocr._DIENSTE), "jeder Dienst meldet sich für den Hook an"
    monkeypatch.setattr(ocr, "_DIENSTE", weakref.WeakSet([d]))     # andere Dienste der Testsitzung schonen
    d.selbsttest()
    prozesse = list(d._pool._processes.values())
    d._pool.submit(time.sleep, 30)                                  # laufender Auftrag
    ocr._beim_beenden()
    ende = time.time() + 10
    while time.time() < ende and any(p.is_alive() for p in prozesse):
        time.sleep(0.1)
    assert not any(p.is_alive() for p in prozesse)
    d.schliessen()


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
