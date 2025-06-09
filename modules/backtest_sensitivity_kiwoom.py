# modules/backtest_sensitivity_kiwoom.py

import os
import pandas as pd
from datetime import datetime, timedelta
import time # Included for potential future use (e.g., API request delays)
from pykiwoom.kiwoom import Kiwoom

# Strategy Parameters
# These lists define the sensitivity ranges for backtesting.
STOP_LOSS_LIST = [-1.0, -2.0, -3.0]      # Percentage loss at which to sell
TAKE_PROFIT_LIST = [3.0, 5.0, 7.0]       # Percentage gain at which to sell
TRAIL_STOP_LIST = [0.5, 1.0, 1.5]        # Percentage below the high to trigger trailing stop
HOLD_DAYS = 5                            # Number of trading days to hold if no stop/profit hit

def get_daily_data(kiwoom_instance, code, verbose=False):
    """
    Fetches daily historical data for a given stock code from Kiwoom.
    The '현재가' column from opt10081 represents the closing price for historical daily data.

    Args:
        kiwoom_instance: An initialized Kiwoom object.
        code (str): The stock ticker code (e.g., "005930").
        verbose (bool): If True, prints detailed progress and warning messages.

    Returns:
        pd.DataFrame: A DataFrame with daily stock data (sorted by date ascending),
                      including a '종가' column, or None if data retrieval fails or is insufficient.
    """
    try:
        df = kiwoom_instance.block_request(
            "opt10081",
            종목코드=code,
            기준일자=datetime.today().strftime("%Y%m%d"), # Using today's date as reference
            수정주가구분=1, # Adjusted price
            output="주식일봉차트조회",
            next=0
        )

        if df is None or df.empty:
            if verbose:
                print(f"⚠️ 경고: {code} 에 대한 일봉 데이터가 없거나 비어 있습니다.")
            return None

        # Kiwoom's '현재가' for opt10081 (daily historical) effectively means '종가'.
        # Clean and convert it to integer, then rename/assign for clarity in simulation.
        df['종가'] = df['현재가'].astype(str).str.replace(',', '').str.replace('+', '').str.replace('-', '').astype(int)
        df = df.sort_index(ascending=True) # Sort by date ascending for simulation
        return df
    except Exception as e:
        print(f"❌ 오류: {code} 일봉 데이터 조회 실패 - {e}")
        return None

def simulate_strategy(df_daily_data, stop_loss_pct, take_profit_pct, trail_stop_pct):
    """
    Simulates a trading strategy on historical data for a single stock.

    Args:
        df_daily_data (pd.DataFrame): DataFrame of daily stock data.
        stop_loss_pct (float): Stop loss percentage (e.g., -1.0 for -1%).
        take_profit_pct (float): Take profit percentage (e.g., 3.0 for +3%).
        trail_stop_pct (float): Trailing stop percentage (e.g., 0.5 for 0.5%).

    Returns:
        tuple: (Return_percentage, Status_message) or (None, Error_message)
    """
    # Ensure sufficient data for entry and at least one day of holding
    if df_daily_data is None or len(df_daily_data) < HOLD_DAYS + 1:
        return None, "데이터 부족 또는 기간 부족"

    try:
        # Define entry price: Using the '종가' (closing price) of the first day in the data window.
        # This simulates buying at the close of the signal day.
        buy_price = df_daily_data["종가"].iloc[0]
        
        # Initial trailing high is the buy price
        trail_high = buy_price

        # Simulate holding for HOLD_DAYS
        for i in range(1, HOLD_DAYS + 1):
            if i >= len(df_daily_data):
                # If we run out of data before HOLD_DAYS, exit at the last available price
                final_price = df_daily_data["종가"].iloc[-1]
                strategy_return = (final_price - buy_price) / buy_price * 100
                return round(strategy_return, 2), "기간종료(데이터부족)"

            current_price = df_daily_data["종가"].iloc[i]
            current_return = (current_price - buy_price) / buy_price * 100
            
            # Update trailing high
            trail_high = max(trail_high, current_price)

            # Check profit/loss conditions
            if current_return >= take_profit_pct:
                return round(current_return, 2), "익절"
            elif current_return <= stop_loss_pct:
                return round(current_return, 2), "손절"
            # Trailing stop condition: price falls X% from the highest point reached
            elif current_price <= trail_high * (1 - trail_stop_pct / 100):
                # Calculate return based on the price that triggered the trailing stop
                trail_stop_return = (current_price - buy_price) / buy_price * 100
                return round(trail_stop_return, 2), "트레일링익절"

        # If none of the conditions are met within HOLD_DAYS, exit at the last day's closing price
        final_price = df_daily_data["종가"].iloc[min(HOLD_DAYS, len(df_daily_data) - 1)]
        strategy_return = (final_price - buy_price) / buy_price * 100
        return round(strategy_return, 2), "보유종료"

    except KeyError as e:
        return None, f"데이터 컬럼 오류: {e}. '종가' 컬럼 확인 필요."
    except IndexError as e:
        return None, f"데이터 인덱스 오류: {e}. 데이터프레임 구조 확인 필요."
    except Exception as e:
        return None, f"전략 시뮬레이션 중 예상치 못한 에러: {e}"

