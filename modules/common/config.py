# modules/common/config.py

import os
from dotenv import load_dotenv

# .env 파일 로드 (환경 변수 사용을 위함)
load_dotenv()

# --- 환경 변수 로드 헬퍼 함수 ---
def get_env(key, default=None):
    return os.getenv(key, default)

# --- 경로 설정 ---
# 프로젝트 루트 디렉토리 (local_api_server.py가 위치한 곳)
# sys.path에 modules가 추가되어 있으므로, 데이터 경로는 절대 경로 또는 상대 경로로 설정합니다.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # modules 폴더의 부모 폴더 (stock_auto)
DATA_DIR = os.path.join(BASE_DIR, 'data') # data 폴더 경로

# 데이터 폴더가 없으면 생성
os.makedirs(DATA_DIR, exist_ok=True)

# 💡 포지션 파일 및 로그 DB 경로
POSITIONS_FILE_PATH = os.path.join(DATA_DIR, 'positions.json')
TRADE_LOG_DB_PATH = os.path.join(DATA_DIR, 'trade_log.db')

# --- Kiwoom API 관련 설정 ---
KIWOOM_OCX_VERSION = "KHOPENAPI.KHOpenAPICtrl.1"
API_SERVER_PORT = get_env("API_SERVER_PORT", "5000") # Flask 서버 포트
ACCOUNT_NUMBERS = get_env("ACCOUNT_NUMBERS", "") # .env에서 계좌번호 로드 (쉼표로 구분 가능)
LOCAL_API_KEY = get_env("LOCAL_API_KEY") # 로컬 Flask API 인증 키

# --- Telegram 봇 설정 ---
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_env("TELEGRAM_CHAT_ID")

# --- 매수 전략 관련 상수 ---
MIN_GAP_UP_PCT = 3.0 # 시가 갭 상승 최소 비율
MIN_CURRENT_PRICE_VS_OPEN_PCT = 3.0 # 현재가 대비 시가 상승 최소 비율
MIN_VOLUME_INCREASE_RATIO = 700.0 # 직전 5일 평균 대비 거래량 증가율 (%)
MIN_TRADING_VALUE_BILLION = 20.0 # 최소 거래대금 (억 원)
MIN_CHEGYUL_GANGDO = 130.0 # 최소 체결강도 (%)
MIN_BUY_SELL_RATIO = 1.5 # 매수 총 잔량 / 매도 총 잔량 최소 비율

MIN_PRICE = 1000 # 최소 주가
MAX_PRICE = 50000 # 최대 주가
MIN_MARKET_CAP_BILLION = 500 # 최소 시가총액 (억 원)
MAX_MARKET_CAP_BILLION = 5000 # 최대 시가총액 (억 원)
MAX_CURRENT_DAILY_CHANGE_PCT = 12.0 # 당일 등락률 최대 허용치 (%) - 고점 추격 방지

DEFAULT_LOT_SIZE = 1 # 최소 거래 단위 (주식은 보통 1주)
MAX_BUY_ATTEMPTS = 3 # 매수 주문 시도 횟수 (지정가 -> 시장가 재시도 등)


# --- 매도 전략 관련 상수 (monitor_positions_strategy에서 사용) ---
TAKE_PROFIT_PCT_1ST = 2.0 # 1차 익절 목표 수익률 (%)
TRAIL_STOP_PCT_2ND = 0.8 # 2차 익절 (트레일링 스탑) 최고가 대비 하락률 (%)
STOP_LOSS_PCT_ABS = -1.2 # 절대 손절 비율 (%)
TIME_STOP_MINUTES = 15 # 시간 손절 (매수 후 N분 경과 시)

