# modules/monitor_positions.py (UPDATED FULL CODE)

import os
import sys
import pandas as pd
from datetime import datetime
import logging

# --- 필수 수정 1: __file__ 오타 수정 및 경로 설정 ---
# 현재 파일의 디렉토리를 sys.path에 추가하여 모듈을 올바르게 임포트할 수 있도록 합니다.
# 이 설정은 프로젝트 구조에 따라 필요하며, IDE나 실행 환경에 따라 다를 수 있습니다.
# 예를 들어, modules/monitor_positions.py에서 modules/notify.py를 임포트하려면
# modules/ 디렉토리가 sys.path에 있어야 합니다.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from pykiwoom.kiwoom import Kiwoom
from modules.notify import send_telegram_message # notify.py 모듈이 존재해야 합니다.
from modules.trade_logger import log_trade       # trade_logger.py 모듈이 존재해야 합니다.
from modules.config import (
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_STOP_PCT, MAX_HOLD_DAYS,
    POSITIONS_FILE_PATH, DEFAULT_LOT_SIZE
)

# --- 로깅 설정 ---
logger = logging.getLogger(__name__)
if not logger.handlers: # Avoid re-adding handlers if basicConfig is called elsewhere (e.g., in run_all.py)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# --- 도우미 함수 ---

# Kiwoom 응답 코드에 대한 간단한 설명 맵 (선택 개선 3 관련)
KIWOOM_ERROR_CODES = {
    0: "정상 처리",
    -10: "미접속",
    -100: "계좌정보 없음",
    -101: "계좌 비밀번호 없음",
    -102: "비정상적인 모듈 호출",
    -103: "종목코드 없음",
    -104: "계좌증거금율 오류",
    -105: "조건 검색 오류",
    -106: "조건 검색 미신청",
    -107: "사용자 정보 없음",
    -108: "주문 가격 오류",
    -109: "주문 수량 오류",
    -110: "실시간 등록 오류",
    -111: "실시간 해제 오류",
    -112: "데이터 없음",
    -113: "API 미설정",
    -114: "알 수 없는 오류",
    # 필요에 따라 더 많은 코드와 설명을 추가할 수 있습니다.
}

def get_current_price(kiwoom_instance: Kiwoom, code: str) -> int:
    """
    주식 코드에 대한 현재 가격을 Kiwoom API를 통해 조회합니다 (opt10001 사용).

    Args:
        kiwoom_instance (Kiwoom): 초기화되고 연결된 Kiwoom 객체.
        code (str): 종목 코드 (예: "005930").

    Returns:
        int: 조회된 현재가. 조회 실패 시 0을 반환합니다.
    """
    try:
        price_data = kiwoom_instance.block_request(
            "opt10001",
            종목코드=code,
            output="주식기본정보",
            next=0
        )
        if price_data is None or price_data.empty or '현재가' not in price_data:
            logger.warning(f"⚠️ 현재가 데이터 없음: {code}. 빈 DataFrame 또는 '현재가' 컬럼 누락.")
            return 0
        
        # '현재가' 데이터에서 쉼표, +,- 기호를 제거하고 공백을 없앤 후 정수로 변환
        raw_price = str(price_data['현재가'].iloc[0]).replace(",", "").replace("+", "").replace("-", "").strip()
        
        # 숫자인지 확인 후 변환, 아니면 0 반환
        return int(raw_price) if raw_price.isdigit() else 0
    except Exception as e:
        logger.error(f"❌ 현재가 조회 실패: {code} - {e}", exc_info=True) # Stack trace 추가
        return 0

def load_positions(file_path: str) -> pd.DataFrame:
    """
    CSV 파일에서 포지션 데이터를 로드합니다. 파일이 없거나 비어있는 경우,
    또는 새로운 컬럼이 추가된 경우 기본값으로 DataFrame을 초기화합니다.

    Args:
        file_path (str): 포지션 CSV 파일 경로.

    Returns:
        pd.DataFrame: 로드된 포지션을 포함하는 DataFrame.
    """
    # 예상되는 컬럼과 기본 데이터 타입 정의
    cols = {
        "ticker": str, "name": str, "buy_price": int, "quantity": int,
        "buy_date": str, "half_exited": bool, "trail_high": float
    }

    if not os.path.exists(file_path):
        logger.info(f"📂 포지션 파일 없음: '{file_path}'. 새 DataFrame을 생성합니다.")
        return pd.DataFrame(columns=list(cols.keys()))

    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        logger.warning(f"⚠️ 포지션 파일 비어있음: '{file_path}'. 빈 DataFrame을 반환합니다.")
        return pd.DataFrame(columns=list(cols.keys()))
    except Exception as e:
        logger.error(f"❌ 포지션 파일 로딩 중 오류 발생: {file_path} - {e}. 빈 DataFrame을 반환합니다.", exc_info=True)
        return pd.DataFrame(columns=list(cols.keys()))

    # 모든 예상 컬럼이 존재하는지 확인하고, 누락된 경우 기본값으로 채웁니다.
    for col, dtype in cols.items():
        if col not in df.columns:
            if dtype == bool:
                df[col] = False
            elif dtype in [int, float]:
                df[col] = 0
            else: # str
                df[col] = ""
            logger.info(f"💡 누락된 컬럼 '{col}'을 추가하고 기본값을 설정했습니다.")
        
        # 데이터 타입을 올바르게 변환합니다. 오류 발생 시 기본값으로 대체합니다.
        if dtype == int:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        elif dtype == float:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
        elif dtype == bool:
            # 문자열 "True", 1, True 등은 True로, 나머지는 False로 변환
            df[col] = df[col].apply(lambda x: str(x).lower() == 'true' or x == '1').fillna(False) # '1' 문자열도 인식하도록
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
    return df

