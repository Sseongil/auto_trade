# modules/check_conditions_threaded.py

import os
import sys
import logging
import pandas as pd
import threading
import concurrent.futures
from datetime import datetime
import pythoncom # COM 초기화를 위해 필요

# --- 모듈 경로 설정 (필요시) ---
# 이 스크립트의 디렉토리를 sys.path에 추가 (상대 경로 임포트 문제 방지)
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
# 프로젝트 루트 디렉토리도 추가 (modules 패키지 임포트용)
project_root = os.path.abspath(os.path.join(script_dir, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- 모듈 임포트 ---
from modules.common.config import (
    MARKET_CODES,
    EXCLUDE_NAME_KEYWORDS,
    EXCLUDE_STATUS_KEYWORDS,
    MIN_DATA_POINTS,
    CONDITION_CHECK_MAX_WORKERS,
    MA_SHORT_PERIOD, MA_MEDIUM_PERIOD, MA_LONG_PERIOD, # 추가된 MA 설정
    VOLUME_AVG_PERIOD, VOLUME_MULTIPLIER, HIGH_PRICE_LOOKBACK # 추가된 거래량/고점 돌파 설정
)
from modules.common.utils import get_current_time_str
from modules.Kiwoom.kiwoom_query_helper import KiwoomQueryHelper # KiwoomQueryHelper 임포트
from modules.Kiwoom.kiwoom_tr_request import KiwoomTrRequest # KiwoomTrRequest 임포트

# --- 로깅 설정 ---
logger = logging.getLogger(__name__)

# --- 도우미 함수: 일봉 데이터 조회 ---
def get_daily_data(kiwoom_tr_request_instance, stock_code):
    """
    주어진 종목코드에 대한 일봉 데이터를 키움 API로부터 요청합니다.
    Args:
        kiwoom_tr_request_instance: KiwoomTrRequest 클래스의 인스턴스 (스레드별 독립)
        stock_code (str): 종목 코드
    Returns:
        pd.DataFrame: 일봉 데이터 (날짜, 종가, 거래량, 시가, 고가, 저가), 또는 None
    """
    try:
        today_str = datetime.today().strftime("%Y%m%d")
        # KiwoomTrRequest 인스턴스를 통해 opt10081 요청
        # kiwoom_tr_request에 request_daily_ohlcv (opt10081) 메서드가 구현되어 있어야 함
        df_raw = kiwoom_tr_request_instance.request_daily_ohlcv(
            stock_code=stock_code,
            base_date=today_str,
            modify_price_gubun=1 # 수정주가구분: 1
        )
        
        if df_raw is None or df_raw.empty:
            logger.debug(f"[{stock_code}] 일봉 데이터 조회 결과 없음.")
            return None

        # 데이터 클렌징 및 타입 변환
        # GetCommData로 받은 필드명이 '현재가'일 경우 '종가'로 통일
        df = df_raw.rename(columns={"현재가": "종가", "일자": "날짜"})
        
        # 숫자형 컬럼 처리: 콤마, +/- 부호 제거 후 정수형 변환
        for col in ["종가", "거래량", "고가", "저가", "시가"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '').str.replace('+', '').str.replace('-', '').astype(int)
            else:
                logger.warning(f"[{stock_code}] 일봉 데이터에 '{col}' 컬럼이 없습니다.")
                return None # 필수 컬럼 누락 시 None 반환

        df['날짜'] = pd.to_datetime(df['날짜']) # 날짜를 datetime 객체로 변환
        df = df.sort_values("날짜").reset_index(drop=True) # 날짜 순으로 정렬

        # 최소 데이터 포인트 확인
        if len(df) < MIN_DATA_POINTS:
            logger.debug(f"[{stock_code}] 데이터 포인트 부족 ({len(df)}개, 최소 {MIN_DATA_POINTS}개 필요).")
            return None
        
        return df
    except Exception as e:
        logger.error(f"[{stock_code}] 일봉 데이터 조회 실패: {e}", exc_info=True)
        return None

# --- 도우미 함수: 기술적 조건 평가 ---
def is_passing_conditions(df):
    """
    주어진 DataFrame에 대해 기술적 분석 조건을 평가합니다.
    """
    try:
        # 데이터 길이 다시 확인 (가장 긴 롤링 윈도우를 커버할 수 있는지)
        min_required_data = max(MA_LONG_PERIOD, VOLUME_AVG_PERIOD, HIGH_PRICE_LOOKBACK)
        if len(df) < min_required_data:
            logger.debug(f"데이터 포인트 부족 ({len(df)}개, 최소 {min_required_data}개 필요). 기술적 분석 불가.")
            return False

        # 이동평균선 계산
        # 마지막 N일 데이터만 사용하는 것이 아니라, 전체 DataFrame에 대해 계산
        df['MA_SHORT'] = df['종가'].rolling(window=MA_SHORT_PERIOD).mean()
        df['MA_MEDIUM'] = df['종가'].rolling(window=MA_MEDIUM_PERIOD).mean()
        df['MA_LONG'] = df['종가'].rolling(window=MA_LONG_PERIOD).mean()

        # 최신 데이터 포인트 (iloc[-1]) 사용
        curr_close = df["종가"].iloc[-1]
        curr_ma_s = df["MA_SHORT"].iloc[-1]
        curr_ma_m = df["MA_MEDIUM"].iloc[-1]
        curr_ma_l = df["MA_LONG"].iloc[-1]

        # 필요한 값이 NaN이 아닌지 확인 (초기 롤링 기간 때문에 NaN이 될 수 있음)
        if pd.isna(curr_ma_s) or pd.isna(curr_ma_m) or pd.isna(curr_ma_l):
            logger.debug("이동평균선 계산 중 NaN 값 발생 (데이터 부족 또는 계산 오류).")
            return False

        # 1. 정배열 조건 (단기 > 중기 > 장기 이동평균선)
        ma_aligned = (curr_ma_s > curr_ma_m and curr_ma_m > curr_ma_l)
        if not ma_aligned:
            logger.debug(f"정배열 조건 불충족: {curr_ma_s:.2f} > {curr_ma_m:.2f} > {curr_ma_l:.2f}")
            return False

        # 2. 고점 돌파 조건 (현재 종가가 최근 N일간의 최고가 돌파)
        # 과거 N일 (HIGH_PRICE_LOOKBACK) 동안의 고가 중 최고값
        # iloc[-HIGH_PRICE_LOOKBACK-1:-1]은 현재 봉을 제외한 최근 HIGH_PRICE_LOOKBACK 개 봉을 의미.
        if len(df) < HIGH_PRICE_LOOKBACK + 1:
            logger.debug(f"고점 돌파 조건 검사 데이터 부족 (최소 {HIGH_PRICE_LOOKBACK + 1}개 필요).")
            return False
            
        recent_high_price = df["고가"].iloc[-(HIGH_PRICE_LOOKBACK + 1):-1].max() # 현재 봉 제외 과거 고점
        price_breakout = (curr_close > recent_high_price)
        if not price_breakout:
            logger.debug(f"고점 돌파 조건 불충족: 현재종가 {curr_close:,}원 <= 최근 {HIGH_PRICE_LOOKBACK}일 최고가 {recent_high_price:,}원")
            return False

        # 3. 거래량 조건 (최근 1일 거래량이 과거 N일 평균 거래량의 X배 이상)
        volume_condition_met = False
        if len(df) >= VOLUME_AVG_PERIOD + 1: # 과거 평균 거래량 계산을 위해 충분한 데이터 필요
            # 마지막 거래일 제외하고 과거 VOLUME_AVG_PERIOD일의 평균 거래량
            avg_volume = df["거래량"].iloc[-(VOLUME_AVG_PERIOD + 1):-1].mean()
            if avg_volume > 0:
                volume_condition_met = (df["거래량"].iloc[-1] >= avg_volume * VOLUME_MULTIPLIER)
            else: # 과거 평균 거래량이 0이면 (거래가 거의 없었으면) 현재 거래량이 커도 조건 불충족으로 간주
                volume_condition_met = False
        
        if not volume_condition_met:
            logger.debug(f"거래량 조건 불충족: 현재 거래량 {df['거래량'].iloc[-1]:,}, 평균 {avg_volume:.0f}, 배율 {VOLUME_MULTIPLIER}")
            return False

        # 모든 조건 종합
        return ma_aligned and price_breakout and volume_condition_met

    except Exception as e:
        logger.error(f"기술적 조건 평가 중 오류 발생: {e}", exc_info=True)
        return False

# --- 스레드 워커 함수 ---
def _run_condition_worker(market_code):
    """
    단일 시장에 대해 조건 검색을 실행하는 스레드 워커 함수.
    이 함수는 자신만의 Kiwoom API 인스턴스를 생성하고 관리합니다.
    """
    worker_kiwoom_ocx = None
    worker_kiwoom_helper = None
    worker_kiwoom_tr_request = None
    
    try:
        # 각 스레드에서 COM 객체 초기화 (중요)
        pythoncom.CoInitialize() 

        # QApplication 인스턴스 참조 (메인 스레드에서 생성된 것 사용)
        # 백그라운드 스레드에서 QApplication을 새로 생성하면 안 됨.
        app_instance = QApplication.instance()
        if app_instance is None:
            # 이 워커가 메인 스레드에서 실행되지 않고, QApplication이 아직 생성되지 않은 경우
            # (예: 테스트 환경), 오류 방지를 위해 더미 QApplication을 사용하거나 로깅
            logger.error("❌ QApplication 인스턴스를 찾을 수 없습니다. GUI 관련 기능에 문제가 발생할 수 있습니다.")
            # 실제 운영 환경에서는 QApplication이 메인 스레드에서 항상 생성되어야 함
            # 여기서는 편의상 무시하고 진행하거나, 치명적 오류로 처리할 수 있음.
            # 이 워커에서는 GUI 이벤트를 처리할 필요가 없으므로 큰 문제는 아닐 수 있음.
            # app_instance = QApplication([]) # 이렇게 하면 안됨

        # 각 스레드에 독립적인 Kiwoom API 객체 생성
        from PyQt5.QAxContainer import QAxWidget
        worker_kiwoom_ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        
        # KiwoomQueryHelper 및 KiwoomTrRequest 인스턴스 생성
        worker_kiwoom_helper = KiwoomQueryHelper(worker_kiwoom_ocx, app_instance)
        worker_kiwoom_tr_request = KiwoomTrRequest(
            kiwoom_helper=worker_kiwoom_helper, 
            qt_app=app_instance, 
            account_password="" # TR 요청 시 비밀번호가 필요할 수 있으나, 여기서는 조회용이므로 빈 값
        )

        # 키움 API 연결 (로그인)
        if not worker_kiwoom_helper.connect_kiwoom(timeout_ms=10000):
            logger.error(f"❌ 시장({market_code}) 워커 Kiwoom API 연결 실패. 해당 시장 검색 건너뜀.")
            return []

        # 종목 필터링 및 데이터 조회
        tickers = worker_kiwoom_helper.get_code_list_by_market(market_code)
        filtered_candidates = []

        for code in tickers:
            try:
                name = worker_kiwoom_helper.get_stock_name(code)

                # 이름 필터링
                if any(keyword in name for keyword in EXCLUDE_NAME_KEYWORDS):
                    logger.debug(f"이름 제외 키워드 포함 ({name}) - {code}")
                    continue

                # 종목 상태 필터링
                state = worker_kiwoom_helper.get_stock_state(code)
                if any(keyword in state for keyword in EXCLUDE_STATUS_KEYWORDS):
                    logger.debug(f"상태 제외 키워드 포함 ({state}) - {name}({code})")
                    continue
                
                # 일봉 데이터 조회 (request_daily_ohlcv는 KiwoomTrRequest에 있어야 함)
                # 이 부분에서 get_daily_data는 KiwoomTrRequest를 인자로 받습니다.
                df = get_daily_data(worker_kiwoom_tr_request, code)
                
                if df is None or df.empty or len(df) < MIN_DATA_POINTS:
                    continue

                # 기술적 조건 검사
                if is_passing_conditions(df):
                    current_price = df['종가'].iloc[-1]
                    filtered_candidates.append({"ticker": code, "name": name, "price": current_price})
                    logger.info(f"✅ 조건 통과 종목 발견: {name}({code}), 현재가: {current_price:,}")
            except Exception as inner_e:
                logger.warning(f"[{code}] 개별 종목 필터링 중 오류: {inner_e}", exc_info=True)
                continue # 개별 종목 오류는 전체 필터링 중단 없이 건너뜀
        
        return filtered_candidates

    except Exception as e:
        logger.critical(f"❌ 워커 스레드 ({market_code}) 실행 중 치명적인 오류: {e}", exc_info=True)
        return []
    finally:
        # 스레드 종료 시 Kiwoom API 연결 해제 및 COM 객체 해제
        if worker_kiwoom_helper:
            worker_kiwoom_helper.disconnect_kiwoom()
        try:
            pythoncom.CoUninitialize()
        except Exception as e_uninit:
            logger.warning(f"COM CoUninitialize 중 오류 발생: {e_uninit}")

# --- 메인 실행 함수 ---
def run_condition_filter_and_return_df(main_pyqt_app): # main_pyqt_app 인자 추가
    """
    전체 시장에 대해 조건 검색 필터를 멀티스레드로 실행하고 결과를 DataFrame으로 반환합니다.
    이 함수는 메인 스레드에서 호출되며, 각 워커 스레드는 독립적인 Kiwoom API 인스턴스를 생성합니다.
    Args:
        main_pyqt_app (QApplication): 메인 QApplication 인스턴스 (스레드에서 참조용)
    Returns:
        pd.DataFrame: 조건 통과 종목 DataFrame
    """
    logger.info("📊 조건검색 실행 시작 (스레드 기반 필터)...")
    
    global QApplication # QApplication을 글로벌로 선언하여 _run_condition_worker에서 접근 가능하게 함
    from PyQt5.QtWidgets import QApplication 

    all_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONDITION_CHECK_MAX_WORKERS) as executor:
        futures = {
            executor.submit(_run_condition_worker, market_code): market_code
            for market_code in MARKET_CODES
        }

        for future in concurrent.futures.as_completed(futures):
            market_code = futures[future]
            try:
                result = future.result()
                all_results.extend(result)
            except Exception as e:
                logger.error(f"❌ 시장({market_code}) 스레드 작업 실패: {e}", exc_info=True)

    if not all_results:
        logger.info("📭 조건검색 결과: 조건을 만족하는 종목 없음.")
        return pd.DataFrame()

    df_result = pd.DataFrame(all_results, columns=["ticker", "name", "price"])
    logger.info(f"✅ 최종 조건 통과 종목 수: {len(df_result)}개")
    return df_result

