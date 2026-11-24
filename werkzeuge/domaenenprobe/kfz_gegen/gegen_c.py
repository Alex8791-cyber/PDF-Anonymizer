# Gegenprüfung Kfz, Teil C: Über-Schwärzung (Firmen hinter Rollen, Marken/Modelle, Modellcodes als Kennzeichen,
# Überschriften/Feldbezeichner als Name, Fahrbahnen als Straße, HSN/Feldverweise als Kennung).
# Je Befund: gleiche Zeilen wie beim Prüfer + leicht andere realistische Schreibweise. Geheim sind nur die (erfundenen)
# Personenangaben, nicht die Firmen.
def F(name, zeilen, geheim, scans=(), **extra):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(extra)
    return d


FAELLE = [
    # --- Befund 23: Firmen hinter Rollen-Etiketten -------------------------------------------------------------
    F("c01_firma_gleich", ["Beteiligte Unternehmen (ohne Privatpersonen)",
                           "Vermieter: Sixt GmbH & Co Autovermietung KG, Filiale Rosenheim",
                           "Vermieter: Europcar Autovermietung GmbH, Station Flughafen München",
                           "Werkstatt: A.T.U Auto-Teile-Unger GmbH & Co. KG",
                           "Halter: Stadtwerke Rosenheim GmbH & Co. KG",
                           "Halter: Spedition Wimmer & Söhne GmbH"], []),
    F("c02_firma_var", ["Beteiligte Unternehmen",
                        "Mietwagenfirma: Starcar Autovermietung GmbH",
                        "Gutachter: DEKRA Automobil GmbH, Niederlassung Rosenheim",
                        "Halter: Rosenheimer Verkehrsbetriebe GmbH",
                        "Leasinggeber: Volkswagen Leasing GmbH",
                        "Vermieterin: Buchbinder Rent-a-Car GmbH"], []),
    # --- Befund 24: Fahrzeug-, Wohnwagen-, Fahrradmarken/-modelle als Name ------------------------------------------
    F("c03_marken_gleich", ["Versicherte Fahrzeuge",
                            "Fahrzeug: Mofa Piaggio Ciao",
                            "Anhänger: Böckmann TPV, nur Haftpflicht",
                            "Wohnwagen Tabbert Rossini 540",
                            "Werkstattwagen Dacia Logan MCV",
                            "E-Bike-Hersteller im Tarif: Riese & Müller, Haibike, Kalkhoff, Gazelle"], []),
    F("c04_marken_var", ["Versicherte Fahrzeuge (Camping und Zweirad)",
                         "Wohnwagen: Hobby De Luxe 495 UL",
                         "Wohnmobil: Knaus Sun TI 650 MEG",
                         "E-Bike: Cube Kathmandu Hybrid SLX",
                         "Roller: Kymco Agility 125",
                         "Pkw: Seat Leon Sportstourer"], []),
    # --- Befund 25: Modellcodes als Kennzeichen ----------------------------------------------------------------
    F("c05_modelle_gleich", ["Fahrzeugübersicht für das Flottenangebot",
                             "Pkw: Toyota C-HR 1.8 Hybrid; Honda CR-V 2.0 i-MMD",
                             "Krad: KTM RC 390; Yamaha YZF-R1; Suzuki GSX-R 750",
                             "Lkw: DAF XF 480 FT"], []),
    F("c06_modelle_var", ["Fahrzeugübersicht für das Flottenangebot",
                          "Pkw: Honda HR-V 1.5 e:HEV; Nissan GT-R 3.8 V6; Renault ZOE R135",
                          "Krad: Yamaha YZF-R125; Suzuki GSX-S 1000",
                          "Lkw: DAF CF 450 FT"], []),
    # --- Befund 26: Überschriften und Feldbezeichner als Name -----------------------------------------------------
    F("c07_ueberschrift_gleich", ["Diebstahlanzeige Kfz",
                                  "Versicherungsnehmer: Theodor Wimmersberger",
                                  "Hauptfahrer: Fokko Grübelhuber",
                                  "Sozius: Jendrik Wimmersberger"],
      ["Wimmersberger", "Grübelhuber"]),
    F("c08_ueberschrift_var", ["Diebstahlanzeige Fahrrad",
                               "Unfallanzeige Kfz",
                               "Zweitfahrer: Okke Brünnhuber",
                               "Fahrzeugführer: Reinmar Grübelhuber",
                               "Beifahrerin: Gesche Kollmannsberger"],
      ["Brünnhuber", "Grübelhuber", "Kollmannsberger"]),
    # --- Befund 27: Fahrbahnen als Straße ---------------------------------------------------------------------
    F("c09_fahrbahn_gleich", ["Unfallschilderung (ohne Personenangaben)",
                              "Auf der A 8 Richtung Salzburg kam es zum Stau.",
                              "Auf der A 94 bei km 12,5 kam es zum Auffahrunfall; Umleitung über die St 2089."], []),
    F("c10_fahrbahn_var", ["Unfallschilderung (ohne Personenangaben)",
                           "Auf der B 15 kurz vor Rosenheim flog ein Stein gegen die Windschutzscheibe.",
                           "Unfallort: Auf der A 99, Höhe Ausfahrt Haar",
                           "Ich fuhr auf der B 304 Richtung Wasserburg."], []),
    # --- Befund 28: HSN/Feldverweise als Kennung ---------------------------------------------------------------
    F("c11_hsn_gleich", ["Fahrzeugdaten laut Zulassungsbescheinigung Teil I",
                         "Herstellerschlüsselnummer (HSN): 0603",
                         "Schlüssel-Nr. 2.1/2.2: 0005/CXY"], []),
    F("c12_hsn_var", ["Fahrzeugdaten für das Vergleichsangebot",
                      "Herstellerschlüssel-Nr.: 0588",
                      "Herstellernummer (zu 2.1): 0005",
                      "HSN-Nr. 0603 / TSN-Nr. BJT"], []),
]

