# local_api_server.py

import os
import sys
import json
import time as time_module
import logging
from functools import wraps
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from datetime import datetime, time
import threading

# PyQt5 관련 임포트는 백그라운드 스레드 함수 내에서 수행 (CoInitialize 문제 방지)
# from PyQt5.QtWidgets import QApplication
# from PyQt5.QAxContainer import QAxWidget

# --- 모듈 경로 설정 ---
script_dir = os.path.dirname(os.path.abspath(__file__))
modules_path = os.path.join(script_dir, 'modules')
if modules_path not in sys.path:
    sys.path.insert(0, modules_path)

# --- 모듈 임포트 ---
# Kiwoom 관련 모듈은 initialize_kiwoom_api_in_background_thread() 내에서 임포트
# from modules.Kiwoom.kiwoom_query_helper import KiwoomQueryHelper
# from modules.Kiwoom.kiwoom_tr_request import KiwoomTrRequest
# from modules.Kiwoom.monitor_positions import MonitorPositions
# from modules.Kiwoom.trade_manager import TradeManager

from modules.strategies.main_strategy_loop import run_daily_trading_cycle, set_strategy_flag, set_real_condition_info, strategy_flags
from modules.common.config import get_env, API_SERVER_PORT, API_KEY
from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
from modules.trade_logger import TradeLogger # TradeLogger 임포트

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 환경 변수 로드 ---
load_dotenv()

app = Flask(__name__)

# 전역 상태 변수
app_initialized = False
shared_kiwoom_state = {
    "account_number": "N/A",
    "balance": 0,
    "positions": {},
    "last_kiwoom_update": "N/A",
    "kiwoom_connected": False,
    "condition_check_enabled": False,
    "buy_strategy_enabled": False,
    "exit_strategy_enabled": False,
    "real_condition_name": None
}
shared_state_lock = threading.Lock() # 공유 상태 접근을 위한 락

