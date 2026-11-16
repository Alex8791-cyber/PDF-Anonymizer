"""Tests der Fotobereich-Erkennung und der Bildfunde (anonymisierer/fotos.py), der Haken in Analyse und Schwärzung
und der Bildprüfungen in anonymisierer/bilder.py.

Alle Bilder sind synthetisch (tests/foto_vorlagen.py): Porträts aus Verläufen, Rauschen und Formen – keine echten
Gesichter –, Ausweiskarten mit Sicherheitsuntergrund und maschinenlesbarer Zone, Schadenfotos, Logos, Stempel,
Diagramme, Tabellen und Schrift. Die OCR ist eine Attrappe (feste Wörter), damit die Tests ohne Tesseract laufen.

Geprüft wird:
  * Erkennung: Lichtbilder auf Ausweisscans (Rauschen, JPEG, geringe Auflösung, Schräglage, Graustufen, Raster),
    Fotos auf Textseiten und ganzen Fotoseiten werden gefunden; Brief, Logo (auch mit Verlauf), Stempel, Diagramm,
    Tabelle, große Überschrift und das fotografierte Blatt selbst nicht.
  * „hoch“: Lichtbild mit Ausweis-Kontext als angehakter Fund (abgedeckt, „[LICHTBILD]“, auch auf gedrehten Seiten;
    ein eingebettetes Passbild ganz), abgewählt -> Freigabe nötig; Ausweiskopie ohne gefundenes Lichtbild -> Freigabe
    nötig; sonstige Fotos bleiben unberührt.
  * „maximal“: jedes Rasterbild einer Textseite verschwindet (XObject, Inline-Bild, Bildmaske, Bild mit SMask, Bild in
    Form-XObject und in einem Kachelmuster), winzige Symbole bleiben; Fotobereiche auf Scans werden abgedeckt;
    Zählung in Ergebnis und Meldungen.
  * Beschädigte Bilder: abgeschnittenes progressives JPEG -> BILD_BESCHAEDIGT; große JPEGs werden verkleinert dekodiert.
  * Speicher: Neukodierung ohne Vollkopie der Pixel, „Seite als Bild“ rechnet nie hoch.
"""

import tracemalloc
import zlib
from pathlib import Path

import numpy as np
import pytest

import pymupdf as fitz

import foto_vorlagen as fv
from anonymisierer import analyse, bilder, fotos, muster
from anonymisierer.analyse import analysiere_pdf
from anonymisierer.schwaerzung import schwaerze_pdf

MM = fv.MM
pytestmark = pytest.mark.skipif(not fotos.verfuegbar(), reason="numpy fehlt")


# ----------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------
class Attrappe:
    """OCR-Attrappe: feste Wörter je Seite (x0, y0, x1, y1, Text)."""

    def __init__(self, woerter_je_seite=None):
        self.woerter_je_seite = woerter_je_seite or {}
        self.hinweise = []

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, **_):
        return list(self.woerter_je_seite.get(seite_nr0, [])), None

    def abbrechen(self):
        pass

    def schliessen(self):
        pass


def zeilenwoerter(zeilen, x0=40.0, y0=600.0, abstand=16.0):
    """OCR-Wörter für Textzeilen (unten auf der Seite, fern der Karte)."""
    aus = []
    for i, z in enumerate(zeilen):
        x, y = x0, y0 + abstand * i
        for w in z.split():
            breite = 6.0 * len(w)
            aus.append((x, y, x + breite, y + 12, w))
            x += breite + 5
    return aus


def abdeckung(rect, bereiche) -> float:
    """Anteil der Fläche von rect, den die Vereinigung der Bereiche bedeckt (Raster 1 pt)."""
    r = fitz.Rect(rect)
    x0, y0, x1, y1 = int(r.x0), int(r.y0), int(r.x1) + 1, int(r.y1) + 1
    m = np.zeros((y1 - y0, x1 - x0), bool)
    for b in bereiche:
        b = fitz.Rect(getattr(b, "rect", b)) & r
        if not b.is_empty:
            m[int(b.y0) - y0:int(b.y1) - y0, int(b.x0) - x0:int(b.x1) - x0] = True
    return float(m.mean())


def flaeche(bereiche) -> float:
    return sum(abs(fitz.Rect(getattr(b, "rect", b))) for b in bereiche)


def ausweis_scan(pfad, rng, art="personalausweis", dpi=200, grau=False, qualitaet=60, rauschen=6.0, schraeg=0.0,
                 dither=False, rueckseite=False, skala=1.0):
    """A4-Scan einer Ausweiskarte (Vorderseite; mit rueckseite die Rückseite ohne Lichtbild darunter).
    Rückgabe: (Pfad, Lichtbild-Rechteck in pt oder None, Karten-Rechteck)."""
    doc, licht = fv.ausweis_karte(rng, art, "hinten" if rueckseite else "vorn")
    bw, bh = doc[0].rect.width, doc[0].rect.height
    karte = fv.rendern(doc[0], 300)
    doc.close()
    x0, y0 = 90.0, 110.0
    rect = (x0, y0, x0 + bw * skala, y0 + bh * skala)
    seite, _ = fv.seite_komponieren(rng, [(karte, rect)], dpi=dpi, grau_=grau, schraeg=schraeg)
    seite = fv.scan_effekte(rng, seite, rauschen=rauschen, unschaerfe=0.5)
    if dither:
        seite = fv.dither(seite)
    fv.scan_pdf(pfad, [seite], qualitaet=qualitaet, als_png=dither)
    foto = None
    if licht is not None:
        foto = fitz.Rect(x0 + licht.x0 * skala, y0 + licht.y0 * skala, x0 + licht.x1 * skala, y0 + licht.y1 * skala)
        if abs(schraeg) > 0.01:
            mitte = fitz.Point(fv.A4[0] / 2, fv.A4[1] / 2)
            mat = fitz.Matrix(1, 1).prerotate(-schraeg)
            ecken = [(p - mitte) * mat + mitte for p in (foto.tl, foto.tr, foto.bl, foto.br)]
            foto = fitz.Rect(min(p.x for p in ecken), min(p.y for p in ecken), max(p.x for p in ecken),
                             max(p.y for p in ecken))
    return Path(pfad), foto, fitz.Rect(rect)


def scan_mit(pfad, rng, teile, text=None, dpi=150, grau=False, qualitaet=60, rauschen=6.0):
    seite, _ = fv.seite_komponieren(rng, teile, dpi=dpi, grau_=grau, text=text)
    seite = fv.scan_effekte(rng, seite, rauschen=rauschen, unschaerfe=0.5)
    fv.scan_pdf(pfad, [seite], qualitaet=qualitaet)
    return Path(pfad)


def seitenbereiche(pdf, **kw):
    with fitz.open(pdf) as doc:
        return fotos.fotobereiche(doc[0], **kw)


AUSWEIS_WOERTER = [(95, 70, 250, 82, "PERSONALAUSWEIS"), (252, 70, 260, 82, "/"), (262, 70, 320, 82, "IDENTITY"),
                   (322, 70, 360, 82, "CARD")]


