"""OCR (Texterkennung für eingescannte PDFs) auf Basis des in PyMuPDF eingebauten Tesseract.

Öffentliche Schnittstelle (siehe CONTRACT.md):
    _tessdata_finden()            Sprachdaten-Ordner suchen (Projekt-tessdata zuerst)
    ocr_noetig(seite)             "nein" | "seite" | "bilder"
    bild_bereiche(seite)          Bildbereiche einer Seite (für "bilder"-OCR)
    class OcrDienst               OCR in einem Prozess-Pool (Start-Methode "spawn"), Fallback im Prozess
Kompatibilität für ältere Aufrufer: ist_scan_seite(seite), ocr_textpage(seite).

Koordinaten: Alle Wörter (x0, y0, x1, y1, text) beziehen sich auf die Seite NACH page.remove_rotation().
"""

import concurrent.futures
import multiprocessing
import os
import re
import sys
import threading
import time
import warnings
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

Wort = tuple  # (x0, y0, x1, y1, text)

PROJEKTWURZEL = Path(__file__).resolve().parent.parent

# Heuristik-Schwellen für ocr_noetig()
MIN_BILD_ANTEIL = 0.01        # Bilder unter 1 % der Seitenfläche (Icons, Linien) werden ignoriert
SCAN_BILD_ANTEIL = 0.20       # ab 20 % Bildfläche (in Summe) gilt eine textarme Seite als Scan
WENIG_TEXT_ZEICHEN = 200      # weniger sichtbare Zeichen = textarm (Stempel, Faxkopf, Seitenzahl)

# Plausibilität der OCR-Wörter (kopfstehende/seitliche Scans liefern Buchstabensalat)
PLAUSIBEL_GUT = 0.75          # ab diesem Anteil wird keine andere Ausrichtung mehr probiert (sonst
                              # werden alle vier Drehungen verglichen – seitlicher Text liefert bei
                              # Tesseract oft wortähnlichen Salat mit 50-60 %)
PLAUSIBEL_WARNUNG = 0.40      # darunter: Warnung "Seite nicht lesbar"
OCR_ZEITLIMIT_S = 900         # Sekunden je Seite, danach gilt der Aufruf als gescheitert

_VOKALE = set("aeiouyäöüáéíóúàèìòùâêîôûœæ")
_RANDZEICHEN = ".,;:!?()[]{}\"'„“‚‘«»/\\|<>*-–—_"
# Buchstaben europäischer Schriften; alles andere (ɐ ǝ ʇ … aus verdrehten Scans) ist unplausibel
_EUROPAEISCH = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ]+")


class OcrAbgebrochen(Exception):
    """Die OCR wurde über OcrDienst.abbrechen() gestoppt."""


# ----------------------------------------------------------------------
# Sprachdaten
# ----------------------------------------------------------------------
def _hat_sprachdaten(ordner) -> bool:
    try:
        return any(Path(ordner).glob("*.traineddata"))
    except OSError:
        return False


