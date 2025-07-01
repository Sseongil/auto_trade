# local_api_server.py

import os
import sys
import json
import time as time_module
import logging
from flask import Flask, request, jsonify, render_template # render_template 임포트 추가
from dotenv import load_dotenv
from datetime import datetime, time
import threading

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
from modules.strategies.main_strategy_loop import run_condition_check_step, run_buy_strategy_step, run_exit_strategy_step
from modules.common.config import get_env, API_SERVER_PORT
from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
from modules.trade_logger import TradeLogger # TradeLogger 임포트

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 환경 변수 로드 ---
load_dotenv()

app = Flask(__name__)

# --- 전역 상태 변수 ---
# app_initialized를 threading.Event로 변경하여 스레드 동기화 강화
app_initialized = threading.Event()
shared_kiwoom_state = {
    "account_number": "N/A",
    "balance": 0,
    "positions": {},
    "last_kiwoom_update": "N/A",
    "kiwoom_connected": False,
    "condition_check_enabled": True, # 조건 검색 활성화 여부
    "buy_strategy_enabled": True,    # 매수 전략 활성화 여부
    "exit_strategy_enabled": True,   # 익절/손절 전략 활성화 여부
    "kiwoom_helper": None,           # KiwoomQueryHelper 인스턴스 저장
    "kiwoom_tr_request": None,       # KiwoomTrRequest 인스턴스 저장
    "monitor_positions": None,       # MonitorPositions 인스턴스 저장
    "trade_manager": None,           # TradeManager 인스턴스 저장
    "trade_logger": TradeLogger()    # TradeLogger 인스턴스
}
shared_state_lock = threading.Lock() # 공유 상태 접근을 위한 락

# --- API 키 인증 데코레이터 ---
def api_key_required(f):
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != get_env('API_KEY'):
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__ # Flask 데코레이터 문제 해결
    return decorated_function

# --- 키움 API 초기화 (백그라운드 스레드에서 실행) ---
def initialize_kiwoom_api_in_background_thread(pyqt_app):
    import pythoncom
    pythoncom.CoInitialize() # COM 객체 초기화 (각 스레드마다 호출 필요)

    # QApplication은 메인 스레드에서만 생성되어야 하지만,
    # 백그라운드 스레드에서 QAxWidget을 사용하기 위해 필요합니다.
    # 이 경우, PyQt 이벤트 루프가 백그라운드 스레드에서 독립적으로 실행됩니다.
    kiwoom_ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
    kiwoom_helper = KiwoomQueryHelper(kiwoom_ocx, pyqt_app)

    if not kiwoom_helper.connect_kiwoom(timeout_ms=10000):
        logger.critical("❌ 키움 API 연결 실패. 애플리케이션을 종료합니다.")
        send_telegram_message("� 키움 API 연결 실패. 서버 종료.")
        return None, None, None, None

    account_number = os.getenv("ACCOUNT_NUMBERS", "").split(',')[0].strip()
    account_password = os.getenv("ACCOUNT_PASSWORD", "").strip()

    kiwoom_tr_request = KiwoomTrRequest(kiwoom_helper, pyqt_app, account_password)
    monitor_positions = MonitorPositions(kiwoom_helper, kiwoom_tr_request, None, account_number)
    trade_manager = TradeManager(kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number)
    monitor_positions.set_trade_manager(trade_manager) # 순환 참조 해결

    with shared_state_lock:
        shared_kiwoom_state["account_number"] = account_number
        shared_kiwoom_state["kiwoom_connected"] = True
        shared_kiwoom_state["kiwoom_helper"] = kiwoom_helper
        shared_kiwoom_state["kiwoom_tr_request"] = kiwoom_tr_request
        shared_kiwoom_state["monitor_positions"] = monitor_positions
        shared_kiwoom_state["trade_manager"] = trade_manager

    app_initialized.set() # 초기화 완료 이벤트 설정
    logger.info("✅ 키움 API 및 트레이딩 시스템 초기화 완료.")
    send_telegram_message("✅ 트레이딩 시스템 시작됨")

    return kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager

