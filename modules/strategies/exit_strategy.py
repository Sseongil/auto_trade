# modules/strategies/exit_strategy.py

import logging
from datetime import datetime, timedelta
from modules.common.config import (
    TAKE_PROFIT_PCT_1ST, TRAIL_STOP_PCT_2ND, STOP_LOSS_PCT_ABS, MAX_HOLD_DAYS,
    EXIT_STRATEGY_PRIORITY, MIN_HOLD_TIME_MINUTES
)
from modules.notify import send_telegram_message
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

def execute_exit_strategy(kiwoom_helper, trade_manager, monitor_positions):
    """
    현재 포지션들을 순회하며 자동 익절/손절 전략을 실행합니다.
    """
    current_time_str = get_current_time_str()
    logger.info(f"[{current_time_str}] 자동 익절/손절 전략 실행 시작")

    positions = monitor_positions.get_all_positions()
    now = datetime.now()

    for code, pos in positions.items():
        stock_name = pos.get("name", "Unknown") # '종목명' 대신 'name' 사용
        quantity = pos.get("quantity", 0)
        purchase_price = pos.get("purchase_price", 0)
        buy_time_str = pos.get("buy_time", None) # '매수일시' 대신 'buy_time' 사용
        half_exited = pos.get("half_exited", False) # '절반익절' 대신 'half_exited' 사용
        trail_high = pos.get('trail_high', purchase_price) # 'trail_high' 사용

        if quantity <= 0 or purchase_price <= 0 or not buy_time_str:
            logger.debug(f"[{stock_name}({code})] 포지션 데이터 불완전 또는 수량 0. 건너뜀.")
            continue

        try:
            buy_time = datetime.strptime(buy_time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.error(f"[{stock_name}({code})] 잘못된 매수 시간 형식: {buy_time_str}. 건너뜀.")
            continue

        # ✅ 매수 후 최소 보유 시간 체크
        if (now - buy_time).total_seconds() < MIN_HOLD_TIME_MINUTES * 60:
            logger.debug(f"[{stock_name}({code})] 매수 후 최소 보유 시간({MIN_HOLD_TIME_MINUTES}분) 미경과. 현재 경과: {(now - buy_time).total_seconds() / 60:.1f}분. 매도 전략 건너뜀.")
            continue

        current_price = kiwoom_helper.real_time_data.get(code, {}).get('current_price', 0)
        if current_price == 0:
            logger.warning(f"[{stock_name}({code})] 현재가 정보 없음. 익절/손절 조건 검사 건너뜀.")
            continue

        # 수익률 계산
        pnl_pct = ((current_price - purchase_price) / purchase_price) * 100
        hold_days = (now - buy_time).days

        # 매도 조건 우선순위 로직
        conditions_met = []

        # 손절 조건
        if pnl_pct <= -STOP_LOSS_PCT_ABS: # STOP_LOSS_PCT_ABS는 양수이므로 음수로 비교
            conditions_met.append(("STOP_LOSS", pnl_pct))

        # 1차 익절 조건 (절반 매도)
        if pnl_pct >= TAKE_PROFIT_PCT_1ST and not half_exited:
            conditions_met.append(("TAKE_PROFIT_1ST", pnl_pct))

        # 트레일링 스탑 (1차 익절 후 또는 전량 매도 시)
        if pnl_pct >= 0.8: # 최소한 수익권에 있을 때만 트레일링 스탑 작동
            if current_price > trail_high:
                monitor_positions.update_position_trail_high(code, current_price) # trail_high 업데이트
                logger.debug(f"[{stock_name}({code})] 트레일링 스탑 최고가 갱신: {current_price:,}원")
            elif current_price <= trail_high * (1 - TRAIL_STOP_PCT_2ND / 100.0): # TRAIL_STOP_PCT_2ND는 % 값
                conditions_met.append(("TRAIL_STOP", pnl_pct))

        # 보유일 초과
        if hold_days >= MAX_HOLD_DAYS:
            conditions_met.append(("MAX_HOLD_DAYS", hold_days))


        # ✅ 우선순위에 따른 조건 처리
        if EXIT_STRATEGY_PRIORITY == "PROFIT_FIRST":
            # 익절 조건 먼저 확인
            if any(c[0] == "TAKE_PROFIT_1ST" for c in conditions_met):
                half_qty = max(1, quantity // 2)
                if half_qty > 0:
                    logger.info(f"[{current_time_str}] ✅ 익절 조건 만족: {stock_name}({code}) 수익률 {pnl_pct:.2f}% → 절반 매도 시도")
                    _sell(code, stock_name, half_qty, "익절 (절반)", trade_manager, monitor_positions)
                continue # 익절 후 다음 종목으로 이동

            if any(c[0] == "TRAIL_STOP" for c in conditions_met):
                logger.info(f"[{current_time_str}] 📉 트레일링 스탑 발동: {stock_name}({code}) 수익률 {pnl_pct:.2f}% → 전량 매도 시도")
                _sell(code, stock_name, quantity, "트레일링 스탑", trade_manager, monitor_positions)
                continue

            # 손절 조건
            if any(c[0] == "STOP_LOSS" for c in conditions_met):
                logger.info(f"[{current_time_str}] ❌ 손절 조건 충족: {stock_name}({code}) 손실률 {pnl_pct:.2f}% → 전량 매도 시도")
                _sell(code, stock_name, quantity, "손절", trade_manager, monitor_positions)
                continue

            # 보유일 초과
            if any(c[0] == "MAX_HOLD_DAYS" for c in conditions_met):
                logger.info(f"[{current_time_str}] ⏰ 보유일 초과 청산: {stock_name}({code}) {hold_days}일 경과 → 전량 매도 시도")
                _sell(code, stock_name, quantity, "보유일 초과", trade_manager, monitor_positions)
                continue

        elif EXIT_STRATEGY_PRIORITY == "LOSS_FIRST":
            # 손절 조건 먼저 확인
            if any(c[0] == "STOP_LOSS" for c in conditions_met):
                logger.info(f"[{current_time_str}] ❌ 손절 조건 충족: {stock_name}({code}) 손실률 {pnl_pct:.2f}% → 전량 매도 시도")
                _sell(code, stock_name, quantity, "손절", trade_manager, monitor_positions)
                continue

            # 익절 조건
            if any(c[0] == "TAKE_PROFIT_1ST" for c in conditions_met):
                half_qty = max(1, quantity // 2)
                if half_qty > 0:
                    logger.info(f"[{current_time_str}] ✅ 익절 조건 만족: {stock_name}({code}) 수익률 {pnl_pct:.2f}% → 절반 매도 시도")
                    _sell(code, stock_name, half_qty, "익절 (절반)", trade_manager, monitor_positions)
                continue

            if any(c[0] == "TRAIL_STOP" for c in conditions_met):
                logger.info(f"[{current_time_str}] 📉 트레일링 스탑 발동: {stock_name}({code}) 수익률 {pnl_pct:.2f}% → 전량 매도 시도")
                _sell(code, stock_name, quantity, "트레일링 스탑", trade_manager, monitor_positions)
                continue

            # 보유일 초과
            if any(c[0] == "MAX_HOLD_DAYS" for c in conditions_met):
                logger.info(f"[{current_time_str}] ⏰ 보유일 초과 청산: {stock_name}({code}) {hold_days}일 경과 → 전량 매도 시도")
                _sell(code, stock_name, quantity, "보유일 초과", trade_manager, monitor_positions)
                continue

    logger.info(f"[{current_time_str}] 자동 익절/손절 전략 실행 종료.")


def _sell(stock_code, stock_name, quantity, reason, trade_manager, monitor_positions):
    """
    시장가 전량 매도 실행 및 포지션 업데이트
    """
    if quantity <= 0:
        logger.warning(f"[{stock_name}({stock_code})] 매도 수량 0. 매도 주문을 보내지 않습니다.")
        return

    logger.info(f"[{stock_name}({stock_code})] {reason}으로 {quantity}주 시장가 매도 시도...")
    send_telegram_message(f"🚨 매도 시도: {stock_name}({stock_code}) - {reason} ({quantity}주)")

    result = trade_manager.place_order(
        stock_code=stock_code,
        order_type=2,  # 2: 매도
        quantity=quantity,
        price=0,       # 0: 시장가
        order_division="03" # 03: 시장가
    )

    if result["status"] == "success":
        logger.info(f"✅ {stock_name}({stock_code}) {reason} 매도 주문 성공. 주문번호: {result.get('order_no')}")
        # MonitorPositions에서 체결 이벤트를 통해 자동으로 포지션 업데이트/삭제됨
    else:
        logger.error(f"❌ {stock_name}({stock_code}) {reason} 매도 주문 실패: {result.get('message', '알 수 없는 오류')}")
        send_telegram_message(f"❌ 매도 실패: {stock_name}({stock_code}) - {reason} ({result.get('message', '알 수 없는 오류')})")

