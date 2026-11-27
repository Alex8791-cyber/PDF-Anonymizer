# Kritik-Lauf K3: Dokumentarten des Maklerbüros, die in den Sparten fehlten (Entgeltabrechnung, Maklervollmacht,
# Unterschriftenblock Maklervertrag, Beratungsdokumentation, Schweigepflichtentbindung, Kündigung des Kunden,
# Personalausweis-Kopie mit MRZ, Kundenstammblatt ohne Doppelpunkte) – erfundene Personen und Nummern
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import bau


def F(name, seiten, geheim, **kw):
    d = dict(name=name, zeilen=[], geheim=geheim, bauer=bau.bauer(seiten))
    d.update(kw)
    return d


def Z(name, zeilen, geheim, **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, unicode=True)
    d.update(kw)
    return d


EXS = [40, 100, 165, 205, 250, 290, 385]
ENTGELT = [[(40, 45, "Brandlhuber Metallbau GmbH · Industriestraße 4 · 84478 Waldkraiburg", 7)]
           + bau.zeilen(40, 80, ["Herrn", "Severin Gstettner", "Kapellenweg 3", "84347 Pfarrkirchen"], 10, 14)
           + [(40, 160, "Abrechnung der Brutto/Netto-Bezüge für November 2026", 11)]
           + bau.tabelle(185, EXS, [["Personal-Nr.", "Geburtsdatum", "StKl", "Ki.Frbtr.", "Konf.", "SV-Nummer",
                                     "Krankenkasse"]], 7)
           + bau.tabelle(197, EXS, [["00471", "17.09.1966", "3", "1,0", "rk", "65170966G014", "AOK Bayern"]], 8.5)
           + bau.tabelle(220, EXS, [["Eintritt", "Steuer-ID", "", "", "", "Beitragsgruppe", "Resturlaub"]], 7)
           + bau.tabelle(232, EXS, [["01.04.2009", "52 918 304 620", "", "", "", "1111", "12,5 Tage"]], 8.5)
           + bau.tabelle(265, [40, 100, 400], [["Lohnart", "Bezeichnung", "Betrag"],
                                               ["1000", "Gehalt", "3.987,50"],
                                               ["2050", "VWL Arbeitgeberanteil", "26,59"],
                                               ["5100", "Entgeltumwandlung Direktversicherung", "-150,00"]], 8.5)
           + [(40, 345, "Gesamt-Brutto 4.014,09     Netto-Verdienst 2.611,37", 9),
              (40, 362, "Überweisung: IBAN DE58 7406 1813 0001 2345 67, Raiffeisenbank Musterland eG", 8.5)]]

VOLLMACHT = [bau.zeilen(60, 70, [
    "Maklervollmacht", "",
    "Hiermit bevollmächtige ich, Gerlinde Brandlhuber, geboren am 3. März 1965 in Trostberg,",
    "wohnhaft in der Schwarzenböckstraße 8, 84503 Altötting, die Sonnleitner Versicherungsmakler GmbH,",
    "mich gegenüber Versicherern, Behörden und Sozialversicherungsträgern zu vertreten.",
    "Die Vollmacht erstreckt sich auch auf die Verträge meines Ehemanns Vinzenz Brandlhuber,",
    "geb. 17.10.62, und unserer Tochter Liesl (geb. 2009).", "",
    "Altötting, den 12. November 2026", "", "_____________________________", "Gerlinde Brandlhuber"], 10, 15)]

UNTERSCHRIFT = [bau.zeilen(60, 70, ["Maklervertrag (Seite 4 von 4)",
                                    "§ 12 Schlussbestimmungen: Änderungen und Ergänzungen bedürfen der Textform."],
                           10, 15)
                + [(60, 160, "Trostberg, 12.11.2026", 10), (330, 160, "Trostberg, 12.11.2026", 10),
                   (60, 200, "______________________________", 10), (330, 200, "______________________________", 10),
                   (60, 212, "Unterschrift Auftraggeber", 7.5), (330, 212, "Unterschrift Makler", 7.5),
                   (60, 226, "Baltasar Hölzlwimmer", 10), (330, 226, "Sonnleitner Versicherungsmakler GmbH", 10),
                   (60, 280, "______________________________", 10),
                   (60, 292, "Unterschrift mitversicherte Person", 7.5),
                   (60, 306, "Ottilie Hölzlwimmer-Kraxenberger", 10)]]

