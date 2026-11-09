"""Klassische Detektoren: die bisherigen Muster (muster.finde_*) und die Namenserkennung
(namen.finde_personen) als Detektoren, die STELLEN liefern.

Die Muster-Funktionen liefern Fundtexte; jeder Text wird an seinen Ganzwort-Vorkommen im Dokumenttext
verortet (exakte Vorkommen, sonst über den gemeinsamen Vergleicher). Die Namenserkennung liefert schon
Positionen. Dazu kommen die IMMER-Begriffe und eine Formularfeld-Regel (Etikett + Wert, Kammfelder).

Übergangsmodul: Agent "regeln" ersetzt die Muster-/Namens-Detektoren durch eigene Module, die Spans
direkt liefern (gleiche Register-Namen mit ersetzt=True, oder dieses Modul wird entfernt).
"""

from __future__ import annotations

import re

from .. import muster, namen
from ..seitenmodell import ganzwort_stellen, ganzwort_stellen_viele, modus_fuer
from . import ALLE_PROFILE, Treffer, detektor, registrieren

# Sicherheit je Kategorie (1 = Prüfziffer, sonst Heuristik)
SICHERHEIT = {"iban": 1.0, "steuerid": 1.0, "kreditkarte": 1.0, "svnr": 0.9, "email": 0.95, "fin": 0.9,
              "bic": 0.85, "kvnr": 0.9, "kindergeld": 0.85, "steuernr": 0.85, "geburt": 0.8, "telefon": 0.75,
              "strasse": 0.75, "plzort": 0.75, "vertrag": 0.7, "kfz": 0.7, "ausweis": 0.75, "mandat": 0.8,
              "datum": 0.6}


def _vorkommen(dok, texte, modus: str) -> dict:
    """Ganzwort-Vorkommen der Fundtexte eines Musters im Dokumenttext: wie geschrieben (nur Groß-/Klein-
    schreibung und Leerraum flexibel); gibt es keins, dann über den Vergleicher des Kategorie-Modus.
    Alle Texte auf einmal (linear im Text, Gutachten PERF-01)."""
    genau = ganzwort_stellen_viele(dok, texte, "begriff")
    fehlend = [t for t in texte if not genau.get(t)]
    if fehlend and modus != "begriff":
        genau.update(ganzwort_stellen_viele(dok, fehlend, modus))
    return genau


def _funktion(schluessel):
    for k, _, _, f, _ in muster.KATEGORIEN:
        if k == schluessel:
            return f
    return None


def _muster_detektor(schluessel: str):
    quelle = f"muster.{schluessel}"

    def erkennen(dok, kontext):
        funktion = _funktion(schluessel)
        if funktion is None:
            return []
        modus = modus_fuer(schluessel)
        sicherheit = SICHERHEIT.get(schluessel, 0.7)
        texte = [t for t in dict.fromkeys(x.strip() for x in funktion(dok.text) if x and x.strip()) if len(t) >= 2]
        treffer = []
        for stellen in _vorkommen(dok, texte, modus).values():
            for s, e in stellen:
                treffer.append(Treffer(s, e, schluessel, quelle, sicherheit))
        return treffer
    erkennen.__name__ = f"muster_{schluessel}"
    return erkennen


for _schluessel, _anzeige, _platzhalter, _f, _an in muster.KATEGORIEN:
    if _f is not None:
        registrieren(f"muster.{_schluessel}", {_schluessel}, ALLE_PROFILE, _muster_detektor(_schluessel))


# ----------------------------------------------------------------------
# Namen
# ----------------------------------------------------------------------
_ANREDE_DAVOR_RE = re.compile(r"(?:Herrn?|Frau|Hr\.|Fr\.|Fräulein|Familie|Fam\.|Eheleute)[ \t]*$")


def _ohne_ortsnamen(text: str, kandidaten: list) -> list:
    """Einzelwort-Kandidaten verwerfen, die als Ort hinter einer PLZ vorkommen (die KI hält Städte gern
    für Personen) – außer hinter Herr/Frau."""
    orte = set()
    for f in muster.finde_plz_ort(text):
        ort = re.sub(r"^\D*\d{4,5}\s*", "", f).strip()
        if ort:
            orte.add(" ".join(ort.split()).casefold())
    if not orte:
        return kandidaten
    return [k for k in kandidaten
            if not (" " not in k["text"] and k["text"].casefold() in orte
                    and not _ANREDE_DAVOR_RE.search(text[max(0, k["start"] - 12):k["start"]]))]


def _komma_phantome_entfernen(text: str, kandidaten: list) -> list:
    """Gutachten EQ-10 (3): Die Regel "Nachname, Vorname" darf nicht hinter einer Anrede greifen –
    in "Sehr geehrte Frau Krüger, Max Mustermann ist versichert" ist "Krüger, Max" keine Person."""
    phantome = set()
    for k in kandidaten:
        g = k.get("gruppe")
        if g and k["text"] == g and "," in g and _ANREDE_DAVOR_RE.search(text[max(0, k["start"] - 12):k["start"]]):
            phantome.add(g)
    if not phantome:
        return kandidaten
    aus = []
    for k in kandidaten:
        if k.get("gruppe") in phantome:
            if k["text"] == k["gruppe"]:
                continue
            k = dict(k, gruppe=None)
        aus.append(k)
    return aus


