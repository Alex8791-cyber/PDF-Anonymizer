# Kritik-Lauf K5: Tabellenfortsetzung mit voller erster Seite, MRZ in Festbreitenschrift (Ausweis TD1, Pass TD3)
# als Scan, Handyfoto eines Briefs, Textseite mit eingebettetem Bild – erfundene Personen und Nummern
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # bau.py und die Nachbardateien
import bau
import faelle_k1 as K1

MONO = bau.MONO


def F(name, bauer, geheim, **kw):
    d = dict(name=name, zeilen=[], geheim=geheim, bauer=bauer)
    d.update(kw)
    return d


XS = [36, 130, 290, 380, 470]
KOPF = ["Vertrag", "Versicherungsnehmer", "Sparte", "Beginn", "Jahresbeitrag"]
NACH = ["Haberl", "Mooslechner", "Zeitlhofer", "Feichtner", "Bichlmaier", "Rottenhuber", "Kaltenecker", "Pointner",
        "Stadler", "Wimmer", "Lackner", "Rieder", "Kammerer"]
VOR = ["Josefa", "Anton", "Maria", "Georg", "Theresia", "Michael", "Rosa", "Florian", "Kreszenz"]
SPARTEN = [("Hausrat", "186,40"), ("PHV", "89,90"), ("Wohngebäude", "612,00"), ("Unfall", "142,80"),
           ("Rechtsschutz", "298,30")]
FUELL = [[f"HR-7740-2291-{i:02d}", f"{NACH[i % len(NACH)]}, {VOR[i % len(VOR)]}", SPARTEN[i % 5][0],
          f"01.{1 + i % 12:02d}.20{15 + i % 10}", SPARTEN[i % 5][1]] for i in range(52)]
S1 = [(36, 50, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026", 12)] + bau.tabelle(80, XS, [KOPF] + FUELL, 8) + [
    (36, 815, "Seite 1 von 2", 7)]
S2_ZEILEN = [["PHV 447118", "Wiesenhofer, Baltasar", "PHV", "01.11.2019", "89,90"],
             ["4471-0815", "Pichlmeier, Notburga", "Hausrat", "01.12.2020", "186,40"],
             ["RS 0815", "Ruhstorfer Kunigunde", "Rechtsschutz", "01.03.2018", "298,30"],
             ["7.712.345", "Oberprieler, Severin", "Unfall", "15.10.2026", "142,80"],
             ["LV 2291/8817-03", "Gstettner, Afra", "Rente", "01.11.2016", "1.234,56"]]
S2_OHNE = [(36, 40, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026", 8)] + bau.tabelle(70, XS, S2_ZEILEN, 8) + [
    (36, 815, "Seite 2 von 2", 7)]
S2_MIT = [(36, 40, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026", 8)] + bau.tabelle(70, XS, [KOPF] + S2_ZEILEN, 8) \
    + [(36, 815, "Seite 2 von 2", 7)]
GEHEIM_S2 = ["PHV447118", "Wiesenhofer", "Baltasar", "44710815", "Pichlmeier", "RS0815", "Ruhstorfer", "7712345",
             "Oberprieler", "LV2291881703", "Gstettner", "HR7740229151", "Kammerer"]

TD1 = [[(60, 80, "Anschrift / Address", 7), (60, 95, "83346 BERGEN", 10), (60, 109, "KIRCHSTEIG 2", 10),
        (60, 135, "Größe / Height  182 cm      Augenfarbe / Colour of eyes  BRAUN", 7.5),
        (60, 152, "Datum / Date  14.03.2021      Behörde / Authority  LANDRATSAMT TRAUNSTEIN", 7.5),
        (60, 200, "IDD<<T220001293<<<<<<<<<<<<<<<", 11, 0, MONO),
        (60, 216, "9011300<3103142D<<<<<<<<<<<<<8", 11, 0, MONO),
        (60, 232, "HOELZLWIMMER<<BALTASAR<KORBINI", 11, 0, MONO)]]

TD3 = [[(60, 70, "REISEPASS   PASSPORT   PASSEPORT      BUNDESREPUBLIK DEUTSCHLAND", 9),
        (60, 95, "Typ / Type  P      Kode / Code  D      Pass-Nr. / Passport No.  C4KR7NT2X", 8),
        (60, 115, "Name / Surname  HÖLZLWIMMER", 9),
        (60, 130, "Vornamen / Given names  BALTASAR KORBINIAN", 9),
        (60, 145, "Geburtstag / Date of birth  30.11.1990", 9),
        (60, 160, "Geburtsort / Place of birth  TROSTBERG", 9),
        (40, 230, "P<D<<HOELZLWIMMER<<BALTASAR<KORBINIAN<<<<<<<", 10, 0, MONO),
        (40, 246, "C4KR7NT2X1D<<9011300M3302141<<<<<<<<<<<<<<04", 10, 0, MONO)]]

MISCH_TEXT = (bau.zeilen(60, 100, ["Notburga Pichlmeier", "Am Gänsbichl 4", "84453 Mühldorf a. Inn"], 10, 14)
              + bau.zeilen(60, 200, ["Änderung der Bankverbindung für meine Verträge", "",
                                     "Sehr geehrter Herr Sonnleitner,",
                                     "die Beiträge sollen künftig vom Konto meines Sohnes abgebucht werden.",
                                     "Anbei ein Foto seiner Bankkarte und seiner Steuerbescheinigung:"], 10, 15))
MISCH_BILD = [[(40, 40, "Kontoinhaber: Severin Gstettner", 12), (40, 62, "IBAN: DE58 7406 1813 0001 2345 67", 12),
               (40, 84, "Steuer-ID: 81 304 275 611", 12)]]

FAELLE = [
    F("k5_forts_voll", bau.bauer([S1, S2_OHNE]), GEHEIM_S2),
    F("k5_forts_voll_kopf", bau.bauer([S1, S2_MIT]), GEHEIM_S2),
    F("k5_mrz_td1", lambda p: bau.pdf2(p, TD1), ["83346", "KIRCHSTEIG 2", "T22000129", "9011300", "HOELZLWIMMER",
                                                  "BALTASAR"], scans=((200, 0.0, None),), text=False),
    F("k5_mrz_td3", lambda p: bau.pdf2(p, TD3), ["HÖLZLWIMMER", "C4KR7NT2X", "30.11.1990", "TROSTBERG",
                                                  "HOELZLWIMMER", "9011300"], scans=((200, 0.0, None),), text=False),
    F("k5_foto_brief", bau.foto(K1.INFOBLOCK2), ["Ruhstorfer", "Untere Bachgasse 5", "83512", "55210938",
                                                 "KV1234567890"]),
    F("k5_mischseite", bau.mit_bild(MISCH_TEXT, MISCH_BILD, (60, 300, 420, 427)),
      ["Pichlmeier", "Gstettner", "DE58740618130001234567", "81304275611"]),
]
