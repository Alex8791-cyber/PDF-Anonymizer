"""Seiten, die sich nicht wie gewöhnliche Textseiten lesen lassen (Runde 2, Paket "seiten-lesen"):

  R-02  kaputte Textebene (falsche/fehlende ToUnicode) -> Seite per OCR lesen und schwärzen
  R-03  Text als Vektorpfade, Text in Kachelmustern     -> per OCR lesen, Mustertext entfernen
  R-05  /Rotate + CropBox                                -> sichtbarer Ausschnitt bleibt exakt erhalten
  R-06  riesige Seiten (Fotos mit 1 px = 1 pt)           -> Renderauflösung begrenzt, Fehler verständlich
  R-08  zyklisches Form-XObject                          -> Seite als Bild geschwärzt
  M-20  schräge Scans                                    -> Rechtecke folgen der schrägen Zeile
  M-31  MuPDF verschiebt den Rest der Zeile              -> kein Folgewort unter dem Platzhalter
  M-51  Kontroll-OCR von Bildbereichen                   -> keine zweite Ausrichtungssuche
  M-66  Unterschrift aus 1-2 Kurven / Linienzug          -> Hinweis VEKTORGRAFIK
"""

import math
import pickle
import re
import sys
from pathlib import Path

import pytest

import pymupdf as fitz

from conftest import braucht_ocr, schrift_mit_zeichen
from anonymisierer import bilder, ocr, schwaerzung
from anonymisierer import seitenmodell as sm
from anonymisierer.schwaerzung import schwaerze_pdf

NAME = "Max Mustermann"
IBAN = "DE89 3704 0044 0532 0130 00"
BRIEF = ["Muster Versicherung AG - Abteilung Leistung", "Herrn", NAME, "Hauptstraße 12", "10115 Berlin", "",
         "Ihre Schadenmeldung vom 03.05.2024", "", "Sehr geehrter Herr Mustermann,",
         "wir bestätigen den Eingang Ihrer Unterlagen. Versicherungsnehmer ist",
         f"{NAME}, geboren am 12.03.1975. Die Erstattung erfolgt auf das",
         f"Konto mit der IBAN {IBAN} bei der Commerzbank.", "", "Mit freundlichen Grüßen",
         "Ihre Muster Versicherung"]
FUELLFARBE = schwaerzung.FUELLFARBE


def brief_einfuegen(seite, zeilen=BRIEF, x=72, y=90, groesse=11, **kw):
    for i, z in enumerate(zeilen):
        if z:
            seite.insert_text((x, y + i * groesse * 1.45), z, fontsize=groesse, **kw)


def fund(text, ersatz="[PERSON A]", kategorie="namen"):
    return {"kategorie": kategorie, "text": text, "ersatz": ersatz}


NAMENSFUNDE = [fund(NAME), fund("Mustermann"), fund(IBAN, "[IBAN]", "iban")]


def graue_kaesten(seite):
    return [fitz.Rect(d["rect"]) for d in seite.get_drawings()
            if d.get("fill") and all(abs(a - b) < 0.02 for a, b in zip(d["fill"], FUELLFARBE))]


def codes(ergebnis):
    return {m["code"] for m in ergebnis.get("meldungen") or []}


# ----------------------------------------------------------------------
# R-05: /Rotate + CropBox
# ----------------------------------------------------------------------
def gedrehte_seite(winkel, mediabox, cropbox, vererbt=False):
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    s.insert_text((80, 120), "OBEN LINKS Mustermann", fontsize=12)
    s.insert_text((300, 420), "MITTE Hauptstraße 12", fontsize=12)
    s.insert_text((80, 760), "UNTEN Rand", fontsize=12)
    s.insert_text((10, 40), "WEGGESCHNITTEN Notiz", fontsize=9)
    s.draw_rect(fitz.Rect(200, 600, 400, 700), color=(1, 0, 0), fill=(0, 0, 1))
    doc.xref_set_key(s.xref, "MediaBox", "[%g %g %g %g]" % mediabox)
    if cropbox is not None:
        doc.xref_set_key(s.xref, "CropBox", "[%g %g %g %g]" % cropbox)
    if vererbt:      # /Rotate und /MediaBox nur im Seitenbaum (vererbt)
        eltern = int(doc.xref_get_key(s.xref, "Parent")[1].split()[0])
        doc.xref_set_key(eltern, "Rotate", str(winkel))
        doc.xref_set_key(eltern, "MediaBox", "[%g %g %g %g]" % mediabox)
        doc.xref_set_key(s.xref, "MediaBox", "null")
        doc.xref_set_key(s.xref, "Rotate", "null")
    else:
        doc.xref_set_key(s.xref, "Rotate", str(winkel))
    return fitz.open("pdf", doc.tobytes())


def ansicht_woerter(seite):
    """Wörter in Koordinaten der gedrehten Ansicht (so, wie sie ein Betrachter sieht)."""
    m = seite.rotation_matrix
    return sorted((w[4], tuple(round(v, 1) for v in fitz.Rect(w[:4]) * m)) for w in seite.get_text("words"))


@pytest.mark.parametrize("winkel", [90, 180, 270])
@pytest.mark.parametrize("mediabox,cropbox", [
    ((0, 0, 595, 842), (30, 50, 535, 797)),
    ((0, 0, 595, 842), (60, 12, 580, 822)),
    ((-100, -200, 495, 642), (-40, -150, 480, 600)),
    ((-100, -200, 495, 642), None),
])
@pytest.mark.parametrize("vererbt", [False, True])
def test_drehung_entfernen_erhaelt_den_sichtbaren_ausschnitt(winkel, mediabox, cropbox, vererbt):
    """R-05: page.remove_rotation() setzt die CropBox zurück (90/270°) bzw. spiegelt sie nicht (180°) – ein
    weggeschnittener Text wurde sichtbar, sichtbarer ging verloren. drehung_entfernen erhält Lage und Bild."""
    original = gedrehte_seite(winkel, mediabox, cropbox, vererbt)[0]
    doc = gedrehte_seite(winkel, mediabox, cropbox, vererbt)
    assert ocr.drehung_entfernen(doc[0]) is True
    neu = fitz.open("pdf", doc.tobytes())[0]
    assert neu.rotation == 0
    assert neu.rect == original.rect
    assert ansicht_woerter(neu) == ansicht_woerter(original)
    if cropbox is not None:
        assert "WEGGESCHNITTEN" not in neu.get_text()
    a = original.get_pixmap(dpi=24, alpha=False)
    b = neu.get_pixmap(dpi=24, alpha=False)
    assert (a.width, a.height) == (b.width, b.height)
    assert sum(1 for x, y in zip(a.samples, b.samples) if abs(x - y) > 40) == 0


def test_drehung_entfernen_ohne_drehung_aendert_nichts():
    doc = gedrehte_seite(0, (0, 0, 595, 842), (30, 50, 535, 797))
    seite = doc[0]
    vorher = (doc.xref_object(seite.xref), [doc.xref_stream(x) for x in seite.get_contents()], doc.xref_length())
    assert ocr.drehung_entfernen(seite) is False
    nachher = (doc.xref_object(seite.xref), [doc.xref_stream(x) for x in seite.get_contents()], doc.xref_length())
    assert nachher == vorher


def test_schwaerzung_gedrehter_beschnittener_seite_deckt_nichts_auf(tmp_path):
    """R-05 Ende zu Ende: verdeckte Notiz außerhalb der CropBox bleibt draußen (auch im Rohstrom), sichtbare Wörter
    bleiben erhalten, der Name ist weg."""
    for winkel in (90, 180, 270):
        doc = gedrehte_seite(winkel, (0, 0, 595, 842), (30, 50, 535, 797))
        pfad = tmp_path / f"gedreht_{winkel}.pdf"
        doc.save(pfad)
        original = fitz.open(pfad)[0]
        sichtbar = {w[4] for w in original.get_text("words")}
        e = schwaerze_pdf(pfad, [fund("Mustermann")], ziel_ordner=tmp_path / f"aus_{winkel}")
        assert e["ausgabe"] is not None, e
        aus = fitz.open(e["ausgabe"])
        seite = aus[0]
        assert seite.rect == original.rect
        text = seite.get_text()
        assert "WEGGESCHNITTEN" not in text and "Notiz" not in text
        roh = b"".join(aus.xref_stream(x) or b"" for x in range(1, aus.xref_length()) if aus.xref_is_stream(x))
        assert b"WEGGESCHNITTEN" not in roh
        assert "Mustermann" not in text
        nachher = {w[4] for w in seite.get_text("words")}
        assert sichtbar - {"Mustermann"} <= nachher, sorted(sichtbar - nachher)


# ----------------------------------------------------------------------
# R-06: riesige Seiten
# ----------------------------------------------------------------------
def fotoseite(breite_pt, hoehe_pt, breite_px, hoehe_px):
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, breite_px, hoehe_px), False)
    pix.clear_with(250)            # wie set_rect(..., (250, 250, 250)), aber in C: 48 MP 0,1 s statt 166 s unter Last
    doc = fitz.open()
    s = doc.new_page(width=breite_pt, height=hoehe_pt)
    s.insert_image(s.rect, pixmap=pix)
    return doc


def test_render_dpi_normale_seite_unveraendert():
    doc = fitz.open()
    seite = doc.new_page()                      # A4: 8,7 MP bei 300 dpi
    assert ocr.render_dpi(seite, None, 300) == 300
    assert ocr.render_dpi(seite, fitz.Rect(0, 0, 100, 100), 300) == 300


def test_render_dpi_handyfoto_mit_eigener_aufloesung():
    """12-MP-Foto mit 1 px = 1 pt: statt 300 dpi (212 MP, bis 3 GB je Arbeiter) die echte Auflösung."""
    doc = fotoseite(4032, 3024, 4032, 3024)
    seite = doc[0]
    dpi = ocr.render_dpi(seite, None, 300)
    assert dpi == 72
    assert (seite.rect.width * dpi / 72) * (seite.rect.height * dpi / 72) <= ocr.MAX_RENDER_PIXEL


def test_render_dpi_kleines_bild_auf_riesiger_seite_hoechstens_doppelt():
    doc = fotoseite(8064, 6048, 2016, 1512)     # 48-MP-Seite, Bild nur 18 dpi
    dpi = ocr.render_dpi(doc[0], None, 300)
    assert dpi == 36


def test_render_dpi_vektorseite_an_der_grenze():
    doc = fitz.open()
    seite = doc.new_page(width=5000, height=5000)
    dpi = ocr.render_dpi(seite, None, 300)
    assert dpi < 300
    assert (5000 * dpi / 72) ** 2 <= ocr.MAX_RENDER_PIXEL * 1.01


class _NichtUebertragbar(Exception):
    """Wie die MuPDF-Ausnahmen: lässt sich nicht zwischen Prozessen übertragen."""

    def __init__(self, text):
        super().__init__(text)
        self.zeiger = lambda: None


def test_arbeiter_uebersetzt_nicht_uebertragbare_ausnahme(monkeypatch):
    """R-06: Die MuPDF-Ausnahme ("Overly large image") ließ sich nicht picklen – die Nutzerin sah nur
    "cannot pickle 'SwigPyObject'". Der Arbeiter gibt jetzt einen RuntimeError mit lesbarem Text weiter."""
    def kaputt(*a, **k):
        raise _NichtUebertragbar("code=2: irgendwas")
    monkeypatch.setattr(ocr, "_ocr_lesen", kaputt)
    with pytest.raises(RuntimeError) as info:
        ocr._ocr_worker("x.pdf", 0, 300, None, "deu", None)
    pickle.loads(pickle.dumps(info.value))
    assert "irgendwas" in str(info.value)


def test_arbeiter_wiederholt_bei_speichermangel_mit_halber_aufloesung(monkeypatch):
    aufrufe = []

    def lesen(*a, verkleinern=1.0, **k):
        aufrufe.append(verkleinern)
        if verkleinern == 1.0:
            raise MemoryError()
        return {"woerter": [], "winkel": 0}
    monkeypatch.setattr(ocr, "_ocr_lesen", lesen)
    ergebnis = ocr._ocr_worker("x.pdf", 0, 300, None, "deu", None)
    assert aufrufe == [1.0, 0.5]
    assert ergebnis["speicher_knapp"] is True


def test_arbeiter_meldet_endgueltigen_speichermangel_verstaendlich(monkeypatch):
    class FzErrorLimit(Exception):
        pass

    def lesen(*a, **k):
        raise FzErrorLimit("code=5: Overly large image")
    monkeypatch.setattr(ocr, "_ocr_lesen", lesen)
    with pytest.raises(RuntimeError, match="zu groß für den verfügbaren Arbeitsspeicher"):
        ocr._ocr_worker("x.pdf", 0, 300, None, "deu", None)


