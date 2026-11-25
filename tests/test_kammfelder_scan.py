"""Kammfelder auf Scans (Kästchen „je Kästchen ein Zeichen“): Erkennung im Bild (kammraster.py), Linien vor der
Texterkennung entfernen und Lage weitergeben (ocr.py), Inhalt hinter einem Feldnamen für Personenangaben schwärzen
(detektoren/kammfelder.py, struktur.kammfeld_scan) und sichtbare Reste melden (restrisiko._kammfelder_pruefen).

Abwandlungen: geschlossene Kästchen, Kamm mit kurzen Wänden (oben offen), unten offene Kästchen, Kästchenbreiten
4-8 mm, 150/200/300 dpi, Schräglage, unterbrochene Linien (Fax), Feldname links oder darüber. Gegenproben: leere Felder,
Felder ohne Personenbezug (Antragsdatum, Anzahl, Betrag, Kilometerstand, Tarifgruppe), Tabellen mit ungleichen
Spalten, Ankreuzkästchen, Unterschriftslinie, Fließtext. Alle Werte sind frei erfunden."""

import pytest

import pymupdf as fitz

from anonymisierer import kammraster, muster
from conftest import braucht_ocr

np = pytest.importorskip("numpy")

MM = 72 / 25.4
ALLE = {k[0] for k in muster.KATEGORIEN if k[4]}


# ----------------------------------------------------------------------
# Hilfen: Formularseiten zeichnen, rendern, als Scan ablegen
# ----------------------------------------------------------------------
def _kaesten(seite, x, y, n, breite, hoehe, stil="zu", luecken=()):
    """Kästchen zeichnen (y = Oberkante); stil "zu", "kamm" (Grundlinie + kurze Wände) oder "unten_offen";
    luecken: Kästchenindizes, vor denen eine Gruppenlücke steht (IBAN). Rückgabe: Kästchenrechtecke."""
    form = seite.new_shape()
    kaesten, pos = [], x
    for i in range(n):
        if i in luecken:
            pos += 1.6 * MM
        kaesten.append(fitz.Rect(pos, y, pos + breite, y + hoehe))
        pos += breite
    for k in kaesten:
        if stil == "zu":
            form.draw_rect(k)
        elif stil == "kamm":
            form.draw_line(k.bl, k.br)
            for xx in (k.x0, k.x1):
                form.draw_line(fitz.Point(xx, k.y1), fitz.Point(xx, k.y1 - 0.35 * hoehe))
        else:
            form.draw_line(k.tl, k.tr)
            for xx in (k.x0, k.x1):
                form.draw_line(fitz.Point(xx, k.y0), fitz.Point(xx, k.y1))
    form.finish(color=(0.2, 0.2, 0.25), width=0.5)
    form.commit()
    return kaesten


def _wert(seite, kaesten, wert, groesse=None):
    for k, c in zip(kaesten, wert):
        if c == " ":
            continue
        g = groesse or min(0.62 * k.height, 1.1 * k.width)
        b = fitz.get_text_length(c, fontname="hebo", fontsize=g)
        seite.insert_text(((k.x0 + k.x1) / 2 - b / 2, k.y1 - (k.height - 0.72 * g) / 2), c, fontsize=g,
                          fontname="hebo")


