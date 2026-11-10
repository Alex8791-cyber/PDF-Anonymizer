#!/usr/bin/env python3
"""Erzeugt die Erkennungstabelle der README aus anonymisierer.muster.KATEGORIEN.

Damit README und Code nicht auseinanderlaufen:
    python werkzeuge/readme_tabelle.py             # Tabelle anzeigen
    python werkzeuge/readme_tabelle.py --schreiben # Tabelle in README.md ersetzen

In der README steht die Tabelle zwischen den Markierungen
<!-- TABELLE-ANFANG --> und <!-- TABELLE-ENDE -->.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROGRAMM_ORDNER = Path(__file__).resolve().parent.parent
if str(PROGRAMM_ORDNER) not in sys.path:
    sys.path.insert(0, str(PROGRAMM_ORDNER))

README = PROGRAMM_ORDNER / "README.md"
ANFANG = "<!-- TABELLE-ANFANG -->"
ENDE = "<!-- TABELLE-ENDE -->"

# Beispiele je Kategorie-Schlüssel (für Kategorien ohne Eintrag erscheint "–")
BEISPIELE = {
    "namen": "Max Mustermann",
    "iban": "DE89 3704 0044 0532 0130 00",
    "email": "max.mustermann@example.de",
    "telefon": "0171 2345678",
    "geburt": "geb. am 02.09.1983",
    "strasse": "Hauptstraße 12a",
    "plzort": "90402 Nürnberg",
    "vertrag": "Versicherungsschein-Nr. LV-2024-887766",
    "svnr": "12 345678 A 123",
    "steuerid": "91064389278",
    "kindergeld": "009FK407160",
    "kfz": "N-XY 123",
    "datum": "15.03.2024",
}
ERLAEUTERUNG = {
    "namen": "KI-Modell (spaCy); gleiche Person = gleicher Platzhalter",
    "iban": "nur mit gültiger Prüfsumme",
    "geburt": "Datum hinter „geb.“, „Geburtsdatum“ …",
    "vertrag": "Nummer hinter einem Etikett wie „Vertrags-Nr.“",
    "steuerid": "amtliche Prüfziffer, auch ohne Beschriftung",
    "datum": "Vorsicht: auch Vertrags- und Briefdaten",
}


def tabelle() -> str:
    from anonymisierer.muster import KATEGORIEN

    zeilen = ["| Kategorie | Beispiel | Wird ersetzt durch | Standard | Hinweis |",
              "|---|---|---|---|---|"]
    for schluessel, anzeige, platzhalter, _funktion, an in KATEGORIEN:
        ersatz = platzhalter or "[PERSON A], [PERSON B] …"
        zeilen.append(f"| {anzeige} | {BEISPIELE.get(schluessel, '–')} | `{ersatz}` | "
                      f"{'an' if an else 'aus'} | {ERLAEUTERUNG.get(schluessel, '')} |")
    return "\n".join(zeilen)


def readme_aktualisieren(pfad: Path = README) -> bool:
    """Ersetzt die Tabelle zwischen den Markierungen. Rückgabe: wurde etwas geändert?"""
    text = pfad.read_text(encoding="utf-8")
    a, e = text.find(ANFANG), text.find(ENDE)
    if a < 0 or e < 0 or e < a:
        raise SystemExit(f"Markierungen {ANFANG} / {ENDE} fehlen in {pfad}")
    neu = text[:a + len(ANFANG)] + "\n" + tabelle() + "\n" + text[e:]
    if neu == text:
        return False
    pfad.write_text(neu, encoding="utf-8")
    return True


if __name__ == "__main__":
    if "--schreiben" in sys.argv[1:]:
        print("README aktualisiert." if readme_aktualisieren() else "README war schon aktuell.")
    else:
        print(tabelle())
