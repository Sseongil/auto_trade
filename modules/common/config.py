# modules/common/config.py

import os
from dotenv import load_dotenv

# --- .env 환경변수 로드 ---
# 현재 파일 위치는 modules/common 이므로, .env는 두 단계 상위 디렉토리에 있음
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)

# --- 환경 변수 접근 함수 ---
def get_env(key, default_value=None):
    value = os.environ.get(key)
    if value is None and default_value is not None:
        print(f"⚠️ 환경 변수 '{key}'가 없습니다. 기본값 '{default_value}' 사용.")
        return default_value
    return value

# --- 텔레그램 환경 변수 ---
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = get_env("TELEGRAM_CHAT_ID", "")
LOCAL_API_SERVER_URL = get_env("LOCAL_API_SERVER_URL", "http://127.0.0.1:5000")
API_SERVER_PORT = int(get_env("PORT", "5000"))

# --- 경로 설정 ---
DATA_DIR = os.path.join(BASE_DIR, "data")
POSITIONS_FILE_PATH = os.path.join(DATA_DIR, "positions.json")
TRADE_LOG_FILE_PATH = os.path.join(DATA_DIR, "trades.csv")
STATUS_FILE_PATH = os.path.join(DATA_DIR, "status.json")

# --- 디렉토리 생성 ---
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
    print(f"📁 data 디렉토리 생성됨: {DATA_DIR}")

# --- 전략 설정 ---
STOP_LOSS_PCT = float(get_env("STOP_LOSS_PCT", "-1.2"))
TAKE_PROFIT_PCT = float(get_env("TAKE_PROFIT_PCT", "2.0"))
TRAIL_STOP_PCT = float(get_env("TRAIL_STOP_PCT", "0.8"))
MAX_HOLD_DAYS = int(get_env("MAX_HOLD_DAYS", "3"))     # 트레일링 스탑 (%)         # 최대 보유일 (일)

# --- 수수료/세금 관련 설정 ---
BUY_FEE_RATE = 0.00015           # 매수 수수료 (0.015%)
SELL_FEE_RATE = 0.0023           # 매도 수수료 + 세금 (0.23%)
TRADE_SAFETY_MARGIN = 0.003      # 수량 계산 시 여유 마진 (0.3%)

# --- 매수 계산 파라미터 ---
MIN_INVEST_AMOUNT_KRW = 10_000   # 최소 투자 금액
DEFAULT_LOT_SIZE = 1             # 거래 단위 (1주, 제한 없음)

# --- 포지션 컬럼 정의 ---
POSITION_COLUMNS = [
    "ticker", "name", "buy_price", "quantity",
    "buy_date", "half_exited", "trail_high"
]

# --- 수량 계산 함수 ---
def calculate_quantity(current_price: int, available_balance: int) -> int:
    """
    주어진 예수금과 주가 기준으로 매수 가능한 수량 계산
    (수수료 고려, 최소금액 조건 포함, 1주 단위)

    Args:
        current_price (int): 현재 주가 (원)
        available_balance (int): 예수금 (원)

    Returns:
        int: 매수 수량
    """
    if current_price <= 0:
        return 0

    # 1. 투자 비중 계산
    if available_balance < 5_000_000:
        invest_amount = available_balance * 0.5
    elif available_balance < 10_000_000:
        invest_amount = available_balance * 0.2
    else:
        invest_amount = min(5_000_000, available_balance * 0.2)

    # 2. 수수료 및 세금 고려
    invest_amount *= (1 - TRADE_SAFETY_MARGIN)

    # 3. 최소 투자 금액 확인
    if invest_amount < MIN_INVEST_AMOUNT_KRW:
        return 0

    # 4. 수량 계산 (1주 단위)
    quantity = invest_amount // current_price
    return max(0, int(quantity))