# --- 백그라운드 트레이딩 루프 ---
def background_trading_loop(pyqt_app):
    kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager = \
        initialize_kiwoom_api_in_background_thread(pyqt_app)

    if not kiwoom_helper:
        return # 초기화 실패 시 스레드 종료

    # 초기화 완료 대기
    app_initialized.wait()

    # 장 시작 시간 및 종료 시간 설정
    MARKET_OPEN_TIME = time(9, 0)
    MARKET_CLOSE_TIME = time(15, 30) # 15시 30분까지 매매 가능

    condition_checked_today = False # 당일 조건 검색 실행 여부 플래그

    while True:
        try:
            now = datetime.now()
            now_time = now.time()

            # 장 중 시간 (09:00 ~ 15:30)
            if MARKET_OPEN_TIME <= now_time < MARKET_CLOSE_TIME:
                with shared_state_lock:
                    # 잔고 및 포지션 업데이트
                    account_info = kiwoom_tr_request.request_account_info(shared_kiwoom_state["account_number"])
                    shared_kiwoom_state["balance"] = account_info.get("예수금", 0)
                    shared_kiwoom_state["positions"] = monitor_positions.get_all_positions()
                    shared_kiwoom_state["last_kiwoom_update"] = get_current_time_str()

                logger.info(f"[{get_current_time_str()}] 🔄 트레이딩 루프 실행 중...")
                logger.info(f"현재 예수금: {shared_kiwoom_state['balance']:,}원, 보유 종목: {len(shared_kiwoom_state['positions'])}개")

                # 조건 검색 (장 시작 후 한 번만 실행 또는 주기적으로 실행)
                if not condition_checked_today and now_time < time(9, 30): # 예: 장 시작 후 30분 이내 한번만
                    if shared_kiwoom_state["condition_check_enabled"]:
                        run_condition_check_step(kiwoom_helper)
                        condition_checked_today = True # 당일 조건 검색 실행 완료 표시
                    else:
                        logger.info("조건 검색 기능 비활성화됨.")

                # 매수 전략 실행 (조건 검색 결과가 있을 경우)
                if shared_kiwoom_state["buy_strategy_enabled"]:
                    run_buy_strategy_step(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)
                else:
                    logger.info("매수 전략 기능 비활성화됨.")

                # 익절/손절 전략 실행 (항상 실행)
                if shared_kiwoom_state["exit_strategy_enabled"]:
                    run_exit_strategy_step(kiwoom_helper, trade_manager, monitor_positions)
                else:
                    logger.info("익절/손절 전략 기능 비활성화됨.")

                time_module.sleep(30) # 30초마다 루프 실행
            elif now_time >= time(15, 0) and now_time < time(15, 30): # 장 마감 임박 정리 시간
                logger.info("⏰ 장 마감 정리 단계 실행: 실시간 데이터 해제 및 플래그 초기화")
                kiwoom_helper.SetRealRemove("ALL", "ALL") # 모든 실시간 데이터 해제
                condition_checked_today = False # 다음 장을 위해 플래그 초기화
                time_module.sleep(30)
            else:
                logger.info("⏸️ 장 시간 외 대기 중...")
                condition_checked_today = False # 장 시간 외에는 플래그 초기화
                time_module.sleep(60) # 장 시간 외에는 더 긴 간격으로 대기

        except Exception as e:
            logger.exception(f"🔥 백그라운드 트레이딩 루프 오류: {e}")
            send_telegram_message(f"🔥 백그라운드 트레이딩 루프 오류: {e}")
            time_module.sleep(60) # 오류 발생 시 1분 대기 후 재시도

# --- Flask API 엔드포인트 ---

@app.route('/')
def home():
    """서버 상태 확인을 위한 기본 페이지."""
    return render_template('index.html') # templates 폴더의 index.html을 반환

@app.route('/status')
@api_key_required
def status():
    """현재 트레이딩 시스템의 상태를 반환합니다."""
    if not app_initialized.is_set():
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
            "exit_strategy_enabled": shared_kiwoom_state["exit_strategy_enabled"]
        })

@app.route('/trade_history', methods=['GET'])
@api_key_required
def get_trade_history():
    """거래 로그 기록을 반환합니다."""
    if not app_initialized.is_set():
        return jsonify({"status": "error", "message": "시스템이 초기화되지 않았습니다."}), 503
    
    with shared_state_lock:
        try:
            logs = shared_kiwoom_state["trade_logger"].get_trade_log()
            return jsonify({"status": "success", "trade_history": logs})
        except Exception as e:
            logger.error(f"거래 내역 조회 중 오류 발생: {e}", exc_info=True)
            return jsonify({"status": "error", "message": f"거래 내역 조회 실패: {e}"}), 500

