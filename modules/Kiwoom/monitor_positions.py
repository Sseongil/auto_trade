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
    def __init__(self, kiwoom_helper, kiwoom_tr_request, trade_manager, account_number): 
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.trade_manager = trade_manager 
        self.account_number = account_number
        self.position_lock = threading.Lock() 
        self.positions = self.load_positions()
        logger.info(f"{get_current_time_str()}: MonitorPositions initialized for account {self.account_number}. Loaded {len(self.positions)} positions.")

    def load_positions(self):
        with self.position_lock: 
            if os.path.exists(POSITIONS_FILE_PATH):
                with open(POSITIONS_FILE_PATH, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        for pos_key, pos_data in data.items():
                            if "buy_time" not in pos_data:
                                pos_data["buy_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                logger.warning(f"Position for {pos_key} had no 'buy_time'. Initialized with current time.")
                        return data
                    except json.JSONDecodeError:
                        logger.error(f"JSONDecodeError when loading positions from {POSITIONS_FILE_PATH}. Returning empty positions.")
                        return {}
            logger.info(f"{POSITIONS_FILE_PATH} not found. Starting with empty positions.")
            return {}

    def save_positions(self):
        with self.position_lock: 
            try:
                with open(POSITIONS_FILE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(self.positions, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error saving positions to {POSITIONS_FILE_PATH}: {e}")

    def update_position(self, stock_code, quantity, price):
        stock_code = stock_code.strip()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.position_lock: 
            if stock_code not in self.positions:
                self.positions[stock_code] = {
                    "quantity": 0,  
                    "purchase_price": 0.0, 
                    "total_purchase_amount": 0.0, 
                    "buy_date": datetime.today().strftime("%Y-%m-%d"),
                    "buy_time": None, 
                    "half_exited": False,
                    "trail_high": 0.0, 
                    "name": self.kiwoom_helper.get_stock_name(stock_code) 
                }
                logger.info(f"Initial position data structure created for {stock_code}.")

            position = self.positions[stock_code]

            if quantity > 0: 
                total_purchase_amount = position["total_purchase_amount"] + price * quantity
                new_quantity = position["quantity"] + quantity
                avg_purchase_price = total_purchase_amount / new_quantity if new_quantity else 0.0
                
                position.update({
                    "quantity": new_quantity,
                    "total_purchase_amount": total_purchase_amount,
                    "purchase_price": avg_purchase_price,
                    "buy_time": position["buy_time"] if position["buy_time"] else now_str 
                })
                logger.info(f"Position updated for {stock_code} (BUY): new_qty={new_quantity}, avg_price={avg_purchase_price:.2f}, buy_time={position['buy_time']}")

            elif quantity < 0: 
                sell_qty = abs(quantity)
                if position["quantity"] >= sell_qty: 
                    position["quantity"] -= sell_qty
                    logger.info(f"Position updated for {stock_code} (SELL): remaining_qty={position['quantity']}")

                    if position["quantity"] == 0: 
                        position.update({
                            "total_purchase_amount": 0.0,
                            "purchase_price": 0.0,
                            "trail_high": 0.0,
                            "half_exited": False,
                            "buy_time": None 
                        })
                        logger.info(f"Position {stock_code} fully exited. Position data reset, buy_time set to None.")
                else:
                    logger.warning(f"Attempted to sell {sell_qty} of {stock_code}, but only {position['quantity']} are held. No action taken.")
            
            self.save_positions()

    def get_position(self, stock_code):
        with self.position_lock: 
            return self.positions.get(stock_code, None)

    def get_all_positions(self):
        with self.position_lock: 
            return self.positions.copy() 

    def remove_position(self, stock_code):
        with self.position_lock: 
            if stock_code in self.positions:
                del self.positions[stock_code]
                self.save_positions()
                logger.info(f"Position for {stock_code} removed from monitoring.")
            else:
                logger.warning(f"Attempted to remove non-existent position: {stock_code}. No action taken.")

    def sync_local_positions(self, api_holdings: list):
        """
        키움 API에서 가져온 보유 종목 리스트 (opw00018 결과)와 로컬 positions.json을 동기화합니다.
        API 데이터에 기반하여 로컬 데이터를 업데이트하고, 불필요한 로컬 포지션을 정리합니다.
        Args:
            api_holdings (list): kiwoom_tr_request.request_daily_account_holdings()의 결과.
                                 각 항목은 dict이며 "stock_code", "name", "quantity" 등을 포함.
        """
        with self.position_lock:
            updated_local_positions = {}
            current_time_str = get_current_time_str()

            for api_item in api_holdings:
                stock_code = api_item["stock_code"]
                item_name = api_item["name"]
                api_quantity = api_item["quantity"]
                api_purchase_price = api_item.get("purchase_price", 0.0)
                api_total_purchase_amount = api_item.get("total_purchase_amount", 0.0)
                api_current_price = api_item.get("current_price", 0.0)

                if stock_code in self.positions:
                    local_pos = self.positions[stock_code]
                    local_pos["quantity"] = api_quantity
                    local_pos["purchase_price"] = api_purchase_price
                    local_pos["total_purchase_amount"] = api_total_purchase_amount
                    local_pos["trail_high"] = max(local_pos.get("trail_high", 0.0), api_current_price)
                    local_pos["last_update"] = current_time_str
                    updated_local_positions[stock_code] = local_pos
                    logger.debug(f"Sync: Updated local position for {stock_code} from API.")
                else:
                    new_pos = {
                        "quantity": api_quantity,
                        "purchase_price": api_purchase_price,
                        "total_purchase_amount": api_total_purchase_amount,
                        "buy_date": datetime.today().strftime("%Y-%m-%d"), 
                        "buy_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                        "half_exited": False, 
                        "trail_high": api_current_price, 
                        "name": item_name,
                        "last_update": current_time_str
                    }
                    updated_local_positions[stock_code] = new_pos
                    logger.info(f"Sync: Added new position {stock_code} ({item_name}) from API to local.")
            
            keys_to_remove = []
            for stock_code, local_pos in self.positions.items():
                if stock_code not in updated_local_positions and local_pos["quantity"] == 0:
                    keys_to_remove.append(stock_code)
                    logger.info(f"Sync: Removed zero-quantity local position for {stock_code} (not in API holdings).")
                elif stock_code not in updated_local_positions and local_pos["quantity"] > 0:
                    logger.warning(f"Sync: Local position {stock_code} (Qty: {local_pos['quantity']}) exists but not found in API holdings. This might indicate an issue.")
            
            for key in keys_to_remove:
                if key in self.positions:
                    del self.positions[key]

            self.positions = updated_local_positions 
            self.save_positions()
            logger.info(f"Sync: Local positions synchronized. Total {len(self.positions)} positions remaining.")