def _formular(felder, breite=5.0 * MM, hoehe=6.4 * MM, stil="zu", oben=True, titel=True):
    """Vektorseite mit Kammfeldern: felder = [(Feldname oder "", Wert, Kästchenzahl)]."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    if titel:
        seite.insert_text((57, 60), "Musterkasse Versicherung", fontsize=11, fontname="helv")
        seite.insert_text((57, 80), "Bitte in Druckbuchstaben ausfüllen, je Kästchen ein Zeichen.", fontsize=8,
                          fontname="helv")
    y = 110
    for etikett, wert, n in felder:
        if oben:
            if etikett:
                seite.insert_text((57, y), etikett, fontsize=8, fontname="helv")
            x0, y0 = 57, y + 3
            y += hoehe + 22
        else:
            if etikett:
                seite.insert_text((57, y + 0.65 * hoehe), etikett, fontsize=9, fontname="helv")
            x0, y0 = 230, y
            y += hoehe + 14
        kaesten = _kaesten(seite, x0, y0, n, breite, hoehe, stil)
        _wert(seite, kaesten, wert)
    return doc


def _grau(doc, dpi=300, winkel=0.0):
    seite = doc[0]
    pix = seite.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72).prerotate(winkel), colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()


def _scan(doc, pfad, dpi=200, winkel=0.0, jpeg=None):
    """Scan-Seite: Graustufen-Rendering (um `winkel` gedreht) als einziges Bild einer neuen Seite."""
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72).prerotate(winkel), colorspace=fitz.csGRAY)
    daten = pix.tobytes("jpeg", jpg_quality=jpeg) if jpeg else pix.tobytes("png")
    ziel = fitz.open()
    seite = ziel.new_page(width=pix.width * 72 / dpi, height=pix.height * 72 / dpi)
    seite.insert_image(seite.rect, stream=daten)
    ziel.save(pfad)
    ziel.close()
    return pfad


def _finden(grau, dpi):
    felder = kammraster.kammfelder_finden(grau, dpi)
    sauber = grau.copy()
    kammraster.linien_entfernen(sauber, felder)
    return kammraster.fuellung_bestimmen(sauber, felder, dpi), sauber


# ----------------------------------------------------------------------
# Erkennung im Bild
# ----------------------------------------------------------------------
@pytest.mark.parametrize("stil", ["zu", "kamm", "unten_offen"])
def test_kammfeld_stile_erkannt_und_gefuellt(stil):
    doc = _formular([("Name", "WALDBRUNN", 12), ("Postleitzahl", "37073", 5), ("Bemerkung", "", 6)], stil=stil)
    felder, _ = _finden(_grau(doc), 300)
    assert len(felder) == 3, [len(f.kaesten) for f in felder]
    assert [len(f.kaesten) for f in felder] == [12, 5, 6]
    assert [sum(f.gefuellt) for f in felder] == [9, 5, 0]
    if stil == "kamm":
        assert all(f.offen == "oben" for f in felder)


@pytest.mark.parametrize("breite_mm,dpi", [(4.0, 150), (5.0, 200), (6.0, 300), (8.0, 150), (8.0, 300)])
def test_kammfeld_kaestchengroessen_und_aufloesungen(breite_mm, dpi):
    doc = _formular([("Vorname", "MIRA", 7), ("Telefon", "03412233", 10)], breite=breite_mm * MM,
                    hoehe=max(breite_mm * 1.2, 5.0) * MM)
    felder, _ = _finden(_grau(doc, dpi), dpi)
    assert [len(f.kaesten) for f in felder] == [7, 10]
    assert [sum(f.gefuellt) for f in felder] == [4, 8]


@pytest.mark.parametrize("winkel", [0.8, -1.4, 2.0])
def test_kammfeld_schraeg(winkel):
    doc = _formular([("Name", "OSTERKAMP", 12), ("Wohnort", "KIEL", 8)])
    felder, _ = _finden(_grau(doc, 200, winkel), 200)
    assert [sum(f.gefuellt) for f in felder] == [9, 4], [len(f.kaesten) for f in felder]


def test_kammfeld_iban_gruppen_ein_feld():
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    kaesten = _kaesten(seite, 57, 100, 22, 5 * MM, 6.4 * MM, luecken=(2, 4, 8, 12, 16, 20))
    _wert(seite, kaesten, "DE02120300000000202051")
    felder, _ = _finden(_grau(doc), 300)
    assert len(felder) == 1 and len(felder[0].kaesten) == 22 and sum(felder[0].gefuellt) == 22


def _fax(doc, pfad):
    """Fax-Scan: 204 x 98 dpi, Schwelle auf Schwarzweiß (dünne Linien werden punktiert oder fallen aus)."""
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(204 / 72, 98 / 72), colorspace=fitz.csGRAY)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    a = np.where(a < 150, 0, 255).astype(np.uint8)
    bild = fitz.Pixmap(fitz.csGRAY, pix.width, pix.height, a.tobytes(), False)
    ziel = fitz.open()
    seite = ziel.new_page(width=595, height=842)
    seite.insert_image(seite.rect, stream=bild.tobytes("png"), keep_proportion=False)
    ziel.save(pfad)
    ziel.close()
    return pfad


@pytest.mark.parametrize("zeilen", [0, 1, 2])
def test_kammfeld_unterbrochene_linien_wie_fax(tmp_path, zeilen):
    """Fax (204 x 98 dpi, Schwarzweiß): Linien punktiert, Wände unterbrochen – die Bruchstücke eines Felds werden
    verbunden, jedes gefüllte Kästchen bleibt gefüllt."""
    felder_def = [("Name", "HAGEDORN", 12), ("Vorname", "TILL", 8), ("Telefon", "03017744221", 13)]
    doc = _formular(felder_def[zeilen:zeilen + 1] + felder_def[:zeilen], oben=False)
    with fitz.open(_fax(doc, tmp_path / "fax.pdf")) as fax:
        felder, _ = _finden(_grau(fax, 300), 300)
    erwartet = sorted(len(w) for _, w, _ in (felder_def[zeilen:zeilen + 1] + felder_def[:zeilen]))
    assert sorted(sum(f.gefuellt) for f in felder) == erwartet, [len(f.kaesten) for f in felder]


def test_kammfeld_linien_entfernt_zeichen_bleiben():
    doc = _formular([("Name", "PETROVIC", 10)])
    grau = _grau(doc)
    felder, sauber = _finden(grau, 300)
    x0, y0, x1, y1 = kammraster.feld_bereich(felder[0])
    vorher = (grau[y0:y1, x0:x1] < 128).sum()
    nachher = (sauber[y0:y1, x0:x1] < 128).sum()
    assert 0 < nachher < 0.6 * vorher
    # keine lange waagerechte Linie mehr im Feld
    zeilen = (sauber[y0:y1, x0:x1] < 128).sum(axis=1)
    assert zeilen.max() < 0.5 * (x1 - x0)
    # in jedem gefüllten Kästchen bleibt Tinte (die Zeichen)
    for (a0, b0, a1, b1), g in zip(felder[0].kaesten, felder[0].gefuellt):
        assert ((sauber[b0:b1, a0:a1] < 128).sum() > 0) == g


def test_gegenprobe_tabelle_mit_ungleichen_spalten():
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    form = seite.new_shape()
    xs = [57, 140, 260, 330, 470]
    for r in range(5):
        for a, b in zip(xs, xs[1:]):
            form.draw_rect(fitz.Rect(a, 100 + r * 14, b, 114 + r * 14))
    form.finish(color=(0, 0, 0), width=0.5)
    form.commit()
    for r in range(5):
        seite.insert_text((60, 111 + r * 14), f"Zeile {r + 1}", fontsize=8, fontname="helv")
    assert kammraster.kammfelder_finden(_grau(doc), 300) == []


def test_gegenprobe_ankreuzkaestchen_unterschrift_fliesstext():
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    form = seite.new_shape()
    form.draw_rect(fitz.Rect(57, 100, 57 + 4 * MM, 100 + 4 * MM))           # [ ] ja
    form.draw_rect(fitz.Rect(120, 100, 120 + 4 * MM, 100 + 4 * MM))         # [ ] nein
    form.draw_line(fitz.Point(300, 300), fitz.Point(520, 300))              # Unterschriftslinie
    form.finish(color=(0, 0, 0), width=0.6)
    form.commit()
    seite.insert_text((57 + 5 * MM, 110), "ja", fontsize=9, fontname="helv")
    seite.insert_text((120 + 5 * MM, 110), "nein", fontsize=9, fontname="helv")
    for i in range(12):
        seite.insert_text((57, 200 + 12 * i), "Hiermit bestätige ich die Richtigkeit meiner Angaben im Antrag "
                                              "IIII HHHH 1111 llll.", fontsize=10, fontname="helv")
    assert kammraster.kammfelder_finden(_grau(doc), 300) == []


def _textseite():
    """Gegenprobe: Schreibmaschinenzeilen (gleich breite Zeichen, Serifen auf der Grundlinie) und Schrift auf
    Schreiblinien – Grundlinie und Grundstriche sehen aus wie ein Kamm."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    y = 100
    for zeile in ("Sehr geehrte Damen und Herren, anbei wie telefonisch besprochen die unterschriebene",
                  "Erklaerung. Bitte melden Sie sich zurueck, wenn noch etwas fehlt. Mit freundlichen",
                  "Gruessen aus Bielefeld, Ihre Annegret Pohl, geboren am 6.9.1974, Feldkirchener Weg 66"):
        seite.insert_text((57, y), zeile, fontsize=10, fontname="cour")
        y += 13
    y += 20
    form = seite.new_shape()
    for wert in ("Andrzej Jablonska", "HH-PF 4", "Skoda Octavia Combi 2.0 TDI", "Kirchsteig 74"):
        seite.insert_text((62, y), wert, fontsize=16, fontname="tiit")
        form.draw_line(fitz.Point(57, y + 2), fitz.Point(400, y + 2))
        y += 34
    form.finish(color=(0.3, 0.3, 0.3), width=0.6)
    form.commit()
    return doc


