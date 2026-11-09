"""Tests der Strukturregeln (anonymisierer/detektoren/struktur*.py): Etikett + Wert, Tabellen, Formular-
felder, Anschriften (Kunde oder Organisation), Anrede/Gruß, Betreff, Ort-Datum, Kopf-/Fußzeilen.

Geometrie wird mit kleinen PDFs (fitz) geprüft, reine Textregeln mit seitenmodell.dokument_aus_text.
Zu jeder Regel gibt es Gegenproben: Vertragsdaten, Beträge, Spaltenköpfe, Anschriften von Versicherern
bleiben stehen."""

import time

import pytest

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

from anonymisierer import detektoren, seitenmodell
from anonymisierer.detektoren import Kontext
from anonymisierer.detektoren import struktur as st
from anonymisierer.muster import KATEGORIEN

ALLE = {k[0] for k in KATEGORIEN if k[4]}


# ----------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------
def _pdf(pfad, seiten, quer=False, felder=()):
    """seiten: je Seite eine Liste (x, y, text[, groesse]); felder: (seite, rect, name, wert, etikett_xy)."""
    doc = fitz.open()
    for inhalt in seiten:
        seite = doc.new_page(width=842 if quer else 595, height=595 if quer else 842)
        for eintrag in inhalt:
            x, y, text = eintrag[:3]
            groesse = eintrag[3] if len(eintrag) > 3 else 9
            seite.insert_text((x, y), text, fontsize=groesse, fontname="helv")
    for nr, rect, name, wert in felder:
        w = fitz.Widget()
        w.field_name, w.field_type = name, fitz.PDF_WIDGET_TYPE_TEXT
        w.rect, w.field_value = fitz.Rect(rect), wert
        w.text_fontsize = 10
        doc[nr].add_widget(w)
    doc.save(pfad)
    doc.close()
    return pfad


def _modell(pfad):
    doc = fitz.open(pfad)
    vorbereitung = seitenmodell.dokument_vorbereiten(doc)
    return seitenmodell.dokument_aufbauen(vorbereitung.get("dokument") or doc, pfad, vorbereitung=vorbereitung)


def _detektor(name):
    return next(e for e in detektoren.REGISTER if e.name == name).funktion


def _treffer(dok, name, aktive=None):
    kontext = Kontext(aktive or ALLE, "hoch")
    return [(t.kategorie, dok.text[t.start:t.ende]) for t in _detektor(name)(dok, kontext)]


def _texte(dok, name, kategorie=None):
    return {t for k, t in _treffer(dok, name) if kategorie is None or k == kategorie}


def _text(text, name):
    return _treffer(seitenmodell.dokument_aus_text(text), name)


# ----------------------------------------------------------------------
# Register
# ----------------------------------------------------------------------
def test_strukturdetektoren_registriert_und_muster_umhuellt():
    namen = {e.name for e in detektoren.REGISTER}
    assert {"struktur.etikett_wert", "struktur.tabelle", "struktur.formularfeld", "struktur.adressblock",
            "struktur.anrede_gruss", "struktur.betreff", "struktur.ort_datum", "struktur.kopf_fuss"} <= namen
    for name in ("muster.strasse", "muster.plzort"):
        eintrag = next(e for e in detektoren.REGISTER if e.name == name)
        assert eintrag.funktion.__name__.endswith("_ohne_firmen")
    assert not detektoren.LADEFEHLER


# ----------------------------------------------------------------------
# Wertformen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text,erwartet", [
    ("47.897.336.2 – fehlende Angaben", "47.897.336.2"),
    ("KH 0815 4471 2", "KH 0815 4471 2"),
    ("7 111 562 795\t31.03.2025", "7 111 562 795"),
    ("D-Y3TV-NW64X-52 (§ 34d Abs. 1 GewO)", "D-Y3TV-NW64X-52"),
    ("LV/24/4058468.", "LV/24/4058468"),
    ("HR-2022-251237", "HR-2022-251237"),
])
def test_kennung_spanne(text, erwartet):
    sp = st.kennung_spanne(text, 0, len(text))
    assert sp and text[sp[0]:sp[1]] == erwartet


@pytest.mark.parametrize("text", ["01.03.2019", "1.340,70 EUR", "2025", "fehlen uns noch", "§ 38 VVG", "19 %",
                                  "EUR 12"])
def test_kennung_spanne_gegenproben(text):
    assert st.kennung_spanne(text, 0, len(text)) is None


@pytest.mark.parametrize("wert,ja", [
    ("660/124641-9", True), ("SV926201774", True), ("2012860414", True), ("6 259 674 059", True),
    ("1.340,70", False), ("01.11.2032", False), ("78050", False), ("19 %", False), ("2025", False),
    ("PT 50", False), ("12:30", False),
])
def test_kennungsform_ohne_etikett(wert, ja):
    assert st.ist_kennungsform(wert) is ja


@pytest.mark.parametrize("text,erwartet", [
    ("Hahn, Annika", "Hahn, Annika"),
    ("STOJANOVIC, MIRELA", "STOJANOVIC, MIRELA"),
    ("van den Berg, Pieter", "van den Berg, Pieter"),
    ("FREIHERR VON ROTENSTEIN, CLARA", "FREIHERR VON ROTENSTEIN, CLARA"),
    ("GRAF, LISELOTTE", "GRAF, LISELOTTE"),
    ("Freitag, Jonas", "Freitag, Jonas"),
    ("Herr Dr. Max Graf", "Max Graf"),
    ("Dipl.-Ing. Erika Kovacs (Vorsitzende)", "Erika Kovacs"),
    ("Schulze, Dr. Anton", "Schulze, Dr. Anton"),
    ("V. De Luca", "V. De Luca"),
    ("al-Hassan, Omar", "al-Hassan, Omar"),
    ("El-Masri, Karim", "El-Masri, Karim"),
])
def test_namen_spanne(text, erwartet):
    sp = st.namen_spanne(text, 0, len(text))
    assert sp and text[sp.start:sp.ende] == erwartet