def _tessdata_finden():
    """Sucht den Tesseract-Sprachdaten-Ordner.

    Reihenfolge: $TESSDATA_PREFIX (nur, wenn dort *.traineddata liegt), <Projektwurzel>/tessdata
    (mitgelieferte deu.traineddata), sys._MEIPASS/tessdata (PyInstaller), dann die üblichen
    Installationspfade. Rückgabe: Pfad als str oder None.
    """
    kandidaten = []
    umgebung = os.environ.get("TESSDATA_PREFIX")
    if umgebung:
        kandidaten.append(umgebung)
    kandidaten.append(PROJEKTWURZEL / "tessdata")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        kandidaten.append(Path(meipass) / "tessdata")
    if sys.platform == "win32":
        kandidaten += [
            r"C:\Program Files\Tesseract-OCR\tessdata",
            r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
            str(Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tessdata"),
        ]
    else:
        kandidaten += ["/usr/share/tesseract-ocr/5/tessdata",
                       "/usr/share/tesseract-ocr/4.00/tessdata",
                       "/usr/share/tessdata", "/usr/local/share/tessdata"]
    for k in kandidaten:
        if k and _hat_sprachdaten(k):
            pfad = str(Path(k))
            os.environ["TESSDATA_PREFIX"] = pfad
            return pfad
    return None


def _ocr_sprache(tessdata):
    """Liefert (Sprachkürzel oder None, Warnung oder None) für den Sprachdaten-Ordner."""
    if tessdata is None:
        return None, ("Tesseract-Sprachdaten nicht gefunden – Scans können nicht gelesen werden. "
                      "Der Ordner »tessdata« mit deu.traineddata muss neben dem Programm liegen "
                      "(Installieren.bat erneut ausführen).")
    if (Path(tessdata) / "deu.traineddata").exists():
        return "deu", None
    if (Path(tessdata) / "eng.traineddata").exists():
        return "eng", ("Deutsche OCR-Sprachdatei fehlt – nutze Englisch "
                       "(Umlaute werden evtl. falsch erkannt).")
    return None, "Keine OCR-Sprachdatei gefunden – Installieren.bat erneut ausführen."


# ----------------------------------------------------------------------
# Seiten-Heuristik
# ----------------------------------------------------------------------
def _vereinige(rechtecke):
    """Fasst sich überlappende oder berührende Rechtecke zusammen (Kacheln -> ein Bereich)."""
    rechtecke = [fitz.Rect(r) for r in rechtecke if not fitz.Rect(r).is_empty]
    geaendert = True
    while geaendert:
        geaendert = False
        for i in range(len(rechtecke)):
            for j in range(i + 1, len(rechtecke)):
                a, b = rechtecke[i], rechtecke[j]
                naehe = fitz.Rect(a.x0 - 2, a.y0 - 2, a.x1 + 2, a.y1 + 2)
                if naehe.intersects(b):
                    rechtecke[i] = a | b
                    del rechtecke[j]
                    geaendert = True
                    break
            if geaendert:
                break
    return rechtecke


def bild_bereiche(seite) -> list:
    """Sichtbare Bildbereiche der Seite (auf die Seite beschnitten, Winzlinge entfernt, zusammengefasst)."""
    try:
        infos = seite.get_image_info()
    except Exception:
        infos = []
    grenze = MIN_BILD_ANTEIL * abs(seite.rect)
    rechtecke = []
    for info in infos:
        r = fitz.Rect(info["bbox"]) & seite.rect
        if r.is_empty or abs(r) < grenze:
            continue
        rechtecke.append(r)
    return _vereinige(rechtecke)


def _sichtbare_zeichen(seite) -> int:
    """Anzahl sichtbarer Textzeichen. Unsichtbarer Text (Rendermodus 3, z. B. die OCR-Textebene
    eines Kopierers) zählt nicht – sonst gälte ein durchsuchbarer Scan als Textseite."""
    try:
        anzahl = 0
        for span in seite.get_texttrace():
            if span.get("type", 0) == 3:
                continue
            anzahl += sum(1 for z in span["chars"] if not chr(z[0]).isspace())
        return anzahl
    except Exception:
        return len(re.sub(r"\s", "", seite.get_text()))


def _hat_zeichnungen(seite) -> bool:
    try:
        return bool(seite.get_drawings())
    except Exception:
        return False


def ocr_noetig(seite) -> str:
    """Entscheidet je Seite, ob und wie OCR nötig ist.

    "seite":  Scan – OCR der ganzen Seite (kein sichtbarer Text, oder textarm mit viel Bildfläche;
              Textstempel, Faxkopf und Kacheln ändern daran nichts, weil die Bildfläche in Summe zählt).
    "bilder": Textseite mit relevanten Bildern (Briefkopf, Unterschrift, Ausweiskopie, Foto) –
              OCR nur der Bildbereiche.
    "nein":   reiner Text.
    """
    bilder = bild_bereiche(seite)
    bildflaeche = sum(abs(r) for r in bilder)
    seitenflaeche = abs(seite.rect) or 1.0
    zeichen = _sichtbare_zeichen(seite)
    if zeichen == 0:
        if bilder:
            return "seite"
        # Weder Text noch Bilder: nur bei Zeichnungen (in Pfade gewandelter Text) OCR versuchen
        return "seite" if _hat_zeichnungen(seite) else "nein"
    if zeichen < WENIG_TEXT_ZEICHEN and bildflaeche >= SCAN_BILD_ANTEIL * seitenflaeche:
        return "seite"
    return "bilder" if bilder else "nein"


def ist_scan_seite(seite) -> bool:
    """Kompatibilität: True, wenn die ganze Seite per OCR gelesen werden muss."""
    return ocr_noetig(seite) == "seite"


# ----------------------------------------------------------------------
# OCR-Kern (läuft im Kindprozess ODER im eigenen Prozess)
# ----------------------------------------------------------------------
def _plausibilitaet(texte) -> float:
    """Anteil der OCR-Wörter, die wie normale Wörter/Zahlen aussehen (0..1).
    Aufrechte Seiten liegen bei ~0,8, kopfstehende bei ~0,1, um 90° gedrehte bei ~0,05."""
    tokens = [t for t in texte if t and t.strip()]
    if not tokens:
        return 0.0
    gut = 0
    for t in tokens:
        kern = t.strip(_RANDZEICHEN)
        if not kern:
            continue
        if re.fullmatch(r"[\d.,:/\-]+", kern):                       # Zahlen, Daten, Beträge
            gut += 1
        elif kern.isalpha():
            if not _EUROPAEISCH.fullmatch(kern):
                continue
            if len(kern) >= 2 and any(z in _VOKALE for z in kern.lower()) and (
                    kern.islower() or kern.isupper() or kern[1:].islower()):
                gut += 1
            elif len(kern) == 1 and kern.isupper():
                gut += 1
        elif re.fullmatch(r"[A-Za-z]{1,4}[\-/]?\d[\d\-/]*|[A-Z]{2}\d{2}[A-Z0-9]{2,}|[\w.\-+]+@[\w.\-]+", kern):
            gut += 1                                                   # Kennzeichen, IBAN-Gruppen, E-Mail
    return gut / len(tokens)


def _woerter_aus_ocr_pdf(ocr_bytes, dpi, pix_x, pix_y, matrix):
    """Wörter (8-Tupel wie get_text("words")) aus dem OCR-PDF, in Seitenkoordinaten umgerechnet."""
    ocr_doc = fitz.open("pdf", ocr_bytes)
    try:
        ocr_seite = ocr_doc[0]
        zoom = fitz.Matrix(dpi / 72.0, dpi / 72.0)        # OCR-PDF (Punkte bei dpi) -> Pixel
        rueck = ~matrix                                    # Pixel -> Seitenkoordinaten
        ergebnis = []
        for w in ocr_seite.get_text("words"):
            r = fitz.Rect(w[:4]) * zoom
            r = fitz.Rect(r.x0 + pix_x, r.y0 + pix_y, r.x1 + pix_x, r.y1 + pix_y) * rueck
            r.normalize()
            ergebnis.append((r.x0, r.y0, r.x1, r.y1, w[4], w[5], w[6], w[7]))
        return ergebnis
    finally:
        ocr_doc.close()


def _ocr_durchlauf(seite, dpi, clip, winkel, sprache, tessdata):
    """Rendert die Seite (oder den Ausschnitt) um `winkel` gedreht, lässt Tesseract laufen und
    liefert die Wörter in Seitenkoordinaten (Drehung herausgerechnet)."""
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0).prerotate(winkel)
    # RGB ist Pflicht: mit Graustufen-Pixmaps liefert pdfocr_tobytes keine Wörter (MuPDF 1.28)
    pix = seite.get_pixmap(matrix=matrix, clip=clip, colorspace=fitz.csRGB, alpha=False)
    pix.set_dpi(dpi, dpi)
    ocr_bytes = pix.pdfocr_tobytes(compress=False, language=sprache, tessdata=tessdata)
    return _woerter_aus_ocr_pdf(ocr_bytes, dpi, pix.x, pix.y, matrix)


