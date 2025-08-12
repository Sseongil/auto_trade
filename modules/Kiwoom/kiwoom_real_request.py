import logging
from PyQt5.QtCore import QObject, pyqtSignal

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def safe_int(value):
    try:
        return int(value.strip())
    except Exception:
        return 0


class KiwoomRealRequest(QObject):
    """
    키움 OpenAPI를 통해 실시간 데이터를 요청하고 처리하는 클래스.
    """
    real_data_updated = pyqtSignal(str, dict)

    def __init__(self, api_caller):
        super().__init__()
        self.kiwoom_ocx = api_caller.kiwoom_ocx  # 수정 완료
        self.real_data = {}
        self._connect_signals()

    def _connect_signals(self):
        """키움 OCX의 실시간 데이터 시그널을 연결합니다."""
        self.kiwoom_ocx.OnReceiveRealData.connect(self.on_receive_real_data)
        logger.info("✅ KiwoomRealRequest 시그널 연결 완료.")

    def on_receive_real_data(self, code, real_type, real_data):
        """실시간 데이터를 수신했을 때 호출되는 슬롯."""
        if real_type == "주식체결":
            current_price = self.kiwoom_ocx.GetCommRealData(code, 10)  # 현재가
            trading_volume = self.kiwoom_ocx.GetCommRealData(code, 15)  # 거래량

            self.real_data[code] = {
                "current_price": safe_int(current_price),
                "trading_volume": safe_int(trading_volume)
            }

            logger.info(f"📈 실시간 데이터 수신: 종목={code}, 현재가={self.real_data[code]['current_price']}")
            self.real_data_updated.emit(code, self.real_data[code])

    def set_real_data(self, screen_no, code_list, fid_list, real_type):
        """
        실시간 데이터 수신을 등록합니다.
        Args:
            screen_no (str): 화면 번호.
            code_list (str): 종목코드 목록 (세미콜론으로 구분).
            fid_list (str): FID 목록 (세미콜론으로 구분).
            real_type (str): 0: 등록, 1: 해제
        """
        logger.info(f"🔔 실시간 데이터 등록/해제 요청: 화면번호={screen_no}, 종목={code_list}, 타입={real_type}")
        self.kiwoom_ocx.SetRealReg(screen_no, code_list, fid_list, real_type)


# === 테스트 코드 ===
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import pyqtSignal
    import sys

    class DummyOCX(QObject):
        OnReceiveRealData = pyqtSignal(str, str, str)

        def GetCommRealData(self, code, fid):
            dummy_data = {
                10: "81200",  # 현재가
                15: "15420"   # 거래량
            }
            return dummy_data.get(fid, "0")

        def SetRealReg(self, screen_no, code_list, fid_list, real_type):
            logger.info(f"[Mock] SetRealReg 호출됨 - 화면번호={screen_no}, 종목={code_list}, 타입={real_type}")
            # 수동 테스트용 이벤트 트리거는 외부에서 호출

    class DummyKiwoomApiCaller(QObject):
        def __init__(self):
            super().__init__()
            self.kiwoom_ocx = DummyOCX()

    def test_real_data():
        app = QApplication(sys.argv)
        dummy_caller = DummyKiwoomApiCaller()
        real_request = KiwoomRealRequest(dummy_caller)

        def on_updated(code, data):
            logger.info(f"✅ 테스트 통과: 실시간 데이터 수신됨 - 종목={code}, 데이터={data}")

        real_request.real_data_updated.connect(on_updated)

        # 실시간 등록 테스트
        real_request.set_real_data("0002", "005930", "10;15", "0")

        # 수동으로 시그널 발행
        dummy_caller.kiwoom_ocx.OnReceiveRealData.emit("005930", "주식체결", "")

        app.quit()

    test_real_data()
