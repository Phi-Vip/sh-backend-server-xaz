@echo off
chcp 65001 > nul
title Khoi Dong Nginx Ingress Load Balancer [Port 8000]
color 0E
echo ======================================================================
echo       KHOI DONG NGINX INGRESS LOAD BALANCER (CHUAN THUONG MAI)
echo   Tiep nhan ket noi tu Loa ESP32 (Port 8000) va can bang tai 4 Workers
echo   Thuat toan: least_conn (chuyen ket noi vao Worker ranh nhat)
echo   Bao mat: Anti-CVE-2026-123007 (Thuan HTTP/1.1 + WebSocket Upgrade)
echo ======================================================================
echo.

set NGINX_DIR=%~dp0..\deploy\nginx\windows\nginx-1.26.2

if not exist "%NGINX_DIR%\nginx.exe" (
    echo [LOI] Khong tim thay nginx.exe tai: %NGINX_DIR%
    pause
    exit /b 1
)

cd /d "%NGINX_DIR%"

netstat -aon | findstr ":8000" | findstr "LISTENING" > nul
if errorlevel 1 (
    echo Dang khoi dong Nginx Ingress Server...
    taskkill /F /IM nginx.exe > nul 2>&1
    if exist logs\nginx.pid del /F /Q logs\nginx.pid > nul 2>&1
    start "" nginx.exe
) else (
    echo [THONG BAO] Nginx dang chay tren Port 8000. Dang nap lai cau hinh...
    nginx.exe -s reload
)

ping 127.0.0.1 -n 3 > nul

netstat -aon | findstr ":8000" | findstr "LISTENING" > nul
if %ERRORLEVEL% equ 0 (
    echo.
    echo ======================================================================
    echo   [THANH CONG] NGINX INGRESS DANG LANG NGHE TAI CONG 8000!
    echo   Loa ESP32 san sang ket noi ws://dia_chi_ip:8000/xiaozhi/v1/
    echo ======================================================================
) else (
    echo [CANH BAO] Chua thay Nginx lang nghe tai cong 8000.
)
