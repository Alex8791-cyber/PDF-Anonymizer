"""Bewertung: Pipeline wie die Oberfläche laufen lassen und die AUSGABE über alle Kanäle prüfen.

Ablauf je Dokument (BENCHMARK_SCHEMA.md):
    aktive = alle Kategorien mit standard_an=True; NIE-/IMMER-Liste leer; alle Funde angehakt
    erg = analysiere_pdf(pdf, aktive, [], [], ocr=dienst)          (ein OcrDienst je Lauf)
    out = schwaerze_pdf(pdf, erg["funde"], ocr=dienst, ocr_cache=erg["ocr_cache"], ziel_ordner=tmp)

Geprüft wird die Ausgabedatei (nicht die Fundliste) über diese Kanäle:
    text        PyMuPDF-Textebene jeder Seite (inkl. unsichtbarem Text)
    formular    Werte verbliebener Formularfelder
    anmerkung   Inhalte/Autoren verbliebener Anmerkungen
    metadaten   Info-Dictionary und XMP
    lesezeichen Titel der Lesezeichen
    anhang      Namen und Inhalte eingebetteter Dateien
    rohdaten    alle Objekte und dekomprimierten Ströme (doc.xref_stream), Zeichenketten dekodiert
    dateiname   Name der Ausgabedatei
    ocr         OCR der gerenderten Ausgabeseite bei Scan-Seiten: Tesseract in PyMuPDF mit den
                Sprachdaten des Repos (DIESELBE Engine wie das Programm!) und – wo vorhanden – die
                Tesseract-Kommandozeile als zweite, unabhängigere Leseart
    pixel       Pixelvergleich Original/Ausgabe an den Wortrechtecken der Wahrheit (nur Scans;
                unabhängig von jeder OCR: Stehen dort noch die Original-Pixel, ist der Text lesbar)

Kennzahlen je Eintrag mit erwartung=schwaerzen:
    leck       der normalisierte Volltext steht noch in einem Kanal (Pixel: alle Wörter sichtbar)
    teilweise  kein Volltreffer, aber ein signifikantes Token steht noch auf derselben Seite
    entfernt   sonst
Restrisiko (zweite Verteidigungslinie, Vertrag Abschnitt 7) – je Dokument werden der Status der Ausgabe
("fertig"/"pruefen" aus schwaerze_pdf, sonst aus dem Namen _PRUEFEN) und die Verdachtsstellen festgehalten:
    stille Lecks          Kern-Einträge mit Status leck/teilweise in Dokumenten, deren Ausgabe NICHT _PRUEFEN ist
                          (ohne Ausgabe zählt als nicht _PRUEFEN) – diese Zahl muss 0 werden
    Verdachtsabdeckung    Anteil der Kern-Einträge mit leck/teilweise, die ein Verdacht überdeckt: Rechteck des
                          Verdachts schneidet ein Wortrechteck des Eintrags (gleiche Seite), Verdachtstext und
                          Eintrag überlappen (gefaltet, an Wortgrenzen) oder teilen ein signifikantes Token auf
                          derselben Seite; ein Seitenverdacht ohne Rechteck deckt seine ganze Seite ab
    Fehlverdacht je Seite Verdachtsstellen, die keinen zu schwärzenden Eintrag (Kern oder erweitert) überdecken,
                          im Mittel je Seite
    _PRUEFEN ohne Leck    Dokumente mit Ausgabe _PRUEFEN, in denen kein Kern-Eintrag geleckt ist
    nur Pixelrest         Teil-Lecks, die NUR der Pixelvergleich sieht und deren Wörter alle unter der Sichtbarkeits-
                          schwelle liegen (auf Scans oft Unterstreichung/Schräglage im Wortrechteck statt lesbarer
                          Reste): die Abdeckung wird zusätzlich ohne sie berichtet
Gezählt werden die Verdachtsstellen der Restrisiko-Prüfung und – wie in der Vorschau der Oberfläche – die von der
Selbstkontrolle gemeldeten Reste mit ihrer Lage (gui_attrappen.reste_als_verdacht).
Normalisierung siehe normalisierung.py (Schema-Normalisierung + Diakritika-Faltung + Wortgrenzen).
Mehrdeutigkeit: Kommt ein Wert/Token im ORIGINAL auch außerhalb der Einträge vor (z. B. ein Ortsname im
Briefkopf des Versicherers), zählt erst ein Vorkommen ÜBER dieser Grundzahl als Rest.
"""

import difflib
import importlib
import inspect
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

try:
    import numpy as np
except ImportError:
    np = None

from .normalisierung import Gefaltet, signifikante_token, token

SICHTBAR_SCHWELLE = 0.55      # Anteil unveränderter Tintenpixel, ab dem ein Wort als lesbar gilt
TEILWEISE_SCHWELLE = 0.30     # darunter gilt ein Wort als entfernt
PIXEL_DPI = 100
OCR_DPI = 300
SEITENKANAELE = ("text", "formular", "anmerkung")
DOKUMENTKANAELE = ("metadaten", "lesezeichen", "anhang", "rohdaten", "dateiname")


# ----------------------------------------------------------------------
# Pipeline laden (auch aus einem anderen Checkout)
# ----------------------------------------------------------------------
def _liegt_in(datei, ordner: Path) -> bool:
    """Liegt `datei` unterhalb von `ordner`? (Groß-/Kleinschreibung wie das Betriebssystem)"""
    d = os.path.normcase(str(Path(datei).resolve()))
    o = os.path.normcase(str(Path(ordner).resolve()))
    return d == o or d.startswith(o.rstrip("\\/") + os.sep)


class Pipeline:
    """Die Programmfunktionen aus einem Repository-Pfad (Standard: dieses Repository)."""

    def __init__(self, repo: Path | None = None):
        self.repo = Path(repo).resolve() if repo else Path(__file__).resolve().parents[2]
        if str(self.repo) not in sys.path:
            sys.path.insert(0, str(self.repo))
        vorhanden = sys.modules.get("anonymisierer")
        if vorhanden is not None and getattr(vorhanden, "__file__", None):
            if not _liegt_in(vorhanden.__file__, self.repo):
                raise RuntimeError(f"Paket 'anonymisierer' ist schon aus {vorhanden.__file__} geladen – "
                                   f"für --repo bitte einen eigenen Prozess verwenden.")
        try:
            self.muster = importlib.import_module("anonymisierer.muster")
            if not _liegt_in(self.muster.__file__, self.repo):
                # sonst würde still der Code eines anderen Checkouts (dieses Benchmarks) gemessen
                raise ImportError(f"Paket 'anonymisierer' nicht in {self.repo}")
            self.analyse = importlib.import_module("anonymisierer.analyse")
            self.schwaerzung = importlib.import_module("anonymisierer.schwaerzung")
            try:
                self.ocr_modul = importlib.import_module("anonymisierer.ocr")
            except ImportError:
                self.ocr_modul = None
            self.analysiere_pdf = self.analyse.analysiere_pdf
            self.schwaerze_pdf = self.schwaerzung.schwaerze_pdf
            self.kategorien = self.muster.KATEGORIEN
            try:   # Reste der Selbstkontrolle mit Lage (wie die Vorschau der Oberfläche sie zeigt)
                self.reste_als_verdacht = getattr(importlib.import_module("anonymisierer.gui_attrappen"),
                                                  "reste_als_verdacht", None)
            except Exception:
                self.reste_als_verdacht = None
        except ImportError:                          # ältere Programmversion (eine Datei)
            pa = importlib.import_module("pdf_anonymisierer")
            if not _liegt_in(pa.__file__, self.repo):
                raise RuntimeError(f"Weder 'anonymisierer' noch 'pdf_anonymisierer.py' in {self.repo} gefunden")
            self.ocr_modul = None
            self.reste_als_verdacht = None
            self.analysiere_pdf = pa.analysiere_pdf
            self.schwaerze_pdf = pa.schwaerze_pdf
            self.kategorien = pa.KATEGORIEN
        self.commit = _git_commit(self.repo)

    def aktive(self) -> set:
        return {k[0] for k in self.kategorien if k[4]}

    def ocr_dienst(self):
        if self.ocr_modul is not None and hasattr(self.ocr_modul, "OcrDienst"):
            try:
                return self.ocr_modul.OcrDienst()
            except Exception:
                return None
        return None

    def tessdata(self) -> str | None:
        if self.ocr_modul is not None and hasattr(self.ocr_modul, "_tessdata_finden"):
            try:
                return self.ocr_modul._tessdata_finden()
            except Exception:
                pass
        kandidat = self.repo / "tessdata"
        return str(kandidat) if any(kandidat.glob("*.traineddata")) else None


def _git_commit(repo: Path) -> str | None:
    try:
        aus = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=10)
        return aus.stdout.strip() or None
    except Exception:
        return None


def _rufe(funktion, *args, **kwargs):
    """Wie die Oberfläche: unbekannte Schlüsselwort-Argumente weglassen (ältere Versionen)."""
    try:
        parameter = inspect.signature(funktion).parameters
    except (TypeError, ValueError):
        return funktion(*args, **kwargs)
    if any(p.kind is p.VAR_KEYWORD for p in parameter.values()):
        return funktion(*args, **kwargs)
    return funktion(*args, **{k: v for k, v in kwargs.items() if k in parameter})


