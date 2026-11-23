@echo off
chcp 65001 > nul
title SmartHome ^& Home Assistant MCP Hub [Port 8005]
color 0B
echo ======================================================================
echo    KHOI DONG SMARTHOME ^& HOME ASSISTANT MCP HUB SERVER (PORT 8005)
echo ======================================================================
echo.
echo - WebSocket MCP Endpoint : ws://127.0.0.1:8005/mcp_endpoint/mcp/?token=smarthome_secret_token
echo - Health Check HTTP      : http://127.0.0.1:8005/health
echo.
echo Nhan Ctrl+C de dung server.
echo ======================================================================
echo.

set MCP_DIR=%~dp0..\mcp_smarthome_hub
set PYTHON_EXE=%~dp0..\venv\Scripts\python.exe
set PYTHONUNBUFFERED=1

if not exist "%MCP_DIR%" (
    echo [LOI] Khong tim thay thu muc: %MCP_DIR%
    pause
    exit /b 1
)

cd /d "%MCP_DIR%"

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" main.py
) else (
    echo [CANH BAO] Khong tim thay Python venv, chuyen sang python he thong...
    python main.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] SmartHome MCP Server dung dot ngot hoac gap loi!
    pause
)

