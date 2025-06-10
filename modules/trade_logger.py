# modules/trade_logger.py (UPDATED FULL CODE)

import csv
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
if not logger.handlers: # Avoid re-adding handlers if basicConfig is called elsewhere
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def log_trade(code: str, name: str, price: int, quantity: int, trade_type: str, pnl: float = None):
    """
    매매 내역을 trade_log.csv 파일에 기록합니다.

    Args:
        code (str): 종목 코드.
        name (str): 종목명.
        price (int): 체결 가격.
        quantity (int): 체결 수량.
        trade_type (str): 매매 유형 (예: "BUY", "SELL", "STOP_LOSS", "TAKE_PROFIT", "TRAILING_STOP", "MAX_HOLD_DAYS_SELL").
        pnl (float, optional): 수익률 (퍼센트). 매수 시에는 None으로 전달.
    """
    log_path = "trade_log.csv" # trade_log.csv 파일은 프로젝트 루트에 생성됩니다.
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 수익률 정보는 매도 시에만 유효. 매수 시에는 'None'이 전달되므로 '-'로 표시
    pnl_str = f"{pnl:.2f}%" if pnl is not None else "-"

    # 로그에 기록할 데이터 행
    row = [now, code, name, price, quantity, trade_type, pnl_str]

    # 파일이 존재하지 않으면 헤더를 먼저 작성
    write_header = not os.path.exists(log_path)

    try:
        with open(log_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["시간", "종목코드", "종목명", "체결가", "수량", "매매유형", "수익률"])
            writer.writerow(row)
        logger.info(f"📝 매매 로그 저장 완료: {name}({code}) | 유형: {trade_type} | 가격: {price:,}원 | 수량: {quantity}주 | 수익률: {pnl_str}")
    except Exception as e:
        logger.error(f"❌ 매매 로그 저장 중 오류 발생: {e}", exc_info=True)

# 테스트 코드 (모듈 단독 실행 시)
if __name__ == "__main__":
    # 단독 실행 시 로깅 설정을 다시 확인
    # logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    # logger = logging.getLogger(__name__) # __name__으로 logger를 다시 가져옴

    # 매수 로그 예시
    log_trade("005930", "삼성전자", 75000, 10, "BUY")
    log_trade("035420", "네이버", 180000, 5, "BUY")
    
    # 매도 로그 예시 (수익률 포함)
    log_trade("005930", "삼성전자", 70000, 10, "STOP_LOSS", -5.0)
    log_trade("035420", "네이버", 200000, 3, "TAKE_PROFIT", 11.11)
    log_trade("035420", "네이버", 190000, 2, "TRAILING_STOP", 5.55)
    log_trade("000660", "SK하이닉스", 100000, 0, "수량0제거") # 수량 0으로 제거되는 경우