# ----------------------------------------------------------------------
# PDF-Zeichenketten aus Rohdaten
# ----------------------------------------------------------------------
_LITERAL_RE = re.compile(rb"\((?:[^()\\]|\\.|\((?:[^()\\]|\\.)*\))*\)", re.S)
_HEX_RE = re.compile(rb"<([0-9A-Fa-f\s]{4,})>")
_TJ_RE = re.compile(rb"\[((?:[^\]\\]|\\.)*)\]\s*TJ", re.S)


def _literal_dekodieren(roh: bytes) -> bytes:
    inhalt = roh[1:-1]
    aus = bytearray()
    i = 0
    while i < len(inhalt):
        c = inhalt[i]
        if c == 0x5C and i + 1 < len(inhalt):            # Backslash
            n = inhalt[i + 1]
            if n in b"01234567":
                j = i + 1
                ziffern = b""
                while j < len(inhalt) and len(ziffern) < 3 and inhalt[j] in b"01234567":
                    ziffern += bytes([inhalt[j]])
                    j += 1
                aus.append(int(ziffern, 8) & 0xFF)
                i = j
                continue
            aus += {ord("n"): b"\n", ord("r"): b"\r", ord("t"): b"\t", ord("b"): b"\b", ord("f"): b"\f"}.get(n, bytes([n]))
            i += 2
            continue
        aus.append(c)
        i += 1
    return bytes(aus)


def _zeichenkette_als_text(b: bytes) -> str | None:
    """Eine PDF-Zeichenkette als Text – oder None für Glyphen-Nummern (Identity-H: Bytepaare mit
    Nullbytes, keine Zeichen; als Text gelesen ergäben sie zufällige Buchstabenfolgen)."""
    if b.startswith((b"\xfe\xff", b"\xff\xfe")):
        return _bytes_als_text(b)
    if b"\x00" in b:
        return None
    return _bytes_als_text(b)


def _bytes_als_text(b: bytes) -> str:
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be", "replace")
    if b.startswith(b"\xff\xfe"):
        return b[2:].decode("utf-16-le", "replace")
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8", "replace")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252", "replace")


def zeichenketten(daten: bytes) -> list:
    """Alle PDF-Zeichenketten (Literal und Hex) eines Objekts/Stroms als Text; TJ-Felder werden
    ohne Trenner zusammengesetzt ('[(Muster) 20 (mann)] TJ' -> 'Mustermann')."""
    texte = []
    for tj in _TJ_RE.finditer(daten):
        teile = [_zeichenkette_als_text(_literal_dekodieren(m.group(0))) for m in _LITERAL_RE.finditer(tj.group(1))]
        teile = [x for x in teile if x is not None]
        if teile:
            texte.append("".join(teile))
    for m in _LITERAL_RE.finditer(daten):
        text = _zeichenkette_als_text(_literal_dekodieren(m.group(0)))
        if text is not None:
            texte.append(text)
    for m in _HEX_RE.finditer(daten):
        hexa = re.sub(rb"\s", b"", m.group(1))
        if len(hexa) % 2:
            hexa += b"0"
        try:
            text = _zeichenkette_als_text(bytes.fromhex(hexa.decode()))
        except ValueError:
            continue
        if text is not None:
            texte.append(text)
    return texte


def _rohdaten(doc) -> str:
    """Alle Objekte und dekomprimierten Ströme (ohne Bild-, Schrift- und Querverweisströme)."""
    teile = []
    for xref in range(1, doc.xref_length()):
        try:
            objekt = doc.xref_object(xref, compressed=False) or ""
        except Exception:
            continue
        teile.extend(zeichenketten(objekt.encode("latin-1", "replace")))
        if not doc.xref_is_stream(xref):
            continue
        if re.search(r"/Subtype\s*/(Image|Type1C|CIDFontType0C|OpenType)|/Length[123]\b|/Type\s*/(XRef|ObjStm)", objekt):
            continue
        try:
            strom = doc.xref_stream(xref) or b""
        except Exception:
            continue
        if len(strom) > 8_000_000:
            continue
        teile.extend(zeichenketten(strom))
        if b"<?xpacket" in strom or b"<x:xmpmeta" in strom or not re.search(rb"[\x00-\x08\x0e-\x1f]", strom[:2000]):
            teile.append(_bytes_als_text(strom))
    return "\n".join(teile)


# ----------------------------------------------------------------------
# Kanäle eines PDFs
# ----------------------------------------------------------------------
class Kanaele:
    """Alle Textkanäle eines PDFs (Original oder Ausgabe) in gefalteter Form."""

    def __init__(self, pdf: Path, dateiname: str | None = None):
        doc = fitz.open(pdf)
        try:
            self.seiten = len(doc)
            self.seitentext = []
            self.formular = []
            self.anmerkung = []
            self.woerter = []
            for page in doc:
                self.seitentext.append(page.get_text("text"))
                self.woerter.append([tuple(w[:5]) for w in page.get_text("words")])
                werte = []
                try:
                    for w in page.widgets():
                        werte += [str(w.field_value or ""), str(w.field_name or ""), str(getattr(w, "field_label", "") or "")]
                        werte += [str(x) for x in (w.choice_values or [])]
                except Exception:
                    pass
                self.formular.append("\n".join(werte))
                notizen = []
                try:
                    for a in page.annots():
                        info = a.info or {}
                        notizen += [info.get("content", ""), info.get("title", ""), info.get("subject", "")]
                except Exception:
                    pass
                self.anmerkung.append("\n".join(notizen))
            meta = doc.metadata or {}
            self.metadaten = "\n".join(str(v) for v in meta.values() if v) + "\n" + (doc.get_xml_metadata() or "")
            try:
                self.lesezeichen = "\n".join(str(t[1]) for t in doc.get_toc(simple=True))
            except Exception:
                self.lesezeichen = ""
            anh = []
            try:
                for i in range(doc.embfile_count()):
                    info = doc.embfile_info(i)
                    anh += [str(info.get("name", "")), str(info.get("filename", "")), str(info.get("ufilename", "")),
                            str(info.get("desc", ""))]
                    anh.append(_bytes_als_text(doc.embfile_get(i)))
            except Exception:
                pass
            self.anhang = "\n".join(anh)
            self.rohdaten = _rohdaten(doc)
        finally:
            doc.close()
        self.dateiname = dateiname if dateiname is not None else Path(pdf).name
        self._cache: dict = {}
        self.ocr: dict = {}          # Seite (1-basiert) -> {"pymupdf": str, "tesseract": str}

    def gefaltet(self, kanal: str, seite: int | None = None) -> Gefaltet:
        """Gefalteter Text eines Kanals (seite=None: alle Seiten zusammen)."""
        schluessel = (kanal, seite)
        if schluessel not in self._cache:
            if kanal in SEITENKANAELE:
                liste = getattr(self, "seitentext" if kanal == "text" else kanal)
                text = "\n".join(liste) if seite is None else (liste[seite - 1] if 0 < seite <= len(liste) else "")
            elif kanal.startswith("ocr_"):
                art = kanal[4:]
                if seite is None:
                    text = "\n".join(v.get(art, "") for v in self.ocr.values())
                else:
                    text = self.ocr.get(seite, {}).get(art, "")
            else:
                text = getattr(self, kanal)
            self._cache[schluessel] = Gefaltet(text)
        return self._cache[schluessel]

    def kanalnamen(self) -> list:
        namen = list(SEITENKANAELE) + list(DOKUMENTKANAELE)
        arten = sorted({a for v in self.ocr.values() for a in v})
        return namen + [f"ocr_{a}" for a in arten]


# ----------------------------------------------------------------------
# OCR der Ausgabe (Bewertungs-OCR)
# ----------------------------------------------------------------------
_VOKALE = set("aeiouyäöüáéíóúàèìòùâêîôû")


def _plausibel(text: str) -> float:
    woerter = re.findall(r"\S+", text)
    if not woerter:
        return 0.0
    gut = 0
    for w in woerter:
        kern = w.strip(".,;:!?()[]\"'„“»«-/")
        if re.fullmatch(r"[\d.,:/\-]+", kern) and kern:
            gut += 1
        elif kern.isalpha() and len(kern) >= 2 and any(c in _VOKALE for c in kern.lower()):
            gut += 1
    return gut / len(woerter)


def _pixmap_ocr(page, winkel: int, sprache: str, tessdata: str) -> str:
    matrix = fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72).prerotate(winkel)
    pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
    pix.set_dpi(OCR_DPI, OCR_DPI)
    daten = pix.pdfocr_tobytes(compress=False, language=sprache, tessdata=tessdata)
    with fitz.open("pdf", daten) as d:
        return d[0].get_text("text")


def ocr_pymupdf(page, tessdata: str | None) -> tuple:
    """OCR einer Seite mit dem in PyMuPDF eingebauten Tesseract; Ausrichtung wird über die
    Plausibilität bestimmt (0°, sonst 180/90/270). Liefert (Text, Winkel)."""
    if not tessdata:
        return "", 0
    sprache = "deu" if (Path(tessdata) / "deu.traineddata").exists() else "eng"
    beste = ("", 0, -1.0)
    for winkel in (0, 180, 90, 270):
        try:
            text = _pixmap_ocr(page, winkel, sprache, tessdata)
        except Exception:
            continue
        q = _plausibel(text)
        if q > beste[2]:
            beste = (text, winkel, q)
        if q >= 0.6 or (winkel == 0 and not text.strip()):
            break
    return beste[0], beste[1]


def tesseract_cli() -> str | None:
    return shutil.which("tesseract")


