"""Tabellenaufbau und Scans aus der Domänen-Durchsicht (Runde 5, Paket „Tabellen und Scans“: Befunde 84, 85, 90, 91,
93).

Je Befund: die Zeilen aus den Falldateien der Durchsicht (Bestandslisten mit umbrochenen Zellen, Kastenformulare,
Courtage- und Entgeltabrechnungen, Ausweiskopien), eine abgewandelte Schreibweise und Gegenproben gegen
Über-Schwärzung (Feld-Etiketten, Überschriften, Firmen, Sparten, Beträge, Daten). Wo die Erkennung etwas neu kennt,
prüft ein Test auch die Selbstkontrolle (restrisiko.py): bliebe der Wert lesbar, muss sie ihn melden. Die Scans
(Befund 85) laufen mit Tesseract. Alle Personen, Nummern und Anschriften sind erfunden."""

import io

import pytest

import pymupdf as fitz

from anonymisierer import muster
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.restrisiko import pruefe_text, restrisiko_pruefen
from conftest import braucht_ocr, schrift_mit_zeichen

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------
def _pdf(pfad, elemente, schrift=None):
    """Textseite aus Elementen (x, y, text, schriftgröße); schrift: Pfad einer TrueType-Schrift, sonst Helvetica."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    for x, y, text, groesse in elemente:
        if text and schrift:
            seite.insert_text((x, y), text, fontsize=groesse, fontname="tt", fontfile=schrift)
        elif text:
            seite.insert_text((x, y), text, fontsize=groesse, fontname="helv")
    doc.save(pfad)
    doc.close()
    return pfad


def _tabelle(y, xs, reihen, groesse=8, abstand=11):
    """Reihen (Listen von Zellen) an den Spaltenpositionen xs, wie die Falldateien der Durchsicht (bau.tabelle)."""
    return [(x, y + i * abstand, zelle, groesse) for i, reihe in enumerate(reihen) for x, zelle in zip(xs, reihe)]


def _kasten(y, xs, paare, lg=7.5, wg=10, schritt=27):
    """Kastenformular: Etikett klein, darunter der Wert (wie faelle_k1.kasten)."""
    aus = []
    for i, (etiketten, werte) in enumerate(paare):
        yy = y + i * schritt
        for x, e, w in zip(xs, etiketten, werte):
            aus.append((x, yy, e, lg))
            aus.append((x, yy + 12, w, wg))
    return aus


def _funde(pfad, ocr=None):
    erg = analysiere_pdf(pfad, ALLE, [], [], ocr=ocr)
    assert not erg.get("fehler"), erg.get("fehler")
    return erg["funde"]


def _stellen(funde, kategorie=None) -> list:
    """Texte aller angehakten Stellen (optional nur einer Kategorie)."""
    return [st["text"] for f in funde if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)]


def _gedeckt(funde, wert, kategorie=None) -> bool:
    """Liegt der Wert ganz in einer angehakten Stelle?"""
    return any(wert in t for t in _stellen(funde, kategorie))


def _beruehrt(funde, wert) -> bool:
    """Wird der Wert (oder ein Teil davon) geschwärzt?"""
    return any(wert in t or t in wert for t in _stellen(funde) if len(t) >= 2)


def _verdacht_pdf(pfad) -> list:
    return [(v.text, v.grund) for v in restrisiko_pruefen(pfad)]


def _gemeldet(verdacht, wert) -> bool:
    return any(wert in t or (len(t) >= 3 and t in wert) for t, _ in verdacht)


# ----------------------------------------------------------------------
# Befund 84: mehrzeilige Tabellenzellen (Zellumbruch in Bestandslisten)
# ----------------------------------------------------------------------
_XS = [36, 130, 262, 470]
_KOPF = ["VSNR", "Versicherungsnehmer", "Risikoanschrift", "Beitrag"]
_TITEL = (36, 50, "Wohngebäude – Bestandsübersicht (Hausverwaltung)", 11)
_NAMEN = [_KOPF,
          ["WG 4471-0815-31", "Eheleute", "Kapellenweg 3,", "702,00"],
          ["", "Gstettner", "84347 Pfarrkirchen", ""],
          ["WG 4471-0815-32", "Familie", "Am Kellerberg 7,", "612,00"],
          ["", "Wiesenhofer", "84489 Burghausen", ""],
          ["WG 4471-0815-33", "Erbengemeinschaft", "Kirchsteig 2,", "498,00"],
          ["", "Ruhstorfer", "83346 Bergen", ""]]
_ADRESSE = [_KOPF,
            ["WG 4471-0815-34", "Pichlmeier, Notburga", "Am Gänsbichl", "586,00"],
            ["", "", "4, 84453 Mühldorf a. Inn", ""],
            ["WG 4471-0815-35", "Ruhstorfer, Kunigunde", "Untere Bachgasse", "498,00"],
            ["", "", "5, 83512 Wasserburg a. Inn", ""],
            ["WG 4471-0815-36", "Schwarzenböck, Ottilie", "Sonnleitenstraße 17,", "655,00"],
            ["", "", "83395 Freilassing", ""]]
# abgewandelte Schreibweise (Durchsicht k10c/k4): lange Namenszellen, PLZ und Ort getrennt, Komma am Zeilenende
_LANG = [_KOPF,
         ["WG 4471-0815-41", "Eheleute Severin und Afra", "Kapellenweg 3, 84347", "702,00"],
         ["", "Gstettner", "Pfarrkirchen", ""],
         ["HR 7740-2291-42", "Baltasar Wiesenhofer und", "Am Kellerberg 7, 84489", "186,40"],
         ["", "Walburga Oberprieler", "Burghausen", ""],
         ["WG 4471-0815-43", "Grundstücksgemeinschaft", "Sonnleitenstraße", "655,00"],
         ["", "Schwarzenböck/Lechleitner", "17, 83395 Freilassing", ""],
         ["WG 4471-0815-44", "Haberl,", "Am Anger 22,", "498,00"],
         ["", "Josefa", "83533 Edling", ""]]


def test_befund_84_namen_ueber_zwei_zeilen_einer_zelle(tmp_path):
    funde = _funde(_pdf(tmp_path / "namen.pdf", [_TITEL] + _tabelle(80, _XS, _NAMEN)))
    for name in ("Gstettner", "Wiesenhofer", "Ruhstorfer"):
        assert _gedeckt(funde, name, "namen"), (name, _stellen(funde))
    # die Wörter für die Personengruppe bleiben stehen
    for wort in ("Eheleute", "Familie", "Erbengemeinschaft", "Versicherungsnehmer"):
        assert not _beruehrt(funde, wort), (wort, _stellen(funde))


def test_befund_84_anschrift_ueber_zwei_zeilen_einer_zelle(tmp_path):
    funde = _funde(_pdf(tmp_path / "anschrift.pdf", [_TITEL] + _tabelle(80, _XS, _ADRESSE)
                        + [(36, 180, "Anzahl Objekte: 4, davon 5 vermietet. Seite 1 von 1", 8)]))
    for wert in ("Am Gänsbichl", "Untere Bachgasse", "84453 Mühldorf a. Inn", "83512 Wasserburg a. Inn"):
        assert _gedeckt(funde, wert), (wert, _stellen(funde))
    # die Hausnummern in der Folgezeile gehören zur Straße und werden mitgeschwärzt ...
    texte = _stellen(funde, "strasse")
    assert "4" in texte and "5" in texte, texte
    # ... aber nicht im ganzen Dokument weitergegeben ("4" und "5" in der Fußzeile bleiben)
    assert texte.count("4") == 1 and texte.count("5") == 1, texte


def test_befund_84_abgewandelte_schreibweise(tmp_path):
    funde = _funde(_pdf(tmp_path / "lang.pdf", [_TITEL] + _tabelle(80, _XS, _LANG)))
    for name in ("Gstettner", "Wiesenhofer", "Oberprieler", "Schwarzenböck", "Lechleitner", "Haberl"):
        assert _gedeckt(funde, name, "namen"), (name, _stellen(funde))
    for wert in ("84347", "Pfarrkirchen", "84489", "Burghausen", "Sonnleitenstraße"):
        assert _gedeckt(funde, wert), (wert, _stellen(funde))
    assert not _beruehrt(funde, "Grundstücksgemeinschaft"), _stellen(funde)


def test_befund_84_namensteile_einer_person_tragen_einen_platzhalter(tmp_path):
    funde = _funde(_pdf(tmp_path / "lang.pdf", [_TITEL] + _tabelle(80, _XS, _LANG)))
    ersatz = {st["text"]: f["ersatz"] for f in funde if f["kategorie"] == "namen" for st in f["stellen"]}
    assert ersatz.get("Haberl") == ersatz.get("Josefa"), ersatz


@pytest.mark.parametrize("reihen, bleibt", [
    # zweite Reihe ohne Kunden, aber mit eigener Vertragsnummer: ein neuer Vertrag, kein Umbruch
    ([["Kunde", "Vertrag", "Sparte", "Beitrag"],
      ["Pichlmeier, Notburga", "HR-7740-2291-05", "Hausrat", "186,40"],
      ["", "PHV-0071-4471", "Privathaftpflicht", "89,90"],
      ["Ruhstorfer, Kunigunde", "RS-0815-2291", "Rechtsschutz", "298,30"]], ["Hausrat", "Privathaftpflicht"]),
    # Firma über zwei Zeilen in der Personenspalte, Vermerk unter dem Namen
    ([_KOPF, ["WG 4471-0815-51", "Hausverwaltung", "Kirchsteig 2,", "498,00"],
      ["", "Inntal GmbH", "83346 Bergen", ""],
      ["WG 4471-0815-52", "Gstettner, Severin", "Kapellenweg 3,", "702,00"],
      ["", "(verstorben)", "84347 Pfarrkirchen", ""]], ["Hausverwaltung", "Inntal", "verstorben"]),
    # umbrochene Sparte und Summenzeile: keine Personen- oder Anschriftspalte
    ([["Vertrag", "Versicherungsnehmer", "Sparte", "Beitrag"],
      ["HR-7740-2291-05", "Pichlmeier, Notburga", "Wohngebäude-", "612,00"],
      ["", "", "versicherung", ""],
      ["Summe", "", "", "612,00"]], ["Wohngebäude-", "versicherung", "Summe"]),
    # Zusatz unter der Anschrift
    ([_KOPF, ["WG 4471-0815-53", "Pichlmeier, Notburga", "Kirchsteig 2,", "498,00"],
      ["", "", "(Nebengebäude)", ""]], ["Nebengebäude", "498,00"]),
])
def test_befund_84_gegenproben_kein_umbruch(tmp_path, reihen, bleibt):
    funde = _funde(_pdf(tmp_path / "gegen.pdf", [_TITEL] + _tabelle(80, _XS, reihen)))
    for wert in bleibt:
        assert not _beruehrt(funde, wert), (wert, _stellen(funde))


def test_befund_84_selbstkontrolle_meldet_umbrochene_werte(tmp_path):
    """Bliebe ein umbrochener Name oder Straßenname lesbar, meldet ihn die Selbstkontrolle (Spalte mit Personen- bzw.
    Anschrift-Etikett im Kopf, auch über Datenzeilen hinweg)."""
    pdf = _pdf(tmp_path / "rest.pdf", [_TITEL] + _tabelle(80, _XS, _NAMEN))
    verdacht = _verdacht_pdf(pdf)
    for name in ("Gstettner", "Wiesenhofer"):
        assert _gemeldet(verdacht, name), verdacht
    pdf = _pdf(tmp_path / "rest2.pdf", [_TITEL] + _tabelle(80, _XS, _ADRESSE))
    verdacht = _verdacht_pdf(pdf)
    for wert in ("Am Gänsbichl", "Untere Bachgasse"):
        assert _gemeldet(verdacht, wert), verdacht


# ----------------------------------------------------------------------
# Befund 91: Namensspannen über Spaltentrenner ("Mooslechner, Anton⇥⇥PHV")
# ----------------------------------------------------------------------
_COURTAGE = ["Vertrag\t\tVersicherungsnehmer\t\tSparte\t\tBeginn\t\tJahresbeitrag",
             "HR-7740-2291-01\t\tMooslechner, Anton\t\tPHV\t\t01.02.2016\t\t89,90",
             "LV 2291/8817-03\t\tGstettner, Severin\t\tBU\t\t01.11.2016\t\t1.234,56",
             "HR-7740-2291-02\t\tRieder, Maria\t\tPHV\t\t01.03.2017\t\t89,90",
             "HR-7740-2291-03\t\tKaltenecker, Rosa\t\tHausrat\t\t01.04.2018\t\t186,40"]


def test_befund_91_namensspanne_endet_am_spaltentrenner():
    funde = analysiere_text("\n".join(_COURTAGE), ALLE, [], [])
    namen = _stellen(funde, "namen")
    assert "Mooslechner, Anton" in namen and "Gstettner, Severin" in namen, namen
    assert not any("\t" in t for t in namen), namen
    for sparte in ("PHV", "BU", "Hausrat"):
        assert not _beruehrt(funde, sparte), (sparte, _stellen(funde))


def test_befund_91_versalwort_hinter_vornamen_ohne_spaltentrenner():
    """OCR-Zeilen kennen keine Tabulatoren: ein Spartenkürzel hinter dem Vornamen ist kein zweiter Vorname – weder in
    der Regel "Nachname, Vorname" noch in einem Treffer der KI ("Severin BU")."""
    funde = analysiere_text("Versicherungsnehmer: Mooslechner, Anton PHV 01.02.2016 89,90\n"
                            "LV 2291/8817-03 Gstettner, Severin BU 01.11.2016 1.234,56", ALLE, [], [])
    assert _gedeckt(funde, "Mooslechner, Anton", "namen") and _gedeckt(funde, "Severin", "namen"), _stellen(funde)
    assert not _beruehrt(funde, "PHV") and not _beruehrt(funde, "BU"), _stellen(funde)


@pytest.mark.parametrize("zeile, name", [
    ("Versicherungsnehmer: MOOSLECHNER, ANTON JOSEF", "MOOSLECHNER, ANTON JOSEF"),   # alles in Versalien
    ("Versicherungsnehmer: Mooslechner, Anton Maria", "Mooslechner, Anton Maria"),   # zweiter Vorname bekannt
    ("Versicherungsnehmer: Mooslechner, Anton MARIA", "Mooslechner, Anton MARIA"),   # bekannter Vorname in Versalien
])
def test_befund_91_gegenproben_zweiter_vorname_bleibt_teil_des_namens(zeile, name):
    assert _gedeckt(analysiere_text(zeile, ALLE, [], []), name, "namen")


def test_befund_91_bestandsliste_als_pdf(tmp_path):
    reihen = [["Vertrag", "Versicherungsnehmer", "Sparte", "Beginn", "Jahresbeitrag"]] + [
        [f"HR-7740-2291-{i:02d}", name, sparte, f"01.0{1 + i}.2016", "89,90"]
        for i, (name, sparte) in enumerate([("Mooslechner, Anton", "PHV"), ("Rieder, Maria", "PHV"),
                                            ("Gstettner, Severin", "BU"), ("Kaltenecker, Rosa", "PHV")])]
    funde = _funde(_pdf(tmp_path / "liste.pdf", _tabelle(80, [36, 130, 290, 380, 470], reihen)))
    assert not _beruehrt(funde, "PHV") and not _beruehrt(funde, "BU"), _stellen(funde)
    for name in ("Mooslechner", "Rieder", "Gstettner", "Kaltenecker"):
        assert _gedeckt(funde, name, "namen"), (name, _stellen(funde))


# ----------------------------------------------------------------------
# Befund 90: Fehlverdacht der Selbstkontrolle für Spaltenköpfe und Etikettwörter
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeilen, kein_verdacht", [
    (["Vornamen / Given names / Prénoms", "[PERSON A]"], ["Given", "Prénoms", "Vornamen"]),
    (["Geburtsort / Place of birth / Lieu de naissance", "[PLZ ORT]"], ["Place", "Lieu", "naissance"]),
    (["Name / Surname / Nom", "[PERSON A]"], ["Surname", "Nom"]),
    (["Wohngebäude – Bestandsübersicht Hausverwaltung Inntal GmbH"], ["Inntal"]),
])
def test_befund_90_etikettwoerter_und_firmen_ohne_fehlverdacht(zeilen, kein_verdacht):
    verdacht = [v.text for v in pruefe_text("\n".join(zeilen))]
    for wort in kein_verdacht:
        assert not any(wort in t for t in verdacht), (wort, verdacht)


# Fortsetzungsseite einer Bestandsliste (Durchsicht k4/k5): die Vertragsnummer "7.712.345" hat die Form eines Betrags.
# Ohne den Fehlverdacht auf "Sparte" fiel die Datei nur noch über ihn auf – der Wert selbst blieb still.
_XS5 = [36, 130, 290, 380, 470]
_FORTSETZUNG = [(36, 40, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026 – Seite 2", 8)] + _tabelle(70, _XS5, [
    ["Vertrag", "Versicherungsnehmer", "Sparte", "Beginn", "Jahresbeitrag"],
    ["PHV 447118", "Wiesenhofer, Baltasar", "PHV", "01.11.2019", "89,90"],
    ["RS 0815", "Ruhstorfer Kunigunde", "Rechtsschutz", "01.03.2018", "298,30"],
    ["7.712.345", "Oberprieler, Severin", "Unfall", "15.10.2026", "12.480"]])


def test_befund_90_vertragsnummer_in_betragsform_unter_dem_spaltenkopf(tmp_path):
    funde = _funde(_pdf(tmp_path / "fortsetzung.pdf", _FORTSETZUNG))
    assert _gedeckt(funde, "7.712.345", "vertrag"), _stellen(funde)
    # Gegenproben: der Betrag ohne Nachkommastellen in der Beitragsspalte, Sparte und Daten bleiben stehen
    for wert in ("12.480", "Unfall", "15.10.2026", "Sparte"):
        assert not _beruehrt(funde, wert), (wert, _stellen(funde))


def test_befund_90_selbstkontrolle_meldet_vertragsnummer_in_betragsform(tmp_path):
    verdacht = _verdacht_pdf(_pdf(tmp_path / "fortsetzung.pdf", _FORTSETZUNG))
    assert _gemeldet(verdacht, "7.712.345"), verdacht
    assert not _gemeldet(verdacht, "12.480") and not _gemeldet(verdacht, "Sparte"), verdacht
    # ein Betrag mit Nachkommastellen ist auch unter "Vertrag" kein Verdacht
    zeilen = [z if z[2] != "7.712.345" else (z[0], z[1], "1.712,35", z[3]) for z in _FORTSETZUNG]
    assert not _gemeldet(_verdacht_pdf(_pdf(tmp_path / "betrag.pdf", zeilen)), "1.712,35")


_BERUF = [(50, 60, "Antrag Berufsunfähigkeitsversicherung – Angaben zur versicherten Person", 12)] + _kasten(
    95, [50, 300], [(("Name, Vorname", "Geburtsdatum"), ("Pichlmeier, Notburga", "02.08.1958")),
                    (("Ausgeübter Beruf", "Arbeitgeber"), ("Pflegehelferin", "Seniorenstift St. Josef")),
                    (("Beruf des Ehepartners", "Beruf"), ("Erzieherin", "Pflegehelferin"))])


class _OcrAttrappe:
    """OcrDienst-Ersatz für Textseiten (keine OCR nötig)."""

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, winkel=None, **_):
        return [], None

    def schliessen(self):
        pass


def test_befund_90_ausgeuebter_beruf_im_kastenformular_ohne_fehlverdacht(tmp_path):
    """Ende zu Ende: das Etikett "Ausgeübter Beruf" bleibt ganz stehen, die Selbstkontrolle hält "Ausgeübter" nicht
    für einen Namen (die Durchsicht sah den Verdacht neben dem zu [ARBEITGEBER] geschwärzten "Beruf")."""
    from anonymisierer.schwaerzung import schwaerze_pdf
    pdf = _pdf(tmp_path / "beruf.pdf", _BERUF)
    a = analysiere_pdf(pdf, ALLE, [], [], ocr=_OcrAttrappe())
    e = schwaerze_pdf(pdf, a["funde"], modell=a["modell"], ocr=_OcrAttrappe(), ziel_ordner=tmp_path / "aus")
    assert e["fehler"] is None
    verdacht = [(v.text, v.grund) for v in e["verdacht"]]
    assert not _gemeldet(verdacht, "Ausgeübter"), verdacht


@pytest.mark.parametrize("zeile, wert", [
    ("Rechnung der Hausverwaltung Gstettner vom 12.11.2026", "Gstettner"),     # ohne Rechtsform: ein Name
    ("Rechnung der Werkstatt Müller GmbH vom 12.11.2026", "Müller"),           # Name der Wissensbasis
    ("die Bäckerei Kamps hat geliefert", "Kamps"),
])
def test_befund_90_gegenproben_namen_in_firmenbezeichnungen_bleiben_verdacht(zeile, wert):
    assert any(wert in v.text for v in pruefe_text(zeile)), [v.text for v in pruefe_text(zeile)]


# ----------------------------------------------------------------------
# Befund 93: Raster aus mehreren Kopf- und Wertzeilen (Kastenformular, Entgeltabrechnung)
# ----------------------------------------------------------------------
_KASTEN3 = [(50, 60, "Antrag auf Unfallversicherung – Angaben zur zu versichernden Person", 12)] + _kasten(
    95, [50, 220, 390], [
        (("Name", "Vorname", "Geburtsdatum"), ("Pichlmeier", "Notburga", "02.08.1958")),
        (("Straße, Hausnummer", "PLZ", "Ort"), ("Am Gänsbichl 4", "84453", "Mühldorf a. Inn")),
        (("Telefon", "Beruf (genaue Tätigkeit)", "Arbeitgeber"),
         ("08631 98765", "Pflegehelferin", "Seniorenstift St. Josef")),
        (("IBAN", "", "Kreditinstitut"), ("DE97 7115 0000 0020 3040 50", "", "Sparkasse Altötting-Mühldorf")),
    ]) + [(50, 225, "Gewünschte Leistungen: Invaliditätsgrundsumme 150.000 EUR, Progression 350 %", 10)]

_EXS = [40, 100, 165, 205, 250, 290, 385]
_ENTGELT = ([(40, 160, "Abrechnung der Brutto/Netto-Bezüge für November 2026", 11)]
            + _tabelle(185, _EXS, [["Personal-Nr.", "Geburtsdatum", "StKl", "Ki.Frbtr.", "Konf.", "SV-Nummer",
                                    "Krankenkasse"]], 7)
            + _tabelle(197, _EXS, [["00471", "17.09.1966", "3", "1,0", "rk", "65170966G014", "AOK Bayern"]], 8.5)
            + _tabelle(220, _EXS, [["Eintritt", "Steuer-ID", "", "", "", "Beitragsgruppe", "Resturlaub"]], 7)
            + _tabelle(232, _EXS, [["01.04.2009", "52 918 304 620", "", "", "", "1111", "12,5 Tage"]], 8.5))


def test_befund_93_kastenformular_naechste_etikettzeile_beendet_die_tabelle(tmp_path):
    funde = _funde(_pdf(tmp_path / "kasten.pdf", _KASTEN3))
    paare = {(f["kategorie"], st["text"]) for f in funde for st in f["stellen"] if st.get("an", True)}
    assert ("arbeitgeber", "Kreditinstitut") not in paare, paare
    assert ("arbeitgeber", "Sparkasse Altötting-Mühldorf") not in paare, paare
    assert not _beruehrt(funde, "Beruf") and not _beruehrt(funde, "Kreditinstitut"), _stellen(funde)
    # die Werte des Kastenformulars bleiben erkannt
    for wert in ("Pichlmeier", "Notburga", "02.08.1958", "Am Gänsbichl 4", "84453", "Mühldorf a. Inn",
                 "08631 98765", "Pflegehelferin", "Seniorenstift St. Josef", "DE97 7115 0000 0020 3040 50"):
        assert _gedeckt(funde, wert), (wert, _stellen(funde))


def test_befund_93_beruf_im_kastenformular_ist_kein_arbeitgeber(tmp_path):
    """Die Etikettzeile "Beruf des Ehepartners ⇥⇥ Beruf" beginnt einen neuen Kopf: weder das Etikett "Beruf" noch der
    Beruf darunter werden zum Arbeitgeber der Spalte "Arbeitgeber" darüber."""
    funde = _funde(_pdf(tmp_path / "beruf.pdf", _BERUF))
    paare = {(f["kategorie"], st["text"]) for f in funde for st in f["stellen"] if st.get("an", True)}
    assert ("arbeitgeber", "Beruf") not in paare and ("arbeitgeber", "Pflegehelferin") not in paare, paare
    assert not _beruehrt(funde, "Beruf") and not _beruehrt(funde, "Ausgeübter"), _stellen(funde)
    for wert in ("Pichlmeier", "02.08.1958", "Seniorenstift St. Josef"):
        assert _gedeckt(funde, wert), (wert, _stellen(funde))


def test_befund_93_beruf_unter_etikett_mit_genitiv(tmp_path):
    """Jede Zelle unter einem Beruf-Etikett ist ein Beruf – auch unter "Beruf des Ehepartners" (Etikett mit
    Genitiv). Ohne den Fehlverdacht auf "Ausgeübter" fiel "Erzieherin" sonst nicht mehr auf."""
    funde = _funde(_pdf(tmp_path / "beruf.pdf", _BERUF))
    assert _gedeckt(funde, "Erzieherin", "beruf") and _gedeckt(funde, "Pflegehelferin", "beruf"), _stellen(funde)
    assert not _beruehrt(funde, "Ehepartners"), _stellen(funde)


@pytest.mark.parametrize("text, beruf", [
    ("Beruf des Ehepartners: Erzieherin", "Erzieherin"),
    ("Beruf der versicherten Person\nSchreiner", "Schreiner"),
    ("Name des Ehepartners\t\tBeruf des Ehepartners\nWalburga Oberprieler\t\tSteuerfachangestellte",
     "Steuerfachangestellte"),
])
def test_befund_93_beruf_etikett_mit_genitiv_als_text(text, beruf):
    funde = analysiere_text(text, ALLE, [], [])
    assert _gedeckt(funde, beruf, "beruf"), _stellen(funde)


@pytest.mark.parametrize("text", ["Der Beruf des Vaters spielt für den Tarif keine Rolle.",
                                  "Tätigkeit der Gesellschaft: Großhandel mit Baustoffen",
                                  "Berufsunfähigkeit der versicherten Person: ausgeschlossen"])
def test_befund_93_gegenproben_genitiv_ohne_beruf(text):
    funde = analysiere_text(text, ALLE, [], [])
    assert not _stellen(funde, "beruf"), _stellen(funde)


@pytest.mark.parametrize("text", ["08631 98765\nBeruf (genaue Tätigkeit)\nPflegehelferin",
                                  "Telefon\n08024 47119\nTätigkeit\nDachdecker",
                                  "Fax\n089 456712\nSparte\nKfz"])
def test_befund_93_musterspanne_nicht_ueber_den_umbruch_ins_etikett(text):
    funde = analysiere_text(text, ALLE, [], [])
    for f in funde:
        for st in f["stellen"]:
            assert "\n" not in st["text"], (f["kategorie"], st["text"])
    for etikett in ("Beruf", "Tätigkeit", "Sparte"):
        if etikett in text:
            assert not _beruehrt(funde, etikett), _stellen(funde)


def test_befund_93_entgeltabrechnung_zweite_kopfzeile(tmp_path):
    funde = _funde(_pdf(tmp_path / "entgelt.pdf", _ENTGELT))
    paare = {(f["kategorie"], st["text"]) for f in funde for st in f["stellen"] if st.get("an", True)}
    assert ("svnr", "1111") not in paare, paare
    assert not _beruehrt(funde, "Bayern"), _stellen(funde)
    for wert in ("00471", "17.09.1966", "65170966G014", "52 918 304 620"):
        assert _gedeckt(funde, wert), (wert, _stellen(funde))
    # Eintrittsdatum: kein Geburtsdatum, auch nicht für die Selbstkontrolle
    verdacht = _verdacht_pdf(_pdf(tmp_path / "entgelt2.pdf", _ENTGELT))
    assert not _gemeldet(verdacht, "01.04.2009"), verdacht


# ----------------------------------------------------------------------
# Befund 85: leichte Schräglage bei Einzugsscans (0,5–1,5°)
# ----------------------------------------------------------------------
_BESTAND = ([(36, 50, "Anlage zum Maklerauftrag – Übertragung der Betreuung (Vertragsliste)", 11)]
            + _tabelle(80, [36, 130, 210, 270, 400, 470],
                       [["Gesellschaft", "Vers.-Nr.", "Sparte", "Versicherungsnehmer", "geb. am", "Ablauf"],
                        ["Musterland Leben", "4471 0815 22", "Rente", "Gstettner, Severin", "17.09.1966",
                         "01.10.2031"],
                        ["Beispiel Sach AG", "SH-88 1294 7", "Hausrat", "Gstettner, Afra", "21.06.1969",
                         "01.01.2027"],
                        ["Muster Kranken", "K 7712 3450", "PKV", "Gstettner, Severin", "17.09.1966", "–"]], 8, 12.8)
            + [(36, 160, "Hiermit beauftrage ich den Makler, die Betreuung der o. g. Verträge zu übernehmen.", 9)])


def _scan(vorlage, pfad, winkel, dpi=200):
    """Scan-Seite wie im Harness der Durchsicht: Graustufen-Rendering, um `winkel` Grad gedreht (Einzugsscanner)."""
    from PIL import Image
    with fitz.open(vorlage) as d:
        pix = d[0].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    if winkel:
        img = img.rotate(winkel, expand=False, fillcolor=255, resample=Image.BICUBIC)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    seite.insert_image(seite.rect, stream=buf.getvalue())
    doc.save(pfad)
    doc.close()
    return pfad


@pytest.fixture(scope="module")
def ocr_dienst():
    from anonymisierer.ocr import OcrDienst
    with OcrDienst(prozesse=1) as dienst:
        yield dienst


@braucht_ocr
@pytest.mark.parametrize("winkel", [0.8, -0.8, 0.6])
def test_befund_85_kastenformular_schief_gescannt(tmp_path, ocr_dienst, winkel):
    vorlage = _pdf(tmp_path / "kasten.pdf", _KASTEN3)
    funde = _funde(_scan(vorlage, tmp_path / "scan.pdf", winkel), ocr=ocr_dienst)
    for wert in ("84453", "Mühldorf", "Seniorenstift", "Pichlmeier", "02.08.1958"):
        assert _gedeckt(funde, wert), (winkel, wert, _stellen(funde))


@braucht_ocr
@pytest.mark.parametrize("winkel", [0.8, 0.6])
def test_befund_85_vertragsliste_schief_gescannt(tmp_path, ocr_dienst, winkel):
    # Schrift und Zeilenabstand wie die Falldateien der Durchsicht (DejaVu Sans, 1,6 × 8 pt; unter Windows Arial o. ä.)
    schrift = schrift_mit_zeichen("".join(e[2] for e in _BESTAND))
    vorlage = _pdf(tmp_path / "bestand.pdf", _BESTAND, schrift)
    funde = _funde(_scan(vorlage, tmp_path / "scan.pdf", winkel), ocr=ocr_dienst)
    for wert in ("21.06.1969", "17.09.1966", "Gstettner"):
        assert _gedeckt(funde, wert), (winkel, wert, _stellen(funde))
    texte = " ".join(_stellen(funde))
    for ziffern in ("1294", "7712"):
        assert ziffern in texte, (winkel, ziffern, _stellen(funde))


@braucht_ocr
def test_befund_85_gerader_scan_unveraendert(tmp_path, ocr_dienst):
    """Gegenprobe: ein gerader Scan wird nicht gedreht gelesen und bleibt vollständig erkannt."""
    vorlage = _pdf(tmp_path / "kasten.pdf", _KASTEN3)
    erg = analysiere_pdf(_scan(vorlage, tmp_path / "scan.pdf", 0.0), ALLE, [], [], ocr=ocr_dienst)
    for wert in ("84453", "Mühldorf", "Seniorenstift", "Pichlmeier", "02.08.1958", "Am Gänsbichl 4"):
        assert _gedeckt(erg["funde"], wert), (wert, _stellen(erg["funde"]))
    for etikett in ("Kreditinstitut", "PLZ"):              # Etiketten der nächsten Zeile sind keine Werte
        assert not _beruehrt(erg["funde"], etikett), _stellen(erg["funde"])
    seite = erg["modell"].seiten[0]
    assert seite.ocr_schraeg == 0.0, "gerader Scan: keine Neigung"
