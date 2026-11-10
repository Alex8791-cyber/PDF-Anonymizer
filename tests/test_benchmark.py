"""Entwicklungs-Benchmark (werkzeuge/benchmark) im CI-Format.

* Generator: Prüfziffern, Determinismus, Plausibilität der Wahrheit, Kollisionsprüfung – ohne Modell/OCR.
* Bewertung: 12 erzeugte Dokumente (darunter 2 Scans und 1 AcroForm-Formular) laufen durch die echte
  Pipeline (analysiere_pdf -> schwaerze_pdf wie die Oberfläche); geprüft wird die Ausgabe über alle
  Kanäle. Die Qualitätsgrenzen liegen knapp unter den zuletzt gemessenen Werten – eine Verschlechterung
  der Erkennung oder Schwärzung lässt den Test scheitern. Wer die Erkennung verbessert, zieht die Grenzen
  hier nach (Messwerte stehen im Kommentar).
* Selbstprüfung der Bewertung: Null-Anonymisierer (Ausgabe = Original: jeder zu schwärzende Eintrag ein Leck
  an seiner Stelle), Orakel (perfekte Schwärzung, auch mit Platzhaltertext wie das Programm: Recall 100 %,
  Über-Schwärzung 0) und Teilreste (Orakel + ein zurückgeschriebenes XMP-/Info-/Anhang-Exemplar: Leck im Kanal);
  Pixelvergleich, Grundzahl der Dokumentkanäle, Über-Schwärzung und Fehlalarme an kleinen Beispielen.

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
# Gemessen am 2026-11-09 auf 4408edc + Paket restrisiko-messung (Linux, PyMuPDF 2.1, de_core_news_md 3.8.0, ohne
# Tesseract-Kommandozeile; Pixelvergleich ohne Platzhaltertinte und auf der eigenen Zeile, Über-Schwärzung nach
# Lage/eigenständigen Vorkommen): recall_kern 0,9973 (371/372), Über-Schwärzung 0,0 (0/216). Die beiden Grenzen
# stammen noch vom Stand 4e4a769 (0,7231 bzw. 0,0417) und lassen weiten Spielraum für Plattform-Abweichungen
# (Windows: Schriften, OCR-Build) – nachziehen, sobald die Windows-Werte zum neuen Stand vorliegen.
MIN_RECALL_KERN = 0.70
MAX_UEBERSCHWAERZUNG = 0.065
# Restrisiko-Prüfung (Vertrag Abschnitt 7), gemessen am 2026-11-09 auf demselben Stand (Linux): 0 Dokumente mit
# stillem Leck; 1 Kern-Leck (kein reiner Pixelrest), abgedeckt vom Verdacht im Unterschriftsblock ("V. De Luca" in
# 007_kuendigung_DeLuca, vom Unterschriftszug durchkreuzt); 0,429 Fehlverdacht je Seite (6 von 12 Verdachtsstellen,
# darunter eine echte Unterschrift ohne gedruckten Namen); 6 von 12 Ausgaben _PRUEFEN (5 ohne Kern-Leck).
# Vorher (4408edc, alte Bewertung): 2 Kern-Lecks, keines abgedeckt – ">= 0,90" war eine Quote über 2 Einträge.
# Nach den Review-Korrekturen (2026-11-10: Lesegeometrie, Schräglage, Rollenzeilen, Fach-/Firmenzeilen, gerade
# Linienreste, Seitenmaske; Grundzahl der Dokumentkanäle) alle Werte unverändert.
MAX_DOKUMENTE_STILLES_LECK = 1
MIN_VERDACHTSABDECKUNG = 0.90
MIN_LECKS_FUER_QUOTE = 10      # darunter ist eine Quote bedeutungslos: JEDES Leck braucht einen Verdacht
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
    # Verdachtsabdeckung über die Kern-Lecks, die nicht nur Pixelreste sind (nur_pixelrest: kein Wort mehr als zur
    # Hälfte lesbar). Bei wenigen solchen Lecks wäre eine Quote bedeutungslos (2 Einträge: 50 % oder 100 %) – dann
    # muss JEDES von einem Verdacht abgedeckt sein; ab MIN_LECKS_FUER_QUOTE gilt die Quote.
    n = rr["kern_lecks_ohne_pixelrest"]
    ohne_verdacht = [(x["dokument"], x["text"]) for x in rr["nicht_abgedeckt"] if not x.get("nur_pixelrest")]
    if n < MIN_LECKS_FUER_QUOTE:
        assert rr["kern_lecks_ohne_pixelrest_abgedeckt"] == n, (
            f"{n - rr['kern_lecks_ohne_pixelrest_abgedeckt']} von {n} Kern-Lecks ohne Verdacht: {ohne_verdacht}")
    else:
        assert rr["verdachtsabdeckung_ohne_pixelrest"] >= MIN_VERDACHTSABDECKUNG, (
            f"Verdachtsabdeckung ohne Pixelreste {rr['verdachtsabdeckung_ohne_pixelrest']}: {ohne_verdacht}")
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


# ----------------------------------------------------------------------
# Pixelvergleich: Platzhaltertinte, eigene Zeile
# ----------------------------------------------------------------------
def _scan_mit_zwei_zeilen(pfad):
    """Scan-Seite (Bild): oben "Umzugs zum 31.12.", darunter "54290 Trier"; Wortrechteck von "Trier" wie bei
    Schräglage bis in die Zeile darüber vergrößert. Liefert (pdf, Wortrechteck, Rechteck der Glyphen)."""
    import pymupdf as fitz
    vorlage = fitz.open()
    s = vorlage.new_page(width=300, height=200)
    s.insert_text((40, 80), "Umzugs zum 31.12. gilt", fontsize=12, fontname="helv")
    s.insert_text((40, 94), "54290 Trier", fontsize=12, fontname="helv")
    glyphen = next(fitz.Rect(w[:4]) for w in s.get_text("words") if w[4] == "Trier")
    pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=300, height=200)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    doc.save(pfad)
    doc.close()
    vorlage.close()
    return pfad, [glyphen.x0, glyphen.y0 - 7, glyphen.x1, glyphen.y1, "Trier"], glyphen


def test_pixelvergleich_ohne_platzhaltertinte_und_auf_der_eigenen_zeile(tmp_path):
    """Die Schwärzung legt ein graues Rechteck über "Trier" und schreibt den Platzhalter "[PLZ ORT]" hinein: dessen
    Tinte ist kein Original, und die Tinte der Zeile darüber gehört nicht zum Wort – der Wert gilt als entfernt.
    Streng bleibt der Vergleich: unverändert (Ausgabe = Original) ist das Wort voll sichtbar; ein Klammertext, der
    schon im Original steht, wird nicht entfernt."""
    import pymupdf as fitz
    original, wort, glyphen = _scan_mit_zwei_zeilen(tmp_path / "o.pdf")
    with fitz.open(original) as d:
        s = d[0]
        s.draw_rect(glyphen + (-1, -1, 1, 1), color=None, fill=(0.92, 0.92, 0.92))
        s.insert_text((glyphen.x0, glyphen.y1 - 3), "[PLZ ORT]", fontsize=9, fontname="helv")
        d.save(tmp_path / "a.pdf")
    eng = [glyphen.x0, glyphen.y0, glyphen.x1, glyphen.y1, "Trier"]
    with fitz.open(original) as do, fitz.open(tmp_path / "a.pdf") as da:
        go, ga = bewertung._graubild(do[0]), bewertung._graubild(da[0])
        ohne, entfernt = bewertung.graubild_ohne_platzhalter(tmp_path / "a.pdf", 0, do[0])
        assert entfernt == 1
        # früher (Bild mit Platzhalter, ganzes Rechteck): mindestens ein Teil-Leck
        assert bewertung.wort_sichtbarkeit(go, ga, wort, zuschnitt=False) >= bewertung.TEILWEISE_SCHWELLE
        # jeder Fehler für sich: Platzhaltertinte (enges Rechteck) und Tinte der Zeile darüber (weites Rechteck)
        assert bewertung.wort_sichtbarkeit(go, ga, eng, zuschnitt=False) > 0.1
        assert bewertung.wort_sichtbarkeit(go, ohne, eng, zuschnitt=False) < 0.02
        assert bewertung.wort_sichtbarkeit(go, ohne, wort, zuschnitt=False) >= bewertung.TEILWEISE_SCHWELLE
        # beides behoben: entfernt
        assert bewertung.wort_sichtbarkeit(go, ohne, wort) < 0.05
        # Null-Anonymisierer: Ausgabe = Original -> voll sichtbar, nichts entfernt
        gleich, n = bewertung.graubild_ohne_platzhalter(original, 0, do[0])
        assert n == 0 and bewertung.wort_sichtbarkeit(go, gleich, wort) == 1.0
    # Klammertext im Original bleibt im Vergleichsbild
    doc = fitz.open()
    seite = doc.new_page(width=200, height=100)
    seite.insert_text((20, 50), "Anlage [1] beachten", fontsize=11)
    doc.save(tmp_path / "k.pdf")
    with fitz.open(tmp_path / "k.pdf") as d:
        assert bewertung.platzhalter_rechtecke(d[0], d[0]) == []
        assert len(bewertung.platzhalter_rechtecke(d[0])) == 1
    doc.close()


def test_eigene_zeile_schneidet_nachbarzeilen_ab():
    import numpy as np
    tinte = np.zeros((20, 30), dtype=bool)
    tinte[1:4, 2:20] = True            # Unterlängen der Zeile darüber
    tinte[7:14, 0:30] = True           # eigene Zeile (durch die Mitte)
    tinte[17:19, 5:9] = True           # Oberlänge der Zeile darunter
    eigen = bewertung.eigene_zeile(tinte)
    assert eigen[7:14].all() and not eigen[:5].any() and not eigen[15:].any()
    schraeg = np.zeros((20, 32), dtype=bool)
    for x in range(32):                # schräge eigene Zeile: wandert über die Breite um 6 Pixel
        schraeg[5 + x // 6:11 + x // 6, x] = True
    assert bewertung.eigene_zeile(schraeg).sum() == schraeg.sum()


# ----------------------------------------------------------------------
# Über-Schwärzung: eigenständig und an der Stelle; Fehlalarme nur angehakter Funde
# ----------------------------------------------------------------------
def test_eigenstaendige_vorkommen():
    z = bewertung.eigenstaendig_zaehlen
    assert z("BU BU-2018-848343 BU/96/8657146 (BU), BU.", "BU") == 3
    assert z("Wohn-\ngebäude und Wohngebäude", "Wohngebäude") == 2
    assert z("Herr Müller-Lüdenscheidt", "Müller") == 0
    assert z("Vertrag 47.897.336.2", "897") == 0
    assert z("ŞAHIN und Sahin", "Şahin") == 2


def test_behaltenes_wort_in_geschwaerzter_kennung_ist_keine_ueberschwaerzung(tmp_path):
    """"BU" (Sparte, zu behalten) steckt auch in der geschwärzten Kennung "BU-2018-848343": deren Schwärzung senkt
    die Rohzahl, ist aber keine Über-Schwärzung. Wird das eigenständige "BU" geschwärzt, fehlt es."""
    import pymupdf as fitz

    def seite(pfad, zeile):
        doc = fitz.open()
        s = doc.new_page(width=300, height=100)
        s.insert_text((20, 50), zeile, fontsize=11, fontname="helv")
        woerter = s.get_text("words")
        doc.save(pfad)
        doc.close()
        return woerter

    woerter = seite(tmp_path / "o.pdf", "Sparte BU   Vertrag BU-2018-848343")
    seite(tmp_path / "a.pdf", "Sparte BU   Vertrag [VERTRAGS-NR]")
    seite(tmp_path / "b.pdf", "Sparte [ ]   Vertrag [VERTRAGS-NR]")
    bu = next(w for w in woerter if w[4] == "BU")
    e = {"text": "BU", "seite": 1, "kanal": "text", "woerter": [list(bu[:5])]}
    original = bewertung.Kanaele(tmp_path / "o.pdf")
    aus = bewertung.Kanaele(tmp_path / "a.pdf")
    nadel = bewertung.Gefaltet("BU")
    assert original.gefaltet("text", 1).zaehle(nadel) == 2 and aus.gefaltet("text", 1).zaehle(nadel) == 1
    assert bewertung._behalten_pruefen(e, nadel, original, aus, [])["status"] == "erhalten"
    weg = bewertung.Kanaele(tmp_path / "b.pdf")
    assert bewertung._behalten_pruefen(e, nadel, original, weg, [])["status"] == "fehlt"


class _FesteAusgabe(bewertung._Pruefling):
    """Prüfling, dessen „Ausgabe" eine vorbereitete Datei ist (Teilfehler gezielt nachstellen)."""

    def __init__(self, datei):
        super().__init__("feste-ausgabe")
        self.datei = Path(datei)

    def schwaerze_pdf(self, pdf, funde=None, ziel_ordner=None, **kwargs):
        import shutil
        ziel = Path(ziel_ordner) / "ausgabe_01.pdf"
        shutil.copyfile(self.datei, ziel)
        return {"ausgabe": ziel, "treffer": 0, "status": "fertig", "verdacht": [], "reste": [], "warnungen": []}


