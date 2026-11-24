# Domänen-Probe "Finanzen, Behörden": Bank, Steuer, Rente/Sozialleistungen, Ausweis/Aufenthalt.
# Alle Namen und Nummern sind erfunden (Prüfziffern von IBAN, Kreditkarte, Steuer-ID gültig gerechnet).
def F(name, zeilen, geheim, scans=(), **kw):
    return dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans, **kw)


S200 = ((200, 0.0, None),)

FAELLE = [
    # ------------------------------------------------------------------ Bank
    F("bank_depotauszug", [
        "Musterbank AG · Kaiserstraße 1 · 60311 Frankfurt am Main",
        "",
        "Herrn",
        "Quirin Zwackelhuber",
        "Lerchenfeldstraße 12",
        "86150 Augsburg",
        "",
        "Depotauszug per 31.12.2025",
        "Depotinhaber: Quirin Zwackelhuber",
        "Depot-Nr. 712.345.678\t\tKunden-Nr. 4.711.081",
        "Verrechnungskonto: 0712345679",
        "Wertpapier\t\tStück\t\tKurswert EUR",
        "MSCI World ETF\t\t125\t\t12.345,67",
        "Deutsche Telekom AG\t\t200\t\t5.432,10",
    ], ["712.345.678", "4.711.081", "0712345679", "Zwackelhuber", "Lerchenfeldstraße 12"]),

    F("bausparvertrag", [
        "Bausparkasse Musterstadt AG",
        "Jahreskontoauszug 2025 zu Ihrem Bausparvertrag",
        "Bausparer: Irmtraud Ölschläger\t\tVertragsnummer: 6.012.345.678",
        "Bausparsumme: 50.000,00 EUR\t\tTarif: Classic 25",
        "Darlehenskonto: 6012345679 (nach Zuteilung)",
        "Wohnungsbauprämie: Ihre Steuer-ID 52690741930 wurde übermittelt.",
    ], ["6.012.345.678", "6012345679", "52690741930", "Ölschläger"]),

    F("konten_uebersicht", [
        "Ihre Konten im Überblick – Kunde: Quirin Zwackelhuber",
        "Konto\t\tKontonummer\t\tSaldo EUR",
        "Girokonto\t\t1234567890\t\t2.345,67",
        "Tagesgeld\t\t9876543210\t\t10.000,00",
        "Kreditkarte\t\t4929 3847 6512 3458\t\t-312,40",
        "Referenzkonto für Auszahlungen: DE29 7205 0000 0240 1234 56",
    ], ["1234567890", "9876543210", "4929384765123458", "DE29720500000240123456", "Zwackelhuber"]),

    F("iban_varianten", [
        "SEPA-Lastschriftmandat",
        "Kontoinhaber: Irmtraud Ölschläger",
        "IBAN: de66 7209 0000 0001 2345 67",
        "IBAN (bei Rückerstattung): DE26-7015-0000-9988-7766-55",
        "Zweitkonto der Ehefrau: AT84 2011 1282 6541 8800",
        "Bitte überweisen Sie den Betrag auf das Konto DE29 7205 0000",
        "0240 1234 56 (Kontoinhaber: Q. Zwackelhuber).",
    ], ["DE66720900000001234567", "DE26701500009988776655", "AT842011128265418800", "DE2972050000",
        "0240123456", "Ölschläger", "Zwackelhuber"], scans=S200),

    F("kreditkarte_varianten", [
        "Reiseversicherung – Zahlung per Kreditkarte",
        "Karteninhaber: Quirin Zwackelhuber",
        "Kreditkartennummer: 4532.0151.1283.0366, gültig bis 08/27",
        "Mastercard 5425 2334 3010 9903",
        "American Express: 3714 496353 98431",
        "Kartennummer der Ehefrau (Visa): 5100-1234-5678-9013",
    ], ["4532015112830366", "5425233430109903", "371449635398431", "5100123456789013", "Zwackelhuber"]),

    F("darlehen_kredit", [
        "Darlehensvertrag Nr. 2025/77812-01",
        "Darlehensnehmer: Quirin Zwackelhuber, Lerchenfeldstraße 12, 86150 Augsburg",
        "Mitdarlehensnehmerin: Irmtraud Zwackelhuber",
        "Kreditnummer: 60 1234 5678",
        "Restschuldversicherung zu Kredit 6012345678, versicherte Person: Quirin Zwackelhuber",
        "Auszahlung auf Girokonto 1234567890 bei der Stadtsparkasse Augsburg",
    ], ["2025/77812-01", "6012345678", "1234567890", "Zwackelhuber", "Lerchenfeldstraße 12"]),

    F("pfaendung_pkonto", [
        "Pfändungs- und Überweisungsbeschluss – Amtsgericht Augsburg, Az. 2 M 1234/25",
        "Schuldner: Quirin Zwackelhuber, Lerchenfeldstraße 12, 86150 Augsburg",
        "Drittschuldnerin: Stadtsparkasse Augsburg",
        "Gepfändet wird das Guthaben auf dem Konto 1234567890 (Pfändungsschutzkonto).",
        "Gläubigerin: Inkasso Muster GmbH, Gz. IM-4711/25",
    ], ["2M1234/25", "Zwackelhuber", "1234567890", "Lerchenfeldstraße 12"]),

    F("formular_felder_bank", [
        "Antrag auf Beitragsrückerstattung",
        "Kontoinhaber:",
        "IBAN:",
        "Steuer-ID:",
        "Depotnummer:",
    ], ["Ölschläger", "DE66720900000001234567", "90375461211", "712.345.678"],
        felder=(("Kontoinhaber", (200, 86, 450, 102), "Irmtraud Ölschläger"),
                ("IBAN", (200, 104, 450, 120), "DE66 7209 0000 0001 2345 67"),
                ("SteuerID", (200, 122, 450, 138), "90 375 461 211"),
                ("Depotnummer", (200, 140, 450, 156), "712.345.678"))),

    # ------------------------------------------------------------------ Steuer
    F("steuerbescheid", [
        "Finanzamt Augsburg-Stadt · Prinzregentenplatz 2 · 86150 Augsburg",
        "Steuernummer: 103/215/80451",
        "",
        "Herrn und Frau",
        "Quirin und Irmtraud Zwackelhuber",
        "Lerchenfeldstraße 12",
        "86150 Augsburg",
        "",
        "Bescheid für 2024 über Einkommensteuer und Solidaritätszuschlag",
        "Identifikationsnummer: Ehemann 10 163 985 243, Ehefrau 30 268 175 922",
        "Festgesetzt werden: Einkommensteuer 4.812,00 EUR",
        "Kassenzeichen: 921.103.215",
    ], ["103/215/80451", "10163985243", "30268175922", "Zwackelhuber", "921.103.215", "Lerchenfeldstraße 12"],
        scans=S200),

    F("steuer_id_kinder", [
        "Anlage Kind zum Antrag auf Kindergeld",
        "Familienkasse Bayern Süd\t\tKindergeldnummer: 245FK123456",
        "Steuer-ID Kind 1: 14 208 593 466",
        "Steuer-ID Kind 2: 90 186 747 252",
        "Vorname\t\tGeburtsdatum\t\tIdentifikationsnummer",
        "Lio\t\t14.07.2015\t\t54 361 902 281",
        "Mia\t\t02.02.2018\t\t78 934 510 695",
    ], ["14208593466", "90186747252", "54361902281", "78934510695", "245FK123456", "14.07.2015", "02.02.2018"]),

    F("steuernummer_gewerbe", [
        "Fragebogen zur steuerlichen Erfassung – Einzelunternehmen",
        "Inhaber: Gottfried Brezelmeier (Hausmeisterservice)",
        "Steuernummer (Gewerbe): 178/123/45678",
        "Steuernr. 9178012345678 (ELSTER)",
        "USt-IdNr.: DE287654321",
        "Steuernummer bisher (FA Augsburg-Land): 102/123/45678",
    ], ["Brezelmeier", "178/123/45678", "9178012345678", "DE287654321", "102/123/45678"]),

    F("lohnsteuerbescheinigung", [
        "Ausdruck der elektronischen Lohnsteuerbescheinigung für 2024",
        "Identifikationsnummer: 17 490 854 263",
        "Personalnummer: 004711\t\tGeburtsdatum: 03.03.1985",
        "eTIN: ZWCKQRN85C03",
        "Arbeitnehmer: Quirin Zwackelhuber, Lerchenfeldstraße 12, 86150 Augsburg",
        "Arbeitgeber: Brezelmeier Haustechnik e.K., Steuernummer 178/123/45678",
        "Bruttoarbeitslohn 41.250,00 EUR",
    ], ["17490854263", "004711", "03.03.1985", "ZWCKQRN85C03", "Zwackelhuber", "Lerchenfeldstraße 12"]),

    # ------------------------------------------------------------------ Rente / Sozialleistungen
    F("rentenbescheid", [
        "Deutsche Rentenversicherung Schwaben · 86223 Augsburg",
        "Versicherungsnummer 12 030359 Z 508",
        "Herrn Quirin Zwackelhuber",
        "Rentenbescheid – Altersrente für langjährig Versicherte",
        "Die Rente beginnt am 01.04.2025. Monatlicher Zahlbetrag: 1.734,22 EUR",
        "Zahlung auf: IBAN DE29 7205 0000 0240 1234 56",
        "Renten Service der Deutschen Post AG, Rentennummer 12 030359 Z 508 / 41",
        "Bei Rückfragen: Frau Edeltraud Bichlmaier, Telefon 0821 500-4711",
    ], ["12030359Z508", "Zwackelhuber", "DE29720500000240123456"]),

    F("jobcenter_bescheid", [
        "Jobcenter Augsburg-Stadt · Wertachstraße 28 · 86153 Augsburg",
        "BG-Nummer: 96202BG0012345\t\tKundennummer: 962D123456",
        "Bewilligungsbescheid über Bürgergeld",
        "Mitglieder der Bedarfsgemeinschaft:",
        "Name\t\tVorname\t\tgeboren am",
        "Zwackelhuber\t\tQuirin\t\t03.03.1985",
        "Zwackelhuber\t\tLio\t\t14.07.2015",
        "Nummer der Bedarfsgemeinschaft bitte stets angeben: 96202//0012345",
    ], ["96202BG0012345", "962D123456", "Zwackelhuber", "03.03.1985", "14.07.2015", "96202//0012345"],
        scans=S200),

    F("agentur_arbeit", [
        "Agentur für Arbeit Augsburg",
        "Ihre Kundennummer: 962D654321\t\tMein Zeichen: 832.3 – 962D654321",
        "Bescheid über die Bewilligung von Arbeitslosengeld",
        "Frau Irmtraud Ölschläger, geb. 22.11.1979",
        "Bemessungsentgelt täglich: 98,52 EUR",
        "Bankverbindung: IBAN DE66 7209 0000 0001 2345 67",
    ], ["962D654321", "Ölschläger", "22.11.1979", "DE66720900000001234567"]),

    F("kindergeld_bescheid", [
        "Familienkasse Bayern Süd",
        "Kindergeld-Nr. 245 FK 654 321",
        "Kindergeldberechtigte: Irmtraud Ölschläger",
        "Kind: Mia Ölschläger, geb. 02.02.2018",
        "Ihr Kindergeld wird unter der Kindergeldnummer 245FK654321 geführt.",
    ], ["245FK654321", "Ölschläger", "02.02.2018"]),

    F("elterngeld", [
        "Zentrum Bayern Familie und Soziales – Elterngeldstelle Schwaben",
        "Aktenzeichen: EG 2024/123456",
        "Antragsnummer (ElterngeldDigital): EGD-7H3K-92LX",
        "Bescheid über Elterngeld für Ihr Kind Mia Ölschläger, geboren am 14.07.2024",
        "Elterngeldberechtigt: Irmtraud Ölschläger",
        "anderer Elternteil: Quirin Zwackelhuber",
    ], ["EG2024/123456", "EGD7H3K92LX", "Ölschläger", "Zwackelhuber", "14.07.2024"]),

    # ------------------------------------------------------------------ Ausweis / Pass / Aufenthalt
    F("legitimation_gwg", [
        "Identifizierung nach dem Geldwäschegesetz (Lebensversicherung)",
        "Name, Vorname: Zwackelhuber, Quirin",
        "Staatsangehörigkeit: deutsch",
        "Ausweisart: Personalausweis\t\tAusweisnummer: L7XKPMT92",
        "Ausstellende Behörde: Stadt Augsburg, ausgestellt am: 12.05.2021",
        "gültig bis: 11.05.2031\t\tGeburtsort: Augsburg",
        "Die Identität wurde zusätzlich anhand des Reisepasses CF9JKRTN7 geprüft.",
    ], ["Zwackelhuber", "L7XKPMT92", "CF9JKRTN7"], scans=S200),

    F("aufenthaltstitel", [
        "Stadt Augsburg – Ausländerbehörde",
        "Az.: 32.1-AT-4711/25",
        "Frau Elif Karadag",
        "Ihr elektronischer Aufenthaltstitel (Seriennummer Y4KR7NT2X) ist bis zum 30.06.2026 gültig.",
        "AZR-Nummer: 123456789012",
        "Nummer des Nationalpasses: U12345678",
    ], ["32.1-AT-4711/25", "Karadag", "Y4KR7NT2X", "123456789012", "U12345678"]),
]
