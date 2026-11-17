#!/usr/bin/env python3
"""Zeigt für Rückfragen, womit das Programm auf diesem Rechner läuft.

Aufruf (im Programmordner):  python werkzeuge\\pruefe_installation.py
Die Ausgabe kann man bei Problemen kopieren und mitschicken. Es wird nichts verändert.

Exit-Code 0 = alles vorhanden, 1 = etwas fehlt oder passt nicht (steht in der Ausgabe).

Mit --vc-laufzeit (für Installieren.bat und EXE-bauen.bat) nur die Probe, ob dieses Python die Visual-C++-Laufzeit
laden kann: keine Ausgabe, Exit-Code wie bei VC_EXIT_BASIS beschrieben.
"""

from __future__ import annotations

import importlib
import os
import platform
import re
import struct
import sys
import sysconfig
from importlib import metadata
from pathlib import Path

PROGRAMM_ORDNER = Path(__file__).resolve().parent.parent
REQUIREMENTS = PROGRAMM_ORDNER / "requirements.txt"
PAKETE = ("pymupdf", "spacy", "tkinterdnd2", "de_core_news_md")

# Visual-C++-Laufzeit: PyMuPDF (und spaCy) brauchen msvcp140.dll (C++-Standardbibliothek) und vcruntime140_1.dll
# (PyMuPDF daraus nur __CxxFrameHandler4). Python bringt vcruntime140.dll und vcruntime140_1.dll selbst mit (ab 3.8.1,
# im Ordner von python.exe), msvcp140.dll nicht: Die legt erst die „Visual C++ Redistributable“ in den Windows-
# Systemordner, conda bringt sie im eigenen Ordner mit. Geprüft wird deshalb, ob dieses Python die DLLs laden kann –
# nicht, ob sie im Systemordner liegen. Die EXE-Version hat beide im Ordner _internal.
VC_LAUFZEIT = "Microsoft Visual C++ 2015-2022 Redistributable (x64)"
VC_DLLS = ("msvcp140.dll", "vcruntime140_1.dll")
# Exit-Code von "pruefe_installation.py --vc-laufzeit" (Installieren.bat, EXE-bauen.bat): 10 + 1 (msvcp140.dll lässt
# sich nicht laden) + 2 (vcruntime140_1.dll lässt sich nicht laden). Die Basis 10 hält 1 (Python-Fehler) und 2 (Datei
# fehlt) frei: Die Batch-Dateien lesen jeden anderen Code als „nicht prüfbar“ und machen dann weiter.
VC_EXIT_BASIS = 10
VC_ABHILFE = (f"„{VC_LAUFZEIT}“ einmalig mit Administratorrechten installieren – "
              "winget install --id Microsoft.VCRedist.2015+.x64 -e oder vc_redist.x64.exe von Microsoft "
              "(https://aka.ms/vs/17/release/vc_redist.x64.exe) –, danach erneut prüfen")


def _version(paket: str) -> str | None:
    try:
        return metadata.version(paket)
    except metadata.PackageNotFoundError:
        return None


def _tupel(version: str) -> tuple[int, ...]:
    """'1.24.10' -> (1, 24, 10); Zusätze wie 'rc1' oder '.post1' zählen nicht."""
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3])


def versionsgrenzen(datei: Path = REQUIREMENTS) -> dict[str, tuple[str, tuple | None, tuple | None]]:
    """{paket: (Angabe, Untergrenze, Obergrenze)} aus requirements.txt – nur Zeilen wie 'name>=a,<b'.
    Für das per URL gebundene Sprachmodell gilt die Haupt-/Nebenversion aus dem Dateinamen."""
    grenzen: dict[str, tuple[str, tuple | None, tuple | None]] = {}
    try:
        zeilen = datei.read_text(encoding="utf-8").splitlines()
    except OSError:
        return grenzen
    for zeile in zeilen:
        zeile = zeile.split("#", 1)[0].strip()
        url = re.fullmatch(r"([\w.-]+)\s*@\s*\S+?-(\d+)\.(\d+)\.\d+-py3-none-any\.whl", zeile)
        if url:
            haupt, neben = int(url.group(2)), int(url.group(3))
            grenzen[url.group(1).lower()] = (f"{haupt}.{neben}.x", (haupt, neben), (haupt, neben + 1))
            continue
        m = re.fullmatch(r"([\w.-]+)\s*((?:(?:>=|<)\s*[\d.]+\s*,?\s*)+)", zeile)
        if not m:
            continue
        unten = oben = None
        for op, ver in re.findall(r"(>=|<)\s*([\d.]+)", m.group(2)):
            if op == ">=":
                unten = _tupel(ver)
            else:
                oben = _tupel(ver)
        grenzen[m.group(1).lower()] = (m.group(2).replace(" ", ""), unten, oben)
    return grenzen


