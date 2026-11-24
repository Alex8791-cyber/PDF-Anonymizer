# Kritik-Lauf K1: Layouts aus dem Briefverkehr (Kastenformular mit Etikett über dem Wert, Infoblock neben dem
# Anschriftfeld, Bezugszeichenzeile, Folgeseite, Fußzeile, senkrechter Randvermerk) – erfundene Personen/Nummern
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import bau

SCAN = ((200, 0.8, 70),)


def F(name, seiten, geheim, **kw):
    d = dict(name=name, zeilen=[], geheim=geheim, bauer=bau.bauer(seiten))
    d.update(kw)
    return d


def kasten(y, xs, paare, lg=7.5, wg=10, schritt=27):
    """Kastenformular: Etikett klein, darunter der Wert."""
    aus = []
    for i, (etiketten, werte) in enumerate(paare):
        yy = y + i * schritt
        for x, e, w in zip(xs, etiketten, werte):
            aus.append((x, yy, e, lg))
            aus.append((x, yy + 12, w, wg))
    return aus


KASTEN2 = [[(50, 60, "Schadenanzeige zur Hausratversicherung", 13), (50, 85, "1. Versicherungsnehmer", 10)]
           + kasten(110, [50, 300], [
               (("Name, Vorname", "Geburtsdatum"), ("Kraxenberger, Wendelin", "14.05.1971")),
               (("Straße, Hausnummer", "PLZ, Wohnort"), ("Hölzlweg 12", "83626 Valley")),
               (("Telefon (tagsüber)", "E-Mail"), ("08024 47119", "w.kraxenberger@t-online.de")),
               (("Versicherungsschein-Nr.", "Schadentag"), ("HR-7740-2291-05", "03.11.2026")),
           ])
           + [(50, 240, "2. Schadenhergang", 10),
              (50, 256, "Beim Nachhausekommen bemerkten wir, dass die Terrassentür aufgehebelt war.", 10)]]

KASTEN3 = [[(50, 60, "Antrag auf Unfallversicherung – Angaben zur zu versichernden Person", 12)]
           + kasten(95, [50, 220, 390], [
               (("Name", "Vorname", "Geburtsdatum"), ("Pichlmeier", "Notburga", "02.08.1958")),
               (("Straße, Hausnummer", "PLZ", "Ort"), ("Am Gänsbichl 4", "84453", "Mühldorf a. Inn")),
               (("Telefon", "Beruf (genaue Tätigkeit)", "Arbeitgeber"),
                ("08631 98765", "Pflegehelferin", "Seniorenstift St. Josef")),
               (("IBAN", "", "Kreditinstitut"), ("DE97 7115 0000 0020 3040 50", "", "Sparkasse Altötting-Mühldorf")),
           ])
           + [(50, 225, "Gewünschte Leistungen: Invaliditätsgrundsumme 150.000 EUR, Progression 350 %", 10)]]

INFOBLOCK = [[(60, 62, "Musterland Versicherung AG · Postfach 20 30 40 · 80001 München", 7)]
             + bau.zeilen(60, 100, ["Herrn", "Severin Gstettner", "Kapellenweg 3", "84347 Pfarrkirchen"], 10, 15)
             + bau.zeilen(360, 100, ["Kundennummer: 3307 4471", "Versicherungsschein: LV 2291/8817-03",
                                     "Ihre Ansprechpartnerin: Frau Lechleitner", "Telefon: 089 4567-120",
                                     "Datum: 12.11.2026"], 8.5, 15)
             + bau.zeilen(60, 220, ["Ihre Berufsunfähigkeitsversicherung – Erhöhung ohne Gesundheitsprüfung", "",
                                    "Sehr geehrter Herr Gstettner,",
                                    "wie gewünscht haben wir die versicherte Rente zum 01.12.2026 erhöht.",
                                    "Mit freundlichen Grüßen", "Musterland Versicherung AG"], 10, 15)]

