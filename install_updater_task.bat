@echo off
chcp 65001 >nul
setlocal

:: ============================================================
:: install_updater_task.bat — Register TUNTUN_AUTO_UPDATE task
:: Runs auto_update.bat every N minutes (default: 2).
:: Requires: Run as Administrator
:: ============================================================

echo ============================================
echo   TUNTUN — Install Auto-Update Task
echo ============================================
echo.

:: Check admin rights
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This script requires Administrator privileges.
    echo         Right-click the file and choose "Run as administrator".
    pause
    exit /b 1
)

:: ---- Read AUTO_UPDATE_INTERVAL_MINUTES from .env (default 2) ----
set "INTERVAL=2"
if exist "%~dp0.env" (
    for /f "usebackq tokens=1,2 delims==" %%a in ("%~dp0.env") do (
        if "%%a"=="AUTO_UPDATE_INTERVAL_MINUTES" set "INTERVAL=%%b"
    )
)

set "TASK_NAME=TUNTUN_AUTO_UPDATE"
set "BAT_PATH=%~dp0auto_update.bat"
set "WORK_DIR=%~dp0"
if "%WORK_DIR:~-1%"=="\" set "WORK_DIR=%WORK_DIR:~0,-1%"

:: Delete existing task if present
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Create task: runs every INTERVAL minutes, starting now
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "cmd /c \"%BAT_PATH%\"" ^
    /sc MINUTE ^
    /mo %INTERVAL% ^
    /ru SYSTEM ^
    /rl HIGHEST ^
    /f

if errorlevel 1 (
    echo [ERROR] Failed to create scheduled task "%TASK_NAME%".
    pause
    exit /b 1
)

echo [OK] Task "%TASK_NAME%" created. Auto-update runs every %INTERVAL% minute(s).
echo.
echo To verify: schtasks /query /tn "%TASK_NAME%"
echo To change interval: edit AUTO_UPDATE_INTERVAL_MINUTES in .env
echo   then re-run this script.
echo.
