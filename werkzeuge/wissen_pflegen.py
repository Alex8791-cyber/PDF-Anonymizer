#!/usr/bin/env python3
"""Pflegewerkzeug für die Wortlisten der Wissensbasis (anonymisierer/daten).

    python werkzeuge/wissen_pflegen.py              # prüfen, Bericht ausgeben
    python werkzeuge/wissen_pflegen.py --schreiben  # sortieren, doppelte Einträge entfernen, prüfen

Neue Einträge an beliebiger Stelle in die passende .txt-Datei schreiben (ein Eintrag je
Zeile) und danach mit --schreiben einsortieren lassen. Geprüft werden:

- UTF-8 ohne BOM, LF-Zeilenenden, NFC, keine Steuerzeichen, Kommentare (#) nur im Dateikopf
- Sortierung nach Vergleichsform (anonymisierer.wissen.sortierschluessel), keine Dubletten
  (auch nicht bis auf Groß-/Kleinschreibung)
- allerweltswoerter_gross enthält keine Vor-/Nachnamen, Berufe, Diagnosen, Medikamente und
  kein Wort, das über die Beugungsregel von ist_allerweltswort einen Namen träfe
- der Kern jedes Namens mit Partikel ("Vries" aus "de Vries") steht als eigener Nachname
  in der Liste, außer er ist Vorname oder Allerweltswort ("Marco", "Meer")
- jeder Eintrag von nachnamen_mehrdeutig ist ein Nachname, jeder von vornamen_mehrdeutig
  ein Vorname
- Berufe und Einzelwörter der Erlaubnisliste, die zugleich Nachnamen sind, stehen in
  nachnamen_mehrdeutig (Regeln brauchen dort Kontext)

Rückgabewert 0 = alles in Ordnung, 1 = Probleme gefunden (Bericht auf der Konsole).
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

PROGRAMM_ORDNER = Path(__file__).resolve().parent.parent
if str(PROGRAMM_ORDNER) not in sys.path:
    sys.path.insert(0, str(PROGRAMM_ORDNER))

from anonymisierer import wissen  # noqa: E402


def datei_aufbereiten(pfad: Path, schreiben: bool) -> list[str]:
    """Prüft (und ordnet auf Wunsch) eine Listendatei. Liefert die gefundenen Probleme."""
    probleme = []
    roh = pfad.read_bytes()
    try:
        text = roh.decode("utf-8")
    except UnicodeDecodeError as fehler:
        return [f"{pfad.name}: kein UTF-8 ({fehler})"]
    if text.startswith("﻿"):
        probleme.append(f"{pfad.name}: Byte-Order-Mark am Anfang")
        text = text[1:]
    if "\r" in text:
        probleme.append(f"{pfad.name}: Windows-Zeilenenden (CRLF) statt LF")
    kopf, eintraege, im_kopf = [], [], True
    for nr, zeile in enumerate(text.splitlines(), 1):
        inhalt = zeile.strip()
        if not inhalt:
            continue
        if inhalt.startswith("#"):
            if not im_kopf:
                probleme.append(f"{pfad.name}:{nr}: Kommentar nach dem ersten Eintrag")
            kopf.append(inhalt)
            continue
        im_kopf = False
        if zeile != inhalt:
            probleme.append(f"{pfad.name}:{nr}: Leerraum am Zeilenrand")
        if any(unicodedata.category(z) == "Cc" for z in inhalt):
            probleme.append(f"{pfad.name}:{nr}: Steuerzeichen")
        nfc = " ".join(unicodedata.normalize("NFC", inhalt).split())
        if nfc != inhalt:
            probleme.append(f"{pfad.name}:{nr}: nicht NFC oder doppelter Leerraum")
        eintraege.append(nfc)
    eindeutig, gesehen, gesehen_klein = [], set(), {}
    for e in eintraege:
        if e in gesehen:
            probleme.append(f"{pfad.name}: Dublette {e!r}")
            continue
        klein = e.casefold()
        if klein in gesehen_klein:
            probleme.append(f"{pfad.name}: Dublette bis auf Groß-/Kleinschreibung "
                            f"{gesehen_klein[klein]!r} / {e!r}")
        gesehen.add(e)
        gesehen_klein.setdefault(klein, e)
        eindeutig.append(e)
    sortiert = sorted(eindeutig, key=wissen.sortierschluessel)
    if sortiert != eintraege:
        probleme.append(f"{pfad.name}: nicht sortiert oder mit Dubletten")
    if schreiben:
        # newline="\n": auch unter Windows Unix-Zeilenenden (siehe .gitattributes)
        pfad.write_text("\n".join(kopf + sortiert) + "\n", encoding="utf-8", newline="\n")
    return probleme


def querpruefungen() -> list[str]:
    """Überschneidungen zwischen den Listen (nach dem Schreiben neu geladen)."""
    for funktion in (wissen._liste, wissen._index, wissen._menge, wissen._partikel_folgen):
        funktion.cache_clear()
    probleme = []
    gesperrt = set()
    for name in ("vornamen", "nachnamen", "berufe", "diagnosen", "medikamente"):
        gesperrt |= wissen.menge(name)
    for eintrag in wissen.liste("allerweltswoerter_gross"):
        if wissen.normalisieren(eintrag) in gesperrt or wissen.ist_vorname(eintrag) \
                or wissen.ist_nachname(eintrag):
            probleme.append(f"allerweltswoerter_gross: {eintrag!r} ist Name/Beruf/Diagnose/Medikament")
    for name in wissen.liste("vornamen") + wissen.liste("nachnamen"):
        if wissen.ist_allerweltswort(name):
            probleme.append(f"Name {name!r} gilt als Allerweltswort (Beugungsregel)")
    for eintrag in wissen.liste("nachnamen"):
        kern = wissen._partikel_kern(eintrag)
        if kern and not (wissen._im_index("nachnamen", kern) or wissen.ist_vorname(kern)
                         or wissen.ist_allerweltswort(kern)):
            probleme.append(f"nachnamen: Kern {kern!r} von {eintrag!r} fehlt als eigener Eintrag "
                            f"(ist er ein gewöhnliches Wort: in allerweltswoerter_gross)")
    for eintrag in wissen.liste("nachnamen_mehrdeutig"):
        if not wissen.ist_nachname(eintrag):
            probleme.append(f"nachnamen_mehrdeutig: {eintrag!r} fehlt in nachnamen")
    for eintrag in wissen.liste("vornamen_mehrdeutig"):
        if not wissen.ist_vorname(eintrag):
            probleme.append(f"vornamen_mehrdeutig: {eintrag!r} fehlt in vornamen")
    for eintrag in wissen.liste("berufe"):
        if wissen.ist_nachname(eintrag) and not wissen.ist_mehrdeutig(eintrag):
            probleme.append(f"berufe: {eintrag!r} ist auch Nachname, fehlt in nachnamen_mehrdeutig")
    for eintrag in wissen.liste("versicherer_und_organisationen"):
        if len(wissen.woerter(eintrag)) == 1:
            if wissen.ist_nachname(eintrag) and not wissen.ist_mehrdeutig(eintrag):
                probleme.append(f"Erlaubnisliste: {eintrag!r} ist auch Nachname, "
                                f"fehlt in nachnamen_mehrdeutig")
            if wissen.ist_vorname(eintrag) and not wissen.ist_vorname_mehrdeutig(eintrag):
                probleme.append(f"Erlaubnisliste: {eintrag!r} ist auch Vorname, "
                                f"fehlt in vornamen_mehrdeutig")
    return probleme


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schreiben", action="store_true",
                        help="Dateien sortieren, doppelte Einträge entfernen, LF-Zeilenenden")
    args = parser.parse_args(argv)
    try:                        # Windows-Konsole mit cp1252: Namen wie "Łukasz" nicht abbrechen
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ordner = wissen.daten_ordner()
    probleme = []
    for name, datei in wissen.LISTEN.items():
        pfad = ordner / datei
        if not pfad.is_file():
            probleme.append(f"Datei fehlt: {pfad}")
            continue
        probleme += datei_aufbereiten(pfad, args.schreiben)
    if args.schreiben:
        # nach dem Ordnen erneut prüfen: übrig bleiben nur echte Probleme
        probleme = [p for name, datei in wissen.LISTEN.items()
                    for p in datei_aufbereiten(ordner / datei, False)]
    probleme += querpruefungen()
    for name in wissen.LISTEN:
        print(f"{name:34s} {len(wissen.liste(name)):6d} Einträge")
    if probleme:
        print(f"\n{len(probleme)} Problem(e):")
        for p in probleme:
            print("  -", p)
        return 1
    print("\nAlles in Ordnung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