@braucht_ocr
def test_riesige_fotoseite_wird_gelesen(tmp_path):
    """R-06 Ende zu Ende: Foto (1 px = 1 pt) einer Textseite, 2400 x 1800 pt (300 dpi wären 75 MP)."""
    quelle = fitz.open()
    q = quelle.new_page(width=2400, height=1800)
    for i, z in enumerate(["Versicherungsnehmer " + NAME, "IBAN " + IBAN, "Sehr geehrter Herr Mustermann,"]):
        q.insert_text((150, 300 + i * 120), z, fontsize=70)
    bild = q.get_pixmap(dpi=72, alpha=False).tobytes("png")
    doc = fitz.open()
    s = doc.new_page(width=2400, height=1800)
    s.insert_image(s.rect, stream=bild)
    pfad = tmp_path / "foto.pdf"
    doc.save(pfad)
    with ocr.OcrDienst(prozesse=1) as dienst:
        e = dienst.ergebnis(pfad, 0)
    text = " ".join(w[4] for w in e["woerter"])
    assert "Mustermann" in text, text
    assert not e.get("fehler")
    assert any(m["code"] == "OCR_GELESEN" and "sehr groß" in m["text"] for m in e["meldungen"]), e["meldungen"]


# ----------------------------------------------------------------------
# R-02: kaputte Textebene
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text,erwartet", [
    ("Pxvwhu#Yhuvlfkhuxqj#DJ#0#Dewhloxqj#Ohlvwxqj Khuuq Pd{#Pxvwhupdqq Kdxswvwudàh#45 43448#Ehuolq "
     "Lkuh#Vfkdghqphogxqj#yrp#3613815357 Vhku#jhhkuwhu#Khuu#Pxvwhupdqq/", True),
    ("AecdQb!FQbcUOTQbe_S!16!#!1NdQU]e_S!@QUcde_S =Qbb_ AMn!AecdQb]Q__ XQ^_dcdbQccQ!12 21115!2UbY__ "
     "Ub_Q!CSXQTU^]UYTe^W!f_]!04/05/3135 CUXb!WUUXbdUb!XUbb!AecdQb]Q__", True),
    ("�" * 40 + " " + "�" * 12, True),
    ("Sehr geehrter Herr Mustermann, wir bestätigen den Eingang Ihrer Unterlagen. Die Erstattung erfolgt "
     "auf das Konto mit der IBAN DE89 3704 0044 0532 0130 00 bei der Commerzbank.", False),
    ("Besondere Vereinbarungen", False),
    ("Gemeinschaftspraxis Dr. med. Hatice Çakir & Dr. med. Mathilde Brandt", False),
    ("Urszula Pawłowska <urszula_pawlowska@gmx.de> Mittwoch, 19. April 2025 > Reparaturrechnung und Fotos", False),
    ("Уважаемый господин Мустерманн, мы подтверждаем получение ваших документов и благодарим вас за терпение",
     False),
    ("Königsbrücker Str. 33 · 01099 Dresden Service-Telefon 0800 2345678", False),
])
def test_schrift_unlesbar(text, erwartet):
    assert ocr.schrift_unlesbar(text) is erwartet


def _truetype_brief():
    schrift = schrift_mit_zeichen("Mußäöü€")
    if schrift is None:
        pytest.skip("keine TrueType-Schrift mit Umlauten gefunden")
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s, fontname="tt", fontfile=str(schrift))
    return fitz.open("pdf", doc.tobytes(garbage=3))


def brief_ohne_tounicode():
    doc = _truetype_brief()
    for f in doc.get_page_fonts(0):
        doc.xref_set_key(f[0], "ToUnicode", "null")
    return doc


def brief_mit_falscher_tounicode():
    doc = _truetype_brief()
    for f in doc.get_page_fonts(0):
        art, wert = doc.xref_get_key(f[0], "ToUnicode")
        if art != "xref":
            continue
        tu = int(wert.split()[0])
        cmap = doc.xref_stream(tu).decode("latin-1")
        # jede Zuordnung um 3 verschieben ("Max" -> "Pd{"), wie ein Druckertreiber mit falscher Tabelle
        cmap = re.sub(r"(<[0-9a-fA-F]{4}>\s*<[0-9a-fA-F]{4}>\s*)<([0-9a-fA-F]{4})>",
                      lambda m: m.group(1) + "<%04X>" % (int(m.group(2), 16) + 3), cmap)
        cmap = re.sub(r"(beginbfchar.*?)(endbfchar)", lambda m: re.sub(
            r"(<[0-9a-fA-F]{4}>\s*)<([0-9a-fA-F]{4})>", lambda n: n.group(1) + "<%04X>" % (int(n.group(2), 16) + 3),
            m.group(1)) + m.group(2), cmap, flags=re.S)
        doc.update_stream(tu, cmap.encode("latin-1"))
    return fitz.open("pdf", doc.tobytes(garbage=3))


@pytest.mark.parametrize("bauen", [brief_ohne_tounicode, brief_mit_falscher_tounicode])
def test_kaputte_textebene_entscheidet_fuer_ocr(bauen):
    doc = bauen()
    seite = doc[0]
    if "Mustermann" in seite.get_text():
        pytest.skip("diese PyMuPDF-Version stellt die Zuordnung selbst wieder her")
    pruefung = ocr.seiten_pruefung(seite)
    assert pruefung.modus == "seite"
    assert any(m["code"] == "TEXTEBENE_UNLESBAR" for m in pruefung.meldungen)
    assert sm.unlesbare_schriften(seite)


def test_lesbare_textseiten_bleiben_ohne_ocr():
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s)
    s.insert_text((72, 700), "Besondere Vereinbarungen", fontsize=14, fontname="hebo")
    pruefung = ocr.seiten_pruefung(doc[0])
    assert pruefung.modus == "nein" and not pruefung.meldungen


@braucht_ocr
@pytest.mark.parametrize("bauen", [brief_ohne_tounicode, brief_mit_falscher_tounicode])
def test_kaputte_textebene_wird_per_ocr_geschwaerzt(tmp_path, bauen):
    """R-02: Die Seite sieht richtig aus, die Textebene ist Zeichensalat – früher 0 Funde bzw. Fund "Khuuq",
    Name und IBAN blieben sichtbar. Jetzt: OCR liest die Seite, geschwärzt wird über die OCR-Wortkästen."""
    doc = bauen()
    if "Mustermann" in doc[0].get_text():
        pytest.skip("diese PyMuPDF-Version stellt die Zuordnung selbst wieder her")
    pfad = tmp_path / "brief.pdf"
    doc.save(pfad)
    with ocr.OcrDienst(prozesse=1) as dienst:
        e = schwaerze_pdf(pfad, NAMENSFUNDE, ocr=dienst, ziel_ordner=tmp_path / "aus")
        assert e["ausgabe"] is not None, e
        assert e["reste"] == []
        kontrolle = dienst.text(e["ausgabe"], 0, winkel=0)
    assert "Mustermann" not in kontrolle and "3704" not in kontrolle, kontrolle
    assert "Versicherung" in kontrolle


# ----------------------------------------------------------------------
# R-03: Text als Vektorpfade, Text in Kachelmustern
# ----------------------------------------------------------------------
def als_vektoren(zeilen=BRIEF):
    hilf = fitz.open()
    s = hilf.new_page()
    brief_einfuegen(s, zeilen)
    svg = s.get_svg_image(text_as_path=True)
    svgdoc = fitz.open("svg", svg.encode())
    return fitz.open("pdf", svgdoc.convert_to_pdf())


def test_vektortext_mit_seitenzahl_wird_per_ocr_gelesen():
    """R-03: Seite als Kurven plus eine echte Zeile "Seite 1 von 1" galt als Textseite – keine OCR, 0 Funde."""
    doc = als_vektoren()
    doc[0].insert_text((450, 820), "Seite 1 von 1", fontsize=9)
    pruefung = ocr.seiten_pruefung(doc[0])
    assert pruefung.modus == "seite"
    assert any(m["code"] == "OCR_GELESEN" and "Grafik" in m["text"] for m in pruefung.meldungen)


def test_vektortext_auf_textseite_wird_als_bereich_gelesen():
    doc = als_vektoren(["Herrn", NAME, "Hauptstraße 12", "10115 Berlin"])
    seite = doc[0]
    brief_einfuegen(seite, BRIEF[6:] * 3, y=300)
    pruefung = ocr.seiten_pruefung(seite)
    assert pruefung.modus == "bilder"
    assert pruefung.bereiche and all(r.y1 < 300 for r in pruefung.bereiche)


def test_wenige_kurven_sind_kein_vektortext():
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s)
    s.draw_circle((300, 600), 20, color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    s.draw_rect(fitz.Rect(72, 650, 300, 700), color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
    assert ocr.vektortext_bereiche(doc[0]) == []
    assert ocr.seiten_pruefung(doc[0]).modus == "nein"


def kachelmuster_seite():
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s, ["Allgemeine Versicherungsbedingungen (AVB) - Auszug", "",
                        "§ 1 Gegenstand der Versicherung",
                        "Versichert sind Schäden an den im Versicherungsschein bezeichneten Sachen.",
                        "§ 2 Beginn des Versicherungsschutzes",
                        "Der Versicherungsschutz beginnt zu dem im Versicherungsschein angegebenen Zeitpunkt."])
    doc = fitz.open("pdf", doc.tobytes())
    s = doc[0]
    fx = [f[0] for f in doc.get_page_fonts(0)][0]
    pat = doc.get_new_xref()
    doc.update_object(pat, f"<< /Type /Pattern /PatternType 1 /PaintType 1 /TilingType 1 /BBox [0 0 420 30] "
                           f"/XStep 420 /YStep 30 /Resources << /Font << /F1 {fx} 0 R >> >> >>")
    doc.update_stream(pat, f"BT /F1 11 Tf 2 10 Td (Kunde: {NAME}, IBAN {IBAN}) Tj ET".encode())
    c = doc.get_new_xref()
    doc.update_object(c, "<<>>")
    doc.update_stream(c, b"q /Pattern cs /P1 scn 72 400 430 32 re f Q")
    inhalte = s.get_contents()
    doc.xref_set_key(s.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in inhalte) + f" {c} 0 R]")
    art, w = doc.xref_get_key(s.xref, "Resources")
    if art == "xref":
        doc.xref_set_key(int(w.split()[0]), "Pattern", f"<< /P1 {pat} 0 R >>")
    else:
        doc.xref_set_key(s.xref, "Resources/Pattern", f"<< /P1 {pat} 0 R >>")
    return fitz.open("pdf", doc.tobytes()), pat


def test_text_in_kachelmuster_wird_erkannt():
    doc, _ = kachelmuster_seite()
    seite = doc[0]
    assert "Mustermann" not in seite.get_text()
    befund = ocr.textebene_pruefen(seite)
    assert befund.verborgen >= ocr.VERBORGEN_MIN_ZEICHEN
    assert ocr.seiten_pruefung(seite).modus == "seite"


def test_text_abschnitte_entfernen():
    strom = b"q 1 0 0 1 0 0 cm BT /F1 11 Tf (ET BT \\) Name) Tj ET 0 0 10 10 re f BT (x) Tj ET Q"
    assert schwaerzung._text_abschnitte_entfernen(strom) == b"q 1 0 0 1 0 0 cm  0 0 10 10 re f  Q"


@braucht_ocr
def test_text_in_kachelmuster_verlaesst_die_ausgabe_nicht(tmp_path):
    doc, pat = kachelmuster_seite()
    pfad = tmp_path / "muster.pdf"
    doc.save(pfad)
    with ocr.OcrDienst(prozesse=1) as dienst:
        e = schwaerze_pdf(pfad, [fund("Max Mus"), fund(IBAN, "[IBAN]", "iban")], ocr=dienst,
                          ziel_ordner=tmp_path / "aus")
    assert e["ausgabe"] is not None, e
    aus = fitz.open(e["ausgabe"])
    roh = b"".join(aus.xref_stream(x) or b"" for x in range(1, aus.xref_length()) if aus.xref_is_stream(x))
    assert b"Mustermann" not in roh and b"3704" not in roh


# ----------------------------------------------------------------------
# R-08: zyklisches Form-XObject
# ----------------------------------------------------------------------
def zyklus_brief():
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s)
    doc = fitz.open("pdf", doc.tobytes())
    x = doc.get_new_xref()
    doc.update_object(x, f"<< /Type /XObject /Subtype /Form /BBox [0 0 100 100] "
                         f"/Resources << /XObject << /X1 {x} 0 R >> >> >>")
    doc.update_stream(x, b"q 0.9 0 0 0.9 1 1 cm /X1 Do Q")
    s = doc[0]
    c = doc.get_new_xref()
    doc.update_object(c, "<<>>")
    doc.update_stream(c, b"q 1 0 0 1 400 50 cm /X1 Do Q")
    inhalte = s.get_contents()
    doc.xref_set_key(s.xref, "Contents", "[" + " ".join(f"{i} 0 R" for i in inhalte) + f" {c} 0 R]")
    art, w = doc.xref_get_key(s.xref, "Resources")
    if art == "xref":
        doc.xref_set_key(int(w.split()[0]), "XObject", f"<< /X1 {x} 0 R >>")
    else:
        doc.xref_set_key(s.xref, "Resources/XObject", f"<< /X1 {x} 0 R >>")
    return fitz.open("pdf", doc.tobytes())


