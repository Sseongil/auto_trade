# modules/strategies/main_strategy_loop.py

import logging
import time as time_module
from datetime import datetime, time

from modules.common.config import REALTIME_FID_LIST
from modules.notify import send_telegram_message
from modules.strategies.check_conditions_runner import get_candidate_stocks_from_condition
from modules.strategies.buy_strategy import execute_buy_strategy
from modules.strategies.exit_strategy import execute_exit_strategy
from modules.Kiwoom.real_time_condition_manager import RealTimeConditionManager # RealTimeConditionManager 임포트

logger = logging.getLogger(__name__)

# 전략 활성화/비활성화 상태를 저장할 전역 변수 (local_api_server에서 제어)
strategy_flags = {
    "condition_check_enabled": False,
    "buy_strategy_enabled": False,
    "exit_strategy_enabled": False,
    "real_condition_name": None, # 현재 등록된 실시간 조건식 이름
    "real_condition_index": None # 현재 등록된 실시간 조건식 인덱스
}

# RealTimeConditionManager 인스턴스 (메인 루프에서 초기화되어 전달될 예정)
real_time_condition_manager_instance = None

def set_strategy_flag(strategy_name: str, enabled: bool):
    """
    특정 전략의 활성화 상태를 설정합니다.
    """
    if strategy_name in strategy_flags:
        strategy_flags[strategy_name] = enabled
        logger.info(f"✅ 전략 '{strategy_name}' 상태 변경: {'활성화' if enabled else '비활성화'}")
    else:
        logger.warning(f"⚠️ 알 수 없는 전략 이름: {strategy_name}")

def set_real_condition_info(condition_name: str | None, condition_index: int | None):
    """
    현재 등록된 실시간 조건식 정보를 설정합니다.
    """
    strategy_flags["real_condition_name"] = condition_name
    strategy_flags["real_condition_index"] = condition_index
    logger.info(f"✅ 실시간 조건식 정보 설정: 이름='{condition_name}', 인덱스={condition_index}")

def initialize_real_time_condition_manager(kiwoom_helper):
    """
    RealTimeConditionManager 인스턴스를 초기화하고 전역 변수에 할당합니다.
    """
    global real_time_condition_manager_instance
    if real_time_condition_manager_instance is None:
        real_time_condition_manager_instance = RealTimeConditionManager(kiwoom_helper)
        logger.info("✅ RealTimeConditionManager 인스턴스 초기화 완료.")

def run_condition_check_step(kiwoom_helper):
    """
    조건 검색 단계를 실행합니다.
    """
    if not strategy_flags["condition_check_enabled"]:
        logger.info("⏸️ 조건 검색 전략 비활성화됨. 건너뜜.")
        return

    # 실시간 조건식 등록/해제 로직
    condition_name = strategy_flags["real_condition_name"]
    condition_index = strategy_flags["real_condition_index"]

    if real_time_condition_manager_instance and condition_name and condition_index is not None:
        if not real_time_condition_manager_instance.is_monitoring or \
           real_time_condition_manager_instance.condition_name != condition_name or \
           real_time_condition_manager_instance.condition_index != condition_index:
            
            logger.info(f"📊 조건검색 매니저 시작/재시작: {condition_name} ({condition_index})")
            real_time_condition_manager_instance.start_monitoring(condition_name)
        else:
            logger.info(f"📊 조건검색 매니저 이미 실행 중: {condition_name}")
            real_time_condition_manager_instance.log_current_stocks() # 현재 통과 종목 로깅
    elif real_time_condition_manager_instance and real_time_condition_manager_instance.is_monitoring:
        # 조건식 이름이 None이거나 인덱스가 None인데 모니터링 중이면 중지
        logger.info("📊 조건검색 매니저 중지 요청 수신.")
        real_time_condition_manager_instance.stop_monitoring()
    else:
        logger.info("📊 조건 검색 매니저가 활성화되지 않았거나 조건식 정보가 없습니다.")
    
    # 조건 검색 결과 DataFrame 업데이트 (RealTimeConditionManager의 현재 통과 종목 활용)
    passing_stocks = real_time_condition_manager_instance.get_passing_stocks() if real_time_condition_manager_instance else {}
    
    # passing_stocks 딕셔너리를 DataFrame으로 변환
    # {stock_code: stock_name} 형태이므로, ticker와 name 컬럼으로 변환
    df_result = pd.DataFrame([
        {"ticker": code, "name": name, "price": kiwoom_helper.get_current_price(code)} # 현재가 추가
        for code, name in passing_stocks.items()
    ])
    kiwoom_helper.filtered_df = df_result
    logger.info(f"📈 실시간 조건검색 통과 종목 수 (업데이트): {len(df_result)}개")


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

    # 장 시작 전 (예: 8시 50분 ~ 9시) 또는 장 마감 후 (15시 30분 이후)
    if not (time(9, 0) <= now_time < time(15, 30)):
        logger.info("⏸️ 장 시간 외 대기 중...")
        # 장 마감 후에는 실시간 데이터 등록 해제
        if now_time >= time(15, 30):
            kiwoom_helper.SetRealRemove("ALL", "ALL")
            logger.info("✅ 장 마감. 모든 실시간 데이터 등록 해제.")
            # 조건 검색 실행 여부 초기화 (다음 날 재실행을 위해)
            kiwoom_helper.is_condition_checked = False
            # 실시간 조건식 정보도 초기화
            set_real_condition_info(None, None)
            if real_time_condition_manager_instance and real_time_condition_manager_instance.is_monitoring:
                real_time_condition_manager_instance.stop_monitoring()
        return

    logger.info(f"🚀 메인 전략 루프 실행 중... (현재 시각: {now_time.strftime('%H:%M:%S')})")

    # RealTimeConditionManager 초기화 (최초 1회)
    initialize_real_time_condition_manager(kiwoom_helper)

    # 1. 조건 검색 단계 (실시간 조건 매니저를 통해 관리)
    run_condition_check_step(kiwoom_helper)

    # 2. 매수 전략 단계
    run_buy_strategy_step(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions)

    # 3. 익절/손절 전략 단계
    run_exit_strategy_step(kiwoom_helper, trade_manager, monitor_positions)

    logger.info("🔄 메인 전략 루프 한 사이클 완료.")
