@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   TUNTUN — Stop Bot
echo ============================================
echo.

:: ---- Python detection ----
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else if exist "C:\Python310\python.exe" (
    set "PYTHON=C:\Python310\python.exe"
) else (
    set "PYTHON=python"
)

"%PYTHON%" run_background.py stop
