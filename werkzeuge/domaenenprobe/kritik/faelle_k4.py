# Kritik-Lauf K4: Gegenproben und Varianten zu K1/K2 (Tabellenfortsetzung ohne Kopf, Namen mit Initiale,
# Zellumbruch, CSV-/Pipe-Ausdruck, Beruf im Kastenformular, Scan des Kastenformulars gerade/schief/JPEG)
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import bau
import faelle_k1 as K1


def F(name, seiten, geheim, **kw):
    d = dict(name=name, zeilen=[], geheim=geheim, bauer=bau.bauer(seiten))
    d.update(kw)
    return d


XS = [36, 130, 290, 380, 470]
KOPF = ["Vertrag", "Versicherungsnehmer", "Sparte", "Beginn", "Jahresbeitrag"]
S1 = [(36, 50, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026", 12)] + bau.tabelle(80, XS, [
    KOPF, ["HR-7740-2291-05", "Kraxenberger, Wendelin", "Hausrat", "01.12.2020", "186,40"],
    ["PHV-0071-4471", "Brandlhuber, Gerlinde", "PHV", "01.11.2019", "89,90"]], 8)
S2_ZEILEN = [["PHV 447118", "Wiesenhofer, Baltasar", "PHV", "01.11.2019", "89,90"],
             ["4471-0815", "Pichlmeier, N.", "Hausrat", "01.12.2020", "186,40"],
             ["RS 0815", "Ruhstorfer Kunigunde", "Rechtsschutz", "01.03.2018", "298,30"],
             ["7.712.345", "Oberprieler, Severin", "Unfall", "15.10.2026", "142,80"]]
S2_OHNE = [(36, 40, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026 – Seite 2", 8)] + bau.tabelle(70, XS, S2_ZEILEN, 8)
S2_MIT = [(36, 40, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026 – Seite 2", 8)] + bau.tabelle(
    70, XS, [KOPF] + S2_ZEILEN, 8)
GEHEIM_S2 = ["PHV447118", "Wiesenhofer", "Baltasar", "44710815", "Pichlmeier", "RS0815", "Ruhstorfer", "7712345",
             "Oberprieler"]

INITIAL = [[(36, 50, "Courtageabrechnung November 2026 – Musterland Versicherung AG", 11)] + bau.tabelle(
    80, [36, 140, 300, 420], [["VSNR", "Versicherungsnehmer", "Sparte", "Beitrag"],
                              ["HR-7740-2291-05", "Pichlmeier, N.", "Hausrat", "186,40"],
                              ["PHV-0071-4471", "Oberprieler, S.", "PHV", "89,90"],
                              ["U-2026-5512", "Ruhstorfer K.", "Unfall", "142,80"],
                              ["KV 12/3456789-0", "Dr. Lechleitner, A.", "PKV", "4.812,00"]], 8)]

UMBRUCH = [[(36, 50, "Wohngebäude – Bestandsübersicht Hausverwaltung", 11)] + bau.tabelle(
    80, [36, 130, 260, 470], [["VSNR", "Versicherungsnehmer", "Risikoanschrift", "Beitrag"],
                              ["WG 4471-0815-24", "Grundstücksgemeinschaft", "Kirchsteig 2,", "498,00"],
                              ["", "Hölzlwimmer/Pichlmeier", "83346 Bergen", ""],
                              ["WG 4471-0815-25", "Wiesenhofer,", "Am Kellerberg 7,", "612,00"],
                              ["", "Baltasar", "84489 Burghausen", ""],
                              ["WG 4471-0815-26", "Eheleute Gstettner,", "Kapellenweg 3,", "702,00"],
                              ["", "Severin und Afra", "84347 Pfarrkirchen", ""]], 8, 11)]

CSV = [[(36, 50, "kunden_bu_2026-11-12.csv", 9)] + bau.zeilen(36, 75, [
    "Kdnr;Name;Vorname;PLZ;Ort;Gebdat;Sparte",
    "10477;Wiesenhofer;Baltasar;84489;Burghausen;17.09.1966;BU",
    "10478;Pichlmeier;Notburga;84453;Mühldorf a. Inn;02.08.1958;Unfall"], 8, 12)]

PIPE = [[(36, 50, "Auswertung Geburtstage Q1/2027 (Maklerverwaltung)", 9)] + bau.zeilen(36, 75, [
    "Kdnr | Name | Vorname | PLZ | Ort | Gebdat",
    "10479 | Gstettner | Severin | 84347 | Pfarrkirchen | 17.09.1966",
    "10480 | Ruhstorfer | Kunigunde | 83512 | Wasserburg a. Inn | 21.06.1949"], 8, 12)]

BERUF = [[(50, 60, "Antrag Berufsunfähigkeitsversicherung – Angaben zur versicherten Person", 12)]
         + K1.kasten(95, [50, 300], [
             (("Name, Vorname", "Geburtsdatum"), ("Pichlmeier, Notburga", "02.08.1958")),
             (("Ausgeübter Beruf", "Arbeitgeber"), ("Pflegehelferin", "Seniorenstift St. Josef")),
             (("Beruf des Ehepartners", "Beruf"), ("Erzieherin", "Pflegehelferin")),
         ])]

KG = ["Pichlmeier", "02.08.1958", "Am Gänsbichl 4", "84453", "Mühldorf a. Inn", "0863198765",
      "DE97711500000020304050", "Pflegehelferin", "Seniorenstift St. Josef"]

FAELLE = [
    F("k4_forts_ohne_kopf", [S1, S2_OHNE], GEHEIM_S2),
    F("k4_forts_mit_kopf", [S1, S2_MIT], GEHEIM_S2),
    F("k4_initial", INITIAL, ["Pichlmeier", "Oberprieler", "Ruhstorfer", "Lechleitner"]),
    F("k4_umbruch", UMBRUCH, ["Hölzlwimmer", "Pichlmeier", "Wiesenhofer", "Baltasar", "Gstettner", "Severin",
                              "Afra"]),
    F("k4_csv", CSV, ["10477", "Wiesenhofer", "Baltasar", "84489", "17.09.1966", "Pichlmeier", "84453",
                      "02.08.1958"]),
    F("k4_pipe", PIPE, ["10479", "Gstettner", "84347", "17.09.1966", "Ruhstorfer", "83512", "21.06.1949"]),
    F("k4_kasten_beruf", BERUF, ["Pichlmeier", "02.08.1958", "Pflegehelferin", "Seniorenstift St. Josef",
                                 "Erzieherin"]),
    F("k4_kasten3_gerade", K1.KASTEN3, KG, scans=((200, 0.0, None),), text=False),
    F("k4_kasten3_schief", K1.KASTEN3, KG, scans=((200, 0.8, None),), text=False),
    F("k4_kasten3_jpeg", K1.KASTEN3, KG, scans=((200, 0.0, 70),), text=False),
]
