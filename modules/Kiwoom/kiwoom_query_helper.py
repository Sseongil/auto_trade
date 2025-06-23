# modules/Kiwoom/kiwoom_query_helper.py

import sys
import logging
from PyQt5.QtCore import QEventLoop, QTimer 
from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    def __init__(self, ocx_instance, pyqt_app_instance):
        self.ocx = ocx_instance 
        self.pyqt_app = pyqt_app_instance 
        
        self.connected_state = -1 
        
        self.connect_event_loop = QEventLoop() 
        self.connect_timer = QTimer() 
        self.connect_timer.setSingleShot(True) 
        self.connect_timer.timeout.connect(self._on_connect_timeout) 
        
        self.ocx.OnEventConnect.connect(self._on_event_connect)
        
        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def _on_event_connect(self, err_code):
        self.connected_state = err_code 
        if err_code == 0:
            logger.info(f"[{get_current_time_str()}]: [✅] 로그인 성공")
        else:
            logger.error(f"[{get_current_time_str()}]: [❌] 로그인 실패 (에러 코드: {err_code})")
        
        if self.connect_timer.isActive():
            self.connect_timer.stop()

        if self.connect_event_loop.isRunning():
            self.connect_event_loop.exit()

    def connect_kiwoom(self, timeout_ms=30000):
        if self.ocx.dynamicCall("GetConnectState()") == 1: 
            logger.info("✅ 키움 API 이미 연결됨.")
            self.connected_state = 0 
            return True

        logger.info("✅ 키움 API 로그인 시도 중...")
        self.ocx.dynamicCall("CommConnect()")
        
        self.connect_timer.start(timeout_ms)
        
        self.connect_event_loop.exec_()
        
        if self.connected_state == 0: 
            return True
        else:
            logger.critical(f"❌ Kiwoom API 연결 실패 (에러 코드: {self.connected_state} 또는 타임아웃 발생)")
            return False

    def _on_connect_timeout(self):
        if self.connect_event_loop.isRunning(): 
            logger.error(f"[{get_current_time_str()}]: ❌ Kiwoom API 연결 실패 - 타임아웃 ({self.connect_timer.interval()}ms)")
            self.connected_state = -999 
            self.connect_event_loop.exit()

    def disconnect_kiwoom(self):
        if self.ocx.dynamicCall("GetConnectState()") == 1: 
            logger.info("🔌 Kiwoom API 연결 종료 시도...") 
            self.ocx.dynamicCall("CommTerminate()") 
            self.connected_state = -1 
            logger.info("🔌 Kiwoom API 연결 종료 완료.")
        else:
            logger.info("🔌 이미 연결되지 않은 상태입니다.")

    def get_login_info(self, tag):
        return self.ocx.dynamicCall("GetLoginInfo(QString)", tag)

    def get_stock_name(self, stock_code):
        name = self.ocx.dynamicCall("GetMasterCodeName(QString)", stock_code)
        if not name:
            logger.warning(f"종목명 조회 실패: {stock_code}")
            return "Unknown"
        return name

    def CommGetData(self, tr_code, record_name, item_name, index):
        return self.ocx.CommGetData(tr_code, record_name, index, item_name)

    def GetRepeatCnt(self, tr_code, record_name):
        return self.ocx.GetRepeatCnt(tr_code, record_name)

