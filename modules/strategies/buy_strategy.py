# modules/strategies/buy_strategy.py

import logging
import time
from datetime import datetime, timedelta # timedelta 추가
from modules.common.config import DEFAULT_LOT_SIZE, MIN_HOLD_TIME_MINUTES # MIN_HOLD_TIME_MINUTES 추가
from modules.notify import send_telegram_message
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

def check_buy_conditions(kiwoom_helper, stock_code: str, stock_name: str) -> dict | None:
    """
    실시간 체결 데이터 기반으로 최종 매수 대상 여부를 판단합니다.
    """
    real_time_info = kiwoom_helper.real_time_data.get(stock_code, {})
    current_price = real_time_info.get("current_price")
    if current_price is None or current_price == 0:
        logger.debug(f"⚠️ {stock_name}({stock_code}) 현재가 정보 없음.")
        return None

    chegyul_gangdo = real_time_info.get("chegyul_gangdo", 0)
    total_buy_cvol = real_time_info.get("total_buy_cvol", 0)
    total_sell_cvol = real_time_info.get("total_sell_cvol", 1) # 0으로 나누는 것 방지

    # 체결 강도 조건 (예: 120 이상)
    if chegyul_gangdo < 120:
        logger.debug(f"❌ {stock_name}({stock_code}) 체결강도 부족: {chegyul_gangdo:.2f}")
        return None

    # 매수/매도 체결량 비율 조건 (예: 매수 체결량이 매도 체결량의 1.5배 이상)
    buy_sell_ratio = total_buy_cvol / total_sell_cvol if total_sell_cvol > 0 else 0
    if buy_sell_ratio < 1.5:
        logger.debug(f"❌ {stock_name}({stock_code}) 매수/매도 비율 부족: {buy_sell_ratio:.2f}")
        return None

    # 추가적인 실시간 조건들을 여기에 추가할 수 있습니다.
    # 예: 특정 시간대 매수, 호가창 잔량 분석 등

    # 모든 조건을 통과하면 종목 정보 반환
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "current_price": current_price,
        "score": chegyul_gangdo # 점수 기준으로 정렬할 수 있도록 체결강도 사용 (예시)
    }

def execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    """
    매수 전략을 실행합니다. 조건 검색을 통과한 종목 중 실시간 조건을 만족하는 종목을 매수합니다.
    """
    current_time_str = get_current_time_str()
    filtered_df = kiwoom_helper.filtered_df.copy() # 조건 검색으로 걸러진 종목들

    if filtered_df.empty:
        logger.info(f"[{current_time_str}] 조건 통과 종목 없음. 매수 전략 종료.")
        return

    logger.info(f"[{current_time_str}] 조건 통과 종목 {len(filtered_df)}개. 매수 전략 실행.")

    # 현재 보유 중인 종목은 매수 대상에서 제외
    current_positions = monitor_positions.get_all_positions()
    current_holding_codes = set(current_positions.keys())

    buy_candidates = []
    for _, row in filtered_df.iterrows():
        stock_code = row["ticker"]
        stock_name = row["name"]

        if stock_code in current_holding_codes:
            logger.debug(f"보유 중인 종목 {stock_name}({stock_code}) 제외")
            continue

        # 실시간 매수 조건 점검
        result = check_buy_conditions(kiwoom_helper, stock_code, stock_name)
        if result:
            buy_candidates.append(result)

    if not buy_candidates:
        logger.info(f"[{current_time_str}] 실시간 조건 만족 종목 없음. 매수 전략 종료.")
        return

    # 가장 점수가 높은 종목 하나만 매수 (예시)
    buy_candidates.sort(key=lambda x: x["score"], reverse=True)
    target = buy_candidates[0]

    account_info = kiwoom_tr_request.request_account_info(trade_manager.account_number)
    available_cash = account_info.get("예수금", 0)
    if available_cash <= 0:
        logger.warning(f"[{current_time_str}] 예수금 부족. 매수 불가 (현재 잔고: {available_cash:,}원)")
        send_telegram_message("🚫 매수 실패: 예수금 부족")
        return

    # 매수 금액 (예수금의 50%)
    buy_amount = available_cash * 0.5
    # 매수 수량 계산 (최소 거래 단위 DEFAULT_LOT_SIZE 고려)
    quantity = int(buy_amount / target["current_price"] // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE

    if quantity <= 0:
        logger.warning(f"[{current_time_str}] {target['stock_name']}({target['stock_code']}) 매수 가능 수량 부족. 건너뜀.")
        return

    logger.info(f"🚀 {target['stock_name']}({target['stock_code']}) 매수 시도: 수량 {quantity}주, 가격 {target['current_price']:,}원")
    send_telegram_message(f"🚀 매수 시도: {target['stock_name']}({target['stock_code']}) 수량: {quantity}")

    # 시장가 매수 주문 (03: 시장가)
    result = trade_manager.place_order(target["stock_code"], 1, quantity, 0, "03")

    if result["status"] == "success":
        logger.info(f"✅ {target['stock_name']}({target['stock_code']}) 시장가 매수 주문 성공. 주문번호: {result.get('order_no')}")
        # 매수 성공 시, MonitorPositions에서 체결 이벤트를 통해 포지션이 업데이트됨
    else:
        logger.error(f"❌ {target['stock_name']}({target['stock_code']}) 매수 주문 실패: {result.get('message', '알 수 없는 오류')}")
        send_telegram_message(f"❌ 매수 실패: {target['stock_name']}({target['stock_code']}) - {result.get('message', '알 수 없는 오류')}")

