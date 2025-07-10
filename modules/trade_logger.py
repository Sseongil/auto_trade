# modules/trade_logger.py

import os
import csv
import logging
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

LOG_DIR = "logs"
TRADE_LOG_FILE = os.path.join(LOG_DIR, "trade_log.csv")

class TradeLogger:
    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.lock = threading.Lock()

        if not os.path.exists(TRADE_LOG_FILE) or os.stat(TRADE_LOG_FILE).st_size == 0:
            with self.lock:
                with open(TRADE_LOG_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "timestamp", "stock_code", "stock_name", "trade_type",
                        "quantity", "price", "order_no", "result", "message"
                    ])
            logger.info(f"✅ 거래 로그 파일 생성됨: {TRADE_LOG_FILE}")
        else:
            logger.info(f"✅ 기존 거래 로그 파일 사용: {TRADE_LOG_FILE}")

    def log_trade(self, stock_code, stock_name, trade_type, quantity, price, order_no, result, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = [timestamp, stock_code, stock_name, trade_type, quantity, price, order_no, result, message]
        with self.lock:
            try:
                with open(TRADE_LOG_FILE, 'a', newline='', encoding='utf-8-sig') as f:
                    csv.writer(f).writerow(log_entry)
            except Exception as e:
                logger.error(f"❌ 거래 로그 기록 실패: {e}")

    def get_trade_log(self):
        logs = []
        with self.lock:
            try:
                with open(TRADE_LOG_FILE, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    logs = list(reader)
            except Exception as e:
                logger.error(f"❌ 거래 로그 읽기 실패: {e}")
        return logs

    def clear_trade_log(self):
        with self.lock:
            try:
                with open(TRADE_LOG_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                    csv.writer(f).writerow([
                        "timestamp", "stock_code", "stock_name", "trade_type",
                        "quantity", "price", "order_no", "result", "message"
                    ])
                logger.info("🗑️ 거래 로그 초기화 완료")
                return True
            except Exception as e:
                logger.error(f"❌ 거래 로그 초기화 실패: {e}")
                return False
