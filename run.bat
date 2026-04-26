@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   TUNTUN — Run (Auto Setup + Start)
echo ============================================
echo.

:: First run: setup if .venv missing
if not exist ".venv\Scripts\activate.bat" (
    echo [*] Первый запуск — выполняю setup...
    call setup.bat
    if errorlevel 1 exit /b 1
    echo.
    echo Заполни .env и запусти run.bat снова.
    exit /b 0
)

:: Check .env exists and has token
if not exist ".env" (
    call setup.bat
    if errorlevel 1 exit /b 1
    echo Заполни .env и запусти run.bat снова.
    exit /b 0
)

:: All good — start
call start.bat
