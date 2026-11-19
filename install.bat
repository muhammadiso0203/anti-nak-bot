@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Nakrutka Blocker - o'rnatish

echo ==========================================
echo    NAKRUTKA BLOCKER - O'RNATISH
echo ==========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [XATO] Python topilmadi!
    echo Python'ni https://python.org/downloads dan yuklab o'rnating.
    echo O'rnatishda "Add Python to PATH" ni belgilashni unutmang.
    pause
    exit /b 1
)

python --version
echo.
echo Kerakli kutubxonalar o'rnatilmoqda...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [XATO] Kutubxonalar o'rnatilmadi. Internetni tekshirib qayta urinib ko'ring.
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo [OK] .env fayli yaratildi.
    echo Endi .env faylini bloknotda ochib BOT_TOKEN va ADMIN_IDS ni to'ldiring.
    notepad .env
) else (
    echo.
    echo [OK] .env fayli allaqachon mavjud.
)

echo.
echo ==========================================
echo  O'rnatish tugadi.
echo.
echo  1) start.bat  - botni ishga tushirish (doimiy ochiq turadi)
echo  2) login.bat  - kanal ICHIDAGI eski nakrutkalarni tozalash uchun
echo                  bir martalik akkaunt login (/scan buyrugi uchun)
echo ==========================================
pause