def _fax_grau(doc, dpi=300, winkel=0.0):
    """Fax (204 x 98 dpi, Schwelle auf Schwarzweiß, optional schräg eingezogen), wieder mit dpi gerendert."""
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(204 / 72, 98 / 72).prerotate(winkel), colorspace=fitz.csGRAY)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    a = np.where(a < 150, 0, 255).astype(np.uint8)
    bild = fitz.Pixmap(fitz.csGRAY, pix.width, pix.height, a.tobytes(), False)
    with fitz.open() as fax:
        seite = fax.new_page(width=595, height=842)
        seite.insert_image(seite.rect, stream=bild.tobytes("png"), keep_proportion=False)
        return _grau(fax, dpi)


@pytest.mark.parametrize("dpi", [150, 200, 300])
@pytest.mark.parametrize("als_fax", [False, True])
def test_gegenprobe_textzeilen_und_schreiblinien_kein_kamm(dpi, als_fax):
    """Eine Textzeile und eine Schreiblinie mit Schrift darauf sind kein Kamm: neben den Grundstrichen von Buchstaben
    steht Tinte (WAND_FREI_ANTEIL), eine Schreiblinie mit Handschrift ist dick (KAMM_MAX_DICKE_MM), und Bruchstücke
    aus wenigen Wänden werden nicht zu langen Feldern verbunden (WAND_BELEG_ANTEIL). Sonst übermalte die OCR
    Buchstaben und läse die Zeile nicht mehr."""
    grau = _fax_grau(_textseite(), dpi) if als_fax else _grau(_textseite(), dpi)
    assert kammraster.kammfelder_finden(grau, dpi) == []


