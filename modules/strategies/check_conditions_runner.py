# modules/strategies/check_conditions_runner.py

import logging
import pandas as pd
# run_condition_filter_and_return_df 함수가 kiwoom_helper를 인자로 받도록 변경되었으므로
# 해당 함수를 import 할 때도 이를 고려해야 합니다.
from modules.check_conditions_threaded import run_condition_filter_and_return_df 
from modules.common.config import CONDITION_CHECK_MAX_WORKERS

logger = logging.getLogger(__name__)

def get_candidate_stocks_from_condition(kiwoom_helper): # kiwoom_helper 인자 추가
    """
    실시간으로 조건 검색 필터를 실행하고 결과 DataFrame을 반환합니다.
    실시간 자동매매 루프에서 호출됩니다.
    """
    logger.info("📊 조건검색 실행 시작 (스레드 기반 필터)...")
    
    try:
        # run_condition_filter_and_return_df에 kiwoom_helper 인자 전달
        df_result = run_condition_filter_and_return_df(kiwoom_helper, max_workers=CONDITION_CHECK_MAX_WORKERS)

        if df_result.empty:
            logger.info("📭 조건검색 결과: 조건을 만족하는 종목 없음.")
        else:
            logger.info(f"📈 조건검색 통과 종목 수: {len(df_result)}개")

        return df_result
    
    except Exception as e:
        logger.error(f"❌ 조건검색 중 예외 발생: {e}", exc_info=True)
        return pd.DataFrame()
