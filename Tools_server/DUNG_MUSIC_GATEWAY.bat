@echo off
chcp 65001 > nul
title Dung Music Resolver Gateway
color 0C
echo ========================================================
echo    DANG DUNG MUSIC RESOLVER GATEWAY (PORT 3000)
echo ========================================================
echo.

set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo [OK] Da tat tien trinh PID: %%a (Port 3000)
    set FOUND=1
)

if "%FOUND%"=="0" (
    echo [INFO] Music Resolver Gateway hien khong chay tren port 3000.
)

echo.
echo Hoan tat giai phong Port 3000!
timeout /t 2 > nul
