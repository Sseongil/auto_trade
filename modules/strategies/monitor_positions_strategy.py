# modules/Kiwoom/monitor_positions_strategy.py

from datetime import datetime, timedelta
from modules.common.utils import get_current_time_str
from modules.common.config import (
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TRAIL_STOP_PCT,
    MAX_HOLD_DAYS,
    TRADE_LOG_FILE_PATH,
)
from modules.notify import send_telegram_message
from modules.trade_logger import log_trade


def monitor_positions_strategy(monitor_positions, trade_manager):
    """
    각 보유 종목에 대해 청산 조건(익절, 손절, 트레일링 스탑, 보유일 초과 등)을 점검하고 자동 매도 실행.
    Args:
        monitor_positions (MonitorPositions): 포지션 관리 객체
        trade_manager (TradeManager): 주문 실행 객체
    """
    positions = monitor_positions.get_current_positions()
    now = datetime.now()

    for pos in positions:
        ticker = pos["ticker"]
        name = pos["name"]
        buy_price = float(pos["buy_price"])
        quantity = int(pos["quantity"])
        buy_date = datetime.strptime(pos["buy_date"], "%Y-%m-%d")
        hold_days = (now - buy_date).days
        half_exited = pos.get("half_exited", False)
        trail_high = float(pos.get("trail_high", buy_price))

        # 현재가 가져오기
        current_price = trade_manager.get_current_price(ticker)
        if current_price <= 0:
            continue

        # 수익률 계산
        pnl_pct = ((current_price - buy_price) / buy_price) * 100

        # 최고가 갱신
        if pnl_pct > 5.0:
            pos["trail_high"] = max(trail_high, current_price)
            trail_high = pos["trail_high"]

        ### 손절 조건: -2% 하락
        if pnl_pct <= STOP_LOSS_PCT:
            reason = f"❌ 손절 실행: {name} ({pnl_pct:.2f}%)"
            _exit_position(
                ticker, quantity, current_price, reason,
                trade_manager, monitor_positions, pos
            )
            continue

        ### 익절 조건: +5% 이상 시 절반 익절
        if pnl_pct >= TAKE_PROFIT_PCT and not half_exited:
            half_qty = quantity // 2
            reason = f"✅ 1차 익절 (50%): {name} +{pnl_pct:.2f}%"
            _partial_exit_position(
                ticker, half_qty, current_price, reason,
                trade_manager, monitor_positions, pos
            )
            continue

        ### 트레일링 스탑 조건: +10% 이상 상승 후 고점 대비 -1% 하락
        if pnl_pct >= 10.0 and current_price < trail_high * (1 - TRAIL_STOP_PCT / 100):
            reason = f"📉 트레일링 스탑 발동: {name} - 최고가 대비 하락"
            _exit_position(
                ticker, quantity, current_price, reason,
                trade_manager, monitor_positions, pos
            )
            continue

        ### 보유 기간 초과 조건
        if hold_days >= MAX_HOLD_DAYS:
            reason = f"⏰ 보유일 초과 {hold_days}일: {name} 매도"
            _exit_position(
                ticker, quantity, current_price, reason,
                trade_manager, monitor_positions, pos
            )


def _exit_position(ticker, quantity, price, reason, trade_manager, monitor_positions, pos):
    """전량 매도 실행 및 포지션 제거"""
    try:
        result = trade_manager.place_order(ticker, 2, quantity, price, "03")  # 시장가 매도
        log_trade(ticker, "SELL_ALL", quantity, price, reason)
        send_telegram_message(f"{reason}\n💵 {quantity}주 @ {price:,}원 매도 완료")
        monitor_positions.remove_position(ticker)
    except Exception as e:
        send_telegram_message(f"❗ 매도 실패: {ticker}\n오류: {e}")


def _partial_exit_position(ticker, quantity, price, reason, trade_manager, monitor_positions, pos):
    """절반 매도 실행 (익절) 및 포지션 수정"""
    try:
        result = trade_manager.place_order(ticker, 2, quantity, price, "03")  # 시장가 매도
        log_trade(ticker, "SELL_HALF", quantity, price, reason)
        send_telegram_message(f"{reason}\n📤 절반 매도: {quantity}주 @ {price:,}원")
        pos["quantity"] -= quantity
        pos["half_exited"] = True
        monitor_positions.save_positions()
    except Exception as e:
        send_telegram_message(f"❗ 절반 매도 실패: {ticker}\n오류: {e}")
