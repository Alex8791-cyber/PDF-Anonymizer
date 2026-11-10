"""OCR-Lesart: Kennungen, Telefonnummern, PLZ und Daten auch dann erkennen, wenn die OCR sich typisch verliest.

Tesseract liest in Ziffernfolgen gern Buchstaben (O/0, I/l/|/1, S/5, B/8, Z/2, G/6, ©/0), fügt Trenner ein
("27568: Bremerhaven", "01511:58548399", "38:077.3762 2", "HFY:4312", "+49'(0)385", "728%41"), liest ein Komma
statt eines Punkts ("37.211.169,7") oder setzt Rauschen vor Tabellenzellen ("[1431 649 845"). Die Regeln dieses
Moduls gelten NUR für OCR-Text – Zeichen mit der Quelle "ocr" (Scan-Seite) oder "bild" (Bildbereich einer
Textseite) im Seitenmodell; auf der Textebene eines PDFs ist ein "O" ein O.

Vorgehen: Für die OCR-Zeilen entsteht eine reparierte Lesart des Dokumenttexts. Sie ist GLEICH LANG – jede
Reparatur ersetzt ein Zeichen durch genau ein Zeichen –, deshalb gelten alle Offsets unverändert. Auf dieser
Lesart laufen die Muster- und Strukturregeln für Kennungen, Telefon, PLZ/Ort und Daten noch einmal; übernommen
werden nur Treffer, die auf dem Originaltext fehlen (Quelle "<regel>.ocr"). Jede Stelle deckt damit genau die
Zeichen, die auf der Seite stehen ("HFY:4312", nicht "HFY 4312"). Die Formprüfungen der Regeln (Prüfziffern,
Etiketten, Mindestlängen) bleiben unverändert streng – die Lesart macht nur den Lesefehler rückgängig.

Reparaturen (nur innerhalb von OCR-Zeilen):
  * Buchstaben in Ziffernfolgen: ein Lauf aus Ziffern und verwechselbaren Buchstaben, mindestens zur Hälfte
    Ziffern, wird ganz zu Ziffern ("8O331" -> "80331", "O171" -> "0171", "S081827865" -> "5081827865") – Buchstaben
    zwischen Ziffern oder EIN Buchstabe am Rand; ein Block aus mehreren Buchstaben am Rand nur aus O/I/l
    ("OO49"), sonst ist es ein Kürzel ("ZB100", "SB150", "BS100" bleiben). Läufe mit anderen Buchstaben bleiben
    ("SV197328226", "L8S0NZWEM31", "DE36").
  * Doppelpunkt zwischen Zifferngruppen (zusammen mindestens 5 Ziffern, keine Uhrzeit) -> Leerzeichen;
    Doppelpunkt zwischen Kennzeichen-Buchstaben und -Ziffern -> Leerzeichen.
  * Komma statt Punkt in gegliederten Nummern ("37.211.169,7" – kein Betrag: nur eine Nachkommastelle).
  * "%" zwischen Ziffern -> "-", Apostroph/Anführung zwischen Ziffern und Klammern -> Leerzeichen,
    Punkt/Komma zwischen den Vierergruppen einer IBAN -> Leerzeichen, "©" vor Ziffern -> "0".
  * Rauschzeichen ([ ] { } _ \\) am Anfang einer Zeile oder Tabellenzelle -> Leerzeichen.
  * Nur im Anschrift-Kontext (anschrift_kontext: Straße mit Hausnummer davor, Anschrift-Etikett davor, Straße in
    der Zeile darüber): Doppelpunkt hinter einer PLZ vor dem Ort -> Leerzeichen ("27568: Bremerhaven"),
    kleingeschriebener Ort direkt hinter einer PLZ -> Großbuchstabe ("Wohnort: 97070 würzburg"). Ohne Anschrift
    bleiben Positionen, Beträge und Mengen stehen ("20231: Zahnbehandlung", "15000 jährlich").
Dazu eine Form, die sich nicht durch Ersetzen darstellen lässt: Kennzeichen hinter dem Etikett mit Rauschen
zwischen den Teilen ("Kennzeichen: B-]JY 743").

PLZ + Ort, die erst die Lesart liefert, zählt nur im Anschrift-Kontext ("Z1000 Sport" ist ein Modellname).
Außerdem verwirft das Modul verlesene Feldbezeichner, die die KI für Namen hält ("Name, Vomame:"), aus den Treffern
des Namens-Detektors "ner" – nur auf OCR-Text (namen.verlesenes_etikett_statt_name).
"""

