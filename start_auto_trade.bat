@echo off
chcp 65001 > nul
setlocal

:: -------- 설정 시작 --------
:: ngrok.exe 파일의 전체 경로를 지정하세요.
set NGROK_PATH=C:\ngrok\ngrok.exe
:: Python 가상 환경의 python.exe 경로를 지정하세요.
set PYTHON_PATH=C:\Users\user\stock_auto\venv\Scripts\python.exe
:: Flask + PyQt 통합 서버 스크립트 파일의 전체 경로를 지정하세요.
set API_SERVER_SCRIPT=C:\Users\user\stock_auto\local_api_server.py
:: -------- 설정 끝 ----------

:: === 경로 존재 여부 확인 (견고성을 위해 다시 추가) ===
if not exist "%NGROK_PATH%" (
    echo ❌ 오류: NGROK_PATH 경로에 ngrok.exe가 없습니다. 경로를 확인해주세요: %NGROK_PATH%
    pause
    exit /b 1
)
if not exist "%PYTHON_PATH%" (
    echo ❌ 오류: PYTHON_PATH 경로에 python.exe가 없습니다. 가상 환경 경로를 확인해주세요: %PYTHON_PATH%
    pause
    exit /b 1
)
if not exist "%API_SERVER_SCRIPT%" (
    echo ❌ 오류: API_SERVER_SCRIPT 경로에 local_api_server.py가 없습니다. 경로를 확인해주세요: %API_SERVER_SCRIPT%
    pause
    exit /b 1
)

echo -----------------------------------------------------
echo      자동매매 시스템 통합 실행 스크립트 시작
echo -----------------------------------------------------

echo.
echo [1/2] ngrok 시작 중...
echo    ngrok 실행 파일: %NGROK_PATH%
echo    로컬 5000번 포트를 외부에 노출합니다.
echo    사용 리전: jp
echo -----------------------------------------------------
start "ngrok Console" cmd /k "%NGROK_PATH% http 5000 --region=jp"

echo.
echo ngrok이 완전히 시작될 때까지 6초간 대기 중...
timeout /t 6 /nobreak > nul

echo.
echo [2/2] local_api_server.py 실행 중...
echo    Python 실행 파일: %PYTHON_PATH%
echo    서버 스크립트: %API_SERVER_SCRIPT%
echo -----------------------------------------------------
start "Local API Server Console" cmd /k "%PYTHON_PATH% %API_SERVER_SCRIPT%"

echo.
echo -----------------------------------------------------
echo ✅ 모든 프로세스 실행 요청 완료.
echo -----------------------------------------------------
echo.
echo [중요] 다음 단계를 수행하세요:
echo 1. ngrok 콘솔에서 'Forwarding' 주소 (https://...)를 확인하세요.
echo 2. 웹 브라우저에서 http://127.0.0.1:5000 에 접속하여 대시보드를 확인하세요.
echo 3. 텔레그램 봇에게 /status 명령을 보내 알림을 확인하세요.
echo 4. Render 서버의 웹훅 URL이 올바르게 설정되었는지 확인하세요.

pause
