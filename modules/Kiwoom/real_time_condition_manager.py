# modules/Kiwoom/real_time_condition_manager.py

import pandas as pd
import logging
from PyQt5.QtCore import QObject, QTimer, QEventLoop, pyqtSignal
from datetime import datetime
import time

from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
from modules.Kiwoom.tr_event_loop import TrEventLoop # TrEventLoop 임포트 추가

logger = logging.getLogger(__name__)

class RealTimeConditionManager(QObject):
    # 조건식에 편입/이탈된 종목을 외부에 알리는 시그널
    # (stock_code, event_type "I"/"D", condition_name)
    condition_change_signal = pyqtSignal(str, str, str)

    def __init__(self, kiwoom_helper):
        super().__init__()
        self.kiwoom_helper = kiwoom_helper
        self.is_monitoring = False
        self.condition_name = None
        self.condition_index = None
        self.condition_screen_no = None
        self.currently_passing_stocks = {} # {stock_code: stock_name}
        self.tr_event_loop = TrEventLoop.instance() # TrEventLoop 인스턴스 가져오기

        # KiwoomQueryHelper의 실시간 조건검색 시그널 연결
        self.kiwoom_helper.real_condition_signal.connect(self._on_receive_real_condition)
        logger.info(f"{get_current_time_str()}: RealTimeConditionManager initialized.")

    def start_monitoring(self, condition_name: str, initial_query_timeout_sec=10):
        """
        지정된 조건식으로 실시간 조건검색을 시작합니다.
        Args:
            condition_name (str): 모니터링할 조건식 이름
            initial_query_timeout_sec (int): 초기 종목 리스트를 기다릴 최대 시간 (초)
        """
        if self.is_monitoring and self.condition_name == condition_name:
            logger.warning(f"⚠️ Real-time condition monitoring for '{self.condition_name}' is already running.")
            return
        
        # 기존 모니터링 중지 (다른 조건식으로 변경하거나 재시작하는 경우)
        if self.is_monitoring:
            self.stop_monitoring()
            time.sleep(1) # 중지 후 잠시 대기

        self.condition_name = condition_name
        
        # 1. 조건식 인덱스 가져오기
        # 조건식 목록이 로드될 때까지 기다립니다.
        logger.info("🧠 Waiting for Kiwoom condition list to be loaded...")
        # kiwoom_helper.get_condition_list_names()를 호출하여 조건식 목록을 서버에서 가져오도록 요청
        self.kiwoom_helper.get_condition_list_names() 
        if not self.tr_event_loop.wait_for_condition_version(timeout_ms=initial_query_timeout_sec * 1000):
            logger.error("❌ Failed to load Kiwoom condition list (timeout).")
            send_telegram_message("🚨 조건식 목록 로드 실패 (타임아웃). 모니터링 시작 불가.")
            return

        condition_map = self.kiwoom_helper.get_condition_list() # 이제 조건식 목록이 로드되었을 것임
        if condition_name not in condition_map:
            logger.error(f"❌ Condition '{condition_name}' not found. Please check your Kiwoom conditions.")
            send_telegram_message(f"🚨 조건식 '{condition_name}' 찾을 수 없음. 모니터링 시작 실패.")
            return

        self.condition_index = condition_map[condition_name]
        
        # 2. 고유 화면번호 생성 및 저장 (조건 검색 전용 화면번호 사용)
        self.condition_screen_no = self.kiwoom_helper.generate_condition_screen_no()
        logger.info(f"Generated screen number for condition monitoring: {self.condition_screen_no}")

        # 3. 현재 조건을 만족하는 종목 초기화 (중요)
        # 이전 모니터링 세션의 잔여 데이터 방지
        self.currently_passing_stocks = {} 
        logger.info(f"[{get_current_time_str()}] Initializing currently_passing_stocks for new monitoring session.")

        # 4. 일반 조회 (search_type=0)를 통해 현재 조건 만족 종목 리스트를 가져옵니다.
        logger.info(f"🧠 Sending initial condition query (search_type=0) for '{condition_name}' on screen {self.condition_screen_no}")
        success = self.kiwoom_helper.SendCondition(
            self.condition_screen_no, self.condition_name, self.condition_index, 0
        )
        if not success:
            logger.error(f"❌ Failed to send initial condition query for '{condition_name}'.")
            send_telegram_message(f"🚨 조건식 초기 조회 실패: {condition_name}")
            return

        # 초기 종목 리스트 수신을 위한 짧은 대기
        logger.info(f"Waiting {initial_query_timeout_sec} seconds for initial condition results...")
        time.sleep(initial_query_timeout_sec) 
        logger.info(f"Initial condition query processed. Currently passing stocks: {len(self.currently_passing_stocks)} stocks.")
        self.log_current_stocks() # 초기 로드된 종목들 로그

        # 5. 실시간 조회 (search_type=1) 시작
        logger.info(f"🧠 Starting real-time condition monitoring (search_type=1) for '{condition_name}' on screen {self.condition_screen_no}")
        success = self.kiwoom_helper.SendCondition(
            self.condition_screen_no, self.condition_name, self.condition_index, 1
        )
        if not success:
            logger.error(f"❌ Failed to start real-time condition monitoring for '{condition_name}'.")
            send_telegram_message(f"🚨 조건식 실시간 감시 시작 실패: {condition_name}")
            return

        self.is_monitoring = True
        logger.info(f"✅ Real-time condition monitoring for '{condition_name}' started successfully.")
        send_telegram_message(f"✅ 조건식 실시간 감시 시작: {condition_name}")

    def stop_monitoring(self):
        """
        실시간 조건검색을 중지하고 관련 리소스를 해제합니다.
        """
        if not self.is_monitoring:
            logger.warning("⚠️ Real-time condition monitoring is not running.")
            return

        current_time_str = get_current_time_str()
        logger.info(f"[{current_time_str}] Stopping real-time condition monitoring for '{self.condition_name}' on screen {self.condition_screen_no}...")

        if self.condition_screen_no and self.condition_name and self.condition_index is not None:
            # 1. 실시간 조건검색 중지 요청
            self.kiwoom_helper.SendConditionStop(
                self.condition_screen_no, self.condition_name, self.condition_index
            )
            logger.info(f"Sent SendConditionStop for '{self.condition_name}'.")

            # 2. 해당 화면번호에 등록된 모든 실시간 데이터 해제
            self.kiwoom_helper.SetRealRemove(self.condition_screen_no, "ALL")
            logger.info(f"Called SetRealRemove for screen {self.condition_screen_no}.")
        else:
            logger.warning("⚠️ No active condition monitoring to stop (missing screen_no or condition info).")

        self.is_monitoring = False
        self.condition_name = None
        self.condition_index = None
        self.condition_screen_no = None
        self.currently_passing_stocks = {} # 중지 시 초기화
        logger.info(f"[{current_time_str}] Real-time condition monitoring stopped.")
        send_telegram_message(f"🛑 조건식 실시간 감시 중지됨.")

    def _on_receive_real_condition(self, stock_code, event_type, condition_name, condition_index):
        """
        KiwoomQueryHelper로부터 실시간 조건검색 이벤트를 수신하여 처리합니다.
        """
        # 현재 모니터링 중인 조건식의 이벤트인지 확인
        # (condition_index는 문자열로 넘어올 수 있으므로 비교 시 형변환)
        if not self.is_monitoring or str(condition_index) != str(self.condition_index):
            # 아직 모니터링이 시작되지 않았거나, 현재 모니터링 중인 조건식이 아닌 경우 무시
            return

        stock_name = self.kiwoom_helper.get_stock_name(stock_code) # 캐시된 종목명 사용

        if event_type == "I": # 편입
            if stock_code not in self.currently_passing_stocks:
                self.currently_passing_stocks[stock_code] = stock_name
                logger.info(f"✅ Condition INCLUSION: {stock_name}({stock_code}) added to passing stocks.")
                self.condition_change_signal.emit(stock_code, "I", condition_name)
        elif event_type == "D": # 이탈
            if stock_code in self.currently_passing_stocks:
                del self.currently_passing_stocks[stock_code]
                logger.info(f"❌ Condition EXCLUSION: {stock_name}({stock_code}) removed from passing stocks.")
                self.condition_change_signal.emit(stock_code, "D", condition_name)
        else:
            logger.warning(f"Unknown condition event type: {event_type} for {stock_name}({stock_code})")

    def get_passing_stocks(self):
        """현재 조건을 만족하는 종목 목록을 반환합니다."""
        return self.currently_passing_stocks.copy()

    def log_current_stocks(self):
        """
        현재 조건을 만족하는 종목 목록을 로그로 출력합니다.
        디버깅 및 모니터링에 유용합니다.
        """
        current_time_str = get_current_time_str()
        if not self.currently_passing_stocks:
            logger.info(f"[{current_time_str}] 현재 조건을 만족하는 종목 없음.")
            return

        logger.info(f"[{current_time_str}] 현재 조건을 만족하는 종목 목록 ({len(self.currently_passing_stocks)}개):")
        for code, name in self.currently_passing_stocks.items():
            logger.info(f"  - {name} ({code})")
