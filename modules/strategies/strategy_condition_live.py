# modules/strategies/strategy_condition_live.py

import logging
from datetime import datetime
from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)

class ConditionLiveStrategy:
    def __init__(self, kiwoom_helper, trade_manager, monitor_positions, condition_name="매수전략_1"):
        self.kiwoom_helper = kiwoom_helper
        self.trade_manager = trade_manager
        self.monitor_positions = monitor_positions
        self.condition_name = condition_name
        self.executed_stocks = set()
        self.strategy_name = "ConditionAutoBuy"

        self._connect_signals()

    def _connect_signals(self):
        """
        키움 실시간 조건검색 이벤트 핸들링 등록
        """
        self.kiwoom_helper.ocx.OnReceiveRealCondition.connect(self._on_receive_real_condition)
        logger.info("✅ 실시간 조건검색 이벤트 연결 완료")

    def _on_receive_real_condition(self, stock_code, event_type, condition_name, condition_index):
        """
        실시간 조건검색 이벤트 수신 핸들러
        """
        logger.info(f"[조건검색 포착] 종목코드: {stock_code}, 이벤트: {event_type}, 조건명: {condition_name}")
        
        if event_type == "I":  # 진입 조건 포착
            self.handle_condition_hit(stock_code)

    def handle_condition_hit(self, stock_code):
        """
        조건검색에 포착된 종목 매수 실행
        """
        if stock_code in self.executed_stocks:
            logger.info(f"⚠️ 이미 매수된 종목 {stock_code}, 중복 실행 방지")
            return

        # 전략 필터 로직은 외부에서 삽입하거나 추후 확장 가능
        price = self.kiwoom_helper.get_current_price(stock_code)
        quantity = self._calculate_quantity(price)

        result = self.trade_manager.place_order(
            stock_code=stock_code,
            order_type=1,  # 1: 신규 매수
            quantity=quantity,
            price=0,
            order_division="03",  # 시장가
            screen_no="1801"
        )

        if result.get("status") == "success":
            logger.info(f"✅ 조건검색 자동매수 성공: {stock_code} - 수량 {quantity}")
            send_telegram_message(f"✅ 조건검색 자동매수 성공: {stock_code} - 수량 {quantity}")
            self.executed_stocks.add(stock_code)
        else:
            logger.warning(f"❌ 조건검색 자동매수 실패: {stock_code} - 사유: {result.get('message')}")
            send_telegram_message(f"❌ 조건검색 자동매수 실패: {stock_code} - 사유: {result.get('message')}")

    def _calculate_quantity(self, price, capital=1000000):
        """
        매수 수량 계산 (단순 비중 기반)
        """
        if price <= 0:
            return 0
        qty = int(capital / price / 2)  # 종목당 자금 비중 50%
        return max(qty, 1)

    def reset_executed_stocks(self):
        self.executed_stocks.clear()
        logger.info("🔁 실행 종목 목록 초기화 완료")
