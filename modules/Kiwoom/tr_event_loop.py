# modules/Kiwoom/tr_event_loop.py

import logging
from PyQt5.QtCore import QEventLoop, QTimer, QObject

logger = logging.getLogger(__name__)

class TrEventLoop(QObject):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TrEventLoop, cls).__new__(cls)
            cls._instance._init_singleton()
        return cls._instance

    def _init_singleton(self):
        self.tr_data_meta = {} # Stores metadata about received TRs
        self.tr_event_loop = QEventLoop()
        self.condition_version_received_flag = False
        self.tr_condition_data = {} # For TR condition search results

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_tr_meta(self, rq_name, tr_code, screen_no):
        """TR 데이터 수신 시 호출되어 메타데이터를 저장하고 이벤트 루프를 종료합니다."""
        key = f"{rq_name}_{tr_code}_{screen_no}"
        self.tr_data_meta[key] = {"received": True} # Mark as received
        logger.debug(f"TR meta received for key: {key}")
        if self.tr_event_loop.isRunning():
            self.tr_event_loop.quit()

    def wait_for_tr_data(self, rq_name, tr_code, screen_no, timeout=10):
        """TR 데이터 요청 후 수신을 기다립니다."""
        key = f"{rq_name}_{tr_code}_{screen_no}"
        self.tr_data_meta[key] = {"received": False} # Reset for new request

        timeout_timer = QTimer()
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(self.tr_event_loop.quit)
        timeout_timer.start(timeout * 1000) # Convert seconds to milliseconds

        self.tr_event_loop.exec_()

        timeout_timer.stop() # Stop the timer once event loop quits

        if self.tr_data_meta[key]["received"]:
            logger.debug(f"TR data signal received for key: {key}")
            return True # Signal received
        else:
            logger.warning(f"TR data for {key} not signaled within timeout.")
            return False

    def set_condition_version_received(self, status):
        """조건식 버전 수신 여부를 설정하고 이벤트 루프를 종료합니다."""
        self.condition_version_received_flag = status
        if self.tr_event_loop.isRunning():
            self.tr_event_loop.quit()

    def wait_for_condition_version(self, timeout=10):
        """조건식 버전 수신을 기다립니다."""
        self.condition_version_received_flag = False
        timeout_timer = QTimer()
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(self.tr_event_loop.quit)
        timeout_timer.start(timeout * 1000)

        self.tr_event_loop.exec_()
        timeout_timer.stop()
        return self.condition_version_received_flag

    def set_tr_condition_data(self, stock_code, condition_name, condition_index, search_type, event_type, current_cnt, total_cnt):
        """TR 조건 검색 결과 수신 시 호출되어 데이터를 저장하고 이벤트 루프를 종료합니다."""
        key = f"condition_{condition_name}_{condition_index}"
        self.tr_condition_data[key] = {
            "stock_code": stock_code,
            "event_type": event_type,
            "current_cnt": current_cnt,
            "total_cnt": total_cnt
        }
        logger.debug(f"TR condition data received for key: {key}")
        if self.tr_event_loop.isRunning():
            self.tr_event_loop.quit()

    def wait_for_tr_condition_data(self, condition_name, condition_index, timeout=10):
        """TR 조건 검색 결과 수신을 기다립니다."""
        key = f"condition_{condition_name}_{condition_index}"
        self.tr_condition_data[key] = None # Reset for new request

        timeout_timer = QTimer()
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(self.tr_event_loop.quit)
        timeout_timer.start(timeout * 1000)

        self.tr_event_loop.exec_()
        timeout_timer.stop()

        return self.tr_condition_data.get(key)
