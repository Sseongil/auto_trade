# modules/backtest_sensitivity_kiwoom.py

import os
import pandas as pd
from datetime import datetime, timedelta
from pykiwoom.kiwoom import Kiwoom

# 전략 설정
STOP_LOSS_LIST = [-1.0, -2.0, -3.0]
TAKE_PROFIT_LIST = [3.0, 5.0, 7.0]
TRAIL_STOP_LIST = [0.5, 1.0, 1.5]
HOLD_DAYS = 5

kiwoom = Kiwoom()
kiwoom.CommConnect(block=True)

def get_daily_data(code):
    try:
        df = kiwoom.block_request(
            "opt10081",
            종목코드=code,
            기준일자=datetime.today().strftime("%Y%m%d"),
            수정주가구분=1,
            output="주식일봉차트조회",
            next=0
        )
        df = df.sort_index(ascending=True)
        return df
    except:
        return None

def simulate_strategy(df, stop_loss, take_profit, trail_stop):
    try:
        if df is None or len(df) < HOLD_DAYS + 1:
            return None, "데이터 부족"

        buy_price = df["현재가"].iloc[0]
        trail_high = buy_price

        for i in range(1, HOLD_DAYS + 1):
            if i >= len(df):
                break

            price = df["현재가"].iloc[i]
            change = (price - buy_price) / buy_price * 100
            trail_high = max(trail_high, price)

            if change >= take_profit:
                return round(change, 2), "익절"
            elif change <= stop_loss:
                return round(change, 2), "손절"
            elif price <= trail_high * (1 - trail_stop / 100):
                return round(change, 2), "트레일링익절"

        final_price = df["현재가"].iloc[min(HOLD_DAYS, len(df)-1)]
        hold_return = (final_price - buy_price) / buy_price * 100
        return round(hold_return, 2), "보유종료"

    except Exception as e:
        return None, f"에러: {e}"

def run_kiwoom_sensitivity_backtest():
    today = datetime.today().strftime("%Y%m%d")
    path = os.path.join("data", today, f"buy_list_{today}.csv")
    if not os.path.exists(path):
        print(f"❌ buy_list 파일 없음: {path}")
        return

    df = pd.read_csv(path)
    ticker_list = df["ticker"] if "ticker" in df.columns else df["종목코드"]

    results = []

    for sl in STOP_LOSS_LIST:
        for tp in TAKE_PROFIT_LIST:
            for ts in TRAIL_STOP_LIST:
                total_return = 0
                win_count = 0
                trade_count = 0

                for code in ticker_list:
                    code = str(code).zfill(6)
                    data = get_daily_data(code)
                    result = simulate_strategy(data, sl, tp, ts)
                    if result:
                        r, status = result
                        if r is not None:
                            total_return += r
                            win_count += int(r > 0)
                            trade_count += 1

                if trade_count == 0:
                    continue

                avg_return = total_return / trade_count
                win_rate = win_count / trade_count * 100

                results.append({
                    "손절": sl,
                    "익절": tp,
                    "트레일링": ts,
                    "평균수익률": round(avg_return, 2),
                    "승률": round(win_rate, 2),
                    "거래수": trade_count
                })

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values(by=["평균수익률", "승률"], ascending=[False, False])
    result_df.to_csv("kiwoom_sensitivity_result.csv", index=False, encoding="utf-8-sig")

    print("\n📊 전략 민감도 분석 결과:")
    print(result_df.head(10))

if __name__ == "__main__":
    run_kiwoom_sensitivity_backtest()
