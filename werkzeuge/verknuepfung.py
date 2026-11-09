#!/usr/bin/env python3
"""Desktop-Verknüpfung für den PDF-Anonymisierer anlegen (wird von Installieren.bat aufgerufen).

Warum ein Python-Skript statt echo-Zeilen in der Batch-Datei?
- Pfade mit Umlauten, "&", "!", Klammern oder Apostroph überleben weder cmd-"echo"
  noch eine .ps1 ohne BOM (Windows PowerShell 5.1 liest BOM-lose Skripte als ANSI).
- Hier wandern alle Pfade als Umgebungsvariablen zu PowerShell (Unicode, kein
  Quoting), die .ps1 enthält keinen einzigen Pfad und wird als UTF-8 mit BOM
  geschrieben, und am Ende wird geprüft, ob die .lnk wirklich existiert.

Nebenbei wird .python_pfad.txt (Pfad zu pythonw.exe) für Starten.bat geschrieben.

Exit-Codes: 0 = Verknüpfung liegt auf dem Desktop, 1 = fehlgeschlagen (Meldung
steht in der Ausgabe), 2 = nicht unter Windows aufgerufen.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROGRAMM_ORDNER = Path(__file__).resolve().parent.parent
STARTSKRIPT = PROGRAMM_ORDNER / "pdf_anonymisierer.py"
ICON = PROGRAMM_ORDNER / "icon.ico"
PFAD_DATEI = PROGRAMM_ORDNER / ".python_pfad.txt"
NAME = "PDF-Anonymisierer"
BESCHREIBUNG = "PDF-Anonymisierer: personenbezogene Daten in PDFs durch Platzhalter ersetzen"

# Das PowerShell-Skript enthält bewusst keinen Pfad – alles kommt aus $env:PDFANON_*.
PS1_TEXT = f"""\
$ErrorActionPreference = 'Stop'
$ws  = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($env:PDFANON_LNK)
$lnk.TargetPath       = $env:PDFANON_ZIEL
$lnk.Arguments        = '"' + $env:PDFANON_SKRIPT + '"'
$lnk.WorkingDirectory = $env:PDFANON_ORDNER
$lnk.Description      = '{BESCHREIBUNG}'
if ($env:PDFANON_ICON) {{ $lnk.IconLocation = $env:PDFANON_ICON }}
$lnk.Save()
"""


def pythonw_pfad(python: Path | None = None) -> Path:
    """pythonw.exe neben dem laufenden Interpreter (ohne Konsolenfenster); sonst der Interpreter selbst."""
    exe = Path(python or sys.executable).resolve()
    ohne_konsole = exe.with_name("pythonw.exe")
    return ohne_konsole if ohne_konsole.exists() else exe


def desktop_ordner() -> Path:
    """Der echte Desktop-Ordner – auch wenn OneDrive ihn umgeleitet hat (SHGetKnownFolderPath)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            # FOLDERID_Desktop = {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
            kennung = GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                           (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41))
            zeiger = ctypes.c_wchar_p()
            shell32 = ctypes.windll.shell32
            shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD,
                                                     wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
            if shell32.SHGetKnownFolderPath(ctypes.byref(kennung), 0, None, ctypes.byref(zeiger)) == 0:
                try:
                    return Path(zeiger.value)
                finally:
                    ctypes.windll.ole32.CoTaskMemFree(zeiger)
        except Exception:
            pass
    return Path(os.environ.get("USERPROFILE") or Path.home()) / "Desktop"


def umgebung(ziel: Path, skript: Path, ordner: Path, lnk: Path, icon: Path | None = None,
             basis: dict | None = None) -> dict:
    """Umgebungsvariablen für PowerShell – Pfade werden unverändert als Unicode übergeben."""
    env = dict(os.environ if basis is None else basis)
    env["PDFANON_ZIEL"] = str(ziel)
    env["PDFANON_SKRIPT"] = str(skript)
    env["PDFANON_ORDNER"] = str(ordner)
    env["PDFANON_LNK"] = str(lnk)
    env["PDFANON_ICON"] = str(icon) if icon else ""
    return env


def schreibe_ps1(ordner: Path) -> Path:
    """Schreibt das PowerShell-Skript als UTF-8 MIT BOM (sonst liest PowerShell 5.1 es als ANSI)."""
    ps1 = Path(ordner) / "pdf_anonymisierer_verknuepfung.ps1"
    ps1.write_text(PS1_TEXT, encoding="utf-8-sig")
    return ps1


def schreibe_python_pfad(pythonw: Path, datei: Path = PFAD_DATEI) -> None:
    """Merkt sich den Interpreter für Starten.bat: UTF-8 ohne BOM, ohne Zeilenumbruch (für set /p)."""
    datei.write_text(str(pythonw), encoding="utf-8")


def powershell_befehle(ps1: Path) -> list[list[str]]:
    """Erst die .ps1-Datei; falls Richtlinien Skriptdateien sperren, derselbe Code per -Command."""
    basis = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"]
    einzeilig = "; ".join(z for z in PS1_TEXT.splitlines() if z.strip())
    return [basis + ["-File", str(ps1)],
            basis + ["-Command", einzeilig]]


def verknuepfung_anlegen(pythonw: Path, desktop: Path | None = None) -> Path:
    """Legt <Desktop>\\PDF-Anonymisierer.lnk an und gibt den Pfad zurück; wirft RuntimeError bei Fehlern."""
    desktop = desktop or desktop_ordner()
    if not desktop.is_dir():
        raise RuntimeError(f"Desktop-Ordner nicht gefunden: {desktop}")
    if not STARTSKRIPT.exists():
        raise RuntimeError(f"Startskript fehlt: {STARTSKRIPT}")
    lnk = desktop / f"{NAME}.lnk"
    env = umgebung(ziel=pythonw, skript=STARTSKRIPT, ordner=PROGRAMM_ORDNER, lnk=lnk,
                   icon=ICON if ICON.exists() else None)
    fehler: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        ps1 = schreibe_ps1(Path(tmp))
        for befehl in powershell_befehle(ps1):
            try:
                lauf = subprocess.run(befehl, env=env, capture_output=True, text=True,
                                      encoding="utf-8", errors="replace", timeout=120)
            except (OSError, subprocess.TimeoutExpired) as e:
                fehler.append(f"{befehl[0]} konnte nicht gestartet werden: {e}")
                continue
            if lauf.returncode == 0 and lnk.exists():
                return lnk
            meldung = (lauf.stderr or lauf.stdout or "").strip() or f"Exit-Code {lauf.returncode}"
            fehler.append(meldung)
    raise RuntimeError("PowerShell konnte die Verknüpfung nicht anlegen.\n" + "\n".join(fehler))


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        print("Dieses Skript legt eine Windows-Desktop-Verknüpfung an und läuft nur unter Windows.")
        return 2
    pythonw = pythonw_pfad()
    schreibe_python_pfad(pythonw)
    print(f"      Python für den Start: {pythonw}")
    try:
        lnk = verknuepfung_anlegen(pythonw)
    except RuntimeError as e:
        print(f"      FEHLER: {e}")
        print("      Das Programm lässt sich trotzdem per Doppelklick auf Starten.bat starten.")
        return 1
    print(f"      Verknüpfung angelegt: {lnk}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
