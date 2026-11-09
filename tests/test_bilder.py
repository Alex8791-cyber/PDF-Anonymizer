"""Tests für anonymisierer/bilder.py (Gutachten S-04): nach der Pixel-Schwärzung werden Scans wieder als JPEG
(bzw. 1-Bit-Flate) gespeichert – die Datei bleibt etwa so groß wie das Original, und die geschwärzten Pixel
bleiben geschwärzt (erneute OCR des Bereichs findet nichts)."""

import zlib
from pathlib import Path

import pytest

import pymupdf as fitz

from conftest import braucht_ocr
from anonymisierer import bilder
from anonymisierer.bilder import (bilder_neu_kodieren, bildzustand, geaenderte_bilder, jpeg_qualitaet_schaetzen,
                                  nach_schwaerzung)

ZEILEN = ["Versicherungsnehmer: Max Mustermann", "Lange Straße 7, 51429 Bergisch Gladbach",
          "IBAN: DE89 3704 0044 0532 0130 00", "Sehr geehrter Herr Kunde, vielen Dank für Ihre Nachricht.",
          "Mit freundlichen Grüßen", "Sabine Krüger, Kundenservice"] + [
          "Die Prüfung dauert in der Regel zwei bis drei Wochen. Bei Fragen sind wir für Sie da."] * 12


def scan_pdf(pfad, farbe=True, qualitaet=75, dpi=150):
    """Scan-Seite aus einem JPEG; liefert (Pfad, Rechteck von "Max Mustermann" in Seitenkoordinaten – der
    Name steht genau einmal auf der Seite)."""
    quelle = fitz.open()
    s = quelle.new_page()
    y = 80
    for z in ZEILEN:
        s.insert_text((60, y), z, fontsize=12, fontname="helv", color=(0.1, 0.1, 0.4) if farbe else (0, 0, 0))
        y += 22
    name = s.search_for("Max Mustermann")[0]
    pix = s.get_pixmap(dpi=dpi, colorspace=fitz.csRGB if farbe else fitz.csGRAY)
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_image(seite.rect, stream=pix.tobytes("jpeg", jpg_quality=qualitaet))
    doc.save(pfad)
    doc.close()
    quelle.close()
    return Path(pfad), name


def schwaerzen(doc, seite, rect, neu_kodieren=True):
    vorher = bildzustand(seite)
    seite.add_redact_annot(rect + (-2, -2, 2, 2), fill=(0.92, 0.92, 0.92))
    seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                           text=fitz.PDF_REDACT_TEXT_REMOVE)
    return nach_schwaerzung(doc, seite, vorher) if neu_kodieren else 0


@pytest.mark.parametrize("farbe", [True, False])
def test_geschwaerzter_jpeg_scan_bleibt_klein(tmp_path, farbe):
    pdf, name = scan_pdf(tmp_path / "scan.pdf", farbe=farbe)
    original = pdf.stat().st_size
    groessen = {}
    for neu in (False, True):
        doc = fitz.open(pdf)
        seite = doc[0]
        komponenten = fitz.Pixmap(doc, seite.get_images()[0][0]).n
        anzahl = schwaerzen(doc, seite, name, neu_kodieren=neu)
        xref = seite.get_images()[0][0]
        if neu:
            assert anzahl == 1
            assert doc.xref_get_key(xref, "Filter")[1] == "/DCTDecode"
            assert fitz.Pixmap(doc, xref).n == komponenten, "Farbraum bleibt"
        ziel = tmp_path / f"aus_{neu}.pdf"
        doc.save(ziel, garbage=4, deflate=True)
        doc.close()
        groessen[neu] = ziel.stat().st_size
    assert groessen[True] <= 1.3 * original, groessen
    assert groessen[False] > 1.3 * groessen[True], f"ohne Neukodierung größer: {groessen}"


