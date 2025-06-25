# modules/strategies/buy_strategy.py

import logging
from datetime import datetime, timedelta
import pandas as pd
import time 

from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
from modules.trade_logger import TradeLogger 
from modules.common.config import (
    MIN_GAP_UP_PCT, MIN_CURRENT_PRICE_VS_OPEN_PCT, MIN_VOLUME_INCREASE_RATIO,
    MIN_TRADING_VALUE_BILLION, MIN_CHEGYUL_GANGDO, MIN_BUY_SELL_RATIO,
    MIN_PRICE, MAX_PRICE, MIN_MARKET_CAP_BILLION, MAX_MARKET_CAP_BILLION,
    MAX_CURRENT_DAILY_CHANGE_PCT, DEFAULT_LOT_SIZE
)

logger = logging.getLogger(__name__)
trade_logger = TradeLogger() 

def get_news_score(stock_code, stock_name):
    """
    뉴스/공시 점수를 반환하는 임시 함수.
    실제 구현에서는 news_crawler 모듈을 통해 최신 뉴스/공시를 분석합니다.
    """
    logger.debug(f"뉴스/공시 점수 계산 (현재 더미): {stock_name}({stock_code})")
    return 15 

def check_buy_conditions(kiwoom_helper, kiwoom_tr_request, stock_code, stock_name):
    """
    주어진 종목이 매수 조건을 충족하는지 확인하고, 점수를 반환합니다.
    """
    logger.info(f"🔍 {stock_name}({stock_code}) 매수 조건 검사 시작...")
    
    real_time_info = kiwoom_helper.real_time_data.get(stock_code, {})
    current_price = real_time_info.get('current_price', 0)
    trading_volume = real_time_info.get('trading_volume', 0)
    chegyul_gangdo = real_time_info.get('chegyul_gangdo', 0.0)
    total_buy_cvol = real_time_info.get('total_buy_cvol', 0)
    total_sell_cvol = real_time_info.get('total_sell_cvol', 0)

    if current_price == 0:
        logger.warning(f"⚠️ {stock_name}({stock_code}) 실시간 현재가 정보 없음. 조건 검사 불가.")
        return None

    today_str = datetime.today().strftime("%Y%m%d")
    
    time.sleep(0.05) 

    daily_ohlcv_data = kiwoom_tr_request.request_daily_ohlcv_data(stock_code, today_str, sPrevNext="0")
    if not daily_ohlcv_data or daily_ohlcv_data.get("error"):
        logger.warning(f"⚠️ {stock_name}({stock_code}) 일봉 데이터 조회 실패: {daily_ohlcv_data.get('error', '응답 없음')}")
        return None
    
    df_daily = pd.DataFrame(daily_ohlcv_data['data'])
    if df_daily.empty:
        logger.warning(f"⚠️ {stock_name}({stock_code}) 일봉 데이터 부족. 조건 검사 불가.")
        return None

    df_daily['날짜'] = pd.to_datetime(df_daily['날짜'])
    df_daily = df_daily.sort_values(by='날짜', ascending=True).reset_index(drop=True)
    
    time.sleep(0.05) 

    five_min_ohlcv_data = kiwoom_tr_request.request_five_minute_ohlcv_data(stock_code, "5", sPrevNext="0") 
    if not five_min_ohlcv_data or five_min_ohlcv_data.get("error"):
        logger.warning(f"⚠️ {stock_name}({stock_code}) 5분봉 데이터 조회 실패: {five_min_ohlcv_data.get('error', '응답 없음')}")
        return None

    df_5min = pd.DataFrame(five_min_ohlcv_data['data'])
    if df_5min.empty:
        logger.warning(f"⚠️ {stock_name}({stock_code}) 5분봉 데이터 부족. 조건 검사 불가.")
        return None

    time.sleep(0.05) 

    stock_info = kiwoom_tr_request.request_stock_basic_info(stock_code)
    if not stock_info or stock_info.get("error"):
        logger.warning(f"⚠️ {stock_name}({stock_code}) 기본 정보 조회 실패: {stock_info.get('error', '응답 없음')}")
        return None
    
    market_cap_billion = stock_info.get('시가총액', 0) / 1_0000_0000 

    if len(df_daily) < 2: 
        logger.debug(f"❌ {stock_name}({stock_code}) 일봉 데이터 부족 (2일 미만). 갭 상승 조건 건너뜀.")
        return None 
    
    today_open = df_daily.iloc[-1]['시가']
    prev_close = df_daily.iloc[-2]['현재가'] 

    if prev_close == 0:
        logger.warning(f"⚠️ {stock_name}({stock_code}) 전일 종가 0. 갭 상승 조건 검사 불가.")
        return None

    gap_up_pct = ((today_open - prev_close) / prev_close) * 100
    if gap_up_pct < MIN_GAP_UP_PCT:
        logger.debug(f"❌ {stock_name}({stock_code}) 갭 상승 조건 불충족: {gap_up_pct:.2f}% (기준: {MIN_GAP_UP_PCT}%)")
        return None

    current_vs_open_pct = ((current_price - today_open) / today_open) * 100 if today_open != 0 else 0
    if current_vs_open_pct < MIN_CURRENT_PRICE_VS_OPEN_PCT:
        logger.debug(f"❌ {stock_name}({stock_code}) 현재가 대비 시가 상승 조건 불충족: {current_vs_open_pct:.2f}% (기준: {MIN_CURRENT_PRICE_VS_OPEN_PCT}%)")
        return None

    if len(df_daily) < 6: 
        logger.debug(f"❌ {stock_name}({stock_code}) 일봉 데이터 부족 (6일 미만). 거래량 증가 조건 건너뜀.")
        return None
        
    last_5_days_volume = df_daily['거래량'].iloc[-6:-1].astype(float) 
    if last_5_days_volume.empty or last_5_days_volume.mean() <= 0: 
        avg_5_day_volume = 1 
    else:
        avg_5_day_volume = last_5_days_volume.mean()

    volume_increase_ratio = (trading_volume / avg_5_day_volume * 100) if avg_5_day_volume != 0 else float('inf')
    if volume_increase_ratio < MIN_VOLUME_INCREASE_RATIO:
        logger.debug(f"❌ {stock_name}({stock_code}) 거래량 증가 조건 불충족: {volume_increase_ratio:.2f}% (기준: {MIN_VOLUME_INCREASE_RATIO}%)")
        return None

    today_trading_value_billion = (current_price * trading_volume) / 1_0000_0000 
    if today_trading_value_billion < MIN_TRADING_VALUE_BILLION:
        logger.debug(f"❌ {stock_name}({stock_code}) 거래대금 조건 불충족: {today_trading_value_billion:.2f}억 원 (기준: {MIN_TRADING_VALUE_BILLION}억 원)")
        return None

    df_daily['MA5'] = df_daily['현재가'].rolling(window=5).mean()
    df_daily['MA20'] = df_daily['현재가'].rolling(window=20).mean()
    df_daily['MA60'] = df_daily['현재가'].rolling(window=60).mean()

    if len(df_daily) < 60:
        logger.debug(f"❌ {stock_name}({stock_code}) 일봉 MA60 계산에 필요한 데이터 부족 (60일 미만).")
        return None

    ma5_daily = df_daily['MA5'].iloc[-1]
    ma20_daily = df_daily['MA20'].iloc[-1]
    ma60_daily = df_daily['MA60'].iloc[-1]
    
    daily_ma_golden_cross = False
    if len(df_daily) >= 2: 
        ma5_prev = df_daily['MA5'].iloc[-2]
        ma20_prev = df_daily['MA20'].iloc[-2]
        if ma5_prev is not None and ma20_prev is not None and ma5_prev < ma20_prev and ma5_daily >= ma20_daily:
            daily_ma_golden_cross = True

    daily_ma_strong_alignment = (ma5_daily > ma20_daily > ma60_daily)
    
    if not (daily_ma_golden_cross or daily_ma_strong_alignment):
        logger.debug(f"❌ {stock_name}({stock_code}) 일봉 이평선 정배열/골든크로스 조건 불충족.")
        return None

    df_5min['MA5'] = df_5min['현재가'].rolling(window=5).mean()
    df_5min['MA20'] = df_5min['현재가'].rolling(window=20).mean()

    if len(df_5min) < 20:
        logger.debug(f"❌ {stock_name}({stock_code}) 5분봉 MA20 계산에 필요한 데이터 부족 (20개 봉 미만).")
        return None

    ma5_5min = df_5min['MA5'].iloc[-1]
    ma20_5min = df_5min['MA20'].iloc[-1]

    if not (current_price > ma5_5min and ma5_5min > ma20_5min):
        logger.debug(f"❌ {stock_name}({stock_code}) 5분봉 이평선 조건 불충족: 현재가({current_price}) > MA5({ma5_5min:.2f}) > MA20({ma20_5min:.2f})")
        return None

    if chegyul_gangdo < MIN_CHEGYUL_GANGDO:
        logger.debug(f"❌ {stock_name}({stock_code}) 체결강도 조건 불충족: {chegyul_gangdo:.2f}% (기준: {MIN_CHEGYUL_GANGDO}%)")
        return None
    
    if total_sell_cvol == 0:
        buy_sell_ratio = float('inf') 
    else:
        buy_sell_ratio = total_buy_cvol / total_sell_cvol

    if buy_sell_ratio < MIN_BUY_SELL_RATIO:
        logger.debug(f"❌ {stock_name}({stock_code}) 매수/매도 잔량 비율 조건 불충족: {buy_sell_ratio:.2f}배 (기준: {MIN_BUY_SELL_RATIO}배)")
        return None

    if not (MIN_PRICE <= current_price <= MAX_PRICE):
        logger.debug(f"❌ {stock_name}({stock_code}) 주가 범위 조건 불충족: {current_price:,}원 (기준: {MIN_PRICE}~{MAX_PRICE}원)")
        return None

    if not (MIN_MARKET_CAP_BILLION <= market_cap_billion <= MAX_MARKET_CAP_BILLION):
        logger.debug(f"❌ {stock_name}({stock_code}) 시가총액 범위 조건 불충족: {market_cap_billion:.2f}억 원 (기준: {MIN_MARKET_CAP_BILLION}~{MAX_MARKET_CAP_BILLION}억 원)")
        return None

    if len(df_daily) < 2:
        logger.debug(f"❌ {stock_name}({stock_code}) 전일 종가 데이터 부족. 당일 등락률 조건 건너뜀.")
        return None
    
    prev_day_close = df_daily.iloc[-2]['현재가']
    current_daily_change_pct = ((current_price - prev_day_close) / prev_day_close) * 100 if prev_day_close != 0 else 0
    
    if current_daily_change_pct > MAX_CURRENT_DAILY_CHANGE_PCT:
        logger.debug(f"❌ {stock_name}({stock_code}) 당일 등락률 조건 불충족: {current_daily_change_pct:.2f}% (기준: {MAX_CURRENT_DAILY_CHANGE_PCT}%)")
        return None

    score = calculate_score(
        stock_code, stock_name,
        gap_up_pct, current_vs_open_pct,
        volume_increase_ratio, today_trading_value_billion,
        chegyul_gangdo, buy_sell_ratio,
        daily_ma_strong_alignment, (current_price > ma5_5min and ma5_5min > ma20_5min)
    )

    logger.info(f"✅ {stock_name}({stock_code}) 모든 매수 조건 충족! (점수: {score:.2f})")
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "current_price": current_price,
        "score": score,
        "gap_up_pct": gap_up_pct,
        "current_vs_open_pct": current_vs_open_pct,
        "volume_increase_ratio": volume_increase_ratio,
        "trading_value_billion": today_trading_value_billion,
        "chegyul_gangdo": chegyul_gangdo,
        "buy_sell_ratio": buy_sell_ratio
    }

