# C:\Users\user\stock_auto\local_api_server.py

from flask import Flask, jsonify, request
import os
import logging
from pykiwoom.kiwoom import *
import time
import traceback

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- 키움증권 API 관련 전역 변수 초기화 ---
kiwoom = None
connected = False
account_number = None
trade_status = "stop"

def initialize_kiwoom_api():
    global kiwoom, connected, account_number, trade_status
    logger.info("Initializing Kiwoom API...")
    try:
        kiwoom = Kiwoom()
        kiwoom.CommConnect()
        time.sleep(5) 

        if kiwoom.GetConnectState() == 1:
            connected = True
            logger.info("Kiwoom API connected successfully!")
            
            accounts_raw = kiwoom.GetLoginInfo("ACCNO")
            logger.info(f"Raw accounts info from Kiwoom: {accounts_raw} (Type: {type(accounts_raw)})")

            if isinstance(accounts_raw, str) and accounts_raw:
                account_number = accounts_raw.split(';')[0]
                logger.info(f"Using account number: {account_number}")
                logger.info(f"Connected accounts (string): {accounts_raw}")
            elif isinstance(accounts_raw, list) and accounts_raw:
                account_number = str(accounts_raw[0])
                logger.info(f"Using account number (from list): {account_number}. Full list: {accounts_raw}")
            else:
                account_number = None
                logger.warning("No account numbers found or unexpected format from Kiwoom API.")
                logger.info(f"Received accounts_raw: {accounts_raw} (Type: {type(accounts_raw)})")
        else:
            connected = False
            logger.error("Failed to connect to Kiwoom API. Please check Kiwoom HTS login.")
    except Exception as e:
        connected = False
        logger.error(f"Error initializing Kiwoom API: {e}")
        logger.error(traceback.format_exc())


