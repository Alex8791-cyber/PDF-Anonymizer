"""Nebenkanäle: alles, was personenbezogene Daten außerhalb des sichtbaren Seitentexts tragen kann.

Öffentliche Schnittstelle (CONTRACT_V2.md 12.4):
    nebenkanaele_lesen(doc) -> list[NebenkanalText]
                                               Texte der Nebenkanäle für die Erkennung (Gutachten R-04): Info-/
                                               XMP-Metadaten (auch an Seiten und Bildern; Creator/Producer/CreatorTool
                                               als eigener Kanal „programm“), Lesezeichen, Anhänge (Name, Beschreibung,
                                               Inhalt – Text/CSV/XML/Office/PDF, rekursiv; auch Portfolios und Datei-
                                               Anmerkungen), XFA-Formulardaten, JavaScript (Zeichenketten), Link-
                                               Ziele, Seitenbeschriftungen. Nicht lesbare Anhänge (Bild, Scan,
                                               verschlüsselt …) kommen mit pruefbar=False zurück
    nebenkanaele_zaehlen(doc) -> dict          VOR doc.bake() aufrufen (Formularfelder, Anmerkungen, XFA …)
    markierungen_entfernen(doc) -> int         /ActualText, /Alt, /E aus Inhaltsströmen (Seiten, alle Form-
                                               XObjects, Muster) und Properties-Ressourcen; gehört in die
                                               gemeinsame Vorbereitung von Analyse UND Schwärzung (vor dem
                                               Seitenmodell), damit beide die echten Glyphen sehen (S-06)
    nebenkanaele_entfernen(doc, zaehler=None) -> dict
                                               nach dem Anwenden aller Schwärzungen, vor dem Speichern
    nebenkanal_hinweis(zaehler) -> str         Nutzerhinweis "Entfernt bzw. eingebrannt: …"

Entfernt werden: Anmerkungen aller Art (außer noch nicht angewendeten Schwärzungen), Links, Lesezeichen,
eingebettete Dateien (auch /AF, ZUGFeRD-XML), Info- und XMP-Metadaten (Dokument, Seiten, Bilder, Fonts),
Seiten-Miniaturbilder, PieceInfo, Strukturbaum, /ActualText-/Alt-/E-Ersatztexte, Seitenbeschriftungen
(/PageLabels), JavaScript und Aktionen (/OpenAction, /AA, URI, Launch …), Formular-/XFA-Daten, Artikel-
threads, Ebenennamen, Inhalte außerhalb des sichtbaren Seitenbereichs (CropBox/MediaBox, S-05), EXIF/XMP/
IPTC/Kommentare und Vorschaubilder in eingebetteten JPEG-/JPX-Bildern (S-11), die Dokument-/ID.
"""

import html
import io
import re
import zipfile
from typing import NamedTuple

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import bilder as _bilder

# Katalog-Einträge, die Klartext, Dateien oder Skripte tragen können
KATALOG_SCHLUESSEL = ("AcroForm", "Names", "Dests", "PieceInfo", "OpenAction", "AA", "StructTreeRoot", "MarkInfo",
                      "Outlines", "Metadata", "OCProperties", "Collection", "Requirements", "PageLabels",
                      "SpiderInfo", "Threads", "URI", "Perms", "DSS", "AF", "Legal")
SEITEN_SCHLUESSEL = ("Thumb", "PieceInfo", "AA", "Metadata", "B", "AF", "ID", "PresSteps")
XOBJEKT_SCHLUESSEL = ("Metadata", "PieceInfo", "OPI", "AF", "Ref")
AKTIONS_TYPEN = ("/JavaScript", "/Launch", "/URI", "/SubmitForm", "/GoToR", "/GoToE", "/ImportData",
                 "/Rendition", "/Sound", "/Movie", "/RichMediaExecute", "/Thread", "/GoTo3DView")
MARKIERUNGS_SCHLUESSEL = (b"ActualText", b"Alt", b"E")      # Ersatz-, Alternativ-, Abkürzungstext
STRUKTUR_TEXT_SCHLUESSEL = ("ActualText", "Alt", "E", "T")

# Beschnitt (S-05): Inhalt, der so weit über den sichtbaren Bereich hinausreicht, wird entfernt
BESCHNITT_RAND_PT = 0.5        # Abstand der Schwärzungsstreifen vom sichtbaren Rand (Glyphen am Rand bleiben)
BESCHNITT_TEXT_PT = 1.0        # Text/Vektor, der mehr als 1 pt hinausragt, zählt
BESCHNITT_BILD_PT = 9.0        # Bilder erst ab 9 pt (über übliche 3-mm-Druckbeschnitt-Zugaben hinaus)

ZAEHLER_TEXTE = (
    ("formularfelder", "Formularfeld(er)"), ("anmerkungen", "Anmerkung(en)"), ("links", "Link(s)"),
    ("lesezeichen", "Lesezeichen"), ("anhaenge", "eingebettete Datei(en)"),
    ("miniaturbilder", "Miniaturbild(er)"), ("ebenen", "Ebene(n)"),
    ("markierungen", "versteckte Ersatztext(e) (ActualText/Alt)"),
    ("seitenbeschriftungen", "Seitenbeschriftung(en)"), ("aktionen", "Skript(e)/Aktion(en)"),
    ("beschnitt", "Seite(n) mit Inhalt außerhalb des sichtbaren Bereichs"),
    ("bild_metadaten", "Bild-Metadaten (EXIF/XMP/Kommentar)"), ("strukturbaum", "Strukturbaum (Tags)"),
    ("formulardaten", "Formular-/XFA-Daten"),
)


# ----------------------------------------------------------------------
# Hilfen für Wörterbuch-Schlüssel
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


def _ist_stream(doc, xref) -> bool:
    try:
        return bool(doc.xref_is_stream(xref))
    except Exception:
        return False


# ----------------------------------------------------------------------
# Lexer für Inhaltsströme (nur so viel PDF-Syntax wie nötig)
# ----------------------------------------------------------------------
_WEISS = frozenset(b" \t\r\n\x0c\x00")
_TRENNER = frozenset(b"()<>[]{}/%")
_REGULAER = re.compile(rb"[^\s()<>\[\]{}/%\x00]+")
_NAME = re.compile(rb"/[^\s()<>\[\]{}/%\x00]*")
_HEX = re.compile(rb"<[0-9A-Fa-f\s]*>")
_KANDIDAT = re.compile(rb"/(?:ActualText|Alt|E)(?=[\s()<>\[\]{}/%\x00]|$)")


class _Lexerfehler(Exception):
    pass


def _string_ende(strom: bytes, i: int) -> int:
    """Ende (exklusiv) der Literal-Zeichenkette ab strom[i] == '(' – Klammertiefe und Escapes."""
    tiefe, j, n = 0, i, len(strom)
    while j < n:
        c = strom[j]
        if c == 0x5C:                    # Backslash: nächstes Zeichen überspringen
            j += 2
            continue
        if c == 0x28:
            tiefe += 1
        elif c == 0x29:
            tiefe -= 1
            if tiefe == 0:
                return j + 1
        j += 1
    raise _Lexerfehler("Zeichenkette nicht geschlossen")


def _name_wert(token: bytes) -> bytes:
    """Name ohne '/' mit aufgelösten #xx-Escapes."""
    roh = token[1:]
    if b"#" not in roh:
        return roh
    return re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), roh)


def _inline_bild_ende(strom: bytes, i: int) -> int:
    """Position nach den Binärdaten eines Inline-Bilds (i = direkt hinter dem Operator ID)."""
    n = len(strom)
    j = i + 1 if i < n and strom[i] in _WEISS else i
    while True:
        k = strom.find(b"EI", j)
        if k < 0:
            return n
        vor_ok = k > 0 and strom[k - 1] in _WEISS
        nach_ok = k + 2 >= n or strom[k + 2] in _WEISS
        if vor_ok and nach_ok:
            return k + 2
        j = k + 2


class _Behaelter:
    __slots__ = ("art", "start", "eintraege", "schluessel", "schluessel_start")

    def __init__(self, art, start):
        self.art = art                    # "dict" | "array"
        self.start = start
        self.eintraege = []               # dict: (schluessel, schluessel_start, wert_ende)
        self.schluessel = None
        self.schluessel_start = None


