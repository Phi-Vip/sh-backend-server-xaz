@echo off
chcp 65001 > nul
title Dung Cum Voice Core 4 Workers va Nginx Ingress
color 0C
echo ========================================================
echo       DANG DUNG CUM VOICE CORE VA NGINX INGRESS
echo ========================================================
echo.

set NGINX_DIR=%~dp0..\deploy\nginx\windows\nginx-1.26.2
if exist "%NGINX_DIR%\nginx.exe" (
    cd /d "%NGINX_DIR%"
    nginx.exe -s stop > nul 2>&1
)
taskkill /F /IM nginx.exe > nul 2>&1
if exist "%NGINX_DIR%\logs\nginx.pid" del /F /Q "%NGINX_DIR%\logs\nginx.pid" > nul 2>&1
echo [OK] Da dung Nginx Ingress Server.

for %%p in (8000 8001 8002 8003 8007 8008 8011 8012 8013 8014) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%%p" ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a > nul 2>&1
        echo [OK] Da tat tien trinh PID: %%a (Port %%p)
    )
)

echo.
echo Hoan tat giai phong tat ca Ports cua Cum Voice Core va Nginx!
ping 127.0.0.1 -n 3 > nul
