"""Kleine Satz-Engine für die Benchmark-Dokumente – mit Mitschrift der Wahrheitseinträge.

Texte werden mit einer Inline-Auszeichnung geschrieben:

    "Sehr geehrte Frau ⟦namen|Groß|Anrede⟧,"      -> Eintrag (Kategorie namen, Bemerkung Anrede)
    "Tarif ⟦kontext|KomfortMed 300⟧"              -> Eintrag mit erwartung=behalten

Jede Auszeichnung wird beim Setzen zu genau einem Eintrag der Wahrheitsdatei: mit dem Text, wie
er auf der Seite steht (nach evtl. Transliteration für Base14-Schriften), der Seite und den
Wortrechtecken (für den Pixelvergleich bei Scans). Unausgezeichneter Text wird als „Klartext“
je Seite mitgeschrieben – damit prüft der Generator, dass kein personenbezogener Wert zufällig
auch im übrigen Text steht (sonst wäre die Leck-Prüfung mehrdeutig).

Schriften: Base14 (helv/tiro/cour, nicht eingebettet, WinAnsi) oder eingebettete TrueType-Dateien
aus dem System. Gesucht werden metrisch kompatible Paare (Liberation Sans/Arial, Liberation Serif/
Times New Roman, Liberation Mono/Courier New, Carlito/Calibri), damit Zeilenumbrüche unter Linux
und Windows gleich ausfallen. Fehlt eine Datei, wird auf Base14 zurückgefallen.
"""

import os
import random
import re
import sys
import unicodedata
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

A4_B, A4_H = 595.28, 841.89
MM = 72 / 25.4

KERN = {"namen", "strasse", "plzort", "postfach", "geburt", "telefon", "email", "iban", "bic", "kreditkarte",
        "steuerid", "steuernr", "svnr", "kvnr", "kindergeld", "vertrag", "kfz", "fin", "ausweis", "mandat"}
ERWEITERT = {"diagnose", "beruf", "arbeitgeber", "auslaendisch", "sonstiges"}
KONTEXT = "kontext"

_AUSZEICHNUNG = re.compile(r"⟦([a-z]+)\|([^⟦⟧|]*)(?:\|([^⟦⟧]*))?⟧")


def m(kategorie: str, text, bemerkung: str = "") -> str:
    """Auszeichnung für einen Eintrag bauen."""
    text = str(text)
    if any(z in text for z in "⟦⟧|"):
        raise ValueError(f"Unzulässiges Zeichen im Eintragstext: {text!r}")
    if kategorie != KONTEXT and kategorie not in KERN and kategorie not in ERWEITERT:
        raise ValueError(f"Unbekannte Kategorie {kategorie}")
    return f"⟦{kategorie}|{text}|{bemerkung}⟧" if bemerkung else f"⟦{kategorie}|{text}⟧"


def k(text) -> str:
    """Kontext-Eintrag (soll erhalten bleiben)."""
    return m(KONTEXT, text)


def ohne_auszeichnung(markup: str) -> str:
    return _AUSZEICHNUNG.sub(lambda mo: mo.group(2), markup)


# ----------------------------------------------------------------------
# Schriften
# ----------------------------------------------------------------------
_TRANSLIT = {"ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G", "ł": "l", "Ł": "L", "ż": "z",
             "Ż": "Z", "ś": "s", "Ś": "S", "č": "c", "Č": "C", "ć": "c", "Ć": "C", "ő": "ö", "Ő": "Ö",
             "ű": "ü", "Ű": "Ü", "ț": "t", "Ț": "T", "ș": "s", "Ș": "S", "ă": "a", "Ă": "A", "ę": "e",
             "ą": "a", "ń": "n", "ź": "z", "ř": "r", "Ř": "R", "ě": "e", "ů": "u", "ď": "d", "ť": "t",
             "ň": "n", "đ": "d", "Đ": "D", "ê": "ê", "→": "->", "ẞ": "SS", "ē": "e", "ā": "a", "ī": "i",
             "ū": "u", "Ā": "A", "š": "s", "Š": "S", "ž": "z", "Ž": "Z", "Œ": "OE", "œ": "oe", "Ÿ": "Y",
             "–": "-", "—": "-", "„": "\"", "“": "\"", "”": "\"", "‚": "'", "‘": "'", "’": "'", "…": "...",
             "•": "·", "€": "EUR", "™": "TM", "‰": "o/oo", "‹": "<", "›": ">", "ˆ": "^", "˜": "~", "ƒ": "f",
             "✓": "x"}

