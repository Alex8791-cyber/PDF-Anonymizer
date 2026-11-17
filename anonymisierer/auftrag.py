"""Schwärz-Auftrag der Oberfläche: welche Funde und Stellen an die Schwärzung gehen, mit welchen Parametern, und wie
die Oberfläche den Status der Ausgabe liest.

Reine Funktionen ohne tkinter. Die Oberfläche (gui.py) baut ihre Aufträge damit; der Entwicklungs-Benchmark
(werkzeuge/benchmark.py --weg oberflaeche) baut damit genau den Auftrag, den die Oberfläche ohne Eingriff der Nutzerin
abschickt: Einstellungen wie beim ersten Start (Schutzstufe „Hoch“, NIE-/IMMER-Liste leer, keine Kundenliste,
„Freigabe vor Weitergabe“ an), Häkchen so, wie die Fundliste sie nach der Analyse setzt.

Befund (Runde 3b): Der Benchmark gab bisher jeden Fund der Analyse unverändert an die Schwärzung („alle Funde
angehakt“), ohne Seitenmodell, Nebenkanäle und Freigabe. Die Oberfläche lässt ganz abgewählte Funde weg (z. B. die in
„Hoch“ nur angebotenen Gesundheitsdaten – die Restrisiko-Prüfung und die Selbstkontrolle erfahren dann nicht, dass
sie bewusst stehen bleiben), gibt abgewählte Bildfunde mit allen Bereichen abgewählt mit (ein abgewähltes Lichtbild
verlangt die Freigabe) und reicht Seitenmodell und Nebenkanäle der Analyse weiter (deren leckrelevante Meldungen
machen die Ausgabe _PRUEFEN). Damit die Schlussmessung zeigt, was die Nutzerin mit den Standards bekommt, steht diese
Auswahl nur hier und wird im Benchmark nicht nachgebaut.

Zustand eines Funds in der Fundliste: „an“ | „aus“ | „teil“ – mit Einzelstellen (die Analyse lieferte ein
Seitenmodell, die Schwärzung nimmt es an) aus den Stellen abgeleitet ("an" fehlt = angehakt), sonst das Häkchen
seiner Zeile (nach der Analyse „an“).
"""

from __future__ import annotations

import inspect
from pathlib import Path

from . import gui_attrappen as _attrappen
from . import muster as _muster

# Einstellungen der Oberfläche beim ersten Start (keine gespeicherten Einstellungen)
STANDARD_PROFIL = _attrappen.STANDARD_PROFIL         # Schutzstufe „Hoch“
STANDARD_FREIGABE = True                             # „Freigabe vor Weitergabe“ (Vertrag Abschnitt 10)
# Schutzstufen der Engine (muster.PROFILE), sonst aus den Kategorien abgeleitet (Attrappe)
PROFILE = getattr(_muster, "PROFILE", None) or _attrappen.PROFILE
# Grund der Engine („pruefen_gruende“), wenn eine Ausgabe nur wegen „Freigabe vor Weitergabe“ _PRUEFEN heißt
FREIGABE_AUSSTEHEND = "Freigabe ausstehend"


# ----------------------------------------------------------------------
# Kennt die Engine einen Parameter?
# ----------------------------------------------------------------------
def _parameter(funktion) -> set | None:
    """Parameternamen einer Engine-Funktion; None, wenn sie beliebige Schlüsselwörter annimmt."""
    try:
        parameter = inspect.signature(funktion).parameters
    except (TypeError, ValueError):
        return None
    if any(p.kind is p.VAR_KEYWORD for p in parameter.values()):
        return None
    return set(parameter)


def kann(funktion, name: str) -> bool:
    """Kennt die Engine-Funktion den (neuen, optionalen) Parameter? Pflichtparameter aus Phase 1 werden
    immer direkt übergeben – ein umbenannter Parameter führt zu einem sichtbaren Fehler, nie zu Stille."""
    parameter = _parameter(funktion)
    return parameter is None or name in parameter


# ----------------------------------------------------------------------
# Einstellungen
# ----------------------------------------------------------------------
def stufe_kategorien(profile, name: str, alle) -> set[str] | None:
    """Aktive Kategorien der Schutzstufe `name` – die Häkchen, die die Oberfläche für diese Stufe setzt (profile wie
    muster.PROFILE; nennt es die Stufe nicht, gilt die Attrappe). None, wenn keine der beiden die Stufe kennt."""
    menge = _attrappen.profil_kategorien(profile, name, alle)
    if menge is None:
        menge = _attrappen.profil_kategorien(_attrappen.PROFILE, name, alle)
    return menge


