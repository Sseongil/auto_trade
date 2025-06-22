import logging
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    def __init__(self, ocx, app):
        self.ocx = ocx
        self.app = app
        self._connected = False
        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def connect_kiwoom(self):
        logger.info("✅ Kiwoom API 로그인 시도 중...")
        try:
            self.ocx.dynamicCall("CommConnect()")
            self.app.processEvents()

            import time
            for i in range(30):  # 최대 30초 대기
                state = int(self.ocx.dynamicCall("GetConnectState()"))
                if state == 1:
                    self._connected = True
                    logger.info("✅ Kiwoom API 연결 확인 완료.")
                    # 로그인 후 계좌정보 확인
                    accounts = self.get_login_info("ACCNO")
                    logger.info(f"🔐 로그인된 계좌 정보: {accounts}")
                    return True
                time.sleep(1)

            logger.error("❌ Kiwoom API 연결 실패 - 타임아웃")
            return False
        except Exception as e:
            logger.critical(f"❌ Kiwoom 로그인 중 예외 발생: {e}", exc_info=True)
            return False

    def disconnect_kiwoom(self):
        try:
            self.ocx.dynamicCall("CommTerminate()")
            self._connected = False
            logger.info("🔌 Kiwoom API 연결 종료")
        except Exception as e:
            logger.warning(f"❌ Kiwoom API 종료 실패: {e}")

    def get_login_info(self, tag):
        try:
            value = self.ocx.dynamicCall("GetLoginInfo(QString)", [tag])
            logger.info(f"🔎 GetLoginInfo({tag}) => {value}")
            return value
        except Exception as e:
            logger.error(f"❌ GetLoginInfo 호출 실패 - tag: {tag}, 예외: {e}")
            return ""

    def is_connected(self):
        return self._connected
