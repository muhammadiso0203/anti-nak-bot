@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Nakrutka Blocker - SKANER

echo ==========================================
echo   KANAL ICHIDAGI NAKRUTKALARNI SKANER
echo ==========================================
echo.
echo 1 - Kanallar ro'yxatini ko'rish
echo 2 - Kanalni tekshirish (hech kim o'chirilmaydi, CSV hisobot)
echo 3 - Tekshirish va topilganlarni O'CHIRISH
echo.
set /p choice="Tanlang (1/2/3): "

if "%choice%"=="1" (
    python scanner.py --list
    pause
    exit /b
)

set /p chat="Kanal (@username yoki -100... ID): "
if "%choice%"=="3" (
    python scanner.py --chat %chat% --apply --mode ban
) else (
    python scanner.py --chat %chat%
)
pause
