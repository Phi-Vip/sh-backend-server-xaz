@echo off
title Ket Noi MCP Sunhouse Voi Cloud XiaoZhi
color 0A
setlocal

cd /d "%~dp0"

if exist "..\venv\Scripts\python.exe" (
    "..\venv\Scripts\python.exe" connect_xiaozhi_cloud.py %*
) else (
    python connect_xiaozhi_cloud.py %*
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [THONG BAO] Ket noi da dung.
    pause
)