def _markierungs_spannen(strom: bytes) -> list:
    """Byte-Spannen (start, ende) aller /ActualText-, /Alt- und /E-Einträge in den Eigenschafts-
    Wörterbüchern der Operatoren BDC und DP. Zeichenketten, Inline-Bilder und Kommentare werden korrekt
    übersprungen; verschachtelte Klammern und Hex-Strings sind erlaubt."""
    spannen = []
    stapel: list = []
    operanden: list = []                  # ("dict", _Behaelter) | ("wert", None)
    i, n = 0, len(strom)

    def wert_fertig(art, behaelter, ende):
        if stapel:
            oben = stapel[-1]
            if oben.art == "dict":
                if oben.schluessel is None:
                    raise _Lexerfehler("Wert ohne Schlüssel")
                oben.eintraege.append((oben.schluessel, oben.schluessel_start, ende))
                oben.schluessel = None
            return
        operanden.append((art, behaelter))

    while i < n:
        c = strom[i]
        if c in _WEISS:
            i += 1
            continue
        if c == 0x25:                                       # % Kommentar
            j = i
            while j < n and strom[j] not in (0x0A, 0x0D):
                j += 1
            i = j
            continue
        if c == 0x28:                                       # (
            ende = _string_ende(strom, i)
            wert_fertig("wert", None, ende)
            i = ende
            continue
        if c == 0x3C:                                       # <
            if i + 1 < n and strom[i + 1] == 0x3C:          # <<
                stapel.append(_Behaelter("dict", i))
                i += 2
                continue
            m = _HEX.match(strom, i)
            if not m:
                raise _Lexerfehler("Hex-String defekt")
            wert_fertig("wert", None, m.end())
            i = m.end()
            continue
        if c == 0x3E:                                       # >>
            if i + 1 < n and strom[i + 1] == 0x3E and stapel and stapel[-1].art == "dict":
                b = stapel.pop()
                wert_fertig("dict", b, i + 2)
                i += 2
                continue
            raise _Lexerfehler("unerwartetes >")
        if c == 0x5B:                                       # [
            stapel.append(_Behaelter("array", i))
            i += 1
            continue
        if c == 0x5D:                                       # ]
            if stapel and stapel[-1].art == "array":
                b = stapel.pop()
                wert_fertig("wert", b, i + 1)
                i += 1
                continue
            raise _Lexerfehler("unerwartetes ]")
        if c in (0x7B, 0x7D, 0x29):                         # { } ) – in Inhaltsströmen bedeutungslos
            i += 1
            continue
        if c == 0x2F:                                       # /Name
            m = _NAME.match(strom, i)
            ende = m.end()
            if stapel and stapel[-1].art == "dict" and stapel[-1].schluessel is None:
                stapel[-1].schluessel = _name_wert(m.group(0))
                stapel[-1].schluessel_start = i
            else:
                wert_fertig("wert", None, ende)
            i = ende
            continue
        m = _REGULAER.match(strom, i)
        if not m:
            raise _Lexerfehler("unbekanntes Zeichen")
        token = m.group(0)
        i = m.end()
        if stapel:                                          # Zahl/Schlüsselwort innerhalb eines Behälters
            wert_fertig("wert", None, i)
            continue
        if re.fullmatch(rb"[+\-]?(?:\d+\.?\d*|\.\d+)|true|false|null", token):
            operanden.append(("wert", None))
            continue
        # Operator
        if token in (b"BDC", b"DP") and operanden and operanden[-1][0] == "dict":
            for schluessel, start, ende in operanden[-1][1].eintraege:
                if schluessel in MARKIERUNGS_SCHLUESSEL:
                    spannen.append((start, ende))
        if token == b"ID":
            i = _inline_bild_ende(strom, i)
        operanden = []
    return spannen


def markierungen_aus_strom(strom: bytes) -> tuple:
    """Entfernt /ActualText, /Alt und /E aus den BDC-/DP-Eigenschaften eines Inhaltsstroms.
    Rückgabe: (neuer Strom, Anzahl entfernter Einträge). Unverändert, wenn nichts zu tun ist.
    Lässt sich der Strom nicht zerlegen, werden die Schlüssel samt Zeichenkette außerhalb von
    Zeichenketten trotzdem entfernt (Rückfall), damit kein Ersatztext übrig bleibt."""
    if not strom or not _KANDIDAT.search(strom):
        return strom, 0
    try:
        spannen = _markierungs_spannen(strom)
    except _Lexerfehler:
        spannen = _rueckfall_spannen(strom)
    if not spannen:
        return strom, 0
    teile, pos = [], 0
    for start, ende in sorted(spannen):
        if start < pos:
            continue
        teile.append(strom[pos:start])
        teile.append(b" ")
        pos = ende
    teile.append(strom[pos:])
    return b"".join(teile), len(spannen)


def _rueckfall_spannen(strom: bytes) -> list:
    """Rückfall für defekte Ströme: /ActualText und /Alt mit folgender Zeichenkette (auch verschachtelt)."""
    spannen = []
    for m in re.finditer(rb"/(?:ActualText|Alt)(?=[\s(<])", strom):
        j = m.end()
        while j < len(strom) and strom[j] in _WEISS:
            j += 1
        try:
            if strom[j:j + 1] == b"(":
                ende = _string_ende(strom, j)
            elif strom[j:j + 1] == b"<" and strom[j + 1:j + 2] != b"<":
                hm = _HEX.match(strom, j)
                if not hm:
                    continue
                ende = hm.end()
            else:
                continue
        except _Lexerfehler:
            continue
        spannen.append((m.start(), ende))
    return spannen


# ----------------------------------------------------------------------
# Inhaltsströme und Ressourcen des Dokuments
# ----------------------------------------------------------------------
def _formular_xrefs(doc) -> list:
    """Alle Form-XObjects und Kachelmuster (eigene Inhaltsströme), auch verschachtelte und unbenutzte."""
    xrefs = []
    for xref in range(1, doc.xref_length()):
        if not _ist_stream(doc, xref):
            continue
        try:
            if doc.xref_get_key(xref, "Subtype")[1] == "/Form" or doc.xref_get_key(xref, "PatternType")[1] == "1":
                xrefs.append(xref)
        except Exception:
            continue
    return xrefs


def _aufloesen(doc, xref, pfad):
    """Folgt einem Schlüsselpfad über indirekte Verweise: (xref des Objekts, das den Rest direkt enthält,
    Restpfad). xref_set_key lehnt Pfade durch indirekte Objekte ab."""
    teile = pfad.split("/")
    i = 0
    while i < len(teile):
        art, wert = doc.xref_get_key(xref, "/".join(teile[:i + 1]))
        if art == "xref" and i < len(teile) - 1:
            xref = int(wert.split()[0])
            teile = teile[i + 1:]
            i = 0
            continue
        if art == "null":
            return None, None
        i += 1
    return xref, "/".join(teile)


def _properties_bereinigen(doc, xref) -> int:
    """Properties-Ressourcen (/Span /MC0 BDC) eines Seiten-/XObject-Wörterbuchs: /ActualText, /Alt, /E
    aus direkt eingebetteten Eigenschafts-Wörterbüchern entfernen (indirekte erledigt der Objekt-Durchgang)."""
    try:
        besitzer, pfad = _aufloesen(doc, xref, "Resources/Properties")
        if besitzer is None:
            return 0
        art, wert = doc.xref_get_key(besitzer, pfad)
        if art == "xref":
            besitzer, pfad = int(wert.split()[0]), ""
            wert = doc.xref_object(besitzer, compressed=True)
        elif art != "dict":
            return 0
    except Exception:
        return 0
    namen = {_name_wert(m.group(0)).decode("latin-1") for m in _NAME.finditer(wert.encode("latin-1", "replace"))}
    anzahl = 0
    for name in namen:
        voll = f"{pfad}/{name}" if pfad else name
        try:
            art_n, _ = doc.xref_get_key(besitzer, voll)
        except Exception:
            continue
        if art_n != "dict":
            continue
        for schluessel in ("ActualText", "Alt", "E"):
            if _schluessel_loeschen(doc, besitzer, f"{voll}/{schluessel}"):
                anzahl += 1
    return anzahl


