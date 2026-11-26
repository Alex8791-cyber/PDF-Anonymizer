"""Nachbesserung 6 nach der vierten Abnahme von integration-r7 (Stand 0230782).

Je Befund der Abnahme (Lecks AB4-01 bis AB4-18, Über-Schwärzung und Laufzeit AB4U-01 bis AB4U-12) die Zeilen der
Abnahme, eigene Abwandlungen und nicht geheime Gegenproben. Grundsätze: eine Verengung lässt einen sichtbaren Rückfall
(Meldung der Selbstkontrolle) an ihrer Stelle (P1); mehrdeutige Fälle werden gemeldet, geschwärzt nur mit sicherem
Beleg, frei gelassen nur mit sicherem Gegenbeleg (P2); allgemeine Regeln statt Wortlisten (P3). Alle Personen, Codes,
Nummern und Anschriften sind frei erfunden."""


import pytest

from anonymisierer import detektoren, kammraster, kennungsformen, muster, personenkontext, seitenmodell
from anonymisierer.analyse import analysiere_text
from anonymisierer.detektoren import Kontext
from anonymisierer.restrisiko import pruefe_text
from conftest import braucht_modell

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Hilfsfunktionen (wie tests/test_abnahme3_r7.py)
# ----------------------------------------------------------------------
def _funde(text, profil="hoch"):
    return analysiere_text(text, ALLE, [], [], profil=profil)


def _stellen(funde, kategorie=None) -> set:
    return {st["text"] for f in funde if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


def _geschwaerzt(text, wert, kategorie=None) -> bool:
    return any(wert in s for s in _stellen(_funde(text), kategorie))


def _beruehrt(text, wert) -> bool:
    return any(wert in s or (len(s) >= 2 and s in wert) for s in _stellen(_funde(text)))


def _verdacht(text, **kw) -> list:
    return [(v.text, v.grund) for v in pruefe_text(text, **kw)]


def _ausgabe(text) -> tuple:
    spannen = sorted((st["start"], st["ende"], f["kategorie"].upper()) for f in _funde(text)
                     for st in f["stellen"] if st.get("an", True) and "start" in st)
    aus, pos, ph = [], 0, set()
    for s, e, k in spannen:
        if s < pos:
            continue
        aus += [text[pos:s], f"[{k}]"]
        ph.add(f"[{k}]")
        pos = e
    aus.append(text[pos:])
    return "".join(aus), sorted(ph)


def _weg_oder_gemeldet(text, wert) -> bool:
    aus, ph = _ausgabe(text)
    if wert not in aus:
        return True
    return any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(aus, platzhalter=ph))


def _gemeldet(text, wert) -> bool:
    """In der Ausgabe gemeldet (Verdacht an der Stelle)."""
    aus, ph = _ausgabe(text)
    return any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(aus, platzhalter=ph))


def _kamm(text):
    """Treffer von struktur.kammfeld auf der Textebene (ein Kammfeld in der Kopfzeile als Vorfilter der Regel)."""
    funktion = next(e for e in detektoren.REGISTER if e.name == "struktur.kammfeld").funktion
    dok = seitenmodell.dokument_aus_text("Name\nM U S T E R M A N N\n" + text)
    return {(t.kategorie, dok.text[t.start:t.ende]) for t in funktion(dok, Kontext(ALLE, "hoch"))} - \
        {("namen", "M U S T E R M A N N")}


# ----------------------------------------------------------------------
# AB4-01: Teile eines Datums (Tag, Monat, Jahr) unter einem Geburts-Feldnamen; "Datum" allein bleibt ein Datum
# ----------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Tag", "Monat", "Jahr", "TT", "MM", "JJJJ", "Jahr:", "Datum", "Tag (TT)"])
def test_ab4_01_teil_feldnamen(name):
    assert kammraster.teil_etikett(name)


@pytest.mark.parametrize("name", ["Geburtsdatum", "Antragsdatum", "Tagegeld", "Jahresbeitrag", "Monatsbeitrag"])
def test_ab4_01_keine_teil_feldnamen(name):
    assert not kammraster.teil_etikett(name)


@pytest.mark.parametrize("feldname, wert", [("Jahr", "2016"), ("Tag", "25"), ("Monat", "04"), ("JJJJ", "1987"),
                                            ("TT", "03"), ("Jahr:", "2016")])
def test_ab4_01_teil_allein_nie_frei(feldname, wert):
    """Auf 0230782 galt „Jahr“ mit einer Jahreszahl als frei (Wortliste ohne Personenbezug) – erst der übergeordnete
    Feldname sagt, wessen Jahr."""
    assert not kammraster.wert_ohne_personenbezug(feldname, wert)
    assert kammraster.teil_ohne_datum(feldname)


def test_ab4_01_datum_allein_bleibt_frei():
    """Gegenprobe: „Datum“ allein (Ort, Datum der Unterschrift) ist ein Datum wie „Antragsdatum“."""
    assert kammraster.wert_ohne_personenbezug("Datum", "15.03.2019")
    assert not kammraster.teil_ohne_datum("Datum")


@pytest.mark.parametrize("text", [
    "Geburtsdatum\t\tTag\t\t2 5\t\tMonat\t\t0 4\t\tJahr\t\t2 0 1 6",
    "Geburtsdatum Tag 2 5 Monat 0 4 Jahr 2 0 1 6",
    "Geburtsdatum:\t\tTag 1 1\t\tMonat 0 9\t\tJahr 1 9 8 7",
])
def test_ab4_01_geteiltes_geburtsdatum_textebene(text):
    treffer = _kamm(text)
    assert {k for k, _ in treffer} == {"geburt"}, treffer
    assert len(treffer) == 3, treffer


class _Rechteck:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


class _OcrSeite:
    """Kleinste OCR-Seite für kammfelder._geteiltes_datum: Zeilen aus (x, y, Wort)-Folgen, jedes Zeichen mit Rechteck."""

    def __init__(self, zeilen):
        from types import SimpleNamespace
        teile, self.zeichen, self.abbildung, self.zeilen, pos = [], [], [], [], 0
        for zeile in zeilen:
            start = pos
            for k, (x, y, wort) in enumerate(zeile):
                if k:
                    teile.append("\t\t")
                    self.abbildung += [-1, -1]
                    pos += 2
                for i, c in enumerate(wort):
                    self.zeichen.append(SimpleNamespace(rect=_Rechteck(x + 5 * i, y, x + 5 * i + 5, y + 9)))
                    self.abbildung.append(len(self.zeichen) - 1)
                teile.append(wort)
                pos += len(wort)
            self.zeilen.append(SimpleNamespace(start=start, ende=pos))
            teile.append("\n")
            self.abbildung.append(-1)
            pos += 1
        self.text = "".join(teile)


def _teile_ocr(vorn, zweite):
    """Reihe "<vorn> ⇥⇥ Tag" als eine OCR-Zeile, der Rest derselben Reihe (y fast gleich, Schräglage) als zweite."""
    from types import SimpleNamespace
    from anonymisierer.detektoren import kammfelder
    seite = _OcrSeite([[(10, 100, vorn), (120, 100, "Tag")], [(x, 101, w) for x, w in zweite]])
    arten = {"datum_geburt"} if vorn.startswith("Geburt") else {"datum"}
    ets = [SimpleNamespace(start=0, ende=len(vorn), arten=arten)]
    return {seite.text[s:e] for s, e, _ in kammfelder._geteiltes_datum(seite, ets)}


