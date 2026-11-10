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
  * Nur echte PDFs (Gutachten R-01): ein Bild oder eine Webseite mit der Endung .pdf wird vor jedem
    Seitenzugriff abgewiesen (sonst Absturz im C-Code von PyMuPDF).
  * Status _PRUEFEN (Gutachten R-07/R-11) außer bei Resten, Verdacht, nicht lokalisierten Stellen und
    Modellabweichung auch, wenn die Ausgabe aus anderen Gründen nicht als geprüft gelten kann: Scan-Seite kaum
    lesbar (wenige Wörter UND schlecht gelesen oder viel ungelesene Tinte), OCR unplausibel oder ohne Text (aber mit
    Tinte), OCR-Fehler, XFA-Formular, beschädigte und von MuPDF reparierte Datei, beschädigtes Bild (abgebrochenes
    JPEG), Schlüsselwort mit ungeschwärztem Wert dahinter, Ausgabe nur wegen der Nebenkanäle. Die Gründe stehen in
    der Warnung AUSGABE_PRUEFEN und in „pruefen_gruende“; Seiten mit einem Seitenverdacht der Restrisiko-Prüfung
    werden nicht doppelt gemeldet.
  * Beschädigte Dateien (R-11): Direkt nach dem Öffnen wird jedes Objekt geladen (analyse.reparatur_erzwingen) – eine
    Reparatur geschieht dann vor jeder Änderung. Repariert MuPDF trotzdem erst nach Beginn der Änderungen (dabei
    verwirft es alle Schwärzungen im Speicher), entsteht KEINE Ausgabe. Die Selbstkontrolle wertet Text in einem
    Schwärzungsrechteck nur als Platzhalter, wenn er wirklich in einem Platzhalter steht.
  * Nebenkanäle (Gutachten R-04): Stehen personenbezogene Daten nur in Dokumenteigenschaften, Lesezeichen,
    Anhängen oder XFA-Daten, entsteht auch ohne Fund auf den Seiten eine bereinigte Ausgabe – immer als _PRUEFEN.
"""

from __future__ import annotations

import datetime
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import NamedTuple

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import analyse as _analyse
from . import ocr as _ocr
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
# Gutachten M-25: Die Zuordnungsdatei enthält die Original-Dateinamen (oft mit Kundennamen). Neben dem Ausgabeordner
# statt darin („<Ordner>/_zuordnung_<Ausgabeordner>.txt“, im Standardfall neben den Originalen
# „_zuordnung_anonymisiert.txt“) landet sie nicht mehr in dem Ordner, den die Nutzerin hochlädt. NOCH AUSGESCHALTET:
# Tests der Schwärzung, der Oberfläche, der Vorschau und des Selbsttests schreiben „anonymisiert/_zuordnung.txt“ fest
# (test_schwaerzung, test_gui, test_vorschau_fenster, test_selbsttest) – einschalten heißt, sie mit umzustellen.
ZUORDNUNG_NEBEN_AUSGABEORDNER = False

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
    denn die Seitenschleife hat sie dem Modul überlassen."""
    lauf.beschnitt_lokal = True
    for nr in range(len(doc)):
        seite = doc[nr]
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
            lauf.melden("fehler", "NEBENKANAL_ENTFERNT",
                        f"Seite {nr + 1}: Inhalte außerhalb des sichtbaren Seitenbereichs konnten nicht entfernt "
                        f"werden ({e}).", nr)


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


def zuordnung_pfad(ziel) -> Path:
    """Zuordnungsdatei des Ausgabeordners `ziel`: darin (_zuordnung.txt) oder – mit ZUORDNUNG_NEBEN_AUSGABEORDNER –
    daneben (_zuordnung_<Ausgabeordner>.txt), damit sie nicht mit hochgeladen wird."""
    ziel = Path(ziel)
    if ZUORDNUNG_NEBEN_AUSGABEORDNER and ziel.name and ziel.parent != ziel:
        return ziel.parent / f"_zuordnung_{ziel.name}.txt"
    return ziel / _ZUORDNUNG


def _zuordnung_anhaengen(ziel: Path, ausgabe: Path, original: Path) -> Path:
    """Zeile „anonym_NN.pdf  <-  Original.pdf  (Zeit)“ anhängen; liefert die Datei. Liegt neben dem Ausgabeordner
    abgelegt noch eine alte _zuordnung.txt IM Ausgabeordner, wird sie übernommen (angehängt) und dort gelöscht – sie
    soll nicht mehr mit hochgeladen werden. Ist neben dem Ordner nicht beschreibbar, bleibt es beim alten Ort."""
    zeit = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    zeile = f"{ausgabe.name}  <-  {original.name}  ({zeit})\n"
    datei, alt = zuordnung_pfad(ziel), Path(ziel) / _ZUORDNUNG
    if datei != alt:
        try:
            with open(datei, "a", encoding="utf-8") as f:
                if alt.exists():
                    altbestand = alt.read_text(encoding="utf-8")
                    f.write(altbestand if altbestand.endswith("\n") or not altbestand else altbestand + "\n")
                f.write(zeile)
            _aufraeumen([alt])
            return datei
        except OSError:
            pass                                      # z. B. Ordner darüber schreibgeschützt: alter Ort
    with open(alt, "a", encoding="utf-8") as f:
        f.write(zeile)
    return alt


