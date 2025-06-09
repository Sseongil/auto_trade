# modules/check_conditions.py

import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from pykiwoom.kiwoom import Kiwoom
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

# Keywords to exclude based on stock name or status (unified list for clarity)
EXCLUDE_KEYWORDS_NAME = ["스팩", "우", "ETN", "ETF", "리츠", "선물"] # Added 리츠, 선물
EXCLUDE_KEYWORDS_STATUS = ["관리종목", "투자위험", "투자경고", "거래정지", "정리매매", "환기종목", "불성실공시"] # Common statuses

# Fundamental filtering criteria
MIN_MARKET_CAP_KRW_BILLION = 500  # Minimum market capitalization in KRW 억 (hundred million)
MAX_MARKET_CAP_KRW_BILLION = 5000 # Maximum market capitalization in KRW 억
MIN_AVG_TRADING_VALUE_KRW = 5_000_000_000 # Minimum average daily trading value in KRW (50억)

# Technical analysis parameters
MIN_DAILY_DATA_POINTS = 60 # Minimum number of daily data points required for MA calculations
MA_SHORT_PERIOD = 5        # Short-term moving average period
MA_MEDIUM_PERIOD = 20      # Medium-term moving average period
MA_LONG_PERIOD = 60        # Long-term moving average period
VOLUME_AVG_PERIOD = 20     # Period for average volume calculation
VOLUME_MULTIPLIER = 2      # Current volume must be this much greater than average
HIGH_PRICE_LOOKBACK = 20   # Lookback period for highest price in the range (for pullback detection)
MAX_VOLATILITY_PCT = 15    # Maximum daily volatility percentage allowed

# Supply/Demand (수급) parameters
SUPPLY_DEMAND_LOOKBACK_DAYS = 3 # Lookback for institutional/foreign net buy (e.g., last 3 days)
MIN_INST_FOREIGN_NET_BUY = 1_000_000_000 # Minimum combined net buy amount (10억 KRW) to get extra score
MIN_LISTING_DAYS = 20 # Minimum days since listing for new stock filter

# ✅ 종목 리스트 가져오기
def get_all_market_tickers(kiwoom_instance):
    """
    Retrieves all stock ticker codes from specified markets (KOSPI, KOSDAQ).

    Args:
        kiwoom_instance: An initialized Kiwoom object.

    Returns:
        list: A concatenated list of all stock ticker codes.
    """
    logger.info("📌 전체 시장 종목 코드 로딩 중...")
    all_codes = []
    for market_code in MARKET_CODES:
        all_codes.extend(kiwoom_instance.GetCodeListByMarket(market_code))
    logger.info(f"✅ 총 {len(all_codes)}개의 종목 코드 로드 완료.")
    return all_codes