def test_seite_als_bild_schwaerzen_brennt_rechtecke_ein():
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s)
    ziel = s.search_for("Mustermann")[0]
    bilder.seite_als_bild_schwaerzen(doc, s, [ziel], dpi=100)
    s = doc[0]
    assert s.get_text().strip() == ""
    assert len(s.get_images()) == 1
    pix = s.get_pixmap(dpi=100, clip=ziel)
    # das Rechteck ist einheitlich grau (keine Schrift mehr darin)
    werte = set(pix.samples)
    assert max(werte) - min(werte) <= 6, sorted(werte)[:5]


@braucht_ocr
def test_zyklisches_xobjekt_seite_wird_als_bild_geschwaerzt(tmp_path):
    """R-08: apply_redactions brach mit "exception stack overflow" ab – keine Ausgabe, unverständlicher Fehler."""
    pfad = tmp_path / "zyklus.pdf"
    zyklus_brief().save(pfad)
    with ocr.OcrDienst(prozesse=1) as dienst:
        e = schwaerze_pdf(pfad, NAMENSFUNDE, ocr=dienst, ziel_ordner=tmp_path / "aus")
        assert e["ausgabe"] is not None and e["fehler"] is None, e
        assert "SEITE_ALS_BILD" in codes(e)
        assert e["reste"] == []
        kontrolle = dienst.text(e["ausgabe"], 0, winkel=0)
    assert "Mustermann" not in kontrolle and "3704" not in kontrolle, kontrolle
    assert "Commerzbank" in kontrolle


# ----------------------------------------------------------------------
# M-31: Platzhalter und verschobener Rest der Zeile
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile,treffer", [
    ("Frau Berg Versicherungsmakler GmbH", "Berg"),
    ("Sehr geehrter Herr Ott, Ihr Vertrag ist da.", "Ott"),
    ("Max Mustermann, geb. 02.09.1983, wohnhaft Hauptstraße 5, 90403 Nürnberg, Tel. 0911 123456.", None),
])
def test_kein_folgewort_unter_dem_platzhalter(tmp_path, zeile, treffer):
    """M-31: MuPDF 1.28.5+ verschiebt nach dem Entfernen den Rest der Zeile nach links – das Folgewort lag unter
    dem grauen Kasten ("[PERSON A]/ersicherungsmakler", Textebene "[P,A]Ihr")."""
    doc = fitz.open()
    doc.new_page().insert_text((50, 80), zeile, fontsize=10)
    pfad = tmp_path / "zeile.pdf"
    doc.save(pfad)
    if treffer:
        funde = [fund(treffer)]
    else:
        funde = [fund("Max Mustermann"), fund("02.09.1983", "[GEB-DATUM]", "geburt"),
                 fund("Hauptstraße 5", "[ADRESSE]", "strasse"), fund("90403 Nürnberg", "[PLZ ORT]", "plzort"),
                 fund("0911 123456", "[TELEFON]", "telefon")]
    e = schwaerze_pdf(pfad, funde, ziel_ordner=tmp_path / "aus")
    seite = fitz.open(e["ausgabe"])[0]
    kaesten = graue_kaesten(seite)
    assert kaesten
    getroffen = {w for f in funde for w in f["text"].split()}
    for w in seite.get_text("words"):
        r = fitz.Rect(w[:4])
        if w[4].startswith("[") or w[4].endswith("]") or w[4].strip(".,") in getroffen:
            continue
        for k in kaesten:
            if min(r.y1, k.y1) - max(r.y0, k.y0) > 0.4 * r.height:
                assert min(r.x1, k.x1) - max(r.x0, k.x0) <= 0.3, (w[4], r, k)
    assert not any("unter einem Platzhalter" in h for h in e["hinweise"])


@braucht_ocr
def test_durchsuchbarer_scan_kasten_bleibt_ueber_den_bildpixeln(tmp_path):
    """Auf einem durchsuchbaren Scan rutscht nur die unsichtbare Textebene – der graue Kasten muss dort bleiben,
    wo die Bildpixel des Namens entfernt wurden (sonst stünde der Platzhalter neben einem weißen Loch)."""
    quelle = fitz.open()
    q = quelle.new_page()
    zeilen = ["Ansprechpartnerin: Frau Berg Versicherungsmakler GmbH", "Sehr geehrte Damen und Herren,",
              "wir bestätigen den Eingang Ihrer Unterlagen vom 12.03.2025."]
    for i, z in enumerate(zeilen):
        q.insert_text((60, 100 + 20 * i), z, fontsize=12)
    bild = q.get_pixmap(dpi=200, alpha=False).tobytes("png")
    ziel = q.search_for("Berg")[0]
    doc = fitz.open()
    s = doc.new_page()
    s.insert_image(s.rect, stream=bild)
    for i, z in enumerate(zeilen):
        s.insert_text((60, 100 + 20 * i), z, fontsize=12, render_mode=3)
    pfad = tmp_path / "durchsuchbar.pdf"
    doc.save(pfad)
    with ocr.OcrDienst(prozesse=1) as dienst:
        e = schwaerze_pdf(pfad, [fund("Berg")], ocr=dienst, ziel_ordner=tmp_path / "aus")
    seite = fitz.open(e["ausgabe"])[0]
    kern = fitz.Rect(ziel.x0 + 0.5, ziel.y0 + 0.3 * ziel.height, ziel.x1 - 0.5, ziel.y1 - 0.3 * ziel.height)
    assert any(k.contains(kern) for k in graue_kaesten(seite)), (kern, graue_kaesten(seite))


def test_textebene_ohne_verschraenkung(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((50, 80), "Kennzeichen S-TB 4711 laut Antrag.", fontsize=10)
    pfad = tmp_path / "kennzeichen.pdf"
    doc.save(pfad)
    e = schwaerze_pdf(pfad, [fund("S-TB 4711", "[KENNZEICHEN]", "kfz")], ziel_ordner=tmp_path / "aus")
    text = " ".join(fitz.open(e["ausgabe"])[0].get_text(sort=True).split())
    assert "[KENNZEICHEN] laut Antrag." in text, text


# ----------------------------------------------------------------------
# M-66: Unterschrift aus wenigen Kurven
# ----------------------------------------------------------------------
def brief_mit_zeichnung(tmp_path, zeichnen):
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s)
    form = s.new_shape()
    zeichnen(form)
    form.finish(color=(0, 0, 0.5), width=1.2)
    form.commit()
    pfad = tmp_path / "zeichnung.pdf"
    doc.save(pfad)
    return pfad


@pytest.mark.parametrize("zeichnen,hinweis", [
    (lambda f: f.draw_bezier((80, 400), (120, 360), (160, 440), (220, 395)), True),             # 1 Kurve
    (lambda f: (f.draw_bezier((80, 400), (120, 360), (160, 440), (220, 395)),
                f.draw_bezier((220, 395), (240, 380), (260, 410), (280, 390))), True),           # 2 Kurven
    (lambda f: f.draw_polyline([(80 + 6 * i, 400 + (8 if i % 2 else -8)) for i in range(40)]), True),
    (lambda f: (f.draw_line((72, 400), (520, 400)), f.draw_line((72, 380), (72, 420)),
                f.draw_line((520, 380), (520, 420))), False),                                    # Tabellenlinien
])
def test_vektorunterschrift_meldet_vektorgrafik(tmp_path, zeichnen, hinweis):
    pfad = brief_mit_zeichnung(tmp_path, zeichnen)
    e = schwaerze_pdf(pfad, [fund(NAME)], ziel_ordner=tmp_path / "aus")
    assert ("VEKTORGRAFIK" in codes(e)) is hinweis


# ----------------------------------------------------------------------
# M-51: Kontroll-OCR von Bildbereichen mit der Ausrichtung der Analyse
# ----------------------------------------------------------------------
def test_vorgegebener_winkel_gilt_fuer_anfragen_ohne_winkel(tmp_path):
    pfad = tmp_path / "a.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pfad)
    dienst = ocr.OcrDienst(prozesse=1)
    try:
        clip = fitz.Rect(10, 10, 200, 200)
        assert dienst._schluessel(pfad, 0, 300, clip, None)[4] is None
        dienst.winkel_vorgeben(pfad, 0, clip, 180)
        assert dienst._schluessel(pfad, 0, 300, clip, None)[4] == 180
        assert dienst._schluessel(pfad, 0, 300, clip, 90)[4] == 90
        assert dienst._schluessel(pfad, 0, 300, fitz.Rect(0, 0, 5, 5), None)[4] is None
    finally:
        dienst.schliessen()


class _ZaehlDienst:
    """Attrappe: zählt OCR-Anfragen der Kontroll-OCR."""

    def __init__(self):
        self.anfragen = []
        self.vorgaben = []

    def winkel_falls_bekannt(self, pfad, nr, dpi=300, clip=None):
        return 90

    def winkel_vorgeben(self, pfad, nr, clip, winkel):
        self.vorgaben.append((nr, tuple(fitz.Rect(clip)), winkel))

    def ergebnis(self, pfad, nr, dpi=300, clip=None, winkel=None):
        self.anfragen.append((nr, clip, winkel))
        return {"woerter": [], "winkel": winkel or 0}


def test_kontroll_ocr_von_bildbereichen_ohne_neue_ausrichtungssuche(tmp_path):
    lauf = schwaerzung._Lauf(tmp_path / "x.pdf", [], None, None, None, _ZaehlDienst(), None, tmp_path)
    lauf.ocr_modus[0] = "bilder"
    bereich = fitz.Rect(50, 50, 300, 300)
    lauf.bildbereiche[0] = [bereich]
    lauf.kategorien_je_seite[0] = {"namen"}
    schwaerzung._kontroll_woerter(lauf, tmp_path / "ausgabe.pdf", 0, [])
    assert lauf.ocr.anfragen == [(0, bereich, 90)]
    assert lauf.ocr.vorgaben == [(0, tuple(bereich), 90)]


def test_kontroll_ocr_sucht_die_ausrichtung_wenn_sie_unbekannt_ist(tmp_path):
    """Ohne bekannte Ausrichtung (z. B. OCR-Fehler bei der Analyse) wird nichts vorgegeben – die Kontroll-OCR sucht
    die Ausrichtung selbst, statt ein gedrehtes Foto nur waagerecht zu lesen."""
    class Unbekannt(_ZaehlDienst):
        def winkel_falls_bekannt(self, pfad, nr, dpi=300, clip=None):
            return None

    lauf = schwaerzung._Lauf(tmp_path / "x.pdf", [], None, None, None, Unbekannt(), None, tmp_path)
    lauf.ocr_modus[0] = "bilder"
    bereich = fitz.Rect(50, 50, 300, 300)
    lauf.bildbereiche[0] = [bereich]
    lauf.kategorien_je_seite[0] = {"namen"}
    schwaerzung._kontroll_woerter(lauf, tmp_path / "ausgabe.pdf", 0, [])
    assert lauf.ocr.anfragen == [(0, bereich, None)]
    assert lauf.ocr.vorgaben == []


def test_ausgefallene_kontroll_ocr_wird_gemeldet(tmp_path):
    class Kaputt(_ZaehlDienst):
        def ergebnis(self, pfad, nr, dpi=300, clip=None, winkel=None):
            return {"woerter": [], "winkel": 0, "fehler": True}

    lauf = schwaerzung._Lauf(tmp_path / "x.pdf", [], None, None, None, Kaputt(), None, tmp_path)
    lauf.ocr_modus[0] = "seite"
    lauf.kategorien_je_seite[0] = {"namen"}
    schwaerzung._kontroll_woerter(lauf, tmp_path / "ausgabe.pdf", 0, [fitz.Rect(0, 0, 10, 10)])
    assert lauf.restrisiko_fehler is True
    assert any(m["code"] == "OCR_FEHLER" for m in lauf.meldungen)


# ----------------------------------------------------------------------
# M-20: schräge Scans
# ----------------------------------------------------------------------
def schraege_ocr_woerter(winkel_grad=2.5, x0=60.0, y0=200.0, hoehe=11.0):
    """OCR-Wörter einer um winkel_grad schrägen Zeile, wie sie eine gerade gerückte Lesung liefert: der Kasten
    eines Worts ist der achsenparallele Umriss des gedrehten Wortrechtecks (10-Tupel mit Schräglage)."""
    import math
    woerter, lauf = [], 0.0                      # lauf: Abstand vom Zeilenanfang entlang der schrägen Grundlinie
    c, s = math.cos(math.radians(winkel_grad)), math.sin(math.radians(winkel_grad))
    for i, (text, breite) in enumerate([("Konto", 30.0), ("DE89", 26.0), ("3704", 24.0), ("0044", 24.0),
                                        ("0532", 24.0), ("0130", 24.0), ("00", 12.0), ("abgebucht.", 52.0)]):
        ecken = [(x0 + (lauf + dx) * c - dy * s, y0 + (lauf + dx) * s + dy * c)
                 for dx in (0, breite) for dy in (0, hoehe)]
        xs, ys = [e[0] for e in ecken], [e[1] for e in ecken]
        woerter.append((min(xs), min(ys), max(xs), max(ys), text, 0, 0, i, 0, winkel_grad))
        lauf += breite + 5.0
    return woerter


