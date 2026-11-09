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


def _pdf(pfad: Path, zeilen):
    doc = fitz.open()
    seite = doc.new_page()
    y = 80
    for z in zeilen:
        seite.insert_text((60, y), z, fontsize=10, fontname="helv")
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
    # temporäre Ausgaben gelöscht, im Eingabeordner nichts entstanden
    assert erzeugt and not any(p.exists() for p in erzeugt)
    assert sorted(p.name for p in ordner.rglob("*")) == sorted(
        ["Mustermann_Erika_Police_47.897.336.2.pdf", "Kowalczyk", "Bergisch Gladbach 2520868691.pdf"])


def test_selbsttest_behalten_legt_ausgaben_ab(tmp_path, capsys):
    ordner = _ordner(tmp_path)
    ziel = tmp_path / "ausgaben"
    werte = selbsttest.selbsttest(ordner, behalten=ziel, kategorien="iban,telefon,email,vertrag",
                                  ausgabe=lambda zeile: None)
    assert werte["dokumente"] == 2 and werte["seiten"] == 2 and not werte["fehler"]
    assert werte["funde"]["iban"] == 1 and werte["pruefen"] + werte["fertig"] == 2
    assert len(list(ziel.glob("anonym_*.pdf"))) == 2 and (ziel / "_zuordnung.txt").exists()
    assert capsys.readouterr().out == ""


def test_regelnamen_ohne_dokumentinhalt():
    assert selbsttest._regel("Wert hinter Etikett »Kundennummer«") == "Wert hinter Etikett"
    assert selbsttest._regel("Formularfeld »Wohnort Mustermann« nicht geschwärzt") == "Formularfeld nicht geschwärzt"
