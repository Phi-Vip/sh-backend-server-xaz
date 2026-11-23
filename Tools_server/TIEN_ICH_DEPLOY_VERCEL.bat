@echo off
chcp 65001 > nul
title Trien khai XiaoZhi Music Gateway len Vercel Cloud
color 0B
set MUSIC_DIR=%~dp0..\..\serverless_music_api

if not exist "%MUSIC_DIR%" (
    echo [LOI] Khong tim thay thu muc serverless_music_api tai: %MUSIC_DIR%
    pause
    exit /b 1
)

cd /d "%MUSIC_DIR%"

echo ========================================================
echo   TRIEN KHAI XIAOZHI MUSIC RESOLVER LEN VERCEL CLOUD
echo ========================================================
echo.
echo [BUOC 1] Dang nhap vao tai khoan Vercel...
echo Neu trinh duyet mo ra, hay chon dang nhap voi GitHub hoac Google.
echo.

call npx vercel login

echo.
echo ========================================================
echo [BUOC 2] Dang trien khai (Deploy) len Vercel Cloud...
echo ========================================================
echo.

call npx vercel --prod --yes

echo.
echo ========================================================
echo   HOAN TAT! HAY COPY LINK "Production: https://..." 
echo   GUI CHO TOI DE GAN VAO FIRMWARE XIAOZHI NHE!
echo ========================================================
echo.
pause
