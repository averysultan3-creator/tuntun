@echo off
chcp 65001 >nul
setlocal

:: ============================================================
:: uninstall_tasks.bat — Remove both TUNTUN scheduled tasks
:: Requires: Run as Administrator
:: ============================================================

echo ============================================
echo   TUNTUN — Uninstall Scheduled Tasks
echo ============================================
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This script requires Administrator privileges.
    pause
    exit /b 1
)

schtasks /delete /tn "TUNTUN_BOT" /f >nul 2>&1
if errorlevel 1 (
    echo [INFO] TUNTUN_BOT task not found (already removed)
) else (
    echo [OK] TUNTUN_BOT task removed
)

schtasks /delete /tn "TUNTUN_AUTO_UPDATE" /f >nul 2>&1
if errorlevel 1 (
    echo [INFO] TUNTUN_AUTO_UPDATE task not found (already removed)
) else (
    echo [OK] TUNTUN_AUTO_UPDATE task removed
)

echo.
echo Done. Bot and updater tasks removed from Task Scheduler.
pause