def save_positions(df: pd.DataFrame, file_path: str):
    """
    현재 포지션 DataFrame을 CSV 파일로 저장합니다.

    Args:
        df (pd.DataFrame): 포지션을 포함하는 DataFrame.
        file_path (str): 포지션 CSV 파일 경로.
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True) # 디렉토리가 없으면 생성
        # CSV 저장 시 날짜 형식 일관성을 위해 date_format 지정
        df.to_csv(file_path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
        logger.info(f"✅ 포지션 {len(df)}개 저장 완료: '{file_path}'")
    except Exception as e:
        logger.error(f"❌ 포지션 저장 중 오류 발생: {file_path} - {e}", exc_info=True)

# --- 메인 모니터링 로직 ---

def monitor_positions():
    """
    보유 중인 주식 포지션을 모니터링하고, 설정된 전략(손절, 익절, 트레일링 스탑, 최대 보유일)에 따라
    매도 주문을 실행합니다.
    """
    logger.info("🚀 포지션 모니터링 시작")

    kiwoom = Kiwoom()
    try:
        kiwoom.CommConnect(block=True)
        if not kiwoom.connected:
            logger.critical("❌ 키움증권 API 연결 실패. 모니터링을 중단합니다.")
            send_telegram_message("🚨 키움 API 연결 실패. 포지션 모니터링 중단.")
            return
        logger.info("✅ 키움증권 API 연결 성공.")
        account = kiwoom.GetLoginInfo("ACCNO")[0] # 연결된 계좌 번호 가져오기
        logger.info(f"💰 로그인 계좌: {account}")

        df_positions = load_positions(POSITIONS_FILE_PATH) # 포지션 데이터 로드
        if df_positions.empty:
            logger.info("📂 모니터링할 포지션이 없습니다.")
            return # 모니터링할 포지션이 없으면 종료

        updated_positions_list = [] # 처리 후 남은 포지션들을 저장할 리스트

        for idx, row in df_positions.iterrows(): # idx도 함께 가져옴 (나중에 필요할 수 있으므로)
            # 각 포지션의 정보 추출 및 초기화
            code = str(row["ticker"]).zfill(6)
            name = row["name"]
            buy_price = row["buy_price"]
            quantity = int(row["quantity"])
            trail_high = float(row["trail_high"])
            half_exited = bool(row["half_exited"])
            
            # DataFrame row를 딕셔너리로 변환하여 수정할 수 있도록 합니다.
            # to_dict() 호출 시 copy=True를 명시하여 원본 DataFrame의 row에 영향을 주지 않도록 합니다.
            current_row_dict = row.to_dict() # 수정된 부분: .copy() 대신 to_dict() 사용

            # 매수일자 처리 및 보유일 계산
            try:
                # buy_date가 datetime 객체가 아닐 수 있으므로 str()로 변환 후 파싱
                buy_date = datetime.strptime(str(row["buy_date"]), "%Y-%m-%d")
                hold_days = (datetime.today() - buy_date).days
            except ValueError as e:
                logger.warning(f"❌ 날짜 형식 오류: {name}({code}) - buy_date: '{row['buy_date']}' - {e}. 해당 포지션은 건너뛰고 다음 주기에 다시 확인합니다.")
                updated_positions_list.append(current_row_dict) # 오류 있는 포지션은 그대로 유지
                continue # 다음 포지션으로 넘어감

            # 수량이 0이거나 유효하지 않은 경우 로그 기록 후 건너뛰기
            if quantity <= 0:
                logger.info(f"정보: {name}({code}) - 수량 0. 포지션 목록에서 제거합니다.")
                # log_trade 함수 호출 방식 변경: quantity와 trade_type 추가
                log_trade(code, name, 0, 0, "ZERO_QUANTITY_REMOVE", None) # price 0, pnl None
                continue # 다음 포지션으로 넘어감

            # 현재가 조회
            current_price = get_current_price(kiwoom, code)
            if current_price == 0:
                logger.warning(f"경고: {name}({code}) 현재가 조회 실패. 이 종목은 다음 모니터링 주기에 다시 확인합니다.")
                updated_positions_list.append(current_row_dict) # 조회 실패 시 포지션 유지
                continue # 다음 포지션으로 넘어감

            # 수익률 계산 (매수가 0인 경우 ZeroDivisionError 방지)
            pnl_pct = (current_price - buy_price) / buy_price * 100 if buy_price != 0 else 0

            logger.info(f"🔍 {name}({code}) | 현재가: {current_price:,}원, 수익률: {pnl_pct:.2f}%, 보유일: {hold_days}일, 추적고점: {trail_high:,}원")

            action_taken = False # 이번 반복에서 매도 액션이 발생했는지 추적

            # 1. 손절 조건 검사 (최우선 순위)
            if pnl_pct <= STOP_LOSS_PCT:
                logger.warning(f"❌ 손절 조건 충족: {name}({code}) 수익률 {pnl_pct:.2f}% (기준: {STOP_LOSS_PCT:.2f}%)")
                order_quantity = quantity # 전체 물량 매도
                if order_quantity > 0:
                    r = kiwoom.SendOrder("손절매도", "0101", account, 2, code, order_quantity, 0, "03", "") # 시장가 매도
                    if r == 0: # 주문 성공 시
                        send_telegram_message(f"❌ 손절: {name}({code}) | 수익률: {pnl_pct:.2f}% | 수량: {order_quantity}주")
                        # log_trade 함수 호출 방식 변경: quantity와 trade_type 추가
                        log_trade(code, name, current_price, order_quantity, "STOP_LOSS", pnl_pct)
                        action_taken = True
                    else: # 주문 실패 시
                        error_msg = KIWOOM_ERROR_CODES.get(r, "알 수 없는 오류")
                        logger.error(f"🔴 손절 주문 실패: {name}({code}) 응답코드 {r} ({error_msg})")
                else:
                    logger.warning(f"경고: {name}({code}) 손절 매도 수량 0주. (총 수량: {quantity}주)")
            
            # 매도 액션이 발생하지 않았을 경우에만 다음 조건들을 검사
            if not action_taken:
                # 2. 50% 익절 조건 검사
                if not half_exited and pnl_pct >= TAKE_PROFIT_PCT:
                    logger.info(f"🎯 50% 익절 조건 충족: {name}({code}) 수익률 {pnl_pct:.2f}% (기준: {TAKE_PROFIT_PCT:.2f}%)")
                    # 전체 수량의 절반을 기본 거래 단위에 맞춰 계산
                    half_qty = (quantity // 2 // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE
                    
                    if half_qty > 0:
                        r = kiwoom.SendOrder("익절매도(50%)", "0101", account, 2, code, half_qty, 0, "03", "") # 시장가 매도
                        if r == 0: # 주문 성공 시
                            send_telegram_message(f"🎯 50% 익절: {name}({code}) | 수익률: {pnl_pct:.2f}% | 수량: {half_qty}주")
                            # log_trade 함수 호출 방식 변경: quantity와 trade_type 추가
                            log_trade(code, name, current_price, half_qty, "TAKE_PROFIT_50", pnl_pct)
                            
                            # 포지션 데이터 업데이트: 남은 수량, half_exited 플래그, 추적 고점
                            current_row_dict["quantity"] -= half_qty
                            current_row_dict["half_exited"] = True
                            current_row_dict["trail_high"] = current_price
                            logger.info(f"업데이트: {name}({code}) 남은 수량: {current_row_dict['quantity']}주, 추적고점: {current_row_dict['trail_high']:,}원")
                            action_taken = True
                        else: # 주문 실패 시
                            error_msg = KIWOOM_ERROR_CODES.get(r, "알 수 없는 오류")
                            logger.error(f"🔴 50% 익절 주문 실패: {name}({code}) 응답코드 {r} ({error_msg})")
                    else:
                        logger.warning(f"경고: {name}({code}) 50% 익절을 위한 최소 수량({DEFAULT_LOT_SIZE}주) 부족. 현재 수량: {quantity}주.")
            
            # 매도 액션이 발생하지 않았고, 이미 50% 익절이 된 상태에서 다음 조건 검사
            if not action_taken and half_exited:
                # 3. 트레일링 스탑 조건 검사
                if current_price > trail_high:
                    # 현재가가 추적 고점보다 높으면 고점 업데이트
                    current_row_dict["trail_high"] = current_price
                    logger.debug(f"추적고점 업데이트: {name}({code}) -> {current_row_dict['trail_high']:,}원")
                elif current_price <= trail_high * (1 - TRAIL_STOP_PCT / 100):
                    logger.warning(f"📉 트레일링 스탑 조건 충족: {name}({code}) 현재가 {current_price}원, 추적고점 {trail_high}원 (하락률: {((trail_high - current_price)/trail_high*100):.2f}%)")
                    order_quantity = quantity # 남은 전체 물량 매도
                    if order_quantity > 0:
                        pnl_on_exit = (current_price - buy_price) / buy_price * 100 # 청산 시점 수익률
                        r = kiwoom.SendOrder("트레일링익절", "0101", account, 2, code, order_quantity, 0, "03", "") # 시장가 매도
                        if r == 0: # 주문 성공 시
                            send_telegram_message(f"📉 트레일링 스탑: {name}({code}) | 수익률: {pnl_on_exit:.2f}% | 수량: {order_quantity}주")
                            # log_trade 함수 호출 방식 변경: quantity와 trade_type 추가
                            log_trade(code, name, current_price, order_quantity, "TRAILING_STOP", pnl_on_exit)
                            action_taken = True
                        else: # 주문 실패 시
                            error_msg = KIWOOM_ERROR_CODES.get(r, "알 수 없는 오류")
                            logger.error(f"🔴 트레일링 스탑 주문 실패: {name}({code}) 응답코드 {r} ({error_msg})")
                    else:
                        logger.warning(f"경고: {name}({code}) 트레일링 스탑 매도 수량 0주. (총 수량: {quantity}주)")

            # 매도 액션이 발생하지 않았을 경우에만 다음 조건 검사
            if not action_taken:
                # 4. 최대 보유일 초과 조건 검사 (가장 낮은 순위)
                if hold_days >= MAX_HOLD_DAYS:
                    logger.info(f"⌛ 보유일 초과 조건 충족: {name}({code}) 보유일 {hold_days}일 (기준: {MAX_HOLD_DAYS}일)")
                    order_quantity = quantity # 남은 전체 물량 매도
                    if order_quantity > 0:
                        pnl_on_exit = (current_price - buy_price) / buy_price * 100 # 청산 시점 수익률
                        r = kiwoom.SendOrder("보유종료매도", "0101", account, 2, code, order_quantity, 0, "03", "") # 시장가 매도
                        if r == 0: # 주문 성공 시
                            send_telegram_message(f"⌛ 보유일 초과 청산: {name}({code}) | 수익률: {pnl_on_exit:.2f}% | 수량: {order_quantity}주")
                            # log_trade 함수 호출 방식 변경: quantity와 trade_type 추가
                            log_trade(code, name, current_price, order_quantity, "MAX_HOLD_DAYS_SELL", pnl_on_exit)
                            action_taken = True
                        else: # 주문 실패 시
                            error_msg = KIWOOM_ERROR_CODES.get(r, "알 수 없는 오류")
                            logger.error(f"🔴 보유일 초과 청산 주문 실패: {name}({code}) 응답코드 {r} ({error_msg})")
                    else:
                        logger.warning(f"경고: {name}({code}) 보유일 초과 매도 수량 0주. (총 수량: {quantity}주)")

            # 처리된 포지션 업데이트 (매도되지 않았거나 부분 매도된 경우)
            # action_taken이 True이고 남은 수량이 0이면 포지션에서 제거 (즉, updated_positions_list에 추가하지 않음)
            # 그렇지 않으면 (액션이 없었거나, 액션이 있었지만 남은 수량이 있는 경우) 리스트에 추가
            if not action_taken or (action_taken and current_row_dict["quantity"] > 0):
                updated_positions_list.append(current_row_dict)

        # 모든 포지션 처리 후 업데이트된 DataFrame을 저장
        new_df_positions = pd.DataFrame(updated_positions_list, columns=df_positions.columns)
        save_positions(new_df_positions, POSITIONS_FILE_PATH)

    except Exception as e:
        logger.critical(f"🚨 모니터링 중 치명적인 예외 발생: {e}", exc_info=True) # exc_info=True로 스택 트레이스 출력
        send_telegram_message(f"🚨 포지션 모니터링 중 치명적 오류: {e}")
    finally:
        # Kiwoom 연결은 항상 종료되도록 보장
        if 'kiwoom' in locals() and kiwoom.connected: # kiwoom 객체가 생성되었고 연결된 경우에만 disconnect
            kiwoom.Disconnect()
        logger.info("--- 포지션 모니터링 종료 ---")

if __name__ == "__main__":
    # 이 부분이 monitor_positions.py를 단독 실행할 때 로깅을 설정합니다.
    # 만약 이 모듈이 다른 메인 스크립트(예: run_all.py)에 의해 임포트되어 실행된다면,
    # 메인 스크립트에서 logging.basicConfig를 한 번만 설정하는 것이 좋습니다.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    # logger = logging.getLogger(__name__) # __name__으로 logger를 다시 가져옴 (선택 사항)
    monitor_positions()