SCHRIFTFAMILIEN = {
    # Familie: (Dateien normal, Dateien fett, Base14 normal, Base14 fett)
    "sans": (["LiberationSans-Regular.ttf", "arial.ttf", "Arial.ttf"],
             ["LiberationSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"], "helv", "hebo"),
    "serif": (["LiberationSerif-Regular.ttf", "times.ttf", "Times New Roman.ttf"],
              ["LiberationSerif-Bold.ttf", "timesbd.ttf", "Times New Roman Bold.ttf"], "tiro", "tibo"),
    "mono": (["LiberationMono-Regular.ttf", "cour.ttf", "Courier New.ttf"],
             ["LiberationMono-Bold.ttf", "courbd.ttf", "Courier New Bold.ttf"], "cour", "cobo"),
    "carlito": (["Carlito-Regular.ttf", "calibri.ttf", "Calibri.ttf"],
                ["Carlito-Bold.ttf", "calibrib.ttf", "Calibri Bold.ttf"], "helv", "hebo"),
    "dejavu": (["DejaVuSans.ttf", "verdana.ttf", "Verdana.ttf"],
               ["DejaVuSans-Bold.ttf", "verdanab.ttf", "Verdana Bold.ttf"], "helv", "hebo"),
    "helv": ([], [], "helv", "hebo"),
    "tiro": ([], [], "tiro", "tibo"),
    "cour": ([], [], "cour", "cobo"),
}

_SCHRIFT_INDEX = None


