# modules/auto_trade.py

import os
import sys
import json
import pandas as pd
from datetime import datetime
from pykiwoom.kiwoom import Kiwoom

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.trade_manager import add_position
from modules.notify import send_telegram_message
from modules.trade_logger import log_trade
from modules.config import calculate_quantity


def should_trade():
    try:
        with open("status.json", "r", encoding="utf-8") as f:
            status_data = json.load(f)
            return status_data.get("status") == "start"
    except FileNotFoundError:
        print("[ERROR] status.json 파일을 찾을 수 없습니다.")
        return False
    except json.JSONDecodeError:
        print("[ERROR] status.json 형식 오류.")
        return False
    except Exception as e:
        print(f"[ERROR] status.json 예외: {e}")
        return False


def run_auto_trade():
    print("✅ 자동매매 실행 시작")

    if not should_trade():
        print("🛑 상태: 중지됨")
        return

    kiwoom = Kiwoom()
    try:
        kiwoom.CommConnect(block=True)
        if not kiwoom.connected:
            send_telegram_message("❌ 키움 API 연결 실패")
            return
    except Exception as e:
        send_telegram_message(f"❌ 키움 연결 오류: {e}")
        return

    accounts = kiwoom.GetLoginInfo("ACCNO")
    if not accounts:
        send_telegram_message("❌ 계좌 정보 없음")
        return
    account = accounts[0].strip()

    today = datetime.today().strftime("%Y%m%d")
    buy_list_dir = os.path.join("data", today)
    buy_list_path = os.path.join(buy_list_dir, "buy_list.csv")

    if not os.path.exists(buy_list_path):
        send_telegram_message(f"❌ buy_list.csv 없음: {buy_list_path}")
        return

    try:
        df = pd.read_csv(buy_list_path, encoding="utf-8-sig")
    except Exception as e:
        send_telegram_message(f"❌ buy_list.csv 읽기 오류: {e}")
        return

    if df.empty:
        send_telegram_message("📭 매수 종목 없음")
        return

    print(f"📋 매수 대상:\n{df[['ticker', 'name']]}")

    # 예수금 조회
    deposit_data = kiwoom.block_request("opw00001",
        계좌번호=account,
        비밀번호="0000",
        비밀번호입력매체구분="00",
        조회구분=2,
        output="예수금상세현황",
        next=0)
    balance = int(deposit_data['예수금'][0].replace(",", ""))
    print(f"💰 현재 예수금: {balance:,}원")

    for _, row in df.iterrows():
        code = str(row["ticker"]).zfill(6)
        name = row["name"]

        print(f"\n📈 매수 시도: {name}({code})")

        try:
            price_data = kiwoom.block_request("opt10001", 종목코드=code, output="주식기본정보", next=0)
            price_str = str(price_data.get("현재가", "0")).replace(",", "").replace("+", "").replace("-", "").strip()
            current_price = int(price_str) if price_str.isdigit() else 0
            if current_price == 0:
                raise ValueError("현재가 변환 실패")
        except Exception as e:
            send_telegram_message(f"❌ 현재가 조회 실패: {name}({code}) - {e}")
            continue

        quantity = calculate_quantity(current_price, balance)
        if quantity <= 0:
            print(f"🚫 매수 불가 (수량 0): {name}({code})")
            continue

        result = kiwoom.SendOrder("자동매수", "0101", account, 1, code, quantity, 0, "03", "")
        if result == 0:
            print(f"✅ 매수 성공: {name}({code}) {current_price:,} x {quantity}")
            send_telegram_message(f"✅ 매수 성공: {name}({code})\n💰 {current_price:,}원 x {quantity}주")
            add_position(code, name, current_price, quantity)
            log_trade(code, name, current_price, pnl=0)
        else:
            print(f"❌ 매수 실패: {name}({code}) 코드: {result}")
            send_telegram_message(f"❌ 매수 실패: {name}({code})")

    print("✅ 자동매매 완료")
