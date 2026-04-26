@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ============================================================
:: DEPLOY_TO_SERVER.bat — TUNTUN One-Click Server Deployer
::
:: Скопируй ТОЛЬКО этот файл на сервер и запусти.
:: Он сам:
::   1. Проверит Python 3.10+
::   2. Проверит Git
::   3. Клонирует репо с GitHub
::   4. Создаст .venv и установит зависимости
::   5. Попросит заполнить .env (токен + API ключ)
::   6. Инициализирует БД
::   7. Установит автозапуск и авто-обновление
::   8. Запустит бота
::
:: После этого бот работает 24/7.
:: Обновления: git push с локального ПК — сервер сам тянет.
:: ============================================================

set "REPO_URL=https://averysultan3-creator@github.com/averysultan3-creator/tuntun.git"
set "INSTALL_DIR=%~dp0TUNTUN"

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║       TUNTUN — One-Click Server Deployer               ║
echo ║       Репо: %REPO_URL%
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: ================================================================
:: STEP 1 — Python check
:: ================================================================
echo [1/5] Проверяю Python...

for %%P in (
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
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

echo.
echo [ERROR] Python не найден!
echo.
echo   Скачай и установи Python 3.10+ с https://python.org
echo   При установке обязательно отметь "Add Python to PATH"
echo.
pause
exit /b 1

:python_found
"%PYTHON%" -c "import sys; v=sys.version_info; exit(0 if v.major==3 and v.minor>=10 else 1)" 2>nul
if errorlevel 1 (
    echo [ERROR] Нужен Python 3.10+. Установлен более старый.
    "%PYTHON%" --version
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('"%PYTHON%" --version 2^>^&1') do echo [OK] Python %%v

:: ================================================================
:: STEP 2 — Git check
:: ================================================================
echo [2/5] Проверяю Git...
where git >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Git не найден!
    echo.
    echo   Скачай и установи Git с https://git-scm.com/download/win
    echo   После установки перезапусти этот батник.
    echo.
    pause
    exit /b 1
)
for /f "tokens=3" %%v in ('git --version 2^>^&1') do echo [OK] Git %%v

:: ================================================================
:: STEP 3 — Clone or update repo
:: ================================================================
echo [3/5] Клонирую репо...

if exist "%INSTALL_DIR%\main.py" (
    echo [OK] Репо уже склонировано — пропускаю
    cd /d "%INSTALL_DIR%"
) else (
    if exist "%INSTALL_DIR%" (
        echo [INFO] Папка TUNTUN существует, но main.py не найден. Удаляю и клонирую заново...
        rmdir /s /q "%INSTALL_DIR%"
    )
    echo [*] git clone %REPO_URL%...
    git clone "%REPO_URL%" "%INSTALL_DIR%"
    if errorlevel 1 (
        echo.
        echo [ERROR] Не удалось склонировать репо.
        echo   Проверь интернет и доступ к GitHub.
        echo   Если репо приватное — выполни сначала:
        echo     git config --global credential.helper manager
        echo   и попробуй снова.
        echo.
        pause
        exit /b 1
    )
    cd /d "%INSTALL_DIR%"
    echo [OK] Репо склонировано в %INSTALL_DIR%
)

:: ================================================================
:: STEP 4 — Run full installer
:: ================================================================
echo [4/5] Запускаю полный установщик...
echo.

:: Check if running as admin (needed for Task Scheduler)
net session >nul 2>&1
if errorlevel 1 (
    echo [WARN] Батник запущен НЕ от администратора.
    echo        Автозапуск при старте Windows не будет установлен.
    echo        Для установки задач планировщика:
    echo          правый клик → Запуск от имени администратора
    echo.
)

call "%INSTALL_DIR%\SERVER_INSTALL_AND_RUN.bat"

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║   Готово! Бот TUNTUN запущен.                          ║
echo ║                                                          ║
echo ║   Папка проекта: %INSTALL_DIR%
echo ║                                                          ║
echo ║   Управление:                                           ║
echo ║     status.bat  — статус бота + логи                   ║
echo ║     restart.bat — перезапустить                        ║
echo ║     stop.bat    — остановить                           ║
echo ║                                                          ║
echo ║   Авто-обновление: каждые 2 минуты проверяет GitHub    ║
echo ║   Просто делай git push — сервер сам обновится.        ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
pause
