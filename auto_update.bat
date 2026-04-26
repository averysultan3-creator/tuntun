@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ============================================================
:: auto_update.bat — TUNTUN automatic git-based updater
:: Runs every N minutes via Windows Task Scheduler.
:: ============================================================

set "LOGFILE=%~dp0logs\deploy.log"
set "LOCKFILE=%~dp0update.lock"
set "BACKUPDIR=%~dp0storage\backups"
set "LAST_GOOD_FILE=%~dp0logs\last_good_commit.txt"

:: ---- Python detection ----
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
) else if exist "C:\Python310\python.exe" (
    set "PYTHON=C:\Python310\python.exe"
) else (
    set "PYTHON=python"
)

:: ---- Timestamp helper ----
for /f "tokens=1-6 delims=/: " %%a in ('powershell -NoProfile -Command "Get-Date -Format \"yyyy/MM/dd HH:mm:ss\""') do (
    set "DT=%%a-%%b-%%c %%d:%%e:%%f"
    set "DTS=%%a%%b%%c_%%d%%e%%f"
)

:: Ensure logs dir exists
if not exist "%~dp0logs" mkdir "%~dp0logs"

call :LOG "=== auto_update started ==="

:: ---- Concurrency lock ----
if exist "%LOCKFILE%" (
    call :LOG "[SKIP] update.lock exists — another update is running. Exit."
    exit /b 0
)
echo %DT% > "%LOCKFILE%"

:: ---- Read AUTO_UPDATE_ENABLED from .env ----
set "UPDATE_ENABLED=true"
for /f "usebackq tokens=1,2 delims==" %%a in ("%~dp0.env") do (
    if "%%a"=="AUTO_UPDATE_ENABLED" set "UPDATE_ENABLED=%%b"
)
if /i "%UPDATE_ENABLED%"=="false" (
    call :LOG "[SKIP] AUTO_UPDATE_ENABLED=false"
    goto :cleanup
)

:: ---- Read GIT_BRANCH from .env (default: main) ----
set "GIT_BRANCH=main"
for /f "usebackq tokens=1,2 delims==" %%a in ("%~dp0.env") do (
    if "%%a"=="GIT_BRANCH" set "GIT_BRANCH=%%b"
)

cd /d "%~dp0"

:: ---- Check git ----
where git >nul 2>&1
if errorlevel 1 (
    call :LOG "[ERROR] git not found in PATH"
    goto :cleanup
)

:: ---- Fetch latest ----
call :LOG "[GIT] Fetching origin/%GIT_BRANCH%..."
git fetch origin %GIT_BRANCH% >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :LOG "[ERROR] git fetch failed"
    goto :cleanup
)

:: ---- Compare commits ----
for /f %%i in ('git rev-parse HEAD 2^>nul') do set "LOCAL_COMMIT=%%i"
for /f %%i in ('git rev-parse origin/%GIT_BRANCH% 2^>nul') do set "REMOTE_COMMIT=%%i"

call :LOG "[GIT] Local:  %LOCAL_COMMIT%"
call :LOG "[GIT] Remote: %REMOTE_COMMIT%"

if "%LOCAL_COMMIT%"=="%REMOTE_COMMIT%" (
    call :LOG "[OK] Already up to date. No update needed."
    goto :cleanup
)

call :LOG "[UPDATE] New commits found. Starting deployment..."

:: ---- Backup database ----
if exist "%~dp0tuntun.db" (
    if not exist "%BACKUPDIR%" mkdir "%BACKUPDIR%"
    set "BACKUP_FILE=%BACKUPDIR%\pre_deploy_%DTS%_tuntun.db"
    copy "%~dp0tuntun.db" "!BACKUP_FILE!" >nul
    call :LOG "[BACKUP] DB backed up to !BACKUP_FILE!"
)

:: ---- Stop bot ----
call :LOG "[DEPLOY] Stopping bot..."
call "%~dp0stop.bat" >> "%LOGFILE%" 2>&1

:: ---- git pull ----
call :LOG "[DEPLOY] git pull..."
git pull origin %GIT_BRANCH% >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :LOG "[ERROR] git pull failed — rolling back"
    goto :rollback
)

:: ---- pip install ----
call :LOG "[DEPLOY] Installing dependencies..."
"%PYTHON%" -m pip install --quiet -r "%~dp0requirements.txt" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :LOG "[WARN] pip install had errors (continuing)"
)

:: ---- Init DB ----
call :LOG "[DEPLOY] Running --init-db..."
"%PYTHON%" "%~dp0main.py" --init-db >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :LOG "[ERROR] --init-db failed — rolling back"
    goto :rollback
)

:: ---- Check ----
call :LOG "[DEPLOY] Running check.bat..."
call "%~dp0check.bat" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :LOG "[ERROR] check.bat failed — rolling back"
    goto :rollback
)

:: ---- Start bot ----
call :LOG "[DEPLOY] Starting bot..."
call "%~dp0start.bat" >> "%LOGFILE%" 2>&1

:: ---- Save last good commit ----
echo %REMOTE_COMMIT%> "%LAST_GOOD_FILE%"
call :LOG "[OK] Deployment complete. Commit: %REMOTE_COMMIT%"
goto :cleanup

:: ================================================================
:rollback
call :LOG "[ROLLBACK] Reverting to last known good state..."

:: Restore DB backup if available
if defined BACKUP_FILE if exist "!BACKUP_FILE!" (
    copy "!BACKUP_FILE!" "%~dp0tuntun.db" >nul
    call :LOG "[ROLLBACK] DB restored from !BACKUP_FILE!"
)

:: Reset git to last good commit
if exist "%LAST_GOOD_FILE%" (
    set /p LAST_GOOD=<"%LAST_GOOD_FILE%"
    if defined LAST_GOOD (
        call :LOG "[ROLLBACK] git reset --hard !LAST_GOOD!..."
        git reset --hard !LAST_GOOD! >> "%LOGFILE%" 2>&1
    )
) else (
    call :LOG "[ROLLBACK] No last_good_commit.txt — resetting to local HEAD before pull..."
    git reset --hard %LOCAL_COMMIT% >> "%LOGFILE%" 2>&1
)

call :LOG "[ROLLBACK] Starting bot from previous version..."
call "%~dp0start.bat" >> "%LOGFILE%" 2>&1
call :LOG "[ROLLBACK] Done."
goto :cleanup

:: ================================================================
:cleanup
if exist "%LOCKFILE%" del /f /q "%LOCKFILE%"
call :LOG "=== auto_update finished ==="
exit /b 0

:: ================================================================
:LOG
echo [%DT%] %~1
echo [%DT%] %~1 >> "%LOGFILE%"
goto :eof
