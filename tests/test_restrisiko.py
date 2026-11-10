"""Tests für anonymisierer/restrisiko.py – die zweite, unabhängige Verteidigungslinie (Vertrag Abschnitt 7).

Je Regel ein Positiv- und ein Negativfall (auch mit NBSP/weichem Trennstrich wie auf Windows-Rechnern),
Platzhalter-, NIE- und Abwahl-Immunität, Rechtecke, Scan-Seite aus dem OCR-Zwischenspeicher und ein
Ende-zu-Ende-Test: ein von der Erkennung verpasster Wert macht die Ausgabe zu _PRUEFEN, mit Verdacht an der
richtigen Stelle.
"""

import datetime
import time
from pathlib import Path

import pytest

import pymupdf as fitz

from anonymisierer import restrisiko
from anonymisierer.restrisiko import Verdacht, pruefe_text, restrisiko_pruefen, verdacht_als_dict
from anonymisierer.schwaerzung import schwaerze_pdf

IBAN = "DE89 3704 0044 0532 0130 00"


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------
def texte(text, **kw) -> list:
    """Texte aller Verdachtsstellen eines reinen Texts."""
    return [v.text for v in pruefe_text(text, **kw)]


def gemeldet(text, wert, **kw) -> bool:
    """Wird `wert` (ganz oder als Teil einer Verdachtsstelle) gemeldet?"""
    return any(wert in t or t in wert for t in texte(text, **kw) if t.strip())


def pdf_mit_zeilen(pfad, zeilen, fontsize=10, x=60, y=80, abstand=16):
    doc = fitz.open()
    seite = doc.new_page()
    for z in zeilen:
        seite.insert_text((x, y), z, fontsize=fontsize, fontname="helv")
        y += abstand
    doc.save(pfad)
    doc.close()
    return Path(pfad)


class OcrAttrappe:
    """OcrDienst-Ersatz: liefert vorgegebene Wörter je Seite und protokolliert jeden Aufruf."""

    def __init__(self, woerter=None):
        self.woerter_je_seite = woerter or {}
        self.aufrufe = []
        self.hinweise = []

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, winkel=None, **_):
        self.aufrufe.append({"seite": seite_nr0, "clip": clip, "winkel": winkel})
        return list(self.woerter_je_seite.get(seite_nr0, [])), None

    def schliessen(self):
        pass


# ----------------------------------------------------------------------
# Kennungen und Ziffernfolgen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, wert", [
    ("Auszahlung aus Ihrem Vertrag 47.897.336.2 – fehlende Angaben", "47.897.336.2"),
    ("KF007952512\t\tLV-2014-697971", "KF007952512"),
    ("Vertrag LV-2014-697971 vom Makler", "LV-2014-697971"),
    ("Kundennummer 6 259 674 059", "6 259 674 059"),
    ("Aktenzeichen 545/983537-1", "545/983537-1"),
    ("IHK-Register D-Y3TV-NW64X-52", "D-Y3TV-NW64X-52"),
    ("Mandat SEPA816626-520", "SEPA816626-520"),
])
def test_ziffernfolge_wird_gemeldet(zeile, wert):
    assert gemeldet(zeile, wert), texte(zeile)


@pytest.mark.parametrize("zeile", [
    "Der Beitrag beträgt 1.234,56 EUR monatlich.",
    "Die Versicherungssumme beträgt 100.000 EUR.",
    "Ihr Schreiben vom 12.03.2025 haben wir erhalten.",
    "Gemäß § 12345 VVG gilt Folgendes.",
    "Kilometerstand 45.000 km",
    "Sitz: Freiburg · Amtsgericht Freiburg HRB 16963",
    "USt-IdNr. DE402080537",
    "Service-Telefon 0800 826 9819 (kostenfrei)",
    "Tarif Vollkasko Komfort 300/150",
    "Seite 1 von 2",
    "Gläubiger-ID DE70ZZZ03290639901",
])
def test_unkritische_zahlen_sind_kein_verdacht(zeile):
    assert texte(zeile) == []


def test_telefonnummern_auch_mit_landesvorwahl():
    assert gemeldet("Mobil 0170 318 40 11", "0170 318 40 11")
    assert gemeldet("Zeuge, Tel. 07 51 / 345 09 42", "07 51 / 345 09 42")
    v = pruefe_text("erreichbar unter +49 (0)7141 842332")
    assert [x.text for x in v] == ["+49 (0)7141 842332"] and "Ländervorwahl" in v[0].grund


def test_plz_einer_firmenanschrift_ist_kein_verdacht_einer_person_schon():
    kopf = "Schwarzwald Lebensversicherung AG · Habsburgerstr. 8 · 79100 Freiburg im Breisgau"
    assert texte(kopf) == []
    assert gemeldet("Ich bin umgezogen nach 54290 Trier.", "54290 Trier")


# ----------------------------------------------------------------------
# Formen mit Prüfziffer: gemeldet wird die Form, die Prüfziffer verstärkt nur den Grund
# ----------------------------------------------------------------------
def test_iban_gueltig_und_mit_ocr_fehler():
    v = pruefe_text(f"IBAN {IBAN}")
    assert v and v[0].text == IBAN and "Prüfziffer gültig" in v[0].grund
    kaputt = "DE89 3704 0044 0532 0130 01"          # Prüfziffer falsch (OCR-Verleser) – Form bleibt Verdacht
    v = pruefe_text(f"IBAN {kaputt}")
    assert v and v[0].text == kaputt and v[0].grund == "IBAN-Form"


@pytest.mark.parametrize("zeile, wert, grund", [
    ("Steuer-ID 41 056 847 324", "41 056 847 324", "Steuer-ID"),
    ("Rentenversicherungsnummer 03 241061 C 515", "03 241061 C 515", "Sozialversicherungsnummer"),
    ("Krankenversichertennummer A123456780", "A123456780", "Krankenversichertennummer"),
    ("FIN WF0F7P253MY032257 laut Schein", "WF0F7P253MY032257", "FIN"),
    ("Karte 4111 1111 1111 1111", "4111 1111 1111 1111", "Kreditkarte"),
    ("Personalausweis Nr. TLH4PLJCH", "TLH4PLJCH", "Ausweis"),
    ("Kennzeichen HF Y 4312", "HF Y 4312", "Kfz-Kennzeichen"),
])
def test_formen_mit_pruefziffer_und_kennzeichen(zeile, wert, grund):
    v = [x for x in pruefe_text(zeile) if wert in x.text or x.text in wert]
    assert v, (zeile, texte(zeile))
    assert any(grund in x.grund for x in v), [x.grund for x in v]


def test_pruefziffern_rechnungen():
    assert restrisiko.iban_gueltig(IBAN) and not restrisiko.iban_gueltig(IBAN[:-1] + "1")
    assert restrisiko.luhn_gueltig("4111 1111 1111 1111") and not restrisiko.luhn_gueltig("4111 1111 1111 1112")
    assert restrisiko.sv_nummer_gueltig("15070649C103")
    assert restrisiko.icao_gueltig("L01X00T471")


# ----------------------------------------------------------------------
# Datum mit plausiblem Geburtsjahr
# ----------------------------------------------------------------------
def test_geburtsdatum_mit_und_ohne_etikett():
    assert gemeldet("Geburtsdatum: 14.03.1961", "14.03.1961")
    assert gemeldet("Herr X (geb. 29.12.69) wohnt hier.", "29.12.69")
    assert gemeldet("Er ist am 14.03.1961 geboren.", "14.03.1961")
    assert gemeldet("Liste: 14.03.1961", "14.03.1961")               # plausibles Geburtsjahr ohne Etikett
    kind = (datetime.date.today() - datetime.timedelta(days=8 * 365)).strftime("%d.%m.%Y")
    assert gemeldet(f"Geburtsdatum des Kindes: {kind}", kind)        # hinter Etikett jedes Alter


