# modules/backtest.py

import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from pykiwoom.kiwoom import Kiwoom

# 경로 보정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

kiwoom = Kiwoom()
kiwoom.CommConnect(block=True)

# ✅ 시뮬레이션: 손절, 익절, 보유 종료
def simulate_stop_loss_take_profit(ticker, start_date, stop_loss=-3.0, take_profit=6.5, hold_days=5):
    df = kiwoom.block_request(
        "opt10081",
        종목코드=ticker,
        기준일자=start_date,
        수정주가구분=1,
        output="주식일봉차트조회",
        next=0
    )

    if df is None or len(df) < hold_days:
        return None, "데이터 부족"

    df = df.sort_index(ascending=True)
    df = df.reset_index(drop=True)

    buy_price = df.loc[0, "현재가"]

    for i in range(1, min(hold_days + 1, len(df))):
        price = df.loc[i, "현재가"]
        change = (price - buy_price) / buy_price * 100

        if change >= take_profit:
            return round(change, 2), f"익절({change:.2f}%)"
        elif change <= stop_loss:
            return round(change, 2), f"손절({change:.2f}%)"

    final_price = df.loc[min(hold_days, len(df) - 1), "현재가"]
    hold_return = (final_price - buy_price) / buy_price * 100
    return round(hold_return, 2), f"보유종료({hold_return:.2f}%)"

# ✅ 백테스트 실행
def run_backtest(input_file="buy_list.csv"):
    try:
        df = pd.read_csv(input_file)

        if "ticker" in df.columns:
            df = df.rename(columns={"ticker": "종목코드", "name": "종목명"})

        today = datetime.today()
        start = (today - timedelta(days=30)).strftime("%Y%m%d")

        results = []
        for _, row in df.iterrows():
            ticker = str(row["종목코드"]).zfill(6)
            name = row["종목명"]
            try:
                ret, status = simulate_stop_loss_take_profit(ticker, start)
                if ret is not None:
                    results.append((ticker, name, ret, status))
            except Exception as e:
                print(f"{name}({ticker}) 에러: {e}")

        result_df = pd.DataFrame(results, columns=["종목코드", "종목명", "수익률(%)", "결과"])
        result_df.to_csv("backtest_result.csv", index=False, encoding="utf-8-sig")

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

