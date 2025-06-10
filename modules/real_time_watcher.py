# modules/real_time_watcher.py

import os
import sys
import pandas as pd
from datetime import datetime, time
import logging
import time as time_module

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pykiwoom.kiwoom import Kiwoom
from modules.config import POSITIONS_FILE_PATH
from modules.notify import send_telegram_message
from modules.trade_logger import log_trade

# 로깅 설정
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 전역 등록 종목 관리용 Set
registered_realtime_codes = set()

# --- 포지션 로드 ---
def load_positions_for_watching(file_path: str) -> pd.DataFrame:
    cols = {"ticker": str, "name": str}
    if not os.path.exists(file_path):
        logger.info(f"📂 포지션 파일 없음: '{file_path}'")
        return pd.DataFrame(columns=list(cols.keys()))
    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        for col in cols:
            if col not in df.columns:
                df[col] = ""
                logger.warning(f"⚠️ 누락된 컬럼 '{col}'이 포지션 파일에 추가됨")
        return df[list(cols.keys())]
    except pd.errors.EmptyDataError:
        logger.warning(f"⚠️ 포지션 파일이 비어 있습니다: '{file_path}'")
        return pd.DataFrame(columns=list(cols.keys()))
    except Exception as e:
        logger.error(f"❌ 포지션 파일 로딩 중 오류: {e}", exc_info=True)
        send_telegram_message(f"🚨 포지션 파일 로딩 중 오류 발생: {e}")
        return pd.DataFrame(columns=list(cols.keys()))

# --- 실시간 체결/잔고 콜백 ---
def make_chejan_handler(kiwoom_instance):
    def _handler(gubun: str, item_cnt: int, fid_list: str):
        try:
            if gubun == '0':  # 주문 체결
                order_no = kiwoom_instance.GetChejanData(9203)
                stock_code = kiwoom_instance.GetChejanData(9001)
                stock_name = kiwoom_instance.GetChejanData(302)
                price = kiwoom_instance.GetChejanData(910)
                qty = kiwoom_instance.GetChejanData(911)
                balance = kiwoom_instance.GetChejanData(958)

                logger.info(f"💰 체결: {stock_name}({stock_code}), {qty}주 @ {price}원")
                send_telegram_message(f"💰 체결: {stock_name}({stock_code}) - {qty}주 @ {price}원")
                log_trade(stock_code, stock_name, price, qty, "BUY" if float(qty) > 0 else "SELL")

            elif gubun == '1':  # 잔고 변경
                stock_code = kiwoom_instance.GetChejanData(9001)
                stock_name = kiwoom_instance.GetChejanData(302)
                logger.info(f"💼 잔고 변경 감지: {stock_name}({stock_code})")
        except Exception as e:
            logger.error(f"❌ 체결/잔고 데이터 처리 오류: {e}", exc_info=True)
    return _handler

# --- 실시간 데이터 수신 콜백 ---
def real_data_handler(stock_code: str, real_type: str, real_data: str):
    logger.debug(f"📈 실시간 수신: {stock_code}, {real_type}, 데이터={real_data[:60]}...")

# --- 실시간 감시 등록 ---
def start_real_time_monitoring(kiwoom: Kiwoom, df_positions: pd.DataFrame):
    global registered_realtime_codes
    if df_positions.empty:
        logger.info("🟡 감시할 종목 없음")
        return

    current_codes = set(df_positions["ticker"].apply(lambda x: str(x).zfill(6)))
    new_codes = current_codes - registered_realtime_codes

    for code in new_codes:
        row = df_positions[df_positions["ticker"].apply(lambda x: str(x).zfill(6)) == code].iloc[0]
        name = row["name"]
        try:
            kiwoom.SetRealReg("0101", code, "10;11;13;20", "0")
            registered_realtime_codes.add(code)
            logger.info(f"🟢 실시간 등록 완료: {name}({code})")
        except Exception as e:
            logger.error(f"❌ 실시간 등록 실패: {name}({code}) - {e}", exc_info=True)
            send_telegram_message(f"🚨 실시간 등록 실패: {name}({code}) - {e}")

# --- 메인 와처 ---
def run_watcher():
    logger.info("🚀 실시간 감시 와처 시작")
    kiwoom = Kiwoom()

    try:
        kiwoom.CommConnect(block=True)
        if not kiwoom.connected:
            send_telegram_message("🚨 Kiwoom 연결 실패. 와처 종료.")
            return

        logger.info("✅ Kiwoom 연결 성공")
        send_telegram_message("✅ 실시간 감시 시작됨")

        kiwoom.set_real_data_callback('default', real_data_handler)
        kiwoom.set_real_data_callback('stock_conclusion', make_chejan_handler(kiwoom))

        last_checked_minute = -1
        END_TIME = time(15, 40)

        while True:
            now = datetime.now()
            if now.minute != last_checked_minute:
                df_positions = load_positions_for_watching(POSITIONS_FILE_PATH)
                start_real_time_monitoring(kiwoom, df_positions)
                last_checked_minute = now.minute

            if now.time() >= END_TIME:
                logger.info("🕒 장 마감 도달. 와처 종료.")
                send_telegram_message("🛑 실시간 감시 종료")
                break

            time_module.sleep(5)

    except KeyboardInterrupt:
        logger.info("👋 수동 종료 감지")
        send_telegram_message("👋 실시간 감시 수동 종료")
    except Exception as e:
        logger.critical(f"🚨 예외 발생: {e}", exc_info=True)
        send_telegram_message(f"🚨 예외 발생: {e}")
    finally:
        if kiwoom.connected:
            kiwoom.Disconnect()
            logger.info("🔌 Kiwoom 연결 해제 완료")
        logger.info("📁 실시간 감시 와처 종료")

if __name__ == "__main__":
    run_watcher()
