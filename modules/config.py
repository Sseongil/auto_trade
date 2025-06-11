# modules/config.py

import os

# --- 파일 경로 설정 ---
STATUS_FILE_PATH = "status.json"
BUY_LIST_DIR_PATH = os.path.join("data")
# POSITIONS_FILE_PATH는 trade_manager.py 내에서 직접 경로를 구성하는 것이 더 유연합니다.
# (e.g., os.path.join("data", "positions.csv"))

# ✅ 새로운 POSITION_COLUMNS 추가: positions.csv 파일의 컬럼 순서 및 정의 (데이터 스키마)
POSITION_COLUMNS = [
    "ticker", "name", "buy_price", "quantity", "buy_date", "half_exited", "trail_high"
]

# --- 거래 전략 상수 ---
STOP_LOSS_PCT = -5.0
TAKE_PROFIT_PCT = 10.0
TRAIL_STOP_PCT = 3.0
MAX_HOLD_DAYS = 7
DEFAULT_LOT_SIZE = 1

# --- 텔레그램 알림 설정 ---
# ✅ 환경 변수에서 값 로드. 없으면 하드코딩된 기본값 사용 (보안상 환경 변수 사용 강력 권장)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE") # 텔레그램 봇 토큰
TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", 0)) # 메시지를 받을 채팅 ID (개인 채팅 또는 그룹 채팅 ID), int 변환 필수!


# --- 매수 수량 계산 함수 ---
def calculate_quantity(current_price: int, available_balance: int) -> int:
    if current_price <= 0 or available_balance <= 0:
        return 0
    total_buy_amount = available_balance
    max_shares = total_buy_amount // current_price
    return max_shares


# --- Kiwoom API 관련 설정 (선택 사항) ---
# KIWOOM_ACCOUNT_PASSWORD = os.environ.get("KIWOOM_ACCOUNT_PASSWORD", "YOUR_PASSWORD") # TODO: 환경 변수 등으로 관리 권장