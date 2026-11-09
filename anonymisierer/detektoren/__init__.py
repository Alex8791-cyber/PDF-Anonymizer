"""Detektor-Register: jede Erkennungsregel ist eine Funktion f(dok, kontext) -> list[Treffer].

Ein Detektor wird mit dem Dekorator @detektor(name, kategorien, profile) registriert. Alle Module dieses
Pakets werden beim Import automatisch geladen (pkgutil.iter_modules) – neue Detektoren brauchen KEINE
Änderung an dieser Datei. Register-Namen sind eindeutig; ein späteres Modul darf einen Namen mit
ersetzt=True überschreiben (Module werden alphabetisch geladen).

    Treffer(start, ende, kategorie, quelle, sicherheit, gruppe)   Offsets im Dokument.text (global)
    Kontext(aktive, profil, nie, immer, wissen, kundenliste, lauf)
    alle_treffer(dok, kontext) -> list[Treffer]                    führt alle passenden Detektoren aus

Ladefehler eines Moduls und Ausnahmen eines Detektors werden gesammelt (LADEFEHLER bzw. fehler-Liste)
und von der Analyse als Warnung gemeldet – eine kaputte Regel legt nicht die ganze Analyse lahm, wird
aber auch nicht verschwiegen.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Callable, NamedTuple

ALLE_PROFILE = frozenset({"ausgewogen", "hoch", "maximal"})
IMMER_AKTIV = frozenset({"begriff"})        # Kategorien, die unabhängig von den Häkchen laufen


class Treffer(NamedTuple):
    """Ausgabe eines Detektors (Offsets im Dokument.text)."""
    start: int
    ende: int
    kategorie: str                  # Schlüssel aus KATEGORIEN, "namen" oder "begriff"
    quelle: str                     # z. B. "muster.iban", "ner", "immer"
    sicherheit: float = 0.5         # 0..1 (1 = Prüfziffer/Kundenliste, 0.5 = Heuristik)
    gruppe: str | None = None       # Personenschlüssel/Vollname (für Pseudonyme) oder None


class Kontext:
    """Alles, was ein Detektor wissen darf."""

    def __init__(self, aktive=(), profil: str = "hoch", nie=(), immer=(), wissen=None, kundenliste=None,
                 lauf=None):
        self.aktive = set(aktive or ())
        self.profil = profil or "hoch"
        self.nie = list(nie or [])
        self.immer = list(immer or [])
        self.wissen = wissen
        self.kundenliste = kundenliste
        self.lauf = lauf

    def __repr__(self):
        return f"<Kontext profil={self.profil} aktive={sorted(self.aktive)}>"


class Eintrag(NamedTuple):
    name: str
    kategorien: frozenset
    profile: frozenset
    funktion: Callable


REGISTER: list = []                 # [Eintrag(name, kategorien, profile, funktion), ...]
LADEFEHLER: list = []               # Texte zu Modulen, die nicht geladen werden konnten


def registrieren(name: str, kategorien, profile=ALLE_PROFILE, funktion=None, ersetzt: bool = False,
                 nur_wenn_frei: bool = False) -> Eintrag:
    """Trägt einen Detektor ein. Doppelte Namen nur mit ersetzt=True (dann an derselben Stelle).
    nur_wenn_frei=True (Rückfall-Detektoren wie klassisch.py): ist der Name schon vergeben, bleibt der
    vorhandene Detektor – so ist die Ladereihenfolge der Module egal."""
    if funktion is None or not callable(funktion):
        raise TypeError(f"Detektor {name!r}: Funktion fehlt")
    eintrag = Eintrag(name, frozenset(kategorien), frozenset(profile or ALLE_PROFILE), funktion)
    for i, alt in enumerate(REGISTER):
        if alt.name == name:
            if nur_wenn_frei and not ersetzt:
                return alt
            if not ersetzt:
                raise ValueError(f"Detektor {name!r} ist schon registriert (ersetzt=True zum Überschreiben)")
            REGISTER[i] = eintrag
            return eintrag
    REGISTER.append(eintrag)
    return eintrag


def detektor(name: str, kategorien, profile=ALLE_PROFILE, ersetzt: bool = False, nur_wenn_frei: bool = False):
    """Dekorator: registriert f(dok: Dokument, kontext: Kontext) -> list[Treffer]."""
    def dekorieren(funktion):
        registrieren(name, kategorien, profile, funktion, ersetzt=ersetzt, nur_wenn_frei=nur_wenn_frei)
        return funktion
    return dekorieren


def entfernen(name: str) -> bool:
    for i, alt in enumerate(REGISTER):
        if alt.name == name:
            del REGISTER[i]
            return True
    return False


def detektoren_fuer(kontext: Kontext) -> list:
    """Detektoren, die zum Profil passen und mindestens eine aktive Kategorie liefern."""
    aktiv = set(kontext.aktive) | IMMER_AKTIV
    return [e for e in REGISTER if kontext.profil in e.profile and e.kategorien & aktiv]


def alle_treffer(dok, kontext: Kontext, fehler: list | None = None) -> list:
    """Führt alle passenden Detektoren aus. Treffer werden geprüft (gültige Offsets, aktive Kategorie)
    und an den Rändern von Leerraum befreit. Ausnahmen eines Detektors landen in `fehler`."""
    aktiv = set(kontext.aktive) | IMMER_AKTIV
    laenge = len(dok.text)
    ergebnis = []
    for eintrag in detektoren_fuer(kontext):
        try:
            treffer = eintrag.funktion(dok, kontext) or []
        except Exception as e:  # eine kaputte Regel darf die übrigen nicht verhindern
            if fehler is not None:
                fehler.append(f"Erkennungsregel »{eintrag.name}« ist ausgefallen ({type(e).__name__}: {e})")
            continue
        for t in treffer:
            if not isinstance(t, Treffer):
                t = Treffer(*t)
            if t.kategorie not in aktiv:
                continue
            s, e = max(0, int(t.start)), min(laenge, int(t.ende))
            while s < e and dok.text[s].isspace():
                s += 1
            while e > s and dok.text[e - 1].isspace():
                e -= 1
            if e <= s:
                continue
            if (s, e) != (t.start, t.ende):
                t = t._replace(start=s, ende=e)
            ergebnis.append(t)
    return ergebnis


# ----------------------------------------------------------------------
# Automatisches Laden aller Module des Pakets
# ----------------------------------------------------------------------
_BEKANNTE_MODULE = ("klassisch",)   # Rückfall, falls iter_modules (z. B. in einer EXE) nichts liefert


def _automatisch_laden():
    namen = [m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_")]
    for name in _BEKANNTE_MODULE:
        if name not in namen:
            namen.append(name)
    for name in sorted(namen):
        try:
            importlib.import_module(f"{__name__}.{name}")
        except ModuleNotFoundError as e:
            if e.name != f"{__name__}.{name}":
                LADEFEHLER.append(f"Erkennungsmodul »{name}« konnte nicht geladen werden: {e}")
        except Exception as e:
            LADEFEHLER.append(f"Erkennungsmodul »{name}« konnte nicht geladen werden: {type(e).__name__}: {e}")


_automatisch_laden()

try:  # statischer Verweis, damit PyInstaller das Modul sicher mitnimmt (Laden geschah schon oben)
    from . import klassisch as _klassisch  # noqa: F401,E402
except Exception:  # pragma: no cover - Modul wurde entfernt/ersetzt
    _klassisch = None
