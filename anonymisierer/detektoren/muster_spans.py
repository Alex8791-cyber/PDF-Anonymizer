"""Muster-Detektoren, die STELLEN liefern (Vertrag Abschnitt 3: "muster.* … Spans via re.finditer").

Ersetzt die Muster-Einträge von klassisch.py (gleiche Register-Namen, ersetzt=True): statt Fundtexte im
Dokument wiederzusuchen, liefert jedes Muster seine Stellen direkt (muster.stellen). Unsichere Stellen (z. B.
IBAN mit falscher Prüfziffer – meist ein OCR-Lesefehler) kommen mit geringerer Sicherheit und der Quelle
"muster.<kategorie>.lesefehler" (Hinweis über muster.quellen_hinweis).

Nicht hier: "muster.strasse" und "muster.plzort" (Agent "struktur" registriert sie mit Blockzusammenhang neu
und ruft die Text-Schnittstelle von muster.py) sowie die Wissens-Kategorien (beruf, arbeitgeber, diagnose,
medikament, ort, international: detektoren/wissen_kontext.py).

Tabellen: Die Muster stammen aus der Zeit vor dem Seitenmodell (Tabellenzellen auf eigenen Zeilen) und lassen
Leerraum zwischen Wörtern zu – über einen Spaltentrenner hinweg würden sie Nachbarzellen verschlucken. Deshalb
zählen Stellen im Dokumenttext nur ohne Spaltentrenner, dazu die Stellen der zeilenweisen Lesart (Spaltentrenner
durch zwei Zeilenumbrüche ersetzt – gleiche Länge, also gleiche Offsets).
"""

from __future__ import annotations

from .. import muster
from ..seitenmodell import SPALTENTRENNER, ganzwort_stellen_viele, modus_fuer
from . import ALLE_PROFILE, Treffer, registrieren

# Sicherheit je Kategorie (1 = Prüfziffer, sonst Heuristik)
SICHERHEIT = {"iban": 1.0, "steuerid": 1.0, "kreditkarte": 1.0, "svnr": 0.9, "email": 0.95, "fin": 0.9,
              "bic": 0.85, "kvnr": 0.9, "kindergeld": 0.85, "steuernr": 0.85, "geburt": 0.8, "telefon": 0.75,
              "strasse": 0.75, "plzort": 0.75, "vertrag": 0.7, "kfz": 0.7, "ausweis": 0.75, "mandat": 0.8,
              "datum": 0.6}
# Kategorien, die andere Module liefern
NICHT_HIER = frozenset({"strasse", "plzort", "beruf", "arbeitgeber", "diagnose", "medikament", "ort",
                        "international"})


def _funktion(schluessel):
    for eintrag in muster.KATEGORIEN:
        if eintrag[0] == schluessel:
            return eintrag[3]
    return None


def zeilenweise(text: str) -> str | None:
    """Text mit jeder Tabellenzelle auf eigener Zeile (Spaltentrenner -> Leerzeichen + Umbruch, längentreu:
    wie früher "eine Zelle je Zeile", die Offsets bleiben gleich)."""
    if SPALTENTRENNER not in text:
        return None
    return text.replace(SPALTENTRENNER, " " * (len(SPALTENTRENNER) - 1) + "\n")


def _stellen_im_dokument(text: str, schluessel: str) -> list:
    """Stellen eines Musters im Dokumenttext: ohne Spaltentrenner in der Stelle, plus zeilenweise Lesart."""
    aus = {}
    for st in muster.stellen(schluessel, text):
        if SPALTENTRENNER not in text[st.start:st.ende]:
            aus.setdefault((st.start, st.ende), st)
    zeilen = zeilenweise(text)
    if zeilen is not None:
        for st in muster.stellen(schluessel, zeilen):
            if SPALTENTRENNER not in text[st.start:st.ende]:
                aus.setdefault((st.start, st.ende), st)
    return [aus[k] for k in sorted(aus)]


def _text_rueckfall(dok, funktion, schluessel: str, quelle: str, sicherheit: float) -> list:
    """Muster ohne Stellen-Schnittstelle (z. B. in Tests ersetzt): Fundtexte an ihren Ganzwort-Vorkommen."""
    roh = [x for x in funktion(dok.text) if x and SPALTENTRENNER not in x]
    zeilen = zeilenweise(dok.text)
    if zeilen is not None:
        roh += list(funktion(zeilen))
    texte = [t for t in dict.fromkeys(x.strip() for x in roh if x and x.strip()) if len(t) >= 2]
    genau = ganzwort_stellen_viele(dok, texte, "begriff")
    fehlend = [t for t in texte if not genau.get(t)]
    modus = modus_fuer(schluessel)
    if fehlend and modus != "begriff":
        genau.update(ganzwort_stellen_viele(dok, fehlend, modus))
    return [Treffer(s, e, schluessel, quelle, sicherheit) for stellen in genau.values() for s, e in stellen]


def _detektor(schluessel: str):
    quelle = f"muster.{schluessel}"

    def erkennen(dok, kontext):
        funktion = _funktion(schluessel)
        if funktion is None:
            return []
        sicherheit = SICHERHEIT.get(schluessel, 0.7)
        if getattr(funktion, "kategorie", None) != schluessel or schluessel not in muster.SPANNEN:
            return _text_rueckfall(dok, funktion, schluessel, quelle, sicherheit)
        treffer = []
        for st in _stellen_im_dokument(dok.text, schluessel):
            q = quelle + (".lesefehler" if st.hinweis == muster.HINWEIS_PRUEFZIFFER else "")
            treffer.append(Treffer(st.start, st.ende, schluessel, q,
                                   st.sicherheit if st.sicherheit is not None else sicherheit))
        return treffer
    erkennen.__name__ = f"muster_{schluessel}"
    erkennen.__doc__ = f"Muster „{schluessel}“ als Stellen (muster.stellen)."
    return erkennen


for _schluessel, _anzeige, _platzhalter, _f, _an in muster.KATEGORIEN:
    if _f is not None and _schluessel not in NICHT_HIER:
        registrieren(f"muster.{_schluessel}", {_schluessel}, ALLE_PROFILE, _detektor(_schluessel), ersetzt=True)
