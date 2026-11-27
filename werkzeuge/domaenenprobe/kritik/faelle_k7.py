# Kritik-Lauf K7: Ausweis-/Passkopie mit mehrsprachigen Etiketten über dem Wert (wie auf der Karte), Beruf als
# Tabellenspalte, PDF-Kommentare (Freitext-Kommentar, Notiz) – erfundene Personen und Nummern
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import bau
import pymupdf as fitz

MONO = bau.MONO


def F(name, bauer, geheim, **kw):
    d = dict(name=name, zeilen=[], geheim=geheim, bauer=bauer)
    d.update(kw)
    return d


def stapel(x, y, paare, lg=6.5, wg=10, schritt=24):
    aus = []
    for i, (e, w) in enumerate(paare):
        aus.append((x, y + i * schritt, e, lg))
        aus.append((x, y + i * schritt + 11, w, wg))
    return aus


AUSWEIS = [[(60, 60, "BUNDESREPUBLIK DEUTSCHLAND   PERSONALAUSWEIS / IDENTITY CARD / CARTE D'IDENTITÉ", 8),
            (400, 85, "T22000129", 11)]
           + stapel(170, 90, [("Name / Surname / Nom", "HÖLZLWIMMER"),
                              ("Vornamen / Given names / Prénoms", "BALTASAR KORBINIAN"),
                              ("Geburtstag / Date of birth / Date de naissance", "30.11.1990"),
                              ("Staatsangehörigkeit / Nationality / Nationalité", "DEUTSCH"),
                              ("Geburtsort / Place of birth / Lieu de naissance", "TROSTBERG"),
                              ("Gültig bis / Date of expiry / Date d'expiration", "14.03.2031")])
           + [(430, 240, "123456", 10),
              (60, 300, "Anschrift / Address / Adresse", 6.5), (60, 311, "83346 BERGEN", 10),
              (60, 324, "KIRCHSTEIG 2", 10),
              (60, 350, "IDD<<T220001293<<<<<<<<<<<<<<<", 11, 0, MONO),
              (60, 366, "9011300<3103142D<<<<<<<<<<<<<8", 11, 0, MONO),
              (60, 382, "HOELZLWIMMER<<BALTASAR<KORBINI", 11, 0, MONO)]]
G_AUSWEIS = ["HÖLZLWIMMER", "BALTASAR", "30.11.1990", "TROSTBERG", "T22000129", "83346", "KIRCHSTEIG 2", "9011300"]

PASS = [[(60, 60, "REISEPASS / PASSPORT / PASSEPORT      BUNDESREPUBLIK DEUTSCHLAND", 8)]
        + stapel(170, 85, [("Pass-Nr. / Passport No. / Passeport No", "C4KR7NT2X"),
                           ("Name / Surname / Nom", "HÖLZLWIMMER"),
                           ("Vornamen / Given names / Prénoms", "BALTASAR KORBINIAN"),
                           ("Geburtstag / Date of birth / Date de naissance", "30.11.1990"),
                           ("Geburtsort / Place of birth / Lieu de naissance", "TROSTBERG")])
        + [(40, 230, "P<D<<HOELZLWIMMER<<BALTASAR<KORBINIAN<<<<<<<", 10, 0, MONO),
           (40, 246, "C4KR7NT2X1D<<9011300M3302141<<<<<<<<<<<<<<04", 10, 0, MONO)]]
G_PASS = ["C4KR7NT2X", "HÖLZLWIMMER", "BALTASAR", "30.11.1990", "TROSTBERG"]

BERUF_TAB = [[(36, 50, "Gruppen-Berufsunfähigkeitsversicherung – Anmeldung neuer Mitarbeiter", 11)]
             + bau.tabelle(80, [36, 190, 270, 420],
                           [["Name, Vorname", "Geb.-Datum", "Beruf", "Eintritt"],
                            ["Pichlmeier, Notburga", "02.08.1958", "Pflegehelferin", "01.10.2026"],
                            ["Hölzlwimmer, Vinzenz", "30.11.1990", "Dachdecker", "01.11.2026"],
                            ["Oberprieler, Severin", "12.12.1975", "Erzieher", "01.11.2026"]], 8.5)]


def kommentare(pfad):
    bau.pdf2(pfad, [bau.zeilen(60, 100, ["Musterland Versicherung AG", "80001 München"], 10, 14)
                    + bau.zeilen(60, 180, ["Ihre Berufsunfähigkeitsversicherung – Nachweis zur Leistungsprüfung", "",
                                           "Sehr geehrte Damen und Herren,",
                                           "anbei erhalten Sie die angeforderten Unterlagen.",
                                           "Mit freundlichen Grüßen", "Ihr Versicherungsmakler"], 10, 15)])
    doc = fitz.open(pfad)
    s = doc[0]
    a = s.add_freetext_annot(fitz.Rect(300, 300, 560, 345),
                             "Rückruf: Baltasar Wiesenhofer, Tel. 0171 2345678 (abends)", fontsize=9)
    a.update()
    n = s.add_text_annot(fitz.Point(520, 180), "Kunde Wiesenhofer will BU kündigen, Vers.-Nr. LV 2291/8817-03")
    n.set_info(title="Sonnleitner")
    n.update()
    h = s.add_highlight_annot(fitz.Rect(58, 205, 300, 218))
    h.set_info(content="Herr Wiesenhofer, geb. 17.09.1966 – Unterlagen vollständig?")
    h.update()
    doc.saveIncr()
    doc.close()


FAELLE = [
    F("k7_ausweis_stapel", bau.bauer(AUSWEIS) if False else (lambda p: bau.pdf2(p, AUSWEIS)), G_AUSWEIS,
      scans=((200, 0.0, None),)),
    F("k7_pass_stapel", lambda p: bau.pdf2(p, PASS), G_PASS, scans=((200, 0.0, None),)),
    F("k7_beruf_spalte", bau.bauer(BERUF_TAB), ["Pichlmeier", "02.08.1958", "Pflegehelferin", "Dachdecker",
                                                "Erzieher"]),
    F("k7_kommentare", kommentare, ["Wiesenhofer", "01712345678", "LV2291881703", "17.09.1966"]),
]

import faelle_k2 as K2
G_BESTAND = ["Gstettner", "17.09.1966", "21.06.1969", "4471081522", "SH8812947", "K77123450"]
FAELLE += [
    dict(name="k7_bestand_gerade", zeilen=[], geheim=G_BESTAND, bauer=bau.bauer(K2.BESTAND),
         scans=((200, 0.0, None),), text=False),
    dict(name="k7_bestand_schief_neg", zeilen=[], geheim=G_BESTAND, bauer=bau.bauer(K2.BESTAND),
         scans=((200, -0.8, None),), text=False),
]