@pytest.mark.parametrize("text,erwartet", [
    ("Katarzyna Kowalski, Dipl.-Ing. Jörg Ziegler", "Katarzyna Kowalski"),
    ("Horst Biedermann, Liselotte Schmidt", "Horst Biedermann"),
    ("Biedermann, Liselotte Schmidt", "Biedermann"),
    ("Müller, Hans Peter", "Müller, Hans Peter"),
    ("Schmidt-Brandt, Anna Lena", "Schmidt-Brandt, Anna Lena"),
])
def test_namen_spanne_aufzaehlungskomma(text, erwartet):
    """Ein Komma zwischen "Vorname Nachname"-Paaren zählt Personen auf; "Nachname, Vorname(n)" bleibt."""
    sp = st.namen_spanne(text, 0, len(text))
    assert sp and text[sp.start:sp.ende] == erwartet


def test_gremium_aufzaehlung_ergibt_einzelne_namen():
    dok = seitenmodell.dokument_aus_text("Vorstand: Katarzyna Kowalski, Dipl.-Ing. Jörg Ziegler, Ursula Frank")
    namen = [w for k, w in _treffer(dok, "struktur.etikett_wert") if k == "namen"]
    assert namen == ["Katarzyna Kowalski", "Jörg Ziegler", "Ursula Frank"]


@pytest.mark.parametrize("text", ["Sehr geehrte Damen", "Montag", "Kundenservice", "Versicherte Person",
                                  "Allianz Versicherungs-AG", "Ihr Beitragsservice", "LeaFR", "ERS"])
def test_namen_spanne_gegenproben(text):
    sp = st.namen_spanne(text, 0, len(text))
    assert sp is None or text[sp.start:sp.ende] not in ("Damen", "Montag", "Kundenservice", "Versicherte",
                                                         "Allianz", "Ihr", "LeaFR", "ERS")


def test_name_in_firmenbezeichnung_ist_ein_name():
    """"Kurt & Partner GmbH", "Werkstatt Becker": der Personenname im Firmennamen ist ein Name, die
    Rechtsform nicht; Organisationen der Erlaubnisliste bleiben."""
    for text, name in (("Kurt & Partner GmbH", "Kurt"), ("Müller GmbH", "Müller")):
        sp = st.namen_spanne(text, 0, len(text))
        assert sp and text[sp.start:sp.ende] == name
    assert st.namen_spanne("Allianz SE", 0, 10) is None


# ----------------------------------------------------------------------
# Etikett + Wert (reiner Text)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text,kategorie,wert", [
    ("Kundennummer: 4711-0815", "vertrag", "4711-0815"),
    ("Versicherungsnummer\tLV-2024-887766\tBeginn 01.10.2024", "vertrag", "LV-2024-887766"),
    ("Kunden-Nr. ........ KD 4711-0815", "vertrag", "KD 4711-0815"),
    ("Auszahlung aus Ihrem Vertrag 47.897.336.2 – fehlende Angaben", "vertrag", "47.897.336.2"),
    ("Registrierungsnummer D-Y3TV-NW64X-52 (§ 34d Abs. 1 GewO)", "vertrag", "D-Y3TV-NW64X-52"),
    ("IHK-Registernummer: D-ABCD-12345-67", "vertrag", "D-ABCD-12345-67"),
    ("Personalnummer: 0815-4711", "vertrag", "0815-4711"),
    ("Mitgliedsnummer 12 345 678", "vertrag", "12 345 678"),
    ("Geburtsdatum: 23. März 1973", "geburt", "23. März 1973"),
    ("Ort:\t\tFrankfurt am Main", "plzort", "Frankfurt am Main"),
    ("PLZ:\t\t60311", "plzort", "60311"),
    ("Straße, Hausnummer:\t\tKonrad-Adenauer-Platz 6", "strasse", "Konrad-Adenauer-Platz 6"),
    ("Anschrift:\t\tKleine Bergstraße 113, 57610 Altenkirchen (Westerwald)", "strasse", "Kleine Bergstraße 113"),
    ("Name, Vorname:\t\tStefanescu, Andreea", "namen", "Stefanescu, Andreea"),
    ("Kontoinhaber\t\tGyöri, Réka", "namen", "Györi, Réka"),
    ("Telefon:\t\t(069) 311 50 80", "telefon", "(069) 311 50 80"),
    ("E-Mail:\t\tm.muster@example.de", "email", "m.muster@example.de"),
    ("Steuer-ID:\t\t67084313926", "steuerid", "67084313926"),
    ("Amtl. Kennzeichen:\t\tHL V 591", "kfz", "HL V 591"),
])
def test_etikett_wert(text, kategorie, wert):
    assert (kategorie, wert) in _text(text, "struktur.etikett_wert")


def test_etikett_wert_gremium_liste():
    text = "Vorstand: Dipl.-Ing. Erika Kovacs (Vorsitzende), Ben Mayer, Anna-Lena Schmidt"
    namen = {w for k, w in _text(text, "struktur.etikett_wert") if k == "namen"}
    assert {"Erika Kovacs", "Ben Mayer", "Anna-Lena Schmidt"} <= namen


@pytest.mark.parametrize("text", [
    "Vertragsbeginn: 01.03.2019",
    "Ablauf:\t\t01.03.2044",
    "Beitrag (monatlich):\t\t395,91 EUR",
    "für die Auszahlung aus Ihrem Vertrag fehlen uns noch Angaben.",
    "Ihr Vertrag hat am 01.12.2015 begonnen.",
    "Kunde seit 2010",
    "Bankverbindung: Postbank Ndl. Mitte",
    "Sehr geehrte Damen und Herren,",
    "Versicherungsnehmer und versicherte Person sind identisch.",
    "Gläubiger-ID:\t\tDE70ZZZ03290639901",
])
def test_etikett_wert_gegenproben(text):
    assert _text(text, "struktur.etikett_wert") == []


