@echo off
chcp 65001 > nul
setlocal

REM === 사용자 설정 ===
set NGROK_PATH=C:\ngrok\ngrok.exe
set PYTHON_EXEC=C:\Users\user\stock_auto\venv\Scripts\python.exe
set SERVER_SCRIPT=local_api_server.py

REM === ngrok 실행 ===
start "ngrok" cmd /k "%NGROK_PATH% http 5000 --region=jp"

echo [INFO] ngrok이 시작될 때까지 5초간 대기 중...
timeout /t 5 /nobreak > nul

REM === Flask + PyQt 통합 서버 실행 ===
start "auto_trade_server" cmd /k "%PYTHON_EXEC% %SERVER_SCRIPT%"

echo [INFO] 자동매매 서버 구동 완료. 창을 닫지 마세요!
pause