# --- API Key 인증 데코레이터 ---
def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.headers.get('X-API-Key') and request.headers.get('X-API-Key') == API_KEY:
            return f(*args, **kwargs)
        else:
            logger.warning(f"❌ API 키 인증 실패: {request.remote_addr}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return decorated_function

# --- Kiwoom API 초기화 및 백그라운드 루프 ---
def initialize_kiwoom_api_in_background_thread():
    """
    별도의 스레드에서 Kiwoom API를 초기화합니다.
    PyQt QApplication은 스레드마다 하나씩 있어야 하므로, 이 함수 내에서 생성합니다.
    """
    import pythoncom
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QAxContainer import QAxWidget
    from modules.Kiwoom.kiwoom_query_helper import KiwoomQueryHelper
    from modules.Kiwoom.kiwoom_tr_request import KiwoomTrRequest
    from modules.Kiwoom.monitor_positions import MonitorPositions
    from modules.Kiwoom.trade_manager import TradeManager
    from modules.common.config import ACCOUNT_NUMBERS, ACCOUNT_PASSWORD

    # COM 객체 초기화 (필수)
    pythoncom.CoInitialize()

    # QApplication 인스턴스 생성
    pyqt_app = QApplication([])
    kiwoom_ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
    kiwoom_helper = KiwoomQueryHelper(kiwoom_ocx, pyqt_app)

    # Kiwoom API 연결 시도
    if not kiwoom_helper.connect_kiwoom(timeout_ms=10000):
        logger.critical("❌ 키움 API 연결 실패. 서버를 시작할 수 없습니다.")
        send_telegram_message("🚨 자동매매 서버 시작 실패: Kiwoom API 연결 불가.")
        # QApplication 종료 (필요 시)
        pyqt_app.quit()
        return None, None, None, None, None

    # 계좌 정보 가져오기
    account_number = ACCOUNT_NUMBERS.split(',')[0].strip() # 첫 번째 계좌 사용

    # 모듈 인스턴스 생성
    kiwoom_tr_request = KiwoomTrRequest(kiwoom_helper, pyqt_app, ACCOUNT_PASSWORD)
    monitor_positions = MonitorPositions(kiwoom_helper, kiwoom_tr_request, None, account_number)
    trade_manager = TradeManager(kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number)
    monitor_positions.set_trade_manager(trade_manager) # 순환 참조 해결

    # KiwoomQueryHelper에 TradeManager 인스턴스 전달 (실시간 데이터 처리에서 필요할 수 있음)
    # kiwoom_helper.set_trade_manager(trade_manager) # 필요 시 추가

    # 초기 계좌 정보 및 포지션 업데이트
    initial_account_info = kiwoom_tr_request.request_account_info(account_number)
    initial_balance = initial_account_info.get("예수금", 0)
    initial_positions = monitor_positions.get_all_positions()

    with shared_state_lock:
        shared_kiwoom_state["account_number"] = account_number
        shared_kiwoom_state["balance"] = initial_balance
        shared_kiwoom_state["positions"] = initial_positions
        shared_kiwoom_state["last_kiwoom_update"] = get_current_time_str()
        shared_kiwoom_state["kiwoom_connected"] = kiwoom_helper.connected
        # 초기 전략 상태 설정 (config에서 가져오거나 기본값)
        shared_kiwoom_state["condition_check_enabled"] = False
        shared_kiwoom_state["buy_strategy_enabled"] = False
        shared_kiwoom_state["exit_strategy_enabled"] = False

        # main_strategy_loop의 전역 플래그 초기화
        set_strategy_flag("condition_check_enabled", False)
        set_strategy_flag("buy_strategy_enabled", False)
        set_strategy_flag("exit_strategy_enabled", False)

    global app_initialized
    app_initialized = True
    logger.info("✅ Kiwoom API 및 트레이딩 모듈 초기화 완료.")
    send_telegram_message("✅ 자동매매 서버 시작 및 Kiwoom API 연결 완료.")

    return pyqt_app, kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager

def trading_main_loop(pyqt_app, kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager):
    """
    백그라운드에서 트레이딩 로직을 주기적으로 실행하는 메인 루프.
    """
    logger.info("🚀 트레이딩 루프 시작.")
    condition_checked_today = False # 하루에 한 번만 조건 검색 실행을 위한 플래그

    while True:
        try:
            now = datetime.now()
            now_time = now.time()

            # 장 시작 전 초기화 (매일 08:50분 기준)
            if now_time >= time(8, 50) and now_time < time(9, 0) and not condition_checked_today:
                logger.info("⏰ 장 시작 전 초기화 및 조건 검색 준비.")
                kiwoom_helper.is_condition_checked = False # 다음 장 시작을 위해 플래그 초기화
                condition_checked_today = True # 당일 초기화 완료 표시
                send_telegram_message("✅ 장 시작 전 초기화 완료. 조건 검색 준비.")

            # 장 중 (09:00 ~ 15:20)
            if time(9, 0) <= now_time < time(15, 20):
                # run_daily_trading_cycle 함수는 이제 내부적으로 strategy_flags를 확인
                run_daily_trading_cycle(kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager)

                # 공유 상태 업데이트
                with shared_state_lock:
                    account_info = kiwoom_tr_request.request_account_info(shared_kiwoom_state["account_number"])
                    shared_kiwoom_state["balance"] = account_info.get("예수금", 0)
                    shared_kiwoom_state["positions"] = monitor_positions.get_all_positions()
                    shared_kiwoom_state["last_kiwoom_update"] = get_current_time_str()
                    shared_kiwoom_state["kiwoom_connected"] = kiwoom_helper.connected
                    # 전략 활성화 상태도 공유 상태에 반영
                    shared_kiwoom_state["condition_check_enabled"] = strategy_flags["condition_check_enabled"]
                    shared_kiwoom_state["buy_strategy_enabled"] = strategy_flags["buy_strategy_enabled"]
                    shared_kiwoom_state["exit_strategy_enabled"] = strategy_flags["exit_strategy_enabled"]
                    shared_kiwoom_state["real_condition_name"] = strategy_flags["real_condition_name"]

            # 장 마감 정리 단계 (15:20 ~ 15:30)
            elif now_time >= time(15, 20) and now_time < time(15, 30):
                logger.info("⏰ 장 마감 정리 단계 실행")
                # 모든 실시간 데이터 등록 해제
                kiwoom_helper.SetRealRemove("ALL", "ALL")
                logger.info("✅ 장 마감. 모든 실시간 데이터 등록 해제.")
                condition_checked_today = False # 다음 날을 위해 플래그 초기화

            # 장 외 시간 (15:30 이후 ~ 다음 날 08:50 이전)
            else:
                logger.info("⏸️ 장 시간 외 대기 중...")
                # 장 외 시간에는 Kiwoom API 연결 상태만 주기적으로 확인
                with shared_state_lock:
                    shared_kiwoom_state["kiwoom_connected"] = kiwoom_helper.connected
                    shared_kiwoom_state["last_kiwoom_update"] = get_current_time_str()
                    # 장 외 시간에는 전략 비활성화
                    shared_kiwoom_state["condition_check_enabled"] = False
                    shared_kiwoom_state["buy_strategy_enabled"] = False
                    shared_kiwoom_state["exit_strategy_enabled"] = False
                    set_strategy_flag("condition_check_enabled", False)
                    set_strategy_flag("buy_strategy_enabled", False)
                    set_strategy_flag("exit_strategy_enabled", False)


            time_module.sleep(30) # 30초 대기

        except Exception as e:
            logger.exception(f"🔥 백그라운드 트레이딩 루프 오류: {e}")
            send_telegram_message(f"🔥 백그라운드 트레이딩 루프 오류: {e}")
            time_module.sleep(60) # 오류 발생 시 1분 대기 후 재시도

# --- Flask API 엔드포인트 ---
@app.route('/')
def home():
    return "Local API Server is running!"

@app.route('/status')
@api_key_required
def status():
    """서버 및 Kiwoom API의 현재 상태를 반환합니다."""
    if not app_initialized:
        return jsonify({"status": "error", "message": "백그라운드 트레이딩 시스템이 아직 초기화되지 않았습니다."}), 503

    with shared_state_lock:
        return jsonify({
            "status": "ok",
            "server_time": get_current_time_str(),
            "account_number": shared_kiwoom_state["account_number"],
            "balance": shared_kiwoom_state["balance"],
            "positions": shared_kiwoom_state["positions"],
            "last_kiwoom_update": shared_kiwoom_state["last_kiwoom_update"],
            "kiwoom_connected": shared_kiwoom_state["kiwoom_connected"],
            "condition_check_enabled": shared_kiwoom_state["condition_check_enabled"],
            "buy_strategy_enabled": shared_kiwoom_state["buy_strategy_enabled"],
            "exit_strategy_enabled": shared_kiwoom_state["exit_strategy_enabled"],
            "real_condition_name": shared_kiwoom_state["real_condition_name"]
        })

@app.route('/toggle_strategy', methods=['POST'])
@api_key_required
def toggle_strategy():
    """
    특정 전략의 활성화/비활성화 상태를 변경합니다.
    """
    data = request.get_json()
    strategy_name = data.get('strategy_name')
    enabled = data.get('enabled')

    if strategy_name not in ["condition_check_enabled", "buy_strategy_enabled", "exit_strategy_enabled"]:
        return jsonify({"status": "error", "message": "유효하지 않은 전략 이름입니다."}), 400

    if not isinstance(enabled, bool):
        return jsonify({"status": "error", "message": "enabled 값은 boolean이어야 합니다."}), 400

    with shared_state_lock:
        set_strategy_flag(strategy_name, enabled)
        shared_kiwoom_state[strategy_name] = enabled # 공유 상태에도 반영

    return jsonify({"status": "success", "message": f"전략 '{strategy_name}'이(가) {'활성화' if enabled else '비활성화'}되었습니다."})


@app.route('/set_real_condition', methods=['POST'])
@api_key_required
def set_real_condition():
    """
    실시간 조건 검색식을 등록하거나 해제합니다.
    """
    data = request.get_json()
    condition_name = data.get('condition_name')
    search_type = data.get('search_type') # "0": 등록, "1": 해제

    if not condition_name or search_type not in ["0", "1"]:
        return jsonify({"status": "error", "message": "조건식 이름 또는 검색 타입이 유효하지 않습니다."}), 400

    # KiwoomHelper 인스턴스에 접근
    # 이 부분은 백그라운드 스레드에서 KiwoomHelper 인스턴스를 가져와야 합니다.
    # 현재 구조에서는 전역 변수로 직접 접근하기 어렵습니다.
    # 해결책: initialize_kiwoom_api_in_background_thread가 반환하는 kiwoom_helper를 전역으로 저장하거나,
    # Flask 요청 처리 시점에 스레드 로컬 스토리지를 통해 접근하도록 해야 합니다.
    # 여기서는 간단히 전역으로 선언된 kiwoom_helper_instance를 사용한다고 가정합니다.
    # 실제 구현 시에는 스레드 간 안전한 참조 전달 메커니즘이 필요합니다.
    global kiwoom_helper_instance # 아래 main 블록에서 할당될 전역 변수

    if not kiwoom_helper_instance:
        return jsonify({"status": "error", "message": "Kiwoom API가 초기화되지 않았습니다."}), 503

    # 조건식 인덱스 조회
    condition_list = kiwoom_helper_instance.get_condition_list()
    condition_index = condition_list.get(condition_name)

    if condition_index is None:
        return jsonify({"status": "error", "message": f"조건식 '{condition_name}'을(를) 찾을 수 없습니다."}), 404

    screen_no = kiwoom_helper_instance.generate_condition_screen_no()
    success = kiwoom_helper_instance.SendCondition(screen_no, condition_name, condition_index, int(search_type))

    if success:
        with shared_state_lock:
            if search_type == "0": # 등록
                set_real_condition_info(condition_name, condition_index)
                shared_kiwoom_state["real_condition_name"] = condition_name
            else: # 해제
                set_real_condition_info(None, None)
                shared_kiwoom_state["real_condition_name"] = None
        return jsonify({"status": "success", "message": f"조건식 '{condition_name}' {'등록' if search_type == '0' else '해제'} 요청 성공."})
    else:
        return jsonify({"status": "error", "message": f"조건식 '{condition_name}' {'등록' if search_type == '0' else '해제'} 요청 실패."}), 500

@app.route('/trade_history')
@api_key_required
def trade_history():
    """
    거래 내역을 반환합니다.
    """
    trade_logger = TradeLogger() # TradeLogger 인스턴스 생성
    log_data = trade_logger.get_trade_log()
    return jsonify({"status": "success", "trade_history": log_data})


# --- 메인 실행 블록 ---
if __name__ == '__main__':
    # Kiwoom API 초기화 및 트레이딩 루프를 위한 스레드 시작
    # QApplication은 메인 스레드에서 실행되어야 하므로, Flask는 별도의 스레드에서 실행되거나
    # QApplication을 백그라운드 스레드에서 실행하고 Flask는 메인 스레드에서 실행해야 합니다.
    # 여기서는 QApplication을 백그라운드 스레드에서 실행하는 방식을 따릅니다.

    pyqt_app_instance = None
    kiwoom_helper_instance = None
    kiwoom_tr_request_instance = None
    monitor_positions_instance = None
    trade_manager_instance = None

    def init_and_run_kiwoom():
        global pyqt_app_instance, kiwoom_helper_instance, kiwoom_tr_request_instance, monitor_positions_instance, trade_manager_instance
        pyqt_app_instance, kiwoom_helper_instance, kiwoom_tr_request_instance, monitor_positions_instance, trade_manager_instance = \
            initialize_kiwoom_api_in_background_thread()

        if pyqt_app_instance and kiwoom_helper_instance:
            # Kiwoom API 초기화가 성공하면 트레이딩 루프 시작
            trading_thread = threading.Thread(target=trading_main_loop,
                                              args=(pyqt_app_instance, kiwoom_helper_instance,
                                                    kiwoom_tr_request_instance, monitor_positions_instance,
                                                    trade_manager_instance),
                                              daemon=True)
            trading_thread.start()
            logger.info("🚀 트레이딩 루프 스레드 시작 완료")

            # PyQt 이벤트 루프 시작 (이것이 블로킹 호출이므로 마지막에 실행)
            # QApplication.exec_()는 GUI 스레드를 블로킹하므로,
            # Flask 서버는 별도의 스레드에서 실행되어야 합니다.
            pyqt_app_instance.exec_()
        else:
            logger.critical("❌ Kiwoom API 초기화 실패로 PyQt 앱 시작 불가.")
            sys.exit(1)


    # Kiwoom 초기화 및 트레이딩 루프를 위한 별도 스레드 시작
    kiwowoom_init_thread = threading.Thread(target=init_and_run_kiwoom, daemon=True)
    kiwowoom_init_thread.start()

    # Flask 서버가 시작될 때까지 Kiwoom 초기화를 기다립니다.
    init_timeout = 120 # 2분 타임아웃
    start_time = time_module.time()
    while not app_initialized and (time_module.time() - start_time) < init_timeout:
        time_module.sleep(1)

    if not app_initialized:
        logger.critical("❌ Kiwoom API 초기화 타임아웃. Flask 서버를 시작할 수 없습니다.")
        sys.exit(1)

    # Flask 서버 시작
    logger.info(f"🌐 Flask API 서버 시작 (포트: {API_SERVER_PORT})...")
    app.run(host='0.0.0.0', port=API_SERVER_PORT, debug=False, use_reloader=False)