def _cli_tessdata() -> str | None:
    for kandidat in (os.environ.get("BENCHMARK_TESSDATA"), "/usr/share/tesseract-ocr/5/tessdata",
                     "/usr/share/tesseract-ocr/4.00/tessdata", "/usr/share/tessdata"):
        if kandidat and (Path(kandidat) / "deu.traineddata").exists():
            return kandidat
    return None


def ocr_cli(page, winkel: int, arbeitsordner: Path) -> str:
    """Zweite Leseart mit der Tesseract-Kommandozeile (eigene Installation, eigener Build)."""
    programm = tesseract_cli()
    if not programm:
        return ""
    matrix = fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72).prerotate(winkel)
    bild = arbeitsordner / f"ocr_{os.getpid()}_{page.number}.png"
    page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY, alpha=False).save(bild)
    befehl = [programm, str(bild), "stdout", "-l", "deu", "--psm", "3"]
    td = _cli_tessdata()
    if td:
        befehl[1:1] = ["--tessdata-dir", td]
    try:
        aus = subprocess.run(befehl, capture_output=True, text=True, timeout=300, errors="replace")
        return aus.stdout
    except Exception:
        return ""
    finally:
        try:
            bild.unlink()
        except OSError:
            pass


# ----------------------------------------------------------------------
# Pixelvergleich
# ----------------------------------------------------------------------
def _graubild(page):
    pix = page.get_pixmap(dpi=PIXEL_DPI, colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def _tintenschwelle(region) -> int:
    """Grauwert, unter dem ein Pixel als Tinte gilt – relativ zum Papierton (Median), damit auch
    blasse Schrift auf schlechten Scans (120 dpi, Unschärfe) zählt."""
    return min(200, int(np.median(region)) - 45)


def wort_sichtbarkeit(original, ausgabe, rechteck) -> float | None:
    """Anteil der Tintenpixel des Originals im Wortrechteck, die in der Ausgabe unverändert
    dunkel sind (1.0 = Wort unverändert lesbar, ~0 = entfernt). None = keine Tinte gefunden."""
    if np is None:
        return None
    s = PIXEL_DPI / 72.0
    x0, y0, x1, y1 = [int(round(v * s)) for v in rechteck[:4]]
    x0, y0 = max(0, x0 - 1), max(0, y0 - 1)
    h = min(original.shape[0], ausgabe.shape[0])
    b = min(original.shape[1], ausgabe.shape[1])
    x1, y1 = min(b, x1 + 2), min(h, y1 + 2)
    if x1 <= x0 or y1 <= y0:
        return None
    o = original[y0:y1, x0:x1].astype(np.int16)
    a = ausgabe[y0:y1, x0:x1].astype(np.int16)
    schwelle = _tintenschwelle(o)
    tinte = o < schwelle
    if tinte.sum() < 3:
        return None
    unveraendert = tinte & (a < schwelle) & (np.abs(a - o) < 60)
    return float(unveraendert.sum() / tinte.sum())


# ----------------------------------------------------------------------
# Wahrheit lesen und prüfen
# ----------------------------------------------------------------------
def lade_wahrheiten(korpus: Path) -> list:
    aus = []
    for datei in sorted(Path(korpus).glob("*.wahrheit.json")):
        w = json.loads(datei.read_text(encoding="utf-8"))
        w["_pfad"] = Path(korpus) / w["dokument"]
        aus.append(w)
    return aus


def pruefe_wahrheit(pdf: Path, wahrheit: dict) -> list:
    """Plausibilität der Wahrheit gegen das ORIGINAL: Jeder Eintrag muss in seinem Kanal stehen
    (Text-/Formular-Einträge in der Textebene seiner Seite, Scan-Einträge als Tinte in den Wortrechtecken)."""
    probleme = []
    k = Kanaele(pdf)
    doc = fitz.open(pdf)
    bilder = {}
    try:
        for e in wahrheit["eintraege"]:
            nadel = Gefaltet(e["text"])
            kanal = e["kanal"]
            if kanal in ("text", "formular"):
                if not k.gefaltet("text", e["seite"]).enthaelt(nadel):
                    probleme.append(f"{e['id']}: '{e['text']}' nicht in der Textebene von Seite {e['seite']}")
            elif kanal == "scan":
                if np is None:
                    continue
                if e["seite"] not in bilder:
                    bilder[e["seite"]] = _graubild(doc[e["seite"] - 1])
                bild = bilder[e["seite"]]
                for w in e.get("woerter", []):
                    if not any(c.isalnum() for c in w[4]):
                        continue                  # Satzzeichen allein ("/") tragen nichts bei
                    s = PIXEL_DPI / 72.0
                    x0, y0, x1, y1 = [int(round(v * s)) for v in w[:4]]
                    region = bild[max(0, y0 - 1):max(0, y1) + 2, max(0, x0 - 1):max(0, x1) + 2]
                    if region.size == 0 or (region < _tintenschwelle(region)).sum() < 2:
                        probleme.append(f"{e['id']}: keine Tinte im Wortrechteck von '{w[4]}' (Seite {e['seite']})")
            elif kanal in ("anmerkung", "metadaten", "lesezeichen", "anhang"):
                if not k.gefaltet(kanal).enthaelt(nadel) and not k.gefaltet("text").enthaelt(nadel):
                    probleme.append(f"{e['id']}: '{e['text']}' nicht im Kanal {kanal}")
            elif kanal == "dateiname":
                if not Gefaltet(Path(pdf).name).enthaelt(nadel):
                    probleme.append(f"{e['id']}: '{e['text']}' nicht im Dateinamen")
    finally:
        doc.close()
    return probleme


def _scan_seiten(pdf: Path, wahrheit: dict) -> set:
    """Seiten, auf denen OCR-Kontrolle nötig ist: Seiten mit Scan-Einträgen und bildlastige Seiten."""
    seiten = {e["seite"] for e in wahrheit["eintraege"] if e["kanal"] == "scan"}
    with fitz.open(pdf) as doc:
        for i, page in enumerate(doc):
            try:
                flaeche = abs(page.rect) or 1.0
                bild = sum(abs(fitz.Rect(b["bbox"]) & page.rect) for b in page.get_image_info())
                if bild >= 0.5 * flaeche and len(page.get_text("text").strip()) < 200:
                    seiten.add(i + 1)
            except Exception:
                pass
    return seiten


# ----------------------------------------------------------------------
# Bewertung eines Dokuments
# ----------------------------------------------------------------------
def _grundzahl(original: Kanaele, kanal: str, seite, nadel: Gefaltet, eintraege: list) -> int:
    """Vorkommen von `nadel` im Original-Kanal, die NICHT zu einem zu schwärzenden Eintrag gehören."""
    im_original = original.gefaltet(kanal, seite).zaehle(nadel)
    if not im_original:
        return 0
    in_eintraegen = 0
    for e in eintraege:
        if e["erwartung"] != "schwaerzen":
            continue
        if seite is not None and e["seite"] != seite:
            continue
        in_eintraegen += Gefaltet(e["text"]).zaehle(nadel)
    return max(0, im_original - in_eintraegen)


def _grund_kanal(original: Kanaele, kanal: str, seite, nadel: Gefaltet, eintraege: list) -> int:
    """Grundzahl je Kanal: Rohdaten enthalten jeden Text mehrfach (Inhaltsstrom, Feldwert,
    Erscheinungsbild) – dort zählt als Grundzahl die des sichtbaren Texts. OCR-Kanäle haben eine
    Grundzahl nur, wenn auch das Original per OCR gelesen wurde (Scans ohne Wortrechtecke)."""
    if kanal == "rohdaten":
        return _grundzahl(original, "text", seite, nadel, eintraege)
    if kanal.startswith("ocr_"):
        return _grundzahl(original, "ocr_pymupdf", seite, nadel, eintraege) if original.ocr else 0
    return _grundzahl(original, kanal, seite, nadel, eintraege)


def _erkannt(e_text: str, funde_gefaltet: list, scan: bool = False) -> str:
    """Hat die Analyse den Eintrag gefunden? voll = Fund mit genau diesem Text; teil = nur Teile
    (z. B. Nachname ohne Vorname); umfassend = nur ein längerer Fund enthält ihn (dieser Wert wird
    an anderen Stellen dann nicht gesucht); nein = kein Fund."""
    nadel = Gefaltet(e_text)
    if not nadel.kette:
        return "nein"
    teil = umfassend = False
    for g in funde_gefaltet:
        if not g.kette:
            continue
        if g.kette == nadel.kette:
            return "voll"
        if nadel.enthaelt(g):
            teil = True
        elif g.enthaelt(nadel):
            umfassend = True
    if teil or umfassend:
        return "teil" if teil else "umfassend"
    if scan and len(nadel.kette) >= 5:
        # OCR-Verleser: ein Fund, der dem gedruckten Wert sehr ähnlich ist ("Mustermarm")
        for g in funde_gefaltet:
            if g.kette and abs(len(g.kette) - len(nadel.kette)) <= 3 and \
                    difflib.SequenceMatcher(None, g.kette, nadel.kette).ratio() >= 0.8:
                return "aehnlich"
    return "nein"


def _am_ort(e: dict, aus: "Kanaele", sichtbar: list) -> str | None:
    """Steht der Eintrag noch an SEINER Stelle? voll | teil | weg (None = nicht bestimmbar).
    Textseiten: Wörter der Ausgabe, deren Mitte in einem Wortrechteck des Eintrags liegt;
    Scans: Pixelvergleich; Nebenkanäle: der eigene Kanal."""
    kanal = e["kanal"]
    nadel = Gefaltet(e["text"])
    tokens = signifikante_token(e["text"])
    if kanal in ("metadaten", "lesezeichen", "anhang", "dateiname"):
        g = aus.gefaltet(kanal)
        if g.enthaelt(nadel):
            return "voll"
        return "teil" if any(g.enthaelt(Gefaltet(t_)) for t_ in tokens) else "weg"
    if kanal == "anmerkung":
        g = aus.gefaltet("anmerkung")
        if g.enthaelt(nadel) or aus.gefaltet("text", e["seite"]).enthaelt(nadel):
            return "voll"
        return "weg"
    if sichtbar:
        if all(a >= SICHTBAR_SCHWELLE for _, a in sichtbar):
            return "voll"
        return "teil" if any(a >= TEILWEISE_SCHWELLE for _, a in sichtbar) else "weg"
    if kanal == "scan" or not e.get("woerter"):
        return None
    seite = e["seite"]
    if not (0 < seite <= len(aus.woerter)):
        return None
    kaesten = [fitz.Rect(w[:4]) + (-1, -1, 1, 1) for w in e["woerter"]]
    gefunden = [w for w in aus.woerter[seite - 1]
                if any(k.contains(fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)) for k in kaesten)]
    if not gefunden:
        return "weg"
    g = Gefaltet(" ".join(w[4] for w in gefunden))
    if g.enthaelt(nadel, grenzen_pruefen=False):
        return "voll"
    return "teil" if any(g.enthaelt(Gefaltet(t_)) for t_ in tokens) else "weg"


