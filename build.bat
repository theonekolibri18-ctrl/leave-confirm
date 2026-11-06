@echo off
REM ChessLens lokal bauen (Windows). Voraussetzung: Python 3.11 oder 3.12 installiert.
REM Ergebnis: dist\ChessLens\ChessLens.exe
setlocal
cd /d "%~dp0"

echo [1/4] Python-Pakete installieren ...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :fail

echo [2/4] Stockfish laden ...
if not exist stockfish mkdir stockfish
if not exist stockfish\stockfish-windows-x86-64-avx2.exe (
  powershell -NoProfile -ExecutionPolicy Bypass -File build\get_stockfish.ps1 || goto :fail
)

echo [3/4] Bauen ...
python -m PyInstaller build\chesslens.spec --noconfirm || goto :fail

echo [4/4] Selbsttest ...
start /wait "" dist\ChessLens\ChessLens.exe --selftest
if errorlevel 1 goto :fail
type chesslens-selftest.txt

echo.
echo Fertig: dist\ChessLens\ChessLens.exe
exit /b 0

:fail
echo.
echo Build fehlgeschlagen.
exit /b 1