def test_schraege_ocr_zeile_bekommt_treppenrechtecke():
    doc = fitz.open()
    seite = doc.new_page()
    woerter = schraege_ocr_woerter()
    m = sm.seite_aufbauen(seite, 0, ocr_woerter=woerter)
    start = m.text.index("DE89")
    ende = m.text.index("00 abgebucht") + 2
    teile = m.rechtecke(start, ende)
    assert len(teile) > 1
    einzeln = max(w[3] - w[1] for w in woerter[1:7])
    for r, *_ in teile:
        assert r.height <= einzeln + 2 * sm.OCR_RAND + sm.OCR_STUFE_TOLERANZ + 0.5, (r, einzeln)
    # jedes Wort der Stelle ist vollständig bedeckt
    for w in woerter[1:7]:
        wr = fitz.Rect(w[:4])
        bedeckt = fitz.Rect()
        for r, *_ in teile:
            bedeckt |= (r & wr)
        assert abs(bedeckt) >= 0.97 * abs(wr), (w[4], bedeckt, wr)
    vereinigt = fitz.Rect()
    for w in woerter[1:7]:
        vereinigt |= fitz.Rect(w[:4])
    assert all(r.height < vereinigt.height for r, *_ in teile)


def test_gerade_ocr_zeile_bleibt_ein_rechteck():
    doc = fitz.open()
    seite = doc.new_page()
    woerter = schraege_ocr_woerter(winkel_grad=0.0)
    m = sm.seite_aufbauen(seite, 0, ocr_woerter=woerter)
    start = m.text.index("DE89")
    ende = m.text.index("00 abgebucht") + 2
    assert len(m.rechtecke(start, ende)) == 1


def test_kurzes_ocr_wort_wird_nicht_als_senkrechte_zeile_zerlegt():
    """"6." ist schmaler als hoch – trotzdem eine waagerechte Zeile: ein Rechteck, keine Stücke."""
    doc = fitz.open()
    seite = doc.new_page()
    for woerter in ([(60.4, 466.6, 71.4, 477.4, "6.", 0, 0, 0, 0, 0.0)],
                    [(60.4, 466.6, 71.4, 477.4, "6.", 0, 0, 0, 0, 0.0),
                     (75.0, 466.6, 160.0, 477.4, "Unfallhergang", 0, 0, 1, 0, 0.0)]):
        m = sm.seite_aufbauen(seite, 0, ocr_woerter=woerter)
        assert len(m.rechtecke(0, 2)) == 1


def test_schraege_senkrechte_ocr_zeile_bekommt_treppenrechtecke():
    import math
    c, s = math.cos(math.radians(2.5)), math.sin(math.radians(2.5))
    woerter, lauf = [], 0.0
    for i, (text, laenge) in enumerate([("Konto", 30.0), ("DE89", 26.0), ("3704", 24.0), ("0044", 24.0),
                                        ("0532", 24.0)]):
        ecken = [(100.0 + (lauf + dl) * s - dq, 700.0 - (lauf + dl) * c - dq * s)
                 for dl in (0, laenge) for dq in (0, 11.0)]
        xs, ys = [e[0] for e in ecken], [e[1] for e in ecken]
        woerter.append((min(xs), min(ys), max(xs), max(ys), text, 0, 0, i, 90, 2.5))
        lauf += laenge + 5.0
    doc = fitz.open()
    seite = doc.new_page()
    m = sm.seite_aufbauen(seite, 0, ocr_woerter=woerter)
    teile = m.rechtecke(m.text.index("DE89"), m.text.index("0532") + 4)
    assert len(teile) > 1
    vereinigt = fitz.Rect()
    for w in woerter[1:]:
        vereinigt |= fitz.Rect(w[:4])
    assert all(r.width < vereinigt.width for r, *_ in teile)


def test_platzhalter_steht_ueber_der_ganzen_treppe():
    doc = fitz.open()
    seite = doc.new_page()
    m = sm.seite_aufbauen(seite, 0, ocr_woerter=schraege_ocr_woerter(winkel_grad=1.5))
    start = m.text.index("3704")
    ende = m.text.index("0532") + 4
    rects = [t[0] for t in m.rechtecke(start, ende)]
    zone = schwaerzung._platzhalter_treppe(rects)
    assert len(rects) > 1 and zone is not None
    vereinigt = fitz.Rect()
    for r in rects:
        vereinigt |= r
    assert zone == vereinigt


def test_streifen_eines_durchsuchbaren_scans_sind_keine_treppe():
    """Bildrechteck der Stelle plus schmale Streifen über der unsichtbaren Textebene (etwas versetzt): Der
    Platzhalter bleibt im Bildrechteck und darf dort wie bisher in die freie Lücke wachsen."""
    for rects in ([(90.4, 466.5, 170.4, 478.4), (88.8, 466.7, 128.3, 472.9), (133.2, 466.7, 169.4, 472.9)],
                  [(331.9, 785.7, 348.5, 795.9), (330.1, 786.9, 342.7, 791.0)],
                  [(406.3, 792.9, 434.5, 803.8), (404.7, 795.0, 411.5, 799.2), (414.7, 795.0, 428.8, 799.2)]):
        assert schwaerzung._platzhalter_treppe([fitz.Rect(r) for r in rects]) is None


# ----------------------------------------------------------------------
# Vorbereitung: Drehung mit Selbstprüfung
# ----------------------------------------------------------------------
def test_vorbereitung_entfernt_drehung_mit_ausschnitt_ohne_abweichung():
    doc = gedrehte_seite(270, (-100, -200, 495, 642), (-40, -150, 480, 600))
    original = fitz.open("pdf", doc.tobytes())[0]
    info = sm.dokument_vorbereiten(doc)
    seite = info["dokument"][0]
    assert info["rotation"] == {0: 270}
    assert not info.get("drehung_abweichung")
    assert seite.rotation == 0 and seite.rect == original.rect
    assert ansicht_woerter(seite) == ansicht_woerter(original)


def test_ocr_arbeiter_liest_gedrehte_beschnittene_seite_im_sichtbaren_ausschnitt(tmp_path):
    """Der OCR-Arbeiter öffnet die Originaldatei selbst – er muss dieselbe Geometrie sehen wie das Modell."""
    doc = gedrehte_seite(90, (0, 0, 595, 842), (30, 50, 535, 797))
    pfad = tmp_path / "gedreht.pdf"
    doc.save(pfad)
    arbeiter = fitz.open(pfad)
    ocr.drehung_entfernen(arbeiter[0])
    modell = fitz.open(pfad)
    info = sm.dokument_vorbereiten(modell)
    assert arbeiter[0].rect == info["dokument"][0].rect
    assert ansicht_woerter(arbeiter[0]) == ansicht_woerter(info["dokument"][0])


def test_gedrehte_seite_mit_anmerkung_sieht_im_arbeiter_aus_wie_im_modell(tmp_path):
    """Der OCR-Arbeiter brennt Anmerkungen einer gedrehten Seite ein wie die Vorbereitung – sonst läge der
    Stempel im Bild der OCR an anderer Stelle als im Modell."""
    doc = gedrehte_seite(90, (0, 0, 595, 842), (30, 50, 535, 797))
    seite = doc[0]
    stempel = seite.add_freetext_annot(fitz.Rect(100, 300, 300, 340), "GEPRUEFT Max Mustermann", fontsize=12)
    stempel.update()
    pfad = tmp_path / "gedreht_stempel.pdf"
    doc.save(pfad)
    arbeiter = fitz.open(pfad)
    ocr._anmerkungen_einbrennen(arbeiter, arbeiter[0])
    ocr.drehung_entfernen(arbeiter[0])
    modell = sm.dokument_vorbereiten(fitz.open(pfad))["dokument"]
    a = arbeiter[0].get_pixmap(dpi=36, alpha=False)
    b = modell[0].get_pixmap(dpi=36, alpha=False)
    assert (a.width, a.height) == (b.width, b.height)
    assert sum(1 for x, y in zip(a.samples, b.samples) if abs(x - y) > 40) == 0
    assert "GEPRUEFT" in modell[0].get_text()


# ======================================================================
# Runde 2, Nachbesserung (Review der Befunde R-02, R-03, R-06, R-08)
# ======================================================================
# ----------------------------------------------------------------------
# R-02: Glyphennummern als Unicode, falsche Buchstabenzuordnung, kurze Läufe
# ----------------------------------------------------------------------
def _identitaets_cmap() -> bytes:
    """ToUnicode-CMap, die jede Glyphennummer als Unicode ausgibt (Erzeugerfehler "Glyph-ID statt Unicode")."""
    bereiche = "\n".join(f"<{i:02X}00> <{i:02X}FF> <{i:02X}00>" for i in range(16))
    return (f"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            f"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            f"/CMapName /Adobe-Identity-UCS def /CMapType 2 def\n"
            f"1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
            f"16 beginbfrange\n{bereiche}\nendbfrange\n"
            f"endcmap CMapName currentdict /CMap defineresource pop end end").encode("ascii")


def _caesar(text: str, k: int = 3) -> str:
    return "".join(chr(97 + (ord(c) - 97 + k) % 26) if "a" <= c <= "z" else
                   chr(65 + (ord(c) - 65 + k) % 26) if "A" <= c <= "Z" else c for c in text)


def brief_mit_eigener_schrift(zeilen_eigen, zuordnung):
    """Brief, dessen Zeilen `zeilen_eigen` (Indizes in BRIEF) in einer eingebetteten TrueType-Schrift stehen; deren
    ToUnicode wird verdorben: "strom" = Identitäts-CMap, "name" = /ToUnicode /Identity-H, "caesar" = Buchstabe ->
    Buchstabe um 3 verschoben. Alle übrigen Zeilen in Helvetica (lesbar)."""
    schrift = schrift_mit_zeichen("Mußäöü€")
    if schrift is None:
        pytest.skip("keine TrueType-Schrift mit Umlauten gefunden")
    doc = fitz.open()
    s = doc.new_page()
    for i, z in enumerate(BRIEF):
        if not z:
            continue
        if i in zeilen_eigen:
            s.insert_text((72, 90 + i * 16), z, fontsize=11, fontname="tt", fontfile=str(schrift))
        else:
            s.insert_text((72, 90 + i * 16), z, fontsize=11)
    doc = fitz.open("pdf", doc.tobytes(garbage=3))
    for f in doc.get_page_fonts(0):
        if f[4] != "tt":
            continue
        art, wert = doc.xref_get_key(f[0], "ToUnicode")
        if zuordnung == "name":
            doc.xref_set_key(f[0], "ToUnicode", "/Identity-H")
        elif zuordnung == "strom":
            doc.update_stream(int(wert.split()[0]), _identitaets_cmap())
        else:
            tu = int(wert.split()[0])
            cmap = doc.xref_stream(tu).decode("latin-1")
            gid_zu_unicode = {}
            for zeile in cmap.splitlines():                 # bfchar <gid> <unicode> und bfrange aufschlüsseln
                m = re.fullmatch(r"\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*", zeile)
                if m:
                    gid_zu_unicode[int(m.group(1), 16)] = int(m.group(2), 16)
                m = re.fullmatch(r"\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*", zeile)
                if m:
                    a, b, u = (int(g, 16) for g in m.groups())
                    gid_zu_unicode.update({a + k: u + k for k in range(b - a + 1)})
            eintraege = [f"<{g:04X}> <{ord(_caesar(chr(u))):04X}>" for g, u in sorted(gid_zu_unicode.items())]
            neu = ("/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
                   "1 begincodespacerange <0000> <FFFF> endcodespacerange\n")
            for i in range(0, len(eintraege), 100):
                teil = eintraege[i:i + 100]
                neu += f"{len(teil)} beginbfchar\n" + "\n".join(teil) + "\nendbfchar\n"
            neu += "endcmap CMapName currentdict /CMap defineresource pop end end"
            doc.update_stream(tu, neu.encode("ascii"))
    return fitz.open("pdf", doc.tobytes(garbage=3))


ALLE_ZEILEN = set(range(len(BRIEF)))
ADRESSBLOCK = {1, 2, 3, 4}


def textebene(seite, rect=None) -> str:
    """Text der Seite (oder des Rechtecks) mit NBSP als Leerzeichen: Windows-Schriften (z. B. Segoe UI) legen
    Leerzeichen und NBSP auf eine Glyphe, die Textebene liefert dann "Pda\\xa0Pxvwhupdqq" statt "Pda Pxvwhupdqq"."""
    text = seite.get_text() if rect is None else seite.get_textbox(rect)
    return text.replace("\xa0", " ")


def zeilen_lesbar(seite, zeilen) -> bool:
    """Liefert die Textebene die Zeilen `zeilen` des Briefs richtig (dann gibt es nichts zu prüfen)?"""
    return any(BRIEF[i] and BRIEF[i] in textebene(seite, fitz.Rect(60, 90 + i * 16 - 12, 560, 90 + i * 16 + 4))
               for i in zeilen)