def _zuordnung_umschreiben(ziel: Path, alt: str, neu: str | None):
    """Zeile der Ausgabe `alt` in der Zuordnungsdatei auf `neu` umbenennen (neu=None: Zeile entfernen) – am neuen
    und am alten Ort, falls es beide gibt."""
    for datei in dict.fromkeys((zuordnung_pfad(ziel), Path(ziel) / _ZUORDNUNG)):
        if not datei.exists():
            continue
        zeilen = datei.read_text(encoding="utf-8").splitlines(keepends=True)
        aus = []
        for z in zeilen:
            if z.startswith(alt + "  <-  "):
                if neu is None:
                    continue
                z = neu + z[len(alt):]
            aus.append(z)
        tmp = datei.parent / f".{datei.name}.{os.getpid()}.tmp"
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
        self.repariert = False               # MuPDF musste die Datei beim Öffnen reparieren (R-11)
        self.repariert_objekt = None         # das Dokument, das schon VOR allen Änderungen repariert war (R-11)
        self.leckrelevant: list = []         # Gründe, die Ausgabe nicht als geprüft gelten zu lassen (R-07)
        self.nebenkanal_bezug = None         # personenbezogene Daten in Nebenkanälen (R-04); None = ungeprüft
        self.manuelle_platzhalter: set = set()   # Platzhalter manueller Stellen (für die Selbstkontrolle)

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
        _spaete_reparatur_pruefen(self, self.doc)      # nie einen zurückgesetzten Stand weiterverarbeiten (R-11)
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


class _SpaeteReparatur(Exception):
    """MuPDF hat die Datei erst NACH Beginn der Änderungen repariert (Gutachten R-11): dabei verwirft es alle Änderungen
    im Speicher – die Schwärzungen wären weg, die Ausgabe enthielte wieder den Klartext."""


TEXT_SPAETE_REPARATUR = ("Die Datei ist beschädigt: Beim Schwärzen musste sie nachträglich repariert werden, dabei "
                         "können Schwärzungen verloren gehen. Sicherheitshalber wurde KEINE Ausgabe erzeugt. Bitte die "
                         "Datei erneut herunterladen – oder sie öffnen und über „Drucken“ → „Microsoft Print to PDF“ "
                         "als neue PDF speichern und diese verwenden.")


def _spaete_reparatur_pruefen(lauf, doc) -> None:
    """Wirft _SpaeteReparatur, wenn MuPDF `doc` repariert hat, obwohl es beim Öffnen (nach reparatur_erzwingen) noch
    nicht repariert war – oder es ein später geöffneter Zwischenstand ist."""
    if doc is not None and _analyse.datei_repariert(doc) and doc is not lauf.repariert_objekt:
        raise _SpaeteReparatur()


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
            lauf.manuelle_platzhalter.add(str(ersatz))
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


def _seite_bearbeiten(lauf: _Lauf, nr: int, m, plan: _Plan, bereiche: list, versteckt: list):
    """Eine Seite schwärzen: Rechtecke aus dem Modell, Platzhalter, Anwenden, Prüfungen."""
    doc = lauf.doc
    seite = doc[nr]
    if seite.rotation:          # nur nach einem Zwischenstand denkbar – Vorbereitung entfernt sie
        seite.remove_rotation()
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
        hits.append({"fund": fund, "ersatz": ersatz, "rects": rects, "groesse": teile[0][2],
                     "grundlinie": teile[0][3], "freiraum": m.freiraum(s, e, rects[0])})
        getroffen_text |= {g for g in m.glyphen(s, e) if m.zeichen[g].quelle == "text"}

    if modus in ("seite", "bilder"):
        lauf.ocr_modus[nr] = modus
        lauf.bildbereiche[nr] = list(m.bilder)
        if modus == "seite":
            _schluesselwoerter_pruefen(lauf, nr, m, kategorien)

    # 2) Redaktionen und Platzhalter planen (nur ENTHALTENE Rechtecke verwerfen)
    bereits: list = []
    platzhalter: list = []      # (Rechteck, Text, Schriftgröße, Grundlinie)
    for hit in hits:
        rects = [r for r in hit["rects"] if not r.is_empty and not any(alt.contains(r) for alt in bereits)]
        if not rects:
            continue
        lauf.treffer += 1
        lauf.stellen_geschwaerzt += 1
        ersatz = hit["ersatz"]
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
    for eintrag in bereiche:              # manuelle Bereiche: Text UND Bildpixel, Platzhalter
        r, ersatz = (eintrag if isinstance(eintrag, tuple) else (eintrag, PLATZHALTER_BEREICH))
        r = fitz.Rect(r) & seite.rect
        if r.is_empty:
            continue
        lauf.treffer += 1
        fs = _platzhalter_schrift(r, ersatz, PLATZHALTER_MAX_PT)
        if fs >= PLATZHALTER_MIN_PT:
            platzhalter.append((r, ersatz, fs, None))
        bereits.append(r)
        seite.add_redact_annot(r, fill=FUELLFARBE)
    if kategorien:
        lauf.kategorien_je_seite[nr] = kategorien

    # 3) Versteckte Ebenen-Inhalte (ohne Platzhalter) und Inhalte außerhalb des Beschnitts
    for r in versteckt:
        bereits.append(r)
        seite.add_redact_annot(r, fill=FUELLFARBE)
    if versteckt:
        lauf.melden("hinweis", "NEBENKANAL_ENTFERNT",
                    f"Seite {nr + 1}: {len(versteckt)} ausgeblendete Inhalt(e) einer Ebene entfernt.", nr)
    if lauf.beschnitt_lokal:
        beschnitt = _beschnitt_rechtecke(seite)
        for r in beschnitt:
            try:
                seite.add_redact_annot(r, fill=False)
                bereits.append(r)
            except Exception:
                pass
        if beschnitt:
            lauf.beschnitt_seiten.append(nr + 1)

    # 4) Anwenden (Text UND Bildpixel), Teilreste prüfen, Platzhalter schreiben, Kollateralschaden prüfen
    if bereits:
        bild_vorher = None
        if _bilder is not None and hasattr(_bilder, "bildzustand") and hasattr(_bilder, "nach_schwaerzung"):
            try:
                bild_vorher = _bilder.bildzustand(seite)
            except Exception:
                bild_vorher = None
        seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                               graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                               text=fitz.PDF_REDACT_TEXT_REMOVE)
        if bild_vorher is not None:
            try:
                lauf.bilder_neu_kodiert += int(_bilder.nach_schwaerzung(doc, seite, bild_vorher) or 0)
            except Exception as e:
                lauf.melden("hinweis", "BILDER_UNGEPRUEFT", f"Geschwärzte Bilder auf Seite {nr + 1} konnten nicht "
                                                            f"neu komprimiert werden ({e}) – die Datei wird größer.", nr)
        if getroffen_text:
            _glyphreste_pruefen(lauf, nr, seite, m, getroffen_text)
        for r, text, fs, grundlinie in platzhalter:
            if not _platzhalter_zeichnen(seite, r, text, fs, grundlinie):
                lauf.ohne_platzhalter += 1
        if woerter_vorher:
            _kollateral_pruefen(lauf, nr, seite, woerter_vorher, bereits)
        if bild_vorher is None:
            try:
                for info in seite.get_image_info(xrefs=True):
                    xref = info.get("xref") or 0
                    if xref > 0 and any(fitz.Rect(info["bbox"]).intersects(r) for r in bereits):
                        lauf.bild_xrefs.add(xref)
            except Exception:
                pass
        if modus == "seite":
            lauf.scan_seiten_seit_speichern += 1
    lauf.rects_je_seite[nr] = bereits

    # 5) Hinweise zu Grafiken/Bildern (Unterschriften, Stempel, Fotos werden nicht geprüft)
    if m.bilder and modus == "bilder":
        lauf.bild_seiten.append(nr + 1)
    if _hat_kurven(seite):
        lauf.grafik_seiten.append(nr + 1)


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