BERATUNG = [bau.zeilen(40, 60, [
    "Beratungsdokumentation nach § 61 VVG – Gespräch vom 05.11.2026 in den Räumen des Maklers",
    "Anwesend: Herr Baltasar Wiesenhofer (Kunde), Frau Walburga Wiesenhofer (Ehefrau), Herr Sonnleitner (Makler)",
    "Situation: Der Kunde (54) ist selbständiger Elektromeister (Wiesenhofer Elektrotechnik e.K., Burghausen).",
    "Die Ehefrau (51) arbeitet als Zahnmedizinische Fachangestellte in der Praxis Dr. Oberprieler.",
    "Kinder: Liesl (9) und Korbinian (12), beide familienversichert bei der AOK Bayern.",
    "Vorerkrankungen: Bandscheibenvorfall L4/L5 im Jahr 2019, seitdem beschwerdefrei.",
    "Wunsch: Absicherung der Arbeitskraft und Risikoleben über 250.000 EUR zugunsten der Ehefrau."], 9, 14)]

SCHWEIGE = [bau.zeilen(40, 60, [
    "Schweigepflichtentbindungserklärung (Anlage zum Antrag auf Berufsunfähigkeitsversicherung)",
    "Ich, Severin Gstettner, geb. 17.09.1966, entbinde die folgenden Ärzte, Krankenhäuser und Therapeuten,",
    "die mich in den letzten fünf Jahren untersucht oder behandelt haben, von ihrer Schweigepflicht:",
    "– Hausärztin Dr. med. Afra Lechleitner, Marktplatz 3, 84347 Pfarrkirchen",
    "– Orthopädische Gemeinschaftspraxis Dr. Hölzlwimmer & Kollegen, Ringstraße 12, 84307 Eggenfelden",
    "– Physiotherapie Oberprieler, Stadtplatz 8, 84347 Pfarrkirchen (Behandlung 03–05/2024)",
    "– Rottal-Inn Kliniken, Standort Pfarrkirchen (stationär 11.03.–15.03.2024, Knie-Arthroskopie)", "",
    "Pfarrkirchen, 12.11.2026"], 9, 14)]

KUENDIGUNG = [[(60, 60, "Severin Gstettner · Kapellenweg 3 · 84347 Pfarrkirchen", 7.5)]
              + bau.zeilen(60, 90, ["Musterland Versicherung AG", "Kundenservice", "Postfach 20 30 40",
                                    "80001 München"], 10, 14)
              + bau.zeilen(60, 180, ["Pfarrkirchen, 12.11.2026", "",
                                     "Kündigung meiner Hausratversicherung, Versicherungsschein-Nr. HR-7740-2291-05", "",
                                     "Sehr geehrte Damen und Herren,",
                                     "hiermit kündige ich den oben genannten Vertrag fristgerecht zum 01.01.2027.",
                                     "Bitte bestätigen Sie mir die Kündigung schriftlich.", "",
                                     "Mit freundlichen Grüßen", "", "Severin Gstettner"], 10, 15)]

KOPF = [[(200, 55, "Ottilie Schwarzenböck", 16),
         (110, 75, "Sonnleitenstraße 17 · 83395 Freilassing · Tel. 08654 7781 · o.schwarzenboeck@web.de", 8)]
        + bau.zeilen(60, 120, ["Musterland Versicherung AG", "Schadenabteilung", "80001 München"], 10, 14)
        + bau.zeilen(60, 190, ["Freilassing, 12.11.2026", "",
                               "Widerspruch gegen Ihre Abrechnung vom 03.11.2026, Schaden-Nr. S-2026-118842", "",
                               "Sehr geehrte Damen und Herren,",
                               "der Zeitwert des Teppichs ist zu niedrig angesetzt. Die Rechnung liegt bei.", "",
                               "Mit freundlichen Grüßen", "Ottilie Schwarzenböck"], 10, 15)]

