# modules/Kiwoom/kiwoom_query_helper.py

import time
import logging
from PyQt5.QtCore import QEventLoop

from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    def __init__(self, ocx, app):
        self.ocx = ocx  # QAxWidget 인스턴스 (백그라운드 스레드에서 생성됨)
        self.app = app  # QApplication 인스턴스
        self.login_event_loop = QEventLoop()

        # 이벤트 슬롯 연결
        self.ocx.OnEventConnect.connect(self._on_login)
        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def _on_login(self, err_code):
        """로그인 이벤트 핸들러"""
        if err_code == 0:
            logger.info("[✅] 로그인 성공")
        else:
            logger.error(f"[❌] 로그인 실패 - 코드: {err_code}")
        self.login_event_loop.quit()

    def connect_kiwoom(self):
        """
        로그인 요청 및 로그인 완료 대기
        Returns: True if login successful, False otherwise
        """
        if self.ocx.dynamicCall("GetConnectState()") == 0:
            logger.info("✅ 키움 API 로그인 시도 중...")
            self.ocx.dynamicCall("CommConnect()")
            self.login_event_loop.exec_()
            time.sleep(1.0)  # 로그인 직후 대기
        else:
            logger.info("✅ 키움 API 이미 연결됨.")

        return self.ocx.dynamicCall("GetConnectState()") == 1

    def disconnect_kiwoom(self):
        self.ocx.dynamicCall("CommTerminate()")
        logger.info("🔌 연결 종료 (별도 지원 없음)")

    def get_login_info(self, tag):
        """키움 OpenAPI+ 로그인 정보 조회"""
        try:
            value = self.ocx.dynamicCall("GetLoginInfo(QString)", tag)
            logger.debug(f"[GetLoginInfo] {tag}: {value}")
            return value
        except Exception as e:
            logger.warning(f"[GetLoginInfo 예외] {tag} - {e}")
            return None
