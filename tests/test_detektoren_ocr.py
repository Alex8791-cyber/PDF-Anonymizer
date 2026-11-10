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
from conftest import braucht_modell

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
    # PLZ-Reparaturen nur im Anschrift-Kontext (Review-Befund: ohne Anschrift wären es Beträge und Positionen)
    ("Wohnort:\t\t97070 würzburg", "Wohnort:\t\t97070 Würzburg"),
    ("Hauptstraße 5\n79098 freiburg", "Hauptstraße 5\n79098 Freiburg"),
    ("Anschrift: 27568: Bremerhaven", "Anschrift: 27568  Bremerhaven"),
    ("Tel. OO49 221 7214632", "Tel. 0049 221 7214632"),                # Block aus O am Rand: Nullen
])
def test_reparieren(roh, erwartet):
    neu = ol.reparieren(roh)
    assert neu == erwartet
    assert len(neu) == len(roh)


@pytest.mark.parametrize("roh", [
    "SV197328226", "L8S0NZWEM31", "DE36 8181", "Kundenservice", "Uhrzeit 10:05 Uhr", "Beitrag 1.234,56 EUR",
    "Versicherungsteuer 19% 7,50", "|234 567", "IBAN-Nr. 12", "Seite 1:2", "B1 Fahrerlaubnis",
    # Tarif- und Produktkürzel: ein Block aus mehreren Großbuchstaben am Anfang ist kein Lesefehler
    "Tarif: ZB100 Zahnersatz", "SB150\t\tSelbstbehalt", "BS100 Stationär", "GZ100 Gesundheit", "BG200 Beihilfe",
    # ohne Anschrift keine PLZ-Reparatur: Positionen, Beträge, Mengen
    "Rechnung 20231: Zahnbehandlung", "03000: Versichertenpauschale", "45678: Reparatur\t\t80,00",
    "Jahresfahrleistung\t\t15000 jährlich", "Einkommen\t\t35000 brutto", "97070 würzburg",
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


@pytest.mark.parametrize("zeilen", [
    # Tarif-Tabelle und Tarif-/Produktkürzel, Modellnamen (Review-Befund: "SB150 ⇥⇥ Selbstbehalt" als PLZ + Ort)
    ["Tarif\t\tBezeichnung\t\tBeitrag", "ZB100\t\tZahnbehandlung\t\t12,40", "BS100\t\tStationär\t\t45,20",
     "SB150\t\tSelbstbehalt\t\t12,10"],
    ["Tarif: ZB100 Zahnersatz", "Fahrzeug: Kawasaki Z1000 SX", "Typ S2000 Roadster", "BMW S1000 RR",
     "Tarif GZ100 Gesundheit", "BG200 Beihilfe", "Ihr Tarif ZB100 Zahnersatz bleibt unverändert."],
    # Beträge und Mengen hinter einem Etikett in der Nachbarzelle (Review-Befund: "15000 jährlich")
    ["Jahresfahrleistung\t\t15000 jährlich", "Einkommen\t\t35000 brutto", "Einkommen:\t\t45000 netto",
     "Kilometerstand\t\t45000 abgelesen", "Schadenhöhe\t\t12000 geschätzt", "Versicherungssumme\t\t25000 einmalig"],
    # Positionen und EBM-Ziffern mit Doppelpunkt (Review-Befund: "20231: Zahnbehandlung")
    ["Rechnung 20231: Zahnbehandlung", "03000: Versichertenpauschale", "10001: Arzthonorar\t\t120,00",
     "45678: Reparatur\t\t80,00", "01100: Unvorhergesehene Inanspruchnahme", "Vorgang 12345: Wasserschaden"],
])
def test_ocr_lesart_keine_plz_ohne_anschrift(zeilen):
    """PLZ + Ort, die erst die Lesart liefert, zählt nur im Anschrift-Kontext; ohne Anschrift sind es Kürzel,
    Beträge und Positionen (dieselben Zeilen ergeben auch auf der Textebene keine PLZ)."""
    for dok in (_ocr_dok(zeilen), seitenmodell.dokument_aus_text("\n".join(zeilen))):
        funde = analyse._analysiere_dokument(dok, ALLE, [], [])
        assert not [f["text"] for f in funde if f["kategorie"] == "plzort"]


@pytest.mark.parametrize("zeilen, plz_ort", [
    (["Herrn", "Max Mustermann", "Hauptstraße 5", "8O331 München"], "8O331 München"),    # Straße darüber
    (["Anschrift:\t\tBirkenallee 119, 27568: Bremerhaven"], "27568: Bremerhaven"),       # Straße davor
    (["Wohnort:\t\t97070 würzburg"], "97070 würzburg"),                                   # Etikett davor
    (["Max Mustermann", "Hauptstraße 5", "79098 freiburg"], "79098 freiburg"),
])
def test_ocr_lesart_plz_im_anschrift_kontext(zeilen, plz_ort):
    assert ("plzort", plz_ort) in set(_treffer(_ocr_dok(zeilen), "ocr.lesart"))


@pytest.mark.parametrize("text, pos_wort, erwartet", [
    ("Anschrift:\t\tBirkenallee 119, 27568: Bremerhaven", "27568", True),
    ("Wohnort: 97070 würzburg", "97070", True),
    ("Anschrlft: 97070 würzburg", "97070", True),                    # Etikett selbst verlesen
    ("Hauptstraße 5\n79098 freiburg", "79098", True),
    ("Anschrift:\n97070 würzburg", "97070", True),                   # Etikett am Ende der Zeile darüber
    ("Rechnung 20231: Zahnbehandlung", "20231", False),
    ("Jahresfahrleistung\t\t15000 jährlich", "15000", False),
    ("Tarif Komfort, 12000 Selbstbeteiligung", "12000", False),
    ("Hauptstraße 5\nRechnung 20231: Zahnbehandlung", "20231", False),  # Straße darüber zählt nur am Zeilenanfang
    ("Wohnort: Bonn\n45678: Reparatur", "45678", False),             # Etikett darüber hat schon seinen Wert
])
def test_anschrift_kontext(text, pos_wort, erwartet):
    assert ol.anschrift_kontext(text, text.index(pos_wort)) is erwartet


@pytest.mark.parametrize("zeilen", [
    ["Unfallanzeige", "Verletzte Körperteile:\t\tSchulter\t\tKnie", "Schulter:\t\tPrellung"],
    ["Leistungsübersicht", "Pflege: Ambulanter Pflegedienst Sonnenschein", "Pflege:\t\tHäusliche Pflege",
     "Pflege:\t\tStationärer Aufenthalt"],
    ["Nachnahme:\t\tPostbote", "Patent:\t\tEuropäisches Patentamt", "Spende:\t\tRotes Kreuz",
     "Signatur:\t\tElektronisch signiert"],
    ["Schulter\t\tlinks\t\tPrellung", "Knie\t\trechts\t\tZerrung", "Schulter\t\tSchultereckgelenksprengung"],
])
def test_keine_namen_aus_echten_woertern(zeilen):
    """Review-Befund: Körperteile, Verletzungen und Pflegebegriffe wurden über unscharfe Personen-Etiketten
    ("Schulter" ~ "Schüler", "Pflege" ~ "Pfleger") zu Namen – und per Weitergabe in alle Dokumente getragen."""
    funde = analyse._analysiere_dokument(_ocr_dok(zeilen), ALLE, [], [])
    assert not [f["text"] for f in funde if f["kategorie"] == "namen"]


@pytest.mark.parametrize("zeilen", [
    ["Vertragssumme: 125000 EUR", "Patientenzimmer:\t\t1204", "Seitennummer:\t\t1234", "Dienstzimmer: 3.12",
     "Wasserzeichen:\t\t12345678", "Versicherungskammer:\t\t12345678"],
    ["Fälligkeiten gehören:\t\t01.04.2024", "gehören:\t\t01.02.1980"],
])
def test_keine_kennung_aus_betraegen_und_raeumen(zeilen):
    """Review-Befund: "Vertragssumme" ~ "Vertragsnummer", "Patientenzimmer" ~ "Patientennummer", "gehören" ~
    "geboren" machten Beträge, Zimmernummern und Daten zu [VERTRAGS-NR] bzw. [GEB-DATUM]."""
    funde = analyse._analysiere_dokument(_ocr_dok(zeilen), ALLE, [], [])
    assert not [f["text"] for f in funde if f["kategorie"] in ("vertrag", "geburt")]


def test_unscharfe_etiketten_sind_markiert_und_keine_rollen_fuer_unterschriften():
    """Ein nur verlesen erkanntes Personen-Etikett macht die Zeile darüber nicht zum Unterschriftsnamen
    ("Verletzte Körperteile" über "Schulter:"); ein exaktes Rollen-Etikett schon."""
    from anonymisierer.detektoren import struktur, struktur_brief
    dok = _ocr_dok(["Name, Vomame:\t\tKara, Özlem", "Telefon:\t\t0911 123456"])
    markiert = {dok.text[e.start:e.ende]: e.unscharf for e in struktur.etiketten(dok.seiten[0])}
    assert markiert.get("Name, Vomame") is True and markiert.get("Telefon") is False
    for rolle, erwartet in (("Unterschrlft", []), ("Unterschrift", ["Peter Lustig"])):
        seite = _ocr_dok(["Peter Lustig", rolle]).seiten[0]
        namen = [seite.text[a:b] for a, b, *_ in struktur_brief._namen_ueber_rollen(seite, struktur.lage(seite))]
        assert namen == erwartet, rolle


# ----------------------------------------------------------------------
# Unscharfe Etiketten
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, etikett, art", [
    ("Name, Vomame:\t\tKara, Özlem", "Name, Vomame", "person"),           # rn -> m
    ("Nordiicht Lebensversicherung AG - Kundenntimmer 76183905", "Kundenntimmer", "kennung"),   # u -> ti
    # zwei typische Lesefehler bei einem langen Etikettwort (i -> l, m -> rn). Früher stand hier
    # "Versicherungsnuarmmer": ein hinzugelesenes "a" ist kein typischer OCR-Fehler, seit dem Review zählen für
    # Etiketten nur noch typische Lesefehler ("Vertragssumme" ist keine "Vertragsnummer")
    ("Verslcherungsnurnmer\n40.190964 Y B34", "Verslcherungsnurnmer", "kennung"),
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
    # Review-Befund: echte Wörter sind keine verlesenen Personen-/Anschrift-Etiketten (Körperteile, Pflege …)
    "Schulter:\t\tPrellung", "Verletzte Körperteile:\t\tSchulter\t\tKnie", "Pflege: Ambulanter Pflegedienst",
    "Patent:\t\tEuropäisches Patentamt", "Nachnahme:\t\tPostbote", "Vornahme:\t\tReparatur der Heizung",
    "Signatur:\t\tElektronisch signiert", "Verstand:\t\tklar", "Beruf:\t\tMalerin", "Spende:\t\tRotes Kreuz",
    "Fahrzeugalter:\t\t5 Jahre",
    # Review-Befund: Beträge, Räume und Verben sind keine verlesenen Kennungs-/Geburts-Etiketten
    "Vertragssumme: 125000 EUR", "Vertragssumme\t\t125000", "Patientenzimmer:\t\t1204", "Dienstzimmer: 3.12",
    "Geschäftszimmer: 2.014", "Seitennummer:\t\t1234", "Wasserzeichen:\t\t12345678",
    "Versicherungskammer:\t\t12345678", "Bayerische Versorgungskammer 81921 München",
    "Fälligkeiten gehören:\t\t01.04.2024", "gehören:\t\t01.02.1980",
    "Auftragsnehmer: 4711", "Leistungsnehmer:\t\t12345",
])
def test_unscharfe_etiketten_gegenproben(zeile):
    assert eu.unscharfe_etiketten(zeile) == []