def test_eq09_umbrochenes_etikett_ueber_tabellenzellen():
    """Gutachten EQ-09 (b): Kopfzelle "Versicherungsschein-", der Wert "Nr. KH 0815 4471 2" steht in der Zelle
    darunter; "Verhältnis zum VN: Mitbewohner" ist kein Personenfeld."""
    from pathlib import Path
    dok = _modell(Path(__file__).parent / "daten" / "c_schadenmeldung.pdf")
    werte = set(_treffer(dok, "struktur.tabelle")) | set(_treffer(dok, "struktur.etikett_wert"))
    assert ("vertrag", "KH 0815 4471 2") in werte
    assert ("namen", "Adeyemi, Olumide") in werte
    assert ("telefon", "0176 / 23 45 67 89") in werte
    assert not any(w == "Mitbewohner" for _, w in werte)


def test_etikett_wert_kennung_in_folgezeile():
    text = "Kündigung meiner Privathaftpflichtversicherung, Versicherungsschein-Nr.\nHR-2022-251237"
    assert ("vertrag", "HR-2022-251237") in _text(text, "struktur.etikett_wert")


# ----------------------------------------------------------------------
# Etikett über dem Wert (Informationsblock) – Geometrie
# ----------------------------------------------------------------------
def test_informationsblock_etikett_ueber_wert(tmp_path):
    pdf = _pdf(tmp_path / "info.pdf", [[
        (354, 140, "Kundennummer", 7), (354, 151, "51-633867", 9),
        (354, 165, "Ansprechpartnerin", 7), (354, 176, "Andrea Krause", 9),
        (354, 190, "Datum", 7), (354, 201, "19.06.2025", 9),
        (71, 140, "Frau", 10), (71, 153, "Noemie Bonnet", 10),
    ]])
    dok = _modell(pdf)
    werte = _treffer(dok, "struktur.etikett_wert")
    assert ("vertrag", "51-633867") in werte
    assert ("namen", "Andrea Krause") in werte
    assert not any(w == "19.06.2025" for _, w in werte), "Vertragsdatum bleibt"


# ----------------------------------------------------------------------
# Tabellen
# ----------------------------------------------------------------------
_KOEPFE = [(40, "Nr."), (58, "Kunde (Name, Vorname)"), (220, "Geb.-Datum"), (290, "PLZ / Ort"), (420, "Sparte"),
           (480, "Vertragsnummer"), (600, "Beitrag p.a."), (680, "Ablauf")]
_KUNDEN = [("Hahn, Annika", "14.03.1961", "78050 Villingen-Schwenningen", "Kfz", "2520868691"),
           ("Aßmann, Torsten", "14.11.93", "38440 Wolfsburg", "PKV", "LV-2018-933486"),
           ("Dubois, Hélène", "29.12.1969", "87435 Kempten (Allgäu)", "Unfall", "6 259 674 059"),
           ("SEIDEL, SUSANNE", "13.05.1984", "22880 Wedel", "BU", "828/225137-9"),
           ("van den Berg, Pieter", "07.03.1968", "91207 Lauf", "Leben", "KF923151122")]


def _bestandsliste(zeilen_je_seite=24, anzahl=30, kopf_auf_folgeseite=False, schraege=0.0, abstand=20):
    seiten, seite = [], []
    y = 70
    for x, t in _KOEPFE:
        seite.append((x, y + schraege * x, t, 7))
    for i in range(anzahl):
        if i and i % zeilen_je_seite == 0:
            seiten.append(seite)
            seite, y = [], 70
            if kopf_auf_folgeseite:
                for x, t in _KOEPFE:
                    seite.append((x, y + schraege * x, t, 7))
        y += abstand
        name, geb, ort, sparte, vnr = _KUNDEN[i % len(_KUNDEN)]
        if i >= len(_KUNDEN):
            vnr = f"LV-2020-{100000 + i}"
        for x, t in [(50 if i < 9 else 46, str(i + 1)), (58, name), (220, geb), (290, ort), (420, sparte),
                     (480, vnr), (610, "1.340,70"), (680, "01.11.2032")]:
            seite.append((x, y + schraege * x, t, 7))
    seiten.append(seite)
    return seiten


@pytest.mark.parametrize("kopf_auf_folgeseite", [False, True])
def test_tabelle_bestandsliste_mit_seitenumbruch(tmp_path, kopf_auf_folgeseite):
    dok = _modell(_pdf(tmp_path / "liste.pdf", _bestandsliste(kopf_auf_folgeseite=kopf_auf_folgeseite), quer=True))
    treffer = _treffer(dok, "struktur.tabelle")
    texte = {w for _, w in treffer}
    for name, geb, ort, _, vnr in _KUNDEN:
        assert ("namen", name) in treffer
        assert ("geburt", geb) in treffer
        assert ("vertrag", vnr) in treffer
        assert ort in texte
    # 30 Reihen auf zwei Seiten: die Werte der zweiten Seite sind dabei (eigene Vertragsnummern)
    for i in range(24, 30):
        assert ("vertrag", f"LV-2020-{100000 + i}") in treffer
    # Vertragsdaten, Beträge, Sparten und Köpfe bleiben
    for bleibt in ("01.11.2032", "1.340,70", "Kfz", "PKV", "Vertragsnummer", "Geb.-Datum", "Sparte"):
        assert bleibt not in texte


def test_tabelle_schraeger_scan(tmp_path):
    """Zeilen eines leicht schräg liegenden Scans: die Reihen liegen nicht auf gleicher Höhe."""
    dok = _modell(_pdf(tmp_path / "schraeg.pdf", _bestandsliste(anzahl=10, schraege=0.012, abstand=13), quer=True))
    treffer = _treffer(dok, "struktur.tabelle")
    assert ("vertrag", "6 259 674 059") in treffer
    assert ("geburt", "13.05.1984") in treffer
    assert ("namen", "Dubois, Hélène") in treffer