@pytest.mark.parametrize("zeile", [
    "Versicherungsbeginn 01.04.1998",
    "Datum 19.06.2025",
    "Beschäftigung 01.09.1985 – 31.08.1988",
    "01.09.1985\t\t31.08.1988\t\tAusbildung",
    "Ablauf: 01.04.2030",
])
def test_vertragsdaten_und_zeitraeume_sind_kein_geburtsdatum(zeile):
    assert texte(zeile) == []


# ----------------------------------------------------------------------
# Kontakt
# ----------------------------------------------------------------------
def test_e_mail_adressen():
    assert gemeldet("Bitte an a.krause@schwarzwald-versicherung.de", "a.krause@schwarzwald-versicherung.de")
    assert gemeldet("Von: <ionescu854@gmx . de>", "ionescu854@gmx . de")          # OCR mit Leerzeichen
    assert texte("Schäden bitte an schaden@taunus-versicherung.de melden.") == []   # Funktionspostfach
    assert gemeldet("Homepage www.mueller-hausverwaltung.de", "www.mueller-hausverwaltung.de")


# ----------------------------------------------------------------------
# Namen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, wert", [
    ("Sehr geehrte Frau Bonnet,", "Bonnet"),
    ("Vorstand: Dipl.-Kfm. Anton Schulze (Vorsitzender), Petra Strauß", "Anton Schulze"),
    ("Vorstand: Dipl.-Kfm. Anton Schulze (Vorsitzender), Petra Strauß", "Petra Strauß"),
    ("Kołodziej, Grzegorz\t\t14.03.1961", "Kołodziej"),
    ("STOJANOVIĆ, MIRELA", "STOJANOVIĆ"),
    ("Mit freundlichen Grüßen\ni. A. Andrea Krause", "Andrea Krause"),
    ("Paul Freitag hat angerufen.", "Paul Freitag"),          # Wochentag als Nachname hinter einem Vornamen
    ("Anna Mai kommt morgen.", "Anna Mai"),                   # Monat als Nachname
    ("Herr Ågren hat angerufen.", "Ågren"),                   # unbekannter Name hinter Anrede
    ("Anrede: Dr. rer. nat. von Stetten", "Stetten"),
    ("Name: Siddiqui", "Siddiqui"),
])
def test_namen_werden_gemeldet(zeile, wert):
    assert gemeldet(zeile, wert), texte(zeile)


@pytest.mark.parametrize("zeile", [
    "Meine Frau bzw. mein Mann hat den Wagen geparkt.",
    "Am Freitag ist das Büro geschlossen.",
    "Hersteller/Typ: Renault Clio",
    "Versicherungsnehmer und versicherte Person",
    "Sehr geehrte Damen und Herren,",
    "Facharzt für Innere Medizin",
])
def test_gewoehnliche_woerter_sind_keine_namen(zeile):
    assert texte(zeile) == []


# ----------------------------------------------------------------------
# Anschriften, Ort-Datum, Reste neben Platzhaltern
# ----------------------------------------------------------------------
def test_anschriften():
    assert gemeldet("Neue Anschrift: Hauptstr. 5, 12345 Berlin", "Hauptstr. 5")
    assert gemeldet("Neue Anschrift: Hauptstr. 5, 12345 Berlin", "12345 Berlin")
    assert gemeldet("Zeuge wohnt Platz der Republik 99 a", "Platz der Republik 99 a")
    assert gemeldet("Ort: Frankfurt am Main", "Frankfurt am Main")
    assert gemeldet("Tübingen, 14. Januar 2025", "Tübingen")
    assert texte("Gesendet: Mittwoch, 12. März 2025") == []


def test_reste_neben_platzhaltern():
    assert gemeldet("Untere [ADRESSE]", "Untere")
    assert gemeldet("[PLZ ORT]OPf.", "OPf.")
    assert gemeldet("[ADRESSE] 54", "54")
    assert texte("Herr [PERSON A] und Frau [PERSON B]") == []
    assert texte("Facharzt für Innere Medizin · [ADRESSE]") == []


# ----------------------------------------------------------------------
# Was nie Verdacht ist: Platzhalter, NIE-Liste, abgewählte Stellen
# ----------------------------------------------------------------------
def test_platzhalter_sind_nie_verdacht():
    text = ("[PERSON A]\n[ADRESSE]\n[PLZ ORT]\nKundennummer [VERTRAGS-NR]\nIBAN [IBAN]\n[GESCHWÄRZT]\n"
            "Sehr geehrte Frau [PERSON A],\n[P B] und [F A]\nTelefon [TELEFON]")
    assert texte(text) == []
    # eigene Platzhalter des Laufs (kein Klammermuster) über die Liste
    assert texte("Kunde XQ-1234567-ZZ", platzhalter=["XQ-1234567-ZZ"]) == []
    assert texte("Kunde XQ-1234567-ZZ") != []


def test_nie_liste_und_abgewaehlte_stellen():
    zeile = "Rückruf bitte unter Tel. 0911 123456"
    assert gemeldet("Vertreten durch Petra Strauß", "Petra Strauß")
    assert not gemeldet("Vertreten durch Petra Strauß", "Petra Strauß", nie=["Petra Strauß"])
    assert gemeldet(zeile, "0911 123456")
    assert not gemeldet(zeile, "0911 123456", abgewaehlt=["0911 123456"])


# ----------------------------------------------------------------------
# Windows-Sonderzeichen (Vertrag 12.7): NBSP, sichtbarer weicher Trennstrich, U+2011
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, wert", [
    ("Versicherungsnehmerin: Frau Noémie Bonnet", "Bonnet"),
    ("Kundennummer: 51­633867", "51-633867"),
    ("Telefon 0421 3498­936", "0421 3498-936"),
    ("Mobil 0171‑2345678", "0171-2345678"),
    ("E-Mail a.krause@schwarzwald­versicherung.de", "a.krause@schwarzwald-versicherung.de"),
    ("IBAN DE89 3704 0044 0532 0130 00", IBAN),
])
def test_windows_sonderzeichen(zeile, wert):
    assert gemeldet(zeile, wert), texte(zeile)


# ----------------------------------------------------------------------
# PDF: Rechtecke, Seiten, Platzhalter auf der Seite, Laufzeit
# ----------------------------------------------------------------------
def test_rechtecke_liegen_auf_dem_wert(tmp_path):
    pdf = pdf_mit_zeilen(tmp_path / "r.pdf", ["Sehr geehrte Damen und Herren,", "",
                                              "Ihre Vertragsnummer lautet 47.897.336.2.",
                                              "Mit freundlichen Grüßen"])
    verdacht = restrisiko_pruefen(pdf)
    assert len(verdacht) == 1, verdacht
    v = verdacht[0]
    assert isinstance(v, Verdacht) and v.seite == 0 and v.text == "47.897.336.2"
    with fitz.open(pdf) as doc:
        soll = doc[0].search_for("47.897.336.2")[0]
    assert v.rechtecke and all(fitz.Rect(r).intersects(soll) for r in v.rechtecke)
    assert abs(fitz.Rect(v.rechtecke[0]).x0 - soll.x0) < 2 and abs(fitz.Rect(v.rechtecke[0]).x1 - soll.x1) < 2
    d = verdacht_als_dict(v)
    assert d["seite"] == 0 and isinstance(d["rechtecke"][0], list) and len(d["rechtecke"][0]) == 4


def test_mehrere_seiten_und_gedrehte_seite(tmp_path):
    doc = fitz.open()
    for i in range(3):
        seite = doc.new_page()
        seite.insert_text((60, 100), "Bitte um Rückruf." if i != 1 else "Kundennummer 2520868691", fontsize=11)
    doc[1].set_rotation(90)
    pdf = tmp_path / "s.pdf"
    doc.save(pdf)
    doc.close()
    verdacht = restrisiko_pruefen(pdf)
    assert [(v.seite, v.text) for v in verdacht] == [(1, "2520868691")]
    with fitz.open(pdf) as d:
        seite = d[1]
        seite.remove_rotation()                       # Koordinaten wie in der Vorschau (nach remove_rotation)
        soll = seite.search_for("2520868691")[0]
    assert fitz.Rect(verdacht[0].rechtecke[0]).intersects(soll)


