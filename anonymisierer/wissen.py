"""Wissensbasis: kuratierte Wortlisten für die Erkennungsregeln.

Die Listen liegen als UTF-8-Textdateien in ``anonymisierer/daten`` (ein Eintrag je Zeile,
Kommentarzeilen mit ``#`` nur im Kopf der Datei, sortiert, ohne Dubletten; Herkunft und
Pflege siehe ``daten/QUELLEN.md``). Dieses Modul lädt eine Liste erst beim ersten Zugriff
und hält sie danach zwischengespeichert (unveränderliche Tupel, Mengen und Suchindizes).

Öffentliche Schnittstelle:

- ``normalisieren(wort)``: Vergleichsform (casefold, ß → ss, Diakritika entfernt:
  "Çelik" → "celik", "Łukasz" → "lukasz", "Müller" → "muller").
- ``ist_vorname``, ``ist_nachname``, ``ist_mehrdeutig``, ``ist_vorname_mehrdeutig``,
  ``ist_partikel``, ``ist_anrede_titel``, ``ist_allerweltswort``: Einzelwort-Prüfungen.
- ``ist_beruf``, ``ist_diagnose``, ``ist_medikament``: längster Listeneintrag, der als
  ganze Wortfolge in der Phrase vorkommt, sonst ``None`` (als Wahrheitswert verwendbar).
- ``ist_allowlist(phrase)``: True, wenn die Phrase vollständig aus Einträgen der Liste
  ``versicherer_und_organisationen`` besteht (Versicherer, Behörden, Banken, Produkte).
- ``etiketten(art)``: Feldbezeichner einer Art, nach Länge absteigend (für Alternationen).
- ``finde(text, liste)``: alle Vorkommen einer Liste im Text – wortgenau, längster
  Treffer zuerst, ohne Überlappung. ``Phrasenindex`` bietet dasselbe für eigene Listen
  (z. B. die NIE-/IMMER-Listen der Oberfläche).
- ``liste(name)``, ``menge(name)``, ``index(name)``: Rohzugriff (Tupel der Einträge,
  Menge der Vergleichsformen, Suchindex).

Vergleichsregeln (gelten für alle Prüf- und Suchfunktionen):

- Groß-/Kleinschreibung und Diakritika sind egal; ä/ö/ü passen außerdem auf die
  Umschrift ae/oe/ue ("Mueller" findet "Müller", "Muller" ebenfalls).
- Verglichen werden ganze Wörter (Buchstaben-/Ziffernfolgen): "Arzt" passt nicht in
  "Zahnarzt", "Rentner" nicht in "Rentnerin".
- Leerraum, Bindestrich und Punkt zwischen zwei Wörtern sind gleichwertig
  ("Kfz-Haftpflicht" = "Kfz Haftpflicht", "Dr. med." = "Dr.med."); andere Zeichen
  (+ & / ' , …) müssen übereinstimmen ("R+V" passt nicht auf "R, V").
- Treffer laufen nicht über Zeilenumbrüche, außer mit ``zeilenuebergreifend=True``.
- Am Zeilenende getrennte Wörter ("Bandscheiben-\\nvorfall") werden nicht
  zusammengesetzt; dafür muss der Aufrufer den Text vorher entsilben.

Für das PyInstaller-Paket muss der Ordner ``anonymisierer/daten`` mitkopiert werden
(``--add-data "anonymisierer\\daten;anonymisierer\\daten"``); gesucht wird neben dieser
Datei und ersatzweise unter ``sys._MEIPASS``.
"""

from __future__ import annotations

import functools
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, NamedTuple

__all__ = [
    "LISTEN", "ETIKETTEN_ARTEN", "WissensbasisFehler", "Vorkommen", "Phrasenindex",
    "daten_ordner", "lies_listendatei", "liste", "menge", "index", "finde",
    "normalisieren", "normalisieren_umschrift", "sortierschluessel", "woerter",
    "ist_vorname", "ist_nachname", "ist_mehrdeutig", "ist_vorname_mehrdeutig",
    "ist_partikel", "ist_anrede_titel",
    "ist_allerweltswort", "ist_beruf", "ist_diagnose", "ist_medikament", "ist_allowlist",
    "etiketten",
]