_WERT_NACH_SCHLUESSELWORT = 40     # so weit hinter dem Schlüsselwort wird ein Wert gesucht (Zeichen)
_WERTARTIG_RE = re.compile(r"[\w./\-]*\d[\w./\-]*")
_DATUM_RE = re.compile(r"\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})\b")
# Fließtext: eine Zeile mit mindestens _FLIESSTEXT_MIN_WOERTER Wörtern, in der direkt hinter dem Schlüsselwort (nur
# Leerzeichen oder Komma dazwischen) der Satz mit einem kleingeschriebenen Wort weitergeht („… diesen
# Versicherungsschein zusammen mit …“, „… geboren werden …“) oder direkt davor ein kleingeschriebenes Wort steht
# („Nachtrag zum Versicherungsschein, Merkblatt“) – und kein Etikett-Zeichen folgt („:“, „-Nr.“). Kurze Zeilen
# („Geburtsdatum des Kindes“, „neue IBAN“) gelten als Formular-Etikett: deren Wert kann in einer eigenen Zelle stehen.
_FLIESSTEXT_MIN_WOERTER = 5
_FLIESSTEXT_DANACH_RE = re.compile(r"[ \t,;]*[a-zäöüß]")
_FLIESSTEXT_DAVOR_RE = re.compile(r"(?:^|[\s(])[a-zäöüß][^\W\d_]*[ \t]+$")
_ETIKETT_DANACH_RE = re.compile(r"[ \t]*(?::|[\-\s]?(?:nr|nummer)\b)", re.IGNORECASE)
_ZEILENWORT_RE = re.compile(r"[^\W\d_]{2,}")
_ZEILENANFANG_RE = re.compile(r"[\s:;,.|*()\[\]-]*")


