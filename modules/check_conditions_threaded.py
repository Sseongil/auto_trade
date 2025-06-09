# modules/check_conditions_threaded.py

import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from pykiwoom.kiwoom import Kiwoom
from concurrent.futures import ThreadPoolExecutor, as_completed # Import as_completed for progress bar
import time # For potential delays or if thread sleep is needed
import logging # For more structured logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path correction (ensure modules are discoverable)
# Add the directory containing this script to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# Add the parent directory (root of your project) to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# --- Constants for Filtering and Strategy ---
MARKET_CODES = ["0", "10"] # "0": KOSPI, "10": KOSDAQ
EXCLUDE_NAME_KEYWORDS = ["스팩", "우", "ETN", "ETF"]
EXCLUDE_STATUS_KEYWORDS = ["관리종목", "투자위험", "투자경고", "거래정지", "정리매매", "우선주", "스팩", "ETF", "ETN", "초저유동성"]

# Constants for technical analysis
MIN_DATA_POINTS = 60      # Minimum number of daily data points required for analysis
MA_SHORT_PERIOD = 5       # Moving average short period
MA_MEDIUM_PERIOD = 20     # Moving average medium period
MA_LONG_PERIOD = 60       # Moving average long period
VOLUME_AVG_PERIOD = 20    # Period for average volume calculation
VOLUME_MULTIPLIER = 2     # Volume must be this much greater than average volume
HIGH_PRICE_LOOKBACK = 20  # Lookback period for highest price

# --- Kiwoom Connection (managed per thread for robustness) ---
# Global Kiwoom instance is removed. Each thread will create its own.

# Helper function to get daily data (re-used from backtest_sensitivity_kiwoom.py logic)
def get_daily_data(kiwoom_instance, code, num_days=MIN_DATA_POINTS + 5): # Fetch a few extra days for safety
    """
    Fetches daily historical data for a given stock code from Kiwoom.
    The '현재가' column from opt10081 represents the closing price for historical daily data.

    Args:
        kiwoom_instance: An initialized Kiwoom object.
        code (str): The stock ticker code (e.g., "005930").
        num_days (int): The number of recent days to fetch data for.

    Returns:
        pd.DataFrame: A DataFrame with daily stock data (sorted by date ascending),
                      including '종가' column, or None if data retrieval fails or is insufficient.
    """
    try:
        # Requesting daily chart data up to today, for the specified number of days
        df = kiwoom_instance.block_request(
            "opt10081",
            종목코드=code,
            기준일자=datetime.today().strftime("%Y%m%d"), # Reference date for data retrieval
            수정주가구분=1, # Adjusted price
            output="주식일봉차트조회",
            next=0
        )

        if df is None or df.empty:
            logger.debug(f"데이터 경고: {code} 일봉 데이터가 없거나 비어 있습니다.")
            return None

        # Kiwoom's '현재가' for opt10081 (daily historical) means '종가'.
        # Clean and convert it to integer, then rename/assign for clarity.
        df['종가'] = df['현재가'].astype(str).str.replace(',', '').str.replace('+', '').str.replace('-', '').astype(int)
        df['거래량'] = df['거래량'].astype(str).str.replace(',', '').astype(int) # Ensure volume is int

        # Sort by date ascending for consistent time-series analysis
        df = df.sort_index(ascending=True).reset_index(drop=True)

        # Ensure we have enough data points after sorting and potential filtering by Kiwoom
        if len(df) < num_days:
            logger.debug(f"데이터 경고: {code} 데이터 포인트 부족 (필요: {num_days}, 실제: {len(df)})")
            return None

        return df
    except Exception as e:
        logger.error(f"데이터 오류: {code} 일봉 데이터 조회 실패 - {e}")
        return None

def get_filtered_tickers(kiwoom_instance):
    """
    Retrieves all stock tickers from specified markets and filters out
    undesirable stocks based on name keywords and stock status.

    Args:
        kiwoom_instance: An initialized Kiwoom object for master data lookup.

    Returns:
        list: A list of filtered stock ticker codes.
    """
    logger.info("📌 전체 종목 리스트 로딩 중...")
    
    all_codes = []
    for market_code in MARKET_CODES:
        all_codes.extend(kiwoom_instance.GetCodeListByMarket(market_code))
    
    filtered_codes = []

    for code in all_codes:
        try:
            name = kiwoom_instance.GetMasterCodeName(code)
            
            # Filter by name keywords
            if any(keyword in name for keyword in EXCLUDE_NAME_KEYWORDS):
                continue

            # Filter by stock state
            status = kiwoom_instance.GetMasterStockState(code)
            if any(b in status for b in EXCLUDE_STATUS_KEYWORDS):
                continue
            
            filtered_codes.append(code)
        except Exception as e:
            logger.warning(f"마스터 정보 조회 오류: {code} ({kiwoom_instance.GetMasterCodeName(code)}) - {e}")
            continue # Skip this code if master info retrieval fails

    logger.info(f"✅ 초기 필터링 완료. 총 종목 수: {len(filtered_codes)}")
    return filtered_codes

