"""Domänen-Probe (werkzeuge/domaenenprobe): Die Falldateien laden, haben die Pflichtfelder und passen zur Referenz;
ein kleiner Text-Fall läuft Ende-zu-Ende über das Werkzeug (messen.py -> e2e.py -> ergebnis.json/bericht.md); ohne
lesbare OCR-Prüfung bricht das Werkzeug ab, statt Werte still als „weg“ zu zählen. Die volle Probe läuft nicht hier
(Laufzeit, Tesseract-Kommandozeile) – siehe werkzeuge/domaenenprobe/README.md."""

import importlib.util
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
PROBE = WURZEL / "werkzeuge" / "domaenenprobe"
SPARTEN = {"lauf1", "kfz", "person", "sach", "digital", "kritik"}


def _modul(datei: str):
    spec = importlib.util.spec_from_file_location(f"domaenenprobe_{Path(datei).stem}", PROBE / datei)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def faelle_je_datei():
    """{Falldatei: (Sparte, FAELLE)}. Die Kritik-Fälle legen ihren Ordner in sys.path und importieren bau.py und
    Nachbardateien – sys.path und sys.modules werden danach wiederhergestellt."""
    messen = _modul("messen.py")
    pfad, module = list(sys.path), set(sys.modules)
    try:
        geladen = {datei: (bereich, runpy.run_path(str(datei))["FAELLE"]) for bereich, datei in messen.falldateien()}
    finally:
        sys.path[:] = pfad
        for name in set(sys.modules) - module:
            del sys.modules[name]
    return messen, geladen


def test_falldateien_laden_und_haben_die_pflichtfelder(faelle_je_datei):
    messen, geladen = faelle_je_datei
    assert len(geladen) == 41
    assert {bereich for bereich, _ in geladen.values()} == SPARTEN
    for datei, (_, faelle) in geladen.items():
        assert isinstance(faelle, list) and faelle, datei
        namen = [fall["name"] for fall in faelle]
        assert len(namen) == len(set(namen)), f"{datei}: doppelte Fallnamen überschreiben sich in ergebnis.json"
        for fall in faelle:
            ort = f"{datei.name}: {fall.get('name')}"
            assert isinstance(fall["name"], str) and fall["name"], ort
            assert isinstance(fall["geheim"], list) and all(isinstance(g, str) and g for g in fall["geheim"]), ort
            if fall.get("bauer"):
                assert callable(fall["bauer"]), ort
            else:
                assert fall["zeilen"] and all(isinstance(z, str) for z in fall["zeilen"]), ort
            scans = fall.get("scans", ())
            assert all(len(s) == 3 and s[0] > 0 for s in scans), ort          # (dpi, winkel, jpeg)
            assert fall.get("text", True) or scans, f"{ort}: weder Textebene noch Scan"


def test_referenz_passt_zu_den_falldateien(faelle_je_datei):
    """referenz.json hat genau die Einträge, die die Falldateien ergeben (Datei|Fall|Art|Wert, Art wie in e2e.py) –
    wer Fälle ändert, erneuert die Referenz (README der Probe)."""
    messen, geladen = faelle_je_datei
    erwartet = {}
    for datei, (bereich, faelle) in geladen.items():
        for fall in faelle:
            arten = (["text"] if fall.get("text", True) else []) + [f"scan{d}/{w}/{j}" for d, w, j in
                                                                    fall.get("scans", ())]
            for art in arten:
                for g in fall["geheim"]:
                    erwartet[f"{messen.schluessel_datei(datei)}|{fall['name']}|{art}|{g}"] = bereich
    referenz = json.loads((PROBE / "referenz.json").read_text(encoding="utf-8"))
    fehlen, zuviel = sorted(set(erwartet) - set(referenz)), sorted(set(referenz) - set(erwartet))
    assert not fehlen and not zuviel, f"fehlen in referenz.json: {fehlen[:5]}, nur in referenz.json: {zuviel[:5]}"
    for schluessel, eintrag in referenz.items():
        assert eintrag["bereich"] == erwartet[schluessel], schluessel
        assert eintrag["zustand"] in ("weg", "sichtbar", "still"), schluessel
    assert "Referenz der Domänen-Probe" in (PROBE / "referenz.md").read_text(encoding="utf-8")


FALL = '''FAELLE = [dict(name="probe_brief",
                zeilen=["Schadenmeldung Hausratversicherung", "Versicherungsnehmer: Quirin Zwackelhuber",
                        "IBAN: DE29 7205 0000 0240 1234 56"],
                geheim=["Zwackelhuber", "DE29720500000240123456", "Hausratversicherung"])]
'''


