@echo off
chcp 65001 > nul
title Cau Hinh Firewall Cho Toan Bo Server XiaoZhi
color 0B

:: Kiem tra quyen Administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Dang yeu cau quyen Administrator de mo Firewall...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo =====================================================================
echo       DANG CAU HINH WINDOWS FIREWALL CHO TOAN BO SERVER XIAOZHI
echo =====================================================================
echo.

echo 1. Mo cac cong XiaoZhi Core (Port 8000, 8003)...
netsh advfirewall firewall delete rule name="XiaoZhi Server (8000, 8003)" >nul 2>&1
netsh advfirewall firewall add rule name="XiaoZhi Server (8000, 8003)" dir=in action=allow protocol=TCP localport=8000,8003 >nul 2>&1

echo 2. Mo cong MCP Server (Port 8004)...
netsh advfirewall firewall delete rule name="XiaoZhi MCP Server (8004)" >nul 2>&1
netsh advfirewall firewall add rule name="XiaoZhi MCP Server (8004)" dir=in action=allow protocol=TCP localport=8004 >nul 2>&1

echo 3. Mo cong Music Resolver Gateway (Port 3000)...
netsh advfirewall firewall delete rule name="XiaoZhi Music Port 3000" >nul 2>&1
netsh advfirewall firewall add rule name="XiaoZhi Music Port 3000" dir=in action=allow protocol=TCP localport=3000 >nul 2>&1

echo 4. Mo cong YouTube Audio Stream Relay (Port 3001)...
netsh advfirewall firewall delete rule name="XiaoZhi Audio Relay Port 3001" >nul 2>&1
netsh advfirewall firewall add rule name="XiaoZhi Audio Relay Port 3001" dir=in action=allow protocol=TCP localport=3001 >nul 2>&1

echo 5. Cap quyen Inbound cho Python venv...
set PYTHON_VENV=%~dp0..\venv\Scripts\python.exe
if exist "%PYTHON_VENV%" (
    netsh advfirewall firewall add rule name="Python Venv XiaoZhi" dir=in action=allow program="%PYTHON_VENV%" enable=yes >nul 2>&1
)

echo.
echo =====================================================================
echo [THANH CONG] Da cau hinh Firewall cho toan bo cac cong 8000, 8003, 8004, 3000, 3001!
echo Thiet bi ESP32 va cac may trong mang LAN gio day co the ket noi thong suot.
echo =====================================================================
echo.
pause
