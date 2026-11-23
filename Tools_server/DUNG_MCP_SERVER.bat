@echo off
chcp 65001 > nul
title Dung Sunhouse MCP Server
color 0C
echo ========================================================
echo    DANG DUNG SUNHOUSE MCP ENDPOINT SERVER (PORT 8004)
echo ========================================================
echo.

set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8004" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo [OK] Da tat tien trinh PID: %%a (Port 8004)
    set FOUND=1
)

if "%FOUND%"=="0" (
    echo [INFO] MCP Server hien khong chay tren port 8004.
)

echo.
echo Hoan tat giai phong Port 8004!
timeout /t 2 > nul
