@echo off
chcp 65001 >nul
title PDF-Anonymisierer - EXE bauen
setlocal
pushd "%~dp0" || goto fehler_ordner

REM ==============================================================
REM  Baut einen eigenstaendigen Programmordner (onedir) mit
REM  PDF-Anonymisierer.exe fuer Kollegen ohne Python - inklusive
REM  Sprachmodell, OCR-Sprachdatei, Visual-C++-Laufzeit und
REM  Lizenztexten. Empfaenger brauchen KEIN Tesseract und keine
REM  Installation.
REM  Reines ASCII + CRLF, keine verzoegerte Variablenerweiterung.
REM  pushd statt "cd /d", damit es auch auf einer per UNC-Pfad
REM  geoeffneten Netzwerkfreigabe geht; popd vor jedem "exit /b".
REM  Die GitHub-Action (.github\workflows\tests.yml, Job "exe")
REM  ruft genau diese Datei auf.
REM ==============================================================

echo ============================================================
echo   PDF-Anonymisierer - EXE bauen
echo ============================================================
echo.

if not exist "pdf_anonymisierer.py" goto fehler_unvollstaendig
if not exist "tessdata\deu.traineddata" goto fehler_unvollstaendig
if not exist "werkzeuge\version_info.txt" goto fehler_unvollstaendig
if not exist "LICENSE" goto fehler_unvollstaendig
if not exist "THIRD_PARTY_NOTICES.md" goto fehler_unvollstaendig
if not exist "README.md" goto fehler_unvollstaendig
if not exist "licenses\AGPL-3.0.txt" goto fehler_unvollstaendig

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
REM Ohne Visual-C++-Laufzeit laesst sich PyMuPDF nicht laden ("DLL load failed"): Die Vorab-Pruefung
REM schlug dann bei jedem Bau fehl, und pip lief jedes Mal vergeblich - deshalb vorher pruefen.
call :pruefe_vc_laufzeit
if defined VC_FEHLT goto fehler_vc_laufzeit

REM --- [1/4] Pakete ------------------------------------------------
echo [1/4] Pruefe Pakete und PyInstaller ...
REM Vorab-Pruefungen: pip laeuft nur, wenn etwas fehlt oder veraltet ist. Sonst wuerde
REM jeder Bau das 44-MB-Sprachmodell (Paket per URL) neu laden und ohne Zugang zu
REM github.com scheitern. Laufzeitpakete (wie Installieren.bat) und PyInstaller werden
REM getrennt geprueft: Fehlt nur PyInstaller - der erste Bau nach Installieren.bat -,
REM wird nur requirements-dev.txt installiert, ganz ohne github.com.
REM Die Versionsgrenzen muessen zu requirements*.txt passen (tests\test_auslieferung.py).
"%PY%" -W ignore -c "import fitz, spacy, tkinterdnd2, de_core_news_md, re, sys; from importlib.metadata import version as v; t = lambda n: tuple(int(x) for x in re.findall(r'\d+', v(n))[:3]); sys.exit(0 if (1,24,10) <= t('pymupdf') < (3,) and (3,8) <= t('spacy') < (3,9) and (3,8) <= t('de_core_news_md') < (3,9) and t('tkinterdnd2') >= (0,4) else 1)" >nul 2>&1
if errorlevel 1 (
    echo       Laufzeitpakete fehlen oder sind veraltet - installiere requirements.txt ...
    "%PY%" -m pip install --only-binary=:all: --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto fehler_pakete
)
"%PY%" -W ignore -c "import PyInstaller, re, sys; from importlib.metadata import version as v; t = lambda n: tuple(int(x) for x in re.findall(r'\d+', v(n))[:3]); sys.exit(0 if (6,10) <= t('pyinstaller') < (7,) else 1)" >nul 2>&1
if errorlevel 1 (
    echo       PyInstaller fehlt oder ist veraltet - installiere requirements-dev.txt ...
    "%PY%" -m pip install --only-binary=:all: --disable-pip-version-check -r requirements-dev.txt
    if errorlevel 1 goto fehler_pakete
)
echo       Pakete, Sprachmodell und PyInstaller sind vorhanden.

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
    --add-data "anonymisierer\daten;anonymisierer\daten" ^
    --collect-submodules anonymisierer.detektoren ^
    --collect-all de_core_news_md ^
    --exclude-module spacy.tests ^
    --version-file werkzeuge\version_info.txt ^
    %ICON% ^
    pdf_anonymisierer.py
