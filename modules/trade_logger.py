# modules/trade_logger.py

import os
import sqlite3
import logging
from datetime import datetime

# common 모듈의 config와 utils를 임포트 (경로 주의)
from modules.common.config import LOG_DB_PATH
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class TradeLogger:
    def __init__(self, db_path=LOG_DB_PATH):
        self.db_path = db_path
        self._ensure_db_directory_exists()
        self._create_table()
        logger.info(f"{get_current_time_str()}: TradeLogger initialized. DB Path: {self.db_path}")

    def _ensure_db_directory_exists(self):
        """DB 파일이 저장될 디렉토리가 존재하는지 확인하고 없으면 생성합니다."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"Created directory for DB: {db_dir}")

    def _get_db_connection(self):
        """SQLite 데이터베이스 연결을 반환합니다."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # 결과를 딕셔너리처럼 접근할 수 있도록 설정
        return conn

    def _create_table(self):
        """매매 로그를 저장할 테이블을 생성합니다 (테이블이 없으면)."""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT,
                    trade_type TEXT NOT NULL,
                    order_price REAL,
                    executed_price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    pnl_amount REAL,
                    pnl_pct REAL,
                    account_balance_after_trade REAL,
                    strategy_name TEXT
                )
            """)
            conn.commit()
            conn.close()
            logger.info("Trade_logs table checked/created successfully.")
        except Exception as e:
            logger.error(f"Error creating trade_logs table: {e}", exc_info=True)

    def log_trade(self, stock_code, stock_name, trade_type, order_price, executed_price, quantity, 
                  pnl_amount=None, pnl_pct=None, account_balance_after_trade=None, strategy_name=None):
        """
        매매 내역을 데이터베이스에 기록합니다.

        Args:
            stock_code (str): 종목 코드
            stock_name (str): 종목명
            trade_type (str): 매매 유형 (예: "매수", "매도", "손절", "익절")
            order_price (float): 주문 가격 (지정가), 시장가면 0 또는 None
            executed_price (float): 실제 체결 가격
            quantity (int): 거래 수량
            pnl_amount (float, optional): 해당 거래로 발생한 손익 금액. Defaults to None.
            pnl_pct (float, optional): 해당 거래로 발생한 손익률. Defaults to None.
            account_balance_after_trade (float, optional): 거래 후 계좌 잔고. Defaults to None.
            strategy_name (str, optional): 해당 매매를 발생시킨 전략 이름. Defaults to None.
        """
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO trade_logs (
                    timestamp, stock_code, stock_name, trade_type, order_price, 
                    executed_price, quantity, pnl_amount, pnl_pct, 
                    account_balance_after_trade, strategy_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp, stock_code, stock_name, trade_type, order_price, 
                executed_price, quantity, pnl_amount, pnl_pct, 
                account_balance_after_trade, strategy_name
            ))
            conn.commit()
            conn.close()
            logger.info(f"Trade logged: {trade_type} {stock_name}({stock_code}) Qty:{quantity} Price:{executed_price}")
        except Exception as e:
            logger.error(f"Error logging trade for {stock_name}({stock_code}): {e}", exc_info=True)

    def get_all_trades(self):
        """데이터베이스에 기록된 모든 매매 내역을 조회하여 반환합니다."""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trade_logs ORDER BY timestamp ASC")
            trades = cursor.fetchall()
            conn.close()
            # SQLite.Row 객체를 딕셔너리 리스트로 변환하여 반환
            return [dict(row) for row in trades]
        except Exception as e:
            logger.error(f"Error retrieving all trades: {e}", exc_info=True)
            return []

    def get_trades_by_date_range(self, start_date, end_date):
        """특정 기간 내의 매매 내역을 조회하여 반환합니다. (YYYY-MM-DD 형식)"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trade_logs 
                WHERE timestamp BETWEEN ? AND ? 
                ORDER BY timestamp ASC
            """, (f"{start_date} 00:00:00", f"{end_date} 23:59:59"))
            trades = cursor.fetchall()
            conn.close()
            return [dict(row) for row in trades]
        except Exception as e:
            logger.error(f"Error retrieving trades by date range: {e}", exc_info=True)
            return []

    def get_trades_by_stock_code(self, stock_code):
        """특정 종목 코드의 매매 내역을 조회하여 반환합니다."""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trade_logs 
                WHERE stock_code = ? 
                ORDER BY timestamp ASC
            """, (stock_code,))
            trades = cursor.fetchall()
            conn.close()
            return [dict(row) for row in trades]
        except Exception as e:
            logger.error(f"Error retrieving trades by stock code {stock_code}: {e}", exc_info=True)
            return []