"""Schwärzung: Funde wirklich aus dem PDF entfernen (Text und Bildpixel), Nebenkanäle leeren,
neutral benannte Ausgabe schreiben und das Ergebnis selbst kontrollieren.

Öffentliche Schnittstelle (siehe CONTRACT.md): schwaerze_pdf(...).

Arbeitsweise je Seite:
  * Textebene: Zeichen mit Koordinaten (get_text("rawdict")) -> normalisierter Suchtext (Leerraum,
    Silbentrennung) -> Ganzwort-Treffer -> Rechtecke aus den echten Glyphen-Koordinaten. Damit
    hängt nichts an den (in MuPDF 1.28 bei Silbentrennung verschobenen) search_for-Rechtecken,
    und Wortteile ("Berg" in "Heidelberg") werden nicht getroffen.
  * Scan-Seiten ("seite") und Bilder auf Textseiten ("bilder"): Wortfolgen-Vergleich über die
    OCR-Wortliste (aus ocr_cache der Analyse oder vom OcrDienst), Rechtecke = Wortboxen + Rand.
  * Rechtecke auf Textseiten reichen von 0,70 x Schriftgröße über bis 0,02 x Schriftgröße unter die
    Grundlinie: MuPDF entfernt jede Glyphe, deren Schriftbox das Rechteck nennenswert schneidet –
    so verschwinden alle Glyphen des Treffers, Nachbarzeilen bleiben auch bei Zeilenabstand 1,0 heil.
"""

import datetime
import os
import re
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from .ocr import OcrDienst, bild_bereiche, ocr_noetig

FUELLFARBE = (0.92, 0.92, 0.92)
TEXTFARBE = (0, 0, 0)
PLATZHALTER_MIN_PT = 4.0      # darunter zeichnet MuPDF den Platzhalter nicht
PLATZHALTER_MAX_PT = 9.0
OBERKANTE = 0.70              # Rechteck-Oberkante: Anteil der Schriftgröße über der Grundlinie
UNTERKANTE = 0.02             # Rechteck-Unterkante: Anteil der Schriftgröße unter der Grundlinie
OCR_RAND = 1.5                # pt Rand um OCR-Wortboxen (Pixel am Glyphenrand mit erwischen)
OCR_DPI = 300
STAPEL_SCANSEITEN = 10        # nach so vielen geschwärzten Scan-Seiten Zwischenstand speichern
SATZZEICHEN = ".,;:!?()[]{}\"'„“‚‘«»/\\|<>*"
ABGEBROCHEN = "Abgebrochen"
WARNUNG_KEIN_TREFFER = ("Kein angehakter Fund konnte im Dokument lokalisiert werden – "
                        "keine Ausgabedatei erzeugt.")

# Schlüsselwörter, die auf OCR-Seiten einen Fund der Kategorie erwarten lassen (M-50)
_SCHLUESSELWOERTER = [
    ("iban", "IBAN", re.compile(r"\bIBAN\b", re.IGNORECASE)),
    ("vertrag", "Kunden-/Versicherungsschein-Nr.",
     re.compile(r"Kunden[\-\s]?[NH]r|Versicherungsschein|Vertrags[\-\s]?[NH]r|Policen?[\-\s]?[NH]r", re.IGNORECASE)),
    ("geburt", "Geburtsdatum", re.compile(r"Geburtsdatum|\bgeb\.|geboren", re.IGNORECASE)),
    ("steuerid", "Steuer-ID", re.compile(r"Steuer[\-\s]?ID|Identifikationsnummer", re.IGNORECASE)),
    ("svnr", "Sozialversicherungsnummer",
     re.compile(r"Sozialversicherungsnummer|SV[\-\s]?Nr|Rentenversicherungsnummer", re.IGNORECASE)),
]
_NAMENSMUSTER = re.compile(r"^anonym_(\d+)(?:_PRUEFEN)?\.pdf$", re.IGNORECASE)
_MARKIERUNGS_MUSTER = re.compile(rb"/(?:ActualText|Alt)\s*(?:\((?:[^()\\]|\\.)*\)|<[0-9A-Fa-f\s]*>)")


class _Abgebrochen(Exception):
    """Der Nutzer hat den Lauf abgebrochen."""