def _ohne_textebene(woerter, seite, clip):
    """Entfernt OCR-Wörter, die auf sichtbarem Text der Textebene liegen (sie wären Dubletten
    oder Verleser des echten Texts, z. B. bei Text über einem Hintergrundbild)."""
    try:
        textwoerter = [fitz.Rect(w[:4]) for w in seite.get_text("words", clip=clip)]
    except Exception:
        return woerter
    if not textwoerter:
        return woerter
    behalten = []
    for w in woerter:
        r = fitz.Rect(w[:4])
        flaeche = abs(r) or 1.0
        if any(abs(r & t) > 0.5 * flaeche for t in textwoerter if r.intersects(t)):
            continue
        behalten.append(w)
    return behalten


def _ocr_worker(pdf_pfad, seite_nr0, dpi, clip, sprache, tessdata, ausrichtung_pruefen=True,
                nur_bilder=False, winkel_fest=None):
    """Modulfunktion für den Kindprozess (muss per Import erreichbar sein – Start-Methode "spawn").

    Rückgabe: {"woerter": [(x0, y0, x1, y1, text, block, zeile, nr), ...], "winkel": 0|90|180|270,
               "plausibel": 0..1}. Koordinaten beziehen sich auf die Seite nach remove_rotation().
    winkel_fest: Ausrichtung vorgeben (z. B. für die Kontroll-OCR der Ausgabe) statt sie zu suchen.
    """
    warnings.simplefilter("ignore")
    doc = fitz.open(pdf_pfad)
    try:
        seite = doc[seite_nr0]
        if seite.rotation:
            seite.remove_rotation()
        clip_rect = fitz.Rect(clip) if clip else None
        beste = None
        if winkel_fest is not None:
            winkel_folge = (int(winkel_fest) % 360,)
        elif ausrichtung_pruefen:
            winkel_folge = (0, 180, 90, 270)
        else:
            winkel_folge = (0,)
        for winkel in winkel_folge:
            woerter = _ocr_durchlauf(seite, dpi, clip_rect, winkel, sprache, tessdata)
            quote = _plausibilitaet([w[4] for w in woerter])
            if beste is None or quote > beste[1]:
                beste = (woerter, quote, winkel)
            # Leere Seite (aufrecht nichts gelesen) oder plausibles Ergebnis: keine weiteren Drehungen.
            # Wenige Wörter bei 0° heißen NICHT "leer" – seitlicher Text liefert oft nur Bruchstücke.
            # Bei vielen Wörtern reicht ein mittlerer Anteil: verdrehte Seiten liegen dann unter 0,3,
            # verrauschte aufrechte Scans bei 0,5-0,7 (sonst kostet jede solche Seite vier OCR-Läufe).
            if (winkel == 0 and not woerter) or quote >= PLAUSIBEL_GUT or (
                    len(woerter) >= 40 and quote >= PLAUSIBEL_WARNUNG + 0.1):
                break
        woerter, quote, winkel = beste
        if nur_bilder and clip_rect is not None:
            woerter = _ohne_textebene(woerter, seite, clip_rect)
        return {"woerter": woerter, "winkel": winkel, "plausibel": quote}
    finally:
        doc.close()


