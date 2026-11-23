@echo off
chcp 65001 > nul
title Dung Dich Vu YouTube Relay va Ngrok
color 0C
echo ========================================================
echo    DANG DUNG YOUTUBE AUDIO RELAY VA NGROK TUNNEL
echo ========================================================
echo.

taskkill /F /IM ngrok.exe > nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Da tat tien trinh Ngrok.
) else (
    echo [INFO] Ngrok khong hoat dong.
)

set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3001" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo [OK] Da tat tien trinh Relay PID: %%a (Port 3001)
    set FOUND=1
)

if "%FOUND%"=="0" (
    echo [INFO] Audio Stream Relay khong chay tren port 3001.
)

echo.
echo Hoan tat dung dich vu YouTube Relay va Ngrok!
timeout /t 2 > nul
