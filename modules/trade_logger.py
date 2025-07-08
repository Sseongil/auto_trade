# modules/trade_logger.py

import os
import csv
import logging
from datetime import datetime
import threading

# 로깅 설정
logger = logging.getLogger(__name__)

# 로그 파일 경로
LOG_DIR = "logs"
TRADE_LOG_FILE = os.path.join(LOG_DIR, "trade_log.csv")

class TradeLogger:
    def __init__(self):
        # 로그 디렉토리 생성 (없으면)
        os.makedirs(LOG_DIR, exist_ok=True)
        self.lock = threading.Lock() # 파일 접근 시 동시성 문제 방지를 위한 락

        # 파일이 없거나 비어있으면 헤더를 작성
        if not os.path.exists(TRADE_LOG_FILE) or os.stat(TRADE_LOG_FILE).st_size == 0:
            with self.lock:
                with open(TRADE_LOG_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "timestamp", "stock_code", "stock_name", "trade_type",
                        "quantity", "price", "order_no", "result", "message"
                    ])
                logger.info(f"✅ 거래 로그 파일 '{TRADE_LOG_FILE}'이(가) 생성되었습니다. (헤더 포함)")
        else:
            logger.info(f"✅ 기존 거래 로그 파일 '{TRADE_LOG_FILE}'을(를) 사용합니다.")

    def log_trade(self, stock_code, stock_name, trade_type, quantity, price, order_no, result, message):
        """
        거래 내역을 CSV 파일에 기록합니다.
        :param stock_code: 종목 코드
        :param stock_name: 종목명
        :param trade_type: 거래 유형 (예: "매수", "매도")
        :param quantity: 수량
        :param price: 가격
        :param order_no: 주문 번호
        :param result: 거래 결과 (예: "성공", "실패", "부분체결")
        :param message: 상세 메시지
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = [timestamp, stock_code, stock_name, trade_type, quantity, price, order_no, result, message]

        with self.lock:
            try:
                with open(TRADE_LOG_FILE, 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(log_entry)
                logger.debug(f"거래 로그 기록: {log_entry}")
            except Exception as e:
                logger.error(f"❌ 거래 로그 파일 쓰기 실패: {e}", exc_info=True)

    def get_trade_log(self):
        """
        CSV 파일에서 모든 거래 로그를 읽어 리스트 형태로 반환합니다.
        """
        logs = []
        with self.lock:
            if not os.path.exists(TRADE_LOG_FILE) or os.stat(TRADE_LOG_FILE).st_size == 0:
                logger.info(f"ℹ️ 거래 로그 파일 '{TRADE_LOG_FILE}'이(가) 없거나 비어 있습니다.")
                return []
            
            try:
                with open(TRADE_LOG_FILE, 'r', newline='', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    # DictReader는 첫 줄을 헤더로 자동 인식합니다.
                    # 헤더가 없거나 잘못된 경우 여기서 오류가 발생할 수 있으므로,
                    # 파일 초기화 시 헤더를 강제 작성하여 문제를 방지합니다.
                    for row in reader:
                        logs.append(row)
                logger.debug(f"거래 로그 {len(logs)}개 로드 완료.")
            except Exception as e:
                logger.error(f"❌ 거래 로그 파일 읽기 실패: {e}", exc_info=True)
                # 파일이 손상되었을 가능성이 있으므로 빈 리스트 반환
                return []
        return logs

    def clear_trade_log(self):
        """
        모든 거래 로그를 삭제합니다. (파일 내용 비우기)
        """
        with self.lock:
            if os.path.exists(TRADE_LOG_FILE):
                try:
                    with open(TRADE_LOG_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                        # 헤더만 다시 작성하여 파일 내용을 비움
                        writer = csv.writer(f)
                        writer.writerow([
                            "timestamp", "stock_code", "stock_name", "trade_type",
                            "quantity", "price", "order_no", "result", "message"
                        ])
                    logger.info(f"🗑️ 거래 로그 파일 '{TRADE_LOG_FILE}'의 내용이 삭제되었습니다.")
                    return True
                except Exception as e:
                    logger.error(f"❌ 거래 로그 파일 삭제 실패: {e}", exc_info=True)
                    return False
            else:
                logger.info(f"ℹ️ 삭제할 거래 로그 파일 '{TRADE_LOG_FILE}'이(가) 존재하지 않습니다.")
                return False