AUSWEIS = ["BUNDESREPUBLIK DEUTSCHLAND   PERSONALAUSWEIS   IDENTITY CARD",
           "Name/Surname/Nom: HÖLZLWIMMER",
           "Vornamen/Given names/Prénoms: BALTASAR KORBINIAN",
           "Geburtstag/Date of birth: 30.11.1990",
           "Geburtsort/Place of birth: TROSTBERG",
           "Staatsangehörigkeit/Nationality: DEUTSCH",
           "Gültig bis/Date of expiry: 14.03.2031          T22000129",
           "",
           "Anschrift/Address: 83346 BERGEN, KIRCHSTEIG 2",
           "IDD<<T220001293<<<<<<<<<<<<<<<",
           "9011300<3103142D<<<<<<<<<<<<<8",
           "HOELZLWIMMER<<BALTASAR<KORBINI"]

STAMM = ["Kundenstammblatt (Ausdruck Maklerverwaltung, Stand 12.11.2026)",
         "Anrede\t\tHerr", "Titel\t\tDipl.-Ing. (FH)", "Vorname\t\tBaltasar", "Nachname\t\tHölzlwimmer",
         "Geburtsdatum\t\t30.11.1990", "Geburtsort\t\tTrostberg", "Familienstand\t\tledig",
         "Beruf\t\tDachdeckermeister", "Arbeitgeber\t\tHolzbau Kraxenberger GmbH", "Straße\t\tKirchsteig 2",
         "PLZ / Ort\t\t83346 Bergen", "Telefon privat\t\t08662 4471", "Mobil\t\t0151 23456789",
         "E-Mail\t\tb.hoelzlwimmer@web.de", "Steuer-ID\t\t68 123 904 652"]

FAELLE = [
    F("k3_entgelt", ENTGELT, ["00471", "Gstettner", "17.09.1966", "65170966G014", "52918304620",
                              "DE58740618130001234567", "Kapellenweg 3", "84347"]),
    F("k3_vollmacht", VOLLMACHT, ["Brandlhuber", "3. März 1965", "Trostberg", "Schwarzenböckstraße 8", "84503",
                                  "17.10.62", "Liesl", "2009"]),
    F("k3_unterschrift", UNTERSCHRIFT, ["Hölzlwimmer", "Baltasar", "Kraxenberger", "Trostberg"]),
    F("k3_beratung", BERATUNG, ["Wiesenhofer", "Walburga", "Elektromeister", "Wiesenhofer Elektrotechnik",
                                "Zahnmedizinische Fachangestellte", "Oberprieler", "Liesl", "Korbinian"]),
    F("k3_schweigepflicht", SCHWEIGE, ["Gstettner", "17.09.1966", "Lechleitner", "Hölzlwimmer", "Oberprieler"]),
    F("k3_kuendigung", KUENDIGUNG, ["Gstettner", "Kapellenweg 3", "84347", "HR7740229105"]),
    F("k3_briefkopf_privat", KOPF, ["Schwarzenböck", "Sonnleitenstraße 17", "83395", "086547781",
                                    "o.schwarzenboeck@web.de", "S2026118842"]),
    Z("k3_ausweis", AUSWEIS, ["HÖLZLWIMMER", "BALTASAR", "30.11.1990", "TROSTBERG", "T22000129", "KIRCHSTEIG 2",
                              "83346", "HOELZLWIMMER", "9011300"], scans=((200, 0.0, None),)),
    Z("k3_stammblatt", STAMM, ["Baltasar", "Hölzlwimmer", "30.11.1990", "Trostberg", "Dachdeckermeister",
                               "Holzbau Kraxenberger", "Kirchsteig 2", "83346", "086624471", "015123456789",
                               "b.hoelzlwimmer@web.de", "68123904652"]),
]
