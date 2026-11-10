"""Analyse: Text und PDFs nach personenbezogenen Daten durchsuchen (Vertrag Phase 2, Abschnitte 2–4).

Ablauf:
  1. Seitenmodell bauen (seitenmodell.dokument_vorbereiten + dokument_aufbauen; Scans per OCR) –
     dasselbe Modell benutzen Schwärzung und Selbstkontrolle.
  2. Alle passenden Detektoren laufen lassen (detektoren.alle_treffer) -> Treffer mit Offsets. Dazu laufen
     die Hinweis-Kategorien der Schutzstufe (muster.hinweis_kategorien: Gesundheitsdaten in „hoch“ und
     „ausgewogen“, sofern nicht selbst angehakt) – ihre Funde werden nur angeboten (alle Stellen abgewählt).
  3. NIE-Liste: Ganzphrasen-Vorkommen sind Schutzhüllen – Treffer darin entfallen (auch Bruchstücke wie
     eine "Telefonnummer" mitten in der freigegebenen eigenen IBAN). Einträge mit Ziffern (IBAN, Nummern)
     gelten auch mit anderem Leerraum ("DE89 3704 …" gibt "DE893704…" frei und umgekehrt). Namens-Treffer, die
     ganz aus Diagnosen/Medikamenten der Wissensbasis bestehen („Distale Radiusfraktur“), entfallen.
  4. Weitergabe: jeder Treffertext an ALLEN Ganzwort-Stellen des Dokuments (Vergleichsmodus je Kategorie;
     bei Namen alle Schreibweisen), dazu Namensbestandteile (Vor-, Nach-, Doppelnamensteile).
  5. Überlappende Stellen zusammenführen: die umfassende Stelle gewinnt (Bruchstücke gehen in ihr auf);
     bei gleicher Spanne entscheidet die Kategorie-Priorität (IMMER-Begriff > Kennungen > Namen >
     Adresse > Rest); teilweise Überlappung -> Vereinigung, Kategorie nach Priorität. Stellen der
     Gesundheitskategorien (angeboten oder angehakt) und der übrigen Hinweis-Kategorien werden getrennt
     zusammengeführt: sie schlucken nie eine andere Stelle (ein Name in „Diabetes bei Herrn Meier“ behält seine
     eigene, angehakte Stelle – auch in „maximal“, wo die Nutzerin die Diagnose abwählen kann, damit sie lesbar
     bleibt) und entfallen, wo eine andere Stelle sie ganz überdeckt.
  6. Funde bilden (Format v2: id, stellen, quellen, sicherheit, hinweis; alte Schlüssel bleiben) mit festen
     Pseudonymen je Person. Hinweise: Gesundheitsdaten (abgewählt angeboten; „möglicherweise“, wenn nur
     allgemeine Fachbegriffe ohne Personenbezug erkannt sind – Quelle "….vermutet"), Prüfziffer ungültig
     (Quelle "….lesefehler", muster.quellen_hinweis), nur als Namensbestandteil erkannt.
  Runde 2: Auf OCR-Seiten zählen auch leicht verlesene Vorkommen eines bestätigten Werts (gleiche Wortzahl und
  Ziffern, Abstand <= Länge/7: 'Birkanallea 40' für 'Birkenallee 40'). Ein Name in einer Stelle einer anderen
  Kategorie („Meier“ in „Meier Bau GmbH“) behält eine eigene Stelle. Ein Titel ohne Namen (Formularfeld „Titel“:
  „Dipl.-Ing.“) wird nur an seiner Stelle geschwärzt ([TITEL]) und ist keine Person – nie aber ein Wort, das die
  Wissensbasis als Vor- oder Nachnamen kennt („Graf“, „Ritter“, „Kaplan“, „Pastor“: das bleibt eine Person).
  Firmenanschriften, die die Strukturregeln stehen lassen, werden abgewählt angeboten („vermutlich
  Firmenanschrift“) – außer im Absender einer Person (eigener Briefkopf von Selbständigen, Fußzeile eines
  Privatbriefs) oder wenn ein anderes Dokument des Laufs dieselbe Anschrift als Kundenanschrift angehakt hat.
  Vor dem Seitenmodell: keine PDF (Bild/Webseite mit Endung .pdf) -> klare Meldung statt Absturz (R-01); jedes Objekt
  einmal geladen, damit MuPDF eine nötige Reparatur JETZT ausführt und nicht erst nach Änderungen -> DATEI_REPARIERT
  (R-11); beschädigte Bilder (abgebrochenes JPEG) -> BILD_BESCHAEDIGT (R-07); Nebenkanäle mit denselben Detektoren
  geprüft (auch Skripte, Link-Ziele, Seitenbeschriftungen, XMP an Seiten und Bildern; Werte in Dateinamen-
  Schreibweise als Wörter; Programmfelder nur auf Personennamen) -> „nebenkanaele“, NEBENKANAL_FUND (R-04; ein
  Hinweis, wenn auf den Seiten ohnehin geschwärzt wird). Nach dem Seitenmodell: „kaum lesbar“ (weniger als 25
  OCR-Wörter) bleibt nur eine Warnung, wenn die Lesung schlecht ist oder die Tinte nicht zu den Wörtern passt
  (scan_kaum_lesbar, dieselbe Regel wie der _PRUEFEN-Grund der Schwärzung); sonst Hinweis WENIG_TEXT. Meldungen, die
  die Ausgabe _PRUEFEN machen, stehen am Modell (dok.leckrelevant, R-07).

Öffentlich: analysiere_pdf, analysiere_text, weitergabe_anwenden, LaufWissen, hinweis_kategorien,
gesundheit_nur_vermutet, ANZEIGE_BEGRIFF, PLATZHALTER_BEGRIFF, HINWEIS_GESUNDHEIT, HINWEIS_GESUNDHEIT_VERMUTET,
keine_pdf_meldung, datei_repariert, reparatur_erzwingen, bild_schaeden, scan_kaum_lesbar, tintenanteil,
KAUM_LESBAR_WOERTER, nebenkanaele_pruefen, NEBENKANAELE_LEER, HINWEIS_FIRMENANSCHRIFT, HINWEIS_ABSENDER,
ANZEIGE_TITEL.
"""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from pathlib import Path
from typing import NamedTuple

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import detektoren
from . import muster as _muster
from . import nebenkanaele as _nebenkanaele
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


def _zum_hinweis(meldungen, warnungen, hinweise, code):
    """Warnungen mit diesem Code zu Hinweisen machen (Text wandert von den Warnungen zu den Hinweisen)."""
    for m in meldungen or ():
        if m.get("code") != code or m.get("art") != "warnung":
            continue
        m["art"] = "hinweis"
        if warnungen is not None and m["text"] in warnungen:
            warnungen.remove(m["text"])
        if hinweise is not None and m["text"] not in hinweise:
            hinweise.append(m["text"])


# ----------------------------------------------------------------------
# Hinweis-Kategorien der Schutzstufe (Gesundheitsdaten in „hoch“/„ausgewogen“) und Fund-Hinweise
# ----------------------------------------------------------------------
HINWEIS_GESUNDHEIT = "Gesundheitsdaten (Art. 9 DSGVO) – angeboten, nicht angehakt"
HINWEIS_GESUNDHEIT_VERMUTET = ("möglicherweise Gesundheitsdaten (Art. 9 DSGVO): nur ein Fachbegriff, ohne Etikett "
                               "„Diagnose:“, ICD-Code oder Bezug zu einer Person – angeboten, nicht angehakt")
HINWEIS_ANGEBOTEN = "angeboten, nicht angehakt"
HINWEIS_BESTANDTEIL = "nur als Namensbestandteil erkannt"
HINWEIS_WEITERGABE = "aus einem anderen Dokument dieses Laufs übernommen"
_GESUNDHEIT_ANZEIGE = {"diagnose": "Diagnosen", "medikament": "Medikamente"}
_VERMUTET = ".vermutet"                 # Quellen-Endung der Detektoren: nur vermutet (wissen.gesundheit.vermutet)
_NEUTRALE_QUELLEN = {"weitergabe", "weitergabe.aehnlich"}   # Weitergabe im Dokument: erbt die Art der übrigen Quellen
# Angehakte Funde dieser Kategorien zeigen eine Person im Dokument: dann sind auch allgemeine Fachbegriffe
# („Physiotherapie“ in einer Leistungsabrechnung) vermutlich Angaben über sie – die Meldung ist sicher. Anschrift,
# Telefon, IBAN, Nummern zählen nicht (auch Versicherer und Tarifblätter tragen sie).
_PERSONEN_KATEGORIEN = {"namen", "geburt", "svnr", "kvnr", "steuerid", "ausweis", "kindergeld"}


def hinweis_kategorien(profil, aktive) -> set:
    """Kategorien, die in dieser Schutzstufe erkannt, aber nur abgewählt angeboten werden (muster.hinweis_kategorien:
    Gesundheitsdaten in „hoch“/„ausgewogen“, ohne die selbst angehakten). Leer, wenn muster sie nicht kennt."""
    funktion = getattr(_muster, "hinweis_kategorien", None)
    if funktion is None:
        return set()
    try:
        return set(funktion(profil, set(aktive or ())))
    except Exception:  # unbekanntes Profilformat: nichts nur anbieten (alles Erkannte bleibt wie angehakt)
        return set()


def _gesundheit_kategorien() -> set:
    return set(getattr(_muster, "GESUNDHEIT", _GESUNDHEIT_ANZEIGE))


def _ist_gesundheit(kategorie: str) -> bool:
    return kategorie in _gesundheit_kategorien()


def _nur_vermutet(quellen) -> bool:
    """Beruht eine Stelle/ein Fund nur auf vermuteten Treffern (Quellen-Endung „.vermutet“, dazu höchstens die
    Weitergabe im Dokument)? Dann sind es z. B. nur Leistungsbegriffe einer Tarifübersicht („Physiotherapie“)."""
    eigene = set(quellen or ()) - _NEUTRALE_QUELLEN
    return bool(eigene) and all(q.endswith(_VERMUTET) for q in eigene)


def _angebots_hinweis(kategorie: str, vermutet: bool = False) -> str:
    """Hinweis eines nur angebotenen Funds (alle Stellen abgewählt)."""
    if _ist_gesundheit(kategorie):
        return HINWEIS_GESUNDHEIT_VERMUTET if vermutet else HINWEIS_GESUNDHEIT
    return f"{_anzeige(kategorie)} – {HINWEIS_ANGEBOTEN}"


def gesundheit_nur_vermutet(fund: dict) -> bool:
    """Für die Oberfläche: ist ein Fund eine nur vermutete, angebotene Gesundheitsangabe (allgemeiner Fachbegriff
    ohne Etikett, ICD-Code, Dosierung oder Personenbezug – z. B. „Physiotherapie“ in einer Tarifübersicht)?"""
    return HINWEIS_GESUNDHEIT_VERMUTET in str(fund.get("hinweis") or "").split("; ")


def _gesundheit_meldungstext(kategorien, beispiel: str | None = None) -> str:
    """Meldung GESUNDHEITSDATEN. `beispiel`: Text eines nur vermuteten Funds, wenn ALLE angebotenen Gesundheitsfunde
    nur vermutet sind – dann vorsichtiger („möglicherweise“)."""
    arten = [_GESUNDHEIT_ANZEIGE.get(k, _anzeige(k)) for k in sorted(kategorien, key=_rang)]
    welche = f" ({', '.join(dict.fromkeys(arten))})" if arten else ""
    if beispiel is None:
        return (f"Das Dokument enthält Gesundheitsdaten{welche}. Gesundheitsdaten sind nach Art. 9 DSGVO besonders "
                f"geschützt. Sie stehen in der Fundliste, sind aber nicht angehakt und bleiben deshalb lesbar. Zum "
                f"Schwärzen bitte anhaken – oder die Schutzstufe „Maximal“ wählen.")
    kurz = _normalisiert(beispiel)
    kurz = kurz if len(kurz) <= 40 else kurz[:39] + "…"
    return (f"Das Dokument enthält möglicherweise Gesundheitsdaten{welche}: erkannt wurden nur Fachbegriffe wie "
            f"„{kurz}“ – ohne Etikett wie „Diagnose:“, ohne ICD-Code und ohne erkennbaren Bezug zu einer Person "
            f"(in Tarif- und Leistungsübersichten sind das meist nur Leistungen). Gesundheitsdaten sind nach Art. 9 "
            f"DSGVO besonders geschützt. Sie stehen in der Fundliste, sind aber nicht angehakt und bleiben lesbar. "
            f"Sind es Angaben über eine Person, bitte anhaken – oder die Schutzstufe „Maximal“ wählen.")


_ANREDE_DAVOR_RE = re.compile(r"(?<![\wäöüß])(?:Herrn?|Frau|Hr\.|Fr\.|Dr\.|Prof\.)[ \t]+$")
_WORT_RE = re.compile(r"[^\W\d_][\w'’\-]*")


def _gesundheitsbegriff_als_name(wissen, text: str, t) -> bool:
    """Ein Namens-Treffer, der ganz aus Diagnosen/Medikamenten der Wissensbasis besteht („Distale Radiusfraktur“ als
    Tabellenzelle), ist ein Fehltreffer – sonst schwärzte er einen Teil einer abgewählten, also lesbar gewollten
    Diagnose als [PERSON …]. Ausnahmen: Kundenliste, bekannter Vor-/Nachname („Krebs“) und Anrede davor."""
    if t.kategorie != "namen" or t.quelle == "kundenliste" or wissen is None:
        return False
    wort = text[t.start:t.ende]
    try:
        if not any(wissen.index(liste).deckt_ab(wort) for liste in ("diagnosen", "medikamente")):
            return False
        if any(wissen.ist_vorname(w) or wissen.ist_nachname(w) for w in _WORT_RE.findall(wort)):
            return False
    except Exception:  # ältere Wissensbasis ohne diese Funktionen: Treffer behalten
        return False
    return not _ANREDE_DAVOR_RE.search(text[max(0, t.start - 20):t.start])