# Nachbesserung 6 (Kammfeld-Korpus eigen404k a005/a001, 150/200 dpi, Schräglage 1°): die OCR liest "Geburtsdatum ⇥⇥
# Tag" als eine Zeile und den Rest der Reihe als andere ("2,35, ⇥⇥ Monat 0.4 ⇥⇥ Jahr ⇥⇥ 2016", "ala] ⇥⇥ Monat O 1");
# der Tag-Wert vor dem ersten Teil-Feldnamen und verlesene Ziffern gehören zum Geburtsdatum
@pytest.mark.parametrize("zweite, erwartet", [
    ([(150, "2,35,"), (200, "Monat"), (240, "0.4"), (280, "Jahr"), (320, "2016")], {"2,35,", "0.4", "2016"}),
    ([(150, "ala]"), (200, "Monat"), (240, "O 1"), (280, "Jahh"), (320, "2016")], {"ala]", "O 1"}),
    ([(150, "25"), (200, "Monat"), (240, "04"), (280, "Jahr"), (320, "1987")], {"25", "04", "1987"}),
])
def test_n6_geteiltes_geburtsdatum_ueber_ocr_zeilen(zweite, erwartet):
    assert _teile_ocr("Geburtsdatum", zweite) == erwartet


@pytest.mark.parametrize("vorn, zweite", [
    ("Antragsdatum", [(150, "2,35,"), (200, "Monat"), (240, "0.4"), (280, "Jahr"), (320, "2025")]),   # kein Geburtsdatum
    ("Geburtsdatum", [(150, "Name"), (200, "Monat"), (240, "04"), (280, "Jahr"), (320, "1987")]),    # Wort davor
    ("Geburtsdatum", [(150, "25"), (200, "Monat"), (240, "So"), (280, "Jahr"), (320, "Mai")]),        # keine Ziffer
])
def test_n6_geteiltes_geburtsdatum_gegenproben(vorn, zweite):
    assert _teile_ocr(vorn, zweite) <= ({"25"} if vorn == "Geburtsdatum" and zweite[0][1] == "25" else set())


@pytest.mark.parametrize("text", [
    "Antragsdatum\t\tTag\t\t2 5\t\tMonat\t\t0 4\t\tJahr\t\t2 0 2 5",
    "Versicherungsbeginn Tag 0 1 Monat 0 1 Jahr 2 0 2 6",
])
def test_ab4_01_geteiltes_datum_ohne_personenbezug_bleibt(text):
    assert _kamm(text) == set()


def _datumszeile(teile, breite_mm=5.0, oben=False, vorn="Geburtsdatum", dazu=()):
    """Vektorseite mit einer Zeile aus Kammfeldern: vorn ein Feldname, dann je Teil (Feldname, Wert, Kästchen) ein
    Teil-Feldname links (oben=False) bzw. über den Kästchen (oben=True). dazu: weitere Einzelfelder darunter.
    Rückgabe: (Dokument, [(Kästchen des Teils, Wert)])."""
    import pymupdf as fitz
    mm = 72 / 25.4
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    s.insert_text((57, 60), "Antrag Hausrat / Änderungsmeldung", fontsize=11, fontname="helv")
    h, y = 6.4 * mm, 120
    s.insert_text((57, y + 0.65 * h), vorn, fontsize=9, fontname="helv")
    x = 177                                      # Lage wie im Generator der Abnahme (abnahme4_lecks/skripte/a4_kamm.py)
    form = s.new_shape()
    werte = []
    for etikett, wert, n in list(teile):
        if oben:
            s.insert_text((x + 30, y - 3), etikett, fontsize=8, fontname="helv")
        else:
            s.insert_text((x, y + 0.65 * h), etikett, fontsize=8, fontname="helv")
        x0 = x + 30
        kaesten = [fitz.Rect(x0 + i * breite_mm * mm, y, x0 + (i + 1) * breite_mm * mm, y + h) for i in range(n)]
        werte.append((kaesten, wert))
        x = kaesten[-1].x1 + 18
    for i, (etikett, wert, n, b_mm) in enumerate(dazu):
        yy = 200 + 40 * i
        s.insert_text((57, yy + 0.65 * h), etikett, fontsize=9, fontname="helv")
        werte.append(([fitz.Rect(150 + j * b_mm * mm, yy, 150 + (j + 1) * b_mm * mm, yy + h) for j in range(n)], wert))
    for kaesten, _ in werte:
        for k in kaesten:
            form.draw_rect(k)
    form.finish(color=(0.2, 0.2, 0.25), width=0.5)
    form.commit()
    for kaesten, wert in werte:
        for k, c in zip(kaesten, wert):
            g = min(0.62 * k.height, 1.1 * k.width)
            b = fitz.get_text_length(c, fontname="hebo", fontsize=g)
            s.insert_text(((k.x0 + k.x1) / 2 - b / 2, k.y1 - (k.height - 0.72 * g) / 2), c, fontsize=g, fontname="hebo")
    return doc, werte[:len(list(teile))]


def _kammfelder_im_bild(doc, dpi):
    np = pytest.importorskip("numpy")
    import pymupdf as fitz
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), colorspace=fitz.csGRAY)
    grau = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
    return sorted(kammraster.kammfelder_finden(grau, dpi), key=lambda k: (k.rahmen[1] // 40, k.rahmen[0]))


@pytest.mark.parametrize("dpi", [150, 200, 300])
@pytest.mark.parametrize("oben", [False, True])
def test_ab4_01_zweierfelder_einer_datumszeile_erkannt(dpi, oben):
    """Tag und Monat aus je zwei Kästchen neben dem Jahr aus vier (eigene Kammfeld-Probe a013 der Abnahme: die zwei
    Kästchen galten nicht als Kammfeld, die OCR las „03“ und „02“ nicht, beide blieben still) – auch drei Zweierfelder
    (TT MM JJ): jedes Kästchen jedes Teils liegt in einem erkannten Feld (eng gesetzte Teile verbindet die Erkennung
    auf ihrem Raster zu einem Feld)."""
    s = dpi / 72.0
    for teile in ([("Tag", "03", 2), ("Monat", "02", 2), ("Jahr", "2016", 4)],
                  [("TT", "03", 2), ("MM", "02", 2), ("JJ", "16", 2)]):
        doc, werte = _datumszeile(teile, oben=oben)
        felder = _kammfelder_im_bild(doc, dpi)
        for kaesten, wert in werte:
            for k in kaesten:
                mx, my = (k.x0 + k.x1) / 2 * s, (k.y0 + k.y1) / 2 * s
                assert any(f.rahmen[0] <= mx <= f.rahmen[2] and f.rahmen[1] <= my <= f.rahmen[3] for f in felder), \
                    (wert, [(len(f.kaesten), f.rahmen) for f in felder])


@pytest.mark.parametrize("dpi", [150, 300])
def test_ab4_01_zweierfeld_gegenproben(dpi):
    """Ein Zweierfeld allein in seiner Zeile (Ankreuzpaar) und eines neben einem Feld anderer Bauart (8 mm statt 5 mm)
    bleiben kein Kammfeld; das Feld aus zwölf Kästchen daneben bleibt eines."""
    doc, _ = _datumszeile([("Anzahl", "2", 2)], vorn="Kinder", dazu=[("Telefon", "086112345678", 12, 8.0)])
    assert [len(k.kaesten) for k in _kammfelder_im_bild(doc, dpi)] == [12]
    doc, _ = _datumszeile([("Hausnr.", "17", 2)], vorn="Ort", dazu=())
    assert _kammfelder_im_bild(doc, dpi) == []


@pytest.fixture(scope="module")
def _ocr_n6():
    from anonymisierer.ocr import OcrDienst
    with OcrDienst(prozesse=1) as d:
        yield d


@pytest.mark.parametrize("dpi", [150, 200])
def test_ab4_01_zweierfelder_ende_zu_ende(tmp_path, _ocr_n6, dpi):
    """Analyse und Schwärzung eines Scans mit „Geburtsdatum Tag [03] Monat [02] Jahr [2016]“: die Kontroll-OCR liest
    keinen der Teile mehr; „Antragsdatum“ mit denselben Teilen bleibt lesbar."""
    from conftest import _tessdata_vorhanden
    if not _tessdata_vorhanden():
        pytest.skip("Tesseract-Sprachdaten fehlen")
    import pymupdf as fitz
    from anonymisierer.analyse import analysiere_pdf
    from anonymisierer.schwaerzung import schwaerze_pdf
    for vorn, weg in (("Geburtsdatum", True), ("Antragsdatum", False)):
        doc, _ = _datumszeile([("Tag", "03", 2), ("Monat", "02", 2), ("Jahr", "2016", 4)], oben=True, vorn=vorn)
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), colorspace=fitz.csGRAY)
        scan = fitz.open()
        seite = scan.new_page(width=595, height=842)
        seite.insert_image(seite.rect, stream=pix.tobytes("png"))
        pfad = tmp_path / f"{vorn}_{dpi}.pdf"
        scan.save(pfad)
        scan.close()
        erg = analysiere_pdf(pfad, ALLE, [], [], ocr=_ocr_n6)
        aus = schwaerze_pdf(pfad, erg["funde"], ocr=_ocr_n6, ocr_cache=erg["ocr_cache"], ziel_ordner=tmp_path / vorn)
        ausgabe = aus["ausgabe"] if isinstance(aus, dict) else aus
        gelesen = "".join(w[4] for w in _ocr_n6.ergebnis(ausgabe, 0)["woerter"])
        for wert in ("03", "02", "2016"):
            assert (wert not in gelesen) == weg, (vorn, wert, gelesen)


