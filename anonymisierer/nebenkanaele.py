"""Nebenkanäle: alles, was personenbezogene Daten außerhalb des sichtbaren Seitentexts tragen kann.

Öffentliche Schnittstelle (CONTRACT_V2.md 12.4):
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

import re

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
