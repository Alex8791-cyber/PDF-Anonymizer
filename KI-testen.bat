@echo off
chcp 65001 >nul
title PDF-Anonymisierer - KI-Verbindung testen

REM Prueft die Verbindung zu LM Studio (KI-Zweitpruefung) mit erfundenen Beispieldaten.
REM Den Interpreter hat Installieren.bat in .python_pfad.txt hinterlegt; fuer die Ausgabe im
REM Fenster wird python.exe statt pythonw.exe verwendet. Alle Pfade absolut (%~dp0), kein "cd".

set "PY="
if exist "%~dp0.python_pfad.txt" set /p PY=<"%~dp0.python_pfad.txt"
if defined PY set "PY=%PY:pythonw.exe=python.exe%"
if defined PY if exist "%PY%" goto start

set "PY="
for %%v in (312 313 314 315 311 310) do (
    if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
    if not defined PY if exist "%ProgramFiles%\Python%%v\python.exe" set "PY=%ProgramFiles%\Python%%v\python.exe"
)
if defined PY goto start

where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0werkzeuge\ki_test.py"
    pause
    exit /b 0
)

echo Python wurde nicht gefunden. Bitte zuerst "Installieren.bat" ausfuehren.
pause
exit /b 1

:start
"%PY%" "%~dp0werkzeuge\ki_test.py"
pause
exit /b 0
