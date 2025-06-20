# C:\Users\user\stock_auto\modules\local_position_manager.py

import os
import pandas as pd
from datetime import datetime
import logging

# ✅ 임포트 경로 수정됨: common 폴더 안의 config
from common.config import POSITIONS_FILE_PATH, POSITION_COLUMNS # POSITION_COLUMNS도 config에 정의되어 있어야 함

logger = logging.getLogger(__name__)

# NOTE: 이 파일은 CSV 기반 로컬 포지션 관리를 담당합니다.
# 실제 키움 API 연동은 modules/Kiwoom/monitor_positions.py가 담당합니다.

def add_position_to_csv(code: str, name: str, buy_price: float, quantity: int):
    """
    새로운 매수 포지션을 positions.csv 파일에 추가합니다.
    - 유효성 검사: buy_price, quantity가 0 이하이면 추가하지 않습니다.
    - 중복 방지: 동일한 ticker가 이미 존재하면 추가하지 않습니다. (공백 제거 후 비교)
    """
    # 1. 데이터 유효성 검사
    if buy_price <= 0 or quantity <= 0:
        logger.warning(f"⚠️ 유효하지 않은 매수 정보입니다. 포지션을 추가하지 않습니다: 종목={name}({code}), 가격={buy_price}, 수량={quantity}")
        return

    path = POSITIONS_FILE_PATH # config에서 경로 가져오기
    today = datetime.today().strftime("%Y-%m-%d")

    new_entry_data = {
        "ticker": code,
        "name": name,
        "buy_price": buy_price,
        "quantity": quantity,
        "buy_date": today,
        "half_exited": False,
        "trail_high": buy_price # 초기 트레일링 하이 값은 매수 가격으로 설정
    }

    # data 디렉토리가 없으면 생성 (config에서 이미 처리하지만, 한 번 더 방어적으로)
    data_dir = os.path.dirname(path)
    try:
        os.makedirs(data_dir, exist_ok=True)
        logger.info(f"💾 데이터 디렉토리 확인/생성 완료: {data_dir}")
    except Exception as e:
        logger.error(f"❌ 데이터 디렉토리 생성 실패: {e}", exc_info=True)
        return

    new_df = pd.DataFrame([new_entry_data])
    
    # 정의된 컬럼 순서에 맞추고, 누락된 컬럼은 None으로 채움
    # POSITION_COLUMNS는 common/config.py에 정의되어 있어야 합니다.
    for col in POSITION_COLUMNS:
        if col not in new_df.columns:
            new_df[col] = None
    new_df = new_df[POSITION_COLUMNS] # 정의된 순서로 정렬

    if os.path.exists(path):
        try:
            existing_df = pd.read_csv(path, encoding="utf-8-sig")
            
            # ✅ 2. 기존 포지션 중복 방지 (동일 종목 코드가 이미 존재하면 추가 방지)
            existing_tickers = existing_df["ticker"].astype(str).str.strip().values
            if code.strip() in existing_tickers:
                logger.warning(f"⚠️ 이미 포지션에 존재하는 종목입니다: {name}({code}). 중복 추가를 방지합니다.")
                return # 함수 종료하여 중복 추가 방지
            
            # 기존 DataFrame도 정의된 컬럼 순서에 맞춤 (유지보수성 향상)
            existing_df = existing_df.reindex(columns=POSITION_COLUMNS, fill_value=None)
            
            df = pd.concat([existing_df, new_df], ignore_index=True)
            logger.info(f"✅ 기존 positions.csv에 새 포지션 추가: {name}({code})")
        except Exception as e:
            logger.error(f"❌ positions.csv 읽기 오류: {e}. 새 파일로 시작합니다.", exc_info=True)
            df = new_df # 오류 발생 시 새 데이터로 시작
    else:
        logger.info(f"🆕 positions.csv 파일이 없습니다. 새 파일로 생성합니다.")
        df = new_df
    
    try:
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info(f"💾 포지션 저장 완료: {name}({code})")
    except Exception as e:
        logger.error(f"❌ positions.csv 쓰기 오류: {e}", exc_info=True)

