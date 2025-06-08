# modules/monitor_positions.py

import os
import sys
import pandas as pd
from datetime import datetime
from pykiwoom.kiwoom import Kiwoom

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.notify import send_telegram_message
from modules.trade_logger import log_trade
from modules.config import STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_STOP_PCT, MAX_HOLD_DAYS

def get_current_price(kiwoom, code):
    price_data = kiwoom.block_request(
        "opt10001",
        종목코드=code,
        output="주식기본정보",
        next=0
    )
    raw = str(price_data['현재가'][0]).replace(",", "").replace("+", "").replace("-", "")
    return int(raw)

def load_positions():
    path = os.path.join("data", "positions.csv")
    cols = ["ticker", "name", "buy_price", "quantity", "buy_date", "half_exited", "trail_high"]

    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)

    df = pd.read_csv(path, encoding="utf-8-sig")

    for col in cols:
        if col not in df.columns:
            if col == "half_exited":
                df[col] = False
            elif col == "trail_high":
                df[col] = df["buy_price"]
            else:
                df[col] = ""

    df["quantity"] = df["quantity"].fillna(0).astype(int)
    df["buy_price"] = df["buy_price"].fillna(0).astype(int)
    df["half_exited"] = df["half_exited"].fillna(False)
    df["trail_high"] = df["trail_high"].fillna(df["buy_price"]).astype(float)

    return df

def save_positions(df):
    path = os.path.join("data", "positions.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")

def monitor_positions():
    kiwoom = Kiwoom()
    kiwoom.CommConnect(block=True)
    account = kiwoom.GetLoginInfo("ACCNO")[0]

    df = load_positions()
    if df.empty:
        print("📂 모니터링할 포지션 없음.")
        return

    for idx, row in df.iterrows():
        try:
            code = str(row["ticker"]).zfill(6)
            name = row["name"]
            buy_price = row["buy_price"]
            quantity = int(row["quantity"])
            half_exited = bool(row.get("half_exited", False))
            trail_high = float(row.get("trail_high", buy_price))
            buy_date = datetime.strptime(row["buy_date"], "%Y-%m-%d")
            hold_days = (datetime.today() - buy_date).days

            current_price = get_current_price(kiwoom, code)
            pnl = (current_price - buy_price) / buy_price * 100

            print(f"🔍 {name}({code}) 현재가: {current_price}, 수익률: {pnl:.2f}%, 보유일: {hold_days}")

            # 손절
            if pnl <= STOP_LOSS_PCT:
                kiwoom.SendOrder("손절매도", "0101", account, 2, code, quantity, 0, "03", "")
                send_telegram_message(f"❌ 손절: {name}({code}) {pnl:.2f}%")
                log_trade(code, name, current_price, pnl)
                df.drop(idx, inplace=True)
                continue

            # 50% 익절
            if not half_exited and pnl >= TAKE_PROFIT_PCT:
                kiwoom.SendOrder("익절매도(50%)", "0101", account, 2, code, quantity // 2, 0, "03", "")
                df.at[idx, "half_exited"] = True
                df.at[idx, "trail_high"] = current_price
                send_telegram_message(f"🎯 50% 익절: {name}, +{pnl:.2f}%")
                continue

            # 트레일링 스탑
            if half_exited:
                if current_price > trail_high:
                    df.at[idx, "trail_high"] = current_price
                elif current_price <= trail_high * (1 - TRAIL_STOP_PCT / 100):
                    kiwoom.SendOrder("트레일링익절", "0101", account, 2, code, quantity // 2, 0, "03", "")
                    pnl2 = (current_price - buy_price) / buy_price * 100
                    send_telegram_message(f"📉 트레일링 익절: {name}, +{pnl2:.2f}%")
                    log_trade(code, name, current_price, pnl2)
                    df.drop(idx, inplace=True)
                    continue

            # 보유일 초과
            if hold_days >= MAX_HOLD_DAYS:
                kiwoom.SendOrder("보유종료매도", "0101", account, 2, code, quantity, 0, "03", "")
                send_telegram_message(f"⌛ 보유일 초과 청산: {name}")
                log_trade(code, name, current_price, pnl)
                df.drop(idx, inplace=True)

        except Exception as e:
            print(f"[오류] {name}({code}) 오류: {e}")

    save_positions(df)

if __name__ == "__main__":
    monitor_positions()