@pytest.mark.parametrize("schrift", ["helv", "tiro", "cour"])
def test_gegenprobe_saetze_in_grosser_schrift_kein_kamm(schrift):
    """Sätze in großer Schrift (Überschrift, Briefkopf): Grundstriche über 4 mm hoch in fast regelmäßigem Abstand,
    Querstriche als „Kanten“ – Bruchstücke daraus werden nicht auf dem Raster zu einem Feld verlängert (zu wenige
    erkannte Wände, WAND_BELEG_ANTEIL). Sonst übermalte die OCR die Grundstriche und läse den Satz nicht mehr."""
    doc = fitz.open()
    seite = doc.new_page()
    for i, satz in enumerate(("Erste Fassung Berta Betaa 2222", "Erste Fassung Anton Alpha 1111",
                              "Kündigung der Hausratversicherung", "Schadenmeldung Wohngebäude")):
        seite.insert_text((72, 100 + 40 * i), satz, fontsize=20, fontname=schrift)
    for dpi in (150, 300):
        assert kammraster.kammfelder_finden(_grau(doc, dpi), dpi) == []


@pytest.mark.parametrize("winkel", [0.3, 0.6, -0.5, -0.9])
def test_kammfeld_fax_linien_nur_stueckweise(winkel):
    """Fax, schräg eingezogen: dünne waagerechte Linien kommen bei 98 dpi senkrecht nur stückweise an (abwechselnd
    Kästchen mit und ohne Kante), Wände zerfallen in Stücke – jede Reihe gefüllter Kästchen wird trotzdem gefunden.
    Schräglagen unter 1° (ab 1° rückt die OCR die Seite vorher gerade). Fehlen die Linien ganz, gilt eine Reihe aus
    Strichen nicht als Kammfeld: große Schrift sähe sonst so aus."""
    felder_def = [("Versicherungsnummer", "HR59080055", 12), ("Straße", "KIRCHPLATZ", 11),
                  ("Telefon", "07776673292", 12), ("Name", "HAGEDORN", 10)]
    doc = _formular(felder_def, breite=6.0 * MM, hoehe=7.0 * MM, oben=False)
    felder, _ = _finden(_fax_grau(doc, 300, winkel), 300)
    assert sorted(sum(f.gefuellt) for f in felder) == sorted(len(w) for _, w, _ in felder_def), \
        [len(f.kaesten) for f in felder]


@pytest.mark.parametrize("feldname,wert", [
    ("Antragsdatum (TTMMJJJJ)", "01082025"), ("Antragsdatum", "01.08.2025"), ("Datum", "15.03.2019"),
    ("Schadendatum", "3 1 1 2 2 0 2 4"), ("Anzahl der Fahrzeuge", "2"), ("Betrag in EUR", "1.250,00"),
    ("Kilometerstand", "48211"), ("Tarifgruppe", "B4"), ("Baujahr", "2014"), ("Leistung (kW)", "110")])
