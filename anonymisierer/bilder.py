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
    nur_bildpixel_schwaerzen(doc, seite, rechtecke) -> int
        Bildpixel in den Rechtecken entfernen, ohne Text und Linien darüber anzutasten („Maximal“: Hintergrundbild).
    seite_als_bild_schwaerzen(doc, seite, fuellen, leeren=(), farbe=…, dpi=200) -> xref
        Rückfall, wenn apply_redactions an einer Seite scheitert (Befund R-08): Seite durch ein Bild mit
        eingebrannten Schwärzungen ersetzen.
    bild_leeren(doc, xref) -> bool              Bild durch ein weißes 1 x 1-Bild ersetzen
    erreichbare_bilder(doc, seite_xref) -> {xref: indirekt}   Bilder, die die Seite über ihre (auch geerbten)
        Ressourcen erreicht – auch über Form-XObjects, Kachelmuster, Type3-Schriften, weiche Masken, Anmerkungen
    gezeichnete_bilder(doc) -> (gezeichnet, unsicher, vollstaendig)   was die Seiten zeichnen
    bildreste_entfernen(doc) -> {"geleert", "geleert_alle", "unsicher", "rest"}   vor dem Speichern: Bilder, die keine
        Seite zeichnet (das ungeschwärzte Original in geerbten oder geteilten Ressourcen, ungenutzte Bilder), leeren
    bildreste_in_datei_entfernen(pfad, hilfspfad) -> dict   dasselbe als Netz in der gespeicherten Datei

Ablauf beim Aufrufer:  vorher = bildzustand(seite); seite.apply_redactions(...);
                       nach_schwaerzung(doc, seite, vorher)
                       … alle Seiten …; bildreste_entfernen(doc); doc.save(pfad, garbage=4)
                       bildreste_in_datei_entfernen(pfad, hilfspfad)
