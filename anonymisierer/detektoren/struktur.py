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
Geschäftsführer) lesen eine ganze Namensliste, auch über die Folgezeilen derselben Spalte. Quer gestellte
Tabellen (eine Spalte je Beteiligtem: "Führerschein-Nr. ⇥⇥ H996KNYGE24 ⇥⇥ P9873B6ND15") liefern jede weitere
Wertzelle derselben Art (folgezellen_werte). Kopfzeilen aus Feldnamen/Kürzeln ("NAME ⇥⇥ VORN. ⇥⇥ GEB.-DAT.") mit
einer Wertzeile darunter haben keinen Wert in derselben Zeile (kopfzeile); eine ausgefüllte Formularzeile in
Versalien ("NAME: KOCH ⇥⇥ VORNAME: UWE ⇥⇥ ORT: BONN") ist nie Kopfzeile. Auf OCR-Zeilen gilt ohne lesbare
Wertform der Rohwert hinter dem Feldnamen (Handschrift, Kästchen, Schreibmaschine), wenn er die grobe Gestalt
seiner Kategorie hat (ocr_rohwert, Quelle "struktur.etikett_wert.rohwert").
"""

from __future__ import annotations

import datetime
import functools
import math
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
from .. import kennungsformen, personenkontext

try:
    from ..namen import personen_teilen as _personen_teilen
except Exception:  # pragma: no cover
    def _personen_teilen(text, start, ende):
        return [(start, ende)]


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
        # Leicht schräger Scan, den die OCR nicht gerade gerückt gelesen hat (unter ocr.SCHRAEG_KORREKTUR_AB, Befund
        # 85): jedes OCR-Wort trägt das waagerechte Band seiner ganzen Zeile, die Neigung steckt nur im Versatz der
        # Zeilen gegeneinander (rechte Spalte eines Kastenformulars höher als die linke). Dann wird jede OCR-Zeile
        # als Ganzes um die geschätzte Neigung des Seitenbilds zurückgedreht – um die Mitte der Zeile, damit ihre
        # Wörter in einer Reihe bleiben.
        band = 0.0
        if not s and not self.richtung:
            band = math.tan(math.radians(float(getattr(seite, "ocr_schraeg", 0.0) or 0.0)))
            if abs(band) > 0.1:
                band = 0.0
        mitte_x: dict = {}
        if band:
            for e in roh:
                if e[8]:
                    a, b = mitte_x.get(e[6], (e[2], e[4]))
                    mitte_x[e[6]] = (min(a, e[2]), max(b, e[4]))
        woerter = []
        for start, ende, x0, y0, x1, y1, zid, hoehe, ocr in roh:
            if s:
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                dx, dy = s * cy, -s * cx
                x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
            elif band and ocr:
                a, b = mitte_x[zid]
                dx, dy = band * (y0 + y1) / 2, -band * (a + b) / 2
                x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
            woerter.append(Wort(start, ende, x0, y0, x1, y1, zid, hoehe, ocr))
        if band:
            self.schraege = band
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
    unscharf: bool = False  # nur als von der OCR verlesenes Etikett erkannt (detektoren/etiketten_unscharf.py)


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
    (re.compile(r"kreditkarte|karten ?n|kartennr|karten ?pruf|\bcv[cv]\d?\b|\bcav\d?\b"), "kreditkarte"),
]
# Kennungs-Etiketten, deren Wert NICHT zur Person gehört (Kennung des Gläubigers/Versicherers)
_KENNUNG_FREMD_RE = re.compile(r"glaubiger|bankleitzahl|\bblz\b|\bust\b|umsatzsteuer|wirtschafts ?ident|\bw idnr\b|"
                               r"bankverbindung|kontoverbindung")
_KONTAKT_TELEFON_RE = re.compile(r"tel|fax|mobil|handy|ruf|durchwahl|\bdw\b|festnetz|phone|cell|whatsapp|"
                                 r"erreichbar|threema|telegram|signal")
_KONTAKT_EMAIL_RE = re.compile(r"mail|e post|de mail|\bbea\b")

# zusammengesetzte Nummern-Etiketten, die in keiner Liste stehen ("Bestandsnummer", "Mitglieds-ID")
_NUMMERN_WORT_RE = re.compile(
    r"(?<![\w.\-])([A-ZÄÖÜa-zäöü][\wäöüß]*?(?:[-._][\wäöüßÄÖÜ]+)*?(?:[Nn]ummer|NUMMER|[-_]?[Nn]r\.?|[-_]?NR\.?|"
    r"[-_]ID|[-_]Id|[Kk]ennung|KENNUNG|[Kk]ennziffer))(?![\w])")
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
# Spaltenkürzel aus Exporten (Excel, Bestandsführung): Versalien bis vier Buchstaben, Kürzel mit Punkt oder Wörter mit
# Unterstrich ("VU", "ZW.", "HF", "GES.", "VORN.", "BTR_BRUTTO", "TEL_PRIVAT") – nie ein Personenname im Kopf
ABKUERZUNG_RE = re.compile(r"[A-ZÄÖÜ]{1,4}\.?|[A-ZÄÖÜa-zäöü]{1,6}\.(?:[ ]?[A-ZÄÖÜa-zäöü]{1,5}\.)*|"
                           r"[A-ZÄÖÜ0-9]+(?:_[A-ZÄÖÜ0-9]+)+(?:[ ][A-ZÄÖÜ]{1,4}\.?)?")
_GREMIUM_RE = re.compile(
    r"(?i)^(?:vorst(?:a|ä)nd(?:e|s)?|vorstandsvorsitzende[r]?|aufsichtsrat(?:s|es)?|aufsichtsratsvorsitzende[r]?|"
    r"vorsitz(?:ende[r]?)?(?: des)?(?: aufsichtsrat(?:s|es)?| vorstand(?:s|es)?)?|geschäftsführer(?:in|innen)?|"
    r"geschäftsführung|geschäftsleitung|gesellschafter(?:in)?|beirat|verwaltungsrat|vertreten durch|"
    r"vertretungsberechtigt(?:e[r]?)?|inhaber(?:in)?|partner|prokurist(?:in)?|prokura)$")


def _vergleichsform(text: str) -> str:
    # "_" trennt wie "-" und "." (Spaltennamen aus Datenbank-Exporten: "STEUER_NR", "VN_GEBDAT")
    if _wissen is not None:
        try:
            return " ".join(_wissen.normalisieren(re.sub(r"[-./()_]+", " ", text)).split())
        except Exception:
            pass
    return " ".join(re.sub(r"[-./()_]+", " ", text).casefold().split())


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
    # Zellen getrennt durchsuchen: der Spaltentrenner "\t\t" gilt der Wissensbasis als Leerraum, ein Eintrag
    # "PLZ Ort" würde sonst über zwei Kopfzellen "PLZ ⇥⇥ ORT" greifen und (verworfen) beide Etiketten verdecken
    such = text.replace("\t", "\n")
    for art in ARTEN:
        try:
            vorkommen = _wissen.finde(such, f"etiketten_{art}")
        except Exception:
            continue
        for v in vorkommen:
            aus.append((v.start, v.ende, art, v.eintrag))
    for m in _NUMMERN_WORT_RE.finditer(text):
        wort = m.group(1)
        if len(wort) < 5 or _NUMMERN_FREMD.match(wort):
            continue
        aus.append((m.start(1), m.end(1), "kennung", wort))
    # Feldcode C.1.3 einer Zulassungsbescheinigung Teil I: das Anschrift-Etikett des Halters (Befund 32 der
    # Domänen-Durchsicht; nur auf einer erkennbaren Zulassungsbescheinigung, sonst Gliederungsnummer)
    for s, e in personenkontext.zb1_anschrift_etiketten(text):
        aus.append((s, e, "adresse", "Anschrift"))
    return aus


# Straßenwort als Teil eines Straßennamens statt als Feldname: Wort + ein Leerzeichen davor, Hausnummer danach
_STRASSENNAME_TEIL_RE = re.compile(r"(?i)stra(?:ß|ss)e|str\.?")
_VOR_STRASSENWORT_RE = re.compile(r"[A-Za-zÄÖÜäöüß][\wäöüß'’.\-]*[ ]$")
_HAUSNUMMER_DANACH_RE = re.compile(r"[ ]?\d{1,4}(?![\d.:])")


def _etiketten_ocr_unscharf(seite) -> list:
    """Von der OCR verlesene Etiketten ("Name, Vomame:", "Kundenntimmer 76183905") – nur in OCR-Zeilen
    (detektoren/etiketten_unscharf.py)."""
    try:
        from .etiketten_unscharf import unscharfe_etiketten
        from .ocr_lesart import OCR_QUELLEN, zeile_ist_ocr
    except Exception:  # pragma: no cover - Modul fehlt
        return []
    if not any(z.quelle in OCR_QUELLEN for z in seite.zeichen):
        return []
    aus = []
    for z in seite.zeilen:
        if z.ende > z.start and zeile_ist_ocr(seite, z):
            aus.extend(unscharfe_etiketten(seite.text, z.start, z.ende))
    return aus


def etiketten(seite) -> list:
    """Etiketten einer Seite (nach Lage geordnet, nicht überlappend, nie über eine Zellgrenze)."""
    zw = getattr(seite, "_struktur_etiketten", None)
    if zw is not None and zw[0] is seite.text:
        return zw[1]
    text = seite.text
    lg = lage(seite)
    unscharf_roh = _etiketten_ocr_unscharf(seite)
    unscharf = {(s, e) for s, e, *_ in unscharf_roh}
    roh = _etiketten_roh(text)
    unscharf -= {(s, e) for s, e, *_ in roh}           # exakt erkannt geht vor
    roh += unscharf_roh
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
        if art == "adresse" and _STRASSENNAME_TEIL_RE.fullmatch(text[s:e]) and \
                _VOR_STRASSENWORT_RE.search(text, max(0, s - 40), s) and _HAUSNUMMER_DANACH_RE.match(text, e):
            continue                                  # "HOHE STRASSE 129", "Neue Str. 5": Teil des Straßennamens
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
        aus.append(Etikett(s, e, frozenset(arten), kategorie, eintrag, (s, e) in unscharf))
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
    if not arten and _muster is not None and (_muster.eigene_wertform(sauber) or _muster.pruefnummer_etikett(sauber)):
        arten, eintrag = {"kennung"}, sauber          # "Versicherungsbestätigung" (zweizeiliger Kopf), "CVC", "Prüfnr."
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


def _versalien(text: str) -> bool:
    """Überwiegend Großbuchstaben (oder gar keine Buchstaben)?"""
    buchstaben = [c for c in text if c.isalpha()]
    return not buchstaben or sum(c.isupper() for c in buchstaben) > 0.7 * len(buchstaben)


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
# Pässe und Ausweise anderer Staaten: Monatskürzel englisch/französisch in Versalien, Jahr zweistellig
# ("11 JAN 94", "04 JUL/JUIL 50" – ICAO 9303 Teil 3, Sichtzone)
_MONATE_PASS = {"jan": 1, "janv": 1, "feb": 2, "fev": 2, "fév": 2, "fevr": 2, "févr": 2, "mar": 3, "mars": 3,
                "apr": 4, "avr": 4, "may": 5, "mai": 5, "jun": 6, "juin": 6, "jul": 7, "juil": 7, "aug": 8,
                "aou": 8, "aoû": 8, "aout": 8, "août": 8, "sep": 9, "sept": 9, "oct": 10, "okt": 10, "nov": 11,
                "dec": 12, "déc": 12, "dez": 12}
_MONAT_ALT = "|".join(sorted(_MONATE, key=len, reverse=True))
_MONAT_PASS_ALT = "|".join(sorted({m.upper() for m in _MONATE_PASS}, key=len, reverse=True))
_DATUM_RE = re.compile(
    r"(?<![\d.])(?:(\d{1,2})\.[ ]?(\d{1,2})\.[ ]?((?:19|20)\d{2}|\d{2})"
    r"|(\d{1,2})\.?[ ]?(" + _MONAT_ALT + r")\.?[ ]?((?:19|20)\d{2})"
    r"|((?:19|20)\d{2})-(\d{2})-(\d{2})"
    r"|(\d{1,2})/(\d{1,2})/((?:19|20)\d{2})"
    r"|(\d{1,2})[ ]+(?-i:(" + _MONAT_PASS_ALT + r"))(?:[ ]?/[ ]?(?-i:" + _MONAT_PASS_ALT + r"))?\.?[ ]+"
    r"((?:19|20)\d{2}|\d{2}))(?![\d])", re.IGNORECASE)


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
        elif g[9]:
            t, mo, j = int(g[9]), int(g[10]), int(g[11])
        else:
            t, mo, j = int(g[12]), _MONATE_PASS[g[13].casefold()], int(g[14])
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
# Artikel unter den Partikeln: Teil eines Namens nur hinter einem anderen Partikel ("van den Berg", "von der Leyen")
_ARTIKEL_PARTIKEL = frozenset({"der", "den", "dem", "des", "die", "das"})
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
                                r"handel|bäckerei|metzgerei|gruppe|verwaltung|spedition|vermietung|stadtwerke|"
                                r"betriebe|logistik|transporte|leasing)$")
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
            if k in _ARTIKEL_PARTIKEL and not (woerter and woerter[-1][2] == "partikel"):
                break                                # "Lukas den Ball": ein Artikel nur hinter "van", "von", "de"
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
            if woerter and len(wort) <= 4 and wort.isalpha() and wort.isupper() and not wort_bekannter_name(wort) \
                    and not text[woerter[-1][0]:woerter[-1][1]].isupper():
                break                                # "Mooslechner, Anton PHV": ein Kürzel, kein weiterer Name
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
                        and not (_STRASSENWORT_RE.search(n.group(0).rstrip("."))
                                 and not wort_bekannter_name(n.group(0))) \
                        and not re.match(r"[ ]?\d{1,4}[a-zA-Z]?(?![\d.])", text[n.end():n.end() + 7]) \
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
# Wörter durch ein Leerzeichen getrennt; vor einem Straßenwort auch durch mehrere (Blocksatz/Ausrichtung in Courier:
# "Hohe   Straße 129") – sonst verbände die Lücke zwei Zellen ("Kreissparkasse Talheim   SWBPDEZ7")
_STRASSE_FREI_RE = re.compile(
    r"(?:[A-ZÄÖÜ][\wäöüß'’.\-]*|(?:am|an|auf|im|in|zum|zur|unter|hinter|vor|bei|der|die|das|den|dem|des|von)"
    r"(?=[ ]))(?:(?:[ ]|[ ]{2,4}(?=(?:stra(?:ß|ss)e|str\.|weg|platz|allee|gasse|ring|damm|ufer|chaussee|"
    r"promenade|markt|steig|pfad)(?![\wäöüß])))(?:[A-ZÄÖÜ][\wäöüß'’.\-]*|am|an|auf|im|in|zum|zur|der|die|das|den|"
    r"dem|des|von|vom|\d{1,2}\.))*[ ]?(" + _HAUSNUMMER_RE.pattern + r")(?![\w])", re.IGNORECASE)
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
    if "\n" in zwischen and (ist_etikett_oder_allerwelt(kern) or kern.casefold() in NEUTRALE_KOEPFE):
        return None                                   # "16963\nVorstand", "98765\nBeruf": Folgezeile ist kein Ort
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


def eigene_wertform(eintrag: str) -> str | None:
    """Art der eigenen Wertform eines Etiketts (muster.eigene_wertform: eVB-Nummer, Transferticket, Kartenprüfnummer)
    oder None. Deren Werte haben eine feste Form, oft mit weniger als drei Ziffern (kennung_spanne): "A1BCDEF",
    "123"."""
    if not eintrag or _muster is None:
        return None
    return _muster.eigene_wertform(eintrag)


def allgemein_hinter(eintrag: str) -> bool:
    """Gilt hinter einem Etikett mit eigener Wertform ZUSÄTZLICH der allgemeine Kennungsweg – ein Etikett mit
    Nummer-Wort ("Versicherungsbestätigung Nr. 123/24", "Transferticket-Nr.: TT-12345";
    kennungsformen.nummer_etikett)?"""
    return kennungsformen.nummer_etikett(eintrag)


def allgemeiner_wert_passt(wert: str) -> bool:
    """Allgemeiner Kennungsweg hinter einem Etikett mit eigener Wertform: die Form einer Kennung, kein Jahresbereich
    und kein kurzes Datum ("eVB-Nummer 2024/2025", "12/2025"; muster.kennungsform)."""
    return _muster is None or _muster.kennungsform(wert)


def eigener_wert(text: str, s: int, e: int, art: str, kategorie: str | None, versalien: bool = True,
                 darunter: bool = False, etikett: str = "") -> list:
    """Wert der eigenen Form `art` am Anfang von [s, e) (muster.eigener_wert; leer, wenn keiner passt). versalien:
    das Etikett steht in Großbuchstaben bzw. ist nicht bekannt (dann zählen eVB/Transferticket nur mit Ziffer).
    darunter: der Wert steht nicht in der Zeile des Etiketts (Zelle darunter, Spalte, Folgezeile) – dann zählen
    eVB/Transferticket nur mit Ziffer ("ERTEILT" unter "eVB-Nummer") und eine Kartenprüfnummer nur als ganze Zelle."""
    while s < e and text[s] in " \t:":
        s += 1
    sp = _muster.eigener_wert(art, text, s, e, versalien, darunter, etikett) if _muster is not None else None
    return [Wert(sp[0], sp[1], kategorie or "vertrag")] if sp else []


def _kennungs_wert(text: str, s: int, e: int, kategorie: str, streng: bool, eintrag: str = "",
                   etikett_text: str = "", darunter: bool = False) -> list:
    # "Nr." vor dem Wert gehört zum Etikett ("Versicherungsschein-" / "Nr. KH 0815 4471 2")
    m = NR_VORSATZ_RE.match(text, s, e)
    if m and m.end() < e:
        s = m.end()
    art = eigene_wertform(eintrag)
    if art is not None:
        # eVB, Transferticket, Kartenprüfnummer: ihre eigene Form – hinter einem Nummer-Etikett ZUSÄTZLICH der
        # allgemeine Kennungsweg ("Versicherungsbestätigung Nr. 123/24"; eine Nummer hinter einem Kartenprüfnummer-
        # Etikett, die keine Kartenprüfnummer ist, ist eine Kennung: "Kartenprüfnummer 4711-0815")
        eigen = eigener_wert(text, s, e, art, kategorie, _versalien(etikett_text or eintrag), darunter,
                             etikett_text or eintrag)
        if eigen or not allgemein_hinter(eintrag):
            return eigen
        if art == "cvc":
            kategorie = "vertrag"
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
    if sp is None or (art is not None and not allgemeiner_wert_passt(text[sp[0]:sp[1]])):
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
        aus = _kennungs_wert(text, i, e, et.kategorie, streng=not mit_trenner, eintrag=et.eintrag,
                             etikett_text=text[et.start:et.ende] if et.ende > et.start else "",
                             darunter=0 <= et.ende <= i and "\n" in text[et.ende:i])
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


def _hinter_ortsgattung(text: str, k: int, e: int):
    """Beginnt die Ortsangabe ab k mit Gattungswörtern ("Skigebiet Sudelfeld", "Turnhalle der Mittelschule Erding"),
    die Stelle des Eigennamens dahinter; nur Gattungswörter: None. Ein einzelnes Wort bleibt, wie es ist."""
    if _wissen is None:
        return k
    # die ganze Zelle zählt, auch hinter dem nächsten Etikett ("Kreuzung Bamberger Straße": "Straße" ist ein Etikett)
    zelle = re.match(r"[^\t\n]*", text[k:])
    woerter = list(re.finditer(r"[^\s,;()/]+", zelle.group(0)))
    if len(woerter) < 2 or k + woerter[1].start() >= e:
        return k
    n = _wissen.ortsname_hinter_gattung([w.group(0) for w in woerter])
    if n is None or k + woerter[n].start() >= e:
        return None
    return k + woerter[n].start()


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
        if not m:
            k = _hinter_ortsgattung(text, k, e)
            if k is None:
                return []                    # nur Gattungswörter ("Unfallort: Turnhalle der Grundschule")
        sp = ort_spanne(text, k, e)
        if sp:
            return [Wert(i if m else sp[0], sp[1], "plzort")]
        return []
    if _STRASSE_ETIKETT_RE.search(v):
        if re.fullmatch(r"\d{1,4}[ ]?[a-zA-Z]?", text[i:e].strip()):
            k = i + len(text[i:e]) - len(text[i:e].lstrip())
            return [Wert(k, k + len(text[i:e].strip()), "strasse")]
        m = re.match(r"[A-ZÄÖÜ][\wäöüß'’.\-]*(?:[ ][A-Za-zÄÖÜäöüß][\wäöüß'’.\-]*){0,4}", text[i:e])
        if m and text[i:i + m.end()].casefold() not in NEUTRALE_KOEPFE \
                and etikett_fuer_text(text[i:i + m.end()]) is None:
            # das nächste Feld-Etikett ist kein Straßenname ("Straße, Hausnummer ⇥⇥ PLZ" einer Etikettzeile)
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


# ein Doppelpunkt direkt hinter einem unbekannten "Namen": ein Feld-Etikett, kein Name ("Geburtsland: Polen")
_FELD_DAHINTER_RE = re.compile(r"[ \t]*:")
# Rechtsform einer juristischen Person direkt hinter dem "Namen" ("Gegner: Wohnbau GmbH", "Leasingnehmer: Muster
# Leasing GmbH"): eine Firma, keine Person. Einzelkaufleute (e.K.) und Gesellschaften bürgerlichen Rechts (GbR) tragen
# Namen natürlicher Personen und bleiben Namen.
_JURISTISCH_DAHINTER_RE = re.compile(
    r"[ \t]*(?:gGmbH|GmbH|mbH|AG|SE|KGaA|KG|OHG|UG|e\.[ \t]?V\.|eG|VVaG|Ltd\.?|Inc\.?|PLC|S\.[ \t]?A\.|B\.[ \t]?V\.|"
    r"N\.[ \t]?V\.|&[ \t]*Co\.?)(?![\wäöüß])")


def _namens_werte(text: str, i: int, e: int, et: Etikett, mit_trenner: bool) -> list:
    """Namen hinter einem Personen-Etikett; Gremien-Etiketten (Vorstand …) lesen eine Liste. In der Abstammung eines
    Tiers ("Abstammung: Vater: Sandro Hit") steht kein Mensch."""
    if personenkontext.tierangabe(text, i):
        return []
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
        if not sp.bekannt and _FELD_DAHINTER_RE.match(text, sp.ende, e):
            break                                    # "Geburtsname:" ⏎ "Geburtsland: Polen": das nächste Feld
        if _JURISTISCH_DAHINTER_RE.match(text, sp.ende, e):
            break                                    # "Gegner: Wohnbau GmbH": eine Firma
        if liste and sp.woerter == 1 and not sp.bekannt:
            pos = sp.ende                            # einzelnes unbekanntes Wort in einer Liste: OCR-Rest?
            continue
        if sp.woerter == 1 and not sp.bekannt and not mit_trenner:
            break
        # "Jörg Ziegler Ursula Frank" (Komma von der OCR verschluckt): je Person ein Wert
        teile = _personen_teilen(text, sp.start, sp.ende) if sp.woerter >= 3 and not sp.komma \
            else [(sp.start, sp.ende)]
        for a, b in teile:
            gruppe = text[a:b] if len(text[a:b].split()) >= 2 and (len(teile) > 1 or sp.woerter >= 2) else None
            aus.append(Wert(a, b, "namen", gruppe))
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
    if not mit_trenner and personenkontext.ZB1_FELDCODE_RE.fullmatch(text[et.start:et.ende]):
        mit_trenner = True                           # Feldcode ("C.1.3"): der Wert folgt direkt, wie hinter ":"
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


_FUELLWERT_RE = re.compile(r"(?i)^(?:wie\b.*|siehe\b.*|s\.\s*o\.?|entf[aä]llt|keine?|nein|ja|[-–—/_.x]+|n/?a|"
                           r"unbekannt|nicht\s+bekannt|wird\s+(?:separat|gesondert|noch|nachträglich)\b.*|"
                           r"(?:folgt|nachgereicht)\b.*)$")
# Beschriftungen unter Unterschriftslinien und Firmenzusätze: kein Eintrag einer Person
_BESCHRIFTUNG_RE = re.compile(r"(?i)unterschrift|^datum\b|^ort\b|stempel")
_HINWEIS_KLAMMER_RE = re.compile(r"[ \t]*\([^()\n]{0,30}\)?")
_PLZ_ORT_FELD_RE = re.compile(r"(?i)^(?:plz|postleitzahl|ort|wohnort|plz[ ,/]*(?:und[ ]+)?ort|postleitzahl und ort)"
                              r"\.?:?$")


def etikett_kategorie(et: Etikett, etikett_text: str, wert: str = "") -> str | None:
    """Kategorie eines Werts hinter einem Feldnamen (unabhängig von seiner Form)."""
    arten = et.arten
    if "person" in arten:
        return "namen"
    if "datum_geburt" in arten:
        v = _vergleichsform(et.eintrag)
        if re.search(r"(?:ort|\bin)$", v) and not re.search(r"dat|tag", v):
            return "plzort"
        return "geburt"
    if "kennung" in arten:
        return et.kategorie or "vertrag"
    if "kontakt" in arten:
        return et.kategorie or ("email" if "@" in wert else "telefon")
    if "adresse" in arten:
        if _NICHT_ADRESSE_RE.search(_vergleichsform(et.eintrag)):
            return None
        return "plzort" if _PLZ_ORT_FELD_RE.match(etikett_text.strip()) else "strasse"
    return None


# Rohwerte: Funktionswörter verraten Satzreste und Überschriften ("für Innere Medizin", "Ich kündige daher den")
_ROH_FUNKTIONSWORT = frozenset(
    "für und oder das die dem des zum zur im am an auf aus bei mit nach vom zu sie ich wir ihr er es mein meine "
    "meinen meiner ihre ihren ihrer ihrem ihres unser unsere unserer unserem unseres sein seine seiner seinem "
    "seines dessen deren ein eine einen einem einer eines daher bitte nicht diese dieser dieses wie ist sind wird "
    "werden wurde hat haben kein keine sowie siehe".split())
_ROH_NAMENSPARTIKEL = frozenset("von van de der den del della di da dos du la le ter ten zu vom y".split())
_ROH_KENNUNG = frozenset({"vertrag", "ausweis", "kvnr", "svnr", "steuerid", "steuernr", "iban", "kfz", "fin",
                          "mandat", "kreditkarte", "kindergeld", "postfach"})
# Ort eines Ereignisses (Unfall, Schaden, Einsatz, Besichtigung) ist keine Anschrift – in jeder Wortstellung
# ("Schadenort", "Ort des Schadens", "Stelle des Unfalls"); Unterschrift/Stempel sind Felder für Tinte
_ROH_KEIN_FELD_RE = re.compile(
    r"(?i)(?:schadens?|unfall|ereignis|tat|einsatz|besichtigungs?|übergabe|uebergabe)(?:ort|stelle)|"
    r"(?:ort|stelle)[ \t]+(?:des|der|vom)[ \t]+(?:schadens?|schadenfalls|unfall(?:e?s)?|ereignisses|geschehens|tat|"
    r"einsatzes|besichtigung|übergabe|uebergabe|untersuchung|termins?)|unterschrift|stempel")
# Ortsangaben: Zusätze zwischen den Wörtern eines Orts ("Frankfurt am Main", "Bad Homburg v. d. Höhe")
_ROH_ORTSZUSATZ = frozenset("am an der den dem im in ob bei vor unter auf a d v i b u".split())
# Ereignis- und Betriebsorte, nie ein Wohnort ("Ort: Parkplatz Rewe-Markt", "Ort: Werkstatt Ihrer Wahl")
_ROH_KEIN_WOHNORT = frozenset("parkplatz parkhaus tiefgarage garage kreuzung einmündung einmuendung ausfahrt "
                              "einfahrt auffahrt autobahn bab bundesstraße bundesstrasse landstraße landstrasse "
                              "kreisstraße kreisstrasse raststätte raststaette rastplatz tankstelle werkstatt "
                              "baustelle supermarkt firmengelände firmengelaende betriebsgelände".split())
# Feldnummer eines Formulars am Wertanfang: das nächste gedruckte Feld ("3. Verletzte", "5) Polizei"), kein Wert
_ROH_FELDNUMMER_RE = re.compile(r"^\(?\d{1,2}[a-z]?(?:[.)][ \t]*|[ \t]+)(?=[^\W\d_])")
# Fortsetzung des gedruckten Feldnamens hinter dem Etikett bis zum Doppelpunkt ("Ort| der Besichtigung:")
_FELDNAME_REST_RE = re.compile(r"[ ]((?:[^\W\d_][\w'’.\-]*[ ]?){1,4}?)[ ]?:")


# Führungspunkte mit eingestreutem OCR-Rest ("2..........;", "i....."): höchstens zwei Zeichen zwischen Punkten
_FUEHRUNGSPUNKTE_RE = re.compile(r"[^\s.…_]{1,2}(?=[.…_]{3})[.…_]{3,}[;:,]?")


def _rohwert_passt(wert: str, kat: str) -> bool:
    """Passt ein OCR-Rohwert zur Kategorie seines Feldnamens? Ohne lesbare Wertform zählt nur die grobe Gestalt:
    Kennungen, Daten und Telefonnummern tragen Ziffern, Namen keine; kein Satzrest, kein weiterer Feldname
    ("NAME", "GEB.-DAT.", "Name, Vorname"), keine Übersetzung eines zweisprachigen Feldnamens ("/ Prénoms")."""
    w = wert.strip()
    if not w or w[0] in "/([{":
        return False
    teile = [t.strip(" .:") for t in re.split(r"\t\t|[ ]*[/,;][ ]*", w) if t.strip(" .:")]
    if not teile or all(etikett_fuer_text(t, mit_vertragsdaten=True) is not None for t in teile):
        return False
    ziffern = sum(c.isdigit() for c in w)
    if kat == "geburt":
        return ziffern >= 3
    if kat == "telefon":
        return ziffern >= 5
    if kat == "email":
        return "@" in w or bool(re.search(r"\w\.\w", w))
    if kat == "bic":
        return sum(c.isalnum() for c in w) >= 8
    if kat in _ROH_KENNUNG:
        return ziffern >= 2
    if kat in ("plzort", "namen") and _ROH_FELDNUMMER_RE.match(w):
        return False                                  # "Ort: 3. Verletzte": das nächste Feld des Formulars
    if kat == "strasse":
        return ziffern >= 1 or bool(re.search(r"(?i)stra(?:ß|ss)e|str\.|weg\b|platz\b|allee\b|gasse\b", w))
    woerter = re.findall(r"[^\W\d_][^\W\d_'’.\-]*", w)
    if kat == "plzort":
        return _roh_ort_passt(w, woerter, ziffern)     # auch eine PLZ allein ("PLZ des Wohnorts: 99423")
    if not woerter:
        return False
    if kat == "namen":
        if ziffern > 1:
            return False
        if woerter[0][0].islower() and woerter[0].casefold() not in _ROH_NAMENSPARTIKEL:
            return False
        if any(x.casefold() in _ROH_FUNKTIONSWORT for x in woerter):
            return False
        lang = [x.strip(".") for x in woerter if len(x) >= 3]
        return bool(lang) and not all(_roh_feldwort(x) for x in lang)
    return True


def _roh_ort_passt(w: str, woerter: list, ziffern: int) -> bool:
    """Grobe Gestalt eines Orts (PLZ, Wohnort, Geburtsort) als Rohwert: eine Postleitzahl oder ein bis drei Wörter mit
    großem Anfang – Ortszusätze ("am Main", "v. d. Höhe") dazwischen –, ohne Funktionswort ("Werkstatt Ihrer Wahl",
    "bitte angeben"), ohne kleingeschriebenen Anfang ("der Besichtigung", "unbekannt verzogen"), ohne Feldnummer und
    ohne Ereignis- oder Betriebsort ("Parkplatz Rewe-Markt")."""
    if re.search(r"(?<!\d)\d{4,5}(?!\d)", w):
        return ziffern <= 6                           # PLZ (mit Ort): "90402 Nürnberg", "D-90402"
    if ziffern:
        return False
    # Ortszusätze zuerst ausnehmen: "am", "an", "im" sind auch Funktionswörter ("Frankfurt am Main" ist ein Ort)
    kern = [x for x in woerter if x.rstrip(".").casefold() not in _ROH_ORTSZUSATZ]
    if any(x.casefold() in _ROH_FUNKTIONSWORT or x.casefold() in _ROH_KEIN_WOHNORT for x in kern):
        return False
    if not kern or not woerter[0][0].isupper() or any(not x[0].isupper() for x in kern) or len(kern) > 3:
        return False
    return not all(_roh_feldwort(x) for x in kern if len(x) >= 3)


def _roh_feldwort(wort: str) -> bool:
    """Feldbezeichner oder Allerweltswort, auch in der Mehrzahl ("Personen", "Namen, Anschriften")."""
    if ist_etikett_oder_allerwelt(wort):
        return True
    stamm = re.sub(r"(?:en|n|s|e)$", "", wort)
    return len(stamm) >= 3 and stamm != wort and (ist_etikett_oder_allerwelt(stamm) or
                                                  etikett_fuer_text(stamm) is not None)


def ocr_rohwert(seite, lg: Lage, et: Etikett, alle: list) -> list:
    """Rohwert hinter einem Feldnamen auf einer gescannten Seite. Handschrift, Druckbuchstaben in Kästchen und
    Schreibmaschine liest die OCR oft als Buchstabensalat ("Versicherungsnummer: REN RER ⇥⇥ ERNEST EI") – keine
    Wertform passt, die Tinte steht trotzdem da. Steht der Feldname am Anfang seiner Zelle, gilt dann der ganze
    Eintrag bis zum nächsten Feldnamen bzw. Zeilenende als Wert (Kategorie nach dem Feldnamen); steht er allein in
    seiner Zeile, der Eintrag der Zeile darunter in derselben Spalte. Nur auf OCR-Zeilen: auf der Textebene sind
    die Wertformen verlässlich. Ausgenommen sind Füllwerte ("wie oben", "entfällt", "nein"), Werte ohne die grobe
    Gestalt ihrer Kategorie (_rohwert_passt: ein Ort ist eine PLZ oder bis zu drei großgeschriebene Wörter ohne
    Funktionswort und ohne Feldnummer – nicht "Werkstatt Ihrer Wahl", "3. Verletzte", "bitte angeben"), Ereignisorte
    in jeder Wortstellung ("Schadenort", "Ort des Schadens", "Ort der Besichtigung") und Unterschriftsfelder. Reicht
    der gedruckte Feldname eines Anschrift-Felds über das Etikett hinaus ("PLZ| des Wohnorts:"), ist der Rest kein
    Wert – gelesen wird erst hinter dem Doppelpunkt."""
    zelle = lg.zelle_bei(et.start)
    if zelle is None or not lg.zeilen_ocr.get(zelle.zeile) or not _etikett_am_zellanfang(seite, lg, et):
        return []
    kat = etikett_kategorie(et, seite.text[et.start:et.ende])
    if kat is None or _ROH_KEIN_FELD_RE.search(seite.text[et.start:et.ende]):
        return []
    text = seite.text
    zeile = seite.zeile_von(et.start)
    if zeile is None:
        return []
    starts = sorted(n.start for n in alle if n.arten)
    # Der gedruckte Feldname reicht bis zum Doppelpunkt: "Ort der Besichtigung:", "Stelle des Unfalls:" – ein
    # Ereignisort ist keine Anschrift, und deckt das Etikett ("PLZ") den Feldnamen nicht ganz ab ("PLZ des
    # Wohnorts:"), ist der Rest kein Wert: der Wert steht erst hinter dem Doppelpunkt (Anschrift-Kategorien; "Name des
    # Kindes:" liest weiter den Namen)
    anfang = et.ende
    fm = _FELDNAME_REST_RE.match(text, et.ende, zelle.ende)
    if fm is not None:
        if _ROH_KEIN_FELD_RE.search(text[et.start:fm.end()]):
            return []
        if kat in ("plzort", "strasse") and not any(fm.start(1) <= s0 < fm.end(1) for s0 in starts):
            anfang = fm.end()

    def bereich(s: int, ende: int):
        h = _HINWEIS_KLAMMER_RE.match(text, s, ende)       # "(TTMMJJJJ)", "(bei Selbstständigen)"
        if h and h.end() > s:
            s = h.end()
        while s < ende:
            while s < ende and text[s] in " \t:;.…_-–":
                s += 1
            m = _FUEHRUNGSPUNKTE_RE.match(text, s, ende)   # "Kontoinhaber ......2.........; Zeidler"
            if not m or m.end() <= s:
                break
            s = m.end()
        i = bisect_right(starts, s)
        if i < len(starts) and starts[i] < ende:
            ende = starts[i]
        e = ende
        while e > s and text[e - 1] in " \t,;:":
            e -= 1
        while s < e and text[s] in " \t,;":
            s += 1
        wert = text[s:e]
        ziffern = sum(c.isdigit() for c in wert)
        if e <= s or sum(c.isalnum() for c in wert) < (2 if ziffern else 3) or len(wert) > 80 \
                or len(wert.split()) > 8:
            return None
        sauber = wert.strip()
        if _FUELLWERT_RE.match(sauber) or _BESCHRIFTUNG_RE.search(sauber):
            return None
        if re.fullmatch(r"[a-zäöüß]{1,5}", sauber):
            return None                                 # Funktionswort/OCR-Rest ("und", "der", "ll")
        if any(t.casefold().strip(".,") in _FIRMEN_TOKEN for t in sauber.split()) or \
                re.search(r"(?i)versicherung|assekuranz|sparkasse|\bbank\b|kasse\b", sauber):
            return None                                 # Firma als Zahlungsempfänger/Versicherer
        if not _rohwert_passt(sauber, kat):
            return None
        if art is not None and not _muster.eigener_rohwert(art, sauber) and not (
                allgemein_hinter(et.eintrag) and _muster.kennungsform(sauber)):
            return None                                 # eVB, Transferticket, CVC: "gültig bis 12/2025" ist keine
        return s, e
    art = eigene_wertform(et.eintrag)
    b = bereich(anfang, zeile.ende)
    if b is not None:
        return [Wert(b[0], b[1], kat)]
    if text[anfang:zeile.ende].strip(" \t:.()…_") and not _HINWEIS_KLAMMER_RE.fullmatch(text[anfang:zeile.ende]):
        return []
    # Feldname allein in seiner Zeile: Eintrag darunter in derselben Spalte
    box = lg.box(et.start, et.ende)
    if box is None:
        return []
    h = max(zelle.hoehe, 4.0)
    for zid in lg.zeilen_darunter(zelle.zeile, 1.9 * h):
        if not lg.zeilen_ocr.get(zid):
            return []
        for z in lg.zellen_je_zeile.get(zid, ()):
            if ueberlappung(z.x0, z.x1, box[0] - h, max(box[2], box[0] + 8 * h)) <= 0:
                continue
            i = bisect_left(starts, z.start)
            if i < len(starts) and starts[i] <= z.start + 2:
                return []                               # darunter steht der nächste Feldname
            b = bereich(z.start, z.ende)
            return [Wert(b[0], b[1], kat)] if b is not None else []
        return []
    return []


def folgezellen_werte(seite, lg: Lage, et: Etikett, werte: list, starts: set) -> list:
    """Weitere Wertzellen derselben Zeile hinter dem ersten Wert – Spalten je Beteiligtem in einer quer gestellten
    Tabelle ("Führerschein-Nr. ⇥⇥ H996KNYGE24 ⇥⇥ P9873B6ND15", Unfallbeteiligte A/B, Versicherte 1/2). Gelesen wird
    nur, solange jede Zelle ganz ein Wert derselben Art wie der erste ist (gleiche Kategorie, ähnliche Länge) und
    kein Feldname in ihr beginnt; das Etikett steht am Anfang seiner Zeile."""
    zelle0 = lg.zelle_bei(et.start)
    if zelle0 is None or not _etikett_am_zellanfang(seite, lg, et):
        return []
    text = seite.text
    zeile = seite.zeile_von(et.start)
    if zeile is None or text[zeile.start:et.start].strip():
        return []
    kategorien = {w.kategorie for w in werte}
    laenge0 = max(1, werte[0].ende - werte[0].start)
    ende_bisher = werte[-1].ende
    aus = []
    for z in sorted(lg.zellen_je_zeile.get(zelle0.zeile, ()), key=lambda z: z.start):
        if z.start < ende_bisher or z.start <= et.start:
            continue
        if any(z.start <= s0 < z.ende for s0 in starts):
            break                                     # nächster Feldname: neue Spalte mit eigenem Wert
        inhalt = text[z.start:z.ende].strip()
        if not inhalt:
            continue
        neu = werte_lesen(text, z.start, z.ende, et, True)
        if not neu or not {w.kategorie for w in neu} <= kategorien:
            break
        if sum(w.ende - w.start for w in neu) < 0.6 * len(inhalt) or \
                not 0.4 <= (neu[0].ende - neu[0].start) / laenge0 <= 2.5:
            break
        aus.extend(neu)
        ende_bisher = neu[-1].ende
        if len(aus) >= 4:
            break
    return aus


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
    art = eigene_wertform(et.eintrag)
    kategorie = et.kategorie
    if art is not None:
        # eVB, Transferticket, Kartenprüfnummer: ihre eigene Form, ganz vorn in der Folgezeile – eVB/Transferticket
        # mit Ziffer ("… das Transferticket" ⏎ "BEITRAGSRECHNUNG …"), eine Kartenprüfnummer nur, wenn die Zeile des
        # Etiketts eine Etikettzeile ist und der Wert die Folgezeile beendet ("… die CVC" ⏎ "1500 EUR …"); hinter einem
        # Nummer-Etikett zusätzlich der allgemeine Kennungsweg ("Versicherungsbestätigung Nr." ⏎ "HR-4711-B")
        if not (art == "cvc" and not _muster.etikett_zeile(text, et.start, et.ende)):
            eigen = eigener_wert(text, folge.start, folge.ende, art, et.kategorie, True, darunter=True,
                                 etikett=et.eintrag)
            if eigen:
                return eigen
        if not allgemein_hinter(et.eintrag):
            return []
        if art == "cvc":
            kategorie = "vertrag"
    m = re.match(r"[ \t]*(?:\S{1,2}[ \t]+)?", text[folge.start:folge.ende])
    for anfang in (folge.start, folge.start + (m.end() if m else 0)):
        sp = kennung_spanne(text, anfang, folge.ende, 3)
        if sp and sp[0] - anfang <= 1 and (art is None or allgemeiner_wert_passt(text[sp[0]:sp[1]])):
            return [Wert(sp[0], sp[1], kategorie or "vertrag")]
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


_KOPF_TOKEN_RE = re.compile(r"[^\s:;,/()\-–+&#]+")


def _kopf_kuerzel(token: str) -> bool:
    """Spaltenkürzel ohne Etikett: mit Punkt oder Unterstrich ("VORN.", "GEB.-DAT.", "TEL_PRIVAT") oder höchstens
    zwei Versalien ("VU", "HF", "ZW"). Ein Versalwort mit drei oder vier Buchstaben ohne Punkt ("KOCH", "UWE",
    "BONN", "PRÜM") ist ein WERT – in einer Formularzeile in Versalien sieht es aus wie ein Kürzel."""
    return bool(ABKUERZUNG_RE.fullmatch(token)) and ("." in token or "_" in token or len(token) <= 2)


def _kopf_wort(token: str) -> bool:
    """Rest einer Kopfzelle neben den Etiketten: Kürzel oder für sich ein Feldname ("VN-NAME": "NAME")."""
    kern = token.strip("._")
    if _kopf_kuerzel(token.lstrip("._")):
        return True
    k = kern.casefold()
    return k in NEUTRALE_KOEPFE or k in _LAUFEND or etikett_fuer_text(kern, mit_vertragsdaten=True) is not None


def _kopfzelle(text: str, z: Zelle, ets: list) -> str | None:
    """Art einer Zelle für die Kopfzeilen-Regel: "etikett" (ganz aus Feldnamen, ggf. mit ":"/"." und Kürzeln –
    "NAME", "VORNAME:", "Name, Vorname", "VN_PLZ"), "kuerzel" bzw. "kurz" (ganz aus Spaltenkürzeln; "kurz": höchstens
    zwei Versalien ohne Punkt, "VU"), "feldwert" (Feldname, Doppelpunkt und Wert: "NAME: KOCH") oder None (anderer
    Inhalt, z. B. ein Wert)."""
    inhalt = list(text[z.start:z.ende])
    for et in ets:
        for i in range(max(et.start, z.start), min(et.ende, z.ende)):
            inhalt[i - z.start] = " "
    rest = "".join(inhalt)
    if ets and ":" in rest and any(c.isalnum() for c in rest[rest.index(":"):]):
        return "feldwert"
    tokens = [t for t in _KOPF_TOKEN_RE.findall(rest) if t.strip("._")]
    if not tokens:
        return "etikett" if ets else None
    if not all(_kopf_wort(t) for t in tokens):
        return None
    if ets:
        return "etikett"
    if len(tokens) == 1 and "." not in tokens[0] and "_" not in tokens[0] and len(tokens[0]) <= 2:
        return "kurz"
    return "kuerzel"


def _wertzeile_darunter(text: str, lg: Lage, zelle: Zelle, zellen: list, alle: list) -> bool:
    """Steht unter einer Kopfzeile eine Wertzeile (mindestens zwei Zellen unter Kopfzellen, davon mindestens eine
    mit Wert statt Feldname)? Eine zweite Kopfzeile darunter (zweizeiliger Kopf) wird übersprungen."""
    h = max(max((z.hoehe for z in zellen), default=0.0), 4.0)
    for zid in lg.zeilen_darunter(zelle.zeile, 2.6 * h)[:2]:
        unter = [c for c in lg.zellen_je_zeile.get(zid, ()) if any(ueberlappung(c.x0, c.x1, k.x0, k.x1) > 0
                                                                     for k in zellen)]
        if len(unter) < 2:
            continue
        arten = [_kopfzelle(text, c, [et for et in alle if c.start <= et.start < c.ende]) for c in unter]
        if any(a is None or a == "feldwert" for a in arten):
            return True
    return False


def kopfzeile(seite, lg: Lage, pos: int, alle: list, cache: dict | None = None) -> bool:
    """Steht `pos` in einer Kopfzeile (Spaltenköpfe einer Liste: mindestens drei Zellen, keine Ziffern, fast jede
    Zelle ganz ein Etikett oder Spaltenkürzel – "NAME ⇥⇥ VORN. ⇥⇥ GEBDAT ⇥⇥ PLZ" – und darunter eine Wertzeile)?
    Rechts neben einem Kopf steht der nächste Kopf, kein Wert.

    Eine ausgefüllte Formularzeile ist nie Kopfzeile, auch in Versalien: eine Zelle "NAME: KOCH" (Feldname mit Wert)
    schließt die Regel aus, ein Versalwort ohne Punkt ("KOCH", "UWE", "BONN") ist kein Kürzel, und ein Kürzel direkt
    rechts neben einem Personen-/Anschrift-Feldnamen ("NAME ⇥⇥ LI ⇥⇥ VORNAME ⇥⇥ YU") ist dessen Wert."""
    zelle = lg.zelle_bei(pos)
    if zelle is None:
        return False
    if cache is not None and zelle.zeile in cache:
        return cache[zelle.zeile]
    zellen = sorted(lg.zellen_je_zeile.get(zelle.zeile, ()), key=lambda z: z.start)
    text = seite.text
    ergebnis = False
    if len(zellen) >= 3 and not any(c.isdigit() or c == "@" for z in zellen for c in text[z.start:z.ende]):
        mit = 0
        feldwert = False
        vorher_pii = False
        for z in zellen:
            ets = [et for et in alle if z.start <= et.start < z.ende]
            art = _kopfzelle(text, z, ets)
            if art == "feldwert":
                feldwert = True
                break
            if art in ("etikett", "kuerzel") or (art == "kurz" and not vorher_pii):
                mit += 1
            vorher_pii = art == "etikett" and any(et.arten & PII_ARTEN for et in ets)
        ergebnis = (not feldwert and mit >= max(3, 0.75 * len(zellen))
                    and _wertzeile_darunter(text, lg, zelle, zellen, alle))
    if cache is not None:
        cache[zelle.zeile] = ergebnis
    return ergebnis


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
        koepfe: dict = {}
        for idx, et in enumerate(alle):
            if not et.arten & PII_ARTEN:
                continue
            if et.arten <= {"person"} and _in_wendung(seite.text, lg, et):
                continue                              # "Verhältnis zum VN: Mitbewohner" ist kein Personenfeld
            werte = []
            bereich = None if kopfzeile(seite, lg, et.start, alle, koepfe) else wert_bereich_rechts(seite, lg, et,
                                                                                                    alle, idx)
            if bereich is not None:
                s, g, mit_trenner = bereich
                werte = werte_lesen(seite.text, s, g, et, mit_trenner)
                if werte and _GREMIUM_RE.search(et.eintrag) and "person" in et.arten:
                    werte += gremium_folgezeilen(seite, lg, et, werte[-1].ende, starts)
                elif werte:
                    werte += folgezellen_werte(seite, lg, et, werte, starts)
            if not werte and _etikett_am_ende(seite, lg, et) and _etikett_am_zellanfang(seite, lg, et) \
                    and not _mit_doppelpunkt(seite, et):
                werte = werte_darunter(seite, lg, et, starts)
                quelle_sicherheit = SICHERHEIT_UNTER
            else:
                quelle_sicherheit = SICHERHEIT_ETIKETT
            if not werte and "kennung" in et.arten:
                werte = kennung_folgezeile(seite, lg, et)
            quelle = "struktur.etikett_wert"
            if not werte and not kopfzeile(seite, lg, et.start, alle, koepfe):
                werte = ocr_rohwert(seite, lg, et, alle)
                quelle, quelle_sicherheit = "struktur.etikett_wert.rohwert", 0.6
            werte = [w for w in werte if w.kategorie in kontext.aktive or not kontext.aktive]
            treffer.extend(_global(dok, nr, werte, quelle, quelle_sicherheit))
    return treffer
