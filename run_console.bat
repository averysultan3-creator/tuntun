@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title TUNTUN — Console Mode

echo ============================================
echo   TUNTUN — Console (logs visible here)
echo   Logs also saved to: logs\app.log
echo   Press Ctrl+C to stop the bot
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
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

:: ---- .env check ----
if not exist ".env" (
    echo [ERROR] .env not found. Run SERVER_INSTALL_AND_RUN.bat first.
    pause
    exit /b 1
)

:: ---- Stop background instance if running ----
"%PYTHON%" run_background.py status >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Stopping background bot instance first...
    call stop.bat >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:: ---- Run bot directly in this window (stdout+stderr visible + saved to app.log) ----
echo [START] Bot starting...
echo.
"%PYTHON%" -u main.py

echo.
echo [EXIT] Bot stopped.
pause