def markierungen_entfernen(doc) -> int:
    """Entfernt /ActualText, /Alt und /E (Ersatz-, Alternativ-, Abkürzungstext) aus allen Inhaltsströmen
    (Seiten, alle Form-XObjects beliebiger Tiefe, Kachelmuster) und aus den Properties-Ressourcen. MuPDF und
    andere Werkzeuge geben diese Texte statt der gezeichneten Glyphen aus – sie können also Daten tragen,
    die auf der Seite gar nicht zu sehen sind (Gutachten S-06). Rückgabe: Anzahl entfernter Einträge."""
    anzahl = 0
    besitzer = []
    for seite in doc:
        besitzer.append(seite.xref)
        try:
            ströme = list(seite.get_contents())
        except Exception:
            ströme = []
        for xref in ströme:
            anzahl += _strom_bereinigen(doc, xref)
    for xref in _formular_xrefs(doc):
        besitzer.append(xref)
        anzahl += _strom_bereinigen(doc, xref)
    for xref in besitzer:
        anzahl += _properties_bereinigen(doc, xref)
    # indirekte Eigenschafts-Wörterbücher und Strukturelemente
    for xref in range(1, doc.xref_length()):
        try:
            schluessel = doc.xref_get_keys(xref)
        except Exception:
            continue
        if not schluessel:
            continue
        typ = doc.xref_get_key(xref, "Type")[1] if "Type" in schluessel else ""
        struktur = typ == "/StructElem" or ("S" in schluessel and "P" in schluessel and "K" in schluessel)
        for s in (STRUKTUR_TEXT_SCHLUESSEL if struktur else ("ActualText", "Alt")):
            if s in schluessel and _schluessel_loeschen(doc, xref, s):
                anzahl += 1
    return anzahl


def _strom_bereinigen(doc, xref) -> int:
    try:
        strom = doc.xref_stream(xref)
    except Exception:
        return 0
    neu, anzahl = markierungen_aus_strom(strom)
    if anzahl:
        doc.update_stream(xref, neu)
    return anzahl


# ----------------------------------------------------------------------
# Beschnitt (S-05)
# ----------------------------------------------------------------------
def _beschnitt_streifen(seite) -> list:
    """Schwärzungsstreifen für Inhalte außerhalb des sichtbaren Bereichs (CropBox, bzw. MediaBox, falls
    kleiner): MuPDF liefert solchen Text nicht, pdftotext und Parser aber schon. Leer, wenn nichts
    hinausragt (Druckbeschnitt von Hintergrundbildern bis BESCHNITT_BILD_PT zählt nicht)."""
    sichtbar = fitz.Rect(seite.rect)
    gesamt = fitz.Rect(sichtbar)
    for art, bbox in seite.get_bboxlog():
        if "clip" in art:
            continue
        r = fitz.Rect(bbox)
        if r.is_empty or r.is_infinite or abs(r) > 1e12:
            continue
        grenze = BESCHNITT_BILD_PT if "image" in art or "imgmask" in art else BESCHNITT_TEXT_PT
        if (r.x0 < sichtbar.x0 - grenze or r.y0 < sichtbar.y0 - grenze or r.x1 > sichtbar.x1 + grenze
                or r.y1 > sichtbar.y1 + grenze):
            gesamt |= r
    if gesamt == sichtbar:
        return []
    innen = sichtbar + (-BESCHNITT_RAND_PT, -BESCHNITT_RAND_PT, BESCHNITT_RAND_PT, BESCHNITT_RAND_PT)
    aussen = gesamt + (-2, -2, 2, 2)
    streifen = [fitz.Rect(aussen.x0, aussen.y0, aussen.x1, innen.y0),
                fitz.Rect(aussen.x0, innen.y1, aussen.x1, aussen.y1),
                fitz.Rect(aussen.x0, innen.y0, innen.x0, innen.y1),
                fitz.Rect(innen.x1, innen.y0, aussen.x1, innen.y1)]
    return [r for r in streifen if r.width > 0.5 and r.height > 0.5]


def beschnitt_entfernen(doc, seite, qualitaet=_bilder.JPEG_QUALITAET) -> bool:
    """Entfernt Text, Vektorgrafik und Bildpixel außerhalb des sichtbaren Bereichs einer Seite (per
    Schwärzung ohne Füllung – der sichtbare Inhalt bleibt unverändert). Berührte Bilder werden danach
    wieder kompakt kodiert. Rückgabe: True, wenn etwas entfernt wurde. Liegen auf der Seite noch nicht
    angewendete Schwärzungen, bricht sie mit RuntimeError ab: apply_redactions würde sie sonst mit fremden
    Parametern anwenden (Reihenfolge beim Aufrufer: erst schwärzen, dann Nebenkanäle)."""
    if seite.rotation:
        seite.remove_rotation()
    streifen = _beschnitt_streifen(seite)
    if not streifen:
        return False
    if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in seite.annots()):
        raise RuntimeError("Seite hat noch nicht angewendete Schwärzungen – nebenkanaele_entfernen erst "
                           "nach apply_redactions aufrufen.")
    vorher = _bilder.bildzustand(seite)
    for r in streifen:
        seite.add_redact_annot(r, fill=False, cross_out=False)
    seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                           graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                           text=fitz.PDF_REDACT_TEXT_REMOVE)
    geaendert = _bilder.geaenderte_bilder(seite, vorher)
    if geaendert:
        _bilder.bilder_neu_kodieren(doc, geaendert, qualitaet)
    return True


# ----------------------------------------------------------------------
# Zählen (vor bake) und Entfernen (nach dem Schwärzen)
# ----------------------------------------------------------------------
def nebenkanaele_zaehlen(doc) -> dict:
    """Zählt Nebenkanäle VOR doc.bake() (danach sind Formularfelder und Anmerkungen eingebrannt)."""
    z = {"formularfelder": 0, "anmerkungen": 0, "links": 0, "lesezeichen": 0, "anhaenge": 0,
         "miniaturbilder": 0, "ebenen": 0, "xfa": False}
    for seite in doc:
        try:
            z["formularfelder"] += sum(1 for _ in seite.widgets())
            z["anmerkungen"] += sum(1 for _ in seite.annots())
            z["links"] += len(seite.get_links())
            z["miniaturbilder"] += int(_schluessel_vorhanden(doc, seite.xref, "Thumb"))
        except Exception:
            continue
    try:
        z["lesezeichen"] = len(doc.get_toc())
    except Exception:
        pass
    try:
        z["anhaenge"] = doc.embfile_count()
    except Exception:
        pass
    try:
        z["ebenen"] = len(doc.get_ocgs())
    except Exception:
        pass
    z["xfa"] = _schluessel_vorhanden(doc, doc.pdf_catalog(), "AcroForm/XFA")
    return z


def _anmerkungen_entfernen(doc, seite) -> tuple:
    """Löscht alle Anmerkungen und Links der Seite (nicht: noch nicht angewendete Schwärzungen)."""
    anmerkungen = links = 0
    for annot in list(seite.annots()):
        if annot.type[0] == fitz.PDF_ANNOT_REDACT:
            continue
        seite.delete_annot(annot)
        anmerkungen += 1
    for link in seite.get_links():
        seite.delete_link(link)
        links += 1
    # was die API nicht kennt (Popup, Widget-Reste, unbekannte Typen): aus /Annots austragen
    art, wert = doc.xref_get_key(seite.xref, "Annots")
    if art == "xref":                                        # /Annots als indirektes Array
        try:
            wert, art = doc.xref_object(int(wert.split()[0]), compressed=True), "array"
        except Exception:
            art = "null"
    if art != "null":
        behalten = []
        for annot in seite.annots(types=[fitz.PDF_ANNOT_REDACT]):
            behalten.append(f"{annot.xref} 0 R")
        rest = len(re.findall(r"\d+\s+0\s+R", wert)) if art == "array" else 0
        if rest > len(behalten):
            anmerkungen += rest - len(behalten)
            doc.xref_set_key(seite.xref, "Annots", f"[{' '.join(behalten)}]" if behalten else "null")
    return anmerkungen, links