from __future__ import annotations

import bisect
import copy
import re

from ..seitenmodell import SPALTENTRENNER
from . import REGISTER, Treffer, detektor, registrieren

try:
    from .. import muster as _muster
    from .. import wissen as _wissen
except Exception:  # pragma: no cover - Muster/Wissensbasis fehlen
    _muster = None
    _wissen = None

OCR_QUELLEN = frozenset({"ocr", "bild"})

# Detektoren, die auf der reparierten Lesart noch einmal laufen (Formen mit Ziffern, Etikett + Wert, Tabellen)
LESART_DETEKTOREN = (
    "muster.iban", "muster.telefon", "muster.geburt", "muster.strasse", "muster.plzort", "muster.vertrag",
    "muster.svnr", "muster.steuerid", "muster.steuernr", "muster.kvnr", "muster.kindergeld", "muster.kfz",
    "muster.fin", "muster.ausweis", "muster.mandat", "muster.bic", "muster.kreditkarte", "muster.datum",
    "kundenliste", "struktur.etikett_wert", "struktur.adressblock", "struktur.tabelle", "struktur.betreff",
    "struktur.kopf_fuss", "wissen.geburt", "international",
)
KATEGORIEN = frozenset({"iban", "telefon", "geburt", "strasse", "plzort", "vertrag", "svnr", "steuerid", "steuernr",
                        "kvnr", "kindergeld", "kfz", "fin", "ausweis", "mandat", "bic", "kreditkarte", "datum",
                        "namen", "email", "international"})


# ----------------------------------------------------------------------
# Wo ist OCR-Text?
# ----------------------------------------------------------------------
def zeile_ist_ocr(seite, zeile) -> bool:
    """Stammt die Zeile aus der OCR (Quelle "ocr" oder "bild")? Entscheidend ist ihr erstes Zeichen mit Glyphe."""
    abb = seite.abbildung
    for i in range(zeile.start, min(zeile.ende, len(abb))):
        g = abb[i]
        if g >= 0:
            return seite.zeichen[g].quelle in OCR_QUELLEN
    return False


def ocr_bereiche(dok) -> list:
    """[(start, ende)] der OCR-Zeilen im Dokumenttext (benachbarte Zeilen zusammengefasst), zwischengespeichert."""
    zw = getattr(dok, "_ocr_bereiche", None)
    if zw is not None and zw[0] is dok.text:
        return zw[1]
    aus: list = []
    for nr, seite in enumerate(getattr(dok, "seiten", ()) or ()):
        if not any(z.quelle in OCR_QUELLEN for z in seite.zeichen):
            continue
        basis = dok.seiten_start[nr]
        for z in seite.zeilen:
            if z.ende <= z.start or not zeile_ist_ocr(seite, z):
                continue
            s, e = basis + z.start, basis + z.ende
            if aus and s - aus[-1][1] <= 1:
                aus[-1] = (aus[-1][0], e)
            else:
                aus.append((s, e))
    try:
        dok._ocr_bereiche = (dok.text, aus)
    except AttributeError:
        pass
    return aus


# ----------------------------------------------------------------------
# Reparaturen (gleich lang: Zeichen für Zeichen)
# ----------------------------------------------------------------------
_VERWECHSLUNG = {"O": "0", "o": "0", "D": "0", "Q": "0", "©": "0", "I": "1", "l": "1", "i": "1", "|": "1",
                 "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6"}
_KURZ_VERWECHSLUNG = frozenset("OoDQ©Il")             # in kurzen Läufen (bis 3 Zeichen) nur 0 und 1
_LAUF_RE = re.compile(r"[0-9A-Za-zÄÖÜäöüß©|]+")
_DOPPELPUNKT_RE = re.compile(r"(?<=\d):(?=\d)")
_KOMMA_GLIEDERUNG_RE = re.compile(r"(?<![\d.,])\d{1,3}(?:\.\d{3}){2,}(,)\d(?![\d,])")
_PROZENT_RE = re.compile(r"(?<=\d)%(?=\d)")
_ANFUEHRUNG_RE = re.compile(r"(?<=[\d)])['’‘`´\"”„](?=[\d(])")
_IBAN_GRUPPEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}[0-9A-Z]{2}(?:[ .,][A-Z0-9]{4}){2,7}(?:[ .,][A-Z0-9]{1,4})?"
                              r"(?![A-Za-z0-9])")