def versions_probleme(versionen: dict[str, str | None], datei: Path = REQUIREMENTS) -> list[str]:
    """Pakete, deren installierte Version nicht zu requirements.txt passt (fehlende meldet pakete_bericht)."""
    probleme = []
    for paket, (angabe, unten, oben) in versionsgrenzen(datei).items():
        version = versionen.get(paket)
        if not version:
            continue
        t = _tupel(version)
        if (unten and t < unten) or (oben and t >= oben):
            probleme.append(f"Paket {paket} {version} passt nicht zu requirements.txt ({angabe}) – "
                            "Installieren.bat erneut ausführen.")
    return probleme


def _importierbar(modul: str) -> tuple[bool, str]:
    try:
        importlib.import_module(modul)
        return True, "ok"
    except Exception as e:  # noqa: BLE001 - jede Ursache soll im Bericht stehen
        return False, f"{type(e).__name__}: {e}"


def _dll_ladefehler(info: str) -> bool:
    """„DLL load failed“ (Erweiterungsmodul) bzw. WinError 126/127 (ctypes): eine DLL fehlt oder passt nicht –
    meist die Visual-C++-Laufzeit."""
    return "DLL load failed" in info or "WinError 126" in info or "WinError 127" in info


def _dll_laden(name: str) -> str:
    """Lädt eine DLL so, wie dieses Python die DLLs seiner Erweiterungsmodule sucht, und liefert den Pfad der geladenen
    Datei. ctypes nimmt für einen Namen ohne Pfad LOAD_LIBRARY_SEARCH_DEFAULT_DIRS – zuerst den Ordner von python.exe,
    dann System32 (für ein 64-Bit-Python das echte, auch aus einem 32-Bit-cmd heraus) und mit os.add_dll_directory
    eingetragene Ordner, nicht PATH; so findet auch PyMuPDF seine Laufzeit. OSError, wenn das nicht geht."""
    import ctypes
    dll = ctypes.WinDLL(name)
    try:
        modulname = ctypes.WinDLL("kernel32").GetModuleFileNameW
        modulname.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32)
        modulname.restype = ctypes.c_uint32
        puffer = ctypes.create_unicode_buffer(32768)
        if modulname(dll._handle, puffer, len(puffer)):
            return puffer.value
    except Exception:  # noqa: BLE001 - der Pfad ist nur eine Zusatzangabe; geladen ist die DLL
        pass
    return name


def vc_laufzeit(laden=None) -> dict[str, str | None]:
    """{DLL: Pfad, aus dem dieses Python sie lädt, oder None} für die DLLs der Visual-C++-Laufzeit, die PyMuPDF braucht.
    laden: Name -> Pfad, OSError, wenn die DLL nicht ladbar ist (Standard: _dll_laden, nur unter Windows)."""
    laden = laden or _dll_laden
    orte: dict[str, str | None] = {}
    for dll in VC_DLLS:
        try:
            orte[dll] = laden(dll) or dll
        except OSError:
            orte[dll] = None
    return orte


def vc_laufzeit_fehlt(laden=None) -> list[str]:
    """Die DLLs der Visual-C++-Laufzeit, die dieses Python nicht laden kann (leer = beide ladbar)."""
    return [dll for dll, ort in vc_laufzeit(laden).items() if ort is None]


def vc_laufzeit_exitcode(laden=None) -> int:
    """Exit-Code für die Batch-Dateien: VC_EXIT_BASIS + 1 (msvcp140.dll fehlt) + 2 (vcruntime140_1.dll fehlt).
    Außerhalb von Windows gibt es ohne eigenen Lader nichts zu prüfen."""
    if laden is None and sys.platform != "win32":
        return VC_EXIT_BASIS
    fehlt = vc_laufzeit_fehlt(laden)
    return VC_EXIT_BASIS + sum(1 << i for i, dll in enumerate(VC_DLLS) if dll in fehlt)


