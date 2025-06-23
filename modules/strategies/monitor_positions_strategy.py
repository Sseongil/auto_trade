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

    logger.info(f"[{current_time_str}] Kiwoom API로부터 최신 보유 종목 현황 조회 중...")
    api_holdings_data = monitor_positions.kiwoom_tr_request.request_daily_account_holdings(
        monitor_positions.account_number
    )
    
    if isinstance(api_holdings_data, dict) and "error" in api_holdings_data:
        logger.error(f"[{current_time_str}] ❌ Kiwoom API 보유 종목 조회 실패: {api_holdings_data['error']}. 포지션 모니터링을 중단합니다.")
        _handle_market_close_cleanup(monitor_positions, trade_manager, now)
        return
    
    monitor_positions.sync_local_positions(api_holdings_data)
    
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
                logger.debug(f"[{current_time_str}] {pos_data.get('name', stock_code)} - 수량 0 또는 음수. 모니터링 건너뛰고 해당 포지션 삭제 시도.")
                monitor_positions.remove_position(stock_code) 
                continue

            current_price = pos_data.get('current_price', 0)
            if current_price == 0: 
                logger.warning(f"[{current_time_str}] {pos_data.get('name', stock_code)}의 현재가가 API 데이터에 없습니다. 전략 실행에 제한이 있을 수 있습니다.")
                continue 

            purchase_price = pos_data['purchase_price']
            
            pnl_pct = (current_price - purchase_price) / purchase_price * 100 if purchase_price != 0 else 0

            logger.info(f"🔍 {pos_data.get('name', stock_code)}({stock_code}) | 현재가: {current_price:,}원, 수익률: {pnl_pct:.2f}%, 보유일: {(datetime.now() - datetime.strptime(pos_data.get('buy_date', '1900-01-01'), '%Y-%m-%d')).days}일, 추적고점: {pos_data.get('trail_high', 0.0):,}원")

            action_taken = False 

            if pnl_pct <= STOP_LOSS_PCT:
                logger.warning(f"❌ 손절 조건 충족: {pos_data.get('name', stock_code)}({stock_code}) 수익률 {pnl_pct:.2f}% (기준: {STOP_LOSS_PCT:.2f}%)")
                order_quantity = pos_data['quantity']
                if order_quantity > 0:
                    result = trade_manager.place_order(stock_code, 2, order_quantity, 0, "03") 
                    if result["status"] == "success":
                        send_telegram_message(f"❌ 손절: {pos_data.get('name', stock_code)}({stock_code}) | 수익률: {pnl_pct:.2f}% | 수량: {order_quantity}주")
                        action_taken = True
                    else:
                        logger.error(f"🔴 손절 주문 실패: {pos_data.get('name', stock_code)}({stock_code}) {result.get('message', '알 수 없는 오류')}")
            
            if not action_taken:
                if not pos_data.get('half_exited', False) and pnl_pct >= TAKE_PROFIT_PCT:
                    logger.info(f"🎯 50% 익절 조건 충족: {pos_data.get('name', stock_code)}({stock_code}) 수익률 {pnl_pct:.2f}% (기준: {TAKE_PROFIT_PCT:.2f}%)")
                    half_qty = (pos_data['quantity'] // 2 // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE
                    
                    if half_qty > 0:
                        result = trade_manager.place_order(stock_code, 2, half_qty, 0, "03") 
                        if result["status"] == "success":
                            send_telegram_message(f"🎯 50% 익절: {pos_data.get('name', stock_code)}({stock_code}) | 수익률: {pnl_pct:.2f}% | 수량: {half_qty}주")
                            
                            monitor_positions.positions[stock_code]["half_exited"] = True
                            monitor_positions.positions[stock_code]["trail_high"] = current_price 
                            monitor_positions.save_positions() 
                            
                            logger.info(f"업데이트: {pos_data.get('name', stock_code)}({stock_code}) 남은 수량: {monitor_positions.positions[stock_code]['quantity']}주, 추적고점: {monitor_positions.positions[stock_code]['trail_high']:,}원")
                            action_taken = True
                        else:
                            logger.error(f"🔴 50% 익절 주문 실패: {pos_data.get('name', stock_code)}({stock_code}) {result.get('message', '알 수 없는 오류')}")
                
            if not action_taken and pos_data.get('half_exited', False):
                if current_price > pos_data.get('trail_high', 0.0):
                    monitor_positions.positions[stock_code]["trail_high"] = current_price
                    monitor_positions.save_positions() 
                    logger.debug(f"추적고점 업데이트: {pos_data.get('name', stock_code)}({stock_code}) -> {monitor_positions.positions[stock_code]['trail_high']:,}원")
                elif current_price <= pos_data.get('trail_high', 0.0) * (1 - TRAIL_STOP_PCT / 100):
                    logger.warning(f"📉 트레일링 스탑 조건 충족: {pos_data.get('name', stock_code)}({stock_code}) 현재가 {current_price}원, 추적고점 {pos_data.get('trail_high', 0.0)}원 (하락률: {((pos_data.get('trail_high', 0.0) - current_price)/pos_data.get('trail_high', 0.0)*100):.2f}%)")
                    order_quantity = pos_data['quantity']
                    if order_quantity > 0:
                        pnl_on_exit = (current_price - purchase_price) / purchase_price * 100 if purchase_price != 0 else 0
                        result = trade_manager.place_order(stock_code, 2, order_quantity, 0, "03") 
                        if result["status"] == "success":
                            send_telegram_message(f"📉 트레일링 스탑: {pos_data.get('name', stock_code)}({stock_code}) | 수익률: {pnl_on_exit:.2f}% | 수량: {order_quantity}주")
                            action_taken = True
                        else:
                            logger.error(f"🔴 트레일링 스탑 주문 실패: {pos_data.get('name', stock_code)}({stock_code}) {result.get('message', '알 수 없는 오류')}")
            
            if not action_taken:
                if pos_data.get("buy_date") and (datetime.now() - datetime.strptime(pos_data["buy_date"], "%Y-%m-%d")).days >= MAX_HOLD_DAYS:
                    logger.info(f"⌛ 보유일 초과 조건 충족: {pos_data.get('name', stock_code)}({stock_code}) 보유일 {(datetime.now() - datetime.strptime(pos_data['buy_date'], '%Y-%m-%d')).days}일 (기준: {MAX_HOLD_DAYS}일)")
                    order_quantity = pos_data['quantity']
                    if order_quantity > 0:
                        pnl_on_exit = (current_price - purchase_price) / purchase_price * 100 if purchase_price != 0 else 0
                        result = trade_manager.place_order(stock_code, 2, order_quantity, 0, "03") 
                        if result["status"] == "success":
                            send_telegram_message(f"⌛ 보유일 초과 청산: {pos_data.get('name', stock_code)}({stock_code}) | 수익률: {pnl_on_exit:.2f}% | 수량: {order_quantity}주")
                            action_taken = True
                        else:
                            logger.error(f"🔴 보유일 초과 청산 주문 실패: {pos_data.get('name', stock_code)}({stock_code}) {result.get('message', '알 수 없는 오류')}")
            
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
