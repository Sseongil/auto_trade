# modules/trade_logger.py

import os
import csv
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 거래 로그 파일 경로 (프로젝트 루트에 'logs' 디렉토리 생성)
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
TRADE_LOG_FILE = os.path.join(LOG_DIR, 'trade_log.csv')

# 로그 디렉토리 생성
os.makedirs(LOG_DIR, exist_ok=True)

class TradeLogger:
    def __init__(self):
        """
        TradeLogger 클래스 초기화.
        로그 파일이 없으면 헤더를 추가합니다.
        """
        self._ensure_header()

    def _ensure_header(self):
        """거래 로그 파일이 없으면 헤더를 추가합니다."""
        if not os.path.exists(TRADE_LOG_FILE) or os.stat(TRADE_LOG_FILE).st_size == 0:
            with open(TRADE_LOG_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'stock_code', 'stock_name', 'trade_type', 'quantity', 'price', 'order_no', 'message'])
            logger.info(f"거래 로그 파일 헤더 생성: {TRADE_LOG_FILE}")

    def log_trade(self, stock_code: str, stock_name: str, trade_type: str, quantity: int, price: float, order_no: str = None, message: str = ""):
        """
        거래 내역을 로그 파일에 기록합니다.

        Args:
            stock_code (str): 종목 코드
            stock_name (str): 종목명
            trade_type (str): 거래 유형 (예: 'BUY_ORDER_REQUEST', 'BUY_FILLED', 'SELL_ORDER_REQUEST', 'SELL_FILLED', 'MANUAL_NOTE')
            quantity (int): 수량
            price (float): 가격
            order_no (str, optional): 주문 번호. Defaults to None.
            message (str, optional): 추가 메시지. Defaults to "".
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(TRADE_LOG_FILE, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, stock_code, stock_name, trade_type, quantity, price, order_no, message])
            logger.info(f"거래 로그 기록: [{trade_type}] {stock_name}({stock_code}) {quantity}주 @ {price}원 (주문번호: {order_no if order_no else 'N/A'})")
        except Exception as e:
            logger.error(f"거래 로그 기록 중 오류 발생: {e}", exc_info=True)

    def get_trade_log(self, stock_code: str = None):
        """
        저장된 모든 거래 로그를 읽어와 리스트 형태로 반환합니다.
        stock_code가 제공되면 해당 종목의 로그만 필터링하여 반환합니다.
        """
        logs = []
        if not os.path.exists(TRADE_LOG_FILE):
            return logs

        try:
            with open(TRADE_LOG_FILE, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if stock_code is None or row.get('stock_code') == stock_code:
                        logs.append(row)
        except Exception as e:
            logger.error(f"거래 로그 읽기 중 오류 발생: {e}", exc_info=True)
        return logs

    def clear_trade_log(self):
        """
        모든 거래 로그를 삭제합니다. (주의: 되돌릴 수 없는 작업입니다)
        """
        try:
            if os.path.exists(TRADE_LOG_FILE):
                os.remove(TRADE_LOG_FILE)
                self._ensure_header() # 헤더 다시 생성
                logger.warning(f"모든 거래 로그가 삭제되었습니다: {TRADE_LOG_FILE}")
                return True
            else:
                logger.info("삭제할 거래 로그 파일이 없습니다.")
                return False
        except Exception as e:
            logger.error(f"거래 로그 삭제 중 오류 발생: {e}", exc_info=True)
            return False

