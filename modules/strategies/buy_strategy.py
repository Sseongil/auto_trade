# modules/strategies/buy_strategy.py

import logging
import time
from modules.notify import send_telegram_message
from modules.common.config import DEFAULT_LOT_SIZE
from modules.common.utils import get_current_time_str
from modules.trade_logger import TradeLogger # TradeLogger 임포트

logger = logging.getLogger(__name__)
trade_logger = TradeLogger() # TradeLogger 인스턴스 생성

def check_buy_conditions(kiwoom_helper, stock_code, stock_name):
    """
    실시간 체결 데이터 기반으로 매수 대상 여부를 판단합니다.
    (향후 조건이 복잡해지면 scoring_rules.py 또는 buy_filters.py로 분리 고려)
    """
    real_time_info = kiwoom_helper.real_time_data.get(stock_code, {})
    current_price = real_time_info.get("current_price")
    if current_price is None:
        logger.debug(f"⚠️ {stock_name}({stock_code}) 현재가 정보 없음")
        return None
    chegyul_gangdo = real_time_info.get("chegyul_gangdo", 0)
    total_buy_cvol = real_time_info.get("total_buy_cvol", 0)
    total_sell_cvol = real_time_info.get("total_sell_cvol", 1) # 0으로 나누는 것 방지

    # 체결강도 조건
    if chegyul_gangdo < 120:
        logger.debug(f"❌ {stock_name}({stock_code}) 체결강도 조건 미충족: {chegyul_gangdo}")
        return None

    # 매수/매도 체결량 비율 조건
    buy_sell_ratio = total_buy_cvol / total_sell_cvol
    if buy_sell_ratio < 1.5:
        logger.debug(f"❌ {stock_name}({stock_code}) 매수/매도 체결량 비율 조건 미충족: {buy_sell_ratio:.2f}")
        return None

    # 모든 조건을 만족하면 해당 종목의 정보를 반환
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "current_price": current_price,
        "chegyul_gangdo": chegyul_gangdo,
        "buy_sell_ratio": buy_sell_ratio,
        "score": (chegyul_gangdo * 0.5) + (buy_sell_ratio * 10) # 예시 스코어링
    }

def execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    """
    조건 검색을 통해 필터링된 종목들을 대상으로 매수 전략을 실행합니다.
    """
    current_time_str = get_current_time_str()
    # filtered_df는 main_strategy_loop에서 조건 검색 후 설정됩니다.
    # RealTimeConditionManager는 filtered_df를 직접 조작하지 않고,
    # on_receive_real_condition 이벤트를 통해 currently_passing_stocks를 관리합니다.
    # 따라서 여기서 .copy()를 사용하는 것은 안전합니다.
    filtered_df = kiwoom_helper.filtered_df.copy()

    if filtered_df.empty:
        logger.info(f"[{current_time_str}] 조건 통과 종목 없음. 매수 전략 종료.")
        return

    logger.info(f"[{current_time_str}] 조건 통과 종목 {len(filtered_df)}개. 매수 전략 실행 준비.")

    # 계좌 정보 조회
    account_info = kiwoom_tr_request.request_account_info(trade_manager.account_number)
    available_cash = account_info.get("예수금", 0)

    if available_cash <= 0:
        logger.warning(f"⚠️ 예수금 부족. 매수 불가 (현재 잔고: {available_cash:,}원)")
        send_telegram_message("🚫 매수 실패: 예수금 부족")
        return

    buy_candidates = []
    for _, target in filtered_df.iterrows():
        stock_code = target["ticker"]
        stock_name = target["name"]

        # 이미 보유 중인 종목은 매수 대상에서 제외
        if monitor_positions.get_position(stock_code):
            logger.debug(f"[{current_time_str}] {stock_name}({stock_code})은(는) 이미 보유 중이므로 매수 대상에서 제외합니다.")
            continue

        # 실시간 데이터 기반으로 최종 매수 조건 검사
        result = check_buy_conditions(kiwoom_helper, stock_code, stock_name)
        if result:
            buy_candidates.append(result)

    if not buy_candidates:
        logger.info(f"[{current_time_str}] 최종 매수 조건 만족 종목 없음.")
        return

    # 가장 높은 점수를 받은 종목 선택 (예시: 스코어링 기반)
    buy_candidates.sort(key=lambda x: x["score"], reverse=True)
    target_stock = buy_candidates[0]

    stock_code = target_stock["stock_code"]
    stock_name = target_stock["stock_name"]
    current_price = target_stock["current_price"]

    # 매수 금액 및 수량 계산
    # available_cash가 10만원 미만일 경우 quantity가 0이 될 수 있으므로,
    # 최소 거래 단위를 고려하여 수량을 계산하고 0보다 큰지 확인
    buy_amount_per_stock = available_cash * 0.5 # 전체 예수금의 50%를 한 종목 매수에 사용
    
    # DEFAULT_LOT_SIZE는 현재 config.py에 고정값으로 설정되어 있으나,
    # 향후 주식 종목별로 다른 값을 가질 수 있도록 확장 가능합니다.
    quantity_to_buy = int(buy_amount_per_stock / current_price)
    quantity_to_buy = (quantity_to_buy // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE

    if quantity_to_buy <= 0:
        logger.warning(f"[{current_time_str}] ⚠️ {stock_name}({stock_code}) 매수 가능 수량 부족 (예수금: {available_cash:,}원, 현재가: {current_price:,}원). 매수 건너뜀.")
        send_telegram_message(f"🚫 매수 실패: {stock_name} - 매수 수량 부족")
        return

    logger.info(f"[{current_time_str}] 🚀 최종 매수 시도: {stock_name}({stock_code}), 수량: {quantity_to_buy}주, 가격: {current_price:,}원")
    send_telegram_message(f"🚀 매수 시도: {stock_name}({stock_code}) 수량: {quantity_to_buy}주")

    # 시장가 매수 주문 (구분: "03")
    order_result = trade_manager.place_order(
        stock_code=stock_code,
        order_type=1, # 1: 신규매수
        quantity=quantity_to_buy,
        price=0,      # 시장가이므로 0
        order_division="03" # 03: 시장가
    )

    if order_result["status"] == "success":
        order_no = order_result.get("order_no", "N/A")
        logger.info(f"[{current_time_str}] ✅ 시장가 매수 주문 성공: {stock_name}({stock_code}), 주문번호: {order_no}")
        send_telegram_message(f"✅ 매수 주문 성공: {stock_name}({stock_code}) - 주문번호: {order_no}")
        # 주문 요청 성공 시 로그 기록 (실제 체결 정보는 TradeManager의 OnReceiveChejanData에서 처리)
        trade_logger.log_trade(stock_code, stock_name, 'BUY_ORDER_REQUEST', quantity_to_buy, current_price, order_no=order_no)
    else:
        error_message = order_result.get("message", "알 수 없는 오류")
        logger.error(f"[{current_time_str}] ❌ 시장가 매수 주문 실패: {stock_name}({stock_code}) - {error_message}")
        send_telegram_message(f"❌ 매수 주문 실패: {stock_name}({stock_code}) - {error_message}")

