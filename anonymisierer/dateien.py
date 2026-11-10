"""Dateiverwaltung: PDFs einsammeln (Inhalt statt Endung, lange Windows-Pfade), Bilder und geschützte PDFs als
Arbeitskopie im Programmordner für Zwischendateien, Einstellungen laden/speichern, Fehlerprotokoll, Ordner öffnen,
Einzelinstanz-Sperre, verwaiste Zwischendateien, CSV-Vorschau (Kundenliste).

Das Modul braucht beim Import keine Fremdpakete (das Startskript lädt es vor der Paketprüfung); PyMuPDF wird nur
in den Funktionen geladen, die es brauchen (Bild umwandeln, Kennwort prüfen/entfernen)."""

import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

PROGRAMM_NAME = "PDF-Anonymisierer"
EINSTELLUNGEN_DATEI = "einstellungen.json"
KUNDENLISTE_DATEI = "kundenliste.dat"
SPERR_DATEI = "instanz.lock"
FEHLERLOG_DATEI = "fehler.log"
FEHLERLOG_MAX_BYTES = 200_000          # danach wird nach fehler.log.1 rotiert
AUSGABE_ORDNER = "anonymisiert"        # Unterordner, in den die Schwärzung schreibt
ZWISCHENDATEI_MAX_ALTER = 3600.0       # Sekunden; ältere Zwischendateien gelten immer als verwaist
TEMP_ORDNER = "temp"                   # Arbeitskopien (Bild als PDF, entschlüsselte PDF) je Programmsitzung
SITZUNG_MAX_ALTER = 7 * 86400.0        # Sekunden; ältere Sitzungsordner werden beim Start immer gelöscht
PROTOKOLL_PRAEFIX = "PDF-Anonymisierer_Protokoll_"   # Laufprotokolle („Protokoll speichern …“)

# Dateinamen, die die Schwärzung selbst erzeugt (neu: anonym_01.pdf, alt: <name>_anonym.pdf)
_AUSGABE_NAME = re.compile(r"^anonym_\d+(_PRUEFEN)?$|_anonym$", re.IGNORECASE)
# Zwischendateien der Schwärzung („.anonym_tmp_<PID>_<Kennung>.pdf“): nie eine Eingabe; bleiben nur nach
# einem Absturz liegen (GR-11)
_ZWISCHEN_NAME = re.compile(r"^\.anonym_tmp_(\d+)_", re.IGNORECASE)
_SITZUNG_NAME = re.compile(r"^sitzung_(\d+)_")
_CLOUD_MERKMALE = ("onedrive", "dropbox", "icloud", "google drive", "googledrive",
                   "nextcloud", "sharepoint", "box sync", "mega")

