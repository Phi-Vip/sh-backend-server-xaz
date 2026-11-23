@echo off
chcp 65001 > nul
title Dung XiaoZhi Voice Core Server
color 0C
echo ========================================================
echo    DANG DUNG XIAOZHI VOICE CORE SERVER (PORT 8000, 8003)
echo ========================================================
echo.

set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo [OK] Da tat tien trinh PID: %%a (Port 8000)
    set FOUND=1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8003" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo [OK] Da tat tien trinh PID: %%a (Port 8003)
    set FOUND=1
)

if "%FOUND%"=="0" (
    echo [INFO] XiaoZhi Server hien khong chay tren port 8000/8003.
)

echo.
echo Hoan tat giai phong Port 8000 va 8003!
timeout /t 2 > nul
