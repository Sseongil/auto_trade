# modules/auto_trade.py (FINAL UPDATED VERSION)

import os
import sys
import json
import pandas as pd
from datetime import datetime, time # time 모듈 import
import logging
import time as time_module # 주문 간 딜레이를 위한 time 모듈

# 프로젝트 루트 경로를 sys.path에 추가 (다른 모듈 임포트를 위해)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 필요한 모듈 임포트
from pykiwoom.kiwoom import Kiwoom
from modules.position_manager import add_position_to_csv as add_position
from modules.notify import send_telegram_message
from modules.trade_logger import log_trade # <-- 이 모듈의 함수 호출 방식을 변경할 예정
from modules.config import calculate_quantity, STATUS_FILE_PATH, BUY_LIST_DIR_PATH # config.py에서 경로 가져오기

# 로깅 설정 (auto_trade.py 자체의 로깅)
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Kiwoom API 에러 코드 정의 (monitor_positions.py와 동일하게) ---
KIWOOM_ERROR_CODES = {
    0: "정상 처리",
    -10: "미접속",
    -100: "계좌정보 없음",
    -101: "계좌 비밀번호 없음",
    -102: "비정상적인 모듈 호출",
    -103: "종목코드 없음",
    -104: "계좌증거금율 오류",
    -105: "조건 검색 오류",
    -106: "조건 검색 미신청",
    -107: "사용자 정보 없음",
    -108: "주문 가격 오류",
    -109: "주문 수량 오류",
    -110: "실시간 등록 오류",
    -111: "실시간 해제 오류",
    -112: "데이터 없음",
    -113: "API 미설정",
    -114: "알 수 없는 오류",
}

def should_trade() -> bool:
    """
    status.json 파일을 읽어 자동매매 시작/중지 상태를 확인합니다.
    """
    try:
        if not os.path.exists(STATUS_FILE_PATH):
            logger.warning(f"⚠️ {STATUS_FILE_PATH} 파일을 찾을 수 없습니다. 기본값 'stop'으로 처리합니다.")
            return False # 파일 없으면 기본적으로 중지

        with open(STATUS_FILE_PATH, "r", encoding="utf-8") as f:
            status_data = json.load(f)
            status = status_data.get("status", "stop") # 'status' 키 없으면 기본값 'stop'
            return status == "start"
    except json.JSONDecodeError as e:
        logger.error(f"❌ {STATUS_FILE_PATH} 파일 형식 오류: {e}", exc_info=True)
        send_telegram_message(f"❌ status.json 읽기 오류 (형식): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ {STATUS_FILE_PATH} 읽기 중 예외 발생: {e}", exc_info=True)
        send_telegram_message(f"❌ status.json 읽기 오류 (일반): {e}")
        return False


