# Gegenprüfung Sparte "digital" (Digitales): je Befund die Zeile des Prüfers (…_gleich) und eine leicht andere,
# realistische Schreibweise (…_var). Alle Namen, Kennungen und Adressen erfunden.
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d

FAELLE = [
    # B4/B5 Zwischenwörter zwischen Etikett und kurzem Wert
    F("b4_zw_gleich", ["Bestätigung Ihres Online-Antrags", "Vorgangsnummer Ihres Online-Antrags: 7HXK-92LQ-QA",
                       "Bitte geben Sie diese Nummer bei Rückfragen an."],
      ["7HXK-92LQ-QA"]),
    F("b4_zw_var", ["Eingangsbestätigung", "Schadennummer zu Ihrer Online-Meldung: SK-7Q3-XW92",
                    "Bitte geben Sie diese Nummer bei Rückfragen an."],
      ["SK-7Q3-XW92"]),
    F("b4_zw_lang", ["Eingangsbestätigung", "Versicherungsnummer Ihres Hausratvertrags: HR-4711-0815"],
      ["HR-4711-0815"]),
    F("b5_ref_gleich", ["Ihre Online-Schadenmeldung ist eingegangen.", "Referenznummer für Rückfragen: KX-4711-QZ",
                        "Kundennummer bei der Musterbank: Q-0815"],
      ["KX-4711-QZ", "Q-0815"]),
    # B6 Benutzerkennung / Aktivierungscode
    F("b6_portal_gleich", ['Ihr Zugang zum Kundenportal "MeineVersicherung"', "Benutzerkennung: zwackelq",
                           "Ihr Aktivierungscode: 7HXK-92LQ", "Der Code ist 14 Tage gültig."],
      ["zwackelq", "7HXK-92LQ"]),
    F("b6_portal_var", ["Zugangsdaten für die Service-App", "Ihre Zugangskennung: brezelg",
                        "Freischaltcode: QM7Z-K4XR"],
      ["brezelg", "QM7Z-K4XR"]),
    # B7 Plattform-Benutzernamen
    F("b7_plattform_gleich", ["Schadenmeldung Internetschutz (Kaufbetrug)",
                              "Verkäufer auf Kleinanzeigen, Nutzername: rumpelmayr_hilde",
                              "Mein eBay-Mitgliedsname: hilde.rumpel57", "Profilname auf Vinted: HildeR1957"],
      ["rumpelmayr_hilde", "hilde.rumpel57", "HildeR1957"]),
    F("b7_plattform_var", ["Schadenmeldung Internetschutz (Identitätsdiebstahl)",
                           "Kleinanzeigen-Profil: zeitlhofer_korbi", "eBay-Name: korbinian.z84",
                           "Nutzer-Name bei Vinted: KorbiZ1984"],
      ["zeitlhofer_korbi", "korbinian.z84", "KorbiZ1984"]),
    # B8 Messenger-Handles ohne "@"
    F("b8_handles_gleich", ["Erreichbarkeit des Kunden", "Telegram: t.me/lenchen_wiese82", "Snapchat: lenchenwiese",
                            "Signal-Benutzername: lenchen.82"],
      ["lenchen_wiese82", "lenchenwiese", "lenchen.82"]),
    F("b8_handles_var", ["Kontaktwege laut Kundenbogen", "Telegram-Name: korbi_zeitl84", "Snapchat-Name: korbizeitl",
                         "Signal: korbi.84"],
      ["korbi_zeitl84", "korbizeitl", "korbi.84"]),
    # B9 IPv6
    F("b9_ipv6_gleich", ["Elektronische Einwilligung",
                         "Zustimmung erteilt am 12.03.2025 um 14:08 Uhr von 2001:db8:85a3::8a2e:370"],
      ["2001:db8:85a3::8a2e:370"]),
    F("b9_ipv6_var_a", ["Protokoll der elektronischen Signatur",
                        "Unterzeichnet am 12.03.2025 14:08 von IP-Adresse 2a02:8070:a2c1:4f00:d5e3:91b2:7c4a:1e08"],
      ["2a02:8070:a2c1:4f00:d5e3:91b2:7c4a:1e08"]),
    F("b9_ipv6_var_b", ["Protokoll der elektronischen Signatur",
                        "Unterzeichnet am 12.03.2025 14:08, IP: 2003:c2:7f1a:9e00:b5d4:3c2e:8e7f:42a1"],
      ["2003:c2:7f1a:9e00:b5d4:3c2e:8e7f:42a1"]),
    F("b9_ipv6_var_c", ["Zustimmung zur elektronischen Kommunikation",
                        "erteilt am 12.03.2025 von fe80::1c4b:a2ff:fe3d:9b7e (Mobilgerät)"],
      ["fe80::1c4b:a2ff:fe3d:9b7e"]),
    # B14 Postnummer
    F("b14_post_gleich", ["Lieferadresse für das Ersatzgerät", "Postnummer 76543210 (Packstation 117)"],
      ["76543210"]),
    F("b14_post_var", ["Versand des Ersatzgeräts an die Packstation 204", "Ihre Postnummer: 58403917"],
      ["58403917"]),
    # B16 verschleierte E-Mail
    F("b16_mail_gleich", ["Rückmeldung zur Schadenmeldung",
                          "Bitte schreiben Sie mir an q.zwackelhuber(at)gmx.de oder quirin.zw [at] web [dot] de"],
      ["q.zwackelhuber(at)gmx.de", "quirin.zw [at] web [dot] de"]),
    F("b16_mail_var", ["Rückmeldung zur Schadenmeldung", "Antwort bitte an hilde.rumpel [at] t-online.de"],
      ["hilde.rumpel [at] t-online.de"]),
    # B17 Ticket mit "#"
    F("b17_ticket_gleich", ["Ihre Anfrage wurde unter der Ticketnummer #A-4711 erfasst.",
                            "Bitte antworten Sie nicht auf diese E-Mail."],
      ["A-4711"]),
    F("b17_ticket_var", ["Ihr Ticket #KX-2291 wurde geschlossen.", "Bitte antworten Sie nicht auf diese E-Mail."],
      ["KX-2291"]),
    # B18 Geräte-ID / VideoIdent-Vorgang
    F("b18_geraet_gleich", ["Antrag gestartet\t\t12.03.2025 14:03:22\t\tGeräte-ID 3f2504e0-4f89",
                            "Identifizierung\t\t12.03.2025 14:05:10\t\tVideoIdent VID-77812-QZ"],
      ["3f2504e0-4f89", "VID-77812-QZ"], scans=((200, 0.0, None),)),
    F("b18_geraet_var", ["Schadenmeldung Smartphone (App)", "Geräte-ID: 6D92078A-8246-4BA4-AE5B-76104861E7DC",
                         "Ident-Vorgang: IDN-4K7Q2"],
      ["6D92078A-8246-4BA4-AE5B-76104861E7DC", "IDN-4K7Q2"]),
    # B20 Namen/Kennungen in Profil-URLs und Links
    F("b20_url_gleich", ["Kontaktdaten des Kunden (Stammdatenblatt)", "Facebook: facebook.com/quirin.zwackelhuber",
                         "https://portal.mv-versich.de/dok?kdnr=4711081&vsnr=LV2024887766&name=Zwackelhuber"],
      ["quirin.zwackelhuber", "LV2024887766", "Zwackelhuber"]),
    F("b20_url_var", ["Kontaktdaten des Kunden (Stammdatenblatt)",
                      "Facebook-Profil: https://www.facebook.com/hildegard.rumpelmayr.7",
                      "Ihr Dokument: https://kundenportal.example-vers.de/akte?vn=Rumpelmayr&police=HR-2291-0047"],
      ["hildegard.rumpelmayr", "Rumpelmayr", "HR-2291-0047"]),
    # B22 Fehltreffer der Namenserkennung (E-Mail-/Bankwörter)
    F("b22_ner_gleich", ["Best regards, Irmtraud Ölschläger", "\t\tMandatsref. MV-0815-4711-01",
                         "Notiz: VN ab 01.04. im Pflegeheim, Post bitte an den Sohn, Kellerstraße 7"],
      ["Ölschläger", "MV-0815-4711-01", "Kellerstraße 7"]),
    F("b22_ner_var", ["Kind regards, Hildegard Rumpelmayr", "\t\tMandatsreferenz MV-2291-0047-02",
                      "Notiz: Post ab sofort an die Tochter, Gartenweg 3"],
      ["Rumpelmayr", "MV-2291-0047-02", "Gartenweg 3"]),
    # B23 OCR-Lesung "Videoldent" -> Name (Scan)
    F("b23_videoident", ["Identifizierung per VideoIdent abgeschlossen", "Identifizierung\t\t12.03.2025\t\tVideoIdent"],
      [], scans=((200, 0.0, None),)),
    # B24 Fehlalarm "TAN" als Nachname
    F("b24_tan_gleich", ["Ausgeführt am 12.03.2025 · TAN-Verfahren: pushTAN · Auftrags-ID: 8XK2-77LQ",
                         "SMS-TAN gesendet\t\t12.03.2025 14:07:45"],
      ["8XK2-77LQ"]),
    F("b24_tan_var", ["Freigabe per chipTAN am 12.03.2025", "Die TAN-Liste ist ungültig.",
                      "Photo-TAN-Verfahren aktiviert"],
      []),
]
