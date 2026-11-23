@echo off
chcp 65001 > nul
title Nginx Ingress Live Log [Port 8000]
color 0E

set NGINX_LOG=%~dp0..\deploy\nginx\windows\nginx-1.26.2\logs\access.log

if not exist "%NGINX_LOG%" (
    echo [CANH BAO] File log chua ton tai tai: %NGINX_LOG%
    echo Dang khoi tao file log...
    type nul > "%NGINX_LOG%"
)

powershell -NoExit -ExecutionPolicy Bypass -Command "$host.UI.RawUI.WindowTitle = 'Nginx Ingress Traffic Stream [Port 8000]'; Clear-Host; Write-Host '======================================================================' -ForegroundColor Cyan; Write-Host '   NGINX INGRESS LOAD BALANCER [PORT 8000] - LIVE TRAFFIC STREAM' -ForegroundColor Yellow; Write-Host '   Lang nghe va hien thi truc tiep moi ket noi tu Loa ESP32...' -ForegroundColor Gray; Write-Host '   File log: %NGINX_LOG%' -ForegroundColor DarkGray; Write-Host '======================================================================' -ForegroundColor Cyan; Write-Host ''; Get-Content -Path '%NGINX_LOG%' -Wait -Tail 25"
