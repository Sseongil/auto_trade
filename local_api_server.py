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
from modules.strategies.main_strategy_loop import run_daily_trading_cycle
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

# --- Kiwoom API 초기화 (백그라운드 트레이딩 스레드에서만 호출될 함수) ---
def initialize_kiwoom_api_in_background_thread():
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

        pyqt_app = QApplication([])
        logger.info("✅ 새로운 QApplication 인스턴스 생성 (백그라운드 트레이딩 스레드)")

        kiwoom_ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        logger.info("✅ QAxWidget 인스턴스 생성 완료")

        kiwoom_helper_thread = KiwoomQueryHelper(kiwoom_ocx, pyqt_app)
        if not kiwoom_helper_thread.connect_kiwoom(timeout_ms=15000):
            logger.critical("❌ Kiwoom API 연결 실패 (백그라운드 트레이딩 스레드)")
            send_telegram_message("❌ Kiwoom API 연결 실패. 자동 매매 중단됨.")
            pythoncom.CoUninitialize()
            return False, None, None, None, None

        account_number = get_env("ACCOUNT_NUMBERS", "").split(',')[0].strip()
        account_password = get_env("ACCOUNT_PASSWORD", "").strip()

        kiwoom_tr_request_thread = KiwoomTrRequest(kiwoom_helper_thread, pyqt_app, account_password)
        monitor_positions_thread = MonitorPositions(kiwoom_helper_thread, kiwoom_tr_request_thread, None, account_number)
        trade_manager_thread = TradeManager(kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, account_number)
        monitor_positions_thread.set_trade_manager(trade_manager_thread)

        logger.info(f"✅ Kiwoom API 연결 완료 (백그라운드 트레이딩 스레드) - 계좌번호: {account_number}")

        global app_initialized
        app_initialized = True

        threading.Thread(target=pyqt_app.exec_, daemon=True).start()

        return True, kiwoom_helper_thread, kiwoom_tr_request_thread, monitor_positions_thread, trade_manager_thread

    except Exception as e:
        logger.critical(f"❌ Kiwoom API 초기화 중 예외 발생: {e}", exc_info=True)
        send_telegram_message(f"❌ 자동 매매 스레드 초기화 실패: {e}")
        return False, None, None, None, None

# --- 자동 매매 전략 백그라운드 루프 ---
def background_trading_loop():
    logger.info("🔍 백그라운드 트레이딩 스레드 시작 중...")

    success, kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager = initialize_kiwoom_api_in_background_thread()

    if not success:
        logger.critical("❌ 백그라운드 트레이딩 스레드 초기화 실패. 스레드를 종료합니다.")
        return

    while True:
        try:
            run_daily_trading_cycle(kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager)

            with shared_state_lock:
                shared_kiwoom_state["positions"] = monitor_positions.get_all_positions()
                shared_kiwoom_state["last_update_time"] = get_current_time_str()

            time_module.sleep(30)

        except Exception as e:
            logger.exception(f"🔥 백그라운드 트레이딩 루프 오류 발생: {e}")
            send_telegram_message(f"🔥 백그라운드 트레이딩 루프 오류 발생: {e}")
            time_module.sleep(60)

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
        return jsonify(shared_kiwoom_state)

# --- Flask 서버 실행 ---
if __name__ == '__main__':
    trading_thread = threading.Thread(target=background_trading_loop, daemon=True)
    trading_thread.start()

    logger.info("📡 Flask 서버 시작 준비 중...")
    app.run(host="0.0.0.0", port=int(API_SERVER_PORT), debug=True, use_reloader=False)
