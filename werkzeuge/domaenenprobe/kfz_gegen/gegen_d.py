# Gegenprüfung Kfz, Teil D: Nachproben (ZB I als Scan ohne fremde Verdachtsstellen, Kontrolle Länderwort CH)
def F(name, zeilen, geheim, scans=(), **extra):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(extra)
    return d


SCAN = ((200, 0.0, None),)

FAELLE = [
    F("d01_zb1_versal_scan", ["ZULASSUNGSBESCHEINIGUNG TEIL I",
                              "A  M-KS 4471\t\tB  14.09.2020",
                              "C.1.1  STEINLECHNER",
                              "C.1.2  GUNDOLF"], ["STEINLECHNER", "GUNDOLF"], scans=SCAN, text=False),
    F("d02_zb1_gemischt_scan", ["Zulassungsbescheinigung Teil I (Kopie)",
                                "A  M-KS 4471\t\tB  14.09.2020",
                                "C.1.1  Steinlechner",
                                "C.1.2  Gundolf"], ["Steinlechner", "Gundolf"], scans=SCAN),
    F("d03_ch_mit_land", ["Angaben zur Unfallgegnerin",
                          "Frau Gesche Oberrauch, Seestrasse 12, 8002 Zürich, Schweiz"], ["8002 Zürich"]),
]