SCAN = ((200, 0.0, None),)

FAELLE += [
    # --- Zusatzproben zu den Lecks (Ursachen trennen) -------------------------------------------------------
    F("c13_vkz_kompakt", ["Versicherungsbestätigung Mofa",
                          "Versicherungskennzeichen: 435GHT"], ["435GHT"]),
    F("c14_sensor_4ziffern", ["Willkommen im Telematik-Tarif, Ihr Sensor ist aktiviert.",
                              "Sensor-ID: TLX-PW48-HX73"], ["TLXPW48HX73"]),
    F("c15_geraete_4ziffern", ["Willkommen im Telematik-Tarif, Ihr Stecker ist aktiviert.",
                               "Geräte-ID: TLX-PW48-HX73"], ["TLXPW48HX73"]),
    F("c16_zb1_vorname_fremd", ["ZULASSUNGSBESCHEINIGUNG TEIL I",
                                "A  M-KS 4471\t\tB  14.09.2020",
                                "C.1.1  STEINLECHNER",
                                "C.1.2  GUNDOLF"], ["STEINLECHNER", "GUNDOLF"]),
    F("c17_zb1_fin_scan", ["Zulassungsbescheinigung Teil I (Kopie)",
                           "D.1  FORD\t\tD.3  FOCUS",
                           "E  WF0EXXGCDEKA12345",
                           "2.1  8566\t\t2.2  AQZ"], ["WF0EXXGCDEKA12345"], scans=SCAN),
    F("c18_rahmen_lang", ["Diebstahlanzeige E-Bike",
                          "Rahmennummer laut Rechnung: WAC1193K4471"], ["WAC1193K4471"]),
    F("c19_zusatzfahrer", ["Antrag Kfz-Versicherung – Fahrerangaben",
                           "Zusatzfahrer: Kriemhild Ottenschläger"], ["Ottenschläger", "Kriemhild"]),
    F("c20_hauptfahrerin", ["Antrag Kfz-Versicherung – Fahrerangaben",
                            "Hauptfahrerin: Ortrun Haberlander"], ["Haberlander", "Ortrun"]),
    F("c21_sozia", ["Motorradunfall – verletzte Personen",
                    "Sozia: Jorinde Wittmannsgruber"], ["Wittmannsgruber", "Jorinde"]),
]