@braucht_ocr
def test_geschwaerzte_pixel_bleiben_nach_neukodierung_weg(tmp_path):
    from anonymisierer.ocr import OcrDienst
    pdf, name = scan_pdf(tmp_path / "scan.pdf")
    doc = fitz.open(pdf)
    schwaerzen(doc, doc[0], name)
    aus = tmp_path / "aus.pdf"
    doc.save(aus, garbage=4, deflate=True)
    doc.close()
    with OcrDienst(prozesse=1) as dienst:
        woerter, _ = dienst.woerter(aus, 0)
        texte = [w[4] for w in woerter]
        bereich, _ = dienst.woerter(aus, 0, clip=name + (-30, -6, 30, 6))
    assert "Mustermann" not in texte and "Max" not in texte, texte
    assert "Versicherungsnehmer:" in texte and "Gladbach" in texte, "übriger Text bleibt lesbar"
    assert not any("Muster" in w[4] for w in bereich)
    # der geschwärzte Bereich ist gleichmäßig grau (JPEG-Rauschen höchstens gering)
    d = fitz.open(aus)
    pix = d[0].get_pixmap(dpi=72, clip=name + (-1, -1, 1, 1), colorspace=fitz.csGRAY)
    werte = pix.samples
    assert max(werte) - min(werte) < 40 and abs(sum(werte) / len(werte) - 0.92 * 255) < 12
    d.close()