def test_laufzeit_textseite(tmp_path):
    zeilen = [f"Zeile {i}: Der Versicherungsnehmer hat den Antrag vom 12.03.2025 unterschrieben, Betrag "
              f"{i},50 EUR." for i in range(55)]
    pdf = pdf_mit_zeilen(tmp_path / "l.pdf", zeilen, fontsize=8, abstand=13, y=40)
    restrisiko_pruefen(pdf)                           # Wissensbasis laden (einmal je Programmstart)
    beginn = time.perf_counter()
    assert restrisiko_pruefen(pdf) == []
    assert time.perf_counter() - beginn < 1.0          # Ziel 0,3 s/Seite; Spielraum für langsame CI-Rechner


# ----------------------------------------------------------------------
# Scan-Seiten: OCR aus dem Zwischenspeicher, gleiche Ausrichtung, ungelesene Seite
# ----------------------------------------------------------------------
def _scan(pfad, zeilen, dpi=150, unterschrift=False):
    """Scan-Seite: gerenderter Text als Bild; liefert die Wortkästen (wie eine OCR)."""
    vorlage = fitz.open()
    seite = vorlage.new_page()
    y = 100
    for z in zeilen:
        seite.insert_text((60, y), z, fontsize=12, fontname="helv")
        y += 20
    woerter = [tuple(w[:5]) for w in seite.get_text("words")]
    if unterschrift:                                   # handschriftliche Unterschrift: Kurven unter der Grußformel
        form = seite.new_shape()
        for k in range(6):
            form.draw_bezier((70 + 25 * k, y + 8), (80 + 25 * k, y - 10), (90 + 25 * k, y + 22), (95 + 25 * k, y + 6))
        form.finish(color=(0, 0, 0), width=1.6)
        form.commit()
        seite.insert_text((70, y + 30), "J. Kowalczyk", fontsize=12, fontname="helv")
    pix = seite.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=seite.rect.width, height=seite.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    vorlage.close()
    doc.save(pfad)
    doc.close()
    return Path(pfad), woerter


def test_scan_seite_aus_dem_ocr_zwischenspeicher_ohne_zweiten_ocr_lauf(tmp_path):
    pdf, woerter = _scan(tmp_path / "scan.pdf", ["Sehr geehrte Damen und Herren,", "Vertrag LV-2014-697971",
                                                 "Mit freundlichen Grüßen"])
    dienst = OcrAttrappe()
    verdacht = restrisiko_pruefen(pdf, ocr=dienst, ocr_modus={0: "seite"}, ocr_woerter={0: woerter})
    assert dienst.aufrufe == []                       # unveränderte Seite: Wörter der Analyse, keine OCR
    v = [x for x in verdacht if x.text == "LV-2014-697971"]
    assert v and v[0].seite == 0 and v[0].rechtecke
    soll = fitz.Rect(next(w[:4] for w in woerter if w[4] == "LV-2014-697971"))
    assert fitz.Rect(v[0].rechtecke[0]).intersects(soll)


def test_scan_seite_wird_mit_der_ausrichtung_des_originals_gelesen(tmp_path):
    pdf, woerter = _scan(tmp_path / "scan.pdf", ["Sehr geehrte Damen und Herren,", "Kundennummer 2520868691",
                                                 "Mit freundlichen Grüßen"])
    dienst = OcrAttrappe({0: woerter})
    verdacht = restrisiko_pruefen(pdf, ocr=dienst, ocr_modus={0: "seite"}, winkel={0: 180})
    assert dienst.aufrufe == [{"seite": 0, "clip": None, "winkel": 180}]
    assert [v.text for v in verdacht] == ["2520868691"]


def test_ungelesene_scan_seite_ist_seitenverdacht(tmp_path):
    pdf, _ = _scan(tmp_path / "scan.pdf", ["Herr Max Mustermann, Hauptstr. 5"])
    verdacht = restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: []}), ocr_modus={0: "seite"})
    assert [(v.seite, v.start, v.rechtecke) for v in verdacht] == [(0, -1, [])]
    assert verdacht[0].grund == restrisiko.GRUND_SEITE_UNGELESEN
    # ohne OCR-Dienst genauso: eine Scan-Seite, die niemand gelesen hat, ist nie unverdächtig
    assert restrisiko_pruefen(pdf, ocr=None, ocr_modus={0: "seite"})[0].grund == restrisiko.GRUND_SEITE_UNGELESEN


def test_unplausible_lesung_einer_scan_seite_ist_seitenverdacht(tmp_path):
    """Eine verdrehte Seite liest die OCR als wortähnlichen Buchstabensalat. Liest die Kontroll-OCR mit derselben
    (falschen) Ausrichtung wie die Analyse, greift keine Regel verlässlich – dann ist die Seite selbst der
    Verdacht (Maß und Schwellen der OCR, aufrecht gelesene Seiten bleiben unverdächtig)."""
    pdf, woerter = _scan(tmp_path / "scan.pdf", ["Sehr geehrte Damen und Herren,",
                                                 "wir bestätigen den Eingang Ihrer Unterlagen.",
                                                 "Mit freundlichen Grüßen"])
    salat = ["youyseN", "uuewlesjsnyy", "Bunjiamuy", "uaBunjne", "Japuas", "ualeyq", "yalsıa", "Bunzıaq",
             "ualyıaz", "ayosyuy", "Bunpuaz", "ıɐsnɐɥ", "ɹǝʇuıɥ", "ʇɥɔıu"]
    gedreht = [(*w[:4], salat[i % len(salat)]) for i, w in enumerate(woerter)]
    assert len(gedreht) >= 10
    verdacht = restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: gedreht}), ocr_modus={0: "seite"}, winkel={0: 0})
    seite = [v for v in verdacht if v.grund == restrisiko.GRUND_SEITE_UNPLAUSIBEL]
    assert [(v.seite, v.start, v.rechtecke) for v in seite] == [(0, -1, [])], verdacht
    # aufrecht gelesen: kein Seitenverdacht; wenige Wörter (Stempel, Seitenzahl) werden nicht bewertet
    aufrecht = restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"})
    assert not [v for v in aufrecht if v.start == -1], aufrecht
    assert not restrisiko._lesung_unplausibel(gedreht[:5])


def test_unterschrift_unter_der_grussformel_auf_scan(tmp_path):
    pdf, woerter = _scan(tmp_path / "u.pdf", ["Vielen Dank für Ihre Nachricht.", "Mit freundlichen Grüßen"],
                         unterschrift=True)
    # die OCR liest den Namen unter der Unterschrift nicht (wie bei echten Scans, wenn sie ihn kreuzt)
    verdacht = restrisiko_pruefen(pdf, ocr=OcrAttrappe(), ocr_modus={0: "seite"}, ocr_woerter={0: woerter})
    v = [x for x in verdacht if x.grund == restrisiko.GRUND_UNTERSCHRIFT]
    assert v and v[0].rechtecke and fitz.Rect(v[0].rechtecke[0]).y0 > max(w[3] for w in woerter) - 2
    pdf2, woerter2 = _scan(tmp_path / "o.pdf", ["Vielen Dank für Ihre Nachricht.", "Mit freundlichen Grüßen"])
    assert restrisiko_pruefen(pdf2, ocr=OcrAttrappe(), ocr_modus={0: "seite"}, ocr_woerter={0: woerter2}) == []


