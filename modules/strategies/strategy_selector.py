# modules/strategies/strategy_selector.py

import logging
import time
from modules.strategies.buy_strategy import check_buy_conditions

logger = logging.getLogger(__name__)

def select_top_candidates(
    kiwoom_helper,
    kiwoom_tr_request,
    monitor_positions,
    candidate_codes,
    top_n=2
):
    """
    실시간 조건검색 포착 종목 중 우선순위 점수가 높은 상위 종목 추출

    :param kiwoom_helper: PyKiwoom 헬퍼 객체
    :param kiwoom_tr_request: Kiwoom TR 요청 객체
    :param monitor_positions: 현재 포지션 객체
    :param candidate_codes: 조건검색으로 포착된 종목 코드 리스트
    :param top_n: 상위 몇 개의 종목을 추출할지
    :return: 우선순위 상위 종목 리스트 (dict 리스트)
    """
    results = []
    holding_codes = set(monitor_positions.get_all_positions().keys())

    for code in candidate_codes:
        if code in holding_codes:
            logger.debug(f"보유 종목 제외: {code}")
            continue

        stock_name = kiwoom_helper.get_stock_name(code)
        if stock_name == "Unknown":
            logger.debug(f"종목명 확인 실패: {code}")
            continue

        try:
            result = check_buy_conditions(
                kiwoom_helper, kiwoom_tr_request, code, stock_name
            )
            if result:
                results.append(result)
                logger.info(f"후보 등록: {stock_name}({code}), 점수: {result['score']:.2f}")
        except Exception as e:
            logger.error(f"{code}({stock_name}) 조건 평가 중 오류: {e}")

        time.sleep(0.2)  # API 호출 제한 회피

    if not results:
        logger.info("조건 만족 후보 없음")
        return []

    sorted_results = sorted(results, key=lambda x: x["score"], reverse=True)
    return sorted_results[:top_n]