def _einbit_pdf(pfad, maske=False):
    """1-Bit-Scan (Fax/Schwarzweiß) wie aus einem Scanner: DeviceGray 1 bpc oder ImageMask."""
    quelle = fitz.open()
    s = quelle.new_page(width=400, height=60)
    s.insert_text((10, 40), "Name: Max Mustermann geb. 02.09.1983", fontsize=16)
    pix = s.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    quelle.close()
    breite, hoehe = pix.width, pix.height
    zeile = (breite + 7) // 8
    bits = bytearray(zeile * hoehe)
    for y in range(hoehe):
        for x in range(breite):
            if pix.samples[y * breite + x] >= 128:     # 1 = weiß (Graustufe) bzw. nicht malen (Maske)
                bits[y * zeile + x // 8] |= 0x80 >> (x % 8)
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((10, 10), " ")
    xref = doc.get_new_xref()
    zusatz = "/ImageMask true /Decode [0 1]" if maske else "/ColorSpace /DeviceGray"
    doc.update_object(xref, f"<< /Type /XObject /Subtype /Image /Width {breite} /Height {hoehe} "
                            f"/BitsPerComponent 1 {zusatz} >>")
    doc.update_stream(xref, bytes(bits), compress=True)
    art, res = doc.xref_get_key(seite.xref, "Resources")
    if art == "xref":
        doc.xref_set_key(int(res.split()[0]), "XObject", f"<< /Im0 {xref} 0 R >>")
    else:
        doc.xref_set_key(seite.xref, "Resources/XObject", f"<< /Im0 {xref} 0 R >>")
    c = seite.get_contents()[0]
    doc.update_stream(c, (b"q 0 g " if maske else b"q ") + b"400 0 0 60 50 700 cm /Im0 Do Q")
    doc.save(pfad)
    doc.close()
    return Path(pfad)


@pytest.mark.parametrize("maske", [False, True])
def test_einbit_scan_bleibt_einbit_und_klein(tmp_path, maske):
    pdf = _einbit_pdf(tmp_path / "fax.pdf", maske=maske)
    doc = fitz.open(pdf)
    seite = doc[0]
    original = len(doc.xref_stream_raw(seite.get_images()[0][0]))
    bild = next(fitz.Rect(b) for art, b in seite.get_bboxlog() if "image" in art or "imgmask" in art)
    rect = fitz.Rect(bild.x0 + 0.4 * bild.width, bild.y0, bild.x1, bild.y1)      # Name und Datum
    assert schwaerzen(doc, seite, rect) == 1
    xref = seite.get_images()[0][0]
    assert doc.xref_get_key(xref, "BitsPerComponent")[1] == "1"
    assert doc.xref_get_key(xref, "Filter")[1] == "/FlateDecode"
    assert (doc.xref_get_key(xref, "ImageMask")[1] == "true") == maske
    roh = doc.xref_stream_raw(xref)
    assert len(roh) < len(zlib.decompress(roh)) / 3, "1-Bit-Daten gepackt"
    assert len(roh) < 2 * original, (len(roh), original)   # (Datei: + ICC-Profil, das MuPDF ergänzt)
    doc.close()


def test_verlustfreies_original_bleibt_verlustfrei(tmp_path):
    """Grafik mit wenigen Farben (Diagramm/Screenshot, Flate): JPEG wäre nicht deutlich kleiner -> Flate."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 300), False)
    pix.set_rect(pix.irect, (255, 255, 255))
    for i in range(0, 400, 40):
        pix.set_rect(fitz.IRect(i, 50, i + 20, 250), (200, 30, 30))
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_image(fitz.Rect(50, 50, 450, 350), pixmap=pix)
    pdf = tmp_path / "grafik.pdf"
    doc.save(pdf, deflate=True)
    doc.close()
    doc = fitz.open(pdf)
    seite = doc[0]
    assert "Flate" in doc.xref_get_key(seite.get_images()[0][0], "Filter")[1]
    schwaerzen(doc, seite, fitz.Rect(60, 60, 120, 90))
    xref = seite.get_images()[0][0]
    assert doc.xref_get_key(xref, "Filter")[1] == "/FlateDecode"
    doc.close()


def test_jpeg_qualitaet_schaetzen():
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 64, 64), False)
    pix.set_rect(pix.irect, (90, 140, 200))
    for q in (40, 60, 75, 85, 95):
        geschaetzt = jpeg_qualitaet_schaetzen(pix.tobytes("jpeg", jpg_quality=q))
        assert geschaetzt is not None and abs(geschaetzt - q) <= 3, (q, geschaetzt)
    assert jpeg_qualitaet_schaetzen(b"keine Bilddaten") is None


def test_qualitaet_des_originals_wird_uebernommen(tmp_path):
    """Ein JPEG mit Qualität 60 wird nicht mit 85 neu kodiert (sonst wächst die Datei ohne Nutzen)."""
    pdf, name = scan_pdf(tmp_path / "scan.pdf", qualitaet=60)
    doc = fitz.open(pdf)
    seite = doc[0]
    schwaerzen(doc, seite, name)
    xref = seite.get_images()[0][0]
    q = jpeg_qualitaet_schaetzen(doc.xref_stream_raw(xref))
    assert q is not None and q <= 64, q
    doc.close()


def test_nur_das_geschwaerzte_bild_wird_neu_kodiert(tmp_path):
    """Zwei gleich große Bilder, eines wird geschwärzt: nur dessen neues Objekt wird kodiert, das andere
    Bild bleibt Byte für Byte unverändert."""
    pdf, name = scan_pdf(tmp_path / "scan.pdf")
    quelle = fitz.open(pdf)
    jpeg = quelle.extract_image(quelle[0].get_images()[0][0])["image"]
    quelle.close()
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_image(fitz.Rect(0, 0, 297, 421), stream=jpeg)
    seite.insert_image(fitz.Rect(298, 421, 595, 842), stream=jpeg, keep_proportion=False)
    doc.save(tmp_path / "zwei.pdf")
    doc.close()
    doc = fitz.open(tmp_path / "zwei.pdf")
    seite = doc[0]
    vorher = bildzustand(seite)
    rohe = {x: doc.xref_stream_raw(x) for x in vorher}
    seite.add_redact_annot(fitz.Rect(20, 20, 120, 40))
    seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
    neu = geaenderte_bilder(seite, vorher)
    jetzt = [e[0] for e in seite.get_images()]
    if len(vorher) == 1:          # gleiches Bild zweimal platziert: MuPDF teilt das Objekt
        assert len(neu) >= 1
    else:
        assert len(neu) == 1 and len(set(jetzt) & set(vorher)) == 1
        unveraendert = (set(jetzt) & set(vorher)).pop()
        assert doc.xref_stream_raw(unveraendert) == rohe[unveraendert]
    assert bilder_neu_kodieren(doc, neu) == len(neu)
    for x in neu:
        assert doc.xref_get_key(x, "Filter")[1] == "/DCTDecode"
    doc.close()


def test_menge_statt_zuordnung_und_robustheit(tmp_path):
    """bilder_neu_kodieren nimmt auch eine einfache Menge von xrefs; Unsinn bricht nichts ab."""
    pdf, name = scan_pdf(tmp_path / "scan.pdf")
    doc = fitz.open(pdf)
    seite = doc[0]
    seite.add_redact_annot(name)
    seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
    xref = seite.get_images()[0][0]
    assert doc.xref_get_key(xref, "Filter")[0] == "null", "MuPDF legt das Bild unkomprimiert an"
    assert bilder_neu_kodieren(doc, {xref, 99999, seite.xref}) == 1
    assert doc.xref_get_key(xref, "Filter")[1] == "/DCTDecode"
    assert bilder_neu_kodieren(doc, {xref}) == 0, "schon kompakt: nichts zu tun"
    doc.close()
