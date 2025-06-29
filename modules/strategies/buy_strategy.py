import time
import logging
from modules.common.config import DEFAULT_LOT_SIZE
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)

def execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    filtered_df = kiwoom_helper.filtered_df.copy()
    if filtered_df.empty:
        logger.info("조건검색 결과 없음. 매수 전략 종료")
        return

    available_cash = kiwoom_tr_request.request_account_info(trade_manager.account_number).get("예수금", 0)
    buy_amount = available_cash * 0.5

    for idx, target in filtered_df.iterrows():
        code = target["ticker"]
        name = target["name"]
        price = target["price"]

        quantity = int(buy_amount / price)
        if quantity <= 0:
            logger.warning(f"{name}({code}) 매수 가능 수량 부족. 건너뜀")
            continue

        result = trade_manager.place_order(code, 1, quantity, 0, "03")
        if result["status"] == "success":
            logger.info(f"{name}({code}) 시장가 매수 주문 성공")
            send_telegram_message(f"🚀 매수 주문 성공: {name}({code}) 수량: {quantity}")
        else:
            logger.error(f"{name}({code}) 매수 실패: {result.get('message', '알 수 없는 오류')}")
            send_telegram_message(f"❌ 매수 실패: {name}({code})")
        time.sleep(1)
