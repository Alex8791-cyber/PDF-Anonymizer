@echo off
chcp 65001 >nul
title PDF-Anonymisierer - Installation
setlocal
cd /d "%~dp0"

REM ==============================================================
REM  PDF-Anonymisierer - Einrichtung in EINEM Lauf
REM  Diese Datei ist absichtlich reines ASCII (ae/oe/ue) mit CRLF.
REM  Keine verzoegerte Variablenerweiterung: so bleiben "!" in Pfaden erhalten.
REM  Schritte: 1 Python finden/installieren, 2 Rechner pruefen,
REM            3 Pakete, 4 Pruefung, 5 Desktop-Verknuepfung.
REM ==============================================================

echo ============================================================
echo   PDF-Anonymisierer - Einrichtung
echo ============================================================
echo.
echo Dieses Fenster bitte offen lassen, bis "Fertig" erscheint.
echo.

if not exist "werkzeuge\verknuepfung.py" goto fehler_unvollstaendig
if not exist "requirements.txt" goto fehler_unvollstaendig
if not exist "tessdata\deu.traineddata" goto fehler_unvollstaendig
if not exist "pdf_anonymisierer.py" goto fehler_unvollstaendig

set "PY="
set "UNGEEIGNET="
set "ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "ARCH=%PROCESSOR_ARCHITEW6432%"

REM --- Schritt 1: Python finden oder installieren ---------------
echo [1/5] Suche Python ...
call :suche_python
if defined PY goto python_ok

echo       Kein passendes Python gefunden.
echo       Installiere Python 3.12 automatisch ^(nur fuer dieses Benutzerkonto, kein Admin noetig^) ...
if /i "%ARCH%"=="ARM64" echo       HINWEIS: ARM64-Prozessor erkannt - PyMuPDF/spaCy gibt es dafuer kaum; es wird trotzdem versucht.
where winget >nul 2>&1
if errorlevel 1 goto fehler_kein_winget
winget install --id Python.Python.3.12 -e --scope user --custom "InstallLauncherAllUsers=0" --accept-source-agreements --accept-package-agreements --disable-interactivity
if not "%errorlevel%"=="0" (
    echo       Erster Versuch fehlgeschlagen - zweiter Versuch mit Standardeinstellungen ...
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
)
REM Das frisch installierte Python steht noch nicht im PATH dieses Fensters,
REM deshalb wird es direkt in den bekannten Ordnern gesucht.
call :suche_python
if not defined PY goto fehler_kein_python

:python_ok
echo       Verwende: "%PY%"

REM --- Schritt 2: Rechner pruefen -------------------------------
echo [2/5] Pruefe Rechner ^(64-Bit, Prozessor, pip^) ...
"%PY%" -c "import platform,sys;sys.exit(4 if platform.machine().upper().startswith('ARM') else 0)"
if errorlevel 4 (
    echo       HINWEIS: ARM64-Prozessor ^(z. B. Snapdragon / Surface Pro X^) erkannt.
    echo       Dafuer gibt es PyMuPDF nur in einer aelteren Version und spaCy
    echo       eventuell gar nicht. ARM64 wird nicht unterstuetzt - es wird
    echo       trotzdem versucht; bei Fehlern ist das die Ursache.
)
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 "%PY%" -m ensurepip --default-pip >nul 2>&1
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 goto fehler_kein_pip

REM --- Schritt 3: Pakete installieren ---------------------------
echo [3/5] Installiere Pakete ^(PyMuPDF, spaCy, tkinterdnd2, deutsches Sprachmodell^) ...
echo       Beim ersten Mal werden ca. 300 MB geladen - das dauert einige Minuten.
echo       Nur fertige Pakete ^(--only-binary^): es wird nichts aus Quelltext gebaut.
"%PY%" -m pip install --only-binary=:all: --disable-pip-version-check -r requirements.txt
if not errorlevel 1 goto pakete_ok

echo.
echo       Das hat nicht geklappt. Zweiter Versuch: erst die Pakete, dann das
echo       Sprachmodell ueber spaCy ^(falls nur der GitHub-Download blockiert war^) ...
"%PY%" -m pip install --only-binary=:all: --disable-pip-version-check "pymupdf>=1.24,<3" "spacy>=3.8,<3.9" "tkinterdnd2>=0.4"
if errorlevel 1 goto fehler_pakete
"%PY%" -m spacy download de_core_news_md
if errorlevel 1 goto fehler_modell