# ----------------------------------------------------------------------
# AB4-17: kurze Kammfeld-Werte der Textebene mit Tabulatoren zwischen den Kästchen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("Hausnr.\t\t1\t\t3", ("strasse", "1\t\t3")),
    ("Hausnr.\n1\t\t3", ("strasse", "1\t\t3")),
    ("Vorname\nL\t\tI", ("namen", "L\t\tI")),
])
def test_ab4_17_kurzer_wert_mit_tabulator(text, erwartet):
    assert _kamm(text) == {erwartet}


@pytest.mark.parametrize("text", ["Anzahl der Kinder\n2\t\t1", "Bemerkung\n1\t\t3", "Vorname\n1\t\t2"])
def test_ab4_17_kurzer_wert_gegenproben(text):
    assert _kamm(text) == set()


# ----------------------------------------------------------------------
# AB4-02 bis AB4-05, AB4-16: Zugangscodes – Schloss nach seinem Grundwort, Codeform, Meldewörter, PIN/Zugang + X
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Feuerschutztür-Code 2761", "2761"),                       # AB4-02
    ("Rauchschutztürcode: 9968", "9968"),
    ("Der Brandschutztürcode lautet 3196.", "3196"),
    ("Code Doppelgarage: 2824", "2824"),                        # AB4-03
    ("Der Code für das Haupttor lautet 5512.", "5512"),
    ("Hintertor (Code 5971)", "5971"),
    ("Türsprechanlage (Code 7596)", "7596"),
    ("Gittertor:\n6312", "6312"),
    ("Code Einzelgarage: 4418", "4418"),                        # Abwandlungen
    ("Seitentor (Code 2045)", "2045"),
    ("Kellertür – Code 7A3B", "7A3B"),                          # AB4-04
    ("Code Tiefgarage K2580", "K2580"),
    ("Die Haustür hat den Code A1B2C3.", "A1B2C3"),
    ("Am Display der Garage den Code 2240 eingeben.", "2240"),  # AB4-05
    ("Der Vermieter meldete den neuen Code der Kellertür: 8034", "8034"),
    ("Die Hausverwaltung meldet: neuer Code für die Tiefgarage ist 7992.", "7992"),
    ("Falls die Alarmanlage blinkt: Code 3917 eingeben.", "3917"),
    ("Herr Brandl zeigte uns die Garage, Code 4711.", "4711"),
    ("PIN Wohnungstür: 5862", "5862"),                          # AB4-16
    ("Zugang Tiefgarage: 4096", "4096"),
    ("Zahlencode Gartentor: 7713", "7713"),
    ("Schadenort Gartenhaus, Code 3141", "3141"),
    ("Zum Schaden in der Ferienwohnung: Die Tiefgarage ist mit 9063 gesichert.", "9063"),
    ("Zum Schaden in der Ferienwohnung: Code 9245 (Werkraum)", "9245"),     # Differenztest (fbd755b: weg)
    ("Zum Schaden in der Ferienwohnung: Hobbyraum -> Code 2099", "2099"),
])
def test_ab4_codes_weg_oder_gemeldet(text, wert):
    assert _weg_oder_gemeldet(text, wert), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@pytest.mark.parametrize("text, wert", [
    ("Fehlalarmcode 3401", "3401"),                             # Alarm-Vorgriff bleibt (AB4-02)
    ("Feueralarmcode 3401", "3401"),
    ("Der Motor zeigt Code 2207.", "2207"),                     # Gerät auf -tor ist kein Tor (AB4-03)
    ("Der Monitor (Code 2207) ist defekt.", "2207"),
    ("Inspektor (Code 2207) war da.", "2207"),
    ("Fehlercode P0300 am Garagentor", "P0300"),                # Fehlercode-Gestalt (AB4-04)
    ("Schadenschlüssel: Code 9245", "9245"),                    # Einordnung bleibt Einordnung
    ("Zum Schaden: Code 2207 laut Schadenkatalog.", "2207"),
])
def test_ab4_codes_gegenproben(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))
    assert not any(wert in t for t, g in _verdacht(text) if "Zugangscode" in g), _verdacht(text)


# ----------------------------------------------------------------------
# AB4U-05/AB4U-06: Beträge, Baujahre, Produkt-, Tarif- und Katalogcodes
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Wohnhaus:\t\t450.000\t\tEUR", "450.000"),
    ("Wohnhaus/Scheune/Stall/Carport:\t\t1974/1911/1987/2021", "1974/1911/1987/2021"),
    ("Das Einfamilienhaus mit 2021 erneuerter Heizung ist bewohnt.", "2021"),
    ("Die Scheune mit 1890 gebautem Dachstuhl brannte ab.", "1890"),
    ("Laut Rechnung des Möbelhauses trägt der Kleiderschrank den Code 66130.", "66130"),
    ("Kfz-Haftpflicht, Code 1101 für Pkw privat, Code 1201 für Krafträder.", "1101"),
    ("Das Fahrzeug hat den Code 0815 für die Typklasse.", "0815"),
    ("Der Code lautet 2207 laut Gebührenordnung.", "2207"),
    ("Kostenstelle: Code 4410", "4410"),
])
def test_ab4u_05_06_keine_zugangscodes(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))
    assert not any(wert in t for t, g in _verdacht(text) if "Zugangscode" in g), _verdacht(text)


# Nachbesserung 6 (Über-Probe der Abnahme 4, k02/g02): "Code für X lautet N" nur für einen Raum, ein Schloss oder einen
# Zugang; ein Jahr in der Spalte "Baujahr" einer Tabelle ist kein Zugangscode hinter einem Gebäude als Feldname
@pytest.mark.parametrize("text, wert", [
    ("Der Code für den Prospekt lautet 3344.", "3344"),
    ("Der Code für das Gewinnspiel lautet 7781.", "7781"),
    ("Der Code für den Newsletter lautet 5521.", "5521"),
    ("Gebäude\t\tBaujahr\t\tBauart\nWohnhaus:\t\t1974\t\tMassiv\nScheune:\t\t1911\t\tFachwerk", "1974"),
    ("Gebäude\t\tBaujahr\t\tBauart\nWohnhaus:\t\t1974\t\tMassiv\nScheune:\t\t1911\t\tFachwerk", "1911"),
    ("Objekt\t\tErbaut\nGarage:\t\t1999", "1999"),
])
def test_n6_code_prospekt_und_baujahr_spalte(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))
    assert not any(wert in t for t, g in _verdacht(text) if "Zugangscode" in g), _verdacht(text)


