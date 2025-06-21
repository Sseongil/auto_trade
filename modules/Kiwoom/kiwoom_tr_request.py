# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
# QApplication은 이제 local_api_server에서 직접 관리하여 주입받습니다.
# from PyQt5.QtWidgets import QApplication 

from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    # __init__ 메서드는 kiwoom_helper와 pyqt_app_instance (QApplication)를 인자로 받습니다.
    def __init__(self, kiwoom_helper, pyqt_app_instance):
        self.kiwoom_helper = kiwoom_helper 
        self.pyqt_app = pyqt_app_instance # 외부에서 생성된 QApplication 인스턴스를 받습니다.
        self.tr_event_loop = self.pyqt_app # TR 응답 대기를 위한 이벤트 루프는 주입받은 pyqt_app 사용
        
        self.tr_data = None 
        self.rq_name = None 

        # QAxWidget의 OnReceiveTrData 이벤트를 연결합니다.
        self.kiwoom_helper.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, sPrevNext, data_len, err_code, msg1, msg2):
        """TR 데이터 수신 이벤트 핸들러"""
        if rq_name == self.rq_name: # 현재 요청 중인 TR에 대한 응답인 경우
            try:
                # 계좌 정보 요청 (opw00001)에 대한 처리 예시
                if tr_code == "opw00001":
                    deposit = self.kiwoom_helper.ocx.CommGetData(
                        tr_code, "", rq_name, 0, "예수금" # TR 문서에 따라 필드명 정확히 확인 필요
                    )
                    self.tr_data = {"예수금": int(deposit)}
                    logger.info(f"TR 데이터 수신: {tr_code} - 예수금: {deposit}")
                
                # TODO: 다른 TR 코드에 대한 처리 로직 추가 (예: opw00018 등)
                # elif tr_code == "opw00018":
                #     # opw00018은 멀티 데이터 (보유 종목 리스트)를 포함할 수 있으므로,
                #     # GetRepeatCnt와 GetCommData를 사용하여 반복 처리해야 합니다.
                #     pass 

            except Exception as e:
                logger.error(f"Error processing TR data for {tr_code}: {e}")
                self.tr_data = {"error": str(e)}
            finally:
                # TR 응답을 받았으므로 이벤트 루프 종료 (블로킹 해제)
                if self.tr_event_loop.isRunning():
                    self.tr_event_loop.exit()
        
    def request_account_info(self, account_no):
        """
        계좌 정보를 요청하고 반환합니다.
        TR 코드: opw00001 (계좌평가현황요청 - 주로 예수금 등의 단일 정보)
        """
        self.rq_name = "opw00001_req"
        self.tr_data = None # 이전 데이터 초기화

        self.kiwoom_helper.ocx.SetInputValue("계좌번호", account_no)
        
        # CommRqData 호출
        # sScrNo: 화면번호 (임의의 고유 번호, 중복되지 않게 관리)
        # sRQName: TR 요청명 (_on_receive_tr_data에서 해당 요청을 구분하기 위함)
        # sTrCode: TR 코드
        # sPrevNext: 연속조회 (0: 연속조회 아님, 2: 연속조회)
        result = self.kiwoom_helper.ocx.CommRqData(
            self.rq_name, "opw00001", 0, "2000" # 화면번호는 임의로 설정. 여러 TR에 같은 화면번호 사용 시 충돌 주의
        )
        
        if result == 0:
            # TR 요청 성공 시, 데이터가 수신될 때까지 이벤트 루프 대기
            self.tr_event_loop.exec_() 
            return self.tr_data
        else:
            logger.error(f"계좌 정보 요청 실패: {result} ({self._get_error_message(result)})")
            return {"error": f"TR 요청 실패 코드: {result} ({self._get_error_message(result)})"}

    def _get_error_message(self, err_code):
        """Kiwoom API 에러 코드에 대한 설명을 반환합니다."""
        # 이전에 정의된 KIWOOM_ERROR_CODES 딕셔너리를 활용하거나 직접 정의
        # 현재는 이 함수가 정의되어 있지 않으므로 임시로 반환
        error_map = {
            -10: "미접속", -100: "계좌정보 없음", -101: "계좌 비밀번호 없음",
            -102: "비정상적인 모듈 호출", -103: "종목코드 없음", -104: "계좌증거금율 오류",
            -105: "조건 검색 오류", -106: "통신 연결 종료", -107: "사용자 정보 없음",
            -108: "주문 가격 오류", -109: "주문 수량 오류", -110: "실시간 등록 오류",
            -111: "실시간 해제 오류", -112: "데이터 없음", -113: "API 미설정",
            -202: "알 수 없는 오류 (계좌 관련 일반 오류일 수 있음)" # 💡 -202 코드에 대한 임의 설명 추가
            # 더 많은 에러 코드는 키움 Open API+ 개발 가이드 참고
        }
        return error_map.get(err_code, "알 수 없는 오류")

    # 필요한 다른 TR 요청 메서드들을 여기에 추가합니다.
    # 예: get_daily_ohlcv, get_current_price 등
