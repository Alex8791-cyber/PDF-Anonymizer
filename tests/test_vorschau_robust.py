"""Vorschau robust (Runde 3, Paket „vorschau-oberflaeche“):

  1. Zyklus im Strukturbaum: MuPDF 1.28 hängt beim Rendern einer solchen Seite über zehn Minuten (gemessen; Textauszug,
     Zeichenspur, Pfade, SVG und Suche sind nicht betroffen – nur das Rastern). Jeder Renderweg der Vorschau
     (vorschau.py, gui_attrappen.py) und der Tintenanteil in Analyse und Schwärzung rendern deshalb ohne Strukturbaum –
     an einer Kopie im Speicher bzw. nur für die Dauer des Renderns; das Original bleibt unverändert. Vorher hing an
     einer solchen PDF mit einer kaum lesbaren Scan-Seite schon die ANALYSE (Tintenanteil), nicht nur die Vorschau. Die
     Renderwege laufen hier in einem eigenen Prozess mit Zeitlimit, damit ein Rückfall den Test scheitern lässt statt
     die ganze Testsitzung aufzuhängen.
  2. R-05-Rest: Seiten mit /Rotate 90/180/270 und CropBox zeigen in jeder Vorschau genau den Ausschnitt, den Analyse
     und Schwärzung sehen (dieselbe Seitenvorbereitung seitenmodell.dokument_vorbereiten statt remove_rotation).
"""

import hashlib
import importlib
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import pymupdf as fitz

from conftest import braucht_ocr
from anonymisierer import analyse, ocr, vorschau
from anonymisierer import gui_attrappen as attrappen
from anonymisierer.analyse import analysiere_pdf
from anonymisierer.schwaerzung import schwaerze_pdf

WURZEL = Path(__file__).resolve().parent.parent
NAME = "Max Mustermann"
ZEITLIMIT_S = 120          # normal: wenige Sekunden; der Fehler wäre ein Hängen über zehn Minuten
STRECKE_S = 240            # ganze Strecke mit OCR; unter der Testschranke des CI (--timeout=300)
KONTROLLE_S = 4            # so lange darf das ungeschützte Rendern zeigen, dass es hängt


# ----------------------------------------------------------------------
# Test-PDF mit Zyklus im Strukturbaum
# ----------------------------------------------------------------------
def strukturbaum_mit_zyklus(doc) -> "fitz.Document":
    """Getaggte PDF wie aus einem Präsentationsprogramm, deren Strukturbaum einen Zyklus hat (nachgebaut nach
    PyMuPDF-Testdatei test_2548.pdf: Tabelle -> Zeile -> Tabelle). Jede Seite bekommt zwei Marked-Content-Abschnitte
    (MCID 0 und 1), deren Strukturelemente keinen gemeinsamen Vorfahren haben: beim Wechsel vom ersten zum zweiten
    prüft MuPDF den ganzen Strukturbaum (pdf_check_structure_tree) und läuft dabei die Elternkette des ParentTree-
    Eintrags im Zyklus endlos hoch. Gibt das Dokument neu geöffnet zurück."""
    doc = fitz.open("pdf", doc.tobytes())
    wurzel, ohne_eltern, k1, k2, baum = (doc.get_new_xref() for _ in range(5))
    nums, kinder = [], []
    for nr in range(len(doc)):
        seite = doc[nr]
        xrefs = seite.get_contents()
        alt = b"".join(doc.xref_stream(x) for x in xrefs)
        doc.update_stream(xrefs[0], b"/P <</MCID 0>> BDC\n" + alt + b"\nEMC\n/P <</MCID 1>> BDC\nEMC\n")
        for x in xrefs[1:]:
            doc.update_stream(x, b"")
        e0, e1, e2 = (doc.get_new_xref() for _ in range(3))
        doc.update_object(e0, f"<</Type/StructElem/S/P/P {wurzel} 0 R/Pg {seite.xref} 0 R/K 0>>")
        doc.update_object(e1, f"<</Type/StructElem/S/P/P {ohne_eltern} 0 R/Pg {seite.xref} 0 R/K 1>>")
        doc.update_object(e2, f"<</Type/StructElem/S/TD/P {k1} 0 R/Pg {seite.xref} 0 R/K 2>>")
        doc.xref_set_key(seite.xref, "StructParents", str(nr))
        nums.append(f"{nr} [{e0} 0 R {e1} 0 R {e2} 0 R]")
        kinder.append(f"{e0} 0 R")
    doc.update_object(ohne_eltern, "<</Type/StructElem/S/Sect>>")
    doc.update_object(k1, f"<</Type/StructElem/S/Table/P {k2} 0 R/K [{k2} 0 R]>>")
    doc.update_object(k2, f"<</Type/StructElem/S/TR/P {k1} 0 R/K [{k1} 0 R]>>")
    doc.update_object(baum, f"<</Nums [{' '.join(nums)}]>>")
    doc.update_object(wurzel, f"<</Type/StructTreeRoot/K [{' '.join(kinder)}]/ParentTree {baum} 0 R"
                              f"/ParentTreeNextKey {len(doc)}>>")
    kat = doc.pdf_catalog()
    doc.xref_set_key(kat, "StructTreeRoot", f"{wurzel} 0 R")
    doc.xref_set_key(kat, "MarkInfo", "<</Marked true>>")
    return fitz.open("pdf", doc.tobytes())