def _jpeg_ohne_metadaten(daten: bytes) -> bytes:
    """Entfernt aus einem JPEG die Segmente APP1-APP13 und APP15 (EXIF mit Vorschaubild und GPS, XMP, IPTC,
    ICC, FlashPix …), COM (Kommentare), JFXX-Vorschaubilder in APP0 und alles nach dem Bildende (angehängte
    Vorschau-/Tiefenbilder, Bewegtbild). JFIF (APP0) und Adobe (APP14, Farbtransformation) bleiben.
    Bei unerwartetem Aufbau: unverändert zurück."""
    if not daten.startswith(b"\xff\xd8"):
        return daten
    aus, i, n = [b"\xff\xd8"], 2, len(daten)
    while i + 4 <= n:
        if daten[i] != 0xFF:
            return daten
        marker = daten[i + 1]
        if marker == 0xFF:                                   # Füllbyte
            i += 1
            continue
        if marker == 0xD9:                                   # Bildende ohne Scan: lieber nichts anfassen
            return daten
        if marker in (0x01,) or 0xD0 <= marker <= 0xD7:
            aus.append(daten[i:i + 2])
            i += 2
            continue
        laenge = int.from_bytes(daten[i + 2:i + 4], "big")
        if laenge < 2 or i + 2 + laenge > n:
            return daten
        segment = daten[i:i + 2 + laenge]
        if marker == 0xDA:                                   # Start of Scan: Entropiedaten bis zum nächsten Marker
            aus.append(segment)
            j = i + 2 + laenge
            while j < n - 1:
                if daten[j] == 0xFF and daten[j + 1] != 0x00 and not (0xD0 <= daten[j + 1] <= 0xD7):
                    break
                j += 1
            aus.append(daten[i + 2 + laenge:j])
            if j >= n - 1:
                return daten                                 # kein Bildende gefunden
            if daten[j + 1] == 0xD9:                         # Bildende: Rest (Anhänge) verwerfen
                aus.append(b"\xff\xd9")
                return b"".join(aus)
            i = j                                            # weitere Segmente (progressives JPEG)
            continue
        weg = (0xE1 <= marker <= 0xED) or marker == 0xEF or marker == 0xFE
        if marker == 0xE0 and segment[4:9] != b"JFIF\x00":
            weg = True                                       # JFXX-Vorschaubild u. a.
        elif marker == 0xE0 and len(segment) > 18:           # JFIF mit eingebettetem Vorschaubild:
            # Marker(2) Länge(2) "JFIF\0"(5) Version(2) Einheit(1) Dichte(4) Vorschau-Breite/-Höhe(2)
            segment = segment[:2] + (16).to_bytes(2, "big") + segment[4:16] + b"\x00\x00"
        if not weg:
            aus.append(segment)
        i += 2 + laenge
    return daten


def _jpx_ohne_metadaten(daten: bytes) -> bytes:
    """JPEG 2000 (JP2-Container): oberste Kästen xml/uuid/uinf/jp2i/ipr entfernen."""
    if len(daten) < 12 or daten[4:8] != b"jP  ":
        return daten
    aus, i, n = [], 0, len(daten)
    while i + 8 <= n:
        laenge = int.from_bytes(daten[i:i + 4], "big")
        typ = daten[i + 4:i + 8]
        kopf = 8
        if laenge == 1:
            if i + 16 > n:
                return daten
            laenge = int.from_bytes(daten[i + 8:i + 16], "big")
            kopf = 16
        elif laenge == 0:
            laenge = n - i
        if laenge < kopf or i + laenge > n:
            return daten
        if typ not in (b"xml ", b"uuid", b"uinf", b"jp2i", b"ipr "):
            aus.append(daten[i:i + laenge])
        i += laenge
    return b"".join(aus) if i == n else daten


def _bild_metadaten_entfernen(doc, xref) -> bool:
    """EXIF/XMP/Kommentare aus einem Bild-XObject (JPEG/JPX-Strom und /Metadata)."""
    entfernt = _schluessel_loeschen(doc, xref, "Metadata")
    filt = doc.xref_get_key(xref, "Filter")[1]
    if "DCTDecode" in filt or "JPXDecode" in filt:
        if filt.startswith("[") and len(re.findall(r"/\w+", filt)) > 1:
            return entfernt                                  # Filterkette: Rohdaten nicht direkt JPEG
        roh = doc.xref_stream_raw(xref)
        neu = _jpeg_ohne_metadaten(roh) if "DCT" in filt else _jpx_ohne_metadaten(roh)
        if neu != roh:
            parameter = doc.xref_get_key(xref, "DecodeParms")
            doc.update_stream(xref, neu, compress=False)
            doc.xref_set_key(xref, "Filter", "/DCTDecode" if "DCT" in filt else "/JPXDecode")
            if parameter[0] != "null":
                doc.xref_set_key(xref, "DecodeParms", parameter[1])
            entfernt = True
    return entfernt


def _objekte_bereinigen(doc, z: dict):
    """Ein Durchgang über alle Objekte: Metadaten-Ströme leeren, /Metadata-Verweise lösen, Aktionen
    entschärfen, Ebenennamen neutralisieren, XObject-Schlüssel (OPI, Ref, PieceInfo, AF) und
    Bild-Metadaten entfernen."""
    ebene = 0
    for xref in range(1, doc.xref_length()):
        try:
            schluessel = doc.xref_get_keys(xref)
        except Exception:
            continue
        if not schluessel:
            continue
        typ = doc.xref_get_key(xref, "Type")[1] if "Type" in schluessel else ""
        subtyp = doc.xref_get_key(xref, "Subtype")[1] if "Subtype" in schluessel else ""
        if typ == "/Metadata" and _ist_stream(doc, xref):
            doc.update_stream(xref, b"")
            z["metadaten"] = z.get("metadaten", 0) + 1
            continue
        if typ == "/EmbeddedFile" and _ist_stream(doc, xref):
            doc.update_stream(xref, b"")                 # Inhalt eines (noch irgendwo verwiesenen) Anhangs
            continue
        if typ in ("/Sig", "/DocTimeStamp"):
            doc.update_object(xref, "<<>>")              # Unterschrift: Name, Ort, Grund, Zertifikat
            z["formulardaten"] = 1
            continue
        if typ == "/Filespec" or ("EF" in schluessel and "F" in schluessel):
            for s in ("EF", "RF", "Desc", "CI", "Thumb"):
                _schluessel_loeschen(doc, xref, s)
            for s in ("F", "UF"):
                if s in schluessel:
                    doc.xref_set_key(xref, s, "(Anhang)")  # Dateinamen tragen oft Namen
            continue
        if "Metadata" in schluessel and subtyp != "/Image":
            _schluessel_loeschen(doc, xref, "Metadata")
        if "S" in schluessel and doc.xref_get_key(xref, "S")[1] in AKTIONS_TYPEN and not _ist_stream(doc, xref):
            doc.update_object(xref, "<<>>")
            z["aktionen"] += 1
            continue
        if typ == "/OCG" and "Name" in schluessel:
            ebene += 1
            doc.xref_set_key(xref, "Name", f"(Ebene {ebene})")
        if subtyp in ("/Form", "/Image"):
            for s in XOBJEKT_SCHLUESSEL:
                if s != "Metadata" and s in schluessel:
                    _schluessel_loeschen(doc, xref, s)
        if subtyp == "/Image":
            try:
                if _bild_metadaten_entfernen(doc, xref):
                    z["bild_metadaten"] += 1
            except Exception as e:
                z.setdefault("fehler", []).append(f"Bild {xref}: {e}")


