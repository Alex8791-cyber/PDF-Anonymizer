"""Tests für anonymisierer/schwaerzung.py – jede Prüfung belegt einen Audit-Befund
(M-02, M-03, M-07, M-09, M-18, M-20, M-24, M-25, M-31, M-33, M-35, M-50, M-52, M-66)."""

import hashlib
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

import pymupdf as fitz

from conftest import braucht_ocr
from anonymisierer import schwaerzung
from anonymisierer.ocr import OcrDienst
from anonymisierer.schwaerzung import WARNUNG_KEIN_TREFFER, schwaerze_pdf

DATEN = Path(__file__).parent / "daten"
PDFTOTEXT = shutil.which("pdftotext")
QPDF = shutil.which("qpdf")
NAME = "Max Mustermann"
IBAN = "DE89 3704 0044 0532 0130 00"


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------
def fund(text, ersatz="[PERSON A]", kategorie="namen", seiten=()):
    return {"kategorie": kategorie, "anzeige": kategorie, "text": text, "ersatz": ersatz,
            "seiten": list(seiten), "anzahl": 1, "kontext": ""}


def funde_aus_inventar(posten):
    """Funde wie aus der Analyse: Vollnamen plus Namensbestandteile (>= 3 Zeichen) als eigene Funde."""
    funde, gesehen = [], set()
    for i, p in enumerate(posten):
        ersatz = f"[PERSON {chr(65 + i % 26)}]" if p["kategorie"] == "namen" else f"[{p['kategorie'].upper()}]"
        texte = [p["text"]]
        if p["kategorie"] == "namen":
            texte += [t for t in p["text"].replace("-", " ").split() if len(t) >= 3]
        for t in texte:
            if t.lower() not in gesehen:
                gesehen.add(t.lower())
                funde.append(fund(t, ersatz, p["kategorie"], [p["seite"]]))
    return funde


def textseite(pfad, zeilen, fontsize=10, abstand=1.2, fontname="helv", fontfile=None, seiten=1):
    doc = fitz.open()
    for _ in range(seiten):
        seite = doc.new_page()
        y = 80
        for z in zeilen:
            if z:
                seite.insert_text((50, y), z, fontsize=fontsize, fontname=fontname, fontfile=fontfile)
            y += fontsize * abstand
    doc.save(pfad)
    doc.close()
    return Path(pfad)


def scan_pdf(pfad, zeilen, dpi=200, winkel=0.0, rotate=0, fontsize=12, unsichtbare_textebene=None):
    """Baut einen 'Scan': gerenderter Text als JPEG. winkel = Schräglage des Bilds, rotate = /Rotate
    der Seite (das Bild wird gegenläufig gedreht gespeichert, damit der Viewer es aufrecht zeigt)."""
    vorlage = fitz.open()
    seite = vorlage.new_page()
    y = 100
    for z in zeilen:
        seite.insert_text((60, y), z, fontsize=fontsize, fontname="helv")
        y += 20
    woerter = seite.get_text("words")
    matrix = fitz.Matrix(dpi / 72, dpi / 72).prerotate(winkel - rotate)
    pix = seite.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
    bild = pix.tobytes("jpeg", jpg_quality=75)
    breite, hoehe = pix.width * 72 / dpi, pix.height * 72 / dpi
    vorlage.close()
    doc = fitz.open()
    p = doc.new_page(width=breite, height=hoehe)
    p.insert_image(p.rect, stream=bild)
    if unsichtbare_textebene is not None:
        yy = 100 + unsichtbare_textebene
        for z in zeilen:
            p.insert_text((60, yy), z, fontsize=fontsize, fontname="helv", render_mode=3)
            yy += 20
    if rotate:
        p.set_rotation(rotate)
    doc.save(pfad)
    doc.close()
    return Path(pfad), [tuple(w[:5]) for w in woerter]


def pdftotext(pfad):
    if not PDFTOTEXT:
        pytest.skip("pdftotext fehlt")
    return subprocess.run([PDFTOTEXT, "-layout", str(pfad), "-"], capture_output=True, text=True).stdout


def volltext(pfad):
    doc = fitz.open(pfad)
    try:
        return "\n".join(seite.get_text() for seite in doc)
    finally:
        doc.close()


def qdf_rohbytes(pfad):
    """Alle Objekte dekomprimiert (qpdf --qdf) – findet Klartext auch in Strömen und Strukturen."""
    if not QPDF:
        pytest.skip("qpdf fehlt")
    ziel = Path(str(pfad) + ".qdf")
    subprocess.run([QPDF, "--qdf", "--object-streams=disable", "--decode-level=all", str(pfad), str(ziel)],
                   capture_output=True)
    roh = ziel.read_bytes()
    return roh.decode("latin-1") + roh.decode("utf-16-be", "ignore")


def bereich_hell(pfad, nr, rect, dpi=100):
    """True, wenn im Bereich keine dunklen Pixel mehr liegen (Scan-Pixel wirklich gelöscht)."""
    doc = fitz.open(pfad)
    pix = doc[nr].get_pixmap(dpi=dpi, clip=fitz.Rect(rect), colorspace=fitz.csGRAY)
    doc.close()
    return min(pix.samples) > 150


def md5(pfad):
    return hashlib.md5(Path(pfad).read_bytes()).hexdigest()


class FakeDienst:
    """OcrDienst-Ersatz: liefert vorgegebene Wörter je (Datei, Seite) und protokolliert Aufrufe."""

    def __init__(self, woerter=None):
        self.woerter_je_seite = woerter or {}
        self.aufrufe = []
        self.hinweise = []

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, **_):
        self.aufrufe.append((Path(pdf_pfad).name, seite_nr0, clip))
        return list(self.woerter_je_seite.get(seite_nr0, [])), None

    def text(self, pdf_pfad, seite_nr0, dpi=300, **_):
        return " ".join(w[4] for w in self.woerter_je_seite.get(seite_nr0, []))

    def abbrechen(self):
        pass

    def schliessen(self):
        pass


