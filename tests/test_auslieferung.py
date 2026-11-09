"""Tests für die Auslieferung: Batch-Dateien, requirements, tessdata, README, Lizenz, Werkzeuge.

Statische Prüfungen gegen die bekannten Stolperfallen aus dem Audit (M-08, M-26, M-27, M-37,
M-41 … M-46, M-60, M-62, M-70). Es wird nichts installiert und kein Windows gebraucht.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
BATCHES = ("Installieren.bat", "EXE-bauen.bat", "Starten.bat")


def _lies(name: str) -> str:
    return (WURZEL / name).read_text(encoding="utf-8")


def _version() -> str:
    sys.path.insert(0, str(WURZEL))
    from anonymisierer import __version__
    return __version__


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
    # Architektur / 32-Bit (M-41)
    assert "ARM" in text and "calcsize('P')" in text
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
    """Der zweite Versuch in der Batch nennt dieselben Bereichs-Pins wie requirements.txt."""
    req = {z.split("@")[0].strip() for z in _lies("requirements.txt").splitlines()
           if z.strip() and not z.startswith("#")}
    bat = _lies("Installieren.bat")
    for pin in ("pymupdf>=1.24,<3", "spacy>=3.8,<3.9", "tkinterdnd2>=0.4"):
        assert pin in req, f"{pin} fehlt in requirements.txt"
        assert f'"{pin}"' in bat, f"{pin} fehlt im Fallback der Installieren.bat"


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


# ----------------------------------------------------------------------
# requirements, tessdata, Versionsinfo
# ----------------------------------------------------------------------

def test_requirements_pins():
    text = _lies("requirements.txt")
    assert re.search(r"^pymupdf>=1\.24,<3$", text, re.MULTILINE)
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


def test_lizenz_und_drittkomponenten():
    lizenz = _lies("LICENSE")
    assert lizenz.startswith("MIT License")
    assert "Copyright (c)" in lizenz and "Alex8791-cyber" in lizenz
    notices = _lies("THIRD_PARTY_NOTICES.md")
    for begriff in ("PyMuPDF", "AGPL-3.0", "deu.traineddata", "Apache-2.0", "spaCy",
                    "de_core_news_md", "tkinterdnd2", "MIT"):
        assert begriff in notices


def test_github_action():
    text = _lies(".github/workflows/tests.yml")
    for begriff in ("ubuntu-latest", "windows-latest", "pytest", "--only-binary=:all:",
                    "TESSDATA_PREFIX", 'python-version: "3.12"', "requirements.txt"):
        assert begriff in text
    yaml = pytest.importorskip("yaml")
    daten = yaml.safe_load(text)
    assert "pytest" in daten["jobs"]
    assert set(daten["jobs"]["pytest"]["strategy"]["matrix"]["os"]) == {"ubuntu-latest", "windows-latest"}


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


def test_readme_tabelle_skript_ohne_schreiben():
    lauf = subprocess.run([sys.executable, "-W", "ignore", str(WURZEL / "werkzeuge" / "readme_tabelle.py")],
                          capture_output=True, text=True, timeout=60, cwd=str(WURZEL))
    assert lauf.returncode == 0, lauf.stderr
    assert lauf.stdout.startswith("| Kategorie |")
