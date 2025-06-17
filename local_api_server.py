# C:\Users\user\stock_auto\local_api_server.py

import os
import sys
import json
import time
import logging
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# --- 모듈 경로 설정 ---
# 이 스크립트의 디렉토리를 기준으로 modules 폴더를 sys.path에 추가
script_dir = os.path.dirname(os.path.abspath(__file__))
modules_path = os.path.join(script_dir, 'modules')
if modules_path not in sys.path:
    sys.path.insert(0, modules_path)
    # logger.info(f"Added modules path to sys.path: {modules_path}") # 디버깅 시 유용

# --- 모듈 임포트 ---
# 주의: 이 경로 설정이 없으면 아래 import에서 오류 발생 가능
from modules.Kiwoom.kiwoom_query_helper import KiwoomQueryHelper
from modules.Kiwoom.kiwoom_tr_request import KiwoomTrRequest
from modules.Kiwoom.monitor_positions import MonitorPositions
from modules.Kiwoom.trade_manager import TradeManager
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
kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager = None, None, None, None
app_initialized = False # Kiwoom API 초기화 성공 여부 플래그

# --- 보안: 로컬 API 키 로드 ---
LOCAL_API_KEY = get_env("LOCAL_API_KEY")
if not LOCAL_API_KEY:
    logger.critical("❌ LOCAL_API_KEY 환경 변수가 설정되지 않았습니다. 서버를 종료합니다.")
    sys.exit(1)

