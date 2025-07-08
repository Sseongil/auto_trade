# modules/common/config.py

import os
from dotenv import load_dotenv

load_dotenv()

# --- API 서버 설정 ---
API_SERVER_PORT = int(os.getenv("API_SERVER_PORT", 5000))
API_KEY = os.getenv("LOCAL_API_KEY", "your_local_api_key_here")

# --- Kiwoom API 계정 정보 ---
ACCOUNT_NUMBERS = os.getenv("ACCOUNT_NUMBERS", "")
ACCOUNT_PASSWORD = os.getenv("ACCOUNT_PASSWORD", "")

# --- 파일 경로 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, "../../"))
DATA_DIR = os.path.join(ROOT_DIR, "data")
LOG_DIR = os.path.join(ROOT_DIR, "logs")

POSITIONS_FILE_PATH = os.path.join(DATA_DIR, "positions.json")
TRADE_LOG_FILE_PATH = os.path.join(LOG_DIR, "trade_log.csv")

# --- 전략 및 시장 설정 ---
REALTIME_FID_LIST = "10;11;12;13;228;290;291"

CONDITION_CHECK_MAX_WORKERS = int(os.getenv("CONDITION_CHECK_MAX_WORKERS", 6))

MIN_GAP_UP_PCT = float(os.getenv("MIN_GAP_UP_PCT", 1.0))
MIN_CURRENT_PRICE_VS_OPEN_PCT = float(os.getenv("MIN_CURRENT_PRICE_VS_OPEN_PCT", 0.5))
MIN_VOLUME_INCREASE_RATIO = float(os.getenv("MIN_VOLUME_INCREASE_RATIO", 2.0))
MIN_TRADING_VALUE_BILLION = float(os.getenv("MIN_TRADING_VALUE_BILLION", 5.0))
MIN_CHEGYUL_GANGDO = float(os.getenv("MIN_CHEGYUL_GANGDO", 120.0))
MIN_BUY_SELL_RATIO = float(os.getenv("MIN_BUY_SELL_RATIO", 1.5))
MIN_PRICE = int(os.getenv("MIN_PRICE", 1000))
MAX_PRICE = int(os.getenv("MAX_PRICE", 100000))
MIN_MARKET_CAP_BILLION = float(os.getenv("MIN_MARKET_CAP_BILLION", 50.0))
MAX_MARKET_CAP_BILLION = float(os.getenv("MAX_MARKET_CAP_BILLION", 10000.0))
MAX_CURRENT_DAILY_CHANGE_PCT = float(os.getenv("MAX_CURRENT_DAILY_CHANGE_PCT", 10.0))
DEFAULT_LOT_SIZE = int(os.getenv("DEFAULT_LOT_SIZE", 1))

TAKE_PROFIT_PCT_1ST = float(os.getenv("TAKE_PROFIT_PCT_1ST", 2.0))
TRAIL_STOP_PCT_2ND = float(os.getenv("TRAIL_STOP_PCT_2ND", 0.8))
STOP_LOSS_PCT_ABS = float(os.getenv("STOP_LOSS_PCT_ABS", 1.2))
MAX_HOLD_DAYS = int(os.getenv("MAX_HOLD_DAYS", 5))

EXIT_STRATEGY_PRIORITY = os.getenv("EXIT_STRATEGY_PRIORITY", "PROFIT_FIRST")
MIN_HOLD_TIME_MINUTES = int(os.getenv("MIN_HOLD_TIME_MINUTES", 5))

EXCLUDE_NAME_KEYWORDS = ["스팩", "우", "ETN", "ETF"]
EXCLUDE_STATUS_KEYWORDS = [
    "관리종목", "투자위험", "투자경고", "거래정지", "정리매매", "우선주", "스팩", "ETF", "ETN", "초저유동성",
    "증거금100%", "신용가능", "담보대출", "대주가능", "신용융자", "신용대주"
]

MARKET_CODES = ["0", "10"]
MIN_DATA_POINTS = int(os.getenv("MIN_DATA_POINTS", 60))

def get_env(key, default=None):
    return os.getenv(key, default)
