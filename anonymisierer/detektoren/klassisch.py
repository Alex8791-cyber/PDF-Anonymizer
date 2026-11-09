"""Klassische Detektoren: die bisherigen Muster (muster.finde_*) und die Namenserkennung
(namen.finde_personen) als Detektoren, die STELLEN liefern.

Die Muster-Funktionen liefern Fundtexte; jeder Text wird an seinen Ganzwort-Vorkommen im Dokumenttext
verortet (exakte Vorkommen, sonst über den gemeinsamen Vergleicher). Die Namenserkennung liefert schon
Positionen. Dazu kommen die IMMER-Begriffe und eine Formularfeld-Regel (Etikett + Wert, Kammfelder).

Übergangsmodul: Agent "regeln" ersetzt die Muster-/Namens-Detektoren durch eigene Module, die Spans
direkt liefern (gleiche Register-Namen mit ersetzt=True, oder dieses Modul wird entfernt).
"""

from __future__ import annotations

import bisect
import re

from .. import muster, namen
from ..seitenmodell import SPALTENTRENNER, ganzwort_stellen, ganzwort_stellen_viele, modus_fuer
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


def _zeilenweise(dok) -> str | None:
    """Der Dokumenttext mit jeder Tabellenzelle auf einer eigenen Zeile (Spaltentrenner -> Zeilenumbruch) –
    so, wie die Muster ihn vor dem Seitenmodell sahen; None ohne Spaltentrenner. Einmal je Dokument."""
    text = dok.text
    if SPALTENTRENNER not in text:
        return None
    zwischen = getattr(dok, "_klassisch_zeilenweise", None)
    if zwischen is None or zwischen[0] is not text:
        zwischen = (text, text.replace(SPALTENTRENNER, "\n"))
        try:
            dok._klassisch_zeilenweise = zwischen
        except AttributeError:
            pass
    return zwischen[1]


def _muster_texte(funktion, dok) -> list:
    """Fundtexte eines Musters. Die Muster stammen aus der Zeit vor dem Seitenmodell (Tabellenzellen auf
    eigenen Zeilen) und lassen Leerraum zwischen Wörtern zu – über einen Spaltentrenner hinweg würden sie
    Nachbarzellen verschlucken ("78050 Villingen-Schwenningen | Kfz | Spreewald") oder ein Etikett mit Wert
    für einen Spaltenkopf halten ("Vertragsnummer | LV/86/0439377"). Deshalb: Treffer im Dokumenttext, die
    keinen Spaltentrenner überspannen, plus die Treffer der zeilenweisen Lesart."""
    roh = [x for x in funktion(dok.text) if x and SPALTENTRENNER not in x]
    zeilenweise = _zeilenweise(dok)
    if zeilenweise is not None:
        roh += list(funktion(zeilenweise))
    return [t for t in dict.fromkeys(x.strip() for x in roh if x and x.strip()) if len(t) >= 2]


def _muster_detektor(schluessel: str):
    quelle = f"muster.{schluessel}"

    def erkennen(dok, kontext):
        funktion = _funktion(schluessel)
        if funktion is None:
            return []
        modus = modus_fuer(schluessel)
        sicherheit = SICHERHEIT.get(schluessel, 0.7)
        texte = _muster_texte(funktion, dok)
        treffer = []
        pruefen = _PLAUSIBEL.get(schluessel)
        for stellen in _vorkommen(dok, texte, modus).values():
            for s, e in stellen:
                if pruefen is None or pruefen(dok.text, s, e):
                    treffer.append(Treffer(s, e, schluessel, quelle, sicherheit))
        return treffer
    erkennen.__name__ = f"muster_{schluessel}"
    return erkennen


_BETRAG_DANACH_RE = re.compile(r"[,.]\d")


def _strasse_plausibel(text: str, s: int, e: int) -> bool:
    """Eine Hausnummer steht nicht in einer anderen Tabellenspalte ("Rehazentrum Am Kurpark | 946,21")
    und ist kein Betrag ("Am Kurpark 946,21") – sonst würde Kontext (Einrichtung, Betrag) geschwärzt."""
    if SPALTENTRENNER in text[s:e]:
        return False
    return not _BETRAG_DANACH_RE.match(text, e)


# Zusatzprüfung je Kategorie für Stellen der Muster: (Dokumenttext, start, ende) -> bool
_PLAUSIBEL = {"strasse": _strasse_plausibel}


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


# Spaltenköpfe und Tabellenwörter, die die KI in einer einzelnen Zelle gern für Personen hält
_ZELLEN_KEINE_NAMEN = frozenset({
    "betrag", "beträge", "netto", "brutto", "gesamt", "gesamtbetrag", "summe", "zwischensumme", "saldo",
    "kfz", "tarif", "tarife", "beitrag", "beiträge", "erstattung", "leistung", "leistungen", "position",
    "menge", "preis", "einzelpreis", "gesamtpreis", "anzahl", "zeitraum", "datum", "status", "bemerkung",
    "bemerkungen", "rabatt", "steuer", "mwst", "zahlbetrag", "rechnung", "vertrag", "sparte", "produkt",
    "deckung", "laufzeit", "beginn", "ablauf", "prämie", "gebühr", "gebühren", "kosten", "art", "typ",
    "name", "vorname", "nachname", "anschrift", "ort", "plz", "straße", "telefon", "kennzeichen",
    "fälligkeit", "zahlung", "zahlungen", "eingang", "ausgang", "soll", "haben", "konto", "nummer"})