def _schluesselwoerter_pruefen(lauf, nr, m, kategorien_mit_treffer: set):
    """M-50: Schlüsselwort auf einer OCR-Seite gelesen, aber kein Fund dieser Kategorie – warnen (die Ausgabe wird
    _PRUEFEN, R-07). Keine Warnung, wenn der Wert hinter dem Schlüsselwort geschwärzt ist (der erste Ausdruck mit
    Ziffern in derselben Zeile; endet die Zeile mit dem Schlüsselwort bzw. seinem Etikett „…:“, der Ausdruck GANZ
    vorn in der nächsten Zeile – auch ein Wert einer anderen Kategorie: „IBAN [VERTRAGS-NR]“, die OCR hat eine Ziffer
    der IBAN verlesen, der Wert ist trotzdem weg) oder wenn das Schlüsselwort ohne Wert im Fließtext steht („im
    Versicherungsschein bezeichneten Sachen“, „Kinder, die … geboren / oder adoptiert werden“; ein Datum nennt dort
    keine Nummer: „Versicherungsschein vom 01.05.2024“). Sonst bleibt die Warnung: ein ungeschwärzter Wert („IBAN
    DE89 3704 [TELEFON]“, „geboren am 12.03.1975“) – und auch ein Etikett, hinter dem sich kein Wert finden lässt
    (Formular: „Steuer-ID:“, darunter steht schon das nächste Etikett, der Wert in einer eigenen Spalte wurde nicht
    erkannt)."""
    ocr_ids = {zid for b in m.bloecke if b.quelle != "text" for zid in b.zeilen}
    zeilen = [z for z in m.zeilen if z.id in ocr_ids and m.text[z.start:z.ende].strip()]
    if not zeilen:
        return
    kategorien = {f.get("kategorie", "") for f in lauf.funde}
    spannen = []
    for f in lauf.funde:
        for st in f.get("stellen") or []:
            if st.get("an", True) and st.get("seite") == nr:
                try:
                    spannen.append((int(st.get("start", -1)), int(st.get("ende", -1))))
                except (TypeError, ValueError):
                    continue

    def geschwaerzt(pos: int) -> bool:
        return any(s <= pos < e for s, e in spannen)

    def ist_wert(pos: int, ende: int, kategorie: str) -> bool:
        """Beginnt bei pos ein Wert (mindestens zwei Ziffern; ein Datum nur beim Geburtsdatum)?"""
        if sum(c.isdigit() for c in m.text[pos:min(ende, pos + 30)]) < 2:
            return False
        return kategorie == "geburt" or not _DATUM_RE.match(m.text, pos)

    def wert_in_zeile(s: int, e: int, kategorie: str):
        """Position des ersten Werts in text[s:e] (höchstens _WERT_NACH_SCHLUESSELWORT Zeichen weit) oder None."""
        for wt in _WERTARTIG_RE.finditer(m.text, s, min(e, s + _WERT_NACH_SCHLUESSELWORT)):
            if ist_wert(wt.start(), e, kategorie):
                return wt.start()
        return None

    def fliesstext(t, i: int, danach: str) -> bool:
        zeile = zeilen[i]
        if len(_ZEILENWORT_RE.findall(m.text, zeile.start, zeile.ende)) < _FLIESSTEXT_MIN_WOERTER:
            return False
        if _ETIKETT_DANACH_RE.match(m.text, t.end(), zeile.ende):
            return False
        return bool(_FLIESSTEXT_DANACH_RE.match(danach) or _FLIESSTEXT_DAVOR_RE.search(m.text[zeile.start:t.start()]))

    def warnen(t, i: int, kategorie: str) -> bool:
        """Warnung für das Schlüsselwort `t` in Zeile i? Ein Wert dahinter entscheidet (geschwärzt: nein, sonst ja);
        ohne Wert: nein nur im Fließtext, sonst ja (Etikett ohne erkennbaren Wert)."""
        zeile = zeilen[i]
        rest = m.text[t.end():zeile.ende]
        pos = wert_in_zeile(t.end(), zeile.ende, kategorie)
        if pos is not None:
            return not geschwaerzt(pos)
        naechste = zeilen[i + 1] if i + 1 < len(zeilen) else None
        anfang = m.text[naechste.start:naechste.ende] if naechste is not None else ""
        leer = not any(c.isalnum() for c in rest)
        if leer or rest.rstrip().endswith(":"):
            # Die Zeile endet mit dem Schlüsselwort bzw. seinem Etikett: ein Wert steht – wenn überhaupt – ganz vorn in
            # der nächsten Zeile. Ein Satz, der dort klein weitergeht, ist Fließtext; ein Etikett („…:“) nie.
            if naechste is not None:
                vorn = naechste.start + _ZEILENANFANG_RE.match(anfang).end()
                if _WERTARTIG_RE.match(m.text, vorn) and ist_wert(vorn, naechste.ende, kategorie):
                    return not geschwaerzt(vorn)
            if rest.rstrip().endswith(":"):
                return True
            return not fliesstext(t, i, anfang)
        return not fliesstext(t, i, rest)
    for kategorie, anzeige, muster in _SCHLUESSELWOERTER:
        if kategorie in kategorien_mit_treffer:
            continue
        treffer = None
        for i, z in enumerate(zeilen):
            for t in muster.finditer(m.text, z.start, z.ende):
                if warnen(t, i, kategorie):
                    treffer = t
                    break
            if treffer is not None:
                break
        if treffer is None:
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


_PLATZHALTER_FORM = re.compile(r"\[[A-ZÄÖÜ0-9][A-ZÄÖÜ0-9 .\-–/]*\]")


def _platzhalter_texte(lauf: _Lauf) -> set:
    """Alle Platzhalter, die in die Ausgabe gezeichnet werden (normalisiert)."""
    texte = {f.get("ersatz") for f in lauf.funde if f.get("ersatz")} | set(lauf.abgekuerzt) | {PLATZHALTER_BEREICH}
    texte |= lauf.manuelle_platzhalter
    return {" ".join(str(t).split()) for t in texte if t}


