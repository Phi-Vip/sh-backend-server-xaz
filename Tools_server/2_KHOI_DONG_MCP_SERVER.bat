@echo off
chcp 65001 > nul
title Sunhouse RAG MCP Endpoint Server [Port 8004]
color 0E
echo ======================================================================
echo          KHOI DONG SUNHOUSE RAG MCP ENDPOINT SERVER (PORT 8004)
echo ======================================================================
echo.
echo - WebSocket MCP Endpoint : ws://127.0.0.1:8004/mcp_endpoint/mcp/?token=sunhouse_secret_token
echo - Health Check HTTP      : http://127.0.0.1:8004/health
echo.
echo Nhan Ctrl+C de dung server.
echo ======================================================================
echo.

set MCP_DIR=%~dp0..\mcp_sunhouse_rag
set PYTHON_EXE=%~dp0..\venv\Scripts\python.exe

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
    echo [LOI] Sunhouse RAG MCP Server dung dot ngot hoac gap loi!
    pause
)