def calculate_score(
    stock_code, stock_name,
    gap_up_pct, current_vs_open_pct,
    volume_increase_ratio, trading_value_billion,
    chegyul_gangdo, buy_sell_ratio,
    daily_ma_strong_alignment, five_min_ma_alignment
):
    """
    각 후보 종목의 우선순위 점수를 계산합니다.
    """
    news_score = get_news_score(stock_code, stock_name) 
    
    volume_value_score = 0
    volume_value_score += min(10, (volume_increase_ratio / MIN_VOLUME_INCREASE_RATIO) * 5) 
    volume_value_score += min(10, (trading_value_billion / MIN_TRADING_VALUE_BILLION) * 5) 
    volume_value_score = min(20, volume_value_score) 

    chegyul_score = min(5, (chegyul_gangdo / MIN_CHEGYUL_GANGDO) * 5) 

    buy_pressure_score = min(5, (buy_sell_ratio / MIN_BUY_SELL_RATIO) * 5) 

    ma_score = 0
    if daily_ma_strong_alignment:
        ma_score += 2
    if five_min_ma_alignment:
        ma_score += 1
    ma_score = min(3, ma_score) 

    total_score = (news_score * 0.4) + \
                  (volume_value_score * 0.3) + \
                  (chegyul_score * 0.15) + \
                  (buy_pressure_score * 0.1) + \
                  (ma_score * 0.05)
    
    return total_score

