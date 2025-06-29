# modules/strategies/exit_strategy.py

import logging
from datetime import datetime, timedelta
# config.py에서 관련 상수 임포트
from modules.common.config import STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_STOP_PCT, MAX_HOLD_DAYS, EXIT_STRATEGY_SCREEN_NO
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)

def exit_strategy(monitor_positions, trade_manager):
    """
    현재 포지션을 순회하며 자동 익절/손절/보유일 초과 조건을 체크 후 매도합니다.
    이 함수는 local_api_server의 백그라운드 트레이딩 루프에서 주기적으로 호출됩니다.
    """
    all_positions = monitor_positions.get_all_positions()
    now = datetime.now()

    if not all_positions:
        logger.info("현재 보유 중인 포지션이 없습니다. 매도 전략을 건너뜀.")
        return

    for code, pos in all_positions.items():
        stock_name = pos.get("name", "Unknown") # '종목명' 대신 'name' 사용
        quantity = pos.get("quantity", 0) # '보유수량' 대신 'quantity' 사용
        avg_price = pos.get("purchase_price", 0) # '매입가' 대신 'purchase_price' 사용
        buy_time_str = pos.get("buy_time", None) # '매수일시' 대신 'buy_time' 사용
        sold_half = pos.get("half_exited", False) # '절반익절' 대신 'half_exited' 사용

        # 필수 데이터가 없는 경우 건너뛰기
        if quantity <= 0 or avg_price <= 0 or not buy_time_str:
            logger.warning(f"[{stock_name}({code})] 매도 전략 검토를 위한 필수 포지션 데이터 부족. 건너뜜.")
            continue

        current_price = trade_manager.kiwoom_helper.real_time_data.get(code, {}).get("current_price")

        # 현재가 조회 실패 시 경고 로깅 및 다음 종목으로 넘어감
        if current_price is None or current_price <= 0:
            logger.warning(f"[{stock_name}({code})] 실시간 현재가 조회 실패 또는 0 이하 값: {current_price}. 매도 전략 검토 불가.")
            continue

        try:
            # 수익률 계산
            change_pct = ((current_price - avg_price) / avg_price) * 100
            logger.info(f"[{stock_name}({code})] 현재가: {current_price:,}원, 매입가: {avg_price:,}원, 수익률: {change_pct:.2f}%")

            # 보유일수 계산
            buy_time = datetime.strptime(buy_time_str, "%Y-%m-%d %H:%M:%S")
            hold_days = (now - buy_time).days

            # 1. 손절 조건
            if change_pct <= float(STOP_LOSS_PCT):
                logger.info(f"❌ 손절 조건 만족: {stock_name}({code}) 수익률 {change_pct:.2f}% (설정: {STOP_LOSS_PCT}%)")
                _sell(code, stock_name, quantity, "손절", trade_manager)
                continue # 매도 후 다음 포지션으로

            # 2. 익절 조건 (50%만 매도) - 아직 절반 매도하지 않았을 경우
            if not sold_half and change_pct >= float(TAKE_PROFIT_PCT):
                half_qty = max(1, quantity // 2) # 최소 1주 매도
                logger.info(f"✅ 익절 조건 만족: {stock_name}({code}) 수익률 {change_pct:.2f}% (설정: {TAKE_PROFIT_PCT}%) → 절반 매도 시도")
                _sell(code, stock_name, half_qty, "익절 (절반)", trade_manager)
                monitor_positions.mark_half_sold(code)  # 절반 익절 기록
                continue # 매도 후 다음 포지션으로

            # 3. 트레일링 스탑 (익절 후) - 절반 매도 상태일 경우
            if sold_half and change_pct <= float(TRAIL_STOP_PCT):
                logger.info(f"📉 트레일링 스탑 발동: {stock_name}({code}) 수익률 {change_pct:.2f}% (설정: {TRAIL_STOP_PCT}%)")
                _sell(code, stock_name, quantity, "트레일링 스탑", trade_manager)
                continue # 매도 후 다음 포지션으로

            # 4. 보유일 초과
            if hold_days >= int(MAX_HOLD_DAYS): # >= 로 변경하여 당일 포함 이상일 때 발동
                logger.info(f"⏰ 보유일 초과 청산: {stock_name}({code}) {hold_days}일 경과 (설정: {MAX_HOLD_DAYS}일)")
                _sell(code, stock_name, quantity, "보유일 초과", trade_manager)
                continue # 매도 후 다음 포지션으로

        except Exception as e:
            logger.error(f"[{stock_name}({code})] 매도 전략 검토 중 예외 발생: {e}", exc_info=True)
            send_telegram_message(f"🚨 매도 전략 오류: {stock_name}({code}) - {e}")


def _sell(stock_code, stock_name, quantity, reason, trade_manager):
    """
    시장가 매도 주문을 실행합니다.
    """
    if quantity <= 0:
        logger.warning(f"[{stock_name}({stock_code})] 매도 수량 0 또는 음수입니다. 매도 요청 무시.")
        return

    logger.info(f"[{stock_name}({stock_code})] 매도 시도: 수량 {quantity}주, 사유: {reason}")
    result = trade_manager.place_order(
        stock_code=stock_code,
        order_type=2,  # 2: 매도
        quantity=quantity,
        price=0,       # 시장가
        order_division="03",  # 03: 시장가
        screen_no=EXIT_STRATEGY_SCREEN_NO # config.py에서 정의된 화면번호 사용
    )

    if result["status"] == "success":
        msg = f"🔽 매도 성공: {stock_name}({stock_code}) - 수량 {quantity}주 ({reason})"
        logger.info(msg)
        send_telegram_message(msg)
    else:
        msg = f"❌ 매도 실패: {stock_name}({stock_code}) - {result.get('message', '알 수 없는 오류')} ({reason})"
        logger.error(msg)
        send_telegram_message(msg)
