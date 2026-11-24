# Domänen-Probe "Finanzen, Behörden, Digitales" – Runde 2: Gegenproben zu den Befunden aus lauf_a/lauf_b
# (Einzelfälle ohne weiteren Verdacht auf der Seite, Nachbar-Schreibweisen, Über-Schwärzung). Alles erfunden.
def F(name, zeilen, geheim, scans=(), **kw):
    return dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans, **kw)


S200 = ((200, 0.0, None),)

FAELLE = [
    # --- Kennungen mit Tausenderpunkten (Betragsform) hinter eindeutigen Etiketten, je Seite ohne anderen Verdacht
    F("punkte_kassenzeichen", [
        "Stadt Augsburg – Stadtkasse",
        "Grundsteuerbescheid 2025",
        "Kassenzeichen: 921.103.215",
        "Bitte geben Sie bei Zahlungen stets das Kassenzeichen an.",
    ], ["921.103.215"]),
    F("punkte_varianten", [
        "Übersicht Ihrer Verträge",
        "Mitgliedsnummer: 31.415.926",
        "Darlehensnummer 2.718.281.828",
        "Konto-Nr. 161.803.398",
        "Personalnummer: 004.711",
        "Versicherungsnummer 47.110.815",
    ], ["31.415.926", "2.718.281.828", "161.803.398", "004.711", "47.110.815"]),
    F("punkte_tabelle_spalte", [
        "Bestandsliste Kunde",
        "Sparte\t\tVertragsnummer\t\tBeitrag",
        "Bausparen\t\t6.012.345.678\t\t50,00",
        "Fondsdepot\t\t893.104.552\t\t100,00",
    ], ["6.012.345.678", "893.104.552"]),
    F("punkte_scan", [
        "Depotauszug",
        "Depot-Nr. 712.345.678",
        "Kunden-Nr. 4.711.081",
    ], ["712.345.678", "4.711.081"], scans=S200),

    # --- Zwischenwörter / Präfixe zwischen Etikett und Wert, Wert mit wenigen Ziffern
    F("vorgang_zwischenwort_allein", [
        "Bestätigung Ihres Online-Antrags",
        "Vorgangsnummer Ihres Online-Antrags: 7HXK-92LQ-QA",
        "Bitte geben Sie diese Nummer bei Rückfragen an.",
    ], ["7HXK-92LQ-QA"]),
    F("referenz_zwischenwort", [
        "Ihre Online-Schadenmeldung ist eingegangen.",
        "Referenznummer für Rückfragen: KX-4711-QZ",
        "Kundennummer bei der Musterbank: Q-0815",
    ], ["KX-4711-QZ", "Q-0815"]),
    F("ticket_raute", [
        "Ihre Anfrage wurde unter der Ticketnummer #A-4711 erfasst.",
        "Bitte antworten Sie nicht auf diese E-Mail.",
    ], ["A-4711"]),

    # --- fehlende Etiketten (Behörden, Bank, Post)
    F("bg_nummer_varianten", [
        "Jobcenter Augsburg-Stadt – Änderungsbescheid",
        "BG-Nr.: 96202BG0023456",
        "Bedarfsgemeinschaftsnummer: 96202BG0034567",
        "Nummer der BG: 96202//0045678",
    ], ["96202BG0023456", "96202BG0034567", "96202//0045678"]),
    F("postnummer_varianten", [
        "Lieferadresse für das Ersatzgerät",
        "DHL-Postnummer: 87654321",
        "Postnummer 76543210 (Packstation 117)",
    ], ["87654321", "76543210"]),
    F("konto_ohne_nr", [
        "Bitte überweisen Sie die Erstattung auf mein Konto 0240123456 bei der Volksbank.",
        "Alternativ: Sparkonto 3182736455, Tagesgeldkonto 5928374610",
    ], ["0240123456", "3182736455", "5928374610"]),
    F("reisepass_fliesstext", [
        "Der Antragsteller hat sich mit seinem Reisepass CF9JKRTN7 ausgewiesen.",
        "Die Ehefrau legte ihren Personalausweis LZ6KR4P9T vor.",
    ], ["CF9JKRTN7", "LZ6KR4P9T"]),

    # --- Digitales: IPv6, Messenger-Handles, Namen in URLs, Mitgliedsnamen
    F("ipv6_allein", [
        "Elektronische Einwilligung",
        "Zustimmung erteilt am 12.03.2025 um 14:08 Uhr von 2001:db8:85a3::8a2e:370",
    ], ["2001:db8:85a3::8a2e:370"]),
    F("messenger_handles", [
        "Erreichbarkeit des Kunden",
        "Telegram: t.me/lenchen_wiese82",
        "Snapchat: lenchenwiese",
        "Signal-Benutzername: lenchen.82",
    ], ["lenchen_wiese82", "lenchenwiese", "lenchen.82"]),
    F("portal_link_mit_ids", [
        "Ihr Dokument liegt im Kundenportal bereit:",
        "https://portal.mv-versich.de/dok?kdnr=4711081&vsnr=LV2024887766&name=Zwackelhuber",
    ], ["4711081", "LV2024887766", "Zwackelhuber"]),
    F("plattform_namen", [
        "Schadenmeldung Internetschutz (Kaufbetrug)",
        "Verkäufer auf Kleinanzeigen, Nutzername: rumpelmayr_hilde",
        "Mein eBay-Mitgliedsname: hilde.rumpel57",
        "Profilname auf Vinted: HildeR1957",
    ], ["rumpelmayr_hilde", "hilde.rumpel57", "HildeR1957"]),
    F("einzelunternehmer_ust", [
        "Antrag Betriebshaftpflicht – Einzelunternehmen",
        "Versicherungsnehmer: Gottfried Brezelmeier, Inhaber Brezelmeier Haustechnik e.K.",
        "USt-IdNr. des Versicherungsnehmers: DE287654321",
    ], ["Brezelmeier", "DE287654321"]),

    # --- Telefonnotiz / Chat ohne Anrede, Namen außerhalb der Wissensbasis
    F("telefonnotiz_knapp", [
        "12.03. RR Rumpelmayr (0821 456789) – will kündigen",
        "13.03. Rumpelmayr erneut angerufen, Unterlagen per Post",
        "Sohn Korbinian ruft morgen zurück",
    ], ["Rumpelmayr", "0821456789", "Korbinian"]),
    F("whatsapp_android", [
        "WhatsApp Chat mit Hildegard Rumpelmayr",
        "12.03.25, 14:03 - Hildegard Rumpelmayr: Guten Tag, der Wasserschaden ist schlimmer geworden",
        "12.03.25, 14:05 - Makler Sonnleitner: Ich schicke den Gutachter.",
        "12.03.25, 14:07 - Hildegard Rumpelmayr: Mein Schwiegersohn Korbinian Zeitlhofer ist vor Ort",
    ], ["Rumpelmayr", "Zeitlhofer"], scans=S200),

    # --- Über-Schwärzung: Fonds-/Produktnamen, Bescheid-Fachwörter, E-Mail-Kopfwörter
    F("ueber_depot_fonds", [
        "Depotübersicht zum Beratungsprotokoll",
        "Fonds\t\tStück\t\tKurswert EUR",
        "iShares Core MSCI World\t\t120\t\t11.240,00",
        "Xtrackers DAX\t\t40\t\t7.512,00",
        "DWS Top Dividende\t\t35\t\t4.311,00",
        "Allianz Global Investors\t\t10\t\t1.050,00",
        "Festgeld Zinsplus\t\t1\t\t10.000,00",
    ], []),
    F("ueber_bescheid_woerter", [
        "Berechnung der Leistungen",
        "Regelbedarf\t\t563,00 EUR",
        "Mehrbedarf Alleinerziehung\t\t67,56 EUR",
        "Kosten der Unterkunft\t\t650,00 EUR",
        "Festgesetzt werden: Einkommensteuer 4.812,00 EUR",
        "Bruttoarbeitslohn\t\t41.250,00 EUR",
        "Kindergeldberechtigte Person: siehe Seite 2",
        "Wichtigkeit: Hoch\t\tAnlagen: Bescheid.pdf",
        "Kind regards, Best regards, Mit freundlichen Grüßen",
    ], []),
]
