# modules/run_scheduler.py

import schedule
import time
import os
from datetime import datetime

def run_file(file_name):
    print(f"▶ 실행: {file_name}")
    os.system(f"python -m modules.{file_name}")

# ✅ 장 시작 전 조건검색 실행
schedule.every().day.at("08:40").do(run_file, "check_conditions_threaded")

# ✅ 실시간 매매
schedule.every().day.at("08:59").do(run_file, "real_time_watcher")

# ✅ 포지션 감시 (매 5분)
schedule.every(5).minutes.do(run_file, "monitor_positions")

# ✅ 장 종료 후 요약 전송
schedule.every().day.at("15:40").do(run_file, "report_generator")

print("📅 스케줄러 실행 중...")
while True:
    schedule.run_pending()
    time.sleep(1)