def standard_kategorien(kategorien=None, profile=None) -> set[str]:
    """Aktive Kategorien beim ersten Start: die der Schutzstufe STANDARD_PROFIL, sonst die standardmäßig angehakten
    (kategorien: Einträge wie muster.KATEGORIEN; profile: Standard PROFILE)."""
    kategorien = _muster.KATEGORIEN if kategorien is None else kategorien
    alle = {eintrag[0] for eintrag in kategorien}
    menge = stufe_kategorien(PROFILE if profile is None else profile, STANDARD_PROFIL, alle)
    if menge is None:
        return {eintrag[0] for eintrag in kategorien if len(eintrag) < 5 or eintrag[4]}
    return set(menge)


# ----------------------------------------------------------------------
# Häkchen der Fundliste
# ----------------------------------------------------------------------
def ist_bildfund(fund: dict) -> bool:
    """Bildfund (Lichtbild, Bild, Foto): Stellen sind Bereiche im Bild statt Textstellen."""
    return any("bereich" in st for st in fund.get("stellen") or ())


def einzelstellen_moeglich(ergebnis: dict | None, schwaerze_pdf) -> bool:
    """Kann die Engine einzelne Fundstellen schwärzen? (Analyse lieferte ein Seitenmodell, die Schwärzung
    nimmt es an – Vertrag Abschnitt 5). Sonst gilt ein Fund immer an allen seinen Stellen."""
    return bool(ergebnis) and ergebnis.get("modell") is not None and kann(schwaerze_pdf, "modell")


def hat_einzelstellen(fund: dict, einzelstellen: bool) -> bool:
    """Gelten für den Fund seine Einzelstellen? (Liste mit mindestens einer Stelle und einzelstellen_moeglich)"""
    return bool(einzelstellen) and isinstance(fund.get("stellen"), list) and bool(fund["stellen"])


def zustand_aus_stellen(stellen: list) -> str:
    """an | aus | teil aus den Stellen eines Funds ("an" fehlt = angehakt)."""
    an = sum(1 for s in stellen if s.get("an", True))
    return "an" if an == len(stellen) else ("aus" if an == 0 else "teil")


def standard_zustand(fund: dict, einzelstellen: bool) -> str:
    """Häkchen eines Funds direkt nach der Analyse (Fundliste ohne Eingriff der Nutzerin): mit Einzelstellen aus den
    Stellen abgeleitet – nur angebotene Funde (z. B. Gesundheitsdaten in „Hoch“) stehen dann „aus“ –, sonst „an“."""
    return zustand_aus_stellen(fund["stellen"]) if hat_einzelstellen(fund, einzelstellen) else "an"


# ----------------------------------------------------------------------
# Auftrag und Parameter der Schwärzung
# ----------------------------------------------------------------------
def auftrag_funde(funde: list, zustaende: list, einzelstellen: bool) -> tuple[list, list]:
    """Funde für schwaerze_pdf aus den Häkchen (zustaende[i] = an | aus | teil des Funds i):
    (angehakte und teilweise angehakte Funde, abgewählte Bildfunde). Ein ganz abgewählter Fund bleibt weg – außer einem
    Bildfund: er geht mit allen Bereichen abgewählt mit (ein abgewähltes Lichtbild verlangt die Freigabe), auch ohne
    Einzelstellen. Mit Einzelstellen bestimmen die Stellen, was geschwärzt wird. Nur Kopien – das Analyseergebnis
    bleibt unverändert."""
    angehakt, abgewaehlte_bilder = [], []
    for fund, zustand in zip(funde, zustaende, strict=True):
        if zustand == "aus" and not ist_bildfund(fund):
            continue
        kopie = dict(fund)
        if zustand == "aus":            # abgewählt: alle Bereiche bleiben stehen (auch ohne Einzelstellen)
            kopie["stellen"] = [dict(s, an=False) for s in fund.get("stellen") or ()]
            abgewaehlte_bilder.append(kopie)
            continue
        if hat_einzelstellen(fund, einzelstellen):
            kopie["stellen"] = [dict(s) for s in fund["stellen"]]
        angehakt.append(kopie)
    return angehakt, abgewaehlte_bilder


