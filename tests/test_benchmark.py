"""Entwicklungs-Benchmark (werkzeuge/benchmark) im CI-Format.

* Generator: Prüfziffern, Determinismus, Plausibilität der Wahrheit, Kollisionsprüfung – ohne Modell/OCR.
* Bewertung: 12 erzeugte Dokumente (darunter 2 Scans und 1 AcroForm-Formular) laufen durch die echte
  Pipeline (analysiere_pdf -> schwaerze_pdf wie die Oberfläche); geprüft wird die Ausgabe über alle
  Kanäle. Die Qualitätsgrenzen liegen knapp unter den zuletzt gemessenen Werten – eine Verschlechterung
  der Erkennung oder Schwärzung lässt den Test scheitern. Wer die Erkennung verbessert, zieht die Grenzen
  hier nach (Messwerte stehen im Kommentar).

Alle erzeugten Dateien landen im tmp_path.
"""

import datetime
import json
import random

import pytest

from conftest import braucht_modell, braucht_ocr
from werkzeuge.benchmark import bewertung, generator, kennungen
from werkzeuge.benchmark.bausteine import Dok, stil_waehlen
from werkzeuge.benchmark.normalisierung import Gefaltet, signifikante_token
from werkzeuge.benchmark.satz import m

ANZAHL_CI = 12
SEED_CI = 1
# Gemessen am 2026-11-09 auf Commit 4e4a769 (Linux, PyMuPDF 2.1, de_core_news_md 3.8.0, ohne
# Tesseract-Kommandozeile): recall_kern 0,7231 (269/372), Über-Schwärzung 0,0417 (9/216).
# Spielraum für Abweichungen zwischen Plattformen (Schriften, OCR-Build): ~2,3 Prozentpunkte
# (≈ 8 Einträge) bzw. ~2,3 Prozentpunkte (≈ 5 Einträge).
MIN_RECALL_KERN = 0.70
MAX_UEBERSCHWAERZUNG = 0.065


# ----------------------------------------------------------------------
# Generator (ohne Modell und OCR)
# ----------------------------------------------------------------------
def test_kennungen_haben_gueltige_pruefziffern():
    rng = random.Random(3)
    for land in kennungen.IBAN_LAENGE:
        for _ in range(20):
            iban = kennungen.iban(rng, land)
            assert kennungen.iban_gueltig(iban) and len(iban) == kennungen.IBAN_LAENGE[land]
    from anonymisierer.muster import _luhn_gueltig, _steuer_id_gueltig, _steuer_id_struktur
    for _ in range(200):
        sid = kennungen.steuer_id(rng)
        assert _steuer_id_gueltig(sid) and _steuer_id_struktur(sid)
        assert _luhn_gueltig(kennungen.kreditkarte(rng)[1])
    # Dokumentierte Beispiele: SV-Nummer 15 070649 C 10[3], Ausweis L01X00T47[1]
    assert kennungen.sv_pruefziffer("15070649C10") == 3
    assert kennungen.icao_pruefziffer("L01X00T47") == 1
    geb = datetime.date(1975, 3, 3)
    sv = kennungen.sv_nummer(rng, geb, "Mustermann", "w")
    assert sv[2:8] == "030375" and sv[8] == "M" and int(sv[9:11]) >= 50
    assert kennungen.sv_pruefziffer(sv[:11]) == int(sv[11])


def test_normalisierung_wortgrenzen_und_diakritika():
    text = Gefaltet("Herr Şahin, Muster-\nmann, Nürnberger Str. 5, IBAN DE89 3704 0044")
    assert text.enthaelt(Gefaltet("Sahin"))                  # Diakritika gefaltet
    assert text.enthaelt(Gefaltet("Mustermann"))             # Silbentrennung überbrückt
    assert text.enthaelt(Gefaltet("DE8937040044"))           # Leerraum egal
    assert not text.enthaelt(Gefaltet("Nürnberg"))           # aber nur an Wortgrenzen
    assert signifikante_token("Dr. med. Hans-Peter von der Heyde") == ["hans", "peter", "heyde"]
    assert signifikante_token("Am Alten Bahnhof 3") == ["bahnhof"]


def test_rohdaten_zeichenketten_werden_dekodiert():
    """Rohdaten-Kanal: TJ-Felder zusammensetzen, Oktal-Escapes und UTF-16 dekodieren, Glyphen-Nummern
    (Identity-H) nicht als Text lesen."""
    strom = (rb"BT [(Muster) -20 (mann)] TJ (M\374ller) Tj <FEFF0047007200F600DF> Tj "
             rb"<00410042004300440045> Tj ET")
    texte = bewertung.zeichenketten(strom)
    assert "Mustermann" in texte and "Müller" in texte and "Größ" in texte
    assert not any("ABCDE" in t for t in texte)


def test_plan_deckt_typen_scans_und_formular_ab():
    klein = generator.plane_korpus(ANZAHL_CI, SEED_CI)
    assert sum(1 for p in klein if p.scan) >= 2
    assert any(p.typ == "antrag_formular" and not p.scan for p in klein)
    gross = generator.plane_korpus(80, 1)
    assert {p.typ for p in gross} == set(generator.TYPEN)
    assert {p.scan for p in gross if p.scan} >= set(generator.SCAN_VARIANTEN) | {"gemischt"}
    assert all(any(k in p.neben for p in gross) for k in generator.NEBENKANAELE)


