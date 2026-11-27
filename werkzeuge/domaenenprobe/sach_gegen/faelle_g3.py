# Gegenprüfung Sach – Teil 3: Abgrenzungen zu den Befunden 1, 2, 7, 10, 14, 16 (erfundene Namen und Nummern)
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


FAELLE = [
    # B1: welcher Kopf trägt die Tabelle?
    F("b1_kopf_bezeichnung_eur", [
        "Stehlgutliste zur Hausratschadenanzeige",
        "Bezeichnung\t\tKaufpreis\t\tSeriennummer",
        "Spiegelreflexkamera Nikon D7500\t\t1.099,00 EUR\t\t3049217",
        "Objektiv Nikkor 18-140 mm\t\t449,00 EUR\t\t62231874",
        "Spielkonsole Sony PS5\t\t549,00 EUR\t\tE31K8TQ",
    ], ["3049217", "62231874", "E31K8TQ"]),
    F("b1_kopf_gegenstand_anschaffung_euro", [
        "Schadenaufstellung Einbruchdiebstahl",
        "Gegenstand\t\tAnschaffungspreis\t\tSerien-Nr.",
        "Notebook Lenovo ThinkPad T14\t\t1.299,00 €\t\tPF3K9XZ2",
        "E-Bike Cube Kathmandu\t\t2.499,00 €\t\tWCU88213",
        "Kopfhörer Bose QC45\t\t279,00 €\t\t077162",
    ], ["PF3K9XZ2", "WCU88213", "077162"]),
    # B2: weitere Etiketten der Gegenseite
    F("b2_var_antragsgegner_beklagte", [
        "Deckungsanfrage Rechtsschutz",
        "Versicherungsnehmer: Josef Kranzbühler",
        "Antragsgegner: Riedlinger",
        "Beklagte: Unterholzner",
    ], ["Riedlinger", "Unterholzner"]),
    # B7: genau die Zeilen des Prüfers, dann Varianten ohne fremden Fehlalarm
    F("b7_exakt_pruefer", [
        "Amtsgericht Ebersberg",
        "Geschäftsnummer: 3 C 456/24",
        "Beschluss",
        "Der Streitwert wird auf 2.400,00 EUR festgesetzt.",
        "Hartlieb",
        "Richterin am Amtsgericht",
        "Ausgefertigt",
        "Eibl, JAng",
        "Urkundsbeamtin der Geschäftsstelle",
    ], ["Hartlieb", "Eibl"]),
    F("b7_var_isoliert", [
        "Polizeiinspektion Grafing",
        "Ihre Anzeige wurde von PHKin Reithmeier aufgenommen.",
        "Kollmannsberger, JOSin",
        "als Urkundsbeamtin der Geschäftsstelle",
    ], ["Reithmeier", "Kollmannsberger"]),
    # B10: weitere "Name des/der <Rolle>"-Zeilen mit zweitem Personenfeld
    F("b10_var_geschaedigte_zwei_felder", [
        "Schadenmeldung Privathaftpflicht",
        "Name der Geschädigten: Riedlinger        Vorname: Anna",
    ], ["Riedlinger"]),
    F("b10_var_mieter_zwei_felder", [
        "Schadenmeldung Leitungswasser",
        "Name des Mieters: Oberleitner        Vorname: Klaus",
    ], ["Oberleitner"]),
    # B14: Rubrum mit bekannten Nachnamen
    F("b14_var_bekannte_namen", [
        "Amtsgericht Ebersberg",
        "In dem Rechtsstreit",
        "Pfisterer, Josef ./. Haberkorn, Rainer",
        "wird Termin zur mündlichen Verhandlung bestimmt.",
    ], ["Pfisterer", "Haberkorn"]),
    F("b14_var_unbekannt_gegen", [
        "Amtsgericht Ebersberg",
        "In dem Rechtsstreit",
        "Kranzbühler, Josef gegen Felsberger, Rainer",
        "wird Termin zur mündlichen Verhandlung bestimmt.",
    ], ["Kranzbühler", "Felsberger"]),
    # B16: GbR in der Eigentümerspalte ohne MEA-Spalte (ohne fremden Fehlalarm)
    F("b16_var_ohne_mea", [
        "Wohngebäudeversicherung WEG - Eigentümerliste",
        "Whg.\t\tEigentümer\t\tLage",
        "1\t\tKranzbühler, J.\t\tEG links",
        "2\t\tFelsberger GbR\t\tEG rechts",
        "3\t\tDr. Hartlieb\t\t1. OG",
    ], ["Kranzbühler", "Felsberger", "Hartlieb"]),
]