_COPYRIGHT_RE = re.compile(r"©(?=[ \n]?\d)")
_PLZ_DOPPELPUNKT_RE = re.compile(r"(?<![\w.,/\-])(?:(?:D|DE)-)?\d{5}(:)(?=[ \t]?[A-ZÄÖÜa-zäöü])")
_KFZ_DOPPELPUNKT_RE = re.compile(r"(?<![\w\-])[A-ZÄÖÜ]{1,3}(?:[- ][A-Z]{1,2})?(:)(?=\d{1,4}[EH]?(?![\w]))")
_RAUSCHEN_RE = re.compile(r"(?:^|(?<=\t\t)|(?<=\n))((?:[\[\]{}_\\][ ]?)+)(?=[A-Za-z0-9ÄÖÜ])")
_PLZ_KLEIN_RE = re.compile(r"(?:^|(?<=\t\t)|(?<=\n))[ ]*(?:(?:D|DE)-)?\d{5}[ ]+([a-zäöü])(?=[a-zäöüß]{2,}"
                           r"(?:[ -][A-Za-zÄÖÜäöüß.()]+){0,3}[ ]*(?:$|\t\t|\n|,))")


def _randblock(lauf: str) -> tuple:
    """(Buchstaben am Anfang, Buchstaben am Ende) eines Laufs."""
    vorn = len(lauf) - len(lauf.lstrip("".join(_VERWECHSLUNG)))
    hinten = len(lauf) - len(lauf.rstrip("".join(_VERWECHSLUNG)))
    return lauf[:vorn], lauf[len(lauf) - hinten:]


def _ziffern_laeufe(t: str, z: list) -> None:
    for m in _LAUF_RE.finditer(t):
        lauf = m.group(0)
        if len(lauf) < 2:
            continue
        ziffern = sum(c.isdigit() for c in lauf)
        if not ziffern or ziffern == len(lauf) or 2 * ziffern < len(lauf):
            continue
        if any(not c.isdigit() and c not in _VERWECHSLUNG for c in lauf):
            continue
        if lauf[0] == "|" or lauf[-1] == "|":
            continue                                  # Tabellenlinie am Rand, keine "1"
        if len(lauf) <= 3 and any(not c.isdigit() and c not in _KURZ_VERWECHSLUNG for c in lauf):
            continue                                  # "B1", "S2", "Z1": kurze Kürzel bleiben (nur "O7" -> "07")
        if any(len(block) >= 2 and any(c not in _KURZ_VERWECHSLUNG for c in block) for block in _randblock(lauf)):
            continue                                  # "ZB100", "SB150", "BS100": Tarifkürzel, kein Lesefehler
        for k, c in enumerate(lauf):
            if not c.isdigit():
                z[m.start() + k] = _VERWECHSLUNG[c]


# ----------------------------------------------------------------------
# Anschrift-Kontext einer PLZ
# ----------------------------------------------------------------------
# Trenner zwischen Straße und PLZ ("Birkenallee 119, 27568", "Hauptstraße 5 · 79098", Zellen)
_TRENNER_VOR_PLZ_RE = re.compile(r"[ \t,;·•|/–\-]*$")
# Anschrift-Etiketten der Wissensbasis, hinter denen eine PLZ steht (nicht: Hausnummer, Etage, Land …)
_ANSCHRIFT_EINTRAG_RE = re.compile(r"anschrift|adress|address|plz|postleitzahl|postcode|zip|wohn|ort\b|city|"
                                   r"gemeinde|postfach|c/o|belegenheit|lage des risikos")


