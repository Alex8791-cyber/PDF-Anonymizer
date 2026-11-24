"""Tests für die Auslieferung: Batch-Dateien, requirements, tessdata, README, Lizenz, Werkzeuge.

Statische Prüfungen gegen die bekannten Stolperfallen aus dem Audit (M-08, M-26, M-27, M-37,
M-41 … M-46, M-60, M-62, M-70) und dem Auslieferungs-Review (AD-01 … AD-08). Es wird nichts
installiert und kein Windows gebraucht; die Python-Teile der Batch-Dateien (Vorab-Prüfungen)
werden aber wirklich ausgeführt.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
BATCHES = ("Installieren.bat", "EXE-bauen.bat", "Starten.bat")
MODELL_URL_MUSTER = r"^de_core_news_md @ (https://\S+/(de_core_news_md-(\d+)\.(\d+)\.\d+-py3-none-any\.whl))$"


def _lies(name: str) -> str:
    return (WURZEL / name).read_text(encoding="utf-8")


def _version() -> str:
    sys.path.insert(0, str(WURZEL))
    from anonymisierer import __version__
    return __version__


def _pins(name: str = "requirements.txt") -> dict[str, str]:
    """{paket: Angabe} der Bereichs-Pins einer requirements-Datei, z. B. {'pymupdf': '>=1.24.10,<3'}."""
    pins = {}
    for zeile in _lies(name).splitlines():
        zeile = zeile.split("#", 1)[0].strip()
        m = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*([<>=!~][^@]*)", zeile)
        if m:
            pins[m.group(1).lower()] = m.group(2).replace(" ", "")
    return pins


def _tupel_text(version: str) -> str:
    """'1.24.10' -> '(1,24,10)', '3' -> '(3,)' – so stehen die Grenzen in den Vorab-Prüfungen."""
    teile = version.split(".")
    return "(" + ",".join(teile) + ("," if len(teile) == 1 else "") + ")"


def _erwartete_bedingung(paket: str, angabe: str) -> str:
    """Bedingung, die eine Vorab-Prüfung für einen Pin wie '>=1.24.10,<3' enthalten muss."""
    unten = re.search(r">=([\d.]+)", angabe)
    oben = re.search(r"<([\d.]+)", angabe)
    assert unten, f"{paket}: Pin ohne Untergrenze ({angabe})"
    if oben:
        return f"{_tupel_text(unten.group(1))} <= t('{paket}') < {_tupel_text(oben.group(1))}"
    return f"t('{paket}') >= {_tupel_text(unten.group(1))}"


def _modell_url() -> re.Match:
    m = re.search(MODELL_URL_MUSTER, _lies("requirements.txt"), re.MULTILINE)
    assert m, "requirements.txt: Zeile 'de_core_news_md @ https://…whl' fehlt"
    return m


def _vorabpruefungen(name: str) -> dict[str, str]:
    """Python-Code der Vorab-Prüfungen einer Batch-Datei: {'laufzeit': …, 'pyinstaller': …}.
    Gesucht werden Zeilen '"%PY%" -W ignore -c "import …; …sys.exit(…)" >nul 2>&1'; cmd gibt den
    Text zwischen den Anführungszeichen unverändert an Python weiter."""
    pruefungen = {}
    for zeile in _lies(name).splitlines():
        m = re.fullmatch(r'"%PY%" -W ignore -c "(import (\w+)[^"]*sys\.exit\([^"]*)" >nul 2>&1', zeile.strip())
        if m:
            pruefungen["laufzeit" if m.group(2) == "fitz" else m.group(2).lower()] = m.group(1)
    return pruefungen


def _fuehre_vorabpruefung_aus(code: str, versionen: dict, monkeypatch) -> int:
    """Führt den Prüfcode mit vorgetäuschten Modulen/Versionen aus und liefert den Exit-Code
    (wie 'python -c': SystemExit-Code, bei einer Ausnahme 1). Version None = Paket fehlt."""
    for modul in ("fitz", "spacy", "tkinterdnd2", "de_core_news_md", "PyInstaller"):
        paket = {"fitz": "pymupdf", "PyInstaller": "pyinstaller"}.get(modul, modul)
        monkeypatch.setitem(sys.modules, modul, types.ModuleType(modul) if versionen.get(paket) else None)

    def version(paket):
        if versionen.get(paket.lower()) is None:
            raise importlib.metadata.PackageNotFoundError(paket)
        return versionen[paket.lower()]

    monkeypatch.setattr(importlib.metadata, "version", version)
    try:
        exec(compile(code, "<vorabpruefung>", "exec"), {})
    except SystemExit as e:
        return 0 if e.code is None else int(e.code)
    except Exception:  # noqa: BLE001 - Python beendet sich dann mit Exit-Code 1
        return 1
    return 0


# ----------------------------------------------------------------------
# Batch-Dateien: Zeichensatz, Zeilenenden, cmd-Fallen
# ----------------------------------------------------------------------

@pytest.mark.parametrize("name", BATCHES)
def test_batch_ist_ascii_und_crlf(name):
    roh = (WURZEL / name).read_bytes()
    roh.decode("ascii")  # keine Umlaute, kein BOM
    zeilen = roh.split(b"\n")
    assert zeilen[-1] == b"", f"{name}: letzte Zeile ohne Zeilenende"
    for nr, z in enumerate(zeilen[:-1], 1):
        assert z.endswith(b"\r"), f"{name}:{nr} hat kein CRLF"
    assert b"\r\r" not in roh, f"{name}: doppeltes CR"


@pytest.mark.parametrize("name", BATCHES)
def test_batch_grundgeruest(name):
    text = _lies(name)  # read_text normalisiert CRLF zu LF; CRLF prueft test_batch_ist_ascii_und_crlf
    assert text.startswith("@echo off\n")
    assert "chcp 65001" in text
    # kein "cd /d" mehr: es scheitert an UNC-Pfaden (test_batch_arbeitsordner_auch_auf_netzwerkfreigaben)
    befehle = [z.strip() for z in text.splitlines() if z.strip() and not z.strip().upper().startswith("REM")]
    assert not any(re.match(r"(cd|chdir)\b", z, re.IGNORECASE) for z in befehle)
    # "!" in Pfaden ueberlebt nur ohne verzoegerte Variablenerweiterung (M-26)
    assert "EnableDelayedExpansion" not in text


# ----------------------------------------------------------------------
# Kleiner cmd-Nachbau für Abschnitte der Batch-Dateien (cmd selbst gibt es hier nicht)
# ----------------------------------------------------------------------
CMD_BEFEHLE = (  # Stichwort in der Zeile -> Name im nachgebauten Ablauf (erstes passendes zählt)
    ("pushd ", "pushd"), ("popd", "popd"), ("where winget", "where_winget"), ("choice ", "choice"),
    ("winget install --id Microsoft.VCRedist", "winget_vc"), ("pruefe_installation.py --vc-laufzeit", "py_vc"),
)
_CMD_IF = re.compile(r'if\s+(/i\s+)?(not\s+)?(?:exist\s+("[^"]*"|\S+)|defined\s+(\w+)|errorlevel\s+(\d+)'
                     r'|("[^"]*")==("[^"]*"))\s+(.+)', re.IGNORECASE)


def _cmd(name: str, start: str, ende_labels: set[str], *, variablen: dict | None = None, dateien=(),
         ergebnisse: dict | None = None, effekte: dict | None = None, ende_zeile: str | None = None,
         ausgabe: list | None = None, variablen_aus: dict | None = None):
    """Spielt einen Abschnitt einer Batch-Datei ab der Zeile `start` durch: Labels, goto, call :label / goto :eof,
    set "X=…" mit %X%-Erweiterung (undefiniert = leer, je Zeile vor der Ausführung wie cmd), if [/i] [not]
    exist/defined/errorlevel N/"a"=="b" (auch verkettet), "befehl || anweisung" und exit /b N. Befehle aus
    CMD_BEFEHLE liefern den Errorlevel aus `ergebnisse` (Standard 0; eine Funktion bekommt die Dateien des
    nachgebauten Rechners und rechnet ihn daraus aus); `effekte` legt danach Dateien an (z. B. die DLLs nach winget).
    echo-Zeilen landen ohne Fluchtzeichen ^ in `ausgabe`, die Variablen am Ende in `variablen_aus` (falls übergeben).
    Unbekannte Befehle und Klammerblöcke sind ein Testfehler – der Nachbau soll nichts stillschweigend übergehen.
    Rückgabe: (ausgeführte Befehle, erreichtes Label | "weiter" an `ende_zeile` | "exit N")."""
    zeilen = [z.strip() for z in _lies(name).splitlines()]
    labels = {z[1:].lower(): i for i, z in enumerate(zeilen) if re.fullmatch(r":\w+", z)}
    werte = {k.upper(): v for k, v in (variablen or {}).items()}
    vorhanden = {d.lower() for d in dateien}
    ergebnisse, effekte = dict(ergebnisse or {}), dict(effekte or {})
    zustand = {"errorlevel": 0, "zeile": ""}
    ausgefuehrt, stapel = [], []

    def fertig(ergebnis):
        if variablen_aus is not None:
            variablen_aus.update(werte)
        return ausgefuehrt, ergebnis

    def befehl(text):
        art = next((a for stichwort, a in CMD_BEFEHLE if stichwort.lower() in zustand["zeile"].lower()), None)
        assert art, f"{name}: unbekannter Befehl im nachgebauten Ablauf: {text!r}"
        ausgefuehrt.append(art)
        wert = ergebnisse.get(art, 0)
        zustand["errorlevel"] = wert(frozenset(vorhanden)) if callable(wert) else wert
        vorhanden.update(d.lower() for d in effekte.get(art, ()))

    def anweisung(text):
        """Führt eine (schon erweiterte) Anweisung aus; Rückgabe None, ("goto", i), ("call", i), ("exit", N) oder
        "eof"."""
        text = text.strip()
        m = re.fullmatch(r"echo(?:[ .](.*))?", text, re.IGNORECASE)
        if m:
            if ausgabe is not None:
                ausgabe.append(re.sub(r"\^(.)", r"\1", m.group(1) or "").rstrip())
            return None
        if not text or re.match(r"(rem\b|pause$)", text, re.IGNORECASE):
            return None
        m = re.fullmatch(r"exit\s+/b(?:\s+(\d+))?", text, re.IGNORECASE)
        if m:
            return "exit", int(m.group(1) or 0)
        assert not text.endswith("("), f"{name}: Klammerblock im nachgebauten Ablauf: {text!r}"
        m = _CMD_IF.fullmatch(text)
        if m:
            if m.group(3):
                wahr = m.group(3).strip('"').lower() in vorhanden
            elif m.group(4):
                wahr = bool(werte.get(m.group(4).upper()))
            elif m.group(5):
                wahr = zustand["errorlevel"] >= int(m.group(5))
            else:
                a, b = m.group(6), m.group(7)
                wahr = a.lower() == b.lower() if m.group(1) else a == b
            return anweisung(m.group(8)) if wahr != bool(m.group(2)) else None
        if " || " in text:
            links, rechts = text.split(" || ", 1)
            befehl(links)
            return anweisung(rechts) if zustand["errorlevel"] else None
        m = re.fullmatch(r"goto\s+(:?\w+)", text, re.IGNORECASE)
        if m:
            return "eof" if m.group(1).lower() == ":eof" else ("goto", labels[m.group(1).lower()])
        m = re.fullmatch(r"call\s+:(\w+)", text, re.IGNORECASE)
        if m:
            return "call", labels[m.group(1).lower()]
        m = re.fullmatch(r'set\s+"(\w+)=(.*)"', text, re.IGNORECASE)
        if m:
            werte[m.group(1).upper()] = m.group(2)
            return None
        befehl(text)
        return None

    i = zeilen.index(start)
    for _ in range(2000):
        z = zeilen[i]
        if re.fullmatch(r":\w+", z) and z[1:].lower() in ende_labels:
            return fertig(z[1:].lower())
        if z == ende_zeile:
            return fertig("weiter")
        zustand["zeile"] = z
        if re.fullmatch(r":\w+", z):
            ziel = None
        else:   # %~dp0 (Ordner der Batch-Datei) hat kein schließendes %, Variablen schon
            ziel = anweisung(re.sub(r"%~dp0|%(\w+)%", lambda m: werte.get((m.group(1) or "~dp0").upper(), ""), z))
        if ziel is None:
            i += 1
        elif ziel == "eof":
            assert stapel, f"{name}: goto :eof außerhalb eines Unterprogramms beendet die Batch-Datei"
            i = stapel.pop()
        elif ziel[0] == "call":
            stapel.append(i + 1)
            i = ziel[1]
        elif ziel[0] == "exit":
            assert not stapel, f"{name}: exit /b in einem Unterprogramm ist im Nachbau nicht vorgesehen"
            return fertig(f"exit {ziel[1]}")
        else:
            i = ziel[1]
    raise AssertionError("Endlosschleife im nachgebauten Ablauf")


# ----------------------------------------------------------------------
# Netzwerkfreigaben (\\server\freigabe\…): cmd kann UNC nicht als aktuellen Ordner setzen
# ----------------------------------------------------------------------
def _bloecke_bis_exit(name: str):
    """[(Label des Abschnitts oder None, Zeilen bis einschließlich 'exit /b …')] einer Batch-Datei."""
    bloecke, label, zeilen = [], None, []
    for z in (z.strip() for z in _lies(name).splitlines()):
        if re.fullmatch(r":\w+", z):
            label, zeilen = z[1:].lower(), []
            continue
        zeilen.append(z)
        if z.lower().startswith("exit /b"):
            bloecke.append((label, zeilen))
            zeilen = []
    return bloecke


@pytest.mark.parametrize("name", ("Installieren.bat", "EXE-bauen.bat"))
def test_batch_arbeitsordner_auch_auf_netzwerkfreigaben(name):
    """Befund: 'cd /d "%~dp0"' scheitert auf einer per UNC-Pfad geöffneten Freigabe; danach prüften die relativen
    Pfade C:\\Windows und meldeten fälschlich „Dateien fehlen – ZIP komplett entpacken“. pushd ordnet der Freigabe
    einen freien Laufwerksbuchstaben zu; scheitert auch das, kommt eine eigene Meldung."""
    zeilen = [z.strip() for z in _lies(name).splitlines()]
    assert 'pushd "%~dp0" || goto fehler_ordner' in zeilen
    pushd = zeilen.index('pushd "%~dp0" || goto fehler_ordner')
    erste_relative = next(i for i, z in enumerate(zeilen) if z.startswith('if not exist "'))
    assert pushd < erste_relative, "der Arbeitsordner muss vor der ersten relativen Prüfung stehen"
    assert all(re.match(r"(@echo off|chcp |title |setlocal$|$)", z) for z in zeilen[:pushd])
    bloecke = _bloecke_bis_exit(name)
    assert bloecke and any(label == "fehler_ordner" for label, _ in bloecke)
    for label, block in bloecke:
        if label == "fehler_ordner":
            # pushd ist gescheitert: popd würde einen Eintrag des Aufrufers entfernen
            assert "popd" not in block and "pause" in block and block[-1] == "exit /b 1"
            text = "\n".join(block)
            for begriff in ("Netzwerkfreigabe", "Laufwerksbuchstaben", "%~dp0", "kopieren", "Netzlaufwerk"):
                assert begriff in text, f"{name}: :fehler_ordner erklärt '{begriff}' nicht"
            assert "ZIP" not in text, "die Meldung darf nicht zum Neu-Entpacken raten"
        else:
            # popd gibt den vorübergehenden Laufwerksbuchstaben wieder frei
            assert "popd" in block, f"{name}: Ausgang nach :{label} ohne popd"


@pytest.mark.parametrize("name, erste_pruefung", [
    ("Installieren.bat", 'if not exist "werkzeuge\\verknuepfung.py" goto fehler_unvollstaendig'),
    ("EXE-bauen.bat", 'if not exist "pdf_anonymisierer.py" goto fehler_unvollstaendig'),
])
@pytest.mark.parametrize("pushd, erwartet", [(0, "weiter"), (1, "fehler_ordner")])
def test_batch_arbeitsordner_ablauf(name, erste_pruefung, pushd, erwartet):
    befehle, ende = _cmd(name, 'pushd "%~dp0" || goto fehler_ordner', {"fehler_ordner", "fehler_unvollstaendig"},
                         variablen={"~dp0": "\\\\server\\freigabe\\PDF-Anonymisierer\\"}, ergebnisse={"pushd": pushd},
                         ende_zeile=erste_pruefung)
    assert (befehle, ende) == (["pushd"], erwartet)


def test_installieren_startet_das_programm_nicht_vom_voruebergehenden_laufwerk():
    """Der Laufwerksbuchstabe von pushd verschwindet mit popd. Das Programm wird deshalb erst danach gestartet –
    sonst stünde sein Arbeitsordner auf einem Laufwerk, das es nicht mehr gibt (neue OCR-Prozesse starten dort
    nicht mehr)."""
    zeilen = [z.strip() for z in _lies("Installieren.bat").splitlines()]
    autostart = next(i for i, z in enumerate(zeilen) if z.startswith('start "" "%PYW%"'))
    assert "popd" in zeilen[autostart - 3:autostart]
    assert '"%~dp0pdf_anonymisierer.py"' in zeilen[autostart]


def test_starten_bat_braucht_keinen_arbeitsordner():
    """Starten.bat liest .python_pfad.txt und startet das Programm über absolute Pfade (%~dp0) – auch von einer
    Netzwerkfreigabe, ohne vorübergehendes Laufwerk, das beim Beenden wieder verschwinden müsste."""
    zeilen = [z.strip() for z in _lies("Starten.bat").splitlines()]
    assert not any(re.match(r"(cd|chdir|pushd|popd)\b", z, re.IGNORECASE) for z in zeilen)
    code = [z for z in zeilen if z and not z.upper().startswith("REM")]
    for datei in (".python_pfad.txt", "pdf_anonymisierer.py"):
        stellen = [z for z in code if datei in z]
        assert stellen, datei
        for z in stellen:
            assert z.count(datei) == z.count("%~dp0" + datei), f"Starten.bat: {datei} relativ in {z!r}"


# ----------------------------------------------------------------------
# Visual-C++-Laufzeit: PyMuPDF braucht msvcp140.dll und vcruntime140_1.dll. Python bringt vcruntime140*.dll selbst
# mit, msvcp140.dll legt erst die „Visual C++ Redistributable“ in den Systemordner. Deshalb lädt das gefundene Python
# die DLLs zur Probe selbst (werkzeuge\pruefe_installation.py --vc-laufzeit) – mit der Suchreihenfolge von PyMuPDF.
# ----------------------------------------------------------------------
VC_WINGET = "winget install --id Microsoft.VCRedist.2015+.x64 -e"
VC_LINK = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
VC_NAME = "Microsoft Visual C++ 2015-2022 Redistributable (x64)"
SYS32, NATIV, WOW64 = "C:\\Windows\\System32\\", "C:\\Windows\\Sysnative\\", "C:\\Windows\\SysWOW64\\"
VC_DLLS = ("msvcp140.dll", "vcruntime140_1.dll")
PYDIR = "C:\\Users\\Nutzer\\AppData\\Local\\Programs\\Python\\Python312\\"
VC_AUFRUF = '"%PY%" werkzeuge\\pruefe_installation.py --vc-laufzeit >nul 2>&1'


def _vc(*namen, ordner=SYS32):
    return {ordner + n for n in namen}


# Dateien des nachgebauten Rechners aus Sicht des 64-Bit-Pythons (System32 = das echte, SysWOW64 = 32-Bit-DLLs).
# Jedes python.org-Python (x64) ab 3.8.1 bringt vcruntime140.dll und vcruntime140_1.dll im eigenen Ordner mit.
PYTHON_ORG = _vc("python.exe", "vcruntime140.dll", "vcruntime140_1.dll", ordner=PYDIR)
VC2017 = _vc("msvcp140.dll", "vcruntime140.dll")                    # VC++ 2015/2017: vcruntime140_1.dll erst ab 2019
VC2022 = _vc("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
CONDA = _vc("msvcp140.dll", ordner=PYDIR)                           # app-lokale Laufzeit neben python.exe


def _python_vc(vorhanden) -> int:
    """Errorlevel von VC_AUFRUF auf dem nachgebauten Rechner: die echte Prüfung (vc_laufzeit_exitcode) mit einem Lader,
    der wie Windows für ein 64-Bit-Python sucht (ctypes, Name ohne Pfad: LOAD_LIBRARY_SEARCH_DEFAULT_DIRS) – zuerst
    im Ordner von python.exe, dann im echten System32; nicht in SysWOW64 und nicht in PATH."""
    def laden(dll):
        for ordner in (PYDIR, SYS32):
            if (ordner + dll).lower() in vorhanden:
                return ordner + dll
        raise FileNotFoundError(2, f"Could not find module '{dll}' (or one of its dependencies)")
    return _pruefe_installation().vc_laufzeit_exitcode(laden)


def _block(name: str, label: str) -> str:
    text = _lies(name)
    block = text[text.index(f"\n:{label}\n"):]
    return block[:block.index("exit /b")]


def _ohne_rem(block: str) -> list[str]:
    return [z.strip() for z in block.splitlines() if z.strip() and not z.strip().upper().startswith("REM")]


def _unterprogramm(name: str, label: str) -> list[str]:
    """Befehlszeilen (ohne REM) eines Unterprogramms, vom Label bis vor das nächste Label."""
    text = _lies(name)
    block = text[text.index(f"\n:{label}\n") + len(label) + 2:]
    naechstes = re.search(r"^:\w+$", block, re.MULTILINE)
    return _ohne_rem(block[:naechstes.start()] if naechstes else block)


def test_installieren_prueft_vc_laufzeit_vor_den_paketen():
    """Befund: Ohne „Visual C++ Redistributable“ scheitert 'import fitz' mit „DLL load failed“ – die Vorab-Prüfung
    schlug deshalb bei jedem Lauf fehl, pip installierte alles neu, und Schritt 4 nannte eine falsche Ursache.
    Geänderte Erwartung (Gegenprüfung, Regression): Verlangt war, dass das Unterprogramm msvcp140.dll und
    vcruntime140_1.dll als Dateien in System32 bzw. Sysnative sucht. Das brach Rechner mit VC++ 2015/2017
    (vcruntime140_1.dll liegt dann nur neben python.exe) und mit app-lokaler Laufzeit (conda) ab. Jetzt lädt das
    gefundene Python die DLLs selbst – mit derselben Suchreihenfolge wie die Erweiterungsmodule von PyMuPDF."""
    text = _lies("Installieren.bat")
    pruefung = text.index("call :pruefe_vc_laufzeit")
    assert text.index("echo [2/5]") < pruefung < text.index("echo [3/5]")
    assert pruefung < text.index('"%PY%" -W ignore -c "import fitz, spacy'), "vor der Vorab-Prüfung der Pakete"
    unter = _unterprogramm("Installieren.bat", "pruefe_vc_laufzeit")
    assert unter[:2] == ['set "VC_FEHLT="', VC_AUFRUF], unter
    assert not any(re.search(r"exist|system32|sysnative|syswow64", z, re.IGNORECASE) for z in unter), unter
    assert VC_WINGET in text and "choice /c JN" in text
    meldung = _block("Installieren.bat", "fehler_vc_laufzeit")
    for begriff in (VC_NAME, VC_WINGET, "vc_redist.x64.exe", VC_LINK, "DLL load failed", "Administratorrechte",
                    "EXE-Version", "msvcp140.dll", "vcruntime140_1.dll", "erneut starten"):
        assert begriff in meldung, f":fehler_vc_laufzeit erklärt '{begriff}' nicht"
    # Schritt 4 nennt bei „DLL load failed“ die Laufzeit statt nur Virenscanner/zwei Pythons
    pruefung = _block("Installieren.bat", "fehler_pruefung")
    assert "DLL load failed" in pruefung and VC_WINGET in pruefung and VC_LINK in pruefung


NACH_WINGET = ["py_vc", "where_winget", "choice", "winget_vc", "py_vc"]


@pytest.mark.parametrize("arch, dateien, ergebnisse, effekte, erwartet_befehle, erwartet_ende", [
    # alles da: keine Rückfrage, weiter zu pip
    ("AMD64", PYTHON_ORG | VC2022, {}, {}, ["py_vc"], "vc_ok"),
    # Befund (Regression): nur VC++ 2015/2017 – vcruntime140_1.dll liegt allein neben python.exe, und dort sucht
    # Windows für Erweiterungsmodule zuerst. PyMuPDF lädt hier; die Installation läuft weiter.
    ("AMD64", PYTHON_ORG | VC2017, {}, {}, ["py_vc"], "vc_ok"),
    # app-lokale Laufzeit (conda): msvcp140.dll neben python.exe, im Systemordner nichts
    ("AMD64", PYTHON_ORG | CONDA, {}, {}, ["py_vc"], "vc_ok"),
    # msvcp140.dll fehlt (frischer Rechner, Windows-Sandbox) und kein winget: Meldung mit Abhilfe, kein Paket-Schritt
    ("AMD64", PYTHON_ORG, {"where_winget": 1}, {}, ["py_vc", "where_winget"], "fehler_vc_laufzeit"),
    # vcruntime140_1.dll nirgends (ein Python ohne die Datei) und nur VC++ 2017: die Laufzeit ab 2019 bringt sie mit
    ("AMD64", PYTHON_ORG - _vc("vcruntime140_1.dll", ordner=PYDIR) | VC2017, {"where_winget": 1}, {},
     ["py_vc", "where_winget"], "fehler_vc_laufzeit"),
    # winget da, Installation abgelehnt (N = Errorlevel 2), choice nicht bedienbar (255) oder mit Strg+C
    # unterbrochen, ohne die Batch-Datei abzubrechen (0): nichts installieren
    ("AMD64", PYTHON_ORG, {"choice": 2}, {}, ["py_vc", "where_winget", "choice"], "fehler_vc_laufzeit"),
    ("AMD64", PYTHON_ORG, {"choice": 255}, {}, ["py_vc", "where_winget", "choice"], "fehler_vc_laufzeit"),
    ("AMD64", PYTHON_ORG, {"choice": 0}, {}, ["py_vc", "where_winget", "choice"], "fehler_vc_laufzeit"),
    # angenommen: winget installiert die Laufzeit, die zweite Probe lädt sie, danach geht es weiter
    ("AMD64", PYTHON_ORG, {"choice": 1}, {"winget_vc": VC2022}, NACH_WINGET, "vc_ok"),
    # winget scheitert (z. B. keine Administratorrechte) oder meldet Erfolg, ohne dass Python die DLL laden kann:
    # Meldung, keine Schleife
    ("AMD64", PYTHON_ORG, {"choice": 1, "winget_vc": 1}, {}, NACH_WINGET, "fehler_vc_laufzeit"),
    ("AMD64", PYTHON_ORG, {"choice": 1}, {"winget_vc": _vc("vcruntime140_1.dll")}, NACH_WINGET, "fehler_vc_laufzeit"),
    # 32-Bit-cmd auf 64-Bit-Windows (Sysnative vorhanden): Es prüft das 64-Bit-Python, das das echte System32 sieht –
    # cmd selbst sieht keine DLL an. Nur die 32-Bit-Laufzeit (SysWOW64) reicht diesem Python nicht.
    ("AMD64", PYTHON_ORG | VC2022 | _vc("cmd.exe", ordner=NATIV), {}, {}, ["py_vc"], "vc_ok"),
    ("AMD64", PYTHON_ORG | _vc("cmd.exe", ordner=NATIV) | _vc("msvcp140.dll", "vcruntime140.dll", ordner=WOW64),
     {"where_winget": 1}, {}, ["py_vc", "where_winget"], "fehler_vc_laufzeit"),
    # ARM64 (ungetestet): nur ein Hinweis, die Installation läuft weiter
    ("ARM64", PYTHON_ORG, {}, {}, ["py_vc"], "vc_ok"),
])
def test_installieren_ablauf_vc_laufzeit(arch, dateien, ergebnisse, effekte, erwartet_befehle, erwartet_ende):
    """Geänderte Erwartung (Gegenprüfung, Regression): Ein Rechner mit msvcp140.dll im Systemordner, aber ohne
    vcruntime140_1.dll dort (VC++ 2015/2017), galt als „Laufzeit fehlt“ und wurde abgewiesen. Maßgeblich ist, was das
    gefundene Python laden kann – vcruntime140_1.dll bringt es selbst mit (Modell: _python_vc)."""
    befehle, ende = _cmd("Installieren.bat", "call :pruefe_vc_laufzeit", {"vc_ok", "fehler_vc_laufzeit"},
                         variablen={"SystemRoot": "C:\\Windows", "ARCH": arch, "PY": PYDIR + "python.exe"},
                         dateien=dateien, ergebnisse={"py_vc": _python_vc, **ergebnisse}, effekte=effekte)
    assert (befehle, ende) == (erwartet_befehle, erwartet_ende)


@pytest.mark.parametrize("ergebnisse, winget_da, versucht", [
    ({"where_winget": 1}, False, False),            # Befund: kein winget (Sandbox, LTSC, gesperrter App Installer)
    ({"choice": 2}, True, False),                   # winget da, Installation abgelehnt
    ({"choice": 1, "winget_vc": 1}, True, True),    # winget versucht und gescheitert (z. B. ohne Administratorrechte)
])
def test_installieren_vc_meldung_passt_zur_lage(ergebnisse, winget_da, versucht):
    """Befund: :fehler_vc_laufzeit nannte als erste Abhilfe den winget-Befehl – auch wenn das Skript dorthin kam, weil
    winget fehlt. Ohne winget steht jetzt vc_redist.x64.exe von Microsoft vorn, und winget kommt gar nicht vor; hat
    winget die Installation versucht, verweist die Meldung auf dessen Ausgabe."""
    ausgabe = []
    befehle, ende = _cmd("Installieren.bat", "call :pruefe_vc_laufzeit", {"vc_ok"},
                         variablen={"SystemRoot": "C:\\Windows", "ARCH": "AMD64", "PY": PYDIR + "python.exe"},
                         dateien=PYTHON_ORG, ergebnisse={"py_vc": _python_vc, **ergebnisse}, ausgabe=ausgabe)
    assert ende == "exit 1" and befehle[-1] == "popd", (befehle, ende)
    meldung = ausgabe[next(i for i, z in enumerate(ausgabe) if "FEHLER: Die Visual-C++-Laufzeit" in z):]
    abhilfen = [z.strip()[2:] for z in meldung if z.strip().startswith("- ")]
    assert any(VC_LINK in z for z in meldung) and any("msvcp140.dll" in z for z in meldung), meldung
    if winget_da:
        assert VC_WINGET in abhilfen[0] and "vc_redist.x64.exe" in abhilfen[1], abhilfen
    else:
        assert "vc_redist.x64.exe" in abhilfen[0], abhilfen
        assert not any("winget" in z for z in ausgabe), ausgabe
    assert any("Meldung von winget" in z for z in meldung) == versucht, meldung
    # die Merker starten leer – eine gleichnamige Umgebungsvariable verfälscht die Meldung nicht
    zeilen = [z.strip() for z in _lies("Installieren.bat").splitlines()]
    schritt1 = next(i for i, z in enumerate(zeilen) if z.startswith("echo [1/5]"))
    for merker in ("WINGET_DA", "VC_WINGET_VERSUCHT"):
        assert f'set "{merker}="' in zeilen[:schritt1], merker


def _vc_unterprogramm(name: str, errorlevel: int) -> dict:
    """Variablen nach ':pruefe_vc_laufzeit', wenn VC_AUFRUF den Errorlevel `errorlevel` liefert."""
    zeilen = [z.strip() for z in _lies(name).splitlines()]
    danach = zeilen[zeilen.index("call :pruefe_vc_laufzeit") + 1]
    variablen = {}
    befehle, ende = _cmd(name, "call :pruefe_vc_laufzeit", set(), variablen={"VC_FEHLT": "vom letzten Lauf"},
                         ergebnisse={"py_vc": errorlevel}, ende_zeile=danach, variablen_aus=variablen)
    assert (befehle, ende) == (["py_vc"], "weiter")
    return variablen


@pytest.mark.parametrize("name", ("Installieren.bat", "EXE-bauen.bat"))
@pytest.mark.parametrize("nicht_ladbar", [(), ("msvcp140.dll",), ("vcruntime140_1.dll",), VC_DLLS])
def test_vc_laufzeit_batch_versteht_den_exitcode(name, nicht_ladbar):
    """Prüfskript und Batch-Dateien verständigen sich über den Exit-Code von '--vc-laufzeit': VC_FEHLT nennt genau die
    DLLs, die Python nicht laden konnte."""
    def laden(dll):
        if dll in nicht_ladbar:
            raise FileNotFoundError(2, f"Could not find module '{dll}'")
        return SYS32 + dll
    errorlevel = _pruefe_installation().vc_laufzeit_exitcode(laden)
    assert _vc_unterprogramm(name, errorlevel).get("VC_FEHLT", "") == ", ".join(nicht_ladbar)


@pytest.mark.parametrize("name", ("Installieren.bat", "EXE-bauen.bat"))
@pytest.mark.parametrize("errorlevel", [0, 1, 2, 9, 14, 255, -1073741819])
def test_vc_laufzeit_nicht_pruefbar_haelt_nicht_auf(name, errorlevel):
    """Läuft die Probe nicht (Python-Fehler: 1, Datei fehlt: 2, Absturz: negativ, sonst Unbekanntes), bleibt VC_FEHLT
    leer: Die Installation läuft weiter wie ohne die Prüfung, statt einen Rechner abzuweisen, auf dem PyMuPDF lädt."""
    assert _vc_unterprogramm(name, errorlevel).get("VC_FEHLT", "") == ""


def test_installieren_vc_ok_fuehrt_zu_pip_und_paketen():
    """Nach der Laufzeit-Prüfung geht es mit pip weiter – nicht an der Prüfung vorbei und nicht doppelt."""
    zeilen = [z.strip() for z in _lies("Installieren.bat").splitlines()]
    vc_ok = zeilen.index(":vc_ok")
    assert zeilen[vc_ok + 1].startswith('"%PY%" -m pip --version')
    assert zeilen.index("call :pruefe_vc_laufzeit") < vc_ok < zeilen.index(next(z for z in zeilen
                                                                                if z.startswith("echo [3/5]")))


def test_exe_bauen_behaelt_die_vc_laufzeit_im_programmordner():
    """Die EXE braucht keine installierte Laufzeit: PyInstaller (6.x, depend/dylib.py: _win_includes) packt
    msvcp140.dll und vcruntime140_1.dll in _internal. EXE-bauen.bat prüft das nach dem Bau, damit es so bleibt."""
    text = _lies("EXE-bauen.bat")
    bau = text.index("-m PyInstaller")
    zip_schritt = text.index("Compress-Archive")
    for dll in VC_DLLS:
        pruefung = f'if not exist "dist\\PDF-Anonymisierer\\_internal\\{dll}" goto fehler_vc_im_ordner'
        assert pruefung in text and bau < text.index(pruefung) < zip_schritt
    # nichts vom Bau ausschließen außer den spaCy-Tests (kein --exclude für DLLs, kein --upx-exclude o. Ä.)
    assert re.findall(r"--\w*exclude\S*\s+\S+", text) == ["--exclude-module spacy.tests"]
    meldung = _block("EXE-bauen.bat", "fehler_vc_im_ordner")
    assert "msvcp140.dll" in meldung and VC_NAME in meldung
    lauf = _lies(".github/workflows/tests.yml")
    for dll in VC_DLLS:
        assert f'"_internal\\{dll}"' in lauf, f"EXE-Job prüft _internal\\{dll} nicht"


def test_exe_bauen_prueft_vc_laufzeit_vor_den_paketen():
    """Dieselbe Vorab-Prüfung der Pakete steht in EXE-bauen.bat: Ohne Laufzeit hätte auch dort jeder Bau vergeblich
    neu installiert. Geprüft wird mit demselben Unterprogramm wie in Installieren.bat (verglichen bis zum nächsten
    Label, nicht nur bis zum ersten 'goto :eof')."""
    text = _lies("EXE-bauen.bat")
    pruefung = text.index("call :pruefe_vc_laufzeit")
    assert text.index("goto fehler_32bit") < pruefung < text.index("echo [1/4]")
    assert pruefung < text.index('"%PY%" -W ignore -c "import fitz, spacy')
    assert (_unterprogramm("EXE-bauen.bat", "pruefe_vc_laufzeit")
            == _unterprogramm("Installieren.bat", "pruefe_vc_laufzeit"))
    meldung = _block("EXE-bauen.bat", "fehler_vc_laufzeit")
    for begriff in (VC_NAME, VC_WINGET, VC_LINK, "%VC_FEHLT%", "DLL load failed", "Installieren.bat",
                    "Administratorrechte"):
        assert begriff in meldung, f"EXE-bauen.bat, :fehler_vc_laufzeit: '{begriff}' fehlt"


@pytest.mark.parametrize("dateien, erwartet", [
    (PYTHON_ORG | VC2022, "weiter"),
    (PYTHON_ORG | VC2017, "weiter"),                                            # Befund (Regression): reicht
    (PYTHON_ORG | CONDA, "weiter"),                                             # app-lokale Laufzeit
    (PYTHON_ORG, "fehler_vc_laufzeit"),                                         # msvcp140.dll fehlt
    (PYTHON_ORG - _vc("vcruntime140_1.dll", ordner=PYDIR) | VC2017, "fehler_vc_laufzeit"),   # vcruntime140_1 nirgends
    (set(), "fehler_vc_laufzeit"),
    (PYTHON_ORG | VC2022 | _vc("cmd.exe", ordner=NATIV), "weiter"),             # 32-Bit-cmd: das 64-Bit-Python prüft
    (PYTHON_ORG | _vc("cmd.exe", ordner=NATIV) | _vc("msvcp140.dll", ordner=WOW64), "fehler_vc_laufzeit"),
])
def test_exe_bauen_ablauf_vc_laufzeit(dateien, erwartet):
    """Geänderte Erwartung wie bei test_installieren_ablauf_vc_laufzeit: „msvcp140.dll im Systemordner,
    vcruntime140_1.dll nur neben python.exe“ verweigerte den Bau, obwohl PyMuPDF auf diesem Rechner lädt."""
    zeilen = [z.strip() for z in _lies("EXE-bauen.bat").splitlines()]
    weiter = next(z for z in zeilen if z.startswith("echo [1/4]"))
    befehle, ende = _cmd("EXE-bauen.bat", "call :pruefe_vc_laufzeit", {"fehler_vc_laufzeit"},
                         variablen={"SystemRoot": "C:\\Windows", "PY": PYDIR + "python.exe"}, dateien=dateien,
                         ergebnisse={"py_vc": _python_vc}, ende_zeile=weiter)
    assert (befehle, ende) == (["py_vc"], erwartet)


def test_installieren_meldet_fehlende_verknuepfung_passend():
    """Befund: Die Meldung nannte pauschal PowerShell als Ursache – auch als nur .python_pfad.txt im
    schreibgeschützten Programmordner scheiterte (das bricht die Verknüpfung jetzt gar nicht mehr ab)."""
    meldung = _block("Installieren.bat", "fehler_verknuepfung")
    assert "steht oben" in meldung and "PowerShell" in meldung and "Desktop-Ordner" in meldung
    assert "Starten.bat" in meldung


@pytest.mark.parametrize("name", BATCHES)
def test_fortschrittszeilen_haben_echo(name):
    """M-42: '[5/5] …' ohne echo wurde als Befehl ausgefuehrt."""
    for nr, zeile in enumerate(_lies(name).splitlines(), 1):
        s = zeile.strip()
        assert not s.startswith("["), f"{name}:{nr} beginnt mit '[' ohne echo: {s!r}"
        if re.search(r"\[\d/\d\]", s):
            assert re.match(r"(echo|REM)\b", s, re.IGNORECASE), f"{name}:{nr}: {s!r}"


def test_installieren_schritte_und_pruefungen():
    text = _lies("Installieren.bat")
    for schritt in ("[1/5]", "[2/5]", "[3/5]", "[4/5]", "[5/5]"):
        assert re.search(rf"^echo \{schritt}", text, re.MULTILINE), f"{schritt} fehlt"
    # Pakete nur als fertige Wheels, aus requirements.txt (M-37, M-41)
    assert "--only-binary=:all:" in text
    assert "-r requirements.txt" in text
    # Fallback fuer das Modell
    assert "spacy download de_core_news_md" in text
    # Kein winget-Tesseract mehr (M-08), Sprachdatei kommt aus dem Repo
    assert "UB-Mannheim" not in text
    assert "tesseract" not in text.lower() or "winget install --id UB" not in text
    assert "tessdata\\deu.traineddata" in text
    # Python nach winget direkt suchen statt zweiter Lauf (M-45)
    assert r"%LOCALAPPDATA%\Programs\Python\Python" in text
    assert r"%ProgramFiles%\Python" in text
    assert "ERNEUT starten" not in text
    # Architektur / 32-Bit (M-41); ARM64-Python erst ab 3.11 (dafuer gibt es spaCy-Pakete, AD-08)
    assert "ARM" in text and "calcsize('P')" in text
    assert "(3,11 if arm else 10)<=sys.version_info[:2]<(3,16)" in text
    assert "ARM64 wird nicht unterstuetzt" not in text
    # Verknuepfung ueber Python, nicht ueber echo in eine .ps1 (M-26)
    assert "werkzeuge\\verknuepfung.py" in text
    assert ".ps1" not in text
    # Ursachen in Klartext (M-60)
    for stichwort in ("Proxy", "CERTIFICATE_VERIFY_FAILED", "github.com", "ARM64", "Schreibrechte", "Store-Alias"):
        assert stichwort in text, f"Ursachenhinweis '{stichwort}' fehlt"
    # "Fertig" genau einmal, Autostart nur im Erfolgszweig vor dem ersten Fehlerlabel
    assert text.count("Fertig!") == 1
    erfolg = text.index("Fertig!")
    autostart = text.index('start "" "%PYW%"')
    erstes_fehlerlabel = text.index(":fehler_")
    assert erfolg < autostart < erstes_fehlerlabel
    # Jeder Fehlerausgang endet mit pause + exit /b 1
    for block in re.findall(r"^:fehler_\w+\r?\n(.*?)^exit /b (\d)", text, re.MULTILINE | re.DOTALL):
        assert "pause" in block[0] and block[1] == "1"
    assert "Starten.bat" in text


def test_installieren_pins_passen_zu_requirements():
    """Der zweite Versuch in der Batch nennt genau die Bereichs-Pins aus requirements.txt."""
    pins = {f"{paket}{angabe}" for paket, angabe in _pins().items()}
    assert pins == {"pymupdf>=1.24.10,<3", "spacy>=3.8,<3.9", "tkinterdnd2>=0.4"}
    zeilen = [z for z in _lies("Installieren.bat").splitlines() if "pip install" in z and '"pymupdf' in z]
    assert zeilen, "Fallback-Zeile mit den einzelnen Pins fehlt in Installieren.bat"
    for zeile in zeilen:
        assert set(re.findall(r'"([a-z0-9_.-]+[<>=][^"]*)"', zeile)) == pins, zeile


# ----------------------------------------------------------------------
# AD-01/AD-03: Vorab-Prüfung statt erneutem 44-MB-Download, Grenzen wie in requirements
# ----------------------------------------------------------------------

def test_vorabpruefung_steht_vor_pip_und_ueberspringt_den_download():
    text = _lies("Installieren.bat").splitlines()
    vorab = next(i for i, z in enumerate(text) if z.startswith('"%PY%" -W ignore -c "import fitz, spacy'))
    pip_req = next(i for i, z in enumerate(text) if "pip install" in z and "-r requirements.txt" in z)
    assert vorab < pip_req, "Vorab-Prüfung muss vor dem pip-Lauf stehen"
    assert text[vorab].endswith(">nul 2>&1")
    block = "\n".join(text[vorab + 1:pip_req])
    assert text[vorab + 1].strip() == "if not errorlevel 1 ("
    assert "goto pakete_ok" in block and "kein Download" in block

    exe = _lies("EXE-bauen.bat").splitlines()
    for modul, datei in (("fitz", "requirements.txt"), ("PyInstaller", "requirements-dev.txt")):
        vorab = next(i for i, z in enumerate(exe) if z.startswith(f'"%PY%" -W ignore -c "import {modul}'))
        assert exe[vorab].endswith(">nul 2>&1")
        assert exe[vorab + 1].strip() == "if errorlevel 1 (", f"pip fuer {datei} muss von der Vorab-Pruefung abhaengen"
        assert f"-r {datei}" in exe[vorab + 3] and "pip install" in exe[vorab + 3]
    # Kein gemeinsamer Lauf mehr: Fehlt nur PyInstaller, darf requirements.txt (Modell-URL) nicht laufen
    assert not any("-r requirements.txt -r requirements-dev.txt" in z for z in exe)
    assert sum("pip install" in z for z in exe) == 2


@pytest.mark.parametrize("name", ("Installieren.bat", "EXE-bauen.bat"))
def test_vorabpruefung_grenzen_passen_zu_requirements(name):
    pruefungen = _vorabpruefungen(name)
    erwartet = {"laufzeit"} | ({"pyinstaller"} if name == "EXE-bauen.bat" else set())
    assert set(pruefungen) == erwartet, pruefungen
    code = pruefungen["laufzeit"]
    for paket, angabe in _pins().items():
        assert _erwartete_bedingung(paket, angabe) in code, f"{name}: Grenze für {paket} passt nicht zu {angabe}"
    url = _modell_url()
    haupt, neben = int(url.group(3)), int(url.group(4))
    assert f"({haupt},{neben}) <= t('de_core_news_md') < ({haupt},{neben + 1})" in code
    assert code.count("t('") == len(_pins()) + 1, "Vorab-Prüfung prüft ein Paket, das nicht in requirements.txt steht"
    if name == "EXE-bauen.bat":
        dev = _pins("requirements-dev.txt")
        assert _erwartete_bedingung("pyinstaller", dev["pyinstaller"]) in pruefungen["pyinstaller"]


def test_vorabpruefung_ist_in_beiden_batchdateien_gleich():
    assert _vorabpruefungen("Installieren.bat")["laufzeit"] == _vorabpruefungen("EXE-bauen.bat")["laufzeit"]


VERSIONEN_OK = {"pymupdf": "2.1", "spacy": "3.8.18", "tkinterdnd2": "0.7.0", "de_core_news_md": "3.8.0",
                "pyinstaller": "6.22.3"}


@pytest.mark.parametrize("aenderung, erwartet", [
    ({}, 0),
    ({"pymupdf": "1.24.10"}, 0),
    ({"pymupdf": "1.28.2"}, 0),                 # Python 3.10, 3.15 und ARM64 bekommen 1.28.x
    ({"pymupdf": "1.24.9"}, 1),                 # liest seitlich gedrehte Scans nicht
    ({"pymupdf": "1.24.2"}, 1),                 # ohne Page.remove_rotation()
    ({"pymupdf": "3.0.0"}, 1),
    ({"pymupdf": "2.1.0rc1"}, 0),
    ({"spacy": "3.7.5"}, 1),
    ({"spacy": "3.9.0"}, 1),
    ({"de_core_news_md": "3.7.0"}, 1),
    ({"tkinterdnd2": "0.3.9"}, 1),
    ({"de_core_news_md": None}, 1),             # Modell fehlt
    ({"pymupdf": None}, 1),                     # PyMuPDF fehlt
])
def test_vorabpruefung_entscheidet_richtig(aenderung, erwartet, monkeypatch):
    code = _vorabpruefungen("Installieren.bat")["laufzeit"]
    assert _fuehre_vorabpruefung_aus(code, {**VERSIONEN_OK, **aenderung}, monkeypatch) == erwartet


@pytest.mark.parametrize("version, erwartet", [("6.22.3", 0), ("6.10.0", 0), ("6.9.0", 1), ("7.0", 1), (None, 1)])
def test_vorabpruefung_pyinstaller(version, erwartet, monkeypatch):
    code = _vorabpruefungen("EXE-bauen.bat")["pyinstaller"]
    assert _fuehre_vorabpruefung_aus(code, {**VERSIONEN_OK, "pyinstaller": version}, monkeypatch) == erwartet


@pytest.mark.parametrize("name", ("Installieren.bat", "EXE-bauen.bat"))
def test_vorabpruefung_laeuft_im_echten_python(name):
    """Der Einzeiler ist gültiges Python und liefert in einer vollständigen Installation Exit-Code 0."""
    for art, code in _vorabpruefungen(name).items():
        module = re.match(r"import ([\w, ]+?)(?:, re, sys)?;", code).group(1).split(", ")
        fehlend = [m for m in module if importlib.util.find_spec(m) is None]
        if fehlend:
            pytest.skip(f"nicht installiert: {', '.join(fehlend)}")
        lauf = subprocess.run([sys.executable, "-W", "ignore", "-c", code], capture_output=True, text=True,
                              timeout=180, cwd=str(WURZEL))
        assert lauf.returncode == 0, f"{name} ({art}): {lauf.stderr[-2000:]}"


BEFEHLE = (  # Stichwort in der Befehlszeile -> Name im simulierten Ablauf (erstes passendes zählt)
    ("import PyInstaller", "vorab_pyinstaller"), ("import fitz, spacy", "vorab"), ("--no-index", "offline"),
    ("-r requirements-dev.txt", "pip_dev"), ("-r requirements.txt", "pip_req"),
    ("spacy download", "spacy_download"), ('"pymupdf', "pins"),
)


def _simuliere(name: str, start: str, ende_labels: set[str], ergebnisse: dict[str, int],
               datei_da: bool = False, ende_zeile: str | None = None):
    """Spielt den Ablauf einer Batch-Datei ab der Zeile `start` durch (goto, Labels, if errorlevel,
    if exist "%MODELL_WHL%", Klammerblöcke) – cmd selbst gibt es hier nicht. Befehle liefern den
    Errorlevel aus `ergebnisse`. Rückgabe: (ausgeführte Befehle, erreichtes Label bzw. "weiter")."""
    zeilen = [z.strip() for z in _lies(name).splitlines()]
    labels = {z[1:].lower(): i for i, z in enumerate(zeilen) if re.fullmatch(r":\w+", z)}
    i, errorlevel, ausgefuehrt = zeilen.index(start), 0, []
    for _ in range(500):
        z = zeilen[i]
        if re.fullmatch(r":\w+", z) and z[1:].lower() in ende_labels:
            return ausgefuehrt, z[1:].lower()
        if z == ende_zeile:
            return ausgefuehrt, "weiter"
        m = re.fullmatch(r"if (not )?(errorlevel 1|exist \"%MODELL_WHL%\") (goto (\w+)|\()", z)
        if m:
            wahr = (errorlevel >= 1) if m.group(2) == "errorlevel 1" else datei_da
            wahr = wahr != bool(m.group(1))
            if m.group(4):                                   # if … goto ziel
                i = labels[m.group(4).lower()] if wahr else i + 1
            elif wahr:                                       # if … ( Block betreten
                i += 1
            else:                                            # Block überspringen
                i = next(j for j in range(i + 1, len(zeilen)) if zeilen[j] == ")") + 1
            continue
        if z.startswith("goto "):
            i = labels[z[5:].strip().lower()]
            continue
        if z.startswith('"%PY%"'):
            art = next(a for stichwort, a in BEFEHLE if stichwort in z)
            ausgefuehrt.append(art)
            errorlevel = ergebnisse[art]
        else:
            assert re.match(r"(echo|REM\b|\)$|:\w+$|$)", z), f"{name}: unerwartete Zeile im Ablauf: {z!r}"
        i += 1
    raise AssertionError("Endlosschleife im simulierten Ablauf")


@pytest.mark.parametrize("ergebnisse, datei_da, erwartet_befehle, erwartet_ende", [
    ({"vorab": 0}, False, ["vorab"], "pakete_ok"),                                  # zweiter Lauf: kein pip
    ({"vorab": 0}, True, ["vorab"], "pakete_ok"),
    ({"vorab": 1, "pip_req": 0}, False, ["vorab", "pip_req"], "pakete_ok"),
    ({"vorab": 1, "pip_req": 1, "pins": 0, "spacy_download": 0}, False,
     ["vorab", "pip_req", "pins", "spacy_download"], "pakete_ok"),
    ({"vorab": 1, "pip_req": 1, "pins": 1}, False, ["vorab", "pip_req", "pins"], "fehler_pakete"),
    ({"vorab": 1, "pip_req": 1, "pins": 0, "spacy_download": 1}, False,
     ["vorab", "pip_req", "pins", "spacy_download"], "fehler_modell"),
    ({"vorab": 1, "pins": 0, "offline": 0}, True, ["vorab", "pins", "offline"], "pakete_ok"),  # ohne github.com
    ({"vorab": 1, "pins": 1}, True, ["vorab", "pins"], "fehler_pakete"),
    ({"vorab": 1, "pins": 0, "offline": 1}, True, ["vorab", "pins", "offline"], "fehler_modell"),
])
def test_installieren_ablauf_paketschritt(ergebnisse, datei_da, erwartet_befehle, erwartet_ende):
    start = next(z.strip() for z in _lies("Installieren.bat").splitlines() if z.startswith("echo [3/5]"))
    befehle, ende = _simuliere("Installieren.bat", start, {"pakete_ok", "fehler_pakete", "fehler_modell"},
                               ergebnisse, datei_da)
    assert (befehle, ende) == (erwartet_befehle, erwartet_ende)


@pytest.mark.parametrize("ergebnisse, erwartet_befehle, erwartet_ende", [
    ({"vorab": 0, "vorab_pyinstaller": 0}, ["vorab", "vorab_pyinstaller"], "weiter"),
    # erster Bau nach Installieren.bat: nur PyInstaller fehlt -> kein Lauf über requirements.txt (Modell-URL)
    ({"vorab": 0, "vorab_pyinstaller": 1, "pip_dev": 0}, ["vorab", "vorab_pyinstaller", "pip_dev"], "weiter"),
    ({"vorab": 1, "pip_req": 0, "vorab_pyinstaller": 0}, ["vorab", "pip_req", "vorab_pyinstaller"], "weiter"),
    ({"vorab": 1, "pip_req": 1}, ["vorab", "pip_req"], "fehler_pakete"),
    ({"vorab": 0, "vorab_pyinstaller": 1, "pip_dev": 1}, ["vorab", "vorab_pyinstaller", "pip_dev"], "fehler_pakete"),
])
def test_exe_bauen_ablauf_paketschritt(ergebnisse, erwartet_befehle, erwartet_ende):
    zeilen = [z.strip() for z in _lies("EXE-bauen.bat").splitlines()]
    start = next(z for z in zeilen if z.startswith("echo [1/4]"))
    weiter = next(z for z in zeilen if z.startswith("echo [2/4]"))
    befehle, ende = _simuliere("EXE-bauen.bat", start, {"fehler_pakete"}, ergebnisse, ende_zeile=weiter)
    assert (befehle, ende) == (erwartet_befehle, erwartet_ende)


def test_offline_weg_fuer_das_sprachmodell():
    text = _lies("Installieren.bat")
    url = _modell_url()
    assert f'set "MODELL_WHL={url.group(2)}"' in text, "Dateiname passt nicht zur Modell-URL in requirements.txt"
    assert 'if exist "%MODELL_WHL%"' in text
    assert text.index('if exist "%MODELL_WHL%"') < text.index("-r requirements.txt"), \
        "liegt die Datei bereit, darf pip nicht erst github.com versuchen"
    assert "--no-index --find-links . de_core_news_md" in text
    modell = text[text.index(":fehler_modell"):]
    modell = modell[:modell.index("exit /b 1")]
    for begriff in ("%MODELL_WHL%", "requirements.txt", "Offline", "Hotspot", "github.com"):
        assert begriff in modell, f":fehler_modell erklaert den Offline-Weg nicht ({begriff})"
    # Ehrliche Texte: auch "spacy download" laedt von github.com
    assert "falls nur der GitHub-Download blockiert war" not in text
    assert re.search(r'"spacy download"[^\n]*\n[^\n]*github\.com', text)


def test_starten_bat():
    text = _lies("Starten.bat")
    assert ".python_pfad.txt" in text
    assert "pdf_anonymisierer.py" in text
    assert "pythonw" in text
    assert "Installieren.bat" in text  # Hinweis, falls Python fehlt


def test_exe_bauen_flags():
    text = _lies("EXE-bauen.bat")
    assert "--onedir" in text and "--onefile" not in text        # M-46
    assert "--noconfirm" in text and "--clean" in text            # M-44
    assert '--add-data "tessdata;tessdata"' in text               # M-08, Windows-Trenner ;
    assert "--collect-all de_core_news_md" in text
    assert '--add-data "anonymisierer\\daten;anonymisierer\\daten"' in text   # Wissensbasis (Wortlisten)
    assert "--collect-submodules anonymisierer.detektoren" in text           # Detektoren werden dynamisch geladen
    assert "--collect-all tkinterdnd2" not in text                # Hooks vorhanden (M-44)
    assert "--exclude-module spacy.tests" in text
    assert "--version-file werkzeuge\\version_info.txt" in text   # M-27
    assert "--icon" in text and "icon.ico" in text
    assert "import de_core_news_md" in text                       # Modellpruefung vor dem Bau (M-37)
    assert "spacy download" not in text                           # kein stiller Download mehr
    assert "Compress-Archive" in text
    assert "SmartScreen" in text and "signtool" in text
    assert "KEIN Tesseract" in text
    assert "--only-binary=:all:" in text
    assert "AGPL" in text
    assert "_internal\\tessdata\\deu.traineddata" in text


LIZENZ_KOPIEN = {  # Quelle im Repository -> Ziel im Programmordner der EXE (und damit in der ZIP)
    "LICENSE": "LICENSE.txt",
    "THIRD_PARTY_NOTICES.md": "THIRD_PARTY_NOTICES.md",
    "README.md": "README.md",
    "licenses\\AGPL-3.0.txt": "licenses\\AGPL-3.0.txt",
}


def test_exe_bauen_legt_lizenztexte_in_die_zip():
    """AD-02: LICENSE, THIRD_PARTY_NOTICES.md, AGPL-Text und README landen im dist-Ordner – vor dem Packen."""
    text = _lies("EXE-bauen.bat")
    zip_schritt = text.index("Compress-Archive")
    bau = text.index("-m PyInstaller")
    for quelle, ziel in LIZENZ_KOPIEN.items():
        kopie = f'copy /y "{quelle}" "dist\\PDF-Anonymisierer\\{ziel}" >nul'
        assert kopie in text, f"Kopierschritt fehlt: {kopie}"
        assert bau < text.index(kopie) < zip_schritt, f"{quelle} muss nach dem Bau und vor dem ZIP kopiert werden"
        pruefung = f'if not exist "dist\\PDF-Anonymisierer\\{ziel}" goto fehler_lizenz'
        assert pruefung in text and text.index(pruefung) < zip_schritt
        assert f'if not exist "{quelle}" goto fehler_unvollstaendig' in text, f"{quelle}: Prüfung vor dem Bau fehlt"
    assert 'mkdir "dist\\PDF-Anonymisierer\\licenses"' in text
    # Jeder Fehlerausgang endet mit pause + exit /b 1
    bloecke = re.findall(r"^:fehler_\w+\n(.*?)^exit /b (\d)", text, re.MULTILINE | re.DOTALL)
    assert len(bloecke) == text.count("\n:fehler_") >= 8
    for block, code in bloecke:
        assert "pause" in block and code == "1"
    # Schlusstext verspricht nur, was im Ordner liegt
    assert "liegt in diesem Ordner" not in text
    assert "licenses\\AGPL-3.0.txt" in text[text.index("Fertig:"):]


def test_agpl_lizenztext_liegt_bei():
    """Voller AGPL-3.0-Text (das PyMuPDF-Wheel enthält nur einen Einzeiler) – unverändert aus dem
    PyMuPDF-Quellpaket (pymupdf-2.1.tar.gz, Datei COPYING), identisch mit COPYING von MuPDF."""
    roh = (WURZEL / "licenses" / "AGPL-3.0.txt").read_bytes()
    assert hashlib.sha256(roh).hexdigest() == "57c8ff33c9c0cfc3ef00e650a1cc910d7ee479a8bc509f6c9209a7c2a11399d6"
    text = roh.decode("ascii")
    assert text.lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")
    for stelle in ("Version 3, 19 November 2007", "13. Remote Network Interaction", "END OF TERMS AND CONDITIONS"):
        assert stelle in text


# ----------------------------------------------------------------------
# requirements, tessdata, Versionsinfo
# ----------------------------------------------------------------------

def test_requirements_pins():
    text = _lies("requirements.txt")
    # 1.24.10: remove_rotation (1.24.3), bake/apply_redactions(text=) (1.24.2), OCR seitlicher Scans (1.24.10)
    assert re.search(r"^pymupdf>=1\.24\.10,<3$", text, re.MULTILINE)
    assert re.search(r"^spacy>=3\.8,<3\.9$", text, re.MULTILINE)
    assert re.search(r"^tkinterdnd2>=0\.4$", text, re.MULTILINE)
    assert ("de_core_news_md @ https://github.com/explosion/spacy-models/releases/download/"
            "de_core_news_md-3.8.0/de_core_news_md-3.8.0-py3-none-any.whl") in text
    dev = _lies("requirements-dev.txt")
    assert "pytest" in dev and "pyinstaller" in dev


def test_tessdata_liegt_bei():
    deu = WURZEL / "tessdata" / "deu.traineddata"
    assert deu.exists(), "tessdata/deu.traineddata fehlt (M-08)"
    assert deu.stat().st_size >= 1_000_000


def test_versionsinfo_passt_zur_version():
    version = _version()
    text = (WURZEL / "werkzeuge" / "version_info.txt").read_text(encoding="utf-8")
    teile = tuple(int(x) for x in version.split(".")[:3]) + (0,)
    assert f"filevers={teile}".replace(" ", "") in text.replace(" ", "")
    assert f"'FileVersion', '{version}'" in text
    assert f"'ProductVersion', '{version}'" in text
    assert "'PDF-Anonymisierer'" in text

    class Stub:
        def __init__(self, *a, **k):
            self.a, self.k = a, k
    namen = ("VSVersionInfo", "FixedFileInfo", "StringFileInfo", "StringTable",
             "StringStruct", "VarFileInfo", "VarStruct")
    info = eval(text, {n: Stub for n in namen})  # so liest PyInstaller die Datei auch
    assert info.k["ffi"].k["filevers"] == teile


def test_changelog_nennt_version():
    assert f"[{_version()}]" in _lies("CHANGELOG.md")


# ----------------------------------------------------------------------
# README, Lizenz, Drittkomponenten, GitHub-Action
# ----------------------------------------------------------------------

def test_readme_markdown_struktur():
    text = _lies("README.md")
    assert text.startswith("# PDF-Anonymisierer")
    assert len(re.findall(r"^## ", text, re.MULTILINE)) >= 8
    tabellen = re.findall(r"^\|.*\|\r?\n^\|[-| ]+\|$", text, re.MULTILINE)
    assert len(tabellen) >= 2, "Erkennungstabelle und Problemloesungstabelle erwartet"
    md = pytest.importorskip("markdown_it")
    tokens = md.MarkdownIt("gfm-like", {"linkify": False}).parse(text)  # linkify braucht ein Zusatzpaket
    typen = {t.type for t in tokens}
    assert "heading_open" in typen and "table_open" in typen and "bullet_list_open" in typen


def test_readme_inhalt():
    text = _lies("README.md")
    assert "gefahrlos" not in text.lower()
    assert "Pseudonymisierung" in text
    for begriff in ("anonym_01.pdf", "_zuordnung.txt", "_PRUEFEN", "fehler.log",
                    "%LOCALAPPDATA%\\PDF-Anonymisierer", "PDF-Anonymizer-main",
                    "Sicherheitswarnung", "SmartScreen", "Trotzdem ausführen",
                    "Was NICHT erkannt wird", "Diagnosen", "Unterschriften", "Handschrift",
                    "64-Bit", "ARM64", "EXE-bauen.bat", "Starten.bat", "AGPL-3.0", "Apache-2.0",
                    "MIT", "THIRD_PARTY_NOTICES.md", "pruefe_installation.py"):
        assert begriff in text, f"README erwaehnt '{begriff}' nicht"
    assert "winget install UB-Mannheim" not in text


def test_readme_tabelle_deckt_kategorien_ab():
    """Jeder Platzhalter aus KATEGORIEN steht in der README-Tabelle (sonst: readme_tabelle.py --schreiben)."""
    sys.path.insert(0, str(WURZEL))
    from anonymisierer.muster import KATEGORIEN
    from werkzeuge.readme_tabelle import ANFANG, ENDE, tabelle
    text = _lies("README.md")
    a, e = text.index(ANFANG), text.index(ENDE)
    block = text[a:e]
    for schluessel, anzeige, platzhalter, _f, _an in KATEGORIEN:
        assert anzeige in block, f"Kategorie '{anzeige}' fehlt in der README-Tabelle"
        if platzhalter:
            assert f"`{platzhalter}`" in block, f"Platzhalter {platzhalter} fehlt in der README-Tabelle"
    erzeugt = tabelle()
    assert erzeugt.startswith("| Kategorie |") and erzeugt.count("\n") == len(KATEGORIEN) + 1


def test_readme_tabelle_entspricht_dem_werkzeug():
    """Die Erkennungstabelle der README ist genau die Ausgabe von werkzeuge/readme_tabelle.py: Schutzstufen
    („Angehakt ab Stufe“ aus muster.PROFILE), Beispiele und Hinweise laufen nicht auseinander."""
    sys.path.insert(0, str(WURZEL))
    from werkzeuge.readme_tabelle import ANFANG, ENDE, tabelle
    text = _lies("README.md")
    block = text[text.index(ANFANG) + len(ANFANG):text.index(ENDE)]
    assert block.strip() == tabelle(), "README-Tabelle veraltet: python werkzeuge/readme_tabelle.py --schreiben"


def test_readme_tabelle_stufen_und_beispiele():
    """Jedes Beispiel der README-Tabelle findet die Erkennung seiner Kategorie – die README verspricht nichts, was das
    Programm nicht erkennt (Personennamen erkennt das Sprachmodell: tests/test_namen.py). „Angehakt ab Stufe“ nennt
    die mildeste Stufe; hakt keine Stufe die Kategorie an, heißt es „nur von Hand“."""
    sys.path.insert(0, str(WURZEL))
    from anonymisierer import muster
    from werkzeuge.readme_tabelle import BEISPIELE, NUR_VON_HAND, angehakt_ab
    funktionen = {k: f for k, _a, _p, f, _an in muster.KATEGORIEN if f is not None}
    assert set(BEISPIELE) <= {k for k, *_ in muster.KATEGORIEN}
    for schluessel, beispiel in BEISPIELE.items():
        if schluessel not in funktionen:
            continue
        gefunden = list(funktionen[schluessel](beispiel))
        gefunden += [beispiel[s.start:s.ende] for s in muster.stellen(schluessel, beispiel)]
        assert gefunden, f"README-Beispiel der Kategorie {schluessel} wird nicht erkannt: {beispiel!r}"
    profile = {"ausgewogen": {"aktive": {"a", "c"}}, "hoch": {"aktive": {"a", "b"}}, "maximal": {"aktive": {"a", "b"}}}
    assert [angehakt_ab(k, profile) for k in "abcd"] == ["Ausgewogen", "Hoch", "nur Ausgewogen", NUR_VON_HAND]
    assert angehakt_ab("datum") == NUR_VON_HAND             # „ALLE Datumsangaben“ hakt keine Stufe an


def test_readme_fakten_aus_dem_auslieferungs_review():
    text = _lies("README.md")
    # AD-01: zweiter Lauf ohne Download, Offline-Weg für das Sprachmodell
    assert _modell_url().group(2) in text and "Offline" in text
    assert "ca. 300 MB" not in text
    # AD-02: Lizenztexte liegen der EXE-ZIP bei
    for datei in ("LICENSE.txt", "THIRD_PARTY_NOTICES.md", "licenses\\AGPL-3.0.txt"):
        assert datei in text, f"README nennt {datei} in der EXE-Version nicht"
    # AD-03: welche PyMuPDF-Reihe welches Python bekommt
    assert "1.28" in text and "1.24.10" in text
    # AD-04: Versicherten-, Fahrzeug-, Ausweisnummern werden erkannt (Kategorien kvnr/fin/ausweis)
    assert "werden nicht gesondert erkannt" not in text
    assert "nur hinter einem Etikett" in text
    # AD-06: die EXE schreibt fehler.log nie neben sich; Rückfrage-Werkzeug nur in der Skript-Version
    assert "(bzw. neben der EXE)" not in text
    assert "_internal\\tessdata" in text
    # AD-08: ARM64 ist ungetestet, nicht pauschal "nicht unterstützt"
    assert "ungetestet" in text
    assert not re.search(r"ARM64[^.]*werden\s+nicht\s+unterstützt", text)


# ----------------------------------------------------------------------
# Durchsicht der Doku: Aussagen von README, CHANGELOG und Modulköpfen am Code geprüft
# ----------------------------------------------------------------------
def _flach(text: str) -> str:
    """Text mit zusammengezogenem Leerraum (Zeilenumbrüche der Markdown-Absätze zählen nicht)."""
    return " ".join(text.split())


def _listenpunkt(text: str, anfang: str) -> str:
    """Der Listenpunkt (auch ein nummerierter Schritt), der mit `anfang` beginnt: seine erste Zeile und alle
    eingerückten Folgezeilen, Leerraum zusammengezogen."""
    zeilen = text[text.index(anfang):].splitlines()
    punkt = [zeilen[0]]
    for zeile in zeilen[1:]:
        if not zeile.startswith(" ") or not zeile.strip():
            break
        punkt.append(zeile)
    return _flach("\n".join(punkt))


def _abschnitt(text: str, ueberschrift: str) -> str:
    """Abschnitt von der Überschrift bis zur nächsten Überschrift desselben Rangs, Leerraum zusammengezogen."""
    start = text.index(ueberschrift + "\n")
    ende = text.find("\n" + ueberschrift.split(" ", 1)[0] + " ", start + len(ueberschrift))
    return _flach(text[start:ende if ende >= 0 else len(text)])


def _konstante(datei: str, name: str):
    """Wert einer Konstante auf Modulebene (ohne Import – die Oberfläche bräuchte tkinter)."""
    for knoten in ast.parse(_lies(datei)).body:
        if isinstance(knoten, ast.Assign) and [getattr(z, "id", None) for z in knoten.targets] == [name]:
            return ast.literal_eval(knoten.value)
    raise AssertionError(f"{name} fehlt in {datei}")


def test_doku_anschrift_im_eigenen_briefkopf():
    """Durchsicht Befund 1: Die README versprach „Die Anschrift einer Person im eigenen Briefkopf (z. B. Selbständige)
    wird geschwärzt“. Wirkt der Briefkopf wie der einer Firma (Webadresse, Bankverbindung, USt-IdNr.), schwärzt das
    Programm sie aber nur mit einem Namen davor, den die Wortlisten als Vor- oder Nachnamen kennen
    (analyse._person_vorn); sonst steht sie nicht angehakt als „vermutlich Firmenanschrift“ in der Liste (Verhalten:
    test_robustheit_analyse.py::test_briefkopf_wie_eine_firma_nur_mit_bekanntem_namen_geschwaerzt). README und
    CHANGELOG sagen das gleich."""
    readme = _lies("README.md")
    assert "Die Anschrift einer Person im eigenen Briefkopf (z. B. Selbständige) wird geschwärzt" not in _flach(readme)
    for text, anfang in ((readme, "- **Firmenanschriften**"), (_lies("CHANGELOG.md"), "- **Mehr wird geschwärzt")):
        punkt = _listenpunkt(text, anfang)
        for begriff in ("Webadresse", "Bankverbindung", "Vor- oder Nachnamen", "vermutlich Firmenanschrift",
                        "Selbständigen", "prüfen und anhaken"):
            assert begriff in punkt, (anfang, begriff)


def test_doku_restrisiko_meldet_ganz_abgewaehlte_funde():
    """Durchsicht Befund 2: CHANGELOG und der Docstring von analyse._firmenanschriften sagten, die Restrisiko-Prüfung
    melde nicht, was in der Fundliste abgewählt ist (z. B. „vermutlich Firmenanschrift“). Die Oberfläche gibt einen
    ganz abgewählten Text-Fund aber gar nicht an die Schwärzung (auftrag.auftrag_funde): sieht er nach Personendaten
    aus, bleibt er meist Verdacht – gewollt, bei Selbständigen der Hinweis auf eine lesbare Privatanschrift (Verhalten:
    test_robustheit_analyse.py::test_ganz_abgewaehlter_fund_bleibt_verdacht_abgewaehlte_einzelstelle_nicht). Nur
    abgewählte Stellen eines angehakten Funds meldet sie nicht."""
    changelog = _lies("CHANGELOG.md")
    assert "Was in der Fundliste abgewählt ist" not in _flach(changelog)
    punkt = _listenpunkt(changelog, "- **Restrisiko-Prüfung:**")
    for begriff in ("abgewählte Stellen eines angehakten Funds", "ganz abgewählten Fund", "gar nicht an die Schwärzung",
                    "weiter als Verdacht"):
        assert begriff in punkt, begriff
    funktion = next(k for k in ast.parse(_lies("anonymisierer/analyse.py")).body
                    if isinstance(k, ast.FunctionDef) and k.name == "_firmenanschriften")
    doc = _flach(ast.get_docstring(funktion))
    assert "meldet abgewählte Stellen nicht als Verdacht" not in doc
    assert "auftrag.auftrag_funde" in doc and "Nur abgewählte Stellen eines angehakten Funds" in doc
    # Die Regel, auf die sich beide Texte stützen: ein ganz abgewählter Text-Fund bleibt aus dem Auftrag weg
    sys.path.insert(0, str(WURZEL))
    from anonymisierer import auftrag
    fund = {"kategorie": "strasse", "text": "Hauptstraße 12",
            "stellen": [{"seite": 0, "start": 0, "ende": 14, "an": False}]}
    assert auftrag.auftrag_funde([fund], ["aus"], True) == ([], [])


def test_doku_seitenrahmen_auch_bei_hellen_scans():
    """Durchsicht Befund 3: „bei sehr hellen Scans fehlt der Seitenrahmen“ stimmt seit Runde 3b nicht mehr – ein heller
    Scan, auf dem die OCR nichts liest, ist ein Seitenverdacht und wird ganz umrahmt (restrisiko._seite_nachweislich_
    leer, test_restrisiko.py::test_hell_gedruckte_ungelesene_scan_seite_ist_seitenverdacht). Ohne Rahmen bleibt z. B.
    eine Seite mit viel Handschrift, auf der die OCR nur ein paar gedruckte Wörter liest (Grund „Scan kaum lesbar“,
    test_restrisiko.py::test_kaum_lesbare_seite_mit_einigen_woertern_ohne_seitenrahmen) – das Beispiel an beiden
    Stellen der README, mit dem Grund, wie ihn die Schwärzung nennt."""
    readme = _lies("README.md")
    for alt in ("zum Beispiel nicht bei sehr hellen Scans",
                "Der Rahmen kann aber fehlen (z. B. bei sehr hellen Scans)"):
        assert alt not in _flach(readme), alt
    grund = _konstante("anonymisierer/schwaerzung.py", "_GRUND_TEXTE")["KAUM_LESBAR"]
    for ueberschrift in ("## Was NICHT erkannt wird", "## Prüfen und freigeben"):
        teil = _abschnitt(readme, ueberschrift)
        assert f"„{grund}“" in teil and "viel Handschrift" in teil, ueberschrift


def test_doku_kompaktstufen_wie_in_der_oberflaeche():
    """Durchsicht Befund 4: README und CHANGELOG beschrieben die alten Kompaktstufen (zuerst „Hinweiskasten
    einzeilig“). Die Oberfläche (gui.KOMPAKT_STUFEN) setzt erst Titel und Ablagefläche in eine Zeile (nur, wenn beide
    nebeneinander passen), macht dann die Knöpfe flacher und zeigt zuletzt eine Kurzfassung des Hinweiskastens:
    höchstens zwei Zeilen mit den Kernaussagen, ein Klick zeigt alle Grenzen (test_layout_bildschirme.py::
    test_kompaktstufen_nur_so_weit_wie_noetig_und_umkehrbar). Beide Texte nennen die Stufen in dieser Reihenfolge;
    die README dazu die Fenstergrenze und die Zeilen des Protokolls aus gui.py."""
    stufen = _konstante("anonymisierer/gui.py", "KOMPAKT_STUFEN")
    assert stufen == ("dateikopf", "knoepfe", "hinweiskasten")
    merkmal = {"dateikopf": "Ablagefläche", "knoepfe": "flacher", "hinweiskasten": "Kurzfassung"}
    for text, anfang in ((_lies("README.md"), "- **Kleine Bildschirme**"),
                         (_lies("CHANGELOG.md"), "- **Kleine Bildschirme:**")):
        punkt = _listenpunkt(text, anfang)
        assert "einzeilig" not in punkt, anfang
        lage = [punkt.index(merkmal[stufe]) for stufe in stufen]
        assert lage == sorted(lage), (anfang, lage)
        for begriff in ("nebeneinander passen", "zwei Zeilen", "Kernaussagen", "Klick"):
            assert begriff in punkt, (anfang, begriff)
    punkt = _listenpunkt(_lies("README.md"), "- **Kleine Bildschirme**")
    assert f"Unter {_konstante('anonymisierer/gui.py', 'FENSTER_KLEIN_HOEHE')} Pixel Fensterhöhe" in punkt
    assert (f"{_konstante('anonymisierer/gui.py', 'PROTOKOLL_ZEILEN_KLEIN')} statt "
            f"{_konstante('anonymisierer/gui.py', 'PROTOKOLL_ZEILEN')} Zeilen") in punkt


def test_doku_paketaufbau_nennt_jedes_modul():
    """Durchsicht Befund 5: Der Paketaufbau der README und der Modulkopf von pdf_anonymisierer.py nannten
    anonymisierer/auftrag.py nicht. Jedes Modul des Pakets steht in beiden."""
    module = sorted(p.stem for p in (WURZEL / "anonymisierer").glob("*.py") if p.stem != "__init__")
    assert "auftrag" in module
    aufbau = _listenpunkt(_lies("README.md"), "- Code und Oberfläche sind deutsch.")
    kopf = ast.get_docstring(ast.parse(_lies("pdf_anonymisierer.py")))
    for name in module:
        assert f"`{name}.py`" in aufbau, f"Paketaufbau der README nennt {name}.py nicht"
        assert re.search(rf"(?<!\w){name}(?!\w)", kopf), f"Modulkopf von pdf_anonymisierer.py nennt {name} nicht"
    for ordner in ("detektoren", "daten"):
        assert f"`{ordner}/`" in aufbau, ordner


def test_doku_entwicklerteil_nennt_exe_bau_fuer_jeden_pull_request():
    """Durchsicht Befund 5: Seit a88d8da baut die GitHub-Action die EXE auch für jeden Pull Request (Job „exe“,
    test_github_action_rechte_zeitlimits_screenshots_und_exe_job); der Entwicklerteil der README nannte nur „auf
    Wunsch bzw. für Versions-Tags“. Der Satz zum EXE-Bau nennt alle drei Auslöser des Jobs."""
    entwickler = _abschnitt(_lies("README.md"), "## Mitentwickeln und Tests")
    satz = next(s for s in re.split(r"(?<=[.)])\s+(?=[A-ZÄÖÜ])", entwickler) if "EXE-bauen.bat" in s)
    for ausloeser in ("für jeden Pull Request", "auf Wunsch", "Versions-Tags"):
        assert ausloeser in satz, (ausloeser, satz)


# Nachprüfung der Durchsicht: Grenzen, die die Gegenprüfung an den berichtigten Texten gefunden hat
def test_doku_briefkopf_rat_auch_bei_bekanntem_namen():
    """Nachprüfung Befund 1: README und CHANGELOG nannten den bekannten Namen vor der Anschrift, als reiche er – der Rat
    „prüfen und anhaken“ hing am unbekannten Namen. Nötig ist er, er reicht aber nicht immer: Ohne Trenner hinter dem
    Namen oder mit einer Firmenzeile zwischen Name und Anschrift („Mitglied der Handwerkskammer …“) bleibt die
    Anschrift auch mit bekanntem Namen nicht angehakt (test_robustheit_analyse.py::
    test_briefkopf_wie_eine_firma_nur_mit_bekanntem_namen_geschwaerzt). Beide Texte geben den Rat deshalb unabhängig
    vom Namen; der Modulkopf von analyse.py nennt die Bedingungen (_absender_einer_person, _person_vorn)."""
    for text, anfang in ((_lies("README.md"), "- **Firmenanschriften**"),
                         (_lies("CHANGELOG.md"), "- **Mehr wird geschwärzt")):
        punkt = _listenpunkt(text, anfang)
        for begriff in ("auch dann nicht immer", "Mitglied der Handwerkskammer",
                        "jeden solchen Fund prüfen und anhaken, wenn es ihre Anschrift ist",
                        "auch wenn ihr Name davorsteht"):
            assert begriff in punkt, (anfang, begriff)
    assert _konstante("anonymisierer/analyse.py", "_ABSENDER_ZEILEN_DARUEBER") == 3
    kopf = _flach(ast.get_docstring(ast.parse(_lies("anonymisierer/analyse.py"))))
    for begriff in ("bis zu drei Zeilen darüber", "ohne Firmenzeile dazwischen", "erste Segment endet mit ihm"):
        assert begriff in kopf, begriff


def test_doku_restrisiko_kein_verlass_auf_verdacht_fuer_abgewaehlte_anschrift():
    """Nachprüfung Befund 2: Der CHANGELOG versprach, eine lesbare Privatanschrift im Briefkopf von Selbständigen falle
    in der Ausgabe als Verdacht auf. Steht über ihr eine Zeile, die die Restrisiko-Prüfung als Namen einer Organisation
    liest („Mitglied der Handwerkskammer …“), meldet sie sie nicht (test_robustheit_analyse.py::
    test_abgewaehlte_privatanschrift_unter_kammerzeile_ohne_verdacht). CHANGELOG und Docstring von
    analyse._firmenanschriften sagen deshalb „meist“ und nennen die Grenze. Außerdem gilt „gar nicht an die Schwärzung“
    nur für Funde im Text: ein ganz abgewähltes Lichtbild geht mit allen Bereichen abgewählt mit (auftrag.auftrag_funde,
    Lichtbild-Punkt des CHANGELOG)."""
    punkt = _listenpunkt(_lies("CHANGELOG.md"), "- **Restrisiko-Prüfung:**")
    assert "fällt bei Selbständigen eine lesbare Privatanschrift im Briefkopf noch in der Ausgabe auf" not in punkt
    for begriff in ("ganz abgewählten Fund im Text", "meist weiter als Verdacht", "kein Verlass", "Organisation",
                    "Mitglied der Handwerkskammer", "ohne Verdacht"):
        assert begriff in punkt, begriff
    funktion = next(k for k in ast.parse(_lies("anonymisierer/analyse.py")).body
                    if isinstance(k, ast.FunctionDef) and k.name == "_firmenanschriften")
    doc = _flach(ast.get_docstring(funktion))
    assert "ist das in der Ausgabe der einzige Hinweis" not in doc
    for begriff in ("meist weiter als Verdacht", "oft der einzige Hinweis", "verlässlich ist er nicht",
                    "Mitglied der Handwerkskammer", "restrisiko._org_name"):
        assert begriff in doc, begriff
    # Ein ganz abgewählter Fund im Text bleibt aus dem Auftrag weg, ein ganz abgewähltes Lichtbild geht abgewählt mit
    sys.path.insert(0, str(WURZEL))
    from anonymisierer import auftrag
    text_fund = {"kategorie": "strasse", "text": "Hauptstraße 12", "stellen": [{"seite": 0, "start": 0, "ende": 14}]}
    bild_fund = {"kategorie": "lichtbild", "text": "", "stellen": [{"seite": 0, "start": 0, "ende": 0, "an": True,
                                                                    "text": "", "bereich": [40, 60, 160, 210]}]}
    angehakt, bilder = auftrag.auftrag_funde([text_fund, bild_fund], ["aus", "aus"], True)
    assert angehakt == [] and [b["kategorie"] for b in bilder] == ["lichtbild"]
    assert [st["an"] for st in bilder[0]["stellen"]] == [False]


def test_doku_selbsttest_nennt_abweichungen_von_der_oberflaeche():
    """Nachprüfung (Werkzeuge): Die README sagte, selbsttest.py analysiere und schwärze einen Ordner „wie die
    Oberfläche“. Er gibt aber auch ganz abgewählte Funde an die Schwärzung – die Restrisiko-Prüfung meldet sie dann
    nicht (test_selbsttest.py::test_selbsttest_gibt_ganz_abgewaehlte_funde_mit_anders_als_die_oberflaeche) –,
    schwärzt ohne „Freigabe vor Weitergabe“ und nimmt jedes Dokument für sich, ohne Weitergabe im Lauf und ohne
    Kundenliste. README und Modulkopf nennen das; die Aufrufe in selbsttest.py, auf die sich beide stützen, sind hier
    mitgeprüft."""
    punkt = _listenpunkt(_lies("README.md"), "- `selbsttest.py`")
    assert "Ordner wie die Oberfläche" not in punkt
    for begriff in ("nicht ganz wie in der Oberfläche", "jedes Dokument für sich", "Weitergabe im Lauf", "Kundenliste",
                    "Freigabe vor Weitergabe", "ganz abgewählte Funde", "Restrisiko-Prüfung", "--einstellungen"):
        assert begriff in punkt, begriff
    baum = ast.parse(_lies("werkzeuge/selbsttest.py"))
    kopf = _flach(ast.get_docstring(baum))
    assert "wie in der Oberfläche analysiert und geschwärzt" not in kopf
    for begriff in ("nicht ganz wie in der Oberfläche", "auftrag.auftrag_funde", "freigabe_erforderlich", "Kundenliste",
                    "weitergabe_anwenden"):
        assert begriff in kopf, begriff
    aufrufe = {getattr(k.args[0], "id", None): k for k in ast.walk(baum)
               if isinstance(k, ast.Call) and getattr(k.func, "id", None) == "_rufe" and k.args}
    assert not {"lauf", "kundenliste"} & {w.arg for w in aufrufe["analysiere_pdf"].keywords}
    schwaerzen = aufrufe["schwaerze_pdf"]
    assert "freigabe_erforderlich" not in {w.arg for w in schwaerzen.keywords}
    assert ast.unparse(schwaerzen.args[2]) == "a['funde']"           # alle Funde der Analyse, auch ganz abgewählte
    namen = {k.id for k in ast.walk(baum) if isinstance(k, ast.Name)} | {k.attr for k in ast.walk(baum)
                                                                         if isinstance(k, ast.Attribute)}
    assert not {"standard_auftrag", "auftrag_funde", "weitergabe_anwenden", "LaufWissen"} & namen


def test_lizenz_und_drittkomponenten():
    lizenz = _lies("LICENSE")
    assert lizenz.startswith("MIT License")
    assert "Copyright (c)" in lizenz and "Alex8791-cyber" in lizenz
    assert "licenses/AGPL-3.0.txt" in lizenz
    notices = _lies("THIRD_PARTY_NOTICES.md")
    for begriff in ("PyMuPDF", "AGPL-3.0", "deu.traineddata", "Apache-2.0", "spaCy",
                    "de_core_news_md", "tkinterdnd2", "MIT"):
        assert begriff in notices
    # AD-02/AD-07: Ort des AGPL-Texts, richtige Versionen, Abhängigkeiten von PyMuPDF 2.x
    for begriff in ("licenses/AGPL-3.0.txt", "1.24.10", "MuPDF 1.24.9", "2.10.3", "onnxruntime", "PyYAML",
                    "psutil", "networkx", "nicht in der EXE"):
        assert begriff in notices, f"THIRD_PARTY_NOTICES.md: '{begriff}' fehlt"
    assert "2.9.x" not in notices and "MuPDF 1.26–1.28" not in notices
    # MIT verlangt den Copyright-Vermerk der gebündelten Pakete
    for vermerk in ("ExplosionAI GmbH", "Philippe Gagné", "George Petasis"):
        assert vermerk in notices


def test_github_action():
    text = _lies(".github/workflows/tests.yml")
    for begriff in ("ubuntu-latest", "windows-latest", "pytest", "--only-binary=:all:",
                    "TESSDATA_PREFIX", 'python-version: "3.12"', "requirements.txt"):
        assert begriff in text
    yaml = pytest.importorskip("yaml")
    daten = yaml.safe_load(text)
    assert "pytest" in daten["jobs"]
    assert set(daten["jobs"]["pytest"]["strategy"]["matrix"]["os"]) == {"ubuntu-latest", "windows-latest"}


def test_github_action_installiert_testpakete_ausserhalb_der_exe():
    """CI-Lauf auf 2090752: tests/test_tabellen_scans.py erzeugt schräg gescannte Seiten mit Pillow, die GitHub-Action
    installierte es nicht – sieben Tests schlugen mit „No module named 'PIL'“ fehl (lokal war Pillow zufällig
    vorhanden). Pillow und pyyaml brauchen nur die Tests und die Domänen-Probe: Sie gehören in die
    Installationsschritte der Jobs „pytest“ und „domaenenprobe“ und in die Anleitung der README, aber nicht in
    requirements-dev.txt, denn EXE-bauen.bat installiert diese Datei und PyInstaller packte Pillow sonst in die EXE."""
    yaml = pytest.importorskip("yaml")
    daten = yaml.safe_load(_lies(".github/workflows/tests.yml"))

    def pakete(job):
        return " ".join(s.get("run", "") for s in daten["jobs"][job]["steps"] if "pip install" in s.get("run", "")).split()

    assert {"pyyaml", "pillow"} <= set(pakete("pytest")), pakete("pytest")
    assert "pillow" in pakete("domaenenprobe"), pakete("domaenenprobe")
    assert "pillow" not in [w.lower() for w in pakete("exe")], pakete("exe")
    dev = _lies("requirements-dev.txt").lower()
    assert "pillow" not in dev and "pyyaml" not in dev
    assert "requirements-dev.txt pyyaml pillow" in _abschnitt(_lies("README.md"), "## Mitentwickeln und Tests")
    assert "**Pillow**" in _lies("werkzeuge/domaenenprobe/README.md")


def test_github_action_rechte_zeitlimits_screenshots_und_exe_job():
    """AD-05: nur Leserechte, Zeitlimits, Auflösung und Layout-Screenshots, EXE-Bau auf windows-latest."""
    text = _lies(".github/workflows/tests.yml")
    assert re.search(r"^permissions:\n  contents: read$", text, re.MULTILINE)
    yaml = pytest.importorskip("yaml")
    daten = yaml.safe_load(text)
    ausloeser = daten.get("on", daten.get(True))         # YAML 1.1 liest den Schlüssel "on" als True
    assert "workflow_dispatch" in ausloeser and "v*" in ausloeser["push"]["tags"]
    assert ausloeser["push"]["branches"] == ["main"] and "pull_request" in ausloeser
    assert daten["permissions"] == {"contents": "read"}
    for name, job in daten["jobs"].items():
        assert job.get("timeout-minutes"), f"Job {name} ohne timeout-minutes"
        for schritt in job["steps"]:
            lauf = schritt.get("run", "")
            if any(w in lauf for w in ("pip install", "pytest", "EXE-bauen.bat", "apt-get")):
                assert schritt.get("timeout-minutes"), f"{name}: Schritt '{schritt.get('name')}' ohne timeout-minutes"

    pytest_job = daten["jobs"]["pytest"]
    schritte = pytest_job["steps"]
    assert any("PrimaryScreen" in s.get("run", "") and s.get("if") == "runner.os == 'Windows'" for s in schritte)
    assert any("scrot" in s.get("run", "") for s in schritte), "Linux braucht scrot für die Layout-Screenshots"
    tests = [s for s in schritte if "pytest" in s.get("run", "")]
    assert len(tests) == 2
    for s in tests:
        assert "-rs" in s["run"], "Begründungen übersprungener Tests gehören in den Bericht"
        assert "PDF_ANONYMISIERER_SCREENSHOTS" in s.get("env", {})
    upload = [s for s in schritte if str(s.get("uses", "")).startswith("actions/upload-artifact")]
    assert len(upload) == 2 and all(u["if"] == "always()" for u in upload)
    assert any("screenshots" in u["with"]["path"] for u in upload)
    assert any("bericht" in u["with"]["path"] for u in upload), "Benchmark-Bericht als Artefakt sichern"

    exe = daten["jobs"]["exe"]
    assert exe["runs-on"] == "windows-latest" and exe["needs"] == "pytest"
    assert "workflow_dispatch" in exe["if"] and "refs/tags/v" in exe["if"]
    assert "github.event_name == 'pull_request'" in exe["if"], "Jeder Pull Request baut und startet die EXE"
    lauf = "\n".join(s.get("run", "") for s in exe["steps"])
    assert "call EXE-bauen.bat < NUL" in lauf, "Der EXE-Job soll genau EXE-bauen.bat ausführen (gleiche Flags)"
    assert ".python_pfad.txt" in lauf
    for pflicht in ("_internal\\tessdata\\deu.traineddata", "_internal\\de_core_news_md", "LICENSE.txt",
                    "THIRD_PARTY_NOTICES.md", "README.md", "licenses\\AGPL-3.0.txt", "Start-Process", "fehler.log",
                    "-windows-x64.zip"):
        assert pflicht in lauf, f"EXE-Job prüft '{pflicht}' nicht"
    assert "-windows-x64.zip" in _lies("EXE-bauen.bat")
    hochladen = [s for s in exe["steps"] if str(s.get("uses", "")).startswith("actions/upload-artifact")]
    assert len(hochladen) == 1 and hochladen[0]["with"]["if-no-files-found"] == "error"
    assert hochladen[0]["with"]["path"].endswith(".zip")


def test_gitattributes_und_gitignore():
    assert "*.bat text eol=crlf" in _lies(".gitattributes")
    ignore = _lies(".gitignore")
    for eintrag in ("fehler.log", "build/", "dist/", "*.spec", ".python_pfad.txt", "anonymisiert/"):
        assert eintrag in ignore


# ----------------------------------------------------------------------
# werkzeuge/verknuepfung.py – ohne Windows testbar
# ----------------------------------------------------------------------

KNIFFLIGE_PFADE = [
    r"C:\Users\Jörg\AppData\Local\Programs\Python\Python312\pythonw.exe",
    r"C:\Users\jm\OneDrive - Müller & Partner GmbH\Desktop\PDF-Anonymizer-main (1)\PDF-Anonymizer-main",
    r"D:\Büro\O'Brien!\PDF-Anonymisierer",
]


def _verknuepfung():
    sys.path.insert(0, str(WURZEL))
    import werkzeuge.verknuepfung as v
    return v


def test_ps1_enthaelt_keine_pfade():
    v = _verknuepfung()
    assert "\\" not in v.PS1_TEXT and "%" not in v.PS1_TEXT
    for var in ("PDFANON_LNK", "PDFANON_ZIEL", "PDFANON_SKRIPT", "PDFANON_ORDNER", "PDFANON_ICON"):
        assert f"$env:{var}" in v.PS1_TEXT
    assert "WScript.Shell" in v.PS1_TEXT and ".Save()" in v.PS1_TEXT


def test_ps1_wird_mit_bom_geschrieben(tmp_path):
    v = _verknuepfung()
    ps1 = v.schreibe_ps1(tmp_path)
    roh = ps1.read_bytes()
    assert roh.startswith(b"\xef\xbb\xbf"), "PowerShell 5.1 braucht UTF-8 mit BOM (M-26)"
    inhalt = roh[3:].decode("utf-8")
    assert "\r\n" in inhalt, "Zeilenenden muessen CRLF sein (Windows PowerShell)"
    assert inhalt.replace("\r\n", "\n") == v.PS1_TEXT.replace("\r\n", "\n")


@pytest.mark.parametrize("pfad", KNIFFLIGE_PFADE)
def test_umgebung_reicht_pfade_unveraendert_durch(pfad):
    v = _verknuepfung()
    p = Path(pfad)
    env = v.umgebung(ziel=p, skript=p / "pdf_anonymisierer.py", ordner=p, lnk=p / "x.lnk", basis={})
    assert env["PDFANON_ZIEL"] == str(p)
    assert env["PDFANON_SKRIPT"] == str(p / "pdf_anonymisierer.py")
    assert env["PDFANON_ORDNER"] == str(p)
    assert env["PDFANON_LNK"] == str(p / "x.lnk")
    assert env["PDFANON_ICON"] == ""
    assert v.umgebung(p, p, p, p, icon=p / "icon.ico", basis={})["PDFANON_ICON"] == str(p / "icon.ico")


def test_python_pfad_datei_ohne_bom(tmp_path):
    v = _verknuepfung()
    datei = tmp_path / ".python_pfad.txt"
    pfad = Path(KNIFFLIGE_PFADE[0])
    v.schreibe_python_pfad(pfad, datei)
    roh = datei.read_bytes()
    assert not roh.startswith(b"\xef\xbb\xbf")
    assert roh.decode("utf-8") == str(pfad)
    assert b"\n" not in roh  # set /p in Starten.bat liest genau eine Zeile


def test_powershell_befehle_mit_fallback(tmp_path):
    v = _verknuepfung()
    befehle = v.powershell_befehle(tmp_path / "v.ps1")
    assert len(befehle) == 2
    assert befehle[0][0] == "powershell.exe" and "-File" in befehle[0] and "-NoProfile" in befehle[0]
    assert "-Command" in befehle[1] and "$lnk.Save()" in befehle[1][-1]
    assert all("-NonInteractive" in b for b in befehle)


def test_pythonw_pfad_fallback():
    v = _verknuepfung()
    assert v.pythonw_pfad() == Path(sys.executable).resolve() or v.pythonw_pfad().name == "pythonw.exe"


@pytest.mark.skipif(sys.platform == "win32", reason="unter Windows legt das Skript wirklich eine Verknuepfung an")
def test_verknuepfung_main_ausserhalb_windows():
    v = _verknuepfung()
    assert v.main([]) == 2


def _als_windows(v, monkeypatch):
    """main() so aufrufen, als liefe es unter Windows (nur das Modul sieht sys.platform == 'win32')."""
    monkeypatch.setattr(v, "sys", types.SimpleNamespace(platform="win32", executable=sys.executable, argv=[]))


def test_verknuepfung_trotz_schreibgeschuetztem_programmordner(tmp_path, monkeypatch, capsys):
    """Befund: .python_pfad.txt wurde vor dem try geschrieben – im schreibgeschützten Programmordner (z. B.
    Netzlaufwerk nur mit Leserecht) brach main() mit Traceback ab, ohne Desktop-Verknüpfung."""
    v = _verknuepfung()
    _als_windows(v, monkeypatch)

    def verweigert(pythonw, datei=None):
        raise PermissionError(13, "Zugriff verweigert", str(datei or v.PFAD_DATEI))

    angelegt = []

    def anlegen(pythonw, desktop=None):
        angelegt.append(pythonw)
        lnk = tmp_path / f"{v.NAME}.lnk"
        lnk.write_bytes(b"lnk")
        return lnk

    monkeypatch.setattr(v, "schreibe_python_pfad", verweigert)
    monkeypatch.setattr(v, "verknuepfung_anlegen", anlegen)
    assert v.main([]) == 0
    ausgabe = capsys.readouterr().out
    assert angelegt == [v.pythonw_pfad()]
    assert ".python_pfad.txt" in ausgabe and "Starten.bat" in ausgabe and "Zugriff verweigert" in ausgabe
    assert "Verknüpfung angelegt" in ausgabe and "FEHLER" not in ausgabe


@pytest.mark.parametrize("fehler", [RuntimeError("PowerShell konnte die Verknüpfung nicht anlegen.\nZugriff"),
                                    PermissionError(13, "Zugriff verweigert"),
                                    OSError(28, "Kein Speicherplatz")])
def test_verknuepfung_exit_1_nur_ohne_verknuepfung(tmp_path, monkeypatch, capsys, fehler):
    """Exit-Code 1 (Installieren.bat: „OHNE Desktop-Verknüpfung“) nur, wenn die .lnk wirklich fehlt – auch ein
    OSError beim Anlegen (Temp-Ordner, Desktop) endet mit Meldung statt Traceback."""
    v = _verknuepfung()
    _als_windows(v, monkeypatch)
    pfad_datei = tmp_path / ".python_pfad.txt"
    monkeypatch.setattr(v, "PFAD_DATEI", pfad_datei)

    def anlegen(pythonw, desktop=None):
        raise fehler

    monkeypatch.setattr(v, "verknuepfung_anlegen", anlegen)
    assert v.main([]) == 1
    ausgabe = capsys.readouterr().out
    assert "FEHLER" in ausgabe and "Starten.bat" in ausgabe
    assert pfad_datei.read_text(encoding="utf-8") == str(v.pythonw_pfad())   # Starten.bat findet Python trotzdem


def test_pruefe_installation_laeuft():
    lauf = subprocess.run([sys.executable, "-W", "ignore", str(WURZEL / "werkzeuge" / "pruefe_installation.py")],
                          capture_output=True, text=True, timeout=180, cwd=str(WURZEL))
    assert "Python:" in lauf.stdout and "tessdata" in lauf.stdout and "fehler.log" in lauf.stdout
    assert lauf.returncode in (0, 1), lauf.stderr
    if lauf.returncode == 1:
        assert "PROBLEME" in lauf.stdout


def test_pruefe_installation_vergleicht_versionen_mit_requirements():
    sys.path.insert(0, str(WURZEL))
    import werkzeuge.pruefe_installation as p
    grenzen = p.versionsgrenzen()
    assert set(grenzen) == set(_pins()) | {"de_core_news_md"}
    assert grenzen["pymupdf"][1:] == ((1, 24, 10), (3,))
    ok = {"pymupdf": "2.1", "spacy": "3.8.18", "tkinterdnd2": "0.7.0", "de_core_news_md": "3.8.0"}
    assert p.versions_probleme(ok) == []
    assert p.versions_probleme({**ok, "pymupdf": "1.28.2"}) == []
    for paket, version in (("pymupdf", "1.24.9"), ("pymupdf", "3.0"), ("spacy", "3.9.0"),
                           ("tkinterdnd2", "0.3"), ("de_core_news_md", "3.7.0")):
        probleme = p.versions_probleme({**ok, paket: version})
        assert len(probleme) == 1 and paket in probleme[0] and version in probleme[0], probleme
    assert p.versions_probleme({**ok, "pymupdf": None}) == []   # fehlende Pakete meldet pakete_bericht


def test_pruefe_installation_nennt_arm64_nicht_mehr_pauschal_als_problem():
    text = _lies("werkzeuge/pruefe_installation.py")
    assert "ARM64 wird nicht unterstützt" not in text
    assert "sysconfig.get_platform()" in text   # Paketauswahl hängt am Python, nicht am Prozessor


DLL_FEHLER = "DLL load failed while importing _mupdf: Das angegebene Modul wurde nicht gefunden."


def _pruefe_installation():
    sys.path.insert(0, str(WURZEL))
    import werkzeuge.pruefe_installation as p
    return p


def test_pruefe_installation_nennt_vc_laufzeit_bei_dll_ladefehler(monkeypatch):
    """Befund: „DLL load failed“ stand nur als Importfehler im Bericht – die Ursache (fehlende Visual-C++-Laufzeit)
    und die Abhilfe nicht. Gemeldet wird sie einmal, auch wenn PyMuPDF und spaCy beide scheitern."""
    p = _pruefe_installation()
    monkeypatch.setattr(p, "_version", lambda paket: VERSIONEN_OK.get(paket))
    monkeypatch.setattr(p, "_importierbar", lambda modul: (False, f"ImportError: {DLL_FEHLER}")
                        if modul in ("fitz", "spacy") else (True, "ok"))
    monkeypatch.setitem(sys.modules, "spacy", types.SimpleNamespace(load=lambda *a, **k: None))
    _zeilen, probleme = p.pakete_bericht()
    laufzeit = [pr for pr in probleme if "Visual C++" in pr]
    assert len(laufzeit) == 1, probleme
    for begriff in ("DLL load failed", VC_WINGET, "vc_redist.x64.exe", VC_LINK):
        assert begriff in laufzeit[0], laufzeit[0]
    # ein gewöhnlicher Importfehler bleibt, was er ist
    monkeypatch.setattr(p, "_importierbar", lambda modul: (False, "ModuleNotFoundError: No module named 'fitz'")
                        if modul == "fitz" else (True, "ok"))
    _zeilen, probleme = p.pakete_bericht()
    assert probleme and not any("Visual C++" in pr for pr in probleme)
    # unter Windows mit der Ladeprobe: fehlt die Laufzeit, oder lässt sie sich laden und ist vermutlich veraltet?
    fehlt = p._dll_problem(["fitz"], ["msvcp140.dll"])
    assert "'fitz' lässt sich" in fehlt and "fehlt (msvcp140.dll" in fehlt and VC_WINGET in fehlt
    veraltet = p._dll_problem(["fitz", "spacy"], [])
    assert "'fitz' und 'spacy' lassen sich" in veraltet and "veraltet" in veraltet and VC_WINGET in veraltet
    # pip hielte das installierte PyMuPDF für vollständig – deshalb ausdrücklich --force-reinstall, mit den Grenzen
    assert f'--force-reinstall --no-deps --only-binary=:all: "pymupdf{_pins()["pymupdf"]}"' in veraltet
    assert "Installieren.bat erneut" not in veraltet


def test_pruefe_installation_dll_abhilfe_je_modul():
    """Befund: War die Laufzeit ladbar, riet die Meldung immer, PyMuPDF neu zu installieren – auch wenn nur spaCy oder
    tkinter an einer DLL scheiterten. tkinter gehört zu Python selbst (Tcl/Tk); die Visual-C++-Laufzeit ist dort nicht
    die übliche Ursache. Die Abhilfe richtet sich jetzt nach dem gescheiterten Modul."""
    p = _pruefe_installation()
    pymupdf_neu = f'--force-reinstall --no-deps --only-binary=:all: "pymupdf{_pins()["pymupdf"]}"'
    spacy_neu = f'--force-reinstall --only-binary=:all: "spacy{_pins()["spacy"]}"'     # mit thinc, blis, …
    dnd_neu = f'--force-reinstall --no-deps --only-binary=:all: "tkinterdnd2{_pins()["tkinterdnd2"]}"'
    spacy = p._dll_problem(["spacy"], [])
    assert spacy.startswith("'spacy' lässt sich nicht laden („DLL load failed“)."), spacy
    assert spacy_neu in spacy and "pymupdf" not in spacy.lower(), spacy
    assert VC_WINGET in spacy and "veraltet" in spacy, spacy        # spaCy (C++) braucht die Laufzeit ebenso
    assert VC_WINGET in p._dll_problem(["spacy"], ["msvcp140.dll"])
    for fehlt in ([], ["msvcp140.dll"], None):
        tk = p._dll_problem(["tkinter"], fehlt)
        assert "Tcl/Tk" in tk and "reparieren" in tk and "tcl/tk and IDLE" in tk, tk
        assert "pip install" not in tk and VC_WINGET not in tk and "pymupdf" not in tk.lower(), tk
    nur_dnd = p._dll_problem(["tkinterdnd2"], [])
    assert dnd_neu in nur_dnd and "pymupdf" not in nur_dnd.lower() and "Tcl/Tk" not in nur_dnd, nur_dnd
    # PyMuPDF wie bisher
    fitz = p._dll_problem(["fitz"], [])
    assert pymupdf_neu in fitz and spacy_neu not in fitz and "Tcl/Tk" not in fitz, fitz
    # mehrere Module: jede Abhilfe passt zu ihrem Modul; tkinterdnd2 scheitert dann an tkinter
    alle = p._dll_problem(["fitz", "spacy", "tkinter", "tkinterdnd2"], [])
    for teil in (pymupdf_neu, spacy_neu, "Tcl/Tk", VC_WINGET):
        assert teil in alle, (teil, alle)
    assert dnd_neu not in alle, alle


def _windows_rechner(tmp_path, monkeypatch, system32=(), python_ordner=("vcruntime140.dll", "vcruntime140_1.dll")):
    """Nachgebauter Windows-Rechner für die Laufzeit-Prüfung: Dateien in %SystemRoot%\\System32 und im Ordner von
    python.exe (Standard: was jedes python.org-Python mitbringt). ctypes.WinDLL lädt einen Namen ohne Pfad wie Windows
    für ein 64-Bit-Python (LOAD_LIBRARY_SEARCH_DEFAULT_DIRS): zuerst aus dem Ordner von python.exe, dann aus System32 –
    nicht aus PATH. GetModuleFileNameW nennt den Pfad der geladenen Datei. Rückgabe: (System32, Ordner von python.exe).
    """
    import ctypes
    system, python = tmp_path / "Windows" / "System32", tmp_path / "Python312"
    for ordner, dateien in ((system, system32), (python, ("python.exe", *python_ordner))):
        ordner.mkdir(parents=True)
        for datei in dateien:
            (ordner / datei).write_bytes(b"MZ")
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    monkeypatch.setattr(sys, "executable", str(python / "python.exe"))
    geladen = {}

    def modulname(handle, puffer, groesse):
        puffer.value = geladen[handle]
        return len(geladen[handle])

    def windll(name, *args, **kwargs):
        if name.lower() in ("kernel32", "kernel32.dll"):
            return types.SimpleNamespace(GetModuleFileNameW=modulname)
        assert "\\" not in name and "/" not in name, f"{name}: mit Pfad gilt die Suchreihenfolge nicht"
        for ordner in (python, system):
            if (ordner / name).is_file():
                geladen[len(geladen) + 1] = str(ordner / name)
                return types.SimpleNamespace(_name=name, _handle=len(geladen))
        raise FileNotFoundError(2, f"Could not find module '{name}' (or one of its dependencies). Try using the full "
                                   "path with constructor syntax.")

    monkeypatch.setattr(ctypes, "WinDLL", windll, raising=False)
    return system, python


def test_pruefe_installation_vc_laufzeit_wie_python_sie_laedt(tmp_path, monkeypatch):
    """Befund (Regression): Der Bericht verlangte vcruntime140_1.dll im Systemordner. PyMuPDF braucht daraus nur
    __CxxFrameHandler4, und Python (ab 3.8.1) bringt die Datei im Ordner von python.exe mit – dort sucht Windows für
    Erweiterungsmodule zuerst. Auf einem Rechner mit VC++ 2015/2017 meldete der Bericht deshalb ein PROBLEM, obwohl
    „import fitz: ok“ daneben stand; mit app-lokaler Laufzeit (conda) ebenso."""
    p = _pruefe_installation()
    system, python = _windows_rechner(tmp_path, monkeypatch, system32=("msvcp140.dll", "vcruntime140.dll"))
    zeilen, probleme = p.laufzeit_bericht(windows=True)
    text = "\n".join(zeilen)
    assert probleme == [] and "FEHLT" not in text, (zeilen, probleme)
    assert str(system / "msvcp140.dll") in text and str(python / "vcruntime140_1.dll") in text, text
    # conda: die ganze Laufzeit liegt im Ordner von python.exe, im Systemordner nichts
    (system / "msvcp140.dll").rename(python / "msvcp140.dll")
    assert p.laufzeit_bericht(windows=True)[1] == []
    # fehlt msvcp140.dll wirklich (frischer Rechner), kommt das Problem – mit genau dieser Datei
    (python / "msvcp140.dll").unlink()
    zeilen, probleme = p.laufzeit_bericht(windows=True)
    assert len(probleme) == 1 and "msvcp140.dll" in probleme[0] and "vcruntime140_1.dll" not in probleme[0], probleme
    assert VC_WINGET in probleme[0] and "FEHLT msvcp140.dll" in "\n".join(zeilen), (zeilen, probleme)


def test_pruefe_installation_vc_laufzeit_bericht(tmp_path, monkeypatch):
    """Geänderte Erwartung (Gegenprüfung, Regression): Verlangt war, dass der Bericht die DLLs als Dateien in
    %SystemRoot%\\System32 sucht – das meldete Rechner mit VC++ 2015/2017 und mit conda fälschlich. Jetzt zählt, ob
    dieses Python die DLLs laden kann (Lader austauschbar; ohne Angabe ctypes wie beim Import von PyMuPDF)."""
    p = _pruefe_installation()

    def lader(*ladbar):
        def laden(dll):
            if dll not in ladbar:
                raise FileNotFoundError(2, f"Could not find module '{dll}'")
            return SYS32 + dll
        return laden
    zeilen, probleme = p.laufzeit_bericht(windows=True, laden=lader())
    assert len(probleme) == 1 and "msvcp140.dll" in probleme[0] and "vcruntime140_1.dll" in probleme[0]
    assert VC_NAME in probleme[0] and VC_WINGET in probleme[0] and VC_LINK in probleme[0]
    assert "FEHLT" in "\n".join(zeilen)
    zeilen, probleme = p.laufzeit_bericht(windows=True, laden=lader("msvcp140.dll"))
    assert len(probleme) == 1 and "vcruntime140_1.dll" in probleme[0] and "msvcp140.dll" not in probleme[0]
    zeilen, probleme = p.laufzeit_bericht(windows=True, laden=lader(*VC_DLLS))
    assert probleme == [] and SYS32 + "msvcp140.dll" in "\n".join(zeilen)
    assert p.laufzeit_bericht(windows=False) == ([], [])
    # Ohne Angabe lädt das prüfende Python die DLLs selbst (ctypes, Name ohne Pfad) – so wie PyMuPDF sie bekommt
    system, python = _windows_rechner(tmp_path, monkeypatch, system32=VC_DLLS)
    assert p.vc_laufzeit_fehlt() == []
    (system / "msvcp140.dll").unlink()
    assert p.vc_laufzeit_fehlt() == ["msvcp140.dll"]
    (python / "vcruntime140_1.dll").unlink()
    assert p.vc_laufzeit_fehlt() == ["msvcp140.dll"]            # System32 hat vcruntime140_1.dll noch
    (system / "vcruntime140_1.dll").unlink()
    assert p.vc_laufzeit_fehlt() == list(VC_DLLS)


def test_pruefe_installation_vc_laufzeit_aufruf_der_batchdateien(monkeypatch):
    """VC_AUFRUF im echten Python: Exit-Code 10 = beide DLLs ladbar (außerhalb von Windows gibt es nichts zu prüfen).
    Ein Fehler im Prüfcode (Exit-Code 1) fiele hier auf – die Batch-Dateien liefen dann ungeprüft weiter."""
    p = _pruefe_installation()
    lauf = subprocess.run([sys.executable, str(WURZEL / "werkzeuge" / "pruefe_installation.py"), "--vc-laufzeit"],
                          capture_output=True, text=True, timeout=120, cwd=str(WURZEL))
    assert lauf.returncode == p.VC_EXIT_BASIS == 10, (lauf.stdout, lauf.stderr[-2000:])
    if sys.platform == "win32":     # der echte Lader nennt den vollen Pfad der geladenen Datei
        for dll, ort in p.vc_laufzeit().items():
            assert ort and os.path.isabs(ort) and ort.lower().endswith(dll), (dll, ort)
    # main() gibt den Exit-Code der Prüfung unverändert weiter
    # (seit Runde 5 mit der PyMuPDF-Ladeprobe als Rückfall: main reicht sie an die Prüfung weiter)
    aufrufe = []
    monkeypatch.setattr(p, "vc_laufzeit_exitcode", lambda laden=None, **kw: aufrufe.append(kw) or 13)
    assert p.main(["--vc-laufzeit"]) == 13
    assert aufrufe == [{"pymupdf_laedt": p._pymupdf_laedt}], aufrufe


def test_pruefe_installation_meldet_den_benutzten_ocr_ordner(tmp_path, monkeypatch):
    """Befund: Bei einer fremden Tesseract-Installation ($TESSDATA_PREFIX nur mit eng.traineddata) las das Programm
    englisch, der Bericht zeigte aber „deu.traineddata vorhanden“. Jetzt nennt er Ordner und Sprache, mit denen
    die OCR wirklich liest, und dass $TESSDATA_PREFIX nicht benutzt wird."""
    p = _pruefe_installation()
    from anonymisierer import ocr
    programm = tmp_path / "programm"
    (programm / "tessdata").mkdir(parents=True)
    (programm / "tessdata" / "deu.traineddata").write_bytes(b"x" * 4096)
    fremd = tmp_path / "Tesseract-OCR" / "tessdata"
    fremd.mkdir(parents=True)
    (fremd / "eng.traineddata").write_bytes(b"x")
    monkeypatch.setattr(p, "PROGRAMM_ORDNER", programm)
    monkeypatch.setattr(ocr, "PROJEKTWURZEL", programm)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setenv("TESSDATA_PREFIX", str(fremd))
    zeilen, probleme = p.tessdata_bericht()
    text = "\n".join(zeilen)
    assert probleme == [], probleme
    assert f"OCR liest mit:  deu aus {programm / 'tessdata'}" in text, text
    assert f"TESSDATA_PREFIX zeigt auf {fremd}" in text and "nicht benutzt" in text, text
    assert "die mitgelieferte deutsche Sprachdatei geht vor" in text
    # mitgelieferte Datei fehlt, eine andere Tesseract-Installation hat Deutsch: der Grund passt dazu
    (programm / "tessdata" / "deu.traineddata").rename(programm / "deu.traineddata")
    system = tmp_path / "Programme" / "Tesseract-OCR" / "tessdata"
    system.mkdir(parents=True)
    (system / "deu.traineddata").write_bytes(b"x")
    monkeypatch.setattr(ocr, "_system_tessdata", lambda: [str(system)])
    monkeypatch.setenv("TESSDATA_PREFIX", str(fremd))
    zeilen, probleme = p.tessdata_bericht()
    text = "\n".join(zeilen)
    assert probleme == [] and f"OCR liest mit:  deu aus {system}" in text, text
    assert "nicht benutzt, dort liegt keine deu.traineddata" in text, text
    (programm / "deu.traineddata").rename(programm / "tessdata" / "deu.traineddata")
    # Fehlt die mitgelieferte Datei, liest die OCR aus der fremden Installation englisch: Problem mit dem Ordner
    (programm / "tessdata" / "deu.traineddata").unlink()
    monkeypatch.setattr(ocr, "_system_tessdata", lambda: [])
    monkeypatch.setenv("TESSDATA_PREFIX", str(fremd))
    zeilen, probleme = p.tessdata_bericht()
    assert f"OCR liest mit:  eng aus {fremd}" in "\n".join(zeilen)
    assert len(probleme) == 1 and str(fremd) in probleme[0] and "Englisch" in probleme[0], probleme
    assert "tessdata" in probleme[0] and "deu.traineddata" in probleme[0]


# ----------------------------------------------------------------------
# Startskript: Meldung, wenn PyMuPDF fehlt oder sich nicht laden lässt
# ----------------------------------------------------------------------
def _startskript():
    sys.path.insert(0, str(WURZEL))
    import pdf_anonymisierer as pa
    return pa


def test_startskript_nennt_vc_laufzeit_bei_dll_ladefehler(monkeypatch):
    """Befund: „DLL load failed“ (Visual-C++-Laufzeit fehlt) meldete das Startskript als „Paket fehlt – Installieren.bat
    ausführen“; das installiert nur erneut, ohne etwas zu ändern."""
    pa = _startskript()
    monkeypatch.delattr(sys, "frozen", raising=False)
    meldung = pa._meldung_paket_fehlt(ImportError(DLL_FEHLER))
    for begriff in (VC_NAME, VC_WINGET, "vc_redist.x64.exe", VC_LINK, "Administratorrechte", "DLL load failed"):
        assert begriff in meldung, meldung
    # dieselbe Ursache als OSError (ctypes/os.add_dll_directory: WinError 126 „Modul nicht gefunden“)
    fehler = OSError("[WinError 126] Das angegebene Modul wurde nicht gefunden")
    fehler.winerror = 126
    assert VC_WINGET in pa._meldung_paket_fehlt(fehler)
    # der Rückfall auf den alten Namen „fitz“ verdeckt die Ursache nicht (Ausnahmekette)
    try:
        try:
            raise ImportError(DLL_FEHLER)
        except ImportError:
            raise ModuleNotFoundError("No module named 'fitz'")
    except ImportError as e:
        verkettet = e
    assert VC_WINGET in pa._meldung_paket_fehlt(verkettet)
    # ein wirklich fehlendes Paket: wie bisher Installieren.bat
    gewoehnlich = pa._meldung_paket_fehlt(ModuleNotFoundError("No module named 'pymupdf'"))
    assert "Installieren.bat" in gewoehnlich and "Visual C++" not in gewoehnlich
    assert pa._meldung_paket_fehlt() == gewoehnlich
    # EXE: Die Laufzeit liegt im Programmordner – fehlt sie dort, hilft neu entpacken
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    exe = pa._meldung_paket_fehlt(ImportError(DLL_FEHLER))
    assert "neu entpacken" in exe and "Installieren.bat" not in exe


@pytest.mark.parametrize("ausloesen", [
    f"raise ImportError({DLL_FEHLER!r})\n",
    "e = OSError('[WinError 126] Das angegebene Modul wurde nicht gefunden')\ne.winerror = 126\nraise e\n",
])
def test_startskript_meldet_dll_ladefehler_beim_start(tmp_path, ausloesen):
    """Das echte Startskript mit einem PyMuPDF, das sich nicht laden lässt: Meldung statt Traceback, Exit-Code 1.
    Vorher fing es OSError gar nicht ab (Traceback), ImportError nur mit falscher Abhilfe. Die tkinter-Attrappe
    verhindert den Fehlerdialog – unter Windows bliebe er sonst offen stehen (dort gibt es kein DISPLAY)."""
    attrappe = tmp_path / "attrappe"
    for paket, code in (("pymupdf", ausloesen), ("fitz", "from pymupdf import *\n"),
                        ("tkinter", "raise ImportError('Testattrappe: kein Fehlerdialog')\n")):
        (attrappe / paket).mkdir(parents=True)
        (attrappe / paket / "__init__.py").write_text(code, encoding="utf-8")
    umgebung = dict(os.environ, PYTHONPATH=str(attrappe), DISPLAY="", PYTHONIOENCODING="utf-8")
    lauf = subprocess.run([sys.executable, "-W", "ignore", str(WURZEL / "pdf_anonymisierer.py")], capture_output=True,
                          text=True, encoding="utf-8", timeout=120, cwd=str(tmp_path), env=umgebung)
    assert lauf.returncode == 1, lauf.stderr[-2000:]
    assert "Traceback" not in lauf.stderr, lauf.stderr[-2000:]
    assert lauf.stdout.startswith("FEHLER: ") and VC_WINGET in lauf.stdout, lauf.stdout


def test_startskript_andere_osfehler_kommen_in_die_fehlerlog(tmp_path):
    """Befund: Seit auch OSError abgefangen wurde, erschien jeder OSError beim Import von PyMuPDF als „Das Paket
    'PyMuPDF' fehlt“ – auch ohne DLL-Bezug, z. B. ein PermissionError, weil ein Virenscanner eine Paketdatei sperrt.
    Die genannte Ursache war falsch, und es entstand keine fehler.log. Ein solcher Fehler geht jetzt wie jeder
    unerwartete Fehler mit Traceback in die fehler.log (Dialog „Unerwarteter Fehler“ mit Details; hier verhindert die
    tkinter-Attrappe den Dialog). Das Startskript läuft als Kopie mit dem Paket anonymisierer, damit die fehler.log
    neben der Kopie entsteht und nicht im Projektordner."""
    programm = tmp_path / "programm"
    programm.mkdir()
    shutil.copy2(WURZEL / "pdf_anonymisierer.py", programm)
    shutil.copytree(WURZEL / "anonymisierer", programm / "anonymisierer",
                    ignore=shutil.ignore_patterns("__pycache__"))
    gesperrt = ("raise PermissionError(13, 'Der Prozess kann nicht auf die Datei zugreifen (Virenscanner-Sperre)', "
                "'_extra.pyd')\n")
    attrappe = tmp_path / "attrappe"
    for paket, code in (("pymupdf", gesperrt), ("fitz", "from pymupdf import *\n"),
                        ("tkinter", "raise ImportError('Testattrappe: kein Fehlerdialog')\n")):
        (attrappe / paket).mkdir(parents=True)
        (attrappe / paket / "__init__.py").write_text(code, encoding="utf-8")
    umgebung = dict(os.environ, PYTHONPATH=str(attrappe), DISPLAY="", PYTHONIOENCODING="utf-8")
    lauf = subprocess.run([sys.executable, "-W", "ignore", str(programm / "pdf_anonymisierer.py")],
                          capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=str(tmp_path),
                          env=umgebung)
    assert lauf.returncode == 1, lauf.stderr[-2000:]
    assert "fehlt" not in lauf.stdout and "Installieren.bat" not in lauf.stdout, lauf.stdout
    log = programm / "fehler.log"
    assert log.is_file(), (lauf.stdout, lauf.stderr[-2000:])
    eintrag = log.read_text(encoding="utf-8")
    assert "Traceback" in eintrag and "PermissionError" in eintrag and "Virenscanner-Sperre" in eintrag, eintrag


def test_startskript_gesperrte_mupdf_datei_kommt_in_die_fehlerlog(tmp_path):
    """Gegenprüfung Runde 5: PyMuPDF fängt einen Fehler beim Laden von pymupdf.mupdf selbst ab und meldet „No module
    named 'mupdf'“ – der PermissionError (Virenscanner-Sperre) steht dann nur in der Ausnahmekette. Das Startskript
    meldete dafür „Das Paket 'PyMuPDF' fehlt“ ohne fehler.log; jetzt geht auch dieser Fall mit Traceback in die
    fehler.log."""
    programm = tmp_path / "programm"
    programm.mkdir()
    shutil.copy2(WURZEL / "pdf_anonymisierer.py", programm)
    shutil.copytree(WURZEL / "anonymisierer", programm / "anonymisierer",
                    ignore=shutil.ignore_patterns("__pycache__"))
    gesperrt = ("try:\n"
                "    raise PermissionError(13, 'Zugriff verweigert (Virenscanner-Sperre)', 'mupdf.py')\n"
                "except Exception:\n"
                "    raise ModuleNotFoundError(\"No module named 'mupdf'\")\n")
    attrappe = tmp_path / "attrappe"
    for paket, code in (("pymupdf", gesperrt), ("fitz", "from pymupdf import *\n"),
                        ("tkinter", "raise ImportError('Testattrappe: kein Fehlerdialog')\n")):
        (attrappe / paket).mkdir(parents=True)
        (attrappe / paket / "__init__.py").write_text(code, encoding="utf-8")
    umgebung = dict(os.environ, PYTHONPATH=str(attrappe), DISPLAY="", PYTHONIOENCODING="utf-8")
    lauf = subprocess.run([sys.executable, "-W", "ignore", str(programm / "pdf_anonymisierer.py")],
                          capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=str(tmp_path),
                          env=umgebung)
    assert lauf.returncode == 1, lauf.stderr[-2000:]
    assert "fehlt" not in lauf.stdout and "Installieren.bat" not in lauf.stdout, lauf.stdout
    log = programm / "fehler.log"
    assert log.is_file(), (lauf.stdout, lauf.stderr[-2000:])
    eintrag = log.read_text(encoding="utf-8")
    assert "PermissionError" in eintrag and "Virenscanner-Sperre" in eintrag, eintrag


def test_startskript_fremder_oserror_nur_ohne_dll_bezug():
    """Die Weiche des Startskripts: ein OSError ohne DLL-Bezug irgendwo in der Kette ist ein unerwarteter Fehler; ein
    DLL-Ladefehler und ein wirklich fehlendes Paket (ohne OSError) bleiben Meldungen."""
    pa = _startskript()
    try:
        try:
            raise PermissionError(13, "Zugriff verweigert")
        except PermissionError:
            raise ModuleNotFoundError("No module named 'mupdf'")
    except ImportError as e:
        gesperrt = e
    assert isinstance(pa._fremder_oserror(gesperrt), PermissionError)
    assert pa._fremder_oserror(ModuleNotFoundError("No module named 'pymupdf'")) is None
    assert pa._fremder_oserror(ImportError(DLL_FEHLER)) is None
    dll = OSError("[WinError 126] Das angegebene Modul wurde nicht gefunden")
    dll.winerror = 126
    assert pa._fremder_oserror(dll) is None


def test_pruefe_installation_bericht_in_cp1252():
    """Gegenprüfung Runde 5: Umgeleitete Ausgabe (> bericht.txt, | clip) schreibt unter Windows ohne UTF-8-Modus
    cp1252 – ein Zeichen wie „→“ brach den Bericht mitten in der Liste der Probleme ab. Alle Texte des Prüfskripts
    lassen sich in cp1252 schreiben, und main() schreibt ohnehin mit errors="replace"."""
    quelle = _lies("werkzeuge/pruefe_installation.py")
    quelle.encode("cp1252")
    assert 'reconfigure(errors="replace")' in quelle
    p = _pruefe_installation()
    for module in (["tkinter"], ["tkinter", "tkinterdnd2"], ["spacy"], ["fitz"], ["tkinterdnd2"]):
        p._dll_problem(module, []).encode("cp1252")


def test_vc_laufzeit_pymupdf_laedt_trotz_fehlgeschlagener_probe():
    """Gegenprüfung Runde 5: ctypes sucht eine DLL ohne Pfad nicht im Ordner von PyMuPDF, ein Erweiterungsmodul
    dagegen schon. Liegt msvcp140.dll nur dort, scheiterte die Probe, obwohl PyMuPDF lädt – Installieren.bat brach dann
    ab. Jetzt zählt in diesem Fall, dass PyMuPDF lädt."""
    p = _pruefe_installation()

    def laden(dll):
        if dll == "msvcp140.dll":
            raise OSError("[WinError 126] Das angegebene Modul wurde nicht gefunden")
        return "C:\\Python312\\" + dll

    assert p.vc_laufzeit_exitcode(laden, pymupdf_laedt=lambda: True) == p.VC_EXIT_BASIS
    assert p.vc_laufzeit_exitcode(laden, pymupdf_laedt=lambda: False) == p.VC_EXIT_BASIS + 1
    assert p.vc_laufzeit_exitcode(laden) == p.VC_EXIT_BASIS + 1          # Lader für Tests: keine echte Probe
    zeilen, probleme = p.laufzeit_bericht(windows=True, laden=laden, pymupdf_laedt=lambda: True)
    assert probleme == [] and "PyMuPDF lädt trotzdem" in "\n".join(zeilen), (zeilen, probleme)
    zeilen, probleme = p.laufzeit_bericht(windows=True, laden=laden, pymupdf_laedt=lambda: False)
    assert len(probleme) == 1 and "msvcp140.dll" in probleme[0], probleme


def _fliesstext(datei: str) -> str:
    """Text einer Datei als Fließtext: ohne REM, # und echo am Zeilenanfang, ohne ^ und `, Leerraum zusammengefasst –
    so lassen sich Sätze über Zeilenumbrüche hinweg prüfen."""
    zeilen = (re.sub(r"^\s*(REM\b|#|echo\b)", "", z, flags=re.IGNORECASE) for z in _lies(datei).splitlines())
    return re.sub(r"\s+", " ", " ".join(zeilen).replace("^", "").replace("`", ""))


def test_vc_laufzeit_texte_nennen_die_quelle_richtig():
    """Befund: Docstring des Startskripts, CHANGELOG, README, Prüfskript und Batch-Kommentare behaupteten, PyMuPDF lade
    msvcp140.dll und vcruntime140_1.dll aus dem Windows-Systemordner, Python bringe sie nicht mit. Python bringt
    vcruntime140_1.dll (ab 3.8.1, im Ordner von python.exe) selbst mit; fehlen kann praktisch nur msvcp140.dll."""
    falsch = re.compile(r"msvcp140\.dll und vcruntime140_1\.dll (aus dem|im) (Windows-)?Systemordner"
                        r"|Python bringt sie nicht mit", re.IGNORECASE)
    richtig = re.compile(r"Python bringt .{0,100}vcruntime140_1\.dll.{0,100}\bmit\b")
    for datei in ("README.md", "CHANGELOG.md", "pdf_anonymisierer.py", "werkzeuge/pruefe_installation.py",
                  "Installieren.bat", "EXE-bauen.bat"):
        treffer = falsch.search(_fliesstext(datei))
        assert treffer is None, f"{datei}: {treffer.group(0)!r}"
    for datei in ("README.md", "CHANGELOG.md", "pdf_anonymisierer.py", "werkzeuge/pruefe_installation.py",
                  "Installieren.bat"):
        assert richtig.search(_fliesstext(datei)), f"{datei}: sagt nicht, dass Python vcruntime140_1.dll mitbringt"


def test_vc_laufzeit_ueberall_gleich_benannt():
    """Name, winget-Befehl und Microsoft-Link der Laufzeit stehen in Batch, Startskript, Prüfskript und README
    gleich da (auseinanderlaufende Abhilfen verwirren am Telefon)."""
    for datei in ("Installieren.bat", "EXE-bauen.bat", "pdf_anonymisierer.py", "werkzeuge/pruefe_installation.py",
                  "README.md"):
        text = _lies(datei)
        for begriff in (VC_NAME, VC_WINGET, VC_LINK):
            assert begriff in text, f"{datei}: '{begriff}' fehlt"


def test_readme_vc_laufzeit_netzwerkfreigabe_und_ocr_ordner():
    text = _lies("README.md")
    voraus = text[text.index("## Voraussetzungen"):text.index("## Installation (Windows)")]
    assert VC_NAME in voraus and VC_WINGET in voraus and "EXE-Version" in voraus
    loesung = text[text.index("## Problemlösung"):text.index("## Technik")]
    for begriff in ("DLL load failed", "vc_redist.x64.exe", VC_WINGET, "TESSDATA_PREFIX", "\\\\server",
                    "schreibgeschützt", "pruefe_installation.py"):
        assert begriff in loesung, f"README, Problemlösung: '{begriff}' fehlt"


def test_readme_tabelle_skript_ohne_schreiben():
    lauf = subprocess.run([sys.executable, "-W", "ignore", str(WURZEL / "werkzeuge" / "readme_tabelle.py")],
                          capture_output=True, text=True, timeout=60, cwd=str(WURZEL))
    assert lauf.returncode == 0, lauf.stderr
    assert lauf.stdout.startswith("| Kategorie |")
