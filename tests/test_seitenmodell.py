"""Tests für das Seitenmodell (anonymisierer/seitenmodell.py) und das Detektor-Register
(anonymisierer/detektoren): EIN logischer Text für Analyse, Schwärzung und Selbstkontrolle.

Belegt die Gutachten S-03 (Ligaturen), KQ-02 (Silbentrennung), S-02/EQ-02 (Formularfelder neben ihrem
Etikett), S-12 (Kammfelder), EQ-01 (OCR-Zeilenbildung), S-05 (Inhalt außerhalb der CropBox), S-16
(Versal-ẞ) und PERF-06/PERF-08 (keine Bilder im rawdict, Suchtexte nur einmal vorbereitet)."""

import random
from pathlib import Path

import pytest

import pymupdf as fitz

from anonymisierer import detektoren, seitenmodell as sm
from anonymisierer.detektoren import Kontext, Treffer
from anonymisierer.seitenmodell import dokument_aus_text, ganzwort_stellen

DATEN = Path(__file__).parent / "daten"
DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def baue(pfad: Path) -> sm.Dokument:
    doc = fitz.open(pfad)
    try:
        info = sm.dokument_vorbereiten(doc)
        return sm.dokument_aufbauen(info["dokument"], pfad)
    finally:
        doc.close()


def textseite(pfad, zeilen, fontsize=10, fontname="helv", fontfile=None, x=50, abstand=1.4):
    doc = fitz.open()
    seite = doc.new_page()
    y = 70
    for z in zeilen:
        if isinstance(z, tuple):           # (x, text) für Spalten
            for xx, t in z:
                seite.insert_text((xx, y), t, fontsize=fontsize, fontname=fontname, fontfile=fontfile)
        elif z:
            seite.insert_text((x, y), z, fontsize=fontsize, fontname=fontname, fontfile=fontfile)
        y += fontsize * abstand
    doc.save(pfad)
    doc.close()
    return Path(pfad)


def texte(dok, stellen):
    return [dok.text[s:e] for s, e in stellen]


# ----------------------------------------------------------------------
# Zeichenregeln: Ligaturen, NFC, Leerzeichen, Silbentrennung
# ----------------------------------------------------------------------
@pytest.mark.skipif(not DEJAVU.exists(), reason="DejaVuSans fehlt")
def test_ligaturen_werden_aufgeloest_und_zeigen_auf_dieselbe_glyphe(tmp_path):
    pdf = textseite(tmp_path / "lig.pdf", ["Frau Steﬃ Hoﬀmann und Herr Pfeiﬀer"], fontname="F0", fontfile=str(DEJAVU))
    dok = baue(pdf)
    seite = dok.seiten[0]
    assert "Steffi Hoffmann" in seite.text and "Pfeiffer" in seite.text
    s = seite.text.index("Steffi")
    glyphen = [seite.abbildung[i] for i in range(s + 3, s + 6)]          # "ffi"
    assert len(set(glyphen)) == 1 and seite.zeichen[glyphen[0]].c == "ﬃ"
    assert texte(seite, ganzwort_stellen(seite, "Steffi Hoffmann", "name")) == ["Steffi Hoffmann"]
    assert len(seite.rechtecke(s, s + len("Steffi Hoffmann"))) == 1


def test_nfc_nbsp_weiche_trennstriche_und_nullbreite():
    # Vertrag 12.7 (neu): ein weicher Trennstrich MITTEN in der Zeile mit sichtbarer Glyphe ist ein Bindestrich
    # (Windows-Textauslesung); reiner Text hat synthetische Glyphen mit Breite. Vorher entfiel er immer.
    dok = dokument_aus_text("Herr Mu\u0308ller\xa0wohnt in Ko\u0308ln, Muster\xadmann, Max\u200bMustermann")
    seite = dok.seiten[0]
    assert "Herr Müller wohnt in Köln, Muster-mann, MaxMustermann" == seite.text
    i = seite.text.index("ü")
    g = seite.abbildung[i]
    assert seite.zeichen[g].c == "u" and seite.zeichen[seite.verbunden[g]].c == "\u0308"
    s = seite.text.index("Muster-mann,")
    assert seite.zeichen[seite.abbildung[s + 6]].c == "\xad", "Bindestrich zeigt auf die Trennstrich-Glyphe"
    # ohne sichtbare Glyphe (Breite 0) entfällt er weiterhin und wird mit dem Wort geschwärzt
    roh = [(c, sm._rect(50 + 6 * k, 50, 50 + 6 * k + (0 if c == "\xad" else 6), 62), 60.0, 10.0, -1)
           for k, c in enumerate("Muster\xadmann")]
    s2 = sm._seite_aus_zeilen(0, fitz.Rect(0, 0, 595, 842), [sm._Rohzeile(0, roh)])
    assert s2.text == "Mustermann"
    assert any(s2.zeichen[x].c == "\xad" for x in s2.glyphen(0, 10)), "weicher Trennstrich mitschwärzen"