def _hinweise_verbinden(*hinweise) -> str | None:
    """Mehrere Fund-Hinweise zu einem Text ("; "), ohne Wiederholungen; None, wenn keiner da ist."""
    teile: list = []
    for h in hinweise:
        for t in str(h or "").split("; "):
            t = t.strip()
            if t and t not in teile:
                teile.append(t)
    return "; ".join(teile) or None


def _quellen_hinweise(quellen) -> list:
    """Hinweise zu den Quellen eines Funds ("muster.iban.lesefehler" -> "Prüfziffer ungültig (Lesefehler?)")."""
    funktion = getattr(_muster, "quellen_hinweis", None)
    if funktion is None:
        return []
    return [h for h in (funktion(q) for q in sorted(quellen or ())) if h]


def _geerbte_hinweise(fund: dict) -> list:
    """Hinweise eines Funds, die mit seinem Text in ein anderes Dokument wandern („Prüfziffer ungültig …“)."""
    texte = set(getattr(_muster, "QUELLEN_HINWEISE", {}).values())
    return [h for h in str(fund.get("hinweis") or "").split("; ") if h in texte]


def _alle_abgewaehlt(fund: dict) -> bool:
    stellen = fund.get("stellen") or []
    return bool(stellen) and not any(st.get("an", True) for st in stellen)


def _nicht_weitergeben(fund: dict) -> bool:
    """Funde, die nie in andere Dokumente wandern: Titel ohne Namen (gehören zu keiner Person) und angebotene
    Firmenanschriften (sonst würden sie dort zu angehakten Stellen)."""
    return fund.get("anzeige") == ANZEIGE_TITEL or QUELLE_FIRMENANSCHRIFT in (fund.get("quellen") or ())


class LaufWissen:
    """Dokumentübergreifendes Wissen eines Laufs (für Detektoren und weitergabe_anwenden):
    bekannte Personen (Name -> Pseudonym) und Kennungen der bisher analysierten Dokumente. Nur angebotene Funde
    der Hinweis-Kategorien (Gesundheitsdaten in „hoch“) werden nicht übernommen – sie dürfen in anderen
    Dokumenten nicht als angehakte Kennung wiederkehren."""

    def __init__(self):
        self.personen: dict = {}       # Namensschlüssel -> Pseudonym
        self.kennungen: dict = {}      # (Kategorie, Schlüssel) -> Text

    def aufnehmen(self, ergebnis: dict):
        ergebnis = ergebnis or {}
        nur_hinweis = hinweis_kategorien(ergebnis.get("profil"), ergebnis.get("aktive") or ()) \
            if "aktive" in ergebnis else set()
        for f in ergebnis.get("funde", []):
            if f["kategorie"] in nur_hinweis or _nicht_weitergeben(f):
                continue
            modus = modus_fuer(f["kategorie"])
            schluessel = fund_schluessel(f["text"], modus)
            if f["kategorie"] == "namen":
                self.personen.setdefault(schluessel, f.get("ersatz"))
            elif modus == "kennung":
                self.kennungen.setdefault((f["kategorie"], schluessel), f["text"])


# ----------------------------------------------------------------------
# NIE-Liste als Schutzhüllen
# ----------------------------------------------------------------------
def _ohne_leerraum_stellen(text: str, eintrag: str) -> list:
    """Vorkommen eines Eintrags mit Ziffern, bei denen nur der Leerraum abweicht (Gutachten EQ-19: NIE
    "DE89 3704 0044 0532 0130 00" = "DE89370400440532013000", "123 4567" = "1234567"). Ganzwort wie
    ganzwort_stellen: davor und danach kein Buchstabe/keine Ziffer – "123" passt nicht in "41234" oder "1234"."""
    kompakt = "".join(eintrag.split())
    if sum(1 for c in kompakt if c.isalnum()) < 3:
        return []
    muster = r"\s*".join(re.escape(c) for c in kompakt)
    if kompakt[0].isalnum():
        muster = r"(?<![^\W_])" + muster
    if kompakt[-1].isalnum():
        muster += r"(?![^\W_])"
    return [(m.start(), m.end()) for m in re.finditer(muster, text, re.IGNORECASE)]


class _NieHuellen:
    """NIE-schwärzen-Liste: Ganzwort-/Ganzphrasen-Vorkommen (Mindestlänge 3, Groß-/Kleinschreibung egal,
    Einträge mit Ziffern trennzeichen-flexibel wie Kennungen und unabhängig vom Leerraum: Gutachten EQ-19).
    Jede Stelle, die ganz in einem Vorkommen liegt, bleibt stehen – auch Bruchstücke anderer Kategorien
    (Gutachten KQ-03/KQ-04); ein Vorkommen innerhalb einer längeren Nummer gibt diese nicht frei."""

    def __init__(self, dok, eintraege):
        huellen = []
        text = dok if isinstance(dok, str) else dok.text
        for e in eintraege or []:
            n = _normalisiert(str(e or "")).strip(".,;:")
            if len(n) < 3:
                continue
            if any(c.isdigit() for c in n):
                huellen.extend(ganzwort_stellen(dok, n, "kennung"))
                huellen.extend(_ohne_leerraum_stellen(text, n))
            else:
                huellen.extend(ganzwort_stellen(dok, n, "begriff"))
        huellen = sorted(set(huellen))
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
_ADRESSE_RE = re.compile(r"[^\s@]+@[^\s@]+|(?:https?://|www\.)\S+", re.IGNORECASE)


def _titelwort_ist_name(roh: str, pos: int, anzahl: int) -> bool:
    """Ein Wort aus namen.TITEL bzw. den Namenszusätzen, das hier ein Name ist: groß geschrieben, ohne Punkt und als
    letztes Wort ein bekannter Nachname („Thomas Pastor“, „Ayşe Sen“) bzw. als erstes Wort vor einem weiteren ein
    bekannter Vorname („Phil Graf“, „Jun Kaplan“). „Pastor Müller“, „Dr. phil.“, „Max Müller sen.“ bleiben Titel."""
    kern = roh.strip(",;:()[]\"'")
    if not kern or kern.endswith(".") or not kern[0].isupper():
        return False
    wissen = _wissen_modul()
    if wissen is None:
        return False
    try:
        if pos == anzahl - 1 and wissen.ist_nachname(kern):
            return True
        return pos == 0 and anzahl >= 2 and bool(wissen.ist_vorname(kern))
    except Exception:
        return False


def _name_zerlegen(name: str) -> tuple:
    """(vornamen, nachname) aus einem Namen: Titel/Anreden/Partikel/Suffixe entfernt, 'Nachname, Vorname'
    erkannt. Bei einem einzelnen Wort ist nachname None und das Wort steht in vornamen (Rolle offen)."""
    def tokens(teil):
        aus = []
        liste = teil.split()
        for pos, roh in enumerate(liste):
            t = roh.strip(".,;:()[]\"'")
            if not t:
                continue
            tl, rl = t.lower(), roh.lower()
            if tl in ANREDEN or rl in ANREDEN:
                continue
            if (tl in TITEL or rl in TITEL or rl in _NAMENSSUFFIXE) and not _titelwort_ist_name(roh, pos, len(liste)):
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
    # Position je Teil vor/nach einem Komma („Pastor, Thomas“: „Pastor“ ist dort das letzte Wort seines Teils)
    woerter = [(pos, len(teil), roh) for teil in (t.split() for t in name.split(","))
               for pos, roh in enumerate(teil)]
    for pos, anzahl, roh in woerter:
        t = roh.strip(".,;:()[]\"'")
        teile = [t] + ([x for x in t.split("-") if x] if "-" in t else [])
        for teil in teile:
            if len(teil) < 3:
                continue
            tl, rl = teil.lower(), roh.lower()
            als_name = teil == t and _titelwort_ist_name(roh, pos, anzahl)
            if (tl in TITEL or rl in TITEL or rl in _NAMENSSUFFIXE) and not als_name:
                continue
            if tl in ANREDEN or tl in PARTIKEL or tl in NAMEN_STOPPLISTE:
                continue
            if any(c.isdigit() for c in teil):
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


def _fund_bauen(dok, schluessel, kategorie, stellen_global, quellen, sicherheit, anzeige, ersatz, hinweis,
                ausgelassen=(), an=True):
    """Fund v2. `ausgelassen`: (start, ende, grund) bewusst nicht geschwärzter Vorkommen desselben Texts
    (NIE-Liste, mehrdeutig am Satzanfang, fremdes Bindestrich-Wort) – sie erscheinen als abgewählte Stellen
    (an: False, grund), damit Vorschau und Selbstkontrolle sie kennen und die Nutzerin sie anhaken kann.
    an=False: ein nur angebotener Fund (Hinweis-Kategorie der Schutzstufe) – alle Stellen abgewählt."""
    stellen = []
    for s, e in stellen_global:
        for nr, ls, le in dok.lokal(s, e):
            stellen.append({"seite": nr, "start": ls, "ende": le, "an": bool(an),
                            "text": dok.seiten[nr].text[ls:le]})
    s0, e0 = stellen_global[0]
    erste = stellen[0] if stellen else None
    text = erste["text"] if erste else dok.text[s0:e0]
    seiten = [] if dok.aus_text else sorted({st["seite"] + 1 for st in stellen})
    anzahl = max(1, len(stellen))
    for s, e, grund in ausgelassen:
        for nr, ls, le in dok.lokal(s, e):
            stellen.append({"seite": nr, "start": ls, "ende": le, "an": False, "grund": grund,
                            "text": dok.seiten[nr].text[ls:le]})
    if ausgelassen:
        stellen.sort(key=lambda st: (st["seite"], st["start"]))
    return {"id": "", "kategorie": kategorie, "anzeige": anzeige, "text": text, "ersatz": ersatz,
            "seiten": seiten, "anzahl": anzahl, "kontext": _kontext_text(dok.text, s0, e0),
            "stellen": stellen, "quellen": sorted(quellen), "sicherheit": round(float(sicherheit), 3),
            "hinweis": hinweis}


GRUND_NIE = "NIE-Liste"
GRUND_SATZANFANG = "mehrdeutiges Wort am Satzanfang"
GRUND_KOMPOSITUM = "Teil eines fremden Bindestrich-Worts"
GRUND_TITEL = "derselbe Titel bei einer anderen Person"


# ----------------------------------------------------------------------
# Titel ohne Namen (Formularfeld „Titel“: „Dipl.-Ing.“)
# ----------------------------------------------------------------------
ANZEIGE_TITEL = "Titel"
PLATZHALTER_TITEL = "[TITEL]"
HINWEIS_TITEL = "Titel ohne Namen – nur an dieser Stelle geschwärzt, keine eigene Person"
_TITEL_SCHLUESSEL = "\x00titel:"           # Fund-Schlüssel eines Titels: nie eine Person, nie weitergegeben
_TITEL_FELD_RE = re.compile(r"(?i)^\W*(?:akad(?:emischer|\.)?\s*)?(?:titel|grad|titel\s*/\s*grad|grad\s*/\s*titel)"
                            r"\W*$")


def _bekannter_name(wort: str, wissen) -> bool:
    """Kennt die Wissensbasis das Wort als Vor- oder Nachnamen („Graf“, „Ritter“, „Kaplan“, „Pastor“, „Phil“, „Şen“)?
    Abkürzungen mit Punkt („phil.“, „sen.“) sind nie Namen."""
    kern = wort.strip(",;:()[]\"'")
    if not kern or kern.endswith(".") or wissen is None:
        return False
    try:
        return bool(wissen.ist_nachname(kern) or wissen.ist_vorname(kern))
    except Exception:
        return False


def _nur_titel(text: str, wissen=None, feld: bool = False) -> bool:
    """Besteht der Text nur aus Titeln („Dipl.-Ing.“, „Dr. med.“, „Prof. Dr.“, auch mit Anrede: „Herrn Dr.“)?

    Nie, wenn ein Wort ein bekannter Vor- oder Nachname ist: „Graf“, „Ritter“, „Herzog“, „Kaplan“, „Fürst“, „Pastor“
    stehen in der Liste der Anreden und Titel, sind aber häufige Nachnamen – „Herr Graf“ oder „Frau Kaplan“ bleibt eine
    Person (Befund Punkt 9: sonst wurde der Nachname nur an einer Stelle geschwärzt). Erst die Namensprüfung, dann die
    Titel: namen.TITEL enthält auch „pastor“. Ein Treffer der Erkennung zählt nur mit den festen Titeln aus namen.TITEL
    und Titel-Abkürzungen mit Punkt; nur im Formularfeld „Titel“ (feld=True) auch die übrigen Titel der Wissensbasis
    („Mag. phil.“, „Dipl.-Ing. (FH)“, „Rechtsanwältin“). Reine Anreden ohne Titel („An Herrn“) sind kein Titel."""
    teile = [t for t in re.split(r"\s+", (text or "").strip()) if t]
    if not teile:
        return False
    titel = False
    for t in teile:
        tl = t.lower().rstrip(",;:")
        if tl in ANREDEN:
            continue
        if _bekannter_name(t, wissen):
            return False
        if tl in TITEL:
            titel = True
            continue
        try:
            wissens_titel = wissen is not None and wissen.ist_anrede_titel(t)
        except Exception:
            wissens_titel = False
        if wissens_titel and (feld or "." in tl or tl.startswith("(")):
            titel = True                  # Abkürzung („Dipl.Ing“, „Mag.“) – ein Name trägt keinen Punkt
            continue
        return False
    return titel


