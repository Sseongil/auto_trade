# modules/Kiwoom/trade_manager.py

import logging
import time
from datetime import datetime

from PyQt5.QtCore import QEventLoop, QTimer # 💡 QEventLoop와 QTimer 임포트

from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
from modules.trade_logger import TradeLogger # 💡 TradeLogger 임포트

logger = logging.getLogger(__name__)
trade_logger = TradeLogger() # 매매 로그 기록을 위한 TradeLogger 인스턴스 생성

class TradeManager:
    # 💡 monitor_positions 인자가 __init__에 추가되었습니다.
    def __init__(self, kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number):
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.monitor_positions = monitor_positions # 💡 MonitorPositions 인스턴스 저장
        self.account_number = account_number
        
        self.order_event_loop = QEventLoop()
        self.order_timer = QTimer()
        self.order_timer.setSingleShot(True)
        self.order_timer.timeout.connect(self._on_order_timeout)

        # 💡 주문 및 체결 관련 정보 저장
        self.last_order_no = None
        self.pending_orders = {} # {order_no: {'stock_code': '...', 'order_type': 'BUY/SELL', 'quantity': X, ...}}
        self.chejan_data = {} # 최신 체결 정보 저장

        # Kiwoom API의 OnReceiveMsg와 OnReceiveChejanData 이벤트를 연결
        self.kiwoom_helper.ocx.OnReceiveMsg.connect(self._on_receive_msg)
        self.kiwoom_helper.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data)
        
        logger.info(f"{get_current_time_str()}: TradeManager initialized for account {self.account_number}.")

    def _on_order_timeout(self):
        """주문 요청 타임아웃 발생 시 호출되는 콜백."""
        if self.order_event_loop.isRunning():
            logger.error(f"[{get_current_time_str()}]: ❌ 주문 요청 타임아웃 발생 (마지막 주문번호: {self.last_order_no})")
            # 타임아웃 시 해당 주문을 실패 처리
            if self.last_order_no and self.last_order_no in self.pending_orders:
                del self.pending_orders[self.last_order_no] # 대기 목록에서 제거
            self.order_event_loop.exit() # 이벤트 루프 강제 종료

    def _on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        """API로부터의 메시지를 수신했을 때 호출됩니다 (주로 주문 확인/오류 메시지)."""
        logger.info(f"[{get_current_time_str()}]: [API 메시지] [{rq_name}] {msg} (화면: {screen_no})")
        # 주문 관련 메시지일 경우 처리 (예: 주문 접수 성공, 주문 오류 등)
        if "주문이 접수되었습니다." in msg or "주문확인" in msg:
            # 주문 성공 메시지이므로, 이벤트 루프를 종료하여 place_order 함수를 계속 진행
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
        
        if gubun == "0": # 접수/체결 데이터
            # 주요 FID 값들을 가져옵니다.
            # FID 9201: 계좌번호, 9203: 주문번호, 9001: 종목코드, 911: 종목명
            # FID 906: 주문구분 (+매수/-매도), 900: 주문수량, 901: 주문가격
            # FID 904: 체결량, 905: 체결가
            # FID 910: 원주문번호
            
            order_no = self.kiwoom_helper.ocx.GetChejanData(9203).strip() # 주문번호
            stock_code = self.kiwoom_helper.ocx.GetChejanData(9001).strip() # 종목코드
            stock_name = self.kiwoom_helper.ocx.GetChejanData(911).strip() # 종목명
            order_type_str = self.kiwoom_helper.ocx.GetChejanData(906).strip() # 주문구분 (+매수/-매도)
            order_qty = abs(int(self.kiwoom_helper.ocx.GetChejanData(900).strip())) # 주문수량
            order_price = abs(int(self.kiwoom_helper.ocx.GetChejanData(901).strip())) # 주문가격
            executed_qty = abs(int(self.kiwoom_helper.ocx.GetChejanData(904).strip())) # 체결량
            executed_price = abs(int(self.kiwoom_helper.ocx.GetChejanData(905).strip())) # 체결가
            current_total_qty = abs(int(self.kiwoom_helper.ocx.GetChejanData(930).strip())) # 현재 보유수량

            # 주문 상태 확인 (접수, 체결, 확인, 취소 등)
            order_status = self.kiwoom_helper.ocx.GetChejanData(919).strip() # 주문상태 (접수, 확인, 체결, 취소 등)
            
            # 최종 체결 여부 (완전히 체결되면 pending_orders에서 제거)
            is_fully_executed = (current_total_qty == 0 and "매도" in order_type_str) or \
                                (current_total_qty >= order_qty and "매수" in order_type_str and order_qty > 0 and executed_qty > 0)
            
            logger.info(f"[{get_current_time_str()}] 체결 알림: {stock_name}({stock_code}) - 주문번호: {order_no}, 구분: {order_type_str}, 체결량: {executed_qty}, 체결가: {executed_price}, 상태: {order_status}")

            # 매수/매도 구분에 따른 처리
            if "매수" in order_type_str:
                trade_type = "매수"
                pnl_amount = 0.0
                pnl_pct = 0.0
                # MonitorPositions 업데이트
                self.monitor_positions.update_position_from_chejan(stock_code, current_total_qty, executed_price, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            elif "매도" in order_type_str:
                trade_type = "매도"
                # 매도 시 손익 계산 (MonitorPositions에서 매입가를 가져와서 계산)
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
                    pnl_pct = 0.0 # 포지션 정보 없으면 손익 계산 불가

                # MonitorPositions 업데이트 (보유수량 갱신 또는 삭제)
                self.monitor_positions.update_position_from_chejan(stock_code, current_total_qty, executed_price) # 매도 시에는 executed_price가 중요
            else: # 기타 (정정, 취소 등)
                trade_type = "기타"
                pnl_amount = 0.0
                pnl_pct = 0.0

            # 계좌 예수금 업데이트 (TradeManager가 직접 TR 요청)
            account_info = self.kiwoom_tr_request.request_account_info(self.account_number)
            account_balance_after_trade = account_info.get("예수금", 0)

            # 거래 로그 기록
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
                strategy_name="AutoTrade" # 또는 세부 전략명 (예: BuySignal, TakeProfit, StopLoss)
            )

            # 주문번호가 pending_orders에 있다면 업데이트 (부분 체결/전량 체결)
            if order_no in self.pending_orders:
                # TODO: 부분 체결 시 잔량 관리 로직 추가
                if is_fully_executed:
                    del self.pending_orders[order_no]
                    logger.info(f"주문 {order_no} ({stock_name}) 완전 체결 완료. 대기 목록에서 제거.")
        
        elif gubun == "1": # 잔고 데이터 (계좌에 새 종목 편입/편출 또는 잔고 변화)
            # 여기서는 별도의 처리 없이 로그만 남깁니다.
            # MonitorPositions는 자체적으로 계좌 상태를 동기화합니다.
            logger.debug(f"잔고 데이터 수신 (Gubun=1): {fid_list}")

        # 주문 이벤트 루프가 실행 중이라면 (place_order에서 대기 중인 경우) 종료
        if self.order_timer.isActive():
            self.order_timer.stop()
        if self.order_event_loop.isRunning():
            self.order_event_loop.exit()

    def place_order(self, stock_code, order_type, quantity, price, order_division, screen_no="0101"):
        """
        주문(매수/매도)을 실행합니다.
        Args:
            stock_code (str): 종목코드
            order_type (int): 주문 유형 (1: 매수, 2: 매도, 3: 정정, 4: 취소)
            quantity (int): 주문 수량
            price (int): 주문 가격 (지정가에만 사용, 시장가는 0)
            order_division (str): 거래구분 (00: 지정가, 03: 시장가 등)
            screen_no (str): 화면번호 (기본값 "0101" 또는 고유하게 생성)
        Returns:
            dict: 주문 결과 (성공/실패, 메시지, 주문번호)
        """
        if self.kiwoom_helper.connected_state != 0:
            logger.error("❌ Kiwoom API에 연결되지 않아 주문을 보낼 수 없습니다.")
            send_telegram_message("❌ 주문 실패: 키움 API 미연결.")
            return {"status": "error", "message": "API Not Connected"}

        if quantity <= 0:
            logger.warning(f"⚠️ 주문 수량 0 또는 음수입니다. 주문을 실행하지 않습니다. 종목: {stock_code}")
            return {"status": "error", "message": "Invalid quantity"}

        # CommRqData 대신 SendOrder 함수 사용
        # SendOrder(sRQName, sScreenNo, sAccNo, nOrderType, sCode, nQty, nPrice, sHogaGb, sOrgOrderNo)
        rq_name = "stock_order_req"
        
        # 이전 주문 정보 초기화 및 타이머 시작
        self.last_order_no = None
        self.order_timer.start(30000) # 30초 타임아웃
        
        try:
            # 💡 sHogaGb에 대한 설명 (호가구분)
            # 00 : 지정가 
            # 03 : 시장가
            # 05 : 조건부지정가
            # 06 : 최유리 지정가
            # 07 : 최우선 지정가
            # 10 : 지정가IOC
            # 13 : 시장가IOC
            # 16 : 최유리IOC
            # 20 : 지정가FOK
            # 23 : 시장가FOK
            # 26 : 최유리FOK
            # 61 : 장전 시간외
            # 62 : 장후 시간외
            # 81 : 시간외 단일가
            # 82 : 시간외 단일가 (20% 상하한)

            order_result_code = self.kiwoom_helper.ocx.SendOrder(
                rq_name, # 요청명 (사용자 정의)
                screen_no, # 화면번호
                self.account_number, # 계좌번호
                order_type, # 주문 유형 (1: 매수, 2: 매도, 3: 정정, 4: 취소)
                stock_code, # 종목코드
                quantity, # 주문 수량
                price, # 주문 가격 (시장가면 0)
                order_division, # 호가구분 (지정가, 시장가 등)
                "" # 원주문번호 (정정/취소 시 사용)
            )

            if order_result_code == 0:
                logger.info(f"✅ 주문 요청 성공: {stock_code}, 타입: {order_type}, 수량: {quantity}, 가격: {price}, 호가: {order_division}")
                # 주문 성공 시 OnReceiveMsg 또는 OnReceiveChejanData에서 실제 주문번호를 받을 때까지 대기
                # _on_receive_msg에서 주문 접수 메시지 받으면 event_loop.exit() 호출
                self.order_event_loop.exec_() # 이벤트 루프 대기

                if self.last_order_no: # OnReceiveChejanData에서 주문번호를 받았다면
                    self.pending_orders[self.last_order_no] = {
                        "stock_code": stock_code,
                        "order_type": order_type,
                        "quantity": quantity,
                        "price": price,
                        "order_division": order_division,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    return {"status": "success", "message": "Order placed", "order_no": self.last_order_no}
                else: # 주문 접수 메시지나 체결 메시지를 받지 못하고 타임아웃/종료된 경우
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

