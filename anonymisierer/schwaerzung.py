"""Schwärzung: Funde wirklich aus dem PDF entfernen (Text und Bildpixel), Nebenkanäle leeren, neutral
benannte Ausgabe schreiben und das Ergebnis selbst kontrollieren.

Öffentliche Schnittstelle (CONTRACT.md, CONTRACT_V2.md Abschnitt 5):
    schwaerze_pdf(...)     Funde/Stellen schwärzen, Selbstkontrolle, Ausgabe anonym_NN.pdf / _PRUEFEN.pdf
    freigeben(pfad)        _PRUEFEN entfernen (Name exklusiv vergeben), _zuordnung.txt anpassen
    verwerfen(pfad)        Ausgabe löschen, Zuordnung austragen

Arbeitsweise:
  * Dieselbe Vorbereitung und dasselbe Seitenmodell wie die Analyse (seitenmodell): bake, Seitendrehung,
    Ebenen, /ActualText; Textebene, OCR (aus dem ocr_cache der Analyse), Bild-OCR, Formularwerte.
    Wird das Modell der Analyse übergeben, wird sein Fingerabdruck mit dem frisch gebauten verglichen.
  * Geschwärzt werden die STELLEN der Funde (nur "an": True). Jede Stelle wird am frischen Modell geprüft
    (gleicher Text an gleicher Stelle); weicht sie ab, wird sie auf der Seite neu gesucht. Funde ohne
    Stellen (alte Aufrufer) werden über den gemeinsamen Vergleicher (ganzwort_stellen) gesucht.
  * Rechtecke aus den echten Glyphen (Textebene: 0,70 x Schriftgröße über bis 0,02 x unter der Grundlinie)
    bzw. den ganzen OCR-Wortboxen + Rand; apply_redactions löscht Text UND Bildpixel.
  * Nach dem Anwenden: Glyphenrest-Prüfung je Zeile (Teilreste, Gutachten S-07), Platzhalter passend zur
    Lücke, Kollateralprüfung. Danach Selbstkontrolle der AUSGABE mit demselben Modell und demselben
    Vergleicher (Ganzwort, alle Schreibweisen; Scan-Seiten per Kontroll-OCR mit derselben Ausrichtung).
  * Ausgabename exklusiv reserviert (O_CREAT|O_EXCL) – zwei gleichzeitige Läufe überschreiben sich nie.
"""

from __future__ import annotations

import datetime
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import seitenmodell as sm
from .ocr import OcrDienst, bild_bereiche, ocr_noetig  # noqa: F401  (Namen bleiben importierbar)
from .seitenmodell import Abgebrochen as _Abgebrochen
from .seitenmodell import ganzwort_stellen, modus_fuer, suchtext_normalisieren

try:  # Agent "ocr-bild": Nebenkanäle (S-05, S-06, S-11, S-14) und Bild-Neukodierung (S-04)
    from . import nebenkanaele as _nebenkanaele
except ImportError:
    _nebenkanaele = None
try:
    from . import bilder as _bilder
except ImportError:
    _bilder = None
try:  # Restrisiko-Prüfung (Vertrag Abschnitt 7)
    from . import restrisiko as _restrisiko
except ImportError:
    _restrisiko = None

FUELLFARBE = (0.92, 0.92, 0.92)
TEXTFARBE = (0, 0, 0)
PLATZHALTER_MIN_PT = 4.0      # darunter zeichnet MuPDF den Platzhalter nicht
PLATZHALTER_MAX_PT = 9.0
PLATZHALTER_BEREICH = "[GESCHWÄRZT]"
OBERKANTE = sm.OBERKANTE
UNTERKANTE = sm.UNTERKANTE
OCR_RAND = sm.OCR_RAND
OCR_DPI = sm.OCR_DPI
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
_ZUORDNUNG = "_zuordnung.txt"

_norm_fund = suchtext_normalisieren      # Kompatibilität (alter Name)


def _kern(wort: str) -> str:
    return wort.strip(SATZZEICHEN + " ")


def _anfangs_varianten(text: str) -> tuple:
    """Kürzere Anfänge eines mehrteiligen Fundtexts – für Funde alter Aufrufer, die mitten im Wort
    abgeschnitten sind ("KH-2025-004711 vom 12.03.2"): dann wird wenigstens der Anfang gefunden.
    Es bleiben mindestens zwei Wörter oder eine Kennung mit Ziffern (>= 5 Zeichen)."""
    tokens = suchtext_normalisieren(text).split()
    varianten = []
    for n in range(len(tokens) - 1, 0, -1):
        rest = tokens[:n]
        if len(rest) >= 2 or (len(rest[0]) >= 5 and any(z.isdigit() for z in rest[0])):
            varianten.append(" ".join(rest))
    return tuple(varianten)


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
# Nebenkanäle (Rückfall, solange anonymisierer/nebenkanaele.py fehlt)
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


def _nebenkanaele_entfernen(doc, zaehler: dict):
    """Anmerkungen, Links, Lesezeichen, Anhänge, Metadaten (Info + XMP), Miniaturbilder und weitere
    Katalog-Einträge entfernen, die Klartext tragen können."""
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
                       "Collection", "Requirements", "PageLabels", "SpiderInfo", "Threads"):
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


def _nebenkanaele_bereinigen(lauf, doc, zaehler: dict) -> str:
    """Nebenkanäle entfernen: anonymisierer/nebenkanaele.py, falls vorhanden (Gutachten S-05/S-06/S-11/S-14),
    sonst die eingebaute Bereinigung. Liefert den Hinweistext."""
    if _nebenkanaele is not None and hasattr(_nebenkanaele, "nebenkanaele_entfernen"):
        try:
            try:
                neu = _nebenkanaele.nebenkanaele_entfernen(doc, dict(zaehler))
            except TypeError:                       # ältere Signatur ohne Zähler
                neu = _nebenkanaele.nebenkanaele_entfernen(doc)
            for k, v in (neu or {}).items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    zaehler[k] = max(int(zaehler.get(k, 0) or 0), int(v))
                elif k not in zaehler or v:
                    zaehler[k] = v
            hinweis_fn = getattr(_nebenkanaele, "nebenkanal_hinweis", None)
            return hinweis_fn(zaehler) if hinweis_fn else _nebenkanal_hinweis(zaehler)
        except Exception as e:
            lauf.melden("warnung", "NEBENKANAL_ENTFERNT",
                        f"Nebenkanäle (Anmerkungen, Metadaten …) konnten nicht vollständig entfernt werden ({e}) – "
                        f"Rückfall auf die einfache Bereinigung.")
            if not lauf.beschnitt_lokal:
                _beschnitt_nachholen(lauf, doc)
    _nebenkanaele_entfernen(doc, zaehler)
    return _nebenkanal_hinweis(zaehler)


def _beschnitt_nachholen(lauf, doc) -> None:
    """Rückfall, wenn das Nebenkanal-Modul scheitert: Inhalte außerhalb des Beschnitts (S-05) hier entfernen,
    denn die Seitenschleife hat sie dem Modul überlassen. Scheitert MuPDF an einer Seite (zyklisches Form-XObject,
    Befund R-08), wird sie als Bild ihres sichtbaren Bereichs neu erzeugt – nie bleibt der Inhalt still stehen;
    lässt sie sich auch nicht rendern, entsteht keine Ausgabe (_seite_als_bild)."""
    lauf.beschnitt_lokal = True
    for nr in range(len(doc)):
        seite = doc[nr]
        rechtecke = []
        try:
            rechtecke = _beschnitt_rechtecke(seite)
            if not rechtecke:
                continue
            for r in rechtecke:
                seite.add_redact_annot(r, fill=False)
            seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                                   graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                                   text=fitz.PDF_REDACT_TEXT_REMOVE)
            lauf.beschnitt_seiten.append(nr + 1)
        except Exception as e:
            modell = lauf.modell.seiten[nr] if lauf.modell is not None and nr < len(lauf.modell.seiten) else None
            _seite_als_bild(lauf, nr, seite, modell, [], rechtecke, e)


def _beschnitt_rechtecke(seite) -> list:
    """Rechtecke außerhalb des sichtbaren Seitenbereichs (CropBox), in denen laut Bounding-Box-Protokoll
    Inhalt liegt: unsichtbar für Betrachter und Textextraktion, aber lesbar für andere Werkzeuge
    (Gutachten S-05). Sie werden ohne Füllung geschwärzt."""
    sichtbar = fitz.Rect(seite.rect)
    gesamt = fitz.Rect(sichtbar)
    try:
        for _, bbox in seite.get_bboxlog():
            r = fitz.Rect(bbox)
            if not r.is_empty and not r.is_infinite and abs(r) < 1e7:
                gesamt |= r
    except Exception:
        pass
    if gesamt == sichtbar or sichtbar.contains(gesamt):
        return []
    gesamt = gesamt + (-2, -2, 2, 2)
    streifen = [fitz.Rect(gesamt.x0, gesamt.y0, gesamt.x1, sichtbar.y0),
                fitz.Rect(gesamt.x0, sichtbar.y1, gesamt.x1, gesamt.y1),
                fitz.Rect(gesamt.x0, sichtbar.y0, sichtbar.x0, sichtbar.y1),
                fitz.Rect(sichtbar.x1, sichtbar.y0, gesamt.x1, sichtbar.y1)]
    return [r for r in streifen if not r.is_empty and r.width > 0.5 and r.height > 0.5]


# ----------------------------------------------------------------------
# Ausgabedateien
# ----------------------------------------------------------------------
def _nummern(ziel: Path) -> list:
    nummern = []
    try:
        for p in ziel.glob("anonym_*.pdf"):
            m = _NAMENSMUSTER.match(p.name)
            if m:
                nummern.append(int(m.group(1)))
    except OSError:
        pass
    return nummern


def _freier_ausgabename(ziel: Path, pruefen: bool) -> Path:
    """Nächste freie laufende Nummer im Zielordner (ohne Reservierung; siehe _ausgabe_reservieren)."""
    nummer = max(_nummern(ziel), default=0) + 1
    while True:
        basis = ziel / f"anonym_{nummer:02d}.pdf"
        pruef = ziel / f"anonym_{nummer:02d}_PRUEFEN.pdf"
        if not basis.exists() and not pruef.exists():
            return pruef if pruefen else basis
        nummer += 1


