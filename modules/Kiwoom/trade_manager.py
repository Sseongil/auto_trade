# modules/Kiwoom/trade_manager.py

import logging
import time
from datetime import datetime

from PyQt5.QtCore import QEventLoop, QTimer 

from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
from modules.trade_logger import TradeLogger 

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
        self.chejan_data = {} 

        self.kiwoom_helper.ocx.OnReceiveMsg.connect(self._on_receive_msg)
        self.kiwoom_helper.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data)
        
        logger.info(f"{get_current_time_str()}: TradeManager initialized for account {self.account_number}.")

    def _on_order_timeout(self):
        """주문 요청 타임아웃 발생 시 호출되는 콜백."""
        if self.order_event_loop.isRunning():
            logger.error(f"[{get_current_time_str()}]: ❌ 주문 요청 타임아웃 발생 (마지막 주문번호: {self.last_order_no})")
            if self.last_order_no and self.last_order_no in self.pending_orders:
                del self.pending_orders[self.last_order_no] 
            self.order_event_loop.exit() 


    def _on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        """API로부터의 메시지를 수신했을 때 호출됩니다 (주로 주문 확인/오류 메시지)."""
        logger.info(f"[{get_current_time_str()}]: [API 메시지] [{rq_name}] {msg} (화면: {screen_no})")
        if "주문이 접수되었습니다." in msg or "주문확인" in msg:
            if self.order_timer.isActive():
                self.order_timer.stop()
            if self.order_event_loop.isRunning():
                self.order_event_loop.exit()
        elif "실패" in msg or "오류" in msg:
            logger.error(f"[{get_current_time_str()}]: 🚨 주문/오류 메시지 수신: {msg}")
            send_telegram_message(f"🚨 주문 오류 발생: {msg}")
            if self.order_timer.isActive():
                self.order_timer.stop()
            if self.order_event_loop.isRunning():
                self.order_event_loop.exit()


    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        """
        💡 체결/잔고 데이터 수신 이벤트 핸들러.
        매매체결통보, 잔고편입/편출 통보 등을 수신합니다.
        gubun '0'은 접수/체결, '1'은 잔고
        """
        logger.debug(f"[{get_current_time_str()}] 체결 데이터 수신: Gubun={gubun}, FID List={fid_list}")
        
        if gubun == "0": 
            order_no = self.kiwoom_helper.ocx.GetChejanData(9203).strip() 
            stock_code = self.kiwoom_helper.ocx.GetChejanData(9001).strip() 
            stock_name = self.kiwoom_helper.ocx.GetChejanData(911).strip() 
            order_type_str = self.kiwoom_helper.ocx.GetChejanData(906).strip() 
            order_qty = abs(int(self.kiwoom_helper.ocx.GetChejanData(900).strip())) 
            order_price = abs(int(self.kiwoom_helper.ocx.GetChejanData(901).strip())) 
            executed_qty = abs(int(self.kiwoom_helper.ocx.GetChejanData(904).strip())) 
            executed_price = abs(int(self.kiwoom_helper.ocx.GetChejanData(905).strip())) 
            current_total_qty = abs(int(self.kiwoom_helper.ocx.GetChejanData(930).strip())) 

            order_status = self.kiwoom_helper.ocx.GetChejanData(919).strip() 
            
            is_fully_executed = (current_total_qty == 0 and "매도" in order_type_str) or \
                                (current_total_qty >= order_qty and "매수" in order_type_str and order_qty > 0 and executed_qty > 0)
            
            logger.info(f"[{get_current_time_str()}] 체결 알림: {stock_name}({stock_code}) - 주문번호: {order_no}, 구분: {order_type_str}, 체결량: {executed_qty}, 체결가: {executed_price}, 상태: {order_status}")

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
                order_price=order_price,
                executed_price=executed_price,
                quantity=executed_qty,
                pnl_amount=pnl_amount,
                pnl_pct=pnl_pct,
                account_balance_after_trade=account_balance_after_trade,
                strategy_name="AutoTrade" 
            )

            if order_no in self.pending_orders:
                if is_fully_executed:
                    del self.pending_orders[order_no]
                    logger.info(f"주문 {order_no} ({stock_name}) 완전 체결 완료. 대기 목록에서 제거.")
        
        elif gubun == "1": 
            logger.debug(f"잔고 데이터 수신 (Gubun=1): {fid_list}")

        if self.order_timer.isActive():
            self.order_timer.stop()
        if self.order_event_loop.isRunning():
            self.order_event_loop.exit()

    def place_order(self, stock_code, order_type, quantity, price, order_division, screen_no="0101"):
        """
        주문(매수/매도)을 실행합니다.
        """
        if self.kiwoom_helper.connected_state != 0:
            logger.error("❌ Kiwoom API에 연결되지 않아 주문을 보낼 수 없습니다.")
            send_telegram_message("❌ 주문 실패: 키움 API 미연결.")
            return {"status": "error", "message": "API Not Connected"}

        if quantity <= 0:
            logger.warning(f"⚠️ 주문 수량 0 또는 음수입니다. 주문을 실행하지 않습니다. 종목: {stock_code}")
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
                logger.info(f"✅ 주문 요청 성공: {stock_code}, 타입: {order_type}, 수량: {quantity}, 가격: {price}, 호가: {order_division}")
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
                    logger.warning(f"⚠️ 주문 요청 성공했으나 주문번호 수신 실패 또는 타임아웃: {stock_code}")
                    return {"status": "warning", "message": "Order placed but no order_no received (timeout)"}
            else:
                error_msg = self.kiwoom_tr_request._get_error_message(order_result_code)
                logger.error(f"❌ 주문 요청 실패: {stock_code}, 코드: {order_result_code} ({error_msg})")
                send_telegram_message(f"❌ 주문 실패: {stock_code} - {error_msg}")
                return {"status": "error", "message": f"Order failed: {error_msg}"}

        except Exception as e:
            logger.error(f"❌ 주문 중 예외 발생: {stock_code} - {e}", exc_info=True)
            send_telegram_message(f"❌ 주문 중 예외 발생: {stock_code} - {e}")
            return {"status": "error", "message": f"Exception during order: {e}"}
        finally:
            if self.order_timer.isActive():
                self.order_timer.stop()


