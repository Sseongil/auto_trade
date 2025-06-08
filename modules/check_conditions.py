# modules/check_conditions.py

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

MIN_MARKET_CAP = 500         # 억 원
MAX_MARKET_CAP = 5000
MIN_VALUE = 5_000_000_000    # 평균 거래대금 최소
today = datetime.today().strftime("%Y%m%d")

# ✅ 종목 리스트
def get_tickers():
    kospi = kiwoom.GetCodeListByMarket("0")
    kosdaq = kiwoom.GetCodeListByMarket("10")
    return kospi + kosdaq

# ✅ 개별 종목 조건 확인
def check_conditions(code):
    try:
        name = kiwoom.GetMasterCodeName(code)

        # 필터: ETF, 스팩, 우선주, 관리종목, 거래정지
        if "스팩" in name or "우선주" in name:
            return None
        info = kiwoom.GetMasterConstruction(code)
        if "관리" in info or "정지" in info:
            return None

        # 일봉 데이터
        df = kiwoom.block_request(
            "opt10081",
            종목코드=code,
            기준일자=today,
            수정주가구분=1,
            output="주식일봉차트조회",
            next=0
        )
        if df is None or len(df) < 60:
            return None

        df = df.sort_index(ascending=True)
        df["MA5"] = df["현재가"].rolling(window=5).mean()
        df["MA20"] = df["현재가"].rolling(window=20).mean()
        df["MA60"] = df["현재가"].rolling(window=60).mean()

        ma5, ma20, ma60 = df["MA5"].iloc[-1], df["MA20"].iloc[-1], df["MA60"].iloc[-1]
        curr_price = df["현재가"].iloc[-1]

        if not (ma5 > ma20 > ma60):
            return None
        if not (curr_price > df["고가"].iloc[-20:].max()):
            return None

        curr_vol = df["거래량"].iloc[-1]
        avg_vol = df["거래량"].iloc[-20:].mean()
        if curr_vol < avg_vol * 2:
            return None

        df["거래대금"] = df["현재가"] * df["거래량"]
        curr_value = df["거래대금"].iloc[-1]
        avg_value = df["거래대금"].iloc[-20:].mean()
        if curr_value < avg_value * 2 or avg_value < MIN_VALUE:
            return None

        high, low = df["고가"].iloc[-1], df["저가"].iloc[-1]
        volatility = ((high - low) / low) * 100
        if volatility > 15:
            return None

        # 기본정보 조회
        base = kiwoom.block_request("opt10001", 종목코드=code, output="주식기본정보", next=0)
        market_cap_raw = base["시가총액"][0].replace(",", "")
        market_cap = int(market_cap_raw) / 1e8  # 억원 단위

        if not (MIN_MARKET_CAP <= market_cap <= MAX_MARKET_CAP):
            return None

        # 상장일 필터
        list_date = kiwoom.GetMasterListedStockDate(code)
        list_dt = datetime.strptime(list_date, "%Y%m%d")
        if (datetime.today() - list_dt).days < 20:
            return None

        # 수급 (기관/외국인)
        supply = kiwoom.block_request(
            "opt10059",
            종목코드=code,
            기준일자=today,
            수정주가구분=1,
            output="일별기관매매종목",
            next=0
        )
        if supply is None or len(supply) < 3:
            return None

        inst_sum = sum(int(str(supply["기관합계"][i]).replace(",", "")) for i in range(3))
        fore_sum = sum(int(str(supply["외국인합계"][i]).replace(",", "")) for i in range(3))
        if inst_sum <= 0 and fore_sum <= 0:
            return None

        score = 0
        if inst_sum > 0: score += 1
        if fore_sum > 0: score += 1
        if inst_sum + fore_sum > 1_000_000_000: score += 1

        return {
            "ticker": code,
            "name": name,
            "score": score,
            "curr_price": curr_price,
            "market_cap(억)": round(market_cap, 1),
            "value": round(curr_value / 1e8, 1),
            "volume": curr_vol
        }

    except Exception as e:
        print(f"[ERROR] {code} 오류: {e}")
        return None

# ✅ 전체 실행
def filter_all_stocks():
    tickers = get_tickers()
    results = []

    for code in tickers:
        result = check_conditions(code)
        if result:
            results.append(result)

    df = pd.DataFrame(results)
    df = df.sort_values(by="score", ascending=False)
    df.to_csv("buy_list.csv", index=False, encoding="utf-8-sig")
    print(f"✅ 필터링 완료 - 종목 수: {len(df)}")
    return df

if __name__ == "__main__":
    filter_all_stocks()
