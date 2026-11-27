# Kritik-Lauf K10: Zellumbruch in Listen (Name und Anschrift über zwei Zeilen einer Zelle), nur Textebene
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import bau

XS = [36, 130, 262, 470]
KOPF = ["VSNR", "Versicherungsnehmer", "Risikoanschrift", "Beitrag"]
NAMEN = [[(36, 50, "Wohngebäude – Bestandsübersicht (Hausverwaltung)", 11)] + bau.tabelle(80, XS, [
    KOPF,
    ["WG 4471-0815-31", "Eheleute", "Kapellenweg 3,", "702,00"],
    ["", "Gstettner", "84347 Pfarrkirchen", ""],
    ["WG 4471-0815-32", "Familie", "Am Kellerberg 7,", "612,00"],
    ["", "Wiesenhofer", "84489 Burghausen", ""],
    ["WG 4471-0815-33", "Erbengemeinschaft", "Kirchsteig 2,", "498,00"],
    ["", "Hölzlwimmer", "83346 Bergen", ""]], 8, 11)]
ADRESSE = [[(36, 50, "Wohngebäude – Bestandsübersicht (Hausverwaltung)", 11)] + bau.tabelle(80, XS, [
    KOPF,
    ["WG 4471-0815-34", "Pichlmeier, Notburga", "Am Gänsbichl", "586,00"],
    ["", "", "4, 84453 Mühldorf a. Inn", ""],
    ["WG 4471-0815-35", "Ruhstorfer, Kunigunde", "Untere Bachgasse", "498,00"],
    ["", "", "5, 83512 Wasserburg a. Inn", ""],
    ["WG 4471-0815-36", "Schwarzenböck, Ottilie", "Sonnleitenstraße 17,", "655,00"],
    ["", "", "83395 Freilassing", ""]], 8, 11)]

FAELLE = [
    dict(name="k10b_umbruch_namen", zeilen=[], bauer=bau.bauer(NAMEN),
         geheim=["Gstettner", "Wiesenhofer", "Hölzlwimmer", "Kapellenweg 3", "Am Kellerberg 7", "Kirchsteig 2"]),
    dict(name="k10b_umbruch_adresse", zeilen=[], bauer=bau.bauer(ADRESSE),
         geheim=["Pichlmeier", "Am Gänsbichl", "84453", "Untere Bachgasse", "83512", "Sonnleitenstraße 17", "83395"]),
]