@pytest.fixture(scope="module")
def dienst():
    with OcrDienst(prozesse=2) as d:
        yield d


# ----------------------------------------------------------------------
# M-03: Formularfelder
# ----------------------------------------------------------------------
def test_acroform_feldwerte_werden_entfernt(tmp_path):
    pdf = tmp_path / "formular.pdf"
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((50, 80), "Antrag – bitte Felder ausfüllen", fontsize=11, fontname="helv")
    for i, (name, wert) in enumerate([("name", NAME), ("iban", IBAN), ("geb", "02.09.1983")]):
        w = fitz.Widget()
        w.field_name = name
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.rect = fitz.Rect(50, 120 + 30 * i, 320, 140 + 30 * i)
        w.field_value = wert
        seite.add_widget(w)
    doc.save(pdf)
    doc.close()
    funde = [fund(NAME), fund(IBAN, "[IBAN]", "iban"), fund("02.09.1983", "[GEB-DATUM]", "geburt")]
    e = schwaerze_pdf(pdf, funde)
    assert e["fehler"] is None and e["ausgabe"] is not None
    assert e["treffer"] == 3 and e["reste"] == []
    aus = fitz.open(e["ausgabe"])
    assert list(aus[0].widgets()) == [], "Formularfelder dürfen in der Ausgabe nicht mehr existieren"
    assert aus.xref_get_key(aus.pdf_catalog(), "AcroForm")[0] == "null"
    aus.close()
    text = pdftotext(e["ausgabe"])
    for wert in (NAME, "Mustermann", "0532 0130", "02.09.1983"):
        assert wert not in text
    roh = qdf_rohbytes(e["ausgabe"])
    assert "Mustermann" not in roh and "0532" not in roh
    assert any("Formularfelder" in h for h in e["hinweise"])


def test_antrag_formular_realistisch(tmp_path):
    """Realistisches Antragsformular aus dem E2E-Audit: alle vorgesehenen Feldwerte verschwinden."""
    quelle = DATEN / "d_antrag_formular.pdf"
    pdf = tmp_path / quelle.name
    shutil.copy(quelle, pdf)
    inventar = json.loads((DATEN / "d_antrag_formular.inventar.json").read_text(encoding="utf-8"))
    posten = [p for p in inventar["pii"] if p["erwartung"] == "schwärzen"]
    funde = funde_aus_inventar(posten)
    e = schwaerze_pdf(pdf, funde)
    assert e["fehler"] is None and e["ausgabe"] is not None
    assert e["reste"] == [], e["reste"]
    aus = fitz.open(e["ausgabe"])
    assert all(list(s.widgets()) == [] for s in aus)
    aus.close()
    text = pdftotext(e["ausgabe"]).replace("\n", " ")
    text = " ".join(text.split())
    verblieben = [p["text"] for p in posten if " ".join(p["text"].split()) in text]
    assert verblieben == [], verblieben
    assert "Esposito" not in qdf_rohbytes(e["ausgabe"])


# ----------------------------------------------------------------------
# M-02 / M-20: Nachbarzeilen, enge Listen
# ----------------------------------------------------------------------
def test_versichertenliste_helvetica_9pt_vollstaendig(tmp_path):
    """t13b aus dem Audit: Liste mit 9-pt-Helvetica und 12-pt-Zeilenabstand – vorher blieben 4 Namen
    und 6 Geburtsdaten stehen, weil sich die Treffer-Rechtecke berührten."""
    pdf = tmp_path / "t13b.pdf"
    shutil.copy(DATEN / "t13b.pdf", pdf)
    namen = ["Max Mustermann", "Erika Musterfrau", "Hans Beispiel", "Petra Probe", "Karl Testmann", "Lena Muster"]
    daten = [f"0{i % 9 + 1}.0{i % 8 + 1}.198{i % 10}" for i in range(12)]
    funde = [fund(n, f"[PERSON {chr(65 + i)}]") for i, n in enumerate(namen)]
    funde += [fund(d, "[GEB-DATUM]", "geburt") for d in daten]
    e = schwaerze_pdf(pdf, funde)
    assert e["treffer"] == 24, e
    assert e["reste"] == [] and e["uebersprungen"] == 0
    text = pdftotext(e["ausgabe"])
    for n in namen + daten:
        assert n not in text, n
    assert text.count("EUR") == 12, "Beiträge der Nachbarzeilen müssen erhalten bleiben"
    assert "Versicherte Person" in text and "Geburtsdatum" in text
    assert not any("beschädigt" in h for h in e["hinweise"]), e["hinweise"]


def test_nachbarzeilen_bei_zeilenabstand_1_0_bleiben_heil(tmp_path):
    zeilen = ["Ihr Vertrag LV-2024-887766 beginnt am 01.01.2025.", NAME, "Beitrag: 500 EUR jährlich gyp",
              "IBAN " + IBAN, "Telefon 0171 2345678 (Mobil)", "Ägypten Zeile darunter"]
    for fontfile, kennung in ((None, "helv"), ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "dejavu")):
        if fontfile and not Path(fontfile).exists():
            continue
        pdf = textseite(tmp_path / f"eng_{kennung}.pdf", zeilen, fontsize=11, abstand=1.0,
                        fontname="helv" if not fontfile else "F0", fontfile=fontfile)
        e = schwaerze_pdf(pdf, [fund(NAME), fund(IBAN, "[IBAN]", "iban"), fund("0171 2345678", "[TELEFON]", "telefon")])
        text = pdftotext(e["ausgabe"])
        assert e["treffer"] == 3 and e["reste"] == []
        for rest in (NAME, "Mustermann", "0532", "2345678"):
            assert rest not in text
        for erhalten in ("Ihr Vertrag LV-2024-887766 beginnt am 01.01.2025.", "Beitrag: 500 EUR jährlich gyp",
                         "(Mobil)", "Ägypten Zeile darunter"):
            assert erhalten in text, (kennung, erhalten, text)


