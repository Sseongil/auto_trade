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
    thread.join(timeout) # 지정된 시간만큼 스레드가 종료되기를 기다림

    if thread.is_alive():
        logger.warning(f"Function '{target_func.__name__}' timed out after {timeout} seconds.")
        return None, "timeout"
    
    if error_occurred:
        return None, result.get("error", "An unknown error occurred in the target function.")
        
    return result.get("value", None), None

# --- Kiwoom 초기화 ---
def initialize_kiwoom_api():
    global kiwoom, connected, account_number
    logger.info("Initializing Kiwoom API...")

    try:
        kiwoom = Kiwoom()
        kiwoom.CommConnect()
        time.sleep(5)  # CommConnect 완료 대기

        if kiwoom.GetConnectState() == 1:
            connected = True
            accounts_raw = kiwoom.GetLoginInfo("ACCNO")
            if isinstance(accounts_raw, str) and accounts_raw:
                account_number = accounts_raw.split(';')[0]
            elif isinstance(accounts_raw, list) and accounts_raw: # pykiwoom 버전 및 환경에 따라 리스트로 반환될 수 있음
                account_number = str(accounts_raw[0])
            else:
                account_number = None
                logger.warning("No account numbers found or unexpected format from Kiwoom API. Type: %s, Data: %s", type(accounts_raw), accounts_raw)
            logger.info(f"Kiwoom API 연결 성공 - 계좌: {account_number}")
        else:
            connected = False
            logger.error("Kiwoom API 연결 실패. 영웅문4 HTS를 실행하고 로그인해주세요.")
    except Exception as e:
        connected = False
        logger.error(f"Kiwoom API 초기화 오류: {e}")
        logger.error(traceback.format_exc())

# --- /status 라우트 ---
@app.route('/status', methods=['GET'])
def get_status():
    global connected, account_number, trade_status

    if not connected:
        logger.warning("/status 요청: Kiwoom API가 연결되지 않았습니다.")
        return jsonify({"status": "error", "message": "키움 API가 연결되지 않았습니다. 영웅문4 HTS를 실행하고 로그인해주세요."}), 503

    if not account_number:
        logger.error("/status 요청: 계좌 번호를 가져올 수 없습니다. 로그인 정보를 확인해주세요.")
        return jsonify({"status": "error", "message": "계좌 번호를 가져올 수 없습니다. 로그인 정보를 확인해주세요."}), 503

    try:
        # --- opw00004 요청 (타임아웃 적용) ---
        def request_opw00004_tr():
            logger.info(f"TR 요청: opw00004 (계좌평가현황) 시작...")
            return kiwoom.block_request("opw00004",
                                         계좌번호=account_number,
                                         비밀번호="",
                                         상장폐지구분=0,
                                         비밀번호입력매체구분="00",
                                         거래소구분="KRX",
                                         output="계좌평가현황",
                                         next=0)

        result_opw, err_opw = run_with_timeout(request_opw00004_tr, timeout=10) # 10초 타임아웃
        time.sleep(0.2) # TR 요청 간 딜레이 추가 (키움증권 가이드라인)

        if err_opw == "timeout":
            logger.error("opw00004 TR 요청 응답 지연 (10초 초과).")
            return jsonify({"status": "error", "message": "계좌평가현황 조회 응답 지연 (10초 초과). Kiwoom HTS 및 API 상태를 확인해주세요."}), 504
        elif err_opw:
            logger.error(f"opw00004 TR 요청 오류: {err_opw}")
            return jsonify({"status": "error", "message": f"계좌평가현황 조회 오류: {err_opw}"}), 500
        
        if result_opw is None:
            logger.error("opw00004 TR 요청 결과가 None입니다. 키움 API 응답이 없거나 예기치 않은 오류가 발생했습니다.")
            return jsonify({"status": "error", "message": "계좌평가현황 조회 실패: 키움 API 응답 없음."}), 500

        # opw00004 결과 파싱
        if isinstance(result_opw, pd.DataFrame) and not result_opw.empty:
            account_data = result_opw.iloc[0].to_dict()
        elif isinstance(result_opw, dict):
            account_data = result_opw
        else:
            logger.error(f"opw00004 데이터 형식 오류: 예상치 못한 타입 - {type(result_opw)}")
            return jsonify({"status": "error", "message": "계좌평가현황 데이터 형식 오류."}), 500

        # --- opw00018 요청 (타임아웃 적용) ---
        def request_opw00018_tr():
            logger.info(f"TR 요청: opw00018 (계좌평가잔고내역) 시작...")
            return kiwoom.block_request("opw00018",
                                         계좌번호=account_number,
                                         비밀번호="",
                                         조회구분=1,
                                         비밀번호입력매체구분="00",
                                         거래소구분="KRX",
                                         output="종목별계좌평가현황",
                                         next=0)

        result_pos, err_pos = run_with_timeout(request_opw00018_tr, timeout=10) # 10초 타임아웃
        time.sleep(0.2) # TR 요청 간 딜레이 추가

        if err_pos == "timeout":
            logger.error("opw00018 TR 요청 응답 지연 (10초 초과).")
            # 이 경우 opw00004는 성공했을 수 있으므로 부분 응답을 줄 수 있지만, 여기서는 오류로 처리
            return jsonify({"status": "error", "message": "계좌평가잔고내역 조회 응답 지연 (10초 초과). Kiwoom HTS 및 API 상태를 확인해주세요."}), 504
        elif err_pos:
            logger.error(f"opw00018 TR 요청 오류: {err_pos}")
            return jsonify({"status": "error", "message": f"계좌평가잔고내역 조회 오류: {err_pos}"}), 500
            
        # opw00018 결과 파싱 (종목이 없을 수 있으므로 None/empty DataFrame/empty list 처리)
        positions = []
        if isinstance(result_pos, pd.DataFrame) and not result_pos.empty:
            for _, row in result_pos.iterrows():
                positions.append({
                    "stock_name": row.get("종목명", "N/A").strip(), # 공백 제거
                    "current_price": int(row.get("현재가", 0)),
                    "profit_loss_rate": float(row.get("수익률%", 0.0))
                })
        elif isinstance(result_pos, list):
            for stock in result_pos:
                if isinstance(stock, dict):
                    positions.append({
                        "stock_name": stock.get("종목명", "N/A").strip(), # 공백 제거
                        "current_price": int(stock.get("현재가", 0)),
                        "profit_loss_rate": float(stock.get("수익률%", 0.0))
                    })
                else:
                    logger.warning(f"opw00018 결과: 예상치 못한 종목 데이터 타입 - {type(stock)}. 스킵합니다.")
        else:
            logger.info("opw00018 결과: 보유 종목이 없거나 예상치 못한 빈 데이터입니다.")
            # 종목이 없을 때는 정상적인 상황이므로 오류로 처리하지 않음

        # 최종 응답 데이터 구성
        response = {
            "trade_status": trade_status,
            "total_buy_amount": int(account_data.get("총매입금액", 0)),
            "total_eval_amount": int(account_data.get("총평가금액", 0)),
            "total_profit_loss": int(account_data.get("총평가손익금액", 0)),
            "total_profit_loss_rate": float(account_data.get("총수익률", 0.0)),
            "positions": positions
        }
        logger.info(f"[/status] 응답 데이터 전송: {response}")
        return jsonify(response)

    except Exception as e:
        logger.error(f"[/status] 처리 중 예상치 못한 오류 발생: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": f"API 서버 내부 오류 발생: {e}"}), 500

