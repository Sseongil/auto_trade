# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
from PyQt5.QtCore import QEventLoop, QTimer 

from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    def __init__(self, kiwoom_helper, pyqt_app_instance, account_password=""): 
        self.kiwoom_helper = kiwoom_helper 
        self.pyqt_app = pyqt_app_instance 
        self.account_password = account_password # 계좌 비밀번호 저장 (초기화 시점에서 받아옴)
        
        self.tr_data = None 
        self.rq_name = None 

        # TR 응답 대기를 위한 전용 QEventLoop와 QTimer
        self.tr_wait_event_loop = QEventLoop()
        self.tr_wait_timer = QTimer()
        self.tr_wait_timer.setSingleShot(True) 
        self.tr_wait_timer.timeout.connect(self._on_tr_timeout) 

        # QAxWidget의 OnReceiveTrData 이벤트를 연결합니다.
        self.kiwoom_helper.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, sPrevNext, data_len, err_code, msg1, msg2):
        """TR 데이터 수신 이벤트 핸들러"""
        # TR 대기 타이머가 활성 상태라면 중지
        if self.tr_wait_timer.isActive():
            self.tr_wait_timer.stop()

        if rq_name == self.rq_name: # 현재 요청 중인 TR에 대한 응답인 경우
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
                        
                        # 종목코드에서 'A' 접두사 제거 (Kiwoom API 특성)
                        if stock_code.startswith('A'):
                            stock_code = stock_code[1:]

                        if current_qty > 0: # 수량이 0 이상인 종목만 유효한 포지션으로 간주
                            holdings_list.append({
                                "stock_code": stock_code,
                                "name": item_name,
                                "quantity": current_qty,
                                "purchase_price": purchase_price,
                                "current_price": current_price,
                                "total_purchase_amount": total_purchase_amount,
                            })
                    self.tr_data = {"holdings": holdings_list} # "holdings" 키로 데이터를 저장
                    logger.info(f"TR 데이터 수신: {tr_code} - 보유 종목 {len(holdings_list)}개.")

            except Exception as e:
                logger.error(f"Error processing TR data for {tr_code}: {e}", exc_info=True)
                self.tr_data = {"error": f"TR 데이터 처리 오류: {str(e)}"}
            finally:
                # TR 응답을 받았으므로 전용 이벤트 루프 종료 (블로킹 해제)
                if self.tr_wait_event_loop.isRunning(): 
                    self.tr_wait_event_loop.exit()
        
    def _on_tr_timeout(self):
        """TR 요청 타임아웃 발생 시 호출되는 콜백."""
        if self.tr_wait_event_loop.isRunning(): 
            logger.error(f"[{get_current_time_str()}]: ❌ TR 요청 실패 - 타임아웃 ({self.rq_name}, {self.tr_wait_timer.interval()}ms)")
            self.tr_data = {"error": f"TR 요청 타임아웃 ({self.rq_name})"}
            self.tr_wait_event_loop.exit() # 이벤트 루프 강제 종료

    def _send_tr_request(self, rq_name, tr_code, sPrevNext, screen_no, timeout_ms=30000, retry_attempts=5, retry_delay_sec=5):
        """
        CommRqData를 호출하고 TR 응답을 기다리는 헬퍼 함수.
        TR 요청 실패 시 재시도 로직을 포함합니다.
        """
        for attempt in range(retry_attempts):
            self.rq_name = rq_name
            self.tr_data = None # 이전 데이터 초기화

            logger.info(f"TR 요청 시도 {attempt + 1}/{retry_attempts}: rq_name='{rq_name}', tr_code='{tr_code}', screen_no='{screen_no}'") 
            
            # API 요청 간 최소 지연 시간 (TR 요청 제한 회피)
            time.sleep(0.5) 

            result_code = self.kiwoom_helper.ocx.CommRqData(rq_name, tr_code, sPrevNext, screen_no)
            
            if result_code == 0: # TR 요청 함수 호출 성공
                self.tr_wait_timer.start(timeout_ms) # TR 응답 대기 타이머 시작
                self.tr_wait_event_loop.exec_() # TR 응답이 오거나 타임아웃 될 때까지 대기

                # 이벤트 루프 종료 후 타이머가 아직 활성 상태라면 중지
                if self.tr_wait_timer.isActive(): 
                    self.tr_wait_timer.stop()
                
                # TR 데이터가 성공적으로 수신되었는지 확인
                if self.tr_data is not None and not self.tr_data.get("error"):
                    logger.info(f"TR 요청 성공 및 데이터 수신: {rq_name}") 
                    return self.tr_data 
                elif self.tr_data and self.tr_data.get("error"):
                    # 데이터 처리 중 오류가 발생했거나 타임아웃으로 인한 오류 데이터
                    logger.warning(f"TR 요청 성공 후 응답 데이터 처리 오류: {self.tr_data['error']}. (재시도 중...)")
                    if attempt == retry_attempts - 1: # 마지막 시도라면 오류 반환
                        return self.tr_data 
                    time.sleep(retry_delay_sec) 
                    continue # 재시도
                else:
                    # 응답 데이터 자체가 None이거나 예상치 못한 상황 (재시도)
                    logger.warning(f"TR 요청 성공했으나 응답 데이터 없음 (내부 오류 또는 타임아웃). (재시도 중...)")
                    if attempt == retry_attempts - 1:
                        return {"error": f"TR 요청 응답 없음/내부 타임아웃: {rq_name}"}
                    time.sleep(retry_delay_sec) 
                    continue # 재시도

            else: # TR 요청 함수 호출 자체 실패 (CommRqData의 반환 코드)
                error_msg = self._get_error_message(result_code)
                logger.error(f"TR 요청 자체 실패: {rq_name} ({tr_code}) - 코드: {result_code} ({error_msg}). (재시도 중...)")
                if attempt == retry_attempts - 1: # 마지막 시도라면 최종 오류 반환
                    return {"error": f"TR 요청 최종 실패: {result_code} ({error_msg})"}
                time.sleep(retry_delay_sec) # 실패 시 재시도 전 대기
        
        return {"error": "알 수 없는 TR 요청 실패 (모든 재시도 소진)"} 