def test_grundzahl_dokumentkanal_ein_eintrag_steht_fuer_alle_exemplare(tmp_path):
    """Metadaten: EIN Eintrag der Wahrheit steht für Info-Dict-Titel UND XMP dc:title (Generator: "Info-Dict Titel und
    XMP dc:title"). Bleibt ein Exemplar stehen (Info bereinigt, XMP vergessen – oder umgekehrt), ist das ein Leck im
    Kanal metadaten. Früher zog die Grundzahl je Eintrag nur EIN Vorkommen ab: 2 Exemplare - 1 Eintrag = 1, und der
    Rest lag nicht darüber; der Name stand zudem zweimal in der Textebene (Felder Vorname/Nachname untereinander und
    Kontoinhaber), sodass auch die Rohdaten ihn nicht sahen – ein vollständig unsichtbares Leck (Seed 1, 037-029)."""
    import pymupdf as fitz
    titel = "Antrag auf Riester-Rente Omar El-Masri"
    xmp = ('<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
           'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
           'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title><rdf:Alt><rdf:li xml:lang="x-default">' + titel
           + '</rdf:li></rdf:Alt></dc:title></rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')

    def pdf(pfad, zeilen, info, mit_xmp):
        doc = fitz.open()
        s = doc.new_page()
        for i, z in enumerate(zeilen):
            s.insert_text((50, 80 + 16 * i), z, fontsize=11, fontname="helv")
        doc.set_metadata({"title": titel} if info else {})
        if mit_xmp:
            doc.set_xml_metadata(xmp)
        doc.save(pfad)
        doc.close()
        return pfad

    original = pdf(tmp_path / "o.pdf", ["Omar", "El-Masri", "Kontoinhaber: Omar El-Masri"], True, True)
    eintraege = [{"id": f"e{i}", "text": t, "kategorie": "namen", "seite": 1, "erwartung": "schwaerzen",
                  "umfang": "kern", "kanal": k}
                 for i, (t, k) in enumerate([("Omar", "text"), ("El-Masri", "text"), ("Omar El-Masri", "text"),
                                             ("Omar El-Masri", "metadaten")])]
    kanaele = bewertung.Kanaele(original)
    nadel = Gefaltet("Omar El-Masri")
    assert kanaele.gefaltet("metadaten").zaehle(nadel) == 2
    assert bewertung._grund_kanal(kanaele, "metadaten", None, nadel, eintraege) == 0
    wahrheit = {"dokument": "o.pdf", "typ": "test", "merkmale": [], "seiten": 1, "eintraege": eintraege}
    schwarz = ["[PERSON A]", "[PERSON A]", "Kontoinhaber: [PERSON A]"]
    for art, info, mit_xmp in (("nur_xmp", False, True), ("nur_info", True, False), ("keins", False, False)):
        aus = pdf(tmp_path / f"{art}.pdf", schwarz, info, mit_xmp)
        (tmp_path / art).mkdir()
        d = bewertung.bewerte_dokument(original, wahrheit, _FesteAusgabe(aus), None, tmp_path / art, tmp_path,
                                       cli_ocr=False, pixel=False)
        meta = next(e for e in d["eintraege"] if e["id"] == "e3")
        if art == "keins":
            assert meta["status"] == "entfernt", meta
        else:
            assert meta["status"] == "leck" and "metadaten" in meta["kanaele"], (art, meta)