@pytest.mark.parametrize("text, wert", [
    ("Der Code für das Postfach lautet 2798.", "2798"),
    ("Der Code für die Wohnung lautet 1357.", "1357"),
    ("Der Code für den Tresor lautet 7316.", "7316"),
    ("Der Code für die Tiefgarage lautet 4096.", "4096"),
    ("Wohnhaus:\t\t1974\t\tMassiv", "1974"),                       # ohne Spaltenkopf: mehrdeutig, gemeldet
    ("Gebäude\t\tCode\t\tBauart\nWohnhaus:\t\t1974\t\tMassiv", "1974"),
    ("Gebäude\t\tBaujahr\nGartentor:\t\t6312", "6312"),           # kein Jahr unter "Baujahr"
])
def test_n6_code_prospekt_und_baujahr_gegenproben(text, wert):
    assert _weg_oder_gemeldet(text, wert), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


# ----------------------------------------------------------------------
# AB4-06, AB4-18: Beruf einer Person – geschwärzt oder gemeldet; Rolle, Ehrenamt und Sache als Gegenproben
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, beruf", [
    ("Sie ist ehrenamtlich als Erzieherin tätig.", "Erzieherin"),
    ("Die Firma hat sie 2019 als Hebamme eingestellt.", "Hebamme"),
    ("Die Stadt Traunstein beschäftigt ihn seit 2015 als Schreiner.", "Schreiner"),
    ("Er ist Fitnesstrainer in Rosenheim.", "Fitnesstrainer"),
    ("Sie ist von Beruf Versicherungsmaklerin.", "Versicherungsmaklerin"),
    ("da Sie als Krankenschwester im Schichtdienst arbeiten, empfehlen wir den Tarif Plus.", "Krankenschwester"),
    ("Sehr geehrte Frau Haslbeck,\nals Lehrerin haben Sie Anspruch auf den Berufsgruppenrabatt.", "Lehrerin"),
    ("Er hat den Beruf des Bäckers erlernt.", "Bäckers"),
    ("Sie ist hauptberuflich Kinderbetreuerin.", "Kinderbetreuerin"),
    ("Sie lernt den Beruf der Floristin.", "Floristin"),
])
def test_ab4_06_18_beruf_weg_oder_gemeldet(text, beruf):
    assert _weg_oder_gemeldet(text, beruf), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@pytest.mark.parametrize("text, wort", [
    ("Als Beamter haben Sie Anspruch auf Beihilfe.", "Beamter"),         # allgemeiner Satz (A2-03)
    ("Wir sind als Versicherungsmakler für Sie tätig.", "Versicherungsmakler"),
    ("Er ist ehrenamtlich als Trainer tätig.", "Trainer"),
])
def test_ab4_06_rolle_ohne_meldung(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))
    assert not any(wort in t for t, _ in _verdacht(text)), _verdacht(text)


@pytest.mark.parametrize("text, wort", [
    ("Sie ist ehrenamtlich als Kassiererin im Verein tätig.", "Kassiererin"),   # Ehrenamt: höchstens gemeldet
    ("Sie ist ehrenamtlich als Schöffin am Landgericht tätig.", "Schöffin"),
    ("Die Software arbeitet als Eingabehilfe für die Schadenmeldung.", "Eingabehilfe"),  # Sache als Satzgegenstand
])
def test_ab4_06_ehrenamt_und_sache_nicht_geschwaerzt(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))


# ----------------------------------------------------------------------
# AB4-07: Quadrate (Mannheim) – mit Wohnwort oder Person im Satz kein Ausschluss, „nach“ hinter einer Leistung gemeldet
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Herr Gruber wohnt laut Liste in S 2, 3.", "S 2, 3"),
    ("Die Entschädigung senden wir per Post nach K 1, 5.", "K 1, 5"),
    ("Die Wohnung liegt laut Lageplan in H 7, 21.", "H 7, 21"),
    ("Die Erstattung geht an Frau Hiebl nach U 1, 7.", "U 1, 7"),
])
def test_ab4_07_quadrate(text, wert):
    assert _weg_oder_gemeldet(text, wert), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@pytest.mark.parametrize("text, wert", [
    ("Die Entschädigung senden wir per Postnach K1, 5.", "K1, 5"),       # 300 dpi JPEG: „Post nach“ zusammengelesen
    ("Die Erstattung geht an Frau Hiebl Richtungnach U 1, 7.", "U 1, 7"),
])
def test_ab4_07_quadrat_nach_angeklebt_gemeldet(text, wert):
    assert any(wert in t for t, _ in _verdacht(text)), _verdacht(text)


@pytest.mark.parametrize("text, wert", [
    ("Die Abrechnung erfolgt nach K 1, 2.", "K 1, 2"),                    # „nach“ im Sinn von „gemäß“ (A2-05)
    ("Demnach K 1, 2 der Gliederung.", "K 1, 2"),                         # Adverb auf -nach
    ("Hiernach B 3, 4 prüfen.", "B 3, 4"),
])
def test_ab4_07_quadrat_nach_gegenproben(text, wert):
    assert not any(wert in t for t, _ in _verdacht(text)), _verdacht(text)


# ----------------------------------------------------------------------
# AB4-08, AB4-11, AB4-13, AB4-14: Name hinter Personenwort – gewöhnliche Wörter, ohne Beleg, Titel, Doppelname
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Zeugin Ledig wurde von der Polizei befragt.", "Ledig"),
    ("Mieterin Niemand wird morgen zurückrufen.", "Niemand"),
    ("Wir haben mit dem Onkel Grebl telefoniert.", "Grebl"),
    ("Wir haben mit dem Kunden Leser telefoniert.", "Leser"),
    ("Der Schaden wurde der Mieterin Tremml gemeldet.", "Tremml"),
    ("Maler Kaplan kam am Montag gegen 9 Uhr.", "Kaplan"),
    ("Onkel Kaplan ist seit Montag im Urlaub.", "Kaplan"),
    ("Das Fahrzeug gehört Herrn Halter aus Traunstein.", "Halter"),
    ("Laut Zeugin Bauer-Kaltl war die Ampel rot.", "Bauer-Kaltl"),
    ("Glaser Frost ist erst nächste Woche frei.", "Frost"),
    ("Laut Klempner Dyson ist der Schaden älter.", "Dyson"),
    ("Kaminkehrer Hofsteiger war am Freitag da.", "Hofsteiger"),
])
def test_ab4_personenwort_name_weg_oder_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


def test_ab4_14_doppelname_neben_platzhalter_gemeldet():
    """„Kreszenz Bauer-Hinterseer hat angerufen.“: geschwärzt wird der Vorname; der Doppelname daneben ist länger als
    ein Wort einer Zeile (14 Zeichen) – gezählt wird je Namensteil."""
    v = _verdacht("Telefonnotiz\n[PERSON A] Bauer-Hinterseer hat angerufen.", platzhalter=["[PERSON A]"])
    assert any(t == "Bauer-Hinterseer" for t, _ in v), v


def _ausgabe_pdf(tmp_path, vorn, hinten, ocr_platzhalter=None, rechteck=True):
    """Ausgabe wie die Schwärzung sie schreibt: graues Rechteck an der Stelle des geschwärzten Worts, der Platzhalter
    „[PERSON A]“ darin als letzter Text der Seite (Textebene) bzw. als Scan-Seite, deren OCR-Wörter den Platzhalter
    als `ocr_platzhalter` verlesen. vorn/hinten: Text links bzw. rechts des Rechtecks. Rückgabe: (Pfad, Zusatz für
    restrisiko_pruefen)."""
    import pymupdf as fitz
    from anonymisierer import restrisiko
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    s.insert_text((60, 70), "Telefonnotiz", fontsize=11, fontname="helv")
    x = 60
    if vorn:
        s.insert_text((x, 98), vorn, fontsize=11, fontname="helv")
        x += fitz.get_text_length(vorn + " ", fontname="helv", fontsize=11)
    r = fitz.Rect(x, 88.5, x + 50, 101)
    s.insert_text((r.x1 + 3, 98), hinten, fontsize=11, fontname="helv")
    zusatz = {}
    if ocr_platzhalter is not None:
        woerter = [tuple(w[:5]) for w in s.get_text("words")]
        woerter.append((r.x0 + 2, r.y0 + 1, r.x1 - 2, r.y1 - 1, ocr_platzhalter))
        pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
        scan = fitz.open()
        seite = scan.new_page(width=595, height=842)
        seite.insert_image(seite.rect, stream=pix.tobytes("png"))
        doc.close()
        doc, s = scan, seite
        zusatz = {"ocr_modus": {0: "seite"}, "ocr_woerter": {0: woerter}}
    if rechteck:
        s.draw_rect(r, color=None, fill=restrisiko.FUELLFARBE)
    if ocr_platzhalter is None:
        s.insert_text((r.x0 + 2, 98), "[PERSON A]", fontsize=8, fontname="helv")
    pfad = tmp_path / "ausgabe.pdf"
    doc.save(pfad)
    doc.close()
    return pfad, zusatz


