"""Tests für die Muster-Erkennung (anonymisierer/muster.py)."""

import time

import pytest

from anonymisierer import muster as mu

SCHLUESSEL = [k for k, *_ in mu.KATEGORIEN]
STANDARD = {k for k, _, _, _, an in mu.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Kategorienliste (M-36, M-39, M-48)
# ----------------------------------------------------------------------
def test_kategorien_enthalten_pflichteintraege():
    assert "kindergeld" in SCHLUESSEL                       # M-36
    assert "kfz" in STANDARD                                # M-39
    for neu in ("steuernr", "kvnr", "fin", "ausweis", "mandat", "bic", "kreditkarte"):
        assert neu in SCHLUESSEL and neu in STANDARD        # M-48
    assert "datum" not in STANDARD
    assert len(SCHLUESSEL) == len(set(SCHLUESSEL))
    for schluessel, anzeige, platzhalter, funktion, an in mu.KATEGORIEN:
        assert anzeige
        if schluessel == "namen":
            assert funktion is None and platzhalter is None
        else:
            assert callable(funktion) and platzhalter.startswith("[") and platzhalter.endswith("]")
    assert set(mu.KATEGORIE_PRIORITAET) == set(SCHLUESSEL) - {"namen"}


def test_kindergeldnummer_in_kategorien_aktiv():
    funktion = dict((k, f) for k, _, _, f, _ in mu.KATEGORIEN)["kindergeld"]
    assert funktion("Kindergeld-Nr. 009FK407160") == ["009FK407160"]
    assert funktion("Kindergeldnummer: 009 FK 407160") == ["009 FK 407160"]


# ----------------------------------------------------------------------
# IBAN (M-49, M-65)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("IBAN AT61 1904 3002 3457 3201\nBIC: RZOOAT2L", ["AT61 1904 3002 3457 3201"]),
    ("AT61 1904 3002 3457 3201 RZOOAT2L", ["AT61 1904 3002 3457 3201"]),
    ("AT61 1904 3002 3457 3201\n2024", ["AT61 1904 3002 3457 3201"]),
    ("IBAN: BE68 5390 0754 7034\nBIC: GEBABEBB", ["BE68 5390 0754 7034"]),
    ("ES91 2100 0418 4502 0005 1332 EUR", ["ES91 2100 0418 4502 0005 1332"]),
    ("de89 3704 0044 0532 0130 00", ["de89 3704 0044 0532 0130 00"]),
    ("Konto: DE89 3704 0044\n0532 0130 00", ["DE89 3704 0044\n0532 0130 00"]),
    ("DE89370400440532013000 BIC COBADEFFXXX", ["DE89370400440532013000"]),
    ("IBAN: DE89 37O4 0044 0532 0130 00", ["DE89 37O4 0044 0532 0130 00"]),      # OCR: O statt 0
    ("Siehe ab12 3456 7890 1234 5678 90", []),
    ("DE89 3704 0044 0532 0130 01", []),                                          # falsche Prüfziffer
])
def test_iban(text, erwartet):
    assert mu.finde_iban(text) == erwartet


def test_iban_zwei_ibans_hintereinander():
    text = "IBAN AT61 1904 3002 3457 3201\nIBAN CH93 0076 2011 6238 5295 7"
    assert mu.finde_iban(text) == ["AT61 1904 3002 3457 3201", "CH93 0076 2011 6238 5295 7"]
    assert mu.IBAN_LAENGEN["DE"] == 22 and mu.IBAN_LAENGEN["AT"] == 20 and mu.IBAN_LAENGEN["CH"] == 21


# ----------------------------------------------------------------------
# E-Mail
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("max.mustermann(at)example.de", ["max.mustermann(at)example.de"]),
    ("E-Mail:max@web.de.", ["max@web.de"]),
    ("info@müller-versicherungen.de", ["info@müller-versicherungen.de"]),
    ("m_mustermann+versicherung@gmail.com", ["m_mustermann+versicherung@gmail.com"]),
    ("Max.Mustermann@Example.DE   Mobil", ["Max.Mustermann@Example.DE"]),
])
def test_email(text, erwartet):
    assert mu.finde_email(text) == erwartet


# ----------------------------------------------------------------------
# Telefon (M-14, M-38, M-65)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("Tel.: 0911 / 123 45 67", "0911 / 123 45 67"),
    ("(0911) 123456", "(0911) 123456"),
    ("+49 (0) 171 2345678", "+49 (0) 171 2345678"),
    ("0 89 / 12 34 56 78", "0 89 / 12 34 56 78"),
    ("0171 – 2345678", "0171 – 2345678"),
    ("Tel.0911 123456", "0911 123456"),
    ("0911-123456", "0911-123456"),
    ("0171/2345678", "0171/2345678"),
    ("+49 171 2345678", "+49 171 2345678"),
    ("030 865-27781", "030 865-27781"),
    ("0911 1234567-0", "0911 1234567-0"),
    ("+49-911-1234567", "+49-911-1234567"),
    ("0049 911 1234567", "0049 911 1234567"),
    ("+49 911 12 34 56", "+49 911 12 34 56"),
    ("Telefon 09 11 / 12 34 56", "09 11 / 12 34 56"),
    ("Fax: 0911 123457", "0911 123457"),
    ("Mobil 01512345678", "01512345678"),
    ("Tel. O171 2345678", "O171 2345678"),                     # OCR: O statt 0
])
def test_telefon_positiv(text, erwartet):
    assert mu.finde_telefon(text) == [erwartet]


@pytest.mark.parametrize("text", [
    "geb. 01.02.1980 in Nürnberg", "Beitrag 0,50 EUR monatlich, 12 Monate", "Seite 1 von 12",
    "Vertragsbeginn 01.01.2020 Ablauf 31.12.2045", "Rate 2 x 450,00", "90402 Nürnberg", "01067 Dresden",
    "Kontonummer 1234567890 (BLZ 70150000)", "Versicherungssumme 100 000 EUR",
])
def test_telefon_negativ(text):
    assert mu.finde_telefon(text) == []


def test_telefon_nicht_ueber_zeilenumbruch():
    assert mu.finde_telefon("0911 123456\n45,90 EUR") == ["0911 123456"]              # M-38
    assert mu.finde_telefon("Tel: 0911 123456\nFax: 0911 123457") == ["0911 123456", "0911 123457"]


