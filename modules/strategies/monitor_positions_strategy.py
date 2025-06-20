# modules/Kiwoom/monitor_positions_strategy.py

from datetime import datetime, timedelta, time
from modules.common.utils import get_current_time_str
from modules.common.config import (
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_STOP_PCT, MAX_HOLD_DAYS, # MAX_HOLD_DAYS 사용 예정
)
from modules.notify import send_telegram_message
from modules.trade_logger import log_trade


def monitor_positions_strategy(monitor_positions, trade_manager):
    positions = monitor_positions.get_current_positions()
    now = datetime.now()

    # for 루프를 돌면서 pos 객체를 직접 수정하므로, 반복 중 딕셔너리 크기 변경 오류를 피하기 위해
    # 현재 포지션 리스트의 복사본을 순회하는 것이 안전합니다.
    for ticker, pos in list(positions.items()): # .items()로 딕셔너리 순회, list()로 복사본 생성
        # pos 딕셔너리에서 직접 필요한 정보를 가져옵니다.
        # 'quantity'는 현재 보유 수량으로, _partial_exit_position에서 업데이트됩니다.
        
        name = pos["name"]
        buy_price = float(pos["buy_price"])
        
        # NOTE: 여기서는 'quantity' 변수를 사용하지 않고, 항상 pos["quantity"]를 직접 참조합니다.
        # 이렇게 하면 _partial_exit_position에서 pos["quantity"]가 업데이트될 때,
        # 이후의 모든 조건 검사에서 최신 수량을 참조하게 됩니다.
        
        buy_date = datetime.strptime(pos["buy_date"], "%Y-%m-%d")
        half_exited = pos.get("half_exited", False)
        trail_high = float(pos.get("trail_high", buy_price))
        buy_time = datetime.strptime(pos.get("buy_time", now.strftime("%Y-%m-%d %H:%M:%S")), "%Y-%m-%d %H:%M:%S")
        hold_minutes = (now - buy_time).total_seconds() / 60
        hold_days = (now - buy_date).days

        # 현재가
        current_price = trade_manager.get_current_price(ticker)
        if current_price <= 0:
            continue

        pnl_pct = ((current_price - buy_price) / buy_price) * 100

        # 최고가 갱신
        if current_price > trail_high:
            pos["trail_high"] = current_price
            # trail_high 변수도 업데이트하여 즉시 사용 가능하도록
            trail_high = current_price 

        # --- 매도 조건 우선순위 (보통 손절이 가장 먼저) ---

        # 1. 손절 조건: -1.2% (현재 보유 수량 전체 매도)
        if pnl_pct <= STOP_LOSS_PCT:
            reason = f"❌ 손절 실행: {name} ({pnl_pct:.2f}%)"
            _exit_position(ticker, pos["quantity"], current_price, reason, trade_manager, monitor_positions, pos)
            continue # 현재 포지션에 대한 다음 조건 검사 스킵

        # 2. 1차 익절: +2% 절반 익절
        if pnl_pct >= TAKE_PROFIT_PCT and not half_exited:
            # 남은 수량이 1개일 경우 0이 되는 것을 방지하고 1개라도 팔도록 수정
            half_qty = pos["quantity"] // 2 
            if half_qty == 0 and pos["quantity"] > 0: # 수량이 1개 남아있을 때 절반 매도 요청 시
                half_qty = pos["quantity"] # 남은 1개 전부 매도
            elif half_qty == 0: # 이미 수량이 0인 경우 (예: 버그나 외부 요인으로 이미 소량 남았을 때 0)
                continue # 매도할 수량이 없으므로 다음 조건으로 넘어감 (실제로는 여기서 remove_position 필요할 수도)

            reason = f"✅ 1차 익절: {name} +{pnl_pct:.2f}%"
            _partial_exit_position(ticker, half_qty, current_price, reason, trade_manager, monitor_positions, pos)
            continue # 현재 포지션에 대한 다음 조건 검사 스킵

        # 3. 2차 익절: 최고가 대비 -0.8% (잔여 수량 전체 매도)
        # half_exited가 True일 때만 발동
        if half_exited and pos["quantity"] > 0 and current_price <= trail_high * (1 - TRAIL_STOP_PCT / 100):
            reason = f"📉 트레일링 스탑: {name} 고점대비 하락"
            _exit_position(ticker, pos["quantity"], current_price, reason, trade_manager, monitor_positions, pos)
            continue # 현재 포지션에 대한 다음 조건 검사 스킵

        # 4. 시간 손절: 15분 경과 (잔여 수량 전체 매도)
        # 1차 익절을 하지 않았거나, 1차 익절 후에도 너무 오래 보유 중인 경우
        if hold_minutes >= 15 and pos["quantity"] > 0 and not half_exited: # 1차 익절 안 된 상태에서만 15분 조건
            reason = f"⏰ 15분 경과 시간 손절: {name}"
            _exit_position(ticker, pos["quantity"], current_price, reason, trade_manager, monitor_positions, pos)
            continue # 현재 포지션에 대한 다음 조건 검사 스킵
        
        # 5. 최대 보유 일수 초과 손절 (MAX_HOLD_DAYS 활용 - 단타에서는 보통 해당 안됨)
        # 이 조건은 스윙/장기 매매에서 주로 사용되나, 설정되어 있으므로 추가
        if MAX_HOLD_DAYS is not None and hold_days >= MAX_HOLD_DAYS and pos["quantity"] > 0:
            reason = f"🗓️ {MAX_HOLD_DAYS}일 초과 시간 손절: {name}"
            _exit_position(ticker, pos["quantity"], current_price, reason, trade_manager, monitor_positions, pos)
            continue # 현재 포지션에 대한 다음 조건 검사 스킵


    # --- 장 마감 전 정리 (모든 포지션을 대상으로 루프 밖에서 처리하거나,
    #                   매도 로직에서 `remove_position`이 호출된 후 남은 것만 처리되도록 해야 함) ---
    # NOTE: 이 부분은 for 루프 안에 있으면 문제가 생길 수 있습니다.
    #       for 루프는 현재 포지션들을 순회하며 각 포지션에 대한 조건을 확인합니다.
    #       장 마감 정리 로직은 모든 포지션을 한번에 처리하는 것이 일반적입니다.
    #       따라서 이 코드는 for 루프 밖으로 빼내어 별도로 호출하는 것이 좋습니다.
    #       main.py (또는 포지션 관리 루프가 있는 곳)에서 이 전략 함수를 호출한 후에
    #       장 마감 정리를 별도의 함수로 호출하거나, 아래와 같이 for 루프 외부에서 한 번만 확인하도록 합니다.
    
    # 장 마감 전 정리는 모든 개별 포지션 조건 검사 후, 루프 밖에서 한 번 더 최종 확인하는 것이 좋습니다.
    # 이 부분은 monitor_positions_strategy가 호출되는 main 루프에서 now.time() >= time(15, 20)을
    # 한 번만 검사하여 전체 잔여 포지션을 정리하는 것이 더 효율적입니다.
    # 하지만 현재 구조를 유지하려면, 'for pos in positions' 루프가 한 번 돌 때마다
    # 이미 매도된 포지션이 또 다시 정리되지 않도록 주의해야 합니다.
    # remove_position이 제대로 동작한다면 문제 없습니다.
    
    # 현재 코드는 for 루프 안에 있으므로, 각 포지션에 대해 개별적으로 조건을 체크합니다.
    # 이는 기술적으로 오류는 아니나, 전체 포지션의 잔여 수량이 0이 아닐 때만 매도하도록 pos["quantity"] > 0 조건을 명시적으로 추가했습니다.
    if now.time() >= time(15, 20):
        # 현재 루프에서 처리되지 않고 남아있는 포지션들에 대해 장 마감 정리
        # (이미 위에서 매도된 종목은 remove_position에 의해 positions에서 제거되었을 것임)
        remaining_positions = monitor_positions.get_current_positions() # 최신 상태 다시 가져오기
        for ticker, pos in list(remaining_positions.items()):
            if pos["quantity"] > 0:
                current_price = trade_manager.get_current_price(ticker)
                if current_price <= 0:
                    continue
                reason = f"🔚 장 마감 정리 매도: {pos['name']}"
                _exit_position(ticker, pos["quantity"], current_price, reason, trade_manager, monitor_positions, pos)