# ✅ 개별 종목 조건 확인
def check_stock_conditions(kiwoom_instance, code, today_str):
    """
    Checks various fundamental and technical conditions for a single stock.

    Args:
        kiwoom_instance: An initialized Kiwoom object (assumed to be connected).
        code (str): The stock ticker code.
        today_str (str): Current date in YYYYMMDD format.

    Returns:
        dict: A dictionary of stock details if all conditions are met, otherwise None.
    """
    try:
        name = kiwoom_instance.GetMasterCodeName(code)

        # 1. Basic Filters (Name and Status)
        # Check name keywords
        if any(keyword in name for keyword in EXCLUDE_KEYWORDS_NAME):
            logger.debug(f"{code} ({name}): 이름 필터에 걸림 ({[k for k in EXCLUDE_KEYWORDS_NAME if k in name]})")
            return None
        
        # Check stock status (관리종목, 거래정지 등)
        status_info = kiwoom_instance.GetMasterStockState(code)
        if any(keyword in status_info for keyword in EXCLUDE_KEYWORDS_STATUS):
            logger.debug(f"{code} ({name}): 상태 필터에 걸림 ({[k for k in EXCLUDE_KEYWORDS_STATUS if k in status_info]})")
            return None

        # 2. Daily Data (opt10081)
        df_daily = kiwoom_instance.block_request(
            "opt10081",
            종목코드=code,
            기준일자=today_str,
            수정주가구분=1,
            output="주식일봉차트조회",
            next=0
        )
        if df_daily is None or df_daily.empty:
            logger.debug(f"{code} ({name}): 일봉 데이터 없음 또는 비어 있음.")
            return None

        # Clean and convert relevant columns
        df_daily['종가'] = df_daily['현재가'].astype(str).str.replace(',', '').str.replace('+', '').str.replace('-', '').astype(int)
        df_daily['거래량'] = df_daily['거래량'].astype(str).str.replace(',', '').astype(int)
        df_daily['고가'] = df_daily['고가'].astype(str).str.replace(',', '').astype(int) # Ensure '고가' is int
        df_daily['저가'] = df_daily['저가'].astype(str).str.replace(',', '').astype(int) # Ensure '저가' is int

        # Sort by date ascending
        df_daily = df_daily.sort_index(ascending=True).reset_index(drop=True)

        # Check for minimum data points after sorting
        if len(df_daily) < MIN_DAILY_DATA_POINTS:
            logger.debug(f"{code} ({name}): 일봉 데이터 부족 ({len(df_daily)}개 < {MIN_DAILY_DATA_POINTS}개)")
            return None

        # 3. Technical Indicators Calculation
        df_daily["MA_SHORT"] = df_daily["종가"].rolling(window=MA_SHORT_PERIOD).mean()
        df_daily["MA_MEDIUM"] = df_daily["종가"].rolling(window=MA_MEDIUM_PERIOD).mean()
        df_daily["MA_LONG"] = df_daily["종가"].rolling(window=MA_LONG_PERIOD).mean()
        
        # Ensure moving averages are calculated (handle NaN for initial rows)
        if pd.isna(df_daily["MA_LONG"].iloc[-1]):
            logger.debug(f"{code} ({name}): 이동평균선 계산에 필요한 데이터 부족.")
            return None

        # Get latest values
        curr_price = df_daily["종가"].iloc[-1]
        ma_short = df_daily["MA_SHORT"].iloc[-1]
        ma_medium = df_daily["MA_MEDIUM"].iloc[-1]
        ma_long = df_daily["MA_LONG"].iloc[-1]

        # 4. Technical Conditions
        # Golden Cross / 정배열: Short MA > Medium MA > Long MA
        if not (ma_short > ma_medium > ma_long):
            logger.debug(f"{code} ({name}): 정배열 조건 불충족 (MA5:{ma_short:.2f}, MA20:{ma_medium:.2f}, MA60:{ma_long:.2f})")
            return None
        
        # Price below recent high (potential pullback/consolidation in uptrend)
        # Condition: Current price is NOT strictly greater than the max high of the last HIGH_PRICE_LOOKBACK days.
        # This implies: Current price <= max high of last N days.
        # This filters out stocks making *new* N-day highs today, focusing on those in a pullback or consolidation phase.
        recent_high = df_daily["고가"].iloc[-HIGH_PRICE_LOOKBACK:].max()
        if curr_price >= recent_high: # Adjusted logic for clarity: if current price is >= recent high, it fails this filter
            logger.debug(f"{code} ({name}): 현재가가 최근 {HIGH_PRICE_LOOKBACK}일 고가보다 높거나 같음 (현재:{curr_price}, 최고:{recent_high})")
            return None

        # Volume Check: Current volume significantly higher than average
        curr_vol = df_daily["거래량"].iloc[-1]
        avg_vol = df_daily["거래량"].iloc[-VOLUME_AVG_PERIOD:-1].mean() # Exclude today's volume from avg
        if avg_vol == 0 or curr_vol < avg_vol * VOLUME_MULTIPLIER:
            logger.debug(f"{code} ({name}): 거래량 조건 불충족 (현재:{curr_vol}, 평균:{avg_vol:.0f}, 필요:{avg_vol * VOLUME_MULTIPLIER:.0f})")
            return None

        # Trading Value Check: Ensure sufficient liquidity
        df_daily["거래대금"] = df_daily["종가"] * df_daily["거래량"] # Use '종가' for consistent calculation
        curr_value = df_daily["거래대금"].iloc[-1]
        avg_value = df_daily["거래대금"].iloc[-VOLUME_AVG_PERIOD:-1].mean() # Exclude today's value from avg
        if avg_value < MIN_AVG_TRADING_VALUE_KRW:
            logger.debug(f"{code} ({name}): 평균 거래대금 최소치 미달 (평균:{avg_value:.0f} KRW)")
            return None
        # Original code had `curr_value < avg_value * 2` for trading value,
        # which is somewhat redundant with volume check. Keeping it if it's a specific rule.
        # If the intent is "current trading value must be at least twice the average," keep it.
        # If it's just about liquidity, `MIN_AVG_TRADING_VALUE_KRW` is primary.
        # Let's keep it for now as a separate filter.
        if curr_value < avg_value * VOLUME_MULTIPLIER: # Reusing VOLUME_MULTIPLIER for consistency
            logger.debug(f"{code} ({name}): 현재 거래대금이 평균의 {VOLUME_MULTIPLIER}배 미달 (현재:{curr_value}, 평균:{avg_value:.0f})")
            return None

        # Volatility Check: Prevent excessively volatile stocks
        high_price = df_daily["고가"].iloc[-1]
        low_price = df_daily["저가"].iloc[-1]
        if low_price == 0: # Avoid division by zero
            logger.debug(f"{code} ({name}): 당일 저가 0원 (비정상 데이터)")
            return None
        volatility = ((high_price - low_price) / low_price) * 100
        if volatility > MAX_VOLATILITY_PCT:
            logger.debug(f"{code} ({name}): 당일 변동성 과다 ({volatility:.2f}% > {MAX_VOLATILITY_PCT}%)")
            return None

        # 5. Fundamental Filters (Market Cap and Listing Date)
        # Market Capitalization (opt10001)
        base_info = kiwoom_instance.block_request("opt10001", 종목코드=code, output="주식기본정보", next=0)
        if base_info is None or base_info.empty:
            logger.debug(f"{code} ({name}): 주식기본정보 조회 실패.")
            return None
        
        market_cap_raw = str(base_info["시가총액"].iloc[0]).replace(",", "")
        if not market_cap_raw.isdigit():
            logger.warning(f"{code} ({name}): 시가총액 데이터 형식 오류: {market_cap_raw}")
            return None
        market_cap = int(market_cap_raw) / 1e8 # Convert to 억 원 단위

        if not (MIN_MARKET_CAP_KRW_BILLION <= market_cap <= MAX_MARKET_CAP_KRW_BILLION):
            logger.debug(f"{code} ({name}): 시가총액 범위 불충족 ({market_cap:.1f}억)")
            return None

        # Listing Date Filter
        list_date_str = kiwoom_instance.GetMasterListedStockDate(code)
        if not list_date_str: # Check if string is empty
            logger.warning(f"{code} ({name}): 상장일 정보 없음.")
            return None

        list_dt = datetime.strptime(list_date_str, "%Y%m%d")
        if (datetime.today() - list_dt).days < MIN_LISTING_DAYS:
            logger.debug(f"{code} ({name}): 상장일 {MIN_LISTING_DAYS}일 미만 (상장일:{list_date_str})")
            return None

        # 6. Supply/Demand (수급) (opt10059)
        supply_demand_df = kiwoom_instance.block_request(
            "opt10059",
            종목코드=code,
            기준일자=today_str,
            수정주가구분=1, # This parameter is usually for opt10081, but harmless here
            output="일별기관매매종목",
            next=0
        )
        # We need at least SUPPLY_DEMAND_LOOKBACK_DAYS of data
        if supply_demand_df is None or len(supply_demand_df) < SUPPLY_DEMAND_LOOKBACK_DAYS:
            logger.debug(f"{code} ({name}): 수급 데이터 부족 ({len(supply_demand_df)}개 < {SUPPLY_DEMAND_LOOKBACK_DAYS}개)")
            return None

        # Sum net buy/sell for the last N days
        inst_sum = 0
        fore_sum = 0
        for i in range(SUPPLY_DEMAND_LOOKBACK_DAYS):
            try:
                inst_sum += int(str(supply_demand_df["기관합계"].iloc[i]).replace(",", ""))
                fore_sum += int(str(supply_demand_df["외국인합계"].iloc[i]).replace(",", ""))
            except ValueError:
                logger.warning(f"{code} ({name}): 수급 데이터 변환 오류 (기관/외국인합계) - {supply_demand_df.iloc[i]}")
                # Treat as zero if data is malformed
                continue

        # Condition: At least one of Inst or Foreign is net buying, OR combined net buy is significant
        if inst_sum <= 0 and fore_sum <= 0:
            logger.debug(f"{code} ({name}): 기관({inst_sum}) 및 외국인({fore_sum}) 순매수 없음.")
            return None

        # 7. Scoring (for prioritizing results)
        score = 0
        if inst_sum > 0: score += 1
        if fore_sum > 0: score += 1
        if inst_sum + fore_sum >= MIN_INST_FOREIGN_NET_BUY: score += 1 # Check combined net buy amount

        # If all conditions met, return stock details
        logger.info(f"✅ 조건 통과: {name}({code}) - 시총: {market_cap:.1f}억, 점수: {score}")
        return {
            "ticker": code,
            "name": name,
            "score": score,
            "curr_price": curr_price,
            "market_cap(억)": round(market_cap, 1),
            "value(억)": round(curr_value / 1e8, 1), # Trading value in 억 KRW
            "volume": curr_vol,
            "inst_net": inst_sum,
            "fore_net": fore_sum
        }

    except Exception as e:
        logger.error(f"❌ 종목 {code} ({name if 'name' in locals() else 'Unknown'}): 조건 검사 중 오류 발생 - {e}", exc_info=False) # exc_info=True for full traceback
        return None

