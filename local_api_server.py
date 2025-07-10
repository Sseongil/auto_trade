# local_api_server.py

import os
import sys
import json
import time as time_module
import logging
import threading
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime, time

# --- 초기 설정 ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- 경로 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "modules"))

# --- Flask 앱 초기화 ---
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"), static_folder=os.path.join(BASE_DIR, "static"))

# --- 공통 모듈 임포트 ---
from common.config import API_KEY, API_SERVER_PORT, ACCOUNT_NUMBERS, ACCOUNT_PASSWORD, RENDER_API_KEY, RENDER_SERVICE_ID, RENDER_DEPLOY_HOOK_URL
from common.utils import get_current_time_str
from trade_logger import TradeLogger
from notify import send_telegram_message
from strategies.main_strategy_loop import (
    run_daily_trading_cycle,
    set_strategy_flag,
    strategy_flags,
    set_real_condition_info,
    initialize_real_time_condition_manager
)

# --- 전역 상태 변수 ---
shared_kiwoom_state = {
    "account_number": "N/A",
    "balance": 0,
    "positions": {},
    "last_kiwoom_update": "N/A",
    "kiwoom_connected": False,
    "condition_check_enabled": False,
    "buy_strategy_enabled": False,
    "exit_strategy_enabled": False,
    "real_condition_name": None,
    "ngrok_url": "N/A"
}

shared_state_lock = threading.Lock()
app_initialized = threading.Event() # Kiwoom 초기화 완료를 알리는 이벤트

# --- 전역 객체 (메인 스레드에서 접근 가능하도록) ---
trade_logger_instance = TradeLogger() # TradeLogger 인스턴스 이름 변경
kiwoom_helper_instance = None
kiwoom_tr_request_instance = None
monitor_positions_instance = None
trade_manager_instance = None

# --- API 인증 데코레이터 ---
def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.headers.get("X-API-Key") == API_KEY:
            return f(*args, **kwargs)
        logger.warning(f"❌ API 키 인증 실패: {request.remote_addr}")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return decorated

# --- Flask API 라우팅 ---
@app.route("/")
def index():
    return render_template("index.html", api_key=API_KEY)

@app.route("/status")
@api_key_required
def status():
    with shared_state_lock:
        return jsonify({
            **shared_kiwoom_state,
            "status": "ok" if app_initialized.is_set() else "initializing",
            "server_time": get_current_time_str(),
        })

@app.route("/toggle_strategy", methods=["POST"])
@api_key_required
def toggle_strategy():
    data = request.get_json()
    name, enabled = data.get("strategy_name"), data.get("enabled")
    if name not in strategy_flags or not isinstance(enabled, bool):
        return jsonify({"status": "error", "message": "전략 이름 또는 형식 오류"}), 400
    
    with shared_state_lock:
        set_strategy_flag(name, enabled)
        shared_kiwoom_state[name] = enabled
    
    message = f"전략 '{name}'이(가) {'활성화' if enabled else '비활성화'}되었습니다."
    send_telegram_message(message) # 텔레그램 알림 추가
    logger.info(message)
    return jsonify({"status": "success", "message": message})

@app.route("/set_real_condition", methods=["POST"])
@api_key_required
def set_real_condition():
    global kiwoom_helper_instance # 전역 인스턴스 사용
    data = request.get_json()
    name, mode = data.get("condition_name"), data.get("search_type")
    
    if not name or mode not in ["0", "1"]:
        return jsonify({"status": "error", "message": "파라미터 오류"}), 400
    
    # Kiwoom API가 초기화되었는지 확인
    if not app_initialized.is_set() or not kiwoom_helper_instance or not kiwoom_helper_instance.connected:
        return jsonify({"status": "error", "message": "Kiwoom API가 초기화되지 않았거나 연결되지 않았습니다."}), 503

    try:
        conds = kiwoom_helper_instance.get_condition_list()
        index = conds.get(name)
        if index is None:
            return jsonify({"status": "error", "message": f"조건식 '{name}'을(를) 찾을 수 없습니다."}), 404
        
        screen_no = kiwoom_helper_instance.generate_condition_screen_no()
        success = kiwoom_helper_instance.SendCondition(screen_no, name, index, int(mode))
        
        if success:
            with shared_state_lock:
                if mode == "0":
                    set_real_condition_info(name, index)
                    shared_kiwoom_state["real_condition_name"] = name
                else:
                    set_real_condition_info(None, None)
                    shared_kiwoom_state["real_condition_name"] = None
            message = f"조건식 '{name}' {'등록' if mode == '0' else '해제'} 요청 성공."
            send_telegram_message(message) # 텔레그램 알림 추가
            logger.info(message)
            return jsonify({"status": "success", "message": message})
        else:
            message = f"조건식 '{name}' {'등록' if mode == '0' else '해제'} 요청 실패."
            send_telegram_message(message) # 텔레그램 알림 추가
            logger.error(message)
            return jsonify({"status": "error", "message": message}), 500
    except Exception as e:
        logger.exception(f"❌ 조건식 설정 중 오류 발생: {e}")
        return jsonify({"status": "error", "message": f"조건식 설정 중 오류 발생: {e}"}), 500