"""

import re
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


ZLIB_BLOCK = 1 << 22          # zlib arbeitet blockweise (4 MB): nie eine zweite volle Kopie der Pixel im Speicher
# Speicher (Befund 3 der Runde 3a, gemessen mit dem Kernel-Hochwasser VmHWM): Der JPEG-Kodierer von MuPDF schreibt
# progressiv und ohne Farbunterabtastung – er hält dafür alle DCT-Koeffizienten, 6 Byte je Pixel (48-MP-Foto: 288 MB)
# neben der Pixmap (3 Byte je Pixel). Größere Fotos (Handy mit 48, 50, 108 MP) werden deshalb nach dem Schwärzen mit
# höchstens so vielen Pixeln gespeichert – für jede Anzeige und jede KI mehr als genug (A4 mit 600 dpi: 35 MP; A3 mit
# 300 dpi, 17 MP, bleibt unverändert). Verlustfreie Originale behalten ihre Auflösung.
NEUKODIEREN_MAX_PIXEL = 24_000_000


def _zlib(daten, stufe: int) -> bytes:
    """zlib-Daten blockweise erzeugen (aus einem memoryview, ohne Kopie der Eingabe)."""
    packer = zlib.compressobj(stufe)
    mv = memoryview(daten)
    teile = [packer.compress(mv[i:i + ZLIB_BLOCK]) for i in range(0, len(mv), ZLIB_BLOCK)]
    teile.append(packer.flush())
    return b"".join(teile)


def flate_groesse(daten, grenze: float | None = None, stufe: int = 1) -> int:
    """Größe der zlib-Daten (Stufe 1: schnelle Schätzung), blockweise und ohne die Ausgabe zu behalten – der Speicher
    bleibt bei wenigen MB, auch für ein 48-MP-Foto. Mit grenze: Abbruch, sobald die Größe sie übersteigt (dann steht
    der Vergleich schon fest)."""
    packer = zlib.compressobj(stufe)
    mv = memoryview(daten)
    n = 0
    for i in range(0, len(mv), ZLIB_BLOCK):
        n += len(packer.compress(mv[i:i + ZLIB_BLOCK]))
        if grenze is not None and n > grenze:
            return n
    return n + len(packer.flush())


def _flate_packen(doc, xref) -> bool:
    """Unkomprimiertes Bild (1 Bit, oder nicht JPEG-geeignet) verlustfrei mit Flate packen. zlib-Stufe 6:
    update_stream(compress=True) nutzt die höchste Stufe und braucht für eine 300-dpi-Seite rund 1 s.
    Speicher: die Rohdaten liegen nur einmal vor – die Fassung im Dokument wird freigegeben, bevor gepackt wird."""
    if doc.xref_get_key(xref, "Filter")[0] != "null":
        return False
    roh = doc.xref_stream_raw(xref)
    doc.update_stream(xref, b"", compress=False)
    try:
        gepackt = _zlib(roh, 6)
    except BaseException:
        doc.update_stream(xref, roh, compress=False)        # Rohdaten zurück (Bild bleibt unkomprimiert)
        raise
    roh = None
    doc.update_stream(xref, gepackt, compress=False)
    doc.xref_set_key(xref, "Filter", "/FlateDecode")
    doc.xref_set_key(xref, "DecodeParms", "null")
    return True


def _nur_pixel(doc, xref, pix) -> bool:
    """Sind die Rohdaten des (unkomprimierten) Bilds genau die Pixel der Pixmap (8 Bit, ohne Zeilenauffüllung)? Nur
    dann darf sein Strom fürs Kodieren freigegeben und notfalls aus der Pixmap zurückgeschrieben werden."""
    try:
        laenge = int(doc.xref_get_key(xref, "Length")[1] or 0)
    except (TypeError, ValueError):
        return False
    return (doc.xref_get_key(xref, "Filter")[0] == "null" and pix.stride == pix.width * pix.n
            and laenge == pix.width * pix.height * pix.n)


def _pixel_zurueck(doc, xref, pix, flate: bool = False) -> None:
    """Die Pixel der Pixmap als Bilddaten von xref schreiben (unkomprimiert bzw. Flate, mit ihrer Breite und Höhe) –
    nachdem der Strom im Dokument für das Kodieren freigegeben wurde."""
    daten = getattr(pix, "samples_mv", None) or pix.samples
    if flate:
        doc.update_stream(xref, _zlib(daten, 6), compress=False)
        doc.xref_set_key(xref, "Filter", "/FlateDecode")
    else:
        doc.update_stream(xref, bytes(daten), compress=False)
        doc.xref_set_key(xref, "Filter", "null")
    doc.xref_set_key(xref, "DecodeParms", "null")
    doc.xref_set_key(xref, "Width", str(pix.width))
    doc.xref_set_key(xref, "Height", str(pix.height))


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
    # Speicher (gemessen mit VmHWM, Befund 3 der Runde 3a): erst MuPDFs Zwischenspeicher leeren – dort liegt noch das
    # dekodierte Original –, dann das neue Bild EINMAL dekodieren
    speicher_freigeben()
    pix = fitz.Pixmap(doc, xref)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    if pix.n != n or pix.width * pix.height < MIN_PIXEL_JPEG:
        pix = None
        return _flate_packen(doc, xref)
    original_filter = original.get("filter", "") or ""
    verlustbehaftet = any(f in original_filter for f in VERLUSTBEHAFTET)
    q = qualitaet
    if original.get("qualitaet"):
        q = max(JPEG_MIN_QUALITAET, min(qualitaet, int(original["qualitaet"])))
    # Die Pixel liegen jetzt zweimal vor: unkomprimiert im Dokument und in der Pixmap. Der Strom im Dokument wird
    # freigegeben, solange die Pixmap dieselben Pixel hält; scheitert etwas, werden sie zurückgeschrieben.
    frei = _nur_pixel(doc, xref, pix)
    if frei:
        speicher_freigeben()                                # das Bildobjekt im Zwischenspeicher hielte die Daten
        doc.update_stream(xref, b"", compress=False)
    try:
        if (frei and verlustbehaftet and pix.width * pix.height > NEUKODIEREN_MAX_PIXEL
                and doc.xref_get_key(xref, "SMask")[0] == "null" and doc.xref_get_key(xref, "Mask")[0] == "null"):
            faktor = (NEUKODIEREN_MAX_PIXEL / (pix.width * pix.height)) ** 0.5
            pix = fitz.Pixmap(pix, max(1, int(pix.width * faktor)), max(1, int(pix.height * faktor)), None)
        jpeg = pix.tobytes("jpeg", jpg_quality=q)
        if not verlustbehaftet:
            # Vergleichsgröße: Länge des verlustfreien Originals (die geschwärzte Fassung packt sich ebenso), sonst
            # eine schnelle Schätzung (zlib-Stufe 1, blockweise, Abbruch sobald der Vergleich feststeht)
            flate = original.get("laenge") if "Flate" in original_filter else None
            if not flate:
                flate = flate_groesse(getattr(pix, "samples_mv", None) or pix.samples,
                                      len(jpeg) / VERLUSTFREI_SCHWELLE)
            if len(jpeg) > VERLUSTFREI_SCHWELLE * flate:
                jpeg = None
                if frei:
                    _pixel_zurueck(doc, xref, pix, flate=True)
                    return True
                pix = None
                return _flate_packen(doc, xref)
    except BaseException:
        if frei:
            try:
                _pixel_zurueck(doc, xref, pix)
            except BaseException:
                bild_leeren(doc, xref)                      # nie ein Bild ohne Daten: lieber weiß als kaputt
        raise
    breite, hoehe = pix.width, pix.height
    pix = None
    doc.update_stream(xref, jpeg, compress=False)
    doc.xref_set_key(xref, "Filter", "/DCTDecode")
    doc.xref_set_key(xref, "DecodeParms", "null")
    doc.xref_set_key(xref, "BitsPerComponent", "8")
    doc.xref_set_key(xref, "Width", str(breite))
    doc.xref_set_key(xref, "Height", str(hoehe))
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
    for xref, original in eintraege:               # ein Bild nach dem anderen, Speicher dazwischen freigeben
        try:
            if _neu_kodieren(doc, int(xref), original or {}, qualitaet):
                anzahl += 1
        except Exception:
            continue                                        # Bild bleibt wie es ist (unkomprimiert, aber geschwärzt)
        finally:
            speicher_freigeben()
    return anzahl


def nach_schwaerzung(doc, seite, vorher: dict, qualitaet: int = JPEG_QUALITAET) -> int:
    """Nach apply_redactions einer Seite: geänderte Bilder finden und neu kodieren."""
    geaendert = geaenderte_bilder(seite, vorher)
    return bilder_neu_kodieren(doc, geaendert, qualitaet) if geaendert else 0


def nur_bildpixel_schwaerzen(doc, seite, rechtecke, qualitaet: int = JPEG_QUALITAET) -> int:
    """Bildpixel in den Rechtecken entfernen – OHNE Text und Linien anzutasten (Schutzstufe „Maximal“, Befund 5 der
    Runde 3a): ein Hintergrundbild, ein Wasserzeichen oder ein Formularhintergrund verschwindet, der Text darüber
    bleibt. Ein Bild, das ganz in einem Rechteck liegt, entfernt MuPDF vollständig, sonst nur die Pixel darin.
    Rückgabe: Anzahl neu kodierter Bilder. Ausnahmen (MuPDF scheitert an der Seite) gehen an den Aufrufer."""
    rechtecke = [fitz.Rect(r) & seite.rect for r in rechtecke]
    rechtecke = [r for r in rechtecke if not r.is_empty]
    if not rechtecke:
        return 0
    vorher = bildzustand(seite)
    for r in rechtecke:
        seite.add_redact_annot(r, fill=False)
    seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                           text=fitz.PDF_REDACT_TEXT_NONE)
    return nach_schwaerzung(doc, seite, vorher, qualitaet)


def bild_leeren(doc, xref: int) -> bool:
    """Ersetzt ein Bild-XObject durch ein weißes 1 x 1-Bild (Maske, Alternativbilder und Metadaten fallen weg)."""
    try:
        doc.update_stream(xref, b"\xff", compress=False)
        for schluessel, wert in (("Width", "1"), ("Height", "1"), ("BitsPerComponent", "8"),
                                 ("ColorSpace", "/DeviceGray")):
            doc.xref_set_key(xref, schluessel, wert)
        for schluessel in ("Filter", "DecodeParms", "SMask", "Mask", "Decode", "ImageMask", "Alternates",
                           "Metadata", "Intent", "Interpolate", "SMaskInData", "OC", "Name"):
            if doc.xref_get_key(xref, schluessel)[0] != "null":
                doc.xref_set_key(xref, schluessel, "null")
        return True
    except Exception:
        return False


LEER_MAX_BYTES = 64           # ein geleertes Bild (1 x 1) hat so viele Bytes Daten höchstens


def _ist_leer(doc, xref: int) -> bool:
    """Ist das Bild schon leer (1 x 1 Pixel und kaum Daten – ein größerer Strom könnte etwas anderes tragen)?"""
    try:
        return (int(doc.xref_get_key(xref, "Width")[1] or 0) <= 1 and int(doc.xref_get_key(xref, "Height")[1] or 0) <= 1
                and int(doc.xref_get_key(xref, "Length")[1] or 0) <= LEER_MAX_BYTES)
    except (TypeError, ValueError):
        return False


# ----------------------------------------------------------------------
# Bildreste (Befund 1 der Runde 3a): Originale in geerbten, geteilten oder ungenutzten Ressourcen
# ----------------------------------------------------------------------
# apply_redactions(images=PDF_REDACT_IMAGE_PIXELS) gibt der geschwärzten Seite ein EIGENES Ressourcen-Wörterbuch mit
# dem neuen, geschwärzten Bild. Erbt die Seite ihre Ressourcen vom Seitenbaum (/Pages) oder teilt sie das Wörterbuch
# mit anderen Seiten (LibreOffice hängt EIN Wörterbuch an alle Seiten und an den Seitenbaum), bleibt das ungeschwärzte
# Original dort verwiesen: save(garbage=4) behält es, jedes Programm kann es herausziehen, sichtbar ist es nirgends.
# Ebenso ein Original, das die Schwärzung ganz entfernt hat (vollständig abgedeckt), und mitgeschleppte, nie
# gezeichnete Bilder. Deshalb wird vor dem Speichern – und nach dem Speichern noch einmal in der geschriebenen Datei –
# jedes Bild geleert (weißes 1 x 1-Bild), das keine Seite zeichnet. Gezeichnet ist:
#   * was der Inhalt einer Seite mit dem Operator „Do“ aufruft, auch in Form-XObjects, samt Masken und
#     Alternativbildern (gelesen werden nur die Inhaltsströme, kein Bild wird dekodiert, kein Inhalt umgeschrieben);
#   * alles, was eine Seite über Kachelmuster, Type3-Schriften, Grafikzustände (weiche Masken) und Anmerkungen erreicht
#     – dort wird nicht nachgezählt: lieber stehen lassen als ein sichtbares Bild leeren („indirekt“).
SUCHE_GRENZE = 50_000         # so viele Objekte besucht die Suche je Seite höchstens (Schutz vor Riesendateien)
_REF_RE = re.compile(r"(\d+)\s+(\d+)\s+R(?![\w])")
_ALLE_REFS_RE = re.compile(r"(\d+)\s+\d+\s+R(?![\w])")
_KEINE_INHALTSOBJEKTE = ("/Page", "/Pages", "/Catalog", "/Annot", "/Metadata", "/OCG", "/OCMD", "/StructElem",
                         "/StructTreeRoot")
_SCHRIFTARTEN = ("/Type1", "/TrueType", "/Type0", "/CIDFontType0", "/CIDFontType2", "/MMType1", "/PS")
# „/Name Do“ im Inhaltsstrom: Name bis zum nächsten PDF-Leerraum oder Trennzeichen, dann der Operator
_REGULAER = rb"[^\x00\t\n\f\r /<>\[\]()%{}]"
_DO_RE = re.compile(rb"/(" + _REGULAER + rb"+)[\x00\t\n\f\r ]*Do(?!" + _REGULAER + rb")")
_NAME_ESCAPE_RE = re.compile(r"#([0-9A-Fa-f]{2})")


def _wert_ende(text: str, i: int) -> int:
    """Ende (exklusiv) des PDF-Werts, der bei text[i] beginnt (Wörterbuch, Feld, Zeichenkette, Name, Zahl, Verweis)."""
    n = len(text)
    if text.startswith("<<", i) or text[i] == "[":
        tiefe = 0
        while i < n:
            if text.startswith("<<", i):
                tiefe += 1
                i += 2
                continue
            if text.startswith(">>", i):
                tiefe -= 1
                i += 2
            elif text[i] == "[":
                tiefe += 1
                i += 1
            elif text[i] == "]":
                tiefe -= 1
                i += 1
            elif text[i] == "(":
                i = _wert_ende(text, i)
            elif text[i] == "<":
                ende = text.find(">", i)
                i = n if ende < 0 else ende + 1
            else:
                i += 1
            if tiefe == 0:
                return i
        return n
    if text[i] == "(":                                       # Zeichenkette mit Klammern und Escapes
        tiefe = 0
        while i < n:
            c = text[i]
            if c == "\\":
                i += 2
                continue
            if c == "(":
                tiefe += 1
            elif c == ")":
                tiefe -= 1
                if tiefe == 0:
                    return i + 1
            i += 1
        return n
    if text[i] == "<":                                       # Hex-Zeichenkette
        ende = text.find(">", i)
        return n if ende < 0 else ende + 1
    treffer = _REF_RE.match(text, i)
    if treffer:
        return treffer.end()
    j = i + 1
    while j < n and not text[j].isspace() and text[j] not in "/<>[]()":
        j += 1
    return j


def _eintraege(text: str) -> list:
    """[(Schlüssel, Werttext)] der obersten Ebene eines Wörterbuchs in PDF-Schreibweise (<</A 1 0 R/B<<…>>>>)."""
    text = (text or "").strip()
    if not text.startswith("<<"):
        return []
    aus = []
    i, n = 2, len(text) - 2
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        if text[i] != "/":
            i = _wert_ende(text, i)                          # unerwartet: Wert überspringen
            continue
        j = i + 1
        while j < n and not text[j].isspace() and text[j] not in "/<>[]()":
            j += 1
        name = text[i + 1:j]
        while j < n and text[j].isspace():
            j += 1
        if j >= n:
            break
        ende = _wert_ende(text, j)
        aus.append((name, text[j:ende].strip()))
        i = ende
    return aus


def _verweis(wert: str):
    treffer = _REF_RE.match((wert or "").strip())
    return int(treffer.group(1)) if treffer else None


def _name(text: str) -> str:
    """PDF-Name ohne #xx-Schreibweise (im Inhaltsstrom und im Wörterbuch gleich vergleichen)."""
    return _NAME_ESCAPE_RE.sub(lambda t: chr(int(t.group(1), 16)), text)


