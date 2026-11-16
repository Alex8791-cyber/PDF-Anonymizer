"""Bildreste (Befund 1 der Runde 3a): Das ungeschwärzte Original eines Bilds darf nie unsichtbar in der Ausgabe stecken.

apply_redactions(images=PDF_REDACT_IMAGE_PIXELS) gibt der geschwärzten Seite ein eigenes Ressourcen-Wörterbuch mit dem
neuen Bild. Erbt die Seite ihre Ressourcen vom Seitenbaum (/Pages) oder teilt sie das Wörterbuch mit anderen Seiten
(LibreOffice: EIN Wörterbuch für alle Seiten und den Seitenbaum), blieb das Original dort verwiesen – angezeigt wurde
die geschwärzte Fassung, in der Datei steckte der volle Scan (Gesicht, Name, Anschrift), Status „fertig“.

Geprüft wird:
  * bilder.py: nicht gezeichnete Bilder werden geleert (geerbt, geteilt, beides, vollständig abgedeckt, ungenutzt),
    gezeichnete bleiben – auch in Form-XObjects, Kachelmustern, weichen Masken, Anmerkungen, mit #-Namen, als Maske –
    und nichts Sichtbares ändert sich; das Netz in der gespeicherten Datei leert und schreibt neu.
  * Schwärzung („hoch“ und „maximal“): Scan-Brief, Ausweisscan mit Lichtbild, zwei Scan-Seiten mit gemeinsamem
    Wörterbuch, Textseite mit Porträt bzw. eingebettetem Ausweis – das Original steckt nicht mehr in der Ausgabe; fällt
    die Bereinigung vor dem Speichern aus, greift das Netz nach dem Speichern und die Ausgabe wird _PRUEFEN.
"""

from pathlib import Path

import numpy as np
import pytest

import pymupdf as fitz

import foto_vorlagen as fv
from anonymisierer import bilder, fotos, schwaerzung
from test_fotos import AUSWEIS_WOERTER, Attrappe, _analyse_und_schwaerzung, zeilenwoerter

MM = fv.MM
A4 = fitz.Rect(0, 0, 595, 842)


# ----------------------------------------------------------------------
# Hilfen: Scan-Dokumente mit eigenen, geteilten oder geerbten Ressourcen
# ----------------------------------------------------------------------
def _bild_objekt(doc, jpeg: bytes, breite: int, hoehe: int, grau: bool = False) -> int:
    x = doc.get_new_xref()
    cs = "/DeviceGray" if grau else "/DeviceRGB"
    doc.update_object(x, f"<</Type/XObject/Subtype/Image/Width {breite}/Height {hoehe}/ColorSpace {cs}"
                         f"/BitsPerComponent 8>>")
    doc.update_stream(x, jpeg, new=True, compress=False)
    doc.xref_set_key(x, "Filter", "/DCTDecode")            # erst nach update_stream (das den Filter zurücksetzt)
    return x


def scan_dokument(pfad, seiten: list, art: str = "eigen") -> list:
    """PDF aus Rasterbildern (je Seite eins, A4). art: „eigen“ (jede Seite ihr Wörterbuch), „geteilt“ (alle Seiten
    EIN Wörterbuch), „geerbt“ (das Wörterbuch hängt am Seitenbaum, die Seiten erben es) oder „beides“ (wie
    LibreOffice: Seitenbaum UND alle Seiten). Rückgabe: die JPEG-Daten der Originale je Seite."""
    doc = fitz.open()
    daten, namen = [], []
    for i, a in enumerate(seiten):
        doc.new_page(width=A4.width, height=A4.height)
        jpeg = fv.jpeg(a, 80)
        x = _bild_objekt(doc, jpeg, a.shape[1], a.shape[0], grau=a.ndim == 2)
        daten.append(jpeg)
        namen.append((f"Scan{i}", x))
    for i, s in enumerate(doc):
        c = doc.get_new_xref()
        doc.update_object(c, "<<>>")
        doc.update_stream(c, f"q 595 0 0 842 0 0 cm /Scan{i} Do Q".encode(), new=True)
        doc.xref_set_key(s.xref, "Contents", f"{c} 0 R")
    alle = "<</XObject<<" + "".join(f"/{n} {x} 0 R" for n, x in namen) + ">>>>"
    gemeinsam = doc.get_new_xref()
    doc.update_object(gemeinsam, alle)
    wurzel = int(doc.xref_get_key(doc.pdf_catalog(), "Pages")[1].split()[0])
    for i, s in enumerate(doc):
        if art == "eigen":
            doc.xref_set_key(s.xref, "Resources", f"<</XObject<</{namen[i][0]} {namen[i][1]} 0 R>>>>")
        elif art in ("geteilt", "beides"):
            doc.xref_set_key(s.xref, "Resources", f"{gemeinsam} 0 R")
        else:
            doc.xref_set_key(s.xref, "Resources", "null")
    if art in ("geerbt", "beides"):
        doc.xref_set_key(wurzel, "Resources", f"{gemeinsam} 0 R")
    doc.save(pfad)
    doc.close()
    return daten


