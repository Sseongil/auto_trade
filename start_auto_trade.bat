@echo off
setlocal

:: Python 경로 (확인된 가상환경)
set PYTHON_PATH=C:\Users\user\stock_auto\venv\Scripts\python.exe
:: 프로젝트 경로
set PROJECT_DIR=C:\Users\user\stock_auto

cd /d %PROJECT_DIR%

echo.
echo --- Local API Server 실행 중 ---
start "Local API Server" cmd /k %PYTHON_PATH% local_api_server.py
timeout /t 10 >nul

echo.
echo --- ngrok 실행 중 ---
start "ngrok" cmd /k "C:\ngrok\ngrok.exe" http 5000
timeout /t 15 >nul

echo.
echo --- Render 환경변수 동기화 및 재배포 ---
%PYTHON_PATH% run_ngrok_and_update_render.py > ngrok_render_log.txt 2>&1

echo.
echo --- 자동화 완료 ---
pause