# ----------------------------------------------------------------------
# Ausweis-Kontext, winzige Bilder
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("PERSONALAUSWEIS / IDENTITY CARD", fotos.KONTEXT_STARK),
    ("REISEPASS", fotos.KONTEXT_STARK),
    ("Reisepass / Passport", fotos.KONTEXT_STARK),
    ("Führerschein", fotos.KONTEXT_STARK),
    ("IDD<<T220001294<<<<<<<<<<<<<<<", fotos.KONTEXT_STARK),
    ("IDD<<T22OOO1294<<<<< <<<< <<<<<<", fotos.KONTEXT_STARK),          # OCR trennt die Zone
    ("Name / Surname\nVornamen / Given names", fotos.KONTEXT_STARK),
    ("anbei die Kopie meines Personalausweises", fotos.KONTEXT_SCHWACH),
    ("Kopie Ihres Reisepasses", fotos.KONTEXT_SCHWACH),
    ("Führerschein-Nr.: B072RRE2I55", fotos.KONTEXT_SCHWACH),           # Formularfeld, keine Ausweiskopie
    ("Bitte das Lichtbild einkleben", fotos.KONTEXT_SCHWACH),
    ("Staatsangehörigkeit: deutsch\nGeburtsort: Köln\nGültig bis: 12/2027", fotos.KONTEXT_KEINER),
    ("Vertrag Kfz-Haftpflicht, Schadenmeldung vom 12.03.2025", fotos.KONTEXT_KEINER),
    ("Summe <<< Zwischensumme", fotos.KONTEXT_KEINER),
])
def test_ausweis_kontext(text, erwartet):
    assert fotos.ausweis_kontext(text) == erwartet


def test_winzige_bilder():
    """Ein Gesicht ist ab etwa 24 x 24 Pixeln erkennbar, eine Zeile ab etwa 6 Pixeln Höhe; die Größe auf der Seite
    zählt nicht (ein winzig gezeigtes Bild lässt sich in voller Auflösung herausziehen)."""
    assert fotos.bild_winzig(16, 16) and fotos.bild_winzig(23, 24) and fotos.bild_winzig(2000, 5)
    assert not fotos.bild_winzig(24, 24) and not fotos.bild_winzig(120, 150) and not fotos.bild_winzig(800, 6)


# ----------------------------------------------------------------------
# Erkennung auf Scans und eingebetteten Bildern
# ----------------------------------------------------------------------
@pytest.mark.parametrize("art, variante", [
    ("personalausweis", dict(dpi=100, grau=True, qualitaet=35, rauschen=12.0)),
    ("personalausweis", dict(dpi=150, grau=False, qualitaet=60, rauschen=6.0, schraeg=-2.0)),
    ("personalausweis", dict(dpi=300, grau=False, qualitaet=85, rauschen=2.0)),
    ("personalausweis", dict(dpi=200, grau=True, qualitaet=60, rauschen=2.0, skala=0.6)),
    ("personalausweis", dict(dpi=150, grau=False, qualitaet=60, rauschen=6.0, dither=True)),
    ("reisepass", dict(dpi=100, grau=False, qualitaet=35, rauschen=6.0)),
    ("reisepass", dict(dpi=200, grau=True, qualitaet=85, rauschen=12.0, schraeg=1.5)),
    ("fuehrerschein", dict(dpi=150, grau=True, qualitaet=60, rauschen=6.0)),
    ("fuehrerschein", dict(dpi=200, grau=False, qualitaet=35, rauschen=2.0, schraeg=-2.0)),
], ids=["ausweis-100dpi-grau-q35-rauschen", "ausweis-150dpi-schraeg", "ausweis-300dpi-farbe",
        "ausweis-verkleinerte-kopie", "ausweis-schwarzweiss-raster", "pass-100dpi-q35", "pass-200dpi-grau-schraeg",
        "fuehrerschein-150dpi-grau", "fuehrerschein-200dpi-q35-schraeg"])
def test_lichtbild_auf_ausweisscan_wird_gefunden(tmp_path, variante, art):
    rng = np.random.default_rng(zlib.crc32(repr((art, sorted(variante.items()))).encode()))
    pdf, foto, karte = ausweis_scan(tmp_path / "ausweis.pdf", rng, art, **variante)
    bereiche = seitenbereiche(pdf)
    assert abdeckung(foto, bereiche) >= 0.85, (bereiche, foto)
    # nicht die ganze Karte: das Lichtbild nimmt rund ein Drittel der Karte ein
    assert flaeche(bereiche) <= 2.2 * abs(foto), (flaeche(bereiche), abs(foto), abs(karte))
    if not variante.get("dither"):
        assert any(b.hochformat for b in bereiche)


@pytest.mark.parametrize("art", ["brief", "logo_stempel_unterschrift", "logo_verlauf", "diagramm", "tabelle",
                                 "ueberschrift"])
@pytest.mark.parametrize("dpi, grau, qualitaet", [(100, True, 35), (200, False, 60)])
def test_keine_fotos_auf_text_und_grafik(tmp_path, art, dpi, grau, qualitaet):
    rng = np.random.default_rng(zlib.crc32(repr((art, dpi)).encode()))
    text, teile = fv.BRIEFTEXT, []
    if art == "logo_stempel_unterschrift":
        teile = [(fv.logo(rng), (380, 30, 560, 102)), (fv.stempel(rng), (350, 600, 470, 720)),
                 (fv.unterschrift(rng), (60, 700, 260, 770))]
    elif art == "logo_verlauf":
        teile = [(fv.logo(rng, verlauf=True), (360, 20, 560, 100))]
    elif art == "diagramm":
        text, teile = fv.BRIEFTEXT[:10], [(fv.diagramm(rng), (70, 300, 520, 600))]
    elif art == "tabelle":
        text, teile = fv.BRIEFTEXT[:6], [(fv.tabelle(rng), (60, 200, 540, 520))]
    elif art == "ueberschrift":
        text, teile = None, [(fv.ueberschrift_bild(rng), (50, 60, 545, 200)),
                             (fv.textblock_bild(rng), (50, 220, 545, 700))]
    pdf = scan_mit(tmp_path / f"{art}.pdf", rng, teile, text=text, dpi=dpi, grau=grau, qualitaet=qualitaet)
    assert seitenbereiche(pdf) == []


def test_schadenfoto_und_passbild_auf_scans(tmp_path):
    rng = np.random.default_rng(5)
    r_schaden = (60, 420, 60 + 110 * MM, 420 + 82 * MM)
    pdf = scan_mit(tmp_path / "schaden.pdf", rng, [(fv.objektfoto(rng), r_schaden)], text=fv.BRIEFTEXT[:14])
    assert abdeckung(r_schaden, seitenbereiche(pdf)) >= 0.9
    r_pass = (380, 160, 380 + 35 * MM, 160 + 45 * MM)
    pdf = scan_mit(tmp_path / "formular.pdf", rng, [(fv.portraet(rng), r_pass)],
                   text=["Antrag auf Ausstellung eines Dienstausweises", "", "Name: Erika Musterfrau",
                         "Lichtbild (35 x 45 mm):"])
    bereiche = seitenbereiche(pdf)
    assert abdeckung(r_pass, bereiche) >= 0.9 and flaeche(bereiche) <= 1.8 * abs(fitz.Rect(r_pass))