def _exklusiv_anlegen(pfad: Path) -> bool:
    try:
        fd = os.open(pfad, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.close(fd)
    return True


def _nummer_reservieren(ziel: Path, pruefen: bool, nummer: int | None = None) -> Path:
    """Reserviert eine Ausgabenummer exklusiv und liefert den (leer angelegten) Zielnamen.

    Protokoll: Die Nummer gilt als belegt, sobald anonym_NN.pdf existiert – es wird mit O_CREAT|O_EXCL
    angelegt (zwei Läufe können nicht dieselbe Nummer bekommen). Für _PRUEFEN wird danach
    anonym_NN_PRUEFEN.pdf exklusiv angelegt und die Platzhalterdatei anonym_NN.pdf wieder entfernt
    (ein anderer Lauf sieht dann die _PRUEFEN-Datei und überspringt die Nummer)."""
    if nummer is None:
        nummer = max(_nummern(ziel), default=0) + 1
    for _ in range(10000):
        basis = ziel / f"anonym_{nummer:02d}.pdf"
        pruef = ziel / f"anonym_{nummer:02d}_PRUEFEN.pdf"
        if _exklusiv_anlegen(basis):
            if pruef.exists():
                _aufraeumen([basis])
                nummer += 1
                continue
            if not pruefen:
                return basis
            if _exklusiv_anlegen(pruef):
                _aufraeumen([basis])
                return pruef
            _aufraeumen([basis])
        nummer += 1
    raise OSError(f"Kein freier Ausgabename in {ziel}")


def _ausgabe_reservieren(ziel: Path, pruefen: bool) -> Path:
    return _nummer_reservieren(ziel, pruefen)


def _zuordnung_anhaengen(ziel: Path, ausgabe: Path, original: Path):
    zeit = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(ziel / _ZUORDNUNG, "a", encoding="utf-8") as f:
        f.write(f"{ausgabe.name}  <-  {original.name}  ({zeit})\n")


def _zuordnung_umschreiben(ziel: Path, alt: str, neu: str | None):
    """Zeile der Ausgabe `alt` in _zuordnung.txt auf `neu` umbenennen (neu=None: Zeile entfernen)."""
    datei = ziel / _ZUORDNUNG
    if not datei.exists():
        return
    zeilen = datei.read_text(encoding="utf-8").splitlines(keepends=True)
    aus = []
    for z in zeilen:
        if z.startswith(alt + "  <-  "):
            if neu is None:
                continue
            z = neu + z[len(alt):]
        aus.append(z)
    tmp = ziel / f".{_ZUORDNUNG}.{os.getpid()}.tmp"
    tmp.write_text("".join(aus), encoding="utf-8")
    os.replace(tmp, datei)


def _aufraeumen(pfade):
    for p in pfade:
        try:
            Path(p).unlink()
        except OSError:
            pass


def freigeben(ausgabe_pfad) -> Path:
    """Gibt eine _PRUEFEN-Ausgabe frei: neuer Name ohne _PRUEFEN (dieselbe Nummer, falls frei, sonst die
    nächste freie – exklusiv vergeben), _zuordnung.txt wird angepasst. Rückgabe: neuer Pfad."""
    pfad = Path(ausgabe_pfad)
    m = _NAMENSMUSTER.match(pfad.name)
    if not pfad.exists():
        raise FileNotFoundError(f"Ausgabe nicht gefunden: {pfad}")
    if "_PRUEFEN" not in pfad.name.upper():
        return pfad
    ziel = pfad.parent
    nummer = int(m.group(1)) if m else None
    neu = None
    if nummer is not None:
        basis = ziel / f"anonym_{nummer:02d}.pdf"
        if _exklusiv_anlegen(basis):
            neu = basis
    if neu is None:
        neu = _nummer_reservieren(ziel, pruefen=False)
    try:
        os.replace(pfad, neu)
    except OSError:
        _aufraeumen([neu])
        raise
    _zuordnung_umschreiben(ziel, pfad.name, neu.name)
    return neu


def verwerfen(ausgabe_pfad) -> None:
    """Löscht eine Ausgabe und trägt sie aus _zuordnung.txt aus."""
    pfad = Path(ausgabe_pfad)
    try:
        pfad.unlink()
    except FileNotFoundError:
        pass
    _zuordnung_umschreiben(pfad.parent, pfad.name, None)


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
        self.ocr_cache = dict(ocr_cache) if ocr_cache else {}
        self.ziel = ziel
        self.restrisiko_fehler = False
        self.doc = None
        self.modell = None                   # frisch gebautes Seitenmodell
        self.analyse_modell = None           # Modell der Analyse (falls übergeben)
        self.geoeffnet_von = None            # Pfad, aus dem self.doc gerade geladen ist (Zwischenstand)
        self.tmp_pfade: list = []
        self.rects_je_seite: dict = {}       # Seitenindex -> angewendete Rechtecke (für die Kontrolle)
        self.ocr_modus: dict = {}            # Seitenindex -> "seite" | "bilder"
        self.bildbereiche: dict = {}         # Seitenindex -> Bildbereiche (für Kontroll-OCR "bilder")
        self.kategorien_je_seite: dict = {}  # Seitenindex -> Kategorien mit Treffer
        self.gefunden: set = set()           # id() der Funde mit mindestens einer geschwärzten Stelle
        self.treffer = 0
        self.stellen_geschwaerzt = 0
        self.nicht_lokalisiert: list = []    # Fundtexte von Stellen, die nicht lokalisiert werden konnten
        self.nicht_gefunden: list = []       # Fundtexte (alte Aufrufer), die nirgends vorkommen
        self.neu_gesucht = 0                 # Stellen, die wegen Abweichung neu gesucht wurden
        self.abgewaehlt: list = []           # (Seite, Text, Grundlinie) abgewählter Stellen
        self.ohne_platzhalter = 0
        self.abgekuerzt: dict = {}           # Kurzform -> voller Platzhalter (enge Lücken)
        self.anfangstreffer: dict = {}       # Fundtext -> gefundener Anfang (abgeschnittene Fundtexte)
        self.teilreste: list = []            # Treffer, deren Glyphen nach dem Anwenden noch da waren
        self.kollateral: list = []
        self.grafik_seiten: list = []
        self.bild_seiten: list = []
        self.bild_xrefs: set = set()         # geänderte Bilder (Neukodierung)
        self.bilder_neu_kodiert = 0
        self.beschnitt_lokal = True
        self.beschnitt_seiten: list = []
        self.scan_seiten_seit_speichern = 0
        self.warnungen: list = []
        self.hinweise: list = []
        self.meldungen: list = []
        self.modell_abweichung: list = []    # Seiten, deren Modell von der Analyse abweicht

    def abbruch_pruefen(self):
        if self.abbruch is not None and self.abbruch.is_set():
            raise _Abgebrochen()

    def melden(self, art: str, code: str, text: str, seite=None):
        liste = self.warnungen if art in ("warnung", "fehler") else self.hinweise
        if text not in liste:
            liste.append(text)
        self.meldungen.append({"art": art, "code": code, "text": text, "seite": seite})

    def ziel_sicherstellen(self):
        """Zielordner erst anlegen, wenn wirklich etwas geschrieben wird (kein leerer Ordner bei 0 Treffern)."""
        try:
            self.ziel.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OSError(f"Zielordner kann nicht angelegt werden ({self.ziel}): {e}") from e

    def tmp_pfad(self, kennung: str) -> Path:
        self.ziel_sicherstellen()
        p = self.ziel / f".anonym_tmp_{os.getpid()}_{id(self)}_{kennung}.pdf"
        if p not in self.tmp_pfade:
            self.tmp_pfade.append(p)
        return p

    def bilder_kodieren(self):
        """Durch die Pixel-Schwärzung geänderte Bilder wieder kompakt speichern (Gutachten S-04)."""
        if not self.bild_xrefs or _bilder is None or not hasattr(_bilder, "bilder_neu_kodieren"):
            self.bild_xrefs.clear()
            return
        try:
            self.bilder_neu_kodiert += int(_bilder.bilder_neu_kodieren(self.doc, set(self.bild_xrefs)) or 0)
        except Exception as e:
            self.melden("hinweis", "BILDER_UNGEPRUEFT",
                        f"Geschwärzte Bilder konnten nicht neu komprimiert werden ({e}) – die Datei wird größer.")
        self.bild_xrefs.clear()

    def zwischenspeichern(self, nr):
        """Zwischenstand speichern und neu öffnen, damit geschwärzte Scan-Bilder nicht unkomprimiert
        im Speicher bleiben (M-52). Wechselt zwischen zwei Dateinamen, weil PyMuPDF nicht auf die
        gerade geöffnete Datei speichert."""
        self.bilder_kodieren()
        kennung = "b" if self.geoeffnet_von == self.tmp_pfad("a") else "a"
        ziel = self.tmp_pfad(kennung)
        self.doc.save(ziel, garbage=1, deflate=True)
        self.doc.close()
        self.doc = fitz.open(ziel)
        self.geoeffnet_von = ziel
        self.scan_seiten_seit_speichern = 0
        self.melde(f"   Zwischenstand gespeichert (Seite {nr + 1}) …")

    def winkel(self, nr: int) -> int:
        """Ausrichtung der Scan-Seite für die Kontroll-OCR (Gutachten S-08): aus dem Modell, sonst vom Dienst."""
        for modell in (self.modell, self.analyse_modell):
            if modell is not None and nr < len(modell.seiten) and modell.seiten[nr].ocr_winkel is not None:
                return int(modell.seiten[nr].ocr_winkel)
        for name in ("winkel_falls_bekannt", "winkel"):
            f = getattr(self.ocr, name, None)
            if f is None:
                continue
            try:
                w = f(self.pdf_pfad, nr, OCR_DPI)
            except Exception:
                w = None
            if w is not None:
                return int(w)
        return 0


# ----------------------------------------------------------------------
# Planung der Stellen
# ----------------------------------------------------------------------
class _Plan:
    """Zu schwärzende Stellen je Seite: (start, ende, Fund, Ersatz)."""

    def __init__(self):
        self.je_seite: dict = {}

    def hinzu(self, nr: int, start: int, ende: int, fund: dict, ersatz: str):
        self.je_seite.setdefault(nr, []).append((start, ende, fund, ersatz))

    def zusammengefasst(self, nr: int) -> list:
        """Überlappende Stellen einer Seite zu einer zusammenfassen (Platzhalter des längsten Treffers)."""
        stellen = sorted(self.je_seite.get(nr, []), key=lambda x: (x[0], -x[1]))
        aus = []
        for s, e, fund, ersatz in stellen:
            if aus and s < aus[-1][1]:
                a_s, a_e, a_fund, a_ersatz, mitglieder = aus[-1]
                if e - s > a_e - a_s:
                    a_fund, a_ersatz = fund, ersatz
                aus[-1] = (a_s, max(a_e, e), a_fund, a_ersatz, mitglieder + [fund])
            else:
                aus.append((s, e, fund, ersatz, [fund]))
        return aus


def _suche_auf_seite(seite, texte, modus) -> list:
    for t in texte:
        if t and t.strip():
            treffer = ganzwort_stellen(seite, t, modus)
            if treffer:
                return treffer
    return []


def _planen(lauf: _Lauf, plan: _Plan, dok, manuelle_stellen: dict, manuelle_bereiche: dict):
    """Stellen der Funde am frischen Modell prüfen bzw. suchen und in den Plan eintragen."""
    ana = lauf.analyse_modell
    for fund in lauf.funde:
        kategorie = fund.get("kategorie", "")
        modus = modus_fuer(kategorie)
        ersatz = fund.get("ersatz") or ""
        stellen = fund.get("stellen")
        if stellen:
            for st in stellen:
                try:
                    nr, s, e = int(st.get("seite", -1)), int(st.get("start", -1)), int(st.get("ende", -1))
                except (TypeError, ValueError):
                    nr, s, e = -1, -1, -1
                seite = dok.seiten[nr] if 0 <= nr < len(dok.seiten) else None
                gueltig = seite is not None and 0 <= s < e <= len(seite.text)
                soll = st.get("text")
                passt = gueltig and (seite.text[s:e] == soll if soll is not None
                                     else nr not in lauf.modell_abweichung)
                if not st.get("an", True):
                    text = soll if soll is not None else (seite.text[s:e] if gueltig else fund.get("text", ""))
                    grundlinie = None
                    if passt:
                        teile = seite.rechtecke(s, e)
                        grundlinie = teile[0][3] if teile else None
                    lauf.abgewaehlt.append([nr, _vergleichstext(text), grundlinie])
                    continue
                if passt:
                    plan.hinzu(nr, s, e, fund, ersatz)
                    continue
                gefunden = _suche_auf_seite(seite, [soll, fund.get("text")], modus) if seite is not None else []
                if gefunden:
                    lauf.neu_gesucht += 1
                    for s2, e2 in gefunden:
                        plan.hinzu(nr, s2, e2, fund, ersatz)
                else:
                    lauf.nicht_lokalisiert.append(fund.get("text") or soll or "?")
            continue
        # Alte Aufrufer: Fund ohne Stellen -> Ganzwort-Suche auf allen Seiten
        text = fund.get("text", "")
        gefunden = False
        for nr, seite in enumerate(dok.seiten):
            for s, e in ganzwort_stellen(seite, text, modus):
                plan.hinzu(nr, s, e, fund, ersatz)
                gefunden = True
        if not gefunden:
            for variante in _anfangs_varianten(text):
                for nr, seite in enumerate(dok.seiten):
                    for s, e in ganzwort_stellen(seite, variante, modus):
                        plan.hinzu(nr, s, e, fund, ersatz)
                        gefunden = True
                if gefunden:
                    lauf.anfangstreffer[text] = variante
                    break
        if not gefunden:
            lauf.nicht_gefunden.append(text)
    # Manuelle Stellen aus der Vorschau (Offsets im Modell der Analyse)
    for nr, liste in (manuelle_stellen or {}).items():
        for eintrag in liste:
            s, e = int(eintrag[0]), int(eintrag[1])
            ersatz = eintrag[2] if len(eintrag) > 2 and eintrag[2] else PLATZHALTER_BEREICH
            pseudo = {"kategorie": "manuell", "text": "", "ersatz": ersatz}
            seite = dok.seiten[nr] if 0 <= nr < len(dok.seiten) else None
            if (ana is not None and nr in lauf.modell_abweichung and nr < len(ana.seiten)
                    and 0 <= s < e <= len(ana.seiten[nr].text)):
                # Modell weicht ab: Geometrie aus dem Modell der Analyse (das hat die Nutzerin gesehen)
                for teil in ana.seiten[nr].rechtecke(s, e):
                    manuelle_bereiche.setdefault(nr, []).append((fitz.Rect(teil[1]) + (-0.5, -0.5, 0.5, 0.5), ersatz))
                continue
            if seite is not None and 0 <= s < e <= len(seite.text):
                pseudo["text"] = seite.text[s:e]
                plan.hinzu(nr, s, e, pseudo, ersatz)
            else:
                lauf.nicht_lokalisiert.append(f"manuelle Stelle auf Seite {nr + 1}")


def _vergleichstext(text: str) -> str:
    return " ".join(suchtext_normalisieren(text or "").casefold().split())


# ----------------------------------------------------------------------
# Seite bearbeiten
# ----------------------------------------------------------------------
KURVEN_SCHRAEGE_LINIEN = 4    # so viele schräge Liniensegmente ergeben einen Linienzug (Unterschriftenpad, Ink)


def _hat_kurven(seite) -> bool:
    """Vektorzeichnungen, die eine Unterschrift, ein Stempel oder ein Logo sein können: schon EINE Bézierkurve
    (ein Namenszug aus 1-2 Kurven, Befund M-66) oder ein Linienzug aus mehreren schrägen Segmenten
    (Unterschriftenpad, eingebrannte Freihand-Anmerkung). Rechtecke sowie waagerechte und senkrechte Linien
    (Tabellen, Unterstreichungen) zählen nicht."""
    try:
        if len(seite.read_contents()) > 1_500_000:
            return False
        schraeg = 0
        for pfad in seite.get_drawings():
            for item in pfad.get("items", []):
                if item[0] == "c":
                    return True
                if item[0] == "l":
                    p, q = item[1], item[2]
                    if abs(p.x - q.x) > 0.5 and abs(p.y - q.y) > 0.5:
                        schraeg += 1
                        if schraeg >= KURVEN_SCHRAEGE_LINIEN:
                            return True
    except Exception:
        pass
    return False


def _platzhalter_zeilen_vorher(m, rects: list) -> dict:
    """Vor apply_redactions: je waagerechter Textzeile des Modells, die ein Kasten berührt, ihre sichtbaren
    Textglyphen [(x0, x1, Zeichen)] nach x sortiert, Grundlinie und Schriftgröße – Grundlage für
    _platzhalter_verschiebung."""
    zeilen: dict = {}
    for g, z in enumerate(m.zeichen):
        if z.quelle != "text" or z.c.isspace() or not (z.rect.x1 > z.rect.x0):
            continue
        zeilen.setdefault(z.zeile, []).append(z)
    aus = {}
    for zid, zs in zeilen.items():
        if not all(z.horizontal for z in zs):
            continue
        box = fitz.Rect(min(z.rect.x0 for z in zs), min(z.rect.y0 for z in zs),
                        max(z.rect.x1 for z in zs), max(z.rect.y1 for z in zs))
        if not any(min(r.y1, box.y1) - max(r.y0, box.y0) > 0.3 * min(r.height, box.height) and
                   r.x1 > box.x0 - 1 and r.x0 < box.x1 + 1 for r in rects):
            continue
        zs = sorted(zs, key=lambda z: z.rect.x0)
        grund = sorted(z.grundlinie for z in zs)[len(zs) // 2]
        aus[zid] = {"glyphen": [(z.rect.x0, z.rect.x1, z.c) for z in zs], "grundlinie": grund,
                    "groesse": max(z.groesse for z in zs) or 10.0, "box": box}
    return aus


def _platzhalter_verschiebung(seite, zeilen_vorher: dict, rects: list) -> list:
    """Nach apply_redactions: MuPDF 1.28.5/1.28.6 (PyMuPDF 2.0/2.1) lässt beim Entfernen von Glyphen mitten in
    einem TJ-Feld die Breite der ersten entfernten Glyphe weg – der Rest der Zeile rutscht nach links unter den
    grauen Kasten (Befund M-31: "[PERSON A]/ersicherungsmakler", in der Textebene "[P,A]Ihr"). Gemessen wird die
    tatsächliche Lage der verbliebenen Zeichen jeder betroffenen Zeile (Zeichenfolge vor/nach dem Schwärzen
    abgeglichen); je Kasten (dl, dr, frei_links, frei_rechts): Verschiebung des linken bzw. rechten
    Nachbarzeichens und die neue rechte Kante des linken bzw. linke Kante des rechten Nachbarzeichens (None =
    kein Nachbar) – so weit darf ein Platzhalter wachsen. Ohne Messung (0, 0, None, None)."""
    aus = [(0.0, 0.0, None, None)] * len(rects)
    if not zeilen_vorher:
        return aus
    import difflib
    try:
        rd = seite.get_text("rawdict", flags=sm.TEXT_FLAGS)
    except Exception:
        return aus
    nachher = []
    for block in rd.get("blocks", []):
        for zeile in block.get("lines", []):
            for sp in zeile.get("spans", []):
                for ch in sp.get("chars", []):
                    if not ch["c"].isspace():
                        b = ch["bbox"]
                        nachher.append((b[0], b[2], ch["c"], ch["origin"][1]))
    verschiebung: dict = {}           # zid -> [(x0_vorher, x1_vorher, dx)] der wiedergefundenen Glyphen
    for zid, info in zeilen_vorher.items():
        vorher = info["glyphen"]
        box, grund, groesse = info["box"], info["grundlinie"], info["groesse"]
        kandidaten = sorted((c for c in nachher if abs(c[3] - grund) <= 0.3 * groesse
                             and c[1] > box.x0 - 2 and c[0] < box.x1 + 2), key=lambda c: c[0])
        abgleich = difflib.SequenceMatcher(None, [g[2] for g in vorher], [c[2] for c in kandidaten],
                                           autojunk=False)
        paare = []
        for a, b, n in abgleich.get_matching_blocks():
            for k in range(n):
                v, c = vorher[a + k], kandidaten[b + k]
                paare.append((v[0], v[1], c[0] - v[0], c[0], c[1]))
        verschiebung[zid] = paare
    for i, r in enumerate(rects):
        beste, ueberlappung = None, 0.0
        for zid, info in zeilen_vorher.items():
            box = info["box"]
            u = min(r.y1, box.y1) - max(r.y0, box.y0)
            if u > ueberlappung and r.x1 > box.x0 - 1 and r.x0 < box.x1 + 1:
                beste, ueberlappung = zid, u
        if beste is None:
            continue
        paare = verschiebung.get(beste) or []
        links = [p for p in paare if p[1] <= r.x0 + 0.5]
        rechts = [p for p in paare if p[0] >= r.x1 - 0.5]
        nachbar_l = max(links, key=lambda p: p[1]) if links else None
        nachbar_r = min(rechts, key=lambda p: p[0]) if rechts else None
        dl = nachbar_l[2] if nachbar_l else 0.0
        dr = nachbar_r[2] if nachbar_r else dl
        if abs(dl) > r.width + 50 or abs(dr) > r.width + 50:      # Abgleich unplausibel: nicht verschieben
            continue
        aus[i] = (dl, dr, nachbar_l[4] if nachbar_l else None, nachbar_r[3] if nachbar_r else None)
    return aus


def _platzhalter_treppe(rects: list):
    """Bilden die Rechtecke einer Stelle eine Treppe auf EINER Zeile (schräge OCR-Zeile, seitenmodell._ocr_stufen:
    Stücke, die sich senkrecht mindestens zur Hälfte überlappen und waagerecht aneinanderstoßen, ohne sich
    nennenswert zu überdecken), liefert das ihr gemeinsames Rechteck – dort steht der Platzhalter. Sonst None
    (gewöhnliche Stelle, eine Zeile = ein Rechteck). Die schmalen Streifen über der unsichtbaren Textebene eines
    durchsuchbaren Scans liegen im Bildrechteck der Stelle (waagerecht fast ganz überdeckt) und sind keine Treppe:
    dort bleibt der Platzhalter im ersten Rechteck wie bisher."""
    if len(rects) < 2:
        return None
    zone = fitz.Rect(rects[0])
    offen = list(rects[1:])
    # Nachbarstücke einer Treppe überdecken sich nur um ihre Ränder (2 x OCR_RAND) und die geschätzten Glyphen
    stoss = 2 * OCR_RAND + 2.0
    gewachsen = True
    while gewachsen and offen:
        gewachsen = False
        for k in list(offen):
            senkrecht = min(zone.y1, k.y1) - max(zone.y0, k.y0)
            waagerecht = min(zone.x1, k.x1) - max(zone.x0, k.x0)       # Überdeckung; negativ = Lücke
            if (senkrecht >= 0.5 * min(zone.height, k.height)
                    and -2 <= waagerecht <= min(stoss, 0.5 * min(k.width, zone.width))):
                zone |= k
                offen.remove(k)
                gewachsen = True
    if zone == rects[0] or zone.height > 1.6 * rects[0].height:
        return None
    return zone


def _platzhalter_neu_planen(rect, text, ersatz, max_pt):
    """Platzhalter für einen durch die Verschiebung kleiner gewordenen Kasten: (Text, Schriftgröße oder None)."""
    for variante in (text, ersatz, _platzhalter_kurz(ersatz or "")):
        if not variante:
            continue
        fs = _platzhalter_schrift(rect, variante, max(PLATZHALTER_MIN_PT, min(max_pt, PLATZHALTER_MAX_PT)))
        if fs >= PLATZHALTER_MIN_PT:
            return variante, fs
    return text, None


def _platzhalter_verdeckung_pruefen(lauf, nr, seite, kaesten: list) -> None:
    """Nach dem Zeichnen: Kein verbliebenes Wort darf teilweise unter einem grauen Kasten liegen (sonst wäre
    "Versicherungsmakler" als "/ersicherungsmakler" zu lesen). Ganz im Kasten liegende Wörter sind Platzhalter."""
    if not kaesten:
        return
    try:
        woerter = seite.get_text("words", flags=sm.TEXT_FLAGS)
    except Exception:
        return
    verdeckt = []
    for w in woerter:
        r = fitz.Rect(w[:4])
        if r.width <= 0:
            continue
        for k in kaesten:
            if min(r.y1, k.y1) - max(r.y0, k.y0) <= 0.4 * r.height:
                continue
            anteil = max(0.0, min(r.x1, k.x1) - max(r.x0, k.x0)) / r.width
            if 0.15 < anteil < 0.9:
                verdeckt.append(w[4])
                break
    if verdeckt:
        beispiel = ", ".join(repr(v) for v in verdeckt[:3])
        lauf.kollateral.append(f"Seite {nr + 1}: {len(verdeckt)} Wort/Wörter teilweise unter einem Platzhalter, "
                               f"z. B. {beispiel}")


def _platzhalter_kaesten_zeichnen(seite, kaesten: list) -> None:
    """Graue Kästen der Treffer zeichnen wie apply_redactions sie zeichnete: gefüllt und mit 1 pt Rand in derselben
    Farbe (der Rand deckt Tintenreste am Rechteckrand eines Scans ab) – je Kasten ein eigener Pfad, damit die
    Restrisiko-Prüfung jeden einzeln erkennt."""
    if not kaesten:
        return
    form = seite.new_shape()
    for r in kaesten:
        form.draw_rect(r)
        form.finish(color=FUELLFARBE, fill=FUELLFARBE, width=1)
    form.commit()


def _muster_text_entfernen(doc, seite) -> int:
    """Text in Kachelmustern (Füllmuster) der Seite entfernen (Befund R-03): die Textextraktion liefert ihn nicht,
    apply_redactions erreicht ihn nicht – er bliebe im Bild und im Rohstrom. Entfernt werden die BT…ET-Abschnitte
    der Musterströme und der Form-XObjects, die nur über ein Muster erreicht werden (Befund R-03, Runde 2: Muster
    ruft /Fm1 Do auf, der Text steht im XObject); das übrige Muster (Linien, Flächen) bleibt. Form-XObjects, die
    die Seite auch direkt zeichnet, bleiben unverändert (dort erreicht apply_redactions den Text, und sichtbarer
    Text der Seite ginge sonst verloren). Rückgabe: Anzahl geänderter Ströme."""
    geaendert = 0
    try:
        verweise = [x[0] for x in seite.get_xobjects()]
    except Exception:
        verweise = []
    direkt: set = set(verweise)      # ohne Muster erreichbar
    im_muster: set = set()           # Muster und alles, was in ihren Ressourcen steht
    stapel = [(seite.xref, False)] + [(x, False) for x in verweise]
    gesehen: set = set()
    while stapel:
        xref, unter_muster = stapel.pop()
        if (xref, unter_muster) in gesehen or xref <= 0 or len(gesehen) > 1000:
            continue
        gesehen.add((xref, unter_muster))
        for schluessel in ("Resources/Pattern", "Resources/XObject"):
            try:
                art, wert = doc.xref_get_key(xref, schluessel)
                if art == "xref":
                    wert = doc.xref_object(int(wert.split()[0]), compressed=True)
                elif art != "dict":
                    continue
            except Exception:
                continue
            for nummer in re.findall(r"(\d+)\s+0\s+R", wert):
                nummer = int(nummer)
                kind_unter_muster = unter_muster or schluessel.endswith("Pattern")
                (im_muster if kind_unter_muster else direkt).add(nummer)
                stapel.append((nummer, kind_unter_muster))
    for xref in sorted(im_muster - direkt):
        try:
            if not doc.xref_is_stream(xref):
                continue
            if doc.xref_get_key(xref, "PatternType")[1] != "1" and doc.xref_get_key(xref, "Subtype")[1] != "/Form":
                continue                                   # Bilder, Schattierungen
            strom = doc.xref_stream(xref)
            neu = _text_abschnitte_entfernen(strom)
            if neu != strom:
                doc.update_stream(xref, neu)
                geaendert += 1
        except Exception:
            continue
    return geaendert


def _text_abschnitte_entfernen(strom: bytes) -> bytes:
    """BT … ET aus einem Inhaltsstrom entfernen; Zeichenketten, Kommentare und Inline-Bilder werden beim
    Suchen übersprungen."""
    aus, i, n, start = [], 0, len(strom), None
    trenner = b" \t\r\n\x0c\x00()<>[]{}/%"
    while i < n:
        c = strom[i:i + 1]
        if c == b"(":
            tiefe = 0
            while i < n:
                z = strom[i:i + 1]
                if z == b"\\":
                    i += 2
                    continue
                tiefe += (z == b"(") - (z == b")")
                i += 1
                if tiefe == 0:
                    break
            continue
        if c == b"<" and strom[i + 1:i + 2] != b"<":
            j = strom.find(b">", i)
            i = n if j < 0 else j + 1
            continue
        if c == b"%":
            j = strom.find(b"\n", i)
            i = n if j < 0 else j + 1
            continue
        if c.isalpha():
            j = i
            while j < n and strom[j:j + 1] not in trenner:
                j += 1
            wort = strom[i:j]
            if wort == b"BI":                                    # Inline-Bild: bis EI überspringen
                k = strom.find(b"EI", j)
                j = n if k < 0 else k + 2
            elif wort == b"BT" and start is None:
                start = i
            elif wort == b"ET" and start is not None:
                aus.append((start, j))
                start = None
            i = j
            continue
        i += 1
    if not aus:
        return strom
    teile, pos = [], 0
    for a, b in aus:
        teile.append(strom[pos:a])
        pos = b
    teile.append(strom[pos:])
    return b"".join(teile)


def _seite_bearbeiten(lauf: _Lauf, nr: int, m, plan: _Plan, bereiche: list, versteckt: list):
    """Eine Seite schwärzen: Rechtecke aus dem Modell, Platzhalter, Anwenden, Prüfungen."""
    doc = lauf.doc
    seite = doc[nr]
    if seite.rotation:          # nur nach einem Zwischenstand denkbar – Vorbereitung entfernt sie
        from .ocr import drehung_entfernen
        drehung_entfernen(seite)
    modus = m.ocr_modus
    textglyphen = any(z.quelle == "text" for z in m.zeichen)
    woerter_vorher = seite.get_text("words", flags=sm.TEXT_FLAGS) if textglyphen else []

    # 1) Treffer: zusammengefasste Stellen -> Rechtecke je Zeile
    hits = []
    getroffen_text: set = set()
    kategorien: set = set()
    for s, e, fund, ersatz, mitglieder in plan.zusammengefasst(nr):
        teile = m.rechtecke(s, e)
        for f in mitglieder:
            lauf.gefunden.add(id(f))
            kategorien.add(f.get("kategorie", ""))
        if not teile or _unbedeckt(m, s, e, [t[0] for t in teile]):
            # Lokalisierungsgarantie (Vertrag Z1): jede Glyphe der Stelle muss in einem Rechteck liegen –
            # sonst nie still weiter, sondern NICHT_LOKALISIERT (Fehler, Ausgabe _PRUEFEN)
            lauf.nicht_lokalisiert.append(fund.get("text") or m.text[s:e])
            if not teile:
                continue
        rects = [t[0] for t in teile]
        # Nur sichtbarer Text rutscht nach dem Anwenden (M-31); Kästen über Scans, Bildern und der unsichtbaren
        # Textebene eines durchsuchbaren Scans bleiben, wo die Bildpixel entfernt wurden
        verschiebbar = modus != "seite" and all(m.zeichen[g].quelle == "text" for g in m.glyphen(s, e))
        hits.append({"fund": fund, "ersatz": ersatz, "rects": rects, "boxen": [t[1] for t in teile],
                     "groesse": teile[0][2], "grundlinie": teile[0][3], "freiraum": m.freiraum(s, e, rects[0]),
                     "verschiebbar": verschiebbar})
        getroffen_text |= {g for g in m.glyphen(s, e) if m.zeichen[g].quelle == "text"}

    if modus in ("seite", "bilder"):
        lauf.ocr_modus[nr] = modus
        lauf.bildbereiche[nr] = list(m.bilder)
        if modus == "seite":
            _schluesselwoerter_pruefen(lauf, nr, m, kategorien)

    # 2) Redaktionen und Platzhalter planen (nur ENTHALTENE Rechtecke verwerfen). Treffer werden OHNE Füllung
    #    angewendet; die grauen Kästen zeichnet _platzhalter_kaesten_zeichnen danach an der gemessenen Lage
    #    (MuPDF verschiebt den Rest einer Zeile, Befund M-31).
    bereits: list = []
    kaesten: list = []          # graue Kästen der Treffer (werden nach dem Anwenden gezeichnet)
    verschiebbar: list = []     # je Kasten: darf er der verschobenen Zeile folgen (sichtbarer Text, kein Bild)?
    platzhalter: list = []      # [Kasten-Index oder None, Rechteck, Text, Schriftgröße, Grundlinie, Ersatz, max_pt]
    einbrennen: list = []       # Rückfall "Seite als Bild": zusätzlich die vollen Glyphenboxen der Treffer
    for hit in hits:
        paare = [(r, b) for r, b in zip(hit["rects"], hit["boxen"])
                 if not r.is_empty and not any(alt.contains(r) for alt in bereits)]
        if not paare:
            continue
        rects = [r for r, _ in paare]
        lauf.treffer += 1
        lauf.stellen_geschwaerzt += 1
        ersatz = hit["ersatz"]
        if ersatz:
            max_pt = hit["groesse"] if hit["groesse"] > 0 else rects[0].height / 1.6
            zone = _platzhalter_treppe(rects)
            if zone is None:
                r, text, fs = _platzhalter_planen(rects[0], ersatz, max_pt, hit["freiraum"], seite.rect)
            else:
                # schräge Scanzeile in Treppenstücken (M-20): Platzhalter über die ganze Stelle, nicht über die
                # Stücke hinaus (dort ist nichts geschwärzt)
                r = zone
                text, fs = _platzhalter_neu_planen(zone, ersatz, ersatz, max_pt)
            if fs is None:
                lauf.ohne_platzhalter += 1
            else:
                if text != ersatz:
                    lauf.abgekuerzt[text] = ersatz
                if zone is None:
                    rects[0] = r
                platzhalter.append([len(kaesten) if zone is None else None, r, text, fs, hit["grundlinie"], ersatz,
                                    max_pt])
        for r, (_, box) in zip(rects, paare):
            bereits.append(r)
            kaesten.append(r)
            verschiebbar.append(hit["verschiebbar"] and not any(r.intersects(b) for b in m.bilder))
            einbrennen.append(r | (fitz.Rect(box) + (-0.5, -0.5, 0.5, 0.5)))
            seite.add_redact_annot(r, fill=False)
    for eintrag in bereiche:              # manuelle Bereiche: Text UND Bildpixel, Platzhalter
        r, ersatz = (eintrag if isinstance(eintrag, tuple) else (eintrag, PLATZHALTER_BEREICH))
        r = fitz.Rect(r) & seite.rect
        if r.is_empty:
            continue
        lauf.treffer += 1
        fs = _platzhalter_schrift(r, ersatz, PLATZHALTER_MAX_PT)
        if fs >= PLATZHALTER_MIN_PT:
            platzhalter.append([None, r, ersatz, fs, None, ersatz, PLATZHALTER_MAX_PT])
        bereits.append(r)
        einbrennen.append(r)
        seite.add_redact_annot(r, fill=FUELLFARBE)
    if kategorien:
        lauf.kategorien_je_seite[nr] = kategorien

    # 3) Versteckte Ebenen-Inhalte (ohne Platzhalter) und Inhalte außerhalb des Beschnitts
    for r in versteckt:
        bereits.append(r)
        einbrennen.append(r)
        seite.add_redact_annot(r, fill=FUELLFARBE)
    if versteckt:
        lauf.melden("hinweis", "NEBENKANAL_ENTFERNT",
                    f"Seite {nr + 1}: {len(versteckt)} ausgeblendete Inhalt(e) einer Ebene entfernt.", nr)
    leeren: list = []
    if lauf.beschnitt_lokal:
        beschnitt = _beschnitt_rechtecke(seite)
        for r in beschnitt:
            try:
                seite.add_redact_annot(r, fill=False)
                bereits.append(r)
                leeren.append(r)
            except Exception:
                pass
        if beschnitt:
            lauf.beschnitt_seiten.append(nr + 1)

    # 3a) Text in Kachelmustern erreicht apply_redactions nicht (Befund R-03): auf Seiten, deren Text sich nicht
    #     vollständig auslesen lässt, wird er aus den Mustern entfernt – auch ohne Treffer, denn was die OCR dort
    #     nicht erkannt hat, wäre sonst ungeprüft in der Ausgabe
    if modus == "seite" and hasattr(sm._ocr, "textebene_pruefen"):
        try:
            befund = sm._ocr.textebene_pruefen(seite)
            if befund.verborgen >= getattr(sm._ocr, "VERBORGEN_MIN_ZEICHEN", 10) and getattr(befund, "muster", True):
                if _muster_text_entfernen(doc, seite):
                    lauf.melden("hinweis", "NEBENKANAL_ENTFERNT",
                                f"Seite {nr + 1}: Text in Füllmustern entfernt (nicht auslesbar).", nr)
        except Exception:
            pass

    # 4) Anwenden (Text UND Bildpixel), Teilreste prüfen, Kästen und Platzhalter an der gemessenen Lage
    #    zeichnen, Kollateralschaden prüfen. Scheitert MuPDF an der Seite (zyklische Form-XObjects, Befund R-08),
    #    wird sie als Bild geschwärzt.
    als_bild = False
    if bereits:
        bild_vorher = None
        if _bilder is not None and hasattr(_bilder, "bildzustand") and hasattr(_bilder, "nach_schwaerzung"):
            try:
                bild_vorher = _bilder.bildzustand(seite)
            except Exception:
                bild_vorher = None
        beweglich = [k for k, v in zip(kaesten, verschiebbar) if v]
        zeilen_vorher = _platzhalter_zeilen_vorher(m, beweglich) if (textglyphen and beweglich) else {}
        try:
            seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                                   graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                                   text=fitz.PDF_REDACT_TEXT_REMOVE)
        except Exception as fehler:
            als_bild = True
            _seite_als_bild(lauf, nr, seite, m, einbrennen, leeren, fehler)
            seite = doc[nr]
        if not als_bild:
            if bild_vorher is not None:
                try:
                    lauf.bilder_neu_kodiert += int(_bilder.nach_schwaerzung(doc, seite, bild_vorher) or 0)
                except Exception as e:
                    lauf.melden("hinweis", "BILDER_UNGEPRUEFT", f"Geschwärzte Bilder auf Seite {nr + 1} konnten "
                                                                f"nicht neu komprimiert werden ({e}) – die Datei wird "
                                                                f"größer.", nr)
            if getroffen_text:
                _glyphreste_pruefen(lauf, nr, seite, m, getroffen_text)
            verschiebung = _platzhalter_verschiebung(seite, zeilen_vorher, kaesten)
            verschiebung = [v if ok else (0.0, 0.0, None, None) for v, ok in zip(verschiebung, verschiebbar)]
            kaesten = [fitz.Rect(r.x0 + v[0], r.y0, max(r.x1 + v[1], r.x0 + v[0] + 1.0), r.y1)
                       for r, v in zip(kaesten, verschiebung)]
            for eintrag in platzhalter:              # verschobene Kästen: Platzhalter neu einpassen
                index = eintrag[0]
                if index is None or kaesten[index] == eintrag[1]:
                    continue
                r, text, ersatz, max_pt = kaesten[index], eintrag[2], eintrag[5], eintrag[6]
                neu_text, fs = _platzhalter_neu_planen(r, text, ersatz, max_pt)
                if fs is None:                       # in die freie Lücke zu den Nachbarzeichen wachsen
                    links, rechts = verschiebung[index][2], verschiebung[index][3]
                    weit = fitz.Rect(min(r.x0, links + 1.0) if links is not None else r.x0, r.y0,
                                     max(r.x1, rechts - 1.0) if rechts is not None else r.x1, r.y1)
                    neu_text, fs = _platzhalter_neu_planen(weit, text, ersatz, max_pt)
                    if fs is not None:
                        r = kaesten[index] = weit
                eintrag[1], eintrag[2], eintrag[3] = r, neu_text, fs
            _platzhalter_kaesten_zeichnen(seite, kaesten)
        for index, r, text, fs, grundlinie, ersatz, _ in platzhalter:
            if fs is None:
                lauf.ohne_platzhalter += 1
                continue
            if text != ersatz:
                lauf.abgekuerzt[text] = ersatz
            if not _platzhalter_zeichnen(seite, r, text, fs, grundlinie):
                lauf.ohne_platzhalter += 1
        if woerter_vorher and not als_bild:
            _kollateral_pruefen(lauf, nr, seite, woerter_vorher, bereits)
            if modus != "seite":            # Scans: unsichtbare Textebene unter den Kästen ist gewollt
                _platzhalter_verdeckung_pruefen(lauf, nr, seite, kaesten)
        if bild_vorher is None and not als_bild:
            try:
                for info in seite.get_image_info(xrefs=True):
                    xref = info.get("xref") or 0
                    if xref > 0 and any(fitz.Rect(info["bbox"]).intersects(r) for r in bereits):
                        lauf.bild_xrefs.add(xref)
            except Exception:
                pass
        if modus == "seite" or als_bild:
            lauf.scan_seiten_seit_speichern += 1

    # 4a) Inhalte außerhalb des Beschnitts (Gutachten S-05) entfernt das Nebenkanal-Modul – hier schon je Seite:
    #     Scheitert MuPDF an der Seite (zyklische oder zu tief verschachtelte Form-XObjects, Befund R-08), wird sie
    #     als Bild ihres sichtbaren Bereichs neu erzeugt, auch ohne Treffer. Vorher blieb der Inhalt außerhalb der
    #     CropBox (Name, IBAN) still in der Ausgabe, und die Nebenkanal-Bereinigung brach für das ganze Dokument ab.
    if not lauf.beschnitt_lokal and not als_bild and _nebenkanaele is not None:
        entfernen = getattr(_nebenkanaele, "beschnitt_entfernen", None)
        if entfernen is not None:
            try:
                if entfernen(doc, seite):
                    lauf.beschnitt_seiten.append(nr + 1)
            except Exception as fehler:
                als_bild = True
                _seite_als_bild(lauf, nr, seite, m, [], [], fehler)
                seite = doc[nr]
                lauf.scan_seiten_seit_speichern += 1

    # 4b) Abgeschnittener Text (Befund R-03, Runde 2): Zeichen, die ein Beschneidungspfad unsichtbar macht (überlanger
    #     Formularwert, Tabellenzelle), liest pdftotext trotzdem – sie werden entfernt, ohne Sichtbares anzutasten
    if not als_bild:
        seite, als_bild = _abgeschnittenen_text_entfernen(lauf, nr, seite, m)
        if als_bild:
            lauf.scan_seiten_seit_speichern += 1
    lauf.rects_je_seite[nr] = bereits + [k for k in kaesten if k not in bereits]

    # 5) Hinweise zu Grafiken/Bildern (Unterschriften, Stempel, Fotos werden nicht geprüft)
    if m.bilder and modus == "bilder":
        lauf.bild_seiten.append(nr + 1)
    if _hat_kurven(seite):
        lauf.grafik_seiten.append(nr + 1)


ABGESCHNITTEN_RAND = 0.15     # Rechteck je abgeschnittener Glyphe: so viel der Breite (und 0,2 der Höhe) eingerückt –
                              # MuPDF entfernt jede Glyphe, die ein Rechteck auch nur zu ~10 % berührt (gemessen)


def _glyphen_aus(seite, flags) -> list:
    """[(Ursprung, Kasten als Zahlen)] der Zeichen, die get_text mit diesen flags liefert."""
    return [(ch.get("origin") or (0.0, 0.0), ch["bbox"])
            for block in seite.get_text("rawdict", flags=flags).get("blocks", ())
            for zeile in block.get("lines", ()) for sp in zeile.get("spans", ()) for ch in sp.get("chars", ())]


_NACHBARN = ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))


