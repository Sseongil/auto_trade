# local_api_server.py

import os
import sys
import json
import time as time_module
import logging
import threading
import requests
from functools import wraps
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from datetime import datetime, time

# --- 초기 설정 ---
load_dotenv()

# 로깅 설정 (파일 상단으로 이동)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the directory containing this script to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Add the 'modules' directory to sys.path
modules_path = os.path.join(script_dir, "modules")
if modules_path not in sys.path:
    sys.path.insert(0, modules_path)

# Flask 애플리케이션 초기화
# template_folder와 static_folder를 명시적으로 지정하여 경로 문제를 방지
app = Flask(__name__, template_folder=os.path.join(script_dir, "templates"), static_folder=os.path.join(script_dir, "static"))

# --- 공통 모듈 임포트 (경로 설정 후) ---
# 이제 sys.path에 'modules'가 있으므로, 'modules.' 접두사 없이 임포트 가능
from common.config import API_SERVER_PORT, API_KEY, ACCOUNT_NUMBERS, ACCOUNT_PASSWORD
from common.utils import get_current_time_str
from strategies.main_strategy_loop import (
    run_daily_trading_cycle, set_strategy_flag, strategy_flags, set_real_condition_info,
    initialize_real_time_condition_manager # 새로 추가된 함수 임포트
)
from trade_logger import TradeLogger
from notify import send_telegram_message

# --- 전역 상태 ---
shared_state_lock = threading.Lock()
# Initialize shared_kiwoom_state with default values.
# These will be updated by the Kiwoom initialization thread.
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
    "ngrok_url": "N/A" # Added for ngrok URL display
}
app_initialized = threading.Event() # Use threading.Event for better synchronization

# Global instances for Kiwoom modules, accessed by the Flask thread.
# These must be initialized in the PyQt thread and then assigned here.
kiwoom_helper_instance = None
kiwoom_tr_request_instance = None
monitor_positions_instance = None
trade_manager_instance = None
trade_logger_instance = TradeLogger() # Initialize TradeLogger once globally

# --- 인증 데코레이터 ---
def api_key_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.headers.get("X-API-Key") == API_KEY:
            return f(*args, **kwargs)
        logger.warning(f"❌ API 키 인증 실패: {request.remote_addr}")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return wrapper

# --- 대시보드 ---
@app.route("/")
def dashboard():
    # Pass API_KEY to the template for client-side use
    return render_template("index.html", api_key=API_KEY)

# --- 상태 API ---
@app.route("/status")
@api_key_required
def status():
    try:
        with shared_state_lock:
            # ngrok_url is updated in the main block and stored in os.environ
            current_ngrok = os.getenv("LOCAL_API_SERVER_URL", "ngrok URL 미확인")
            shared_kiwoom_state["ngrok_url"] = current_ngrok # Update shared state
            return jsonify({
                "status": "ok" if app_initialized.is_set() else "initializing",
                "server_time": get_current_time_str(),
                "account_number": shared_kiwoom_state["account_number"],
                "balance": shared_kiwoom_state["balance"],
                "positions": shared_kiwoom_state["positions"],
                "last_kiwoom_update": shared_kiwoom_state["last_kiwoom_update"],
                "kiwoom_connected": shared_kiwoom_state["kiwoom_connected"],
                "condition_check_enabled": shared_kiwoom_state["condition_check_enabled"],
                "buy_strategy_enabled": shared_kiwoom_state["buy_strategy_enabled"],
                "exit_strategy_enabled": shared_kiwoom_state["exit_strategy_enabled"],
                "real_condition_name": shared_kiwoom_state["real_condition_name"],
                "ngrok_url": shared_kiwoom_state["ngrok_url"] # Return from shared state
            })
    except Exception as e:
        logger.exception(f"❌ /status API 처리 중 오류 발생: {e}")
        return jsonify({"status": "error", "message": f"서버 상태를 가져오는 중 오류 발생: {e}"}), 500

# --- 전략 토글 ---
@app.route("/toggle_strategy", methods=["POST"])
@api_key_required
def toggle_strategy():
    data = request.get_json()
    name, enabled = data.get("strategy_name"), data.get("enabled")
    if name not in strategy_flags or not isinstance(enabled, bool):
        return jsonify({"status": "error", "message": "전략 이름 또는 형식 오류"}), 400

    with shared_state_lock:
        set_strategy_flag(name, enabled) # Update flag in main_strategy_loop module
        shared_kiwoom_state[name] = enabled # Update shared state for dashboard
    
    message = f"전략 '{name}'이(가) {'활성화' if enabled else '비활성화'}되었습니다."
    send_telegram_message(message)
    logger.info(message)
    return jsonify({"status": "success", "message": message})