def ressourcen_vererben(quelle, ziel) -> None:
    """Die Ressourcen jeder Seite an den Seitenbaum hängen (nur für einseitige Dokumente)."""
    doc = fitz.open(quelle)
    assert len(doc) == 1
    s = doc[0]
    art, res = doc.xref_get_key(s.xref, "Resources")
    wurzel = int(doc.xref_get_key(doc.pdf_catalog(), "Pages")[1].split()[0])
    doc.xref_set_key(wurzel, "Resources", res)
    doc.xref_set_key(s.xref, "Resources", "null")
    doc.save(ziel)
    doc.close()


def rohdaten(pdf) -> set:
    """Rohdaten (Strom, wie gespeichert) aller Bilder der Datei."""
    with fitz.open(pdf) as doc:
        return {doc.xref_stream_raw(x) for x in bilder.alle_bilder(doc)}


def ungezeichnet(pdf) -> list:
    with fitz.open(pdf) as doc:
        gezeichnet, unsicher, voll = bilder.gezeichnete_bilder(doc)
        assert voll and not unsicher
        return [x for x in bilder.alle_bilder(doc) if x not in gezeichnet and not bilder._ist_leer(doc, x)]


def grau(seite, dpi=40) -> np.ndarray:
    p = seite.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, annots=True)
    return np.frombuffer(p.samples, np.uint8).reshape(p.height, p.stride)[:, :p.width].astype(int)


def schwaerzen(doc, seite, rect):
    vorher = bilder.bildzustand(seite)
    seite.add_redact_annot(fitz.Rect(rect), fill=(0.92, 0.92, 0.92))
    seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
    bilder.nach_schwaerzung(doc, seite, vorher)


def brief(rng, zeilen=fv.BRIEFTEXT, dpi=100):
    return fv.scan_effekte(rng, fv.textseite_bild(rng, zeilen, dpi=dpi, grau_=False), rauschen=3.0, unschaerfe=0.4)


# ----------------------------------------------------------------------
# bilder.py
# ----------------------------------------------------------------------
@pytest.mark.parametrize("art", ["eigen", "geteilt", "geerbt", "beides"])
def test_original_eines_geschwaerzten_scans_bleibt_nicht_in_der_datei(tmp_path, art):
    rng = np.random.default_rng(1)
    pdf = tmp_path / f"{art}.pdf"
    original = scan_dokument(pdf, [brief(rng), brief(rng)], art)
    aus = tmp_path / "aus.pdf"
    with fitz.open(pdf) as doc:
        vorher_s2 = grau(doc[1])
        schwaerzen(doc, doc[0], (60, 100, 300, 160))
        befund = bilder.bildreste_entfernen(doc)
        doc.save(aus, garbage=4, deflate=True)
    assert befund["rest"] == [] and befund["unsicher"] == []
    # nur dort, wo die Datei das Original sonst behalten hätte, wird es gemeldet (eigene Ressourcen: verwaist)
    assert befund["geleert"] == (0 if art == "eigen" else 1)
    daten = rohdaten(aus)
    assert original[0] not in daten, "das ungeschwärzte Original von Seite 1 steckt noch in der Datei"
    assert original[1] in daten, "Seite 2 (ohne Schwärzung) behält ihr Bild unverändert"
    assert ungezeichnet(aus) == []
    with fitz.open(aus) as doc:
        assert np.abs(grau(doc[1]) - vorher_s2).max() <= 8
        assert len(doc[0].get_image_info()) == 1


