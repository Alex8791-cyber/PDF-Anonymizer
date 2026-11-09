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
from pathlib import Path
import os
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
# Restrisiko-Prüfung (Vertrag Abschnitt 7), gemessen am 2026-11-09 (Linux): 0 Dokumente mit stillem Leck,
# Verdachtsabdeckung 0,973 (73/75; die 2 fehlenden sind reine Pixelreste), 0,0 Fehlverdacht je Seite, 10 von 12
# Ausgaben _PRUEFEN. Spielraum für Plattform-Abweichungen (Schriften, OCR-Build).
MAX_DOKUMENTE_STILLES_LECK = 1
MIN_VERDACHTSABDECKUNG = 0.90
MAX_FEHLVERDACHT_JE_SEITE = 1.0


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
    # In der CI den vollständigen Bericht sichern (auch wenn die Prüfungen unten scheitern), damit
    # plattformabhängige Abweichungen (z. B. Windows) nachvollziehbar sind.
    ziel = os.environ.get("PDF_ANONYMISIERER_BERICHT")
    if ziel:
        import shutil
        import sys
        ablage = Path(ziel) / f"benchmark_{sys.platform}"
        shutil.copytree(tmp_path / "ergebnis", ablage, dirs_exist_ok=True)
        shutil.copytree(ordner, ablage / "korpus", dirs_exist_ok=True)
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
    # Kein stilles Leck: was die Erkennung verpasst, meldet die Restrisiko-Prüfung (Ausgabe _PRUEFEN)
    rr = ergebnis["restrisiko"]
    assert all(d["status_ausgabe"] in ("fertig", "pruefen") for d in ergebnis["dokumente"])
    assert rr["dokumente_mit_stillem_leck"] <= MAX_DOKUMENTE_STILLES_LECK, (
        f"stille Lecks in {rr['dokumente_still']}: "
        f"{[(x['dokument'], x['text']) for x in rr['nicht_abgedeckt'] if not x['ausgabe_pruefen']][:15]}")
    assert rr["verdachtsabdeckung"] >= MIN_VERDACHTSABDECKUNG, (
        f"Verdachtsabdeckung {rr['verdachtsabdeckung']}: {[(x['dokument'], x['text']) for x in rr['nicht_abgedeckt']]}")
    assert rr["fehlverdacht_je_seite"] <= MAX_FEHLVERDACHT_JE_SEITE, rr["fehlverdacht_liste"][:15]
    assert "## Restrisiko" in (tmp_path / "ergebnis" / "bericht.md").read_text(encoding="utf-8")


