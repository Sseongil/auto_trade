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
        logger.info(f"{get_current_time_str()}: MonitorPositions initialized for account {self.account_number}.")

    def load_positions(self):
        if os.path.exists(POSITIONS_FILE_PATH):
            with open(POSITIONS_FILE_PATH, 'r', encoding='utf-8') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def save_positions(self):
        with open(POSITIONS_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.positions, f, indent=4, ensure_ascii=False)

    def update_position(self, stock_code, quantity, price):
        stock_code = stock_code.strip()
        if stock_code not in self.positions:
            self.positions[stock_code] = {
                "quantity": 0,
                "purchase_price": 0.0,
                "total_purchase_amount": 0.0,
                "buy_date": datetime.today().strftime("%Y-%m-%d"),
                "half_exited": False,
                "trail_high": 0.0
            }

        position = self.positions[stock_code]
        if quantity > 0:
            total = position["total_purchase_amount"] + price * quantity
            qty = position["quantity"] + quantity
            avg_price = total / qty if qty else 0.0
            position.update({
                "quantity": qty,
                "total_purchase_amount": total,
                "purchase_price": avg_price
            })
        elif quantity < 0:
            sell_qty = abs(quantity)
            if position["quantity"] >= sell_qty:
                position["quantity"] -= sell_qty
                if position["quantity"] == 0:
                    position.update({
                        "total_purchase_amount": 0.0,
                        "purchase_price": 0.0,
                        "trail_high": 0.0,
                        "half_exited": False
                    })
        self.save_positions()

    def get_position(self, stock_code):
        return self.positions.get(stock_code, None)

    def get_all_positions(self):
        return self.positions