def bewerte_dokument(pdf: Path, wahrheit: dict, pipeline: Pipeline, dienst, ziel: Path, arbeitsordner: Path,
                     cli_ocr: bool = True, pixel: bool = True) -> dict:
    """Pipeline ausführen und die Ausgabe gegen die Wahrheit prüfen."""
    ergebnis = {"dokument": wahrheit["dokument"], "typ": wahrheit.get("typ"), "merkmale": wahrheit.get("merkmale", []),
                "seiten": wahrheit.get("seiten"), "fehler": None, "warnungen": [], "ausgabe": None,
                "keine_ausgabe": False}
    aktive = pipeline.aktive()
    t0 = time.perf_counter()
    try:
        erg = _rufe(pipeline.analysiere_pdf, pdf, aktive, [], [], ocr=dienst)
    except Exception as fehler:  # Programmfehler gehören ins Ergebnis, nicht in einen Abbruch
        erg = {"funde": [], "warnungen": [], "fehler": f"Analyse-Ausnahme: {type(fehler).__name__}: {fehler}",
               "ocr_cache": {}}
    t1 = time.perf_counter()
    funde = list(erg.get("funde") or [])
    try:
        out = _rufe(pipeline.schwaerze_pdf, pdf, funde, ocr=dienst, ocr_cache=erg.get("ocr_cache"), ziel_ordner=ziel)
    except Exception as fehler:
        out = {"ausgabe": None, "treffer": 0, "warnungen": [], "reste": [],
               "fehler": f"Schwärzungs-Ausnahme: {type(fehler).__name__}: {fehler}"}
    t2 = time.perf_counter()
    ergebnis.update({
        "dauer_analyse_s": round(t1 - t0, 2), "dauer_schwaerzung_s": round(t2 - t1, 2),
        "funde_anzahl": len(funde), "treffer": out.get("treffer"), "reste": out.get("reste", []),
        "fehler": erg.get("fehler") or out.get("fehler"), "ocr_seiten_programm": erg.get("ocr_seiten", 0),
        "warnungen": list(erg.get("warnungen") or []) + list(out.get("warnungen") or [])})
    ausgabe = Path(out["ausgabe"]) if out.get("ausgabe") else None
    ergebnis.update(_status_und_verdacht(out, ausgabe, pipeline))
    if ausgabe is None or not ausgabe.exists():
        # Keine Ausgabe = nichts wurde geschwärzt: das Original gilt als „Ausgabe“ (vorsichtige Wertung)
        ergebnis["keine_ausgabe"] = True
        ausgabe = Path(pdf)
        ausgabe_name = Path(pdf).name
    else:
        ausgabe_name = ausgabe.name
        ergebnis["ausgabe"] = str(ausgabe)
    t3 = time.perf_counter()
    original = Kanaele(pdf)
    aus = Kanaele(ausgabe, dateiname=ausgabe_name)
    # OCR der Scan-Seiten der Ausgabe (Bewertungs-OCR)
    scan_seiten = _scan_seiten(pdf, wahrheit)
    tessdata = pipeline.tessdata()
    ohne_kasten = {e["seite"] for e in wahrheit["eintraege"] if e["kanal"] == "scan" and not e.get("woerter")}
    with fitz.open(ausgabe) as doc_aus, fitz.open(pdf) as doc_orig:
        for s in sorted(scan_seiten):
            if s > len(doc_aus):
                continue
            text, winkel = ocr_pymupdf(doc_aus[s - 1], tessdata)
            eintrag = {"pymupdf": text}
            if cli_ocr and tesseract_cli():
                eintrag["tesseract"] = ocr_cli(doc_aus[s - 1], winkel, arbeitsordner)
            aus.ocr[s] = eintrag
            if s in ohne_kasten:                   # Grundzahl für Token: OCR auch vom Original
                otext, _ = ocr_pymupdf(doc_orig[s - 1], tessdata)
                original.ocr[s] = {"pymupdf": otext}
        bilder = {}
        if pixel and np is not None:
            for s in {e["seite"] for e in wahrheit["eintraege"] if e["kanal"] == "scan" and e.get("woerter")}:
                if s <= len(doc_aus) and s <= len(doc_orig):
                    bilder[s] = (_graubild(doc_orig[s - 1]), _graubild(doc_aus[s - 1]))
    eintraege = wahrheit["eintraege"]
    funde_gefaltet = [Gefaltet(f.get("text", "")) for f in funde]
    kanalnamen = aus.kanalnamen()
    bewertete = []
    for e in eintraege:
        nadel = Gefaltet(e["text"])
        r = {"id": e["id"], "text": e["text"], "kategorie": e["kategorie"], "seite": e["seite"],
             "erwartung": e["erwartung"], "umfang": e.get("umfang", "kern"), "kanal": e["kanal"],
             "bemerkung": e.get("bemerkung", "")}
        # Pixel je Wort
        sichtbar = []
        if e["kanal"] == "scan" and e.get("woerter") and e["seite"] in bilder:
            orig_bild, aus_bild = bilder[e["seite"]]
            for w in e["woerter"]:
                if not any(c.isalnum() for c in w[4]):
                    continue
                anteil = wort_sichtbarkeit(orig_bild, aus_bild, w)
                if anteil is not None:
                    sichtbar.append((w[4], anteil))
        if e["erwartung"] == "behalten":
            r.update(_behalten_pruefen(e, nadel, original, aus, sichtbar))
            r["verursacht_von"] = [f.get("text") for f in funde if _ueberlappt(Gefaltet(f.get("text", "")), nadel)][:3]
            bewertete.append(r)
            continue
        # 1) Volltreffer in irgendeinem Kanal
        lecks = []
        for kanal in kanalnamen:
            anzahl = aus.gefaltet(kanal).zaehle(nadel)
            if anzahl and anzahl > _grund_kanal(original, kanal, None, nadel, eintraege):
                lecks.append(kanal)
        if sichtbar and all(a >= SICHTBAR_SCHWELLE for _, a in sichtbar):
            lecks.append("pixel")
        # 2) signifikante Token auf derselben Seite
        reste = []
        if not lecks:
            reste = _token_reste(e, original, aus, sichtbar, eintraege)
        if lecks:
            status = "leck"
        elif reste:
            status = "teilweise"
        else:
            status = "entfernt"
        erk = _erkannt(e["text"], funde_gefaltet, scan=e["kanal"] == "scan")
        ort = _am_ort(e, aus, sichtbar)
        r.update({"status": status, "kanaele": lecks, "reste": reste, "erkannt": erk, "am_ort": ort,
                  "pixel": [[t, round(a, 2)] for t, a in sichtbar] if sichtbar else None})
        if status != "entfernt":
            r["diagnose"] = _diagnose(status, lecks, reste, erk, e, ort)
        bewertete.append(r)
    t4 = time.perf_counter()
    # Fehlalarme: Funde, die mit keinem zu schwärzenden Eintrag überlappen (Enthaltensein an
    # Wortgrenzen oder ein gemeinsames signifikantes Token – z. B. "Horváth, Anton" aus zwei
    # Vorstandsnamen ist kein Fehlalarm, sondern eine falsche Gruppierung echter Namen)
    schwaerzen = [(Gefaltet(e["text"]), set(signifikante_token(e["text"])))
                  for e in eintraege if e["erwartung"] == "schwaerzen"]
    behalten = [(Gefaltet(e["text"]), set(signifikante_token(e["text"])))
                for e in eintraege if e["erwartung"] == "behalten"]
    fehlalarme = []
    for f in funde:
        g = Gefaltet(f.get("text", ""))
        if not g.kette:
            continue
        tok = set(signifikante_token(f.get("text", "")))
        if any(_ueberlappt(g, s) or (tok & st) for s, st in schwaerzen):
            continue
        schaedlich = any(_ueberlappt(g, b) or (tok & bt) for b, bt in behalten)
        fehlalarme.append({"text": f.get("text"), "kategorie": f.get("kategorie"), "trifft_kontext": schaedlich})
    verdacht_bewerten(ergebnis, bewertete, eintraege)
    ergebnis.update({"eintraege": bewertete, "fehlalarme": fehlalarme, "dauer_bewertung_s": round(t4 - t3, 2),
                     "funde": [{"kategorie": f.get("kategorie"), "text": f.get("text"), "seiten": f.get("seiten")}
                               for f in funde],
                     "ocr_seiten_bewertung": sorted(aus.ocr), "pixel_seiten": sorted(bilder)})
    return ergebnis