def _schriftordner() -> list:
    ordner = ["/usr/share/fonts", "/usr/local/share/fonts", str(Path.home() / ".fonts"),
              str(Path.home() / ".local/share/fonts"), "/Library/Fonts", "/System/Library/Fonts/Supplemental",
              str(Path.home() / "Library/Fonts")]
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        ordner = [str(Path(windir) / "Fonts"),
                  str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts")] + ordner
    extra = os.environ.get("BENCHMARK_SCHRIFTEN")
    if extra:
        ordner = extra.split(os.pathsep) + ordner
    return ordner


def schriftdatei(namen) -> str | None:
    """Erste vorhandene Schriftdatei aus der Namensliste (Groß-/Kleinschreibung egal)."""
    global _SCHRIFT_INDEX
    if _SCHRIFT_INDEX is None:
        _SCHRIFT_INDEX = {}
        for basis in _schriftordner():
            if not basis or not os.path.isdir(basis):
                continue
            for wurzel, _, dateien in os.walk(basis):
                for d in dateien:
                    if d.lower().endswith(".ttf"):
                        _SCHRIFT_INDEX.setdefault(d.lower(), os.path.join(wurzel, d))
    for n in namen:
        p = _SCHRIFT_INDEX.get(n.lower())
        if p:
            return p
    return None


class Schrift:
    """Eine Schrift (Base14 oder eingebettete TrueType-Datei) mit Messung und Transliteration."""

    def __init__(self, base14: str, datei: str | None = None):
        self.datei = datei
        self.base14 = datei is None
        if self.base14:
            self.name = base14
            self.font = fitz.Font(base14)
        else:
            self.name = "F" + re.sub(r"[^A-Za-z0-9]", "", Path(datei).stem)[:20]
            self.font = fitz.Font(fontfile=datei)
        self.aufstieg = max(0.6, min(1.1, self.font.ascender))
        self.abstieg = max(0.1, min(0.4, -self.font.descender))
        self._ok: dict = {}

    def _zeichen_ok(self, c: str) -> bool:
        ok = self._ok.get(c)
        if ok is None:
            if self.base14:
                # PyMuPDF setzt Base14-Schriften mit Latin-1 (nicht dem vollen cp1252: €, „, –, š … fehlen)
                ok = c == "\n" or (0x20 <= ord(c) <= 0x7E) or (0xA0 <= ord(c) <= 0xFF)
            else:
                ok = c in " \n" or bool(self.font.has_glyph(ord(c)))
            self._ok[c] = ok
        return ok

    def darstellbar(self, text: str) -> str:
        """Text so umschreiben, dass jedes Zeichen in der Schrift vorhanden ist."""
        aus = []
        for c in text:
            if self._zeichen_ok(c):
                aus.append(c)
                continue
            ersatz = _TRANSLIT.get(c)
            if ersatz is None:
                zerlegt = unicodedata.normalize("NFKD", c)
                ersatz = "".join(z for z in zerlegt if not unicodedata.combining(z)) or "?"
            aus.append("".join(z if self._zeichen_ok(z) else "?" for z in ersatz))
        return "".join(aus)

    def breite(self, text: str, groesse: float) -> float:
        return self.font.text_length(text, fontsize=groesse)

    def setzen(self, page, x: float, y: float, text: str, groesse: float, farbe=(0, 0, 0),
               unsichtbar: bool = False):
        if not text:
            return
        if self.base14:
            page.insert_text((x, y), text, fontsize=groesse, fontname=self.name, color=farbe,
                             render_mode=3 if unsichtbar else 0)
        else:
            page.insert_text((x, y), text, fontsize=groesse, fontname=self.name, fontfile=self.datei,
                             color=farbe, render_mode=3 if unsichtbar else 0)


class Familie:
    """Schriftfamilie mit normalem und fettem Schnitt."""

    def __init__(self, name: str, ttf_erlaubt: bool = True):
        dateien, fett_dateien, b14, b14_fett = SCHRIFTFAMILIEN[name]
        datei = schriftdatei(dateien) if (ttf_erlaubt and dateien) else None
        fett_datei = schriftdatei(fett_dateien) if datei else None
        self.name = name
        self.normal = Schrift(b14, datei)
        self.fett = Schrift(b14_fett, fett_datei) if (fett_datei or not datei) else self.normal
        self.eingebettet = datei is not None


# ----------------------------------------------------------------------
# Stücke: Auszeichnung -> (Text, Eintrag)
# ----------------------------------------------------------------------
class _Stueck:
    __slots__ = ("text", "eintrag", "trennstrich")

    def __init__(self, text, eintrag=None, trennstrich=False):
        self.text = text
        self.eintrag = eintrag
        self.trennstrich = trennstrich


def _silben_grenzen(wort: str) -> list:
    """Mögliche Trennstellen (Index, vor dem getrennt wird) – einfache Heuristik: vor einem
    Konsonanten (ch/ck/sch als Einheit), dem ein Vokal folgt; beide Teile >= 3 Buchstaben."""
    vokale = set("aeiouyäöüáéíóúàèìòùâêîôûåøőűı")
    klein = wort.lower()
    stellen = []
    i = 3
    while i <= len(wort) - 3:
        c = klein[i]
        if c.isalpha() and c not in vokale and i + 1 < len(klein):
            einheit = 1
            if klein.startswith("sch", i):
                einheit = 3
            elif klein.startswith(("ch", "ck", "ph", "th"), i):
                einheit = 2
            if klein[i - 1] == "c" and c in "hk":
                i += 1
                continue
            if klein[i - 2:i] == "sc" and c == "h":
                i += 1
                continue
            folge = klein[i + einheit] if i + einheit < len(klein) else ""
            if folge in vokale and klein[i - 1].isalpha():
                stellen.append(i)
            i += einheit
            continue
        i += 1
    return stellen


# Merkmal "sonderzeichen_windows" (Vertrag 12.7): Windows-Schriften liefern in der Textebene NBSP statt
# Leerzeichen und einen SICHTBAREN weichen Trennstrich (U+00AD) bzw. geschützte Bindestriche (U+2011) statt "-".
# Der Generator schreibt diese Zeichen in ausgewählte Einträge, damit auch Linux-Läufe die Fehlerklasse messen.
SONDERZEICHEN_KATEGORIEN = {"namen", "telefon", "email", "iban", "vertrag", "plzort", "strasse", "kfz", "svnr",
                            "bic", "mandat", "steuerid", "kvnr", "ausweis"}
SONDERZEICHEN_BEMERKUNG = "Sonderzeichen (Windows)"


class Satz:
    """Ein PDF im Aufbau: Seiten, Wahrheitseinträge, Klartext je Seite, Merkmale."""

    def __init__(self, kennung: str):
        self.kennung = kennung
        self.doc = fitz.open()
        self.eintraege: list = []
        self.klartext: dict = {}          # Seite -> [Klartextstücke]
        self.merkmale: set = set()
        self.trennungen = 0
        self.seiten: list = []            # Seite-Objekte
        self.messmodus = False
        self.sonderzeichen: str | None = None   # Startwert der Sonderzeichen-Entscheidungen oder None (aus)

    def _sonderzeichen_setzen(self, text: str, kategorie: str, schrift: Schrift) -> str:
        """Leerzeichen -> NBSP, "-" -> sichtbarer U+00AD oder U+2011/U+2010 (je nach Schrift), wie es die
        Textebene von Windows-Schriften liefert. Die Entscheidung hängt nur von Startwert, Kategorie und Text ab
        (eigener Zufallsstrom: Messung und Setzen ergeben dasselbe, der übrige Korpus bleibt unverändert)."""
        if self.sonderzeichen is None or kategorie not in SONDERZEICHEN_KATEGORIEN or schrift.base14:
            return text
        rng = random.Random(f"{self.sonderzeichen}/{kategorie}/{text}")
        if rng.random() >= 0.7:
            return text
        striche = [z for z in ("­", "‑", "‐") if schrift._zeichen_ok(z)]
        aus = []
        for c in text:
            if c == " " and schrift._zeichen_ok(" ") and rng.random() < 0.8:
                aus.append(" ")
            elif c == "-" and striche and rng.random() < 0.8:
                aus.append(rng.choice(striche))
            else:
                aus.append(c)
        return "".join(aus)

    # -- Einträge ------------------------------------------------------
    def eintrag(self, text: str, kategorie: str, seite: int, kanal: str = "text", bemerkung: str = "",
                woerter=None) -> dict:
        erwartung = "behalten" if kategorie == KONTEXT else "schwaerzen"
        umfang = "erweitert" if kategorie in ERWEITERT else "kern"
        e = {"id": None, "text": text, "kategorie": kategorie, "seite": seite, "erwartung": erwartung,
             "umfang": umfang, "kanal": kanal, "bemerkung": bemerkung, "woerter": list(woerter or [])}
        self.eintraege.append(e)
        return e

    def klartext_merken(self, seite: int, text: str):
        if text and text.strip():
            self.klartext.setdefault(seite, []).append(text)

    def neue_seite(self, breite: float = A4_B, hoehe: float = A4_H) -> "Seite":
        page = self.doc.new_page(width=breite, height=hoehe)
        s = Seite(self, page, len(self.seiten) + 1)
        self.seiten.append(s)
        return s

    def zerlegen(self, markup: str, schrift: Schrift, seite_nr: int, zusatz: str = "") -> list:
        """Auszeichnung in Stücke zerlegen; legt (außer im Messmodus) die Einträge an."""
        stuecke, pos = [], 0
        for mo in _AUSZEICHNUNG.finditer(markup):
            if mo.start() > pos:
                stuecke.append(_Stueck(schrift.darstellbar(markup[pos:mo.start()])))
            kat, text, bem = mo.group(1), mo.group(2), mo.group(3) or ""
            trennen = "~trennen" in bem
            bem = "; ".join(t.strip() for t in bem.replace("~trennen", "").split(";") if t.strip())
            dargestellt = schrift.darstellbar(text)
            if dargestellt != text and kat != KONTEXT:
                bem = (bem + "; " if bem else "") + "transliteriert"
                if not self.messmodus:
                    self.merkmale.add("transliteration")
            sonder = self._sonderzeichen_setzen(dargestellt, kat, schrift)
            if sonder != dargestellt:
                dargestellt = sonder
                bem = (bem + "; " if bem else "") + SONDERZEICHEN_BEMERKUNG
                if not self.messmodus:
                    self.merkmale.add("sonderzeichen_windows")
            if zusatz:
                bem = (bem + "; " if bem else "") + zusatz
            if not self.messmodus:
                eintrag = self.eintrag(dargestellt, kat, seite_nr, bemerkung=bem)
            else:
                eintrag = {"bemerkung": bem, "messung": True}
            if trennen:
                eintrag["_trennen"] = True
            stuecke.append(_Stueck(dargestellt, eintrag))
            pos = mo.end()
        if pos < len(markup):
            stuecke.append(_Stueck(schrift.darstellbar(markup[pos:])))
        return [s for s in stuecke if s.text]

    def wahrheit(self, dokumentname: str, typ: str, seiten: int | None = None) -> dict:
        """Wahrheitsdaten nach BENCHMARK_SCHEMA.md (plus Wortrechtecke)."""
        eintraege = []
        stamm = Path(dokumentname).stem
        for i, e in enumerate(self.eintraege, 1):
            d = {schl: wert for schl, wert in e.items() if not schl.startswith("_")}
            d["id"] = f"{stamm}-{i:03d}"
            d["woerter"] = [[round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 1), w[4]]
                            for w in e["woerter"]]
            d.pop("messung", None)
            eintraege.append(d)
        return {"dokument": dokumentname, "typ": typ, "seiten": seiten if seiten is not None else len(self.doc),
                "merkmale": sorted(self.merkmale), "eintraege": eintraege}


