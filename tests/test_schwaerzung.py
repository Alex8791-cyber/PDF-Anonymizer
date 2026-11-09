"""Tests für anonymisierer/schwaerzung.py – jede Prüfung belegt einen Audit-Befund
(M-02, M-03, M-07, M-09, M-18, M-20, M-24, M-25, M-31, M-33, M-35, M-50, M-52, M-66)."""

import hashlib
import json
import re
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
    """Textebene, wie ein fremdes Werkzeug sie liest: pdftotext -layout (Poppler); ohne Poppler (z. B. auf dem
    Windows-Runner) PyMuPDF in Layout-Reihenfolge – der Test läuft dann trotzdem, statt übersprungen zu werden."""
    if PDFTOTEXT:
        aus = subprocess.run([PDFTOTEXT, "-layout", str(pfad), "-"], capture_output=True, text=True)
        if aus.returncode == 0 and aus.stdout is not None:
            return aus.stdout
    with fitz.open(pfad) as doc:
        return "\n".join(seite.get_text("text", sort=True) for seite in doc)


def volltext(pfad):
    doc = fitz.open(pfad)
    try:
        return "\n".join(seite.get_text() for seite in doc)
    finally:
        doc.close()


_HEX_STRING_RE = re.compile(r"<([0-9A-Fa-f\s]{4,})>")
_LITERAL_RE = re.compile(r"\((?:[^()\\]|\\.)*\)", re.S)
_ESCAPES = {"n": b"\n", "r": b"\r", "t": b"\t", "b": b"\b", "f": b"\f", "(": b"(", ")": b")", "\\": b"\\"}


def _literal_bytes(s: str) -> bytes:
    """PDF-Literalzeichenkette (ohne Klammern) mit Escapes (\\ddd, \\n …) -> Bytes."""
    aus, i = bytearray(), 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            j = i + 1
            while j < len(s) and j < i + 4 and s[j] in "01234567":
                j += 1
            if j > i + 1:
                aus.append(int(s[i + 1:j], 8) & 0xFF)
                i = j
                continue
            aus += _ESCAPES.get(s[i + 1], s[i + 1].encode("latin-1", "replace"))
            i += 2
            continue
        aus += s[i].encode("latin-1", "replace")
        i += 1
    return bytes(aus)


def _zeichenkette(b: bytes) -> str:
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be", "ignore")
    if b.startswith(b"\xff\xfe"):
        return b[2:].decode("utf-16-le", "ignore")
    return b.decode("latin-1")


def _rohtext_pymupdf(pfad) -> str:
    """Rückfall ohne qpdf: jedes Objekt als Quelltext, seine Zeichenketten dekodiert (PDFDocEncoding/UTF-16)
    und jeder Strom entpackt und in Latin-1, UTF-8 und UTF-16 gelesen (wie qpdf --qdf --decode-level=all)."""
    teile = []
    with fitz.open(pfad) as doc:
        for xref in range(1, doc.xref_length()):
            try:
                quelle = doc.xref_object(xref, compressed=False) or ""
            except Exception:
                quelle = ""
            try:
                strom = doc.xref_stream(xref) if doc.xref_is_stream(xref) else None
            except Exception:
                strom = None
            texte = [quelle] + ([strom.decode("latin-1")] if strom else [])
            for t in texte:                 # Objektquelle und entpackter Strom (z. B. "<4d6178> Tj")
                teile.append(t)
                for m in _HEX_STRING_RE.finditer(t):
                    try:
                        teile.append(_zeichenkette(bytes.fromhex("".join(m.group(1).split()))))
                    except ValueError:
                        pass
                for m in _LITERAL_RE.finditer(t):
                    teile.append(_zeichenkette(_literal_bytes(m.group(0)[1:-1])))
            if strom:
                teile += [strom.decode("utf-8", "ignore"), strom.decode("utf-16-be", "ignore"),
                          strom[1:].decode("utf-16-be", "ignore")]
        try:
            teile.append(doc.pdf_trailer())
        except Exception:
            pass
    return "\n".join(teile)