@app.route('/set_real_condition', methods=['POST'])
@api_key_required
def set_real_condition():
    """
    실시간 조건 검색식을 수동으로 변경하거나 등록합니다.
    요청 바디: {"condition_name": "나의강력조건식", "search_type": "0"}
    search_type: "0" (실시간 등록), "1" (실시간 해제)
    """
    if not app_initialized.is_set():
        return jsonify({"status": "error", "message": "시스템이 초기화되지 않았습니다."}), 503

    data = request.get_json()
    condition_name = data.get('condition_name')
    search_type = data.get('search_type', '0') # 기본값: 실시간 등록

    if not condition_name:
        return jsonify({"status": "error", "message": "condition_name이 필요합니다."}), 400

    with shared_state_lock:
        kiwoom_helper = shared_kiwoom_state.get("kiwoom_helper")
        if not kiwoom_helper or not kiwoom_helper.connected:
            return jsonify({"status": "error", "message": "키움 API가 연결되지 않았습니다."}), 500

        try:
            # 조건식 목록 갱신
            condition_list = kiwoom_helper.get_condition_list()
            condition_index = condition_list.get(condition_name)

            if condition_index is None:
                return jsonify({"status": "error", "message": f"조건식 '{condition_name}'을(를) 찾을 수 없습니다."}), 404

            # 기존 실시간 조건 해제 (필요하다면)
            # kiwoom_helper.SetRealRemove("0001", "ALL") # 조건검색용 화면번호 (임시)

            # 새로운 조건식 등록/해제
            screen_no = "0001" # 조건 검색용 고정 화면번호
            kiwoom_helper.SendCondition(screen_no, condition_name, condition_index, int(search_type))

            if search_type == '0':
                message = f"조건식 '{condition_name}'이(가) 실시간 검색으로 등록되었습니다."
            else:
                message = f"조건식 '{condition_name}'이(가) 실시간 검색에서 해제되었습니다."
            
            logger.info(message)
            send_telegram_message(message)
            return jsonify({"status": "success", "message": message})

        except Exception as e:
            logger.error(f"실시간 조건식 설정 중 오류 발생: {e}", exc_info=True)
            return jsonify({"status": "error", "message": f"실시간 조건식 설정 실패: {e}"}), 500

@app.route('/toggle_strategy', methods=['POST'])
@api_key_required
def toggle_strategy():
    """
    특정 전략의 활성화/비활성화를 토글합니다.
    요청 바디: {"strategy_name": "buy_strategy_enabled", "enabled": true/false}
    strategy_name: "condition_check_enabled", "buy_strategy_enabled", "exit_strategy_enabled"
    """
    if not app_initialized.is_set():
        return jsonify({"status": "error", "message": "시스템이 초기화되지 않았습니다."}), 503

    data = request.get_json()
    strategy_name = data.get('strategy_name')
    enabled = data.get('enabled')

    if strategy_name not in ["condition_check_enabled", "buy_strategy_enabled", "exit_strategy_enabled"] or enabled is None:
        return jsonify({"status": "error", "message": "유효하지 않은 전략 이름 또는 enabled 값입니다."}), 400

    with shared_state_lock:
        shared_kiwoom_state[strategy_name] = bool(enabled)
        message = f"전략 '{strategy_name}'이(가) {'활성화' if enabled else '비활성화'}되었습니다."
        logger.info(message)
        send_telegram_message(message)
        return jsonify({"status": "success", "message": message})


# --- 메인 실행 블록 ---
if __name__ == '__main__':
    # PyQt 애플리케이션은 메인 스레드에서 한 번만 생성되어야 합니다.
    # QAxWidget은 QApplication 인스턴스가 필요합니다.
    pyqt_app = QApplication(sys.argv)

    # 백그라운드 스레드에서 키움 API 초기화 및 트레이딩 루프 실행
    trading_thread = threading.Thread(target=background_trading_loop, args=(pyqt_app,), daemon=True)
    trading_thread.start()
    logger.info("🚀 트레이딩 루프 스레드 시작 완료")

    # Flask 서버 실행
    # Flask는 기본적으로 단일 스레드이므로, 백그라운드 트레이딩 로직은 별도 스레드에서 처리
    try:
        app.run(host='0.0.0.0', port=API_SERVER_PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.critical(f"❌ Flask 서버 시작 실패: {e}")
        sys.exit(1)

    # PyQt 이벤트 루프 시작 (QAxWidget이 이벤트를 처리하도록)
    # Flask 서버가 종료되면 이 부분이 실행될 수 있도록 설계
    # 하지만 실제로는 Flask 서버가 계속 실행되므로 이 부분은 도달하지 않을 수 있습니다.
    # pyqt_app.exec_() # 이 줄은 Flask 서버와 함께 실행될 때 주의 필요
