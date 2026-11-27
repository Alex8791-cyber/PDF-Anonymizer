"""Tests für werkzeuge/selbsttest.py: Selbsttest mit echten Dokumenten – nur Zählwerte, nie Inhalte.

Geprüft wird mit synthetischen PDFs, deren Inhalt UND Dateinamen personenbezogen aussehen: Nichts davon darf in
stdout/stderr auftauchen, temporäre Ausgaben verschwinden, im Eingabeordner entsteht nichts.
"""

import tempfile
from pathlib import Path

import pymupdf as fitz

from werkzeuge import selbsttest

GEHEIM = ["Mustermann", "Erika", "DE89 3704 0044 0532 0130 00", "DE89370400440532013000", "0911 1234567",
          "erika.mustermann@example.org", "47.897.336.2", "2520868691", "Bergisch Gladbach", "Kowalczyk"]


def _pdf(pfad: Path, zeilen, schrift=10):
    doc = fitz.open()
    seite = doc.new_page()
    y = 80
    for z in zeilen:
        seite.insert_text((60, y), z, fontsize=schrift, fontname="helv")
        y += 16
    doc.save(pfad)
    doc.close()


def _ordner(tmp_path) -> Path:
    ordner = tmp_path / "Kunden Mustermann Erika"
    (ordner / "Kowalczyk").mkdir(parents=True)
    _pdf(ordner / "Mustermann_Erika_Police_47.897.336.2.pdf",
         ["Versicherungsnehmerin: Erika Mustermann", "IBAN DE89 3704 0044 0532 0130 00",
          "Telefon 0911 1234567, E-Mail erika.mustermann@example.org", "Vertragsnummer 47.897.336.2"])
    _pdf(ordner / "Kowalczyk" / "Bergisch Gladbach 2520868691.pdf",
         ["Sehr geehrte Damen und Herren,", "die Kundennummer 2520868691 gehört nach Bergisch Gladbach.",
          "Mit freundlichen Grüßen"])
    return ordner


def test_selbsttest_gibt_keine_inhalte_aus_und_raeumt_auf(tmp_path, capsys, monkeypatch):
    ordner = _ordner(tmp_path)
    arbeits = tmp_path / "arbeits"
    arbeits.mkdir()
    erzeugt = []
    original = tempfile.mkdtemp

    def mkdtemp(prefix="", **_):
        p = Path(original(prefix=prefix, dir=arbeits))
        erzeugt.append(p)
        return str(p)
    monkeypatch.setattr(selbsttest.tempfile, "mkdtemp", mkdtemp)
    assert selbsttest.main([str(ordner), "--kategorien", "iban,telefon,email,vertrag"]) == 0
    aus = capsys.readouterr()
    text = aus.out + aus.err
    for geheim in GEHEIM + [str(ordner), ordner.name]:
        assert geheim not in text, geheim
    assert "Dokumente: 2" in text and "Funde je Kategorie:" in text and "Verdachtsstellen:" in text
    assert "Ausgaben:" in text and "Fehler: keine" in text and "Laufzeit:" in text
    # Nicht erkannte Werte (keine Namen-Erkennung) melden sich als Verdacht -> _PRUEFEN
    assert "_PRUEFEN" in text
    # temporäre Ausgaben gelöscht – auch die Zuordnungsdatei, die NEBEN dem Ausgabeordner liegt (M-25: sie enthält die
    # Original-Dateinamen) –, im Eingabeordner nichts entstanden
    assert erzeugt and not any(p.exists() for p in erzeugt)
    assert list(arbeits.iterdir()) == []
    assert sorted(p.name for p in ordner.rglob("*")) == sorted(
        ["Mustermann_Erika_Police_47.897.336.2.pdf", "Kowalczyk", "Bergisch Gladbach 2520868691.pdf"])


def test_selbsttest_behalten_legt_ausgaben_ab(tmp_path, capsys):
    ordner = _ordner(tmp_path)
    ziel = tmp_path / "ausgaben"
    werte = selbsttest.selbsttest(ordner, behalten=ziel, kategorien="iban,telefon,email,vertrag",
                                  ausgabe=lambda zeile: None)
    assert werte["dokumente"] == 2 and werte["seiten"] == 2 and not werte["fehler"]
    assert werte["funde"]["iban"] == 1 and werte["pruefen"] + werte["fertig"] == 2
    from anonymisierer import schwaerzung
    assert len(list(ziel.glob("anonym_*.pdf"))) == 2 and schwaerzung.zuordnung_pfad(ziel).exists()
    assert capsys.readouterr().out == ""