@pytest.mark.parametrize("art", ["geteilt", "geerbt", "beides"])
def test_ganz_abgedecktes_bild_verschwindet_auch_aus_geteiltem_woerterbuch(tmp_path, art):
    """Deckt die Schwärzung ein Bild vollständig ab, entfernt MuPDF es von der Seite (kein Ersatzbild) – das Original
    blieb im geerbten bzw. geteilten Wörterbuch stehen."""
    rng = np.random.default_rng(2)
    doc = fitz.open()
    s = fv.textseite(doc, fv.BRIEFTEXT[:6])
    foto = fv.jpeg(fv.objektfoto(rng, 320, 240), 80)
    r = fitz.Rect(80, 300, 400, 540)
    s.insert_image(r, stream=foto, keep_proportion=False)
    fv.textseite(doc, fv.BRIEFTEXT[6:12])                   # zweite Seite (teilt bzw. erbt dasselbe Wörterbuch)
    pdf = tmp_path / "foto.pdf"
    doc.save(pdf)
    doc.close()
    doc = fitz.open(pdf)
    art_res, res = doc.xref_get_key(doc[0].xref, "Resources")
    if art_res == "xref":
        res = doc.xref_object(int(res.split()[0]), compressed=True)
    gemeinsam = doc.get_new_xref()
    doc.update_object(gemeinsam, res)
    wurzel = int(doc.xref_get_key(doc.pdf_catalog(), "Pages")[1].split()[0])
    for seite in doc:
        doc.xref_set_key(seite.xref, "Resources", "null" if art == "geerbt" else f"{gemeinsam} 0 R")
    if art != "geteilt":
        doc.xref_set_key(wurzel, "Resources", f"{gemeinsam} 0 R")
    doc.save(tmp_path / "umgebaut.pdf")
    doc.close()
    aus = tmp_path / "aus.pdf"
    with fitz.open(tmp_path / "umgebaut.pdf") as doc:
        assert doc[0].get_image_info() and not doc[1].get_image_info()
        schwaerzen(doc, doc[0], r + (-2, -2, 2, 2))
        assert not doc[0].get_images()                       # MuPDF hat das Bild von der Seite genommen
        befund = bilder.bildreste_entfernen(doc)
        doc.save(aus, garbage=4, deflate=True)
    assert befund["geleert"] == 1
    assert foto not in rohdaten(aus) and ungezeichnet(aus) == []


def _inhalt(doc, seite, c: bytes):
    alt = doc.xref_get_key(seite.xref, "Contents")
    x = doc.get_new_xref()
    doc.update_object(x, "<<>>")
    doc.update_stream(x, c, new=True)
    neu = f"{x} 0 R"
    if alt[0] == "array":
        doc.xref_set_key(seite.xref, "Contents", alt[1].rstrip()[:-1] + f" {neu}]")
    elif alt[0] == "xref":
        doc.xref_set_key(seite.xref, "Contents", f"[{alt[1]} {neu}]")
    else:
        doc.xref_set_key(seite.xref, "Contents", neu)


