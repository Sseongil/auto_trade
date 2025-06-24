# modules/strategies/buy_strategy.py

import logging
from datetime import datetime, timedelta
import pandas as pd # 데이터 처리를 위해 pandas 임포트

# 필요한 모듈 임포트
from modules.common.utils import get_current_time_str
from modules.notify import send_telegram_message
from modules.trade_logger import TradeLogger
from modules.common.config import (
    MIN_GAP_UP_PCT, MIN_CURRENT_PRICE_VS_OPEN_PCT, MIN_VOLUME_INCREASE_RATIO,
    MIN_TRADING_VALUE_BILLION, MIN_CHEGYUL_GANGDO, MIN_BUY_SELL_RATIO,
    MIN_PRICE, MAX_PRICE, MIN_MARKET_CAP_BILLION, MAX_MARKET_CAP_BILLION,
    MAX_CURRENT_DAILY_CHANGE_PCT, DEFAULT_LOT_SIZE, MAX_BUY_ATTEMPTS
)

logger = logging.getLogger(__name__)
trade_logger = TradeLogger() # 매매 로그 기록을 위한 TradeLogger 인스턴스

# 뉴스/공시 점수를 위한 임시 함수 (추후 news_crawler 모듈과 연동)
def get_news_score(stock_code, stock_name):
    """
    뉴스/공시 점수를 반환하는 임시 함수.
    실제 구현에서는 news_crawler 모듈을 통해 최신 뉴스/공시를 분석합니다.
    """
    # TODO: news_crawler 모듈과 연동하여 실제 뉴스 점수 로직 구현
    # 현재는 더미 점수 반환 (예: 긍정적 뉴스 가정 시 높은 점수)
    logger.debug(f"뉴스/공시 점수 계산 (현재 더미): {stock_name}({stock_code})")
    # 실제 뉴스 검색 결과에 따라 점수 부여 로직이 필요
    # 예: 특정 키워드 포함, 발표 시간, 중요도 등
    return 15 # 임시로 15점 부여 (0~20점 범위)

