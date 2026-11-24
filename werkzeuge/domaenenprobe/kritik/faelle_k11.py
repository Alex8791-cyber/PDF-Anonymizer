# Kritik-Lauf K11: Namen mit abgekürztem Vornamen in Listen, ohne Spalte "Sparte" (deren Fehlverdacht verdeckt sonst)
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import bau

T = [[(36, 50, "Courtageabrechnung November 2026 – Musterland Versicherung AG", 11)] + bau.tabelle(
    80, [36, 140, 300, 420], [["VSNR", "Versicherungsnehmer", "Produkt", "Beitrag"],
                              ["HR-7740-2291-05", "Kraxenberger, Wendelin", "Hausrat Plus", "186,40"],
                              ["PHV-0071-4471", "Oberprieler, S.", "Privathaftpflicht", "89,90"],
                              ["U-2026-5512", "Pichlmeier, N.", "Unfall Komfort", "142,80"],
                              ["KV 12/3456789-0", "Gstettner, A.", "Krankenzusatz", "48,20"]], 8)]
FAELLE = [dict(name="k11_initial_ohne_sparte", zeilen=[], bauer=bau.bauer(T),
               geheim=["Kraxenberger", "Oberprieler", "Pichlmeier", "Gstettner"])]
