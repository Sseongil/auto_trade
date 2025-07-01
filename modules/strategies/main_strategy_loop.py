# modules/strategies/main_strategy_loop.py

import logging
import time as time_module
from datetime import datetime, time

from modules.strategies.check_conditions_runner import get_candidate_stocks_from_condition
from modules.strategies.buy_strategy import execute_buy_strategy
from modules.strategies.exit_strategy import execute_exit_strategy
from modules.common.config import REALTIME_FID_LIST
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)

# 전략 활성화/비활성화 상태를 저장할 전역 변수 (local_api_server에서 제어)
strategy_flags = {
    "condition_check_enabled": False,
    "buy_strategy_enabled": False,
    "exit_strategy_enabled": False,
    "real_condition_name": None, # 현재 등록된 실시간 조건식 이름
    "real_condition_index": None # 현재 등록된 실시간 조건식 인덱스
}

def set_strategy_flag(strategy_name: str, enabled: bool):
    """
    특정 전략의 활성화 상태를 설정합니다.
    """
    if strategy_name in strategy_flags:
        strategy_flags[strategy_name] = enabled
        logger.info(f"✅ 전략 '{strategy_name}' 상태 변경: {'활성화' if enabled else '비활성화'}")
    else:
        logger.warning(f"⚠️ 알 수 없는 전략 이름: {strategy_name}")

def set_real_condition_info(condition_name: str, condition_index: int):
    """
    현재 등록된 실시간 조건식 정보를 설정합니다.
    """
    strategy_flags["real_condition_name"] = condition_name
    strategy_flags["real_condition_index"] = condition_index
    logger.info(f"✅ 실시간 조건식 정보 설정: 이름='{condition_name}', 인덱스={condition_index}")

def run_condition_check_step(kiwoom_helper):
    """
    조건 검색 단계를 실행합니다.
    """
    if not strategy_flags["condition_check_enabled"]:
        logger.info("⏸️ 조건 검색 전략 비활성화됨. 건너뜜.")
        return

    logger.info("📊 조건검색 실행 시작 (스레드 기반 필터)...")
    candidate_df = get_candidate_stocks_from_condition(kiwoom_helper) # kiwoom_helper 인자 전달
    kiwoom_helper.filtered_df = candidate_df
    logger.info(f"📈 조건검색 통과 종목 수: {len(candidate_df)}개")

    # 조건 검색 결과가 있을 경우 실시간 데이터 등록
    if not candidate_df.empty:
        tickers_to_register = candidate_df["ticker"].tolist()
        screen_no = kiwoom_helper.generate_real_time_screen_no()

        try:
            kiwoom_helper.SetRealReg(screen_no, ";".join(tickers_to_register), REALTIME_FID_LIST, "0")
            logger.info(f"📡 실시간 데이터 등록 완료: {len(tickers_to_register)} 종목")
        except Exception as e:
            logger.error(f"❌ 실시간 데이터 등록 실패: {e}", exc_info=True)
        time_module.sleep(3) # 실시간 데이터 수신을 위한 대기

def run_buy_strategy_step(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    """
    매수 전략 단계를 실행합니다.
    """
    if not strategy_flags["buy_strategy_enabled"]:
        logger.info("⏸️ 매수 전략 비활성화됨. 건너뜜.")
        return

    logger.info("💰 매수 전략 실행 시작...")
    execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)
    logger.info("💰 매수 전략 실행 종료.")

def run_exit_strategy_step(kiwoom_helper, trade_manager, monitor_positions):
    """
    익절/손절 전략 단계를 실행합니다.
    """
    if not strategy_flags["exit_strategy_enabled"]:
        logger.info("⏸️ 익절/손절 전략 비활성화됨. 건너뜜.")
        return

    logger.info("📉 익절/손절 전략 실행 시작...")
    execute_exit_strategy(kiwoom_helper, trade_manager, monitor_positions)
    logger.info("📉 익절/손절 전략 실행 종료.")

def run_daily_trading_cycle(kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager):
    """
    매일의 트레이딩 사이클을 실행합니다.
    """
    now_time = datetime.now().time()

    # 장 시작 전 (예: 8시 30분 ~ 9시) 또는 장 마감 후 (15시 30분 이후)
    if not (time(9, 0) <= now_time < time(15, 30)):
        logger.info("⏸️ 장 시간 외 대기 중...")
        # 장 마감 후에는 실시간 데이터 등록 해제
        if now_time >= time(15, 30):
            kiwoom_helper.SetRealRemove("ALL", "ALL")
            logger.info("✅ 장 마감. 모든 실시간 데이터 등록 해제.")
            # 조건 검색 실행 여부 초기화 (다음 날 재실행을 위해)
            kiwoom_helper.is_condition_checked = False
            strategy_flags["real_condition_name"] = None
            strategy_flags["real_condition_index"] = None
        return

    logger.info(f"🚀 메인 전략 루프 실행 중... (현재 시각: {now_time.strftime('%H:%M:%S')})")

    # 1. 조건 검색 단계 (하루에 한 번 또는 필요 시)
    # is_condition_checked 플래그를 사용하여 하루에 한 번만 실행되도록 제어
    if not kiwoom_helper.is_condition_checked:
        run_condition_check_step(kiwoom_helper)
        kiwoom_helper.is_condition_checked = True # 조건 검색 완료 플래그 설정

    # 2. 매수 전략 단계
    run_buy_strategy_step(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)

    # 3. 익절/손절 전략 단계
    run_exit_strategy_step(kiwoom_helper, trade_manager, monitor_positions)

    logger.info("🔄 메인 전략 루프 한 사이클 완료.")

