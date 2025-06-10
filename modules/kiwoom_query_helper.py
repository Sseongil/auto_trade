# modules/kiwoom_query_helper.py (수정된 부분)

import sys
import os
import pandas as pd
import logging
from datetime import datetime
from dotenv import load_dotenv # 이 줄을 추가합니다.

# --- 환경 변수 로드 ---
# 프로젝트 루트에서 .env 파일을 로드하도록 경로를 지정합니다.
# 현재 모듈 파일 위치(__file__)에서 상위 디렉토리(..)를 한 번 더 올라가서 (../..) 프로젝트 루트를 찾습니다.
# 만약 run_all.py나 server.py가 modules/ 디렉토리 밖에 있다면, os.path.dirname(__file__)에서
# 상위 디렉토리를 두 번 (..) 올라가야 프로젝트 루트를 찾을 수 있습니다.
# 이 경로 설정은 프로젝트의 실제 구조에 따라 다릅니다.
# 가장 확실한 방법은 server.py나 run_all.py 같은 메인 진입점에서 load_dotenv()를 호출하는 것입니다.
# 여기서는 헬퍼에서 호출하지만, 실제로는 메인 스크립트에서 한 번만 호출하는 것이 좋습니다.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env'))


# sys.path 설정 (모듈을 찾을 수 있도록)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pykiwoom.kiwoom import Kiwoom
from modules.config import POSITIONS_FILE_PATH, DEFAULT_LOT_SIZE # 필요한 경우 가져오기
from modules.notify import send_telegram_message # 에러 발생 시 텔레그램 알림용

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    """
    Kiwoom API를 사용하여 계좌 및 보유 종목 정보를 조회하는 헬퍼 클래스.
    웹훅 환경에서는 연결을 유지하기보다 필요 시마다 연결/조회/해제하는 것이 효율적일 수 있습니다.
    """
    def __init__(self):
        self.kiwoom = Kiwoom()
        self.account_password = os.getenv("KIWOOM_ACCOUNT_PASSWORD") # 환경 변수에서 비밀번호 로드
        self.account_number = os.getenv("KIWOOM_ACCOUNT_NUMBER") # 환경 변수에서 계좌 번호 로드 (선택 사항)

        if not self.account_password:
            logger.critical("🚨 환경 변수 'KIWOOM_ACCOUNT_PASSWORD'가 설정되지 않았습니다!")
            send_telegram_message("❌ [오류] Kiwoom 비밀번호가 설정되지 않았습니다.")
            # 필요에 따라 프로그램 종료 또는 기본값 설정
            raise ValueError("KIWOOM_ACCOUNT_PASSWORD 환경 변수 필요")

        # account_number가 .env에 없으면 Kiwoom.GetLoginInfo에서 가져오도록 기존 로직 유지
        if not self.account_number:
            logger.warning("⚠️ 환경 변수 'KIWOOM_ACCOUNT_NUMBER'가 설정되지 않아, Kiwoom API에서 계좌 정보를 가져옵니다.")


    def _connect_kiwoom(self) -> bool:
        """Kiwoom API에 연결하고 계좌 정보를 가져옵니다."""
        if self.kiwoom.connected:
            return True # 이미 연결되어 있으면 다시 연결하지 않음

        try:
            self.kiwoom.CommConnect(block=True)
            if not self.kiwoom.connected:
                logger.error("❌ Kiwoom API 연결 실패")
                send_telegram_message("❌ 키움 API 연결 실패 (조회 기능)")
                return False

            if not self.account_number: # .env에 계좌 번호가 없었다면 API에서 가져옴
                accounts = self.kiwoom.GetLoginInfo("ACCNO")
                if not accounts:
                    logger.error("❌ Kiwoom 계좌 정보 없음")
                    send_telegram_message("❌ 키움 계좌 정보 없음 (조회 기능)")
                    return False
                self.account_number = accounts[0].strip()
            
            logger.info(f"✅ Kiwoom API 연결 및 계좌 ({self.account_number}) 확인 완료.")
            return True
        except Exception as e:
            logger.error(f"❌ Kiwoom 연결 또는 계좌 정보 조회 중 오류: {e}", exc_info=True)
            send_telegram_message(f"❌ 키움 연결/계좌 조회 오류: {e}")
            return False

    def _disconnect_kiwoom(self):
        """Kiwoom API 연결을 해제합니다."""
        if self.kiwoom.connected:
            self.kiwoom.Disconnect()
            logger.info("🔌 Kiwoom API 연결 해제 완료.")

    def get_deposit_balance(self) -> int:
        """현재 예수금을 조회하여 반환합니다."""
        if not self._connect_kiwoom():
            return -1 # 연결 실패 시 -1 반환

        balance = 0
        try:
            deposit_data = self.kiwoom.block_request(
                "opw00001",
                계좌번호=self.account_number,
                비밀번호=self.account_password, # 환경 변수에서 로드한 비밀번호 사용
                비밀번호입력매체구분="00",
                조회구분=2,
                output="예수금상세현황",
                next=0
            )
            if deposit_data is None or deposit_data.empty:
                logger.warning("⚠️ 예수금 상세 현황 데이터 없음.")
                return 0

            balance_str = str(deposit_data['예수금'].iloc[0]).replace(",", "").strip()
            balance = int(balance_str) if balance_str.isdigit() else 0
            logger.info(f"💰 예수금 조회 완료: {balance:,}원")
        except Exception as e:
            logger.error(f"❌ 예수금 조회 실패: {e}", exc_info=True)
            send_telegram_message(f"❌ 예수금 조회 오류: {e}")
        finally:
            self._disconnect_kiwoom()
        return balance

    def get_account_positions(self) -> pd.DataFrame:
        """
        Kiwoom API에서 실제 계좌의 보유 종목과 현재가, 수익률을 조회합니다.
        (modules/monitor_positions.py의 load_positions 함수와 별개)
        """
        if not self._connect_kiwoom():
            return pd.DataFrame() # 연결 실패 시 빈 DataFrame 반환

        df_positions = pd.DataFrame()
        try:
            # opw00018: 계좌평가잔고내역요청
            account_data = self.kiwoom.block_request(
                "opw00018",
                계좌번호=self.account_number,
                비밀번호=self.account_password, # 환경 변수에서 로드한 비밀번호 사용
                비밀번호입력매체구분="00",
                조회구분=1, # 1: 일반 (전체), 2: 잔고수량 있는것만
                output="계좌평가잔고개별합산",
                next=0
            )

            if account_data is None or account_data.empty:
                logger.info("📂 키움 계좌에 보유 종목 없음.")
                return pd.DataFrame()

            # 필요한 정보만 추출 및 가공
            data = []
            for i in range(len(account_data)):
                try:
                    code = account_data['종목번호'].iloc[i].strip() # 종목코드
                    name = account_data['종목명'].iloc[i].strip() # 종목명
                    current_price_str = str(account_data['현재가'].iloc[i]).replace(",", "").replace("+", "").replace("-", "").strip()
                    current_price = int(current_price_str) if current_price_str.isdigit() else 0
                    buy_price_str = str(account_data['매입가'].iloc[i]).replace(",", "").replace("+", "").replace("-", "").strip()
                    buy_price = int(buy_price_str) if buy_price_str.isdigit() else 0
                    quantity_str = str(account_data['보유수량'].iloc[i]).replace(",", "").strip()
                    quantity = int(quantity_str) if quantity_str.isdigit() else 0
                    pnl_pct_str = str(account_data['수익률'].iloc[i]).replace(",", "").strip()
                    pnl_pct = float(pnl_pct_str) if pnl_pct_str else 0.0

                    data.append({
                        "ticker": code,
                        "name": name,
                        "current_price": current_price,
                        "buy_price": buy_price,
                        "quantity": quantity,
                        "pnl_pct": pnl_pct
                    })
                except Exception as inner_e:
                    logger.error(f"❌ 계좌 데이터 개별 처리 오류: {inner_e}", exc_info=True)
                    continue

            df_positions = pd.DataFrame(data)
            logger.info(f"📈 계좌 보유 종목 {len(df_positions)}개 조회 완료.")

        except Exception as e:
            logger.error(f"❌ 계좌 보유 종목 조회 실패: {e}", exc_info=True)
            send_telegram_message(f"❌ 보유 종목 조회 오류: {e}")
        finally:
            self._disconnect_kiwoom()
        return df_positions

# 이 모듈이 단독 실행될 때는 테스트 목적으로 사용될 수 있습니다.
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    # .env 파일이 단독 실행시에도 로드되도록 (만약 메인 스크립트에서 이미 로드했다면 불필요)
    # load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env'))

    helper = KiwoomQueryHelper()

    # 예수금 테스트
    balance = helper.get_deposit_balance()
    if balance != -1:
        print(f"테스트: 현재 예수금: {balance:,}원")
    else:
        print("테스트: 예수금 조회 실패")

    print("\n---")
    # 보유 종목 테스트
    positions_df = helper.get_account_positions()
    if not positions_df.empty:
        print("테스트: 보유 종목 현황:")
        print(positions_df)
    else:
        print("테스트: 보유 종목 없음 또는 조회 실패")