@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ============================================================
:: SERVER_INSTALL_AND_RUN.bat — TUNTUN Master Installer
::
:: Performs full fresh installation on a Windows server:
::   1. Checks Python 3.10+
::   2. Checks Git
::   3. Creates .venv
::   4. Installs pip requirements
::   5. Creates required folders
::   6. Checks/creates .env
::   7. Initialises database (--init-db)
::   8. Runs check.bat
::   9. Installs Windows Task Scheduler tasks
::  10. Starts the bot
::
:: Re-running this script is safe — it skips steps already done.
:: ============================================================

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║         TUNTUN — Server Install and Run                 ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: ================================================================
:: STEP 1 — Python check
:: ================================================================
echo [1/10] Checking Python...

:: Try .venv first (in case of re-run)
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    goto :python_ok
)

:: Try system Python
for %%P in (
    "C:\Python310\python.exe"
    "C:\Python311\python.exe"
    "C:\Python312\python.exe"
    "C:\Python313\python.exe"
) do (
    if exist %%P (
        set "PYTHON=%%~P"
        goto :python_found
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=python"
    goto :python_found
)

where python3 >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=python3"
    goto :python_found
)

echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
echo         Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1

:python_found
:: Check version >= 3.10
"%PYTHON%" -c "import sys; v=sys.version_info; exit(0 if v.major==3 and v.minor>=10 else 1)" 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.10 or higher is required.
    "%PYTHON%" --version
    pause
    exit /b 1
)

:python_ok
echo [OK] Python found: !PYTHON!

:: ================================================================
:: STEP 2 — Git check
:: ================================================================
echo [2/10] Checking Git...
where git >nul 2>&1
if errorlevel 1 (
    echo [WARN] Git not found. Auto-update will be disabled.
    echo        Install Git from https://git-scm.com if you want auto-updates.
    set "GIT_AVAILABLE=0"
) else (
    echo [OK] Git found.
    set "GIT_AVAILABLE=1"
)

:: ================================================================
:: STEP 3 — Create .venv
:: ================================================================
echo [3/10] Setting up virtual environment...

if exist ".venv\Scripts\python.exe" (
    echo [OK] .venv already exists — skipping
) else (
    echo [*] Creating .venv...
    "%PYTHON%" -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv
        pause
        exit /b 1
    )
    echo [OK] .venv created
)
set "PYTHON=.venv\Scripts\python.exe"

:: ================================================================
:: STEP 4 — Install dependencies
:: ================================================================
echo [4/10] Installing Python dependencies...

if not exist "requirements.txt" (
    echo [ERROR] requirements.txt not found. Cannot install dependencies.
    pause
    exit /b 1
)

"%PYTHON%" -m pip install --upgrade pip
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed!
    echo         Проверь интернет и посмотри ошибки выше.
    pause
    exit /b 1
)
echo [OK] Dependencies installed

:: ================================================================
:: STEP 5 — Create required folders
:: ================================================================
echo [5/10] Creating required folders...

for %%D in (
    "logs"
    "storage"
    "storage\photos"
    "storage\voice"
    "storage\documents"
    "storage\exports"
    "storage\backups"
) do (
    if not exist "%%~D" (
        mkdir "%%~D"
        echo [OK] Created %%~D
    )
)
echo [OK] All folders present

:: ================================================================
:: STEP 6 — .env check / creation
:: ================================================================
echo [6/10] Checking .env...

if exist ".env" (
    echo [OK] .env already exists — not touching it
) else (
    echo [*] .env not found — creating from .env.example...
    if not exist ".env.example" (
        echo [ERROR] .env.example not found. Cannot create .env.
        pause
        exit /b 1
    )
    copy ".env.example" ".env" >nul
    echo.
    echo ╔══════════════════════════════════════════════════════════╗
    echo ║   ACTION REQUIRED: Fill in your API keys in .env        ║
    echo ║                                                          ║
    echo ║   Open .env in Notepad and set:                         ║
    echo ║     TELEGRAM_BOT_TOKEN=  (from @BotFather)              ║
    echo ║     OPENAI_API_KEY=      (from platform.openai.com)     ║
    echo ║     ADMIN_TELEGRAM_IDS=  (your Telegram user ID)        ║
    echo ╚══════════════════════════════════════════════════════════╝
    echo.
    echo Press any key to open .env in Notepad, then re-run this script.
    pause >nul
    notepad .env
    echo.
    echo Re-run SERVER_INSTALL_AND_RUN.bat after saving .env.
    exit /b 0
)

:: ---- Verify keys are not empty ----
set "TOKEN_OK=0"
set "API_OK=0"
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    if "%%a"=="TELEGRAM_BOT_TOKEN" if not "%%b"=="" set "TOKEN_OK=1"
    if "%%a"=="BOT_TOKEN"          if not "%%b"=="" set "TOKEN_OK=1"
    if "%%a"=="OPENAI_API_KEY"     if not "%%b"=="" set "API_OK=1"
)

if "%TOKEN_OK%"=="0" (
    echo [ERROR] TELEGRAM_BOT_TOKEN is not set in .env
    echo         Open .env and add your bot token.
    notepad .env
    exit /b 1
)
if "%API_OK%"=="0" (
    echo [ERROR] OPENAI_API_KEY is not set in .env
    echo         Open .env and add your OpenAI key.
    notepad .env
    exit /b 1
)
echo [OK] API keys present (not displayed for security)

:: ================================================================
:: STEP 7 — Init database
:: ================================================================
echo [7/10] Initialising database...
"%PYTHON%" main.py --init-db
if errorlevel 1 (
    echo [ERROR] Database initialisation failed.
    pause
    exit /b 1
)
echo [OK] Database ready

:: ================================================================
:: STEP 8 — Verify installation with check.bat
:: ================================================================
echo [8/10] Running pre-flight checks...
call check.bat
if errorlevel 1 (
    echo [ERROR] Pre-flight checks failed. Fix the errors above, then re-run.
    pause
    exit /b 1
)
echo [OK] All checks passed

:: ================================================================
:: STEP 9 — Install Task Scheduler tasks (optional, needs admin)
:: ================================================================
echo [9/10] Installing scheduled tasks...

net session >nul 2>&1
if errorlevel 1 (
    echo [WARN] Not running as Administrator.
    echo        Scheduled tasks will NOT be installed automatically.
    echo        To set up auto-start and auto-update, right-click
    echo        install_bot_task.bat and install_updater_task.bat
    echo        and choose "Run as administrator".
) else (
    call install_bot_task.bat
    call install_updater_task.bat
    echo [OK] Scheduled tasks installed
)

:: ================================================================
:: STEP 10 — Start bot
:: ================================================================
echo [10/10] Starting bot...
call start.bat

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║   TUNTUN is now running!                                ║
echo ║                                                          ║
echo ║   Useful commands:                                       ║
echo ║     status.bat   — check if bot is running              ║
echo ║     stop.bat     — stop bot                             ║
echo ║     restart.bat  — restart bot                          ║
echo ║     auto_update.bat — run update manually               ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
pause