# ----------------------------------------------------------------------
# Geburtsdatum (M-12)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("Geburtsdatum des Versicherungsnehmers: 15.03.1979", "15.03.1979"),
    ("geb. am 02.09.1983", "02.09.1983"),
    ("Herr Max Mustermann, * 02.09.1983, wohnhaft", "02.09.1983"),
    ("geboren am 2. September 1983", "2. September 1983"),
    ("Geburtsdatum: 1983-09-02", "1983-09-02"),
    ("GEBURTSDATUM 02/09/1983", "02/09/1983"),
    ("Geb.-Dat. 2.9.83", "2.9.83"),
    ("Geburtsdatum der versicherten Person: 02.09.1983", "02.09.1983"),
    ("Geburtsdatum\n02.09.1983", "02.09.1983"),
    ("geb. Schulz, 14.03.1979", "14.03.1979"),
    ("Mitversichert: Lea Schneider (Kind), geb. 21.11.2015", "21.11.2015"),
    ("Unsere Tochter Mia (geb. 04.04.2016) wurde", "04.04.2016"),
    ("Geburtsdatum Geburtsort Staatsangehörigkeit\n02.09.1983 Nürnberg deutsch", "02.09.1983"),
])
def test_geburtsdatum_positiv(text, erwartet):
    assert mu.finde_geburtsdaten(text) == [erwartet]


def test_geburtsdatum_tabellenlayouts():
    tabelle = ("Versicherte Person          Geburtsdatum          Versicherungsbeginn\n"
               "Max Mustermann              02.09.1983            01.01.2020\n")
    assert mu.finde_geburtsdaten(tabelle) == ["02.09.1983"]            # Spaltenzuordnung, nicht der Beginn
    kopf = "Geburtsdatum           Geschlecht           Familienstand\n02.09.1983             männlich\n"
    assert mu.finde_geburtsdaten(kopf) == ["02.09.1983"]
    zellen = "Versicherte Person\nGeburtsdatum\nVersicherungsbeginn\nMax Mustermann\n02.09.1983\n01.01.2020\n"
    assert mu.finde_geburtsdaten(zellen) == ["02.09.1983"]
    mehrere = ("Name                  Vorname      Geburtsdatum   Rolle\n"
               "Mustermann            Max          02.09.1983     VN\n"
               "Mustermann            Erika        15.05.1985     Ehepartner\n"
               "Nguyen                Thi Lan      12.07.1990     Partnerin\n")
    assert mu.finde_geburtsdaten(mehrere) == ["02.09.1983", "15.05.1985", "12.07.1990"]


@pytest.mark.parametrize("text", [
    "Angebot vom 14.03.2025", "Gebäudeversicherung ab 01.01.2026", "Arbeitgeber seit 01.09.1983",
    "Ergebnis der Prüfung vom 02.06.2025", "Gebühr fällig am 01.07.2025", "freigegeben am 02.06.2025",
    "Geburtsdatum: ______  Vertragsbeginn: 01.01.2020", "Geburtstag-Rabatt gültig bis 31.12.2025",
    "geboren am 31.02.2030", "Angebot Nr. 5 * 14.03.2025", "Den Antrag haben Sie am 15.05.2025 abgegeben.",
    "Gebietsleiter seit 01.01.2020", "Geburtsdatum 02.09.1983, Vertragsbeginn 01.01.2020"[32:],
])
def test_geburtsdatum_negativ(text):
    assert mu.finde_geburtsdaten(text) == []


# ----------------------------------------------------------------------
# Straße + Hausnummer (M-13, M-65)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Berliner Straße 5", "Berliner Str. 5", "Von-der-Tann-Str. 3", "Carl-Zeiss-Straße 12a", "Unter den Linden 1",
    "Am Alten Bahnhof 3", "Am Bahnhof 3", "HAUPTSTRASSE 12A", "Schillerstr.12", "Hauptstraße 12a",
    "Frankfurter Allee 100", "Im Winkel 2", "An der Alten Mühle 4", "Münchener Str. 1a", "Bahnhofstraße 1-3",
    "Berliner Platz 1", "Marktplatz 1", "Kirchgasse 2", "Lindenallee 7", "Goethestraße 10-12", "Rosenweg 14 b",
    "Straße des 17. Juni 135", "Postfach 10 11 12", "Dr.-Ing.-Müller-Weg 3", "Lange Straße 7", "Fürther Str. 120",
])
def test_strasse_positiv(text):
    assert mu.finde_strasse(text) == [text]


def test_strasse_im_satz():
    assert mu.finde_strasse("Zeuge: Herr Piotr Wiśniewski, Im Winkel 2, 90403 Nürnberg") == ["Im Winkel 2"]
    assert mu.finde_strasse("Hauptstr. 12 a, 90402 Nürnberg") == ["Hauptstr. 12 a"]
    assert mu.finde_strasse("Herr Max Berg, Bergstraße 12") == ["Bergstraße 12"]


@pytest.mark.parametrize("text", [
    "Im Jahr 2024 wurde", "Am Montag 12 Uhr", "Im Januar 2025", "Beitrag 500 EUR", "Zum Beispiel 3 Jahre",
    "Rechnung 12 vom", "Tarif Komfort 3", "Im Schadenfall 3 Tage", "Versicherungssumme 100",
])
def test_strasse_negativ(text):
    assert mu.finde_strasse(text) == []


# ----------------------------------------------------------------------
# PLZ + Ort (M-13, M-38)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "61348 Bad Homburg v. d. Höhe", "90402 NÜRNBERG", "51429 Bergisch Gladbach", "66386 St. Ingbert",
    "60311 Frankfurt am Main", "A-1010 Wien", "CH-8001 Zürich", "D-90402 Nürnberg", "10115 Berlin-Mitte",
    "15230 Frankfurt (Oder)", "91413 Neustadt a. d. Aisch", "89231 Neu-Ulm",
])
def test_plz_ort_positiv(text):
    assert mu.finde_plz_ort(text) == [text]


def test_plz_ort_grenzen():
    assert mu.finde_plz_ort("90402 Nürnberg, Hauptstraße 12") == ["90402 Nürnberg"]
    assert mu.finde_plz_ort("80331 München. Mitversichert: Anna") == ["80331 München"]
    assert mu.finde_plz_ort("90402 Nürnberg Telefon 0911") == ["90402 Nürnberg"]
    assert mu.finde_plz_ort("90402 Nürnberg Sehr geehrte") == ["90402 Nürnberg"]
    assert mu.finde_plz_ort("90402 Nürnberg\nTelefon") == ["90402 Nürnberg"]
    # Formularlayout: genau ein Umbruch zwischen PLZ und Ort ist erlaubt
    assert mu.finde_plz_ort("PLZ/Ort\n90402\nNürnberg") == ["90402\nNürnberg"]


