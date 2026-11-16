"""Kammfelder und gesperrte Schrift: ein Zeichen je Kästchen ("M U S T E R M A N N", "D E ⇥⇥ 8 8 ⇥⇥ 9 8 8 6").

Formulare "bitte in Druckbuchstaben, je Kästchen ein Zeichen" stehen in der Textebene bzw. in der OCR-Lesung als
Folge einzelner Zeichen, getrennt durch ein Leerzeichen oder – über leere Kästchen und Gruppenlücken – durch den
Spaltentrenner. Kein Muster und keine Namensliste erkennt "M A R K O V I Ć" als Namen.

»struktur.kammfeld«: Folgen von mindestens drei Zeichen-Stücken (überwiegend einzelne Buchstaben/Ziffern, die OCR
klebt manchmal zwei zusammen: "M A G D E B U RG") werden zu einem Wert verbunden. Die Kategorie kommt vom Feldnamen
(in derselben Zeile links oder allein in der Zeile darüber: Name/Vorname -> namen, Geburtsdatum -> geburt,
Straße/Hausnummer -> strasse, PLZ/Ort -> plzort, Telefon/E-Mail, Kennungen nach ihrer Art); ohne Feldnamen zählt
nur, was sich selbst ausweist (IBAN mit stimmender Prüfsumme, Steuer-ID mit Prüfziffer). Geschwärzt wird die
ganze Zeichenfolge in der Zeile.
"""

from __future__ import annotations

import re

from . import ALLE_PROFILE, Treffer, detektor
from .struktur import ALLE_KATEGORIEN, etiketten, lage

QUELLE = "struktur.kammfeld"
_STUECK_RE = re.compile(r"\S+")
_PLZ_ORT_ETIKETT_RE = re.compile(r"(?i)^(?:plz|postleitzahl|ort|wohnort|plz[ ,/]*ort|postleitzahl und ort)\.?:?$")
_ZEICHEN = re.compile(r"[^\W_]|[-/.]")


def _laeufe(text: str, start: int, ende: int) -> list:
    """[(s, e, wert)] gesperrter Folgen in text[start:ende]; wert ist verbunden (Kästchenlücken als Leerzeichen)."""
    stuecke = [(m.start(), m.end()) for m in _STUECK_RE.finditer(text, start, ende)]
    aus = []
    i = 0
    while i < len(stuecke):
        j = i
        folge = []
        while j < len(stuecke):
            s, e = stuecke[j]
            t = text[s:e]
            if len(t) > 2 or not all(_ZEICHEN.fullmatch(c) for c in t):
                break
            if folge:
                zwischen = text[folge[-1][1]:s]
                if zwischen not in (" ",) and not re.fullmatch(r"[ ]?\t\t[ ]?", zwischen):
                    break
            folge.append((s, e))
            j += 1
        einzel = sum(1 for s, e in folge if e - s == 1)
        if len(folge) >= 3 and einzel >= max(3, 0.6 * len(folge)) and \
                sum(1 for s, e in folge if any(c.isalnum() for c in text[s:e])) >= 3:
            teile = []
            for k, (s, e) in enumerate(folge):
                if k and "\t" in text[folge[k - 1][1]:s]:
                    teile.append(" ")
                teile.append(text[s:e])
            aus.append((folge[0][0], folge[-1][1], "".join(teile)))
            i = j
        else:
            i += 1
    return aus


def kategorie_fuer(et, etikett_text: str, wert: str) -> str | None:
    """Kategorie eines Werts hinter einem Feldnamen."""
    arten = et.arten
    if "person" in arten:
        return "namen"
    if "datum_geburt" in arten:
        return "geburt"
    if "kennung" in arten:
        return et.kategorie or "vertrag"
    if "kontakt" in arten:
        return et.kategorie or ("email" if "@" in wert else "telefon")
    if "adresse" in arten:
        return "plzort" if _PLZ_ORT_ETIKETT_RE.match(etikett_text.strip()) else "strasse"
    return None


def _ohne_etikett(wert: str) -> str | None:
    """Kategorie eines gesperrten Werts ohne Feldnamen: nur was sich selbst ausweist."""
    try:
        from .. import muster
    except Exception:  # pragma: no cover
        return None
    kompakt = wert.replace(" ", "")
    for kategorie in ("iban", "steuerid", "kvnr"):
        if any(s.streng and s.ende - s.start >= len(kompakt) - 1 for s in muster.stellen(kategorie, kompakt)):
            return kategorie
    return None


@detektor(QUELLE, ALLE_KATEGORIEN, ALLE_PROFILE)
def kammfeld(dok, kontext):
    """Werte in Kammfeldern/gesperrter Schrift mit der Kategorie ihres Feldnamens."""
    treffer = []
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        if not text.strip() or not re.search(r"(?:(?<!\S)\S ){3}", text):
            continue
        laeufe_je_zeile = []
        for z in seite.zeilen:
            for s, e, wert in _laeufe(text, z.start, z.ende):
                laeufe_je_zeile.append((z, s, e, wert))
        if not laeufe_je_zeile:
            continue
        lg = lage(seite)
        ets = [et for et in etiketten(seite) if et.arten]
        for z, s, e, wert in laeufe_je_zeile:
            # Feldname: links in derselben Zeile (das nächste davor) oder allein in einer Zeile darüber
            et_wahl = None
            for et in ets:
                if z.start <= et.start and et.ende <= s:
                    et_wahl = et                      # das letzte Etikett vor dem Wert
            if et_wahl is not None:
                zwischen = re.sub(r"\([^()\n]{0,30}\)", "", text[et_wahl.ende:s])     # "(TTMMJJJJ)", "(n)"
                if any(c.isalnum() for c in zwischen):
                    et_wahl = None                    # zwischen Feldname und Wert steht noch etwas anderes
            if et_wahl is None and not text[z.start:s].strip():
                zelle = lg.zelle_bei(s)
                if zelle is not None:
                    for zid in _zeilen_darueber(lg, zelle.zeile, zelle.hoehe)[:1]:
                        kandidaten = [et for et in ets if lg.zelle_bei(et.start) is not None
                                      and lg.zelle_bei(et.start).zeile == zid]
                        if len(kandidaten) == 1:
                            et_wahl = kandidaten[0]
            if et_wahl is not None:
                kat = kategorie_fuer(et_wahl, text[et_wahl.start:et_wahl.ende], wert)
            else:
                kat = _ohne_etikett(wert)
            if kat is None or (kontext.aktive and kat not in kontext.aktive):
                continue
            treffer.append(Treffer(dok.global_(nr, s), dok.global_(nr, e), kat, QUELLE,
                                   0.85 if et_wahl is not None else 0.9))
    return treffer


def _zeilen_darueber(lg, zid: int, hoehe: float) -> list:
    """Zeilen-IDs direkt über `zid` (nächste zuerst), höchstens gut zwei Zeilenhöhen entfernt."""
    box = lg.zeilen_box.get(zid)
    if box is None:
        return []
    h = max(hoehe, 6.0)
    kandidaten = []
    for z2, b2 in lg.zeilen_box.items():
        if z2 == zid:
            continue
        abstand = box[1] - b2[3]
        if -0.3 * h <= abstand <= 2.2 * h and min(box[2], b2[2]) - max(box[0], b2[0]) > -2 * h:
            kandidaten.append((abstand, z2))
    return [z2 for _, z2 in sorted(kandidaten)]