def _verdacht_feld(v, name, standard=None):
    if isinstance(v, dict):
        return v.get(name, standard)
    return getattr(v, name, standard)


def verdacht_serialisieren(v) -> dict:
    """Verdacht (NamedTuple des Programms oder dict) -> JSON-taugliches dict (Rechtecke als [x0, y0, x1, y1])."""
    rechtecke = []
    for r in _verdacht_feld(v, "rechtecke") or []:
        try:
            rechtecke.append([round(float(x), 2) for x in fitz.Rect(r)])
        except Exception:
            continue
    seite = _verdacht_feld(v, "seite")
    start = _verdacht_feld(v, "start", -1)
    return {"seite": int(seite) if seite is not None else None, "start": -1 if start is None else int(start),
            "ende": int(_verdacht_feld(v, "ende", -1) or -1), "text": str(_verdacht_feld(v, "text", "") or ""),
            "grund": str(_verdacht_feld(v, "grund", "") or ""), "rechtecke": rechtecke}


def _status_und_verdacht(out: dict, ausgabe, pipeline) -> dict:
    """Status der Ausgabe ("fertig"/"pruefen"; ältere Programmversionen ohne "status": aus dem Namen) und die
    Verdachtsstellen (Restrisiko-Prüfung + Reste der Selbstkontrolle mit Lage, wie die Vorschau sie zeigt)."""
    status = out.get("status")
    if ausgabe is None or not Path(ausgabe).exists():
        status = None
    elif status not in ("fertig", "pruefen") or "_PRUEFEN" in Path(ausgabe).name.upper():
        status = "pruefen" if "_PRUEFEN" in Path(ausgabe).name.upper() else "fertig"
    verdacht = [verdacht_serialisieren(v) for v in out.get("verdacht") or []]
    reste_verdacht = []
    if out.get("reste") and ausgabe is not None and Path(ausgabe).exists() \
            and getattr(pipeline, "reste_als_verdacht", None) is not None:
        try:
            reste_verdacht = [verdacht_serialisieren(v)
                              for v in pipeline.reste_als_verdacht(ausgabe, out["reste"], out.get("verdacht") or [])]
        except Exception:
            reste_verdacht = []
    return {"status_ausgabe": status, "verdacht": verdacht, "reste_verdacht": reste_verdacht,
            "dauer_restrisiko_s": out.get("dauer_restrisiko_s")}


def _verdacht_trifft(v: dict, e: dict, kasten: list, nadel: Gefaltet, tokens: set) -> bool:
    """Überdeckt der Verdacht v den Eintrag e (Wortrechtecke der Wahrheit in `kasten`)?"""
    seite = v.get("seite")
    gleiche_seite = seite is not None and int(seite) + 1 == e["seite"]
    if gleiche_seite and not v.get("rechtecke") and int(v.get("start", 0) or 0) < 0:
        return True                              # Seitenverdacht ("Seite selbst durchsehen")
    if gleiche_seite and kasten:
        for r in v.get("rechtecke") or []:
            rv = fitz.Rect(r)
            for k in kasten:
                if rv.intersects(k) and abs(rv & k) > 0.15 * min(abs(k) or 1.0, abs(rv) or 1.0):
                    return True
    if _ueberlappt(Gefaltet(v.get("text", "")), nadel):
        return True
    return bool(gleiche_seite and tokens and tokens & set(signifikante_token(v.get("text", ""))))


def verdacht_bewerten(ergebnis: dict, bewertete: list, wahrheit_eintraege: list) -> None:
    """Je zu schwärzendem Eintrag "verdacht_abgedeckt", je Verdacht "trifft" (überdeckt er einen zu schwärzenden
    Eintrag, Kern oder erweitert?) – Grundlage für Verdachtsabdeckung und Fehlverdacht."""
    verdacht = list(ergebnis.get("verdacht") or []) + list(ergebnis.get("reste_verdacht") or [])
    wahrheit = {w["id"]: w for w in wahrheit_eintraege}
    vorbereitet = []
    for r in bewertete:
        if r.get("erwartung") != "schwaerzen":
            continue
        w = wahrheit.get(r["id"], {})
        kasten = [fitz.Rect(x[:4]) for x in w.get("woerter") or [] if any(c.isalnum() for c in str(x[4]))]
        vorbereitet.append((r, kasten, Gefaltet(r["text"]), set(signifikante_token(r["text"]))))
    for v in verdacht:
        v["trifft"] = any(_verdacht_trifft(v, r, kasten, nadel, tokens) for r, kasten, nadel, tokens in vorbereitet)
    for r, kasten, nadel, tokens in vorbereitet:
        r["verdacht_abgedeckt"] = any(_verdacht_trifft(v, r, kasten, nadel, tokens) for v in verdacht)


def _ueberlappt(a: Gefaltet, b: Gefaltet) -> bool:
    """Textüberlappung (normalisiert): einer enthält den anderen an Wortgrenzen."""
    if not a.kette or not b.kette:
        return False
    return a.enthaelt(b) or b.enthaelt(a)


def _token_reste(e: dict, original: Kanaele, aus: Kanaele, sichtbar: list, eintraege: list) -> list:
    """Signifikante Token des Eintrags, die auf seiner Seite (bzw. in seinem Kanal) noch stehen –
    über der Grundzahl des Originals (Vorkommen außerhalb der Einträge)."""
    reste = []
    tokens = signifikante_token(e["text"])
    if not tokens:
        return reste
    seite = e["seite"]
    if e["kanal"] in ("metadaten", "lesezeichen", "anhang", "dateiname"):
        kanaele = [(e["kanal"], None)]
    else:
        kanaele = [(k, seite) for k in SEITENKANAELE]
        if e["kanal"] == "scan" and not sichtbar:
            kanaele += [(k, seite) for k in aus.kanalnamen() if k.startswith("ocr_")]
    for t in tokens:
        nadel = Gefaltet(t)
        gefunden = None
        for kanal, s in kanaele:
            anzahl = aus.gefaltet(kanal, s).zaehle(nadel)
            if anzahl and anzahl > _grund_kanal(original, kanal, s, nadel, eintraege):
                gefunden = kanal
                break
        if gefunden is None and sichtbar:
            for wort, anteil in sichtbar:
                if anteil >= TEILWEISE_SCHWELLE and t in token(wort):
                    gefunden = "pixel"
                    break
        if gefunden:
            reste.append([t, gefunden])
    return reste


def _behalten_pruefen(e: dict, nadel: Gefaltet, original: Kanaele, aus: Kanaele, sichtbar: list) -> dict:
    seite = e["seite"]
    if e["kanal"] == "scan":
        if sichtbar:
            ok = all(a >= SICHTBAR_SCHWELLE for _, a in sichtbar)
            return {"status": "erhalten" if ok else "fehlt", "pixel": [[t, round(a, 2)] for t, a in sichtbar]}
        ok = any(aus.gefaltet(k, seite).enthaelt(nadel) for k in aus.kanalnamen() if k.startswith("ocr_"))
        return {"status": "erhalten" if ok else "fehlt"}
    soll = original.gefaltet("text", seite).zaehle(nadel)
    ist = aus.gefaltet("text", seite).zaehle(nadel)
    if soll == 0:
        status = "unbekannt"                     # steht so nicht im Original – nicht bewertbar
    else:
        status = "erhalten" if ist >= soll else "fehlt"
    return {"status": status, "anzahl_original": soll, "anzahl_ausgabe": ist}


def _diagnose(status: str, lecks: list, reste: list, erkannt: str, e: dict, am_ort: str | None) -> str:
    """Vermutete Ursache (welche Stufe der Pipeline hat versagt)."""
    sichtbare = {"text", "pixel", "formular", "anmerkung"} | {k for k in lecks if k.startswith("ocr_")}
    if e["kanal"] in ("metadaten", "lesezeichen", "anhang", "dateiname", "anmerkung") and am_ort in ("voll", "teil"):
        return f"Kanal nicht abgedeckt ({e['kanal']})"
    if am_ort == "weg":
        return "an der Stelle entfernt, gleicher Wert anderswo sichtbar"
    if bool(lecks) and not (set(lecks) & sichtbare):
        return "Kanal nicht abgedeckt (" + ", ".join(lecks) + ")"
    if erkannt == "nein":
        return "Erkennung (kein Fund)"
    if erkannt == "teil":
        return "Erkennung unvollständig (nur Teil gefunden)"
    if erkannt == "umfassend":
        return "Erkennung nur als Teil eines längeren Funds (hier nicht gesucht)"
    if erkannt == "aehnlich":
        return "OCR-Verleser (Fund weicht vom gedruckten Wert ab)"
    if e["kanal"] == "scan":
        return "Lokalisierung/Schwärzung auf Scan (gefunden, Pixel nicht entfernt)"
    return "Lokalisierung/Schwärzung (gefunden, aber nicht entfernt)"


# ----------------------------------------------------------------------
# Kennzahlen
# ----------------------------------------------------------------------
def _zaehlen(eintraege: list) -> dict:
    n = len(eintraege)
    c = Counter(e["status"] for e in eintraege)
    return {"n": n, "entfernt": c.get("entfernt", 0), "teilweise": c.get("teilweise", 0), "leck": c.get("leck", 0),
            "recall": round(c.get("entfernt", 0) / n, 4) if n else None}