def check_condition_for_thread(code):
    """
    Checks specific technical conditions for a given stock ticker.
    This function is designed to be run in a separate thread.
    A new Kiwoom instance is created and connected for each thread.

    Args:
        code (str): The stock ticker code (e.g., "005930").

    Returns:
        dict: A dictionary containing ticker, name, and current price if conditions are met,
              otherwise None.
    """
    # CRITICAL: Create and connect a new Kiwoom instance for each thread
    # Kiwoom API is NOT thread-safe for a single connection.
    thread_kiwoom = Kiwoom()
    try:
        thread_kiwoom.CommConnect(block=True)
        if not thread_kiwoom.connected:
            logger.error(f"❌ 스레드 Kiwoom 연결 실패: {code}")
            return None
    except Exception as e:
        logger.error(f"❌ 스레드 Kiwoom 연결 중 오류 발생: {code} - {e}")
        return None

    try:
        df_daily_data = get_daily_data(thread_kiwoom, code) # Use the thread-specific Kiwoom instance
        
        if df_daily_data is None:
            return None # get_daily_data already logged warning/error

        # Ensure we have enough data after potential partial fetch
        if len(df_daily_data) < MIN_DATA_POINTS:
            logger.debug(f"{code}: 데이터 포인트 부족 ({len(df_daily_data)} < {MIN_DATA_POINTS})")
            return None

        # Calculate Moving Averages on '종가' (closing price)
        df_daily_data["MA_SHORT"] = df_daily_data["종가"].rolling(window=MA_SHORT_PERIOD).mean()
        df_daily_data["MA_MEDIUM"] = df_daily_data["종가"].rolling(window=MA_MEDIUM_PERIOD).mean()
        df_daily_data["MA_LONG"] = df_daily_data["종가"].rolling(window=MA_LONG_PERIOD).mean()

        # Get latest data points
        curr_price = df_daily_data["종가"].iloc[-1]
        ma_short = df_daily_data["MA_SHORT"].iloc[-1]
        ma_medium = df_daily_data["MA_MEDIUM"].iloc[-1]
        ma_long = df_daily_data["MA_LONG"].iloc[-1]

        # Condition 1: Golden Cross / 정배열 (MA_SHORT > MA_MEDIUM > MA_LONG)
        if not (ma_short > ma_medium > ma_long):
            logger.debug(f"{code}: 정배열 조건 불충족 (MA5:{ma_short:.2f}, MA20:{ma_medium:.2f}, MA60:{ma_long:.2f})")
            return None

        # Condition 2: Current price must be below its 20-day high (potential for rebound)
        # Assuming '고가' is available. '현재가' from opt10081 is the closing price.
        # This condition seems to look for a stock that is NOT at its 20-day high.
        # If the intent is "current price is NOT at its recent high," this is fine.
        # If the intent is "current price is below its *absolute* 20-day high," that would be `curr_price < df_daily_data["고가"].iloc[-HIGH_PRICE_LOOKBACK:].max()`.
        # Assuming "고가" (High Price) column is available and valid from opt10081.
        # Let's assume the original intent means: current price is NOT above its 20-day high.
        # The condition `curr < df["고가"].iloc[-20:].max()` implies that the current price must be *less than* the max high of the last 20 days.
        # This means it's not at a new high, potentially indicating a pullback or consolidation within an uptrend.
        if curr_price >= df_daily_data["고가"].iloc[-HIGH_PRICE_LOOKBACK:].max():
            logger.debug(f"{code}: 최근 20일 고가보다 높거나 같음. (고가: {df_daily_data['고가'].iloc[-HIGH_PRICE_LOOKBACK:].max()}, 현재가: {curr_price})")
            return None

        # Condition 3: Volume check (current day's volume is significantly higher than average)
        current_volume = df_daily_data["거래량"].iloc[-1]
        avg_volume = df_daily_data["거래량"].iloc[-VOLUME_AVG_PERIOD:].mean()

        if current_volume < avg_volume * VOLUME_MULTIPLIER:
            logger.debug(f"{code}: 거래량 조건 불충족 (현재:{current_volume}, 평균:{avg_volume:.0f}, 필요:{avg_volume * VOLUME_MULTIPLIER:.0f})")
            return None
        
        # If all conditions pass, get the stock name and return the result
        stock_name = thread_kiwoom.GetMasterCodeName(code)
        logger.info(f"✅ 조건 통과: {stock_name}({code}) - 가격: {curr_price:,}")
        return {"ticker": code, "name": stock_name, "price": curr_price}

    except Exception as e:
        logger.error(f"조건 검사 오류: {code} - {e}")
        return None
    finally:
        # Ensure Kiwoom connection is closed in the thread if it was opened
        if thread_kiwoom.connected:
            thread_kiwoom.Disconnect()
            logger.debug(f"스레드 Kiwoom 연결 해제: {code}")


