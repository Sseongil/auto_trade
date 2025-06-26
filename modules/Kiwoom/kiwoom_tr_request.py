import time
import logging
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    def __init__(self, kiwoom_helper, qt_app, account_password):
        self.kiwoom_helper = kiwoom_helper
        self.qt_app = qt_app
        self.account_password = account_password
        self.screen_no_counter = 3400  # 초기값

    def _generate_unique_screen_no(self):
        """
        TR 요청용으로 고유 screen_no를 생성합니다.
        """
        self.screen_no_counter += 1
        if self.screen_no_counter > 9999:
            self.screen_no_counter = 3400
        return str(self.screen_no_counter)

    def _send_tr_request(self, rq_name, tr_code, prev_next, screen_no, timeout_ms=10000, retry_attempts=3, retry_delay_sec=3):
        """
        키움 OpenAPI+의 TR 요청을 보내고 응답을 기다리는 함수입니다.
        """
        for attempt in range(1, retry_attempts + 1):
            try:
                logger.info(f"TR 요청 시도 {attempt}/{retry_attempts}: rq_name='{rq_name}', tr_code='{tr_code}', screen_no='{screen_no}'")

                self.kiwoom_helper.tr_event_loop.reset()
                self.kiwoom_helper.ocx.CommRqData(rq_name, tr_code, prev_next, screen_no)

                success = self.kiwoom_helper.tr_event_loop.wait(timeout_ms)

                if not success:
                    raise TimeoutError(f"TR 응답 타임아웃: {rq_name}")

                data = self.kiwoom_helper.tr_event_loop.get_data()

                if data is None:
                    raise ValueError(f"TR 응답 데이터 없음: {rq_name}")

                logger.info(f"✅ TR 응답 성공: {rq_name} - {list(data.keys())}")
                return data

            except Exception as e:
                logger.error(f"TR 요청 자체 실패: {rq_name} ({tr_code}) - 코드: -300 (알 수 없는 오류). (재시도 중...)\n오류: {e}")
                time.sleep(retry_delay_sec)

        return {"error": f"TR 요청 실패: {rq_name} ({tr_code}) - 모든 재시도 실패"}

    def request_account_info(self, account_no, timeout_ms=30000, retry_attempts=5, retry_delay_sec=5):
        """
        예수금/잔고 등 계좌 정보를 요청합니다.
        """
        try:
            self.kiwoom_helper.ocx.SetInputValue("계좌번호", account_no)

            masked_password = (
                self.account_password[:2] + '*' * (len(self.account_password) - 4) + self.account_password[-2:]
                if len(self.account_password) > 4 else '*' * len(self.account_password)
            )
            logger.info(f"SetInputValue: 계좌번호='{account_no}', 비밀번호='{masked_password}'")

            self.kiwoom_helper.ocx.SetInputValue("비밀번호", self.account_password)
            self.kiwoom_helper.ocx.SetInputValue("비밀번호입력매체구분", "00")
            self.kiwoom_helper.ocx.SetInputValue("조회구분", "2")

            screen_no = self._generate_unique_screen_no()

            result = self._send_tr_request(
                rq_name="opw00001_req",
                tr_code="opw00001",
                prev_next=0,
                screen_no=screen_no,
                timeout_ms=timeout_ms,
                retry_attempts=retry_attempts,
                retry_delay_sec=retry_delay_sec
            )
            return result

        except Exception as e:
            logger.exception(f"❌ request_account_info() 중 오류 발생: {e}")
            return {"error": str(e)}
