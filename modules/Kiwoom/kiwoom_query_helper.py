# modules/Kiwoom/kiwoom_query_helper.py

import sys
import logging
# QApplication과 QAxWidget은 이제 local_api_server에서 직접 관리하여 주입받습니다.
# 따라서 이 파일 내에서는 이들을 직접 임포트하지 않습니다.
# from PyQt5.QtWidgets import QApplication
# from PyQt5.QAxContainer import QAxWidget
from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    # __init__ 메서드는 ocx_instance (QAxWidget)와 pyqt_app_instance (QApplication)를 인자로 받습니다.
    def __init__(self, ocx_instance, pyqt_app_instance):
        self.ocx = ocx_instance # 외부에서 생성된 QAxWidget 인스턴스를 받습니다.
        self.pyqt_app = pyqt_app_instance # 외부에서 생성된 QApplication 인스턴스를 받습니다.
        
        self.connected_state = -1 # 초기 상태: 미접속 (0: 연결 성공)
        
        # OnEventConnect 이벤트 핸들러 연결
        self.ocx.OnEventConnect.connect(self._on_event_connect)
        
        # 로그인 이벤트 루프는 주입받은 pyqt_app 인스턴스를 사용합니다.
        self.login_event_loop = self.pyqt_app 
        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def _on_event_connect(self, err_code):
        """
        키움 API 로그인 연결 상태 변경 시 호출되는 이벤트 핸들러.
        """
        self.connected_state = err_code # 연결 상태 업데이트
        if err_code == 0:
            logger.info(f"[{get_current_time_str()}]: [✅] 로그인 성공")
        else:
            logger.error(f"[{get_current_time_str()}]: [❌] 로그인 실패 (에러 코드: {err_code})")
        
        # 로그인 이벤트 루프가 실행 중이라면 종료 (블로킹 해제)
        if self.login_event_loop.isRunning():
            self.login_event_loop.exit()

    def connect_kiwoom(self):
        """
        키움증권 API에 연결을 시도합니다.
        """
        if self.ocx.dynamicCall("GetConnectState()") == 0:
            logger.info("✅ 키움 API 이미 연결됨.")
            self.connected_state = 0 # 이미 연결되어 있으면 상태를 0으로 설정
            return True

        logger.info("✅ 키움 API 로그인 시도 중...")
        # CommConnect() 호출 (로그인 시도)
        self.ocx.dynamicCall("CommConnect()")
        
        # 로그인 성공/실패 응답을 기다리기 위해 이벤트 루프 실행
        # _on_event_connect에서 이벤트 루프를 종료합니다.
        self.login_event_loop.exec_()
        
        if self.connected_state == 0: # 로그인 성공
            return True
        else:
            logger.critical(f"❌ Kiwoom API 연결 실패 (에러 코드: {self.connected_state})")
            return False

    def disconnect_kiwoom(self):
        """
        키움증권 API 연결을 종료합니다.
        """
        if self.ocx.dynamicCall("GetConnectState()") == 1: # 연결되어 있다면
            logger.info("🔌 연결 종료 (별도 지원 없음)")
            self.connected_state = -1 # 상태 업데이트
        else:
            logger.info("🔌 이미 연결되지 않은 상태입니다.")

    def get_login_info(self, tag):
        """
        로그인 정보를 요청합니다 (예: "ACCNO" for 계좌번호).
        """
        return self.ocx.dynamicCall("GetLoginInfo(QString)", tag)

    def get_stock_name(self, stock_code):
        """종목 코드를 이용해 종목명을 가져옵니다."""
        name = self.ocx.dynamicCall("GetMasterCodeName(QString)", stock_code)
        if not name:
            logger.warning(f"종목명 조회 실패: {stock_code}")
            return "Unknown"
        return name
