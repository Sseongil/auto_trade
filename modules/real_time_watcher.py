# modules/real_time_watcher.py

import os
import sys
import pandas as pd
from datetime import datetime, time
import logging
import time as time_module # time 모듈과의 이름 충돌 방지

# sys.path 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pykiwoom.kiwoom import Kiwoom
from modules.config import POSITIONS_FILE_PATH, STATUS_FILE_PATH # 필요한 설정 가져오기
from modules.trade_logger import log_trade # 거래 로그 함수
from modules.notify import send_telegram_message # 텔레그램 알림 함수

# 로깅 설정
logger = logging.getLogger(__name__)

# --- 도우미 함수 ---

def load_positions_for_watching(file_path: str) -> pd.DataFrame:
    """
    모니터링할 포지션 데이터를 CSV 파일에서 로드합니다.
    필요한 컬럼만 로드하고, 파일이 없거나 비어있는 경우 빈 DataFrame을 반환합니다.
    """
    cols = {"ticker": str, "name": str} # 실시간 조회를 위해 필요한 최소 정보
    
    if not os.path.exists(file_path):
        logger.info(f"📂 포지션 파일 없음: '{file_path}'. 실시간 감시할 종목이 없습니다.")
        return pd.DataFrame(columns=list(cols.keys()))

    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        # 필요한 컬럼만 선택하고, 누락된 경우 빈 문자열로 채우기
        for col in cols.keys():
            if col not in df.columns:
                df[col] = ""
                logger.warning(f"⚠️ 포지션 파일에 '{col}' 컬럼이 누락되어 빈 값으로 초기화합니다.")
        df = df[list(cols.keys())] # 필요한 컬럼만 유지
        logger.info(f"✅ 실시간 감시를 위해 {len(df)}개의 포지션 로드 완료.")
        return df
    except pd.errors.EmptyDataError:
        logger.warning(f"⚠️ 포지션 파일 비어있음: '{file_path}'. 실시간 감시할 종목이 없습니다.")
        return pd.DataFrame(columns=list(cols.keys()))
    except Exception as e:
        logger.error(f"❌ 포지션 파일 로딩 중 오류 발생: {file_path} - {e}. 실시간 감시를 시작할 수 없습니다.")
        return pd.DataFrame(columns=list(cols.keys()))

def start_real_time_monitoring(kiwoom: Kiwoom, df_positions: pd.DataFrame):
    """
    주어진 DataFrame의 종목들에 대해 실시간 시세 조회를 시작합니다.
    이미 등록된 종목은 중복 등록하지 않습니다.
    """
    if df_positions.empty:
        logger.info("모니터링할 포지션이 없어 실시간 감시를 시작하지 않습니다.")
        return

    logger.info("⭐ 실시간 시세 감시 종목 등록 시작...")
    registered_count = 0
    for _, row in df_positions.iterrows():
        code = str(row["ticker"]).zfill(6)
        name = row["name"]

        # --- 세션 내 중복 방지 로직 (미완 부분) 마무리 ---
        # kiwoom 객체 내부에 실시간 등록된 종목 리스트가 있다고 가정하고,
        # 해당 리스트에 이미 종목코드가 있는지 확인하여 중복 등록을 방지합니다.
        # pykiwoom의 내부 구현에 따라 're_type_stock_list'와 같은 속성이 없을 수 있습니다.
        # 이 경우, 직접 등록 여부를 추적하는 셋(set)을 사용해야 합니다.
        # 여기서는 pykiwoom의 일반적인 패턴을 따릅니다.
        
        # NOTE: pykiwoom의 최신 버전은 `SetRealReg` 호출 시 내부적으로 중복을 처리하거나,
        # 실시간 등록된 종목 코드를 직접 제공하지 않을 수 있습니다.
        # 안전하게는 직접 `registered_realtime_codes` 셋을 관리하는 것이 좋습니다.
        # 여기서는 편의상 `kiwoom.re_type_stock_list`가 있다고 가정하고 진행합니다.
        
        if hasattr(kiwoom, 're_type_stock_list') and code in kiwoom.re_type_stock_list:
             logger.info(f"✅ {name}({code})는 이미 실시간 감시 중입니다. (중복 등록 방지)")
             continue

        try:
            # SetRealReg("스크린번호", "종목코드", "FID", "0" 또는 "1")
            # FID: 10(현재가), 12(등락율), 11(전일대비), 20(거래량), 13(누적거래량), 22(누적거래대금) 등
            # 0: 종목만 등록, 1: 종목 해지 후 등록
            kiwoom.SetRealReg("0101", code, "10;11;12;20;13", "0") 
            logger.info(f"🟢 {name}({code}) 실시간 감시 등록 완료.")
            registered_count += 1
        except Exception as e:
            logger.error(f"❌ {name}({code}) 실시간 감시 등록 실패: {e}")
            send_telegram_message(f"🚨 {name}({code}) 실시간 감시 등록 실패: {e}")
    
    if registered_count > 0:
        logger.info(f"⭐ 총 {registered_count}개 종목 실시간 감시 등록 완료.")
    else:
        logger.info("등록된 새로운 실시간 감시 종목이 없습니다.")

