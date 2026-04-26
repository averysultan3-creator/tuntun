@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================
echo   TUNTUN — Start Bot
echo ============================================
echo.

:: ---- Python detection ----
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else if exist "C:\Python310\python.exe" (
    set "PYTHON=C:\Python310\python.exe"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found
        exit /b 1
    )
    set "PYTHON=python"
)

:: ---- .env check ----
if not exist ".env" (
    echo [ERROR] .env not found. Run SERVER_INSTALL_AND_RUN.bat first.
    exit /b 1
)

:: ---- Use run_background.py to start safely (no duplicate) ----
"%PYTHON%" run_background.py start
