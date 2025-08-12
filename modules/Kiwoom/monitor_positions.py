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
        self.positions = self.load_positions() # Initial load from file
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
                        # Ensure all necessary fields exist for loaded positions
                        for pos_key, pos_data in data.items():
                            if 'buy_time' not in pos_data or not pos_data['buy_time']:
                                pos_data['buy_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                logger.warning(f"⚠️ {pos_key} 포지션에 'buy_time' 없음. 현재 시간으로 설정.")
                            if 'trail_high' not in pos_data or not pos_data['trail_high']:
                                pos_data['trail_high'] = pos_data.get('purchase_price', 0.0)
                                logger.warning(f"⚠️ {pos_key} 포지션에 'trail_high' 없음. purchase_price로 설정.")
                            if 'name' not in pos_data or not pos_data['name']:
                                stock_name = self.kiwoom_helper.get_stock_name(pos_key)
                                pos_data['name'] = stock_name
                                logger.warning(f"⚠️ {pos_key} 포지션에 'name' 없음. '{stock_name}'으로 설정.")
                            if 'current_price' not in pos_data: # Add current_price if missing
                                pos_data['current_price'] = self.kiwoom_helper.get_current_price(pos_key)
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
            current_pos = self.positions.get(stock_code, {})
            current_qty = current_pos.get("quantity", 0)
            
            if new_quantity > 0:
                if stock_code not in self.positions:
                    self.positions[stock_code] = {
                        "stock_code": stock_code,
                        "quantity": new_quantity,
                        "purchase_price": new_purchase_price if new_purchase_price else 0,
                        "buy_date": datetime.today().strftime("%Y-%m-%d"),
                        "buy_time": new_buy_time if new_buy_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "half_exited": False,
                        "trail_high": new_purchase_price if new_purchase_price else 0,
                        "name": stock_name,
                        "current_price": self.kiwoom_helper.get_current_price(stock_code)
                    }
                    logger.info(f"New position added: {stock_name}({stock_code}) Qty: {new_quantity}, Price: {new_purchase_price}")
                else:
                    old_qty = current_pos["quantity"]
                    old_purchase_price = current_pos["purchase_price"]
                    
                    if new_quantity > old_qty and new_purchase_price is not None:
                        total_amount_before = old_qty * old_purchase_price
                        total_amount_after = total_amount_before + ((new_quantity - old_qty) * new_purchase_price)
                        self.positions[stock_code]["purchase_price"] = total_amount_after / new_quantity
                        self.positions[stock_code]["buy_time"] = new_buy_time if new_buy_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        logger.info(f"Updated position (added): {stock_name}({stock_code}) Qty: {new_quantity}, Avg Price: {self.positions[stock_code]['purchase_price']:.2f}")
                    
                    self.positions[stock_code]["quantity"] = new_quantity
                    self.positions[stock_code]["current_price"] = self.kiwoom_helper.get_current_price(stock_code)
                    logger.info(f"Updated position: {stock_name}({stock_code}) Qty: {new_quantity}")

            elif new_quantity == 0 and stock_code in self.positions:
                self.remove_position(stock_code)
                logger.info(f"Position removed: {stock_name}({stock_code}) (quantity became 0)")
            else:
                if stock_code in self.positions:
                    self.positions[stock_code]["quantity"] = new_quantity
                    self.positions[stock_code]["current_price"] = self.kiwoom_helper.get_current_price(stock_code)
                    logger.info(f"Position decreased: {stock_name}({stock_code}) Remaining Qty: {new_quantity}")

            self.save_positions()

    def get_position(self, stock_code):
        with self.position_lock:
            return self.positions.get(stock_code, None)

    def get_all_positions(self):
        """
        현재 보유 중인 모든 포지션 데이터를 반환합니다 (사본 반환).
        이 함수를 호출하기 전에 kiwoom_tr_request.request_account_balance_and_positions()를 호출하여
        최신 잔고 데이터를 가져오는 것이 좋습니다.
        """
        with self.position_lock:
            # TR로 가져온 최신 잔고 정보를 사용하여 self.positions를 업데이트
            # 이 함수는 TR 요청을 직접 하지 않고, 이미 업데이트된 self.positions를 반환합니다.
            # TR 요청은 main_strategy_loop나 Flask의 /status에서 주기적으로 수행해야 합니다.
            updated_positions = self.positions.copy()
            for code, pos_data in updated_positions.items():
                pos_data['current_price'] = self.kiwoom_helper.get_current_price(code) # Ensure current price is up-to-date
            return updated_positions

    def update_positions_from_tr(self, tr_positions_list: list):
        """
        opw00018 TR 조회로 받은 최신 보유 종목 리스트로 self.positions를 업데이트합니다.
        """
        with self.position_lock:
            new_positions = {}
            for item in tr_positions_list:
                stock_code = item.get("종목코드")
                if not stock_code:
                    continue
                
                # 데이터 정제 및 타입 변환
                # 쉼표 제거 후 int/float 변환 시도, 실패 시 기본값 0
                try:
                    quantity = int(item.get("보유수량", "0").replace(",", ""))
                except ValueError:
                    quantity = 0
                    logger.warning(f"[{stock_code}] 보유수량 파싱 오류: '{item.get('보유수량')}'")
                
                try:
                    purchase_price = int(item.get("매입가", "0").replace(",", ""))
                except ValueError:
                    purchase_price = 0
                    logger.warning(f"[{stock_code}] 매입가 파싱 오류: '{item.get('매입가')}'")
                
                try:
                    current_price = int(item.get("현재가", "0").replace(",", ""))
                except ValueError:
                    current_price = 0
                    logger.warning(f"[{stock_code}] 현재가 파싱 오류: '{item.get('현재가')}'")
                
                try:
                    pnl = int(item.get("평가손익", "0").replace(",", ""))
                except ValueError:
                    pnl = 0
                    logger.warning(f"[{stock_code}] 평가손익 파싱 오류: '{item.get('평가손익')}'")
                
                try:
                    pnl_pct = float(item.get("수익률", "0.0"))
                except ValueError:
                    pnl_pct = 0.0
                    logger.warning(f"[{stock_code}] 수익률 파싱 오류: '{item.get('수익률')}'")
                
                # 기존 포지션 정보 가져오기 (half_exited, buy_time, trail_high 유지)
                existing_pos = self.positions.get(stock_code, {})
                
                new_positions[stock_code] = {
                    "stock_code": stock_code,
                    "name": item.get("종목명"),
                    "quantity": quantity,
                    "purchase_price": purchase_price,
                    "current_price": current_price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "buy_date": existing_pos.get("buy_date", datetime.today().strftime("%Y-%m-%d")), # TR에는 없으므로 기존 값 유지
                    "buy_time": existing_pos.get("buy_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")), # TR에는 없으므로 기존 값 유지
                    "half_exited": existing_pos.get("half_exited", False), # TR에는 없으므로 기존 값 유지
                    "trail_high": existing_pos.get("trail_high", current_price) # TR에는 없으므로 현재가로 초기화 또는 기존 값 유지
                }
            
            self.positions = new_positions
            self.save_positions()
            logger.info(f"✅ Positions updated from TR data. Current positions: {len(self.positions)}.")


    def remove_position(self, stock_code):
        with self.position_lock:
            if stock_code in self.positions:
                del self.positions[stock_code]
                self.save_positions()
                logger.info(f"{stock_code} removed from positions.")

    def mark_half_sold(self, stock_code):
        with self.position_lock:
            if stock_code in self.positions:
                self.positions[stock_code]["half_exited"] = True
                self.save_positions()
                logger.info(f"{stock_code} marked as half_exited.")

    def update_position_trail_high(self, stock_code, new_high_price):
        with self.position_lock:
            if stock_code in self.positions:
                current_trail_high = self.positions[stock_code].get("trail_high", 0.0)
                if new_high_price > current_trail_high:
                    self.positions[stock_code]["trail_high"] = new_high_price
                    self.save_positions()
                    logger.debug(f"[{stock_code}] Trail high updated to {new_high_price:.2f}")
