"""Tests für die Auslieferung: Batch-Dateien, requirements, tessdata, README, Lizenz, Werkzeuge.

Statische Prüfungen gegen die bekannten Stolperfallen aus dem Audit (M-08, M-26, M-27, M-37,
M-41 … M-46, M-60, M-62, M-70) und dem Auslieferungs-Review (AD-01 … AD-08). Es wird nichts
installiert und kein Windows gebraucht; die Python-Teile der Batch-Dateien (Vorab-Prüfungen)
werden aber wirklich ausgeführt.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import re
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
    assert 'cd /d "%~dp0"' in text
    # "!" in Pfaden ueberlebt nur ohne verzoegerte Variablenerweiterung (M-26)
    assert "EnableDelayedExpansion" not in text


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


def test_readme_tabelle_skript_ohne_schreiben():
    lauf = subprocess.run([sys.executable, "-W", "ignore", str(WURZEL / "werkzeuge" / "readme_tabelle.py")],
                          capture_output=True, text=True, timeout=60, cwd=str(WURZEL))
    assert lauf.returncode == 0, lauf.stderr
    assert lauf.stdout.startswith("| Kategorie |")
