# modules/strategies/main_strategy_loop.py

import logging
from datetime import datetime, time
from modules.strategies.buy_strategy import execute_buy_strategy
from modules.strategies.exit_strategy import execute_exit_strategy
from modules.strategies.check_conditions_runner import get_candidate_stocks_from_condition

logger = logging.getLogger(__name__)

def run_daily_trading_cycle(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    """
    장중 자동매매 전략을 주기적으로 실행
    """
    now = datetime.now().time()

    if time(9, 1) <= now < time(9, 5):
        logger.info("🟡 1단계: 조건검색 시작")
        try:
            candidate_df = get_candidate_stocks_from_condition()
            tickers = candidate_df['ticker'].tolist()

            if not tickers:
                logger.info("조건검색 통과 종목 없음. 매매 전략 실행 안함.")
                return

            # 실시간 데이터 등록 (매수 조건 검사용)
            screen_no = kiwoom_helper.generate_real_time_screen_no()
            fid_list = "10;15;228;851;852;27;28"  # 가격/체결강도 관련
            kiwoom_helper.SetRealReg(screen_no, ";".join(tickers), fid_list, "0")

            logger.info(f"✅ 조건검색 종목 실시간 등록 완료: {len(tickers)}개")

        except Exception as e:
            logger.error(f"❌ 조건검색 실행 실패: {e}", exc_info=True)

    if time(9, 5) <= now < time(15, 0):
        logger.info("🟢 2단계: 매수 전략 실행")
        try:
            execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)
        except Exception as e:
            logger.error(f"❌ 매수 전략 실행 중 오류: {e}", exc_info=True)

        logger.info("🔵 3단계: 익절/손절 전략 실행")
        try:
            execute_exit_strategy(kiwoom_helper, trade_manager, monitor_positions)
        except Exception as e:
            logger.error(f"❌ 익절/손절 전략 실행 중 오류: {e}", exc_info=True)