def test_gezeichnete_bilder_bleiben_ungenutzte_werden_geleert(tmp_path):
    """Gezeichnet ist auch: ein Bild in einem Form-XObject, in einem Kachelmuster, in der Gruppe einer weichen Maske, im
    Erscheinungsbild einer Anmerkung, über einen Namen mit #-Schreibweise und eine SMask. Diese bleiben, nichts
    Sichtbares ändert sich; ein ungenutzt mitgeschlepptes Bild wird geleert."""
    rng = np.random.default_rng(3)
    doc = fitz.open()
    s = fv.textseite(doc, fv.BRIEFTEXT[:3])

    def bild(w=60, h=75):
        return _bild_objekt(doc, fv.jpeg(fv.portraet(rng, w, h), 80), w, h)
    form_bild, muster_bild, maske_bild, name_bild, anm_bild, ungenutzt = (bild() for _ in range(6))
    form = doc.get_new_xref()
    doc.update_object(form, f"<</Type/XObject/Subtype/Form/BBox[0 0 1 1]/Resources<</XObject<</B {form_bild} 0 R>>>>>>")
    doc.update_stream(form, b"q 1 0 0 1 0 0 cm /B Do Q", new=True)
    muster = doc.get_new_xref()
    doc.update_object(muster, f"<</Type/Pattern/PatternType 1/PaintType 1/TilingType 1/BBox[0 0 60 75]/XStep 60"
                              f"/YStep 75/Resources<</XObject<</M {muster_bild} 0 R>>>>>>")
    doc.update_stream(muster, b"q 60 0 0 75 0 0 cm /M Do Q", new=True)
    gruppe = doc.get_new_xref()
    doc.update_object(gruppe, f"<</Type/XObject/Subtype/Form/BBox[0 0 595 842]/Group<</S/Transparency/CS/DeviceGray>>"
                              f"/Resources<</XObject<</G {maske_bild} 0 R>>>>>>")
    doc.update_stream(gruppe, b"q 595 0 0 842 0 0 cm /G Do Q", new=True)
    art, res = doc.xref_get_key(s.xref, "Resources")
    ziel = int(res.split()[0]) if art == "xref" else None

    def setzen(schluessel, wert):
        if ziel:
            doc.xref_set_key(ziel, schluessel, wert)
        else:
            doc.xref_set_key(s.xref, "Resources/" + schluessel, wert)
    setzen("XObject", f"<</Fm {form} 0 R/Mein#20Bild {name_bild} 0 R/Unbenutzt {ungenutzt} 0 R>>")
    setzen("Pattern", f"<</P1 {muster} 0 R>>")
    setzen("ExtGState", f"<</GS1<</SMask<</S/Luminosity/G {gruppe} 0 R>>>>>>")
    _inhalt(doc, s, b"q 120 0 0 150 60 500 cm /Fm Do Q q 80 0 0 100 300 500 cm /Mein#20Bild Do Q "
                    b"q /Pattern cs /P1 scn 400 300 120 150 re f Q q /GS1 gs 0 0 1 rg 60 650 200 100 re f Q")
    annot = s.add_rect_annot(fitz.Rect(300, 700, 380, 780))
    annot.update()
    ap = int(doc.xref_get_key(annot.xref, "AP/N")[1].split()[0])
    doc.xref_set_key(ap, "Resources", f"<</XObject<</A {anm_bild} 0 R>>>>")
    doc.update_stream(ap, b"q 80 0 0 80 0 0 cm /A Do Q")
    alpha = (255 - fv.grau(fv.unterschrift(rng, 120, 40))).astype(np.uint8)
    s.insert_image(fitz.Rect(60, 760, 180, 800),
                   pixmap=fitz.Pixmap(fitz.csRGB, 120, 40,
                                      np.dstack([np.zeros((40, 120, 3), np.uint8), alpha]).tobytes(), True))
    pdf = tmp_path / "wege.pdf"
    doc.save(pdf)
    doc.close()
    with fitz.open(pdf) as doc:
        vorher = grau(doc[0], 60)
        erreichbar = bilder.erreichbare_bilder(doc, doc[0].xref)
        assert erreichbar[muster_bild] and erreichbar[maske_bild] and erreichbar[anm_bild]      # indirekt
        assert not erreichbar[form_bild] and not erreichbar[name_bild]
        befund = bilder.bildreste_entfernen(doc)
        assert befund["geleert"] == 1 and befund["rest"] == [] and befund["unsicher"] == []
        assert bilder._ist_leer(doc, ungenutzt)
        for x in (form_bild, muster_bild, maske_bild, name_bild, anm_bild):
            assert not bilder._ist_leer(doc, x), x
        smask = [x for x in bilder.alle_bilder(doc) if doc.xref_get_key(x, "SMask")[0] == "xref"]
        assert smask and not bilder._ist_leer(doc, int(doc.xref_get_key(smask[0], "SMask")[1].split()[0]))
        daten = doc.tobytes(garbage=4, deflate=True)
    with fitz.open("pdf", daten) as doc:
        assert np.abs(grau(doc[0], 60) - vorher).max() <= 8


def test_netz_leert_bildrest_in_der_gespeicherten_datei(tmp_path):
    rng = np.random.default_rng(4)
    pdf = tmp_path / "geerbt.pdf"
    original = scan_dokument(pdf, [brief(rng)], "geerbt")
    with fitz.open(pdf) as doc:
        schwaerzen(doc, doc[0], (60, 100, 300, 160))
        doc.save(tmp_path / "ohne_bereinigung.pdf", garbage=4, deflate=True)
    assert original[0] in rohdaten(tmp_path / "ohne_bereinigung.pdf")        # so sah die Ausgabe bisher aus
    befund = bilder.bildreste_in_datei_entfernen(tmp_path / "ohne_bereinigung.pdf", tmp_path / "hilf.pdf")
    assert befund["geleert"] == 1 and befund["geleert_alle"] == 1 and befund["rest"] == []
    assert original[0] not in rohdaten(tmp_path / "ohne_bereinigung.pdf") and not (tmp_path / "hilf.pdf").exists()
    assert bilder.bildreste_in_datei_entfernen(tmp_path / "ohne_bereinigung.pdf", tmp_path / "hilf.pdf")[
        "geleert_alle"] == 0