def _schluessel(doc, xref, pfad):
    try:
        return doc.xref_get_key(xref, pfad)
    except Exception:
        return ("null", "null")


def _objekttext(doc, xref, pfad) -> str:
    """Text des Werts unter pfad (Wörterbuch oder Feld; ein Verweis wird aufgelöst), sonst ""."""
    art, wert = _schluessel(doc, xref, pfad)
    if art == "xref":
        try:
            return doc.xref_object(int(wert.split()[0]), compressed=True)
        except Exception:
            return ""
    return wert if art in ("dict", "array") else ""


class _Bildsuche:
    """Bilder, die eine Seite über ihre Ressourcen erreicht: {xref: indirekt} – indirekt = True, wenn (auch) über ein
    Kachelmuster, eine Type3-Schrift, einen Grafikzustand oder eine Anmerkung (dort erreicht apply_redactions sie nicht,
    und ob sie gezeichnet werden, zählt bildreste_entfernen nicht nach). vollstaendig = False, wenn die Suche an
    SUCHE_GRENZE abgebrochen wurde."""

    def __init__(self, doc):
        self.doc = doc
        self.bilder: dict = {}
        self.gesehen: set = set()
        self.schritte = 0
        self.vollstaendig = True

    def ressourcen(self, halter: int, indirekt: bool) -> None:
        """Die Ressourcen des Objekts halter (Seite, Seitenbaum-Knoten, Form-XObject, Muster, Type3-Schrift)."""
        for kategorie in ("XObject", "Pattern", "Font", "ExtGState"):
            weiter = indirekt or kategorie != "XObject"
            for _name_, wert in _eintraege(_objekttext(self.doc, halter, "Resources/" + kategorie)):
                ref = _verweis(wert)
                if ref is not None:
                    self.objekt(ref, weiter)
                else:                          # direktes Wörterbuch (Grafikzustand mit weicher Maske, Schrift)
                    for x in _ALLE_REFS_RE.findall(wert):
                        self.objekt(int(x), True)

    def objekt(self, xref: int, indirekt: bool) -> None:
        if xref <= 0 or (xref, indirekt) in self.gesehen:
            return
        if self.schritte >= SUCHE_GRENZE:
            self.vollstaendig = False
            return
        self.gesehen.add((xref, indirekt))
        self.schritte += 1
        subtyp = _schluessel(self.doc, xref, "Subtype")[1]
        if subtyp == "/Image":
            self.bilder[xref] = self.bilder.get(xref, False) or indirekt
            for schluessel in ("SMask", "Mask"):           # Masken gehören zum Bild (nie einzeln leeren)
                art, wert = _schluessel(self.doc, xref, schluessel)
                if art == "xref":
                    self.objekt(int(wert.split()[0]), indirekt)
            for x in _ALLE_REFS_RE.findall(_objekttext(self.doc, xref, "Alternates")):
                self.objekt(int(x), indirekt)               # Alternativbilder (z. B. für den Druck)
            return
        if subtyp == "/Form":
            self.ressourcen(xref, indirekt)
            return
        if subtyp == "/Type3":
            self.ressourcen(xref, True)
            return
        if _schluessel(self.doc, xref, "PatternType")[1] == "1":     # Kachelmuster
            self.ressourcen(xref, True)
            return
        if subtyp in _SCHRIFTARTEN:
            return                                            # gewöhnliche Schrift: keine Bilder
        if _schluessel(self.doc, xref, "Type")[1] in _KEINE_INHALTSOBJEKTE:
            return
        # Grafikzustand (/Type ist dort freiwillig), weiche Maske, Schattierung, Alternativbild-Eintrag …: allen
        # Verweisen folgen – die Gruppe /G einer weichen Maske ist ein Form-XObject, das ein Bild zeichnen kann
        try:
            text = self.doc.xref_object(xref, compressed=True)
        except Exception:
            return
        for x in _ALLE_REFS_RE.findall(text):
            self.objekt(int(x), True)

    def anmerkungen(self, seite_xref: int) -> None:
        """Erscheinungsbilder (/AP) der Anmerkungen der Seite."""
        for x in _ALLE_REFS_RE.findall(_objekttext(self.doc, seite_xref, "Annots")):
            x = int(x)
            for y in _ALLE_REFS_RE.findall(_objekttext(self.doc, x, "AP")):
                self.objekt(int(y), True)
            if _schluessel(self.doc, x, "Subtype")[1] == "/Form":    # Verweis aus einer direkt eingetragenen Anmerkung
                self.objekt(x, True)


