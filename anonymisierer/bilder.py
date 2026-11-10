"""Bilder nach der Pixel-Schwärzung wieder kompakt speichern (Gutachten S-04).

apply_redactions(images=PDF_REDACT_IMAGE_PIXELS) legt jedes berührte Bild als NEUES, unkomprimiertes
Bildobjekt an; beim Speichern wird es FlateDecode-gepackt – ein JPEG-Scan wird dadurch 4- bis 5-mal größer
(946 KB -> 4,2 MB für zwei Seiten), mehrseitige Scans sprengen dann Upload-Grenzen. Dieses Modul kodiert die
geänderten Bilder wieder als JPEG (Farbe/Graustufen) bzw. Flate mit 1 Bit je Pixel (Schwarzweiß-Scans,
Stempelmasken). Die Schwärzung selbst bleibt erhalten: kodiert wird das bereits geschwärzte Pixelbild.

Öffentliche Schnittstelle (CONTRACT_V2.md 12.4):
    bildzustand(seite) -> dict                  vor apply_redactions: {xref: Bildinfo}
    geaenderte_bilder(seite, vorher) -> dict    nach apply_redactions: {neue xref: Bildinfo des Originals}
    bilder_neu_kodieren(doc, xrefs, qualitaet=85) -> int
        xrefs: Menge von xrefs oder dict aus geaenderte_bilder (dann zählt der Filter des Originals);
        Rückgabe: Anzahl neu kodierter Bilder.
    nach_schwaerzung(doc, seite, vorher, qualitaet=85) -> int   (geaenderte_bilder + bilder_neu_kodieren)
    seite_als_bild_schwaerzen(doc, seite, fuellen, leeren=(), farbe=…, dpi=200) -> xref
        Rückfall, wenn apply_redactions an einer Seite scheitert (Befund R-08): Seite durch ein Bild mit
        eingebrannten Schwärzungen ersetzen.

Ablauf beim Aufrufer:  vorher = bildzustand(seite); seite.apply_redactions(...);
                       nach_schwaerzung(doc, seite, vorher)
"""

import zlib

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

JPEG_QUALITAET = 85           # Standard für Farb-/Graustufenbilder
JPEG_MIN_QUALITAET = 60       # Untergrenze, wenn die Qualität des Originals geschätzt wird
VERLUSTFREI_SCHWELLE = 0.6    # Original verlustfrei: JPEG nur, wenn es höchstens 60 % der Flate-Größe hat
MIN_PIXEL_JPEG = 64 * 64      # kleinere Bilder (Icons) bleiben verlustfrei
VERLUSTBEHAFTET = ("DCTDecode", "JPXDecode")

# Standard-Quantisierungstabelle (Luminanz, JPEG Anhang K) für die Qualitätsschätzung
_STD_LUMINANZ = (16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
                 14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113,
                 92, 49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99)
_ZICKZACK = (0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6,
             7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31,
             39, 46, 53, 60, 61, 54, 47, 55, 62, 63)


def jpeg_qualitaet_schaetzen(daten: bytes):
    """Schätzt die libjpeg-Qualität (1-100) aus der Luminanz-Quantisierungstabelle eines JPEG; None, wenn
    keine Tabelle lesbar ist."""
    if not daten or not daten.startswith(b"\xff\xd8"):
        return None
    i, n = 2, len(daten)
    while i + 4 <= n and daten[i] == 0xFF:
        marker = daten[i + 1]
        laenge = int.from_bytes(daten[i + 2:i + 4], "big")
        if marker == 0xDB:                                  # DQT
            j, ende = i + 4, i + 2 + laenge
            while j < ende:
                praezision, tabelle = daten[j] >> 4, daten[j] & 0x0F
                groesse = 128 if praezision else 64
                werte = daten[j + 1:j + 1 + groesse]
                if praezision:
                    werte = [int.from_bytes(werte[k:k + 2], "big") for k in range(0, 128, 2)]
                if tabelle == 0 and len(werte) == 64:
                    natuerlich = [0] * 64
                    for k, z in enumerate(_ZICKZACK):
                        natuerlich[z] = werte[k]
                    skala = sum(natuerlich[k] * 100.0 / _STD_LUMINANZ[k] for k in range(64)) / 64
                    if skala <= 0:
                        return None
                    q = (200 - skala) / 2 if skala <= 100 else 5000 / skala
                    return int(max(1, min(100, round(q))))
                j += 1 + groesse
        if marker == 0xDA:
            return None
        i += 2 + laenge
    return None


