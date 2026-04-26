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

:: Ищем через PowerShell: стандартные пути + все профили пользователей
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command ^
    "$paths = @('C:\Python313\python.exe','C:\Python312\python.exe','C:\Python311\python.exe','C:\Python310\python.exe') + (Get-ChildItem 'C:\Users\*\AppData\Local\Programs\Python\*\python.exe' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName); ($paths | Where-Object { Test-Path $_ } | Select-Object -First 1)" 2^>nul`) do (
    if not "%%p"=="" set "PYTHON=%%p"
)

:: Если PowerShell не нашёл — пробуем PATH
if not defined PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%x in ('where python') do if not defined PYTHON set "PYTHON=%%x"
    )
)

if not defined PYTHON (
    echo.
    echo [ERROR] Python не найден!
    echo         Установи Python 3.10+ с https://python.org
    echo         При установке ОБЯЗАТЕЛЬНО отметь "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
echo [OK] Python: %PYTHON%
echo.

:: ================================================================
:: 2. GIT CLONE / PULL
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
    if not exist "%DIR%" md "%DIR%"
    git clone "%REPO%" "%DIR%"
    if errorlevel 1 (
        echo [ERROR] git clone не удался! Проверь интернет.
        pause
        exit /b 1
    )
    echo [OK] Клонировано
) else (
    echo [GIT] Обновляем код...
    cd /d "%DIR%"
    git config pull.rebase false >nul 2>&1
    git fetch origin main >nul 2>&1
    git reset --hard origin/main >nul 2>&1
    echo [OK] Код обновлён
)

cd /d "%DIR%"
if not exist "logs" mkdir "logs"
echo.

:: ================================================================
:: 3. .ENV
:: ================================================================
if not exist ".env" (
    echo ============================================================
    echo   ПЕРВЫЙ ЗАПУСК — введи два ключа ^(один раз навсегда^)
    echo ============================================================
    echo.
    echo   Где взять ключи:
    echo   Telegram: https://t.me/BotFather  -^>  /mybots -^>  API Token
    echo   OpenAI:   https://platform.openai.com/api-keys
    echo.
    set /p "TG=  TELEGRAM_BOT_TOKEN : "
    set /p "OAI=  OPENAI_API_KEY       : "

    if "!TG!"=="" (
        echo [ERROR] Токен Telegram не может быть пустым!
        pause
        exit /b 1
    )
    if "!OAI!"=="" (
        echo [ERROR] OpenAI API ключ не может быть пустым!
        pause
        exit /b 1
    )
    echo.
    (
        echo TELEGRAM_BOT_TOKEN=!TG!
        echo OPENAI_API_KEY=!OAI!
        echo OPENAI_MODEL=gpt-4o-mini
        echo OPENAI_MODEL_ROUTER=gpt-4o-mini
        echo OPENAI_MODEL_CHAT=gpt-4o-mini
        echo OPENAI_MODEL_REASONING=gpt-4o
        echo OPENAI_MODEL_VISION=gpt-4o-mini
        echo OPENAI_MODEL_TRANSCRIBE=whisper-1
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
    echo [OK] .env найден — проверяю ключи...

    :: Читаем токен и API ключ для проверки на пустоту
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="TELEGRAM_BOT_TOKEN" set "CHECK_TG=%%b"
        if "%%a"=="OPENAI_API_KEY" set "CHECK_OAI=%%b"
    )
    if "!CHECK_TG!"=="" (
        echo.
        echo [WARN] TELEGRAM_BOT_TOKEN пустой в .env!
        echo        Открой .env и вставь токен бота.
        echo.
        pause
        exit /b 1
    )
    if "!CHECK_OAI!"=="" (
        echo.
        echo [WARN] OPENAI_API_KEY пустой в .env!
        echo        Открой .env и вставь ключ с platform.openai.com
        echo.
        pause
        exit /b 1
    )
    echo [OK] Ключи заполнены
)
echo.

:: ================================================================
:: 4. PIP
:: ================================================================
echo [PIP] Устанавливаем зависимости...
"%PYTHON%" -m pip install --upgrade pip -q >nul 2>&1
"%PYTHON%" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [WARN] pip вернул ошибку — пробуем без --quiet...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Не удалось установить зависимости!
        pause
        exit /b 1
    )
)
echo [OK] Зависимости установлены
echo.

:: ================================================================
:: 5. INIT DB (не критично — продолжаем даже при ошибке)
:: ================================================================
echo [DB] Инициализация БД...
"%PYTHON%" main.py --init-db >nul 2>&1
if errorlevel 1 (
    echo [WARN] init-db вернул ошибку — возможно БД уже инициализирована
) else (
    echo [OK] БД готова
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
    echo.
    echo [ERROR] Бот не запустился!
    echo         Смотри logs\runtime.log для деталей.
    echo.
    :: Показываем последние строки лога если есть
    if exist "logs\runtime.log" (
        echo --- Последние строки лога ---
        powershell -NoProfile -Command "Get-Content 'logs\runtime.log' -Tail 20"
        echo -----------------------------
    )
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

:: Ждём появления лога (до 15 сек)
set /a WAIT=0
:waitlog
if not exist "logs\runtime.log" (
    if !WAIT! geq 15 (
        echo [WARN] Лог не появился за 15 сек — что-то пошло не так
        pause
        exit /b 1
    )
    timeout /t 1 /nobreak >nul
    set /a WAIT+=1
    goto waitlog
)

powershell -NoProfile -Command "Get-Content 'logs\runtime.log' -Wait -Tail 50"

echo.
echo [INFO] Бот работает в фоне. Для остановки: stop.bat
pause