@pytest.mark.parametrize("zuordnung", ["strom", "name"])
@pytest.mark.parametrize("zeilen", [ALLE_ZEILEN, ADRESSBLOCK, {2}], ids=["ganz", "adresse", "name"])
def test_glyphennummern_als_unicode_werden_erkannt(zuordnung, zeilen):
    """R-02 (Runde 2): Identitäts-ToUnicode bzw. /ToUnicode /Identity-H – beim Kopieren erscheint "0XVWHU" statt
    "Muster". Ganze Seite 0,23 seltsame Zeichen, Adressblock 0,22, fetter Name 1 von 14: alles galt als lesbar,
    Name, Anschrift und IBAN blieben ohne jede Meldung stehen. Jetzt: Seite per OCR, Meldung TEXTEBENE_UNLESBAR."""
    doc = brief_mit_eigener_schrift(zeilen, zuordnung)
    seite = doc[0]
    if zeilen_lesbar(seite, zeilen):
        pytest.skip("diese PyMuPDF-Version stellt die Zuordnung selbst wieder her")
    pruefung = ocr.seiten_pruefung(seite)
    assert pruefung.modus == "seite", pruefung
    assert any(m["code"] == "TEXTEBENE_UNLESBAR" for m in pruefung.meldungen)
    assert sm.unlesbare_schriften(seite)
    assert "Helvetica" not in sm.unlesbare_schriften(seite)


def test_falsche_buchstabenzuordnung_einer_ganzen_seite_wird_erkannt():
    """R-02 (Runde 2, Zusatzpunkt): Buchstaben auf Buchstaben verschoben ("Pxvwhu Yhuvlfkhuxqj DJ") – keine
    seltsamen Zeichen, keine Sonderzeichen. Die Buchstabenpaare verraten den Salat auch ohne OCR."""
    doc = brief_mit_eigener_schrift(ALLE_ZEILEN, "caesar")
    seite = doc[0]
    assert "Mustermann" not in seite.get_text() and "Pxvwhupdqq" in seite.get_text()
    befund = ocr.textebene_pruefen(seite)
    assert befund.unlesbar
    assert ocr.seiten_pruefung(seite).modus == "seite"


@braucht_ocr
@pytest.mark.parametrize("zeilen", [ADRESSBLOCK, {2}], ids=["adresse", "name"])
def test_falsche_buchstabenzuordnung_kurzer_laeufe_entscheidet_die_ocr_probe(zeilen):
    """Kurze Läufe (nur Anschrift, nur Name) sind statistisch nicht sicher – die OCR-Probe der Schrift liest
    "Max Mustermann", die Textebene sagt "Pda Pxvwhupdqq": unlesbar."""
    doc = brief_mit_eigener_schrift(zeilen, "caesar")
    seite = doc[0]
    assert not zeilen_lesbar(seite, zeilen) and "Pda Pxvwhupdqq" in textebene(seite)
    befund = ocr.textebene_pruefen(seite)
    assert befund.unlesbar and "Helvetica" not in befund.unlesbar
    assert ocr.seiten_pruefung(seite).modus == "seite"


@pytest.mark.parametrize("text", [
    "Sehr geehrter Herr Mustermann, wir bestätigen den Eingang Ihrer Unterlagen.",
    "Max Mustermann Hauptstraße 12 10115 Berlin", "Frau Urszula Pawłowska", "Kleine Bergstraße 45 b 49074 Osnabrück",
    "Gemeinschaftspraxis Dr. med. Hatice Çakir", "Versicherungsschein-Nr.: KH-2012-627583"])
def test_paar_bewertung_natuerlicher_text(text):
    wert, paare = ocr.paar_bewertung(text)
    assert paare >= ocr.PAAR_MIN and wert >= ocr.PAAR_SCHWELLE, (text, wert)


@pytest.mark.parametrize("text", ["Pda Pxvwhupdqq", "Khuuq Pda Pxvwhupdqq Kdxswvwudßh", "0D[ 0XVWHUPDQQ",
                                  "+HUUQ 0D[ 0XVWHUPDQQ +DXSWVWUD¡H", _caesar("Erika Beispiel Lindenweg Köln", 7)])
def test_paar_bewertung_salat(text):
    wert, paare = ocr.paar_bewertung(text)
    assert paare >= ocr.PAAR_MIN and wert < ocr.PAAR_SCHWELLE, (text, wert)


@braucht_ocr
def test_verdaechtige_aber_lesbare_schrift_bleibt_in_der_textebene():
    """Gegenprobe: maschinenlesbare Ausweiszeile (Buchstabenpaare wie Salat) – die OCR-Probe liest dasselbe wie die
    Textebene, die Seite bleibt eine Textseite ohne Meldung."""
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s)
    s.insert_text((72, 700), "IDD<<T01XHC7WF8<<<<<<<<<<<<<<<", fontsize=12, fontname="cour")
    s.insert_text((72, 716), "7901298<3407XKZ<<<<<<<<<<<<<<", fontsize=12, fontname="cour")
    befund = ocr.textebene_pruefen(doc[0])
    assert befund.unlesbar == [] and befund.geprueft == ("Courier",)
    pruefung = ocr.seiten_pruefung(doc[0])
    assert pruefung.modus == "nein" and not pruefung.meldungen


@braucht_ocr
def test_glyphennummern_im_adressblock_verlassen_die_ausgabe_nicht(tmp_path):
    """R-02 Ende zu Ende: Analyse liest die Anschrift per OCR (Meldung TEXTEBENE_UNLESBAR), die Schwärzung entfernt
    Name und Straße auch aus den Glyphen der kaputten Schrift."""
    from anonymisierer import analyse
    doc = brief_mit_eigener_schrift(ADRESSBLOCK, "name")
    pfad = tmp_path / "adresse.pdf"
    doc.save(pfad)
    with ocr.OcrDienst(prozesse=1) as dienst:
        erg = analyse.analysiere_pdf(pfad, {"namen", "strasse", "plzort", "iban"}, [], [], ocr=dienst)
        assert any(m["code"] == "TEXTEBENE_UNLESBAR" for m in erg["meldungen"]), erg["meldungen"]
        assert "Hauptstraße" in erg["modell"].text or "Hauptstrasse" in erg["modell"].text
        funde = NAMENSFUNDE + [fund("Hauptstraße 12", "[ADRESSE]", "strasse")]
        e = schwaerze_pdf(pfad, funde, ocr=dienst, ocr_cache=erg.get("ocr_cache"), modell=erg.get("modell"),
                          ziel_ordner=tmp_path / "aus")
        assert e["ausgabe"] is not None, e
        kontrolle = dienst.text(e["ausgabe"], 0, winkel=0)
    assert "Mustermann" not in kontrolle and "Hauptstra" not in kontrolle, kontrolle
    assert "Commerzbank" in kontrolle


# ----------------------------------------------------------------------
# R-03: Vektortext ohne Kurven, je Zeile ein Pfad, Strichschrift; Laufzeit bei Symbolrastern
# ----------------------------------------------------------------------
def _bezier_punkte(p0, p1, p2, p3, n=4):
    """Bézierkurve als Linienzug aus n Stücken (wie ein Druckertreiber oder "In Polygon umwandeln")."""
    aus = []
    for k in range(1, n + 1):
        t = k / n
        u = 1 - t
        aus.append(fitz.Point(u ** 3 * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t ** 3 * p3.x,
                              u ** 3 * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t ** 3 * p3.y))
    return aus


def vektor_brief(art, zeilen=BRIEF, y=90, seite=None, seitenzahl=True):
    """Brief als Vektorpfade auf einer neuen (oder gegebenen) Seite: "polygon" = jede Glyphe ein gefüllter Linienzug
    ohne Kurven, "zeile" = alle Glyphen einer Zeile in EINEM gefüllten Pfad, "block" = alle Glyphen in EINEM
    gefüllten Pfad (zusammengesetzter Umriss, "In Pfade umwandeln"), "strich" = Umrisse nur gestrichen.
    Dazu echter Text "Seite 1 von 1" (textarme Seite)."""
    quelle = fitz.open()
    q = quelle.new_page()
    brief_einfuegen(q, zeilen, y=y)
    pfade = fitz.open("pdf", fitz.open("svg", q.get_svg_image(text_as_path=True).encode()).convert_to_pdf())[0]
    zeichnungen = pfade.get_drawings()
    doc = None
    if seite is None:
        doc = fitz.open()
        seite = doc.new_page()
    gruppen: dict = {}
    for d in zeichnungen:
        schluessel = {"zeile": round(d["rect"].y1 / 4), "block": 0}.get(art, id(d))
        gruppen.setdefault(schluessel, []).append(d)
    for _, ds in sorted(gruppen.items()):
        form = seite.new_shape()
        for d in ds:
            for it in d["items"]:
                if it[0] == "l":
                    form.draw_line(it[1], it[2])
                elif it[0] == "c":
                    if art in ("zeile", "block"):
                        form.draw_bezier(it[1], it[2], it[3], it[4])
                    else:
                        start = it[1]
                        for p in _bezier_punkte(*it[1:5]):
                            form.draw_line(start, p)
                            start = p
                elif it[0] == "re":
                    form.draw_rect(it[1])
                elif it[0] == "qu":
                    form.draw_quad(it[1])
        if art == "strich":
            form.finish(color=(0, 0, 0), fill=None, width=0.5)
        else:
            form.finish(fill=(0, 0, 0), color=None, even_odd=ds[0].get("even_odd", False), closePath=True)
        form.commit()
    if seitenzahl:
        seite.insert_text((450, 820), "Seite 1 von 1", fontsize=9)
    return doc


@pytest.mark.parametrize("art", ["polygon", "zeile", "block", "strich"])
def test_vektortext_jeder_form_mit_seitenzahl_wird_per_ocr_gelesen(art):
    """R-03 (Runde 2): Glyphen als Linienzüge (Druckertreiber, LibreOffice "In Polygon umwandeln"), je Zeile ein
    Umrisspfad (breiter als 60 pt, nur 20 Pfade), die ganze Seite als EIN Umrisspfad (über 40 pt hoch) oder
    gestrichene Strichschrift (CAD) – plus echte Seitenzahl. Vorher: keine OCR, 0 Funde, keine Meldung, die
    Oberfläche meldete "keine personenbezogenen Daten"."""
    doc = vektor_brief(art)
    if art == "block":
        assert len(doc[0].get_drawings()) == 1 and doc[0].get_drawings()[0]["rect"].height > 40
    pruefung = ocr.seiten_pruefung(doc[0])
    assert pruefung.modus == "seite", pruefung
    assert pruefung.vektor
    assert any(m["code"] == "OCR_GELESEN" and "Grafik" in m["text"] for m in pruefung.meldungen)


@pytest.mark.parametrize("art", ["polygon", "block"])
def test_vektor_adressblock_neben_fliesstext_wird_als_bereich_gelesen(art):
    """Anschrift als Polygon-Glyphen bzw. als EIN zusammengesetzter Umriss (54 pt hoch), darunter über 200 echte
    Zeichen Fließtext: der Anschriftsbereich wird wie ein Bildbereich gelesen (vorher: modus "nein", 0 Funde)."""
    doc = fitz.open()
    seite = doc.new_page()
    vektor_brief(art, zeilen=["Herrn", NAME, "Hauptstraße 12", "10115 Berlin"], seite=seite, seitenzahl=False)
    brief_einfuegen(seite, BRIEF[6:] * 3, y=300)
    pruefung = ocr.seiten_pruefung(seite)
    assert pruefung.modus == "bilder", pruefung
    anschrift = fitz.Rect(70, 80, 200, 150)
    assert any(r.intersects(anschrift) for r in pruefung.bereiche) and all(r.y1 < 300 for r in pruefung.bereiche)