def _bildinfo(doc, xref, breite=0, hoehe=0) -> dict:
    filt = doc.xref_get_key(xref, "Filter")[1]
    info = {"filter": filt, "groesse": (breite, hoehe), "qualitaet": None, "laenge": None}
    try:
        info["laenge"] = int(doc.xref_get_key(xref, "Length")[1])
    except (ValueError, TypeError):
        pass
    if "DCTDecode" in filt:
        try:
            info["qualitaet"] = jpeg_qualitaet_schaetzen(doc.xref_stream_raw(xref))
        except Exception:
            pass
    return info


def _bilder_der_seite(seite) -> list:
    """(xref, Breite, Höhe) aller Bilder aus den Ressourcen der Seite. Bewusst NICHT get_image_info/
    get_image_rects: PyMuPDF puffert deren Ergebnis im Seitenobjekt, nach apply_redactions ist es veraltet."""
    try:
        return [(e[0], e[2], e[3]) for e in seite.get_images(full=True) if e[0] > 0]
    except Exception:
        return []


def bildzustand(seite) -> dict:
    """Momentaufnahme der Bilder einer Seite vor apply_redactions: {xref: {"filter", "groesse", "qualitaet"}}."""
    doc = seite.parent
    zustand = {}
    for xref, breite, hoehe in _bilder_der_seite(seite):
        if xref not in zustand:
            try:
                zustand[xref] = _bildinfo(doc, xref, breite, hoehe)
            except Exception:
                zustand[xref] = {"filter": "", "groesse": (breite, hoehe), "qualitaet": None}
    return zustand


def geaenderte_bilder(seite, vorher: dict) -> dict:
    """Bilder, die apply_redactions neu angelegt hat (MuPDF ersetzt ein geschwärztes Bild durch ein neues
    Objekt mit neuer xref). Rückgabe: {neue xref: Bildinfo des ersetzten Originals (gleiche Pixelgröße,
    aus der Seite verschwunden) oder {} wenn unbekannt}."""
    jetzt = _bilder_der_seite(seite)
    noch_da = {x for x, _, _ in jetzt}
    verschwunden = [x for x in vorher if x not in noch_da]
    neu = {}
    for xref, breite, hoehe in jetzt:
        if xref in vorher or xref in neu:
            continue
        passend = [x for x in verschwunden if vorher[x].get("groesse") == (breite, hoehe)] or verschwunden
        if passend:
            alt = passend[0]
            verschwunden.remove(alt)
            neu[xref] = dict(vorher[alt])
        else:
            neu[xref] = {}
    return neu


def _komponenten(doc, xref) -> int | None:
    """Anzahl Farbkomponenten des Bildes (1 Grau, 3 RGB) oder None für alles Übrige (CMYK, Indexed …)."""
    art, cs = doc.xref_get_key(xref, "ColorSpace")
    if art == "name":
        return {"/DeviceGray": 1, "/DeviceRGB": 3, "/CalGray": 1, "/CalRGB": 3}.get(cs)
    if art == "xref":
        quelle = doc.xref_object(int(cs.split()[0]), compressed=True)
    elif art == "array":
        quelle = cs
    else:
        return None
    if "/ICCBased" in quelle:
        try:
            icc = int(quelle.split("/ICCBased")[1].split()[0])
            n = doc.xref_get_key(icc, "N")[1]
            return int(n) if n in ("1", "3") else None
        except Exception:
            return None
    if "/CalRGB" in quelle:
        return 3
    if "/CalGray" in quelle:
        return 1
    return None


