# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
from PyQt5.QtWidgets import QApplication # PyQt5 QApplication 임포트 (키움 OCX 사용을 위해 필요)
from PyQt5.QtCore import QEventLoop, QTimer # 💡 QEventLoop, QTimer 임포트

# 누락된 get_current_time_str 함수 임포트
from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    def __init__(self, kiwoom_helper):
        self.kiwoom_helper = kiwoom_helper # KiwoomQueryHelper 인스턴스
        # TR 응답 대기를 위한 이벤트 루프. __init__에서 생성된 QApplication 객체 사용하도록 수정
        # self.tr_event_loop = QApplication([]) # QApplication은 메인 스레드에서만 생성되어야 하므로 수정 필요
        # 💡 QApplication 인스턴스를 직접 받거나, QEventLoop만 사용하도록 합니다.
        #    여기서는 PyQt5 애플리케이션 루프를 직접 받는 대신, QEventLoop만 사용합니다.
        self.tr_event_loop = QEventLoop()
        self.tr_timeout_timer = QTimer()
        self.tr_timeout_timer.setSingleShot(True)
        self.tr_timeout_timer.timeout.connect(self._on_tr_timeout)

        self.tr_data = None # TR 요청 결과 데이터
        self.rq_name = None # 현재 요청 중인 TR의 rq_name

        # KiwoomQueryHelper (또는 Kiwoom API 컨트롤)의 OnReceiveTrData 이벤트를 연결
        # 이 이벤트는 TR 요청에 대한 응답을 받을 때 호출됩니다.
        self.kiwoom_helper.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def _on_tr_timeout(self):
        """TR 요청 타임아웃 발생 시 호출됩니다."""
        if self.tr_event_loop.isRunning():
            logger.error(f"[{get_current_time_str()}]: ❌ TR 요청 실패 - 타임아웃 ({self.rq_name})")
            self.tr_data = {"error": "TR 요청 타임아웃"}
            self.tr_event_loop.exit()

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, sPrevNext, data_len, err_code, msg1, msg2):
        """TR 데이터 수신 이벤트 핸들러"""
        if self.tr_timeout_timer.isActive(): # 타임아웃 타이머가 활성화되어 있으면 중지
            self.tr_timeout_timer.stop()

        if rq_name == self.rq_name: # 현재 요청 중인 TR에 대한 응답인 경우
            try:
                if tr_code == "opw00001": # 계좌 정보 요청
                    deposit = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "예수금")
                    # 예수금 외에 다른 정보도 필요하면 여기에 추가 가능
                    self.tr_data = {"예수금": int(deposit)}
                    logger.info(f"TR 데이터 수신: {tr_code} - 예수금: {deposit}")
                
                elif tr_code == "opw00018": # 💡 계좌 보유 종목 정보 요청
                    # Single Data (보유 종목 총계 정보)
                    total_pnl_amt = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "총평가손익금액").strip()
                    total_pnl_pct = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, 0, "총수익률(%)").strip()

                    # Multi Data (각 보유 종목 상세 정보)
                    repeat_cnt = self.kiwoom_helper.ocx.GetRepeatCnt(tr_code, rq_name)
                    holdings = {}
                    for i in range(repeat_cnt):
                        stock_code = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "종목번호").strip()
                        stock_name = self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "종목명").strip()
                        current_price = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "현재가").strip().replace('+', '').replace('-', ''))
                        purchase_price = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "매입가").strip())
                        quantity = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "보유수량").strip())
                        pnl_amount = int(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "평가손익").strip())
                        pnl_pct = float(self.kiwoom_helper.ocx.CommGetData(tr_code, "", rq_name, i, "수익률(%)").strip())

                        # 'A' 접두사 제거
                        if stock_code.startswith('A'):
                            stock_code = stock_code[1:]

                        holdings[stock_code] = {
                            "name": stock_name,
                            "current_price": current_price,
                            "purchase_price": purchase_price,
                            "quantity": quantity,
                            "pnl_amount": pnl_amount,
                            "pnl_pct": pnl_pct
                        }
                    self.tr_data = {
                        "total_pnl_amount": int(total_pnl_amt),
                        "total_pnl_pct": float(total_pnl_pct),
                        "holdings": holdings
                    }
                    logger.info(f"TR 데이터 수신: {tr_code} - 보유 종목 {len(holdings)}개.")
                
                # 다른 TR 코드에 대한 처리 로직 추가...

            except Exception as e:
                logger.error(f"Error processing TR data for {tr_code} ({rq_name}): {e}", exc_info=True)
                self.tr_data = {"error": str(e)}
            finally:
                if self.tr_event_loop.isRunning():
                    self.tr_event_loop.exit()
        
    def request_tr_data(self, tr_code, rq_name, input_values, next_page=0, timeout_ms=30000):
        """
        일반화된 TR 데이터 요청 함수.
        Args:
            tr_code (str): TR 코드 (예: "opw00001", "opt10081")
            rq_name (str): TR 요청명 (사용자 정의)
            input_values (dict): SetInputValue에 사용할 딕셔너리 {입력명: 값}
            next_page (int): 연속 조회 여부 (0: 단일 조회, 2: 연속 조회)
            timeout_ms (int): TR 응답 대기 타임아웃 (밀리초)
        Returns:
            dict or list: TR 응답 데이터 또는 오류 정보.
        """
        self.rq_name = rq_name
        self.tr_data = None

        for key, value in input_values.items():
            self.kiwoom_helper.ocx.SetInputValue(key, value)
        
        result_code = self.kiwoom_helper.ocx.CommRqData(
            rq_name, tr_code, next_page, "2000" # 화면번호는 임의로 설정, 연속조회는 next_page
        )
        
        if result_code == 0:
            self.tr_timeout_timer.start(timeout_ms)
            self.tr_event_loop.exec_()
            if self.tr_data is None: # 타임아웃 등으로 데이터가 None인 경우
                return {"error": "TR 응답 없음 또는 타임아웃"}
            return self.tr_data
        else:
            error_message = self.kiwoom_helper.ocx.CommGetConnectState() # 연결 상태로 오류 메시지 확인
            logger.error(f"TR 요청 실패: {tr_code}, {rq_name}, 코드: {result_code}, 메시지: {error_message}")
            return {"error": f"TR 요청 실패 코드: {result_code}, 메시지: {error_message}"}

    def request_account_info(self, account_no, timeout_ms=30000):
        """
        계좌 정보를 요청하고 반환합니다. (opw00001)
        """
        return self.request_tr_data(
            tr_code="opw00001",
            rq_name="예수금상세현황요청",
            input_values={"계좌번호": account_no, "비밀번호": "", "비밀번호입력매체구분": "00", "조회구분": "2"},
            timeout_ms=timeout_ms
        )

    def request_daily_account_holdings(self, account_no, timeout_ms=30000):
        """
        계좌 보유 종목 정보를 요청하고 반환합니다. (opw00018)
        """
        return self.request_tr_data(
            tr_code="opw00018",
            rq_name="계좌평가현황요청",
            input_values={"계좌번호": account_no, "비밀번호": "", "상장폐지구분": "0", "비밀번호입력매체구분": "00"},
            timeout_ms=timeout_ms
        )

