# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
from PyQt5.QtCore import QEventLoop, QTimer # 💡 QEventLoop와 QTimer 임포트

from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    # __init__ 메서드는 kiwoom_helper와 pyqt_app_instance (QApplication)를 인자로 받습니다.
    def __init__(self, kiwoom_helper, pyqt_app_instance):
        self.kiwoom_helper = kiwoom_helper 
        self.pyqt_app = pyqt_app_instance # 외부에서 생성된 QApplication 인스턴스를 받습니다.
        
        # 💡 TR 응답 대기를 위한 전용 QEventLoop와 QTimer
        self.tr_event_loop = QEventLoop()
        self.tr_timer = QTimer()
        self.tr_timer.setSingleShot(True) # 타이머 1회성 설정
        self.tr_timer.timeout.connect(self._on_tr_timeout) # 타임아웃 시 콜백 연결
        
        self.tr_data = None 
        self.rq_name = None 

        # QAxWidget의 OnReceiveTrData 이벤트를 연결합니다.
        self.kiwoom_helper.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def _on_tr_timeout(self):
        """TR 요청 타임아웃 발생 시 호출되는 콜백."""
        if self.tr_event_loop.isRunning():
            logger.error(f"[{get_current_time_str()}]: ❌ TR 요청 타임아웃 발생: {self.rq_name}")
            self.tr_data = {"error": f"TR 요청 타임아웃: {self.rq_name}"}
            self.tr_event_loop.exit() # 이벤트 루프 강제 종료

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, sPrevNext, data_len, err_code, msg1, msg2):
        """TR 데이터 수신 이벤트 핸들러"""
        # 💡 현재 요청 중인 TR에 대한 응답인지 확인 (다른 TR 응답이 들어올 수 있으므로)
        if rq_name == self.rq_name: 
            # 💡 TR 응답이 오면 타이머를 즉시 중지
            if self.tr_timer.isActive():
                self.tr_timer.stop()

            try:
                if tr_code == "opw00001": # 계좌 정보 요청 (예수금)
                    deposit = self.kiwoom_helper.ocx.CommGetData(
                        tr_code, "", rq_name, 0, "예수금" 
                    )
                    self.tr_data = {"예수금": int(deposit.strip())} # .strip() 추가
                    logger.info(f"TR 데이터 수신: {tr_code} - 예수금: {deposit.strip()}")
                
                elif tr_code == "OPT10081": # 주식 일봉 차트 요청
                    data_cnt = self.kiwoom_helper.ocx.GetRepeatCnt(tr_code, rq_name)
                    daily_data_list = []
                    for i in range(data_cnt):
                        date = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "일자").strip()
                        open_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "시가").strip()))
                        high_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "고가").strip()))
                        low_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "저가").strip()))
                        close_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip())) # '현재가'는 해당 일봉의 종가
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
                        close_price = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip())) # '현재가'는 해당 봉의 종가
                        volume = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "거래량").strip()))
                        
                        five_min_data_list.append({
                            "체결시간": date_time, "시가": open_price, "고가": high_price, 
                            "저가": low_price, "현재가": close_price, "거래량": volume
                        })
                    self.tr_data = {"data": five_min_data_list, "sPrevNext": sPrevNext}
                    logger.info(f"TR 데이터 수신: {tr_code} - {data_cnt}개 5분봉 데이터")

                elif tr_code == "OPT10001": # 주식 기본 정보 요청 (시가총액 등)
                    market_cap_str = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "시가총액").strip()
                    market_cap = 0
                    if market_cap_str:
                        # 시가총액이 "1조 2,345억" 형식으로 올 수 있으므로 숫자만 추출
                        # 키움 API는 시가총액을 실제 값으로 주기도 하므로, 문자열 처리 방식이 다를 수 있음
                        # 여기서는 간단히 숫자로만 변환 시도. (실제 값은 원 단위로 가정)
                        market_cap = int(market_cap_str.replace(",", "").replace(" ", "").replace("조", "000000000000").replace("억", "00000000")) # 💡 숫자만 추출 및 변환 개선
                        # 실제 시가총액이 원 단위로 올 경우, config에서 억 단위로 나눌 때 사용
                        
                    stock_basic_info = {
                        "종목코드": self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "종목코드").strip(),
                        "종목명": self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "종목명").strip(),
                        "시가총액": market_cap, # 원 단위로 저장
                        "현재가": abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "현재가").strip())),
                    }
                    self.tr_data = stock_basic_info
                    logger.info(f"TR 데이터 수신: {tr_code} - {stock_basic_info.get('종목명')} 기본 정보")

            except Exception as e:
                logger.error(f"Error processing TR data for {tr_code}: {e}", exc_info=True)
                self.tr_data = {"error": str(e)}
            finally:
                # TR 응답을 받았으므로 이벤트 루프 종료 (블로킹 해제)
                if self.tr_event_loop.isRunning():
                    self.tr_event_loop.exit()
        
    def _send_tr_request(self, rq_name, tr_code, sPrevNext, screen_no, timeout_ms=30000):
        """
        CommRqData를 호출하고 TR 응답을 기다리는 헬퍼 함수.
        Args:
            rq_name (str): TR 요청명 (식별자)
            tr_code (str): TR 코드 (예: "opw00001", "OPT10081")
            sPrevNext (int): 연속조회 여부 (0: 조회, 2: 연속)
            screen_no (str): 화면 번호
            timeout_ms (int): 응답 대기 타임아웃 (밀리초)
        Returns:
            dict: TR 응답 데이터 또는 오류 정보
        """
        self.rq_name = rq_name
        self.tr_data = None # 이전 데이터 초기화

        logger.debug(f"TR 요청: rq_name='{rq_name}', tr_code='{tr_code}', sPrevNext={sPrevNext}, screen_no='{screen_no}'")
        
        # 💡 CommRqData 호출 시 인자 순서 확인: (sRQName, sTrCode, nPrevNext, sScreenNo)
        # Type error: 'str' to 'int' for argument 2 (sTrCode)
        # This error is counter-intuitive if sTrCode is expected as string.
        # Let's explicitly check types for debugging.
        # logger.debug(f"CommRqData types: arg1({type(rq_name)}), arg2({type(tr_code)}), arg3({type(sPrevNext)}), arg4({type(screen_no)})")

        result = self.kiwoom_helper.ocx.CommRqData(rq_name, tr_code, sPrevNext, screen_no)
        
        if result == 0:
            # TR 요청 성공 시, 데이터가 수신될 때까지 이벤트 루프 대기
            self.tr_timer.start(timeout_ms) # 타임아웃 타이머 시작
            self.tr_event_loop.exec_() # _on_receive_tr_data에서 exit() 호출됨

            if self.tr_timer.isActive(): # 응답이 타임아웃 전에 도착한 경우 타이머 중지
                self.tr_timer.stop()
            else: # 타이머가 만료된 경우 (타임아웃 발생)
                # 이 경우는 _on_tr_timeout에서 이미 self.tr_data가 설정되었을 것임
                return self.tr_data # 타임아웃 오류 메시지가 이미 포함됨

            return self.tr_data
        else:
            error_msg = self._get_error_message(result)
            logger.error(f"TR 요청 실패: {rq_name} ({tr_code}) - 코드: {result} ({error_msg})")
            return {"error": f"TR 요청 실패: {result} ({error_msg})"}

    def request_account_info(self, account_no, timeout_ms=30000):
        """
        계좌 정보를 요청하고 반환합니다.
        TR 코드: opw00001 (계좌평가현황요청 - 주로 예수금 등의 단일 정보)
        """
        self.kiwoom_helper.ocx.SetInputValue("계좌번호", account_no)
        # 화면번호는 임의로 설정. 여러 TR에 같은 화면번호 사용 시 충돌 주의
        return self._send_tr_request("opw00001_req", "opw00001", 0, "2000", timeout_ms)

    def request_daily_ohlcv_data(self, stock_code, end_date, sPrevNext="0", timeout_ms=30000):
        """
        주식 일봉 차트 데이터를 요청합니다 (OPT10081).
        Args:
            stock_code (str): 종목코드
            end_date (str): 기준일자 (YYYYMMDD)
            sPrevNext (str): 연속조회 여부 ("0": 조회, "2": 연속)
            timeout_ms (int): 타임아웃 (밀리초)
        Returns:
            dict: 일봉 데이터 또는 오류 정보
        """
        self.kiwoom_helper.ocx.SetInputValue("종목코드", stock_code)
        self.kiwoom_helper.ocx.SetInputValue("기준일자", end_date)
        self.kiwoom_helper.ocx.SetInputValue("수정주가구분", "1") # 1: 수정주가 반영
        
        # CommRqData의 sPrevNext는 int 타입이므로, "0" 또는 "2"를 int로 변환
        prev_next_int = 0 if sPrevNext == "0" else 2
        
        return self._send_tr_request(
            f"OPT10081_req_{stock_code}", "OPT10081", prev_next_int, "2001", timeout_ms # 화면번호 고유하게 설정 (2001)
        )

    def request_five_minute_ohlcv_data(self, stock_code, tick_unit="5", sPrevNext="0", timeout_ms=30000):
        """
        주식 분봉/틱봉 차트 데이터를 요청합니다 (OPT10080).
        Args:
            stock_code (str): 종목코드
            tick_unit (str): 틱범위 (1, 3, 5, 10, 15, 30, 45, 60분 등)
            sPrevNext (str): 연속조회 여부 ("0": 조회, "2": 연속)
            timeout_ms (int): 타임아웃 (밀리초)
        Returns:
            dict: 분봉/틱봉 데이터 또는 오류 정보
        """
        self.kiwoom_helper.ocx.SetInputValue("종목코드", stock_code)
        self.kiwoom_helper.ocx.SetInputValue("틱범위", tick_unit)
        self.kiwoom_helper.ocx.SetInputValue("수정주가구분", "1") # 1: 수정주가 반영
        
        prev_next_int = 0 if sPrevNext == "0" else 2
        
        return self._send_tr_request(
            f"OPT10080_req_{stock_code}", "OPT10080", prev_next_int, "2002", timeout_ms # 화면번호 고유하게 설정 (2002)
        )

    def request_stock_basic_info(self, stock_code, timeout_ms=30000):
        """
        주식 기본 정보 (시가총액 등)를 요청합니다 (OPT10001).
        Args:
            stock_code (str): 종목코드
            timeout_ms (int): 타임아웃 (밀리초)
        Returns:
            dict: 기본 정보 데이터 또는 오류 정보
        """
        self.kiwoom_helper.ocx.SetInputValue("종목코드", stock_code)
        
        return self._send_tr_request(
            f"OPT10001_req_{stock_code}", "OPT10001", 0, "2003", timeout_ms # 화면번호 고유하게 설정 (2003)
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