def test_unlesbarer_inhalt_leert_nichts_und_meldet(tmp_path, monkeypatch):
    rng = np.random.default_rng(5)
    pdf = tmp_path / "geerbt.pdf"
    original = scan_dokument(pdf, [brief(rng), brief(rng)], "beides")

    def kaputt(doc, seite):
        raise RuntimeError("Probe")
    monkeypatch.setattr(bilder, "_aufgerufen", kaputt)
    with fitz.open(pdf) as doc:
        schwaerzen(doc, doc[0], (60, 100, 300, 160))
        befund = bilder.bildreste_entfernen(doc)
        assert befund["unsicher"] == [0, 1] and befund["geleert"] == 0
        assert any(doc.xref_stream_raw(x) == original[0] for x in bilder.alle_bilder(doc))


# ----------------------------------------------------------------------
# Schwärzung („hoch“, „maximal“)
# ----------------------------------------------------------------------
EMAIL = "erika.musterfrau@example.org"


def _codes(s, art="hinweis"):
    return {m["code"] for m in s["meldungen"] if m["art"] == art}


@pytest.mark.parametrize("art", ["geerbt", "beides"])
def test_hoch_scan_brief_mit_geerbten_ressourcen(tmp_path, art):
    rng = np.random.default_rng(11)
    pdf = tmp_path / "brief.pdf"
    original = scan_dokument(pdf, [brief(rng)], art)
    ocr = Attrappe({0: zeilenwoerter([f"Kontakt: {EMAIL}"], x0=60, y0=300)})
    e, s = _analyse_und_schwaerzung(pdf, ocr)
    assert any(f["kategorie"] == "email" for f in e["funde"])
    assert s["ausgabe"] and original[0] not in rohdaten(s["ausgabe"]) and ungezeichnet(s["ausgabe"]) == []
    assert s["bilder_entfernt"] == 1 and "BILDER_ENTFERNT" in _codes(s)
    assert not any("Bilder" in g for g in s["pruefen_gruende"])


@pytest.mark.parametrize("art", ["eigen", "geerbt"])
def test_hoch_ausweisscan_lichtbild_original_nicht_in_der_datei(tmp_path, art):
    rng = np.random.default_rng(12)
    doc, licht = fv.ausweis_karte(rng, "personalausweis", "vorn")
    karte = fv.rendern(doc[0], 300)
    bw, bh = doc[0].rect.width, doc[0].rect.height
    doc.close()
    seite, _ = fv.seite_komponieren(rng, [(karte, (90, 110, 90 + bw, 110 + bh))], dpi=200)
    pdf = tmp_path / "ausweis.pdf"
    original = scan_dokument(pdf, [fv.scan_effekte(rng, seite, rauschen=4.0, unschaerfe=0.5)], art)
    foto = fitz.Rect(90 + licht.x0, 110 + licht.y0, 90 + licht.x1, 110 + licht.y1)
    ocr = Attrappe({0: AUSWEIS_WOERTER + zeilenwoerter(["Name / Surname MUSTERMANN"])})
    e, s = _analyse_und_schwaerzung(pdf, ocr)
    assert s["lichtbilder_abgedeckt"] == 1
    daten = rohdaten(s["ausgabe"])
    assert original[0] not in daten and ungezeichnet(s["ausgabe"]) == []
    with fitz.open(s["ausgabe"]) as aus:
        (bild,) = [x for x in bilder.alle_bilder(aus) if not bilder._ist_leer(aus, x)]
        pix = fitz.Pixmap(aus, bild)
        f = pix.width / 595
        a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
        gesicht = a[int(foto.y0 * f) + 4:int(foto.y1 * f) - 4, int(foto.x0 * f) + 4:int(foto.x1 * f) - 4]
        assert gesicht.std() < 20, "im einzigen Bild der Datei ist das Lichtbild abgedeckt"


def test_hoch_zwei_scanseiten_gemeinsames_woerterbuch(tmp_path):
    """Nur Seite 1 hat einen Fund: ihr Original verschwindet, Seite 2 bleibt unverändert."""
    rng = np.random.default_rng(13)
    pdf = tmp_path / "zwei.pdf"
    original = scan_dokument(pdf, [brief(rng), brief(rng, fv.BRIEFTEXT[9:])], "geteilt")
    ocr = Attrappe({0: zeilenwoerter([f"Kontakt: {EMAIL}"], x0=60, y0=300),
                    1: zeilenwoerter(["Die Prüfung dauert in der Regel zwei Wochen."], x0=60, y0=300)})
    e, s = _analyse_und_schwaerzung(pdf, ocr)
    daten = rohdaten(s["ausgabe"])
    assert original[0] not in daten and original[1] in daten and ungezeichnet(s["ausgabe"]) == []


