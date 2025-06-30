import logging
from PyQt5.QtCore import QObject
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class RealTimeWatcher(QObject):
    def __init__(self, kiwoom_helper, strategy_executor):
        super().__init__()
        self.kiwoom_helper = kiwoom_helper
        self.strategy_executor = strategy_executor
        self.is_running = False

    def start(self):
        if self.is_running:
            logger.warning("⚠️ 실시간 감시 이미 실행 중입니다.")
            return

        self.is_running = True
        logger.info(f"{get_current_time_str()} [RealTimeWatcher] 실시간 감시 시작")

        self.kiwoom_helper.real_time_signal.connect(self.on_real_time_event)

    def stop(self):
        if not self.is_running:
            logger.warning("⚠️ 실시간 감시가 이미 중지 상태입니다.")
            return

        self.is_running = False
        logger.info(f"{get_current_time_str()} [RealTimeWatcher] 실시간 감시 종료")

        self.kiwoom_helper.real_time_signal.disconnect(self.on_real_time_event)

    def on_real_time_event(self, data):
        if not self.is_running:
            return

        try:
            logger.debug(f"[RealTimeWatcher] 실시간 데이터 수신: {data}")
            self.strategy_executor.handle_real_time_data(data)
        except Exception as e:
            logger.error(f"실시간 이벤트 처리 중 오류: {e}", exc_info=True)
