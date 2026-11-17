"""Gegenprüfung Runde 4d: Befunde der zwei Gegenprüfer zu 9546ef1 (Regel „Etikett + Wert“ für eVB, Transferticket,
Kartenprüfnummer und Geburtsname).

Befund 1  Kammfeld (ein Zeichen je Kästchen): auf Scans liest die Texterkennung die Kästchen nicht – die Selbstkontrolle
          meldet Schrift hinter einem Kennungs-Etikett, die sie nicht lesen kann; auf der Textebene auch das
          eVB-Kammfeld.
Befund 2  Herkunftsnamen (Mainzer, Danziger, Linz, Israel) hinter „geb.“ und Geburtsnamen-Etiketten.
Befund 3  eVB-Aufzählungen mit Aufzählungszeichen, Nummern, Zusätzen und Zuordnungen („Pkw: …“).
Befund 4  eVB in Briefsätzen ohne Ankündigung („hat die Nummer“, Klammer „(Nr. …)“, „Kennz.“, „Fa.“).
Befund 5  Kartenprüfnummer hinter Kartendaten über mehrere Zeilen und hinter weiteren Etiketten.
Befund 6  Seltenere Schreibweisen (OCR-Verleser, Geburtsname-Etiketten, Kammfeld mit Spaltentrennern).
Befund 7  Regression: hinter Nummer-Etiketten gilt der allgemeine Kennungsweg wie vor Runde 4 („3/2025“, „2024/25“,
          „12/345“, „KFZ-VB 12345“).
Befund 8  Über-Schwärzung: Telefonnummern, Internetadressen, Jahresbereiche und Tarifcodes sind kein Transferticket
          und keine eVB – auch nicht hinter wenigen Wörtern ohne Ankündigung.
Befund 9  Über-Schwärzung: hinter einem leeren Feld „Geb.-Name“ ist das nächste Feld-Etikett kein Geburtsname.
Befund 10 Über-Schwärzung: „GEB.“ als Spaltenkopf einer Festbreiten-Liste macht den nächsten Kopf nicht zur Person.
Befund 11 Das Etikett „Prüfnr.“/„Kartenprüfnr.“ ist kein Name.
Befund 12 Kein Fehlverdacht „möglicher Geburtsname“ in Erläuterungen und hinter leeren Feldern.
Befund 13 Mehrdeutige Geburtsnamen („Deutsch“) und Versalwörter hinter „GEB.“ wandern nicht in fremde Stellen.
Alle Werte sind erfunden."""

import re

import pytest

import pymupdf as fitz

from anonymisierer import analyse, kennungsformen, muster
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.restrisiko import pruefe_text, restrisiko_pruefen
from anonymisierer.schwaerzung import schwaerze_pdf
from conftest import braucht_ocr
from test_kennungen_makler import OcrAttrappe, _ocr_dok, _paare, _stellen

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


def _an(funde) -> set:
    return {st["text"] for f in funde for st in f["stellen"] if st.get("an", True)}


def _gruende(text, **kw) -> list:
    return [(v.text, v.grund) for v in pruefe_text(text, **kw)]


def _ausgabe_simuliert(text, funde) -> tuple:
    """(Text der Ausgabe mit Platzhaltern, Platzhalter) – wie die Schwärzung die angehakten Stellen ersetzt."""
    spannen = sorted((st["start"], st["ende"], f.get("ersatz") or "[X]") for f in funde for st in f["stellen"]
                     if st.get("an", True))
    teile, pos, platz = [], 0, set()
    for s, e, ers in spannen:
        if s < pos:
            continue
        teile += [text[pos:s], ers]
        platz.add(ers)
        pos = e
    teile.append(text[pos:])
    return "".join(teile), sorted(platz)


def _geschwaerzt_oder_gemeldet(text, wert) -> str:
    """"weg" (geschwärzt), "VERDACHT" (lesbar, aber von der Selbstkontrolle gemeldet) oder "STILL"."""
    funde = analysiere_text(text, ALLE, [], [])
    aus, platz = _ausgabe_simuliert(text, funde)
    if wert not in aus:
        return "weg"
    if any(wert in v.text or (v.text in wert and len(v.text) >= 3) for v in pruefe_text(aus, platzhalter=platz)):
        return "VERDACHT"
    return "STILL"


def _ausgabe_text(pfad) -> str:
    with fitz.open(pfad) as doc:
        return "\n".join(s.get_text() for s in doc)


def _text_pdf(pfad, zeilen, font="helv", spalte=170, groesse=10):
    """Text-PDF; Zellen einer Zeile ("\\t\\t") in Spalten."""
    doc = fitz.open()
    seite = doc.new_page()
    y = 70
    for z in zeilen:
        for i, zelle in enumerate(z.split("\t\t")):
            seite.insert_text((50 + spalte * i, y), zelle, fontsize=groesse, fontname=font)
        y += groesse * 1.6
    doc.save(pfad)
    doc.close()
    return pfad