def test_silbentrennung_regeln():
    dok = dokument_aus_text("Herr Muster-\nmann und Frau Klein-\nHoffmann, Vertrags-\n4711 sowie Versicherungs-\n"
                            "Nr. 12 und Muster­\nfrau.")
    t = dok.seiten[0].text
    assert "Herr Mustermann und Frau Klein-Hoffmann, Vertrags-\n4711 sowie Versicherungs-Nr. 12 und Musterfrau." == t
    seite = dok.seiten[0]
    s = t.index("Mustermann")
    glyphen = seite.glyphen(s, s + len("Mustermann"))
    assert any(seite.zeichen[g].c == "-" for g in glyphen), "entfallener Trennstrich gehört zur Stelle"
    # Zeilen bleiben erhalten (Offsets ohne Trenner)
    assert [t[z.start:z.ende] for z in seite.zeilen][:2] == ["Herr Muster", "mann und Frau Klein-"]


def test_silbentrennung_pdf_wie_analyse_und_schwaerzung(tmp_path):
    """Gutachten KQ-02: dieselbe Regel für alle – der getrennte Name wird EIN Wort."""
    dok = baue(DATEN / "t02a.pdf")
    assert "Mustermann," in dok.text and "Muster-" not in dok.text
    stellen = ganzwort_stellen(dok.seiten[0], "Mustermann", "name")
    assert len(stellen) == 1
    rechtecke = dok.seiten[0].rechtecke(*stellen[0])
    assert len(rechtecke) == 2, "zwei Zeilen -> zwei Schwärzungsrechtecke"


def test_trennstrich_in_tabellenkopf_verbindet_keine_fremde_zeile():
    """Ein Zellentext 'Versicherungsschein-' rechts in der Kopfzeile darf nicht mit der nächsten Zeile
    (erste Spalte) verschmelzen (c_schadenmeldung)."""
    dok = baue(DATEN / "c_schadenmeldung.pdf")
    assert "Versicherungsschein-Adeyemi" not in dok.text
    assert "Adeyemi, Olumide" in dok.text


# ----------------------------------------------------------------------
# Struktur: Spalten, Zeilen, Blöcke
# ----------------------------------------------------------------------
def test_spalten_bleiben_als_tabulator_erkennbar(tmp_path):
    pdf = textseite(tmp_path / "tab.pdf", [((50, "Name"), (200, "Vorname"), (350, "Geburtsdatum")),
                                           ((50, "Mustermann"), (200, "Max"), (350, "02.09.1983")),
                                           "Name:   Max Mustermann        Tel. 0911 123456"])
    dok = baue(pdf)
    zeilen = dok.seiten[0].text.split("\n")
    assert zeilen[0] == "Name\t\tVorname\t\tGeburtsdatum"
    assert zeilen[1] == "Mustermann\t\tMax\t\t02.09.1983"
    assert zeilen[2] == "Name:   Max Mustermann        Tel. 0911 123456", "echte Leerzeichen bleiben"
    seite = dok.seiten[0]
    assert len(seite.zeilen) == 3 and seite.zeile_von(seite.text.index("Max")).id == 1
    assert {z.id for z in seite.zeilen_im_bereich(fitz.Rect(40, 60, 600, 71))} == {0}
    # Leerraum im Fundtext passt auf die Spaltengrenze
    assert texte(seite, ganzwort_stellen(seite, "Mustermann Max", "name")) == ["Mustermann\t\tMax"]


def test_luecke_ohne_leerzeichen_wird_tabulator():
    zeile = [("A", fitz.Rect(10, 0, 16, 10), 9.0, 10.0, -1), ("B", fitz.Rect(16, 0, 22, 10), 9.0, 10.0, -1),
             ("C", fitz.Rect(60, 0, 66, 10), 9.0, 10.0, -1)]

    class FakeSeite:
        rect = fitz.Rect(0, 0, 200, 100)

        @staticmethod
        def get_text(art, flags=0, textpage=None):
            return {"blocks": [{"type": 0, "lines": [{"dir": (1, 0), "wmode": 0, "spans": [
                {"size": 10, "chars": [{"c": c, "bbox": tuple(r), "origin": (r.x0, g)} for c, r, g, *_ in zeile]}]}]}]}
    zeilen = sm._textzeilen(FakeSeite())
    seite = sm._seite_aus_zeilen(0, FakeSeite.rect, zeilen)
    assert seite.text == "AB\tC" and seite.abbildung[2] == -1


