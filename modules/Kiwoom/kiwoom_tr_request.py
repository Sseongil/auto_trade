# modules/Kiwoom/kiwoom_tr_request.py

import pandas as pd
import time
import logging
from modules.common.utils import get_current_time_str
from modules.common.error_codes import get_error_message

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
                # TR 요청 전에 KiwoomQueryHelper에 이벤트 루프를 설정합니다.
                self.kiwoom_helper.set_tr_response_event(screen_no)

                ret = self.kiwoom_helper.kiwoom.dynamicCall(
                    "CommRqData(QString, QString, int, QString)",
                    rq_name, tr_code, int(prev_next), screen_no
                )
                if ret == 0:
                    logger.info(f"TR 요청 성공. 응답 대기 중... (화면번호: {screen_no}, 요청: {rq_name})")
                    # KiwoomQueryHelper의 wait_for_tr_response를 사용하여 응답을 기다립니다.
                    if not self.kiwoom_helper.wait_for_tr_response(screen_no, timeout_ms):
                        logger.error(f"TR 응답 타임아웃: {rq_name} ({tr_code}) (화면번호: {screen_no})")
                        raise TimeoutError("TR response timeout")

                    # 응답 데이터 가져오기
                    result_data = self.kiwoom_helper.get_tr_data(screen_no)
                    if result_data and not result_data.get("error"):
                        return result_data
                    else:
                        logger.error(f"TR 데이터 수신 오류 또는 에러 응답: {result_data} (화면번호: {screen_no})")
                        return {"error": "TR data error", "details": result_data}
                else:
                    error_msg = get_error_message(ret)
                    logger.error(f"TR 요청 실패: {rq_name} ({tr_code}) - 코드: {ret} ({error_msg}) (화면번호: {screen_no})")
                    return {"error": "TR request failed", "code": ret, "message": error_msg}

            except TimeoutError:
                logger.error(f"TR 요청 타임아웃 발생: {rq_name} ({tr_code}) (재시도 {attempt}/{retry_attempts}) (화면번호: {screen_no})")
                if attempt < retry_attempts:
                    time.sleep(retry_delay_sec)
                else:
                    return {"error": "TR request timeout", "message": "Max retries reached for timeout"}
            except Exception as e:
                logger.error(f"TR 요청 중 예외 발생: {rq_name} ({tr_code}) - {e} (재시도 {attempt}/{retry_attempts}) (화면번호: {screen_no})", exc_info=True)
                if attempt < retry_attempts:
                    time.sleep(retry_delay_sec)
                else:
                    return {"error": "TR request exception", "message": str(e)}
        return {"error": "TR request failed after all retries"}


    def request_account_info(self, account_no, timeout_ms=5000, retry_attempts=3, retry_delay_sec=3):
        """
        예수금 정보를 요청합니다. (TR: opw00001)
        """
        try:
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "계좌번호", account_no)
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
                logger.info(f"✅ 예수금 조회 성공. 예수금: {result['single_data'].get('예수금', 'N/A')}")
                return result["single_data"]
            else:
                logger.error(f"❌ 계좌 정보 조회 실패: {result.get('message', result.get('error', '알 수 없는 오류'))}")
                return {"error": "Failed to get account info", "details": result}
        except Exception as e:
            logger.error(f"❌ 계좌 정보 조회 중 예외 발생: {e}", exc_info=True)
            return {"error": "Exception during account info request", "details": str(e)}

    def request_account_positions(self, account_no, timeout_ms=10000, retry_attempts=5, retry_delay_sec=5):
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
                logger.error(f"❌ 계좌 평가 잔고 및 보유 종목 조회 실패: {result.get('message', result.get('error', '알 수 없는 오류'))}")
                return {"error": "Failed to get account positions", "details": result}
        except Exception as e:
            logger.error(f"❌ 계좌 평가 잔고 및 보유 종목 조회 중 예외 발생: {e}", exc_info=True)
            return {"error": "Exception during account positions request", "details": str(e)}

    def request_daily_ohlcv(self, stock_code, end_date, prev_next="0", timeout_ms=5000, retry_attempts=3, retry_delay_sec=3):
        """
        일봉 데이터를 요청합니다. (TR: opt10081)
        """
        try:
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "종목코드", stock_code)
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "기준일자", end_date)
            self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "수정주가구분", "1") # 1: 수정주가 적용

            screen_no = self._generate_unique_screen_no()

            result = self._send_tr_request(
                rq_name="opt10081_req",
                tr_code="opt10081",
                prev_next=prev_next,
                screen_no=screen_no,
                timeout_ms=timeout_ms,
                retry_attempts=retry_attempts,
                retry_delay_sec=retry_delay_sec
            )
            if result and not result.get("error"):
                logger.info(f"✅ 일봉 데이터 조회 성공: {stock_code}")
                return result
            else:
                logger.error(f"❌ 일봉 데이터 조회 실패: {stock_code} - {result.get('message', result.get('error', '알 수 없는 오류'))}")
                return {"error": "Failed to get daily OHLCV", "details": result}
        except Exception as e:
            logger.error(f"❌ 일봉 데이터 조회 중 예외 발생: {e}", exc_info=True)
            return {"error": "Exception during daily OHLCV request", "details": str(e)}