# ----------------------------------------------------------------------
# M-09: Ganzwort-Treffer
# ----------------------------------------------------------------------
def test_teilwoerter_bleiben_erhalten(tmp_path):
    zeilen = ["Eva Berg wohnt in Heidelberg an der Bergstraße.", "Max ist maximal MAX und Maximilian.",
              "Hans Lang bleibt langfristig in der Hansestadt.", "Ali prüft die Qualität. Lang ist lang.",
              "Nürnberger Lebensversicherung AG, Württembergische"]
    pdf = textseite(tmp_path / "teil.pdf", zeilen)
    funde = [fund("Eva Berg"), fund("Berg"), fund("Max", "[PERSON B]"), fund("Lang", "[PERSON C]"),
             fund("Hans", "[PERSON C]"), fund("Ali", "[PERSON D]")]
    e = schwaerze_pdf(pdf, funde)
    text = volltext(e["ausgabe"])
    for erhalten in ("Heidelberg", "Bergstraße", "maximal", "Maximilian", "langfristig", "Hansestadt",
                     "Qualität", "Nürnberger", "Württembergische", "ist lang."):
        assert erhalten in text, erhalten
    for weg in ("Eva Berg", "Hans Lang", "Ali prüft"):
        assert weg not in text
    assert "Max ist" not in text and "MAX und" not in text, "Max und MAX (Versalien) sind Treffer"
    assert e["reste"] == []
    # Nur Ganzwörter zählen: 'Berg' 1x, 'Max' 2x (Max, MAX), 'Lang' 1x, 'Hans' 1x, 'Ali' 1x, 'Eva Berg' 1x
    assert e["treffer"] == 7, e


# ----------------------------------------------------------------------
# M-18 / M-24: Silbentrennung
# ----------------------------------------------------------------------
def test_silbentrennung_am_zeilenende(tmp_path):
    pdf = tmp_path / "t02a.pdf"
    shutil.copy(DATEN / "t02a.pdf", pdf)          # "Sehr geehrter Herr Muster-" / "mann, vielen Dank …"
    e = schwaerze_pdf(pdf, [fund("Mustermann")])
    assert e["treffer"] == 1 and e["ausgabe"] is not None, e
    text = pdftotext(e["ausgabe"])
    assert "Muster" not in text
    assert not any(z.strip().startswith("mann") for z in text.splitlines()), text
    assert "vielen Dank" in text


def test_silbentrennung_verschiebt_keine_rechtecke(tmp_path):
    """M-24: Nach Zeilenenden mit Trennstrich lieferte search_for verschobene Boxen – 'ann', '983',
    '00' blieben stehen. Die Rechtecke kommen jetzt aus den Glyphen-Koordinaten."""
    zeilen = ["Die Versicherungs-", "nehmerin hat die Berufsunfähigkeits-", "versicherung mit Beitrags-",
              "dynamik abgeschlossen von Max Mustermann, geb. 02.09.1983,", "IBAN " + IBAN + " (SEPA)."]
    pdf = textseite(tmp_path / "trenn.pdf", zeilen)
    e = schwaerze_pdf(pdf, [fund(NAME), fund("02.09.1983", "[GEB-DATUM]", "geburt"), fund(IBAN, "[IBAN]", "iban")])
    text = pdftotext(e["ausgabe"])
    assert e["treffer"] == 3 and e["reste"] == []
    for rest in ("ann", "983", "0130", "Mustermann", "Max"):
        assert rest not in text, (rest, text)
    assert "abgeschlossen von" in text and "(SEPA)" in text and "Versicherungs-" in text


def test_getrennter_name_aus_realdokument(tmp_path):
    """c_schadenmeldung aus dem E2E-Audit: Tabellenkopf 'Versicherungsschein-' verschob die Boxen,
    'Adeyemi' blieb als 'i, Olumide' stehen; Notiz-Annotation trug Name + Telefon."""
    pdf = tmp_path / "c.pdf"
    shutil.copy(DATEN / "c_schadenmeldung.pdf", pdf)
    inventar = json.loads((DATEN / "c_schadenmeldung.inventar.json").read_text(encoding="utf-8"))
    posten = [p for p in inventar["pii"] if p["erwartung"] == "schwärzen" and p["kategorie"] != "annotation"]
    funde = funde_aus_inventar(posten)
    e = schwaerze_pdf(pdf, funde)
    assert e["fehler"] is None and e["reste"] == [], e
    text = pdftotext(e["ausgabe"])
    for rest in ("Adeyemi", "yemi", "Olumide", "Dubois", "Klein-Hoffmann", "1245 1261"):
        assert rest not in text, rest
    aus = fitz.open(e["ausgabe"])
    assert all(list(s.annots()) == [] for s in aus)
    assert not aus.metadata.get("author") and not aus.metadata.get("title")
    aus.close()
    roh = qdf_rohbytes(e["ausgabe"])
    assert "Adeyemi" not in roh and "Rückruf" not in roh


# ----------------------------------------------------------------------
# M-29 / M-28 / M-02: Scans
# ----------------------------------------------------------------------
@braucht_ocr
@pytest.mark.parametrize("rotate", [90, 270])
def test_scan_mit_rotate_attribut_vollstaendig(tmp_path, dienst, rotate):
    zeilen = ["Versicherungsnehmer " + NAME, "IBAN " + IBAN, "Kunden-Nr. 100245678 Stuttgart",
              "Geburtsdatum 02.09.1983 Lindenallee 47b"]
    pdf, _ = scan_pdf(tmp_path / f"rot{rotate}.pdf", zeilen, rotate=rotate)
    assert fitz.open(pdf)[0].rotation == rotate
    funde = [fund(NAME), fund(IBAN, "[IBAN]", "iban"), fund("100245678", "[VERTRAGS-NR]", "vertrag"),
             fund("02.09.1983", "[GEB-DATUM]", "geburt"), fund("Lindenallee 47b", "[ADRESSE]", "strasse")]
    e = schwaerze_pdf(pdf, funde, ocr=dienst)
    assert e["fehler"] is None and e["treffer"] == 5, e
    assert e["reste"] == [], e["reste"]
    assert not any("gedreht" in w for w in e["warnungen"]), "Seite mit /Rotate ist im Viewer aufrecht"
    kontrolle = dienst.text(e["ausgabe"], 0)
    for rest in ("Mustermann", "3704", "100245678", "1983", "Lindenallee"):
        assert rest not in kontrolle, (rest, kontrolle)
    assert "Stuttgart" in kontrolle