def _anschrift_etikett_in(zeile: str, am_ende: bool = False) -> bool:
    """Steht in der Zeile ein Anschrift-Etikett (auch verlesen: "Anschrlft:")? am_ende=True: nur als Abschluss der
    Zeile ("Anschrift:" mit dem Wert in der Zeile darunter)."""
    if _wissen is None or not zeile.strip():
        return False
    ende = len(zeile.rstrip(" \t:")) if am_ende else 0
    try:
        eintraege = [v.eintrag for v in _wissen.finde(zeile, "etiketten_adresse") if v.ende >= ende]
    except Exception:
        eintraege = []
    if not eintraege and re.search(r"[^\W\d_]{7,}", zeile):
        try:
            from .etiketten_unscharf import unscharfe_etiketten
            eintraege = [eintrag for _, e, art, eintrag in unscharfe_etiketten(zeile) if art == "adresse" and e >= ende]
        except Exception:  # pragma: no cover - Modul fehlt
            eintraege = []
    return any(_ANSCHRIFT_EINTRAG_RE.search(_wissen.normalisieren(e)) for e in eintraege)


def _strasse_am_ende(text: str) -> bool:
    """Endet der Text (ohne Trenner) mit Straße und Hausnummer, ohne Spaltentrenner in der Straße?"""
    kern = text[:_TRENNER_VOR_PLZ_RE.search(text).start()]
    if not kern.strip() or _muster is None:
        return False
    try:
        stellen = _muster.stellen("strasse", kern)
    except Exception:  # pragma: no cover - Muster defekt
        return False
    return any(st.ende >= len(kern) and SPALTENTRENNER not in kern[st.start:st.ende] for st in stellen)


def _strasse_in(zeile: str) -> bool:
    if _muster is None or not zeile.strip():
        return False
    try:
        stellen = _muster.stellen("strasse", zeile)
    except Exception:  # pragma: no cover - Muster defekt
        return False
    return any(SPALTENTRENNER not in zeile[st.start:st.ende] for st in stellen)


def anschrift_kontext(text: str, pos: int) -> bool:
    """Steht die Zahl an `pos` dort, wo eine PLZ steht? Straße mit Hausnummer direkt davor ("Birkenallee 119,
    27568: Bremerhaven") oder ein Anschrift-Etikett davor in derselben Zeile ("Wohnort: 97070 würzburg"); am
    Zeilen- oder Zellenanfang auch eine Straße in der Zeile darüber (Anschriftblock) oder ein Anschrift-Etikett am
    Ende der Zeile darüber ("Anschrift:" ⏎ "…"). Positionen, Beträge, Mengen und Kürzel ("20231: Zahnbehandlung",
    "15000 jährlich", "ZB100 Zahnersatz") haben das nicht."""
    zeilenanfang = text.rfind("\n", 0, pos) + 1
    davor = text[zeilenanfang:pos]
    if davor.strip() and (_strasse_am_ende(davor) or _anschrift_etikett_in(davor)):
        return True
    if zeilenanfang == 0 or (davor.strip() and not davor.rstrip(" ").endswith(SPALTENTRENNER)):
        return False                                  # mitten in der Zeile: die Zeile darüber zählt nicht
    vorige = text[text.rfind("\n", 0, zeilenanfang - 1) + 1:zeilenanfang - 1]
    return _strasse_in(vorige) or _anschrift_etikett_in(vorige, am_ende=True)


def _gruppe_links(t: str, i: int) -> int:
    n = 0
    while i - 1 - n >= 0 and t[i - 1 - n].isdigit():
        n += 1
    return n


def _gruppe_rechts(t: str, i: int) -> int:
    n = 0
    while i + 1 + n < len(t) and t[i + 1 + n].isdigit():
        n += 1
    return n


