# modules/Kiwoom/condition_handler.py

import logging
from datetime import datetime
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)

class ConditionHandler:
    def __init__(self, kiwoom_helper, strategy_executor):
        self.kiwoom_helper = kiwoom_helper
        self.strategy_executor = strategy_executor
        self.loaded_conditions = {}
        self.real_time_condition_screen_no = "5000"  # 실시간 조건검색용 화면번호

    def load_conditions(self):
        try:
            self.loaded_conditions = self.kiwoom_helper.get_condition_list()
            logger.info(f"🔍 조건검색식 로드 완료: {len(self.loaded_conditions)}개")
        except Exception as e:
            logger.error(f"❌ 조건검색식 로딩 실패: {e}")
            send_telegram_message(f"❌ 조건검색식 로딩 실패: {e}")

    def start_real_time_condition(self, condition_name):
        if not self.loaded_conditions:
            self.load_conditions()
        
        if condition_name not in self.loaded_conditions:
            logger.error(f"❌ 존재하지 않는 조건검색식 이름: {condition_name}")
            send_telegram_message(f"❌ 조건검색식 '{condition_name}' 존재하지 않음.")
            return

        index = self.loaded_conditions[condition_name]
        logger.info(f"⚡ 실시간 조건검색 등록 시작: '{condition_name}' (Index: {index})")
        
        try:
            self.kiwoom_helper.SendCondition(
                self.real_time_condition_screen_no,
                condition_name,
                index,
                1  # 실시간 등록 모드
            )
            logger.info(f"✅ 실시간 조건검색 '{condition_name}' 등록 완료")
            send_telegram_message(f"✅ 실시간 조건검색 '{condition_name}' 등록 완료")
        except Exception as e:
            logger.error(f"❌ 조건검색 등록 실패: {e}", exc_info=True)
            send_telegram_message(f"❌ 조건검색 등록 실패: {e}")

    def on_condition_stock_enter(self, stock_code, stock_name):
        logger.info(f"🚨 조건검색 편입 종목: {stock_name}({stock_code})")
        self.strategy_executor.process_condition_match(stock_code, stock_name)