def _feldname_lesbar(name: str) -> str:
    n = re.sub(r"^(?:f|fld|feld|field|txt|text|tf)[_\-.]", "", name or "", flags=re.IGNORECASE)
    n = re.sub(r"[_\-.]\d+(?=[_\-.]|$)", "", n)
    return " ".join(re.sub(r"[_\-.\[\]\d]+", " ", n).split())


def _titel_felder(dok, wissen=None) -> list:
    """(start, ende) im Dokumenttext: Werte von Formularfeldern „Titel“ / „akad. Grad“, die nur aus Titeln bestehen.
    Ein Titel gehört zur Person des Formulars, ist aber selbst kein Name: er wird nur an dieser Stelle geschwärzt
    (Platzhalter [TITEL]) – nie als eigene Person, die dann die Titel anderer Personen mitnähme."""
    aus = []
    for feld in getattr(dok, "felder", None) or ():
        try:
            if feld.start < 0 or feld.ende <= feld.start or not (0 <= feld.seite < len(dok.seiten)):
                continue
            if not (_TITEL_FELD_RE.match((feld.etikett or "").strip())
                    or _TITEL_FELD_RE.match(_feldname_lesbar(feld.name))):
                continue
            seite_text = dok.seiten[feld.seite].text
            s, e = feld.start, feld.ende
            while s < e and seite_text[s].isspace():
                s += 1
            while e > s and seite_text[e - 1].isspace():
                e -= 1
            if e > s and _nur_titel(seite_text[s:e], wissen, feld=True):
                aus.append((dok.global_(feld.seite, s), dok.global_(feld.seite, e)))
        except Exception:
            continue
    return aus


# ----------------------------------------------------------------------
# Firmenanschriften der Strukturregeln: abgewählt angeboten
# ----------------------------------------------------------------------
HINWEIS_FIRMENANSCHRIFT = "vermutlich Firmenanschrift – nicht geschwärzt, bitte prüfen"
QUELLE_FIRMENANSCHRIFT = "struktur.firmenanschrift"
# Befund Punkt 6: Die Strukturregeln werten eine Webadresse oder „Bankverbindung“ im Briefkopf bzw. in der Fußzeile als
# Firmenbeleg – bei Selbständigen (Fotograf, Handwerker, Praxis) und in Privatbriefen ist das aber die Anschrift der
# Kundin bzw. des Kunden. Steht die Anschrift in einer Absenderzeile oder einem Absenderblock, der mit dem Namen einer
# Person beginnt („Max Mustermann · Hauptstraße 12 · 10115 Berlin“, „Max Mustermann · Fotografie“ darüber,
# „Vollmachtgeber: Max Mustermann, Hauptstraße 12 …“), wird sie wie jede Kundenanschrift geschwärzt.
HINWEIS_ABSENDER = "Anschrift einer Person im Absender bzw. Briefkopf – geschwärzt"
QUELLE_ABSENDER = "struktur.absender"
HINWEIS_LAUF_KUNDENANSCHRIFT = "in einem anderen Dokument dieses Laufs als Kundenanschrift geschwärzt"
_ABSENDER_ETIKETT_RE = re.compile(
    r"(?i)^\W*(?:(?:absender(?:in)?|von|vollmachtgeber(?:in)?|antragsteller(?:in)?|versicherungsnehmer(?:in)?|"
    r"kunde|kundin|name|inhaber(?:in)?|inh\.)\s*:?\s*)?(?:(?:herrn?|frau|dr\.|prof\.)\s+)*$")
_SEGMENT_TRENNER_RE = re.compile(r"\s+[·•|–—-]\s+|\s*[·•|,;\t]\s*")
_ABSENDER_ZEILEN_DARUEBER = 3
# Berufs- und Betriebswörter vor dem Namen im ersten Segment („Physiotherapie Anna Schmidt“, „Malermeister Max
# Mustermann“) sind erlaubt, Rollen in einer Firma nicht („Vorstand Dr. Hans Müller“, „Ansprechpartner Max Schmidt“)
_ROLLEN_RE = re.compile(r"(?i)vorstand|aufsicht|geschäftsf|vorsitz|ansprech|sachbearb|bearbeit|berater|prokur|"
                        r"direkt|leiter|kontakt|vertret|vermittl|makler|mitarbeit|team|abteilung|referent|sekretar")


def _firmenbeleg(text: str) -> bool:
    """Firmenbeleg einer Zeile (Rechtsform, Organisationswort, Erlaubnisliste) – dieselbe Regel wie die Strukturregeln."""
    try:
        from .detektoren.struktur_adresse import firmen_beleg
        return bool(firmen_beleg(text))
    except Exception:
        return bool(re.search(r"(?<![\wäöüß])(?:GmbH|AG|KG|OHG|GbR|SE|eG|e\.V\.|VVaG|mbH|UG)(?![\wäöüß])", text))


def _person_vorn(seite, zeile, namen: list) -> bool:
    """Beginnt die Zeile mit dem Namen einer Person (angehakte Namensstelle) – höchstens nach einem Absender-Etikett
    („Absender:“, „Vollmachtgeber:“), einer Anrede oder bis zu drei Berufs-/Betriebswörtern („Physiotherapie“) – und
    endet das erste Segment (bis „·“, „,“, „|“) mit diesem Namen, ohne Ziffern und ohne Firmenbeleg? Rollen in einer
    Firma („Vorstand:“, „Ansprechpartner“) zählen nicht."""
    text = seite.text
    wissen = _wissen_modul()
    for s, e in namen:
        if not (zeile.start <= s < zeile.ende):
            continue
        if not any(_bekannter_name(w, wissen) for w in _BUCHSTABEN_WORT_RE.findall(text[s:e])):
            continue                      # kein bekannter Vor- oder Nachname (z. B. eine verlesene Firmenzeile)
        davor = text[zeile.start:s]
        if _SEGMENT_TRENNER_RE.search(davor):
            continue                      # der Name steht nicht im ersten Segment
        if not _ABSENDER_ETIKETT_RE.match(davor):
            woerter = davor.split()
            if (len(woerter) > 3 or any(c.isdigit() or c == ":" for c in davor) or _ROLLEN_RE.search(davor)
                    or not all(w[:1].isupper() for w in woerter)):
                continue
        m = _SEGMENT_TRENNER_RE.search(text, e, zeile.ende)
        segment_ende = m.start() if m else zeile.ende
        segment = text[zeile.start:segment_ende]
        if segment_ende - e > 2 or any(c.isdigit() for c in segment) or _firmenbeleg(segment):
            continue
        return True
    return False


def _zeilen_darueber(seite, zeile, anzahl: int) -> list:
    """Bis zu `anzahl` Zeilen direkt über der Zeile (gleiche Spalte, kleine Lücken), nächste zuerst."""
    aus, aktuell = [], zeile

    def passt(z, a) -> bool:
        h = max(a.rect.height, z.rect.height, 4.0)
        if z.id == a.id or z.rect.y1 > a.rect.y0 + 0.4 * h or a.rect.y0 - z.rect.y1 > 1.2 * h:
            return False
        if not (z.rect.x0 < a.rect.x1 and z.rect.x1 > a.rect.x0):
            return False
        mitte_z, mitte_a = (z.rect.x0 + z.rect.x1) / 2, (a.rect.x0 + a.rect.x1) / 2
        return abs(z.rect.x0 - a.rect.x0) <= 3 * h or abs(mitte_z - mitte_a) <= 3 * h   # bündig oder zentriert
    for _ in range(anzahl):
        oben = [z for z in seite.zeilen if passt(z, aktuell)]
        if not oben:
            break
        aktuell = max(oben, key=lambda z: z.rect.y1)
        aus.append(aktuell)
    return aus


def _absender_einer_person(dok, s: int, e: int, namen_je_seite: dict) -> bool:
    """Steht die Anschrift (globale Spanne) in einer Absenderzeile einer Person oder in einem Block, dessen Kopfzeile
    mit dem Namen einer Person beginnt (ohne Firmenzeile dazwischen)?"""
    for nr, ls, _le in dok.lokal(s, e):
        seite = dok.seiten[nr]
        namen = namen_je_seite.get(nr)
        if not namen:
            continue
        zeile = seite.zeile_von(ls)
        if zeile is None:
            continue
        if _person_vorn(seite, zeile, namen):
            return True
        for oben in _zeilen_darueber(seite, zeile, _ABSENDER_ZEILEN_DARUEBER):
            zeilentext = seite.text[oben.start:oben.ende]
            if _person_vorn(seite, oben, namen):
                return True
            if _firmenbeleg(zeilentext) or len(zeilentext.split()) > 8:
                break                     # Firmenzeile oder Satz: kein Absenderblock einer Person
    return False


def _firmenanschriften(dok, funde: list, aktive: set) -> list:
    """Firmenanschriften, die die Strukturregeln stehen lassen (dok.struktur_vorschlaege: Briefkopf, Fußzeile einer
    unbekannten Firma), als Funde mit lauter abgewählten Stellen: die Nutzerin sieht sie in der Liste und kann sie
    anhaken; die Restrisiko-Prüfung meldet abgewählte Stellen nicht als Verdacht. Vorschläge, die eine vorhandene
    Stelle berühren, entfallen. Steht eine solche Anschrift im Absender einer Person (siehe _absender_einer_person),
    ist es die Anschrift der Kundin bzw. des Kunden: dann ein normaler, angehakter Fund (HINWEIS_ABSENDER)."""
    vorschlaege = getattr(dok, "struktur_vorschlaege", None) or []
    if not vorschlaege:
        return []
    belegt: dict = {}
    namen_je_seite: dict = {}
    for f in funde:
        person = (f.get("kategorie") == "namen" and f.get("anzeige") != ANZEIGE_TITEL)
        for st in f.get("stellen") or ():
            belegt.setdefault(st["seite"], []).append((st["start"], st["ende"]))
            if person and st.get("an", True):
                namen_je_seite.setdefault(st["seite"], []).append((st["start"], st["ende"]))
    for liste in belegt.values():
        liste.sort()
    gruppen: dict = {}
    for v in vorschlaege:
        try:
            kategorie, s, e = v.get("kategorie"), int(v["start"]), int(v["ende"])
        except (TypeError, ValueError, KeyError):
            continue
        if kategorie not in aktive or not (0 <= s < e <= len(dok.text)):
            continue
        if any(_ueberlappt(belegt, nr, ls, le) for nr, ls, le in dok.lokal(s, e)):
            continue
        schl = (kategorie, fund_schluessel(dok.text[s:e], modus_fuer(kategorie)))
        if schl[1]:
            gruppen.setdefault(schl, set()).add((s, e))
    neue = []
    for schl, spannen in gruppen.items():
        if any(_absender_einer_person(dok, s, e, namen_je_seite) for s, e in spannen):
            neue.append(_fund_bauen(dok, schl, schl[0], sorted(spannen), {QUELLE_ABSENDER}, 0.6, _anzeige(schl[0]),
                                    _platzhalter(schl[0]), HINWEIS_ABSENDER))
            continue
        neue.append(_fund_bauen(dok, schl, schl[0], sorted(spannen), {QUELLE_FIRMENANSCHRIFT}, 0.3,
                                _anzeige(schl[0]), _platzhalter(schl[0]), HINWEIS_FIRMENANSCHRIFT, an=False))
    return neue


# ----------------------------------------------------------------------
# Weitere Vorkommen auf OCR-Seiten: leicht verlesene Werte
# ----------------------------------------------------------------------
AEHNLICH_MIN_ZEICHEN = 8         # nur Werte ab 8 Zeichen
AEHNLICH_TEILER = 7              # Editierabstand höchstens Länge/7 ('Birkanallea 40' für 'Birkenallee 40')
QUELLE_AEHNLICH = "weitergabe.aehnlich"
_RANDZEICHEN = ".,;:!?()[]{}<>\"'„“‚‘«»"


def _abstand(a: str, b: str, grenze: int) -> int:
    """Editierabstand (Levenshtein); grenze + 1, sobald er sicher größer als grenze ist."""
    if abs(len(a) - len(b)) > grenze:
        return grenze + 1
    vorher = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        jetzt = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            jetzt[j] = min(vorher[j] + 1, jetzt[j - 1] + 1, vorher[j - 1] + (ca != cb))
        if min(jetzt) > grenze:
            return grenze + 1
        vorher = jetzt
    return vorher[-1]


def _ocr_zeilen(dok):
    """(start, ende) im Dokumenttext aller Zeilen, die die OCR gelesen hat (Scan-Seiten und Bildbereiche)."""
    for nr, seite in enumerate(dok.seiten):
        ids = {zid for b in seite.bloecke if b.quelle != "text" for zid in b.zeilen}
        if not ids:
            continue
        basis = dok.seiten_start[nr]
        for z in seite.zeilen:
            if z.id in ids and z.ende > z.start:
                yield basis + z.start, basis + z.ende


