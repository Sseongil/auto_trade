# modules/strategies/exit_strategy.py

import logging
from datetime import datetime
from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)

def execute_exit_strategy(kiwoom_helper, trade_manager, monitor_positions):
    """
    현재 포지션들을 순회하며 자동 익절/손절 전략을 실행합니다.
    """
    current_time_str = get_current_time_str()
    logger.info(f"[{current_time_str}] 자동 익절/손절 전략 실행 시작")

    positions = monitor_positions.get_all_positions()

    for code, pos in positions.items():
        current_price = kiwoom_helper.real_time_data.get(code, {}).get('current_price', 0)
        trail_high = pos.get('trail_high', pos['purchase_price'])

        if current_price == 0:
            logger.warning(f"{code}: 현재가 정보 없음. 익절/손절 조건 검사 건너뜀")
            continue

        purchase_price = pos['purchase_price']
        quantity = pos['quantity']

        # 손절 조건
        loss_pct = ((current_price - purchase_price) / purchase_price) * 100
        if loss_pct <= -1.2:
            logger.info(f"{code}: 손절 조건 충족 (수익률 {loss_pct:.2f}%). 시장가 매도 시도")
            result = trade_manager.place_order(code, 2, quantity, 0, "03")
            if result['status'] == 'success':
                send_telegram_message(f"🔻 손절 매도 완료: {code} 수익률 {loss_pct:.2f}%")
            else:
                logger.error(f"{code}: 손절 매도 실패 - {result.get('message', '알 수 없는 오류')}")
            continue

        # 익절 조건
        gain_pct = ((current_price - purchase_price) / purchase_price) * 100
        if gain_pct >= 2.0 and not pos.get('half_exited', False):
            half_qty = quantity // 2
            if half_qty > 0:
                logger.info(f"{code}: 익절 조건 충족 (수익률 {gain_pct:.2f}%). 절반 시장가 매도 시도")
                result = trade_manager.place_order(code, 2, half_qty, 0, "03")
                if result['status'] == 'success':
                    pos['half_exited'] = True
                    monitor_positions.save_positions()
                    send_telegram_message(f"✅ 절반 익절 매도 완료: {code} 수익률 {gain_pct:.2f}%")
                else:
                    logger.error(f"{code}: 절반 익절 매도 실패 - {result.get('message', '알 수 없는 오류')}")

        # 트레일링 스탑 조건
        if gain_pct >= 0.8:
            if current_price > trail_high:
                pos['trail_high'] = current_price
                monitor_positions.save_positions()
                logger.info(f"{code}: 트레일링 스탑 최고가 갱신: {current_price}")
            elif current_price <= trail_high * (1 - 0.008):
                logger.info(f"{code}: 트레일링 스탑 조건 충족. 시장가 매도 시도")
                result = trade_manager.place_order(code, 2, quantity, 0, "03")
                if result['status'] == 'success':
                    send_telegram_message(f"✅ 트레일링 스탑 매도 완료: {code}")
                else:
                    logger.error(f"{code}: 트레일링 스탑 매도 실패 - {result.get('message', '알 수 없는 오류')}")
