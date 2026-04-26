@echo off
chcp 65001 >nul
setlocal

:: ============================================================
:: install_bot_task.bat — Register TUNTUN_BOT in Task Scheduler
:: Runs the bot automatically at Windows startup.
:: Requires: Run as Administrator
:: ============================================================

echo ============================================
echo   TUNTUN — Install Bot Startup Task
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

set "TASK_NAME=TUNTUN_BOT"
set "BAT_PATH=%~dp0start.bat"
set "WORK_DIR=%~dp0"

:: Remove trailing backslash from WORK_DIR
if "%WORK_DIR:~-1%"=="\" set "WORK_DIR=%WORK_DIR:~0,-1%"

:: Delete existing task if present (ignore errors)
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Create task: runs start.bat at system startup, as SYSTEM, in WORK_DIR
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "cmd /c \"%BAT_PATH%\"" ^
    /sc ONSTART ^
    /ru SYSTEM ^
    /rl HIGHEST ^
    /delay 0000:30 ^
    /f

if errorlevel 1 (
    echo [ERROR] Failed to create scheduled task "%TASK_NAME%".
    pause
    exit /b 1
)

:: Set working directory via XML patch (schtasks doesn't accept /wd on all Windows versions)
schtasks /query /tn "%TASK_NAME%" /xml > "%TEMP%\tuntun_bot_task.xml" 2>nul
powershell -NoProfile -Command ^
    "(Get-Content '%TEMP%\tuntun_bot_task.xml') -replace '(<WorkingDirectory>).*?(</WorkingDirectory>)', '$1%WORK_DIR%$2' | Set-Content '%TEMP%\tuntun_bot_task.xml'"
powershell -NoProfile -Command ^
    "if (-not ((Get-Content '%TEMP%\tuntun_bot_task.xml') -match '<WorkingDirectory>')) { (Get-Content '%TEMP%\tuntun_bot_task.xml') -replace '(<Command>)', \"<WorkingDirectory>%WORK_DIR%</WorkingDirectory>`n      `$1\" | Set-Content '%TEMP%\tuntun_bot_task.xml' }"
schtasks /create /tn "%TASK_NAME%" /xml "%TEMP%\tuntun_bot_task.xml" /f >nul 2>&1

echo [OK] Task "%TASK_NAME%" created. Bot will start at Windows boot.
echo.
echo To verify: schtasks /query /tn "%TASK_NAME%"
echo.