def test_fotoseiten_ganzes_foto_und_fotografiertes_blatt(tmp_path):
    """Ein Handyfoto als PDF: ein Porträt ist ganz Foto; bei einem fotografierten Brief auf einer Tischplatte ist nur
    die Tischplatte Foto – der Brief in der Mitte bleibt lesbar."""
    rng = np.random.default_rng(7)
    doc = fitz.open()
    s = doc.new_page(width=420, height=560)
    s.insert_image(s.rect, stream=fv.jpeg(fv.portraet(rng, 600, 800), 85), keep_proportion=False)
    doc.save(tmp_path / "portraet.pdf")
    doc.close()
    assert abdeckung((0, 0, 420, 560), seitenbereiche(tmp_path / "portraet.pdf")) >= 0.9
    h, w = 1400, 1050
    bild = fv.dokumentfoto_hintergrund(rng, w, h)
    brief = fv.textseite_bild(rng, dpi=100, grau_=False, papier=240)
    ys = (np.arange(int(brief.shape[0] * 0.75)) / 0.75).astype(int)
    xs = (np.arange(int(brief.shape[1] * 0.75)) / 0.75).astype(int)
    klein = brief[ys][:, xs]
    oy, ox = (h - klein.shape[0]) // 2, (w - klein.shape[1]) // 2
    bild[oy:oy + klein.shape[0], ox:ox + klein.shape[1]] = klein
    doc = fitz.open()
    faktor = 595 / w
    s = doc.new_page(width=w * faktor, height=h * faktor)
    s.insert_image(s.rect, stream=fv.jpeg(bild, 85), keep_proportion=False)
    doc.save(tmp_path / "blatt.pdf")
    doc.close()
    blatt = fitz.Rect(ox, oy, ox + klein.shape[1], oy + klein.shape[0]) * faktor
    innen = blatt + (3 * MM, 3 * MM, -3 * MM, -3 * MM)       # 2-mm-Zellen dürfen den Rand des Blatts streifen
    bereiche = seitenbereiche(tmp_path / "blatt.pdf")
    assert bereiche and abdeckung(innen, bereiche) <= 0.02, bereiche


def test_eingebettete_bilder_einer_textseite(tmp_path):
    """Ausschnitt = eingebettetes Bild: ein Passbild füllt ihn ganz (das Papier daneben gibt das Weiß), ein Logo ist
    kein Foto, auf einer eingebetteten Ausweiskopie wird nur das Lichtbild gefunden."""
    rng = np.random.default_rng(11)
    doc = fitz.open()
    s = fv.textseite(doc)
    r_licht = fitz.Rect(400, 60, 400 + 30 * MM, 60 + 40 * MM)
    s.insert_image(r_licht, stream=fv.jpeg(fv.portraet(rng), 80), keep_proportion=False)
    r_logo = fitz.Rect(60, 720, 240, 790)
    s.insert_image(r_logo, stream=fv.png(fv.logo(rng, verlauf=True)), keep_proportion=False)
    karte, licht = fv.karte_rendern(rng, "personalausweis", "vorn", dpi=150)
    r_karte = fitz.Rect(300, 430, 300 + 85.6 * MM, 430 + 54 * MM)
    s.insert_image(r_karte, stream=fv.jpeg(karte, 75), keep_proportion=False)
    f = r_karte.width / karte.shape[1]
    foto = fitz.Rect(r_karte.x0 + licht[0] * f, r_karte.y0 + licht[1] * f, r_karte.x0 + licht[2] * f,
                     r_karte.y0 + licht[3] * f)
    assert abdeckung(r_licht, fotos.fotobereiche(s, clip=r_licht)) >= 0.95
    assert fotos.fotobereiche(s, clip=r_logo) == []
    im_ausweis = fotos.fotobereiche(s, clip=r_karte)
    assert abdeckung(foto, im_ausweis) >= 0.85 and flaeche(im_ausweis) <= 2.2 * abs(foto)
    assert any(fotos.ist_lichtbild(b, fotos.KONTEXT_KEINER) for b in im_ausweis), "Passbild auf ausweisgroßer Karte"
    doc.close()


def test_text_veto_der_ocr():
    """Was die OCR als viele lesbare Wörter gelesen hat, ist Text, kein Foto."""
    rng = np.random.default_rng(3)
    grau = fv.grau(fv.portraet(rng, 200, 260))
    seite = np.full((800, 600), 250, np.uint8)
    seite[100:360, 100:300] = grau
    px_je_mm = fotos.FOTO_DPI / 25.4
    assert fotos.fotobereiche_im_bild(seite, px_je_mm)
    woerter = [(100 + 40 * i, 100 + 26 * j, 136 + 40 * i, 118 + 26 * j, "Wort") for i in range(5) for j in range(10)]
    assert fotos.fotobereiche_im_bild(seite, px_je_mm, woerter_px=woerter) == []


# ----------------------------------------------------------------------
# „hoch“: Lichtbild-Fund, Freigabe
# ----------------------------------------------------------------------
def _analyse_und_schwaerzung(pdf, ocr, profil="hoch", ziel=None, aendern=None):
    aktive = set(muster.PROFILE[profil]["aktive"])
    e = analysiere_pdf(pdf, aktive, [], [], ocr=ocr, profil=profil)
    if aendern:
        aendern(e["funde"])
    s = schwaerze_pdf(pdf, e["funde"], ocr=ocr, ocr_cache=e["ocr_cache"], modell=e["modell"], profil=profil,
                      ziel_ordner=ziel or Path(pdf).parent / f"aus_{profil}")
    return e, s


def _pixel(pdf_pfad, rect, dpi=100) -> np.ndarray:
    with fitz.open(pdf_pfad) as doc:
        pix = doc[0].get_pixmap(dpi=dpi, clip=fitz.Rect(rect), colorspace=fitz.csGRAY)
        return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)


def _ohne_platzhalter_gleichmaessig(pdf_pfad, rect) -> bool:
    """Ist der Bereich gleichmäßig gefüllt (nur Füllgrau und Platzhalterschrift, kein Bildinhalt)?"""
    a = _pixel(pdf_pfad, fitz.Rect(rect) + (2, 2, -2, -2)).astype(int)
    fuell = np.bincount(a.ravel()).argmax()
    return float((np.abs(a - fuell) > 12).mean()) < 0.08


def test_hoch_lichtbild_wird_angehakt_angeboten_und_abgedeckt(tmp_path):
    rng = np.random.default_rng(21)
    pdf, foto, _ = ausweis_scan(tmp_path / "ausweis.pdf", rng, dpi=200)
    ocr = Attrappe({0: AUSWEIS_WOERTER + zeilenwoerter(["Name / Surname MUSTERMANN"])})
    e, s = _analyse_und_schwaerzung(pdf, ocr)
    (licht,) = [f for f in e["funde"] if f["kategorie"] == fotos.KAT_LICHTBILD]
    assert licht["anzeige"] == "Lichtbild (Ausweis)" and licht["ersatz"] == "[LICHTBILD]" and licht["text"] == ""
    assert all(st["an"] for st in licht["stellen"]) and licht["seiten"] == [1]
    assert abdeckung(foto, [st["bereich"] for st in licht["stellen"]]) >= 0.85
    assert "LICHTBILD" in {m["code"] for m in e["meldungen"]}
    assert s["ausgabe"] and s["lichtbilder_abgedeckt"] == 1
    assert _ohne_platzhalter_gleichmaessig(s["ausgabe"], foto & licht["stellen"][0]["bereich"])
    with fitz.open(s["ausgabe"]) as doc:
        assert "[LICHTBILD]" in doc[0].get_text()
    assert not any("Lichtbild" in g or "Ausweiskopie" in g for g in s["pruefen_gruende"])
    vorher = _pixel(pdf, foto).astype(float)
    assert vorher.std() > 20                          # im Original ist dort ein Bild (Kontrolle der Messung)