def _aehnliche_stellen(dok, werte) -> dict:
    """Weitere Vorkommen bestätigter Werte in OCR-Zeilen, die die OCR leicht verlesen hat: gleiche Wortzahl, gleiche
    Ziffern, mindestens AEHNLICH_MIN_ZEICHEN Zeichen, Editierabstand höchstens Länge/AEHNLICH_TEILER (ohne Groß-/
    Kleinschreibung). Nur Werte mit Buchstaben und mindestens zwei Wörtern (oder E-Mail-Adressen): ein einzelnes
    Wort liegt zu oft nah an einem gewöhnlichen Wort („Schreiber“/„Schreiben“). werte: [(Schlüssel, Text)];
    Rückgabe {Schlüssel: [(start, ende)]}."""
    vorbereitet = []
    for schl, wert in werte:
        norm = " ".join(str(wert).split())
        grenze = len(norm) // AEHNLICH_TEILER
        anzahl = norm.count(" ") + 1
        if (len(norm) < AEHNLICH_MIN_ZEICHEN or grenze < 1 or sum(c.isalpha() for c in norm) < 4
                or (anzahl < 2 and "@" not in norm)):
            continue
        vorbereitet.append((schl, norm.casefold(), anzahl, re.sub(r"\D", "", norm), grenze))
    aus: dict = {}
    if not vorbereitet:
        return aus
    text = dok.text
    for zs, ze in _ocr_zeilen(dok):
        woerter = [(zs + m.start(), zs + m.end()) for m in re.finditer(r"\S+", text[zs:ze])]
        for schl, norm, anzahl, ziffern, grenze in vorbereitet:
            for i in range(len(woerter) - anzahl + 1):
                s, e = woerter[i][0], woerter[i + anzahl - 1][1]
                while s < e and text[s] in _RANDZEICHEN:
                    s += 1
                while e > s and text[e - 1] in _RANDZEICHEN:
                    e -= 1
                kandidat = " ".join(text[s:e].split()).casefold()
                if norm in kandidat or abs(len(kandidat) - len(norm)) > grenze:
                    continue                  # genaue Vorkommen findet schon die Ganzwort-Suche
                if re.sub(r"\D", "", kandidat) != ziffern:
                    continue
                if _abstand(kandidat, norm, grenze) <= grenze:
                    aus.setdefault(schl, []).append((s, e))
    return aus


def _analysiere_dokument(dok, aktive, whitelist, immer_schwaerzen, profil="hoch", kundenliste=None,
                         lauf=None, hinweise=None, warnungen=None, meldungen=None, angebote=True) -> list:
    """Kern der Analyse auf einem Seitenmodell. Liefert die Funde (Format v2).

    Hinweis-Kategorien der Schutzstufe (Gesundheitsdaten in „hoch“/„ausgewogen“, sofern nicht selbst angehakt)
    werden mit erkannt, ihre Funde aber nur angeboten: alle Stellen an: False, Hinweis HINWEIS_GESUNDHEIT und
    eine Meldung GESUNDHEITSDATEN je Dokument – vorsichtiger („möglicherweise“, HINWEIS_GESUNDHEIT_VERMUTET), wenn
    alle nur auf allgemeinen Fachbegriffen beruhen und das Dokument keine Person nennt (Tarifübersicht). In
    „maximal“ sind sie aktiv und werden normal geschwärzt – getrennt zusammengeführt, damit ein Name darin seine
    eigene Stelle behält.
    angebote=False (reine Text-Schnittstelle ohne Schutzstufe): nur die aktiven Kategorien, nichts angeboten."""
    hinweise = [] if hinweise is None else hinweise
    text = dok.text
    aktive = set(aktive)
    nur_hinweis = hinweis_kategorien(profil, aktive) if angebote else set()
    kontext = Kontext(aktive | nur_hinweis, profil, whitelist, immer_schwaerzen, wissen=_wissen_modul(),
                      kundenliste=kundenliste, lauf=lauf)
    fehler: list = []
    treffer = detektoren.alle_treffer(dok, kontext, fehler)
    for f in list(detektoren.LADEFEHLER) + fehler:
        _melde(meldungen, warnungen, "warnung", "ERKENNUNG_FEHLER",
               f"{f} – diese Regel hat nichts erkannt, Ergebnis bitte besonders sorgfältig prüfen!")

    # 1) NIE-Liste: Treffer in einer Schutzhülle entfallen (IMMER-Begriffe nicht); Namens-Treffer, die nur aus
    #    Diagnosen/Medikamenten bestehen, sind Fehltreffer (_gesundheitsbegriff_als_name)
    nie = _NieHuellen(dok, whitelist)
    behalten = []
    frei_spannen = set()
    titel = []                            # (start, ende, Quelle, Sicherheit): Titel ohne Namen, keine Person
    for t in treffer:
        if t.kategorie != "begriff" and nie.umhuellt(t.start, t.ende):
            frei_spannen.add((t.start, t.ende))
            continue
        if _gesundheitsbegriff_als_name(kontext.wissen, text, t):
            continue
        if t.kategorie == "namen" and _nur_titel(text[t.start:t.ende], kontext.wissen):
            titel.append((t.start, t.ende, t.quelle, t.sicherheit))
            continue
        behalten.append(t)
    if "namen" in aktive:
        titel += [(s, e, "struktur.formularfeld.titel", 0.8) for s, e in _titel_felder(dok, kontext.wissen)
                  if not nie.umhuellt(s, e)]
    freigegeben: dict = {}
    weitestes = -1
    for s, e in sorted(frei_spannen, key=lambda x: (x[0], -x[1])):
        if e <= weitestes:
            continue                  # Bruchstück einer freigegebenen Nummer: nicht eigens melden
        weitestes = e
        freigegeben.setdefault(_normalisiert(text[s:e]), None)
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
    # kleingeschriebene Wörter des Texts (Beleg für Mehrdeutigkeit) – ohne E-Mail-Adressen und URLs, dort ist
    # alles klein ("a.krause@…" macht "Krause" nicht mehrdeutig)
    kleinwoerter = set(_KLEINWORT_RE.findall(_ADRESSE_RE.sub(" ", text))) if namen_treffer else set()
    wissen = kontext.wissen

    def mehrdeutig(wort: str) -> bool:
        w = wort.casefold()
        if w in kleinwoerter or w in _ALLERWELTS_NAMEN:
            return True
        liste = getattr(wissen, "ALLERWELTSWOERTER", None) if wissen is not None else None
        return bool(liste) and w in liste

    def ausschluss(s: int, e: int, wort: str):
        """Weitergabe eines einzelnen Namensworts: nicht als Teil eines fremden Bindestrich-Worts
        ("Kraftfahrt" in "Kraftfahrt-Versicherung"); mehrdeutige Wörter nicht am Satzanfang ohne
        Personenkontext. Liefert den Grund des Ausschlusses oder None."""
        kompositum = _bindestrich_wort(text, s, e)
        if kompositum is not None:
            andere = [p for p in kompositum.split("-") if p and _schluessel(p) != _schluessel(wort)]
            if (fund_schluessel(kompositum, "name") not in personen.zuordnung
                    and not any(_schluessel(p) in personen.namensteile for p in andere)):
                return GRUND_KOMPOSITUM
        if not mehrdeutig(wort):
            return None
        if not _satzanfang(text, s) or _personenkontext(text, s, e, personen.namensteile):
            return None
        return GRUND_SATZANFANG

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
    ausgelassen = []                        # (start, ende, Fund-Schlüssel, Grund)
    for (kategorie, roh), sicherheit in gesucht.items():
        modus = modus_fuer(kategorie)
        schl = schluessel_je_treffer[(kategorie, roh)]
        einzelwort = modus == "name" and len(roh.split()) == 1 and "," not in roh
        for s, e in vorkommen[modus].get(roh, ()):
            if kategorie != "begriff" and nie.umhuellt(s, e):
                ausgelassen.append((s, e, schl, GRUND_NIE))
                continue
            grund = ausschluss(s, e, roh) if einzelwort else None
            if grund:
                ausgelassen.append((s, e, schl, grund))
                continue
            kandidaten.append(_Kandidat(s, e, kategorie, schl, "weitergabe", sicherheit, 1))
    # Auf OCR-Seiten auch leicht verlesene Vorkommen ('Birkanallea 40' für 'Birkenallee 40')
    aehnlich = _aehnliche_stellen(dok, [((kategorie, roh), roh) for kategorie, roh in gesucht])
    for (kategorie, roh), spannen in aehnlich.items():
        for s, e in spannen:
            if kategorie == "begriff" or not nie.umhuellt(s, e):
                kandidaten.append(_Kandidat(s, e, kategorie, schluessel_je_treffer[(kategorie, roh)], QUELLE_AEHNLICH,
                                            gesucht[(kategorie, roh)], 1))
    if "namen" in set(aktive) and personen.bestandteile:
        teile = ganzwort_stellen_viele(dok, [teil for teil, _ in personen.bestandteile], "name")
        for teil, tkey in personen.bestandteile:
            for s, e in teile.get(teil, ()):
                grund = GRUND_NIE if nie.umhuellt(s, e) else ausschluss(s, e, teil)
                if grund:
                    ausgelassen.append((s, e, ("namen", tkey), grund))
                    continue
                kandidaten.append(_Kandidat(s, e, "namen", ("namen", tkey), "bestandteil", 0.5, 2))
    # Titel ohne Namen: nur die eigene Stelle; dieselbe Zeichenfolge anderswo gehört zu anderen Personen und bleibt
    # (als abgewählte Stelle, damit die Selbstkontrolle sie nicht als Rest meldet)
    for s, e, quelle, sicherheit in titel:
        schl = ("namen", _TITEL_SCHLUESSEL + fund_schluessel(text[s:e], "begriff"))
        kandidaten.append(_Kandidat(s, e, "namen", schl, quelle, sicherheit, 0))
        for s2, e2 in ganzwort_stellen(dok, text[s:e], "begriff"):
            if (s2, e2) != (s, e):
                ausgelassen.append((s2, e2, schl, GRUND_TITEL))

    # 4) Überlappende Stellen zusammenführen – Gesundheits- und Hinweis-Kategorien getrennt (siehe
    #    Moduldokumentation): auch eine angehakte Diagnose („maximal“) schluckt keinen Namen, sonst bliebe er nach
    #    dem Abwählen der Diagnose ohne eigene Stelle und ohne Warnung lesbar. Ebenso behält ein Name in einer
    #    anderen Stelle (Arbeitgeber „Meier Bau GmbH“, Ort in „99423 Weimar“) seine eigene Stelle: wählt die Nutzerin
    #    die größere Stelle ab, bleibt der Name trotzdem nie lesbar.
    getrennt = nur_hinweis | (aktive & _gesundheit_kategorien())
    stellen = _zusammenfuehren([k for k in kandidaten if k.kategorie not in getrennt])
    stellen += _eingebettete_namen(stellen, [k for k in kandidaten if k.kategorie == "namen"], personen.zuordnung)
    belegte = sorted((s, e) for s, e, *_ in stellen)         # Stellen, die angehakt geschwärzt werden
    anfaenge = [b[0] for b in belegte]
    max_ende, m = [], -1
    for _, e1 in belegte:
        m = max(m, e1)
        max_ende.append(m)
    if getrennt:
        for st in _zusammenfuehren([k for k in kandidaten if k.kategorie in getrennt]):
            i = bisect_right(anfaenge, st[0])
            if i and belegte[i - 1][1] >= st[1]:
                continue                  # ganz in einer angehakten Stelle: wird ohnehin geschwärzt
            stellen.append(st)

    # 5) Funde
    je_fund: dict = {}
    for s, e, schl, kategorie, quellen, sicherheit, arten, eigene in stellen:
        eintrag = je_fund.setdefault(schl, {"stellen": [], "quellen": set(), "sicherheit": 0.0, "arten": set(),
                                            "kategorie": kategorie, "eigene": set()})
        eintrag["stellen"].append((s, e))
        eintrag["quellen"] |= quellen
        eintrag["sicherheit"] = max(eintrag["sicherheit"], sicherheit)
        eintrag["arten"] |= arten
        eintrag["eigene"] |= eigene
    aus_je_fund: dict = {}
    if ausgelassen:
        gesehen_aus = set()
        for s, e, schl, grund in sorted(ausgelassen, key=lambda a: (a[0], a[1])):
            if schl not in je_fund or (s, e) in gesehen_aus:
                continue
            i = bisect_right(anfaenge, e - 1)
            if i and max_ende[i - 1] > s:
                continue                      # liegt in einer Stelle, die ohnehin geschwärzt wird
            gesehen_aus.add((s, e))
            aus_je_fund.setdefault(schl, []).append((s, e, grund))
    funde = []
    namens_ersatz = personen.pseudonyme(
        [schl[1] for schl, eintrag in sorted(je_fund.items(), key=lambda x: x[1]["stellen"][0])
         if eintrag["kategorie"] == "namen" and not schl[1].startswith(_TITEL_SCHLUESSEL)])
    angeboten = set()                       # Kategorien nur angebotener Funde (Hinweis-Kategorien)
    sicher_angeboten = False                # mindestens ein angebotener Gesundheitsfund, der nicht nur vermutet ist
    vermutet_beispiel = None                # (Start, Text) des ersten nur vermuteten angebotenen Gesundheitsfunds
    vermutete = []                          # diese Funde (Hinweis HINWEIS_GESUNDHEIT_VERMUTET)
    for schl, eintrag in je_fund.items():
        kategorie = eintrag["kategorie"]
        hinweis = None
        if kategorie == "namen" and schl[1].startswith(_TITEL_SCHLUESSEL):
            anzeige, ersatz, hinweis = ANZEIGE_TITEL, PLATZHALTER_TITEL, HINWEIS_TITEL   # keine Person
        elif kategorie == "namen":
            nur_bestandteil = eintrag["arten"] <= {2}
            anzeige = ANZEIGE_BESTANDTEIL if nur_bestandteil else ANZEIGE_NAME
            ersatz = namens_ersatz[schl[1]]
            if nur_bestandteil:
                hinweis = HINWEIS_BESTANDTEIL
        else:
            anzeige = _anzeige(kategorie)
            ersatz = _platzhalter(kategorie)
        nur_angeboten = kategorie in nur_hinweis
        vermutet = nur_angeboten and _ist_gesundheit(kategorie) and _nur_vermutet(eintrag["eigene"])
        if nur_angeboten:
            angeboten.add(kategorie)
            if _ist_gesundheit(kategorie) and not vermutet:
                sicher_angeboten = True
            elif vermutet:
                s0, e0 = min(eintrag["stellen"])
                if vermutet_beispiel is None or s0 < vermutet_beispiel[0]:
                    vermutet_beispiel = (s0, text[s0:e0])
        hinweis = _hinweise_verbinden(_angebots_hinweis(kategorie, vermutet) if nur_angeboten else None, hinweis,
                                      *_quellen_hinweise(eintrag["eigene"]))
        funde.append(_fund_bauen(dok, schl, kategorie, sorted(eintrag["stellen"]), eintrag["quellen"],
                                 eintrag["sicherheit"], anzeige, ersatz, hinweis, aus_je_fund.get(schl, ()),
                                 an=not nur_angeboten))
        if vermutet:
            vermutete.append(funde[-1])
    if vermutete and any(f["kategorie"] in _PERSONEN_KATEGORIEN and any(st["an"] for st in f["stellen"])
                         for f in funde):
        # Personenbezug im Dokument: die Fachbegriffe gelten als sichere Gesundheitsdaten (Hinweis und Meldung)
        for f in vermutete:
            f["hinweis"] = _hinweise_verbinden(*(HINWEIS_GESUNDHEIT if h == HINWEIS_GESUNDHEIT_VERMUTET else h
                                                 for h in f["hinweis"].split("; ")))
        sicher_angeboten = True
    if angebote:
        funde += _firmenanschriften(dok, funde, aktive)

    def erste_stelle(f):
        """Erste angehakte Stelle; bei nur angebotenen Funden die erste Stelle überhaupt (Dokumentreihenfolge)."""
        st = next((st for st in f["stellen"] if st.get("an", True)), None) or next(iter(f["stellen"]), None)
        return (st["seite"], st["start"]) if st else (0, 0)
    funde.sort(key=erste_stelle)
    for i, f in enumerate(funde, 1):
        f["id"] = f"f{i}"
    gesundheit = {k for k in angeboten if _ist_gesundheit(k)}
    if gesundheit:
        beispiel = None if sicher_angeboten or vermutet_beispiel is None else vermutet_beispiel[1]
        _melde(meldungen, hinweise, "hinweis", "GESUNDHEITSDATEN", _gesundheit_meldungstext(gesundheit, beispiel))
    return funde


