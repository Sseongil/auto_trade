# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
from PyQt5.QtCore import QEventLoop
from modules.common.utils import get_current_time_str
from modules.common.config import get_env

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    def __init__(self, kiwoom_helper, app):
        self.helper = kiwoom_helper
        self.app = app
        self.ocx = kiwoom_helper.ocx
        self.account_info = {}
        self.tr_event_loop = QEventLoop()

        # 이벤트 슬롯 연결
        self.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def _on_receive_tr_data(self, screen_no, rqname, trcode, recordname, prev_next, data_len, err_code, msg1, msg2):
        try:
            if rqname == "계좌평가잔고내역요청":
                count = self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)
                total_deposit = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", trcode, rqname, 0, "예수금")
                total_assets = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", trcode, rqname, 0, "총평가자산")
                self.account_info = {
                    "예수금": int(total_deposit.strip()) if total_deposit.strip().isdigit() else 0,
                    "총평가자산": int(total_assets.strip()) if total_assets.strip().isdigit() else 0
                }
        except Exception as e:
            logger.error(f"❌ TR 응답 처리 중 예외 발생: {e}")
        finally:
            self.tr_event_loop.quit()

    def request_account_info(self, account_number):
        try:
            password = get_env("KIWOOM_ACCOUNT_PASSWORD")
            if not password:
                logger.critical("❌ 계좌 비밀번호가 .env에 설정되지 않았습니다. 'KIWOOM_ACCOUNT_PASSWORD' 항목 추가 필요.")
                send_telegram_message("❌ 계좌 비밀번호 미설정으로 계좌 정보 요청 실패")
                return {}

            # ✅ 로그인 직후 계좌 조회 시 안정성 위해 잠시 대기
            time.sleep(5)

            logger.info(f"📥 계좌 정보 요청 시도 중... (계좌번호: {account_number})")
            self.ocx.dynamicCall("SetInputValue(QString, QString)", "계좌번호", account_number)
            self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호", password)
            self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "02")  # 02: 키보드
            self.ocx.dynamicCall("SetInputValue(QString, QString)", "조회구분", "1")  # 1: 잔고 + 평가

            result = self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", "계좌평가잔고내역요청", "opw00018", 0, "1000")
            if result != 0:
                logger.error(f"❌ 계좌 정보 요청 실패. 오류 코드: {result}")
                return {}

            self.tr_event_loop.exec_()
            return self.account_info

        except Exception as e:
            logger.exception(f"❌ 계좌 정보 요청 중 예외 발생: {e}")
            return {}