def test_fund_aktiv():
    assert bewertung.fund_aktiv({"text": "x"})                                    # ältere Funde ohne Stellen
    assert bewertung.fund_aktiv({"stellen": [{"an": False}, {"an": True}]})
    assert not bewertung.fund_aktiv({"stellen": [{"an": False}, {"an": False}]})   # nur angeboten


class _AngebotPruefling(bewertung.NullAnonymisierer):
    """Null-Anonymisierer mit zwei Funden ohne PII-Bezug: einer angehakt, einer nur angeboten (Stelle abgewählt)."""

    def analysiere_pdf(self, pdf, *args, **kwargs):
        return {"funde": [{"kategorie": "sonstiges", "text": "Zzyzx-Angehakt", "stellen": [{"an": True}]},
                          {"kategorie": "gesundheit", "text": "Zzyzx-Angeboten", "stellen": [{"an": False}]}],
                "warnungen": [], "fehler": None, "ocr_cache": {}}


def test_fehlalarme_nur_angehakte_funde(ci_korpus, tmp_path):
    ordner, wahrheiten = ci_korpus
    text_dok = next(w["dokument"] for w in wahrheiten if "scan" not in w["merkmale"])
    e = bewertung.bewerte_korpus(ordner, tmp_path / "e", cli_ocr=False, melde=None, nur=[text_dok],
                                 pipeline=_AngebotPruefling())
    g = e["gesamt"]
    assert g["funde"] == 2 and g["funde_aktiv"] == 1 and g["fehlalarme"] == 1 and g["fehlalarm_quote"] == 1.0
    assert [f["text"] for f in e["dokumente"][0]["fehlalarme"]] == ["Zzyzx-Angehakt"]


