@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   TUNTUN — Live Logs  (Ctrl+C для выхода)
echo ============================================
echo.

if not exist "logs\runtime.log" (
    echo [INFO] Лог-файл ещё не создан.
    echo        Запусти start.bat и подожди пару секунд, затем открой снова.
    echo.
    pause
    exit /b 0
)

echo Показываю последние 50 строк + новые в реальном времени:
echo -------------------------------------------------------
powershell -NoProfile -Command "Get-Content 'logs\runtime.log' -Wait -Tail 50"
