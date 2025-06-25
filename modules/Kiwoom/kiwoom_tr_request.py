# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
from PyQt5.QtCore import QEventLoop, QTimer 

from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    # 💡 __init__ 메서드에 account_password 인자 추가
    def __init__(self, kiwoom_helper, pyqt_app_instance, account_password=""):
        self.kiwoom_helper = kiwoom_helper 
        self.pyqt_app = pyqt_app_instance 
        self.account_password = account_password # 💡 계좌 비밀번호 저장
        
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
                # opw00001 (예수금상세현황요청) 처리
                if tr_code == "opw00001":
                    deposit = self.kiwoom_helper.ocx.CommGetData(
                        tr_code, "", rq_name, 0, "예수금" 
                    )
                    self.tr_data = {"예수금": int(deposit.strip()) if deposit.strip() else 0}
                    logger.info(f"TR 데이터 수신: {tr_code} - 예수금: {self.tr_data['예수금']}")
                
                # opw00018 (계좌평가현황요청) 처리 - 멀티 데이터 파싱
                elif tr_code == "opw00018":
                    cnt = self.kiwoom_helper.ocx.GetRepeatCnt(tr_code, rq_name)
                    holdings_list = []
                    for i in range(cnt):
                        item_name = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "종목명").strip()
                        stock_code = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "종목번호").strip()
                        current_qty = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "보유수량").strip())
                        purchase_price = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "매입단가").strip())
                        current_price = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip())
                        total_purchase_amount = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "매입금액").strip())
                        
                        # 종목코드에서 'A' 접두사 제거
                        if stock_code.startswith('A'):
                            stock_code = stock_code[1:]

                        if current_qty > 0: # 수량이 0 이상인 종목만 추가
                            holdings_list.append({
                                "stock_code": stock_code,
                                "name": item_name,
                                "quantity": current_qty,
                                "purchase_price": purchase_price,
                                "current_price": current_price,
                                "total_purchase_amount": total_purchase_amount,
                            })
                    self.tr_data = {"holdings": holdings_list}
                    logger.info(f"TR 데이터 수신: {tr_code} - 보유 종목 {len(holdings_list)}개.")

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
        """
        예수금 등 계좌 잔고 정보 요청 (opw00001)
        """
        self.rq_name = "opw00001_req"
        self.tr_data = None 

        self.kiwoom_helper.ocx.SetInputValue("계좌번호", account_no)
        # 💡 계좌 비밀번호를 SetInputValue에 사용
        self.kiwoom_helper.ocx.SetInputValue("비밀번호", self.account_password) 
        self.kiwoom_helper.ocx.SetInputValue("비밀번호입력매체구분", "00")
        self.kiwoom_helper.ocx.SetInputValue("조회구분", "2") 

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

    def request_daily_account_holdings(self, account_no, timeout_ms=30000):
        """
        계좌 평가 현황 및 보유 종목 정보를 요청합니다 (opw00018).
        리스트 형태의 보유 종목 데이터를 반환합니다.
        """
        self.rq_name = "opw00018_req"
        self.tr_data = None

        self.kiwoom_helper.ocx.SetInputValue("계좌번호", account_no)
        # opw00018은 계좌 비밀번호를 요구하지 않는 경우가 많지만, 안전을 위해 설정
        self.kiwoom_helper.ocx.SetInputValue("비밀번호", self.account_password) 
        self.kiwoom_helper.ocx.SetInputValue("비밀번호입력매체구분", "00")


        screen_no = self._generate_unique_screen_no()

        result = self.kiwoom_helper.ocx.CommRqData(
            self.rq_name, "opw00018", 0, screen_no 
        )

        if result == 0:
            self.tr_wait_timer.start(timeout_ms)
            self.tr_wait_event_loop.exec_()
            if self.tr_data and "holdings" in self.tr_data:
                return self.tr_data["holdings"]
            else:
                logger.warning(f"TR 요청 성공했으나 opw00018 보유 종목 데이터 없음: {self.tr_data}")
                return []
        else:
            logger.error(f"보유 종목 요청 실패: {result} ({self._get_error_message(result)})")
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
