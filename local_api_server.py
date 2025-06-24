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

# 💡 PyQt5 모듈 임포트 추가 (QAxWidget은 QAxContainer에서 가져옴)
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget 

# --- 모듈 경로 설정 ---
script_dir = os.path.dirname(os.path.abspath(__file__))
modules_path = os.path.join(script_dir, 'modules')
if modules_path not in sys.path:
    sys.path.insert(0, modules_path)

# --- 모듈 임포트 ---
from modules.Kiwoom.kiwoom_query_helper import KiwoomQueryHelper
from modules.Kiwoom.kiwoom_tr_request import KiwoomTrRequest
from modules.Kiwoom.monitor_positions import MonitorPositions
from modules.Kiwoom.trade_manager import TradeManager
# from modules.strategies.monitor_positions_strategy import monitor_positions_strategy # 💡 이제 MonitorPositions 클래스의 메서드로 통합됨

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

app_initialized = False 

shared_kiwoom_state = {
    "account_number": "N/A",
    "balance": 0,
    "positions": {},
    "last_update_time": None 
}
shared_state_lock = threading.Lock() 

# --- API 키 보안 인증 ---
RENDER_UPDATE_API_KEY = get_env("INTERNAL_API_KEY") 
if not RENDER_UPDATE_API_KEY:
    logger.critical("❌ INTERNAL_API_KEY 환경 변수 미설정 - 서버 종료")
    sys.exit(1)

LOCAL_API_KEY_FOR_STATUS = get_env("LOCAL_API_KEY")
if not LOCAL_API_KEY_FOR_STATUS:
    logger.critical("❌ LOCAL_API_KEY 환경 변수 미설정 (Flask status용) - 서버 종료")
    sys.exit(1)

