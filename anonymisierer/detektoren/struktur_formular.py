"""Strukturregel »struktur.formularfeld« (Vertrag Abschnitt 3, Gutachten S-02/EQ-02/S-12).

Dokument.felder kennt für jedes Formularfeld (vor dem Einbrennen gelesen) den Feldnamen, das sichtbare
Etikett und die Stelle des eingebrannten Werts im Seitentext. Das Etikett – sonst der Feldname
("f_Ort_25_306" -> "Ort", "geburtsDatum" -> "geburts Datum") – wird in den Etiketten der Wissensbasis
nachgeschlagen; die Art bestimmt die Kategorie des Werts: "Ort" -> plzort, auch wenn die PLZ in einem
eigenen Feld steht, "PLZ" -> plzort, "Vorname" -> namen, "Geburtsdatum" -> geburt (auch Kammfelder
"30071988"), "Straße" -> strasse, "Telefon" -> telefon, "IBAN" -> iban …
"""

from __future__ import annotations

import re

from . import Treffer, detektor
from .struktur import ALLE_KATEGORIEN, etikett_fuer_text, werte_lesen

QUELLE = "struktur.formularfeld"


def _feldname_lesbar(name: str) -> str:
    """"f_Ort_25_306" -> "Ort", "geburtsDatum" -> "geburts Datum", "plz-ort" -> "plz ort"."""
    n = re.sub(r"^(?:f|fld|feld|field|txt|text|tf)[_\-.]", "", name or "", flags=re.IGNORECASE)
    n = re.sub(r"[_\-.]\d+(?=[_\-.]|$)", "", n)
    n = re.sub(r"(?<=[a-zäöü])(?=[A-ZÄÖÜ])", " ", n)
    return " ".join(re.sub(r"[_\-.\[\]]+", " ", n).split())


def _etikett_fuer(text: str):
    """Etikett-Objekt (Arten, Kategorie, Eintrag) für einen Feldbezeichner oder None (neutrale Köpfe zählen
    nicht)."""
    et = etikett_fuer_text(text)
    if et is None or "neutral" in et.arten:
        return None
    return et


def _kamm_datum(wert: str):
    ziffern = "".join(wert.split())
    if not ziffern.isdigit() or len(ziffern) not in (6, 8):
        return False
    t, m = int(ziffern[:2]), int(ziffern[2:4])
    return 1 <= t <= 31 and 1 <= m <= 12


@detektor(QUELLE, ALLE_KATEGORIEN)
def formularfeld(dok, kontext):
    """Werte von Formularfeldern nach der Art ihres Etiketts bzw. Feldnamens."""
    treffer = []
    for feld in getattr(dok, "felder", []) or []:
        if feld.start < 0 or feld.ende <= feld.start or not (feld.wert or "").strip():
            continue
        nr = feld.seite
        if nr >= len(dok.seiten):
            continue
        seite = dok.seiten[nr]
        et = _etikett_fuer(feld.etikett) or _etikett_fuer(_feldname_lesbar(feld.name))
        if et is None:
            continue
        werte = werte_lesen(seite.text, feld.start, feld.ende, et, True)
        if not werte and "datum_geburt" in et.arten and _kamm_datum(seite.text[feld.start:feld.ende]):
            treffer.append(Treffer(dok.global_(nr, feld.start), dok.global_(nr, feld.ende), "geburt", QUELLE, 0.8))
            continue
        for w in werte:
            treffer.append(Treffer(dok.global_(nr, w.start), dok.global_(nr, w.ende), w.kategorie, QUELLE, 0.85,
                                   w.gruppe))
    return [t for t in treffer if t.kategorie in kontext.aktive or not kontext.aktive]