def test_lichtbild_auf_gedrehter_seite_abgedeckt(tmp_path):
    """Seite mit /Rotate 90: Analyse und Schwärzung arbeiten auf der entdrehten Seite – der Lichtbild-Bereich liegt
    in der Ausgabe dort, wo das Gesicht angezeigt wurde."""
    rng = np.random.default_rng(41)
    pdf, foto, _ = ausweis_scan(tmp_path / "ausweis.pdf", rng, dpi=200)
    with fitz.open(pdf) as doc:
        doc[0].set_rotation(90)
        angezeigt = foto * doc[0].rotation_matrix          # Lage des Gesichts, wie es angezeigt wird
        gedreht = tmp_path / "ausweis_gedreht.pdf"
        doc.save(gedreht)
    ocr = Attrappe({0: AUSWEIS_WOERTER + zeilenwoerter(["Name / Surname MUSTERMANN"])})
    e, s = _analyse_und_schwaerzung(gedreht, ocr)
    assert [f for f in e["funde"] if f["kategorie"] == fotos.KAT_LICHTBILD]
    assert s["ausgabe"] and s["lichtbilder_abgedeckt"] == 1
    with fitz.open(s["ausgabe"]) as aus:
        r = angezeigt * aus[0].derotation_matrix
    assert _ohne_platzhalter_gleichmaessig(s["ausgabe"], r)


def test_hoch_abgewaehltes_lichtbild_braucht_freigabe(tmp_path):
    """Abgewählt bleibt das Lichtbild stehen – die Ausgabe muss dann in der Vorschau freigegeben werden (auch wenn
    „Freigabe vor Weitergabe“ aus ist), statt still als „fertig“ hinauszugehen."""
    rng = np.random.default_rng(22)
    pdf, foto, _ = ausweis_scan(tmp_path / "ausweis.pdf", rng, dpi=200)
    ocr = Attrappe({0: AUSWEIS_WOERTER + zeilenwoerter(["Kontakt: erika.musterfrau@example.org"])})

    def abwaehlen(funde):
        for f in funde:
            if f["kategorie"] == fotos.KAT_LICHTBILD:
                for st in f["stellen"]:
                    st["an"] = False
    e, s = _analyse_und_schwaerzung(pdf, ocr, aendern=abwaehlen)
    assert any(f["kategorie"] == "email" for f in e["funde"]), e["funde"]
    assert s["status"] == "pruefen" and "Seite 1: Lichtbild nicht abgedeckt" in s["pruefen_gruende"]
    assert "_PRUEFEN" in Path(s["ausgabe"]).name
    assert not _ohne_platzhalter_gleichmaessig(s["ausgabe"], foto)


def test_ausweiskopie_ohne_gefundenes_lichtbild_braucht_freigabe(tmp_path):
    """Ausweistext auf dem Bild (hier: maschinenlesbare Zone der Rückseite), aber kein Lichtbild erkannt: das Gesicht
    kann trotzdem da sein – Warnung in der Analyse, Freigabe in der Vorschau nötig."""
    rng = np.random.default_rng(23)
    pdf, _, _ = ausweis_scan(tmp_path / "rueckseite.pdf", rng, dpi=200, rueckseite=True)
    ocr = Attrappe({0: [(95, 250, 400, 262, "IDD<<T220001294<<<<<<<<<<<<<<<"),
                        (95, 270, 400, 282, "6408125<2010315D<<<<<<<<<<<<<4")]
                    + zeilenwoerter(["Kontakt: erika.musterfrau@example.org"])})
    e, s = _analyse_und_schwaerzung(pdf, ocr)
    assert not [f for f in e["funde"] if f["kategorie"] == fotos.KAT_LICHTBILD]
    assert "AUSWEIS_OHNE_LICHTBILD" in {m["code"] for m in e["meldungen"] if m["art"] == "warnung"}
    assert s["status"] == "pruefen" and "Seite 1: Ausweiskopie – Lichtbild bitte selbst prüfen" in s["pruefen_gruende"]


def test_eingebettetes_passbild_wird_ganz_abgedeckt(tmp_path):
    """Nimmt das Foto mindestens die Hälfte eines eingebetteten Bilds ein (Passbild mit hellem Rand unten), deckt der
    Lichtbild-Fund das ganze Bild ab – nicht nur den erkannten Teil – und das Bild verschwindet aus der Ausgabe."""
    rng = np.random.default_rng(31)
    bild = np.full((560, 280, 3), 246, np.uint8)
    bild[:360] = fv.portraet(rng)
    doc = fitz.open()
    s = fv.textseite(doc, ["PERSONALAUSWEIS", "", "Antrag auf Ausstellung", "", "Name: Erika Musterfrau"])
    r = fitz.Rect(400, 60, 400 + 30 * MM, 60 + 60 * MM)
    s.insert_image(r, stream=fv.jpeg(bild, 85), keep_proportion=False)
    pdf = tmp_path / "antrag.pdf"
    doc.save(pdf)
    doc.close()
    teil = seitenbereiche(pdf, clip=r)
    assert teil and abdeckung(r, teil) < 0.9          # die Erkennung allein lässt den hellen Rand stehen
    e, s = _analyse_und_schwaerzung(pdf, Attrappe())
    (licht,) = [f for f in e["funde"] if f["kategorie"] == fotos.KAT_LICHTBILD]
    assert any(fitz.Rect(st["bereich"]).contains(r) for st in licht["stellen"]), licht["stellen"]
    assert s["ausgabe"] and s["lichtbilder_abgedeckt"] == 1
    with fitz.open(s["ausgabe"]) as aus:
        assert not aus[0].get_image_info()
        assert "[LICHTBILD]" in aus[0].get_text()


def test_fehler_der_bildpruefung_verlangt_freigabe(tmp_path, monkeypatch):
    """Scheitert die Bildprüfung einer Seite, bricht die Analyse nicht ab – sie warnt, und die Ausgabe muss in der
    Vorschau freigegeben werden (ein Lichtbild könnte unbemerkt stehen bleiben)."""
    doc = fitz.open()
    fv.textseite(doc, ["Kopie meines Personalausweises", "", "Kontakt: erika.musterfrau@example.org"])
    pdf = tmp_path / "brief.pdf"
    doc.save(pdf)
    doc.close()

    def kaputt(*a, **k):
        raise MemoryError("Probe")
    monkeypatch.setattr(fotos, "seite_pruefen", kaputt)
    e, s = _analyse_und_schwaerzung(pdf, Attrappe())
    assert any(m["code"] == "BILDER_UNGEPRUEFT" and m["art"] == "warnung" and "fehlgeschlagen" in m["text"]
               for m in e["meldungen"])
    assert any(f["kategorie"] == "email" for f in e["funde"])
    assert s["status"] == "pruefen" and "Seite 1: Bilder nicht geprüft" in s["pruefen_gruende"]


def test_hoch_sonstige_fotos_bleiben_unberuehrt(tmp_path):
    """Ohne Ausweis-Kontext bleibt ein Foto (Schadenfoto, Porträt im Brief) in „hoch“ stehen – mit dem bisherigen
    Hinweis, ohne Bildfund."""
    rng = np.random.default_rng(24)
    doc = fitz.open()
    s = fv.textseite(doc)
    r = fitz.Rect(70, 430, 70 + 120 * MM, 430 + 90 * MM)
    s.insert_image(r, stream=fv.jpeg(fv.objektfoto(rng), 70), keep_proportion=False)
    pdf = tmp_path / "schadenbrief.pdf"
    doc.save(pdf)
    doc.close()
    e, s = _analyse_und_schwaerzung(pdf, Attrappe())
    assert not [f for f in e["funde"] if f["kategorie"] in fotos.BILD_KATEGORIEN]
    assert s["lichtbilder_abgedeckt"] == 0 and s["bilder_abgedeckt"] == 0
    assert _pixel(s["ausgabe"], r).std() > 20
    assert "BILDER_UNGEPRUEFT" in {m["code"] for m in s["meldungen"]}


