import os
import pandas as pd
from datetime import datetime
import logging
from modules.config import POSITION_COLUMNS

# ✅ 로깅 설정은 메인 진입점에서 담당하므로, 여기서는 로거 인스턴스만 가져옵니다.
logger = logging.getLogger(__name__)


def add_position(code: str, name: str, buy_price: float, quantity: int):
    """
    새로운 매수 포지션을 positions.csv 파일에 추가합니다.
    - 유효성 검사: buy_price, quantity가 0 이하이면 추가하지 않습니다.
    - 중복 방지: 동일한 ticker가 이미 존재하면 추가하지 않습니다. (공백 제거 후 비교)
    """
    # 1. 데이터 유효성 검사
    if buy_price <= 0 or quantity <= 0:
        logger.warning(f"⚠️ 유효하지 않은 매수 정보입니다. 포지션을 추가하지 않습니다: 종목={name}({code}), 가격={buy_price}, 수량={quantity}")
        return

    path = os.path.join("data", "positions.csv")
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

    # data 디렉토리가 없으면 생성
    data_dir = os.path.dirname(path)
    try:
        os.makedirs(data_dir, exist_ok=True)
        logger.info(f"💾 데이터 디렉토리 확인/생성 완료: {data_dir}")
    except Exception as e:
        logger.error(f"❌ 데이터 디렉토리 생성 실패: {e}", exc_info=True)
        return

    new_df = pd.DataFrame([new_entry_data])
    
    # 정의된 컬럼 순서에 맞추고, 누락된 컬럼은 None으로 채움
    for col in POSITION_COLUMNS:
        if col not in new_df.columns:
            new_df[col] = None
    new_df = new_df[POSITION_COLUMNS] # 정의된 순서로 정렬

    if os.path.exists(path):
        try:
            existing_df = pd.read_csv(path, encoding="utf-8-sig")
            
            # ✅ 2. 기존 포지션 중복 방지 (동일 종목 코드가 이미 존재하면 추가 방지)
            # ticker 컬럼을 문자열로 변환 후 공백 제거하여 비교 안정성 강화
            existing_tickers = existing_df["ticker"].astype(str).str.strip().values
            # 입력된 code도 공백 제거
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

# 테스트 코드 (모듈 단독 실행 시) - 이 부분은 로깅 설정을 메인 진입점에서 하므로,
# 실제 애플리케이션 실행 시에는 main.py나 server.py에서 로깅이 설정됩니다.
# 이 스크립트를 단독 실행할 경우 로깅 메시지가 콘솔에 출력되지 않을 수 있습니다.
# 단독 테스트 시에는 아래와 같이 basicConfig를 추가해줄 수 있습니다.
if __name__ == "__main__":
    # 이 모듈만 단독으로 테스트할 경우를 위한 임시 로깅 설정
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    logger.info("trade_manager.py 테스트 실행 시작")
    
    # 테스트를 위해 data/positions.csv 파일이 있다면 삭제
    test_path = os.path.join("data", "positions.csv")
    if os.path.exists(test_path):
        os.remove(test_path)
        logger.info(f"테스트를 위해 기존 {test_path} 파일 삭제.")

    # 유효한 포지션 추가
    add_position("005930", "삼성전자", 75000, 10)
    add_position("035420", "네이버", 180000, 5)
    
    # ✅ 유효하지 않은 포지션 추가 시도 (로그 경고 발생 및 저장 안 됨)
    add_position("999999", "테스트음수", -100, 5)
    add_position("888888", "테스트제로", 10000, 0)
    add_position("777777", "테스트모두제로", 0, 0)

    # ✅ 중복 포지션 추가 시도 (로그 경고 발생 및 저장 안 됨)
    add_position("005930", "삼성전자", 75500, 12) # 이미 존재하는 삼성전자 ticker
    
    logger.info("trade_manager.py 테스트 실행 완료")
    # 실행 후 'data/positions.csv' 파일을 확인하여 결과 검증