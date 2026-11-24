# Kritik-Lauf K2: Listen aus dem Maklerbüro (Courtageabrechnung, Fortsetzung auf Folgeseite, Bestandsübertragung,
# Kundenliste aus der Maklerverwaltung, CSV-Ausdruck, Angebotsvergleich, Gruppenunfall-Liste, Zellumbruch)
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import bau


def F(name, seiten, geheim, **kw):
    d = dict(name=name, zeilen=[], geheim=geheim, bauer=bau.bauer(seiten))
    d.update(kw)
    return d


CXS = [36, 112, 252, 300, 352, 410, 480]
COURT_KOPF = ["VSNR", "Versicherungsnehmer", "Sparte", "Beginn", "Beitrag", "Satz", "Courtage"]
COURT = [[(36, 50, "Courtageabrechnung Oktober 2026", 12),
          (36, 66, "Musterland Versicherung AG – Abrechnung für Vermittler-Nr. 0815-4471, Sonnleitner "
                   "Versicherungsmakler GmbH", 7.5)]
         + bau.tabelle(95, CXS, [COURT_KOPF,
                                 ["HR-7740-2291-05", "KRAXENBERGER, WENDELIN", "Hausrat", "01.12.2026", "186,40",
                                  "15,0 %", "27,96"],
                                 ["LV 2291/8817-03", "Gstettner, Severin", "BU", "01.11.2026", "1.234,56",
                                  "25 ‰ BWS", "308,64"],
                                 ["KV 12/3456789-0", "Pichlmeier, N.", "PKV", "01.10.2026", "4.812,00", "3,0 MB",
                                  "1.203,00"],
                                 ["PHV-0071-4471", "Brandlhuber Gerlinde", "PHV", "01.11.2026", "89,90", "20,0 %",
                                  "17,98"],
                                 ["U-2026-5512", "SCHWARZENBÖCK OTTILIE", "Unfall", "15.10.2026", "142,80", "20,0 %",
                                  "28,56"]], 7.5)
         + [(36, 210, "Summe Courtage: 1.586,14 EUR – Auszahlung auf das bekannte Courtagekonto.", 8)]]

