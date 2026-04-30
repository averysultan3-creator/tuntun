@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title TUNTUN — Bootstrap

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   TUNTUN Bootstrap — только этот файл   ║
echo  ║   Клонирует репо и запускает установку  ║
echo  ╚══════════════════════════════════════════╝
echo.

:: ================================================================
:: Проверяем Python
:: ================================================================
set "PYTHON="
for %%p in (
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do (
    if not defined PYTHON if exist "%%~p" set "PYTHON=%%~p"
)
if not defined PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
    echo [ERROR] Python не найден!
    echo.
    echo Скачай: https://python.org/downloads
    echo При установке отметь "Add Python to PATH",
    echo затем запусти BOOTSTRAP.bat снова.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('"%PYTHON%" --version 2^>^&1') do set "PY_VER=%%v"
echo [OK] Python %PY_VER%

:: ================================================================
:: Проверяем git
:: ================================================================
where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git не найден!
    echo.
    echo Скачай: https://git-scm.com/download/win
    echo После установки перезапусти BOOTSTRAP.bat.
    echo.
    pause
    exit /b 1
)
for /f "tokens=3" %%v in ('git --version 2^>^&1') do set "GIT_VER=%%v"
echo [OK] git %GIT_VER%

:: ================================================================
:: Клонируем репо (если ещё нет)
:: ================================================================
set "REPO_URL=https://github.com/averysultan3-creator/tuntun.git"
set "TARGET_DIR=%~dp0TUNTUN"

if exist "%TARGET_DIR%\main.py" (
    echo [OK] Папка TUNTUN уже существует — обновляем...
    cd /d "%TARGET_DIR%"
    git pull origin main
) else (
    echo [GIT] Клонируем %REPO_URL%...
    git clone "%REPO_URL%" "%TARGET_DIR%"
    if errorlevel 1 (
        echo [ERROR] git clone провалился — проверь интернет
        pause
        exit /b 1
    )
    cd /d "%TARGET_DIR%"
)

echo [OK] Репозиторий готов: %TARGET_DIR%
echo.

:: ================================================================
:: Передаём управление SETUP.bat из репо
:: ================================================================
call "%TARGET_DIR%\SETUP.bat"
