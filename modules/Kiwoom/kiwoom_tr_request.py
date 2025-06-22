# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    def __init__(self, kiwoom_helper, pyqt_app=None):
        self.kiwoom = kiwoom_helper
        self.app = pyqt_app
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def request_account_info(self, account_number):
        """
        예수금, 총자산 등 계좌 잔고 정보 요청
        """
        logger.info(f"{get_current_time_str()}: [TR 요청] 계좌 정보 요청 중... 계좌번호: {account_number}")
        try:
            tr_code = "opw00001"
            rq_name = "예수금상세현황요청"
            screen_no = "2000"
            input_params = {
                "계좌번호": account_number,
                "비밀번호": "",  # 증권사 비밀번호 입력이 필요하면 여기에
                "비밀번호입력매체구분": "00",
                "조회구분": "2"  # 1: 단일, 2: 복수
            }

            self.kiwoom.comm_rq_data(
                rq_name=rq_name,
                tr_code=tr_code,
                screen_no=screen_no,
                input_params=input_params
            )

            logger.info(f"{get_current_time_str()}: [✅] 요청 완료. 응답 대기 중...")
            data = self.kiwoom.get_tr_data(tr_code, timeout=10)

            if not data:
                logger.error("❌ 계좌 정보 응답 없음 (TR 응답 대기 실패)")
                return {}

            result = {
                "예수금": int(data.get("예수금", 0)),
                "총평가자산": int(data.get("총평가자산", 0)),
                "추정예탁자산": int(data.get("추정예탁자산", 0))
            }

            logger.info(f"{get_current_time_str()}: [💰] 예수금: {result['예수금']}, 총자산: {result['총평가자산']}")
            return result

        except Exception as e:
            logger.exception(f"{get_current_time_str()}: ❌ 계좌 정보 요청 실패: {e}")
            return {}
