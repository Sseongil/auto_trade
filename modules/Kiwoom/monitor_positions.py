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
