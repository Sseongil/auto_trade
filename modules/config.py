# modules/config.py

import os
from dotenv import load_dotenv
import logging

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- 경로 설정 ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")

# --- .env 환경 변수 로딩 ---
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    logger.warning("⚠️ .env 파일을 찾을 수 없습니다. 환경변수가 올바르게 설정되지 않았을 수 있습니다.")

# --- 전략 파라미터 (중앙 관리) ---
STOP_LOSS_PCT = -2.0        # 손절: -2%
TAKE_PROFIT_PCT = 5.0       # 익절: +5%
TRAIL_STOP_PCT = 1.0        # 트레일링 스탑: 최고점 대비 -1%
MAX_HOLD_DAYS = 3           # 최대 보유일: 3일

# --- 텔레그램 설정 (환경변수에서 불러옴) ---
TELEGRAM_TOKEN = os.getenv("8081086653:AAFbATaP5fUVOJztvPtxQWaMRF0WPEOkUqo", "")
TELEGRAM_CHAT_ID = os.getenv("1866728370", "")

# --- 파일 경로 ---
POSITIONS_FILE_PATH = os.path.join(DATA_DIR, "positions.csv")
STATUS_FILE_PATH = os.path.join(DATA_DIR, "status.json")

# --- 투자 계산 설정 ---
MIN_INVEST_AMOUNT_KRW = 10_000     # 최소 투자금: 1만 원
DEFAULT_LOT_SIZE = 10              # 매수 단위: 10주

# --- 수량 계산 함수 ---
def calculate_quantity(current_price: int, available_balance: int) -> int:
    """
    주어진 예수금과 현재 주가 기준으로 매수 가능한 수량 계산.

    Args:
        current_price (int): 현재 주가 (원)
        available_balance (int): 사용 가능한 예수금 (원)

    Returns:
        int: 매수 수량 (기본 거래 단위 DEFAULT_LOT_SIZE의 배수, 최소 0)
    """
    if current_price <= 0:
        return 0

    # 1. 자산 규모에 따른 투자 금액 설정
    if available_balance < 5_000_000:
        invest_amount = available_balance * 0.5
    elif available_balance < 10_000_000:
        invest_amount = available_balance * 0.2
    else:
        invest_amount = min(5_000_000, available_balance * 0.2)

    # 2. 최소 투자 금액 조건 확인
    if invest_amount < MIN_INVEST_AMOUNT_KRW:
        return 0

    # 3. 매수 수량 계산
    total_shares = invest_amount // current_price
    quantity = (total_shares // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE

    return max(0, int(quantity))