def test_wert_ohne_personenbezug_frei(feldname, wert):
    assert kammraster.wert_ohne_personenbezug(feldname, wert)


@pytest.mark.parametrize("feldname,wert", [
    ("Geburtsdatum (TTMMJJJJ)", "14031987"),       # Feldname mit Personenbezug
    ("Datum der Geburt", "01082025"),
    ("Antragsdatum", "14031957"),                  # Datum vor Jahrzehnten: vielleicht ein Geburtsdatum im falschen Feld
    ("Anzahl", "12345678"),                        # Wert nicht in der Form des Feldnamens
    ("Kilometerstand", "WALDBRUNN"),
    ("Tarifgruppe", "KV12345678"),
    ("Name", "2"), ("Telefon", "48211"), ("Kennzeichen", "B4"),
    ("", "01082025"), ("Bemerkung", "01082025")])  # kein oder unbekannter Feldname
def test_wert_ohne_personenbezug_gegenproben(feldname, wert):
    assert not kammraster.wert_ohne_personenbezug(feldname, wert)


def test_ocr_vorbereitung_aendert_nur_die_linien():
    """Vor der Texterkennung werden nur die Linien der Kammfelder weiß – Farbe und alle anderen Pixel bleiben (schon
    wenige veränderte Pixel ändern sonst die Seitenaufteilung der ganzen Seite)."""
    from anonymisierer import ocr
    doc = _formular([("Name", "WALDBRUNN", 12)])
    doc[0].insert_text((57, 400), "Blaue Tinte bleibt blau", fontsize=12, fontname="helv", color=(0.1, 0.2, 0.8))
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), colorspace=fitz.csRGB, alpha=False)
    pix.set_dpi(300, 300)
    neu, felder, _ = ocr._kammfelder_vorbereiten(pix, 300)
    assert felder and neu.colorspace.n == 3 and (neu.width, neu.height) == (pix.width, pix.height)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    b = np.frombuffer(neu.samples, dtype=np.uint8).reshape(neu.height, neu.width, 3)
    geaendert = (a != b).any(axis=2)
    x0, y0, x1, y1 = kammraster.feld_bereich(felder[0])
    assert geaendert.sum() > 0
    assert not geaendert[:max(0, y0 - 20)].any() and not geaendert[y1 + 20:].any()
    assert (b[geaendert] == 255).all()                       # übermalt wird nur mit Weiß
    blau = (a[..., 2] > 150) & (a[..., 0] < 100)
    assert blau.sum() > 0 and (b[blau] == a[blau]).all()     # farbige Schrift unverändert


def test_ohne_numpy_keine_kammfelder(monkeypatch):
    monkeypatch.setattr(kammraster, "_np", lambda: None)
    doc = _formular([("Name", "WALDBRUNN", 12)])
    assert kammraster.kammfelder_finden(_grau(doc), 300) == []
    assert not kammraster.verfuegbar()


def test_im_feld_fragt_die_kaestchen_nicht_den_rahmen():
    """Ein schräges Feld reicht mit seinem Rahmen in die Zeile darüber – nur die Kästchen zählen."""
    feld = {"rahmen": [50, 90, 400, 120], "kaesten": [[50 + 14 * i, 100 + 0.3 * i, 64 + 14 * i, 118 + 0.3 * i]
                                                     for i in range(20)], "gefuellt": [True] * 20, "offen": ""}
    assert kammraster.im_feld(feld, 57, 109)
    assert not kammraster.im_feld(feld, 60, 93)          # Feldname darüber, innerhalb des Rahmens
    assert kammraster.kopfkasten(feld)[0] == 50


# ----------------------------------------------------------------------
# OCR, Erkennung, Selbstkontrolle (Tesseract)
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def ocr_dienst():
    from anonymisierer.ocr import OcrDienst
    with OcrDienst(prozesse=1) as dienst:
        yield dienst


_PERSONEN = [("Name", "WALDBRUNN", 12), ("Vorname", "MIRA", 8), ("Geburtsdatum (TTMMJJJJ)", "14031987", 9),
             ("Straße", "AM MUEHLBACH", 14), ("Hausnummer", "17", 4), ("PLZ", "37073", 5), ("Wohnort", "GOETTINGEN", 12),
             ("Telefon", "05512233441", 12)]
_OHNE_PERSONENBEZUG = [("Antragsdatum (TTMMJJJJ)", "01082025", 9), ("Anzahl der Fahrzeuge", "2", 3),
                       ("Kilometerstand", "48211", 7), ("Tarifgruppe", "B4", 4)]


