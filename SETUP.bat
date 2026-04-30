@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title TUNTUN — Setup & Run

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║       TUNTUN — Setup and Launch              ║
echo  ║   Runs everything: install → config → start  ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: ================================================================
:: STEP 1 — Find Python
:: ================================================================
echo [1/6] Ищем Python...

set "PYTHON="
for %%p in (
    ".venv\Scripts\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "C:\Python313\python.exe"
) do (
    if not defined PYTHON (
        if exist "%%~p" set "PYTHON=%%~p"
    )
)
if not defined PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
    echo.
    echo [ERROR] Python не найден!
    echo Скачай с https://python.org/downloads и при установке
    echo отметь "Add Python to PATH", затем запусти SETUP.bat снова.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('"%PYTHON%" --version 2^>^&1') do set "PY_VER=%%v"
echo [OK] Python %PY_VER%: %PYTHON%

:: ================================================================
:: STEP 2 — Create/update virtualenv
:: ================================================================
echo.
echo [2/6] Настраиваем виртуальное окружение (.venv)...

if not exist ".venv\Scripts\python.exe" (
    echo      Создаём .venv...
    "%PYTHON%" -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Не удалось создать .venv
        pause
        exit /b 1
    )
    echo [OK] .venv создан
) else (
    echo [OK] .venv уже существует
)
set "PYTHON=.venv\Scripts\python.exe"

:: ================================================================
:: STEP 3 — Install dependencies
:: ================================================================
echo.
echo [3/6] Устанавливаем зависимости (pip install -r requirements.txt)...
"%PYTHON%" -m pip install --quiet --upgrade pip >nul 2>&1
"%PYTHON%" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [WARN] Некоторые пакеты не установились — проверь вывод выше
) else (
    echo [OK] Зависимости установлены
)

:: ================================================================
:: STEP 4 — Create/fill .env
:: ================================================================
echo.
echo [4/6] Настройка .env...

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo      .env создан из .env.example
    echo      Нужно ввести токены прямо сейчас:
    echo.

    :: --- TELEGRAM_BOT_TOKEN ---
    set "TG_TOKEN="
    :ask_tg
    set /p TG_TOKEN="  Telegram Bot Token (от @BotFather): "
    if "!TG_TOKEN!"=="" (
        echo      [!] Токен не может быть пустым
        goto ask_tg
    )

    :: --- OPENAI_API_KEY ---
    set "OAI_KEY="
    :ask_oai
    set /p OAI_KEY="  OpenAI API Key (sk-...): "
    if "!OAI_KEY!"=="" (
        echo      [!] Ключ не может быть пустым
        goto ask_oai
    )

    :: --- ADMIN_ID ---
    set "ADMIN_ID="
    set /p ADMIN_ID="  Твой Telegram User ID (число, можно оставить пустым): "

    :: Write values into .env using Python (avoids cmd escaping issues)
    "%PYTHON%" -c "
import re, sys
path = '.env'
content = open(path, 'r', encoding='utf-8').read()
replacements = {
    'TELEGRAM_BOT_TOKEN': r'''%TG_TOKEN%''',
    'OPENAI_API_KEY':     r'''%OAI_KEY%''',
    'ADMIN_TELEGRAM_IDS': r'''%ADMIN_ID%''',
}
for key, val in replacements.items():
    content = re.sub(rf'^({key}=).*$', rf'\g<1>{val}', content, flags=re.MULTILINE)
open(path, 'w', encoding='utf-8').write(content)
print('[OK] .env заполнен')
"
) else (
    echo [OK] .env уже существует — пропускаем

    :: Quick check: are required tokens set?
    "%PYTHON%" -c "
import os; from dotenv import load_dotenv; load_dotenv()
t = os.getenv('TELEGRAM_BOT_TOKEN','')
k = os.getenv('OPENAI_API_KEY','')
if not t: print('[WARN] TELEGRAM_BOT_TOKEN не задан в .env')
if not k: print('[WARN] OPENAI_API_KEY не задан в .env')
if t and k: print('[OK] Токены найдены в .env')
"
)

:: ================================================================
:: STEP 5 — Create dirs + init DB
:: ================================================================
echo.
echo [5/6] Создаём папки и инициализируем базу данных...

for %%d in (logs storage storage\photos storage\voice storage\documents storage\exports storage\backups credentials) do (
    if not exist "%%d" mkdir "%%d"
)

"%PYTHON%" main.py --init-db
if errorlevel 1 (
    echo [ERROR] Ошибка при инициализации базы данных
    pause
    exit /b 1
)
echo [OK] База данных инициализирована

:: ================================================================
:: STEP 6 — Health check + start
:: ================================================================
echo.
echo [6/6] Проверка установки...
call check.bat
if errorlevel 1 (
    echo.
    echo [ERROR] Проверка не прошла — исправь ошибки выше и запусти SETUP.bat снова
    pause
    exit /b 1
)

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   Установка завершена! Запускаю бота...      ║
echo  ║   Логи видны здесь + сохраняются в logs\     ║
echo  ║   Ctrl+C — остановить бота                   ║
echo  ╚══════════════════════════════════════════════╝
echo.
timeout /t 2 /nobreak >nul

:: Run bot in this window (visible logs)
"%PYTHON%" -u main.py

echo.
echo [EXIT] Бот остановлен.
pause
