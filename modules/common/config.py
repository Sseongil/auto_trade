# modules/common/config.py

import os
from dotenv import load_dotenv

load_dotenv() # .env 파일에서 환경 변수 로드

# --- API 서버 설정 ---
API_SERVER_PORT = int(os.getenv("API_SERVER_PORT", 5000)) # 기본값 5000
API_KEY = os.getenv("API_KEY", "your_secret_api_key_here") # 실제 사용 시 반드시 변경!

# --- Kiwoom API 관련 설정 ---
# Kiwoom API 로그인 시 사용할 계좌 번호 (쉼표로 구분하여 여러 개 지정 가능)
ACCOUNT_NUMBERS = os.getenv("ACCOUNT_NUMBERS", "YOUR_ACCOUNT_NUMBER")
# Kiwoom API 계좌 비밀번호 (주의: 환경 변수로 관리 권장)
ACCOUNT_PASSWORD = os.getenv("ACCOUNT_PASSWORD", "YOUR_ACCOUNT_PASSWORD")

# 실시간 데이터 FID (Field ID) 목록
# 10: 현재가, 11: 전일대비, 12: 등락률, 13: 누적거래량, 228: 체결강도, 290: 매수체결량, 291: 매도체결량
REALTIME_FID_LIST = "10;11;12;13;228;290;291"

# --- 파일 경로 설정 ---
# 포지션 데이터 저장 경로
POSITIONS_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../data/positions.json')
# 거래 로그 저장 경로
TRADE_LOG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../data/trade_log.csv')

# --- 전략 관련 설정 ---
# 조건 검색 스레드 풀 최대 워커 수
CONDITION_CHECK_MAX_WORKERS = int(os.getenv("CONDITION_CHECK_MAX_WORKERS", 6))

# 매수 전략 파라미터 (예시 값, 실제 전략에 맞게 조정 필요)
MIN_GAP_UP_PCT = float(os.getenv("MIN_GAP_UP_PCT", 1.0)) # 최소 갭 상승률
MIN_CURRENT_PRICE_VS_OPEN_PCT = float(os.getenv("MIN_CURRENT_PRICE_VS_OPEN_PCT", 0.5)) # 시가 대비 현재가 최소 상승률
MIN_VOLUME_INCREASE_RATIO = float(os.getenv("MIN_VOLUME_INCREASE_RATIO", 2.0)) # 거래량 증가 비율
MIN_TRADING_VALUE_BILLION = float(os.getenv("MIN_TRADING_VALUE_BILLION", 5.0)) # 최소 거래 대금 (억 원)
MIN_CHEGYUL_GANGDO = float(os.getenv("MIN_CHEGYUL_GANGDO", 120.0)) # 최소 체결 강도
MIN_BUY_SELL_RATIO = float(os.getenv("MIN_BUY_SELL_RATIO", 1.5)) # 매수/매도 체결량 비율
MIN_PRICE = int(os.getenv("MIN_PRICE", 1000)) # 최소 주가
MAX_PRICE = int(os.getenv("MAX_PRICE", 100000)) # 최대 주가
MIN_MARKET_CAP_BILLION = float(os.getenv("MIN_MARKET_CAP_BILLION", 50.0)) # 최소 시가총액 (억 원)
MAX_MARKET_CAP_BILLION = float(os.getenv("MAX_MARKET_CAP_BILLION", 10000.0)) # 최대 시가총액 (억 원)
MAX_CURRENT_DAILY_CHANGE_PCT = float(os.getenv("MAX_CURRENT_DAILY_CHANGE_PCT", 10.0)) # 당일 최대 등락률
DEFAULT_LOT_SIZE = int(os.getenv("DEFAULT_LOT_SIZE", 1)) # 최소 거래 단위 (보통 1주)

# 익절/손절 전략 파라미터 (예시 값, 실제 전략에 맞게 조정 필요)
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", 2.0)) # 1차 익절 수익률 (%)
TRAIL_STOP_PCT = float(os.getenv("TRAIL_STOP_PCT", 0.8)) # 트레일링 스탑 손절률 (최고가 대비 하락률)
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", -1.2)) # 절대 손절률 (%)
MAX_HOLD_DAYS = int(os.getenv("MAX_HOLD_DAYS", 5)) # 최대 보유 일수

# 제외할 종목명 키워드
EXCLUDE_NAME_KEYWORDS = ["스팩", "우", "ETN", "ETF"]
# 제외할 종목 상태 키워드
EXCLUDE_STATUS_KEYWORDS = ["관리종목", "투자위험", "투자경고", "거래정지", "정리매매", "우선주", "스팩", "ETF", "ETN", "초저유동성"]

# 시장 코드
MARKET_CODES = ["0", "10"] # "0": KOSPI, "10": KOSDAQ

# 일봉 데이터 최소 포인트 (이동평균선 계산 등)
MIN_DATA_POINTS = int(os.getenv("MIN_DATA_POINTS", 60))

def get_env(key, default=None):
    """환경 변수를 가져오는 헬퍼 함수."""
    return os.getenv(key, default)