def ressourcen_halter(doc, seite_xref: int):
    """xref des Objekts, dessen /Resources für die Seite gelten: die Seite selbst oder der nächste Knoten des
    Seitenbaums, von dem sie sie erbt; None, wenn es keine gibt."""
    x, gesehen = seite_xref, set()
    while x and x not in gesehen and len(gesehen) < 64:
        gesehen.add(x)
        try:
            if doc.xref_get_key(x, "Resources")[0] != "null":
                return x
            art, wert = doc.xref_get_key(x, "Parent")
        except Exception:
            return None
        if art != "xref":
            return None
        x = int(wert.split()[0])
    return None


def _erreichbar(doc, seite_xref: int) -> tuple:
    suche = _Bildsuche(doc)
    halter = ressourcen_halter(doc, seite_xref)
    if halter is not None:
        suche.ressourcen(halter, False)
    suche.anmerkungen(seite_xref)
    return suche.bilder, suche.vollstaendig


def erreichbare_bilder(doc, seite_xref: int) -> dict:
    """{xref: indirekt} aller Bild-XObjects, die die Seite über ihre (auch geerbten) Ressourcen erreicht – auch über
    Form-XObjects, Kachelmuster, Type3-Schriften, weiche Masken und Anmerkungen, auch ungenutzte. indirekt = True,
    wenn das Bild (auch) in einem Kachelmuster, einer Type3-Schrift, einem Grafikzustand oder einer Anmerkung liegt
    (apply_redactions erreicht es dort nicht)."""
    return _erreichbar(doc, seite_xref)[0]


