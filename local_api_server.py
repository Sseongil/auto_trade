import os
import sys
import json
import logging
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from datetime import datetime, time
import threading
import time as time_module

# --- 모듈 경로 설정 ---
script_dir = os.path.dirname(os.path.abspath(__file__))
modules_path = os.path.join(script_dir, 'modules')
if modules_path not in sys.path:
    sys.path.insert(0, modules_path)

# --- 모듈 임포트 ---
# Kiwoom 관련 클래스는 백그라운드 스레드에서 인스턴스를 생성하므로, 여기서는 클래스만 임포트합니다.
from modules.Kiwoom.kiwoom_query_helper import KiwoomQueryHelper
from modules.Kiwoom.kiwoom_tr_request import KiwoomTrRequest
from modules.Kiwoom.monitor_positions import MonitorPositions
from modules.Kiwoom.trade_manager import TradeManager
from modules.Kiwoom.monitor_positions_strategy import monitor_positions_strategy
from modules.common.config import get_env, API_SERVER_PORT
from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 환경 변수 로드 ---
load_dotenv()

# --- Flask 앱 초기화 ---
app = Flask(__name__)

# 백그라운드 트레이딩 스레드가 Kiwoom 초기화를 완료했는지 나타내는 플래그
# 메인 스레드 (Flask)와 백그라운드 스레드 간의 동기화에 사용
app_initialized = False 

# 백그라운드 스레드와 Flask 메인 스레드 간에 안전하게 공유될 Kiwoom 상태 데이터
# 이 데이터는 백그라운드 스레드에서 주기적으로 업데이트하고, Flask 엔드포인트에서 안전하게 읽습니다.
shared_kiwoom_state = {
    "account_number": "N/A",
    "balance": 0,
    "positions": {},
    "last_update_time": None # 마지막으로 공유 상태가 업데이트된 시간
}
# 공유 데이터 접근 시 사용될 락 (Race Condition 방지)
shared_state_lock = threading.Lock() 

# --- API 키 보안 인증 ---
LOCAL_API_KEY = get_env("LOCAL_API_KEY")
if not LOCAL_API_KEY:
    logger.critical("❌ LOCAL_API_KEY 환경 변수 미설정 - 서버 종료")
    sys.exit(1)

