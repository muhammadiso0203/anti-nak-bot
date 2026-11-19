@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Nakrutka Blocker - BOT

:run
echo [%date% %time%] Bot ishga tushirilmoqda...
python bot.py
echo.
echo [!] Bot to'xtadi. 10 sekunddan keyin qayta ishga tushadi.
echo     To'xtatish uchun bu oynani yoping yoki Ctrl+C bosing.
timeout /t 10 /nobreak >nul
goto run