def _flate_packen(doc, xref) -> bool:
    """Unkomprimiertes Bild (1 Bit, oder nicht JPEG-geeignet) verlustfrei mit Flate packen. zlib-Stufe 6:
    update_stream(compress=True) nutzt die höchste Stufe und braucht für eine 300-dpi-Seite rund 1 s."""
    if doc.xref_get_key(xref, "Filter")[0] != "null":
        return False
    roh = doc.xref_stream_raw(xref)
    doc.update_stream(xref, zlib.compress(roh, 6), compress=False)
    doc.xref_set_key(xref, "Filter", "/FlateDecode")
    doc.xref_set_key(xref, "DecodeParms", "null")
    return True


def _neu_kodieren(doc, xref, original: dict, qualitaet: int) -> bool:
    if doc.xref_get_key(xref, "Subtype")[1] != "/Image":
        return False
    filt = doc.xref_get_key(xref, "Filter")[1]
    if any(f in filt for f in VERLUSTBEHAFTET):
        return False                                        # schon kompakt
    bpc = doc.xref_get_key(xref, "BitsPerComponent")[1]
    maske = doc.xref_get_key(xref, "ImageMask")[1] == "true"
    if maske or bpc == "1":
        return _flate_packen(doc, xref)
    n = _komponenten(doc, xref)
    if (bpc != "8" or n is None or doc.xref_get_key(xref, "Decode")[0] != "null"
            or doc.xref_get_key(xref, "SMaskInData")[0] != "null"):
        return _flate_packen(doc, xref)
    pix = fitz.Pixmap(doc, xref)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    if pix.n != n or pix.width * pix.height < MIN_PIXEL_JPEG:
        return _flate_packen(doc, xref)
    original_filter = original.get("filter", "") or ""
    verlustbehaftet = any(f in original_filter for f in VERLUSTBEHAFTET)
    q = qualitaet
    if original.get("qualitaet"):
        q = max(JPEG_MIN_QUALITAET, min(qualitaet, int(original["qualitaet"])))
    jpeg = pix.tobytes("jpeg", jpg_quality=q)
    if not verlustbehaftet:
        # Vergleichsgröße: Länge des verlustfreien Originals (die geschwärzte Fassung packt sich ebenso),
        # sonst eine schnelle Schätzung (zlib-Stufe 1)
        flate = original.get("laenge") if "Flate" in original_filter else None
        if not flate:
            flate = len(zlib.compress(pix.samples, 1))
        if len(jpeg) > VERLUSTFREI_SCHWELLE * flate:
            return _flate_packen(doc, xref)
    doc.update_stream(xref, jpeg, compress=False)
    doc.xref_set_key(xref, "Filter", "/DCTDecode")
    doc.xref_set_key(xref, "DecodeParms", "null")
    doc.xref_set_key(xref, "BitsPerComponent", "8")
    return True


def bilder_neu_kodieren(doc, xrefs, qualitaet: int = JPEG_QUALITAET) -> int:
    """Kodiert durch apply_redactions geänderte Bilder wieder kompakt: Farbe/Graustufen (8 Bit) als JPEG
    (Qualität des Originals, höchstens `qualitaet`), 1-Bit-Bilder und Masken verlustfrei als Flate.
    Ursprünglich verlustfreie Bilder werden nur dann JPEG, wenn das deutlich kleiner ist.
    xrefs: Menge von xrefs oder dict {xref: Bildinfo des Originals} (aus geaenderte_bilder).
    Rückgabe: Anzahl neu kodierter Bilder."""
    if isinstance(xrefs, dict):
        eintraege = xrefs.items()
    else:                       # Original unbekannt: JPEG nur, wenn es deutlich kleiner ist als Flate
        eintraege = ((x, {}) for x in xrefs)
    anzahl = 0
    for xref, original in eintraege:
        try:
            if _neu_kodieren(doc, int(xref), original or {}, qualitaet):
                anzahl += 1
        except Exception:
            continue                                        # Bild bleibt wie es ist (unkomprimiert, aber geschwärzt)
    return anzahl


def nach_schwaerzung(doc, seite, vorher: dict, qualitaet: int = JPEG_QUALITAET) -> int:
    """Nach apply_redactions einer Seite: geänderte Bilder finden und neu kodieren."""
    geaendert = geaenderte_bilder(seite, vorher)
    return bilder_neu_kodieren(doc, geaendert, qualitaet) if geaendert else 0