def _ping_worker():
    """Selbsttest des Pools: liefert (PID, Start-Methode, ist Kindprozess)."""
    return (os.getpid(), multiprocessing.get_start_method(allow_none=True),
            multiprocessing.parent_process() is not None)


def _pool_beenden(pool, hart=False):
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    if hart:  # laufende Tesseract-Aufrufe sofort beenden (Abbruch durch den Nutzer)
        try:
            for prozess in list(getattr(pool, "_processes", {}).values()):
                prozess.terminate()
        except Exception:
            pass


# ----------------------------------------------------------------------
# OcrDienst
# ----------------------------------------------------------------------
class OcrDienst:
    """OCR außerhalb des GUI-Threads: Prozess-Pool (Start-Methode "spawn" wie unter Windows),
    damit Tesseract den GIL der Oberfläche nicht blockiert. Kann der Pool nicht gestartet werden,
    läuft die OCR im eigenen Prozess (Oberfläche friert dann zwischendurch ein).

    Ergebnisse werden je (Datei, Seite, dpi, Ausschnitt) zwischengespeichert, damit Analyse,
    Schwärzung und Kontrolle dieselbe Seite nicht mehrfach lesen.
    """

    def __init__(self, prozesse: int | None = None):
        kerne = os.cpu_count() or 2
        self.prozesse = max(1, prozesse if prozesse else min(3, kerne - 1))
        self._pool = None
        self._pool_versuche = 0
        self._lock = threading.Lock()
        self._abbruch = threading.Event()
        self._cache: dict = {}
        self.tessdata = _tessdata_finden()
        self.sprache, self.sprach_warnung = _ocr_sprache(self.tessdata)
        self.in_prozess = False           # True, sobald der Fallback ohne Pool genutzt wird
        self.hinweise: list[str] = []     # einmalige Hinweise (z. B. Fallback aktiv)

    # -- Pool-Verwaltung ------------------------------------------------
    def _pool_holen(self):
        """Liefert den Pool (legt ihn beim ersten Mal an) oder None, wenn er nicht startbar ist."""
        with self._lock:
            if self._pool is None and self._pool_versuche < 2:
                self._pool_versuche += 1
                try:
                    self._pool = concurrent.futures.ProcessPoolExecutor(
                        max_workers=self.prozesse, mp_context=multiprocessing.get_context("spawn"))
                except Exception as e:  # z. B. eingeschränkte Umgebung ohne Prozessstart
                    self._pool = None
                    self._pool_fehler = str(e)
            return self._pool

    def _fallback_melden(self, grund):
        if not self.in_prozess:
            self.in_prozess = True
            self.hinweise.append(f"OCR läuft im Hauptprozess ({grund}) – die Oberfläche kann "
                                 f"während der Texterkennung kurz einfrieren.")

    def _pool_verwerfen(self, hart=False):
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            _pool_beenden(pool, hart=hart)

    def _ausfuehren(self, funktion, *args):
        """Führt `funktion(*args)` im Pool aus (Abbruch und Zeitlimit beachtend).

        Lässt sich der Pool nicht starten, läuft die Funktion im eigenen Prozess. Stürzt ein
        Kindprozess ab, wird der Pool einmal neu aufgebaut; stürzt er erneut ab, gilt der Auftrag
        als gescheitert – KEIN Fallback im eigenen Prozess, derselbe Absturz würde die Oberfläche
        mitreißen.
        """
        if self._abbruch.is_set():
            raise OcrAbgebrochen()
        if self.in_prozess:
            return funktion(*args)
        fehlschlaege = 0
        while True:
            pool = self._pool_holen()
            if pool is None:
                self._fallback_melden("Prozess-Pool konnte nicht gestartet werden: "
                                      + getattr(self, "_pool_fehler", "unbekannt"))
                return funktion(*args)
            try:
                zukunft = pool.submit(funktion, *args)
            except Exception as e:  # Pool gerade im Abbau (z. B. nach abbrechen())
                self._pool_verwerfen(hart=True)
                if self._abbruch.is_set():
                    raise OcrAbgebrochen()
                fehlschlaege += 1
                if fehlschlaege >= 2:
                    raise RuntimeError(f"OCR-Prozess nicht verfügbar ({e})")
                continue
            start = time.monotonic()
            while True:
                try:
                    return zukunft.result(timeout=0.25)
                except concurrent.futures.TimeoutError:
                    if self._abbruch.is_set():
                        zukunft.cancel()
                        self._pool_verwerfen(hart=True)
                        raise OcrAbgebrochen()
                    if time.monotonic() - start > OCR_ZEITLIMIT_S:
                        self._pool_verwerfen(hart=True)
                        raise RuntimeError(f"Zeitlimit von {OCR_ZEITLIMIT_S} s überschritten")
                except concurrent.futures.process.BrokenProcessPool:
                    self._pool_verwerfen(hart=True)
                    if self._abbruch.is_set():
                        raise OcrAbgebrochen()
                    fehlschlaege += 1
                    if fehlschlaege >= 2:
                        raise RuntimeError("OCR-Prozess abgestürzt")
                    break  # Pool neu aufbauen und den Auftrag einmal wiederholen

    def selbsttest(self):
        """Prüft den Pool: liefert (PID des Arbeiters, Start-Methode, ist Kindprozess) oder None."""
        try:
            return self._ausfuehren(_ping_worker)
        except Exception:
            return None

    # -- Schnittstelle ---------------------------------------------------
    @staticmethod
    def _datei_schluessel(pdf_pfad):
        p = Path(pdf_pfad)
        try:
            st = p.stat()
            return (str(p.resolve()), st.st_size, int(st.st_mtime))
        except OSError:
            return (str(p), 0, 0)

    def ergebnis(self, pdf_pfad, seite_nr0: int, dpi: int = 300, clip=None, winkel=None) -> dict:
        """Vollständiges OCR-Ergebnis einer Seite: {"woerter": 8-Tupel, "winkel", "plausibel", "warnung"}.
        clip: nur dieser Bereich (Bilder auf Textseiten; dort keine Ausrichtungssuche).
        winkel: Ausrichtung vorgeben (Kontroll-OCR der Ausgabe) statt sie zu suchen."""
        clip_tupel = tuple(round(float(v), 1) for v in fitz.Rect(clip)) if clip is not None else None
        schluessel = (self._datei_schluessel(pdf_pfad), seite_nr0, dpi, clip_tupel, winkel)
        if schluessel in self._cache:
            return self._cache[schluessel]
        if self.sprache is None:
            return {"woerter": [], "winkel": 0, "plausibel": 0.0, "warnung": self.sprach_warnung}
        try:
            roh = self._ausfuehren(_ocr_worker, str(pdf_pfad), seite_nr0, dpi, clip_tupel,
                                   self.sprache, self.tessdata, clip is None, clip is not None, winkel)
        except OcrAbgebrochen:
            return {"woerter": [], "winkel": 0, "plausibel": 0.0, "warnung": "Abgebrochen"}
        except Exception as e:
            return {"woerter": [], "winkel": 0, "plausibel": 0.0,
                    "warnung": f"Seite {seite_nr0 + 1}: OCR fehlgeschlagen ({e}) – Seite nicht lesbar."}
        warnung = self.sprach_warnung
        if roh["winkel"] and winkel is None:
            hinweis = (f"Seite {seite_nr0 + 1}: Scan lag um {roh['winkel']}° gedreht – "
                       f"OCR mit korrigierter Ausrichtung.")
            warnung = f"{warnung} {hinweis}" if warnung else hinweis
        if roh["plausibel"] < PLAUSIBEL_WARNUNG and len(roh["woerter"]) >= 5 and winkel is None:
            hinweis = (f"Seite {seite_nr0 + 1}: OCR-Text ist unplausibel (Seite verdreht, Handschrift "
                       f"oder unleserlich?) – dort kann NICHTS zuverlässig erkannt werden. Unbedingt "
                       f"manuell prüfen!")
            warnung = f"{warnung} {hinweis}" if warnung else hinweis
        ergebnis = {"woerter": roh["woerter"], "winkel": roh["winkel"],
                    "plausibel": roh["plausibel"], "warnung": warnung}
        self._cache[schluessel] = ergebnis
        return ergebnis

    def woerter(self, pdf_pfad, seite_nr0: int, dpi: int = 300, clip=None, winkel=None):
        """Wörter der OCR-Ebene einer Seite (nach remove_rotation; mit clip nur dieser Bereich).

        Rückgabe: (Liste von (x0, y0, x1, y1, text), Warnung oder None). Bei kopfstehenden oder
        seitlichen Scans wird die Ausrichtung über die Plausibilität der Wörter erkannt und korrigiert
        (winkel=None); mit winkel wird diese Ausrichtung ohne Suche verwendet.
        """
        ergebnis = self.ergebnis(pdf_pfad, seite_nr0, dpi, clip, winkel)
        return [tuple(w[:5]) for w in ergebnis["woerter"]], ergebnis["warnung"]

    def winkel(self, pdf_pfad, seite_nr0: int, dpi: int = 300) -> int:
        """Erkannte Ausrichtung (0/90/180/270) der Seite – OCR läuft, falls noch nicht geschehen."""
        return self.ergebnis(pdf_pfad, seite_nr0, dpi)["winkel"]

    def text(self, pdf_pfad, seite_nr0: int, dpi: int = 300, winkel=None) -> str:
        """OCR-Text einer Seite (für die Kontroll-OCR), zeilenweise zusammengesetzt."""
        return woerter_zu_text(self.ergebnis(pdf_pfad, seite_nr0, dpi, None, winkel)["woerter"])

    def abbrechen(self):
        """Stoppt laufende und wartende OCR-Aufträge (Kindprozesse werden beendet)."""
        self._abbruch.set()
        self._pool_verwerfen(hart=True)

    def zuruecksetzen(self):
        """Hebt einen Abbruch wieder auf (für einen neuen Lauf mit demselben Dienst)."""
        self._abbruch.clear()
        self._pool_versuche = 0

    def schliessen(self):
        """Beendet den Pool und leert den Zwischenspeicher."""
        self._pool_verwerfen(hart=True)
        self._cache.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.schliessen()
        return False