def test_restrisiko_kennzahlen_aus_dokumenten():
    """Stille Lecks, Abdeckung, Fehlverdacht und _PRUEFEN ohne Leck aus bewerteten Dokumenten (ohne Pipeline)."""
    def eintrag(i, status, text, kategorie="namen", umfang="kern", reste=(), pixel=None):
        return {"id": f"e{i}", "text": text, "kategorie": kategorie, "seite": 1, "erwartung": "schwaerzen",
                "umfang": umfang, "kanal": "text", "status": status, "reste": [list(r) for r in reste],
                "pixel": pixel, "bemerkung": ""}
    wahr = [{"id": "e1", "woerter": [[100, 100, 150, 110, "Mustermann"]]},
            {"id": "e2", "woerter": [[100, 200, 160, 210, "2520868691"]]},
            {"id": "e3", "woerter": [[100, 300, 140, 310, "Erika"]]}]
    still = {"dokument": "a.pdf", "seiten": 1, "status_ausgabe": "fertig", "verdacht": [], "reste_verdacht": [],
             "eintraege": [eintrag(1, "leck", "Mustermann"), eintrag(2, "entfernt", "2520868691", "vertrag")]}
    gemeldet = {"dokument": "b.pdf", "seiten": 2, "status_ausgabe": "pruefen", "reste_verdacht": [],
                "verdacht": [{"seite": 0, "start": 5, "ende": 15, "text": "2520868691", "grund": "Ziffernfolge",
                              "rechtecke": [[101, 201, 159, 209]]},
                             {"seite": 1, "start": 0, "ende": 4, "text": "Bonn", "grund": "Ort",
                              "rechtecke": [[10, 10, 30, 20]]}],
                "eintraege": [eintrag(1, "entfernt", "Mustermann"), eintrag(2, "leck", "2520868691", "vertrag"),
                              eintrag(3, "teilweise", "Erika", reste=[("erika", "pixel")], pixel=[["Erika", 0.4]])]}
    leer = {"dokument": "c.pdf", "seiten": 1, "status_ausgabe": "pruefen", "verdacht": [], "reste_verdacht": [],
            "eintraege": [eintrag(1, "entfernt", "Mustermann")]}
    for d in (still, gemeldet, leer):
        bewertung.verdacht_bewerten(d, d["eintraege"], wahr)
    assert gemeldet["verdacht"][0]["trifft"] is True and gemeldet["verdacht"][1]["trifft"] is False
    rr = bewertung.restrisiko_kennzahlen([still, gemeldet, leer])
    assert rr["stille_lecks"] == 1 and rr["dokumente_still"] == ["a.pdf"]
    assert rr["kern_lecks"] == 3 and rr["kern_lecks_abgedeckt"] == 1 and rr["verdachtsabdeckung"] == round(1 / 3, 4)
    assert rr["kern_lecks_ohne_pixelrest"] == 2 and rr["verdachtsabdeckung_ohne_pixelrest"] == 0.5
    assert rr["fehlverdacht"] == 1 and rr["fehlverdacht_je_seite"] == 0.25
    assert rr["ausgaben_pruefen"] == 2 and rr["pruefen_ohne_leck"] == 1 and rr["pruefen_ohne_leck_dokumente"] == ["c.pdf"]
    # Verdacht (NamedTuple des Programms) wird JSON-tauglich
    from anonymisierer.restrisiko import Verdacht
    import pymupdf as fitz
    v = bewertung.verdacht_serialisieren(Verdacht(0, 1, 5, "Text", "Grund", [fitz.Rect(1, 2, 3, 4)]))
    assert v == {"seite": 0, "start": 1, "ende": 5, "text": "Text", "grund": "Grund", "rechtecke": [[1.0, 2.0, 3.0, 4.0]]}
    json.dumps(v)


def test_tesseract_kommandozeile_mit_einem_openmp_thread(tmp_path, monkeypatch):
    """Die zweite Leseart (Tesseract-Kommandozeile) läuft mit OMP_THREAD_LIMIT=1 – auf ausgelasteten Rechnern
    warten mehrere OpenMP-Threads sonst aktiv aufeinander und die Seite läuft in den Timeout. Ein vom Aufrufer
    gesetzter Wert bleibt erhalten."""
    import pymupdf as fitz
    aufrufe = []

    class Lauf:
        stdout = "Text"

    def run(befehl, **kwargs):
        aufrufe.append(kwargs.get("env"))
        return Lauf()

    monkeypatch.setattr(bewertung, "tesseract_cli", lambda: "tesseract")
    monkeypatch.setattr(bewertung.subprocess, "run", run)
    doc = fitz.open()
    seite = doc.new_page(width=100, height=100)
    monkeypatch.delenv("OMP_THREAD_LIMIT", raising=False)
    assert bewertung.ocr_cli(seite, 0, tmp_path) == "Text"
    monkeypatch.setenv("OMP_THREAD_LIMIT", "3")
    bewertung.ocr_cli(seite, 0, tmp_path)
    doc.close()
    assert [a.get("OMP_THREAD_LIMIT") for a in aufrufe] == ["1", "3"]
    assert not list(tmp_path.iterdir()), "Seitenbild wird gelöscht"