# --- 조건 검색 설정 ---
@app.route("/set_real_condition", methods=["POST"])
@api_key_required
def set_real_condition():
    global kiwoom_helper_instance # Access the global instance
    data = request.get_json()
    name, mode = data.get("condition_name"), data.get("search_type")

    if not name or mode not in ["0", "1"]:
        return jsonify({"status": "error", "message": "파라미터 오류"}), 400
    
    # Kiwoom API가 초기화되었고 연결되었는지 확인
    if not app_initialized.is_set() or not kiwoom_helper_instance or not kiwoom_helper_instance.connected:
        return jsonify({"status": "error", "message": "Kiwoom API가 초기화되지 않았거나 연결되지 않았습니다."}), 503

    try:
        condition_list = kiwoom_helper_instance.get_condition_list()
        index = condition_list.get(name)

        if index is None:
            return jsonify({"status": "error", "message": f"조건식 '{name}'을(를) 찾을 수 없습니다."}), 404
        
        screen_no = kiwoom_helper_instance.generate_condition_screen_no()
        # SendCondition의 search_type은 0(등록) 또는 1(해제)
        success = kiwoom_helper_instance.SendCondition(screen_no, name, index, int(mode))

        if success:
            with shared_state_lock:
                if mode == "0": # 등록
                    set_real_condition_info(name, index) # Update flag in main_strategy_loop module
                    shared_kiwoom_state["real_condition_name"] = name # Update shared state for dashboard
                else: # 해제
                    # 조건식 해제 시, main_strategy_loop의 real_condition_name과 index를 None으로 설정
                    set_real_condition_info(None, None) # Update flag in main_strategy_loop module
                    shared_kiwoom_state["real_condition_name"] = None # Update shared state for dashboard
            message = f"조건식 '{name}' {'등록' if mode == '0' else '해제'} 요청 성공."
            send_telegram_message(message)
            logger.info(message)
            return jsonify({"status": "success", "message": message})
        else:
            message = f"조건식 '{name}' {'등록' if mode == '0' else '해제'} 요청 실패."
            send_telegram_message(message)
            logger.error(message)
            return jsonify({"status": "error", "message": message}), 500
    except Exception as e:
        logger.exception(f"❌ 조건식 설정 중 오류 발생: {e}")
        return jsonify({"status": "error", "message": f"조건식 설정 중 오류 발생: {e}"}), 500


# --- 거래 로그 조회 ---
@app.route("/trade_history")
@api_key_required
def trade_history():
    try:
        logging.info("🧾 거래 로그 요청 수신")
        # Use the shared TradeLogger instance
        logs = trade_logger_instance.get_trade_log()
        return jsonify({"status": "success", "trade_history": logs})
    except Exception as e:
        logger.exception(f"❌ /trade_history API 처리 중 오류 발생: {e}")
        return jsonify({"status": "error", "message": f"거래 내역을 가져오는 중 오류 발생: {e}"}), 500