def test_ocr_woerter_zeilenbildung_eq01():
    """Gutachten EQ-01: OCR-Kästen höher als der Zeilenabstand dürfen Nachbarzeilen nicht verschmelzen."""
    woerter = []
    for zeile, text in enumerate(["auf Ihr Konto IBAN DE44 5001 0517 5407 3249 31",
                                  "Frau Nowak, da Sie in Höhe im Jahr 2024 insgesamt keine",
                                  "Telefon 089 2160-4477 oder per E-Mail"]):
        y = 100 + zeile * 9.6
        x = 50
        for wort in text.split():
            breite = 6 * len(wort)
            woerter.append((x, y - 10, x + breite, y + 10, wort))      # 20 pt hohe Kästen
            x += breite + 4
    random.Random(1).shuffle(woerter)
    zeilen = sm.woerter_zu_zeilen(woerter)
    assert [" ".join(w[4] for w in z) for z in zeilen] == [
        "auf Ihr Konto IBAN DE44 5001 0517 5407 3249 31",
        "Frau Nowak, da Sie in Höhe im Jahr 2024 insgesamt keine",
        "Telefon 089 2160-4477 oder per E-Mail"]


def test_ocr_zeichen_anteilig_und_wortboxen_beim_schwaerzen(tmp_path):
    doc = fitz.open()
    doc.new_page()
    pdf = tmp_path / "leer.pdf"
    doc.save(pdf)
    doc.close()
    woerter = [(50, 90, 110, 102, "Max"), (115, 90, 200, 102, "Mustermann,"), (50, 110, 80, 122, "IBAN")]
    d = fitz.open(pdf)
    seite = sm.seite_aufbauen(d[0], 0, ocr_woerter=woerter)
    d.close()
    assert seite.text == "Max Mustermann,\nIBAN" and seite.quelle == "ocr"
    s, e = ganzwort_stellen(seite, "Max Mustermann", "name")[0]
    teile = seite.rechtecke(s, e)
    assert len(teile) == 1
    r = teile[0][0]
    assert r.x0 <= 50 - 1 and r.x1 >= 200 + 1, "ganze Wortboxen (mit Komma) + Rand"
    z = seite.zeichen[seite.abbildung[s + 1]]
    assert abs(z.rect.width - 20) < 0.01 and z.quelle == "ocr"


# ----------------------------------------------------------------------
# Formularfelder
# ----------------------------------------------------------------------
def _formular(pfad, kamm=False, rotate=0):
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((50, 100), "Geburtsdatum:", fontsize=10)
    seite.insert_text((50, 140), "Name:", fontsize=10)
    seite.insert_text((50, 300), "Seite 1 von 1", fontsize=10)
    for name, wert, rect, flags in (("geb", "30071988" if kamm else "30.07.1988", fitz.Rect(150, 88, 300, 106),
                                     fitz.PDF_TX_FIELD_IS_COMB if kamm else 0),
                                    ("name", "Giovanni Esposito", fitz.Rect(150, 128, 300, 146), 0)):
        w = fitz.Widget()
        w.field_name, w.field_type, w.rect, w.field_value = name, fitz.PDF_WIDGET_TYPE_TEXT, rect, wert
        if flags:
            w.field_flags = flags
            w.text_maxlen = 8
        seite.add_widget(w)
    if rotate:
        seite.set_rotation(rotate)
    doc.save(pfad)
    doc.close()
    return Path(pfad)


@pytest.mark.parametrize("rotate", [0, 90])
def test_formularwerte_stehen_hinter_ihrem_etikett(tmp_path, rotate):
    """Gutachten S-02/EQ-02: MuPDF hängt eingebrannte Feldwerte ans Seitenende – im Modell stehen sie
    hinter ihrem Etikett, Dokument.felder kennt Feldname, Etikett, Wert und Stelle."""
    dok = baue(_formular(tmp_path / "f.pdf", rotate=rotate))
    t = dok.seiten[0].text
    if rotate == 0:
        assert t.split("\n")[:2] == ["Geburtsdatum:\t\t30.07.1988", "Name:\t\tGiovanni Esposito"]
    felder = {f.name: f for f in dok.felder}
    assert set(felder) == {"geb", "name"}
    for f in felder.values():
        assert t[f.start:f.ende] == f.wert
    if rotate == 0:
        assert felder["geb"].etikett == "Geburtsdatum:" and felder["name"].etikett == "Name:"
    assert t.count("Giovanni Esposito") == 1, "Werte nicht doppelt eingebrannt"


