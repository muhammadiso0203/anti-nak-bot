@echo off
chcp 65001 >nul
title Nakrutka Blocker - Web App Tunnel
cd /d "%~dp0"

echo ==========================================================
echo    NAKRUTKA BLOCKER — WEB APP HTTPS TUNNEL
echo ==========================================================
echo.
echo Telegram Mini App ishlashi uchun bepul HTTPS havola yaratilmoqda...
echo.

if not exist "cloudflared.exe" (
    echo [1/2] Cloudflared yordamchisi yuklab olinmoqda (faqat bir marta)...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
)

echo.
echo [2/2] Tunnel ishga tushirilmoqda (localhost:8080)...
echo.
echo ----------------------------------------------------------
echo DIQQAT: Quyida chiquvchi 'https://....trycloudflare.com'
echo havolasini nusxalab, .env faylidagi WEBAPP_URL= ga yozing!
echo ----------------------------------------------------------
echo.

cloudflared.exe tunnel --url http://localhost:8080
pause
