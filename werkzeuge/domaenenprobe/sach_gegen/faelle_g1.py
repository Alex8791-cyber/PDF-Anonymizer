# Gegenprüfung Sach – Teil 1 (Befunde 1–10): je Befund die gleiche Zeile isoliert und eine leicht andere, realistische
# Schreibweise. Erfundene Namen und Nummern.
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


FAELLE = [
    # --- B1 Stehlgutliste: Seriennummer-Spalte hinter Preisspalte ---------------------------------------------------
    F("b1_gleich_sn_preis", [
        "Stehlgutliste zur Hausratschadenanzeige",
        "Gegenstand\t\tKaufpreis\t\tSeriennummer",
        "Spiegelreflexkamera Nikon D7500\t\t1.099,00 EUR\t\t3049217",
        "Objektiv Nikkor 18-140 mm\t\t449,00 EUR\t\t62231874",
        "Armbanduhr\t\t895,00 EUR\t\t4521",
        "Spielkonsole Sony PS5\t\t549,00 EUR\t\tE31K8TQ",
    ], ["3049217", "62231874", "4521", "E31K8TQ"]),
    F("b1_var_neupreis_euro", [
        "Aufstellung der entwendeten Gegenstände",
        "Bezeichnung\t\tNeupreis\t\tSerien-Nr.",
        "Notebook Lenovo ThinkPad T14\t\t1.299,00 €\t\tPF3K9XZ2",
        "E-Bike Cube Kathmandu\t\t2.499,00 €\t\tWCU88213",
        "Tablet Samsung Galaxy Tab S9\t\t749,00 €\t\tR52W40ABCDE",
        "Kopfhörer Bose QC45\t\t279,00 €\t\t077162",
    ], ["PF3K9XZ2", "WCU88213", "R52W40ABCDE", "077162"]),
    F("b1_var_kaufdatum", [
        "Stehlgutliste zur Hausratschadenanzeige",
        "Gegenstand\t\tKaufdatum\t\tSeriennummer",
        "Notebook Lenovo ThinkPad T14\t\t14.11.2023\t\tPF3K9XZ2",
        "E-Bike Cube Kathmandu\t\t02.05.2022\t\tWCU88213",
        "Kopfhörer Bose QC45\t\t24.12.2021\t\t077162",
    ], ["PF3K9XZ2", "WCU88213", "077162"]),
    # --- B2 Gegenseite im Rechtsschutz -----------------------------------------------------------------------------
    F("b2_gleich_insachen", [
        "Dr. Moosreiner & Kollegen",
        "Ihr VN: Josef Kranzbühler",
        "In Sachen Kranzbühler ./. Felsberger",
        "wegen Mietminderung",
        "der Vermieter Felsberger verweigert die Beseitigung des Schimmels im Schlafzimmer.",
        "Wir bitten um Deckungszusage für die erste Instanz.",
    ], ["Felsberger", "Kranzbühler"]),
    F("b2_gleich_gegner", [
        "Schadenmeldung Rechtsschutz",
        "Versicherungsnehmer: Josef Kranzbühler",
        "Gegner: Felsberger",
    ], ["Felsberger", "Kranzbühler"]),
    F("b2_gleich_beklagter", [
        "Klageerwiderung - Abschrift für den Rechtsschutzversicherer",
        "Ihr VN: Josef Kranzbühler",
        "Beklagter: Felsberger",
    ], ["Felsberger", "Kranzbühler"]),
    F("b2_var_gegen_gegenseite", [
        "Deckungsanfrage Rechtsschutz",
        "Mandant: Thomas Pfisterer",
        "In der Mietsache Pfisterer gegen Wendlinger",
        "Gegenseite: Wendlinger, vertreten durch die Hausverwaltung",
        "Die Vermieterin Wendlinger verlangt Schadensersatz wegen angeblicher Schäden an der Einbauküche.",
    ], ["Wendlinger", "Pfisterer"]),
    F("b2_var_prozessgegner_klaeger", [
        "Schadenmeldung Rechtsschutz - Arbeitsrecht",
        "Versicherungsnehmerin: Monika Tremmel",
        "Prozessgegner: Riedlinger",
        "Klägerin: Oberleitner",
    ], ["Riedlinger", "Oberleitner", "Tremmel"]),
    F("b2_var_bekannter_name", [
        "Schadenmeldung Rechtsschutz",
        "Versicherungsnehmer: Josef Kranzbühler",
        "Gegner: Haberkorn",
    ], ["Haberkorn", "Kranzbühler"]),
    # --- B3 Nachname im Fließtext ohne Etikett ---------------------------------------------------------------------
    F("b3_gleich_nachbarn", [
        "Schadenanzeige Privathaftpflicht",
        "Mein Sohn schoss beim Fußballspielen den Ball in das Wohnzimmerfenster unseres Nachbarn Felsberger.",
        "Das Glas ist gesprungen, ein Glaser hat ein Angebot über 640,00 EUR erstellt.",
    ], ["Felsberger"]),
    F("b3_gleich_bei_klammern", [
        "Schadenmeldung Leitungswasser",
        "Bei Felsberger im 1. OG ist das Wasser durch die Decke getreten.",
        "Betroffen sind die Wohnungen EG links (Hackenschmied) und 1. OG links (Rauchenberger).",
    ], ["Felsberger", "Hackenschmied", "Rauchenberger"]),
    F("b3_var_unser_nachbar", [
        "Schadenmeldung Privathaftpflicht",
        "Unser Nachbar Wendlinger hat den Schaden am Gartenzaun am nächsten Morgen bemerkt.",
        "Die Mieterin Riedlinger aus dem Erdgeschoss war Zeugin.",
    ], ["Wendlinger", "Riedlinger"]),
    F("b3_var_wohnung_von", [
        "Schadenmeldung Leitungswasser (Hausverwaltung)",
        "Das Wasser ist aus der Wohnung Oberleitner (2. OG rechts) in die darunterliegende Wohnung gelaufen.",
        "Beim Nachbarn Unterholzner sind Decke und Parkett beschädigt.",
    ], ["Oberleitner", "Unterholzner"]),
    F("b3_var_bekannter_name", [
        "Schadenmeldung Leitungswasser",
        "Bei Haberkorn im 1. OG ist das Wasser durch die Decke getreten.",
    ], ["Haberkorn"]),
    # --- B4 Aktenzeichen im Fließtext ohne Etikett -----------------------------------------------------------------
    F("b4_gleich", [
        "Kostenrechnung zur Rechtsschutzsache Ihres VN Josef Kranzbühler",
        "Das Verfahren 3 C 456/24 vor dem AG Ebersberg wurde durch Vergleich beendet.",
        "Die Staatsanwaltschaft Traunstein hat das Verfahren 210 Js 345/24 eingestellt.",
    ], ["3 C 456/24", "345/24"]),
    F("b4_var", [
        "Sehr geehrte Damen und Herren,",
        "im Rechtsstreit 14 S 2211/24 hat das Landgericht München I am 12.03.2025 die Berufung zurückgewiesen.",
        "Im Ermittlungsverfahren 410 Js 12345/24 der Staatsanwaltschaft München I wurde Akteneinsicht gewährt.",
    ], ["14 S 2211/24", "12345/24"]),
    # --- B5 Abkürzungen "Xxx.-Nr." und "X-Nummer" ------------------------------------------------------------------
    F("b5_gleich", [
        "Eingangsbestätigung Fahrraddiebstahl",
        "Vorg.-Nr. 123/25",
        "Ser.-Nr. des Rahmens: WTU 4471",
        "Mdt.-Nr. 1024",
    ], ["123/25", "WTU4471", "1024"]),
    F("b5_gleich_rahmen_nummer", [
        "Fahrradversicherung - Diebstahlanzeige",
        "Rahmen-Nummer: WTU 4471",
    ], ["WTU4471"]),
    F("b5_var", [
        "Diebstahlanzeige Fahrrad",
        "Vorg.-Nr.: 0815/25",
        "Ser.-Nr.: WTU 44718",
        "Mdt.-Nr.: 10245",
        "Geräte-Nummer: GX 7741",
    ], ["0815/25", "WTU44718", "10245", "GX7741"]),
    F("b5_var_bindestrich_nummer", [
        "Fahrradpass",
        "Rahmen-Nummer: WBK 556677",
        "Akku-Nummer: 1KX 4471",
    ], ["WBK556677", "1KX4471"]),
    # --- B6 Tierkennzeichnung --------------------------------------------------------------------------------------
    F("b6_gleich", [
        "Antrag Hundekrankenversicherung",
        "Kennzeichnung des Hundes",
        "Tätowierung (li. Ohr): ZB 2187",
        "Tätowiernummer Zuchtbuch: VDH 3366",
        "Hundesteuermarke Nr. 0386",
    ], ["ZB 2187", "VDH 3366", "0386"]),
    F("b6_gleich_kennnummer", [
        "Hundehaftpflicht - Angaben zum Tier",
        "Kennnummer: 0815",
    ], ["0815"]),
    F("b6_var", [
        "Angaben zum versicherten Tier",
        "Tätowierung: DT 4417",
        "Tätowiernummer: VDH 7734",
        "Steuermarke: 2291",
        "Hundemarke Nr. 1187",
    ], ["DT4417", "VDH7734", "2291", "1187"]),
    # --- B7 Dienstgrade / Amtsbezeichnungen ------------------------------------------------------------------------
    F("b7_gleich_gericht", [
        "Amtsgericht Ebersberg",
        "Beschluss",
        "Der Streitwert wird auf 2.400,00 EUR festgesetzt.",
        "Eibl, JAng",
        "Urkundsbeamtin der Geschäftsstelle",
    ], ["Eibl"]),
    F("b7_gleich_polizei", [
        "Polizeiinspektion Poing",
        "Rückfragen richten Sie bitte an KHKin Sedlmayr (K 33).",
    ], ["Sedlmayr"]),
    F("b7_var", [
        "Polizeiinspektion Grafing",
        "Ihre Anzeige wurde von PHKin Reithmeier aufgenommen.",
        "Für Rückfragen steht Ihnen KOK Unterholzner zur Verfügung.",
        "Kollmannsberger, JOSin",
        "als Urkundsbeamtin der Geschäftsstelle",
    ], ["Reithmeier", "Unterholzner", "Kollmannsberger"]),
    # --- B8 Einzelkaufmann: HRA und USt-IdNr. ----------------------------------------------------------------------
    F("b8_gleich", [
        "Antrag Betriebshaftpflicht",
        "Inhaber: Florian Sedlmayr",
        "Handelsregister: Amtsgericht München HRA 112233",
        "USt-IdNr.: DE287654321",
    ], ["HRA 112233", "DE287654321"]),
    F("b8_var", [
        "Antrag Inhaltsversicherung für Handwerksbetriebe",
        "Firma: Schreinerei Thomas Wendlinger e.K.",
        "Registergericht: AG Traunstein, HRA 20455",
        "Umsatzsteuer-ID: DE 312 445 678",
    ], ["HRA 20455", "DE312445678"]),
    # --- B9 Service-Tag / MAC-Adresse ------------------------------------------------------------------------------
    F("b9_gleich_servicetag", [
        "Diebstahlanzeige - Angaben zum Gerät",
        "Notebook: Dell Latitude",
        "Service-Tag: 7XK2Q3F",
    ], ["7XK2Q3F"]),
    F("b9_gleich_mac", [
        "Diebstahlanzeige - Angaben zum Gerät",
        "MAC-Adresse: 3C:22:FB:9A:1B:7E",
    ], ["3C22FB9A1B7E"]),
    F("b9_var", [
        "Schadenmeldung Elektronikversicherung",
        "Service Tag (S/N): 4HQ9ZM2",
        "MAC: 3C-22-FB-9A-1B-7E",
    ], ["4HQ9ZM2", "3C22FB9A1B7E"]),
    # --- B10 Zwei Felder in einer Zeile ----------------------------------------------------------------------------
    F("b10_gleich", [
        "Unfallmeldung Tierhalterhaftpflicht",
        "Name des Hundehalters: Felsberger        Vorname: Rainer",
    ], ["Felsberger"]),
    F("b10_var_name_vorname", [
        "Schadenanzeige Hausratversicherung",
        "Name: Wendlinger        Vorname: Petra",
        "Straße: Ahornstraße 9        PLZ/Ort: 85586 Poing",
    ], ["Wendlinger", "Ahornstraße 9"]),
    F("b10_var_nachname_bekannt", [
        "Schadenanzeige Hausratversicherung",
        "Nachname: Haberkorn        Vorname: Petra",
    ], ["Haberkorn"]),
    F("b10_var_scan", [
        "Schadenanzeige Hausratversicherung",
        "Name: Wendlinger        Vorname: Petra",
        "Straße: Ahornstraße 9        PLZ/Ort: 85586 Poing",
    ], ["Wendlinger", "Ahornstraße 9"], scans=((200, 0.0, None),), text=False),
]