# ----------------------------------------------------------------------
# Listen und Dateien
# ----------------------------------------------------------------------
LISTEN = {
    "vornamen": "vornamen.txt",
    "vornamen_mehrdeutig": "vornamen_mehrdeutig.txt",
    "nachnamen": "nachnamen.txt",
    "partikel": "partikel.txt",
    "nachnamen_mehrdeutig": "nachnamen_mehrdeutig.txt",
    "berufe": "berufe.txt",
    "diagnosen": "diagnosen.txt",
    "medikamente": "medikamente.txt",
    "versicherer_und_organisationen": "versicherer_und_organisationen.txt",
    "etiketten_person": "etiketten_person.txt",
    "etiketten_kennung": "etiketten_kennung.txt",
    "etiketten_datum_geburt": "etiketten_datum_geburt.txt",
    "etiketten_adresse": "etiketten_adresse.txt",
    "etiketten_kontakt": "etiketten_kontakt.txt",
    "etiketten_vertragsdaten": "etiketten_vertragsdaten.txt",
    "allerweltswoerter_gross": "allerweltswoerter_gross.txt",
    "anreden_titel": "anreden_titel.txt",
}
# Kurznamen (bequemer in Regeln)
_ALIAS = {
    "allowlist": "versicherer_und_organisationen",
    "mehrdeutig": "nachnamen_mehrdeutig",
    "allerweltswoerter": "allerweltswoerter_gross",
    "titel": "anreden_titel",
    "anreden": "anreden_titel",
}
ETIKETTEN_ARTEN = ("person", "kennung", "datum_geburt", "adresse", "kontakt", "vertragsdaten")


class WissensbasisFehler(RuntimeError):
    """Eine Wortliste fehlt oder ist beschädigt (Installation unvollständig)."""


def daten_ordner() -> Path:
    """Ordner mit den Wortlisten: neben diesem Modul, im PyInstaller-Paket ersatzweise
    unter sys._MEIPASS/anonymisierer/daten bzw. sys._MEIPASS/daten."""
    kandidaten = [Path(__file__).resolve().parent / "daten"]
    basis = getattr(sys, "_MEIPASS", None)
    if basis:
        kandidaten += [Path(basis) / "anonymisierer" / "daten", Path(basis) / "daten"]
    for ordner in kandidaten:
        if (ordner / LISTEN["vornamen"]).is_file():
            return ordner
    return kandidaten[0]


def _listenname(name: str) -> str:
    name = _ALIAS.get(name, name)
    if name not in LISTEN:
        raise KeyError(f"Unbekannte Wortliste: {name!r} (bekannt: {', '.join(sorted(LISTEN))})")
    return name


def lies_listendatei(pfad: Path) -> tuple[list[str], list[str]]:
    """Liest eine Listendatei: (Kommentarzeilen, Einträge). Leere Zeilen werden übersprungen,
    Einträge auf NFC gebracht und innen auf einfache Leerzeichen vereinheitlicht."""
    try:
        roh = Path(pfad).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise WissensbasisFehler(
            f"Wortliste fehlt: {pfad} – die Installation ist unvollständig "
            f"(der Ordner anonymisierer/daten muss mitgeliefert werden).") from None
    except UnicodeDecodeError as fehler:
        raise WissensbasisFehler(f"Wortliste ist kein gültiges UTF-8: {pfad} ({fehler})") from None
    if roh.startswith("﻿"):
        roh = roh[1:]
    kommentare, eintraege = [], []
    for zeile in roh.splitlines():
        inhalt = zeile.strip()
        if not inhalt:
            continue
        if inhalt.startswith("#"):
            kommentare.append(inhalt)
            continue
        eintraege.append(" ".join(unicodedata.normalize("NFC", inhalt).split()))
    return kommentare, eintraege


@functools.lru_cache(maxsize=None)
def _liste(name: str) -> tuple[str, ...]:
    _kommentare, eintraege = lies_listendatei(daten_ordner() / LISTEN[name])
    if not eintraege:
        raise WissensbasisFehler(f"Wortliste ist leer: {LISTEN[name]}")
    return tuple(eintraege)


