@echo off
chcp 65001 > nul
title Sunhouse Audio Stream Relay va Ngrok Tunnel [Port 3001]
color 0A
setlocal

rem --- Tu dong tim kiem thu muc audio_stream_relay ---
set RELAY_DIR=
if exist "%~dp0..\..\audio_stream_relay" set "RELAY_DIR=%~dp0..\..\audio_stream_relay"
if "%RELAY_DIR%"=="" if exist "%~dp0..\..\Xiaozhi_Project\xiaozhi-esp32-main\audio_stream_relay" set "RELAY_DIR=%~dp0..\..\Xiaozhi_Project\xiaozhi-esp32-main\audio_stream_relay"
if "%RELAY_DIR%"=="" if exist "%~dp0..\audio_stream_relay" set "RELAY_DIR=%~dp0..\audio_stream_relay"
if "%RELAY_DIR%"=="" if exist "E:\ESP_Arduino_VSCode\Xiaozhi_Project\xiaozhi-esp32-main\audio_stream_relay" set "RELAY_DIR=E:\ESP_Arduino_VSCode\Xiaozhi_Project\xiaozhi-esp32-main\audio_stream_relay"

rem --- Tu dong tim kiem ngrok.exe ---
set NGROK_EXE=
if exist "%~dp0..\..\tools\ngrok.exe" set "NGROK_EXE=%~dp0..\..\tools\ngrok.exe"
if "%NGROK_EXE%"=="" if exist "%~dp0..\..\Xiaozhi_Project\xiaozhi-esp32-main\tools\ngrok.exe" set "NGROK_EXE=%~dp0..\..\Xiaozhi_Project\xiaozhi-esp32-main\tools\ngrok.exe"
if "%NGROK_EXE%"=="" if exist "%~dp0..\tools\ngrok.exe" set "NGROK_EXE=%~dp0..\tools\ngrok.exe"
if "%NGROK_EXE%"=="" if exist "E:\ESP_Arduino_VSCode\Xiaozhi_Project\xiaozhi-esp32-main\tools\ngrok.exe" set "NGROK_EXE=E:\ESP_Arduino_VSCode\Xiaozhi_Project\xiaozhi-esp32-main\tools\ngrok.exe"

echo ====================================================================
echo   KHOI DONG DICH VU PHAT NHAC YOUTUBE [RELAY + NGROK TUNNEL]
echo   Domain: https://unstuffed-dingo-barley.ngrok-free.dev
echo ====================================================================
echo.

netstat -aon | findstr ":3001" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    if "%RELAY_DIR%"=="" (
        echo [LOI] Khong tim thay thu muc audio_stream_relay!
        pause
        exit /b 1
    )
    if not exist "%RELAY_DIR%" (
        echo [LOI] Khong tim thay thu muc: %RELAY_DIR%
        pause
        exit /b 1
    )
    echo [1/2] Dang khoi dong Audio Stream Relay tren port 3001...
    echo       Thu muc: %RELAY_DIR%
    start "XiaoZhi Audio Stream Relay [Port 3001]" /D "%RELAY_DIR%" cmd /k node server.js
    ping 127.0.0.1 -n 3 >nul
) else (
    echo [1/2] Audio Stream Relay [Port 3001] da dang hoat dong san.
)

if "%NGROK_EXE%"=="" (
    echo [LOI] Khong tim thay tools\ngrok.exe!
    pause
    exit /b 1
)
if not exist "%NGROK_EXE%" (
    echo [LOI] Khong tim thay tools\ngrok.exe tai: %NGROK_EXE%
    pause
    exit /b 1
)

tasklist /fi "imagename eq ngrok.exe" | findstr /i "ngrok.exe" >nul
if %errorlevel% equ 0 (
    echo [2/2] Ngrok dang chay san. He thong da san sang phat nhac YouTube!
    echo.
    echo Bam phim bat ky de thoat cua so nay...
    pause >nul
    exit /b 0
)

echo [2/2] Dang khoi dong Ngrok Tunnel toi port 3001...
echo       File: %NGROK_EXE%
"%NGROK_EXE%" http 3001 --url unstuffed-dingo-barley.ngrok-free.dev
pause