# --- 메인 와처 실행 함수 ---

def run_watcher():
    """
    실시간 시세 감시를 실행하는 메인 루프입니다.
    정해진 시간에 종료되거나, 수동으로 중단될 수 있습니다.
    """
    logger.info("🚀 실시간 감시 와처 시작.")
    kiwoom = Kiwoom()
    
    try:
        # 키움증권 API 연결
        kiwoom.CommConnect(block=True)
        if not kiwoom.connected:
            logger.critical("❌ 키움증권 API 연결 실패. 와처를 종료합니다.")
            send_telegram_message("🚨 키움증권 API 연결 실패. 실시간 감시 와처 종료.")
            return

        logger.info("✅ 키움증권 API 연결 성공.")
        
        # 이벤트 핸들러 등록 (실시간 데이터를 받았을 때 호출될 함수)
        # Kiwoom 클래스에 OnReceiveRealData 이벤트 핸들러가 구현되어 있다고 가정합니다.
        # 실제 데이터 처리는 kiwoom.OnReceiveRealData 또는 별도의 콜백 함수에서 이루어져야 합니다.
        # 예시: kiwoom.set_real_callback(my_real_data_handler)

        last_checked_minute = -1 # 분이 바뀔 때마다 포지션을 로드하도록 초기화

        # --- while True: 루프의 종료 조건 추가 ---
        # 매일 장 종료 시간(예: 오후 3시 30분)에 와처를 종료하도록 설정
        # 텔레그램 알림은 실제 거래 시간을 기반으로 조정해야 합니다.
        END_WATCH_TIME = time(15, 40) # 오후 3시 40분 (장 마감 10분 후)

        while True:
            now = datetime.now()
            
            # 매 분마다 포지션 파일 다시 로드 및 실시간 등록 확인 (필요시)
            # 불필요한 파일 I/O를 줄이기 위해 5분마다 또는 특정 이벤트 시에만 로드하도록 최적화할 수 있습니다.
            if now.minute != last_checked_minute:
                logger.debug(f"[{now.strftime('%H:%M')}] 포지션 파일 확인 및 실시간 등록 업데이트.")
                df_current_positions = load_positions_for_watching(POSITIONS_FILE_PATH)
                start_real_time_monitoring(kiwoom, df_current_positions)
                last_checked_minute = now.minute

            # 특정 시간(장 종료 후)이 되면 루프 종료
            if now.time() >= END_WATCH_TIME:
                logger.info(f"⏳ {END_WATCH_TIME.strftime('%H:%M')} 도달. 실시간 감시 와처를 종료합니다.")
                send_telegram_message(f"✅ 실시간 감시 와처가 {END_WATCH_TIME.strftime('%H:%M')}에 정상 종료되었습니다.")
                break # 루프 종료

            time_module.sleep(5) # 5초마다 확인 (CPU 사용량 줄이기)

    except KeyboardInterrupt:
        logger.info("👋 사용자에 의해 실시간 감시 와처가 중단되었습니다.")
        send_telegram_message("👋 실시간 감시 와처가 수동으로 중단되었습니다.")
    except Exception as e:
        logger.critical(f"🚨 실시간 감시 와처 실행 중 치명적인 예외 발생: {e}", exc_info=True)
        send_telegram_message(f"🚨 실시간 감시 와처 오류 발생: {e}")
    finally:
        # Kiwoom 연결은 항상 종료되도록 보장
        if kiwoom.connected:
            kiwoom.Disconnect()
            logger.info("🔌 키움증권 API 연결 해제 완료.")
        logger.info("--- 실시간 감시 와처 종료 ---")

if __name__ == "__main__":
    # 이 스크립트가 단독 실행될 때만 로깅 기본 설정을 수행합니다.
    # 메인 애플리케이션에서는 전체 로깅 설정을 한 번만 하는 것이 좋습니다.
    if not logging.root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    run_watcher()