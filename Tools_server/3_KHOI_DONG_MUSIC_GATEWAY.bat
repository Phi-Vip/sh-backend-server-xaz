@echo off
chcp 65001 > nul
title XiaoZhi Music Resolver Gateway [Port 3000]
color 0A

rem --- Tu dong tim kiem thu muc serverless_music_api ---
set MUSIC_DIR=
if exist "%~dp0..\..\serverless_music_api" set "MUSIC_DIR=%~dp0..\..\serverless_music_api"
if "%MUSIC_DIR%"=="" if exist "%~dp0..\..\Xiaozhi_Project\xiaozhi-esp32-main\serverless_music_api" set "MUSIC_DIR=%~dp0..\..\Xiaozhi_Project\xiaozhi-esp32-main\serverless_music_api"
if "%MUSIC_DIR%"=="" if exist "%~dp0..\serverless_music_api" set "MUSIC_DIR=%~dp0..\serverless_music_api"
if "%MUSIC_DIR%"=="" if exist "E:\ESP_Arduino_VSCode\Xiaozhi_Project\xiaozhi-esp32-main\serverless_music_api" set "MUSIC_DIR=E:\ESP_Arduino_VSCode\Xiaozhi_Project\xiaozhi-esp32-main\serverless_music_api"

if "%MUSIC_DIR%"=="" (
    echo [LOI] Khong tim thay thu muc serverless_music_api!
    pause
    exit /b 1
)
if not exist "%MUSIC_DIR%" (
    echo [LOI] Khong tim thay thu muc serverless_music_api tai: %MUSIC_DIR%
    pause
    exit /b 1
)

cd /d "%MUSIC_DIR%"

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1"') do (
    set CURRENT_IP=%%a
    goto :found_ip
)
:found_ip
set CURRENT_IP=%CURRENT_IP: =%

echo ========================================================
echo       KHOI DONG XIAOZHI MUSIC RESOLVER GATEWAY
echo ========================================================
echo - Local PC : http://localhost:3000
echo - Mang LAN : http://%CURRENT_IP%:3000
echo - API Test : http://%CURRENT_IP%:3000/api/music/resolve?query=em cua ngay hom qua
echo ========================================================
echo Nhan Ctrl + C de dung server bat cu luc nao.
echo.

node index.js
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] Music Gateway dung dot ngot hoac NodeJS chua duoc cai dat!
    pause
)
