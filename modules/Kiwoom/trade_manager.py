# modules/Kiwoom/trade_manager.py

import logging
import time
from datetime import datetime, time as dt_time
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication # QApplication import 추가

logger = logging.getLogger(__name__)

class TradeManager:
    def __init__(self, kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number, trade_logger):
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.monitor_positions = monitor_positions
        self.account_number = account_number
        self.trade_logger = trade_logger # TradeLogger 인스턴스 저장
        self.pending_orders = {} # {주문번호: {"종목코드": "...", "주문유형": "매수/매도", ...}}

        self._set_event_handlers()
        logger.info("TradeManager initialized.")

    def _set_event_handlers(self):
        # OnReceiveMsg 이벤트 핸들러 연결
        # 수정된 부분: self.kiwoom_helper.kiwoom -> self.kiwoom_helper.ocx
        self.kiwoom_helper.ocx.OnReceiveMsg.connect(self._on_receive_msg)
        self.kiwoom_helper.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        self.kiwoom_helper.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data)
        logger.info("TradeManager event handlers set.")

    def _on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        """
        TR 요청에 대한 메시지를 수신하는 이벤트
        """
        logger.info(f"[OnReceiveMsg] ScreenNo: {screen_no}, RqName: {rq_name}, TrCode: {tr_code}, Msg: {msg}")
        # 여기에 메시지 처리 로직 추가 (예: 주문 성공/실패 알림)

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name,
                            data_len, err_code, msg, srv_item_cnt):
        """
        TR 데이터를 수신하는 이벤트
        """
        logger.info(f"[OnReceiveTrData] ScreenNo: {screen_no}, RqName: {rq_name}, TrCode: {tr_code}")
        # KiwoomTrRequest 인스턴스에 TR 데이터 전달
        self.kiwoom_tr_request.on_receive_tr_data(screen_no, rq_name, tr_code, record_name,
                                                  data_len, err_code, msg, srv_item_cnt)

    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        """
        체결, 잔고 변경, 파생 잔고 등 실시간 체결 데이터를 수신하는 이벤트
        """
        logger.info(f"[OnReceiveChejanData] Gubun: {gubun}, ItemCnt: {item_cnt}, FidList: {fid_list}")
        # gubun: 0 - 주문체결, 1 - 잔고, 3 - 특이신호
        if gubun == "0": # 주문체결통보
            self._process_order_chejan(fid_list)
        elif gubun == "1": # 잔고통보
            self._process_balance_chejan(fid_list)
        # MonitorPositions에 체결 데이터 전달
        self.monitor_positions.on_receive_chejan_data(gubun, item_cnt, fid_list)


    def _process_order_chejan(self, fid_list):
        """
        주문체결통보를 처리하고 거래 로그를 기록
        """
        order_no = self.kiwoom_helper.get_chejan_data(9203) # 주문번호
        stock_code = self.kiwoom_helper.get_chejan_data(9001) # 종목코드
        stock_name = self.kiwoom_helper.get_chejan_data(302) # 종목명
        order_status = self.kiwoom_helper.get_chejan_data(919) # 주문상태 (접수, 확인, 체결)
        order_type = self.kiwoom_helper.get_chejan_data(906) # 매도/매수
        order_quantity = int(self.kiwoom_helper.get_chejan_data(900)) # 주문수량
        order_price = int(self.kiwoom_helper.get_chejan_data(901)) # 주문가격
        contract_quantity = int(self.kiwoom_helper.get_chejan_data(910)) # 체결량
        contract_price = int(self.kiwoom_helper.get_chejan_data(911)) # 체결가격
        current_balance = int(self.kiwoom_helper.get_chejan_data(953)) # 당일 잔고

        trade_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = {
            "시간": trade_time,
            "종목코드": stock_code.strip(),
            "종목명": stock_name.strip(),
            "주문번호": order_no.strip(),
            "주문유형": order_type.strip(),
            "주문수량": order_quantity,
            "주문가격": order_price,
            "체결량": contract_quantity,
            "체결가격": contract_price,
            "주문상태": order_status.strip(),
            "당일잔고": current_balance
        }
        logger.info(f"💰 체결 데이터: {log_entry}")
        self.trade_logger.add_trade_log(log_entry)

        # pending_orders 업데이트 (필요시)
        if order_no in self.pending_orders:
            if order_status == "체결":
                del self.pending_orders[order_no]
            # 부분 체결 등의 추가 로직 구현 가능

    def _process_balance_chejan(self, fid_list):
        """
        잔고통보를 처리
        """
        # 잔고통보 관련 FID 값들을 사용하여 잔고 정보 업데이트
        # MonitorPositions에서 이 정보를 처리하므로 여기서는 간단히 로깅만
        account_balance = self.kiwoom_helper.get_chejan_data(953) # 계좌평가잔고총액
        deposit = self.kiwoom_helper.get_chejan_data(952) # 예수금
        logger.info(f"📊 잔고통보 수신 - 계좌평가잔고총액: {account_balance}, 예수금: {deposit}")

    def send_order(self, stock_code, order_type, quantity, price, order_gubun="00", org_order_no=""):
        """
        주문을 전송하는 함수
        :param stock_code: 종목코드
        :param order_type: "매수" 또는 "매도"
        :param quantity: 수량
        :param price: 가격
        :param order_gubun: 거래구분 (00: 지정가, 03: 시장가 등)
        :param org_order_no: 원주문번호 (정정/취소 시 사용)
        :return: 주문번호 (성공 시), None (실패 시)
        """
        screen_no = self.kiwoom_helper.generate_screen_no()
        # 매수/매도 구분
        if order_type == "매수":
            s_order_type = 1 # 신규매수
        elif order_type == "매도":
            s_order_type = 2 # 신규매도
        else:
            logger.error(f"❌ 잘못된 주문 유형: {order_type}")
            return None

        # SendOrder 함수 호출
        order_result = self.kiwoom_helper.send_order(
            rq_name="주식주문",
            screen_no=screen_no,
            account_no=self.account_number,
            order_type=s_order_type, # 1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
            stock_code=stock_code,
            quantity=quantity,
            price=price,
            trade_type=order_gubun, # 00:지정가, 03:시장가
            org_order_no=org_order_no
        )

        if order_result:
            order_no = order_result # SendOrder는 성공 시 주문번호 반환
            self.pending_orders[order_no] = {
                "종목코드": stock_code,
                "주문유형": order_type,
                "수량": quantity,
                "가격": price,
                "주문시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            logger.info(f"✅ 주문 전송 성공: 종목={stock_code}, 유형={order_type}, 수량={quantity}, 가격={price}, 주문번호={order_no}")
            return order_no
        else:
            logger.error(f"❌ 주문 전송 실패: 종목={stock_code}, 유형={order_type}, 수량={quantity}, 가격={price}")
            return None

    def buy_stock(self, stock_code, quantity, price, order_gubun="00"):
        """ 주식 매수 """
        logger.info(f"🛒 매수 요청: 종목={stock_code}, 수량={quantity}, 가격={price}")
        return self.send_order(stock_code, "매수", quantity, price, order_gubun)

    def sell_stock(self, stock_code, quantity, price, order_gubun="00"):
        """ 주식 매도 """
        logger.info(f"💰 매도 요청: 종목={stock_code}, 수량={quantity}, 가격={price}")
        return self.send_order(stock_code, "매도", quantity, price, order_gubun)

    def cancel_order(self, order_no, stock_code, quantity):
        """ 주문 취소 """
        logger.info(f"🚫 주문 취소 요청: 주문번호={order_no}, 종목={stock_code}, 수량={quantity}")
        return self.kiwoom_helper.send_order(
            rq_name="주식주문",
            screen_no=self.kiwoom_helper.generate_screen_no(),
            account_no=self.account_number,
            order_type=3, # 3:매수취소, 4:매도취소
            stock_code=stock_code,
            quantity=quantity,
            price=0, # 취소 시 가격은 0
            trade_type="00",
            org_order_no=order_no
        )

    def correct_order(self, order_no, stock_code, order_type, new_quantity, new_price):
        """ 주문 정정 """
        logger.info(f"✏️ 주문 정정 요청: 주문번호={order_no}, 종목={stock_code}, 유형={order_type}, 새수량={new_quantity}, 새가격={new_price}")
        s_order_type = 5 if order_type == "매수" else 6 # 5:매수정정, 6:매도정정
        return self.kiwoom_helper.send_order(
            rq_name="주식주문",
            screen_no=self.kiwoom_helper.generate_screen_no(),
            account_no=self.account_number,
            order_type=s_order_type,
            stock_code=stock_code,
            quantity=new_quantity,
            price=new_price,
            trade_type="00",
            org_order_no=order_no
        )

    def get_market_open_time(self):
        """ 시장 개장 시간 (예: 9시) """
        return dt_time(9, 0, 0)

    def get_market_close_time(self):
        """ 시장 마감 시간 (예: 15시 30분) """
        return dt_time(15, 30, 0)

    def is_market_open(self):
        """ 현재 시간이 시장 개장 시간과 마감 시간 사이인지 확인 """
        now = datetime.now().time()
        market_open = self.get_market_open_time()
        market_close = self.get_market_close_time()
        return market_open <= now <= market_close

    def get_current_price(self, stock_code):
        """
        현재가를 조회하는 함수 (OPT10001 사용)
        :param stock_code: 종목코드
        :return: 현재가 (int) 또는 None
        """
        logger.info(f"🔍 현재가 조회 요청: 종목코드 {stock_code}")
        tr_data = self.kiwoom_tr_request.request_tr_data(
            tr_code="OPT10001",
            rq_name="주식기본정보요청",
            input_values={"종목코드": stock_code},
            output_key="현재가"
        )
        if tr_data:
            try:
                # 현재가는 음수일 수 있으므로 절대값으로 변환 후 int로 변환
                current_price = int(abs(int(tr_data)))
                logger.info(f"✅ 종목 {stock_code} 현재가: {current_price}")
                return current_price
            except ValueError as e:
                logger.error(f"❌ 현재가 데이터 변환 오류: {tr_data}, {e}")
                return None
        else:
            logger.warning(f"⚠️ 종목 {stock_code} 현재가 조회 실패.")
            return None

