# Gegenprüfung Sach – Teil 2 (Befunde 11–19): je Befund die gleiche Zeile isoliert und eine leicht andere, realistische
# Schreibweise. Erfundene Namen und Nummern.
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


FAELLE = [
    # --- B11 Kundenanschrift unter Titelzeile "…versicherung" / Versicherername ------------------------------------
    F("b11_gleich_tierhalter", [
        "Antrag Hundekrankenversicherung",
        "Tierhalter: Sabine Ollenbrock, Am Mühlbach 3, 85570 Markt Schwaben",
    ], ["Ollenbrock", "Am Mühlbach 3", "85570"]),
    F("b11_gleich_vermieter_arag", [
        "ARAG SE",
        "Schadenmeldung Rechtsschutz",
        "Vermieter: Rainer Felsberger, Lindenweg 6, 82008 Unterhaching",
    ], ["Felsberger", "Lindenweg 6", "82008"]),
    F("b11_var_geschaedigte_hausrat", [
        "Schadenanzeige zur Hausratversicherung",
        "Geschädigte: Petra Wendlinger, Ahornstraße 9, 85586 Poing",
        "Schadentag: 03.03.2025",
    ], ["Wendlinger", "Ahornstraße 9", "85586"]),
    F("b11_var_eigentuemer_mehrzeilig", [
        "Schadenmeldung Wohngebäudeversicherung",
        "Eigentümer:",
        "Thomas Riedlinger",
        "Kirchplatz 2",
        "85567 Grafing",
    ], ["Riedlinger", "Kirchplatz 2", "85567"]),
    F("b11_kontrolle_vn", [
        "Schadenanzeige zur Hausratversicherung",
        "Versicherungsnehmerin: Petra Wendlinger, Ahornstraße 9, 85586 Poing",
    ], ["Wendlinger", "Ahornstraße 9", "85586"]),
    # --- B12 IMEI mit Laufnummer, ICCID, EID -----------------------------------------------------------------------
    F("b12_gleich", [
        "Schadenmeldung Elektronikversicherung - Diebstahl",
        "Gerät: Apple iPhone 15 Pro, 256 GB",
        "IMEI 1: 35 693803 564380 9",
        "IMEI 2: 35 693803 564381 7",
        "SIM-Karte (ICCID): 8949 0200 0012 3456 7890",
        "eSIM-EID: 89049032004008882600012345678901",
    ], ["356938035643809", "356938035643817", "89490200001234567890", "89049032004008882600012345678901"]),
    F("b12_var", [
        "Schadenmeldung Handyversicherung",
        "IMEI (SIM 1): 352099001761481",
        "IMEI1: 359876543210987",
        "ICCID: 89490200001234567891",
        "EID: 89049032004008882600012345678902",
    ], ["352099001761481", "359876543210987", "89490200001234567891", "89049032004008882600012345678902"]),
    # --- B13 Über-Schwärzung Rasse / Geschlecht / Abstammung -------------------------------------------------------
    F("b13_gleich", [
        "Tierkrankenversicherung - versicherte Tiere",
        "Tier\t\tRasse\t\tGeschlecht",
        "Hund\t\tCavalier King Charles Spaniel\t\tHündin",
        "Hund\t\tDobermann\t\tRüde",
        "Katze\t\tMaine Coon\t\tKater",
        "Rasse: Jack Russell Terrier",
        "Geschlecht: Wallach",
        "Abstammung: Vater: Sandro Hit / Muttervater: Donnerhall",
        "Name des Pferdes: Don Camillo",
        "Versicherungsnehmer: Leon Wittkamp",
    ], ["Wittkamp"]),
    F("b13_var", [
        "Antrag Hundehalterhaftpflicht",
        "Rasse: Labrador Retriever, Geschlecht: Rüde, Farbe: schwarz",
        "Zweithund: Australian Shepherd, Hündin, kastriert",
        "Antrag Pferdehaftpflicht",
        "Rasse: Trakehner, Geschlecht: Stute, Abstammung: v. Gribaldi a.d. Kassandra",
        "Versicherungsnehmerin: Petra Wendlinger",
    ], ["Wendlinger"]),
    # --- B14 Rubrum, Gegner-Formular, RA ---------------------------------------------------------------------------
    F("b14_gleich_rubrum", [
        "Amtsgericht Ebersberg",
        "Geschäftsnummer: 3 C 456/24",
        "In dem Rechtsstreit",
        "Kranzbühler, Josef ./. Felsberger, Rainer",
        "wird Termin zur mündlichen Verhandlung bestimmt.",
    ], ["Kranzbühler", "Felsberger"]),
    F("b14_gleich_gegner_ra", [
        "Schadenmeldung Rechtsschutz",
        "Gegner (Name, Anschrift): Felsberger, Lindenweg 6, 82008 Unterhaching",
        "Gegnerischer Anwalt: RA Rauchenberger, Ebersberg",
    ], ["Felsberger", "Lindenweg 6", "Rauchenberger"]),
    F("b14_var", [
        "Landgericht München II",
        "In dem Rechtsstreit Wendlinger, Petra gegen Riedlinger, Thomas",
        "Die Gegenseite wird von RA Oberleitner vertreten.",
    ], ["Wendlinger", "Riedlinger", "Oberleitner"]),
    # --- B15 MaStR -------------------------------------------------------------------------------------------------
    F("b15_gleich", [
        "Antrag Photovoltaikversicherung",
        "MaStR-Nummer der Einheit: SEE912345678901",
        "MaStR-Nr. Anlagenbetreiber: ABR987654321098",
    ], ["SEE912345678901", "ABR987654321098"]),
    F("b15_var", [
        "Photovoltaikanlage - Angaben zur Anlage",
        "MaStR-Nr.: SEE998877665544",
        "Marktstammdatenregister-Nummer: ABR911223344556",
    ], ["SEE998877665544", "ABR911223344556"]),
    # --- B16 GbR in Eigentümerliste --------------------------------------------------------------------------------
    F("b16_gleich", [
        "Wohngebäudeversicherung WEG - Eigentümerliste",
        "Whg.\t\tEigentümer\t\tMEA",
        "1\t\tKranzbühler, J.\t\t125/1000",
        "2\t\tFelsberger GbR\t\t98/1000",
        "3\t\tDr. Hartlieb\t\t110/1000",
    ], ["Kranzbühler", "Felsberger", "Hartlieb"]),
    F("b16_var", [
        "Antrag Wohngebäudeversicherung",
        "Versicherungsnehmer: Wendlinger GbR (Petra und Thomas Wendlinger)",
        "Eigentümer: Grundstücksgemeinschaft Riedlinger",
    ], ["Wendlinger", "Riedlinger"]),
    # --- B17 Hersteller-/Modellnamen -------------------------------------------------------------------------------
    F("b17_gleich", [
        "Schadenliste Leitungswasser - beschädigter Hausrat",
        "Gegenstand\t\tHersteller/Modell\t\tZeitwert",
        "Gasgrill\t\tWeber Genesis II E-315\t\t480 EUR",
        "Akkuschrauber\t\tBosch GSR 18V-55\t\t90 EUR",
        "Armbanduhr Junghans Max Bill\t\t895,00 EUR",
        "Wechselrichter: Fronius Symo 10.0-3-M",
        "Warmwasser: Stiebel Eltron DHB-E 18 Sli",
        "Kunde: Leon Wittkamp",
    ], ["Wittkamp"]),
    F("b17_var", [
        "Kostenvoranschlag / Schadenliste",
        "Kaffeevollautomat\t\tDe'Longhi Magnifica S\t\t320 EUR",
        "Staubsauger\t\tMiele Complete C3\t\t180 EUR",
        "Fernseher\t\tLoewe bild i.55\t\t1.200 EUR",
        "Durchlauferhitzer: AEG DDLE 18 Basis",
        "Wärmepumpe: Vaillant aroTHERM plus",
        "Kunde: Petra Wendlinger",
    ], ["Wendlinger"]),
    # --- B18 Feld- und Rollenwörter als Namen ----------------------------------------------------------------------
    F("b18_gleich", [
        "Kanzlei Dr. Moosreiner & Kollegen - Rechtsanwälte - Marktplatz 3 - 85560 Ebersberg",
        "Gegnerischer Anwalt: noch nicht bekannt",
        "Patientenbesitzer: Familie Feldhoff",
        "Fachtierärztin für Kleintiere",
        "Reitbeteiligung: Lena Kortmann (Mitreiterin)",
        "Ausgefertigt",
        "Hergang: Beim Fußballspielen im Garten schoss mein Sohn Lukas den Ball gegen das Fenster.",
    ], ["Feldhoff", "Kortmann"]),
    F("b18_var", [
        "Rechtsanwaltskanzlei Pfisterer - Fachanwälte für Mietrecht",
        "Tierbesitzer: Familie Wendlinger",
        "Fachtierarzt für Pferde",
        "Beglaubigt",
        "Schadenhergang: Beim Rasenmähen schleuderte meine Tochter Anna einen Stein gegen das Auto.",
    ], ["Wendlinger"]),
    # --- B19 Fehlverdacht des Restrisikos --------------------------------------------------------------------------
    F("b19_gleich", [
        "ARAG SE",
        "40472 Düsseldorf",
        "Die Scheibe ist gesprungen.",
        "Korrespondenzanschrift: Siedlung 12, 16798 Fürstenberg/Havel",
        "Notebook: Dell XPS 13 9340",
        "WLAN-MAC-Adresse: liegt nicht vor",
        "MEA 125/1000",
        "Versicherungsnehmer: Leon Wittkamp",
    ], ["Wittkamp", "Siedlung 12"]),
    F("b19_var", [
        "HUK-COBURG",
        "96444 Coburg",
        "Die Scheibe war gerissen.",
        "Notebook: HP EliteBook 840 G10",
        "Miteigentumsanteil: 87/1000",
        "Versicherungsnehmerin: Petra Wendlinger",
    ], ["Wendlinger"]),
    # --- Scan-Stichprobe -------------------------------------------------------------------------------------------
    F("b11_scan", [
        "Schadenanzeige zur Hausratversicherung",
        "Geschädigte: Petra Wendlinger, Ahornstraße 9, 85586 Poing",
        "Schadentag: 03.03.2025",
    ], ["Wendlinger", "Ahornstraße 9", "85586"], scans=((200, 0.0, None),), text=False),
]