def laufzeit_bericht(windows: bool | None = None, laden=None) -> tuple[list[str], list[str]]:
    """Visual-C++-Laufzeit (nur unter Windows): Lässt sie sich nicht laden, scheitert jeder Import von PyMuPDF mit
    „DLL load failed“ – Pakete neu zu installieren hilft dann nicht. Die Zeile nennt, woher Python jede DLL lädt."""
    if not (sys.platform == "win32" if windows is None else windows):
        return [], []
    orte = vc_laufzeit(laden)
    teile = [f"{dll} aus {ort}" if ort else f"FEHLT {dll} (lässt sich nicht laden)" for dll, ort in orte.items()]
    zeilen = [f"Visual C++:    {', '.join(teile)}"]
    fehlt = [dll for dll, ort in orte.items() if ort is None]
    if not fehlt:
        return zeilen, []
    return zeilen, [f"Die Visual-C++-Laufzeit fehlt ({', '.join(fehlt)} lässt sich von diesem Python nicht laden) – "
                    f"ohne sie lässt sich PyMuPDF nicht laden („DLL load failed“). Abhilfe: {VC_ABHILFE}."]


# „DLL load failed“: Wer die DLLs eines Moduls bereitstellt, entscheidet über die Abhilfe. PyMuPDF und spaCy (C++)
# brauchen die Visual-C++-Laufzeit; tkinter gehört zu Python selbst (Tcl/Tk), tkinterdnd2 braucht tkinter.
# (Anzeigename, Paket, beim Neuinstallieren mit Abhängigkeiten – bei spaCy liegt die kaputte Datei oft in thinc,
# blis, cymem …)
_LAUFZEIT_MODULE = {"fitz": ("PyMuPDF", "pymupdf", False), "spacy": ("spaCy", "spacy", True)}
_STANDARD_GRENZEN = {"pymupdf": ">=1.24.10,<3", "spacy": ">=3.8,<3.9", "tkinterdnd2": ">=0.4"}


def _neu_installieren(paket: str, mit_abhaengigkeiten: bool = False) -> str:
    """pip-Befehl, der ein Paket ausdrücklich neu installiert: pip hält ein installiertes Paket sonst für vollständig,
    auch wenn ein Virenscanner Dateien entfernt hat. Die Grenzen kommen aus requirements.txt."""
    angabe = versionsgrenzen().get(paket, (_STANDARD_GRENZEN.get(paket, ""),))[0]
    ohne = "" if mit_abhaengigkeiten else "--no-deps "
    return f'"{sys.executable}" -m pip install --force-reinstall {ohne}--only-binary=:all: "{paket}{angabe}"'


def _aufzaehlung(module: list[str]) -> str:
    """'a', 'a' und 'b', 'a', 'b' und 'c'."""
    namen = [f"'{m}'" for m in module]
    return namen[0] if len(namen) == 1 else f"{', '.join(namen[:-1])} und {namen[-1]}"


def _dll_problem(module: list[str], fehlt: list[str] | None) -> str:
    """Eine Meldung für alle Module, die an einer DLL scheitern – mit Ursache und Abhilfe je Modul. fehlt: die
    Laufzeit-DLLs, die dieses Python nicht laden kann (vc_laufzeit_fehlt), oder None, wenn das nicht prüfbar ist
    (nicht unter Windows)."""
    verb = "lässt" if len(module) == 1 else "lassen"
    teile = [f"{_aufzaehlung(module)} {verb} sich nicht laden („DLL load failed“)."]
    laufzeit = [m for m in module if m not in ("tkinter", "tkinterdnd2")]
    # Scheitert auch tkinter, steht vor dem Teil zur Laufzeit, für welche Module er gilt
    wer = f"{_aufzaehlung(laufzeit)}: " if laufzeit and len(laufzeit) < len(module) else ""
    if laufzeit and fehlt:
        teile.append(f"{wer}Die Visual-C++-Laufzeit fehlt ({', '.join(fehlt)} lässt sich von diesem Python nicht "
                     f"laden). Abhilfe: {VC_ABHILFE}.")
    elif laufzeit and fehlt == []:
        teile.append(f"{wer}Die Visual-C++-Laufzeit lässt sich zwar laden, ist aber vermutlich veraltet. "
                     f"Abhilfe: {VC_ABHILFE}.")
        neu = [f"{_LAUFZEIT_MODULE[m][0]}: {_neu_installieren(*_LAUFZEIT_MODULE[m][1:])}"
               for m in laufzeit if m in _LAUFZEIT_MODULE]
        if neu:
            teile.append("Hilft das nicht, hat wohl ein Virenscanner Dateien entfernt (Quarantäne prüfen); dann neu "
                         f"installieren – {'; '.join(neu)}.")
    elif laufzeit:
        teile.append(f"{wer}Meist fehlt die Visual-C++-Laufzeit oder sie ist veraltet. Abhilfe: {VC_ABHILFE}.")
    if "tkinter" in module:
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        teile.append("tkinter gehört zu Python selbst (Tcl/Tk: _tkinter.pyd, tcl86t.dll und tk86t.dll im Ordner DLLs "
                     "der Python-Installation) – an der Visual-C++-Laufzeit liegt das meist nicht. Abhilfe: Python "
                     f"reparieren (Einstellungen → Apps → „Python {version}“ → Ändern → „Repair“) oder neu "
                     "installieren und dabei „tcl/tk and IDLE“ angehakt lassen"
                     + ("; 'tkinterdnd2' braucht tkinter und lädt danach wieder." if "tkinterdnd2" in module else "."))
    elif "tkinterdnd2" in module:
        teile.append(f"Abhilfe für tkinterdnd2: neu installieren – {_neu_installieren('tkinterdnd2')}.")
    return " ".join(teile)