def _im_platzhalter(text: str, s: int, e: int, platzhalter: set) -> bool:
    """Liegt text[s:e] ganz in einem gezeichneten Platzhalter („Person“ in „[PERSON A]“)? Nur dann ist ein Treffer
    innerhalb eines Schwärzungsrechtecks harmlos – sonst steht dort noch Originaltext (Gutachten R-11: eine späte
    Reparatur stellte den Klartext an genau diesen Stellen wieder her)."""
    links = text.rfind("[", max(0, s - 60), s + 1)
    if links < 0 or "]" in text[links:s]:
        return False
    rechts = text.find("]", max(links, e - 1), e + 60)
    if rechts < 0 or "[" in text[max(e, links + 1):rechts]:
        return False
    token = " ".join(text[links:rechts + 1].split())
    return token in platzhalter or bool(_PLATZHALTER_FORM.fullmatch(token))


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
    if modus == "seite":
        # dieselbe Ausrichtung wie beim Original (Gutachten S-08): die Ausgabe enthält zu wenige Wörter,
        # um sie neu zu bestimmen. Vollständiges Ergebnis (10-Tupel mit Ausrichtung und Schräglagen-Korrektur),
        # damit das Kontrollmodell die Zeilen genauso bildet wie das der Analyse
        ergebnis_fn = getattr(lauf.ocr, "ergebnis", None)
        if ergebnis_fn is not None:
            w = ergebnis_fn(ausgabe, nr, OCR_DPI, winkel=lauf.winkel(nr)).get("woerter")
        else:
            try:
                w, _ = lauf.ocr.woerter(ausgabe, nr, OCR_DPI, winkel=lauf.winkel(nr))
            except TypeError:
                w, _ = lauf.ocr.woerter(ausgabe, nr, OCR_DPI)
        woerter += list(w or [])
    else:
        for bereich in lauf.bildbereiche.get(nr, []):
            try:
                w, _ = lauf.ocr.woerter(ausgabe, nr, OCR_DPI, clip=bereich)
            except TypeError:
                w, _ = lauf.ocr.woerter(ausgabe, nr)
            woerter += list(w or [])
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
    platzhalter = _platzhalter_texte(lauf)
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
                        if (teile and all(_innerhalb(t[1], rects) for t in teile)
                                and _im_platzhalter(m.text, s, e, platzhalter)):
                            continue                       # Platzhaltertext (nie Originaltext im Rechteck)
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
# Status: Gründe für _PRUEFEN (Gutachten R-07, R-11), Nebenkanäle (R-04), reparierte Dateien (R-11)
# ----------------------------------------------------------------------
KAUM_LESBAR_WOERTER = _analyse.KAUM_LESBAR_WOERTER   # weniger OCR-Wörter: Seite KANN kaum lesbar sein (siehe
#                                                     analyse.scan_kaum_lesbar – dieselbe Regel wie die Analyse)
TINTE_MIN = 0.0003              # Anteil dunkler Pixel (wie die Restrisiko-Prüfung): darunter ist eine Seite leer
# Meldungen, deren Ursache bis in die Ausgabe wirkt: die Ausgabe kann dann nicht als geprüft gelten (_PRUEFEN)
LECKRELEVANTE_CODES = frozenset({"OCR_UNPLAUSIBEL", "KAUM_LESBAR", "OCR_FEHLER", "XFA", "DATEI_REPARIERT",
                                 "BILDER_UNGEPRUEFT", "SCHLUESSELWORT_OHNE_FUND", "BILD_BESCHAEDIGT"})
_GRUND_TEXTE = {"KAUM_LESBAR": "Scan kaum lesbar", "OCR_UNPLAUSIBEL": "Texterkennung unsicher (Buchstabensalat)",
                "OCR_FEHLER": "kein Text erkannt bzw. Texterkennung fehlgeschlagen",
                "BILDER_UNGEPRUEFT": "Bilder nicht geprüft", "XFA": "XFA-Formular (Inhalt nicht prüfbar)",
                "DATEI_REPARIERT": "Datei war beschädigt (repariert) – Inhalte können fehlen",
                "SCHLUESSELWORT_OHNE_FUND": "Schlüsselwort ohne geschwärzten Wert (OCR-Verleser?)",
                "NUR_NEBENKANAL": "Personendaten nur außerhalb der Seiten gefunden – Seiten bitte selbst ansehen",
                "BILD_BESCHAEDIGT": "Bild beschädigt – Teile nicht lesbar"}


class _Grund(NamedTuple):
    code: str
    seite: int | None              # 0-basiert; None = ganzes Dokument
    text: str                      # kurz, für die Warnung AUSGABE_PRUEFEN und „pruefen_gruende“


def _grund(code: str, seite=None, zusatz: str = "") -> _Grund:
    text = _GRUND_TEXTE.get(code, code) + zusatz
    return _Grund(code, seite, f"Seite {seite + 1}: {text}" if seite is not None else text)


_tintenanteil = _analyse.tintenanteil     # Anteil dunkler Pixel (eine Regel für Analyse und Schwärzung)
_kaum_lesbar = _analyse.scan_kaum_lesbar


def _lesung_unplausibel(woerter) -> bool:
    """Buchstabensalat nach dem Maß der OCR (dasselbe Maß wie die OCR selbst und die Restrisiko-Prüfung)."""
    try:
        bewertung = _ocr._lesung_bewerten([str(w[4]) for w in woerter])
        return bewertung["tokens"] >= _ocr.MIN_TOKENS_WARNUNG and not _ocr._plausibel(bewertung)
    except Exception:
        return False


def _leckrelevant_ermitteln(lauf: _Lauf, dok, zaehler: dict) -> list:
    """Gründe, die Ausgabe nicht als geprüft gelten zu lassen (R-07/R-11) – vor dem Schwärzen ermittelt, damit die
    Tinte leerer Scan-Seiten am Original gemessen wird. Quellen: das Dokument (XFA, Reparatur), das frische Modell
    mit der OCR der Analyse (kaum lesbar, unplausibel, ohne Text aber mit Tinte), die Meldungen der OCR beim
    Aufbau des Modells (OCR-Fehler, Bilder nicht prüfbar) und – falls übergeben – die Meldungen der Analyse."""
    gruende: dict = {}

    def dazu(code, seite=None):
        gruende.setdefault((code, seite), _grund(code, seite))
    if zaehler.get("xfa"):
        dazu("XFA")
    if lauf.repariert:
        dazu("DATEI_REPARIERT")
    leer: set = set()
    for nr, m in enumerate(dok.seiten):
        if m.ocr_modus != "seite":
            continue
        anzahl = int(m.ocr_woerter or 0)
        if 0 < anzahl < KAUM_LESBAR_WOERTER:
            if _kaum_lesbar(lauf.doc[nr], lauf.ocr_cache.get(nr) or ()):
                dazu("KAUM_LESBAR", nr)
        elif anzahl and _lesung_unplausibel(lauf.ocr_cache.get(nr) or ()):
            dazu("OCR_UNPLAUSIBEL", nr)
        elif anzahl == 0:
            if _tintenanteil(lauf.doc[nr]) > TINTE_MIN:
                dazu("OCR_FEHLER", nr)
            else:
                leer.add(nr)                               # leere Scan-Seite (Rückseite): kein Grund
    if lauf.analyse_modell is None:
        # Beschädigte Bilder (R-07, scan_bild_defekt) – mit dem Modell der Analyse stehen sie in dessen Meldungen
        for nr in _analyse.bild_schaeden(lauf.pdf_pfad):
            dazu("BILD_BESCHAEDIGT", nr)
    meldungen = list(lauf.meldungen) + list(getattr(lauf.analyse_modell, "leckrelevant", None) or [])
    for m in meldungen:
        code, seite = m.get("code"), m.get("seite")
        if code not in LECKRELEVANTE_CODES or m.get("art") not in ("warnung", "fehler"):
            continue
        if code in ("SCHLUESSELWORT_OHNE_FUND", "KAUM_LESBAR") or (code == "OCR_FEHLER" and seite in leer):
            continue                    # Schlüsselwörter prüft die Seitenschleife, kaum lesbar die Schleife oben
            #                             (mit Lesung und Tinte, nicht nur nach Wortzahl); leere Seite: kein Grund
        dazu(code, seite if isinstance(seite, int) else None)
    return list(gruende.values())