@app.route('/status', methods=['GET'])
def get_status():
    global connected, account_number, trade_status 
    if not connected:
        logger.warning("/status request received but Kiwoom API is not connected.")
        return jsonify({"status": "error", "message": "키움 API가 연결되지 않았습니다. 영웅문4 HTS를 실행하고 로그인해주세요."}), 503

    if not account_number:
        logger.error("Account number is not set. Cannot retrieve status.")
        return jsonify({"status": "error", "message": "계좌 번호를 가져올 수 없습니다. 로그인 정보를 확인해주세요."}), 503

    try:
        # opw00004 (계좌평가현황요청) TR 요청
        # TR 요청 시도를 로그로 남김
        logger.info(f"Attempting block_request for opw00004 with account: {account_number}")
        account_info = kiwoom.block_request("opw00004", 
                                            계좌번호=account_number, 
                                            비밀번호="", 
                                            상장폐지구분=0, 
                                            비밀번호입력매체구분="00", 
                                            거래소구분="KRX")
        
        # <<< 핵심 디버그 코드 삽입: block_request 직후 반환 값 확인 >>>
        logger.info(f"RAW result from opw00004 block_request: {account_info} (Type: {type(account_info)})")
        if account_info is None:
            logger.error("block_request for opw00004 returned None. Kiwoom API request might have failed.")
            return jsonify({"status": "error", "message": "계좌평가현황 조회 실패: 키움 API 응답 없음."}), 500
        
        # 만약 dict 안에 'output' 키가 있고 그 안에 데이터가 있다면 아래와 같이 처리할 수도 있습니다.
        # 하지만 일단은 pykiwoom의 일반적인 패턴(dict 또는 list of dicts)을 따르도록 하겠습니다.
        # if isinstance(account_info, dict) and 'output' in account_info and isinstance(account_info['output'], dict):
        #     account_info = account_info['output']
        
        time.sleep(0.2) # TR 요청 간 딜레이 추가

        # opw00018 (계좌평가잔고내역요청) TR 요청 - 보유 종목 정보
        logger.info(f"Attempting block_request for opw00018 with account: {account_number}")
        account_stocks = kiwoom.block_request("opw00018", 
                                              계좌번호=account_number, 
                                              비밀번호="", 
                                              조회구분=1, 
                                              비밀번호입력매체구분="00", 
                                              거래소구분="KRX")

        logger.info(f"RAW result from opw00018 block_request: {account_stocks} (Type: {type(account_stocks)})")
        if account_stocks is None:
            logger.error("block_request for opw00018 returned None. Kiwoom API request might have failed.")
            # 이 시점에서는 이미 opw00004에서 성공했으니 오류를 다르게 처리할 수도 있습니다.
            # 일단은 진행하고 오류가 나면 해당 TR이 문제임을 알 수 있도록 합니다.
            # return jsonify({"status": "error", "message": "계좌평가잔고내역 조회 실패: 키움 API 응답 없음."}), 500

        # TR 결과 파싱 및 데이터 구성
        total_buy_amount = 0
        total_eval_amount = 0
        total_profit_loss = 0
        total_profit_loss_rate = 0.0
        
        # opw00004의 Single Data 파싱
        # (이전 로그에서 이 라인에서 Key Error가 났으므로, account_info의 실제 값을 확인하는 것이 중요)
        logger.info(f"Parsing Account Info from opw00004. Current account_info: {account_info} (Type: {type(account_info)})")
        if isinstance(account_info, dict):
            total_buy_amount = int(account_info.get('총매입금액', 0))
            total_eval_amount = int(account_info.get('총평가금액', 0))
            total_profit_loss = int(account_info.get('총평가손익금액', 0))
            total_profit_loss_rate = float(account_info.get('총수익률', 0.0))
        elif isinstance(account_info, list) and account_info and isinstance(account_info[0], dict):
            logger.warning("Account info was a list, using first element as dict.")
            account_info_dict = account_info[0]
            total_buy_amount = int(account_info_dict.get('총매입금액', 0))
            total_eval_amount = int(account_info_dict.get('총평가금액', 0))
            total_profit_loss = int(account_info_dict.get('총평가손익금액', 0))
            total_profit_loss_rate = float(account_info_dict.get('총수익률', 0.0))
        else:
            logger.error(f"Unexpected data type for account_info: {type(account_info)}. Data: {account_info}")
            raise ValueError(f"Failed to retrieve valid account info from opw00004: Unexpected data format.")


        current_positions = []
        # opw00018의 Multi Data 파싱
        logger.info(f"Parsing Account Stocks from opw00018. Current account_stocks: {account_stocks} (Type: {type(account_stocks)})")
        if account_stocks and isinstance(account_stocks, list):
            for stock in account_stocks:
                if isinstance(stock, dict):
                    current_positions.append({
                        "stock_name": stock.get('종목명', 'N/A'),
                        "current_price": int(stock.get('현재가', 0)),
                        "profit_loss_rate": float(stock.get('수익률%', 0.0))
                    })
                else:
                    logger.warning(f"Unexpected stock data type: {type(stock)}. Skipping: {stock}")
        else:
            logger.error(f"Unexpected data type or empty for account_stocks: {type(account_stocks)}. Data: {account_stocks}")
            # opw00018은 계좌에 종목이 없으면 빈 리스트가 올 수 있으므로 반드시 오류는 아님.
            # 여기서는 ValueError를 발생시키지 않겠습니다.


        current_trade_status = trade_status

        status_data = {
            "trade_status": current_trade_status,
            "total_buy_amount": total_buy_amount,
            "total_eval_amount": total_eval_amount,
            "total_profit_loss": total_profit_loss,
            "total_profit_loss_rate": total_profit_loss_rate,
            "positions": current_positions
        }
        logger.info(f"[/status] Request received. Returning (real data): {status_data}")
        return jsonify(status_data)

    except Exception as e:
        logger.error(f"Error retrieving Kiwoom data: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": f"키움 API 데이터 조회 중 오류 발생: {e}"}), 500


# Flask 라우트 (POST /trade)
@app.route('/trade', methods=['POST'])
def toggle_trade():
    global connected, trade_status
    if not connected:
        logger.warning("/trade request received but Kiwoom API is not connected.")
        return jsonify({"status": "error", "message": "키움 API가 연결되지 않았습니다. 매매 상태를 변경할 수 없습니다."}), 503

    data = request.get_json()
    if data and 'status' in data:
        new_status = data['status']
        if new_status in ['start', 'stop']:
            trade_status = new_status
            message = f"매매 스위치를 '{trade_status}'로 변경했습니다."
            logger.info(f"[/trade] Trade status changed to: {trade_status}")
            return jsonify({"status": "success", "message": message})
        else:
            return jsonify({"status": "error", "message": "유효하지 않은 상태 값입니다. 'start' 또는 'stop'이어야 합니다."}), 400
    return jsonify({"status": "error", "message": "요청 본문에 'status' 필드가 필요합니다."}), 400

if __name__ == "__main__":
    initialize_kiwoom_api()

    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Local API server starting Flask app on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=True)