# Domänen-Probe Sach/Haftpflicht/Wohnen/Recht – Runde 2: Lecks aus Runde 1 ohne fremde Fehlalarme nachstellen,
# neue Schreibweisen, Über-Schwärzung (eigene Fälle, erfundene Namen und Nummern)
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


SN_PREIS = [
    "Stehlgutliste zur Hausratschadenanzeige",
    "Gegenstand\t\tKaufpreis\t\tSeriennummer",
    "Spiegelreflexkamera Nikon D7500\t\t1.099,00 EUR\t\t3049217",
    "Objektiv Nikkor 18-140 mm\t\t449,00 EUR\t\t62231874",
    "Armbanduhr\t\t895,00 EUR\t\t4521",
    "Spielkonsole Sony PS5\t\t549,00 EUR\t\tE31K8TQ",
]

FAELLE = [
    # --- stille Lecks aus Runde 1 ohne fremden Verdacht im selben Dokument -----------------------------------------
    F("rs_insachen_isoliert", [
        "Dr. Moosreiner & Kollegen",
        "Ihr VN: Josef Kranzbühler",
        "Versicherungsschein-Nr.: RS-4471122-03",
        "In Sachen Kranzbühler ./. Felsberger",
        "wegen Mietminderung",
        "Sehr geehrte Damen und Herren,",
        "der Vermieter Felsberger verweigert die Beseitigung des Schimmels im Schlafzimmer.",
        "Wir bitten um Deckungszusage für die erste Instanz.",
        "Mit freundlichen Grüßen",
        "Dr. Ulrike Moosreiner",
    ], ["Felsberger", "Kranzbühler"]),
    F("rs_mehrdeutige_namen", [
        "Deckungsanfrage Rechtsschutz",
        "Ihr VN: Josef Kranzbühler, Vers.-Nr. RS-4471122-03",
        "In der Mietsache Kranzbühler ./. Engel",
        "Die Vermieterin Engel hat die Nebenkostenabrechnung 2023 bis heute nicht vorgelegt.",
    ], ["Engel", "Kranzbühler"]),
    F("rs_aktenzeichen_fliesstext", [
        "Kostenrechnung zur Rechtsschutzsache Ihres VN Josef Kranzbühler",
        "Das Verfahren 3 C 456/24 vor dem AG Ebersberg wurde durch Vergleich beendet.",
        "Die Staatsanwaltschaft Traunstein hat das Verfahren 210 Js 345/24 eingestellt.",
    ], ["3 C 456/24", "345/24", "Kranzbühler"]),
    F("gericht_beschluss_unterschrift", [
        "Amtsgericht Ebersberg",
        "Geschäftsnummer: 3 C 456/24",
        "Beschluss",
        "Der Streitwert wird auf 2.400,00 EUR festgesetzt.",
        "Hartlieb",
        "Richterin am Amtsgericht",
        "Ausgefertigt",
        "Eibl, JAng",
        "Urkundsbeamtin der Geschäftsstelle",
    ], ["Hartlieb", "Eibl", "3 C 456/24"]),
    F("polizei_rang_fliesstext", [
        "Polizeiinspektion Poing",
        "Vorgangsnummer: BY8513-004711-25/1",
        "Ihre Anzeige wurde von POK Zwickl aufgenommen.",
        "Rückfragen richten Sie bitte an KHKin Sedlmayr (K 33).",
    ], ["Zwickl", "Sedlmayr", "BY8513-004711-25/1"]),
    F("abkuerzung_punkt_strich_nr", [
        "Eingangsbestätigung Fahrraddiebstahl",
        "Vorg.-Nr. 123/25",
        "Ser.-Nr. des Rahmens: WTU 4471",
        "Mdt.-Nr. 1024",
    ], ["123/25", "WTU4471", "1024"]),
    F("tier_kennzeichnung_isoliert", [
        "Antrag Hundekrankenversicherung",
        "Tierhalterin: Sabine Ollenbrock",
        "Kennzeichnung des Hundes",
        "Tätowierung (li. Ohr): ZB 2187",
        "Tätowiernummer Zuchtbuch: VDH 3366",
        "Hundesteuermarke Nr. 0386",
    ], ["ZB 2187", "VDH 3366", "0386", "Ollenbrock"]),
    F("laptop_isoliert", [
        "Diebstahlanzeige - Angaben zum Gerät",
        "Notebook: Dell Latitude",
        "Service-Tag: 7XK2Q3F",
        "MAC-Adresse: 3C:22:FB:9A:1B:7E",
    ], ["7XK2Q3F", "3C22FB9A1B7E"]),
    F("gewerbe_isoliert", [
        "Antrag Betriebshaftpflicht",
        "Inhaber: Florian Sedlmayr",
        "Handelsregister: Amtsgericht München HRA 112233",
        "USt-IdNr.: DE287654321",
    ], ["Sedlmayr", "HRA 112233", "DE287654321"]),
    F("phv_nachbar_isoliert", [
        "Schadenanzeige Privathaftpflicht",
        "Mein Sohn schoss beim Fußballspielen den Ball in das Wohnzimmerfenster unseres Nachbarn Felsberger.",
        "Das Glas ist gesprungen, der Glaser Eibl hat ein Angebot über 640,00 EUR erstellt.",
    ], ["Felsberger", "Eibl"]),
    F("name_des_tierhalters", [
        "Unfallmeldung Tierhalterhaftpflicht",
        "Name des Tierhalters: Felsberger",
        "Name der Geschädigten: Ollenbrock",
    ], ["Felsberger", "Ollenbrock"]),
    F("mieter_im_satz", [
        "Schadenmeldung Leitungswasser",
        "In der Wohnung von Rauchenberger (2. OG) ist der Zulaufschlauch der Waschmaschine geplatzt.",
        "Bei Felsberger im 1. OG ist das Wasser durch die Decke getreten.",
    ], ["Rauchenberger", "Felsberger"]),
    F("anschrift_bei_untermieter", [
        "Änderung der Korrespondenzanschrift",
        "Versicherungsnehmer: Leon Wittkamp",
        "Neue Anschrift: Lindenweg 4 (bei Felsberger), 82008 Unterhaching",
    ], ["Felsberger", "Lindenweg 4", "Wittkamp"]),
    # --- Tabelle: Seriennummern hinter einer Preisspalte ------------------------------------------------------------
    F("hausrat_seriennr_mit_preis", SN_PREIS, ["3049217", "62231874", "4521", "E31K8TQ"]),
    F("hausrat_sn_ohne_preis", [
        "Stehlgutliste zur Hausratschadenanzeige",
        "Gegenstand\t\tS/N",
        "Spiegelreflexkamera Nikon D7500\t\t3049217",
        "Objektiv Nikkor 18-140 mm\t\t62231874",
    ], ["3049217", "62231874"]),
    F("hausrat_preis_dann_imei", [
        "Schadenmeldung Handyversicherung - Diebstahl",
        "Gerät\t\tKaufpreis\t\tIMEI",
        "Smartphone Galaxy S23\t\t899,00 EUR\t\t356938035643809",
        "Tablet Galaxy Tab S9\t\t749,00 EUR\t\t352099001761481",
    ], ["356938035643809", "352099001761481"]),
    # --- Kundenanschrift unter Titel- bzw. Versichererzeile ---------------------------------------------------------
    F("anschrift_unter_titel_geschaedigter", [
        "Schadenmeldung Privathaftpflichtversicherung",
        "Geschädigter: Rainer Felsberger, Lindenweg 6, 82008 Unterhaching",
        "Schadentag: 14.08.2025",
    ], ["Felsberger", "Lindenweg 6", "82008"]),
    F("anschrift_unter_versicherer", [
        "ARAG SE - Schadenmeldung Rechtsschutz",
        "Vermieter: Rainer Felsberger, Lindenweg 6, 82008 Unterhaching",
        "Rechtsgebiet: Mietrecht",
    ], ["Felsberger", "Lindenweg 6", "82008"]),
    F("anschrift_unter_titel_halter_kontrolle", [
        "Antrag Hundekrankenversicherung",
        "Versicherungsnehmerin: Sabine Ollenbrock, Am Mühlbach 3, 85570 Markt Schwaben",
    ], ["Ollenbrock", "Am Mühlbach 3", "85570"]),
    # --- Formularfelder ---------------------------------------------------------------------------------------------
    F("formular_tierantrag", [
        "Antrag Tierkrankenversicherung (Formular)",
        "Name Tierhalter:",
        "Tätowierung:",
        "Steuermarke:",
    ], ["Ollenbrock", "ZB 2187", "0386"],
      felder=(("Tierhalter_Name", (200, 90, 400, 106), "Ollenbrock"),
              ("Taetowierung", (200, 108, 400, 124), "ZB 2187"),
              ("Steuermarke", (200, 126, 400, 142), "0386"))),
    # --- Über-Schwärzung -------------------------------------------------------------------------------------------
    F("tier_rassen_ueber", [
        "Tierkrankenversicherung - versicherte Tiere",
        "Tier\t\tRasse\t\tGeschlecht",
        "Hund\t\tBerner Sennenhund\t\tRüde",
        "Hund\t\tCavalier King Charles Spaniel\t\tHündin",
        "Hund\t\tDobermann\t\tRüde",
        "Katze\t\tMaine Coon\t\tKater",
        "Versicherungsnehmer: Leon Wittkamp",
    ], ["Wittkamp"]),
    F("heizung_marken_ueber", [
        "Leitungswasserschaden - Kostenvoranschlag Heizung/Sanitär",
        "Wärmeerzeuger: Viessmann Vitodens 200-W, Baujahr 2012",
        "Alternativ: Wolf CGB-2-20 oder Junkers Cerapur 9000i",
        "Warmwasser: Stiebel Eltron DHB-E 18 Sli",
        "Armaturen: Hansgrohe Talis, Grohe Eurosmart",
        "Kunde: Leon Wittkamp",
    ], ["Wittkamp"]),
    F("behoerden_ueber", [
        "Nachweise zur Schadenmeldung",
        "Bestätigung des Landratsamts Ebersberg über die Hundesteuer liegt bei.",
        "Registrierung des Hundes bei TASSO e.V. und FINDEFIX.",
        "Einspeisezusage der Bayernwerk Netz GmbH und Registrierung im Marktstammdatenregister der Bundesnetzagentur.",
        "Kunde: Leon Wittkamp",
    ], ["Wittkamp"]),
    # --- Scans (Stichprobe) ----------------------------------------------------------------------------------------
    F("scan_hausrat_seriennr_mit_preis", SN_PREIS, ["3049217", "62231874", "4521", "E31K8TQ"],
      scans=((200, 0.0, None),), text=False),
]