FORTS = [[(36, 50, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026", 12)]
         + bau.tabelle(80, [36, 130, 290, 380, 470],
                       [["Vertrag", "Versicherungsnehmer", "Sparte", "Beginn", "Jahresbeitrag"]]
                       + [["HR-7740-2291-05", "Kraxenberger, Wendelin", "Hausrat", "01.12.2020", "186,40"]] * 1
                       + [["PHV-0071-4471", "Brandlhuber, Gerlinde", "PHV", "01.11.2019", "89,90"]]
                       + [["KFZ-2021-4400", "Haberl, Josefa", "Kfz", "01.01.2021", "612,00"],
                          ["RS-0815-2291", "Haberl, Josefa", "Rechtsschutz", "01.03.2018", "298,30"]], 8),
         [(36, 40, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026 – Seite 2", 8)]
         + bau.tabelle(70, [36, 130, 290, 380, 470],
                       [["LV 2291/8817-03", "Gstettner, Severin", "BU", "01.11.2016", "1.234,56"],
                        ["WG 4471-0815-22", "Hölzlwimmer, Vinzenz", "Wohngebäude", "01.11.2022", "612,00"],
                        ["U-2026-5512", "Schwarzenböck, Ottilie", "Unfall", "15.10.2026", "142,80"]], 8)]

BESTAND = [[(36, 50, "Anlage zum Maklerauftrag – Übertragung der Betreuung (Vertragsliste)", 11)]
           + bau.tabelle(80, [36, 130, 210, 270, 400, 470],
                         [["Gesellschaft", "Vers.-Nr.", "Sparte", "Versicherungsnehmer", "geb. am", "Ablauf"],
                          ["Musterland Leben", "4471 0815 22", "Rente", "Gstettner, Severin", "17.09.1966",
                           "01.10.2031"],
                          ["Beispiel Sach AG", "SH-88 1294 7", "Hausrat", "Gstettner, Afra", "21.06.1969",
                           "01.01.2027"],
                          ["Muster Kranken", "K 7712 3450", "PKV", "Gstettner, Severin", "17.09.1966", "–"]], 8)
           + [(36, 160, "Hiermit beauftrage ich den Makler, die Betreuung der o. g. Verträge zu übernehmen.", 9)]]

KUNDEN = [[(30, 50, "Kundenliste – Export Maklerverwaltung (Filter: PLZ 83*, Stand 12.11.2026)", 10)]
          + bau.tabelle(80, [30, 72, 140, 192, 290, 322, 410, 468],
                        [["Kd.-Nr.", "Name", "Vorname", "Straße", "PLZ", "Ort", "Geb.-Dat.", "Telefon"],
                         ["10471", "Ruhstorfer", "Kunigunde", "Untere Bachgasse 5", "83512", "Wasserburg a. Inn",
                          "21.06.1949", "08071 12345"],
                         ["10472", "Kraxenberger", "Wendelin", "Hölzlweg 12", "83626", "Valley", "14.05.1971",
                          "08024 47119"],
                         ["10473", "Schwarzenböck", "Ottilie", "Sonnleitenstraße 17", "83395", "Freilassing",
                          "03.03.1980", "08654 7781"],
                         ["10474", "Hölzlwimmer", "Vinzenz", "Kirchsteig 2", "83346", "Bergen", "30.11.1990",
                          "0160 5544332"]], 7)]

CSV = [[(36, 50, "kunden_export_2026-11-12.csv", 9)]
       + bau.zeilen(36, 75, ["Kdnr;Name;Vorname;Strasse;PLZ;Ort;Gebdat;Telefon;Email",
                             "10475;Oberprieler;Severin;Kirchweg 9;83527;Haag i. OB;12.12.1975;08072 9876;"
                             "s.oberprieler@gmx.de",
                             "10476;Lechleitner;Walburga;Am Anger 22;83533;Edling;01.02.1961;08071 5566;"], 8, 12)]

VERGL = [[(36, 50, "Angebotsvergleich Privathaftpflicht", 12),
          (36, 68, "für Herrn Vinzenz Hölzlwimmer, geb. 30.11.1990, Single ohne Kind, Beamter", 9)]
         + bau.tabelle(95, [36, 160, 280, 400],
                       [["Versicherer", "Tarif", "Deckungssumme", "Jahresbeitrag"],
                        ["Adam Riese", "XXL", "50 Mio. EUR", "61,23 EUR"],
                        ["Roland", "Komfort", "20 Mio. EUR", "58,90 EUR"],
                        ["Waldenburger", "Premium", "30 Mio. EUR", "64,10 EUR"],
                        ["Haftpflichtkasse", "Einfach Komplett", "50 Mio. EUR", "79,00 EUR"],
                        ["Basler", "Top", "30 Mio. EUR", "72,30 EUR"]], 8.5)]

GRUPPE = [[(36, 50, "Gruppenunfallversicherung – Verzeichnis der versicherten Personen", 11),
           (36, 66, "Versicherungsnehmer: Kraxenberger Holzbau GmbH, Gewerbering 3, 83346 Bergen", 8)]
          + bau.tabelle(95, [36, 60, 190, 260, 420],
                        [["Lfd.", "Name, Vorname", "Geb.-Datum", "Tätigkeit", "Gefahrengruppe"],
                         ["1", "Hölzlwimmer, Vinzenz", "30.11.1990", "Dachdecker", "B"],
                         ["2", "Oberprieler, Severin", "12.12.1975", "Bürokaufmann", "A"],
                         ["3", "Kraxenberger, Liesl", "03.04.2001", "Auszubildende Zimmerin", "B"]], 8)]

UMBRUCH = [[(36, 50, "Wohngebäude – Bestandsübersicht Hausverwaltung", 11)]
           + bau.tabelle(80, [36, 130, 260, 470],
                         [["VSNR", "Versicherungsnehmer", "Risikoanschrift", "Beitrag"],
                          ["WG 4471-0815-22", "Wiesenhofer, Baltasar", "Am Kellerberg 7,", "612,00"],
                          ["", "und Walburga", "84489 Burghausen", ""],
                          ["WG 4471-0815-23", "Erbengemeinschaft", "Untere Bachgasse 5,", "498,00"],
                          ["", "Ruhstorfer", "83512 Wasserburg a. Inn", ""]], 8, 11)]

FAELLE = [
    F("k2_courtage", COURT, ["Kraxenberger", "Gstettner", "Pichlmeier", "Brandlhuber", "Schwarzenböck",
                             "HR7740229105", "LV2291881703", "KV1234567890", "PHV00714471", "U20265512"]),
    F("k2_fortsetzung", FORTS, ["Gstettner", "Hölzlwimmer", "Schwarzenböck", "LV2291881703", "WG4471081522",
                                "U20265512"]),
    F("k2_bestand", BESTAND, ["Gstettner", "17.09.1966", "21.06.1969", "4471081522", "SH8812947", "K77123450"]),
    F("k2_kundenliste", KUNDEN, ["10471", "Ruhstorfer", "Untere Bachgasse 5", "83512", "21.06.1949", "0807112345",
                                 "Kraxenberger", "Hölzlweg 12", "14.05.1971", "Schwarzenböck", "03.03.1980",
                                 "Hölzlwimmer", "Kirchsteig 2", "01605544332"]),
    F("k2_csv", CSV, ["10475", "Oberprieler", "Kirchweg 9", "83527", "12.12.1975", "080729876",
                      "s.oberprieler@gmx.de", "Lechleitner", "Am Anger 22", "83533", "01.02.1961", "080715566"]),
    F("k2_vergleich", VERGL, ["Hölzlwimmer", "30.11.1990"]),
    F("k2_gruppe", GRUPPE, ["Hölzlwimmer", "30.11.1990", "Oberprieler", "12.12.1975", "Kraxenberger",
                            "03.04.2001"]),
    F("k2_umbruch", UMBRUCH, ["Wiesenhofer", "Walburga", "Am Kellerberg 7", "84489", "Ruhstorfer",
                              "Untere Bachgasse 5", "83512"]),
]
