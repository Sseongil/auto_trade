# modules/Kiwoom/tr_event_loop.py

from PyQt5.QtCore import QEventLoop, QTimer

class TrEventLoop:
    """
    키움 API의 TR 요청 후 응답을 기다리기 위한 PyQt 이벤트 루프 래퍼.
    TR 응답 데이터는 set_data()로 수신하며, get_data()로 접근한다.
    """

    def __init__(self):
        self.loop = QEventLoop()
        self.data = None

    def reset(self):
        """이벤트 루프 초기화 (TR 요청 전에 호출 필요)"""
        self.data = None
        self.loop = QEventLoop()

    def wait(self, timeout_ms=10000):
        """TR 응답을 대기한다. timeout 초과 시 종료."""
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self.loop.quit)
        timer.start(timeout_ms)
        self.loop.exec_()
        return self.data is not None

    def set_data(self, data):
        """TR 응답 수신 시 호출 - 데이터 저장 및 루프 종료"""
        self.data = data
        if self.loop.isRunning():
            self.loop.quit()

    def get_data(self):
        """응답 데이터를 반환"""
        return self.data