def liste(name: str) -> tuple[str, ...]:
    """Alle Einträge einer Wortliste in Dateireihenfolge (Originalschreibweise)."""
    return _liste(_listenname(name))


# ----------------------------------------------------------------------
# Normalisierung
# ----------------------------------------------------------------------
# Buchstaben ohne Zerlegung in Grundzeichen + Akzent (NFKD hilft dort nicht)
_SONDERZEICHEN = {
    "ß": "ss", "ẞ": "ss", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe", "ø": "o", "Ø": "o",
    "ł": "l", "Ł": "l", "đ": "d", "Đ": "d", "ð": "d", "Ð": "d", "þ": "th", "Þ": "th",
    "ı": "i", "ħ": "h", "Ħ": "h", "ŧ": "t", "Ŧ": "t", "ŀ": "l", "Ŀ": "l", "ĸ": "k",
    "ſ": "s", "ƒ": "f", "ə": "e", "Ə": "e", "ǝ": "e",
}
# Umschrift wie im Deutschen üblich (Müller -> Mueller, Søren -> Soeren, Åsa -> Aasa)
_UMSCHRIFT_DE = {"ä": "ae", "Ä": "ae", "ö": "oe", "Ö": "oe", "ü": "ue", "Ü": "ue",
                 "ø": "oe", "Ø": "oe", "å": "aa", "Å": "aa"}
_APOSTROPHE = "’‘‛`´ʼʹ′ꞌ"
_STRICHE = "‐‑‒–—―−"
_UNSICHTBAR = "­​‌‍⁠﻿"
_BEREICHE = ((0x00C0, 0x0250), (0x0370, 0x0530), (0x1E00, 0x1F00), (0xFB00, 0xFB07))


def _baue_faltung(deutsch: bool) -> dict[int, str | None]:
    sonder = dict(_SONDERZEICHEN)
    if deutsch:
        sonder.update(_UMSCHRIFT_DE)
    tabelle: dict[int, str | None] = {}
    for anfang, ende in _BEREICHE:
        for codepunkt in range(anfang, ende):
            zeichen = chr(codepunkt)
            if zeichen in sonder:
                tabelle[codepunkt] = sonder[zeichen]
                continue
            zerlegt = unicodedata.normalize("NFKD", zeichen.casefold())
            ziel = "".join(sonder.get(z, z) for z in zerlegt if not unicodedata.combining(z))
            if ziel != zeichen:
                tabelle[codepunkt] = ziel
    for codepunkt in range(0x0300, 0x0370):           # kombinierende Akzente
        tabelle[codepunkt] = None
    for zeichen in _UNSICHTBAR:
        tabelle[ord(zeichen)] = None
    for zeichen in _APOSTROPHE:
        tabelle[ord(zeichen)] = "'"
    for zeichen in _STRICHE:
        tabelle[ord(zeichen)] = "-"
    tabelle[0x00A0] = " "
    return tabelle


_FALTUNG = _baue_faltung(deutsch=False)
_FALTUNG_DE = _baue_faltung(deutsch=True)


@functools.lru_cache(maxsize=131072)
def normalisieren(wort: str) -> str:
    """Vergleichsform: casefold, ß → ss, Diakritika entfernt, Leerraum vereinfacht.
    "Çelik" → "celik", "STRAUSS" und "Strauß" → "strauss", "Łukasz" → "lukasz"."""
    return " ".join(wort.translate(_FALTUNG).lower().split())


@functools.lru_cache(maxsize=65536)
def normalisieren_umschrift(wort: str) -> str:
    """Wie normalisieren, aber mit deutscher Umschrift (ä → ae, ö → oe, ü → ue, ø → oe,
    å → aa): "Müller" → "mueller". Wird zusätzlich zu normalisieren verwendet."""
    return " ".join(wort.translate(_FALTUNG_DE).lower().split())


def sortierschluessel(eintrag: str) -> tuple[str, str]:
    """Sortierung der Listendateien: nach Vergleichsform, bei Gleichstand nach Schreibweise."""
    return normalisieren(eintrag), eintrag


