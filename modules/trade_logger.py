# modules/trade_logger.py

import sqlite3
import os
import logging
from datetime import datetime

# 💡 LOG_DB_PATH 대신 TRADE_LOG_DB_PATH 임포트
from modules.common.config import TRADE_LOG_DB_PATH 
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class TradeLogger:
    def __init__(self):
        self.db_path = TRADE_LOG_DB_PATH
        self._ensure_db_and_table()
        logger.info(f"{get_current_time_str()}: TradeLogger initialized. DB Path: {self.db_path}")

    def _ensure_db_and_table(self):
        """데이터베이스 파일과 trade_logs 테이블이 존재하는지 확인하고 없으면 생성합니다."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT NOT NULL,
                    trade_type TEXT NOT NULL,
                    order_price REAL,
                    executed_price REAL,
                    quantity INTEGER NOT NULL,
                    pnl_amount REAL,
                    pnl_pct REAL,
                    account_balance_after_trade REAL,
                    strategy_name TEXT
                )
            """)
            conn.commit()
            logger.info("Trade_logs table checked/created successfully.")
        except sqlite3.Error as e:
            logger.error(f"Error ensuring DB and table: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()

    def log_trade(self, stock_code, stock_name, trade_type, order_price, executed_price, 
                  quantity, pnl_amount, pnl_pct, account_balance_after_trade, strategy_name="N/A"):
        """
        거래 내역을 데이터베이스에 기록합니다.
        
        Args:
            stock_code (str): 종목 코드
            stock_name (str): 종목명
            trade_type (str): 거래 유형 ('매수', '매도', '익절', '손절', '보유종료')
            order_price (float): 주문 가격
            executed_price (float): 체결 가격
            quantity (int): 거래 수량
            pnl_amount (float): 손익 금액 (매도 시에만 유효)
            pnl_pct (float): 손익률 (%) (매도 시에만 유효)
            account_balance_after_trade (float): 거래 후 계좌 예수금 (또는 총자산)
            strategy_name (str): 사용된 전략명 (기본값 "N/A")
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO trade_logs (timestamp, stock_code, stock_name, trade_type, 
                                        order_price, executed_price, quantity, 
                                        pnl_amount, pnl_pct, account_balance_after_trade, strategy_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, stock_code, stock_name, trade_type, 
                  order_price, executed_price, quantity, 
                  pnl_amount, pnl_pct, account_balance_after_trade, strategy_name))
            conn.commit()
            logger.info(f"📊 Trade logged: [{trade_type}] {stock_name}({stock_code}), Qty: {quantity}, Price: {executed_price}")
        except sqlite3.Error as e:
            logger.error(f"Error logging trade: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()

    def get_trades(self, limit=100):
        """최근 거래 내역을 조회합니다."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trade_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error fetching trades: {e}", exc_info=True)
            return []
        finally:
            if conn:
                conn.close()

    def get_daily_summary(self, date_str=None):
        """특정 날짜의 매매 요약을 반환합니다 (YYYY-MM-DD 형식)."""
        if date_str is None:
            date_str = datetime.today().strftime("%Y-%m-%d")

        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 총 거래 횟수
            cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE DATE(timestamp) = ?", (date_str,))
            total_trades = cursor.fetchone()[0]

            # 총 손익 금액 및 수익률
            cursor.execute("SELECT SUM(pnl_amount), AVG(pnl_pct) FROM trade_logs WHERE DATE(timestamp) = ? AND (trade_type = '매도' OR trade_type = '익절' OR trade_type = '손절' OR trade_type = '보유종료')", (date_str,))
            total_pnl_amount, avg_pnl_pct = cursor.fetchone()
            total_pnl_amount = total_pnl_amount if total_pnl_amount is not None else 0.0
            avg_pnl_pct = avg_pnl_pct if avg_pnl_pct is not None else 0.0

            # 승리/패배 횟수
            cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE DATE(timestamp) = ? AND (trade_type = '매도' OR trade_type = '익절' OR trade_type = '손절' OR trade_type = '보유종료') AND pnl_amount > 0", (date_str,))
            win_trades = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM trade_logs WHERE DATE(timestamp) = ? AND (trade_type = '매도' OR trade_type = '익절' OR trade_type = '손절' OR trade_type = '보유종료') AND pnl_amount <= 0", (date_str,))
            loss_trades = cursor.fetchone()[0]

            win_rate = (win_trades / (win_trades + loss_trades)) * 100 if (win_trades + loss_trades) > 0 else 0.0

            return {
                "date": date_str,
                "total_trades": total_trades,
                "total_pnl_amount": total_pnl_amount,
                "avg_pnl_pct": avg_pnl_pct,
                "win_trades": win_trades,
                "loss_trades": loss_trades,
                "win_rate": win_rate
            }

        except sqlite3.Error as e:
            logger.error(f"Error fetching daily summary for {date_str}: {e}", exc_info=True)
            return None
        finally:
            if conn:
                conn.close()