INFOBLOCK2 = [[(60, 70, "Musterland Krankenversicherung a.G. · 80001 München", 7)]
              + bau.zeilen(60, 110, ["Frau", "Kunigunde Ruhstorfer", "Untere Bachgasse 5", "83512 Wasserburg a. Inn"],
                           10, 14)
              + [(380, 100, "Ihre Kundennummer", 7), (380, 111, "5521 0938", 9.5),
                 (380, 126, "Ihre Versicherungsnummer", 7), (380, 137, "KV 12/3456789-0", 9.5),
                 (380, 152, "Ihre Ansprechpartnerin", 7), (380, 163, "Frau Lechleitner", 9.5),
                 (380, 178, "Telefon", 7), (380, 189, "089 4567-120", 9.5),
                 (380, 204, "Datum", 7), (380, 215, "12.11.2026", 9.5)]
              + bau.zeilen(60, 260, ["Beitragsanpassung zum 01.01.2027", "", "Sehr geehrte Frau Ruhstorfer,",
                                     "Ihr Monatsbeitrag ändert sich ab Januar 2027 auf 612,48 EUR.",
                                     "Mit freundlichen Grüßen"], 10, 15)]

BEZUG = [[(60, 70, "Musterland Versicherung AG · 80001 München", 7)]
         + bau.zeilen(60, 100, ["Frau", "Ottilie Schwarzenböck", "Sonnleitenstraße 17", "83395 Freilassing"], 10, 14)
         + [(60, 200, "Ihr Zeichen, Ihre Nachricht vom", 7), (175, 200, "Unser Zeichen, unsere Nachricht vom", 7),
            (300, 200, "Telefon, Name", 7), (490, 200, "Datum", 7),
            (60, 212, "os/29.10.2026", 9.5), (175, 212, "S-2026-118842 / Ls", 9.5),
            (300, 212, "089 4567-311, Herr Oberprieler", 9.5), (490, 212, "12.11.2026", 9.5)]
         + bau.zeilen(60, 250, ["Ihre Schadenmeldung Leitungswasser vom 29.10.2026", "",
                                "Sehr geehrte Frau Schwarzenböck,",
                                "wir haben einen Sachverständigen mit der Besichtigung beauftragt."], 10, 15)]

BEZUG2 = [[(60, 70, "Musterland Versicherung AG · 80001 München", 7)]
          + bau.zeilen(60, 100, ["Herrn", "Baltasar Wiesenhofer", "Am Kellerberg 7", "84489 Burghausen"], 10, 14)
          + [(60, 200, "Versicherungsschein-Nr.", 7), (190, 200, "Schaden-Nr.", 7),
             (320, 200, "Sachbearbeitung", 7), (490, 200, "Datum", 7),
             (60, 212, "WG 4471-0815-22", 9.5), (190, 212, "2026/SH/04471", 9.5),
             (320, 212, "Herr Oberprieler", 9.5), (490, 212, "12.11.2026", 9.5)]
          + bau.zeilen(60, 250, ["Sturmschaden vom 02.11.2026", "", "Sehr geehrter Herr Wiesenhofer,",
                                 "bitte senden Sie uns Fotos des beschädigten Daches."], 10, 15)]

FOLGESEITE = [
    bau.zeilen(60, 100, ["Herrn", "Severin Gstettner", "Kapellenweg 3", "84347 Pfarrkirchen"], 10, 14)
    + bau.zeilen(60, 200, ["Ihre Rentenversicherung – Standmitteilung 2026", "", "Sehr geehrter Herr Gstettner,",
                           "anbei erhalten Sie die jährliche Mitteilung zum Stand Ihres Vertrags.",
                           "Mit freundlichen Grüßen"], 10, 15)
    + [(60, 815, "Musterland Lebensversicherung AG · Sitz München · Amtsgericht München HRB 123456", 6.5)],
    [(60, 40, "Seite 2 zum Schreiben vom 12.11.2026 · Herrn Gstettner · Versicherungsschein-Nr. LV 2291/8817-03", 7.5)]
    + bau.zeilen(60, 90, ["Versicherte Personen", "Versicherte Person 1: Versicherungsnehmer",
                          "Versicherte Person 2: Ehefrau Afra Gstettner, geb. 21.06.1969",
                          "Bezugsberechtigt im Todesfall: der jeweils überlebende Ehegatte"], 10, 15)
    + [(60, 815, "Musterland Lebensversicherung AG · Sitz München · Amtsgericht München HRB 123456", 6.5)],
]

