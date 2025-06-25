# modules/strategies/monitor_positions_strategy.py

import logging
from datetime import datetime, time, timedelta
import time as time_module

# 필요한 모듈 임포트
from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
# 💡 config에서 전략 관련 상수 임포트 (이름 일치 확인)
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

    # 💡 Kiwoom API 연결 상태 확인
    if not monitor_positions.kiwoom_helper.connected_state == 0: # 0: 연결 성공
        logger.warning(f"[{current_time_str}] Kiwoom API 연결 상태 불량. 포지션 모니터링 건너뜀.")
        # API 연결이 끊겼더라도 장 마감 정리 로직은 시도해야 할 수 있음 (예: 프로그램 재시작 시점)
        _handle_market_close_cleanup(monitor_positions, trade_manager, now)
        return

    # 모든 현재 보유 포지션을 가져옵니다.
    current_positions = monitor_positions.get_all_positions()

    if not current_positions:
        logger.info(f"[{current_time_str}] 현재 보유 중인 포지션이 없습니다.")
        _handle_market_close_cleanup(monitor_positions, trade_manager, now) # 포지션 없어도 정리 로직은 확인
        return

    # 💡 매매 시간 (09:05 ~ 15:20)에만 매도 전략 실행
    if time(9, 5) <= now.time() < time(15, 20): 
        for stock_code, pos_data in current_positions.items():
            try:
                if pos_data['quantity'] <= 0: # 이미 매도 완료된 포지션은 건너뜀
                    logger.debug(f"[{current_time_str}] {pos_data.get('name', stock_code)} - 수량 0 또는 음수. 모니터링 건너뜀.")
                    # 실제 수량이 0인데 buy_time이 None이 아닌 경우는 완전 매도 후 정리 안된 경우
                    if pos_data.get('buy_time') is not None and pos_data['quantity'] == 0:
                         monitor_positions.remove_position(stock_code)
                    continue

                # 💡 실시간 현재가 가져오기 (KiwoomQueryHelper의 real_time_data 활용)
                current_price = monitor_positions.kiwoom_helper.real_time_data.get(stock_code, {}).get('current_price', 0)
                if current_price == 0:
                    logger.warning(f"⚠️ {pos_data['name']}({stock_code}) 실시간 현재가 정보 없음. 매도 전략 건너뜀.")
                    continue

                purchase_price = pos_data['purchase_price']
                quantity = pos_data['quantity']
                name = pos_data['name']
                buy_time_str = pos_data.get('buy_time')
                half_exited = pos_data.get('half_exited', False) # 1차 익절 여부
                trail_high = pos_data.get('trail_high', current_price) # 트레일링 고점 (초기값은 현재가)

                # 매수가 0인 경우 방지
                if purchase_price == 0:
                    logger.warning(f"⚠️ {name}({stock_code}) 매입가 0. 매도 전략 실행 불가.")
                    continue

                pnl_pct = ((current_price - purchase_price) / purchase_price) * 100

                # 💡 트레일링 고점 업데이트 (현재가가 기록된 최고가보다 높으면 갱신)
                if current_price > trail_high:
                    pos_data['trail_high'] = current_price
                    monitor_positions.save_positions() # 업데이트된 트레일링 하이 저장
                    logger.debug(f"DEBUG: {name}({stock_code}) 트레일링 고점 갱신: {trail_high:,} -> {current_price:,}원")
                
                # 1. 1차 익절 (매수가 대비 +2.0% 상승 시, 보유 수량의 50% 분할 익절)
                if pnl_pct >= TAKE_PROFIT_PCT_1ST and quantity > 0 and not half_exited:
                    sell_quantity = quantity // 2 # 50% 분할 익절
                    if sell_quantity > 0:
                        logger.info(f"✅ {name}({stock_code}) 1차 익절 조건 달성 (+{pnl_pct:.2f}%). 50% 분할 매도 시도.")
                        send_telegram_message(f"✅ 1차 익절: {name}({stock_code}) +{pnl_pct:.2f}% (매수량 50% 매도)")
                        trade_manager.place_order(stock_code, 2, sell_quantity, 0, "03") # 2: 매도, 03: 시장가
                        pos_data['half_exited'] = True # 1차 익절 완료 플래그 설정
                        monitor_positions.save_positions() # 플래그 저장
                        continue 

                # 2. 2차 익절 (트레일링 스탑): 1차 익절 후 남은 수량에 대해, 매수 후 기록된 최고가 대비 -0.8% 하락 시 전량 매도
                # 중요한 것은 현재 잔여 수량 (quantity)이 있어야 하고, 최고가 대비 하락폭이 기준 이상이어야 함.
                drop_from_high_pct = ((trail_high - current_price) / trail_high) * 100 if trail_high != 0 else 0.0
                if drop_from_high_pct >= TRAIL_STOP_PCT_2ND and quantity > 0:
                    logger.info(f"✅ {name}({stock_code}) 2차 익절(트레일링 스탑) 조건 달성. 최고가 대비 -{drop_from_high_pct:.2f}%. 전량 매도 시도.")
                    send_telegram_message(f"✅ 2차 익절(트레일링 스탑): {name}({stock_code}) 최고가 대비 -{drop_from_high_pct:.2f}% (전량 매도)")
                    trade_manager.place_order(stock_code, 2, quantity, 0, "03") # 전량 매도
                    continue

                # 3. 손절 (매수가 대비 -1.2% 하락 시 전량 손절)
                if pnl_pct <= STOP_LOSS_PCT_ABS and quantity > 0:
                    logger.warning(f"🚨 {name}({stock_code}) 손절 조건 달성 ({pnl_pct:.2f}%). 전량 손절 시도.")
                    send_telegram_message(f"🚨 손절: {name}({stock_code}) {pnl_pct:.2f}% (전량 매도)")
                    trade_manager.place_order(stock_code, 2, quantity, 0, "03") # 전량 매도
                    continue

                # 4. 시간 손절 (매수 후 TIME_STOP_MINUTES 분 이내에 어떤 조건도 충족되지 않을 경우 전량 매도)
                if buy_time_str:
                    buy_time_dt = datetime.strptime(buy_time_str, "%Y-%m-%d %H:%M:%S")
                    time_since_buy = now - buy_time_dt
                    
                    if time_since_buy.total_seconds() >= TIME_STOP_MINUTES * 60 and quantity > 0:
                        # 1차 익절을 하지 않았고, 아직 익절/손절 범위에 도달하지 않은 애매한 포지션일 때만 시간 손절
                        if not half_exited and (STOP_LOSS_PCT_ABS < pnl_pct < TAKE_PROFIT_PCT_1ST):
                            logger.warning(f"🚨 {name}({stock_code}) 시간 손절 조건 달성 ({TIME_STOP_MINUTES}분 경과). 전량 매도 시도.")
                            send_telegram_message(f"🚨 시간 손절: {name}({stock_code}) {TIME_STOP_MINUTES}분 경과 (전량 매도)")
                            trade_manager.place_order(stock_code, 2, quantity, 0, "03") # 전량 매도
                            continue

                logger.debug(f"[{current_time_str}] {name}({stock_code}) 현재가: {current_price:,}원, 매입가: {purchase_price:,}원, 수익률: {pnl_pct:.2f}%")

            except Exception as e:
                logger.error(f"[{current_time_str}] {pos_data.get('name', stock_code)} 포지션 모니터링 중 오류 발생: {e}", exc_info=True)
        
    # 장 마감 시간 정리 로직 (모든 포지션을 순회한 후에 실행)
    _handle_market_close_cleanup(monitor_positions, trade_manager, now)
    
    logger.info(f"[{current_time_str}] 포지션 모니터링 및 매매 전략 실행 종료.")


