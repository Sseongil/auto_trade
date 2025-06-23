# modules/strategies/monitor_positions_strategy.py

import logging
from datetime import datetime, time, timedelta 
import time as time_module

from modules.common.utils import get_current_time_str
from modules.common.config import STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_STOP_PCT, MAX_HOLD_DAYS, DEFAULT_LOT_SIZE 

logger = logging.getLogger(__name__)

def monitor_positions_strategy(monitor_positions, trade_manager): 
    now = datetime.now()
    current_time_str = get_current_time_str()
    
    logger.info(f"[{current_time_str}] 포지션 모니터링 및 매매 전략 실행 중...")

    current_positions = monitor_positions.get_all_positions()

    if not current_positions:
        logger.info(f"[{current_time_str}] 현재 보유 중인 포지션이 없습니다.")
        _handle_market_close_cleanup(monitor_positions, trade_manager, now)
        return

    if not monitor_positions.kiwoom_helper.connected_state == 0: 
        logger.warning(f"[{current_time_str}] Kiwoom API 연결 상태 불량. 포지션 모니터링 건너뜁니다.")
        _handle_market_close_cleanup(monitor_positions, trade_manager, now)
        return

    for stock_code, pos_data in current_positions.items():
        try:
            if pos_data['quantity'] <= 0: 
                logger.debug(f"[{current_time_str}] {pos_data.get('name', stock_code)} - 수량 0 또는 음수. 모니터링 건너뜁니다.")
                if pos_data.get('buy_time') is None and pos_data['quantity'] == 0:
                     monitor_positions.remove_position(stock_code)
                continue

            current_price = 0 
            
            purchase_price = pos_data['purchase_price']
            
            # 💡 전략 구현 시작: 익절, 손절, 트레일링 스탑, 시간 손절
            
            # 1. 시간 손절 (MAX_HOLD_DAYS 활용) - buy_time이 있을 경우에만
            if pos_data.get("buy_time"):
                buy_time_dt = datetime.strptime(pos_data["buy_time"], "%Y-%m-%d %H:%M:%S")
                hold_duration = now - buy_time_dt
                
                if hold_duration >= timedelta(days=MAX_HOLD_DAYS): 
                    logger.warning(f"[{current_time_str}] {pos_data['name']}({stock_code}) 보유 기간 초과 ({hold_duration}). 강제 청산 시도.")
                    # trade_manager.place_order(stock_code, pos_data['quantity'], "sell", "시장가") 
                    # monitor_positions.remove_position(stock_code) 
                    logger.info(f"[{current_time_str}] {pos_data['name']}({stock_code}) 시간 손절 (시뮬레이션).")
                    continue 

            # 2. 익절 (TAKE_PROFIT_PCT 활용)
            # if current_price > purchase_price * (1 + TAKE_PROFIT_PCT / 100):
            #     logger.info(f"[{current_time_str}] {pos_data['name']}({stock_code}) 익절 조건 달성. 매도 시도.")
            #     trade_manager.place_order(stock_code, pos_data['quantity'], "sell", "시장가")
            #     # 주문 체결 후 monitor_positions.remove_position(stock_code) 호출 필요
            #     continue

            # 3. 손절 (STOP_LOSS_PCT 활용)
            # if current_price < purchase_price * (1 - STOP_LOSS_PCT / 100):
            #     logger.warning(f"[{current_time_str}] {pos_data['name']}({stock_code}) 손절 조건 달성. 매도 시도.")
            #     trade_manager.place_order(stock_code, pos_data['quantity'], "sell", "시장가")
            #     # 주문 체결 후 monitor_positions.remove_position(stock_code) 호출 필요
            #     continue

            # 4. 트레일링 스탑 (TRAIL_STOP_PCT 활용)
            # if current_price > pos_data['trail_high']:
            #     pos_data['trail_high'] = current_price 
            #     monitor_positions.save_positions() 
            # else:
            #     if current_price < pos_data['trail_high'] * (1 - TRAIL_STOP_PCT / 100):
            #         logger.info(f"[{current_time_str}] {pos_data['name']}({stock_code}) 트레일링 스탑 조건 달성. 매도 시도.")
            #         trade_manager.place_order(stock_code, pos_data['quantity'], "sell", "시장가")
            #         # 주문 체결 후 monitor_positions.remove_position(stock_code) 호출 필요
            #         continue

            logger.debug(f"[{current_time_str}] {pos_data['name']}({stock_code}) 포지션 모니터링 완료.")

        except Exception as e:
            logger.error(f"[{current_time_str}] {pos_data.get('name', stock_code)} 포지션 모니터링 중 오류 발생: {e}", exc_info=True)

    _handle_market_close_cleanup(monitor_positions, trade_manager, now)
    
    logger.info(f"[{current_time_str}] 포지션 모니터링 및 매매 전략 실행 종료.")

def _handle_market_close_cleanup(monitor_positions, trade_manager, now):
    current_time_str = get_current_time_str()
    if time(15, 0) <= now.time() < time(15, 20):
        logger.info(f"[{current_time_str}] 장 마감 전 포지션 정리 시간.")
        for stock_code, pos_data in monitor_positions.get_all_positions().items():
            if pos_data['quantity'] > 0: 
                logger.warning(f"[{current_time_str}] 장 마감 임박. {pos_data['name']}({stock_code}) 잔여 포지션 강제 청산 시도.")
                # trade_manager.place_order(stock_code, pos_data['quantity'], "sell", "지정가", price=0) 
                # monitor_positions.remove_position(stock_code) 
                logger.info(f"[{current_time_str}] {pos_data['name']}({stock_code}) 강제 청산 (시뮬레이션).")
    elif now.time() >= time(15, 20) and now.time() < time(15, 30): 
        logger.info(f"[{current_time_str}] 장 마감 동시호가 시간. 추가 매매/매도 불가.")
    elif now.time() >= time(15, 30) or now.time() < time(9, 0):
        logger.info(f"[{current_time_str}] 현재 매매 시간 아님. 대기 중...")