:pakete_ok
REM --- Schritt 4: Installation pruefen --------------------------
echo [4/5] Pruefe die Installation ...
"%PY%" -W ignore -c "import fitz, spacy, tkinterdnd2, de_core_news_md"
if errorlevel 1 goto fehler_pruefung
echo       Pakete und Sprachmodell sind vorhanden.
echo       OCR-Sprachdatei: tessdata\deu.traineddata ^(wird mitgeliefert, keine Installation noetig^).

REM --- Schritt 5: Desktop-Verknuepfung ---------------------------
echo [5/5] Lege Verknuepfung auf dem Desktop an ...
"%PY%" -X utf8 werkzeuge\verknuepfung.py
if errorlevel 1 goto fehler_verknuepfung

echo.
echo ============================================================
echo   Fertig! Alles ist eingerichtet.
echo ============================================================
echo   Starten: Doppelklick auf "PDF-Anonymisierer" auf dem Desktop
echo            oder auf "Starten.bat" in diesem Ordner.
echo   Wird dieser Ordner spaeter verschoben: Installieren.bat einfach
echo   noch einmal ausfuehren ^(geht dann schnell^).
echo.
echo   Das Programm wird jetzt einmal gestartet ...
set "PYW=%PY:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PY%"
start "" "%PYW%" "%~dp0pdf_anonymisierer.py"
pause
exit /b 0


REM ==============================================================
REM  Unterprogramme
REM ==============================================================

:suche_python
REM Reihenfolge: Python-Launcher 3.12, Launcher neuestes 3.x, bekannte
REM Installationsordner, zuletzt "python" im PATH ^(Store-Alias faellt durch^).
set "PY="
call :kandidat_launcher -3.12
if defined PY goto :eof
call :kandidat_launcher -3
if defined PY goto :eof
for %%v in (312 313 314 315 311 310) do (
    if not defined PY call :kandidat_datei "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
    if not defined PY call :kandidat_datei "%ProgramFiles%\Python%%v\python.exe"
)
if defined PY goto :eof
call :kandidat_befehl python
goto :eof

:kandidat_launcher
set "KAND="
for /f "delims=" %%i in ('py %1 -X utf8 -c "import sys;print(sys.executable)" 2^>nul') do set "KAND=%%i"
if not defined KAND goto :eof
call :pruefe_kandidat "%KAND%"
goto :eof

:kandidat_befehl
set "KAND="
for /f "delims=" %%i in ('%1 -X utf8 -c "import sys;print(sys.executable)" 2^>nul') do set "KAND=%%i"
if not defined KAND goto :eof
call :pruefe_kandidat "%KAND%"
goto :eof

:kandidat_datei
if not exist "%~1" goto :eof
call :pruefe_kandidat "%~1"
goto :eof

:pruefe_kandidat
REM Geeignet = Python 3.10 bis 3.15, 64-Bit, mit tkinter.
if not exist "%~1" goto :eof
"%~1" -c "import sys,struct,tkinter;sys.exit(0 if (3,10)<=sys.version_info[:2]<(3,16) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if errorlevel 1 (
    echo       Ueberspringe "%~1" ^(zu alt/zu neu, 32-Bit oder ohne tkinter^).
    set "UNGEEIGNET=1"
    goto :eof
)
set "PY=%~1"
goto :eof


REM ==============================================================
REM  Fehlerausgaenge - "Fertig" erscheint hier nie, kein Autostart
REM ==============================================================

:fehler_unvollstaendig
echo.
echo FEHLER: Dateien fehlen ^(werkzeuge\verknuepfung.py, requirements.txt,
echo tessdata\deu.traineddata oder pdf_anonymisierer.py^).
echo Bitte die ZIP-Datei komplett entpacken ^(Rechtsklick ^> "Alle extrahieren"^)
echo und Installieren.bat aus dem entpackten Ordner starten - nicht aus der ZIP heraus.
pause
exit /b 1

:fehler_kein_winget
echo.
echo FEHLER: Python ist nicht installiert, und der Windows-Paketmanager "winget"
echo fehlt auf diesem Rechner ^(aeltere Windows-10-Version, LTSC, Server oder
echo per Richtlinie gesperrt^).
echo Loesung: Python 3.12 ^(64-Bit^) von https://www.python.org/downloads/windows/
echo laden ^("Windows installer (64-bit)"^), installieren - dabei den Haken
echo "Add python.exe to PATH" setzen - und danach Installieren.bat erneut starten.
pause
exit /b 1

