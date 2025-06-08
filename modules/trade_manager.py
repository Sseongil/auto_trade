# modules/trade_manager.py
import os
import pandas as pd
from datetime import datetime

def add_position(code, name, buy_price, quantity):
    path = os.path.join("data", "positions.csv")
    today = datetime.today().strftime("%Y-%m-%d")

    new_entry = {
        "ticker": code,
        "name": name,
        "buy_price": buy_price,
        "quantity": quantity,
        "buy_date": today,
        "half_exited": False,
        "trail_high": buy_price
    }

    if os.path.exists(path):
        df = pd.read_csv(path, encoding="utf-8-sig")
        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
    else:
        df = pd.DataFrame([new_entry])

    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"💾 포지션 저장 완료: {name}({code})")
