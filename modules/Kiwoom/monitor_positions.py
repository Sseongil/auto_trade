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
                            if "buy_time" not in pos_data:
                                pos_data["buy_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                logger.warning(f"Position for {pos_key} had no 'buy_time'. Initialized.")
                            if "name" not in pos_data:
                                pos_data["name"] = self.kiwoom_helper.get_stock_name(pos_key)
                        return data
                    except json.JSONDecodeError:
                        logger.error(f"JSONDecodeError when loading positions from {POSITIONS_FILE_PATH}")
                        return {}
            logger.info(f"Positions file not found at {POSITIONS_FILE_PATH}. Starting with empty positions.")
            return {}

    def save_positions(self):
        with self.position_lock:
            try:
                with open(POSITIONS_FILE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(self.positions, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error saving positions: {e}")

    def sync_local_positions(self, api_holdings_data):
        with self.position_lock:
            if not isinstance(api_holdings_data, list):
                logger.warning(f"Invalid holdings data: {api_holdings_data}")
                return

            old_positions = self.positions.copy()
            self.positions = {}

            for item in api_holdings_data:
                stock_code = item.get("종목코드", "").strip()
                quantity = int(item.get("보유수량", 0))
                purchase_price = float(item.get("매입가", 0))
                stock_name = item.get("종목명", "Unknown")

                if stock_code and quantity > 0:
                    existing_pos_data = old_positions.get(stock_code, {})
                    self.positions[stock_code] = {
                        "quantity": quantity,
                        "purchase_price": purchase_price,
                        "total_purchase_amount": purchase_price * quantity,
                        "buy_date": existing_pos_data.get("buy_date", datetime.today().strftime("%Y-%m-%d")),
                        "buy_time": existing_pos_data.get("buy_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        "half_exited": existing_pos_data.get("half_exited", False),
                        "trail_high": existing_pos_data.get("trail_high", purchase_price),
                        "name": stock_name
                    }
                    logger.info(f"Synced holding: {stock_name}({stock_code}) x{quantity}")
            self.save_positions()
            logger.info(f"Local positions synced with API holdings: {len(self.positions)} items")

    def register_all_positions_for_real_time_data(self):
        with self.position_lock:
            if not self.positions:
                logger.info("No positions to register for real-time data.")
                return

            codes_to_register = list(self.positions.keys())
            screen_no = self.kiwoom_helper.generate_real_time_screen_no()
            fid_list = "10;15;228;851;852;27;28"

            try:
                self.kiwoom_helper.SetRealReg(screen_no, ";".join(codes_to_register), fid_list, "0")
                logger.info(f"Real-time data registered for {len(codes_to_register)} items.")
            except Exception as e:
                logger.error(f"Failed to register real-time data: {e}", exc_info=True)

    def update_position_from_chejan(self, stock_code, new_quantity, new_purchase_price=None, new_buy_time=None):
        stock_code = stock_code.strip()
        with self.position_lock:
            current_pos = self.positions.get(stock_code, {})
            current_qty = current_pos.get("quantity", 0)

            if new_quantity <= 0:
                self.remove_position(stock_code)
                logger.info(f"{stock_code} position removed (quantity <= 0).")
                return

            if new_quantity > current_qty:
                stock_name = self.kiwoom_helper.get_stock_name(stock_code)
                self.positions[stock_code] = {
                    "quantity": new_quantity,
                    "purchase_price": new_purchase_price if new_purchase_price else 0.0,
                    "total_purchase_amount": new_purchase_price * new_quantity if new_purchase_price else 0.0,
                    "buy_date": datetime.today().strftime("%Y-%m-%d"),
                    "buy_time": new_buy_time if new_buy_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "half_exited": False,
                    "trail_high": new_purchase_price if new_purchase_price else 0.0,
                    "name": stock_name
                }
                logger.info(f"New position: {stock_name}({stock_code}) x{new_quantity}")
            else:
                self.positions[stock_code]["quantity"] = new_quantity
                logger.info(f"Updated quantity for {stock_code}: {new_quantity}")

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
                self.kiwoom_helper.SetRealRemove("ALL", stock_code)
                del self.positions[stock_code]
                self.save_positions()
                logger.info(f"{stock_code} removed from positions.")