# ----------------------------------------------------------------------
# „maximal“: alle Rasterbilder auf Textseiten, Fotobereiche auf Scans
# ----------------------------------------------------------------------
def _inhalt_anhaengen(doc, s, c: bytes):
    alt = doc.xref_get_key(s.xref, "Contents")
    neu = doc.get_new_xref()
    doc.update_object(neu, "<<>>")
    doc.update_stream(neu, c, new=True)
    if alt[0] == "array":
        doc.xref_set_key(s.xref, "Contents", alt[1].rstrip()[:-1] + f" {neu} 0 R]")
    else:
        doc.xref_set_key(s.xref, "Contents", f"[{alt[1]} {neu} 0 R]" if alt[0] == "xref" else f"{neu} 0 R")


def _ressource(doc, s, schluessel, wert):
    art, res = doc.xref_get_key(s.xref, "Resources")
    if art == "xref":
        doc.xref_set_key(int(res.split()[0]), schluessel, wert)
    else:
        doc.xref_set_key(s.xref, "Resources/" + schluessel, wert)


def _bild_xref(doc, a: np.ndarray, extra: str = "") -> int:
    x = doc.get_new_xref()
    h, w = a.shape[:2]
    cs = "/DeviceGray" if a.ndim == 2 else "/DeviceRGB"
    doc.update_object(x, f"<</Type/XObject/Subtype/Image/Width {w}/Height {h}/ColorSpace {cs}/BitsPerComponent 8"
                         f"{extra}>>")
    doc.update_stream(x, np.ascontiguousarray(a).tobytes(), new=True)
    return x


def textseite_mit_allen_bildarten(pfad, rng) -> dict:
    """Textseite mit einem Passbild (XObject), einem Inline-Bild, einer Bildmaske (Unterschrift als Schablone), einem
    Bild mit SMask (Unterschrift im Alphakanal), einem Bild in einem Form-XObject (wie bild_als_pdf), einem Bild in
    einem Kachelmuster, einem ungenutzt mitgeschleppten Bild und einem winzigen Symbol. Rückgabe: Rechtecke je Art."""
    doc = fitz.open()
    s = fv.textseite(doc, fv.BRIEFTEXT[:4])
    rects = {}
    rects["xobject"] = fitz.Rect(400, 40, 480, 140)
    s.insert_image(rects["xobject"], stream=fv.jpeg(fv.portraet(rng, 120, 150), 85), keep_proportion=False)
    roh = fv.grau(fv.portraet(rng, 48, 60))
    rects["inline"] = fitz.Rect(60, 200, 108, 260)
    _inhalt_anhaengen(doc, s, b"q 48 0 0 60 60 582 cm BI /W 48 /H 60 /CS /G /BPC 8 ID " + roh.tobytes() + b" EI Q")
    maske = (fv.grau(fv.unterschrift(rng, 160, 56)) < 128)
    bits = np.packbits(~maske, axis=1)
    mx = doc.get_new_xref()
    doc.update_object(mx, "<</Type/XObject/Subtype/Image/Width 160/Height 56/ImageMask true/BitsPerComponent 1>>")
    doc.update_stream(mx, bits.tobytes(), new=True)
    rects["bildmaske"] = fitz.Rect(150, 200, 310, 256)
    _ressource(doc, s, "XObject", f"<</Msk {mx} 0 R>>")
    _inhalt_anhaengen(doc, s, b"q 0 0 0.5 rg 160 0 0 56 150 586 cm /Msk Do Q")
    alpha = (255 - fv.grau(fv.unterschrift(rng, 160, 56))).astype(np.uint8)
    pix = fitz.Pixmap(fitz.csRGB, 160, 56, np.dstack([np.zeros((56, 160, 3), np.uint8), alpha]).tobytes(), True)
    rects["smask"] = fitz.Rect(330, 200, 490, 256)
    s.insert_image(rects["smask"], pixmap=pix, keep_proportion=False)
    quelle = fitz.open()
    q = quelle.new_page(width=200, height=150)
    q.insert_image(q.rect, stream=fv.jpeg(fv.objektfoto(rng, 200, 150), 80), keep_proportion=False)
    rects["form"] = fitz.Rect(60, 300, 260, 450)
    s.show_pdf_page(rects["form"], quelle, 0)
    quelle.close()
    bx = _bild_xref(doc, fv.portraet(rng, 60, 75))
    px = doc.get_new_xref()
    doc.update_object(px, f"<</Type/Pattern/PatternType 1/PaintType 1/TilingType 1/BBox[0 0 60 75]/XStep 60/YStep 75"
                          f"/Resources<</XObject<</ImP {bx} 0 R>>>>>>")
    doc.update_stream(px, b"q 60 0 0 75 0 0 cm /ImP Do Q", new=True)
    _ressource(doc, s, "Pattern", f"<</P1 {px} 0 R>>")
    rects["muster"] = fitz.Rect(300, 300, 420, 450)
    _inhalt_anhaengen(doc, s, b"q /Pattern cs /P1 scn 300 392 120 150 re f Q")
    rects["symbol"] = fitz.Rect(60, 470, 72, 482)
    s.insert_image(rects["symbol"], stream=fv.png(np.full((16, 16, 3), 40, np.uint8)), keep_proportion=False)
    ungenutzt = _bild_xref(doc, fv.portraet(rng, 90, 110))
    art, res = doc.xref_get_key(s.xref, "Resources")
    ziel = int(res.split()[0]) if art == "xref" else s.xref
    doc.xref_set_key(ziel, ("" if art == "xref" else "Resources/") + "XObject/Ungenutzt", f"{ungenutzt} 0 R")
    doc.save(pfad)
    doc.close()
    return rects


def _bilddaten_in_ressourcen(pdf, nr=0) -> list:
    """(xref, Breite, Höhe) aller Bilder, die die Seite über ihre Ressourcen erreicht."""
    with fitz.open(pdf) as doc:
        xrefs = fotos.bilder_in_ressourcen(doc, doc[nr].xref)
        return sorted((x, int(doc.xref_get_key(x, "Width")[1]), int(doc.xref_get_key(x, "Height")[1]))
                      for x in xrefs)


