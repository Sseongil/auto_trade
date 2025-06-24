# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
from PyQt5.QtCore import QEventLoop, QTimer # 💡 QEventLoop, QTimer 임포트
# QApplication은 이제 local_api_server에서 직접 관리하여 주입받습니다.
# from PyQt5.QtWidgets import QApplication 

from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    # 💡 __init__ 메서드 변경: pyqt_app을 인자로 받습니다.
    def __init__(self, kiwoom_helper, pyqt_app_instance):
        self.kiwoom_helper = kiwoom_helper 
        self.pyqt_app = pyqt_app_instance # 외부에서 생성된 QApplication 인스턴스를 받습니다.
        
        # TR 응답 대기를 위한 이벤트 루프는 주입받은 pyqt_app을 사용합니다.
        # QEventLoop를 사용하여 해당 TR 요청에 대한 응답만을 기다리도록 개선
        self.tr_event_loop = QEventLoop() 
        self.tr_timeout_timer = QTimer()
        self.tr_timeout_timer.setSingleShot(True)
        self.tr_timeout_timer.timeout.connect(self._on_tr_timeout) # 타임아웃 핸들러 연결
        
        self.tr_data = None 
        self.rq_name = None 
        self.sPrevNext = "0" # 연속 조회 기본값

        # QAxWidget의 OnReceiveTrData 이벤트를 연결합니다.
        self.kiwoom_helper.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def _on_tr_timeout(self):
        """TR 요청 타임아웃 발생 시 이벤트 루프를 종료합니다."""
        if self.tr_event_loop.isRunning():
            logger.warning(f"⚠️ TR 요청 '{self.rq_name}' 타임아웃 발생.")
            self.tr_data = {"error": "TR 응답 대기 타임아웃"}
            self.tr_event_loop.exit()

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, sPrevNext, data_len, err_code, msg1, msg2):
        """TR 데이터 수신 이벤트 핸들러"""
        #logger.debug(f"TR 데이터 수신: {rq_name}, {tr_code}, {sPrevNext}")
        # CommRqData 호출 시 지정했던 rq_name과 일치하는지 확인
        if rq_name == self.rq_name: 
            self.sPrevNext = sPrevNext # 다음 조회 가능 여부 업데이트

            try:
                # --- opw00001: 예수금상세현황요청 ---
                if tr_code == "opw00001":
                    예수금 = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "예수금").strip()
                    출금가능금액 = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "출금가능금액").strip()
                    주문가능금액 = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "주문가능금액").strip()
                    
                    self.tr_data = {
                        "예수금": int(예수금),
                        "출금가능금액": int(출금가능금액),
                        "주문가능금액": int(주문가능금액)
                    }
                    logger.info(f"TR 데이터 수신: {tr_code} - 예수금: {self.tr_data['예수금']:,}")

                # --- opw00018: 계좌평가현황요청 (보유 종목 조회) ---
                elif tr_code == "opw00018":
                    계좌명 = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "계좌명").strip()
                    총평가금액 = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "총평가금액").strip())
                    총매입금액 = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "총매입금액").strip())
                    총평가손익금액 = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "총평가손익금액").strip())
                    총수익률 = float(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "총수익률(%)").strip())

                    # 멀티 데이터 (보유 종목 리스트)
                    cnt = self.kiwoom_helper.ocx.GetRepeatCnt(tr_code, rq_name)
                    holdings = {}
                    for i in range(cnt):
                        종목코드 = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "종목코드").strip().replace('A', '') # A 제거
                        종목명 = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "종목명").strip()
                        보유수량 = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "보유수량").strip())
                        매입가 = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "매입가").strip())
                        현재가 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip())) # 절대값
                        평가손익 = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "평가손익").strip())
                        수익률 = float(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "수익률(%)").strip())

                        holdings[종목코드] = {
                            "name": 종목명,
                            "quantity": 보유수량,
                            "purchase_price": 매입가,
                            "current_price": 현재가,
                            "pnl_amount": 평가손익,
                            "pnl_pct": 수익률
                        }
                    
                    self.tr_data = {
                        "계좌명": 계좌명,
                        "총평가금액": 총평가금액,
                        "총매입금액": 총매입금액,
                        "총평가손익금액": 총평가손익금액,
                        "총수익률": 총수익률,
                        "holdings": holdings
                    }
                    logger.info(f"TR 데이터 수신: {tr_code} - 보유 종목 {len(holdings)}개.")

                # --- OPT10081: 주식일봉차트조회 ---
                elif tr_code == "OPT10081":
                    cnt = self.kiwoom_helper.ocx.GetRepeatCnt(tr_code, rq_name)
                    data_list = []
                    for i in range(cnt):
                        일자 = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "일자").strip()
                        시가 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "시가").strip()))
                        고가 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "고가").strip()))
                        저가 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "저가").strip()))
                        현재가 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip()))
                        거래량 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "거래량").strip()))
                        
                        data_list.append({
                            "날짜": 일자,
                            "시가": 시가,
                            "고가": 고가,
                            "저가": 저가,
                            "현재가": 현재가,
                            "거래량": 거래량
                        })
                    self.tr_data = {"data": data_list, "sPrevNext": sPrevNext}
                    logger.debug(f"TR 데이터 수신: {tr_code} - 일봉 {cnt}개. 연속조회: {sPrevNext}")

                # --- OPT10080: 주식분봉차트조회 ---
                elif tr_code == "OPT10080":
                    cnt = self.kiwoom_helper.ocx.GetRepeatCnt(tr_code, rq_name)
                    data_list = []
                    for i in range(cnt):
                        체결시간 = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "체결시간").strip()
                        시가 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "시가").strip()))
                        고가 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "고가").strip()))
                        저가 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "저가").strip()))
                        현재가 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip()))
                        거래량 = abs(int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "거래량").strip()))

                        data_list.append({
                            "체결시간": 체결시간,
                            "시가": 시가,
                            "고가": 고가,
                            "저가": 저가,
                            "현재가": 현재가,
                            "거래량": 거래량
                        })
                    self.tr_data = {"data": data_list, "sPrevNext": sPrevNext}
                    logger.debug(f"TR 데이터 수신: {tr_code} - 분봉 {cnt}개. 연속조회: {sPrevNext}")

                # --- OPT10001: 주식기본정보요청 (시가총액 등) ---
                elif tr_code == "OPT10001":
                    종목코드 = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "종목코드").strip().replace('A','')
                    시가총액 = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "시가총액").strip()) # 단위: 1주당 만원, 총합
                    # 시가총액은 억 단위로 가져올 수도 있음 (TR 문서 확인 필요)
                    # 여기서는 일단 원단위로 받아서 외부에서 변환한다고 가정
                    
                    self.tr_data = {
                        "종목코드": 종목코드,
                        "시가총액": 시가총액 # 원단위
                    }
                    logger.debug(f"TR 데이터 수신: {tr_code} - 종목: {종목코드}, 시가총액: {시가총액:,}")


            except Exception as e:
                logger.error(f"Error processing TR data for {tr_code}: {e}", exc_info=True)
                self.tr_data = {"error": str(e)}
            finally:
                # TR 응답을 받았으므로 이벤트 루프 종료 및 타이머 중지
                if self.tr_timeout_timer.isActive():
                    self.tr_timeout_timer.stop()
                if self.tr_event_loop.isRunning():
                    self.tr_event_loop.exit()
        
    def _send_tr_request(self, rq_name, tr_code, screen_no, input_values, sPrevNext="0", timeout_ms=30000):
        """범용 TR 요청 함수"""
        self.rq_name = rq_name
        self.tr_data = None 
        self.sPrevNext = sPrevNext

        for key, value in input_values.items():
            self.kiwoom_helper.ocx.SetInputValue(key, value)
        
        result = self.kiwoom_helper.ocx.CommRqData(rq_name, tr_code, sPrevNext, screen_no)
        
        if result == 0:
            self.tr_timeout_timer.start(timeout_ms) # 타임아웃 타이머 시작
            self.tr_event_loop.exec_() # TR 응답 대기
            
            if self.tr_data is None: # 타임아웃 등으로 데이터가 설정되지 않은 경우
                return {"error": "TR 응답 없음 또는 타임아웃"}
            return self.tr_data
        else:
            error_msg = self._get_error_message(result)
            logger.error(f"TR 요청 실패: {tr_code} ({rq_name}) - {result} ({error_msg})")
            return {"error": f"TR 요청 실패 코드: {result} ({error_msg})"}

    def request_account_info(self, account_no, timeout_ms=30000):
        """
        계좌 정보를 요청하고 반환합니다. (opw00001)
        """
        return self._send_tr_request(
            rq_name="예수금상세현황요청",
            tr_code="opw00001",
            screen_no="2000",
            input_values={
                "계좌번호": account_no,
                "비밀번호": "", # 비밀번호 필요 시 여기에 입력
                "비밀번호입력매체구분": "00",
                "조회구분": "2" # 1: 단일, 2: 복수
            },
            timeout_ms=timeout_ms
        )

    def request_daily_account_holdings(self, account_no, timeout_ms=30000):
        """
        계좌 보유 종목 및 평가 현황을 요청하고 반환합니다. (opw00018)
        """
        return self._send_tr_request(
            rq_name="계좌평가현황요청",
            tr_code="opw00018",
            screen_no="2001", # 다른 화면번호 사용
            input_values={
                "계좌번호": account_no
            },
            timeout_ms=timeout_ms
        )

    def request_daily_ohlcv_data(self, stock_code, end_date, sPrevNext="0", timeout_ms=30000):
        """
        주식 일봉 차트 데이터를 요청합니다. (OPT10081)
        Args:
            stock_code (str): 종목코드
            end_date (str): 기준일자 (YYYYMMDD)
            sPrevNext (str): 연속조회 여부 ("0": 조회, "2": 연속)
        """
        return self._send_tr_request(
            rq_name=f"일봉데이터요청_{stock_code}",
            tr_code="OPT10081",
            screen_no=self.kiwoom_helper.generate_real_time_screen_no(), # 임의 화면번호
            input_values={
                "종목코드": stock_code,
                "기준일자": end_date,
                "수정주가구분": "1" # 1: 수정주가 반영
            },
            sPrevNext=sPrevNext,
            timeout_ms=timeout_ms
        )

    def request_five_minute_ohlcv_data(self, stock_code, end_date, sPrevNext="0", timeout_ms=30000):
        """
        주식 분봉 차트 데이터를 요청합니다. (OPT10080)
        Args:
            stock_code (str): 종목코드
            end_date (str): 기준일자 (YYYYMMDD)
            sPrevNext (str): 연속조회 여부 ("0": 조회, "2": 연속)
        """
        return self._send_tr_request(
            rq_name=f"분봉데이터요청_{stock_code}",
            tr_code="OPT10080",
            screen_no=self.kiwoom_helper.generate_real_time_screen_no(), # 임의 화면번호
            input_values={
                "종목코드": stock_code,
                "틱범위": "5", # 5분봉
                "수정주가구분": "1"
            },
            sPrevNext=sPrevNext,
            timeout_ms=timeout_ms
        )
    
    def request_stock_basic_info(self, stock_code, timeout_ms=30000):
        """
        종목 기본 정보를 요청합니다. (OPT10001) - 시가총액 포함
        """
        return self._send_tr_request(
            rq_name=f"종목기본정보요청_{stock_code}",
            tr_code="OPT10001",
            screen_no=self.kiwoom_helper.generate_real_time_screen_no(), # 임의 화면번호
            input_values={
                "종목코드": stock_code
            },
            timeout_ms=timeout_ms
        )

    def _get_error_message(self, err_code):
        """Kiwoom API 에러 코드에 대한 설명을 반환합니다."""
        error_map = {
            0: "정상 처리",
            -10: "미접속",
            -100: "계좌정보 없음",
            -101: "계좌 비밀번호 없음",
            -102: "비정상적인 모듈 호출",
            -103: "종목코드 없음",
            -104: "계좌증거금율 오류",
            -105: "조건 검색 오류",
            -106: "통신 연결 종료",
            -107: "사용자 정보 없음",
            -108: "주문 가격 오류",
            -109: "주문 수량 오류",
            -110: "실시간 등록 오류",
            -111: "실시간 해제 오류",
            -112: "데이터 없음",
            -113: "API 미설정",
            -200: "전문 송수신 실패 (API 내부 오류)",
            -201: "정의되지 않은 TR 코드",
            -202: "TR 입력값 오류",
            -203: "조회 과도 제한",
            -204: "주문 과도 제한",
            -205: "데이터 요청 지연 (내부 타임아웃)",
            # 키움 Open API+ 개발 가이드에 있는 주요 에러 코드들을 추가할 수 있습니다.
        }
        return error_map.get(err_code, "알 수 없는 오류")