def load_positions_from_csv(file_path: str) -> pd.DataFrame:
    """
    CSV 파일에서 포지션 데이터를 로드합니다. 파일이 없거나 비어있는 경우,
    또는 새로운 컬럼이 추가된 경우 기본값으로 DataFrame을 초기화합니다.
    """
    # 예상되는 컬럼과 기본 데이터 타입 정의 (POSITION_COLUMNS와 일치해야 함)
    cols = {
        "ticker": str, "name": str, "buy_price": int, "quantity": int,
        "buy_date": str, "half_exited": bool, "trail_high": float
    }

    if not os.path.exists(file_path):
        logger.info(f"📂 포지션 파일 없음: '{file_path}'. 새 DataFrame을 생성합니다.")
        return pd.DataFrame(columns=POSITION_COLUMNS) # config에서 가져온 컬럼 사용

    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        logger.warning(f"⚠️ 포지션 파일 비어있음: '{file_path}'. 빈 DataFrame을 반환합니다.")
        return pd.DataFrame(columns=POSITION_COLUMNS)
    except Exception as e:
        logger.error(f"❌ 포지션 파일 로딩 중 오류 발생: {file_path} - {e}. 빈 DataFrame을 반환합니다.", exc_info=True)
        return pd.DataFrame(columns=POSITION_COLUMNS)

    # 모든 예상 컬럼이 존재하는지 확인하고, 누락된 경우 기본값으로 채웁니다.
    for col in POSITION_COLUMNS: # config에서 가져온 컬럼 순서대로 처리
        if col not in df.columns:
            dtype = cols.get(col, str) # 예상 타입 가져오기
            if dtype == bool:
                df[col] = False
            elif dtype in [int, float]:
                df[col] = 0
            else: # str
                df[col] = ""
            logger.info(f"💡 누락된 컬럼 '{col}'을 추가하고 기본값을 설정했습니다.")
        
        # 데이터 타입을 올바르게 변환합니다. 오류 발생 시 기본값으로 대체합니다.
        dtype = cols.get(col, str)
        if dtype == int:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        elif dtype == float:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
        elif dtype == bool:
            df[col] = df[col].apply(lambda x: str(x).lower() == 'true' or x == '1').fillna(False)
        elif dtype == str:
            df[col] = df[col].fillna("").astype(str)
            
    # 'trail_high' 컬럼이 존재하고 'buy_price' 컬럼이 존재할 경우,
    # 'trail_high'가 NaN이거나 0이면 'buy_price'로 초기화합니다.
    if "trail_high" in df.columns and "buy_price" in df.columns:
        df["trail_high"] = df.apply(
            lambda row: row["buy_price"] if pd.isna(row["trail_high"]) or row["trail_high"] == 0 else row["trail_high"],
            axis=1
        )
    logger.info(f"✅ 포지션 {len(df)}개 로드 완료.")
    return df[POSITION_COLUMNS] # 최종적으로 config에 정의된 순서로 정렬하여 반환

def save_positions_to_csv(df: pd.DataFrame, file_path: str):
    """
    현재 포지션 DataFrame을 CSV 파일로 저장합니다.
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        df.to_csv(file_path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
        logger.info(f"✅ 포지션 {len(df)}개 저장 완료: '{file_path}'")
    except Exception as e:
        logger.error(f"❌ 포지션 저장 중 오류 발생: {file_path} - {e}", exc_info=True)


if __name__ == "__main__":
    # 이 모듈만 단독으로 테스트할 경우를 위한 임시 로깅 설정
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    logger.info("local_position_manager.py 테스트 실행 시작")
    
    # 테스트를 위해 data/positions.csv 파일이 있다면 삭제
    test_path = POSITIONS_FILE_PATH
    if os.path.exists(test_path):
        os.remove(test_path)
        logger.info(f"테스트를 위해 기존 {test_path} 파일 삭제.")

    # 유효한 포지션 추가
    add_position_to_csv("005930", "삼성전자", 75000, 10)
    add_position_to_csv("035420", "네이버", 180000, 5)
    
    # ✅ 유효하지 않은 포지션 추가 시도 (로그 경고 발생 및 저장 안 됨)
    add_position_to_csv("999999", "테스트음수", -100, 5)
    add_position_to_csv("888888", "테스트제로", 10000, 0)
    add_position_to_csv("777777", "테스트모두제로", 0, 0)

    # ✅ 중복 포지션 추가 시도 (로그 경고 발생 및 저장 안 됨)
    add_position_to_csv("005930", "삼성전자", 75500, 12) # 이미 존재하는 삼성전자 ticker
    
    logger.info("local_position_manager.py 테스트 실행 완료")
    # 실행 후 'data/positions.csv' 파일을 확인하여 결과 검증