:fehler_kein_python
echo.
echo FEHLER: Python konnte nicht automatisch installiert werden.
echo Moegliche Ursachen:
echo   - keine Internetverbindung oder Firmen-Proxy
echo   - winget / Microsoft Store ist per Richtlinie gesperrt
echo   - die Installation wurde abgebrochen ^(Benutzerkontensteuerung^)
echo   - "python" ist nur der Store-Alias von Windows ^(oeffnet den Store statt Python^)
echo     -^> Einstellungen ^> Apps ^> Erweiterte App-Einstellungen ^> Aliase fuer die
echo        App-Ausfuehrung: python.exe und python3.exe ausschalten
if defined UNGEEIGNET echo   - ein vorhandenes Python wurde uebersprungen ^(32-Bit, zu alt/zu neu oder ohne tkinter^)
echo Loesung: Python 3.12 ^(64-Bit^) von https://www.python.org/downloads/windows/
echo laden ^("Windows installer (64-bit)"^), installieren - dabei den Haken
echo "Add python.exe to PATH" setzen - und danach Installieren.bat erneut starten.
pause
exit /b 1

:fehler_kein_pip
echo.
echo FEHLER: Zu diesem Python gehoert kein "pip" ^(Paketverwaltung^).
echo Python von https://www.python.org/downloads/windows/ neu installieren
echo ^(Standardeinstellungen, Haken "Add python.exe to PATH"^) und erneut starten.
pause
exit /b 1

:fehler_pakete
echo.
echo ============================================================
echo   FEHLER: Die Pakete konnten nicht installiert werden.
echo ============================================================
echo   Die genaue Meldung steht oben in den letzten Zeilen von pip.
echo   Haeufige Ursachen und was hilft:
echo   - Kein Internet / Verbindung abgebrochen
echo     -^> Verbindung pruefen und Installieren.bat erneut starten.
echo   - Firmen-Proxy oder TLS-Pruefung ^("CERTIFICATE_VERIFY_FAILED", "ProxyError"^)
echo     -^> IT bitten, pypi.org, files.pythonhosted.org und github.com freizugeben,
echo        oder die fertige EXE-Version nutzen ^(siehe README, "Weitergabe"^).
echo   - ARM64-Geraet oder 32-Bit-Python ^("No matching distribution found"^)
echo     -^> unterstuetzt wird nur 64-Bit-Windows auf x64-Prozessoren.
echo   - Keine Schreibrechte / Virenscanner greift ein ^("PermissionError", "Access is denied"^)
echo     -^> Ordner z. B. nach Dokumente verschieben und erneut starten.
echo   Fuer Rueckfragen: "%PY%" werkzeuge\pruefe_installation.py ausfuehren
echo   und die Ausgabe mitschicken.
pause
exit /b 1

:fehler_modell
echo.
echo ============================================================
echo   FEHLER: Das deutsche Sprachmodell konnte nicht geladen werden.
echo ============================================================
echo   Ohne Sprachmodell gibt es KEINE Namenserkennung - Personennamen blieben
echo   im Dokument stehen. Deshalb ist die Installation NICHT abgeschlossen.
echo   Das Modell kommt von github.com. Haeufige Ursachen:
echo   - github.com ist im Firmennetz gesperrt
echo     -^> einmalig ueber ein anderes Netz ^(z. B. Handy-Hotspot^) installieren.
echo   - Firmen-Proxy / TLS-Pruefung ^("CERTIFICATE_VERIFY_FAILED"^)
echo     -^> IT fragen oder die fertige EXE-Version nutzen ^(siehe README^).
echo   Danach Installieren.bat erneut starten ^(bereits Installiertes wird nicht neu geladen^).
pause
exit /b 1

:fehler_pruefung
echo.
echo FEHLER: Die Pakete wurden installiert, lassen sich aber nicht laden.
echo Die Meldung steht oben. Typische Ursache: zwei Python-Installationen
echo durcheinander oder ein Virenscanner hat Dateien entfernt.
echo Fuer Rueckfragen: "%PY%" werkzeuge\pruefe_installation.py ausfuehren.
pause
exit /b 1

:fehler_verknuepfung
echo.
echo ============================================================
echo   Installation abgeschlossen - aber OHNE Desktop-Verknuepfung.
echo ============================================================
echo   Das Programm selbst ist einsatzbereit. Starten ueber Doppelklick auf
echo   "Starten.bat" in diesem Ordner ^(Rechtsklick darauf ^> "Senden an" ^>
echo   "Desktop (Verknuepfung erstellen)" legt eine eigene Verknuepfung an^).
echo   Ursache ist meist PowerShell, das durch Firmenrichtlinien eingeschraenkt ist.
pause
exit /b 1
