# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
from PyQt5.QtCore import QEventLoop, QTimer 

from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    def __init__(self, kiwoom_helper, pyqt_app_instance):
        self.kiwoom_helper = kiwoom_helper 
        self.pyqt_app = pyqt_app_instance 
        
        self.tr_data = None 
        self.rq_name = None 

        self.tr_wait_event_loop = QEventLoop()
        self.tr_wait_timer = QTimer()
        self.tr_wait_timer.setSingleShot(True) 
        self.tr_wait_timer.timeout.connect(self._on_tr_timeout) 

        self.kiwoom_helper.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, sPrevNext, data_len, err_code, msg1, msg2):
        if self.tr_wait_timer.isActive():
            self.tr_wait_timer.stop()

        if rq_name == self.rq_name: 
            try:
                if tr_code == "opw00001":
                    deposit = self.kiwoom_helper.ocx.CommGetData(
                        tr_code, "", rq_name, 0, "예수금" 
                    )
                    self.tr_data = {"예수금": int(deposit.strip()) if deposit.strip() else 0}
                    logger.info(f"TR 데이터 수신: {tr_code} - 예수금: {self.tr_data['예수금']}")
                
                # TODO: 다른 TR 코드에 대한 처리 로직 추가 (예: opw00018 등)
                # opw00018은 멀티 데이터 (보유 종목 리스트)를 포함할 수 있으므로,
                # GetRepeatCnt와 GetCommData를 사용하여 반복 처리해야 합니다.
                # 예시:
                # if tr_code == "opw00018":
                #     cnt = self.kiwoom_helper.ocx.GetRepeatCnt(tr_code, rq_name)
                #     items = []
                #     for i in range(cnt):
                #         item_data = {
                #             "종목코드": self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "종목번호").strip(),
                #             "종목명": self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "종목명").strip(),
                #             "보유수량": int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "보유수량").strip()),
                #             "매입가": int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "매입가").strip()),
                #             "현재가": int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip())
                #         }
                #         items.append(item_data)
                #     self.tr_data = {"보유종목": items}


            except Exception as e:
                logger.error(f"Error processing TR data for {tr_code}: {e}", exc_info=True)
                self.tr_data = {"error": f"TR 데이터 처리 오류: {str(e)}"}
            finally:
                if self.tr_wait_event_loop.isRunning(): 
                    self.tr_wait_event_loop.exit()
        
    def _on_tr_timeout(self):
        if self.tr_wait_event_loop.isRunning(): 
            logger.error(f"[{get_current_time_str()}]: ❌ TR 요청 실패 - 타임아웃 ({self.rq_name}, {self.tr_wait_timer.interval()}ms)")
            self.tr_data = {"error": f"TR 요청 타임아웃 ({self.rq_name})"}
            self.tr_wait_event_loop.exit()

    def request_account_info(self, account_no, timeout_ms=30000): 
        self.rq_name = "opw00001_req"
        self.tr_data = None 

        self.kiwoom_helper.ocx.SetInputValue("계좌번호", account_no)
        
        screen_no = self._generate_unique_screen_no() 

        result = self.kiwoom_helper.ocx.CommRqData(
            self.rq_name, "opw00001", 0, screen_no 
        )
        
        if result == 0:
            self.tr_wait_timer.start(timeout_ms)
            self.tr_wait_event_loop.exec_() 
            return self.tr_data
        else:
            logger.error(f"계좌 정보 요청 실패: {result} ({self._get_error_message(result)})")
            return {"error": f"TR 요청 실패 코드: {result} ({self._get_error_message(result)})"}

    def _generate_unique_screen_no(self):
        unique_part = str(int(time.time() * 100000))[-4:] 
        screen_no = str(2000 + int(unique_part) % 7999) 
        return screen_no

    def _get_error_message(self, err_code):
        error_map = {
            0: "정상 처리",
            -10: "미접속",
            -100: "사용자정보교환실패",
            -101: "서버접속실패",
            -102: "버전처리실패",
            -103: "비정상적인 모듈 호출",
            -104: "종목코드 없음",
            -105: "계좌증거금율 오류",
            -106: "통신연결종료",
            -107: "사용자정보 없음",
            -108: "주문 가격 오류",
            -109: "주문 수량 오류",
            -110: "실시간 등록 오류",
            -111: "실시간 해제 오류",
            -112: "데이터 없음",
            -113: "API 미설정",
            -200: "전문 송수신 실패", 
            -201: "입력값 오류",
            -202: "계좌정보 오류 (계좌번호 또는 비밀번호 관련 문제일 가능성 높음)", 
            -300: "알 수 없는 오류 (API 내부 오류, 요청 제한 등 복합적인 원인)", 
            -999: "타임아웃 발생 (내부 정의)" 
        }
        return error_map.get(err_code, "알 수 없는 오류")