@pytest.mark.parametrize("wort, etikett", [
    ("Vomame", "vorname"), ("Geburtsdaturn", "geburtsdatum"), ("Anschrlft", "anschrift"),
    ("Telefom", "telefon"), ("Kundenntimmer", "kundennummer"), ("Verscherungsnchmer", "versicherungsnehmer"),
])
def test_nur_typische_lesefehler(wort, etikett):
    assert eu.etikettwort_fuer(wort)[0] == etikett


@pytest.mark.parametrize("wort", [
    "Schulter", "Pflege", "Patent", "Nachnahme", "Vornahme", "Signatur", "Verstand", "Malerin", "Fahrzeugalter",
    "Vertragssumme", "Patientenzimmer", "Seitennummer", "Wasserzeichen", "gehören", "Unfallart",
    # unbekannte Nachnamen dicht an einem Etikett (Review-Befund): untypischer Fehler oder dem Sprachmodell bekannt
    "Ehmann", "Portner", "Witter", "Schüller", "Schuller", "Nachbaur", "Schildner", "Spenner", "Kanzler",
])
def test_kein_verlesenes_etikett(wort):
    assert eu.etikettwort_fuer(wort) is None


def test_ohne_sprachmodell_personen_etiketten_nur_exakt(monkeypatch):
    """Ohne Wortschatz des Sprachmodells lassen sich echte Wörter ("Schulter") nicht ausschließen: unscharfe
    Personen- und Anschrift-Etiketten entfallen dann, Kennungen und Daten (feste Form des Werts) bleiben."""
    monkeypatch.setattr(eu, "_wortschatz", lambda: None)
    eu.etikettwort_fuer.cache_clear()
    try:
        assert eu.unscharfe_etiketten("Name, Vomame:\t\tKara, Özlem") == []
        assert eu.unscharfe_etiketten("Anschrlft:\t\tBirkenallee 119") == []
        gefunden = [(a, e) for _, _, a, e in eu.unscharfe_etiketten("Geburtsdaturn:\t\t14.07.1957")]
        assert gefunden and gefunden[0][0] == "datum_geburt"
    finally:
        eu.etikettwort_fuer.cache_clear()