# ----------------------------------------------------------------------
# Wortfolgen und Trenner
# ----------------------------------------------------------------------
# Wort = Buchstaben/Ziffern; kombinierende Akzente, weiche Trennstriche und
# Null-Breiten-Zeichen gehören zum Wort (beim Normalisieren entfernt).
_TOKEN_RE = re.compile(r"[^\W_](?:[^\W_]|[̀-ͯ­​-‍⁠])*")
_WEICHE_TRENNER = str.maketrans({**{z: None for z in " \t\r\n\f\v    -."},
                                 **{z: None for z in _STRICHE + _UNSICHTBAR},
                                 **{z: "'" for z in _APOSTROPHE}})
_UMBRUCH_RE = re.compile(r"[\n\r\f\v  ]")


def _trenner(roh: str) -> str:
    """Vergleichsform des Trenners zwischen zwei Wörtern: Leerraum, Bindestriche und Punkte
    entfallen ("" = weicher Trenner), andere Zeichen bleiben ("+", "&", "/", "'")."""
    return roh.translate(_WEICHE_TRENNER) if roh else ""


def woerter(text: str) -> list[str]:
    """Die Wörter (Buchstaben-/Ziffernfolgen) eines Textes in Originalschreibweise."""
    return [m.group(0) for m in _TOKEN_RE.finditer(text)]


class _Muster(NamedTuple):
    woerter: tuple[str, ...]        # normalisierte Wörter
    trenner: tuple[str, ...]        # Vergleichsform der Trenner (eins weniger als Wörter)
    eintrag: str                    # Originaleintrag der Liste
    vorsatz: str                    # Zeichen vor dem ersten Wort ("(" in "(FH)")
    nachsatz: str                   # Zeichen nach dem letzten Wort ("." in "Nr.")


class Vorkommen(NamedTuple):
    """Fundstelle im Text: Zeichenbereich [start, ende), Originaltext, passender Eintrag."""
    start: int
    ende: int
    text: str
    eintrag: str


def _zerlegen(eintrag: str, falte) -> _Muster | None:
    treffer = list(_TOKEN_RE.finditer(eintrag))
    if not treffer:
        return None
    woerter_ = tuple(falte(m.group(0)) for m in treffer)
    trenner = tuple(_trenner(eintrag[a.end():b.start()]) for a, b in zip(treffer, treffer[1:]))
    vorsatz = eintrag[:treffer[0].start()].strip()
    nachsatz = eintrag[treffer[-1].end():].strip()
    return _Muster(woerter_, trenner, eintrag, vorsatz, nachsatz)


def _schluessel(woerter_: tuple[str, ...], trenner: tuple[str, ...]) -> str:
    """Vergleichsschlüssel einer ganzen Wortfolge ("kfz haftpflicht", "r+v")."""
    teile = [woerter_[0]]
    for t, w in zip(trenner, woerter_[1:]):
        teile.append(t or " ")
        teile.append(w)
    return "".join(teile)


