# modules/strategies/exit_strategy.py

import logging
from datetime import datetime, timedelta
from modules.common.config import STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_STOP_PCT, MAX_HOLD_DAYS
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)

def exit_strategy(monitor_positions, trade_manager):
    """
    현재 포지션을 순회하며 자동 익절/손절/보유일 초과 조건을 체크 후 매도
    """
    all_positions = monitor_positions.get_all_positions()
    now = datetime.now()

    for code, pos in all_positions.items():
        stock_name = pos.get("종목명", "Unknown")
        quantity = pos.get("보유수량", 0)
        avg_price = pos.get("매입가", 0)
        buy_time_str = pos.get("매수일시", None)
        sold_half = pos.get("절반익절", False)

        if quantity <= 0 or avg_price <= 0 or not buy_time_str:
            continue

        try:
            current_price = trade_manager.kiwoom_helper.get_current_price(code)
        except Exception as e:
            logger.warning(f"{stock_name} 현재가 조회 실패: {e}")
            continue

        # 수익률 계산
        change_pct = ((current_price - avg_price) / avg_price) * 100
        logger.info(f"{stock_name} 수익률: {change_pct:.2f}%")

        # 보유일수 계산
        try:
            buy_time = datetime.strptime(buy_time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning(f"{stock_name} 매수일시 파싱 실패: {buy_time_str}")
            continue

        hold_days = (now - buy_time).days

        # 손절 조건
        if change_pct <= float(STOP_LOSS_PCT):
            logger.info(f"❌ 손절 조건 만족: {stock_name}({code}) 수익률 {change_pct:.2f}%")
            _sell(code, stock_name, quantity, "손절", trade_manager)
            continue

        # 익절 조건 (50%만 매도)
        if not sold_half and change_pct >= float(TAKE_PROFIT_PCT):
            half_qty = max(1, quantity // 2)
            logger.info(f"✅ 익절 조건 만족: {stock_name}({code}) 수익률 {change_pct:.2f}% → 절반 매도")
            _sell(code, stock_name, half_qty, "익절 (절반)", trade_manager)
            monitor_positions.mark_half_sold(code)  # 절반 익절 기록
            continue

        # 트레일링 스탑 (익절 후)
        if sold_half and change_pct <= float(TRAIL_STOP_PCT):
            logger.info(f"📉 트레일링 스탑 발동: {stock_name}({code}) 수익률 {change_pct:.2f}%")
            _sell(code, stock_name, quantity, "트레일링 스탑", trade_manager)
            continue

        # 보유일 초과
        if hold_days > int(MAX_HOLD_DAYS):
            logger.info(f"⏰ 보유일 초과 청산: {stock_name}({code}) {hold_days}일 경과")
            _sell(code, stock_name, quantity, "보유일 초과", trade_manager)
            continue

def _sell(stock_code, stock_name, quantity, reason, trade_manager):
    """
    시장가 전량 매도 실행
    """
    result = trade_manager.place_order(
        stock_code=stock_code,
        order_type=2,  # 매도
        quantity=quantity,
        price=0,
        order_division="03",  # 시장가
        screen_no="1821"
    )

    if result["status"] == "success":
        msg = f"🔽 매도 실행: {stock_name}({stock_code}) - 수량 {quantity} ({reason})"
        logger.info(msg)
        send_telegram_message(msg)
    else:
        msg = f"❌ 매도 실패: {stock_name}({stock_code}) - {result.get('message', '알 수 없는 오류')}"
        logger.error(msg)
        send_telegram_message(msg)
