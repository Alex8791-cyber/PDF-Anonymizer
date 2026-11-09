"""Strukturregeln: gemeinsame Bausteine und die Regel »struktur.etikett_wert« (Vertrag Abschnitt 3).

Strukturregeln lesen die LAGE des Textes aus dem Seitenmodell – Zeilen und Zeichenrechtecke –, nie
Zeichenspalten: PyMuPDF liefert Tabellenzellen oft als eigene Zeilen oder Blöcke, OCR-Zeilen kennen
keine Tabulatoren, und schräg eingescannte Seiten verschieben ganze Zeilen. Bausteine:

    lage(seite) -> Lage       Wörter mit geradegerückten Rechtecken (Schräglage ausgeglichen), Zellen
                              je Zeile (Tabulator oder Lücke > ~1 Zeichenhöhe), Zeilen von oben nach unten
    etiketten(seite) -> [Etikett]
                              Feldbezeichner der Wissensbasis (daten/etiketten_*.txt), zusammengesetzte
                              Nummern-Etiketten ("Bestandsnummer", "Mitglieds-ID") und neutrale
                              Spaltenköpfe ("Beitrag", "Sparte"); nie über eine Zellgrenze hinweg
    Wertformen                kennung_spanne, datums_spannen, namen_spannen, ort_spanne, strasse_spanne …
                              liefern nur den personenbezogenen WERT, nie das Etikett oder die ganze Zeile

»struktur.etikett_wert«: ein Etikett mit seinem Wert – in derselben Zeile hinter ":", Tabulator,
Punktleiste oder breiter Lücke, in der Zeile darunter in derselben Spalte oder (Kennungen) am Anfang der
Folgezeile. Die Art des Etiketts bestimmt die Kategorie (Person -> namen, Kennung -> vertrag bzw. die
passende Kennungsart, Geburt -> geburt, Anschrift -> strasse/plzort, Kontakt -> telefon/email);
Vertragsdaten (Beginn, Ablauf, Stand …) bleiben stehen. Gremien-Etiketten (Vorstand, Aufsichtsrat,
Geschäftsführer) lesen eine ganze Namensliste, auch über die Folgezeilen derselben Spalte.
"""

from __future__ import annotations

import datetime
import functools
import re
from bisect import bisect_left, bisect_right
from typing import NamedTuple

from . import Treffer, detektor

try:
    from .. import wissen as _wissen
except Exception:  # pragma: no cover - Wissensbasis fehlt (unvollständige Installation)
    _wissen = None

try:
    from .. import muster as _muster
except Exception:  # pragma: no cover
    _muster = None


# ----------------------------------------------------------------------
# Kategorien
# ----------------------------------------------------------------------
KENNUNGS_KATEGORIEN = frozenset({"vertrag", "iban", "bic", "kfz", "fin", "ausweis", "steuerid", "steuernr",
                                 "svnr", "kvnr", "kindergeld", "mandat", "kreditkarte"})
ALLE_KATEGORIEN = frozenset({"namen", "geburt", "strasse", "plzort", "telefon", "email"}) | KENNUNGS_KATEGORIEN

# Sicherheit je Beleg (Etikett + passende Wertform ist stärker als eine reine Musterregel)
SICHERHEIT_ETIKETT = 0.8
SICHERHEIT_SPALTE = 0.8
SICHERHEIT_UNTER = 0.7


# ----------------------------------------------------------------------
# Geometrie: Wörter, Zellen, Zeilen
# ----------------------------------------------------------------------
_NICHT_LEER_RE = re.compile(r"\S+")


class Wort(NamedTuple):
    start: int             # Offset in Seite.text
    ende: int
    x0: float              # geradegerücktes Rechteck (Schräglage ausgeglichen)
    y0: float
    x1: float
    y1: float
    zeile: int             # Zeilen-ID der Seite
    hoehe: float           # Schriftgröße (Textebene) bzw. Höhe der OCR-Wortbox
    ocr: bool


class Zelle(NamedTuple):
    start: int             # Offset in Seite.text (erstes Zeichen des ersten Worts)
    ende: int              # Ende des letzten Worts
    x0: float
    y0: float
    x1: float
    y1: float
    zeile: int
    hoehe: float
    woerter: tuple         # Wort-Objekte