# ✅ 전체 종목 필터링 실행
def run_all_stock_conditions_filter(output_filename="buy_list.csv", verbose=True):
    """
    Executes the comprehensive stock filtering process for all market tickers.
    Connects to Kiwoom, retrieves stock data, applies various conditions,
    and saves the filtered results to a date-stamped CSV file.

    Args:
        output_filename (str): The base name for the output CSV file (e.g., "buy_list.csv").
                               The actual filename will be date-stamped.
        verbose (bool): If True, enables detailed logging.
    """
    if verbose:
        logger.setLevel(logging.DEBUG) # Set logging level to DEBUG for verbose output
    else:
        logger.setLevel(logging.INFO) # Set logging level to INFO for less output

    logger.info("🚀 전체 종목 조건 필터링 시작")

    # Establish Kiwoom connection
    kiwoom = Kiwoom()
    try:
        kiwoom.CommConnect(block=True)
        if not kiwoom.connected:
            logger.critical("❌ 키움증권 API 연결 실패. 스크립트 종료.")
            return None
    except Exception as e:
        logger.critical(f"❌ 키움증권 CommConnect 중 오류 발생: {e}. 스크립트 종료.")
        return None
    logger.info("✅ 키움증권 API 연결 성공.")

    today_str = datetime.today().strftime("%Y%m%d")

    # Step 1: Get all tickers from KOSPI and KOSDAQ
    all_tickers = get_all_market_tickers(kiwoom)
    if not all_tickers:
        logger.warning("🚫 필터링할 종목이 없습니다. 스크립트 종료.")
        kiwoom.Disconnect()
        return None
    
    logger.info(f"📋 총 {len(all_tickers)}개의 종목에 대해 조건 검사를 진행합니다.")

    # Step 2: Check conditions for each ticker sequentially
    results_list = []
    processed_count = 0
    passed_count = 0

    for code in all_tickers:
        processed_count += 1
        # Update progress on the same line
        sys.stdout.write(f"\r🔍 종목 검사 중: {processed_count}/{len(all_tickers)} 완료 ({passed_count}개 통과)")
        sys.stdout.flush()

        result = check_stock_conditions(kiwoom, code, today_str)
        if result:
            results_list.append(result)
            passed_count += 1

    sys.stdout.write("\n") # Newline after progress bar
    logger.info(f"✅ 조건 검사 완료. 총 {len(results_list)}개 종목이 조건을 통과했습니다.")

    # Disconnect Kiwoom instance
    kiwoom.Disconnect()
    logger.info("✅ 키움증권 API 연결 해제.")

    if not results_list:
        logger.info("🚫 조건을 통과한 종목이 없습니다. 'buy_list'가 생성되지 않았습니다.")
        return None

    df_filtered = pd.DataFrame(results_list)
    df_filtered = df_filtered.sort_values(by="score", ascending=False).reset_index(drop=True)

    # Save results to a date-stamped CSV
    output_dir = os.path.join("data", today_str) # Save in the data/YYYYMMDD directory
    os.makedirs(output_dir, exist_ok=True) # Ensure directory exists
    output_filepath = os.path.join(output_dir, f"{os.path.splitext(output_filename)[0]}_{today_str}.csv") # Add date to filename
    
    df_filtered.to_csv(output_filepath, index=False, encoding="utf-8-sig")

    logger.info(f"📊 필터링 결과 저장 완료: '{output_filepath}'")
    logger.info("\n--- 조건 통과 상위 10개 종목 ---")
    logger.info(df_filtered.head(10).to_string(index=False))
    
    return df_filtered

if __name__ == "__main__":
    run_all_stock_conditions_filter(verbose=True) # Set verbose=False for less detailed output