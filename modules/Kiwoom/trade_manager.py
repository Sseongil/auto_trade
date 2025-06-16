# C:\Users\user\stock_auto\modules\Kiwoom\trade_manager.py

import time
import logging

# ✅ 임포트 경로 수정됨: common 폴더 안의 config와 utils
from modules.common.config import DEFAULT_LOT_SIZE
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class TradeManager:
    def __init__(self, kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number):
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.monitor_positions = monitor_positions # MonitorPositions 인스턴스
        self.account_number = account_number
        logger.info(f"{get_current_time_str()}: TradeManager initialized for account {self.account_number}.")

    def place_order(self, stock_code, order_type, quantity, price=0, hoga_gb="03", org_order_no=""):
        """
        주문을 실행합니다.
        :param stock_code: 종목 코드
        :param order_type: 주문 유형 (1:매수, 2:매도)
        :param quantity: 수량
        :param price: 가격 (시장가이면 0)
        :param hoga_gb: 호가 구분 (00:지정가, 03:시장가)
        :param org_order_no: 원주문번호 (정정/취소 시 사용)
        :return: 주문 결과 딕셔너리
        """
        if not self.kiwoom_helper.connect_kiwoom(): # 연결 상태 다시 확인
            logger.error(f"{get_current_time_str()}: Kiwoom API not connected. Cannot place order for {stock_code}.")
            return {"result": "fail", "message": "Kiwoom API not connected."}

        rqname = f"SendOrder_{stock_code}_{order_type}_{time.time()}" # 고유한 RQName
        screen_no = "1000" # 임의의 화면 번호 (중복되지 않게 관리)

        logger.info(f"{get_current_time_str()}: Attempting to place order for {stock_code}. Type: {order_type} (1:Buy, 2:Sell), Qty: {quantity}, Price: {price}, Hoga: {hoga_gb}")

        # 주문 전송
        order_result = self.kiwoom_tr_request.send_order(
            rqname=rqname,
            screen_no=screen_no,
            account_no=self.account_number,
            order_type=order_type,
            stock_code=stock_code,
            quantity=quantity,
            price=price,
            hoga_gb=hoga_gb,
            org_order_no=org_order_no
        )
        
        if order_result["result"] == "success":
            logger.info(f"{get_current_time_str()}: Order placed successfully for {stock_code}. Type: {order_type}, Qty: {quantity}")
            
            # 주문 성공 시 monitor_positions 업데이트 (여기서 바로 업데이트)
            # 시장가 매수 시 현재가를 조회하여 매입단가로 사용
            actual_price = price
            if hoga_gb == "03" and order_type == 1: # 시장가 매수 시 현재가 조회
                current_price = self.kiwoom_tr_request.request_current_price(stock_code)
                if current_price:
                    actual_price = current_price
                else:
                    logger.warning(f"{get_current_time_str()}: Could not get current price for {stock_code}. Using provided price ({price}) for position update.")

            if order_type == 1: # 매수
                # MonitorPositions는 JSON 파일 기반이므로, JSON 파일 업데이트를 담당
                self.monitor_positions.update_position(stock_code, quantity, actual_price)
            elif order_type == 2: # 매도
                self.monitor_positions.update_position(stock_code, -quantity, 0) # 매도는 매입단가 업데이트 안함

            return {"status": "success", "order_result": order_result["status"]}
        else:
            logger.error(f"{get_current_time_str()}: Order failed for {stock_code}. Error: {order_result['error_message']}")
            return {"status": "error", "message": order_result["error_message"]}

    def send_buy_order(self, stock_code, order_type_str, price, quantity):
        hoga_gb = "00" if order_type_str == "지정가" else "03"
        return self.place_order(stock_code, 1, quantity, price, hoga_gb)

    def send_sell_order(self, stock_code, order_type_str, price, quantity):
        hoga_gb = "00" if order_type_str == "지정가" else "03"
        return self.place_order(stock_code, 2, quantity, price, hoga_gb)

    def get_current_stock_price(self, stock_code):
        """종목의 현재가를 조회합니다."""
        if not self.kiwoom_helper.connect_kiwoom():
            return None
        price = self.kiwoom_tr_request.request_current_price(stock_code)
        return price