def test_tabelle_spalte_ohne_etikett_nur_mit_personenspalte(tmp_path):
    zeilen = [(72, 300, "Versicherte Person"), (230, 300, "Objekt"), (380, 300, "Beitrag")]
    ohne = [(72, 300, "Tarif"), (230, 300, "Objekt"), (380, 300, "Beitrag")]
    werte = [("Max Mustermann", "LV-2014-697971"), ("Erika Mustermann", "KV/35/5276751"),
             ("Paul Mustermann", "HR454253977"), ("Anna Mustermann", "2012860414")]
    for i, (name, nr) in enumerate(werte):
        y = 314 + 13 * i
        zeilen += [(72, y, name), (230, y, nr), (380, y, "238,02")]
        ohne += [(72, y, "Haus&Heim Komfort"), (230, y, nr), (380, y, "238,02")]
    dok = _modell(_pdf(tmp_path / "mit.pdf", [zeilen]))
    erwartet = {"LV-2014-697971", "KV/35/5276751", "HR454253977", "2012860414"}
    assert erwartet <= _texte(dok, "struktur.tabelle", "vertrag")
    dok = _modell(_pdf(tmp_path / "ohne.pdf", [ohne]))
    assert _texte(dok, "struktur.tabelle", "vertrag") == set()


def test_tabelle_kopf_entscheidet_ueber_daten(tmp_path):
    inhalt = [(72, 300, "Name"), (180, 300, "Vorname"), (280, 300, "Geburtsdatum"), (380, 300, "Rolle"),
              (72, 314, "von Schönau"), (180, 314, "Jakob"), (280, 314, "23.09.1993"), (380, 314, "versicherte Person"),
              (72, 327, "von Schönau"), (180, 327, "Ole"), (280, 327, "27.04.2009"), (380, 327, "mitversichertes Kind"),
              (72, 360, "Vertragsnummer"), (200, 360, "Beginn"), (300, 360, "Ablauf"),
              (72, 374, "KV-2019-385221"), (200, 374, "01.03.2019"), (300, 374, "01.03.2044")]
    dok = _modell(_pdf(tmp_path / "kopf.pdf", [inhalt]))
    treffer = _treffer(dok, "struktur.tabelle")
    assert ("geburt", "23.09.1993") in treffer and ("geburt", "27.04.2009") in treffer
    assert ("namen", "Jakob") in treffer and ("namen", "Ole") in treffer
    assert ("vertrag", "KV-2019-385221") in treffer
    texte = {w for _, w in treffer}
    assert "01.03.2019" not in texte and "01.03.2044" not in texte, "Vertragsdaten bleiben"
    assert not any("Person" in w or "Kind" in w for w in texte), "Rollen sind keine Namen"


def test_tabelle_kopf_ueber_zwei_zeilen_in_versalien(tmp_path):
    """Spaltenköpfe über zwei Zeilen ("PERSONAL-" / "NUMMER", "GEBURTS-" / "DATUM") und in Versalien."""
    inhalt = [(72, 300, "MITARBEITER"), (200, 300, "PERSONAL-"), (300, 300, "GEBURTS-"), (400, 300, "ABTEILUNG"),
              (200, 309, "NUMMER"), (300, 309, "DATUM"),
              (72, 324, "Weber, Jonas"), (200, 324, "P-004711"), (300, 324, "03.04.1981"), (400, 324, "Vertrieb"),
              (72, 337, "Kaya, Elif"), (200, 337, "P-008150"), (300, 337, "17.11.1990"), (400, 337, "Schaden")]
    dok = _modell(_pdf(tmp_path / "personal.pdf", [inhalt]))
    treffer = _treffer(dok, "struktur.tabelle")
    assert ("vertrag", "P-004711") in treffer and ("vertrag", "P-008150") in treffer
    assert ("geburt", "03.04.1981") in treffer and ("geburt", "17.11.1990") in treffer
    assert ("namen", "Weber, Jonas") in treffer and ("namen", "Kaya, Elif") in treffer
    assert not any(w in ("Vertrieb", "Schaden") for _, w in treffer)


def test_tabelle_leistungserbringer(tmp_path):
    """Leistungserbringer-Spalte: Ärzte und Namen in Firmenbezeichnungen sind Personen, Apotheken nicht."""
    inhalt = [(72, 300, "Person"), (130, 300, "Datum"), (200, 300, "Leistungserbringer"), (380, 300, "Betrag"),
              (72, 314, "Ida"), (130, 314, "12.09.2025"), (200, 314, "Physiotherapie Tran"), (380, 314, "847,38"),
              (72, 327, "Ida"), (130, 327, "13.08.2025"), (200, 327, "Dr. med. Erika Weber"), (380, 327, "1252,86"),
              (72, 340, "Ida"), (130, 340, "20.08.2025"), (200, 340, "Löwen-Apotheke"), (380, 340, "1625,27")]
    dok = _modell(_pdf(tmp_path / "leistung.pdf", [inhalt]))
    namen = _texte(dok, "struktur.tabelle", "namen")
    assert {"Tran", "Erika Weber", "Ida"} <= namen
    assert not any("Apotheke" in n or "Physiotherapie" in n for n in namen)
    assert not _texte(dok, "struktur.tabelle", "geburt"), "Behandlungsdaten sind keine Geburtsdaten"


