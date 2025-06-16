# C:\Users\user\stock_auto\local_api_server.py

import os
import sys
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv # .env 파일 로드를 위해 추가

# .env 로드
load_dotenv()

# 현재 스크립트 기준 modules 경로 추가
script_dir = os.path.dirname(os.path.abspath(__file__))
modules_path = os.path.join(script_dir, 'modules')
if modules_path not in sys.path:
    sys.path.insert(0, modules_path)  # 우선순위 부여

# 패키지 경로에 맞게 import 수정
from Kiwoom.kiwoom_query_helper import KiwoomQueryHelper
from Kiwoom.kiwoom_tr_request import KiwoomTrRequest
from Kiwoom.monitor_positions import MonitorPositions
from Kiwoom.trade_manager import TradeManager
from common.utils import get_current_time_str # common 폴더로 이동했으므로 수정
from common.config import get_env # common 폴더로 이동했으므로 수정

# Flask 앱 초기화
app = Flask(__name__)

# 글로벌 인스턴스
kiwoom_helper = None
kiwoom_tr_request = None
trade_manager = None
monitor_positions = None
app_initialized = False

def initialize_kiwoom_api():
    global kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions, app_initialized

    if app_initialized:
        print("INFO: Kiwoom API already initialized.")
        return True

    try:
        # .env 파일에서 계좌번호 로드
        accounts_str = get_env("ACCOUNT_NUMBERS")
        print(f"DEBUG: ACCOUNT_NUMBERS from env: {accounts_str}")

        account_number = None
        if isinstance(accounts_str, str):
            # 쉼표로 구분된 계좌번호 중 첫 번째 사용
            account_number = accounts_str.split(',')[0].strip() if accounts_str else None
        
        if not account_number:
            print("ERROR: No valid account number found from .env or GetLoginInfo.")
            # 이 단계에서 계좌번호를 못 찾으면, 실제 키움 연결 후 GetLoginInfo로 다시 시도
            # (아래 kiwoom_helper.connect_kiwoom() 후 호출)
            pass

        # Python COM 초기화 (멀티쓰레딩 환경 고려)
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except pythoncom.com_error as e:
            if e.hresult != -2147417850: # RPC_E_CHANGED_MODE
                raise e

        kiwoom_helper = KiwoomQueryHelper()
        if not kiwoom_helper.connect_kiwoom():
            print("ERROR: Failed to connect to Kiwoom.")
            # 연결 실패 시 CoUninitialize 필요
            pythoncom.CoUninitialize()
            return False

        # 키움 연결 성공 후, GetLoginInfo로 계좌번호 가져오기 (만약 .env에 없었다면)
        if not account_number:
            accounts_from_kiwoom = kiwoom_helper.ocx.GetLoginInfo("ACCNO")
            if accounts_from_kiwoom:
                account_number = accounts_from_kiwoom.split(';')[0].strip()
                print(f"INFO: Using account number from Kiwoom API: {account_number}")
            else:
                print("ERROR: Could not retrieve account number from Kiwoom API.")
                kiwoom_helper.disconnect_kiwoom()
                pythoncom.CoUninitialize()
                return False

        kiwoom_tr_request = KiwoomTrRequest(kiwoom_helper)
        
        # monitor_positions와 trade_manager 초기화 시 account_number 인자 전달
        monitor_positions = MonitorPositions(kiwoom_helper, kiwoom_tr_request, account_number) # kiwoom_tr_request 인자 추가
        trade_manager = TradeManager(kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number) # monitor_positions 인자 추가

        app_initialized = True
        print("INFO: Kiwoom API initialized successfully.")
        return True

    except Exception as e:
        print(f"CRITICAL ERROR during Kiwoom API initialization: {e}")
        # 예외 발생 시 CoUninitialize 시도 (연결이 되었을 수도 있으므로)
        if kiwoom_helper:
            kiwoom_helper.disconnect_kiwoom()
        try:
            pythoncom.CoUninitialize()
        except Exception as e_uninit:
            print(f"WARNING: Error during CoUninitialize: {e_uninit}")
        return False

