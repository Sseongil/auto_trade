# modules/strategies/monitor_positions_strategy.py

import logging
from datetime import datetime, time, timedelta 
import time as time_module

from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
from modules.common.config import (
    TAKE_PROFIT_PCT_1ST, TRAIL_STOP_PCT_2ND, STOP_LOSS_PCT_ABS,
    TIME_STOP_MINUTES
)

logger = logging.getLogger(__name__)

def monitor_positions_strategy(monitor_positions, trade_manager): 
    """
    모든 보유 포지션을 모니터링하고, 사전 정의된 전략(익절, 손절, 트레일링 스탑, 시간 손절 등)에 따라
    매도 주문을 실행하거나 포지션 정보를 업데이트하는 함수.
    이 함수는 local_api_server의 백그라운드 트레이딩 루프에서 주기적으로 호출됩니다.
    """
    now = datetime.now()
    current_time_str = get_current_time_str()
    
    logger.info(f"[{current_time_str}] 포지션 모니터링 및 매매 전략 실행 중...")

    if not monitor_positions.kiwoom_helper.connected_state == 0: 
        logger.warning(f"[{current_time_str}] Kiwoom API 연결 상태 불량. 포지션 모니터링 건너뜀.")
        _handle_market_close_cleanup(monitor_positions, trade_manager, now)
        return

    current_positions = monitor_positions.get_all_positions()

    if not current_positions:
        logger.info(f"[{current_time_str}] 현재 보유 중인 포지션이 없습니다.")
        _handle_market_close_cleanup(monitor_positions, trade_manager, now) 
        return

    if time(9, 5) <= now.time() < time(15, 20): 
        for stock_code, pos_data in current_positions.items():
            try:
                if pos_data['quantity'] <= 0: 
                    logger.debug(f"[{current_time_str}] {pos_data.get('name', stock_code)} - 수량 0 또는 음수. 모니터링 건너뜀.")
                    if pos_data.get('buy_time') is not None and pos_data['quantity'] == 0:
                         monitor_positions.remove_position(stock_code)
                    continue

                current_price = monitor_positions.kiwoom_helper.real_time_data.get(stock_code, {}).get('current_price', 0)
                if current_price == 0:
                    logger.warning(f"⚠️ {pos_data['name']}({stock_code}) 실시간 현재가 정보 없음. 매도 전략 건너뜀.")
                    continue

                purchase_price = pos_data['purchase_price']
                quantity = pos_data['quantity']
                name = pos_data['name']
                buy_time_str = pos_data.get('buy_time')
                half_exited = pos_data.get('half_exited', False) 
                trail_high = pos_data.get('trail_high', current_price) 

                if purchase_price == 0:
                    logger.warning(f"⚠️ {name}({stock_code}) 매입가 0. 매도 전략 실행 불가.")
                    continue

                pnl_pct = ((current_price - purchase_price) / purchase_price) * 100

                if current_price > trail_high:
                    pos_data['trail_high'] = current_price
                    monitor_positions.save_positions() 
                    logger.debug(f"DEBUG: {name}({stock_code}) 트레일링 고점 갱신: {trail_high:,} -> {current_price:,}원")
                
                if pnl_pct >= TAKE_PROFIT_PCT_1ST and quantity > 0 and not half_exited:
                    sell_quantity = quantity // 2 
                    if sell_quantity > 0:
                        logger.info(f"✅ {name}({stock_code}) 1차 익절 조건 달성 (+{pnl_pct:.2f}%). 50% 분할 매도 시도.")
                        send_telegram_message(f"✅ 1차 익절: {name}({stock_code}) +{pnl_pct:.2f}% (매수량 50% 매도)")
                        trade_manager.place_order(stock_code, 2, sell_quantity, 0, "03") 
                        pos_data['half_exited'] = True 
                        monitor_positions.save_positions() 
                        continue 

                drop_from_high_pct = ((trail_high - current_price) / trail_high) * 100 if trail_high != 0 else 0.0
                if drop_from_high_pct >= TRAIL_STOP_PCT_2ND and quantity > 0:
                    logger.info(f"✅ {name}({stock_code}) 2차 익절(트레일링 스탑) 조건 달성. 최고가 대비 -{drop_from_high_pct:.2f}%. 전량 매도 시도.")
                    send_telegram_message(f"✅ 2차 익절(트레일링 스탑): {name}({stock_code}) 최고가 대비 -{drop_from_high_pct:.2f}% (전량 매도)")
                    trade_manager.place_order(stock_code, 2, quantity, 0, "03") 
                    continue

                if pnl_pct <= STOP_LOSS_PCT_ABS and quantity > 0:
                    logger.warning(f"🚨 {name}({stock_code}) 손절 조건 달성 ({pnl_pct:.2f}%). 전량 손절 시도.")
                    send_telegram_message(f"🚨 손절: {name}({stock_code}) {pnl_pct:.2f}% (전량 매도)")
                    trade_manager.place_order(stock_code, 2, quantity, 0, "03") 
                    continue

                if buy_time_str:
                    buy_time_dt = datetime.strptime(buy_time_str, "%Y-%m-%d %H:%M:%S")
                    time_since_buy = now - buy_time_dt
                    
                    if time_since_buy.total_seconds() >= TIME_STOP_MINUTES * 60 and quantity > 0:
                        if not half_exited and (STOP_LOSS_PCT_ABS < pnl_pct < TAKE_PROFIT_PCT_1ST):
                            logger.warning(f"🚨 {name}({stock_code}) 시간 손절 조건 달성 ({TIME_STOP_MINUTES}분 경과). 전량 매도 시도.")
                            send_telegram_message(f"🚨 시간 손절: {name}({stock_code}) {TIME_STOP_MINUTES}분 경과 (전량 매도)")
                            trade_manager.place_order(stock_code, 2, quantity, 0, "03") 
                            continue

                logger.debug(f"[{current_time_str}] {name}({stock_code}) 현재가: {current_price:,}원, 매입가: {purchase_price:,}원, 수익률: {pnl_pct:.2f}%")

            except Exception as e:
                logger.error(f"[{current_time_str}] {pos_data.get('name', stock_code)} 포지션 모니터링 중 오류 발생: {e}", exc_info=True)
        
    _handle_market_close_cleanup(monitor_positions, trade_manager, now)
    
    logger.info(f"[{current_time_str}] 포지션 모니터링 및 매매 전략 실행 종료.")


def _handle_market_close_cleanup(monitor_positions, trade_manager, now):
    """
    장 마감 임박 시 잔여 포지션을 정리하는 로직.
    """
    current_time_str = get_current_time_str()
    if time(15, 0) <= now.time() < time(15, 20):
        logger.info(f"[{current_time_str}] 장 마감 전 포지션 정리 시간.")
        for stock_code, pos_data in monitor_positions.get_all_positions().items():
            if pos_data['quantity'] > 0: 
                logger.warning(f"[{current_time_str}] 장 마감 임박. {pos_data['name']}({stock_code}) 잔여 포지션 강제 청산 시도.")
                send_telegram_message(f"🚨 장 마감 정리: {pos_data['name']}({stock_code}) 전량 시장가 매도 주문.")
                trade_manager.place_order(stock_code, 2, pos_data['quantity'], 0, "03") 

    elif now.time() >= time(15, 20) and now.time() < time(15, 30): 
        logger.info(f"[{current_time_str}] 장 마감 동시호가 시간. 추가 매매/매도 불가.")
    elif now.time() >= time(15, 30) or now.time() < time(9, 0): 
        logger.info(f"[{current_time_str}] 현재 매매 시간 아님. 대기 중...")