class Phrasenindex:
    """Suchindex über eine Liste von Wörtern und Wortfolgen.

    Der Aufbau geschieht einmal (einige Millisekunden je tausend Einträge). Die Suche ist
    linear in der Textlänge: der Text wird in Wörter zerlegt, jedes Wort normalisiert
    (zwischengespeichert) und über ein Wörterbuch der Anfangswörter nachgeschlagen;
    nur dort werden mehrteilige Einträge Wort für Wort verglichen.
    """

    def __init__(self, eintraege: Iterable[str], name: str = ""):
        self.name = name
        self._anfang: dict[str, list[_Muster]] = {}
        self._ganz: dict[str, str] = {}
        self.max_woerter = 0
        gesehen = set()
        for eintrag in eintraege:
            for falte in (normalisieren, normalisieren_umschrift):
                muster = _zerlegen(eintrag, falte)
                if muster is None:
                    continue
                kennung = (muster.woerter, muster.trenner, muster.vorsatz, muster.nachsatz)
                self._ganz.setdefault(_schluessel(muster.woerter, muster.trenner), eintrag)
                if kennung in gesehen:
                    continue                      # Umschrift gleich oder schon vorhanden
                gesehen.add(kennung)
                self._anfang.setdefault(muster.woerter[0], []).append(muster)
                self.max_woerter = max(self.max_woerter, len(muster.woerter))
        for kandidaten in self._anfang.values():
            kandidaten.sort(key=lambda m: (-len(m.woerter), -len(m.nachsatz), -len(m.vorsatz)))

    def __len__(self) -> int:
        return len(self._ganz)

    def __contains__(self, phrase: object) -> bool:
        return isinstance(phrase, str) and self.eintrag_fuer(phrase) is not None

    def eintrag_fuer(self, phrase: str) -> str | None:
        """Listeneintrag, der der GANZEN Phrase entspricht (normalisiert), sonst None."""
        for falte in (normalisieren, normalisieren_umschrift):
            muster = _zerlegen(phrase, falte)
            if muster is None:
                return None
            eintrag = self._ganz.get(_schluessel(muster.woerter, muster.trenner))
            if eintrag is not None:
                return eintrag
        return None

    def finde(self, text: str, *, zeilenuebergreifend: bool = False,
              nur_gross: bool = False) -> list[Vorkommen]:
        """Alle nicht überlappenden Vorkommen, von links, längster Eintrag zuerst.
        nur_gross: nur Treffer, deren erstes Wort mit einem Großbuchstaben beginnt
        (für Namenslisten: "klein" ist kein Nachname, "Klein" vielleicht)."""
        if not text or not self._anfang:
            return []
        gefunden = [(m.start(), m.end(), m.group(0)) for m in _TOKEN_RE.finditer(text)]
        schluessel = [normalisieren(w[2]) for w in gefunden]
        anfang = self._anfang
        ergebnis: list[Vorkommen] = []
        i, anzahl = 0, len(gefunden)
        while i < anzahl:
            kandidaten = anfang.get(schluessel[i])
            if not kandidaten or (nur_gross and not gefunden[i][2][0].isupper()):
                i += 1
                continue
            for muster in kandidaten:
                laenge = len(muster.woerter)
                if i + laenge > anzahl:
                    continue
                passt = True
                for j in range(1, laenge):
                    if schluessel[i + j] != muster.woerter[j]:
                        passt = False
                        break
                    zwischen = text[gefunden[i + j - 1][1]:gefunden[i + j][0]]
                    if (not zeilenuebergreifend and _UMBRUCH_RE.search(zwischen)) \
                            or _trenner(zwischen) != muster.trenner[j - 1]:
                        passt = False
                        break
                if not passt:
                    continue
                start, ende = gefunden[i][0], gefunden[i + laenge - 1][1]
                if muster.nachsatz and text.startswith(muster.nachsatz, ende):
                    ende += len(muster.nachsatz)
                if muster.vorsatz and start >= len(muster.vorsatz) \
                        and text.startswith(muster.vorsatz, start - len(muster.vorsatz)):
                    start -= len(muster.vorsatz)
                ergebnis.append(Vorkommen(start, ende, text[start:ende], muster.eintrag))
                i += laenge
                break
            else:
                i += 1
        return ergebnis

    def laengster(self, phrase: str) -> str | None:
        """Längster Listeneintrag, der als ganze Wortfolge in der Phrase vorkommt."""
        treffer = self.finde(phrase, zeilenuebergreifend=True)
        if not treffer:
            return None
        return max(treffer, key=lambda t: (t.ende - t.start, -t.start)).eintrag

    def deckt_ab(self, phrase: str) -> bool:
        """True, wenn jedes Wort der Phrase zu einem Treffer gehört (die Phrase also
        vollständig aus Listeneinträgen besteht)."""
        teile = list(_TOKEN_RE.finditer(phrase))
        if not teile:
            return False
        treffer = self.finde(phrase, zeilenuebergreifend=True)
        return all(any(t.start <= w.start() and w.end() <= t.ende for t in treffer) for w in teile)


@functools.lru_cache(maxsize=None)
def _index(name: str) -> Phrasenindex:
    return Phrasenindex(_liste(name), name=name)


def index(name: str) -> Phrasenindex:
    """Suchindex einer Wortliste (einmalig aufgebaut, danach zwischengespeichert)."""
    return _index(_listenname(name))