@pytest.mark.parametrize("ocr_platzhalter", [None, "IPERSONAI", "|PERSON A|", "IRERSON AI"])
def test_ab4_14_doppelname_hinter_platzhalter_der_ausgabe(tmp_path, ocr_platzhalter):
    """In der Ausgabe steht der Platzhalter-Text am Ende der Textebene, sein Rechteck aber links vor dem Doppelnamen –
    kein „Beruf vor dem Namen“ (Bauer); auf Scans verliest die Kontroll-OCR die Klammern des Platzhalters (E2E-Probe
    b_doppelname_vorname: 4/4 still)."""
    from anonymisierer import restrisiko
    pfad, zusatz = _ausgabe_pdf(tmp_path, "", "Bauer-Hinterseer hat angerufen.", ocr_platzhalter)
    v = [(x.text, x.grund) for x in restrisiko.restrisiko_pruefen(pfad, platzhalter=["[PERSON A]"], **zusatz)]
    assert any(t == "Bauer-Hinterseer" for t, _ in v), v


@pytest.mark.parametrize("ocr_platzhalter", [None, "IPERSONAI"])
def test_ab4_14_beruf_vor_platzhalter_der_ausgabe_gegenprobe(tmp_path, ocr_platzhalter):
    """Gegenprobe: „Monteur [PERSON A] kam am Montag.“ – das Berufswort links vom Rechteck ist kein Name; ohne
    Schwärzungsrechteck ist ein verlesenes „IPERSONAI“ kein Platzhalter."""
    from anonymisierer import restrisiko
    pfad, zusatz = _ausgabe_pdf(tmp_path, "Monteur", "kam am Montag.", ocr_platzhalter)
    v = [(x.text, x.grund) for x in restrisiko.restrisiko_pruefen(pfad, platzhalter=["[PERSON A]"], **zusatz)]
    assert not any("Monteur" in t for t, _ in v), v
    if ocr_platzhalter:
        pfad, zusatz = _ausgabe_pdf(tmp_path, "", "Bauer-Hinterseer hat angerufen.", ocr_platzhalter, rechteck=False)
        v = [(x.text, x.grund) for x in restrisiko.restrisiko_pruefen(pfad, platzhalter=["[PERSON A]"], **zusatz)]
        assert not any(g == "unbekannter Eigenname im Personenkontext" for _, g in v), v


@pytest.mark.parametrize("text, wort", [
    ("Zeuge Unbekannt hat den Rauch zuerst bemerkt.", "Unbekannt"),
    ("Kunden Service-Center ist am Brückentag geschlossen.", "Service-Center"),
    ("Familienstand: ledig", "ledig"),
])
def test_ab4_personenwort_gegenproben(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))
    assert not any(wort in t for t, _ in _verdacht(text)), _verdacht(text)


# ----------------------------------------------------------------------
# AB4U-01: Abteilungs-, Orts- und Firmenwörter hinter einem Personenwort – nicht geschwärzt, höchstens gemeldet
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wort", [
    ("Kollege Außendienst ruft morgen zurück.", "Außendienst"),
    ("Mitarbeiter Vertrieb meldet sich bis Freitag.", "Vertrieb"),
    ("Nachbar Gegenüber sah den Rauch zuerst.", "Gegenüber"),
    ("Monteur Stadtwerke kam am Montag und hat den Zähler getauscht.", "Stadtwerke"),
    ("Kollege Backoffice hat die Police geprüft.", "Backoffice"),
    ("Mieter Nebenan hat Wasser an der Decke gesehen.", "Nebenan"),
    ("Techniker Wasserversorger hat den Zähler getauscht.", "Wasserversorger"),
    ("Techniker Netzbetreiber hat den Zähler getauscht.", "Netzbetreiber"),
    ("Kollegin Spätdienst hat den Anruf um 21 Uhr angenommen.", "Spätdienst"),
])
def test_ab4u_01_org_woerter_nicht_geschwaerzt(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))


@braucht_modell
@pytest.mark.parametrize("text, name", [
    ("Monteur Grohe kam am 03.03. und hat die Armatur getauscht.", "Grohe"),
    ("Nachbar Zettl hat den Brand gemeldet.", "Zettl"),
    ("Elektriker Miele kam am Montag.", "Miele"),
])
def test_ab4u_01_namen_mit_beleg_bleiben_geschwaerzt(text, name):
    assert _geschwaerzt(text, name), _stellen(_funde(text))


# ----------------------------------------------------------------------
# AB4-09: Organisationswort und unbekanntes Wort unter einem Gruß
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Mit freundlichen Grüßen\nAgentur Moik", "Moik"),
    ("Mit freundlichen Grüßen\nTeam Holzwohner", "Holzwohner"),
    ("Viele Grüße\nBüro Zirngast", "Zirngast"),
])
def test_ab4_09_gruss_mit_organisation_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@pytest.mark.parametrize("text, wort", [
    ("Mit freundlichen Grüßen\nKundenservice Traunstein", "Traunstein"),
    ("Mit freundlichen Grüßen\nIhr Team Service", "Service"),
])
def test_ab4_09_gegenproben(text, wort):
    assert not any(wort in t for t, _ in _verdacht(text)), _verdacht(text)


# ----------------------------------------------------------------------
# AB4-10, AB4-15: Hausnamen hinter beim/vom/zum
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Wir waren beim Brandl zum Essen.", "Brandl"),
    ("Die Kühe vom Lindinger standen auf der Straße.", "Lindinger"),
    ("Zum Brandl sind es zwei Kilometer.", "Brandl"),
])
def test_ab4_10_bekannter_familienname_als_hausname_geschwaerzt(text, name):
    assert _geschwaerzt(text, name), _stellen(_funde(text))


@pytest.mark.parametrize("text, name", [
    ("Vom Kaltl kam der Anruf wegen des Hagelschadens.", "Kaltl"),
    ("Wir waren beim Pfnürl zum Essen.", "Pfnürl"),
])
def test_ab4_15_unbekannter_hausname_weg_oder_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@pytest.mark.parametrize("text, wort", [
    ("Beim Bäcker gab es keine Brezen mehr.", "Bäcker"),
    ("Vom Keller aus sah man das Wasser.", "Keller"),
])
def test_ab4_10_15_gegenproben(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))


def _ocr_verdacht(tmp_path, zeilen) -> list:
    """Verdacht der Restrisiko-Prüfung einer Scan-Seite, deren OCR-Wörter genau die gedruckten Zeilen sind (so gelesen
    wie angegeben, z. B. mit einem Verleser der Texterkennung)."""
    import pymupdf as fitz
    from anonymisierer import restrisiko
    vorlage = fitz.open()
    s = vorlage.new_page()
    for i, z in enumerate(zeilen):
        s.insert_text((60, 100 + 24 * i), z, fontsize=12, fontname="helv")
    woerter = [tuple(w[:5]) for w in s.get_text("words")]
    pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    pfad = tmp_path / "scan.pdf"
    doc.save(pfad)
    doc.close()
    vorlage.close()
    return [(v.text, v.grund) for v in restrisiko.restrisiko_pruefen(pfad, ocr_modus={0: "seite"},
                                                                     ocr_woerter={0: woerter})]


