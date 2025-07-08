# # modules/run_all.py

import sys
import os
import threading
from datetime import datetime
import time
import logging

# 로깅 설정
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 경로 보정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from modules.Kiwoom.monitor_positions import MonitorPositions
from modules.real_time_watcher import run_watcher
from modules.check_conditions_threaded import run_filter
from modules.report_generator import generate_daily_trade_report

def run_condition_filter_task():
    logger.info("🧠 [1] 조건검색 필터링 시작")
    run_filter()
    logger.info("🧠 [1] 조건검색 필터링 완료")

def run_real_time_watcher_task():
    logger.info("📡 [2] 실시간 조건검색 감시 시작")
    run_watcher()
    logger.info("📡 [2] 실시간 조건검색 감시 종료")

def run_position_monitor_task():
    logger.info("🧮 [3] 포지션 모니터링 시작")
    monitor_positions()
    logger.info("🧮 [3] 포지션 모니터링 종료")

def main():
    logger.info(f"🚀 자동매매 시스템 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    run_condition_filter_task()

    t1 = threading.Thread(target=run_real_time_watcher_task)
    t2 = threading.Thread(target=run_position_monitor_task)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    logger.info("✅ 모든 주요 자동매매 프로세스 종료.")
    
    logger.info("📊 일일 자동매매 리포트 생성 시작")
    generate_daily_trade_report()
    logger.info("📊 일일 자동매매 리포트 생성 완료")

    logger.info(f"🛑 자동매매 시스템 종료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
