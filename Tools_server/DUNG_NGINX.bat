@echo off
chcp 65001 > nul
title Dung Nginx Ingress Server
color 0C
echo ========================================================
echo          DANG DUNG NGINX INGRESS LOAD BALANCER
echo ========================================================
echo.

set NGINX_DIR=%~dp0..\deploy\nginx\windows\nginx-1.26.2

if exist "%NGINX_DIR%\nginx.exe" (
    cd /d "%NGINX_DIR%"
    nginx.exe -s stop > nul 2>&1
)

taskkill /F /IM nginx.exe > nul 2>&1

echo [OK] Da dung hoan toan tien trinh Nginx!
ping 127.0.0.1 -n 3 > nul