def _eingebettete_namen(stellen: list, namen: list, zuordnung: dict) -> list:
    """Eigene Stellen für Namen, die beim Zusammenführen in einer Stelle einer ANDEREN Kategorie aufgegangen sind
    („Meier“ im Arbeitgeber „Meier Bau GmbH“, „Weimar“ in „99423 Weimar“, wenn eine Person so heißt). Beide Stellen
    werden geschwärzt (die Schwärzung fasst Überlappendes zusammen); wählt die Nutzerin die größere ab, bleibt der
    Name trotzdem geschwärzt – wie bei Namen in Gesundheitsangaben. Nur Namen einer Person, die auch außerhalb
    solcher Stellen vorkommt (zuordnung: Namensschlüssel -> Person): „Meier Bau“ als Namens-Treffer, der nur im
    Firmennamen steht, wird keine eigene Person. IMMER-Begriffe (ausdrücklicher Wunsch der Nutzerin) zählen wie
    Namensstellen."""
    if not namen:
        return []
    eigenstaendig = {zuordnung.get(schl[1]) for _s, _e, schl, kategorie, *_ in stellen if kategorie == "namen"}
    eigenstaendig.discard(None)
    namen = sorted((k for k in namen if zuordnung.get(k.schluessel[1]) in eigenstaendig),
                   key=lambda k: (k.start, -k.ende))
    anfaenge = [k.start for k in namen]
    eingebettet = []
    for s, e, _schl, kategorie, *_ in stellen:
        if kategorie in ("namen", "begriff"):
            continue
        i = bisect_left(anfaenge, s)
        while i < len(namen) and namen[i].start < e:
            if namen[i].ende <= e:
                eingebettet.append(namen[i])
            i += 1
    return _zusammenfuehren(eingebettet) if eingebettet else []


def _zusammenfuehren(kandidaten: list) -> list:
    """Überlappende Kandidaten zu Stellen zusammenführen: die umfassende Stelle gewinnt, bei gleicher Spanne die
    Kategorie-Priorität. Liefert (start, ende, schluessel, kategorie, quellen, sicherheit, arten, eigene_quellen);
    eigene_quellen sind die Quellen der Kandidaten des Siegers (für Hinweise wie „Prüfziffer ungültig“ – ein
    unterlegenes Telefon-Bruchstück soll der IBAN keinen Hinweis vererben)."""
    stellen = []
    gruppe, ende = [], -1

    def abschliessen(gruppe):
        u_s = min(k.start for k in gruppe)
        u_e = max(k.ende for k in gruppe)
        sieger = max(gruppe, key=lambda k: (k.start == u_s and k.ende == u_e, -_rang(k.kategorie),
                                           k.ende - k.start, k.art == 0, k.sicherheit))
        eigene = [k for k in gruppe if k.schluessel == sieger.schluessel]
        stellen.append((u_s, u_e, sieger.schluessel, sieger.kategorie, {k.quelle for k in gruppe},
                        max(k.sicherheit for k in gruppe), {k.art for k in eigene}, {k.quelle for k in eigene}))
    for k in sorted(kandidaten, key=lambda k: (k.start, -k.ende)):
        if gruppe and k.start < ende:
            gruppe.append(k)
            ende = max(ende, k.ende)
        else:
            if gruppe:
                abschliessen(gruppe)
            gruppe, ende = [k], k.ende
    if gruppe:
        abschliessen(gruppe)
    return stellen


def _analysiere(text: str, aktive: set, whitelist: list, immer_schwaerzen: list, profil: str | None = None,
                meldungen: list | None = None) -> tuple:
    """Analyse eines reinen Texts. Liefert (funde, hinweise) (für Tests und Werkzeuge)."""
    hinweise: list = []
    dok = dokument_aus_text(text)
    funde = _analysiere_dokument(dok, set(aktive), whitelist, immer_schwaerzen, profil=profil or "hoch",
                                 hinweise=hinweise, meldungen=meldungen, angebote=profil is not None)
    return funde, hinweise


def analysiere_text(text: str, aktive: set[str], whitelist: list[str], immer_schwaerzen: list[str],
                    profil: str | None = None) -> list[dict]:
    """Durchsucht einen Text nach allen aktivierten Kategorien. Liefert Funde (seiten bleibt leer,
    stellen beziehen sich auf die eine Seite des Textmodells).

    Ohne `profil` (bisherige Schnittstelle) nur die aktivierten Kategorien; mit Schutzstufe ("hoch" …) wie
    analysiere_pdf, also zusätzlich die nur angebotenen Funde ihrer Hinweis-Kategorien (alle Stellen abgewählt)."""
    funde, _ = _analysiere(text, set(aktive), whitelist, immer_schwaerzen, profil=profil)
    return funde


# ----------------------------------------------------------------------
# Dateiart: nur echte PDFs (Gutachten R-01)
# ----------------------------------------------------------------------
# MuPDF erkennt Bilder, Webseiten, XPS … am Inhalt und öffnet sie auch mit der Endung .pdf – als Nicht-PDF
# (doc.is_pdf False, eine Seite). Seiten-Funktionen für PDFs (seite.xref) bringen PyMuPDF dann im C-Code zum
# Absturz (Speicherzugriffsfehler): kein try/except fängt das ab, das ganze Programm verschwindet ohne Meldung.
# Deshalb prüfen Analyse, Schwärzung und Vorschau die Art direkt nach dem Öffnen, vor jedem Seitenzugriff.
_BILD_FORMATE = {"image": "Bild", "jpeg": "JPEG", "jpg": "JPEG", "png": "PNG", "tiff": "TIFF", "gif": "GIF",
                 "bmp": "BMP", "jpx": "JPEG 2000", "jbig2": "JBIG2", "pnm": "PNM", "psd": "Photoshop", "svg": "SVG"}


def _dateianfang(pfad, laenge: int = 2048) -> bytes:
    try:
        with open(pfad, "rb") as f:
            return f.read(laenge)
    except (OSError, TypeError, ValueError):
        return b""


def _nicht_pdf_art(anfang: bytes, format_: str) -> tuple:
    """Art einer Datei, die keine PDF ist: ("bild", "JPEG") | ("web", "HTML") | ("andere", Formatname)."""
    bild = _nebenkanaele.bildart(anfang)
    if bild:
        return "bild", bild
    kopf = anfang.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if _nebenkanaele.ist_html(anfang) or b"<html" in kopf:
        return "web", "HTML"
    fmt = (format_ or "").strip()
    klein = fmt.lower()
    if "html" in klein or "xhtml" in klein:
        return "web", "HTML"
    for schluessel, name in _BILD_FORMATE.items():
        if klein == schluessel or klein.startswith(schluessel + " "):
            return "bild", name
    return "andere", fmt or "unbekannt"


def keine_pdf_meldung(doc, pfad=None) -> str | None:
    """Meldung für die Nutzerin, wenn `doc` keine PDF ist (Bild, Webseite … mit der Endung .pdf), sonst None.
    MUSS direkt nach fitz.open und vor jedem Seitenzugriff geprüft werden (siehe oben, Gutachten R-01)."""
    try:
        if doc.is_pdf:
            return None
    except Exception:
        pass                                   # Art nicht bestimmbar: wie eine Nicht-PDF behandeln (kein Absturz)
    try:
        format_ = (doc.metadata or {}).get("format", "")
    except Exception:
        format_ = ""
    art, name = _nicht_pdf_art(_dateianfang(pfad) if pfad is not None else b"", format_)
    datei = f"»{Path(pfad).name}«" if pfad is not None else "Die Datei"
    if art == "bild":
        art_text = "ein Bild" if name == "Bild" else f"ein Bild ({name})"
        return (f"{datei} ist keine PDF, sondern {art_text} – sie trägt nur die Endung .pdf (z. B. ein umbenanntes "
                f"Handyfoto oder Fax). Bitte zuerst in eine echte PDF umwandeln: das Bild öffnen, „Drucken“ wählen "
                f"und als Drucker „Microsoft Print to PDF“ nehmen. Diese PDF dann hier hinzufügen.")
    if art == "web":
        return (f"{datei} ist keine PDF, sondern eine Webseite (HTML) – sie trägt nur die Endung .pdf (oft eine "
                f"Fehler- oder Anmeldeseite eines Portals statt des Dokuments). Bitte das Dokument erneut "
                f"herunterladen und prüfen, ob es sich als PDF öffnen lässt.")
    return (f"{datei} ist keine PDF, sondern eine Datei im Format {name} – sie trägt nur die Endung .pdf. Bitte "
            f"im Ursprungsprogramm als PDF speichern (oder über „Drucken“ → „Microsoft Print to PDF“) und diese "
            f"PDF hinzufügen.")


# ----------------------------------------------------------------------
# Beschädigte Dateien (Gutachten R-11)
# ----------------------------------------------------------------------
TEXT_REPARIERT = ("Die Datei war beschädigt und wurde repariert – Inhalte können fehlen, bitte das Original "
                  "prüfen")
# Analyse-Meldungen, deren Ursache bis in die Ausgabe wirkt (Gutachten R-07): die Schwärzung legt die Ausgabe dann
# als _PRUEFEN ab. Die Analyse vermerkt sie am Modell (dok.leckrelevant).
LECKRELEVANTE_CODES = frozenset({"OCR_UNPLAUSIBEL", "KAUM_LESBAR", "OCR_FEHLER", "XFA", "DATEI_REPARIERT",
                                 "BILDER_UNGEPRUEFT", "BILD_BESCHAEDIGT"})


def datei_repariert(doc) -> bool:
    """Hat MuPDF die Datei reparieren müssen (abgeschnittener Download, kaputte Querverweise)?"""
    try:
        return bool(getattr(doc, "is_repaired", False))
    except Exception:
        return False


def reparatur_erzwingen(doc) -> bool:
    """Lädt jedes Objekt der Datei einmal und liefert danach datei_repariert(doc).

    MuPDF repariert eine beschädigte Datei oft erst, wenn ein kaputtes Objekt zum ersten Mal gebraucht wird (falscher
    Versatz in der Querverweistabelle, ein mitten in der Datei zerstörter Block, ein kaputtes Strukturelement einer
    getaggten PDF) – und verwirft dabei ALLE Änderungen im Speicher: eine schon geschwärzte Seite stünde danach wieder
    im Klartext da (Gutachten R-11). Deshalb direkt nach dem Öffnen und vor jeder Änderung aufrufen: eine nötige
    Reparatur geschieht dann jetzt, solange noch nichts geändert ist. MuPDF repariert eine Datei nur einmal."""
    if datei_repariert(doc):
        return True
    try:
        anzahl = int(doc.xref_length())
    except Exception:
        return datei_repariert(doc)
    for xref in range(1, anzahl):
        try:
            doc.xref_get_keys(xref)
        except Exception:
            pass
        if datei_repariert(doc):
            break
    return datei_repariert(doc)


# ----------------------------------------------------------------------
# Beschädigte Bilder (Gutachten R-07, Fall scan_bild_defekt)
# ----------------------------------------------------------------------
BILD_MIN_PIXEL = 2500            # kleinere Bilder (Symbole, Linien) tragen keine lesbare Zeile
BILD_MAX_ANZAHL = 400            # so viele Bilder je Dokument werden höchstens geprüft
_DEKODIER_WARNUNG_RE = re.compile(r"(?i)premature end|corrupt|truncat|padding|unexpected end|not enough data|"
                                  r"bad (?:huffman|data|code|marker)|jpeg error|jbig2|jpx|invalid")
