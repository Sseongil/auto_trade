# modules/Kiwoom/trade_manager.py

import logging
import time
from PyQt5.QtCore import QEventLoop, QTimer
from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message # 텔레그램 알림을 위해 임포트
from modules.trade_logger import TradeLogger # 💡 TradeLogger 임포트

logger = logging.getLogger(__name__)

class TradeManager:
    def __init__(self, kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number):
        self.kiwoom = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.monitor_positions = monitor_positions
        self.account_number = account_number
        self.order_event_loop = QEventLoop()
        self.order_timer = QTimer()
        self.order_timer.setSingleShot(True)
        self.order_timer.timeout.connect(self._on_order_timeout)
        
        self.order_result = None # 주문 결과 저장
        self.order_rq_name = None # 주문 요청명
        self.order_no = None # 주문 번호

        self.kiwoom.ocx.OnReceiveMsg.connect(self._on_receive_msg)
        self.kiwoom.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data)

        # 💡 TradeLogger 인스턴스 생성
        self.trade_logger = TradeLogger()

        logger.info(f"{get_current_time_str()}: TradeManager initialized.")

    def _on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        """키움으로부터 메시지를 수신했을 때 호출됩니다."""
        logger.info(f"[{get_current_time_str()}]: [API 메시지] [{rq_name}] {msg}")
        # 주문 관련 메시지 처리 (예: 주문 성공/실패)
        if rq_name == self.order_rq_name:
            if "주문이 전송되었습니다" in msg or "주문 접수" in msg:
                self.order_result = {"status": "success", "message": msg}
            elif "실패" in msg or "오류" in msg:
                self.order_result = {"status": "fail", "message": msg}
            
            if self.order_event_loop.isRunning():
                self.order_event_loop.exit()

    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        """
        체결 데이터 수신 이벤트 핸들러
        'gubun' 0: 주문접수, 1: 주문체결, 2: 주문취소/정정
        """
        # logger.debug(f"체결 데이터 수신. Gubun: {gubun}, FID List: {fid_list}")
        
        # 체결 (gubun == '1') 또는 접수 후 바로 체결되는 경우
        if gubun == '1' or gubun == '0': # '0'은 접수인데, 바로 체결되는 경우가 많으므로 함께 처리
            order_no = self.kiwoom.ocx.GetChejanData('920') # 주문번호
            stock_code = self.kiwoom.ocx.GetChejanData('9001').strip() # 종목코드 (A제거 필요)
            stock_name = self.kiwoom.ocx.GetChejanData('302').strip() # 종목명
            order_status = self.kiwoom.ocx.GetChejanData('919').strip() # 주문상태 (접수, 확인, 체결 등)
            order_type_str = self.kiwoom.ocx.GetChejanData('901').strip() # 매매구분 (매도, 매수)
            contract_qty = int(self.kiwoom.ocx.GetChejanData('902').strip()) # 체결수량
            contract_price = int(self.kiwoom.ocx.GetChejanData('900').strip()) # 체결가격
            current_qty_in_account = int(self.kiwoom.ocx.GetChejanData('930').strip()) # 계좌에 있는 현재 보유수량
            
            # 'A' 접두사 제거 (예: 'A005930' -> '005930')
            if stock_code.startswith('A'):
                stock_code = stock_code[1:]

            logger.info(f"[{get_current_time_str()}]: [체결] 주문번호: {order_no}, 종목: {stock_name}({stock_code}), 매매: {order_type_str}, 체결수량: {contract_qty}, 체결가: {contract_price}")

            # 매수/매도 후 포지션 업데이트
            if "매수" in order_type_str:
                self.monitor_positions.update_position(stock_code, contract_qty, contract_price)
                # 💡 매매 로그 기록 (매수)
                self.trade_logger.log_trade(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    trade_type="매수",
                    order_price=None, # 시장가 매수이므로 주문가는 None
                    executed_price=contract_price,
                    quantity=contract_qty,
                    strategy_name="수동/조건검색" # 추후 조건검색식 매수 로직과 연결
                )
                send_telegram_message(f"✅ 매수 체결: {stock_name}({stock_code}) | 수량: {contract_qty}주 | 체결가: {contract_price:,}원")

            elif "매도" in order_type_str:
                # 매도의 경우, 수익률 계산하여 로그에 추가
                # 현재 포지션 정보를 가져옴 (업데이트 전)
                current_pos = self.monitor_positions.get_position(stock_code)
                purchase_price = current_pos.get('purchase_price', 0) if current_pos else 0
                
                pnl_amount = (contract_price - purchase_price) * contract_qty
                pnl_pct = (pnl_amount / (purchase_price * contract_qty) * 100) if (purchase_price * contract_qty) != 0 else 0

                self.monitor_positions.update_position(stock_code, -contract_qty, contract_price) # 음수로 전달하여 매도 처리
                
                # 💡 매매 로그 기록 (매도)
                self.trade_logger.log_trade(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    trade_type="매도", # 구체적인 전략명은 strategy에서 전달하도록 보완 필요
                    order_price=None, # 시장가 매도이므로 주문가는 None
                    executed_price=contract_price,
                    quantity=contract_qty,
                    pnl_amount=pnl_amount,
                    pnl_pct=pnl_pct,
                    strategy_name="익절/손절/트레일링" # 추후 구체적인 전략명과 연결
                )
                send_telegram_message(f"📉 매도 체결: {stock_name}({stock_code}) | 수량: {contract_qty}주 | 체결가: {contract_price:,}원 | PnL: {pnl_pct:.2f}%")
            
            # 주문 번호가 일치하면 이벤트 루프 종료 (여러 체결에 대해 한 번만 종료)
            if self.order_no == order_no and self.order_event_loop.isRunning():
                self.order_event_loop.exit()

    def _on_order_timeout(self):
        """주문 요청 타임아웃 발생 시 호출됩니다."""
        if self.order_event_loop.isRunning():
            logger.error(f"[{get_current_time_str()}]: ❌ 주문 요청 실패 - 타임아웃 ({self.order_rq_name})")
            self.order_result = {"status": "timeout", "message": "주문 요청 타임아웃"}
            send_telegram_message(f"🚨 주문 실패: {self.order_rq_name} 타임아웃 발생.")
            self.order_event_loop.exit()

    def place_order(self, stock_code, order_type, quantity, price, order_unit="03", timeout_ms=30000):
        """
        주문 실행 함수
        Args:
            stock_code (str): 종목코드
            order_type (int): 주문유형 (1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정)
            quantity (int): 주문수량
            price (int): 주문가격 (시장가/최유리/지정가 등에 따라 0 또는 가격)
            order_unit (str): 거래구분 ("00":지정가, "03":시장가 등)
            timeout_ms (int): 주문 결과 대기 타임아웃 (밀리초)
        Returns:
            dict: 주문 결과 (status, message)
        """
        self.order_result = None
        self.order_rq_name = f"Order_{stock_code}_{int(time.time()*1000)}" # 고유한 요청명 생성
        screen_no = "4000" # 주문용 화면번호 (중복 피해야 함)

        # CommKwRqData(계좌번호, 전문, 주문유형, 종목코드, 주문수량, 주문가격, 거래구분, 원주문번호, 화면번호)
        # 키움 API는 매수/매도 주문 시 '0' 또는 None 가격을 받지 않음. 시장가 매매 시에도 0을 넣어야 함.
        # 따라서 시장가 주문일 경우 price를 0으로 명시적으로 설정.
        actual_price = price if order_unit != "03" else 0 # 시장가 주문 시 가격 0

        # 주문 번호 획득을 위해 CommRqData 대신 SendOrder를 사용.
        # SendOrder(rq_name, screen_no, account_no, order_type, stock_code, quantity, price, order_unit, original_order_no)
        # sRQName: 사용자 구분명
        # sScreenNo: 화면번호
        # sAccNo: 계좌번호
        # nOrderType: 주문유형 (1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정)
        # sCode: 종목코드
        # nQty: 주문수량
        # nPrice: 주문가격
        # sHogaGb: 거래구분 (00:지정가, 03:시장가)
        # sOrgOrderNo: 원주문번호 (정정/취소시 사용)
        
        # 시장가 주문 시 가격은 0
        result_code = self.kiwoom.ocx.SendOrder(
            self.order_rq_name, 
            screen_no, 
            self.account_number, 
            order_type, 
            stock_code, 
            quantity, 
            actual_price, # 시장가인 경우 0
            order_unit, 
            "" # 원주문번호 (신규 주문이므로 공백)
        )
        
        if result_code == 0:
            logger.info(f"[{get_current_time_str()}]: [✅] 주문 요청 성공 - 종목: {stock_code}, 유형: {order_type}, 수량: {quantity}, 가격: {actual_price}, 거래구분: {order_unit}")
            self.order_timer.start(timeout_ms)
            self.order_event_loop.exec_() # 체결/메시지 수신까지 대기
            return self.order_result if self.order_result else {"status": "fail", "message": "응답 없음"}
        else:
            error_message = self._get_error_message(result_code)
            logger.error(f"❌ 주문 요청 실패: {result_code} ({error_message}) - 종목: {stock_code}, 유형: {order_type}, 수량: {quantity}, 가격: {actual_price}")
            send_telegram_message(f"🚨 주문 요청 실패: {stock_code} - {error_message}")
            return {"status": "fail", "message": error_message}
            
    def _get_error_message(self, err_code):
        error_map = {
            0: "정상 처리",
            -10: "미접속",
            -100: "사용자정보교환실패",
            -101: "서버접속실패",
            -102: "버전처리실패",
            -103: "비정상적인 모듈 호출",
            -104: "종목코드 없음",
            -105: "계좌증거금율 오류",
            -106: "통신연결종료",
            -107: "사용자정보 없음",
            -108: "주문 가격 오류",
            -109: "주문 수량 오류",
            -110: "실시간 등록 오류",
            -111: "실시간 해제 오류",
            -112: "데이터 없음",
            -113: "API 미설정",
            -200: "전문 송수신 실패", 
            -201: "입력값 오류",
            -202: "계좌정보 오류 (계좌번호 또는 비밀번호 관련 문제일 가능성 높음)", 
            -300: "알 수 없는 오류 (API 내부 오류, 요청 제한 등 복합적인 원인)", 
            -999: "타임아웃 발생 (내부 정의)" 
        }
        return error_map.get(err_code, "알 수 없는 오류")
