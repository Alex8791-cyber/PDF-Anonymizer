"""Gegenprüfung Runde 4c: Etikett + Wert verallgemeinert – eVB-Nummer, Transferticket, Kartenprüfnummer (CVC/CVV) und
Geburtsname.

Die Erkennung (muster.py, namen.py, detektoren/struktur*.py) und die Selbstkontrolle (restrisiko.py) lesen hinter dem
Etikett dieselbe Regel (anonymisierer/kennungsformen.py): ein Wert der passenden Form direkt hinter dem Etikett oder
hinter Zwischenwörtern desselben Satzes (auch groß geschrieben, Klammern, Abkürzungen mit Punkt, ein Zeilenumbruch)
bis zu einer Ankündigung (":", "lautet", "ist", Zellgrenze); Abbruch am Satzende, an einem anderen Etikett und nach
einer Höchstzahl von Wörtern; der Wert ist kein Wort, kein Datum, kein Betrag, keine Einheit.

A  Regression: hinter Etiketten mit eigener Wertform gilt die eigene Form ZUSÄTZLICH zum allgemeinen Kennungsweg –
   was a88d8da hinter "Versicherungsbestätigung Nr.", "VB-Nr.", "eVB-Nr.", "Transferticket-Nr." usw. schwärzte, wird
   weiter geschwärzt.
B  Stille Lecks: Zwischenwörter, Etikett-Varianten (Zusammensetzungen, Abkürzungen, Versalien, Mehrzahl), Wert in der
   Nachbarzelle, Kammfeld je Ziffer, zweizeiliger Spaltenkopf, Geburtsname hinter "Geburtsname, falls abweichend:".
C  Über-Schwärzung: ein Feld-Etikett ist nie ein Geburtsname; hinter "geb." zählen nur namenartige Wörter (kein
   Funktionswort, Ort, Land, keine Abkürzung).
D  Niedrig: seltene Schreibweisen, Fehlverdacht der allgemeinen Etikett-Regel, Prüfnummern anderer Gegenstände,
   Weitergabe kurzer Kartennummern, Laufzeit der Spaltenprüfung.
Alle Werte sind erfunden."""

import re

import pytest

import pymupdf as fitz

from anonymisierer import analyse, kennungsformen, muster
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.restrisiko import pruefe_text, restrisiko_pruefen
from anonymisierer.schwaerzung import schwaerze_pdf
from test_kennungen_makler import OcrAttrappe, _ocr_dok, _paare, _stellen, _tabellen_pdf, _text_pdf

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


def _an(funde) -> set:
    """Texte aller angehakten Stellen (jede Kategorie)."""
    return {st["text"] for f in funde for st in f["stellen"] if st.get("an", True)}


def _gemeldet(text, wert, **kw) -> bool:
    return any(wert in v.text for v in pruefe_text(text, **kw))


def _gruende(text, **kw) -> list:
    return [(v.text, v.grund) for v in pruefe_text(text, **kw)]


def _ausgabe_text(pfad) -> str:
    with fitz.open(pfad) as doc:
        return "\n".join(s.get_text() for s in doc)


def _schwaerzen(tmp_path, zeilen, name="dok.pdf"):
    pdf = _text_pdf(tmp_path / name, zeilen)
    a = analysiere_pdf(pdf, ALLE, [], [], ocr=OcrAttrappe())
    assert a["fehler"] is None
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / f"aus_{name}")
    assert e["fehler"] is None
    return a, e, _ausgabe_text(e["ausgabe"])


# ======================================================================
# A  Regression: der allgemeine Kennungsweg bleibt hinter Etiketten mit eigener Wertform
# ======================================================================
REGRESSION = [
    ("Versicherungsbestätigung Nr. 123/24", "123/24"),
    ("Versicherungsbestätigung Nr.: HR-4711-B", "HR-4711-B"),
    ("Versicherungsbestätigung Nr.: KH-123-AB", "KH-123-AB"),
    ("Versicherungsbestätigung Nr. 12345678", "12345678"),
    ("Versicherungsbestätigungsnummer: 2024-0815-12", "2024-0815-12"),
    ("Versicherungsbestätigungs-Nr.: 4711/2024", "4711/2024"),
    ("VB-Nr. 12345678", "12345678"),
    ("eVB-Nr. 471108", "471108"),
    ("eVB-Nr. K7H-3M9P", "K7H-3M9P"),
    ("Transferticket-Nr. 1234567", "1234567"),
    ("Transferticket-Nr.: TT-12345", "TT-12345"),
    ("Kartenprüfnummer: 12345", "12345"),
    ("Kartenprüfnummer 4711-0815", "4711-0815"),             # nie nur "4711" (der Rest bliebe lesbar)
    ("Versicherungsbestätigung Nr.\nHR-4711-B", "HR-4711-B"),  # Wert am Anfang der nächsten Zeile
    ("Bitte beachten Sie die Versicherungsbestätigung Nr.\nHR-4711-B vom Mai", "HR-4711-B"),
]