@pytest.mark.parametrize("text", [
    "Versicherungssumme 50000 Euro", "Fahrleistung 15000 Kilometer", "Deckung 10000 Euro je Schadenfall",
    "Vermittler-Nr. 55123\nStuttgart, 14.03.2025", "Betrag 12345 Euro", "Vertrag 12345 Beginn",
    "00123 Versicherungsnehmer", "Kunden-Nr. 12345\nSehr geehrter", "Mandatsreferenz: M-2024-55667 Antragsteller",
    "1010 Wien",                                                      # 4-stellig nur mit Länderkürzel
])
def test_plz_ort_negativ(text):
    assert mu.finde_plz_ort(text) == []


# ----------------------------------------------------------------------
# Vertrags-/Kunden-/Schein-Nummern (M-06)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("Versicherungsnummer 1234567890", "1234567890"),
    ("Versicherungsnummer: 7 345 678 901", "7 345 678 901"),
    ("Versicherungs-Nr. 123456789", "123456789"),
    ("Vers.-Nr. 123.456.789-0", "123.456.789-0"),
    ("VS-Nr. 9876543210", "9876543210"),
    ("Versicherungsscheinnummer 123456789", "123456789"),
    ("Schein-Nr.: LV-2024-887766", "LV-2024-887766"),
    ("Policen-Nr. 4711/0815/22", "4711/0815/22"),
    ("Vorgangsnummer VG-2024-001122", "VG-2024-001122"),
    ("Aktenzeichen 12 O 345/24", "12 O 345/24"),
    ("Az.: 12 AZ 345/24", "12 AZ 345/24"),
    ("Referenz: 99887766", "99887766"),
    ("Kd.-Nr. 4711-0815", "4711-0815"),
    ("Kundennummer 4711", "4711"),
    ("Kunden-Nr. 4711", "4711"),
    ("Versicherten-Nr. 987654321", "987654321"),
    ("Mitgliedsnummer 55667788", "55667788"),
    ("Depot-Nr. 1234567890", "1234567890"),
    ("Kontonummer 0123456789 BLZ 37040044", "0123456789"),
    ("Zulagenummer 86 123456 M 789 (Ehefrau)", "86 123456 M 789"),
    ("Versicherungsschein-\nNr. LV-2024-887766", "LV-2024-887766"),
    ("Vertragsnummer 1234567 gilt ab 01.01.2025", "1234567"),
    ("Antragsnummer A-2024-0001 vom 03.03.2024", "A-2024-0001"),
    ("Kundennummer 4711 Herr Max Mustermann Hauptstraße 12", "4711"),
    ("Versicherungsschein-Nr. 123456789 Vertragsbeginn 01.01.2020", "123456789"),
    ("Vertragsnummer: 123456 Sehr geehrter Herr Mustermann,", "123456"),
    ("Schein-Nr. LV 88 77 66 55).", "LV 88 77 66 55"),
    ("Meine Vertragsnummer lautet PHV 123 456 789.", "PHV 123 456 789"),
    ("Versicherungsschein-Nummer: BU 7788 9900 12", "BU 7788 9900 12"),
    ("Versicherungsschein-Nr. 4711-0815 IBAN DE89 3704 0044 0532 0130 00", "4711-0815"),
    ("VERSICHERUNGSNUMMER: 7 345 678 901", "7 345 678 901"),               # OCR-Großschreibung
])
def test_vertragsnummern_positiv(text, erwartet):
    assert mu.finde_vertragsnummern(text) == [erwartet]


def test_vertragsnummern_tabellen_und_umbrueche():
    kopf = ("Vertragsnummer          Beginn          Ablauf          Jahresbeitrag\n"
            "LV-2024-887766          01.01.2020      31.12.2045      1.200,00 EUR\n")
    assert mu.finde_vertragsnummern(kopf) == ["LV-2024-887766"]
    assert mu.finde_vertragsnummern("Vertragsnummer\nBeginn\nAblauf\nLV-2024-887766") == ["LV-2024-887766"]
    assert mu.finde_vertragsnummern("Versicherungsschein-Nr.:\nLV-2024-887766\nKundennummer:\n4711-0815") == [
        "LV-2024-887766", "4711-0815"]
    assert mu.finde_vertragsnummern("Kundennummer: K-100245678, Vertragsnummer: LV-2024-887766") == [
        "K-100245678", "LV-2024-887766"]


@pytest.mark.parametrize("text", ["Kundennummer: siehe oben", "Vertrag LV-1 für Max", "Kundennummer: 12",
                                  "Personalausweis-Nr. L01X00T47", "Vertragsnummer   Beginn   Ablauf"])
def test_vertragsnummern_negativ(text):
    assert mu.finde_vertragsnummern(text) == []


# ----------------------------------------------------------------------
# Weitere Kennnummern (M-48, M-65)
# ----------------------------------------------------------------------
def test_sv_nummer():
    assert mu.finde_sv_nummer("12 345678 A 123") == ["12 345678 A 123"]
    assert mu.finde_sv_nummer("12 345678 a 123") == ["12 345678 a 123"]
    assert mu.finde_sv_nummer("65170839J008 und 12345678A123") == ["65170839J008", "12345678A123"]


def test_steuer_id():
    assert mu.finde_steuer_id("Steuer-ID 86095742719") == ["86095742719"]
    assert mu.finde_steuer_id("IdNr. 86 095 742 719") == ["86 095 742 719"]
    assert mu.finde_steuer_id("Ihre steuerliche Identifikationsnummer lautet 86 095 742 719.") == ["86 095 742 719"]
    assert mu.finde_steuer_id("Steuer-ID 8609574271 9") == ["8609574271 9"]
    assert mu.finde_steuer_id("86095742719") == ["86095742719"]                 # freistehend, gültig
    assert mu.finde_steuer_id("Beitrag 10000000000 EUR") == []
    assert mu.finde_steuer_id("Rechnungsnummer 20240012345") == []
    assert mu._steuer_id_struktur("86095742719") and not mu._steuer_id_struktur("12345678901")


def test_steuernummer():
    assert mu.finde_steuernummer("Steuernummer 123/4567/8901") == ["123/4567/8901"]
    assert mu.finde_steuernummer("Steuer-Nr. 181/815/08155") == ["181/815/08155"]
    assert mu.finde_steuernummer("Steuernummer 013 815 08153") == ["013 815 08153"]
    assert mu.finde_steuernummer("Steuernummer 1181081508155") == ["1181081508155"]
    assert mu.finde_steuernummer("USt-IdNr. DE123456789") == ["DE123456789"]
    assert mu.finde_steuernummer("Aktenzeichen 12 AZ 345/24") == []


def test_kv_nummer():
    assert mu.finde_kv_nummer("Krankenversichertennummer A123456789") == ["A123456789"]
    assert mu.finde_kv_nummer("Versichertennummer: B987654321") == ["B987654321"]
    assert mu.finde_kv_nummer("DE123456789 WVWZZZ1KZAW123456") == []