def test_kammfeld_wird_ein_wort(tmp_path):
    """Gutachten S-12: Kammfeld '3 0 0 7 1 9 8 8' -> '30071988' (lokalisierbar und erkennbar)."""
    dok = baue(_formular(tmp_path / "kamm.pdf", kamm=True))
    assert "Geburtsdatum:\t\t30071988" in dok.text
    feld = next(f for f in dok.felder if f.name == "geb")
    assert dok.seiten[0].text[feld.start:feld.ende] == "30071988"
    assert ganzwort_stellen(dok, "30071988", "kennung")


def test_echtes_antragsformular_felder(tmp_path):
    dok = baue(DATEN / "d_antrag_formular.pdf")
    assert "Geburtsdatum:\t\t30.07.1988" in dok.text
    feld = next(f for f in dok.felder if f.name == "geburtsdatum")
    assert feld.etikett == "Geburtsdatum:" and dok.seiten[feld.seite].text[feld.start:feld.ende] == "30.07.1988"


# ----------------------------------------------------------------------
# Vorbereitung: Ebenen, ActualText, CropBox, Drehung
# ----------------------------------------------------------------------
def test_ausgeblendete_ebene_wird_sichtbar_und_gemerkt(tmp_path):
    doc = fitz.open()
    s = doc.new_page()
    s.insert_text((50, 80), "Sichtbar", fontsize=11)
    ocg = doc.add_ocg("Intern", on=False)
    s.insert_text((50, 120), "Geheim Mustermann", fontsize=11, oc=ocg)
    pdf = tmp_path / "ebene.pdf"
    doc.save(pdf)
    doc.close()
    d = fitz.open(pdf)
    info = sm.dokument_vorbereiten(d)
    assert info["dokument"] is not d and info["versteckt"].get(0)
    dok = sm.dokument_aufbauen(info["dokument"], pdf)
    assert "Geheim Mustermann" in dok.text
    d.close()


def test_text_ausserhalb_der_cropbox_gehoert_nicht_zum_modell(tmp_path):
    """Gutachten S-05 (Entscheidung): Inhalt außerhalb des sichtbaren Bereichs wird nicht analysiert,
    sondern von der Schwärzung entfernt (siehe test_schwaerzung)."""
    doc = fitz.open()
    s = doc.new_page()
    s.insert_text((50, 80), "Innen Text", fontsize=11)
    s.insert_text((50, 800), "Unten Mustermann", fontsize=11)
    s.set_cropbox(fitz.Rect(0, 0, 595, 700))
    pdf = tmp_path / "crop.pdf"
    doc.save(pdf)
    doc.close()
    assert baue(pdf).text == "Innen Text"


def test_actualtext_wird_vor_dem_lesen_entfernt():
    strom = (b"/Span <</ActualText (Tel. (0221) Max) >> BDC BT /F1 10 Tf (XXX) Tj ET EMC "
             b"/Figure <</Alt <4d61> >> BDC q Q EMC /Span /MC0 BDC EMC")
    neu = sm.markierungen_entfernen(strom)
    assert b"ActualText" not in neu and b"Alt" not in neu and b"(XXX) Tj" in neu
    assert b"/Span <<>> BDC" in neu and b"/MC0" not in neu


def test_fingerabdruck_gleich_und_ungleich(tmp_path):
    pdf = textseite(tmp_path / "a.pdf", ["Herr Max Mustermann", "IBAN DE89 3704 0044 0532 0130 00"])
    a, b = baue(pdf), baue(pdf)
    assert a.fingerabdruck == b.fingerabdruck and a.seiten[0].fingerabdruck == b.seiten[0].fingerabdruck
    anders = baue(textseite(tmp_path / "b.pdf", ["Herr Max Mustermann", "IBAN DE89 3704 0044 0532 0130 01"]))
    assert anders.fingerabdruck != a.fingerabdruck


def test_dokument_offsets_ueber_seiten(tmp_path):
    doc = fitz.open()
    for t in ("Seite eins Max", "Seite zwei Max"):
        doc.new_page().insert_text((50, 72), t, fontsize=11)
    pdf = tmp_path / "zwei.pdf"
    doc.save(pdf)
    doc.close()
    dok = baue(pdf)
    assert dok.text == "Seite eins Max\n\f\nSeite zwei Max"
    stellen = ganzwort_stellen(dok, "Max", "name")
    assert [dok.seite_von(s) for s, _ in stellen] == [0, 1]
    assert dok.lokal(*stellen[1]) == [(1, 11, 14)]
    assert dok.global_(1, 11) == stellen[1][0]
    assert dok.lokal(0, len(dok.text)) == [(0, 0, 14), (1, 0, 14)]