def python_bericht() -> tuple[list[str], list[str]]:
    zeilen, probleme = [], []
    bits = struct.calcsize("P") * 8
    zeilen.append(f"Python:        {platform.python_version()} ({bits}-Bit) – {sys.executable}")
    zeilen.append(f"System:        {platform.system()} {platform.release()} {platform.version()}")
    zeilen.append(f"Prozessor:     {platform.machine()}  "
                  f"(PROCESSOR_ARCHITECTURE={os.environ.get('PROCESSOR_ARCHITECTURE', '-')}, "
                  f"PROCESSOR_ARCHITEW6432={os.environ.get('PROCESSOR_ARCHITEW6432', '-')})")
    if bits != 64:
        probleme.append("32-Bit-Python: für PyMuPDF/spaCy gibt es keine passenden Pakete – "
                        "bitte 64-Bit-Python (x64) installieren.")
    if sysconfig.get_platform().endswith("arm64"):
        if sys.version_info[:2] < (3, 11):
            probleme.append("ARM64-Python 3.10: dafür gibt es kein spaCy-Paket – "
                            "Python 3.11 oder neuer installieren (Installieren.bat nimmt 3.12).")
        zeilen.append("Hinweis:       ARM64 ist ungetestet; die Pakete gibt es für ARM64-Python 3.11 bis "
                      "3.15 (PyMuPDF dort 1.28.x).")
    elif platform.machine().upper().startswith("ARM"):
        zeilen.append("Hinweis:       ARM64-Prozessor mit x64-Python (Emulation unter Windows 11) – ungetestet.")
    if not (3, 10) <= sys.version_info[:2] < (3, 16):
        probleme.append(f"Python {platform.python_version()} wird nicht unterstützt (nötig: 3.10 bis 3.15).")
    pip = _version("pip")
    zeilen.append(f"pip:           {pip or 'FEHLT'}")
    if pip is None:
        probleme.append("pip fehlt – Python-Installation reparieren oder 'python -m ensurepip' ausführen.")
    return zeilen, probleme


def pakete_bericht() -> tuple[list[str], list[str]]:
    zeilen, probleme = [], []
    versionen = {}
    for paket in PAKETE:
        version = versionen[paket] = _version(paket)
        zeilen.append(f"{paket + ':':<20}{version or 'FEHLT'}")
        if version is None:
            probleme.append(f"Paket {paket} fehlt – Installieren.bat ausführen.")
    probleme += versions_probleme(versionen)
    import warnings
    warnings.simplefilter("ignore")
    dll_fehler = []
    for modul in ("fitz", "spacy", "tkinter", "tkinterdnd2"):
        ok, info = _importierbar(modul)
        zeilen.append(f"import {modul + ':':<13}{info}")
        if not ok and _dll_ladefehler(info):
            dll_fehler.append(modul)
        elif not ok:
            probleme.append(f"'{modul}' lässt sich nicht importieren ({info}).")
    if dll_fehler:
        probleme.append(_dll_problem(dll_fehler, vc_laufzeit_fehlt() if sys.platform == "win32" else None))
    try:
        import spacy
        spacy.load("de_core_news_md", disable=["lemmatizer", "tagger"])
        zeilen.append("Sprachmodell:  de_core_news_md lädt")
    except Exception as e:  # noqa: BLE001
        zeilen.append(f"Sprachmodell:  FEHLER {type(e).__name__}: {e}")
        probleme.append("Das Sprachmodell de_core_news_md lässt sich nicht laden – "
                        "ohne Modell gibt es keine Namenserkennung.")
    return zeilen, probleme