def _stellen(funde):
    return [st["text"] for f in funde for st in f["stellen"] if st.get("an", True)]


def _gedeckt(funde, wert):
    kompakt = wert.replace(" ", "")
    return any(kompakt in t.replace(" ", "").replace("\t", "").upper() for t in _stellen(funde))


def _beruehrt(funde, wert):
    """Ist der Wert (ganz, als eigene Stelle oder deren Teil an Wortgrenzen) geschwärzt?"""
    import re
    kompakt = wert.replace(" ", "")
    muster_ = re.compile(rf"(?<![0-9A-Z]){re.escape(kompakt)}(?![0-9A-Z])")
    return any(muster_.search(t.replace(" ", "").replace("\t", "").upper()) for t in _stellen(funde))


@braucht_ocr
def test_ocr_liest_kammfeld_und_meldet_lage(tmp_path, ocr_dienst):
    pfad = _scan(_formular(_PERSONEN[:4]), tmp_path / "scan.pdf", dpi=200, jpeg=60)
    erg = ocr_dienst.ergebnis(pfad, 0)
    assert len(erg["kammfelder"]) == 4
    assert [sum(f["gefuellt"]) for f in erg["kammfelder"]] == [9, 4, 8, 11]
    text = " ".join(w[4] for w in erg["woerter"])
    for wort in ("WALDBRUNN", "MIRA", "14031987", "MUEHLBACH", "Geburtsdatum", "Vorname"):
        assert wort in text, text


@braucht_ocr
def test_ocr_seite_ohne_kammfeld_ohne_lage(tmp_path, ocr_dienst):
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    seite.insert_text((57, 100), "Sehr geehrte Damen und Herren, anbei die Unterlagen.", fontsize=11, fontname="helv")
    erg = ocr_dienst.ergebnis(_scan(doc, tmp_path / "brief.pdf"), 0)
    assert erg["kammfelder"] == []
    assert "Unterlagen." in [w[4] for w in erg["woerter"]]


@braucht_ocr
@pytest.mark.parametrize("oben,stil,dpi,winkel", [(True, "zu", 200, 0.0), (False, "zu", 150, 1.3),
                                                  (True, "kamm", 300, -0.7), (False, "unten_offen", 200, 0.0)])
def test_analyse_schwaerzt_kammfelder_hinter_personen_etiketten(tmp_path, ocr_dienst, oben, stil, dpi, winkel):
    from anonymisierer.analyse import analysiere_pdf
    felder = _PERSONEN + _OHNE_PERSONENBEZUG + [("Bemerkung", "", 8)]
    pfad = _scan(_formular(felder, stil=stil, oben=oben), tmp_path / "scan.pdf", dpi=dpi, winkel=winkel, jpeg=70)
    erg = analysiere_pdf(pfad, ALLE, [], [], ocr=ocr_dienst)
    funde = erg["funde"]
    for _, wert, _ in _PERSONEN:
        if wert in ("17",):
            continue                                   # zu kurz für einen Textvergleich (Lage siehe unten)
        assert _gedeckt(funde, wert) or _gedeckt(funde, wert[1:]), (wert, _stellen(funde))
    for _, wert, _ in _OHNE_PERSONENBEZUG:
        assert not _beruehrt(funde, wert), (wert, _stellen(funde))
    for etikett in ("Antragsdatum", "Kilometerstand", "Tarifgruppe", "Bemerkung", "Wohnort", "Vorname", "Telefon"):
        assert not any(etikett.upper() in t.upper() for t in _stellen(funde)), (etikett, _stellen(funde))
    # die Hausnummer (zwei Zeichen) ist über die Lage ihres Felds gefunden
    assert any(f["kategorie"] == "strasse" and any(st["text"].strip() in ("17", "1 7") for st in f["stellen"])
               for f in funde), _stellen(funde)