def test_rechtecke_textebene_gekuerzt_und_wort_an(tmp_path):
    pdf = textseite(tmp_path / "r.pdf", ["Herr Max Mustermann wohnt hier"], fontsize=10)
    dok = baue(pdf)
    seite = dok.seiten[0]
    s, e = ganzwort_stellen(seite, "Mustermann", "name")[0]
    r, box, groesse, grundlinie = seite.rechtecke(s, e)[0]
    assert groesse == 10 and r.height < box.height and abs(r.y1 - (grundlinie + 0.2)) < 0.01
    mitte = fitz.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
    assert seite.wort_an(mitte) == (s, e)
    assert [w[1] for w in seite.woerter()] == ["Herr", "Max", "Mustermann", "wohnt", "hier"]


def test_rawdict_ohne_bilder():
    """Gutachten PERF-06: Bilder werden beim Lesen nie mitkodiert."""
    assert not sm.TEXT_FLAGS & fitz.TEXT_PRESERVE_IMAGES


# ----------------------------------------------------------------------
# Vergleicher
# ----------------------------------------------------------------------
def test_modus_name_alle_schreibweisen_aber_nicht_klein():
    dok = dokument_aus_text("Herrn MAX MUSTERMANN\nSehr geehrter Herr Max Mustermann, max mustermann.\n"
                            "Herr Klein ist klein. Frau GROẞ, Herr GROSS, Herr Groß ist groß. Mustermanns Vertrag.")
    assert texte(dok, ganzwort_stellen(dok, "Max Mustermann", "name")) == ["MAX MUSTERMANN", "Max Mustermann"]
    assert texte(dok, ganzwort_stellen(dok, "MAX MUSTERMANN", "name")) == ["MAX MUSTERMANN", "Max Mustermann"]
    assert texte(dok, ganzwort_stellen(dok, "Klein", "name")) == ["Klein"]
    assert texte(dok, ganzwort_stellen(dok, "Groß", "name")) == ["GROẞ", "GROSS", "Groß"]
    assert texte(dok, ganzwort_stellen(dok, "Mustermann", "name"))[-1] == "Mustermanns", "Genitiv-s"


def test_modus_kennung_trennzeichen_flexibel():
    dok = dokument_aus_text("IBAN DE89 3704 0044 0532 0130 00 und DE89370400440532013000, de89-3704-0044-0532-0130-00\n"
                            "Tel. (0911) 123456, 0911/123456, 0911-123456, 0911123456 und Kennzeichen N-AB 1234, N AB 1234")
    assert len(ganzwort_stellen(dok, "DE89 3704 0044 0532 0130 00", "kennung")) == 3
    assert len(ganzwort_stellen(dok, "0911 123456", "kennung")) == 4
    assert texte(dok, ganzwort_stellen(dok, "N-AB 1234", "kennung")) == ["N-AB 1234", "N AB 1234"]
    assert ganzwort_stellen(dok, "NAB 1234", "kennung") == [], "zwischen Buchstaben bleibt der Trenner Pflicht"
    kurz = dokument_aus_text("geb. 1.3.80, Betrag 1380 EUR")
    assert texte(kurz, ganzwort_stellen(kurz, "1.3.80", "kennung")) == ["1.3.80"], "kurze Kennung: Trenner Pflicht"


def test_modus_begriff_und_leerraum():
    dok = dokument_aus_text("Kostenstelle 4711\nKostenstelle\n4711, kostenstelle 4711x, Allianzarena, Allianz")
    assert texte(dok, ganzwort_stellen(dok, "Kostenstelle 4711", "begriff")) == ["Kostenstelle 4711", "Kostenstelle\n4711"]
    assert texte(dok, ganzwort_stellen(dok, "allianz", "begriff")) == ["Allianz"]


_WOERTER = ["Max", "Mustermann", "klein", "Klein", "Berg", "Heidelberg", "Bergstraße", "lange", "Lange", "groß",
            "Groß", "Hans", "Hansestadt", "Lang", "langfristig", "4711", "DE89", "3704", "Weber", "Webers", "Peter",
            "Peters", "Ali", "Qualität", "Bad", "Salzuflen", "Müller-Lüdenscheidt", "Müller"]


def test_eigenschaft_ganzwort_nie_innerhalb_eines_laengeren_worts():
    """Eigenschaftstest: Eine Stelle beginnt und endet nie mitten in einem Wort (außer dem Genitiv-s)."""
    zufall = random.Random(4711)
    for _ in range(200):
        woerter = [zufall.choice(_WOERTER) for _ in range(40)]
        trenner = [zufall.choice([" ", " ", "\n", ", ", "-", ". "]) for _ in woerter]
        text = "".join(w + t for w, t in zip(woerter, trenner))
        dok = dokument_aus_text(text)
        for nadel in set(_WOERTER):
            for modus in ("name", "begriff", "kennung"):
                for s, e in ganzwort_stellen(dok, nadel, modus):
                    t = dok.text
                    assert s == 0 or not t[s - 1].isalnum(), (nadel, modus, t[max(0, s - 5):e + 5])
                    assert e == len(t) or not t[e].isalnum(), (nadel, modus, t[max(0, s - 5):e + 5])