@braucht_ocr
def test_schraeger_scan_2_grad_pixel_geloescht(tmp_path, dienst):
    zeilen = ["Versicherungsnehmer " + NAME, "Sehr geehrter Herr Mustermann,", "IBAN " + IBAN,
              "Geburtsdatum 02.09.1983, Telefon 0171 2345678"]
    pdf, _ = scan_pdf(tmp_path / "schraeg.pdf", zeilen, winkel=2.0)
    funde = [fund(NAME), fund("Mustermann"), fund(IBAN, "[IBAN]", "iban"), fund("02.09.1983", "[GEB-DATUM]", "geburt"),
             fund("0171 2345678", "[TELEFON]", "telefon")]
    e = schwaerze_pdf(pdf, funde, ocr=dienst)
    assert e["fehler"] is None and e["treffer"] >= 5, e
    assert e["reste"] == [], e["reste"]
    kontrolle = dienst.text(e["ausgabe"], 0)
    for rest in ("Mustermann", "3704", "0532", "1983", "2345678"):
        assert rest not in kontrolle, (rest, kontrolle)
    assert "Versicherungsnehmer" in kontrolle


@braucht_ocr
def test_kopfstehender_scan_wird_erkannt_und_geschwaerzt(tmp_path, dienst):
    zeilen = ["Versicherungsnehmer " + NAME, "IBAN " + IBAN, "Kunden-Nr. 100245678 Stuttgart"]
    pdf, _ = scan_pdf(tmp_path / "kopf.pdf", zeilen, winkel=180)
    e = schwaerze_pdf(pdf, [fund(NAME), fund(IBAN, "[IBAN]", "iban")], ocr=dienst)
    assert e["treffer"] == 2 and e["reste"] == [], e
    assert any("180°" in w for w in e["warnungen"]), e["warnungen"]
    # Kontrolle mit der erkannten Ausrichtung (die Ausgabe ist als Bild weiterhin kopfstehend)
    kontrolle = dienst.text(e["ausgabe"], 0, winkel=180)
    assert "Mustermann" not in kontrolle and "3704" not in kontrolle and "Stuttgart" in kontrolle


def test_ocr_cache_wird_genutzt_und_pixel_geloescht(tmp_path):
    """Wortliste aus der Analyse (ocr_cache) reicht – der Dienst wird für das Original nicht gerufen."""
    zeilen = ["Versicherungsnehmer " + NAME, "IBAN " + IBAN]
    pdf, woerter = scan_pdf(tmp_path / "cache.pdf", zeilen)
    fake = FakeDienst()
    e = schwaerze_pdf(pdf, [fund(NAME, ""), fund(IBAN, "", "iban")], ocr=fake, ocr_cache={0: woerter})
    assert e["treffer"] == 2, e
    assert not any(name == "cache.pdf" for name, _, _ in fake.aufrufe), fake.aufrufe
    name_rect = fitz.Rect(min(w[0] for w in woerter if w[4] in ("Max", "Mustermann")),
                          min(w[1] for w in woerter if w[4] in ("Max", "Mustermann")),
                          max(w[2] for w in woerter if w[4] in ("Max", "Mustermann")),
                          max(w[3] for w in woerter if w[4] in ("Max", "Mustermann")))
    assert bereich_hell(e["ausgabe"], 0, name_rect), "Bildpixel des Namens müssen gelöscht sein"
    links = fitz.Rect(60, 90, 175, 104)   # "Versicherungsnehmer" bleibt
    assert not bereich_hell(e["ausgabe"], 0, links)


def test_durchsuchbarer_scan_mit_versetzter_textebene(tmp_path):
    """Kopierer-PDF: unsichtbare Textebene liegt 9 pt versetzt – Text UND Pixel müssen weg (M-02)."""
    zeilen = ["Versicherungsnehmer " + NAME, "IBAN " + IBAN]
    pdf, woerter = scan_pdf(tmp_path / "kopierer.pdf", zeilen, unsichtbare_textebene=9)
    e = schwaerze_pdf(pdf, [fund(NAME, ""), fund(IBAN, "", "iban")], ocr=FakeDienst(), ocr_cache={0: woerter})
    assert e["treffer"] >= 2 and e["reste"] == [], e
    assert "Mustermann" not in volltext(e["ausgabe"]) and "3704" not in volltext(e["ausgabe"])
    name_rect = fitz.Rect(min(w[0] for w in woerter if w[4] in ("Max", "Mustermann")),
                          min(w[1] for w in woerter if w[4] in ("Max", "Mustermann")),
                          max(w[2] for w in woerter if w[4] in ("Max", "Mustermann")),
                          max(w[3] for w in woerter if w[4] in ("Max", "Mustermann")))
    assert bereich_hell(e["ausgabe"], 0, name_rect)


@braucht_ocr
def test_bild_auf_textseite_wird_gelesen_und_geschwaerzt(tmp_path, dienst):
    """M-04: Ausweiskopie (10 % der Seite) auf einer Textseite."""
    ausweis = fitz.open()
    a = ausweis.new_page(width=300, height=120)
    a.insert_text((10, 40), "PERSONALAUSWEIS", fontsize=14, fontname="helv")
    a.insert_text((10, 70), "Erika Musterfrau", fontsize=14, fontname="helv")
    a.insert_text((10, 100), "geb. 12.08.1964 Berlin", fontsize=14, fontname="helv")
    bild = a.get_pixmap(dpi=200, colorspace=fitz.csRGB).tobytes("png")
    ausweis.close()
    doc = fitz.open()
    seite = doc.new_page()
    y = 80
    for i in range(12):
        seite.insert_text((50, y), f"Zeile {i}: Dieser Brief enthält ausreichend sichtbaren Text, um als Textseite zu gelten.", fontsize=10, fontname="helv")
        y += 14
    bildrect = fitz.Rect(60, 300, 360, 420)
    seite.insert_image(bildrect, stream=bild)
    pdf = tmp_path / "ausweis.pdf"
    doc.save(pdf)
    doc.close()
    e = schwaerze_pdf(pdf, [fund("Erika Musterfrau", "[PERSON A]"), fund("12.08.1964", "[GEB-DATUM]", "geburt")], ocr=dienst)
    assert e["treffer"] == 2 and e["reste"] == [], e
    assert any("Bilder" in h for h in e["hinweise"]), e["hinweise"]
    woerter, _ = dienst.woerter(e["ausgabe"], 0, clip=bildrect)
    texte = " ".join(w[4] for w in woerter)
    assert "Musterfrau" not in texte and "1964" not in texte, texte
    assert "PERSONALAUSWEIS" in texte
    assert "Zeile 11" in volltext(e["ausgabe"])