def _scan_brief(pfad, rotate=0, gedreht=0, schraeg=0.0, strich=True, lesung="falsch", firma=False, zehn=False):
    """Scan eines Briefschlusses wie im CI-Korpus (007_kuendigung_DeLuca): Grußformel, Unterschriftszug quer durch
    den gedruckten Namen "V. De Luca", Anlagenzeile. rotate: /Rotate der Scan-Seite (Bild gegenläufig gespeichert,
    Anzeige aufrecht); gedreht: Bild um 90/180° gedreht OHNE /Rotate (die OCR liest dann in dieser Ausrichtung);
    schraeg: Schräglage in Grad. lesung "falsch": die OCR liest den Zug als hohes Wort "Dee" und den durchkreuzten
    Namen als "DeLuca" (wie im CI-Korpus); "keine": im Unterschriftsblock liest sie nichts; "med" und "az": wie
    Tesseract diesen Block wirklich liest – Name und Zug als bekanntes Wort "Med" (111 x 12 pt) neben "Do", bzw. den
    Zug als kleingeschriebenes "az" (106 x 18,5 pt). firma: statt Zug und Name eine Firmenzeile und eine Abteilung
    (harmlose Lesung). zehn: OCR-Wörter als 10-Tupel wie OcrDienst.ergebnis() (Block, Zeile, Wort, Ausrichtung 0,
    Schräglage = schraeg). Liefert (pdf, OCR-Wörter in Seitenkoordinaten nach remove_rotation in Lesefolge,
    Rechteck des Namens)."""
    vorlage = fitz.open()
    s = vorlage.new_page()
    y = 100
    for z in ["Sehr geehrte Damen und Herren,", "vielen Dank für Ihre Nachricht vom Montag.",
              "Bitte bestätigen Sie den Eingang.", "Mit freundlichen Grüßen"]:
        s.insert_text((60, y), z, fontsize=12, fontname="helv")
        y += 20
    name_y = y + 24
    if firma:
        s.insert_text((60, name_y - 10), "Donau Leben AG", fontsize=12, fontname="helv")
        s.insert_text((60, name_y + 8), "Kundenservice", fontsize=12, fontname="helv")
    else:
        s.insert_text((62, name_y), "V. De Luca", fontsize=12, fontname="helv")
    if strich and not firma:
        form = s.new_shape()
        for k in range(5):
            form.draw_bezier((58 + 22 * k, name_y - 2), (66 + 22 * k, name_y - 26), (74 + 22 * k, name_y + 10),
                             (80 + 22 * k, name_y - 6))
        form.finish(color=(0.05, 0.1, 0.45), width=1.4)
        form.commit()
    s.insert_text((60, name_y + 26), "Anlage: Kopie Personalausweis", fontsize=11, fontname="helv")
    woerter = [tuple(w[:8]) for w in s.get_text("words")]
    zoom = 150 / 72
    matrix = fitz.Matrix(zoom, zoom).prerotate(schraeg + gedreht - rotate)
    pix = s.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY, alpha=False)
    doc = fitz.open()
    p = doc.new_page(width=pix.width / zoom, height=pix.height / zoom)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    if rotate:
        p.set_rotation(rotate)
    drehung = p.rotation_matrix

    def kasten(r):
        ecken = [fitz.Point((q.x - pix.x) / zoom, (q.y - pix.y) / zoom) * drehung
                 for q in (fitz.Point(e) * matrix for e in (r.tl, r.tr, r.bl, r.br))]
        return (min(e.x for e in ecken), min(e.y for e in ecken), max(e.x for e in ecken), max(e.y for e in ecken))

    namen = [w for w in woerter if w[4] in ("V.", "De", "Luca")]
    name = fitz.Rect(kasten(fitz.Rect(namen[0][:4]))) if namen else None
    for w in namen[1:]:
        name |= fitz.Rect(kasten(fitz.Rect(w[:4])))
    ocr = []
    for w in woerter:
        rest = tuple(w[5:8]) + (0, schraeg) if zehn else ()
        if w[4] in ("V.", "De"):
            continue
        if w[4] == "Luca":
            if lesung == "falsch":
                zug = fitz.Rect(56, name_y - 26, 170, name_y + 10)
                ocr.append(kasten(zug) + ("Dee",) + rest)
                ocr.append(kasten(fitz.Rect(namen[1][:4]) | fitz.Rect(w[:4])) + ("DeLuca",) + rest)
            elif lesung == "med":
                ocr.append(kasten(fitz.Rect(57.6, name_y - 11.0, 168.9, name_y + 0.7)) + ("Med",) + rest)
                ocr.append(kasten(fitz.Rect(142.3, name_y - 12.0, 169.8, name_y + 3.6)) + ("Do",) + rest)
            elif lesung == "az":
                ocr.append(kasten(fitz.Rect(57.0, name_y - 14.0, 163.0, name_y + 4.5)) + ("az",) + rest)
            continue
        ocr.append(kasten(fitz.Rect(w[:4])) + (w[4],) + rest)
    vorlage.close()
    doc.save(pfad)
    doc.close()
    return Path(pfad), ocr, name


class OcrAttrappeErgebnis(OcrAttrappe):
    """OcrDienst-Ersatz mit ergebnis() (10-Tupel samt Ausrichtung und Schräglage) – wie der echte Dienst."""

    def ergebnis(self, pdf_pfad, seite_nr0, dpi=300, clip=None, winkel=None):
        self.aufrufe.append({"seite": seite_nr0, "clip": clip, "winkel": winkel, "ergebnis": True})
        return {"woerter": list(self.woerter_je_seite.get(seite_nr0, [])), "winkel": winkel or 0, "warnung": None}


@pytest.mark.parametrize("lage", [dict(), dict(rotate=90), dict(rotate=180), dict(rotate=270), dict(gedreht=180),
                                  dict(gedreht=90), dict(schraeg=2.5), dict(rotate=90, schraeg=-1.5),
                                  dict(schraeg=5), dict(schraeg=6), dict(schraeg=7), dict(schraeg=-6),
                                  dict(rotate=90, schraeg=6), dict(rotate=90, schraeg=-7)],
                         ids=["0", "rotate90", "rotate180", "rotate270", "kopfstehend", "quer", "schraeg",
                              "rotate90_schraeg", "schraeg5", "schraeg6", "schraeg7", "schraeg-6", "rotate90_schraeg6",
                              "rotate90_schraeg-7"])
@pytest.mark.parametrize("lesung", ["falsch", "keine", "med", "az"])
def test_unterschriftsblock_mit_durchkreuztem_namen_auf_scan(tmp_path, lage, lesung):
    """Der vom Unterschriftszug durchkreuzte Name unter der Grußformel (CI-Korpus 007_kuendigung_DeLuca): die OCR
    liest den Zug als hohes "Wort" und den Namen als unbekanntes "DeLuca", dort gar nichts – oder, wie Tesseract
    diesen Block wirklich liest, Name und Zug als bekanntes Wort "Med" (Kasten 111 pt breit für drei Zeichen) bzw.
    als kleingeschriebenes "az" über 106 pt. Nichts davon ist eine verlässliche Lesung: Verdacht MIT Rechteck auf dem
    Namen, auf gedrehten und schrägen Scans genauso (Bereich in Leserichtung) – auch bei 5-7° Schräglage, wenn die
    OCR-Wörter (5-Tupel) keine Schräglage tragen und das Seitenmodell die Grußformel in Einzelwörter zerlegt."""
    pdf, ocr, name = _scan_brief(tmp_path / "u.pdf", lesung=lesung, **lage)
    verdacht = restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: ocr}), ocr_modus={0: "seite"}, winkel={0: 0})
    v = [x for x in verdacht if x.grund == restrisiko.GRUND_UNTERSCHRIFT]
    assert v and v[0].start == -1, verdacht
    assert any(fitz.Rect(r).intersects(name) for r in v[0].rechtecke), (v[0].rechtecke, name)
    # das Rechteck bleibt im Unterschriftsblock (keine ganze Seite, nicht der Brieftext darüber)
    with fitz.open(pdf) as d:
        flaeche = abs(d[0].rect)
    assert sum(abs(fitz.Rect(r)) for r in v[0].rechtecke) < 0.05 * flaeche