def reparieren(t: str) -> str:
    """Reparierte Lesart eines OCR-Textstücks (gleich lang). Siehe Modulkopf."""
    z = list(t)
    _ziffern_laeufe(t, z)
    zw = "".join(z)
    for m in _DOPPELPUNKT_RE.finditer(zw):
        links, rechts = _gruppe_links(zw, m.start()), _gruppe_rechts(zw, m.start())
        if links + rechts >= 5 and max(links, rechts) >= 3:
            z[m.start()] = " "
    for m in _KOMMA_GLIEDERUNG_RE.finditer(zw):
        z[m.start(1)] = "."
    for regel, zeichen in ((_PROZENT_RE, "-"), (_ANFUEHRUNG_RE, " "), (_COPYRIGHT_RE, "0")):
        for m in regel.finditer(zw):
            z[m.start()] = zeichen
    for m in _IBAN_GRUPPEN_RE.finditer(zw):
        for k in range(m.start(), m.end()):
            if zw[k] in ".,":
                z[k] = " "
    for m in _KFZ_DOPPELPUNKT_RE.finditer(zw):
        z[m.start(1)] = " "
    for m in _RAUSCHEN_RE.finditer(zw):
        for k in range(m.start(1), m.end(1)):
            if zw[k] != " ":
                z[k] = " "
    # PLZ-Reparaturen nur, wo eine Anschrift steht ("20231: Zahnbehandlung", "15000 jährlich" bleiben)
    zw = "".join(z)
    for m in _PLZ_DOPPELPUNKT_RE.finditer(zw):
        if anschrift_kontext(zw, m.start()):
            z[m.start(1)] = " "
    for m in _PLZ_KLEIN_RE.finditer(zw):
        gross = zw[m.start(1)].upper()
        if len(gross) == 1 and anschrift_kontext(zw, m.start()):
            z[m.start(1)] = gross
    return "".join(z)


def lesart(dok) -> str | None:
    """Reparierte Lesart des Dokumenttexts (gleich lang) oder None, wenn es nichts zu reparieren gibt."""
    bereiche = ocr_bereiche(dok)
    if not bereiche:
        return None
    text = dok.text
    teile, pos, geaendert = [], 0, False
    for s, e in bereiche:
        teile.append(text[pos:s])
        neu = reparieren(text[s:e])
        geaendert = geaendert or neu != text[s:e]
        teile.append(neu)
        pos = e
    teile.append(text[pos:])
    if not geaendert:
        return None
    neu = "".join(teile)
    return neu if len(neu) == len(text) else None


def _lesart_dokument(dok, neu: str):
    """Kopie des Modells mit dem reparierten Text (Seiten mit unverändertem Text bleiben dieselben Objekte)."""
    seiten = []
    for nr, seite in enumerate(dok.seiten):
        a = dok.seiten_start[nr]
        t = neu[a:a + len(seite.text)]
        if t == seite.text:
            seiten.append(seite)
            continue
        kopie = copy.copy(seite)
        for name in [n for n in vars(kopie) if n.startswith("_struktur") or n.startswith("_ocr")]:
            delattr(kopie, name)
        kopie.text = t
        kopie._fingerabdruck = None
        seiten.append(kopie)
    d = copy.copy(dok)
    for name in [n for n in vars(d) if n.startswith("_struktur") or n.startswith("_klassisch") or n.startswith("_ocr")]:
        delattr(d, name)
    d.seiten = seiten
    d.text = neu
    d._fingerabdruck = None
    d.struktur_vorschlaege = []                     # Vorschläge der Lesart gehen nicht in die Oberfläche
    return d


# ----------------------------------------------------------------------
# Kennzeichen mit Rauschen hinter dem Etikett
# ----------------------------------------------------------------------
_KFZ_ETIKETT_RE = re.compile(r"(?<![\wäöüß])(?i:(?:amtl(?:iches|\.)?[ \t]+)?(?:kfz-?)?kennzeichen|kennz\.)"
                             r"[ \t]*:?[ \t]*(?:\t\t[ \t]*)?")
_KFZ_RAUSCH_RE = re.compile(r"([A-ZÄÖÜ]{1,3})[ \-:.]{0,2}[\]\[|!'’‘:.]{1,2}[ \-]?([A-Z]{1,2})[ :.\-]?(\d{1,4})[EH]?"
                            r"(?![\w])")


def _kennzeichen_mit_rauschen(text: str, bereiche: list) -> list:
    aus = []
    for s, e in bereiche:
        for m in _KFZ_ETIKETT_RE.finditer(text, s, e):
            w = _KFZ_RAUSCH_RE.match(text, m.end(), e)
            if w and SPALTENTRENNER not in w.group(0):
                aus.append(Treffer(w.start(), w.end(), "kfz", "ocr.kennzeichen", 0.6))
    return aus


# ----------------------------------------------------------------------
# Detektor
# ----------------------------------------------------------------------
def _normiert(text: str, treffer) -> set:
    aus = set()
    for t in treffer or ():
        if not isinstance(t, Treffer):
            t = Treffer(*t)
        s, e = max(0, int(t.start)), min(len(text), int(t.ende))
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e > s:
            aus.add(t._replace(start=s, ende=e))
    return aus