@pytest.mark.parametrize("zeile, name", [
    ("Vom Kalt! kam der Anruf wegen des Hagelschadens.", "Kalt"),       # 300 dpi JPEG: „l“ als „!“ gelesen
    ("Wir waren beim Pfnür! zum Essen.", "Pfnür"),
])
def test_ab4_15_ocr_ausrufezeichen_als_l_gemeldet(tmp_path, zeile, name):
    v = _ocr_verdacht(tmp_path, ["Hagelschaden", zeile])
    assert any(name in t for t, _ in v), v


def test_ab4_15_ocr_ausrufezeichen_gegenprobe(tmp_path):
    """Ein echtes Ausrufezeichen (das Wort danach groß) bleibt eines; auf der Textebene gilt die Lesart nicht."""
    v = _ocr_verdacht(tmp_path, ["Achtung! Der Keller ist nass.", "Vorsicht! Das Wasser steht hoch."])
    assert not any("Achtungl" in t or "Vorsichtl" in t for t, _ in v), v
    assert not any("Kalt" in t for t, _ in _verdacht("Vom Kalt! kam der Anruf wegen des Hagelschadens.")), \
        _verdacht("Vom Kalt! kam der Anruf wegen des Hagelschadens.")


# ----------------------------------------------------------------------
# AB4-12: Familienname mit Artikel und Satzteil einer Person
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Gesehen hat es der Hintermaier.", "Hintermaier"),
    ("Der Kumpfl hat den Schaden gemeldet.", "Kumpfl"),
    ("Den Unfall verursachte der Pfnürl.", "Pfnürl"),
    ("Der Koch hat den Unfall verursacht.", "Koch"),
    ("Der Becher hat den Unfall verursacht.", "Becher"),
    ("Die Scheibe hat der Wimmer beschädigt.", "Wimmer"),
    ("Gesehen hat es der Hafl.", "Hafl"),                      # Name aus vier Buchstaben am Satzende
    ("Gemeldet hat den Schaden der Daxl.", "Daxl"),
    ("Der Grebl hat den Wagen gefahren.", "Grebl"),            # Fahrzeug als Objekt: die Person fährt
    ("Die Becherin hat angerufen.", "Becherin"),               # weibliche Form eines Sachworts
    ("Am Steuer saß die Becherin.", "Becherin"),
])
def test_ab4_12_artikel_name_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@pytest.mark.parametrize("text, wort", [
    ("Gefahren ist nach Angaben der Polizei der Wagen.", "Wagen"),     # Abnahme 2 V5
    ("Den Zaun rammte der Wagen.", "Wagen"),
    ("Der Hagel hat den Schaden verursacht.", "Hagel"),
    ("Den Zaun hat der Sturm beschädigt.", "Sturm"),
    ("Der Bagger hat die Leitung beschädigt.", "Bagger"),
    ("Die Scheibe hat der Wimmer beschädigt.", "Scheibe"),           # Objekt vor dem Täter
    ("Das ist das Ende.", "Ende"),
    ("Gemäß Abs. 2 der Ziff.\nWeiter", "Ziff"),
])
def test_ab4_12_gegenproben(text, wort):
    assert not any(wort in t for t, g in _verdacht(text) if "Artikel" in g), _verdacht(text)


# Nachbesserung 6 (Über-Probe der Abnahme 4, s11): "die X" hinter dem Verb ist das Objekt, wenn davor ein Subjekt im
# Nominativ steht ("Der …", "Er"); ein Tier der Wissensbasis verursacht einen Schaden selbst
@pytest.mark.parametrize("text, wort", [
    ("Der Saugroboter beschädigte die Stehlampe im Wohnzimmer.", "Stehlampe"),
    ("Er beschädigte die Stehlampe beim Staubsaugen.", "Stehlampe"),
    ("Der neue Hund des Nachbarn beschädigte die Vitrine.", "Vitrine"),
    ("Der Mieter bemerkte die Gardine erst am Abend.", "Gardine"),
    ("Der Hund beschädigte die Couch.", "Hund"),
    ("Die Katze hat den Vorhang beschädigt.", "Katze"),
])
def test_n6_objekt_und_tier_ohne_meldung(text, wort):
    assert not any(wort in t for t, g in _verdacht(text) if "Artikel" in g), _verdacht(text)


@pytest.mark.parametrize("text, name", [
    ("Den Zaun beschädigte die Pfnürl.", "Pfnürl"),             # "Den …" davor: die Person ist das Subjekt
    ("Gestern beschädigte die Pfnürl den Zaun.", "Pfnürl"),
    ("Den Schaden bemerkte die Pfnürl.", "Pfnürl"),
    ("Die Scheibe beschädigte die Pfnürl.", "Pfnürl"),          # "Die …" davor: mehrdeutig, gemeldet
    ("Das Auto beschädigte die Kumpfl beim Ausparken.", "Kumpfl"),
    ("Der Hund hat angerufen.", "Hund"),                         # ein Verb, das nur eine Person tut
])
def test_n6_objekt_gegenproben(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


# ----------------------------------------------------------------------
# AB4U-04: Geräte, Tiere und Rollen in Schadensätzen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wort", [
    ("Der Marder beschädigte die Zündkabel im Motorraum.", "Marder"),
    ("Der Toaster verursachte den Küchenbrand am Morgen.", "Toaster"),
    ("Der Heizlüfter hat den Brand im Bad verursacht.", "Heizlüfter"),
    ("Der Kondenstrockner verursachte den Wasserschaden im Keller.", "Kondenstrockner"),
    ("Der Gabelstapler beschädigte das Hochregal.", "Gabelstapler"),
    ("Der Hochdruckreiniger hat die Fassadendämmung beschädigt.", "Hochdruckreiniger"),
    ("Der Spaziergänger bemerkte den Rauch zuerst.", "Spaziergänger"),
])
def test_ab4u_04_geraete_und_rollen_ohne_meldung(text, wort):
    assert not any(wort in t for t, _ in _verdacht(text)), _verdacht(text)


# ----------------------------------------------------------------------
# AB4U-02, AB4U-03: Kreuzchen und vorgedruckte Ausfüllhinweise sind keine Werte
# ----------------------------------------------------------------------
@pytest.mark.parametrize("wert", ["X", "x", "✓", "TTMMJJJJ", "T T M M J J J J", "TT.MM.JJJJ", "MM/JJ", "JJJJ",
                                  "TTMMJJJIJ", "TTMMJJIJJ", "TlMMJJJJ", "MMIJJ"])   # Wandreste der OCR (300 dpi JPEG)
def test_ab4u_02_03_ausfuellhinweis(wert):
    assert kammraster.ausfuellhinweis(wert)


@pytest.mark.parametrize("wert", ["14031987", "DE", "L I", "8", "XY", "TIM", "TIMO", "JIMMY", "LILLI", "1111",
                                  "TIMM", "MIMI", "01011990"])
def test_ab4u_02_03_werte_sind_keine_hinweise(wert):
    assert not kammraster.ausfuellhinweis(wert)


# ----------------------------------------------------------------------
# AB4U-12: kurze Hausnummer nur am Feldnamen, nicht an gleichen Zahlen des Dokuments
# ----------------------------------------------------------------------
def test_ab4u_12_hausnummer_nicht_weitergegeben():
    text = ("Straße: Industriestraße\nHausnummer: 8\nDie Ware liegt in Halle 8 am Tor 8, insgesamt 8 Stück.\n"
            "Seite 1 von 8")
    funde = _funde(text)
    acht = [st for f in funde for st in f["stellen"] if st.get("an", True) and st["text"] == "8"]
    assert len(acht) == 1, [(f["kategorie"], st) for f in funde for st in f["stellen"]]
    assert text[acht[0]["start"] - 12:acht[0]["start"]] == "Hausnummer: "


