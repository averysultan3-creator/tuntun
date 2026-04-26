@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title TUNTUN — Server

echo ============================================================
echo   TUNTUN — Deploy ^& Run (live logs)
echo ============================================================
echo.

cd /d "%~dp0"

:: ---- Logs dir ----
if not exist "logs" mkdir "logs"
set "LOGFILE=logs\deploy.log"

:: ---- Python detection ----
set "PYTHON="
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    if "%%a"=="PYTHON_EXE" set "PYTHON=%%b"
)
if not defined PYTHON (
    if exist ".venv\Scripts\python.exe" (
        set "PYTHON=.venv\Scripts\python.exe"
    ) else if exist "C:\Python312\python.exe" (
        set "PYTHON=C:\Python312\python.exe"
    ) else if exist "C:\Python311\python.exe" (
        set "PYTHON=C:\Python311\python.exe"
    ) else if exist "C:\Python310\python.exe" (
        set "PYTHON=C:\Python310\python.exe"
    ) else (
        set "PYTHON=python"
    )
)
echo [INFO] Python: %PYTHON%

:: ---- .env check ----
if not exist ".env" (
    echo [ERROR] .env not found!
    pause
    exit /b 1
)

:: ---- git pull ----
echo.
echo [GIT] Pulling latest code...
git fetch origin >nul 2>&1
git pull origin main 2>&1
if errorlevel 1 (
    echo [WARN] git pull failed — running with current code
)

:: ---- pip install ----
echo.
echo [PIP] Installing dependencies...
"%PYTHON%" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [WARN] pip install had errors — continuing anyway
)

:: ---- init DB ----
echo.
echo [DB] Initializing database...
"%PYTHON%" main.py --init-db
if errorlevel 1 (
    echo [ERROR] --init-db failed!
    pause
    exit /b 1
)

:: ---- Kill old instance if running ----
if exist "bot.pid" (
    set /p OLD_PID=<"bot.pid"
    echo [INFO] Stopping old instance (PID !OLD_PID!)...
    "%PYTHON%" run_background.py stop >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:: ---- Run bot in THIS window (live logs) ----
echo.
echo ============================================================
echo   Bot is starting. Logs appear below. Press Ctrl+C to stop.
echo ============================================================
echo.
"%PYTHON%" main.py
echo.
echo [INFO] Bot stopped.
pause