def test_maximal_textseite_portraet_mit_geerbten_ressourcen(tmp_path):
    rng = np.random.default_rng(14)
    doc = fitz.open()
    s = fv.textseite(doc, fv.BRIEFTEXT[:8] + [f"Kontakt: {EMAIL}"])
    portraet = fv.jpeg(fv.portraet(rng, 280, 360), 85)
    s.insert_image(fitz.Rect(380, 400, 520, 580), stream=portraet, keep_proportion=False)
    doc.save(tmp_path / "eigen.pdf")
    doc.close()
    ressourcen_vererben(tmp_path / "eigen.pdf", tmp_path / "geerbt.pdf")
    e, s = _analyse_und_schwaerzung(tmp_path / "geerbt.pdf", Attrappe(), profil="maximal")
    assert [f for f in e["funde"] if f["kategorie"] == fotos.KAT_BILD]
    assert portraet not in rohdaten(s["ausgabe"]) and ungezeichnet(s["ausgabe"]) == []
    with fitz.open(s["ausgabe"]) as aus:
        assert all(bilder._ist_leer(aus, x) for x in bilder.alle_bilder(aus))


def test_hoch_textseite_mit_eingebettetem_ausweis_geerbt(tmp_path):
    rng = np.random.default_rng(15)
    karte, licht = fv.karte_rendern(rng, "personalausweis", "vorn", dpi=150)
    jpeg = fv.jpeg(karte, 80)
    doc = fitz.open()
    s = fv.textseite(doc, ["Anbei die Kopie meines Personalausweises.", "", f"Kontakt: {EMAIL}"])
    s.insert_image(fitz.Rect(150, 300, 150 + 85.6 * MM, 300 + 54 * MM), stream=jpeg, keep_proportion=False)
    doc.save(tmp_path / "eigen.pdf")
    doc.close()
    ressourcen_vererben(tmp_path / "eigen.pdf", tmp_path / "geerbt.pdf")
    e, s = _analyse_und_schwaerzung(tmp_path / "geerbt.pdf", Attrappe())
    assert s["lichtbilder_abgedeckt"] == 1
    assert jpeg not in rohdaten(s["ausgabe"]) and ungezeichnet(s["ausgabe"]) == []


def test_netz_nach_dem_speichern_greift_wenn_die_bereinigung_ausfaellt(tmp_path, monkeypatch):
    """Fällt die Bereinigung vor dem Speichern aus (hier: abgeschaltet), findet das Netz das Original in der
    geschriebenen Datei, leert es, schreibt neu – und die Ausgabe wird _PRUEFEN (das sollte nie vorkommen)."""
    rng = np.random.default_rng(16)
    pdf = tmp_path / "brief.pdf"
    original = scan_dokument(pdf, [brief(rng)], "geerbt")
    monkeypatch.setattr(schwaerzung, "_bildreste_entfernen", lambda lauf, ergebnis: None)
    ocr = Attrappe({0: zeilenwoerter([f"Kontakt: {EMAIL}"], x0=60, y0=300)})
    e, s = _analyse_und_schwaerzung(pdf, ocr)
    assert s["ausgabe"] and original[0] not in rohdaten(s["ausgabe"]) and ungezeichnet(s["ausgabe"]) == []
    assert s["status"] == "pruefen" and "_PRUEFEN" in Path(s["ausgabe"]).name
    assert any("nachträglich entfernt" in g for g in s["pruefen_gruende"]), s["pruefen_gruende"]


def test_fehler_der_bereinigung_macht_die_ausgabe_pruefen(tmp_path, monkeypatch):
    rng = np.random.default_rng(17)
    pdf = tmp_path / "brief.pdf"
    scan_dokument(pdf, [brief(rng)], "geerbt")

    def kaputt(*a, **k):
        raise MemoryError("Probe")
    monkeypatch.setattr(bilder, "bildreste_entfernen", kaputt)
    ocr = Attrappe({0: zeilenwoerter([f"Kontakt: {EMAIL}"], x0=60, y0=300)})
    e, s = _analyse_und_schwaerzung(pdf, ocr)
    assert s["status"] == "pruefen"
    assert any("nicht sicher entfernt" in g for g in s["pruefen_gruende"]), s["pruefen_gruende"]
    assert "BILDER_UNGEPRUEFT" in _codes(s, "warnung")