@app.route("/trade_history")
@api_key_required
def trade_history():
    logs = trade_logger_instance.get_trade_log() # trade_logger_instance 사용
    return jsonify({"status": "success", "trade_history": logs})

@app.route("/trade_history/clear", methods=["POST"])
@api_key_required
def clear_history():
    ok = trade_logger_instance.clear_trade_log() # trade_logger_instance 사용
    message = "거래 로그 초기화 완료." if ok else "거래 로그 초기화 실패."
    send_telegram_message(f"🗑️ {message}") # 텔레그램 알림 추가
    logger.info(message)
    return jsonify({"status": "success" if ok else "error", "message": message})


# --- ngrok 주소 감지 ---
def detect_ngrok_url():
    try:
        # ngrok API endpoint is usually at 4040
        res = requests.get("http://localhost:4040/api/tunnels", timeout=10) # 타임아웃 증가
        res.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        tunnels = res.json().get("tunnels", [])
        for t in tunnels:
            if t["proto"] == "https": # Prefer HTTPS tunnel
                return t["public_url"]
    except requests.exceptions.ConnectionError:
        logger.warning("⚠️ ngrok API에 연결할 수 없습니다. ngrok이 실행 중인지 확인하세요.")
    except requests.exceptions.Timeout:
        logger.warning("⚠️ ngrok API 연결 타임아웃.")
    except requests.exceptions.RequestException as e:
        logger.warning(f"⚠️ ngrok 주소 감지 실패: {e}")
    except json.JSONDecodeError:
        logger.warning("⚠️ ngrok API 응답 JSON 디코딩 실패.")
    return None

