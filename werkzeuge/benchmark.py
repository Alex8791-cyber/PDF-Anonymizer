"""Entwicklungs-Benchmark des PDF-Anonymisierers: Korpus erzeugen und die Pipeline bewerten.

Aufruf (aus der Projektwurzel):
    python werkzeuge/benchmark.py --anzahl 60 --seed 1 --ausgabe <ordner> [--repo <pfad>]

Ergebnis in <ordner>:
    korpus/            erzeugte PDFs + <name>.wahrheit.json (Schema BENCHMARK_SCHEMA.md)
    anonymisiert/      Ausgaben des Programms (anonym_01.pdf …, _zuordnung.txt)
    ergebnis.json      alle Kennzahlen und Einzelergebnisse
    bericht.md         Markdown-Bericht (Gesamt, je Kategorie, je Merkmal, Lecks, Laufzeiten)

Optionen:
    --repo <pfad>      Programmcode (Paket anonymisierer) aus einem anderen Checkout messen;
                       der Benchmark selbst stammt immer aus diesem Checkout
    --korpus <ordner>  vorhandenen Korpus bewerten (statt zu erzeugen), z. B. einen Prüfkorpus
    --nur-erzeugen     nur den Korpus erzeugen
    --ohne-cli-ocr     Tesseract-Kommandozeile nicht als zweite OCR-Leseart verwenden
    --ohne-pixel       Pixelvergleich an Scan-Wortrechtecken abschalten
"""

import argparse
import multiprocessing
import sys
import time
import warnings
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Entwicklungs-Benchmark: Korpus erzeugen und bewerten")
    parser.add_argument("--anzahl", type=int, default=60, help="Anzahl der zu erzeugenden Dokumente")
    parser.add_argument("--seed", type=int, default=1, help="Startwert des Zufallsgenerators")
    parser.add_argument("--ausgabe", type=Path, required=True, help="Ergebnisordner")
    parser.add_argument("--repo", type=Path, default=None, help="Checkout, dessen Programmcode gemessen wird")
    parser.add_argument("--korpus", type=Path, default=None, help="vorhandenen Korpus bewerten")
    parser.add_argument("--nur-erzeugen", action="store_true", help="nur den Korpus erzeugen")
    parser.add_argument("--ohne-cli-ocr", action="store_true", help="keine Tesseract-Kommandozeile verwenden")
    parser.add_argument("--ohne-pixel", action="store_true", help="keinen Pixelvergleich durchführen")
    args = parser.parse_args(argv)

    warnings.filterwarnings("ignore", category=FutureWarning)   # "fitz" ist in PyMuPDF 2.x veraltet
    if str(WURZEL) not in sys.path:
        sys.path.insert(1, str(WURZEL))
    from werkzeuge.benchmark.bewertung import bewerte_korpus
    from werkzeuge.benchmark.generator import erzeuge_korpus

    ausgabe = args.ausgabe.resolve()
    ausgabe.mkdir(parents=True, exist_ok=True)
    if args.korpus is None:
        korpus = ausgabe / "korpus"
        if korpus.exists() and any(korpus.iterdir()):
            for alt in list(korpus.glob("*.pdf")) + list(korpus.glob("*.wahrheit.json")):
                alt.unlink()
        start = time.perf_counter()
        erzeuge_korpus(korpus, args.anzahl, args.seed)
        print(f"Korpus erzeugt: {args.anzahl} Dokumente in {korpus} ({time.perf_counter() - start:.1f} s)")
    else:
        korpus = args.korpus.resolve()
    if args.nur_erzeugen:
        return 0
    ergebnis = bewerte_korpus(korpus, ausgabe, repo=args.repo, cli_ocr=not args.ohne_cli_ocr,
                              pixel=not args.ohne_pixel)
    g = ergebnis["gesamt"]
    print(f"\nrecall_kern: {g['recall_kern']:.4f} ({g['kern']['entfernt']}/{g['kern']['n']}), "
          f"teilweise {g['kern']['teilweise']}, Leck {g['kern']['leck']}")
    if g["recall_erweitert"] is not None:
        print(f"recall_erweitert: {g['recall_erweitert']:.4f}")
    if g["ueberschwaerzung"] is not None:
        print(f"Über-Schwärzung: {g['ueberschwaerzung']:.4f} ({g['behalten_fehlt']}/{g['behalten_n']})")
    print(f"Fehlalarme: {g['fehlalarme']} von {g['funde']} Funden")
    print(f"Bericht: {ausgabe / 'bericht.md'}")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
