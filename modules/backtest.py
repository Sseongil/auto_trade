# modules/backtest.py

import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from pykiwoom.kiwoom import Kiwoom

# Path correction (ensure modules are discoverable)
# Add the directory containing this script to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# Add the parent directory (root of your project) to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# --- Strategy Parameters (Can be moved to a config file if needed) ---
DEFAULT_STOP_LOSS = -3.0  # Default stop loss percentage
DEFAULT_TAKE_PROFIT = 6.5 # Default take profit percentage
DEFAULT_HOLD_DAYS = 5     # Default number of days to hold if no conditions met
HISTORICAL_DAYS_FETCH = 30 # Number of past days to fetch for a ticker to ensure sufficient data

# ✅ 시뮬레이션: 손절, 익절, 보유 종료 (with improved data handling and clarity)
def simulate_strategy_simple(kiwoom_instance, ticker, date_to_simulate, stop_loss_pct, take_profit_pct, hold_days, verbose=False):
    """
    Simulates a simple stop-loss/take-profit strategy for a single ticker.
    Fetches historical daily data starting from 'date_to_simulate' and applies the strategy.

    Args:
        kiwoom_instance: An initialized Kiwoom object.
        ticker (str): The stock ticker code (e.g., "005930").
        date_to_simulate (str): The date from which to start fetching data (e.g., "YYYYMMDD").
                                This is assumed to be the entry date.
        stop_loss_pct (float): Stop loss percentage (e.g., -3.0 for -3%).
        take_profit_pct (float): Take profit percentage (e.g., 6.5 for +6.5%).
        hold_days (int): Maximum number of days to hold the position.
        verbose (bool): If True, prints detailed messages.

    Returns:
        tuple: (Return_percentage, Status_message) or (None, Error_message)
    """
    try:
        # Fetch data. '기준일자' in opt10081 is the start date for historical data retrieval.
        # Fetching enough days to cover the holding period plus some buffer.
        # We need data *after* the entry date to simulate holding.
        df_raw = kiwoom_instance.block_request(
            "opt10081",
            종목코드=ticker,
            기준일자=date_to_simulate,
            수정주가구분=1,
            output="주식일봉차트조회",
            next=0
        )

        if df_raw is None or df_raw.empty:
            if verbose:
                print(f"⚠️ 경고: {ticker} 에 대한 일봉 데이터가 없거나 비어 있습니다. (시작일: {date_to_simulate})")
            return None, "데이터 부족"

        # Kiwoom's '현재가' for opt10081 (daily historical) effectively means '종가'.
        # Clean and convert '현재가' to integer, and rename it to '종가' for clarity.
        df_raw['종가'] = df_raw['현재가'].astype(str).str.replace(',', '').str.replace('+', '').str.replace('-', '').astype(int)
        
        # Sort data by date ascending (oldest to newest)
        df_raw = df_raw.sort_index(ascending=True).reset_index(drop=True)

        # Ensure we have enough data points.
        # We need at least 1 day for entry and then 'hold_days' for potential holding.
        # So, total of 'hold_days + 1' data points starting from the entry day.
        if len(df_raw) < hold_days + 1:
            if verbose:
                print(f"⚠️ 경고: {ticker} 에 대한 데이터가 부족합니다. (필요: {hold_days+1}개, 실제: {len(df_raw)}개)")
            return None, "데이터 부족"

        # The buy price is the closing price of the entry day (first day in the dataframe)
        buy_price = df_raw.loc[0, "종가"]

        # Simulate holding over the next days
        # The loop starts from the next day after entry (index 1)
        for i in range(1, min(hold_days + 1, len(df_raw))):
            current_price = df_raw.loc[i, "종가"]
            current_return_pct = (current_price - buy_price) / buy_price * 100

            if current_return_pct >= take_profit_pct:
                return round(current_return_pct, 2), f"익절({current_return_pct:.2f}%)"
            elif current_return_pct <= stop_loss_pct:
                return round(current_return_pct, 2), f"손절({current_return_pct:.2f}%)"

        # If conditions are not met within hold_days, exit at the closing price of the last hold day
        # Ensure we don't go out of bounds if df_raw somehow gets truncated
        final_price_index = min(hold_days, len(df_raw) - 1)
        final_price = df_raw.loc[final_price_index, "종가"]
        
        hold_return_pct = (final_price - buy_price) / buy_price * 100
        return round(hold_return_pct, 2), f"보유종료({hold_return_pct:.2f}%)"

    except KeyError as e:
        print(f"❌ 오류: {ticker} 데이터 컬럼 문제 - {e}. '종가' 컬럼 확인 필요.")
        return None, f"컬럼 오류: {e}"
    except IndexError as e:
        print(f"❌ 오류: {ticker} 데이터 인덱스 문제 - {e}. 데이터프레임 구조 확인 필요.")
        return None, f"인덱스 오류: {e}"
    except Exception as e:
        print(f"❌ 오류: {ticker} 시뮬레이션 중 예상치 못한 에러: {e}")
        return None, f"예상치 못한 에러: {e}"

