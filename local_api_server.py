from flask import Flask, jsonify, request
import os
import logging
import traceback
import pandas as pd
from pykiwoom.kiwoom import *
import time
import threading

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- 키움 API 전역 상태 ---
kiwoom = None
connected = False
account_number = None
trade_status = "stop"

# --- 타임아웃 처리 함수 ---
def run_with_timeout(target_func, args=(), kwargs={}, timeout=10):
    result = {}
    error_occurred = False

    def wrapper():
        nonlocal error_occurred
        try:
            result["value"] = target_func(*args, **kwargs)
        except Exception as e:
            result["error"] = str(e)
            error_occurred = True
            logger.error(f"Error in target_func '{target_func.__name__}': {e}")
            logger.error(traceback.format_exc())

    thread = threading.Thread(target=wrapper)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        logger.warning(f"Function '{target_func.__name__}' timed out after {timeout} seconds.")
        return None, "timeout"
    
    if error_occurred:
        return None, result.get("error", "Unknown error.")
        
    return result.get("value", None), None

# --- Kiwoom 초기화 ---
def initialize_kiwoom_api():
    global kiwoom, connected, account_number
    logger.info("Initializing Kiwoom API...")

    try:
        kiwoom = Kiwoom()
        kiwoom.CommConnect()
        time.sleep(5)

        if kiwoom.GetConnectState() == 1:
            connected = True
            accounts_raw = kiwoom.GetLoginInfo("ACCNO")
            logger.info(f"accounts_raw from Kiwoom: {accounts_raw} (type: {type(accounts_raw)})")

            if isinstance(accounts_raw, str):
                account_number = accounts_raw.split(';')[0]
            elif isinstance(accounts_raw, list):
                account_number = accounts_raw[0]
            else:
                account_number = None
                logger.warning("No valid account number found.")

            logger.info(f"✅ Connected to Kiwoom API. Using account number: {account_number}")
        else:
            connected = False
            logger.error("❌ Failed to connect to Kiwoom API.")
    except Exception as e:
        connected = False
        logger.error(f"Error initializing Kiwoom API: {e}")
        logger.error(traceback.format_exc())

@app.route('/status', methods=['GET'])
def get_status():
    global connected, account_number, trade_status

    if not connected:
        return jsonify({"status": "error", "message": "키움 API 연결되지 않음"}), 503

    if not account_number:
        return jsonify({"status": "error", "message": "계좌번호 없음"}), 503

    try:
        def request_opw00004_tr():
            return kiwoom.block_request("opw00004",
                                        계좌번호=account_number,
                                        비밀번호="",
                                        상장폐지구분=0,
                                        비밀번호입력매체구분="00",
                                        거래소구분="KRX",
                                        output="계좌평가현황",
                                        next=0)

        account_info, err = run_with_timeout(request_opw00004_tr, timeout=10)
        time.sleep(0.2)

        if err:
            return jsonify({"status": "error", "message": f"opw00004 실패: {err}"}), 500

        if isinstance(account_info, pd.DataFrame) and not account_info.empty:
            account_data = account_info.iloc[0].to_dict()
        elif isinstance(account_info, dict):
            account_data = account_info
        else:
            return jsonify({"status": "error", "message": "계좌정보 데이터 형식 오류"}), 500

        def request_opw00018_tr():
            return kiwoom.block_request("opw00018",
                                        계좌번호=account_number,
                                        비밀번호="",
                                        조회구분=1,
                                        비밀번호입력매체구분="00",
                                        거래소구분="KRX",
                                        output="종목별계좌평가현황",
                                        next=0)

        stock_info, err2 = run_with_timeout(request_opw00018_tr, timeout=10)
        time.sleep(0.2)

        positions = []
        if isinstance(stock_info, pd.DataFrame):
            for _, row in stock_info.iterrows():
                positions.append({
                    "stock_name": row.get("종목명", "N/A").strip(),
                    "current_price": int(row.get("현재가", 0)),
                    "profit_loss_rate": float(row.get("수익률%", 0.0))
                })
        elif isinstance(stock_info, list):
            for item in stock_info:
                if isinstance(item, dict):
                    positions.append({
                        "stock_name": item.get("종목명", "N/A").strip(),
                        "current_price": int(item.get("현재가", 0)),
                        "profit_loss_rate": float(item.get("수익률%", 0.0))
                    })

        return jsonify({
            "trade_status": trade_status,
            "total_buy_amount": int(account_data.get("총매입금액", 0)),
            "total_eval_amount": int(account_data.get("총평가금액", 0)),
            "total_profit_loss": int(account_data.get("총평가손익금액", 0)),
            "total_profit_loss_rate": float(account_data.get("총수익률", 0.0)),
            "positions": positions
        })

    except Exception as e:
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/trade', methods=['POST'])
def toggle_trade():
    global connected, trade_status

    if not connected:
        return jsonify({"status": "error", "message": "키움 API 연결되지 않음"}), 503

    data = request.get_json()
    if data and data.get("status") in ["start", "stop"]:
        trade_status = data["status"]
        return jsonify({"status": "success", "message": f"매매 상태를 '{trade_status}'로 설정했습니다."})
    return jsonify({"status": "error", "message": "status 값이 start 또는 stop 이어야 합니다."}), 400

if __name__ == "__main__":
    initialize_kiwoom_api()
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Flask 서버 시작 - 포트 {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