def test_selbsttest_schwaerzt_auch_dateien_ohne_fund(tmp_path):
    """Runde 3: jede lesbare PDF bekommt eine bereinigte Ausgabe – der Selbsttest zählt sie wie die Oberfläche (früher:
    „keine Ausgabe (kein Fund)“, die Datei wurde gar nicht geschwärzt und ihr Status nicht gemessen)."""
    ordner = tmp_path / "Ordner"
    ordner.mkdir()
    _pdf(ordner / "Bedingungen.pdf", ["Allgemeine Versicherungsbedingungen", "Es gelten die gesetzlichen Bestimmungen."])
    ziel = tmp_path / "ausgaben"
    werte = selbsttest.selbsttest(ordner, behalten=ziel, kategorien="iban,telefon,email,vertrag",
                                  ausgabe=lambda zeile: None)
    assert werte["dokumente"] == 1 and werte["ohne_ausgabe"] == 0 and not werte["fehler"]
    assert werte["fertig"] + werte["pruefen"] == 1 and len(list(ziel.glob("anonym_*.pdf"))) == 1
    assert werte["meldungen"]["NICHTS_GESCHWAERZT"] == 1


def test_selbsttest_gibt_ganz_abgewaehlte_funde_mit_anders_als_die_oberflaeche(tmp_path):
    """Durchsicht der Doku (README „Werkzeuge“, Modulkopf von selbsttest.py): Der Selbsttest nimmt nicht ganz den Weg
    der Oberfläche. Er gibt alle Funde der Analyse an die Schwärzung, auch ganz abgewählte (die Oberfläche lässt sie
    weg, auftrag.auftrag_funde), und schwärzt ohne „Freigabe vor Weitergabe“. Die nicht angehakte „vermutlich
    Firmenanschrift“ im Briefkopf einer Selbständigen (Name nicht in den Wortlisten) kommt dort als abgewählte Stelle
    an: In der Oberfläche ist die lesbare Anschrift ein Verdacht, im Selbsttest nicht – er zählt die Ausgabe als
    „fertig“. Schwärzt der Selbsttest einmal wie die Oberfläche (auftrag.standard_auftrag), README und Modulkopf
    anpassen und diesen Test umdrehen."""
    from anonymisierer import analyse, auftrag
    from anonymisierer.schwaerzung import schwaerze_pdf

    ordner = tmp_path / "Ordner"
    ordner.mkdir()
    pdf = ordner / "Kuendigung.pdf"
    _pdf(pdf, ["Tjorven Quaasdorf · Fotografie", "Hauptstraße 12 · 10115 Berlin",
               "Tel. 030 1234567 · www.quaasdorf-foto.de", "", "", "Muster Versicherung AG", "Kundenservice",
               "Postfach 10 11 12", "20007 Hamburg", "", "Kündigung meiner Berufshaftpflicht", "",
               "Sehr geehrte Damen und Herren,", "hiermit kündige ich meine Versicherung zum 31.12.2024.", "",
               "Mit freundlichen Grüßen"], schrift=11)
    anschrift = {"Hauptstraße 12", "10115 Berlin"}
    # Weg der Oberfläche (Einstellungen wie beim ersten Start, Häkchen wie nach der Analyse)
    e = analyse.analysiere_pdf(pdf, auftrag.standard_kategorien(), [], [], profil=auftrag.STANDARD_PROFIL)
    assert anschrift <= {f["text"] for f in e["funde"] if f["hinweis"] == analyse.HINWEIS_FIRMENANSCHRIFT}
    a, _ = auftrag.standard_auftrag(e, schwaerze_pdf)
    parameter = auftrag.schwaerz_parameter(a, auftrag.STANDARD_FREIGABE, auftrag.STANDARD_PROFIL, schwaerze_pdf)
    s = schwaerze_pdf(pdf, a["funde"], ziel_ordner=tmp_path / "oberflaeche", **parameter)
    assert anschrift <= {v.text for v in s["verdacht"]}, s["verdacht"]
    # Selbsttest: dieselbe Anschrift bleibt ebenso lesbar, aber ohne Verdacht
    ziel = tmp_path / "selbsttest"
    werte = selbsttest.selbsttest(ordner, behalten=ziel, ausgabe=lambda zeile: None)
    assert werte["verdacht_je_dokument"] == [0] and werte["fertig"] == 1 and werte["pruefen"] == 0, werte
    [ausgabe] = ziel.glob("anonym_*.pdf")
    with fitz.open(ausgabe) as doc:
        assert all(teil in doc[0].get_text() for teil in anschrift)


def test_regelnamen_ohne_dokumentinhalt():
    assert selbsttest._regel("Wert hinter Etikett »Kundennummer«") == "Wert hinter Etikett"
    assert selbsttest._regel("Formularfeld »Wohnort Mustermann« nicht geschwärzt") == "Formularfeld nicht geschwärzt"