def test_grosse_gestrichene_zeichnung_ist_kein_vektortext():
    """Gegenprobe zu "block": eine technische Zeichnung als EIN großer gestrichener Pfad mit vielen Kreisen und Bögen
    verschiedener Größe (Räder, Bolzen) neben echtem Text ist kein Text als Grafik – Strichschrift steht je Glyphe
    oder Zeile in kleinen Pfaden (gemessen an der Zeichnung einer fremden Broschüre)."""
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s, BRIEF[6:] * 2, y=80)
    form = s.new_shape()
    form.draw_rect(fitz.Rect(80, 400, 520, 700))
    for i in range(60):
        form.draw_circle((110 + (i % 12) * 17, 430 + (i // 12) * 17), 2 + (i * 5) % 11 * 0.5)
    form.finish(color=(0, 0, 0), fill=None, width=0.6)
    form.commit()
    assert len(s.get_drawings()) == 1 and s.get_drawings()[0]["rect"].height > 40
    # Vorbedingung: die Kreise bilden eine Gruppe mit der Größenvielfalt von Text
    formen = ocr._glyphenformen(s.get_drawings()[0])
    assert max(len(g) for g in ocr._nahe_gruppen(formen, ocr.VEKTORTEXT_ABSTAND_PT)) >= ocr.VEKTORTEXT_STARK_GRUPPE
    assert len({(round(2 * (f[2] - f[0])), round(2 * (f[3] - f[1]))) for f in formen}) >= ocr.VEKTORTEXT_VIELFALT
    assert ocr.vektortext_bereiche(s) == []
    assert ocr.seiten_pruefung(s).modus == "nein"


def test_diagramm_als_ein_gefuellter_pfad_ist_kein_vektortext():
    """Gegenprobe zu "block": ein Blasendiagramm (Kreise verschiedener Größe, verstreut) als EIN gefüllter Pfad hat
    die Größenvielfalt von Text, aber keine gemeinsamen Grundlinien (gemessen: Diagramme mit Markern und
    Fehlerbalken einer fremden Fachzeitschrift 0,00-0,67, Textblöcke 0,87-1,00)."""
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s, BRIEF[6:] * 2, y=80)
    form = s.new_shape()
    for i in range(60):
        x = 100 + (i * 23) % 160
        y = 420 + (i * 31) % 120 + 3 * math.sin(i)
        form.draw_circle((x, y), 2 + (i * 7) % 15 * 0.5)
    form.finish(fill=(0.2, 0.3, 0.8), color=None)
    form.commit()
    assert len(s.get_drawings()) == 1 and s.get_drawings()[0]["rect"].height > 40
    formen = ocr._glyphenformen(s.get_drawings()[0])
    # Vorbedingungen: eine zusammenhängende Gruppe mit der Größenvielfalt von Text – nur die Grundlinien fehlen
    assert max(len(g) for g in ocr._nahe_gruppen(formen, ocr.VEKTORTEXT_ABSTAND_PT)) >= ocr.VEKTORTEXT_STARK_GRUPPE
    assert len({(round(2 * (f[2] - f[0])), round(2 * (f[3] - f[1]))) for f in formen}) >= ocr.VEKTORTEXT_VIELFALT
    assert ocr._grundlinien_anteil(formen) < ocr.VEKTORTEXT_GRUNDLINIE
    assert ocr.vektortext_bereiche(s) == []
    assert ocr.seiten_pruefung(s).modus == "nein"


def symbolraster(breite, hoehe, abstand=21.0, radius=2.0):
    doc = fitz.open()
    s = doc.new_page(width=breite, height=hoehe)
    form = s.new_shape()
    y = 60.0
    while y < hoehe - 20:
        x = 30.0
        while x < breite - 20:
            form.draw_circle((x, y), radius)
            x += abstand
        y += abstand
    form.finish(fill=(0, 0.5, 0), color=None)
    form.commit()
    s.insert_text((30, 30), f"Lageplan Bauherr {NAME}, Hauptstraße 12, 10115 Berlin", fontsize=10)
    s.insert_text((30, 45), "Hydranten und Bäume laut Bestand", fontsize=10)
    return doc


def test_symbolraster_ist_kein_vektortext_und_schnell():
    """R-03/Laufzeit: Kreise im Abstand von 21 pt (Baum-, Hydranten-, Leuchtenplan). vektortext_bereiche zählte je
    Bereich alle Pfade – A2 mit 4028 Symbolen 56-84 s je Aufruf, A4 mit 900 Symbolen 3,5 s. Jetzt linear."""
    import time
    for breite, hoehe in ((595, 842), (1191, 1684)):
        doc = symbolraster(breite, hoehe)
        start = time.perf_counter()
        assert ocr.vektortext_bereiche(doc[0]) == []
        assert ocr.seiten_pruefung(doc[0]).modus == "nein"
        assert time.perf_counter() - start < 5.0


def test_dichtes_symbolraster_ist_kein_vektortext():
    """Gleich große Symbole, die zu einem Bereich zusammenwachsen (Streudiagramm, Punktraster), sind kein Text."""
    doc = symbolraster(595, 842, abstand=8.0)
    assert ocr.vektortext_bereiche(doc[0]) == []


def test_diagramm_mit_wenigen_markerformen_ist_kein_vektortext():
    """Liniendiagramm mit Markern in drei Formen (Quadrat, Dreieck, Kreis) und Fehlerbalken: gemessen an einer
    fremden Fachzeitschrift 1-4 verschiedene Größen je Gruppe, Text 7-32."""
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s, BRIEF[6:] * 3, y=80)
    form = s.new_shape()
    for i in range(30):
        x, y = 100 + 9 * i, 600 - 3 * i
        if i % 3 == 0:
            form.draw_rect(fitz.Rect(x - 2, y - 2, x + 2, y + 2))
        elif i % 3 == 1:
            form.draw_polyline([(x - 2.5, y + 2), (x, y - 2.5), (x + 2.5, y + 2), (x - 2.5, y + 2)])
        else:
            form.draw_circle((x, y), 2.2)
        form.draw_line((x, y - 6), (x + 0.6, y + 6))
    form.finish(color=(0.8, 0, 0), fill=(0.8, 0, 0), width=0.5)
    form.commit()
    assert ocr.vektortext_bereiche(s) == []
    assert ocr.seiten_pruefung(s).modus == "nein"


def test_strukturbaum_entfernen():
    """MuPDF 1.28 hängt beim Rendern mancher Seiten mit Zyklus im Strukturbaum (gemessen über 10 Minuten; Textauszug
    unberührt). OCR-Arbeiter, OCR-Probe und "Seite als Bild" rendern deshalb ohne Strukturbaum."""
    doc = fitz.open()
    brief_einfuegen(doc.new_page())
    doc = fitz.open("pdf", doc.tobytes())
    wurzel = doc.get_new_xref()
    doc.update_object(wurzel, "<< /Type /StructTreeRoot /K [] >>")
    doc.xref_set_key(doc.pdf_catalog(), "StructTreeRoot", f"{wurzel} 0 R")
    ocr.strukturbaum_entfernen(doc)
    assert doc.xref_get_key(doc.pdf_catalog(), "StructTreeRoot")[0] == "null"
    ocr.strukturbaum_entfernen(doc)                      # zweimal schadet nicht


def test_ocr_probe_rendert_eine_kopie_ohne_strukturbaum(monkeypatch):
    doc = brief_mit_eigener_schrift({2}, "name")
    wurzel = doc.get_new_xref()
    doc.update_object(wurzel, "<< /Type /StructTreeRoot /K [] >>")
    doc.xref_set_key(doc.pdf_catalog(), "StructTreeRoot", f"{wurzel} 0 R")
    gesehen = []

    def lesen(seite, *a):
        gesehen.append(seite)
        return ""
    monkeypatch.setattr(ocr, "_probe_lesen", lesen)
    ocr._PROBE_ERGEBNISSE.clear()
    ocr.textebene_pruefen(doc[0])
    assert gesehen and all(s.parent is not doc for s in gesehen)
    assert doc.xref_get_key(doc.pdf_catalog(), "StructTreeRoot")[0] == "xref"   # das geprüfte Dokument bleibt
    ocr._PROBE_ERGEBNISSE.clear()


def test_nahe_gruppen_linear():
    import random
    import time
    zufall = random.Random(3)
    rechtecke = []
    for _ in range(20000):
        x, y = zufall.uniform(0, 3000), zufall.uniform(0, 3000)
        rechtecke.append((x, y, x + 4, y + 4))
    start = time.perf_counter()
    gruppen = ocr._nahe_gruppen(rechtecke, ocr.VEKTORTEXT_ABSTAND_PT)
    assert time.perf_counter() - start < 5.0
    assert sum(len(g) for g in gruppen) == len(rechtecke)
    # zwei Rechtecke mit 10 pt Abstand gehören zusammen, mit 40 pt nicht
    assert len(ocr._nahe_gruppen([(0, 0, 5, 5), (15, 0, 20, 5)], 12.0)) == 1
    assert len(ocr._nahe_gruppen([(0, 0, 5, 5), (45, 0, 50, 5)], 12.0)) == 2


def test_seitenpruefung_laeuft_im_modellaufbau_je_seite_einmal(monkeypatch):
    """Befund R-03/Laufzeit: Analyse und Schwärzung fragten jede Seite 2- bis 4-mal (Entscheidung, Bildbereiche,
    unlesbare Schriften) – teuer bei großen Plänen."""
    aufrufe = []
    original = ocr._seiten_pruefung

    def zaehlen(seite):
        aufrufe.append(seite.number)
        return original(seite)
    monkeypatch.setattr(ocr, "_seiten_pruefung", zaehlen)
    doc = fitz.open()
    for _ in range(3):
        s = doc.new_page()
        brief_einfuegen(s)
        s.insert_image(fitz.Rect(300, 600, 500, 760), pixmap=fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 30), False))

    class Dienst:
        def vorab(self, *a, **k):
            return 0

        def ergebnis(self, pfad, nr, dpi=300, clip=None, winkel=None):
            return {"woerter": [], "winkel": 0}
    sm.dokument_aufbauen(doc, "x.pdf", ocr=Dienst())
    assert sorted(aufrufe) == [0, 1, 2]


def test_abbruch_wirkt_schon_in_der_vorab_pruefung():
    import threading
    doc = fitz.open()
    for _ in range(3):
        brief_einfuegen(doc.new_page())
    abbruch = threading.Event()
    abbruch.set()

    class Dienst:
        def vorab(self, *a, **k):
            raise AssertionError("nach dem Abbruch darf nichts mehr eingereiht werden")
    with pytest.raises(sm.Abgebrochen):
        sm.dokument_aufbauen(doc, "x.pdf", ocr=Dienst(), abbruch=abbruch)


@braucht_ocr
@pytest.mark.parametrize("art", ["polygon", "block", "strich"])
def test_vektortext_verlaesst_die_ausgabe_nicht(tmp_path, art):
    """R-03 Ende zu Ende: Die Analyse findet die IBAN im Vektortext (per OCR), die Schwärzung entfernt Name und
    IBAN aus den Pfaden (Seite als Scan geschwärzt)."""
    from anonymisierer import analyse
    pfad = tmp_path / f"vektor_{art}.pdf"
    vektor_brief(art).save(pfad)
    with ocr.OcrDienst(prozesse=1) as dienst:
        erg = analyse.analysiere_pdf(pfad, {"iban"}, [], [], ocr=dienst)
        assert erg["ocr_seiten"] == 1
        assert any(f["kategorie"] == "iban" for f in erg["funde"]), erg["funde"]
        e = schwaerze_pdf(pfad, NAMENSFUNDE, ocr=dienst, ocr_cache=erg.get("ocr_cache"), modell=erg.get("modell"),
                          ziel_ordner=tmp_path / "aus")
        assert e["ausgabe"] is not None, e
        kontrolle = dienst.text(e["ausgabe"], 0, winkel=0)
    assert "Mustermann" not in kontrolle and "3704" not in kontrolle, kontrolle
    assert "Commerzbank" in kontrolle


# ----------------------------------------------------------------------
# R-06 (Runde 2): Auflösung großer Seiten, Speicherfehler, Speicher je Auftrag
# ----------------------------------------------------------------------
def plan_mit_unterlage(unterlage_px=(400, 560), schriftgroesse=11):
    """A1-Plan (1684 x 2384 pt): Rasterunterlage über die ganze Seite (Standard 400 x 560 px = 17 dpi), Legende als
    echter Text (über 200 Zeichen) und ein Schriftfeld mit Personendaten als Kurven."""
    doc = fitz.open()
    s = doc.new_page(width=1684, height=2384)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, *unterlage_px), False)
    pix.clear_with(235)
    s.insert_image(s.rect, pixmap=pix)
    for i in range(8):
        s.insert_text((100, 200 + 20 * i),
                      f"Legende {i + 1}: Bestand Mauerwerk, Planung Stahlbeton, Abbruch gestrichelt", fontsize=12)
    quelle = fitz.open()
    q = quelle.new_page(width=1684, height=2384)
    for i, z in enumerate([f"Bauherr: {NAME}", "Hauptstraße 12, 10115 Berlin", f"IBAN {IBAN}"]):
        q.insert_text((1100, 2100 + i * schriftgroesse * 1.5), z, fontsize=schriftgroesse)
    pfade = fitz.open("pdf", fitz.open("svg", q.get_svg_image(text_as_path=True).encode()).convert_to_pdf())
    s.show_pdf_page(s.rect, pfade, 0)
    return doc


@pytest.mark.parametrize("unterlage_px,groesse", [((400, 560), 11), ((4, 4), 11), ((1170, 1656), 8)],
                         ids=["17dpi", "winzbild", "50dpi_8pt"])
def test_render_dpi_schriftfeld_ueber_grober_unterlage_wird_voll_gelesen(unterlage_px, groesse):
    """R-06 (Runde 2): Liegt Text oder ein Schriftfeld als Kurven über einer groben Rasterunterlage, richtete
    render_dpi die Lese-Auflösung nach dem Bild (34, 1 bzw. 72 dpi) – die OCR las 0 Wörter, 0 Funde. Jetzt: die
    höchste Auflösung, die der Speicher erlaubt (A1: 227 dpi)."""
    doc = plan_mit_unterlage(unterlage_px, groesse)
    seite = doc[0]
    dpi, grund = ocr.render_aufloesung(seite, None, 300)
    assert grund == "speicher" and dpi == int(ocr.dpi_grenze(seite)), (dpi, grund)
    assert dpi >= 200


def test_render_dpi_reines_foto_bleibt_bei_seiner_aufloesung():
    doc = fotoseite(4032, 3024, 4032, 3024)
    assert ocr.render_aufloesung(doc[0], None, 300) == (72, "bild")
    doc = fotoseite(8064, 6048, 8064, 6048)          # 48 MP: die Grenze (65 dpi) liegt knapp unter den 72 dpi des Bilds
    dpi, grund = ocr.render_aufloesung(doc[0], None, 300)
    assert grund == "bild" and 60 <= dpi <= 72


