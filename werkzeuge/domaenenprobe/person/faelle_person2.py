# Domänen-Probe Sparte Personenversicherungen/Gesundheit, Runde 2: Nachbarn der Befunde aus Runde 1
# (Fehlerklassen eingrenzen; erfundene Personen und Nummern)
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


SCAN = ((200, 0.0, None),)

FAELLE = [
    # --- A: Nummern mit Tausenderpunkten hinter Kennungs-Etiketten ----------------------------------------------
    F("punkt_kundennr", [
        "Barmenia Krankenversicherung AG - Beitragsanpassung zum 01.01.2027",
        "Kundennummer: 4.711.208",
        "Versicherungsschein-Nr. 2.345.671",
        "Kd.-Nr. 12.345.678",
    ], ["4711208", "2345671", "12345678"], scans=SCAN),

    F("punkt_mischformen", [
        "Vers.-Nr. 47.897.336.2",
        "Vertragsnummer 1.234.567-8",
        "Mitgliedsnummer 123.456.789-01",
    ], ["478973362", "12345678", "12345678901"]),

    F("punkt_tabelle", [
        "Versicherte Personen",
        "Name\t\tVersicherungsnummer\t\tTarif",
        "Hans Obermaier\t\t123.456.789\t\tKS 2",
        "Rosa Obermaier\t\t123.456.790\t\tKS 2",
    ], ["Obermaier", "123456789", "123456790"]),

    # --- B: Geburtsdaten von Kindern ohne Stichwort -------------------------------------------------------------
    F("kind_name_komma", [
        "Kind 2: Bastian Leutgeb, 30.06.2018",
        "Mitversicherte Person: Oskar Hufnagl, 21.11.2019",
    ], ["Leutgeb", "30.06.2018", "Hufnagl", "21.11.2019"]),

    F("kinder_klammer_liste", [
        "Familienversicherung - mitversicherte Angehörige",
        "Kinder: Liv (09.09.2017), Jakob (13.01.2020)",
    ], ["Liv", "09.09.2017", "Jakob", "13.01.2020"], scans=SCAN),

    F("reisende_liste", [
        "Reiserücktrittsversicherung - versicherte Reisende",
        "Reisende: Kranich, Detlef, 12.04.1969; Kranich, Jona, 17.02.2014;",
        "Kranich, Emma, 05.05.2019",
    ], ["Kranich", "12.04.1969", "Jona", "17.02.2014", "Emma", "05.05.2019"]),

    F("kinder_tabelle_geburtstag", [
        "Kinder (Zahnzusatz Junior)",
        "Name\t\tGeburtstag\t\tTarif",
        "Ella Brandstetter\t\t14.03.2018\t\tZahn Junior",
        "Paul Brandstetter\t\t02.12.2020\t\tZahn Junior",
    ], ["Brandstetter", "14.03.2018", "02.12.2020"]),

    F("kinder_tabelle_ohne_kopf2", [
        "Kinder:",
        "1.\t\tLea Brandl\t\t09.09.2013",
        "2.\t\tMax Brandl\t\t13.01.2015",
    ], ["Brandl", "09.09.2013", "13.01.2015"]),

    F("neugeborenes", [
        "Kindernachversicherung - Anmeldung eines Neugeborenen",
        "Geburt des Kindes Emil am 02.10.2026 in der Frauenklinik Rosenheim",
        "Vorname des Kindes: Emil, Familienname: Hufnagl",
    ], ["02.10.2026", "Emil", "Hufnagl"]),

    # --- C: Geburtsjahr -----------------------------------------------------------------------------------------
    F("geburtsjahr_varianten", [
        "Geburtsjahr 1983",
        "Geb.-Jahr: 1979",
        "Geburtsjahr des Kindes: 2017",
        "Jg. 1961",
    ], ["1983", "1979", "2017", "1961"]),

    # --- D: Buchungscodes ohne Ziffernmenge ---------------------------------------------------------------------
    F("buchungscodes", [
        "Buchungscode: 6XK2QF",
        "Filekey: K7QXMZ",
        "PNR: 8HJ4TW",
        "Buchungsreferenz: 4Z9K7L",
    ], ["6XK2QF", "K7QXMZ", "8HJ4TW", "4Z9K7L"]),

    # --- E: Zwischenwörter mit kurzem Wert ----------------------------------------------------------------------
    F("zwischenwort_kurz", [
        "Personalnummer beim Arbeitgeber: 4711",
        "Mitgliedsnummer bei der Ärzteversorgung: 8821",
        "Versicherungsnummer des Ehepartners: KV-0815",
    ], ["4711", "8821", "KV0815"]),

    # --- F: Anschrift des Rechnungsempfängers unter einem Firmenkopf --------------------------------------------
    F("re_empfaenger_luecke", [
        "PVS Südbayern GmbH, Postfach 20 11 33, 80011 München",
        "",
        "Rechnungsempfänger: Ilse Wohlgemuth-Brandl, Am Mühlbach 12, 83646 Bad Tölz",
        "Rechnungsnummer: 2024-118733",
    ], ["Wohlgemuth", "Am Mühlbach 12", "83646", "2024118733"]),

    F("re_empfaenger_patientin", [
        "PVS Südbayern GmbH, Postfach 20 11 33, 80011 München",
        "Patientin: Ilse Wohlgemuth-Brandl, Am Mühlbach 12, 83646 Bad Tölz",
        "Rechnungsnummer: 2024-118733",
    ], ["Wohlgemuth", "Am Mühlbach 12", "83646", "2024118733"]),

    F("leistungsempfaenger_klinik", [
        "Kreisklinik Wolfratshausen gGmbH",
        "Kostenträger: Bayerische Beamtenkrankenkasse",
        "Hauptversicherter: Konrad Hiltl, Waldweg 3, 82515 Wolfratshausen",
    ], ["Hiltl", "Waldweg 3", "82515"]),

    # --- G: Feld- und Fachwörter als Namen ----------------------------------------------------------------------
    F("etikettwoerter_als_namen", [
        "Hauptversicherter: Albin Zwickl",
        "Überweiser: Dr. Ralf Ebner",
        "Bezugsperson: Tochter Imke Brodersen",
        "Bewohnerin: Gertrud Ottersbach, Wohnbereich 2, Zimmer 214",
        "Rehabilitand: Jörg Pfeiffer-Nolte",
    ], ["Zwickl", "Ebner", "Brodersen", "Ottersbach", "Pfeiffer"]),

    F("fachwoerter_als_namen", [
        "Diagnosen:",
        "Distale Radiusfraktur links, konservativ versorgt",
        "Chronische Lumbalgie seit 2019",
        "Rezidivierende depressive Episode, gegenwärtig remittiert",
        "Arterielle Hypertonie, medikamentös eingestellt",
        "Beidseitige Gonarthrose Grad II",
    ], []),

    # --- I: Gebührenziffern / PZN -------------------------------------------------------------------------------
    F("goae_ziffer_spalte", [
        "Rechnung Facharztpraxis Orthopädie",
        "Datum\t\tGOÄ-Ziffer\t\tBetrag",
        "02.09.2025\t\t5855\t\t53,62 €",
        "02.09.2025\t\t3511\t\t5,36 €",
        "Datum\t\tGeb.-Nr.\t\tBetrag",
        "09.09.2025\t\t0410\t\t19,82 €",
    ], []),

    F("apotheke_pzn", [
        "Apothekenquittung (Privatrezept)",
        "PZN\t\tArtikel\t\tPreis",
        "01126111\t\tIbuprofen 600 mg 50 St.\t\t12,49 €",
        "04884569\t\tPantoprazol 20 mg 28 St.\t\t9,98 €",
    ], []),

    # --- J: Unfallort -------------------------------------------------------------------------------------------
    F("unfallort_varianten", [
        "Unfallort: Sporthalle der Grundschule Haar",
        "Ort des Unfalls: Treppenhaus, Lindenweg 14, 82008 Unterhaching",
        "Unfallstelle: Skipiste am Sudelfeld, Bayrischzell",
    ], ["Lindenweg 14"]),

    # --- K: Namensformat der Fluggesellschaften -----------------------------------------------------------------
    F("airline_namensformat", [
        "Passagier: KRANICH/DETLEF MR",
        "Name: OSTERKAMP/JULIANE MS",
    ], ["KRANICH", "DETLEF", "OSTERKAMP", "JULIANE"]),

    # --- X: SV-Nummer-Schreibweisen -----------------------------------------------------------------------------
    F("svnr_schreibweisen", [
        "SV-Nummer: 12150385M003",
        "Rentenversicherungsnummer: 65-170839-J-003",
        "Versicherungsnummer 53 030362 K 51 3",
    ], ["12150385M003", "65170839J003", "53030362K513"]),

    # --- AA: Mitarbeiterliste bAV -------------------------------------------------------------------------------
    F("bav_mitarbeiterliste", [
        "Gruppenvertrag bAV - Mitarbeiterliste zum 01.01.2027",
        "Name, Vorname\t\tPers.-Nr.\t\tGeb.-Datum",
        "Ivanović-Huber, Svetlana\t\t4711\t\t12.03.1988",
        "Bauer, Mehmet\t\t4802\t\t30.09.1979",
        "Oyelaran, Tobi\t\t5120\t\t01.02.1995",
    ], ["Ivanović", "4711", "12.03.1988", "4802", "30.09.1979", "Oyelaran", "5120", "01.02.1995"], unicode=True),
]