def _xobjekte(doc, halter: int) -> dict:
    """{Name: xref} des XObject-Wörterbuchs in den Ressourcen von halter."""
    aus = {}
    for name, wert in _eintraege(_objekttext(doc, halter, "Resources/XObject")):
        ref = _verweis(wert)
        if ref is not None:
            aus[_name(name)] = ref
    return aus


def _aufgerufen(doc, seite) -> set:
    """Bild-XObjects, die der Inhalt der Seite mit „Do“ aufruft – auch in (verschachtelten) Form-XObjects; ein Form-
    XObject ohne eigene Ressourcen nutzt die des Aufrufers. Ausnahmen (unlesbarer Inhalt) gehen an den Aufrufer."""
    bilder: set = set()
    stapel = [(seite.read_contents() or b"", ressourcen_halter(doc, seite.xref), 0)]
    gesehen: set = set()
    while stapel:
        daten, halter, tiefe = stapel.pop()
        if halter is None or not daten:
            continue
        namen = {_name(n.decode("latin-1")) for n in _DO_RE.findall(daten)}
        if not namen:
            continue
        xobjekte = _xobjekte(doc, halter)
        for name in namen:
            x = xobjekte.get(name)
            if x is None or (x, halter) in gesehen:
                continue
            gesehen.add((x, halter))
            subtyp = doc.xref_get_key(x, "Subtype")[1]
            if subtyp == "/Image":
                bilder.add(x)
            elif subtyp == "/Form" and tiefe < 64:
                eigen = x if doc.xref_get_key(x, "Resources")[0] != "null" else halter
                stapel.append((doc.xref_stream(x) or b"", eigen, tiefe + 1))
    return bilder


def _mit_masken(doc, xrefs) -> set:
    """xrefs samt Masken (SMask, Mask) und Alternativbildern."""
    aus, stapel = set(xrefs), list(xrefs)
    while stapel:
        x = stapel.pop()
        dazu = [_schluessel(doc, x, s) for s in ("SMask", "Mask")]
        weitere = [int(w.split()[0]) for art, w in dazu if art == "xref"]
        weitere += [int(y) for y in _ALLE_REFS_RE.findall(_objekttext(doc, x, "Alternates"))]
        for y in weitere:
            if y not in aus and _schluessel(doc, y, "Subtype")[1] == "/Image":
                aus.add(y)
                stapel.append(y)
    return aus


def alle_bilder(doc) -> list:
    """xrefs aller Bild-XObjects der Datei – gezeichnet oder nicht."""
    aus = []
    for x in range(1, doc.xref_length()):
        if _schluessel(doc, x, "Subtype")[1] == "/Image":
            aus.append(x)
    return aus


def gezeichnet_auf_seite(doc, seite) -> tuple:
    """(gezeichnet, suche_vollstaendig, inhalt_lesbar): die Bilder, die die Seite zeichnet – was ihr Inhalt mit „Do“
    aufruft und was sie indirekt erreicht (Kachelmuster, Type3-Schriften, Grafikzustände, Anmerkungen), mit Masken.
    Ist der Inhalt unlesbar, zählt alles, was die Seite erreicht; ist die Suche abgebrochen, ist auch das
    unvollständig."""
    erreichbar, vollstaendig = _erreichbar(doc, seite.xref)
    if not erreichbar:
        return set(), vollstaendig, True
    gezeichnet = {x for x, indirekt in erreichbar.items() if indirekt}
    lesbar = True
    try:
        gezeichnet.update(x for x in _aufgerufen(doc, seite) if x in erreichbar)
    except Exception:
        lesbar = False
        gezeichnet.update(erreichbar)              # Inhalt unlesbar: alles stehen lassen, was die Seite erreicht
    return _mit_masken(doc, gezeichnet), vollstaendig, lesbar


