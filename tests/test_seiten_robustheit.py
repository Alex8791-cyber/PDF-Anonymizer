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

import pickle
import re

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
    pix.set_rect(pix.irect, (250, 250, 250))
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