@pytest.mark.parametrize("text, wert", REGRESSION)
def test_a_allgemeiner_kennungsweg_bleibt(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert wert in _an(funde), _paare(funde)


@pytest.mark.parametrize("text, wert", REGRESSION)
def test_a_allgemeiner_kennungsweg_auf_ocr_text(text, wert):
    funde = analyse._analysiere_dokument(_ocr_dok(text.split("\n")), ALLE, [], [])
    assert wert in _an(funde), _paare(funde)


def test_a_spalte_mit_transferticket_nr(tmp_path):
    """Spaltenkopf "Transferticket-Nr.": auch Werte, die nicht die Form eines Transfertickets haben, aber die einer
    Kennung ("TT-123", "1234567"), bleiben geschwärzt (a88d8da: beide geschwärzt)."""
    pdf = _tabellen_pdf(tmp_path / "tt.pdf", ["Kennzeichen", "Transferticket-Nr.", "Vertrag"],
                        [["M-AB 123", "TT-123", "KH-0815"], ["M-CD 456", "1234567", "KH-0816"]])
    e = analysiere_pdf(pdf, ALLE, [], [])
    assert {"TT-123", "1234567"} <= _an(e["funde"]), _paare(e["funde"])


def test_a_ende_zu_ende_versicherungsbestaetigung(tmp_path):
    """"Versicherungsbestätigung Nr. …" ist auch ein Dokumenttyp (für Vermieter, Arbeitgeber): die Nummer wird
    geschwärzt, die Ausgabe ist ohne Verdacht fertig."""
    _, e, text = _schwaerzen(tmp_path, ["Versicherungsbestätigung zur Vorlage beim Arbeitgeber",
                                        "Versicherungsbestätigung Nr. 123/24",
                                        "Versicherungsbestätigung Nr.: HR-4711-B",
                                        "Hiermit bestätigen wir den Versicherungsschutz."])
    assert "123/24" not in text and "HR-4711-B" not in text, text
    assert not [v for v in e["verdacht"] if "123/24" in v.text or "HR-4711" in v.text], e["verdacht"]


# ======================================================================
# B  Stille Lecks
# ======================================================================
# --- B1: eVB und Transferticket hinter Zwischenwörtern desselben Satzes
ZWISCHEN = [
    ("Die eVB-Nummer Ihres neuen Fahrzeugs lautet: K7H3M9P", "K7H3M9P"),            # groß geschriebenes "Ihres"
    ("Die eVB-Nummer Ihres neuen Pkw lautet K7H3M9P.", "K7H3M9P"),
    ("Das Transferticket Ihres Vorversicherers lautet TTABCDEFGH12XY.", "TTABCDEFGH12XY"),
    ("Ihre elektronische Versicherungsbestätigung (eVB) für die Zulassung: B9C8D7E", "B9C8D7E"),   # Klammer
    ("Die elektronische Versicherungsbestätigung (eVB) für Ihr Fahrzeug lautet K7H3M9P.", "K7H3M9P"),
    ("Ihre eVB-Nummer für die Zulassung Ihres Pkw (Kennzeichen M-AB 123) lautet: X4Y8Z2Q", "X4Y8Z2Q"),
    ("Die eVB-Nummer für das Fahrzeug mit dem amtl. Kennzeichen HH-AB 123 lautet: K7H3M9P", "K7H3M9P"),  # "amtl."
    ("Ihre Versicherungsbestätigung (eVB-Nummer) für die Zulassung des Fahrzeugs lautet: K7H3M9P", "K7H3M9P"),
    ("Die eVB-Nummer für Ihr neues\nFahrzeug lautet K7H3M9P.", "K7H3M9P"),          # Zeilenumbruch im Satz
    ("wir haben eingedeckt. Die eVB-Nummer für Ihr neues\nFahrzeug lautet K7H3M9P. Bitte legen Sie sie vor.",
     "K7H3M9P"),
    ("eVB-Nummer für die Zulassung\t\tK7H3M9P", "K7H3M9P"),                       # Zelle ohne Doppelpunkt
    ("Versicherungsbestätigung (eVB)\t\tK7H3M9P", "K7H3M9P"),
    ("Bitte teilen Sie uns die eVB-Nr. Ihres neuen Versicherers mit: K7H3M9P", "K7H3M9P"),
    ("Ihre eVB-Nummer für das Kfz. M-AB 123 lautet K7H3M9P.", "K7H3M9P"),
    ("Ihre eVB-Nummer für das Fzg. M-AB 123: K7H3M9P", "K7H3M9P"),
    ("eVB-Nummer gem. Ihrer Anfrage vom 12.03.2025: K7H3M9P", "K7H3M9P"),
    ("eVB-Nummer zum Vertrag 0815/4711: K7H3M9P", "K7H3M9P"),
    ("eVB-Nummer (Versicherungsbestätigung für die Zulassungsstelle): K7H3M9P", "K7H3M9P"),
    ("eVB-Nummer (bitte bei der Zulassungsstelle vorlegen): K7H3M9P", "K7H3M9P"),
    ("eVB-Nr. lt. Zulassungsstelle: K7H3M9P", "K7H3M9P"),
    ("Die eVB-Nummer für Ihren Golf (Erstzulassung 2019) lautet K7H3M9P.", "K7H3M9P"),
    ("eVB-Nummer für Kennzeichen M-AB 123 und Fahrzeug-Ident-Nr. WVWZZZ1KZAW123456: K7H3M9P", "K7H3M9P"),
    ("Transferticket für Ihren Vertrag (SF 12): TTABCDEFGH12XY", "TTABCDEFGH12XY"),
    # ein Wort der Wertform direkt hinter dem Etikett ist ein Zwischenwort, keine Kennung
    ("TRANSFERTICKET ANGEFORDERT, NUMMER: TT0815AB4711", "TT0815AB4711"),
    ("EVB-NUMMER ANGEBEN: K7H3M9P", "K7H3M9P"),
]


@pytest.mark.parametrize("text, wert", ZWISCHEN)
def test_b1_kennung_hinter_zwischenwoertern(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert ("vertrag", wert) in _paare(funde), _paare(funde)
    assert _gemeldet(text, wert), _gruende(text)


@pytest.mark.parametrize("text", [
    # Satzende zwischen Etikett und Wert
    "Die eVB-Nummer ist bei Ihrer Zulassungsstelle hinterlegt. Ihr Servicecode lautet: KFZ2025",
    "Wir erstellen die eVB. Das Kennwort für das Portal lautet K7H3M9P.",
    # ein anderes Etikett übernimmt den Doppelpunkt
    "Die eVB senden wir Ihnen zu, Ihre Kundennummer: KD47110",
    # zu viele Wörter
    "Die eVB-Nummer wird Ihnen nach der Prüfung aller eingereichten Unterlagen durch unsere Abteilung in den "
    "nächsten Tagen per Post zugesandt, Zeichen: AB12CD3",
    # ein Wort, ein Datum, ein Betrag
    "Die eVB-Nummer für die Zulassung lautet: ERTEILT",
    "Die eVB für Ihr Fahrzeug ist: 12.03.2025",
    "Das Transferticket für den Wechsel lautet: 1.250,00 EUR",
])
def test_b1_zwischenwoerter_gegenproben(text):
    """Keine eVB-Nummer und kein Transferticket (andere Regeln dürfen den Wert als Kennung melden)."""
    assert not [v for v in pruefe_text(text) if "eVB" in v.grund or "Transferticket" in v.grund], _gruende(text)
    assert not [w for w in _evb_ticket(text)], _evb_ticket(text)


def _evb_ticket(text) -> list:
    """Werte, die die gemeinsame Regel (kennungsformen) als eVB-Nummer oder Transferticket liest."""
    return [text[f.start:f.ende] for f in kennungsformen.kennungen(text) if f.art in ("evb", "ticket")]


# --- B2: Kartenprüfnummer – Etikett-Varianten, Nachbarzelle, Kammfeld, Zwischenwörter über einen Zeilenumbruch
KARTE = "Kreditkarte: 5555 5555 5555 4444\n"
CVC_LECKS = [
    ("Kreditkartenprüfnummer: 739", "739"),
    ("Kreditkarten-Prüfnummer: 739", "739"),
    ("KREDITKARTENPRÜFNUMMER: 739", "739"),
    ("Kartenprüfnr.: 739", "739"),
    (KARTE + "Prüfnr.: 739", "739"),
    ("Prüfnr. (Kartenrückseite): 739", "739"),
    ("Kreditkartenprüfnummer\t\t739", "739"),                         # Wert in der Nachbarzelle
    (KARTE + "Sicherheitscode (3 Ziffern): 739", "739"),
    ("Kreditkarte: American Express\nKartennummer: 3782 822463 10005\nCID: 7391", "7391"),
    ("CVC: 7 3 9", "7 3 9"),                                          # Kammfeld: Kästchen je Ziffer
    ("Die CVC auf der\nRückseite ist 739.", "739"),                   # Zwischenwörter über den Zeilenumbruch
    ("Hallo, anbei meine Kreditkartendaten. Die CVC auf der\nRückseite ist 739.", "739"),
    ("Hallo Herr Makler, die Prüfnummer meiner\nKreditkarte lautet 739.", "739"),
    ("Kreditkarte 5555 5555 5555 4444, die Prüfziffer\nhinten lautet 739", "739"),
    ("Die CVC Ihrer Karte lautet 123.", "123"),
    ("Die Kartenprüfnummer Ihrer Visa-Karte lautet 123.", "123"),
    ("Die Prüfnummer Ihrer Visa-Karte lautet 123.", "123"),
    ("Prüfnummer (CVV) der Mastercard: 123", "123"),
    ("Die dreistellige Prüfnummer auf der Rückseite Ihrer Karte: 123", "123"),
    ("Kartenprüfnummer (die letzten 3 Ziffern auf dem Unterschriftsfeld): 739", "739"),
    (KARTE + "CVC 2: 739", "739"),
    (KARTE + "CVV 2: 739", "739"),
    (KARTE + "CV2: 739", "739"),
    (KARTE + "C.V.C.: 739", "739"),
    (KARTE + "CVC.: 739", "739"),
    (KARTE + "Kartenprüfzahl: 739", "739"),
    (KARTE + "Kartenverifikationsnummer: 739", "739"),
    ("Kreditkarten-Sicherheitscode: 123", "123"),
    ("Kreditkartensicherheitscode: 123", "123"),
    # Kunden-Mail ohne Ankündigung: wenige Zwischenwörter, der Wert beendet die Zeile (Ende-zu-Ende-Fall)
    ("Mastercard 5555 5555 5555 4444, gültig bis 11/26, Prüfziffer hinten 739", "739"),
    ("Kreditkarte 4111 1111 1111 1111, CVC auf der Rückseite 739.", "739"),
]


@pytest.mark.parametrize("text, wert", CVC_LECKS)
def test_b2_kartenpruefnummer(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert wert in _stellen(funde, "kreditkarte") or wert.replace(" ", "") in "".join(_stellen(funde, "kreditkarte")), \
        _paare(funde)
    platzhalter = ["[KREDITKARTE]"]
    assert _gemeldet(text, wert.split()[0], platzhalter=platzhalter), _gruende(text)


def test_b2_pruefnr_als_spaltenkopf(tmp_path):
    """Spaltenkopf "Prüfnr." neben "Kartennummer": der Wert darunter wird geschwärzt, das Etikett selbst ist kein
    Name."""
    pdf = _tabellen_pdf(tmp_path / "karte.pdf", ["Karteninhaber", "Kartennummer", "Prüfnr."],
                        [["Weber, Anna", "4111 1111 1111 1111", "739"]])
    e = analysiere_pdf(pdf, ALLE, [], [])
    assert "739" in _stellen(e["funde"], "kreditkarte"), _paare(e["funde"])
    assert not [t for t in _an(e["funde"]) if "Prüfnr" in t], _paare(e["funde"])


def test_b2_kammfeld_je_ziffer(tmp_path):
    """Kammfeld mit Kästchen je Ziffer: die drei Ziffern werden geschwärzt (Textebene der Ausgabe ohne "7 3 9")."""
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    y = 80
    for z in ["Zahlung per Kreditkarte", "Kreditkarte: Mastercard", "Kartennummer: 5555 5555 5555 4444",
              "Gültig bis: 11/26"]:
        s.insert_text((60, y), z, fontsize=11, fontname="helv")
        y += 18
    y += 10
    s.insert_text((60, y), "Kartenprüfnummer (CVC):", fontsize=11, fontname="helv")
    for i, ziffer in enumerate("739"):
        r = fitz.Rect(200 + i * 20, y - 13, 216 + i * 20, y + 4)
        s.draw_rect(r, color=(0, 0, 0), width=0.6)
        s.insert_text((r.x0 + 4.5, y), ziffer, fontsize=11, fontname="cour")
    pdf = tmp_path / "kamm.pdf"
    doc.save(pdf)
    doc.close()
    a = analysiere_pdf(pdf, ALLE, [], [], ocr=OcrAttrappe())
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / "aus")
    text = _ausgabe_text(e["ausgabe"])
    assert not re.findall(r"(?<!\S)[739](?!\S)", text), text
    assert "Gültig bis" in text and "11/26" in text, text


# --- B3: Geburtsname hinter Etiketten mit Zusatz, langer Klammer, in der Nachbarzelle
GEBURTSNAME_LECKS = [
    ("Geburtsname, falls abweichend: Quarnstedt", "Quarnstedt"),
    ("Geburtsname (falls vom Familiennamen abweichend): Quarnstedt", "Quarnstedt"),
    ("Geburtsname (nur ausfüllen, wenn abweichend): Quarnstedt", "Quarnstedt"),
    ("Geburtsname der versicherten Person: Quarnstedt", "Quarnstedt"),
    ("Geburtsname lt. Ausweis: Quarnstedt", "Quarnstedt"),
    ("Ihr Geburtsname lautet Quarnstedt.", "Quarnstedt"),
    ("Geb.-Name\t\tQuarnstedt", "Quarnstedt"),
    ("GEB.-NAME\t\tQUARNSTEDT", "QUARNSTEDT"),
    ("Geb.Name\t\tQuarnstedt", "Quarnstedt"),
    ("Geb. Name\t\tQuarnstedt", "Quarnstedt"),
    # Versalien: "FALLS", "DER" treffen die Namensform, sind aber Zwischenwörter (Ende-zu-Ende-Fall der Gegenprüfung)
    ("GEBURTSNAME, FALLS ABWEICHEND: QUARNSTEDT", "QUARNSTEDT"),
    ("GEBURTSNAME DER VERSICHERTEN PERSON: QUARNSTEDT", "QUARNSTEDT"),
    ("GEBURTSNAME ABWEICHEND: QUARNSTEDT", "QUARNSTEDT"),
    ("Geburtsname der Versicherten: Quarnstedt", "Quarnstedt"),
    ("Geburtsname abweichend: Quarnstedt", "Quarnstedt"),
    # Etikett in der Klammer eines anderen: der Wert ist die Klammer des Werts (Ende-zu-Ende-Fall der Gegenprüfung)
    ("Familienname (Geburtsname): Weber (Quarnstedt)", "Quarnstedt"),
    ("Name (ggf. Geburtsname): Weber (Quarnstedt)", "Quarnstedt"),
    ("Name, Vorname (Geburtsname): Weber, Anna (Quarnstedt)", "Quarnstedt"),
    ("FAMILIENNAME (GEBURTSNAME): WEBER (QUARNSTEDT)", "QUARNSTEDT"),
]


@pytest.mark.parametrize("text, wert", GEBURTSNAME_LECKS)
def test_b3_geburtsname_hinter_etikett(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert wert in _stellen(funde, "namen"), _paare(funde)
    assert _gemeldet(text, wert), _gruende(text)


@pytest.mark.parametrize("text, person, geburtsname", [
    ("Familienname (Geburtsname): Weber (Quarnstedt)", "Weber", "Quarnstedt"),
    ("Name, Vorname (Geburtsname): Weber, Anna (Quarnstedt)", "Weber, Anna", "Quarnstedt"),
])
def test_b3_geburtsname_in_klammer_gleicher_platzhalter(text, person, geburtsname):
    funde = analysiere_text(text, {"namen"}, [], [])
    ersatz = {f["text"]: f["ersatz"] for f in funde if f["kategorie"] == "namen"}
    assert ersatz.get(geburtsname) == ersatz.get(person) is not None, ersatz


def test_b3_geburtsname_ende_zu_ende(tmp_path):
    _, e, text = _schwaerzen(tmp_path, ["Antrag auf Lebensversicherung", "Name: Weber", "Vorname: Anna",
                                        "Geburtsname, falls abweichend: Quarnstedt", "Familienstand: verheiratet"])
    assert "Quarnstedt" not in text, text
    assert "Familienstand" in text and "verheiratet" in text, text


# --- B (mittel): Mehrzahl und zweizeiliger Spaltenkopf
@pytest.mark.parametrize("text, werte", [
    ("eVB-Nummern: M3N4P5Q, R7T2W9K", ["M3N4P5Q", "R7T2W9K"]),
    ("EVB-NUMMERN: K7H3M9P, R7T2W9K", ["K7H3M9P", "R7T2W9K"]),
    ("eVB-Nummern:\nK7H3M9P\nB9C8D7E", ["K7H3M9P", "B9C8D7E"]),
    ("Transfertickets: TTABCDEFGH12XY", ["TTABCDEFGH12XY"]),
    ("Transferticket-Nummern: TTABCDEFGH12XY", ["TTABCDEFGH12XY"]),
    ("Versicherungsbestätigungen: K7H3M9P", ["K7H3M9P"]),
])
def test_b_mehrzahl(text, werte):
    funde = analysiere_text(text, ALLE, [], [])
    for wert in werte:
        assert ("vertrag", wert) in _paare(funde), _paare(funde)
        assert _gemeldet(text, wert), _gruende(text)


def test_b_zweizeiliger_spaltenkopf(tmp_path):
    """Bestandsliste: der Spaltenkopf "Versicherungs-" ⏎ "bestätigung" bricht um – die eVB-Nummern darunter werden
    geschwärzt und, bleiben sie lesbar, gemeldet."""
    doc = fitz.open()
    seite = doc.new_page()
    zeilen = [["Kennzeichen", "Versicherungs-", "Vertrag"], ["", "bestätigung", ""],
              ["M-AB 123", "K7H3M9P", "KH-0815"], ["M-CD 456", "R7T2W9K", "KH-0816"]]
    for zi, zeile in enumerate(zeilen):
        for si, zelle in enumerate(zeile):
            if zelle:
                seite.insert_text((60 + 160 * si, 100 + 14 * zi), zelle, fontsize=10, fontname="helv")
    pdf = tmp_path / "bestand.pdf"
    doc.save(pdf)
    doc.close()
    e = analysiere_pdf(pdf, ALLE, [], [])
    for wert in ("K7H3M9P", "R7T2W9K"):
        assert ("vertrag", wert) in _paare(e["funde"]), _paare(e["funde"])
    texte = [v.text for v in restrisiko_pruefen(pdf)]
    for wert in ("K7H3M9P", "R7T2W9K"):
        assert wert in texte, texte


def test_b_zweizeiliger_spaltenkopf_unter_titel(tmp_path):
    """Ende-zu-Ende-Fall der Gegenprüfung: über dem zweizeiligen Kopf steht eine Titelzeile ("Bestandsliste Kfz").
    Titel und erste Kopfzeile ergeben schon einen Kopf ("Kfz-Kennzeichen", "Vertrag") – der Kopf eine Zeile tiefer
    kennt aber mehr Spalten ("Versicherungsbestätigung") und gilt."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    zeilen = [["Bestandsliste Kfz"], ["Kennzeichen", "Versicherungs-", "Vertrag"], ["", "bestätigung", ""],
              ["M-AB 123", "K7H3M9P", "KH-0815"], ["M-CD 456", "R7T2W9K", "KH-0816"]]
    for zi, zeile in enumerate(zeilen):
        for si, zelle in enumerate(zeile):
            if zelle:
                seite.insert_text(((60, 250, 420)[si], 80 + 18.15 * zi), zelle, fontsize=11, fontname="helv")
    pdf = tmp_path / "bestand.pdf"
    doc.save(pdf)
    doc.close()
    e = analysiere_pdf(pdf, ALLE, [], [])
    for wert in ("K7H3M9P", "R7T2W9K", "KH-0815"):
        assert ("vertrag", wert) in _paare(e["funde"]), _paare(e["funde"])
    assert ("kfz", "M-AB 123") in _paare(e["funde"]), _paare(e["funde"])
    aus = schwaerze_pdf(pdf, e["funde"], modell=e["modell"], ziel_ordner=tmp_path / "aus")
    text = _ausgabe_text(aus["ausgabe"])
    assert "K7H3M9P" not in text and "R7T2W9K" not in text, text
    assert "Bestandsliste" in text and "Kennzeichen" in text, text


# ======================================================================
# C  Über-Schwärzung
# ======================================================================
# --- C1: leeres Feld "Geburtsname" – das nächste Feld-Etikett ist kein Geburtsname
@pytest.mark.parametrize("text, wort", [
    ("Geburtsname:\nPLZ, Ort: 50667 Köln\nDie PLZ ist Pflicht. Ohne PLZ keine Tarifierung.", "PLZ"),
    ("Geburtsname:\t\tPLZ: 50667\nDie PLZ des Wohnorts zählt.", "PLZ"),
    ("Person\t\tGeburtsname\t\tStatus\nWeber, Anna\t\t\t\taktiv\nStatus des Vertrags: aktiv", "Status"),
    ("Geburtsname:\nPostleitzahl: 50667", "Postleitzahl"),
    ("Geburtsname:\nKreis: Rhein-Sieg", "Kreis"),
    ("Geburtsname:\nGeburtsland: Polen", "Geburtsland"),
    ("Geburtsname:\nErziehungsberechtigter: Max Weber", "Erziehungsberechtigter"),
    ("GEBURTSNAME:\nPLZ, ORT: 50667 KÖLN", "PLZ"),
    ("GEBURTSNAME:\t\tSTATUS: AKTIV", "STATUS"),
    ("Bitte nennen Sie uns den Geburtsname\nIhnen ist bekannt, dass wir ihn benötigen.", "Ihnen"),
    ("Wir benötigen den Geburtsname\nSowie das Geburtsdatum des Kindes.", "Sowie"),
    ("Geburtsname: Art der Versicherung: Leben", "Art"),          # Etikett mit Ergänzung ("Art der …:")
    ("Geburtsname: Art der Versicherung: Leben", "Leben"),
    ("Geburtsname: Status: ledig", "Status"),
])
def test_c1_feld_etikett_ist_kein_geburtsname(text, wort):
    funde = analysiere_text(text, ALLE, [], [])
    assert not [t for t in _stellen(funde, "namen") if wort in t.split() or t == wort], _paare(funde)
    assert not [g for t, g in _gruende(text) if wort in t and "Geburtsname" in g], _gruende(text)


def test_c1_leeres_feld_wird_nicht_weitergegeben(tmp_path):
    """Lauf mit zwei Dokumenten: das leere Feld "Geburtsname:" in A macht "PLZ" nicht zur Person – auch nicht in B."""
    a = _text_pdf(tmp_path / "a.pdf", ["Antrag Hausrat", "Name: Weber, Anna", "Geburtsname:", "PLZ, Ort: 50667 Köln"])
    b = _text_pdf(tmp_path / "b.pdf", ["Hausrat-Police", "Tarifzone nach PLZ: 3",
                                       "Die PLZ des Versicherungsorts zählt."])
    ea, eb = analysiere_pdf(a, ALLE, [], [], ocr=OcrAttrappe()), analysiere_pdf(b, ALLE, [], [], ocr=OcrAttrappe())
    analyse.weitergabe_anwenden([ea, eb])
    for e in (ea, eb):
        assert not [t for t in _stellen(e["funde"], "namen") if "PLZ" in t], _paare(e["funde"])


# --- C2: hinter "geb." zählen nur namenartige Wörter
@pytest.mark.parametrize("text, wort", [
    ("VERSICHERUNGSNEHMER WEBER, ANNA GEB. IN KÖLN\nVERTRAG IN KRAFT", "IN"),
    ("Max Mustermann, geb. In Köln\nIn Kürze erhalten Sie Post.", "In"),
    ("Anna Weber geb. Polen\nReiseziel: Polen", "Polen"),
    ("Als geborener Kölner kennt der Fahrer die Strecke. Der Kölner Ring ist gesperrt.", "Kölner"),
    ("Max Weber, geb. Lt. Ausweis 12.03.1980\nLt. Vertrag gilt der Tarif.", "Lt"),
    ("Anna Weber geb. Wien", "Wien"),
    ("Anna Weber geb. Paris", "Paris"),
    ("Anna Weber geb. London", "London"),
    ("Anna Weber geb. Istanbul", "Istanbul"),
    ("Anna Weber geb. Warschau", "Warschau"),
    ("Anna Weber geb. Moskau", "Moskau"),
    ("Anna Weber geb. Ankara", "Ankara"),
    ("Anna Weber geb. Türkei", "Türkei"),
    ("Anna Weber geb. Russland", "Russland"),
    ("Anna Weber geb. Kasachstan", "Kasachstan"),
    ("Anna Weber geb. Rumänien", "Rumänien"),
    ("Anna Weber geb. USA", "USA"),
    ("Anna Weber geb. Zürich", "Zürich"),
    ("Anna Weber geb. Neustadt", "Neustadt"),
    ("Anna Weber geb. Bad Homburg", "Bad"),
    ("Anna Weber geb. St. Ingbert", "Ingbert"),
    ("Anna Weber geb. Marburg", "Marburg"),
    ("ANNA WEBER GEB. MARBURG", "MARBURG"),
    ("Anna Weber geb. Laut Urkunde 1980", "Laut"),
    ("Anna Weber geb. Erste Ehe", "Erste"),
    ("Standort Köln, Geb. Kantine", "Kantine"),
    ("Bürogebäude Hauptstraße, Geb. Hinterhaus", "Hinterhaus"),
    ("Familienname (Geburtsname): Weber (Hamburg)\nWohnort: Hamburg", "Hamburg"),   # Klammer ohne Namen
])
def test_c2_kein_geburtsname_aus_nicht_namen(text, wort):
    funde = analysiere_text(text, ALLE, [], [])
    assert not [t for t in _stellen(funde, "namen") if wort in t.split() or t == wort], _paare(funde)


@pytest.mark.parametrize("text, wort", [
    ("Klinikum Mitte, Geb. Nord", "Nord"),
    ("Werk Süd, Geb. West", "West"),
    ("Geborene Zwillinge sind im Tarif mitversichert.", "Zwillinge"),
    ("[PERSON A] geb. In Köln", "In"),
])
def test_c2_kein_fehlverdacht_geburtsname(text, wort):
    assert not [g for t, g in _gruende(text, platzhalter=["[PERSON A]"]) if wort in t and "Geburtsname" in g], \
        _gruende(text, platzhalter=["[PERSON A]"])


@pytest.mark.parametrize("text, wort", [("[PERSON A], geb. Flensburg", "Flensburg"),
                                        ("[PERSON A] geb. Polen", "Polen")])
def test_c2_ort_hinter_geb_wird_gemeldet(text, wort):
    """Gegenprüfung 4d (Befund 2): ein Ort direkt hinter "Name geb." kann Geburtsname sein (Herkunftsnamen wie Linz,
    Dessau, Israel) – die Erkennung schwärzt ihn nicht (er kann auch der Geburtsort sein), die Selbstkontrolle meldet
    ihn, bleibt er lesbar. Bis Runde 4c galt das als Fehlverdacht; still blieb so jeder Herkunftsname."""
    assert [g for t, g in _gruende(text, platzhalter=["[PERSON A]"]) if wort in t and "Geburtsname" in g], \
        _gruende(text, platzhalter=["[PERSON A]"])


@pytest.mark.parametrize("text, person, geburtsname", [
    ("Anna Weber geb. Quarnstedt", "Anna Weber", "Quarnstedt"),
    ("Anna Weber geb. Hagen", "Anna Weber", "Hagen"),            # Großstadt, zugleich Nachname
    ("WEBER, ANNA GEB. QUARNSTEDT", "WEBER, ANNA", "QUARNSTEDT"),
    ("Max Weber, geborener Schulz", "Max Weber", "Schulz"),
    ("Anna Weber geb. Li", "Anna Weber", "Li"),                  # kurzer Nachname der Wissensbasis
])
def test_c2_gegenproben_namen_bleiben_geburtsnamen(text, person, geburtsname):
    funde = analysiere_text(text, {"namen"}, [], [])
    ersatz = {f["text"]: f["ersatz"] for f in funde if f["kategorie"] == "namen"}
    assert ersatz.get(geburtsname) == ersatz.get(person) is not None, ersatz


# ======================================================================
# D  Niedrig
# ======================================================================
@pytest.mark.parametrize("text, wert", [
    ("Anna Weber geb. d'Alessandro", "Alessandro"),
    ("WEBER, ANNA GEB.    QUARNSTEDT", "QUARNSTEDT"),                 # Festbreiten-Bestandsliste
    ("Ihre eVB-Nurnmer: K7H3M9P", "K7H3M9P"),                         # OCR-Verleser in fremder Textebene
    ("Kreditkarte: 4111 1111 1111 1111\nKartenprüfnurnmer: 739", "739"),
    ("Name: Weber, Anna\nGeburtsnarne: Quarnstedt", "Quarnstedt"),
    ("Kreditkarte: 4111 1111 1111 1111\nSecurity Code: 739", "739"),  # englische Etiketten
    ("Card Verification Code: 739", "739"),
    (KARTE + "CVN: 739", "739"),
    ("Betreff: AW: eVB-Anfrage – K7H3M9P", "K7H3M9P"),
    ("eVB-Nummer*: K7H3M9P", "K7H3M9P"),
    ("eVB-Nummer „K7H3M9P“", "K7H3M9P"),
    ("eVB-Nummer → K7H3M9P", "K7H3M9P"),
    ("eVB-Nummer| K7H3M9P", "K7H3M9P"),
    ("eVB-Nummer » K7H3M9P", "K7H3M9P"),
    ("eVB-Nummer: \"K7H3M9P\"", "K7H3M9P"),
    ("eVB-Nummer; K7H3M9P", "K7H3M9P"),
    ("eVB-Nummer_________K7H3M9P", "K7H3M9P"),
    ("SF-Transferticket: TT12345678AB", "TT12345678AB"),
    ("Versicherungsnehmerin: Anna Weber gab. Quarnstedt", "Quarnstedt"),  # OCR liest "geb." als "gab."
    ("Anna Weber gab. Quarnstedt, geb. am 12.03.1980", "Quarnstedt"),
])
def test_d_seltene_schreibweisen(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert any(wert in t for t in _an(funde)), _paare(funde)


def test_d_gab_als_geburtsname_gleicher_platzhalter():
    """ "gab." (OCR für "geb.") zwischen zwei Namen: der Geburtsname bekommt den Platzhalter der Person, und die
    Selbstkontrolle meldet ihn, bleibt er lesbar."""
    text = "Versicherungsnehmerin: Anna Weber gab. Quarnstedt"
    funde = analysiere_text(text, {"namen"}, [], [])
    ersatz = {f["text"]: f["ersatz"] for f in funde if f["kategorie"] == "namen"}
    assert ersatz.get("Quarnstedt") == ersatz.get("Anna Weber") is not None, ersatz
    rest = "Versicherungsnehmerin: [PERSON A] gab. Quarnstedt"
    assert [g for t, g in _gruende(rest, platzhalter=["[PERSON A]"]) if t == "Quarnstedt" and "Geburtsname" in g], \
        _gruende(rest, platzhalter=["[PERSON A]"])


@pytest.mark.parametrize("text", [
    "Frau Weber gab. Müller kam später.",                 # Satzende: "gab" ist ein Verb
    "Das Geld, das sie gab. Danach ging sie.",
    "Er erzählte, dass er ihm alles gab. Müller kam später.",
])
def test_d_gab_im_satz_ist_kein_geburtsname(text):
    funde = analysiere_text(text, ALLE, [], [])
    assert not [f for f in funde if "gab." in (f.get("gruppe") or "") or "geb." in (f.get("gruppe") or "")], funde
    assert not [g for _, g in _gruende(text) if "Geburtsname" in g], _gruende(text)


@pytest.mark.parametrize("text", [
    "Transferticket: SF 12 / SF 8 übernommen",
    "Laut Transferticket: SF 12 (Haftpflicht), SF 8 (Vollkasko)",
    "Transferticket: SF-Klasse 12, Beitragssatz 45 %",
    "Transferticket: Übernahme SF 12 ab 01.01.2025",
    "TRANSFERTICKET SF 12",
    "eVB: Tarif KH 12 / VK 8",
    "CVC: 3-4 Ziffern",
    "Kartenprüfnummer: 250 Euro",
    "CVC Capital Partners 2024",
])
def test_d_kein_fehlverdacht_der_etikett_regel(text):
    assert not [g for _, g in _gruende(text) if "Wert hinter Etikett" in g], _gruende(text)


@pytest.mark.parametrize("text, zahl", [
    ("Prüfbericht Nr. 4711, Prüfnummer 0815\nZahlung: girocard", "0815"),
    ("DIN EN ISO 9001\nPrüfnummer 4102\nAbrechnung per Kreditkarte", "4102"),
    ("Gutachten Nr. 2024-123\nPrüfnummer: 789\nRechnung per Kreditkarte beglichen", "789"),
    ("Sachverständigenbüro Weber\nPrüfnummer 1234\nKarteninhaber: siehe Rückseite", "1234"),
    ("Zahlungsart: Visa\nPrüfnummer 4567 vom TÜV", "4567"),
    ("Sicherheitscode: 4711 (Tür)\nKreditkarte", "4711"),
    ("CAV 2019", "2019"),
    # ohne Ankündigung: ein Verweis oder eine Jahreszahl ist kein Wert
    ("Kreditkarte: 4111 1111 1111 1111\nCVC auf Seite 123.", "123"),
    ("Kreditkarte: 4111 1111 1111 1111\nDie CVC gibt es seit 2015.", "2015"),
    ("Kreditkarte: 4111 1111 1111 1111\nDie CVC steht auf der Rückseite 2024 neu", "2024"),
])
def test_d_pruefnummer_anderer_gegenstaende(text, zahl):
    funde = analysiere_text(text, ALLE, [], [])
    assert ("kreditkarte", zahl) not in _paare(funde), _paare(funde)
    assert not [g for t, g in _gruende(text) if t == zahl and "Kartenprüf" in g], _gruende(text)


@pytest.mark.parametrize("text", ["eVB: EXPIRED", "eVB-Status: PENDING", "Transferticket: REQUESTED"])
def test_d_englische_statuswoerter(text):
    funde = analysiere_text(text, ALLE, [], [])
    assert not [t for k, t in _paare(funde) if k == "vertrag"], _paare(funde)
    assert not [g for _, g in _gruende(text) if "eVB" in g or "Transferticket" in g], _gruende(text)


@pytest.mark.parametrize("zeile", ["eVB: 2025/2026", "eVB-Nummer 2024/2025"])
def test_d_jahresbereich_auf_scans(zeile):
    funde = analyse._analysiere_dokument(_ocr_dok([zeile]), ALLE, [], [])
    assert not [t for k, t in _paare(funde) if k == "vertrag"], _paare(funde)


def test_d_kurze_kartennummer_wird_weitergegeben():
    """Die Sperre der Weitergabe gilt nur der Kartenprüfnummer: eine kurze Kartennummer hinter "Karten-Nr." wird wie
    vor Runde 4 auf ihre anderen Vorkommen übertragen."""
    funde = analysiere_text("Karten-Nr.: 1234\nKarte 1234 gesperrt", ALLE, [], [])
    stellen = [st for f in funde if f["kategorie"] == "kreditkarte" for st in f["stellen"] if st.get("an", True)]
    assert [st["text"] for st in stellen] == ["1234", "1234"], funde


def test_d_laufzeit_spaltenpruefung():
    """Die Spaltenprüfung hinter eVB-/CVC-Köpfen kostet keine überlineare Zeit (Befund: 200/400/800/1600 Zeilen mit
    Kopf "CVC … eVB-Nummer" 0,9/1,8/5,5/14,4 s, ohne solchen Kopf wie vorher 0,5/1,1/2,4/3,5 s – jede Prüfung las alle
    Zeilen der Seite neu nach ihrer Lage). Lastunabhängig: CPU-Zeit derselben Tabelle mit und ohne die beiden Köpfe im
    Wechsel gemessen."""
    import random
    import zeitmessung

    def tabelle(kopf):
        zufall = random.Random(4)
        zeilen = ["\t\t".join([f"{zufall.randint(100, 9999)}" for _ in range(8)]
                              + ["".join(zufall.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") for _ in range(7))])
                  for _ in range(600)]
        return kopf + "\n" + "\n".join(zeilen)
    mit = tabelle("Nr.\t\tCVC\t\tTarif\t\tWert\t\tA\t\tB\t\tC\t\tD\t\teVB-Nummer")
    ohne = tabelle("Nr.\t\tAnzahl\t\tTarif\t\tWert\t\tA\t\tB\t\tC\t\tD\t\tCode")
    pruefe_text(mit)
    gemessen = zeitmessung.cpu_sekunden_abwechselnd({"mit": lambda: pruefe_text(mit),
                                                     "ohne": lambda: pruefe_text(ohne)}, 2)
    verhaeltnis = gemessen["mit"][1] / max(gemessen["ohne"][1], 1e-6)
    print(f"Spaltenprüfung CPU: mit Kopf {gemessen['mit'][1]:.2f} s, ohne {gemessen['ohne'][1]:.2f} s")
    assert verhaeltnis < 1.4, f"Selbstkontrolle: eVB-/CVC-Köpfe kosten das {verhaeltnis:.2f}-Fache"