def gezeichnete_bilder(doc) -> tuple:
    """(gezeichnet, unsicher, vollstaendig): die Bilder, die irgendeine Seite zeichnet (siehe oben; mit Masken), die
    Seiten (0-basiert), deren Inhalt oder Ressourcen sich nicht vollständig lesen ließen (dort zählt alles als
    gezeichnet, was die Seite erreicht), und ob die Prüfung vollständig ist (sonst darf nichts geleert werden: was eine
    Seite zeichnet, ist unbekannt)."""
    gezeichnet: set = set()
    unsicher: list = []
    vollstaendig = True
    for nr in range(len(doc)):
        try:
            bilder, voll, lesbar = gezeichnet_auf_seite(doc, doc[nr])
        except Exception:
            unsicher.append(nr)
            vollstaendig = False
            continue
        gezeichnet |= bilder
        if not (voll and lesbar):
            unsicher.append(nr)
        vollstaendig = vollstaendig and voll
    return gezeichnet, unsicher, vollstaendig


def _verwiesen(doc) -> set:
    """xrefs, die vom Trailer aus über Verweise erreichbar sind – was save(garbage) behält (verwaiste Objekte, etwa das
    Original eines Bilds mit seiteneigenen Ressourcen nach apply_redactions, fallen beim Speichern ohnehin weg)."""
    try:
        stapel = [int(x) for x in _ALLE_REFS_RE.findall(doc.pdf_trailer(compressed=True))]
    except Exception:
        return set()
    aus: set = set()
    while stapel:
        x = stapel.pop()
        if x <= 0 or x in aus or x >= doc.xref_length():
            continue
        aus.add(x)
        try:
            stapel += [int(y) for y in _ALLE_REFS_RE.findall(doc.xref_object(x, compressed=True))]
        except Exception:
            continue
    return aus


def bildreste_entfernen(doc) -> dict:
    """Vor dem Speichern, in jeder Schutzstufe (und als Netz in der gespeicherten Datei): jedes Bild, das keine Seite
    zeichnet, wird geleert – das ungeschwärzte Original in geerbten oder geteilten Ressourcen (auch eines, das
    apply_redactions ganz entfernt hat), ungenutzt mitgeschleppte Bilder. Sichtbar ändert sich nichts.
    Rückgabe: {"geleert": Anzahl geleerter Bilder, die die Datei sonst behalten hätte (verwaiste zählen nicht),
    "geleert_alle": Anzahl aller geleerten, "unsicher": Seiten, deren Inhalt oder Ressourcen sich nicht vollständig
    prüfen ließen (dort kann ein nicht angezeigtes Bild stehen bleiben), "rest": [(xref, Breite, Höhe)] nicht
    angezeigter Bilder, die stehen geblieben sind}."""
    gezeichnet, unsicher, vollstaendig = gezeichnete_bilder(doc)
    kandidaten = [x for x in alle_bilder(doc) if x not in gezeichnet and not _ist_leer(doc, x)]
    befund = {"geleert": 0, "geleert_alle": 0, "unsicher": sorted(set(unsicher)), "rest": []}
    if not kandidaten:
        return befund
    if not vollstaendig:                       # was die Seiten zeichnen, ist nicht sicher bekannt: nichts leeren
        befund["rest"] = [_masse(doc, x) for x in kandidaten]
        return befund
    verwiesen = _verwiesen(doc)
    for x in kandidaten:
        if bild_leeren(doc, x):
            befund["geleert_alle"] += 1
            befund["geleert"] += int(x in verwiesen)
        else:
            befund["rest"].append(_masse(doc, x))
    return befund


def _masse(doc, xref: int) -> tuple:
    try:
        return (xref, int(doc.xref_get_key(xref, "Width")[1] or 0), int(doc.xref_get_key(xref, "Height")[1] or 0))
    except (TypeError, ValueError):
        return (xref, 0, 0)


def bildreste_in_datei_entfernen(pfad, hilfspfad) -> dict:
    """Netz nach dem Speichern: dieselbe Prüfung in der geschriebenen Datei. Steckt dort noch ein Bild, das keine Seite
    zeichnet, wird es geleert und die Datei über hilfspfad neu geschrieben (garbage=4) und ersetzt.
    Rückgabe wie bildreste_entfernen; Ausnahmen gehen an den Aufrufer."""
    import os
    with fitz.open(pfad) as d:
        befund = bildreste_entfernen(d)
        if not befund["geleert_alle"]:
            return befund
        d.save(hilfspfad, garbage=4, deflate=True)
    os.replace(hilfspfad, pfad)
    return befund


# ----------------------------------------------------------------------
# Beschädigte Bilder (Gutachten R-07): abgebrochene JPEGs – auch progressive
# ----------------------------------------------------------------------
SCHADEN_ABBRUCH = "bricht mitten im Bild ab"
SCHADEN_PROGRESSIV = "unvollständig übertragen, überall unscharf"
SCHADEN_DEKODIEREN = "lässt sich nicht dekodieren"
DEKODIER_WARNUNG_RE = re.compile(r"(?i)premature end|corrupt|truncat|padding|unexpected end|not enough data|"
                                 r"bad (?:huffman|data|code|marker)|jpeg error|jbig2|jpx|invalid")
