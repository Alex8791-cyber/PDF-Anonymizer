# Kritik-Lauf K8: Schräglage genauer eingrenzen (Richtung, Winkel) für Kastenformular, kleine und große Tabelle
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import faelle_k6 as K6
from faelle_k6 import F, G_KASTEN3, G_BESTAND, G_KUNDEN
import faelle_k1 as K1
import faelle_k2 as K2

FAELLE = [
    F("k8_kasten3_minus08", K1.KASTEN3, G_KASTEN3, (200, -0.8, None)),
    F("k8_kasten3_plus12", K1.KASTEN3, G_KASTEN3, (200, 1.2, None)),
    F("k8_bestand_plus06", K2.BESTAND, G_BESTAND, (200, 0.6, None)),
    F("k8_bestand_plus12", K2.BESTAND, G_BESTAND, (200, 1.2, None)),
    F("k8_kunden_plus15", K2.KUNDEN, G_KUNDEN, (200, 1.5, None)),
]
