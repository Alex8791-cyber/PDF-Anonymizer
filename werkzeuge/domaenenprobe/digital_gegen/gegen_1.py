# Gegenprüfung Sparte "digital" (Finanzen/Behörden): je Befund die Zeile des Prüfers (…_gleich) und eine leicht
# andere, realistische Schreibweise (…_var). Alle Namen und Nummern erfunden; Steuer-IDs mit gültiger Prüfziffer
# (gen_werte.py). Werte so gewählt, dass die Unschärfe-Prüfung des Harness sie nicht verwechselt.
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d

FAELLE = [
    # B1 Betragsform hinter Kennungs-Etikett (Depot/Kunden-Nr.)
    F("b1_depot_gleich", ["Musterbank AG · Kaiserstraße 1 · 60311 Frankfurt am Main", "",
                          "Depotauszug per 31.12.2025",
                          "Depot-Nr. 712.345.678\t\tKunden-Nr. 4.711.081",
                          "Wertpapier\t\tStück\t\tKurswert EUR",
                          "Deutsche Telekom AG\t\t200\t\t5.432,10"],
      ["712.345.678", "4.711.081"], scans=((200, 0.0, None),)),
    F("b1_vers_var", ["Musterleben Versicherung AG – Standmitteilung 2025",
                      "Versicherungsschein-Nr. 34.567.890",
                      "Kundennummer: 1.258.093",
                      "Ihre Versicherungssumme von 50.000 EUR bleibt unverändert."],
      ["34.567.890", "1.258.093"]),
    F("b1_gegenprobe", ["Auszahlung aus Ihrem Vertrag 47.897.336.2 zum 01.12.2025.",
                        "Bausparsumme: 50.000 EUR, Guthaben 12.345 EUR"],
      ["47.897.336.2"]),
    # B2 Kassenzeichen
    F("b2_kasse_gleich", ["Stadt Augsburg – Stadtkasse", "Grundsteuerbescheid 2025", "Kassenzeichen: 921.103.215",
                          "Bitte geben Sie bei Zahlungen stets das Kassenzeichen an."],
      ["921.103.215"]),
    F("b2_kasse_var", ["Gebührenbescheid Abfallentsorgung 2025",
                       "Kassenzeichen 6.120.334.871",
                       "Fällig am 15.05.2025: 312,00 EUR"],
      ["6.120.334.871"]),
    # B3 Tabellenspalte unter Kennungs-Kopf
    F("b3_tab_gleich", ["Bestandsliste Kunde", "Sparte\t\tVertragsnummer\t\tBeitrag",
                        "Bausparen\t\t6.012.345.678\t\t50,00", "Fondsdepot\t\t893.104.552\t\t100,00"],
      ["6.012.345.678", "893.104.552"]),
    F("b3_tab_var", ["Vertragsübersicht", "Gesellschaft\t\tVers.-Nr.\t\tJahresbeitrag",
                     "Musterleben AG\t\t52.418.736\t\t480,00 EUR", "Bausparkasse Süd\t\t3.904.617.205\t\t600,00 EUR"],
      ["52.418.736", "3.904.617.205"]),
    # B10 Konto ohne "Nr." / Kontoverbindung / Bankverbindung
    F("b10_konto_gleich", ["Alternativ: Sparkonto 3182736455, Tagesgeldkonto 5928374610",
                           "Gepfändet wird das Guthaben auf dem Konto 1234567890 (Pfändungsschutzkonto).",
                           "Kontoverbindung: 7362514098, BLZ 720 500 00",
                           "Bankverbindung: Konto 2468013579 bei der Stadtsparkasse Augsburg"],
      ["3182736455", "5928374610", "1234567890", "7362514098", "2468013579"]),
    F("b10_konto_var", ["Der Beitrag wird vom Girokonto 4455667788 (BLZ 720 500 00) abgebucht.",
                        "Erstattung bitte auf Konto 9182736450 bei der Raiffeisenbank Augsburg."],
      ["4455667788", "9182736450"]),
    # B11 zweite Steuer-ID einer Aufzählung / Zwischenwort mit Ziffer
    F("b11_stid_gleich", ["Identifikationsnummer: Ehemann 10 163 985 243, Ehefrau 30 268 175 922",
                          "Steuer-ID Kind 1: 14 208 593 466"],
      ["10163985243", "30268175922", "14208593466"]),
    F("b11_stid_var", ["Identifikationsnummern: 47 036 892 451 (Ehemann), 65 129 830 677 (Ehefrau)",
                       "IdNr. des 2. Kindes: 27 418 360 251"],
      ["47036892451", "65129830677", "27418360251"]),
    # B12 BG-Nummer / AZR-Nummer / "Nummer der …"
    F("b12_bg_gleich", ["BG-Nummer: 96202BG0012345",
                        "Nummer der Bedarfsgemeinschaft bitte stets angeben: 96202//0012345",
                        "AZR-Nummer: 123456789012", "Nummer des Nationalpasses: U12345678"],
      ["96202BG0012345", "96202//0012345", "123456789012", "U12345678"]),
    F("b12_bg_var", ["Jobcenter Augsburg-Land – Änderungsbescheid",
                     "BG-Nummer 96202BG0067890",
                     "AZR-Nummer 987650432198"],
      ["96202BG0067890", "987650432198"]),
    # B13 Ausweis-Etikett ohne "Nr." im Fließtext
    F("b13_ausweis_gleich", ["Der Antragsteller hat sich mit seinem Reisepass CF9JKRTN7 ausgewiesen.",
                             "Die Ehefrau legte ihren Personalausweis LZ6KR4P9T vor."],
      ["CF9JKRTN7", "LZ6KR4P9T"]),
    F("b13_ausweis_var", ["Legitimiert durch Personalausweis T22K0M9P4, ausgestellt von der Stadt Augsburg.",
                          "Zusätzlich vorgelegt: Reisepass C7HJ2NP4X (gültig bis 03/2032)."],
      ["T22K0M9P4", "C7HJ2NP4X"]),
    # B15 USt-IdNr. eines Einzelunternehmers neben "·"
    F("b15_ust_gleich", ["Mit freundlichen Grüßen", "Gottfried Brezelmeier",
                         "Brezelmeier Haustechnik e.K. · Inhaber Gottfried Brezelmeier",
                         "Steuernummer 178/123/45678 · USt-IdNr. DE287654321"],
      ["178/123/45678", "DE287654321"]),
    F("b15_ust_var", ["Malerbetrieb Anton Huberle e.K. · Gartenweg 3 · 86199 Augsburg",
                      "Inhaber: Anton Huberle · Steuer-Nr. 102/234/56789 · USt-IdNr. DE312845670"],
      ["102/234/56789", "DE312845670"]),
    # B19 eTIN
    F("b19_etin_gleich", ["Ausdruck der elektronischen Lohnsteuerbescheinigung für 2007", "eTIN: ZWCKQRN85C03"],
      ["ZWCKQRN85C03"]),
    F("b19_etin_var", ["Ausdruck der elektronischen Lohnsteuerbescheinigung für 2008", "eTIN: RMPLHLDG57K14T"],
      ["RMPLHLDG57K14T"]),
    # B21/B22 Fehltreffer der Namenserkennung (Fachwörter)
    F("b21_ner_gleich", ["Festgesetzt werden: Einkommensteuer 4.812,00 EUR", "Bruttoarbeitslohn\t\t41.250,00 EUR",
                         "Kindergeldberechtigte Person: siehe Seite 2", "Wichtigkeit: Hoch\t\tAnlagen: Bescheid.pdf",
                         "Zweitkonto der Ehefrau: AT84 2011 1282 6541 8800"],
      []),
    F("b21_ner_var", ["Festgesetzt wird: Solidaritätszuschlag 0,00 EUR", "Einbehaltene Lohnsteuer\t\t5.102,00 EUR",
                      "Kirchensteuer\t\t312,00 EUR", "Anspruchsberechtigte Person: siehe Anlage",
                      "Anlagen: Steuerbescheid_2024.pdf", "Drittkonto des Sohnes: AT26 3200 0000 1234 5678"],
      []),
    # B24 Fehlalarm "Mein Zeichen" hinter geschwärzter Kundennummer
    F("b24_zeichen_gleich", ["Agentur für Arbeit Augsburg", "Ihre Kundennummer: 962D654321\t\tMein Zeichen: 832.3 – 962D654321"],
      ["962D654321"]),
    F("b24_zeichen_var", ["Agentur für Arbeit Augsburg", "Kundennummer: 962D778899 · Unser Zeichen: 832.31"],
      ["962D778899"]),
]
