# Kritik-Lauf K9: Querformat-Liste (Excel-Ausdruck), Hochformatseite mit /Rotate 90, auf dem Kopf eingezogener Scan
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import pymupdf as fitz
import bau
import faelle_k1 as K1

KOPF = ["Kd.-Nr.", "Name", "Vorname", "Geb.-Datum", "Straße", "PLZ", "Ort", "Telefon", "E-Mail", "Vers.-Nr."]
XS = [30, 75, 145, 200, 255, 355, 385, 475, 545, 680]
REIHEN = [["10471", "Ruhstorfer", "Kunigunde", "21.06.1949", "Untere Bachgasse 5", "83512", "Wasserburg a. Inn",
           "08071 12345", "k.ruhstorfer@gmx.de", "HR-7740-2291-05"],
          ["10474", "Hölzlwimmer", "Vinzenz", "30.11.1990", "Kirchsteig 2", "83346", "Bergen", "0160 5544332",
           "v.hoelzl@web.de", "KV 12/3456789-0"]]
GEHEIM = ["Ruhstorfer", "21.06.1949", "Untere Bachgasse 5", "83512", "0807112345", "k.ruhstorfer@gmx.de",
          "HR7740229105", "Hölzlwimmer", "30.11.1990", "Kirchsteig 2", "01605544332", "KV1234567890"]


def quer(pfad, drehen=False):
    doc = fitz.open()
    if drehen:
        s = doc.new_page(width=595, height=842)       # Hochformat-Seite, Inhalt quer, /Rotate 90
        s.set_rotation(90)
    else:
        s = doc.new_page(width=842, height=595)
    els = [(30, 50, "Bestandsliste Privatkunden (Export Maklerverwaltung) – Stand 12.11.2026", 11)] + bau.tabelle(
        80, XS, [KOPF] + REIHEN, 8)
    for x, y, t, g in els:
        if drehen:
            # Koordinaten der gedrehten Ansicht (842 x 595) in Seitenkoordinaten umrechnen
            p = fitz.Point(x, y) * s.derotation_matrix
            s.insert_text(p, t, fontsize=g, fontname="dv", fontfile=bau.DEJAVU, rotate=90)
        else:
            s.insert_text((x, y), t, fontsize=g, fontname="dv", fontfile=bau.DEJAVU)
    doc.save(pfad)
    doc.close()


FAELLE = [
    dict(name="k9_quer", zeilen=[], geheim=GEHEIM, bauer=lambda p: quer(p)),
    dict(name="k9_rotate90", zeilen=[], geheim=GEHEIM, bauer=lambda p: quer(p, True)),
    dict(name="k9_scan_kopf", zeilen=[], geheim=["Ruhstorfer", "Untere Bachgasse 5", "83512", "55210938",
                                                 "KV1234567890"], bauer=bau.bauer(K1.INFOBLOCK2),
         scans=((200, 180.0, None),), text=False),
]
