@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title TUNTUN — Install ^& Run

echo ============================================================
echo   TUNTUN — Fresh Install ^& Run
echo ============================================================
echo.

:: ================================================================
:: 1. PYTHON
:: ================================================================
set "PYTHON="

for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "$paths = @('C:\Python312\python.exe','C:\Python311\python.exe','C:\Python310\python.exe') + (Get-ChildItem 'C:\Users\*\AppData\Local\Programs\Python\*\python.exe' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName); $f = $paths | Where-Object { Test-Path $_ } | Select-Object -First 1; if ($f) { $f }" 2^>nul`) do set "PYTHON=%%p"

if not defined PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
)

if not defined PYTHON (
    echo [ERROR] Python не найден!
    echo         Установи Python 3.10+ с https://python.org
    echo         При установке отметь "Add Python to PATH"
    pause & exit /b 1
)
echo [OK] Python: %PYTHON%

:: ================================================================
:: 2. GIT CLONE / PULL
:: ================================================================
set "REPO=https://github.com/averysultan3-creator/tuntun.git"
set "DIR=C:\Users\Sasha\Documents\Bots\TUNTUN"

where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git не найден! Установи с https://git-scm.com
    pause & exit /b 1
)

if not exist "%DIR%\.git" (
    echo.
    echo [GIT] Клонируем репозиторий...
    git clone %REPO% "%DIR%"
    if errorlevel 1 (
        echo [ERROR] git clone не удался!
        pause & exit /b 1
    )
)

cd /d "%DIR%"
if not exist "logs" mkdir "logs"

echo.
echo [GIT] Обновляем код...
git config pull.rebase false >nul 2>&1
git pull origin main

:: ================================================================
:: 3. .ENV — создаём если нет
:: ================================================================
if not exist ".env" (
    echo.
    echo ============================================================
    echo   Первый запуск — нужно ввести два ключа.
    echo   Это делается ОДИН РАЗ. Потом .env сохранится на сервере.
    echo ============================================================
    echo.
    set /p "TG=  TELEGRAM_BOT_TOKEN: "
    set /p "OAI=  OPENAI_API_KEY:      "
    echo.
    (
        echo TELEGRAM_BOT_TOKEN=!TG!
        echo OPENAI_API_KEY=!OAI!
        echo OPENAI_MODEL=gpt-4o-mini
        echo OPENAI_MODEL_ROUTER=gpt-4o-mini
        echo OPENAI_MODEL_CHAT=gpt-4o
        echo OPENAI_MODEL_REASONING=gpt-4o
        echo OPENAI_MODEL_VISION=gpt-4o
        echo OPENAI_TRANSCRIBE_MODEL=whisper-1
        echo OPENAI_MODEL_EMBEDDINGS=text-embedding-3-small
        echo DATABASE_PATH=tuntun.db
        echo TIMEZONE=Europe/Warsaw
        echo ADMIN_TELEGRAM_IDS=
        echo GIT_BRANCH=main
        echo AUTO_UPDATE_ENABLED=true
        echo AUTO_UPDATE_INTERVAL_MINUTES=2
    ) > ".env"
    echo [OK] .env создан
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
    pause & exit /b 1
)

:: ================================================================
:: 6. START BOT
:: ================================================================
echo.
echo [BOT] Запускаем...
"%PYTHON%" run_background.py stop >nul 2>&1
timeout /t 2 /nobreak >nul
"%PYTHON%" run_background.py start
if errorlevel 1 (
    echo [ERROR] Бот не запустился!
    pause & exit /b 1
)
echo [OK] Бот запущен!

:: ================================================================
:: 7. LIVE LOGS
:: ================================================================
echo.
echo ============================================================
echo   Всё работает. Логи ниже.
echo   Ctrl+C = выйти из просмотра (бот продолжит работать)
echo ============================================================
echo.

:waitlog
if not exist "logs\runtime.log" ( timeout /t 1 /nobreak >nul & goto waitlog )

powershell -NoProfile -Command "Get-Content 'logs\runtime.log' -Wait -Tail 50"

echo.
echo Бот работает в фоне. Для остановки запусти stop.bat
pause
