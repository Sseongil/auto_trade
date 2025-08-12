import logging
from PyQt5.QtCore import QObject, QEventLoop, pyqtSignal

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def safe_int(value):
    try:
        return int(value.strip())
    except Exception:
        return 0


class KiwoomDashboardController(QObject):
    """
    키움증권 API를 사용하여 대시보드에 필요한 정보를 관리하는 클래스.
    """
    
    account_info_received = pyqtSignal()
    tr_data_received = pyqtSignal()
    real_data_received = pyqtSignal()

    def __init__(self, kiwoom_api_caller):
        super().__init__()
        self.kiwoom_api_caller = kiwoom_api_caller
        
        self.event_loop = QEventLoop()
        
        self.account_numbers = []
        self.current_account_number = None
        self.account_balance = {}  
        self.holdings = {}         

        self._connect_signals()

    def _connect_signals(self):
        self.kiwoom_api_caller.kiwoom_ocx.OnReceiveTrData.connect(self.on_receive_tr_data)
        self.kiwoom_api_caller.kiwoom_ocx.OnReceiveRealData.connect(self.on_receive_real_data)

        self.account_info_received.connect(self.event_loop.quit)
        self.tr_data_received.connect(self.event_loop.quit)
        self.real_data_received.connect(self.pass_event)

        logger.info("✅ KiwoomDashboardController 시그널 연결 완료.")

    def get_account_numbers(self):
        accounts_string = self.kiwoom_api_caller.get_login_info("ACCLIST")
        self.account_numbers = accounts_string.split(";")[:-1]

        if self.account_numbers:
            self.current_account_number = self.account_numbers[0]
            logger.info(f"✅ 로그인된 계좌 목록: {self.account_numbers}, 현재 계좌: {self.current_account_number}")
        else:
            logger.warning("⚠️ 로그인된 계좌가 없습니다.")

        return self.account_numbers

    def on_receive_tr_data(self, screen_no, tr_name, record_name, is_last):
        logger.info(f"💰 TR 데이터 수신: TR명={tr_name}, 화면번호={screen_no}")
        
        if tr_name == "opw00018":
            total_buy_price = self.kiwoom_api_caller.get_comm_data(tr_name, record_name, 0, "총매입금액")
            total_eval_profit_loss = self.kiwoom_api_caller.get_comm_data(tr_name, record_name, 0, "총평가손익금액")
            
            self.account_balance = {
                "total_buy_price": safe_int(total_buy_price),
                "total_eval_profit_loss": safe_int(total_eval_profit_loss)
            }

            self.holdings = {}
            repeat_count = self.kiwoom_api_caller.get_repeat_cnt(tr_name, record_name)
            for i in range(repeat_count):
                code = self.kiwoom_api_caller.get_comm_data(tr_name, record_name, i, "종목코드").strip()
                name = self.kiwoom_api_caller.get_comm_data(tr_name, record_name, i, "종목명").strip()
                quantity = safe_int(self.kiwoom_api_caller.get_comm_data(tr_name, record_name, i, "보유수량"))
                buy_price = safe_int(self.kiwoom_api_caller.get_comm_data(tr_name, record_name, i, "매입가"))

                self.holdings[code] = {
                    "name": name,
                    "quantity": quantity,
                    "buy_price": buy_price
                }

            logger.info(f"✅ 보유 종목 수신 완료: {len(self.holdings)}개")
        
        self.tr_data_received.emit()

    def request_account_balance(self):
        if not self.current_account_number:
            logger.error("❌ 계좌번호가 설정되지 않았습니다.")
            return

        logger.info(f"🔍 계좌 잔고 정보 요청: 계좌번호={self.current_account_number}")
        
        self.kiwoom_api_caller.set_input_value("계좌번호", self.current_account_number)
        self.kiwoom_api_caller.set_input_value("비밀번호", "")
        self.kiwoom_api_caller.set_input_value("상장구분", "0")
        self.kiwoom_api_caller.set_input_value("조회구분", "1")
        
        self.kiwoom_api_caller.comm_rq_data("opw00018", "opw00018", 0, "0001")

        self.event_loop.exec_()
        
        return self.account_balance, self.holdings

    def set_real_data(self, screen_no, code):
        logger.info(f"🔔 실시간 등록: 화면번호={screen_no}, 종목코드={code}")
        self.kiwoom_api_caller.set_real_reg(screen_no, code, "20;10;11;12;13;14;15", "0")

    def on_receive_real_data(self, code, real_type, real_data):
        if real_type == "주식체결":
            current_price = self.kiwoom_api_caller.get_comm_real_data(code, 10)
            logger.info(f"📈 실시간 체결: 종목={code}, 현재가={current_price}")
        self.real_data_received.emit()

    def pass_event(self):
        pass


# === 테스트 ===
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import pyqtSignal
    import sys

    class DummyKiwoomApiCaller(QObject):
        # 시그널은 클래스 변수로 선언해야 작동
        class KiwoomOCX(QObject):
            OnReceiveTrData = pyqtSignal(str, str, str, int)
            OnReceiveRealData = pyqtSignal(str, str, str)
        
        def __init__(self):
            super().__init__()
            self.kiwoom_ocx = self.KiwoomOCX()

        def get_login_info(self, tag):
            return "1234567890;"

        def set_input_value(self, id, value):
            pass

        def comm_rq_data(self, tr_name, tr_code, prev_next, screen_no):
            self.kiwoom_ocx.OnReceiveTrData.emit(screen_no, tr_name, tr_code, 0)

        def get_comm_data(self, tr_code, record_name, index, item_name):
            dummy = {
                "총매입금액": "10000000",
                "총평가손익금액": "500000",
                "종목코드": "005930",
                "종목명": "삼성전자",
                "보유수량": "10",
                "매입가": "80000"
            }
            return dummy.get(item_name, "")

        def get_repeat_cnt(self, tr_code, record_name):
            return 1

        def set_real_reg(self, screen_no, code_list, fid_list, real_type):
            pass

        def get_comm_real_data(self, code, fid):
            return "81000"

    app = QApplication(sys.argv)

    dummy_api = DummyKiwoomApiCaller()
    controller = KiwoomDashboardController(dummy_api)

    accounts = controller.get_account_numbers()
    logger.info(f"🧪 계좌: {accounts}")

    balance, holdings = controller.request_account_balance()
    logger.info(f"🧪 잔고: {balance}")
    logger.info(f"🧪 보유 종목: {holdings}")

    if holdings:
        first_code = list(holdings.keys())[0]
        controller.set_real_data("0002", first_code)

    app.quit()
