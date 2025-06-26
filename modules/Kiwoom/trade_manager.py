# modules/kiwoom/trade_manager.py

import logging
import time
from datetime import datetime
from PyQt5.QtCore import QEventLoop, QTimer

from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
from modules.trade_logger import TradeLogger
from modules.common.error_codes import get_error_message  # ✅ 신규

logger = logging.getLogger(__name__)
trade_logger = TradeLogger()


class TradeManager:
    def __init__(self, kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number):
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.monitor_positions = monitor_positions
        self.account_number = account_number

        self.order_event_loop = QEventLoop()
        self.order_timer = QTimer()
        self.order_timer.setSingleShot(True)
        self.order_timer.timeout.connect(self._on_order_timeout)

        self.last_order_no = None
        self.pending_orders = {}

        self.kiwoom_helper.ocx.OnReceiveMsg.connect(self._on_receive_msg)
        self.kiwoom_helper.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data)

        logger.info(f"{get_current_time_str()}: TradeManager initialized for account {self.account_number}.")

    def _on_order_timeout(self):
        if self.order_event_loop.isRunning():
            logger.error(f"[{get_current_time_str()}] ❌ 주문 요청 타임아웃 발생")
            if self.last_order_no and self.last_order_no in self.pending_orders:
                del self.pending_orders[self.last_order_no]
            self.order_event_loop.exit()

    def _on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        logger.info(f"[{get_current_time_str()}] [API 메시지] [{rq_name}] {msg} (화면: {screen_no})")
        if "접수" in msg or "주문확인" in msg:
            if self.order_timer.isActive():
                self.order_timer.stop()
            if self.order_event_loop.isRunning():
                self.order_event_loop.exit()
        elif "실패" in msg or "오류" in msg:
            logger.error(f"[{get_current_time_str()}] 🚨 주문/오류 메시지 수신: {msg}")
            send_telegram_message(f"🚨 주문 오류 발생: {msg}")
            if self.order_timer.isActive():
                self.order_timer.stop()
            if self.order_event_loop.isRunning():
                self.order_event_loop.exit()

    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        if gubun != "0":
            return

        try:
            order_no = self.kiwoom_helper.ocx.GetChejanData(9203).strip()
            stock_code = self.kiwoom_helper.ocx.GetChejanData(9001).strip().lstrip("A")
            stock_name = self.kiwoom_helper.ocx.GetChejanData(302).strip()
            order_type_str = self.kiwoom_helper.ocx.GetChejanData(906).strip()
            order_qty = abs(int(self.kiwoom_helper.ocx.GetChejanData(900).strip()))
            executed_qty = abs(int(self.kiwoom_helper.ocx.GetChejanData(904).strip()))
            executed_price = abs(int(self.kiwoom_helper.ocx.GetChejanData(905).strip()))
            current_total_qty = abs(int(self.kiwoom_helper.ocx.GetChejanData(930).strip()))

            logger.info(f"[체결] {stock_name}({stock_code}) - 체결량: {executed_qty}, 체결가: {executed_price}, 현재잔고: {current_total_qty}")

            if "매수" in order_type_str:
                trade_type = "매수"
                pnl_amount = 0.0
                pnl_pct = 0.0
                self.monitor_positions.update_position_from_chejan(stock_code, current_total_qty, executed_price, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            elif "매도" in order_type_str:
                trade_type = "매도"
                pos_info = self.monitor_positions.get_position(stock_code)
                if pos_info:
                    purchase_price = pos_info.get("purchase_price", 0)
                    if purchase_price > 0:
                        pnl_amount = (executed_price - purchase_price) * executed_qty
                        pnl_pct = ((executed_price - purchase_price) / purchase_price) * 100
                        trade_type = "익절" if pnl_pct > 0 else "손절"
                    else:
                        pnl_amount = 0.0
                        pnl_pct = 0.0
                else:
                    pnl_amount = 0.0
                    pnl_pct = 0.0
                self.monitor_positions.update_position_from_chejan(stock_code, current_total_qty, executed_price)

            else:
                trade_type = "기타"
                pnl_amount = 0.0
                pnl_pct = 0.0

            account_info = self.kiwoom_tr_request.request_account_info(self.account_number)
            account_balance_after_trade = account_info.get("예수금", 0)

            trade_logger.log_trade(
                stock_code=stock_code,
                stock_name=stock_name,
                trade_type=trade_type,
                order_price=executed_price,
                executed_price=executed_price,
                quantity=executed_qty,
                pnl_amount=pnl_amount,
                pnl_pct=pnl_pct,
                account_balance_after_trade=account_balance_after_trade,
                strategy_name="AutoTrade"
            )

            if order_no in self.pending_orders:
                del self.pending_orders[order_no]

        except Exception as e:
            logger.error(f"[체결 처리 오류] {e}", exc_info=True)

    def place_order(self, stock_code, order_type, quantity, price, order_division, screen_no="0101"):
        if self.kiwoom_helper.connected_state != 0:
            logger.error("❌ 키움 API에 연결되지 않아 주문을 보낼 수 없습니다.")
            send_telegram_message("❌ 주문 실패: 키움 API 미연결.")
            return {"status": "error", "message": "API Not Connected"}

        if quantity <= 0:
            logger.warning(f"⚠️ 주문 수량 0 또는 음수입니다. 주문 무시: {stock_code}")
            return {"status": "error", "message": "Invalid quantity"}

        rq_name = "stock_order_req"

        self.last_order_no = None
        self.order_timer.start(30000)

        try:
            order_result_code = self.kiwoom_helper.ocx.SendOrder(
                rq_name,
                screen_no,
                self.account_number,
                order_type,
                stock_code,
                quantity,
                price,
                order_division,
                ""
            )

            if order_result_code == 0:
                logger.info(f"✅ 주문 요청 성공: {stock_code}, 수량: {quantity}, 가격: {price}, 구분: {order_division}")
                self.order_event_loop.exec_()

                if self.last_order_no:
                    self.pending_orders[self.last_order_no] = {
                        "stock_code": stock_code,
                        "order_type": order_type,
                        "quantity": quantity,
                        "price": price,
                        "order_division": order_division,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    return {"status": "success", "message": "Order placed", "order_no": self.last_order_no}
                else:
                    logger.warning("⚠️ 주문번호 수신 실패")
                    return {"status": "warning", "message": "Order placed but no order_no"}

            else:
                error_msg = get_error_message(order_result_code)
                logger.error(f"❌ 주문 요청 실패: {stock_code} - 코드: {order_result_code} ({error_msg})")
                send_telegram_message(f"❌ 주문 실패: {stock_code} - {error_msg}")
                return {"status": "error", "message": f"Order failed: {error_msg}"}

        except Exception as e:
            logger.error(f"❌ 주문 예외 발생: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
