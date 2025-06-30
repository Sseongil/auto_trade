# modules/Kiwoom/trade_manager.py

import logging
import time
from datetime import datetime
from PyQt5.QtCore import QEventLoop, QTimer
import uuid # 고유 ID 생성을 위해 추가

from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
from modules.trade_logger import TradeLogger
from modules.common.error_codes import get_error_message

logger = logging.getLogger(__name__)
trade_logger = TradeLogger() # TradeLogger 인스턴스 생성

class TradeManager:
    # 1. 클래스-레벨 상수로 주문 유형 및 거래 구분 정의
    ORDER_TYPE_MAP = {
        1: "신규매수", 2: "신규매도", 3: "매수취소", 4: "매도취소", 5: "매수정정", 6: "매도정정"
    }
    ORDER_DIVISION_MAP = {
        "00": "지정가", "03": "시장가"
    }

    def __init__(self, kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number):
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.monitor_positions = monitor_positions
        self.account_number = account_number
        
        self.order_event_loop = QEventLoop()
        self.order_timer = QTimer()
        self.order_timer.setSingleShot(True)
        self.order_timer.timeout.connect(self._on_order_timeout)

        # 2. self.pending_orders를 사용하여 주문 상태를 더 구조적으로 관리
        # key: 임시 주문 ID (UUID), value: {주문 정보, 실제 주문번호, 상태 등}
        self.pending_orders = {} 
        self.last_received_order_no = None # 가장 최근에 체결 통보된 주문번호

        # 키움 API 이벤트 연결
        self.kiwoom_helper.ocx.OnReceiveMsg.connect(self._on_receive_msg)
        self.kiwoom_helper.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data)
        
        logger.info(f"{get_current_time_str()}: TradeManager initialized for account {self.account_number}.")

    def _on_order_timeout(self):
        """주문 응답 타임아웃 처리."""
        if self.order_event_loop.isRunning():
            self.order_event_loop.quit()
        logger.warning("⚠️ 주문 응답 타임아웃 발생.")
        send_telegram_message("⚠️ 주문 응답 타임아웃 발생.")

    def _on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        """
        키움 API 메시지 수신 이벤트 핸들러.
        주문 관련 메시지를 처리하고 주문 응답 이벤트 루프를 종료합니다.
        """
        logger.info(f"📩 메시지 수신: {msg} (화면: {screen_no}, 요청: {rq_name}, TR: {tr_code})")
        
        # 주문 이벤트 루프가 실행 중이면 종료
        # OnReceiveChejanData에서 실제 주문번호를 받으므로, 여기서는 단순히 루프 종료만
        if self.order_event_loop.isRunning():
            self.order_event_loop.quit()

    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        """
        체결 데이터 수신 이벤트 핸들러.
        실시간 체결 정보를 처리하고 포지션을 업데이트합니다.
        """
        logger.info(f"📊 체결 데이터 수신: 구분={gubun}, 항목수={item_cnt}, FID리스트={fid_list}")

        # gubun '0': 접수/체결, '1': 잔고
        if gubun == "0": # 접수/체결 데이터
            order_no = self.kiwoom_helper.ocx.GetChejanData(9203).strip() # 주문번호
            stock_code = self.kiwoom_helper.ocx.GetChejanData(9001).strip() # 종목코드
            stock_name = self.kiwoom_helper.get_stock_name(stock_code) # 종목명
            order_type_str = self.kiwoom_helper.ocx.GetChejanData(912).strip() # 주문구분 (+매수, -매도)
            order_quantity = int(self.kiwoom_helper.ocx.GetChejanData(900).strip()) # 주문수량 (원래 주문 수량)
            executed_quantity = int(self.kiwoom_helper.ocx.GetChejanData(911).strip()) # 체결량
            executed_price = float(self.kiwoom_helper.ocx.GetChejanData(910).strip()) # 체결가
            current_quantity = int(self.kiwoom_helper.ocx.GetChejanData(930).strip()) # 현재 보유수량 (잔고)
            
            # 주문 상태 (접수, 체결, 확인 등)
            order_status = self.kiwoom_helper.ocx.GetChejanData(919).strip() # 주문상태 (접수, 확인, 체결)

            trade_type = ""
            if "+" in order_type_str:
                trade_type = "BUY_FILLED"
            elif "-" in order_type_str:
                trade_type = "SELL_FILLED"
            
            log_message = f"✅ 체결 정보: 주문번호={order_no}, 종목={stock_name}({stock_code}), 구분={order_type_str}, 체결량={executed_quantity}, 체결가={executed_price}, 현재보유={current_quantity}, 상태={order_status}"
            logger.info(log_message)

            # TradeLogger를 통해 체결 내역 기록
            trade_logger.log_trade(
                stock_code=stock_code,
                stock_name=stock_name,
                trade_type=trade_type,
                quantity=executed_quantity,
                price=executed_price,
                order_no=order_no,
                message=f"체결 완료 (체결가: {executed_price}, 상태: {order_status})"
            )
            send_telegram_message(f"✅ 체결 완료: {stock_name}({stock_code}) {executed_quantity}주 @ {executed_price:,}원")

            # MonitorPositions 업데이트
            # 체결 완료 시점에만 포지션 업데이트
            if "체결" in order_status:
                self.monitor_positions.update_position_from_chejan(
                    stock_code=stock_code,
                    new_quantity=current_quantity,
                    purchase_price=executed_price, # 체결가로 매입가 업데이트 (단순화)
                    buy_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S") # 현재 시간으로 업데이트
                )

            # 주문 응답 이벤트 루프 종료 (place_order에서 대기 중인 경우)
            # 가장 최근에 수신된 주문번호를 저장
            self.last_received_order_no = order_no 
            if self.order_event_loop.isRunning():
                self.order_event_loop.quit()

        elif gubun == "1": # 잔고 데이터 (현재는 사용하지 않음, MonitorPositions에서 TR로 관리)
            logger.debug("잔고 데이터 수신 (현재 처리 안함)")
            pass

    def place_order(self, stock_code: str, order_type: int, quantity: int, price: int, order_division: str,
                    retry_attempts: int = 2, retry_delay_sec: int = 3):
        """
        주식 매수/매도 주문을 실행합니다.

        Args:
            stock_code (str): 종목코드
            order_type (int): 주문 유형 (1: 신규매수, 2: 신규매도, 3: 매수취소, 4: 매도취소, 5: 매수정정, 6: 매도정정)
            quantity (int): 주문 수량
            price (int): 주문 가격 (시장가 주문 시 0)
            order_division (str): 거래 구분 (00: 지정가, 03: 시장가 등)
            retry_attempts (int): 주문 실패 시 재시도 횟수
            retry_delay_sec (int): 재시도 간 대기 시간 (초)
        """
        current_time_str = get_current_time_str()
        stock_name = self.kiwoom_helper.get_stock_name(stock_code)
        
        order_type_text = self.ORDER_TYPE_MAP.get(order_type, "알 수 없는 주문")
        order_division_text = self.ORDER_DIVISION_MAP.get(order_division, "알 수 없는 구분")

        # 2. 임시 주문 ID 생성 및 pending_orders에 초기 정보 저장
        temp_order_id = str(uuid.uuid4())
        self.pending_orders[temp_order_id] = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "order_type": order_type_text,
            "quantity": quantity,
            "price": price,
            "order_division": order_division_text,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "REQUESTED", # 초기 상태
            "actual_order_no": None # 실제 주문번호는 나중에 채워짐
        }

        logger.info(f"[{current_time_str}] 🚀 주문 요청: {stock_name}({stock_code}), 유형: {order_type_text}, 수량: {quantity}, 가격: {price:,}원, 구분: {order_division_text} (임시 ID: {temp_order_id})")
        send_telegram_message(f"🚀 주문 요청: {stock_name}({stock_code}) {order_type_text} {quantity}주 @ {price:,}원 ({order_division_text})")

        # TradeLogger를 통해 주문 요청 내역 기록
        trade_logger.log_trade(
            stock_code=stock_code,
            stock_name=stock_name,
            trade_type=f"{order_type_text.replace('신규', '').upper()}_ORDER_REQUEST", # BUY_ORDER_REQUEST, SELL_ORDER_REQUEST
            quantity=quantity,
            price=price,
            order_no=temp_order_id, # 임시 ID를 주문번호로 사용
            message=f"주문 요청 ({order_division_text})"
        )

        for attempt in range(1, retry_attempts + 1):
            try:
                self.last_received_order_no = None # 주문번호 초기화
                self.order_event_loop.processEvents() # 이벤트 루프가 이미 실행 중인 경우를 대비
                self.order_timer.start(30000) # 30초 타임아웃 설정

                order_result_code = self.kiwoom_helper.ocx.SendOrder(
                    rq_name=f"{order_type_text}_req",
                    screen_no="0101", # 주문용 화면번호
                    account_no=self.account_number,
                    order_type=order_type,
                    stock_code=stock_code,
                    quantity=quantity,
                    price=price,
                    trade_type=order_division,
                    org_order_no="" # 신규 주문이므로 공백
                )

                if order_result_code == 0:
                    logger.info(f"✅ 주문 요청 성공: {stock_code}, 수량: {quantity}, 가격: {price}, 구분: {order_division} (재시도 {attempt}/{retry_attempts})")
                    # 주문 응답을 기다림 (OnReceiveMsg 또는 OnReceiveChejanData에서 quit 호출)
                    self.order_event_loop.exec_()
                    self.order_timer.stop() # 타이머 중지

                    if self.last_received_order_no:
                        # 2. pending_orders에 실제 주문번호 업데이트 및 상태 변경
                        self.pending_orders[temp_order_id]["actual_order_no"] = self.last_received_order_no
                        self.pending_orders[temp_order_id]["status"] = "RECEIVED"
                        logger.info(f"✅ 주문번호 수신 성공: {self.last_received_order_no}")
                        return {"status": "success", "message": "Order placed", "order_no": self.last_received_order_no}
                    else:
                        logger.warning(f"⚠️ 주문 요청 성공했으나 주문번호 수신 실패 또는 타임아웃: {stock_code} (재시도 {attempt}/{retry_attempts})")
                        self.pending_orders[temp_order_id]["status"] = "TIMEOUT"
                        # 주문번호를 받지 못했더라도 일단 성공으로 간주하고 모니터링
                        return {"status": "warning", "message": "Order placed but no order_no received (timeout)"}
                else:
                    error_msg = get_error_message(order_result_code)
                    logger.error(f"❌ 주문 요청 실패: {stock_code} - 코드: {order_result_code} ({error_msg}) (재시도 {attempt}/{retry_attempts})")
                    send_telegram_message(f"❌ 주문 실패: {stock_code} - {error_msg}")
                    self.pending_orders[temp_order_id]["status"] = "FAILED"
                    
                    if attempt < retry_attempts:
                        logger.info(f"재시도 중... {retry_delay_sec}초 대기.")
                        time.sleep(retry_delay_sec)
                    else:
                        return {"status": "error", "message": f"Order failed after multiple retries: {error_msg}"}

            except Exception as e:
                logger.error(f"❌ 주문 중 예외 발생: {stock_code} - {e} (재시도 {attempt}/{retry_attempts})", exc_info=True)
                send_telegram_message(f"❌ 주문 중 예외 발생: {stock_code} - {e}")
                self.pending_orders[temp_order_id]["status"] = "EXCEPTION"
                
                if attempt < retry_attempts:
                    logger.info(f"재시도 중... {retry_delay_sec}초 대기.")
                    time.sleep(retry_delay_sec)
                else:
                    return {"status": "error", "message": f"Order processing exception after multiple retries: {e}"}
        
        # 모든 재시도 실패 시
        return {"status": "error", "message": "All order attempts failed."}

