@echo off
chcp 65001 > nul
title XiaoZhi Voice Core Server [Port 8000 va 8003]
color 0B
echo =====================================================================
echo          KHOI DONG XIAOZHI VOICE CORE SERVER (PORT 8000 va 8003)
echo =====================================================================
echo.
echo - WebSocket Endpoint : ws://0.0.0.0:8000/xiaozhi/v1/
echo - OTA / Web Endpoint : http://0.0.0.0:8003/xiaozhi/ota/
echo.
echo Nhan Ctrl+C de dung server.
echo =====================================================================
echo.

set SERVER_DIR=%~dp0..\main\xiaozhi-server
set PYTHON_EXE=%~dp0..\venv\Scripts\python.exe

if not exist "%SERVER_DIR%" (
    echo [LOI] Khong tim thay thu muc: %SERVER_DIR%
    pause
    exit /b 1
)

cd /d "%SERVER_DIR%"

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" app.py
) else (
    echo [CANH BAO] Khong tim thay Python venv, chuyen sang python he thong...
    python app.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] XiaoZhi Server dung dot ngot hoac gap loi!
    pause
)
