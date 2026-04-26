@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================
echo   TUNTUN — Health Check
echo ============================================
echo.

set "FAIL_COUNT=0"

:: ---- Python detection: prefer .venv ----
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    echo [OK] .venv найден
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON=python"
        echo [WARN] .venv не найден — используется системный Python
    ) else (
        echo [FAIL] Python не найден
        exit /b 1
    )
)

:: ---- .env ----
if exist ".env" (
    echo [OK] .env существует
) else (
    echo [FAIL] .env не найден — скопируй .env.example в .env и заполни ключи
    set /a FAIL_COUNT+=1
)

:: ---- Python version ----
for /f "tokens=2 delims= " %%v in ('"!PYTHON!" --version 2^>^&1') do echo [OK] Python: %%v

:: ---- Imports ----
"!PYTHON!" -c "import aiogram, openai, aiosqlite, apscheduler, openpyxl, pytz, aiofiles, dotenv; print('[OK] Все зависимости доступны')" 2>&1
if errorlevel 1 (
    echo [FAIL] Ошибка импортов — запусти: .venv\Scripts\pip install -r requirements.txt
    set /a FAIL_COUNT+=1
)

:: ---- Token check ----
"!PYTHON!" -c "
import os, sys
from dotenv import load_dotenv
load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('BOT_TOKEN', '')
key = os.getenv('OPENAI_API_KEY', '')
fails = 0
if not token:
    print('[FAIL] TELEGRAM_BOT_TOKEN не задан в .env')
    fails += 1
else:
    print(f'[OK] TELEGRAM_BOT_TOKEN: ...{token[-6:]}')
if not key:
    print('[FAIL] OPENAI_API_KEY не задан в .env')
    fails += 1
else:
    print(f'[OK] OPENAI_API_KEY: ...{key[-6:]}')
sys.exit(fails)
" 2>&1
if errorlevel 1 set /a FAIL_COUNT+=1

:: ---- Database ----
"!PYTHON!" -c "
import asyncio, sys
async def check():
    from bot.db.database import db
    await db.init()
    import aiosqlite, config
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
        tables = [r[0] for r in await cur.fetchall()]
    expected = ['users', 'tasks', 'reminders', 'dynamic_sections', 'dynamic_records', 'message_logs']
    missing = [t for t in expected if t not in tables]
    if missing:
        print(f'[FAIL] Отсутствуют таблицы: {missing}')
        sys.exit(1)
    else:
        print(f'[OK] База данных: {len(tables)} таблиц')
asyncio.run(check())
" 2>&1
if errorlevel 1 set /a FAIL_COUNT+=1

:: ---- Storage folders ----
for %%d in (storage storage\photos storage\voice storage\documents storage\exports storage\backups logs) do (
    if exist "%%d" (
        echo [OK] %%d
    ) else (
        echo [WARN] %%d отсутствует — будет создана при запуске бота
    )
)

echo.
if !FAIL_COUNT! GTR 0 (
    echo [RESULT] FAIL — %FAIL_COUNT% critical error(s) found
    echo ============================================
    exit /b 1
) else (
    echo [RESULT] OK — все проверки пройдены
    echo ============================================
    exit /b 0
)
