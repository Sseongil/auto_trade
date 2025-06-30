# modules/strategies/buy_strategy.py

import logging
from modules.common.config import DEFAULT_LOT_SIZE
from modules.notify import send_telegram_message
from modules.strategies.strategy_conditions_live import check_buy_conditions
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

def execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    if kiwoom_helper.filtered_df.empty:
        logger.info("📭 조건검색 통과 종목 없음. 매수 전략 건너뜀.")
        return

    available_cash = kiwoom_tr_request.request_account_info(trade_manager.account_number).get("예수금", 0)
    if available_cash <= 0:
        logger.warning("🚫 매수 실패: 예수금 부족.")
        return

    buy_amount = available_cash * 0.5

    for _, row in kiwoom_helper.filtered_df.iterrows():
        stock_code = row["ticker"]
        stock_name = row["name"]

        result = check_buy_conditions(kiwoom_helper, kiwoom_tr_request, stock_code, stock_name)
        if result:
            target_current_price = result["current_price"]
            quantity = int(buy_amount / target_current_price / DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE

            if quantity <= 0:
                logger.warning(f"🚫 {stock_name} 매수 불가: 매수 수량 부족 (예수금: {available_cash}, 현재가: {target_current_price})")
                continue

            logger.info(f"🚀 매수 시도: {stock_name}({stock_code}), 수량: {quantity}")
            resp = trade_manager.place_order(stock_code, 1, quantity, 0, "03")

            if resp.get("status") == "success":
                send_telegram_message(f"✅ 매수 완료: {stock_name} {quantity}주")
                logger.info(f"✅ 매수 성공: {stock_name}({stock_code})")
            else:
                logger.error(f"❌ 매수 실패: {stock_name}({stock_code}) - {resp.get('message')}")
