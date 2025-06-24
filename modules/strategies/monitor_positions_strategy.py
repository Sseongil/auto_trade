# modules/strategies/monitor_positions_strategy.py

import logging
from datetime import datetime, time, timedelta 
import time as time_module

from modules.common.utils import get_current_time_str
from modules.common.config import STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_STOP_PCT, MAX_HOLD_DAYS, DEFAULT_LOT_SIZE 
from modules.notify import send_telegram_message # 텔레그램 알림을 위해 임포트
from modules.trade_logger import TradeLogger # 💡 매매 로그 기록을 위해 TradeLogger 클래스 임포트

logger = logging.getLogger(__name__)

# TradeLogger 인스턴스를 전역적으로 생성 (필요시 TradeManager에서 주입 받을 수도 있음)
# 현재는 Strategy에서 직접 매매 로그를 남기므로 여기서 생성
trade_logger = TradeLogger()

def monitor_positions_strategy(monitor_positions, trade_manager): 
    now = datetime.now()
    current_time_str = get_current_time_str()
    
    logger.info(f"[{current_time_str}] 포지션 모니터링 및 매매 전략 실행 중...")

    # 최신 보유 현황을 키움 API에서 가져와서 로컬 데이터와 동기화
    # NOTE: api_holdings_data는 계좌 보유 종목 리스트를 가져오는 용도이며,
    # 각 종목의 `current_price`는 KiwoomQueryHelper의 `real_time_data`에서 가져올 것입니다.
    logger.info(f"[{current_time_str}] Kiwoom API로부터 최신 계좌 보유 현황 조회 중...")
    api_holdings_data = monitor_positions.kiwoom_tr_request.request_daily_account_holdings(
        monitor_positions.account_number
    )
    
    if isinstance(api_holdings_data, dict) and "error" in api_holdings_data:
        logger.error(f"[{current_time_str}] ❌ Kiwoom API 보유 종목 조회 실패: {api_holdings_data['error']}. 포지션 모니터링을 중단합니다.")
        _handle_market_close_cleanup(monitor_positions, trade_manager, now)
        return
    
    # Kiwoom API 보유 현황을 바탕으로 로컬 포지션 데이터 동기화
    monitor_positions.sync_local_positions(api_holdings_data)
    
    # 💡 실시간 시세 등록 (보유 종목에 대한 실시간 데이터를 구독)
    monitor_positions.register_all_positions_for_real_time_data()

    # 현재 포지션 데이터 가져오기 (이미 current_price는 real_time_data에서 업데이트됨)
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

            # 💡 current_price는 get_all_positions() 호출 시 이미 real_time_data에서 업데이트되어 있음
            current_price = pos_data.get('current_price', 0)
            if current_price == 0: 
                logger.warning(f"[{current_time_str}] {pos_data.get('name', stock_code)}의 실시간 현재가가 아직 수신되지 않았습니다. 전략 실행에 제한이 있을 수 있습니다.")
                continue 

            purchase_price = pos_data['purchase_price']
            
            pnl_pct = (current_price - purchase_price) / purchase_price * 100 if purchase_price != 0 else 0

            logger.info(f"🔍 {pos_data.get('name', stock_code)}({stock_code}) | 현재가: {current_price:,}원, 수익률: {pnl_pct:.2f}%, 보유일: {(datetime.now() - datetime.strptime(pos_data.get('buy_date', '1900-01-01'), '%Y-%m-%d')).days}일, 추적고점: {pos_data.get('trail_high', 0.0):,}원")

            action_taken = False 

            # 1. 손절 조건 검사 (최우선 순위)
            if pnl_pct <= STOP_LOSS_PCT:
                logger.warning(f"❌ 손절 조건 충족: {pos_data.get('name', stock_code)}({stock_code}) 수익률 {pnl_pct:.2f}% (기준: {STOP_LOSS_PCT:.2f}%)")
                order_quantity = pos_data['quantity']
                if order_quantity > 0:
                    result = trade_manager.place_order(stock_code, 2, order_quantity, 0, "03") 
                    if result["status"] == "success":
                        send_telegram_message(f"❌ 손절: {pos_data.get('name', stock_code)}({stock_code}) | 수익률: {pnl_pct:.2f}% | 수량: {order_quantity}주")
                        # 💡 매매 로그 기록
                        trade_logger.log_trade(
                            stock_code=stock_code, stock_name=pos_data.get('name'), trade_type="손절",
                            order_price=0, executed_price=current_price, quantity=order_quantity,
                            pnl_amount=(current_price - purchase_price) * order_quantity, pnl_pct=pnl_pct,
                            account_balance_after_trade=trade_manager.kiwoom_tr_request.request_account_info(trade_manager.account_number).get("예수금"), # 매매 후 잔고
                            strategy_name="StopLoss"
                        )
                        action_taken = True
                    else:
                        logger.error(f"🔴 손절 주문 실패: {pos_data.get('name', stock_code)}({stock_code}) {result.get('message', '알 수 없는 오류')}")
            
            if not action_taken:
                # 2. 50% 익절 조건 검사
                if not pos_data.get('half_exited', False) and pnl_pct >= TAKE_PROFIT_PCT:
                    logger.info(f"🎯 50% 익절 조건 충족: {pos_data.get('name', stock_code)}({stock_code}) 수익률 {pnl_pct:.2f}% (기준: {TAKE_PROFIT_PCT:.2f}%)")
                    half_qty = (pos_data['quantity'] // 2 // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE
                    
                    if half_qty > 0:
                        result = trade_manager.place_order(stock_code, 2, half_qty, 0, "03") 
                        if result["status"] == "success":
                            send_telegram_message(f"🎯 50% 익절: {pos_data.get('name', stock_code)}({stock_code}) | 수익률: {pnl_pct:.2f}% | 수량: {half_qty}주")
                            # 💡 매매 로그 기록
                            trade_logger.log_trade(
                                stock_code=stock_code, stock_name=pos_data.get('name'), trade_type="50%익절",
                                order_price=0, executed_price=current_price, quantity=half_qty,
                                pnl_amount=(current_price - purchase_price) * half_qty, pnl_pct=pnl_pct,
                                account_balance_after_trade=trade_manager.kiwoom_tr_request.request_account_info(trade_manager.account_number).get("예수금"),
                                strategy_name="TakeProfit50"
                            )
                            
                            monitor_positions.positions[stock_code]["half_exited"] = True
                            monitor_positions.positions[stock_code]["trail_high"] = current_price 
                            monitor_positions.save_positions() 
                            
                            logger.info(f"업데이트: {pos_data.get('name', stock_code)}({stock_code}) 남은 수량: {monitor_positions.positions[stock_code]['quantity']}주, 추적고점: {monitor_positions.positions[stock_code]['trail_high']:,}원")
                            action_taken = True
                        else:
                            logger.error(f"🔴 50% 익절 주문 실패: {pos_data.get('name', stock_code)}({stock_code}) {result.get('message', '알 수 없는 오류')}")
                
            if not action_taken and pos_data.get('half_exited', False):
                # 3. 트레일링 스탑 조건 검사 (50% 익절 후 잔여 수량에 대해 동작)
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
                            # 💡 매매 로그 기록
                            trade_logger.log_trade(
                                stock_code=stock_code, stock_name=pos_data.get('name'), trade_type="트레일링스탑",
                                order_price=0, executed_price=current_price, quantity=order_quantity,
                                pnl_amount=(current_price - purchase_price) * order_quantity, pnl_pct=pnl_on_exit,
                                account_balance_after_trade=trade_manager.kiwoom_tr_request.request_account_info(trade_manager.account_number).get("예수금"),
                                strategy_name="TrailingStop"
                            )
                            action_taken = True
                        else:
                            logger.error(f"🔴 트레일링 스탑 주문 실패: {pos_data.get('name', stock_code)}({stock_code}) {result.get('message', '알 수 없는 오류')}")
            
            if not action_taken:
                # 4. 최대 보유일 초과 조건 검사 (가장 낮은 순위)
                if pos_data.get("buy_date") and (datetime.now() - datetime.strptime(pos_data["buy_date"], "%Y-%m-%d")).days >= MAX_HOLD_DAYS:
                    logger.info(f"⌛ 보유일 초과 조건 충족: {pos_data.get('name', stock_code)}({stock_code}) 보유일 {(datetime.now() - datetime.strptime(pos_data['buy_date'], '%Y-%m-%d')).days}일 (기준: {MAX_HOLD_DAYS}일)")
                    order_quantity = pos_data['quantity']
                    if order_quantity > 0:
                        pnl_on_exit = (current_price - purchase_price) / purchase_price * 100 if purchase_price != 0 else 0
                        result = trade_manager.place_order(stock_code, 2, order_quantity, 0, "03") 
                        if result["status"] == "success":
                            send_telegram_message(f"⌛ 보유일 초과 청산: {pos_data.get('name', stock_code)}({stock_code}) | 수익률: {pnl_on_exit:.2f}% | 수량: {order_quantity}주")
                            # 💡 매매 로그 기록
                            trade_logger.log_trade(
                                stock_code=stock_code, stock_name=pos_data.get('name'), trade_type="보유일초과청산",
                                order_price=0, executed_price=current_price, quantity=order_quantity,
                                pnl_amount=(current_price - purchase_price) * order_quantity, pnl_pct=pnl_on_exit,
                                account_balance_after_trade=trade_manager.kiwoom_tr_request.request_account_info(trade_manager.account_number).get("예수금"),
                                strategy_name="MaxHoldDaysSell"
                            )
                            action_taken = True
                        else:
                            logger.error(f"🔴 보유일 초과 청산 주문 실패: {pos_data.get('name', stock_code)}({stock_code}) {result.get('message', '알 수 없는 오류')}")
            
        except Exception as e:
            logger.error(f"[{current_time_str}] {pos_data.get('name', stock_code)} 포지션 모니터링 중 오류 발생: {e}", exc_info=True)

    _handle_market_close_cleanup(monitor_positions, trade_manager, now)
    
    logger.info(f"[{current_time_str}] 포지션 모니터링 및 매매 전략 실행 종료.")

def _handle_market_close_cleanup(monitor_positions, trade_manager, now):
    current_time_str = get_current_time_str()
    # 장 마감 15:00 ~ 15:20 사이에 잔여 포지션 강제 청산 (시장가)
    if time(15, 0) <= now.time() < time(15, 20):
        logger.info(f"[{current_time_str}] 장 마감 전 포지션 정리 시간.")
        for stock_code, pos_data in monitor_positions.get_all_positions().items():
            if pos_data['quantity'] > 0: # 아직 보유 중인 종목만 해당
                logger.warning(f"[{current_time_str}] 장 마감 임박. {pos_data['name']}({stock_code}) 잔여 포지션 강제 청산 시도.")
                # 주문 실행: "2"는 매도, "03"은 시장가 (키움 API 주문 유형)
                result = trade_manager.place_order(stock_code, 2, pos_data['quantity'], 0, "03") 
                if result["status"] == "success":
                    send_telegram_message(f"🚨 장 마감 강제 청산: {pos_data['name']}({stock_code}) | 수량: {pos_data['quantity']}주")
                    # 💡 매매 로그 기록
                    trade_logger.log_trade(
                        stock_code=stock_code, stock_name=pos_data.get('name'), trade_type="장마감청산",
                        order_price=0, executed_price=pos_data.get('current_price', 0), quantity=pos_data['quantity'],
                        pnl_amount=(pos_data.get('current_price', 0) - pos_data.get('purchase_price',0)) * pos_data['quantity'], 
                        pnl_pct=(pos_data.get('current_price', 0) - pos_data.get('purchase_price',0)) / pos_data.get('purchase_price',1) * 100 if pos_data.get('purchase_price',1) != 0 else 0,
                        account_balance_after_trade=trade_manager.kiwoom_tr_request.request_account_info(trade_manager.account_number).get("예수금"),
                        strategy_name="MarketCloseSell"
                    )
                else:
                    logger.error(f"🔴 장 마감 강제 청산 주문 실패: {pos_data['name']}({stock_code}) {result.get('message', '알 수 없는 오류')}")

    elif now.time() >= time(15, 20) and now.time() < time(15, 30):
        logger.info(f"[{current_time_str}] 장 마감 동시호가 시간. 추가 매매/매도 불가.")
    elif now.time() >= time(15, 30) or now.time() < time(9, 0):
        logger.info(f"[{current_time_str}] 현재 매매 시간 아님. 대기 중...")