def api_key_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key and api_key == LOCAL_API_KEY:
            return f(*args, **kwargs)
        else:
            logger.warning(f"❌ 인증 실패 - 유효하지 않은 API 키: {request.remote_addr}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return wrapper

# --- Kiwoom API 초기화 (백그라운드 트레이딩 스레드에서만 호출될 함수) ---
def initialize_kiwoom_api_in_background_thread():
    """
    백그라운드 트레이딩 스레드에서 Kiwoom API 및 관련 객체들을 초기화합니다.
    모든 COM 객체는 이 스레드 내에서 생성되고 사용되어야 합니다.
    """
    kiwoom_helper_thread = None
    kiwoom_tr_request_thread = None
    monitor_positions_thread = None
    trade_manager_thread = None

    try:
        import pythoncom
        # 현재 스레드에 COM 라이브러리 초기화 (Single-Threaded Apartment 모델)
        pythoncom.CoInitialize() 
        logger.info("✅ pythoncom CoInitialize 완료 (백그라운드 트레이딩 스레드)")
    except Exception as e:
        logger.critical(f"❌ pythoncom 초기화 실패 (백그라운드 스레드): {e}")
        send_telegram_message(f"❌ 자동 매매 스레드 COM 초기화 실패: {e}")
        return False, None, None, None, None

    account_number = get_env("ACCOUNT_NUMBERS", "").split(',')[0].strip()
    
    try:
        kiwoom_helper_thread = KiwoomQueryHelper()
        if not kiwoom_helper_thread.connect_kiwoom():
            logger.critical("❌ Kiwoom API 연결 실패 (백그라운드 트레이딩 스레드)")
            send_telegram_message("❌ Kiwoom API 연결 실패. 자동 매매 중단됨.")
            # 실패 시 COM 객체 정리 시도
            if kiwoom_helper_thread: 
                kiwoom_helper_thread.disconnect_kiwoom()
            try:
                pythoncom.CoUninitialize()
            except Exception as e_uninit:
                logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")
            return False, None, None, None, None

        if not account_number:
            # 계좌번호가 .env에 없으면 Kiwoom API를 통해 조회
            account_number_from_api = kiwoom_helper_thread.get_login_info("ACCNO")
            if account_number_from_api:
                account_number = account_number_from_api.split(';')[0].strip()
            
        if not account_number:
            logger.critical("❌ 계좌번호를 가져올 수 없습니다 (백그라운드 트레이딩 스레드)")
            send_telegram_message("❌ 계좌번호 설정 오류. 자동 매매 중단됨.")
            kiwoom_helper_thread.disconnect_kiwoom()
            try:
                pythoncom.CoUninitialize()
            except Exception as e_uninit:
                logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")
            return False, None, None, None, None

        kiwoom_tr_request_thread = KiwoomTrRequest(kiwoom_helper_thread)
        monitor_positions_thread = MonitorPositions(kiwoom_helper_thread, kiwoom_tr_request_thread, account_number)
        trade_manager_thread = TradeManager(kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, account_number)
        
        logger.info(f"✅ Kiwoom API 연결 완료 (백그라운드 트레이딩 스레드) - 계좌번호: {account_number}")
        
        # Kiwoom 초기화 성공 후, 공유 상태 업데이트
        with shared_state_lock:
            shared_kiwoom_state["account_number"] = account_number
            # 초기 잔고 및 포지션 정보 로드 및 공유 상태에 저장
            account_info = kiwoom_tr_request_thread.request_account_info(account_number)
            shared_kiwoom_state["balance"] = account_info.get("예수금", 0)
            shared_kiwoom_state["positions"] = monitor_positions_thread.get_current_positions()
            shared_kiwoom_state["last_update_time"] = get_current_time_str()

        global app_initialized
        app_initialized = True # 백그라운드 트레이딩 시스템이 성공적으로 준비되었음을 메인 스레드에 알림
        
        return True, kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, trade_manager_thread

    except Exception as e:
        logger.critical(f"❌ Kiwoom API 초기화 중 예외 발생 (백그라운드 스레드): {e}", exc_info=True)
        send_telegram_message(f"❌ Kiwoom API 초기화 중 예외 발생: {e}")
        # 오류 발생 시 COM 객체 및 리소스 정리
        if kiwoom_helper_thread:
            kiwoom_helper_thread.disconnect_kiwoom()
        try:
            pythoncom.CoUninitialize()
        except Exception as e_uninit:
            logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")
        return False, None, None, None, None


# --- 자동 매매 전략 백그라운드 루프 (메인 로직) ---
def background_trading_loop(): # 함수명 변경 (더 포괄적인 역할)
    logger.info("🔍 백그라운드 트레이딩 스레드 시작 중...")
    
    # Kiwoom API 및 관련 객체들을 이 스레드 내에서 초기화
    success, kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, trade_manager_thread = \
        initialize_kiwoom_api_in_background_thread()
    
    if not success:
        logger.critical("❌ 백그라운드 트레이딩 스레드 초기화 실패. 스레드를 종료합니다.")
        return # 초기화 실패 시 스레드 종료

    # NOTE: Kiwoom API가 성공적으로 연결된 후 ngrok URL 업데이트 로직을 추가합니다.
    # 이 부분은 main.py (최상위 실행 파일)에서 Ngrok 터널을 실행하고,
    # 그 URL을 Render 서버로 전송하는 로직을 통합하는 것이 더 좋습니다.
    # 하지만 현재 구조에서는 이 백그라운드 스레드가 Kiwoom 초기화 후 ngrok URL을 전송하는 것이 다음 로직입니다.
    # 이전에 지적했던 `401 Unauthorized` 오류와 관련된 부분입니다.
    # 이 로직은 백그라운드 스레드에서 실행되어야 하며,
    # Flask 앱이 시작하기 전에 먼저 Kiwoom 연결 및 ngrok 업데이트를 완료하는 것이 중요합니다.
    
    # Kiwoom API 초기화 후 ngrok 터널이 뜰 충분한 시간을 줌 (ngrok이 이 스레드에서 실행된다고 가정)
    logger.info("Ngrok 터널 활성화를 위해 5초 대기...")
    time_module.sleep(5)
    
    # ngrok URL 감지 및 Render 업데이트 로직 (이전에 제시했던 detect_and_notify_ngrok 함수를 여기에 구현)
    # 이 함수는 외부(main.py)에서 ngrok을 관리하고 업데이트 요청하는 것이 더 깔끔하나,
    # 백그라운드 스레드에서 Kiwoom API 초기화 후 바로 이어지는 흐름으로 가정
    # (여기서는 임시로 함수 내용을 직접 넣습니다. 실제로는 함수로 분리하여 호출)
    try:
        ngrok_port = get_env("NGROK_API_PORT", "4040")
        response = requests.get(f"http://127.0.0.1:{ngrok_port}/api/tunnels", timeout=5)
        response.raise_for_status()
        tunnels = response.json().get("tunnels", [])
        https_url = next((t["public_url"] for t in tunnels if t["proto"] == "https"), None)

        if https_url:
            logger.info(f"📡 Ngrok URL 감지됨: {https_url}")
            send_telegram_message(f"📡 새로운 ngrok URL 감지:\n`{https_url}`")

            render_public_url = get_env("RENDER_PUBLIC_URL")
            if render_public_url:
                render_update_endpoint = f"{render_public_url.rstrip('/')}/update_ngrok_internal"
                try:
                    logger.info(f"🌐 Render 서버로 ngrok URL 업데이트 요청 중: {render_update_endpoint}")
                    headers = {
                        'Content-Type': 'application/json',
                        'X-Internal-API-Key': LOCAL_API_KEY # Render 서버의 /update_ngrok_internal 엔드포인트에 인증용 키 전송
                    }
                    update_response = requests.post(
                        render_update_endpoint,
                        json={"new_url": https_url},
                        headers=headers,
                        timeout=30 # 타임아웃을 30초로 늘림 (이전 문제 해결 목적)
                    )
                    update_response.raise_for_status()
                    logger.info(f"✅ Render 서버 응답: {update_response.status_code} - {update_response.text}")
                except requests.exceptions.RequestException as req_e:
                    logger.warning(f"⚠️ Render 서버로 ngrok URL 업데이트 요청 실패: {req_e}")
                    send_telegram_message(f"⚠️ Render URL 업데이트 실패: {req_e}")
                except Exception as e_inner:
                    logger.warning(f"⚠️ Render 서버 업데이트 중 예기치 않은 오류: {e_inner}")
                    send_telegram_message(f"⚠️ Render URL 업데이트 중 오류: {e_inner}")
            else:
                logger.warning("RENDER_PUBLIC_URL 환경 변수가 설정되지 않아 Render 서버에 업데이트를 보낼 수 없습니다.")
        else:
            logger.warning("❌ HTTPS Ngrok 터널을 찾지 못했습니다.")
            send_telegram_message("❌ Ngrok 터널 감지 실패.")
    except requests.exceptions.RequestException as req_e:
        logger.error(f"❌ Ngrok API 접근 실패: {req_e} - ngrok이 실행 중인지, 포트가 맞는지 확인하세요.")
        send_telegram_message(f"❌ Ngrok API 접근 실패: {req_e}")
    except Exception as e:
        logger.error(f"❌ Ngrok URL 감지 및 알림 실패: {e}", exc_info=True)
        send_telegram_message(f"❌ Ngrok URL 감지 및 알림 실패: {e}")

    # --- 메인 트레이딩 루프 ---
    while True:
        try:
            now = datetime.now()
            # 매매 시간 (09:05 ~ 15:00)에만 매매 전략 실행
            # monitor_positions_strategy가 15:20 이후 정리 로직을 포함하므로 시간대 조정 필요
            if time(9, 5) <= now.time() < time(15, 0): # 매수 신호 탐색 및 매수 진행 시간
                # TODO: 여기에 종목 검색 및 매수 결정 로직을 통합합니다.
                # (예: check_and_execute_buy_strategy(kiwoom_helper_thread, kiwoom_tr_request_thread, trade_manager_thread, monitor_positions_thread))
                # 이 예시에서는 생략하지만, 실제로는 여기에 단타 검색식 및 점수화 로직이 들어갑니다.
                logger.info(f"[{get_current_time_str()}] 매매 전략 탐색 및 실행 중...")
            elif now.time() >= time(15, 0) and now.time() < time(15, 20): # 장 마감 직전 정리 시간
                logger.info(f"[{get_current_time_str()}] 장 마감 전 포지션 정리 시간.")
            elif now.time() >= time(15, 20) and now.time() < time(15, 30): # 장 마감 동시호가 시간
                logger.info(f"[{get_current_time_str()}] 장 마감 동시호가 시간. 추가 매매/매도 불가.")
            elif now.time() >= time(15, 30) or now.time() < time(9, 0): # 장 종료 후/개장 전
                logger.info(f"[{get_current_time_str()}] 현재 매매 시간 아님. 대기 중...")

            # --- 포지션 모니터링 및 매도 전략 실행 (지속적으로 실행) ---
            # 모든 보유 포지션에 대한 익절/손절/트레일링 스탑/시간 손절/장 마감 정리를 여기서 처리
            monitor_positions_strategy(monitor_positions_thread, trade_manager_thread)

            # Flask의 /status 엔드포인트를 위해 공유 상태 업데이트
            with shared_state_lock:
                shared_kiwoom_state["positions"] = monitor_positions_thread.get_current_positions()
                # 계좌 잔고는 TR 요청이 필요하므로, 자주 호출하면 API 제한에 걸릴 수 있습니다.
                # 필요하다면 훨씬 낮은 빈도(예: 1분마다 1번)로 업데이트하거나,
                # 주문 체결 시점에만 업데이트하도록 trade_manager에서 호출하는 것이 좋습니다.
                # 여기서는 30초마다 업데이트한다고 가정
                account_info = kiwoom_tr_request_thread.request_account_info(shared_kiwoom_state["account_number"])
                shared_kiwoom_state["balance"] = account_info.get("예수금", 0)
                shared_kiwoom_state["last_update_time"] = get_current_time_str()

            time_module.sleep(30)  # 매 30초마다 모든 작업(검색, 매매, 모니터링) 주기

        except Exception as e:
            msg = f"🔥 백그라운드 트레이딩 루프 오류 발생: {e}"
            logger.exception(msg)
            send_telegram_message(msg)
            time_module.sleep(60) # 오류 발생 시 긴 대기 후 재시도
        finally:
            # 데몬 스레드이므로 애플리케이션 종료 시 Python 런타임이 자동으로 정리합니다.
            pass


# --- Flask 엔드포인트 ---
@app.route('/')
def home():
    return "Local API Server is running!"

@app.route('/status')
@api_key_required
def status():
    # Flask 스레드에서는 Kiwoom COM 객체에 직접 접근하지 않고, 공유된 상태를 읽습니다.
    if not app_initialized:
        return jsonify({"status": "error", "message": "백그라운드 트레이딩 시스템이 아직 초기화되지 않았습니다."}), 503
    
    with shared_state_lock:
        status_data = {
            "status": "ok",
            "server_time": get_current_time_str(), # 현재 서버 시간
            "account_number": shared_kiwoom_state["account_number"],
            "balance": shared_kiwoom_state["balance"],
            "positions": shared_kiwoom_state["positions"],
            "last_kiwoom_update": shared_kiwoom_state["last_update_time"] # Kiwoom 상태 마지막 업데이트 시간
        }
    return jsonify(status_data)

# --- Flask 서버 실행 ---
if __name__ == '__main__':
    # Kiwoom API 및 트레이딩 로직을 담당할 백그라운드 스레드 시작
    # daemon=True 설정으로 메인 스레드 종료 시 함께 종료되도록 함
    trading_thread = threading.Thread(target=background_trading_loop, daemon=True)
    trading_thread.start()
    
    logger.info("📡 Flask 서버 시작 준비 중...")
    
    # 백그라운드 스레드가 Kiwoom API 초기화를 완료할 때까지 기다림
    # app_initialized 플래그가 백그라운드 스레드에서 설정될 때까지 대기
    init_timeout = 120 # 최대 120초(2분) 대기 (COM 초기화, 로그인, Ngrok 업데이트까지 충분한 시간)
    start_time = time_module.time()
    while not app_initialized and (time_module.time() - start_time) < init_timeout:
        time_module.sleep(1) # 1초마다 확인
    
    if not app_initialized:
        logger.critical("❌ Kiwoom API 초기화 실패 (백그라운드 트레이딩 스레드). 서버 시작을 중단합니다.")
        send_telegram_message("❌ Kiwoom API 초기화 실패. 자동 매매 중단됨.")
        sys.exit(1) # 초기화 실패 시 애플리케이션 종료
        
    logger.info(f"🚀 Flask 서버 실행: http://0.0.0.0:{API_SERVER_PORT}")
    # Flask 앱을 메인 스레드에서 실행
    # debug=True는 개발 중에는 유용하지만, 프로덕션에서는 False로 설정해야 합니다.
    # use_reloader=False는 Kiwoom API와 같은 COM 객체 사용 시 충돌 방지를 위해 필수입니다.
    app.run(host="0.0.0.0", port=int(API_SERVER_PORT), debug=True, use_reloader=False)