def tessdata_bericht() -> tuple[list[str], list[str]]:
    """Wo Sprachdateien liegen und – entscheidend – mit welcher Sprache aus welchem Ordner die OCR wirklich liest.
    Eine fremde Tesseract-Installation ($TESSDATA_PREFIX) zählt nur, wenn die mitgelieferte Datei fehlt."""
    zeilen, probleme = [], []
    prefix = os.environ.get("TESSDATA_PREFIX")   # vor _tessdata_finden(): das setzt die Variable auf seine Wahl
    meipass = getattr(sys, "_MEIPASS", None)
    kandidaten = [("Programmordner", PROGRAMM_ORDNER / "tessdata"),
                  ("TESSDATA_PREFIX", Path(prefix) if prefix else None),
                  ("PyInstaller", Path(meipass) / "tessdata" if meipass else None)]
    gefunden = False
    for name, ordner in kandidaten:
        if ordner is None:
            zeilen.append(f"tessdata ({name}): nicht gesetzt")
            continue
        deu = ordner / "deu.traineddata"
        status = f"deu.traineddata {deu.stat().st_size // 1024} KB" if deu.exists() else "ohne deu.traineddata"
        zeilen.append(f"tessdata ({name}): {ordner} – {status}")
        gefunden = gefunden or deu.exists()
    try:
        from anonymisierer.ocr import _ocr_sprache, _tessdata_finden
        benutzt = _tessdata_finden()
        sprache, warnung = _ocr_sprache(benutzt)
    except Exception as e:  # noqa: BLE001 - z. B. PyMuPDF lässt sich nicht laden (steht dann schon oben)
        zeilen.append(f"OCR liest mit:  nicht prüfbar ({type(e).__name__}: {e})")
        if not gefunden:
            probleme.append("Keine deutsche OCR-Sprachdatei gefunden – Scans würden nur auf Englisch gelesen. "
                            "Der Ordner tessdata mit deu.traineddata gehört in den Programmordner.")
        return zeilen, probleme
    zeilen.append(f"OCR liest mit:  {sprache or 'keiner Sprache'} aus {benutzt or '(kein Ordner)'}")
    if prefix and benutzt and Path(prefix) != Path(benutzt):
        mitgeliefert = {ordner for name, ordner in kandidaten if name != "TESSDATA_PREFIX" and ordner is not None}
        grund = ("die mitgelieferte deutsche Sprachdatei geht vor" if Path(benutzt) in mitgeliefert
                 else "dort liegt keine deu.traineddata")
        zeilen.append(f"Hinweis:       TESSDATA_PREFIX zeigt auf {prefix} (andere Tesseract-Installation?) – "
                      f"wird nicht benutzt, {grund}.")
    if sprache != "deu":
        probleme.append(warnung)
    return zeilen, probleme


def fehlerlog_bericht() -> list[str]:
    try:
        from anonymisierer.dateien import fehlerlog_pfad
        return [f"fehler.log:    {fehlerlog_pfad()}"]
    except Exception:  # noqa: BLE001 - ältere Stände ohne fehlerlog_pfad
        return [f"fehler.log:    neben dem Startskript ({PROGRAMM_ORDNER}) oder unter "
                f"%LOCALAPPDATA%\\PDF-Anonymisierer"]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--vc-laufzeit"]:
        # Nur die Laufzeit-Probe für Installieren.bat und EXE-bauen.bat: Exit-Code statt Bericht (VC_EXIT_BASIS)
        return vc_laufzeit_exitcode()
    if str(PROGRAMM_ORDNER) not in sys.path:
        sys.path.insert(0, str(PROGRAMM_ORDNER))
    try:
        from anonymisierer import __version__
    except Exception:  # noqa: BLE001
        __version__ = "unbekannt"
    print(f"PDF-Anonymisierer {__version__} – Installationsprüfung")
    print(f"Programmordner: {PROGRAMM_ORDNER}")
    print("-" * 72)
    probleme: list[str] = []
    for bericht in (python_bericht, laufzeit_bericht, pakete_bericht, tessdata_bericht):
        zeilen, neue = bericht()
        if zeilen:                       # laufzeit_bericht hat außerhalb von Windows nichts zu sagen
            print("\n".join(zeilen))
        probleme += neue
    print("\n".join(fehlerlog_bericht()))
    print("-" * 72)
    if probleme:
        print("PROBLEME:")
        for p in probleme:
            print(f"  - {p}")
        return 1
    print("Alles vorhanden – das Programm sollte laufen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