def test_maximal_entfernt_jedes_rasterbild_einer_textseite(tmp_path):
    rng = np.random.default_rng(31)
    pdf = tmp_path / "allebilder.pdf"
    rects = textseite_mit_allen_bildarten(pdf, rng)
    vorher = _bilddaten_in_ressourcen(pdf)
    assert len([b for b in vorher if not fotos.bild_winzig(b[1], b[2])]) >= 5      # Kontrolle des Aufbaus
    e, s = _analyse_und_schwaerzung(pdf, Attrappe(), profil="maximal")
    (bild,) = [f for f in e["funde"] if f["kategorie"] == fotos.KAT_BILD]
    assert bild["ersatz"] == "[BILD]" and all(st["an"] for st in bild["stellen"])
    for art in ("xobject", "inline", "bildmaske", "smask", "form"):
        assert any(fitz.Rect(st["bereich"]).contains(rects[art]) for st in bild["stellen"]), art
    # Bilder in Kachelmustern meldet MuPDF an der Stelle der Musterzelle – ihre Daten leert die Nachkontrolle
    assert not any(fitz.Rect(st["bereich"]).contains(rects["symbol"]) for st in bild["stellen"]), "Symbol bleibt"
    assert s["ausgabe"] and s["bilder_abgedeckt"] == len(bild["stellen"])
    nachher = [b for b in _bilddaten_in_ressourcen(s["ausgabe"]) if not fotos.bild_winzig(b[1], b[2])]
    assert nachher == [], f"Bilddaten in der Ausgabe: {nachher}"
    with fitz.open(s["ausgabe"]) as doc:
        sichtbar = [(i["width"], i["height"]) for i in doc[0].get_image_info()
                    if not fotos.bild_winzig(i["width"], i["height"])]
        assert sichtbar == [] and "[BILD]" in doc[0].get_text()
        assert any(fotos.bild_winzig(i["width"], i["height"]) and i["width"] == 16 for i in doc[0].get_image_info())
    for art in ("xobject", "inline", "bildmaske", "smask", "form", "muster"):
        assert _ohne_platzhalter_gleichmaessig(s["ausgabe"], rects[art]), art
    texte = [m["text"] for m in s["meldungen"] if m["code"] == "BILDER_ABGEDECKT"]
    assert texte and "Bild(er)" in " ".join(texte)
    assert "BILDER_ABGEDECKT" in {m["code"] for m in e["meldungen"]}


def test_maximal_abgewaehltes_bild_bleibt_ohne_freigabezwang(tmp_path):
    rng = np.random.default_rng(32)
    doc = fitz.open()
    s = fv.textseite(doc)
    r = fitz.Rect(70, 430, 70 + 120 * MM, 430 + 90 * MM)
    s.insert_image(r, stream=fv.jpeg(fv.objektfoto(rng), 70), keep_proportion=False)
    pdf = tmp_path / "schaden.pdf"
    doc.save(pdf)
    doc.close()

    def abwaehlen(funde):
        for f in funde:
            if f["kategorie"] == fotos.KAT_BILD:
                for st in f["stellen"]:
                    st["an"] = False
    e, s = _analyse_und_schwaerzung(pdf, Attrappe(), profil="maximal", aendern=abwaehlen)
    assert _pixel(s["ausgabe"], r).std() > 20 and _bilddaten_in_ressourcen(s["ausgabe"])
    assert not any("Bild" in g for g in s["pruefen_gruende"])


def test_maximal_fotobereich_auf_scan_abgedeckt_text_bleibt(tmp_path):
    rng = np.random.default_rng(33)
    r = (60, 420, 60 + 110 * MM, 420 + 82 * MM)
    pdf = scan_mit(tmp_path / "scan.pdf", rng, [(fv.objektfoto(rng), r)], text=fv.BRIEFTEXT[:14], dpi=150)
    ocr = Attrappe({0: zeilenwoerter(["Ihre Schadenmeldung vom 14.02.2025"], x0=60, y0=180)})
    e, s = _analyse_und_schwaerzung(pdf, ocr, profil="maximal")
    (foto,) = [f for f in e["funde"] if f["kategorie"] == fotos.KAT_FOTO]
    assert abdeckung(r, [st["bereich"] for st in foto["stellen"]]) >= 0.9
    assert s["fotobereiche_abgedeckt"] == 1 and _ohne_platzhalter_gleichmaessig(s["ausgabe"], r)
    oben_vorher, oben = _pixel(pdf, (50, 60, 540, 300)), _pixel(s["ausgabe"], (50, 60, 540, 300))
    tinte_vorher, tinte = (oben_vorher < 160).mean(), (oben < 160).mean()
    assert tinte_vorher > 0.005 and tinte > 0.8 * tinte_vorher   # der Brieftext oberhalb des Fotos ist noch da


def test_maximal_geteiltes_woerterbuch_leert_kein_scanbild(tmp_path):
    """Befund 6a der Runde 3a: Textseite (ohne Fund) und Scan-Seite teilen EIN Ressourcen-Wörterbuch – die
    Nachkontrolle in „maximal“ leerte über die Textseite das Seitenbild des Scans (leere Seite in der Ausgabe)."""
    rng = np.random.default_rng(35)
    doc = fitz.open()
    fv.textseite(doc, ["Anlagen", "", "Die Unterlagen folgen auf der nächsten Seite."])
    scan = fv.textseite_bild(rng, zeilen=["KOSTENVORANSCHLAG Nr. 2025-117", "", "Malerbetrieb Beispiel GmbH",
                                         "Summe netto 1.234,00 EUR"], dpi=100, grau_=True)
    s2 = doc.new_page(width=595, height=842)
    s2.insert_image(s2.rect, stream=fv.jpeg(scan, 70), keep_proportion=False)
    x2 = s2.get_images()[0][0]
    schrift = doc.xref_get_key(doc[0].xref, "Resources/Font")[1]
    gemeinsam = doc.get_new_xref()
    doc.update_object(gemeinsam, f"<</Font {schrift}/XObject<</Scan {x2} 0 R>>>>")
    _inhalt_anhaengen(doc, s2, b"")
    doc.xref_set_key(s2.xref, "Contents", "[]")
    _inhalt_anhaengen(doc, s2, b"q 595 0 0 842 0 0 cm /Scan Do Q")
    for nr in (0, 1):
        doc.xref_set_key(doc[nr].xref, "Resources", f"{gemeinsam} 0 R")
    fv.textseite(doc, ["Kontakt für Rückfragen: erika.musterfrau@example.org"])
    pdf = tmp_path / "geteilt.pdf"
    doc.save(pdf, garbage=3)
    doc.close()
    ocr = Attrappe({1: [(60, 60, 300, 75, "KOSTENVORANSCHLAG"), (60, 100, 300, 115, "Malerbetrieb")]})
    e, s = _analyse_und_schwaerzung(pdf, ocr, profil="maximal")
    assert any(f["kategorie"] == "email" for f in e["funde"])
    assert s["bilder_geleert"] == 0
    with fitz.open(pdf) as vorher, fitz.open(s["ausgabe"]) as aus:
        assert [(i["width"], i["height"]) for i in aus[1].get_image_info()] == [(scan.shape[1], scan.shape[0])]
        p0, p1 = vorher[1].get_pixmap(dpi=40), aus[1].get_pixmap(dpi=40)
        assert p0.samples == p1.samples or np.abs(np.frombuffer(p0.samples, np.uint8).astype(int)
                                                  - np.frombuffer(p1.samples, np.uint8)).max() <= 8


def _grosses_bild_auf_textseite(pfad, rng, portraet: bool):
    """Textseite (Fließtext) mit einem Bild über rund zwei Drittel der Seite: ein Porträt bzw. ein fotografiertes
    Formular ohne Foto. Rückgabe: Rechteck des Bilds."""
    doc = fitz.open()
    s = fv.textseite(doc, ["Anlage zum Schreiben vom 12.03.2025 – Schadennummer 2025-00417 – Vollmacht und "
                           "Abtretungserklärung",
                           "Sehr geehrte Damen und Herren, anbei erhalten Sie die unterschriebene Vollmacht als Foto, "
                           "wie besprochen.",
                           "Bitte bestätigen Sie den Eingang kurz per E-Mail. Mit freundlichen Grüßen, Ihr Maklerbüro.",
                           "Kontakt: erika.musterfrau@example.org"], groesse=8.5, abstand=11)
    assert len(s.get_text()) > 300                         # genug Text: eine Textseite mit Bild, kein Scan
    if portraet:
        blatt = fv.portraet(rng, 700, 900)
    else:
        blatt = fv.textseite_bild(rng, zeilen=["VOLLMACHT", "", "Hiermit bevollmächtige ich die Firma",
                                              "Muster-Makler GmbH ...", "", "Köln, den 01.02.2025"], dpi=100,
                                  grau_=False)
    r = fitz.Rect(40, 160, 560, 800)
    s.insert_image(r, stream=fv.jpeg(blatt, 80), keep_proportion=False)
    doc.save(pfad)
    doc.close()
    return r