def nebenkanaele_entfernen(doc, zaehler=None) -> dict:
    """Entfernt alle Nebenkanäle (siehe Modulbeschreibung) und liefert die Zähler für den Nutzerhinweis.

    zaehler: Ergebnis von nebenkanaele_zaehlen() VOR doc.bake() (wird ergänzt und zurückgegeben).
    Aufrufen NACH dem Anwenden aller Schwärzungen (apply_redactions) und vor dem Speichern; noch nicht
    angewendete Schwärzungsanmerkungen bleiben stehen. Speichern danach mit garbage >= 1 (besser 4), damit
    gelöste Objekte (alte Metadaten, Original-Bilder, Anhänge) nicht in der Datei bleiben.
    """
    z = dict(zaehler or {})
    for s, standard in (("formularfelder", 0), ("anmerkungen", 0), ("links", 0), ("lesezeichen", 0),
                        ("anhaenge", 0), ("miniaturbilder", 0), ("ebenen", 0), ("xfa", False),
                        ("markierungen", 0), ("seitenbeschriftungen", 0), ("aktionen", 0), ("beschnitt", 0),
                        ("bild_metadaten", 0), ("strukturbaum", 0), ("formulardaten", 0), ("metadaten", 0)):
        z.setdefault(s, standard)
    gezaehlt = zaehler is not None
    katalog = doc.pdf_catalog()

    # 1) Seiten: Anmerkungen, Links, Seiten-Schlüssel
    for seite in doc:
        anmerkungen, links = _anmerkungen_entfernen(doc, seite)
        if not gezaehlt:
            z["anmerkungen"] += anmerkungen
            z["links"] += links
        for s in SEITEN_SCHLUESSEL:
            if _schluessel_loeschen(doc, seite.xref, s):
                if s == "Thumb" and not gezaehlt:
                    z["miniaturbilder"] += 1
                elif s == "AA":
                    z["aktionen"] += 1

    # 2) Ersatztexte in Inhaltsströmen (idempotent, falls schon in der Vorbereitung geschehen)
    z["markierungen"] += markierungen_entfernen(doc)

    # 3) Inhalte außerhalb des sichtbaren Bereichs
    for seite in doc:
        if beschnitt_entfernen(doc, seite):
            z["beschnitt"] += 1

    # 4) Dokumentweite Kanäle
    try:
        toc = doc.get_toc()
        if toc:
            if not gezaehlt:
                z["lesezeichen"] = len(toc)
            doc.set_toc([])
    except Exception:
        pass
    try:
        namen = list(doc.embfile_names())
        for name in namen:
            doc.embfile_del(name)
        if not gezaehlt:
            z["anhaenge"] = len(namen)
    except Exception:
        pass
    if _schluessel_vorhanden(doc, katalog, "PageLabels"):
        try:
            z["seitenbeschriftungen"] = len(doc.get_page_labels()) or 1
        except Exception:
            z["seitenbeschriftungen"] = 1
    if _schluessel_vorhanden(doc, katalog, "StructTreeRoot"):
        z["strukturbaum"] = 1
    if _schluessel_vorhanden(doc, katalog, "AcroForm"):
        z["formulardaten"] = 1
    for s in ("OpenAction", "AA"):
        if _schluessel_vorhanden(doc, katalog, s):
            z["aktionen"] += 1
    if _schluessel_vorhanden(doc, katalog, "Names/JavaScript"):
        z["aktionen"] += 1
    if not gezaehlt:
        try:
            z["ebenen"] = len(doc.get_ocgs())
        except Exception:
            pass
    try:
        doc.set_metadata({})
    except Exception:
        pass
    try:
        doc.del_xml_metadata()
    except Exception:
        pass
    for s in KATALOG_SCHLUESSEL:
        _schluessel_loeschen(doc, katalog, s)
    _schluessel_loeschen(doc, -1, "ID")          # neue Dokument-ID beim Speichern (keine Verknüpfung zum Original)
    _schluessel_loeschen(doc, -1, "Info")

    # 5) Alle Objekte: Metadaten, Aktionen, Ebenennamen, XObject-Schlüssel, Bild-Metadaten
    _objekte_bereinigen(doc, z)
    return z


# ----------------------------------------------------------------------
# Lesen für die Erkennung (Analyse, Gutachten R-04)
# ----------------------------------------------------------------------
class NebenkanalText(NamedTuple):
    """Ein Stück Text aus einem Nebenkanal.
    kanal: "metadaten" | "programm" (Creator/Producer/CreatorTool: Programm- und Gerätenamen – zählen nur mit einem
    ausdrücklichen Vor- und Nachnamen, E-Mail-Adresse oder IBAN) | "lesezeichen" | "anhaenge" | "xfa" | "kommentare"
    (Notizen/Kommentare an der Seite) | "skripte" (JavaScript) | "links" (Link-Ziele: mailto, Parameter einer Adresse,
    Dateien) | "seitenbeschriftungen";
    einheit: Nummer innerhalb des Kanals – ein Metadatenfeld, ein Lesezeichen, ein Anhang samt Name, Beschreibung
    und Inhalt (auch dessen eigene Nebenkanäle) zählen je einmal; art: was es ist (für Meldungen, ohne den Inhalt);
    text: Text für die Erkennung; pruefbar=False: Inhalt nicht lesbar (Bild, Scan, verschlüsselt, unbekanntes
    Format, zu groß) – personenbezogene Daten sind dann nicht auszuschließen."""
    kanal: str
    einheit: int
    art: str
    text: str
    pruefbar: bool = True


LESEN_MAX_ZEICHEN = 400_000      # so viel Text wird höchstens gelesen (danach: „nicht vollständig prüfbar“)
LESEN_MAX_BYTES = 60 * 2**20     # größere Anhänge werden nicht ausgepackt
LESEN_MAX_TIEFE = 3              # Anhänge in Anhängen …
LESEN_MAX_SEITEN = 500           # Seiten eines angehängten PDFs
BILDFLAECHE_NICHT_PRUEFBAR = 0.3   # Seite eines angehängten PDFs, die zu so viel Fläche Bild ist: nicht prüfbar (Scan)
_INFO_TECHNISCH = frozenset({"CreationDate", "ModDate", "Trapped", "PTEX.Fullbanner", "GTS_PDFXVersion",
                             "GTS_PDFXConformance", "GTS_PDFVTVersion", "SourceModified"})
# Programm- und Gerätenamen (Gutachten-Befund NEBENKANAL_FUND auf „RICOH MP C3004“, „Crystal Reports“): eigener Kanal
# „programm“, geprüft nur auf ausdrückliche Personennamen, E-Mail-Adressen und IBAN
_INFO_PROGRAMM = frozenset({"Creator", "Producer"})
_XML_PROGRAMM = re.compile(r"(?i)^(?:creatortool|producer)$")
_XML_TECHNISCH = re.compile(
    r"(?i)^(?:about|documentid|instanceid|originaldocumentid|versionid|renditionclass|createdate|modifydate|"
    r"metadatadate|pdfversion|format|trapped|producer|when|action|changed|parameters|softwareagent|xmptk|part|"
    r"conformance|lang|schemeid|currencyid|listid|unitcode|encoding|version|standalone|space|type|id|href|class|"
    r"style)$")
_XML_WERT_TECHNISCH = re.compile(r"(?i)^(?:[\d\s.,:+\-/TZ]*|uuid:\S*|xmp\.\w+:\S*|urn:\S*|https?://\S*|"
                                 r"application/\S+|true|false)$")
_XML_BLATT = re.compile(r"<([A-Za-z_][\w.:-]*)(\s[^<>]*)?(?<!/)>([^<>]*)</\1\s*>", re.S)
_XML_ATTRIBUT = re.compile(r"([A-Za-z_][\w.:-]*)\s*=\s*\"([^\"]*)\"")
_XML_WEGLASSEN = re.compile(r"(?is)<!--.*?-->|<!\[CDATA\[|\]\]>|<\?.*?\?>|<(\w+:)?(?:template|config)\b.*?"
                            r"</(?:\w+:)?(?:template|config)\s*>")
_HTML_RE = re.compile(rb"(?is)^\s*(?:<!doctype\s+html|<html|<head|<body)")
_BILD_KENNUNGEN = ((b"\xff\xd8\xff", "JPEG"), (b"\x89PNG\r\n\x1a\n", "PNG"), (b"II*\x00", "TIFF"),
                   (b"MM\x00*", "TIFF"), (b"GIF87a", "GIF"), (b"GIF89a", "GIF"), (b"BM", "BMP"),
                   (b"\x00\x00\x00\x0cjP  \r\n\x87\n", "JPEG 2000"), (b"\xffO\xffQ", "JPEG 2000"),
                   (b"8BPS", "Photoshop"), (b"\x97JB2\r\n\x1a\n", "JBIG2"))
_OFFICE_TEILE = re.compile(r"^(?:word/(?:document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml|"
                           r"xl/(?:sharedStrings|comments\d*)\.xml|xl/worksheets/sheet\d+\.xml|"
                           r"ppt/(?:slides/slide\d+|notesSlides/notesSlide\d+|comments/comment\d+)\.xml|"
                           r"docProps/(?:core|app|custom)\.xml|content\.xml|meta\.xml)$")


def bildart(anfang: bytes):
    """Bildformat aus den ersten Bytes einer Datei ("JPEG", "PNG", "TIFF", "HEIC" …) oder None."""
    for kennung, name in _BILD_KENNUNGEN:
        if anfang.startswith(kennung):
            return name
    if anfang[:4] == b"RIFF" and anfang[8:12] == b"WEBP":
        return "WebP"
    if anfang[4:8] == b"ftyp" and anfang[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"avif"):
        return "HEIC"
    kopf = anfang.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if kopf.startswith(b"<svg") or (kopf.startswith(b"<?xml") and b"<svg" in kopf):
        return "SVG"
    return None


def ist_html(anfang: bytes) -> bool:
    return bool(_HTML_RE.match(anfang.lstrip(b"\xef\xbb\xbf")))