_BILD_KANTE_ZEILEN = 24          # so viele Zeilen über der Abbruchkante werden auf Tinte geprüft


def _kante_mit_tinte(pix) -> bool:
    """Bricht das Bild unten ab (MuPDF füllt fehlende Daten mit einer einheitlichen Fläche, z. B. Grau 128 oder der
    letzten Farbe) und liegt direkt über der Kante Tinte – eine halb sichtbare Zeile, die die OCR nicht liest, ein Mensch
    oder eine Bild-KI aber schon? Ein vollständiges Bild, dem nur die Endmarke fehlt, hat unten keine solche Fläche."""
    try:
        if pix.colorspace is not None and pix.colorspace.n != 1:
            pix = fitz.Pixmap(fitz.csGRAY, pix)
        elif pix.alpha:
            pix = fitz.Pixmap(pix, 0)
        breite, hoehe, n = pix.width, pix.height, pix.n
        daten = pix.samples
    except Exception:
        return False
    zeile = breite * n
    if hoehe < 16 or zeile <= 0:
        return False
    flach = 0
    for y in range(hoehe - 1, -1, -1):
        z = daten[y * zeile:(y + 1) * zeile]
        if z.count(z[:1]) != len(z):
            break
        flach += 1
    if flach < 8 or flach >= hoehe:
        return False                      # keine Füllfläche – oder gar nichts sichtbar
    ende = hoehe - flach
    band = daten[max(0, ende - _BILD_KANTE_ZEILEN) * zeile:ende * zeile]
    dunkel = len(band) - len(band.translate(None, bytes(range(128))))
    return dunkel > 0.002 * len(band)


def bild_schaeden(pfad) -> dict:
    """Seiten (0-basiert) mit beschädigten Bildern: {Seite: Beschreibung}. Jedes Bild wird einmal dekodiert (in einem
    eigenen, frisch geöffneten Dokument – MuPDF merkt sich dekodierte Bilder und warnte beim zweiten Mal nicht mehr):
    bricht es mitten im Bild ab (MuPDF: „premature end of file in jpeg“, „padding truncated image“) und ist über der
    Abbruchkante etwas halb zu sehen, oder lässt es sich gar nicht dekodieren, gilt die Seite als nicht geprüft
    (Gutachten R-07: die halbe Zeile mit Geburtsdatum bzw. IBAN blieb lesbar, die OCR las sie nicht)."""
    schaeden: dict = {}
    try:
        doc = fitz.open(pfad)
    except Exception:
        return schaeden
    try:
        if not doc.is_pdf or doc.needs_pass:
            return schaeden
        geprueft: dict = {}
        for nr in range(len(doc)):
            try:
                bilder = doc[nr].get_images(full=True)
            except Exception:
                continue
            for eintrag in bilder:
                xref = int(eintrag[0])
                if xref not in geprueft:
                    if len(geprueft) >= BILD_MAX_ANZAHL:
                        break
                    breite, hoehe = int(eintrag[2] or 0), int(eintrag[3] or 0)
                    geprueft[xref] = (None if breite * hoehe < BILD_MIN_PIXEL
                                      else _bild_beschaedigt(doc, xref, str(eintrag[8] or "")))
                if geprueft[xref]:
                    schaeden.setdefault(nr, geprueft[xref])
    except Exception:
        return schaeden
    finally:
        doc.close()
    return schaeden


def _warnungen_zuruecksetzen():
    """MuPDF unterdrückt eine Warnung, die genauso lautet wie die vorige („… repeated 2 times“) – nach einem anderen
    beschädigten Bild käme „premature end of file in jpeg“ sonst nicht mehr an. Deshalb erst MuPDFs Gedächtnis leeren,
    dann die gesammelten Warnungen."""
    try:
        fitz.mupdf.fz_flush_warnings()
    except Exception:
        pass
    try:
        fitz.TOOLS.reset_mupdf_warnings()
    except Exception:
        pass


def _bild_beschaedigt(doc, xref: int, filter_name: str):
    """Beschreibung des Schadens eines Bild-XObjects oder None."""
    _warnungen_zuruecksetzen()
    try:
        pix = fitz.Pixmap(doc, xref)
    except Exception:
        return "lässt sich nicht dekodieren"
    try:
        warnungen = fitz.TOOLS.mupdf_warnings() or ""
    except Exception:
        warnungen = ""
    if not _DEKODIER_WARNUNG_RE.search(warnungen):
        return None
    # Ein progressives JPEG, das in einer späteren Stufe abbricht, ist überall gleich unscharf – die OCR sieht dasselbe
    # Bild wie ein Mensch; nur eine Füllfläche unter einer halb sichtbaren Zeile ist das hier gemeinte Leck
    return "bricht mitten im Bild ab" if _kante_mit_tinte(pix) else None


# ----------------------------------------------------------------------
# Kaum lesbare Scan-Seiten (Gutachten R-07, Befund Fehlalarm-Gründe): EINE Regel für die Warnung der Analyse und den
# _PRUEFEN-Grund der Schwärzung
# ----------------------------------------------------------------------
KAUM_LESBAR_WOERTER = 25        # eine Scan-Seite mit weniger OCR-Wörtern KANN kaum lesbar sein ...
# ... aber nur, wenn die OCR dort schlecht gelesen hat oder viel mehr Tinte auf der Seite ist, als die gelesenen Wörter
# erklären (eine gut lesbare Unterschriftsseite, ein Begleitschreiben mit 17 Wörtern oder „Seite 2 von 2“ ist nicht
# „kaum lesbar“). Tinte je Wortfläche gedruckter Schrift: höchstens etwa TINTE_JE_WORTFLAECHE.
TINTE_JE_WORTFLAECHE = 0.35
TINTE_FAKTOR = 4.0
TINTE_SOCKEL = 0.004            # Linien, Logo, Stempel, Unterschrift einer sonst lesbaren Seite


def tintenanteil(seite) -> float:
    """Anteil dunkler Pixel (grob gerendert): eine leere Scan-Rückseite hat fast keine, eine unlesbare Seite viele."""
    try:
        daten = seite.get_pixmap(dpi=50, colorspace=fitz.csGRAY, alpha=False).samples
    except Exception:
        return 1.0
    return (len(daten) - len(bytes(daten).translate(None, bytes(range(180))))) / max(1, len(daten))


def scan_kaum_lesbar(seite, woerter) -> bool:
    """Eine Scan-Seite mit wenigen OCR-Wörtern ist nur dann „kaum lesbar“, wenn die OCR dort schlecht gelesen hat
    (keine plausible Lesung) oder auf der Seite viel mehr Tinte ist, als die gelesenen Wörter erklären (Handschrift,
    Kritzel, unscharfer Text). Eine kurze, gut lesbare Seite („Ort, Datum / Unterschrift Versicherungsnehmer“,
    „Seite 2 von 2“, ein Begleitschreiben) ist es nicht. Im Zweifel (Fehler beim Messen): kaum lesbar."""
    woerter = [w for w in woerter or () if len(w) >= 5 and str(w[4]).strip()]
    try:
        if not _ocr._plausibel(_ocr._lesung_bewerten([str(w[4]) for w in woerter])):
            return True
    except Exception:
        return True
    try:
        flaeche = abs(seite.rect) or 1.0
    except Exception:
        return True
    wortflaeche = 0.0
    for w in woerter:
        try:
            wortflaeche += max(0.0, float(w[2]) - float(w[0])) * max(0.0, float(w[3]) - float(w[1]))
        except (TypeError, ValueError):
            continue
    erwartet = TINTE_JE_WORTFLAECHE * min(1.0, wortflaeche / flaeche)
    return tintenanteil(seite) > TINTE_FAKTOR * erwartet + TINTE_SOCKEL


def _kaum_lesbar_nachpruefen(doc, ocr_cache: dict, meldungen: list, warnungen: list, hinweise: list) -> None:
    """Das Seitenmodell meldet jede Scan-Seite mit weniger als KAUM_LESBAR_WOERTER OCR-Wörtern als „kaum lesbar –
    Unbedingt manuell prüfen!“. Ist sie nach scan_kaum_lesbar gut lesbar, wird daraus ein Hinweis (WENIG_TEXT) – sonst
    hieße die Ausgabe „fertig“, während die Analyse noch vor ihr warnt."""
    for m in meldungen:
        nr = m.get("seite")
        if m.get("code") != "KAUM_LESBAR" or m.get("art") != "warnung" or not isinstance(nr, int):
            continue
        try:
            if scan_kaum_lesbar(doc[nr], ocr_cache.get(nr) or ()):
                continue
        except Exception:
            continue
        if m["text"] in warnungen:
            warnungen.remove(m["text"])
        m.update(art="hinweis", code="WENIG_TEXT",
                 text=f"Seite {nr + 1}: nur wenige Wörter gelesen, diese aber gut lesbar – bitte kurz selbst ansehen.")
        if m["text"] not in hinweise:
            hinweise.append(m["text"])


def bildschaden_meldungstext(nr: int, art: str) -> str:
    return (f"Seite {nr + 1}: Ein Bild ist beschädigt ({art}). Was an der Abbruchkante halb zu sehen ist, kann die "
            f"Texterkennung nicht lesen – ein Mensch oder eine KI womöglich schon. Ausgabe bitte selbst ansehen.")


def leere_seiten(doc) -> list:
    """Seiten (1-basiert) ohne jeden gezeichneten Inhalt – nach einer Reparatur ein Zeichen für fehlende Teile."""
    leer = []
    for nr in range(len(doc)):
        try:
            if not doc[nr].get_bboxlog():
                leer.append(nr + 1)
        except Exception:
            continue
    return leer


def reparatur_meldungstext(leer: list) -> str:
    """Text der Meldung DATEI_REPARIERT, mit den leeren Seiten, falls es welche gibt."""
    if not leer:
        return TEXT_REPARIERT + "."
    seiten = ", ".join(map(str, leer[:12])) + (" …" if len(leer) > 12 else "")
    return f"{TEXT_REPARIERT}. Leer sind Seite(n) {seiten} – dort fehlt vermutlich Inhalt."


# ----------------------------------------------------------------------
# Nebenkanäle: Dokumenteigenschaften, Lesezeichen, Anhänge, XFA (Gutachten R-04)
# ----------------------------------------------------------------------
NEBENKANAELE_LEER = {"metadaten": 0, "lesezeichen": 0, "anhaenge": 0, "xfa": False, "personenbezug": False}
# Kanal eines Eintrags -> Zähler im Ergebnis (vereinbarte Schlüssel; Skripte, Link-Ziele, Seitenbeschriftungen und
# Notizen zählen nur in „personenbezug“ und stehen in der Meldung)
_ZAEHLER_JE_KANAL = {"metadaten": "metadaten", "programm": "metadaten", "lesezeichen": "lesezeichen",
                     "anhaenge": "anhaenge"}


def _aufzaehlung(teile: list) -> str:
    return teile[0] if len(teile) == 1 else ", ".join(teile[:-1]) + " und " + teile[-1]


# ----------------------------------------------------------------------
# Nebenkanäle: Dateinamen-Schreibweise, Programmfelder, Standardtitel (Gutachten R-04, Befund NEBENKANAL_FUND)
# ----------------------------------------------------------------------
_STANDARDTITEL_RE = re.compile(
    r"(?i)^(?:microsoft\s+\w+\s*-\s*)?(?:unbenannt|untitled|ohne\s+titel|neues\s+dokument|dokument|document|"
    r"gescanntes\s+dokument|scan|scanned\s+document|bild|image|img)[\s_\-]*\d*(?:\.[a-z0-9]{2,4})?$")
_DATEI_PRAEFIX_RE = re.compile(r"(?i)^\s*(?:microsoft\s*(?:®\s*)?(?:office\s+)?(?:word|excel|powerpoint|outlook)|"
                               r"libreoffice\s+\w+|openoffice\.org\s+\w+|word|excel)\s*[-–:]\s*")
_DATEI_ENDUNG_RE = re.compile(r"(?i)\.(?:docx?|docm|dotx?|xlsx?|xlsm|pptx?|pdf|odt|ods|odp|rtf|txt|csv|jpe?g|png|"
                              r"tiff?|gif|bmp|heic|eml|msg|zip|xml|html?)$")
_BUCHSTABEN_WORT_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")
# Wörter, mit denen Programm- und Gerätenamen enden („Crystal Reports“, „Genius Scan“, „Scanner Pro“): nie ein Nachname
_PROGRAMMWOERTER = frozenset(
    "reports report scan scanner scansnap pro plus lens notes pages preview writer editor creator printer office "
    "capture manager home utility library version inspire power create works studio suite cloud mobile app apps print "
    "viewer reader converter maker server service services edition express standard premium online desktop portal "
    "generator designer builder drucker druck export import tools toolkit engine framework system systems software "
    "pdf mill exstream context phantompdf finereader paperport acrobat distiller".split())
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?\b")