def test_tabelle_endet_vor_formularblock(tmp_path):
    inhalt = [(72, 300, "Name"), (180, 300, "Vorname"), (280, 300, "Geb.-Datum"),
              (72, 314, "Brandt"), (180, 314, "Dennis"), (280, 314, "12.02.1979"),
              (72, 335, "Vertragsdaten", 9), (72, 348, "Tarif:"), (180, 348, "PflegeTagegeld PT 50"),
              (72, 361, "BIC:"), (180, 361, "RCBWDEB3"), (72, 374, "Zahlungsweise: SEPA-Lastschrift")]
    dok = _modell(_pdf(tmp_path / "ende.pdf", [inhalt]))
    texte = _texte(dok, "struktur.tabelle", "namen")
    assert "Brandt" in texte and "Dennis" in texte
    assert not texte & {"Vertragsdaten", "Tarif", "BIC", "SEPA-Lastschrift", "PflegeTagegeld"}


def test_arbeitgeberspalte_ganze_zelle(tmp_path):
    """Spalte "Arbeitgeber" (Versicherungsverlauf): der Zellwert ist der Arbeitgeber; Organisationen der
    Erlaubnisliste bleiben stehen."""
    inhalt = [(72, 300, "Zeitraum"), (200, 300, "Arbeitgeber"), (420, 300, "Beitragsmonate"),
              (72, 314, "1998 - 2004"), (200, 314, "Maschinenfabrik Ostertal AG"), (420, 314, "72"),
              (72, 328, "2005 - 2012"), (200, 328, "Bäckerei Hofmeister"), (420, 328, "96"),
              (72, 342, "2013 - 2024"), (200, 342, "Deutsche Rentenversicherung Bund"), (420, 342, "144")]
    dok = _modell(_pdf(tmp_path / "verlauf.pdf", [inhalt]))
    werte = _texte(dok, "struktur.tabelle", "arbeitgeber")
    assert werte == {"Maschinenfabrik Ostertal AG", "Bäckerei Hofmeister"}


def test_layoutspalten_sind_keine_tabelle(tmp_path):
    """Anschriftfeld links und Informationsblock rechts auf gleicher Höhe bilden keine Tabelle."""
    inhalt = [(71, 200, "Frau"), (71, 211, "Yasmin Mansour"), (71, 222, "Postfach 2 20"), (71, 233, "89073 Ulm"),
              (355, 222, "Ansprechpartner", 7), (355, 233, "Panagiotis Nikolaidis"),
              (355, 244, "Telefon", 7), (355, 255, "0711 3003-460")]
    dok = _modell(_pdf(tmp_path / "layout.pdf", [inhalt]))
    assert _treffer(dok, "struktur.tabelle") == []


def test_tabelle_laufzeit_je_seite(tmp_path):
    dok = _modell(_pdf(tmp_path / "zeit.pdf", _bestandsliste(zeilen_je_seite=40, anzahl=32, abstand=13), quer=True))
    kontext = Kontext(ALLE)
    anfang = time.perf_counter()
    for name in ("struktur.tabelle", "struktur.etikett_wert", "struktur.adressblock", "struktur.anrede_gruss",
                 "struktur.betreff", "struktur.ort_datum", "struktur.kopf_fuss", "struktur.formularfeld"):
        _detektor(name)(dok, kontext)
    assert time.perf_counter() - anfang < 1.0


# ----------------------------------------------------------------------
# Formularfelder
# ----------------------------------------------------------------------
def test_formularfeld_ort_und_plz_in_eigenen_feldern(tmp_path):
    inhalt = [(57, 130, "Vorname:"), (57, 150, "PLZ:"), (57, 170, "Ort:"), (57, 190, "Geburtsdatum:")]
    felder = [(0, (204, 120, 340, 134), "f_Vorname_25_156", "Miroslaw"),
              (0, (204, 140, 260, 154), "f_PLZ_25_287", "60311"),
              (0, (204, 160, 366, 174), "f_Ort_25_306", "Frankfurt am Main"),
              (0, (204, 180, 285, 194), "f_Geburtsdatum_25_212", "29.03.1985")]
    dok = _modell(_pdf(tmp_path / "formular.pdf", [inhalt], felder=felder))
    werte = _treffer(dok, "struktur.formularfeld")
    assert ("plzort", "Frankfurt am Main") in werte
    assert ("plzort", "60311") in werte
    assert ("namen", "Miroslaw") in werte
    assert ("geburt", "29.03.1985") in werte


def test_formularfeld_feldname_ohne_etikett():
    from anonymisierer.detektoren.struktur_formular import _etikett_fuer, _feldname_lesbar
    assert _feldname_lesbar("f_Ort_25_306") == "Ort"
    assert _feldname_lesbar("geburtsDatum") == "geburts Datum"
    assert "adresse" in _etikett_fuer("Wohnort").arten
    assert _etikett_fuer("Vertragsbeginn") is None


# ----------------------------------------------------------------------
# Anschriften: Kunde oder Organisation
# ----------------------------------------------------------------------
def _versichererbrief():
    return [[
        (71, 45, "Harz Assekuranz AG", 14), (71, 66, "Breite Straße 70 · 38855 Wernigerode", 8),
        (71, 78, "Service-Telefon 0800 826 9819 · www.harz-versicherung.de", 8),
        (71, 140, "Harz Assekuranz AG · Breite Straße 70 · 38855 Wernigerode", 7),
        (71, 186, "Frau", 10), (71, 198, "Réka Györi", 10), (71, 210, "Postfach 66 01 13", 10),
        (71, 222, "79098 Freiburg im Breisgau", 10),
        (71, 300, "Sehr geehrte Frau Györi,", 10),
        (71, 790, "Harz Assekuranz AG", 7), (71, 798, "Breite Straße 70 · 38855 Wernigerode", 7),
        (71, 806, "Sitz: Wernigerode · Amtsgericht Wernigerode HRB 16963", 7),
        (227, 790, "Vorstand: José González (Vorsitzender), Anton Frank", 7),
    ]]


