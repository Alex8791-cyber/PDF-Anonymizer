# Kritik-Lauf K10c: Zellumbruch mit realistischem Umbruch langer Namenszellen (nur Textebene)
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import bau

XS = [36, 130, 262, 470]
T = [[(36, 50, "Hausrat/Wohngebäude – Bestandsübersicht", 11)] + bau.tabelle(80, XS, [
    ["VSNR", "Versicherungsnehmer", "Risikoanschrift", "Beitrag"],
    ["WG 4471-0815-41", "Eheleute Severin und Afra", "Kapellenweg 3, 84347", "702,00"],
    ["", "Gstettner", "Pfarrkirchen", ""],
    ["HR 7740-2291-42", "Baltasar Wiesenhofer und", "Am Kellerberg 7, 84489", "186,40"],
    ["", "Walburga Oberprieler", "Burghausen", ""],
    ["WG 4471-0815-43", "Grundstücksgemeinschaft", "Sonnleitenstraße", "655,00"],
    ["", "Schwarzenböck/Lechleitner", "17, 83395 Freilassing", ""]], 8, 11)]

FAELLE = [dict(name="k10c_umbruch_lang", zeilen=[], bauer=bau.bauer(T),
               geheim=["Gstettner", "Wiesenhofer", "Oberprieler", "Schwarzenböck", "Lechleitner", "Kapellenweg 3",
                       "84347", "Am Kellerberg 7", "Sonnleitenstraße"])]
