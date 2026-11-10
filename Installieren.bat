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

REM Offline-Weg fuer das Sprachmodell: Liegt diese Datei im Programmordner, wird das
REM Modell daraus installiert - ohne github.com. Der Name passt zur Adresse in
REM requirements.txt (tests\test_auslieferung.py prueft das).
set "MODELL_WHL=de_core_news_md-3.8.0-py3-none-any.whl"
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
if /i "%ARCH%"=="ARM64" echo       HINWEIS: ARM64-Prozessor erkannt - ungetestet; die Pakete gibt es auch fuer ARM64, die Installation wird versucht.
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
    echo       Fuer ARM64 gibt es alle Pakete als fertige Wheels ^(Python 3.11 bis 3.15,
    echo       PyMuPDF 1.28^). Getestet ist das Programm auf ARM64 aber nicht - bei
    echo       Problemen die EXE-Version nutzen ^(laeuft unter Windows 11 in der x64-Emulation^).
)
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 "%PY%" -m ensurepip --default-pip >nul 2>&1
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 goto fehler_kein_pip

REM --- Schritt 3: Pakete installieren ---------------------------
echo [3/5] Installiere Pakete ^(PyMuPDF, spaCy, tkinterdnd2, deutsches Sprachmodell^) ...
REM Vorab-Pruefung: Ist schon alles in passender Version installiert, laeuft pip gar nicht
REM erst. pip wuerde das Sprachmodell (Paket per URL, 44 MB) sonst bei JEDEM Lauf neu laden
REM und ohne Zugang zu github.com scheitern - obwohl alles installiert ist.
REM Die Versionsgrenzen muessen zu requirements.txt passen (tests\test_auslieferung.py).
"%PY%" -W ignore -c "import fitz, spacy, tkinterdnd2, de_core_news_md, re, sys; from importlib.metadata import version as v; t = lambda n: tuple(int(x) for x in re.findall(r'\d+', v(n))[:3]); sys.exit(0 if (1,24,10) <= t('pymupdf') < (3,) and (3,8) <= t('spacy') < (3,9) and (3,8) <= t('de_core_news_md') < (3,9) and t('tkinterdnd2') >= (0,4) else 1)" >nul 2>&1
if not errorlevel 1 (
    echo       Pakete und Sprachmodell sind schon in passender Version installiert -
    echo       kein Download noetig.
    goto pakete_ok
)
if exist "%MODELL_WHL%" (
    echo       Datei %MODELL_WHL% im Programmordner gefunden:
    echo       das Sprachmodell wird daraus installiert, ohne github.com.
    goto pakete_einzeln
)
echo       Beim ersten Mal werden ca. 170 MB geladen - das dauert einige Minuten.
echo       Nur fertige Pakete ^(--only-binary^): es wird nichts aus Quelltext gebaut.
"%PY%" -m pip install --only-binary=:all: --disable-pip-version-check -r requirements.txt
if not errorlevel 1 goto pakete_ok

echo.
echo       Das hat nicht geklappt. Zweiter Versuch: erst die Pakete einzeln von PyPI,
echo       dann das Sprachmodell ueber "spacy download". Achtung: auch das laedt von
echo       github.com - es hilft bei einer Stoerung, nicht bei gesperrtem github.com.
:pakete_einzeln
"%PY%" -m pip install --only-binary=:all: --disable-pip-version-check "pymupdf>=1.24.10,<3" "spacy>=3.8,<3.9" "tkinterdnd2>=0.4"
if errorlevel 1 goto fehler_pakete
if exist "%MODELL_WHL%" goto modell_offline
"%PY%" -m spacy download de_core_news_md
if errorlevel 1 goto fehler_modell
goto pakete_ok

:modell_offline
REM --no-index: pip sucht nur in diesem Ordner (--find-links .), nicht im Internet.
"%PY%" -m pip install --only-binary=:all: --disable-pip-version-check --no-index --find-links . de_core_news_md
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
echo   noch einmal ausfuehren ^(geht dann schnell, ohne Download^).
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
REM Geeignet = Python 3.10 bis 3.15, 64-Bit, mit tkinter. Ein ARM64-Python erst ab 3.11:
REM fuer ARM64 mit Python 3.10 gibt es kein spaCy-Paket (dann wird 3.12 installiert).
if not exist "%~1" goto :eof
"%~1" -c "import sys,struct,sysconfig,tkinter;arm=sysconfig.get_platform().endswith('arm64');sys.exit(0 if (3,11 if arm else 10)<=sys.version_info[:2]<(3,16) and struct.calcsize('P')==8 else 1)" >nul 2>&1
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
echo   - "No matching distribution found": meist erreicht pip pypi.org nicht ^(Proxy,
echo     siehe oben^); seltener fehlt fuer dieses Python bzw. diesen Prozessor ein
echo     fertiges Paket ^(z. B. ARM64 mit Python 3.10^)
echo     -^> Python 3.12 ^(64-Bit^) installieren oder die EXE-Version nutzen.
echo   - Keine Schreibrechte / Virenscanner greift ein ^("PermissionError", "Access is denied"^)
echo     -^> Ordner z. B. nach Dokumente verschieben und erneut starten.
echo   Fuer Rueckfragen: "%PY%" werkzeuge\pruefe_installation.py ausfuehren
echo   und die Ausgabe mitschicken.
pause
exit /b 1

:fehler_modell
echo.
echo ============================================================
echo   FEHLER: Das deutsche Sprachmodell konnte nicht installiert werden.
echo ============================================================
echo   Ohne Sprachmodell gibt es KEINE Namenserkennung - Personennamen blieben
echo   im Dokument stehen. Deshalb ist die Installation NICHT abgeschlossen.
echo   Das Modell kommt von github.com ^(auch "spacy download" laedt von dort^).
echo   Abhilfe, wenn github.com im Firmennetz gesperrt ist:
echo   a^) einmalig ueber ein anderes Netz ^(z. B. Handy-Hotspot^) installieren, ODER
echo   b^) Offline-Weg: an einem anderen Rechner die Datei
echo      %MODELL_WHL% ^(44 MB^) laden - die Adresse steht
echo      in requirements.txt in der Zeile "de_core_news_md @ ..." -, die Datei
echo      unveraendert in DIESEN Ordner legen und Installieren.bat erneut starten.
echo      Das Modell wird dann ohne Internet aus der Datei installiert.
echo   Firmen-Proxy / TLS-Pruefung ^("CERTIFICATE_VERIFY_FAILED"^)
echo     -^> IT fragen oder die fertige EXE-Version nutzen ^(siehe README^).
echo   Bereits installierte Pakete bleiben erhalten und werden nicht neu geladen.
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