def test_kollision_mit_klartext_wird_erkannt():
    dok = Dok(random.Random(1), "t", stil=stil_waehlen(random.Random(1), familie="helv"))
    seite = dok.satz.neue_seite()
    seite.text(50, 80, "Das dauert so lange wie nötig, sagte " + m("namen", "Lange", "Test"), dok.stil.normal, 10)
    assert generator.kollisionen(dok) == ["Lange"]


@pytest.fixture(scope="module")
def ci_korpus(tmp_path_factory):
    ordner = tmp_path_factory.mktemp("benchmark") / "korpus"
    wahrheiten = generator.erzeuge_korpus(ordner, ANZAHL_CI, SEED_CI)
    return ordner, wahrheiten


def test_korpus_und_wahrheit_sind_schemakonform(ci_korpus):
    ordner, wahrheiten = ci_korpus
    assert len(wahrheiten) == ANZAHL_CI
    for w in wahrheiten:
        assert (ordner / w["dokument"]).exists()
        datei = ordner / (w["dokument"][:-4] + ".wahrheit.json")
        gespeichert = json.loads(datei.read_text(encoding="utf-8"))
        assert set(gespeichert) >= {"dokument", "typ", "seiten", "merkmale", "eintraege"}
        for e in gespeichert["eintraege"]:
            assert e["erwartung"] in ("schwaerzen", "behalten")
            assert e["umfang"] in ("kern", "erweitert")
            assert e["kanal"] in ("text", "formular", "scan", "anmerkung", "metadaten", "lesezeichen", "anhang",
                                  "dateiname")
            assert e["text"].strip() and e["seite"] >= 1
    merkmale = {m for w in wahrheiten for m in w["merkmale"]}
    assert {"scan", "formular", "tabelle", "silbentrennung", "versalien"} <= merkmale
    kategorien = {e["kategorie"] for w in wahrheiten for e in w["eintraege"]}
    assert {"namen", "strasse", "plzort", "geburt", "telefon", "email", "iban", "vertrag", "kfz"} <= kategorien


def test_wahrheit_passt_zum_original(ci_korpus):
    """Jeder Eintrag steht im Original in seinem Kanal (Textebene der Seite, Tinte im Scan-Wortrechteck,
    Metadaten …) – sonst wären Lecks/Entfernungen nicht messbar."""
    ordner, wahrheiten = ci_korpus
    probleme = []
    for w in wahrheiten:
        probleme += bewertung.pruefe_wahrheit(ordner / w["dokument"], w)
    assert probleme == []


def test_generator_ist_deterministisch(tmp_path, ci_korpus):
    ordner, _ = ci_korpus
    for plan in generator.plane_korpus(4, SEED_CI):
        w = generator.erzeuge_dokument(plan, SEED_CI, tmp_path)
        original = json.loads((ordner / (w["dokument"][:-4] + ".wahrheit.json")).read_text(encoding="utf-8"))
        assert w["eintraege"] == original["eintraege"]
        assert (tmp_path / w["dokument"]).read_bytes() == (ordner / w["dokument"]).read_bytes()


# ----------------------------------------------------------------------
# Bewertung mit der echten Pipeline (Modell + OCR nötig)
# ----------------------------------------------------------------------
@braucht_modell
@braucht_ocr
def test_benchmark_laeuft_und_haelt_qualitaetsgrenzen(ci_korpus, tmp_path):
    ordner, wahrheiten = ci_korpus
    ergebnis = bewertung.bewerte_korpus(ordner, tmp_path / "ergebnis", cli_ocr=False, melde=None)
    assert (tmp_path / "ergebnis" / "ergebnis.json").exists()
    assert "recall_kern" in (tmp_path / "ergebnis" / "bericht.md").read_text(encoding="utf-8")
    g = ergebnis["gesamt"]
    assert g["dokumente"] == ANZAHL_CI
    assert g["dokumente_mit_fehler"] == 0, [d["fehler"] for d in ergebnis["dokumente"] if d["fehler"]]
    assert g["dokumente_ohne_ausgabe"] == 0
    # Scans wurden per OCR und Pixelvergleich geprüft, das Formular über die Kanäle
    scan_docs = [d for d in ergebnis["dokumente"] if "scan" in d["merkmale"]]
    assert len(scan_docs) >= 2 and all(d["ocr_seiten_bewertung"] and d["pixel_seiten"] for d in scan_docs)
    assert any("formular" in d["merkmale"] for d in ergebnis["dokumente"])
    # Qualitätsgrenzen (Regressionen lassen den Test scheitern)
    assert g["recall_kern"] >= MIN_RECALL_KERN, (
        f"recall_kern {g['recall_kern']:.4f} < {MIN_RECALL_KERN} – Erkennung/Schwärzung schlechter geworden? "
        f"Lecks: {[(l['dokument'], l['text']) for l in ergebnis['lecks'][:15]]}")
    assert g["ueberschwaerzung"] <= MAX_UEBERSCHWAERZUNG, (
        f"Über-Schwärzung {g['ueberschwaerzung']:.4f} > {MAX_UEBERSCHWAERZUNG}: "
        f"{[(u['dokument'], u['text']) for u in ergebnis['ueberschwaerzt']]}")
