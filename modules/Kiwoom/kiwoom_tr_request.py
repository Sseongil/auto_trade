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
        
        self.tr_event_loop = QEventLoop()
        self.tr_timer = QTimer()
        self.tr_timer.setSingleShot(True) 
        self.tr_timer.timeout.connect(self._on_tr_timeout) 
        
        self.tr_data = None 
        self.rq_name = None 

        self.kiwoom_helper.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def _on_tr_timeout(self):
        """TR 요청 타임아웃 발생 시 호출되는 콜백."""
        if self.tr_event_loop.isRunning():
            logger.error(f"[{get_current_time_str()}]: ❌ TR 요청 타임아웃 발생: {self.rq_name}")
            self.tr_data = {"error": f"TR 요청 타임아웃: {self.rq_name}"}
            self.tr_event_loop.exit() 

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, sPrevNext, data_len, err_code, msg1, msg2):
        """TR 데이터 수신 이벤트 핸들러"""
        if rq_name == self.rq_name: 
            if self.tr_timer.isActive():
                self.tr_timer.stop()

            try:
                if tr_code == "opw00001": # 계좌 정보 요청 (예수금)
                    deposit = self.kiwoom_helper.ocx.CommGetData(
                        tr_code, "", rq_name, 0, "예수금" 
                    )
                    self.tr_data = {"예수금": int(deposit.strip())} 
                    logger.info(f"TR 데이터 수신: {tr_code} - 예수금: {deposit.strip()}")
                
                elif tr_code == "OPT10081": # 주식 일봉 차트 요청
                    data_cnt = self.kiwoom_helper.ocx.GetRepeatCnt(tr_code, rq_name)
                    daily_data_list = []
                    for i in range(data_cnt):
                        date = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "일자").strip()
                        open_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "시가").strip()))
                        high_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "고가").strip()))
                        low_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "저가").strip()))
                        close_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip())) 
                        volume = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "거래량").strip()))
                        
                        daily_data_list.append({
                            "날짜": date, "시가": open_price, "고가": high_price, 
                            "저가": low_price, "현재가": close_price, "거래량": volume
                        })
                    self.tr_data = {"data": daily_data_list, "sPrevNext": sPrevNext}
                    logger.info(f"TR 데이터 수신: {tr_code} - {data_cnt}개 일봉 데이터")
                
                elif tr_code == "OPT10080": # 주식 분봉/틱봉 차트 요청
                    data_cnt = self.kiwoom_helper.ocx.GetRepeatCnt(tr_code, rq_name)
                    five_min_data_list = []
                    for i in range(data_cnt):
                        date_time = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "체결시간").strip()
                        open_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "시가").strip()))
                        high_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "고가").strip()))
                        low_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "저가").strip()))
                        close_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip())) 
                        volume = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "거래량").strip()))
                        
                        five_min_data_list.append({
                            "체결시간": date_time, "시가": open_price, "고가": high_price, 
                            "저가": low_price, "현재가": close_price, "거래량": volume
                        })
                    self.tr_data = {"data": five_min_data_list, "sPrevNext": sPrevNext}
                    logger.info(f"TR 데이터 수신: {tr_code} - {data_cnt}개 5분봉 데이터")

                elif tr_code == "OPT10001": # 주식 기본 정보 요청 (시가총액 등)
                    # 💡 시가총액 파싱 로직 개선: 숫자만 추출하여 변환
                    market_cap_str = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "시가총액").strip()
                    market_cap = 0
                    if market_cap_str:
                        # 숫자만 남기도록 정규식 또는 replace 사용
                        import re
                        numeric_part = re.sub(r'[^0-9]', '', market_cap_str)
                        if numeric_part:
                            market_cap = int(numeric_part) # 키움은 원 단위로 시가총액을 반환하는 경우가 많음
                    
                    stock_basic_info = {
                        "종목코드": self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "종목코드").strip(),
                        "종목명": self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "종목명").strip(),
                        "시가총액": market_cap, 
                        "현재가": abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "현재가").strip())),
                    }
                    self.tr_data = stock_basic_info
                    logger.info(f"TR 데이터 수신: {tr_code} - {stock_basic_info.get('종목명')} 기본 정보")

                # 💡 opw00018: 계좌평가잔고내역요청 (보유 종목 리스트)
                elif tr_code == "opw00018":
                    # 단일 데이터 (총평가금액 등)
                    total_valuation_amount = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "총평가금액").strip())
                    total_profit_loss_amount = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "총손익금액").strip())
                    total_profit_loss_rate = float(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "총수익률(%)").strip())

                    # 멀티 데이터 (보유 종목별 상세 정보)
                    data_cnt = self.kiwoom_helper.ocx.GetRepeatCnt(tr_code, rq_name)
                    holdings_list = []
                    for i in range(data_cnt):
                        stock_code = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "종목번호").strip().replace('A', '') 
                        stock_name = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "종목명").strip()
                        quantity = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "보유수량").strip())
                        purchase_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "매입가").strip()))
                        current_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip()))
                        profit_loss = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "평가손익").strip())
                        profit_loss_rate = float(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "수익률(%)").strip())
                        
                        holdings_list.append({
                            "종목코드": stock_code,
                            "종목명": stock_name,
                            "보유수량": quantity,
                            "매입가": purchase_price,
                            "현재가": current_price,
                            "평가손익": profit_loss,
                            "수익률(%)": profit_loss_rate
                        })
                    
                    self.tr_data = {
                        "total_info": {
                            "총평가금액": total_valuation_amount,
                            "총손익금액": total_profit_loss_amount,
                            "총수익률(%)": total_profit_loss_rate
                        },
                        "data": holdings_list, 
                        "sPrevNext": sPrevNext 
                    }
                    logger.info(f"TR 데이터 수신: {tr_code} - {len(holdings_list)}개 보유 종목")


            except Exception as e:
                logger.error(f"Error processing TR data for {tr_code}: {e}", exc_info=True)
                self.tr_data = {"error": str(e)}
            finally:
                if self.tr_event_loop.isRunning():
                    self.tr_event_loop.exit()
        
    def _send_tr_request(self, rq_name, tr_code, sPrevNext, screen_no, timeout_ms=30000, retry_attempts=3, retry_delay_sec=5):
        """
        CommRqData를 호출하고 TR 응답을 기다리는 헬퍼 함수.
        TR 요청 실패 시 재시도 로직을 포함합니다.
        """
        for attempt in range(retry_attempts):
            self.rq_name = rq_name
            self.tr_data = None 

            logger.debug(f"TR 요청 시도 {attempt + 1}/{retry_attempts}: rq_name='{rq_name}', tr_code='{tr_code}', sPrevNext={sPrevNext}, screen_no='{screen_no}'")
            
            # 💡 TR 요청 간 짧은 대기 (API 제한 방지)
            time.sleep(0.2) # 0.2초 대기 (초당 5회 제한 고려)

            result_code = self.kiwoom_helper.ocx.CommRqData(rq_name, tr_code, sPrevNext, screen_no)
            
            if result_code == 0: # TR 요청 성공 (응답을 기다릴 준비 완료)
                self.tr_timer.start(timeout_ms) 
                self.tr_event_loop.exec_() 

                if self.tr_timer.isActive(): # 응답이 타임아웃 전에 도착한 경우 타이머 중지
                    self.tr_timer.stop()
                
                # TR 데이터가 성공적으로 수신되었거나, 오류가 반환된 경우 (ex: 데이터 없음)
                if self.tr_data is not None and not self.tr_data.get("error"):
                    return self.tr_data # 성공적으로 데이터 수신
                elif self.tr_data and self.tr_data.get("error"):
                    logger.warning(f"TR 요청 성공 후 데이터 처리 오류: {self.tr_data['error']}. 재시도 필요 시도.")
                    # TR 응답은 받았으나, 데이터 처리 중 오류가 발생한 경우 (내부 로직 오류)
                    # 이 경우 재시도가 의미 없을 수 있으나, API 통신 자체의 문제는 아니므로 마지막 시도에만 최종 에러 반환
                    if attempt == retry_attempts - 1:
                        return self.tr_data # 마지막 시도에서는 에러 반환
                    time.sleep(retry_delay_sec) # 재시도 전 대기
                    continue # 다음 재시도
                else:
                    logger.warning(f"TR 요청 성공 후 응답 데이터 없음 (타임아웃?). 재시도 필요 시도.")
                    # 응답이 오지 않아 tr_data가 None인 경우 (타임아웃)
                    if attempt == retry_attempts - 1:
                        return {"error": f"TR 요청 응답 없음/타임아웃: {rq_name}"}
                    time.sleep(retry_delay_sec) # 재시도 전 대기
                    continue # 다음 재시도

            else: # TR 요청 자체 실패 (CommRqData 호출 실패)
                error_msg = self._get_error_message(result_code)
                logger.error(f"TR 요청 자체 실패: {rq_name} ({tr_code}) - 코드: {result_code} ({error_msg}). 재시도 중...")
                if attempt == retry_attempts - 1:
                    return {"error": f"TR 요청 최종 실패: {result_code} ({error_msg})"}
                time.sleep(retry_delay_sec) # 재시도 전 대기
        
        return {"error": "알 수 없는 TR 요청 실패 (모든 재시도 소진)"} # 모든 재시도가 실패했을 경우

    def request_account_info(self, account_no, timeout_ms=30000):
        """
        계좌 정보를 요청하고 반환합니다.
        TR 코드: opw00001 (계좌평가현황요청 - 주로 예수금 등의 단일 정보)
        """
        self.kiwoom_helper.ocx.SetInputValue("계좌번호", account_no)
        # 💡 retry_attempts 및 retry_delay_sec를 전달하여 재시도 로직 적용
        return self._send_tr_request("opw00001_req", "opw00001", 0, "2000", timeout_ms, retry_attempts=5, retry_delay_sec=3)

    def request_daily_account_holdings(self, account_no, password="", prev_next="0", timeout_ms=60000):
        """
        계좌 평가 잔고 내역 (보유 종목 리스트)를 요청합니다 (opw00018).
        """
        self.kiwoom_helper.ocx.SetInputValue("계좌번호", account_no)
        # 💡 비밀번호는 .env에서 가져오도록 설정. 없으면 빈 문자열 사용.
        self.kiwoom_helper.ocx.SetInputValue("비밀번호", password) 
        self.kiwoom_helper.ocx.SetInputValue("비밀번호입력매체구분", "00") # 00: 키보드 (보통 고정)
        self.kiwoom_helper.ocx.SetInputValue("조회구분", "1") # 1: 총자산, 2: 개별종목

        prev_next_int = 0 if prev_next == "0" else 2 # 0: 조회, 2: 연속조회

        # 💡 retry_attempts 및 retry_delay_sec를 전달하여 재시도 로직 적용
        return self._send_tr_request(
            f"opw00018_req_{account_no}", "opw00018", prev_next_int, "2004", timeout_ms, retry_attempts=5, retry_delay_sec=3
        )

    def request_daily_ohlcv_data(self, stock_code, end_date, sPrevNext="0", timeout_ms=30000):
        """
        주식 일봉 차트 데이터를 요청합니다 (OPT10081).
        """
        self.kiwoom_helper.ocx.SetInputValue("종목코드", stock_code)
        self.kiwoom_helper.ocx.SetInputValue("기준일자", end_date)
        self.kiwoom_helper.ocx.SetInputValue("수정주가구분", "1") 
        
        prev_next_int = 0 if sPrevNext == "0" else 2
        
        return self._send_tr_request(
            f"OPT10081_req_{stock_code}", "OPT10081", prev_next_int, "2001", timeout_ms
        )

    def request_five_minute_ohlcv_data(self, stock_code, tick_unit="5", sPrevNext="0", timeout_ms=30000):
        """
        주식 분봉/틱봉 차트 데이터를 요청합니다 (OPT10080).
        """
        self.kiwoom_helper.ocx.SetInputValue("종목코드", stock_code)
        self.kiwoom_helper.ocx.SetInputValue("틱범위", tick_unit)
        self.kiwoom_helper.ocx.SetInputValue("수정주가구분", "1") 
        
        prev_next_int = 0 if sPrevNext == "0" else 2
        
        return self._send_tr_request(
            f"OPT10080_req_{stock_code}", "OPT10080", prev_next_int, "2002", timeout_ms 
        )

    def request_stock_basic_info(self, stock_code, timeout_ms=30000):
        """
        주식 기본 정보 (시가총액 등)를 요청합니다 (OPT10001).
        """
        self.kiwoom_helper.ocx.SetInputValue("종목코드", stock_code)
        
        return self._send_tr_request(
            f"OPT10001_req_{stock_code}", "OPT10001", 0, "2003", timeout_ms 
        )

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
        }
        return error_map.get(err_code, "알 수 없는 오류")

