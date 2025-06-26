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
from modules.strategies.monitor_positions_strategy import monitor_positions_strategy 
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

# --- Kiwoom API 초기화 ---
def initialize_kiwoom_api_in_background_thread():
    """
    백그라운드 트레이딩 스레드에서 Kiwoom API 및 관련 객체들을 초기화합니다.
    모든 COM 객체는 이 스레드 내에서 생성되고 사용되어야 합니다.
    """
    kiwoom_helper_thread = None
    kiwoom_tr_request_thread = None
    monitor_positions_thread = None
    trade_manager_thread = None
    pyqt_app = None
    kiwoom_ocx = None

    try:
        import pythoncom
        pythoncom.CoInitialize()
        logger.info("✅ pythoncom CoInitialize 완료 (백그라운드 트레이딩 스레드)")

        try:
            pyqt_app = QApplication([])
            logger.info("✅ 새로운 QApplication 인스턴스 생성 (백그라운드 트레이딩 스레드).")
        except Exception as qapp_e:
            logger.critical(f"❌ QApplication 생성 실패: {qapp_e}")
            return False, None, None, None, None

        try:
            kiwoom_ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
            logger.info("✅ QAxWidget 인스턴스 생성 완료.")
        except Exception as ocx_e:
            logger.critical(f"❌ QAxWidget 생성 실패: {ocx_e}")
            return False, None, None, None, None

        kiwoom_helper_thread = KiwoomQueryHelper(kiwoom_ocx, pyqt_app)

        if not kiwoom_helper_thread.connect_kiwoom(timeout_ms=10000):
            logger.critical("❌ Kiwoom API 연결 실패")
            return False, None, None, None, None

        account_number = get_env("ACCOUNT_NUMBERS", "").split(',')[0].strip()
        account_password = get_env("ACCOUNT_PASSWORD", "").strip()

        if not account_number:
            account_number = kiwoom_helper_thread.get_login_info("ACCNO").split(';')[0].strip()

        kiwoom_tr_request_thread = KiwoomTrRequest(kiwoom_helper_thread, pyqt_app, account_password)

        logger.info(f"💡 Kiwoom API 초기화에 사용될 계좌번호: '{account_number}'")

        monitor_positions_thread = MonitorPositions(kiwoom_helper_thread, kiwoom_tr_request_thread, None, account_number)
        trade_manager_thread = TradeManager(kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, account_number)
        monitor_positions_thread.trade_manager = trade_manager_thread

        logger.info(f"✅ Kiwoom API 연결 완료 (백그라운드 트레이딩 스레드) - 계좌번호: {account_number}")

        # ✅ 여기서 계좌 정보 요청할 때 수정된 부분입니다
        account_info = kiwoom_tr_request_thread.request_account_info(account_number, timeout_ms=30000)

        if account_info and not account_info.get("error"):
            shared_kiwoom_state["balance"] = account_info.get("예수금", 0)
            logger.info(f"💰 초기 계좌 잔고: {shared_kiwoom_state['balance']} KRW")
        else:
            error_msg = account_info.get("error", "알 수 없는 계좌 정보 조회 오류") if account_info else "계좌 정보 조회 결과 없음"
            logger.critical(f"❌ 계좌 정보 초기 조회 실패: {error_msg}")
            return False, None, None, None, None

        shared_kiwoom_state["last_update_time"] = get_current_time_str()
        global app_initialized
        app_initialized = True

        return True, kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, trade_manager_thread

    except Exception as e:
        logger.critical(f"❌ Kiwoom API 초기화 중 예외 발생: {e}", exc_info=True)
        return False, None, None, None, None

# --- 백그라운드 매매 루프 ---
def background_trading_loop():
    logger.info("🔍 백그라운드 트레이딩 스레드 시작 중...")
    success, kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, trade_manager_thread = \
        initialize_kiwoom_api_in_background_thread()
    if not success:
        logger.critical("❌ 초기화 실패")
        return 

    while True:
        try:
            now = datetime.now()
            if time(9, 5) <= now.time() < time(15, 0):
                logger.info(f"[{get_current_time_str()}] 매매 전략 실행 중...")
            monitor_positions_strategy(monitor_positions_thread, trade_manager_thread)
            with shared_state_lock:
                shared_kiwoom_state["positions"] = monitor_positions_thread.get_all_positions()
                shared_kiwoom_state["last_update_time"] = get_current_time_str()
            time_module.sleep(30)
        except Exception as e:
            logger.exception(f"🔥 루프 오류: {e}")
            send_telegram_message(f"🔥 루프 오류: {e}")
            time_module.sleep(60)


# --- Flask API ---
@app.route('/')
def home():
    return "Local API Server is running!"

@app.route('/status')
@api_key_required
def status():
    if not app_initialized:
        return jsonify({"status": "error", "message": "초기화되지 않음"}), 503
    with shared_state_lock:
        return jsonify({
            "status": "ok",
            "server_time": get_current_time_str(),
            "account_number": shared_kiwoom_state["account_number"],
            "balance": shared_kiwoom_state["balance"],
            "positions": shared_kiwoom_state["positions"],
            "last_kiwoom_update": shared_kiwoom_state["last_update_time"]
        })

if __name__ == '__main__':
    trading_thread = threading.Thread(target=background_trading_loop, daemon=True)
    trading_thread.start()

    init_timeout = 120
    start_time = time_module.time()
    while not app_initialized and (time_module.time() - start_time) < init_timeout:
        time_module.sleep(1)

    if not app_initialized:
        logger.critical("❌ Kiwoom API 초기화 실패. 서버 종료.")
        send_telegram_message("❌ Kiwoom API 초기화 실패")
        sys.exit(1)

    logger.info(f"🚀 Flask 서버 실행: http://0.0.0.0:{API_SERVER_PORT}")
    app.run(host="0.0.0.0", port=int(API_SERVER_PORT), debug=True, use_reloader=False)
