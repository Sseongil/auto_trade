# modules/check_conditions_threaded.py

import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging
import time
import traceback # 오류 스택 트레이스 출력을 위해 추가

from modules.Kiwoom.tr_event_loop import TrEventLoop
from modules.common.config import (
    MARKET_CODES,
    EXCLUDE_NAME_KEYWORDS,
    EXCLUDE_STATUS_KEYWORDS,
    MIN_DATA_POINTS,
    CONDITION_CHECK_MAX_WORKERS
)
# KiwoomQueryHelper는 QApplication 인스턴스를 필요로 하므로,
# 실제 실행 환경에서 QApplication이 이미 생성되어 있어야 합니다.
# 여기서는 KiwoomQueryHelper를 인스턴스화할 때 app 인자를 전달해야 합니다.
# local_api_server.py에서 이 함수를 호출할 때 kiwoom_helper 인스턴스를 전달하도록 변경해야 합니다.
# from modules.Kiwoom.kiwoom_query_helper import KiwoomQueryHelper # 직접 임포트 대신 인자로 받도록 변경

logger = logging.getLogger(__name__)

def get_daily_data(kiwoom_helper, stock_code: str) -> pd.DataFrame | None:
    """
    Kiwoom API를 통해 종목의 일봉 데이터를 조회하고 DataFrame으로 반환합니다.
    """
    try:
        today_str = datetime.today().strftime("%Y%m%d")
        # ✅ kiwoom_helper의 request_daily_ohlcv 메서드 사용
        data = kiwoom_helper.request_daily_ohlcv(stock_code, today_str)
        if data and not data.get("error"):
            df = pd.DataFrame(data["data"])
            if "현재가" in df.columns:
                df['종가'] = df['현재가'].astype(str).str.replace(',', '').str.replace('+', '').str.replace('-', '').astype(int)
            else:
                logger.warning(f"[{stock_code}] 일봉 데이터에 '현재가' 컬럼 없음.")
                return None

            df['날짜'] = pd.to_datetime(df['날짜'])
            df = df.sort_values("날짜").reset_index(drop=True)

            return df
        return None
    except Exception as e:
        logger.error(f"get_daily_data 오류 ({stock_code}): {e}", exc_info=True)
        return None

def is_passing_conditions(df: pd.DataFrame) -> bool:
    """
    주어진 일봉 데이터프레임이 기본적인 기술적 분석 조건을 만족하는지 확인합니다.
    이 함수는 예시이며, 실제 전략에 따라 복잡한 로직이 추가될 수 있습니다.
    """
    if len(df) < MIN_DATA_POINTS:
        # logger.debug(f"데이터 포인트 부족: {len(df)} < {MIN_DATA_POINTS}")
        return False

    # 최신 데이터
    latest = df.iloc[-1]
    current_price = latest['종가']
    volume = latest['거래량']

    # 간단한 조건 예시:
    # 1. 최근 5일 이동평균선이 20일 이동평균선 위에 있는지 (골든 크로스 또는 정배열 초기)
    # 2. 최근 거래량이 특정 기준 이상인지
    # 3. 주가가 특정 가격 범위 내에 있는지

    # 이동평균선 계산
    df['MA5'] = df['종가'].rolling(window=5).mean()
    df['MA20'] = df['종가'].rolling(window=20).mean()

    if df['MA5'].iloc[-1] <= df['MA20'].iloc[-1]:
        # logger.debug(f"MA5({df['MA5'].iloc[-1]:.2f}) <= MA20({df['MA20'].iloc[-1]:.2f})")
        return False

    # 거래량 조건 (예: 최근 5일 평균 거래량의 2배 이상)
    avg_volume_5d = df['거래량'].rolling(window=5).mean().iloc[-1]
    if volume < avg_volume_5d * 2:
        # logger.debug(f"거래량 조건 미충족: {volume} < {avg_volume_5d * 2:.0f}")
        return False

    # 주가 범위 조건 (config에서 가져올 수 있음)
    from modules.common.config import MIN_PRICE, MAX_PRICE
    if not (MIN_PRICE <= current_price <= MAX_PRICE):
        # logger.debug(f"가격 범위 미충족: {current_price} (범위: {MIN_PRICE}~{MAX_PRICE})")
        return False

    # 추가적인 복잡한 조건들을 여기에 추가할 수 있습니다.
    # 예: 일목균형표, 볼린저밴드, RSI, MACD 등

    return True