@pytest.mark.parametrize("lage", [dict(), dict(rotate=90), dict(gedreht=180)], ids=["0", "rotate90", "kopfstehend"])
def test_unterschriftsblock_mit_harmloser_lesung_bleibt_unverdaechtig(tmp_path, lage):
    """Firmenzeile und Abteilung unter der Grußformel, verlässlich gelesen: kein Verdacht."""
    pdf, ocr, _ = _scan_brief(tmp_path / "f.pdf", firma=True, **lage)
    assert restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: ocr}), ocr_modus={0: "seite"}, winkel={0: 0}) == []


def test_unterschriftsblock_geschwaerzt_bleibt_unverdaechtig(tmp_path):
    """Name geschwärzt (graues Rechteck + Platzhalter auf der Textebene wie von der Schwärzung), ohne Zug: der
    Personen-Platzhalter und sein Rechteck erklären die Tinte – kein Verdacht."""
    pdf, ocr, name = _scan_brief(tmp_path / "g.pdf", strich=False, lesung="keine")
    with fitz.open(pdf) as d:
        s = d[0]
        s.draw_rect(name + (-2, -2, 2, 2), color=None, fill=restrisiko.FUELLFARBE)
        s.insert_text((name.x0, name.y1 - 2), "[PERSON A]", fontsize=8, fontname="helv")
        d.save(tmp_path / "g2.pdf")
    verdacht = restrisiko_pruefen(tmp_path / "g2.pdf", ocr=OcrAttrappe({0: ocr}), ocr_modus={0: "seite"},
                                  platzhalter=["[PERSON A]"])
    assert verdacht == [], verdacht


def test_grussformel_auch_wie_die_ocr_sie_liest():
    for zeile in ("Mit freundlichen Grüßen", "Mit freundlichen GrüBen", "Mlt freundllchen Grüßen,", "MfG",
                  "Freundliche Griiße", "mit freundlichem Gruss", "Hochachtungsvoll", "Viele Grüße aus Köln"):
        assert restrisiko.ist_grussformel(zeile), zeile
    for zeile in ("Mit freundlicher Unterstützung", "Herzlichen Glückwunsch", "Kündigung", "Freundin"):
        assert not restrisiko.ist_grussformel(zeile), zeile


@pytest.mark.parametrize("lage", [dict(schraeg=5), dict(schraeg=6), dict(schraeg=7), dict(schraeg=-6),
                                  dict(rotate=90, schraeg=6), dict(rotate=90, schraeg=-5)],
                         ids=["5", "6", "7", "-6", "rotate90_6", "rotate90_-5"])
def test_schraeger_scan_mit_ausrichtung_und_schraeglage_der_ocr(tmp_path, monkeypatch, lage):
    """Der OCR-Dienst liefert über ergebnis() 10-Tupel mit Ausrichtung und Schräglage. Die Prüfung holt die Wörter
    dort (nicht über woerter(), das nur 5-Tupel kennt) und reicht Ausrichtung und Schräglage an die Tintenprüfung
    durch: Seitenmodell und Bereiche werden gerade gerückt, die Grußformel ist EINE Zeile, der Name bekommt einen
    Verdacht."""
    pdf, ocr, name = _scan_brief(tmp_path / "s.pdf", lesung="keine", zehn=True, **lage)
    gesehen = []
    original = restrisiko._unterschrift_pruefen

    def mitschreiben(*args, **kwargs):
        gesehen.append(args[5] if len(args) > 5 else kwargs.get("ausrichtung"))
        return original(*args, **kwargs)

    monkeypatch.setattr(restrisiko, "_unterschrift_pruefen", mitschreiben)
    dienst = OcrAttrappeErgebnis({0: ocr})
    verdacht = restrisiko_pruefen(pdf, ocr=dienst, ocr_modus={0: "seite"}, winkel={0: 0})
    assert [a.get("ergebnis") for a in dienst.aufrufe] == [True]
    assert gesehen and gesehen[0] == (0, float(lage["schraeg"])), gesehen
    v = [x for x in verdacht if x.grund == restrisiko.GRUND_UNTERSCHRIFT]
    assert v and any(fitz.Rect(r).intersects(name) for r in v[0].rechtecke), verdacht


def test_grussformel_ueber_zerlegte_zeilen():
    """Ohne Schräglage zerlegt das Seitenmodell eine schräge Grußformel in Einzelwörter: zusammen sind sie eine
    Formel (mit dem Schlusswort, auch wie die OCR es liest); unzusammenhängende kurze Zeilen nicht."""
    m = restrisiko.sm.dokument_aus_text("Sehr geehrte Damen und Herren,\nMit\nfreundlichen\nGrüBen,\nV.\nAnlage")
    folge = [(z.id, z) for z in m.seiten[0].zeilen]
    gruppen = restrisiko._grussformel_gruppen(m.seiten[0].text, folge)
    texte = [[m.seiten[0].text[z.start:z.ende] for zid, z in folge if zid in g] for g in gruppen]
    assert texte == [["Mit", "freundlichen", "GrüBen,"]], texte
    m2 = restrisiko.sm.dokument_aus_text("Mit\nder\nPost\nfreundlich")
    assert restrisiko._grussformel_gruppen(m2.seiten[0].text, [(z.id, z) for z in m2.seiten[0].zeilen]) == []


def test_lesung_erklaert_tinte_nur_mit_passendem_kasten():
    """Eine OCR-Lesung erklärt Tinte nur, wenn ihr Kasten zum Text passt: "Med" (bekanntes Wort) oder "az"
    (kleingeschrieben) über 106-111 pt sind ein Zug, kein Wort; dieselben Lesungen in normaler Breite bleiben harmlos.
    Ein hoher Kasten um ein bekanntes Wort ("Mandant" samt Zug darüber) erklärt nur auf Seiten, auf denen hohe
    Kästen üblich sind (Fax)."""
    m = restrisiko.sm.dokument_aus_text("Med az Mandant").seiten[0]
    p = restrisiko._Seitenpruefung(m, restrisiko._Wissen(restrisiko._wissen_laden()))

    def harmlos(wort, breite, hoehe, **kw):
        s = m.text.index(wort)
        return p.lesung_harmlos(s, s + len(wort), hoehe, 11.5, lese_breite=breite, **kw)

    assert harmlos("Med", 20.0, 11.8) and harmlos("az", 12.0, 8.0)
    assert not harmlos("Med", 111.3, 11.8) and not harmlos("az", 106.3, 18.5)
    assert harmlos("Mandant", 45.0, 11.0)
    assert not harmlos("Mandant", 88.1, 24.0, hohe_kaesten=False)       # 24 pt > 1,8 x 11,5 pt
    assert harmlos("Mandant", 88.1, 24.0, hohe_kaesten=True)


def test_hoher_wortkasten_erklaert_nur_eine_textzeile(tmp_path):
    """Ein bekanntes Wort in einem hohen OCR-Kasten erklärt dessen Tinte nur, wenn sie in EINEM Textband liegt:
    Tabellenkopf mit grauem Grund (der Rest des Kastens ist leer) ja; "Mandant" samt durchkreuztem Namen darüber
    nein."""
    vorlage = fitz.open()
    s = vorlage.new_page()
    s.draw_rect(fitz.Rect(60, 90, 200, 125), color=None, fill=(0.85, 0.85, 0.85))
    s.insert_text((70, 112), "Leistungserbringer", fontsize=11, fontname="hebo")
    s.insert_text((302, 102), "V. De Luca", fontsize=11, fontname="helv")
    s.insert_text((300, 117), "Mandant", fontsize=10, fontname="helv")
    pix = s.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    bild = restrisiko._Seitenbild(p)
    assert bild.ein_textband(fitz.Rect(62, 88, 198, 127), 0, 10.5)
    assert not bild.ein_textband(fitz.Rect(298, 88, 380, 122), 0, 10.5)
    doc.close()
    vorlage.close()