def check_buy_conditions(kiwoom_helper, kiwoom_tr_request, stock_code, stock_name):
    """
    주어진 종목이 매수 조건을 충족하는지 확인하고, 점수를 반환합니다.
    
    Args:
        kiwoom_helper (KiwoomQueryHelper): 키움 API 헬퍼 인스턴스.
        kiwoom_tr_request (KiwoomTrRequest): TR 요청 헬퍼 인스턴스.
        stock_code (str): 종목 코드.
        stock_name (str): 종목명.
        
    Returns:
        dict: 조건을 통과한 경우 종목 정보와 점수, 실패 시 None.
    """
    logger.info(f"🔍 {stock_name}({stock_code}) 매수 조건 검사 시작...")
    
    # --- 실시간 데이터 가져오기 (KiwoomQueryHelper에서 수집된 데이터 활용) ---
    real_time_info = kiwoom_helper.real_time_data.get(stock_code, {})
    current_price = real_time_info.get('current_price', 0)
    trading_volume = real_time_info.get('trading_volume', 0)
    # 체결강도, 매수/매도 잔량 등은 KiwoomQueryHelper의 _on_receive_real_data에서 더 많은 FID를 수집해야 함
    # 현재는 임시로 0으로 설정하거나, get_current_real_data_fids 함수를 통해 가져와야 함.
    chegyul_gangdo = real_time_info.get('chegyul_gangdo', 0.0) # FID 228 (체결강도) 또는 229 (매수체결강도), 230 (매도체결강도)
    total_buy_cvol = real_time_info.get('total_buy_cvol', 0) # 총 매수 잔량 (FID 851)
    total_sell_cvol = real_time_info.get('total_sell_cvol', 0) # 총 매도 잔량 (FID 852)

    if current_price == 0:
        logger.warning(f"⚠️ {stock_name}({stock_code}) 실시간 현재가 정보 없음. 조건 검사 불가.")
        return None

    # --- TR 데이터 요청 (일봉, 5분봉, 시가총액 등) ---
    today_str = datetime.today().strftime("%Y%m%d")
    
    # 일봉 데이터 요청 (OPT10081)
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
    
    # 5분봉 데이터 요청 (OPT10080)
    five_min_ohlcv_data = kiwoom_tr_request.request_five_minute_ohlcv_data(stock_code, today_str, sPrevNext="0")
    if not five_min_ohlcv_data or five_min_ohlcv_data.get("error"):
        logger.warning(f"⚠️ {stock_name}({stock_code}) 5분봉 데이터 조회 실패: {five_min_ohlcv_data.get('error', '응답 없음')}")
        return None

    df_5min = pd.DataFrame(five_min_ohlcv_data['data'])
    if df_5min.empty:
        logger.warning(f"⚠️ {stock_name}({stock_code}) 5분봉 데이터 부족. 조건 검사 불가.")
        return None

    # 시가총액 및 기본 정보 요청 (OPT10001 또는 OPT10004 등)
    stock_info = kiwoom_tr_request.request_stock_basic_info(stock_code)
    if not stock_info or stock_info.get("error"):
        logger.warning(f"⚠️ {stock_name}({stock_code}) 기본 정보 조회 실패: {stock_info.get('error', '응답 없음')}")
        return None
    
    market_cap_billion = stock_info.get('시가총액', 0) / 1_0000_0000 # 억 단위로 변환

    # --- 2단계: 매수 조건 검사 ---
    
    # [시가 갭 상승 및 장대 양봉 형성]
    # 당일 시가가 전일 종가 대비 3% 이상 갭 상승 출발.
    # df_daily의 가장 최근(오늘) 데이터를 사용
    today_open = df_daily.iloc[-1]['시가']
    if len(df_daily) < 2:
        logger.debug(f"DEBUG: {stock_name}({stock_code}) 일봉 데이터 2개 미만. 갭 상승 조건 건너뜀.")
        return None # 전일 종가 비교 불가
    prev_close = df_daily.iloc[-2]['현재가'] # 전일 종가는 '현재가' 컬럼으로 들어옴

    if prev_close == 0:
        logger.warning(f"⚠️ {stock_name}({stock_code}) 전일 종가 0. 갭 상승 조건 검사 불가.")
        return None

    gap_up_pct = ((today_open - prev_close) / prev_close) * 100
    if gap_up_pct < MIN_GAP_UP_PCT:
        logger.debug(f"❌ {stock_name}({stock_code}) 갭 상승 조건 불충족: {gap_up_pct:.2f}% (기준: {MIN_GAP_UP_PCT}%)")
        return None

    # 현재가가 당일 시가 대비 3% 이상 상승 중.
    current_vs_open_pct = ((current_price - today_open) / today_open) * 100 if today_open != 0 else 0
    if current_vs_open_pct < MIN_CURRENT_PRICE_VS_OPEN_PCT:
        logger.debug(f"❌ {stock_name}({stock_code}) 현재가 대비 시가 상승 조건 불충족: {current_vs_open_pct:.2f}% (기준: {MIN_CURRENT_PRICE_VS_OPEN_PCT}%)")
        return None

    # [압도적인 거래량/거래대금]
    # 당일 누적 거래량이 직전 5일 평균 거래량 대비 700% 이상 증가.
    # 당일 누적 거래대금이 200억 원 이상.
    if len(df_daily) < 6: # 오늘 포함 6일 (오늘 + 직전 5일)
        logger.debug(f"DEBUG: {stock_name}({stock_code}) 일봉 데이터 6개 미만. 거래량 조건 건너뜀.")
        return None
        
    last_5_days_volume = df_daily['거래량'].iloc[-6:-1].astype(float) # 직전 5일 거래량
    avg_5_day_volume = last_5_days_volume.mean()

    volume_increase_ratio = (trading_volume / avg_5_day_volume * 100) if avg_5_day_volume != 0 else float('inf') # 현재 누적 거래량
    if volume_increase_ratio < MIN_VOLUME_INCREASE_RATIO:
        logger.debug(f"❌ {stock_name}({stock_code}) 거래량 증가 조건 불충족: {volume_increase_ratio:.2f}% (기준: {MIN_VOLUME_INCREASE_RATIO}%)")
        return None

    today_trading_value_billion = (current_price * trading_volume) / 1_0000_0000_0000 # 억 단위로 변환 (현재가 * 거래량 / 1조)
    if today_trading_value_billion < MIN_TRADING_VALUE_BILLION:
        logger.debug(f"❌ {stock_name}({stock_code}) 거래대금 조건 불충족: {today_trading_value_billion:.2f}억 원 (기준: {MIN_TRADING_VALUE_BILLION}억 원)")
        return None

    # [이동평균선 정배열 전환/유지]
    # 일봉: 5일 이평선이 20일 이평선 위로 상향 돌파했거나, 이미 정배열(5 > 20 > 60)을 유지하며 상승 추세 중.
    # 5분봉: 현재가가 5분봉 5일 이평선 위에 위치하며, 5분봉 5일 이평선이 20일 이평선 위에 위치.
    
    # 일봉 이평선 계산
    df_daily['MA5'] = df_daily['현재가'].rolling(window=5).mean()
    df_daily['MA20'] = df_daily['현재가'].rolling(window=20).mean()
    df_daily['MA60'] = df_daily['현재가'].rolling(window=60).mean()

    # 충분한 데이터가 있는지 확인
    if len(df_daily) < 60:
        logger.debug(f"DEBUG: {stock_name}({stock_code}) 일봉 MA60 계산에 필요한 데이터 부족.")
        return None

    # 일봉 정배열 조건 검사
    ma5_daily = df_daily['MA5'].iloc[-1]
    ma20_daily = df_daily['MA20'].iloc[-1]
    ma60_daily = df_daily['MA60'].iloc[-1]
    
    daily_ma_golden_cross = False
    if len(df_daily) >= 2:
        ma5_prev = df_daily['MA5'].iloc[-2]
        ma20_prev = df_daily['MA20'].iloc[-2]
        if ma5_prev < ma20_prev and ma5_daily >= ma20_daily: # 골든크로스 발생
            daily_ma_golden_cross = True

    daily_ma_strong_alignment = (ma5_daily > ma20_daily > ma60_daily)
    
    if not (daily_ma_golden_cross or daily_ma_strong_alignment):
        logger.debug(f"❌ {stock_name}({stock_code}) 일봉 이평선 정배열/골든크로스 조건 불충족.")
        return None

    # 5분봉 이평선 계산 (현재 종가 기준)
    df_5min['MA5'] = df_5min['현재가'].rolling(window=5).mean()
    df_5min['MA20'] = df_5min['현재가'].rolling(window=20).mean()

    if len(df_5min) < 20: # 5분봉 MA20 계산에 필요한 데이터
        logger.debug(f"DEBUG: {stock_name}({stock_code}) 5분봉 MA20 계산에 필요한 데이터 부족.")
        return None

    ma5_5min = df_5min['MA5'].iloc[-1]
    ma20_5min = df_5min['MA20'].iloc[-1]

    if not (current_price > ma5_5min and ma5_5min > ma20_5min):
        logger.debug(f"❌ {stock_name}({stock_code}) 5분봉 이평선 조건 불충족: 현재가({current_price}) > MA5({ma5_5min}) > MA20({ma20_5min})")
        return None

    # [강력한 매수 압력 (실시간)]
    # 5분봉 체결강도가 130% 이상.
    # 매수 총 잔량이 매도 총 잔량의 1.5배 이상.
    if chegyul_gangdo < MIN_CHEGYUL_GANGDO:
        logger.debug(f"❌ {stock_name}({stock_code}) 체결강도 조건 불충족: {chegyul_gangdo:.2f}% (기준: {MIN_CHEGYUL_GANGDO}%)")
        return None
    
    if total_sell_cvol == 0: # 매도 총 잔량이 0이면 무한대이므로 조건 충족
        buy_sell_ratio = float('inf')
    else:
        buy_sell_ratio = total_buy_cvol / total_sell_cvol

    if buy_sell_ratio < MIN_BUY_SELL_RATIO:
        logger.debug(f"❌ {stock_name}({stock_code}) 매수/매도 잔량 비율 조건 불충족: {buy_sell_ratio:.2f}배 (기준: {MIN_BUY_SELL_RATIO}배)")
        return None

    # [변동성 및 가격대 제한]
    # 주가: 1,000원 ~ 50,000원.
    # 시가총액: 500억 원 ~ 5조 원.
    # 당일 등락률: 매수 시점 기준 +12% 이하 (고점 추격 방지).
    if not (MIN_PRICE <= current_price <= MAX_PRICE):
        logger.debug(f"❌ {stock_name}({stock_code}) 주가 범위 조건 불충족: {current_price:,}원 (기준: {MIN_PRICE}~{MAX_PRICE}원)")
        return None

    if not (MIN_MARKET_CAP_BILLION <= market_cap_billion <= MAX_MARKET_CAP_BILLION):
        logger.debug(f"❌ {stock_name}({stock_code}) 시가총액 범위 조건 불충족: {market_cap_billion:.2f}억 원 (기준: {MIN_MARKET_CAP_BILLION}~{MAX_MARKET_CAP_BILLION}억 원)")
        return None

    current_daily_change_pct = ((current_price - df_daily.iloc[-1]['종가']) / df_daily.iloc[-1]['종가']) * 100 if df_daily.iloc[-1]['종가'] != 0 else 0
    if current_daily_change_pct > MAX_CURRENT_DAILY_CHANGE_PCT:
        logger.debug(f"❌ {stock_name}({stock_code}) 당일 등락률 조건 불충족: {current_daily_change_pct:.2f}% (기준: {MAX_CURRENT_DAILY_CHANGE_PCT}%)")
        return None

    # 모든 조건을 통과한 경우 점수 계산
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
        # 추가적인 정보 (나중에 필요할 수 있음)
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
    news_score = get_news_score(stock_code, stock_name) # 0~20점
    
    # 거래량/거래대금 점수 (0~20점)
    # 증가율이 높을수록, 거래대금 클수록 점수 높게
    volume_value_score = 0
    volume_value_score += min(20, (volume_increase_ratio / MIN_VOLUME_INCREASE_RATIO) * 10) # 기준 700% 대비
    volume_value_score += min(20, (trading_value_billion / MIN_TRADING_VALUE_BILLION) * 10) # 기준 200억 대비
    volume_value_score = min(20, volume_value_score) # 최대 20점

    # 체결강도 점수 (0~5점)
    chegyul_score = min(5, (chegyul_gangdo / MIN_CHEGYUL_GANGDO) * 3) # 기준 130% 대비

    # 호가창 매수 압력 점수 (0~5점)
    buy_pressure_score = min(5, (buy_sell_ratio / MIN_BUY_SELL_RATIO) * 3) # 기준 1.5배 대비

    # 이평선 배열 점수 (0~3점)
    ma_score = 0
    if daily_ma_strong_alignment:
        ma_score += 2
    if five_min_ma_alignment:
        ma_score += 1
    ma_score = min(3, ma_score) # 최대 3점

    # 총점 계산 (가중치 적용)
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

    # 1. 모든 코스피/코스닥 종목 리스트 가져오기 (KiwoomQueryHelper에 해당 메서드 추가 필요)
    # TODO: kiwoom_helper.get_code_list_by_market("0") # 코스피
    # TODO: kiwoom_helper.get_code_list_by_market("10") # 코스닥
    
    # 임시 종목 리스트 (실제로는 API에서 받아와야 함)
    # 예시 종목: 삼성전자, 카카오 (실제로는 시장 전체 종목을 조회)
    all_tickers = ["005930", "035720", "005380"] # 삼성전자, 카카오, 현대차 예시
    
    buy_candidates = []

    # 이미 보유 중인 종목은 매수 후보에서 제외
    current_positions = monitor_positions.get_all_positions()
    if current_positions:
        logger.info(f"현재 보유 종목: {len(current_positions)}개. 매수 후보에서 제외합니다.")

    for i, stock_code in enumerate(all_tickers):
        if stock_code in current_positions:
            logger.debug(f"보유 중인 종목 {stock_code}는 매수 후보에서 제외합니다.")
            continue
            
        stock_name = kiwoom_helper.get_stock_name(stock_code)
        if stock_name == "Unknown":
            logger.warning(f"종목명 조회 실패 ({stock_code}). 건너뜀.")
            continue

        # 2. 각 종목에 대해 매수 조건 검사
        result = check_buy_conditions(kiwoom_helper, kiwoom_tr_request, stock_code, stock_name)
        if result:
            buy_candidates.append(result)

        # 너무 많은 TR 요청을 방지하기 위해 잠시 대기 (실제 운영 시에는 트래픽 관리 필요)
        # TR 요청이 많으므로 여기에 적절한 지연 시간을 두거나,
        # TR 요청 횟수를 제한하는 로직이 필요합니다.
        # (예: 1초에 5회 이상 TR 요청 금지)
        # time.sleep(0.2) # TR 요청 간 최소 간격 (키움 API 제한에 따라 조정)

    if not buy_candidates:
        logger.info(f"[{current_time_str}] 매수 조건을 충족하는 종목이 없습니다.")
        return

    # 3. 우선순위 점수화 및 최종 매매 결정
    df_candidates = pd.DataFrame(buy_candidates)
    df_candidates = df_candidates.sort_values(by="score", ascending=False).reset_index(drop=True)

    # 매수 비중: 예수금의 50%
    account_info = kiwoom_tr_request.request_account_info(trade_manager.account_number)
    available_cash = account_info.get("예수금", 0)
    
    if available_cash <= 0:
        logger.warning(f"[{current_time_str}] 매수 가능 예수금이 없습니다. 매수 중단.")
        send_telegram_message("🚫 매수 실패: 예수금 부족.")
        return

    buy_amount = available_cash * 0.5 # 예수금의 50%

    logger.info(f"[{current_time_str}] 매수 후보군 {len(df_candidates)}개 발견. 상위 종목 선정...")
    
    # 최종 매수 대상 선정 (가장 점수가 높은 1개 종목)
    top_candidate = df_candidates.iloc[0]
    target_stock_code = top_candidate["stock_code"]
    target_stock_name = top_candidate["stock_name"]
    target_current_price = top_candidate["current_price"]

    # 매수 수량 계산 (DEFAULT_LOT_SIZE 단위로)
    quantity_to_buy = int((buy_amount / target_current_price) // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE
    
    if quantity_to_buy <= 0:
        logger.warning(f"[{current_time_str}] {target_stock_name}({target_stock_code}) 매수 가능한 수량 없음 (예수금 부족 또는 가격이 너무 높음).")
        send_telegram_message(f"🚫 매수 실패: {target_stock_name} 매수 수량 부족.")
        return

    logger.info(f"[{current_time_str}] 최종 매수 종목 선정: {target_stock_name}({target_stock_code})")
    logger.info(f"매수 시도: {target_stock_name}({target_stock_code}), 수량: {quantity_to_buy}주, 예상 매수 금액: {quantity_to_buy * target_current_price:,}원")
    send_telegram_message(f"🚀 매수 신호 포착: {target_stock_name}({target_stock_code})\n예상 수량: {quantity_to_buy}주, 점수: {top_candidate['score']:.2f}")

    # 매수 주문 실행 (최우선 매수 호가에 지정가 주문 먼저 시도)
    order_success = False
    
    # 최우선 매수 호가 조회
    buy_order_price = kiwoom_helper.real_time_data.get(target_stock_code, {}).get('최우선매수호가', target_current_price)
    
    logger.info(f"[{current_time_str}] 지정가 매수 시도: {target_stock_name}({target_stock_code}) 수량: {quantity_to_buy}주, 가격: {buy_order_price:,}원")
    result = trade_manager.place_order(target_stock_code, 1, quantity_to_buy, buy_order_price, "00") # 1: 매수, 00: 지정가
    
    if result["status"] == "success":
        order_success = True
        logger.info(f"✅ 지정가 매수 주문 성공: {target_stock_name}({target_stock_code})")
    else:
        logger.warning(f"⚠️ 지정가 매수 주문 실패 ({result.get('message', '알 수 없는 오류')}). 시장가 재시도.")
        send_telegram_message(f"⚠️ 지정가 매수 실패: {target_stock_name}. 시장가 재시도.")
        
        # 10초 이내 미체결 시 시장가로 전환하여 매수 (단타 전략의 속도 중요성)
        # 실제 체결 여부 확인은 TradeManager의 on_receive_chejan_data 이벤트로 이루어져야 함.
        # 여기서는 간단히 일정 시간 대기 후 미체결이면 시장가로 간주.
        # TODO: 실제 미체결 확인 로직 (OnReceiveChejanData에서 미체결 잔량 확인) 필요.
        
        # 임시 대기 (실제로는 미체결 여부를 API로 확인해야 함)
        # time_module.sleep(10) 
        
        # 시장가 매수 재시도 (미체결 주문이 있을 경우 취소 후 재주문 로직도 필요)
        logger.info(f"[{current_time_str}] 시장가 매수 시도: {target_stock_name}({target_stock_code}) 수량: {quantity_to_buy}주")
        result = trade_manager.place_order(target_stock_code, 1, quantity_to_buy, 0, "03") # 03: 시장가
        
        if result["status"] == "success":
            order_success = True
            logger.info(f"✅ 시장가 매수 주문 성공: {target_stock_name}({target_stock_code})")
        else:
            logger.error(f"🔴 시장가 매수 주문 실패: {target_stock_name}({target_stock_code}) - {result.get('message', '알 수 없는 오류')}")
            send_telegram_message(f"🔴 매수 최종 실패: {target_stock_name}({target_stock_code}) - {result.get('message', '알 수 없는 오류')}")

    if order_success:
        # 매수 주문 성공 시, MonitorPositions에서 자동으로 포지션이 업데이트될 것임
        # 여기서는 매매 로그만 남깁니다.
        # 매수 체결 가격은 TradeManager의 체결 이벤트에서 받아와야 정확합니다.
        # 여기서는 임시로 현재가를 사용합니다.
        trade_logger.log_trade(
            stock_code=target_stock_code,
            stock_name=target_stock_name,
            trade_type="매수",
            order_price=buy_order_price, # 지정가 시도 가격
            executed_price=target_current_price, # 임시로 현재가 (실제는 체결가)
            quantity=quantity_to_buy,
            pnl_amount=0, pnl_pct=0,
            account_balance_after_trade=trade_manager.kiwoom_tr_request.request_account_info(trade_manager.account_number).get("예수금"),
            strategy_name="BuySignal"
        )
        logger.info(f"[{current_time_str}] 매수 전략 실행 종료: {target_stock_name} 매수 주문 완료.")
    else:
        logger.info(f"[{current_time_str}] 매수 전략 실행 종료: {target_stock_name} 매수 주문 실패.")