# ----------------------------------------------------------------------
# Text-Normalisierung
# ----------------------------------------------------------------------
def _norm_fund(text: str) -> str:
    """Fundtext so normalisieren wie den Seitentext: Leerraum -> ein Leerzeichen, weiche Trennstriche
    weg, Trennstrich vor Zeilenumbruch + Kleinbuchstabe weg ("Muster-\\nmann" -> "Mustermann")."""
    text = text.replace("­", "")
    text = re.sub(r"(?<=[^\W\d_])[-‐‑][ \t]*\n\s*(?=[a-zäöüß])", "", text)
    text = re.sub(r"(?<=[^\W\d_])[-‐‑][ \t]*\n\s*(?=\w)", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def _kern(wort: str) -> str:
    return wort.strip(SATZZEICHEN + " ")


def _anfangs_varianten(text: str) -> list:
    """Kürzere Anfänge eines mehrteiligen Fundtexts – für Funde, die die Analyse mitten im Wort
    abgeschnitten hat ("KH-2025-004711 vom 12.03.2"): dann wird wenigstens der Anfang gefunden.
    Es bleiben mindestens zwei Wörter oder eine Kennung mit Ziffern (>= 5 Zeichen)."""
    tokens = _norm_fund(text).split()
    varianten = []
    for n in range(len(tokens) - 1, 0, -1):
        rest = tokens[:n]
        if len(rest) >= 2 or (len(rest[0]) >= 5 and any(z.isdigit() for z in rest[0])):
            varianten.append(" ".join(rest))
    return varianten


class _Zeichenkette:
    """Alle Zeichen einer Seite mit Koordinaten plus normalisierter Suchtext mit Rückabbildung."""

    def __init__(self, seite, textpage=None):
        self.zeichen: list = []      # (c, Rect, grundlinie_y, schriftgroesse, zeile_id, horizontal)
        self.zeilen: dict = {}       # zeile_id -> [Zeichenindex, ...]
        self.verbunden: dict = {}    # Zeichenindex -> Index eines entfallenen Trennstrichs dahinter
        self.text = ""
        self.abbildung: list = []    # Index im Suchtext -> Zeichenindex (oder -1)
        self._aufbauen(seite, textpage)

    def _aufbauen(self, seite, textpage):
        roh: list = []   # (Zeichen, Zeichenindex oder -1 für Trenner)
        try:
            rd = seite.get_text("rawdict", textpage=textpage) if textpage is not None \
                else seite.get_text("rawdict")
        except Exception:
            rd = {"blocks": []}
        zeile_id = 0
        for block in rd.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for zeile in block.get("lines", []):
                richtung = zeile.get("dir", (1, 0))
                horizontal = abs(richtung[1]) < 0.2 and zeile.get("wmode", 0) == 0
                for span in zeile.get("spans", []):
                    groesse = float(span.get("size", 0) or 0)
                    for ch in span.get("chars", []):
                        idx = len(self.zeichen)
                        self.zeichen.append((ch["c"], fitz.Rect(ch["bbox"]), float(ch["origin"][1]),
                                             groesse, zeile_id, horizontal))
                        self.zeilen.setdefault(zeile_id, []).append(idx)
                        roh.append((ch["c"], idx))
                roh.append(("\n", -1))
                zeile_id += 1
        text: list = []
        abb: list = []
        i, n = 0, len(roh)
        while i < n:
            c, idx = roh[i]
            if c == "­":                       # weicher Trennstrich: unsichtbar, an Vorgänger hängen
                if text and not text[-1].isspace() and abb[-1] >= 0:
                    self.verbunden[abb[-1]] = idx
                i += 1
                continue
            if c in "-‐‑" and idx >= 0 and text and text[-1].isalpha():
                j = i + 1
                while j < n and roh[j][0] in " \t":
                    j += 1
                if j < n and roh[j][0] == "\n":
                    k = j + 1
                    while k < n and roh[k][0] in " \t":
                        k += 1
                    if k < n and roh[k][0].isalpha():
                        if roh[k][0].islower():        # Silbentrennung: Trennstrich + Umbruch entfallen
                            self.verbunden[abb[-1]] = idx
                            i = k
                            continue
                        text.append("-")               # Kompositum ("Klein-/Hoffmann"): nur Umbruch weg
                        abb.append(idx)
                        i = k
                        continue
            if c.isspace():
                if text and not text[-1].isspace():
                    text.append(" ")
                    abb.append(idx)
                i += 1
                continue
            text.append(c)
            abb.append(idx)
            i += 1
        while text and text[-1].isspace():
            text.pop()
            abb.pop()
        self.text = "".join(text)
        self.abbildung = abb

    def suche(self, fund_text: str) -> list:
        """Ganzwort-Treffer des Fundtexts. Rückgabe: Liste von Zeichenindex-Mengen (eine je Treffer).
        Groß-/Kleinschreibung muss stimmen; nur VERSALIEN im Dokument dürfen abweichen."""
        nadel = _norm_fund(fund_text)
        if not nadel:
            return []
        alphabetisch = nadel.replace(" ", "").replace("-", "").isalpha()
        varianten = [nadel]
        if nadel.upper() != nadel:
            varianten.append(nadel.upper())
        treffer = []
        for v in varianten:
            start = 0
            while True:
                a = self.text.find(v, start)
                if a < 0:
                    break
                start = a + 1
                b = a + len(v)
                if a > 0 and self.text[a - 1].isalnum():
                    continue
                if b < len(self.text) and self.text[b].isalnum():
                    # Genitiv-s bei Namen mitnehmen ("Mustermanns Vertrag")
                    if alphabetisch and self.text[b] == "s" and (
                            b + 1 == len(self.text) or not self.text[b + 1].isalnum()):
                        b += 1
                    else:
                        continue
                indizes = {self.abbildung[i] for i in range(a, b) if self.abbildung[i] >= 0}
                for idx in list(indizes):
                    if idx in self.verbunden:
                        indizes.add(self.verbunden[idx])
                if indizes:
                    treffer.append(indizes)
        return treffer

    def rechtecke(self, indizes, bildbereiche) -> list:
        """Rechtecke eines Treffers je Zeile: [(Rechteck, volle Zeichenbox, Schriftgröße, Grundlinie), ...]."""
        nach_zeile: dict = {}
        for idx in indizes:
            z = self.zeichen[idx]
            nach_zeile.setdefault(z[4], []).append(z)
        ergebnis = []
        for zeile_id, zs in sorted(nach_zeile.items()):
            box = fitz.Rect(zs[0][1])
            for z in zs[1:]:
                box |= z[1]
            if box.is_empty or box.is_infinite:
                continue
            groesse = max(z[3] for z in zs)
            grundlinie = max(z[2] for z in zs)
            if all(z[5] for z in zs) and groesse > 0:
                oben = min(z[2] - OBERKANTE * z[3] for z in zs if z[3] > 0)
                unten = max(z[2] + UNTERKANTE * z[3] for z in zs if z[3] > 0)
                r = fitz.Rect(box.x0, max(box.y0, oben), box.x1, min(box.y1, unten))
                if r.is_empty or r.height < 0.3 * box.height:
                    r = fitz.Rect(box)
            else:
                r = fitz.Rect(box)
            if any(r.intersects(b) for b in bildbereiche):
                # Text über einem Bild (z. B. unsichtbare Textebene eines Kopierers): Pixel komplett löschen
                r = fitz.Rect(box.x0 - 1, box.y0 - 1, box.x1 + 1, box.y1 + 1)
            ergebnis.append((r, fitz.Rect(box), groesse, grundlinie))
        return ergebnis

    def freiraum(self, rect, indizes):
        """(x1 des vorigen, x0 des nächsten Buchstabens/Ziffer) in der Zeile des Treffers – so weit
        darf das Rechteck für den Platzhalter wachsen; Satzzeichen dazwischen entfallen. None = frei."""
        zeilen = {self.zeichen[i][4] for i in indizes}
        links, rechts = [], []
        for zid in zeilen:
            for idx in self.zeilen.get(zid, []):
                if idx in indizes:
                    continue
                z = self.zeichen[idx]
                if not z[0].isalnum():
                    continue
                if z[1].x0 >= rect.x1 - 0.5:
                    rechts.append(z[1].x0)
                elif z[1].x1 <= rect.x0 + 0.5:
                    links.append(z[1].x1)
        return (max(links) if links else None), (min(rechts) if rechts else None)


# ----------------------------------------------------------------------
# Wortlisten-Vergleich (OCR-Seiten)
# ----------------------------------------------------------------------
def _passt(wort: str, token: str, lage: str) -> bool:
    """Prüft, ob `token` im (satzzeichen-bereinigten) OCR-Wort steht.
    lage: 'ganz' (gleich), 'ende' (Token am Wortende), 'anfang' (Token am Wortanfang),
    'innen' (irgendwo, aber an Wortgrenzen). Versalien im Dokument dürfen abweichen."""
    kandidaten = [token]
    if wort.isupper() and token.upper() != token:
        kandidaten.append(token.upper())
    for t in kandidaten:
        if wort == t:
            return True
        if lage == "ganz" or not t:
            continue
        start = 0
        while True:
            i = wort.find(t, start)
            if i < 0:
                break
            start = i + 1
            ende = i + len(t)
            vor_ok = i == 0 or not wort[i - 1].isalnum()
            nach_ok = ende == len(wort) or not wort[ende].isalnum() or (
                t.isalpha() and wort[ende] == "s" and ende + 1 == len(wort))   # Genitiv-s
            if lage == "ende" and vor_ok and ende == len(wort):
                return True
            if lage == "anfang" and i == 0 and nach_ok:
                return True
            if lage == "innen" and vor_ok and nach_ok:
                return True
    return False


def _treffer_in_woertern(woerter, fund_text: str) -> list:
    """Wortfolgen-Vergleich: Rückgabe Liste von Treffern, jeder Treffer = Liste von Wort-Rechtecken.
    Satzzeichen an Wortgrenzen werden ignoriert, Trennstriche am Zeilenende überbrückt."""
    tokens = [_kern(t) for t in _norm_fund(fund_text).split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return []
    n = len(woerter)
    treffer = []
    for i in range(n):
        j, rects, ok = i, [], True
        for k, token in enumerate(tokens):
            if j >= n:
                ok = False
                break
            if len(tokens) == 1:
                lage = "innen"
            elif k == 0:
                lage = "ende"
            elif k == len(tokens) - 1:
                lage = "anfang"
            else:
                lage = "ganz"
            w = woerter[j]
            if _passt(_kern(w[4]), token, lage):
                rects.append(fitz.Rect(w[:4]))
                j += 1
                continue
            if j + 1 < n and w[4].rstrip(SATZZEICHEN + " ").endswith("-"):
                kombi = _kern(w[4].rstrip(SATZZEICHEN + " ")[:-1] + woerter[j + 1][4])
                if _passt(kombi, token, lage):
                    rects.append(fitz.Rect(w[:4]))
                    rects.append(fitz.Rect(woerter[j + 1][:4]))
                    j += 2
                    continue
            ok = False
            break
        if ok and rects:
            treffer.append(rects)
    return treffer


def _zeilen_zusammenfassen(rects) -> list:
    """Fasst Wort-Rechtecke derselben Zeile zu einem Rechteck zusammen (ein Platzhalter je Zeile)."""
    rects = sorted((fitz.Rect(r) for r in rects), key=lambda r: (round(r.y0), r.x0))
    ergebnis: list = []
    for r in rects:
        if ergebnis:
            letzt = ergebnis[-1]
            ueberlappung = min(letzt.y1, r.y1) - max(letzt.y0, r.y0)
            hoehe = min(letzt.height, r.height) or 1.0
            if ueberlappung > 0.5 * hoehe and r.x0 - letzt.x1 < 1.5 * hoehe:
                ergebnis[-1] = letzt | r
                continue
        ergebnis.append(fitz.Rect(r))
    return ergebnis


def _wort_freiraum(woerter, rect):
    """(x1 des vorigen, x0 des nächsten OCR-Worts) auf gleicher Höhe wie das Rechteck (None = frei)."""
    links, rechts = [], []
    for w in woerter:
        r = fitz.Rect(w[:4])
        if not _kern(w[4]) or min(r.y1, rect.y1) - max(r.y0, rect.y0) <= 0.4 * min(r.height, rect.height):
            continue
        if r.x0 >= rect.x1 - 0.5:
            rechts.append(r.x0)
        elif r.x1 <= rect.x0 + 0.5:
            links.append(r.x1)
    return (max(links) if links else None), (min(rechts) if rechts else None)


# ----------------------------------------------------------------------
# Platzhalter
# ----------------------------------------------------------------------
# Die Platzhalter werden NICHT über den Text-Parameter von add_redact_annot gezeichnet: MuPDF lässt
# diesen Text unter ~7 pt Rechteckhöhe ganz weg, bricht ihn um ("[PERSO/N A]") oder setzt ihn je
# Rechteck erneut. Stattdessen wird nach apply_redactions mit insert_text gezeichnet – passend zur
# Rechteckbreite, auf der Grundlinie des ersetzten Texts, ein Platzhalter je Treffer.
def _platzhalter_schrift(rect, text, max_pt) -> float:
    """Größte Schrift (pt), mit der der Platzhalter in das Rechteck passt (Versalhöhe ~0,72 x pt)."""
    breite_je_pt = fitz.get_text_length(text, fontname="helv", fontsize=1) or 1.0
    return min(max_pt, rect.height / 0.80, (rect.width - 1.0) / breite_je_pt)


def _platzhalter_kurz(text: str):
    """Kurzform für enge Lücken: "[PERSON B]" -> "[P B]", "[FAMILIE A]" -> "[F A]"; sonst None."""
    m = re.fullmatch(r"\[([A-ZÄÖÜ])[A-ZÄÖÜ]+[ \-]([A-Z0-9]{1,2})\]", text)
    return f"[{m.group(1)} {m.group(2)}]" if m else None


def _platzhalter_planen(rect, text, max_pt, freiraum, seitenrect):
    """Liefert (Rechteck, Platzhaltertext, Schriftgröße oder None). Passt der Platzhalter nicht hinein,
    wird das Rechteck in der Zeile bis zu den Nachbarbuchstaben erweitert (Satzzeichen dazwischen
    entfallen); reicht auch das nicht, kommt die Kurzform ("[P B]")."""
    max_pt = max(PLATZHALTER_MIN_PT, min(max_pt, PLATZHALTER_MAX_PT))
    fs = _platzhalter_schrift(rect, text, max_pt)
    if fs >= PLATZHALTER_MIN_PT:
        return rect, text, fs
    links, rechts = freiraum if freiraum else (None, None)
    links = (links + 1.0) if links is not None else max(seitenrect.x0 + 2, rect.x0 - 6)
    rechts = (rechts - 1.0) if rechts is not None else seitenrect.x1 - 2
    for variante in (text, _platzhalter_kurz(text)):
        if not variante:
            continue
        breite_je_pt = fitz.get_text_length(variante, fontname="helv", fontsize=1) or 1.0
        benoetigt = PLATZHALTER_MIN_PT * breite_je_pt + 1.5
        r = fitz.Rect(rect)
        if r.width < benoetigt:                       # erst nach rechts, dann nach links wachsen
            r.x1 = max(r.x1, min(rechts, r.x0 + benoetigt))
        if r.width < benoetigt:
            r.x0 = min(r.x0, max(links, r.x1 - benoetigt))
        fs = _platzhalter_schrift(r, variante, max_pt)
        if fs >= PLATZHALTER_MIN_PT:
            return r, variante, fs
    return rect, text, None


def _platzhalter_zeichnen(seite, rect, text, fs, grundlinie):
    """Schreibt den Platzhalter zentriert in das (bereits grau gefüllte) Rechteck."""
    breite = fitz.get_text_length(text, fontname="helv", fontsize=fs)
    x = rect.x0 + max(0.5, (rect.width - breite) / 2)
    if grundlinie is None or not (rect.y0 < grundlinie <= rect.y1 + 0.5):
        grundlinie = rect.y1 - 0.22 * rect.height
    grundlinie = min(grundlinie, rect.y1 - 0.02 * fs)
    try:
        return seite.insert_text(fitz.Point(x, grundlinie), text, fontsize=fs, fontname="helv",
                                 color=TEXTFARBE) > 0
    except Exception:
        return False


# ----------------------------------------------------------------------
# Nebenkanäle
# ----------------------------------------------------------------------
def _schluessel_vorhanden(doc, xref, schluessel) -> bool:
    try:
        return doc.xref_get_key(xref, schluessel)[0] != "null"
    except Exception:
        return False


def _schluessel_loeschen(doc, xref, schluessel) -> bool:
    if not _schluessel_vorhanden(doc, xref, schluessel):
        return False
    try:
        doc.xref_set_key(xref, schluessel, "null")
        return True
    except Exception:
        return False


def _nebenkanaele_zaehlen(doc) -> dict:
    z = {"formularfelder": 0, "anmerkungen": 0, "links": 0, "lesezeichen": 0, "anhaenge": 0,
         "miniaturbilder": 0, "ebenen": 0, "xfa": False}
    for seite in doc:
        try:
            z["formularfelder"] += sum(1 for _ in seite.widgets())
            z["anmerkungen"] += sum(1 for _ in seite.annots())
            z["links"] += len(seite.get_links())
            z["miniaturbilder"] += int(_schluessel_vorhanden(doc, seite.xref, "Thumb"))
        except Exception:
            pass
    try:
        z["lesezeichen"] = len(doc.get_toc())
        z["anhaenge"] = doc.embfile_count()
        z["ebenen"] = len(doc.get_ocgs())
        z["xfa"] = _schluessel_vorhanden(doc, doc.pdf_catalog(), "AcroForm/XFA")
    except Exception:
        pass
    return z


def _markierungen_bereinigen(doc):
    """Entfernt /ActualText und /Alt aus den Inhaltsströmen (Seiten und Form-XObjects): beides kann
    Klartext tragen und lenkt die Textextraktion weg von den echten Glyphen."""
    for seite in doc:
        xrefs = list(seite.get_contents())
        try:
            xrefs += [x[0] for x in seite.get_xobjects()]
        except Exception:
            pass
        for xref in xrefs:
            try:
                strom = doc.xref_stream(xref)
            except Exception:
                continue
            if strom and b"BDC" in strom and _MARKIERUNGS_MUSTER.search(strom):
                doc.update_stream(xref, _MARKIERUNGS_MUSTER.sub(b"", strom))


def _wortmenge(seite) -> set:
    return {(w[4], tuple(round(v, 1) for v in w[:4])) for w in seite.get_text("words")}


def _bildmenge(seite) -> set:
    try:
        return {tuple(round(v, 1) for v in i["bbox"]) for i in seite.get_image_info()}
    except Exception:
        return set()


def _ebenen_behandeln(doc):
    """Optional Content (Ebenen): ausgeblendete Inhalte werden ermittelt (Differenz der Wörter und
    Bilder vor/nach dem Entfernen der Ebenensteuerung) und als Rechtecke zum Schwärzen zurückgegeben.
    Die Ebenensteuerung selbst wird entfernt, damit nichts mehr versteckt sein kann.

    Rückgabe: (Dokument, {Seitenindex: [Rect, ...]}). Das Dokument wird dafür einmal aus dem Speicher
    neu geöffnet, weil MuPDF den Sichtbarkeitszustand der Ebenen beim Öffnen festlegt.
    """
    try:
        if not doc.get_ocgs():
            return doc, {}
    except Exception:
        return doc, {}
    vorher = {}
    for nr in range(len(doc)):
        seite = doc[nr]
        if seite.rotation:
            seite.remove_rotation()
        vorher[nr] = (_wortmenge(seite), _bildmenge(seite))
    _schluessel_loeschen(doc, doc.pdf_catalog(), "OCProperties")
    puffer = doc.tobytes(garbage=0)
    doc.close()
    doc = fitz.open("pdf", puffer)
    versteckt: dict = {}
    for nr in range(len(doc)):
        seite = doc[nr]
        woerter, bilder = _wortmenge(seite), _bildmenge(seite)
        neu = [r for (t, r) in woerter if (t, r) not in vorher[nr][0]]
        neu += [r for r in bilder if r not in vorher[nr][1]]
        if neu:
            versteckt[nr] = [fitz.Rect(r) + (-1, -1, 1, 1) for r in neu]
    return doc, versteckt


def _nebenkanaele_entfernen(doc, zaehler: dict):
    """Anmerkungen, Links, Lesezeichen, Anhänge, Metadaten (Info + XMP), Miniaturbilder und
    weitere Katalog-Einträge entfernen, die Klartext tragen können."""
    for seite in doc:
        try:
            for annot in list(seite.annots()):
                seite.delete_annot(annot)
            for link in seite.get_links():
                seite.delete_link(link)
            for schluessel in ("Thumb", "PieceInfo", "AA", "Metadata"):
                _schluessel_loeschen(doc, seite.xref, schluessel)
        except Exception:
            pass
    try:
        if doc.get_toc():
            doc.set_toc([])
    except Exception:
        pass
    try:
        for name in list(doc.embfile_names()):
            doc.embfile_del(name)
    except Exception:
        pass
    try:
        doc.set_metadata({})
        doc.del_xml_metadata()
    except Exception:
        pass
    katalog = doc.pdf_catalog()
    for schluessel in ("AcroForm", "Names", "Dests", "PieceInfo", "OpenAction", "AA",
                       "StructTreeRoot", "MarkInfo", "Outlines", "Metadata", "OCProperties",
                       "Collection", "Requirements"):
        _schluessel_loeschen(doc, katalog, schluessel)


def _nebenkanal_hinweis(zaehler: dict) -> str:
    teile = []
    for schluessel, wort in (("formularfelder", "Formularfeld(er)"), ("anmerkungen", "Anmerkung(en)"),
                             ("links", "Link(s)"), ("lesezeichen", "Lesezeichen"),
                             ("anhaenge", "eingebettete Datei(en)"), ("miniaturbilder", "Miniaturbild(er)"),
                             ("ebenen", "Ebene(n)")):
        if zaehler.get(schluessel):
            teile.append(f"{zaehler[schluessel]} {wort}")
    teile.append("Metadaten/XMP")
    return "Entfernt bzw. eingebrannt: " + ", ".join(teile) + "."


# ----------------------------------------------------------------------
# Ausgabedateien
# ----------------------------------------------------------------------
def _freier_ausgabename(ziel: Path, pruefen: bool) -> Path:
    """Nächste freie laufende Nummer im Zielordner – bestehende Ausgaben werden nie überschrieben."""
    nummern = []
    for p in ziel.glob("anonym_*.pdf"):
        m = _NAMENSMUSTER.match(p.name)
        if m:
            nummern.append(int(m.group(1)))
    nummer = max(nummern, default=0) + 1
    while True:
        basis = ziel / f"anonym_{nummer:02d}.pdf"
        pruef = ziel / f"anonym_{nummer:02d}_PRUEFEN.pdf"
        if not basis.exists() and not pruef.exists():
            return pruef if pruefen else basis
        nummer += 1


def _zuordnung_anhaengen(ziel: Path, ausgabe: Path, original: Path):
    zeit = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(ziel / "_zuordnung.txt", "a", encoding="utf-8") as f:
        f.write(f"{ausgabe.name}  <-  {original.name}  ({zeit})\n")


def _aufraeumen(pfade):
    for p in pfade:
        try:
            Path(p).unlink()
        except OSError:
            pass


# ----------------------------------------------------------------------
# Lauf-Zustand
# ----------------------------------------------------------------------
class _Lauf:
    def __init__(self, pdf_pfad, funde, melde, fortschritt, abbruch, ocr, ocr_cache, ziel):
        self.pdf_pfad = pdf_pfad
        self.funde = funde
        self.melde = melde or (lambda t: None)
        self.fortschritt = fortschritt
        self.abbruch = abbruch
        self.ocr = ocr
        self.ocr_cache = ocr_cache or {}
        self.ziel = ziel
        self.doc = None
        self.geoeffnet_von = None            # Pfad, aus dem self.doc gerade geladen ist (Zwischenstand)
        self.tmp_pfade: list = []
        self.rects_je_seite: dict = {}       # Seitenindex -> angewendete Rechtecke (für die Kontrolle)
        self.ocr_modus: dict = {}            # Seitenindex -> "seite" | "bilder"
        self.bildbereiche: dict = {}         # Seitenindex -> Bildbereiche (für Kontroll-OCR "bilder")
        self.kategorien_je_seite: dict = {}  # Seitenindex -> Kategorien mit Treffer
        self.gefunden: set = set()           # Fundtexte mit mindestens einem Treffer
        self.treffer = 0
        self.ohne_platzhalter = 0
        self.abgekuerzt: dict = {}           # Kurzform -> voller Platzhalter (enge Lücken)
        self.anfangstreffer: dict = {}       # Fundtext -> gefundener Anfang (abgeschnittene Fundtexte)
        self.winkel_je_seite: dict = {}      # Seitenindex -> erkannte Scan-Ausrichtung (für die Kontroll-OCR)
        self.kollateral: list = []
        self.grafik_seiten: list = []
        self.bild_seiten: list = []
        self.scan_seiten_seit_speichern = 0
        self.warnungen: list = []
        self.hinweise: list = []
        self._ocr_warnungen: set = set()

    def abbruch_pruefen(self):
        if self.abbruch is not None and self.abbruch.is_set():
            raise _Abgebrochen()

    def ocr_warnung(self, text):
        if text and text not in self._ocr_warnungen:
            self._ocr_warnungen.add(text)
            if text != ABGEBROCHEN:
                self.warnungen.append(text)

    def ziel_sicherstellen(self):
        """Zielordner erst anlegen, wenn wirklich etwas geschrieben wird (kein leerer Ordner bei 0 Treffern)."""
        try:
            self.ziel.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OSError(f"Zielordner kann nicht angelegt werden ({self.ziel}): {e}") from e

    def tmp_pfad(self, kennung: str) -> Path:
        self.ziel_sicherstellen()
        p = self.ziel / f".anonym_tmp_{os.getpid()}_{kennung}.pdf"
        if p not in self.tmp_pfade:
            self.tmp_pfade.append(p)
        return p

    def zwischenspeichern(self, nr):
        """Zwischenstand speichern und neu öffnen, damit geschwärzte Scan-Bilder nicht unkomprimiert
        im Speicher bleiben (M-52). Wechselt zwischen zwei Dateinamen, weil PyMuPDF nicht auf die
        gerade geöffnete Datei speichert."""
        kennung = "b" if self.geoeffnet_von == self.tmp_pfad("a") else "a"
        ziel = self.tmp_pfad(kennung)
        self.doc.save(ziel, garbage=1, deflate=True)
        self.doc.close()
        self.doc = fitz.open(ziel)
        self.geoeffnet_von = ziel
        self.scan_seiten_seit_speichern = 0
        self.melde(f"   Zwischenstand gespeichert (Seite {nr + 1}) …")

    def ocr_woerter(self, nr, modus, bildbereiche):
        """OCR-Wörter der Seite: aus dem Cache der Analyse oder vom OcrDienst."""
        if nr in self.ocr_cache:
            return [tuple(w[:5]) for w in self.ocr_cache[nr]]
        self.melde(f"   OCR läuft: {self.pdf_pfad.name}, Seite {nr + 1}/{len(self.doc)} …")
        woerter = []
        if modus == "seite":
            w, warnung = self.ocr.woerter(self.pdf_pfad, nr, OCR_DPI)
            woerter += w
            self.ocr_warnung(warnung)
            winkel = getattr(self.ocr, "winkel", None)
            if winkel is not None:
                try:
                    self.winkel_je_seite[nr] = winkel(self.pdf_pfad, nr, OCR_DPI)
                except Exception:
                    pass
        else:
            for bereich in bildbereiche:
                self.abbruch_pruefen()
                w, warnung = self.ocr.woerter(self.pdf_pfad, nr, OCR_DPI, clip=bereich)
                woerter += w
                self.ocr_warnung(warnung)
        self.abbruch_pruefen()
        return woerter


# ----------------------------------------------------------------------
# Seite bearbeiten
# ----------------------------------------------------------------------
def _hat_kurven(seite) -> bool:
    """Vektorzeichnungen mit Kurven (Unterschrift, Stempel, Logo) – Linien und Rechtecke zählen nicht."""
    try:
        if len(seite.read_contents()) > 1_500_000:
            return False
        kurven = 0
        for pfad in seite.get_drawings():
            for item in pfad.get("items", []):
                if item[0] == "c":
                    kurven += 1
                    if kurven >= 3:
                        return True
    except Exception:
        pass
    return False


def _seite_bearbeiten(lauf: _Lauf, nr: int, versteckt: list):
    doc = lauf.doc
    seite = doc[nr]
    if seite.rotation:
        seite.remove_rotation()
    modus = ocr_noetig(seite)
    bildbereiche = bild_bereiche(seite) if modus != "nein" else []
    tp = seite.get_textpage()
    kette = _Zeichenkette(seite, tp)
    woerter_vorher = seite.get_text("words", textpage=tp) if kette.zeichen else []

    # 1) Treffer in der Textebene (Ganzwort, echte Glyphen-Koordinaten)
    hits = []   # dict: fund, rects, groesse, grundlinie, freiraum
    for fund in lauf.funde:
        treffer = kette.suche(fund["text"])
        if not treffer and kette.zeichen:
            for variante in _anfangs_varianten(fund["text"]):
                treffer = kette.suche(variante)
                if treffer:
                    lauf.anfangstreffer[fund["text"]] = variante
                    break
        for indizes in treffer:
            teile = kette.rechtecke(indizes, bildbereiche)
            if not teile:
                continue
            rects = [t[0] for t in teile]
            hits.append({"fund": fund, "rects": rects, "groesse": teile[0][2], "grundlinie": teile[0][3],
                         "freiraum": kette.freiraum(rects[0], indizes)})

    # 2) Treffer in der OCR-Wortliste (Scans, Bilder auf Textseiten)
    ocr_woerter = []
    if modus in ("seite", "bilder"):
        lauf.ocr_modus[nr] = modus
        lauf.bildbereiche[nr] = bildbereiche
        ocr_woerter = lauf.ocr_woerter(nr, modus, bildbereiche)
        for fund in lauf.funde:
            wort_treffer = _treffer_in_woertern(ocr_woerter, fund["text"])
            if not wort_treffer and ocr_woerter:
                for variante in _anfangs_varianten(fund["text"]):
                    wort_treffer = _treffer_in_woertern(ocr_woerter, variante)
                    if wort_treffer:
                        lauf.anfangstreffer[fund["text"]] = variante
                        break
            for wort_rects in wort_treffer:
                rects = []
                for r in _zeilen_zusammenfassen(wort_rects):
                    r = fitz.Rect(r.x0 - OCR_RAND, r.y0 - OCR_RAND, r.x1 + OCR_RAND, r.y1 + OCR_RAND)
                    rects.append(r & seite.rect)
                hits.append({"fund": fund, "rects": rects, "grundlinie": None,
                             "groesse": rects[0].height / 1.6 if rects else 0,
                             "freiraum": _wort_freiraum(ocr_woerter, rects[0]) if rects else None})
        if modus == "seite":
            _schluesselwoerter_pruefen(lauf, nr, ocr_woerter)

    # 3) Deduplizieren (nur ENTHALTENE Rechtecke verwerfen), Redaktionen und Platzhalter planen
    bereits: list = []
    platzhalter: list = []   # (Rechteck, Text, Schriftgröße, Grundlinie)
    kategorien: set = set()
    for hit in hits:
        fund = hit["fund"]
        lauf.gefunden.add(fund["text"])          # auch, wenn ein längerer Treffer ihn schon abdeckt
        kategorien.add(fund.get("kategorie", ""))
        rects = [r for r in hit["rects"] if not r.is_empty
                 and not any(alt.contains(r) for alt in bereits)]
        if not rects:
            continue
        lauf.treffer += 1
        ersatz = fund.get("ersatz") or ""
        if ersatz:
            max_pt = hit["groesse"] if hit["groesse"] > 0 else rects[0].height / 1.6
            r, text, fs = _platzhalter_planen(rects[0], ersatz, max_pt, hit["freiraum"], seite.rect)
            if fs is None:
                lauf.ohne_platzhalter += 1
            else:
                if text != ersatz:
                    lauf.abgekuerzt[text] = ersatz
                rects[0] = r
                platzhalter.append((r, text, fs, hit["grundlinie"]))
        for r in rects:
            bereits.append(r)
            seite.add_redact_annot(r, fill=FUELLFARBE)
    if kategorien:
        lauf.kategorien_je_seite[nr] = kategorien

    # 4) Versteckte Ebenen-Inhalte (ohne Platzhalter) mitschwärzen
    for r in versteckt:
        bereits.append(r)
        seite.add_redact_annot(r, fill=FUELLFARBE)
    if versteckt:
        lauf.hinweise.append(f"Seite {nr + 1}: {len(versteckt)} ausgeblendete Inhalt(e) einer Ebene entfernt.")

    # 5) Anwenden (Text UND Bildpixel), Platzhalter schreiben, Kollateralschaden prüfen
    if bereits:
        seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                               graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                               text=fitz.PDF_REDACT_TEXT_REMOVE)
        for r, text, fs, grundlinie in platzhalter:
            if not _platzhalter_zeichnen(seite, r, text, fs, grundlinie):
                lauf.ohne_platzhalter += 1
        if woerter_vorher:
            _kollateral_pruefen(lauf, nr, seite, woerter_vorher, bereits)
        if modus == "seite":
            lauf.scan_seiten_seit_speichern += 1
    lauf.rects_je_seite[nr] = bereits

    # 6) Hinweise zu Grafiken/Bildern (Unterschriften, Stempel, Fotos werden nicht geprüft)
    if bildbereiche and modus == "bilder":
        lauf.bild_seiten.append(nr + 1)
    if _hat_kurven(seite):
        lauf.grafik_seiten.append(nr + 1)
    return modus


def _kollateral_pruefen(lauf, nr, seite, woerter_vorher, rects):
    """Wörter, die kein Treffer waren, müssen nach der Schwärzung noch da sein (gleicher Text auf
    gleicher Höhe – MuPDF verschiebt Resttext einer Zeile horizontal leicht)."""
    try:
        nachher = [(w[4], fitz.Rect(w[:4])) for w in seite.get_text("words")]
    except Exception:
        return
    beschaedigt = []
    for w in woerter_vorher:
        r = fitz.Rect(w[:4])
        bedeckt = 0.0
        for x in rects:
            if min(r.y1, x.y1) - max(r.y0, x.y0) > 0.3 * r.height:
                bedeckt += max(0.0, min(r.x1, x.x1) - max(r.x0, x.x0))
        if bedeckt > 0.5 * (r.width or 1.0):
            continue   # gehört zum Treffer (oder ist dessen Satzzeichen)
        if not any(t == w[4] and min(r.y1, n.y1) - max(r.y0, n.y0) > 0.5 * r.height for t, n in nachher):
            beschaedigt.append(w[4])
    if beschaedigt:
        beispiel = ", ".join(repr(b) for b in beschaedigt[:3])
        lauf.kollateral.append(f"Seite {nr + 1}: {len(beschaedigt)} Nachbarwort/-wörter beschädigt "
                               f"(enger Zeilenabstand), z. B. {beispiel}")


def _schluesselwoerter_pruefen(lauf, nr, ocr_woerter):
    """M-50: Schlüsselwort auf einer OCR-Seite gelesen, aber kein Fund dieser Kategorie – warnen."""
    if not ocr_woerter:
        return
    text = " ".join(w[4] for w in ocr_woerter)
    kategorien = {f.get("kategorie", "") for f in lauf.funde}
    for kategorie, anzeige, muster in _SCHLUESSELWOERTER:
        m = muster.search(text)
        if not m:
            continue
        hat_treffer = any(f.get("kategorie") == kategorie and _treffer_in_woertern(ocr_woerter, f["text"])
                          for f in lauf.funde)
        if hat_treffer:
            continue
        hinweis = ("" if kategorie in kategorien else " (Kategorie nicht in der Fundliste)")
        lauf.warnungen.append(f"Seite {nr + 1}: Schlüsselwort »{m.group(0)}« gelesen, aber kein "
                              f"{anzeige}-Fund lokalisiert{hinweis} – OCR-Verleser möglich, bitte prüfen!")


# ----------------------------------------------------------------------
# Selbstkontrolle
# ----------------------------------------------------------------------
def _innerhalb(rect, rects) -> bool:
    mitte = fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
    return any(r.contains(mitte) for r in rects)


def _selbstkontrolle(lauf: _Lauf, ausgabe: Path) -> list:
    """Sucht alle Fundtexte in der Ausgabe (Ganzwort / Wortfolge; auf OCR-Seiten per Kontroll-OCR der
    Ausgabe). Treffer innerhalb der gesetzten Rechtecke (= Platzhalter) zählen nicht."""
    reste: list = []
    kontrolle = fitz.open(ausgabe)
    try:
        for nr in range(len(kontrolle)):
            lauf.abbruch_pruefen()
            seite = kontrolle[nr]
            rects = lauf.rects_je_seite.get(nr, [])
            kette = _Zeichenkette(seite)
            for fund in lauf.funde:
                if fund["text"] in reste:
                    continue
                for indizes in kette.suche(fund["text"]):
                    teile = kette.rechtecke(indizes, [])
                    if teile and not all(_innerhalb(t[1], rects) for t in teile):
                        reste.append(fund["text"])
                        break
            modus = lauf.ocr_modus.get(nr)
            if modus and lauf.ocr is not None and (rects or lauf.kategorien_je_seite.get(nr)):
                lauf.melde(f"   Kontroll-OCR: Seite {nr + 1}/{len(kontrolle)} …")
                woerter = []
                if modus == "seite":
                    # dieselbe Ausrichtung wie beim Original: die Ausgabe enthält zu wenige Wörter,
                    # um sie neu zu bestimmen (und die Platzhalter stehen aufrecht)
                    w, _ = lauf.ocr.woerter(ausgabe, nr, OCR_DPI, winkel=lauf.winkel_je_seite.get(nr, 0))
                    woerter += w
                else:
                    for bereich in lauf.bildbereiche.get(nr, []):
                        w, _ = lauf.ocr.woerter(ausgabe, nr, OCR_DPI, clip=bereich)
                        woerter += w
                lauf.abbruch_pruefen()
                woerter = [w for w in woerter if not _innerhalb(fitz.Rect(w[:4]), rects)]
                for fund in lauf.funde:
                    if fund["text"] in reste:
                        continue
                    if _treffer_in_woertern(woerter, fund["text"]):
                        reste.append(fund["text"])
    finally:
        kontrolle.close()
    return reste


# ----------------------------------------------------------------------
# Hauptfunktion
# ----------------------------------------------------------------------
def schwaerze_pdf(pdf_pfad, funde: list, melde=None, fortschritt=None, abbruch=None, ocr=None,
                  ocr_cache=None, ziel_ordner=None) -> dict:
    """Ersetzt alle übergebenen Funde durch ihre Platzhalter – auch in Scans (Bildpixel werden mit
    entfernt) – und schreibt eine neutral benannte Ausgabedatei.

    Rückgabe: {"original", "ausgabe", "treffer", "uebersprungen", "warnungen", "hinweise", "reste", "fehler"}.
    melde(text): Protokolltext; fortschritt(seite_1basiert, seiten_gesamt); abbruch: threading.Event;
    ocr: OcrDienst (sonst eigener); ocr_cache: {Seitenindex: Wortliste} aus der Analyse;
    ziel_ordner: sonst <Ordner der PDF>/anonymisiert.
    """
    pdf_pfad = Path(pdf_pfad)
    ergebnis = {"original": pdf_pfad, "ausgabe": None, "treffer": 0, "uebersprungen": 0,
                "warnungen": [], "hinweise": [], "reste": [], "fehler": None}
    funde = [dict(f) for f in funde if str(f.get("text", "")).strip()]
    for f in funde:
        f["text"] = str(f["text"]).strip()
    funde.sort(key=lambda f: len(_norm_fund(f["text"])), reverse=True)
    if not funde:
        ergebnis["warnungen"].append(WARNUNG_KEIN_TREFFER)
        return ergebnis

    ziel = Path(ziel_ordner) if ziel_ordner else pdf_pfad.parent / "anonymisiert"
    eigener_dienst = None
    if ocr is None:
        ocr = eigener_dienst = OcrDienst()
    lauf = _Lauf(pdf_pfad, funde, melde, fortschritt, abbruch, ocr, ocr_cache, ziel)
    try:
        try:
            lauf.doc = fitz.open(pdf_pfad)
        except Exception as e:
            ergebnis["fehler"] = f"Konnte nicht geöffnet werden: {e}"
            return ergebnis
        if lauf.doc.needs_pass:
            ergebnis["fehler"] = "Passwortgeschützt – übersprungen."
            return ergebnis
        _schwaerzen(lauf, ergebnis)
    except _Abgebrochen:
        ergebnis["fehler"] = ABGEBROCHEN
        ergebnis["ausgabe"] = None
    except OSError as e:   # Zielordner/Zwischenstand nicht schreibbar
        ergebnis["fehler"] = str(e)
        ergebnis["warnungen"] = lauf.warnungen
        ergebnis["hinweise"] = lauf.hinweise
    finally:
        if lauf.doc is not None:
            try:
                lauf.doc.close()
            except Exception:
                pass
        _aufraeumen(lauf.tmp_pfade)
        if eigener_dienst is not None:
            eigener_dienst.schliessen()
    return ergebnis


def _schwaerzen(lauf: _Lauf, ergebnis: dict):
    doc = lauf.doc
    seiten = len(doc)
    lauf.abbruch_pruefen()

    # 1) Formularfelder und Anmerkungen in den Seiteninhalt einbrennen (sonst bleiben Feldwerte stehen)
    zaehler = _nebenkanaele_zaehlen(doc)
    try:
        doc.bake()
    except Exception as e:
        lauf.warnungen.append(f"Formularfelder/Anmerkungen konnten nicht eingebrannt werden ({e}) – "
                              f"Feldinhalte in der Ausgabe bitte prüfen.")
    if zaehler["formularfelder"]:
        lauf.hinweise.append("Formularfelder wurden eingebrannt und mitgeschwärzt – die Ausgabe ist "
                             "nicht mehr ausfüllbar.")
    if zaehler["xfa"]:
        lauf.warnungen.append("XFA-Formular: Feldinhalte können nicht geprüft werden – die XFA-Daten "
                              "werden aus der Ausgabe entfernt.")

    # 2) Ebenen: ausgeblendete Inhalte ermitteln (werden geschwärzt), Ebenensteuerung entfernen
    doc, versteckt = _ebenen_behandeln(doc)
    lauf.doc = doc
    # 3) Klartext-Markierungen in Inhaltsströmen, Nebenkanäle
    _markierungen_bereinigen(doc)
    _nebenkanaele_entfernen(doc, zaehler)
    lauf.hinweise.append(_nebenkanal_hinweis(zaehler))

    # 4) Seiten
    ocr_seiten = 0
    for nr in range(seiten):
        lauf.abbruch_pruefen()
        if lauf.fortschritt:
            lauf.fortschritt(nr + 1, seiten)
        modus = _seite_bearbeiten(lauf, nr, versteckt.get(nr, []))
        if modus == "seite":
            ocr_seiten += 1
        if lauf.scan_seiten_seit_speichern >= STAPEL_SCANSEITEN:
            lauf.abbruch_pruefen()
            lauf.zwischenspeichern(nr)
    doc = lauf.doc
    ergebnis["treffer"] = lauf.treffer

    # 5) Nicht lokalisierte Funde
    nicht_gefunden = [f["text"] for f in lauf.funde if f["text"] not in lauf.gefunden]
    # gleiche Texte nur einmal
    nicht_gefunden = list(dict.fromkeys(nicht_gefunden))
    ergebnis["uebersprungen"] = len(nicht_gefunden)
    if lauf.treffer == 0:
        lauf.warnungen.append(WARNUNG_KEIN_TREFFER)
        ergebnis["warnungen"] = lauf.warnungen
        ergebnis["hinweise"] = lauf.hinweise
        return
    if nicht_gefunden:
        beispiele = ", ".join(repr(t) for t in nicht_gefunden[:6])
        rest = f" (+{len(nicht_gefunden) - 6} weitere)" if len(nicht_gefunden) > 6 else ""
        lauf.warnungen.append(f"{len(nicht_gefunden)} Fund(e) konnten im Dokument nicht lokalisiert werden "
                              f"und bleiben ggf. sichtbar – bitte prüfen: {beispiele}{rest}")
    if ocr_seiten:
        lauf.hinweise.append(f"{ocr_seiten} Seite(n) als Scan per OCR geschwärzt (Bildpixel entfernt).")
    if lauf.anfangstreffer:
        paare = "; ".join(f"{k!r} → {v!r}" for k, v in list(lauf.anfangstreffer.items())[:5])
        lauf.warnungen.append(f"{len(lauf.anfangstreffer)} Fund(e) kamen so im Dokument nicht vor und wurden "
                              f"nur mit ihrem Anfang geschwärzt (Fundtext endet mitten im Wort?): {paare}")
    if lauf.abgekuerzt:
        paare = ", ".join(f"{k} = {v}" for k, v in sorted(lauf.abgekuerzt.items()))
        lauf.hinweise.append(f"Platzhalter in engen Lücken abgekürzt: {paare}.")
    if lauf.ohne_platzhalter:
        lauf.hinweise.append(f"{lauf.ohne_platzhalter} Stelle(n) ohne Platzhalter-Text (Lücke zu klein) – "
                             f"geschwärzt sind sie trotzdem.")
    lauf.hinweise.extend(lauf.kollateral)
    if lauf.bild_seiten:
        lauf.hinweise.append(f"Seite(n) {', '.join(map(str, lauf.bild_seiten))}: enthalten Bilder – "
                             f"maschinenlesbarer Text darin wurde per OCR geprüft, Unterschriften, "
                             f"Fotos und Handschrift nicht.")
    if lauf.grafik_seiten:
        lauf.hinweise.append(f"Seite(n) {', '.join(map(str, lauf.grafik_seiten))}: enthalten Grafiken/"
                             f"Zeichnungen (Unterschrift? Stempel? Logo?), die nicht geprüft werden.")
    if lauf.ocr is not None:
        for h in getattr(lauf.ocr, "hinweise", []):
            if h not in lauf.hinweise:
                lauf.hinweise.append(h)

    # 6) Speichern (erst unter Hilfsnamen), Selbstkontrolle, dann endgültiger Name
    lauf.abbruch_pruefen()
    tmp = lauf.tmp_pfad("ausgabe")
    try:
        doc.save(tmp, garbage=4, deflate=True)
    except Exception as e:
        ergebnis["fehler"] = (f"Ausgabe konnte nicht geschrieben werden ({e}) – ist der Ordner "
                              f"»{lauf.ziel}« beschreibbar oder die Datei noch geöffnet?")
        ergebnis["warnungen"] = lauf.warnungen
        ergebnis["hinweise"] = lauf.hinweise
        return
    doc.close()
    lauf.doc = None
    reste = _selbstkontrolle(lauf, tmp)
    ergebnis["reste"] = reste
    if reste:
        beispiele = ", ".join(repr(t) for t in reste[:5])
        lauf.warnungen.append(f"Selbstkontrolle: {len(reste)} Fundtext(e) sind in der Ausgabe noch "
                              f"auffindbar ({beispiele}) – Datei als _PRUEFEN abgelegt, unbedingt "
                              f"manuell prüfen!")
    lauf.abbruch_pruefen()
    ausgabe = _freier_ausgabename(lauf.ziel, pruefen=bool(reste))
    try:
        os.replace(tmp, ausgabe)
    except OSError as e:
        ergebnis["fehler"] = f"Ausgabe konnte nicht abgelegt werden ({e}) – Ordner »{lauf.ziel}« beschreibbar?"
        ergebnis["warnungen"] = lauf.warnungen
        ergebnis["hinweise"] = lauf.hinweise
        return
    lauf.tmp_pfade.remove(tmp)
    ergebnis["ausgabe"] = ausgabe
    try:
        _zuordnung_anhaengen(lauf.ziel, ausgabe, lauf.pdf_pfad)
    except OSError as e:
        lauf.warnungen.append(f"Zuordnungsdatei _zuordnung.txt konnte nicht geschrieben werden: {e}")
    lauf.hinweise.append(f"Zuordnung Original ↔ Ausgabe steht in {lauf.ziel / '_zuordnung.txt'} "
                         f"(nicht mit weitergeben).")
    ergebnis["warnungen"] = lauf.warnungen
    ergebnis["hinweise"] = lauf.hinweise