def qdf_rohbytes(pfad):
    """Alle Objekte dekomprimiert (qpdf --qdf) – findet Klartext auch in Strömen und Strukturen. Ohne qpdf
    (Windows-Runner) derselbe Blick über PyMuPDF."""
    if QPDF:
        ziel = Path(str(pfad) + ".qdf")
        subprocess.run([QPDF, "--qdf", "--object-streams=disable", "--decode-level=all", str(pfad), str(ziel)],
                       capture_output=True)
        if ziel.exists():
            roh = ziel.read_bytes()
            return roh.decode("latin-1") + roh.decode("utf-16-be", "ignore")
    return _rohtext_pymupdf(pfad)


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
    die Datei heißt _PRUEFEN und die Warnung nennt den Rest. Die Kontrolle benutzt denselben Vergleicher
    wie die Schwärzung – blind gemacht wird er nur bis zum Beginn der Kontrolle."""
    pdf = textseite(tmp_path / "rest.pdf", [NAME, "Erika Musterfrau"])
    echt = schwaerzung.ganzwort_stellen
    zustand = {"blind": True}

    def halb_blind(seite, fundtext, modus="name"):
        if fundtext == "Erika Musterfrau" and zustand["blind"]:
            return []
        return echt(seite, fundtext, modus)

    orig_kontrolle = schwaerzung._selbstkontrolle

    def kontrolle(lauf, ausgabe):
        zustand["blind"] = False        # ab hier sieht die Kontrolle wieder alles
        return orig_kontrolle(lauf, ausgabe)

    monkeypatch.setattr(schwaerzung, "ganzwort_stellen", halb_blind)
    monkeypatch.setattr(schwaerzung, "_selbstkontrolle", kontrolle)
    e = schwaerze_pdf(pdf, [fund(NAME), fund("Erika Musterfrau", "[PERSON B]")])
    assert e["reste"] == ["Erika Musterfrau"], e
    assert e["ausgabe"].name.endswith("_PRUEFEN.pdf") and e["status"] == "pruefen"
    assert any("Selbstkontrolle" in w and "Erika Musterfrau" in w for w in e["warnungen"])
    assert "RESTE" in {m["code"] for m in e["meldungen"]}


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
    # Gutachten KQ-09: keine knappe Wanduhr-Schranke (CI-Runner unter Last) – 20 s fangen jede
    # Rückkehr zum alten quadratischen Verhalten (Audit: 8 Minuten) zuverlässig ab
    assert dauer < 20.0, f"Schwärzung dauerte {dauer:.1f} s"


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


# ----------------------------------------------------------------------
# Phase 2: Stellen, Modell, Status, Meldungen
# ----------------------------------------------------------------------
from anonymisierer import seitenmodell as sm  # noqa: E402
from anonymisierer.analyse import analysiere_pdf  # noqa: E402
from anonymisierer.muster import KATEGORIEN  # noqa: E402

OHNE_NAMEN = {k for k, _, _, _, an in KATEGORIEN if an} - {"namen"}
DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _analysiert(pdf, aktive=OHNE_NAMEN, immer=()):
    e = analysiere_pdf(pdf, aktive, [], list(immer), ocr=FakeDienst())
    assert e["fehler"] is None, e
    return e


def test_stellen_der_analyse_werden_geschwaerzt(tmp_path):
    pdf = textseite(tmp_path / "s.pdf", [f"Versicherungsnehmer {NAME}", f"IBAN {IBAN}", "Tel. 0911 123456",
                                         "Herr MAX MUSTERMANN unterschreibt."])
    a = _analysiert(pdf, immer=[NAME])
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=FakeDienst(), ocr_cache=a["ocr_cache"])
    assert e["fehler"] is None and e["status"] == "fertig" and e["ausgabe_pruefen"] is False
    assert e["stellen_nicht_lokalisiert"] == 0 and e["reste"] == [] and e["verdacht"] == []
    assert e["stellen_geschwaerzt"] == e["treffer"] == sum(f["anzahl"] for f in a["funde"])
    text = volltext(e["ausgabe"])
    for weg in ("Mustermann", "MUSTERMANN", "3704", "123456"):
        assert weg not in text, weg
    codes = {m["code"] for m in e["meldungen"]}
    assert {"NEBENKANAL_ENTFERNT", "ZUORDNUNG"} <= codes and "MODELL_ABWEICHUNG" not in codes


def test_abgewaehlte_stelle_bleibt_und_ist_kein_rest(tmp_path):
    pdf = textseite(tmp_path / "ab.pdf", [f"Vertrag von {NAME}", "Vermittler-Nr. 4711 4711", f"Kunde {NAME} zahlt."])
    a = _analysiert(pdf, immer=[NAME])
    funde = [dict(f, stellen=[dict(st) for st in f["stellen"]]) for f in a["funde"]]
    name = next(f for f in funde if f["text"] == NAME)
    assert len(name["stellen"]) == 2
    name["stellen"][1]["an"] = False
    e = schwaerze_pdf(pdf, funde, modell=a["modell"], ocr=FakeDienst())
    assert e["reste"] == [] and e["status"] == "fertig", e
    text = volltext(e["ausgabe"])
    assert "Vertrag von [BEGRIFF]" in text.replace("\n", " ") or "[BEGRIFF]" in text
    assert text.count(NAME) == 1 and f"Kunde {NAME} zahlt." in text


def test_modell_abweichung_wird_gemeldet_und_neu_gesucht(tmp_path):
    pdf_a = textseite(tmp_path / "a.pdf", [f"Vertrag von {NAME}", "Zeile zwei"])
    pdf_b = textseite(tmp_path / "b.pdf", ["Eine ganz andere erste Zeile", f"Vertrag von {NAME}"])
    a = _analysiert(pdf_a, immer=[NAME])
    e = schwaerze_pdf(pdf_b, a["funde"], modell=a["modell"], ocr=FakeDienst())
    assert NAME not in volltext(e["ausgabe"]), "Stelle wurde auf der Seite neu gesucht"
    assert e["status"] == "pruefen" and e["ausgabe"].name.endswith("_PRUEFEN.pdf")
    assert "MODELL_ABWEICHUNG" in {m["code"] for m in e["meldungen"]}


def test_nicht_lokalisierbare_stelle_macht_pruefen(tmp_path):
    pdf = textseite(tmp_path / "nl.pdf", [f"Vertrag von {NAME}", "IBAN " + IBAN])
    a = _analysiert(pdf, immer=[NAME])
    funde = [dict(f) for f in a["funde"]]
    funde.append({"kategorie": "namen", "anzeige": "Name", "text": "Erika Musterfrau", "ersatz": "[PERSON B]",
                  "stellen": [{"seite": 0, "start": 0, "ende": 16, "an": True, "text": "Erika Musterfrau"}]})
    e = schwaerze_pdf(pdf, funde, modell=a["modell"], ocr=FakeDienst())
    assert e["stellen_nicht_lokalisiert"] == 1 and e["status"] == "pruefen"
    assert any(m["code"] == "NICHT_LOKALISIERT" and m["art"] == "fehler" for m in e["meldungen"])
    assert NAME not in volltext(e["ausgabe"])


def test_freigabe_erforderlich_freigeben_und_verwerfen(tmp_path):
    pdf = textseite(tmp_path / "f.pdf", [NAME])
    e = schwaerze_pdf(pdf, [fund(NAME)], freigabe_erforderlich=True, ocr=FakeDienst())
    assert e["ausgabe"].name == "anonym_01_PRUEFEN.pdf" and e["status"] == "pruefen" and e["reste"] == []
    ziel = e["ausgabe"].parent
    neu = schwaerzung.freigeben(e["ausgabe"])
    assert neu.name == "anonym_01.pdf" and neu.exists() and not e["ausgabe"].exists()
    zeilen = (ziel / "_zuordnung.txt").read_text(encoding="utf-8").splitlines()
    assert len(zeilen) == 1 and zeilen[0].startswith("anonym_01.pdf  <-  f.pdf")
    e2 = schwaerze_pdf(pdf, [fund(NAME)], freigabe_erforderlich=True, ocr=FakeDienst())
    assert e2["ausgabe"].name == "anonym_02_PRUEFEN.pdf"
    schwaerzung.verwerfen(e2["ausgabe"])
    assert not e2["ausgabe"].exists()
    assert [z.split()[0] for z in (ziel / "_zuordnung.txt").read_text(encoding="utf-8").splitlines()] == ["anonym_01.pdf"]


def test_ausgabename_wird_exklusiv_reserviert(tmp_path, monkeypatch):
    """Gutachten S-13/KQ-13: Legt ein zweiter Lauf zwischen Namenswahl und Ablage anonym_01.pdf an, wird
    dessen Datei nicht überschrieben – die Ausgabe bekommt die nächste Nummer."""
    pdf = textseite(tmp_path / "r.pdf", [NAME])
    ziel = tmp_path / "anonymisiert"
    orig = schwaerzung._selbstkontrolle

    def fremder_lauf(lauf, ausgabe):
        (ziel / "anonym_01.pdf").write_bytes(b"%PDF-1.4 fremde Ausgabe")
        return orig(lauf, ausgabe)
    monkeypatch.setattr(schwaerzung, "_selbstkontrolle", fremder_lauf)
    e = schwaerze_pdf(pdf, [fund(NAME)], ocr=FakeDienst())
    assert e["ausgabe"].name == "anonym_02.pdf"
    assert (ziel / "anonym_01.pdf").read_bytes() == b"%PDF-1.4 fremde Ausgabe"
    # Protokoll: _PRUEFEN-Datei belegt ihre Nummer, die Platzhalterdatei verschwindet wieder
    (ziel / "anonym_03_PRUEFEN.pdf").write_bytes(b"x")
    assert schwaerzung._nummer_reservieren(ziel, pruefen=True, nummer=3).name == "anonym_04_PRUEFEN.pdf"
    assert not (ziel / "anonym_04.pdf").exists() and not (ziel / "anonym_03.pdf").exists()


def test_teilrest_wird_erkannt(tmp_path, monkeypatch):
    """Gutachten S-07: bleibt ein Wortrest stehen (Rechteck künstlich halbiert), meldet die Glyphenrest-
    Prüfung ihn als Rest -> _PRUEFEN."""
    pdf = textseite(tmp_path / "teil.pdf", ["Herr Mustermann wohnt hier."])
    echt = sm.Seite.rechtecke

    def halbiert(self, start, ende):
        aus = []
        for r, box, groesse, grundlinie in echt(self, start, ende):
            r = fitz.Rect(r.x0, r.y0, r.x0 + r.width / 2, r.y1)
            aus.append((r, box, groesse, grundlinie))
        return aus
    monkeypatch.setattr(sm.Seite, "rechtecke", halbiert)
    e = schwaerze_pdf(pdf, [fund("Mustermann")], ocr=FakeDienst())
    assert e["status"] == "pruefen" and any("nicht entfernt" in r for r in e["reste"]), e["reste"]


@pytest.mark.skipif(not DEJAVU.exists(), reason="DejaVuSans fehlt")
def test_ligaturen_werden_geschwaerzt(tmp_path):
    """Gutachten S-03: 'Steﬃ Hoﬀmann' (Ligaturglyphen) – Fund aus der Analyse wird vollständig entfernt."""
    pdf = textseite(tmp_path / "lig.pdf", ["Versicherungsnehmerin: Frau Steﬃ Hoﬀmann", "Herr Pfeiﬀer"],
                    fontname="F0", fontfile=str(DEJAVU))
    a = _analysiert(pdf, immer=["Steffi Hoffmann", "Pfeiffer"])
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=FakeDienst())
    assert e["reste"] == [] and e["stellen_nicht_lokalisiert"] == 0
    text = volltext(e["ausgabe"])
    for weg in ("Steﬃ", "Hoﬀmann", "Steffi", "Hoffmann", "Pfeiﬀer", "Pfeiffer"):
        assert weg not in text, weg


def test_kammfeld_und_formularfeld_werden_geschwaerzt(tmp_path):
    """Gutachten S-12 und S-02: Kammfeld-Geburtsdatum und Feldwert neben dem Etikett verschwinden."""
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((50, 100), "Geburtsdatum:", fontsize=10)
    seite.insert_text((50, 140), "IBAN:", fontsize=10)
    for name, wert, rect, kamm in (("geb", "30071988", fitz.Rect(150, 88, 300, 106), True),
                                   ("iban", IBAN, fitz.Rect(150, 128, 400, 146), False)):
        w = fitz.Widget()
        w.field_name, w.field_type, w.rect, w.field_value = name, fitz.PDF_WIDGET_TYPE_TEXT, rect, wert
        if kamm:
            w.field_flags, w.text_maxlen = fitz.PDF_TX_FIELD_IS_COMB, 8
        seite.add_widget(w)
    pdf = tmp_path / "kamm.pdf"
    doc.save(pdf)
    doc.close()
    a = _analysiert(pdf)
    assert {f["kategorie"] for f in a["funde"]} >= {"geburt", "iban"}
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=FakeDienst())
    assert e["reste"] == [] and e["status"] == "fertig"
    text = volltext(e["ausgabe"]).replace(" ", "").replace("\n", "")
    assert "30071988" not in text and "3704" not in text


def test_formular_d03_geburtsdatum(tmp_path):
    """E2E d-03: Geburtsdatum im Formularfeld neben 'Geburtsdatum:' – Analyse findet, Schwärzung entfernt."""
    pdf = tmp_path / "d.pdf"
    shutil.copy(DATEN / "d_antrag_formular.pdf", pdf)
    a = _analysiert(pdf)
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=FakeDienst())
    assert e["reste"] == [] and e["stellen_nicht_lokalisiert"] == 0
    assert "30.07.1988" not in pdftotext(e["ausgabe"]) and "30.07.1988" not in qdf_rohbytes(e["ausgabe"])


def test_versal_eszett_und_alle_schreibweisen(tmp_path):
    """Gutachten S-16/KQ-01: 'Groß' trifft auch 'GROẞ' und 'GROSS'; Versalien und Normalschrift beide weg."""
    pdf = textseite(tmp_path / "gross.pdf", ["Frau GROẞ und Herr GROSS", "Sehr geehrte Frau Groß,",
                                             "der Großteil bleibt, groß auch."], fontname="F0",
                    fontfile=str(DEJAVU) if DEJAVU.exists() else None)
    e = schwaerze_pdf(pdf, [fund("Groß")], ocr=FakeDienst())
    text = volltext(e["ausgabe"])
    assert "GROẞ" not in text and "GROSS" not in text and "Frau Groß" not in text
    assert "Großteil" in text and "groß auch" in text and e["reste"] == []


def test_manuelle_bereiche_und_stellen(tmp_path):
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((50, 80), "Unterschrift: Max Mustermann", fontsize=11, fontname="helv")
    seite.insert_text((50, 110), "Bemerkung: Kunde zahlt pünktlich", fontsize=11, fontname="helv")
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 30), False)
    pix.clear_with(0)
    seite.insert_image(fitz.Rect(300, 300, 420, 360), pixmap=pix)
    pdf = tmp_path / "manuell.pdf"
    doc.save(pdf)
    doc.close()
    a = _analysiert(pdf)
    m = a["modell"].seiten[0]
    s = m.text.index("pünktlich")
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=FakeDienst(),
                      manuelle_bereiche={0: [fitz.Rect(48, 66, 250, 84), fitz.Rect(290, 290, 430, 370)]},
                      manuelle_stellen={0: [(s, s + len("pünktlich"), "[BEMERKUNG]")]})
    text = volltext(e["ausgabe"])
    assert "Mustermann" not in text and "Unterschrift" not in text and "pünktlich" not in text
    assert "[GESCHWÄRZT]" in text and "[BEMERKUNG]" in text and "Bemerkung: Kunde zahlt" in text
    assert bereich_hell(e["ausgabe"], 0, fitz.Rect(305, 302, 415, 325)), "Bildpixel im Bereich gelöscht"
    assert not bereich_hell(pdf, 0, fitz.Rect(305, 302, 415, 325)), "im Original ist das Bild dunkel"


def test_kontroll_ocr_benutzt_winkel_aus_dem_modell(tmp_path):
    """Gutachten S-08: Kontroll-OCR der Ausgabe mit derselben Ausrichtung wie die Analyse (Cache-Fall)."""
    zeilen = ["Versicherungsnehmer " + NAME, "IBAN " + IBAN]
    pdf, woerter = scan_pdf(tmp_path / "winkel.pdf", zeilen)
    aufrufe = []

    class Dienst(FakeDienst):
        def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, winkel=None, **_):
            aufrufe.append((Path(pdf_pfad).name, winkel))
            return list(woerter), None
    a = analysiere_pdf(pdf, OHNE_NAMEN, [], [NAME], ocr=Dienst())
    a["modell"].seiten[0].ocr_winkel = 180
    aufrufe.clear()
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=Dienst(), ocr_cache=a["ocr_cache"])
    assert e["fehler"] is None and e["reste"] == [], e
    assert aufrufe and all(name != "winkel.pdf" for name, _ in aufrufe), "Original nicht erneut gelesen"
    assert all(w == 180 for name, w in aufrufe), aufrufe


def test_selbstkontrolle_liest_keine_bilder(tmp_path, monkeypatch):
    """Gutachten PERF-06: kein rawdict MIT Bildern (Scanbild würde neu kodiert)."""
    zeilen = ["Versicherungsnehmer " + NAME, "IBAN " + IBAN]
    pdf, woerter = scan_pdf(tmp_path / "perf06.pdf", zeilen)
    flags = []
    echt = fitz.Page.get_text

    def beobachten(self, option="text", *args, **kwargs):
        if option in ("rawdict", "dict"):
            flags.append(kwargs.get("flags"))
        return echt(self, option, *args, **kwargs)
    monkeypatch.setattr(fitz.Page, "get_text", beobachten)
    e = schwaerze_pdf(pdf, [fund(NAME, ""), fund(IBAN, "", "iban")], ocr=FakeDienst({0: woerter}),
                      ocr_cache={0: woerter})
    assert e["treffer"] == 2
    assert flags and all(f is not None and not f & fitz.TEXT_PRESERVE_IMAGES for f in flags), flags


def test_text_ausserhalb_der_cropbox_wird_entfernt(tmp_path):
    """Gutachten S-05: Inhalt im weggeschnittenen Rand (nur CropBox gesetzt) verschwindet aus der Ausgabe."""
    doc = fitz.open()
    s = doc.new_page()
    s.insert_text((50, 80), f"Versicherungsnehmer {NAME}", fontsize=11)
    s.insert_text((50, 800), "Unten: Erika Musterfrau, IBAN " + IBAN, fontsize=11)
    s.set_cropbox(fitz.Rect(0, 0, 595, 700))
    pdf = tmp_path / "crop.pdf"
    doc.save(pdf)
    doc.close()
    e = schwaerze_pdf(pdf, [fund(NAME)], ocr=FakeDienst())
    assert "Musterfrau" not in pdftotext(e["ausgabe"]) and "Musterfrau" not in qdf_rohbytes(e["ausgabe"])


def test_fremdmodule_nebenkanaele_und_bilder_werden_genutzt(tmp_path, monkeypatch):
    """Vertrag 12.4: nebenkanaele.nebenkanaele_entfernen und bilder.bilder_neu_kodieren werden aufgerufen,
    wenn es sie gibt."""
    aufrufe = {}

    class Neben:
        @staticmethod
        def nebenkanaele_entfernen(doc):
            aufrufe["neben"] = True
            return {"anmerkungen": 0}

        @staticmethod
        def nebenkanal_hinweis(zaehler):
            return "Nebenkanäle bereinigt (Modul)."

    class Bilder:
        @staticmethod
        def bilder_neu_kodieren(doc, xrefs, qualitaet=85):
            aufrufe["bilder"] = set(xrefs)
            return len(xrefs)
    monkeypatch.setattr(schwaerzung, "_nebenkanaele", Neben)
    monkeypatch.setattr(schwaerzung, "_bilder", Bilder)
    zeilen = ["Versicherungsnehmer " + NAME]
    pdf, woerter = scan_pdf(tmp_path / "module.pdf", zeilen)
    e = schwaerze_pdf(pdf, [fund(NAME)], ocr=FakeDienst({0: woerter}), ocr_cache={0: woerter})
    assert aufrufe.get("neben") and aufrufe.get("bilder"), aufrufe
    assert "Nebenkanäle bereinigt (Modul)." in e["hinweise"]


def test_beschnitt_wird_entfernt_wenn_nebenkanal_modul_scheitert(tmp_path, monkeypatch):
    """Die Seitenschleife überlässt Inhalte außerhalb der CropBox dem Nebenkanal-Modul; scheitert es,
    werden sie trotzdem entfernt (S-05) und die Warnung steht in den Meldungen."""
    class Kaputt:
        @staticmethod
        def nebenkanaele_entfernen(doc, zaehler=None):
            raise RuntimeError("defekt")
    monkeypatch.setattr(schwaerzung, "_nebenkanaele", Kaputt)
    doc = fitz.open()
    s = doc.new_page()
    s.insert_text((50, 80), f"Versicherungsnehmer {NAME}", fontsize=11)
    s.insert_text((50, 800), "Unten: Erika Musterfrau, IBAN " + IBAN, fontsize=11)
    s.set_cropbox(fitz.Rect(0, 0, 595, 700))
    pdf = tmp_path / "crop_kaputt.pdf"
    doc.save(pdf)
    doc.close()
    e = schwaerze_pdf(pdf, [fund(NAME)], ocr=FakeDienst())
    assert "Musterfrau" not in pdftotext(e["ausgabe"]) and "Musterfrau" not in qdf_rohbytes(e["ausgabe"])
    assert any(m["code"] == "NEBENKANAL_ENTFERNT" and m["art"] == "warnung" and "defekt" in m["text"]
               for m in e["meldungen"])


def test_pruefhelfer_ohne_poppler_und_qpdf(tmp_path, monkeypatch):
    """Windows-Runner ohne pdftotext/qpdf: die Prüf-Helfer fallen auf PyMuPDF zurück und finden Klartext
    in Textebene, Metadaten (UTF-16) und komprimierten Strömen – Leck-Prüfungen bleiben also scharf."""
    import sys
    modul = sys.modules[__name__]
    monkeypatch.setattr(modul, "PDFTOTEXT", None)
    monkeypatch.setattr(modul, "QPDF", None)
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((50, 80), "Versicherungsnehmerin Erika Musterfrau", fontsize=11)
    doc.set_metadata({"author": "Jürgen Ölmann"})
    pdf = tmp_path / "helfer.pdf"
    doc.save(pdf, deflate=True)
    doc.close()
    assert "Musterfrau" in pdftotext(pdf)
    roh = qdf_rohbytes(pdf)
    assert "Musterfrau" in roh and "Ölmann" in roh
