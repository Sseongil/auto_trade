# modules/Kiwoom/trade_manager.py

import logging
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class TradeManager:
    def __init__(self, kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number):
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.monitor_positions = monitor_positions
        self.account_number = account_number
        logger.info(f"{get_current_time_str()}: TradeManager initialized.")

    def place_order(self, stock_code, order_type, quantity, price=0, hoga_gb="03", org_order_no=""):
        if not self.kiwoom_helper.connect_kiwoom():
            logger.error("❌ Kiwoom API not connected.")
            return {"status": "error", "message": "API 연결 안됨"}

        rqname = f"order_{stock_code}_{get_current_time_str()}"
        screen_no = "1000"

        order_result = self.kiwoom_tr_request.send_order(
            rqname, screen_no, self.account_number,
            order_type, stock_code, quantity, price, hoga_gb, org_order_no
        )

        if order_result["result"] == "success":
            actual_price = price
            if order_type == 1 and hoga_gb == "03":
                market_price = self.kiwoom_tr_request.request_current_price(stock_code)
                if market_price:
                    actual_price = market_price
            qty_sign = 1 if order_type == 1 else -1
            self.monitor_positions.update_position(stock_code, qty_sign * quantity, actual_price)
            return {"status": "success", "message": "주문 성공"}
        else:
            return {"status": "error", "message": order_result.get("error_message", "주문 실패")}