def auftrag_bauen(ergebnis: dict, zustaende: list, einzelstellen: bool, bereiche: dict | None = None,
                  stellen: dict | None = None) -> dict:
    """Schwärz-Auftrag einer fehlerfrei analysierten Datei (ohne Pfade – Datei, Arbeitskopie und Zielordner setzt
    die Oberfläche): funde (angehakte, dahinter abgewählte Bildfunde), ocr_cache, modell (nur mit Einzelstellen),
    bereiche/stellen (manuelle Markierungen der Vorschau), nebenkanaele, ohne_haken (nichts angehakt: die Ausgabe
    ist nur bereinigt) und gefunden (die Analyse fand überhaupt etwas)."""
    angehakt, abgewaehlte_bilder = auftrag_funde(ergebnis["funde"], zustaende, einzelstellen)
    bereiche = bereiche if bereiche is not None else {}
    stellen = stellen if stellen is not None else {}
    nebenkanaele = ergebnis.get("nebenkanaele")
    return {"funde": angehakt + abgewaehlte_bilder,      # abgewählte Bilder gehen mit, zählen aber nicht als Haken
            "ocr_cache": ergebnis.get("ocr_cache"),
            "modell": ergebnis.get("modell") if einzelstellen else None,
            "bereiche": bereiche, "stellen": stellen,
            "nebenkanaele": nebenkanaele if isinstance(nebenkanaele, dict) else None,
            "ohne_haken": not angehakt and not bereiche and not stellen,
            "gefunden": bool(ergebnis.get("funde"))}


def standard_auftrag(ergebnis: dict, schwaerze_pdf) -> tuple[dict, list]:
    """(Auftrag, Häkchen je Fund), wie die Oberfläche ihn für ein Analyseergebnis ohne Eingriff der Nutzerin abschickt:
    Häkchen der Fundliste nach der Analyse (standard_zustand, wie gui._baum_datei_fuellen), keine Markierungen aus der
    Vorschau, daraus der Auftrag (auftrag_bauen, wie gui._auftrag). schwaerze_pdf: die Schwärzung, die ihn bekommt."""
    einzelstellen = einzelstellen_moeglich(ergebnis, schwaerze_pdf)
    zustaende = [standard_zustand(f, einzelstellen) for f in ergebnis["funde"]]
    return auftrag_bauen(ergebnis, zustaende, einzelstellen), zustaende


def freigabe_noetig(auftrag: dict, freigabe: bool) -> bool:
    """Bleibt die Ausgabe bis zur Freigabe in der Vorschau _PRUEFEN? Mit „Freigabe vor Weitergabe“ – und bei Fotos
    immer: Gesicht, Unterschrift und Handschrift bleiben stehen (Befund Runde 2)."""
    return bool(freigabe or auftrag.get("foto"))


def schwaerz_parameter(auftrag: dict, freigabe: bool, profil: str, schwaerze_pdf) -> dict:
    """Schlüsselwort-Parameter für schwaerze_pdf(datei, auftrag["funde"], …) – ohne melde, fortschritt, abbruch, ocr
    und ziel_ordner (Sache des Aufrufers). Neue Parameter nur, wenn die Engine sie kennt."""
    kwargs = {"ocr_cache": auftrag["ocr_cache"]}
    if auftrag.get("nebenkanaele") is not None and kann(schwaerze_pdf, "nebenkanaele"):
        kwargs["nebenkanaele"] = auftrag["nebenkanaele"]
    if auftrag["modell"] is not None:
        kwargs["modell"] = auftrag["modell"]
    if auftrag["bereiche"]:
        kwargs["manuelle_bereiche"] = auftrag["bereiche"]
    if auftrag["stellen"]:
        kwargs["manuelle_stellen"] = auftrag["stellen"]
    if kann(schwaerze_pdf, "freigabe_erforderlich"):
        kwargs["freigabe_erforderlich"] = freigabe_noetig(auftrag, freigabe)
    if kann(schwaerze_pdf, "profil"):
        kwargs["profil"] = profil
    return kwargs


# ----------------------------------------------------------------------
# Status der Ausgabe, wie die Oberfläche ihn zeigt
# ----------------------------------------------------------------------
def ausgabe_status(ergebnis: dict) -> str:
    """fertig | pruefen | fehler | keine – die Engine meldet „status“ (Vertrag 5), sonst aus dem Namen."""
    ausgabe = ergebnis.get("ausgabe")
    if ergebnis["fehler"]:
        return "fehler"
    if ausgabe is None:
        return "keine"
    status = ergebnis.get("status")
    if "_PRUEFEN" in Path(ausgabe).name.upper() or ergebnis.get("reste") or ergebnis.get("verdacht") \
            or int(ergebnis.get("stellen_nicht_lokalisiert") or 0):
        return "pruefen"                           # im Zweifel prüfen, auch wenn „status“ anderes sagt
    return status if status in ("fertig", "pruefen") else "fertig"


def nur_freigabe_offen(ergebnis: dict, status: str) -> bool:
    """„fertig“, oder _PRUEFEN allein wegen „Freigabe vor Weitergabe“ – kein Grund der Engine, kein Verdacht."""
    if status == "fertig":
        return True
    return (status == "pruefen" and not ergebnis.get("verdacht") and not ergebnis.get("reste")
            and not int(ergebnis.get("stellen_nicht_lokalisiert") or 0)
            and all(str(g) == FREIGABE_AUSSTEHEND for g in ergebnis.get("pruefen_gruende") or ()))
