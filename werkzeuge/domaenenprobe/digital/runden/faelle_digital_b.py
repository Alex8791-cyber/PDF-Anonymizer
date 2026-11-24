# Domänen-Probe "Digitales": E-Mail-Ausdrucke, Kundenportal, Online-Antrag-Protokoll, Paket-Tracking,
# Messenger/Social Media, Telefonnotizen, Online-Banking-Belege. Alle Namen und Nummern sind erfunden.
def F(name, zeilen, geheim, scans=(), **kw):
    return dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans, **kw)


S200 = ((200, 0.0, None),)

FAELLE = [
    # ------------------------------------------------------------------ E-Mail-Ausdrucke
    F("email_outlook_kopf", [
        "Von: Zwackelhuber, Quirin <q.zwackelhuber@gmx.de>",
        "Gesendet: Dienstag, 11. März 2025 09:14",
        "An: schaden@makler-sonnleitner.de",
        "Cc: Irmtraud Ölschläger <irmi.oe@web.de>",
        "Betreff: AW: Wasserschaden Kellerstraße 7 – Schaden-Nr. 2025-0815",
        "",
        "Hallo Herr Sonnleitner,",
        "anbei die Fotos. Die Rechnung des Installateurs folgt.",
        "Viele Grüße",
        "Quirin Zwackelhuber",
        "Gesendet von meinem iPhone",
    ], ["Zwackelhuber", "q.zwackelhuber@gmx.de", "Ölschläger", "irmi.oe@web.de", "Kellerstraße 7"], scans=S200),

    F("email_englisch_kopf", [
        "From: \"Ölschläger, Irmtraud\" <i.oelschlaeger@t-online.de>",
        "Sent: Monday, March 10, 2025 4:02 PM",
        "To: Service <service@musterversicherung.de>",
        "Subject: RE: Policy 12-3456789 / Customer No. 4711-0815",
        "Dear Sir or Madam, please find attached my claim form.",
        "Best regards, Irmtraud Ölschläger",
    ], ["Ölschläger", "i.oelschlaeger@t-online.de", "12-3456789", "4711-0815"]),

    F("email_weiterleitung", [
        "-----Ursprüngliche Nachricht-----",
        "Von: Brezelmeier Gottfried [mailto:g.brezelmeier@online.de]",
        "Gesendet: Freitag, 7. März 2025 18:22",
        "An: info@makler-sonnleitner.de",
        "Betreff: Kündigung Hausrat Vertrag 4711-0815-03",
        "Sehr geehrte Damen und Herren, hiermit kündige ich meine Hausratversicherung zum 01.06.2025.",
        "Gottfried Brezelmeier, Kellerstraße 7, 86152 Augsburg",
    ], ["Brezelmeier", "g.brezelmeier@online.de", "4711-0815-03", "Kellerstraße 7"]),

    F("email_signatur_einzelunternehmer", [
        "Mit freundlichen Grüßen",
        "Gottfried Brezelmeier",
        "Brezelmeier Haustechnik e.K. · Inhaber Gottfried Brezelmeier",
        "Mobil: +49 (0) 157 1234 5678 · Fax: 0821 4567-99",
        "Steuernummer 178/123/45678 · USt-IdNr. DE287654321",
    ], ["Brezelmeier", "15712345678", "178/123/45678", "DE287654321"]),

    # ------------------------------------------------------------------ Kundenportal / Tickets / Tracking
    F("kundenportal_zugang", [
        "Ihr Zugang zum Kundenportal \"MeineVersicherung\"",
        "Benutzerkennung: zwackelq",
        "Kunden-ID: K-0815-47",
        "Ihr Aktivierungscode: 7HXK-92LQ",
        "Der Code ist 14 Tage gültig.",
    ], ["zwackelq", "K-0815-47", "7HXK-92LQ"]),

    F("kundenportal_nachricht", [
        "Nachricht aus Ihrem Kundenportal – Postfach",
        "Vorgangs-ID: 7f3e2a1b\t\tEingang: 12.03.2025 14:03",
        "Vorgangsnummer Ihres Online-Antrags: 7HXK-92LQ-QA",
        "Ihre Anfrage wurde unter der Ticketnummer #A-4711 erfasst.",
        "Ticket-ID: INC0012345",
        "[Ticket#2025031110000123] Rückfrage zu Ihrem Schaden",
    ], ["7f3e2a1b", "7HXK-92LQ-QA", "A-4711", "INC0012345", "2025031110000123"]),

    F("paket_tracking", [
        "Versandbestätigung Ersatzgerät (Handyversicherung)",
        "Empfänger: Quirin Zwackelhuber",
        "Packstation 123 · Postnummer 12345678 · 86150 Augsburg",
        "Sendungsnummer: 00340434161234567890",
        "Paketnummer (DHL): JJD000390007891234567",
        "Tracking-ID: 1Z999AA10123456784",
    ], ["Zwackelhuber", "12345678", "00340434161234567890", "JJD000390007891234567", "1Z999AA10123456784"]),

    # ------------------------------------------------------------------ Online-Antrag
    F("online_antrag_protokoll", [
        "Protokoll zum Online-Antrag Risikolebensversicherung",
        "Ereignis\t\tZeitpunkt\t\tAngaben",
        "Antrag gestartet\t\t12.03.2025 14:03:22\t\tGeräte-ID 3f2504e0-4f89",
        "Identifizierung\t\t12.03.2025 14:05:10\t\tVideoIdent VID-77812-QZ",
        "E-Mail bestätigt\t\t12.03.2025 14:06:01\t\tq.zwackelhuber@gmx.de",
        "SMS-TAN gesendet\t\t12.03.2025 14:07:45\t\t+49 151 2345 6789",
        "Unterschrift\t\t12.03.2025 14:08:30\t\tQuirin Zwackelhuber",
        "IPv6-Adresse\t\t12.03.2025 14:08:30\t\t2001:db8:85a3::8a2e:370",
    ], ["3f2504e0-4f89", "VID-77812-QZ", "q.zwackelhuber@gmx.de", "15123456789", "Zwackelhuber",
        "2001:db8:85a3::8a2e:370"], scans=S200),

    F("antrag_datenexport", [
        "Antragsdaten (Export Vergleichsrechner)",
        "VN_NAME: Zwackelhuber\t\tVN_VORNAME: Quirin",
        "VN_GEBDAT: 1959-03-03\t\tVN_GEBORT: Augsburg",
        "VN_IBAN: DE29720500000240123456",
        "VN_EMAIL: q.zwackelhuber@gmx.de",
        "VN_TEL: 0151 23456789\t\tSESSION_ID: 8d7a3c1e9f",
    ], ["Zwackelhuber", "1959-03-03", "DE29720500000240123456", "q.zwackelhuber@gmx.de", "015123456789",
        "8d7a3c1e9f"]),

    F("geraete_ids_fliesstext", [
        "Schadenmeldung Smartphone (Online-Formular)",
        "Gerät: iPhone 14, Seriennummer F2LXK9Q1N72J",
        "Geräte-ID des Kundenkontos: 3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        "Apple-ID des Kunden: quirin.zw@icloud.com",
        "Letzte Anmeldung von IPv6 2001:db8:85a3::8a2e:370:7334",
    ], ["F2LXK9Q1N72J", "3f2504e0-4f89-11d3-9a0c-0305e82c3301", "quirin.zw@icloud.com",
        "2001:db8:85a3::8a2e:370:7334"]),

    # ------------------------------------------------------------------ Messenger / Social Media
    F("messenger_whatsapp", [
        "WhatsApp-Chat mit Quirin Zwackelhuber (exportiert)",
        "[12.03.25, 14:03:11] Quirin Zwackelhuber: Hallo, anbei die Fotos vom Wasserschaden",
        "[12.03.25, 14:05:42] Sonnleitner Versicherungsmakler: Danke, ich melde es.",
        "[12.03.25, 14:06:10] Quirin Zwackelhuber: Meine neue Handynummer ist 0151 23456789",
        "[12.03.25, 14:07:30] Quirin Zwackelhuber: Meine Frau erreichen Sie unter 0176 98765432",
        "[12.03.25, 14:09:02] Irmi: Bin ab Montag im Klinikum, bitte nur per Mail: irmi.oe@web.de",
    ], ["Zwackelhuber", "015123456789", "017698765432", "irmi.oe@web.de"]),

    F("social_profile", [
        "Kontaktdaten des Kunden (Stammdatenblatt)",
        "Facebook: facebook.com/quirin.zwackelhuber",
        "Xing: www.xing.com/profile/Gottfried_Brezelmeier",
        "LinkedIn: linkedin.com/in/irmtraud-oelschlaeger-4a7b2c",
        "Skype: live:.cid.4f8a2b9c1d3e",
        "Threema-ID: 7HX3KJ9P",
        "Telegram: t.me/lenchen_wiese82",
    ], ["quirin.zwackelhuber", "Gottfried_Brezelmeier", "irmtraud-oelschlaeger", "4f8a2b9c1d3e", "7HX3KJ9P",
        "lenchen_wiese82"]),

    F("cyber_identitaetsdiebstahl", [
        "Schadenmeldung Internetschutz: Identitätsdiebstahl",
        "Betroffene Person: Irmtraud Ölschläger",
        "eBay-Mitgliedsname: irmi_oe_1979",
        "PayPal-Konto: irmi.oe@web.de",
        "Unberechtigte Bestellung, Amazon-Bestellnummer 302-1234567-7654321",
        "Missbräuchliche Zahlung, PayPal-Transaktionscode 9HU12345HB9876543",
    ], ["Ölschläger", "irmi_oe_1979", "irmi.oe@web.de", "302-1234567-7654321", "9HU12345HB9876543"]),

    # ------------------------------------------------------------------ Telefonnotizen
    F("telefonnotiz", [
        "Telefonnotiz",
        "Datum: 12.03.2025, 10:15 Uhr\t\taufgenommen: MS",
        "Anrufer: Hr. Zwackelhuber jun. (Sohn der VN Irmtraud Ölschläger)",
        "Rückruf erbeten unter 0821 / 45 67 89 oder mobil 0151-2345678",
        "Anliegen: Kündigung Hausrat, Vertrag 4711-0815-03",
        "Notiz: VN ab 01.04. im Pflegeheim, Post bitte an den Sohn, Kellerstraße 7",
    ], ["Zwackelhuber", "Ölschläger", "0821456789", "01512345678", "4711-0815-03", "Kellerstraße 7"], scans=S200),

    F("telefonnotiz_stichworte", [
        "TN 12.03. – Fr. Bichlmaier (Tochter) angerufen, bittet um Rückruf",
        "Tel. 0176/98 76 54 32, ab 17 Uhr",
        "Kd. Brezelmeier: neue Mobilnr. 0157-1234 5678, alte Nr. löschen",
        "AB: Herr Pfannkuch, Rückruf wg. Riester, Tel 08 21/71 23 45",
    ], ["Bichlmaier", "017698765432", "015712345678", "Pfannkuch", "0821712345"]),

    # ------------------------------------------------------------------ Online-Banking
    F("ueberweisungsbeleg", [
        "Überweisungsbeleg (Online-Banking)",
        "Auftraggeber: Quirin Zwackelhuber",
        "IBAN Auftraggeber: DE29 7205 0000 0240 1234 56",
        "Empfänger: Irmtraud Ölschläger",
        "IBAN Empfänger: DE66 7209 0000 0001 2345 67",
        "Verwendungszweck: Kd-Nr 4711 Vers-Nr 12345678 Erstattung Brille",
        "Ausgeführt am 12.03.2025 · TAN-Verfahren: pushTAN · Auftrags-ID: 8XK2-77LQ",
    ], ["Zwackelhuber", "DE29720500000240123456", "Ölschläger", "DE66720900000001234567", "12345678",
        "8XK2-77LQ"]),

    F("kontoauszug", [
        "Kontoauszug Nr. 3/2025\t\tKonto 1234567890",
        "Kontoinhaber: Quirin Zwackelhuber",
        "12.03.\t\tLastschrift Musterversich. AG\t\t-45,90",
        "\t\tMandatsref. MV-0815-4711-01",
        "13.03.\t\tGutschrift Irmtraud Ölschläger\t\t250,00",
        "\t\tDE66720900000001234567",
        "14.03.\t\tKartenzahlung girocard\t\t-23,10",
    ], ["1234567890", "Zwackelhuber", "MV-0815-4711-01", "Ölschläger", "DE66720900000001234567"]),

    # ------------------------------------------------------------------ Über-Schwärzung (harmlose Wörter)
    F("behoerden_kanaele_harmlos", [
        "Zuständige Stellen: Finanzamt Augsburg-Stadt, Familienkasse Bayern Süd, Jobcenter Augsburg-Stadt",
        "Deutsche Rentenversicherung Schwaben, Bundeszentralamt für Steuern, Elterngeldstelle Schwaben",
        "Kanäle: WhatsApp, Signal, Threema, Telegram, Facebook Messenger, Snapchat, TikTok",
        "Zahlarten: VISA, Mastercard, American Express, PayPal, Klarna, giropay",
        "Ausweisdokumente: Personalausweis, Reisepass, Aufenthaltstitel, Fiktionsbescheinigung",
        "Online-Banking mit pushTAN, chipTAN oder photoTAN; Login mit Benutzerkennung und PIN",
    ], []),
]