def _exit_position(ticker, quantity, price, reason, trade_manager, monitor_positions, pos):
    """
    모든 수량을 매도하고 포지션을 제거합니다.
    :param quantity: 현재 매도할 수량 (pos["quantity"]로 받아와야 함)
    """
    # 매도할 수량이 0보다 커야만 주문을 시도합니다.
    if quantity <= 0:
        send_telegram_message(f"❗ 매도 요청 수량 오류: {ticker} - 수량이 0 이하입니다.")
        monitor_positions.remove_position(ticker) # 수량이 0이므로 포지션 제거
        return

    try:
        # 매도 주문 전송 (시장가 '03'으로 가정)
        trade_manager.place_order(ticker, 2, quantity, price, "03")
        
        # 로그 기록 및 텔레그램 알림
        # PNL 계산 시 초기 buy_price와 매도 current_price 사용
        pnl = ((price - pos["buy_price"]) / pos["buy_price"]) * 100
        log_trade(ticker, pos["name"], price, quantity, "SELL_ALL", pnl=pnl)
        send_telegram_message(f"{reason}\n💰 {quantity}주 @ {price:,}원 매도 완료")
        
        # 포지션 제거 (매도 완료 후)
        monitor_positions.remove_position(ticker)
    except Exception as e:
        send_telegram_message(f"❗ 매도 실패: {ticker} - {e}")


def _partial_exit_position(ticker, quantity, price, reason, trade_manager, monitor_positions, pos):
    """
    일부 수량을 매도하고 포지션 정보를 업데이트합니다.
    :param quantity: 매도할 부분 수량
    """
    # 부분 매도할 수량이 0보다 커야만 주문을 시도합니다.
    if quantity <= 0:
        send_telegram_message(f"❗ 부분 매도 요청 수량 오류: {ticker} - 수량이 0 이하입니다.")
        return

    try:
        # 매도 주문 전송 (시장가 '03'으로 가정)
        trade_manager.place_order(ticker, 2, quantity, price, "03")
        
        # 로그 기록 및 텔레그램 알림
        pnl = ((price - pos["buy_price"]) / pos["buy_price"]) * 100
        log_trade(ticker, pos["name"], price, quantity, "SELL_HALF", pnl=pnl)
        send_telegram_message(f"{reason}\n📤 {quantity}주 익절 완료")
        
        # 포지션 객체의 잔여 수량 업데이트
        pos["quantity"] -= quantity
        pos["half_exited"] = True # 절반 익절 플래그 설정
        
        # 변경된 포지션 정보 저장 (monitor_positions 내부의 데이터 저장 함수 호출)
        monitor_positions.save_positions() 
    except Exception as e:
        send_telegram_message(f"❗ 절반 매도 실패: {ticker} - {e}")