def _seitenbaum_reparieren(doc):
    """Reparierte Datei (abgeschnitten): Einträge im Seitenbaum, die auf fehlende Objekte zeigen, durch leere
    Seiten ersetzen und das Dokument neu öffnen. Sonst zeigen sie nach dem Speichern auf neu angelegte Objekte
    (Schwärzungen, Inhaltsströme) – andere Programme lesen dann eine andere Seitenzahl oder lehnen die Datei ab.
    Liefert das (ggf. neu geöffnete) Dokument."""
    try:
        art, wert = doc.xref_get_key(doc.pdf_catalog(), "Pages")
        if art != "xref":
            return doc
        ersetzt, stapel, gesehen = 0, [int(wert.split()[0])], set()
        while stapel:
            knoten = stapel.pop()
            if knoten in gesehen:
                continue
            gesehen.add(knoten)
            art, kinder = doc.xref_get_key(knoten, "Kids")
            if art != "array":
                continue
            neu, geaendert = [], False
            for nummer in re.findall(r"(\d+)\s+\d+\s+R", kinder):
                x = int(nummer)
                typ = doc.xref_get_key(x, "Type")[1] if 0 < x < doc.xref_length() else None
                if typ == "/Pages":
                    stapel.append(x)
                elif typ != "/Page":
                    x = doc.get_new_xref()
                    doc.update_object(x, f"<</Type/Page/Parent {knoten} 0 R/MediaBox[0 0 612 792]/Resources<<>>>>")
                    ersetzt += 1
                    geaendert = True
                neu.append(f"{x} 0 R")
            if geaendert:
                doc.xref_set_key(knoten, "Kids", "[" + " ".join(neu) + "]")
        if not ersetzt:
            return doc
        neu_doc = fitz.open("pdf", doc.tobytes(garbage=0))
    except Exception:
        return doc
    doc.close()
    return neu_doc


def _nebenkanal_bezug(pfad, nebenkanaele=None, modell=None, profil: str = "hoch") -> bool:
    """Stehen personenbezogene Daten in Nebenkanälen (R-04)? Aus dem Analyse-Ergebnis („nebenkanaele“), sonst selbst
    geprüft – mit den Standard-Kategorien und der NIE-Liste aus dem Modell der Analyse, am ungeöffneten Original
    (vor dem Einbrennen der Anmerkungen). Im Zweifel True: lieber eine bereinigte Ausgabe als das Original."""
    if isinstance(nebenkanaele, dict) and "personenbezug" in nebenkanaele:
        return bool(nebenkanaele["personenbezug"])
    try:
        doc = fitz.open(pfad)
    except Exception:
        return False                                   # nicht lesbar: es entsteht ohnehin keine Ausgabe
    try:
        if _analyse.keine_pdf_meldung(doc, pfad) or doc.needs_pass:
            return False
        aktive = {k[0] for k in _analyse.KATEGORIEN if k[4]}
        ergebnis = _analyse.nebenkanaele_pruefen(doc, aktive, getattr(modell, "nie", None) or [], [], profil=profil)
        return bool(ergebnis.get("personenbezug"))
    except Exception:
        return True
    finally:
        doc.close()


def _verdacht_feld(v, name, standard=None):
    return v.get(name, standard) if isinstance(v, dict) else getattr(v, name, standard)