@detektor("ner", {"namen"})
def namen_erkennen(dok, kontext):
    """KI-Namenserkennung (spaCy) plus Regeln für Briefe, Formulare und Tabellen (namen.finde_personen)."""
    text = dok.text
    kandidaten = list(namen.finde_personen(text))
    if "plzort" in kontext.aktive:
        kandidaten = _ohne_ortsnamen(text, kandidaten)
    kandidaten = _komma_phantome_entfernen(text, kandidaten)
    treffer = []
    for k in kandidaten:
        s, e = int(k.get("start", -1)), int(k.get("ende", -1))
        gruppe = k.get("gruppe")
        if not (0 <= s < e <= len(text)) or text[s:e] != k["text"]:
            # Position fehlt oder passt nicht: alle Ganzwort-Stellen des Namens
            for s2, e2 in ganzwort_stellen(dok, k["text"], "name"):
                treffer.append(Treffer(s2, e2, "namen", "ner", 0.6, gruppe))
            continue
        # Die KI schneidet Namen gelegentlich mitten im Wort ab ("Olumid|e"): auf ganze Wörter erweitern,
        # damit nie ein Wortrest stehen bleibt
        s0, e0 = s, e
        while s > 0 and text[s - 1].isalnum():
            s -= 1
        while e < len(text) and text[e].isalnum():
            e += 1
        if (s, e) != (s0, e0) and gruppe == k["text"]:
            gruppe = text[s:e]
        treffer.append(Treffer(s, e, "namen", "ner", 0.6, gruppe))
    return treffer


# ----------------------------------------------------------------------
# IMMER-Begriffe
# ----------------------------------------------------------------------
@detektor("immer", {"begriff"})
def immer_begriffe(dok, kontext):
    """IMMER-schwärzen-Begriffe der Nutzerin: jede Ganzwort-Stelle (Groß-/Kleinschreibung egal)."""
    treffer, gesehen = [], set()
    for begriff in kontext.immer:
        b = " ".join(str(begriff or "").split())
        if len(b) < 2 or b.casefold() in gesehen:
            continue
        gesehen.add(b.casefold())
        for s, e in ganzwort_stellen(dok, b, "begriff"):
            treffer.append(Treffer(s, e, "begriff", "immer", 1.0))
    return treffer


# ----------------------------------------------------------------------
# Formularfelder (Gutachten S-02/EQ-02/S-12)
# ----------------------------------------------------------------------
_GEB_ETIKETT_RE = re.compile(r"(?i)geb(?:\.|urt)|geboren")


def _kamm_datum(wert: str):
    """'30071988' / '300788' -> True, wenn es ein plausibles Datum TTMMJJ(JJ) ist."""
    ziffern = "".join(wert.split())
    if not ziffern.isdigit() or len(ziffern) not in (6, 8):
        return False
    t, m = int(ziffern[:2]), int(ziffern[2:4])
    return 1 <= t <= 31 and 1 <= m <= 12


@detektor("klassisch.formularfeld", set(muster.KATEGORIE_PRIORITAET) | {"namen"})
def formularfelder(dok, kontext):
    """Muster auf 'Etikett: Wert' jedes Formularfelds; Treffer im Wert werden an der Stelle des
    eingebrannten Werts verortet. Kammfelder mit Geburtsdatum (TTMMJJJJ ohne Punkte) zählen als
    Geburtsdatum."""
    treffer = []
    for feld in getattr(dok, "felder", []) or []:
        if feld.start < 0 or not feld.wert:
            continue
        g0 = dok.global_(feld.seite, feld.start)
        g1 = dok.global_(feld.seite, feld.ende)
        etikett = feld.etikett or ""
        zeile = f"{etikett}: {feld.wert}" if etikett else feld.wert
        wert_ab = len(zeile) - len(feld.wert)
        for schluessel, _, _, funktion, _ in muster.KATEGORIEN:
            if funktion is None or schluessel not in kontext.aktive:
                continue
            for t in dict.fromkeys(x.strip() for x in funktion(zeile) if x and x.strip()):
                pos = zeile.find(t, wert_ab)
                if pos < wert_ab:
                    continue
                for s, e in ganzwort_stellen(dok.text[g0:g1], t, modus_fuer(schluessel)):
                    treffer.append(Treffer(g0 + s, g0 + e, schluessel, "formularfeld",
                                           SICHERHEIT.get(schluessel, 0.7)))
        if "geburt" in kontext.aktive and _GEB_ETIKETT_RE.search(etikett) and _kamm_datum(feld.wert):
            treffer.append(Treffer(g0, g1, "geburt", "formularfeld", 0.8))
    return treffer
