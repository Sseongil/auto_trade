# modules/config.py

# 익절/손절 전략 설정
STOP_LOSS_PCT = -2.0         # 손절 기준
TAKE_PROFIT_PCT = 5.0        # 분할 익절 기준
TRAIL_STOP_PCT = 1.0         # 최고가 대비 하락 시 청산
MAX_HOLD_DAYS = 5            # 최대 보유일

# 텔레그램 설정
TELEGRAM_TOKEN = "8081086653:AAFbATaP5fUVOJztvPtxQWaMRF0WPEOkUqo"
TELEGRAM_CHAT_ID = "1866728370"

# 투자금 비중 전략 함수
def calculate_quantity(price: int, balance: int) -> int:
    """
    현재가와 예수금 기준으로 매수 수량을 계산한다.
    - 예수금 < 500만: 50% 투자
    - 예수금 < 1000만: 20% 투자
    - 예수금 >= 5000만: 최대 500만원까지만 투자
    """
    if balance < 5_000_000:
        invest_amount = balance * 0.5
    elif balance < 10_000_000:
        invest_amount = balance * 0.2
    else:
        invest_amount = min(5_000_000, balance * 0.2)
    quantity = int(invest_amount // price)
    return max(quantity, 1)
