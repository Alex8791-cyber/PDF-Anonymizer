"""Kennungen aus dem Makler-Alltag (Runde 4): eVB-Nummer und Transferticket der Kfz-Versicherung, Geburtsname hinter
"geb."/"geborene"/"Geburtsname", Kartenprüfnummer (CVC/CVV) einer Zahlungskarte.

Je Kennung: Erkennung auf der Textebene (Etikett in derselben Zeile, hinter Doppelpunkt, in der nächsten Zeile bzw.
Tabellenzelle), auf OCR-Text (synthetische Scan-Seite wie in test_detektoren_ocr.py, dazu eine echte Scan-Seite mit
Tesseract), Gegenproben ohne Fund und die Selbstkontrolle (restrisiko.py): ein lesbarer Wert hinter dem Etikett in
der Ausgabe ist ein Verdacht und macht die Ausgabe zu _PRUEFEN. Alle Werte sind erfunden."""

from pathlib import Path

import pytest

import pymupdf as fitz

from anonymisierer import analyse, muster, seitenmodell
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.restrisiko import pruefe_text, restrisiko_pruefen
from anonymisierer.schwaerzung import schwaerze_pdf
from conftest import braucht_ocr

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------
def _paare(funde) -> set:
    return {(f["kategorie"], f["text"]) for f in funde}


def _ersatz(funde, kategorie="namen") -> dict:
    """Fundtext -> Platzhalter (alle Stellen desselben Funds tragen denselben)."""
    return {f["text"]: f["ersatz"] for f in funde if f["kategorie"] == kategorie}


def _stellen(funde, kategorie) -> set:
    """Texte aller angehakten Stellen einer Kategorie."""
    return {st["text"] for f in funde if f["kategorie"] == kategorie for st in f["stellen"] if st.get("an", True)}


