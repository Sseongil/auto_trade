# modules/check_conditions_threaded.py

import os
import pandas as pd
from datetime import datetime, timedelta
from pykiwoom.kiwoom import Kiwoom
from concurrent.futures import ThreadPoolExecutor

kiwoom = Kiwoom()
kiwoom.CommConnect(block=True)

def get_filtered_tickers():
    print("📌 전체 종목 로딩 중...")
    codes = kiwoom.GetCodeListByMarket("0") + kiwoom.GetCodeListByMarket("10")
    filtered = []

    for code in codes:
        name = kiwoom.GetMasterCodeName(code)
        if any(keyword in name for keyword in ["스팩", "우", "ETN", "ETF"]):
            continue

        status = kiwoom.GetMasterStockState(code)
        banned = ["관리종목", "투자위험", "투자경고", "거래정지", "정리매매", "우선주", "스팩", "ETF", "ETN", "초저유동성"]
        if any(b in status for b in banned):
            continue

        filtered.append(code)
    print(f"✅ 필터링 완료. 종목 수: {len(filtered)}")
    return filtered

def check_condition(code):
    try:
        df = kiwoom.block_request(
            "opt10081",
            종목코드=code,
            기준일자=datetime.today().strftime("%Y%m%d"),
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

        curr = df["현재가"].iloc[-1]
        ma5, ma20, ma60 = df["MA5"].iloc[-1], df["MA20"].iloc[-1], df["MA60"].iloc[-1]
        if not (ma5 > ma20 > ma60):
            return None

        if curr < df["고가"].iloc[-20:].max():
            return None

        vol = df["거래량"].iloc[-1]
        avg_vol = df["거래량"].iloc[-20:].mean()
        if vol < avg_vol * 2:
            return None

        name = kiwoom.GetMasterCodeName(code)
        return {"ticker": code, "name": name, "price": curr}

    except Exception as e:
        print(f"[ERROR] {code}: {e}")
        return None

def run_condition_filter():
    tickers = get_filtered_tickers()
    print("🧠 조건 필터링 시작...")

    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        for res in executor.map(check_condition, tickers):
            if res:
                results.append(res)

    df = pd.DataFrame(results)
    df.to_csv("buy_list.csv", index=False, encoding="utf-8-sig")
    print(f"🎯 조건 통과 종목 수: {len(df)}")

if __name__ == "__main__":
    run_condition_filter()
