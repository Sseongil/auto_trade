# modules/strategies/main_strategy_loop.py

import logging
from datetime import datetime, time
from modules.strategies.buy_strategy import execute_buy_strategy
from modules.strategies.exit_strategy import execute_exit_strategy
from modules.strategies.check_conditions_runner import get_candidate_stocks_from_condition
from modules.common.config import REALTIME_FID_LIST

logger = logging.getLogger(__name__)

def run_daily_trading_cycle(kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager):
    now = datetime.now().time()

    if time(9, 1) <= now < time(9, 5) and kiwoom_helper.filtered_df.empty:
        logger.info("✅ 1단계 - 조건검색 시작")
        candidate_df = get_candidate_stocks_from_condition()
        kiwoom_helper.filtered_df = candidate_df
        tickers = candidate_df["ticker"].tolist()
        screen_no = kiwoom_helper.generate_real_time_screen_no()
        kiwoom_helper.SetRealReg(screen_no, ";".join(tickers), REALTIME_FID_LIST, "0")
    elif time(9, 5) <= now < time(15, 0):
        logger.info("✅ 2단계 - 매수 전략 실행")
        execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)
        logger.info("✅ 3단계 - 익절/손절 전략 실행")
        execute_exit_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)
    elif now >= time(15, 0):
        logger.info("✅ 4단계 - 장 마감 처리")
        kiwoom_helper.SetRealRemove("ALL", "ALL")
        logger.info("✅ 실시간 데이터 해제 완료")