def request_account_info(self, account_no, timeout_ms=30000, retry_attempts=5, retry_delay_sec=5):
    self.kiwoom_helper.ocx.SetInputValue("계좌번호", account_no)
    
    masked_password = self.account_password[:2] + '*' * (len(self.account_password) - 4) + self.account_password[-2:] if len(self.account_password) > 4 else '*' * len(self.account_password)
    logger.info(f"SetInputValue: 계좌번호='{account_no}', 비밀번호='{masked_password}'")

    # ✅ 여기를 수정: 실제 비밀번호를 전달
    self.kiwoom_helper.ocx.SetInputValue("비밀번호", self.account_password)

    self.kiwoom_helper.ocx.SetInputValue("비밀번호입력매체구분", "00")
    self.kiwoom_helper.ocx.SetInputValue("조회구분", "2")

    screen_no = self._generate_unique_screen_no()

    return self._send_tr_request("opw00001_req", "opw00001", 0, screen_no, timeout_ms, retry_attempts, retry_delay_sec)

    def request_daily_account_holdings(self, account_no, timeout_ms=30000, retry_attempts=5, retry_delay_sec=5):
        """
        계좌 평가 현황 및 보유 종목 정보를 요청합니다 (opw00018).
        리스트 형태의 보유 종목 데이터를 반환합니다.
        """
        self.kiwoom_helper.ocx.SetInputValue("계좌번호", account_no)
        # opw00018은 계좌 비밀번호를 요구하지 않는 경우가 많지만, 안전을 위해 설정
        # 보안을 위해 비밀번호의 일부만 로그에 출력 (실제 Kiwoom API에는 빈 문자열 전달)
        masked_password = self.account_password[:2] + '*' * (len(self.account_password) - 4) + self.account_password[-2:] if len(self.account_password) > 4 else '*' * len(self.account_password)
        logger.info(f"SetInputValue: 계좌번호='{account_no}', 비밀번호='{masked_password}' (실제 API 전달 값: 빈 문자열), 비밀번호입력매체구분='00'")
        self.kiwoom_helper.ocx.SetInputValue("비밀번호", "") # 💡 모의투자 계좌의 경우 비밀번호를 공란으로 넘겨야 정상 작동
        self.kiwoom_helper.ocx.SetInputValue("비밀번호입력매체구분", "00")

        screen_no = self._generate_unique_screen_no()

        tr_response = self._send_tr_request("opw00018_req", "opw00018", 0, screen_no, timeout_ms, retry_attempts, retry_delay_sec)
        
        if tr_response and "holdings" in tr_response:
            return tr_response["holdings"]
        elif tr_response and "error" in tr_response:
            logger.error(f"보유 종목 요청 실패 (TR 헬퍼): {tr_response['error']}")
            return {"error": tr_response['error']} # 오류 발생 시 딕셔너리 형태로 반환
        else:
            logger.warning(f"TR 요청 성공했으나 opw00018 보유 종목 데이터 없음: {tr_response}")
            return [] # 데이터 없으면 빈 리스트 반환


    def _generate_unique_screen_no(self):
        """
        중복되지 않는 고유한 화면번호를 생성하여 반환합니다.
        화면번호는 2000 ~ 9999 사이의 값을 사용합니다.
        """
        unique_part = str(int(time.time() * 100000))[-4:] 
        screen_no = str(2000 + int(unique_part) % 7999) 
        return screen_no

    def _get_error_message(self, err_code):
        """Kiwoom API 에러 코드에 대한 설명을 반환합니다."""
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
