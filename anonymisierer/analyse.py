"""Analyse: Text und PDFs nach personenbezogenen Daten durchsuchen (Vertrag Phase 2, Abschnitte 2–4).

Ablauf:
  1. Seitenmodell bauen (seitenmodell.dokument_vorbereiten + dokument_aufbauen; Scans per OCR) –
     dasselbe Modell benutzen Schwärzung und Selbstkontrolle.
  2. Alle passenden Detektoren laufen lassen (detektoren.alle_treffer) -> Treffer mit Offsets.
  3. NIE-Liste: Ganzphrasen-Vorkommen sind Schutzhüllen – Treffer darin entfallen (auch Bruchstücke wie
     eine "Telefonnummer" mitten in der freigegebenen eigenen IBAN).
  4. Weitergabe: jeder Treffertext an ALLEN Ganzwort-Stellen des Dokuments (Vergleichsmodus je Kategorie;
     bei Namen alle Schreibweisen), dazu Namensbestandteile (Vor-, Nach-, Doppelnamensteile).
  5. Überlappende Stellen zusammenführen: die umfassende Stelle gewinnt (Bruchstücke gehen in ihr auf);
     bei gleicher Spanne entscheidet die Kategorie-Priorität (IMMER-Begriff > Kennungen > Namen >
     Adresse > Rest); teilweise Überlappung -> Vereinigung, Kategorie nach Priorität.
  6. Funde bilden (Format v2: id, stellen, quellen, sicherheit; alte Schlüssel bleiben) mit festen
     Pseudonymen je Person.

Öffentlich: analysiere_pdf, analysiere_text, weitergabe_anwenden, LaufWissen, ANZEIGE_BEGRIFF,
PLATZHALTER_BEGRIFF.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from pathlib import Path
from typing import NamedTuple

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import detektoren
from . import ocr as _ocr
from .detektoren import Kontext
from .muster import KATEGORIE_PRIORITAET, KATEGORIEN
from .namen import (ANREDEN, NAMEN_STOPPLISTE, PARTIKEL, TITEL, finde_personen,  # noqa: F401
                    lade_ner, ner_fehler)
from .seitenmodell import (Abgebrochen, dokument_aufbauen, dokument_aus_text, dokument_vorbereiten,
                           fund_schluessel, ganzwort_stellen, ganzwort_stellen_viele, hat_xfa, modus_fuer,
                           woerter_zu_zeilen)

ANZEIGE_BEGRIFF = "Begriff (IMMER-Liste)"
PLATZHALTER_BEGRIFF = "[BEGRIFF]"
ANZEIGE_NAME = "Name"
ANZEIGE_BESTANDTEIL = "Name (Bestandteil)"
_KONTEXT_RAND = 25

_KATEGORIE_INFO = {k: (anzeige, platzhalter) for k, anzeige, platzhalter, _, _ in KATEGORIEN}


# ----------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------
def _normalisiert(text: str) -> str:
    """Leerraum zusammenziehen (für Anzeige, Hinweise und Vergleiche)."""
    return re.sub(r"\s+", " ", text).strip()


def _such_muster(fundtext: str) -> re.Pattern:
    """Regex, der den Fundtext als ganzes Wort/Wortfolge mit beliebigem Leerraum zwischen den Wörtern
    findet (Groß-/Kleinschreibung egal). Nur noch Hilfsfunktion für Tests/Werkzeuge – Analyse und
    Schwärzung benutzen seitenmodell.ganzwort_stellen."""
    teile = [re.escape(t) for t in fundtext.split()]
    if not teile:
        return re.compile(r"(?!x)x")
    muster = r"\s+".join(teile)
    if re.match(r"[\wäöüß]", fundtext):
        muster = r"(?<![\wäöüß])" + muster
    if re.search(r"[\wäöüß]$", fundtext.strip()):
        muster = muster + r"(?![\wäöüß])"
    return re.compile(muster, re.IGNORECASE)


def _spannen(text: str, fundtext: str) -> list:
    return [(m.start(), m.end()) for m in _such_muster(fundtext).finditer(text)]


def _kontext_text(text: str, s: int, e: int) -> str:
    """Ca. 25 Zeichen vor und nach einer Stelle, Zeilenumbrüche -> Leerzeichen, Fund in »…«."""
    davor = _normalisiert(text[max(0, s - _KONTEXT_RAND):s])
    danach = _normalisiert(text[e:e + _KONTEXT_RAND])
    mitte = _normalisiert(text[s:e])
    kontext = (f"{'…' if s > _KONTEXT_RAND else ''}{davor} »{mitte}« {danach}"
               f"{'…' if e + _KONTEXT_RAND < len(text) else ''}")
    return _normalisiert(kontext)


def _anzeige(kategorie: str) -> str:
    if kategorie == "begriff":
        return ANZEIGE_BEGRIFF
    if kategorie == "namen":
        return ANZEIGE_NAME
    return _KATEGORIE_INFO.get(kategorie, (kategorie, None))[0] or kategorie


def _platzhalter(kategorie: str) -> str:
    if kategorie == "begriff":
        return PLATZHALTER_BEGRIFF
    p = _KATEGORIE_INFO.get(kategorie, (None, None))[1]
    return p or f"[{kategorie.upper()}]"


def _prioritaeten() -> dict:
    """Rang je Kategorie für Stellen gleicher Spanne (kleiner = gewinnt): IMMER-Begriff (ausdrücklicher
    Wunsch) > Kennungen (Reihenfolge aus muster.KATEGORIE_PRIORITAET) > Namen > Adresse > Rest."""
    adresse, rest = ["strasse", "plzort"], ["geburt", "datum"]
    kennungen = [k for k in KATEGORIE_PRIORITAET if k not in adresse + rest]
    reihenfolge = ["begriff"] + kennungen + ["namen"] + adresse + rest
    return {k: i for i, k in enumerate(reihenfolge)}


_PRIORITAET = _prioritaeten()


def _rang(kategorie: str) -> int:
    return _PRIORITAET.get(kategorie, len(_PRIORITAET))


def _wissen_modul():
    try:
        from . import wissen  # Agent "regeln" (Listen der Wissensbasis)
        return wissen
    except Exception:
        return None


def _melde(meldungen, liste, art, code, text, seite=None):
    if liste is not None and text not in liste:
        liste.append(text)
    if meldungen is not None:
        meldungen.append({"art": art, "code": code, "text": text, "seite": seite})


class LaufWissen:
    """Dokumentübergreifendes Wissen eines Laufs (für Detektoren und weitergabe_anwenden):
    bekannte Personen (Name -> Pseudonym) und Kennungen der bisher analysierten Dokumente."""

    def __init__(self):
        self.personen: dict = {}       # Namensschlüssel -> Pseudonym
        self.kennungen: dict = {}      # (Kategorie, Schlüssel) -> Text

    def aufnehmen(self, ergebnis: dict):
        for f in (ergebnis or {}).get("funde", []):
            modus = modus_fuer(f["kategorie"])
            schluessel = fund_schluessel(f["text"], modus)
            if f["kategorie"] == "namen":
                self.personen.setdefault(schluessel, f.get("ersatz"))
            elif modus == "kennung":
                self.kennungen.setdefault((f["kategorie"], schluessel), f["text"])


# ----------------------------------------------------------------------
# NIE-Liste als Schutzhüllen
# ----------------------------------------------------------------------
class _NieHuellen:
    """NIE-schwärzen-Liste: Ganzwort-/Ganzphrasen-Vorkommen (Mindestlänge 3, Groß-/Kleinschreibung egal,
    Einträge mit Ziffern trennzeichen-flexibel wie Kennungen). Jede Stelle, die ganz in einem Vorkommen
    liegt, bleibt stehen – auch Bruchstücke anderer Kategorien (Gutachten KQ-03/KQ-04)."""

    def __init__(self, dok, eintraege):
        huellen = []
        for e in eintraege or []:
            n = _normalisiert(str(e or "")).strip(".,;:")
            if len(n) < 3:
                continue
            modus = "kennung" if any(c.isdigit() for c in n) else "begriff"
            huellen.extend(ganzwort_stellen(dok, n, modus))
        huellen.sort()
        self.anfaenge = [h[0] for h in huellen]
        self.huellen = huellen
        laufendes = []
        m = -1
        for _, e in huellen:
            m = max(m, e)
            laufendes.append(m)
        self.max_ende = laufendes

    def __bool__(self):
        return bool(self.huellen)

    def umhuellt(self, s: int, e: int) -> bool:
        if not self.huellen:
            return False
        i = bisect_right(self.anfaenge, s)
        if i == 0 or self.max_ende[i - 1] < e:
            return False
        return any(he >= e for hs, he in self.huellen[:i] if hs <= s)


# ----------------------------------------------------------------------
# Namen und Pseudonyme
# ----------------------------------------------------------------------
_NAMENSSUFFIXE = {"jun.", "jun", "sen.", "sen", "junior", "senior", "jr.", "jr", "sr.", "sr"}
# Häufige Nachnamen, die auch Allerweltswörter sind (groß nur als Name oder am Satzanfang)
_ALLERWELTS_NAMEN = {"lange", "lang", "klein", "groß", "gross", "kurz", "alt", "neu", "neumann", "jung", "frei",
                     "fromm", "stark", "schön", "gut", "schwarz", "weiß", "weiss", "braun", "roth", "rot", "grün",
                     "ernst", "froh", "heil", "hart", "kühn", "klug", "lieb", "wild", "bald", "gern", "gerne",
                     "sauer", "süß", "fein", "rau", "fest", "still", "laut", "kraus", "krause"}
_PERSONENKONTEXT_RE = re.compile(
    r"(?:Herrn?|Frau|Fräulein|Hr\.|Fr\.|Familie|Fam\.|Eheleute|Dr\.|Prof\.|Dipl\.-\w+\.?|gez\.|i\.\s?A\.|"
    r"i\.\s?V\.|ppa\.|Name:?|Nachname:?|Vorname:?)[\s,]*$")
_WORT_DAVOR_RE = re.compile(r"([^\W\d_][\w'’\-]*)[\s,]*$")
_WORT_DANACH_RE = re.compile(r"[\s,]*([^\W\d_][\w'’\-]*)")
_KLEINWORT_RE = re.compile(r"(?<![\w])[a-zäöüß][a-zäöüß]{2,}(?![\w])")


def _name_zerlegen(name: str) -> tuple:
    """(vornamen, nachname) aus einem Namen: Titel/Anreden/Partikel/Suffixe entfernt, 'Nachname, Vorname'
    erkannt. Bei einem einzelnen Wort ist nachname None und das Wort steht in vornamen (Rolle offen)."""
    def tokens(teil):
        aus = []
        for roh in teil.split():
            t = roh.strip(".,;:()[]\"'")
            if not t:
                continue
            tl, rl = t.lower(), roh.lower()
            if tl in TITEL or rl in TITEL or tl in ANREDEN or rl in ANREDEN or rl in _NAMENSSUFFIXE:
                continue
            if t.islower() and tl in PARTIKEL:
                continue
            aus.append(t)
        return aus
    if "," in name:
        links, rechts = name.split(",", 1)
        nach, vor = tokens(links), tokens(rechts)
        if nach and vor:
            return vor, nach[-1]
        rest = nach + vor
    else:
        rest = tokens(name)
    if not rest:
        return [], None
    if len(rest) == 1:
        return rest, None
    return rest[:-1], rest[-1]


def _schluessel(wort: str) -> str:
    return wort.casefold().replace("ß", "ss")


def _bestandteile(name: str) -> list:
    """Namensbestandteile: Mindestlänge 3, keine Titel/Partikel/Anreden; Doppelnamen zusätzlich in
    ihre Teile zerlegt ("Klein-Hoffmann" -> "Klein-Hoffmann", "Klein", "Hoffmann")."""
    aus = []
    for roh in re.split(r"[\s,]+", name):
        t = roh.strip(".,;:()[]\"'")
        teile = [t] + ([x for x in t.split("-") if x] if "-" in t else [])
        for teil in teile:
            if len(teil) < 3:
                continue
            tl, rl = teil.lower(), roh.lower()
            if tl in TITEL or rl in TITEL or tl in ANREDEN or tl in PARTIKEL or tl in NAMEN_STOPPLISTE:
                continue
            if rl in _NAMENSSUFFIXE or any(c.isdigit() for c in teil):
                continue
            if teil.casefold() != name.casefold() and teil not in aus:
                aus.append(teil)
    return aus


def _pseudonym(nummer: int) -> str:
    return f"[PERSON {chr(65 + nummer)}]" if nummer < 26 else f"[PERSON {nummer + 1}]"


def _familienpseudonym(nummer: int) -> str:
    return f"[FAMILIE {chr(65 + nummer)}]" if nummer < 26 else f"[FAMILIE {nummer + 1}]"


class _Personen:
    """Personen mit festen Pseudonymen aus den Namens-Treffern.

    - Varianten derselben Person (Dr. Max Mustermann / Mustermann, Max / MAX MUSTERMANN /
      Max Mustermanns) teilen sich ein Pseudonym (Schlüssel: erster Vorname + Nachname; Genitiv-s wird
      der Grundform zugeordnet – Gutachten EQ-10).
    - Buchstaben in der Reihenfolge des ersten Auftretens.
    - Einzelne Wörter: eindeutiger Nachname (auch als Teil genau eines Doppelnamens) -> diese Person;
      Nachname mehrerer Personen (Familie) -> [FAMILIE A]; Vorname -> erste Person damit; sonst eigene Person.
    - Bestandteile erben das Pseudonym ihrer Person (Nachname einer Familie -> [FAMILIE X])."""

    def __init__(self, varianten: list):
        # varianten: [(schluessel, text, pos, gruppe)] nach Position sortiert
        self.ersatz: dict = {}              # Namensschlüssel -> Pseudonym
        self.bestandteile: list = []        # [(text, schluessel, pseudonym)]
        self.namensteile: set = set()       # _schluessel aller Vor-/Nachnamen (Personenkontext)
        personen: dict = {}
        einzel: list = []
        for key, text, pos, gruppe in varianten:
            basis = gruppe or text
            vor, nach = _name_zerlegen(basis)
            if nach is None and gruppe:
                vor, nach = _name_zerlegen(text)
            if nach is None:
                einzel.append((key, text, pos))
                continue
            schl = (_schluessel(vor[0]) if vor else "", _schluessel(nach))
            p = personen.setdefault(schl, {"varianten": {}, "vor": set(), "pos": pos, "texte": {}})
            p["varianten"][key] = min(p["varianten"].get(key, pos), pos)
            p["texte"].setdefault(key, text)
            p["vor"].update(_schluessel(v) for v in vor)
            p["pos"] = min(p["pos"], pos)
        # Genitiv-Varianten ("Max Mustermanns Vertrag") mit der Grundform zusammenführen
        for schl in list(personen):
            vor, nach = schl
            basis = (vor, nach[:-1]) if nach.endswith("s") else None
            if basis and basis in personen and basis != schl:
                quelle, ziel = personen.pop(schl), personen[basis]
                for k, pos in quelle["varianten"].items():
                    ziel["varianten"][k] = min(ziel["varianten"].get(k, pos), pos)
                    ziel["texte"].setdefault(k, quelle["texte"][k])
                ziel["vor"] |= quelle["vor"]
                ziel["pos"] = min(ziel["pos"], quelle["pos"])
        nach_index: dict = {}
        vor_index: dict = {}
        for schl, p in personen.items():
            nach_index.setdefault(schl[1], set()).add(schl)
            for v in p["vor"]:
                vor_index.setdefault(v, set()).add(schl)
        einzel_zuordnung: dict = {}          # key -> ("person", schl) | ("familie", nachname)
        for key, text, pos in einzel:
            s = _schluessel(text.strip(".,;:()"))
            if s not in nach_index and s.endswith("s") and s[:-1] in nach_index:
                s = s[:-1]                    # Genitiv eines bekannten Nachnamens
            if s not in nach_index:
                doppel = [n for n in nach_index if "-" in n and s in n.split("-")]
                if len(doppel) == 1:          # Teil genau eines Doppelnamens (Gutachten EQ-10)
                    s = doppel[0]
            if s in nach_index:
                traeger = nach_index[s]
                if len(traeger) == 1:
                    schl = next(iter(traeger))
                    personen[schl]["varianten"].setdefault(key, pos)
                    personen[schl]["texte"].setdefault(key, text)
                    personen[schl]["pos"] = min(personen[schl]["pos"], pos)
                    einzel_zuordnung[key] = ("person", schl)
                else:
                    einzel_zuordnung[key] = ("familie", s)
            elif s in vor_index:
                schl = sorted(vor_index[s], key=lambda x: personen[x]["pos"])[0]
                personen[schl]["varianten"].setdefault(key, pos)
                personen[schl]["texte"].setdefault(key, text)
                personen[schl]["pos"] = min(personen[schl]["pos"], pos)
                einzel_zuordnung[key] = ("person", schl)
            else:
                schl = ("", s)
                p = personen.setdefault(schl, {"varianten": {}, "vor": set(), "pos": pos, "texte": {}})
                p["varianten"].setdefault(key, pos)
                p["texte"].setdefault(key, text)
                p["pos"] = min(p["pos"], pos)
                nach_index.setdefault(s, set()).add(schl)
                einzel_zuordnung[key] = ("person", schl)
        reihenfolge = sorted(personen, key=lambda schl: personen[schl]["pos"])
        familien_namen = {schl[1] for schl in reihenfolge if schl[1] and len(nach_index.get(schl[1], ())) > 1}
        # Zuordnung Namensschlüssel -> ("person", schl) | ("familie", nachname)
        self.zuordnung: dict = {}
        for key, (art, wert) in einzel_zuordnung.items():
            if art == "familie":
                self.zuordnung[key] = ("familie", wert)
        for schl in reihenfolge:
            p = personen[schl]
            for key in sorted(p["varianten"], key=lambda k: p["varianten"][k]):
                if key in self.zuordnung:
                    continue
                vor, nach = _name_zerlegen(p["texte"][key])
                if nach is None and vor and _schluessel(vor[0]) in familien_namen:
                    self.zuordnung[key] = ("familie", _schluessel(vor[0]))   # nackter Familienname
                else:
                    self.zuordnung[key] = ("person", schl)
            self.namensteile.add(schl[1])
            self.namensteile |= p["vor"]
        # Bestandteile (Personen in Reihenfolge des Auftretens; erster Träger gewinnt)
        for schl in reihenfolge:
            p = personen[schl]
            for key in sorted(p["varianten"], key=lambda k: p["varianten"][k]):
                for teil in _bestandteile(p["texte"][key]):
                    tkey = fund_schluessel(teil, "name")
                    if not tkey:
                        continue
                    self.namensteile.add(_schluessel(teil))
                    if tkey in self.zuordnung:
                        continue
                    s = _schluessel(teil)
                    self.zuordnung[tkey] = ("familie", s) if s in familien_namen else ("person", schl)
                    self.bestandteile.append((teil, tkey))
        self._pos = {schl: personen[schl]["pos"] for schl in personen}
        self._familie_pos = {}
        for schl in reihenfolge:
            if schl[1] in familien_namen:
                self._familie_pos.setdefault(schl[1], personen[schl]["pos"])

    def pseudonyme(self, schluessel: list) -> dict:
        """Pseudonyme für die tatsächlich verwendeten Namensschlüssel: Buchstaben nur für Personen, die
        in der Fundliste vorkommen, in der Reihenfolge ihres ersten Auftretens im Dokument."""
        personen = set()
        familien = set()
        fremde = []
        for k in schluessel:
            art_wert = self.zuordnung.get(k)
            if art_wert is None:
                fremde.append(k)
            elif art_wert[0] == "person":
                personen.add(art_wert[1])
            else:
                familien.add(art_wert[1])
        buchstabe = {schl: _pseudonym(i) for i, schl in
                     enumerate(sorted(personen, key=lambda s: self._pos.get(s, 1 << 30)))}
        familie = {n: _familienpseudonym(i) for i, n in
                   enumerate(sorted(familien, key=lambda n: self._familie_pos.get(n, 1 << 30)))}
        ersatz = {}
        weitere = len(buchstabe)
        for k in schluessel:
            art_wert = self.zuordnung.get(k)
            if art_wert is None:
                ersatz[k] = _pseudonym(weitere)
                weitere += 1
            elif art_wert[0] == "person":
                ersatz[k] = buchstabe[art_wert[1]]
            else:
                ersatz[k] = familie[art_wert[1]]
        return ersatz


def _satzanfang(text: str, s: int) -> bool:
    """Steht die Stelle am Satzanfang (vorher nur Leerraum nach . ! ? : oder Textbeginn)?"""
    i = s - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    return i < 0 or text[i] in ".!?:"


def _bindestrich_wort(text: str, s: int, e: int):
    """Das Bindestrich-Kompositum um eine Stelle ("Kraftfahrt-Versicherung" um "Kraftfahrt") oder None."""
    a, b = s, e
    while a >= 2 and text[a - 1] == "-" and text[a - 2].isalnum():
        a -= 1
        while a > 0 and text[a - 1].isalnum():
            a -= 1
    while b + 1 < len(text) and text[b] == "-" and text[b + 1].isalnum():
        b += 1
        while b < len(text) and text[b].isalnum():
            b += 1
    return None if (a, b) == (s, e) else text[a:b]


def _personenkontext(text: str, s: int, e: int, namensteile: set) -> bool:
    davor = text[max(0, s - 30):s]
    if _PERSONENKONTEXT_RE.search(davor):
        return True
    m = _WORT_DAVOR_RE.search(davor)
    if m and _schluessel(m.group(1)) in namensteile:
        return True
    m = _WORT_DANACH_RE.match(text, e)
    return bool(m and _schluessel(m.group(1)) in namensteile)


# ----------------------------------------------------------------------
# Kern der Analyse
# ----------------------------------------------------------------------
class _Kandidat(NamedTuple):
    start: int
    ende: int
    kategorie: str
    schluessel: tuple              # (Kategorie, Vergleichsschlüssel) = Fund-Identität
    quelle: str
    sicherheit: float
    art: int                       # 0 = Detektor, 1 = Weitergabe, 2 = Namensbestandteil


def _fund_bauen(dok, schluessel, kategorie, stellen_global, quellen, sicherheit, anzeige, ersatz, hinweis):
    stellen = []
    for s, e in stellen_global:
        for nr, ls, le in dok.lokal(s, e):
            stellen.append({"seite": nr, "start": ls, "ende": le, "an": True,
                            "text": dok.seiten[nr].text[ls:le]})
    s0, e0 = stellen_global[0]
    erste = stellen[0] if stellen else None
    text = erste["text"] if erste else dok.text[s0:e0]
    return {"id": "", "kategorie": kategorie, "anzeige": anzeige, "text": text, "ersatz": ersatz,
            "seiten": [] if dok.aus_text else sorted({st["seite"] + 1 for st in stellen}),
            "anzahl": max(1, len(stellen)), "kontext": _kontext_text(dok.text, s0, e0),
            "stellen": stellen, "quellen": sorted(quellen), "sicherheit": round(float(sicherheit), 3),
            "hinweis": hinweis}


def _analysiere_dokument(dok, aktive, whitelist, immer_schwaerzen, profil="hoch", kundenliste=None,
                         lauf=None, hinweise=None, warnungen=None, meldungen=None) -> list:
    """Kern der Analyse auf einem Seitenmodell. Liefert die Funde (Format v2)."""
    hinweise = [] if hinweise is None else hinweise
    text = dok.text
    kontext = Kontext(aktive, profil, whitelist, immer_schwaerzen, wissen=_wissen_modul(),
                      kundenliste=kundenliste, lauf=lauf)
    fehler: list = []
    treffer = detektoren.alle_treffer(dok, kontext, fehler)
    for f in list(detektoren.LADEFEHLER) + fehler:
        _melde(meldungen, warnungen, "warnung", "ERKENNUNG_FEHLER",
               f"{f} – diese Regel hat nichts erkannt, Ergebnis bitte besonders sorgfältig prüfen!")

    # 1) NIE-Liste: Treffer in einer Schutzhülle entfallen (IMMER-Begriffe nicht)
    nie = _NieHuellen(dok, whitelist)
    behalten = []
    freigegeben: dict = {}
    for t in treffer:
        if t.kategorie != "begriff" and nie.umhuellt(t.start, t.ende):
            freigegeben.setdefault(_normalisiert(text[t.start:t.ende]), None)
            continue
        behalten.append(t)
    for t in freigegeben:
        _melde(meldungen, hinweise, "hinweis", "NIE_FREIGABE", f"Durch NIE-Liste freigegeben: {t}")

    # 2) Personen und Pseudonyme aus den Namens-Treffern
    namen_treffer = sorted((t for t in behalten if t.kategorie == "namen"), key=lambda t: t.start)
    roh_schluessel = {}
    for t in namen_treffer:
        roh_schluessel.setdefault(fund_schluessel(text[t.start:t.ende], "name"), t)

    def namensschluessel(k: str) -> str:
        if k.endswith("s") and k[:-1] in roh_schluessel:      # Genitiv -> Grundform
            return k[:-1]
        return k
    varianten, gesehen_var = [], set()
    for t in namen_treffer:
        k = namensschluessel(fund_schluessel(text[t.start:t.ende], "name"))
        if k and k not in gesehen_var:
            gesehen_var.add(k)
            varianten.append((k, text[t.start:t.ende], t.start, t.gruppe))
        elif k and t.gruppe:
            for i, v in enumerate(varianten):
                if v[0] == k and v[3] is None:
                    varianten[i] = (v[0], v[1], v[2], t.gruppe)
    personen = _Personen(varianten)
    kleinwoerter = {w for w in _KLEINWORT_RE.findall(text)} if namen_treffer else set()
    wissen = kontext.wissen

    def mehrdeutig(wort: str) -> bool:
        w = wort.casefold()
        if w in kleinwoerter or w in _ALLERWELTS_NAMEN:
            return True
        liste = getattr(wissen, "ALLERWELTSWOERTER", None) if wissen is not None else None
        return bool(liste) and w in liste

    def zulassen(s: int, e: int, wort: str) -> bool:
        """Weitergabe eines einzelnen Namensworts: nicht als Teil eines fremden Bindestrich-Worts
        ("Kraftfahrt" in "Kraftfahrt-Versicherung"); mehrdeutige Wörter nicht am Satzanfang ohne
        Personenkontext."""
        kompositum = _bindestrich_wort(text, s, e)
        if kompositum is not None:
            andere = [p for p in kompositum.split("-") if p and _schluessel(p) != _schluessel(wort)]
            if (fund_schluessel(kompositum, "name") not in personen.zuordnung
                    and not any(_schluessel(p) in personen.namensteile for p in andere)):
                return False
        if not mehrdeutig(wort):
            return True
        return not _satzanfang(text, s) or _personenkontext(text, s, e, personen.namensteile)

    # 3) Kandidaten: Detektor-Treffer, Weitergabe, Namensbestandteile
    kandidaten = []
    schluessel_je_treffer = {}
    for t in behalten:
        modus = modus_fuer(t.kategorie)
        roh = text[t.start:t.ende]
        k = fund_schluessel(roh, modus)
        if not k:
            continue
        if t.kategorie == "namen":
            k = namensschluessel(k)
        schl = (t.kategorie, k)
        schluessel_je_treffer[(t.kategorie, roh)] = schl
        kandidaten.append(_Kandidat(t.start, t.ende, t.kategorie, schl, t.quelle, t.sicherheit, 0))
    gesucht: dict = {}                     # (Kategorie, Text) -> Sicherheit
    for t in behalten:
        roh = text[t.start:t.ende]
        if (t.kategorie, roh) in schluessel_je_treffer:
            gesucht[(t.kategorie, roh)] = max(gesucht.get((t.kategorie, roh), 0.0), t.sicherheit)
    nach_modus: dict = {}
    for kategorie, roh in gesucht:
        nach_modus.setdefault(modus_fuer(kategorie), []).append(roh)
    vorkommen = {modus: ganzwort_stellen_viele(dok, texte, modus) for modus, texte in nach_modus.items()}
    for (kategorie, roh), sicherheit in gesucht.items():
        modus = modus_fuer(kategorie)
        schl = schluessel_je_treffer[(kategorie, roh)]
        einzelwort = modus == "name" and len(roh.split()) == 1 and "," not in roh
        for s, e in vorkommen[modus].get(roh, ()):
            if kategorie != "begriff" and nie.umhuellt(s, e):
                continue
            if einzelwort and not zulassen(s, e, roh):
                continue
            kandidaten.append(_Kandidat(s, e, kategorie, schl, "weitergabe", sicherheit, 1))
    if "namen" in set(aktive) and personen.bestandteile:
        teile = ganzwort_stellen_viele(dok, [teil for teil, _ in personen.bestandteile], "name")
        for teil, tkey in personen.bestandteile:
            for s, e in teile.get(teil, ()):
                if nie.umhuellt(s, e) or not zulassen(s, e, teil):
                    continue
                kandidaten.append(_Kandidat(s, e, "namen", ("namen", tkey), "bestandteil", 0.5, 2))

    # 4) Überlappende Stellen zusammenführen
    kandidaten.sort(key=lambda k: (k.start, -k.ende))
    stellen = []          # (start, ende, schluessel, kategorie, quellen, sicherheit, arten)
    gruppe, ende = [], -1

    def abschliessen(gruppe):
        u_s = min(k.start for k in gruppe)
        u_e = max(k.ende for k in gruppe)
        sieger = max(gruppe, key=lambda k: (k.start == u_s and k.ende == u_e, -_rang(k.kategorie),
                                           k.ende - k.start, k.art == 0, k.sicherheit))
        stellen.append((u_s, u_e, sieger.schluessel, sieger.kategorie, {k.quelle for k in gruppe},
                        max(k.sicherheit for k in gruppe), {k.art for k in gruppe if k.schluessel == sieger.schluessel}))
    for k in kandidaten:
        if gruppe and k.start < ende:
            gruppe.append(k)
            ende = max(ende, k.ende)
        else:
            if gruppe:
                abschliessen(gruppe)
            gruppe, ende = [k], k.ende
    if gruppe:
        abschliessen(gruppe)

    # 5) Funde
    je_fund: dict = {}
    for s, e, schl, kategorie, quellen, sicherheit, arten in stellen:
        eintrag = je_fund.setdefault(schl, {"stellen": [], "quellen": set(), "sicherheit": 0.0, "arten": set(),
                                            "kategorie": kategorie})
        eintrag["stellen"].append((s, e))
        eintrag["quellen"] |= quellen
        eintrag["sicherheit"] = max(eintrag["sicherheit"], sicherheit)
        eintrag["arten"] |= arten
    funde = []
    namens_ersatz = personen.pseudonyme(
        [schl[1] for schl, eintrag in sorted(je_fund.items(), key=lambda x: x[1]["stellen"][0])
         if eintrag["kategorie"] == "namen"])
    for schl, eintrag in je_fund.items():
        kategorie = eintrag["kategorie"]
        hinweis = None
        if kategorie == "namen":
            nur_bestandteil = eintrag["arten"] <= {2}
            anzeige = ANZEIGE_BESTANDTEIL if nur_bestandteil else ANZEIGE_NAME
            ersatz = namens_ersatz[schl[1]]
            if nur_bestandteil:
                hinweis = "nur als Namensbestandteil erkannt"
        else:
            anzeige = _anzeige(kategorie)
            ersatz = _platzhalter(kategorie)
        funde.append(_fund_bauen(dok, schl, kategorie, sorted(eintrag["stellen"]), eintrag["quellen"],
                                 eintrag["sicherheit"], anzeige, ersatz, hinweis))
    funde.sort(key=lambda f: (f["stellen"][0]["seite"], f["stellen"][0]["start"]) if f["stellen"] else (0, 0))
    for i, f in enumerate(funde, 1):
        f["id"] = f"f{i}"
    return funde


def _analysiere(text: str, aktive: set, whitelist: list, immer_schwaerzen: list) -> tuple:
    """Analyse eines reinen Texts. Liefert (funde, hinweise) (für Tests und Werkzeuge)."""
    hinweise: list = []
    dok = dokument_aus_text(text)
    funde = _analysiere_dokument(dok, set(aktive), whitelist, immer_schwaerzen, hinweise=hinweise)
    return funde, hinweise


def analysiere_text(text: str, aktive: set[str], whitelist: list[str], immer_schwaerzen: list[str]) -> list[dict]:
    """Durchsucht einen Text nach allen aktivierten Kategorien. Liefert Funde (seiten bleibt leer,
    stellen beziehen sich auf die eine Seite des Textmodells)."""
    funde, _ = _analysiere(text, set(aktive), whitelist, immer_schwaerzen)
    return funde


# ----------------------------------------------------------------------
# PDF-Analyse
# ----------------------------------------------------------------------
def _ocr_noetig(seite) -> str:
    """Vertrags-API ocr_noetig(seite) -> 'nein' | 'seite' | 'bilder' (mit Rückfall auf ist_scan_seite)."""
    if hasattr(_ocr, "ocr_noetig"):
        return _ocr.ocr_noetig(seite)
    return "seite" if _ocr.ist_scan_seite(seite) else "nein"


class _AlterOcrDienst:
    """Rückfall auf die alten Funktionen (ocr_textpage), wenn ocr.py noch keinen OcrDienst hat."""

    def __init__(self, doc):
        self.doc = doc

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None):
        seite = self.doc[seite_nr0]
        tp, warnung = _ocr.ocr_textpage(seite)
        if tp is None:
            return [], warnung
        woerter = [(w[0], w[1], w[2], w[3], w[4]) for w in tp.extractWORDS()
                   if clip is None or fitz.Rect(w[:4]).intersects(clip)]
        return woerter, warnung

    def abbrechen(self):
        pass

    def schliessen(self):
        pass


def _woerter_zu_text(woerter) -> str:
    """OCR-Wörter (x0, y0, x1, y1, text) zu Zeilen zusammensetzen (dieselbe Zeilenbildung wie das Modell)."""
    return "\n".join(" ".join(str(w[4]) for w in zeile) for zeile in woerter_zu_zeilen(woerter))


def _hat_xfa(doc) -> bool:
    return hat_xfa(doc)


def analysiere_pdf(pdf_pfad: Path, aktive: set[str], whitelist: list[str], immer_schwaerzen: list[str],
                   melde=None, fortschritt=None, abbruch=None, ocr=None, profil: str = "hoch",
                   kundenliste=None, lauf=None) -> dict:
    """Öffnet ein PDF (liest Scans per OCR), baut das Seitenmodell und liefert alle Funde.

    melde(text): Fortschrittstext; fortschritt(seite_1basiert, seiten_gesamt); abbruch: threading.Event
    (bei is_set() sofort aufhören, fehler='Abgebrochen'); ocr: OcrDienst oder None (dann eigener Dienst).
    Rückgabe zusätzlich zu Phase 1: "modell" (Dokument, nur im Speicher), "felder", "profil", "meldungen",
    "text_lesbar"; Funde im Format v2 (id, stellen, quellen, sicherheit, hinweis)."""
    pdf_pfad = Path(pdf_pfad)
    aktive = set(aktive)
    ergebnis = {"datei": pdf_pfad, "funde": [], "warnungen": [], "hinweise": [], "fehler": None,
                "seiten": 0, "ocr_seiten": 0, "ocr_cache": {}, "meldungen": [], "modell": None, "felder": [],
                "profil": profil, "text_lesbar": False, "nie": list(whitelist or []),
                "immer": list(immer_schwaerzen or []), "aktive": sorted(aktive)}
    warnungen, hinweise, meldungen = ergebnis["warnungen"], ergebnis["hinweise"], ergebnis["meldungen"]

    def abgebrochen():
        ergebnis["fehler"] = "Abgebrochen"
        _melde(meldungen, None, "fehler", "ABGEBROCHEN", "Abgebrochen")
        return ergebnis

    try:
        doc = fitz.open(pdf_pfad)
    except Exception as e:
        ergebnis["fehler"] = f"Konnte nicht geöffnet werden: {e}"
        return ergebnis
    eigener_dienst = None
    try:
        if doc.needs_pass:
            ergebnis["fehler"] = "Passwortgeschützt — übersprungen."
            return ergebnis
        ergebnis["seiten"] = len(doc)
        vorbereitung = dokument_vorbereiten(doc)
        if vorbereitung.get("dokument") is not None and vorbereitung["dokument"] is not doc:
            alt, doc = doc, vorbereitung["dokument"]          # Ebenen: neu geöffnete Fassung
            alt.close()
        if vorbereitung.get("xfa"):
            _melde(meldungen, warnungen, "warnung", "XFA", "XFA-Formular: Feldinhalte können nicht geprüft werden")
        if vorbereitung.get("bake_fehler"):
            _melde(meldungen, warnungen, "warnung", "FORMULAR_EINGEBRANNT",
                   f"Formularfelder konnten nicht eingebrannt werden: {vorbereitung['bake_fehler']}")
        elif vorbereitung["zaehler"].get("formularfelder"):
            _melde(meldungen, None, "hinweis", "FORMULAR_EINGEBRANNT",
                   f"{vorbereitung['zaehler']['formularfelder']} Formularfeld(er) gelesen – die Werte werden "
                   f"wie Seitentext geprüft.")
        dienst = ocr
        if dienst is None:
            if hasattr(_ocr, "OcrDienst"):
                try:
                    eigener_dienst = _ocr.OcrDienst()
                except Exception as e:
                    _melde(meldungen, warnungen, "warnung", "OCR_FEHLER", f"OCR-Dienst konnte nicht gestartet werden: {e}")
                    eigener_dienst = _AlterOcrDienst(doc) if hasattr(_ocr, "ocr_textpage") else None
            elif hasattr(_ocr, "ocr_textpage"):
                eigener_dienst = _AlterOcrDienst(doc)
            dienst = eigener_dienst
        try:
            dok = dokument_aufbauen(doc, pdf_pfad, ocr=dienst, ocr_cache=ergebnis["ocr_cache"], melde=melde,
                                    fortschritt=fortschritt, abbruch=abbruch, warnungen=warnungen,
                                    hinweise=hinweise, meldungen=meldungen, vorbereitung=vorbereitung)
        except Abgebrochen:
            return abgebrochen()
    finally:
        if eigener_dienst is not None:
            try:
                eigener_dienst.schliessen()
            except Exception:
                pass
        doc.close()

    dok.nie = list(whitelist or [])            # für Schwärzung/Restrisiko (eigene Daten der Nutzerin)
    ergebnis["modell"] = dok
    ergebnis["felder"] = list(dok.felder)
    ergebnis["ocr_seiten"] = sum(1 for s in dok.seiten if s.ocr_modus == "seite" and s.ocr_woerter)
    if not dok.text.strip():
        _melde(meldungen, warnungen, "warnung", "KEIN_TEXT", "Kein Text lesbar — weder direkt noch per OCR.")
        return ergebnis
    ergebnis["text_lesbar"] = True
    if ergebnis["ocr_seiten"]:
        _melde(meldungen, warnungen, "warnung", "OCR_GELESEN",
               f"{ergebnis['ocr_seiten']} Seite(n) per OCR gelesen. OCR kann sich verlesen — Ergebnis bitte "
               f"besonders sorgfältig prüfen!")
    if abbruch is not None and abbruch.is_set():
        return abgebrochen()
    if melde:
        melde(f"   Erkennung läuft: {pdf_pfad.name} …")
    ergebnis["funde"] = _analysiere_dokument(dok, aktive, whitelist, immer_schwaerzen, profil=profil,
                                             kundenliste=kundenliste, lauf=lauf, hinweise=hinweise,
                                             warnungen=warnungen, meldungen=meldungen)
    if lauf is not None and hasattr(lauf, "aufnehmen"):
        lauf.aufnehmen(ergebnis)
    if "namen" in aktive and lade_ner() is None:
        _melde(meldungen, warnungen, "warnung", "NAMEN_INAKTIV",
               "Namenserkennung inaktiv: " + (ner_fehler() or "Modell fehlt."))
    return ergebnis


# ----------------------------------------------------------------------
# Weitergabe zwischen den Dokumenten eines Laufs
# ----------------------------------------------------------------------
def _belegte_stellen(funde) -> dict:
    belegt: dict = {}
    for f in funde:
        for st in f.get("stellen", []):
            belegt.setdefault(st["seite"], []).append((st["start"], st["ende"]))
    for liste in belegt.values():
        liste.sort()
    return belegt


def _ueberlappt(belegt: dict, seite: int, s: int, e: int) -> bool:
    liste = belegt.get(seite, [])
    i = bisect_right(liste, (s, float("inf")))
    for j in (i - 1, i):
        if 0 <= j < len(liste) and liste[j][0] < e and s < liste[j][1]:
            return True
    return any(a < e and s < b for a, b in liste[max(0, i - 3):i + 3])


def _naechstes_pseudonym(funde) -> str:
    vergeben = set()
    for f in funde:
        m = re.fullmatch(r"\[PERSON ([A-Z]|\d+)\]", str(f.get("ersatz") or ""))
        if m:
            w = m.group(1)
            vergeben.add(ord(w) - 65 if len(w) == 1 and w.isalpha() else int(w) - 1)
    i = 0
    while i in vergeben:
        i += 1
    return _pseudonym(i)


def weitergabe_anwenden(ergebnisse: list) -> int:
    """Lauf-übergreifend: Namen und Kennungen aus allen Ergebnissen in allen anderen Dokumenten suchen
    (ganzwort_stellen auf deren Modell) und als neue Stellen/Funde ergänzen (quelle "weitergabe").
    Rückgabe: Anzahl neuer Stellen."""
    gueltig = [e for e in ergebnisse or [] if e and e.get("modell") is not None and not e.get("fehler")]
    neu_gesamt = 0
    for ziel in gueltig:
        dok = ziel["modell"]
        nie = _NieHuellen(dok, ziel.get("nie") or [])
        belegt = _belegte_stellen(ziel["funde"])
        vorhandene = {(f["kategorie"], fund_schluessel(f["text"], modus_fuer(f["kategorie"]))): f
                      for f in ziel["funde"]}
        for quelle in gueltig:
            if quelle is ziel:
                continue
            for fund in list(quelle["funde"]):
                kategorie = fund["kategorie"]
                modus = modus_fuer(kategorie)
                if kategorie == "begriff" or (kategorie != "namen" and modus != "kennung"):
                    continue
                if fund.get("anzeige") == ANZEIGE_BESTANDTEIL:
                    continue          # Bestandteile nur mit ihrer Person (Mehrdeutigkeit)
                texte = list(dict.fromkeys([fund["text"]] + [st.get("text") or "" for st in fund.get("stellen", [])
                                                             if st.get("an", True)]))
                neue = []
                for t in texte:
                    if not t.strip():
                        continue
                    for s, e in ganzwort_stellen(dok, t, modus):
                        if nie.umhuellt(s, e):
                            continue
                        for nr, ls, le in dok.lokal(s, e):
                            if _ueberlappt(belegt, nr, ls, le):
                                continue
                            neue.append({"seite": nr, "start": ls, "ende": le, "an": True,
                                         "text": dok.seiten[nr].text[ls:le]})
                            belegt.setdefault(nr, []).append((ls, le))
                            belegt[nr].sort()
                if not neue:
                    continue
                neue.sort(key=lambda st: (st["seite"], st["start"]))
                schl = (kategorie, fund_schluessel(fund["text"], modus))
                ziel_fund = vorhandene.get(schl)
                if ziel_fund is None:
                    ersatz = fund.get("ersatz") or _platzhalter(kategorie)
                    if kategorie == "namen":
                        ersatz = _naechstes_pseudonym(ziel["funde"])
                    erste = neue[0]
                    g = dok.global_(erste["seite"], erste["start"])
                    ziel_fund = {"id": f"f{len(ziel['funde']) + 1}", "kategorie": kategorie,
                                 "anzeige": fund.get("anzeige") or _anzeige(kategorie), "text": erste["text"],
                                 "ersatz": ersatz, "seiten": [], "anzahl": 0,
                                 "kontext": _kontext_text(dok.text, g, g + len(erste["text"])),
                                 "stellen": [], "quellen": ["weitergabe"], "sicherheit": fund.get("sicherheit", 0.5),
                                 "hinweis": "aus einem anderen Dokument dieses Laufs übernommen"}
                    ziel["funde"].append(ziel_fund)
                    vorhandene[schl] = ziel_fund
                elif "weitergabe" not in ziel_fund.get("quellen", []):
                    ziel_fund["quellen"] = sorted(set(ziel_fund.get("quellen", [])) | {"weitergabe"})
                ziel_fund["stellen"] = sorted(ziel_fund.get("stellen", []) + neue,
                                              key=lambda st: (st["seite"], st["start"]))
                ziel_fund["anzahl"] = len(ziel_fund["stellen"])
                if not dok.aus_text:
                    ziel_fund["seiten"] = sorted({st["seite"] + 1 for st in ziel_fund["stellen"]})
                neu_gesamt += len(neue)
    return neu_gesamt