def _dateinamen_lesart(text: str) -> str | None:
    """Lesart eines Werts in der Schreibweise eines Dateinamens („Microsoft Word - PIB_Hausrat_Mustermann_Max.docx“,
    „Scan_Mustermann_Max_2024-05-03“, „AntragThomasSchaefer“) als Wörter („PIB Hausrat Mustermann Max“) – die
    Namenserkennung findet Namen nur zwischen Leerzeichen. None, wenn der Wert nicht so aussieht."""
    t = " ".join(str(text or "").split())
    if not t or len(t) > 300:
        return None
    ohne_praefix = _DATEI_PRAEFIX_RE.sub("", t)
    kern = _DATEI_ENDUNG_RE.sub("", ohne_praefix)
    endung_oder_praefix = kern != ohne_praefix or ohne_praefix != t
    binnen = re.search(r"[a-zäöüß][A-ZÄÖÜ]", kern) is not None and " " not in kern
    if not ("_" in kern or endung_oder_praefix or binnen):
        return None
    neu = kern.replace("_", " ")
    neu = re.sub(r"(?<=[a-zäöüß])(?=[A-ZÄÖÜ])", " ", neu)                       # Binnenmajuskel
    neu = re.sub(r"(?<=[^\W\d_])-(?=[^\W\d_])", " ", neu)                         # Antrag-Thomas-Schaefer
    neu = " ".join(neu.split())
    return neu if neu and neu != t else None


def _nie_enthaelt(nie_woerter: list, woerter) -> bool:
    """Gehören die Wörter (zusammen) zu einem Eintrag der NIE-Liste (eigene Daten der Nutzerin)?"""
    gesucht = {w.casefold() for w in woerter}
    return any(gesucht <= eintrag for eintrag in nie_woerter)


def _nie_wortmengen(whitelist) -> list:
    return [{w.casefold() for w in _BUCHSTABEN_WORT_RE.findall(str(e or ""))} for e in whitelist or ()]


def _wort_ist(wissen, funktion: str, wort: str) -> bool:
    try:
        return bool(getattr(wissen, funktion)(wort))
    except Exception:
        return False


def _namensartig(wort: str) -> bool:
    """Großgeschriebenes Wort aus Buchstaben (mindestens 3), nicht ganz in Versalien („RICOH“, „PDF“)."""
    return len(wort) >= 3 and wort[0].isupper() and not wort.isupper() and wort.isalpha()


# Wörter typischer Seitenbeschriftungen, die die Wissensbasis nicht als Allerweltswörter führt
_ETIKETT_WOERTER = frozenset("abschnitt band hauptteil cover appendix part page section chapter".split())


def _name_im_dateinamen(text: str, wissen, nie_woerter: list, locker: bool = False) -> bool:
    """Vorsicht-Regel für Nebenkanäle, die die Erkennung nicht sicher liest: Steht in einem Wert in Dateinamen-
    Schreibweise ein bekannter Vorname neben einem namensartigen Wort („Mustermann_Max“) oder ein bekannter, nicht
    mehrdeutiger Nachname („Vollmacht_Schaefer“ … „Schäfer“), gelten Personendaten als nicht auszuschließen.
    locker=True (Seitenbeschriftungen – kurze Etiketten wie „Mustermann-1“, sonst „Anlage-“, „Teil I-“): jedes
    namensartige Wort, das kein Allerweltswort ist, zählt – auch ohne Dateinamen-Schreibweise."""
    if wissen is None:
        return False
    lesart = _dateinamen_lesart(text)
    if lesart is None:
        if not locker:
            return False
        lesart = " ".join(str(text or "").replace("_", " ").replace("-", " ").split())
    woerter = _BUCHSTABEN_WORT_RE.findall(lesart)
    for i, w in enumerate(woerter):
        if not _namensartig(w) or _wort_ist(wissen, "ist_allerweltswort", w):
            continue
        if _wort_ist(wissen, "ist_allowlist", w) or _nie_enthaelt(nie_woerter, (w,)):
            continue
        if locker:
            if w.casefold() not in _ETIKETT_WOERTER:
                return True
            continue
        if _wort_ist(wissen, "ist_vorname", w):
            nachbarn = [woerter[j] for j in (i - 1, i + 1) if 0 <= j < len(woerter)]
            for n in nachbarn:
                if (_namensartig(n) and not _wort_ist(wissen, "ist_allerweltswort", n)
                        and not _nie_enthaelt(nie_woerter, (w, n))):
                    return True
        if _wort_ist(wissen, "ist_nachname", w) and not _wort_ist(wissen, "ist_mehrdeutig", w):
            return True
    return False


def _programm_mit_person(text: str, wissen, nie_woerter: list) -> bool:
    """Programm- und Gerätefelder (Creator, Producer, CreatorTool): Personenbezug nur bei einer E-Mail-Adresse, einer
    IBAN oder einem ausdrücklichen Personennamen – Vorname + bekannter Nachname („Thomas Schäfer“, „Schäfer, Thomas“)
    oder das ganze Feld ein Name aus zwei, drei Wörtern mit bekanntem Vornamen vorn („Max Mustermann“). Modell- und
    Programmnamen („RICOH MP C3004“, „Crystal Reports“, „Genius Scan“) zählen nicht; Kfz- und Kennungsmuster werden
    hier nicht angewandt."""
    t = " ".join(str(text or "").split())
    if not t:
        return False
    if _EMAIL_RE.search(t) or _IBAN_RE.search(t):
        return True
    if wissen is None:
        return False
    woerter = _BUCHSTABEN_WORT_RE.findall(t)
    for a, b in zip(woerter, woerter[1:]):
        if (_namensartig(a) and _namensartig(b) and _wort_ist(wissen, "ist_vorname", a)
                and _wort_ist(wissen, "ist_nachname", b) and not _nie_enthaelt(nie_woerter, (a, b))):
            return True
    m = re.fullmatch(r"([^\W\d_]+(?:-[^\W\d_]+)?)\s*,\s*([^\W\d_]+)", t)
    if (m and _namensartig(m.group(1).split("-")[0]) and _wort_ist(wissen, "ist_nachname", m.group(1))
            and _wort_ist(wissen, "ist_vorname", m.group(2)) and not _nie_enthaelt(nie_woerter, m.groups())):
        return True
    ganz = [w for w in t.replace("-", " ").split() if w.strip(".").casefold() not in TITEL]
    if (2 <= len(ganz) <= 3 and all(_namensartig(w) for w in ganz) and _wort_ist(wissen, "ist_vorname", ganz[0])
            and ganz[-1].casefold() not in _PROGRAMMWOERTER and not _wort_ist(wissen, "ist_allerweltswort", ganz[-1])
            and not _nie_enthaelt(nie_woerter, ganz)):
        return True
    return False


def _standardtitel(eintrag) -> bool:
    """„Unbenannt“, „Dokument1“, „Gescanntes Dokument“ … als Dokumenteigenschaft: kein Personenbezug."""
    return eintrag.kanal == "metadaten" and bool(_STANDARDTITEL_RE.match(" ".join(eintrag.text.split())))


def _personenbezug_fund(fund: dict) -> bool:
    """Zählt ein Fund im Nebenkanal als personenbezogen? Angehakte Funde und angebotene Gesundheitsdaten – nicht
    aber bloß vermutete Fachbegriffe ohne Personenbezug („Physiotherapie“ in einer Tarifübersicht)."""
    if any(st.get("an", True) for st in fund.get("stellen") or ()):
        return True
    hinweise = str(fund.get("hinweis") or "").split("; ")
    return HINWEIS_GESUNDHEIT in hinweise


_KANAL_NAMEN = {"metadaten": "Dateieigenschaften", "programm": "Dateieigenschaften", "lesezeichen": "Lesezeichen",
                 "xfa": "Formulardaten (XFA)", "kommentare": "Notizen/Kommentare", "skripte": "Skripte (JavaScript)",
                 "links": "Link-Ziele", "seitenbeschriftungen": "Seitenbeschriftungen", "anhaenge": "Namen von Anhängen"}


def _nebenkanal_meldungstext(gefunden: set, ungeprueft: list, vermutet: set = frozenset()) -> str:
    """gefunden: {(Kanal, Einheit)} mit personenbezogenen Daten; ungeprueft: [(Kanal, Art)] nicht lesbarer Teile;
    vermutet: {(Kanal, Einheit)} mit einem Namen in Dateinamen-Schreibweise (Vorsicht-Regel)."""
    def anzahl(*kanaele):
        return len({(k, e) for k, e in gefunden if k in kanaele})
    teile = []
    if anzahl("metadaten", "programm"):
        teile.append("in den Dateieigenschaften (z. B. Titel oder Autor)")
    if anzahl("lesezeichen"):
        teile.append(f"in {anzahl('lesezeichen')} Lesezeichen")
    if anzahl("anhaenge"):
        teile.append("in einer angehängten Datei" if anzahl("anhaenge") == 1
                     else f"in {anzahl('anhaenge')} angehängten Dateien")
    if anzahl("xfa"):
        teile.append("in den Formulardaten (XFA)")
    if anzahl("kommentare"):
        teile.append("in Notizen oder Kommentaren")
    if anzahl("skripte"):
        teile.append("in Skripten (JavaScript)")
    if anzahl("links"):
        teile.append("in Link-Zielen (z. B. einer E-Mail-Adresse hinter einem Link)")
    if anzahl("seitenbeschriftungen"):
        teile.append("in Seitenbeschriftungen")
    satz = []
    if teile:
        satz.append(f"Personenbezogene Daten stehen auch außerhalb der Seiten: {_aufzaehlung(teile)}.")
    if vermutet:
        wo = _aufzaehlung(list(dict.fromkeys(_KANAL_NAMEN.get(k, k) for k, _ in sorted(vermutet))))
        satz.append(f"In {wo} steht vermutlich ein Name (geschrieben wie ein Dateiname, z. B. „Antrag_Nachname_"
                    f"Vorname“) – personenbezogene Daten sind nicht auszuschließen.")
    anhaenge = [art for kanal, art in ungeprueft if kanal == "anhaenge"]
    sonst = [kanal for kanal, _ in ungeprueft if kanal != "anhaenge"]
    if anhaenge:
        arten = ", ".join(dict.fromkeys(anhaenge))
        wer = "Eine angehängte Datei konnte" if len(anhaenge) == 1 else f"{len(anhaenge)} angehängte Dateien konnten"
        satz.append(f"{wer} nicht geprüft werden ({arten}) und kann personenbezogene Daten enthalten.")
    if sonst:
        was = _aufzaehlung(list(dict.fromkeys(_KANAL_NAMEN.get(k, k) for k in sonst)))
        satz.append(f"{was} ließen sich nicht lesen und können personenbezogene Daten enthalten.")
    satz.append("Diese Teile sieht man beim Durchblättern nicht, sie werden aber mit hochgeladen. In der geschwärzten "
                "Ausgabe werden sie entfernt – bitte nur die Ausgabe weitergeben, nicht das Original.")
    return " ".join(satz)


def nebenkanaele_pruefen(doc, aktive, whitelist=(), immer_schwaerzen=(), profil: str = "hoch", kundenliste=None,
                         meldungen=None, warnungen=None) -> dict:
    """Prüft die Nebenkanäle eines geöffneten PDFs (vor bake) mit denselben Detektoren wie die Seiten:
    Dokumenteigenschaften (Info, XMP), Lesezeichen, Anhänge (Name, Beschreibung, Inhalt – Text, XML, Office, PDF
    rekursiv; Portfolio), XFA-Formulardaten, Notizen/Kommentare (nebenkanaele.nebenkanaele_lesen).

    Rückgabe {"metadaten": n, "lesezeichen": n, "anhaenge": n, "xfa": bool, "personenbezug": bool}: n = Anzahl der
    Einträge des Kanals (Eigenschaft, Lesezeichen, Anhang) mit personenbezogenen Daten; xfa = XFA-Formulardaten mit
    personenbezogenen Daten; personenbezug = irgendwo gefunden (auch in Skripten, Link-Zielen, Seitenbeschriftungen,
    Notizen) oder nicht auszuschließen (Anhang nicht lesbar, Name in Dateinamen-Schreibweise).
    Werte in Dateinamen-Schreibweise („Antrag_Mustermann_Max.docx“) werden zusätzlich als Wörter gelesen; Programm-
    und Gerätefelder (Creator, Producer, CreatorTool) zählen nur mit einem ausdrücklichen Personennamen, einer E-Mail-
    Adresse oder IBAN; Standardtitel („Unbenannt“, „Dokument1“) zählen nie.
    Bei personenbezug: Meldung NEBENKANAL_FUND (Warnung; analysiere_pdf macht daraus einen Hinweis, wenn auf den
    Seiten ohnehin geschwärzt wird) – die Ausgabe entfernt diese Teile, deshalb schreibt schwaerze_pdf dann auch ohne
    Fund auf den Seiten eine bereinigte Ausgabe (als _PRUEFEN)."""
    ergebnis = dict(NEBENKANAELE_LEER)
    try:
        eintraege = list(_nebenkanaele.nebenkanaele_lesen(doc))
    except Exception as e:  # nebenkanaele_lesen wirft eigentlich nie – sicherheitshalber: nicht auszuschließen
        eintraege = [_nebenkanaele.NebenkanalText("anhaenge", 0, f"Nebenkanäle ({type(e).__name__})", "", False)]
    eintraege = [e for e in eintraege if not _standardtitel(e)]
    wissen = _wissen_modul()
    nie_woerter = _nie_wortmengen(whitelist)
    betroffen: set = set()
    pruefbar = [e for e in eintraege if e.pruefbar and e.text.strip()]
    programm = [e for e in pruefbar if e.kanal == "programm"]
    inhalt = []
    for e in pruefbar:
        if e.kanal == "programm":
            continue
        lesart = _dateinamen_lesart(e.text)
        inhalt.append(e._replace(text=f"{e.text}\n{lesart}") if lesart else e)
    try:
        betroffen = _nebenkanal_funde(inhalt, aktive, whitelist, immer_schwaerzen, profil, kundenliste)
        betroffen |= {(e.kanal, e.einheit) for e in programm if _programm_mit_person(e.text, wissen, nie_woerter)}
    except Exception:  # eine kaputte Regel darf die Analyse nicht abbrechen – dann gilt nichts als geprüft
        eintraege = [x._replace(pruefbar=False) if x in pruefbar else x for x in eintraege]
        pruefbar = []
    gefunden = set(betroffen)
    vermutet = set()                        # (Kanal, Einheit): Name in Dateinamen-Schreibweise (Vorsicht-Regel)
    for e in pruefbar:
        if e.kanal in ("programm", "xfa", "skripte") or (e.kanal, e.einheit) in gefunden:
            continue
        if e.kanal == "anhaenge" and e.art != "Name des Anhangs":
            continue                        # Inhalte von Anhängen prüft die Erkennung (Text, Tabelle, Office …)
        if _name_im_dateinamen(e.text, wissen, nie_woerter, locker=e.kanal == "seitenbeschriftungen"):
            vermutet.add((e.kanal, e.einheit))
    betroffen |= vermutet
    ungeprueft = []                         # (Kanal, Art) nicht lesbarer Teile, die nicht schon Funde haben
    for e in eintraege:
        if e.pruefbar:
            continue
        if (e.kanal, e.einheit) not in gefunden:
            ungeprueft.append((e.kanal, re.sub(r"^Inhalt des Anhangs \((.*)\)$", r"\1", e.art)))
        betroffen.add((e.kanal, e.einheit))
    for schluessel in ("metadaten", "lesezeichen", "anhaenge"):
        ergebnis[schluessel] = len({(k, e) for k, e in betroffen if _ZAEHLER_JE_KANAL.get(k) == schluessel})
    ergebnis["xfa"] = any(k == "xfa" for k, _ in betroffen)
    ergebnis["personenbezug"] = bool(betroffen)
    if ergebnis["personenbezug"]:
        _melde(meldungen, warnungen, "warnung", "NEBENKANAL_FUND",
               _nebenkanal_meldungstext(gefunden, ungeprueft, vermutet - gefunden))
    return ergebnis