@pytest.mark.parametrize("abwaehlen", [False, True])
def test_maximal_grosses_foto_auf_textseite_folgt_der_vorschau(tmp_path, abwaehlen):
    """Befund 6b: Ein Bild über mehr als die Hälfte einer Textseite bleibt wie ein Scan stehen, abgedeckt wird der
    Fotobereich darin (Fund „Foto“). Abgewählt bleibt das Porträt ganz stehen – die Nachkontrolle leerte es vorher
    trotzdem (1 x 1)."""
    rng = np.random.default_rng(36)
    r = _grosses_bild_auf_textseite(tmp_path / "portraet.pdf", rng, portraet=True)

    def aendern(funde):
        for f in funde:
            if f["kategorie"] in fotos.BILD_KATEGORIEN:
                for st in f["stellen"]:
                    st["an"] = not abwaehlen
    e, s = _analyse_und_schwaerzung(tmp_path / "portraet.pdf", Attrappe(), profil="maximal", aendern=aendern)
    (foto,) = [f for f in e["funde"] if f["kategorie"] == fotos.KAT_FOTO]
    assert not [f for f in e["funde"] if f["kategorie"] == fotos.KAT_BILD]
    assert s["bilder_geleert"] == 0
    with fitz.open(s["ausgabe"]) as aus:
        assert [(i["width"], i["height"]) for i in aus[0].get_image_info()] == [(700, 900)]
    vorher = _pixel(tmp_path / "portraet.pdf", r).std()
    if abwaehlen:
        assert abs(_pixel(s["ausgabe"], r).std() - vorher) < 1.0
        assert not any("Bild" in g or "Foto" in g for g in s["pruefen_gruende"])
    else:
        assert s["fotobereiche_abgedeckt"] == 1
        assert _ohne_platzhalter_gleichmaessig(s["ausgabe"], fitz.Rect(foto["stellen"][0]["bereich"]) & r)


def test_maximal_formularhintergrund_bleibt_mit_hinweis(tmp_path):
    """Befund 6c: ein fotografiertes Formular ohne Foto über zwei Drittel einer Textseite – kein Bildfund, und es
    bleibt stehen (vorher leerte die Nachkontrolle es); die Analyse sagt das ausdrücklich."""
    rng = np.random.default_rng(37)
    r = _grosses_bild_auf_textseite(tmp_path / "formular.pdf", rng, portraet=False)
    e, s = _analyse_und_schwaerzung(tmp_path / "formular.pdf", Attrappe(), profil="maximal")
    assert not [f for f in e["funde"] if f["kategorie"] in fotos.BILD_KATEGORIEN]
    assert any(m["code"] == "BILDER_ABGEDECKT" and m["seite"] == 0 and "bleibt wie ein Scan stehen" in m["text"]
               for m in e["meldungen"])
    assert s["bilder_geleert"] == 0
    assert abs(_pixel(s["ausgabe"], r).std() - _pixel(tmp_path / "formular.pdf", r).std()) < 2.0


def test_maximal_musterbild_bleibt_auf_seite_mit_abwahl(tmp_path):
    """Abgewählt heißt abgewählt: auf einer Seite mit abgewähltem Bildbereich leert die Nachkontrolle auch kein Bild in
    einem Kachelmuster (dessen Bildbereich trägt keine xref)."""
    rng = np.random.default_rng(38)
    pdf = tmp_path / "allebilder.pdf"
    rects = textseite_mit_allen_bildarten(pdf, rng)

    def abwaehlen(funde):
        for f in funde:
            if f["kategorie"] == fotos.KAT_BILD:
                for st in f["stellen"]:
                    st["an"] = False
    e, s = _analyse_und_schwaerzung(pdf, Attrappe(), profil="maximal", aendern=abwaehlen)
    assert s["bilder_geleert"] == 0 and s["bilder_abgedeckt"] == 0
    assert not _ohne_platzhalter_gleichmaessig(s["ausgabe"], rects["muster"])
    assert not _ohne_platzhalter_gleichmaessig(s["ausgabe"], rects["xobject"])


def test_maximal_ohne_bilder_keine_bildfunde(tmp_path):
    doc = fitz.open()
    fv.textseite(doc)
    pdf = tmp_path / "nurtext.pdf"
    doc.save(pdf)
    doc.close()
    e, s = _analyse_und_schwaerzung(pdf, Attrappe(), profil="maximal")
    assert not [f for f in e["funde"] if f["kategorie"] in fotos.BILD_KATEGORIEN]
    assert s["bilder_abgedeckt"] == 0 and s["bilder_geleert"] == 0


def test_bildfunde_ohne_text_werden_nicht_weitergegeben_und_nicht_als_rest_gesucht(tmp_path):
    """Bildfunde haben keinen Text: die Weitergabe zwischen Dokumenten und die Selbstkontrolle (Textsuche) lassen sie
    aus; ein Wort „Lichtbild“ auf der Seite ist kein Rest."""
    rng = np.random.default_rng(34)
    pdf, _, _ = ausweis_scan(tmp_path / "ausweis.pdf", rng, dpi=150)
    ocr = Attrappe({0: AUSWEIS_WOERTER + zeilenwoerter(["Lichtbild", "Kontakt: erika.musterfrau@example.org"])})
    e, s = _analyse_und_schwaerzung(pdf, ocr)
    assert [f for f in e["funde"] if f["kategorie"] == fotos.KAT_LICHTBILD]
    assert s["reste"] == [] and s["stellen_nicht_lokalisiert"] == 0
    andere = {"funde": [], "modell": e["modell"], "nie": [], "aktive": e["aktive"], "profil": "hoch"}
    analyse.weitergabe_anwenden([e, andere])
    assert andere["funde"] and not [f for f in andere["funde"] if f["kategorie"] in fotos.BILD_KATEGORIEN]


# ----------------------------------------------------------------------
# Beschädigte Bilder: abgeschnittenes progressives JPEG (R-07, Runde 3)
# ----------------------------------------------------------------------
def _progressives_jpeg(rng, breite=420, hoehe=300) -> bytes:
    """MuPDF schreibt progressive JPEGs (10 Scans); Bild mit Textzeilen-artigen Streifen und Verlauf."""
    a = fv.objektfoto(rng, breite, hoehe)
    jpeg = fv.jpeg(a, 85)
    struktur = bilder.jpeg_struktur(jpeg)
    assert struktur["progressiv"] and len(struktur["scans"]) >= 6 and struktur["ende"]
    return jpeg


def _pdf_mit_jpeg_daten(pfad, voll, daten, rect=(72, 200, 492, 500), text=("Kontoauszug Erika Musterfrau",)):
    doc = fitz.open()
    s = doc.new_page()
    for i, z in enumerate(text):
        s.insert_text((72, 90 + 16 * i), z, fontsize=11)
    s.insert_image(fitz.Rect(rect), stream=voll, keep_proportion=False)
    x = s.get_images()[0][0]
    doc.update_stream(x, daten, compress=False)
    doc.xref_set_key(x, "Filter", "/DCTDecode")
    doc.save(pfad)
    doc.close()
    return Path(pfad)


