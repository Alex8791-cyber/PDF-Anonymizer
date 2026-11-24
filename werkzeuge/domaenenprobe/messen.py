"""Domänen-Messung: alle Falldateien der Domänen-Probe über den Oberflächen-Weg laufen lassen und zählen.

Aufruf (aus der Projektwurzel; Python = das aufrufende, Programmcode = dieses Checkout):
    python werkzeuge/domaenenprobe/messen.py <ausgabeordner> [--jobs 2] [--repo <checkout>]
        [--vergleich <alte ergebnis.json> | --ohne-vergleich] [--als-referenz]
        [--faelle <falldatei> ...] [--nur <fall,...>] [--ocr tesseract|pymupdf] [--tesseract <programm>]
        [--pdfs-behalten]

Zählt je Sparte und gesamt die geheimen Werte: weg (weder Textebene noch OCR lesbar), sichtbar (lesbar, Ausgabe zur
Prüfung markiert) und STILL (lesbar ohne Verdacht und ohne _PRUEFEN außer der bloßen Freigabe). Schreibt
ergebnis.json (je Eintrag Datei|Fall|Art|Wert -> Zustand) und bericht.md; verglichen wird mit referenz.json neben
diesem Skript (oder mit --vergleich) – der Bericht listet die Einträge, die sich verbessert oder verschlechtert
haben. --als-referenz ersetzt danach referenz.json und referenz.md durch diese Messung (nur voller Lauf mit der
Tesseract-Kommandozeile, ohne Fehler). Exit-Code 1, wenn eine Falldatei nicht durchlief; 2 bei falschem Aufruf.
"""
import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parents[1]                 # Vorgabe für --repo: das Checkout, in dem dieses Werkzeug liegt
PY = sys.executable
HARNESS = HIER / "e2e.py"
REFERENZ = HIER / "referenz.json"
REFERENZ_MD = HIER / "referenz.md"
BEREICHE = ["", "kfz", "kfz_gegen", "person", "person_gegen", "sach", "sach_gegen", "digital", "digital/runden",
            "digital_gegen", "kritik"]


def falldateien():
    aus = []
    for b in BEREICHE:
        ordner = HIER / b if b else HIER
        for f in sorted(ordner.glob("*.py")):
            name = f.name
            if not (name.startswith("faelle") or name.startswith("gegen")):
                continue
            if "FAELLE" not in f.read_text(encoding="utf-8", errors="replace"):
                continue
            bereich = (b or "lauf1").split("/")[0].replace("_gegen", "")
            aus.append((bereich, f))
    return aus


def _bereich(datei: Path) -> str:
    """Sparte einer Datei wie in falldateien(); Dateien außerhalb der Probe zählen als „extern“."""
    try:
        teile = datei.relative_to(HIER).parts
    except ValueError:
        return "extern"
    return "lauf1" if len(teile) == 1 else teile[0].replace("_gegen", "")


def ausgewaehlte_falldateien(angaben):
    """--faelle: Pfade relativ zum aktuellen Ordner oder zu diesem Werkzeugordner."""
    aus = []
    for angabe in angaben:
        kandidaten = [Path(angabe), HIER / angabe]
        datei = next((k.resolve() for k in kandidaten if k.is_file()), None)
        if datei is None:
            raise SystemExit(f"Falldatei nicht gefunden: {angabe}")
        if "FAELLE" not in datei.read_text(encoding="utf-8", errors="replace"):
            raise SystemExit(f"Keine Falldatei (FAELLE fehlt): {datei}")
        aus.append((_bereich(datei), datei))
    return aus


def schluessel_datei(datei: Path) -> str:
    """Datei-Teil des Schlüssels: Pfad relativ zum Werkzeugordner mit „/“ (wie unter Linux gemessen)."""
    try:
        return datei.relative_to(HIER).as_posix()
    except ValueError:
        return datei.name


def lauf(repo: Path, ziel: Path, bereich: str, datei: Path, optionen):
    arbeit = ziel / "arbeit" / f"{bereich}_{datei.parent.name}_{datei.stem}"
    arbeit.mkdir(parents=True, exist_ok=True)
    log = arbeit / "lauf.txt"
    erg = arbeit / "ergebnis_oberflaeche.json"
    if erg.exists():
        erg.unlink()                     # kein Ergebnis eines früheren Laufs als dieses zählen
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    befehl = [PY, "-W", "ignore", str(HARNESS), str(datei), str(arbeit), "--repo", str(repo), "--weg", "oberflaeche",
              "--ocr", optionen.ocr]
    if optionen.tesseract:
        befehl += ["--tesseract", optionen.tesseract]
    if optionen.nur:
        befehl += ["--nur", optionen.nur]
    zusatz = {}
    if os.name == "nt":
        zusatz["creationflags"] = subprocess.BELOW_NORMAL_PRIORITY_CLASS
    elif shutil.which("nice"):
        befehl = ["nice", "-n", "15"] + befehl
    with open(log, "w", encoding="utf-8") as aus:
        r = subprocess.run(befehl, stdout=aus, stderr=subprocess.STDOUT, env=env, timeout=3600, **zusatz)
    eintraege = json.loads(erg.read_text(encoding="utf-8")) if erg.exists() else []
    if not optionen.pdfs_behalten:
        for pdf in arbeit.rglob("*.pdf"):
            pdf.unlink()
    return bereich, datei, r.returncode, eintraege


