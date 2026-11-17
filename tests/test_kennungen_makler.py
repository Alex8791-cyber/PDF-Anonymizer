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
    assert ("vertrag", "K7H3M9P") in paare and ("vertrag", "TT0815AB4711") in paare, paare
    ersatz = _ersatz(e["funde"])
    assert ersatz.get("Schulz") == ersatz.get("Anna Weber") is not None, ersatz
    assert ("kreditkarte", "789") in paare, paare
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