FUSS = [bau.zeilen(60, 100, ["Frau", "Notburga Pichlmeier", "Am Gänsbichl 4", "84453 Mühldorf a. Inn"], 10, 14)
        + bau.zeilen(60, 200, ["Beitragsrechnung 2027", "", "Sehr geehrte Frau Pichlmeier,",
                               "für Ihre Wohngebäudeversicherung wird zum 01.01.2027 ein Beitrag von 612,40 EUR fällig.",
                               "Mit freundlichen Grüßen"], 10, 15)
        + [(60, 812, "Pichlmeier, Notburga | Kd.-Nr. 5521 0938 | VS-Nr. WG-4471-0815-22 | Druck 12.11.2026 | "
                     "Seite 1 von 1", 6.5)]]

RAND = [bau.zeilen(60, 100, ["Frau", "Notburga Pichlmeier", "Am Gänsbichl 4", "84453 Mühldorf a. Inn"], 10, 14)
        + bau.zeilen(60, 200, ["Nachtrag zu Ihrer Wohngebäudeversicherung", "", "Sehr geehrte Frau Pichlmeier,",
                               "ab dem 01.12.2026 ist die Photovoltaikanlage mitversichert.",
                               "Mit freundlichen Grüßen"], 10, 15)
        + [(28, 790, "Druckstück 20261112 · VS-Nr. WG-4471-0815-22 · Kd.-Nr. 5521 0938 · Pichlmeier/Notburga", 6, 90)]]

FAELLE = [
    F("k1_kasten2", KASTEN2, ["Kraxenberger", "14.05.1971", "Hölzlweg 12", "83626", "0802447119",
                              "w.kraxenberger@t-online.de", "HR7740229105"]),
    F("k1_kasten3", KASTEN3, ["Pichlmeier", "02.08.1958", "Am Gänsbichl 4", "84453", "Mühldorf a. Inn",
                              "0863198765", "DE97711500000020304050", "Pflegehelferin", "Seniorenstift St. Josef"]),
    F("k1_infoblock", INFOBLOCK, ["Gstettner", "Kapellenweg 3", "84347", "33074471", "LV2291881703",
                                  "Lechleitner"]),
    F("k1_infoblock2", INFOBLOCK2, ["Ruhstorfer", "Untere Bachgasse 5", "83512", "55210938", "KV1234567890",
                                    "Lechleitner"]),
    F("k1_bezug", BEZUG, ["Schwarzenböck", "Sonnleitenstraße 17", "83395", "S2026118842", "Oberprieler"]),
    F("k1_bezug2", BEZUG2, ["Wiesenhofer", "Am Kellerberg 7", "84489", "WG4471081522", "2026SH04471",
                            "Oberprieler"]),
    F("k1_folgeseite", FOLGESEITE, ["Gstettner", "LV2291881703", "21.06.1969", "Afra"]),
    F("k1_fusszeile", FUSS, ["Pichlmeier", "55210938", "WG4471081522"]),
    F("k1_randvermerk", RAND, ["Pichlmeier", "55210938", "WG4471081522"]),
    F("k1_kasten3_scan", KASTEN3, ["Pichlmeier", "02.08.1958", "Am Gänsbichl 4", "84453", "Mühldorf a. Inn",
                                   "0863198765", "DE97711500000020304050"], scans=SCAN, text=False),
    F("k1_infoblock2_scan", INFOBLOCK2, ["Ruhstorfer", "Untere Bachgasse 5", "83512", "55210938",
                                         "KV1234567890"], scans=((200, -0.6, 70),), text=False),
]
