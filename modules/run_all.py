# run_all.py

import sys
import os
import threading
from datetime import datetime

# 경로 보정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from modules.monitor_positions import monitor_positions
from modules.real_time_watcher import run_watcher
from modules.check_conditions_threaded import run_filter


def run_condition_filter():
    print("🧠 [1] 조건검색 필터링 시작")
    run_filter()


def run_real_time_watcher():
    print("📡 [2] 실시간 조건검색 감시 시작")
    run_watcher()


def run_position_monitor():
    print("🧮 [3] 포지션 모니터링 시작")
    monitor_positions()


def main():
    print(f"🚀 자동매매 시스템 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 조건검색 초기 필터링 (buy_list.csv 생성)
    run_condition_filter()

    # 2. 실시간 감시 + 포지션 모니터링을 병렬로 실행
    t1 = threading.Thread(target=run_real_time_watcher)
    t2 = threading.Thread(target=run_position_monitor)

    t1.start()
    t2.start()

    t1.join()
    t2.join()


if __name__ == "__main__":
    main()
