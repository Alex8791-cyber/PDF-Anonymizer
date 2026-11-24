# Kritik-Lauf K6: Scans mit leichter Schräglage (Einzugsscanner) – Tabellen und Kastenformulare, Gegenprobe gerade
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import bau
import faelle_k1 as K1
import faelle_k2 as K2


def F(name, seiten, geheim, scan):
    return dict(name=name, zeilen=[], geheim=geheim, bauer=bau.bauer(seiten), scans=(scan,), text=False)


G_KUNDEN = ["10471", "Ruhstorfer", "Untere Bachgasse 5", "83512", "21.06.1949", "0807112345", "Kraxenberger",
            "Hölzlweg 12", "14.05.1971", "Schwarzenböck", "03.03.1980", "Hölzlwimmer", "Kirchsteig 2", "01605544332"]
G_BESTAND = ["Gstettner", "17.09.1966", "21.06.1969", "4471081522", "SH8812947", "K77123450"]
G_KASTEN2 = ["Kraxenberger", "14.05.1971", "Hölzlweg 12", "83626", "0802447119", "w.kraxenberger@t-online.de",
             "HR7740229105"]
G_KASTEN3 = ["Pichlmeier", "02.08.1958", "Am Gänsbichl 4", "84453", "Mühldorf a. Inn", "0863198765",
             "DE97711500000020304050", "Pflegehelferin", "Seniorenstift St. Josef"]
G_GRUPPE = ["Hölzlwimmer", "30.11.1990", "Oberprieler", "12.12.1975", "Kraxenberger", "03.04.2001"]

FAELLE = [
    F("k6_kunden_gerade", K2.KUNDEN, G_KUNDEN, (200, 0.0, None)),
    F("k6_kunden_schief", K2.KUNDEN, G_KUNDEN, (200, 0.8, None)),
    F("k6_bestand_schief", K2.BESTAND, G_BESTAND, (200, 0.8, None)),
    F("k6_kasten2_schief", K1.KASTEN2, G_KASTEN2, (200, 0.8, None)),
    F("k6_kasten3_schief04", K1.KASTEN3, G_KASTEN3, (200, 0.4, None)),
    F("k6_gruppe_schief", K2.GRUPPE, G_GRUPPE, (200, 0.8, None)),
]