def execute_buy_strategy(kiwoom_helper, kiwoom_tr_request, trade_manager, monitor_positions):
    """
    매수 전략을 실행하여 매수 후보군을 검색하고, 최종 매수 종목을 선정하여 주문을 실행합니다.
    이 함수는 local_api_server의 메인 트레이딩 루프에서 매매 시간대에 주기적으로 호출됩니다.
    """
    current_time_str = get_current_time_str()
    logger.info(f"[{current_time_str}] 매수 전략 실행: 종목 검색 및 매수 결정.")

    kospi_tickers = kiwoom_helper.get_code_list_by_market("0") 
    kosdaq_tickers = kiwoom_helper.get_code_list_by_market("10") 
    all_tickers = kospi_tickers + kosdaq_tickers
    
    if not all_tickers:
        logger.warning(f"[{current_time_str}] 종목 코드 리스트를 가져올 수 없습니다. 매수 전략을 실행할 수 없습니다.")
        return

    buy_candidates = []

    current_positions = monitor_positions.get_all_positions()
    current_holding_codes = set(current_positions.keys())
    if current_holding_codes:
        logger.info(f"현재 보유 종목: {len(current_holding_codes)}개. 매수 후보에서 제외합니다.")

    for i, stock_code in enumerate(all_tickers):
        time.sleep(0.2) 

        if stock_code in current_holding_codes:
            logger.debug(f"보유 중인 종목 {stock_code}는 매수 후보에서 제외합니다.")
            continue
            
        stock_name = kiwoom_helper.get_stock_name(stock_code)
        if stock_name == "Unknown":
            logger.warning(f"종목명 조회 실패 ({stock_code}). 건너뜀.")
            continue

        result = check_buy_conditions(kiwoom_helper, kiwoom_tr_request, stock_code, stock_name)
        if result:
            buy_candidates.append(result)
            logger.info(f"✨ 매수 후보 종목 발견: {stock_name}({stock_code}), 점수: {result['score']:.2f}")

    if not buy_candidates:
        logger.info(f"[{current_time_str}] 매수 조건을 충족하는 종목이 없습니다.")
        return

    df_candidates = pd.DataFrame(buy_candidates)
    df_candidates = df_candidates.sort_values(by="score", ascending=False).reset_index(drop=True)

    account_info = kiwoom_tr_request.request_account_info(trade_manager.account_number)
    available_cash = account_info.get("예수금", 0)
    
    if available_cash <= 0:
        logger.warning(f"[{current_time_str}] 매수 가능 예수금이 없습니다. 매수 중단.")
        send_telegram_message("🚫 매수 실패: 예수금 부족.")
        return

    buy_amount = available_cash * 0.5 

    logger.info(f"[{current_time_str}] 매수 후보군 {len(df_candidates)}개 발견. 상위 종목 선정...")
    
    top_candidate = df_candidates.iloc[0]
    target_stock_code = top_candidate["stock_code"]
    target_stock_name = top_candidate["stock_name"]
    target_current_price = top_candidate["current_price"]

    quantity_to_buy = int((buy_amount / target_current_price) // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE
    
    if quantity_to_buy <= 0:
        logger.warning(f"[{current_time_str}] {target_stock_name}({target_stock_code}) 매수 가능한 수량 없음 (예수금 부족 또는 가격이 너무 높음).")
        send_telegram_message(f"🚫 매수 실패: {target_stock_name} 매수 수량 부족.")
        return

    logger.info(f"[{current_time_str}] 최종 매수 종목 선정: {target_stock_name}({target_stock_code})")
    logger.info(f"매수 시도: {target_stock_name}({target_stock_code}), 수량: {quantity_to_buy}주, 예상 매수 금액: {quantity_to_buy * target_current_price:,}원")
    send_telegram_message(f"🚀 매수 신호 포착: {target_stock_name}({target_stock_code})\n예상 수량: {quantity_to_buy}주, 점수: {top_candidate['score']:.2f}")

    order_success = False
    
    buy_order_price = kiwoom_helper.real_time_data.get(target_stock_code, {}).get('최우선매수호가', target_current_price)
    
    logger.info(f"[{current_time_str}] 지정가 매수 시도: {target_stock_name}({target_stock_code}) 수량: {quantity_to_buy}주, 가격: {buy_order_price:,}원")
    result = trade_manager.place_order(target_stock_code, 1, quantity_to_buy, buy_order_price, "00") 
    
    if result["status"] == "success":
        order_success = True
        logger.info(f"✅ 지정가 매수 주문 성공: {target_stock_name}({target_stock_code})")
    else:
        logger.warning(f"⚠️ 지정가 매수 주문 실패 ({result.get('message', '알 수 없는 오류')}). 시장가 재시도.")
        send_telegram_message(f"⚠️ 지정가 매수 실패: {target_stock_name}. 시장가 재시도.")
        
        logger.info(f"[{current_time_str}] 시장가 매수 시도: {target_stock_name}({target_stock_code}) 수량: {quantity_to_buy}주")
        result = trade_manager.place_order(target_stock_code, 1, quantity_to_buy, 0, "03") 
        
        if result["status"] == "success":
            order_success = True
            logger.info(f"✅ 시장가 매수 주문 성공: {target_stock_name}({target_stock_code})")
        else:
            logger.error(f"🔴 시장가 매수 주문 실패: {target_stock_name}({target_stock_code}) - {result.get('message', '알 수 없는 오류')}")
            send_telegram_message(f"🔴 매수 최종 실패: {target_stock_name}({target_stock_code}) - {result.get('message', '알 수 없는 오류')}")

    if order_success:
        pass 
        logger.info(f"[{current_time_str}] 매수 전략 실행 종료: {target_stock_name} 매수 주문 완료.")
    else:
        logger.info(f"[{current_time_str}] 매수 전략 실행 종료: {target_stock_name} 매수 주문 실패.")