def test_muster_ohne_firmenanschriften(tmp_path):
    dok = _modell(_pdf(tmp_path / "brief.pdf", _versichererbrief()))
    strassen = _texte(dok, "muster.strasse")
    orte = _texte(dok, "muster.plzort")
    assert "Postfach 66 01 13" in strassen
    assert "79098 Freiburg im Breisgau" in orte
    assert not any("Breite Straße" in s for s in strassen), strassen
    assert not any("Wernigerode" in o for o in orte), orte
    assert not any("16963" in o for o in orte), "Registernummer ist keine PLZ"
    vorschlaege = getattr(dok, "struktur_vorschlaege", [])
    assert any("Wernigerode" in dok.text[v["start"]:v["ende"]] for v in vorschlaege), "Firmenanschrift vermerkt"


@pytest.mark.parametrize("text,erwartet", [
    ("92637 Weiden i.d.OPf.\t\tBU", ["92637 Weiden i.d.OPf."]),
    ("91207 Lauf a.d.Pegnitz", ["91207 Lauf a.d.Pegnitz"]),
    ("95028 Hof", ["95028 Hof"]),
    ("32423 Minden Versicherungsnummer 12 345678 A 123", ["32423 Minden"]),
    ("Amtsgericht Freiburg HRB 16963\nVorstand: Anton Schulze", []),
    ("Sitz: Lübbenau HRB 17205 USt-IdNr. DE469515275", []),
])
def test_muster_plzort_fehlgriffe_und_ortszusaetze(text, erwartet):
    dok = seitenmodell.dokument_aus_text(text)
    assert [dok.text[t.start:t.ende] for t in _detektor("muster.plzort")(dok, Kontext({"plzort"}))] == erwartet


@pytest.mark.parametrize("text,erwartet", [
    ("90762 Fürth\t\tPHV", "90762 Fürth"),                               # Zellgrenze (Tabelle im Scan)
    ("82319 Starnberg\t\tLeben\nDebeka\t\tKF589934782", "82319 Starnberg"),
    ("94032 Passau BU Spreewald LV-2016-468183", "94032 Passau"),        # Textschicht ohne Tabs
    ("63739 Aschaffenburg Leben Debeka", "63739 Aschaffenburg"),
    ("93047 Regensburg Kfz", "93047 Regensburg"),
    ("60311 Frankfurt am Main", "60311 Frankfurt am Main"),
    ("06108 Halle (Saale)", "06108 Halle (Saale)"),
    ("53474 Bad Neuenahr-Ahrweiler", "53474 Bad Neuenahr-Ahrweiler"),
    ("61348 Bad Homburg v. d. Höhe", "61348 Bad Homburg v. d. Höhe"),
    ("74523 Schwäbisch Hall", "74523 Schwäbisch Hall"),
    ("86899 Landsberg am Lech\t\tLeben", "86899 Landsberg am Lech"),
    ("92637 Weiden i.d.OPf.", "92637 Weiden i.d.OPf."),
    ("90402 NÜRNBERG", "90402 NÜRNBERG"),
])
def test_plz_ort_endet_an_zellgrenzen_und_fremden_woertern(text, erwartet):
    assert [text[a:b] for a, b in st.plz_ort_spannen(text, 0, len(text))] == [erwartet]


def test_muster_anschrift_als_stellen_nie_ueber_spaltentrenner():
    """Die Muster liefern Stellen; ein anderswo gefundener Text wird nicht über Spaltentrenner hinweg
    wiedergesucht ("82319 Starnberg Leben" in der Textschicht, "82319 Starnberg | Leben" in der Tabelle)."""
    text = "Kundin: 82319 Starnberg Leben\nBestand:\n82319 Starnberg\t\tLeben\t\tDebeka\n"
    dok = seitenmodell.dokument_aus_text(text)
    orte = [dok.text[t.start:t.ende] for t in _detektor("muster.plzort")(dok, Kontext({"plzort"}))]
    assert orte == ["82319 Starnberg", "82319 Starnberg"]
    for text, erwartet in (("Rehazentrum Am Kurpark\t\t946,21\t\t662,34", []),
                           ("Rehazentrum Am Kurpark 946,21 EUR", []),
                           ("Hauptstraße 12a\t\tTelefon", ["Hauptstraße 12a"])):
        dok = seitenmodell.dokument_aus_text(text)
        strassen = [dok.text[t.start:t.ende] for t in _detektor("muster.strasse")(dok, Kontext({"strasse"}))]
        assert strassen == erwartet, text


def test_adressblock_kunde(tmp_path):
    dok = _modell(_pdf(tmp_path / "brief.pdf", _versichererbrief()))
    werte = _treffer(dok, "struktur.adressblock")
    assert ("namen", "Réka Györi") in werte
    assert ("strasse", "Postfach 66 01 13") in werte
    assert ("plzort", "79098 Freiburg im Breisgau") in werte
    assert not any("Wernigerode" in w or "Breite" in w for _, w in werte)


def test_adressblock_ohne_strassenwort_und_zeile_mit_trennern(tmp_path):
    inhalt = [(340, 40, "Erzsébet Kovács", 8), (340, 50, "Alt-Moabit 63", 8),
              (340, 60, "61348 Bad Homburg v. d. Höhe", 8),
              (340, 70, "Tel. +49 6172 733983", 8),
              (71, 140, "Erzsébet Kovács · Alt-Moabit 63 · 61348 Bad Homburg v. d. Höhe", 7),
              (71, 186, "Alpenland Krankenversicherung a.G.", 10), (71, 198, "Kundenservice", 10),
              (71, 210, "Postfach 2 20", 10), (71, 222, "81675 München", 10)]
    dok = _modell(_pdf(tmp_path / "kuendigung.pdf", [inhalt]))
    werte = _treffer(dok, "struktur.adressblock")
    assert ("strasse", "Alt-Moabit 63") in werte
    assert ("namen", "Erzsébet Kovács") in werte
    assert not any("München" in w or "Postfach 2 20" in w for _, w in werte), "Anschrift des Versicherers bleibt"
    assert not any("München" in w for w in _texte(dok, "muster.plzort"))


