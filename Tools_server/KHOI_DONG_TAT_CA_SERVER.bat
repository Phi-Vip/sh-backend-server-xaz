@echo off
chcp 65001 > nul
title KHOI DONG TOAN BO HE THONG SERVER XIAOZHI
color 0A

echo =====================================================================
echo          KHOI DONG TOAN BO HE THONG SERVER XIAOZHI
echo =====================================================================
echo.
echo He thong se khoi dong cac dich vu server chinh (Music Resolver dung Vercel Cloud):
echo  [1] XiaoZhi Voice Core Server     : Port 8000 va 8003
echo  [2] Sunhouse RAG MCP Endpoint     : Port 8004
echo  [3] SmartHome IoT & HA MCP Hub    : Port 8005
echo  [4] YouTube Stream Relay va Ngrok : Port 3001
echo.
echo (Luu y: Cua so Music Gateway Port 3000 local da duoc bo qua vi he thong da
echo         dung san tren Vercel Cloud. Neu muon dung offline, hay chay file so 3).
echo =====================================================================
echo.

echo Dang khoi dong [1/4] XiaoZhi Voice Core Server (Port 8000 & 8003)...
start "1. XiaoZhi Server (8000/8003)" cmd /k call "%~dp01_KHOI_DONG_XIAOZHI_SERVER.bat"
ping 127.0.0.1 -n 3 > nul

echo Dang khoi dong [2/4] Sunhouse RAG MCP Endpoint Server (Port 8004)...
start "2. Sunhouse RAG MCP (8004)" cmd /k call "%~dp02_KHOI_DONG_MCP_SERVER.bat"
ping 127.0.0.1 -n 2 > nul

echo Dang khoi dong [3/4] SmartHome IoT & HA MCP Hub Server (Port 8005)...
start "3. SmartHome MCP Hub (8005)" cmd /k call "%~dp03_KHOI_DONG_SMARTHOME_MCP_SERVER.bat"
ping 127.0.0.1 -n 2 > nul

echo Dang khoi dong [4/4] YouTube Stream Relay va Ngrok (Port 3001)...
start "4. YouTube Relay va Ngrok (3001)" cmd /k call "%~dp04_KHOI_DONG_YOUTUBE_RELAY.bat"

echo.
echo =====================================================================
echo    [HOAN TAT] TOAN BO CAC SERVER DA DUOC KICH HOAT THANH CONG!
echo =====================================================================
echo Cua so tong nay se tu dong dong sau 3 giay...
timeout /t 3 > nul