@braucht_ocr
def test_schluesselwort_ohne_fund_warnt(tmp_path, dienst):
    """M-50: OCR liest 'IBAN', aber kein IBAN-Fund (Prüfziffer verlesen) – Warnung je Seite."""
    zeilen = ["Versicherungsnehmer " + NAME, "IBAN DE83 3704 0044 0532 0130 00", "Kunden-Nr. 100245678"]
    pdf, _ = scan_pdf(tmp_path / "verleser.pdf", zeilen)
    e = schwaerze_pdf(pdf, [fund(NAME)], ocr=dienst)
    assert e["treffer"] == 1
    assert any("IBAN" in w and "Seite 1" in w for w in e["warnungen"]), e["warnungen"]
    assert any("Kunden" in w for w in e["warnungen"]), e["warnungen"]


# ----------------------------------------------------------------------
# M-07: Nebenkanäle
# ----------------------------------------------------------------------
def test_nebenkanaele_werden_entfernt(tmp_path):
    pdf = tmp_path / "kanaele.pdf"
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((50, 80), f"Versicherungsnehmer: {NAME}", fontsize=11, fontname="helv")
    seite.insert_text((50, 100), f"IBAN {IBAN}", fontsize=11, fontname="helv")
    seite.insert_text((50, 120), "E-Mail senden", fontsize=11, fontname="helv")
    seite.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(50, 108, 130, 124), "uri": "mailto:max.mustermann@example.de"})
    seite.add_freetext_annot(fitz.Rect(300, 60, 560, 90), f"Hinweis: {NAME}, Tel 0171 2345678", fontsize=9)
    seite.add_text_annot(fitz.Point(300, 100), f"Rückruf {NAME} wegen IBAN {IBAN}")
    st = seite.add_stamp_annot(fitz.Rect(300, 130, 450, 160), stamp=0)
    st.set_info(content=f"Bearbeitet für {NAME}", title="Sachbearbeiterin Krüger")
    st.update()
    doc.set_toc([[1, f"Versicherungsschein {NAME} LV-2024-887766", 1]])
    doc.embfile_add("rechnung.xml", f"<Rechnung><Name>{NAME}</Name><IBAN>{IBAN}</IBAN></Rechnung>".encode(),
                    filename="zugferd-invoice.xml", desc="ZUGFeRD")
    doc.set_metadata({"author": NAME, "title": f"Police {NAME}", "subject": f"IBAN {IBAN}", "keywords": "Mustermann"})
    doc.set_xml_metadata('<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
                         f'<dc:creator>{NAME}</dc:creator></x:xmpmeta><?xpacket end="w"?>')
    info_xref = int(doc.xref_get_key(-1, "Info")[1].split()[0])
    doc.xref_set_key(info_xref, "Kundenname", f"({NAME})")
    ocg = doc.add_ocg("Intern", on=False)
    seite.insert_text((50, 230), "Interner Vermerk: Kunde Geheimnis zahlt unregelmäßig", fontsize=11, fontname="helv", oc=ocg)
    # Miniaturbild der Seite als /Thumb
    pix = seite.get_pixmap(dpi=36)
    tmp = fitz.open()
    tp = tmp.new_page()
    tp.insert_image(tp.rect, pixmap=pix)
    doc.insert_pdf(tmp)
    thumb_xref = doc[-1].get_images()[0][0]
    doc.delete_page(-1)
    seite = doc[0]
    doc.xref_set_key(seite.xref, "Thumb", f"{thumb_xref} 0 R")
    # ActualText / Alt im Inhaltsstrom
    cs_xref = seite.get_contents()[0]
    strom = doc.xref_stream(cs_xref)
    strom = (b"/Span <</ActualText (Mustermann Max) >> BDC\n" + strom + b"\nEMC\n"
             b"/Figure <</Alt (Unterschrift von Max Mustermann) >> BDC q 1 0 0 1 50 300 cm 0 0 1 rg 0 0 m 100 20 l S Q EMC\n")
    doc.update_stream(cs_xref, strom)
    doc.save(pdf, garbage=0)
    doc.close()

    e = schwaerze_pdf(pdf, [fund(NAME), fund(IBAN, "[IBAN]", "iban"), fund("0171 2345678", "[TELEFON]", "telefon")])
    assert e["fehler"] is None and e["ausgabe"] is not None and e["reste"] == [], e
    aus = fitz.open(e["ausgabe"])
    s = aus[0]
    assert list(s.annots()) == [] and s.get_links() == [] and aus.get_toc() == []
    assert aus.embfile_count() == 0
    assert not any(aus.metadata.get(k) for k in ("author", "title", "subject", "keywords"))
    assert not aus.get_xml_metadata().strip()
    assert aus.xref_get_key(s.xref, "Thumb")[0] == "null"
    assert aus.get_ocgs() == {}
    text = s.get_text()
    aus.close()
    assert "Geheimnis" not in text and "unregelmäßig" not in text, "ausgeblendete Ebene muss entfernt sein"
    assert "Mustermann" not in text
    roh = qdf_rohbytes(e["ausgabe"])
    for nadel in ("Mustermann", "0532 0130", "Geheimnis", "mailto", "Unterschrift von", "zugferd", "Rückruf",
                  "Krüger", "Kundenname", "ActualText"):
        assert nadel not in roh, nadel
    assert any("Anmerkung" in h and "Lesezeichen" in h for h in e["hinweise"]), e["hinweise"]
    assert any("Ebene" in h for h in e["hinweise"])


