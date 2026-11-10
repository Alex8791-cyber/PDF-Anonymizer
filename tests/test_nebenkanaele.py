"""Tests für anonymisierer/nebenkanaele.py: alles, was personenbezogene Daten außerhalb des sichtbaren
Seitentexts trägt, muss nach nebenkanaele_entfernen() verschwunden sein – geprüft über die Textextraktion
(PyMuPDF, pdftotext) UND über eine Rohsuche in allen dekodierten Objekten (qpdf --qdf, falls vorhanden,
sonst PyMuPDF). Gutachten S-05 (Beschnitt), S-06 (ActualText), S-11 (Bild-EXIF), S-14 (PageLabels)."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

import pymupdf as fitz

from anonymisierer import nebenkanaele as nk
from anonymisierer.nebenkanaele import (markierungen_aus_strom, markierungen_entfernen, nebenkanaele_entfernen,
                                        nebenkanaele_zaehlen, nebenkanal_hinweis)

GEHEIM = "Mustermann"
QPDF = shutil.which("qpdf")
PDFTOTEXT = shutil.which("pdftotext")


# ----------------------------------------------------------------------
# Prüfwerkzeuge
# ----------------------------------------------------------------------
_STRING = re.compile(rb"\((?:[^()\\]|\\.)*\)|<[0-9A-Fa-f\s]+>")


def _zeichenketten_dekodieren(roh: bytes) -> str:
    """Literal- und Hex-Strings (auch UTF-16BE) eines PDF-Quelltexts als Klartext."""
    teile = []
    for m in _STRING.finditer(roh):
        s = m.group(0)
        if s.startswith(b"<"):
            try:
                daten = bytes.fromhex(re.sub(rb"\s", b"", s[1:-1]).decode())
            except ValueError:
                continue
        else:
            daten = re.sub(rb"\\(.)", rb"\1", s[1:-1])
        if daten.startswith(b"\xfe\xff"):
            teile.append(daten[2:].decode("utf-16-be", "replace"))
        else:
            teile.append(daten.decode("latin-1"))
    return "\n".join(teile)


def roh_text(pfad) -> str:
    """Alles, was ein Parser in der Datei findet: qpdf-Dump mit dekodierten Strömen (außer JPEG) bzw.
    PyMuPDF-Dump aller Objekte und Ströme, dazu alle Zeichenketten dekodiert (UTF-16, Hex)."""
    teile = []
    if QPDF:
        r = subprocess.run([QPDF, "--qdf", "--object-streams=disable", "--decode-level=generalized",
                            str(pfad), "-"], capture_output=True)
        teile.append(r.stdout)
    doc = fitz.open(pfad)
    try:
        for xref in range(1, doc.xref_length()):
            try:
                teile.append(doc.xref_object(xref, compressed=False).encode("latin-1", "replace"))
                if doc.xref_is_stream(xref):
                    try:
                        teile.append(doc.xref_stream(xref) or b"")
                    except Exception:
                        teile.append(doc.xref_stream_raw(xref) or b"")
            except Exception:
                continue
        teile.append(doc.pdf_trailer(compressed=False).encode("latin-1", "replace"))
    finally:
        doc.close()
    roh = b"\n".join(teile)
    return roh.decode("latin-1") + "\n" + _zeichenketten_dekodieren(roh)


def pdftotext(pfad, cropbox=False) -> str:
    """Text, wie ein fremdes Werkzeug ihn liest. Ausgabe ausdrücklich als UTF-8 und tolerant dekodiert: unter
    Windows liegt ggf. ein xpdf-pdftotext im Pfad, das sonst Latin-1 schreibt (mit text=True lieferte
    subprocess dann None) und -cropbox nicht kennt (dann zählt der Lauf ohne den Schalter)."""
    if not PDFTOTEXT:
        return ""
    args = [PDFTOTEXT, "-enc", "UTF-8"] + (["-cropbox"] if cropbox else []) + ["-layout", str(pfad), "-"]
    aus = subprocess.run(args, capture_output=True)
    if aus.returncode != 0 and cropbox:
        return pdftotext(pfad)
    return (aus.stdout or b"").decode("utf-8", errors="replace")


def seitentext(pfad) -> str:
    doc = fitz.open(pfad)
    try:
        return "\n".join(s.get_text() for s in doc)
    finally:
        doc.close()


def pruefen_sauber(pfad, geheimnisse, sichtbar=()):
    """Kein Geheimnis in Textextraktion, pdftotext oder Rohsuche; sichtbarer Text unverändert lesbar."""
    roh = roh_text(pfad)
    text = seitentext(pfad)
    p_text = pdftotext(pfad) + pdftotext(pfad, cropbox=True)
    for g in geheimnisse:
        assert g not in text, f"{g!r} in get_text"
        assert g not in p_text, f"{g!r} in pdftotext"
        assert g not in roh, f"{g!r} in Rohdaten: …{roh[max(0, roh.find(g) - 80):roh.find(g) + 40]!r}…"
    for s in sichtbar:
        assert s in text, f"sichtbarer Text {s!r} fehlt"
    if QPDF:
        r = subprocess.run([QPDF, "--check", str(pfad)], capture_output=True, text=True)
        assert r.returncode in (0, 3), r.stdout + r.stderr       # 3 = nur Warnungen


def speichern(doc, pfad):
    doc.save(pfad, garbage=4, deflate=True)
    doc.close()
    return Path(pfad)


def jpeg_mit_metadaten(text="Max Mustermann") -> bytes:
    """JPEG (PyMuPDF) mit EXIF-, XMP-, IPTC-, ICC-, Kommentar-Segment und angehängten Daten nach dem Bildende."""
    doc = fitz.open()
    s = doc.new_page(width=200, height=120)
    s.draw_rect(s.rect, fill=(0.8, 0.6, 0.4))
    s.insert_text((20, 60), "Foto", fontsize=20)
    jpeg = s.get_pixmap(dpi=72).tobytes("jpeg", jpg_quality=80)
    doc.close()
    t = text.encode()

    def segment(marker, nutzdaten):
        return bytes([0xFF, marker]) + (len(nutzdaten) + 2).to_bytes(2, "big") + nutzdaten

    zusatz = (segment(0xE1, b"Exif\x00\x00II*\x00" + b"\x00" * 8 + b"Artist " + t + b" GPS 50.93N 6.95E")
              + segment(0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta>" + t + b"</x:xmpmeta>")
              + segment(0xED, b"Photoshop 3.0\x008BIM\x04\x04" + t)
              + segment(0xE2, b"ICC_PROFILE\x00\x01\x01" + b"desc " + t)
              + segment(0xFE, b"Kommentar " + t))
    # nach SOI und JFIF-APP0 einfügen
    app0_ende = 2 + 2 + int.from_bytes(jpeg[4:6], "big")
    return jpeg[:app0_ende] + zusatz + jpeg[app0_ende:] + b"MotionPhoto " + t + b" Vorschaubild"


# ----------------------------------------------------------------------
# Alles auf einmal
# ----------------------------------------------------------------------
def pdf_mit_nebenkanaelen(pfad) -> Path:
    doc = fitz.open()
    doc.new_page()
    doc.new_page()                    # neue Seiten machen ältere Page-Objekte ungültig: danach neu holen
    seite, seite2 = doc[0], doc[1]
    seite.insert_text((72, 100), "Sichtbar: Vertrag Nr. 4711 ohne Namen", fontsize=11)
    seite2.insert_text((72, 100), "Zweite Seite", fontsize=11)
    # Anmerkungen aller Art, Link mit Klartext in der URL
    a = seite.add_text_annot((400, 100), "Notiz: Max Mustermann zurückrufen")
    a.set_info(title="Erika Musterfrau Sachbearbeiterin")
    a.update()
    hl = seite.add_highlight_annot(fitz.Rect(72, 90, 200, 102))
    hl.set_info(content="Kommentar Mustermann IBAN DE89", title="Autor Mustermann")
    hl.update()
    seite.add_freetext_annot(fitz.Rect(72, 400, 350, 430), "Freitext Mustermann", fontsize=10)
    seite.add_file_annot((450, 500), b"Anhang-Inhalt Mustermann geheim", "notiz_mustermann.txt")
    seite.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 200, 200, 212),
                       "uri": "https://portal.example/kunde?name=Max.Mustermann"})
    # Lesezeichen, Anhänge, Metadaten, Seitenbeschriftungen
    doc.set_toc([[1, "Vertrag Max Mustermann", 1], [2, "Anlage Mustermann", 2]])
    doc.embfile_add("kunde.xml", b"<kunde>Max Mustermann LV-2024-887766</kunde>", filename="kunde_mustermann.xml",
                    desc="Daten Mustermann")
    doc.set_metadata({"author": "Max Mustermann", "title": "Police LV-2024-887766 Mustermann",
                      "subject": "Kunde Jürgen Müller-Mustermann", "keywords": "Mustermann", "creator": "Mustermann",
                      "producer": "Mustermann PDF"})
    doc.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'><dc:creator>Max Mustermann</dc:creator></x:xmpmeta>")
    doc.set_page_labels([{"startpage": 0, "prefix": "Police Mustermann LV-2024-887766 S.", "style": "D"}])
    kat = doc.pdf_catalog()
    seite, seite2 = doc[0], doc[1]
    # JavaScript und Aktionen
    doc.xref_set_key(kat, "OpenAction", "<< /S /JavaScript /JS (app.alert\\('Max Mustermann'\\);) >>")
    doc.xref_set_key(seite.xref, "AA", "<< /O << /S /JavaScript /JS (var x='Mustermann Seite';) >> >>")
    js = doc.get_new_xref()
    doc.update_object(js, "<< /S /JavaScript /JS (var kunde = 'Max Mustermann 02.09.1983';) >>")
    doc.xref_set_key(kat, "Names/JavaScript", f"<< /Names [ (init) {js} 0 R ] >>")
    # PieceInfo, Strukturbaum mit Ersatztexten, Ebene mit Namen
    doc.xref_set_key(kat, "PieceInfo", "<< /Plugin << /Private (Mustermann privat) >> >>")
    doc.xref_set_key(seite.xref, "PieceInfo", "<< /Plugin << /Private (Seite Mustermann) >> >>")
    elem = doc.get_new_xref()
    wurzel = doc.get_new_xref()
    doc.update_object(wurzel, f"<< /Type /StructTreeRoot /K {elem} 0 R >>")
    doc.update_object(elem, f"<< /Type /StructElem /S /Figure /P {wurzel} 0 R /K 0 /Pg {seite.xref} 0 R "
                            f"/Alt (Foto von Max Mustermann) /ActualText (Mustermann Ersatz) /T (Titel Mustermann) "
                            f"/E (Abk Mustermann) >>")
    doc.xref_set_key(kat, "StructTreeRoot", f"{wurzel} 0 R")
    doc.xref_set_key(kat, "MarkInfo", "<< /Marked true >>")
    ocg = doc.add_ocg("Notizen Max Mustermann", on=True)
    seite, seite2 = doc[0], doc[1]
    seite2.insert_text((72, 300), "Text auf einer Ebene", fontsize=11, oc=ocg)
    # Miniaturbild, Seiten-XMP, eingebetteter Anhang über /AF, Artikel-Thread
    thumb = doc.get_new_xref()
    doc.update_object(thumb, "<< /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 >>")
    doc.update_stream(thumb, b"\x00")
    doc.xref_set_key(seite.xref, "Thumb", f"{thumb} 0 R")
    meta = doc.get_new_xref()
    doc.update_object(meta, "<< /Type /Metadata /Subtype /XML >>")
    doc.update_stream(meta, b"<x:xmpmeta>Seite von Mustermann</x:xmpmeta>")
    doc.xref_set_key(seite.xref, "Metadata", f"{meta} 0 R")
    af = doc.get_new_xref()
    ef = doc.get_new_xref()
    doc.update_object(ef, "<< /Type /EmbeddedFile >>")
    doc.update_stream(ef, b"<rechnung><kaeufer>Max Mustermann</kaeufer></rechnung>")
    doc.update_object(af, f"<< /Type /Filespec /F (zugferd-mustermann.xml) /UF (zugferd-mustermann.xml) "
                          f"/EF << /F {ef} 0 R >> /AFRelationship /Data >>")
    doc.xref_set_key(kat, "AF", f"[{af} 0 R]")
    doc.xref_set_key(kat, "Threads", "[<< /I << /Title (Artikel Mustermann) >> >>]")
    # Foto mit EXIF/XMP/Kommentar und eigenem XMP-Strom
    xref = seite.insert_image(fitz.Rect(72, 450, 272, 570), stream=jpeg_mit_metadaten())
    bildmeta = doc.get_new_xref()
    doc.update_object(bildmeta, "<< /Type /Metadata /Subtype /XML >>")
    doc.update_stream(bildmeta, b"<x:xmpmeta>Aufnahme Mustermann</x:xmpmeta>")
    doc.xref_set_key(xref, "Metadata", f"{bildmeta} 0 R")
    doc.save(pfad)
    doc.close()
    return Path(pfad)


def test_alle_nebenkanaele_werden_entfernt(tmp_path):
    pdf = pdf_mit_nebenkanaelen(tmp_path / "alles.pdf")
    assert GEHEIM in roh_text(pdf), "Testdatei enthält die Geheimnisse wirklich"
    doc = fitz.open(pdf)
    id_vorher = doc.xref_get_key(-1, "ID")[1]
    bild_vorher = doc[0].get_images()[0][0]
    pix_vorher = fitz.Pixmap(doc, bild_vorher)
    zaehler = nebenkanaele_zaehlen(doc)
    assert zaehler["anmerkungen"] >= 4 and zaehler["links"] == 1 and zaehler["lesezeichen"] == 2
    z = nebenkanaele_entfernen(doc, zaehler)
    aus = speichern(doc, tmp_path / "aus.pdf")
    pruefen_sauber(aus, [GEHEIM, "Musterfrau", "LV-2024-887766", "Müller", "02.09.1983", "app.alert"],
                   sichtbar=["Vertrag Nr. 4711", "Zweite Seite", "Text auf einer Ebene"])
    doc = fitz.open(aus)
    try:
        assert doc.get_toc() == [] and doc.embfile_count() == 0 and doc.get_page_labels() == []
        assert not any(doc.metadata.get(k) for k in ("author", "title", "subject", "keywords", "creator"))
        assert doc.xref_xml_metadata() == 0 or not doc.get_xml_metadata()
        assert all(not list(s.annots()) and not s.get_links() for s in doc)
        assert doc.xref_get_key(-1, "ID")[1] != id_vorher, "neue Dokument-ID (keine Verknüpfung zum Original)"
        katalog = doc.pdf_catalog()
        for s in ("OpenAction", "Names", "StructTreeRoot", "PieceInfo", "PageLabels", "AF", "Threads", "Outlines"):
            assert doc.xref_get_key(katalog, s)[0] == "null", s
        # Foto: noch darstellbar, Pixel unverändert, ohne EXIF/XMP/Kommentar/Anhang
        xref = doc[0].get_images()[0][0]
        daten = doc.extract_image(xref)["image"]
        assert b"Exif" not in daten and b"xmpmeta" not in daten and b"MotionPhoto" not in daten
        pix = fitz.Pixmap(doc, xref)
        assert (pix.width, pix.height) == (pix_vorher.width, pix_vorher.height)
        assert pix.samples == pix_vorher.samples, "Metadaten entfernen ändert keine Pixel"
        assert [n for n in (doc.get_ocgs() or {}).values() if GEHEIM in n.get("name", "")] == []
    finally:
        doc.close()
    for schluessel in ("anmerkungen", "links", "lesezeichen", "anhaenge", "seitenbeschriftungen", "aktionen",
                       "bild_metadaten", "strukturbaum", "miniaturbilder", "ebenen", "markierungen"):
        assert z[schluessel], schluessel
    hinweis = nebenkanal_hinweis(z)
    for wort in ("Anmerkung", "Link", "Lesezeichen", "eingebettete Datei", "Seitenbeschriftung", "Skript",
                 "Bild-Metadaten", "Strukturbaum", "Metadaten/XMP"):
        assert wort in hinweis, (wort, hinweis)


def test_nach_bake_und_ohne_zaehler(tmp_path):
    """Normalfall der Pipeline: bake() vor allem anderen; ohne Zähler zählt nebenkanaele_entfernen selbst."""
    pdf = pdf_mit_nebenkanaelen(tmp_path / "alles.pdf")
    doc = fitz.open(pdf)
    doc.bake()
    z = nebenkanaele_entfernen(doc)
    aus = speichern(doc, tmp_path / "aus.pdf")
    # Freitext und Notiz-Symbol sind nach bake() sichtbarer Seiteninhalt (Aufgabe der Schwärzung),
    # alles Übrige muss weg sein:
    roh = roh_text(aus)
    for g in ("Max.Mustermann", "Mustermann Seite", "Mustermann privat", "Foto von Max Mustermann",
              "LV-2024-887766", "Notizen Max Mustermann", "zugferd-mustermann", "Aufnahme Mustermann"):
        assert g not in roh, g
    assert z["lesezeichen"] == 2 and z["anhaenge"] == 1


def test_noch_nicht_angewendete_schwaerzungen_bleiben(tmp_path):
    doc = fitz.open()
    s = doc.new_page()
    s.insert_text((72, 100), "Max Mustermann", fontsize=11)
    s.add_text_annot((300, 100), "Notiz")
    s.add_redact_annot(fitz.Rect(70, 88, 160, 104))
    nebenkanaele_entfernen(doc)
    assert [a.type[0] for a in s.annots()] == [fitz.PDF_ANNOT_REDACT]
    s.apply_redactions()
    assert GEHEIM not in s.get_text()
    doc.close()


def test_reihenfolge_beschnitt_vor_offener_schwaerzung_bricht_ab():
    """Inhalt außerhalb des Beschnitts UND noch nicht angewendete Schwärzungen: kein stilles Anwenden
    fremder Schwärzungen mit eigenen Parametern, sondern ein klarer Fehler (Aufrufreihenfolge)."""
    doc = fitz.open()
    s = doc.new_page()
    s.insert_text((72, 100), "Max Mustermann", fontsize=11)
    s.insert_text((72, 800), "Rand Mustermann", fontsize=11)
    s.set_cropbox(fitz.Rect(0, 0, 595, 700))
    s.add_redact_annot(fitz.Rect(70, 88, 160, 104))
    with pytest.raises(RuntimeError, match="apply_redactions"):
        nebenkanaele_entfernen(doc)
    doc.close()


def test_unbekannte_anmerkungen_im_indirekten_annots_array(tmp_path):
    """Anmerkungen, die die API nicht aufzählt (hier: unbekannter Typ in einem indirekten /Annots-Array),
    werden trotzdem ausgetragen."""
    doc = fitz.open()
    s = doc.new_page()
    s.insert_text((72, 100), "Seite", fontsize=11)
    fremd = doc.get_new_xref()
    doc.update_object(fremd, "<< /Type /Annot /Subtype /Unbekannt /Rect [0 0 10 10] /Contents (Notiz Mustermann) >>")
    liste = doc.get_new_xref()
    doc.update_object(liste, f"[{fremd} 0 R]")
    doc.xref_set_key(s.xref, "Annots", f"{liste} 0 R")
    z = nebenkanaele_entfernen(doc)
    assert z["anmerkungen"] >= 1
    pruefen_sauber(speichern(doc, tmp_path / "aus.pdf"), [GEHEIM], sichtbar=["Seite"])


# ----------------------------------------------------------------------
# /ActualText, /Alt, /E (S-06)
# ----------------------------------------------------------------------
def seite_mit_strom(strom: bytes):
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((10, 10), " ", fontname="helv")          # legt Inhaltsstrom + Font-Ressource an
    doc.update_stream(seite.get_contents()[0], strom)
    return doc, seite


def test_actualtext_verschachtelte_klammern_hex_und_abkuerzung(tmp_path):
    doc, seite = seite_mit_strom(
        b"/Span <</ActualText (Max \\(Mustermann\\))>> BDC BT /helv 11 Tf 72 100 Td (Erste Zeile) Tj ET EMC\n"
        b"/Span <</ActualText (Klammer (verschachtelt) Erika Mustermann)>> BDC BT /helv 11 Tf 72 130 Td "
        b"(Zweite Zeile) Tj ET EMC\n"
        b"/Figure <</Alt <4D7573746572" + b"6D616E6E> /MCID 3>> BDC EMC\n"
        b"/Span <</E (Mustermann GmbH) /Lang (de)>> BDC BT /helv 11 Tf 72 160 Td (MM GmbH) Tj ET EMC\n"
        b"BT /helv 11 Tf 72 190 Td (Vierte Zeile: Beitrag 89,50 EUR) Tj ET")
    assert GEHEIM in seite.get_text(), "MuPDF gibt den Ersatztext statt der Glyphen aus"
    assert markierungen_entfernen(doc) == 4
    text = seite.get_text()
    assert GEHEIM not in text and "Erste Zeile" in text and "Zweite Zeile" in text and "89,50 EUR" in text
    assert markierungen_entfernen(doc) == 0, "idempotent"
    aus = speichern(doc, tmp_path / "aus.pdf")
    pruefen_sauber(aus, [GEHEIM, "verschachtelt"], sichtbar=["MM GmbH"])


@pytest.mark.parametrize("indirekt", [False, True])
def test_actualtext_in_properties_ressource(tmp_path, indirekt):
    doc, seite = seite_mit_strom(b"/Span /MC0 BDC BT /helv 11 Tf 72 100 Td (Name: Max Muster) Tj ET EMC")
    if indirekt:
        px = doc.get_new_xref()
        doc.update_object(px, "<< /ActualText (Geheim Erika Mustermann geb. 14.03.1979) >>")
        props = f"<< /MC0 {px} 0 R >>"
    else:
        props = "<< /MC0 << /ActualText (Geheim Erika Mustermann geb. 14.03.1979) >> >>"
    art, res = doc.xref_get_key(seite.xref, "Resources")
    ziel = int(res.split()[0]) if art == "xref" else seite.xref
    doc.xref_set_key(ziel, "Properties" if art == "xref" else "Resources/Properties", props)
    assert GEHEIM in seite.get_text()
    assert markierungen_entfernen(doc) >= 1
    assert seite.get_text().strip() == "Name: Max Muster"
    pruefen_sauber(speichern(doc, tmp_path / "aus.pdf"), [GEHEIM, "14.03.1979"], sichtbar=["Name: Max Muster"])


def test_actualtext_in_tief_verschachtelten_xobjects(tmp_path):
    """Drei Ebenen Form-XObjects (show_pdf_page von show_pdf_page) – auch die innerste wird bereinigt."""
    a = fitz.open()
    pa = a.new_page()
    pa.insert_text((10, 10), " ", fontname="helv")
    a.update_stream(pa.get_contents()[0], b"/Span <</ActualText (Tief: Max Mustermann 02.09.1983)>> BDC BT /helv 11 "
                                          b"Tf 20 30 Td (Tief: Max Muster) Tj ET EMC")
    b = fitz.open()
    b.new_page().show_pdf_page(fitz.Rect(36, 36, 400, 300), a, 0)
    c = fitz.open()
    pc = c.new_page()
    pc.insert_text((72, 600), "Außen ohne Namen", fontsize=11)
    pc.show_pdf_page(fitz.Rect(50, 50, 550, 450), b, 0)
    assert GEHEIM in pc.get_text()
    assert markierungen_entfernen(c) == 1
    assert GEHEIM not in pc.get_text() and "Max Muster" in pc.get_text()
    pruefen_sauber(speichern(c, tmp_path / "aus.pdf"), [GEHEIM, "02.09.1983"], sichtbar=["Außen ohne Namen"])


def test_lexer_ueberspringt_zeichenketten_und_inline_bilder():
    binaer = b"\x00\xff/ActualText (Max Mustermann)>> BDC\x89EI-nicht-am-Ende "
    strom = (b"BT /helv 11 Tf 72 100 Td (Text mit /ActualText (x) und BDC) Tj ET\n"
             b"q 10 0 0 10 50 50 cm BI /W 4 /H 4 /CS /G /BPC 8 ID " + binaer + b"\nEI Q\n"
             b"/Span <</ActualText (Mustermann)>> BDC EMC % Kommentar /ActualText (y) BDC\n/E gs /E Do")
    neu, anzahl = markierungen_aus_strom(strom)
    assert anzahl == 1
    assert binaer in neu, "Binärdaten des Inline-Bilds bleiben unangetastet"
    assert b"(Text mit /ActualText (x) und BDC) Tj" in neu, "sichtbarer Text bleibt"
    assert b"/E gs /E Do" in neu, "/E als Ressourcenname ist kein Abkürzungstext"
    assert b"(Mustermann)>> BDC EMC" not in neu


def test_lexer_rueckfall_bei_defektem_strom():
    strom = b"/Span <</ActualText (Max (Mustermann)) >> BDC ] ) unbalanciert << >> >> BT ET"
    neu, anzahl = markierungen_aus_strom(strom)
    assert anzahl == 1 and GEHEIM.encode() not in neu
    assert markierungen_aus_strom(b"BT /helv 11 Tf (ohne alles) Tj ET") == (b"BT /helv 11 Tf (ohne alles) Tj ET", 0)


# ----------------------------------------------------------------------
# Inhalte außerhalb des sichtbaren Bereichs (S-05)
# ----------------------------------------------------------------------
def test_text_unter_dem_beschnitt_und_ausserhalb_der_mediabox(tmp_path):
    doc = fitz.open()
    s = doc.new_page()
    s.insert_text((72, 100), "sichtbar: Vertrag 4711", fontsize=11)
    s.insert_text((72, 690), "am Rand sichtbar", fontsize=11)
    s.insert_text((72, 800), "unter dem Beschnitt: Max Mustermann 02.09.1983", fontsize=11)
    s.insert_text((72, -20), "oberhalb: Erika Mustermann", fontsize=11)
    s.insert_text((620, 300), "rechts außerhalb: Mustermann", fontsize=11)
    s.set_cropbox(fitz.Rect(0, 0, 595, 700))
    pdf = speichern(doc, tmp_path / "beschnitt.pdf")
    # Vorbedingung: der Text unter dem Beschnitt steht wirklich in der Datei und wird sichtbar, sobald jemand den
    # Beschnitt aufhebt (Poppler-pdftotext liest ihn sogar direkt; ein xpdf-pdftotext unter Windows nicht)
    with fitz.open(pdf) as vorher:
        vorher[0].set_cropbox(vorher[0].mediabox)
        assert GEHEIM in vorher[0].get_text(), "Testaufbau: Text unter dem Beschnitt fehlt"
    doc = fitz.open(pdf)
    sichtbar_vorher = doc[0].get_text()
    z = nebenkanaele_entfernen(doc)
    assert z["beschnitt"] == 1
    assert doc[0].get_text() == sichtbar_vorher
    aus = speichern(doc, tmp_path / "aus.pdf")
    pruefen_sauber(aus, [GEHEIM, "02.09.1983", "Beschnitt"], sichtbar=["sichtbar: Vertrag 4711", "am Rand sichtbar"])
    # auch nach Aufheben des Beschnitts ist nichts mehr da
    d = fitz.open(aus)
    d[0].set_cropbox(d[0].mediabox)
    assert GEHEIM not in d[0].get_text(flags=0)
    d.close()


def test_bild_ueber_den_beschnitt_hinaus(tmp_path):
    """Gescannte Seite, deren Kopf (mit Namen) per CropBox weggeschnitten wurde: die verborgenen Pixel
    werden entfernt, der sichtbare Teil bleibt, das Bild wird kompakt gespeichert."""
    quelle = fitz.open()
    q = quelle.new_page()
    q.insert_text((60, 60), "Kopf: Max Mustermann", fontsize=24)
    q.insert_text((60, 400), "Sichtbarer Inhalt", fontsize=24)
    pix = q.get_pixmap(dpi=100)
    doc = fitz.open()
    s = doc.new_page()
    s.insert_image(s.rect, stream=pix.tobytes("jpeg", jpg_quality=80))
    s.set_cropbox(fitz.Rect(0, 200, 595, 842))
    pdf = speichern(doc, tmp_path / "scan.pdf")
    groesse = pdf.stat().st_size
    doc = fitz.open(pdf)
    sichtbar = doc[0].get_pixmap(dpi=50).samples
    assert nebenkanaele_entfernen(doc)["beschnitt"] == 1
    assert "DCTDecode" in doc.xref_get_key(doc[0].get_images()[0][0], "Filter")[1], "wieder JPEG"
    aus = speichern(doc, tmp_path / "aus.pdf")
    assert aus.stat().st_size < 2 * groesse
    d = fitz.open(aus)
    nachher = d[0].get_pixmap(dpi=50).samples
    abweichung = sum(abs(a - b) for a, b in zip(sichtbar, nachher)) / len(sichtbar)
    assert abweichung < 3, "sichtbarer Teil unverändert (bis auf JPEG-Rauschen)"
    d[0].set_cropbox(d[0].mediabox)
    verborgen = d[0].get_pixmap(dpi=50, clip=fitz.Rect(0, 0, 595, 195))
    assert min(verborgen.samples) > 200, "verborgener Kopf ist leer"
    d.close()


def test_druckbeschnitt_und_saubere_seiten_bleiben_unberuehrt(tmp_path):
    doc = fitz.open()
    s = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50), False)
    pix.set_rect(pix.irect, (200, 220, 240))
    s.insert_image(fitz.Rect(-5, -5, 600, 847), pixmap=pix, keep_proportion=False)   # 5 pt Beschnittzugabe
    s.insert_text((72, 100), "Hintergrund bis in den Beschnitt", fontsize=11)
    t = doc.new_page()
    t.insert_text((72, 100), "Normale Seite", fontsize=11)
    pdf = speichern(doc, tmp_path / "druck.pdf")
    doc = fitz.open(pdf)
    vorher = [doc.xref_stream(x) for x in doc[0].get_contents()] + [doc.xref_stream(x) for x in doc[1].get_contents()]
    bild = doc[0].get_images()[0][0]
    assert nebenkanaele_entfernen(doc)["beschnitt"] == 0
    nachher = [doc.xref_stream(x) for x in doc[0].get_contents()] + [doc.xref_stream(x) for x in doc[1].get_contents()]
    assert vorher == nachher and doc[0].get_images()[0][0] == bild
    doc.close()


# ----------------------------------------------------------------------
# Bild-Metadaten (S-11), Seitenbeschriftungen (S-14)
# ----------------------------------------------------------------------
def test_jpeg_metadaten_segmente():
    jpeg = jpeg_mit_metadaten()
    sauber = nk._jpeg_ohne_metadaten(jpeg)
    assert GEHEIM.encode() not in sauber and b"MotionPhoto" not in sauber
    assert sauber.startswith(b"\xff\xd8\xff\xe0") and sauber.endswith(b"\xff\xd9")
    assert fitz.Pixmap(sauber).samples == fitz.Pixmap(jpeg).samples
    assert nk._jpeg_ohne_metadaten(b"kein jpeg") == b"kein jpeg"
    assert nk._jpeg_ohne_metadaten(jpeg[:200]) == jpeg[:200], "abgeschnittenes JPEG: unverändert"
    # Adobe-Segment (APP14, Farbtransformation) bleibt
    adobe = b"\xff\xee\x00\x0eAdobe\x00\x64\x00\x00\x00\x00\x01"
    mit_adobe = jpeg[:20] + adobe + jpeg[20:]
    assert adobe in nk._jpeg_ohne_metadaten(mit_adobe)


def test_jpeg_progressiv_und_jfif_vorschaubild():
    pil = pytest.importorskip("PIL.Image")
    import io
    bild = pil.new("RGB", (64, 48), (120, 80, 40))
    puffer = io.BytesIO()
    bild.save(puffer, "JPEG", progressive=True, quality=80)
    jpeg = puffer.getvalue()
    # JFIF-APP0 mit eingebettetem 2x1-Vorschaubild
    app0_laenge = int.from_bytes(jpeg[4:6], "big")
    jfif = bytearray(jpeg[4:4 + app0_laenge])
    vorschau = b"\x02\x01" + b"Mus" + b"ter"
    neu_app0 = b"\xff\xe0" + (2 + 12 + len(vorschau)).to_bytes(2, "big") + bytes(jfif[2:14]) + vorschau
    jpeg2 = jpeg[:2] + neu_app0 + jpeg[4 + app0_laenge:] + b"Anhang Mustermann"
    sauber = nk._jpeg_ohne_metadaten(jpeg2)
    assert b"Muster" not in sauber
    assert fitz.Pixmap(sauber).samples == fitz.Pixmap(jpeg).samples


def test_jpx_kaesten():
    def kasten(typ, daten):
        return (8 + len(daten)).to_bytes(4, "big") + typ + daten
    jp2 = (kasten(b"jP  ", b"\r\n\x87\n") + kasten(b"ftyp", b"jp2 \x00\x00\x00\x00jp2 ")
           + kasten(b"jp2h", b"ihdr...") + kasten(b"xml ", b"<x>Mustermann</x>") + kasten(b"uuid", b"0" * 16 + b"Mustermann")
           + kasten(b"jp2c", b"\xff\x4f\xff\x51codestream"))
    sauber = nk._jpx_ohne_metadaten(jp2)
    assert b"Mustermann" not in sauber and b"jp2c" in sauber and b"jp2h" in sauber
    assert nk._jpx_ohne_metadaten(b"kein jp2") == b"kein jp2"


def test_seitenbeschriftungen_s14(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Police", fontsize=11)
    doc.set_page_labels([{"startpage": 0, "prefix": "Police Mustermann LV-2024-887766 S.", "style": "D"}])
    z = nebenkanaele_entfernen(doc)
    assert z["seitenbeschriftungen"] == 1 and doc.get_page_labels() == []
    pruefen_sauber(speichern(doc, tmp_path / "aus.pdf"), [GEHEIM, "LV-2024-887766"], sichtbar=["Police"])


def test_hinweis_format():
    assert nebenkanal_hinweis({}) == "Entfernt bzw. eingebrannt: Metadaten/XMP."
    h = nebenkanal_hinweis({"formularfelder": 2, "anmerkungen": 1, "beschnitt": 1, "strukturbaum": 1,
                            "fehler": ["Bild 7: kaputt"]})
    assert h.startswith("Entfernt bzw. eingebrannt: 2 Formularfeld(er), 1 Anmerkung(en), ")
    assert "Strukturbaum" in h and "außerhalb des sichtbaren Bereichs" in h and "prüfen" in h


def test_zaehlen_vor_bake(tmp_path):
    """nebenkanaele_zaehlen liefert dieselben Schlüssel wie bisher schwaerzung._nebenkanaele_zaehlen."""
    pdf = pdf_mit_nebenkanaelen(tmp_path / "alles.pdf")
    doc = fitz.open(pdf)
    z = nebenkanaele_zaehlen(doc)
    assert set(z) == {"formularfelder", "anmerkungen", "links", "lesezeichen", "anhaenge", "miniaturbilder",
                      "ebenen", "xfa"}
    assert z["miniaturbilder"] == 1 and z["anhaenge"] == 1 and z["ebenen"] == 1 and z["xfa"] is False
    doc.close()


# ----------------------------------------------------------------------
# Lesen für die Erkennung (Gutachten R-04): nebenkanaele_lesen
# ----------------------------------------------------------------------
def _kanaele(eintraege):
    aus = {}
    for e in eintraege:
        aus.setdefault(e.kanal, []).append(e)
    return aus


def test_lesen_metadaten_lesezeichen_anhaenge_kommentare():
    """Info-Felder (auch eigene wie /Kunde), XMP, Lesezeichen, eingebettete Datei und Datei-Anmerkung samt Inhalt,
    Notizen an der Seite – jeweils als eigene Einheit; technische Felder (Producer, Kennungen) fehlen."""
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((72, 100), "Allgemeine Bedingungen", fontsize=11)
    doc.set_metadata({"title": "Antrag Max Mustermann", "author": "Erika Musterfrau", "producer": "Werkzeug 1.0"})
    info = int(doc.xref_get_key(-1, "Info")[1].split()[0])
    doc.xref_set_key(info, "Kunde", "(Kunde 4711 Mustermann)")
    doc.set_xml_metadata('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="r"><rdf:Description '
                         'xmlns:dc="d" xmlns:xmpMM="m" xmpMM:DocumentID="uuid:1234"><dc:creator><rdf:Seq>'
                         '<rdf:li>Max Mustermann</rdf:li></rdf:Seq></dc:creator></rdf:Description></rdf:RDF>'
                         '</x:xmpmeta>')
    doc.set_toc([[1, "Antrag Max Mustermann", 1], [1, "Anlagen", 1]])
    doc.embfile_add("Bank.txt", "IBAN DE89 3704 0044 0532 0130 00".encode(), filename="Bank.txt", desc="Bankdaten")
    seite.add_file_annot((300, 300), b"Telefon 0171 2345678", "Notiz.txt", desc="Rueckruf")
    seite.add_text_annot((100, 300), "Kunde Mustermann ruft zurück")
    kanaele = _kanaele(nk.nebenkanaele_lesen(doc))
    meta = " | ".join(e.text for e in kanaele["metadaten"])
    assert "Antrag Max Mustermann" in meta and "Erika Musterfrau" in meta and "Kunde 4711 Mustermann" in meta
    assert "Max Mustermann" in kanaele["metadaten"][-1].text and "uuid" not in meta and "Werkzeug" not in meta
    assert [e.text for e in kanaele["lesezeichen"]] == ["Antrag Max Mustermann", "Anlagen"]
    anhaenge = kanaele["anhaenge"]
    assert {e.einheit for e in anhaenge} == {0, 1} and all(e.pruefbar for e in anhaenge)
    assert any("IBAN DE89" in e.text for e in anhaenge) and any("0171 2345678" in e.text for e in anhaenge)
    assert any("Bank.txt" in e.text and "Bankdaten" in e.text for e in anhaenge)
    assert any("Kunde Mustermann ruft zurück" in e.text for e in kanaele["kommentare"])


def test_lesen_anhaenge_rekursiv_und_nicht_pruefbar():
    """Ein angehängtes PDF wird mit Seitentext UND eigenen Nebenkanälen gelesen; ein Foto, eine verschlüsselte PDF
    und eine unbekannte Binärdatei sind nicht prüfbar (pruefbar=False)."""
    innen = fitz.open()
    innen.new_page().insert_text((72, 100), "Antrag von Max Mustermann", fontsize=11)
    innen.set_metadata({"author": "Erika Musterfrau"})
    innen_bytes = innen.tobytes()
    geheim = fitz.open()
    geheim.new_page().insert_text((72, 100), "Max Mustermann", fontsize=11)
    geheim_bytes = geheim.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
    pix.clear_with(90)
    doc = fitz.open()
    doc.new_page()
    doc.embfile_add("Antrag.pdf", innen_bytes)
    doc.embfile_add("Geheim.pdf", geheim_bytes)
    doc.embfile_add("Foto.jpg", pix.tobytes("jpeg"))
    doc.embfile_add("Daten.bin", bytes(range(256)) * 4)
    inhalt = {e.einheit: e for e in nk.nebenkanaele_lesen(doc)
              if e.kanal == "anhaenge" and e.art.startswith("Inhalt")}
    assert inhalt[0].pruefbar and "Antrag von Max Mustermann" in inhalt[0].text
    assert "Erika Musterfrau" in inhalt[0].text
    assert not inhalt[1].pruefbar and "verschlüsselt" in inhalt[1].art
    assert not inhalt[2].pruefbar and "Bild (JPEG)" in inhalt[2].art
    assert not inhalt[3].pruefbar and "unbekanntes Format" in inhalt[3].art


def test_lesen_xml_und_webseite():
    """XML wird als „Etikett: Wert“ gelesen (der Elementname ist das Etikett); Schablonen, Kennungs-Attribute und
    Zeitstempel fallen weg. Eine Webseite als Text ohne Skripte."""
    xml = ('<?xml version="1.0"?><rsm:Invoice xmlns:rsm="urn:x"><ram:BuyerTradeParty><ram:Name>Max Mustermann'
           '</ram:Name><ram:ID schemeID="0088">4000001123452</ram:ID></ram:BuyerTradeParty>'
           '<template><field name="IBAN"/></template><ram:IssueDateTime>2024-01-01</ram:IssueDateTime></rsm:Invoice>')
    text = nk._xml_zu_text(xml)
    assert "Name: Max Mustermann" in text and "IssueDateTime" not in text and "template" not in text
    assert "schemeID" not in text
    texte, pruefbar, art = nk._anhang_inhalt(b"<html><head><script>var x='Geheim';</script></head><body><p>"
                                             b"Herr Max Mustermann</p></body></html>", 0)
    assert pruefbar and art == "Webseite" and "Herr Max Mustermann" in texte[0] and "Geheim" not in texte[0]


def test_lesen_ohne_nebenkanaele():
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Nur Seitentext", fontsize=11)
    assert nk.nebenkanaele_lesen(doc) == []
    assert nk.bildart(b"\xff\xd8\xff\xe0") == "JPEG" and nk.bildart(b"%PDF-1.7") is None
    assert nk.ist_html(b"\xef\xbb\xbf <!DOCTYPE html><html>") and not nk.ist_html(b"%PDF-1.7")
