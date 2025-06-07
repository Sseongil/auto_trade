# modules/monitor_positions.py
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pykiwoom.kiwoom import Kiwoom
import pandas as pd
from datetime import datetime
from modules.notify import send_telegram_message
from modules.trade_logger import log_trade

# 현재가 조회 함수 (부호 제거 포함)
def get_current_price(kiwoom, code):
    price_data = kiwoom.block_request(
        "opt10001",
        종목코드=code,
        output="주식기본정보",
        next=0
    )
    raw_price = price_data['현재가'][0]
    cleaned_price = str(raw_price).replace(",", "").replace("▲", "").replace("▼", "").replace("+", "").replace("-", "").strip()
    return int(cleaned_price)

# 포지션 로딩
def load_positions():
    path = os.path.join("data", "positions.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=["ticker", "name", "buy_price", "quantity", "buy_date"])
    return pd.read_csv(path, encoding="utf-8-sig")

# 포지션 저장
def save_positions(df):
    path = os.path.join("data", "positions.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")

# 자동 모니터링 수행
def monitor_positions():
    kiwoom = Kiwoom()
    kiwoom.CommConnect(block=True)
    print("✅ 모니터링 시작")

    account = kiwoom.GetLoginInfo("ACCNO")[0]

    df = load_positions()
    if df.empty:
        print("📂 모니터링할 포지션이 없습니다.")
        return

    for idx, row in df.iterrows():
        code = str(row["ticker"]).zfill(6)
        name = row["name"]
        buy_price = row["buy_price"]
        quantity = int(row["quantity"])
        buy_date = datetime.strptime(row["buy_date"], "%Y-%m-%d")
        hold_days = (datetime.today() - buy_date).days

        try:
            current_price = get_current_price(kiwoom, code)
            pnl = (current_price - buy_price) / buy_price * 100
            print(f"{name}({code}) 현재가: {current_price}, 수익률: {pnl:.2f}%, 보유일: {hold_days}")

            if pnl >= 6.5 or pnl <= -3 or hold_days >= 5:
                print(f"💰 매도 조건 충족 → {name} 매도 시도")
                order = kiwoom.SendOrder("sell_request", "0101", account, 2, code, quantity, 0, "03", "")

                if order == 0:
                    print(f"✅ 매도 주문 성공: {name}({code}), 매도가: {current_price}")
                    send_telegram_message(f"📤 매도 주문 성공: {name}({code})\n매도가: {current_price}, 수익률: {pnl:.2f}%")
                    log_trade(code, name, current_price, pnl)
                    df.drop(index=idx, inplace=True)
                else:
                    print(f"❌ 매도 주문 실패: {name}({code})")

        except Exception as e:
            print(f"[오류] {name} 매도 중 오류 발생: {e}")

    save_positions(df)

if __name__ == "__main__":
    monitor_positions()

