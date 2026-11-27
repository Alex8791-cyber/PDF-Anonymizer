# Domänen-Probe Sparte Personenversicherungen/Gesundheit, Runde 1 (erfundene Personen und Nummern;
# Kennungen mit gültigen Prüfziffern aus kennungen_person.py)
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


SCAN = ((200, 0.0, None),)
Y0, DY = 80, 11 * 1.65


def feld(name, zeile, wert, x0=300, x1=560):
    y = Y0 + zeile * DY
    return (name, (x0, y - 11, x1, y + 4), wert)


FAELLE = [
    # --- PKV / GKV -------------------------------------------------------------------------------------------
    F("pkv_schein_tarife", [
        "Versicherungsschein Krankheitskostenvollversicherung",
        "Versicherungsnehmer: Dr. Annette Kolbenschlag, Ginsterweg 7, 82152 Planegg",
        "Versicherungsnummer: KV 4471 0815 22",
        "Versicherte Person\t\tgeb. am\t\tTarife",
        "Annette Kolbenschlag\t\t14.02.1971\t\tAM 80, ZE 75, KT 43, PVN",
        "Moritz Kolbenschlag\t\t09.10.2013\t\tKAM, KZE 90, PVN",
        "Beginn: 01.01.2025\t\tSelbstbehalt: 1.200 EUR\t\tBeitrag: 612,48 EUR",
    ], ["Kolbenschlag", "Ginsterweg 7", "4471081522", "14.02.1971", "09.10.2013", "Moritz"]),

    F("gkv_mitgliedsbescheinigung", [
        "Techniker Krankenkasse - Mitgliedsbescheinigung nach § 175 SGB V",
        "Herr Tobias Wendeborn",
        "Krankenversichertennummer: K123456781",
        "Mitglied seit: 01.04.2009",
        "Arbeitgeber: Hollerith Kältetechnik GmbH, Nürnberg",
        "Diese Bescheinigung gilt zur Vorlage beim Arbeitgeber.",
    ], ["Wendeborn", "K123456781", "Hollerith"]),

    F("ehic_karte", [
        "Europäische Krankenversicherungskarte (Kopie)",
        "3. Name: OSTERKAMP",
        "4. Vornamen: JULIANE",
        "5. Geburtsdatum: 27/03/1988",
        "6. Persönliche Kennnummer: X204817365",
        "7. Kennnummer des Trägers: 101575519 - TK",
        "8. Kennnummer der Karte: 80276001570012345678",
        "9. Ablaufdatum: 31/12/2028",
    ], ["OSTERKAMP", "JULIANE", "27/03/1988", "X204817365", "80276001570012345678"], scans=SCAN),

    F("beihilfe_antrag", [
        "Antrag auf Beihilfe zu Aufwendungen in Krankheits-, Pflege- und Geburtsfällen",
        "Name, Vorname des Beihilfeberechtigten: Brunnhuber, Korbinian",
        "Personalnummer: 00841173",
        "Dienststelle: Finanzamt Rosenheim, Wittelsbacherstraße 10",
        "Aufwendungen für: Ehefrau Vroni Brunnhuber, geb. 11.06.1979; Sohn Xaver, geb. 02.02.2015",
        "Beihilfebemessungssatz: 70 %",
    ], ["Brunnhuber", "Korbinian", "00841173", "11.06.1979", "Xaver", "02.02.2015"]),

    F("nummern_mit_punkten", [
        "Beihilfe-Nr.: 4.711.208",
        "Personalnummer 1.234.567",
        "Versicherungsnummer: 123.456.789",
        "Mitgliedsnummer der Ärzteversorgung: 88.214.067",
    ], ["4711208", "1234567", "123456789", "88214067"]),

    F("arztrechnung_goae", [
        "Privatärztliche Verrechnungsstelle Südbayern GmbH",
        "Rechnungsempfänger: Ilse Wohlgemuth-Brandl, Am Mühlbach 12, 83646 Bad Tölz",
        "Patient/in: Ilse Wohlgemuth-Brandl, geb. 30.08.1956",
        "Rechnungs-Nr.: R-2024-118733\t\tKunden-Nr.: 77120934",
        "Behandelnder Arzt: Dr. med. Kemal Yıldırım, Facharzt für Innere Medizin",
        "Datum\t\tGOÄ-Nr. / Leistung\t\tBetrag",
        "03.06.2024\t\t1 Beratung\t\t10,72 €",
        "03.06.2024\t\t250 Blutentnahme\t\t4,20 €",
        "Diagnose: Diabetes mellitus Typ 2 (E11.9)",
    ], ["Wohlgemuth", "Am Mühlbach 12", "30.08.1956", "R2024118733", "77120934", "Yıldırım"],
        scans=SCAN, unicode=True),

    F("zahnarzt_goz_tabelle", [
        "Liquidation zahnärztliche Behandlung",
        "Patient: Malte Gerstenkorn, geb. 05.05.1990",
        "Datum\t\tGOZ-Nr.\t\tBetrag",
        "12.03.2025\t\t0010\t\t12,94 €",
        "12.03.2025\t\t2197\t\t16,82 €",
        "19.03.2025\t\t5120\t\t287,31 €",
        "Zahn 36, Regio 46-47, Faktor 2,3",
    ], ["Gerstenkorn", "05.05.1990"]),

    F("klinik_entlassbrief", [
        "Klinikum Ingolstadt - Klinik für Unfallchirurgie",
        "Patient: Gregor Wollnitz, *19.07.1964",
        "Aufnahmenummer: 2501-77341\t\tFall-Nr. 30044871",
        "Station U3, Zimmer 312",
        "Aufnahme: 14.03.2025 - Entlassung: 21.03.2025",
        "Diagnosen: Distale Radiusfraktur rechts (S52.51)",
        "Einweisender Arzt: Dr. Petra Ullrich-Habermann, Gaimersheim",
    ], ["Wollnitz", "19.07.1964", "250177341", "30044871", "Ullrich", "Gaimersheim"]),

    F("leistungsabrechnung_pkv", [
        "Leistungsabrechnung vom 02.10.2025",
        "Versicherte Person: Thea Grünewald-Sanchez, Vers.-Nr. 300 4471 12",
        "Rechnung von\t\tRechnungsdatum\t\tErstattung",
        "Dr. Holger Sauerbier\t\t15.08.2025\t\t214,50 €",
        "Löwen-Apotheke Freising\t\t22.08.2025\t\t38,90 €",
        "Physiotherapie Lindqvist\t\t29.08.2025\t\t260,00 €",
        "Die Erstattung überweisen wir auf IBAN DE43 7505 0000 0012 3456 78.",
    ], ["Grünewald", "300447112", "Sauerbier", "Lindqvist", "DE43750500000012345678"]),

    # --- BU / LV / Rente ------------------------------------------------------------------------------------
    F("bu_antrag_gesundheit", [
        "Antrag Berufsunfähigkeitsversicherung - Gesundheitsangaben",
        "Zu versichernde Person: Jannik Feuerstake, geb. 23.01.1992",
        "Beruf: Mechatroniker für Kältetechnik, Arbeitgeber: Kälte-Kraus GmbH, Landshut",
        "Größe: 181 cm\t\tGewicht: 84 kg",
        "Frage 4: Behandlungen in den letzten 5 Jahren? Ja - 03/2022 Bandscheibenvorfall,",
        "konservativ behandelt durch Dr. Wenzel (Orthopäde in Kempten), beschwerdefrei.",
        "Hausarzt: Dr. med. Sigrid Pfaffenzeller, Bahnhofstr. 3, 87435 Kempten",
    ], ["Feuerstake", "23.01.1992", "Kälte-Kraus", "Wenzel", "Pfaffenzeller", "Bahnhofstr. 3"]),

    F("lv_bezugsrecht_varianten", [
        "Bezugsrecht zur Risikolebensversicherung",
        "Im Erlebensfall: der Versicherungsnehmer",
        "Im Todesfall: Lebensgefährtin Sabine Krull, geb. 01.07.1985, unwiderruflich",
        "ersatzweise die Kinder zu gleichen Teilen: Paula Wendt (03.04.2014),",
        "Jonas Wendt (21.09.2016)",
    ], ["Krull", "01.07.1985", "Paula", "Wendt", "03.04.2014", "21.09.2016"]),

    F("renteninformation_drv", [
        "Deutsche Rentenversicherung Bund",
        "Renteninformation 2025",
        "Versicherungsnummer: 12 150385 M 003",
        "Herrn Detlef Ammersbach, Lerchenfeldweg 22, 93051 Regensburg",
        "Ihre bisher erreichte Rentenanwartschaft beträgt 1.142,37 EUR.",
    ], ["12150385M003", "Ammersbach", "Lerchenfeldweg 22"]),

    F("bav_entgeltumwandlung", [
        "Entgeltumwandlungsvereinbarung (bAV) - Direktversicherung",
        "Arbeitgeber: Brückner Maschinenbau GmbH & Co. KG, Industriestr. 9, 94315 Straubing",
        "Arbeitnehmer: Svetlana Ivanović-Huber",
        "Personal-Nr.: 4711\t\tKostenstelle: 310",
        "Gruppenvertrag Nr. GV-5512, Versicherungsnummer: 118-4471209-3",
        "Steuer-ID: 57549285017",
        "Sozialversicherungsnummer: 65 170839 J 003",
    ], ["Ivanović", "4711", "11844712093", "57549285017", "65170839J003"], unicode=True),

    F("steuer_id_varianten", [
        "Bitte teilen Sie uns Ihre steuerliche Identifikationsnummer mit.",
        "Steuer-Identifikationsnummer der versicherten Person: 57 549 285 017",
        "IdNr. (Ehegatte): 86 095 742 719",
        "Die Identifikationsnummer des Beitragszahlers lautet 62143789203.",
    ], ["57549285017", "86095742719", "62143789203"]),

    # --- Unfall --------------------------------------------------------------------------------------------
    F("unfallanzeige", [
        "Schadenanzeige Unfallversicherung",
        "Versicherte Person: Lennart Schönbrodt, geb. 17.06.2008",
        "Unfalltag: 08.02.2026, 15:30 Uhr - Unfallort: Skigebiet Sudelfeld, Bayrischzell",
        "Hergang: Sturz beim Skifahren, Begleitperson: Vater Ralf Schönbrodt, Tel. 0160 98765432",
        "Erstbehandelnde Ärztin: Dr. Ines Abendroth, Unfallklinik Murnau",
        "Invaliditätsgrad laut Gutachten: 1/7 Beinwert (Gliedertaxe)",
    ], ["Schönbrodt", "17.06.2008", "016098765432", "Abendroth"]),

    F("d_arzt_bericht", [
        "Durchgangsarztbericht",
        "Unfallversicherungsträger: BG BAU, Az. 4/2026/011873-7",
        "Name, Vorname des Versicherten: Okonkwo, Chidi Emmanuel",
        "Geburtsdatum: 04.11.1987\t\tTelefon: 0171 5550192",
        "Beschäftigt als Gerüstbauer seit 2019 bei Fa. Gerüstbau Pospiech, Dachau",
    ], ["Okonkwo", "Chidi", "04.11.1987", "01715550192", "Pospiech", "0118737"]),

    # --- Pflege --------------------------------------------------------------------------------------------
    F("pflegegrad_bescheid", [
        "Pflegekasse bei der AOK Bayern - Bescheid über die Feststellung des Pflegegrades",
        "Versicherte(r): Hildegard Ottersbach, geb. 02.11.1938",
        "Versichertennummer: H 987 654 323",
        "Gutachten des Medizinischen Dienstes vom 12.09.2025, Gutachten-Nr. MD-BY-2025-0447812",
        "Ergebnis: Pflegegrad 3 ab 01.08.2025",
        "Pflegeperson: Tochter Brigitte Ottersbach-Lechner, Rosenstr. 4, 91074 Herzogenaurach",
    ], ["Ottersbach", "02.11.1938", "H987654323", "MDBY20250447812", "Rosenstr. 4"]),

    F("md_gutachten_kopf", [
        "Gutachten zur Feststellung der Pflegebedürftigkeit gemäß SGB XI",
        "Auftragsnummer: 2025/BY/0817744",
        "Antragsteller: Wilhelm Gschwendtner\t\tGeb.-Dat.: 03.03.1934",
        "Wohnsituation: Seniorenwohnanlage Am Kurpark, Whg. 14, Kurallee 8, 83435 Bad Reichenhall",
        "Anwesend: Sohn Florian Gschwendtner (Bevollmächtigter)",
        "Gutachterin: Pflegefachkraft Monika Stadlhuber",
    ], ["Gschwendtner", "03.03.1934", "0817744", "Kurallee 8", "Stadlhuber"]),

    # --- Familienversicherung ------------------------------------------------------------------------------
    F("famvers_kinderliste", [
        "Fragebogen zur Familienversicherung",
        "Mitglied: Daniel Hufnagl, KVNR D407182534",
        "Angaben zu den Familienangehörigen",
        "Name, Vorname\t\tgeboren am\t\tVerwandtschaft",
        "Hufnagl, Katharina\t\t14.05.1986\t\tEhefrau",
        "Hufnagl, Mila\t\t03.08.2016\t\tTochter",
        "Hufnagl, Oskar\t\t21.11.2019\t\tSohn",
    ], ["Hufnagl", "D407182534", "14.05.1986", "Mila", "03.08.2016", "Oskar", "21.11.2019"], scans=SCAN),

    F("kinder_fliesstext", [
        "Mitversichert sind unsere Kinder Fenja (11.02.2015) und Bastian (30.06.2018) sowie",
        "Ida, geboren 2021.",
        "Kind 1: Fenja Leutgeb, 11.02.2015",
    ], ["Fenja", "11.02.2015", "Bastian", "30.06.2018", "2021", "Leutgeb"]),

    F("kinder_tabelle_ohne_kopf", [
        "Kinder:",
        "1.\t\tLiv Ostermeier\t\t09.09.2017",
        "2.\t\tJakob Ostermeier\t\t13.01.2020",
    ], ["Ostermeier", "09.09.2017", "13.01.2020"]),

    F("kinder_kopf_geb", [
        "Mitzuversichernde Personen",
        "Vorname\t\tNachname\t\tGeb.",
        "Theo\t\tWaldbrunner\t\t04.04.2018",
        "Greta\t\tWaldbrunner\t\t27.12.2021",
    ], ["Theo", "Waldbrunner", "04.04.2018", "Greta", "27.12.2021"]),

    F("pflegezusatz_tabelle", [
        "Pflegezusatzversicherung - Versicherte Personen",
        "Vers. Person\t\tGeb.-Datum\t\tBeitrag",
        "Holzapfel, Margit\t\t08.08.1961\t\t48,20 €",
        "Holzapfel, Hubert\t\t26.01.1959\t\t52,10 €",
    ], ["Holzapfel", "Margit", "08.08.1961", "26.01.1959"]),

    # --- Reise ---------------------------------------------------------------------------------------------
    F("reise_buchung_pnr", [
        "Reisebestätigung / Rechnung",
        "Reiseanmelder: Herr Detlef Kranich",
        "Vorgangsnummer: 7740-2291\t\tBuchungsdatum: 14.01.2026",
        "Reservierungscode (PNR): 6XK2QF",
        "Teilnehmer: 1. Kranich, Detlef  2. Kranich, Birgit  3. Kranich, Jona (Kind, 12 J.)",
        "Flug: LH 1838 München - Palma, 12.07.2026, 06:40 Uhr",
        "Hotel: Hotel Cala Ratjada Mar, 7 Nächte, Doppelzimmer Meerblick",
    ], ["Kranich", "77402291", "6XK2QF", "Birgit", "Jona"], scans=SCAN),

    F("eticket_airline", [
        "ELECTRONIC TICKET ITINERARY RECEIPT",
        "PASSENGER: KRANICH/BIRGIT MRS",
        "TICKET NUMBER: 220 2345678901",
        "BOOKING REFERENCE: 6XK2QF",
        "FREQUENT FLYER: LH 992004471123",
        "LH 1838 MUC-PMI 12JUL 0640 OK",
    ], ["KRANICH", "BIRGIT", "2202345678901", "6XK2QF", "992004471123"]),

    F("auslandsarzt_englisch", [
        "Clinica San Pere - Invoice",
        "Patient name: Henrike von Thaden",
        "Date of birth: 12/05/1975",
        "Passport No.: C4J7X9K21",
        "Patient ID: 0098812\t\tInvoice No.: F-2026/03341",
        "Insurance: HanseMerkur Reiseversicherung, Policy No. RK-118844-26",
    ], ["Thaden", "12/05/1975", "C4J7X9K21", "0098812", "2026/03341", "RK11884426"]),

    F("reise_storno", [
        "Stornokostenrechnung zur Buchungsnummer 43188276",
        "Kunde: Frau Elfriede Mäusbacher-Toth, Kirchplatz 2, 84489 Burghausen",
        "Grund: akute Erkrankung der Mitreisenden Ruth Toth (Attest Dr. Böhm-Kessler)",
        "Stornogebühr 80 % = 2.236,00 EUR",
    ], ["43188276", "Mäusbacher", "Kirchplatz 2", "Ruth", "Toth", "Böhm"]),

    F("reisepass_angaben", [
        "Angaben zum Reisepass (für die Rückholung)",
        "Reisepass-Nr.: C01X00T47\t\tgültig bis: 06/2031",
        "Personalausweis-Nr. der Mitreisenden: L01X00T47",
        "Ausstellende Behörde: Stadt Augsburg, Staatsangehörigkeit: deutsch",
    ], ["C01X00T47", "L01X00T47"]),

    F("ktg_au_antrag", [
        "Krankentagegeld - Leistungsantrag",
        "Versicherungsnehmer: Mehmet Arslan-Bauer",
        "Arbeitsunfähig seit: 05.01.2026, voraussichtlich bis 15.02.2026",
        "Arbeitgeber: Spedition Hofbauer & Söhne GmbH",
        "Personalnummer beim Arbeitgeber: 20-4471",
        "Bankverbindung für die Erstattung: DE45 7435 0000 0004 4711 09",
    ], ["Arslan", "Hofbauer", "204471", "DE45743500000004471109"]),

    # --- Fehlerklassen gezielt -----------------------------------------------------------------------------
    F("zwischenwoerter", [
        "Versichertennummer bei der Pflegekasse: 4711 0815 33",
        "Name der pflegenden Angehörigen: Roswitha Kamml",
        "Geburtsdatum des zweiten Kindes: 18.10.2020",
        "Rentenversicherungsnummer der Pflegeperson: 53 030362 K 513",
        "Anschrift der Pflegeperson: Hauptstr. 21, 94469 Deggendorf",
    ], ["4711081533", "Kamml", "18.10.2020", "53030362K513", "Hauptstr. 21"]),

    F("rollen_unbekannt", [
        "Stammversicherter: Albin Zwickl",
        "Rechnungsempfänger: Theres Obermüller-Sagstetter",
        "Leistungsberechtigter: Konrad Hiltl",
        "Beihilfeberechtigte: Annemarie Zierngibl",
        "Reiseteilnehmer: Gunnar Lüttjohann",
    ], ["Zwickl", "Obermüller", "Hiltl", "Zierngibl", "Lüttjohann"]),

    F("geburtsjahr_alter", [
        "Risikolebensversicherung - Angebot",
        "Geburtsjahr: 1983\t\tEintrittsalter: 42",
        "Mitversicherter Ehemann: Jahrgang 1958",
        "Alter der versicherten Person bei Beginn: 42 Jahre",
    ], ["1983", "1958"]),

    F("sterbefall_lv", [
        "Leistungsantrag im Todesfall",
        "Verstorbene versicherte Person: Ernst Rauchenecker, geb. 10.12.1949,",
        "verstorben am 03.02.2026 in Passau",
        "Sterbeurkunde: Standesamt Passau, Registernummer S 145/2026",
        "Anspruchsteller: Witwe Liselotte Rauchenecker; Erbschein Amtsgericht Passau, Az. VI 211/26",
    ], ["Rauchenecker", "10.12.1949", "03.02.2026", "S145/2026", "Liselotte", "VI211/26"]),

    F("email_zahnzusatz", [
        "Von: Kröger, Marit <marit.kroeger@web.de>",
        "Gesendet: Montag, 3. November 2026 09:14",
        "An: info@makler-steinbeis.de",
        "Betreff: Zahnzusatz für meinen Sohn Lasse (geb. 07.07.2015)",
        "Hallo Herr Steinbeis, anbei der HKP Nr. 2026-0341 von Dr. Fenske.",
        "Viele Grüße, Marit",
    ], ["Kröger", "marit.kroeger", "Lasse", "07.07.2015", "20260341", "Fenske", "Marit"]),

    F("formularfelder_antrag", [
        "Antrag Risikolebensversicherung (ausfüllbares Formular)",
        "Name, Vorname der versicherten Person:",
        "Geburtsdatum:",
        "Krankenversichertennummer:",
        "Steuer-ID:",
        "Bezugsberechtigter im Todesfall:",
    ], ["Pfisterer", "Annika", "19.04.1990", "P610293847", "86095742719", "Ole"],
        felder=(feld("Text1", 1, "Pfisterer, Annika"), feld("Text2", 2, "19.04.1990"),
                feld("Text3", 3, "P610293847"), feld("Text4", 4, "86095742719"),
                feld("Text5", 5, "Ole Pfisterer (Ehemann)"))),

    # --- Über-Schwärzung -----------------------------------------------------------------------------------
    F("eponyme_diagnosen", [
        "Gesundheitsfragen - Antworten der versicherten Person",
        "Vorerkrankungen: Morbus Crohn seit 2015, Hashimoto-Thyreoiditis, Morbus Bechterew ausgeschlossen",
        "Familienanamnese: Mutter Morbus Parkinson; Vater Alzheimer-Demenz",
        "Behandlung: Baker-Zyste rechts, Dupuytren-Kontraktur links, Morbus Scheuermann",
    ], []),

    F("organisationen_ueber", [
        "Kopie an: HanseMerkur Krankenversicherung AG, Würzburger Versicherungs-AG, Medicproof GmbH,",
        "Deutsche Rentenversicherung Knappschaft-Bahn-See, Familienkasse Bayern Süd,",
        "Bayerische Beamtenkrankenkasse, Postbeamtenkrankenkasse, Barmenia Krankenversicherung,",
        "Landesamt für Finanzen - Dienststelle Regensburg - Bezügestelle Beihilfe",
    ], []),

    F("reiseverlauf_ueber", [
        "Reiseverlauf: 12.07.2026 Flug EW 7582 Köln/Bonn - Heraklion, Transfer zum Hotel",
        "Hotel Kalimera Kriti, Analipsi, All inclusive, Zimmer mit Meerblick",
        "Rückflug: 19.07.2026 EW 7583",
        "Reiseveranstalter: DERTOUR Deutschland GmbH, vermittelt durch Reisebüro Sonnenklar",
    ], []),

    F("behandlungsdaten_nach_namen", [
        "Angaben zu Arztbesuchen der letzten 5 Jahre",
        "Dr. med. Ralf Ebner, 14.02.2019: Gastroskopie ohne Befund",
        "Dr. Ute Kranzfelder, 03.11.2012: Meniskusoperation links",
        "Physiotherapie Hammerl, 2021: 12 Behandlungen Lendenwirbelsäule",
    ], ["Ebner", "Kranzfelder", "Hammerl"]),
]