def test_unscharfe_etiketten_nur_auf_ocr_zeilen():
    zeilen = ["Name, Vomame:\t\tKara, Özlem", "Kundenntimmer\t\t76183905"]
    ocr = _ocr_dok(zeilen)
    werte = set(_treffer(ocr, "struktur.etikett_wert"))
    assert ("namen", "Kara, Özlem") in werte
    assert ("vertrag", "76183905") in werte
    textebene = seitenmodell.dokument_aus_text("\n".join(zeilen))
    assert ("vertrag", "76183905") not in set(_treffer(textebene, "struktur.etikett_wert"))


def test_unscharfes_etikett_ist_kein_name():
    """Verlesene Feldbezeichner, die die KI für Namen hält, verwirft der umhüllte Namens-Detektor – nur auf
    OCR-Text und nur in Etikett-Stellung. Früher prüfte namen._ist_sachwort das für JEDEN Text; seit dem
    Review-Befund (unbekannte Nachnamen auf der Textebene still verloren) kennt namen.py keine Lesefehler-Toleranz
    mehr."""
    from anonymisierer import namen
    for wort in ("Vomame", "Verscherungsnchmer", "Kundenntimmer", "Schneider", "Patel", "Ehrlich", "Adeyemi"):
        assert not namen._ist_sachwort(wort), wort
    zeilen = ["Name, Vomame:\t\tKara, Özlem", "(Unterschrift Verscherungsnchmer", "Kundenntimmer 76183905",
              "Mit freundlichen Grüßen", "Wohnert", "Gestern rief Ehmann an."]

    def ki(dok, kontext):                             # Namens-KI, die die üblichen Fehlgriffe macht
        aus = []
        for wort in ("Vomame", "Verscherungsnchmer", "Kundenntimmer", "Wohnert", "Ehmann", "Kara, Özlem"):
            s = dok.text.index(wort)
            aus.append(detektoren.Treffer(s, s + len(wort), "namen", "ner", 0.6))
        return aus
    gefiltert = ol._ner_ohne_verlesene_etiketten(ki)
    ocr = _ocr_dok(zeilen)
    assert sorted(ocr.text[t.start:t.ende] for t in gefiltert(ocr, Kontext(ALLE, "hoch"))) == \
        ["Ehmann", "Kara, Özlem", "Wohnert"]
    textebene = seitenmodell.dokument_aus_text("\n".join(zeilen))
    assert len(gefiltert(textebene, Kontext(ALLE, "hoch"))) == 6     # Textebene: keine Toleranz, nichts verworfen


