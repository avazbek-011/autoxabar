@echo off
chcp 65001 >nul
title VIPADSUZ - AutoXabar
cd /d "%~dp0"

echo.
echo  ======================================================
echo    VIPADSUZ . AutoXabar
echo  ======================================================
echo.

if not exist ".env" (
  echo  [!] .env fayli topilmadi, .env.example nusxalanmoqda...
  copy ".env.example" ".env" >nul
)

echo  [*] Kutubxonalar tekshirilmoqda...
python -m pip install -q -r requirements.txt

echo  [*] Server ishga tushirilmoqda...
echo.
python app.py

pause
