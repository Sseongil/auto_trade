# modules/check_conditions_threaded.py

import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging

from modules.Kiwoom.tr_event_loop import TrEventLoop
from modules.common.config import (
    MARKET_CODES,
    EXCLUDE_NAME_KEYWORDS,
    EXCLUDE_STATUS_KEYWORDS,
    MIN_DATA_POINTS,
    CONDITION_CHECK_MAX_WORKERS
)
from modules.kiwoom_query_helper import KiwoomQueryHelper

logger = logging.getLogger(__name__)

def get_daily_data(kiwoom, stock_code):
    try:
        loop = TrEventLoop()
        df = kiwoom.request_opt10081(stock_code, loop)
        if df.empty:
            return None

        df = df.rename(columns={"현재가": "종가", "일자": "날짜"})
        df['종가'] = df['종가'].astype(str) \
                               .str.replace(',', '') \
                               .str.replace('+', '') \
                               .str.replace('-', '') \
                               .astype(int)
        df['날짜'] = pd.to_datetime(df['날짜'])
        df = df.sort_values("날짜").reset_index(drop=True)
        return df

    except Exception as e:
        logger.error(f"[{stock_code}] 일봉 데이터 조회 실패: {e}", exc_info=True)
        return None

def is_passing_conditions(df):
    try:
        if len(df) < MIN_DATA_POINTS:
            return False

        df['MA5'] = df['종가'].rolling(5).mean()
        df['MA20'] = df['종가'].rolling(20).mean()
        df['MA60'] = df['종가'].rolling(60).mean()

        latest = df.iloc[-1]
        prev_high = df['종가'][:-1].max()

        return (
            latest['MA5'] > latest['MA20'] > latest['MA60'] and
            latest['종가'] > prev_high
        )

    except Exception as e:
        logger.error(f"기술적 조건 평가 실패: {e}", exc_info=True)
        return False

def get_filtered_tickers(market, kiwoom):
    try:
        codes = kiwoom.get_code_list_by_market(market)
        result = []

        for code in codes:
            try:
                name = kiwoom.get_stock_name(code)

                if any(keyword in name for keyword in EXCLUDE_NAME_KEYWORDS):
                    continue

                state = kiwoom.get_stock_state(code)
                if any(keyword in state for keyword in EXCLUDE_STATUS_KEYWORDS):
                    continue

                df = get_daily_data(kiwoom, code)
                if df is not None and is_passing_conditions(df):
                    result.append((code, name))

            except Exception as inner_e:
                logger.warning(f"[{code}] 개별 종목 처리 중 오류: {inner_e}", exc_info=True)

        return result

    except Exception as e:
        logger.error(f"[{market}] 필터링 실패: {e}", exc_info=True)
        return []

def run_condition_filter_and_return_df(max_workers=CONDITION_CHECK_MAX_WORKERS):
    try:
        logger.info("🚀 조건검색 스레드 시작")

        kiwoom = KiwoomQueryHelper()  # 로그인 및 OCX 초기화됨
        all_results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(get_filtered_tickers, market, kiwoom): market
                for market in MARKET_CODES
            }

            for future in futures:
                try:
                    result = future.result()
                    all_results.extend(result)
                except Exception as e:
                    logger.error(f"❌ 스레드 작업 실패: {e}", exc_info=True)

        if not all_results:
            logger.info("📭 조건검색 결과: 조건을 만족하는 종목 없음.")
            return pd.DataFrame()

        df = pd.DataFrame(all_results, columns=["ticker", "name"])
        logger.info(f"📈 조건검색 통과 종목 수: {len(df)}개")
        return df

    except Exception as e:
        logger.critical(f"❌ 전체 조건 필터링 실패: {e}", exc_info=True)
        return pd.DataFrame()
