import logging
from PyQt5.QtCore import QEventLoop
from modules.Kiwoom.tr_event_loop import TrEventLoop
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    def __init__(self, ocx, qt_app):
        self.ocx = ocx
        self.qt_app = qt_app
        self.connected_state = 0
        self.tr_event_loop = TrEventLoop()
        self._stock_name_cache = {}  # ✅ 종목명 캐시 추가

        # TR 응답 이벤트 핸들러 연결
        self.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)

        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def connect_kiwoom(self, timeout_ms=10000):
        self.ocx.CommConnect()
        loop = QEventLoop()

        from PyQt5.QtCore import QTimer
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)

        while self.ocx.GetConnectState() == 0 and timer.remainingTime() > 0:
            self.qt_app.processEvents()

        connected = self.ocx.GetConnectState() == 1
        self.connected_state = 1 if connected else 0
        return connected

    def disconnect_kiwoom(self):
        self.ocx.CommTerminate()

    def get_login_info(self, tag):
        return self.ocx.GetLoginInfo(tag)

    def get_stock_name(self, stock_code):
        """
        ✅ 종목명 캐싱 기능 적용
        """
        if stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]

        try:
            name = self.ocx.dynamicCall("GetMasterCodeName(QString)", stock_code)
            if not name:
                logger.warning(f"종목명 조회 실패: {stock_code}")
                return "Unknown"

            self._stock_name_cache[stock_code] = name
            return name
        except Exception as e:
            logger.error(f"종목명 조회 중 오류: {stock_code} - {e}")
            return "Unknown"

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, prev_next, data_len, error_code, message, splm_msg):
        """
        TR 응답 수신 시 호출되는 이벤트 핸들러
        """
        try:
            data = {}
            field_count = self.ocx.GetRepeatCnt(tr_code, rq_name)
            if field_count == 0:
                field_names = ["예수금"]
                for name in field_names:
                    data[name] = self.ocx.GetCommData(tr_code, rq_name, 0, name).strip()
            else:
                for i in range(field_count):
                    item = {}
                    item["종목코드"] = self.ocx.GetCommData(tr_code, rq_name, i, "종목코드").strip()
                    item["보유수량"] = self.ocx.GetCommData(tr_code, rq_name, i, "보유수량").strip()
                    item["평균단가"] = self.ocx.GetCommData(tr_code, rq_name, i, "평균단가").strip()
                    item["현재가"] = self.ocx.GetCommData(tr_code, rq_name, i, "현재가").strip()
                    data[i] = item
        except Exception as e:
            logger.exception(f"❌ TR 응답 처리 중 오류 발생: {e}")
            data = None

        self.tr_event_loop.set_data(data)
