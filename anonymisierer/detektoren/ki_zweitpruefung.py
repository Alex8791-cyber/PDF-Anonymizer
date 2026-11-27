"""Detektor "ki.zweitpruefung": zweite Erkennung durch das in LM Studio geladene Sprachmodell (nur eigener Rechner).

Läuft nur bei eingeschalteter KI-Zweitprüfung (anonymisierer.ki.aktiv()). Das Modell liest jede Seite (lange Seiten
in Teilen) und nennt personenbezogene Werte. Übernommen wird nur, was es als eindeutig („sicher“) einstuft und was
wörtlich im Text steht – dann an jeder Ganzwort-Stelle im Dokument (Quelle "ki.zweitpruefung", Sicherheit 0.6).

Die Regeln bleiben maßgeblich: die KI ergänzt nur, sie nimmt nie eine Schwärzung weg (Grundsatz „nur verschärfen“).
Geschwärzt wird nur in angehakten Kategorien (alle_treffer filtert). Ein einzelnes Wort als Name zählt nur, wenn es
groß beginnt und keine Ziffer enthält; Orte ohne Postleitzahl übernimmt die KI nicht (zu unscharf). Ist LM Studio
nicht erreichbar, liefert der Detektor nichts – die Analyse meldet das (Meldung KI_ZWEITPRUEFUNG).
"""

from __future__ import annotations

import re

from .. import ki, muster, wissen
from ..seitenmodell import ganzwort_stellen_viele, modus_fuer
from . import ALLE_PROFILE, Treffer, detektor

QUELLE = "ki.zweitpruefung"
SICHERHEIT = 0.6
KATEGORIEN = frozenset({"namen", "strasse", "plzort", "geburt", "telefon", "email", "iban", "vertrag", "kfz",
                        "diagnose"})

# Anrede und Titel vor einem Namen gehören nicht zur Stelle ("Herr Dr. Thomas Meier" -> "Thomas Meier")
_VORSATZ_RE = re.compile(r"^(?:(?:Herrn?|Frau|Fr\.|Hr\.|Dr\.(?:\s?(?:med|rer\.\s?nat|jur|phil|dent)\.)?|Prof\.|"
                         r"Dipl\.-\w+\.?|Mag\.|Ing\.)\s+)+")
_NAMENSWORT_RE = re.compile(r"[^\W\d_][^\W\d_'’.-]*(?:[-'’][^\W\d_]+)*\.?")
_PARTIKEL = frozenset({"von", "van", "de", "der", "den", "di", "da", "del", "du", "le", "la", "zu", "zur", "vom",
                       "ten", "ter", "al", "el", "bin", "y"})
_ARTIKEL = frozenset({"der", "den", "dem", "die", "das", "des"})     # nie am Anfang eines Namens ("der Kunde")
_PLZORT_RE = re.compile(r"^\d{4,5}\s+\S")
_STRASSE_RE = re.compile(r"\d|(?i:stra(?:ss|ß)e|str\.|weg|gasse|platz|allee|ring|damm|ufer|chaussee)")


def _kein_name(wort: str) -> bool:
    """Rollen-, Berufs- und Etikettwörter, Anreden und Organisationen sind keine Namen ("Versicherungsnehmer")."""
    w = wissen.normalisieren(wort.rstrip("."))
    return (wissen.ist_anrede_titel(wort) or wissen.ist_allowlist(wort)
            or any(w in wissen.menge(liste) for liste in ("etiketten_person", "berufe", "sachnamen")))


def _mehrdeutig(wort: str) -> bool:
    """Ein Wort, das auch ein Alltagswort ist ("Regen", "Wald"): als Name nur mit Anrede davor."""
    return wissen.ist_allerweltswort(wort) or wissen.ist_mehrdeutig(wort)


