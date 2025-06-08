# modules/real_time_watcher.py

import os
import sys
import time
import pandas as pd
from datetime import datetime
from pykiwoom.kiwoom import Kiwoom

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.notify import send_telegram_message
from modules.trade_logger import log_trade
from modules.trade_manager import add_position
from modules.config import calculate_quantity

kiwoom = Kiwoom()
kiwoom.CommConnect(block=True)
account = kiwoom.GetLoginInfo("ACCNO")[0]

def get_watchlist():
    kosdaq = kiwoom.GetCodeListByMarket("10")
    kospi = kiwoom.GetCodeListByMarket("0")
    return kosdaq + kospi

def load_existing_positions():
    path = os.path.join("data", "positions.csv")
    if not os.path.exists(path):
        return set()
    df = pd.read_csv(path, encoding="utf-8-sig")
    # 👉 수량이 0인 경우는 제외(즉, 다시 매수 가능)
    df = df[df["quantity"] > 0]
    return set(df["ticker"].astype(str).str.zfill(6).tolist())

def is_satisfy_condition(code):
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
            return False

        df = df.sort_index(ascending=True)
        df["MA5"] = df["현재가"].rolling(window=5).mean()
        df["MA20"] = df["현재가"].rolling(window=20).mean()
        df["MA60"] = df["현재가"].rolling(window=60).mean()

        ma5 = df["MA5"].iloc[-1]
        ma20 = df["MA20"].iloc[-1]
        ma60 = df["MA60"].iloc[-1]
        curr_price = df["현재가"].iloc[-1]

        if not (ma5 > ma20 > ma60):
            return False
        if curr_price < df["고가"].iloc[-20:].max():
            return False

        curr_vol = df["거래량"].iloc[-1]
        avg_vol = df["거래량"].iloc[-20:].mean()
        if curr_vol < avg_vol * 2:
            return False

        return True

    except Exception as e:
        print(f"[ERROR] 조건 확인 실패: {code}, {e}")
        return False

def run_watcher():
    tickers = get_watchlist()
    print(f"📡 감시 시작 - 총 감시 종목 수: {len(tickers)}")
    send_telegram_message(f"🚀 조건검색 시작 - 감시 종목 수: {len(tickers)}")

    watched = set()

    while True:
        existing = load_existing_positions()

        for code in tickers:
            code = str(code).zfill(6)
            if code in existing or code in watched:
                continue

            if is_satisfy_condition(code):
                name = kiwoom.GetMasterCodeName(code)

                try:
                    # 현재가 조회
                    price_data = kiwoom.block_request("opt10001", 종목코드=code, output="주식기본정보", next=0)
                    curr_price = int(str(price_data["현재가"][0]).replace(",", "").replace("+", "").replace("-", ""))

                    # 예수금 조회
                    deposit_data = kiwoom.block_request("opw00001",
                        계좌번호=account,
                        비밀번호="0000",
                        비밀번호입력매체구분="00",
                        조회구분=2,
                        output="예수금상세현황",
                        next=0)
                    balance = int(deposit_data['예수금'][0].replace(",", ""))
