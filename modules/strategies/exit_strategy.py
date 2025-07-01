# modules/strategies/exit_strategy.py

import logging
from datetime import datetime, timedelta
from modules.common.config import STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_STOP_PCT, MAX_HOLD_DAYS
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)

def execute_exit_strategy(kiwoom_helper, trade_manager, monitor_positions):
    """
    현재 포지션들을 순회하며 자동 익절/손절 전략을 실행합니다.
    """
    now = datetime.now()
    current_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{current_time_str}] 자동 익절/손절 전략 실행 시작")

    all_positions = monitor_positions.get_all_positions()

    for code, pos in all_positions.items():
        stock_name = pos.get("name", "Unknown") # '종목명' 대신 'name' 사용
        quantity = pos.get("quantity", 0) # '보유수량' 대신 'quantity' 사용
        purchase_price = pos.get("purchase_price", 0) # '매입가' 대신 'purchase_price' 사용
        buy_time_str = pos.get("buy_time", None) # '매수일시' 대신 'buy_time' 사용
        half_exited = pos.get("half_exited", False) # '절반익절' 대신 'half_exited' 사용
        trail_high = pos.get('trail_high', purchase_price) # 트레일링 스탑 최고가

        if quantity <= 0 or purchase_price <= 0 or not buy_time_str:
            logger.debug(f"[{current_time_str}] {stock_name}({code}) 유효하지 않은 포지션 데이터. 건너뜀.")
            continue

        try:
            # 실시간 현재가 조회
            current_price = kiwoom_helper.real_time_data.get(code, {}).get('current_price', 0)
            if current_price == 0:
                logger.warning(f"[{current_time_str}] {stock_name}({code}) 현재가 정보 없음. 익절/손절 조건 검사 건너뜀")
                continue
        except Exception as e:
            logger.error(f"[{current_time_str}] {stock_name}({code}) 현재가 조회 실패: {e}", exc_info=True)
            continue

        # 수익률 계산
        gain_pct = ((current_price - purchase_price) / purchase_price) * 100

        # 보유 기간 계산
        try:
            buy_datetime = datetime.strptime(buy_time_str, "%Y-%m-%d %H:%M:%S")
            hold_duration = now - buy_datetime
            hold_days = hold_duration.days
            hold_minutes = hold_duration.total_seconds() / 60
        except ValueError:
            logger.error(f"[{current_time_str}] {stock_name}({code}) 매수일시 형식 오류: {buy_time_str}")
            hold_days = 0
            hold_minutes = 0

        logger.debug(f"[{current_time_str}] {stock_name}({code}) 현재가: {current_price:,}원, 매입가: {purchase_price:,}원, 수익률: {gain_pct:.2f}%, 보유일: {hold_days}일")

        # 1. 절대 손절 조건
        if gain_pct <= STOP_LOSS_PCT: # STOP_LOSS_PCT는 음수 값 (예: -1.0)
            logger.info(f"[{current_time_str}] 📉 손절 조건 충족: {stock_name}({code}) 수익률 {gain_pct:.2f}%")
            _sell(code, stock_name, quantity, "절대 손절", trade_manager)
            monitor_positions.remove_position(code) # 전량 매도 후 포지션 제거
            continue

        # 2. 익절 조건 (절반 매도)
        if gain_pct >= TAKE_PROFIT_PCT and not half_exited:
            half_qty = max(1, quantity // 2) # 최소 1주 매도
            if half_qty > 0:
                logger.info(f"[{current_time_str}] ✅ 익절 조건 만족: {stock_name}({code}) 수익률 {gain_pct:.2f}% → 절반 매도 시도")
                result = _sell(code, stock_name, half_qty, "익절 (절반)", trade_manager)
                if result and result.get("status") == "success":
                    monitor_positions.mark_half_sold(code) # 절반 익절 기록
                    # 남은 수량에 대한 매입가 및 트레일 하이 업데이트는 MonitorPositions 내부에서 처리
                else:
                    logger.error(f"[{current_time_str}] {stock_name}({code}) 절반 익절 매도 실패: {result.get('message', '알 수 없는 오류')}")
            continue # 절반 매도 후에는 다음 전략으로 넘어가지 않고 다음 종목 검사

        # 3. 트레일링 스탑 조건 (익절 후 또는 일정 수익률 이상에서 발동)
        # 트레일링 스탑은 익절 후 남은 물량에 대해 적용되거나, 특정 수익률 이상에서 적용될 수 있음
        # 여기서는 TAKE_PROFIT_PCT 이상 수익이 났을 때 트레일 하이를 갱신하고,
        # TRAIL_STOP_PCT 만큼 하락하면 전량 매도
        if gain_pct > 0: # 수익 중일 때만 트레일링 스탑 고려
            # 트레일 하이 갱신
            if current_price > trail_high:
                monitor_positions.update_trail_high(code, current_price)
                logger.debug(f"[{current_time_str}] {stock_name}({code}) 트레일링 스탑 최고가 갱신: {current_price:,}원")
                continue # 최고가 갱신만 하고 매도하지 않음

            # 트레일링 스탑 발동 (최고가 대비 TRAIL_STOP_PCT 만큼 하락)
            # TRAIL_STOP_PCT는 양수 값 (예: 0.8%)
            if current_price <= trail_high * (1 - TRAIL_STOP_PCT / 100):
                logger.info(f"[{current_time_str}] 📉 트레일링 스탑 발동: {stock_name}({code}) 최고가 {trail_high:,}원 대비 {TRAIL_STOP_PCT:.2f}% 하락")
                _sell(code, stock_name, quantity, "트레일링 스탑", trade_manager)
                monitor_positions.remove_position(code) # 전량 매도 후 포지션 제거
                continue

        # 4. 시간 손절 조건 (MAX_HOLD_DAYS 초과)
        if hold_days >= MAX_HOLD_DAYS: # MAX_HOLD_DAYS는 정수 (예: 3)
            logger.info(f"[{current_time_str}] ⏰ 보유일 초과 청산: {stock_name}({code}) {hold_days}일 경과")
            _sell(code, stock_name, quantity, "보유일 초과", trade_manager)
            monitor_positions.remove_position(code) # 전량 매도 후 포지션 제거
            continue

    logger.info(f"[{current_time_str}] 자동 익절/손절 전략 실행 종료.")


def _sell(stock_code, stock_name, quantity, reason, trade_manager):
    """
    시장가 전량 매도 실행을 요청합니다.
    """
    if quantity <= 0:
        logger.warning(f"⚠️ {stock_name}({stock_code}) 매도 수량 0 이하. 매도 요청 건너뜀.")
        return {"status": "error", "message": "Quantity is zero or less."}

    logger.info(f"🚀 {stock_name}({stock_code}) 시장가 매도 시도: 수량 {quantity}주 (사유: {reason})")
    send_telegram_message(f"🚀 매도 시도: {stock_name}({stock_code}) 수량: {quantity} (사유: {reason})")

    # trade_manager의 place_order 함수를 사용하여 매도 주문 요청
    # 주문 유형: 2 (신규매도), 가격: 0 (시장가), 거래구분: "03" (시장가)
    result = trade_manager.place_order(
        stock_code=stock_code,
        order_type=2, # 신규매도
        quantity=quantity,
        price=0, # 시장가
        order_division="03" # 시장가
    )

    if result["status"] == "success":
        logger.info(f"✅ {stock_name}({stock_code}) 시장가 매도 주문 성공 (사유: {reason})")
    else:
        logger.error(f"❌ {stock_name}({stock_code}) 시장가 매도 주문 실패 (사유: {reason}): {result.get('message', '알 수 없는 오류')}")
    
    return result