def scan_seite_einfuegen(doc, zeilen, dpi=150):
    """Scan-Seite (gerenderter Text als JPEG) anhängen – wenige Wörter: die Analyse prüft dann den Tintenanteil."""
    vorlage = fitz.open()
    s = vorlage.new_page()
    for i, z in enumerate(zeilen):
        s.insert_text((60, 100 + 22 * i), z, fontsize=13, fontname="helv")
    pix = s.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    bild = pix.tobytes("jpeg", jpg_quality=80)
    vorlage.close()
    seite = doc.new_page(width=pix.width * 72 / dpi, height=pix.height * 72 / dpi)
    seite.insert_image(seite.rect, stream=bild)


def zyklus_pdf(pfad: Path, scan: bool = False) -> Path:
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((72, 100), f"Versicherungsnehmer: {NAME}", fontsize=12)
    seite.insert_text((72, 130), "Hauptstraße 12, 90402 Nürnberg", fontsize=12)
    if scan:
        scan_seite_einfuegen(doc, [f"Herr {NAME}", "Hauptstraße 12", "90402 Nürnberg", "Unterschrift"])
    strukturbaum_mit_zyklus(doc).save(pfad)
    doc.close()
    return pfad


def getaggte_pdf(pfad: Path) -> Path:
    """Getaggte PDF mit gewöhnlichem Strukturbaum (ohne Zyklus) – für Prüfungen im Testprozess."""
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), f"Versicherungsnehmer: {NAME}", fontsize=12)
    doc = fitz.open("pdf", doc.tobytes())
    wurzel, element = doc.get_new_xref(), doc.get_new_xref()
    doc.update_object(element, f"<</Type/StructElem/S/P/P {wurzel} 0 R/Pg {doc[0].xref} 0 R>>")
    doc.update_object(wurzel, f"<</Type/StructTreeRoot/K [{element} 0 R]>>")
    doc.xref_set_key(doc.pdf_catalog(), "StructTreeRoot", f"{wurzel} 0 R")
    doc.save(pfad)
    doc.close()
    return pfad


def _hash(pfad: Path) -> str:
    return hashlib.sha256(Path(pfad).read_bytes()).hexdigest()


