# modules/common/config.py

import os
from dotenv import load_dotenv

load_dotenv()

def get_env(key, default=None):
    return os.getenv(key, default)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

POSITIONS_FILE_PATH = os.path.join(DATA_DIR, 'positions.json')
TRADE_LOG_DB_PATH = os.path.join(DATA_DIR, 'trade_log.db')

KIWOOM_OCX_VERSION = "KHOPENAPI.KHOpenAPICtrl.1"
API_SERVER_PORT = get_env("API_SERVER_PORT", "5000")
ACCOUNT_NUMBERS = get_env("ACCOUNT_NUMBERS", "")
LOCAL_API_KEY = get_env("LOCAL_API_KEY")

TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_env("TELEGRAM_CHAT_ID")

# 매수 조건 관련 상수
MIN_GAP_UP_PCT = 3.0
MIN_CURRENT_PRICE_VS_OPEN_PCT = 3.0
MIN_VOLUME_INCREASE_RATIO = 700.0
MIN_TRADING_VALUE_BILLION = 20.0
MIN_CHEGYUL_GANGDO = 130.0
MIN_BUY_SELL_RATIO = 1.5

MIN_PRICE = 1000
MAX_PRICE = 50000
MIN_MARKET_CAP_BILLION = 500
MAX_MARKET_CAP_BILLION = 5000
MAX_CURRENT_DAILY_CHANGE_PCT = 12.0

DEFAULT_LOT_SIZE = 1
MAX_BUY_ATTEMPTS = 3

# 매도 전략
TAKE_PROFIT_PCT_1ST = 2.0
TRAIL_STOP_PCT_2ND = 0.8
STOP_LOSS_PCT_ABS = -1.2
TIME_STOP_MINUTES = 15
EXIT_STRATEGY_SCREEN_NO = "1821" # 매도 전략용 화면번호

# ✅ 조건검색 병렬 처리 워커 수
CONDITION_CHECK_MAX_WORKERS = 6