def zustand(e):
    if not (e["textebene"] or e["ocr"]):
        return "weg"
    return "still" if e["still"] else "sichtbar"


def _harness():
    spec = importlib.util.spec_from_file_location("domaenenprobe_e2e", HARNESS)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _version(paket):
    try:
        return importlib.metadata.version(paket)
    except importlib.metadata.PackageNotFoundError:
        return "fehlt"


def _stand(repo: Path) -> str:
    """Commit des gemessenen Checkouts und ob der Programmcode (anonymisierer/) davon abweicht."""
    try:
        wurzel = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"], capture_output=True,
                                encoding="utf-8", errors="replace", timeout=60)
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, encoding="utf-8",
                           errors="replace", timeout=60)
        if r.returncode != 0 or wurzel.returncode != 0 or Path(wurzel.stdout.strip()).resolve() != repo.resolve():
            return "unbekannt (kein Git-Checkout)"
        s = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "anonymisierer"],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return "unbekannt (git nicht verfügbar)"
    return r.stdout.strip() + (" mit lokalen Änderungen in anonymisierer/" if s.stdout.strip() else "")


def _umgebung(repo: Path, optionen, e2e, anzahl: int) -> list:
    if optionen.ocr == "tesseract":
        ocr = f"Tesseract-Kommandozeile ({e2e.tesseract_version(optionen.tesseract)}, PSM 3)"
    else:
        ocr = "in PyMuPDF eingebautes Tesseract (nicht mit der Referenz vergleichbar)"
    schriften = ", ".join(f"{Path(p).name if p else 'fehlt'}{' (Ersatz für ' + n + ')' if ersatz else ''}"
                          for n, (p, ersatz) in e2e.schriften().items())
    return [f"- Stand: {_stand(repo)}",
            f"- Umgebung: {platform.system()} {platform.release()}, Python {platform.python_version()}, "
            f"PyMuPDF {_version('pymupdf')}, spaCy {_version('spacy')}, de_core_news_md {_version('de_core_news_md')}",
            f"- OCR-Prüfung der Ausgabe: {ocr}",
            f"- Schriften der Fälle: {schriften}",
            f"- Falldateien: {anzahl}" + (f", nur Fälle {optionen.nur}" if optionen.nur else "")]


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Domänen-Probe: Falldateien messen und mit der Referenz vergleichen")
    ap.add_argument("ziel", help="Ausgabeordner (ergebnis.json, bericht.md, arbeit/)")
    ap.add_argument("--repo", default=str(WURZEL), help="Checkout, dessen Programmcode gemessen wird")
    ap.add_argument("--jobs", type=int, default=2, help="Falldateien gleichzeitig (je ein Prozess)")
    vergleich = ap.add_mutually_exclusive_group()
    vergleich.add_argument("--vergleich", help="frühere ergebnis.json (Vorgabe: referenz.json)")
    vergleich.add_argument("--ohne-vergleich", action="store_true", help="nicht vergleichen")
    ap.add_argument("--als-referenz", action="store_true",
                    help="referenz.json/referenz.md durch diese Messung ersetzen")
    ap.add_argument("--faelle", nargs="+", help="nur diese Falldateien")
    ap.add_argument("--nur", default="", help="nur diese Fälle (Namen, durch Komma getrennt)")
    ap.add_argument("--ocr", choices=("tesseract", "pymupdf"), default="tesseract",
                    help="OCR-Prüfung der Ausgabe (Vorgabe: Tesseract-Kommandozeile wie bei der Referenz)")
    ap.add_argument("--tesseract", help="Tesseract-Programm (sonst DOMAENENPROBE_TESSERACT, PATH)")
    ap.add_argument("--pdfs-behalten", action="store_true", help="gebaute PDFs und Ausgaben nicht löschen")
    a = ap.parse_args(argv)
    repo, ziel = Path(a.repo).resolve(), Path(a.ziel).resolve()
    if not (repo / "anonymisierer" / "__init__.py").is_file():
        ap.error(f"--repo {repo}: kein Programmcode (anonymisierer/) gefunden")
    if a.als_referenz and (a.faelle or a.nur or a.ocr != "tesseract"):
        ap.error("--als-referenz nur für einen vollen Lauf mit der Tesseract-Kommandozeile")
    e2e = _harness()
    if a.ocr == "tesseract":
        a.tesseract = e2e.tesseract_programm(a.tesseract)
        if not a.tesseract:
            print("Tesseract-Kommandozeile nicht gefunden (--tesseract, DOMAENENPROBE_TESSERACT oder PATH). Ohne sie "
                  "misst --ocr pymupdf – mit der Referenz nicht vergleichbar.", file=sys.stderr)
            return 2
    ziel.mkdir(parents=True, exist_ok=True)
    dateien = ausgewaehlte_falldateien(a.faelle) if a.faelle else falldateien()
    beginn = time.time()
    ergebnisse = {}
    fehler = []
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        for bereich, datei, rc, eintraege in pool.map(lambda x: lauf(repo, ziel, *x, a), dateien):
            if rc != 0 or not eintraege:
                fehler.append(f"{datei} rc={rc} eintraege={len(eintraege)}")
            for e in eintraege:
                schluessel = f"{schluessel_datei(datei)}|{e['fall']}|{e['art']}|{e['geheim']}"
                ergebnisse[schluessel] = dict(bereich=bereich, zustand=zustand(e), status=e.get("status"))
    dauer = time.time() - beginn
    (ziel / "ergebnis.json").write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=1), encoding="utf-8")
    je = defaultdict(Counter)
    for v in ergebnisse.values():
        je[v["bereich"]][v["zustand"]] += 1
        je["GESAMT"][v["zustand"]] += 1
    tabelle = ["| Sparte | Werte | weg | sichtbar (_PRUEFEN) | STILL |", "|---|---:|---:|---:|---:|"]
    for b in sorted(je, key=lambda x: (x == "GESAMT", x)):
        c = je[b]
        n = sum(c.values())
        tabelle.append(f"| {b} | {n} | {c['weg']} ({100 * c['weg'] / n:.1f} %) | {c['sichtbar']} | {c['still']} |")
    umgebung = _umgebung(repo, a, e2e, len(dateien)) + [f"- Dauer: {dauer / 60:.1f} min mit --jobs {a.jobs}"]
    zeilen = [f"# Domänen-Messung {repo}", ""] + umgebung + [""] + tabelle
    if fehler:
        zeilen += ["", "Fehler:"] + [f"- {x}" for x in fehler]
    vergleich_mit = None if a.ohne_vergleich else (Path(a.vergleich) if a.vergleich else
                                                   (REFERENZ if REFERENZ.exists() else None))
    if vergleich_mit:
        alt = json.loads(vergleich_mit.read_text(encoding="utf-8"))
        besser, schlechter = [], []
        rang = {"weg": 0, "sichtbar": 1, "still": 2}
        for k, v in ergebnisse.items():
            if k not in alt:
                continue
            d = rang[v["zustand"]] - rang[alt[k]["zustand"]]
            if d < 0:
                besser.append(f"{alt[k]['zustand']} -> {v['zustand']}: {k}")
            elif d > 0:
                schlechter.append(f"{alt[k]['zustand']} -> {v['zustand']}: {k}")
        nur_alt = [k for k in alt if k not in ergebnisse]
        zeilen += ["", f"Vergleich mit {vergleich_mit}: {sum(k in alt for k in ergebnisse)} gemeinsame Einträge, "
                       f"{sum(k not in alt for k in ergebnisse)} nur in dieser Messung, {len(nur_alt)} nur im "
                       f"Vergleich" + (" (Teillauf)" if a.faelle or a.nur else "")]
        zeilen += ["", f"Verbessert: {len(besser)}, verschlechtert: {len(schlechter)}", "", "## Verschlechtert"]
        zeilen += [f"- {x}" for x in schlechter] or ["- keine"]
        if nur_alt and not (a.faelle or a.nur):
            zeilen += ["", "## Fehlen gegenüber dem Vergleich"] + [f"- {k}" for k in nur_alt[:50]]
            zeilen += [f"- … und {len(nur_alt) - 50} weitere"] if len(nur_alt) > 50 else []
        zeilen += ["", "## Verbessert"] + [f"- {x}" for x in besser]
    (ziel / "bericht.md").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    ende = zeilen.index("## Verbessert") if "## Verbessert" in zeilen else len(zeilen)
    print("\n".join(zeilen[:ende]).rstrip())
    print(f"\nBericht: {ziel / 'bericht.md'}")
    if fehler:
        return 1
    if a.als_referenz:
        shutil.copyfile(ziel / "ergebnis.json", REFERENZ)
        REFERENZ_MD.write_text("\n".join(
            ["# Referenz der Domänen-Probe", "",
             "Erzeugt mit `python werkzeuge/domaenenprobe/messen.py <ausgabeordner> --als-referenz` "
             f"am {time.strftime('%d.%m.%Y')}; Einträge: {len(ergebnisse)} (`referenz.json`).", ""]
            + [z for z in umgebung if not z.startswith("- Dauer")] + [""] + tabelle) + "\n", encoding="utf-8")
        print(f"Referenz ersetzt: {REFERENZ} ({len(ergebnisse)} Einträge) und {REFERENZ_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
