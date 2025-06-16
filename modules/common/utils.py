# C:\Users\user\stock_auto\modules\common\utils.py

from datetime import datetime

def get_current_time_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")