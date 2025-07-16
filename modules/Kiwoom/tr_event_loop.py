# modules/Kiwoom/tr_event_loop.py

from PyQt5.QtCore import QEventLoop, QTimer
import threading
import logging

logger = logging.getLogger(__name__)

class TrEventLoop:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TrEventLoop, cls).__new__(cls)
                cls._instance._init_once()
        return cls._instance

    def _init_once(self):
        self.loop = QEventLoop()
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.loop.quit)
        self.data = {}
        self.tr_code_waiting = None
        self.rq_name_waiting = None
        # 조건식 버전 수신을 위한 QEventLoop와 플래그
        self.condition_version_loop = QEventLoop()
        self.condition_version_received_flag = False
        self.condition_version_timer = QTimer()
        self.condition_version_timer.setSingleShot(True)
        self.condition_version_timer.timeout.connect(self.condition_version_loop.quit)


    @classmethod
    def instance(cls):
        return cls.__new__(cls)

    def reset(self):
        self.data = {}
        self.tr_code_waiting = None
        self.rq_name_waiting = None

    def set_tr_data(self, rq_name, tr_code, s_prev_next):
        """OnReceiveTrData 이벤트에서 호출되어 데이터를 저장하고 루프를 종료합니다."""
        self.data = {"rq_name": rq_name, "tr_code": tr_code, "s_prev_next": s_prev_next}
        if self.loop.isRunning():
            self.loop.quit()

    def set_condition_version_received(self, status: bool):
        """조건식 버전 수신 완료 상태를 설정하고 대기 중인 루프를 종료합니다."""
        self.condition_version_received_flag = status
        if self.condition_version_loop.isRunning():
            self.condition_version_loop.quit()
        logger.info(f"✅ TrEventLoop: 조건식 버전 수신 플래그 설정 완료: {status}.")

    def wait_for_condition_version(self, timeout_ms: int = 10000) -> bool:
        """조건식 버전 수신을 기다립니다."""
        if self.condition_version_received_flag:
            logger.info("✅ TrEventLoop: 조건식 버전이 이미 수신되었습니다.")
            return True

        logger.info(f"TrEventLoop: 조건식 버전 수신 대기 중 (최대 {timeout_ms}ms)...")
        self.condition_version_timer.start(timeout_ms)
        self.condition_version_loop.exec_() # QEventLoop를 사용하여 GUI 스레드에서 대기
        self.condition_version_timer.stop()

        if self.condition_version_received_flag:
            logger.info("✅ TrEventLoop: 조건식 버전 수신 확인.")
            return True
        else:
            logger.warning("⚠️ TrEventLoop: 조건식 버전 수신 타임아웃.")
            return False

    def wait(self, timeout_ms=10000):
        """TR 응답을 기다립니다."""
        self.timer.start(timeout_ms)
        self.loop.exec_()
        self.timer.stop()
        return self.data is not None and not self.data.get("error")

    def get_data(self):
        return self.data
