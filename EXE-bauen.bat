@echo off
chcp 65001 >nul
title PDF-Anonymisierer - EXE bauen
setlocal
cd /d "%~dp0"

REM ==============================================================
REM  Baut einen eigenstaendigen Programmordner (onedir) mit
REM  PDF-Anonymisierer.exe fuer Kollegen ohne Python - inklusive
REM  Sprachmodell und OCR-Sprachdatei. Empfaenger brauchen KEIN
REM  Tesseract und keine Installation.
REM  Reines ASCII + CRLF, keine verzoegerte Variablenerweiterung.
REM ==============================================================

echo ============================================================
echo   PDF-Anonymisierer - EXE bauen
echo ============================================================
echo.

if not exist "pdf_anonymisierer.py" goto fehler_unvollstaendig
if not exist "tessdata\deu.traineddata" goto fehler_unvollstaendig
if not exist "werkzeuge\version_info.txt" goto fehler_unvollstaendig

REM --- Python finden (dasselbe wie Installieren.bat) --------------
set "PY="
set "KAND="
if exist ".python_pfad.txt" set /p KAND=<".python_pfad.txt"
if defined KAND set "KAND=%KAND:pythonw.exe=python.exe%"
if defined KAND if exist "%KAND%" set "PY=%KAND%"
if not defined PY (
    for /f "delims=" %%i in ('py -3 -X utf8 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
)
if not defined PY (
    for /f "delims=" %%i in ('python -X utf8 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
)
if not defined PY goto fehler_kein_python
if not exist "%PY%" goto fehler_kein_python
echo Verwende Python: "%PY%"
"%PY%" -c "import struct,sys;sys.exit(0 if struct.calcsize('P')==8 else 1)" >nul 2>&1
if errorlevel 1 goto fehler_32bit

REM --- [1/4] Pakete ------------------------------------------------
echo [1/4] Pruefe Pakete und PyInstaller ...
"%PY%" -m pip install --only-binary=:all: --disable-pip-version-check -r requirements.txt -r requirements-dev.txt
if errorlevel 1 goto fehler_pakete

REM --- [2/4] Voraussetzungen fuer den Bau ------------------------
echo [2/4] Pruefe Sprachmodell und OCR-Sprachdatei ...
"%PY%" -W ignore -c "import de_core_news_md, fitz, tkinterdnd2"
if errorlevel 1 goto fehler_modell
set "VERSION="
"%PY%" -c "from anonymisierer import __version__;open(r'%TEMP%\pdfanon_version.txt','w').write(__version__)"
if exist "%TEMP%\pdfanon_version.txt" set /p VERSION=<"%TEMP%\pdfanon_version.txt"
del "%TEMP%\pdfanon_version.txt" >nul 2>&1
if not defined VERSION set "VERSION=dev"
echo       Version %VERSION%
set "ICON="
if exist "icon.ico" set "ICON=--icon icon.ico"
if not defined ICON echo       Kein icon.ico im Ordner - die EXE bekommt das Standard-Symbol.

REM --- [3/4] PyInstaller ----------------------------------------
echo [3/4] Baue den Programmordner ^(dauert einige Minuten^) ...
REM onedir statt onefile: startet schneller, entpackt nichts nach %%TEMP%%,
REM weniger Virenscanner-Fehlalarme. tkinterdnd2 und spaCy haben eigene
REM PyInstaller-Hooks; nur das Sprachmodell braucht --collect-all.
"%PY%" -m PyInstaller --noconfirm --clean --onedir --windowed ^
    --name PDF-Anonymisierer ^
    --add-data "tessdata;tessdata" ^
    --collect-all de_core_news_md ^
    --exclude-module spacy.tests ^
    --version-file werkzeuge\version_info.txt ^
    %ICON% ^
    pdf_anonymisierer.py
if errorlevel 1 goto fehler_bau
if not exist "dist\PDF-Anonymisierer\PDF-Anonymisierer.exe" goto fehler_bau
if not exist "dist\PDF-Anonymisierer\_internal\tessdata\deu.traineddata" goto fehler_tessdata

REM --- [4/4] ZIP ---------------------------------------------------
echo [4/4] Packe dist\PDF-Anonymisierer-%VERSION%-windows-x64.zip ...
if exist "dist\PDF-Anonymisierer-%VERSION%-windows-x64.zip" del "dist\PDF-Anonymisierer-%VERSION%-windows-x64.zip"
powershell -NoProfile -NonInteractive -Command "Compress-Archive -Path 'dist\PDF-Anonymisierer' -DestinationPath 'dist\PDF-Anonymisierer-%VERSION%-windows-x64.zip' -CompressionLevel Optimal"
if not exist "dist\PDF-Anonymisierer-%VERSION%-windows-x64.zip" (
    echo       HINWEIS: ZIP konnte nicht erstellt werden ^(PowerShell gesperrt?^).
    echo       Den Ordner dist\PDF-Anonymisierer dann von Hand packen ^(Rechtsklick ^> Senden an ^> ZIP^).
)

echo.
echo ============================================================
echo   Fertig: dist\PDF-Anonymisierer\PDF-Anonymisierer.exe
echo   ZIP:    dist\PDF-Anonymisierer-%VERSION%-windows-x64.zip
echo ============================================================
echo   Weitergabe an Kollegen:
echo   - Die ZIP ueber Netzlaufwerk, OneDrive/SharePoint oder USB weitergeben
echo     ^(nicht per E-Mail: Outlook blockiert .exe, auch in ZIPs^).
echo   - Empfaenger entpacken den Ordner z. B. nach Dokumente und starten
echo     PDF-Anonymisierer.exe darin. Keine Installation, KEIN Tesseract noetig -
echo     Sprachmodell und OCR-Sprachdatei stecken im Ordner.
echo   - Der ganze Ordner gehoert zusammen; nur die .exe allein laeuft nicht.
echo.
echo   Hinweise zu Warnungen:
echo   - Windows SmartScreen meldet beim ersten Start "Der Computer wurde durch
echo     Windows geschuetzt": "Weitere Informationen" - "Trotzdem ausfuehren".
echo     Das kommt bei jedem neuen Build wieder, weil die EXE nicht signiert ist.
echo   - Dauerhaft verschwindet die Warnung nur mit einer Code-Signatur
echo     ^(Zertifikat eines Herausgebers oder Azure Trusted Signing, kostenpflichtig^):
echo       signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^^
echo         /a dist\PDF-Anonymisierer\PDF-Anonymisierer.exe
echo   - In verwalteten Firmennetzen ^(AppLocker, Defender-Richtlinien^) muss die
echo     IT die EXE ggf. freigeben; bei Virenscanner-Fehlalarm die Datei beim
echo     Hersteller als Fehlalarm melden.
echo   - Die EXE laeuft nur auf 64-Bit-Windows ^(x64^); auf ARM64-Geraeten nur
echo     unter Windows 11 in der x64-Emulation.
echo   - Lizenz: Der Ordner enthaelt PyMuPDF ^(AGPL-3.0^). Bei Weitergabe an
echo     Dritte THIRD_PARTY_NOTICES.md mitgeben ^(liegt in diesem Ordner^).
pause
exit /b 0


:fehler_unvollstaendig
echo FEHLER: Dateien fehlen ^(pdf_anonymisierer.py, tessdata\deu.traineddata oder
echo werkzeuge\version_info.txt^). Bitte den kompletten Ordner verwenden.
pause
exit /b 1

:fehler_kein_python
echo FEHLER: Python nicht gefunden - bitte zuerst "Installieren.bat" ausfuehren.
pause
exit /b 1

:fehler_32bit
echo FEHLER: Dieses Python ist 32-Bit. Fuer den Bau wird 64-Bit-Python ^(x64^) benoetigt.
pause
exit /b 1

:fehler_pakete
echo.
echo FEHLER: Pakete konnten nicht installiert werden ^(Meldung oben^).
echo Ursachen wie bei Installieren.bat: kein Internet, Firmen-Proxy/TLS-Pruefung,
echo ARM64/32-Bit, fehlende Schreibrechte.
pause
exit /b 1

:fehler_modell
echo.
echo FEHLER: Sprachmodell, PyMuPDF oder tkinterdnd2 lassen sich nicht laden.
echo Ohne Sprachmodell wuerde die EXE KEINE Namen erkennen - deshalb wird nicht gebaut.
echo Bitte "Installieren.bat" ausfuehren und die Meldungen dort beachten.
pause
exit /b 1

:fehler_bau
echo.
echo FEHLER beim Bauen - die Meldungen von PyInstaller stehen oben.
echo Haeufig: Virenscanner blockiert den Ordner build\ oder dist\ ^(Ausnahme eintragen
echo oder den Ordner nach Dokumente verschieben^), oder zu wenig Speicherplatz ^(ca. 1 GB^).
pause
exit /b 1

:fehler_tessdata
echo.
echo FEHLER: Die OCR-Sprachdatei fehlt im gebauten Ordner ^(_internal\tessdata^).
echo Bitte pruefen, ob tessdata\deu.traineddata im Projektordner liegt, und erneut bauen.
pause
exit /b 1
