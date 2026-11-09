"""Tests der OCR-Lesart (anonymisierer/detektoren/ocr_lesart.py) und der unscharfen Etiketten
(anonymisierer/detektoren/etiketten_unscharf.py): Erkennung trotz typischer OCR-Lesefehler – NUR auf OCR-Text.

OCR-Seiten werden synthetisch gebaut: Wörter mit Rechtecken wie aus Tesseract (seitenmodell.seite_aufbauen mit
ocr_woerter, Quelle "ocr"); große Lücken werden wie im Programm zum Spaltentrenner "\\t\\t". Dieselben Texte
als Textebene (seitenmodell.dokument_aus_text) dienen als Gegenprobe: dort gilt keine Toleranz."""

import pytest

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

from anonymisierer import analyse, detektoren, seitenmodell
from anonymisierer.detektoren import Kontext
from anonymisierer.detektoren import etiketten_unscharf as eu
from anonymisierer.detektoren import ocr_lesart as ol
from anonymisierer.muster import KATEGORIEN

ALLE = {k[0] for k in KATEGORIEN if k[4]}


def _ocr_dok(zeilen, quelle="ocr"):
    """Seitenmodell einer OCR-Seite: je Zeile Zellen getrennt durch "\\t\\t" (große Lücke), Wörter durch " "."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    woerter = []
    y = 80.0
    for zi, zeile in enumerate(zeilen):
        x, wi = 50.0, 0
        for ci, zelle in enumerate(zeile.split("\t\t")):
            if ci:
                x += 60
            for w in zelle.split(" "):
                if not w:
                    x += 5
                    continue
                breite = 6.0 * len(w)
                woerter.append((x, y, x + breite, y + 12, w, 0, zi, wi))
                wi += 1
                x += breite + 4
        y += 18
    s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=woerter, ocr_quelle=quelle)
    doc.close()
    return seitenmodell.Dokument(None, [s])


def _detektor(name):
    return next(e for e in detektoren.REGISTER if e.name == name).funktion


def _treffer(dok, name, aktive=None):
    return [(t.kategorie, dok.text[t.start:t.ende]) for t in _detektor(name)(dok, Kontext(aktive or ALLE, "hoch"))]


# ----------------------------------------------------------------------
# Wo ist OCR-Text?
# ----------------------------------------------------------------------
def test_ocr_bereiche_nur_fuer_ocr_zeilen():
    text = ["Anschrift:\t\tBirkenallee 119, 27568: Bremerhaven", "Telefon: 01511:58548399"]
    ocr = _ocr_dok(text)
    assert ol.ocr_bereiche(ocr) == [(0, len(ocr.text))]
    assert ol.lesart(ocr) is not None and len(ol.lesart(ocr)) == len(ocr.text)
    textebene = seitenmodell.dokument_aus_text("\n".join(text))
    assert ol.ocr_bereiche(textebene) == []
    assert ol.lesart(textebene) is None
    bild = _ocr_dok(text, quelle="bild")                  # OCR eines Bildbereichs auf einer Textseite
    assert ol.ocr_bereiche(bild) == [(0, len(bild.text))]


# ----------------------------------------------------------------------
# Reparaturen: gleich lang, nur verwechselte Zeichen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("roh, erwartet", [
    ("8O331 München", "80331 München"),                     # O -> 0 in der PLZ
    ("Tel. O171 2345678", "Tel. 0171 2345678"),
    ("Schaden-Nr.: S081827865", "Schaden-Nr.: 5081827865"),   # S -> 5
    ("14.O7.1957", "14.07.1957"),
    ("DE36 8181 9553 8O46 1681 61", "DE36 8181 9553 8046 1681 61"),
    ("Telefonnummer 01511:58548399", "Telefonnummer 01511 58548399"),
    ("VS-Nr. 38:077.3762 2", "VS-Nr. 38 077.3762 2"),
    ("Versicherungsschein-Nr.: 37.211.169,7.", "Versicherungsschein-Nr.: 37.211.169.7."),
    ("Telefon 04131 728%41.", "Telefon 04131 728-41."),
    ("+49'(0)385 7948180", "+49 (0)385 7948180"),
    ("Konto NLBS WDRU.4155 8174 32.", "Konto NLBS WDRU 4155 8174 32."),
    ("erreichbar unter ©\n15 22 / 660 77 64", "erreichbar unter 0\n15 22 / 660 77 64"),
    ("Birkenallee 119, 27568: Bremerhaven", "Birkenallee 119, 27568  Bremerhaven"),
    ("Amtl. Kennzeichen:\t\tHFY:4312", "Amtl. Kennzeichen:\t\tHFY 4312"),
    ("Unfall\t\tHanseMerkur\t\t[1431 649 845", "Unfall\t\tHanseMerkur\t\t 1431 649 845"),
    ("Nordlicht\t\t_ [81.881.554.0", "Nordlicht\t\t   81.881.554.0"),
    ("97070 würzburg", "97070 Würzburg"),
])
def test_reparieren(roh, erwartet):
    neu = ol.reparieren(roh)
    assert neu == erwartet
    assert len(neu) == len(roh)


@pytest.mark.parametrize("roh", [
    "SV197328226", "L8S0NZWEM31", "DE36 8181", "Kundenservice", "Uhrzeit 10:05 Uhr", "Beitrag 1.234,56 EUR",
    "Versicherungsteuer 19% 7,50", "|234 567", "IBAN-Nr. 12", "Seite 1:2", "B1 Fahrerlaubnis",
])
def test_reparieren_laesst_echte_buchstaben_und_formen(roh):
    assert ol.reparieren(roh) == roh


# ----------------------------------------------------------------------
# Detektor "ocr.lesart"
# ----------------------------------------------------------------------
_ZEILEN = [
    "Anschrift:\t\tBirkenallee 119, 27568: Bremerhaven",
    "Versicherer des Gegners: Swiss Life, VS-Nr. 38:077.3762 2",
    "Versicherungsschein-Nr.: 37.211.169,7.",
    "Amtl. Kennzeichen:\t\tHFY:4312",
    "Kennzeichen:\t\tB-]JY 743",
    "Bitte prüfen Sie, ob auch Ihre Telefonnummer 01511:58548399 noch aktuell ist.",
]


def test_ocr_lesart_findet_verlesene_formen():
    dok = _ocr_dok(_ZEILEN)
    gefunden = set(_treffer(dok, "ocr.lesart"))
    assert ("plzort", "27568: Bremerhaven") in gefunden
    assert ("vertrag", "38:077.3762 2") in gefunden
    assert ("vertrag", "37.211.169,7") in gefunden
    assert ("kfz", "HFY:4312") in gefunden                   # die Stelle deckt, was auf der Seite steht
    assert ("kfz", "B-]JY 743") in gefunden
    assert ("telefon", "01511:58548399") in gefunden
    for t in _detektor("ocr.lesart")(dok, Kontext(ALLE, "hoch")):
        assert t.quelle.endswith(".ocr") or t.quelle.startswith("ocr."), t
        assert "\t\t" not in dok.text[t.start:t.ende]


def test_ocr_lesart_nur_auf_ocr_text():
    """Auf der Textebene eines PDFs gilt keine Lesefehler-Toleranz: dort ist "27568:" keine PLZ mit Ort und
    "HFY:4312" kein Kennzeichen."""
    text = "\n".join(_ZEILEN)
    textebene = seitenmodell.dokument_aus_text(text)
    assert _treffer(textebene, "ocr.lesart") == []
    funde = {f["text"] for f in analyse.analysiere_text(text, ALLE, [], [])}
    for verlesen in ("27568: Bremerhaven", "38:077.3762 2", "37.211.169,7", "HFY:4312", "01511:58548399"):
        assert verlesen not in funde


def test_ocr_lesart_ohne_neue_stellen_auf_sauberem_ocr_text():
    dok = _ocr_dok(["Anschrift:\t\tBirkenallee 119, 27568 Bremerhaven", "Telefon: 0471 9499955",
                    "Uhrzeit: 10:05 Uhr, Beitrag 1.234,56 EUR"])
    assert _treffer(dok, "ocr.lesart") == []


def test_ocr_lesart_in_der_analyse():
    """Ende-zu-Ende über _analysiere_dokument: die verlesenen Werte werden Funde mit ihrem Seitentext."""
    dok = _ocr_dok(_ZEILEN)
    funde = analyse._analysiere_dokument(dok, ALLE, [], [])
    texte = {(f["kategorie"], f["text"]) for f in funde}
    assert ("plzort", "27568: Bremerhaven") in texte
    assert ("kfz", "HFY:4312") in texte
    assert ("telefon", "01511:58548399") in texte


# ----------------------------------------------------------------------
# Unscharfe Etiketten
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, etikett, art", [
    ("Name, Vomame:\t\tKara, Özlem", "Name, Vomame", "person"),           # rn -> m
    ("Nordiicht Lebensversicherung AG - Kundenntimmer 76183905", "Kundenntimmer", "kennung"),
    ("Versicherungsnuarmmer\n40.190964 Y B34", "Versicherungsnuarmmer", "kennung"),
    ("Geburtsdaturn:\t\t14.07.1957", "Geburtsdaturn", "datum_geburt"),
    ("Anschrlft:\t\tBirkenallee 119", "Anschrlft", "adresse"),
    ("Telefom: 0911 123456", "Telefom", "kontakt"),
])
def test_unscharfe_etiketten(zeile, etikett, art):
    gefunden = [(zeile[s:e], a) for s, e, a, _ in eu.unscharfe_etiketten(zeile)]
    assert (etikett, art) in gefunden


@pytest.mark.parametrize("zeile", [
    "Unfallart: Vorfahrtsverletzung",           # ein anderes Wort, kein verlesener "Unfallort"
    "Nane: Max Mustermann",                      # kurzes Etikett ("Name"): nur exakt
    "Ort: Bonn",
    "Strasser:\t\tMax",                          # bekannter Nachname
    "Die Kennzeicben sind falsch",               # keine Etikett-Stellung
    "Geburtsdatum: 14.07.1957",                  # exakt – kein unscharfes Etikett
    "Gebürtsdatum: 14.07.1957",                  # Diakritika zählen schon beim exakten Vergleich nicht
])
def test_unscharfe_etiketten_gegenproben(zeile):
    assert eu.unscharfe_etiketten(zeile) == []


def test_unscharfe_etiketten_nur_auf_ocr_zeilen():
    zeilen = ["Name, Vomame:\t\tKara, Özlem", "Kundenntimmer\t\t76183905"]
    ocr = _ocr_dok(zeilen)
    werte = set(_treffer(ocr, "struktur.etikett_wert"))
    assert ("namen", "Kara, Özlem") in werte
    assert ("vertrag", "76183905") in werte
    textebene = seitenmodell.dokument_aus_text("\n".join(zeilen))
    assert ("vertrag", "76183905") not in set(_treffer(textebene, "struktur.etikett_wert"))


def test_unscharfes_etikett_ist_kein_name():
    from anonymisierer import namen
    for wort in ("Vomame", "Verscherungsnchmer", "Kundenntimmer"):
        assert namen._ist_sachwort(wort), wort
    for wort in ("Schneider", "Patel", "Ehrlich", "Adeyemi"):
        assert not namen._ist_sachwort(wort), wort


def test_unscharfe_etiketten_laufzeit():
    import time
    zeile = "Versicherungsnehmerin Dorothea Kaltenbrunner-Hofstätter wohnhaft Ebersberger Landstraße 117 " * 20
    eu.unscharfe_etiketten("Vomame: Max")                   # Index aufbauen
    t0 = time.perf_counter()
    eu.unscharfe_etiketten(zeile)
    assert time.perf_counter() - t0 < 1.0