def _drin(menge: set, o) -> bool:
    """Liegt ein Glyphenursprung (auf 1 pt gerundet, ±1) in der Menge?"""
    rx, ry = round(o[0]), round(o[1])
    return any((rx + dx, ry + dy) in menge for dx, dy in _NACHBARN)


def _abgeschnittene_glyphen(seite) -> tuple:
    """(abgeschnitten, sichtbar): Kästen der gezeichneten Glyphen (Zeichenspur), die ein Beschneidungspfad unsichtbar
    macht – get_text liefert sie mit Beschneidung nicht, ohne schon (überlanger Formularwert, Tabellenzelle, Form-
    XObject mit kleiner BBox) –, und die Kästen der sichtbaren Glyphen (nur, wenn es abgeschnittene gibt).
    Unsichtbarer Text (Rendermodus 3) und Text außerhalb der Seite zählen nicht (Beschnitt: Schritt 4a). Kästen
    werden als Zahlen geprüft, nicht als fitz.Rect je Zeichen (läuft auf jeder Seite)."""
    sichtbar = _glyphen_aus(seite, sm.TEXT_FLAGS)
    if not sichtbar:
        return [], []
    bekannt = {(round(o[0]), round(o[1])) for o, _ in sichtbar}
    kandidaten = []
    px0, py0, px1, py1 = seite.rect
    for span in seite.get_texttrace():
        if span.get("type", 0) == 3 or span.get("opacity", 1) == 0:
            continue
        for z in span["chars"]:
            if len(z) < 4 or z[2] is None or chr(z[0]).isspace():
                continue
            b = z[3]
            if not (b[0] < b[2] and b[1] < b[3]) or not (b[0] < px1 and px0 < b[2] and b[1] < py1 and py0 < b[3]):
                continue                            # leerer Kasten oder außerhalb der Seite
            if not _drin(bekannt, z[2]):
                kandidaten.append((z[2], fitz.Rect(b)))
    if not kandidaten:                              # der Normalfall: alles Gezeichnete ist auch auslesbar
        return [], []
    ohne = {(round(o[0]), round(o[1])) for o, _ in _glyphen_aus(seite, sm.TEXT_FLAGS & ~fitz.TEXT_MEDIABOX_CLIP)}
    return [box for o, box in kandidaten if _drin(ohne, o)], [fitz.Rect(b) for _, b in sichtbar]