def _ocr_dok(zeilen, quelle="ocr"):
    """Seitenmodell einer OCR-Seite: je Zeile Zellen getrennt durch "\\t\\t" (große Lücke), Wörter durch " "."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    woerter = []
    y = 80.0
    for zi, zeile in enumerate(zeilen):
        x, wi = 50.0, 0
        for ci, zelle in enumerate(zeile.split("\t\t")):
            if ci:
                x += 60
            for w in zelle.split(" "):
                if not w:
                    x += 5
                    continue
                breite = 6.0 * len(w)
                woerter.append((x, y, x + breite, y + 12, w, 0, zi, wi))
                wi += 1
                x += breite + 4
        y += 18
    s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=woerter, ocr_quelle=quelle)
    doc.close()
    return seitenmodell.Dokument(None, [s])


def _verdacht(text, **kw) -> list:
    return [v.text for v in pruefe_text(text, **kw)]


def _gemeldet(text, wert, **kw) -> bool:
    return any(wert in t for t in _verdacht(text, **kw))


class OcrAttrappe:
    """OcrDienst-Ersatz: liefert vorgegebene Wörter je Seite."""

    def __init__(self, woerter=None):
        self.woerter_je_seite = woerter or {}

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, winkel=None, **_):
        return list(self.woerter_je_seite.get(seite_nr0, [])), None

    def schliessen(self):
        pass


def _ocr_seite(pfad, zeilen):
    """Scan-Seite aus Textzeilen mit den OCR-Wörtern (5-Tupel) der gedruckten Zeilen."""
    vorlage = fitz.open()
    s = vorlage.new_page()
    woerter = []
    y = 100
    for zeile in zeilen:
        s.insert_text((60, y), zeile, fontsize=12, fontname="helv")
        x = 60.0
        for wort in zeile.split():
            breite = fitz.get_text_length(wort, fontname="helv", fontsize=12)
            woerter.append((x, y - 10, x + breite, y + 3, wort))
            x += breite + fitz.get_text_length(" ", fontname="helv", fontsize=12)
        y += 20
    pix = s.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    vorlage.close()
    doc.save(pfad)
    doc.close()
    return Path(pfad), woerter


def _text_pdf(pfad, zeilen):
    doc = fitz.open()
    seite = doc.new_page()
    y = 80
    for z in zeilen:
        seite.insert_text((60, y), z, fontsize=11, fontname="helv")
        y += 18
    doc.save(pfad)
    doc.close()
    return Path(pfad)


# ----------------------------------------------------------------------
# 1. eVB-Nummer (elektronische Versicherungsbestätigung): 7 Zeichen aus Großbuchstaben und Ziffern
# ----------------------------------------------------------------------
EVB = [
    ("Ihre eVB-Nummer lautet: A1B2C3D", "A1B2C3D"),
    ("eVB-Nr. K7H3M9P für die Zulassung", "K7H3M9P"),
    ("eVB: X4Y8Z2Q", "X4Y8Z2Q"),
    ("EVB-Nr Q2W3E4R", "Q2W3E4R"),
    ("eVB-Nummer: 7RT4ZU9", "7RT4ZU9"),
    ("VB-Nummer: 7RT4ZU9", "7RT4ZU9"),
    ("Versicherungsbestätigungsnummer: B9C8D7E", "B9C8D7E"),
    ("Versicherungsbestätigungs-Nr.: B9C8D7E", "B9C8D7E"),
    ("Ihre elektronische Versicherungsbestätigung: M3N4P5Q", "M3N4P5Q"),
    ("Versicherungsbestätigung (eVB) M3N4P5Q", "M3N4P5Q"),
    ("Ihre eVB lautet M3N4P5Q.", "M3N4P5Q"),
    ("eVB-Nummer\nM3N4P5Q", "M3N4P5Q"),                     # Wert in der nächsten Zeile
    ("eVB-Nummer:\t\tM3N4P5Q", "M3N4P5Q"),                 # Wert in der Tabellenzelle daneben
    ("eVB: LOO117Q", "LOO117Q"),                           # so liest die OCR "L0O1I7Q" (O/0, I/1 verwechselt)
    ("Ihre eVB-Nummer: KXHPMTQ", "KXHPMTQ"),               # ohne Ziffer: Versalien in gemischt geschriebenem Text
    ("eVB 4711081 (Kfz-Haftpflicht)", "4711081"),          # nur Ziffern
]


@pytest.mark.parametrize("text, wert", EVB)
def test_evb_muster(text, wert):
    assert wert in muster.finde_vertragsnummern(text)
    assert any(text[s.start:s.ende] == wert for s in muster.stellen("vertrag", text))


@pytest.mark.parametrize("text, wert", EVB)
def test_evb_in_der_analyse(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert ("vertrag", wert) in _paare(funde), _paare(funde)
    assert _ersatz(funde, "vertrag")[wert] == "[VERTRAGS-NR]"


@pytest.mark.parametrize("text", [
    "Bitte fordern Sie die eVB per E-Mail an.",
    "eVB anfordern",
    "Die eVB per E-Mail erhalten Sie sofort.",
    "Ihre eVB erhalten Sie in Kürze, die eVB gilt für die Zulassung.",
    "EVB-NUMMER ANFRAGE",                                   # Versalien: ein Wort ohne Ziffer ist keine eVB
    "eVB-Nummer: siehe Anlage",
    "eVB gültig bis 31.12.2025",
    "Die VB ist abgelaufen.",                               # "VB" allein ist kein Etikett
    "Verhandlungsbasis 2500 EUR VB",
])
def test_evb_gegenproben(text):
    funde = analysiere_text(text, ALLE, [], [])
    assert not [f["text"] for f in funde if f["kategorie"] == "vertrag"], _paare(funde)
    assert muster.finde_vertragsnummern(text) == []


# ----------------------------------------------------------------------
# 2. Transferticket (Wechsel des Kfz-Versicherers, Übertragung des Schadenfreiheitsrabatts)
# ----------------------------------------------------------------------
TICKET = [
    ("Transferticket: TT12345678AB", "TT12345678AB"),
    ("Transfer-Ticket: 4711ABCD99", "4711ABCD99"),
    ("Transferticket-Nr.: 4711ABCD99", "4711ABCD99"),
    ("Transferticket-Nummer 98AB76CD54EF", "98AB76CD54EF"),
    ("Transfer-Ticket-Nr. 98AB76CD54EF", "98AB76CD54EF"),
    ("Ihr Transferticket lautet TX7Q2M9K4P.", "TX7Q2M9K4P"),
    ("Transferticket\nTT12345678AB", "TT12345678AB"),       # Wert in der nächsten Zeile
    ("Transferticket:\t\tTT-2024-081547", "TT-2024-081547"),  # Tabellenzelle, mit Bindestrichen
    ("Transferticket: Tx8Hq2LmP9", "Tx8Hq2LmP9"),          # gemischte Schreibung mit Ziffern
    ("TRANSFERTICKET: TT0815AB4711", "TT0815AB4711"),
]


@pytest.mark.parametrize("text, wert", TICKET)
def test_transferticket_muster(text, wert):
    assert wert in muster.finde_vertragsnummern(text)


@pytest.mark.parametrize("text, wert", TICKET)
def test_transferticket_in_der_analyse(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert ("vertrag", wert) in _paare(funde), _paare(funde)


@pytest.mark.parametrize("text", [
    "Das Transferticket beantragen wir beim Vorversicherer.",
    "Transferticket anfordern",
    "Transferticket: 2024",
    "Transferticket vom 12.03.2024",
    "TRANSFERTICKET ANGEFORDERT",
    "Transferticket: folgt",
])
def test_transferticket_gegenproben(text):
    funde = analysiere_text(text, ALLE, [], [])
    assert not [f["text"] for f in funde if f["kategorie"] == "vertrag"], _paare(funde)


# ----------------------------------------------------------------------
# 3. Geburtsname hinter "geb." / "geborene" / "geb:" – dieselbe Person, derselbe Platzhalter
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, person, geburtsname", [
    ("Anna Weber geb. Schulz wohnt in Berlin.", "Anna Weber", "Schulz"),
    ("Versicherungsnehmerin: Anna Weber geb. Schulz", "Anna Weber", "Schulz"),
    ("WEBER, ANNA GEB. SCHULZ", "WEBER, ANNA", "SCHULZ"),
    ("Frau Anna Weber geb. Schulz-Meyer wohnt hier.", "Anna Weber", "Schulz-Meyer"),
    ("Anna Weber, geborene Schulz, hat angerufen.", "Anna Weber", "Schulz"),
    ("Anna Weber (geb. Schulz) hat angerufen.", "Anna Weber", "Schulz"),
    ("Anna Weber, geb: Schulz", "Anna Weber", "Schulz"),
    ("Erika Mustermann geb. Gabler", "Erika Mustermann", "Gabler"),
    ("Sabine Krüger geb. Quarnstedt", "Sabine Krüger", "Quarnstedt"),   # unbekannter Geburtsname
])
def test_geburtsname_gehoert_zur_person(text, person, geburtsname):
    funde = analysiere_text(text, {"namen"}, [], [])
    ersatz = _ersatz(funde)
    assert geburtsname in ersatz and person in ersatz, ersatz
    assert ersatz[geburtsname] == ersatz[person], ersatz
    assert not any("geb" in t.casefold() for t in _stellen(funde, "namen")), _stellen(funde, "namen")


@pytest.mark.parametrize("text, wert", [
    ("Geburtsname: Schulz", "Schulz"),
    ("Geburtsname Quarnstedt", "Quarnstedt"),
    ("Geburtsname:\t\tQuarnstedt", "Quarnstedt"),
    ("Mutter: Maria, geb. Quarnstedt", "Quarnstedt"),
    ("Kontoinhaberin Weber geb. Quarnstedt", "Quarnstedt"),
])
def test_geburtsname_hinter_etikett(text, wert):
    funde = analysiere_text(text, {"namen"}, [], [])
    assert wert in _stellen(funde, "namen"), _paare(funde)


def test_geburtsname_einer_familie():
    """Trägt eine zweite Person den Geburtsnamen als Nachnamen, ist der allein stehende Name ein Familienname
    ([FAMILIE A], bestehende Regel); die Personen behalten ihre eigenen Buchstaben."""
    text = "Anna Weber geb. Schulz ist die Tochter von Peter Schulz.\nHerr Schulz hat angerufen."
    ersatz = _ersatz(analysiere_text(text, {"namen"}, [], []))
    assert ersatz.get("Schulz") == "[FAMILIE A]", ersatz
    assert ersatz["Anna Weber"] != ersatz["Peter Schulz"]


def test_geburtsname_derselben_person_ueberall_gleich():
    text = ("Versicherungsnehmerin: Anna Weber geb. Schulz\n"
            "Sehr geehrte Frau Weber,\n"
            "Ihr Antrag unter dem Namen Schulz liegt uns vor.")
    funde = analysiere_text(text, {"namen"}, [], [])
    ersatz = _ersatz(funde)
    assert ersatz["Schulz"] == ersatz["Anna Weber"] == "[PERSON A]", ersatz
    schulz = next(f for f in funde if f["text"] == "Schulz")
    assert [st["text"] for st in schulz["stellen"] if st["an"]] == ["Schulz", "Schulz"]


@pytest.mark.parametrize("text, wort", [
    ("Max Muster, geb. 12.03.1980", None),
    ("Anna Weber, geb. am 12.03.1980 in Köln", "Köln"),
    ("Anna Weber, geb. in Köln", "Köln"),
    ("Die Gebr. Schulz GmbH liefert das Fahrzeug.", None),    # Gebrüder: Firma (Name darin regelt wissen.namen)
    ("Geb. 3, Raum 214", None),
    ("Geb.-Nr. 12, Raum 214", None),
    ("Bitte im Geb. Ost melden.", "Ost"),
    ("Anna Weber geb. schulz", "schulz"),                      # klein geschrieben
    ("Sie ist eine geborene Berlinerin.", "Berlinerin"),
    ("Er ist als geborener Hamburger stolz auf den Hafen.", "Hamburger"),
    ("Anna Weber geb. Mai 1980", "Mai"),                       # Monat mit Jahr: ein Datum
    ("Anna Weber geb. Dez. 1973", "Dez"),
    ("Frau Birgit Müller, geb. Od. Dez. 1973, wohnhaft in Hof", "Od"),   # OCR liest "04." als "Od.": der Tag
    ("Anna Weber, geb. O4.12.1973", "O4"),                     # Ziffer im Wort: kein Name
    ("Nr. Kunde (Name, Vorname)\t\tgeb.\t\tOrt", "Ort"),       # Spaltenköpfe
    ("Name\t\tgeb.\t\tWohnort", "Wohnort"),
    ("GEB.-DATUM            03.06.1962", None),
    ("MITVERS. PERSON       HAAS, ANNA-LENA  GEB. 07.05.1976", "GEB"),
])
def test_geburtsname_gegenproben(text, wort):
    funde = analysiere_text(text, {"namen"}, [], [])
    assert not [f["text"] for f in funde if "ner.geburtsname" in f["quellen"]], _paare(funde)
    if wort is not None:
        assert not any(wort in t.split() or wort == t for t in _stellen(funde, "namen")), _stellen(funde, "namen")


# ----------------------------------------------------------------------
# 4. Kartenprüfnummer (CVC/CVV) einer Zahlungskarte: 3 oder 4 Ziffern
# ----------------------------------------------------------------------
CVC = [
    ("Kartennummer: 4111 1111 1111 1111, CVC 123", "123"),
    ("CVC: 123", "123"),
    ("CVV: 123", "123"),
    ("CVC2: 1234", "1234"),
    ("CVV2: 0123", "0123"),
    ("CAV: 456", "456"),
    ("Kartenprüfnummer: 789", "789"),
    ("Kartenprüfnummer (CVC): 789", "789"),
    ("Prüfnummer der Karte: 456", "456"),
    ("Prüfnummer (der Karte): 456", "456"),
    ("Sicherheitscode der Kreditkarte: 321", "321"),
    ("Sicherheitscode (der Karte): 321", "321"),
    ("Kreditkarte 4111 1111 1111 1111 Prüfnummer 456", "456"),           # Kartennummer daneben
    ("Visa, gültig bis 12/27\nPrüfnummer: 4567", "4567"),               # Kartenangabe in der Zeile darüber
    ("Kreditkarte: 4111 1111 1111 1111\nSicherheitscode: 987", "987"),
    ("CVC\n123", "123"),                                                 # Wert in der nächsten Zeile
    ("CVC:\t\t123", "123"),                                              # Tabellenzelle
]


@pytest.mark.parametrize("text, wert", CVC)
def test_kartenpruefnummer_muster(text, wert):
    assert wert in muster.finde_kreditkarte(text)


@pytest.mark.parametrize("text, wert", CVC)
def test_kartenpruefnummer_in_der_analyse(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert ("kreditkarte", wert) in _paare(funde), _paare(funde)
    assert _ersatz(funde, "kreditkarte")[wert] == "[KREDITKARTE]"


@pytest.mark.parametrize("text, ohne_fund", [
    ("TÜV-Prüfnummer 123", True),
    ("Plakette mit Prüfnummer 123 am Fahrzeug", True),
    ("Prüfnummer der Zulassung: 456", True),
    ("Prüfnummer des Gutachtens: 789", True),
    ("Prüfnummer: 4567", False),                     # ohne Kartenbezug keine Kartenprüfnummer
    ("Sicherheitscode: 123", True),
    ("Sicherheitscode für Ihr Online-Postfach: 123", True),
    ("Die CVC steht auf der Rückseite der Karte.", True),
    ("CVC 12345", False),                            # fünf Ziffern sind keine Kartenprüfnummer
    # eine Kartenangabe in der Nähe, aber die Prüfnummer gehört zu etwas anderem (Bezugswort davor)
    ("Die Reparatur wurde per Kreditkarte bezahlt.\nTÜV Prüfnummer 123", True),
    ("Kreditkarte: 4111 1111 1111 1111\nGutachten Prüfnummer 4567", False),
])
def test_kartenpruefnummer_gegenproben(text, ohne_fund):
    """Keine Kartenprüfnummer (die Kartennummer selbst bleibt ein Fund); ohne_fund: überhaupt kein Fund."""
    funde = analysiere_text(text, ALLE, [], [])
    kurz = [f["text"] for f in funde if f["kategorie"] == "kreditkarte" and len(f["text"]) <= 5]
    assert not kurz, _paare(funde)
    assert not [t for t in muster.finde_kreditkarte(text) if len(t) <= 5]
    if ohne_fund:
        assert funde == [], _paare(funde)


# ----------------------------------------------------------------------
# Scans: OCR-Text (synthetische Seite) und Formularfeld
# ----------------------------------------------------------------------
_SCAN = [
    "Ihre eVB-Nummer lautet: K7H3M9P",
    "eVB: LOO117Q",
    "Transferticket: TT0815AB4711",
    "Versicherungsnehmerin: Anna Weber geb. Schulz",
    "WEBER, ANNA GEB. SCHULZ",
    "Kreditkarte 4111 1111 1111 1111",
    "CVC: 1O3",
    "TÜV-Prüfnummer 123",
]


def test_kennungen_auf_ocr_text():
    funde = analyse._analysiere_dokument(_ocr_dok(_SCAN), ALLE, [], [])
    paare = _paare(funde)
    for wert in ("K7H3M9P", "LOO117Q", "TT0815AB4711"):
        assert ("vertrag", wert) in paare, paare
    ersatz = _ersatz(funde)
    assert ersatz["Schulz"] == ersatz["Anna Weber"], ersatz
    assert ("kreditkarte", "1O3") in paare, paare                   # OCR: O statt 0 in der Prüfnummer
    assert not any(k == "kreditkarte" and "123" in t for k, t in paare), paare


def test_evb_im_formularfeld(tmp_path):
    """Formularfeld neben dem gedruckten Etikett; der Wert hat nur eine Ziffer (keine allgemeine Kennungsform)."""
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((50, 100), "eVB-Nummer:", fontsize=10)
    w = fitz.Widget()
    w.field_name, w.field_type = "evb", fitz.PDF_WIDGET_TYPE_TEXT
    w.rect, w.field_value = fitz.Rect(150, 88, 300, 106), "KXH4PMQ"
    seite.add_widget(w)
    pdf = tmp_path / "evb_formular.pdf"
    doc.save(pdf)
    doc.close()
    e = analysiere_pdf(pdf, ALLE, [], [])
    assert e["fehler"] is None
    assert ("vertrag", "KXH4PMQ") in _paare(e["funde"]), _paare(e["funde"])


def _tabellen_pdf(pfad, kopf, zeilen):
    """Tabelle auf der Textebene: Spalten bei x = 60, 220, 380 (breite Lücken -> Zellen im Seitenmodell)."""
    doc = fitz.open()
    seite = doc.new_page()
    for zi, zeile in enumerate([kopf] + zeilen):
        for si, zelle in enumerate(zeile):
            seite.insert_text((60 + 160 * si, 100 + 18 * zi), zelle, fontsize=10, fontname="helv")
    doc.save(pfad)
    doc.close()
    return Path(pfad)


def test_kennungen_in_tabellenspalten(tmp_path):
    """Spaltenkopf mit dem Etikett, Werte in den Zeilen darunter – auch mit nur einer Ziffer bzw. drei Ziffern
    (keine allgemeine Kennungsform); die Selbstkontrolle meldet einen lesbar gebliebenen Wert in der Spalte."""
    pdf = _tabellen_pdf(tmp_path / "tabelle.pdf", ["Kennzeichen", "eVB-Nummer", "Kartenprüfnummer"],
                        [["M-AB 123", "KXH4PMQ", "123"], ["M-CD 456", "QWPZ7RT", "987"]])
    e = analysiere_pdf(pdf, ALLE, [], [])
    paare = _paare(e["funde"])
    for wert in ("KXH4PMQ", "QWPZ7RT"):
        assert ("vertrag", wert) in paare, paare
    for wert in ("123", "987"):
        assert ("kreditkarte", wert) in paare, paare
    verdacht = restrisiko_pruefen(pdf)
    texte = [v.text for v in verdacht]
    for wert in ("KXH4PMQ", "QWPZ7RT", "123", "987"):
        assert any(wert == t for t in texte), texte


@braucht_ocr
def test_kennungen_auf_einer_echten_scan_seite(tmp_path):
    """Echte Texterkennung (Tesseract): gedruckte Seite als Bild, dieselben Regeln wie auf der Textebene."""
    from anonymisierer.ocr import OcrDienst
    zeilen = ["Ihre eVB-Nummer lautet: K7H3M9P", "Transferticket: TT0815AB4711",
              "Versicherungsnehmerin: Anna Weber geb. Schulz", "Kreditkarte: 4111 1111 1111 1111",
              "Kartenprüfnummer: 789", "TÜV-Prüfnummer 123"]
    vorlage = fitz.open()
    s = vorlage.new_page()
    y = 90
    for z in zeilen:
        s.insert_text((60, y), z, fontsize=12, fontname="helv")
        y += 24
    pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    pdf = tmp_path / "scan_kennungen.pdf"
    doc.save(pdf)
    doc.close()
    vorlage.close()
    with OcrDienst(prozesse=1) as dienst:
        e = analysiere_pdf(pdf, ALLE, [], [], ocr=dienst)
    assert e["fehler"] is None and e["ocr_seiten"] == 1
    paare = _paare(e["funde"])
    # die genaue Lesart der eVB hängt vom Tesseract-Build ab ("K7H3M9P", "K7/H3MY9P", "K7H3MJ9P"): gefunden werden muss
    # sie in jeder dieser Lesarten (ocr_lesart: eVB mit eingefügten Zeichen)
    assert any(k == "vertrag" and _aehnlich(t, "K7H3M9P") for k, t in paare), paare
    assert ("vertrag", "TT0815AB4711") in paare, paare
    ersatz = _ersatz(e["funde"])
    assert ersatz.get("Schulz") == ersatz.get("Anna Weber") is not None, ersatz
    assert ("kreditkarte", "789") in paare, paare
    # nie eine Kartenprüfnummer; die Wissensbasis führt "TÜV-Prüfnummer" selbst als Kennungs-Etikett, auf Scans schwärzt
    # die Rohwert-Regel (struktur.ocr_rohwert) den Wert dahinter deshalb weiter vorsichtig als [VERTRAGS-NR]
    assert not any(k == "kreditkarte" and "123" in t for k, t in paare), paare


# ----------------------------------------------------------------------
# Selbstkontrolle (restrisiko.py): lesbarer Wert hinter einem der Etiketten ist Verdacht
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("eVB-Nummer: A1B2C3D", "A1B2C3D"),
    ("Ihre eVB lautet M3N4P5Q.", "M3N4P5Q"),
    ("eVB: ABC1DEF", "ABC1DEF"),
    ("eVB-Nummer\nM3N4P5Q", "M3N4P5Q"),
    ("Versicherungsbestätigung (eVB): KXHPMTQ", "KXHPMTQ"),
    ("EVB-NR. Q2W3E4R", "Q2W3E4R"),
    ("Transferticket: TTABCDEFGH12XY", "TTABCDEFGH12XY"),
    ("Transferticket\nTXQMKPLRSZ2WA9", "TXQMKPLRSZ2WA9"),
    ("[PERSON A] geb. Quarnstedt", "Quarnstedt"),
    ("[PERSON A] geborene Quarnstedt", "Quarnstedt"),
    ("[PERSON A], GEB. QUARNSTEDT", "QUARNSTEDT"),
    ("Frau [PERSON A] (geb. Quarnstedt-Ellerbrok)", "Quarnstedt-Ellerbrok"),
    ("[PERSON A] geb: Quarnstedt", "Quarnstedt"),
    ("CVC: 123", "123"),
    ("Kartennummer: [KREDITKARTE], CVC 123", "123"),
    ("Kreditkarte [KREDITKARTE]\nPrüfnummer: 456", "456"),
    ("Kartenprüfnummer: 789", "789"),
    ("CVV2: 0123", "0123"),
])
def test_restrisiko_wert_hinter_neuem_etikett(text, wert):
    assert _gemeldet(text, wert, platzhalter=["[PERSON A]", "[KREDITKARTE]"]), _verdacht(text)


@pytest.mark.parametrize("text", [
    "Bitte fordern Sie die eVB per E-Mail an.",
    "eVB-Nummer: [VERTRAGS-NR]",
    "Transferticket: [VERTRAGS-NR]",
    "Das Transferticket beantragen wir beim Vorversicherer.",
    "Die Gebr. Quarnstedt GmbH liefert das Fahrzeug.",
    "Geb. 3, Raum 214",
    "geb. am [GEB-DATUM] in [ORT]",
    "[PERSON A] geb. [PERSON A]",
    "TÜV-Prüfnummer 123",
    "Kreditkarte [KREDITKARTE]\nTÜV Prüfnummer 123",
    "Prüfnummer: 456",
    "Sicherheitscode: 123",
    "Die CVC steht auf der Rückseite der Karte.",
    "CVC: [KREDITKARTE]",
])
def test_restrisiko_gegenproben(text):
    assert _verdacht(text, platzhalter=["[PERSON A]", "[KREDITKARTE]"]) == []


@pytest.mark.parametrize("text, wort", [
    ("[PERSON A], geb. Od. Dez. 1973, wohnhaft in [ORT]", "Od"),      # OCR für "04. Dez. 1973"
    ("[PERSON A] geb. Mai 1980", "Mai"),
    ("[PERSON A] geb. Dez. 1973", "Dez"),
])
def test_restrisiko_kein_geburtsname_vor_einem_datum(text, wort):
    """Vor einem Datum ist das Wort hinter "geb." Monat oder Tag, kein Geburtsname (das Datum selbst bewerten die
    Datumsregeln)."""
    gruende = [v.grund for v in pruefe_text(text, platzhalter=["[PERSON A]", "[ORT]"]) if wort in v.text]
    assert not any("Geburtsname" in g for g in gruende), gruende


def test_restrisiko_auf_scan(tmp_path):
    pdf, woerter = _ocr_seite(tmp_path / "rest_scan.pdf", ["Ihre eVB lautet: LOO117Q", "Kartenprüfnummer: 789",
                                                           "Mutter: Erika, geb. Quarnstedt"])
    verdacht = restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"})
    texte = [v.text for v in verdacht]
    for wert in ("LOO117Q", "789", "Quarnstedt"):
        assert any(wert in t for t in texte), texte


def test_verpasste_evb_macht_die_ausgabe_pruefen(tmp_path):
    """Ende zu Ende: sieht die Erkennung nur die IBAN, bleibt die eVB lesbar – die Selbstkontrolle meldet sie an der
    richtigen Stelle, die Ausgabe heißt _PRUEFEN."""
    pdf = _text_pdf(tmp_path / "evb.pdf", ["Sehr geehrte Damen und Herren,",
                                           "Ihre eVB-Nummer lautet K7H3M9P.",
                                           "IBAN DE89 3704 0044 0532 0130 00", "Mit freundlichen Grüßen"])
    a = analysiere_pdf(pdf, {"iban"}, [], [], ocr=OcrAttrappe())
    assert a["fehler"] is None and [f["kategorie"] for f in a["funde"]] == ["iban"]
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / "aus")
    assert e["fehler"] is None and e["status"] == "pruefen", e["verdacht"]
    v = [x for x in e["verdacht"] if x.text == "K7H3M9P"]
    assert v and v[0].seite == 0, e["verdacht"]


def test_alle_vier_werden_geschwaerzt(tmp_path):
    """Ende zu Ende mit allen Kategorien: in der Ausgabe steht keiner der Werte mehr, und die Selbstkontrolle meldet
    keinen davon."""
    werte = ["K7H3M9P", "TT0815AB4711", "Schulz", "789"]
    pdf = _text_pdf(tmp_path / "alle.pdf", ["Versicherungsnehmerin: Anna Weber geb. Schulz",
                                            "eVB-Nummer: K7H3M9P", "Transferticket: TT0815AB4711",
                                            "Kartenprüfnummer: 789"])
    a = analysiere_pdf(pdf, ALLE, [], [], ocr=OcrAttrappe())
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / "aus")
    assert e["fehler"] is None
    with fitz.open(e["ausgabe"]) as doc:
        ausgabe = "\n".join(s.get_text() for s in doc)
    for wert in werte:
        assert wert not in ausgabe, ausgabe
        assert not any(wert in v.text for v in e["verdacht"]), e["verdacht"]


# ======================================================================
# Gegenprüfung der Runde 4: Befunde des Prüfers (Etikett-Varianten, Wörter statt Kennungen, Weitergabe kurzer
# Kartenprüfnummern, OCR-Einfügungen auf Scans, Geburtsname)
# ======================================================================
def _aehnlich(text: str, wert: str, mindestens: float = 0.75) -> bool:
    """Gleicht `text` ohne Trennzeichen dem Wert (OCR-Lesart mit eingefügten oder verwechselten Zeichen)?"""
    from difflib import SequenceMatcher
    kern = "".join(c for c in text if c.isalnum())
    return SequenceMatcher(None, kern, wert).ratio() >= mindestens


def _scan_pdf(pfad, zeilen, dpi=200):
    """Gedruckte Zeilen (Helvetica 12 pt) als Bild-Seite: ein echter Scan für Tesseract."""
    vorlage = fitz.open()
    s = vorlage.new_page()
    for i, z in enumerate(zeilen):
        s.insert_text((60, 90 + 24 * i), z, fontsize=12, fontname="helv")
    pix = s.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    doc.save(pfad)
    doc.close()
    vorlage.close()
    return Path(pfad)


# --- Befund 1: naheliegende Etikett-Varianten – bisher weder Fund noch Verdacht (stilles Leck)
@pytest.mark.parametrize("text, wert", [
    ("CVC-Code: 987", "987"),
    ("CVV-Code: 987", "987"),
    ("CVC/CVV-Code: 987", "987"),
    ("CVC-Prüfnummer: 123", "123"),
    ("CVC Code 123", "123"),
    ("Mastercard 5555 5555 5555 4444, CVC-Code: 987", "987"),
    ("Kartensicherheitscode: 456", "456"),
    ("Kreditkarte: 4111 1111 1111 1111\nSicherheitscode auf der Kartenrückseite: 123", "123"),
    ("Die Prüfnummer, die Sie auf der Rückseite Ihrer Kreditkarte finden, lautet 123.", "123"),
])
def test_cvc_etikett_varianten(text, wert):
    funde = analysiere_text(text, ALLE, [], [])
    assert ("kreditkarte", wert) in _paare(funde), _paare(funde)
    assert _gemeldet(text, wert), _verdacht(text)


@pytest.mark.parametrize("text, wert", [
    ("Ihre eVB-Nummer für die Zulassung lautet: K7H3M9P", "K7H3M9P"),
    ("Die eVB-Nummer für Ihr neues Fahrzeug lautet K7H3M9P.", "K7H3M9P"),
    ("eVB-Nummer zur Vorlage bei der Zulassungsstelle: K7H3M9P", "K7H3M9P"),
    ("Ihre eVB-Nr. lautend auf K7H3M9P", "K7H3M9P"),
    ("Die Versicherungsbestätigung für Ihr Fahrzeug lautet B9C8D7E.", "B9C8D7E"),
    ("Das Transferticket für den Wechsel lautet TT0815AB4711.", "TT0815AB4711"),
    ("Ihr Transferticket zur Übertragung des Schadenfreiheitsrabatts: TT0815AB4711", "TT0815AB4711"),
    ("eVB-Nummer vom 12.03.2025: K7H3M9P", "K7H3M9P"),
    ("Ihre Versicherungsbestätigung vom 01.02.2024: K7H3M9P", "K7H3M9P"),
    ("Die eVB-Nummer, die Sie für die Zulassung brauchen, lautet K7H3M9P.", "K7H3M9P"),
    ("Transferticket vom 01.02.2024: TT0815AB4711", "TT0815AB4711"),
])
def test_kennung_hinter_zwischenwoertern(text, wert):
    """Zwischen Etikett und Wert stehen Wörter, auch ein Datum oder ein Relativsatz mit Kommas, die mit einer
    Ankündigung enden ("… lautet", "…:")."""
    funde = analysiere_text(text, ALLE, [], [])
    assert ("vertrag", wert) in _paare(funde), _paare(funde)
    assert _gemeldet(text, wert), _verdacht(text)


@pytest.mark.parametrize("text", [
    "eVB-Nummer erhalten Sie unter: 0800 1234567",
    "Die eVB ist für 7 Tage gültig.",
    "Die eVB-Nummer ist bei Ihrer Zulassungsstelle hinterlegt. Bitte bringen Sie mit: Ausweis",
    "Zahlungsart: Kreditkarte\nPrüfnummer der HU: 123",
    "Zahlungsart: Kreditkarte\nSicherheitscode für Ihr Online-Postfach: 123",
    "Die eVB, das Transferticket und die Vollmacht: per Post",
    "Zahlungsart: Kreditkarte\nPrüfnummer, die Sie im Gutachten finden: 4711",
])
def test_zwischenwoerter_gegenproben(text):
    funde = analysiere_text(text, ALLE, [], [])
    kurz = [t for k, t in _paare(funde) if k in ("vertrag", "kreditkarte") and len(t) <= 12]
    assert not kurz, _paare(funde)
    assert not [v for v in pruefe_text(text) if "eVB" in v.grund or "Kartenprüf" in v.grund], _verdacht(text)


# --- Befund 2: Wörter in Versalien und Zahlen der Folgezeile sind keine eVB/Transferticket/Kartenprüfnummer
@pytest.mark.parametrize("text", [
    "eVB: ERTEILT",
    "eVB-Nummer: ANFRAGE",
    "Status eVB: ERFOLGT",
    "Die eVB ist ERTEILT.",
    "eVB DEUTSCH",
    "Versicherungsbestätigung ALLIANZ Versicherungs-AG",
    "Ihre Versicherungsbestätigung GOTHAER Allgemeine Versicherung AG",
    "Versicherungsbestätigung\nGOTHAER Allgemeine Versicherung AG",
    "Wir senden Ihnen die Versicherungsbestätigung\nANLAGEN: Antrag, Vollmacht",
    "Transferticket: ANGEFORDERT",
    "Transferticket: VORHANDEN",
    "Transfer-Ticket: ERHALTEN",
    "Transferticket BERLIN-TEGEL",
    "Transferticket: SF-KLASSE",
    "Für die Zulassung benötigen Sie die eVB.\nWICHTIG: Die Zulassungsstelle prüft die Unterlagen.",
    "Bitte fordern Sie bei uns die eVB\nACHTUNG: Die Frist beträgt 14 Tage.",
    "Ihr bisheriger Versicherer erstellt das Transferticket\nBEITRAGSRECHNUNG für das Jahr 2025",
    "Wir benötigen noch das Transferticket\nKFZ-HAFTPFLICHT und Vollkasko",
])
def test_kein_wort_als_kennung(text):
    funde = analysiere_text(text, ALLE, [], [])
    assert not [f["text"] for f in funde if f["kategorie"] == "vertrag"], _paare(funde)
    assert _verdacht(text) == []


@pytest.mark.parametrize("text, wert", [
    ("eVB-Nummer: QWPZXRT", "QWPZXRT"),
    ("Ihre eVB lautet BXKTMWQ.", "BXKTMWQ"),
    ("eVB: KXHAPMQ", "KXHAPMQ"),
])
def test_evb_ohne_ziffer_bleibt_ein_code(text, wert):
    """Gegenstück: ein Code ohne Ziffer, der kein Wort ist, bleibt eine eVB (Fund und Verdacht)."""
    funde = analysiere_text(text, ALLE, [], [])
    assert ("vertrag", wert) in _paare(funde), _paare(funde)
    assert _gemeldet(text, wert), _verdacht(text)


@pytest.mark.parametrize("text, zahl", [
    ("Bitte geben Sie im Online-Portal die CVC\n1500 EUR Selbstbeteiligung gelten weiter.", "1500"),
    ("Die Zahlung erfolgt per Kreditkarte, bitte nennen Sie keine CVC\n2024 wurde der Vertrag umgestellt.", "2024"),
    ("CVC:\n2024 wurde der Vertrag geschlossen.", "2024"),
    ("Kartenprüfnummer:\n8001 Zürich", "8001"),
    ("Kreditkarte: Visa\nPrüfnummer\n2024 erneuert", "2024"),
])
def test_keine_zahl_der_folgezeile_als_kartenpruefnummer(text, zahl):
    funde = analysiere_text(text, ALLE, [], [])
    assert ("kreditkarte", zahl) not in _paare(funde), _paare(funde)
    assert not [v for v in pruefe_text(text) if "Kartenprüf" in v.grund], _verdacht(text)


@pytest.mark.parametrize("text, zahl", [
    ("Zahlungsart: Kreditkarte\nPrüfnummer (TÜV): 123", "123"),
    ("Kreditkarte 4111 1111 1111 1111\nZulassung, Prüfnummer 1234", "1234"),
])
def test_pruefnummer_mit_fremdem_bezug(text, zahl):
    """Das Bezugswort steht in Klammern hinter "Prüfnummer" oder mit Komma davor: keine Kartenprüfnummer."""
    funde = analysiere_text(text, ALLE, [], [])
    assert ("kreditkarte", zahl) not in _paare(funde), _paare(funde)
    assert not [v for v in pruefe_text(text, platzhalter=["[KREDITKARTE]"]) if v.text == zahl], _verdacht(text)


def test_status_woerter_unter_kennungs_koepfen(tmp_path):
    """Tabelle mit eVB-Nummer und Transferticket im Kopf: Statuswörter in den Zellen darunter sind keine Kennung."""
    pdf = _tabellen_pdf(tmp_path / "status.pdf", ["Kennzeichen", "eVB-Nummer", "Transferticket"],
                        [["M-AB 123", "ERTEILT", "ANGEFORDERT"], ["M-CD 456", "OFFEN", "VORHANDEN"]])
    e = analysiere_pdf(pdf, ALLE, [], [])
    woerter = {"ERTEILT", "ANGEFORDERT", "OFFEN", "VORHANDEN"}
    assert not [t for _, t in _paare(e["funde"]) if t in woerter], _paare(e["funde"])
    assert not [v.text for v in restrisiko_pruefen(pdf) if v.text in woerter]


# --- Befund 3: eine kurze Kartenprüfnummer wandert nicht auf Beträge, Seitenzahlen und in andere Dokumente
def test_kartenpruefnummer_nicht_auf_andere_zahlen_weitergegeben():
    text = "CVC: 250\nBeitrag 1.250,00 EUR\nBetrag 250,00 EUR\nSeite 2 von 250\nTarif 250 Plus"
    funde = [f for f in analysiere_text(text, ALLE, [], []) if f["kategorie"] == "kreditkarte"]
    assert len(funde) == 1, funde
    an = [st for st in funde[0]["stellen"] if st.get("an", True)]
    assert [(st["start"], st["text"]) for st in an] == [(5, "250")], funde
    # die übrigen Vorkommen sind als abgewählte Stellen mit Grund bekannt: die Selbstkontrolle meldet sie nicht als Rest
    ab = [st for st in funde[0]["stellen"] if not st.get("an", True)]
    assert len(ab) == 4 and all(st.get("grund") for st in ab), ab


def test_kartenpruefnummer_im_lauf(tmp_path):
    """Lauf mit zwei Dokumenten: die Kartenprüfnummer aus A wird weder in A (Selbstbeteiligung) noch in B (Hausrat-
    Police ohne Karte) auf gleiche Zahlen übertragen, und die Selbstkontrolle meldet sie dort nicht als Rest."""
    a = _text_pdf(tmp_path / "a.pdf", ["Zahlung per Kreditkarte 4111 1111 1111 1111", "Kartenprüfnummer: 250",
                                       "Selbstbeteiligung 250 EUR je Schadenfall"])
    b = _text_pdf(tmp_path / "b.pdf", ["Versicherungsschein Hausrat", "Selbstbeteiligung: 250 EUR",
                                       "Versicherungssumme 65.000 EUR, Wohnfläche 250 qm"])
    ea, eb = analysiere_pdf(a, ALLE, [], [], ocr=OcrAttrappe()), analysiere_pdf(b, ALLE, [], [], ocr=OcrAttrappe())
    analyse.weitergabe_anwenden([ea, eb])
    assert not [f for f in eb["funde"] if f["kategorie"] == "kreditkarte"], eb["funde"]
    ra = schwaerze_pdf(a, ea["funde"], modell=ea["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / "aus_a")
    rb = schwaerze_pdf(b, eb["funde"], modell=eb["modell"], ocr=OcrAttrappe(), ziel_ordner=tmp_path / "aus_b")
    with fitz.open(ra["ausgabe"]) as d:
        text_a = d[0].get_text()
    with fitz.open(rb["ausgabe"]) as d:
        text_b = d[0].get_text()
    assert "Selbstbeteiligung 250 EUR" in text_a and "Kartenprüfnummer: 250" not in text_a, text_a
    assert "250 EUR" in text_b and "250 qm" in text_b, text_b
    assert ra["reste"] == [] and rb["reste"] == [], (ra["reste"], rb["reste"])


# --- Befund 4: eVB auf Scans mit eingefügten Zeichen (Tesseract liest die Helvetica-„7“/„9“ gern als "7/", "/",
# "J9", "IJ"); Selbstkontrolle mit Umlautverlust
@pytest.mark.parametrize("zeile, wert", [
    ("Ihre eVB-Nummer lautet: K7/H3MY9P", "K7/H3MY9P"),
    ("eVB-Nummer: /RT4ZU9", "/RT4ZU9"),
    ("Ihre eVB-Nummer lautet: K7H3MJ9P", "K7H3MJ9P"),
    ("Versicherungsbestätigungsnummer: BIJC8D7E", "BIJC8D7E"),
    ("eVB: M3NA4P5Q", "M3NA4P5Q"),
    ("eV8-Nummer: K7H3M9P", "K7H3M9P"),                     # "B" im Etikett als "8" gelesen
])
def test_evb_mit_ocr_einfuegung(zeile, wert):
    funde = analyse._analysiere_dokument(_ocr_dok([zeile]), ALLE, [], [])
    assert ("vertrag", wert) in _paare(funde), _paare(funde)


@pytest.mark.parametrize("zeile", [
    "eVB gültig bis 12/2025",
    "eVB-Nummer: siehe Anlage",
    "Ihre eVB-Nummer lautet: ANFRAGE/OFFEN",
    "eVB-Nummer: 12/2025",
])
def test_evb_ocr_gegenproben(zeile):
    funde = analyse._analysiere_dokument(_ocr_dok([zeile]), ALLE, [], [])
    assert not [t for k, t in _paare(funde) if k == "vertrag"], _paare(funde)


@pytest.mark.parametrize("text, wert", [
    ("Ihre eVB-Nummer lautet: K7/H3MY9P", "K7/H3MY9P"),
    ("Ihre eVB-Nummer lautet: /RT4ZU9", "RT4ZU9"),
    ("Ihre eVB-Nummer lautet: K7H3MJ9P", "K7H3MJ9P"),
    ("Kartenprufnummer: 789", "789"),
    ("Versicherungsbestatigung: K7H3M9P", "K7H3M9P"),
    ("Versicherungsbestaetigungsnummer: K7H3M9P", "K7H3M9P"),
    ("eV8-Nummer: K7H3M9P", "K7H3M9P"),
])
def test_selbstkontrolle_ocr_tolerant(text, wert):
    assert _gemeldet(text, wert), _verdacht(text)


@braucht_ocr
@pytest.mark.parametrize("wert", ["K7H3M9P", "7RT4ZU9"])
def test_evb_im_scan_brief_kein_stilles_leck(tmp_path, wert):
    """Echter Scan (Tesseract, 200 dpi), Briefanfang mit eVB-Zeile: die eVB wird geschwärzt; und ohne Erkennung (nur
    IBAN aktiv) meldet die Selbstkontrolle sie, die Ausgabe heißt _PRUEFEN – nie „fertig“ mit lesbarer eVB."""
    from anonymisierer.ocr import OcrDienst
    pdf = _scan_pdf(tmp_path / "brief.pdf", ["Sehr geehrte Damen und Herren,", f"Ihre eVB-Nummer lautet: {wert}",
                                             "Mit freundlichen Grüßen"])
    with OcrDienst(prozesse=1) as dienst:
        a = analysiere_pdf(pdf, ALLE, [], [], ocr=dienst)
        a2 = analysiere_pdf(pdf, {"iban"}, [], [], ocr=dienst)
        e2 = schwaerze_pdf(pdf, a2["funde"], modell=a2["modell"], ocr=dienst, ziel_ordner=tmp_path / "aus2")
    assert a["fehler"] is None and e2["fehler"] is None
    assert [f["text"] for f in a["funde"] if f["kategorie"] == "vertrag" and _aehnlich(f["text"], wert)], \
        _paare(a["funde"])
    assert e2["status"] == "pruefen" and [v for v in e2["verdacht"] if _aehnlich(v.text, wert)], e2["verdacht"]


# --- Geburtsname (Befunde niedrig): dieselbe Person bekommt denselben Platzhalter; Sachwörter sind kein Geburtsname
@pytest.mark.parametrize("text, person, geburtsname", [
    ("Weber, Anna geb. Schulz", "Weber, Anna", "Schulz"),
    ("Frau Weber geb. Schulz hat angerufen.", "Weber", "Schulz"),
    ("Anna Weber\ngeb. Schulz", "Anna Weber", "Schulz"),
    ("Anna Weber geb.Schulz", "Anna Weber", "Schulz"),
    ("Anna Weber geb.: Schulz", "Anna Weber", "Schulz"),
    ("Versicherungsnehmerin: Anna Weber geb. Garcia Lopez, Hauptstraße 5", "Anna Weber", "Garcia Lopez"),
    ("Maria Schmidt geb. da Silva Santos wohnt in Köln.", "Maria Schmidt", "da Silva Santos"),
    ("Kontoinhaberin: Fatma Yilmaz geb. Öztürk Demir", "Fatma Yilmaz", "Öztürk Demir"),
    ("Anna Weber geb. Mac Allister hat angerufen.", "Anna Weber", "Mac Allister"),
    ("WEBER, ANNA GEB. GARCIA LOPEZ", "WEBER, ANNA", "GARCIA LOPEZ"),
])
def test_geburtsname_gleicher_platzhalter(text, person, geburtsname):
    ersatz = _ersatz(analysiere_text(text, {"namen"}, [], []))
    assert ersatz.get(geburtsname) == ersatz.get(person) is not None, ersatz


@pytest.mark.parametrize("text, wort", [
    ("Anna Weber geb. Hamburg", "Hamburg"),
    ("Weber geb. Unbekannt", "Unbekannt"),
    ("Geburtsname: Siehe oben", "Siehe"),
])
def test_geburtsname_kein_sachwort(text, wort):
    funde = analysiere_text(text, {"namen"}, [], [])
    assert not any(wort in t.split() for t in _stellen(funde, "namen")), _paare(funde)


@pytest.mark.parametrize("text, wort", [
    ("# NACHNAME\t\tVORN.\t\tGEB.DAT.\t\tSTRASSE\t\tVN_PLZ", "DAT"),     # Spaltenkopf einer Bestandsliste
    ("NAME\t\tVORNAME\t\tGEB. DAT.\t\tGEB. ORT", "DAT"),
    ("Anna Weber, geb. Datum unbekannt", "Datum"),
    ("Frau Weber geb.Tag", "Tag"),
])
def test_geburtsdatum_kuerzel_ist_kein_geburtsname(text, wort):
    """Kürzel eines Geburtsdatums (auch direkt an "geb." geschrieben: "GEB.DAT.", "geb.Tag") sind kein Geburtsname –
    aus der Messung der Runde 4 (s3x, Bestandsliste): "GEB.DAT." im Spaltenkopf wurde zum Namen "DAT"."""
    funde = analysiere_text(text, {"namen"}, [], [])
    assert not any(wort in t.split() for t in _stellen(funde, "namen")), _paare(funde)


@pytest.mark.parametrize("text", ["geb. Ledig", "Familienstand: geb. Ledig", "Weber geb. Unbekannt",
                                  "[PERSON A] geb. Hamburg", "# NACHNAME\t\tVORN.\t\tGEB.DAT.\t\tSTRASSE",
                                  "[PERSON A] geb.Tag"])
def test_restrisiko_kein_geburtsname_aus_sachwort(text):
    assert not [v for v in pruefe_text(text, platzhalter=["[PERSON A]"]) if "Geburtsname" in v.grund]


def _codes(ergebnis) -> list:
    return [m["code"] for m in ergebnis.get("meldungen") or []]


def test_geburtsname_auf_scan_ist_kein_schluesselwort_ohne_fund(tmp_path):
    """Auf einem Scan steht "geb." vor einem geschwärzten Geburtsnamen: kein Etikett eines Geburtsdatums, also keine
    Warnung SCHLUESSELWORT_OHNE_FUND. Gegenprobe: ein ungeschwärztes Geburtsdatum hinter "geb. am" bleibt ein Grund."""
    pdf, woerter = _ocr_seite(tmp_path / "geb.pdf", ["Sehr geehrte Damen und Herren,",
                                                     "Versicherungsnehmerin: Anna Weber geb. Quarnstedt",
                                                     "Wir bestätigen den Eingang Ihres Antrags."])
    dienst = OcrAttrappe({0: woerter})
    a = analysiere_pdf(pdf, ALLE, [], [], ocr=dienst)
    assert "Quarnstedt" in _stellen(a["funde"], "namen"), _paare(a["funde"])
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=dienst, ziel_ordner=tmp_path / "aus")
    assert e["fehler"] is None and "SCHLUESSELWORT_OHNE_FUND" not in _codes(e), e["warnungen"]
    pdf2, woerter2 = _ocr_seite(tmp_path / "geb2.pdf", ["Versicherungsnehmerin: Anna Weber geb. am 12.03.1980"])
    dienst2 = OcrAttrappe({0: woerter2})
    a2 = analysiere_pdf(pdf2, {"namen"}, [], [], ocr=dienst2)
    e2 = schwaerze_pdf(pdf2, a2["funde"], modell=a2["modell"], ocr=dienst2, ziel_ordner=tmp_path / "aus2")
    assert "SCHLUESSELWORT_OHNE_FUND" in _codes(e2) and e2["status"] == "pruefen", e2["warnungen"]