def test_text_fall_laeuft_ende_zu_ende_ueber_das_werkzeug(tmp_path):
    """Name und IBAN sind nach dem Schwärzen weder in der Textebene noch per OCR lesbar („weg“); das Kontrollwort
    „Hausratversicherung“ bleibt stehen und muss in beiden Kanälen als lesbar erkannt werden – sonst wäre die
    Prüfung blind und zählte Lecks als „weg“. OCR hier mit PyMuPDF (die CI hat keine Tesseract-Kommandozeile)."""
    falldatei = tmp_path / "faelle_probe.py"
    falldatei.write_text(FALL, encoding="utf-8")
    aus = tmp_path / "aus"
    lauf = subprocess.run([sys.executable, "-W", "ignore", str(PROBE / "messen.py"), str(aus), "--faelle",
                           str(falldatei), "--ohne-vergleich", "--ocr", "pymupdf", "--jobs", "1"],
                          capture_output=True, encoding="utf-8", errors="replace", timeout=280)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr + "\n".join(
        p.read_text(encoding="utf-8") for p in aus.rglob("lauf.txt"))
    ergebnis = json.loads((aus / "ergebnis.json").read_text(encoding="utf-8"))
    zustaende = {k.split("|")[-1]: v["zustand"] for k, v in ergebnis.items()}
    assert set(ergebnis) == {f"faelle_probe.py|probe_brief|text|{g}"
                             for g in ("Zwackelhuber", "DE29720500000240123456", "Hausratversicherung")}
    assert {v["bereich"] for v in ergebnis.values()} == {"extern"}
    assert zustaende["Zwackelhuber"] == "weg" and zustaende["DE29720500000240123456"] == "weg", zustaende
    assert zustaende["Hausratversicherung"] in ("sichtbar", "still"), zustaende
    roh = {e["geheim"]: e for p in aus.rglob("ergebnis_oberflaeche.json")
           for e in json.loads(p.read_text(encoding="utf-8"))}
    assert roh["Hausratversicherung"]["textebene"] and roh["Hausratversicherung"]["ocr"], roh["Hausratversicherung"]
    assert not roh["Zwackelhuber"]["ocr"] and not roh["Zwackelhuber"]["textebene"]
    bericht = (aus / "bericht.md").read_text(encoding="utf-8")
    assert "| extern | 3 | 2 (66.7 %) |" in bericht and "| GESAMT | 3 | 2 (66.7 %) |" in bericht, bericht
    assert "in PyMuPDF eingebautes Tesseract" in bericht
    assert not list(aus.rglob("*.pdf")), "ohne --pdfs-behalten löscht das Werkzeug die PDFs"


@pytest.mark.parametrize("zusatz, meldung, code", [
    (["--tesseract", "{tmp}/gibt_es_nicht"], "Tesseract-Kommandozeile nicht gefunden", 2),
    (["--als-referenz", "--faelle", "faelle_domaene.py"], "--als-referenz nur für einen vollen Lauf", 2),
])
def test_werkzeug_bricht_ab_statt_still_zu_zaehlen(tmp_path, zusatz, meldung, code):
    aus = tmp_path / "aus"
    lauf = subprocess.run([sys.executable, "-W", "ignore", str(PROBE / "messen.py"), str(aus)]
                          + [z.replace("{tmp}", str(tmp_path)) for z in zusatz],
                          capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    assert lauf.returncode == code and meldung in lauf.stderr, lauf.stdout + lauf.stderr
    assert not (aus / "ergebnis.json").exists()


def test_ocr_pruefung_meldet_fehler_der_kommandozeile(tmp_path):
    """Endet die Tesseract-Kommandozeile mit einem Fehler, bricht die Prüfung ab – sie liefert keinen leeren
    OCR-Text, mit dem jeder Wert als „weg“ zählte. Als fehlschlagendes Programm dient Python selbst (es versucht,
    die PNG-Datei als Skript auszuführen)."""
    import pymupdf as fitz
    e2e = _modul("e2e.py")
    pdf = tmp_path / "seite.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 72), "Hausratversicherung", fontsize=12)
        doc.save(pdf)
    e2e.OCR_ART, e2e.TESSERACT, e2e.ARBEIT = "tesseract", sys.executable, tmp_path
    with pytest.raises(RuntimeError, match="Tesseract-Kommandozeile mit Exit-Code"):
        e2e.ocr_text(pdf)
    assert not list(tmp_path.glob("_ocr_*.png"))