# --- Nachprüfung (Runde 2b): Fälle einzeln, ohne fremde Verdachtsstellen auf derselben Seite -------------------
FAELLE += [
    F("buchungscodes_isoliert", [
        "Ihre Reisebuchung",
        "Filekey: K7QXMZ",
        "Buchungsreferenz: 4Z9K7L",
    ], ["K7QXMZ", "4Z9K7L"]),

    F("neugeborenes_isoliert", [
        "Kindernachversicherung",
        "Geburt des Kindes am 02.10.2026",
        "Name des Kindes: Emil Hufnagl",
    ], ["02.10.2026", "Emil", "Hufnagl"]),

    F("mitreisende_kinder_nv", [
        "Mitreisende Kinder: Kranich, Emma, 05.05.2019; Kranich, Jonas, 17.02.2016",
    ], ["Kranich", "Emma", "05.05.2019", "Jonas", "17.02.2016"]),

    F("beihilfe_belegliste", [
        "Aufstellung der Aufwendungen",
        "Nr.\t\tName der Person\t\tBetrag",
        "1\t\tVroni\t\t312,45 €",
        "2\t\tXaver\t\t48,20 €",
        "3\t\tKorbinian\t\t96,00 €",
    ], ["Vroni", "Xaver", "Korbinian"]),

    F("nachname_wie_diagnose", [
        "Leistungsantrag Schwere-Krankheiten-Vorsorge",
        "Versicherte Person: Manfred Krebs, geb. 19.03.1961",
        "Diagnose: Bronchialkarzinom (Lungenkrebs), Erstdiagnose 08/2026",
        "Sehr geehrter Herr Krebs, wir bestätigen den Eingang Ihres Antrags.",
        "Mitversichert: Ehefrau Gisela Kropf, Diagnose Struma (Kropf) 2019",
    ], ["Manfred", "19.03.1961", "Gisela"]),
]
