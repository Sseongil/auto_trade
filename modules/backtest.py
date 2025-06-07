# backtest.py
import pandas as pd
from pykrx.stock import get_market_ohlcv_by_date
from datetime import datetime, timedelta

def simulate_stop_loss_take_profit(ticker, start_date, end_date, stop_loss=-3.0, take_profit=6.5, hold_days=5):
    df = get_market_ohlcv_by_date(start_date, end_date, ticker)
    if df.empty or len(df) < hold_days:
        return None, "데이터 부족"

    # 매수가는 첫 번째 날 종가
    buy_price = df.iloc[0]["종가"]

    for i in range(1, hold_days + 1):
        if i >= len(df):
            break
        price = df.iloc[i]["종가"]
        change = (price - buy_price) / buy_price * 100

        if change >= take_profit:
            return round(change, 2), f"익절({change:.2f}%)"
        elif change <= stop_loss:
            return round(change, 2), f"손절({change:.2f}%)"

    # 보유기간 종료, 마지막 날 기준
    final_price = df.iloc[min(hold_days, len(df) - 1)]["종가"]
    hold_return = (final_price - buy_price) / buy_price * 100
    return round(hold_return, 2), f"보유종료({hold_return:.2f}%)"

def run_backtest(input_file="buy_list.csv"):
    try:
        df = pd.read_csv(input_file)

        if "ticker" in df.columns:
            df = df.rename(columns={"ticker": "종목코드", "name": "종목명"})

        today = datetime.today()
        start = (today - timedelta(days=30)).strftime("%Y%m%d")
        end = (today + timedelta(days=5)).strftime("%Y%m%d")

        results = []
        for _, row in df.iterrows():
            ticker = row['종목코드']
            name = row['종목명']
            try:
                ret, status = simulate_stop_loss_take_profit(ticker, start, end)
                if ret is not None:
                    results.append((ticker, name, ret, status))
            except Exception as e:
                print(f"{name}({ticker}) 에러: {e}")

        result_df = pd.DataFrame(results, columns=["종목코드", "종목명", "수익률(%)", "결과"])
        result_df.to_csv("backtest_result.csv", index=False, encoding="utf-8-sig")

        # 통계 출력
        if not result_df.empty:
            print(result_df)
            print("\n📊 전략 요약:")
            print("▶ 평균 수익률:", round(result_df["수익률(%)"].mean(), 2), "%")
            print("▶ 승률:", round((result_df["수익률(%)"] > 0).mean() * 100, 2), "%")
            print("▶ 익절 종목 수:", result_df['결과'].str.contains("익절").sum())
            print("▶ 손절 종목 수:", result_df['결과'].str.contains("손절").sum())
            print("▶ 보유종료 종목 수:", result_df['결과'].str.contains("보유종료").sum())

        return result_df
    except Exception as e:
        print(f"[ERROR] 백테스트 실행 실패: {e}")
        return None

if __name__ == "__main__":
    run_backtest()