if errorlevel 1 goto fehler_bau
if not exist "dist\PDF-Anonymisierer\PDF-Anonymisierer.exe" goto fehler_bau
if not exist "dist\PDF-Anonymisierer\_internal\tessdata\deu.traineddata" goto fehler_tessdata
REM Die Visual-C++-Laufzeit (msvcp140.dll, vcruntime140_1.dll) packt PyInstaller selbst in den
REM Ordner _internal. Deshalb laeuft die EXE auch auf Rechnern ohne "Visual C++ Redistributable" -
REM anders als die Skript-Version. Damit das so bleibt, wird es hier geprueft.
if not exist "dist\PDF-Anonymisierer\_internal\msvcp140.dll" goto fehler_vc_im_ordner
if not exist "dist\PDF-Anonymisierer\_internal\vcruntime140_1.dll" goto fehler_vc_im_ordner

REM Lizenz- und Hilfetexte in den Programmordner: Er wird weitergegeben, und fuer
REM PyMuPDF/MuPDF (AGPL-3.0) muessen Empfaenger Lizenztext und Quellenhinweis bekommen.
REM PyInstaller nimmt keine Lizenzdateien mit, und das PyMuPDF-Paket enthaelt selbst nur
REM einen Einzeiler - deshalb liegt der volle AGPL-Text als licenses\AGPL-3.0.txt bei.
copy /y "LICENSE" "dist\PDF-Anonymisierer\LICENSE.txt" >nul
copy /y "THIRD_PARTY_NOTICES.md" "dist\PDF-Anonymisierer\THIRD_PARTY_NOTICES.md" >nul
copy /y "README.md" "dist\PDF-Anonymisierer\README.md" >nul
if not exist "dist\PDF-Anonymisierer\licenses" mkdir "dist\PDF-Anonymisierer\licenses"
copy /y "licenses\AGPL-3.0.txt" "dist\PDF-Anonymisierer\licenses\AGPL-3.0.txt" >nul
if not exist "dist\PDF-Anonymisierer\LICENSE.txt" goto fehler_lizenz
if not exist "dist\PDF-Anonymisierer\THIRD_PARTY_NOTICES.md" goto fehler_lizenz
if not exist "dist\PDF-Anonymisierer\README.md" goto fehler_lizenz
if not exist "dist\PDF-Anonymisierer\licenses\AGPL-3.0.txt" goto fehler_lizenz

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
echo     Sprachmodell, OCR-Sprachdatei und Wortlisten stecken im Ordner.
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
echo   - Lizenz: Der Ordner enthaelt PyMuPDF/MuPDF ^(AGPL-3.0^). LICENSE.txt,
echo     THIRD_PARTY_NOTICES.md und der AGPL-Text ^(licenses\AGPL-3.0.txt^) liegen
echo     im Ordner und damit in der ZIP - beim Weitergeben nicht herausnehmen.
pause
popd
exit /b 0


:pruefe_vc_laufzeit
REM Wie in Installieren.bat (Begruendung dort): setzt VC_FEHLT auf die DLLs der Visual-C++-Laufzeit, die
REM das gefundene Python nicht laden kann (nicht gesetzt = beide ladbar oder nicht pruefbar). Python laedt
REM sie zur Probe selbst - mit derselben Suchreihenfolge wie PyMuPDF, also auch aus dem Ordner von python.exe.
REM Exit-Code: 10 + 1 (msvcp140.dll fehlt) + 2 (vcruntime140_1.dll fehlt), jeder andere: nicht pruefbar.
set "VC_FEHLT="
"%PY%" werkzeuge\pruefe_installation.py --vc-laufzeit >nul 2>&1
if errorlevel 14 goto :eof
if errorlevel 13 set "VC_FEHLT=msvcp140.dll, vcruntime140_1.dll"
if errorlevel 13 goto :eof
if errorlevel 12 set "VC_FEHLT=vcruntime140_1.dll"
if errorlevel 12 goto :eof
if errorlevel 11 set "VC_FEHLT=msvcp140.dll"
goto :eof


:fehler_ordner
REM pushd ist gescheitert: kein popd (es wuerde einen Eintrag des Aufrufers entfernen).
echo FEHLER: Der Projektordner laesst sich nicht als Arbeitsordner oeffnen:
echo   "%~dp0"
echo Liegt er auf einer Netzwerkfreigabe ^(\\server\freigabe\...^), konnte Windows ihr
echo keinen freien Laufwerksbuchstaben zuordnen, oder der Zugriff wurde verweigert
echo ^(die Meldung von Windows steht oben^). Loesung: den Ordner auf diesen Rechner
echo kopieren ^(z. B. nach Dokumente^) oder die Freigabe als Netzlaufwerk verbinden.
pause
exit /b 1