def get_filtered_tickers(kiwoom_helper, market_code: str) -> list:
    """
    특정 시장의 모든 종목 코드를 가져와 이름 및 상태 필터링을 수행합니다.
    """
    filtered_codes_names = []
    try:
        all_codes = kiwoom_helper.get_code_list_by_market(market_code)
        for code in all_codes:
            name = kiwoom_helper.get_stock_name(code)
            if any(keyword in name for keyword in EXCLUDE_NAME_KEYWORDS):
                continue

            # ✅ kiwoom_helper의 get_stock_state 메서드 사용
            state = kiwoom_helper.get_stock_state(code)
            if any(keyword in state for keyword in EXCLUDE_STATUS_KEYWORDS):
                continue
            filtered_codes_names.append((code, name))
    except Exception as e:
        logger.error(f"get_filtered_tickers 오류 (시장 {market_code}): {e}", exc_info=True)
    return filtered_codes_names

def filter_candidate(code: str, name: str, kiwoom_helper) -> dict | None:
    """
    개별 종목에 대해 일봉 데이터를 조회하고 기술적 분석 조건을 검사합니다.
    """
    try:
        df = get_daily_data(kiwoom_helper, code)
        if df is None or len(df) < MIN_DATA_POINTS:
            return None

        # is_passing_conditions 내부에서 이미 필터링되지만, 명시적으로 다시 확인
        if not is_passing_conditions(df):
            return None

        current = df.iloc[-1]['종가']
        return {"ticker": code, "name": name, "price": current}
    except Exception as e:
        logger.error(f"filter_candidate 오류 ({code}): {e}", exc_info=True)
        return None

def run_condition_filter_and_return_df(kiwoom_helper) -> pd.DataFrame:
    """
    조건 검색 필터를 실행하고 결과 DataFrame을 반환합니다.
    스레드 풀을 사용하여 여러 시장의 종목을 병렬로 처리합니다.
    Args:
        kiwoom_helper: 초기화된 KiwoomQueryHelper 인스턴스
    Returns:
        pd.DataFrame: 조건을 통과한 종목들의 데이터프레임
    """
    logger.info("📊 조건검색 실행 시작 (스레드 기반 필터)...")
    candidate_list = []

    with ThreadPoolExecutor(max_workers=CONDITION_CHECK_MAX_WORKERS) as executor:
        futures = []
        for market_code in MARKET_CODES:
            # 각 시장별로 종목 리스트를 가져와서 개별 종목 필터링 작업을 제출
            tickers = get_filtered_tickers(kiwoom_helper, market_code)
            for code, name in tickers:
                futures.append(executor.submit(filter_candidate, code, name, kiwoom_helper))

        # 진행률 표시
        total_tickers_processed = 0
        total_futures = len(futures)
        sys.stdout.write(f"🔍 종목 검사 중: 0/{total_futures} 완료 (0개 통과)")
        sys.stdout.flush()

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                candidate_list.append(result)

            total_tickers_processed += 1
            sys.stdout.write(f"\r🔍 종목 검사 중: {total_tickers_processed}/{total_futures} 완료 ({len(candidate_list)}개 통과)")
            sys.stdout.flush()

    sys.stdout.write("\n") # 진행률 표시 후 줄 바꿈

    if not candidate_list:
        logger.info("📭 조건검색 결과: 조건을 만족하는 종목 없음.")
        return pd.DataFrame()

    df = pd.DataFrame(candidate_list)
    logger.info(f"📈 조건검색 통과 종목 수: {len(df)}개")
    return df