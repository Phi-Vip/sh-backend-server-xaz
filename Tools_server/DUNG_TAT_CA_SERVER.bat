@echo off
chcp 65001 > nul
title DUNG TOAN BO HE THONG SERVER XIAOZHI
color 0C
echo =====================================================================
echo             DANG DUNG TOAN BO CAC SERVER TRONG HE THONG
echo =====================================================================
echo.

echo [1/7] Dung XiaoZhi Voice Core Server (Ports 8000, 8001, 8002, 8003, 8007)...
for %%p in (8000 8001 8002 8003 8007 8011 8012 8013 8014) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%%p" ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a > nul 2>&1
        echo   - Da dung tien trinh PID: %%a (Port %%p)
    )
)

echo.
echo [2/7] Dung VieNeuTTS Standalone Microservice (Port 8008)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8008" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo   - Da dung tien trinh PID: %%a (Port 8008)
)

echo.
echo [3/7] Dung Sunhouse RAG MCP Endpoint Server (Port 8004)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8004" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo   - Da dung tien trinh PID: %%a (Port 8004)
)

echo.
echo [3/6] Dung SmartHome IoT & HA MCP Hub Server (Port 8005)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8005" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo   - Da dung tien trinh PID: %%a (Port 8005)
)

echo.
echo [4/6] Dung Music Resolver Gateway (Port 3000)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo   - Da dung tien trinh PID: %%a (Port 3000)
)

echo.
echo [5/6] Dung YouTube Audio Stream Relay (Port 3001)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3001" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
    echo   - Da dung tien trinh PID: %%a (Port 3001)
)

echo.
echo [6/6] Dung tien trinh Ngrok Tunnel...
taskkill /F /IM ngrok.exe > nul 2>&1
if %errorlevel% equ 0 (
    echo   - Da tat tien trinh ngrok.exe
) else (
    echo   - Ngrok khong hoat dong.
)

echo.
echo =====================================================================
echo   [HOAN TAT] TOAN BO CAC CONG VA DICH VU SERVER DA DUOC GIAI PHONG!
echo =====================================================================
echo.
pause
