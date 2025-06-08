# modules/auto_trade.py
import os
import sys
import json
import pandas as pd
from datetime import datetime
from pykiwoom.kiwoom import Kiwoom
from modules.trade_manager import add_position
from modules.notify import send_telegram_message
from modules.trade_logger import log_trade

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def should_trade():
    try:
        with open("status.json", "r") as f:
            return json.load(f).get("status", "") == "start"
    except:
        return False

def run_auto_trade():
    print("✅ 자동매매 실행 시작")

    if not should_trade():
        print("🛑 상태: 중지")
        return

    kiwoom = Kiwoom()
    kiwoom.CommConnect(block=True)

    account = kiwoom.GetLoginInfo("ACCNO")[0].strip()

    today = datetime.today().strftime("%Y%m%d")
    buy_list_path = os.path.join("data", today, "buy_list.csv")

    try:
        df = pd.read_csv(buy_list_path, encoding="utf-8-sig")
    except Exception as e:
        print(f"[ERROR] 종목 리스트 불러오기 실패: {e}")
        return

    if df.empty:
        print("❌ 매수 대상 없음")
        return

    print(f"📋 매수 대상:\n{df[['ticker', 'name']]}")

    for _, row in df.iterrows():
        code = str(row["ticker"]).zfill(6)
        name = row["name"]
        quantity = 10

        try:
            price_data = kiwoom.block_request("opt10001", 종목코드=code, output="주식기본정보", next=0)
            curr_price = int(str(price_data["현재가"][0]).replace(",", "").replace("+", "").replace("-", ""))
        except Exception as e:
            send_telegram_message(f"❌ {name} 현재가 조회 실패: {e}")
            continue

        result = kiwoom.SendOrder("매수", "0101", account, 1, code, quantity, 0, "03", "")
        if result == 0:
            send_telegram_message(f"✅ 매수 성공: {name}({code})\n💰 매수가: {curr_price}, 수량: {quantity}")
            add_position(code, name, curr_price, quantity)
            log_trade(code, name, curr_price, pnl=0)
        else:
            send_telegram_message(f"❌ 매수 실패: {name}({code})")

# Flask 연동용 - main 없음
