# modules/strategies/main_strategy_loop.py

import logging
from datetime import datetime, time
import time as time_module

from modules.strategies.check_conditions_runner import get_candidate_stocks_from_condition
from modules.strategies.buy_strategy import execute_buy_strategy
from modules.strategies.exit_strategy import execute_exit_strategy
from modules.common.config import REALTIME_FID_LIST
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)

def run_condition_check_step(kiwoom_helper):
    """
    조건 검색을 실행하고, 결과를 kiwoom_helper.filtered_df에 저장합니다.
    이후 실시간 데이터 수신을 위해 종목들을 등록합니다.
    """
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{current_time_str}] 📊 조건검색 실행 시작 (스레드 기반 필터)...")

    candidate_df = get_candidate_stocks_from_condition()
    kiwoom_helper.filtered_df = candidate_df # 필터링된 종목 목록을 kiwoom_helper에 저장

    # --- 개발/테스트를 위한 팁 ---
    # 조건 검색 결과가 없을 때 테스트를 위해 아래 주석을 해제하고 샘플 데이터를 사용할 수 있습니다.
    # if candidate_df.empty:
    #     logger.warning("📭 조건검색 결과: 조건을 만족하는 종목 없음. 테스트용 샘플 데이터 로드.")
    #     kiwoom_helper.filtered_df = pd.DataFrame([
    #         {"ticker": "005930", "name": "삼성전자", "price": 80000},
    #     ])
    #     candidate_df = kiwoom_helper.filtered_df
    # ----------------------------

    logger.info(f"[{current_time_str}] 📈 조건검색 통과 종목 수: {len(candidate_df)}개")

    if not candidate_df.empty:
        tickers_to_register = candidate_df["ticker"].tolist()
        # 고유한 실시간 화면번호 생성 (KiwoomQueryHelper 내부에서 관리)
        screen_no = kiwoom_helper.generate_real_time_screen_no()

        try:
            # SetRealReg 호출 시, 기존에 등록된 동일 화면번호의 종목들은 자동으로 해제됩니다.
            # "0"은 종목 추가, "1"은 종목 제거 (여기서는 추가)
            kiwoom_helper.SetRealReg(screen_no, ";".join(tickers_to_register), REALTIME_FID_LIST, "0")
            logger.info(f"[{current_time_str}] 📡 실시간 데이터 등록 완료: {len(tickers_to_register)} 종목 (화면번호: {screen_no})")
        except Exception as e:
            logger.error(f"[{current_time_str}] ❌ 실시간 데이터 등록 실패: {e}", exc_info=True)
            send_telegram_message(f"❌ 실시간 데이터 등록 실패: {e}")
        time_module.sleep(3) # 실시간 데이터 수신을 위한 짧은 대기

def run_buy_strategy_step(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    """
    매수 전략을 실행합니다.
    kiwoom_helper.filtered_df에 저장된 종목들을 대상으로 매수를 시도합니다.
    """
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{current_time_str}] 🛒 매수 전략 실행 시작...")

    # execute_buy_strategy 함수는 kiwoom_helper.filtered_df를 참조하여 매수 대상을 결정합니다.
    # 만약 실시간 조건 편입 이벤트 등 특정 단일 종목에 대한 즉각적인 매수 로직을 구현한다면,
    # 해당 로직에서 kiwoom_tr_request, trade_manager 등 필요한 모든 인자를 명시적으로 전달해야 합니다.
    execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)

    logger.info(f"[{current_time_str}] 🛒 매수 전략 실행 종료.")

def run_exit_strategy_step(kiwoom_helper, trade_manager, monitor_positions):
    """
    익절/손절 전략을 실행합니다.
    현재 보유 중인 포지션들을 대상으로 매도 조건을 검사합니다.
    """
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{current_time_str}] 💸 익절/손절 전략 실행 시작...")

    execute_exit_strategy(kiwoom_helper, trade_manager, monitor_positions)

    logger.info(f"[{current_time_str}] 💸 익절/손절 전략 실행 종료.")

# NOTE: run_daily_trading_cycle 함수는 현재 local_api_server.py에서 개별 스텝으로 분리되어 호출됩니다.
# 따라서 이 함수는 직접 사용되지 않을 수 있습니다.
def run_daily_trading_cycle(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    """
    하루 동안의 주요 트레이딩 사이클을 실행합니다.
    (조건 검색 -> 매수 전략 -> 익절/손절 전략)
    """
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{current_time_str}] 🚀 메인 전략 루프 시작")

    # 1. 조건 검색 및 실시간 등록
    run_condition_check_step(kiwoom_helper)

    # 2. 매수 전략 실행
    run_buy_strategy_step(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)

    # 3. 익절/손절 전략 실행
    run_exit_strategy_step(kiwoom_helper, trade_manager, monitor_positions)

    logger.info(f"[{current_time_str}] 🏁 메인 전략 루프 종료")