def finde(text: str, name: str, *, zeilenuebergreifend: bool = False,
          nur_gross: bool = False) -> list[Vorkommen]:
    """Alle Vorkommen der Einträge einer Wortliste im Text (siehe Phrasenindex.finde)."""
    return index(name).finde(text, zeilenuebergreifend=zeilenuebergreifend, nur_gross=nur_gross)


@functools.lru_cache(maxsize=None)
def _menge(name: str) -> frozenset[str]:
    return frozenset(_index(name)._ganz)


def menge(name: str) -> frozenset[str]:
    """Vergleichsformen aller Einträge einer Liste (normalisiert und in Umschrift;
    mehrteilige Einträge mit einfachem Leerzeichen bzw. hartem Trenner: "r+v")."""
    return _menge(_listenname(name))


# ----------------------------------------------------------------------
# Einzelwort-Prüfungen
# ----------------------------------------------------------------------
def _im_index(name: str, wort: str) -> bool:
    return bool(wort) and _index(name).eintrag_fuer(wort) is not None


@functools.lru_cache(maxsize=None)
def _partikel_folgen() -> tuple[tuple[str, ...], ...]:
    """Namenspartikel als Wortfolgen, längste zuerst (("von", "und", "zu"), ("von",) …)."""
    folgen = set()
    for eintrag in _liste("partikel"):
        muster = _zerlegen(eintrag, normalisieren)
        if muster is not None:
            folgen.add(muster.woerter)
    return tuple(sorted(folgen, key=lambda f: (-len(f), f)))


def _ohne_partikel(teile: list[str]) -> list[str]:
    """Führende Namenspartikel entfernen (["von", "der", "leyen"] -> ["leyen"]);
    das letzte Wort bleibt immer stehen."""
    geaendert = True
    while geaendert and len(teile) > 1:
        geaendert = False
        for folge in _partikel_folgen():
            if len(folge) < len(teile) and tuple(teile[:len(folge)]) == folge:
                teile = teile[len(folge):]
                geaendert = True
                break
    return teile


def ist_vorname(wort: str) -> bool:
    """Vorname? Auch Doppelnamen, deren Teile alle Vornamen sind ("Lisa-Marie")."""
    if _im_index("vornamen", wort):
        return True
    teile = woerter(wort)
    return len(teile) > 1 and all(_im_index("vornamen", t) for t in teile)


def _partikel_kern(eintrag: str) -> str | None:
    """Kern eines Namens mit führendem Partikel in Originalschreibweise ("van der Meer" ->
    "Meer", "Al-Hassan" -> "Hassan"), sonst None. Die Liste nachnamen führt solche Kerne
    zusätzlich als eigene Einträge ("Vries" für die Listenform "Vries, Jan de"), außer sie
    sind Vornamen oder Allerweltswörter; das prüft werkzeuge/wissen_pflegen.py."""
    teile = woerter(eintrag)
    kern = _ohne_partikel([normalisieren(t) for t in teile])
    if len(kern) == len(teile):
        return None
    return " ".join(teile[len(teile) - len(kern):])


def ist_nachname(wort: str) -> bool:
    """Nachname? Führende Partikel zählen nicht ("von Weizsäcker", "al-Hassan"); bei
    Doppelnamen müssen alle Teile Nachnamen sein ("Müller-Lüdenscheidt" nur, wenn beide
    Teile bekannt sind)."""
    if _im_index("nachnamen", wort):
        return True
    teile = woerter(wort)
    if not teile:
        return False
    kern = _ohne_partikel([normalisieren(t) for t in teile])
    originale = teile[len(teile) - len(kern):]
    if len(kern) < len(teile) and _im_index("nachnamen", " ".join(originale)):
        return True
    return len(originale) > 1 and all(_im_index("nachnamen", t) for t in originale)


def ist_mehrdeutig(wort: str) -> bool:
    """Nachname, der zugleich ein gewöhnliches Wort, ein Orts- oder Firmenname ist (Klein,
    Wolf, Koch, Winter, Hagen, Nürnberger …): Regeln sollen dafür Kontext verlangen
    (Herr/Frau, Vorname davor, Rollen-Etikett)."""
    return _im_index("nachnamen_mehrdeutig", wort)