# ----------------------------------------------------------------------
# Rückfall: Seite als Bild schwärzen (Befund R-08)
# ----------------------------------------------------------------------
BILDSEITE_DPI = 200           # Auflösung der als Bild geschwärzten Seite (Text bleibt für Menschen und KI lesbar)
BILDSEITE_MAX_PIXEL = 40_000_000
BILDSEITE_GRAU_TOLERANZ = 12  # Farbabstand, bis zu dem ein Pixel als grau gilt (Seite ohne Farbe -> Graustufen-PNG)


def _ohne_farbe(pix) -> bool:
    """Hat das RGB-Bild keine nennenswerte Farbe (Stichprobe)? Dann reicht ein Graustufenbild."""
    proben = pix.samples
    schritt = max(3, (len(proben) // 3 // 20000) * 3)
    for i in range(0, len(proben) - 2, schritt):
        r, g, b = proben[i], proben[i + 1], proben[i + 2]
        if max(r, g, b) - min(r, g, b) > BILDSEITE_GRAU_TOLERANZ:
            return False
    return True


def seite_als_bild_schwaerzen(doc, seite, fuellen, leeren=(), farbe=(0.92, 0.92, 0.92),
                              dpi: int = BILDSEITE_DPI) -> int:
    """Ersetzt den Inhalt der Seite durch ein Bild ihres sichtbaren Bereichs, in das die Rechtecke eingebrannt
    sind: `fuellen` in `farbe` (Schwärzungen), `leeren` weiß (ausgeblendete Inhalte). Rückfall, wenn MuPDF die
    Seite nicht schwärzen kann (zyklische oder zu tief verschachtelte Form-XObjects: "exception stack overflow",
    Befund R-08) – das Rendern kommt mit solchen Seiten zurecht. Inhalte außerhalb des sichtbaren Bereichs,
    Textebene, Anmerkungen und Schwärzungs-Anmerkungen der Seite entfallen. Rückgabe: xref des neuen Bilds.
    Ausnahmen (auch das Rendern scheitert) gehen an den Aufrufer – dann entsteht keine Ausgabe."""
    rect = fitz.Rect(seite.rect)
    flaeche = max(abs(rect), 1.0)
    dpi = min(dpi, int(72 * (BILDSEITE_MAX_PIXEL / flaeche) ** 0.5))
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    try:   # Zyklen im Strukturbaum lassen MuPDF 1.28 beim Rendern hängen; die Ausgabe trägt ohnehin keinen Strukturbaum
        katalog = doc.pdf_catalog()
        if doc.xref_get_key(katalog, "StructTreeRoot")[0] != "null":
            doc.xref_set_key(katalog, "StructTreeRoot", "null")
    except Exception:
        pass
    pix = seite.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False, annots=False)
    grau = tuple(int(round(255 * c)) for c in farbe)
    for liste, wert in ((leeren, (255, 255, 255)), (fuellen, grau)):
        for r in liste:
            r = fitz.Rect(r) & rect
            if r.is_empty:
                continue
            p = fitz.Rect(r.x0 - rect.x0, r.y0 - rect.y0, r.x1 - rect.x0, r.y1 - rect.y0) * matrix
            ir = fitz.IRect(int(p.x0) - 1 + pix.x, int(p.y0) - 1 + pix.y,          # Kanten sicher mitnehmen
                            int(p.x1 + 0.999) + 1 + pix.x, int(p.y1 + 0.999) + 1 + pix.y) & pix.irect
            if not ir.is_empty:
                pix.set_rect(ir, wert)
    if _ohne_farbe(pix):
        pix = fitz.Pixmap(fitz.csGRAY, pix)
        daten = pix.tobytes("png")
    else:
        daten = pix.tobytes("jpeg", jpg_quality=JPEG_QUALITAET)
    for annot in list(seite.annots()):
        try:
            seite.delete_annot(annot)
        except Exception:
            pass
    doc.xref_set_key(seite.xref, "Contents", "[]")
    doc.xref_set_key(seite.xref, "Resources", "<<>>")
    for schluessel in ("Annots", "Group", "Thumb", "PieceInfo"):
        doc.xref_set_key(seite.xref, schluessel, "null")
    return seite.insert_image(rect, stream=daten, keep_proportion=False)
