import time
import logging
from modules.common.utils import get_current_time_str
from modules.common.error_codes import get_error_message # ✅ 경로 확인

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
                self.kiwoom_helper.tr_event_loop.reset() # TR 요청 전에 루프 초기화
                ret = self.kiwoom_helper.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)",
                                                             rq_name, tr_code, int(prev_next), screen_no)

                if ret == 0:
                    if self.kiwoom_helper.tr_event_loop.wait(timeout_ms=timeout_ms): # 응답 대기
                        data = self.kiwoom_helper.tr_event_loop.get_data()
                        if data and not data.get("error"):
                            logger.info(f"✅ TR 요청 성공: {rq_name} ({tr_code})")
                            return data
                        else:
                            error_msg = data.get("error", "알 수 없는 TR 응답 오류")
                            logger.warning(f"⚠️ TR 응답 데이터 오류: {rq_name} ({tr_code}) - {error_msg}")
                            if attempt < retry_attempts:
                                time.sleep(retry_delay_sec)
                                continue
                            return {"error": error_msg}
                    else:
                        logger.warning(f"⚠️ TR 요청 타임아웃: {rq_name} ({tr_code})")
                        if attempt < retry_attempts:
                            time.sleep(retry_delay_sec)
                            continue
                        return {"error": "Timeout"}
                else:
                    error_msg = get_error_message(ret)
                    logger.error(f"❌ TR 요청 실패: {rq_name} ({tr_code}) - 코드: {ret} ({error_msg})")
                    if attempt < retry_attempts:
                        time.sleep(retry_delay_sec)
                        continue
                    return {"error": error_msg}
            except Exception as e:
                logger.error(f"TR 요청 중 예외 발생: {rq_name} ({tr_code}) - {e}", exc_info=True)
                if attempt < retry_attempts:
                    time.sleep(retry_delay_sec)
                    continue
                return {"error": f"TR 요청 중 예외 발생: {e}"}

        return {"error": f"TR 요청 실패: {rq_name} ({tr_code}) - 모든 재시도 실패"}

    def request_account_info(self, account_no, timeout_ms=30000, retry_attempts=5, retry_delay_sec=5):
        """
        예수금/잔고 등 계좌 정보를 요청합니다. (TR: opw00001)
        """
        try:
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "계좌번호", account_no)

            # 비밀번호는 실제 로그에 노출되지 않도록 마스킹 처리
            masked_password = (
                self.account_password[:2] + '*' * (len(self.account_password) - 4) + self.account_password[-2:]
                if len(self.account_password) > 4 else '*' * len(self.account_password)
            )
            logger.info(f"SetInputValue: 계좌번호='{account_no}', 비밀번호='{masked_password}'")

            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "비밀번호", self.account_password)
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "00")
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "조회구분", "2")

            screen_no = self._generate_unique_screen_no()

            result = self._send_tr_request(
                rq_name="opw00001_req",
                tr_code="opw00001",
                prev_next="0",
                screen_no=screen_no,
                timeout_ms=timeout_ms,
                retry_attempts=retry_attempts,
                retry_delay_sec=retry_delay_sec
            )
            if result and not result.get("error"):
                logger.info(f"✅ 계좌 정보 조회 성공: 예수금 {result.get('예수금'):,}원")
                return result
            else:
                logger.error(f"❌ 계좌 정보 조회 실패: {result.get('error', '알 수 없는 오류')}")
                return {"예수금": 0, "error": result.get('error', '알 수 없는 오류')}

        except Exception as e:
            logger.error(f"❌ 계좌 정보 요청 중 예외 발생: {e}", exc_info=True)
            return {"예수금": 0, "error": str(e)}

    def request_account_balance_and_positions(self, account_no, timeout_ms=30000, retry_attempts=5, retry_delay_sec=5):
        """
        계좌 평가 잔고 및 보유 종목 정보를 요청합니다. (TR: opw00018)
        """
        try:
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "계좌번호", account_no)
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "비밀번호", self.account_password)
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "상장폐지구분", "0") # 0: 전체
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "00")

            screen_no = self._generate_unique_screen_no()

            result = self._send_tr_request(
                rq_name="opw00018_req",
                tr_code="opw00018",
                prev_next="0",
                screen_no=screen_no,
                timeout_ms=timeout_ms,
                retry_attempts=retry_attempts,
                retry_delay_sec=retry_delay_sec
            )
            if result and not result.get("error"):
                logger.info(f"✅ 계좌 평가 잔고 및 보유 종목 조회 성공.")
                return result
            else:
                logger.error(f"❌ 계좌 평가 잔고 및 보유 종목 조회 실패: {result.get('error', '알 수 없는 오류')}")
                return {"account_balance": {}, "positions": [], "error": result.get('error', '알 수 없는 오류')}
        except Exception as e:
            logger.error(f"❌ 계좌 평가 잔고 및 보유 종목 요청 중 예외 발생: {e}", exc_info=True)
            return {"account_balance": {}, "positions": [], "error": str(e)}