def _handle_market_close_cleanup(monitor_positions, trade_manager, now):
    """
    장 마감 임박 시 잔여 포지션을 정리하는 로직.
    """
    current_time_str = get_current_time_str()
    # 장 마감 직전 정리 시간 (15:00 ~ 15:20)
    # 15:20 부터는 동시호가이므로, 15:20 이전까지는 시장가 매도가 유효함
    if time(15, 0) <= now.time() < time(15, 20):
        logger.info(f"[{current_time_str}] 장 마감 전 포지션 정리 시간.")
        for stock_code, pos_data in monitor_positions.get_all_positions().items():
            if pos_data['quantity'] > 0: # 아직 보유 중인 포지션이 있다면
                logger.warning(f"[{current_time_str}] 장 마감 임박. {pos_data['name']}({stock_code}) 잔여 포지션 강제 청산 시도.")
                send_telegram_message(f"🚨 장 마감 정리: {pos_data['name']}({stock_code}) 전량 시장가 매도 주문.")
                trade_manager.place_order(stock_code, 2, pos_data['quantity'], 0, "03") # 2: 매도, 03: 시장가

    # 장 마감 후 또는 개장 전 시간대는 매매 활동이 없으므로 정보성 로그만 남김
    elif now.time() >= time(15, 20) and now.time() < time(15, 30): # 장 마감 동시호가 시간
        logger.info(f"[{current_time_str}] 장 마감 동시호가 시간. 추가 매매/매도 불가.")
    elif now.time() >= time(15, 30) or now.time() < time(9, 0): # 장 종료 후/개장 전
        logger.info(f"[{current_time_str}] 현재 매매 시간 아님. 대기 중...")

