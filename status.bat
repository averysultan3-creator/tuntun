@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   TUNTUN — Bot Status
echo ============================================
echo.

:: ---- Python detection ----
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else if exist "C:\Python310\python.exe" (
    set "PYTHON=C:\Python310\python.exe"
) else (
    set "PYTHON=python"
)

:: ---- Process status ----
for /f %%i in ('"%PYTHON%" run_background.py pid') do set "BOT_PID=%%i"
if "%BOT_PID%"=="0" (
    echo [STATUS] Bot: STOPPED
) else (
    echo [STATUS] Bot: RUNNING  (PID %BOT_PID%)
)

:: ---- Git commit ----
echo.
echo [GIT]
git log --oneline -1 2>nul || echo   (git not available)

:: ---- .env / DB ----
echo.
if exist ".env" (echo [ENV]    .env: present) else (echo [ENV]    .env: MISSING)
if exist "tuntun.db" (echo [DB]     tuntun.db: present) else (echo [DB]     tuntun.db: not found)
for %%F in ("storage\backups") do if exist "%%F\" (echo [BACKUP] backups dir: present) else (echo [BACKUP] backups dir: not found)

:: ---- Last good commit ----
if exist "logs\last_good_commit.txt" (
    set /p LAST_GOOD=<logs\last_good_commit.txt
    echo [DEPLOY] Last good commit: %LAST_GOOD%
)

:: ---- Last 30 lines of runtime log ----
echo.
echo [LOG] Last 30 lines of logs\runtime.log:
echo -------------------------------------------------------
if exist "logs\runtime.log" (
    powershell -NoProfile -Command "Get-Content 'logs\runtime.log' -Tail 30"
) else (
    echo   (log file not found)
)
echo -------------------------------------------------------
echo.
