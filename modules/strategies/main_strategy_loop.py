# modules/strategies/main_strategy_loop.py

import logging
from datetime import datetime, time
from modules.strategies.check_conditions_runner import get_candidate_stocks_from_condition
from modules.strategies.buy_strategy import execute_buy_strategy
from modules.strategies.exit_strategy import execute_exit_strategy
from modules.common.config import REALTIME_FID_LIST
import time as time_module

logger = logging.getLogger(__name__)

def run_condition_check_step(kiwoom_helper):
    logger.info("📊 조건검색 실행 시작 (스레드 기반 필터)...")
    candidate_df = get_candidate_stocks_from_condition()
    kiwoom_helper.filtered_df = candidate_df
    logger.info(f"📈 조건검색 통과 종목 수: {len(candidate_df)}개")

    if not candidate_df.empty:
        tickers_to_register = candidate_df["ticker"].tolist()
        screen_no = kiwoom_helper.generate_real_time_screen_no()

        try:
            kiwoom_helper.SetRealReg(screen_no, ";".join(tickers_to_register), REALTIME_FID_LIST, "0")
            logger.info(f"📡 실시간 데이터 등록 완료: {len(tickers_to_register)} 종목")
        except Exception as e:
            logger.error(f"❌ 실시간 데이터 등록 실패: {e}", exc_info=True)
        time_module.sleep(3)

def run_buy_strategy_step(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    logger.info("💰 매수 전략 실행")
    execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)

def run_exit_strategy_step(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    logger.info("🏳️‍🌈 익절/손절 전략 실행")
    execute_exit_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)
