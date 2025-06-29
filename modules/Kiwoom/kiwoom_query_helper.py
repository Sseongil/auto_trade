import pythoncom
import time
import pandas as pd
import logging
from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from modules.error_codes import get_error_message

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    def __init__(self, kiwoom_ocx, pyqt_app):
        self.kiwoom = kiwoom_ocx
        self.app = pyqt_app
        self.filtered_df = pd.DataFrame()

    def connect_kiwoom(self, timeout_ms=10000):
        self.login_event_loop = QEventLoop()
        self.kiwoom.OnEventConnect.connect(self._on_event_connect)
        self.kiwoom.dynamicCall("CommConnect()")

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self.login_event_loop.quit)
        timer.start(timeout_ms)

        self.login_event_loop.exec_()
        timer.stop()

        if self.kiwoom.dynamicCall("GetConnectState()") == 1:
            logger.info("✅ 키움 API 로그인 성공")
            return True
        else:
            logger.critical("❌ 키움 API 로그인 실패")
            return False

    def _on_event_connect(self, err_code):
        msg = get_error_message(err_code)
        logger.info(f"[로그인 이벤트] 코드: {err_code}, 메시지: {msg}")
        if hasattr(self, 'login_event_loop'):
            self.login_event_loop.quit()

    def SetRealReg(self, screen_no, code_list, fid_list, real_type):
        self.kiwoom.dynamicCall("SetRealReg(QString, QString, QString, QString)",
                                 screen_no, code_list, fid_list, real_type)
        logger.info(f"📡 SetRealReg 호출: 화면번호={screen_no}, 종목={code_list}, FID={fid_list}")

    def SetRealRemove(self, screen_no, code_list):
        self.kiwoom.dynamicCall("SetRealRemove(QString, QString)", screen_no, code_list)
        logger.info(f"📡 SetRealRemove 호출: 화면번호={screen_no}, 종목={code_list}")
