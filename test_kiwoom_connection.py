# test_kiwoom_connection.py

import sys
import time
import logging
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QEventLoop, QTimer

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KiwoomTestApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kiwoom API 연결 테스트")
        self.setGeometry(100, 100, 400, 200)

        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.ocx.OnEventConnect.connect(self._on_event_connect)

        self.status_label = QLabel("Kiwoom API 연결 상태: 대기 중...")
        self.connect_button = QPushButton("Kiwoom 연결 시도")
        self.connect_button.clicked.connect(self.start_connection_test)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(self.connect_button)
        self.setLayout(layout)

        self.connection_loop = QEventLoop()

    def start_connection_test(self):
        self.status_label.setText("Kiwoom API 연결 요청 중...")
        self.connect_button.setEnabled(False)

        # ActiveX 컨트롤 유효성 검사
        try:
            # 간단한 dynamicCall을 시도하여 컨트롤이 유효한지 확인
            self.ocx.dynamicCall("GetConnectState()") 
            logger.info("✅ Kiwoom ActiveX 컨트롤 유효성 확인 성공.")
        except Exception as e:
            self.status_label.setText(f"❌ ActiveX 컨트롤 오류: {e}\n(키움 OpenAPI+ 재설치 필요)")
            logger.critical(f"❌ Kiwoom ActiveX 컨트롤 초기화 실패 또는 유효하지 않음: {e}")
            self.connect_button.setEnabled(True)
            return

        # CommConnect() 호출
        logger.info("✅ CommConnect() 요청 시도 (로그인 창 대기).")
        self.ocx.dynamicCall("CommConnect()") # 반환 값과 무관하게 이벤트 루프 시작

        QTimer.singleShot(60000, self.connection_loop.quit) # 60초 타임아웃 (충분히 길게)
        self.connection_loop.exec_() # 로그인 이벤트 대기

        if self.ocx.dynamicCall("GetConnectState()") == 1: # 1: 연결됨
            self.status_label.setText("✅ Kiwoom API 연결 성공!")
            logger.info("✅ Kiwoom API 연결 성공!")
        else:
            self.status_label.setText("❌ Kiwoom API 연결 실패 또는 타임아웃.")
            logger.error("❌ Kiwoom API 연결 실패 또는 타임아웃.")
        
        self.connect_button.setEnabled(True)

    def _on_event_connect(self, err_code):
        """CommConnect() 결과 이벤트."""
        if err_code == 0:
            logger.info("✅ 로그인 성공 이벤트 수신.")
        else:
            logger.error(f"❌ 로그인 실패 이벤트 수신. 오류 코드: {err_code}")
        
        if self.connection_loop.isRunning():
            self.connection_loop.quit() # 이벤트 루프 종료

if __name__ == "__main__":
    # COM 초기화 (메인 스레드에서)
    import pythoncom
    pythoncom.CoInitialize()

    app = QApplication(sys.argv)
    test_app = KiwoomTestApp()
    test_app.show()
    sys.exit(app.exec_())