KANTE_ZEILEN = 24             # so viele Zeilen über der Abbruchkante werden auf Tinte geprüft
VERKLEINERT_AB_PIXEL = 16_000_000  # größere JPEGs (Handyfotos ab 16 MP) werden verkleinert dekodiert (DCT-Skalierung
                                   # von MuPDF): ein 48-MP-Foto kostet sonst rund 150 MB, so rund 40 MB. Warnungen und
                                   # Füllfläche bleiben; Scans (300 dpi A4: 8,7 MP) werden weiter voll dekodiert
VERKLEINERT_MAX_KANTE = 4000  # längste Kante des verkleinert dekodierten Bilds (Pixel)
FUELL_ZEILEN = 8              # so viele einheitliche Zeilen unten (in voller Auflösung) sind eine Füllfläche
_SOF_MARKER = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
_SOF_PROGRESSIV = {0xC2, 0xC6, 0xCA, 0xCE}


def jpeg_struktur(daten: bytes):
    """Aufbau eines JPEG aus seinen Markern (ohne zu dekodieren): {"progressiv", "komponenten", "scans": [(Komponenten,
    Ss, Se, Ah, Al)], "ende": bool (EOI-Marker vorhanden)} – None, wenn es kein JPEG ist. Bricht ein Segmentkopf ab,
    endet die Liste der Scans dort (der Rest fehlt)."""
    if not daten or not daten.startswith(b"\xff\xd8"):
        return None
    n = len(daten)
    aus = {"progressiv": False, "komponenten": [], "scans": [], "ende": False}
    i = 2
    while i + 1 < n:
        if daten[i] != 0xFF:
            i = daten.find(b"\xff", i)
            if i < 0:
                break
            continue
        marker = daten[i + 1]
        if marker == 0xFF:                              # Füllbyte
            i += 1
            continue
        if marker == 0xD9:
            aus["ende"] = True
            break
        if marker in (0x00, 0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if i + 4 > n:
            break
        laenge = int.from_bytes(daten[i + 2:i + 4], "big")
        if laenge < 2 or i + 2 + laenge > n:
            break                                       # Segment abgeschnitten
        segment = daten[i + 4:i + 2 + laenge]
        if marker in _SOF_MARKER and len(segment) >= 6:
            aus["progressiv"] = marker in _SOF_PROGRESSIV
            anzahl = segment[5]
            aus["komponenten"] = [segment[6 + 3 * k] for k in range(anzahl) if 6 + 3 * k < len(segment)]
        elif marker == 0xDA and segment:
            anzahl = segment[0]
            if len(segment) < 4 + 2 * anzahl:
                break
            komponenten = [segment[1 + 2 * k] for k in range(anzahl)]
            ss, se, a = segment[1 + 2 * anzahl], segment[2 + 2 * anzahl], segment[3 + 2 * anzahl]
            aus["scans"].append((komponenten, ss, se, a >> 4, a & 0x0F))
            # Bilddaten des Scans überspringen: bis zum nächsten echten Marker (nicht FF00, nicht RSTn)
            j = i + 2 + laenge
            while True:
                j = daten.find(b"\xff", j)
                if j < 0 or j + 1 >= n:
                    j = n
                    break
                folge = daten[j + 1]
                if folge == 0x00 or 0xD0 <= folge <= 0xD7:
                    j += 2
                    continue
                if folge == 0xFF:
                    j += 1
                    continue
                break
            i = j
            continue
        i += 2 + laenge
    return aus


def progressiv_unvollstaendig(daten: bytes) -> bool:
    """Ist ein progressives JPEG unvollständig übertragen? Seine Scans müssen jeden Koeffizienten (0-63) jeder
    Komponente bis zur vollen Genauigkeit (Al = 0) liefern; fehlen spätere Scans (Datei abgeschnitten), zeigt MuPDF das
    Bild überall unscharf – ohne die einheitliche Füllfläche, an der ein abgebrochenes Baseline-JPEG zu erkennen ist.
    Fehlt nur die Endmarke, ist das Bild vollständig (False)."""
    struktur = jpeg_struktur(daten)
    if not struktur or not struktur["progressiv"] or not struktur["komponenten"]:
        return False
    stand = {k: [None] * 64 for k in struktur["komponenten"]}
    for komponenten, ss, se, _ah, al in struktur["scans"]:
        for k in komponenten:
            if k in stand:
                for c in range(min(ss, 63), min(se, 63) + 1):
                    stand[k][c] = al
    return any(wert != 0 for werte in stand.values() for wert in werte)


def _warnungen_zuruecksetzen():
    """MuPDF unterdrückt eine Warnung, die genauso lautet wie die vorige („… repeated 2 times“) – nach einem anderen
    beschädigten Bild käme „premature end of file in jpeg“ sonst nicht mehr an. Deshalb erst MuPDFs Gedächtnis leeren,
    dann die gesammelten Warnungen."""
    try:
        fitz.mupdf.fz_flush_warnings()
    except Exception:
        pass
    try:
        fitz.TOOLS.reset_mupdf_warnings()
    except Exception:
        pass


def _warnungen() -> str:
    try:
        return fitz.TOOLS.mupdf_warnings() or ""
    except Exception:
        return ""


def kante_mit_tinte(pix, min_flach: int = FUELL_ZEILEN) -> bool:
    """Bricht das Bild unten ab (MuPDF füllt fehlende Daten mit einer einheitlichen Fläche, z. B. Grau 128 oder der
    letzten Farbe) und liegt direkt über der Kante Tinte – eine halb sichtbare Zeile, die die OCR nicht liest, ein Mensch
    oder eine Bild-KI aber schon? Ein vollständiges Bild, dem nur die Endmarke fehlt, hat unten keine solche Fläche."""
    try:
        if pix.colorspace is not None and pix.colorspace.n != 1:
            pix = fitz.Pixmap(fitz.csGRAY, pix)
        elif pix.alpha:
            pix = fitz.Pixmap(pix, 0)
        breite, hoehe, n = pix.width, pix.height, pix.n
        daten = pix.samples_mv if hasattr(pix, "samples_mv") else pix.samples
    except Exception:
        return False
    zeile = breite * n
    if hoehe < 16 or zeile <= 0:
        return False
    flach = 0
    for y in range(hoehe - 1, -1, -1):
        z = bytes(daten[y * zeile:(y + 1) * zeile])
        if z.count(z[:1]) != len(z):
            break
        flach += 1
    if flach < min_flach or flach >= hoehe:
        return False                      # keine Füllfläche – oder gar nichts sichtbar
    ende = hoehe - flach
    band = bytes(daten[max(0, ende - KANTE_ZEILEN) * zeile:ende * zeile])
    dunkel = len(band) - len(band.translate(None, bytes(range(128))))
    return dunkel > 0.002 * len(band)


def _verkleinert_dekodieren(roh: bytes, breite: int, hoehe: int):
    """Ein (großes) JPEG über eine Hilfsseite verkleinert dekodieren: MuPDF liest dabei alle Daten (Warnungen wie beim
    vollen Dekodieren), legt aber nur ein kleines Bild an. Graustufen-Pixmap."""
    faktor = max(1.0, max(breite, hoehe) / VERKLEINERT_MAX_KANTE)
    hilfe = fitz.open()
    try:
        s = hilfe.new_page(width=max(1.0, breite / faktor), height=max(1.0, hoehe / faktor))
        s.insert_image(s.rect, stream=roh, keep_proportion=False)
        return s.get_pixmap(colorspace=fitz.csGRAY, alpha=False, annots=False)
    finally:
        hilfe.close()


def bild_beschaedigt(doc, xref: int, filter_name: str = ""):
    """Beschreibung des Schadens eines Bild-XObjects oder None. Ein progressives JPEG, dem spätere Scans fehlen, ist
    beschädigt (überall unscharf – was die OCR darin nicht liest, kann ein Mensch oder eine KI womöglich erahnen); ein
    Bild, das mitten im Bild abbricht und über der Kante Tinte zeigt, ebenso; eines, das sich nicht dekodieren lässt,
    auch. Große JPEGs werden verkleinert dekodiert, gespeicherte Dekodierungen danach freigegeben (Speicher)."""
    filt = str(filter_name or "")
    try:
        if not filt:
            filt = doc.xref_get_key(xref, "Filter")[1] or ""
        breite = int(doc.xref_get_key(xref, "Width")[1] or 0)
        hoehe = int(doc.xref_get_key(xref, "Height")[1] or 0)
    except (ValueError, TypeError):
        breite = hoehe = 0
    nur_dct = "DCTDecode" in filt and "Flate" not in filt and "LZW" not in filt and "ASCII" not in filt
    roh = None
    if nur_dct:
        try:
            roh = doc.xref_stream_raw(xref)
        except Exception:
            roh = None
        if roh is not None and progressiv_unvollstaendig(roh):
            return SCHADEN_PROGRESSIV
    _warnungen_zuruecksetzen()
    pix = None
    faktor = 1.0
    try:
        if roh is not None and breite * hoehe > VERKLEINERT_AB_PIXEL:
            faktor = max(1.0, max(breite, hoehe) / VERKLEINERT_MAX_KANTE)
            pix = _verkleinert_dekodieren(roh, breite, hoehe)
        else:
            pix = fitz.Pixmap(doc, xref)
    except Exception:
        return SCHADEN_DEKODIEREN
    finally:
        roh = None
    try:
        if not DEKODIER_WARNUNG_RE.search(_warnungen()):
            return None
        return SCHADEN_ABBRUCH if kante_mit_tinte(pix, max(3, int(round(FUELL_ZEILEN / faktor)))) else None
    finally:
        pix = None
        speicher_freigeben()


def speicher_freigeben() -> None:
    """MuPDFs Zwischenspeicher dekodierter Bilder leeren (große Fotos belegen sonst bis zum Programmende Speicher)."""
    try:
        fitz.TOOLS.store_shrink(100)
    except Exception:
        pass


# ----------------------------------------------------------------------
# Rückfall: Seite als Bild schwärzen (Befund R-08)
# ----------------------------------------------------------------------
BILDSEITE_DPI = 200           # Auflösung der als Bild geschwärzten Seite (Text bleibt für Menschen und KI lesbar)
BILDSEITE_MAX_PIXEL = 40_000_000
BILDSEITE_MIN_DPI = 72        # Untergrenze, wenn die Seite selbst grob gerastert ist (nie hochrechnen, Speicher)
BILDSEITE_GRAU_TOLERANZ = 12  # Farbabstand, bis zu dem ein Pixel als grau gilt (Seite ohne Farbe -> Graustufen-PNG)


def _quell_aufloesung(seite) -> float | None:
    """Auflösung (dpi) der Seite, wenn sie nur aus Bildern besteht (kein Text): die höchste effektive Auflösung ihrer
    Bilder – feiner zu rendern zeigt nichts mehr, kostet aber Speicher. None bei Text oder ohne Bilder."""
    try:
        if seite.get_text("words"):
            return None
        hoechste = 0.0
        for info in seite.get_image_info():
            r = fitz.Rect(info["bbox"])
            if r.width > 1 and r.height > 1:
                hoechste = max(hoechste, 72.0 * info["width"] / r.width, 72.0 * info["height"] / r.height)
        return hoechste or None
    except Exception:
        return None


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
    quelle = _quell_aufloesung(seite)
    if quelle:                  # nie hochrechnen: eine Bildseite mit 100 dpi wird mit 100 dpi neu erzeugt (Speicher)
        dpi = min(dpi, max(BILDSEITE_MIN_DPI, quelle))
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
