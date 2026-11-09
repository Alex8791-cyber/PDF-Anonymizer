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
