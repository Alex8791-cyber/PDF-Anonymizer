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