def im_eigenen_prozess(code: str, zeitlimit: float):
    """Führt Python-Code in einem eigenen Prozess aus (Projektwurzel importierbar). Rückgabe: (fertig, Ausgabe).
    Bei Zeitüberschreitung wird der Prozess beendet; die Ausgabe zeigt, welche Schritte noch fertig wurden."""
    kopf = f"import sys, time\nsys.path.insert(0, {str(WURZEL)!r})\n"
    try:
        lauf = subprocess.run([sys.executable, "-W", "ignore", "-c", kopf + textwrap.dedent(code)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=zeitlimit, cwd=str(WURZEL), env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except subprocess.TimeoutExpired as e:
        ausgabe = e.stdout or b""
        if isinstance(ausgabe, bytes):
            ausgabe = ausgabe.decode("utf-8", "replace")
        return False, ausgabe
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    return True, lauf.stdout


RENDERWEGE = '''
import pymupdf as fitz
from anonymisierer import analyse, vorschau
from anonymisierer import gui_attrappen as attrappen
pfad = {pfad!r}

def baum(doc):
    return doc.xref_get_key(doc.pdf_catalog(), "StructTreeRoot")[0]

def schritt(name, f):
    t = time.perf_counter()
    f()
    print("fertig", name, round(time.perf_counter() - t, 2), flush=True)

with fitz.open(pfad) as d:
    seiten = len(d)
schritt("vorschau.seite_bild(Pfad)", lambda: [vorschau.seite_bild(pfad, i, 1.0) for i in range(seiten)])

def mit_dokument(modul):
    with fitz.open(pfad) as d:
        for i in range(seiten):
            modul.seite_bild(d, i, 1.0)
        assert baum(d) == "xref", "Strukturbaum des übergebenen Dokuments verändert"
schritt("vorschau.seite_bild(Dokument)", lambda: mit_dokument(vorschau))
schritt("vorschau.ausgabe_vorschau", lambda: vorschau.ausgabe_vorschau(pfad, [], 0, 1.0))
schritt("gui_attrappen.seite_bild(Pfad)", lambda: [attrappen.seite_bild(pfad, i, 1.0) for i in range(seiten)])
schritt("gui_attrappen.seite_bild(Dokument)", lambda: mit_dokument(attrappen))

def tinte():
    with fitz.open(pfad) as d:
        for i in range(seiten):
            analyse.tintenanteil(d[i])
        assert baum(d) == "xref", "Strukturbaum nach dem Tintenanteil nicht wiederhergestellt"
schritt("analyse.tintenanteil", tinte)
print("ALLES FERTIG", flush=True)
'''


# ----------------------------------------------------------------------
# 1. Zyklus im Strukturbaum
# ----------------------------------------------------------------------
def test_strukturbaum_ausgeblendet_stellt_den_katalog_wieder_her(tmp_path):
    """Ohne Rendern im Testprozess (ein Rückfall ließe ihn sonst hängen): das prüfen die Tests im eigenen Prozess."""
    pfad = zyklus_pdf(tmp_path / "zyklus.pdf")
    with fitz.open(pfad) as doc:
        kat = doc.pdf_catalog()
        vorher = doc.xref_get_key(kat, "StructTreeRoot")
        assert vorher[0] == "xref"
        with ocr.strukturbaum_ausgeblendet(doc):
            assert doc.xref_get_key(kat, "StructTreeRoot")[0] == "null"
        assert doc.xref_get_key(kat, "StructTreeRoot") == vorher
        with pytest.raises(ZeroDivisionError):              # auch nach einem Fehler im Block
            with ocr.strukturbaum_ausgeblendet(doc):
                1 / 0
        assert doc.xref_get_key(kat, "StructTreeRoot") == vorher
    ohne = fitz.open()
    ohne.new_page()
    with ocr.strukturbaum_ausgeblendet(ohne):               # ohne Strukturbaum: nichts zu tun
        pass
    assert ohne.xref_get_key(ohne.pdf_catalog(), "StructTreeRoot")[0] == "null"


def test_alle_renderwege_der_vorschau_ueberstehen_einen_zyklus_im_strukturbaum(tmp_path):
    """Jeder Renderweg der Vorschau (Original und Ausgabe, Engine und Attrappe, Pfad und geöffnetes Dokument) und der
    Tintenanteil der Analyse sind in Sekunden fertig; die Datei bleibt unverändert. Kontrolle vorab: ohne Gegenmittel
    rendert MuPDF dieselbe Seite nicht in KONTROLLE_S Sekunden (sonst prüfte die Test-PDF nichts)."""
    pfad = zyklus_pdf(tmp_path / "zyklus.pdf")
    vorher = _hash(pfad)
    ohne_gegenmittel_fertig, _ = im_eigenen_prozess(f'''
        import pymupdf as fitz
        with fitz.open({str(pfad)!r}) as d:
            d[0].get_pixmap(dpi=20)
        ''', KONTROLLE_S)
    fertig, ausgabe = im_eigenen_prozess(RENDERWEGE.format(pfad=str(pfad)), ZEITLIMIT_S)
    assert fertig and "ALLES FERTIG" in ausgabe, (
        f"Ein Renderweg hängt am Zyklus im Strukturbaum (Zeitlimit {ZEITLIMIT_S} s). Fertig wurden nur:\n{ausgabe}")
    assert _hash(pfad) == vorher, "Die Vorschau hat das Original verändert"
    if ohne_gegenmittel_fertig:
        pytest.skip("MuPDF hängt an diesem Strukturbaum nicht (mehr) – die Renderwege sind trotzdem geprüft")


@braucht_ocr
def test_analyse_schwaerzung_und_vorschau_einer_getaggten_pdf_mit_zyklus(tmp_path):
    """Ganze Strecke im eigenen Prozess mit Zeitlimit: Analyse (mit Scan-Seite: kaum lesbar? -> Tintenanteil),
    Schwärzung, Restrisiko-Prüfung und die Vorschau von Original und Ausgabe."""
    pfad = zyklus_pdf(tmp_path / "zyklus_scan.pdf", scan=True)
    vorher = _hash(pfad)
    ziel = tmp_path / "ausgabe"
    fertig, ausgabe = im_eigenen_prozess(f'''
        from pathlib import Path
        import pymupdf as fitz
        from anonymisierer import vorschau
        from anonymisierer import gui_attrappen as attrappen
        from anonymisierer.analyse import analysiere_pdf
        from anonymisierer.ocr import OcrDienst
        from anonymisierer.restrisiko import restrisiko_pruefen
        from anonymisierer.schwaerzung import schwaerze_pdf
        pfad = Path({str(pfad)!r})
        with OcrDienst(prozesse=1) as dienst:
            e = analysiere_pdf(pfad, {{"namen", "strasse", "plzort"}}, [], [{NAME!r}], ocr=dienst)
            print("fertig Analyse", len(e["funde"]), e["fehler"], flush=True)
            s = schwaerze_pdf(pfad, e["funde"], ocr=dienst, ocr_cache=e["ocr_cache"], modell=e["modell"],
                              ziel_ordner=Path({str(ziel)!r}))
            print("fertig Schwärzung", s["status"], s["fehler"], flush=True)
            v = restrisiko_pruefen(s["ausgabe"], ocr=dienst)
            print("fertig Restrisiko", len(v), flush=True)
        for i in range(2):
            vorschau.seite_bild(pfad, i, 1.0)
            attrappen.seite_bild(pfad, i, 1.0)
            attrappen.seite_bild(s["ausgabe"], i, 1.0)
            vorschau.ausgabe_vorschau(s["ausgabe"], v, i, 1.0)
        print("fertig Vorschau", flush=True)
        text = " ".join(p.get_text() for p in fitz.open(s["ausgabe"]))
        assert {NAME!r} not in text, text
        print("ALLES FERTIG", flush=True)
        ''', STRECKE_S)
    assert fertig and "ALLES FERTIG" in ausgabe, f"Die Strecke hängt oder scheitert. Fertig wurden nur:\n{ausgabe}"
    assert _hash(pfad) == vorher


def test_vorschau_haelt_keine_datei_offen(tmp_path):
    """Die Vorschau zeichnet aus einer Kopie im Speicher: das Original lässt sich (unter Windows) danach umbenennen."""
    pfad = getaggte_pdf(tmp_path / "offen.pdf")
    vorschau.seite_bild(pfad, 0, 0.5)
    attrappen.seite_bild(pfad, 0, 0.5)
    neu = pfad.with_name("umbenannt.pdf")
    pfad.rename(neu)
    neu.unlink()
    vorschau.zwischenspeicher_leeren()
    attrappen.cache_leeren()


# ----------------------------------------------------------------------
# 2. R-05: gedrehte Seiten mit CropBox – derselbe Ausschnitt in Vorschau, Analyse und Ausgabe
# ----------------------------------------------------------------------
def gedreht_beschnitten(pfad: Path, rotate: int) -> Path:
    doc = fitz.open()
    seite = doc.new_page(width=600, height=800)
    seite.insert_text((130, 200), f"Versicherungsnehmer: {NAME}", fontsize=12)
    seite.insert_text((130, 260), "Vertrag LV-2024-887766 Tarif Komfort", fontsize=12)
    seite.insert_text((130, 600), "Unten im Ausschnitt", fontsize=12)
    seite.insert_text((20, 40), "Ausserhalb Geheimtext", fontsize=12)      # außerhalb der CropBox
    seite.set_cropbox(fitz.Rect(100, 150, 520, 700))
    seite.set_rotation(rotate)
    doc.save(pfad)
    doc.close()
    return pfad


def _bild(png: bytes) -> "fitz.Pixmap":
    return fitz.Pixmap(png)


def _dunkelster(pix, rect) -> int:
    """Kleinster Grauwert (erster Kanal) der Pixel im Rechteck (Faktor 1: pt = px)."""
    r = fitz.IRect(fitz.Rect(rect)) & fitz.IRect(0, 0, pix.width, pix.height)
    return min((pix.pixel(x, y)[0] for y in range(r.y0, r.y1) for x in range(r.x0, r.x1)), default=255)


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
def test_gedrehte_seite_mit_cropbox_zeigt_in_jeder_vorschau_den_ausschnitt_der_analyse(tmp_path, rotate):
    pdf = gedreht_beschnitten(tmp_path / f"r{rotate}.pdf", rotate)
    e = analysiere_pdf(pdf, set(), [], [NAME])
    seite = e["modell"].seiten[0]
    rect = fitz.Rect(seite.rect)
    assert (round(rect.width), round(rect.height)) == ((420, 550) if rotate % 180 == 0 else (550, 420))
    woerter = {w[1]: fitz.Rect(w[0]) for w in seite.woerter()}
    assert "Geheimtext" not in woerter and "Mustermann" in woerter

    bilder = {"vorschau(Pfad)": vorschau.seite_bild(pdf, 0, 1.0)[0],
              "Attrappe(Pfad)": attrappen.seite_bild(pdf, 0, 1.0)[0]}
    with fitz.open(pdf) as d:
        bilder["vorschau(Dokument)"] = vorschau.seite_bild(d, 0, 1.0)[0]
    with fitz.open(pdf) as d:
        bilder["Attrappe(Dokument)"] = attrappen.seite_bild(d, 0, 1.0)[0]
    referenz = _bild(bilder["vorschau(Pfad)"])
    assert (referenz.width, referenz.height) == (round(rect.width), round(rect.height))
    for name, png in bilder.items():
        pix = _bild(png)
        assert (pix.width, pix.height) == (referenz.width, referenz.height), name
        assert pix.samples == referenz.samples, f"{name} zeigt einen anderen Ausschnitt"

    # Wörter des Seitenmodells der Attrappe = Wörter der Analyse (gleiche Lage, nichts außerhalb des Ausschnitts)
    modell_a = attrappen.seiten_modell(pdf, 0)
    assert fitz.Rect(modell_a["seitenrect"]) == rect
    woerter_a = {w[1]: fitz.Rect(w[0]) for w in modell_a["woerter"]}
    assert "Geheimtext" not in woerter_a
    for wort in ("Mustermann", "LV-2024-887766", "Ausschnitt"):
        a, m = woerter_a[wort], woerter[wort]
        assert max(abs(a.x0 - m.x0), abs(a.y0 - m.y0), abs(a.x1 - m.x1), abs(a.y1 - m.y1)) < 0.6, (wort, a, m)
    # unter „Mustermann“ liegen im Vorschaubild dunkle Pixel (Bild und Modell passen übereinander)
    assert _dunkelster(referenz, woerter["Mustermann"]) < 128

    # Ausgabe: gleiche Seitengröße; außerhalb der Schwärzung zeigt sie dieselben Pixel wie die Vorschau
    s = schwaerze_pdf(pdf, e["funde"], modell=e["modell"], ziel_ordner=tmp_path / "aus")
    assert s["ausgabe"] and s["treffer"] >= 1, s
    aus = _bild(attrappen.seite_bild(s["ausgabe"], 0, 1.0)[0])
    assert (aus.width, aus.height) == (referenz.width, referenz.height)
    geschwaerzt = [fitz.Rect(t[1]) + (-3, -3, 3, 3) for f in e["funde"] for st in f["stellen"]
                   for t in seite.rechtecke(st["start"], st["ende"])]
    anders = gesamt = 0
    for y in range(0, aus.height, 3):
        for x in range(0, aus.width, 3):
            if any(g.contains(fitz.Point(x, y)) for g in geschwaerzt):
                continue
            gesamt += 1
            anders += abs(aus.pixel(x, y)[0] - referenz.pixel(x, y)[0]) > 60
    assert anders <= 0.002 * gesamt, (anders, gesamt)
    # „Unten im Ausschnitt“ steht in Vorschau und Ausgabe an derselben Stelle (dunkle Pixel in beiden)
    assert _dunkelster(referenz, woerter["Ausschnitt"]) < 128 and _dunkelster(aus, woerter["Ausschnitt"]) < 128
    vorschau.zwischenspeicher_leeren()
    attrappen.cache_leeren()


def test_vorschau_daten_der_attrappe_folgen_dem_ausschnitt(tmp_path):
    """Ohne Seitenmodell der Analyse sucht die Attrappe Funde selbst – auch dann im richtigen Ausschnitt."""
    pdf = gedreht_beschnitten(tmp_path / "r90.pdf", 90)
    daten = attrappen.vorschau_daten({"datei": pdf, "funde": [{"id": "f1", "text": NAME}]}, 0)
    assert daten["quelle"] == "attrappe"
    assert (round(daten["seitenrect"].width), round(daten["seitenrect"].height)) == (550, 420)
    assert daten["stellen"] and all(daten["seitenrect"].contains(s[0]) for s in daten["stellen"])
    attrappen.cache_leeren()


def test_reste_als_verdacht_in_den_koordinaten_der_vorschau(tmp_path):
    """Reste der Selbstkontrolle werden auf der vorbereiteten Ausgabeseite gesucht – dieselben Koordinaten wie das
    Bild der Vorschau (auch wenn eine Datei mit /Rotate und CropBox als „Ausgabe“ geprüft wird)."""
    pdf = gedreht_beschnitten(tmp_path / "r270.pdf", 270)
    verdacht = attrappen.reste_als_verdacht(pdf, ["LV-2024-887766", "Geheimtext"])
    gefunden = {v["text"]: v for v in verdacht}
    rect = fitz.Rect(attrappen.seiten_modell(pdf, 0)["seitenrect"])
    assert gefunden["LV-2024-887766"]["seite"] == 0
    assert all(rect.contains(r) for r in gefunden["LV-2024-887766"]["rechtecke"])
    assert gefunden["Geheimtext"]["seite"] is None              # außerhalb des Ausschnitts: keine Lage
    attrappen.cache_leeren()


def test_tintenanteil_aendert_das_dokument_nicht(tmp_path):
    """Der Strukturbaum ist nur während des Renderns ausgeblendet (mit Zyklus: siehe Test im eigenen Prozess)."""
    pfad = getaggte_pdf(tmp_path / "tinte.pdf")
    with fitz.open(pfad) as doc:
        vorher = doc.xref_get_key(doc.pdf_catalog(), "StructTreeRoot")
        anteil = analyse.tintenanteil(doc[0])
        assert 0.0 < anteil < 0.2
        assert doc.xref_get_key(doc.pdf_catalog(), "StructTreeRoot") == vorher


def test_attrappe_ohne_vorschau_modul_bereitet_gleich_vor(tmp_path, monkeypatch):
    """Rückfall der Attrappe, falls das Vorschau-Modul der Engine fehlt: dieselbe Seitenvorbereitung (das Bild gleicht
    dem der Engine-Vorschau pixelgenau) und kein Strukturbaum in der Kopie im Speicher."""
    pdf = gedreht_beschnitten(tmp_path / "r90.pdf", 90)
    getaggt = getaggte_pdf(tmp_path / "getaggt.pdf")
    mit_engine = vorschau.seite_bild(pdf, 0, 1.0)[0]
    attrappen.cache_leeren()
    monkeypatch.setitem(sys.modules, "anonymisierer.vorschau", None)       # Import scheitert -> eigener Rückfall
    with pytest.raises(ImportError):
        importlib.import_module("anonymisierer.vorschau")
    png, _ = attrappen.seite_bild(pdf, 0, 1.0)
    assert fitz.Pixmap(png).samples == fitz.Pixmap(mit_engine).samples
    doc = attrappen._vorbereitet(getaggt)["doc"]
    assert doc.xref_get_key(doc.pdf_catalog(), "StructTreeRoot")[0] == "null"
    with fitz.open(getaggt) as original:                                    # die Datei selbst bleibt unverändert
        assert original.xref_get_key(original.pdf_catalog(), "StructTreeRoot")[0] == "xref"
    attrappen.cache_leeren()
    vorschau.zwischenspeicher_leeren()