def run_kiwoom_sensitivity_backtest(verbose=True):
    """
    Performs a sensitivity backtest using Kiwoom data for a list of tickers.
    It iterates through predefined stop-loss, take-profit, and trailing stop percentages,
    simulating trades for each stock and calculating overall performance metrics.
    Results are saved to a CSV file.

    Args:
        verbose (bool): If True, prints detailed progress and warning messages during execution.
    """
    print("🚀 키움 증권 전략 민감도 백테스트 시작")

    # Establish Kiwoom connection
    kiwoom = Kiwoom()
    try:
        kiwoom.CommConnect(block=True)
        if not kiwoom.connected:
            print("❌ 키움증권 API 연결 실패. 백테스트를 중단합니다.")
            return
    except Exception as e:
        print(f"❌ 키움증권 CommConnect 중 오류 발생: {e}. 백테스트를 중단합니다.")
        return
    if verbose:
        print("✅ 키움증권 API 연결 성공.")

    # Define path for the buy list
    today_str = datetime.today().strftime("%Y%m%d")
    buy_list_path = os.path.join("data", today_str, "buy_list.csv")

    if not os.path.exists(buy_list_path):
        print(f"❌ 매수 종목 리스트 파일 없음: {buy_list_path}. 백테스트를 중단합니다.")
        return

    try:
        df_tickers = pd.read_csv(buy_list_path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        print(f"⚠️ 경고: {buy_list_path} 파일이 비어 있습니다. 백테스트할 종목이 없습니다.")
        return
    except FileNotFoundError: # This case is already handled by os.path.exists, but good for robustness
        print(f"❌ 매수 종목 리스트 파일을 찾을 수 없습니다: {buy_list_path}. 백테스트를 중단합니다.")
        return
    except Exception as e:
        print(f"❌ 매수 종목 리스트 불러오기 실패: {e}. 백테스트를 중단합니다.")
        return

    # Determine ticker column name (flexible for 'ticker' or '종목코드')
    if "ticker" in df_tickers.columns:
        ticker_list = df_tickers["ticker"].astype(str).str.zfill(6)
    elif "종목코드" in df_tickers.columns:
        ticker_list = df_tickers["종목코드"].astype(str).str.zfill(6)
    else:
        print("❌ 'ticker' 또는 '종목코드' 컬럼을 찾을 수 없습니다. 백테스트를 중단합니다.")
        return

    if ticker_list.empty:
        print("❌ 백테스트할 종목이 없습니다. 'buy_list.csv'를 확인하세요.")
        return

    print(f"📋 총 {len(ticker_list)}개의 종목에 대해 백테스트를 진행합니다.")

    # List to store results of each parameter combination
    all_results = []

    # Iterate through all combinations of strategy parameters
    total_combinations = len(STOP_LOSS_LIST) * len(TAKE_PROFIT_LIST) * len(TRAIL_STOP_LIST)
    current_combination_idx = 0

    for sl in STOP_LOSS_LIST:
        for tp in TAKE_PROFIT_LIST:
            for ts in TRAIL_STOP_LIST:
                current_combination_idx += 1
                if verbose:
                    print(f"\n--- 시뮬레이션 ({current_combination_idx}/{total_combinations}): SL={sl}%, TP={tp}%, TS={ts}% ---")
                
                total_return = 0.0
                win_count = 0
                trade_count = 0
                skipped_stocks = 0

                for i, code in enumerate(ticker_list):
                    if verbose:
                        print(f"  > 종목 ({i+1}/{len(ticker_list)}): {code} 데이터 가져오는 중...", end='\r')
                    data = get_daily_data(kiwoom, code, verbose)
                    if data is None:
                        skipped_stocks += 1
                        continue
                    
                    if verbose:
                        print(f"  > 종목 ({i+1}/{len(ticker_list)}): {code} 시뮬레이션 중...", end='\r')
                    strategy_return, status_message = simulate_strategy(data, sl, tp, ts)
                    
                    if strategy_return is not None:
                        total_return += strategy_return
                        if strategy_return > 0:
                            win_count += 1
                        trade_count += 1
                    else:
                        # Optionally print more detail if verbose is very high
                        # if verbose: print(f"  > {code} 시뮬레이션 실패: {status_message}")
                        skipped_stocks += 1
                
                if trade_count == 0:
                    if verbose:
                        print(f"❌ 이 조합에서는 유효한 거래가 없습니다 (SL={sl}%, TP={tp}%, TS={ts}%).")
                    continue

                avg_return = total_return / trade_count
                win_rate = (win_count / trade_count) * 100 if trade_count > 0 else 0

                all_results.append({
                    "Stop Loss (%)": sl,
                    "Take Profit (%)": tp,
                    "Trailing Stop (%)": ts,
                    "Average Return (%)": round(avg_return, 2),
                    "Win Rate (%)": round(win_rate, 2),
                    "Trade Count": trade_count,
                    "Skipped Stocks": skipped_stocks
                })
                if verbose:
                    print(f"  > 완료: 평균 수익률={avg_return:.2f}%, 승률={win_rate:.2f}% (거래수: {trade_count}, 스킵: {skipped_stocks})")


    if not all_results:
        print("❌ 모든 전략 조합에서 유효한 백테스트 결과가 없습니다.")
        return

    result_df = pd.DataFrame(all_results)
    # Sort by average return and then win rate for best performing strategies
    result_df = result_df.sort_values(
        by=["Average Return (%)", "Win Rate (%)"],
        ascending=[False, False]
    ).reset_index(drop=True)

    # Define output directory and file
    output_dir = os.path.join("backtest_results", today_str)
    os.makedirs(output_dir, exist_ok=True) # Ensure output directory exists
    output_filename = os.path.join(output_dir, "sensitivity_backtest_results.csv")
    
    result_df.to_csv(output_filename, index=False, encoding="utf-8-sig")

    print(f"\n📊 전략 민감도 분석 완료. 결과는 '{output_filename}' 에 저장되었습니다.")
    print("\n--- 상위 10개 전략 ---")
    print(result_df.head(10).to_string(index=False)) # Using .to_string(index=False) for better console display

if __name__ == "__main__":
    run_kiwoom_sensitivity_backtest(verbose=True) # Set to False for less output