def test_namens_detektor_ist_umhuellt():
    """Der Namens-Detektor "ner" trägt den OCR-Filter für verlesene Feldbezeichner – genau einmal."""
    eintraege = [e for e in detektoren.REGISTER if e.name == "ner"]
    assert len(eintraege) == 1 and eintraege[0].funktion.__name__ == "namen_ohne_verlesene_etiketten"
    ol._ner_umhuellen()                               # erneuter Import umhüllt nicht doppelt
    assert [e for e in detektoren.REGISTER if e.name == "ner"] == eintraege


_AKTENNOTIZ = ["Aktennotiz", "Teilnehmer der Besprechung: Ehmann, Portner, Witter, Schüller",
               "Gestern rief Ehmann wegen des Schadens an.", "Laut Portner war die Ampel rot.",
               "Wie Schüller mitteilte, liegt das Gutachten vor.", "Mit freundlichen Grüßen", "Wohnert",
               "Sachbearbeiter"]


@braucht_modell
@pytest.mark.parametrize("quelle", ["ocr", "text"])
def test_unbekannte_nachnamen_bleiben_namen(quelle):
    """Review-Befund (hoch): Ehmann/Ehemann, Portner/Partner, Witter/Twitter, Schüller/Schüler, Wohnert/Wohnort –
    auf der Textebene UND auf OCR-Seiten (Fließtext, Liste, Grußblock) bleiben es Namen."""
    dok = _ocr_dok(_AKTENNOTIZ) if quelle == "ocr" else seitenmodell.dokument_aus_text("\n".join(_AKTENNOTIZ))
    funde = analyse._analysiere_dokument(dok, ALLE, [], [])
    geschwaerzt = " | ".join(st["text"] for f in funde if f["kategorie"] == "namen" for st in f["stellen"]
                             if st.get("an", True))
    for name in ("Ehmann", "Portner", "Witter", "Schüller", "Wohnert"):
        assert name in geschwaerzt, (name, geschwaerzt)


def test_unscharfe_etiketten_laufzeit():
    import time
    zeile = "Versicherungsnehmerin Dorothea Kaltenbrunner-Hofstätter wohnhaft Ebersberger Landstraße 117 " * 20
    eu.unscharfe_etiketten("Vomame: Max")                   # Index aufbauen
    t0 = time.perf_counter()
    eu.unscharfe_etiketten(zeile)
    assert time.perf_counter() - t0 < 1.0
