@echo off
REM =====================================================================
REM  ChessLens aus dem Quellcode starten (ohne eigene .exe)
REM  Laeuft ueber ein signiertes Python -> Smart App Control blockiert nichts.
REM  Einfach doppelklicken. Beim ersten Mal dauert es ein paar Minuten
REM  (Pakete + Stockfish werden geladen), danach startet es sofort.
REM =====================================================================
setlocal EnableDelayedExpansion
title ChessLens
cd /d "%~dp0"

echo.
echo  ====== ChessLens ======
echo.

REM --- 1) Python finden (muss installiert sein) -------------------------
set "PY="
where py  >nul 2>&1 && set "PY=py -3"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )

if not defined PY (
  echo  Python ist nicht installiert.
  echo.
  echo  Ich versuche, es ueber den Windows-Paketmanager zu installieren
  echo  ^(das ist von Microsoft signiert und wird nicht blockiert^)...
  echo.
  where winget >nul 2>&1
  if errorlevel 1 (
    echo  Winget ist nicht verfuegbar.
    echo  Bitte Python einmalig von https://www.python.org/downloads/ installieren
    echo  ^(beim Setup Haken bei "Add python.exe to PATH" setzen^), dann diese
    echo  Datei erneut doppelklicken.
    echo.
    pause
    exit /b 1
  )
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  echo.
  echo  Python wurde installiert. Bitte dieses Fenster schliessen und
  echo  ChessLens-starten.bat noch einmal doppelklicken.
  echo.
  pause
  exit /b 0
)

echo  Python gefunden: %PY%

REM --- 2) Quellcode holen (einmalig) ------------------------------------
set "SRC=%LOCALAPPDATA%\ChessLens-src"
set "ZIPURL=https://github.com/theonekolibri18-ctrl/leave-confirm/archive/refs/heads/chesslens.zip"

if not exist "%SRC%\run_chesslens.py" (
  echo  Lade ChessLens-Quellcode...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$zip=Join-Path $env:TEMP 'chesslens-src.zip';" ^
    "Invoke-WebRequest -Uri '%ZIPURL%' -OutFile $zip;" ^
    "$tmp=Join-Path $env:TEMP 'chesslens-src';" ^
    "if(Test-Path $tmp){Remove-Item -Recurse -Force $tmp};" ^
    "Expand-Archive -Path $zip -DestinationPath $tmp -Force;" ^
    "$inner=Get-ChildItem -Path $tmp -Directory | Select-Object -First 1;" ^
    "if(Test-Path '%SRC%'){Remove-Item -Recurse -Force '%SRC%'};" ^
    "Move-Item -Path $inner.FullName -Destination '%SRC%';"
  if errorlevel 1 (
    echo  Download fehlgeschlagen. Internetverbindung pruefen und erneut versuchen.
    pause
    exit /b 1
  )
)

cd /d "%SRC%"

REM --- 3) Virtuelle Umgebung + Pakete (einmalig) ------------------------
if not exist ".venv\Scripts\python.exe" (
  echo  Richte Arbeitsumgebung ein...
  %PY% -m venv .venv
)
set "VPY=.venv\Scripts\python.exe"

if not exist ".venv\.ready" (
  echo  Installiere Pakete ^(einmalig, dauert ein paar Minuten^)...
  "%VPY%" -m pip install --upgrade pip >nul
  "%VPY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo  Paketinstallation fehlgeschlagen.
    pause
    exit /b 1
  )
  echo ok> ".venv\.ready"
)

REM --- 4) Stockfish holen (einmalig) -----------------------------------
if not exist "stockfish\stockfish-windows-x86-64-avx2.exe" (
  echo  Lade Stockfish ^(Schach-Engine^)...
  powershell -NoProfile -ExecutionPolicy Bypass -File "build\get_stockfish.ps1"
  if errorlevel 1 (
    echo  Stockfish-Download fehlgeschlagen.
    pause
    exit /b 1
  )
)

REM --- 5) Starten -------------------------------------------------------
echo.
echo  Starte ChessLens...
start "" "%VPY%" run_chesslens.py
exit /b 0