# ✅ 백테스트 실행 (with improved error handling, pathing, and progress)
def run_backtest(input_filename="buy_list.csv", verbose=True):
    """
    Executes a backtest on a list of stocks from a CSV file.
    It simulates a simple stop-loss/take-profit strategy for each stock.

    Args:
        input_filename (str): The name of the CSV file containing ticker information.
                              Assumes file is in data/YYYYMMDD/ directory.
        verbose (bool): If True, prints detailed progress and error messages.

    Returns:
        pd.DataFrame: A DataFrame containing the backtest results, or None if an error occurs.
    """
    print("🚀 단일 전략 백테스트 시작")

    # Establish Kiwoom connection
    kiwoom = Kiwoom()
    try:
        kiwoom.CommConnect(block=True)
        if not kiwoom.connected:
            print("❌ 키움증권 API 연결 실패. 백테스트를 중단합니다.")
            return None
    except Exception as e:
        print(f"❌ 키움증권 CommConnect 중 오류 발생: {e}. 백테스트를 중단합니다.")
        return None
    if verbose:
        print("✅ 키움증권 API 연결 성공.")

    # Determine the path for the input buy list
    today_str = datetime.today().strftime("%Y%m%d")
    input_file_path = os.path.join("data", today_str, input_filename)

    if not os.path.exists(input_file_path):
        print(f"❌ 매수 종목 리스트 파일 없음: {input_file_path}. 백테스트를 중단합니다.")
        return None

    try:
        df_tickers = pd.read_csv(input_file_path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        print(f"⚠️ 경고: {input_file_path} 파일이 비어 있습니다. 백테스트할 종목이 없습니다.")
        return None
    except FileNotFoundError: # Already checked by os.path.exists, but good for robustness
        print(f"❌ 매수 종목 리스트 파일을 찾을 수 없습니다: {input_file_path}. 백테스트를 중단합니다.")
        return None
    except Exception as e:
        print(f"❌ 매수 종목 리스트 불러오기 실패: {e}. 백테스트를 중단합니다.")
        return None

    # Handle flexible column names for ticker and name
    if "ticker" in df_tickers.columns:
        df_tickers = df_tickers.rename(columns={"ticker": "종목코드", "name": "종목명"})
    elif "종목코드" not in df_tickers.columns:
        print("❌ 입력 파일에 'ticker' 또는 '종목코드' 컬럼을 찾을 수 없습니다. 백테스트를 중단합니다.")
        return None

    # Ensure ticker codes are correctly formatted (6-digit zero-padded string)
    df_tickers["종목코드"] = df_tickers["종목코드"].astype(str).str.zfill(6)

    if df_tickers.empty:
        print("❌ 백테스트할 종목이 없습니다. 'buy_list.csv'를 확인하세요.")
        return None
    
    print(f"📋 총 {len(df_tickers)}개의 종목에 대해 백테스트를 진행합니다.")

    # Calculate start_date for fetching data: today - historical_days_fetch.
    # This ensures we get enough data to simulate 'hold_days' into the past from the entry date.
    # Note: For actual event-driven backtesting, you'd iterate through historical entry dates.
    # Here, 'date_to_simulate' means the *first day* of the data series needed for simulation.
    data_fetch_start_date = (datetime.today() - timedelta(days=HISTORICAL_DAYS_FETCH)).strftime("%Y%m%d")

    results_list = []
    skipped_stocks_count = 0
    
    # Iterate through each ticker in the buy list
    for i, row in df_tickers.iterrows():
        ticker = row["종목코드"]
        name = row["종목명"]
        
        if verbose:
            print(f"  > 종목 ({i+1}/{len(df_tickers)}): {name}({ticker}) 시뮬레이션 중...", end='\r')

        # Run the simulation for the current ticker with default strategy parameters
        ret, status = simulate_strategy_simple(
            kiwoom,
            ticker,
            data_fetch_start_date, # This is the starting point for fetching data for simulation
            DEFAULT_STOP_LOSS,
            DEFAULT_TAKE_PROFIT,
            DEFAULT_HOLD_DAYS,
            verbose
        )

        if ret is not None:
            results_list.append((ticker, name, ret, status))
        else:
            skipped_stocks_count += 1
            if verbose:
                print(f"  > 종목 ({i+1}/{len(df_tickers)}): {name}({ticker}) 시뮬레이션 실패: {status}")

    print(f"\n✅ 백테스트 완료. 총 {len(df_tickers) - skipped_stocks_count}개 종목 시뮬레이션. ({skipped_stocks_count}개 스킵)")


    if not results_list:
        print("❌ 모든 종목에서 유효한 백테스트 결과가 없습니다.")
        return None

    result_df = pd.DataFrame(results_list, columns=["종목코드", "종목명", "수익률(%)", "결과"])

    # Define output directory and file
    output_dir = os.path.join("backtest_results", today_str)
    os.makedirs(output_dir, exist_ok=True) # Ensure output directory exists
    output_filename = os.path.join(output_dir, f"backtest_result_{today_str}.csv")
    
    result_df.to_csv(output_filename, index=False, encoding="utf-8-sig")

    print(f"\n📊 백테스트 결과 저장 완료: '{output_filename}'")
    print("\n--- 전략 요약 ---")
    
    # Calculate and print summary statistics
    total_avg_return = result_df["수익률(%)"].mean()
    win_rate = (result_df["수익률(%)"] > 0).mean() * 100
    num_take_profit = result_df['결과'].str.contains("익절").sum()
    num_stop_loss = result_df['결과'].str.contains("손절").sum()
    num_hold_end = result_df['결과'].str.contains("보유종료").sum()

    print(f"▶ 전체 평균 수익률: {total_avg_return:.2f}%")
    print(f"▶ 전체 승률: {win_rate:.2f}%")
    print(f"▶ 익절 종목 수: {num_take_profit}")
    print(f"▶ 손절 종목 수: {num_stop_loss}")
    print(f"▶ 보유 종료 종목 수: {num_hold_end}")
    print(f"▶ 총 시뮬레이션 거래 수: {len(results_list)}")

    print("\n--- 상위 10개 종목 ---")
    print(result_df.sort_values(by="수익률(%)", ascending=False).head(10).to_string(index=False))

    print("\n--- 하위 10개 종목 ---")
    print(result_df.sort_values(by="수익률(%)", ascending=True).head(10).to_string(index=False))

    return result_df

if __name__ == "__main__":
    run_backtest(verbose=True) # Set verbose=False for less console output