def test_fin():
    assert mu.finde_fin("Fahrzeug-Ident-Nr. WVWZZZ1KZAW123456") == ["WVWZZZ1KZAW123456"]
    assert mu.finde_fin("12345678901234567") == []            # 17 Ziffern ohne Buchstaben: keine FIN
    assert mu.finde_fin("VERSICHERUNGSNEHM") == []            # 17 Buchstaben ohne Ziffer: keine FIN
    assert mu.finde_fin("WVWZZZ1KZAW12345I") == []            # I ist in FIN nicht erlaubt


def test_bic():
    assert mu.finde_bic("BIC: COBADEFFXXX") == ["COBADEFFXXX"]
    assert mu.finde_bic("IBAN AT61 1904 3002 3457 3201\nBIC: RZOOAT2L") == ["RZOOAT2L"]
    assert mu.finde_bic("IBAN DE89370400440532013000 BIC COBADEFFXXX") == ["COBADEFFXXX"]
    assert mu.finde_bic("DE89 3704 0044 0532 0130 00\nHAUPTSTR 12") == []
    assert mu.finde_bic("RECHNUNG NACHTRAG") == []             # ohne Etikett/IBAN keine Großbuchstaben-Wörter


def test_kreditkarte():
    assert mu.finde_kreditkarte("Kreditkarte: VISA 4532 0151 1283 0366, gültig bis 12/27") == ["4532 0151 1283 0366"]
    assert mu.finde_kreditkarte("4532015112830367") == []      # Luhn falsch
    assert mu.finde_kreditkarte("DE89 3704 0044 0532 0130 00") == []


def test_ausweisnummer_und_mandat():
    assert mu.finde_ausweisnummer("Personalausweis-Nr. L01X00T47, ausgestellt am") == ["L01X00T47"]
    assert mu.finde_ausweisnummer("Ausweisnummer: L01X00T47") == ["L01X00T47"]
    assert mu.finde_ausweisnummer("Reisepass Nr. C01X00T47") == ["C01X00T47"]
    assert mu.finde_ausweisnummer("Führerschein-Nr. J123456789") == ["J123456789"]
    assert mu.finde_ausweisnummer("Ausweis vorgelegt") == []
    assert mu.finde_mandatsreferenz("Mandatsreferenz M-2024-556677") == ["M-2024-556677"]
    assert mu.finde_mandatsreferenz("Mandats-Nr.: 123456789") == ["123456789"]
    assert mu.finde_mandatsreferenz("SEPA-Mandat Nr. ABC") == []


# ----------------------------------------------------------------------
# Kfz-Kennzeichen (M-39, M-65)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("Kennzeichen N-AB 1234", "N-AB 1234"), ("B-MW 1", "B-MW 1"), ("M-X 1E", "M-X 1E"), ("N AB 1234", "N AB 1234"),
    ("N-AB1234", "N-AB1234"), ("HD-XY 987", "HD-XY 987"), ("NM-XY 123", "NM-XY 123"), ("ER-PS 2024", "ER-PS 2024"),
    ("Kennzeichen: n-ab 1234", "n-ab 1234"), ("amtl. Kennzeichen M-AB 1234", "M-AB 1234"),
])
def test_kennzeichen_positiv(text, erwartet):
    assert mu.finde_kennzeichen(text) == [erwartet]


@pytest.mark.parametrize("text", [
    "AVB-BU 2019", "DIN EN 1234", "BMW X5", "ISO 9001", "AVB KH 2008", "SGB VI 2023", "VVG AB 2008", "DIN A 4",
    "VHV-KH 2020", "AKB 2015", "SF 12 auf SF 7", "VW T5", "HSN/TSN 0603 AZJ", "AGB SV 2020",
])
def test_kennzeichen_negativ(text):
    assert mu.finde_kennzeichen(text) == []


# ----------------------------------------------------------------------
# Laufzeit (M-69): keine quadratische Laufzeit bei langen Zeilen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("funktion", [mu.finde_email, mu.finde_strasse, mu.finde_plz_ort, mu.finde_telefon,
                                      mu.finde_vertragsnummern, mu.finde_geburtsdaten, mu.finde_iban,
                                      mu.finde_kennzeichen])
def test_laufzeit_lange_zeile(funktion):
    text = "Aa-" * 10_000                                      # 30.000 Zeichen ohne Leerzeichen
    start = time.perf_counter()
    funktion(text)
    assert time.perf_counter() - start < 1.0
    text = "Max Mustermann wohnt in der Hauptstraße 12, 90402 Nürnberg, Tel. 0911 123456. " * 2000
    start = time.perf_counter()
    funktion(text)
    assert time.perf_counter() - start < 2.0


# ======================================================================
# Phase 3: Stellen-Schnittstelle, Unicode (Vertrag 12.7), Gutachten EQ-04..EQ-20, Schutzstufen
# ======================================================================
TEXT_FUNKTIONEN = [mu.finde_iban, mu.finde_email, mu.finde_telefon, mu.finde_geburtsdaten, mu.finde_strasse,
                   mu.finde_plz_ort, mu.finde_vertragsnummern, mu.finde_sv_nummer, mu.finde_steuer_id,
                   mu.finde_steuernummer, mu.finde_kv_nummer, mu.finde_kindergeldnummer, mu.finde_kennzeichen,
                   mu.finde_fin, mu.finde_ausweisnummer, mu.finde_mandatsreferenz, mu.finde_bic, mu.finde_kreditkarte,
                   mu.finde_alle_daten]
BEISPIEL = ("Versicherungsnehmer: Max Mustermann, geb. am 02.09.1983, Hauptstraße 12a, 90402 Nürnberg\n"
            "Tel. 0911 / 123 45 67, max@example.de, IBAN DE89 3704 0044 0532 0130 00 BIC COBADEFFXXX\n"
            "Versicherungsschein-Nr. LV-2024-887766, SV-Nr. 12 345678 A 123, Steuer-ID 86095742719,\n"
            "Steuernummer 123/4567/8901, KV-Nr. A123456789, Kindergeld-Nr. 009FK407160, Kennzeichen N-AB 1234,\n"
            "FIN WVWZZZ1KZAW123456, Personalausweis-Nr. L01X00T47, Mandatsreferenz M-2024-556677,\n"
            "Kreditkarte 4532 0151 1283 0366")


@pytest.mark.parametrize("funktion", TEXT_FUNKTIONEN, ids=lambda f: f.__name__)
def test_stellen_schnittstelle_passt_zu_fundtexten(funktion):
    stellen_fn = getattr(mu, funktion.__name__ + "_stellen")
    stellen = stellen_fn(BEISPIEL)
    texte = [BEISPIEL[s:e] for s, e in stellen]
    assert texte, funktion.__name__
    assert set(texte) == set(funktion(BEISPIEL))
    for s, e in stellen:
        assert 0 <= s < e <= len(BEISPIEL) and BEISPIEL[s:e] == BEISPIEL[s:e].strip()