@pytest.mark.parametrize("name, woerter", [("Klein", ["klein", "kleine"]), ("Groß", ["groß", "großen"]),
                                           ("Lange", ["lange", "langen"]), ("Weber", ["weber"])])
def test_eigenschaft_namen_treffen_keine_kleingeschriebenen_woerter(name, woerter):
    for wort in woerter:
        dok = dokument_aus_text(f"Das ist {wort}, sehr {wort}. Ein {wort} Haus.")
        assert ganzwort_stellen(dok, name, "name") == [], (name, wort)
        assert ganzwort_stellen(dok, name.upper(), "name") == [], (name, wort)


def test_suchtexte_werden_nur_einmal_vorbereitet(monkeypatch):
    """Gutachten PERF-08: kein Neu-Normalisieren je Fund und Seite."""
    aufrufe = []
    echt = sm._Nadel.__init__

    def zaehlen(self, text, modus):
        aufrufe.append((text, modus))
        echt(self, text, modus)
    monkeypatch.setattr(sm._Nadel, "__init__", zaehlen)
    sm._NADEL_CACHE.clear()
    seiten = [dokument_aus_text(f"Seite {i}: Herr Max Mustermann") for i in range(30)]
    for s in seiten:
        assert ganzwort_stellen(s, "Max Mustermann", "name")
    assert aufrufe.count(("Max Mustermann", "name")) == 1


def test_ganzwort_stellen_lehnt_unbekannten_modus_ab():
    with pytest.raises(ValueError):
        ganzwort_stellen("Text", "Text", "ungefaehr")


# ----------------------------------------------------------------------
# Detektor-Register
# ----------------------------------------------------------------------
@pytest.fixture
def register(monkeypatch):
    monkeypatch.setattr(detektoren, "REGISTER", list(detektoren.REGISTER))
    return detektoren.REGISTER


def test_register_dekorator_doppelt_und_ersetzen(register):
    @detektoren.detektor("test.eins", {"iban"})
    def eins(dok, kontext):
        return [Treffer(0, 4, "iban", "test.eins", 1.0)]
    assert any(e.name == "test.eins" for e in register)
    with pytest.raises(ValueError):
        detektoren.registrieren("test.eins", {"iban"}, funktion=eins)

    @detektoren.detektor("test.eins", {"iban"}, ersetzt=True)
    def zwei(dok, kontext):
        return [Treffer(0, 4, "iban", "test.zwei", 1.0)]
    assert [e.funktion for e in register if e.name == "test.eins"] == [zwei]


def test_alle_treffer_filtert_kategorien_profile_und_meldet_fehler(register):
    register.clear()
    dok = dokument_aus_text("  DE89 und Max  ")

    @detektoren.detektor("test.iban", {"iban"})
    def iban(dok, kontext):
        return [Treffer(0, 7, "iban", "t"), Treffer(9, 12, "namen", "t")]

    @detektoren.detektor("test.maximal", {"iban"}, profile={"maximal"})
    def nur_maximal(dok, kontext):
        return [Treffer(2, 6, "iban", "maximal")]

    @detektoren.detektor("test.kaputt", {"iban"})
    def kaputt(dok, kontext):
        raise RuntimeError("Absicht")
    fehler = []
    treffer = detektoren.alle_treffer(dok, Kontext({"iban"}, "hoch"), fehler)
    assert treffer == [Treffer(2, 6, "iban", "t")], "Leerraum abgeschnitten, inaktive Kategorie gefiltert"
    assert fehler and "test.kaputt" in fehler[0] and "Absicht" in fehler[0]
    assert {t.quelle for t in detektoren.alle_treffer(dok, Kontext({"iban"}, "maximal"))} == {"t", "maximal"}


def test_klassische_detektoren_sind_registriert():
    namen = {e.name for e in detektoren.REGISTER}
    assert {"ner", "immer", "muster.iban", "muster.telefon", "klassisch.formularfeld"} <= namen
    assert not detektoren.LADEFEHLER