@detektor("ocr.lesart", KATEGORIEN)
def ocr_lesart(dok, kontext):
    """Muster und Strukturregeln noch einmal auf der reparierten OCR-Lesart (nur OCR-Text, siehe Modulkopf);
    Treffer, die der Originaltext nicht liefert, mit Quelle "<regel>.ocr"."""
    bereiche = ocr_bereiche(dok)
    if not bereiche:
        return []
    treffer = _kennzeichen_mit_rauschen(dok.text, bereiche)
    neu = lesart(dok)
    if neu is None:
        return treffer
    zweit = _lesart_dokument(dok, neu)
    aktiv = set(kontext.aktive)
    for name in LESART_DETEKTOREN:
        eintrag = next((e for e in REGISTER if e.name == name), None)
        if eintrag is None or kontext.profil not in eintrag.profile or not (eintrag.kategorien & aktiv):
            continue
        try:
            vorher = _normiert(dok.text, eintrag.funktion(dok, kontext))
            nachher = _normiert(neu, eintrag.funktion(zweit, kontext))
        except Exception:
            continue                                  # die Regel selbst meldet ihren Ausfall im Hauptdurchlauf
        bekannt = {(t.start, t.ende, t.kategorie) for t in vorher}
        for t in sorted(nachher):
            if (t.start, t.ende, t.kategorie) in bekannt:
                continue
            if t.kategorie == "plzort" and not anschrift_kontext(neu, t.start):
                continue                              # "ZB100 Zahnersatz", "Z1000 Sport": keine Anschrift
            treffer.append(t._replace(quelle=f"{t.quelle}.ocr", sicherheit=min(t.sicherheit, 0.7)))
    return treffer


# ----------------------------------------------------------------------
# Verlesene Etiketten sind keine Namen (nur OCR-Text)
# ----------------------------------------------------------------------
def _in_ocr(bereiche: list, s: int, e: int) -> bool:
    i = bisect.bisect_right(bereiche, (s, float("inf"))) - 1
    return i >= 0 and bereiche[i][0] <= s and e <= bereiche[i][1]


def _ner_ohne_verlesene_etiketten(alt):
    def namen_ohne_verlesene_etiketten(dok, kontext):
        treffer = list(alt(dok, kontext) or [])
        bereiche = ocr_bereiche(dok) if treffer else []
        if not bereiche:
            return treffer                            # Textebene: keine Toleranz, jeder Name bleibt
        try:
            from ..namen import verlesenes_etikett_statt_name
        except Exception:  # pragma: no cover - Modul fehlt
            return treffer
        aus = []
        for t in treffer:
            tt = t if isinstance(t, Treffer) else Treffer(*t)
            if (tt.kategorie == "namen" and _in_ocr(bereiche, tt.start, tt.ende)
                    and verlesenes_etikett_statt_name(dok.text, tt.start, tt.ende)):
                continue                              # "Name, Vomame:" – ein verlesener Feldbezeichner
            aus.append(t)
        return aus
    namen_ohne_verlesene_etiketten.__doc__ = (
        f"{(alt.__doc__ or '').strip()}\n\nAuf OCR-Text ohne verlesene Feldbezeichner (\"Name, Vomame:\", "
        f"namen.verlesenes_etikett_statt_name); auf der Textebene unverändert.")
    return namen_ohne_verlesene_etiketten


def _ner_umhuellen():
    """Den Namens-Detektor ("ner", klassisch.py oder sein Ersatz) um den OCR-Filter ergänzen: die KI hält
    verlesene Feldbezeichner gern für Namen. Der Filter braucht die Quelle der Zeichen, die nur das Seitenmodell
    kennt – namen.py sieht nur Text und bleibt deshalb ohne Toleranz für Lesefehler."""
    alt = next((e for e in REGISTER if e.name == "ner"), None)
    if alt is None or getattr(alt.funktion, "__name__", "") == "namen_ohne_verlesene_etiketten":
        return                                        # kein Namens-Detektor oder schon umhüllt (erneuter Import)
    registrieren("ner", alt.kategorien, alt.profile, _ner_ohne_verlesene_etiketten(alt.funktion), ersetzt=True)


_ner_umhuellen()