class Seite:
    """Eine Seite mit Setzfunktionen. Koordinaten in pt, y nach unten, y = Grundlinie."""

    def __init__(self, satz: Satz, page, nr: int):
        self.satz = satz
        self._page = page
        self.nr = nr

    @property
    def page(self):
        """Die PyMuPDF-Seite. PyMuPDF macht ältere Seitenobjekte ungültig, sobald weitere Seiten
        angelegt werden – dann wird die Seite neu geladen."""
        p = self._page
        try:
            if p is not None and p.parent is not None:
                p.rect
                return p
        except Exception:
            pass
        self._page = self.satz.doc[self.nr - 1]
        return self._page

    @property
    def breite(self):
        return self.page.rect.width

    @property
    def hoehe(self):
        return self.page.rect.height

    # -- Grundfunktion: eine Zeile -------------------------------------
    def _stuecke_setzen(self, x: float, y: float, stuecke: list, schrift: Schrift, groesse: float,
                        farbe=(0, 0, 0), einzeln: bool = False, unsichtbar: bool = False) -> float:
        """Setzt Stücke in eine Zeile ab x (als ein Textbefehl oder Wort für Wort) und trägt die
        Wortrechtecke der Einträge ein. Liefert das x-Ende."""
        oben = y - schrift.aufstieg * groesse
        unten = y + schrift.abstieg * groesse
        lauf = x
        if not self.satz.messmodus and not einzeln:
            schrift.setzen(self.page, x, y, "".join(s.text for s in stuecke), groesse, farbe, unsichtbar)
        for s in stuecke:
            b = schrift.breite(s.text, groesse)
            if not self.satz.messmodus:
                if einzeln:
                    schrift.setzen(self.page, lauf, y, s.text, groesse, farbe, unsichtbar)
                if s.eintrag is not None and not s.trennstrich:
                    self._woerter_eintragen(s.eintrag, s.text, lauf, oben, unten, schrift, groesse)
                elif s.eintrag is not None and s.trennstrich and s.eintrag["woerter"]:
                    w = s.eintrag["woerter"][-1]
                    w[2] = lauf + b                      # Trennstrich gehört optisch zum Wortrest
                elif s.eintrag is None:
                    self.satz.klartext_merken(self.nr, s.text)
            lauf += b
        return lauf

    def _woerter_eintragen(self, eintrag, text, x, oben, unten, schrift, groesse):
        pos = x
        for teil in re.split(r"( +)", text):
            if not teil:
                continue
            b = schrift.breite(teil, groesse)
            if not teil.startswith(" "):
                eintrag["woerter"].append([pos, oben, pos + b, unten, teil])
            pos += b

    def text(self, x: float, y: float, markup: str, schrift: Schrift, groesse: float, farbe=(0, 0, 0),
             ausrichtung: str = "links", zusatz: str = "", unsichtbar: bool = False) -> float:
        """Eine Zeile setzen (ohne Umbruch). ausrichtung: links | rechts | mitte (x = Bezugspunkt)."""
        stuecke = self.satz.zerlegen(markup, schrift, self.nr, zusatz)
        breite = sum(schrift.breite(s.text, groesse) for s in stuecke)
        rand = self.breite - 3 * MM
        if ausrichtung == "links" and breite > 0 and x + breite > rand and rand - x > 20:
            # würde über den Seitenrand laufen (Text außerhalb der Seite ist nicht extrahierbar):
            # Schrift verkleinern
            groesse = max(4.5, groesse * (rand - x) / breite)
            breite = sum(schrift.breite(s.text, groesse) for s in stuecke)
        if ausrichtung == "rechts":
            x -= breite
        elif ausrichtung == "mitte":
            x -= breite / 2
        return self._stuecke_setzen(x, y, stuecke, schrift, groesse, farbe, unsichtbar=unsichtbar)

    # -- Absatz mit Umbruch und Silbentrennung --------------------------
    def _woerter(self, stuecke):
        """Stücke -> Wörter (Listen von Stücken ohne Leerzeichen); '\\n' erzwingt einen Umbruch."""
        woerter, aktuell = [], []
        for s in stuecke:
            for teil in re.split(r"( +|\n)", s.text):
                if not teil:
                    continue
                if teil == "\n":
                    if aktuell:
                        woerter.append(aktuell)
                        aktuell = []
                    woerter.append("\n")
                elif teil.startswith(" "):
                    if aktuell:
                        woerter.append(aktuell)
                        aktuell = []
                else:
                    aktuell.append(_Stueck(teil, s.eintrag))
        if aktuell:
            woerter.append(aktuell)
        return woerter

    @staticmethod
    def _wortbreite(wort, schrift, groesse):
        return sum(schrift.breite(s.text, groesse) for s in wort)

    def _trennen(self, wort, platz, schrift, groesse, nur_am_ende=False):
        """Wort an einer Silbengrenze (oder am Bindestrich) trennen, sodass der vordere Teil samt
        Trennstrich in `platz` passt; der hintere Teil behält mindestens drei Buchstaben.
        Liefert (vorne, hinten) oder None. Ziffern, E-Mail-Adressen und Schrägstriche werden nie
        getrennt."""
        text = "".join(s.text for s in wort)
        if any(c.isdigit() for c in text) or "@" in text or "/" in text or len(text) < 6:
            return None
        mo = re.fullmatch(r"([(„\"']?)([^\W\d_][^\W\d_'’]*(?:-[^\W\d_][^\W\d_'’]*)*)([.,;:!?)“\"']*)", text)
        if not mo:
            return None
        versatz, kern = len(mo.group(1)), mo.group(2)
        kandidaten = [(versatz + i + 1, False) for i, c in enumerate(kern)
                      if c == "-" and i >= 2 and len(kern) - i - 1 >= 3]
        if not kandidaten:
            kandidaten = [(versatz + i, True) for i in _silben_grenzen(kern)]
        beste = None
        for stelle, strich in kandidaten:
            if schrift.breite(text[:stelle] + ("-" if strich else ""), groesse) <= platz:
                beste = (stelle, strich)
        if beste is None:
            return None
        stelle, strich = beste
        vorne, hinten, pos = [], [], 0
        for s in wort:
            a, b = pos, pos + len(s.text)
            if b <= stelle:
                vorne.append(s)
            elif a >= stelle:
                hinten.append(s)
            else:
                vorne.append(_Stueck(s.text[:stelle - a], s.eintrag))
                hinten.append(_Stueck(s.text[stelle - a:], s.eintrag))
            pos = b
        if strich:
            vorne.append(_Stueck("-", vorne[-1].eintrag, trennstrich=True))
        # Bemerkung nur für Einträge, die wirklich über die Trennstelle laufen
        getrennt = {id(s.eintrag): s.eintrag for s in vorne if s.eintrag is not None and not s.trennstrich}
        for s in hinten:
            e = s.eintrag
            if e is not None and id(e) in getrennt:
                e["_getrennt"] = True
                bem = e.get("bemerkung", "")
                if "Silbentrennung" not in bem:
                    e["bemerkung"] = (bem + "; " if bem else "") + "Silbentrennung"
                if not e.get("messung"):
                    self.satz.merkmale.add("silbentrennung")
        return vorne, hinten

    def absatz(self, markup: str, x0: float, x1: float, y: float, schrift: Schrift, groesse: float,
               zeilenabstand: float = 1.2, blocksatz: bool = False, trennung: bool = True,
               farbe=(0, 0, 0), zusatz: str = "", erste_zeile_einzug: float = 0.0) -> float:
        """Absatz mit Zeilenumbruch setzen; y = Grundlinie der ersten Zeile. Liefert die Grundlinie
        der nächsten freien Zeile. Einträge mit der Bemerkung '~trennen' werden – wenn das Wort
        nicht am Zeilenanfang steht – am Zeilenende getrennt (Flattersatz endet dann früher)."""
        stuecke = self.satz.zerlegen(markup, schrift, self.nr, zusatz)
        woerter = self._woerter(stuecke)
        leer = schrift.breite(" ", groesse)
        zeilen, zeile, breite = [], [], 0.0
        einzug = erste_zeile_einzug
        warteschlange = list(woerter)
        while warteschlange:
            wort = warteschlange.pop(0)
            verfuegbar = (x1 - x0) - einzug
            if wort == "\n":
                zeilen.append((zeile, einzug, True))
                zeile, breite, einzug = [], 0.0, 0.0
                continue
            wb = self._wortbreite(wort, schrift, groesse)
            neu = wb if not zeile else breite + leer + wb
            erzwingen = trennung and bool(zeile) and any(
                s.eintrag is not None and s.eintrag.get("_trennen") and not s.eintrag.get("_getrennt")
                for s in wort)
            if neu <= verfuegbar and not erzwingen:
                zeile.append(wort)
                breite = neu
                continue
            geteilt = None
            if trennung and zeile:
                geteilt = self._trennen(wort, verfuegbar - breite - leer, schrift, groesse)
            if geteilt:
                vorne, hinten = geteilt
                zeile.append(vorne)
                zeilen.append((zeile, einzug, False))
                self.satz.trennungen += 1
                zeile, breite, einzug = [], 0.0, 0.0
                warteschlange.insert(0, hinten)
                continue
            if erzwingen and neu <= verfuegbar:
                zeile.append(wort)                       # Trennung nicht möglich, Wort passt aber
                breite = neu
                continue
            if zeile:
                zeilen.append((zeile, einzug, False))
                zeile, breite, einzug = [], 0.0, 0.0
                warteschlange.insert(0, wort)
                continue
            zeile, breite = [wort], wb                  # überlanges Wort: allein in die Zeile
        if zeile:
            zeilen.append((zeile, einzug, True))
        zeilenhoehe = groesse * zeilenabstand
        for zw, einzug, letzte in zeilen:
            if not zw:
                y += zeilenhoehe
                continue
            gesamt = sum(self._wortbreite(w, schrift, groesse) for w in zw)
            voll = gesamt + leer * (len(zw) - 1) >= 0.82 * (x1 - x0 - einzug)
            if blocksatz and not letzte and len(zw) > 1 and voll:
                luecke = ((x1 - x0 - einzug) - gesamt) / (len(zw) - 1)
                x = x0 + einzug
                for w in zw:
                    x = self._stuecke_setzen(x, y, w, schrift, groesse, farbe, einzeln=True) + luecke
            else:
                folge = []
                for i, w in enumerate(zw):
                    if i:
                        folge.append(_Stueck(" ", None))
                    folge.extend(w)
                self._stuecke_setzen(x0 + einzug, y, folge, schrift, groesse, farbe)
            y += zeilenhoehe
        return y

    def absatz_hoehe(self, markup, x0, x1, schrift, groesse, zeilenabstand=1.2, trennung=True,
                     erste_zeile_einzug=0.0) -> float:
        """Höhe eines Absatzes, ohne ihn zu setzen."""
        vorher = self.satz.messmodus
        self.satz.messmodus = True
        try:
            y_ende = self.absatz(markup, x0, x1, 0.0, schrift, groesse, zeilenabstand, False, trennung,
                                 erste_zeile_einzug=erste_zeile_einzug)
        finally:
            self.satz.messmodus = vorher
        return y_ende

    # -- Schlüssel/Wert, Tabellen, Linien ------------------------------
    def kv(self, x: float, y: float, schluessel: str, wert: str, tab_x: float, schrift: Schrift,
           groesse: float, fett: Schrift | None = None, fuellzeichen: str | None = None,
           zusatz: str = "") -> float:
        """Zeile 'Schlüssel  Wert' mit Tabulator (Wert ab tab_x), optional mit Füllpunkten."""
        ende = self.text(x, y, schluessel, fett or schrift, groesse)
        tab_x = max(tab_x, ende + 1.5 * schrift.breite(" ", groesse))   # Schlüssel länger als Tabulator
        if fuellzeichen:
            pb = schrift.breite(fuellzeichen, groesse)
            n = int(max(0.0, tab_x - ende - 2 * pb) / pb)
            if n > 0:
                self.text(ende + pb, y, fuellzeichen * n, schrift, groesse)
        return self.text(tab_x, y, wert, schrift, groesse, zusatz=zusatz)

    def linie(self, x0, y0, x1, y1, breite=0.5, farbe=(0, 0, 0)):
        if not self.satz.messmodus:
            self.page.draw_line((x0, y0), (x1, y1), color=farbe, width=breite)

    def rechteck(self, r, farbe=None, fuellung=None, breite=0.5):
        if not self.satz.messmodus:
            self.page.draw_rect(fitz.Rect(r), color=farbe, fill=fuellung, width=breite)

    def tabelle(self, x0: float, y: float, spalten: list, zeilen: list, schrift: Schrift, fett: Schrift,
                groesse: float, y_max: float, zeilenabstand: float = 1.15, polster: float = 2.0,
                gitter: bool = True, kopf_fuellung=(0.88, 0.88, 0.88), zebra: bool = False,
                kopf: bool = True, zusatz_je_spalte: dict | None = None) -> tuple:
        """Tabelle mit Kopfzeile. spalten: [(Kopf-Auszeichnung, Breite, Ausrichtung)];
        zeilen: [[Zell-Auszeichnung, …]]. Setzt Zeilen bis y_max und liefert
        (y unter der Tabelle, Index der ersten nicht gesetzten Zeile)."""
        zh = groesse * zeilenabstand
        breite_ges = sum(b for _, b, _ in spalten)

        def zeile_hoehe(zellen, s):
            hoehe = 1
            for (kopf_m, b, _), zelle in zip(spalten, zellen):
                h = self.absatz_hoehe(zelle, 0, b - 2 * polster, s, groesse, zeilenabstand, trennung=False)
                hoehe = max(hoehe, round(h / zh))
            return hoehe * zh + 2 * polster

        def zeile_setzen(zellen, s, y_oben, h, fuellung):
            if fuellung is not None:
                self.rechteck((x0, y_oben, x0 + breite_ges, y_oben + h), fuellung=fuellung, farbe=None)
            x = x0
            for i, ((_, b, ausr), zelle) in enumerate(zip(spalten, zellen)):
                grund = y_oben + polster + s.aufstieg * groesse
                zusatz = (zusatz_je_spalte or {}).get(i, "")
                if ausr == "rechts":
                    self.text(x + b - polster, grund, zelle, s, groesse, ausrichtung="rechts", zusatz=zusatz)
                else:
                    self.absatz(zelle, x + polster, x + b - polster, grund, s, groesse, zeilenabstand,
                                trennung=False, zusatz=zusatz)
                if gitter:
                    self.linie(x, y_oben, x, y_oben + h, 0.4)
                x += b
            if gitter:
                self.linie(x, y_oben, x, y_oben + h, 0.4)
                self.linie(x0, y_oben + h, x0 + breite_ges, y_oben + h, 0.4)

        if kopf:
            koepfe = [kp for kp, _, _ in spalten]
            h = zeile_hoehe(koepfe, fett)
            if gitter:
                self.linie(x0, y, x0 + breite_ges, y, 0.4)
            zeile_setzen(koepfe, fett, y, h, kopf_fuellung)
            y += h
        for i, zellen in enumerate(zeilen):
            h = zeile_hoehe(zellen, schrift)
            if y + h > y_max:
                return y, i
            zeile_setzen(zellen, schrift, y, h, (0.95, 0.95, 0.95) if (zebra and i % 2) else None)
            y += h
        return y, len(zeilen)

    def unterschrift(self, x: float, y: float, rng, breite: float = 110.0, hoehe: float = 22.0):
        """Handschriftlich wirkende Unterschrift als Vektorpfad (enthält keinen Text)."""
        if self.satz.messmodus:
            return
        form = self.page.new_shape()
        p = fitz.Point(x, y)
        for _ in range(rng.randint(3, 5)):
            q = fitz.Point(p.x + breite / 4 * rng.uniform(0.6, 1.2), y - hoehe * rng.uniform(-0.3, 0.6))
            c1 = fitz.Point(p.x + rng.uniform(5, 20), y - hoehe * rng.uniform(0.2, 1.0))
            c2 = fitz.Point(q.x - rng.uniform(5, 20), y + hoehe * rng.uniform(-0.2, 0.5))
            form.draw_bezier(p, c1, c2, q)
            p = q
        form.finish(color=(0.05, 0.1, 0.45), width=1.1, closePath=False)
        form.commit()