def _xml_zu_text(xml: str, programm: list | None = None) -> str:
    """XML lesbar machen: Blattelemente als „Name: Wert“-Zeilen (der Elementname ist oft das Etikett: <IBAN>,
    <Geburtsdatum>), dazu inhaltliche Attributwerte; technische Felder (Kennungen, Zeitstempel, Namensräume) und
    XFA-Schablonen (nur Beschriftungen) entfallen. Ohne Blattelemente: Text ohne Tags.
    programm (Liste, nur für XMP-Metadaten): Werte von CreatorTool und Producer (Programm-/Gerätenamen) kommen
    hierhin statt in den Text – sie werden nur auf ausdrückliche Personennamen geprüft."""
    xml = _XML_WEGLASSEN.sub(" ", xml)
    zeilen = []
    programm_vorher = len(programm) if programm is not None else 0
    for m in _XML_BLATT.finditer(xml):
        name = m.group(1).split(":")[-1]
        wert = " ".join(html.unescape(m.group(3)).split())
        if len(wert) > 200 and " " not in wert:
            continue                                  # eingebettete Daten (Base64-Vorschaubild …), kein Text
        if programm is not None and wert and _XML_PROGRAMM.match(name):
            programm.append(wert)
            continue
        if wert and not _XML_TECHNISCH.match(name) and not _XML_WERT_TECHNISCH.match(wert):
            ohne_etikett = name.lower() in ("li", "value", "text", "t", "p", "span", "div")
            zeilen.append(wert if ohne_etikett else f"{name}: {wert}")
    for name, wert in _XML_ATTRIBUT.findall(xml):
        lokal = name.split(":")[-1]
        wert = " ".join(html.unescape(wert).split())
        if programm is not None and wert and _XML_PROGRAMM.match(lokal):
            programm.append(wert)
            continue
        if name.startswith("xmlns") or _XML_TECHNISCH.match(lokal) or not wert or _XML_WERT_TECHNISCH.match(wert):
            continue
        zeilen.append(f"{lokal}: {wert}")
    if zeilen:
        return "\n".join(zeilen)
    if programm is not None and len(programm) > programm_vorher:
        return ""                                     # nur Programmangaben: die stehen schon in `programm`
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", xml)).split())


