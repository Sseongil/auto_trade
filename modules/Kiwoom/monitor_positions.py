# modules/Kiwoom/monitor_positions.py

import os
import json
import logging
from datetime import datetime
import threading
from modules.common.config import POSITIONS_FILE_PATH
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class MonitorPositions:
    def __init__(self, kiwoom_helper, kiwoom_tr_request, trade_manager_instance, account_number):
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.trade_manager = trade_manager_instance
        self.account_number = account_number
        self.position_lock = threading.Lock()
        self.positions = self.load_positions()
        logger.info(f"{get_current_time_str()}: MonitorPositions initialized for account {self.account_number}. Loaded {len(self.positions)} positions.")

    def set_trade_manager(self, trade_manager_instance):
        self.trade_manager = trade_manager_instance
        logger.info("TradeManager instance set in MonitorPositions.")

    def load_positions(self):
        with self.position_lock:
            if os.path.exists(POSITIONS_FILE_PATH):
                with open(POSITIONS_FILE_PATH, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        for pos_key, pos_data in data.items():
                            # 'buy_time' 필드 호환성 처리: 없으면 현재 시간으로 채움
                            if 'buy_time' not in pos_data or not pos_data['buy_time']:
                                pos_data['buy_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                logger.warning(f"⚠️ {pos_key} 포지션에 'buy_time' 없음. 현재 시간으로 설정.")
                            # 'trail_high' 필드 호환성 처리: 없으면 purchase_price로 초기화
                            if 'trail_high' not in pos_data or not pos_data['trail_high']:
                                pos_data['trail_high'] = pos_data.get('purchase_price', 0.0)
                                logger.warning(f"⚠️ {pos_key} 포지션에 'trail_high' 없음. purchase_price로 설정.")
                            # 'name' 필드 호환성 처리: 없으면 종목명 조회 시도
                            if 'name' not in pos_data or not pos_data['name']:
                                stock_name = self.kiwoom_helper.get_stock_name(pos_key)
                                pos_data['name'] = stock_name
                                logger.warning(f"⚠️ {pos_key} 포지션에 'name' 없음. '{stock_name}'으로 설정.")
                        return data
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ 포지션 파일 로드 실패 (JSON 오류): {e}")
                        return {}
            return {}

    def save_positions(self):
        with self.position_lock:
            try:
                os.makedirs(os.path.dirname(POSITIONS_FILE_PATH), exist_ok=True)
                with open(POSITIONS_FILE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(self.positions, f, indent=4, ensure_ascii=False)
                logger.debug(f"✅ 포지션 저장 완료: {len(self.positions)}개")
            except Exception as e:
                logger.error(f"❌ 포지션 저장 실패: {e}", exc_info=True)

    def update_position(self, stock_code, new_quantity, new_purchase_price=None, new_buy_time=None):
        """
        포지션 정보를 업데이트하거나 새로 추가합니다.
        매수/매도 체결 시 호출됩니다.
        """
        with self.position_lock:
            stock_name = self.kiwoom_helper.get_stock_name(stock_code)
            current_qty = self.positions.get(stock_code, {}).get("quantity", 0)

            if new_quantity > current_qty: # 매수 또는 추가 매수
                # 기존에 없던 종목이거나, 수량이 증가했을 때 매입가와 매수일시를 업데이트
                # (평균 단가 계산 로직은 더 복잡하므로 여기서는 단순화)
                if stock_code not in self.positions:
                    self.positions[stock_code] = {
                        "stock_code": stock_code,
                        "quantity": new_quantity,
                        "purchase_price": new_purchase_price if new_purchase_price else 0.0,
                        "total_purchase_amount": new_purchase_price * new_quantity if new_purchase_price else 0.0,
                        "buy_date": datetime.today().strftime("%Y-%m-%d"),
                        "buy_time": new_buy_time if new_buy_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "half_exited": False,
                        "trail_high": new_purchase_price if new_purchase_price else 0.0, # 매수 시 trail_high는 매입가로 초기화
                        "name": stock_name
                    }
                    logger.info(f"New position: {stock_name}({stock_code}) x{new_quantity}")
                else:
                    # 기존 포지션에 추가 매수 시 평균단가 및 총 매수금액 업데이트 (간단화된 로직)
                    old_qty = self.positions[stock_code]["quantity"]
                    old_purchase_price = self.positions[stock_code]["purchase_price"]
                    old_total_amount = old_qty * old_purchase_price

                    added_qty = new_quantity - old_qty
                    if added_qty > 0 and new_purchase_price:
                        new_total_amount = old_total_amount + (added_qty * new_purchase_price)
                        self.positions[stock_code]["quantity"] = new_quantity
                        self.positions[stock_code]["purchase_price"] = new_total_amount / new_quantity
                        self.positions[stock_code]["total_purchase_amount"] = new_total_amount
                        self.positions[stock_code]["buy_time"] = new_buy_time if new_buy_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S") # 매수 시간 갱신
                        logger.info(f"Updated quantity and avg price for {stock_code}: Qty {new_quantity}, Avg Price {self.positions[stock_code]['purchase_price']:.2f}")
                    else:
                        self.positions[stock_code]["quantity"] = new_quantity
                        logger.info(f"Updated quantity for {stock_code}: {new_quantity}")

            elif new_quantity < current_qty: # 매도
                self.positions[stock_code]["quantity"] = new_quantity
                if new_quantity == 0:
                    self.remove_position(stock_code)
                    logger.info(f"Chejan update: {stock_code} fully sold. Position removed.")
                else:
                    logger.info(f"Chejan update: {stock_code} position decreased. Remaining Qty: {new_quantity}")

            self.save_positions()

    def get_position(self, stock_code):
        """특정 종목의 포지션 데이터를 반환합니다."""
        with self.position_lock:
            return self.positions.get(stock_code, None)

    def get_all_positions(self):
        """현재 보유 중인 모든 포지션 데이터를 반환합니다 (사본 반환)."""
        with self.position_lock:
            return self.positions.copy()

    def remove_position(self, stock_code):
        """특정 종목의 포지션 데이터를 삭제합니다 (보통 전량 매도 후 호출)."""
        with self.position_lock:
            if stock_code in self.positions:
                # SetRealRemove는 KiwoomQueryHelper에서 처리되므로 여기서는 호출하지 않음
                del self.positions[stock_code]
                self.save_positions()
                logger.info(f"{stock_code} removed from positions.")

    def mark_half_sold(self, stock_code):
        """특정 종목의 절반 익절 여부를 표시합니다."""
        with self.position_lock:
            if stock_code in self.positions:
                self.positions[stock_code]["half_exited"] = True
                self.save_positions()
                logger.info(f"{stock_code} marked as half_exited.")

    # ✅ 신규 추가: 트레일링 스탑 최고가 업데이트
    def update_position_trail_high(self, stock_code, new_high_price):
        """
        특정 종목의 트레일링 스탑 최고가를 업데이트합니다.
        """
        with self.position_lock:
            if stock_code in self.positions:
                current_trail_high = self.positions[stock_code].get("trail_high", 0.0)
                if new_high_price > current_trail_high:
                    self.positions[stock_code]["trail_high"] = new_high_price
                    self.save_positions()
                    logger.debug(f"[{stock_code}] Trail high updated to {new_high_price:.2f}")