# ----------------------------------------------------------------------
# AB4U-02 / E2E-Schranke: kurzer Kammfeld-Wert auf Scans – die Texterkennung liest weniger Zeichen, als Kästchen
# gefüllt sind („LI“ als „L“, 300 dpi JPEG); die Zahl der gefüllten Kästchen zählt mit, ein Name aus einem gelesenen
# Buchstaben bleibt geschwärzt, ein einzelnes Zeichen wird nicht weitergegeben
# ----------------------------------------------------------------------
class _KammOcrAttrappe:
    """OcrDienst-Ersatz: vorgegebene OCR-Wörter (5-Tupel) und Kammfelder einer Scan-Seite."""

    def __init__(self, woerter, felder):
        self._woerter, self._felder = woerter, felder

    def ergebnis(self, pdf_pfad, seite_nr0, dpi=300, clip=None):
        return {"woerter": list(self._woerter), "kammfelder": list(self._felder)}

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, **_):
        return list(self._woerter), None

    def schliessen(self):
        pass


def _kamm_scan(tmp_path, etikett, wert, kaesten_zahl, gelesen, weitere=()):
    """Scan-Seite (Bild) mit Feldname links und einem Kammfeld (je Kästchen ein Zeichen von wert); die Attrappe
    liefert den Feldnamen, `gelesen` als OCR-Wort über den ersten Kästchen (die übrigen Zeichen hat die Erkennung
    verloren), weitere Textzeilen und das Kammfeld mit seinen gefüllten Kästchen."""
    import pymupdf as fitz
    mm = 72 / 25.4
    vorlage = fitz.open()
    s = vorlage.new_page(width=595, height=842)
    s.insert_text((57, 122), etikett, fontsize=9, fontname="helv")
    for i, zeile in enumerate(weitere):
        s.insert_text((57, 200 + 20 * i), zeile, fontsize=10, fontname="helv")
    kaesten = [fitz.Rect(230 + i * 5 * mm, 108, 230 + (i + 1) * 5 * mm, 108 + 6.4 * mm) for i in range(kaesten_zahl)]
    form = s.new_shape()
    for k in kaesten:
        form.draw_rect(k)
    form.finish(color=(0.2, 0.2, 0.25), width=0.5)
    form.commit()
    for k, c in zip(kaesten, wert):
        s.insert_text((k.x0 + 3.2, k.y1 - 4.5), c, fontsize=11, fontname="hebo")
    woerter = [tuple(w[:5]) for w in s.get_text("words") if w[3] < 108 + 6.4 * mm + 2 and w[0] < 220]
    woerter += [tuple(w[:5]) for w in s.get_text("words") if w[1] > 180]
    if gelesen:
        letzter = kaesten[len(gelesen) - 1]
        woerter.append((kaesten[0].x0 + 2.5, kaesten[0].y0 + 3.5, letzter.x1 - 2.5, letzter.y1 - 3.5, gelesen))
    feld = {"rahmen": [kaesten[0].x0, kaesten[0].y0, kaesten[-1].x1, kaesten[-1].y1],
            "kaesten": [[k.x0, k.y0, k.x1, k.y1] for k in kaesten],
            "gefuellt": [i < len(wert) and wert[i] != " " for i in range(kaesten_zahl)], "offen": ""}
    pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    pfad = tmp_path / "scan.pdf"
    doc.save(pfad)
    doc.close()
    vorlage.close()
    return pfad, _KammOcrAttrappe(woerter, [feld]), feld


def _kamm_scan_funde(tmp_path, *args, **kw):
    from anonymisierer.analyse import analysiere_pdf
    pfad, attrappe, feld = _kamm_scan(tmp_path, *args, **kw)
    erg = analysiere_pdf(pfad, ALLE, [], [], ocr=attrappe, profil="hoch")
    assert erg["fehler"] is None, erg["fehler"]
    return erg["funde"], feld


@pytest.mark.parametrize("etikett,wert,kaesten_zahl,gelesen,kategorie", [
    ("Name", "LI", 5, "L", "namen"),                        # die Zeile der E2E-Probe (c_kamm_text_hausnr, 300 dpi)
    ("Familienname", "LI", 6, "I", "namen"),
    ("Name", "OK", 5, "K", "namen"),
    ("Name", "PFNUERL", 9, "P", "namen"),                   # sieben gefüllte Kästchen, ein Buchstabe gelesen
    ("Telefon", "0861123456", 12, "08", "telefon"),         # zehn gefüllte Kästchen, zwei Ziffern gelesen
])
def test_n6_kurz_gelesener_kammwert_geschwaerzt(tmp_path, etikett, wert, kaesten_zahl, gelesen, kategorie):
    funde, _ = _kamm_scan_funde(tmp_path, etikett, wert, kaesten_zahl, gelesen)
    stellen = [(f["kategorie"], st["text"]) for f in funde for st in f["stellen"] if st.get("an", True)]
    assert (kategorie, gelesen) in stellen, stellen


def test_n6_einzelner_buchstabe_nicht_weitergegeben(tmp_path):
    """Der eine gelesene Buchstabe „L“ des Namensfelds gilt nur im Feld – „Konfektionsgröße L“ derselben Seite bleibt."""
    funde, _ = _kamm_scan_funde(tmp_path, "Name", "LI", 5, "L", weitere=["Konfektionsgröße L"])
    stellen = [st for f in funde for st in f["stellen"] if st.get("an", True) and st["text"] == "L"]
    assert len(stellen) == 1, [(f["kategorie"], st) for f in funde for st in f["stellen"]]


@pytest.mark.parametrize("etikett,wert,kaesten_zahl,gelesen", [
    ("Staatsangehörigkeit", "DE", 4, "DE"),                 # AB4U-02: Kürzel hinter Feldnamen ohne Namensbezug
    ("Staatsangehörigkeit", "DE", 4, "D"),
    ("Anzahl der Kinder", "2", 3, "2"),
    ("Name", "X", 4, "X"),                                  # Kreuzchen
])
def test_n6_kurzer_kammwert_gegenproben(tmp_path, etikett, wert, kaesten_zahl, gelesen):
    funde, _ = _kamm_scan_funde(tmp_path, etikett, wert, kaesten_zahl, gelesen)
    stellen = [(f["kategorie"], st["text"]) for f in funde for st in f["stellen"] if st.get("an", True)]
    assert not [s for s in stellen if s[1] == gelesen], stellen


# ----------------------------------------------------------------------
# AB4U-10: Kleinstbilder ohne Ausnahme; AB4U-08: schnellere Vorstufen mit gleichem Ergebnis
# ----------------------------------------------------------------------
@pytest.mark.parametrize("form", [(1, 1), (3, 3), (2, 7), (7, 2), (1, 400), (400, 1), (5, 5), (0, 0)])
def test_ab4u_10_kleinstbilder(form):
    np = pytest.importorskip("numpy")
    for wert in (0, 128, 255):
        assert kammraster.kammfelder_finden(np.full(form, wert, dtype=np.uint8), 150) == []
        assert kammraster.kammfelder_finden(np.full(form, wert, dtype=np.uint8), 300) == []


def test_ab4u_08_verkleinern_und_perzentil_wie_vorher():
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(4)
    for form in [(7, 9), (100, 101), (351, 248), (1, 1), (5, 3)]:
        bild = rng.integers(0, 256, size=form, dtype=np.uint8)
        for f in (1, 2, 3):
            h, w = form[0] // f, form[1] // f
            alt = bild if f == 1 else bild[:h * f, :w * f].reshape(h, f, w, f).min(axis=(1, 3))
            assert np.array_equal(kammraster._verkleinern(np, bild, f), alt), (form, f)
        assert kammraster._perzentil_75(np, bild) == pytest.approx(float(np.percentile(bild, 75)))