def ueberlappung(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


class Lage:
    """Lage der Wörter einer Seite für die Strukturregeln (einmal je Seite, zwischengespeichert)."""

    def __init__(self, seite):
        self.seite = seite
        self.text = text = seite.text
        abb = seite.abbildung
        zeichen = seite.zeichen
        roh = []                                  # (start, ende, x0, y0, x1, y1, zeile, hoehe, ocr)
        for z in seite.zeilen:
            for m in _NICHT_LEER_RE.finditer(text, z.start, z.ende):
                x0 = y0 = float("inf")
                x1 = y1 = float("-inf")
                hoehe = 0.0
                ocr = False
                for i in range(m.start(), m.end()):
                    g = abb[i] if i < len(abb) else -1
                    if g < 0:
                        continue
                    zc = zeichen[g]
                    r = zc.rect
                    if not (r.x1 > r.x0 and r.y1 > r.y0):
                        continue
                    if r.x0 < x0:
                        x0 = r.x0
                    if r.y0 < y0:
                        y0 = r.y0
                    if r.x1 > x1:
                        x1 = r.x1
                    if r.y1 > y1:
                        y1 = r.y1
                    if zc.quelle != "text":
                        ocr = True
                    else:
                        hoehe = max(hoehe, zc.groesse or (r.y1 - r.y0))
                if x1 < x0:
                    continue
                roh.append((m.start(), m.end(), x0, y0, x1, y1, z.id, hoehe, ocr))
        # Leserichtung: kopfstehende oder gedrehte Scans liefern OCR-Wörter in gedrehter Lage – alles in
        # eine Lage "Text läuft nach rechts, Zeilen nach unten" bringen
        breite, hoehe_seite = float(seite.rect.width or 595.0), float(seite.rect.height or 842.0)
        self.richtung = _richtung(roh)
        if self.richtung:
            roh = [_drehen(e, self.richtung, breite, hoehe_seite) for e in roh]
            if self.richtung in (90, 270):
                breite, hoehe_seite = hoehe_seite, breite
        self.breite_seite, self.hoehe_seite = breite, hoehe_seite
        # OCR-Wörter: Höhe der (gedrehten) Wortbox
        roh = [e if e[7] else e[:7] + (e[5] - e[3],) + e[8:] for e in roh]
        self.schraege = _schraege(roh)
        s = self.schraege
        woerter = []
        for start, ende, x0, y0, x1, y1, zid, hoehe, ocr in roh:
            if s:
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                dx, dy = s * cy, -s * cx
                x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
            woerter.append(Wort(start, ende, x0, y0, x1, y1, zid, hoehe, ocr))
        self.woerter = woerter
        self.wort_anfaenge = [w.start for w in woerter]
        je_zeile: dict = {}
        for w in woerter:
            je_zeile.setdefault(w.zeile, []).append(w)
        self.je_zeile = je_zeile
        self.zellen_je_zeile: dict = {zid: self._zellen(ws) for zid, ws in je_zeile.items()}
        self.zellen = sorted((c for cs in self.zellen_je_zeile.values() for c in cs), key=lambda c: c.start)
        self.zellen_anfaenge = [c.start for c in self.zellen]
        # Zeilen von oben nach unten (Mitte der geradegerückten Wörter)
        mitten = []
        for zid, ws in je_zeile.items():
            y0 = min(w.y0 for w in ws)
            y1 = max(w.y1 for w in ws)
            mitten.append(((y0 + y1) / 2, zid))
        mitten.sort()
        self.zeilen_mitte = [m for m, _ in mitten]
        self.zeilen_folge = [zid for _, zid in mitten]
        self.zeilen_box = {zid: (min(w.x0 for w in ws), min(w.y0 for w in ws), max(w.x1 for w in ws),
                                 max(w.y1 for w in ws)) for zid, ws in je_zeile.items()}
        self.zeilen_ocr = {zid: any(w.ocr for w in ws) for zid, ws in je_zeile.items()}
        hoehen = sorted(w.hoehe for w in woerter if w.hoehe > 0)
        self.hoehe = hoehen[len(hoehen) // 2] if hoehen else 10.0

    def _zellen(self, ws: list) -> list:
        """Wörter einer Zeile -> Zellen: Grenze bei Tabulator (Spaltenlücke des Seitenmodells) oder
        bei einer Lücke über ~1 Zeichenhöhe (OCR-Zeilen haben keine Tabulatoren)."""
        ws = sorted(ws, key=lambda w: w.start)
        zellen, aktuell = [], []
        text = self.text
        for w in ws:
            if aktuell:
                v = aktuell[-1]
                zwischen = text[v.ende:w.start]
                h = max(v.hoehe, w.hoehe, 1.0)
                grenze = 1.0 * h if (v.ocr or w.ocr) else 1.3 * h
                if "\t" in zwischen or (w.x0 - v.x1) > grenze or w.x0 < v.x0 - 0.5 * h:
                    zellen.append(self._zelle(aktuell))
                    aktuell = []
            aktuell.append(w)
        if aktuell:
            zellen.append(self._zelle(aktuell))
        return zellen

    @staticmethod
    def _zelle(ws: list) -> Zelle:
        return Zelle(ws[0].start, ws[-1].ende, min(w.x0 for w in ws), min(w.y0 for w in ws),
                     max(w.x1 for w in ws), max(w.y1 for w in ws), ws[0].zeile,
                     max(w.hoehe for w in ws), tuple(ws))

    # -- Zugriffe ---------------------------------------------------------
    def zelle_bei(self, pos: int):
        """Zelle, die die Textposition enthält (oder None)."""
        i = bisect_right(self.zellen_anfaenge, pos) - 1
        if i >= 0 and self.zellen[i].start <= pos < self.zellen[i].ende:
            return self.zellen[i]
        return None

    def woerter_in(self, start: int, ende: int) -> list:
        i = bisect_left(self.wort_anfaenge, start)
        aus = []
        while i < len(self.woerter) and self.woerter[i].start < ende:
            if self.woerter[i].ende > start:
                aus.append(self.woerter[i])
            i += 1
        # ein Wort, das vor `start` beginnt und hineinragt
        j = bisect_left(self.wort_anfaenge, start) - 1
        if j >= 0 and self.woerter[j].ende > start:
            aus.insert(0, self.woerter[j])
        return aus

    def box(self, start: int, ende: int):
        ws = self.woerter_in(start, ende)
        if not ws:
            return None
        return (min(w.x0 for w in ws), min(w.y0 for w in ws), max(w.x1 for w in ws), max(w.y1 for w in ws))

    def zeilen_darunter(self, zid: int, max_abstand: float) -> list:
        """Zeilen-IDs unterhalb einer Zeile (nach Lage), deren Mitte höchstens max_abstand unter der
        Unterkante der Zeile liegt – von oben nach unten."""
        box = self.zeilen_box.get(zid)
        if box is None:
            return []
        unten = box[3]
        mitte = (box[1] + box[3]) / 2
        i = bisect_right(self.zeilen_mitte, mitte + 0.3)
        aus = []
        while i < len(self.zeilen_mitte) and self.zeilen_mitte[i] - unten <= max_abstand:
            if self.zeilen_folge[i] != zid and self.zeilen_mitte[i] > mitte + 0.4 * (box[3] - box[1]):
                aus.append(self.zeilen_folge[i])
            i += 1
        return aus

    def zeilen_darueber(self, zid: int, max_abstand: float) -> list:
        """Zeilen-IDs oberhalb (nächste zuerst), Mitte höchstens max_abstand über der Oberkante."""
        box = self.zeilen_box.get(zid)
        if box is None:
            return []
        oben = box[1]
        mitte = (box[1] + box[3]) / 2
        i = bisect_left(self.zeilen_mitte, mitte - 0.3) - 1
        aus = []
        while i >= 0 and oben - self.zeilen_mitte[i] <= max_abstand:
            if self.zeilen_folge[i] != zid and self.zeilen_mitte[i] < mitte - 0.4 * (box[3] - box[1]):
                aus.append(self.zeilen_folge[i])
            i -= 1
        return aus


def _richtung(roh: list) -> int:
    """Leserichtung der Zeilen (0, 90, 180, 270 Grad) aus erstem und letztem Wort jeder Zeile; 0, wenn
    keine Richtung eindeutig überwiegt."""
    je_zeile: dict = {}
    for eintrag in roh:
        je_zeile.setdefault(eintrag[6], []).append(eintrag)
    stimmen: dict = {}
    for ws in je_zeile.values():
        if len(ws) < 2:
            continue
        ws = sorted(ws, key=lambda w: w[0])
        a, b = ws[0], ws[-1]
        dx = (b[2] + b[4]) / 2 - (a[2] + a[4]) / 2
        dy = (b[3] + b[5]) / 2 - (a[3] + a[5]) / 2
        if abs(dx) + abs(dy) < 30:
            continue
        if abs(dx) >= abs(dy):
            r = 0 if dx > 0 else 180
        else:
            r = 90 if dy > 0 else 270
        stimmen[r] = stimmen.get(r, 0) + 1
    if not stimmen:
        return 0
    r, n = max(stimmen.items(), key=lambda kv: kv[1])
    if r == 0 or n < 3 or n < 0.6 * sum(stimmen.values()):
        return 0
    return r


def _drehen(e: tuple, richtung: int, breite: float, hoehe: float) -> tuple:
    """Wortbox in die Leselage drehen (Text nach rechts, Zeilen nach unten)."""
    start, ende, x0, y0, x1, y1 = e[:6]
    if richtung == 180:
        x0, y0, x1, y1 = breite - x1, hoehe - y1, breite - x0, hoehe - y0
    elif richtung == 90:                      # Text läuft nach unten
        x0, y0, x1, y1 = y0, breite - x1, y1, breite - x0
    elif richtung == 270:                     # Text läuft nach oben
        x0, y0, x1, y1 = hoehe - y1, x0, hoehe - y0, x1
    return (start, ende, x0, y0, x1, y1) + tuple(e[6:])


def _schraege(roh: list) -> float:
    """Schräglage der Seite (dy/dx der Zeilen) aus erstem und letztem Wort langer Zeilen; 0 bei
    geraden Seiten. Begrenzt auf ±0,1 (≈ 6°)."""
    je_zeile: dict = {}
    for eintrag in roh:
        je_zeile.setdefault(eintrag[6], []).append(eintrag)
    werte = []
    for ws in je_zeile.values():
        if len(ws) < 2:
            continue
        a = min(ws, key=lambda w: w[2])
        b = max(ws, key=lambda w: w[4])
        ax, bx = (a[2] + a[4]) / 2, (b[2] + b[4]) / 2
        if bx - ax < 80:
            continue
        ay, by = (a[3] + a[5]) / 2, (b[3] + b[5]) / 2
        werte.append((by - ay) / (bx - ax))
    if len(werte) < 3:
        return 0.0
    werte.sort()
    s = werte[len(werte) // 2]
    if abs(s) < 0.003:
        return 0.0
    # nur eine einheitliche Neigung zählt (digitale Seiten mit versetzten Formularwerten: keine Schräglage)
    passend = sum(1 for w in werte if abs(w - s) <= max(0.002, 0.35 * abs(s)))
    if passend < 0.6 * len(werte):
        return 0.0
    return max(-0.1, min(0.1, s))


def lage(seite) -> Lage:
    """Lage einer Seite (zwischengespeichert am Seitenobjekt, solange sich der Text nicht ändert)."""
    zw = getattr(seite, "_struktur_lage", None)
    if zw is None or zw.text is not seite.text:
        zw = Lage(seite)
        try:
            seite._struktur_lage = zw
        except AttributeError:
            pass
    return zw


# ----------------------------------------------------------------------
# Etiketten
# ----------------------------------------------------------------------
ARTEN = ("person", "kennung", "datum_geburt", "adresse", "kontakt", "vertragsdaten")


class Etikett(NamedTuple):
    start: int             # Offset in Seite.text
    ende: int
    arten: frozenset       # {"person", "kennung", "datum_geburt", "adresse", "kontakt", "vertragsdaten",
                           #  "neutral", "laufend"}
    kategorie: str | None  # Zielkategorie einer Kennung (vertrag, iban, kfz …) bzw. telefon/email
    eintrag: str           # Listeneintrag (bzw. das Wort selbst)


# Kennungs-Etikett -> Kategorie (auf der Vergleichsform: klein, ohne Diakritika, Trenner = Leerzeichen)
_KENNUNG_KATEGORIE = [
    (re.compile(r"\biban\b"), "iban"),
    (re.compile(r"\b(?:bic|swift)\b"), "bic"),
    (re.compile(r"egk\b|krankenversicherten|krankenversicherungs ?n|\bkv ?n|\bkvnr\b|versicherten ?n|versicherten ?id"),
     "kvnr"),
    (re.compile(r"kennzeichen|\bkennz\b|\bkz\b|kfz zeichen"), "kfz"),
    (re.compile(r"\b(?:fin|vin)\b|fahrgestell|fahrzeug ?ident"), "fin"),
    (re.compile(r"ausweis|reisepass|\bpass\b|\bpass ?n|fuhrerschein"), "ausweis"),
    (re.compile(r"\bust\b|umsatzsteuer|wirtschafts ?ident|\bw idnr\b"), "steuernr"),
    (re.compile(r"steuer ?id|steueridentifikation|steuer identifikation|steuerliche|\bidnr\b|\bid ?nr\b|"
                r"identifikationsnummer|\btin\b|tax id"), "steuerid"),
    (re.compile(r"steuer ?n|\bst ?nr\b|\bstnr\b"), "steuernr"),
    (re.compile(r"sozialversicherung|\bsv ?n|\bsvnr\b|renten ?n|rentennr|rentenversicherungs ?n|\brv ?n|\brvnr\b|"
                r"renten ?zeichen|\bahv"), "svnr"),
    (re.compile(r"kindergeld|\bkg nummer"), "kindergeld"),
    (re.compile(r"mandat"), "mandat"),
    (re.compile(r"kreditkarte|karten ?n|kartennr"), "kreditkarte"),
]
# Kennungs-Etiketten, deren Wert NICHT zur Person gehört (Kennung des Gläubigers/Versicherers)
_KENNUNG_FREMD_RE = re.compile(r"glaubiger|bankleitzahl|\bblz\b|\bust\b|umsatzsteuer|wirtschafts ?ident|\bw idnr\b|"
                               r"bankverbindung|kontoverbindung")
_KONTAKT_TELEFON_RE = re.compile(r"tel|fax|mobil|handy|ruf|durchwahl|\bdw\b|festnetz|phone|cell|whatsapp|"
                                 r"erreichbar|threema|telegram|signal")
_KONTAKT_EMAIL_RE = re.compile(r"mail|e post|de mail|\bbea\b")

# zusammengesetzte Nummern-Etiketten, die in keiner Liste stehen ("Bestandsnummer", "Mitglieds-ID")
_NUMMERN_WORT_RE = re.compile(
    r"(?<![\w.\-])([A-ZÄÖÜa-zäöü][\wäöüß]*(?:[-.][\wäöüßÄÖÜ]+)*?(?:[Nn]ummer|NUMMER|-?[Nn]r\.?|-?NR\.?|-ID|-Id|"
    r"[Kk]ennung|KENNUNG|[Kk]ennziffer))(?![\w])")
_NUMMERN_FREMD = re.compile(
    r"(?i)^(?:telefon|tel|fax|telefax|ruf|handy|mobil|mobilfunk|festnetz|haus|artikel|art|position|pos|seiten?|"
    r"version|tarif|produkt|bankleit|material|modell|typ|zimmer|raum|kapitel|absatz|paragraph|ziffer|zeilen?|"
    r"lfd|laufende|fortlaufende|kenn|bestell|serien|geräte|gerate|zähler|zahler|post|hnr|nr)[-.]?")

# neutrale Spaltenköpfe (kein Personenbezug): trennen Kopfzeilen in Spalten, Werte bleiben stehen
NEUTRALE_KOEPFE = frozenset("""
sparte versicherer gesellschaft tarif tarife produkt produkte beitrag beiträge beitrage betrag beträge betrage
netto brutto summe gesamt gesamtbetrag zwischensumme steuer verssteuer versst versicherungsteuer mwst ust rabatt
zuschlag zuschläge mahngebühr mahngebühren gebühr gebühren kosten leistung leistungen erstattung erstattungsbetrag
eigenanteil selbstbeteiligung sb status rolle bemerkung bemerkungen hinweis hinweise art typ beschreibung
bezeichnung position pos menge anzahl einheit preis einzelpreis gesamtpreis zahlweise zahlungsweise deckung
deckungssumme versicherungssumme prozent anteil quote rendite zins zinsen saldo soll haben währung eur euro wert
kurs stück diagnose behandlung goä ziffer faktor ergebnis kategorie gruppe klasse sf-klasse regionalklasse
typklasse fahrzeug hersteller modell baujahr km kilometer fahrleistung objekt risiko umfang leistungsart
selbstbehalt beitragssatz monatsbeitrag jahresbeitrag zahlbetrag differenz bisher neu alt aktuell
vorher nachher änderung anderung zeitart arbeitgeber tätigkeit tatigkeit beruf zeitraum laufzeit dauer
""".split())

_LAUFEND = frozenset({"nr", "nr.", "no", "no.", "pos", "pos.", "lfd", "lfd.", "lfd. nr.", "lfd nr", "#", "nummer"})
_GREMIUM_RE = re.compile(
    r"(?i)^(?:vorst(?:a|ä)nd(?:e|s)?|vorstandsvorsitzende[r]?|aufsichtsrat(?:s|es)?|aufsichtsratsvorsitzende[r]?|"
    r"vorsitz(?:ende[r]?)?(?: des)?(?: aufsichtsrat(?:s|es)?| vorstand(?:s|es)?)?|geschäftsführer(?:in|innen)?|"
    r"geschäftsführung|geschäftsleitung|gesellschafter(?:in)?|beirat|verwaltungsrat|vertreten durch|"
    r"vertretungsberechtigt(?:e[r]?)?|inhaber(?:in)?|partner|prokurist(?:in)?|prokura)$")


def _vergleichsform(text: str) -> str:
    if _wissen is not None:
        try:
            return " ".join(_wissen.normalisieren(re.sub(r"[-./()]+", " ", text)).split())
        except Exception:
            pass
    return " ".join(re.sub(r"[-./()]+", " ", text).casefold().split())


def kennung_kategorie(eintrag: str) -> str | None:
    """Zielkategorie eines Kennungs-Etiketts; None für fremde Kennungen (Gläubiger-ID, BLZ)."""
    v = _vergleichsform(eintrag)
    if _KENNUNG_FREMD_RE.search(v):
        return None
    for regel, kategorie in _KENNUNG_KATEGORIE:
        if regel.search(v):
            return kategorie
    return "vertrag"


def kontakt_kategorie(eintrag: str) -> str | None:
    v = _vergleichsform(eintrag)
    if _KONTAKT_EMAIL_RE.search(v):
        return "email"
    if _KONTAKT_TELEFON_RE.search(v):
        return "telefon"
    return None


def _etiketten_roh(text: str) -> list:
    """(start, ende, art, eintrag) aller Listen-Etiketten im Text (ohne Zeilen-Überschreitung)."""
    aus = []
    if _wissen is None:
        return aus
    for art in ARTEN:
        try:
            vorkommen = _wissen.finde(text, f"etiketten_{art}")
        except Exception:
            continue
        for v in vorkommen:
            aus.append((v.start, v.ende, art, v.eintrag))
    for m in _NUMMERN_WORT_RE.finditer(text):
        wort = m.group(1)
        if len(wort) < 5 or _NUMMERN_FREMD.match(wort):
            continue
        aus.append((m.start(1), m.end(1), "kennung", wort))
    return aus


def etiketten(seite) -> list:
    """Etiketten einer Seite (nach Lage geordnet, nicht überlappend, nie über eine Zellgrenze)."""
    zw = getattr(seite, "_struktur_etiketten", None)
    if zw is not None and zw[0] is seite.text:
        return zw[1]
    text = seite.text
    lg = lage(seite)
    roh = _etiketten_roh(text)
    # neutrale Spaltenköpfe und laufende Nummern
    for m in re.finditer(r"(?<![\w.])([A-Za-zÄÖÜäöüß][\w.\-äöüß]*|#)(?![\w])", text):
        w = m.group(1)
        k = w.casefold()
        if k in NEUTRALE_KOEPFE or k.rstrip(".") in NEUTRALE_KOEPFE:
            roh.append((m.start(1), m.end(1), "neutral", w))
        elif k in _LAUFEND or k.rstrip(".") in _LAUFEND:
            roh.append((m.start(1), m.end(1), "laufend", w))
    # je Spanne alle Arten sammeln; überlappende Spannen: die längere gewinnt
    je_spanne: dict = {}
    for s, e, art, eintrag in roh:
        if "\t" in text[s:e] or "\n" in text[s:e]:
            continue
        if s > 0 and (text[s - 1].isalnum() or text[s - 1] in "-/&"):
            continue                                  # mitten im Wort ("Ehm-Welk-Str.")
        if art == "vertragsdaten" and text[s:e].islower() and len(text[s:e]) <= 5:
            continue                                  # "am", "ab", "bis", "per", "seit": Funktionswörter
        a = lg.zelle_bei(s)
        if a is None or e > a.ende:
            continue                                  # über eine Zellgrenze hinweg: kein Etikett
        je_spanne.setdefault((s, e), []).append((art, eintrag))
    spannen = sorted(je_spanne, key=lambda se: (se[0], -(se[1] - se[0])))
    behalten = []
    for s, e in spannen:
        if behalten and s < behalten[-1][1]:
            if e - s > behalten[-1][1] - behalten[-1][0]:
                behalten[-1] = (s, e)
            continue
        behalten.append((s, e))
    aus = []
    for s, e in behalten:
        arten = {art for art, _ in je_spanne[(s, e)]}
        eintrag = je_spanne[(s, e)][0][1]
        if "laufend" in arten and len(arten) > 1:
            arten.discard("adresse")                  # "Nr." ist Spaltenkopf, keine Hausnummer
        if arten & {"person", "kennung", "datum_geburt", "adresse", "kontakt", "vertragsdaten"}:
            arten.discard("neutral")
            arten.discard("laufend") if "kennung" in arten else None
        kategorie = None
        if "kennung" in arten:
            kategorie = kennung_kategorie(next(en for art, en in je_spanne[(s, e)] if art == "kennung"))
            if kategorie is None:
                arten.discard("kennung")
                arten.add("neutral")
        elif "kontakt" in arten:
            kategorie = kontakt_kategorie(next(en for art, en in je_spanne[(s, e)] if art == "kontakt"))
        if arten <= {"adresse", "laufend", "neutral"} and text[s:e].casefold().rstrip(".") in ("nr", "nummer", "no"):
            # "Lebensversicherung Nr. …", "Personalausweis (Nr. …)": Nr. hinter einem Substantiv ist eine Kennung
            vor = _NR_VORWORT_RE.search(text, max(lg.zelle_bei(s).start if lg.zelle_bei(s) else 0, s - 60), s)
            if vor and not _STRASSENWORT_RE.search(vor.group(1)):
                stamm = vor.group(1)
                kategorie = kennung_kategorie(f"{stamm} Nr.")
                if kategorie is not None:
                    arten, eintrag = {"kennung"}, f"{stamm} Nr."
        aus.append(Etikett(s, e, frozenset(arten), kategorie, eintrag))
    try:
        seite._struktur_etiketten = (text, aus)
    except AttributeError:
        pass
    return aus


PII_ARTEN = frozenset({"person", "kennung", "datum_geburt", "adresse", "kontakt"})


def etikett_fuer_text(text: str, mit_vertragsdaten: bool = False):
    """Etikett (Arten, Kategorie, Eintrag) für einen frei stehenden Bezeichner – Formularfeld, zweizeiliger
    Spaltenkopf ("Versicherungs-" + "nummer") – oder None. Der Bezeichner muss ganz (bzw. zur Hälfte) ein
    Etikett der Wissensbasis sein; zusammengesetzte Nummern-Wörter ("Bestandsnummer") zählen als Kennung."""
    if _wissen is None or not text:
        return None
    sauber = text.strip().rstrip(":").strip()
    if not sauber:
        return None
    arten = set()
    eintrag = None
    for art in ARTEN:
        try:
            e = _wissen.index(f"etiketten_{art}").eintrag_fuer(sauber)
        except Exception:
            e = None
        if e is None:
            try:
                vorkommen = _wissen.finde(sauber, f"etiketten_{art}")
            except Exception:
                vorkommen = []
            if vorkommen:
                v = max(vorkommen, key=lambda v: v.ende - v.start)
                if v.ende - v.start >= 0.5 * len(sauber) and not (art == "vertragsdaten" and v.text.islower()):
                    e = v.eintrag
        if e is not None:
            arten.add(art)
            eintrag = eintrag or e
    if not arten and _NUMMERN_WORT_RE.fullmatch(sauber) and not _NUMMERN_FREMD.match(sauber):
        arten, eintrag = {"kennung"}, sauber
    if not arten:
        k = sauber.casefold()
        if k in NEUTRALE_KOEPFE or k.rstrip(".") in NEUTRALE_KOEPFE:
            return Etikett(0, 0, frozenset({"neutral"}), None, sauber)
        return None
    if arten == {"vertragsdaten"} and not mit_vertragsdaten:
        return None
    kategorie = None
    if "kennung" in arten:
        kategorie = kennung_kategorie(eintrag)
        if kategorie is None:
            return None
    elif "kontakt" in arten:
        kategorie = kontakt_kategorie(eintrag)
    return Etikett(0, 0, frozenset(arten), kategorie, eintrag)
_NR_VORWORT_RE = re.compile(r"([A-ZÄÖÜ][\wäöüß\-]{3,})[ \t]*\(?[ \t]*$")
_STRASSENWORT_RE = re.compile(r"(?i)(?:str|straße|strasse|weg|platz|allee|gasse|ring|damm|ufer|haus|zimmer|raum|"
                              r"seite|position|artikel|tarif|produkt|anlage|ziffer|abschnitt|paragraph)$")


# ----------------------------------------------------------------------
# Wertformen
# ----------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöü0-9][A-Za-zÄÖÜäöüß0-9\-./]*")
_BETRAG_RE = re.compile(r"[-+]?\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|[-+]?\d+,\d{1,2}|[-+]?\d{1,3}(?:'\d{3})+")
_DATUM_VOLL_RE = re.compile(r"\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})|"
                            r"\d{1,2}\.\d{4}|\d{2}/\d{4}")
_SPERRE = frozenset({"EUR", "USD", "CHF", "GBP", "IBAN", "BIC", "BLZ", "NR", "TEL", "FAX", "UHR", "KM", "AG", "KG",
                     "SE", "GMBH", "VVG", "SGB", "BGB", "AVB", "PS", "KW", "CM", "MM", "QM", "ST", "STK", "MIO",
                     "MRD", "TSD", "CO", "BZW", "UND", "VON", "VOM", "BIS", "AB", "AM", "IM", "IN", "ZU", "DE",
                     "DM", "PDF", "ID", "NO", "ABS", "NRN", "SEITE"})


def ist_betrag(tok: str) -> bool:
    return bool(_BETRAG_RE.fullmatch(tok))


def ist_datum_text(tok: str) -> bool:
    return bool(_DATUM_VOLL_RE.fullmatch(tok))


def _kennung_token(tok: str, erstes: bool, naechstes: str = "") -> bool:
    if not tok:
        return False
    if len(tok) == 1 and tok.isalpha():
        # einzelner Buchstabe: nur zwischen bzw. vor Ziffergruppen ("03 241061 C 515", "HL V 591")
        return tok.isupper() and any(c.isdigit() for c in naechstes)
    if any(c.isdigit() for c in tok):
        if ist_betrag(tok) or ist_datum_text(tok):
            return False
        if tok.endswith("%"):
            return False
        return True
    if not tok.isalpha():
        # Buchstaben mit Trennern, aber ohne Ziffer ("KH-AB"): nur als Präfix
        teile = [t for t in re.split(r"[-./]", tok) if t]
        return bool(teile) and all(t.isupper() and len(t) <= 4 for t in teile) and erstes
    return tok.isupper() and len(tok) <= 4 and tok not in _SPERRE


def kennung_spanne(text: str, pos: int, grenze: int, min_ziffern: int = 3):
    """Kennung ab pos (führender Leerraum wird übersprungen): Folge von Tokens mit Ziffern bzw. kurzen
    Großbuchstaben-Kürzeln ("KH 0815 4471 2", "LV/24/4058468", "D-Y3TV-NW64X-52", "7 111 562 795"),
    durch einfache Leerzeichen getrennt. Endet an Wort, Satzzeichen, Tabulator, Zeilenende.
    Keine Daten, Beträge, Jahreszahlen. Liefert (start, ende) oder None."""
    i = pos
    while i < grenze and text[i] in " \t":
        i += 1
    tokens = []
    j = i
    while j < grenze:
        m = _TOKEN_RE.match(text, j, grenze)
        if not m:
            break
        roh = m.group(0)
        kern = roh.rstrip(".-/")
        n = _TOKEN_RE.match(text, m.end() + 1, grenze) if m.end() < grenze and text[m.end()] == " " else None
        if not _kennung_token(kern, not tokens, n.group(0) if n else ""):
            break
        tokens.append((m.start(), m.start() + len(kern)))
        j = m.end()
        if len(kern) != len(roh):
            break                                   # Satzzeichen am Ende beendet den Wert
        if j + 1 < grenze and text[j] == " " and text[j + 1] not in " \t\n":
            j += 1
            continue
        break
    while tokens and not any(c.isdigit() for c in text[tokens[-1][0]:tokens[-1][1]]):
        tokens.pop()
    if not tokens:
        return None
    s, e = tokens[0][0], tokens[-1][1]
    wert = text[s:e]
    ziffern = sum(c.isdigit() for c in wert)
    if ziffern < min_ziffern or len(wert) < 4:
        return None
    kompakt = wert.replace(" ", "")
    if kompakt.isdigit() and len(kompakt) == 4 and kompakt[:2] in ("19", "20"):
        return None                                 # Jahreszahl
    if ist_datum_text(kompakt) or ist_betrag(wert):
        return None
    return s, e


def ist_kennungsform(wert: str, min_ziffern: int = 5) -> bool:
    """Kennungsform für Spalten OHNE Etikett: Ziffern gemischt mit Buchstaben/Trennern bzw. lange
    Ziffernfolge – keine Beträge, Prozente, Daten, Postleitzahlen, Jahreszahlen, Uhrzeiten."""
    w = wert.strip()
    if not w or len(w) > 40:
        return False
    sp = kennung_spanne(w, 0, len(w), 3)
    if sp is None or sp != (0, len(w)):
        return False
    ziffern = sum(c.isdigit() for c in w)
    if ziffern < min_ziffern:
        return False
    kompakt = re.sub(r"[ ]", "", w)
    if kompakt.isdigit() and len(kompakt) <= 5:
        return False                                # Postleitzahl, kleine Zahl
    if re.fullmatch(r"\d{1,2}:\d{2}", w):
        return False
    return True


# -- Daten --------------------------------------------------------------
_MONATE = {"januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "mär": 3, "mrz": 3, "april": 4,
           "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8, "aug": 8,
           "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10, "november": 11, "nov": 11,
           "dezember": 12, "dez": 12}
_MONAT_ALT = "|".join(sorted(_MONATE, key=len, reverse=True))
_DATUM_RE = re.compile(
    r"(?<![\d.])(?:(\d{1,2})\.[ ]?(\d{1,2})\.[ ]?((?:19|20)\d{2}|\d{2})"
    r"|(\d{1,2})\.?[ ]?(" + _MONAT_ALT + r")\.?[ ]?((?:19|20)\d{2})"
    r"|((?:19|20)\d{2})-(\d{2})-(\d{2})"
    r"|(\d{1,2})/(\d{1,2})/((?:19|20)\d{2}))(?![\d])", re.IGNORECASE)


def _heute() -> datetime.date:
    return datetime.date.today()


def datum_zerlegen(m) -> tuple | None:
    g = m.groups()
    try:
        if g[0]:
            t, mo, j = int(g[0]), int(g[1]), int(g[2])
        elif g[3]:
            t, mo, j = int(g[3]), _MONATE[g[4].casefold()], int(g[5])
        elif g[6]:
            j, mo, t = int(g[6]), int(g[7]), int(g[8])
        else:
            t, mo, j = int(g[9]), int(g[10]), int(g[11])
    except (KeyError, ValueError, TypeError):
        return None
    if j < 100:
        j += 1900 if j > _heute().year % 100 else 2000
    try:
        return datetime.date(j, mo, t)
    except ValueError:
        return None


def datums_spannen(text: str, start: int, ende: int) -> list:
    """[(s, e, datum)] gültiger Datumsangaben im Bereich."""
    aus = []
    for m in _DATUM_RE.finditer(text, start, ende):
        d = datum_zerlegen(m)
        if d is not None:
            aus.append((m.start(), m.end(), d))
    return aus


def geburtsdatum_plausibel(d: datetime.date) -> bool:
    heute = _heute()
    return d <= heute and d.year >= heute.year - 125


# -- Namen ----------------------------------------------------------------
_ANREDEN = frozenset({"herr", "herrn", "hr.", "frau", "fr.", "fräulein", "familie", "fam.", "eheleute", "ehepaar",
                      "mr.", "mrs.", "ms.", "monsieur", "madame", "signor", "signora", "señor", "señora"})
_TITEL_RE = re.compile(r"(?i)^(?:doktor|doktorin|professor|professorin|kollege|kollegin|kollegen|dr|prof|med|jur|"
                       r"rer|nat|phil|pol|oec|habil|dent|vet|univ|dipl|mag|ing|kfm|lic|"
                       r"mba|msc|m\.sc|b\.sc|bsc|ba|ma|ll\.m|h\.c|em|sen|jun|apl|pd|ra|stb|wp)\.?$|"
                       r"^(?:dr|dipl|prof)\.[-\w.]*$|^(?:dipl|med|dr)\.-?[a-zäöü]+\.?$")
PARTIKEL = frozenset({"von", "van", "de", "der", "den", "dem", "des", "del", "della", "di", "da", "du", "le", "la",
                      "zu", "zum", "zur", "vom", "ten", "ter", "al", "el", "bin", "ibn", "y", "dos", "das", "do",
                      "af", "av", "op"})
# großgeschriebene Funktionswörter (Satzanfang, Anrede, Grußformel), die nie Teil eines Namens sind
FUNKTIONSWOERTER = frozenset("""
ihr ihre ihren ihrem ihrer ihres sie wir ich er es der die das den dem des ein eine einen einem einer mit bei
für fur von vom zu zum zur im am an auf aus nach bitte sehr liebe lieber hallo guten tag herzliche herzlichen
viele beste freundliche freundlichen danke vielen und oder mein meine meinen meinem unser unsere unseren
dieser diese dieses siehe anlage anlagen seite betreff datum ort uhr kopie vorab per via cc bcc an
damen herren kolleginnen kollegen kunden kundinnen mitglieder eltern freunde team alle zusammen leute
heute morgen gestern
""".split())
# Wochentage und Monate: keine Orte ("Montag, 12.03.2025"), als Name nur mit Namenskontext ("Freitag, Jonas")
DATUMSWOERTER = frozenset("""
montag dienstag mittwoch donnerstag freitag samstag sonnabend sonntag januar februar märz april mai juni juli
august september oktober november dezember
""".split())
# Adelstitel gehören zum Namen ("Freiherr von Rotenstein", "GRAF, LISELOTTE" ist ein Nachname)
ADELSTITEL = frozenset({"freiherr", "freifrau", "freiin", "graf", "gräfin", "grafin", "baron", "baronin", "prinz",
                        "prinzessin", "fürst", "fürstin", "furst", "furstin", "herzog", "herzogin", "edler",
                        "edle", "ritter", "reichsgraf", "erbprinz"})
_FIRMEN_TOKEN = frozenset({"gmbh", "ag", "kg", "mbh", "ohg", "gbr", "se", "eg", "e.g.", "e.v.", "ev", "vvag",
                           "a.g.", "kgaa", "ug", "ltd", "ltd.", "inc", "inc.", "co", "co.", "&", "partg", "aör",
                           "versicherung", "versicherungen", "bank", "sparkasse", "kasse", "gesellschaft",
                           "service", "kundenservice", "team", "abteilung"})
# Wortenden von Betrieben und Einrichtungen ("Löwen-Apotheke", "Physiotherapie", "Zahnarztpraxis")
_BETRIEB_ENDUNG_RE = re.compile(r"(?i)(?:apotheke|praxis|klinik|klinikum|zentrum|therapie|labor|institut|"
                                r"versicherung|kasse|bank|werkstatt|autohaus|service|gmbh|büro|buero|kanzlei|"
                                r"handel|bäckerei|metzgerei|gruppe|verwaltung)$")
_NAME_TOKEN_RE = re.compile(r"[^\W\d_][\w'’]*(?:\.?-[\w'’]+|\.[\w'’]+)*\.?")


def _wort_ist_titel(w: str) -> bool:
    return bool(_TITEL_RE.match(w)) or (_wissen is not None and len(w) > 1 and _wissen.ist_anrede_titel(w)
                                        and w.casefold() not in ("herr", "herrn", "frau"))


_PRAEFIX_NAME_RE = re.compile(r"(?:al|el|ad|ed|as|at|ar|an|bin|ibn|abu|d)['’-]([A-ZÄÖÜ][\w'’\-]+)$")
_NAMENSFORM_RE = re.compile(r"(?:Mc|Mac|De|Di|Da|Du|Le|La|Van|Von|O['’]|D['’]|Al-|El-)?[^\W\d_][^\W\d_'’]*"
                            r"(?:['’][^\W\d_]+)?")


def _namensform(wort: str) -> bool:
    """Schreibweise eines Namensworts: Titelform ("Müller"), Versalien ("MÜLLER") oder mit bekannter
    Vorsilbe ("McDonald", "DeLuca", "O'Brien") – keine OCR-Bruchstücke wie "LeaFR"."""
    for teil in wort.split("-"):
        if not teil:
            continue
        if teil.isupper() or teil[1:].islower() or not any(c.isalpha() for c in teil[1:]):
            continue
        m = _NAMENSFORM_RE.fullmatch(teil)
        if not m or sum(1 for c in teil[1:] if c.isupper()) > 1 or teil[-1].isupper():
            return False
    return True


@functools.lru_cache(maxsize=65536)
def wort_namensartig(w: str) -> bool:
    """Großgeschriebenes Wort, das ein Name sein kann: bekannter Vor-/Nachname oder weder
    Allerweltswort noch Feldbezeichner."""
    kern = w.strip(".,;:'’")
    if kern.casefold() in _ANREDEN or kern.casefold().rstrip(".") in ("herr", "herrn", "frau"):
        return False
    if len(kern) < 2 or not kern[0].isupper() or not _namensform(kern):
        return False
    if _wissen is None:
        return True
    try:
        if _wissen.ist_vorname(kern) or _wissen.ist_nachname(kern):
            return True
        titel = kern.title() if kern.isupper() else kern
        if _wissen.ist_vorname(titel) or _wissen.ist_nachname(titel):
            return True
        if _wissen.ist_allerweltswort(titel) or _wissen.ist_allowlist(titel):
            return False
        for art in ARTEN:
            if _wissen.index(f"etiketten_{art}").eintrag_fuer(titel):
                return False
    except Exception:
        return True
    return kern.casefold() not in NEUTRALE_KOEPFE


@functools.lru_cache(maxsize=65536)
def wort_bekannter_name(w: str) -> bool:
    kern = w.strip(".,;:'’")
    if _wissen is None or len(kern) < 2:
        return False
    titel = kern.title() if kern.isupper() else kern
    try:
        if _wissen.ist_vorname(titel) and not _wissen.ist_vorname_mehrdeutig(titel):
            return True
        return _wissen.ist_nachname(titel) and not _wissen.ist_mehrdeutig(titel)
    except Exception:
        return False


class NamensSpanne(NamedTuple):
    start: int
    ende: int
    woerter: int            # Anzahl echter Namenswörter
    bekannt: bool           # mindestens ein bekannter Vor-/Nachname
    komma: bool             # Form "Nachname, Vorname"


def _wissen_frage(frage: str, wort: str) -> bool:
    if _wissen is None:
        return False
    titel = wort.title() if wort.isupper() else wort
    try:
        return bool(getattr(_wissen, frage)(titel))
    except Exception:
        return False


def _vorname_nachname_davor(text: str, woerter: list) -> bool:
    """Steht vor einem Komma schon "Vorname Nachname" (zwei Namenswörter, das erste ein bekannter Vorname)?
    Dann zählt das Komma Personen auf ("Katarzyna Kołodziej, Dipl.-Ing. Jörg Ziegler") und leitet keine
    Form "Nachname, Vorname" ein."""
    namen = [w for w in woerter if w[2] == "name"]
    return len(namen) >= 2 and _wissen_frage("ist_vorname", text[namen[0][0]:namen[0][1]].split("-")[0])


def _nachname_hinten(text: str, hinten: list) -> bool:
    """Hinter dem Komma "Vorname Nachname" ("Biedermann, Liselotte Schmidt")? Dann ist das Komma ein
    Aufzählungskomma: bei "Nachname, Vorname(n)" stehen hinter dem Komma nur Vornamen."""
    namen = [text[a:b] for a, b, art in hinten if art == "name"]
    if len(namen) < 2:
        return False
    letzter = namen[-1]
    return _wissen_frage("ist_vorname", namen[0].split("-")[0]) and _wissen_frage("ist_nachname", letzter) \
        and not _wissen_frage("ist_vorname", letzter.split("-")[0])


def namen_spanne(text: str, pos: int, grenze: int, komma: bool = True, max_woerter: int = 6):
    """Name ab pos: Anreden/Titel vorn werden übersprungen (gehören nicht zur Spanne), dann groß
    geschriebene Wörter, Initialen, Partikel (von, van der …), höchstens ein Komma ("Nachname, Vorname"
    mit höchstens drei Wörtern dahinter). Endet an Ziffern, Satzzeichen, kleingeschriebenen Wörtern,
    Feldbezeichnern, Funktions- und Allerweltswörtern. Liefert NamensSpanne oder None."""
    i = pos
    while i < grenze and text[i] in " \t":
        i += 1
    woerter = []          # (start, ende, art) art: "name" | "partikel" | "titel" | "initiale"
    komma_index = None    # Index in woerter, ab dem der Teil hinter dem Komma beginnt
    j = i
    while j < grenze:
        m = _NAME_TOKEN_RE.match(text, j, grenze)
        if not m:
            break
        tok = m.group(0)
        ts, te = m.start(), m.end()
        k = tok.casefold()
        echte = sum(1 for w in woerter if w[2] in ("name", "initiale"))
        vor_komma = te + 2 < grenze and text[te] == "," and text[te + 1] == " " and text[te + 2].isupper()
        if k.rstrip(".") in ADELSTITEL and tok[0].isupper():
            woerter.append((ts, te, "name" if vor_komma else "adel"))
            j = te
        elif not woerter and (k in _ANREDEN or _wort_ist_titel(tok)) and not vor_komma:
            j = te                                   # Anrede/Titel vor dem Namen gehört nicht dazu
        elif woerter and _wort_ist_titel(tok):
            woerter.append((ts, te, "titel"))
            j = te
        elif k in PARTIKEL and (tok[0].islower() or (tok.isupper() and len(tok) <= 3 and woerter)):
            woerter.append((ts, te, "partikel"))
            j = te
        elif len(tok) == 2 and tok[1] == "." and tok[0].isupper():
            woerter.append((ts, te, "initiale"))
            j = te
        elif _PRAEFIX_NAME_RE.match(tok) and wort_namensartig(_PRAEFIX_NAME_RE.match(tok).group(1)):
            woerter.append((ts, te, "name"))         # "al-Hassan", "d'Alessandro"
            j = te
        elif tok[0].isupper():
            wort = tok[:-1] if tok.endswith(".") else tok
            if wort.casefold() in FUNKTIONSWOERTER or not wort_namensartig(wort):
                break
            if wort.casefold() in DATUMSWOERTER and not (vor_komma or echte):
                break
            woerter.append((ts, ts + len(wort), "name"))
            j = ts + len(wort)
            if len(wort) != len(tok):
                break                                # "Müller." am Satzende
        else:
            break
        if sum(1 for w in woerter if w[2] in ("name", "initiale")) >= max_woerter:
            break
        if komma_index is not None and sum(1 for w in woerter[komma_index:] if w[2] in ("name", "initiale")) >= 3:
            break
        # Trenner
        if j < grenze and text[j] == "," and komma and komma_index is None \
                and any(w[2] == "name" for w in woerter):
            if _vorname_nachname_davor(text, woerter):
                break                                # "Anna Weber, Dr. Jörg Ziegler": Aufzählung
            if j + 2 < grenze and text[j + 1] == " ":
                n = _NAME_TOKEN_RE.match(text, j + 2, grenze)
                if n and n.group(0)[0].isupper() and n.group(0).rstrip(".").casefold() not in FUNKTIONSWOERTER \
                        and (_wort_ist_titel(n.group(0)) or wort_namensartig(n.group(0).rstrip("."))):
                    komma_index = len(woerter)
                    j += 2
                    continue
            break
        if j + 1 < grenze and text[j] == " " and text[j + 1] not in " \t\n":
            j += 1
            continue
        break
    if komma_index is not None and not any(w[2] in ("name", "initiale") for w in woerter[komma_index:]):
        woerter = woerter[:komma_index]
        komma_index = None
    if komma_index is not None and _nachname_hinten(text, woerter[komma_index:]):
        woerter = woerter[:komma_index]              # "Biedermann, Liselotte Schmidt": zwei Personen
        komma_index = None
    if woerter and woerter[-1][2] == "adel" and any(w[2] == "name" for w in woerter):
        woerter[-1] = (woerter[-1][0], woerter[-1][1], "name")      # "Max Graf": Nachname
    while woerter and woerter[-1][2] in ("partikel", "titel", "adel"):
        woerter.pop()
    while woerter and woerter[0][2] == "titel":
        woerter.pop(0)
    # führende Partikel vor einem Vornamen sind eine Präposition ("Ehefrau von Thomas Weber")
    k = 0
    while k < len(woerter) and woerter[k][2] == "partikel":
        k += 1
    if 0 < k < len(woerter) and woerter[k][2] == "name" and sum(1 for w in woerter if w[2] == "name") >= 2 \
            and _wissen is not None and _wissen.ist_vorname(text[woerter[k][0]:woerter[k][1]]):
        woerter = woerter[k:]
    namen = [w for w in woerter if w[2] == "name"]
    if not namen:
        return None
    s, e = woerter[0][0], woerter[-1][1]
    spanne = text[s:e]
    if _wissen is not None:
        try:
            if _wissen.ist_allowlist(spanne):
                return None
        except Exception:
            pass
    if any(t.casefold().strip(".,") in _FIRMEN_TOKEN or _BETRIEB_ENDUNG_RE.search(t.strip(".,"))
           for t in spanne.split()):
        return None                                  # "Löwen-Apotheke", "Müller GmbH": Betrieb, keine Person
    bekannt = any(wort_bekannter_name(text[a:b]) for a, b, _ in namen)
    if len(woerter) == 1 and spanne.isupper() and len(spanne) <= 3 and not bekannt:
        return None                                  # "ERS", "PKV": Kürzel oder OCR-Rest, kein Name
    return NamensSpanne(s, e, len(namen), bekannt, komma_index is not None)


# -- Orte und Straßen -------------------------------------------------------
_ORT_RE = re.compile(
    r"(?:(?:Bad|St\.|Sankt|Neu|Alt|Groß|Klein|Hansestadt|Lutherstadt)[ ])?"
    r"[A-ZÄÖÜ][\wäöüß'’]+(?:-[A-ZÄÖÜ]?[\wäöüß'’]+)*"
    r"(?:[ ](?:am|an der|an dem|im|in der|ob der|bei|a\.[ ]?d\.|v\.[ ]?d\.|i\.[ ]?d\.|i\.|b\.|an)"
    r"[ ][A-ZÄÖÜ][\wäöüß'’.\-]+"
    r"(?:[ ][A-ZÄÖÜ][\wäöüß'’.\-]+)?)?"
    r"(?:[ ]?\([A-ZÄÖÜ][\wäöüß'’ .\-]+\))?"
    r"|[A-ZÄÖÜ]{2,}(?:[ \-][A-ZÄÖÜ]{2,}){0,2}")
_HAUSNUMMER_RE = re.compile(r"\d{1,4}(?:[ ]?[a-zA-Z](?![\wäöüß]))?"
                            r"(?:[ ]?[-/][ ]?\d{1,4}(?:[ ]?[a-zA-Z](?![\wäöüß]))?)?")
_STRASSE_FREI_RE = re.compile(
    r"(?:[A-ZÄÖÜ][\wäöüß'’.\-]*|(?:am|an|auf|im|in|zum|zur|unter|hinter|vor|bei|der|die|das|den|dem|des|von)"
    r"(?=[ ]))(?:[ ](?:[A-ZÄÖÜ][\wäöüß'’.\-]*|am|an|auf|im|in|zum|zur|der|die|das|den|dem|des|von|vom|"
    r"\d{1,2}\.))*[ ]?(" + _HAUSNUMMER_RE.pattern + r")(?![\w])", re.IGNORECASE)
_POSTFACH_RE = re.compile(r"(?i)Postfach[ ]?\d{1,3}(?:[ ]?\d{2,4}){0,3}(?!\d)")
_PLZ_RE = re.compile(r"(?<![\w\-/.,])(?:(?:D|DE|A|AT|CH|L|FL|B|NL|F|I|PL|CZ|DK)[-\s])?\d{4,5}(?![\w])")


def ort_spanne(text: str, pos: int, grenze: int):
    """Ortsname ab pos ("Frankfurt am Main", "Bad Homburg v. d. Höhe", "Altenkirchen (Westerwald)",
    "St. Ingbert", "NEU-ULM"); keine Allerweltswörter/Feldbezeichner. (start, ende) oder None."""
    i = pos
    while i < grenze and text[i] in " \t":
        i += 1
    m = _ORT_RE.match(text, i, grenze)
    if not m:
        return None
    s, e = m.start(), m.end()
    # Abkürzungsketten wie "v. d. Höhe" ausgleichen: Rest der Zeile mit "v. d." aufnehmen
    rest = re.match(r"[ ](?:v\.|a\.|i\.|b\.|o\.)[ ]?(?:d\.[ ]?)?[A-ZÄÖÜ][\wäöüß]+", text[e:grenze])
    if rest:
        e += rest.end()
    worte = text[s:e].split()
    erstes = worte[0].strip(".,")
    if len(worte) > 1 and erstes.casefold() in ("bad", "st", "sankt", "neu", "alt", "groß", "klein", "hansestadt",
                                                 "lutherstadt"):
        erstes = worte[1].strip(".,")
    if erstes.casefold() in NEUTRALE_KOEPFE or erstes.casefold() in FUNKTIONSWOERTER \
            or erstes.casefold() in DATUMSWOERTER:
        return None
    if _wissen is not None:
        try:
            titel = erstes.title() if erstes.isupper() else erstes
            if (_wissen.ist_allerweltswort(titel) and not _wissen.ist_nachname(titel)) \
                    or any(_wissen.index(f"etiketten_{art}").eintrag_fuer(titel) for art in ARTEN):
                return None
        except Exception:
            pass
    return s, e


def strasse_spanne(text: str, pos: int, grenze: int):
    """Straße mit Hausnummer am Anfang des Bereichs, auch ohne Straßenwort ("Alt-Moabit 63",
    "Platz der Republik 99 a", "ZUM STEINBRUCH 66") oder Postfach. (start, ende) oder None."""
    i = pos
    while i < grenze and text[i] in " \t":
        i += 1
    m = _POSTFACH_RE.match(text, i, grenze)
    if m:
        return m.start(), m.end()
    m = _STRASSE_FREI_RE.match(text, i, grenze)
    if not m:
        return None
    s, e = m.start(), m.end()
    teil = text[s:e]
    if not any(c.isalpha() for c in teil.split()[0]) or len(teil) > 60:
        return None
    worte = re.findall(r"[^\W\d_][\w'’\-]*", teil)
    if not worte or all(w.casefold() in PARTIKEL | {"am", "an", "auf", "im", "in", "zum", "zur", "unter", "hinter",
                                                  "vor", "bei"} for w in worte):
        return None
    return s, e


# Ortszusatz ohne Leerzeichen hinter dem Ortsnamen: "Weiden i.d.OPf.", "Lauf a.d.Pegnitz", "Freiburg i. Br."
ORTSZUSATZ_RE = re.compile(r"[ ](?:[a-zäöü]{1,3}\.[ ]?){1,3}[A-ZÄÖÜ][\wäöüß]*\.?"
                           r"|[ ]?\((?:[A-ZÄÖÜ][\wäöüß.]*[ ]?){1,3}\)")


def ort_verlaengern(text: str, ende: int, grenze: int) -> int:
    """Ende eines Ortsnamens um einen abgekürzten Zusatz verlängern ("Weiden" -> "Weiden i.d.OPf.")."""
    m = ORTSZUSATZ_RE.match(text, ende, grenze)
    return m.end() if m else ende


@functools.lru_cache(maxsize=16384)
def ist_etikett_wort(wort: str) -> bool:
    """Feldbezeichner (Personen, Kennungen, Geburt, Kontakt, Vertragsdaten) – kein Ortsname."""
    if not wort or not wort[0].isalpha():
        return True
    if _wissen is None:
        return False
    titel = wort.title() if wort.isupper() else wort
    try:
        return any(_wissen.index(f"etiketten_{art}").eintrag_fuer(titel)
                   for art in ("person", "kennung", "datum_geburt", "kontakt", "vertragsdaten"))
    except Exception:
        return False


@functools.lru_cache(maxsize=16384)
def ist_etikett_oder_allerwelt(wort: str) -> bool:
    """Feldbezeichner oder Allerweltswort ("Leben", "Unfall", "Vorstand"), das kein Nachname ist."""
    if ist_etikett_wort(wort):
        return True
    if _wissen is None:
        return False
    titel = wort.title() if wort.isupper() else wort
    try:
        return _wissen.ist_allerweltswort(titel) and not _wissen.ist_nachname(titel)
    except Exception:
        return False


ORTSZUSATZ_WOERTER = frozenset({"am", "an", "der", "dem", "im", "in", "ob", "bei", "a.", "d.", "v.", "i.", "b.",
                                "st.", "bad", "main", "oder", "saale", "havel", "lech", "neckar", "rhein", "donau",
                                "höhe"})
# Wörter, hinter denen der eigentliche Ortsname erst kommt ("Bad Homburg", "Schwäbisch Hall")
_ORT_VORWORT_RE = re.compile(r"(?i)(?:bad|st\.?|sankt|neu|alt|groß|gross|klein|hohen|königs|markt|stadt|"
                             r"hansestadt|lutherstadt|ostseebad|nordseebad|seebad|hann\.|[a-zäöü]+isch)$")
_ORT_VERBINDER_RE = re.compile(r"(?:am|an|der|dem|den|im|in|ob|bei|vor|auf|unter|über|zu|zum|"
                               r"(?:[a-zäöü]{1,2}\.){1,3})$")
_PLZ_ANFANG_RE = re.compile(r"(?:(?:D|DE|A|AT|CH|L|FL)[-\s])?\d{4,5}")


def plz_ort_kappen(text: str, s: int, e: int) -> int | None:
    """Ende eines PLZ-Ort-Treffers text[s:e] kappen, wo der Ort sicher aufhört: an einer Zellgrenze (Tab)
    oder einem Zeilenwechsel hinter dem ersten Ortswort, vor Wörtern mit Ziffern, Kürzeln ("BU", "PHV",
    "Kfz") und – direkt hinter einem vollständigen Ortsnamen – vor Feldbezeichnern und Allerweltswörtern
    ("63739 Aschaffenburg Leben", "32423 Minden Versicherungsnummer"). Ortszusätze ("am Main", "(Saale)",
    "i.d.OPf.") und Vorwörter ("Bad Homburg") bleiben. None: das erste "Ortswort" ist selbst ein
    Feldbezeichner ("17205 USt-IdNr") oder steht als Allerweltswort in der Folgezeile ("16963\\nVorstand")."""
    m = _PLZ_ANFANG_RE.match(text, s, e)
    if not m:
        return e
    worte = list(re.finditer(r"\S+", text[m.end():e]))
    if not worte:
        return None
    basis = m.end()
    erstes = worte[0].group(0)
    kern = erstes.strip("(),.")
    zwischen = text[basis:basis + worte[0].start()]
    if "\n" in zwischen and ist_etikett_oder_allerwelt(kern):
        return None                                   # "16963\nVorstand": Folgezeile ist kein Ort
    if ist_etikett_wort(kern) and kern.casefold() not in ORTSZUSATZ_WOERTER:
        return None                                   # "17205 USt-IdNr"
    versal = kern.isupper()
    ende = basis + worte[0].end()
    offen = bool(_ORT_VORWORT_RE.match(kern))         # das nächste Wort gehört sicher zum Ort
    for vorher, w in zip(worte, worte[1:]):
        zwischen = text[basis + vorher.end():basis + w.start()]
        if "\t" in zwischen or "\n" in zwischen:
            break
        tok = w.group(0)
        kern = tok.strip("(),.")
        if not kern or any(c.isdigit() for c in kern):
            break
        if _ORT_VERBINDER_RE.match(tok):              # "am", "an der", "i.d.", "v. d."
            offen = True
            continue
        if not offen and not tok.startswith("("):
            if len(kern) <= 3 and not (versal and kern.isupper()) or kern.isupper() and not versal:
                break                                 # "BU", "PHV", "Kfz" hinter dem Ort
            if ist_etikett_oder_allerwelt(kern) and kern.casefold() not in ORTSZUSATZ_WOERTER:
                break                                 # "Aschaffenburg Leben", "Minden Versicherungsnummer"
        offen = bool(_ORT_VORWORT_RE.match(kern))
        ende = basis + w.end()
    return ende


def plz_ort_spannen(text: str, start: int, ende: int) -> list:
    """[(s, e)] von PLZ + Ort im Bereich (Muster der Wissensbasis, Spannen im Text; abgekürzte Ortszusätze
    wie "i.d.OPf." gehören dazu; der Ort endet an Zellgrenzen und vor Wörtern, die kein Ortsteil sind)."""
    aus = []
    if _muster is None:
        return aus
    teil = text[start:ende]
    pos = 0
    for t in _muster.finde_plz_ort(teil):
        k = teil.find(t, pos)
        if k < 0:
            k = teil.find(t)
        if k < 0:
            continue
        pos = k + len(t)
        s = start + k
        e = plz_ort_kappen(text, s, s + len(t))
        if e is None:
            continue
        if e == s + len(t):
            e = ort_verlaengern(text, e, ende)
        aus.append((s, e))
    return aus


def muster_spannen(funktion, text: str, start: int, ende: int) -> list:
    """Fundtexte einer muster-Funktion im Bereich -> Spannen."""
    aus = []
    teil = text[start:ende]
    pos = 0
    try:
        gefunden = funktion(teil)
    except Exception:
        return aus
    for t in gefunden:
        t = t.strip()
        if not t:
            continue
        k = teil.find(t, pos)
        if k < 0:
            k = teil.find(t)
        if k < 0:
            continue
        aus.append((start + k, start + k + len(t)))
        pos = k + len(t)
    return aus


# ----------------------------------------------------------------------
# Werte nach Etikett-Art lesen
# ----------------------------------------------------------------------
class Wert(NamedTuple):
    start: int
    ende: int
    kategorie: str
    gruppe: str | None = None


_KFZ_RE = re.compile(r"[A-ZÄÖÜ]{1,3}[- ][A-Z]{1,2}[ -]?\d{1,4}[EH]?(?![\w])")
_BIC_RE = re.compile(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?(?![\w])")
_AUSWEIS_RE = re.compile(r"(?=[A-Z0-9]*\d)[A-Z0-9]{6,12}(?![\w])")


NR_VORSATZ_RE = re.compile(r"[ \t]*(?:Nr\.?|NR\.?|No\.?|Nº|Nummer|NUMMER)[ \t]*:?[ \t]*")


def _kennungs_wert(text: str, s: int, e: int, kategorie: str, streng: bool) -> list:
    # "Nr." vor dem Wert gehört zum Etikett ("Versicherungsschein-" / "Nr. KH 0815 4471 2")
    m = NR_VORSATZ_RE.match(text, s, e)
    if m and m.end() < e:
        s = m.end()
    # Kennungsarten mit eigener Form (wenige oder keine Ziffern): Kennzeichen, BIC, Ausweis
    for kat, regel in (("kfz", _KFZ_RE), ("bic", _BIC_RE), ("ausweis", _AUSWEIS_RE)):
        if kategorie == kat:
            m = regel.match(text, s, e)
            if m:
                return [Wert(m.start(), m.end(), kat)]
    if kategorie == "iban" and _muster is not None:
        for a, b in muster_spannen(_muster.finde_iban, text, s, e):
            if a - s <= 2:
                return [Wert(a, b, "iban")]
    sp = kennung_spanne(text, s, e, 2 if kategorie in ("mandat", "ausweis") else 3)
    if sp is None:
        return []
    a, b = sp
    if streng:
        wert = text[a:b]
        kompakt = wert.replace(" ", "")
        if kompakt.isdigit() and len(kompakt) < 5:
            return []
    kat = kategorie or "vertrag"
    if kat == "iban" and _muster is not None and not _muster.finde_iban(text[a:b]):
        kat = "vertrag"
    return [Wert(a, b, kat)]


def werte_lesen(text: str, s: int, e: int, et: Etikett, mit_trenner: bool, eintrag: str = "") -> list:
    """Wert(e) eines Etiketts im Bereich [s, e) – nur der personenbezogene Teil. mit_trenner: zwischen
    Etikett und Wert stand ":" / Tabulator / Lücke / Zeilenwechsel (sonst nur ein Leerzeichen –
    dann sind die Anforderungen an den Wert strenger)."""
    arten = et.arten
    aus: list = []
    i = s
    while i < e and text[i] in " \t":
        i += 1
    if i >= e:
        return aus
    if "kennung" in arten:
        aus = _kennungs_wert(text, i, e, et.kategorie, streng=not mit_trenner)
        if aus:
            return aus
    if "datum_geburt" in arten:
        v = _vergleichsform(et.eintrag)
        if re.search(r"(?:ort|\bin)$", v) and not re.search(r"dat|tag", v):
            sp = ort_spanne(text, i, e)
            if sp and (mit_trenner or True):
                return [Wert(sp[0], sp[1], "plzort")]
        elif not re.search(r"alter|jahrgang|jahr\b", v):
            for a, b, d in datums_spannen(text, i, min(e, i + 40)):
                if a - i > 12:
                    break
                if geburtsdatum_plausibel(d):
                    aus.append(Wert(a, b, "geburt"))
                break
            if aus:
                return aus
    if "kontakt" in arten:
        kat = et.kategorie
        if kat == "email" or kat is None:
            for a, b in muster_spannen(_muster.finde_email, text, i, e) if _muster else []:
                if a - i <= 3:
                    return [Wert(a, b, "email")]
        if kat == "telefon" or kat is None:
            for a, b in muster_spannen(_muster.finde_telefon, text, i, e) if _muster else []:
                if a - i <= 3:
                    return [Wert(a, b, "telefon")]
            sp = _telefon_frei(text, i, e)
            if sp and kat == "telefon":
                return [Wert(sp[0], sp[1], "telefon")]
    if "adresse" in arten:
        aus = _adress_werte(text, i, e, et, mit_trenner)
        if aus:
            return aus
    if "person" in arten:
        aus = _namens_werte(text, i, e, et, mit_trenner)
        if aus:
            return aus
    return []


_TELEFON_FREI_RE = re.compile(r"(?:\+\d{1,3}[ ]?(?:\(0\)[ ]?)?|\(0\d{1,5}\)[ ]?|0)\d[\d /\-–]{4,}\d")


def _telefon_frei(text: str, i: int, e: int):
    m = _TELEFON_FREI_RE.match(text, i, e)
    if not m:
        return None
    ziffern = sum(c.isdigit() for c in m.group(0))
    if 6 <= ziffern <= 16:
        return m.start(), m.end()
    return None


_ORT_ETIKETT_RE = re.compile(r"(?:^|\b)(?:ort|wohnort|stadt|city|gemeinde|aufenthaltsort|geburtsort|"
                             r"risikoort|versicherungsort|schadenort|schadensort|unfallort|ereignisort|ortsteil|"
                             r"stadtteil|wohnhaft(?: in)?|wohnt in|wohnsitz|hauptwohnsitz|nebenwohnsitz)$")
_PLZ_ETIKETT_RE = re.compile(r"^(?:plz|postleitzahl|postcode|zip code)$")
_STRASSE_ETIKETT_RE = re.compile(r"str|stra|hausn|haus nr|hnr|street|^nr$")
_ANSCHRIFT_ETIKETT_RE = re.compile(r"anschrift|adresse|address|wohnung|objekt|risiko|belegenheit|lage des|"
                                   r"c o|z hd|zu handen|name und anschrift|wohnsitz")
_NICHT_ADRESSE_RE = re.compile(r"land|staat|bundesland|kreis|bezirk|kanton|nationalitat|staatsangehorigkeit|"
                               r"herkunftsland|country|etage|stockwerk|geschoss|zusatz|app|appartement|"
                               r"vorderhaus|hinterhaus|seitenflugel|dienstort|arbeitsort|arbeitsstatte|"
                               r"beschaftigungsort|tatort|unfallstelle|standort|garagenstandort")


def _adress_werte(text: str, i: int, e: int, et: Etikett, mit_trenner: bool) -> list:
    v = _vergleichsform(et.eintrag)
    if _NICHT_ADRESSE_RE.search(v) and not _ANSCHRIFT_ETIKETT_RE.search(v):
        return []
    aus = []
    # PLZ + Ort im Bereich
    for a, b in plz_ort_spannen(text, i, e):
        aus.append(Wert(a, b, "plzort"))
    # Straße (am Anfang oder hinter einem Komma vor der PLZ)
    sp = strasse_spanne(text, i, e)
    if sp and (mit_trenner or _muster is not None and _muster.finde_strasse(text[sp[0]:sp[1]])):
        if not any(a <= sp[0] < b for a, b, _, _ in aus):
            aus.append(Wert(sp[0], sp[1], "strasse"))
    if aus:
        return aus
    if not mit_trenner:
        return []
    if _PLZ_ETIKETT_RE.search(v):
        m = re.match(r"(?:(?:D|DE|A|CH)[-\s])?\d{4,5}(?![\w])", text[i:e])
        if m:
            return [Wert(i, i + m.end(), "plzort")]
        return []
    if _ORT_ETIKETT_RE.search(v):
        m = re.match(r"(?:(?:D|DE|A|CH)[-\s])?\d{4,5}[ ]+", text[i:e])
        k = i + (m.end() if m else 0)
        sp = ort_spanne(text, k, e)
        if sp:
            return [Wert(i if m else sp[0], sp[1], "plzort")]
        return []
    if _STRASSE_ETIKETT_RE.search(v):
        if re.fullmatch(r"\d{1,4}[ ]?[a-zA-Z]?", text[i:e].strip()):
            k = i + len(text[i:e]) - len(text[i:e].lstrip())
            return [Wert(k, k + len(text[i:e].strip()), "strasse")]
        m = re.match(r"[A-ZÄÖÜ][\wäöüß'’.\-]*(?:[ ][A-Za-zÄÖÜäöüß][\wäöüß'’.\-]*){0,4}", text[i:e])
        if m and text[i:i + m.end()].casefold() not in NEUTRALE_KOEPFE:
            ende = i + m.end()
            n = re.match(r"[ ]?" + _HAUSNUMMER_RE.pattern, text[ende:e])
            if n:
                ende += n.end()
            return [Wert(i, ende, "strasse")]
    return []


_ORT_DATUM_VORN_RE = re.compile(r"[ \t]*[A-ZÄÖÜ][^,\n\t]{1,40},[ \t]*(?:den[ \t]+)?"
                                r"\d{1,2}\.[ ]?(?:\d{1,2}\.|[A-ZÄÖÜa-zäöü]{3,9}\.?)"
                                r"[ ]?(?:19|20)?\d{2}[ \t]*,?[ \t]*")
_ORG_ROLLEN_RE = re.compile(r"(?i)^(?:arbeitgeber|auftraggeber|gläubiger|glaubiger|firma|name ?/ ?firma|"
                            r"firma ?/ ?name|absender|empfänger|zahlungsempfänger|aussteller|verwalter|"
                            r"hausverwalter|vermieter)")


def _namens_werte(text: str, i: int, e: int, et: Etikett, mit_trenner: bool) -> list:
    """Namen hinter einem Personen-Etikett; Gremien-Etiketten (Vorstand …) lesen eine Liste."""
    liste = bool(_GREMIUM_RE.search(et.eintrag)) or et.eintrag.casefold() in ("kinder", "erben", "zeugen",
                                                                            "mitversicherte personen")
    org = bool(_ORG_ROLLEN_RE.match(et.eintrag))
    aus = []
    pos = i
    # "Unterschrift: Nürnberg, 14.06.2025, Giovanni Esposito": Ort und Datum vor dem Namen überspringen
    m = _ORT_DATUM_VORN_RE.match(text, pos, e)
    if m:
        pos = m.end()
    while pos < e:
        sp = namen_spanne(text, pos, e, komma=not (liste or org))
        if sp is None:
            if not liste:
                break
            # Liste: Rolle in Klammern, Kommas, "und", Semikolon überspringen
            m = re.match(r"[ \t]*(?:\([^)\n]{0,40}\)|,|;|und\b|sowie\b|&|/)[ \t]*", text[pos:e])
            if not m or m.end() == 0:
                break
            pos += m.end()
            continue
        if (not mit_trenner or org) and not sp.bekannt and not sp.komma:
            break
        if liste and sp.woerter == 1 and not sp.bekannt:
            pos = sp.ende                            # einzelnes unbekanntes Wort in einer Liste: OCR-Rest?
            continue
        if sp.woerter == 1 and not sp.bekannt and not mit_trenner:
            break
        gruppe = text[sp.start:sp.ende] if sp.woerter >= 2 else None
        aus.append(Wert(sp.start, sp.ende, "namen", gruppe))
        if not liste:
            break
        pos = sp.ende
    return aus


# ----------------------------------------------------------------------
# Etikett -> Wertbereich
# ----------------------------------------------------------------------
_TRENNER_RE = re.compile(r"[ \t]*(?:\([^()\n]{1,25}\)[ \t]*)?(?:[:=][ \t]*|\.{2,}[ \t]*|…+[ \t]*|_{3,}[ \t]*|"
                         r"[ \t]+[-–][ \t]+|\t+[ \t]*|[ \t]{2,})?")


def wert_bereich_rechts(seite, lg: Lage, et: Etikett, alle: list, idx: int):
    """(start, grenze, mit_trenner) des Werts rechts vom Etikett in derselben Zeile – bis zum nächsten
    Etikett bzw. Zellende; None, wenn rechts nichts (Brauchbares) steht."""
    text = seite.text
    zeile = seite.zeile_von(et.start)
    if zeile is None:
        return None
    zeilen_ende = zeile.ende
    m = _TRENNER_RE.match(text, et.ende, zeilen_ende)
    trenner = m.group(0) if m else ""
    s = et.ende + len(trenner)
    if s >= zeilen_ende:
        return None
    # Etikett muss mit Wortgrenze enden ("Name" nicht in "Namensänderung")
    if et.ende < len(text) and text[et.ende].isalnum():
        return None
    mit_trenner = bool(trenner.strip(" ")) or "\t" in trenner or len(trenner) >= 2
    zelle = lg.zelle_bei(s)
    if zelle is None:
        return None
    if et.arten <= {"adresse", "neutral", "laufend"} and not mit_trenner and not _etikett_am_zellanfang(seite, lg, et):
        return None                                  # "Breite Straße 70": Straßenwort, kein Etikett
    eigene = lg.zelle_bei(et.start)
    if eigene is not None and zelle is not eigene:
        # Wert in der nächsten Zelle: nicht zu weit entfernt
        if zelle.x0 - eigene.x1 > max(260.0, 25 * lg.hoehe):
            return None
        mit_trenner = True
    grenze = zelle.ende
    # nächstes Etikett in derselben Zeile begrenzt den Wert
    for k in range(idx + 1, len(alle)):
        n = alle[k]
        if n.start >= grenze:
            break
        if n.start > s and (n.arten & (PII_ARTEN | {"vertragsdaten"})):
            grenze = n.start
            break
    if grenze <= s:
        return None
    return s, grenze, mit_trenner


def _etikett_am_ende(seite, lg: Lage, et: Etikett) -> bool:
    """Steht nach dem Etikett in seiner Zelle nichts mehr (außer Trennzeichen)?"""
    zelle = lg.zelle_bei(et.start)
    if zelle is None:
        return False
    rest = seite.text[et.ende:zelle.ende]
    return not rest.strip(" \t:.…_-–")


def _mit_doppelpunkt(seite, et: Etikett) -> bool:
    """Folgt dem Etikett ein Doppelpunkt mit Platz für den Wert in derselben Zeile (Formularzeile
    "Name: ____")? Dann steht der Wert rechts, die Zeile darunter ist das nächste Feld. Endet die Zeile mit
    dem Doppelpunkt ("Vorsitz Aufsichtsrat:" über dem Namen), darf der Wert darunter stehen."""
    m = re.match(r"[ \t]*(?:\([^()\n]{1,25}\)[ \t]*)?:", seite.text[et.ende:et.ende + 30])
    if m is None:
        return False
    zeile = seite.zeile_von(et.start)
    rest = seite.text[et.ende + m.end():zeile.ende] if zeile is not None else ""
    return bool(rest.strip(" \t_.…")) or "_" in rest or "…" in rest or ".." in rest


_WENDUNG_DAVOR_RE = re.compile(r"(?<![\w])(?:zum|zur|vom|beim|des|eines|für|fur|gegen|über|ueber|ohne)[ \t]+$")


def _in_wendung(text: str, lg: Lage, et: Etikett) -> bool:
    """Steht ein Personen-Etikett mitten in einer Wendung ("Verhältnis zum VN", "Angaben des Fahrers")?"""
    zelle = lg.zelle_bei(et.start)
    vorn = text[zelle.start if zelle else max(0, et.start - 30):et.start]
    return bool(_WENDUNG_DAVOR_RE.search(vorn))


def _etikett_am_zellanfang(seite, lg: Lage, et: Etikett) -> bool:
    zelle = lg.zelle_bei(et.start)
    if zelle is None:
        return False
    vorn = seite.text[zelle.start:et.start]
    return not vorn.strip(" \t0123456789.)(-–•*/")


def werte_darunter(seite, lg: Lage, et: Etikett, alle_starts: set) -> list:
    """Wert in der Zeile darunter, gleiche Spalte (Etikett über dem Wert: Informationsblock,
    Formular mit Feldnamen über dem Eingabefeld)."""
    zelle = lg.zelle_bei(et.start)
    if zelle is None:
        return []
    box = lg.box(et.start, et.ende)
    if box is None:
        return []
    x0, x1 = box[0], max(box[2], box[0] + 6 * lg.hoehe)
    h = max(zelle.hoehe, 4.0)
    text = seite.text
    for zid in lg.zeilen_darunter(zelle.zeile, 1.9 * h):
        for z in lg.zellen_je_zeile.get(zid, ()):
            if ueberlappung(z.x0, z.x1, x0 - 0.5 * h, x1) <= 0:
                continue
            if abs(z.x0 - zelle.x0) > max(4 * h, 40.0) and z.x0 < zelle.x0 - h:
                continue
            if any(z.start <= s < z.ende and s <= z.start + 2 for s in alle_starts):
                return []                           # darunter steht das nächste Etikett
            if re.search(r"(?:/-?in|\(in\)|:)\s*$", text[z.start:z.ende]):
                return []                           # Feldbezeichner ("Raucher/in", "Beruf:")
            werte = werte_lesen(text, z.start, z.ende, et, True)
            return werte
        return []
    return []


def kennung_folgezeile(seite, lg: Lage, et: Etikett) -> list:
    """Kennungs-Etikett am Zeilenende eines Satzes, Wert am Anfang der Folgezeile (umbrochener Text);
    höchstens ein kurzes OCR-Bruchstück davor wird übersprungen."""
    zeile = seite.zeile_von(et.start)
    if zeile is None:
        return []
    text = seite.text
    if text[et.ende:zeile.ende].strip(" \t:.-–"):
        return []
    nach = zeile.ende + 1
    folge = seite.zeile_von(nach) if nach < len(text) else None
    if folge is None or folge.start != nach:
        return []
    m = re.match(r"[ \t]*(?:\S{1,2}[ \t]+)?", text[folge.start:folge.ende])
    for anfang in (folge.start, folge.start + (m.end() if m else 0)):
        sp = kennung_spanne(text, anfang, folge.ende, 3)
        if sp and sp[0] - anfang <= 1:
            return [Wert(sp[0], sp[1], et.kategorie or "vertrag")]
    return []


# ----------------------------------------------------------------------
# Detektor struktur.etikett_wert
# ----------------------------------------------------------------------
def _global(dok, nr: int, werte: list, quelle: str, sicherheit: float) -> list:
    aus = []
    for w in werte:
        aus.append(Treffer(dok.global_(nr, w.start), dok.global_(nr, w.ende), w.kategorie, quelle, sicherheit,
                           w.gruppe))
    return aus


def gremium_folgezeilen(seite, lg: Lage, et: Etikett, letzte_ende: int, alle_starts: set) -> list:
    """Namensliste eines Gremien-Etiketts in den Folgezeilen derselben Spalte (Fußzeilen-Spalten)."""
    text = seite.text
    zelle = lg.zelle_bei(et.start)
    if zelle is None:
        return []
    aus = []
    zid = zelle.zeile
    h = max(zelle.hoehe, 4.0)
    for _ in range(3):
        naechste = None
        for z2 in lg.zeilen_darunter(zid, 1.7 * h):
            for c in lg.zellen_je_zeile.get(z2, ()):
                if abs(c.x0 - zelle.x0) <= 2.5 * h:
                    naechste = c
                    break
            if naechste is not None:
                break
        if naechste is None:
            break
        if any(naechste.start <= s < naechste.ende for s in alle_starts) or ":" in text[naechste.start:naechste.ende]:
            break                                    # nächstes Etikett
        werte = _namens_werte(text, naechste.start, naechste.ende,
                              et._replace(eintrag="Vorstand"), True)
        if not werte:
            break
        aus.extend(werte)
        zid = naechste.zeile
    return aus


@detektor("struktur.etikett_wert", ALLE_KATEGORIEN)
def etikett_wert(dok, kontext):
    """Etikett der Wissensbasis + Wert (gleiche Zeile, Zeile darunter, Folgezeile)."""
    treffer = []
    for nr, seite in enumerate(dok.seiten):
        if not seite.text.strip():
            continue
        lg = lage(seite)
        alle = etiketten(seite)
        if not alle:
            continue
        starts = {et.start for et in alle if et.arten & (PII_ARTEN | {"vertragsdaten"})}
        for idx, et in enumerate(alle):
            if not et.arten & PII_ARTEN:
                continue
            if et.arten <= {"person"} and _in_wendung(seite.text, lg, et):
                continue                              # "Verhältnis zum VN: Mitbewohner" ist kein Personenfeld
            werte = []
            bereich = wert_bereich_rechts(seite, lg, et, alle, idx)
            if bereich is not None:
                s, g, mit_trenner = bereich
                werte = werte_lesen(seite.text, s, g, et, mit_trenner)
                if werte and _GREMIUM_RE.search(et.eintrag) and "person" in et.arten:
                    werte += gremium_folgezeilen(seite, lg, et, werte[-1].ende, starts)
            if not werte and _etikett_am_ende(seite, lg, et) and _etikett_am_zellanfang(seite, lg, et) \
                    and not _mit_doppelpunkt(seite, et):
                werte = werte_darunter(seite, lg, et, starts)
                quelle_sicherheit = SICHERHEIT_UNTER
            else:
                quelle_sicherheit = SICHERHEIT_ETIKETT
            if not werte and "kennung" in et.arten:
                werte = kennung_folgezeile(seite, lg, et)
            werte = [w for w in werte if w.kategorie in kontext.aktive or not kontext.aktive]
            treffer.extend(_global(dok, nr, werte, "struktur.etikett_wert", quelle_sicherheit))
    return treffer