def test_adressblock_formular_mit_versicherer_im_block(tmp_path):
    """Ein Versicherer in einer Formularzeile macht die Anschrift des Unfallgegners nicht zur Firma."""
    inhalt = [(57, 320, "Name:"), (200, 320, "Frau Eva-Maria Grünewald"),
              (57, 332, "Anschrift:"), (200, 332, "Hohe Straße 14 a, 40213 Düsseldorf"),
              (57, 344, "Versicherer des Gegners:"), (200, 344, "HUK-COBURG, VS-Nr. KH-2018-393168"),
              (57, 380, "5. Zeugen"), (57, 392, "Florian Groß, Birkenallee 60, 76133 Karlsruhe, Tel. 0211 2381321")]
    dok = _modell(_pdf(tmp_path / "schaden.pdf", [inhalt]))
    orte = _texte(dok, "muster.plzort")
    assert {"40213 Düsseldorf", "76133 Karlsruhe"} <= orte
    assert "Birkenallee 60" in _texte(dok, "muster.strasse")


# ----------------------------------------------------------------------
# Anrede, Gruß, Unterschrift, Betreff, Ort-Datum, Kopf/Fuß
# ----------------------------------------------------------------------
def test_anrede_und_gruss():
    text = ("Sehr geehrte Frau Prof. Dr. von Arnim-Lübbenau,\n\nvielen Dank.\n\nMit freundlichen Grüßen\n"
            "Schwarzwald Lebensversicherung AG\n\ni. A. Andrea Krause\nKundenservice")
    namen = {w for k, w in _text(text, "struktur.anrede_gruss") if k == "namen"}
    assert "von Arnim-Lübbenau" in namen
    assert "Andrea Krause" in namen
    assert not namen & {"Kundenservice", "Schwarzwald Lebensversicherung AG", "Schwarzwald"}


@pytest.mark.parametrize("text", ["Sehr geehrte Damen und Herren,", "Hallo zusammen,",
                                  "Liebe Kolleginnen und Kollegen,"])
def test_anrede_ohne_namen(text):
    assert _text(text, "struktur.anrede_gruss") == []


def test_unterschriften_ueber_rollen(tmp_path):
    inhalt = [(62, 510, "St. Ingbert, 11.08.2025"), (300, 510, "Hofheim am Taunus, 11.08.2025"),
              (62, 548, "Emily Kelly"), (300, 548, "Burak Kurt"), (62, 562, "Mandant", 8), (300, 562, "Makler", 8)]
    dok = _modell(_pdf(tmp_path / "vollmacht.pdf", [inhalt]))
    namen = _texte(dok, "struktur.anrede_gruss", "namen")
    assert {"Emily Kelly", "Burak Kurt"} <= namen
    orte = _texte(dok, "struktur.ort_datum")
    assert {"St. Ingbert", "Hofheim am Taunus"} <= orte


def test_ort_datum_nicht_der_ort_des_versicherers():
    text = ("Allianz Lebensversicherungs-AG\nReinsburgstraße 19, 70178 Stuttgart\n\nHerrn\nMax Mustermann\n"
            "Bergstraße 7\n69117 Heidelberg\n\nStuttgart, 14.03.2025\n\nMontag, 17.03.2025\n\n"
            "Heidelberg, den 20.03.2025")
    orte = {w for _, w in _text(text, "struktur.ort_datum")}
    assert "Heidelberg" in orte
    assert "Stuttgart" not in orte and "Montag" not in orte


def test_betreff_kennung_ohne_etikett():
    text = ("Beitragsanpassung 2026 – LV-2019-385221 / Ihr Schreiben vom 12.03.2025 (§ 38 VVG)\n\n"
            "Sehr geehrte Frau Mansour,\n\nwir passen den Beitrag an.")
    werte = {w for _, w in _text(text, "struktur.betreff")}
    assert werte == {"LV-2019-385221"}


def test_kopf_fuss_kennung_auf_jeder_seite(tmp_path):
    kopf = "Spreewald · Versicherungsschein KV 3372-8824-91 · Seite {}/2"
    fuss = "Sitz: Lübbenau · Amtsgericht Lübbenau HRB 2418712"
    seiten = [[(71, 30, kopf.format(i), 8), (71, 300, "Text der Seite", 10), (71, 800, fuss, 7)] for i in (1, 2)]
    dok = _modell(_pdf(tmp_path / "kopf.pdf", seiten))
    werte = _texte(dok, "struktur.kopf_fuss")
    assert werte == {"KV 3372-8824-91"}


# ----------------------------------------------------------------------
# Lage: Schräglage und Zellen
# ----------------------------------------------------------------------
def test_lage_schraege_und_zellen():
    dok = seitenmodell.dokument_aus_text("Name:   Max Muster\tKunde\nzweite Zeile")
    lg = st.lage(dok.seiten[0])
    assert lg.schraege == 0.0
    zellen = [dok.text[c.start:c.ende] for c in lg.zellen_je_zeile[0]]
    assert zellen == ["Name:", "Max Muster", "Kunde"]
    # Schräglage aus langen Zeilen: dy/dx der Wortmitten
    roh = [(0, 1, 10, 100 + 0.01 * 10, 20, 110 + 0.01 * 10, z, 10, True) for z in range(4)]
    roh += [(2, 3, 400, 100 + 0.01 * 400, 420, 110 + 0.01 * 400, z, 10, True) for z in range(4)]
    assert abs(st._schraege(roh) - 3.9 / 395) < 1e-6