# --- Render 환경 변수 동기화 ---
def sync_ngrok_to_render(ngrok_url_to_sync):
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        logger.warning("⚠️ RENDER_API_KEY 또는 RENDER_SERVICE_ID 환경 변수가 설정되지 않았습니다. Render 환경 변수 동기화를 건너뜜.")
        return

    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    try:
        # Fetch current environment variables
        res = requests.get(f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars", headers=headers, timeout=30)
        res.raise_for_status()
        envs = res.json()

        updated = False
        new_envs_list = []
        found_existing = False
        
        for env_item in envs:
            # Render API 응답 구조에 따라 'envVar' 키를 통해 실제 환경 변수 데이터에 접근
            if isinstance(env_item, dict) and 'envVar' in env_item and isinstance(env_item['envVar'], dict):
                env = env_item['envVar']
                if 'key' in env and 'value' in env:
                    if env["key"] == "LOCAL_API_SERVER_URL":
                        found_existing = True
                        if env["value"] != ngrok_url_to_sync:
                            env["value"] = ngrok_url_to_sync
                            updated = True
                    new_envs_list.append(env_item) # 원본 env_item (envVar 래퍼 포함) 유지
                else:
                    logger.warning(f"⚠️ Render API 응답의 'envVar' 내부에 'key' 또는 'value'가 없습니다: {env_item}. 스킵합니다.")
            else:
                logger.warning(f"⚠️ Render API 응답에서 예상치 못한 환경 변수 형식 발견: {env_item}. 스킵합니다.")
        
        if not found_existing:
            # 새로 추가할 환경 변수는 Render API의 PUT 요청 형식에 맞게 'key', 'value'만 포함
            new_envs_list.append({"key": "LOCAL_API_SERVER_URL", "value": ngrok_url_to_sync})
            updated = True

        if updated:
            # PUT 요청 시에는 'envVar' 래퍼 없이 'key', 'value'만 있는 리스트를 기대
            final_envs_for_put = []
            for item in new_envs_list:
                if 'envVar' in item: # 기존 항목은 envVar 래퍼를 벗겨냄
                    final_envs_for_put.append(item['envVar'])
                else: # 새로 추가된 항목은 그대로 사용
                    final_envs_for_put.append(item)

            put_res = requests.put(
                f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars",
                headers=headers,
                json=final_envs_for_put,
                timeout=30 # 타임아웃 증가
            )
            put_res.raise_for_status()
            logger.info("✅ Render 환경변수 LOCAL_API_SERVER_URL 업데이트 완료.")
            send_telegram_message(f"✅ Render 서버의 LOCAL_API_SERVER_URL이 {ngrok_url_to_sync} (으)로 업데이트되었습니다.")
            
            # Trigger redeploy if successful
            if RENDER_DEPLOY_HOOK_URL:
                resp = requests.post(RENDER_DEPLOY_HOOK_URL, timeout=30) # 타임아웃 증가
                resp.raise_for_status()
                logger.info("✅ Render 재배포 요청 완료.")
                send_telegram_message("✅ Render 서버 재배포 요청 완료.")
            else:
                logger.warning("⚠️ RENDER_DEPLOY_HOOK_URL 환경 변수가 설정되지 않았습니다. 재배포를 건너뜜.")
        else:
            logger.info("ℹ️ LOCAL_API_SERVER_URL 변경 없음. Render 환경변수 업데이트 건너뜜.")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Render API 업데이트/조회 중 오류: {e}", exc_info=True)
        send_telegram_message(f"❌ Render API 동기화 중 오류: {e}")
    except json.JSONDecodeError:
        logger.error("❌ Render API 응답 JSON 디코딩 실패.", exc_info=True)
        send_telegram_message("❌ Render API 응답 JSON 디코딩 실패.")
    except Exception as e:
        logger.error(f"❌ Render API 동기화 중 알 수 없는 오류: {e}", exc_info=True)
        send_telegram_message(f"❌ Render API 동기화 중 알 수 없는 오류: {e}")


# --- PyQt5 + Kiwoom 실행 (메인 스레드) ---
def start_kiwoom():
    global kiwoom_helper_instance, kiwoom_tr_request_instance, monitor_positions_instance, trade_manager_instance
    
    import pythoncom
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QAxContainer import QAxWidget
    from PyQt5.QtCore import QTimer

    from Kiwoom.kiwoom_query_helper import KiwoomQueryHelper
    from Kiwoom.kiwoom_tr_request import KiwoomTrRequest
    from Kiwoom.monitor_positions import MonitorPositions
    from Kiwoom.trade_manager import TradeManager
    from Kiwoom.real_time_condition_manager import RealTimeConditionManager # 임포트 추가

    pythoncom.CoInitialize()
    pyqt_app = QApplication([]) # QApplication 인스턴스 이름 변경

    ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
    
    kiwoom_helper_instance = KiwoomQueryHelper(ocx, pyqt_app)
    
    # Kiwoom 연결 시도
    if not kiwoom_helper_instance.connect_kiwoom(timeout_ms=30000): # 타임아웃 증가
        logger.critical("❌ Kiwoom API 연결 실패. 자동매매 시스템을 시작할 수 없습니다.")
        send_telegram_message("🚨 자동매매 서버 시작 실패: Kiwoom API 연결 불가.")
        pyqt_app.quit() # 연결 실패 시 PyQt 앱 종료
        return # 스레드 종료

    account = ACCOUNT_NUMBERS.split(",")[0].strip()
    kiwoom_tr_request_instance = KiwoomTrRequest(kiwoom_helper_instance, pyqt_app, ACCOUNT_PASSWORD)
    monitor_positions_instance = MonitorPositions(kiwoom_helper_instance, kiwoom_tr_request_instance, None, account)
    trade_manager_instance = TradeManager(kiwoom_helper_instance, kiwoom_tr_request_instance, monitor_positions_instance, account)
    monitor_positions_instance.set_trade_manager(trade_manager_instance)
    
    # RealTimeConditionManager 초기화 및 main_strategy_loop에 전달
    initialize_real_time_condition_manager(kiwoom_helper_instance)

    # 초기 상태 업데이트
    balance = kiwoom_tr_request_instance.request_account_info(account).get("예수금", 0)
    with shared_state_lock:
        shared_kiwoom_state.update({
            "account_number": account,
            "balance": balance,
            "positions": monitor_positions_instance.get_all_positions(),
            "last_kiwoom_update": get_current_time_str(),
            "kiwoom_connected": kiwoom_helper_instance.connected # 실제 연결 상태 반영
        })
    app_initialized.set() # Kiwoom 초기화 완료 시그널
    send_telegram_message("✅ Kiwoom API 및 자동매매 서버 초기화 완료")
    logger.info("✅ Kiwoom API 및 자동매매 서버 초기화 완료.")

    # --- 트레이딩 루프 스케줄링 ---
    trading_timer = QTimer() # QTimer 인스턴스 이름 변경
    trading_timer.timeout.connect(lambda: run_trading_cycle_on_pyqt_thread())
    trading_timer.start(30000) # 30초마다 실행

    pyqt_app.exec_() # PyQt 이벤트 루프 시작 (블로킹)
    logger.info("PyQt application event loop finished.")


def run_trading_cycle_on_pyqt_thread(): # 함수 이름 변경
    """
    Wrapper function to run the daily trading cycle and update shared state.
    This function is called by QTimer on the PyQt thread.
    """
    global kiwoom_helper_instance, kiwoom_tr_request_instance, monitor_positions_instance, trade_manager_instance
    try:
        # Update strategy flags in main_strategy_loop module from shared_kiwoom_state
        with shared_state_lock:
            set_strategy_flag("condition_check_enabled", shared_kiwoom_state["condition_check_enabled"])
            set_strategy_flag("buy_strategy_enabled", shared_kiwoom_state["buy_strategy_enabled"])
            set_strategy_flag("exit_strategy_enabled", shared_kiwoom_state["exit_strategy_enabled"])
            set_real_condition_info(shared_kiwoom_state["real_condition_name"], strategy_flags.get("real_condition_index"))

        # Kiwoom 인스턴스들이 유효한지 다시 확인 (안전성 강화)
        if not (kiwoom_helper_instance and kiwoom_tr_request_instance and monitor_positions_instance and trade_manager_instance):
            logger.error("❌ 트레이딩 루프 실행 불가: Kiwoom 관련 인스턴스가 초기화되지 않았습니다.")
            send_telegram_message("❌ 트레이딩 루프 실행 불가: Kiwoom 인스턴스 미초기화.")
            return

        run_daily_trading_cycle(kiwoom_helper_instance, kiwoom_tr_request_instance, monitor_positions_instance, trade_manager_instance)

        # Update shared state after running the cycle
        with shared_state_lock:
            account_info = kiwoom_tr_request_instance.request_account_info(shared_kiwoom_state["account_number"])
            shared_kiwoom_state["balance"] = account_info.get("예수금", 0)
            shared_kiwoom_state["positions"] = monitor_positions_instance.get_all_positions()
            shared_kiwoom_state["last_kiwoom_update"] = get_current_time_str()
            shared_kiwoom_state["kiwoom_connected"] = kiwoom_helper_instance.connected # 실제 연결 상태 반영
            
    except Exception as e:
        logger.exception(f"🔥 PyQt 스레드 내 트레이딩 루프 오류: {e}")
        send_telegram_message(f"🔥 PyQt 스레드 내 트레이딩 루프 오류: {e}")


# --- Flask 서버 스레드 실행 ---
def start_flask_thread(): # 함수 이름 변경
    logger.info(f"🌐 Flask API 서버 시작 (포트 {API_SERVER_PORT})...")
    # Kiwoom 초기화가 완료될 때까지 대기
    init_timeout_sec = 120 # 2분 대기
    if not app_initialized.wait(timeout=init_timeout_sec):
        logger.critical("❌ Kiwoom API 초기화 타임아웃. Flask 서버를 시작할 수 없습니다.")
        send_telegram_message("🚨 Flask 서버 시작 실패: Kiwoom API 초기화 타임아웃.")
        # sys.exit(1) # 스레드에서 sys.exit 호출은 전체 앱을 종료시킬 수 있으므로 주의
        return # 스레드 종료

    try:
        app.run(host="0.0.0.0", port=int(API_SERVER_PORT), debug=False, use_reloader=False)
    except Exception as e:
        logger.critical(f"❌ Flask 서버 시작 실패: {e}")
        send_telegram_message(f"🚨 Flask 서버 시작 실패: {e}")

# --- Main ---
if __name__ == "__main__":
    # ngrok 주소 감지 및 Render 동기화 (메인 스레드에서 Flask 스레드 시작 전 실행)
    ngrok_url = detect_ngrok_url()
    if ngrok_url:
        logger.info(f"✅ 감지된 ngrok 주소: {ngrok_url}")
        os.environ["LOCAL_API_SERVER_URL"] = ngrok_url # 환경 변수 설정
        with shared_state_lock:
            shared_kiwoom_state["ngrok_url"] = ngrok_url # 공유 상태 업데이트
        sync_ngrok_to_render(ngrok_url) # Render 동기화 호출
    else:
        logger.warning("⚠️ ngrok 주소 탐지 실패. Render 동기화 건너뜜.")
        os.environ["LOCAL_API_SERVER_URL"] = "N/A"
        with shared_state_lock:
            shared_kiwoom_state["ngrok_url"] = "N/A"

    # Flask 서버를 별도의 스레드에서 시작
    flask_thread = threading.Thread(target=start_flask_thread, daemon=True) # 함수 이름 변경
    flask_thread.start()

    # Kiwoom API 및 PyQt 이벤트 루프를 메인 스레드에서 시작
    start_kiwoom() 