def _scan_vollmacht(pfad, lesung="keine", zug=True, rechts_geschwaerzt=True):
    """Zweispaltiger Unterschriftsblock einer Vollmacht wie im Generator (dokumenttypen.py): Ort, Datum – Zug über
    der Linie – Name – Rolle ("Mandant" | "Makler"), ohne Grußformel und ohne "Unterschrift". Links ist der Name vom
    Zug durchkreuzt und von der Erkennung verpasst; die OCR liest dort nichts (lesung "keine") oder Rolle, Name und
    Zug als EIN hohes Wort "Mandant" (lesung "mandant", wie Tesseract bei 150 dpi). Rechts ist der Name geschwärzt
    (graues Rechteck + "[PERSON B]"). Liefert (pdf, OCR-Wörter, Rechteck des linken Namens)."""
    vorlage = fitz.open()
    s = vorlage.new_page()
    s.insert_text((60, 100), "§ 5 Die Haftung des Maklers ist auf die Mindestversicherungssumme beschränkt.",
                  fontsize=11, fontname="helv")
    for x, rolle, name in ((60, "Mandant", "V. De Luca"), (330, "Makler", "Hans Berger")):
        s.insert_text((x + 40, 160), "19.05.2025", fontsize=11, fontname="helv")
        s.draw_line((x, 200), (x + 200, 200), color=(0, 0, 0), width=0.6)
        s.insert_text((x + 2, 214), name, fontsize=11, fontname="helv")
        s.insert_text((x, 228), rolle, fontsize=10, fontname="helv")
    # Wortkästen so eng wie die der OCR (Versalhöhe bis Unterlänge), nicht wie der Schriftkasten von MuPDF
    alle = [(w[0], w[3] - 0.7 * (w[3] - w[1]), w[2], w[3], w[4]) for w in s.get_text("words")]
    namensteile = ("V.", "De", "Luca", "Hans", "Berger")
    links = fitz.Rect(alle[[w[4] for w in alle].index("V.")][:4])
    for w in alle:
        if w[4] in ("De", "Luca"):
            links |= fitz.Rect(w[:4])
    woerter = [w for w in alle if w[4] not in namensteile]
    if lesung == "mandant":
        woerter = [w for w in woerter if w[4] != "Mandant"] + [(60.0, 192.0, 150.0, 231.0, "Mandant")]
    if zug:
        form = s.new_shape()
        for k in range(5):
            form.draw_bezier((58 + 22 * k, 212), (66 + 22 * k, 188), (74 + 22 * k, 224), (80 + 22 * k, 208))
        form.finish(color=(0.05, 0.1, 0.45), width=1.4)
        form.commit()
    pix = s.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    if rechts_geschwaerzt:
        p.draw_rect(fitz.Rect(330, 203, 400, 217), color=None, fill=restrisiko.FUELLFARBE)
        p.insert_text((334, 213), "[PERSON B]", fontsize=8, fontname="helv")
    vorlage.close()
    doc.save(pfad)
    doc.close()
    return Path(pfad), woerter, links


def test_rollenzeilen_erkennung():
    """Rollen ohne Doppelpunkt ("Mandant", "Antragsteller(in)") sind Text einer Rollenzeile; Feldetiketten mit Komma
    und nummerierte Abschnittsüberschriften nicht. Der Ausdruck läuft auch an langen Wörtern nicht exponentiell
    zurück (eine OCR-Zeile mit Komma am Ende hielt den Benchmark sonst minutenlang an)."""
    r = restrisiko._ROLLE_RE
    for text in ("Mandant", "Makler", "Mandant/in", "Mandant/-in", "Antragsteller(in)", "Versicherte Person"):
        assert r.fullmatch(text), text
    for text in ("Name,", "« Unfallgegner", "4. Unfallgegner", "Name:"):
        assert not r.fullmatch(text), text
    beginn = time.perf_counter()
    assert not r.fullmatch("Versicherungsnehmerinnenvertretung" * 3 + ",")
    assert time.perf_counter() - beginn < 0.1


@pytest.mark.parametrize("lesung", ["keine", "mandant"])
def test_zweispaltiger_unterschriftsblock_ohne_grussformel(tmp_path, lesung):
    """Vollmacht mit zweispaltigem Unterschriftsblock (Rolle "Mandant" | "Makler" unter Name und Linie, kein
    "Unterschrift"-Etikett, keine Grußformel): der vom Zug durchkreuzte, von der OCR nicht oder nur als Teil eines
    hohen "Mandant"-Kastens gelesene Name bekommt einen Verdacht mit Rechteck – über der Rollenzeile."""
    pdf, woerter, name = _scan_vollmacht(tmp_path / "v.pdf", lesung=lesung)
    verdacht = restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"},
                                  platzhalter=["[PERSON B]"])
    assert any(fitz.Rect(r).intersects(name) for v in verdacht for r in v.rechtecke if v.start == -1), verdacht


def test_zweispaltiger_unterschriftsblock_geschwaerzt_ohne_zug_bleibt_unverdaechtig(tmp_path):
    """Beide Namen geschwärzt, keine Unterschrift: Rollen, Linien und Platzhalter erklären alles – kein Verdacht."""
    pdf, woerter, name = _scan_vollmacht(tmp_path / "v.pdf", zug=False)
    with fitz.open(pdf) as d:
        d[0].draw_rect(fitz.Rect(60, 203, 130, 217), color=None, fill=restrisiko.FUELLFARBE)
        d[0].insert_text((64, 213), "[PERSON A]", fontsize=8, fontname="helv")
        d.save(tmp_path / "v2.pdf")
    assert restrisiko_pruefen(tmp_path / "v2.pdf", ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"},
                              platzhalter=["[PERSON A]", "[PERSON B]"]) == []


def _scan_briefschluss(pfad, zeile, nachbar=None, name=None):
    """Scan eines Briefschlusses ohne Unterschrift: Grußformel, geschwärzter Name (graues Rechteck + "[PERSON A]"),
    daneben optional `nachbar` ("& Partner"), darunter eine gedruckte Zeile. name: statt des geschwärzten Namens ein
    gedruckter, von der Erkennung verpasster Name. Die OCR liest alles richtig."""
    vorlage = fitz.open()
    s = vorlage.new_page()
    y = 100
    for z in ["Sehr geehrte Damen und Herren,", "anbei der Befund zu Ihrer Anfrage vom Montag.",
              "Mit freundlichen Grüßen"]:
        s.insert_text((60, y), z, fontsize=11, fontname="helv")
        y += 18
    name_y = y + 14
    s.insert_text((60, name_y + 18), zeile, fontsize=11, fontname="helv")
    if nachbar:
        s.insert_text((150, name_y), nachbar, fontsize=11, fontname="helv")
    if name:
        s.insert_text((60, name_y), name, fontsize=11, fontname="helv")
    woerter = [tuple(w[:5]) for w in s.get_text("words")]
    pix = s.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    if not name:
        p.draw_rect(fitz.Rect(60, name_y - 10, 145, name_y + 3), color=None, fill=restrisiko.FUELLFARBE)
        p.insert_text((64, name_y), "[PERSON A]", fontsize=8, fontname="helv")
    vorlage.close()
    doc.save(pfad)
    doc.close()
    return Path(pfad), woerter