# ----------------------------------------------------------------------
# Vorschau-Engine (Vertrag Abschnitt 8): Koordinaten aus demselben Modell
# ----------------------------------------------------------------------
@pytest.mark.parametrize("rotate", [0, 90])
def test_vorschau_daten_und_seitenbild_passen_zum_modell(tmp_path, rotate):
    from anonymisierer import vorschau
    from anonymisierer.analyse import analysiere_pdf
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((60, 100), "Versicherungsnehmer: Max Mustermann", fontsize=12)
    seite.insert_text((60, 130), "IBAN DE89 3704 0044 0532 0130 00", fontsize=12)
    if rotate:
        seite.set_rotation(rotate)
    pdf = tmp_path / f"v{rotate}.pdf"
    doc.save(pdf)
    doc.close()
    e = analysiere_pdf(pdf, {"iban"}, [], ["Max Mustermann"])
    daten = vorschau.vorschau_daten(e, 0)
    assert daten["seitenrect"] == e["modell"].seiten[0].rect
    ids = {f["id"] for f in e["funde"]}
    assert {s[1] for s in daten["stellen"]} == ids and all(s[3] is True for s in daten["stellen"])
    assert all(daten["seitenrect"].contains(s[0]) for s in daten["stellen"])
    woerter = {w[1]: w for w in daten["woerter"]}
    text = e["modell"].seiten[0].text
    assert "Mustermann" in woerter and text[woerter["Mustermann"][2]:woerter["Mustermann"][3]] == "Mustermann"
    png, faktor = vorschau.seite_bild(pdf, 0, 1.5)
    assert png[:4] == b"\x89PNG" and faktor == 1.5
    bild = fitz.Pixmap(png)
    assert abs(bild.width - daten["seitenrect"].width * 1.5) <= 1
    assert abs(bild.height - daten["seitenrect"].height * 1.5) <= 1
    # Unter einer Fundstelle liegen dunkle Pixel (Text an derselben Stelle wie im Modell)
    r = next(s[0] for s in daten["stellen"])
    if r.width >= r.height:
        punkte = [(r.x0 + r.width * t, r.y0 + r.height / 2) for t in (0.1, 0.3, 0.5, 0.7, 0.9)]
    else:
        punkte = [(r.x0 + r.width / 2, r.y0 + r.height * t) for t in (0.1, 0.3, 0.5, 0.7, 0.9)]
    werte = [min(bild.pixel(int(x * 1.5) + dx, int(y * 1.5) + dy)[0] for dx in (-1, 0, 1) for dy in (-1, 0, 1))
             for x, y in punkte]
    assert min(werte) < 128, werte
    vorschau.zwischenspeicher_leeren()


def test_ausgabe_vorschau_mit_verdacht(tmp_path):
    from collections import namedtuple

    from anonymisierer import vorschau
    pdf = textseite(tmp_path / "aus.pdf", ["Text"])
    Verdacht = namedtuple("Verdacht", "seite start ende text grund rechtecke")
    v = [Verdacht(0, 0, 4, "Text", "Test", [fitz.Rect(50, 60, 80, 72)]), Verdacht(1, 0, 1, "x", "andere Seite", [])]
    aus = vorschau.ausgabe_vorschau(pdf, v, 0, 1.0)
    assert aus["bild"][:4] == b"\x89PNG" and len(aus["verdacht"]) == 1 and aus["verdacht"][0]["grund"] == "Test"


# ----------------------------------------------------------------------
# Blocksatz mit einzeln gesetzten Wörtern vs. Tabellenzeile (Entwicklungs-Benchmark 015_zweispaltig:
# "Konto DE83 2540 …" zerfiel in Zellen, die IBAN wurde nicht mehr erkannt)
# ----------------------------------------------------------------------
def _woerter_setzen(seite, y, woerter, x0=50, fontsize=10, luecken=None):
    """Jedes Wort einzeln setzen (wie Blocksatz-Generatoren); luecken in pt (Standard: 0,83 em)."""
    x = x0
    for i, w in enumerate(woerter):
        seite.insert_text((x, y), w, fontsize=fontsize)
        x += fitz.get_text_length(w, fontsize=fontsize)
        x += (luecken[i] if luecken else 0.83 * fontsize) if i < len(woerter) - 1 else 0


def test_blocksatz_mit_einzeln_gesetzten_woertern_bleibt_fliesstext(tmp_path):
    doc = fitz.open()
    seite = doc.new_page()
    _woerter_setzen(seite, 100, "dem Konto DE89 3704 0044 0532 0130 00 belastet.".split())
    _woerter_setzen(seite, 140, ["Name", "Geburtsdatum", "Betrag"], luecken=[60, 15])      # Tabelle
    pdf = tmp_path / "blocksatz.pdf"
    doc.save(pdf)
    doc.close()
    with fitz.open(pdf) as d:
        info = sm.dokument_vorbereiten(d)
        dok = sm.dokument_aufbauen(info["dokument"], pdf, vorbereitung=info)
    zeilen = dok.text.split("\n")
    assert "dem Konto DE89 3704 0044 0532 0130 00 belastet." in zeilen, zeilen
    assert "Name" + sm.SPALTENTRENNER + "Geburtsdatum" + sm.SPALTENTRENNER + "Betrag" in zeilen, zeilen
    from anonymisierer.analyse import analysiere_pdf
    e = analysiere_pdf(pdf, {"iban"}, [], [])
    assert [f["text"] for f in e["funde"]] == ["DE89 3704 0044 0532 0130 00"]


