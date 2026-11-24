"""Runde 5, Paket „Kennungen allgemein“: Befunde der Domänen-Durchsicht aller Maklersparten (Nummern der Befunde aus
der Durchsicht). Je Befund die Zeile der Falldatei und eine abgewandelte Schreibweise; dazu Gegenproben gegen
Über-Schwärzung (Beträge, Daten, Gebührenziffern, Fahrzeugschlüssel, Modell- und Produktcodes, Feld-Etiketten) und
die Selbstkontrolle: Was die Erkennung kennt, meldet sie, wenn es lesbar bliebe.

Gemeinsame Ursachen (allgemein behoben in kennungsformen.py, das Erkennung und Selbstkontrolle teilen):
  * Zwischenwörter zwischen Kennungs-Etikett und Wert („Personalnummer beim Arbeitgeber: 4711“) – Befunde 6, 30, 31,
    34, 36, 38, 52, 53, 62, 68, 73, 74, 95, 97;
  * Wertformen hinter Kennungs-Etiketten: Tausenderpunkt-Gruppen (1, 67), Codes mit Trennern und wenigen Ziffern (27),
    Buchungscodes (7), „#“ (78), Laufnummer vor dem Wert (59), MAC-Adresse (56), gruppierte Steuer-ID (73);
  * fehlende oder ausgeschlossene Etiketten (9, 11, 12, 35, 39, 52, 53, 56, 59, 62, 72, 74, 75, 76, 79, 80, 96);
  * Über-Schwärzung von Gebühren-, Katalog- und Fahrzeugschlüsseln (13, 17, 47) und IMEI als Kreditkarte (98).
Alle Werte sind erfunden."""

import re

import pymupdf as fitz
import pytest

from anonymisierer import analyse, muster
from anonymisierer.analyse import analysiere_text
from anonymisierer.restrisiko import pruefe_text, restrisiko_pruefen
from test_kennungen_makler import _ocr_dok, _paare

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


def _norm(t: str) -> str:
    return re.sub(r"[\s|_.,;:\"'„“”‚‘’»«→()\[\]#/-]", "", t).upper()


def _funde(text):
    return analysiere_text(text, ALLE, [], [])


def _angehakt(funde) -> list:
    return sorted((st["start"], st["ende"]) for f in funde for st in f["stellen"] if st.get("an", True))


def _abgedeckt(text: str, wert: str, funde=None) -> bool:
    """Ist jedes Vorkommen von `wert` in `text` ganz geschwärzt (jedes Zeichen aus Buchstaben/Ziffern in einer
    angehakten Stelle)?"""
    funde = _funde(text) if funde is None else funde
    spannen = _angehakt(funde)
    vorkommen = [m.start() for m in re.finditer(re.escape(wert), text)]
    assert vorkommen, f"{wert!r} steht nicht im Text"
    for a in vorkommen:
        for i in range(a, a + len(wert)):
            if text[i].isalnum() and not any(s <= i < e for s, e in spannen):
                return False
    return True


def _nicht_geschwaerzt(text: str, wert: str, funde=None) -> bool:
    """Bleibt jedes Vorkommen von `wert` ganz stehen (kein Zeichen in einer angehakten Stelle)?"""
    funde = _funde(text) if funde is None else funde
    spannen = _angehakt(funde)
    for m in re.finditer(re.escape(wert), text):
        if any(s < m.end() and m.start() < e for s, e in spannen):
            return False
    return True


def _gemeldet(text: str, wert: str) -> bool:
    """Meldet die Selbstkontrolle den GANZEN Wert (im ungeschwärzten Text)?"""
    w = _norm(wert)
    return any(w in _norm(v.text) for v in pruefe_text(text))


def _kategorie(text: str, wert: str) -> set:
    return {f["kategorie"] for f in _funde(text) for st in f["stellen"]
            if st.get("an", True) and wert in st["text"]}


# ======================================================================
# Befunde 1 und 67 (hoch): Tausenderpunkt-Gruppen hinter Kennungs-Etiketten sind Kennungen, kein Betrag
# ======================================================================
TAUSENDERPUNKT = [
    ("Versicherungsnummer: 123.456.789", "123.456.789"),
    ("Kundennummer: 4.711.208", "4.711.208"),
    ("Ihre Mitgliedsnummer: 7.654.321", "7.654.321"),
    ("zu Ihrem Vertrag Nr. 12.345.678 erhalten Sie die neue Beitragsübersicht.", "12.345.678"),
    ("Versicherungsschein-Nr. 3.456.782", "3.456.782"),
    ("Vers.-Nr. 300.447.112", "300.447.112"),
    ("Mitgliedsnummer: 2.468.135", "2.468.135"),
    ("Depot-Nr. 712.345.678\t\tKunden-Nr. 4.711.081", "712.345.678"),
    ("Depot-Nr. 712.345.678\t\tKunden-Nr. 4.711.081", "4.711.081"),
    ("Kassenzeichen: 921.103.215", "921.103.215"),
    ("Kassenzeichen 6.120.334.871", "6.120.334.871"),
    ("Versicherungsschein-Nr. 34.567.890", "34.567.890"),
    ("Kundennummer: 1.258.093", "1.258.093"),
    # abgewandelt
    ("Ihre Kunden-Nr. lautet 1.234.567.890.", "1.234.567.890"),
    ("Policennummer 7.111.562 (bitte stets angeben)", "7.111.562"),
]


@pytest.mark.parametrize("zeile, wert", TAUSENDERPUNKT)
def test_b1_b67_tausenderpunkt_hinter_etikett_geschwaerzt(zeile, wert):
    text = f"Isar Krankenversicherung AG – Beitragsanpassung\n{zeile}\nSehr geehrter Herr Lohmeier,"
    assert _abgedeckt(text, wert), _paare(_funde(text))


@pytest.mark.parametrize("zeile, wert", TAUSENDERPUNKT[:13])
def test_b1_b67_tausenderpunkt_selbstkontrolle(zeile, wert):
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


