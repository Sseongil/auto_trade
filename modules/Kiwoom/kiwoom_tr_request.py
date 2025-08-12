# modules/Kiwoom/kiwoom_tr_request.py

import logging
import time
from PyQt5.QtCore import QEventLoop, QTimer
from modules.common.error_codes import get_error_message
from modules.Kiwoom.tr_event_loop import TrEventLoop

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    """
    키움증권 OpenAPI의 TR(Transaction) 요청을 처리하는 클래스입니다.
    TR 요청을 보내고, 응답을 수신하며, 데이터를 파싱하는 역할을 수행합니다.
    """
    def __init__(self, kiwoom_helper, pyqt_app, account_password):
        self.kiwoom_helper = kiwoom_helper
        self.app = pyqt_app
        self.account_password = account_password
        self.tr_event_loop = TrEventLoop.instance() # TR 이벤트 루프 싱글턴 인스턴스 사용

        # 키움 API의 OnReceiveTrData 시그널을 이 클래스의 핸들러 메서드에 연결합니다.
        self.kiwoom_helper.kiwoom.OnReceiveTrData.connect(self._on_receive_tr_data)
        self.kiwoom_helper.kiwoom.OnReceiveConditionVer.connect(self._on_receive_condition_ver)
        self.kiwoom_helper.kiwoom.OnReceiveConditionVer.connect(self._on_receive_tr_condition)
        
        logger.info("KiwoomTrRequest initialized with event connection.")

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, prev_next, data_len, tr_cheabun):
        """
        Kiwoom API로부터 TR 데이터를 수신하면 호출되는 이벤트 핸들러입니다.
        수신된 데이터를 TrEventLoop에 전달하여 대기 중인 루프를 해제합니다.
        """
        logger.info(f"TR 데이터 수신: {rq_name}, TR 코드: {tr_code}")
        # TrEventLoop의 set_tr_meta 메서드를 호출하여 TR 응답이 도착했음을 알립니다.
        self.tr_event_loop.set_tr_meta(rq_name, tr_code, screen_no)

    def _on_receive_condition_ver(self, ret, msg):
        """
        조건식 버전 수신 시 호출되는 이벤트 핸들러입니다.
        """
        status = True if ret == 1 else False
        self.tr_event_loop.set_condition_version_received(status)
        logger.info(f"조건식 버전 수신 완료: {status}, 메시지: {msg}")

    def _on_receive_tr_condition(self, screen_no, stock_code, condition_name, condition_index, search_type):
        """
        TR 조건 검색 결과 수신 시 호출되는 이벤트 핸들러입니다.
        """
        # 이 부분은 조건식 검색 결과 수신 시 호출되지만, 
        # 실제 데이터 처리는 GetConditionLoad API를 통해 이루어지므로,
        # TrEventLoop의 wait_for_tr_condition_data와 연동하는 로직이 필요합니다.
        # (이 로직은 KiwoomTrRequest에 직접 구현되거나 별도의 클래스에서 처리될 수 있습니다.)
        pass

    def _get_comm_data(self, tr_code, record_name, index, item_name):
        """TR 데이터를 가져옵니다."""
        return self.kiwoom_helper.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)",
                                                     tr_code, record_name, index, item_name).strip()

    def _get_repeat_cnt(self, tr_code, record_name):
        """반복되는 데이터의 개수를 가져옵니다."""
        return self.kiwoom_helper.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, record_name)

    def get_tr_data(self, rq_name, tr_code, screen_no, record_name=None, output_items=None, timeout=10):
        """
        TR 요청 후 데이터를 수신 대기하고 파싱합니다.
        output_items: TR에서 가져올 필드명 리스트 (예: ["현재가", "거래량"])
        """
        # TrEventLoop를 사용하여 TR 응답을 기다립니다.
        if not self.tr_event_loop.wait_for_tr_data(rq_name, tr_code, screen_no, timeout):
            logger.warning(f"TR 데이터 ({rq_name}, {tr_code}) 수신 타임아웃.")
            return None

        # 타임아웃이 아닌 경우, 수신된 데이터를 파싱합니다.
        data = {}
        if output_items:
            # 싱글 데이터 파싱
            for item in output_items:
                data[item] = self._get_comm_data(tr_code, record_name, 0, item)

        repeat_data = []
        repeat_cnt = self._get_repeat_cnt(tr_code, record_name)
        if repeat_cnt > 0 and output_items:
            # 반복 데이터 파싱
            for i in range(repeat_cnt):
                row_data = {}
                for item in output_items:
                    row_data[item] = self._get_comm_data(tr_code, record_name, i, item)
                repeat_data.append(row_data)

        return {"data": data, "repeat_data": repeat_data}

    # request_account_info, request_account_positions 등은 변경 없이 그대로 사용
    def request_account_info(self, account_number):
        """계좌번호별 예수금 정보를 요청합니다 (opw00001)."""
        rq_name = "opw00001_req"
        tr_code = "opw00001"
        screen_no = self.kiwoom_helper.generate_screen_no()

        self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "계좌번호", account_number)
        self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "비밀번호", self.account_password)
        self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "상장폐지구분", "0")
        self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "00")

        ret = self.kiwoom_helper.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", rq_name, tr_code, 0, screen_no)
        
        if ret == 0:
            logger.info(f"TR 요청 성공: {rq_name} (계좌번호: {account_number})")
            data = self.get_tr_data(rq_name, tr_code, screen_no,
                                    record_name="opw00001",
                                    output_items=["예수금", "출금가능금액", "주문가능금액"])
            if data and data.get("data"):
                deposit = data["data"].get("예수금", "").strip()
                withdrawal_possible = data["data"].get("출금가능금액", "").strip()
                order_possible = data["data"].get("주문가능금액", "").strip()
                return {
                    "예수금": int(deposit) if deposit else 0,
                    "출금가능금액": int(withdrawal_possible) if withdrawal_possible else 0,
                    "주문가능금액": int(order_possible) if order_possible else 0
                }
            else:
                logger.warning(f"계좌 정보 TR 데이터 파싱 실패 또는 데이터 없음: {rq_name}")
                return {"예수금": 0, "출금가능금액": 0, "주문가능금액": 0}
        else:
            error_msg = get_error_message(ret)
            logger.error(f"❌ TR 요청 실패: {rq_name} (계좌번호: {account_number}), 오류: {error_msg}")
            return {"예수금": 0, "출금가능금액": 0, "주문가능금액": 0, "error": error_msg}

    def request_account_positions(self, account_number):
        """계좌평가현황 및 잔고를 요청합니다 (opw00018)."""
        rq_name = "opw00018_req"
        tr_code = "opw00018"
        screen_no = self.kiwoom_helper.generate_screen_no()

        self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "계좌번호", account_number)
        self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "비밀번호", self.account_password)
        self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "상장폐지구분", "0")
        self.kiwoom_helper.kiwoom.dynamicCall("SetInputValue(QString, QString)", "비밀번호입력매체구분", "00")

        ret = self.kiwoom_helper.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", rq_name, tr_code, 0, screen_no)

        if ret == 0:
            logger.info(f"TR 요청 성공: {rq_name} (계좌번호: {account_number})")
            data = self.get_tr_data(rq_name, tr_code, screen_no,
                                    record_name="opw00018",
                                    output_items=[
                                        "종목코드", "종목명", "현재가", "매입가", "보유수량",
                                        "수익률", "평가손익", "대출일"
                                    ])
            if data and data.get("repeat_data"):
                positions = {}
                for item in data["repeat_data"]:
                    stock_code = item.get("종목코드", "").strip()
                    if stock_code:
                        current_price = item.get("현재가", "").strip()
                        purchase_price = item.get("매입가", "").strip()
                        quantity = item.get("보유수량", "").strip()
                        profit_rate = item.get("수익률", "").strip()
                        profit_loss = item.get("평가손익", "").strip()

                        positions[stock_code] = {
                            "name": item.get("종목명", "").strip(),
                            "current_price": int(current_price) if current_price else 0,
                            "purchase_price": int(purchase_price) if purchase_price else 0,
                            "quantity": int(quantity) if quantity else 0,
                            "profit_rate": float(profit_rate) if profit_rate else 0.0,
                            "profit_loss": int(profit_loss) if profit_loss else 0,
                            "loan_date": item.get("대출일", "").strip()
                        }
                return positions
            else:
                logger.warning(f"계좌평가현황 TR 데이터 파싱 실패 또는 데이터 없음: {rq_name}")
                return {}
        else:
            error_msg = get_error_message(ret)
            logger.error(f"❌ TR 요청 실패: {rq_name} (계좌번호: {account_number}), 오류: {error_msg}")
            return {"error": error_msg}
