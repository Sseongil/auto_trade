# modules/Kiwoom/kiwoom_query_helper.py

import time
import logging
import pandas as pd
from PyQt5.QtCore import QObject, QEventLoop, QTimer
from PyQt5.QAxContainer import QAxWidget
from modules.common.config import REALTIME_FID_LIST

logger = logging.getLogger(__name__)

class KiwoomQueryHelper(QObject):
    def __init__(self, kiwoom_ocx: QAxWidget, app):
        super().__init__()
        self.kiwoom = kiwoom_ocx
        self.app = app
        self.filtered_df = pd.DataFrame()
        self.tr_event_loop = None
        self._setup_signal_slots()

    def _setup_signal_slots(self):
        self.kiwoom.OnEventConnect.connect(self._on_event_connect)
        self.kiwoom.OnReceiveTrData.connect(self._on_receive_tr_data)

    def connect_kiwoom(self, timeout_ms=10000):
        logger.info("📡 Kiwoom OpenAPI+ 서버 연결 시도 중...")
        self.kiwoom.dynamicCall("CommConnect()")

        loop = QEventLoop()
        self.tr_event_loop = loop
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec_()

        if self.kiwoom.dynamicCall("GetConnectState()") == 1:
            logger.info("✅ Kiwoom OpenAPI+ 서버 연결 성공")
            return True
        else:
            logger.error("❌ Kiwoom OpenAPI+ 서버 연결 실패")
            return False

    def _on_event_connect(self, err_code):
        if self.tr_event_loop and self.tr_event_loop.isRunning():
            self.tr_event_loop.quit()

    def _on_receive_tr_data(self, screen_no, rqname, trcode, recordname, prev_next):
        logger.info(f"📩 TR 데이터 수신 - rqname: {rqname}, trcode: {trcode}, screen_no: {screen_no}")
        if self.tr_event_loop and self.tr_event_loop.isRunning():
            self.tr_event_loop.quit()

    def SetRealReg(self, screen_no, code_list, fid_list, real_type):
        try:
            self.kiwoom.dynamicCall("SetRealReg(QString, QString, QString, QString)",
                                    screen_no, code_list, fid_list, real_type)
            logger.info(f"✅ SetRealReg 호출 성공: 화면번호 {screen_no}, 종목 {code_list}")
        except Exception as e:
            logger.error(f"❌ SetRealReg 호출 실패: {e}", exc_info=True)

    def SetRealRemove(self, screen_no, code):
        try:
            self.kiwoom.dynamicCall("SetRealRemove(QString, QString)", screen_no, code)
            logger.info(f"✅ SetRealRemove 호출 성공: 화면번호 {screen_no}, 종목 {code}")
        except Exception as e:
            logger.error(f"❌ SetRealRemove 호출 실패: {e}", exc_info=True)
