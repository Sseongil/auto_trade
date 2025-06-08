# main.py

import sys
import os
import pandas as pd
from datetime import datetime

# 경로 보정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from modules.check_conditions import filter_all_stocks
from modules.backtest import run_backtest

def main():
    today = datetime.today().strftime("%Y%m%d")
    save_dir = f"./data/{today}"
    os.makedirs(save_dir, exist_ok=True)

    # ✅ 1. 조건 검색 실행
    print("[1] 조건 검색 실행 중...")
    filtered = filter_all_stocks()

    if filtered is None or filtered.empty:
        print("❌ 조건을 만족하는 종목이 없습니다.")
        return

    buy_list_path = os.path.join(save_dir, f"buy_list_{today}.csv")
    filtered.to_csv(buy_list_path, index=False, encoding="utf-8-sig")
    print(f"[2] 필터링 완료 - 종목 수: {len(filtered)}")
    print(filtered.head())

    # ✅ 3. 백테스트 수행
    print("[3] 백테스트 수행 중...")
    backtest_result = run_backtest(buy_list_path)
    backtest_path = os.path.join(save_dir, f"backtest_result_{today}.csv")

    if backtest_result is not None:
        backtest_result.to_csv(backtest_path, index=False, encoding="utf-8-sig")
        print(f"[4] 백테스트 완료 - 결과 파일 저장됨: {backtest_path}")
    else:
        print("❌ 백테스트 실패 또는 결과 없음")

if __name__ == "__main__":
    main()
