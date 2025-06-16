# C:\Users\user\stock_auto\modules\common\config.py

import os
from dotenv import load_dotenv # .env 파일을 로드하기 위해 필요

# .env 파일이 stock_auto 폴더에 있다고 가정하고 로드
# 이 파일은 modules/common 안에 있으므로, 두 단계 상위로 이동해야 stock_auto 폴더에 접근 가능
DOTENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(DOTENV_PATH)

def get_env(key, default_value=None):
    """환경 변수를 가져옵니다. 없을 경우 기본값을 반환합니다."""
    value = os.environ.get(key)
    if value is None and default_value is not None:
        print(f"WARNING: Environment variable '{key}' not set. Using default value: '{default_value}'")
        return default_value
    return value

# 환경 변수 사용 예시
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_env("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

LOCAL_API_SERVER_URL = get_env("LOCAL_API_SERVER_URL", "http://127.0.0.1:5000")
API_SERVER_PORT = int(get_env("PORT", "5000")) # 기본값을 문자열로 넘겨야 int 변환 가능

# config.py의 위치가 modules/common 이므로, data 폴더 경로를 정확히 지정
CURRENT_DIR_COMMON = os.path.dirname(os.path.abspath(__file__)) # modules/common 폴더 경로
MODULES_DIR = os.path.dirname(CURRENT_DIR_COMMON) # modules 폴더 경로
DATA_DIR = os.path.join(MODULES_DIR, 'data') # modules/data 폴더

POSITIONS_FILE_PATH = os.path.join(DATA_DIR, 'positions.json') # JSON으로 변경 (monitor_positions가 JSON을 사용하도록 변경되었으므로)
TRADE_LOG_FILE_PATH = os.path.join(DATA_DIR, 'trades.csv') # 거래 로그 파일 경로 추가

# 데이터 디렉토리 없으면 생성
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
    print(f"Created data directory: {DATA_DIR}")

DEFAULT_LOT_SIZE = 1 # 최소 거래 단위 (주식은 보통 1주)

# 전략 관련 상수
STOP_LOSS_PCT = float(get_env("STOP_LOSS_PCT", "-5.0"))  # -5% 손절
TAKE_PROFIT_PCT = float(get_env("TAKE_PROFIT_PCT", "10.0")) # 10% 익절 (50% 매도)
TRAIL_STOP_PCT = float(get_env("TRAIL_STOP_PCT", "3.0"))  # 추적 손절 3%
MAX_HOLD_DAYS = int(get_env("MAX_HOLD_DAYS", "14"))      # 최대 보유일 14일

# positions.csv (이제는 positions.json) 파일의 컬럼 정의
# local_position_manager.py에서 사용됩니다.
POSITION_COLUMNS = [
    "ticker", "name", "buy_price", "quantity",
    "buy_date", "half_exited", "trail_high"
]