@pytest.mark.parametrize("roh,code,muss,darf_nicht", [
    ({"aufloesung": 72, "angefragt": 300, "aufloesung_grund": "bild"}, "OCR_GELESEN", "Auflösung des Bilds",
     "Arbeitsspeicher"),
    ({"aufloesung": 60, "angefragt": 300, "aufloesung_grund": "speicher"}, "OCR_FEHLER", "Bitte prüfen", None),
    ({"aufloesung": 160, "angefragt": 300, "aufloesung_grund": "speicher"}, "OCR_GELESEN", "Arbeitsspeicher", None),
])
def test_meldung_zur_lese_aufloesung_nennt_den_echten_grund(roh, code, muss, darf_nicht):
    """Die Meldung nannte immer "damit der Arbeitsspeicher reicht" und war nur ein Hinweis – auch bei 1-49 dpi."""
    dienst = ocr.OcrDienst(prozesse=1)
    try:
        dienst.sprach_warnung = None
        e = dienst._ergebnis_aufbereiten(dict(roh, woerter=[], winkel=0, seitengroesse=(1684, 2384)), 0, None, None)
    finally:
        dienst.schliessen()
    treffer = [m for m in e["meldungen"] if m["code"] == code]
    assert treffer and muss in treffer[0]["text"], e["meldungen"]
    if darf_nicht:
        assert darf_nicht not in treffer[0]["text"]
    if code == "OCR_FEHLER":
        assert treffer[0]["art"] == "warnung"


def test_ungelesener_vektortext_auf_textseite_wird_gewarnt():
    """Liest die OCR aus einem Bereich mit Text als Grafik nichts, ist er ungeprüft – Warnung statt nur des Hinweises
    "per Texterkennung gelesen"."""
    doc = fitz.open()
    seite = doc.new_page()
    vektor_brief("polygon", zeilen=["Herrn", NAME, "Hauptstraße 12", "10115 Berlin"], seite=seite, seitenzahl=False)
    brief_einfuegen(seite, BRIEF[6:] * 3, y=300)

    class Stumm:
        def vorab(self, *a, **k):
            return 0

        def ergebnis(self, pfad, nr, dpi=300, clip=None, winkel=None):
            return {"woerter": [], "winkel": 0}
    meldungen = []
    sm.dokument_aufbauen(doc, "x.pdf", ocr=Stumm(), meldungen=meldungen)
    assert any(m["code"] == "OCR_FEHLER" and "Text als Grafik" in m["text"] for m in meldungen), meldungen


class _FzErrorSystem(Exception):
    pass


class _FzErrorGeneric(Exception):
    pass


class _FzErrorLimit(Exception):
    pass


@pytest.mark.parametrize("fehler,erwartet", [
    (MemoryError(), True),
    (_FzErrorSystem("code=2: malloc (117343056 bytes) failed"), True),
    (_FzErrorGeneric("code=1: Director error: <class 'MemoryError'>: Traceback (most recent call last): "
                     "/x/site-packages/pymupdf/__init__.py:24360:write(): data = mupdf.raw"), True),
    (_FzErrorLimit("code=5: Overly large image"), True),
    (_FzErrorSystem("code=2: cannot open x.pdf: No such file or directory"), False),
    (_FzErrorLimit("code=5: exception stack overflow!"), False),
    (RuntimeError("code=7: Tesseract initialisation failed"), False),
])
def test_speicherfehler_erkennt_echte_engpaesse(fehler, erwartet):
    """R-06 (Runde 2): Echte Engpässe kommen als FzErrorSystem "malloc failed" oder als MemoryError im
    Schreibrückruf ("Director error") – beides blieb unerkannt, der Rückfall auf halbe Auflösung griff nie."""
    assert ocr._speicherfehler(fehler) is erwartet


def test_arbeiter_wiederholt_bei_malloc_fehler_mit_halber_aufloesung(monkeypatch):
    aufrufe = []

    def lesen(*a, verkleinern=1.0, **k):
        aufrufe.append(verkleinern)
        if verkleinern == 1.0:
            raise _FzErrorSystem("code=2: malloc (119246400 bytes) failed")
        return {"woerter": [], "winkel": 0}
    monkeypatch.setattr(ocr, "_ocr_lesen", lesen)
    assert ocr._ocr_worker("x.pdf", 0, 300, None, "deu", None)["speicher_knapp"] is True
    assert aufrufe == [1.0, 0.5]


def test_arbeiter_meldet_fehler_ohne_traceback_und_pfade(monkeypatch):
    def lesen(*a, **k):
        raise _FzErrorGeneric("code=1: Director error: <class 'ValueError'>: Traceback (most recent call last):\n"
                              "    C:\\Users\\Erika\\AppData\\Local\\Programs\\pdf\\pymupdf\\__init__.py:24360:write()")
    monkeypatch.setattr(ocr, "_ocr_lesen", lesen)
    with pytest.raises(RuntimeError) as info:
        ocr._ocr_worker("x.pdf", 0, 300, None, "deu", None)
    text = str(info.value)
    assert "Traceback" not in text and "AppData" not in text and "Erika" not in text and "__init__" not in text, text


@pytest.mark.parametrize("dpi_vorher,erwartet", [(120, 60), (65, 50), (43, None)])
def test_rueckfall_senkt_die_aufloesung_nur(tmp_path, monkeypatch, dpi_vorher, erwartet):
    """Halbe Auflösung, mindestens 50 dpi – aber nie höher als zuvor (vorher wurden aus 43 dpi 50)."""
    pfad = tmp_path / "leer.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pfad)
    monkeypatch.setattr(ocr, "render_aufloesung", lambda seite, clip, dpi: (dpi_vorher, "speicher"))
    gelesen = []

    def durchlauf(seite, dpi, *a, **k):
        gelesen.append(dpi)
        return []
    monkeypatch.setattr(ocr, "_ocr_durchlauf", durchlauf)
    if erwartet is None:
        with pytest.raises(MemoryError):
            ocr._ocr_lesen(str(pfad), 0, 300, None, "deu", None, verkleinern=0.5)
        assert gelesen == []
    else:
        e = ocr._ocr_lesen(str(pfad), 0, 300, None, "deu", None, verkleinern=0.5)
        assert e["aufloesung"] == erwartet and set(gelesen) == {erwartet}


def test_grosse_auftraege_laufen_nacheinander(tmp_path, monkeypatch):
    """R-06 (Runde 2): Drei Arbeiter lasen je 40 MP gleichzeitig (3,5-3,8 GB). Große Aufträge nehmen jetzt die
    Sperre des Dienstes; kleine nicht."""
    class Sperre:
        def __init__(self):
            self.protokoll = []

        def acquire(self, timeout=None):
            self.protokoll.append("an")
            return True

        def release(self):
            self.protokoll.append("ab")
    sperre = Sperre()
    monkeypatch.setattr(ocr, "_GROSS_SPERRE", sperre)
    monkeypatch.setattr(ocr, "_ocr_durchlauf", lambda *a, **k: [])
    for name, breite, hoehe in (("a4", 595, 842), ("a1", 1684, 2384)):
        doc = fitz.open()
        doc.new_page(width=breite, height=hoehe)
        doc.save(tmp_path / f"{name}.pdf")
    ocr._ocr_lesen(str(tmp_path / "a4.pdf"), 0, 300, None, "deu", None, ausrichtung_pruefen=False)
    assert sperre.protokoll == []
    ocr._ocr_lesen(str(tmp_path / "a1.pdf"), 0, 300, None, "deu", None, ausrichtung_pruefen=False)
    assert sperre.protokoll == ["an", "ab"]


@pytest.mark.skipif(sys.platform == "win32" or not Path("/proc/self/status").exists(),
                    reason="Adressraumgrenze (RLIMIT_AS) und /proc gibt es nur unter Linux")
@braucht_ocr
def test_echter_speichermangel_im_arbeiter_liest_mit_halber_aufloesung(tmp_path):
    """R-06 (Runde 2) mit echtem Speichermangel statt nachgestellter Ausnahme: Der Arbeiter läuft mit einer
    Adressraumgrenze knapp über seinem Grundbedarf; die volle Lesung einer großen Seite scheitert an einer
    Speicheranforderung, die Wiederholung mit halber Auflösung gelingt."""
    import subprocess
    pfad = tmp_path / "gross.pdf"
    doc = fitz.open()
    s = doc.new_page(width=2200, height=2200)
    for i in range(6):
        s.insert_text((150, 300 + 250 * i), f"Versicherungsnehmer {NAME} Zeile {i + 1}", fontsize=70)
    doc.save(pfad)
    skript = tmp_path / "arbeiter.py"
    skript.write_text(
        "import resource, sys\n"
        f"sys.path.insert(0, {str(Path(ocr.__file__).resolve().parent.parent)!r})\n"
        "from anonymisierer import ocr\n"
        "tessdata = ocr._tessdata_finden()\n"
        "ocr._ocr_lesen(sys.argv[1], 0, 72, None, 'deu', tessdata, False)\n"     # Bibliotheken laden
        "with open('/proc/self/status') as f:\n"
        "    vm = [int(z.split()[1]) * 1024 for z in f if z.startswith('VmSize')][0]\n"
        "grenze = vm + 230 * 2**20\n"
        "resource.setrlimit(resource.RLIMIT_AS, (grenze, grenze))\n"
        "e = ocr._ocr_worker(sys.argv[1], 0, 300, None, 'deu', tessdata, False)\n"
        "print('ERGEBNIS', e.get('speicher_knapp'), e['aufloesung'], ' '.join(w[4] for w in e['woerter']))\n",
        encoding="utf-8")
    aus = subprocess.run([sys.executable, str(skript), str(pfad)], capture_output=True, text=True, timeout=600)
    zeile = [z for z in aus.stdout.splitlines() if z.startswith("ERGEBNIS")]
    assert zeile, aus.stdout[-2000:] + aus.stderr[-2000:]
    assert zeile[0].split()[1] == "True" and "Mustermann" in zeile[0], zeile[0]


# ----------------------------------------------------------------------
# R-08 (Runde 2): Seite ohne Fund mit zyklischem Form-XObject und Inhalt außerhalb der CropBox
# ----------------------------------------------------------------------
VERSTECKT = "VERSTECKT: Erika Musterfrau, IBAN DE02 1203 0000 0000 2020 51, Geheimweg 7"


def zyklus_mit_beschnitt(art="selbst", unten=True):
    """Seite 1: Brief mit Funden. Seite 2: kein Fund im sichtbaren Bereich, aber ein zyklisches (art "selbst",
    "paar") bzw. 50-fach verschachteltes (art "tief") Form-XObject und eine Zeile mit Personendaten außerhalb der
    CropBox (unten bzw. rechts)."""
    doc = fitz.open()
    brief_einfuegen(doc.new_page())
    s2 = doc.new_page()
    s2.insert_text((70, 90), "Anlage: Fotodokumentation (keine weiteren Angaben)", fontsize=11)
    if unten:
        s2.insert_text((70, 800), VERSTECKT, fontsize=9)
    else:
        s2.insert_text((320, 400), VERSTECKT, fontsize=7)
    erste = doc.get_new_xref()
    if art == "tief":
        kette = [erste] + [doc.get_new_xref() for _ in range(49)]
        for i, x in enumerate(kette):
            ziel = kette[i + 1] if i + 1 < len(kette) else None
            res = f"/Resources << /XObject << /X1 {ziel} 0 R >> >>" if ziel else ""
            doc.update_object(x, f"<< /Type /XObject /Subtype /Form /BBox [0 0 100 100] {res} >>")
            doc.update_stream(x, b"q 0.99 0 0 0.99 0 0 cm /X1 Do Q" if ziel else b"0 0 5 5 re f")
    elif art == "paar":
        zweite = doc.get_new_xref()
        for a, b in ((erste, zweite), (zweite, erste)):
            doc.update_object(a, f"<< /Type /XObject /Subtype /Form /BBox [0 0 100 100] "
                                 f"/Resources << /XObject << /X1 {b} 0 R >> >> >>")
            doc.update_stream(a, b"q 0.9 0 0 0.9 1 1 cm /X1 Do Q")
    else:
        doc.update_object(erste, f"<< /Type /XObject /Subtype /Form /BBox [0 0 100 100] "
                                 f"/Resources << /XObject << /X1 {erste} 0 R >> >> >>")
        doc.update_stream(erste, b"q 0.9 0 0 0.9 1 1 cm /X1 Do Q")
    c = doc.get_new_xref()
    doc.update_object(c, "<<>>")
    doc.update_stream(c, b"q 1 0 0 1 400 300 cm /X1 Do Q")
    doc.xref_set_key(s2.xref, "Contents", "[" + " ".join(f"{i} 0 R" for i in s2.get_contents()) + f" {c} 0 R]")
    art_res, wert = doc.xref_get_key(s2.xref, "Resources")
    if art_res == "xref":
        doc.xref_set_key(int(wert.split()[0]), "XObject", f"<< /X1 {erste} 0 R >>")
    else:
        doc.xref_set_key(s2.xref, "Resources/XObject", f"<< /X1 {erste} 0 R >>")
    s2.set_cropbox(fitz.Rect(0, 0, 595, 700) if unten else fitz.Rect(0, 0, 300, 842))
    return fitz.open("pdf", doc.tobytes())


