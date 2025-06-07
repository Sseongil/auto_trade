# check_conditions.py
from modules.get_stock_list import get_krx_stock_list
import pandas as pd
from datetime import datetime, timedelta
from pykrx.stock import get_market_ohlcv_by_date

def get_filtered_stocks(df=None):
    if df is None:
        df = get_krx_stock_list()

    if df is None or df.empty:
        print("[ERROR] get_filtered_stocks: 입력된 DataFrame이 비어있습니다.")
        return pd.DataFrame(columns=["ticker", "name"])

    # ✅ 시가총액 상위 500개로 확장
    df = df.sort_values(by="market_cap", ascending=False).head(500)

    result = []

    end_date = datetime.today()
    start_date = end_date - timedelta(days=90)

    for _, row in df.iterrows():
        code = row['ticker']
        name = row['name']

        try:
            ohlcv = get_market_ohlcv_by_date(start_date.strftime("%Y%m%d"),
                                              end_date.strftime("%Y%m%d"),
                                              code)
            if ohlcv.empty or len(ohlcv) < 25:
                continue

            # ✅ 이동평균선 및 엔벨로프
            ma20 = ohlcv['종가'].rolling(window=20).mean()
            upper = ma20 * 1.2
            lower = ma20 * 0.8
            ma5 = ohlcv['종가'].rolling(window=5).mean()

            # ✅ 조건 1: 3개월 내 상단 터치 여부
            touched_upper = (ohlcv['고가'] > upper).any()

            # ✅ 조건 2: 최근 5일 내 하단 터치 여부
            touched_lower_recent = (ohlcv['저가'].iloc[-5:] <= lower.iloc[-5:]).any()

            # ✅ 조건 3: 오늘 종가 > 5일 이동평균
            close_today = ohlcv['종가'].iloc[-1]
            ma5_today = ma5.iloc[-1]
            above_ma5 = close_today > ma5_today

            if touched_upper and touched_lower_recent and above_ma5:
                result.append((code, name))

        except Exception as e:
            print(f"{name}({code}) 에러: {e}")

    return pd.DataFrame(result, columns=["ticker", "name"])

# 단독 실행 시 테스트
if __name__ == "__main__":
    filtered = get_filtered_stocks()
    print(filtered)
    filtered.to_csv("buy_list.csv", index=False, encoding="utf-8-sig")