@pytest.mark.parametrize("zeile, nachbar", [
    ("Facharzt für Innere Medizin", None), ("Fachärztin für Allgemeinmedizin", None),
    ("Fachärztin für Hals-Nasen-Ohren-Heilkunde", None), ("Fachanwältin für Versicherungsrecht", None),
    ("Leiter Schadenabteilung", None), ("Hauptagentur Nord", None), ("Kundenservice", None),
    ("Rechtsanwälte", "& Partner"), ("Rechtsanwälte", "& Kollegen"), ("Rechtsanwälte", "Co. KG"),
    ("Rechtsanwälte", "LL.M."), ("Kfz-Schaden", "&Prof.Dr.med."),
])
def test_gedruckte_fach_und_firmenzeilen_im_unterschriftsblock_sind_kein_verdacht(tmp_path, zeile, nachbar):
    """Berufs-, Abteilungs- und Kanzleizeilen unter dem geschwärzten Namen und Kürzel daneben ("&", "Co.",
    "LL.M."), von der OCR richtig gelesen: keine Personenangabe, kein Verdacht."""
    pdf, woerter = _scan_briefschluss(tmp_path / "b.pdf", zeile, nachbar)
    assert restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"},
                              platzhalter=["[PERSON A]"]) == []


@pytest.mark.parametrize("name", ["F. Noori", "V. DeLuca", "Dr. med. Kowalczyk"])
def test_gedruckter_verpasster_name_im_unterschriftsblock_bleibt_verdacht(tmp_path, name):
    """Gegenprobe: ein richtig gelesener, aber von der Erkennung verpasster Name unter der Grußformel (bekannter
    Nachname, unbekannter Name) bleibt ein Verdacht – die Berufs- und Firmenwörter machen ihn nicht harmlos."""
    pdf, woerter = _scan_briefschluss(tmp_path / "n.pdf", "Facharzt für Innere Medizin", name=name)
    verdacht = restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"})
    nachname = name.split()[-1]
    soll = fitz.Rect(next(w[:4] for w in woerter if w[4] == nachname))
    assert any(fitz.Rect(r).intersects(soll) for v in verdacht for r in v.rechtecke), verdacht


