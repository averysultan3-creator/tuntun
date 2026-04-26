@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================
echo   TUNTUN — Setup Script
echo ============================================
echo.

:: ---- Check Python ----
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python не найден в PATH.
    echo         Скачай Python 3.11+ с https://www.python.org/downloads/
    echo         При установке выбери "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python: %PYVER%

:: Warn if < 3.10
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PYMAJ=%%a
    set PYMIN=%%b
)
if %PYMAJ% LSS 3 (
    echo [ERROR] Нужен Python 3.10+
    pause
    exit /b 1
)
if %PYMAJ% EQU 3 if %PYMIN% LSS 10 (
    echo [ERROR] Нужен Python 3.10+, установлен %PYVER%
    pause
    exit /b 1
)

:: ---- Create virtual environment ----
if not exist ".venv" (
    echo [*] Создаю virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Не удалось создать venv
        pause
        exit /b 1
    )
    echo [OK] .venv создан
) else (
    echo [OK] .venv уже существует
)

:: ---- Activate venv ----
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Не удалось активировать .venv
    pause
    exit /b 1
)
echo [OK] .venv активирован

:: ---- Upgrade pip ----
echo [*] Обновляю pip...
python -m pip install --upgrade pip --quiet
echo [OK] pip обновлён

:: ---- Install requirements ----
echo [*] Устанавливаю зависимости...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Ошибка установки зависимостей
    pause
    exit /b 1
)
echo [OK] Зависимости установлены

:: ---- Create storage folders ----
echo [*] Создаю папки...
if not exist "storage"           mkdir storage
if not exist "storage\photos"    mkdir storage\photos
if not exist "storage\voice"     mkdir storage\voice
if not exist "storage\documents" mkdir storage\documents
if not exist "storage\exports"   mkdir storage\exports
if not exist "storage\backups"   mkdir storage\backups
if not exist "logs"              mkdir logs
echo [OK] Папки созданы

:: ---- Copy .env if missing ----
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] .env создан из .env.example
        echo.
        echo  *** ВАЖНО: открой .env и заполни TELEGRAM_BOT_TOKEN и OPENAI_API_KEY ***
        echo.
    ) else (
        echo [WARN] .env.example не найден, создаю пустой .env
        echo TELEGRAM_BOT_TOKEN=> .env
        echo OPENAI_API_KEY=>> .env
        echo OPENAI_MODEL=gpt-4o-mini>> .env
        echo TIMEZONE=Europe/Warsaw>> .env
        echo DATABASE_PATH=tuntun.db>> .env
    )
) else (
    echo [OK] .env уже существует
)

:: ---- Init database ----
echo [*] Инициализирую базу данных...
python -c "import asyncio; from bot.db.database import db; asyncio.run(db.init()); print('[OK] База данных инициализирована')"
if errorlevel 1 (
    echo [ERROR] Ошибка инициализации базы данных
    pause
    exit /b 1
)

:: ---- Check imports ----
echo [*] Проверяю импорты...
python -c "import aiogram; import openai; import aiosqlite; import apscheduler; import openpyxl; import pytz; print('[OK] Все импорты работают')"
if errorlevel 1 (
    echo [ERROR] Проблема с импортами
    pause
    exit /b 1
)

echo.
echo ============================================
echo   [OK] Setup завершён успешно!
echo ============================================
echo.
echo Следующий шаг:
echo   1. Открой файл .env
echo   2. Вставь TELEGRAM_BOT_TOKEN и OPENAI_API_KEY
echo   3. Запусти run.bat
echo.
pause