def test_versicherungsschein_lesezeichen_und_metadaten(tmp_path):
    pdf = tmp_path / "a.pdf"
    shutil.copy(DATEN / "a_versicherungsschein.pdf", pdf)
    inventar = json.loads((DATEN / "a_versicherungsschein.inventar.json").read_text(encoding="utf-8"))
    posten = [p for p in inventar["pii"] if p["erwartung"] == "schwärzen"]
    funde = funde_aus_inventar(posten)
    e = schwaerze_pdf(pdf, funde)
    assert e["fehler"] is None and e["reste"] == [], e
    aus = fitz.open(e["ausgabe"])
    assert aus.get_toc() == [] and not aus.metadata.get("subject") and not aus.metadata.get("title")
    aus.close()
    roh = qdf_rohbytes(e["ausgabe"])
    assert "Mustermann" not in roh and "Bergisch Gladbach" not in roh and "LV-2024-887766" not in roh


# ----------------------------------------------------------------------
# M-25 / M-18: Ausgabedateien, Zuordnung, treffer == 0
# ----------------------------------------------------------------------
def test_neutrale_ausgabenamen_zuordnung_nie_ueberschreiben(tmp_path):
    pdf = textseite(tmp_path / "Mustermann_Max_Police_LV-2024-887766.pdf", [NAME, "Vertrag LV-2024-887766"])
    e1 = schwaerze_pdf(pdf, [fund(NAME)])
    assert e1["ausgabe"].name == "anonym_01.pdf"
    assert e1["ausgabe"].parent == tmp_path / "anonymisiert"
    pruef1 = md5(e1["ausgabe"])
    e2 = schwaerze_pdf(pdf, [fund("LV-2024-887766", "[VERTRAGS-NR]", "vertrag")])
    assert e2["ausgabe"].name == "anonym_02.pdf"
    assert md5(e1["ausgabe"]) == pruef1, "anonym_01.pdf darf nicht überschrieben werden"
    zuordnung = (tmp_path / "anonymisiert" / "_zuordnung.txt").read_text(encoding="utf-8").splitlines()
    assert len(zuordnung) == 2
    assert zuordnung[0].startswith("anonym_01.pdf  <-  Mustermann_Max_Police_LV-2024-887766.pdf  (")
    assert zuordnung[1].startswith("anonym_02.pdf  <-  ")
    # Lücke wird nicht wiederverwendet, Zielordner-Option greift
    e1["ausgabe"].unlink()
    ziel = tmp_path / "woanders"
    e3 = schwaerze_pdf(pdf, [fund(NAME)], ziel_ordner=ziel)
    assert e3["ausgabe"].parent == ziel and e3["ausgabe"].name == "anonym_01.pdf"
    e4 = schwaerze_pdf(pdf, [fund(NAME)])
    assert e4["ausgabe"].name == "anonym_03.pdf"
    assert not list((tmp_path / "anonymisiert").glob(".anonym_tmp_*")), "keine Hilfsdateien übrig"


def test_pruefen_suffix_bei_resten(tmp_path, monkeypatch):
    pdf = textseite(tmp_path / "rest.pdf", [NAME])
    monkeypatch.setattr(schwaerzung, "_selbstkontrolle", lambda lauf, ausgabe: ["Max"])
    e = schwaerze_pdf(pdf, [fund(NAME)])
    assert e["ausgabe"].name == "anonym_01_PRUEFEN.pdf"
    assert e["reste"] == ["Max"]
    assert any("PRUEFEN" in w for w in e["warnungen"])
    e2 = schwaerze_pdf(pdf, [fund(NAME)])
    assert e2["ausgabe"].name == "anonym_02_PRUEFEN.pdf", "Nummer der _PRUEFEN-Datei zählt mit"


def test_treffer_null_keine_ausgabe(tmp_path):
    pdf = textseite(tmp_path / "leer.pdf", ["Nur harmloser Text ohne Funde."])
    e = schwaerze_pdf(pdf, [fund("Mustermann"), fund("Musterfirma GmbH", "[BEGRIFF]", "begriff")])
    assert e["ausgabe"] is None and e["treffer"] == 0 and e["fehler"] is None
    assert WARNUNG_KEIN_TREFFER in e["warnungen"]
    assert e["uebersprungen"] == 2
    assert not (tmp_path / "anonymisiert").exists(), "kein leerer Ausgabeordner"
    e_leer = schwaerze_pdf(pdf, [])
    assert e_leer["ausgabe"] is None and WARNUNG_KEIN_TREFFER in e_leer["warnungen"]


def test_nicht_lokalisierte_funde_werden_gemeldet(tmp_path):
    pdf = textseite(tmp_path / "teils.pdf", [NAME, "Zweite Zeile"])
    e = schwaerze_pdf(pdf, [fund(NAME), fund("Erika Musterfrau", "[PERSON B]"), fund("Max")])
    assert e["treffer"] == 1 and e["ausgabe"] is not None
    assert e["uebersprungen"] == 1, "'Max' steckt im längeren Treffer und gilt als gefunden"
    assert any("Erika Musterfrau" in w and "nicht lokalisiert" in w for w in e["warnungen"]), e["warnungen"]