def test_lage_kopfstehender_scan():
    """Leserichtung 180°: Text läuft nach links, Zeilen nach oben – die Lage dreht zurück."""
    roh = []
    for z in range(4):
        y = 700 - 20 * z
        roh += [(10 * z, 10 * z + 3, 500, y, 520, y + 10, z, 0, True),
                (10 * z + 4, 10 * z + 7, 300, y, 320, y + 10, z, 0, True)]
    assert st._richtung(roh) == 180
    gedreht = st._drehen(roh[0], 180, 595, 842)
    assert gedreht[2] == 595 - 520 and gedreht[3] == 842 - 710


# ----------------------------------------------------------------------
# Nummern hinter Substantiven, Kennungsarten, Anrede im Fließtext, c/o, Firmenanschriften
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text,kategorie,wert", [
    ("Ihre Lebensversicherung Nr. LV-2011-009307 – Ablauf zum 19.12.2025", "vertrag", "LV-2011-009307"),
    ("Anlage: Kopie Personalausweis (Nr. TLH4PLJCH)", "ausweis", "TLH4PLJCH"),
    ("BIC:\t\tTTCGDEMNXXX", "bic", "TTCGDEMNXXX"),
    ("Mandatsreferenz: SEPA816626-520", "mandat", "SEPA816626-520"),
    ("Sozialversicherungsnummer:\t\t03 241061 C 515", "svnr", "03 241061 C 515"),
])
def test_etikett_wert_kennungsarten(text, kategorie, wert):
    assert (kategorie, wert) in _text(text, "struktur.etikett_wert")


@pytest.mark.parametrize("text,name", [
    ("anbei die Rechnung der Werkstatt Berger und die Fotos.", "Berger"),
    ("Behandlung bei Physiotherapie Santoro", "Santoro"),
    ("Autohaus Schmidt & Söhne GmbH", "Schmidt"),
])
def test_name_in_firmenbezeichnung_hinter_betriebswort(text, name):
    assert ("namen", name) in _text(text, "struktur.etikett_wert")


@pytest.mark.parametrize("text", ["die Werkstatt hat geöffnet", "Die Werkstatt Auto Berg GmbH hat angerufen",
                                  "Verhältnis zum VN:\t\tMitbewohner, berechtigter Fahrer"])
def test_betriebswort_und_wendung_gegenproben(text):
    assert not [w for k, w in _text(text, "struktur.etikett_wert") if k == "namen"]


@pytest.mark.parametrize("text", ["Hauptstraße Nr. 5", "Seite Nr. 12345", "Position Nr. 123456"])
def test_nr_hinter_strasse_oder_seite_ist_keine_kennung(text):
    assert _text(text, "struktur.etikett_wert") == []


@pytest.mark.parametrize("text,name", [
    ("Fragen beantwortet Ihnen gern Frau de Vries in unserer Beratungsstelle.", "de Vries"),
    ("Ihr Berater Herr Ågren ist erreichbar.", "Ågren"),
    ("die Mutter, Frau Yildirim, leidet an Asthma.", "Yildirim"),
])
def test_anrede_im_fliesstext(text, name):
    assert ("namen", name) in _text(text, "struktur.anrede_gruss")


@pytest.mark.parametrize("text", ["Frau Doktor hat angerufen.",
                                  "Sehr geehrter Herr Müller, Max Müller ist versichert."])
def test_anrede_im_fliesstext_gegenproben(text):
    namen = {w for _, w in _text(text, "struktur.anrede_gruss")}
    assert "Doktor" not in namen and "Müller, Max Müller" not in namen


def test_c_o_anschrift_bleibt_personenanschrift():
    text = "Schmidt Finanz GmbH\nc/o Thomas Schmidt\nHauptstraße 12a\n60311 Frankfurt am Main\n"
    dok = seitenmodell.dokument_aus_text(text)
    assert "60311 Frankfurt am Main" in {dok.text[t.start:t.ende] for t in
                                         _detektor("muster.plzort")(dok, Kontext(ALLE))}


@pytest.mark.parametrize("text,anschrift,vorschlag", [
    ("Rentenauskunft\nFrau Anna Berg, geboren am 02.09.1983\n"
     "Deutsche Rentenversicherung Nordbayern, Postfach 10 11 12, 90401 Nürnberg\n", "90401 Nürnberg", False),
    ("Thomas Schmidt\nVersicherungsmakler\nSchmidt Finanz GmbH · Hauptstraße 12a · 60311 Frankfurt am Main\n"
     "Tel.: 069 123456-0\n", "60311 Frankfurt am Main", True),
])
def test_firmenanschrift_bleibt_und_wird_vorgeschlagen(text, anschrift, vorschlag):
    """Vertragsänderung Phase 3 (EQ-15): Anschriften von Behörden und Firmen werden nicht geschwärzt.
    Unbekannte Firmen (nicht in der Erlaubnisliste) werden als Vorschlag vermerkt (dok.struktur_vorschlaege),
    damit die Oberfläche sie anbieten kann; bekannte Organisationen (Deutsche Rentenversicherung) nicht."""
    dok = seitenmodell.dokument_aus_text(text)
    gefunden = {dok.text[t.start:t.ende] for t in _detektor("muster.plzort")(dok, Kontext(ALLE))}
    assert anschrift not in gefunden
    vorgeschlagen = {dok.text[v["start"]:v["ende"]] for v in getattr(dok, "struktur_vorschlaege", [])}
    assert (anschrift in vorgeschlagen) is vorschlag


def test_tabelle_kundenspalte_braucht_namensbeleg():
    """"Berlin, Hamburg" in der Kundenspalte ist kein Name (kein bekannter Vor- oder Nachname in der Reihe)."""
    text = ("Nr. Kunde (Name, Vorname)\t\tgeb.\t\tOrt\n"
            "1 Hahn, Annika\t\t14.03.1961\t\tBerlin\n"
            "2 Berlin, Hamburg\t\t01.01.1970\t\tKöln\n")
    namen = {w for k, w in _text(text, "struktur.tabelle") if k == "namen"}
    assert "Hahn, Annika" in namen and "Berlin, Hamburg" not in namen
