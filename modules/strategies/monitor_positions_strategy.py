# modules/strategies/monitor_positions_strategy.py

from datetime import datetime, timedelta, time
from modules.common.config import (
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_STOP_PCT, MAX_HOLD_DAYS,
)
from modules.notify import send_telegram_message
from modules.trade_logger import log_trade

def monitor_positions_strategy(monitor_positions, trade_manager):
    positions = monitor_positions.get_current_positions()
    now = datetime.now()

    for pos in positions:
        ticker = pos["ticker"]
        name = pos["name"]
        buy_price = float(pos["buy_price"])
        quantity = int(pos["quantity"])  # ✔️ CSV에서 불러오면 float일 수 있음
        buy_date = datetime.strptime(pos["buy_date"], "%Y-%m-%d")
        buy_time = datetime.strptime(
            pos.get("buy_time", now.strftime("%Y-%m-%d %H:%M:%S")),
            "%Y-%m-%d %H:%M:%S"
        )
        half_exited = pos.get("half_exited", False)
        trail_high = float(pos.get("trail_high", buy_price))

        hold_minutes = (now - buy_time).total_seconds() / 60
        hold_days = (now - buy_date).days

        current_price = trade_manager.get_current_price(ticker)
        if current_price <= 0:
            continue

        pnl_pct = ((current_price - buy_price) / buy_price) * 100

        # 최고가 갱신
        if current_price > trail_high:
            pos["trail_high"] = current_price
            trail_high = current_price

        # 손절
        if pnl_pct <= STOP_LOSS_PCT:
            reason = f"❌ 손절 실행: {name} ({pnl_pct:.2f}%)"
            _exit_position(ticker, quantity, current_price, reason, trade_manager, monitor_positions, pos)
            continue

        # 1차 익절 (절반)
        if pnl_pct >= TAKE_PROFIT_PCT and not half_exited:
            half_qty = quantity // 2
            if half_qty == 0 and quantity > 0:
                half_qty = quantity
            elif half_qty == 0:
                continue
            reason = f"✅ 1차 익절: {name} +{pnl_pct:.2f}%"
            _partial_exit_position(ticker, half_qty, current_price, reason, trade_manager, monitor_positions, pos)
            continue

        # 2차 익절: 트레일링 스탑
        if half_exited and current_price <= trail_high * (1 - TRAIL_STOP_PCT / 100):
            reason = f"📉 트레일링 스탑: {name} 고점대비 하락"
            _exit_position(ticker, quantity, current_price, reason, trade_manager, monitor_positions, pos)
            continue

        # 시간 손절
        if hold_minutes >= 15 and not half_exited:
            reason = f"⏰ 15분 경과 시간 손절: {name}"
            _exit_position(ticker, quantity, current_price, reason, trade_manager, monitor_positions, pos)
            continue

        # 보유일 초과
        if MAX_HOLD_DAYS is not None and hold_days >= MAX_HOLD_DAYS:
            reason = f"🗓️ {MAX_HOLD_DAYS}일 초과 보유 손절: {name}"
            _exit_position(ticker, quantity, current_price, reason, trade_manager, monitor_positions, pos)
            continue

        # 장 마감 정리
        if now.time() >= time(15, 20):
            reason = f"🔚 장 마감 정리 매도: {name}"
            _exit_position(ticker, quantity, current_price, reason, trade_manager, monitor_positions, pos)

def _exit_position(ticker, quantity, price, reason, trade_manager, monitor_positions, pos):
    try:
        trade_manager.place_order(ticker, 2, quantity, price, "03")
        pnl = ((price - float(pos["buy_price"])) / float(pos["buy_price"])) * 100  # ✔️ 형변환
        log_trade(ticker, pos["name"], price, quantity, "SELL_ALL", pnl=pnl)
        send_telegram_message(f"{reason}\n💰 {quantity}주 @ {price:,}원 매도 완료")
        monitor_positions.remove_position(ticker)
    except Exception as e:
        send_telegram_message(f"❗ 매도 실패: {ticker} - {e}")

def _partial_exit_position(ticker, quantity, price, reason, trade_manager, monitor_positions, pos):
    try:
        trade_manager.place_order(ticker, 2, quantity, price, "03")
        pnl = ((price - float(pos["buy_price"])) / float(pos["buy_price"])) * 100
        log_trade(ticker, pos["name"], price, quantity, "SELL_HALF", pnl=pnl)
        pos["quantity"] = int(pos["quantity"]) - quantity
        pos["half_exited"] = True
        monitor_positions.save_positions()
        send_telegram_message(f"{reason}\n📤 {quantity}주 익절 완료")
    except Exception as e:
        send_telegram_message(f"❗ 절반 매도 실패: {ticker} - {e}")