def _html_zu_text(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(?:p|div|tr|li|h\d)>", "\n", text)
    return "\n".join(" ".join(z.split()) for z in html.unescape(re.sub(r"<[^>]*>", " ", text)).splitlines()
                     if z.strip())


def _office_xml_text(name: str, xml: str) -> str:
    """Text eines Office-/ODF-Teils: Absätze als Zeilen, Zellen mit Tabulator; Läufe ohne Trennzeichen
    aneinander (Word teilt Wörter auf mehrere <w:t>). Eigenschaften (Autor …) als „Name: Wert“."""
    if name.startswith("docProps/") or name == "meta.xml":
        return _xml_zu_text(xml)
    if name.startswith("xl/worksheets/"):
        xml = " ".join(re.findall(r"(?s)<is>(.*?)</is>", xml))       # nur Zeichenketten in Zellen, keine Zahlen
    xml = re.sub(r"(?i)</(?:w:p|a:p|text:p|text:h|si|row|w:tr|table:table-row)>", "\n", xml)
    xml = re.sub(r"(?i)<(?:w:tab|w:br|w:cr|a:br|text:tab|text:line-break|text:s)\b[^>]*/?>", " ", xml)
    xml = re.sub(r"(?i)</(?:w:tc|c|table:table-cell)>", "\t", xml)
    text = html.unescape(re.sub(r"<[^>]*>", "", xml))
    return "\n".join(" ".join(z.split()) for z in text.splitlines() if z.strip())


def _zip_text(daten: bytes):
    """Text eines Office-/ODF-Dokuments (ZIP mit XML-Teilen) oder None (kein solches / zu groß / defekt)."""
    try:
        with zipfile.ZipFile(io.BytesIO(daten)) as z:
            teile = [i for i in z.infolist() if _OFFICE_TEILE.match(i.filename)]
            if not teile or sum(i.file_size for i in teile) > LESEN_MAX_BYTES:
                return None
            texte = [_office_xml_text(i.filename, z.read(i).decode("utf-8", "replace")) for i in teile]
    except Exception:
        return None
    return "\n".join(t for t in texte if t)


def _als_text(daten: bytes):
    """Bytes als Text (UTF-8/UTF-16 mit BOM, sonst UTF-8 oder Windows-1252) oder None, wenn es kein Text ist."""
    if daten.startswith(b"\xef\xbb\xbf"):
        return daten[3:].decode("utf-8", "replace")
    if daten.startswith((b"\xff\xfe", b"\xfe\xff")):
        return daten.decode("utf-16", "replace")
    probe = daten[:8192]
    if b"\x00" in probe:
        return None
    try:
        text = daten.decode("utf-8")
    except UnicodeDecodeError:
        text = daten.decode("cp1252", "replace")
    stichprobe = text[:8192]
    steuer = sum(1 for c in stichprobe if ord(c) < 32 and c not in "\t\r\n\x0c")
    return None if steuer > 0.02 * max(1, len(stichprobe)) else text


_CSV_TRENNER = (";", "\t", ",", "|")


def _csv_zu_text(text: str):
    """Eine Tabelle als CSV (Excel speichert in Deutschland mit Semikolon) wie ein Formular lesen: mit Kopfzeile
    „Spalte: Wert“ je Zelle, ohne Kopfzeile die Zellen einer Zeile durch Leerzeichen getrennt (dann sieht die
    Namenserkennung „Mustermann Max Berlin“ statt „Mustermann;Max;Berlin“). None, wenn es keine Tabelle ist."""
    zeilen = [z for z in text.splitlines() if z.strip()]
    if len(zeilen) < 2:
        return None
    for trenner in _CSV_TRENNER:
        spalten = [z.count(trenner) for z in zeilen[:50]]
        if min(spalten) < 1 or max(spalten) - min(spalten) > 1:
            continue
        zellen = [[c.strip().strip('"').strip() for c in z.split(trenner)] for z in zeilen]
        kopf = zellen[0]
        mit_kopf = (all(k and not any(ch.isdigit() for ch in k) for k in kopf)
                    and len({k.casefold() for k in kopf}) == len(kopf))
        aus = []
        for reihe in (zellen[1:] if mit_kopf else zellen):
            if mit_kopf:
                aus.extend(f"{k}: {w}" for k, w in zip(kopf, reihe) if w)
            else:
                aus.append(" ".join(w for w in reihe if w))
            aus.append("")
        return "\n".join(aus).strip()
    return None


def _bildanteil(seite) -> float:
    """Anteil der Seitenfläche, den Bilder bedecken (grob, Überlappungen zählen mehrfach, höchstens 1)."""
    try:
        flaeche = abs(seite.rect) or 1.0
        summe = 0.0
        for info in seite.get_image_info():
            r = fitz.Rect(info.get("bbox")) & seite.rect
            if not r.is_empty:
                summe += abs(r)
        return min(1.0, summe / flaeche)
    except Exception:
        return 1.0 if seite.get_images() else 0.0


def _pdf_inhalt(daten: bytes, tiefe: int) -> tuple:
    """(Texte, prüfbar, Art) eines angehängten PDFs: Seitentext und – rekursiv – seine Nebenkanäle. Seiten, die zu
    einem großen Teil Bild sind (Scan, auch mit einer Textzeile wie „Anlage 1“ oder einem Eingangsstempel), sind ohne
    OCR nicht prüfbar."""
    try:
        sub = fitz.open(stream=daten, filetype="pdf")
    except Exception:
        return [], False, "beschädigte PDF"
    try:
        if not sub.is_pdf:                                   # nie Seiten eines Nicht-PDFs anfassen (R-01)
            return [], False, "unbekanntes Format"
        if sub.needs_pass:
            return [], False, "verschlüsselte PDF"
        texte, pruefbar, zeichen = [], len(sub) <= LESEN_MAX_SEITEN, 0
        for nr in range(min(len(sub), LESEN_MAX_SEITEN)):
            seite = sub[nr]
            t = seite.get_text()
            if seite.get_images() and (not t.strip() or _bildanteil(seite) >= BILDFLAECHE_NICHT_PRUEFBAR):
                pruefbar = False                             # Scan im Anhang: ohne OCR nicht prüfbar
            zeichen += len(t)
            texte.append(t)
            if zeichen > LESEN_MAX_ZEICHEN:
                pruefbar = False
                break
        if tiefe < LESEN_MAX_TIEFE:
            for e in nebenkanaele_lesen(sub, tiefe + 1):
                texte.append(e.text)
                pruefbar = pruefbar and e.pruefbar
        else:
            pruefbar = pruefbar and not sub.embfile_count()
        return texte, pruefbar, "PDF" if pruefbar else "PDF (Scan oder zu umfangreich)"
    except Exception:
        return [], False, "beschädigte PDF"
    finally:
        sub.close()


def _anhang_inhalt(daten: bytes, tiefe: int) -> tuple:
    """(Texte, prüfbar, Art) eines Anhangs je nach Format."""
    if not daten:
        return [], True, "leer"
    if len(daten) > LESEN_MAX_BYTES:
        return [], False, "zu groß"
    kopf = daten[:2048]
    if kopf.startswith(b"%PDF") or b"%PDF-" in kopf[:1024]:
        return _pdf_inhalt(daten, tiefe)
    art = bildart(kopf)
    if art:
        return [], False, f"Bild ({art})"
    if kopf.startswith(b"PK\x03\x04"):
        text = _zip_text(daten)
        return ([text], True, "Office-Dokument") if text is not None else ([], False, "ZIP-Archiv")
    if kopf.startswith(b"\xd0\xcf\x11\xe0"):
        return [], False, "Office-/Outlook-Datei im alten Format"
    text = _als_text(daten)
    if text is None:
        return [], False, "unbekanntes Format"
    if len(text) > LESEN_MAX_ZEICHEN:
        return [text[:LESEN_MAX_ZEICHEN]], False, "sehr großer Text"
    probe = text.lstrip("﻿ \t\r\n")[:200].lower()
    if ist_html(text[:2048].encode("utf-8", "replace")):
        return [_html_zu_text(text)], True, "Webseite"
    if probe.startswith("<"):
        return [_xml_zu_text(text)], True, "XML"
    tabelle = _csv_zu_text(text)
    if tabelle is not None:
        return [text, tabelle], True, "Tabelle"
    return [text], True, "Text"


def _info_felder(doc, programm: list | None = None) -> list:
    """(Schlüssel, Wert) der Dokumenteigenschaften (Info-Wörterbuch, auch eigene Felder wie /Company). Creator und
    Producer (Programm-/Gerätenamen) kommen in die Liste `programm` (Schlüssel, Wert), sofern übergeben."""
    felder, programme = [], []
    try:
        art, wert = doc.xref_get_key(-1, "Info")
        if art == "xref":
            info = int(wert.split()[0])
            for k in doc.xref_get_keys(info):
                if k in _INFO_TECHNISCH:
                    continue
                a, v = doc.xref_get_key(info, k)
                if a == "string" and v.strip():
                    (programme if k in _INFO_PROGRAMM else felder).append((k, v.strip()))
    except Exception:
        felder, programme = [], []
    if not felder and not programme:
        try:
            md = doc.metadata or {}
        except Exception:
            md = {}
        for k, name in (("title", "Title"), ("author", "Author"), ("subject", "Subject"), ("keywords", "Keywords"),
                        ("creator", "Creator"), ("producer", "Producer")):
            v = str(md.get(k) or "").strip()
            if v:
                (programme if name in _INFO_PROGRAMM else felder).append((name, v))
    if programm is not None:
        programm.extend(programme)
    return felder


def _js_zeichenketten(quelle: str) -> list:
    """Zeichenketten-Literale eines JavaScript-Texts ('…', "…", `…`) – dort stehen Namen, IBAN, Texte von Meldungen;
    Programmcode selbst (Variablen, Funktionen) trägt keine Personendaten."""
    aus = []
    for m in re.finditer(r"'((?:\\.|[^'\\\n])*)'|\"((?:\\.|[^\"\\\n])*)\"|`((?:\\.|[^`\\])*)`", quelle or ""):
        wert = next((g for g in m.groups() if g is not None), "")
        wert = re.sub(r"\\(.)", r"\1", wert).strip()
        if any(c.isalnum() for c in wert):
            aus.append(wert)
    return aus


def _pdf_zeichenkette(roh: str) -> str:
    """Inhalt einer PDF-Literal-Zeichenkette ohne Klammern: Escapes (\\( \\) \\\\ \\n \\ddd) auflösen."""
    def ersetzen(m):
        z = m.group(1)
        if z.isdigit():
            return chr(int(z, 8))
        return {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f"}.get(z, z)
    return re.sub(r"\\([0-7]{1,3}|.)", ersetzen, roh)


def _skripte(doc) -> list:
    """Texte aller JavaScript-Aktionen (Dokument-Skripte, Öffnen-Aktion, Seiten-, Formularfeld- und Link-Aktionen):
    nur ihre Zeichenketten. Liest die Quelle der Objekte (auch direkt eingebettete Aktionen /A, /AA)."""
    texte = []
    for xref in range(1, doc.xref_length()):
        try:
            quelle = doc.xref_object(xref, compressed=True)
        except Exception:
            continue
        if "/JS" not in quelle:
            continue
        for m in re.finditer(r"/JS\s*(\d+)\s+\d+\s+R", quelle):
            try:
                texte.append(doc.xref_stream(int(m.group(1))).decode("latin-1", "replace"))
            except Exception:
                continue
        for m in re.finditer(r"/JS\s*\(((?:\\.|[^\\)])*)\)", quelle, re.S):
            texte.append(_pdf_zeichenkette(m.group(1)))
        for m in re.finditer(r"/JS\s*<([0-9A-Fa-f\s]*)>", quelle):
            try:
                texte.append(bytes.fromhex("".join(m.group(1).split())).decode("latin-1", "replace"))
            except ValueError:
                continue
    aus = []
    for t in texte:
        if t.startswith("﻿") or t.startswith("þÿ"):
            try:
                t = t.encode("latin-1", "replace").decode("utf-16", "replace")
            except Exception:
                pass
        teile = _js_zeichenketten(t)
        if teile:
            aus.append("\n".join(teile))
    return aus


def _link_text(ziel: str) -> str:
    """Prüfbarer Text eines Link-Ziels: E-Mail-Adresse aus mailto:, Parameter einer Webadresse als „Name: Wert“-Zeilen
    (dekodiert), Dateinamen; eine bloße Webadresse ohne Parameter (www.versicherer.de/kontakt) trägt nichts bei."""
    from urllib.parse import parse_qsl, unquote, urlsplit
    ziel = (ziel or "").strip()
    if not ziel:
        return ""
    if ziel.lower().startswith("mailto:"):
        adresse, _, rest = ziel[7:].partition("?")
        zeilen = [unquote(adresse)]
        zeilen += [f"{k}: {v}" for k, v in parse_qsl(rest, keep_blank_values=False)]
        return "\n".join(z for z in zeilen if z.strip())
    if re.match(r"(?i)^(?:https?|ftp)://", ziel):
        teile = urlsplit(ziel)
        zeilen = [f"{k}: {v}" for k, v in parse_qsl(teile.query, keep_blank_values=False)]
        if teile.fragment:
            zeilen.append(unquote(teile.fragment))
        return "\n".join(z for z in zeilen if z.strip())
    return unquote(ziel)                                     # Datei, Programm, eigenes Schema


def _links(doc) -> list:
    texte = []
    for nr in range(len(doc)):
        try:
            for link in doc[nr].get_links():
                t = _link_text(str(link.get("uri") or link.get("file") or ""))
                if t:
                    texte.append(t)
        except Exception:
            continue
    return texte


def _seitenbeschriftungen(doc) -> list:
    try:
        regeln = doc.get_page_labels() or []
    except Exception:
        return []
    return list(dict.fromkeys(str(r.get("prefix") or "").strip() for r in regeln if str(r.get("prefix") or "").strip()))


def _objekt_xmp(doc) -> list:
    """XMP-Metadaten an Seiten, Bildern, Schriften und Formular-XObjects (nicht die des Dokuments): (Text, Programme)."""
    katalog = doc.pdf_catalog()
    aus = []
    for xref in range(1, doc.xref_length()):
        if xref == katalog:
            continue
        try:
            art, wert = doc.xref_get_key(xref, "Metadata")
        except Exception:
            continue
        if art != "xref":
            continue
        try:
            daten = doc.xref_stream(int(wert.split()[0])) or b""
        except Exception:
            continue
        programme: list = []
        text = _xml_zu_text(daten.decode("utf-8", "replace"), programme)
        if text.strip() or programme:
            aus.append((text, programme))
    return aus


def _xfa_pakete(doc) -> list:
    """Inhalte der XFA-Pakete mit Formulardaten (datasets, form …; ohne Schablone und Einstellungen)."""
    katalog = doc.pdf_catalog()
    art, wert = doc.xref_get_key(katalog, "AcroForm")
    if art == "xref":
        art, wert = doc.xref_get_key(int(wert.split()[0]), "XFA")
    elif art == "dict":
        art, wert = doc.xref_get_key(katalog, "AcroForm/XFA")
    else:
        return []
    if art == "xref":
        return [doc.xref_stream(int(wert.split()[0])).decode("utf-8", "replace")]
    if art != "array":
        return []
    aus = []
    ohne = ("template", "config", "localeset", "xdp:xdp", "</xdp:xdp>", "preamble", "postamble", "xmpmeta",
            "connectionset", "sourceset", "stylesheet", "pdf", "signature", "xfdf")
    for name, xref in re.findall(r"\(([^)]*)\)\s*(\d+)\s+0\s+R", wert):
        if name.strip().lower() in ohne:
            continue
        try:
            aus.append(doc.xref_stream(int(xref)).decode("utf-8", "replace"))
        except Exception:
            continue
    return aus


def nebenkanaele_lesen(doc, tiefe: int = 0) -> list:
    """Texte aller Nebenkanäle eines PDFs für die Erkennung (Gutachten R-04): Dokumenteigenschaften (Info,
    XMP), Lesezeichen, Anhänge (eingebettete Dateien, Portfolio, Datei-Anmerkungen: Name, Beschreibung und
    Inhalt – Text, XML, Webseiten, Office-Dokumente, PDFs rekursiv), XFA-Formulardaten sowie Notizen und
    Kommentare an der Seite. VOR doc.bake() aufrufen (danach sind Anmerkungen eingebrannt). Liefert
    NebenkanalText-Einträge; nicht lesbare Inhalte mit pruefbar=False. Wirft nie: Fehler beim Lesen eines Kanals
    werden als „nicht prüfbar“ gemeldet."""
    aus: list = []
    programme: list = []                                      # (Art, Text) der Programm-/Gerätefelder
    # 1) Dokumenteigenschaften und XMP (des Dokuments, dann der Seiten, Bilder, Schriften)
    try:
        info_programme: list = []
        felder = _info_felder(doc, info_programme)
        for i, (name, wert) in enumerate(felder):
            aus.append(NebenkanalText("metadaten", i, f"Dokumenteigenschaft {name}", wert))
        programme += [(f"Dokumenteigenschaft {k}", v) for k, v in info_programme]
        einheit = len(felder)
        xmp = doc.get_xml_metadata() or ""
        if xmp.strip():
            xmp_programme: list = []
            text = _xml_zu_text(xmp, xmp_programme)
            if text.strip():
                aus.append(NebenkanalText("metadaten", einheit, "XMP-Metadaten", text[:LESEN_MAX_ZEICHEN]))
                einheit += 1
            programme += [("XMP-Metadaten (Programm)", v) for v in xmp_programme]
        for text, objekt_programme in _objekt_xmp(doc):
            if text.strip():
                aus.append(NebenkanalText("metadaten", einheit, "XMP-Metadaten einer Seite oder eines Bilds",
                                          text[:LESEN_MAX_ZEICHEN]))
                einheit += 1
            programme += [("XMP-Metadaten einer Seite oder eines Bilds (Programm)", v) for v in objekt_programme]
    except Exception:
        aus.append(NebenkanalText("metadaten", 0, "Dokumenteigenschaften", "", False))
    for i, (art, wert) in enumerate(dict.fromkeys(programme)):
        aus.append(NebenkanalText("programm", i, art, wert))
    # 2) Lesezeichen
    try:
        for i, eintrag in enumerate(doc.get_toc(simple=True)):
            if len(eintrag) > 1 and str(eintrag[1]).strip():
                aus.append(NebenkanalText("lesezeichen", i, "Lesezeichen", str(eintrag[1]).strip()))
    except Exception:
        aus.append(NebenkanalText("lesezeichen", 0, "Lesezeichen", "", False))
    # 3) Anhänge: eingebettete Dateien (auch Portfolio) und Datei-Anmerkungen
    nummer = 0
    try:
        namen = list(doc.embfile_names())
    except Exception:
        namen = []
    for name in namen:
        try:
            info = doc.embfile_info(name) or {}
            beschriftung = " ".join(dict.fromkeys(str(x).strip() for x in (name, info.get("filename"),
                                                                             info.get("ufilename"),
                                                                             info.get("description"))
                                                  if x and str(x).strip()))
            aus.append(NebenkanalText("anhaenge", nummer, "Name des Anhangs", beschriftung))
            texte, pruefbar, art = _anhang_inhalt(doc.embfile_get(name), tiefe)
            aus.append(NebenkanalText("anhaenge", nummer, f"Inhalt des Anhangs ({art})", "\n".join(texte), pruefbar))
        except Exception:
            aus.append(NebenkanalText("anhaenge", nummer, "Anhang", "", False))
        nummer += 1
    for nr in range(len(doc)):
        try:
            seite = doc[nr]
            for annot in seite.annots():
                typ = annot.type[0]
                info = annot.info or {}
                if typ == fitz.PDF_ANNOT_FILE_ATTACHMENT:
                    datei = getattr(annot, "file_info", None) or {}
                    beschriftung = " ".join(str(x).strip() for x in (datei.get("filename"), datei.get("description"),
                                                                     info.get("content")) if x and str(x).strip())
                    aus.append(NebenkanalText("anhaenge", nummer, "Name des Anhangs", beschriftung))
                    texte, pruefbar, art = _anhang_inhalt(annot.get_file(), tiefe)
                    aus.append(NebenkanalText("anhaenge", nummer, f"Inhalt des Anhangs ({art})", "\n".join(texte),
                                              pruefbar))
                    nummer += 1
                elif typ not in (fitz.PDF_ANNOT_WIDGET, fitz.PDF_ANNOT_LINK, fitz.PDF_ANNOT_REDACT):
                    text = "\n".join(str(info.get(k) or "").strip() for k in ("title", "subject", "content")
                                     if str(info.get(k) or "").strip())
                    if text:
                        aus.append(NebenkanalText("kommentare", len(aus), "Kommentar/Notiz", text))
        except Exception:
            aus.append(NebenkanalText("kommentare", len(aus), "Kommentare", "", False))
    # 4) XFA-Formulardaten
    try:
        pakete = _xfa_pakete(doc)
        text = "\n".join(_xml_zu_text(p) for p in pakete)
        if text.strip():
            aus.append(NebenkanalText("xfa", 0, "XFA-Formulardaten", text))
    except Exception:
        aus.append(NebenkanalText("xfa", 0, "XFA-Formulardaten", "", False))
    # 5) Was die Ausgabe ebenfalls entfernt, man beim Durchblättern aber nicht sieht: JavaScript, Link-Ziele
    #    (mailto:, Parameter einer Adresse, Dateien), Seitenbeschriftungen
    for kanal, art, lesen in (("skripte", "JavaScript", _skripte), ("links", "Link-Ziel", _links),
                              ("seitenbeschriftungen", "Seitenbeschriftung", _seitenbeschriftungen)):
        try:
            for i, text in enumerate(lesen(doc)):
                if text.strip():
                    aus.append(NebenkanalText(kanal, i, art, text[:LESEN_MAX_ZEICHEN]))
        except Exception:
            aus.append(NebenkanalText(kanal, 0, art, "", False))
    return aus


def nebenkanal_hinweis(zaehler: dict) -> str:
    """Nutzerhinweis zu den entfernten Nebenkanälen (Meldungscode NEBENKANAL_ENTFERNT)."""
    teile = []
    for schluessel, wort in ZAEHLER_TEXTE:
        wert = zaehler.get(schluessel)
        if not wert:
            continue
        if schluessel in ("strukturbaum", "formulardaten"):
            teile.append(wort)
        else:
            teile.append(f"{int(wert)} {wort}")
    teile.append("Metadaten/XMP")
    hinweis = "Entfernt bzw. eingebrannt: " + ", ".join(teile) + "."
    if zaehler.get("fehler"):
        hinweis += (f" {len(zaehler['fehler'])} Objekt(e) ließen sich nicht bereinigen – Datei bitte "
                    f"prüfen.")
    return hinweis
