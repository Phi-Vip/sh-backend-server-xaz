@echo off
chcp 65001 > nul
title Khoi Dong Cum Voice Core 4 Workers + Nginx Ingress [Port 8000]
color 0A
echo ======================================================================
echo       KHOI DONG CUM VOICE CORE MULTI-WORKER (GIAI DOAN 4)
echo   Nginx Ingress Load Balancer: Port 8000 (least_conn)
echo   Worker 1: WS Port 8001 ^| HTTP Port 8011
echo   Worker 2: WS Port 8002 ^| HTTP Port 8012
echo   Worker 3: WS Port 8003 ^| HTTP Port 8013
echo   Worker 4: WS Port 8007 ^| HTTP Port 8014
echo ======================================================================
echo.

for %%i in ("%~dp0..\main\xiaozhi-server") do set SERVER_DIR=%%~fi
for %%i in ("%~dp0..\deploy\nginx\windows\nginx-1.26.2") do set NGINX_DIR=%%~fi
for %%i in ("%~dp0..\tts_server") do set TTS_DIR=%%~fi
for %%i in ("%~dp0..\venv\Scripts\python.exe") do set PYTHON_EXE=%%~fi

if not exist "%SERVER_DIR%" (
    echo [LOI] Khong tim thay thu muc: %SERVER_DIR%
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

echo [0/6] Dang khoi dong VieNeuTTS Microservice Standalone (Port 8008)...
start "VieNeuTTS Microservice [Port 8008]" /D "%TTS_DIR%" "%TTS_DIR%\RUN_TTS_SERVER.bat"
echo [OK] Da gui lenh khoi dong VieNeuTTS Service (RUN_TTS_SERVER.bat). Doi service san sang...
ping 127.0.0.1 -n 6 > nul

echo [1/6] Dang khoi dong Worker 1 (Port 8001)...
start "Voice Worker 1 [Port 8001]" cmd /k "cd /d %SERVER_DIR% && set WS_PORT=8001&& set HTTP_PORT=8011&& set WORKER_ID=worker_01&& %PYTHON_EXE% app.py"

echo [2/6] Dang khoi dong Worker 2 (Port 8002)...
start "Voice Worker 2 [Port 8002]" cmd /k "cd /d %SERVER_DIR% && set WS_PORT=8002&& set HTTP_PORT=8012&& set WORKER_ID=worker_02&& %PYTHON_EXE% app.py"

echo [3/6] Dang khoi dong Worker 3 (Port 8003)...
start "Voice Worker 3 [Port 8003]" cmd /k "cd /d %SERVER_DIR% && set WS_PORT=8003&& set HTTP_PORT=8013&& set WORKER_ID=worker_03&& %PYTHON_EXE% app.py"

echo [4/6] Dang khoi dong Worker 4 (Port 8007)...
start "Voice Worker 4 [Port 8007]" cmd /k "cd /d %SERVER_DIR% && set WS_PORT=8007&& set HTTP_PORT=8014&& set WORKER_ID=worker_04&& %PYTHON_EXE% app.py"

ping 127.0.0.1 -n 3 > nul

echo [5/6] Dang khoi dong Nginx Ingress Load Balancer (Port 8000)...
if not exist "%NGINX_DIR%\nginx.exe" (
    echo [CANH BAO] Khong tim thay nginx.exe tai %NGINX_DIR%
    goto :AFTER_NGINX
)

cd /d "%NGINX_DIR%"
netstat -aon | findstr ":8000" | findstr "LISTENING" > nul
if errorlevel 1 (
    taskkill /F /IM nginx.exe > nul 2>&1
    if exist logs\nginx.pid del /F /Q logs\nginx.pid > nul 2>&1
    start "" nginx.exe
    ping 127.0.0.1 -n 2 > nul
    echo [OK] Nginx Ingress Server da khoi dong tren cong 8000!
) else (
    nginx.exe -s reload > nul 2>&1
    echo [OK] Nginx Ingress dang hoat dong va da reload tren cong 8000!
)

:AFTER_NGINX

echo [6/6] Dang mo Cua so Theo doi Truc tiep Luu luong Port 8000 (Live Stream)...
start "Nginx Ingress Traffic Stream [Port 8000]" "%~dp0XEM_LOG_NGINX_PORT_8000.bat"

echo.
echo ======================================================================
echo   DA KHOI DONG THANH CONG CUM 4 WORKERS VA NGINX INGRESS LOAD BALANCER!
echo   Moi ket noi tu Loa ESP32 toi Port 8000 se hien thi o cua so giam sat.
echo   Moi ket noi tu Loa ESP32 toi Port 8000 se duoc Nginx chia deu tai.
echo ======================================================================
pause