def run_auto_trade():
    """
    buy_list.csv에 있는 종목들을 확인하고 자동 매수 주문을 실행합니다.
    """
    logger.info("🚀 자동매매 (매수) 프로세스 시작")

    # 1. 텔레그램 스위치 상태 확인
    if not should_trade():
        logger.info("🛑 텔레그램 스위치 상태가 'start'가 아니므로 자동매매 (매수)를 건너뜜.")
        return
    else:
        logger.info("✅ 텔레그램 스위치 상태 'start' 확인. 자동매매 (매수) 진행.")

    # 2. 키움증권 API 연결
    kiwoom = Kiwoom()
    try:
        kiwoom.CommConnect(block=True)
        if not kiwoom.connected:
            logger.critical("❌ 키움증권 API 연결 실패. 자동매매를 중단합니다.")
            send_telegram_message("🚨 키움 API 연결 실패. 자동매매 (매수) 중단.")
            return
        logger.info("✅ 키움증권 API 연결 성공.")
    except Exception as e:
        logger.critical(f"❌ 키움 연결 중 치명적인 오류 발생: {e}", exc_info=True)
        send_telegram_message(f"🚨 키움 연결 오류: {e}")
        return

    # 3. 계좌 정보 확인
    accounts = kiwoom.GetLoginInfo("ACCNO")
    if not accounts:
        logger.error("❌ 키움증권 계좌 정보를 가져올 수 없습니다.")
        send_telegram_message("❌ 계좌 정보 없음. 자동매매 중단.")
        kiwoom.Disconnect()
        return
    account = accounts[0].strip()
    logger.info(f"💰 로그인 계좌: {account}")

    # 4. buy_list.csv 파일 경로 설정 및 확인
    today = datetime.today().strftime("%Y%m%d")
    buy_list_dir = os.path.join(BUY_LIST_DIR_PATH, today) # config.py에서 경로 가져오기
    buy_list_path = os.path.join(buy_list_dir, "buy_list.csv")

    if not os.path.exists(buy_list_path):
        logger.info(f"📂 매수 리스트 파일 없음: '{buy_list_path}'. 매수할 종목이 없습니다.")
        return

    # 5. buy_list.csv 로드
    df_buy_list = pd.DataFrame() # 빈 DataFrame으로 초기화
    try:
        df_buy_list = pd.read_csv(buy_list_path, encoding="utf-8-sig")
        df_buy_list['ticker'] = df_buy_list['ticker'].apply(lambda x: str(x).zfill(6)) # 종목코드 6자리로 통일
    except pd.errors.EmptyDataError:
        logger.info(f"📂 매수 리스트 파일이 비어 있습니다: '{buy_list_path}'")
        send_telegram_message(f"📭 매수 종목 없음. ({buy_list_path} 비어있음)")
        kiwoom.Disconnect()
        return
    except Exception as e:
        logger.error(f"❌ 매수 리스트 파일 로딩 중 오류 발생: {e}", exc_info=True)
        send_telegram_message(f"🚨 매수 리스트 로딩 오류: {e}")
        kiwoom.Disconnect()
        return

    if df_buy_list.empty:
        logger.info("📭 매수 리스트에 매수할 종목이 없습니다.")
        send_telegram_message("📭 매수 종목 없음")
        kiwoom.Disconnect()
        return

    logger.info(f"📋 매수 대상 {len(df_buy_list)}개 로드 완료.")
    print(f"📋 매수 대상:\n{df_buy_list[['ticker', 'name']]}")


    # 6. 예수금 조회
    balance = 0
    try:
        # KiwoomQueryHelper를 사용하지 않고 직접 요청 (여기서만 사용되므로)
        deposit_data = kiwoom.block_request(
            "opw00001",
            계좌번호=account,
            비밀번호="0000", # TODO: config/환경 변수에서 불러오도록 전환 (KIWOOM_ACCOUNT_PASSWORD)
            비밀번호입력매체구분="00",
            조회구분=2,
            output="예수금상세현황",
            next=0
        )
        if deposit_data is None or deposit_data.empty:
            logger.warning("⚠️ 예수금 상세 현황 데이터 없음.")
            send_telegram_message("❌ 예수금 조회 실패: 데이터 없음.")
            kiwoom.Disconnect()
            return

        balance_str = str(deposit_data['예수금'].iloc[0]).replace(",", "").strip()
        balance = int(balance_str) if balance_str.isdigit() else 0
        logger.info(f"💰 현재 예수금: {balance:,}원")
    except Exception as e:
        logger.error(f"❌ 예수금 조회 실패: {e}", exc_info=True)
        send_telegram_message(f"❌ 예수금 조회 실패: {e}")
        kiwoom.Disconnect()
        return

    # 7. 매수할 종목 순회 및 주문 전송
    successful_buys_tickers = [] # 성공적으로 매수한 종목의 티커를 저장
    for index, row in df_buy_list.iterrows():
        code = str(row["ticker"]).zfill(6)
        name = row["name"]

        logger.info(f"\n📈 매수 시도 중: {name}({code})")

        # 장 운영 시간 확인 (오전 9시부터 오후 3시 20분까지만 주문)
        now_time = datetime.now().time()
        if not (time(9, 0) <= now_time <= time(15, 20)):
            logger.warning(f"⏰ 현재 시간 {now_time}은 장 운영 시간이 아니므로 {name}({code}) 매수를 건너뜀.")
            send_telegram_message(f"⏰ 장 시간 아님. {name}({code}) 매수 스킵.")
            continue # 다음 종목으로 넘어감

        # 종목의 현재가 조회
        current_price = 0
        try:
            price_data = kiwoom.block_request("opt10001", 종목코드=code, output="주식기본정보", next=0)
            price_str = str(price_data.get("현재가", "0")).replace(",", "").replace("+", "").replace("-", "").strip()
            current_price = int(price_str) if price_str.isdigit() else 0
            if current_price <= 0:
                raise ValueError("현재가 조회 실패 또는 0 이하")
            logger.info(f"{name}({code}) 현재가: {current_price:,}원")
        except Exception as e:
            logger.error(f"❌ 현재가 조회 실패: {name}({code}) - {e}", exc_info=True)
            send_telegram_message(f"❌ 현재가 조회 실패: {name}({code}) - {e}")
            continue # 다음 종목으로 넘어감

        # 매수 가능 수량 계산
        quantity = calculate_quantity(current_price, balance)
        if quantity <= 0:
            logger.warning(f"🚫 매수 불가 (수량 0 또는 예수금 부족): {name}({code})")
            send_telegram_message(f"🚫 매수 불가 (수량 0): {name}({code})")
            continue # 다음 종목으로 넘어감

        # Kiwoom 매수 주문 전송 (시장가 매수: "03")
        # 주문 유형: 1 (신규매수)
        # 가격: 0 (시장가)
        order_type = 1 # 신규매수
        price_type = "03" # 시장가
        order_result = kiwoom.SendOrder("자동매수", "0101", account, order_type, code, quantity, 0, price_type, "") # 0 for market price

        if order_result == 0: # 주문 성공
            logger.info(f"✅ 매수 주문 성공: {name}({code}) {current_price:,}원 x {quantity}주")
            send_telegram_message(f"✅ 매수 성공: {name}({code})\n💰 {current_price:,}원 x {quantity}주")

            # --- 통합된 로직 ---
            # 1. trade_logger.py를 사용하여 매매 로그 기록 (새로운 형식으로)
            log_trade(code, name, current_price, quantity, "BUY", None) # 매수 시 pnl은 None

            # 2. trade_manager.py를 사용하여 positions.csv에 포지션 추가
            add_position(code, name, current_price, quantity) # 매수 가격을 buy_price로 사용

            successful_buys_tickers.append(code) # 성공한 매수 종목 기록
            time_module.sleep(2) # 주문 전송 간 딜레이 (과도한 요청 방지)
        else: # 주문 실패
            error_msg = KIWOOM_ERROR_CODES.get(order_result, "알 수 없는 오류")
            logger.error(f"🔴 매수 주문 실패: {name}({code}), 응답코드: {order_result} ({error_msg})")
            send_telegram_message(f"🔴 매수 실패: {name}({code}) | 코드: {order_result} ({error_msg})")
            time_module.sleep(2) # 실패 시에도 딜레이

    # 8. 성공적으로 매수한 종목은 buy_list.csv에서 제거
    if successful_buys_tickers:
        df_remaining_buy_list = df_buy_list[~df_buy_list['ticker'].isin(successful_buys_tickers)]
        
        # 원본 buy_list_dir이 존재하지 않으면 생성
        if not os.path.exists(buy_list_dir):
            os.makedirs(buy_list_dir)

        df_remaining_buy_list.to_csv(buy_list_path, index=False, encoding="utf-8-sig")
        logger.info(f"🗑️ 매수 완료된 종목 {len(successful_buys_tickers)}개 buy_list.csv에서 제거.")
        if df_remaining_buy_list.empty:
            send_telegram_message("✅ 모든 매수 리스트 처리 완료.")
    else:
        logger.info("ℹ️ 이번 주기에는 성공적인 매수 주문이 없었습니다.")
        send_telegram_message("ℹ️ 이번 매수 주기에는 매수된 종목이 없습니다.")


    # 9. 키움증권 API 연결 해제
    try:
        kiwoom.Disconnect()
        logger.info("🔌 키움증권 API 연결 해제 완료.")
    except Exception as e:
        logger.error(f"❌ 키움 API 연결 해제 중 오류 발생: {e}", exc_info=True)

    logger.info("--- 자동매매 (매수) 프로세스 종료 ---")


if __name__ == "__main__":
    run_auto_trade()