# Gegenprüfung Sparte Person, Teil 1: stille Lecks (Befunde 1-7, 11). Erfundene Personen und Nummern.
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


SCAN = ((200, 0.0, None),)

FAELLE = [
    # --- B1: Kennungen mit Tausenderpunkten hinter Kennungs-Etikett ------------------------------------------
    F("b1_gleich", [
        "Versicherungsnummer: 123.456.789",
        "Kundennummer: 4.711.208",
    ], ["123456789", "4711208"]),
    F("b1_brief", [
        "Isar Krankenversicherung AG - Beitragsanpassung zum 01.01.2027",
        "Ihre Mitgliedsnummer: 7.654.321",
        "Sehr geehrter Herr Lohmeier,",
        "zu Ihrem Vertrag Nr. 12.345.678 erhalten Sie die neue Beitragsübersicht.",
    ], ["7654321", "12345678", "Lohmeier"]),
    F("b1_ohne_doppelpunkt", [
        "Lebensversicherung - Standmitteilung 2026",
        "Versicherungsschein-Nr. 3.456.782",
        "Vers.-Nr. 300.447.112",
    ], ["3456782", "300447112"]),
    F("b1_kontrolle_betraege", [
        "Versicherungssumme: 150.000 EUR",
        "Sterbegeld: 5.000",
        "Jahresbeitrag: 1.234,56 EUR",
        "Mitgliedsnummer: 2.468.135",
    ], ["2468135"]),
    F("b1_scan", [
        "Isar Krankenversicherung AG",
        "Kundennummer: 4.711.209",
        "Versicherungsnummer: 123.456.788",
    ], ["4711209", "123456788"], scans=SCAN, text=False),

    # --- B2: Geburtsdaten von Kindern ohne Stichwort ---------------------------------------------------------
    F("b2_gleich", [
        "Kind 2: Bastian Leutgeb, 30.06.2018",
        "Mitversicherte Person: Oskar Hufnagl, 21.11.2019",
    ], ["30.06.2018", "21.11.2019", "Leutgeb", "Hufnagl"]),
    F("b2_tochter_komma", [
        "Familienversicherung - Änderungsmeldung",
        "Tochter: Mia Schöllhorn, 14.08.2017",
    ], ["14.08.2017", "Schöllhorn"]),
    F("b2_sohn_klammer", [
        "Zahnzusatzversicherung Junior",
        "Mitversichert ist unser Sohn Lukas Schöllhorn (04.03.2016).",
    ], ["04.03.2016", "Schöllhorn"]),
    F("b2_vornamen_klammer", [
        "Familienversicherung - mitversicherte Angehörige",
        "Kinder: Ben (02.05.2019) und Lotta (17.10.2021)",
    ], ["02.05.2019", "17.10.2021", "Lotta"]),
    F("b2_nachname_vorname", [
        "Reiserücktrittsversicherung",
        "Mitreisendes Kind: Brenner, Lina, 05.05.2019",
    ], ["05.05.2019", "Brenner", "Lina"]),
    F("b2_kontrolle_erwachsen", [
        "Ehefrau: Petra Schöllhorn, 12.05.1984",
        "Kind: Lea Brandl, 09.09.2014",
    ], ["12.05.1984", "09.09.2014"]),
    F("b2_scan", [
        "Familienversicherung",
        "Kinder: Liv (09.09.2017), Jakob (13.01.2020)",
        "Tochter: Mia Schöllhorn, 14.08.2017",
    ], ["09.09.2017", "13.01.2020", "14.08.2017"], scans=SCAN, text=False),

    # --- B3: Kinderliste mit Tabstopps ohne Spaltenkopf ------------------------------------------------------
    F("b3_gleich", [
        "Kinder:",
        "1.\t\tLiv Ostermeier\t\t09.09.2017",
        "2.\t\tJakob Ostermeier\t\t13.01.2020",
    ], ["09.09.2017", "13.01.2020"]),
    F("b3_ohne_nummer", [
        "Mitzuversichernde Kinder:",
        "Lina Brenner\t\t05.05.2019\t\tTochter",
        "Jonte Brenner\t\t22.07.2021\t\tSohn",
    ], ["05.05.2019", "22.07.2021"]),
    F("b3_erwachsene", [
        "Versicherte Personen:",
        "1.\t\tPetra Rieder\t\t12.05.1984",
        "2.\t\tHans Rieder\t\t03.07.1979",
    ], ["12.05.1984", "03.07.1979"]),

    # --- B4: Geburt eines Neugeborenen ------------------------------------------------------------------------
    F("b4_gleich", [
        "Kindernachversicherung",
        "Geburt des Kindes am 02.10.2026",
        "Name des Kindes: Emil Hufnagl",
    ], ["02.10.2026"]),
    F("b4_mail", [
        "Betreff: Kindernachversicherung",
        "hiermit zeige ich die Geburt unserer Tochter am 14.09.2026 an",
        "und bitte um Aufnahme in meinen Tarif.",
    ], ["14.09.2026"]),
    F("b4_entbindung", [
        "Anmeldung zur Kindernachversicherung",
        "Entbindung am 21.08.2026 im Klinikum Traunstein",
    ], ["21.08.2026"]),

    # --- B5: Geburtsjahr ---------------------------------------------------------------------------------------
    F("b5_gleich", [
        "Risikolebensversicherung - Angebot",
        "Geburtsjahr: 1983\t\tEintrittsalter: 43",
    ], ["1983"]),
    F("b5_var", [
        "Berufsunfähigkeitsversicherung - Angebot",
        "Geburtsjahr der versicherten Person: 1979",
        "Beruf: Industriekauffrau",
    ], ["1979"]),

    # --- B6/B11: Zwischenwörter zwischen Etikett und Wert -----------------------------------------------------
    F("b6_gleich", [
        "Personalnummer beim Arbeitgeber: 4711",
        "Mitgliedsnummer bei der Ärzteversorgung: 8821",
        "Versicherungsnummer des Ehepartners: KV-0815",
    ], ["4711", "8821", "KV0815"]),
    F("b6_var", [
        "Krankentagegeld - Leistungsantrag",
        "Personalnummer des Arbeitnehmers: 3318",
        "Mitgliedsnummer im Versorgungswerk: 5527",
    ], ["3318", "5527"]),
    F("b6_kontrolle", [
        "Personalnummer: 4712",
        "Mitgliedsnummer: 8822",
    ], ["4712", "8822"]),
    F("b11_lang", [
        "Versichertennummer bei der Pflegekasse: 4711 0815 33",
    ], ["4711081533"]),

    # --- B7: Buchungscodes -------------------------------------------------------------------------------------
    F("b7_gleich", [
        "Ihre Reisebuchung",
        "Filekey: K7QXMZ",
        "Buchungsreferenz: 4Z9K7L",
    ], ["K7QXMZ", "4Z9K7L"]),
    F("b7_reservierungscode", [
        "Buchungsbestätigung",
        "Reservierungscode: 7HQ2LM",
    ], ["7HQ2LM"]),
    F("b7_booking_reference", [
        "Booking confirmation",
        "Booking reference: Q8ZP4M",
    ], ["Q8ZP4M"]),
    F("b7_buchungsnummer", [
        "Reiseunterlagen",
        "Buchungsnummer: 6XK2QF",
    ], ["6XK2QF"]),
    F("b7_lautet", [
        "Stornierung Ihrer Reise",
        "Ihr Buchungscode lautet K4RT9P.",
    ], ["K4RT9P"]),
]
