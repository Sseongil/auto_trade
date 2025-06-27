# modules/strategies/buy_strategy.py

import logging
from datetime import datetime
import pandas as pd
import time

from modules.common.utils import get_current_time_str
from modules.common.config import (
    DEFAULT_LOT_SIZE,
    MIN_CHEGYUL_GANGDO,
    MIN_BUY_SELL_RATIO
)

from modules.notify import send_telegram_message
from modules.trade_logger import TradeLogger
from modules.check_conditions_threaded import run_condition_filter_and_return_df

logger = logging.getLogger(__name__)
trade_logger = TradeLogger()


def check_buy_conditions(kiwoom_helper, stock_code, stock_name):
    """
    SetRealReg 등록 후 쌓인 실시간 체결 데이터 기반으로
    최종 매수 대상 여부를 판단.
    """
    logger.info(f"🔍 {stock_name}({stock_code}) 실시간 조건 점검 중...")

    real_time_info = kiwoom_helper.real_time_data.get(stock_code, {})
    if not real_time_info:
        logger.warning(f"⚠️ {stock_name}({stock_code}) 실시간 데이터 없음. 조건 점검 불가.")
        return False

    chegyul_gangdo = real_time_info.get('chegyul_gangdo', 0.0)
    buy_cvol = real_time_info.get('total_buy_cvol', 0)
    sell_cvol = real_time_info.get('total_sell_cvol', 1)  # 0 방지

    buy_sell_ratio = buy_cvol / sell_cvol if sell_cvol else float('inf')

    if chegyul_gangdo < MIN_CHEGYUL_GANGDO:
        logger.debug(f"❌ 체결강도 미달: {chegyul_gangdo:.2f}%")
        return False

    if buy_sell_ratio < MIN_BUY_SELL_RATIO:
        logger.debug(f"❌ 매수/매도 잔량비 미달: {buy_sell_ratio:.2f}")
        return False

    logger.info(f"✅ {stock_name}({stock_code}) 실시간 조건 통과")
    return True


def execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    """
    조건검색으로 선별된 후보 종목에 대해 실시간 체결 조건 추가 점검 후
    최종 매수 종목을 선정하고 주문 실행.
    """
    logger.info("🚀 매수 전략 실행 시작")

    candidate_df = run_condition_filter_and_return_df()
    if candidate_df.empty:
        logger.info("🔍 조건 통과 종목 없음")
        return

    candidate_df = candidate_df.sort_values(by="ticker").reset_index(drop=True)
    logger.info(f"✅ 필터링 후보: {len(candidate_df)}개")

    current_positions = monitor_positions.get_all_positions()
    current_holding_codes = set(current_positions.keys())

    tickers_to_register = candidate_df["ticker"].tolist()
    screen_no = kiwoom_helper.generate_real_time_screen_no()
    fid_list = "10;15;27;28;30;41;121;125"

    try:
        kiwoom_helper.SetRealReg(screen_no, ";".join(tickers_to_register), fid_list, "0")
        logger.info(f"📡 실시간 데이터 등록 완료: {len(tickers_to_register)}종목")
    except Exception as e:
        logger.error(f"❌ 실시간 등록 실패: {e}", exc_info=True)
        return

    time.sleep(3)  # 실시간 데이터 수신 대기 (조정 가능)

    buy_candidates = []
    for _, row in candidate_df.iterrows():
        stock_code = row["ticker"]
        stock_name = row["name"]

        if stock_code in current_holding_codes:
            continue

        if check_buy_conditions(kiwoom_helper, stock_code, stock_name):
            buy_candidates.append((stock_code, stock_name))

    if not buy_candidates:
        logger.info("🔍 실시간 조건 통과 종목 없음")
        return

    stock_code, stock_name = buy_candidates[0]
    logger.info(f"🎯 최종 매수 종목: {stock_name}({stock_code})")

    account_info = kiwoom_tr_request.request_account_info(trade_manager.account_number)
    available_cash = account_info.get("예수금", 0)

    if available_cash <= 0:
        logger.warning(f"🚫 예수금 부족: {available_cash:,}원")
        send_telegram_message("🚫 매수 실패: 예수금 부족")
        return

    current_price = kiwoom_helper.real_time_data.get(stock_code, {}).get("current_price", 0)
    if current_price <= 0:
        logger.warning(f"❌ 현재가 조회 실패: {stock_code}")
        return

    buy_amount = available_cash * 0.5
    quantity = int((buy_amount / current_price) // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE

    if quantity <= 0:
        logger.warning(f"❌ 매수 수량 계산 실패 (예수금: {available_cash}, 가격: {current_price})")
        return

    logger.info(f"🛒 매수 시도: {stock_name}({stock_code}), 수량: {quantity}, 가격: {current_price:,}")
    send_telegram_message(f"🚀 매수 신호 포착: {stock_name}({stock_code}) 수량: {quantity}주")

    result = trade_manager.place_order(stock_code, 1, quantity, current_price, "00")
    if result["status"] != "success":
        logger.warning(f"⚠️ 지정가 실패, 시장가 재시도")
        result = trade_manager.place_order(stock_code, 1, quantity, 0, "03")

    if result["status"] == "success":
        logger.info(f"✅ 매수 주문 완료: {stock_name}")
    else:
        logger.error(f"❌ 매수 실패: {result.get('message')}")
