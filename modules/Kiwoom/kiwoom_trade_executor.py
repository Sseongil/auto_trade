import logging
from PyQt5.QtCore import QObject, QEventLoop, pyqtSignal
from modules.Kiwoom.kiwoom_api_caller import KiwoomApiCaller # KiwoomApiCaller 클래스를 임포트합니다.

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KiwoomTradeExecutor(QObject):
    """
    키움증권 API를 통해 주식 매수/매도 주문을 실행하고 관리하는 클래스.
    """

    # 주문 접수 및 체결 완료를 알리는 시그널
    order_result_received = pyqtSignal()
    # 계좌 잔고 및 체결 데이터를 받을 때 발생하는 시그널
    chejan_data_received = pyqtSignal()

    def __init__(self, kiwoom_api_caller, account_password):
        """
        초기화 메서드.

        Args:
            kiwoom_api_caller (KiwoomApiCaller): Kiwoom API 헬퍼 클래스 인스턴스.
            account_password (str): 키움증권 계좌 비밀번호.
        """
        super().__init__()
        self.kiwoom_api_caller = kiwoom_api_caller
        self.account_password = account_password

        # 주문 처리 시 사용하는 이벤트 루프
        self.order_event_loop = QEventLoop()
        
        # 주문 결과 및 체결 데이터를 저장할 변수
        self.order_number = None
        self.order_status = None
        self.chejan_data = {}

        # 시그널 슬롯 연결
        self._connect_signals()
        logger.info("✅ KiwoomTradeExecutor 초기화 및 시그널 연결 완료.")

    def _connect_signals(self):
        """키움 OCX의 시그널과 클래스의 메서드를 연결합니다."""
        # 주문 접수 시 발생하는 OnReceiveMsg 시그널 연결
        self.kiwoom_api_caller.kiwoom_ocx.OnReceiveMsg.connect(self.on_receive_msg)
        # 주문 체결, 잔고 변경 시 발생하는 OnReceiveChejanData 시그널 연결
        self.kiwoom_api_caller.kiwoom_ocx.OnReceiveChejanData.connect(self.on_receive_chejan_data)
        
        # 내부 시그널 연결
        self.order_result_received.connect(self.order_event_loop.quit)
        self.chejan_data_received.connect(self.chejan_event_loop.quit if hasattr(self, 'chejan_event_loop') else self.pass_event)

    def on_receive_msg(self, screen_no, tr_name, msg_type, msg):
        """
        주문 접수, 오류 발생 등 메시지를 받을 때 호출되는 슬롯.
        """
        if tr_name == "OPT10074": # 매수/매도 주문 TR
            logger.info(f"💌 주문 관련 메시지 수신: {msg}")
            # 메시지에서 주문번호를 파싱하여 저장
            # 키움 API 메시지 형식에 따라 파싱 로직을 구현해야 합니다.
            # 예시: 주문번호, 주문상태 등
            # self.order_number = parsed_order_number
            # self.order_status = parsed_order_status
            self.order_result_received.emit()

    def on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        """
        체결 데이터, 잔고 변경 시 호출되는 슬롯.
        """
        if gubun == "0": # 접수/체결
            logger.info(f"💰 주문 접수/체결 데이터 수신. 체결구분: {gubun}")
            # FID 목록에 따라 데이터를 파싱하여 저장
            # 예: 주문번호, 종목코드, 주문수량, 체결수량 등
            for fid in fid_list.split(';'):
                if fid:
                    value = self.kiwoom_api_caller.kiwoom_ocx.GetChejanData(int(fid))
                    self.chejan_data[fid] = value
            
            logger.info(f"수신된 체결 데이터: {self.chejan_data}")
            self.chejan_data_received.emit()
            
        elif gubun == "1": # 잔고
            logger.info(f"💼 잔고 변경 데이터 수신. 체결구분: {gubun}")
            # 잔고 관련 FID 목록을 파싱하여 저장
            # self.chejan_data = ...
            self.chejan_data_received.emit()

    def send_order(self, screen_no, account_no, order_type, code, qty, price, hoga_gb, org_order_no=""):
        """
        주문 전송.
        
        Args:
            screen_no (str): 화면번호.
            account_no (str): 계좌번호.
            order_type (int): 주문유형 (1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정).
            code (str): 종목코드.
            qty (int): 주문수량.
            price (int): 주문가격.
            hoga_gb (str): 거래구분(01:시장가, 03:지정가 등).
            org_order_no (str): 원주문번호.
        """
        logger.info(f"🚀 주문 전송 시작: {account_no} 계좌, 종목={code}, 수량={qty}, 가격={price}")
        self.kiwoom_api_caller.send_order(
            screen_no, account_no, order_type, code, qty, price, hoga_gb, org_order_no
        )
        
        # 주문 결과가 수신될 때까지 대기
        self.order_event_loop.exec_()
        
        # 주문 결과 반환
        return self.order_number, self.order_status

    def buy_stock(self, screen_no, account_no, code, qty, price, hoga_gb="03"):
        """
        주식 매수 주문을 보냅니다.
        """
        order_type = 1 # 신규매수
        return self.send_order(screen_no, account_no, order_type, code, qty, price, hoga_gb)

    def sell_stock(self, screen_no, account_no, code, qty, price, hoga_gb="03"):
        """
        주식 매도 주문을 보냅니다.
        """
        order_type = 2 # 신규매도
        return self.send_order(screen_no, account_no, order_type, code, qty, price, hoga_gb)

    def pass_event(self):
        """
        더미 이벤트 메서드.
        """
        pass

if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    
    # 이 예제를 실행하려면 실제 Kiwoom API 환경이 필요합니다.
    # 여기서는 더미 클래스를 사용하여 동작 방식만 보여줍니다.
    
    class DummyKiwoomApiCaller(QObject):
        # OnReceiveMsg 시그널과 OnReceiveChejanData 시그널을 가상으로 정의합니다.
        kiwoom_ocx = QObject()
        kiwoom_ocx.OnReceiveMsg = pyqtSignal(str, str, str, str)
        kiwoom_ocx.OnReceiveChejanData = pyqtSignal(str, int, str)
        
        def send_order(self, screen_no, account_no, order_type, code, qty, price, hoga_gb, org_order_no=""):
            logger.info("Mock API: send_order 호출됨")
            # 가상으로 주문 성공 메시지를 보냅니다.
            self.kiwoom_ocx.OnReceiveMsg.emit("0001", "OPT10074", "주문메시지", "주문번호: 1234567890")
            # 가상으로 체결 데이터를 보냅니다.
            self.kiwoom_ocx.OnReceiveChejanData.emit("0", 1, "9201;9203;")

    app = QApplication(sys.argv)
    
    dummy_api_caller = DummyKiwoomApiCaller()
    executor = KiwoomTradeExecutor(dummy_api_caller, "dummy_password")
    
    # 더미 매수 주문 테스트
    logger.info("--- 매수 주문 테스트 시작 ---")
    order_num, status = executor.buy_stock("0001", "dummy_account", "005930", 10, 80000)
    logger.info(f"주문 번호: {order_num}, 주문 상태: {status}")
    
    app.quit()
