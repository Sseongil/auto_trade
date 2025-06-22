# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
from PyQt5.QtCore import QEventLoop, QTimer
from modules.common.utils import get_current_time_str
from modules.common.config import get_env

try:
    from modules.notify import send_telegram_message
except ImportError:
    def send_telegram_message(msg): pass

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    def __init__(self, kiwoom_helper, app):
        self.helper = kiwoom_helper
        self.app = app
        self.ocx = kiwoom_helper.ocx
        self.account_info = {}
        self.tr_event_loop = QEventLoop()
        self.tr_data_received = False

        self.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def _on_receive_tr_data(self, screen_no, rqname, trcode, recordname, prev_next, data_len, err_code, msg1, msg2):
        try:
            if rqname == "계좌평가잔고내역요청":
                count = self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)
                total_deposit = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", trcode, rqname, 0, "예수금")
                total_assets = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", trcode, rqname, 0, "총평가자산")

                try:
                    deposit_int = int(total_deposit.strip().replace(',', ''))
                except Exception as e:
                    deposit_int = 0
                    logger.warning(f"⚠️ 예수금 파싱 실패: {total_deposit} ({e})")

                try:
                    assets_int = int(total_assets.strip().replace(',', ''))
                except Exception as e:
                    assets_int = 0
                    logger.warning(f"⚠️ 총평가자산 파싱 실패: {total_assets} ({e})")

                self.account_info = {
                    "예수금": deposit_int,
                    "총평가자산": assets_int
                }

                self.tr_data_received = True

        except Exception as e:
            logger.exception(f"❌ TR 응답 처리 중 예외 발생: {e}")
        finally:
            if self.tr_event_loop.isRunning():
                self.tr_event_loop.quit()

    def request_account_info(self, account_number):
        try:
            password = get_env("KIWOOM_ACCOUNT_PASSWORD", "").strip()
            if not password:
                msg = "❌ 계좌 비밀번호가 설정되지 않았습니다 (.env에 KIWOOM_ACCOUNT_PASSWORD 추가 필요)"
                logger.critical(msg)
                send_telegram_message(msg)
                return {}

            logger.info(f"📥 계좌 정보 요청 시작 (계좌번호: {account_number})")
            self.tr_data_received = False

            # 입력값 설정
            self.ocx.dynamicCall("SetInputValue(QString, QString)", "계좌번호", account_number)
            self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호", password)
            self.ocx.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "02")
            self.ocx.dynamicCall("SetInputValue(QString, QString)", "조회구분", "1")

            result = self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", "계좌평가잔고내역요청", "opw00018", 0, "2000")

            if result != 0:
                logger.error(f"❌ 계좌 정보 요청 실패. 오류 코드: {result}")
                send_telegram_message(f"❌ 계좌 정보 요청 실패 (TR 오류 코드: {result})")
                return {}

            # 응답 수신을 기다림 (최대 10초 대기)
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(self.tr_event_loop.quit)
            timer.start(10000)

            self.tr_event_loop.exec_()

            if not self.tr_data_received:
                logger.error("❌ 계좌 TR 응답 수신 실패 (타임아웃)")
                send_telegram_message("❌ 계좌 정보 수신 실패 (10초 응답 없음)")
                return {}

            logger.info(f"✅ 계좌 정보 수신 성공: {self.account_info}")
            return self.account_info

        except Exception as e:
            logger.exception(f"❌ 계좌 정보 요청 중 예외 발생: {e}")
            send_telegram_message(f"❌ 계좌 정보 요청 중 오류 발생: {e}")
            return {}
