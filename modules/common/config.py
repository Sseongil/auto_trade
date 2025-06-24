# modules/common/config.py

import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경 변수 가져오는 헬퍼 함수
def get_env(key, default_value=None):
    return os.environ.get(key, default_value)

# --- 공통 설정 ---
API_SERVER_PORT = get_env("PORT", "5000")
NGROK_API_PORT = get_env("NGROK_API_PORT", "4040")

# --- 키움 API 관련 ---
ACCOUNT_NUMBERS = get_env("ACCOUNT_NUMBERS", "").split(',')[0].strip()
ACCOUNT_PASSWORD = get_env("ACCOUNT_PASSWORD", "")

# --- 파일 경로 설정 ---
# 현재 스크립트의 디렉토리 (modules/common)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 프로젝트 루트 디렉토리 (stock_auto)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..')) 

DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

POSITIONS_FILE_PATH = os.path.join(DATA_DIR, 'positions.json')
# 💡 매매 로그 데이터베이스 파일 경로 추가
LOG_DB_PATH = os.path.join(DATA_DIR, 'trade_log.db')

# --- 텔레그램 알림 설정 (필요시 사용) ---
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_env("TELEGRAM_CHAT_ID")

# --- 전략 관련 설정 ---
# .env 파일에서 불러오고, 없으면 기본값 사용 (float 또는 int로 변환)
STOP_LOSS_PCT = float(get_env("STOP_LOSS_PCT", -1.2))
TAKE_PROFIT_PCT = float(get_env("TAKE_PROFIT_PCT", 2.0))
TRAIL_STOP_PCT = float(get_env("TRAIL_STOP_PCT", 0.8))
MAX_HOLD_DAYS = int(get_env("MAX_HOLD_DAYS", 3))

# --- 거래 관련 설정 ---
DEFAULT_LOT_SIZE = 1 # 키움은 1주 단위로 주문 가능 (일반적으로 10주 묶음 아님)

# 이메일 알림 설정 (필요시 추가)
# SMTP_SERVER = get_env("SMTP_SERVER")
# SMTP_PORT = int(get_env("SMTP_PORT", 587))
# EMAIL_USER = get_env("EMAIL_USER")
# EMAIL_PASSWORD = get_env("EMAIL_PASSWORD")
# RECIPIENT_EMAIL = get_env("RECIPIENT_EMAIL")
