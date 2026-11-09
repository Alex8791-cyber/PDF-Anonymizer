"""Dateiverwaltung: PDFs einsammeln, Einstellungen laden/speichern, Fehlerprotokoll, Ordner öffnen,
Einzelinstanz-Sperre, verwaiste Zwischendateien, CSV-Vorschau (Kundenliste)."""

import csv
import io
import json
import os
import re
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

# Dateinamen, die die Schwärzung selbst erzeugt (neu: anonym_01.pdf, alt: <name>_anonym.pdf)
_AUSGABE_NAME = re.compile(r"^anonym_\d+(_PRUEFEN)?$|_anonym$", re.IGNORECASE)
# Zwischendateien der Schwärzung („.anonym_tmp_<PID>_<Kennung>.pdf“): nie eine Eingabe; bleiben nur nach
# einem Absturz liegen (GR-11)
_ZWISCHEN_NAME = re.compile(r"^\.anonym_tmp_(\d+)_", re.IGNORECASE)
_CLOUD_MERKMALE = ("onedrive", "dropbox", "icloud", "google drive", "googledrive",
                   "nextcloud", "sharepoint", "box sync", "mega")


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


def sammle_pdfs_bericht(pfade) -> dict:
    """
    Nimmt Dateien UND Ordner entgegen und liefert einen Bericht:
      {"pdfs": [Path], "uebersprungen": [Path] (keine PDF), "ausgaben": [Path]
       (bereits anonymisierte Dateien aus Ordner-Scans), "zwischendateien": [Path] (Reste einer
       abgebrochenen Schwärzung, nie Eingabe), "leere_ordner": [Path], "fehlend": [Path]}
    Ordner werden rekursiv durchsucht (Endung .pdf in jeder Schreibweise); Ausgaben des
    Programms werden dabei ausgelassen. Einzeln übergebene Dateien werden angenommen
    (auch bereits anonymisierte, z. B. zum Nachschwärzen) – außer Zwischendateien.
    """
    bericht = {"pdfs": [], "uebersprungen": [], "ausgaben": [], "zwischendateien": [],
               "leere_ordner": [], "fehlend": []}
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
                if ist_zwischendatei(datei):
                    bericht["zwischendateien"].append(datei)
                elif ist_ausgabedatei(datei):
                    bericht["ausgaben"].append(datei)
                else:
                    bericht["pdfs"].append(datei)
        elif pfad.is_file():
            if ist_zwischendatei(pfad):
                bericht["zwischendateien"].append(pfad)
            elif pfad.suffix.lower() == ".pdf":
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
            os.startfile(str(pfad))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(pfad)])
        else:
            subprocess.Popen(["xdg-open", str(pfad)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