@app.route('/')
def home():
    return "Local API Server is running!"

@app.route('/status')
def get_status():
    if not app_initialized:
        return jsonify({"status": "error", "message": "Kiwoom API not initialized"}), 503
    try:
        # 계좌 정보 요청 로직 수정
        # account_number는 initialize_kiwoom_api에서 이미 설정됨
        if not kiwoom_helper or not kiwoom_tr_request:
             return jsonify({"status": "error", "message": "Kiwoom helper or TR request not available."}), 500

        # local_api_server.py에서 initialize_kiwoom_api를 통해 account_number가 설정된다고 가정
        # (monitor_positions 또는 trade_manager가 이미 account_number를 가지고 있을 것이므로)
        # 여기서는 편의상 monitor_positions.account_number를 사용합니다.
        account_info = kiwoom_tr_request.request_account_info(monitor_positions.account_number)
        
        positions = monitor_positions.get_current_positions() # 실제 Kiwoom API에서 가져오도록 변경 예정
        
        return jsonify({
            "status": "ok",
            "account_info": account_info,
            "positions": positions,
            "current_time": get_current_time_str()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to retrieve status: {e}"}), 500

@app.route('/buy', methods=['POST'])
def buy_stock():
    if not app_initialized:
        return jsonify({"status": "error", "message": "Kiwoom API not initialized."}), 503

    data = request.get_json()
    stock_code = data.get('stock_code')
    order_type = data.get('order_type', '지정가') # "00" 지정가, "03" 시장가
    price = data.get('price', 0)
    quantity = data.get('quantity')

    if not all([stock_code, quantity]):
        return jsonify({"status": "error", "message": "Missing stock_code or quantity"}), 400

    try:
        # order_type 인자를 실제 키움 API에 맞는 형식으로 변환 (1:매수)
        order_type_kiwoom = 1 # 매수
        hoga_gb = "00" if order_type == "지정가" else "03" # 00: 지정가, 03: 시장가

        result = trade_manager.place_order(stock_code, order_type_kiwoom, quantity, price, hoga_gb)
        
        # 주문 성공 시 monitor_positions 업데이트 (TradeManager에서 처리하도록 변경됨)
        # monitor_positions.update_position(stock_code, quantity, price) # 이미 TradeManager에서 처리
        
        return jsonify({"status": "success", "message": "Buy order placed", "result": result}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to place buy order: {e}"}), 500

@app.route('/sell', methods=['POST'])
def sell_stock():
    if not app_initialized:
        return jsonify({"status": "error", "message": "Kiwoom API not initialized."}), 503

    data = request.get_json()
    stock_code = data.get('stock_code')
    order_type = data.get('order_type', '지정가')
    price = data.get('price', 0)
    quantity = data.get('quantity')

    if not all([stock_code, quantity]):
        return jsonify({"status": "error", "message": "Missing stock_code or quantity"}), 400

    try:
        # order_type 인자를 실제 키움 API에 맞는 형식으로 변환 (2:매도)
        order_type_kiwoom = 2 # 매도
        hoga_gb = "00" if order_type == "지정가" else "03" # 00: 지정가, 03: 시장가

        result = trade_manager.place_order(stock_code, order_type_kiwoom, quantity, price, hoga_gb)
        
        # 주문 성공 시 monitor_positions 업데이트 (TradeManager에서 처리하도록 변경됨)
        # monitor_positions.update_position(stock_code, -quantity, price) # 이미 TradeManager에서 처리
        
        return jsonify({"status": "success", "message": "Sell order placed", "result": result}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to place sell order: {e}"}), 500

if __name__ == '__main__':
    print("Local API Server starting...")
    initialize_kiwoom_api()
    # Flask 서버 포트를 .env에서 가져오도록 수정
    API_SERVER_PORT = int(get_env("PORT", "5000")) 
    app.run(host='0.0.0.0', port=API_SERVER_PORT, debug=True, use_reloader=False)