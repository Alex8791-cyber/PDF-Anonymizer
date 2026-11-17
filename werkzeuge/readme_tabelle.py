#!/usr/bin/env python3
"""Erzeugt die Erkennungstabelle der README aus anonymisierer.muster.KATEGORIEN und muster.PROFILE.

Damit README und Code nicht auseinanderlaufen:
    python werkzeuge/readme_tabelle.py             # Tabelle anzeigen
    python werkzeuge/readme_tabelle.py --schreiben # Tabelle in README.md ersetzen

In der README steht die Tabelle zwischen den Markierungen
<!-- TABELLE-ANFANG --> und <!-- TABELLE-ENDE -->. Die Spalte „Angehakt ab Stufe“ kommt aus den Schutzstufen
(muster.PROFILE), Beispiele und Hinweise aus BEISPIELE und ERLAEUTERUNG unten. tests/test_auslieferung.py prüft,
dass die README-Tabelle genau dieser Ausgabe entspricht und dass jedes Beispiel von seiner Kategorie erkannt wird.
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

# Beispiele je Kategorie-Schlüssel (für Kategorien ohne Eintrag erscheint "–"). Jedes Beispiel muss die Erkennung
# seiner Kategorie finden (tests/test_auslieferung.py); Personennamen erkennt das Sprachmodell (tests/test_namen.py).
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
    "steuernr": "Steuernummer: 181/815/08155",
    "kvnr": "A123456780",
    "kindergeld": "009FK407160",
    "kfz": "N-XY 123",
    "fin": "WVWZZZ1JZXW000001",
    "ausweis": "Ausweisnummer: L01X00T47",
    "mandat": "Mandatsreferenz MR-2024-0815",
    "bic": "COBADEFFXXX",
    "kreditkarte": "4111 1111 1111 1111",
    "international": "Kerkstraat 12, 1017 GC Amsterdam",
    "ort": "Musterstadt, 03.04.2025",
    "beruf": "Beruf: Elektriker",
    "arbeitgeber": "Arbeitgeber: Muster Bau GmbH",
    "diagnose": "Diagnose: Diabetes mellitus (E11.9)",
    "medikament": "Medikation: Metformin 500 mg",
    "datum": "15.03.2024",
}
ERLAEUTERUNG = {
    "namen": "KI-Modell (spaCy), Namenslisten und Regeln; gleiche Person = gleicher Platzhalter im Dokument",
    "iban": "auch mit falscher Prüfziffer, wenn sie eindeutig wie eine IBAN aussieht (Hinweis „Lesefehler?“)",
    "geburt": "hinter „geb.“, „Geburtsdatum“ … oder hinter einem Namen mit Komma, Stern oder Klammer („Max "
              "Mustermann, 02.09.1983“); in „Maximal“ zusätzlich Daten wie „02.09.1983“, die mindestens 14 Jahre "
              "zurückliegen – außer kurz hinter Wörtern wie „am“, „vom“, „seit“ oder „Beginn“",
    "vertrag": "Nummer hinter einem Etikett wie „Vertrags-Nr.“",
    "steuerid": "ohne Beschriftung nur mit gültiger Prüfziffer",
    "steuernr": "ohne Etikett nur mit Schrägstrichen; USt-IdNr. nur mit Etikett und nicht die einer Firma",
    "ausweis": "mit Etikett; Ausweis- und Passnummern auch ohne Etikett, wenn die Prüfziffer stimmt; auf "
               "Ausweiskopien auch die maschinenlesbare Zone",
    "mandat": "nur hinter einem Etikett",
    "bic": "hinter „BIC“, neben einer IBAN oder in eindeutiger Form (11 Zeichen auf „XXX“ oder mit Ziffer im Ortscode)",
    "ort": "Ort-Datum-Zeile, „geboren in …“, „wohnhaft in …“",
    "beruf": "hinter „Beruf:“ oder im Satz („arbeitet als …“)",
    "arbeitgeber": "hinter „Arbeitgeber:“ oder im Satz; bekannte Versicherer, Banken und Behörden bleiben stehen",
    "diagnose": "nur bekannte Begriffe und ICD-Codes mit Gesundheitsbezug; in „Ausgewogen“ und „Hoch“ nur angeboten "
                "(⚕, nicht angehakt)",
    "medikament": "nur bekannte Begriffe mit Gesundheitsbezug; in „Ausgewogen“ und „Hoch“ nur angeboten "
                  "(⚕, nicht angehakt)",
    "datum": "Vorsicht: auch Vertrags- und Briefdaten",
}
# Schutzstufen von der mildesten zur strengsten (Schlüssel in muster.PROFILE, Name in der Tabelle)
STUFEN = (("ausgewogen", "Ausgewogen"), ("hoch", "Hoch"), ("maximal", "Maximal"))
NUR_VON_HAND = "– (nur von Hand)"


def angehakt_ab(schluessel: str, profile=None) -> str:
    """Mildeste Schutzstufe, die die Kategorie anhakt („Ausgewogen“ = in jeder Stufe), NUR_VON_HAND, wenn keine
    Stufe sie anhakt. Haken die Stufen sie nicht von einer Stufe an aufwärts an: „nur …“ mit den einzelnen Stufen."""
    if profile is None:
        from anonymisierer.muster import PROFILE as profile
    stufen = [name for schluessel_stufe, name in STUFEN if schluessel in profile[schluessel_stufe]["aktive"]]
    if not stufen:
        return NUR_VON_HAND
    namen = [name for _, name in STUFEN]
    if stufen == namen[len(namen) - len(stufen):]:
        return stufen[0]
    return "nur " + ", ".join(stufen)


def tabelle() -> str:
    from anonymisierer.muster import KATEGORIEN, PROFILE

    zeilen = ["| Kategorie | Beispiel | Wird ersetzt durch | Angehakt ab Stufe | Hinweis |",
              "|---|---|---|---|---|"]
    for schluessel, anzeige, platzhalter, _funktion, _an in KATEGORIEN:
        ersatz = platzhalter or "[PERSON A], [PERSON B] …"
        zeilen.append(f"| {anzeige} | {BEISPIELE.get(schluessel, '–')} | `{ersatz}` | "
                      f"{angehakt_ab(schluessel, PROFILE)} | {ERLAEUTERUNG.get(schluessel, '')} |")
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
