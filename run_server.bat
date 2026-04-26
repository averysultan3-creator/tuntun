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

:: ---- Stop old instance if running ----
"%PYTHON%" run_background.py stop >nul 2>&1
timeout /t 2 /nobreak >nul

:: ---- Start bot in background (PID tracked, logs -> logs\runtime.log) ----
echo.
"%PYTHON%" run_background.py start
if errorlevel 1 (
    echo [ERROR] Failed to start bot
    pause
    exit /b 1
)

:: ---- Wait for bot to create log file ----
echo [INFO] Waiting for bot to start...
timeout /t 3 /nobreak >nul
if not exist "logs\runtime.log" echo. > "logs\runtime.log"

:: ---- Tail logs in this window (Ctrl+C to stop tailing, bot keeps running) ----
echo.
echo ============================================================
echo   Live logs (bot runs in background). Ctrl+C = stop tailing.
echo   auto_update.bat restarts bot automatically on new commits.
echo ============================================================
echo.
powershell -NoProfile -Command "$f='logs\runtime.log'; while (-not (Test-Path $f)) { Start-Sleep 1 }; Get-Content $f -Wait -Tail 50"
echo.
echo [INFO] Log tailing stopped. Bot is still running in background.
echo [INFO] To stop bot:  stop.bat
echo [INFO] To see logs:  type logs\runtime.log
pause