@pytest.mark.parametrize("anteil", [0.08, 0.3, 0.6])
def test_abgeschnittenes_progressives_jpeg_ist_beschaedigt(tmp_path, anteil):
    """MuPDF zeigt ein progressives JPEG, dem spätere Scans fehlen, überall unscharf – ohne die Füllfläche eines
    abgebrochenen Baseline-JPEG. Es gilt trotzdem als beschädigt: BILD_BESCHAEDIGT in der Analyse, Grund „Bild
    beschädigt“ in der Schwärzung (Ausgabe _PRUEFEN)."""
    jpeg = _progressives_jpeg(np.random.default_rng(41))
    daten = jpeg[:int(len(jpeg) * anteil)]
    assert bilder.progressiv_unvollstaendig(daten)
    pdf = _pdf_mit_jpeg_daten(tmp_path / "defekt.pdf", jpeg, daten)
    assert analyse.bild_schaeden(pdf) == {0: bilder.SCHADEN_PROGRESSIV}
    e = analysiere_pdf(pdf, set(muster.PROFILE["hoch"]["aktive"]), [], [], ocr=Attrappe())
    assert "BILD_BESCHAEDIGT" in {m["code"] for m in e["meldungen"] if m["art"] == "warnung"}
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), ocr_cache=e["ocr_cache"], modell=e["modell"],
                      ziel_ordner=tmp_path / "aus")
    assert s["status"] == "pruefen" and any("Bild beschädigt" in g for g in s["pruefen_gruende"])


def test_vollstaendige_progressive_jpegs_sind_kein_schaden(tmp_path):
    """Kein Fehlalarm: vollständig, nur ohne Endmarke, oder nur im letzten Verfeinerungs-Scan gekürzt (alle Koeffizienten
    sind dann übertragen)."""
    jpeg = _progressives_jpeg(np.random.default_rng(42))
    for name, daten in (("voll", jpeg), ("ohne_endmarke", jpeg[:-2])):
        assert not bilder.progressiv_unvollstaendig(daten), name
        pdf = _pdf_mit_jpeg_daten(tmp_path / f"{name}.pdf", jpeg, daten)
        assert analyse.bild_schaeden(pdf) == {}, name
    assert not bilder.progressiv_unvollstaendig(jpeg[:int(len(jpeg) * 0.97)])
    assert bilder.jpeg_struktur(b"kein jpeg") is None and not bilder.progressiv_unvollstaendig(b"")


def test_grosse_jpegs_werden_verkleinert_dekodiert(tmp_path, monkeypatch):
    """Große JPEGs (48-MP-Fotos) werden für die Schadensprüfung verkleinert dekodiert (rund 20 statt 150 MB) – das
    Urteil bleibt dasselbe: ein abgebrochenes Baseline-JPEG mit halb sichtbarer Zeile bleibt „bricht mitten im Bild
    ab“, ein vollständiges ist kein Schaden."""
    from test_robustheit_analyse import BILD_ZEILEN, _text_jpeg
    voll, breite, hoehe = _text_jpeg(BILD_ZEILEN * 2)
    aufrufe = []
    original = bilder._verkleinert_dekodieren

    def spion(*a, **k):
        aufrufe.append(a[1:])
        return original(*a, **k)
    monkeypatch.setattr(bilder, "VERKLEINERT_AB_PIXEL", 1000)
    monkeypatch.setattr(bilder, "VERKLEINERT_MAX_KANTE", 200)
    monkeypatch.setattr(bilder, "_verkleinert_dekodieren", spion)
    defekt = _pdf_mit_jpeg_daten(tmp_path / "defekt.pdf", voll, voll[:int(len(voll) * 0.5)], rect=(0, 0, 595, 842),
                                 text=())
    assert analyse.bild_schaeden(defekt) == {0: bilder.SCHADEN_ABBRUCH}
    ganz = _pdf_mit_jpeg_daten(tmp_path / "ganz.pdf", voll, voll, rect=(0, 0, 595, 842), text=())
    assert analyse.bild_schaeden(ganz) == {}
    assert aufrufe and all(a == (breite, hoehe) for a in aufrufe)


# ----------------------------------------------------------------------
# Speicher: Neukodierung ohne Vollkopie, „Seite als Bild“ rechnet nie hoch
# ----------------------------------------------------------------------
def test_neukodierung_legt_keine_vollkopie_der_pixel_an(tmp_path):
    """Nach der Pixel-Schwärzung eines verlustfreien Bilds (2000 x 1500, 9 MB Pixel) kodiert bilder.py es neu, ohne
    die Pixel als Python-Bytes zu kopieren (früher: pix.samples für die zlib-Schätzung) – gemessen mit tracemalloc."""
    y, x = np.mgrid[:1500, :2000]
    a = np.dstack([(x / 8) % 256, (y / 6) % 256, ((x + y) / 14) % 256]).astype(np.uint8)
    doc = fitz.open()
    s = doc.new_page(width=600, height=450)
    s.insert_image(s.rect, pixmap=fitz.Pixmap(fitz.csRGB, 2000, 1500, a.tobytes(), False), keep_proportion=False)
    pdf = tmp_path / "verlustfrei.pdf"
    doc.save(pdf, deflate=True)
    doc.close()
    doc = fitz.open(pdf)
    s = doc[0]
    vorher = bilder.bildzustand(s)
    vorher[next(iter(vorher))]["laenge"] = None           # erzwingt die zlib-Schätzung
    s.add_redact_annot(fitz.Rect(100, 100, 200, 150), fill=(0.9, 0.9, 0.9))
    s.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
    geaendert = bilder.geaenderte_bilder(s, vorher)
    tracemalloc.start()
    anzahl = bilder.bilder_neu_kodieren(doc, geaendert)
    spitze = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    doc.close()
    assert anzahl == 1
    assert spitze < 0.5 * a.nbytes, f"Python-Spitze {spitze / 2**20:.1f} MB bei {a.nbytes / 2**20:.1f} MB Pixeln"


def test_seite_als_bild_rechnet_nie_hoch(tmp_path):
    """Eine Bildseite mit 100 dpi wird als Bild mit 100 dpi neu erzeugt (nicht mit 200 dpi hochgerechnet: doppelter
    Speicher ohne sichtbaren Gewinn); eine Textseite weiter mit 200 dpi."""
    rng = np.random.default_rng(51)
    scan = fv.textseite_bild(rng, dpi=100, grau_=True)
    pdf = tmp_path / "scan100.pdf"
    fv.scan_pdf(pdf, [scan], qualitaet=75)
    doc = fitz.open(pdf)
    bilder.seite_als_bild_schwaerzen(doc, doc[0], [fitz.Rect(60, 60, 200, 80)])
    (info,) = doc[0].get_image_info()
    assert abs(info["width"] - scan.shape[1]) <= 2, (info["width"], scan.shape)
    doc.close()
    doc = fitz.open()
    fv.textseite(doc)
    bilder.seite_als_bild_schwaerzen(doc, doc[0], [fitz.Rect(60, 60, 200, 80)])
    (info,) = doc[0].get_image_info()
    assert abs(info["width"] - 595 * 200 / 72) <= 2
    doc.close()
