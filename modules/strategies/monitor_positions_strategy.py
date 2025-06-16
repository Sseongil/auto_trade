# modules/strategies/monitor_positions_strategy.py

from modules.notify import send_telegram_message
import logging

logger = logging.getLogger(__name__)

class MonitorStrategy:
    def __init__(self, monitor_positions, trade_manager):
        self.monitor = monitor_positions
        self.trade_manager = trade_manager

        # 전략 설정값 (퍼센트 단위)
        self.profit_target = 3.0           # ✅ 익절 조건: +3% 이상
        self.loss_cut = -2.0               # ✅ 손절 조건: -2% 이하
        self.trailing_threshold = 1.5      # ✅ 추적 손절 시작 조건: +1.5% 이상
        self.trailing_stop_margin = 0.7    # ✅ 피크 대비 하락폭: -0.7% 이상

        self.peak_profit_by_code = {}  # 종목별 피크 수익률 기록

    def monitor_positions_strategy(self):
        positions = self.monitor.get_current_positions()
        for pos in positions:
            stock_code = pos["stock_code"]
            stock_name = pos["stock_name"]
            profit_rate = pos["profit_loss_rate"]
            quantity = pos["quantity"]
            current_price = pos["current_price"]

            logger.info(f"전략 평가: {stock_name} | 수익률: {profit_rate:.2f}% | 수량: {quantity}")

            # 손절 조건
            if profit_rate <= self.loss_cut:
                self._execute_sell(stock_code, quantity, current_price,
                                   f"❌ 손절 매도: {stock_name} ({profit_rate:.2f}%)")
                continue

            # 익절 조건
            if profit_rate >= self.profit_target:
                self._execute_sell(stock_code, quantity, current_price,
                                   f"✅ 익절 매도: {stock_name} ({profit_rate:.2f}%)")
                continue

            # 트레일링 스탑
            peak = self.peak_profit_by_code.get(stock_code, profit_rate)
            if profit_rate > peak:
                self.peak_profit_by_code[stock_code] = profit_rate
                logger.info(f"📈 피크 갱신: {stock_name} → {profit_rate:.2f}%")
            elif (
                peak >= self.trailing_threshold and
                (peak - profit_rate) >= self.trailing_stop_margin
            ):
                self._execute_sell(stock_code, quantity, current_price,
                                   f"📉 추적손절 매도: {stock_name} 피크 {peak:.2f}% → 현재 {profit_rate:.2f}%")
                continue

    def _execute_sell(self, code, qty, price, message):
        try:
            self.trade_manager.place_order(code, order_type=2, quantity=qty, price=price, hoga_gb="03")  # 시장가 매도
            send_telegram_message(message)
            logger.info(message)
        except Exception as e:
            error_msg = f"⚠️ 매도 실패: {code} | 예외: {e}"
            send_telegram_message(error_msg)
            logger.exception(error_msg)