def kennzahlen(dokumente: list) -> dict:
    schw = [e for d in dokumente for e in d["eintraege"] if e["erwartung"] == "schwaerzen"]
    kern = [e for e in schw if e["umfang"] == "kern"]
    erw = [e for e in schw if e["umfang"] == "erweitert"]
    beh = [e for d in dokumente for e in d["eintraege"] if e["erwartung"] == "behalten" and e["status"] != "unbekannt"]
    fehlt = [e for e in beh if e["status"] == "fehlt"]
    funde = sum(d.get("funde_anzahl", 0) for d in dokumente)
    fa = [f for d in dokumente for f in d.get("fehlalarme", [])]
    gesamt = {
        "dokumente": len(dokumente), "seiten": sum(d.get("seiten") or 0 for d in dokumente),
        "kern": _zaehlen(kern), "erweitert": _zaehlen(erw), "alle": _zaehlen(schw),
        "recall_kern": _zaehlen(kern)["recall"], "recall_erweitert": _zaehlen(erw)["recall"],
        "recall_kern_am_ort": (round(sum(1 for e in kern if e.get("am_ort") == "weg")
                                     / max(1, sum(1 for e in kern if e.get("am_ort") is not None)), 4)
                               if kern else None),
        "behalten_n": len(beh), "behalten_fehlt": len(fehlt),
        "ueberschwaerzung": round(len(fehlt) / len(beh), 4) if beh else None,
        "funde": funde, "fehlalarme": len(fa), "fehlalarme_auf_kontext": sum(1 for f in fa if f["trifft_kontext"]),
        "fehlalarm_quote": round(len(fa) / funde, 4) if funde else None,
        "dokumente_ohne_ausgabe": sum(1 for d in dokumente if d.get("keine_ausgabe")),
        "dokumente_mit_fehler": sum(1 for d in dokumente if d.get("fehler")),
        "dokumente_ohne_leck_kern": sum(1 for d in dokumente
                                        if not any(e["erwartung"] == "schwaerzen" and e["umfang"] == "kern"
                                                   and e["status"] != "entfernt" for e in d["eintraege"])),
    }
    je_kategorie = {}
    for kat in sorted({e["kategorie"] for e in schw}):
        teil = [e for e in schw if e["kategorie"] == kat]
        je_kategorie[kat] = {"umfang": teil[0]["umfang"], **_zaehlen(teil)}
    je_merkmal = {}
    for mm in sorted({m for d in dokumente for m in d.get("merkmale", [])}):
        teil = [e for d in dokumente if mm in d.get("merkmale", []) for e in d["eintraege"]
                if e["erwartung"] == "schwaerzen" and e["umfang"] == "kern"]
        je_merkmal[mm] = {"dokumente": sum(1 for d in dokumente if mm in d.get("merkmale", [])), **_zaehlen(teil)}
    je_kanal = {k: _zaehlen([e for e in kern if e["kanal"] == k]) for k in sorted({e["kanal"] for e in kern})}
    je_typ = {}
    for typ in sorted({d.get("typ") or "?" for d in dokumente}):
        teil = [e for d in dokumente if (d.get("typ") or "?") == typ for e in d["eintraege"]
                if e["erwartung"] == "schwaerzen" and e["umfang"] == "kern"]
        je_typ[typ] = {"dokumente": sum(1 for d in dokumente if (d.get("typ") or "?") == typ), **_zaehlen(teil)}
    je_hinweis = {}
    hinweise = defaultdict(list)
    for e in kern:
        for h in {h.strip() for h in (e.get("bemerkung") or "").split(";") if h.strip()}:
            if h.startswith("Herkunft "):
                h = "Herkunft (nicht deutsch)"
            hinweise[h].append(e)
    for h, teil in sorted(hinweise.items()):
        if len(teil) >= 3:
            je_hinweis[h] = _zaehlen(teil)
    diagnosen = Counter(e.get("diagnose") for e in schw if e["status"] != "entfernt")
    analyse = [d.get("dauer_analyse_s", 0) for d in dokumente]
    schw_z = [d.get("dauer_schwaerzung_s", 0) for d in dokumente]
    seiten = gesamt["seiten"] or 1
    laufzeit = {"analyse_s_gesamt": round(sum(analyse), 1), "schwaerzung_s_gesamt": round(sum(schw_z), 1),
                "analyse_s_median": round(statistics.median(analyse), 2) if analyse else None,
                "schwaerzung_s_median": round(statistics.median(schw_z), 2) if schw_z else None,
                "s_je_seite": round((sum(analyse) + sum(schw_z)) / seiten, 2),
                "max_dokument": max(((d.get("dauer_analyse_s", 0) + d.get("dauer_schwaerzung_s", 0), d["dokument"])
                                     for d in dokumente), default=(0, None)),
                "bewertung_s_gesamt": round(sum(d.get("dauer_bewertung_s", 0) for d in dokumente), 1)}
    scan_docs = [d for d in dokumente if "scan" in d.get("merkmale", [])]
    if scan_docs:
        laufzeit["scan_dokumente_s_median"] = round(statistics.median(
            [d.get("dauer_analyse_s", 0) + d.get("dauer_schwaerzung_s", 0) for d in scan_docs]), 2)
    restrisiko = restrisiko_kennzahlen(dokumente)
    gesamt.update({k: restrisiko[k] for k in ("stille_lecks", "dokumente_mit_stillem_leck", "verdachtsabdeckung",
                                                "fehlverdacht_je_seite", "ausgaben_pruefen", "pruefen_ohne_leck")})
    if restrisiko.get("restrisiko_s_je_seite") is not None:
        laufzeit["restrisiko_s_gesamt"] = restrisiko["restrisiko_s_gesamt"]
        laufzeit["restrisiko_s_je_seite"] = restrisiko["restrisiko_s_je_seite"]
    return {"gesamt": gesamt, "je_kategorie": je_kategorie, "je_merkmal": je_merkmal, "je_kanal": je_kanal,
            "je_typ": je_typ, "je_hinweis": je_hinweis, "diagnosen": dict(diagnosen.most_common()),
            "laufzeit": laufzeit, "restrisiko": restrisiko}


def nur_pixelrest(e: dict) -> bool:
    """Teil-Leck allein über den Pixelvergleich, und jedes der verbliebenen Wörter liegt unter der
    Sichtbarkeitsschwelle (also kein Wort mehr als zur Hälfte lesbar)?"""
    reste, pixel = e.get("reste") or [], e.get("pixel") or []
    if e.get("status") != "teilweise" or not reste or not pixel or any(k != "pixel" for _, k in reste):
        return False
    rest_token = {t for t, _ in reste}
    werte = [a for wort, a in pixel if rest_token & set(token(wort))]
    return bool(werte) and max(werte) < SICHTBAR_SCHWELLE


def restrisiko_kennzahlen(dokumente: list) -> dict:
    """Stille Lecks, Verdachtsabdeckung, Fehlverdacht je Seite, _PRUEFEN ohne Leck (Definitionen im Modulkopf)."""
    seiten = sum(d.get("seiten") or 0 for d in dokumente) or 1
    stille, docs_still, pruefen, pruefen_ohne_leck, pruefen_ohne_jedes = 0, [], 0, [], []
    gezaehlt, abgedeckt, verdacht_n, fehl, nicht_abgedeckt = 0, 0, 0, [], []
    ohne_pixel_n, ohne_pixel_abgedeckt = 0, 0
    je_kat: dict = defaultdict(lambda: {"n": 0, "abgedeckt": 0})
    for d in dokumente:
        status = d.get("status_ausgabe")
        alle_lecks = [e for e in d.get("eintraege", []) if e.get("erwartung") == "schwaerzen"
                      and e.get("status") in ("leck", "teilweise")]
        kern_lecks = [e for e in alle_lecks if e.get("umfang") == "kern"]
        if status == "pruefen":
            pruefen += 1
            if not kern_lecks:
                pruefen_ohne_leck.append(d["dokument"])
            if not alle_lecks:
                pruefen_ohne_jedes.append(d["dokument"])
        elif kern_lecks:
            stille += len(kern_lecks)
            docs_still.append(d["dokument"])
        for e in kern_lecks:
            gezaehlt += 1
            je_kat[e["kategorie"]]["n"] += 1
            pixelrest = nur_pixelrest(e)
            if not pixelrest:
                ohne_pixel_n += 1
                ohne_pixel_abgedeckt += bool(e.get("verdacht_abgedeckt"))
            if e.get("verdacht_abgedeckt"):
                abgedeckt += 1
                je_kat[e["kategorie"]]["abgedeckt"] += 1
            else:
                nicht_abgedeckt.append({"dokument": d["dokument"], "seite": e.get("seite"), "kategorie": e["kategorie"],
                                        "status": e["status"], "text": e["text"], "kanal": e.get("kanal"),
                                        "bemerkung": e.get("bemerkung", ""), "ausgabe_pruefen": status == "pruefen",
                                        "nur_pixelrest": pixelrest})
        for v in list(d.get("verdacht") or []) + list(d.get("reste_verdacht") or []):
            verdacht_n += 1
            if not v.get("trifft", True):
                fehl.append({"dokument": d["dokument"],
                             "seite": v["seite"] + 1 if v.get("seite") is not None else None,
                             "text": v.get("text"), "grund": v.get("grund")})
    dauer = [d["dauer_restrisiko_s"] for d in dokumente if d.get("dauer_restrisiko_s") is not None]
    n = len(dokumente)
    return {
        "stille_lecks": stille, "dokumente_mit_stillem_leck": len(docs_still),
        "dokumente_mit_stillem_leck_quote": round(len(docs_still) / n, 4) if n else None,
        "dokumente_still": docs_still,
        "verdachtsabdeckung": round(abgedeckt / gezaehlt, 4) if gezaehlt else None,
        "kern_lecks": gezaehlt, "kern_lecks_abgedeckt": abgedeckt,
        "verdachtsabdeckung_ohne_pixelrest": round(ohne_pixel_abgedeckt / ohne_pixel_n, 4) if ohne_pixel_n else None,
        "kern_lecks_ohne_pixelrest": ohne_pixel_n, "kern_lecks_ohne_pixelrest_abgedeckt": ohne_pixel_abgedeckt,
        "verdacht": verdacht_n, "fehlverdacht": len(fehl), "fehlverdacht_je_seite": round(len(fehl) / seiten, 3),
        "ausgaben_pruefen": pruefen, "ausgaben_pruefen_quote": round(pruefen / n, 4) if n else None,
        "pruefen_ohne_leck": len(pruefen_ohne_leck), "pruefen_ohne_leck_dokumente": pruefen_ohne_leck,
        "pruefen_ohne_jedes_leck": len(pruefen_ohne_jedes),
        "je_kategorie": {k: dict(v, quote=round(v["abgedeckt"] / v["n"], 4) if v["n"] else None)
                         for k, v in sorted(je_kat.items())},
        "nicht_abgedeckt": nicht_abgedeckt, "fehlverdacht_liste": fehl,
        "restrisiko_s_gesamt": round(sum(dauer), 2) if dauer else None,
        "restrisiko_s_je_seite": round(sum(dauer) / seiten, 3) if dauer else None,
    }


