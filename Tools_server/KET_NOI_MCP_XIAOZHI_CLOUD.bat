@echo off
title Ket Noi Sunhouse RAG MCP Voi Cloud XiaoZhi
color 0A
setlocal

set SCRIPT_DIR=%~dp0
set MCP_DIR=%SCRIPT_DIR%..\mcp_sunhouse_rag
set PYTHON_EXE=%SCRIPT_DIR%..\venv\Scripts\python.exe

cd /d "%MCP_DIR%"

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" connect_xiaozhi_cloud.py %*
) else (
    python connect_xiaozhi_cloud.py %*
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [THONG BAO] Ket noi da dung.
    pause
)