@braucht_ocr
def test_restrisiko_meldet_ungeschwaerzte_kammfelder(tmp_path, ocr_dienst):
    """Die Selbstkontrolle liest ein ungeschwärztes Formular: Kammfelder hinter Personen-Feldnamen und ohne Feldnamen
    sind Verdacht, Felder ohne Personenbezug und leere Felder nicht."""
    from anonymisierer import restrisiko
    felder = [("Name", "WALDBRUNN", 12), ("", "KX7731", 8), ("Antragsdatum (TTMMJJJJ)", "01082025", 9),
              ("Anzahl der Fahrzeuge", "2", 3), ("Bemerkung", "", 8)]
    pfad = _scan(_formular(felder), tmp_path / "scan.pdf", dpi=200)
    verdacht = [v for v in restrisiko.restrisiko_pruefen(pfad, ocr=ocr_dienst)
                if v.grund in (restrisiko.GRUND_KAMMFELD, restrisiko.GRUND_KAMMFELD_UNBEKANNT,
                               restrisiko.GRUND_KAMMFELD_UNGELESEN)]
    gruende = sorted(v.grund for v in verdacht)
    assert gruende.count(restrisiko.GRUND_KAMMFELD) <= 1
    oben = sorted(verdacht, key=lambda v: v.rechtecke[0].y0)
    assert len(oben) == 2, [(v.grund, v.rechtecke) for v in verdacht]
    assert oben[0].grund in (restrisiko.GRUND_KAMMFELD,) or "WALDBRUNN" not in str(oben[0])
    assert oben[1].grund in (restrisiko.GRUND_KAMMFELD_UNBEKANNT, restrisiko.GRUND_KAMMFELD_UNGELESEN)


@braucht_ocr
def test_ende_zu_ende_kammfelder_geschwaerzt_ohne_verdacht(tmp_path, ocr_dienst):
    """Analyse + Schwärzung: die Werte hinter Personen-Feldnamen sind weg (die Kontroll-OCR liest sie nicht mehr), die
    Felder ohne Personenbezug bleiben lesbar, und die Selbstkontrolle meldet kein Kammfeld."""
    from anonymisierer import restrisiko
    from anonymisierer.analyse import analysiere_pdf
    from anonymisierer.schwaerzung import schwaerze_pdf
    felder = _PERSONEN[:3] + _OHNE_PERSONENBEZUG[:2] + [("Bemerkung", "", 8)]
    pfad = _scan(_formular(felder), tmp_path / "scan.pdf", dpi=200)
    erg = analysiere_pdf(pfad, ALLE, [], [], ocr=ocr_dienst)
    aus = schwaerze_pdf(pfad, erg["funde"], ocr=ocr_dienst, ocr_cache=erg["ocr_cache"], ziel_ordner=tmp_path / "aus")
    ausgabe = aus["ausgabe"] if isinstance(aus, dict) else aus
    kontrolle = ocr_dienst.ergebnis(ausgabe, 0)
    gelesen = " ".join(w[4] for w in kontrolle["woerter"])
    for _, wert, _ in _PERSONEN[:3]:
        assert wert not in gelesen, (wert, gelesen)
    assert "01082025" in gelesen.replace(" ", "")
    kamm_verdacht = [v for v in restrisiko.restrisiko_pruefen(ausgabe, ocr=ocr_dienst)
                     if v.grund in (restrisiko.GRUND_KAMMFELD, restrisiko.GRUND_KAMMFELD_UNBEKANNT,
                                    restrisiko.GRUND_KAMMFELD_UNGELESEN)]
    assert kamm_verdacht == [], [(v.grund, v.rechtecke) for v in kamm_verdacht]


# ----------------------------------------------------------------------
# Selbstkontrolle mit den Kammfeldern des Originals (ohne Tesseract: Wörter vorgegeben)
# ----------------------------------------------------------------------
def _seitenfelder(doc, dpi=300):
    """Kammfelder einer Seite in Seitenkoordinaten, wie die OCR sie an Seitenmodell und Selbstkontrolle weitergibt."""
    felder, _ = _finden(_grau(doc, dpi), dpi)
    s = 72.0 / dpi
    return [{"rahmen": [v * s for v in kammraster.feld_bereich(f)], "kaesten": [[v * s for v in k] for k in f.kaesten],
             "gefuellt": list(f.gefuellt), "offen": f.offen} for f in felder]


def _ausgabe_mit_schwaerzung(scan_pfad, ziel, rechtecke):
    """Ausgabe nachstellen: graue Schwärzungsrechtecke der Schwärzung über dem Scan."""
    from anonymisierer import restrisiko
    with fitz.open(scan_pfad) as doc:
        form = doc[0].new_shape()
        for r in rechtecke:
            form.draw_rect(fitz.Rect(r))
        form.finish(color=None, fill=restrisiko.FUELLFARBE, width=0)
        form.commit()
        doc.save(ziel)
    return ziel


def _etiketten_woerter(doc, ohne=()):
    """OCR-Wörter (x0, y0, x1, y1, text) der Feldnamen der Vektorvorlage (dieselbe Lage wie auf dem Scan)."""
    return [tuple(w[:5]) for w in doc[0].get_text("words") if w[4] not in ohne]



