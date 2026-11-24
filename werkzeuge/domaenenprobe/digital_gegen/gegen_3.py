# Gegenprüfung Sparte "digital", Lauf 3: Abgrenzung der Klassen und Gegenproben für die Abhilfen. Alles erfunden.
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d

FAELLE = [
    # B23: Seite des Prüfers unverändert als Scan (OCR "Videoldent" -> Name?)
    F("r3_protokoll_scan", ["Protokoll zum Online-Antrag Risikolebensversicherung",
                            "Ereignis\t\tZeitpunkt\t\tAngaben",
                            "Antrag gestartet\t\t12.03.2025 14:03:22\t\tGeräte-ID 3f2504e0-4f89",
                            "Identifizierung\t\t12.03.2025 14:05:10\t\tVideoIdent VID-77812-QZ",
                            "E-Mail bestätigt\t\t12.03.2025 14:06:01\t\tq.zwackelhuber@gmx.de",
                            "SMS-TAN gesendet\t\t12.03.2025 14:07:45\t\t+49 151 2345 6789",
                            "Unterschrift\t\t12.03.2025 14:08:30\t\tQuirin Zwackelhuber",
                            "IPv6-Adresse\t\t12.03.2025 14:08:30\t\t2001:db8:85a3::8a2e:370"],
      ["Zwackelhuber"], scans=((200, 0.0, None),), text=False),
    # B12-Klasse: "<Kürzel>-Nummer" außerhalb der Wissensbasis (Maklerbezug)
    F("r3_kuerzel_nummer", ["Ihre Verträge bei uns", "LV-Nummer: 47110815", "BU-Nummer 0815-4711-22",
                            "Bedarfsgemeinschafts-Nummer: 96202BG0055501"],
      ["47110815", "0815-4711-22", "96202BG0055501"]),
    # B6-Klasse: Benutzerkennung mit/ohne Ziffern, Aktivierungscode mit Ziffern
    F("r3_benutzer_ziffern", ["Ihre Zugangsdaten", "Benutzerkennung: zwackel1959", "Benutzerkennung (alt): hoffk7",
                              "Aktivierungscode: 48213957"],
      ["zwackel1959", "hoffk7", "48213957"]),
    # B15-Klasse: Kunde ist Freiberufler, Signatur mit "·"
    F("r3_ust_kunde", ["Mit freundlichen Grüßen", "Quirin Zwackelhuber · Fotografie · Lerchenfeldstraße 12 · 86150 Augsburg",
                       "USt-IdNr. DE298765431"],
      ["Zwackelhuber", "DE298765431"]),
    F("r3_ust_kunde_ohne", ["Mit freundlichen Grüßen", "Quirin Zwackelhuber, Fotografie, Lerchenfeldstraße 12, 86150 Augsburg",
                            "USt-IdNr. DE298765431"],
      ["Zwackelhuber", "DE298765431"]),
    # Gegenproben zur Abhilfe B1: Beträge hinter Konto-Etiketten bleiben, gemischte Gruppen sind Kennungen
    F("r3_betrag_gegen", ["Darlehenskonto: 50.000 EUR (nach Zuteilung)", "Beitragskonto: Saldo 1.250 EUR",
                          "Kassenzeichen: 5.0101.123456.7"],
      ["5.0101.123456.7"]),
    # B16: weitere verschleierte Schreibweise
    F("r3_mail_dot", ["Antwort bitte an quirin.zw(at)web(dot)de"], ["quirin.zw(at)web(dot)de"]),
    # B9: weitere echte IPv6-Formen (Kabel/Mobilfunk)
    F("r3_ipv6_mehr", ["Signaturprotokoll", "IP-Adresse: 2a01:598:b1a2:4c3d:1d2e:3f4a:5b6c:7d8e"],
      ["2a01:598:b1a2:4c3d:1d2e:3f4a:5b6c:7d8e"]),
    F("r3_ipv6_mehr2", ["Signaturprotokoll", "IPv6: 2a00:20:c0d2:ee1f:b9a1:fe5c:a3d4:e8f2"],
      ["2a00:20:c0d2:ee1f:b9a1:fe5c:a3d4:e8f2"]),
]