def _abgeschnittenen_text_entfernen(lauf: _Lauf, nr: int, seite, m):
    """Abgeschnittenen Text der Seite entfernen (Befund R-03, Runde 2): je Glyphe ein eingerücktes Rechteck, nur Text
    (Bilder und Linien bleiben). Berührt ein Rechteck eine sichtbare Glyphe, oder bleibt danach etwas übrig, wird die
    Seite als Bild ihres sichtbaren Bereichs neu erzeugt – Sichtbares bleibt, Unsichtbares verschwindet.
    Rückgabe: (Seite, als Bild)."""
    try:
        abgeschnitten, sichtbar = _abgeschnittene_glyphen(seite)
    except Exception:
        abgeschnitten, sichtbar = [], []
    if not abgeschnitten:
        return seite, False
    zeilen: dict = {}                               # sichtbare Glyphen nach 10-pt-Streifen (schnelle Nachbarsuche)
    for v in sichtbar:
        for k in range(int(v.y0 // 10), int(v.y1 // 10) + 1):
            zeilen.setdefault(k, []).append(v)
    rechtecke, beruehrt = [], False
    for b in abgeschnitten:
        r = b + (ABGESCHNITTEN_RAND * b.width, 0.2 * b.height, -ABGESCHNITTEN_RAND * b.width, -0.2 * b.height)
        nachbarn = {id(v): v for k in range(int(r.y0 // 10), int(r.y1 // 10) + 1) for v in zeilen.get(k, ())}
        if r.is_empty or any(r.intersects(v) for v in nachbarn.values()):
            beruehrt = True
            continue
        rechtecke.append(r)
    fehler = None
    if not beruehrt:
        try:
            for r in rechtecke:
                seite.add_redact_annot(r, fill=False, cross_out=False)
            seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                   text=fitz.PDF_REDACT_TEXT_REMOVE)
            if not _abgeschnittene_glyphen(seite)[0]:
                lauf.melden("hinweis", "NEBENKANAL_ENTFERNT",
                            f"Seite {nr + 1}: {len(abgeschnitten)} abgeschnittene, unsichtbare Zeichen entfernt (z. B. "
                            f"ein zu langer Formularwert).", nr)
                return seite, False
        except Exception as e:
            fehler = e
    _seite_als_bild(lauf, nr, seite, m, [], [], fehler or RuntimeError("abgeschnittener Text"),
                    grund=f"enthielt abgeschnittenen, unsichtbaren Text ({len(abgeschnitten)} Zeichen), der sich "
                          f"nicht einzeln entfernen ließ")
    return lauf.doc[nr], True


def _seite_als_bild(lauf: _Lauf, nr: int, seite, m, einbrennen: list, leeren: list, fehler: BaseException,
                    grund: str = "ist im PDF fehlerhaft aufgebaut und ließ sich nicht direkt bereinigen"):
    """Rückfall, wenn apply_redactions an der Seite scheitert (zyklisches oder zu tief verschachteltes
    Form-XObject: "exception stack overflow", Befund R-08): Seite rendern, Schwärzungen (mit den vollen
    Glyphenboxen der Treffer) einbrennen, Seite durch das Bild ersetzen. Die Kontroll-OCR prüft die Seite danach
    wie einen Scan. Lässt sich die Seite auch nicht rendern, endet die Schwärzung mit einer verständlichen
    Meldung – eine Ausgabe entsteht dann nicht."""
    try:
        from .ocr import _protokollieren
        _protokollieren(fehler)
    except Exception:
        pass
    if _bilder is None or not hasattr(_bilder, "seite_als_bild_schwaerzen"):
        raise RuntimeError(f"Seite {nr + 1} ließ sich nicht schwärzen ({type(fehler).__name__}: {fehler})") from fehler
    try:
        for annot in list(seite.annots()):            # noch nicht angewendete Schwärzungs-Anmerkungen
            seite.delete_annot(annot)
        _bilder.seite_als_bild_schwaerzen(lauf.doc, seite, einbrennen, leeren, FUELLFARBE)
    except Exception as e:
        raise RuntimeError(f"Seite {nr + 1} ist im PDF fehlerhaft aufgebaut und ließ sich weder schwärzen noch als "
                           f"Bild schwärzen ({type(e).__name__}: {e}) – bitte die Datei neu als PDF speichern "
                           f"(z. B. über „Drucken als PDF“) und erneut versuchen.") from e
    lauf.ocr_modus[nr] = "seite"
    lauf.bildbereiche[nr] = []
    if m is not None and m.ocr_winkel is None:
        m.ocr_winkel = 0
    lauf.melden("hinweis", "SEITE_ALS_BILD",
                f"Seite {nr + 1} {grund} – sie wurde als Bild neu erzeugt und dabei geschwärzt (Text dort nicht mehr "
                f"markierbar, für Menschen und KI aber lesbar).", nr)


def _unbedeckt(m, start: int, ende: int, rects: list) -> list:
    """Glyphen der Stelle, die kein Schwärzungsrechteck berührt (Textebene: Glyphenbox; OCR: Wortbox).
    Leerraum und Glyphen ohne gültige Box zählen nicht."""
    offen = []
    for g in m.glyphen(start, ende):
        z = m.zeichen[g]
        if z.c.isspace():
            continue
        wid = m.wort_ids[g] if g < len(m.wort_ids) else -1
        box = m.ocr_boxen[wid] if z.quelle != "text" and 0 <= wid < len(m.ocr_boxen) else z.rect
        if not (box.x1 > box.x0 and box.y1 > box.y0):
            continue
        if not any(box.intersects(r) for r in rects):
            offen.append(g)
    return offen


def _glyphreste_pruefen(lauf, nr, seite, m, getroffen: set):
    """Nach apply_redactions: Je Zeile mit Treffer müssen genau die Treffer-Glyphen fehlen. Vergleich über
    die Zeichen der Zeile (nicht über Koordinaten – MuPDF verschiebt Resttext einer Zeile). Zusätzliche
    Zeichen gegenüber der Erwartung, die zum Treffer gehören = Teilrest (Gutachten S-07)."""
    try:
        rd = seite.get_text("rawdict", flags=sm.TEXT_FLAGS)
    except Exception:
        return
    s = seite.rect
    sx0, sy0, sx1, sy1 = s.x0 - 0.5, s.y0 - 0.5, s.x1 + 0.5, s.y1 + 0.5
    nachher = []      # (Grundlinie, x0, x1, Counter)
    for block in rd.get("blocks", []):
        for zeile in block.get("lines", []):
            zs = [ch for sp in zeile.get("spans", []) for ch in sp.get("chars", [])
                  if not ch["c"].isspace() and sx0 <= (ch["bbox"][0] + ch["bbox"][2]) / 2 <= sx1
                  and sy0 <= (ch["bbox"][1] + ch["bbox"][3]) / 2 <= sy1]
            if zs:
                nachher.append((sum(ch["origin"][1] for ch in zs) / len(zs),
                                min(ch["bbox"][0] for ch in zs), max(ch["bbox"][2] for ch in zs),
                                Counter(unicodedata.normalize("NFKC", ch["c"]) for ch in zs)))
    je_zeile: dict = {}
    for g, z in enumerate(m.zeichen):
        je_zeile.setdefault(z.zeile, []).append(g)
    for zid in sorted({m.zeichen[g].zeile for g in getroffen}):
        glyphen = je_zeile.get(zid, [])
        vorher = [m.zeichen[g] for g in glyphen if not m.zeichen[g].c.isspace()]
        if not vorher:
            continue
        grundlinie = sum(z.grundlinie for z in vorher) / len(vorher)
        x0 = min(z.rect.x0 for z in vorher)
        x1 = max(z.rect.x1 for z in vorher)
        hoehe = max(z.groesse for z in vorher) or 10.0
        erwartet = Counter(unicodedata.normalize("NFKC", m.zeichen[g].c) for g in glyphen
                           if g not in getroffen and not m.zeichen[g].c.isspace())
        treffer = Counter(unicodedata.normalize("NFKC", m.zeichen[g].c) for g in glyphen
                          if g in getroffen and not m.zeichen[g].c.isspace())
        da = Counter()
        for g_y, nx0, nx1, zaehler in nachher:
            if abs(g_y - grundlinie) <= 0.3 * hoehe and nx0 < x1 + 1 and nx1 > x0 - 1:
                da += zaehler
        rest = (da - erwartet) & treffer
        if rest:
            beispiel = "".join(sorted(rest.elements()))[:12]
            lauf.teilreste.append(f"Seite {nr + 1}: {sum(rest.values())} Zeichen eines Treffers nicht "
                                  f"entfernt ({beispiel!r})")


def _kollateral_pruefen(lauf, nr, seite, woerter_vorher, rects):
    """Wörter, die kein Treffer waren, müssen nach der Schwärzung noch da sein (gleicher Text auf
    gleicher Höhe – MuPDF verschiebt Resttext einer Zeile horizontal leicht)."""
    try:
        nachher: dict = {}
        for w in seite.get_text("words", flags=sm.TEXT_FLAGS):
            nachher.setdefault(w[4], []).append(fitz.Rect(w[:4]))
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
        if not any(min(r.y1, n.y1) - max(r.y0, n.y0) > 0.5 * r.height for n in nachher.get(w[4], ())):
            beschaedigt.append(w[4])
    if beschaedigt:
        beispiel = ", ".join(repr(b) for b in beschaedigt[:3])
        lauf.kollateral.append(f"Seite {nr + 1}: {len(beschaedigt)} Nachbarwort/-wörter beschädigt "
                               f"(enger Zeilenabstand), z. B. {beispiel}")


def _schluesselwoerter_pruefen(lauf, nr, m, kategorien_mit_treffer: set):
    """M-50: Schlüsselwort auf einer OCR-Seite gelesen, aber kein Fund dieser Kategorie – warnen."""
    ocr_zeilen = {zid for b in m.bloecke if b.quelle != "text" for zid in b.zeilen}
    ocr_text = " ".join(m.text[z.start:z.ende] for z in m.zeilen if z.id in ocr_zeilen)
    if not ocr_text.strip():
        return
    kategorien = {f.get("kategorie", "") for f in lauf.funde}
    for kategorie, anzeige, muster in _SCHLUESSELWOERTER:
        treffer = muster.search(ocr_text)
        if not treffer or kategorie in kategorien_mit_treffer:
            continue
        hinweis = "" if kategorie in kategorien else " (Kategorie nicht in der Fundliste)"
        lauf.melden("warnung", "SCHLUESSELWORT_OHNE_FUND",
                    f"Seite {nr + 1}: Schlüsselwort »{treffer.group(0)}« gelesen, aber kein {anzeige}-Fund "
                    f"lokalisiert{hinweis} – OCR-Verleser möglich, bitte prüfen!", nr)


# ----------------------------------------------------------------------
# Selbstkontrolle
# ----------------------------------------------------------------------
def _innerhalb(rect, rects) -> bool:
    mitte = fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
    return any(r.contains(mitte) for r in rects)


def _nadeln(fund: dict, lauf: _Lauf) -> list:
    """Suchtexte der Selbstkontrolle für einen Fund: Fundtext und Texte seiner geschwärzten Stellen."""
    texte = [fund.get("text", "")]
    for st in fund.get("stellen") or []:
        if st.get("an", True) and st.get("text"):
            texte.append(st["text"])
    if fund.get("text") in lauf.anfangstreffer:
        texte.append(lauf.anfangstreffer[fund["text"]])
    gesehen, aus = set(), []
    for t in texte:
        k = _vergleichstext(t)
        if k and k not in gesehen:
            gesehen.add(k)
            aus.append(t)
    return aus


def _abgewaehlt_verbrauchen(lauf: _Lauf, nr: int, text: str, teile) -> bool:
    """Ist das Vorkommen eine bewusst abgewählte Stelle (gleiche Seite, gleicher Text, gleiche Zeile)?"""
    vergleich = _vergleichstext(text)
    grundlinie = teile[0][3] if teile else None
    for eintrag in lauf.abgewaehlt:
        e_nr, e_text, e_grund = eintrag
        if e_nr != nr or e_text != vergleich:
            continue
        if e_grund is not None and grundlinie is not None and abs(e_grund - grundlinie) > 2.0:
            continue
        lauf.abgewaehlt.remove(eintrag)
        return True
    return False


def _kontroll_woerter(lauf: _Lauf, ausgabe: Path, nr: int, rects: list):
    modus = lauf.ocr_modus.get(nr)
    if not modus or lauf.ocr is None or not (rects or lauf.kategorien_je_seite.get(nr)):
        return None
    lauf.melde(f"   Kontroll-OCR: Seite {nr + 1} …")
    woerter = []
    ergebnis_fn = getattr(lauf.ocr, "ergebnis", None)
    ausgefallen = False
    if modus == "seite":
        # dieselbe Ausrichtung wie beim Original (Gutachten S-08): die Ausgabe enthält zu wenige Wörter,
        # um sie neu zu bestimmen. Vollständiges Ergebnis (10-Tupel mit Ausrichtung und Schräglagen-Korrektur),
        # damit das Kontrollmodell die Zeilen genauso bildet wie das der Analyse
        if ergebnis_fn is not None:
            e = ergebnis_fn(ausgabe, nr, OCR_DPI, winkel=lauf.winkel(nr))
            ausgefallen = bool(e.get("fehler"))
            w = e.get("woerter")
        else:
            try:
                w, _ = lauf.ocr.woerter(ausgabe, nr, OCR_DPI, winkel=lauf.winkel(nr))
            except TypeError:
                w, _ = lauf.ocr.woerter(ausgabe, nr, OCR_DPI)
        woerter += list(w or [])
    else:
        # Bildbereiche ebenfalls mit der Ausrichtung der Analyse (Befund M-51: sonst lief die volle
        # Ausrichtungssuche – bis zu 8 OCR-Läufe je Foto – ein zweites Mal); als Vorgabe für die Ausgabe hinterlegt,
        # damit die Restrisiko-Prüfung dasselbe Ergebnis aus dem Zwischenspeicher bekommt
        bekannt = getattr(lauf.ocr, "winkel_falls_bekannt", None)
        vorgeben = getattr(lauf.ocr, "winkel_vorgeben", None)
        for bereich in lauf.bildbereiche.get(nr, []):
            winkel = None
            if bekannt is not None and vorgeben is not None:
                try:
                    winkel = bekannt(lauf.pdf_pfad, nr, OCR_DPI, clip=bereich)
                    if winkel is not None:          # unbekannt (z. B. OCR-Fehler der Analyse): wie bisher suchen
                        winkel = int(winkel)
                        vorgeben(ausgabe, nr, bereich, winkel)
                except Exception:
                    winkel = None
            e = None
            if ergebnis_fn is not None:
                try:
                    e = ergebnis_fn(ausgabe, nr, OCR_DPI, clip=bereich, winkel=winkel)
                except TypeError:                   # ältere Dienste/Attrappen ohne diese Parameter
                    e = None
            if e is not None:
                ausgefallen = ausgefallen or bool(e.get("fehler"))
                w = e.get("woerter")
            else:
                try:
                    w, _ = lauf.ocr.woerter(ausgabe, nr, OCR_DPI, clip=bereich)
                except TypeError:
                    w, _ = lauf.ocr.woerter(ausgabe, nr)
            woerter += list(w or [])
    if ausgefallen:
        # Befund R-06: ein Ausfall der Kontroll-OCR darf nicht verschluckt werden – die Seite ist dann ungeprüft
        lauf.restrisiko_fehler = True
        lauf.melden("warnung", "OCR_FEHLER",
                    f"Seite {nr + 1}: Die Kontroll-Texterkennung der Ausgabe ist fehlgeschlagen – die Schwärzung "
                    f"dieser Seite ist ungeprüft. Ausgabe bitte selbst prüfen.", nr)
    lauf.abbruch_pruefen()
    return [w for w in woerter if not _innerhalb(fitz.Rect(w[:4]), rects)]


def _selbstkontrolle(lauf: _Lauf, ausgabe: Path) -> list:
    """Sucht alle angehakten Funde in der AUSGABE – mit demselben Seitenmodell und demselben Vergleicher
    wie Analyse und Schwärzung (alle Schreibweisen, Ganzwort; Scan-Seiten per Kontroll-OCR). Platzhalter
    (Treffer innerhalb der gesetzten Rechtecke) und bewusst abgewählte Stellen zählen nicht.
    Rückgabe: Fundtexte, die noch auffindbar sind."""
    reste: list = []
    pruef_funde = [f for f in lauf.funde
                   if f.get("text") and (not f.get("stellen") or any(st.get("an", True) for st in f["stellen"]))]
    nadeln = {id(f): (modus_fuer(f.get("kategorie", "")), _nadeln(f, lauf)) for f in pruef_funde}
    vorab = getattr(lauf.ocr, "vorab", None)
    if vorab is not None:
        # Kontroll-OCR aller Scan-Seiten mit Treffern parallel einreihen (Gutachten PERF-05)
        seiten = [nr for nr, modus in lauf.ocr_modus.items()
                  if modus == "seite" and (lauf.rects_je_seite.get(nr) or lauf.kategorien_je_seite.get(nr))]
        if seiten:
            try:
                vorab(ausgabe, seiten, OCR_DPI, winkel={nr: lauf.winkel(nr) for nr in seiten})
            except Exception:
                pass
    kontrolle = fitz.open(ausgabe)
    try:
        for nr in range(len(kontrolle)):
            lauf.abbruch_pruefen()
            seite = kontrolle[nr]
            rects = lauf.rects_je_seite.get(nr, [])
            woerter = _kontroll_woerter(lauf, ausgabe, nr, rects)
            quelle = "bild" if lauf.ocr_modus.get(nr) == "bilder" else "ocr"
            m = sm.seite_aufbauen(seite, nr, ocr_woerter=woerter, ocr_quelle=quelle)
            if not m.text.strip():
                continue
            for fund in pruef_funde:
                if fund["text"] in reste:
                    continue
                modus, suchtexte = nadeln[id(fund)]
                rest = False
                for nadel in suchtexte:
                    for s, e in ganzwort_stellen(m, nadel, modus):
                        teile = m.rechtecke(s, e)
                        if teile and all(_innerhalb(t[1], rects) for t in teile):
                            continue                       # Platzhaltertext
                        if _abgewaehlt_verbrauchen(lauf, nr, m.text[s:e], teile):
                            continue
                        rest = True
                        break
                    if rest:
                        break
                if rest:
                    reste.append(fund["text"])
    finally:
        kontrolle.close()
    return reste


# ----------------------------------------------------------------------
# Hauptfunktion
# ----------------------------------------------------------------------
def schwaerze_pdf(pdf_pfad, funde: list, melde=None, fortschritt=None, abbruch=None, ocr=None,
                  ocr_cache=None, ziel_ordner=None, modell=None, manuelle_bereiche=None,
                  manuelle_stellen=None, freigabe_erforderlich: bool = False, profil: str = "hoch") -> dict:
    """Ersetzt alle übergebenen Funde durch ihre Platzhalter – auch in Scans (Bildpixel werden mit
    entfernt) – und schreibt eine neutral benannte Ausgabedatei.

    Rückgabe: {"original", "ausgabe", "treffer", "uebersprungen", "warnungen", "hinweise", "reste", "fehler",
               "verdacht", "status" ("fertig"|"pruefen"|None), "stellen_geschwaerzt",
               "stellen_nicht_lokalisiert", "meldungen", "ausgabe_pruefen"}.
    funde: Funde der Analyse (mit "stellen", nur "an": True wird geschwärzt) oder alte Funde (nur "text");
    modell: Seitenmodell der Analyse (Fingerabdruck-Vergleich); manuelle_bereiche: {seite: [Rect]};
    manuelle_stellen: {seite: [(start, ende, ersatz)]}; freigabe_erforderlich: Ausgabe immer _PRUEFEN.
    melde(text): Protokolltext; fortschritt(seite_1basiert, seiten_gesamt); abbruch: threading.Event;
    ocr: OcrDienst (sonst eigener); ocr_cache: {Seitenindex: Wortliste} aus der Analyse;
    ziel_ordner: sonst <Ordner der PDF>/anonymisiert."""
    pdf_pfad = Path(pdf_pfad)
    ergebnis = {"original": pdf_pfad, "ausgabe": None, "treffer": 0, "uebersprungen": 0,
                "warnungen": [], "hinweise": [], "reste": [], "fehler": None, "verdacht": [], "status": None,
                "stellen_geschwaerzt": 0, "stellen_nicht_lokalisiert": 0, "meldungen": [],
                "ausgabe_pruefen": False}
    funde = [dict(f) for f in (funde or []) if str(f.get("text", "")).strip() or f.get("stellen")]
    for f in funde:
        f["text"] = str(f.get("text", "")).strip()
    bereiche = {int(k): [fitz.Rect(r) for r in v] for k, v in (manuelle_bereiche or {}).items() if v}
    stellen_manuell = {int(k): list(v) for k, v in (manuelle_stellen or {}).items() if v}
    if not funde and not bereiche and not stellen_manuell:
        ergebnis["warnungen"].append(WARNUNG_KEIN_TREFFER)
        ergebnis["meldungen"].append({"art": "warnung", "code": "KEIN_TREFFER", "text": WARNUNG_KEIN_TREFFER,
                                      "seite": None})
        return ergebnis

    ziel = Path(ziel_ordner) if ziel_ordner else pdf_pfad.parent / "anonymisiert"
    eigener_dienst = None
    if ocr is None:
        ocr = eigener_dienst = OcrDienst()
    lauf = _Lauf(pdf_pfad, funde, melde, fortschritt, abbruch, ocr, ocr_cache, ziel)
    lauf.analyse_modell = modell
    try:
        try:
            lauf.doc = fitz.open(pdf_pfad)
        except Exception as e:
            ergebnis["fehler"] = f"Konnte nicht geöffnet werden: {e}"
            return ergebnis
        if lauf.doc.needs_pass:
            ergebnis["fehler"] = "Passwortgeschützt – übersprungen."
            return ergebnis
        _schwaerzen(lauf, ergebnis, bereiche, stellen_manuell, freigabe_erforderlich, profil)
    except _Abgebrochen:
        ergebnis["fehler"] = ABGEBROCHEN
        ergebnis["ausgabe"] = None
        ergebnis["status"] = None
        lauf.meldungen.append({"art": "fehler", "code": "ABGEBROCHEN", "text": ABGEBROCHEN, "seite": None})
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
        ergebnis["meldungen"] = lauf.meldungen
    return ergebnis


def _schwaerzen(lauf: _Lauf, ergebnis: dict, bereiche: dict, stellen_manuell: dict,
                freigabe_erforderlich: bool, profil: str):
    doc = lauf.doc
    seiten = len(doc)
    lauf.abbruch_pruefen()

    # 1) Dieselbe Vorbereitung wie die Analyse (bake, Drehung, Ebenen, /ActualText)
    vorbereitung = sm.dokument_vorbereiten(doc)
    if vorbereitung.get("dokument") is not None and vorbereitung["dokument"] is not doc:
        doc.close()                                           # Ebenen: neu geöffnete Fassung
        doc = lauf.doc = vorbereitung["dokument"]
    zaehler = dict(vorbereitung["zaehler"])
    if vorbereitung.get("bake_fehler"):
        lauf.melden("warnung", "FORMULAR_EINGEBRANNT",
                    f"Formularfelder/Anmerkungen konnten nicht eingebrannt werden ({vorbereitung['bake_fehler']}) – "
                    f"Feldinhalte in der Ausgabe bitte prüfen.")
    if zaehler.get("formularfelder"):
        lauf.melden("hinweis", "FORMULAR_EINGEBRANNT",
                    "Formularfelder wurden eingebrannt und mitgeschwärzt – die Ausgabe ist nicht mehr ausfüllbar.")
    if zaehler.get("xfa"):
        lauf.melden("warnung", "XFA", "XFA-Formular: Feldinhalte können nicht geprüft werden – die XFA-Daten "
                                      "werden aus der Ausgabe entfernt.")

    # 2) Seitenmodell (frisch, OCR aus dem Cache der Analyse) und Abgleich mit dem Modell der Analyse
    dok = sm.dokument_aufbauen(doc, lauf.pdf_pfad, ocr=lauf.ocr, ocr_cache=lauf.ocr_cache, melde=lauf.melde,
                               abbruch=lauf.abbruch, warnungen=lauf.warnungen, hinweise=lauf.hinweise,
                               meldungen=lauf.meldungen, vorbereitung=vorbereitung, analyse_meldungen=False)
    lauf.modell = dok
    ana = lauf.analyse_modell
    if ana is not None and getattr(ana, "fingerabdruck", None) != dok.fingerabdruck:
        ana_seiten = getattr(ana, "seiten", [])
        lauf.modell_abweichung = [nr for nr in range(len(dok.seiten))
                                  if nr >= len(ana_seiten) or ana_seiten[nr].fingerabdruck != dok.seiten[nr].fingerabdruck]
        if lauf.modell_abweichung or len(ana_seiten) != len(dok.seiten):
            seiten_text = ", ".join(str(n + 1) for n in lauf.modell_abweichung[:8]) or "?"
            lauf.melden("warnung", "MODELL_ABWEICHUNG",
                        f"Das Dokument liest sich beim Schwärzen anders als bei der Analyse (Seite(n) {seiten_text}) – "
                        f"die Fundstellen wurden dort neu gesucht. Ergebnis bitte prüfen.")

    # 3) Stellen planen
    plan = _Plan()
    _planen(lauf, plan, dok, stellen_manuell, bereiche)
    lauf.abbruch_pruefen()

    # 4) Inhalte außerhalb des Beschnitts: das Nebenkanal-Modul (falls vorhanden) entfernt sie selbst
    lauf.beschnitt_lokal = not (_nebenkanaele is not None and hasattr(_nebenkanaele, "nebenkanaele_entfernen"))

    # 5) Seiten
    versteckt = vorbereitung.get("versteckt", {})
    ocr_seiten = 0
    for nr in range(seiten):
        lauf.abbruch_pruefen()
        if lauf.fortschritt:
            lauf.fortschritt(nr + 1, seiten)
        m = dok.seiten[nr]
        _seite_bearbeiten(lauf, nr, m, plan, bereiche.get(nr, []), versteckt.get(nr, []))
        if m.ocr_modus == "seite":
            ocr_seiten += 1
        if lauf.scan_seiten_seit_speichern >= STAPEL_SCANSEITEN:
            lauf.abbruch_pruefen()
            lauf.zwischenspeichern(nr)
    doc = lauf.doc
    ergebnis["treffer"] = lauf.treffer
    ergebnis["stellen_geschwaerzt"] = lauf.stellen_geschwaerzt

    # 5a) Nebenkanäle – nach allen Schwärzungen, vor dem Speichern (Vertrag des Moduls nebenkanaele)
    lauf.melden("hinweis", "NEBENKANAL_ENTFERNT", _nebenkanaele_bereinigen(lauf, doc, zaehler))

    # 6) Nicht lokalisierte Funde/Stellen
    # Funde ohne Stellen (alte Aufrufer), deren Text nirgends vorkommt: Warnung wie bisher. Stellen der
    # Analyse, die im frischen Modell nicht wiederzufinden sind, sind ein Widerspruch (MUSS 0 sein) ->
    # Fehler-Meldung und _PRUEFEN.
    nicht_gefunden = list(dict.fromkeys(lauf.nicht_gefunden))
    ergebnis["uebersprungen"] = len(nicht_gefunden)
    nicht_lokalisiert = list(lauf.nicht_lokalisiert)
    ergebnis["stellen_nicht_lokalisiert"] = len(nicht_lokalisiert)
    if nicht_gefunden:
        beispiele = ", ".join(repr(t) for t in nicht_gefunden[:6])
        rest = f" (+{len(nicht_gefunden) - 6} weitere)" if len(nicht_gefunden) > 6 else ""
        lauf.melden("warnung", "NICHT_LOKALISIERT",
                    f"{len(nicht_gefunden)} Fund(e) konnten im Dokument nicht lokalisiert werden und bleiben ggf. "
                    f"sichtbar – bitte prüfen: {beispiele}{rest}")
    if nicht_lokalisiert:
        eindeutig = list(dict.fromkeys(nicht_lokalisiert))
        beispiele = ", ".join(repr(t) for t in eindeutig[:6])
        rest = f" (+{len(eindeutig) - 6} weitere)" if len(eindeutig) > 6 else ""
        lauf.melden("fehler", "NICHT_LOKALISIERT",
                    f"{len(nicht_lokalisiert)} Fundstelle(n) der Analyse sind im Dokument nicht mehr auffindbar "
                    f"(Datei geändert?) und bleiben ggf. sichtbar – bitte prüfen: {beispiele}{rest}")
    if lauf.treffer == 0:
        lauf.melden("warnung", "KEIN_TREFFER", WARNUNG_KEIN_TREFFER)
        ergebnis["warnungen"] = lauf.warnungen
        ergebnis["hinweise"] = lauf.hinweise
        return
    if ocr_seiten:
        lauf.melden("hinweis", "OCR_GELESEN", f"{ocr_seiten} Seite(n) als Scan per OCR geschwärzt (Bildpixel entfernt).")
    if lauf.anfangstreffer:
        paare = "; ".join(f"{k!r} → {v!r}" for k, v in list(lauf.anfangstreffer.items())[:5])
        lauf.melden("warnung", "NICHT_LOKALISIERT",
                    f"{len(lauf.anfangstreffer)} Fund(e) kamen so im Dokument nicht vor und wurden nur mit ihrem "
                    f"Anfang geschwärzt (Fundtext endet mitten im Wort?): {paare}")
    if lauf.abgekuerzt:
        paare = ", ".join(f"{k} = {v}" for k, v in sorted(lauf.abgekuerzt.items()))
        lauf.melden("hinweis", "PLATZHALTER_GEKUERZT", f"Platzhalter in engen Lücken abgekürzt: {paare}.")
    if lauf.ohne_platzhalter:
        lauf.melden("hinweis", "PLATZHALTER_GEKUERZT",
                    f"{lauf.ohne_platzhalter} Stelle(n) ohne Platzhalter-Text (Lücke zu klein) – geschwärzt sind "
                    f"sie trotzdem.")
    for k in lauf.kollateral:
        lauf.melden("hinweis", "NACHBARWORT_BESCHAEDIGT", k)
    if lauf.bild_seiten:
        lauf.melden("hinweis", "BILDER_UNGEPRUEFT",
                    f"Seite(n) {', '.join(map(str, lauf.bild_seiten))}: enthalten Bilder – maschinenlesbarer Text "
                    f"darin wurde per OCR geprüft, Unterschriften, Fotos und Handschrift nicht.")
    if lauf.grafik_seiten:
        lauf.melden("hinweis", "VEKTORGRAFIK",
                    f"Seite(n) {', '.join(map(str, lauf.grafik_seiten))}: enthalten Grafiken/Zeichnungen "
                    f"(Unterschrift? Stempel? Logo?), die nicht geprüft werden.")
    if lauf.beschnitt_seiten:
        lauf.melden("hinweis", "NEBENKANAL_ENTFERNT",
                    f"Seite(n) {', '.join(map(str, lauf.beschnitt_seiten))}: Inhalte außerhalb des sichtbaren "
                    f"Seitenbereichs (Beschnitt) entfernt.")
    if lauf.ocr is not None:
        for h in getattr(lauf.ocr, "hinweise", []):
            if h not in lauf.hinweise:
                lauf.hinweise.append(h)

    # 7) Speichern (erst unter Hilfsnamen), Selbstkontrolle, Restrisiko, dann endgültiger Name
    lauf.bilder_kodieren()
    if lauf.bilder_neu_kodiert:
        lauf.hinweise.append(f"{lauf.bilder_neu_kodiert} geschwärzte(s) Bild(er) neu komprimiert.")
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
    reste = list(_selbstkontrolle(lauf, tmp))
    if lauf.teilreste:
        reste += [t for t in lauf.teilreste if t not in reste]
        lauf.melden("warnung", "RESTE", f"{len(lauf.teilreste)} Treffer wurden nur teilweise entfernt (Teilrest): "
                                        + "; ".join(lauf.teilreste[:4]))
    ergebnis["reste"] = reste
    if reste:
        beispiele = ", ".join(repr(t) for t in reste[:5])
        lauf.melden("warnung", "RESTE",
                    f"Selbstkontrolle: {len(reste)} Fundtext(e) sind in der Ausgabe noch auffindbar ({beispiele}) – "
                    f"Datei als _PRUEFEN abgelegt, unbedingt manuell prüfen!")
    verdacht = []
    if _restrisiko is not None and hasattr(_restrisiko, "restrisiko_pruefen"):
        lauf.abbruch_pruefen()
        import time as _zeit
        beginn = _zeit.perf_counter()
        try:
            platzhalter = sorted({f.get("ersatz") for f in lauf.funde if f.get("ersatz")}
                                 | set(lauf.abgekuerzt) | {PLATZHALTER_BEREICH})
            # Was die Prüfung über die Seiten wissen darf, ohne die Erkennung zu teilen: Art und Ausrichtung der OCR
            # je Seite (die Kontroll-OCR der Selbstkontrolle liegt damit schon im Zwischenspeicher – kein zweiter
            # OCR-Lauf), die OCR-Wörter unveränderter Seiten (aus der Analyse), die Formularfelder des Originals und
            # die bewusst abgewählten Stellen (Entscheidung der Nutzerin, kein Verdacht).
            ocr_modus = dict(lauf.ocr_modus)
            zusatz = {"ocr_modus": ocr_modus,
                      "winkel": {nr: lauf.winkel(nr) for nr, art in ocr_modus.items()
                                 if art == "seite" and lauf.rects_je_seite.get(nr)},
                      "bildbereiche": dict(lauf.bildbereiche),
                      "ocr_woerter": {nr: list(lauf.ocr_cache[nr]) for nr in ocr_modus
                                      if nr in lauf.ocr_cache and not lauf.rects_je_seite.get(nr)},
                      "felder": list(getattr(lauf.modell, "felder", None) or []),
                      "abgewaehlt": [(st.get("seite"), st.get("text") or f.get("text", "")) for f in lauf.funde
                                     for st in (f.get("stellen") or []) if not st.get("an", True)],
                      "abbruch": lauf.abbruch}
            verdacht = list(_restrisiko.restrisiko_pruefen(
                tmp, ocr=lauf.ocr, platzhalter=platzhalter, profil=profil,
                nie=getattr(lauf.analyse_modell, "nie", None), **zusatz) or [])
        except _Abgebrochen:
            raise
        except Exception as e:
            lauf.melden("warnung", "VERDACHT", f"Restrisiko-Prüfung ist ausgefallen ({e}) – Ausgabe bitte prüfen.")
            verdacht = []
            lauf.restrisiko_fehler = True
        ergebnis["dauer_restrisiko_s"] = round(_zeit.perf_counter() - beginn, 3)
    ergebnis["verdacht"] = verdacht
    if verdacht:
        lauf.melden("warnung", "VERDACHT",
                    f"Restrisiko: {len(verdacht)} Stelle(n) sehen nach personenbezogenen Daten aus, wurden aber nicht "
                    f"geschwärzt – Datei als _PRUEFEN abgelegt, bitte prüfen.")
    unsicher = bool(nicht_lokalisiert or lauf.modell_abweichung or lauf.restrisiko_fehler)
    pruefen = bool(reste or verdacht or freigabe_erforderlich or unsicher)
    if freigabe_erforderlich and not (reste or verdacht or unsicher):
        lauf.melden("hinweis", "AUSGABE_PRUEFEN", "Freigabe vor Weitergabe ist eingeschaltet – die Ausgabe bleibt "
                                                  "_PRUEFEN, bis sie in der Vorschau freigegeben wird.")
    elif pruefen and not (reste or verdacht):
        lauf.melden("warnung", "AUSGABE_PRUEFEN", "Ausgabe als _PRUEFEN abgelegt – bitte die Warnungen oben prüfen.")
    lauf.abbruch_pruefen()
    try:
        ausgabe = _ausgabe_reservieren(lauf.ziel, pruefen=pruefen)
        os.replace(tmp, ausgabe)
    except OSError as e:
        ergebnis["fehler"] = f"Ausgabe konnte nicht abgelegt werden ({e}) – Ordner »{lauf.ziel}« beschreibbar?"
        ergebnis["warnungen"] = lauf.warnungen
        ergebnis["hinweise"] = lauf.hinweise
        return
    lauf.tmp_pfade.remove(tmp)
    ergebnis["ausgabe"] = ausgabe
    ergebnis["status"] = "pruefen" if pruefen else "fertig"
    ergebnis["ausgabe_pruefen"] = pruefen
    try:
        _zuordnung_anhaengen(lauf.ziel, ausgabe, lauf.pdf_pfad)
        lauf.melden("hinweis", "ZUORDNUNG", f"Zuordnung Original ↔ Ausgabe steht in {lauf.ziel / _ZUORDNUNG} "
                                            f"(nicht mit weitergeben).")
    except OSError as e:
        lauf.melden("warnung", "ZUORDNUNG", f"Zuordnungsdatei _zuordnung.txt konnte nicht geschrieben werden: {e}")
    ergebnis["warnungen"] = lauf.warnungen
    ergebnis["hinweise"] = lauf.hinweise
