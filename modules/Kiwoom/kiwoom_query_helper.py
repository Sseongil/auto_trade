# C:\Users\user\stock_auto\modules\Kiwoom\kiwoom_query_helper.py

from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QEventLoop
import sys
import logging
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    def __init__(self):
        self.app = QApplication(sys.argv)  # GUI 이벤트 루프 필요
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")

        # 로그인 상태
        self.login_loop = QEventLoop()
        self.login_success = False

        # 이벤트 핸들러 연결
        self.ocx.OnEventConnect.connect(self._on_login)

    def _on_login(self, err_code):
        if err_code == 0:
            logger.info("[✅] 로그인 성공")
            self.login_success = True
        else:
            logger.error(f"[❌] 로그인 실패 - 에러 코드: {err_code}")
        self.login_loop.quit()

    def connect_kiwoom(self):
        logger.info("✅ 키움 API 로그인 시도 중...")
        self.ocx.dynamicCall("CommConnect()")
        self.login_loop.exec_()  # 로그인 응답 대기

        return self.login_success

    def get_account_info(self):
        acc_no = self.ocx.dynamicCall("GetLoginInfo(QString)", "ACCNO")
        user_id = self.ocx.dynamicCall("GetLoginInfo(QString)", "USER_ID")
        user_name = self.ocx.dynamicCall("GetLoginInfo(QString)", "USER_NAME")
        return {
            "계좌번호": acc_no.strip().split(';')[0],
            "사용자ID": user_id.strip(),
            "사용자명": user_name.strip()
        }

    def get_code_list_by_market(self, market):
        data = self.ocx.dynamicCall("GetCodeListByMarket(QString)", market)
        return data.split(';')[:-1]

    def get_master_code_name(self, code):
        return self.ocx.dynamicCall("GetMasterCodeName(QString)", code)

    def get_login_info(self, tag):
        return self.ocx.dynamicCall("GetLoginInfo(QString)", tag)

    def disconnect_kiwoom(self):
        logger.info("🔌 연결 종료 (별도 지원 없음)")
