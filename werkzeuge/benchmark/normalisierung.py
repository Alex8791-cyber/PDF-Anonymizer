"""Gemeinsame Textnormalisierung für Generator (Kollisionsprüfung) und Bewertung (Leck-Suche).

Grundlage ist die Normalisierung aus BENCHMARK_SCHEMA.md (casefold, Leerraum entfernt,
Trennstriche entfernt). Zwei Ergänzungen machen den Vergleich robuster und werden im Bericht
genannt:

* Diakritika werden entfernt (ş -> s, ł -> l, ő -> o, ß -> ss): OCR liest Akzente oft falsch
  oder gar nicht; ohne Faltung würde ein sichtbar gebliebener Name wie „Şahin“, den die OCR als
  „Sahin“ liest, NICHT als Leck gezählt (zu Gunsten des Programms – das wäre unehrlich).
* Wortgrenzen bleiben als Positionsmenge erhalten: Ein Treffer zählt nur, wenn er im Original an
  einer Wortgrenze beginnt und endet. Leerraum und Trennstriche innerhalb des Treffers spielen
  keine Rolle („DE89 3704 …“ = „DE893704…“, „Muster-\\nmann“ = „Mustermann“), aber „Nürnberg“
  steckt nicht in „Nürnberger“ und „Ana“ nicht in „Analyse“.
"""

import re
import unicodedata

# Buchstaben ohne Zerlegung in Grundbuchstabe + Akzent
_SONDER = {
    "ß": "ss", "ẞ": "ss", "ł": "l", "Ł": "l", "ı": "i", "ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe", "đ": "d", "Đ": "d", "þ": "th", "Þ": "th", "ð": "d", "Ð": "d", "ħ": "h",
    "Ħ": "h", "ŀ": "l", "Ŀ": "l", "ĸ": "k", "ŉ": "n", "ſ": "s",
}
# Zeichen, die als Trennstrich gelten (entfallen, markieren aber eine Wortgrenze)
_TRENNSTRICHE = set("-­‐‑‒–−")

_CACHE: dict = {}


def _zeichen_falten(zeichen: str) -> str:
    """Ein Zeichen -> gefaltete Zeichenfolge (Kleinbuchstaben ohne Diakritika)."""
    erg = _CACHE.get(zeichen)
    if erg is not None:
        return erg
    if zeichen in _SONDER:
        erg = _SONDER[zeichen]
    else:
        zerlegt = unicodedata.normalize("NFKD", zeichen)
        erg = "".join(c for c in zerlegt if not unicodedata.combining(c))
        erg = "".join(_SONDER.get(c, c) for c in erg).casefold()
        erg = "".join(_SONDER.get(c, c) for c in erg)
    _CACHE[zeichen] = erg
    return erg


class Gefaltet:
    """Gefalteter Text: `kette` enthält nur Buchstaben/Ziffern (klein, ohne Diakritika),
    `grenzen` die Positionen in `kette`, an denen im Original ein Wort beginnt oder endet."""

    __slots__ = ("kette", "grenzen")

    def __init__(self, text: str):
        teile: list = []
        grenzen = {0}
        laenge = 0
        nach_trenner = True
        for zeichen in text or "":
            if zeichen in _TRENNSTRICHE:
                nach_trenner = True
                continue
            gefaltet = _zeichen_falten(zeichen)
            if not gefaltet:
                continue                      # z. B. allein stehender Akzent
            for c in gefaltet:
                if c.isalnum():
                    if nach_trenner:
                        grenzen.add(laenge)
                    teile.append(c)
                    laenge += 1
                    nach_trenner = False
                else:
                    nach_trenner = True
        grenzen.add(laenge)
        self.kette = "".join(teile)
        self.grenzen = grenzen

    def finde(self, nadel: "Gefaltet | str", grenzen_pruefen: bool = True) -> list:
        """Startpositionen aller Treffer von `nadel` (an Wortgrenzen, falls verlangt)."""
        n = nadel.kette if isinstance(nadel, Gefaltet) else Gefaltet(nadel).kette
        if not n:
            return []
        treffer, start = [], 0
        while True:
            i = self.kette.find(n, start)
            if i < 0:
                return treffer
            start = i + 1
            if grenzen_pruefen and (i not in self.grenzen or i + len(n) not in self.grenzen):
                continue
            treffer.append(i)

    def enthaelt(self, nadel, grenzen_pruefen: bool = True) -> bool:
        return bool(self.finde(nadel, grenzen_pruefen))

    def zaehle(self, nadel, grenzen_pruefen: bool = True) -> int:
        return len(self.finde(nadel, grenzen_pruefen))


