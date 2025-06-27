# modules/strategies/check_conditions_runner.py

import logging
import pandas as pd
from modules.check_conditions_threaded import run_condition_filter_and_return_df
from modules.common.config import CONDITION_CHECK_MAX_WORKERS

logger = logging.getLogger(__name__)

def get_candidate_stocks_from_condition():
    """
    실시간으로 조건 검색 필터를 실행하고 결과 DataFrame을 반환합니다.
    실시간 자동매매 루프에서 호출됩니다.
    """
    logger.info("📊 조건검색 실행 시작 (스레드 기반 필터)...")
    
    try:
        df_result = run_condition_filter_and_return_df(max_workers=CONDITION_CHECK_MAX_WORKERS)

        if df_result.empty:
            logger.info("📭 조건검색 결과: 조건을 만족하는 종목 없음.")
        else:
            logger.info(f"📈 조건검색 통과 종목 수: {len(df_result)}개")

        return df_result
    
    except Exception as e:
        logger.error(f"❌ 조건검색 중 예외 발생: {e}", exc_info=True)
        return pd.DataFrame()