def api_key_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key and api_key == LOCAL_API_KEY_FOR_STATUS:
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
    pyqt_app = None # QApplication 인스턴스
    kiwoom_ocx = None # QAxWidget 인스턴스

    try:
        import pythoncom
        pythoncom.CoInitialize() 
        logger.info("✅ pythoncom CoInitialize 완료 (백그라운드 트레이딩 스레드)")
        
        # 💡 QApplication 인스턴스 생성
        try:
            pyqt_app = QApplication([]) 
            logger.info("✅ 새로운 QApplication 인스턴스 생성 (백그라운드 트레이딩 스레드).")
        except Exception as qapp_e:
            logger.critical(f"❌ QApplication 생성 실패 (백그라운드 트레이딩 스레드): {qapp_e}")
            send_telegram_message(f"❌ QApplication 생성 실패: {qapp_e}")
            try:
                pythoncom.CoUninitialize()
            except Exception as e_uninit:
                logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")
            return False, None, None, None, None, None # 실패 시 함수 종료

        # 💡 QAxWidget 인스턴스 생성
        try:
            kiwoom_ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            logger.info("✅ QAxWidget 인스턴스 생성 완료.")
        except Exception as ocx_e:
            logger.critical(f"❌ QAxWidget 인스턴스 생성 실패 (백그라운드 트레이딩 스레드): {ocx_e}")
            send_telegram_message(f"❌ QAxWidget 생성 실패: {ocx_e}")
            if pyqt_app:
                pyqt_app.quit() # 생성된 QApplication 정리
            try:
                pythoncom.CoUninitialize()
            except Exception as e_uninit:
                logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")
            return False, None, None, None, None, None # 실패 시 함수 종료

        # 💡 kiwoom_helper에 ocx_instance, pyqt_app_instance 전달
        kiwoom_helper_thread = KiwoomQueryHelper(kiwoom_ocx, pyqt_app) 

        if not kiwoom_helper_thread.CommConnect(timeout_ms=60000): 
            logger.critical("❌ Kiwoom API 연결 실패 (백그라운드 트레이딩 스레드)")
            send_telegram_message("❌ Kiwoom API 연결 실패. 자동 매매 중단됨.")
            if kiwoom_helper_thread: 
                kiwoom_helper_thread.Disconnect()
            if pyqt_app:
                pyqt_app.quit()
            try:
                pythoncom.CoUninitialize()
            except Exception as e_uninit:
                logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")
            return False, None, None, None, None, None

        account_number = get_env("ACCOUNT_NUMBERS", "").split(',')[0].strip()
        account_password = get_env("ACCOUNT_PASSWORD", "") 

        if not account_number:
            account_number_from_api = kiwoom_helper_thread.get_login_info("ACCNO")
            if account_number_from_api:
                account_number = account_number_from_api.split(';')[0].strip()
            
        if not account_number:
            logger.critical("❌ 계좌번호를 가져올 수 없습니다 (백그라운드 트레이딩 스레드)")
            send_telegram_message("❌ 계좌번호 설정 오류. 자동 매매 중단됨.")
            kiwoom_helper_thread.Disconnect()
            if pyqt_app:
                pyqt_app.quit()
            try:
                pythoncom.CoUninitialize()
            except Exception as e_uninit:
                logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")
            return False, None, None, None, None, None

        kiwoom_tr_request_thread = KiwoomTrRequest(kiwoom_helper_thread) 
        
        logger.info(f"💡 Kiwoom API 초기화에 사용될 계좌번호: '{account_number}'")

        # MonitorPositions, TradeManager 초기화 순서 및 의존성 해결
        monitor_positions_thread = MonitorPositions(kiwoom_helper_thread, kiwoom_tr_request_thread, account_number) 
        trade_manager_thread = TradeManager(kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, account_number)
        
        # monitor_positions_strategy 함수를 직접 호출하는 방식이 아닌, 클래스 인스턴스에 메서드를 추가하고 호출하는 방식으로 변경
        # MonitorPositions 클래스 내에 monitor_positions_strategy 메서드를 직접 정의해야 함 (아직 안 했으면 TODO)
        monitor_positions_thread.trade_manager = trade_manager_thread # TradeManager 인스턴스를 MonitorPositions에 전달

        logger.info(f"✅ Kiwoom API 연결 완료 (백그라운드 트레이딩 스레드) - 계좌번호: {account_number}")
        
        with shared_state_lock:
            shared_kiwoom_state["account_number"] = account_number
            
            account_info = kiwoom_tr_request_thread.request_account_info(account_number, timeout_ms=30000) 
            
            if account_info and not account_info.get("error"): 
                shared_kiwoom_state["balance"] = account_info.get("예수금", 0)
                logger.info(f"💰 초기 계좌 잔고: {shared_kiwoom_state['balance']} KRW")
            else:
                error_msg = account_info.get("error", "알 수 없는 계좌 정보 조회 오류") if account_info else "계좌 정보 조회 결과 없음"
                logger.critical(f"❌ 계좌 정보 초기 조회 실패: {error_msg}")
                send_telegram_message(f"❌ 자동 매매 시작 실패: 계좌 정보 조회 실패. {error_msg}")
                kiwoom_helper_thread.Disconnect()
                if pyqt_app:
                    pyqt_app.quit()
                try:
                    pythoncom.CoUninitialize()
                except Exception as e_uninit:
                    logger.warning(f"CoUninitiaize 중 오류 발생: {e_uninit}")
                return False, None, None, None, None, None 

            # 초기 보유 종목 조회 및 실시간 등록
            monitor_positions_thread.register_all_positions_for_real_time_data()
            shared_kiwoom_state["positions"] = monitor_positions_thread.get_all_positions() 
            shared_kiwoom_state["last_update_time"] = get_current_time_str()

        global app_initialized
        app_initialized = True 
        
        return True, kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, trade_manager_thread, pyqt_app

    except Exception as e:
        logger.critical(f"❌ Kiwoom API 초기화 중 예외 발생 (백그라운드 트레이딩 스레드): {e}", exc_info=True)
        send_telegram_message(f"❌ 자동 매매 스레드 COM 초기화 실패: {e}")
        if kiwoom_helper_thread:
            kiwoom_helper_thread.Disconnect()
        if pyqt_app:
            pyqt_app.quit()
        try:
            pythoncom.CoUninitialize()
        except Exception as e_uninit:
                logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")
        return False, None, None, None, None, None


