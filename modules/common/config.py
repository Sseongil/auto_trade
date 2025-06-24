# modules/common/config.py

# ... (기존 상수들) ...

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
TRAIL_STOP_PCT_2ND = 0.8 # 2차 익절 (트레일링 스탑) -0.8% 하락
STOP_LOSS_PCT_ABS = -1.2 # 절대 손절 -1.2%
TIME_STOP_MINUTES = 15 # 시간 손절 15분