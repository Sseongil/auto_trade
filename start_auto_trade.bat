@echo off
setlocal

:: Python 실행 경로 (가상환경 또는 시스템 Python)
set PYTHON_PATH=C:\Users\user\stock_auto\venv\Scripts\python.exe

:: 프로젝트 루트
set PROJECT_DIR=C:\Users\user\stock_auto

cd /d %PROJECT_DIR%

echo.
echo [1] --- Flask Local API 서버 실행 ---
start "Local API Server" cmd /k %PYTHON_PATH% local_api_server.py
timeout /t 12 >nul

echo.
echo [2] --- ngrok 실행 ---
start "Ngrok" cmd /k "C:\ngrok\ngrok.exe" http 5000"
timeout /t 15 >nul

echo.
echo [3] --- Render 환경변수 동기화 ---
chcp 65001 >nul
start "Render Sync" cmd /k %PYTHON_PATH% run_ngrok_and_update_render.py

echo.
echo [✅] 모든 자동화 프로세스 시작 완료
pause