:fehler_unvollstaendig
echo FEHLER: Dateien fehlen ^(pdf_anonymisierer.py, tessdata\deu.traineddata,
echo werkzeuge\version_info.txt, LICENSE, THIRD_PARTY_NOTICES.md, README.md oder
echo licenses\AGPL-3.0.txt^). Bitte den kompletten Ordner verwenden.
pause
popd
exit /b 1

:fehler_kein_python
echo FEHLER: Python nicht gefunden - bitte zuerst "Installieren.bat" ausfuehren.
pause
popd
exit /b 1

:fehler_32bit
echo FEHLER: Dieses Python ist 32-Bit. Fuer den Bau wird 64-Bit-Python ^(x64^) benoetigt.
pause
popd
exit /b 1

:fehler_pakete
echo.
echo FEHLER: Pakete konnten nicht installiert werden ^(Meldung oben^).
echo Ursachen wie bei Installieren.bat: kein Internet, Firmen-Proxy/TLS-Pruefung,
echo fehlende Schreibrechte. Scheitert nur das Sprachmodell ^(github.com gesperrt^):
echo zuerst Installieren.bat ausfuehren - dort gibt es den Offline-Weg - und dann
echo EXE-bauen.bat erneut starten; vorhandene Pakete werden nicht neu geladen.
pause
popd
exit /b 1

:fehler_modell
echo.
echo FEHLER: Sprachmodell, PyMuPDF oder tkinterdnd2 lassen sich nicht laden.
echo Ohne Sprachmodell wuerde die EXE KEINE Namen erkennen - deshalb wird nicht gebaut.
echo Bitte "Installieren.bat" ausfuehren und die Meldungen dort beachten.
pause
popd
exit /b 1

:fehler_bau
echo.
echo FEHLER beim Bauen - die Meldungen von PyInstaller stehen oben.
echo Haeufig: Virenscanner blockiert den Ordner build\ oder dist\ ^(Ausnahme eintragen
echo oder den Ordner nach Dokumente verschieben^), oder zu wenig Speicherplatz ^(ca. 1 GB^).
pause
popd
exit /b 1

:fehler_tessdata
echo.
echo FEHLER: Die OCR-Sprachdatei fehlt im gebauten Ordner ^(_internal\tessdata^).
echo Bitte pruefen, ob tessdata\deu.traineddata im Projektordner liegt, und erneut bauen.
pause
popd
exit /b 1

:fehler_vc_laufzeit
echo.
echo FEHLER: Auf diesem Rechner fehlt die Visual-C++-Laufzeit von Microsoft ^(Python kann
echo %VC_FEHLT% nicht laden^). Ohne die "Microsoft Visual C++ 2015-2022 Redistributable (x64)" laesst sich
echo PyMuPDF nicht laden ^("DLL load failed"^) - so kann nicht gebaut werden, und die Pakete
echo erneut zu installieren hilft nicht. Abhilfe ^(einmalig, braucht Administratorrechte^):
echo zuerst Installieren.bat ausfuehren ^(bietet die Installation an^), oder
echo   winget install --id Microsoft.VCRedist.2015+.x64 -e
echo bzw. vc_redist.x64.exe von https://aka.ms/vs/17/release/vc_redist.x64.exe
pause
popd
exit /b 1

:fehler_vc_im_ordner
echo.
echo FEHLER: Im gebauten Ordner fehlt die Visual-C++-Laufzeit ^(_internal\msvcp140.dll
echo bzw. _internal\vcruntime140_1.dll^). Ohne sie startet die EXE nur auf Rechnern, auf
echo denen die "Microsoft Visual C++ 2015-2022 Redistributable (x64)" installiert ist.
echo PyInstaller packt beide sonst selbst ein - bitte die Meldungen von PyInstaller oben
echo pruefen und erneut bauen.
pause
popd
exit /b 1

:fehler_lizenz
echo.
echo FEHLER: Die Lizenz- und Hilfetexte konnten nicht nach dist\PDF-Anonymisierer
echo kopiert werden ^(Virenscanner? Schreibrechte?^). Ohne LICENSE.txt,
echo THIRD_PARTY_NOTICES.md und licenses\AGPL-3.0.txt darf der Ordner nicht an Dritte
echo weitergegeben werden ^(PyMuPDF/MuPDF stehen unter AGPL-3.0^).
pause
popd
exit /b 1