def _tabelle(pfad, zeilen):
    """PDF mit Textebene wie in der Domänen-Durchsicht (domaene/e2e.py): Zellen "⇥⇥" an festen Spalten x = 60, 250,
    420 – im Textmodell von analysiere_text verschöbe die Länge der ersten Zelle die Spalten."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    for zi, zeile in enumerate(zeilen):
        teile = zeile.split("\t\t")
        for si, zelle in enumerate(teile):
            seite.insert_text(((60, 250, 420)[si] if len(teile) > 1 else 60, 80 + 18 * zi), zelle, fontsize=11,
                              fontname="helv")
    doc.save(pfad)
    doc.close()
    return pfad


def _pdf_funde(pfad):
    e = analyse.analysiere_pdf(str(pfad), ALLE, [], [])
    assert e["fehler"] is None
    return e["funde"], {st["text"] for f in e["funde"] for st in f["stellen"] if st.get("an", True)}


def _pdf_gemeldet(pfad) -> set:
    return {_norm(v.text) for v in restrisiko_pruefen(str(pfad))}


@pytest.mark.parametrize("zeilen, werte", [
    (["Bestandsliste Kunde", "Vertragsnr.\t\tSparte\t\tBeitrag", "12.345.678\t\tKV\t\t612,48 €",
      "23.456.789\t\tPHV\t\t89,00 €"], ["12.345.678", "23.456.789"]),
    (["Bestandsliste Kunde", "Sparte\t\tVertragsnummer\t\tBeitrag", "Bausparen\t\t6.012.345.678\t\t50,00",
      "Fondsdepot\t\t893.104.552\t\t100,00"], ["6.012.345.678", "893.104.552"]),
    (["Vertragsübersicht", "Gesellschaft\t\tVers.-Nr.\t\tJahresbeitrag",
      "Musterleben AG\t\t52.418.736\t\t480,00 EUR", "Bausparkasse Süd\t\t3.904.617.205\t\t600,00 EUR"],
     ["52.418.736", "3.904.617.205"]),
])
def test_b1_b67_tausenderpunkt_in_kennungsspalte(tmp_path, zeilen, werte):
    pdf = _tabelle(tmp_path / "bestand.pdf", zeilen)
    funde, angehakt = _pdf_funde(pdf)
    for wert in werte:
        assert wert in angehakt, (wert, _paare(funde))
    for betrag in ("612,48 €", "89,00 €", "50,00", "480,00 EUR", "100,00", "600,00 EUR"):
        assert not any(betrag in t for t in angehakt), (betrag, _paare(funde))
    gemeldet = _pdf_gemeldet(pdf)
    for wert in werte:
        assert _norm(wert) in gemeldet, (wert, gemeldet)


@pytest.mark.parametrize("text, betrag", [
    ("Versicherungssumme: 150.000 EUR", "150.000"),
    ("Sterbegeld: 5.000", "5.000"),
    ("Jahresbeitrag: 1.234,56 EUR", "1.234,56"),
    ("Darlehenskonto: 50.000 EUR", "50.000"),
    ("Darlehenskonto: 1.500.000", "1.500.000"),
    ("Beitragskonto: Saldo 1.250 EUR", "1.250"),
    ("Bausparsumme: 50.000 EUR, Guthaben 12.345 EUR", "12.345"),
    ("Kundennummer bitte bei Zahlungen angeben: 1.234,56 EUR", "1.234,56"),
    ("Ihre Versicherungssumme von 50.000 EUR bleibt unverändert.", "50.000"),
    ("Deutsche Telekom AG\t\t200\t\t5.432,10", "5.432,10"),
    ("Vertragsnummer: 4.711.208 EUR Selbstbeteiligung", "4.711.208"),
])
def test_b1_b67_gegenprobe_betraege_bleiben(text, betrag):
    assert _nicht_geschwaerzt(text, betrag), _paare(_funde(text))


# ======================================================================
# Zwischenwörter zwischen Kennungs-Etikett und Wert (Befunde 6, 30, 31, 34, 36, 38, 52, 62, 68, 95, 97)
# ======================================================================
ZWISCHENWOERTER = [
    # Befund 6
    ("Personalnummer beim Arbeitgeber: 4711", "4711"),
    ("Mitgliedsnummer bei der Ärzteversorgung: 8821", "8821"),
    ("Versicherungsnummer des Ehepartners: KV-0815", "KV-0815"),
    ("Personalnummer des Arbeitnehmers: 3318", "3318"),
    ("Mitgliedsnummer im Versorgungswerk: 5527", "5527"),
    ("Versichertennummer bei der Pflegekasse: 4711 0815 33", "4711 0815 33"),
    # Befund 30
    ("Akku: Bosch PowerTube 625, Seriennummer laut Rechnung: AKX-74Q-BZ1", "AKX-74Q-BZ1"),
    ("Rahmennummer lt. Kaufvertrag: WAC-74Q-BZ1", "WAC-74Q-BZ1"),
    ("Rahmennummer laut Rechnung: WAC1193K4471", "WAC1193K4471"),
    ("Seriennummer gemäß Garantiekarte: SN-55 0193", "SN-55 0193"),
    # Befund 34
    ("Führerscheinnummer laut Feld 5 des Kartenführerscheins: N1907WW3L41", "N1907WW3L41"),
    ("Führerschein-Nr. des Zusatzfahrers: J0405KL7P12", "J0405KL7P12"),
    # Befund 36
    ("Vertragsnummer beim Vorversicherer: KH-55 667 788", "KH-55 667 788"),
    ("Versicherungsnummer bei der HUK-COBURG: 55 667 788-K", "55 667 788-K"),
    # Befund 38
    ("Kundennummer bei der BMW Bank: 88-1194-03", "88-1194-03"),
    ("Kundennummer bei der Mercedes-Benz Bank: 1194-KL", "1194-KL"),
    # Befund 62
    ("MaStR-Nummer der Einheit: SEE912345678901", "SEE912345678901"),
    ("MaStR-Nr. Anlagenbetreiber: ABR987654321098", "ABR987654321098"),
    # Befund 68
    ("Vorgangsnummer Ihres Online-Antrags: 7HXK-92LQ-QA", "7HXK-92LQ-QA"),
    ("Referenznummer für Rückfragen: KX-4711-QZ", "KX-4711-QZ"),
    ("Kundennummer bei der Musterbank: Q-0815", "Q-0815"),
    ("Schadennummer zu Ihrer Online-Meldung: SK-7Q3-XW92", "SK-7Q3-XW92"),
    ("Versicherungsnummer Ihres Hausratvertrags: HR-4711-0815", "HR-4711-0815"),
    # Befunde 95, 97
    ("Vers.-Schein-Nr. des Vorvertrags: 44 556677 8", "44 556677 8"),
    ("Vorgangsnummer der Polizei: 1234-567890-23/5", "1234-567890-23/5"),
    # abgewandelt
    ("Ihre Kundennummer bei uns lautet 7740-KX.", "7740-KX"),
    ("Aktenzeichen der Staatsanwaltschaft München I: 410 Js 1234/25", "410 Js 1234/25"),
]


@pytest.mark.parametrize("zeile, wert", ZWISCHENWOERTER)
def test_zwischenwoerter_zwischen_etikett_und_wert(zeile, wert):
    text = f"Schadenmeldung\n{zeile}\nMit freundlichen Grüßen"
    assert _abgedeckt(text, wert), _paare(_funde(text))


@pytest.mark.parametrize("zeile, wert", ZWISCHENWOERTER)
def test_zwischenwoerter_selbstkontrolle(zeile, wert):
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("zeilen, frei", [
    # Datum, Betrag, Uhrzeit, Jahresbereich, Version hinter Zwischenwörtern sind keine Kennung
    (["Vertragsnummer und Beginn: 01.04.2025"], "01.04.2025"),
    (["Kundennummer bitte bei Zahlungen angeben: 1.234,56 EUR"], "1.234,56"),
    (["Versicherungsnummer für das Jahr: 2025"], "2025"),
    (["Schadennummer folgt mit separatem Schreiben. Telefon: 0821 4711"], "0821 4711"),
    (["Vertragsnummer gilt für den Zeitraum: 2024/2025"], "2024/2025"),
    (["Kundennummer und Software-Version: 3.2.1"], "3.2.1"),
    (["Referenznummer der Norm: DIN EN ISO 9001"], "9001"),
    (["Versicherungsnummer im Tarif: KOMFORT 2024"], "KOMFORT 2024"),
    (["Die Vertragsnummer ändert sich nicht. Ab dem 01.01.2026 gilt: 300 EUR Selbstbeteiligung"], "300"),
    (["Kundennummer, Name und Anschrift: siehe Seite 2"], "2"),
    (["Vertragsnummer bei Rückfragen bitte angeben, Hotline: 0800 1234567"], "0800 1234567"),
    (["Versicherungsnummer des Fahrzeugs und Kennzeichen: M-AB 123"], "M-AB 123"),
    # Zeitangaben hinter einer Ergänzung ohne Ankündigung bzw. hinter Zwischenwörtern sind keine Kennung
    (["Policennummer der Hausratversicherung 2024/2025"], "2024/2025"),
    (["Beitragsnummer für das Jahr 2024/25"], "2024/25"),
    (["Rechnungsnummer für die Monate 01-06/2025"], "01-06/2025"),
    (["Kundennummer bei uns seit 2019"], "2019"),
    (["Vertragsnummer des Vorvertrags, gültig: 01/2026"], "01/2026"),
])
def test_zwischenwoerter_gegenproben(zeilen, frei):
    text = "\n".join(zeilen)
    funde = _funde(text)
    assert not any(f["kategorie"] == "vertrag" and frei in st["text"] for f in funde for st in f["stellen"]
                   if st.get("an", True)), _paare(funde)


# Befund 62 (Wertform): die Nummer im Marktstammdatenregister – Kürzel der Art (SEE, SNE, SGE, EEG, ABR) und zwölf
# Ziffern – ist auch ohne Etikett eine Kennung (Anlage bzw. Betreiber, bei einer privaten PV-Anlage eine Person)
@pytest.mark.parametrize("zeile, wert", [
    ("Marktstammdatenregister-Nummer: ABR911223344556", "ABR911223344556"),
    ("Die PV-Anlage (SEE912345678901) wurde am 01.04.2024 in Betrieb genommen.", "SEE912345678901"),
    ("Einheit SEE912345678901 des Betreibers ABR987654321098", "ABR987654321098"),
])
def test_b62_mastr_nummer(zeile, wert):
    assert _abgedeckt(zeile, wert), _paare(_funde(zeile))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("text, frei", [
    ("Bestellung SEE9123456789012 vom 03.02.2025", "SEE9123456789012"),     # 13 Ziffern: keine MaStR-Nummer
    ("Modell SEE1234 aus dem Katalog.", "SEE1234"),                           # zu kurz
    ("Wechselrichter SEE 912345678901 (Prospekt)", "SEE 912345678901"),       # getrennt: keine MaStR-Form
    ("Anlagentyp EEG 2023 nach dem Erneuerbare-Energien-Gesetz", "EEG 2023"),
])
def test_b62_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 7: Buchungscodes (Filekey, Buchungsreferenz, Reservierungscode, PNR, Booking reference)
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Filekey: K7QXMZ", "K7QXMZ"),
    ("Buchungsreferenz: 4Z9K7L", "4Z9K7L"),
    ("Reservierungscode: 7HQ2LM", "7HQ2LM"),
    ("Booking reference: Q8ZP4M", "Q8ZP4M"),
    ("Buchungsnummer: 6XK2QF", "6XK2QF"),
    ("Ihr Buchungscode lautet K4RT9P.", "K4RT9P"),
    ("PNR: KXQRZN", "KXQRZN"),
    ("Buchungscode: KXQRZM", "KXQRZM"),
    # abgewandelt
    ("Ihre Buchungsreferenz für die Reise lautet: Q7W2KD", "Q7W2KD"),
    ("Record locator: ZXKQPT", "ZXKQPT"),
])
def test_b7_buchungscode(zeile, wert):
    text = f"Buchungsbestätigung\n{zeile}\nGute Reise!"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("text, frei", [
    ("Buchungsstatus: STORNO", "STORNO"),
    ("Buchungscode: OFFEN", "OFFEN"),
    ("Flug LH 1838 von MUC nach PMI", "1838"),
    ("Strecke: MUC-PMI, Abflug 07:45", "MUC-PMI"),
    ("Buchungsreferenz: siehe Anlage", "Anlage"),
    ("BOOKING REFERENCE: CONFIRMED", "CONFIRMED"),
])
def test_b7_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 9: englische Etiketten in Versalien (nur die Kennungen; Namen bearbeitet das Paket Personen)
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("TICKET NUMBER: 220 2345678901", "220 2345678901"),
    ("FREQUENT FLYER: LH 992004471123", "LH 992004471123"),
    ("Patient ID: 0098812", "0098812"),
    ("Ticket number 220-2345678903", "220-2345678903"),
    ("Frequent Flyer Number: MS 445566778", "MS 445566778"),
])
def test_b9_englische_kennungs_etiketten(zeile, wert):
    text = f"ELECTRONIC TICKET ITINERARY RECEIPT\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))


@pytest.mark.parametrize("text, frei", [
    ("Flight No.: LH 1838", "1838"),
    ("Seat: 23A\t\tGate: B12", "23A"),
    ("Room No.: 214", "214"),
])
def test_b9_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 11: „Kennnummer der Karte“ (EHIC) – „kenn“ schließt nur Kennzeichen/Kennziffer aus
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("8. Kennnummer der Karte: 80276001570012345678", "80276001570012345678"),
    ("Kennnummer der Karte 80276 00157 0098765432", "80276 00157 0098765432"),
    ("Persönliche Kennnummer: 0098765432", "0098765432"),
])
def test_b11_kennnummer_der_karte(zeile, wert):
    text = f"Europäische Krankenversicherungskarte (Kopie)\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert)


def test_b11_gegenprobe_kennnummer_des_traegers():
    """Feld 7 der Karte („Kennnummer des Trägers“) ist das Institutionskennzeichen der Krankenkasse – keine Kennung der
    Person; Feld 6 und 8 schon."""
    text = "\n".join(["Europäische Krankenversicherungskarte (Kopie)", "6. Persönliche Kennnummer: 0098765432",
                      "7. Kennnummer des Trägers: 108310400", "8. Kennnummer der Karte: 80276001570012345678"])
    funde = _funde(text)
    assert _nicht_geschwaerzt(text, "108310400", funde), _paare(funde)
    assert _abgedeckt(text, "0098765432", funde) and _abgedeckt(text, "80276001570012345678", funde), _paare(funde)


# ======================================================================
# Befund 12: Kürzel vor „Nr.“ (HKP Nr.)
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Hallo Herr Steinbeis, anbei der HKP Nr. 2026-0341 von Dr. Fenske.", "2026-0341"),
    ("Anbei der KVA Nr. 2026-0777 zur Prüfung.", "2026-0777"),
])
def test_b12_kuerzel_vor_nr(zeile, wert):
    text = f"Betreff: Zahnzusatz\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))


def test_b12_gegenprobe_telefon_nr_ist_keine_kennung():
    """„Tel. Nr.“ ist kein Kennungs-Etikett: die Rufnummer bleibt eine Telefonnummer (nicht [VERTRAGS-NR])."""
    text = "Rückruf unter Tel. Nr. 0815 4711"
    assert _kategorie(text, "0815 4711") <= {"telefon"}, _paare(_funde(text))


@pytest.mark.parametrize("text, frei", [
    ("Siehe Pos. Nr. 12 der Rechnung", "12"),
    ("GOÄ Nr. 5855 wurde zweifach berechnet", "5855"),
    ("Art. Nr. 4711-08 ist nicht lieferbar", "4711-08"),
    ("PZN Nr. 04884569 laut Rezept", "04884569"),
])
def test_b12_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befunde 13, 17, 47: Gebühren-/Katalogspalten und Fahrzeugschlüssel bleiben stehen
# ======================================================================
@pytest.mark.parametrize("zeilen, frei", [
    (["Liquidation zahnärztliche Behandlung", "Datum\t\tGOZ-Nr.\t\tBetrag", "12.03.2025\t\t0010\t\t12,94 €",
      "12.03.2025\t\t2197\t\t16,82 €", "19.03.2025\t\t5120\t\t287,31 €"], ["0010", "2197", "5120"]),
    (["Rechnung Facharztpraxis Orthopädie", "Datum\t\tGOÄ-Nr.\t\tBetrag", "02.09.2025\t\t5855\t\t53,62 €",
      "02.09.2025\t\t3511\t\t5,36 €"], ["5855", "3511"]),
    (["Rechnung Praxis Dr. Fuchsberger", "Datum\t\tGeb.-Nr.\t\tBetrag", "09.09.2025\t\t0410\t\t19,82 €"], ["0410"]),
    (["Zahnärztliche Rechnung", "Datum\t\tGeb.-Ziffer\t\tBetrag", "16.10.2025\t\t2120\t\t104,83 €"], ["2120"]),
    (["Abrechnung Labor", "Datum\t\tBEL-Nr.\t\tBetrag", "16.10.2025\t\t0010\t\t14,20 €"], ["0010"]),
    (["Abrechnung Kassenpraxis", "Datum\t\tEBM-Nr.\t\tBetrag", "16.10.2025\t\t03000\t\t14,20 €"], ["03000"]),
    (["Apothekenquittung (Privatrezept)", "PZN\t\tArtikel\t\tPreis",
      "01126111\t\tIbuprofen 600 mg 50 St.\t\t12,49 €"], ["01126111"]),
    (["Privatrezept - Apotheke am Rathaus", "PZN 04884569 Pantoprazol 20 mg, 28 St., 9,98 €"], ["04884569"]),
    (["Liquidation", "GOZ-Nr. 2197: adhäsive Füllung, 16,82 €"], ["2197"]),
    (["Fahrzeugdaten laut Zulassungsbescheinigung Teil I", "Herstellerschlüsselnummer (HSN): 0603",
      "Schlüssel-Nr. 2.1/2.2: 0005/CXY"], ["0603", "0005/CXY", "2.1/2.2"]),
    (["Fahrzeugdaten für das Vergleichsangebot", "Herstellerschlüssel-Nr.: 0588", "Herstellernummer (zu 2.1): 0005",
      "HSN-Nr. 0603 / TSN-Nr. BJT"], ["0588", "0005", "0603", "BJT"]),
    (["Typschlüsselnummer (TSN): AQZ", "Schlüsselnummer zu 2.2: 123"], ["AQZ", "123"]),
    (["Fahrzeugdaten: HSN/TSN 0603/BJT, Erstzulassung 03/2019, 110 kW"], ["0603/BJT"]),
])
def test_b13_b17_b47_katalog_und_schluessel_bleiben(zeilen, frei):
    text = "\n".join(zeilen)
    funde = _funde(text)
    for wert in frei:
        assert _nicht_geschwaerzt(text, wert, funde), (wert, _paare(funde))


def test_b47_fahrzeugschluessel_in_diebstahlanzeige_bleibt_kennung():
    """Gegenprobe: die Schlüsselnummer eines Fahrzeugschlüssels (Schlüssel, nicht Typschlüssel) bleibt Kennung."""
    text = "Diebstahlanzeige\nSchlüsselnummer des Ersatzschlüssels: 7Q4-88213-KX"
    assert _abgedeckt(text, "7Q4-88213-KX"), _paare(_funde(text))


# ======================================================================
# Befund 27/79: Geräte-ID, Sensor-ID, Device-ID – Codes mit Trennern und wenigen Ziffern
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("alte Geräte-ID: TLX-KQ8B-ZR3M, neue Geräte-ID: TLX-PW4N-HX7Q", "TLX-KQ8B-ZR3M"),
    ("alte Geräte-ID: TLX-KQ8B-ZR3M, neue Geräte-ID: TLX-PW4N-HX7Q", "TLX-PW4N-HX7Q"),
    ("Ihre Geräte-ID: TLX-PW4N-HX7Q", "TLX-PW4N-HX7Q"),
    ("Sensor-ID: TLX-PW4N-HX7Q", "TLX-PW4N-HX7Q"),
    ("Geräte-ID: 6D92078A-8246-4BA4-AE5B-76104861E7DC", "6D92078A-8246-4BA4-AE5B-76104861E7DC"),
    ("Antrag gestartet\t\t12.03.2025 14:03:22\t\tGeräte-ID 3f2504e0-4f89", "3f2504e0-4f89"),
    ("Device-ID: QX-7RT2-MKP", "QX-7RT2-MKP"),
    ("Ident-Vorgang: IDN-4K7Q2", "IDN-4K7Q2"),
    ("Identifizierung\t\t12.03.2025 14:05:10\t\tVideoIdent VID-77812-QZ", "VID-77812-QZ"),
])
def test_b27_b79_geraete_id(zeile, wert):
    text = f"Telematik-Tarif – Bestätigung Gerätetausch\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("text, frei", [
    ("Gerätetyp: TLX-Mini", "TLX-Mini"),
    ("Geräte-ID: siehe Rückseite des Steckers", "Rückseite"),
    ("Sensor-ID: BOSCH-XL", "BOSCH-XL"),
    ("Modell: WX-200B, Version 2.1", "WX-200B"),
    ("Kunden-ID: DE-BY-AB", "DE-BY-AB"),
])
def test_b27_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 31: alter Papierführerschein – „Nr.“ hinter dem Ausweis-Wort derselben Zeile
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Führerschein Klasse 3 vom 12.04.1985, Nr. 355/85 (Landratsamt Rosenheim)", "355/85"),
    ("Führerschein der Klasse 3, ausgestellt am 03.06.1982 unter der Nr. 1187/82", "1187/82"),
    ("Personalausweis, ausgestellt am 01.02.2019 in Rosenheim, Nr. L01X00T47", "L01X00T47"),
])
def test_b31_nr_hinter_ausweiswort(zeile, wert):
    text = f"Angaben zum Fahrer (Kfz-Antrag)\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("text, frei", [
    ("Führerschein Klasse B seit 2011, Pos. Nr. 1/2 der Checkliste", "1/2"),
    ("Kopie Führerschein (Vorder- und Rückseite), Seite 3 von 4", "3"),
    ("Verhältnis 300/150 laut Tarif", "300/150"),
])
def test_b31_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 34: „Führerschein“ allein mit Führerscheinform, Ausweis-Wörter ohne „Nr.“ (Befund 75)
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Führerschein: N1907WW3L41, Klasse B seit 02.09.2011", "N1907WW3L41"),
    ("Führerschein J0405KL7P12 (Klasse B)", "J0405KL7P12"),
    # Befund 75
    ("Der Antragsteller hat sich mit seinem Reisepass CF9JKRTN7 ausgewiesen.", "CF9JKRTN7"),
    ("Die Ehefrau legte ihren Personalausweis LZ6KR4P9T vor.", "LZ6KR4P9T"),
    ("Legitimiert durch Personalausweis T22K0M9P4, ausgestellt von der Stadt Augsburg.", "T22K0M9P4"),
    ("Zusätzlich vorgelegt: Reisepass C7HJ2NP4X (gültig bis 03/2032).", "C7HJ2NP4X"),
    ("Die Identität wurde zusätzlich anhand des Reisepasses CF9JKRTN7 geprüft.", "CF9JKRTN7"),
])
def test_b34_b75_ausweiswort_ohne_nr(zeile, wert):
    text = f"Legitimationsprüfung\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("text, frei", [
    ("Führerschein: Klasse B seit 02.09.2011", "02.09.2011"),
    ("Reisepass gültig bis 03/2032", "03/2032"),
    ("Personalausweis liegt vor, Kopie in der Akte 2025", "2025"),
    ("Führerschein seit 2011, Klasse BE und C1E", "C1E"),
])
def test_b34_b75_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


def test_b34_kein_fehlverdacht_anschrift_hinter_feldverweis():
    """„Führerscheinnummer laut Feld 5“ ist keine Straße mit Hausnummer."""
    for zeile in ("Führerscheinnummer laut Feld 5 des Kartenführerscheins: N1907WW3L41",
                  "Angaben laut Feld 7 der Bescheinigung", "Führerscheinnummer gem. Feld 5: J0405KL7P12"):
        assert not any("Feld" in v.text and "Anschrift" in v.grund for v in pruefe_text(zeile)), \
            [(v.text, v.grund) for v in pruefe_text(zeile)]
    # Gegenprobe: eine Straße mit großem Artikel bleibt Verdacht
    verdacht = pruefe_text("Neue Anschrift ab Juli: Am Feld 5")
    assert any("Anschrift" in v.grund and "Am Feld 5" in v.text for v in verdacht), verdacht


# ======================================================================
# Befund 35: Zulassungsbescheinigung Teil I/II, ZB I/II, Fahrzeugbrief, Fahrzeugschein
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Zulassungsbescheinigung Teil II Nr.: ZT482913", "ZT482913"),
    ("Nr. der Zulassungsbescheinigung Teil I: AH 1192847", "AH 1192847"),
    ("ZB Teil II Nr.: ZT482913", "ZT482913"),
    ("Fahrzeugbrief-Nr.: ZT123456", "ZT123456"),
    ("Fahrzeugschein Nr. AB 1234567", "AB 1234567"),
    ("ZB II: ZT 482913", "ZT 482913"),
])
def test_b35_zulassungsbescheinigung(zeile, wert):
    text = f"Diebstahlanzeige (Teilkasko)\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


# ======================================================================
# Befund 39: Komposita auf „-karte“ (Tankkarte, Ladekarte) als Etikett und Spaltenkopf
# ======================================================================
def test_b39_tankkarte_spalte():
    text = "\n".join(["Fuhrparkliste (Anlage zur Kfz-Flottenversicherung)", "Fahrer\t\tKennzeichen\t\tTankkarte",
                      "Marco Strohmaier\t\tRO-MS 301\t\t7083 4400 1188 2207",
                      "Jana Lichtenegger\t\tRO-JL 302\t\t7083 4400 1188 3319"])
    funde = _funde(text)
    for wert in ("7083 4400 1188 2207", "7083 4400 1188 3319"):
        assert _abgedeckt(text, wert, funde), (wert, _paare(funde))


@pytest.mark.parametrize("zeile, wert", [
    ("Tankkarte (Aral Fleet): 7083 4400 1188 2207, gesperrt am 12.11.2025", "7083 4400 1188 2207"),
    ("Ladekarte: DE-EVB-4471088", "DE-EVB-4471088"),
])
def test_b39_tankkarte_etikett(zeile, wert):
    text = f"Einbruch in Firmenfahrzeug – entwendete Gegenstände\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))


@pytest.mark.parametrize("text, frei", [
    ("Landkarte: Maßstab 1:50000", "1:50000"),
    ("Speisekarte 2025 im Anhang", "2025"),
])
def test_b39_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 48: Seriennummer-Spalte mit nur einem Etikett im Kopf (Stehlgutliste)
# ======================================================================
@pytest.mark.parametrize("zeilen, werte, preise", [
    (["Stehlgutliste zur Hausratschadenanzeige", "Gegenstand\t\tKaufpreis\t\tSeriennummer",
      "Spiegelreflexkamera Nikon D7500\t\t1.099,00 EUR\t\t3049217",
      "Objektiv Nikkor 18-140 mm\t\t449,00 EUR\t\t62231874",
      "Armbanduhr\t\t895,00 EUR\t\t4521", "Spielkonsole Sony PS5\t\t549,00 EUR\t\tE31K8TQ"],
     ["3049217", "62231874", "4521", "E31K8TQ"], ["1.099,00 EUR", "449,00 EUR", "895,00 EUR", "549,00 EUR"]),
    (["Schadenaufstellung Einbruchdiebstahl", "Gegenstand\t\tAnschaffungspreis\t\tSerien-Nr.",
      "Notebook Lenovo ThinkPad T14\t\t1.299,00 €\t\tPF3K9XZ2", "E-Bike Cube Kathmandu\t\t2.499,00 €\t\tWCU88213",
      "Kopfhörer Bose QC45\t\t279,00 €\t\t077162"],
     ["PF3K9XZ2", "WCU88213", "077162"], ["1.299,00", "2.499,00", "279,00"]),
])
def test_b48_seriennummer_spalte(tmp_path, zeilen, werte, preise):
    pdf = _tabelle(tmp_path / "stehlgut.pdf", zeilen)
    funde, angehakt = _pdf_funde(pdf)
    for wert in werte:
        assert wert in angehakt, (wert, _paare(funde))
    for preis in preise:
        assert not any(preis in t for t in angehakt), (preis, _paare(funde))
    gemeldet = _pdf_gemeldet(pdf)
    for wert in werte:
        assert _norm(wert) in gemeldet, (wert, gemeldet)


def test_b48_gegenprobe_kopf_ohne_tabelle(tmp_path):
    """Gegenprobe: eine Zeile aus kurzen Wörtern mit „Seriennummer“, darunter Fließtext, ist kein Tabellenkopf."""
    pdf = _tabelle(tmp_path / "brief.pdf", ["Gerät\t\tZustand\t\tSeriennummer",
                                            "Das Gerät wurde am 12.03.2025 bei einem Einbruch entwendet.",
                                            "Die Rechnung über 1.299,00 EUR liegt bei."])
    _, angehakt = _pdf_funde(pdf)
    assert not any("1.299" in t or "12.03.2025" in t for t in angehakt), angehakt


def test_b48_selbstkontrolle_hinter_betragszelle():
    """Hinter einer Betragszelle steht eine eigene Zelle: die Währung davor gilt nicht über den Spaltentrenner."""
    zeile = "Objektiv Nikkor 18-140 mm\t\t449,00 EUR\t\t62231874"
    assert _gemeldet(zeile, "62231874"), [(v.text, v.grund) for v in pruefe_text(zeile)]


# ======================================================================
# Befund 51: Aktenzeichen ohne Etikett in gerichtlicher Form
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Das Verfahren 3 C 456/24 vor dem AG Ebersberg wurde durch Vergleich beendet.", "3 C 456/24"),
    ("Die Staatsanwaltschaft Traunstein hat das Verfahren 210 Js 345/24 eingestellt.", "210 Js 345/24"),
    ("Im Rechtsstreit 14 S 2211/24 hat das Landgericht die Berufung zurückgewiesen.", "14 S 2211/24"),
    ("Das Amtsgericht hat in der Sache 12 C 98/25 einen Termin bestimmt.", "12 C 98/25"),
])
def test_b51_aktenzeichen_ohne_etikett(zeile, wert):
    text = f"Kostenrechnung zur Rechtsschutzsache\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("text, frei", [
    ("Nach § 3 Abs. 2 VVG gilt Folgendes.", "3"),
    ("Tarifstufe 300/150 in der Krankentagegeldversicherung", "300/150"),
    ("Die Wohnung liegt im 3 OG, Zimmer 12/2.", "12/2"),
    ("Spielstand 3 C 4/5 im Turnier", "4/5"),
])
def test_b51_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befunde 52, 74: abgekürzte Stämme („Vorg.-Nr.“) und „<Kürzel>-Nummer“, „Nummer der …“
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Vorg.-Nr. 123/25", "123/25"),
    ("Ser.-Nr. des Rahmens: WTU 4471", "WTU 4471"),
    ("Mdt.-Nr. 1024", "1024"),
    ("Rahmen-Nummer: WTU 4471", "WTU 4471"),
    ("Vorg.-Nr.: 0815/25", "0815/25"),
    ("Mdt.-Nr.: 10245", "10245"),
    ("Rahmen-Nummer: WBK 556677", "WBK 556677"),
    ("Akku-Nummer: 1KX 4471", "1KX 4471"),
    # Befund 74
    ("BG-Nummer: 96202BG0012345", "96202BG0012345"),
    ("Nummer der Bedarfsgemeinschaft bitte stets angeben: 96202//0012345", "96202//0012345"),
    ("AZR-Nummer: 123456789012", "123456789012"),
    ("Nummer des Nationalpasses: U12345678", "U12345678"),
    ("BG-Nummer 96202BG0067890", "96202BG0067890"),
    ("AZR-Nummer 987650432198", "987650432198"),
    ("LV-Nummer: 47110815", "47110815"),
    ("Bedarfsgemeinschafts-Nummer: 96202BG0055501", "96202BG0055501"),
    ("BU-Nummer 0815-4711-22", "0815-4711-22"),
])
def test_b52_b74_nummer_etiketten(zeile, wert):
    text = f"Eingangsbestätigung\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


def test_b74_fuehrende_null_hinter_etikett_ist_kennung():
    """Eine führende 0 hinter einem Kennungs-Etikett ist keine Telefonnummer."""
    assert _kategorie("BU-Nummer 0815-4711-22", "0815-4711-22") == {"vertrag"}


@pytest.mark.parametrize("text, frei", [
    ("Art.-Nr. 4711", "4711"),
    ("Best.-Nr.: 0815-22", "0815-22"),
    ("Pos.-Nr. 12", "12"),
    ("Seiten-Nummer 3 von 4", "3"),
    ("Kapitel-Nummer: 4.2", "4.2"),
    ("Haus-Nummer: 12", "12"),
    ("Modell-Nummer: A2890", "A2890"),
    ("Artikel-Nummer: 123456", "123456"),
    ("Service-Nummer: 0800 1234567", "0800 1234567"),
    ("Hotline-Nummer 0180 5 123456", "0180 5 123456"),
    ("Nummer des Paragraphen: 34", "34"),
    ("Nummer der Seite: 12", "12"),
    ("Tarif-Nummer: KH 2024", "KH 2024"),
])
def test_b52_b74_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 53: Tierkennzeichnung
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Tätowierung (li. Ohr): ZB 2187", "ZB 2187"),
    ("Tätowiernummer Zuchtbuch: VDH 3366", "VDH 3366"),
    ("Hundesteuermarke Nr. 0386", "0386"),
    ("Kennnummer: 0815", "0815"),
    ("Tätowierung: DT 4417", "DT 4417"),
    ("Steuermarke: 2291", "2291"),
    ("Hundemarke Nr. 1187", "1187"),
    ("Täto-Nr.: VDH 7735", "VDH 7735"),
    ("Zuchtbuchnummer: VDH 12345", "VDH 12345"),
])
def test_b53_tierkennzeichnung(zeile, wert):
    text = f"Antrag Hundekrankenversicherung\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


def test_b53_etikettwoerter_sind_kein_name():
    """„Tätowiernummer Zuchtbuch:“ ist ein Etikett mit Ergänzung, keine Person (vorher [PERSON A])."""
    text = "Antrag Hundekrankenversicherung\nTätowiernummer Zuchtbuch: VDH 3366"
    assert not any(f["kategorie"] == "namen" for f in _funde(text)), _paare(_funde(text))


# ======================================================================
# Befund 55: Einzelkaufmann (e.K., Inhaber: Person) – HRA und USt-IdNr. sind personenbezogen
# ======================================================================
@pytest.mark.parametrize("zeilen, werte", [
    (["Antrag Betriebshaftpflicht", "Inhaber: Florian Sedlmayr", "Handelsregister: Amtsgericht München HRA 112233",
      "USt-IdNr.: DE287654321"], ["HRA 112233", "DE287654321"]),
    (["Antrag Inhaltsversicherung für Handwerksbetriebe", "Firma: Schreinerei Thomas Wendlinger e.K.",
      "Registergericht: AG Traunstein, HRA 20455", "Umsatzsteuer-ID: DE 312 445 678"], ["HRA 20455", "DE 312 445 678"]),
    # "e. K." mit Leerzeichen, ohne HRA und ohne "Inh…" im Text: dieselbe Vorprüfung in Erkennung und Selbstkontrolle
    (["Antrag Betriebshaftpflicht", "Firma: Schreinerei Thomas Wendlinger e. K.", "Umsatzsteuer-ID: DE 312 445 678"],
     ["DE 312 445 678"]),
])
def test_b55_einzelkaufmann(zeilen, werte):
    text = "\n".join(zeilen)
    funde = _funde(text)
    for wert in werte:
        assert _abgedeckt(text, wert, funde), (wert, _paare(funde))
        assert _gemeldet(text, wert), [(v.text, v.grund) for v in pruefe_text(text)]


@pytest.mark.parametrize("zeilen, frei", [
    (["Antrag Betriebshaftpflicht", "Firma: Sedlmayr Holzbau GmbH", "Handelsregister: Amtsgericht München HRB 112233",
      "USt-IdNr.: DE287654321"], ["HRB 112233", "DE287654321"]),
    (["Rechnung Nr. 2025-117", "Malerbetrieb Huber GmbH · Gartenweg 3 · 86199 Augsburg",
      "Amtsgericht Augsburg HRB 4711 · USt-IdNr. DE312845670"], ["HRB 4711", "DE312845670"]),
])
def test_b55_gegenprobe_juristische_person(zeilen, frei):
    text = "\n".join(zeilen)
    funde = _funde(text)
    for wert in frei:
        assert _nicht_geschwaerzt(text, wert, funde), (wert, _paare(funde))
    assert not any("Einzelkaufmann" in v.grund for v in pruefe_text(text))


# ======================================================================
# Befund 56: Service-Tag, S/N, MAC-Adresse
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Service-Tag: 7XK2Q3F", "7XK2Q3F"),
    ("MAC-Adresse: 3C:22:FB:9A:1B:7E", "3C:22:FB:9A:1B:7E"),
    ("Service Tag (S/N): 4HQ9ZM2", "4HQ9ZM2"),
    ("MAC: 3C-22-FB-9A-1B-7E", "3C-22-FB-9A-1B-7E"),
    ("S/N: C02XK1Y2JG5H", "C02XK1Y2JG5H"),
    ("WLAN-MAC 00:1A:2B:3C:4D:5E", "00:1A:2B:3C:4D:5E"),
])
def test_b56_servicetag_mac(zeile, wert):
    text = f"Diebstahlanzeige - Angaben zum Gerät\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


def test_b56_mac_ohne_etikett_im_text():
    text = "Das Gerät mit der Adresse 3C:22:FB:9A:1B:7E meldete sich zuletzt am 12.03.2025."
    assert _abgedeckt(text, "3C:22:FB:9A:1B:7E"), _paare(_funde(text))


@pytest.mark.parametrize("text, frei", [
    ("Uhrzeit: 12:30:45", "12:30:45"),
    ("Verhältnis 16:9, Auflösung 1920:1080", "16:9"),
])
def test_b56_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 59: IMEI mit Laufnummer, ICCID, EID; Befund 98: IMEI ist keine Kreditkarte
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("IMEI 1: 35 693803 564380 9", "35 693803 564380 9"),
    ("IMEI 2: 35 693803 564381 7", "35 693803 564381 7"),
    ("SIM-Karte (ICCID): 8949 0200 0012 3456 7890", "8949 0200 0012 3456 7890"),
    ("eSIM-EID: 89049032004008882600012345678901", "89049032004008882600012345678901"),
    ("IMEI (SIM 1): 352099001761481", "352099001761481"),
    ("IMEI1: 359876543210987", "359876543210987"),
    ("ICCID: 89490200001234567891", "89490200001234567891"),
    ("EID: 89049032004008882600012345678902", "89049032004008882600012345678902"),
    ("IMEI (Steckplatz 2): 35 209900 176148 1", "35 209900 176148 1"),
])
def test_b59_imei_laufnummer_iccid_eid(zeile, wert):
    text = f"Schadenmeldung Elektronikversicherung - Diebstahl\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


def test_b59_laufnummer_selbst_bleibt_stehen():
    text = "IMEI 1: 35 693803 564380 9"
    funde = _funde(text)
    assert _nicht_geschwaerzt(text, "IMEI 1", funde) or "1:" in text, _paare(funde)
    assert not any(st["text"].startswith("1") for f in funde for st in f["stellen"]), _paare(funde)


@pytest.mark.parametrize("zeile, wert", [
    ("Gerät: Smartphone, IMEI: 356938035643809", "356938035643809"),
    ("IMEI (SIM 1): 352099001761481", "352099001761481"),
])
def test_b98_imei_ist_kennung_nicht_kreditkarte(zeile, wert):
    assert _kategorie(zeile, wert) == {"vertrag"}, _paare(_funde(zeile))


def test_b59_gegenprobe_telefon_mit_laufnummer():
    """Das Überspringen der Laufnummer gilt nur für Kennungs-Etiketten, nicht für Telefon 1:."""
    text = "Telefon 1: 0821 4711\nTelefon 2: 0821 4712"
    funde = _funde(text)
    assert {"0821 4711", "0821 4712"} <= {st["text"] for f in funde for st in f["stellen"]
                                         if f["kategorie"] == "telefon"}, _paare(funde)


# ======================================================================
# Befund 72: Konto ohne „Nr.“, Girokonto, Sparkonto, Kontoverbindung
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Alternativ: Sparkonto 3182736455, Tagesgeldkonto 5928374610", "3182736455"),
    ("Alternativ: Sparkonto 3182736455, Tagesgeldkonto 5928374610", "5928374610"),
    ("Gepfändet wird das Guthaben auf dem Konto 1234567890 (Pfändungsschutzkonto).", "1234567890"),
    ("Kontoverbindung: 7362514098, BLZ 720 500 00", "7362514098"),
    ("Bankverbindung: Konto 2468013579 bei der Stadtsparkasse Augsburg", "2468013579"),
    ("Der Beitrag wird vom Girokonto 4455667788 (BLZ 720 500 00) abgebucht.", "4455667788"),
    ("Erstattung bitte auf Konto 9182736450 bei der Raiffeisenbank Augsburg.", "9182736450"),
    ("Festgeldkonto: 0012 345 678", "0012 345 678"),
])
def test_b72_konto(zeile, wert):
    text = f"Pfändungs- und Überweisungsbeschluss\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _kategorie(text, wert) <= {"vertrag", "iban"}, _paare(_funde(text))


@pytest.mark.parametrize("text, frei", [
    ("Konto 1.250,00 EUR im Soll", "1.250,00"),
    ("Kontoauszug 2024, Blatt 3", "2024"),
    ("Konto 2024 abgeschlossen", "2024"),
    ("Kontoführungsgebühr: 4,90 EUR monatlich", "4,90"),
])
def test_b72_gegenproben(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 73: Steuer-ID – mehrere Werte hinter einem Etikett, gruppiert 2-3-3-3 mit gültiger Prüfziffer
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Identifikationsnummer: Ehemann 10 163 985 243, Ehefrau 30 268 175 922", "10 163 985 243"),
    ("Identifikationsnummer: Ehemann 10 163 985 243, Ehefrau 30 268 175 922", "30 268 175 922"),
    ("Steuer-ID Kind 1: 14 208 593 466", "14 208 593 466"),
    ("Identifikationsnummern: 47 036 892 451 (Ehemann), 65 129 830 677 (Ehefrau)", "47 036 892 451"),
    ("Identifikationsnummern: 47 036 892 451 (Ehemann), 65 129 830 677 (Ehefrau)", "65 129 830 677"),
    ("IdNr. des 2. Kindes: 27 418 360 251", "27 418 360 251"),
    # ohne Etikett, gruppiert mit gültiger Prüfziffer
    ("Bitte tragen Sie 30 268 175 922 in das Formular ein.", "30 268 175 922"),
])
def test_b73_steuer_id(zeile, wert):
    text = f"Antrag auf Kindergeld\n{zeile}"
    funde = _funde(text)
    assert _abgedeckt(text, wert, funde), _paare(funde)
    assert _kategorie(text, wert) == {"steuerid"}, _paare(funde)


@pytest.mark.parametrize("text, frei", [
    ("Rufnummer: 01 234 567 890", "01 234 567 890"),
    ("Bitte tragen Sie 30 268 175 921 in das Formular ein.", "30 268 175 921"),
])
def test_b73_gegenproben(text, frei):
    funde = _funde(text)
    assert not any(f["kategorie"] == "steuerid" for f in funde), _paare(funde)


# ======================================================================
# Befund 76: Postnummer (Packstation); Befund 78: „#“ als Trenner; Befund 80: eTIN; Befund 96: UELN
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Postnummer 76543210 (Packstation 117)", "76543210"),
    ("Packstation 123 · Postnummer 12345678 · 86150 Augsburg", "12345678"),
    ("Ihre Postnummer: 58403917", "58403917"),
    ("Ihre Anfrage wurde unter der Ticketnummer #A-4711 erfasst.", "A-4711"),
    ("[Ticket#2025031110000123] Rückfrage zu Ihrem Schaden", "2025031110000123"),
    ("Ihr Ticket #KX-2291 wurde geschlossen.", "KX-2291"),
    ("eTIN: ZWCKQRN85C03", "ZWCKQRN85C03"),
    ("eTIN: RMPLHLDG57K14T", "RMPLHLDG57K14T"),
    ("Equidenpass / UELN: 276009090123456", "276009090123456"),
    ("UELN 276 009 09 0123457", "276 009 09 0123457"),
])
def test_b76_b78_b80_b96_etiketten(zeile, wert):
    text = f"Schreiben\n{zeile}"
    assert _abgedeckt(text, wert), _paare(_funde(text))
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("text, frei", [
    ("Postfach: 12 34 56", None),
    ("#Versicherung #Hausrat", "#Hausrat"),
    ("Ticket #3 ist erledigt", "3"),
])
def test_b76_b78_gegenproben(text, frei):
    if frei is not None:
        assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 33: FIN auf Scans OCR-tolerant (O statt 0, I statt 1)
# ======================================================================
@pytest.mark.parametrize("kopf", ["Zulassungsbescheinigung Teil I (Kopie)", "Anlage 3 zur Schadenanzeige"])
@pytest.mark.parametrize("zeile, wert", [
    ("E  WFOEXXGCDEKA12345", "WFOEXXGCDEKA12345"),
    ("FIN: W0LOAHL3555012345", "W0LOAHL3555012345"),
    ("E WOLOAHL35S5O12345", "WOLOAHL35S5O12345"),
    ("Fahrgestell WVWZZZ1KZOW123456 laut Kaufvertrag", "WVWZZZ1KZOW123456"),
])
def test_b33_fin_auf_scan(kopf, zeile, wert):
    """Die OCR liest die 0 der Herstellerkennung als O (WF0 → WFO, W0L → WOL): die FIN gilt trotzdem – auch ohne
    Etikett der Zulassungsbescheinigung in der Zeile darüber."""
    funde = analyse._analysiere_dokument(_ocr_dok([kopf, zeile]), ALLE, [], [])
    assert any(wert in st["text"] for f in funde for st in f["stellen"] if st.get("an", True)), _paare(funde)


def test_b33_gegenprobe_wort_auf_scan():
    funde = analyse._analysiere_dokument(_ocr_dok(["Bitte ANSCHLUSSVERSICHERUNGEN beachten"]), ALLE, [], [])
    assert not any(f["kategorie"] == "fin" for f in funde), _paare(funde)


# ======================================================================
# Befund 89: Pass-/Ausweisnummer der Sichtzone über die MRZ (OCR verliest 4 als A)
# ======================================================================
@pytest.mark.parametrize("mrz_nummer", ["C4KR7NT2X", "CAKR7NT2X"])
def test_b89_passnummer_sichtzone_ueber_mrz(mrz_nummer):
    """Die OCR verliest 4 als A in der Sichtzone – und so (Lauf k7_pass_stapel, Scan 200 dpi) auch in der MRZ: die
    Prüfziffer der Nummer stimmt dann nicht, die Zone ist über Kopf und Geburtsdatum trotzdem bestätigt, und die
    gelesene Nummer sucht die gedruckte."""
    zeilen = ["REISEPASS / PASSPORT / PASSEPORT", "Pass-Nr. / Passport No. / Passeport No", "CAKR7NT2X",
              "Name / Surname / Nom", "MUSTERMANN", "Vornamen / Given names / Prénoms", "ERIKA",
              "P<D<<MUSTERMANN<<ERIKA<<<<<<<<<<<<<<<<<<<<<<<",
              f"{mrz_nummer}1D<<9011300M3302141<<<<<<<<<<<<<<04"]
    funde = analyse._analysiere_dokument(_ocr_dok(zeilen), ALLE, [], [])
    angehakt = {st["text"] for f in funde for st in f["stellen"] if st.get("an", True)}
    assert "CAKR7NT2X" in angehakt, _paare(funde)


def test_b89_gegenprobe_ohne_bestaetigte_zone():
    """Ohne Dokumentkopf und ohne stimmendes Geburtsdatum sucht eine verlesene Nummer nichts in der Sichtzone."""
    zeilen = ["Bestellliste", "CAKR7NT2X", "Q<<KRAUSE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
              "CAKR7NT2X1D<<9011309M3302141<<<<<<<<<<<<<<04"]
    funde = analyse._analysiere_dokument(_ocr_dok(zeilen), ALLE, [], [])
    assert not any(st["text"] == "CAKR7NT2X" and "sichtzone" in " ".join(f["quellen"]) for f in funde
                   for st in f["stellen"]), _paare(funde)


# ======================================================================
# Gegenprobe aus der Korpus-Messung (s7, Maklervollmacht als Scan): die Nummer einer Vorschrift ist kein Wert hinter
# dem Etikett – auch wenn die Texterkennung das Paragrafenzeichen verliest und der eigentliche Wert fehlt bzw. in der
# Ausgabe schon geschwärzt ist ("Registrierungsnummer: ███ 8 34d Abs. 1 GewO")
# ======================================================================
@pytest.mark.parametrize("text, frei", [
    ("Registrierungsnummer: 8 34d Abs. 1 GewO", "8 34d"),
    ("Registrierungsnummer:   8 34d   Abs. 1 GewO", "8 34d"),
    ("Registrierungsnummer: S 34d GewO", "S 34d"),
    ("Registrierungsnummer: § 34d Abs. 1 GewO", "34d"),
    ("Vermittlerregisternummer: 8 34f Abs. 1 GewO", "8 34f"),
])
def test_vorschrift_ist_kein_wert_hinter_etikett(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))
    assert not _gemeldet(text, frei), [(v.text, v.grund) for v in pruefe_text(text)]


@pytest.mark.parametrize("zeile, wert", [
    ("IHK-Registrierungsnummer: D-3H4C-CFJ88-08 § 34d Abs. 1 GewO", "D-3H4C-CFJ88-08"),
    ("Registrierungsnummer D-Y3TV-NW64X-52 (§ 34d Abs. 1 GewO)", "D-Y3TV-NW64X-52"),
    ("Erlaubnis nach § 34d Abs. 1 GewO, Registrierungsnummer: D-W-123-ABCD-45", "D-W-123-ABCD-45"),
])
def test_vorschrift_daneben_wert_bleibt_kennung(zeile, wert):
    assert _abgedeckt(zeile, wert), _paare(_funde(zeile))
    assert _nicht_geschwaerzt(zeile, "34d")
    assert _gemeldet(zeile, wert)


# ======================================================================
# Gegenprobe aus der Korpus-Messung (s3x, SEPA-Mandat als Scan): hinter einem BIC-Etikett gilt nur die Form eines BIC –
# Ziffern eines Kammfelds darunter ("Kreditinstitut (Name und BIC)" ⏎ "67 1 …") sind kein Wert des Etiketts
# ======================================================================
@pytest.mark.parametrize("text, frei", [
    ("Kreditinstitut (Name und BIC)\n67 1\t\t55\t\tm\t\t15 a", "67 1"),
    ("Kreditinstitut (Name und BIC) der Hausbank: 4711 0815", "4711 0815"),
])
def test_bic_etikett_liest_keine_ziffern(text, frei):
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))
    assert not any("BIC" in v.grund or "SWIFT" in v.grund for v in pruefe_text(text)), \
        [(v.text, v.grund) for v in pruefe_text(text)]


@pytest.mark.parametrize("zeile, wert", [
    ("BIC der Hausbank: GENODEF1S01", "GENODEF1S01"),
    ("SWIFT-Code der Bank: DEUTDEFF500", "DEUTDEFF500"),
])
def test_bic_hinter_etikett_bleibt_bic(zeile, wert):
    assert _abgedeckt(zeile, wert), _paare(_funde(zeile))
    assert _kategorie(zeile, wert) == {"bic"}


# ======================================================================
# Gegenprobe aus der Korpus-Messung (s9x, Fax): ohne Ankündigung beginnt der Wert hinter einer Ergänzung mit einer
# Ziffer – ein Wort davor gehört noch zur Ergänzung ("Finanzamt Leipzig II", von der Texterkennung als "IF" gelesen)
# ======================================================================
@pytest.mark.parametrize("text, wert, frei", [
    ("Steuernummer beim Finanzamt Leipzig IF 00934072100.", "00934072100", "Leipzig IF"),
    ("Steuernummer beim Finanzamt München II 14381234567", "14381234567", "München II"),
])
def test_ergaenzung_wert_beginnt_mit_ziffer(text, wert, frei):
    funde = _funde(text)
    assert _abgedeckt(text, wert, funde), _paare(funde)
    assert _nicht_geschwaerzt(text, frei, funde), _paare(funde)