def test_normalisieren_schnellpfad_und_abbildung():
    assert mu.normalisieren("ganz normaler Text") == ("ganz normaler Text", None)
    roh = "Noémie Bonnet 51­633867 Tel‑0421"
    norm, abbildung = mu.normalisieren(roh)
    assert norm == "Noémie Bonnet 51-633867 Tel-0421" and len(abbildung) == len(norm)
    assert roh[abbildung[norm.index("51-6") + 2]] == "­"
    assert mu._normalisieren_einfach(roh)[0] == norm


# Vertrag 12.7: Windows-Schriften liefern NBSP, schmale Leerzeichen, sichtbare weiche Trennstriche und U+2011
@pytest.mark.parametrize("funktion, text, erwartet", [
    (mu.finde_telefon, "Telefon 0421 3498­936", "0421 3498­936"),
    (mu.finde_telefon, "Mobil 0171‑2345678", "0171‑2345678"),
    (mu.finde_telefon, "Tel. +49 911 1234567", "+49 911 1234567"),
    (mu.finde_email, "a.krause@schwarzwald­versicherung.de", "a.krause@schwarzwald­versicherung.de"),
    (mu.finde_iban, "IBAN DE89 3704 0044 0532 0130 00", "DE89 3704 0044 0532 0130 00"),
    (mu.finde_iban, "IBAN DE89 3704 0044 0532 0130 00", "DE89 3704 0044 0532 0130 00"),
    (mu.finde_vertragsnummern, "Kundennummer 51­633867", "51­633867"),
    (mu.finde_vertragsnummern, "Versicherungsschein-Nr. LV‑2024‑887766", "LV‑2024‑887766"),
    (mu.finde_kennzeichen, "Kennzeichen N‑AB 1234", "N‑AB 1234"),
    (mu.finde_plz_ort, "90402 Nürnberg", "90402 Nürnberg"),
    (mu.finde_strasse, "Hauptstraße 12a", "Hauptstraße 12a"),
    (mu.finde_geburtsdaten, "geb. am 02.09.1983", "02.09.1983"),
    (mu.finde_sv_nummer, "SV-Nr. 12 345678 A 123", "12 345678 A 123"),
    (mu.finde_mandatsreferenz, "Mandatsreferenz M‑2024‑556677", "M‑2024‑556677"),
    (mu.finde_telefon, "Telefon ０９１１ 123456", "０９１１ 123456"),
])
def test_unicode_sonderzeichen_windows(funktion, text, erwartet):
    assert funktion(text) == [erwartet]
    s, e = getattr(mu, funktion.__name__ + "_stellen")(text)[0]
    assert text[s:e] == erwartet


# ---------------------------------------------------------------------- Gutachten EQ-05..EQ-17
@pytest.mark.parametrize("text, erwartet", [
    ("Geboren am: 02.09.1983", ["02.09.1983"]),                   # EQ-05
    ("GEBOREN AM 02.09.1983", ["02.09.1983"]),
    ("GEB.-DATUM 02.09.1983", ["02.09.1983"]),
    ("Name Vorname Geb.-Datum Rolle\nMüller\nAnna\n1988-10-12 VN", ["1988-10-12"]),   # Geb.-Datum vor Geb.
    ("Herr Paul Weber, Jg. 1961, Fahrer", ["1961"]),             # Jahrgang
    ("geb. 1961 in Erfurt", ["1961"]),
])
def test_geburtsdatum_stichwoerter_phase3(text, erwartet):
    assert mu.finde_geburtsdaten(text) == erwartet


def test_jahrgang_nicht_bei_vertragsdaten():
    assert mu.finde_geburtsdaten("Beitragsjahr 2024, Jahrgang der Police unbekannt") == []
    assert mu.finde_geburtsdaten("geb. 01.02.2099") == []                   # Zukunft


@pytest.mark.parametrize("text, erwartet", [
    ("Gläubiger-ID: DE98ZZZ09999999999", []),                             # EQ-06/KQ-11
    ("Bei Fragen erreichen Sie uns unter 0800 123 4567.", []),            # EQ-07 Hotline
    ("Service 0180 5 123456 und 0900 1234567", []),
    ("Tel. +33 6 12 34 56 78", ["+33 6 12 34 56 78"]),                   # EQ-08
    ("Tel. +41 79 320 53 58, +43 1 3975369", ["+41 79 320 53 58", "+43 1 3975369"]),
    ("Geburtsdatum 01/10/2024 und 02/09/1983", []),                      # EQ-14
    ("Sie erreichen sie/ihn unter +49 (0)7141\n842332 oder per Mail.", ["+49 (0)7141\n842332"]),
    ("Für Rückfragen erreichen Sie uns unter 0385\n897335.", ["0385\n897335"]),
    ("Bei Fragen bin ich unter 01 74 / 423\n15 49 erreichbar.", ["01 74 / 423\n15 49"]),
    ("Meine Telefonnummer: +49\n(0)355 9825916. Bitte", ["+49\n(0)355 9825916"]),
])
def test_telefon_gutachten_und_zeilenumbruch(text, erwartet):
    assert mu.finde_telefon(text) == erwartet


def test_telefon_tabellenzellen_nicht_verbinden():
    assert mu.finde_telefon("PLZ\n01067\n90402\nOrt") == []                # zwei PLZ-Zellen sind keine Nummer
    assert mu.finde_telefon("0911 123456\n45,90 EUR") == ["0911 123456"]


@pytest.mark.parametrize("text, erwartet", [
    ("Versicherungsnummer  LV-2024-887766  Beginn 01.10.2024", ["LV-2024-887766"]),       # EQ-09 (a)
    ("Kunden-Nr.\tKD 4711-0815\tStand 2025", ["KD 4711-0815"]),
    ("Versicherungsschein-\nZeitraum\nBeginn\nNr. KH 0815 4471 2", ["KH 0815 4471 2"]),     # EQ-09 (b)
    ("Ihre Lebensversicherung Nr. LV-2011-009307 – Ablauf zum 19.12.2025", ["LV-2011-009307"]),
    ("Auszahlung aus Ihrem Vertrag 47.897.336.2 – fehlende Angaben", ["47.897.336.2"]),
    ("Registrierungsnummer D-T4E8-U6G1F-15 (§ 34d Abs. 1 GewO)", ["D-T4E8-U6G1F-15"]),
    ("Ihr Vertrag vom 01.01.2020 und der Vertrag 2024", []),
])
def test_vertragsnummern_phase3(text, erwartet):
    assert mu.finde_vertragsnummern(text) == erwartet