def _kamm_verdacht(verdacht):
    from anonymisierer import restrisiko
    gruende = (restrisiko.GRUND_KAMMFELD, restrisiko.GRUND_KAMMFELD_UNBEKANNT, restrisiko.GRUND_KAMMFELD_UNGELESEN)
    return [v for v in verdacht if v.grund in gruende]


@pytest.mark.parametrize("abgedeckt,verdacht_erwartet", [(8, True), (10, False)])
def test_restrisiko_kammfeld_des_originals_trotz_verdeckter_linien(tmp_path, abgedeckt, verdacht_erwartet):
    """Schwärzungen verdecken die Linien eines Kammfelds fast ganz – in der Ausgabe findet die Prüfung das Feld nicht
    mehr selbst. Mit den Kammfeldern des Originals (Lage und Füllung) bleiben zwei ungeschwärzte gefüllte Kästchen
    hinter „Telefon“ Verdacht; sind alle geschwärzt, ist nichts zu melden."""
    from anonymisierer import restrisiko
    doc = _formular([("Telefon", "0315989596", 12)], oben=False, titel=False)
    felder = _seitenfelder(doc)
    assert len(felder) == 1 and sum(felder[0]["gefuellt"]) == 10
    scan = _scan(doc, tmp_path / "scan.pdf", dpi=200)
    rechtecke = [k for k, g in zip(felder[0]["kaesten"], felder[0]["gefuellt"]) if g][:abgedeckt]
    ausgabe = _ausgabe_mit_schwaerzung(scan, tmp_path / "aus.pdf", [fitz.Rect(r) + (-1, -1, 1, 1) for r in rechtecke])
    woerter = {0: _etiketten_woerter(doc, ohne=list("0315989596"))}
    mit = _kamm_verdacht(restrisiko.restrisiko_pruefen(ausgabe, ocr_modus={0: "seite"}, ocr_woerter=woerter,
                                                        kammfelder={0: felder}))
    if verdacht_erwartet:
        assert [v.grund for v in mit] == [restrisiko.GRUND_KAMMFELD], [(v.grund, v.rechtecke) for v in mit]
        sichtbar = fitz.Rect(felder[0]["kaesten"][8]) | fitz.Rect(felder[0]["kaesten"][9])
        assert abs(mit[0].rechtecke[0] & sichtbar) >= 0.8 * abs(sichtbar)
    else:
        assert mit == [], [(v.grund, v.rechtecke) for v in mit]


def test_restrisiko_kein_textverdacht_im_freien_kammfeld(tmp_path):
    """Ein Datum im Feld „Antragsdatum“ (Wert in der Form des Feldnamens, aus den letzten 30 Jahren) ist frei: weder
    die Kammfeld-Prüfung noch die Textregeln melden es. Dasselbe Datum hinter „Geburtsdatum“ bleibt Verdacht."""
    from anonymisierer import restrisiko
    doc = _formular([("Antragsdatum", "01082025", 9), ("Geburtsdatum", "01081989", 9)], oben=False, titel=False)
    felder = _seitenfelder(doc)
    assert len(felder) == 2
    scan = _scan(doc, tmp_path / "scan.pdf", dpi=200)
    woerter = []
    for w in doc[0].get_text("words"):
        woerter.append(tuple(w[:5]))
    # die Ziffern eines Felds als EIN Wort, wie die Kammfeld-Lesung sie liefert
    werte = [w for w in woerter if w[4].isdigit()]
    rest = [w for w in woerter if not w[4].isdigit()]
    for feld in felder:
        drin = [w for w in werte if kammraster.im_feld(feld, (w[0] + w[2]) / 2, (w[1] + w[3]) / 2)]
        rest.append((min(w[0] for w in drin), min(w[1] for w in drin), max(w[2] for w in drin),
                     max(w[3] for w in drin), "".join(w[4] for w in sorted(drin))))
    verdacht = restrisiko.restrisiko_pruefen(scan, ocr_modus={0: "seite"}, ocr_woerter={0: rest},
                                             kammfelder={0: felder})
    oben, unten = sorted(felder, key=lambda f: f["rahmen"][1])

    def im(feld, v):
        return any(kammraster.im_feld(feld, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2) for r in v.rechtecke)

    assert not [v for v in verdacht if im(oben, v)], [(v.text, v.grund) for v in verdacht if im(oben, v)]
    assert [v for v in verdacht if im(unten, v)], [(v.text, v.grund) for v in verdacht]
