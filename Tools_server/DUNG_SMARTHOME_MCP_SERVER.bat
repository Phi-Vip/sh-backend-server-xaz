@echo off
chcp 65001 > nul
title Dung SmartHome MCP Server
color 0C
echo ========================================================
echo    DANG DUNG SMARTHOME MCP HUB SERVER (PORT 8005)
echo ========================================================
echo.

set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8005" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo [OK] Da tat tien trinh PID: %%a (Port 8005)
    set FOUND=1
)

if "%FOUND%"=="0" (
    echo [INFO] SmartHome MCP Server hien khong chay tren port 8005.
)

echo.
echo Hoan tat giai phong Port 8005!
timeout /t 2 > nul