# ----------------------------------------------------------------------
# Lauf über einen Korpus
# ----------------------------------------------------------------------
def bewerte_korpus(korpus: Path, ausgabe: Path, repo: Path | None = None, cli_ocr: bool = True,
                   pixel: bool = True, melde=print, nur: list | None = None) -> dict:
    """Alle Dokumente eines Korpus bewerten; schreibt ergebnis.json und bericht.md nach `ausgabe`."""
    korpus, ausgabe = Path(korpus), Path(ausgabe)
    ausgabe.mkdir(parents=True, exist_ok=True)
    ziel = ausgabe / "anonymisiert"
    if ziel.exists():
        shutil.rmtree(ziel)
    ziel.mkdir(parents=True)
    arbeits = Path(tempfile.mkdtemp(prefix="bewertung_", dir=ausgabe))
    pipeline = Pipeline(repo)
    wahrheiten = lade_wahrheiten(korpus)
    if nur:
        wahrheiten = [w for w in wahrheiten if w["dokument"] in nur]
    dokumente = []
    start = time.perf_counter()
    dienst = pipeline.ocr_dienst()
    try:
        for i, w in enumerate(wahrheiten, 1):
            d = bewerte_dokument(w["_pfad"], w, pipeline, dienst, ziel, arbeits, cli_ocr=cli_ocr, pixel=pixel)
            dokumente.append(d)
            if melde:
                kern = [e for e in d["eintraege"] if e["erwartung"] == "schwaerzen" and e["umfang"] == "kern"]
                ok = sum(1 for e in kern if e["status"] == "entfernt")
                melde(f"[{i}/{len(wahrheiten)}] {d['dokument']}: Kern {ok}/{len(kern)} entfernt, "
                      f"{d['dauer_analyse_s']:.1f}s + {d['dauer_schwaerzung_s']:.1f}s"
                      + (f"  FEHLER: {d['fehler']}" if d.get("fehler") else "")
                      + ("  (keine Ausgabe)" if d.get("keine_ausgabe") else ""))
    finally:
        if dienst is not None:
            try:
                dienst.schliessen()
            except Exception:
                pass
        shutil.rmtree(arbeits, ignore_errors=True)
    werte = kennzahlen(dokumente)
    ergebnis = {
        "schema": "BENCHMARK_SCHEMA.md", "erzeugt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "korpus": str(korpus), "repo": str(pipeline.repo), "commit": pipeline.commit,
        "umgebung": _umgebung(pipeline, cli_ocr),
        "einstellungen": {"aktive_kategorien": sorted(pipeline.aktive()), "nie_liste": [], "immer_liste": [],
                          "alle_funde_angehakt": True, "pixel_schwelle": SICHTBAR_SCHWELLE,
                          "ocr_dpi_bewertung": OCR_DPI},
        "laufzeit_gesamt_s": round(time.perf_counter() - start, 1),
        **werte,
        "lecks": [{"dokument": d["dokument"], **e} for d in dokumente for e in d["eintraege"]
                  if e["erwartung"] == "schwaerzen" and e["status"] != "entfernt"],
        "ueberschwaerzt": [{"dokument": d["dokument"], **e} for d in dokumente for e in d["eintraege"]
                           if e["erwartung"] == "behalten" and e["status"] == "fehlt"],
        "dokumente": dokumente,
    }
    (ausgabe / "ergebnis.json").write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1, default=str),
                                          encoding="utf-8")
    (ausgabe / "bericht.md").write_text(bericht_markdown(ergebnis), encoding="utf-8")
    return ergebnis


def _umgebung(pipeline: Pipeline, cli_ocr: bool) -> dict:
    u = {"python": sys.version.split()[0], "pymupdf": getattr(fitz, "VersionBind", "?"),
         "plattform": sys.platform, "tessdata": pipeline.tessdata()}
    try:
        import spacy
        u["spacy"] = spacy.__version__
    except Exception:
        u["spacy"] = None
    prog = tesseract_cli()
    if cli_ocr and prog:
        try:
            u["tesseract_cli"] = subprocess.run([prog, "--version"], capture_output=True, text=True,
                                                timeout=20).stdout.split("\n")[0]
        except Exception:
            u["tesseract_cli"] = "vorhanden"
    else:
        u["tesseract_cli"] = None
    return u


# ----------------------------------------------------------------------
# Markdown-Bericht
# ----------------------------------------------------------------------
def _p(x) -> str:
    return "–" if x is None else f"{100 * x:.1f} %"


def _tabelle(kopf: list, zeilen: list) -> list:
    aus = ["| " + " | ".join(kopf) + " |", "|" + "|".join("---" for _ in kopf) + "|"]
    aus += ["| " + " | ".join(str(z).replace("|", "\\|") for z in zeile) + " |" for zeile in zeilen]
    return aus


def _restrisiko_bericht(e: dict) -> list:
    rr = e.get("restrisiko")
    if not rr:
        return []
    g = e["gesamt"]
    zeilen = ["", "## Restrisiko: Verdacht und _PRUEFEN", ""]
    zeilen += _tabelle(["Kennzahl", "Wert"], [
        ["**stille Lecks** (Kern leck/teilweise, Ausgabe nicht _PRUEFEN)",
         f"**{rr['stille_lecks']}** in {rr['dokumente_mit_stillem_leck']} Dokument(en) "
         f"({_p(rr.get('dokumente_mit_stillem_leck_quote'))} der Dokumente)"],
        ["Verdachtsabdeckung (Kern leck/teilweise mit Verdacht)",
         f"{_p(rr['verdachtsabdeckung'])} ({rr['kern_lecks_abgedeckt']}/{rr['kern_lecks']})"],
        ["Verdachtsabdeckung ohne reine Pixelreste",
         f"{_p(rr.get('verdachtsabdeckung_ohne_pixelrest'))} ({rr.get('kern_lecks_ohne_pixelrest_abgedeckt')}/"
         f"{rr.get('kern_lecks_ohne_pixelrest')})"],
        ["Fehlverdacht je Seite (Verdacht ohne zu schwärzenden Eintrag)",
         f"{rr['fehlverdacht_je_seite']} ({rr['fehlverdacht']} von {rr['verdacht']} Verdachtsstellen)"],
        ["Ausgaben _PRUEFEN", f"{rr['ausgaben_pruefen']} von {g['dokumente']} ({_p(rr['ausgaben_pruefen_quote'])})"],
        ["_PRUEFEN ohne Kern-Leck / ohne jedes Leck", f"{rr['pruefen_ohne_leck']} / {rr['pruefen_ohne_jedes_leck']}"],
        ["Restrisiko-Prüfung (Laufzeit gesamt / je Seite)",
         f"{rr['restrisiko_s_gesamt']} s / {rr['restrisiko_s_je_seite']} s"
         if rr.get("restrisiko_s_gesamt") is not None else "–"],
    ])
    if rr["je_kategorie"]:
        zeilen += [""]
        zeilen += _tabelle(["Kategorie", "Kern leck/teilweise", "mit Verdacht", "Abdeckung"],
                           [[k, v["n"], v["abgedeckt"], _p(v["quote"])] for k, v in rr["je_kategorie"].items()])
    if rr["dokumente_still"]:
        zeilen += ["", "Dokumente mit stillem Leck: " + ", ".join(rr["dokumente_still"])]
    if rr["nicht_abgedeckt"]:
        zeilen += ["", f"### Lecks ohne Verdacht ({len(rr['nicht_abgedeckt'])})", ""]
        zeilen += _tabelle(["Dokument", "S.", "Kategorie", "Status", "Text", "Kanal", "Ausgabe _PRUEFEN", "nur Pixelrest",
                            "Bemerkung"],
                           [[x["dokument"], x["seite"], x["kategorie"], x["status"], f"`{x['text']}`", x["kanal"],
                             "ja" if x["ausgabe_pruefen"] else "nein", "ja" if x.get("nur_pixelrest") else "nein",
                             x["bemerkung"]] for x in rr["nicht_abgedeckt"][:150]])
    if rr["fehlverdacht_liste"]:
        gruende = Counter(f["grund"] for f in rr["fehlverdacht_liste"])
        zeilen += ["", f"### Fehlverdacht nach Grund ({rr['fehlverdacht']})", ""]
        zeilen += _tabelle(["Grund", "Anzahl"], [[k, v] for k, v in gruende.most_common()])
        zeilen += ["", "Beispiele: " + "; ".join(f"{f['grund']}: `{f['text']}`" for f in rr["fehlverdacht_liste"][:60])]
    return zeilen