# ----------------------------------------------------------------------
# Selbstprüfung der Bewertung (Null-Anonymisierer, Orakel)
# ----------------------------------------------------------------------
@braucht_ocr
def test_selbstpruefung_der_bewertung(ci_korpus, tmp_path):
    """Die Bewertung selbst: Ausgabe = Original muss JEDEN zu schwärzenden Eintrag als Leck an seiner Stelle zeigen
    und alles zu Behaltende als erhalten; das Orakel (perfekte Schwärzung aus der Wahrheit, auch mit Platzhaltertext
    im grauen Rechteck wie das Programm) muss Recall 100 % und Über-Schwärzung 0 ergeben. Auf den Scans (Pixel,
    Platzhaltertinte), dem Formular (Feldwerte) und einem Brief mit Nebenkanälen."""
    ordner, wahrheiten = ci_korpus
    nur = [w["dokument"] for w in wahrheiten if "scan" in w["merkmale"] or "formular" in w["merkmale"]]
    nur += [w["dokument"] for w in wahrheiten if "metadaten" in w["merkmale"]][:1]
    e = bewertung.selbstpruefung(ordner, tmp_path / "selbst", melde=None, nur=nur)
    null = e["null_anonymisierer"]
    assert null["schwaerzen"] > 50 and null["leck"] == null["schwaerzen"], null["nicht_leck"][:10]
    assert null["nicht_am_ort"] == [] and null["behalten_erhalten"] == null["behalten"], null
    for name in ("orakel", "orakel_platzhalter"):
        assert e[name]["recall_kern"] == 1.0 and e[name]["recall_erweitert"] == 1.0, e[name]["nicht_entfernt"][:10]
        assert e[name]["ueberschwaerzung"] == 0.0, e[name]["ueberschwaerzt"]
    # Teilreste: Orakel, dann EIN Exemplar eines Nebenkanals aus dem Original zurück (XMP oder Info-Dict; Anhangname
    # oder -inhalt) – jeder Eintrag, dessen Wert darin steht, ist ein Leck in seinem Kanal, sonst bleibt alles entfernt
    for name in ("teilrest_xmp", "teilrest_info"):
        assert e[name]["erwartet"] > 0 and e[name]["ok"], e[name]
    for name in ("teilrest_anhang_name", "teilrest_anhang_inhalt"):
        assert name not in e or e[name]["ok"], e[name]
    assert (tmp_path / "selbst" / "selbstpruefung.json").exists()


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