def _name(wert: str) -> list:
    """[("namen", name, suchtext)] – der Name ohne Anrede/Titel; ein mehrdeutiges einzelnes Wort ("Wald") nur dort,
    wo es mit seiner Anrede steht (suchtext "Herr Wald"), sonst gar nicht – „im Wald“ bleibt stehen."""
    kern = _VORSATZ_RE.sub("", wert).strip(" ,;:")
    woerter = kern.split()
    if not woerter or len(woerter) > 5 or len(kern) > 60 or any(ch.isdigit() for ch in kern):
        return []
    if woerter[0].casefold() in _ARTIKEL:
        return []
    echte = []
    for w in woerter:
        if w.casefold() in _PARTIKEL:
            continue
        if not _NAMENSWORT_RE.fullmatch(w) or not w[0].isupper() or len(w.rstrip(".")) < 2 and len(woerter) == 1:
            return []
        echte.append(w)
    if not echte or all(_kein_name(w) for w in echte):
        return []
    if len(echte) == 1 and (_kein_name(echte[0]) or _mehrdeutig(echte[0])):
        anrede = wert[:len(wert) - len(kern)].strip() if wert.endswith(kern) else ""
        if not anrede:
            return []
        varianten = [anrede]
        if anrede.split()[0] in ("Herr", "Herrn"):          # „Herr Wald“ steht auch als „Herrn Wald“ im Text
            rest = anrede.split()[1:]
            varianten = [" ".join([a, *rest]) for a in ("Herr", "Herrn")]
        return [("namen", kern, f"{v} {kern}") for v in varianten]
    return [("namen", kern, kern)]


def zerlegen(art: str, wert: str) -> list:
    """[(kategorie, wert, suchtext)] eines Funds des Modells: Namen ohne Anrede, Anschriften je Teil (Straße |
    PLZ Ort), Kennungen nach ihrer Gestalt (Kfz-Kennzeichen, sonst Vertrags-/Kundennummer). Geschwärzt wird wert an
    jeder Stelle, an der suchtext steht."""
    wert = " ".join(str(wert or "").split())
    if len(wert) < 2:
        return []
    if art == "name":
        return _name(wert)
    if art == "anschrift":
        aus = []
        for teil in re.split(r"\s*[,;]\s*|\s+·\s+", wert):
            teil = teil.strip()
            if len(teil) < 4:
                continue
            if _PLZORT_RE.match(teil):
                aus.append(("plzort", teil, teil))
            elif _STRASSE_RE.search(teil):
                aus.append(("strasse", teil, teil))
        return aus
    if art == "kennung":
        if sum(ch.isalnum() for ch in wert) < 4:
            return []
        if any(st.start == 0 and st.ende == len(wert) for st in muster.stellen("kfz", wert)):
            return [("kfz", wert, wert)]
        return [("vertrag", wert, wert)]
    kategorie = ki.kategorie_fuer(art, wert)
    return [(kategorie, wert, wert)] if kategorie else []


@detektor("ki.zweitpruefung", KATEGORIEN, ALLE_PROFILE)
def ki_zweitpruefung(dok, kontext):
    """Personenbezogene Werte, die das lokale Sprachmodell eindeutig erkennt (nur mit eingeschalteter KI)."""
    if not ki.aktiv():
        return []
    d = ki.dienst()
    if d is None or d.modell() is None:
        return []
    gesucht: dict = {}                     # modus -> {suchtext: (kategorie, wert)}
    for teil in ki.teile(dok):
        try:
            funde = d.personendaten(teil)
        except ki.KiFehler as e:
            d.fehler.append(str(e))
            break
        for f in funde:
            if not f.get("sicher"):
                continue
            for kategorie, wert, such in zerlegen(f.get("art", ""), f.get("text", "")):
                if kategorie in kontext.aktive:
                    gesucht.setdefault(modus_fuer(kategorie), {}).setdefault(such, (kategorie, wert))
    treffer = []
    for modus, je_such in gesucht.items():
        for such, stellen in ganzwort_stellen_viele(dok, list(je_such), modus).items():
            kategorie, wert = je_such[such]
            for s, e in stellen:
                if such != wert:                # "Herr Wald": nur der Name wird Stelle
                    i = dok.text[s:e].casefold().rfind(wert.casefold())
                    if i < 0:
                        continue
                    s, e = s + i, s + i + len(wert)
                treffer.append(Treffer(s, e, kategorie, QUELLE, SICHERHEIT))
    return treffer