def woerter_zu_text(woerter) -> str:
    """Setzt Wörter (5- oder 8-Tupel) zu Text zusammen: Zeilen durch Umbruch, Wörter durch Leerzeichen."""
    if not woerter:
        return ""
    if len(woerter[0]) >= 8:
        zeilen: dict = {}
        for w in woerter:
            zeilen.setdefault((w[5], w[6]), []).append((w[7], w[4]))
        return "\n".join(" ".join(t for _, t in sorted(z)) for _, z in sorted(zeilen.items()))
    # 5-Tupel: Zeilen über die y-Lage bilden
    sortiert = sorted(woerter, key=lambda w: (round((w[1] + w[3]) / 2 / 6), w[0]))
    zeilen, aktuell, letzte_mitte = [], [], None
    for w in sortiert:
        mitte = (w[1] + w[3]) / 2
        if letzte_mitte is not None and abs(mitte - letzte_mitte) > max(3.0, 0.6 * (w[3] - w[1])):
            zeilen.append(" ".join(t for _, t in sorted(aktuell)))
            aktuell = []
        aktuell.append((w[0], w[4]))
        letzte_mitte = mitte
    if aktuell:
        zeilen.append(" ".join(t for _, t in sorted(aktuell)))
    return "\n".join(zeilen)


# ----------------------------------------------------------------------
# Kompatibilität (alte Aufrufer): OCR-Textpage im eigenen Prozess
# ----------------------------------------------------------------------
def ocr_textpage(seite, melde=None):
    """Erzeugt per OCR eine durchsuchbare Textebene für eine Scan-Seite (im eigenen Prozess).
    Rückgabe: (textpage oder None, Warnung oder None). Dreht /Rotate-Seiten vorher gerade."""
    tessdata = _tessdata_finden()
    sprache, warnung = _ocr_sprache(tessdata)
    if sprache is None:
        return None, warnung
    try:
        if seite.rotation:
            seite.remove_rotation()
        tp = seite.get_textpage_ocr(language=sprache, dpi=300, full=True, tessdata=tessdata)
        return tp, warnung
    except Exception as e:
        return None, f"OCR fehlgeschlagen: {e}"