def test_vertragsnummern_lineare_laufzeit():                                # EQ-17 / PERF-07
    text = "Kunden-Nr.: 4711 " * 3000
    start = time.perf_counter()
    mu.finde_vertragsnummern(text)
    assert time.perf_counter() - start < 1.0
    text = ("IBAN DE89 3704 0044 0532 0130 00 BIC COBADEFFXXX " * 2000)
    start = time.perf_counter()
    assert mu.finde_bic(text) == ["COBADEFFXXX"]
    assert time.perf_counter() - start < 2.0


def test_strasse_fahrbahn_und_roemische_zahlen():                           # EQ-12, EQ-13
    assert mu.finde_strasse("Er befuhr die Bundesstraße 7 in Richtung Weimar") == []
    assert mu.finde_strasse("Anschrift: Bundesstraße 7, 99423 Weimar") == ["Bundesstraße 7"]
    assert mu.finde_kennzeichen("BGH, Urteil vom 11.11.2020 – IV ZR 123/19") == []


@pytest.mark.parametrize("text", [
    "Platz der Republik 99 a", "ZUM STEINBRUCH 66", "Alt-Moabit 61", "An den Eichen 140", "Auf der Höhe 32d",
    "Kleine Bergstraße 16", "Obere Hauptstr. 38d", "Untere Grabenstraße 54", "Hinter der Kirche 9 a",
    "Straße der Einheit 5",
])
def test_strasse_sonderformen(text):
    assert mu.finde_strasse(text) == [text]


def test_strasse_ocr_umbruch_in_praeposition():
    assert mu.finde_strasse("Hinter\nder Kirche 9 a") == ["Hinter\nder Kirche 9 a"]


def test_plz_ort_phase3():
    assert mu.finde_plz_ort("Amtsgericht Hamburg HRB 16963\nVorstand: Dr. Max Weber") == []
    assert mu.finde_plz_ort("Sitz: Köln · HRB 91206\nUSt-IdNr. DE123456789") == []
    assert mu.finde_plz_ort("92637 Weiden i.d.OPf.") == ["92637 Weiden i.d.OPf."]
    assert mu.finde_plz_ort("neu: Lindenallee 4\n0.....45879 Gelsenkirchen") == ["45879 Gelsenkirchen"]
    assert mu.finde_plz_ort("81675 München Bu") == ["81675 München"]                # OCR-Rest
    assert mu.finde_plz_ort("53474 Bad Neuenahr-Ahrweiler") == ["53474 Bad Neuenahr-Ahrweiler"]


def test_ust_idnr_firma_oder_person():                                       # EQ-16
    fuss = "Hanse Krankenversicherung a. G. · USt-IdNr. DE123456789 · Vorstand: J. Petersen"
    assert mu.finde_steuernummer(fuss) == []
    assert mu.finde_steuernummer("Zahnärztin Dr. Anna Berg\nUSt-IdNr. DE123456789") == ["DE123456789"]


# ---------------------------------------------------------------------- Prüfziffern: Sicherheit statt Ausschluss
def test_pruefziffer_ungueltig_bleibt_fund_mit_hinweis():
    st = mu.stellen("iban", "IBAN: DE89 3704 0044 0532 0130 01")
    assert len(st) == 1 and not st[0].streng and st[0].hinweis == mu.HINWEIS_PRUEFZIFFER and st[0].sicherheit < 1
    assert mu.finde_iban("IBAN: DE89 3704 0044 0532 0130 01") == []           # Text-Schnittstelle bleibt streng
    st = mu.stellen("iban", "Konto DESG 9065 3989 4189 3574 45 (OCR)")        # Prüfziffern als Buchstaben gelesen
    assert [("DESG 9065 3989 4189 3574 45", False)] == [("Konto DESG 9065 3989 4189 3574 45 (OCR)"[s.start:s.ende],
                                                         s.streng) for s in st]
    assert mu.stellen("iban", "ab12 3456 7890 1234 5678 90") == []
    st = mu.stellen("steuerid", "Steuer-ID: 86095742718")
    assert len(st) == 1 and st[0].hinweis == mu.HINWEIS_PRUEFZIFFER
    st = mu.stellen("kreditkarte", "Kreditkarte: VISA 4532 0151 1283 0367")
    assert len(st) == 1 and not st[0].streng
    assert mu.stellen("kreditkarte", "Vertrag 4532 0151 1283 0367") == []
    assert mu.quellen_hinweis("muster.iban.lesefehler") == mu.HINWEIS_PRUEFZIFFER
    assert mu.quellen_hinweis("muster.iban") is None


def test_ausweis_amtliche_formate():
    # neuer Personalausweis/Reisepass: 9 Zeichen + Prüfziffer (ICAO 9303), auch ohne Etikett (nur Stellen-API)
    nummer = "L01X00T47" + str(mu._icao_pruefziffer("L01X00T47"))
    st = mu.stellen("ausweis", f"Kopie liegt bei ({nummer}).")
    assert [nummer] == [f"Kopie liegt bei ({nummer})."[s.start:s.ende] for s in st]
    falsch = "L01X00T47" + str((mu._icao_pruefziffer("L01X00T47") + 1) % 10)
    assert mu.stellen("ausweis", f"Nummer {falsch}") == []
    assert mu.finde_ausweisnummer("Anlage: Kopie Personalausweis (Nr. TLH4PLJCH)") == ["TLH4PLJCH"]
    assert mu.finde_ausweisnummer("Führerscheinnummer: J010000SD51") == ["J010000SD51"]
    assert mu.finde_ausweisnummer("Reisepassnummer C01X00T47") == ["C01X00T47"]


def test_bic_mandat_kvnr_phase3():
    assert mu.finde_bic("BIC:\nCOBADEFFXXX") == ["COBADEFFXXX"]
    st = mu.stellen("bic", "Bankverbindung Commerzbank COBADEFFXXX")      # ohne Etikett und IBAN: unsicher
    assert len(st) == 1 and not st[0].streng
    assert mu.stellen("bic", "RECHNUNG NACHTRAG BESCHEID") == []
    assert mu.finde_mandatsreferenz("Mandatsreferenz .....nnnnsan.. SEPA816626-520") == ["SEPA816626-520"]
    assert mu.finde_mandatsreferenz("Mandatsreferenz:\nM-2024-556677") == ["M-2024-556677"]
    assert mu.finde_kv_nummer("Krankenversichertennummer: A 123 456 789") == ["A 123 456 789"]


def test_steuer_id_ueber_zeilenumbruch():
    text = "Ihre Steuer-Identifikationsnummer 86 095\n742 719 gespeichert."
    assert mu.finde_steuer_id(text) == ["86 095\n742 719"]


