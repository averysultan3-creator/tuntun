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
:: 1. PYTHON DETECTION
:: ================================================================
set "PYTHON="

:: Check .env override first
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="PYTHON_EXE" set "PYTHON=%%b"
    )
)

if not defined PYTHON (
    for %%p in (
        ".venv\Scripts\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
        "C:\Python310\python.exe"
    ) do (
        if not defined PYTHON (
            if exist %%p set "PYTHON=%%~p"
        )
    )
)

if not defined PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
)

if not defined PYTHON (
    echo [ERROR] Python не найден!
    echo         Установи Python 3.10+ с https://python.org
    echo         или добавь в .env строку: PYTHON_EXE=C:\путь\к\python.exe
    pause
    exit /b 1
)

echo [OK] Python: %PYTHON%

:: ================================================================
:: 2. .ENV CHECK / SETUP
:: ================================================================
if not exist ".env" (
    echo.
    echo [SETUP] Файл .env не найден. Создаём...
    echo.
    set /p "TG_TOKEN=  Введи TELEGRAM_BOT_TOKEN: "
    set /p "OAI_KEY=  Введи OPENAI_API_KEY:      "
    echo.

    if not defined TG_TOKEN (
        echo [ERROR] Токен не введён. Прерывание.
        pause
        exit /b 1
    )
    if not defined OAI_KEY (
        echo [ERROR] API ключ не введён. Прерывание.
        pause
        exit /b 1
    )

    (
        echo TELEGRAM_BOT_TOKEN=!TG_TOKEN!
        echo OPENAI_API_KEY=!OAI_KEY!
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

    echo [OK] .env создан.
)

:: ================================================================
:: 3. GIT PULL
:: ================================================================
echo.
echo [GIT] Обновляем код...
where git >nul 2>&1
if errorlevel 1 (
    echo [WARN] git не найден — работаем с текущим кодом
) else (
    git config pull.rebase false >nul 2>&1
    git pull origin main 2>&1
)

:: ================================================================
:: 4. PIP INSTALL
:: ================================================================
echo.
echo [PIP] Устанавливаем зависимости...
"%PYTHON%" -m pip install --quiet --upgrade pip >nul 2>&1
"%PYTHON%" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [WARN] pip: возможны ошибки — продолжаем...
)

:: ================================================================
:: 5. INIT DB
:: ================================================================
echo.
echo [DB] Инициализация базы данных...
"%PYTHON%" main.py --init-db
if errorlevel 1 (
    echo [ERROR] --init-db завершился с ошибкой!
    pause
    exit /b 1
)

:: ================================================================
:: 6. STOP OLD INSTANCE
:: ================================================================
echo.
echo [BOT] Останавливаем старый процесс (если есть)...
"%PYTHON%" run_background.py stop >nul 2>&1
timeout /t 2 /nobreak >nul

:: ================================================================
:: 7. START BOT
:: ================================================================
echo [BOT] Запускаем...
"%PYTHON%" run_background.py start
if errorlevel 1 (
    echo [ERROR] Не удалось запустить бота!
    pause
    exit /b 1
)

:: ================================================================
:: 8. LIVE LOGS
:: ================================================================
echo.
echo ============================================================
echo   Бот запущен. Логи в реальном времени ниже.
echo   Ctrl+C = остановить просмотр логов (бот продолжит работать)
echo   Для полной остановки: stop.bat
echo ============================================================
echo.

:: Wait for log file to be created
:waitlog
if not exist "logs\runtime.log" (
    timeout /t 1 /nobreak >nul
    goto waitlog
)

powershell -NoProfile -Command "Get-Content 'logs\runtime.log' -Wait -Tail 50"

echo.
echo [INFO] Просмотр логов остановлен. Бот продолжает работать в фоне.
pause