def test_abgeschnittener_fundtext_wird_mit_anfang_geschwaerzt(tmp_path):
    """Die Nummern-Erkennung schneidet lange Treffer nach 26 Zeichen ab ("KH-2025-004711 vom 12.03.2");
    als Ganzwort kommt das nirgends vor – der Anfang muss trotzdem verschwinden."""
    pdf = textseite(tmp_path / "abgeschnitten.pdf", ["Schaden-Nr. KH-2025-004711 vom 12.03.2025 gemeldet.",
                                                      "Antrags-Nr. A-2025-33917        Vermittler-Nr. 00412"])
    funde = [fund("KH-2025-004711 vom 12.03.2", "[VERTRAGS-NR]", "vertrag"),
             fund("A-2025-33917        Vermit", "[VERTRAGS-NR]", "vertrag")]
    e = schwaerze_pdf(pdf, funde)
    text = volltext(e["ausgabe"])
    assert e["treffer"] == 2 and e["uebersprungen"] == 0, e
    assert "KH-2025-004711" not in text and "A-2025-33917" not in text
    assert "12.03.2025 gemeldet" in text and "Vermittler-Nr. 00412" in text
    assert any("nur mit ihrem Anfang" in w for w in e["warnungen"]), e["warnungen"]
    assert e["reste"] == []


def test_passwortgeschuetzt_und_fehlende_datei(tmp_path):
    pdf = textseite(tmp_path / "pw.pdf", [NAME])
    doc = fitz.open(pdf)
    gesichert = tmp_path / "gesichert.pdf"
    doc.save(gesichert, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="geheim", owner_pw="geheim")
    doc.close()
    e = schwaerze_pdf(gesichert, [fund(NAME)])
    assert e["ausgabe"] is None and "Passwort" in e["fehler"]
    e2 = schwaerze_pdf(tmp_path / "gibt_es_nicht.pdf", [fund(NAME)])
    assert e2["ausgabe"] is None and e2["fehler"]


# ----------------------------------------------------------------------
# Fortschritt / Abbruch
# ----------------------------------------------------------------------
def test_fortschritt_je_seite_und_abbruch_ohne_halbe_ausgabe(tmp_path):
    pdf = textseite(tmp_path / "drei.pdf", [NAME, "Zeile"], seiten=3)
    schritte = []
    e = schwaerze_pdf(pdf, [fund(NAME)], fortschritt=lambda s, n: schritte.append((s, n)))
    assert schritte == [(1, 3), (2, 3), (3, 3)] and e["treffer"] == 3
    ereignis = threading.Event()
    schritte.clear()

    def fortschritt(s, n):
        schritte.append((s, n))
        if s == 2:
            ereignis.set()

    e2 = schwaerze_pdf(pdf, [fund(NAME)], fortschritt=fortschritt, abbruch=ereignis, ziel_ordner=tmp_path / "abbruch")
    assert e2["fehler"] == "Abgebrochen" and e2["ausgabe"] is None
    assert schritte == [(1, 3), (2, 3)]
    assert not (tmp_path / "abbruch").exists() or list((tmp_path / "abbruch").iterdir()) == []
    assert md5(pdf) == md5(pdf)


def test_original_bleibt_unveraendert(tmp_path):
    pdf = textseite(tmp_path / "orig.pdf", [NAME, "IBAN " + IBAN])
    vorher = md5(pdf)
    schwaerze_pdf(pdf, [fund(NAME), fund(IBAN, "[IBAN]", "iban")])
    assert md5(pdf) == vorher


# ----------------------------------------------------------------------
# M-31: Platzhalter
# ----------------------------------------------------------------------
def test_platzhalter_passt_auch_bei_kurzen_namen_und_kleiner_schrift(tmp_path):
    pdf = textseite(tmp_path / "klein.pdf", ["Sehr geehrte Frau Berg,", "Herr Wolf hat angerufen."], fontsize=8)
    e = schwaerze_pdf(pdf, [fund("Berg"), fund("Wolf", "[PERSON B]")])
    text = volltext(e["ausgabe"])
    assert "[PERSON A]" in text, text
    assert "[PERSON B]" in text or "[P B]" in text, text      # enge Lücke: Kurzform erlaubt
    if "[P B]" in text:
        assert any("[P B] = [PERSON B]" in h for h in e["hinweise"]), e["hinweise"]
    assert "Berg" not in text and "Wolf" not in text
    assert "Sehr geehrte Frau" in text and "hat angerufen" in text
    assert not any("ohne Platzhalter" in h for h in e["hinweise"]), e["hinweise"]


def test_platzhalter_nur_einmal_bei_mehrzeiligem_treffer(tmp_path):
    pdf = textseite(tmp_path / "zweizeilig.pdf", ["Versicherungsnehmer: Max", "Mustermann", "Vertragsbeginn 01.01.2020"])
    e = schwaerze_pdf(pdf, [fund("Max\nMustermann")])
    text = volltext(e["ausgabe"])
    assert e["treffer"] == 1
    assert text.count("[PERSON A]") == 1, text
    assert "Max" not in text and "Mustermann" not in text and "Vertragsbeginn 01.01.2020" in text


def test_platzhalter_laeuft_nicht_ins_folgewort(tmp_path):
    pdf = textseite(tmp_path / "folge.pdf", ["Frau Berg Versicherungsmakler GmbH"], fontsize=10)
    e = schwaerze_pdf(pdf, [fund("Berg")])
    text = volltext(e["ausgabe"])
    assert "Versicherungsmakler GmbH" in text and "Berg" not in text


# ----------------------------------------------------------------------
# M-33: Selbstkontrolle ohne Platzhalter-Fehlalarme
# ----------------------------------------------------------------------
def test_selbstkontrolle_ohne_fehlalarm_durch_platzhalter(tmp_path):
    zeilen = ["Die versicherte Person ist Thomas Bergmann aus Stuttgart.", "Vertragsnummer 4711 und Ing. Hofmann."]
    pdf = textseite(tmp_path / "m33.pdf", zeilen)
    funde = [fund("Person", "[PERSON A]"), fund("Thomas Bergmann", "[PERSON B]"), fund("Ing", "[PERSON C]"),
             fund("Vertrags", "[VERTRAGS-NR]", "vertrag")]
    e = schwaerze_pdf(pdf, funde)
    assert e["ausgabe"].name == "anonym_01.pdf" and e["reste"] == [], e
    text = volltext(e["ausgabe"])
    assert "[PERSON A]" in text and "[PERSON B]" in text
    assert "Vertragsnummer" in text, "'Vertrags' ist kein Ganzwort – bleibt stehen"
    assert "Ing" not in text.replace("[", "")


