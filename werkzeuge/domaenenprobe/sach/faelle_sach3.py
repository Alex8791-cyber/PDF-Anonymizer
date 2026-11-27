# Domänen-Probe Sach/Haftpflicht/Wohnen/Recht – Runde 3: Grenzen der Fehlerklassen aus Runde 1/2 (eigene Fälle,
# erfundene Namen und Nummern)
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


TIER_KENNZ = [
    "Antrag Hundekrankenversicherung",
    "Tierhalterin: Sabine Ollenbrock",
    "Kennzeichnung des Hundes",
    "Tätowierung (li. Ohr): ZB 2187",
    "Hundesteuermarke Nr. 0386",
]

FAELLE = [
    F("tabelle_seriennummer_mehrzeilig", [
        "Stehlgutliste zur Hausratschadenanzeige",
        "Gegenstand\t\tSeriennummer",
        "Spiegelreflexkamera Nikon D7500\t\t3049217",
        "Armbanduhr\t\t4521",
        "Spielkonsole Sony PS5\t\tE31K8TQ",
        "Objektiv Nikkor 18-140 mm\t\t62231874",
    ], ["3049217", "4521", "E31K8TQ", "62231874"]),
    F("zwei_felder_zeile", [
        "Schadenmeldung Leitungswasser",
        "Name des Vermieters: Felsberger        Telefon: 089 4412345",
    ], ["Felsberger", "0894412345"]),
    F("weg_eigentuemerliste", [
        "Wohngebäudeversicherung WEG Lindenweg 4 - Eigentümerliste",
        "Whg.\t\tEigentümer\t\tMEA",
        "1\t\tKranzbühler, J.\t\t125/1000",
        "2\t\tFelsberger GbR\t\t98/1000",
        "3\t\tDr. Hartlieb\t\t110/1000",
    ], ["Kranzbühler", "Felsberger", "Hartlieb"]),
    F("rs_beklagter", [
        "Klageerwiderung - Abschrift für den Rechtsschutzversicherer",
        "Ihr VN: Josef Kranzbühler",
        "Beklagter: Felsberger",
    ], ["Felsberger", "Kranzbühler"]),
    F("rs_gegner_nachname", [
        "Schadenmeldung Rechtsschutz",
        "Versicherungsnehmer: Josef Kranzbühler",
        "Gegner: Felsberger",
    ], ["Felsberger", "Kranzbühler"]),
    F("hausrat_mitbewohnerin", [
        "Schadenanzeige Hausrat - Einbruchdiebstahl",
        "Versicherungsnehmer: Leon Wittkamp",
        "Mitbewohnerin: Zwickl",
    ], ["Zwickl", "Wittkamp"]),
    F("handwerker_etikett", [
        "Schadenmeldung Leitungswasser - Angaben zur Reparatur",
        "Handwerker: Leitgeb",
        "Reparatur am 04.03.2025 abgeschlossen.",
    ], ["Leitgeb"]),
    F("hv_mieter_klammern", [
        "Schadenmeldung Wohngebäude (Hausverwaltung)",
        "Betroffen sind die Wohnungen EG links (Felsberger) und 1. OG links (Rauchenberger).",
    ], ["Felsberger", "Rauchenberger"]),
    F("polizei_sachbearbeitung_etikett", [
        "Polizeiinspektion Poing",
        "Vorgangsnummer: BY8513-004711-25/1",
        "Sachbearbeitung: KHKin Sedlmayr",
    ], ["Sedlmayr", "BY8513-004711-25/1"]),
    F("steuermarke_varianten", [
        "Hundehaftpflicht - Angaben zum Tier",
        "Steuermarken-Nr.: 0386",
        "Kennnummer: 0815",
    ], ["0386", "0815"]),
    F("servicetag_allein", [
        "Diebstahlanzeige - Angaben zum Gerät",
        "Notebook: Dell Latitude",
        "Service-Tag: 7XK2Q3F",
    ], ["7XK2Q3F"]),
    F("scan_tier_kennzeichnung", TIER_KENNZ, ["ZB 2187", "0386", "Ollenbrock"],
      scans=((200, 0.0, None),), text=False),
    # --- Nachtrag: Bindestrich-Etiketten "X-Nummer" (allgemeine Nummern-Etikettregel) ------------------------------
    F("rahmen_nummer_bindestrich", [
        "Fahrradversicherung - Diebstahlanzeige",
        "Versicherungsnehmer: Leon Wittkamp",
        "Rahmen-Nummer: WTU 4471",
    ], ["WTU4471", "Wittkamp"]),
    F("chip_nummer_bindestrich", [
        "Tierkrankenversicherung - Leistungsantrag",
        "Tierhalterin: Sabine Ollenbrock",
        "Chip-Nummer: 276 098 106 543 210",
    ], ["276098106543210", "Ollenbrock"]),
    F("anschrift_unter_versichererblock", [
        "ARAG SE",
        "Schadenmeldung Rechtsschutz",
        "Vermieter: Rainer Felsberger, Lindenweg 6, 82008 Unterhaching",
        "Rechtsgebiet: Mietrecht",
    ], ["Felsberger", "Lindenweg 6", "82008"]),
]