def _zellentext(text: str) -> str | None:
    """Nur die Tabellenzeilen (mit Spaltenlücken "\\t"), jede Zelle als eigene Zeile; alle übrigen Zeichen
    durch Leerzeichen ersetzt – gleiche Länge, also gleiche Offsets wie der Dokumenttext."""
    if "\t" not in text:
        return None
    teile = []
    for zeile in text.split("\n"):
        teile.append(zeile.replace("\t", "\n") if "\t" in zeile else " " * len(zeile))
    return "\n".join(teile)


def _zellen_kandidaten(text: str, kandidaten: list) -> list:
    """Zweiter Durchgang der Namenserkennung über die einzelnen Tabellenzellen. Das Seitenmodell hält eine
    Tabellenzeile zusammen (Spalten durch Tabulatoren getrennt, Vertrag Abschnitt 1); die Kurzzeilen-Erkennung
    sieht dann nur noch lange Zeilen und übersieht Namen in Zellen wie "Physiotherapie Santoro".
    Ergänzt nur Stellen, die sich mit keinem Kandidaten des ersten Durchgangs überschneiden."""
    zellen = _zellentext(text)
    if zellen is None:
        return []
    # Bereiche des ersten Durchgangs (sortiert, mit laufendem Maximum der Enden) und seine Namen als Text:
    # "Physiotherapie Zieliński" in einer Zelle ist kein neuer Name, wenn "Zieliński" schon erkannt ist
    belegt = sorted((int(k.get("start", -1)), int(k.get("ende", -1))) for k in kandidaten)
    anfaenge = [b[0] for b in belegt]
    max_ende, m = [], -1
    for _, e1 in belegt:
        m = max(m, e1)
        max_ende.append(m)
    bekannt = {" ".join(str(k.get("text", "")).split()).casefold() for k in kandidaten}
    aus = []
    for k in namen.finde_personen(zellen):
        s, e = int(k.get("start", -1)), int(k.get("ende", -1))
        if not (0 <= s < e <= len(text)) or text[s:e] != k.get("text"):
            continue
        i = bisect.bisect_left(anfaenge, e)
        if i and max_ende[i - 1] > s:
            continue                                   # überschneidet einen Kandidaten des ersten Durchgangs
        woerter = k["text"].casefold().split()
        if not woerter or all(w.strip(".,;:()") in _ZELLEN_KEINE_NAMEN for w in woerter):
            continue
        if len(woerter) > 1 and any(" ".join(woerter[a:b]) in bekannt
                                    for a in range(len(woerter)) for b in range(a + 1, len(woerter) + 1)):
            continue
        if len(woerter) == 1 and k["text"].isupper() and len(k["text"]) <= 3:
            continue                                   # "RLV", "PKV": Abkürzungen, keine Namen
        aus.append(dict(k, quelle="ner.zelle"))
    if aus:
        bestaetigt = _zellen_namen_bestaetigen({k["text"] for k in aus})
        if bestaetigt is not None:
            aus = [k for k in aus if k["text"] in bestaetigt]
    aus += _komma_zellen(text, zellen, kandidaten + aus)
    return aus


# Zelle "Nachname, Vorname" (Bestandslisten, Teilnehmerlisten), davor höchstens eine laufende Nummer
_KOMMA_ZELLE_RE = re.compile(
    r"(?:\d{1,4}\.?[ ]+)?"
    r"((?:(?:von|van|de|der|den|di|da|del|della|du|le|la|ter|ten|zu|zum|zur|vom)[ ]+)*"
    r"[^\W\d_][\w'’\-]*(?:[ \-][^\W\d_][\w'’\-]*)?)"
    r",[ ]+([^\W\d_][\w'’\-]*(?:[ \-][^\W\d_][\w'’\-]*)?)")


_PARTIKEL_KLEIN = frozenset({"von", "van", "de", "der", "den", "di", "da", "del", "della", "du", "le", "la", "ter",
                             "ten", "zu", "zum", "zur", "vom"})


def _nachname_gross(nachname: str) -> bool:
    """Der Nachname (ohne vorangestellte Partikel wie "von", "van den") beginnt mit einem Großbuchstaben."""
    kern = next((w for w in nachname.split() if w not in _PARTIKEL_KLEIN), "")
    return kern[:1].isupper()