def ist_vorname_mehrdeutig(wort: str) -> bool:
    """Vorname, der zugleich ein gewöhnliches Wort ist (Rosa, Ernst, Frank, Mai, Kai, An,
    Nur, Mercedes …): auch hier Kontext verlangen (Nachname dahinter, Anrede, Etikett)."""
    return _im_index("vornamen_mehrdeutig", wort)


def ist_partikel(wort: str) -> bool:
    """Namenspartikel (von, van der, de la, al-, bin, ibn, Freiherr von …)?"""
    return _im_index("partikel", wort)


def ist_anrede_titel(wort: str) -> bool:
    """Anrede, Titel oder Rollen-Kürzel (Herr, Frau, Dr. med., Prof., Dipl.-Ing., i. A. …)?"""
    return _im_index("anreden_titel", wort)


_ENDUNGEN = ("nen", "en", "es", "n", "s", "e")


def ist_allerweltswort(wort: str) -> bool:
    """Gewöhnliches großgeschriebenes Wort aus Formularen und Briefen (Schadenanzeige,
    Familientarif …), das kein Name ist. Einfache Beugungsendungen werden versuchsweise
    abgestreift ("Versicherungsnehmers", "Leistungen")."""
    if _im_index("allerweltswoerter_gross", wort):
        return True
    wort = wort.strip()
    if len(wort) < 6 or len(woerter(wort)) != 1:
        return False
    klein = wort.lower()
    return any(klein.endswith(endung) and len(wort) - len(endung) >= 5
               and _im_index("allerweltswoerter_gross", wort[:-len(endung)])
               for endung in _ENDUNGEN)


# ----------------------------------------------------------------------
# Phrasen-Prüfungen
# ----------------------------------------------------------------------
def ist_beruf(phrase: str) -> str | None:
    """Längster Berufseintrag in der Phrase ("Beruf: Zahnärztin (angestellt)" ->
    "Zahnärztin", "Kauffrau für Versicherungen und Finanzen" -> ganzer Eintrag), sonst None.
    Achtung: viele Berufe sind zugleich Familiennamen (Koch, Bauer, Richter, Meister …);
    diese stehen in nachnamen_mehrdeutig. ist_beruf eignet sich daher nicht, um einen
    Namen auszuschließen – nur, um eine Berufsangabe zu erkennen."""
    return index("berufe").laengster(phrase)


def ist_diagnose(phrase: str) -> str | None:
    """Längster Diagnose-Eintrag in der Phrase ("V. a. Diabetes mellitus Typ 2" ->
    "Diabetes mellitus Typ 2"), sonst None."""
    return index("diagnosen").laengster(phrase)


def ist_medikament(phrase: str) -> str | None:
    """Längster Medikamenten-Eintrag in der Phrase ("Ibuprofen 600 mg" -> "Ibuprofen")."""
    return index("medikamente").laengster(phrase)


def ist_allowlist(phrase: str) -> bool:
    """True, wenn die Phrase vollständig aus Einträgen der Liste
    versicherer_und_organisationen besteht ("HUK-COBURG", "Deutsche Rentenversicherung
    Bund", "Allianz Lebensversicherungs-AG", "Riester-Rente"). Achtung: einzelne Wörter
    dieser Liste können auch Nachnamen sein (Nürnberger, Basler) – sie stehen dann
    zusätzlich in nachnamen_mehrdeutig; mit Kontext (Herr/Frau) bleibt es ein Name."""
    return index("versicherer_und_organisationen").deckt_ab(phrase)


@functools.lru_cache(maxsize=None)
def etiketten(art: str) -> tuple[str, ...]:
    """Etiketten (Feldbezeichner) einer Art, nach Länge absteigend, bei gleicher Länge
    alphabetisch. Arten: person, kennung, datum_geburt, adresse, kontakt, vertragsdaten."""
    name = art if art.startswith("etiketten_") else f"etiketten_{art}"
    if name not in LISTEN:
        raise KeyError(f"Unbekannte Etiketten-Art: {art!r} (bekannt: {', '.join(ETIKETTEN_ARTEN)})")
    return tuple(sorted(_liste(name), key=lambda e: (-len(e), sortierschluessel(e))))
