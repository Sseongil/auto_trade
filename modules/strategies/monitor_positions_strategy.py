# modules/strategies/monitor_positions_strategy.py

import logging
from datetime import datetime, time

from modules.strategies.strategy_selector import select_top_candidates
from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)


def monitor_positions_strategy(monitor_positions, trade_manager):
    """
    메인 루프에서 주기적으로 실행되는 전략 함수
    보유 포지션 모니터링 + 전략 진입 신호 탐색
    """
    now = datetime.now().time()
    time_str = get_current_time_str()

    # 전략 수행 시간대 조건 (09:05 ~ 14:50)
    if not (time(9, 5) <= now < time(14, 50)):
        logger.info(f"[{time_str}] 전략 수행 시간이 아님. 스킵")
        return

    # API 연결 여부 확인
    if trade_manager.kiwoom_helper.connected_state != 0:
        logger.warning(f"[{time_str}] Kiwoom API 연결 상태 불량. 전략 실행 스킵")
        return

    logger.info(f"[{time_str}] 포지션 모니터링 및 전략 평가 시작")

    # 1️⃣ 실시간 조건검색 감시 기반 종목 리스트 추출
    condition_hit_codes = trade_manager.kiwoom_helper.get_real_condition_hits()
    if not condition_hit_codes:
        logger.info(f"[{time_str}] 조건검색 포착 종목 없음")
        return

    logger.info(f"[{time_str}] 조건검색 포착 종목: {condition_hit_codes}")

    # 2️⃣ 전략 점수화 + 우선순위 추출
    top_candidates = select_top_candidates(
        kiwoom_helper=trade_manager.kiwoom_helper,
        kiwoom_tr_request=trade_manager.kiwoom_tr_request,
        monitor_positions=monitor_positions,
        candidate_codes=condition_hit_codes,
        top_n=1
    )

    if not top_candidates:
        logger.info(f"[{time_str}] 전략 조건 충족 종목 없음")
        return

    best_pick = top_candidates[0]
    stock_code = best_pick["stock_code"]
    stock_name = best_pick["stock_name"]
    current_price = best_pick["current_price"]

    # 3️⃣ 포지션 중복 방지
    if stock_code in monitor_positions.get_all_positions():
        logger.info(f"[{time_str}] {stock_name}({stock_code}) 이미 보유 중. 진입 생략")
        return

    # 4️⃣ 매수 수량 계산
    account_info = trade_manager.kiwoom_tr_request.request_account_info(trade_manager.account_number)
    cash = account_info.get("예수금", 0)
    if cash <= 0:
        logger.warning(f"❌ 예수금 부족. 매수 불가")
        return

    qty = max(1, int((cash * 0.5) // current_price))  # 종목당 50% 비중

    logger.info(f"🚀 전략 진입: {stock_name}({stock_code}), 수량: {qty}")
    send_telegram_message(f"🚀 전략 진입: {stock_name}({stock_code})\n예상 수량: {qty}, 점수: {best_pick['score']:.2f}")

    # 5️⃣ 주문 실행
    result = trade_manager.place_order(
        stock_code=stock_code,
        order_type=1,
        quantity=qty,
        price=0,
        order_division="03",  # 시장가
        screen_no="1811"
    )

    if result["status"] == "success":
        logger.info(f"✅ 매수 주문 성공: {stock_name}({stock_code})")
    else:
        logger.error(f"❌ 매수 주문 실패: {stock_name}({stock_code}) - {result['message']}")
        send_telegram_message(f"❌ 매수 실패: {stock_name} - {result['message']}")