# ----------------------------------------------------------------------
# Inhalt statt Endung (R-01, R-10)
# ----------------------------------------------------------------------
KOPF_BYTES = 2048
BILD_ARTEN = ("jpeg", "png", "tiff", "bmp")          # werden auf Wunsch in eine PDF umgewandelt
BILD_ENDUNGEN = frozenset({".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".tif", ".tiff", ".bmp", ".dib"})
# Nur bei diesen Endungen wird der Inhalt gelesen (bei allen anderen sagt schon die Endung „keine PDF“, und das
# Lesen würde Cloud-Dateien unnötig herunterladen); „“ = Datei ohne Endung (z. B. Download aus einem Portal)
_INHALT_ENDUNGEN = frozenset({".pdf", ""}) | BILD_ENDUNGEN
# Dateien, die Windows, macOS oder Office selbst anlegen – kein Hinweis „keine PDF“ (sonst nur Rauschen)
_SYSTEM_DATEIEN = frozenset({"desktop.ini", "thumbs.db", "ehthumbs.db", "ehthumbs_vista.db", ".ds_store",
                             "_zuordnung.txt", "icon\r"})
ART_BESCHREIBUNG = {
    "pdf": "eine PDF-Datei", "jpeg": "ein Foto (JPEG)", "png": "ein Bild (PNG)", "tiff": "ein Bild (TIFF, z. B. Fax)",
    "bmp": "ein Bild (BMP)", "gif": "ein Bild (GIF)", "webp": "ein Bild (WEBP)", "heic": "ein iPhone-Foto (HEIC)",
    "html": "eine Webseite (HTML)", "svg": "eine Grafik (SVG)", "xml": "eine XML-Datei",
    "office": "eine Office- oder ZIP-Datei (z. B. Word, Excel)",
    "ole": "eine ältere Office-Datei oder eine Outlook-Nachricht", "rtf": "ein RTF-Text", "text": "eine Textdatei",
    "leer": "leer (0 Byte)", "unbekannt": "keine PDF-Datei", "endung": "keine PDF-Datei",
    "nicht_lesbar": "nicht lesbar"}
# Inhalte, die mit der Endung .pdf an die Engine gehen dürfen: echte PDFs und Unbestimmtes (Text, leere Datei,
# unbekannte Bytes) – dafür meldet die Engine „keine lesbare PDF-Datei“ oder repariert eine beschädigte PDF. Alles
# andere (Bilder, Webseiten, SVG, XML, ZIP …) öffnet PyMuPDF als Nicht-PDF; der erste Seitenzugriff brachte das
# ganze Programm zum Absturz (R-01, nachgemessen: JPEG, PNG, TIFF, BMP, GIF, HTML, XHTML, SVG, FB2, ZIP mit Bildern).
ENGINE_ARTEN = frozenset({"pdf", "text", "leer", "unbekannt"})
_BMP_KOPFGROESSEN = (12, 16, 40, 52, 56, 64, 108, 124)
_HTML_ANFAENGE = (b"<!doctype html", b"<html", b"<head", b"<body", b"<meta", b"<title", b"<script", b"<!-- ")
_HEIF_MARKEN = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif")


def _ist_text(kopf: bytes) -> bool:
    """Sieht der Anfang einer Datei wie Text aus (kaum Steuerzeichen)?"""
    if b"\x00" in kopf:
        return False
    steuer = sum(1 for b in kopf if b < 32 and b not in (9, 10, 12, 13))
    return steuer <= len(kopf) // 100


def art_aus_kopf(kopf: bytes) -> str:
    """Art einer Datei nach ihren ersten Bytes (nicht nach der Endung): "pdf", "jpeg", "png", "tiff", "bmp", "gif",
    "webp", "heic", "html", "svg", "xml", "office", "ole", "rtf", "text", "leer" oder "unbekannt"."""
    if not kopf:
        return "leer"
    if b"%PDF" in kopf[:1024]:                      # wie Acrobat: Kennung irgendwo in den ersten 1024 Bytes
        return "pdf"
    if kopf.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if kopf.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if kopf[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        return "tiff"
    if kopf[:2] == b"BM" and len(kopf) >= 18 and int.from_bytes(kopf[14:18], "little") in _BMP_KOPFGROESSEN:
        return "bmp"
    if kopf[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if kopf[:4] == b"RIFF" and kopf[8:12] == b"WEBP":
        return "webp"
    if kopf[4:8] == b"ftyp" and kopf[8:12] in _HEIF_MARKEN:
        return "heic"
    if kopf[:4] == b"PK\x03\x04":
        return "office"
    if kopf[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "ole"
    if kopf[:5] == b"{\\rtf":
        return "rtf"
    anfang = kopf.lstrip(b"\xef\xbb\xbf").lstrip().lower()
    if anfang.startswith(_HTML_ANFAENGE) or (anfang.startswith((b"<?xml", b"<!--")) and b"<html" in anfang):
        return "html"
    if b"<svg" in anfang[:600]:
        return "svg"
    if anfang.startswith(b"<?xml"):
        return "xml"
    if _ist_text(kopf):
        return "text"
    return "unbekannt"


def datei_art(pfad) -> str:
    """Art einer Datei nach ihrem INHALT (siehe art_aus_kopf); "nicht_lesbar", wenn sie nicht geöffnet werden kann."""
    try:
        with open(langpfad(pfad), "rb") as datei:
            kopf = datei.read(KOPF_BYTES)
    except OSError:
        return "nicht_lesbar"
    return art_aus_kopf(kopf)


def ist_bild_art(art: str) -> bool:
    return art in BILD_ARTEN


def fuer_engine_erlaubt(art: str) -> bool:
    """Darf eine Datei dieser Art (Endung .pdf) an Analyse, Schwärzung und Vorschau? (nicht_lesbar: ja – die Engine
    meldet den Fehler selbst)."""
    return art in ENGINE_ARTEN or art == "nicht_lesbar"


def art_beschreibung(art: str) -> str:
    return ART_BESCHREIBUNG.get(art, ART_BESCHREIBUNG["unbekannt"])


def ist_systemdatei(name: str) -> bool:
    """Von Windows/macOS/Office angelegte Dateien, versteckte Dateien und Dateien dieses Programms
    (_zuordnung.txt, Laufprotokolle) – im Ordner-Scan ohne Meldung übergangen."""
    klein = name.lower()
    return (klein in _SYSTEM_DATEIEN or name.startswith(("~$", ".")) or klein.startswith(PROTOKOLL_PRAEFIX.lower()))


# ----------------------------------------------------------------------
# Lange Pfade unter Windows (R-09)
# ----------------------------------------------------------------------
LANGPFAD_AB = 200        # ab dieser Länge arbeitet das Programm unter Windows mit „\\?\“ (Ausgabeordner und
#                          Ausgabename machen den Pfad noch um gut 35 Zeichen länger; Grenze sonst 260)


def langpfad(pfad, plattform: str | None = None) -> str:
    """Unter Windows: Pfad mit dem Präfix „\\\\?\\“ (bzw. „\\\\?\\UNC\\“ für Netzwerkpfade) – so öffnet und
    durchsucht Windows auch Pfade über 260 Zeichen, ohne dass „lange Pfade“ in der Registrierung eingeschaltet sein
    müssen. Andere Systeme und bereits so geschriebene Pfade bleiben unverändert."""
    text = os.fspath(pfad)
    if isinstance(text, bytes):
        text = os.fsdecode(text)
    if (plattform or sys.platform) != "win32" or text.startswith("\\\\?\\"):
        return text
    if sys.platform == "win32":
        text = os.path.abspath(text)
    text = text.replace("/", "\\")
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def ohne_langpfad(pfad) -> str:
    """Pfad ohne das Präfix „\\\\?\\“ – für Anzeige, Vergleich und gemeinsamen Stammordner."""
    text = os.fspath(pfad)
    if isinstance(text, bytes):
        text = os.fsdecode(text)
    if text.startswith("\\\\?\\UNC\\"):
        return "\\\\" + text[8:]
    if text.startswith("\\\\?\\"):
        return text[4:]
    return text


def pfad_fuer_programm(pfad, plattform: str | None = None) -> Path:
    """Pfad, mit dem Programm und Engine die Datei öffnen: unter Windows ab LANGPFAD_AB Zeichen mit „\\\\?\\“, sonst
    der gewohnte Pfad (kurze Pfade bleiben, wie sie sind)."""
    text = ohne_langpfad(pfad)
    if (plattform or sys.platform) == "win32" and len(text) >= LANGPFAD_AB:
        return Path(langpfad(text, plattform))
    return Path(text)


def _lesefehler_text(fehler: OSError, pfad) -> str:
    """Kurzer Grund, warum eine Datei oder ein Ordner nicht gelesen werden konnte."""
    nummer = getattr(fehler, "errno", None)
    winfehler = getattr(fehler, "winerror", None)
    lang = len(ohne_langpfad(pfad)) >= 250
    if nummer == 36 or (winfehler in (206, 3) and lang) or (lang and isinstance(fehler, FileNotFoundError)):
        return "Pfad zu lang – bitte den Ordner näher an C:\\ kopieren"
    if isinstance(fehler, PermissionError) or winfehler == 5:
        return "Zugriff verweigert"
    text = str(getattr(fehler, "strerror", None) or fehler)
    return text[:80]


# ----------------------------------------------------------------------
# PDFs einsammeln
# ----------------------------------------------------------------------
def ist_zwischendatei(pfad) -> bool:
    """True für Zwischendateien der Schwärzung (.anonym_tmp_<PID>_….pdf)."""
    return bool(_ZWISCHEN_NAME.match(Path(pfad).name))


def ist_ausgabedatei(pfad: Path) -> bool:
    """True, wenn die Datei eine Ausgabe des Programms ist (Ordner „anonymisiert“, Ausgabename oder
    Zwischendatei der Schwärzung)."""
    pfad = Path(pfad)
    if ist_zwischendatei(pfad):
        return True
    if any(teil.lower() == AUSGABE_ORDNER for teil in pfad.parts[:-1]):
        return True
    return bool(_AUSGABE_NAME.search(pfad.stem))


def _leerer_bericht() -> dict:
    return {"pdfs": [], "bilder": [], "pdf_ohne_endung": [], "uebersprungen": [], "keine_pdf": [],
            "nicht_lesbar": [], "ausgaben": [], "ausgaben_einzeln": [], "zwischendateien": [], "leere_ordner": [],
            "fehlend": [], "arten": {}, "gruende": {}}


def _endung(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def _einordnen(bericht: dict, pfad: Path, im_ordner: bool) -> bool:
    """Ordnet eine Datei nach ihrem Inhalt ein. Liefert True, wenn sie für den Ordner zählt (PDF, Bild, Ausgabe …)."""
    if ist_zwischendatei(pfad):
        if not im_ordner or _endung(pfad.name) == ".pdf":
            bericht["zwischendateien"].append(pfad)
            return True
        return False
    if im_ordner:
        if ist_systemdatei(pfad.name):
            return False
        if any(teil.lower() == AUSGABE_ORDNER for teil in pfad.parts[:-1]):
            if _endung(pfad.name) == ".pdf":           # alles im Ausgabeordner gehört dem Programm
                bericht["ausgaben"].append(pfad)
                return True
            return False
    endung = _endung(pfad.name)
    if endung not in _INHALT_ENDUNGEN:
        bericht["keine_pdf" if im_ordner else "uebersprungen"].append(pfad)
        bericht["arten"][pfad] = "endung"
        return False
    art = datei_art(pfad)
    if art == "pdf" or (endung == ".pdf" and art in ENGINE_ARTEN):
        if endung != ".pdf":
            bericht["pdf_ohne_endung"].append(pfad)   # PDF ohne passende Endung: Arbeitskopie mit „.pdf“
        elif ist_ausgabedatei(pfad):
            if im_ordner:
                bericht["ausgaben"].append(pfad)
            else:                                      # einzeln gewählt: wird angenommen, die Oberfläche fragt nach
                bericht["pdfs"].append(pfad)
                bericht["ausgaben_einzeln"].append(pfad)
        else:
            bericht["pdfs"].append(pfad)
        return True
    if ist_bild_art(art):
        bericht["bilder"].append(pfad)
        bericht["arten"][pfad] = art
        return True
    if art == "nicht_lesbar":
        bericht["nicht_lesbar"].append(pfad)
        bericht["gruende"][pfad] = "nicht lesbar (gesperrt oder Pfad zu lang?)"
        return True
    bericht["keine_pdf" if im_ordner else "uebersprungen"].append(pfad)
    bericht["arten"][pfad] = art
    return False


def _ordner_durchsuchen(ordner: Path, bericht: dict) -> bool:
    """Durchsucht einen Ordner samt Unterordnern (ohne Verknüpfungen zu folgen). Nichts wird still übergangen:
    Was nicht gelesen werden kann (Zugriff verweigert, Pfad zu lang …), steht unter „nicht_lesbar“ (R-09).
    Liefert True, wenn etwas Verwertbares (oder Unlesbares) gefunden wurde."""
    wurzel = langpfad(ordner) if sys.platform == "win32" else os.fspath(ordner)
    gefunden = []
    etwas = False
    stapel = [wurzel]
    while stapel:
        aktuell = stapel.pop()
        try:
            with os.scandir(aktuell) as eintraege:
                liste = list(eintraege)
        except OSError as fehler:
            pfad = pfad_fuer_programm(aktuell)
            bericht["nicht_lesbar"].append(pfad)
            bericht["gruende"][pfad] = _lesefehler_text(fehler, aktuell)
            etwas = True
            continue
        for eintrag in liste:
            try:
                if eintrag.is_dir(follow_symlinks=False):
                    if not (hasattr(eintrag, "is_junction") and eintrag.is_junction()):
                        stapel.append(eintrag.path)
                elif eintrag.is_file():
                    gefunden.append(eintrag.path)
            except OSError as fehler:
                pfad = pfad_fuer_programm(eintrag.path)
                bericht["nicht_lesbar"].append(pfad)
                bericht["gruende"][pfad] = _lesefehler_text(fehler, eintrag.path)
                etwas = True
    for text in sorted(gefunden, key=lambda t: Path(ohne_langpfad(t))):
        if _einordnen(bericht, pfad_fuer_programm(text), im_ordner=True):
            etwas = True
    return etwas


def _eindeutig(pfade: list) -> list:
    """Dubletten entfernen (gleicher Pfad in verschiedener Schreibweise), Reihenfolge behalten."""
    eindeutig, gesehen = [], set()
    for pfad in pfade:
        try:
            kennung = str(Path(ohne_langpfad(pfad)).resolve())
        except OSError:
            kennung = ohne_langpfad(pfad)
        if sys.platform == "win32":
            kennung = kennung.lower()
        if kennung not in gesehen:
            gesehen.add(kennung)
            eindeutig.append(pfad)
    return eindeutig


def sammle_pdfs_bericht(pfade) -> dict:
    """
    Nimmt Dateien UND Ordner entgegen und prüft jede Datei am INHALT (nicht nur an der Endung, R-01). Bericht:
      "pdfs": [Path]            echte PDFs (einzeln gewählte Ausgaben des Programms eingeschlossen)
      "bilder": [Path]          Bilder (JPEG, PNG, TIFF, BMP – auch mit falscher Endung wie „Foto.pdf“), die die
                                Oberfläche auf Wunsch in eine PDF umwandelt
      "pdf_ohne_endung": [Path] PDFs ohne die Endung .pdf (z. B. Download aus einem Portal)
      "uebersprungen": [Path]   einzeln gewählte Dateien, die keine PDF und kein Bild sind
      "keine_pdf": [Path]       solche Dateien aus Ordner-Scans (R-10; ohne System- und Programmdateien)
      "nicht_lesbar": [Path]    Dateien/Ordner, die nicht gelesen werden konnten (Grund in "gruende", R-09)
      "ausgaben": [Path]        Ausgaben des Programms aus Ordner-Scans (ausgelassen)
      "ausgaben_einzeln": [Path] einzeln gewählte Ausgaben (stehen auch in "pdfs"; die Oberfläche fragt nach, M-63)
      "zwischendateien": [Path] Reste einer abgebrochenen Schwärzung (nie Eingabe)
      "leere_ordner": [Path], "fehlend": [Path], "arten": {Path: Art}, "gruende": {Path: Text}
    Ordner werden rekursiv durchsucht; unter Windows auch über 260 Zeichen hinaus (Präfix „\\\\?\\“).
    """
    bericht = _leerer_bericht()
    for eintrag in pfade:
        pfad = pfad_fuer_programm(eintrag) if sys.platform == "win32" else Path(eintrag)
        try:
            ist_ordner = Path(langpfad(pfad)).is_dir()
            ist_datei = not ist_ordner and Path(langpfad(pfad)).is_file()
        except OSError as fehler:
            bericht["nicht_lesbar"].append(pfad)
            bericht["gruende"][pfad] = _lesefehler_text(fehler, pfad)
            continue
        if ist_ordner:
            if not _ordner_durchsuchen(pfad, bericht):
                bericht["leere_ordner"].append(pfad)
        elif ist_datei:
            _einordnen(bericht, pfad, im_ordner=False)
        else:
            bericht["fehlend"].append(pfad)
            if len(ohne_langpfad(pfad)) >= 250:
                bericht["gruende"][pfad] = "Pfad sehr lang"
    for schluessel in ("pdfs", "bilder", "pdf_ohne_endung"):
        bericht[schluessel] = _eindeutig(bericht[schluessel])
    return bericht


def sammle_pdfs(pfade) -> list[Path]:
    """Nimmt Dateien UND Ordner entgegen, liefert alle PDFs darin (ohne eigene Ausgaben)."""
    return sammle_pdfs_bericht(pfade)["pdfs"]


def gemeinsamer_stamm(pfade) -> Path | None:
    """Gemeinsamer Elternordner aller Pfade (für die relative Anzeige im Baum); None ohne Pfade. Das Präfix
    „\\\\?\\“ langer Windows-Pfade zählt nicht mit."""
    eltern = [str(Path(ohne_langpfad(p)).parent) for p in pfade]
    if not eltern:
        return None
    try:
        return Path(os.path.commonpath(eltern))
    except ValueError:        # verschiedene Laufwerke unter Windows
        return None


# ----------------------------------------------------------------------
# Arbeitskopien: Bild als PDF, entschlüsselte PDF (R-01, R-12)
# ----------------------------------------------------------------------
A4_LANG, A4_KURZ = 842.0, 595.0
_BILD_DATEITYP = {"jpeg": "jpg", "png": "png", "tiff": "tiff", "bmp": "bmp"}
_SITZUNG: Path | None = None


def _fitz():
    """PyMuPDF erst bei Bedarf laden (das Modul selbst braucht keine Fremdpakete)."""
    try:
        import pymupdf as fitz
    except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
        import fitz
    return fitz


def temp_basis() -> Path:
    """Ordner für Arbeitskopien: %LOCALAPPDATA%\\PDF-Anonymisierer\\temp bzw. ~/.local/state/PDF-Anonymisierer/temp –
    nie im Kundenordner und nie im servergespeicherten (Roaming-)Profil, denn eine entschlüsselte Kopie enthält
    das ganze Original."""
    return _zustands_basis() / TEMP_ORDNER


def sitzungsordner() -> Path:
    """Ordner dieser Programmsitzung („sitzung_<PID>_…“); wird beim ersten Bedarf angelegt."""
    global _SITZUNG
    if _SITZUNG is None or not _SITZUNG.is_dir():
        basis = temp_basis()
        basis.mkdir(parents=True, exist_ok=True)
        _SITZUNG = Path(tempfile.mkdtemp(prefix=f"sitzung_{os.getpid()}_", dir=basis))
    return _SITZUNG


def _innerhalb_temp(pfad) -> bool:
    return _liegt_in(Path(pfad), temp_basis())


def arbeitskopie_ziel(name: str) -> Path:
    """Pfad für eine neue Arbeitskopie: eigener Unterordner der Sitzung (gleiche Namen aus verschiedenen
    Kundenordnern stören sich nicht), der Dateiname bleibt erkennbar – er steht in _zuordnung.txt."""
    ordner = Path(tempfile.mkdtemp(prefix="kopie_", dir=sitzungsordner()))
    sicher = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "dokument"
    if not sicher.lower().endswith(".pdf"):
        sicher += ".pdf"
    return ordner / sicher[-120:]


def arbeitskopie_entfernen(pfad) -> bool:
    """Löscht eine Arbeitskopie samt ihrem Unterordner – nur innerhalb des Ordners für Arbeitskopien."""
    pfad = Path(pfad)
    if not _innerhalb_temp(pfad):
        return False
    ziel = pfad.parent if pfad.parent.name.startswith("kopie_") else pfad
    try:
        if ziel.is_dir():
            shutil.rmtree(ziel)
        elif ziel.exists():
            ziel.unlink()
        return True
    except OSError:
        return False


def sitzung_aufraeumen() -> bool:
    """Löscht alle Arbeitskopien dieser Sitzung (beim Beenden). True, wenn danach nichts mehr übrig ist."""
    global _SITZUNG
    ordner, _SITZUNG = _SITZUNG, None
    if ordner is None or not ordner.exists():
        return True
    shutil.rmtree(ordner, ignore_errors=True)
    return not ordner.exists()


def alte_sitzungen_aufraeumen(max_alter: float = SITZUNG_MAX_ALTER) -> list[Path]:
    """Löscht Arbeitskopien früherer Sitzungen (z. B. nach einem Absturz): Prozess beendet oder Ordner älter als
    max_alter Sekunden. Die eigene Sitzung bleibt. Liefert die gelöschten Ordner."""
    entfernt: list[Path] = []
    try:
        kandidaten = [p for p in temp_basis().iterdir() if p.is_dir() and _SITZUNG_NAME.match(p.name)]
    except OSError:
        return entfernt
    jetzt = time.time()
    for ordner in kandidaten:
        if _SITZUNG is not None and ordner == _SITZUNG:
            continue
        pid = int(_SITZUNG_NAME.match(ordner.name).group(1))
        try:
            alter = jetzt - ordner.stat().st_mtime
        except OSError:
            continue
        if pid == os.getpid() or (alter < max_alter and prozess_lebt(pid)):
            continue
        shutil.rmtree(ordner, ignore_errors=True)
        if not ordner.exists():
            entfernt.append(ordner)
    return entfernt


def bild_als_pdf(bild, ziel, art: str | None = None) -> int:
    """Wandelt ein Bild (JPEG, PNG, TIFF – auch mehrseitige Faxe –, BMP) mit PyMuPDF in eine PDF um: je Bildseite
    eine PDF-Seite, aufgerichtet nach der Lage-Angabe des Fotos (EXIF) und höchstens A4 groß (ein Handyfoto mit
    72 dpi wäre sonst über einen Meter breit; die Texterkennung liest die Seite dann wie einen Scan).
    Liefert die Seitenzahl; ValueError, wenn das Bild nicht lesbar ist."""
    fitz = _fitz()
    art = art or datei_art(bild)
    if art not in _BILD_DATEITYP:
        raise ValueError(f"Die Datei ist kein unterstütztes Bild ({art_beschreibung(art)}).")
    try:
        daten = Path(langpfad(bild)).read_bytes()
        with fitz.open(stream=daten, filetype=_BILD_DATEITYP[art]) as quelle:
            pdf_daten = quelle.convert_to_pdf()
    except OSError:
        raise
    except Exception as fehler:
        raise ValueError(f"Das Bild ist beschädigt oder nicht lesbar ({type(fehler).__name__}).") from fehler
    with fitz.open("pdf", pdf_daten) as zwischen, fitz.open() as neu:
        for nr, seite in enumerate(zwischen):
            rect = seite.rect
            if rect.width < 1 or rect.height < 1:
                continue
            faktor = min(1.0, A4_LANG / max(rect.width, rect.height), A4_KURZ / min(rect.width, rect.height))
            if faktor > 0.999:
                neu.insert_pdf(zwischen, from_page=nr, to_page=nr)
            else:
                seite_neu = neu.new_page(width=rect.width * faktor, height=rect.height * faktor)
                seite_neu.show_pdf_page(seite_neu.rect, zwischen, nr)
        if not len(neu):
            raise ValueError("Das Bild enthält keine lesbare Seite.")
        neu.save(os.fspath(ziel), garbage=3, deflate=True)
        return len(neu)


def pdf_kennwort_noetig(pfad) -> bool:
    """Braucht die PDF ein Kennwort zum Öffnen? (Nur-Besitzer-Kennwort mit Rechten: nein – die Engine liest sie.)"""
    fitz = _fitz()
    try:
        with fitz.open(langpfad(pfad), filetype="pdf") as doc:
            return bool(doc.needs_pass)
    except Exception:
        return False                      # beschädigt o. Ä.: die Analyse meldet das mit eigenem Text


def pdf_entschluesseln(pfad, kennwort: str, ziel) -> bool:
    """Öffnet eine geschützte PDF mit dem Kennwort und speichert eine Kopie OHNE Kennwort nach „ziel“ (Ordner für
    Arbeitskopien). False bei falschem Kennwort. Das Kennwort wird weder gespeichert noch protokolliert."""
    fitz = _fitz()
    with fitz.open(langpfad(pfad), filetype="pdf") as doc:
        if not doc.authenticate(kennwort):
            return False
        # Nach authenticate() needs_pass nicht mehr abfragen: PyMuPDF 2.1 setzt dabei den Schlüssel zurück
        doc.save(os.fspath(ziel), encryption=fitz.PDF_ENCRYPT_NONE, garbage=1)
    return True


def pdf_kopieren(pfad, ziel) -> None:
    """PDF ohne die Endung .pdf als Arbeitskopie mit Endung ablegen (die Engine erkennt die Art an der Endung)."""
    shutil.copyfile(langpfad(pfad), os.fspath(ziel))


def ist_cloud_ordner(pfad) -> bool:
    """Grobe Prüfung, ob ein Pfad in einem Cloud-synchronisierten Ordner liegt (OneDrive, Dropbox …)."""
    text = str(pfad).lower()
    if any(merkmal in text for merkmal in _CLOUD_MERKMALE):
        return True
    for variable in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        wert = os.environ.get(variable)
        if wert and text.startswith(wert.lower()):
            return True
    return False


# ----------------------------------------------------------------------
# Prozesse und verwaiste Zwischendateien
# ----------------------------------------------------------------------
def prozess_lebt(pid: int) -> bool:
    """True, wenn ein Prozess mit dieser PID läuft (im Zweifel True: lieber nichts löschen)."""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.restype = ctypes.c_void_p
            handle = kernel32.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return ctypes.get_last_error() == 5                   # Zugriff verweigert: Prozess existiert
            try:
                code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
                    return True
                return code.value == 259                              # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(ctypes.c_void_p(handle))
        except Exception:
            return True
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def zwischendateien_aufraeumen(ordner, max_alter: float = ZWISCHENDATEI_MAX_ALTER) -> list[Path]:
    """Löscht verwaiste Zwischendateien (.anonym_tmp_<PID>_….pdf) direkt im Ordner: der erzeugende Prozess
    lebt nicht mehr oder die Datei ist älter als max_alter Sekunden. Zwischendateien dieses Prozesses bleiben.
    Liefert die gelöschten Pfade (GR-11)."""
    entfernt: list[Path] = []
    try:
        kandidaten = [p for p in Path(ordner).iterdir() if ist_zwischendatei(p)]
    except OSError:
        return entfernt
    jetzt = time.time()
    for pfad in kandidaten:
        pid = int(_ZWISCHEN_NAME.match(pfad.name).group(1))
        if pid == os.getpid():
            continue
        try:
            alter = jetzt - pfad.stat().st_mtime
        except OSError:
            continue
        if alter < max_alter and prozess_lebt(pid):
            continue
        try:
            pfad.unlink()
            entfernt.append(pfad)
        except OSError:
            pass
    return entfernt


# ----------------------------------------------------------------------
# Einstellungen
# ----------------------------------------------------------------------
def _konfig_basis() -> Path:
    if sys.platform == "win32":
        basis = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        basis = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(basis) / PROGRAMM_NAME


def einstellungen_pfad() -> Path:
    """%APPDATA%\\PDF-Anonymisierer\\einstellungen.json bzw. ~/.config/PDF-Anonymisierer/einstellungen.json."""
    return _konfig_basis() / EINSTELLUNGEN_DATEI


def kundenliste_pfad() -> Path:
    """Speicherort der Kundenliste (nur gesalzene Prüfwerte, kein Klartext) neben den Einstellungen."""
    return einstellungen_pfad().parent / KUNDENLISTE_DATEI


def einstellungen_laden(pfad: Path | None = None) -> dict:
    """Liest die gespeicherten Einstellungen; bei fehlender oder defekter Datei ein leeres dict."""
    pfad = Path(pfad) if pfad is not None else einstellungen_pfad()
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return daten if isinstance(daten, dict) else {}


def einstellungen_speichern(daten: dict, pfad: Path | None = None) -> bool:
    """Schreibt die Einstellungen (erst in eine Temporärdatei, dann umbenennen). True bei Erfolg."""
    pfad = Path(pfad) if pfad is not None else einstellungen_pfad()
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        vorlaeufig = pfad.with_suffix(".tmp")
        vorlaeufig.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(vorlaeufig, pfad)
        return True
    except (OSError, TypeError, ValueError):
        return False


# ----------------------------------------------------------------------
# Einzelinstanz-Sperre (GR-10)
# ----------------------------------------------------------------------
class InstanzSperre:
    """Hält die Sperrdatei, solange das Programm läuft. Das Betriebssystem gibt die Sperre auch nach einem
    Absturz frei (flock bzw. msvcrt.locking hängen am offenen Datei-Handle) – es bleibt keine tote Sperre."""

    def __init__(self, pfad: Path, fd: int | None):
        self.pfad = pfad
        self._fd = fd

    @property
    def aktiv(self) -> bool:
        """False, wenn die Sperre nicht eingerichtet werden konnte (Programm läuft trotzdem)."""
        return self._fd is not None

    def freigeben(self):
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass


def instanz_sperren(pfad: Path | None = None) -> InstanzSperre | None:
    """Einzelinstanz-Sperre im Einstellungsordner. Liefert None, wenn bereits eine andere Instanz läuft.
    Kann die Sperre nicht eingerichtet werden (Ordner nicht beschreibbar, Dateisystem ohne Sperren),
    gibt es eine wirkungslose Sperre zurück – das Programm startet dann trotzdem."""
    pfad = Path(pfad) if pfad is not None else einstellungen_pfad().parent / SPERR_DATEI
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(pfad, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return InstanzSperre(pfad, None)
    try:
        if sys.platform == "win32":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as fehler:
        os.close(fd)
        belegt = isinstance(fehler, BlockingIOError) or getattr(fehler, "errno", None) in (11, 13, 35, 36)
        return None if belegt else InstanzSperre(pfad, None)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, f"{os.getpid():<10d}\n".encode("ascii"))
    except OSError:
        pass
    return InstanzSperre(pfad, fd)


# ----------------------------------------------------------------------
# Fehlerprotokoll
# ----------------------------------------------------------------------
def _zustands_basis() -> Path:
    if sys.platform == "win32":
        basis = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        basis = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(basis) / PROGRAMM_NAME


def _projektwurzel() -> Path:
    return Path(__file__).resolve().parent.parent


def _liegt_in(pfad: Path, ordner) -> bool:
    try:
        Path(pfad).resolve().relative_to(Path(ordner).resolve())
        return True
    except (ValueError, OSError):
        return False


_SCHREIBPROBEN: dict[str, bool] = {}


def _beschreibbar(ordner: Path) -> bool:
    """Prüft durch eine echte Schreibprobe, ob in den Ordner geschrieben werden darf (einmal je Ordner
    und Prozess – keine Probedatei bei jedem Aufruf)."""
    schluessel = str(ordner)
    if schluessel not in _SCHREIBPROBEN:
        try:
            with tempfile.NamedTemporaryFile(dir=ordner, prefix=".schreibprobe_", delete=True):
                pass
            _SCHREIBPROBEN[schluessel] = True
        except OSError:
            _SCHREIBPROBEN[schluessel] = False
    return _SCHREIBPROBEN[schluessel]


def fehlerlog_pfad() -> Path:
    """
    Ort der fehler.log: beim Start als Python-Skript neben dem Startskript, wenn dort geschrieben werden
    darf; sonst %LOCALAPPDATA%\\PDF-Anonymisierer\\fehler.log bzw. ~/.local/state/PDF-Anonymisierer/fehler.log.
    Die EXE (PyInstaller) schreibt immer dorthin – nie in den Entpack-Ordner (sys._MEIPASS), nie neben die EXE.
    """
    gefroren = bool(getattr(sys, "frozen", False))
    meipass = getattr(sys, "_MEIPASS", None)
    if not gefroren:
        wurzel = _projektwurzel()
        if not (meipass and _liegt_in(wurzel, meipass)) and _beschreibbar(wurzel):
            return wurzel / FEHLERLOG_DATEI
    return _zustands_basis() / FEHLERLOG_DATEI


# Verzeichnisteil eines absoluten Pfads (Windows mit Laufwerk, UNC oder POSIX) – beginnt nur nach Leerraum,
# Anführungszeichen oder Klammer, damit „1/2“ oder „und/oder“ unberührt bleiben.
_VERZEICHNIS_RE = re.compile(
    r"""(?<![^\s'"(\[=»«„“])(?:[A-Za-z]:)?(?:[\\/]{1,4}[^\\/\n'"()<>|:*?»«„“]+)+[\\/]{1,4}""")


def pfade_kuerzen(text: str) -> str:
    """Kürzt absolute Pfade in einem Text auf den letzten Bestandteil (KQ-14): Ordnernamen wie
    „Kunden\\Mustermann_Max“ oder der Windows-Benutzername gehören nicht ins Fehlerprotokoll."""
    def ersetzen(m):
        trenner = "\\" if "\\" in m.group(0) else "/"
        return "…" + trenner
    return _VERZEICHNIS_RE.sub(ersetzen, text)


def fehler_protokollieren(typ, wert, tb) -> Path | None:
    """
    Schreibt eine Ausnahme mit Zeitstempel in die fehler.log (mit Größenbegrenzung). Pfade im Text werden
    auf Datei-/Ordnernamen gekürzt (keine Kundenordner im Protokoll).
    Liefert den Pfad der Logdatei oder None, wenn nirgends geschrieben werden konnte.
    """
    text = pfade_kuerzen("".join(traceback.format_exception(typ, wert, tb)))
    eintrag = f"==== {datetime.now():%Y-%m-%d %H:%M:%S}  {PROGRAMM_NAME} ====\n{text}\n"
    kandidaten = []
    try:
        kandidaten.append(fehlerlog_pfad())
    except Exception:
        pass
    kandidaten.append(_zustands_basis() / FEHLERLOG_DATEI)
    for pfad in kandidaten:
        try:
            pfad.parent.mkdir(parents=True, exist_ok=True)
            if pfad.exists() and pfad.stat().st_size > FEHLERLOG_MAX_BYTES:
                os.replace(pfad, pfad.with_suffix(".log.1"))
            with open(pfad, "a", encoding="utf-8") as f:
                f.write(eintrag)
            return pfad
        except OSError:
            continue
    return None


# ----------------------------------------------------------------------
# CSV-Vorschau (Kundenliste: Spaltenzuordnung)
# ----------------------------------------------------------------------
CSV_KODIERUNGEN = ("utf-8-sig", "cp1252")
CSV_TRENNZEICHEN = ";,\t|"


def csv_vorschau(pfad, max_zeilen: int | None = 6) -> dict:
    """Liest die ersten Zeilen (max_zeilen=None: alle) einer CSV-Datei mit erkannter Kodierung (UTF-8,
    UTF-8 mit BOM, Windows-1252) und erkanntem Trennzeichen (; , Tab |). Leere Zeilen entfallen.
    Rückgabe: {"kodierung", "trennzeichen", "zeilen": [[str]]}.
    Wirft OSError (Datei nicht lesbar) bzw. ValueError (keine Textdatei)."""
    roh = Path(pfad).read_bytes()
    if max_zeilen is not None:
        roh = roh[:256_000]
    if b"\x00" in roh[:4096]:
        raise ValueError("Die Datei ist keine CSV-Textdatei (z. B. eine Excel-Datei). Bitte in Excel "
                         "„Speichern unter → CSV (Trennzeichen-getrennt)“ wählen.")
    text, kodierung = None, None
    for versuch in CSV_KODIERUNGEN:
        try:
            text = roh.decode(versuch)
            kodierung = versuch
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text, kodierung = roh.decode("latin-1"), "latin-1"
    probe = "\n".join(text.splitlines()[:20])
    try:
        trennzeichen = csv.Sniffer().sniff(probe, delimiters=CSV_TRENNZEICHEN).delimiter
    except csv.Error:
        erste = probe.splitlines()[0] if probe else ""
        trennzeichen = max(CSV_TRENNZEICHEN, key=erste.count) if erste else ";"
        if not erste.count(trennzeichen):
            trennzeichen = ";"
    zeilen = []
    for zeile in csv.reader(io.StringIO(text), delimiter=trennzeichen):
        if not any(z.strip() for z in zeile):
            continue
        zeilen.append([z.strip() for z in zeile])
        if max_zeilen is not None and len(zeilen) >= max_zeilen:
            break
    return {"kodierung": kodierung, "trennzeichen": trennzeichen, "zeilen": zeilen}


# ----------------------------------------------------------------------
# Ordner öffnen
# ----------------------------------------------------------------------
def oeffne_ordner(pfad) -> bool:
    """Öffnet einen Ordner im Dateimanager (Windows: Explorer, sonst xdg-open/open). Kein Abbruch bei Fehlern."""
    pfad = Path(pfad)
    if pfad.is_file():
        pfad = pfad.parent
    if not pfad.exists():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(ohne_langpfad(pfad))  # type: ignore[attr-defined]  # Explorer kennt „\\?\“ nicht
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(pfad)])
        else:
            subprocess.Popen(["xdg-open", str(pfad)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
