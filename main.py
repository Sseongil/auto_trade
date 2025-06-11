import sys
import os
import pandas as pd
from datetime import datetime
import logging # logging 모듈 임포트

# 로깅 설정 (main.py 자체의 로깅)
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 경로 보정
# 현재 스크립트 파일이 있는 디렉토리를 Python Path에 추가하고, 작업 디렉토리를 변경
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)
os.chdir(script_dir) # 현재 작업 디렉토리 변경

# modules 디렉토리 안에 있다고 가정
from modules.check_conditions import filter_all_stocks
from modules.backtest import run_backtest

def main():
    today = datetime.today().strftime("%Y%m%d")
    save_dir = os.path.join("data", today) # 현재 작업 디렉토리 기준 data/YYYYMMDD

    # save_dir 생성 (main.py에서도 필요)
    try:
        os.makedirs(save_dir, exist_ok=True)
        logger.info(f"💾 결과 저장 디렉토리 확인/생성 완료: {save_dir}")
    except Exception as e:
        logger.error(f"❌ 결과 저장 디렉토리 생성 실패: {e}", exc_info=True)
        return # 디렉토리 생성 실패 시 함수 종료

    # ✅ 1. 조건 검색 실행
    logger.info("[1] 조건 검색 실행 중...")
    try:
        filtered = filter_all_stocks()
    except Exception as e:
        logger.error(f"❌ 조건 검색 실행 중 오류 발생: {e}", exc_info=True)
        return

    if filtered is None or filtered.empty:
        logger.warning(" ❌ 조건을 만족하는 종목이 없습니다. 백테스트를 수행하지 않습니다.")
        return

    buy_list_path = os.path.join(save_dir, f"buy_list_{today}.csv")
    try:
        filtered.to_csv(buy_list_path, index=False, encoding="utf-8-sig")
        logger.info(f"[2] 필터링 완료 - 종목 수: {len(filtered)}, 파일 저장됨: {buy_list_path}")
        logger.info("필터링된 종목 상위 5개:\n" + str(filtered.head()))
    except Exception as e:
        logger.error(f"❌ 필터링 결과 저장 실패: {e}", exc_info=True)
        return

    # ✅ 3. 백테스트 수행
    logger.info("[3] 백테스트 수행 중...")
    try:
        backtest_result = run_backtest(buy_list_path)
    except Exception as e:
        logger.error(f"❌ 백테스트 실행 중 오류 발생: {e}", exc_info=True)
        backtest_result = None # 오류 발생 시 결과 없음으로 처리

    backtest_path = os.path.join(save_dir, f"backtest_result_{today}.csv")

    if backtest_result is not None:
        try:
            backtest_result.to_csv(backtest_path, index=False, encoding="utf-8-sig")
            logger.info(f"[4] 백테스트 완료 - 결과 파일 저장됨: {backtest_path}")
        except Exception as e:
            logger.error(f"❌ 백테스트 결과 저장 실패: {e}", exc_info=True)
    else:
        logger.warning(" ❌ 백테스트 실패 또는 결과 없음")

if __name__ == "__main__":
    main()