def _nebenkanal_funde(pruefbar: list, aktive, whitelist, immer_schwaerzen, profil, kundenliste) -> set:
    """{(Kanal, Einheit)} der lesbaren Nebenkanal-Texte, in denen die Detektoren personenbezogene Daten finden.
    Alle Texte werden in EINEM Textmodell geprüft (durch Leerzeilen getrennt) und die Funde über die Rückabbildung
    des Modells ihren Einheiten zugeordnet."""
    betroffen: set = set()
    if pruefbar:
        teile, grenzen, pos = [], [], 0
        for e in pruefbar:
            t = e.text.strip()
            teile.append(t)
            grenzen.append((pos, pos + len(t), e))
            pos += len(t) + 2
        text = "\n\n".join(teile)
        dok = dokument_aus_text(text)
        funde = _analysiere_dokument(dok, set(aktive), list(whitelist or ()), list(immer_schwaerzen or ()),
                                     profil=profil, kundenliste=kundenliste, hinweise=[], warnungen=[],
                                     meldungen=[])
        seite = dok.seiten[0]
        herkunft = [i for i, c in enumerate(text) if c != "\n"]
        abbildung = [herkunft[g] if 0 <= g < len(herkunft) else -1 for g in seite.abbildung]
        anfaenge = [g[0] for g in grenzen]
        for f in funde:
            if not _personenbezug_fund(f):
                continue
            for st in f.get("stellen") or ():
                for i in range(st["start"], st["ende"]):
                    j = abbildung[i] if 0 <= i < len(abbildung) else -1
                    if j < 0:
                        continue
                    k = bisect_right(anfaenge, j) - 1
                    if k >= 0 and grenzen[k][0] <= j < grenzen[k][1]:
                        betroffen.add((grenzen[k][2].kanal, grenzen[k][2].einheit))
                    break
    return betroffen


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
    "text_lesbar"; Funde im Format v2 (id, stellen, quellen, sicherheit, hinweis); "nebenkanaele" (siehe
    nebenkanaele_pruefen: {"metadaten", "lesezeichen", "anhaenge", "xfa", "personenbezug"}).
    Keine PDF (Bild, Webseite … mit der Endung .pdf): fehler mit Erklärung, Meldung KEIN_PDF (R-01). Von MuPDF
    reparierte Datei: Warnung DATEI_REPARIERT (R-11). Personenbezogene Daten in Nebenkanälen: Warnung
    NEBENKANAL_FUND (R-04)."""
    pdf_pfad = Path(pdf_pfad)
    aktive = set(aktive)
    ergebnis = {"datei": pdf_pfad, "funde": [], "warnungen": [], "hinweise": [], "fehler": None,
                "seiten": 0, "ocr_seiten": 0, "ocr_cache": {}, "meldungen": [], "modell": None, "felder": [],
                "profil": profil, "text_lesbar": False, "nie": list(whitelist or []),
                "immer": list(immer_schwaerzen or []), "aktive": sorted(aktive),
                "nebenkanaele": dict(NEBENKANAELE_LEER)}
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
    keine_pdf = keine_pdf_meldung(doc, pdf_pfad)       # vor jedem Seitenzugriff (R-01: sonst Absturz)
    if keine_pdf:
        doc.close()
        ergebnis["fehler"] = keine_pdf
        _melde(meldungen, None, "fehler", "KEIN_PDF", keine_pdf)
        return ergebnis
    eigener_dienst = None
    repariert = datei_repariert(doc)
    try:
        if doc.needs_pass:
            ergebnis["fehler"] = "Passwortgeschützt — übersprungen."
            return ergebnis
        # vor jeder Änderung (bake, Drehung, Ebenen): eine nötige Reparatur jetzt auslösen (R-11, späte Reparatur)
        repariert = reparatur_erzwingen(doc)
        ergebnis["seiten"] = len(doc)
        ergebnis["nebenkanaele"] = nebenkanaele_pruefen(doc, aktive, whitelist, immer_schwaerzen, profil=profil,
                                                        kundenliste=kundenliste, meldungen=meldungen,
                                                        warnungen=warnungen)
        for nr, art in sorted(bild_schaeden(pdf_pfad).items()):
            _melde(meldungen, warnungen, "warnung", "BILD_BESCHAEDIGT", bildschaden_meldungstext(nr, art), nr)
        vorbereitung = dokument_vorbereiten(doc)
        if vorbereitung.get("dokument") is not None and vorbereitung["dokument"] is not doc:
            alt, doc = doc, vorbereitung["dokument"]          # Ebenen: neu geöffnete Fassung
            repariert = repariert or datei_repariert(alt)
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
        _kaum_lesbar_nachpruefen(doc, ergebnis["ocr_cache"], meldungen, warnungen, hinweise)
        # Netz: hat MuPDF trotzdem erst beim Lesen der Seiten repariert, gilt die Datei ebenso als repariert
        repariert = repariert or datei_repariert(doc)
        if repariert:
            _melde(meldungen, warnungen, "warnung", "DATEI_REPARIERT", reparatur_meldungstext(leere_seiten(doc)))
    finally:
        if eigener_dienst is not None:
            try:
                eigener_dienst.schliessen()
            except Exception:
                pass
        doc.close()

    dok.nie = list(whitelist or [])            # für Schwärzung/Restrisiko (eigene Daten der Nutzerin)
    # Meldungen, deren Ursache bis in die Ausgabe wirkt: die Schwärzung übernimmt sie mit dem Modell und legt die
    # Ausgabe dann als _PRUEFEN ab (R-07; ohne Modell stellt sie dieselben Gründe selbst fest)
    dok.leckrelevant = [dict(m) for m in meldungen
                        if m.get("code") in LECKRELEVANTE_CODES and m.get("art") in ("warnung", "fehler")]
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
    if any(any(st.get("an", True) for st in f.get("stellen") or ()) for f in ergebnis["funde"]):
        # Auf den Seiten wird ohnehin geschwärzt, die Ausgabe entfernt die Nebenkanäle sowieso: dann ist der Fund in
        # den Nebenkanälen keine Warnung (nichts zu tun), sondern ein Hinweis
        _zum_hinweis(meldungen, warnungen, hinweise, "NEBENKANAL_FUND")
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


def _nur_angeboten(ergebnis: dict) -> set:
    """Hinweis-Kategorien eines Analyse-Ergebnisses (aus seiner Schutzstufe und seinen Kategorien)."""
    if "aktive" not in ergebnis:
        return set()
    return hinweis_kategorien(ergebnis.get("profil"), ergebnis.get("aktive") or ())


def _kundenanschriften_uebernehmen(ergebnisse: list) -> int:
    """Befund Punkt 6: Eine als „vermutlich Firmenanschrift“ abgewählt angebotene Anschrift, die ein anderes Dokument
    desselben Laufs als Kundenanschrift angehakt hat, ist die Anschrift der Kundin bzw. des Kunden (ihr eigener
    Briefkopf): ihre Stellen werden angehakt. Die Analyse hat sie selbst abgewählt, nicht die Nutzerin – der Lauf läuft
    vor jeder Entscheidung der Nutzerin. Rückgabe: Anzahl angehakter Stellen."""
    kunde = set()
    for e in ergebnisse:
        for f in e["funde"]:
            if (f["kategorie"] in ("strasse", "plzort") and QUELLE_FIRMENANSCHRIFT not in (f.get("quellen") or ())
                    and any(st.get("an", True) for st in f.get("stellen") or ())):
                kunde.add((f["kategorie"], fund_schluessel(f["text"], modus_fuer(f["kategorie"]))))
    neu = 0
    for e in ergebnisse:
        for f in e["funde"]:
            if QUELLE_FIRMENANSCHRIFT not in (f.get("quellen") or ()) or not _alle_abgewaehlt(f):
                continue
            if (f["kategorie"], fund_schluessel(f["text"], modus_fuer(f["kategorie"]))) not in kunde:
                continue
            for st in f["stellen"]:
                st["an"] = True
                neu += 1
            f["quellen"] = sorted((set(f["quellen"]) - {QUELLE_FIRMENANSCHRIFT}) | {"weitergabe"})
            f["hinweis"] = HINWEIS_LAUF_KUNDENANSCHRIFT
    return neu


def weitergabe_anwenden(ergebnisse: list) -> int:
    """Lauf-übergreifend: Namen und Kennungen aus allen Ergebnissen in allen anderen Dokumenten suchen
    (ganzwort_stellen auf deren Modell) und als neue Stellen/Funde ergänzen (quelle "weitergabe").

    Vorhandene Stellen bleiben unverändert (auch abgewählte: NIE-Liste, Satzanfang, Entscheidung der Nutzerin).
    Neue Stellen sind abgewählt, wenn ihre Kategorie im Ziel nur angeboten wird (Hinweis-Kategorie der
    Schutzstufe) oder der vorhandene Fund im Ziel ganz abgewählt ist – eine Weitergabe hakt nie etwas an, das
    die Nutzerin abgewählt hat. Stellen der Gesundheitskategorien (angeboten oder angehakt) und der übrigen
    Hinweis-Kategorien blockieren keine neue Stelle: ein Name in „Diabetes bei Herrn Meier“ wird trotzdem ergänzt
    (wie in der Analyse, Schritt 5). Rückgabe: Anzahl neuer Stellen."""
    gueltig = [e for e in ergebnisse or [] if e and e.get("modell") is not None and not e.get("fehler")]
    neu_gesamt = _kundenanschriften_uebernehmen(gueltig)
    for ziel in gueltig:
        dok = ziel["modell"]
        nie = _NieHuellen(dok, ziel.get("nie") or [])
        nur_hinweis = _nur_angeboten(ziel)
        getrennt = nur_hinweis | _gesundheit_kategorien()
        belegt = _belegte_stellen([f for f in ziel["funde"] if f["kategorie"] not in getrennt])
        belegt_angebot = _belegte_stellen([f for f in ziel["funde"] if f["kategorie"] in getrennt])
        # Namen blockiert nur eine Namens- oder IMMER-Stelle: in einer Stelle einer anderen Kategorie (Arbeitgeber,
        # Ort, E-Mail) bekommt ein Name seine eigene Stelle – wie in der Analyse (_eingebettete_namen)
        belegt_namen = _belegte_stellen([f for f in ziel["funde"] if f["kategorie"] in ("namen", "begriff")])
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
                if fund.get("anzeige") == ANZEIGE_BESTANDTEIL or _nicht_weitergeben(fund):
                    continue          # Bestandteile nur mit ihrer Person (Mehrdeutigkeit); Titel, Firmenanschriften
                schl = (kategorie, fund_schluessel(fund["text"], modus))
                ziel_fund = vorhandene.get(schl)
                angebot = kategorie in nur_hinweis
                an = not angebot and not (ziel_fund is not None and _alle_abgewaehlt(ziel_fund))
                ziel_belegt = (belegt_angebot if kategorie in getrennt
                               else belegt_namen if kategorie == "namen" else belegt)
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
                            if _ueberlappt(ziel_belegt, nr, ls, le):
                                continue
                            neue.append({"seite": nr, "start": ls, "ende": le, "an": an,
                                         "text": dok.seiten[nr].text[ls:le]})
                            ziel_belegt.setdefault(nr, []).append((ls, le))
                            ziel_belegt[nr].sort()
                            if ziel_belegt is belegt_namen:      # eine neue Namensstelle blockiert auch Kennungen
                                belegt.setdefault(nr, []).append((ls, le))
                                belegt[nr].sort()
                if not neue:
                    continue
                neue.sort(key=lambda st: (st["seite"], st["start"]))
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
                                 "hinweis": _hinweise_verbinden(_angebots_hinweis(kategorie) if angebot else None,
                                                                *_geerbte_hinweise(fund), HINWEIS_WEITERGABE)}
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
