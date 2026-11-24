# Gegenprüfung Sparte Person, Teil 2: markierte Lecks und Über-Schwärzung (Befunde 8-19). Erfundene Personen/Nummern.
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


SCAN = ((200, 0.0, None),)

FAELLE = [
    # --- B8: Rechnungsempfänger unter Firmenkopf ---------------------------------------------------------------
    F("b8_gleich", [
        "Privatärztliche Verrechnungsstelle Südbayern GmbH",
        "Rechnungsempfänger: Ilse Wohlgemuth-Brandl, Am Mühlbach 12, 83646 Bad Tölz",
        "Rechnungs-Nr.: R-2024-118733",
    ], ["Wohlgemuth", "Am Mühlbach 12", "83646"]),
    F("b8_block", [
        "Labor Dr. Brunner MVZ GmbH",
        "Rechnungsempfänger:",
        "Herrn Anton Seidl",
        "Fichtenstr. 9",
        "94036 Passau",
        "Rechnung Nr. 2026-04471 vom 03.11.2026",
    ], ["Seidl", "Fichtenstr. 9", "94036"]),
    F("b8_rechnungsanschrift", [
        "Kreisklinik Altötting gGmbH",
        "Rechnungsanschrift: Anton Seidl, Fichtenstr. 9, 94036 Passau",
    ], ["Seidl", "Fichtenstr. 9", "94036"]),

    # --- B9: E-Ticket / Auslandsrechnung -----------------------------------------------------------------------
    F("b9_gleich", [
        "ELECTRONIC TICKET ITINERARY RECEIPT",
        "PASSENGER: KRANICH/BIRGIT MRS",
        "TICKET NUMBER: 220 2345678901",
        "FREQUENT FLYER: LH 992004471123",
    ], ["KRANICH", "BIRGIT", "2202345678901", "992004471123"]),
    F("b9_var", [
        "Ihr elektronisches Ticket",
        "Name of passenger: SEIDL/ANTON MR",
        "E-Ticket-Nr.: 220-2345678902",
        "Vielfliegernummer: 992004471124",
    ], ["SEIDL", "ANTON", "2202345678902", "992004471124"]),
    F("b9_patient_id", [
        "Hospital Universitario - Invoice",
        "Patient ID: 0098812",
        "Patient No.: 0098813",
    ], ["0098812", "0098813"]),

    # --- B10: Reisende als "Nachname, Vorname, Datum" -----------------------------------------------------------
    F("b10_gleich", [
        "Reiserücktrittsversicherung - versicherte Reisende",
        "Reisende: Kranich, Detlef, 12.04.1969; Kranich, Jona, 17.02.2014;",
        "Kranich, Emma, 05.05.2019",
    ], ["Kranich", "12.04.1969", "Jona", "17.02.2014", "05.05.2019"]),
    F("b10_erwachsene", [
        "Gruppenreiseversicherung - Teilnehmerliste",
        "Versicherte Personen: Seidl, Anton, 03.07.1962; Seidl, Maria, 21.01.1965",
    ], ["Seidl", "Anton", "03.07.1962", "Maria", "21.01.1965"]),

    # --- B12: EHIC Kennnummer der Karte ------------------------------------------------------------------------
    F("b12_gleich", [
        "Europäische Krankenversicherungskarte (Kopie)",
        "8. Kennnummer der Karte: 80276001570012345678",
    ], ["80276001570012345678"]),
    F("b12_var", [
        "Rückseite der Gesundheitskarte (EHIC)",
        "Kennnummer der Karte 80276 00157 0098765432",
    ], ["80276001570098765432"]),

    # --- B13: Heil- und Kostenplan -------------------------------------------------------------------------------
    F("b13_gleich", [
        "Betreff: Zahnzusatz",
        "Hallo Herr Steinbeis, anbei der HKP Nr. 2026-0341 von Dr. Fenske.",
    ], ["20260341"]),
    F("b13_var", [
        "Heil- und Kostenplan Nr. 2026-0342 vom 03.11.2026",
        "HKP-Nr.: 2026-0343",
    ], ["20260342", "20260343"]),

    # --- B14: Gebührenziffern als Kennung ----------------------------------------------------------------------
    F("b14_gleich", [
        "Liquidation zahnärztliche Behandlung",
        "Datum\t\tGOZ-Nr.\t\tBetrag",
        "12.03.2025\t\t0010\t\t12,94 €",
        "12.03.2025\t\t2197\t\t16,82 €",
        "19.03.2025\t\t5120\t\t287,31 €",
    ], []),
    F("b14_goae_nr", [
        "Rechnung Facharztpraxis Orthopädie",
        "Datum\t\tGOÄ-Nr.\t\tBetrag",
        "02.09.2025\t\t5855\t\t53,62 €",
        "02.09.2025\t\t3511\t\t5,36 €",
    ], []),

    # --- B15: Behandlungsdatum als Geburtsdatum -----------------------------------------------------------------
    F("b15_gleich", [
        "Angaben zu Arztbesuchen der letzten 10 Jahre",
        "Dr. Ute Kranzfelder, 03.11.2012: Meniskusoperation links",
    ], ["Kranzfelder"]),
    F("b15_var", [
        "Gesundheitsfragen - Erläuterungen",
        "Dr. med. Sabine Ortlieb, 21.03.2015: Arthroskopie Knie rechts",
    ], ["Ortlieb"]),
    F("b15_gebnr", [
        "Rechnung Praxis Dr. Fuchsberger",
        "Datum\t\tGeb.-Nr.\t\tBetrag",
        "09.09.2025\t\t0410\t\t19,82 €",
    ], []),
    F("b15_gebziffer", [
        "Zahnärztliche Rechnung",
        "Datum\t\tGeb.-Ziffer\t\tBetrag",
        "16.10.2025\t\t2120\t\t104,83 €",
    ], []),

    # --- B16: Eponyme/medizinische Adjektive als Name ----------------------------------------------------------
    F("b16_gleich", [
        "Gesundheitsfragen - Antworten der versicherten Person",
        "Vorerkrankungen: Morbus Crohn seit 2015, Hashimoto-Thyreoiditis, Morbus Bechterew ausgeschlossen",
    ], []),
    F("b16_var", [
        "Diagnosen:",
        "Morbus Basedow, Erstdiagnose 2019",
        "Chronische Gastritis",
        "Akute Bronchitis",
    ], []),

    # --- B17: Rollen-/Feldwörter als Name ----------------------------------------------------------------------
    F("b17_gleich", [
        "Stammversicherter: Albin Zwickl",
        "Hauptversicherter: Konrad Hiltl",
    ], ["Zwickl", "Hiltl"]),
    F("b17_var", [
        "Hauptversicherte: Ilse Brandl",
        "Einweisender Arzt: Dr. Petra Ullrich",
        "Erstbehandelnder Arzt: Dr. Jens Abendroth",
    ], ["Brandl", "Ullrich", "Abendroth"]),
    F("b17_ueberschrift", [
        "Durchgangsarztbericht",
        "Unfallversicherungsträger: BG Verkehr",
    ], []),

    # --- B18: PZN als Telefonnummer ---------------------------------------------------------------------------
    F("b18_gleich", [
        "Apothekenquittung (Privatrezept)",
        "PZN\t\tArtikel\t\tPreis",
        "01126111\t\tIbuprofen 600 mg 50 St.\t\t12,49 €",
    ], []),
    F("b18_inline", [
        "Privatrezept - Apotheke am Rathaus",
        "PZN 04884569 Pantoprazol 20 mg, 28 St., 9,98 €",
    ], []),

    # --- B19: Reisewörter, Unfallort ---------------------------------------------------------------------------
    F("b19_gleich", [
        "Hotel: Hotel Cala Ratjada Mar, 7 Nächte, Doppelzimmer Meerblick",
        "Rückflug: 19.07.2026 EW 7583",
    ], []),
    F("b19_var", [
        "Zimmerkategorie: Doppelzimmer Gartenblick",
        "Hinflug: 12.07.2026 EW 7582",
    ], []),
    F("b19_unfallort", [
        "Unfallanzeige Schülerunfall",
        "Unfallort: Turnhalle der Mittelschule Erding",
        "Unfallort: Skigebiet Sudelfeld, Bayrischzell",
    ], ["Sudelfeld"]),
]
