# C:\Users\user\stock_auto\run_all.py

import subprocess
import os
import time

# --- 설정 (경로를 정확히 확인하고 수정하세요) ---
NGROK_PATH = r"C:\ngrok\ngrok.exe"
LOCAL_API_SERVER_SCRIPT_PATH = r"C:\Users\user\stock_auto\local_api_server.py"
PYTHON_VENV_PATH = r"C:\Users\user\stock_auto\venv\Scripts\python.exe"
# --- 설정 끝 ---

def start_ngrok():
    """ngrok을 실행하여 로컬 5000번 포트를 외부에 노출시킵니다."""
    print("-----------------------------------------------------")
    print("1. ngrok 실행 중...")
    print(f"   ngrok 실행 파일: {NGROK_PATH}")
    print("-----------------------------------------------------")

    try:
        # ngrok을 백그라운드에서 실행하고 출력을 리디렉션합니다.
        # ngrok 콘솔이 직접 보이지 않도록 함
        # 실제 ngrok 콘솔은 따로 열어서 Forwarding 주소를 확인해야 합니다.
        # subprocess.Popen([NGROK_PATH, "http", "5000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 개발/디버깅을 위해 ngrok 콘솔을 열어두는 것이 좋습니다.
        # 실제 사용 시에는 이 주석을 해제하고 위 Popen 라인을 사용하세요.
        subprocess.Popen([NGROK_PATH, "http", "5000"]) # ngrok 콘솔이 열림
        
        print("\n=> ngrok이 시작되었습니다. 별도로 열린 ngrok 콘솔에서 'Forwarding' 주소를 확인하세요.")
        print("   이 주소를 Render 환경 변수 'LOCAL_API_SERVER_URL'에 업데이트해야 합니다.")
        print("   (ngrok 무료 버전은 재실행 시 주소가 바뀔 수 있습니다.)")
        time.sleep(5) # ngrok이 완전히 시작될 시간을 줍니다.

    except FileNotFoundError:
        print(f"오류: ngrok 실행 파일을 찾을 수 없습니다. 경로를 확인하세요: {NGROK_PATH}")
        return False
    except Exception as e:
        print(f"ngrok 실행 중 오류 발생: {e}")
        return False
    return True

def start_local_api_server():
    """local_api_server.py를 가상 환경에서 실행합니다."""
    print("\n-----------------------------------------------------")
    print("2. local_api_server.py 실행 중...")
    print(f"   Python 인터프리터: {PYTHON_VENV_PATH}")
    print(f"   서버 스크립트: {LOCAL_API_SERVER_SCRIPT_PATH}")
    print("-----------------------------------------------------")

    try:
        # local_api_server.py를 백그라운드에서 실행
        # stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL 로 설정하면 콘솔에 출력이 안됩니다.
        # 디버깅을 위해 별도 터미널에 띄우는 것이 좋습니다.
        # 이 스크립트가 종료되어도 서버는 계속 실행됩니다.
        
        # 현재는 별도의 콘솔창을 띄워 서버 로그를 직접 볼 수 있도록 설정합니다.
        # 이는 디버깅과 상태 확인에 용이합니다.
        # Windows 환경에서는 'start' 명령을 통해 새 콘솔 창에서 실행할 수 있습니다.
        
        command = [
            "start", # 새 창에서 실행 (Windows 전용)
            "cmd", "/k", # CMD 창 유지 (자동 종료 방지)
            PYTHON_VENV_PATH, LOCAL_API_SERVER_SCRIPT_PATH
        ]
        
        # shell=True를 사용해야 'start' 명령어가 작동합니다.
        subprocess.Popen(command, shell=True) 

        print("\n=> local_api_server.py가 새 콘솔 창에서 실행되었습니다.")
        print("   서버 로그를 확인하려면 해당 콘솔 창을 확인하세요.")
        print("   (이 서버 창을 닫으면 자동매매가 중단됩니다.)")

    except FileNotFoundError:
        print(f"오류: Python 인터프리터 또는 local_api_server.py를 찾을 수 없습니다.")
        print(f"   Python 경로: {PYTHON_VENV_PATH}")
        print(f"   Server Script 경로: {LOCAL_API_SERVER_SCRIPT_PATH}")
        return False
    except Exception as e:
        print(f"local_api_server.py 실행 중 오류 발생: {e}")
        return False
    return True

if __name__ == "__main__":
    print("-----------------------------------------------------")
    print("     자동매매 시스템 통합 실행 스크립트 시작")
    print("-----------------------------------------------------")

    # 1. ngrok 실행
    ngrok_started = start_ngrok()
    if not ngrok_started:
        print("\n[!] ngrok 실행에 실패하여 시스템 시작을 중단합니다.")
        input("오류를 확인 후 아무 키나 눌러 종료하세요...")
        exit(1)

    # 2. local_api_server.py 실행
    server_started = start_local_api_server()
    if not server_started:
        print("\n[!] local_api_server.py 실행에 실패하여 시스템 시작을 중단합니다.")
        input("오류를 확인 후 아무 키나 눌러 종료하세요...")
        exit(1)

    print("\n-----------------------------------------------------")
    print("     모든 스크립트 실행 명령 완료.")
    print("-----------------------------------------------------")
    print("\n[중요] 다음 단계를 수행하세요:")
    print("1. ngrok 콘솔에서 'Forwarding' 주소 (https://...)를 확인하세요.")
    print("2. Render 대시보드에 접속하여 해당 주소를 'LOCAL_API_SERVER_URL' 환경 변수에 업데이트하세요.")
    print("3. Render 서비스가 재배포될 때까지 기다리세요.")
    print("4. 텔레그램 봇으로 /status 명령을 보내 시스템이 정상 작동하는지 확인하세요.")
    print("\n이 콘솔 창은 닫아도 됩니다. (ngrok 콘솔과 local_api_server 콘솔은 유지해야 함)")
    input("완료하려면 아무 키나 누르세요...")