# --- 거래 로그 삭제 ---
@app.route('/trade_history/clear', methods=['POST'])
@api_key_required
def clear_trade_history():
    logging.info("🗑️ 거래 로그 삭제 요청 수신")
    try:
        # Use the shared TradeLogger instance
        if trade_logger_instance.clear_trade_log():
            message = "모든 거래 로그가 성공적으로 삭제되었습니다."
            logger.warning(message)
            send_telegram_message(f"🗑️ {message}")
            return jsonify({"status": "success", "message": message})
        else:
            message = "삭제할 거래 로그 파일이 없거나 삭제에 실패했습니다."
            logger.info(message)
            return jsonify({"status": "info", "message": message})
    except Exception as e:
        logger.error(f"❌ 거래 로그 삭제 중 오류 발생: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"거래 로그 삭제 실패: {e}"}), 500


# --- Kiwoom 초기화 및 트레이딩 루프 (PyQt 스레드에서 실행) ---
def initialize_kiwoom_and_run_trading_loop():
    """
    This function runs in a dedicated thread. It initializes PyQt, Kiwoom API,
    and then starts a QTimer to periodically run the trading cycle within this thread.
    All COM object interactions must happen within this thread.
    """
    import pythoncom
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QAxContainer import QAxWidget
    from PyQt5.QtCore import QTimer # Import QTimer for scheduling
    # Import Kiwoom modules locally within this function to ensure they are
    # initialized in the correct thread context.
    from Kiwoom.kiwoom_query_helper import KiwoomQueryHelper
    from Kiwoom.kiwoom_tr_request import KiwoomTrRequest
    from Kiwoom.monitor_positions import MonitorPositions
    from Kiwoom.trade_manager import TradeManager
    # RealTimeConditionManager도 이 스레드에서 초기화되어야 합니다.
    from Kiwoom.real_time_condition_manager import RealTimeConditionManager
    from strategies.main_strategy_loop import initialize_real_time_condition_manager # main_strategy_loop의 초기화 함수 임포트

    pythoncom.CoInitialize() # Initialize COM for this thread

    pyqt_app = QApplication([]) # Create QApplication instance for this thread
    ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
    
    # Pass pyqt_app to KiwoomQueryHelper as it needs it for event loops etc.
    kiwoom_helper = KiwoomQueryHelper(ocx, pyqt_app) 
    
    # Connect to Kiwoom API
    if not kiwoom_helper.connected: # Check if already connected (from previous attempts)
        if not kiwoom_helper.connect_kiwoom(timeout_ms=10000): # Use timeout
            logger.critical("❌ Kiwoom API 연결 실패. 자동매매 시스템을 시작할 수 없습니다.")
            send_telegram_message("🚨 자동매매 서버 시작 실패: Kiwoom API 연결 불가.")
            pyqt_app.quit() # Ensure PyQt app exits if connection fails
            return # Exit the thread

    account = ACCOUNT_NUMBERS.split(",")[0].strip()
    kiwoom_tr = KiwoomTrRequest(kiwoom_helper, pyqt_app, ACCOUNT_PASSWORD)
    monitor = MonitorPositions(kiwoom_helper, kiwoom_tr, None, account)
    trade_manager = TradeManager(kiwoom_helper, kiwoom_tr, monitor, account)
    monitor.set_trade_manager(trade_manager)

    # RealTimeConditionManager 초기화 및 main_strategy_loop에 전달
    initialize_real_time_condition_manager(kiwoom_helper)


    # Assign instances to global variables for Flask access
    global kiwoom_helper_instance, kiwoom_tr_request_instance, monitor_positions_instance, trade_manager_instance
    kiwoom_helper_instance = kiwoom_helper
    kiwoom_tr_request_instance = kiwoom_tr
    monitor_positions_instance = monitor
    trade_manager_instance = trade_manager

    # Initial balance and positions update for shared state
    balance = kiwoom_tr.request_account_info(account).get("예수금", 0)
    with shared_state_lock:
        shared_kiwoom_state.update({
            "account_number": account,
            "balance": balance,
            "positions": monitor.get_all_positions(),
            "last_kiwoom_update": get_current_time_str(),
            "kiwoom_connected": kiwoom_helper.connected # Use kiwoom_helper.connected state
        })
    
    app_initialized.set() # Signal that app is initialized
    send_telegram_message("✅ Kiwoom API 및 자동매매 서버 초기화 완료")
    logger.info("✅ Kiwoom API 및 자동매매 서버 초기화 완료.")

    # --- Schedule trading loop using QTimer ---
    # This ensures run_daily_trading_cycle is called periodically on the PyQt thread.
    trading_timer = QTimer()
    trading_timer.timeout.connect(lambda: _run_trading_cycle_on_pyqt_thread(
        kiwoom_helper, kiwoom_tr, monitor, trade_manager
    ))
    trading_timer.start(30000) # Run every 30 seconds (30000 ms)

    # Start the PyQt event loop (this is a blocking call)
    pyqt_app.exec_()
    logger.info("PyQt application event loop finished.")


def _run_trading_cycle_on_pyqt_thread(kiwoom_helper, kiwoom_tr, monitor, trade_manager):
    """
    Wrapper function to run the daily trading cycle and update shared state.
    This function is called by QTimer on the PyQt thread.
    """
    try:
        # Update strategy flags in main_strategy_loop module from shared_kiwoom_state
        # This ensures the trading logic respects the flags set via the Flask API.
        with shared_state_lock:
            set_strategy_flag("condition_check_enabled", shared_kiwoom_state["condition_check_enabled"])
            set_strategy_flag("buy_strategy_enabled", shared_kiwoom_state["buy_strategy_enabled"])
            set_strategy_flag("exit_strategy_enabled", shared_kiwoom_state["exit_strategy_enabled"])
            # Pass condition name and index to main_strategy_loop for real condition handling
            # Ensure real_condition_index is retrieved safely
            set_real_condition_info(shared_kiwoom_state["real_condition_name"], strategy_flags.get("real_condition_index"))

        run_daily_trading_cycle(kiwoom_helper, kiwoom_tr, monitor, trade_manager)

        # Update shared state after running the cycle
        with shared_state_lock:
            account_info = kiwoom_tr.request_account_info(shared_kiwoom_state["account_number"])
            shared_kiwoom_state["balance"] = account_info.get("예수금", 0)
            shared_kiwoom_state["positions"] = monitor.get_all_positions()
            shared_kiwoom_state["last_kiwoom_update"] = get_current_time_str()
            shared_kiwoom_state["kiwoom_connected"] = kiwoom_helper.connected
            # Strategy flags are already updated via set_strategy_flag in this function
            # real_condition_name is updated via set_real_condition_info in this function
            
    except Exception as e:
        logger.exception(f"🔥 PyQt 스레드 내 트레이딩 루프 오류: {e}")
        send_telegram_message(f"🔥 PyQt 스레드 내 트레이딩 루프 오류: {e}")


# --- ngrok 주소 감지 ---
def detect_ngrok_url():
    try:
        # ngrok API endpoint is usually at 4040
        res = requests.get("http://localhost:4040/api/tunnels", timeout=5)
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
    render_api_key = os.getenv("RENDER_API_KEY")
    render_service_id = os.getenv("RENDER_SERVICE_ID")
    if not render_api_key or not render_service_id:
        logger.warning("⚠️ RENDER_API_KEY 또는 RENDER_SERVICE_ID 환경 변수가 설정되지 않았습니다. Render 환경 변수 동기화를 건너뜜.")
        return

    headers = {
        "Authorization": f"Bearer {render_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    try:
        # Fetch current environment variables
        res = requests.get(f"https://api.render.com/v1/services/{render_service_id}/env-vars", headers=headers, timeout=10)
        res.raise_for_status()
        envs = res.json()

        # Check if LOCAL_API_SERVER_URL needs update
        updated = False
        new_envs_list = []
        found_existing = False
        for env in envs:
            if env["key"] == "LOCAL_API_SERVER_URL":
                found_existing = True
                if env["value"] != ngrok_url_to_sync:
                    env["value"] = ngrok_url_to_sync
                    updated = True
            new_envs_list.append(env)
        
        if not found_existing: # Add if not present
            new_envs_list.append({"key": "LOCAL_API_SERVER_URL", "value": ngrok_url_to_sync})
            updated = True

        if updated:
            # Update environment variables
            put_res = requests.put(
                f"https://api.render.com/v1/services/{render_service_id}/env-vars",
                headers=headers,
                json=new_envs_list, # Send the full list back
                timeout=10
            )
            put_res.raise_for_status()
            logger.info("✅ Render 환경변수 LOCAL_API_SERVER_URL 업데이트 완료.")
            
            # Trigger redeploy if successful
            redeploy_hook_url = os.getenv("RENDER_DEPLOY_HOOK_URL")
            if redeploy_hook_url:
                resp = requests.post(redeploy_hook_url, timeout=10)
                resp.raise_for_status()
                logger.info("✅ Render 재배포 요청 완료.")
            else:
                logger.warning("⚠️ RENDER_DEPLOY_HOOK_URL 환경 변수가 설정되지 않았습니다. 재배포를 건너뜜.")
        else:
            logger.info("ℹ️ LOCAL_API_SERVER_URL 변경 없음. Render 환경변수 업데이트 건너뜜.")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Render API 업데이트/조회 중 오류: {e}")
    except json.JSONDecodeError:
        logger.error("❌ Render API 응답 JSON 디코딩 실패.")
    except Exception as e:
        logger.error(f"❌ Render API 동기화 중 알 수 없는 오류: {e}")


# --- 서버 실행 ---
if __name__ == "__main__":
    # Detect ngrok URL and sync to Render (runs in main thread before Flask starts)
    ngrok_url_detected = detect_ngrok_url()
    if ngrok_url_detected:
        logger.info(f"✅ 감지된 ngrok 주소: {ngrok_url_detected}")
        # Store in os.environ for other parts of the app (e.g., status API)
        os.environ["LOCAL_API_SERVER_URL"] = ngrok_url_detected
        sync_ngrok_to_render(ngrok_url_detected)
    else:
        logger.warning("⚠️ ngrok 주소 탐지 실패 (4040 포트 미실행 또는 ngrok 미설치).")
        os.environ["LOCAL_API_SERVER_URL"] = "N/A" # Ensure it's set to N/A if not found

    # Start the Kiwoom initialization and PyQt event loop in a separate thread.
    # This thread will also manage the trading cycle via QTimer.
    kiwoom_thread = threading.Thread(target=initialize_kiwoom_and_run_trading_loop, daemon=True)
    kiwoom_thread.start()

    # Wait for Kiwoom initialization to complete
    init_timeout_sec = 120 # 2 minutes timeout
    start_wait_time = time_module.time()
    while not app_initialized.is_set() and (time_module.time() - start_wait_time) < init_timeout_sec:
        time_module.sleep(1)

    if not app_initialized.is_set():
        logger.critical("❌ Kiwoom API 초기화 타임아웃. Flask 서버를 시작할 수 없습니다.")
        sys.exit(1)

    logger.info(f"🌐 Flask API 서버 시작 (포트 {API_SERVER_PORT})...")
    # Run Flask app in the main thread
    try:
        app.run(host="0.0.0.0", port=API_SERVER_PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.critical(f"❌ Flask 서버 시작 실패: {e}")
        sys.exit(1)