# ----------------------------------------------------------------------
# Vertrag 12.7: Unicode-Normalisierung (Befund Windows-CI: NBSP statt Leerzeichen, sichtbarer U+00AD statt
# Bindestrich, U+2011 in Nummern)
# ----------------------------------------------------------------------
def test_normalisiere_text_regeln_und_abbildung():
    roh = ("Noémie Bonnet 51­633867 Tel‑0421 3498­936 a.krause@schwarzwald­versicherung.de "
           "１２ 3–4 5−6 x y　z A – B Versicherungs­\nnehmer Klein­\nHoffmann")
    text, abbildung = sm.normalisiere_text(roh)
    assert text == ("Noémie Bonnet 51-633867 Tel-0421 3498-936 a.krause@schwarzwald-versicherung.de 12 3-4 5-6 "
                    "x y z A – B Versicherungsnehmer Klein-Hoffmann")
    assert len(abbildung) == len(text)
    for i, j in enumerate(abbildung):
        if j >= 0 and text[i].isalnum() and roh[j].isascii():
            assert roh[j] == text[i]
    assert roh[abbildung[text.index("12")]] == "１"
    assert sm.normalisiere_text("") == ("", [])
    # Suchtexte folgen derselben Regel
    assert sm.suchtext_normalisieren("schwarzwald­versicherung 3–4 Tel‑0421 １") == \
        "schwarzwald-versicherung 3-4 Tel-0421 1"


@pytest.mark.skipif(not DEJAVU.exists(), reason="DejaVuSans fehlt")
def test_windows_sonderzeichen_im_seitentext(tmp_path):
    pdf = textseite(tmp_path / "win.pdf", ["Versicherungsnehmerin Noémie Bonnet",
                                           "Kundennummer 51­633867, Telefon 0421 3498­936",
                                           "a.krause@schwarzwald­versicherung.de, Mobil 0171‑2345678",
                                           "Zeitraum 3–4 Wochen, Abzug −5 EUR",
                                           "Versicherungs­", "nehmer Klein­", "Hoffmann"],
                    fontname="F0", fontfile=str(DEJAVU))
    dok = baue(pdf)
    t = dok.text
    for erwartet in ("Noémie Bonnet", "51-633867", "0421 3498-936", "a.krause@schwarzwald-versicherung.de",
                     "0171-2345678", "3-4 Wochen", "Versicherungsnehmer Klein-Hoffmann"):
        assert erwartet in t, (erwartet, t)
    assert "−5 EUR" in t                      # Minus nicht zwischen Ziffern: unverändert
    # sichtbarer weicher Trennstrich zeigt auf seine Glyphe (wird mitgeschwärzt)
    s = dok.seiten[0]
    i = t.index("51-633867") + 2
    assert s.abbildung[i] >= 0 and s.zeichen[s.abbildung[i]].c == "­"


def test_rueckfall_detektoren_sind_reihenfolge_unabhaengig(register, monkeypatch):
    """klassisch.py registriert nur_wenn_frei: lädt ein Ersatzmodul (Agent "regeln") VOR klassisch, bleibt
    dessen "ner"; lädt es danach, ersetzt es mit ersetzt=True. Kein ValueError, kein Ladefehler."""
    import importlib

    from anonymisierer.detektoren import klassisch

    def eigene(dok, kontext):
        return []
    register.clear()
    detektoren.registrieren("ner", {"namen"}, funktion=eigene)        # Ersatz zuerst geladen
    monkeypatch.setattr(detektoren, "LADEFEHLER", [])
    importlib.reload(klassisch)                                          # Rückfall danach: kein Fehler
    assert [e.funktion for e in register if e.name == "ner"] == [eigene]
    assert any(e.name == "muster.iban" for e in register)
    detektoren.registrieren("ner", {"namen"}, funktion=klassisch.namen_erkennen, ersetzt=True)
    detektoren.registrieren("ner", {"namen"}, funktion=eigene, ersetzt=True)   # Ersatz danach geladen
    assert [e.funktion for e in register if e.name == "ner"] == [eigene]