def test_email_ocr_leerzeichen():
    assert mu.finde_email("Von: Andreea Ionescu <ionescu854@gmx . de>") == ["ionescu854@gmx . de"]
    assert mu.finde_email("nadeschda.pawlowa@ web.de") == ["nadeschda.pawlowa@ web.de"]
    assert mu.finde_email("Treffen @ Büro morgen") == []


# ---------------------------------------------------------------------- Kategorien und Schutzstufen (Abschnitt 9)
def test_neue_kategorien_und_platzhalter():
    eintraege = {k: (p, an) for k, _, p, _, an in mu.KATEGORIEN}
    assert eintraege["beruf"] == ("[BERUF]", True) and eintraege["arbeitgeber"] == ("[ARBEITGEBER]", True)
    assert eintraege["diagnose"] == ("[DIAGNOSE]", False) and eintraege["medikament"] == ("[MEDIKAMENT]", False)
    assert eintraege["ort"] == ("[ORT]", True) and eintraege["international"][1] is True
    assert all(len(e) == 5 for e in mu.KATEGORIEN)


def test_profile_vertrag_abschnitt_9():
    assert set(mu.PROFILE) == {"ausgewogen", "hoch", "maximal"} and mu.STANDARD_PROFIL == "hoch"
    standard = {k for k, _, _, _, an in mu.KATEGORIEN if an}
    hoch, ausgewogen, maximal = (set(mu.PROFILE[n]["aktive"]) for n in ("hoch", "ausgewogen", "maximal"))
    assert hoch == standard, "Standard-Häkchen = Schutzstufe „hoch“ (Oberfläche erkennt sonst „benutzerdefiniert“)"
    assert {"beruf", "arbeitgeber", "international"} <= hoch and not hoch & {"diagnose", "medikament", "datum"}
    assert ausgewogen < hoch and not ausgewogen & {"beruf", "arbeitgeber", "international"}
    assert maximal == hoch | {"diagnose", "medikament"}
    assert mu.hinweis_kategorien("hoch", hoch) == {"diagnose", "medikament"}
    assert mu.hinweis_kategorien("hoch", hoch | {"diagnose"}) == {"medikament"}
    assert mu.hinweis_kategorien("maximal", maximal) == set()
    assert mu.option("maximal", "alle_geburtsdaten") and not mu.option("hoch", "alle_geburtsdaten")
    assert all(isinstance(p["beschreibung"], str) for p in mu.PROFILE.values())


def test_wissens_kategorien_text_schnittstelle():
    assert mu.finde_berufe("Beruf: Zahnärztin") == ["Zahnärztin"]
    assert mu.finde_arbeitgeber("Arbeitgeber: Bäckerei Hofmeister") == ["Bäckerei Hofmeister"]
    assert mu.finde_diagnosen("Diagnosen:\n- Lumboischialgie links (M54.4)") == ["Lumboischialgie links (M54.4)"]
    assert mu.finde_medikamente("Medikation: Ibuprofen 600 mg bei Bedarf") == ["Ibuprofen 600 mg bei Bedarf"]
    assert mu.finde_orte("St. Ingbert, 03.04.2025") == ["St. Ingbert"]
    assert mu.finde_ausland("Prinsengracht 263, 1016 GV Amsterdam") == ["Prinsengracht 263", "1016 GV Amsterdam"]


# ---------------------------------------------------------------------- PLZ/Ort: Folgewörter, Etikett am Zeilenende
@pytest.mark.parametrize("text, erwartet", [
    ("26122 Oldenburg Unfall Weserbergland KF-2016-876830", "26122 Oldenburg"),   # OCR-Tabellenzeile
    ("03046 Cottbus BU R+V 1.210,25", "03046 Cottbus"),
    ("82467 Garmisch-Partenkirchen Unfall Hanseatische BU", "82467 Garmisch-Partenkirchen"),
    ("61352 Bad Homburg v. d. Höhe", "61352 Bad Homburg v. d. Höhe"),
    ("51465 Bergisch Gladbach", "51465 Bergisch Gladbach"),
    ("66386 St. Ingbert", "66386 St. Ingbert"),
    ("60311 FRANKFURT AM MAIN", "60311 FRANKFURT AM MAIN"),
    ("60311 Frankfurt Main", "60311 Frankfurt Main"),
    ("06108 Halle (Saale)", "06108 Halle (Saale)"),
    ("92637 Weiden i.d.OPf.", "92637 Weiden i.d.OPf."),
    ("91207 Lauf a.d.Pegnitz", "91207 Lauf a.d.Pegnitz"),
    ("67433 Neustadt an der Weinstraße", "67433 Neustadt an der Weinstraße"),
    ("76829 Landau in der Pfalz", "76829 Landau in der Pfalz"),
    ("06886 Lutherstadt Wittenberg", "06886 Lutherstadt Wittenberg"),
    ("D 90402 Nürnberg", "D 90402 Nürnberg"),
])
def test_plz_ort_folgewoerter(text, erwartet):
    assert mu.finde_plz_ort(text) == [erwartet]


def test_vertrag_etikett_am_zeilenende_im_fliesstext():
    assert mu.finde_vertragsnummern("Die Polizei (Polizeiinspektion Nürnberg-Süd, Aktenzeichen\n"
                                    "VU/2024/99344) nahm den Unfall auf.") == ["VU/2024/99344"]
    assert mu.finde_vertragsnummern("Kündigung meiner Privathaftpflichtversicherung, Versicherungsschein-Nr.\n"
                                    "Ai HR-2022-251237\nSehr geehrte Damen und Herren,") == ["HR-2022-251237"]
    # keine Jahreszahl, kein Datum, keine PLZ-Zeile
    assert mu.finde_vertragsnummern("Bitte nennen Sie stets Ihre Vertragsnummer\n2025 wird alles anders.") == []
    assert mu.finde_vertragsnummern("Bitte nennen Sie Ihre Kundennummer\n12345 Musterstadt") == []
    assert mu.finde_vertragsnummern("Ihre Schadennummer\n01.02.2025 eingegangen") == []


# ----------------------------------------------------------------------
# PLZ + Ort: nie über den Spaltentrenner, keine Registernummern (Runde 1, Paket erkennung-ocr)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("90762 Fürth\t\tPHV", ["90762 Fürth"]),
    ("90762 Bad\t\tHomburg", ["90762 Bad"]),
    ("60311 Frankfurt am\t\tMain", ["60311 Frankfurt"]),
    ("Musterweg 1\t\t90762 Fürth\t\tLeben Allianz", ["90762 Fürth"]),
    ("90402\t12345 Nürnberg", ["12345 Nürnberg"]),                 # einzelner Tabulator ist eine Lücke, kein Trenner
])
def test_plz_ort_nie_ueber_spaltentrenner(text, erwartet):
    assert mu.finde_plz_ort(text) == erwartet
    for s, e in mu.finde_plz_ort_stellen(text):
        assert "\t\t" not in text[s:e]