# ----------------------------------------------------------------------
# Hauptfunktion
# ----------------------------------------------------------------------
def schwaerze_pdf(pdf_pfad, funde: list, melde=None, fortschritt=None, abbruch=None, ocr=None,
                  ocr_cache=None, ziel_ordner=None, modell=None, manuelle_bereiche=None,
                  manuelle_stellen=None, freigabe_erforderlich: bool = False, profil: str = "hoch",
                  nebenkanaele: dict | None = None) -> dict:
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
    ziel_ordner: sonst <Ordner der PDF>/anonymisiert; nebenkanaele: „nebenkanaele“ aus dem Analyse-Ergebnis
    (sonst prüft die Schwärzung selbst, wenn auf den Seiten nichts zu schwärzen ist).
    Ohne angehakten Fund entsteht nur dann eine Ausgabe, wenn Nebenkanäle personenbezogene Daten tragen (R-04) –
    sie ist das Dokument ohne Dateieigenschaften, Lesezeichen, Anhänge und Formulardaten.
    „pruefen_gruende“: kurze Gründe, warum die Ausgabe _PRUEFEN ist (für die Oberfläche)."""
    pdf_pfad = Path(pdf_pfad)
    ergebnis = {"original": pdf_pfad, "ausgabe": None, "treffer": 0, "uebersprungen": 0,
                "warnungen": [], "hinweise": [], "reste": [], "fehler": None, "verdacht": [], "status": None,
                "stellen_geschwaerzt": 0, "stellen_nicht_lokalisiert": 0, "meldungen": [],
                "ausgabe_pruefen": False, "pruefen_gruende": []}
    funde = [dict(f) for f in (funde or []) if str(f.get("text", "")).strip() or f.get("stellen")]
    for f in funde:
        f["text"] = str(f.get("text", "")).strip()
    bereiche = {int(k): [fitz.Rect(r) for r in v] for k, v in (manuelle_bereiche or {}).items() if v}
    stellen_manuell = {int(k): list(v) for k, v in (manuelle_stellen or {}).items() if v}
    nebenkanal_bezug = None
    if not funde and not bereiche and not stellen_manuell:
        nebenkanal_bezug = _nebenkanal_bezug(pdf_pfad, nebenkanaele, modell, profil)
        if not nebenkanal_bezug:
            ergebnis["warnungen"].append(WARNUNG_KEIN_TREFFER)
            ergebnis["meldungen"].append({"art": "warnung", "code": "KEIN_TREFFER", "text": WARNUNG_KEIN_TREFFER,
                                          "seite": None})
            return ergebnis
    elif isinstance(nebenkanaele, dict) and "personenbezug" in nebenkanaele:
        nebenkanal_bezug = bool(nebenkanaele["personenbezug"])

    ziel = Path(ziel_ordner) if ziel_ordner else pdf_pfad.parent / "anonymisiert"
    eigener_dienst = None
    if ocr is None:
        ocr = eigener_dienst = OcrDienst()
    lauf = _Lauf(pdf_pfad, funde, melde, fortschritt, abbruch, ocr, ocr_cache, ziel)
    lauf.analyse_modell = modell
    lauf.nebenkanal_bezug = nebenkanal_bezug
    try:
        try:
            lauf.doc = fitz.open(pdf_pfad)
        except Exception as e:
            ergebnis["fehler"] = f"Konnte nicht geöffnet werden: {e}"
            return ergebnis
        keine_pdf = _analyse.keine_pdf_meldung(lauf.doc, pdf_pfad)      # vor jedem Seitenzugriff (R-01)
        if keine_pdf:
            ergebnis["fehler"] = keine_pdf
            lauf.meldungen.append({"art": "fehler", "code": "KEIN_PDF", "text": keine_pdf, "seite": None})
            return ergebnis
        if lauf.doc.needs_pass:
            ergebnis["fehler"] = "Passwortgeschützt – übersprungen."
            return ergebnis
        # vor jeder Änderung jedes Objekt einmal laden: eine nötige Reparatur geschieht jetzt, nicht erst nach dem
        # Schwärzen – dann verwürfe MuPDF alle Schwärzungen im Speicher (R-11, späte Reparatur)
        lauf.repariert = _analyse.reparatur_erzwingen(lauf.doc)
        if lauf.repariert:
            lauf.doc = _seitenbaum_reparieren(lauf.doc)
        lauf.repariert_objekt = lauf.doc if _analyse.datei_repariert(lauf.doc) else None
        _schwaerzen(lauf, ergebnis, bereiche, stellen_manuell, freigabe_erforderlich, profil)
    except _Abgebrochen:
        ergebnis["fehler"] = ABGEBROCHEN
        ergebnis["ausgabe"] = None
        ergebnis["status"] = None
        lauf.meldungen.append({"art": "fehler", "code": "ABGEBROCHEN", "text": ABGEBROCHEN, "seite": None})
    except _SpaeteReparatur:
        ergebnis["fehler"] = TEXT_SPAETE_REPARATUR
        ergebnis["ausgabe"] = None
        ergebnis["status"] = None
        lauf.melden("fehler", "DATEI_REPARIERT", TEXT_SPAETE_REPARATUR)
        ergebnis["warnungen"] = lauf.warnungen
        ergebnis["hinweise"] = lauf.hinweise
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
    if lauf.repariert:
        lauf.melden("warnung", "DATEI_REPARIERT", _analyse.reparatur_meldungstext(_analyse.leere_seiten(doc)))

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
    # Gründe für _PRUEFEN aus Lesbarkeit und Zustand der Datei (R-07/R-11) – vor dem Schwärzen (Tinte am Original)
    lauf.leckrelevant = _leckrelevant_ermitteln(lauf, dok, zaehler)

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
        # Auf den Seiten nichts zu schwärzen: eine Ausgabe nur, wenn Nebenkanäle personenbezogene Daten tragen –
        # sonst ginge das Original samt Titel, Anhängen oder XFA-Daten weiter (R-04)
        unklar = bool(nicht_lokalisiert or nicht_gefunden)
        if lauf.nebenkanal_bezug is None and not unklar:
            lauf.nebenkanal_bezug = _nebenkanal_bezug(lauf.pdf_pfad, None, lauf.analyse_modell, profil)
        if unklar or not lauf.nebenkanal_bezug:
            lauf.melden("warnung", "KEIN_TREFFER", WARNUNG_KEIN_TREFFER)
            ergebnis["warnungen"] = lauf.warnungen
            ergebnis["hinweise"] = lauf.hinweise
            return
        lauf.melden("hinweis", "NEBENKANAL_ENTFERNT",
                    "Auf den Seiten wurde nichts erkannt. Die Ausgabe ist das Dokument ohne Dateieigenschaften, "
                    "Lesezeichen, Anhänge und Formulardaten – dort standen personenbezogene Daten (oder sie waren nicht "
                    "auszuschließen).")
        # Starkes Warnsignal: das Dokument nennt außerhalb der Seiten eine Person, auf den Seiten steht keine einzige
        # Fundstelle – vielleicht kann die Erkennung die Seiten nicht lesen. Nie still „fertig“ (Gutachten R-04).
        grund = _grund("NUR_NEBENKANAL")
        if grund not in lauf.leckrelevant:
            lauf.leckrelevant.append(grund)
    if ocr_seiten and lauf.treffer:
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
    _spaete_reparatur_pruefen(lauf, doc)          # R-11: nie einen von MuPDF zurückgesetzten Stand speichern
    tmp = lauf.tmp_pfad("ausgabe")
    try:
        doc.save(tmp, garbage=4, deflate=True)
    except Exception as e:
        ergebnis["fehler"] = (f"Ausgabe konnte nicht geschrieben werden ({e}) – ist der Ordner "
                              f"»{lauf.ziel}« beschreibbar oder die Datei noch geöffnet?")
        ergebnis["warnungen"] = lauf.warnungen
        ergebnis["hinweise"] = lauf.hinweise
        return
    _spaete_reparatur_pruefen(lauf, doc)          # auch eine Reparatur während des Speicherns zählt
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
    # Status (R-07/R-11): Gründe aus Lesbarkeit und Zustand der Datei machen die Ausgabe _PRUEFEN. Eine Seite, die
    # die Restrisiko-Prüfung schon als ganze Seite verdächtigt (ungelesen, kaum lesbar, unplausibel), wird nicht
    # noch einmal gemeldet.
    for m in lauf.meldungen:
        if m.get("code") == "SCHLUESSELWORT_OHNE_FUND" and isinstance(m.get("seite"), int):
            grund = _grund("SCHLUESSELWORT_OHNE_FUND", m["seite"])
            if grund not in lauf.leckrelevant:
                lauf.leckrelevant.append(grund)
    seitenverdacht = {_verdacht_feld(v, "seite") for v in verdacht if _verdacht_feld(v, "start", 0) == -1}
    gruende = [g for g in lauf.leckrelevant if g.seite is None or g.seite not in seitenverdacht]
    unsicher = bool(nicht_lokalisiert or lauf.modell_abweichung or lauf.restrisiko_fehler or lauf.leckrelevant)
    pruefen = bool(reste or verdacht or freigabe_erforderlich or unsicher)
    if freigabe_erforderlich and not (reste or verdacht or unsicher):
        lauf.melden("hinweis", "AUSGABE_PRUEFEN", "Freigabe vor Weitergabe ist eingeschaltet – die Ausgabe bleibt "
                                                  "_PRUEFEN, bis sie in der Vorschau freigegeben wird.")
    elif gruende:
        lauf.melden("warnung", "AUSGABE_PRUEFEN",
                    f"Ausgabe als _PRUEFEN abgelegt – {'; '.join(g.text for g in gruende)}. Bitte die Ausgabe vor der "
                    f"Weitergabe ansehen.")
    elif pruefen and not (reste or verdacht):
        lauf.melden("warnung", "AUSGABE_PRUEFEN", "Ausgabe als _PRUEFEN abgelegt – bitte die Warnungen oben prüfen.")
    pruefen_gruende = []
    if reste:
        pruefen_gruende.append(f"{len(reste)} Fundtext(e) noch auffindbar")
    if verdacht:
        pruefen_gruende.append(f"{len(verdacht)} Verdachtsstelle(n)")
    if nicht_lokalisiert:
        pruefen_gruende.append("Fundstellen nicht lokalisiert")
    if lauf.modell_abweichung:
        pruefen_gruende.append("Dokument liest sich anders als bei der Analyse")
    if lauf.restrisiko_fehler:
        pruefen_gruende.append("Restrisiko-Prüfung ausgefallen")
    pruefen_gruende += [g.text for g in lauf.leckrelevant]
    if pruefen and not pruefen_gruende:
        pruefen_gruende.append("Freigabe ausstehend")
    ergebnis["pruefen_gruende"] = pruefen_gruende if pruefen else []
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
        datei = _zuordnung_anhaengen(lauf.ziel, ausgabe, lauf.pdf_pfad)
        if datei != zuordnung_pfad(lauf.ziel):
            # M-25: neben dem Ausgabeordner ließ sich nicht schreiben – die Datei liegt doch im Ordner, der hochgeladen
            # wird. Das ist dann keine Nebensache mehr (Warnung statt Hinweis).
            lauf.melden("warnung", "ZUORDNUNG",
                        f"Zuordnung Original ↔ Ausgabe steht in {datei} – im Ordner der Ausgaben, weil daneben nicht "
                        f"geschrieben werden konnte. Diese Datei enthält die Original-Dateinamen (oft mit Kundennamen): "
                        f"beim Hochladen NICHT mit auswählen, nur die anonym_….pdf-Dateien weitergeben.")
        else:
            lauf.melden("hinweis", "ZUORDNUNG", f"Zuordnung Original ↔ Ausgabe steht in {datei}. Diese Datei enthält "
                                                f"die Original-Dateinamen (oft mit Kundennamen) – nicht mit hochladen, "
                                                f"nur die anonym_….pdf-Dateien weitergeben.")
    except OSError as e:
        lauf.melden("warnung", "ZUORDNUNG", f"Zuordnungsdatei konnte nicht geschrieben werden: {e}")
    ergebnis["warnungen"] = lauf.warnungen
    ergebnis["hinweise"] = lauf.hinweise
