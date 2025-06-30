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

# --- 매수 전략 관련 상수 ---
MIN_GAP_UP_PCT = 3.0
MIN_CURRENT_PRICE_VS_OPEN_PCT = 3.0
MIN_VOLUME_INCREASE_RATIO = 700.0 # 700% 이상 증가
MIN_TRADING_VALUE_BILLION = 20.0 # 200억 원
MIN_CHEGYUL_GANGDO = 130.0 # 130% 이상
MIN_BUY_SELL_RATIO = 1.5 # 매수 총 잔량 / 매도 총 잔량

MIN_PRICE = 1000
MAX_PRICE = 50000
MIN_MARKET_CAP_BILLION = 500
MAX_MARKET_CAP_BILLION = 5000 # 5조원
MAX_CURRENT_DAILY_CHANGE_PCT = 12.0 # 당일 등락률 +12% 이하

DEFAULT_LOT_SIZE = 1 # 최소 거래 단위 (주식은 보통 1주)
MAX_BUY_ATTEMPTS = 3 # 매수 주문 시도 횟수 (지정가 -> 시장가 재시도 등)


# --- 매도 전략 관련 상수 (monitor_positions_strategy에서 사용) ---
TAKE_PROFIT_PCT_1ST = 2.0 # 1차 익절 +2.0%
TRAIL_STOP_PCT_2ND = 0.8 # 2차 익절 (트레일링 스탑) - 최고가 대비 -0.8% 하락 시 전량 매도
STOP_LOSS_PCT_ABS = -1.2 # 절대 손절 -1.2% 하락 시 전량 매도 (수익률 기준)
TIME_STOP_MINUTES = 60 # 시간 손절 (매수 후 60분 경과 시 청산 검토)
MAX_HOLD_DAYS = 1 # 최대 보유일 (당일 매수, 당일 청산 원칙이므로 보통 1)

# --- 전략 공통 상수 ---
API_SERVER_PORT = 5000
POSITIONS_FILE_PATH = "data/positions.json" # 보유 포지션 저장 파일
CONDITION_CHECK_INTERVAL_SEC = 60 * 5 # 조건 검색 실행 주기 (5분)
POSITION_MONITOR_INTERVAL_SEC = 15 # 보유 포지션 모니터링 주기 (15초)

# 조건 검색 필터링 관련 상수
MA_SHORT_PERIOD = 5   # 단기 이동평균선 기간
MA_MEDIUM_PERIOD = 20  # 중기 이동평균선 기간
MA_LONG_PERIOD = 60   # 장기 이동평균선 기간
VOLUME_AVG_PERIOD = 20 # 거래량 평균 계산 기간
VOLUME_MULTIPLIER = 5.0 # 평균 거래량 대비 최소 거래량 배율
HIGH_PRICE_LOOKBACK = 10 # 고점 돌파 확인 기간 (N일 신고가)

MARKET_CODES = ["0", "10"] # "0": KOSPI, "10": KOSDAQ
EXCLUDE_NAME_KEYWORDS = ["스팩", "우", "ETN", "ETF"]
EXCLUDE_STATUS_KEYWORDS = ["관리종목", "투자위험", "투자경고", "거래정지", "정리매매", "우선주", "스팩", "ETF", "ETN", "초저유동성"]

CONDITION_CHECK_MAX_WORKERS = 4 # 조건 검색 스레드 풀 워커 수

# 실시간 FID 목록 (필요한 FID만 추가)
# 10: 현재가, 11: 전일대비, 12: 등락률, 13: 누적거래량, 16: 시가, 17: 고가, 18: 저가,
# 229: 체결강도, 270: 매도호가1, 271: 매수호가1, 272: 매도총잔량, 273: 매수총잔량, 30: 누적거래대금
REALTIME_FID_LIST = "10;11;12;13;16;17;18;229;270;271;272;273;30"

# 화면번호 정의
REALTIME_SCREEN_NO_PREFIX = "5" # 실시간 데이터용 화면번호 (5000번대)
TR_SCREEN_NO_PREFIX = "6" # TR 요청용 화면번호 (6000번대)
ORDER_SCREEN_NO = "7000" # 주문용 화면번호
EXIT_STRATEGY_SCREEN_NO = "8000" # 매도 전략용 화면번호
# 실시간 조건검색용 화면번호 (새로 추가)
REALTIME_CONDITION_SCREEN_NO = "9000"


def get_env(key, default=None):
    import os
    return os.environ.get(key, default)