def bericht_markdown(e: dict) -> str:
    g = e["gesamt"]
    zeilen = [f"# Entwicklungs-Benchmark PDF-Anonymisierer", "",
              f"Erzeugt {e['erzeugt']} · Repository `{e['repo']}` · Commit `{e.get('commit')}` · Korpus `{e['korpus']}`", "",
              "## Gesamtergebnis", ""]
    zeilen += _tabelle(["Kennzahl", "Wert"], [
        ["Dokumente / Seiten", f"{g['dokumente']} / {g['seiten']}"],
        ["**recall_kern** (vollständig entfernt)", f"**{_p(g['recall_kern'])}** ({g['kern']['entfernt']}/{g['kern']['n']})"],
        ["Kern: teilweise / Leck", f"{g['kern']['teilweise']} / {g['kern']['leck']}"],
        ["recall_erweitert", f"{_p(g['recall_erweitert'])} ({g['erweitert']['entfernt']}/{g['erweitert']['n']})"],
        ["Kern ortsgenau entfernt (Nebenmaß: an der eigenen Fundstelle weg)", _p(g.get("recall_kern_am_ort"))],
        ["Über-Schwärzung (Kontext fehlt)", f"{_p(g['ueberschwaerzung'])} ({g['behalten_fehlt']}/{g['behalten_n']})"],
        ["Fehlalarme (Funde ohne PII-Bezug)", f"{g['fehlalarme']} von {g['funde']} Funden ({_p(g['fehlalarm_quote'])}), "
                                               f"davon auf Kontext: {g['fehlalarme_auf_kontext']}"],
        ["Dokumente ohne Kern-Rest", f"{g['dokumente_ohne_leck_kern']} von {g['dokumente']}"],
        ["Dokumente ohne Ausgabe / mit Fehler", f"{g['dokumente_ohne_ausgabe']} / {g['dokumente_mit_fehler']}"],
    ])
    lz = e["laufzeit"]
    zeilen += ["", "## Laufzeit", ""]
    zeilen += _tabelle(["Kennzahl", "Wert"], [
        ["Analyse gesamt / Median je Dokument", f"{lz['analyse_s_gesamt']} s / {lz['analyse_s_median']} s"],
        ["Schwärzung gesamt / Median je Dokument", f"{lz['schwaerzung_s_gesamt']} s / {lz['schwaerzung_s_median']} s"],
        ["Programm-Laufzeit je Seite", f"{lz['s_je_seite']} s"],
        ["Median Scan-Dokument (Analyse + Schwärzung)", f"{lz.get('scan_dokumente_s_median', '–')} s"],
        ["Langsamstes Dokument", f"{lz['max_dokument'][1]} ({lz['max_dokument'][0]:.1f} s)"],
        ["Bewertung (Kontroll-OCR, Pixel, Kanäle) gesamt", f"{lz['bewertung_s_gesamt']} s"],
    ])
    zeilen += _restrisiko_bericht(e)
    zeilen += ["", "## Je Kategorie", ""]
    zeilen += _tabelle(["Kategorie", "Umfang", "n", "entfernt", "teilweise", "Leck", "Recall"],
                       [[k, v["umfang"], v["n"], v["entfernt"], v["teilweise"], v["leck"], _p(v["recall"])]
                        for k, v in sorted(e["je_kategorie"].items(), key=lambda kv: (kv[1]["umfang"], kv[1]["recall"] or 0))])
    zeilen += ["", "## Je Merkmal (Kern-Einträge der Dokumente mit diesem Merkmal)", ""]
    zeilen += _tabelle(["Merkmal", "Dokumente", "n", "entfernt", "teilweise", "Leck", "Recall"],
                       [[k, v["dokumente"], v["n"], v["entfernt"], v["teilweise"], v["leck"], _p(v["recall"])]
                        for k, v in sorted(e["je_merkmal"].items(), key=lambda kv: kv[1]["recall"] if kv[1]["recall"] is not None else 2)])
    zeilen += ["", "## Je Kanal und Dokumenttyp (Kern)", ""]
    zeilen += _tabelle(["Kanal", "n", "entfernt", "teilweise", "Leck", "Recall"],
                       [[k, v["n"], v["entfernt"], v["teilweise"], v["leck"], _p(v["recall"])] for k, v in e["je_kanal"].items()])
    zeilen += [""]
    zeilen += _tabelle(["Typ", "Dokumente", "n", "entfernt", "teilweise", "Leck", "Recall"],
                       [[k, v["dokumente"], v["n"], v["entfernt"], v["teilweise"], v["leck"], _p(v["recall"])]
                        for k, v in e["je_typ"].items()])
    zeilen += ["", "## Je Fundstellen-Hinweis (Bemerkung, Kern, mind. 3 Einträge; schlechteste zuerst)", ""]
    zeilen += _tabelle(["Hinweis", "n", "entfernt", "teilweise", "Leck", "Recall"],
                       [[k, v["n"], v["entfernt"], v["teilweise"], v["leck"], _p(v["recall"])]
                        for k, v in sorted(e["je_hinweis"].items(), key=lambda kv: kv[1]["recall"] or 0)[:60]])
    zeilen += ["", "## Ursachen (Diagnose je nicht entferntem Eintrag)", ""]
    zeilen += _tabelle(["Diagnose", "Anzahl"], [[k, v] for k, v in e["diagnosen"].items()])
    zeilen += ["", f"## Alle Lecks und Teil-Lecks ({len(e['lecks'])})", ""]
    zeilen += _tabelle(["Dokument", "S.", "Kategorie", "Umfang", "Status", "Text", "Kanäle / Rest", "erkannt", "am Ort",
                        "Bemerkung", "Diagnose"],
                       [[l["dokument"], l["seite"], l["kategorie"], l["umfang"], l["status"], f"`{l['text']}`",
                         ", ".join(l["kanaele"]) or ", ".join(f"{t}@{k}" for t, k in l["reste"]), l["erkannt"],
                         l.get("am_ort") or "–", l["bemerkung"], l.get("diagnose", "")] for l in e["lecks"]])
    zeilen += ["", f"## Über-Schwärzung ({len(e['ueberschwaerzt'])})", ""]
    zeilen += _tabelle(["Dokument", "S.", "Text", "verursacht von"],
                       [[u["dokument"], u["seite"], f"`{u['text']}`", ", ".join(map(str, u.get("verursacht_von") or []))]
                        for u in e["ueberschwaerzt"]])
    fa = Counter((f["kategorie"], f["trifft_kontext"]) for d in e["dokumente"] for f in d.get("fehlalarme", []))
    zeilen += ["", "## Fehlalarme je Kategorie", ""]
    zeilen += _tabelle(["Kategorie", "auf Kontext", "Anzahl"], [[k[0], "ja" if k[1] else "nein", v] for k, v in fa.most_common()])
    beispiele = [f for d in e["dokumente"] for f in d.get("fehlalarme", [])][:60]
    zeilen += ["", "Beispiele: " + "; ".join(f"{f['kategorie']}: `{f['text']}`" for f in beispiele)]
    u = e["umgebung"]
    zeilen += ["", "## Messverfahren und Grenzen", "",
               "- Geprüft wird die **Ausgabedatei** über Textebene, Formularfelder, Anmerkungen, Metadaten/XMP, "
               "Lesezeichen, Anhänge, dekodierte Rohdaten aller Objekte/Ströme und den Ausgabedateinamen.",
               f"- Scan-Seiten: OCR der gerenderten Ausgabeseite ({OCR_DPI} dpi) mit dem in PyMuPDF eingebauten "
               f"Tesseract und den Sprachdaten `{u.get('tessdata')}` – **das ist dieselbe Engine wie im Programm**; "
               f"zusätzlich Tesseract-Kommandozeile: {u.get('tesseract_cli') or 'nicht verfügbar'}.",
               f"- Unabhängig von jeder OCR: Pixelvergleich Original/Ausgabe an den Wortrechtecken der Wahrheit "
               f"({PIXEL_DPI} dpi; ein Wort gilt als lesbar, wenn ≥ {int(SICHTBAR_SCHWELLE * 100)} % seiner Tintenpixel "
               f"unverändert sind).",
               "- Normalisierung: casefold, Leerraum und Trennstriche entfernt (Schema), zusätzlich Diakritika gefaltet "
               "und Treffer nur an Wortgrenzen.",
               "- Fehlt eine Ausgabedatei, wird das Original als Ausgabe gewertet (alles gilt als nicht geschwärzt).",
               f"- Umgebung: Python {u.get('python')}, PyMuPDF {u.get('pymupdf')}, spaCy {u.get('spacy')}, {u.get('plattform')}."]
    return "\n".join(zeilen) + "\n"