# --- /trade 라우트 (on/off 제어) ---
@app.route('/trade', methods=['POST'])
def toggle_trade():
    global connected, trade_status

    if not connected:
        logger.warning("/trade 요청: Kiwoom API가 연결되지 않았습니다.")
        return jsonify({"status": "error", "message": "키움 API가 연결되지 않았습니다. 매매 상태를 변경할 수 없습니다."}), 503

    data = request.get_json()
    if data and 'status' in data:
        new_status = data['status']
        if new_status in ['start', 'stop']:
            trade_status = new_status
            message = f"매매 스위치를 '{trade_status}'로 변경했습니다."
            logger.info(f"[/trade] 매매 상태 변경됨: {trade_status}")
            return jsonify({"status": "success", "message": message})
        else:
            logger.warning(f"[/trade] 유효하지 않은 상태 값 수신: {new_status}")
            return jsonify({"status": "error", "message": "유효하지 않은 상태 값입니다. 'start' 또는 'stop'이어야 합니다."}), 400
    logger.warning("/trade 요청: 'status' 필드가 없습니다.")
    return jsonify({"status": "error", "message": "요청 본문에 'status' 필드가 필요합니다."}), 400

# --- 앱 실행 ---
if __name__ == "__main__":
    initialize_kiwoom_api() # Flask 앱 시작 전에 키움 API 연결 시도

    port = int(os.environ.get("PORT", 5000))
    logger.info(f"✅ Local API Server 실행 중... 포트: {port}")
    # debug=True는 개발 환경에서만 사용하고, 실제 운영 환경에서는 False로 설정하는 것이 좋습니다.
    # production 환경에서는 gunicorn과 같은 WSGI 서버를 사용해야 합니다.
    app.run(host="0.0.0.0", port=port, debug=True)