def falten(text: str) -> str:
    """Nur die gefaltete Zeichenkette (für Schlüssel und Vergleiche)."""
    return Gefaltet(text).kette


def schema_norm(text: str) -> str:
    """Normalisierung genau nach Schema (casefold, Leerraum und Trennstriche entfernt)."""
    return re.sub(r"[\s\-­‐‑–]", "", (text or "").casefold())


# ----------------------------------------------------------------------
# Signifikante Token (für „teilweise“)
# ----------------------------------------------------------------------
# Wörter, deren Rest NICHT als Teil-Leck zählt (generisch, Anreden, Titel, Partikel,
# Adressbestandteile, Rechtsformen, Mail-Anbieter)
GENERISCH = {
    "strasse", "str", "weg", "platz", "allee", "ring", "gasse", "damm", "ufer", "markt", "steig",
    "pfad", "chaussee", "promenade", "am", "an", "im", "in", "auf", "zum", "zur", "unter", "hinter",
    "vor", "bei", "alten", "alte", "alter", "neue", "neuen", "der", "den", "dem", "des", "die", "das",
    "und", "von", "van", "vom", "zu", "de", "la", "le", "di", "da", "del", "dos", "du", "ter", "ten",
    "herr", "herrn", "frau", "familie", "fam", "eheleute", "dr", "med", "dent", "prof", "dipl", "ing",
    "rer", "nat", "jur", "phil", "habil", "univ", "kfm", "gmbh", "ag", "kg", "mbh", "co", "ohg", "ev",
    "postfach", "bad", "st", "sankt", "main", "oder", "saale", "havel", "lech", "neckar", "breisgau",
    "taunus", "pegnitz", "allgau", "aller", "westerwald", "weinstrasse", "pfalz", "hohe", "hoehe",
    "geb", "geboren", "tel", "telefon", "fax", "mobil", "handy", "mail", "email", "iban", "bic",
    "nr", "web", "gmx", "com", "net", "org", "online", "mailbox", "posteo", "outlook", "gmail",
    "yahoo", "icloud", "freenet", "arcor", "vodafone", "versicherung", "versicherungen", "praxis",
    "www", "http", "https", "c", "o", "co", "kreis", "stadt", "jun", "sen", "junior", "senior",
    "typ", "mbh", "eg", "se", "partner", "kollegen",
}


def token(text: str) -> list:
    """Wort-Token (gefaltet) eines Eintragstexts in Reihenfolge, Duplikate entfernt."""
    aus, gesehen = [], set()
    g = Gefaltet(text)
    grenzen = sorted(g.grenzen)
    for a, b in zip(grenzen, grenzen[1:]):
        t = g.kette[a:b]
        if t and t not in gesehen:
            gesehen.add(t)
            aus.append(t)
    return aus


def signifikant(tok: str) -> bool:
    """Signifikantes Token: >= 3 Zeichen, nicht generisch; reine Zahlen erst ab 4 Ziffern."""
    if tok in GENERISCH:
        return False
    if tok.isdigit():
        return len(tok) >= 4
    return len(tok) >= 3


def signifikante_token(text: str) -> list:
    return [t for t in token(text) if signifikant(t)]