def test_linienrest_nur_gerade_linien():
    """Reste gerader Unter-/Durchstreichungen (dünn, leicht geneigt, mit Pixelrauschen) zählen nicht als Tinte; ein
    flacher, dünner Wellenzug (Kugelschreiber-Unterschrift im Fenster der Neigung) schon."""
    gerade = [(x, 10 + x // 30) for x in range(90)] + [(x, 11 + x // 30) for x in range(0, 90, 3)]
    assert restrisiko._linienrest(gerade)
    import math
    welle = [(x, round(10 + 3 * math.sin(x / 6))) for x in range(93)]
    welle += [(x, y + 1) for x, y in welle[::2]]
    assert max(sum(1 for p in welle if p[0] == x) for x in range(93)) <= restrisiko.LINIE_DICKE
    assert not restrisiko._linienrest(welle)


def test_flacher_unterschriftszug_unter_der_grussformel(tmp_path):
    """Ein flacher Unterschriftszug, wie ihn der Benchmark-Generator zeichnet (3-5 Bögen, 110 x 22 pt, Strich
    1,1 pt), als Scan mit 200 dpi und JPEG: dünn genug für das Fenster der Linienreste – trotzdem ein Verdacht."""
    import random
    rng = random.Random(0)
    vorlage = fitz.open()
    s = vorlage.new_page()
    s.insert_text((60, 100), "Vielen Dank für Ihre Nachricht.", fontsize=12, fontname="helv")
    s.insert_text((60, 120), "Mit freundlichen Grüßen", fontsize=12, fontname="helv")
    woerter = [tuple(w[:5]) for w in s.get_text("words")]
    form = s.new_shape()
    p = fitz.Point(70, 150)
    for _ in range(rng.randint(3, 5)):
        q = fitz.Point(p.x + 110 / 4 * rng.uniform(0.6, 1.2), 150 - 22 * rng.uniform(-0.3, 0.6))
        c1 = fitz.Point(p.x + rng.uniform(5, 20), 150 - 22 * rng.uniform(0.2, 1.0))
        c2 = fitz.Point(q.x - rng.uniform(5, 20), 150 + 22 * rng.uniform(-0.2, 0.5))
        form.draw_bezier(p, c1, c2, q)
        p = q
    form.finish(color=(0.05, 0.1, 0.45), width=1.1, closePath=False)
    form.commit()
    pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    doc = fitz.open()
    seite = doc.new_page(width=s.rect.width, height=s.rect.height)
    seite.insert_image(seite.rect, stream=pix.tobytes("jpeg", jpg_quality=60))
    doc.save(tmp_path / "z.pdf")
    doc.close()
    vorlage.close()
    verdacht = restrisiko_pruefen(tmp_path / "z.pdf", ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"})
    v = [x for x in verdacht if x.grund == restrisiko.GRUND_UNTERSCHRIFT]
    assert v and any(fitz.Rect(r).intersects(fitz.Rect(70, 125, 180, 165)) for r in v[0].rechtecke), verdacht


def _tintengruppen_je_bereich(bild, bereich, erklaert):
    """Vergleichsrechnung wie vor der Seitenmaske: die erklärten Rechtecke (um 1,5 pt vergrößert) für jeden Bereich
    eigens in dessen Ausschnitt rastern. `bild` ohne erklaeren() (Maske = Linien)."""
    daten, linie, breite, hoehe, genau = bild.ausschnitt(fitz.Rect(bereich) & bild.rect)
    maske = bytearray(linie)
    for r in erklaert:
        r = fitz.Rect(r) + (-1.5, -1.5, 1.5, 1.5)
        if not r.intersects(genau):
            continue
        x0, x1 = max(0, int((r.x0 - genau.x0) * bild.sx)), min(breite, int((r.x1 - genau.x0) * bild.sx) + 1)
        y0, y1 = max(0, int((r.y0 - genau.y0) * bild.sy)), min(hoehe, int((r.y1 - genau.y0) * bild.sy) + 1)
        for y in range(y0, y1):
            maske[y * breite + x0:y * breite + max(x0, x1)] = b"\x01" * max(0, x1 - x0)

    class Ausschnitt:
        sx, sy, dunkel, rect = bild.sx, bild.sy, bild.dunkel, bild.rect

        def ausschnitt(self, _):
            return daten, bytes(maske), breite, hoehe, genau

    return restrisiko._tintengruppen(Ausschnitt(), bereich)


def test_tintengruppen_mit_seitenmaske_wie_je_bereich(tmp_path):
    """Die erklärten Rechtecke werden EINMAL je Seite gerastert (Laufzeit linear statt Bereiche x Rechtecke); jeder
    Bereich ergibt dieselben Tintengruppen wie mit eigener Rasterung je Bereich."""
    import random
    pdf, _, _ = _scan_brief(tmp_path / "t.pdf", lesung="keine")
    rng = random.Random(4)
    erklaert = [fitz.Rect(x, y, x + rng.uniform(5, 80), y + rng.uniform(4, 20))
                for x, y in ((rng.uniform(40, 400), rng.uniform(80, 260)) for _ in range(150))]
    with fitz.open(pdf) as d:
        seitenmaske = restrisiko._Seitenbild(d[0])
        seitenmaske.erklaeren(erklaert)
        je_bereich = restrisiko._Seitenbild(d[0])
        for bereich in (fitz.Rect(45, 160, 360, 230), fitz.Rect(50, 80, 300, 140), fitz.Rect(0, 0, 612, 792),
                        fitz.Rect(100.3, 185.7, 180.9, 214.2)):
            neu = restrisiko._tintengruppen(seitenmaske, bereich)
            assert neu == _tintengruppen_je_bereich(je_bereich, bereich, erklaert), bereich
        assert restrisiko._tintengruppen(seitenmaske, fitz.Rect(45, 160, 360, 230))     # dort ist Tinte übrig


def test_laufzeit_scan_liste_mit_vielen_personen_platzhaltern(tmp_path):
    """Gescannte Bestandsliste mit 80 Zeilen, je Zeile ein Personen-Platzhalter und drei weitere: die Tintenprüfung
    rastert das Erklärte einmal je Seite – die Prüfung bleibt weit unter einer Sekunde (vorher quadratisch: über
    4 s auf diesem Rechner, 1-4 s je Seite auf realen Listen)."""
    breite, hoehe = 842, 595
    vorlage = fitz.open()
    s = vorlage.new_page(width=breite, height=hoehe)
    s.insert_text((30, 30), "Bestandsliste Makler – Stand 01.10.2026", fontsize=9, fontname="helv")
    zeilen = [50 + i * (hoehe - 70) / 80 for i in range(80)]
    for i, y in enumerate(zeilen):
        s.insert_text((30, y), f"{i + 1:3d}", fontsize=7, fontname="helv")
        s.insert_text((200, y), "Wohngebäude Komfort", fontsize=7, fontname="helv")
        s.insert_text((760, y), "aktiv", fontsize=7, fontname="helv")
    woerter = [tuple(w[:5]) for w in s.get_text("words")]
    pix = s.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=breite, height=hoehe)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    for i, y in enumerate(zeilen):
        for x0, muster in ((60, "[PERSON {}]"), (300, "[GEBURTSDATUM]"), (420, "[PLZ ORT]"), (560, "[VERTRAGS-NR]")):
            p.draw_rect(fitz.Rect(x0, y - 6, x0 + 110, y + 1.5), color=None, fill=restrisiko.FUELLFARBE)
            p.insert_text((x0 + 2, y), muster.format(i + 1), fontsize=6, fontname="helv")
    doc.save(tmp_path / "l.pdf")
    doc.close()
    vorlage.close()
    restrisiko_pruefen(tmp_path / "l.pdf", ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"})
    beginn = time.perf_counter()
    restrisiko_pruefen(tmp_path / "l.pdf", ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"})
    assert time.perf_counter() - beginn < 3.0          # hier ~0,5 s; Spielraum für langsame CI-Rechner


def _scan_formular(pfad, wert="kritzel"):
    """Scan einer Formularzeile "Name:" mit handschriftlichem Wert (Kritzel, den die OCR nicht liest) oder mit
    Platzhalter (wert="platzhalter": graues Rechteck + "[PERSON A]" wie von der Schwärzung)."""
    vorlage = fitz.open()
    s = vorlage.new_page()
    s.insert_text((60, 100), "Antrag auf Leistungen aus der Unfallversicherung", fontsize=12, fontname="helv")
    s.insert_text((60, 140), "Name:", fontsize=12, fontname="helv")
    s.insert_text((60, 170), "Bitte vollständig ausfüllen und unterschreiben.", fontsize=12, fontname="helv")
    woerter = [tuple(w[:5]) for w in s.get_text("words")]
    if wert == "kritzel":
        form = s.new_shape()
        for k in range(4):
            form.draw_bezier((110 + 20 * k, 138), (116 + 20 * k, 124), (124 + 20 * k, 146), (130 + 20 * k, 134))
        form.finish(color=(0.1, 0.1, 0.4), width=1.3)
        form.commit()
    pix = s.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    if wert == "platzhalter":
        p.draw_rect(fitz.Rect(108, 128, 170, 143), color=None, fill=restrisiko.FUELLFARBE)
        p.insert_text((112, 139), "[PERSON A]", fontsize=8, fontname="helv")
    vorlage.close()
    doc.save(pfad)
    doc.close()
    return Path(pfad), woerter


def test_ungelesene_schrift_hinter_personen_etikett_auf_scan(tmp_path):
    """Hinter "Name:" steht Handschrift, die die OCR nicht liest: Verdacht mit Rechteck auf dem Wert. Steht dort
    der Platzhalter der Schwärzung, bleibt die Seite unverdächtig."""
    pdf, woerter = _scan_formular(tmp_path / "k.pdf")
    verdacht = restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"})
    v = [x for x in verdacht if x.grund == restrisiko.GRUND_PERSONENTINTE]
    assert v and any(fitz.Rect(r).intersects(fitz.Rect(115, 126, 190, 146)) for r in v[0].rechtecke), verdacht
    pdf2, woerter2 = _scan_formular(tmp_path / "p.pdf", wert="platzhalter")
    assert restrisiko_pruefen(pdf2, ocr=OcrAttrappe({0: woerter2}), ocr_modus={0: "seite"},
                              platzhalter=["[PERSON A]"]) == []


def test_formularfeld_des_originals(tmp_path):
    pdf = pdf_mit_zeilen(tmp_path / "f.pdf", ["Ort:", "", "Frankfurt am Main"])
    with fitz.open(pdf) as doc:
        r = doc[0].search_for("Frankfurt am Main")[0]
    feld = {"seite": 0, "rect": fitz.Rect(r.x0 - 2, r.y0 - 2, r.x1 + 40, r.y1 + 2), "name": "wohnort", "etikett": "Ort"}
    verdacht = restrisiko_pruefen(pdf, felder=[feld])
    assert any(v.text == "Frankfurt am Main" and "Formularfeld »Ort«" in v.grund for v in verdacht), verdacht
    anrede = {"seite": 0, "rect": fitz.Rect(r.x0 - 2, r.y0 - 2, r.x1 + 40, r.y1 + 2), "name": "anrede"}
    pdf2 = pdf_mit_zeilen(tmp_path / "a.pdf", ["Anrede:", "", "Frau"])
    assert restrisiko_pruefen(pdf2, felder=[anrede]) == []


# ----------------------------------------------------------------------
# Ende zu Ende: verpasster Wert -> _PRUEFEN mit Verdacht an der richtigen Stelle
# ----------------------------------------------------------------------
def test_schwaerzung_mit_verpasstem_wert_wird_pruefen(tmp_path):
    from anonymisierer.analyse import analysiere_pdf

    pdf = pdf_mit_zeilen(tmp_path / "e2e.pdf", ["Sehr geehrte Damen und Herren,", "",
                                                 f"bitte überweisen Sie auf IBAN {IBAN}.",
                                                 "Ihre Vertragsnummer lautet 47.897.336.2.",
                                                 "Mit freundlichen Grüßen"])
    a = analysiere_pdf(pdf, {"iban"}, [], [], ocr=OcrAttrappe())   # Erkennung sieht nur die IBAN
    assert a["fehler"] is None and [f["kategorie"] for f in a["funde"]] == ["iban"]
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=OcrAttrappe(), ocr_cache=a["ocr_cache"],
                      ziel_ordner=tmp_path / "aus")
    assert e["fehler"] is None and e["status"] == "pruefen" and e["ausgabe"].name.endswith("_PRUEFEN.pdf")
    assert "VERDACHT" in {m["code"] for m in e["meldungen"]}
    v = [x for x in e["verdacht"] if x.text == "47.897.336.2"]
    assert v and v[0].seite == 0, e["verdacht"]
    with fitz.open(pdf) as doc:
        soll = doc[0].search_for("47.897.336.2")[0]
    assert fitz.Rect(v[0].rechtecke[0]).intersects(soll)
    assert not any("3704" in x.text for x in e["verdacht"])     # die geschwärzte IBAN ist Platzhalter
    assert e.get("dauer_restrisiko_s") is not None


def test_schwaerzung_ohne_rest_bleibt_fertig(tmp_path):
    from anonymisierer.analyse import analysiere_pdf

    pdf = pdf_mit_zeilen(tmp_path / "ok.pdf", ["Sehr geehrte Damen und Herren,",
                                               f"bitte überweisen Sie auf IBAN {IBAN}.", "Mit freundlichen Grüßen"])
    a = analysiere_pdf(pdf, {"iban"}, [], [], ocr=OcrAttrappe())
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / "aus")
    assert e["status"] == "fertig" and e["verdacht"] == [], e["verdacht"]
