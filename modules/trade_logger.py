# modules/trade_logger.py
import csv
import os
from datetime import datetime

def log_trade(code, name, price, pnl):
    log_path = "trade_log.csv"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [now, code, name, price, f"{pnl:.2f}%"]

    write_header = not os.path.exists(log_path)

    with open(log_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["시간", "종목코드", "종목명", "체결가", "수익률"])
        writer.writerow(row)
    print(f"📝 매매 로그 저장 완료: {name}({code}) @ {price}")
