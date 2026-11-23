@echo off
chcp 65001 >nul
title VieNeuTTS Standalone Microservice (Port 8008)
cd /d "%~dp0"
echo =====================================================================
echo    KHOI DONG VIENEUTTS STANDALONE MICROSERVICE (PORT 8008)
echo    Nap mo hinh 1 lan vao RAM (~800MB) - Phuc vu 4 Voice Worker
echo =====================================================================

for %%i in ("%~dp0..\venv\Scripts\python.exe") do set PYTHON_EXE=%%~fi
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

"%PYTHON_EXE%" "%~dp0server.py"
pause
