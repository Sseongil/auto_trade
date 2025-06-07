import sys
import os
import pandas as pd
from datetime import datetime
from pykiwoom.kiwoom import Kiwoom

# 모듈 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.trade_manager import add_position
from modules.notify import send_telegram_message
from modules.trade_logger import log_trade

import json
def should_trade():
    try:
        with open("status.json", "r") as f:
            status = json.load(f).get("status", "")
            return status == "start"
    except:
        return False

    if not should_trade():
        print("🛑 자동매매 중지 상태입니다.")
        return

def run_auto_trade():
    kiwoom = Kiwoom()
    kiwoom.CommConnect(block=True)
    print("✅ 로그인 성공")

    # 계좌번호
    accounts = kiwoom.GetLoginInfo("ACCNO")
    account = accounts[0].strip()
    print(f"✅ 계좌번호: {account}")

    # 예수금 확인
    deposit_data = kiwoom.block_request("opw00001",
                                        계좌번호=account,
                                        비밀번호="0000",  # 비밀번호 수정
                                        비밀번호입력매체구분="00",
                                        조회구분=2,
                                        output="예수금상세현황",
                                        next=0)
    deposit = int(deposit_data['예수금'][0].replace(",", ""))
    print(f"💰 현재 예수금: {deposit:,}원")

    # 날짜 폴더 및 파일 경로
    today = datetime.today().strftime("%Y%m%d")
    folder_path = os.path.join("data", today)
    buy_list_path = os.path.join(folder_path, "buy_list.csv")

    # 종목 CSV 읽기
    df = None
    try:
        df = pd.read_csv(buy_list_path, encoding="utf-8-sig")
        print("🔍 로딩된 CSV 데이터:")
        print(df.head())
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(buy_list_path, encoding="cp949")
            print("🔍 로딩된 CSV 데이터:")
            print(df.head())
        except Exception as e:
            print(f"[ERROR] 종목 리스트 로드 실패: {e}")
            return

    if df is None or df.empty:
        print("❌ 매수 대상 종목이 없습니다.")
        return

    print(f"📄 매수 대상 종목:\n{df}")

    for _, row in df.iterrows():
        code = str(row['ticker']).zfill(6)
        name = row['name']
        quantity = 10
        print(f"📈 매수 시도: {name}({code})")

        try:
            price_data = kiwoom.block_request("opt10001",
                                              종목코드=code,
                                              output="주식기본정보",
                                              next=0)
            print(f"[DEBUG] {name} 현재가 응답: {price_data}")

            # 현재가 컬럼 추출
            columns = price_data.columns
            matched_cols = [col for col in columns if "현재가" in col.strip()]
            if not matched_cols:
                raise ValueError("현재가 컬럼이 존재하지 않음")

            raw_price = str(price_data[matched_cols[0]].iloc[0])
            raw_price = raw_price.replace(",", "").replace("+", "").replace("-", "").strip()
            if not raw_price.isdigit():
                raise ValueError(f"현재가 변환 실패: '{raw_price}'")

            current_price = int(raw_price)
        except Exception as e:
            print(f"[ERROR] {name}({code}) 현재가 조회 실패: {e}")
            send_telegram_message(f"[ERROR] {name}({code}) 현재가 조회 실패: {e}")
            continue

        order_result = kiwoom.SendOrder(
            "buy_order",     # rq_name
            "0101",          # screen_no
            account,         # 계좌번호
            1,               # 신규매수
            code,            # 종목코드
            quantity,        # 수량
            0,               # 시장가
            "03",            # 시장가 구분
            ""               # 주문번호
        )

        if order_result == 0:
            total_price = current_price * quantity
            print(f"✅ 매수 주문 성공: {name}({code})")
            print(f"📌 매수가: {current_price:,}원")
            print(f"📦 수량: {quantity}주")
            print(f"💰 총 주문 금액: {total_price:,}원")

            message = (
                f"✅ 매수 주문 성공: {name}({code})\n"
                f"📌 매수가: {current_price:,}원\n"
                f"📦 수량: {quantity}주\n"
                f"💰 총 주문 금액: {total_price:,}원"
            )
            send_telegram_message(message)
            add_position(code, name, current_price)
            log_trade(code, name, current_price, pnl=0)
        else:
            print(f"❌ 매수 주문 실패: {name}({code}) - 응답코드: {order_result}")
            send_telegram_message(f"❌ 매수 주문 실패: {name}({code})")

if __name__ == "__main__":
    run_auto_trade()
