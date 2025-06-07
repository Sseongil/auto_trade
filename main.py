# main.py
import sys
import os
import pandas as pd

# 경로 설정 (삭제하지 말고 유지)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from modules.get_stock_list import get_krx_stock_list
from modules.check_conditions import get_filtered_stocks
from modules.backtest import run_backtest

def main():
    today = datetime.today().strftime("%Y%m%d")
    save_dir = f"./data/{today}"
    os.makedirs(save_dir, exist_ok=True)

    # ------------------------------------------
    # ✅ 1. 종목 리스트 수집
    print("[1] 종목 리스트 수집 중...")
    df = get_krx_stock_list()

    print("[DEBUG] get_krx_stock_list 결과:")
    print(type(df))
    if df is None:
        print("❌ df is None")
        return
    elif df.empty:
        print("❌ df is empty")
        return
    else:
        print(df.head())  # 샘플 출력
    # ------------------------------------------

    # ✅ 2. 조건 필터링
    print("[2] 조건 검색 중...")
    filtered = get_filtered_stocks(df)

    if filtered is None or filtered.empty:
        print("❌ 조건을 만족하는 종목이 없습니다.")
        return

    buy_list_path = os.path.join(save_dir, f"buy_list_{today}.csv")
    filtered.to_csv(buy_list_path, index=False, encoding="utf-8-sig")

    # ✅ 3. 백테스트 실행
    print("[3] 백테스트 수행 중...")
    backtest_result = run_backtest(buy_list_path)
    backtest_path = os.path.join(save_dir, f"backtest_result_{today}.csv")
    backtest_result.to_csv(backtest_path, index=False, encoding="utf-8-sig")

    # ✅ 4. 요약 출력
    print(f"[4] 총 종목 개수: {len(filtered)}")

if __name__ == "__main__":
    main()