# --- 인증 데코레이터 ---
def api_key_required(f):
    """API 키가 요청 헤더에 포함되어 있는지 확인하는 데코레이터"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key and api_key == LOCAL_API_KEY:
            return f(*args, **kwargs)
        else:
            logger.warning(f"❌ 인증 실패: 잘못된 또는 누락된 API 키 - 요청 IP: {request.remote_addr}")
            return jsonify({"status": "error", "message": "Unauthorized: Missing or invalid API Key"}), 401
    return decorated_function

# --- Kiwoom API 초기화 ---
def initialize_kiwoom_api():
    global kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager, app_initialized

    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception as e:
        logger.warning(f"⚠️ pythoncom 초기화 실패: {e}. Kiwoom API 사용에 문제가 있을 수 있습니다.")
        # pythoncom 초기화 실패하더라도 KiwoomHelper 내에서 재시도할 수 있으므로 바로 종료하지 않음.
        # 하지만 대부분의 경우 Kiwoom API는 pythoncom이 필수.

    accounts_str = get_env("ACCOUNT_NUMBERS")
    account_number = accounts_str.split(',')[0].strip() if accounts_str else None

    kiwoom_helper = KiwoomQueryHelper()
    if not kiwoom_helper.connect_kiwoom():
        logger.critical("❌ Kiwoom API 연결 실패. 애플리케이션을 종료합니다.")
        try:
            import pythoncom
            pythoncom.CoUninitialize() # 연결 실패 시 COM 해제 시도
        except Exception as e_uninit:
            logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")
        return False

    if not account_number:
        # .env에 계좌번호가 없으면 Kiwoom API에서 직접 가져옴
        login_accounts = kiwoom_helper.get_login_info("ACCNO")
        if login_accounts:
            account_number = login_accounts.split(';')[0].strip()
        
        if not account_number:
            logger.critical("❌ 계좌번호를 가져올 수 없습니다. Kiwoom API 연결을 해제하고 종료합니다.")
            kiwoom_helper.disconnect_kiwoom()
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception as e_uninit:
                logger.warning(f"CoUninitialize 중 오류 발생: {e_uninit}")
            return False

    kiwoom_tr_request = KiwoomTrRequest(kiwoom_helper)
    monitor_positions = MonitorPositions(kiwoom_helper, kiwoom_tr_request, account_number)
    trade_manager = TradeManager(kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number)

    app_initialized = True
    logger.info(f"✅ Kiwoom API 초기화 완료 - 계좌번호: {account_number}")
    return True

# --- ngrok 감지 및 Render 업데이트 ---
def detect_and_notify_ngrok():
    """ngrok URL을 감지하고 Render 서버로 업데이트를 요청합니다."""
    try:
        ngrok_port = get_env("NGROK_API_PORT", "4040")
        response = requests.get(f"http://127.0.0.1:{ngrok_port}/api/tunnels", timeout=5) # 타임아웃 추가
        response.raise_for_status() # HTTP 에러 시 예외 발생
        tunnels = response.json().get("tunnels", [])
        https_url = next((t["public_url"] for t in tunnels if t["proto"] == "https"), None)

        if https_url:
            logger.info(f"📡 Ngrok URL 감지됨: {https_url}")
            send_telegram_message(f"📡 새로운 ngrok URL 감지:\n`{https_url}`") # 텔레그램 알림

            # Render 서버의 내부 업데이트 엔드포인트로 URL 자동 전송
            render_public_url = get_env("RENDER_PUBLIC_URL") # Render 서비스의 실제 공용 URL
            if render_public_url:
                # /update_ngrok_internal 엔드포인트는 Render 서버의 server.py에 구현되어야 함
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
                        timeout=10 # 타임아웃 추가
                    )
                    update_response.raise_for_status()
                    logger.info(f"✅ Render 서버 응답: {update_response.status_code} - {update_response.text}")
                except requests.exceptions.RequestException as req_e:
                    logger.warning(f"⚠️ Render 서버로 ngrok URL 업데이트 요청 실패: {req_e}")
                except Exception as e_inner:
                    logger.warning(f"⚠️ Render 서버 업데이트 중 예기치 않은 오류: {e_inner}")
            else:
                logger.warning("RENDER_PUBLIC_URL 환경 변수가 설정되지 않아 Render 서버에 업데이트를 보낼 수 없습니다.")
        else:
            logger.warning("❌ HTTPS Ngrok 터널을 찾지 못했습니다.")
    except requests.exceptions.RequestException as req_e:
        logger.error(f"❌ Ngrok API 접근 실패: {req_e} - ngrok이 실행 중인지, 포트가 맞는지 확인하세요.")
    except Exception as e:
        logger.error(f"❌ Ngrok URL 감지 및 알림 실패: {e}", exc_info=True)

# --- Flask 엔드포인트 ---
@app.route('/')
def home():
    return "Local API Server is running!"

@app.route('/status')
@api_key_required
def status():
    if not app_initialized:
        return jsonify({"status": "error", "message": "Kiwoom API not initialized. Please wait or check logs."}), 503

    try:
        account_info = kiwoom_tr_request.request_account_info(monitor_positions.account_number)
        positions = monitor_positions.get_current_positions()
        
        return jsonify({
            "status": "ok",
            "server_time": get_current_time_str(),
            "kiwoom_connected": app_initialized,
            "account_number": monitor_positions.account_number,
            "balance": account_info.get("예수금", 0),
            "total_asset": account_info.get("총평가자산", 0),
            "positions": positions
        })
    except Exception as e:
        logger.exception("상태 조회 실패:") # 오류 발생 시 traceback 포함
        return jsonify({"status": "error", "message": f"Failed to retrieve status: {e}"}), 500

@app.route('/buy', methods=['POST'])
@api_key_required
def buy():
    if not app_initialized:
        return jsonify({"status": "error", "message": "Kiwoom API not initialized. Please wait or check logs."}), 503

    data = request.get_json()
    stock_code = data.get("stock_code")
    quantity = data.get("quantity")
    price = data.get("price", 0) # 기본값 0 (시장가)
    order_type = data.get("order_type", "지정가") # '지정가' 또는 '시장가'

    # 입력값 유효성 검사 강화
    if not all([stock_code, quantity is not None]): # quantity가 0일 수도 있으므로 'is not None'
        return jsonify({"status": "error", "message": "Missing stock_code or quantity"}), 400
    
    try:
        quantity = int(quantity)
        if quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid quantity. Must be a positive integer."}), 400
    
    try:
        price = int(price)
        if price < 0: # 가격은 0 이상 (시장가 0)
            raise ValueError("Price must be a non-negative integer.")
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid price. Must be a non-negative integer."}), 400

    try:
        order_type_code = 1  # 1: 신규매수
        hoga_gb = "00" if order_type == "지정가" and price > 0 else "03" # 00: 지정가, 03: 시장가
        
        # 시장가 매수인데 가격이 설정된 경우 경고 또는 오류 처리 (선택적)
        if hoga_gb == "03" and price > 0:
            logger.warning(f"시장가 매수 요청에 가격이 지정되었습니다. 가격은 무시됩니다. Stock: {stock_code}")
            price = 0 # 시장가 주문 시 가격은 0으로 설정

        result = trade_manager.place_order(stock_code, order_type_code, quantity, price, hoga_gb)
        
        # 결과 메시지를 좀 더 명확하게 구성 (성공 시 메시지 포함)
        return jsonify({"status": "success", "message": "Buy order placed successfully", "result": result}), 200
    except Exception as e:
        logger.exception(f"매수 실패: Stock Code: {stock_code}, Qty: {quantity}, Price: {price}, Type: {order_type}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/sell', methods=['POST'])
@api_key_required
def sell():
    if not app_initialized:
        return jsonify({"status": "error", "message": "Kiwoom API not initialized. Please wait or check logs."}), 503

    data = request.get_json()
    stock_code = data.get("stock_code")
    quantity = data.get("quantity")
    price = data.get("price", 0) # 기본값 0 (시장가)
    order_type = data.get("order_type", "지정가") # '지정가' 또는 '시장가'

    # 입력값 유효성 검사 강화
    if not all([stock_code, quantity is not None]):
        return jsonify({"status": "error", "message": "Missing stock_code or quantity"}), 400
    
    try:
        quantity = int(quantity)
        if quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid quantity. Must be a positive integer."}), 400
    
    try:
        price = int(price)
        if price < 0:
            raise ValueError("Price must be a non-negative integer.")
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid price. Must be a non-negative integer."}), 400

    try:
        order_type_code = 2  # 2: 신규매도
        hoga_gb = "00" if order_type == "지정가" and price > 0 else "03" # 00: 지정가, 03: 시장가

        # 시장가 매도인데 가격이 설정된 경우 경고 또는 오류 처리 (선택적)
        if hoga_gb == "03" and price > 0:
            logger.warning(f"시장가 매도 요청에 가격이 지정되었습니다. 가격은 무시됩니다. Stock: {stock_code}")
            price = 0 # 시장가 주문 시 가격은 0으로 설정

        result = trade_manager.place_order(stock_code, order_type_code, quantity, price, hoga_gb)
        
        # 결과 메시지를 좀 더 명확하게 구성 (성공 시 메시지 포함)
        return jsonify({"status": "success", "message": "Sell order placed successfully", "result": result}), 200
    except Exception as e:
        logger.exception(f"매도 실패: Stock Code: {stock_code}, Qty: {quantity}, Price: {price}, Type: {order_type}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- 서버 실행 ---
if __name__ == '__main__':
    logger.info("📡 Local API Server 시작 중...")
    if not initialize_kiwoom_api():
        sys.exit(1)
    
    # Kiwoom API 초기화 후 ngrok 터널이 뜰 충분한 시간을 줌
    logger.info("Ngrok 터널 활성화를 위해 5초 대기...")
    time.sleep(5) 
    detect_and_notify_ngrok()

    logger.info(f"Flask 서버 실행 중: http://0.0.0.0:{API_SERVER_PORT}")
    # debug=True는 개발 중에는 유용하지만, 프로덕션 환경에서는 False로 설정하는 것이 좋음.
    # use_reloader=False는 Kiwoom API와 같은 COM 객체 사용 시 충돌 방지를 위해 필수.
    app.run(host="0.0.0.0", port=int(API_SERVER_PORT), debug=True, use_reloader=False)
