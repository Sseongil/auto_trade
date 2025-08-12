# modules/portfolio_manager.py
import logging
import pandas as pd
from modules.Kiwoom.kiwoom_api_caller import KiwoomApiCaller
from modules.common.config import ACCOUNT_NUMBERS

# 로거 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

class PortfolioManager:
    def __init__(self, kiwoom_api_caller: KiwoomApiCaller):
        self.api = kiwoom_api_caller
        self.account_number = (
            ACCOUNT_NUMBERS.split(';')[0]
            if isinstance(ACCOUNT_NUMBERS, str) and ';' in ACCOUNT_NUMBERS
            else ACCOUNT_NUMBERS
        )
        self.positions = pd.DataFrame(columns=[
            "종목명", "보유수량", "매입가", "현재가", "평가금액", "손익률(%)"
        ])
        self.cash_balance = 0
        logger.info(f"📊 PortfolioManager 초기화 완료. 계좌번호: {self.account_number}")

    def _convert_to_int(self, value):
        """콤마 제거 후 int 변환"""
        try:
            if isinstance(value, str):
                return int(value.replace(',', '').strip())
            return int(value)
        except (ValueError, TypeError):
            logger.warning(f"⚠️ int 변환 실패: {value}")
            return 0

    def _convert_to_float(self, value):
        """float 변환"""
        try:
            if isinstance(value, str):
                return float(value.strip())
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"⚠️ float 변환 실패: {value}")
            return 0.0

    def update_cash_balance(self):
        """예수금 조회"""
        logger.info("💰 예수금 조회 요청...")
        try:
            self.api.set_input_value("계좌번호", self.account_number)
            self.api.set_input_value("비밀번호", "")
            self.api.set_input_value("비밀번호입력매체구분", "00")
            self.api.set_input_value("조회구분", "2")
            data = self.api.comm_rq_data("예수금상세현황요청", "opw00001", 0, "2000")
        except Exception as e:
            logger.error(f"❌ 예수금 요청 실패: {e}", exc_info=True)
            self.cash_balance = 0
            return

        self.cash_balance = 0
        if data and '출금가능금액' in data and data['출금가능금액']:
            self.cash_balance = self._convert_to_int(data['출금가능금액'][0])
            logger.info(f"✅ 예수금: {self.cash_balance:,}원")
        else:
            logger.warning("⚠️ 예수금 데이터 없음")

    def update_positions(self):
        """보유 종목 조회"""
        logger.info("📦 보유 종목 조회 요청...")
        try:
            self.api.set_input_value("계좌번호", self.account_number)
            self.api.set_input_value("비밀번호", "")
            self.api.set_input_value("비밀번호입력매체구분", "00")
            self.api.set_input_value("조회구분", "2")
            data = self.api.comm_rq_data("계좌평가잔고내역요청", "opw00018", 0, "2001")
        except Exception as e:
            logger.error(f"❌ 보유 종목 요청 실패: {e}", exc_info=True)
            self.positions = pd.DataFrame()
            return

        if not data:
            logger.warning("⚠️ 보유 종목 데이터 없음")
            self.positions = pd.DataFrame()
            return

        required_keys = ["종목명", "보유수량", "매입가", "현재가", "평가금액", "손익률(%)"]
        if not all(key in data and data[key] for key in required_keys):
            logger.warning("⚠️ 보유 종목 데이터 일부 누락")
            self.positions = pd.DataFrame()
            return

        self.positions = pd.DataFrame({
            "종목명": data['종목명'],
            "보유수량": [self._convert_to_int(x) for x in data['보유수량']],
            "매입가": [self._convert_to_int(x) for x in data['매입가']],
            "현재가": [self._convert_to_int(x) for x in data['현재가']],
            "평가금액": [self._convert_to_int(x) for x in data['평가금액']],
            "손익률(%)": [self._convert_to_float(x) for x in data['손익률(%)']],
        })
        logger.info(f"✅ 보유 종목 {len(self.positions)}개 조회 성공")

    def get_account_status(self):
        """계좌 상태 요약"""
        self.update_cash_balance()
        self.update_positions()

        msg = f"📊 계좌번호: {self.account_number}\n💰 예수금: {self.cash_balance:,}원\n"
        if self.positions.empty:
            msg += "📦 보유 종목: 없음\n"
        else:
            msg += "\n📦 보유 종목:\n"
            for _, row in self.positions.iterrows():
                msg += (
                    f" - {row['종목명']}: {row['보유수량']}주 / "
                    f"현재가 {row['현재가']:,}원 / "
                    f"손익률 {row['손익률(%)']:.2f}%\n"
                )
        logger.info("✅ 계좌 상태 생성 완료")
        return msg
