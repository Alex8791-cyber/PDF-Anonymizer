@echo off
chcp 65001 >nul
title PDF-Anonymisierer
cd /d "%~dp0"

REM Startet den PDF-Anonymisierer ohne Konsolenfenster (pythonw.exe).
REM Den Interpreter hat Installieren.bat in .python_pfad.txt hinterlegt;
REM fehlt die Datei, werden die ueblichen Installationsordner durchsucht.

set "PYW="
if exist ".python_pfad.txt" set /p PYW=<".python_pfad.txt"
if defined PYW if exist "%PYW%" goto start

set "PYW="
for %%v in (312 313 314 315 311 310) do (
    if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python%%v\pythonw.exe"
    if not defined PYW if exist "%ProgramFiles%\Python%%v\pythonw.exe" set "PYW=%ProgramFiles%\Python%%v\pythonw.exe"
)
if defined PYW goto start

where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw -3 "%~dp0pdf_anonymisierer.py"
    exit /b 0
)

echo Python wurde nicht gefunden. Bitte zuerst "Installieren.bat" ausfuehren.
pause
exit /b 1

:start
start "" "%PYW%" "%~dp0pdf_anonymisierer.py"
exit /b 0
