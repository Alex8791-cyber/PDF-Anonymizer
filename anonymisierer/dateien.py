"""Dateiverwaltung: PDFs einsammeln, Einstellungen laden/speichern, Fehlerprotokoll, Ordner öffnen."""

import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

PROGRAMM_NAME = "PDF-Anonymisierer"
EINSTELLUNGEN_DATEI = "einstellungen.json"
FEHLERLOG_DATEI = "fehler.log"
FEHLERLOG_MAX_BYTES = 200_000          # danach wird nach fehler.log.1 rotiert
AUSGABE_ORDNER = "anonymisiert"        # Unterordner, in den die Schwärzung schreibt

# Dateinamen, die die Schwärzung selbst erzeugt (neu: anonym_01.pdf, alt: <name>_anonym.pdf)
_AUSGABE_NAME = re.compile(r"^anonym_\d+(_PRUEFEN)?$|_anonym$", re.IGNORECASE)
_CLOUD_MERKMALE = ("onedrive", "dropbox", "icloud", "google drive", "googledrive",
                   "nextcloud", "sharepoint", "box sync", "mega")


# ----------------------------------------------------------------------
# PDFs einsammeln
# ----------------------------------------------------------------------
def ist_ausgabedatei(pfad: Path) -> bool:
    """True, wenn die Datei eine Ausgabe des Programms ist (Ordner „anonymisiert“ oder Ausgabename)."""
    pfad = Path(pfad)
    if any(teil.lower() == AUSGABE_ORDNER for teil in pfad.parts[:-1]):
        return True
    return bool(_AUSGABE_NAME.search(pfad.stem))


def sammle_pdfs_bericht(pfade) -> dict:
    """
    Nimmt Dateien UND Ordner entgegen und liefert einen Bericht:
      {"pdfs": [Path], "uebersprungen": [Path] (keine PDF), "ausgaben": [Path]
       (bereits anonymisierte Dateien aus Ordner-Scans), "leere_ordner": [Path], "fehlend": [Path]}
    Ordner werden rekursiv durchsucht (Endung .pdf in jeder Schreibweise); Ausgaben des
    Programms werden dabei ausgelassen. Einzeln übergebene Dateien werden immer angenommen
    (auch bereits anonymisierte, z. B. zum Nachschwärzen).
    """
    bericht = {"pdfs": [], "uebersprungen": [], "ausgaben": [], "leere_ordner": [], "fehlend": []}
    for eintrag in pfade:
        pfad = Path(eintrag)
        if pfad.is_dir():
            treffer = []
            try:
                for datei in pfad.rglob("*"):
                    try:
                        if datei.suffix.lower() == ".pdf" and datei.is_file():
                            treffer.append(datei)
                    except OSError:
                        continue
            except OSError:
                pass
            if not treffer:
                bericht["leere_ordner"].append(pfad)
                continue
            for datei in sorted(treffer):
                if ist_ausgabedatei(datei):
                    bericht["ausgaben"].append(datei)
                else:
                    bericht["pdfs"].append(datei)
        elif pfad.is_file():
            if pfad.suffix.lower() == ".pdf":
                bericht["pdfs"].append(pfad)
            else:
                bericht["uebersprungen"].append(pfad)
        else:
            bericht["fehlend"].append(pfad)

    # Dubletten entfernen (gleicher Pfad in verschiedener Schreibweise), Reihenfolge behalten
    eindeutig, gesehen = [], set()
    for pdf in bericht["pdfs"]:
        try:
            kennung = str(pdf.resolve()).lower() if sys.platform == "win32" else str(pdf.resolve())
        except OSError:
            kennung = str(pdf)
        if kennung not in gesehen:
            gesehen.add(kennung)
            eindeutig.append(pdf)
    bericht["pdfs"] = eindeutig
    return bericht


def sammle_pdfs(pfade) -> list[Path]:
    """Nimmt Dateien UND Ordner entgegen, liefert alle PDFs darin (ohne eigene Ausgaben)."""
    return sammle_pdfs_bericht(pfade)["pdfs"]


def gemeinsamer_stamm(pfade) -> Path | None:
    """Gemeinsamer Elternordner aller Pfade (für die relative Anzeige im Baum); None ohne Pfade."""
    eltern = [str(Path(p).parent) for p in pfade]
    if not eltern:
        return None
    try:
        return Path(os.path.commonpath(eltern))
    except ValueError:        # verschiedene Laufwerke unter Windows
        return None


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


def _beschreibbar(ordner: Path) -> bool:
    """Prüft durch eine echte Schreibprobe, ob in den Ordner geschrieben werden darf."""
    try:
        with tempfile.NamedTemporaryFile(dir=ordner, prefix=".schreibprobe_", delete=True):
            pass
        return True
    except OSError:
        return False


def fehlerlog_pfad() -> Path:
    """
    Ort der fehler.log: neben dem Startskript, wenn dort geschrieben werden darf; sonst
    %LOCALAPPDATA%\\PDF-Anonymisierer\\fehler.log bzw. ~/.local/state/PDF-Anonymisierer/fehler.log.
    Bei PyInstaller nie in den temporären Entpack-Ordner (sys._MEIPASS) und nie neben die EXE.
    """
    gefroren = bool(getattr(sys, "frozen", False))
    meipass = getattr(sys, "_MEIPASS", None)
    if not gefroren:
        wurzel = _projektwurzel()
        if not (meipass and _liegt_in(wurzel, meipass)) and _beschreibbar(wurzel):
            return wurzel / FEHLERLOG_DATEI
    return _zustands_basis() / FEHLERLOG_DATEI


def fehler_protokollieren(typ, wert, tb) -> Path | None:
    """
    Schreibt eine Ausnahme mit Zeitstempel in die fehler.log (mit Größenbegrenzung).
    Liefert den Pfad der Logdatei oder None, wenn nirgends geschrieben werden konnte.
    """
    text = "".join(traceback.format_exception(typ, wert, tb))
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
            os.startfile(str(pfad))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(pfad)])
        else:
            subprocess.Popen(["xdg-open", str(pfad)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
