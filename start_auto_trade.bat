@echo off
chcp 65001 > nul
setlocal

REM === 사용자 설정 ===
REM Python 가상 환경의 python.exe 경로를 지정하세요.
set PYTHON_EXEC=C:\Users\user\stock_auto\venv\Scripts\python.exe
REM Flask + PyQt 통합 서버 스크립트 파일명
set SERVER_SCRIPT_NAME=local_api_server.py
REM 배치 파일이 위치한 디렉토리 경로를 기준으로 서버 스크립트의 전체 경로 설정
set SERVER_SCRIPT_FULL_PATH=%~dp0%SERVER_SCRIPT_NAME%

REM === 경로 확인 ===
if not exist "%PYTHON_EXEC%" (
    echo.
    echo ❌ 오류: PYTHON_EXEC 경로에 python.exe가 없습니다. 경로를 확인해주세요: %PYTHON_EXEC%
    echo.
    pause
    exit /b 1
)
if not exist "%SERVER_SCRIPT_FULL_PATH%" (
    echo.
    echo ❌ 오류: SERVER_SCRIPT_FULL_PATH 경로에 %SERVER_SCRIPT_NAME%가 없습니다. 경로를 확인해주세요: %SERVER_SCRIPT_FULL_PATH%
    echo.
    pause
    exit /b 1
)

echo -----------------------------------------------------
echo      자동매매 시스템 통합 실행 스크립트 시작
echo -----------------------------------------------------

REM 1. Flask + PyQt 통합 서버 실행 (새로운 CMD 창에서)
echo.
echo 🌐 Flask API 서버 시작 중...
echo -----------------------------------------------------
start "Local API Server Console" cmd /k "%PYTHON_EXEC% %SERVER_SCRIPT_FULL_PATH%"

echo.
echo -----------------------------------------------------
echo ✅ 모든 스크립트 실행 명령 완료.
echo -----------------------------------------------------

pause