@pytest.mark.parametrize("text, erwartet", [
    # reine PLZ-Zelle + ganze Ort-Zelle: EINE Stelle über genau diesen Trenner (Tabelle PLZ | Ort, Kästchen)
    ("27568\t\tBremerhaven", ["27568\t\tBremerhaven"]),
    ("Anschrift:\t\tBirkenallee 119\t\t27568\t\tBremerhaven", ["27568\t\tBremerhaven"]),
    ("61348\t\tBad Homburg v. d. Höhe", ["61348\t\tBad Homburg v. d. Höhe"]),
    ("90762\t\tFürth\t\tPHV", ["90762\t\tFürth"]),                  # die Zelle danach gehört nicht dazu
    ("73610\t\tMateusz Grabowski", []),                             # Nachbarzelle ist kein Ort
    ("x 12345\t\tBerlin", []),                                       # PLZ-Zelle enthält mehr als die PLZ
    ("Kunden-Nr.\t\t12345\t\tAllianz", []),
    ("Vertrag\t\t12345\t\tGenerali", []),
    ("12345\t\tUSt-IdNr. DE123", []),
])
def test_plz_und_ort_in_nachbarzellen(text, erwartet):
    assert mu.finde_plz_ort(text) == erwartet
    for s, e in mu.finde_plz_ort_stellen(text):
        assert text[s:e].count("\t\t") <= 1 and mu.plz_ort_zellenpaar(text, s, e) == ("\t\t" in text[s:e])


@pytest.mark.parametrize("text", [
    "Amtsgericht Hamburg 12345 Musterstadt", "Registergericht Hamburg 12345 Musterstadt",
    "Handelsregister 12345 Musterstadt", "Amtsgericht Hamburg, HRB 12345 Musterstadt", "HRB: 16963 Vorstand",
    "HR B 16963 Musterstadt", "Amtsgericht Lübeck HR8 16963 Musterstadt",
    "Registergericht: Amtsgericht Lübeck, 45650 Musterstadt", "Amtsgericht Frankfurt am Main 12345 Musterstadt",
    "Amtsgericht München HRB\n12345 München",
    "Sitz: Wunsiedel - Amtsgericht Wunsiedel HRB 98644\t\tUSt-IdNr. DE871667547",
])
def test_registernummer_ist_keine_plz(text):
    assert mu.finde_plz_ort(text) == []


@pytest.mark.parametrize("text, erwartet", [
    ("Max Mustermann\nHauptstr. 5\n12345 Berlin", ["12345 Berlin"]),
    ("Das Amtsgericht hat entschieden.\n12345 Berlin", ["12345 Berlin"]),
    ("Amtsgericht Berlin\nLittenstraße 12\n10179 Berlin", ["10179 Berlin"]),
])
def test_registerregel_gegenproben(text, erwartet):
    assert mu.finde_plz_ort(text) == erwartet


# ----------------------------------------------------------------------
# Lücken der Muster (Runde 1, Paket erkennung-ocr)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("Tel. 0049 163 8280469\n6. Unfallhergang", ["0049 163 8280469"]),       # keine Aufzählung der Folgezeile
    ("Telefon 0911 123456\n45,90 EUR", ["0911 123456"]),                       # kein Betrag der Folgezeile
    ("Tel. (0911) 12\n34 56. Bitte rufen Sie an", ["(0911) 12\n34 56"]),       # Satzende ist keine Aufzählung
    ("Telefon: +49\n(0)1511 6539102.", ["+49\n(0)1511 6539102"]),
    ("Tel. 07 51 / 345\n09 42", ["07 51 / 345\n09 42"]),
    ("Bei Fragen bin ich unter 0\n15 22 / 660 77 64 erreichbar.", ["0\n15 22 / 660 77 64"]),
])
def test_telefon_ueber_zeilenumbruch_hinter_etikett(text, erwartet):
    assert mu.finde_telefon(text) == erwartet


@pytest.mark.parametrize("text, erwartet", [
    ("Die Polizei (Autobahnpolizei Feucht, Aktenzeichen 92 Js 6010/24) nahm den Unfall auf.", ["92 Js 6010/24"]),
    ("Die Polizei (Polizeipräsidium Oberfranken, Aktenzeichen 381 C\n817/23) nahm den Unfall auf.",
     ["381 C\n817/23"]),
    ("Aktenzeichen 4 Ds 123/24 Js", ["4 Ds 123/24"]),
    ("Kundennummer 12 Js", []),
    ("Aktenzeichen 381 C\n2025 wird alles anders", []),
])
def test_aktenzeichen_mit_registerzeichen_und_umbruch(text, erwartet):
    assert mu.finde_vertragsnummern(text) == erwartet


def test_ocr_datum_mit_o_ist_keine_telefonnummer():
    assert mu.finde_telefon("Geburtsdatum:\t\tO1/08/1966") == []
    assert mu.finde_telefon("Tel. O171 2345678") == ["O171 2345678"]


def test_mandatsreferenz_mit_ocr_rest_in_fuellpunkten():
    assert mu.finde_mandatsreferenz("Mandatsreferenz ...........nn. SEPA816626-520") == ["SEPA816626-520"]
    assert mu.finde_mandatsreferenz("Mandatsreferenz: wird ab dem 01.02.2025 vergeben") == []


def test_geburtsdatum_mit_monatsnamen_ueber_zeilenumbruch():
    assert mu.finde_geburtsdaten("Geburtsdatum laut unseren Unterlagen: 27.\nJanuar 1976.") == ["27.\nJanuar 1976"]
    assert mu.finde_geburtsdaten("Vertragsbeginn: 27.\nJanuar 2020") == []


@pytest.mark.parametrize("text, erwartet", [
    ("Steuer-ID der versicherten Person: 55 894 120 358;", ["55 894 120 358"]),
    ("Steuer-Identifikationsnummer des Kindes: 86095742719", ["86095742719"]),
    ("Steuer-Identifikationsnummer: 86 095 742\n719", ["86 095 742\n719"]),
    ("Steuer-IdNr. 86095742719", ["86095742719"]),
    ("Steuer-ID siehe Anlage. Telefon: 0911 1234567", []),
    ("Steuer-ID der Person und Telefon: 0911 1234567", []),
])
def test_steuer_id_hinter_laengerer_wendung(text, erwartet):
    assert mu.finde_steuer_id(text) == erwartet