def test_ab4u_08_kontroll_ocr_ohne_kammfeldsuche(tmp_path):
    """Eine Seite, deren Original kein Kammfeld hatte, liest die Kontroll-OCR ohne Kammfeld-Suche (Argument
    kamm_suchen=False); jede andere Seite wie bisher."""
    from anonymisierer import ocr
    pfad = tmp_path / "a.pdf"
    pfad.write_bytes(b"%PDF-1.4\n%%EOF\n")
    dienst = ocr.OcrDienst.__new__(ocr.OcrDienst)
    import threading
    dienst._lock = threading.Lock()
    dienst._ohne_kammsuche = set()
    dienst.sprache, dienst.tessdata = "deu", None
    dienst.kammsuche_vorgeben(pfad, 0, False)
    dienst.kammsuche_vorgeben(pfad, 1, True)
    ohne = dienst._auftrag_fuer(pfad, 0, 300, None, 0).args
    mit = dienst._auftrag_fuer(pfad, 1, 300, None, 0).args
    assert ohne[-1] is False and len(ohne) == len(mit) + 1
    dienst.kammsuche_vorgeben(pfad, 0, True)                   # zurückgenommen: wieder mit Suche
    assert dienst._auftrag_fuer(pfad, 0, 300, None, 0).args[1:] == (0,) + mit[2:]


# ----------------------------------------------------------------------
# AB4U-07: Mengen- und Betragsfelder ohne Personenbezug
# ----------------------------------------------------------------------
@pytest.mark.parametrize("etikett", ["Wohnfläche (m²)", "Progression in %", "Unfallrente monatlich",
                                     "Invaliditätsgrundsumme", "Beitrag jährlich", "Anzahl der Fahrzeuge"])
def test_ab4u_07_mengenfelder(etikett):
    from anonymisierer import restrisiko
    assert restrisiko._KAMM_MENGE_ETIKETT_RE.search(etikett)


@pytest.mark.parametrize("etikett", ["Name", "Telefon", "Geburtsdatum", "Kennzeichen", "Straße"])
def test_ab4u_07_personenfelder_keine_mengen(etikett):
    from anonymisierer import restrisiko
    assert not restrisiko._KAMM_MENGE_ETIKETT_RE.search(etikett)


def test_ab4u_07_mengenfeld_ohne_textverdacht(tmp_path):
    """Ein Mengenfeld mit einer Zahl („Jahresfahrleistung“ 12000, „Wohnfläche (m²)“ 145) gilt als frei: auch die
    Textregeln (Ziffernfolge) melden den Wert darin nicht (Kammfeldprobe der Abnahme 4, f01: „12000“ war gemeldet).
    Gegenprobe: die Telefonnummer im Feld darunter bleibt Verdacht."""
    pytest.importorskip("numpy")
    import pymupdf as fitz
    from anonymisierer import restrisiko
    from test_kammfelder_scan import _formular, _scan, _seitenfelder
    doc = _formular([("Jahresfahrleistung", "12000", 6), ("Wohnfläche (m²)", "145", 4),
                     ("Telefon", "0861123456", 11)], oben=False, titel=False)
    felder = _seitenfelder(doc)
    assert len(felder) == 3
    scan = _scan(doc, tmp_path / "scan.pdf", dpi=200)
    woerter, ziffern = [], []
    for w in doc[0].get_text("words"):
        (ziffern if w[4].isdigit() else woerter).append(tuple(w[:5]))
    for feld in felder:                                   # die Ziffern eines Felds als EIN Wort (Kammfeld-Lesung)
        drin = sorted(w for w in ziffern if kammraster.im_feld(feld, (w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
        woerter.append((min(w[0] for w in drin), min(w[1] for w in drin), max(w[2] for w in drin),
                        max(w[3] for w in drin), "".join(w[4] for w in drin)))
    verdacht = restrisiko.restrisiko_pruefen(scan, ocr_modus={0: "seite"}, ocr_woerter={0: woerter},
                                             kammfelder={0: felder})
    oben, mitte, unten = sorted(felder, key=lambda f: f["rahmen"][1])

    def im(feld, v):
        return any(kammraster.im_feld(feld, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2) for r in v.rechtecke)

    assert not [v.text for v in verdacht if im(oben, v) or im(mitte, v)], [(v.text, v.grund) for v in verdacht]
    assert [v for v in verdacht if im(unten, v)], [(v.text, v.grund) for v in verdacht]
    assert fitz is not None


# ----------------------------------------------------------------------
# AB4U-09: Wachstum der Regeln mit Fenster (8k gegen 64k Zeichen ohne Zeilenumbruch) und vieler Platzhalter
# ----------------------------------------------------------------------
def _wachstum(klein, gross, faktor, schranke):
    """Schranken knapp über dem gemessenen linearen Wachstum (Platzhalter 0,9, Personen- und Berufswort 1,0, „mit +
    Ziffern“ 1,4): die Eingriffe der Abnahme (Abfrage über alle Platzhalter ≈ 1,7; Satzanfang bzw. Zugang ohne
    Fenster ≥ 2) liegen darüber."""
    import zeitmessung
    klein()
    return zeitmessung.wachstum_messen(klein, gross, faktor, wiederholungen=1, schranke=schranke)


@pytest.mark.parametrize("baustein", [
    "Die Garage ist mit 4433 gesichert und das Tor mit der Nummer 17 versehen. ",
    # ohne Satzende: das Fenster nach vorn begrenzt die Suche nach dem Gegenstand – ohne Fenster (Eingriff R4 der
    # Abnahme) wächst sie quadratisch (8k gegen 64k Zeichen: Faktor 66 statt 8)
    "der Schuppen mit 5517 und ",
])
def test_ab4u_09_mit_ziffern_waechst_linear(baustein):
    klein = baustein * (8000 // len(baustein))
    gross = baustein * (64000 // len(baustein))
    wachstum, _, zeit = _wachstum(lambda: kennungsformen.zugangsdaten(klein),
                                  lambda: kennungsformen.zugangsdaten(gross), 8, 2.5)
    assert wachstum < 2.5, f"zugangsdaten wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_ab4u_09_personenwort_mit_verb_waechst_linear():
    baustein = "Nachbar Zettl hat den Brand gemeldet und Kollegin Wimmer rief zurück, "
    klein = baustein * (8000 // len(baustein))
    gross = baustein * (64000 // len(baustein))
    wachstum, _, zeit = _wachstum(lambda: personenkontext.personenwort_namen(klein),
                                  lambda: personenkontext.personenwort_namen(gross), 8, 1.6)
    assert wachstum < 1.6, f"personenwort_namen wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_ab4u_09_berufswort_mit_verb_waechst_linear():
    baustein = "Elektriker Miele kam am Montag, Glaser Frost ist frei und laut Klempner Dyson stimmt das; "
    klein = baustein * (8000 // len(baustein))
    gross = baustein * (64000 // len(baustein))
    wachstum, _, zeit = _wachstum(
        lambda: personenkontext.berufswort_namen(klein, alle=True, beleg_ohne_verb=True),
        lambda: personenkontext.berufswort_namen(gross, alle=True, beleg_ohne_verb=True), 8, 1.6)
    assert wachstum < 1.6, f"berufswort_namen wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_ab4u_09_viele_platzhalter_600_gegen_2400():
    """Wie AB3-08, aber 600 gegen 2400 Platzhalter (der Test der Abnahme 3 maß 75 gegen 600 und sah eine lineare
    Abfrage der Platzhalter nicht)."""
    baustein = "Code [ZUGANGSDATEN], Name [NAMEN], Tel. [TELEFON], Zeile mit Text. "
    ph = ["[ZUGANGSDATEN]", "[NAMEN]", "[TELEFON]"]
    klein, gross = baustein * 200, baustein * 800
    wachstum, _, zeit = _wachstum(lambda: pruefe_text(klein, platzhalter=ph),
                                  lambda: pruefe_text(gross, platzhalter=ph), 4, 1.5)
    assert wachstum < 1.5, f"pruefe_text wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"