def run_condition_filter(output_filename="buy_list.csv", max_workers=6):
    """
    Runs the stock condition filtering process using multithreading.
    Filters stocks, checks technical conditions, and saves the results to a CSV file.

    Args:
        output_filename (str): The base name for the output CSV file (e.g., "buy_list.csv").
                               The actual filename will be date-stamped.
        max_workers (int): The maximum number of threads to use for parallel processing.
    """
    logger.info("🧠 종목 조건 필터링 시작...")

    # Main Kiwoom instance for initial GetCodeList and GetMasterCodeName/State
    main_kiwoom = Kiwoom()
    try:
        main_kiwoom.CommConnect(block=True)
        if not main_kiwoom.connected:
            logger.critical("❌ 메인 Kiwoom API 연결 실패. 스크립트 종료.")
            return
    except Exception as e:
        logger.critical(f"❌ 메인 Kiwoom CommConnect 중 오류 발생: {e}. 스크립트 종료.")
        return
    logger.info("✅ 메인 Kiwoom API 연결 성공.")

    # Step 1: Get all filtered tickers based on name and status
    tickers_to_check = get_filtered_tickers(main_kiwoom)
    if not tickers_to_check:
        logger.warning("🚫 필터링할 종목이 없습니다. 스크립트 종료.")
        main_kiwoom.Disconnect() # Disconnect main Kiwoom
        return

    # Step 2: Check conditions for each ticker using a thread pool
    results = []
    # Use ThreadPoolExecutor for parallel processing
    # Each thread will create and manage its own Kiwoom instance
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks and store futures
        future_to_code = {executor.submit(check_condition_for_thread, code): code for code in tickers_to_check}
        
        # Display progress
        processed_count = 0
        total_tickers = len(tickers_to_check)
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception as exc:
                logger.error(f"종목 {code} 처리 중 예외 발생: {exc}")
            
            processed_count += 1
            # Update progress on the same line
            sys.stdout.write(f"\r🔍 종목 검사 중: {processed_count}/{total_tickers} 완료 ({len(results)}개 통과)")
            sys.stdout.flush()
    sys.stdout.write("\n") # Newline after progress bar

    # Disconnect main Kiwoom instance after all tasks are submitted/completed
    main_kiwoom.Disconnect()
    logger.info("✅ 메인 Kiwoom API 연결 해제.")


    df_result = pd.DataFrame(results)

    # Save results to a date-stamped CSV
    today_str = datetime.today().strftime("%Y%m%d")
    output_dir = os.path.join("data", today_str) # Save in the data/YYYYMMDD directory
    os.makedirs(output_dir, exist_ok=True) # Ensure directory exists
    output_filepath = os.path.join(output_dir, f"{os.path.splitext(output_filename)[0]}_{today_str}.csv") # Add date to filename

    if not df_result.empty:
        df_result.to_csv(output_filepath, index=False, encoding="utf-8-sig")
        logger.info(f"🎯 조건 통과 종목 수: {len(df_result)}. 결과는 '{output_filepath}' 에 저장되었습니다.")
        logger.info("\n--- 조건 통과 상위 10개 종목 ---")
        logger.info(df_result.head(10).to_string(index=False))
    else:
        logger.info("🚫 조건 통과 종목이 없습니다. 'buy_list'가 생성되지 않았습니다.")

    logger.info("--- 종목 조건 필터링 완료 ---")

if __name__ == "__main__":
    run_condition_filter(max_workers=os.cpu_count() or 4) # Adjust max_workers based on CPU cores or desired concurrency