# --- 자동 매매 전략 백그라운드 루프 (메인 로직) ---
def background_trading_loop():
    logger.info("🔍 백그라운드 트레이딩 스레드 시작 중...")
    
    success, kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, trade_manager_thread, pyqt_app = \
        initialize_kiwoom_api_in_background_thread()
    
    if not success:
        logger.critical("❌ 백그라운드 트레이딩 스레드 초기화 실패. 스레드를 종료합니다.")
        return 

    logger.info("Ngrok 터널 활성화를 위해 5초 대기...")
    time_module.sleep(5)
    
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
                        'X-Internal-API-Key': RENDER_UPDATE_API_KEY 
                    }
                    update_response = requests.post(
                        render_update_endpoint,
                        json={"new_url": https_url},
                        headers=headers,
                        timeout=30 
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
            if time(9, 5) <= now.time() < time(15, 0): 
                logger.info(f"[{get_current_time_str()}] 매매 전략 탐색 및 실행 중...")
            elif now.time() >= time(15, 0) and now.time() < time(15, 20):
                logger.info(f"[{get_current_time_str()}] 장 마감 전 포지션 정리 시간.")
            elif now.time() >= time(15, 20) and now.time() < time(15, 30):
                logger.info(f"[{get_current_time_str()}] 장 마감 동시호가 시간. 추가 매매/매도 불가.")
            elif now.time() >= time(15, 30) or now.time() < time(9, 0):
                logger.info(f"[{get_current_time_str()}] 현재 매매 시간 아님. 대기 중...")

            # --- 포지션 모니터링 및 매도 전략 실행 (지속적으로 실행) ---
            # 💡 monitor_positions_strategy 함수를 MonitorPositions 클래스의 메서드로 호출
            #    TradeManager는 MonitorPositions.__init__에서 주입되므로 별도 인자 불필요
            monitor_positions_thread.monitor_positions_strategy()

            # Flask의 /status 엔드포인트를 위해 공유 상태 업데이트
            with shared_state_lock:
                shared_kiwoom_state["positions"] = monitor_positions_thread.get_all_positions() 
                account_info = kiwoom_tr_request_thread.request_account_info(shared_kiwoom_state["account_number"])
                shared_kiwoom_state["balance"] = account_info.get("예수금", 0)
                shared_kiwoom_state["last_update_time"] = get_current_time_str()

            time_module.sleep(30) 

        except Exception as e:
            msg = f"🔥 백그라운드 트레이딩 루프 오류 발생: {e}"
            logger.exception(msg)
            send_telegram_message(msg)
            time_module.sleep(60)
        finally:
            # 💡 애플리케이션 종료 시 PyQt 앱 종료
            if pyqt_app:
                pyqt_app.quit()
            try:
                pythoncom.CoUninitialize()
            except Exception as e_uninit:
                logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")


# --- Flask 엔드포인트 ---
@app.route('/')
def home():
    return "Local API Server is running!"

@app.route('/status')
@api_key_required
def status():
    if not app_initialized:
        return jsonify({"status": "error", "message": "백그라운드 트레이딩 시스템이 아직 초기화되지 않았습니다."}), 503
    
    with shared_state_lock:
        status_data = {
            "status": "ok",
            "server_time": get_current_time_str(), 
            "account_number": shared_kiwoom_state["account_number"],
            "balance": shared_kiwoom_state["balance"],
            "positions": shared_kiwoom_state["positions"],
            "last_kiwoom_update": shared_kiwoom_state["last_update_time"]
        }
    return jsonify(status_data)

# --- Flask 서버 실행 ---
if __name__ == '__main__':
    trading_thread = threading.Thread(target=background_trading_loop, daemon=True)
    trading_thread.start()
    
    logger.info("📡 Flask 서버 시작 준비 중...")
    
    init_timeout = 120 
    start_time = time_module.time()
    while not app_initialized and (time_module.time() - start_time) < init_timeout:
        time_module.sleep(1)
    
    if not app_initialized:
        logger.critical("❌ Kiwoom API 초기화 실패 (백그라운드 트레이딩 스레드). 서버 시작을 중단합니다.")
        send_telegram_message("❌ Kiwoom API 초기화 실패. 자동 매매 중단됨.")
        sys.exit(1)
        
    logger.info(f"🚀 Flask 서버 실행: http://0.0.0.0:{API_SERVER_PORT}")
    app.run(host="0.0.0.0", port=int(API_SERVER_PORT), debug=True, use_reloader=False)

