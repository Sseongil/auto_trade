# modules/Kiwoom/monitor_positions.py

import os
import json
import logging
from datetime import datetime
from modules.common.config import POSITIONS_FILE_PATH
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class MonitorPositions:
    def __init__(self, kiwoom_helper, kiwoom_tr_request, account_number):
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.account_number = account_number
        self.positions = self.load_positions()
        
        # 💡 실시간 시세 등록에 사용할 화면번호를 관리하는 딕셔너리
        # {stock_code: screen_no}
        self.real_time_screen_nos = {} 

        logger.info(f"{get_current_time_str()}: MonitorPositions initialized for account {self.account_number}. Loaded {len(self.positions)} positions.")

    def load_positions(self):
        """
        저장된 포지션 데이터를 로드하고, 'buy_time' 필드가 없는
        이전 데이터의 호환성을 위해 현재 시간으로 보완합니다.
        """
        if os.path.exists(POSITIONS_FILE_PATH):
            with open(POSITIONS_FILE_PATH, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    for pos_key, pos_data in data.items():
                        if "buy_time" not in pos_data:
                            pos_data["buy_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            logger.warning(f"Position for {pos_key} had no 'buy_time'. Initialized with current time.")
                        # `current_price` 필드가 없는 경우 초기화
                        if "current_price" not in pos_data:
                            pos_data["current_price"] = 0.0
                        # `name` 필드가 없는 경우 Kiwoom API를 통해 조회
                        if "name" not in pos_data:
                            pos_data["name"] = self.kiwoom_helper.get_stock_name(pos_key)
                            logger.info(f"Loaded position for {pos_key} had no 'name'. Fetched: {pos_data['name']}")
                    return data
                except json.JSONDecodeError:
                    logger.error(f"JSONDecodeError when loading positions from {POSITIONS_FILE_PATH}. Returning empty positions.")
                    return {}
        logger.info(f"Positions file not found at {POSITIONS_FILE_PATH}. Starting with empty positions.")
        return {}

    def save_positions(self):
        """현재 포지션 데이터를 파일에 저장합니다."""
        try:
            with open(POSITIONS_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.positions, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving positions to {POSITIONS_FILE_PATH}: {e}")

    def update_position(self, stock_code, quantity, price):
        """
        종목의 포지션 수량을 업데이트하고, 매수/매도 시점에 따라 buy_time을 관리합니다.
        
        Args:
            stock_code (str): 종목 코드
            quantity (int): 업데이트할 수량 (양수: 매수, 음수: 매도)
            price (float): 거래 가격
        """
        stock_code = stock_code.strip()
        
        # 새로운 종목이거나 기존 포지션이 비어있었던 경우 (초기 매수)
        if stock_code not in self.positions or self.positions[stock_code]["quantity"] == 0:
            self.positions[stock_code] = {
                "quantity": 0,
                "purchase_price": 0.0,
                "total_purchase_amount": 0.0,
                "buy_date": datetime.today().strftime("%Y-%m-%d"),
                "buy_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "half_exited": False,
                "trail_high": 0.0,
                "name": self.kiwoom_helper.get_stock_name(stock_code),
                "current_price": 0.0 # 초기 current_price
            }
            logger.info(f"New position initiated for {stock_code}. Buy time set: {self.positions[stock_code]['buy_time']}")
            # 💡 새 포지션이 생겼으니 실시간 등록
            self._register_real_time_for_position(stock_code)

        position = self.positions[stock_code]

        if quantity > 0: # 매수
            total_purchase_amount = position["total_purchase_amount"] + price * quantity
            new_quantity = position["quantity"] + quantity
            avg_purchase_price = total_purchase_amount / new_quantity if new_quantity else 0.0
            
            position.update({
                "quantity": new_quantity,
                "total_purchase_amount": total_purchase_amount,
                "purchase_price": avg_purchase_price,
                "buy_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            logger.info(f"Position updated for {stock_code} (BUY): new_qty={new_quantity}, avg_price={avg_purchase_price:.2f}")

        elif quantity < 0: # 매도
            sell_qty = abs(quantity)
            if position["quantity"] >= sell_qty:
                position["quantity"] -= sell_qty
                logger.info(f"Position updated for {stock_code} (SELL): remaining_qty={position['quantity']}")

                if position["quantity"] == 0: # 전량 매도된 경우
                    position.update({
                        "total_purchase_amount": 0.0,
                        "purchase_price": 0.0,
                        "trail_high": 0.0,
                        "half_exited": False,
                        "buy_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S") # 청산 시점의 buy_time 갱신
                    })
                    logger.info(f"Position {stock_code} fully exited. Position data reset.")
                    # 💡 전량 매도 시 실시간 등록 해제
                    self._unregister_real_time_for_position(stock_code)
            else:
                logger.warning(f"Attempted to sell {sell_qty} of {stock_code}, but only {position['quantity']} are held.")
        
        self.save_positions()

    def get_position(self, stock_code):
        """특정 종목의 포지션 데이터를 반환합니다."""
        return self.positions.get(stock_code, None)

    def get_all_positions(self):
        """현재 보유 중인 모든 포지션 데이터를 반환합니다."""
        # 💡 각 종목의 current_price를 real_time_data에서 최신으로 업데이트하여 반환
        for stock_code, pos_data in self.positions.items():
            if stock_code in self.kiwoom_helper.real_time_data:
                pos_data['current_price'] = self.kiwoom_helper.real_time_data[stock_code].get('current_price', pos_data['current_price'])
        return self.positions

    def remove_position(self, stock_code):
        """특정 종목의 포지션 데이터를 삭제합니다 (보통 전량 매도 후 호출)."""
        if stock_code in self.positions:
            del self.positions[stock_code]
            self.save_positions()
            self._unregister_real_time_for_position(stock_code) # � 포지션 삭제 시 실시간 등록 해제
            logger.info(f"Position for {stock_code} removed from monitoring.")
        else:
            logger.warning(f"Attempted to remove non-existent position: {stock_code}")

    # 💡 모든 보유 종목에 대한 실시간 시세 등록
    def register_all_positions_for_real_time_data(self):
        """
        현재 보유 중인 모든 종목에 대해 실시간 데이터를 등록합니다.
        Kiwoom API 연결이 완료된 후에 호출되어야 합니다.
        """
        logger.info(f"{get_current_time_str()}: 실시간 데이터 등록 시작 (보유 종목).")
        current_positions = self.get_all_positions() # 현재 포지션 가져오기 (이미 current_price 업데이트 포함)
        
        # 기존에 등록된 종목 중 더 이상 보유하지 않는 종목은 해제
        codes_to_unregister = set(self.real_time_screen_nos.keys()) - set(current_positions.keys())
        for stock_code in codes_to_unregister:
            self._unregister_real_time_for_position(stock_code)

        # 현재 보유 중인 종목 중 아직 실시간 등록되지 않은 종목 등록
        for stock_code in current_positions.keys():
            if stock_code not in self.real_time_screen_nos:
                self._register_real_time_for_position(stock_code)
        
        logger.info(f"{get_current_time_str()}: 실시간 데이터 등록 완료 (총 {len(self.real_time_screen_nos)} 종목 등록됨).")

    def _register_real_time_for_position(self, stock_code):
        """단일 종목에 대해 실시간 데이터를 등록합니다."""
        if self.kiwoom_helper.connected_state != 0:
            logger.warning(f"Kiwoom API가 연결되지 않아 {stock_code} 실시간 등록을 건너뜜.")
            return

        screen_no = self.kiwoom_helper.generate_real_time_screen_no()
        # "10": 현재가, "13": 누적거래량, "15": 체결량 (주식체결 FID)
        # 필요한 다른 FID도 추가 가능
        fid_list = "10;13;15" 
        
        self.kiwoom_helper.SetRealReg(screen_no, stock_code, fid_list, "0")
        self.real_time_screen_nos[stock_code] = screen_no
        logger.info(f"실시간 등록: {stock_code} -> 화면번호 {screen_no}")

    def _unregister_real_time_for_position(self, stock_code):
        """단일 종목에 대해 실시간 데이터를 해제합니다."""
        if stock_code in self.real_time_screen_nos:
            screen_no = self.real_time_screen_nos[stock_code]
            self.kiwoom_helper.SetRealRemove(screen_no, stock_code)
            del self.real_time_screen_nos[stock_code]
            if stock_code in self.kiwoom_helper.real_time_data:
                del self.kiwoom_helper.real_time_data[stock_code] # 헬퍼의 데이터에서도 삭제
            logger.info(f"실시간 해제: {stock_code} -> 화면번호 {screen_no}")