def _lauf(tmp_path, dokumente: dict, font="helv"):
    """Lauf über mehrere Dokumente (analysiere_pdf je Dokument, weitergabe_anwenden, schwaerze_pdf): {Name: (Analyse,
    Schwärzung, Text der Ausgabe)}."""
    teile = []
    for name, zeilen in dokumente.items():
        pdf = _text_pdf(tmp_path / f"{name}.pdf", zeilen, font=font)
        teile.append((name, pdf, analysiere_pdf(pdf, ALLE, [], [], ocr=OcrAttrappe())))
    analyse.weitergabe_anwenden([e for _, _, e in teile])
    aus = {}
    for name, pdf, e in teile:
        r = schwaerze_pdf(pdf, e["funde"], modell=e["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / f"aus_{name}")
        assert r["fehler"] is None, r
        aus[name] = (e, r, _ausgabe_text(r["ausgabe"]))
    return aus


# ======================================================================
# Befund 7 (hoch): allgemeiner Kennungsweg hinter Nummer-Etiketten wie vor Runde 4
# ======================================================================
# Etiketten, hinter denen a88d8da (Stand vor Runde 4) jede Kennungsform schwärzte: Nummer-Wort als Abkürzung oder als
# Teil eines zusammengesetzten Worts
NUMMER_ETIKETTEN_VOR_RUNDE4 = ["Versicherungsbestätigung Nr.", "Versicherungsbestätigungs-Nr.",
                               "Versicherungsbestätigungsnummer:", "VB-Nr.", "eVB-Nr.", "Transferticket-Nr.",
                               "Kartenprüfnummer:"]
LAUFNUMMERN = ["1/2024", "3/2025", "12/345", "1/234", "2024/25", "2023/2024", "2024-25", "2019-20", "KFZ-VB 12345",
               "SF-TT 4711 0815"]


@pytest.mark.parametrize("etikett", NUMMER_ETIKETTEN_VOR_RUNDE4)
@pytest.mark.parametrize("wert", LAUFNUMMERN)
def test_b7_laufnummer_hinter_nummer_etikett(etikett, wert):
    text = f"{etikett} {wert}\nVersicherungsnehmerin: Anna Weber"
    funde = analysiere_text(text, ALLE, [], [])
    assert wert in _an(funde), _paare(funde)


@pytest.mark.parametrize("etikett", ["Versicherungsbestätigung Nr.", "Versicherungsbestätigungs-Nr.", "VB-Nr.",
                                     "eVB-Nr.", "Kartenprüfnummer:"])
@pytest.mark.parametrize("wert", ["3/2025", "12/345", "2024/25", "2019-20", "KFZ-VB 12345"])
def test_b7_laufnummer_auf_ocr_text(etikett, wert):
    funde = analyse._analysiere_dokument(_ocr_dok([f"{etikett} {wert}", "Versicherungsnehmerin: Anna Weber"]),
                                         ALLE, [], [])
    assert wert in _an(funde), _paare(funde)


@pytest.mark.parametrize("text, wert", [
    ("eVB-Nr. 12/345", "12/345"),
    ("Transferticket-Nr. 12/345", "12/345"),
    ("Versicherungsbestätigungsnummer: 12/345", "12/345"),
    ("Kartenprüfnummer: 12/345", "12/345"),
    ("VB-Nr. 2024/25", "2024/25"),
])
def test_b7_selbstkontrolle_meldet_laufnummer(text, wert):
    """Bleibt der Wert lesbar, meldet die Selbstkontrolle ihn (wie ae932bd)."""
    assert [t for t, g in _gruende(text) if wert in t], _gruende(text)


def test_b7_ende_zu_ende_vb_vermieter(tmp_path):
    aus = _lauf(tmp_path, {"vb_vermieter": ["Versicherungsbestätigung für den Vermieter", "VB-Nr. 3/2025",
                                            "Für die Wohnung besteht eine Hausratversicherung.",
                                            "Versicherungsnehmer: Peter Schmitz"],
                           "vb_jahr_nr": ["Versicherungsbestätigung", "Versicherungsbestätigung Nr. 2024/25",
                                          "Versicherungsnehmerin: Anna Weber"],
                           "vb_praefix": ["Versicherungsbestätigung", "Versicherungsbestätigung Nr. KFZ-VB 12345",
                                          "Versicherungsnehmerin: Anna Weber"]})
    for name, wert in (("vb_vermieter", "3/2025"), ("vb_jahr_nr", "2024/25"), ("vb_praefix", "12345")):
        _, r, text = aus[name]
        assert wert not in text, (name, text)
        assert r["status"] == "fertig", (name, r["status"], r["verdacht"])


@pytest.mark.parametrize("zeile", ["eVB: 2025/2026", "eVB-Nummer 2024/2025", "Transferticket: 2024/2025",
                                   "eVB-Nummer: 12/2025"])
def test_b7_zeitraum_hinter_etikett_ohne_nummer_wort_bleibt(zeile):
    """Gegenprobe: hinter einem Etikett der eigenen Wertform ohne Nummer-Abkürzung ist ein Zeitraum keine Kennung
    (a88d8da: lesbar) – auch nicht als Transferticket."""
    for funde in (analysiere_text(zeile, ALLE, [], []), analyse._analysiere_dokument(_ocr_dok([zeile]), ALLE, [], [])):
        assert not [t for k, t in _paare(funde) if k == "vertrag"], _paare(funde)


def test_b7_jahresbereich_in_transferticket_spalte(tmp_path):
    pdf = _text_pdf(tmp_path / "t.pdf", ["Fahrzeug\t\tTransferticket\t\tStatus", "VW Golf\t\tangefordert\t\taktiv",
                                         "BMW 320d\t\t2024/2025\t\taktiv"])
    e = analysiere_pdf(pdf, ALLE, [], [])
    assert ("vertrag", "2024/2025") not in _paare(e["funde"]), _paare(e["funde"])


# ======================================================================
# Befund 8 (mittel): Telefon, Internetadresse, Jahresbereich, Tarif sind kein Transferticket und keine eVB
# ======================================================================
KEIN_TICKET = [
    "Transferticket Hotline 0800-1234567",
    "Transferticket Hotline 0800/1234567",
    "Transferticket Service 0800-1234567",
    "Transferticket Kundenservice 0221-1234567",
    "Transferticket Telefax 0221-1234567",
    "Transferticket anfordern unter 0800-1234567",
    "Transferticket anfordern: 0800-1234567",
    "Transferticket Rückfragen 0221-12345-0",
    "Transferticket anfordern unter www.huk24.de",
    "Transferticket online beantragen auf www.verti24.de",
    "Transferticket Kfz 2024-2025",
    "Transferticket Versicherungsjahr 2024/2025",
    "Transferticket Laufzeit 2024-2026",
    "eVB Hotline 0800123",
    "eVB Tarif KH2024A",
    "Ihr Transferticket erhalten Sie unter 0800-1234567.",
    "Transferticket: Hotline 0800-1234567",
    "Transferticket (Hotline): 0800-1234567",
    "Transferticket – Hotline: 0800-1234567",
    "Transferticket für Tarif: PREMIUM2024",
]


@pytest.mark.parametrize("text", KEIN_TICKET)
def test_b8_kein_transferticket_keine_evb(text):
    funde = analysiere_text(text, ALLE, [], [])
    assert not [t for k, t in _paare(funde) if k == "vertrag"], _paare(funde)
    assert not [t for t in kennungsformen.kennungen(text) if t.art in ("evb", "ticket")], text


def test_b8_keine_weitergabe_in_andere_dokumente(tmp_path):
    aus = _lauf(tmp_path, {
        "wechselbrief": ["Wechsel Ihrer Kfz-Versicherung", "Sehr geehrte Frau Weber,",
                         "Transferticket Versicherungsjahr 2024/2025", "Transferticket anfordern unter www.huk24.de",
                         "Transferticket Hotline 0800-1234567", "eVB Tarif KH2024A", "Mit freundlichen Grüßen"],
        "beitragsrechnung": ["Beitragsrechnung", "Versicherungsjahr 2024/2025", "Online-Service: www.huk24.de",
                             "Tarif KH2024A gilt für das Versicherungsjahr 2024/2025."],
        "kontakt": ["Kontakt", "Service-Hotline: 0800-1234567"]})
    _, _, text = aus["beitragsrechnung"]
    for wert in ("Versicherungsjahr 2024/2025", "www.huk24.de", "Tarif KH2024A"):
        assert wert in text, text
    assert "[VERTRAGS-NR]" not in aus["kontakt"][2], aus["kontakt"][2]


@pytest.mark.parametrize("text, wert", [
    # Gegenproben: echte Transfertickets und eVB-Nummern hinter wenigen Wörtern bleiben Kennungen
    ("Transferticket hinten TT0815AB4711", "TT0815AB4711"),
    ("Ihr Transferticket bitte TT0815AB4711", "TT0815AB4711"),
    ("Transferticket: TT-2024-0815-AB", "TT-2024-0815-AB"),
    ("eVB-Nummer: K7H3M9P", "K7H3M9P"),
    ("Transferticket-Nr.: 0800123456", "0800123456"),
])
def test_b8_gegenproben_kennungen_bleiben(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert wert in _an(funde), _paare(funde)


# ======================================================================
# Befund 9 (mittel): leeres Feld „Geb.-Name“ vor einem Feld-Etikett ohne Doppelpunkt
# ======================================================================
FORMULAR_ETIKETTEN = ["Postleitzahl", "Adresszusatz", "Künstlername", "Ordensname", "Doktorgrad", "Größe", "Hobbys",
                      "Sport", "Vorerkrankungen", "Agentur", "Grund", "Geburtsland", "Beruf", "Raucher", "Kasse",
                      "Haarfarbe", "Schuhgröße", "Spitzname", "Ehename", "Rufname"]


@pytest.mark.parametrize("muster_", ["Geb.-Name\n{}", "Geb.-Name\t\t{}", "Geburtsnamen\t\t{}"])
@pytest.mark.parametrize("etikett", FORMULAR_ETIKETTEN)
def test_b9_feld_etikett_hinter_leerem_geb_name(muster_, etikett):
    text = muster_.format(etikett)
    funde = analysiere_text(text, ALLE, [], [])
    assert not [t for t in _stellen(funde, "namen") if etikett in t], _paare(funde)


@pytest.mark.parametrize("text, name", [
    # das Personen-Etikett "Name" mit leerem Feld: ein Feld-Etikett in der Zelle daneben ist kein Name
    ("Name\t\tKünstlername", None), ("Name\t\tGeburtsland", None), ("Name\t\tSport", None),
    ("Geb. Name\t\tVorerkrankungen", None), ("Name\t\tHaarfarbe", None),
    # Gegenproben: Namen bleiben Namen – auch Nachnamen, die zugleich Wörter sind
    ("Name\t\tQuarnstedt", "Quarnstedt"), ("Name\t\tGrund", "Grund"), ("Name\t\tWeber-Landgraf", "Weber-Landgraf"),
])
def test_b9_etikett_hinter_leerem_namensfeld(text, name):
    funde = analysiere_text(text, ALLE, [], [])
    namen_ = _stellen(funde, "namen")
    assert (name in namen_) if name else not namen_, _paare(funde)


@pytest.mark.parametrize("etikett", ["KÜNSTLERNAME", "ORDENSNAME", "DOKTORGRAD", "GRÖSSE", "HOBBYS", "SPORT",
                                     "VORERKRANKUNGEN", "AGENTUR", "GRUND", "GEBURTSLAND"])
def test_b9_feld_etikett_hinter_leerem_geb_name_versalien(etikett):
    funde = analysiere_text(f"GEB.-NAME\t\t{etikett}", ALLE, [], [])
    assert not [t for t in _stellen(funde, "namen") if etikett in t], _paare(funde)


@pytest.mark.parametrize("text", ["Geb.-Name\t\tGeburtsland\t\tPolen", "Geb.-Name\nGeburtsland\t\tPolen",
                                  "Geb.-Name\t\tSport\t\tTennis", "Geburtsnamen\t\tAgentur\t\tKöln-Mitte"])
def test_b9_feld_mit_wert_dahinter_ist_etikett(text):
    funde = analysiere_text(text, ALLE, [], [])
    assert not [f for f in funde if f["kategorie"] == "namen"], _paare(funde)


def test_b9_ende_zu_ende_ohne_weitergabe(tmp_path):
    aus = _lauf(tmp_path, {
        "antrag_zelle": ["Antrag auf Lebensversicherung", "Name\t\tWeber\t\tVorname\t\tAnna",
                         "Geb.-Name\t\tGeburtsland\t\tPolen", "Sport\t\tTennis\t\tGrund\t\tNeuabschluss"],
        "antrag_darunter": ["Antrag auf Unfallversicherung", "Name\t\tWeber, Anna", "Geb.-Name",
                            "Geburtsland\t\tPolen", "Agentur\t\tKöln-Mitte"],
        "zweites_dokument": ["Gesundheitsfragen", "Geburtsland: Türkei", "Sport: Fußball, Schwimmen",
                             "Grund der Änderung: Heirat", "Ihre Agentur: Köln-Mitte"]})
    for name in ("antrag_zelle", "antrag_darunter"):
        e, _, text = aus[name]
        assert "Geburtsland" in text, text
        assert not [f for f in e["funde"] if f["kategorie"] == "namen" and "Geburtsland" in f["text"]], e["funde"]
    assert "Geburtsland: Türkei" in aus["zweites_dokument"][2], aus["zweites_dokument"][2]


@pytest.mark.parametrize("text, wert", [
    # Gegenproben: der Geburtsname in der Zelle daneben bzw. darunter bleibt ein Name
    ("Geb.-Name\t\tQuarnstedt", "Quarnstedt"),
    ("GEB.-NAME\t\tQUARNSTEDT", "QUARNSTEDT"),
    ("Geb.-Name\nQuarnstedt", "Quarnstedt"),
    ("Geburtsnamen\t\tQuarnstedt", "Quarnstedt"),
    ("Geb.-Name\t\tQuarnstedt\t\tGeburtsdatum\t\t12.03.1980", "Quarnstedt"),
    ("Geb.-Name\t\tWeber-Landgraf", "Weber-Landgraf"),
])
def test_b9_gegenproben_geburtsname_in_zelle(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert wert in _stellen(funde, "namen"), _paare(funde)


# ======================================================================
# Befund 10 (mittel): „GEB.“ als Spaltenkopf einer Festbreiten-Liste
# ======================================================================
def test_b10_geb_spaltenkopf_macht_keine_person(tmp_path):
    aus = _lauf(tmp_path, {
        "bestandsliste": ["WESERBERGLAND RECHTSSCHUTZ AG   BLATT 1   DRUCK 23.04.25",
                          "BESTANDSLISTE MITVERSICHERTE PERSONEN",
                          "NAME, VORNAME          GEB.     STATUS   KLASSE",
                          "HAAS, FIETE            1962     AKTIV    A",
                          "HAAS, ANNA-LENA        1976     AKTIV    B",
                          "STATUS UND KLASSE GELTEN AB 01.01.2025"],
        "beitragsrechnung": ["BEITRAGSRECHNUNG", "VERTRAGSSTATUS: STATUS AKTIV", "TARIFKLASSE: KLASSE B"]},
        font="cour")
    e, _, text = aus["bestandsliste"]
    assert not [f for f in e["funde"] if f["kategorie"] == "namen" and "STATUS" in f["text"]], _paare(e["funde"])
    assert "STATUS UND KLASSE" in text, text
    assert "VERTRAGSSTATUS: STATUS AKTIV" in aus["beitragsrechnung"][2], aus["beitragsrechnung"][2]
    ersatz = {f["text"]: f["ersatz"] for f in e["funde"] if f["kategorie"] == "namen"}
    assert ersatz.get("HAAS, FIETE") == "[PERSON A]", ersatz


@pytest.mark.parametrize("wort", ["STATUS", "KLASSE", "KFZ", "HAUPTVERSICHERTER", "BERUF", "TARIF"])
@pytest.mark.parametrize("luecke", [" ", "        "])
def test_b10_b13_versalwort_hinter_geb(wort, luecke):
    text = f"WEBER, ANNA GEB.{luecke}{wort}\nHINWEIS: {wort} GILT FÜR DEN GESAMTEN VERTRAG"
    funde = analysiere_text(text, ALLE, [], [])
    assert not [t for t in _stellen(funde, "namen") if wort in t.split()], _paare(funde)


@pytest.mark.parametrize("text, wert", [
    ("WEBER, ANNA GEB.        QUARNSTEDT", "QUARNSTEDT"),          # Gegenprobe: Festbreite mit Namen davor
    ("WEBER, ANNA GEB. QUARNSTEDT    12.03.1980", "QUARNSTEDT"),
])
def test_b10_gegenproben_festbreite(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert wert in _stellen(funde, "namen"), _paare(funde)


# ======================================================================
# Befund 11 (mittel): das Etikett „Prüfnr.“ ist kein Name
# ======================================================================
@pytest.mark.parametrize("text, etikett", [
    ("Kreditkarte\nPrüfnr.: 739", "Prüfnr"),
    ("Kartenprüfnr.: 739", "Kartenprüfnr"),
    ("Prüfprotokoll\nPrüfnr.: 2024-0815\nPrüfer: Weber", "Prüfnr"),
    ("Prüfnr.: 4711\nDie Prüfnr. steht auf der Plakette.", "Prüfnr"),
    ("TÜV-Prüfnr.: 4711", "Prüfnr"),
])
def test_b11_pruefnr_ist_kein_name(text, etikett):
    funde = analysiere_text(text, ALLE, [], [])
    assert not [t for t in _stellen(funde, "namen") if etikett in t], _paare(funde)


def test_b11_wert_bleibt_geschwaerzt():
    funde = analysiere_text("Kreditkarte\nPrüfnr.: 739", ALLE, [], [])
    assert "739" in _stellen(funde, "kreditkarte"), _paare(funde)


# ======================================================================
# Befund 12 (niedrig): kein Fehlverdacht „möglicher Geburtsname“
# ======================================================================
@pytest.mark.parametrize("text", [
    "Geburtsname ist Pflichtangabe.",
    "Geburtsname des Versicherungsnehmers ist Pflichtangabe.",
    "Geburtsname des Kindes ist Pflichtangabe.",
    "Mit Geburtsname ist Folgendes gemeint: der Familienname bei Geburt.",
    "Geburtsname\nBeruf",
    "Geburtsname\nRaucher",
    "Geburtsname\nKasse",
    "Geburtsnamen\t\tBeruf",
    "Geb.-Name\nBeruf",
    "GEB.-NAME\t\tKASSE",
    "Geburtsname:\t\tAlt:",
    "Geburtsname:\t\tGröße:",
    "Geburtsname:\t\tGrund:",
    "Geburtsname, falls abweichend:\nAbweichender Halter:",
    "Geburtsname, falls abweichend:\nVersichert seit:",
])
def test_b12_kein_fehlverdacht(text):
    assert not _gruende(text), _gruende(text)


# ======================================================================
# Befund 13 (niedrig): mehrdeutige Geburtsnamen wandern nicht in fremde Stellen
# ======================================================================
def test_b13_deutsch_wird_nicht_weitergegeben(tmp_path):
    aus = _lauf(tmp_path, {"antrag": ["Antrag", "Versicherungsnehmerin: Anna Weber, geb. Deutsch",
                                      "Korrespondenzsprache: Deutsch"],
                           "bedingungen": ["Allgemeine Bedingungen", "Vertragssprache ist Deutsch."]})
    assert "Korrespondenzsprache: Deutsch" in aus["antrag"][2], aus["antrag"][2]
    assert "Vertragssprache ist Deutsch." in aus["bedingungen"][2], aus["bedingungen"][2]
    assert "geb. Deutsch" not in aus["antrag"][2], aus["antrag"][2]


def test_b13_ort_als_geburtsname_nur_an_seiner_stelle():
    text = "Anna Weber, geb. Mallorca\nReiseziel Mallorca, Abflug Köln"
    funde = analysiere_text(text, ALLE, [], [])
    aus, _ = _ausgabe_simuliert(text, funde)
    assert "Reiseziel Mallorca" in aus, aus


# ======================================================================
# Befund 2 (hoch): Herkunftsnamen hinter „geb.“ und hinter Geburtsnamen-Etiketten
# ======================================================================
HERKUNFTSNAMEN = ["Mainzer", "Landauer", "Lindauer", "Augsburger", "Leipziger", "Straßburger", "Wormser", "Pariser",
                  "Breslauer", "Danziger", "Posener", "Ansbacher", "Amberger", "Linzer", "Salzburger", "Krakauer",
                  "Warschauer", "Königsberger", "Lemberger", "Bromberger", "Frankfurter", "Hamburger"]
ORTSNAMEN = ["Israel", "Linz", "Greven", "Hilden", "Dessau", "Homburg", "Königsberg", "London", "Paris"]


@pytest.mark.parametrize("name", HERKUNFTSNAMEN)
def test_b2_herkunftsname_hinter_geb(name):
    for text, wert in ((f"Versicherte Person: Anna Weber, geb. {name}, geboren am 12.03.1980", name),
                       (f"WEBER, ANNA GEB. {name.upper()}    12.03.1980", name.upper()),
                       # so liest die Texterkennung dieselbe Festbreiten-Liste (Gegenprüfer: e2e_n4)
                       (f"WEBER,\t\tANNA GEB.\t\t{name.upper()}\t\t12.03.1980", name.upper()),
                       (f"Anna Weber geborene {name}", name),
                       (f"Frau Anna Weber (geb. {name})", name)):
        assert _geschwaerzt_oder_gemeldet(text, wert) == "weg", text


def test_b2_geb_vor_zellgrenze_selbstkontrolle():
    """Die Selbstkontrolle liest "geb. ⇥⇥ Name" hinter einem Platzhalter wie die Erkennung – nicht als Spaltenkopf und
    nicht hinter einem Wort, das kein Name ist."""
    platz = ["[PERSON A]", "[GEBURTSDATUM]"]
    for text, wort in (("BESTANDSLISTE\n[PERSON A] GEB.\t\tAMBERGER\t\t[GEBURTSDATUM]", "AMBERGER"),
                       # Kontroll-OCR einer geschwärzten Festbreiten-Liste: Zellgrenzen auf beiden Seiten, oder der
                       # geschwärzte Name davor fehlt ganz (die Platzhalter stehen in eigenen Zeilen)
                       ("BESTANDSLISTE\n[PERSON A]\t\tGEB.\t\tISRAEL\t\t[GEBURTSDATUM]", "ISRAEL"),
                       ("[PERSON A]\t\t[GEBURTSDATUM]\nBESTANDSLISTE\t\tLEBEN\nGEB.\nGEB.\t\tISRAEL", "ISRAEL")):
        gruende = _gruende(text, platzhalter=platz)
        assert [g for t, g in gruende if t == wort and "Geburtsname" in g], gruende
    for text in ("Name\t\tgeb.\t\tOrt\nAnna Weber\t\t12.03.1980\t\tLinz", "Klinikum Mitte, Geb.\t\tNord",
                 "Geb.\t\tNord", "GEB.\t\tSTATUS", "GEB.\t\tHAMBURG", "NAME, VORNAME\t\tGEB.\t\tKLASSE"):
        assert not [g for t, g in _gruende(text) if "Geburtsname" in g], _gruende(text)


@pytest.mark.parametrize("name", ORTSNAMEN)
def test_b2_ortsname_hinter_geb_wird_gemeldet(name):
    """Ein Ort hinter „Name geb.“ kann Geburtsname oder Geburtsort sein: bleibt er lesbar, meldet die Selbstkontrolle
    ihn (ae932bd: geschwärzt bzw. gemeldet; 9546ef1: still)."""
    for text, wert in ((f"Versicherungsnehmerin: Anna Weber geb. {name}, wohnhaft in Köln", name),
                       (f"WEBER, ANNA GEB. {name.upper()}    12.03.1980", name.upper())):
        assert _geschwaerzt_oder_gemeldet(text, wert) in ("weg", "VERDACHT"), text


@pytest.mark.parametrize("name", ["Mainzer", "Linz", "Israel", "Danziger", "Amberger", "Dessau"])
def test_b2_herkunftsname_hinter_geburtsnamen_etikett(name):
    for text, wert in ((f"Geb.-Name\t\t{name}", name), (f"GEB.-NAME\t\t{name.upper()}", name.upper()),
                       (f"Geburtsname, falls abweichend: {name}", name),
                       (f"Familienname (Geburtsname): Weber ({name})", name)):
        assert _geschwaerzt_oder_gemeldet(text, wert) == "weg", text


def test_b2_ende_zu_ende_herkunftsname(tmp_path):
    aus = _lauf(tmp_path, {"antrag": ["Antrag auf Krankenversicherung",
                                      "Versicherte Person: Anna Weber, geb. Mainzer",
                                      "Mitversicherte Person: Max Weber, geb. Danziger",
                                      "Wohnort: Mainz, Mainzer Straße 5"]})
    e, r, text = aus["antrag"]
    assert "Mainzer," not in text.replace("Mainzer Straße", "") and "Danziger" not in text, text
    ersatz = {f["text"]: f["ersatz"] for f in e["funde"] if f["kategorie"] == "namen"}
    assert ersatz.get("Mainzer") == ersatz.get("Anna Weber") is not None, ersatz


@pytest.mark.parametrize("text, wort", [
    # Gegenproben: Herkunftsbezeichnungen ohne Geburtsnamen-Bezug bleiben
    ("Als geborener Kölner kennt der Fahrer die Strecke. Der Kölner Ring ist gesperrt.", "Kölner"),
    ("Sie ist eine geborene Hamburgerin.", "Hamburgerin"),
    ("Anna Weber geb. Polen\nReiseziel: Polen", "Reiseziel: Polen"),
])
def test_b2_gegenproben(text, wort):
    funde = analysiere_text(text, ALLE, [], [])
    aus, _ = _ausgabe_simuliert(text, funde)
    assert wort in aus, aus


# ======================================================================
# Befund 3 (mittel): eVB-Aufzählungen
# ======================================================================
AUFZAEHLUNGEN = [
    ("eVB-Nummern:\n• K7H3M9P\n• R7T2W9K\n• B9C8D7E", ["K7H3M9P", "R7T2W9K", "B9C8D7E"]),
    ("Ihre eVB-Nummern:\n• K7H3M9P\n• R7T2W9K", ["K7H3M9P", "R7T2W9K"]),
    ("eVB-Nummern:\n1. K7H3M9P\n2. R7T2W9K", ["K7H3M9P", "R7T2W9K"]),
    ("eVB-Nummern:\n- K7H3M9P\n- R7T2W9K", ["K7H3M9P", "R7T2W9K"]),
    ("eVB-Nummern:\nPkw: K7H3M9P\nAnhänger: R7T2W9K", ["K7H3M9P", "R7T2W9K"]),
    ("anbei die eVB-Nummern für Ihre Fahrzeuge:\nPkw: K7H3M9P\nAnhänger: R7T2W9K\nWohnmobil: B9C8D7E",
     ["K7H3M9P", "R7T2W9K", "B9C8D7E"]),
    ("eVB-Nummern:\nFahrzeug 1: K7H3M9P\nFahrzeug 2: R7T2W9K", ["K7H3M9P", "R7T2W9K"]),
    ("Ihre eVB-Nummern:\nM-AB 123: K7H3M9P\nM-CD 456: R7T2W9K", ["K7H3M9P", "R7T2W9K"]),
    ("eVB-Nummern:\nK7H3M9P – VW Golf\nR7T2W9K – BMW 320d", ["K7H3M9P", "R7T2W9K"]),
    ("eVB-Nummern für Ihre Fahrzeuge:\nK7H3M9P (Pkw)\nR7T2W9K (Anhänger)", ["K7H3M9P", "R7T2W9K"]),
    ("eVB-Nummer(n):\n- K7H3M9P (Pkw)\n- R7T2W9K (Krad)", ["K7H3M9P", "R7T2W9K"]),
    ("Ihre eVB-Nummern lauten:\nK7H3M9P,\nR7T2W9K,\nB9C8D7E", ["K7H3M9P", "R7T2W9K", "B9C8D7E"]),
    ("Ihre eVB-Nummern lauten K7H3M9P (Pkw), R7T2W9K (Anhänger) und B9C8D7E (Wohnmobil).",
     ["K7H3M9P", "R7T2W9K", "B9C8D7E"]),
    ("eVB-Nummern: K7H3M9P (Golf), R7T2W9K (Polo)", ["K7H3M9P", "R7T2W9K"]),
    ("eVB-Nummern: K7H3M9P für den Golf und R7T2W9K für den Polo", ["K7H3M9P", "R7T2W9K"]),
    ("eVB für den Golf: K7H3M9P; für den Polo: R7T2W9K", ["K7H3M9P", "R7T2W9K"]),
    ("Die eVB-Nummer für den Golf lautet K7H3M9P, die für den Polo R7T2W9K.", ["K7H3M9P", "R7T2W9K"]),
    ("Die eVB-Nummer für den Golf lautet K7H3M9P, die für den Polo lautet R7T2W9K.", ["K7H3M9P", "R7T2W9K"]),
    ("eVB-Nummer für Fahrzeug 1: K7H3M9P, für Fahrzeug 2: R7T2W9K", ["K7H3M9P", "R7T2W9K"]),
    ("Transfertickets:\n• TT0815AB4711\n• TT4711CD0815", ["TT0815AB4711", "TT4711CD0815"]),
    ("Transfertickets:\n1. TT0815AB4711\n2. TT4711CD0815", ["TT0815AB4711", "TT4711CD0815"]),
    ("Transfertickets:\nM-AB 123: TT0815AB4711\nM-CD 456: TT4711CD0815", ["TT0815AB4711", "TT4711CD0815"]),
    ("Übersicht eVB\nVW Golf (M-AB 123): K7H3M9P\nBMW 320d (M-CD 456): R7T2W9K", ["K7H3M9P", "R7T2W9K"]),
    ("eVB-Nummern Ihres Fuhrparks\nM-AB 123\t\tVW Golf\t\tK7H3M9P\nM-CD 456\t\tBMW 320d\t\tR7T2W9K",
     ["K7H3M9P", "R7T2W9K"]),
]


@pytest.mark.parametrize("text, werte", AUFZAEHLUNGEN)
def test_b3_aufzaehlung(text, werte):
    funde = analysiere_text(text, ALLE, [], [])
    for wert in werte:
        assert wert in _an(funde), (wert, _paare(funde))
        assert _geschwaerzt_oder_gemeldet(text, wert) == "weg"
    for wert in werte:
        assert [t for t, g in _gruende(text) if wert in t], (wert, _gruende(text))


@pytest.mark.parametrize("text, wert", [
    # Gegenproben: hinter einer eVB-Nummer stehen andere Felder mit eigenen Werten
    ("eVB-Nummer: K7H3M9P\nTarif: KH2024A", "KH2024A"),
    ("eVB-Nummer: K7H3M9P\nKennzeichen: M-AB 123\nTyp: GOLF8TS", "GOLF8TS"),
    ("eVB-Nummer: K7H3M9P, Tarif KH2024A", "KH2024A"),
    ("eVB-Nummern:\n• K7H3M9P\n\nIhr Tarif: KH2024A", "KH2024A"),
])
def test_b3_gegenproben_andere_felder(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert wert not in _an(funde), _paare(funde)
    assert "K7H3M9P" in _an(funde), _paare(funde)


# ======================================================================
# Befund 4 (mittel): eVB in Briefsätzen
# ======================================================================
SAETZE = [
    ("Die eVB (Nr. K7H3M9P) ist sechs Monate gültig.", "K7H3M9P"),
    ("Die eVB (Nr.: K7H3M9P) gilt sechs Monate.", "K7H3M9P"),
    ("Die eVB (Nummer K7H3M9P) ist sechs Monate gültig.", "K7H3M9P"),
    ("Unter der eVB (Nr. K7H3M9P) können Sie zulassen.", "K7H3M9P"),
    ("Das Transferticket (Nr. TT0815AB4711) wurde an Ihren Vorversicherer übermittelt.", "TT0815AB4711"),
    ("Das Transferticket (ID TT0815AB4711) wurde übermittelt.", "TT0815AB4711"),
    ("Die Versicherungsbestätigung für Ihr Fahrzeug hat die Nummer K7H3M9P.", "K7H3M9P"),
    ("Die eVB für Ihr neues Fahrzeug trägt die Nummer K7H3M9P.", "K7H3M9P"),
    ("Ihre eVB hat die Nummer K7H3M9P.", "K7H3M9P"),
    ("Das Transferticket wurde unter der Nummer TT0815AB4711 angefordert.", "TT0815AB4711"),
    ("Wir haben die eVB für Ihren Neuwagen unter K7H3M9P erstellt.", "K7H3M9P"),
    ("Ihre eVB für den neuen Wagen erhalten Sie mit K7H3M9P.", "K7H3M9P"),
    ("Die eVB-Nummer für Ihr Fahrzeug mit dem Kennz. M-AB 123 lautet K7H3M9P.", "K7H3M9P"),
    ("Die eVB-Nummer für Ihr Fahrzeug mit dem amtl. Kennz. M-AB 123 lautet K7H3M9P.", "K7H3M9P"),
    ("Die eVB-Nummer für Ihren Pkw, amtl. Kennz. M-AB 123, lautet K7H3M9P.", "K7H3M9P"),
    ("Die eVB für Ihren Pkw, Kennzeichen: M-AB 123, lautet: K7H3M9P", "K7H3M9P"),
    ("Die eVB-Nummer für Ihren Anhänger Fa. Humbaur lautet K7H3M9P.", "K7H3M9P"),
    ("Ihre eVB-Nummer lautet:\n\nK7H3M9P\n\nBitte legen Sie diese vor.", "K7H3M9P"),
    ("Ihre eVB-Nummer für die Zulassung lautet\n\nK7H3M9P", "K7H3M9P"),
    ("Kreditkarte 4111 1111 1111 1111, die Prüfnr. auf der Rücks. ist 739", "739"),
]


@pytest.mark.parametrize("text, wert", SAETZE)
def test_b4_kennung_im_briefsatz(text, wert):
    assert _geschwaerzt_oder_gemeldet(text, wert) == "weg", _paare(analysiere_text(text, ALLE, [], []))
    assert [t for t, g in _gruende(text) if wert in t], _gruende(text)


@pytest.mark.parametrize("text", [
    # Gegenproben: kein Wert hinter „Nummer“/„unter“/„mit“
    "Die eVB-Nummer erhalten Sie unter 0800-1234567.",
    "Die eVB hat die Nummer erhalten, die Sie angefragt haben.",
    "Die eVB senden wir mit separater Post.",
    "Ihre eVB erhalten Sie unter Angabe Ihrer Kundennummer.",
])
def test_b4_gegenproben(text):
    assert not [f for f in kennungsformen.kennungen(text) if f.art in ("evb", "ticket")], text


# ======================================================================
# Befund 5 (mittel): Kartenprüfnummer hinter Kartendaten über mehrere Zeilen
# ======================================================================
KARTENDATEN = [
    "Hier meine Kartendaten:\nMastercard\n5555 5555 5555 4444\n11/26\n739\nViele Grüße",
    "Mastercard\n5555 5555 5555 4444\n11/26\n739",
    "Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\n739",
    "Visa 4111 1111 1111 1111\n12/27 739",
    "Visa 4111 1111 1111 1111 12/27\n739",
    "Visa\n4111 1111 1111 1111\n12/27\n739",
    "Visa\n4111 1111 1111 1111\ngültig bis 12/27\n739",
    "Kreditkarte: Visa\n4111 1111 1111 1111\n12/27\n739",
    "Kreditkarte: Mastercard\nNummer: 5555 5555 5555 4444\nAblauf: 11/26\nCode: 739",
    "Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\nCode: 739",
    "Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\nRückseite: 739",
    "Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\nZiffern hinten: 739",
    "Kreditkarte: Mastercard 5555 5555 5555 4444\nAblauf: 11/26\nRückseite: 739",
    "Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\nCSC: 739",
    "Kartennummer: 4111 1111 1111 1111, Ablauf 12/27, CSC 739",
    "Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\nSicherheitsziffer: 739",
    "Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\nKontrollziffer: 739",
    "Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\nPrüfz.: 739",
    "Kreditkarte: 4111 1111 1111 1111\nPrüfz.: 739",
    "Kreditkarte: Visa\nKartennummer: 4111 1111 1111 1111\nKontrollnummer: 739",
    "Mastercard 5555 5555 5555 4444 (11/26) 739",
    "Visa 4111111111111111 Ablauf 1227 Code 739",
    "Kreditkarte 4111 1111 1111 1111, 12/27, Code hinten 739",
    "Visa 4111 1111 1111 1111, die drei Zahlen hinten: 739",
    "Visa 4111 1111 1111 1111, die drei Ziffern auf der Rückseite lauten 739",
    "Kreditkarte: Visa\nKartennummer: 4111 1111 1111 1111\ndie 3-stellige Nummer auf der Rückseite: 739",
    "Sicherheitscode (Rückseite der Karte): 739",
    # so liest die Texterkennung eine Mail in Festbreitenschrift: Etikett und Wert in zwei Zellen
    "Kreditkarte:\t\tMastercard\nNummer: 5555 5555 5555 4444\nAblauf:\t\t11/26\nCode:\t\t739",
]


@pytest.mark.parametrize("text", KARTENDATEN)
def test_b5_kartenpruefnummer_ueber_zeilen(text):
    funde = analysiere_text(text, ALLE, [], [])
    assert "739" in _stellen(funde, "kreditkarte"), _paare(funde)
    assert [t for t, g in _gruende(text, platzhalter=["[KREDITKARTE]"]) if "739" in t], _gruende(text)


@pytest.mark.parametrize("text, zahl", [
    # Gegenproben: drei Ziffern hinter Kartendaten, die keine Prüfnummer sind
    ("Visa 4111 1111 1111 1111\n12/27\n250 EUR Limit", "250"),
    ("Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\nFiliale: 123", "123"),
    ("Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\nSeite 2 von 739", "739"),
    ("Kartennummer: 4111 1111 1111 1111\nGültig bis: 12/27\nKundennummer: 739", "739"),
    ("Visa 4111 1111 1111 1111\nBestellung 739 vom 12.03.2025", "739"),
    ("Kartennummer: 4111 1111 1111 1111\nGültig bis:\t\t12/27\nZimmer:\t\t739", "739"),
    ("Kartennummer: 4111 1111 1111 1111\nGültig bis:\t\t12/27\nKunde:\t\t739", "739"),
])
def test_b5_gegenproben(text, zahl):
    funde = analysiere_text(text, ALLE, [], [])
    assert ("kreditkarte", zahl) not in _paare(funde), _paare(funde)


# ======================================================================
# Befund 1 (hoch): Kammfeld
# ======================================================================
def _kamm(seite, x, y, zeichen, breite=16, abstand=4):
    for i, z in enumerate(zeichen):
        r = fitz.Rect(x + i * (breite + abstand), y - 13, x + i * (breite + abstand) + breite, y + 4)
        seite.draw_rect(r, color=(0, 0, 0), width=0.6)
        if z.strip():
            seite.insert_text((r.x0 + 4.5, y), z, fontsize=11, fontname="cour")


def test_b1_evb_kammfeld_auf_der_textebene(tmp_path):
    """eVB-Nummer im Kammfeld eines Zulassungsantrags (Kästchen 16 pt, Abstand 4 pt) wie der CVC-Kammfeldtest."""
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    y = 80
    for z in ["Antrag auf Zulassung eines Fahrzeugs", "Halter: Max Mustermann", "Kennzeichen: M-AB 123"]:
        s.insert_text((60, y), z, fontsize=11, fontname="helv")
        y += 18
    y += 10
    s.insert_text((60, y), "eVB-Nummer:", fontsize=11, fontname="helv")
    _kamm(s, 200, y, "K7H3M9P")
    pdf = tmp_path / "kamm.pdf"
    doc.save(pdf)
    doc.close()
    a = analysiere_pdf(pdf, ALLE, [], [], ocr=OcrAttrappe())
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / "aus")
    text = _ausgabe_text(e["ausgabe"])
    assert not re.search(r"K\s*7\s*H\s*3\s*M\s*9\s*P", text), text
    assert "eVB-Nummer" in text, text


def test_b1_evb_kammfeld_wird_nicht_je_zeichen_weitergegeben(tmp_path):
    """Ein Kammfeld über Tabellenzellen ist eine Stelle, kein Satz einzelner Zeichen: "7", "K" und "3" bleiben in
    Seitenzahlen und Wörtern stehen – im selben Dokument und in einem zweiten Dokument desselben Laufs."""
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    s.insert_text((60, 80), "Antrag auf Zulassung eines Fahrzeugs", fontsize=11, fontname="helv")
    s.insert_text((60, 110), "eVB-Nummer:", fontsize=11, fontname="helv")
    _kamm(s, 200, 110, "K7H3M9P")
    for i, z in enumerate(["Seite 7 von 9", "Haus 3, Block K, Raum P", "Typ M"]):
        s.insert_text((60, 150 + 18 * i), z, fontsize=11, fontname="helv")
    pdf = tmp_path / "kamm.pdf"
    doc.save(pdf)
    doc.close()
    zweit = _text_pdf(tmp_path / "rechnung.pdf", ["Rechnung 7 Positionen, Kunde K, Preis 3 Euro"])
    a = analysiere_pdf(pdf, ALLE, [], [], ocr=OcrAttrappe())
    b = analysiere_pdf(zweit, ALLE, [], [], ocr=OcrAttrappe())
    analyse.weitergabe_anwenden([a, b])
    texte = []
    for name, p, erg in (("a", pdf, a), ("b", zweit, b)):
        e = schwaerze_pdf(p, erg["funde"], modell=erg["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / name)
        texte.append(_ausgabe_text(e["ausgabe"]))
    assert not re.search(r"K\s*7\s*H\s*3\s*M\s*9\s*P", texte[0]), texte[0]
    for teil in ("Seite 7 von 9", "Haus 3, Block K, Raum P", "Typ M"):
        assert teil in texte[0], texte[0]
    assert "Rechnung 7 Positionen, Kunde K, Preis 3 Euro" in texte[1], texte[1]


@pytest.mark.parametrize("text", ["eVB-Nummer: K 7 H 3 M 9 P", "eVB: K | 7 | H | 3 | M | 9 | P",
                                  "eVB-Nummer:\t\tK\t\t7\t\tH\t\t3\t\tM\t\t9\t\tP"])
def test_b1_evb_kammfeld_form(text):
    funde = analysiere_text(text, ALLE, [], [])
    aus, _ = _ausgabe_simuliert(text, funde)
    assert not re.search(r"K\W*7\W*H\W*3\W*M\W*9\W*P", aus), (aus, _paare(funde))


def _scan_mit_kammfeld(pfad, etikett, zeichen, unter=False, dpi=150):
    """Scan-Seite: Kartendaten, ein Kennungs-Etikett und dahinter (bzw. darunter) ein Kammfeld mit Zeichen. Liefert
    (pdf, OCR-Wörter der gedruckten Zeilen) – das Kammfeld liest die „Texterkennung“ wie Tesseract als „[s]“."""
    vorlage = fitz.open()
    s = vorlage.new_page(width=595, height=842)
    y = 80
    for z in ["Zahlung per Kreditkarte", "Kreditkarte: Mastercard", "Gültig bis: 11/26"]:
        s.insert_text((60, y), z, fontsize=11, fontname="helv")
        y += 18
    y += 10
    s.insert_text((60, y), etikett, fontsize=11, fontname="helv")
    woerter = [tuple(w[:5]) for w in s.get_text("words")]
    x = 60 if unter else 60 + fitz.get_text_length(etikett, fontname="helv", fontsize=11) + 30
    ky = y + 26 if unter else y
    _kamm(s, x, ky, zeichen)
    woerter.append((x + 1, ky - 12, x + 15, ky + 3, "[s]"))
    pix = s.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    vorlage.close()
    doc.save(pfad)
    doc.close()
    return pfad, woerter, fitz.Rect(x, ky - 13, x + 20 * len(zeichen), ky + 4)


@pytest.mark.parametrize("etikett, zeichen, unter", [
    ("Kartenprüfnummer (CVC):", "739", False),
    ("Kartenprüfnummer (CID):", "7391", False),
    ("Versicherungsbestätigung (eVB-Nummer):", "K7H3M9P", False),
    ("eVB-Nummer (7-stellig)", "K7H3M9P", True),
])
def test_b1_kammfeld_auf_scan_wird_gemeldet(tmp_path, etikett, zeichen, unter):
    """Auf dem Scan liest die Texterkennung das Kammfeld nicht: die Selbstkontrolle meldet die Schrift hinter (bzw.
    unter) dem Kennungs-Etikett – die Ausgabe wird _PRUEFEN statt fertig."""
    pdf, woerter, kamm = _scan_mit_kammfeld(tmp_path / "k.pdf", etikett, zeichen, unter)
    verdacht = restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"})
    treffer = [v for v in verdacht if any(fitz.Rect(r).intersects(kamm) for r in v.rechtecke or [])]
    assert treffer, verdacht


def test_b1_leere_zeile_hinter_etikett_ohne_verdacht(tmp_path):
    """Gegenprobe: hinter dem Etikett steht nichts (kein Kammfeld, keine Schrift) – kein Verdacht."""
    vorlage = fitz.open()
    s = vorlage.new_page(width=595, height=842)
    for y, t in ((80, "Zahlung per Kreditkarte"), (98, "Kreditkarte: Mastercard"), (126, "Kartenprüfnummer (CVC):"),
                 (170, "Bitte vollständig ausfüllen.")):
        s.insert_text((60, y), t, fontsize=11, fontname="helv")
    woerter = [tuple(w[:5]) for w in s.get_text("words")]
    pix = s.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    vorlage.close()
    doc.save(tmp_path / "leer.pdf")
    doc.close()
    verdacht = restrisiko_pruefen(tmp_path / "leer.pdf", ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"})
    assert not verdacht, verdacht


@braucht_ocr
def test_b1_kammfeld_scan_ende_zu_ende(tmp_path):
    """Ende zu Ende mit der echten Texterkennung (Fall der ersten Gegenprüfung): die Ziffern im Kammfeld liest
    Tesseract nicht; die Ausgabe ist dann _PRUEFEN mit Verdacht am Kammfeld, nicht „fertig“."""
    from anonymisierer.ocr import OcrDienst
    vorlage = fitz.open()
    s = vorlage.new_page(width=595, height=842)
    y = 80
    for z in ["Zahlung per Kreditkarte", "Karteninhaber: Max Mustermann", "Kreditkarte: Mastercard",
              "Kartennummer: 5555 5555 5555 4444", "Gültig bis: 11/26"]:
        s.insert_text((60, y), z, fontsize=11, fontname="helv")
        y += 18
    y += 10
    s.insert_text((60, y), "Kartenprüfnummer (CVC):", fontsize=11, fontname="helv")
    _kamm(s, 200, y, "739")
    pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    vorlage.close()
    pdf = tmp_path / "scan.pdf"
    doc.save(pdf)
    doc.close()
    with OcrDienst(prozesse=1) as dienst:
        a = analysiere_pdf(pdf, ALLE, [], [], ocr=dienst)
        e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=dienst, ziel_ordner=tmp_path / "aus")
    kamm = fitz.Rect(200, y - 13, 260, y + 4)
    gefunden = "739" in "".join(st["text"].replace(" ", "") for f in a["funde"] for st in f["stellen"])
    gemeldet = [v for v in e["verdacht"] if any(fitz.Rect(r).intersects(kamm) for r in v.rechtecke or [])]
    assert gefunden or (e["status"] == "pruefen" and gemeldet), (a["funde"], e["verdacht"], e["status"])


# ======================================================================
# Befund 6 (niedrig): seltenere Schreibweisen
# ======================================================================
@pytest.mark.parametrize("text, wert", [
    ("Anna Weber gcb. Quarnstedt", "Quarnstedt"),
    ("Anna Weber qeb. Quarnstedt", "Quarnstedt"),
    ("Ihre eVB-Nummcr: K7H3M9P", "K7H3M9P"),
    ("Geburtsnamen: Quarnstedt, Ellerbrok", "Ellerbrok"),
    ("Ihr Mädchenname lautet Quarnstedt.", "Quarnstedt"),
    ("Mädchenname: Quarnstedt", "Quarnstedt"),
    ("Geburtsn.: Quarnstedt", "Quarnstedt"),
    ("Name vor der Ehe: Quarnstedt", "Quarnstedt"),
    ("Familienname vor der Eheschließung: Quarnstedt", "Quarnstedt"),
    ("Kreditkarte: 4111 1111 1111 1111\nCVC: [7][3][9]", "7"),
    # OCR-Verleser der Etiketten (Gegenprüfer: faelle_ocr1)
    ("Name: Weber, Anna\nGcburtsname: Quarnstedt", "Quarnstedt"),
    ("Name: Weber, Anna\nGeburlsname: Quarnstedt", "Quarnstedt"),
    ("Name: Weber, Anna\nGeburtsnamc: Quarnstedt", "Quarnstedt"),
    ("Kreditkarte: 4111 1111 1111 1111\nCVG: 739", "739"),
    ("Kreditkarte: 4111 1111 1111 1111\nCV C: 739", "739"),
    ("Kreditkarte: 4111 1111 1111 1111\nKartenprüfnummcr: 739", "739"),
    # mehrere Namen hinter einem Etikett in der Mehrzahl
    ("Geburtsnamen der Eltern: Quarnstedt und Ellerbrok", "Ellerbrok"),
    ("Mädchennamen: Quarnstedt / Ellerbrok", "Ellerbrok"),
])
def test_b6_seltene_schreibweisen(text, wert):
    assert _geschwaerzt_oder_gemeldet(text, wert) in ("weg", "VERDACHT"), _paare(analysiere_text(text, ALLE, [], []))


@pytest.mark.parametrize("text, bleibt", [
    ("Die CVG-Linie 12 fährt ab 7:39 Uhr.", ["CVG-Linie 12", "7:39"]),
    ("Geburtsnamen: Quarnstedt, Status: ledig", ["Status: ledig"]),
    ("Geburtsnamen: Quarnstedt, Hamburg", ["Hamburg"]),
    ("Den Mädchennamen bitte angeben.", ["Den Mädchennamen bitte angeben."]),
    ("Mädchenname ist Pflichtangabe.", ["Mädchenname ist Pflichtangabe."]),
    ("Name vor der Ehe:\nGeburtsdatum: 01.01.1980", ["Name vor der Ehe:", "Geburtsdatum:"]),
    ("Familienname vor der Eheschließung: siehe oben", ["siehe oben"]),
    ("Ihre eVB-Nummcr erhalten Sie per E-Mail.", ["Ihre eVB-Nummcr erhalten Sie per E-Mail."]),
    ("Name: Weber, Anna\nGeburtsnamc: Quarnstedt", ["Geburtsnamc:"]),
])
def test_b6_gegenproben(text, bleibt):
    """Die neuen Schreibweisen schwärzen nur den Namen bzw. die Nummer – nicht das Etikett, nicht das nächste Feld,
    keine Erläuterung und keinen Ort, der kein Name ist."""
    aus, _ = _ausgabe_simuliert(text, analysiere_text(text, ALLE, [], []))
    for teil in bleibt:
        assert teil in aus, aus


@pytest.mark.parametrize("zeilen, geschwaerzt", [
    # Kartentabelle ohne Kartenangabe im Kopf: die Kartendaten stehen in den Zellen (Gegenprüfer: e2e_n2)
    (["Zahlungsdaten Reiseversicherung", "Karte\t\tNummer\t\tSicherheitscode",
      "Visa\t\t4111 1111 1111 1111\t\t739", "Mastercard\t\t5555 5555 5555 4444\t\t4821"], False),
    (["Zahlungsart\t\tKarte\t\tPrüfnummer", "Kreditkarte\t\tVisa\t\t739"], False),
    (["Karteninhaber\t\tNummer\t\tPrüfnummer", "Max Mustermann\t\t4111 1111 1111 1111\t\t739"], True),
    (["Versicherungsnehmer\t\tKarte\t\tPrüfnummer", "Max Mustermann\t\tVisa\t\t739"], True),
])
def test_b6_kartentabelle_ohne_kartennummer_im_kopf(tmp_path, zeilen, geschwaerzt):
    """Ist eine Tabelle als solche erkannt (Personen-Etikett im Kopf), wird die Prüfnummer geschwärzt; sonst meldet sie
    die Selbstkontrolle (die Spalte unter "Sicherheitscode" über Kartendaten)."""
    aus = _lauf(tmp_path, {"karte": zeilen})
    e, r, text = aus["karte"]
    if geschwaerzt:
        assert "739" not in text, text
    else:
        assert "739" not in text or (r["status"] == "pruefen" and [v for v in r["verdacht"] if "739" in v.text]), \
            (text, r["verdacht"])


def test_b6_pruefnummer_tabelle_ohne_kartendaten(tmp_path):
    """Gegenprobe: eine Prüfnummer-Spalte ohne Kartendaten ist keine Kartenprüfnummer (TÜV-Prüfnummer bleibt
    Vertragsnummer wie bisher, keine Kreditkarte)."""
    aus = _lauf(tmp_path, {"kfz": ["Versicherungsnehmer\t\tFahrzeug\t\tPrüfnummer",
                                   "Max Mustermann\t\tVW Golf\t\t4711"]})
    e, r, text = aus["kfz"]
    assert not [f for f in e["funde"] if f["kategorie"] == "kreditkarte"], e["funde"]


def test_b6_kammfeld_mit_spaltentrennern(tmp_path):
    """Kammfeld auf der Textebene, dessen Zeichen weit auseinander stehen (die Textebene trennt sie wie Zellen)."""
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    s.insert_text((60, 100), "Antrag auf Kindergeld", fontsize=11, fontname="helv")
    for zi, (etikett, wort) in enumerate((("Familienname:", "WEBER"), ("Geburtsname:", "QUARNSTEDT"))):
        y = 130 + 26 * zi
        s.insert_text((60, y), etikett, fontsize=11, fontname="helv")
        for i, b in enumerate(wort):
            r = fitz.Rect(170 + i * 30, y - 13, 184 + i * 30, y + 4)
            s.draw_rect(r, color=(0, 0, 0), width=0.6)
            s.insert_text((r.x0 + 3.5, y), b, fontsize=11, fontname="cour")
    pdf = tmp_path / "kamm.pdf"
    doc.save(pdf)
    doc.close()
    a = analysiere_pdf(pdf, ALLE, [], [], ocr=OcrAttrappe())
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / "aus")
    text = re.sub(r"\s+", "", _ausgabe_text(e["ausgabe"]))
    assert "QUARNSTEDT" not in text and "WEBER" not in text, text


def _zellen_pdf(pfad, zeilen):
    """Text-PDF mit Zellen an festen x-Lagen: zeilen = [(y, [(x, text), …]), …]."""
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    for y, zellen in zeilen:
        for x, t in zellen:
            s.insert_text((x, y), t, fontsize=11, fontname="helv")
    doc.save(pfad)
    doc.close()
    return pfad


def test_b6_kammfeld_spaltentrenner_gegenproben(tmp_path):
    """Tabellenzeilen mit je einem Zeichen in Spalten sind kein Kammfeld: verschiedene Spaltenbreiten ("Anzahl" über
    Spalten 1, 2, 3) und Ziffern unter einem Personen-Etikett ("Versicherte Person ⇥⇥ 1 ⇥⇥ 2 ⇥⇥ 3", gleiche Breite)."""
    pdf = _zellen_pdf(tmp_path / "tabelle.pdf", [
        (100, [(60, "Tarifübersicht")]),
        (130, [(60, "Familienname:"), (190, "A"), (260, "B"), (300, "C"), (390, "D")]),
        (160, [(60, "Versicherte Person"), (190, "1"), (230, "2"), (270, "3"), (310, "4")]),
    ])
    a = analysiere_pdf(pdf, ALLE, [], [], ocr=OcrAttrappe())
    kamm = [f for f in a["funde"] if any(q.startswith("struktur.kammfeld") for q in f.get("quellen", []))]
    assert not kamm, kamm
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / "aus")
    text = re.sub(r"\s+", "", _ausgabe_text(e["ausgabe"]))
    assert "1234" in text and "Familienname:" in text, text