def test_selbstkontrolle_findet_echte_reste(tmp_path, monkeypatch):
    """Übersieht die Schwärzung einen Fund (hier künstlich erzwungen), findet ihn die Kontrolle,
    die Datei heißt _PRUEFEN und die Warnung nennt den Rest."""
    pdf = textseite(tmp_path / "rest.pdf", [NAME, "Erika Musterfrau"])
    original_kette = schwaerzung._Zeichenkette
    zustand = {"blind": True}

    class HalbBlind(original_kette):
        def suche(self, fund_text):
            if fund_text == "Erika Musterfrau" and zustand["blind"]:
                return []
            return super().suche(fund_text)

    orig_kontrolle = schwaerzung._selbstkontrolle

    def kontrolle(lauf, ausgabe):
        zustand["blind"] = False        # ab hier sieht die Kontrolle wieder alles
        return orig_kontrolle(lauf, ausgabe)

    monkeypatch.setattr(schwaerzung, "_Zeichenkette", HalbBlind)
    monkeypatch.setattr(schwaerzung, "_selbstkontrolle", kontrolle)
    e = schwaerze_pdf(pdf, [fund(NAME), fund("Erika Musterfrau", "[PERSON B]")])
    assert e["reste"] == ["Erika Musterfrau"], e
    assert e["ausgabe"].name.endswith("_PRUEFEN.pdf")
    assert any("Selbstkontrolle" in w and "Erika Musterfrau" in w for w in e["warnungen"])


# ----------------------------------------------------------------------
# M-35: Laufzeit
# ----------------------------------------------------------------------
def test_laufzeit_50_seiten_300_funde(tmp_path):
    pdf = tmp_path / "gross.pdf"
    doc = fitz.open()
    funde = []
    for p in range(50):
        seite = doc.new_page()
        y = 40
        for i in range(45):
            seite.insert_text((40, y), f"Kunde{p:02d}{i:02d} Nummer{p}{i} Vertrags-Nr. V{p:02d}{i:03d}X Tel 0171 {p:03d}{i:04d}",
                              fontsize=8, fontname="helv")
            y += 15
            if len(funde) < 300 and i % 8 == 0:
                funde.append(fund(f"Kunde{p:02d}{i:02d}", f"[PERSON {len(funde)}]"))
    doc.save(pdf)
    doc.close()
    assert len(funde) == 300
    start = time.perf_counter()
    e = schwaerze_pdf(pdf, funde)
    dauer = time.perf_counter() - start
    assert e["treffer"] == 300 and e["reste"] == [], e
    assert dauer < 5.0, f"Schwärzung dauerte {dauer:.1f} s"


# ----------------------------------------------------------------------
# M-52: Speicher – Zwischenstand bei vielen Scan-Seiten
# ----------------------------------------------------------------------
def test_zwischenspeichern_bei_vielen_scanseiten(tmp_path, monkeypatch):
    monkeypatch.setattr(schwaerzung, "STAPEL_SCANSEITEN", 2)
    zeilen = ["Versicherungsnehmer " + NAME, "IBAN " + IBAN]
    einzel, woerter = scan_pdf(tmp_path / "einzel.pdf", zeilen)
    doc = fitz.open()
    quelle = fitz.open(einzel)
    for _ in range(5):
        doc.insert_pdf(quelle)
    pdf = tmp_path / "fuenf.pdf"
    doc.save(pdf)
    doc.close()
    quelle.close()
    cache = {nr: woerter for nr in range(5)}
    e = schwaerze_pdf(pdf, [fund(NAME, ""), fund(IBAN, "", "iban")], ocr=FakeDienst(), ocr_cache=cache)
    assert e["treffer"] == 10 and e["fehler"] is None, e
    aus = fitz.open(e["ausgabe"])
    assert len(aus) == 5
    aus.close()
    name_rect = fitz.Rect(min(w[0] for w in woerter if w[4] in ("Max", "Mustermann")),
                          min(w[1] for w in woerter if w[4] in ("Max", "Mustermann")),
                          max(w[2] for w in woerter if w[4] in ("Max", "Mustermann")),
                          max(w[3] for w in woerter if w[4] in ("Max", "Mustermann")))
    for nr in range(5):
        assert bereich_hell(e["ausgabe"], nr, name_rect), f"Seite {nr + 1}"
    assert not list((tmp_path / "anonymisiert").glob(".anonym_tmp_*"))


# ----------------------------------------------------------------------
# M-66: Grafiken
# ----------------------------------------------------------------------
def test_hinweis_bei_vektorgrafik(tmp_path):
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((50, 80), f"Unterschrift: {NAME}", fontsize=11, fontname="helv")
    form = seite.new_shape()
    form.draw_bezier((60, 200), (90, 150), (120, 250), (160, 200))
    form.draw_bezier((160, 200), (190, 150), (220, 250), (260, 200))
    form.draw_bezier((260, 200), (290, 150), (320, 250), (360, 200))
    form.finish(color=(0, 0, 0), width=1.5)
    form.commit()
    pdf = tmp_path / "unterschrift.pdf"
    doc.save(pdf)
    doc.close()
    e = schwaerze_pdf(pdf, [fund(NAME)])
    assert any("Grafiken" in h and "Seite(n) 1" in h for h in e["hinweise"]), e["hinweise"]
    pdf2 = textseite(tmp_path / "ohne.pdf", [NAME])
    e2 = schwaerze_pdf(pdf2, [fund(NAME)])
    assert not any("Grafiken" in h for h in e2["hinweise"])


# ----------------------------------------------------------------------
# Kompatibilität
# ----------------------------------------------------------------------
def test_alte_namen_bleiben_importierbar():
    from anonymisierer.ocr import ist_scan_seite, ocr_textpage
    from anonymisierer import schwaerzung as modul
    assert callable(ist_scan_seite) and callable(ocr_textpage) and callable(modul.schwaerze_pdf)
