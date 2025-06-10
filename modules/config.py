# modules/config.py (ADDITIONS FOR TELEGRAM)

import os

# --- 파일 경로 설정 ---
STATUS_FILE_PATH = "status.json"
BUY_LIST_DIR_PATH = os.path.join("data")
POSITIONS_FILE_PATH = os.path.join("positions.csv")

# --- 거래 전략 상수 ---
STOP_LOSS_PCT = -5.0
TAKE_PROFIT_PCT = 10.0
TRAIL_STOP_PCT = 3.0
MAX_HOLD_DAYS = 7
DEFAULT_LOT_SIZE = 1

# --- 텔레그램 알림 설정 ---
# TODO: 실제 토큰과 채팅 ID로 변경하세요! 보안상 환경 변수로 관리하는 것을 강력히 권장합니다.
TELEGRAM_TOKEN = "8081086653:AAFbATaP5fUVOJztvPtxQWaMRF0WPEOkUqo" # 텔레그램 봇 토큰
TELEGRAM_CHAT_ID = "1866728370" # 메시지를 받을 채팅 ID (개인 채팅 또는 그룹 채팅 ID)


# --- 매수 수량 계산 함수 ---
def calculate_quantity(current_price: int, available_balance: int) -> int:
    # ... (기존 calculate_quantity 함수 내용) ...
    if current_price <= 0 or available_balance <= 0:
        return 0
    total_buy_amount = available_balance
    max_shares = total_buy_amount // current_price
    return max_shares


# --- Kiwoom API 관련 설정 (선택 사항) ---
# KIWOOM_ACCOUNT_PASSWORD = "YOUR_PASSWORD" # TODO: 환경 변수 등으로 관리 권장