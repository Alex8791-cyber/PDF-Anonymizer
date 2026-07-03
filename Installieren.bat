@echo off
chcp 65001 >nul
title PDF-Anonymisierer - Installation
setlocal EnableDelayedExpansion

echo ============================================================
echo   PDF-Anonymisierer - Einrichtung
echo ============================================================
echo.
cd /d "%~dp0"

REM --- Schritt 1: Python finden --------------------------------
set "PY="
py -3 -c "print(1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "print(1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo Python wurde nicht gefunden. Automatische Installation wird versucht ...
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    echo.
    echo Bitte dieses Fenster schliessen und "Installieren.bat" ERNEUT starten.
    echo Falls es nicht klappt: Python von https://www.python.org installieren
    echo ^(Haken "Add python.exe to PATH" setzen!^).
    pause
    exit /b 1
)
echo [1/5] Python gefunden.

REM --- Schritt 2: Pakete installieren --------------------------
echo [2/5] Installiere Pakete ^(PyMuPDF, tkinterdnd2, spaCy^) ...
%PY% -m pip install --upgrade pip >nul 2>&1
%PY% -m pip install pymupdf tkinterdnd2 spacy
if errorlevel 1 (
    echo FEHLER bei der Paket-Installation. Internetverbindung pruefen, erneut starten.
    pause
    exit /b 1
)

REM --- Schritt 3: Deutsches Sprachmodell fuer die Namenserkennung ---
echo [3/5] Lade deutsches KI-Sprachmodell ^(einmalig, ca. 40 MB^) ...
%PY% -m spacy download de_core_news_md
if errorlevel 1 (
    echo.
    echo HINWEIS: Sprachmodell konnte nicht geladen werden.
    echo Das Programm laeuft trotzdem - nur die automatische NAMENS-Erkennung
    echo fehlt dann. Diese Datei spaeter einfach nochmal ausfuehren.
    echo.
)

REM --- Schritt 4: Desktop-Verknuepfung anlegen ------------------
echo [4/5] Installiere Tesseract-OCR ^(Texterkennung fuer gescannte PDFs^) ...
where tesseract >nul 2>&1
if errorlevel 1 (
    winget install --id UB-Mannheim.TesseractOCR -e --accept-source-agreements --accept-package-agreements
)
REM Deutsche OCR-Sprachdatei nachladen, falls sie fehlt
set "TDATA=%ProgramFiles%\Tesseract-OCR\tessdata"
if exist "%TDATA%" if not exist "%TDATA%\deu.traineddata" (
    echo Lade deutsche OCR-Sprachdatei ...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/tesseract-ocr/tessdata_fast/raw/main/deu.traineddata' -OutFile '%TDATA%\deu.traineddata'" 2>nul
    if not exist "%TDATA%\deu.traineddata" (
        echo HINWEIS: Sprachdatei konnte nicht automatisch geladen werden.
        echo Bitte diese Datei ggf. als Administrator erneut ausfuehren.
    )
)

[5/5] Lege Verknuepfung auf dem Desktop an ...
for /f "delims=" %%i in ('%PY% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%i"

set "PSF=%TEMP%\pdf_anonymisierer_verknuepfung.ps1"
> "%PSF%" echo $ws = New-Object -ComObject WScript.Shell
>>"%PSF%" echo $lnk = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\PDF-Anonymisierer.lnk')
>>"%PSF%" echo $lnk.TargetPath = '%PYW%'
>>"%PSF%" echo $lnk.Arguments = '"%~dp0pdf_anonymisierer.py"'
>>"%PSF%" echo $lnk.WorkingDirectory = '%~dp0'
>>"%PSF%" echo $lnk.Description = 'Dokumente fuer KI-Dienste anonymisieren'
>>"%PSF%" echo $lnk.Save()
powershell -NoProfile -ExecutionPolicy Bypass -File "%PSF%" >nul
del "%PSF%" >nul 2>&1

echo.
echo ============================================================
echo   Fertig! Auf dem Desktop liegt jetzt "PDF-Anonymisierer".
echo ============================================================
start "" "%PYW%" "%~dp0pdf_anonymisierer.py"
pause
