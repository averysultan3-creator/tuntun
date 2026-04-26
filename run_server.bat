@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title TUNTUN — Server

echo ============================================================
echo   TUNTUN — One-Click Deploy ^& Run
echo ============================================================
echo.

cd /d "%~dp0"
if not exist "logs" mkdir "logs"

:: ================================================================
:: 1. PYTHON — ищем везде через PowerShell
:: ================================================================
set "PYTHON="

:: Сначала проверяем PYTHON_EXE в .env
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="PYTHON_EXE" set "PYTHON=%%b"
    )
)

:: Ищем python.exe во всех профилях и стандартных местах
if not defined PYTHON (
    for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "$paths = @('C:\Python312\python.exe','C:\Python311\python.exe','C:\Python310\python.exe') + (Get-ChildItem 'C:\Users\*\AppData\Local\Programs\Python\*\python.exe' -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty FullName); $found = $paths ^| Where-Object { Test-Path $_ } ^| Select-Object -First 1; if ($found) { $found } else { '' }" 2^>nul`) do (
        if not "%%p"=="" set "PYTHON=%%p"
    )
)

:: Последний вариант — python из PATH
if not defined PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
)

if not defined PYTHON (
    echo.
    echo [ERROR] Python не найден! Установи с https://python.org
    echo         Или добавь в .env: PYTHON_EXE=C:\путь\к\python.exe
    pause
    exit /b 1
)
echo [OK] Python: %PYTHON%

:: ================================================================
:: 2. .ENV CHECK
:: ================================================================
if not exist ".env" (
    echo.
    echo [СТОП] Файл .env не найден в папке: %~dp0
    echo        Скопируй .env из D:\AackREF\TUNTUN\.env сюда.
    pause
    exit /b 1
)
echo [OK] .env найден

:: ================================================================
:: 3. GIT PULL
:: ================================================================
echo.
echo [GIT] Обновляем код...
where git >nul 2>&1
if not errorlevel 1 (
    git config pull.rebase false >nul 2>&1
    git pull origin main
) else (
    echo [WARN] git не найден — пропускаем pull
)

:: ================================================================
:: 4. PIP INSTALL
:: ================================================================
echo.
echo [PIP] Устанавливаем зависимости...
"%PYTHON%" -m pip install -q --upgrade pip >nul 2>&1
"%PYTHON%" -m pip install -q -r requirements.txt
if errorlevel 1 echo [WARN] pip: некоторые пакеты не установились

:: ================================================================
:: 5. INIT DB
:: ================================================================
echo.
echo [DB] Инициализация БД...
"%PYTHON%" main.py --init-db
if errorlevel 1 (
    echo [ERROR] --init-db упал!
    pause
    exit /b 1
)

:: ================================================================
:: 6. RESTART BOT
:: ================================================================
echo.
echo [BOT] Перезапуск...
"%PYTHON%" run_background.py stop >nul 2>&1
timeout /t 2 /nobreak >nul
"%PYTHON%" run_background.py start
if errorlevel 1 (
    echo [ERROR] Бот не запустился!
    pause
    exit /b 1
)
echo [OK] Бот запущен

:: ================================================================
:: 7. LIVE LOGS
:: ================================================================
echo.
echo ============================================================
echo   Логи в реальном времени. Ctrl+C = выйти (бот работает).
echo ============================================================
echo.

:waitlog
if not exist "logs\runtime.log" (
    timeout /t 1 /nobreak >nul
    goto waitlog
)

powershell -NoProfile -Command "Get-Content 'logs\runtime.log' -Wait -Tail 50"

echo.
echo Бот работает в фоне. Для остановки: stop.bat
pause
