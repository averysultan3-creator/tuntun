@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   TUNTUN — Restart Bot
echo ============================================
echo.

call "%~dp0stop.bat"
timeout /t 2 /nobreak >nul
call "%~dp0start.bat"