def _komma_zellen(text: str, zellen: str, kandidaten: list) -> list:
    """Zellen der Form "Nachname, Vorname" als ganze Person, wenn der Vorname als Person gilt: schon erkannt
    oder von der KI im neutralen Satz bestätigt. Die KI übersieht sonst Nachnamen, die auch Wörter sind
    ("Hahn, Annika", "Weber, Jonas"), und schwärzt nur den Vornamen."""
    paare = []
    pos = 0
    for zeile in zellen.split("\n"):
        inhalt = zeile.strip()
        if inhalt and "," in inhalt and len(inhalt) <= 60:
            m = _KOMMA_ZELLE_RE.fullmatch(inhalt)
            if m and _nachname_gross(m.group(1)) and m.group(2)[0].isupper():
                anfang = pos + zeile.index(inhalt)
                paare.append((anfang + m.start(1), anfang + m.end(2), m.group(2)))
        pos += len(zeile) + 1
    if not paare:
        return []
    bekannt = {" ".join(str(k.get("text", "")).split()).casefold() for k in kandidaten}
    offen = {v for _, _, v in paare if v.casefold() not in bekannt and v.casefold() not in _ZELLEN_KEINE_NAMEN}
    personen = _zellen_personen_bestaetigen(offen) if offen else set()
    aus = []
    for s, e, vorname in paare:
        if vorname.casefold() in _ZELLEN_KEINE_NAMEN:
            continue
        if vorname.casefold() in bekannt or vorname in personen:
            voll = text[s:e]
            aus.append({"text": voll, "start": s, "ende": e, "gruppe": voll, "quelle": "ner.zelle"})
    return aus


def _zellen_personen_bestaetigen(texte: set) -> set:
    """Nur die Personen-Probe (ohne Wortart-Rückfall, der auch Orte als Eigennamen durchließe)."""
    nlp = namen.lade_ner()
    if nlp is None:
        return set()
    ok = set()
    texte = sorted(texte)
    try:
        vorn = len(_VORLAGE_PERSON.split("{}")[0])
        for t, d in zip(texte, nlp.pipe([_VORLAGE_PERSON.format(t) for t in texte], batch_size=64)):
            if any(e.label_ == "PER" and e.start_char < vorn + len(t) and e.end_char > vorn for e in d.ents):
                ok.add(t)
    except Exception:
        return set()
    return ok


_VORLAGE_PERSON = "Ich habe heute mit {} gesprochen."
_VORLAGE_WORTART = "Das ist {}."


def _zellen_namen_bestaetigen(texte: set):
    """Gegenprobe für Namen aus einzelnen Zellen (dort fehlt der KI der Satzzusammenhang, sie hält dann auch
    "Familientarif" oder "Betrag" für Personen): bestätigt, wenn die KI den Text in einem neutralen Satz als
    Person erkennt ODER als Eigennamen einordnet. Liefert die bestätigten Texte; None ohne Sprachmodell
    (dann gelten alle)."""
    nlp = namen.lade_ner()
    if nlp is None:
        return None
    texte = sorted(texte)
    ok = set()
    try:
        vorn = len(_VORLAGE_PERSON.split("{}")[0])
        for t, d in zip(texte, nlp.pipe([_VORLAGE_PERSON.format(t) for t in texte], batch_size=64)):
            if any(e.label_ == "PER" and e.start_char < vorn + len(t) and e.end_char > vorn for e in d.ents):
                ok.add(t)
        rest = [t for t in texte if t not in ok]
        vorn = len(_VORLAGE_WORTART.split("{}")[0])
        for t, d in zip(rest, nlp.pipe([_VORLAGE_WORTART.format(t) for t in rest], batch_size=64)):
            woerter = [tok for tok in d if vorn <= tok.idx < vorn + len(t) and tok.is_alpha
                       and tok.text.casefold() not in namen.PARTIKEL]
            if woerter and all(tok.pos_ == "PROPN" for tok in woerter):
                ok.add(t)
    except Exception:
        return None
    return ok


@detektor("ner", {"namen"})
def namen_erkennen(dok, kontext):
    """KI-Namenserkennung (spaCy) plus Regeln für Briefe, Formulare und Tabellen (namen.finde_personen);
    Tabellenzellen zusätzlich einzeln."""
    text = dok.text
    kandidaten = list(namen.finde_personen(text))
    kandidaten += _zellen_kandidaten(text, kandidaten)
    if "plzort" in kontext.aktive:
        kandidaten = _ohne_ortsnamen(text, kandidaten)
    kandidaten = _komma_phantome_entfernen(text, kandidaten)
    treffer = []
    for k in kandidaten:
        s, e = int(k.get("start", -1)), int(k.get("ende", -1))
        gruppe = k.get("gruppe")
        quelle = k.get("quelle", "ner")
        sicherheit = 0.5 if quelle == "ner.zelle" else 0.6
        if not (0 <= s < e <= len(text)) or text[s:e] != k["text"]:
            # Position fehlt oder passt nicht: alle Ganzwort-Stellen des Namens
            for s2, e2 in ganzwort_stellen(dok, k["text"], "name"):
                treffer.append(Treffer(s2, e2, "namen", quelle, sicherheit, gruppe))
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
        treffer.append(Treffer(s, e, "namen", quelle, sicherheit, gruppe))
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
