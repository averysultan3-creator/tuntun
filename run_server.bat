@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title TUNTUN

echo ============================================================
echo   TUNTUN — Install ^& Run
echo ============================================================
echo.

:: ================================================================
:: 1. PYTHON
:: ================================================================
set "PYTHON="

for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "$paths = @('C:\Python313\python.exe','C:\Python312\python.exe','C:\Python311\python.exe','C:\Python310\python.exe') + (Get-ChildItem 'C:\Users\*\AppData\Local\Programs\Python\*\python.exe' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName); ($paths | Where-Object { Test-Path $_ } | Select-Object -First 1)" 2^>nul`) do (
    if not "%%p"=="" set "PYTHON=%%p"
)

if not defined PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 for /f "delims=" %%x in ('where python') do if not defined PYTHON set "PYTHON=%%x"
)

if not defined PYTHON (
    echo.
    echo [ERROR] Python не найден!
    echo         Установи Python 3.10+ с https://python.org
    echo         При установке ОБЯЗАТЕЛЬНО отметь "Add Python to PATH"
    pause
    exit /b 1
)
echo [OK] Python: %PYTHON%
echo.

:: ================================================================
:: 2. GIT
:: ================================================================
set "REPO=https://github.com/averysultan3-creator/tuntun.git"
set "DIR=C:\Users\Sasha\Documents\Bots\TUNTUN"

where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git не найден! Установи с https://git-scm.com/download/win
    pause
    exit /b 1
)

if not exist "%DIR%\.git" (
    echo [GIT] Клонируем репозиторий...
    git clone "%REPO%" "%DIR%"
    if errorlevel 1 (
        echo [ERROR] git clone не удался! Проверь интернет.
        pause
        exit /b 1
    )
    echo [OK] Репозиторий клонирован
) else (
    echo [GIT] Обновляем код...
    cd /d "%DIR%"
    git config pull.rebase false >nul 2>&1
    git pull origin main >nul 2>&1
    echo [OK] Код обновлён
)

cd /d "%DIR%"
if not exist "logs" mkdir "logs"

:: ================================================================
:: 3. .ENV
:: ================================================================
if not exist ".env" (
    echo.
    echo ============================================================
    echo   ПЕРВЫЙ ЗАПУСК — введи два ключа (один раз навсегда^)
    echo ============================================================
    echo.
    set /p "TG=  TELEGRAM_BOT_TOKEN : "
    set /p "OAI=  OPENAI_API_KEY       : "
    echo.
    (
        echo TELEGRAM_BOT_TOKEN=!TG!
        echo OPENAI_API_KEY=!OAI!
        echo OPENAI_MODEL=gpt-5.4-mini
        echo OPENAI_MODEL_ROUTER=gpt-5.4-mini
        echo OPENAI_MODEL_CHAT=gpt-5.4
        echo OPENAI_MODEL_REASONING=gpt-5.4
        echo OPENAI_MODEL_VISION=gpt-5.4
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
) else (
    :: Патчим старые имена моделей если нужно
    powershell -NoProfile -Command "(Get-Content '.env') -replace 'gpt-4o-mini','gpt-5.4-mini' -replace '=gpt-4o$','=gpt-5.4' | Set-Content '.env'" >nul 2>&1
    echo [OK] .env найден
)
echo.

:: ================================================================
:: 4. PIP
:: ================================================================
echo [PIP] Устанавливаем зависимости...
"%PYTHON%" -m pip install -q --upgrade pip >nul 2>&1
"%PYTHON%" -m pip install -q -r requirements.txt >nul 2>&1
echo [OK] Зависимости установлены
echo.

:: ================================================================
:: 5. INIT DB
:: ================================================================
echo [DB] Инициализация БД...
"%PYTHON%" main.py --init-db
if errorlevel 1 (
    echo [ERROR] Ошибка инициализации БД!
    pause
    exit /b 1
)
echo.

:: ================================================================
:: 6. STOP OLD + START BOT
:: ================================================================
echo [BOT] Останавливаем старый процесс...
"%PYTHON%" run_background.py stop >nul 2>&1
timeout /t 2 /nobreak >nul

echo [BOT] Запускаем бота...
"%PYTHON%" run_background.py start
if errorlevel 1 (
    echo [ERROR] Бот не запустился! Смотри логи выше.
    pause
    exit /b 1
)
echo.

:: ================================================================
:: 7. LIVE LOGS
:: ================================================================
echo ============================================================
echo   ВСЁ РАБОТАЕТ. Логи в реальном времени:
echo   Ctrl+C = выйти из логов ^(бот продолжит работать^)
echo ============================================================
echo.

:waitlog
if not exist "logs\runtime.log" (
    timeout /t 1 /nobreak >nul
    goto waitlog
)

powershell -NoProfile -Command "Get-Content 'logs\runtime.log' -Wait -Tail 50"

echo.
echo [INFO] Бот работает в фоне. Для остановки: stop.bat
pause