def _versteckt_lesbar(pfad) -> bool:
    doc = fitz.open(pfad)
    for s in doc:
        s.set_cropbox(s.mediabox)
        if "Musterfrau" in s.get_text() or "2020 51" in s.get_text():
            return True
    roh = b"".join(doc.xref_stream(x) or b"" for x in range(1, doc.xref_length()) if doc.xref_is_stream(x))
    return b"Musterfrau" in roh


@pytest.mark.parametrize("art,unten", [("selbst", True), ("selbst", False), ("paar", True), ("tief", True)])
def test_beschnitt_einer_zyklischen_seite_ohne_fund_verlaesst_die_ausgabe_nicht(tmp_path, art, unten):
    """R-08 (Runde 2): Der Rückfall "Seite als Bild" griff nur auf Seiten mit Schwärzungen. Auf einer Seite ohne Fund
    scheiterte das Entfernen des Beschnitts an apply_redactions ("exception stack overflow"); es blieb eine Meldung
    der Art "fehler", Status "fertig", und Name und IBAN außerhalb der CropBox blieben für Textprogramme lesbar."""
    pfad = tmp_path / f"zyklus_{art}.pdf"
    zyklus_mit_beschnitt(art, unten).save(pfad)
    assert _versteckt_lesbar(pfad)
    e = schwaerze_pdf(pfad, NAMENSFUNDE, ziel_ordner=tmp_path / "aus")
    assert e["ausgabe"] is not None and e["fehler"] is None, e
    assert not _versteckt_lesbar(e["ausgabe"])
    assert not any(m["art"] == "fehler" for m in e["meldungen"]), e["meldungen"]
    assert "SEITE_ALS_BILD" in codes(e)
    aus = fitz.open(e["ausgabe"])
    assert len(aus) == 2 and aus[1].rect == fitz.open(pfad)[1].rect
    assert "Mustermann" not in aus[0].get_text()


# ----------------------------------------------------------------------
# R-03 (Runde 2): Text in einem Form-XObject innerhalb eines Kachelmusters
# ----------------------------------------------------------------------
def kachelmuster_mit_xobjekt(tiefe=1, auch_direkt=False):
    """Wie kachelmuster_seite, aber das Muster ruft /Fm1 Do auf und der Text steht im Form-XObject (tiefe=2: Fm1 ruft
    Fm2 auf). auch_direkt: die Seite zeichnet Fm1 zusätzlich selbst (dann darf sein Text nicht verschwinden)."""
    doc, _ = kachelmuster_seite()
    s = doc[0]
    fx = [f[0] for f in doc.get_page_fonts(0)][0]
    text = f"BT /F1 11 Tf 2 10 Td (Kunde: {NAME}, IBAN {IBAN}) Tj ET".encode()
    innen = doc.get_new_xref()
    doc.update_object(innen, f"<< /Type /XObject /Subtype /Form /BBox [0 0 420 30] /Resources << /Font << /F1 {fx} 0 R "
                             f">> >> >>")
    doc.update_stream(innen, text)
    fm1 = innen
    if tiefe == 2:
        fm1 = doc.get_new_xref()
        doc.update_object(fm1, f"<< /Type /XObject /Subtype /Form /BBox [0 0 420 30] "
                               f"/Resources << /XObject << /Fm2 {innen} 0 R >> >> >>")
        doc.update_stream(fm1, b"/Fm2 Do")
    pat = int(doc.xref_get_key(s.xref, "Resources/Pattern/P1")[1].split()[0]) \
        if doc.xref_get_key(s.xref, "Resources/Pattern/P1")[0] == "xref" else None
    if pat is None:
        art, w = doc.xref_get_key(s.xref, "Resources")
        pat = int(doc.xref_get_key(int(w.split()[0]), "Pattern/P1")[1].split()[0])
    doc.update_object(pat, f"<< /Type /Pattern /PatternType 1 /PaintType 1 /TilingType 1 /BBox [0 0 420 30] "
                           f"/XStep 420 /YStep 30 /Resources << /XObject << /Fm1 {fm1} 0 R >> >> >>")
    doc.update_stream(pat, b"/Fm1 Do")
    if auch_direkt:
        c = doc.get_new_xref()
        doc.update_object(c, "<<>>")
        doc.update_stream(c, b"q 1 0 0 1 72 600 cm /Fm1 Do Q")
        doc.xref_set_key(s.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in s.get_contents()) + f" {c} 0 R]")
        art, w = doc.xref_get_key(s.xref, "Resources")
        ziel = int(w.split()[0]) if art == "xref" else None
        if ziel:
            doc.xref_set_key(ziel, "XObject", f"<< /Fm1 {fm1} 0 R >>")
        else:
            doc.xref_set_key(s.xref, "Resources/XObject", f"<< /Fm1 {fm1} 0 R >>")
    return fitz.open("pdf", doc.tobytes())


def _rohtext(doc) -> bytes:
    return b"".join(doc.xref_stream(x) or b"" for x in range(1, doc.xref_length()) if doc.xref_is_stream(x))


@pytest.mark.parametrize("tiefe", [1, 2])
def test_text_im_xobjekt_eines_kachelmusters_wird_entfernt(tiefe):
    """R-03 (Runde 2): _muster_text_entfernen nahm nur Musterströme auf – Text in einem Form-XObject, das das Muster
    zeichnet, blieb im Strom (und als angeschnittene Kachelzeilen sichtbar), Status "fertig"."""
    doc = kachelmuster_mit_xobjekt(tiefe)
    seite = doc[0]
    assert b"Mustermann" in _rohtext(doc) and "Mustermann" not in seite.get_text()
    assert ocr.textebene_pruefen(seite).verborgen >= ocr.VERBORGEN_MIN_ZEICHEN
    assert schwaerzung._muster_text_entfernen(doc, seite) >= 1
    assert b"Mustermann" not in _rohtext(doc) and b"3704" not in _rohtext(doc)
    assert "Versicherungsschein" in seite.get_text()           # der übrige Text der Seite bleibt


def test_auch_direkt_gezeichnetes_xobjekt_behaelt_seinen_text():
    doc = kachelmuster_mit_xobjekt(auch_direkt=True)
    seite = doc[0]
    assert "Mustermann" in seite.get_text()                      # die Seite zeigt Fm1 auch selbst
    schwaerzung._muster_text_entfernen(doc, seite)
    assert "Mustermann" in seite.get_text()


@braucht_ocr
def test_text_im_xobjekt_eines_kachelmusters_verlaesst_die_ausgabe_nicht(tmp_path):
    pfad = tmp_path / "muster_xobjekt.pdf"
    kachelmuster_mit_xobjekt(2).save(pfad)
    with ocr.OcrDienst(prozesse=1) as dienst:
        e = schwaerze_pdf(pfad, [fund("Max Mus"), fund(IBAN, "[IBAN]", "iban")], ocr=dienst,
                          ziel_ordner=tmp_path / "aus")
    assert e["ausgabe"] is not None, e
    aus = fitz.open(e["ausgabe"])
    assert b"Mustermann" not in _rohtext(aus) and b"3704" not in _rohtext(aus)
    assert "Mustermann" not in "".join(chr(c[0]) for sp in aus[0].get_texttrace() for c in sp["chars"])


# ----------------------------------------------------------------------
# R-03 (Runde 2): abgeschnittener Text (Beschneidungspfad) ist kein Füllmuster
# ----------------------------------------------------------------------
WERT_LANG = "Erika Musterfrau, IBAN DE02 1203 0000 0000 2020 51"


def brief_mit_langem_feld():
    """Brief mit einem 100 pt breiten Textfeld, dessen Wert nicht hineinpasst (Antragsformular)."""
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s, BRIEF[:6])
    s.insert_text((72, 300), "Abweichender Kontoinhaber:", fontsize=10)
    w = fitz.Widget()
    w.field_name = "kontoinhaber"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(220, 288, 320, 304)
    w.field_value = WERT_LANG
    w.text_fontsize = 9
    s.add_widget(w)
    return fitz.open("pdf", doc.tobytes())


def tabelle_mit_abgeschnittener_zelle(nachbar=True):
    """Tabellenzelle mit Beschneidung (re W n) und überlangem Inhalt; nachbar: der Text der Nachbarzelle liegt dort,
    wohin der abgeschnittene Text reichen würde."""
    doc = fitz.open()
    s = doc.new_page()
    brief_einfuegen(s, BRIEF[:6])
    doc = fitz.open("pdf", doc.tobytes())
    s = doc[0]
    fx = doc.get_new_xref()
    doc.update_object(fx, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    art, w = doc.xref_get_key(s.xref, "Resources")
    if art == "xref":
        doc.xref_set_key(int(w.split()[0]), "Font/FX1", f"{fx} 0 R")
    else:
        doc.xref_set_key(s.xref, "Resources/Font/FX1", f"{fx} 0 R")
    inhalt = (f"q 72 506 120 14 re W n BT /FX1 9 Tf 74 509 Td (Kontoinhaber {WERT_LANG}) Tj ET Q\n".encode()
              + (b"q BT /FX1 9 Tf 200 509 Td (Status: offen) Tj ET Q\n" if nachbar else b""))
    c = doc.get_new_xref()
    doc.update_object(c, "<<>>")
    doc.update_stream(c, inhalt)
    doc.xref_set_key(s.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in s.get_contents()) + f" {c} 0 R]")
    return fitz.open("pdf", doc.tobytes())


def _alle_zeichen(pfad_oder_doc) -> str:
    doc = fitz.open(pfad_oder_doc) if not isinstance(pfad_oder_doc, fitz.Document) else pfad_oder_doc
    return "".join(chr(c[0]) for s in doc for sp in s.get_texttrace() for c in sp["chars"])


@pytest.mark.parametrize("bauen", [brief_mit_langem_feld, tabelle_mit_abgeschnittener_zelle])
def test_abgeschnittener_text_fuehrt_nicht_zur_ocr_und_wird_gewarnt(bauen):
    """R-03 (Runde 2): Die Prüfung auf verborgenen Text traf jeden abgeschnittenen Text – Ganzseiten-OCR, Hinweis
    "z. B. in einem Füllmuster … per Texterkennung gelesen", der abgeschnittene Klartext blieb im Strom. Jetzt: keine
    OCR (sie sieht ihn ohnehin nicht), eine Warnung mit der richtigen Ursache."""
    doc = bauen()
    seite = doc[0]
    sm.dokument_vorbereiten(doc)
    seite = doc[0]
    befund = ocr.textebene_pruefen(seite)
    assert befund.verborgen >= ocr.VERBORGEN_MIN_ZEICHEN and befund.muster is False
    pruefung = ocr.seiten_pruefung(seite)
    assert pruefung.modus == "nein", pruefung
    assert [m["code"] for m in pruefung.meldungen] == ["TEXT_ABGESCHNITTEN"]
    assert pruefung.meldungen[0]["art"] == "warnung" and "Füllmuster" not in pruefung.meldungen[0]["text"]


def test_kachelmuster_bleibt_ein_fall_fuer_die_ocr():
    doc, _ = kachelmuster_seite()
    befund = ocr.textebene_pruefen(doc[0])
    assert befund.muster is True
    pruefung = ocr.seiten_pruefung(doc[0])
    assert pruefung.modus == "seite" and not any(m["code"] == "TEXT_ABGESCHNITTEN" for m in pruefung.meldungen)


@pytest.mark.parametrize("bauen,als_bild", [(brief_mit_langem_feld, False),
                                            (lambda: tabelle_mit_abgeschnittener_zelle(False), False),
                                            (tabelle_mit_abgeschnittener_zelle, True)],
                         ids=["feld", "zelle", "zelle_mit_nachbar"])
def test_abgeschnittener_text_verlaesst_die_ausgabe_nicht(tmp_path, bauen, als_bild):
    """Der abgeschnittene Teil ("IBAN DE02 …") stand nach dem Schwärzen weiter im Strom; pdftotext las ihn (Status
    "fertig"). Jetzt wird er entfernt – einzeln, ohne Sichtbares anzutasten, oder (berührt er sichtbaren Text) mit der
    Seite als Bild."""
    pfad = tmp_path / "abgeschnitten.pdf"
    bauen().save(pfad)
    assert "2020 51" in _alle_zeichen(pfad)
    vorher = fitz.open(pfad)
    sichtbar = {w[4] for w in vorher[0].get_text("words")} - {"Max", "Mustermann"}
    e = schwaerze_pdf(pfad, [fund(NAME)], ziel_ordner=tmp_path / "aus")
    assert e["ausgabe"] is not None and e["fehler"] is None, e
    assert "2020" not in _alle_zeichen(e["ausgabe"]) and "DE02" not in _alle_zeichen(e["ausgabe"])
    assert ("SEITE_ALS_BILD" in codes(e)) is als_bild
    if not als_bild:
        nachher = {w[4] for w in fitz.open(e["ausgabe"])[0].get_text("words")}
        assert sichtbar <= nachher, sorted(sichtbar - nachher)
        assert any(m["code"] == "NEBENKANAL_ENTFERNT" and "abgeschnittene" in m["text"] for m in e["meldungen"])
