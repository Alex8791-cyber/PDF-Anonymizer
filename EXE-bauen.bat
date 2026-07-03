@echo off
chcp 65001 >nul
title PDF-Anonymisierer - EXE bauen
cd /d "%~dp0"
echo Baut eine eigenstaendige PDF-Anonymisierer.exe zum Weitergeben.
echo.
set "PY="
py -3 -c "print(1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "print(1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo Python nicht gefunden - bitte zuerst "Installieren.bat" ausfuehren.
    pause
    exit /b 1
)
echo [1/2] Installiere PyInstaller ...
%PY% -m pip install pyinstaller pymupdf tkinterdnd2 spacy
%PY% -m spacy download de_core_news_md >nul 2>&1
echo [2/2] Baue die EXE ^(dauert einige Minuten^) ...
%PY% -m PyInstaller --onefile --windowed --name PDF-Anonymisierer ^
    --collect-all tkinterdnd2 ^
    --collect-all de_core_news_md ^
    --collect-all spacy ^
    pdf_anonymisierer.py
if errorlevel 1 (
    echo FEHLER beim Bauen - Meldungen oben pruefen.
    pause
    exit /b 1
)
echo.
echo Fertig: %~dp0dist\PDF-Anonymisierer.exe
echo Diese eine Datei an Kollegen weitergeben - keine Installation noetig.
echo WICHTIG: Fuer gescannte PDFs brauchen Kollegen zusaetzlich Tesseract-OCR:
echo   winget install UB-Mannheim.TesseractOCR
echo Hinweis: Windows SmartScreen kann beim ersten Start warnen
echo ^("Weitere Informationen" - "Trotzdem ausfuehren"^).
pause
