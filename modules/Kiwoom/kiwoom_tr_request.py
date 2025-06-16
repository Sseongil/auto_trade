# C:\Users\user\stock_auto\modules\Kiwoom\kiwoom_tr_request.py

import pythoncom
import win32com.client
import time
import logging

# ✅ 임포트 경로 수정됨: common 폴더 안의 config와 utils
from modules.common.config import DEFAULT_LOT_SIZE
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    def __init__(self, kiwoom_helper):
        self.kiwoom_helper = kiwoom_helper
        self.rqname_mapping = {}
        self.order_status = None
        
        # KiwoomQueryHelper에서 이미 이벤트를 처리하고 CommRqData에서 대기하므로,
        # 여기서는 추가적인 이벤트 핸들러 연결이 필요 없을 수 있습니다.
        # 단, SendOrder의 결과 메시지를 받기 위한 _handler_msg는 유지하는 것이 좋습니다.
        # self.kiwoom_helper.ocx.OnReceiveTrData.connect(self._handler_trdata) # KiwoomQueryHelper가 처리
        # self.kiwoom_helper.ocx.OnReceiveChejanData.connect(self._handler_chejan) # KiwoomQueryHelper가 처리

        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    # TR 데이터는 KiwoomQueryHelper._handler_trdata에서 처리하고 self.kiwoom_helper.tr_data에 저장됩니다.
    # 여기서는 직접 _handler_trdata를 구현하지 않습니다.

    def _handler_msg(self, sScrNo, sRQName, sTrCode, sMsg):
        logger.info(f"{get_current_time_str()}: TR Msg Received - ScrNo: {sScrNo}, RQName: {sRQName}, TrCode: {sTrCode}, Msg: {sMsg}")
        if sRQName.startswith("SendOrder_"): # SendOrder 관련 메시지 처리
            self.order_status = {"rqname": sRQName, "msg": sMsg, "tr_code": sTrCode}
            # 이 메시지는 SendOrder 호출 직후 바로 들어올 수 있습니다.
            # SendOrder는 CommRqData를 사용하지 않으므로, 이 메시지를 받고 다음 동작을 할 수 있도록
            # 별도의 이벤트 또는 콜백 메커니즘을 고려할 수 있습니다.
            # 현재는 SendOrder 자체가 동기적으로 응답을 기다리지 않으므로, 메시지 로그만 남깁니다.
            # 실제 주문의 체결 결과는 OnReceiveChejanData에서 처리되어야 합니다.

    # SendOrder는 CommRqData를 사용하지 않는 별도의 함수입니다.
    def send_order(self, rqname, screen_no, account_no, order_type, stock_code, quantity, price, hoga_gb, org_order_no=""):
        # self.order_status = None # 주문 전 초기화 (체결 정보는 체결 콜백에서)
        # SendOrder는 TR 대기 루프가 필요 없습니다.
        
        logger.info(f"{get_current_time_str()}: Sending order - RQName: {rqname}, Type: {order_type}, Code: {stock_code}, Qty: {quantity}, Price: {price}, Hoga: {hoga_gb}")

        ret = self.kiwoom_helper.ocx.SendOrder(
            rqname,
            screen_no,
            account_no,
            order_type, # 1: 매수, 2: 매도, 3: 매수취소, 4: 매도취소, 5: 매수정정, 6: 매도정정
            stock_code,
            quantity,
            price,
            hoga_gb,    # 00: 지정가, 03: 시장가
            org_order_no
        )

        if ret == 0:
            logger.info(f"{get_current_time_str()}: SendOrder Request Sent Successfully. Check OnReceiveMsg/OnReceiveChejanData for details.")
            return {"result": "success", "message": "주문 요청 성공"}
        else:
            error_msg = self.kiwoom_helper.ocx.GetErrorMessage(ret)
            logger.error(f"{get_current_time_str()}: SendOrder Failed. Error Code: {ret}, Message: {error_msg}")
            return {"result": "fail", "error_code": ret, "error_message": error_msg}

    def request_account_info(self, account_no, sPrevNext="0", screen_no="0001"):
        self.kiwoom_helper.set_input_value("계좌번호", account_no)
        self.kiwoom_helper.set_input_value("비밀번호", "") # 비밀번호 입력 매체 구분은 0: 미사용
        self.kiwoom_helper.set_input_value("상장폐지조회구분", "1") # 0: 전체, 1: 상장폐지제외
        self.kiwoom_helper.set_input_value("비밀번호입력매체구분", "0") # 0: 미사용

        rqname = "계좌평가현황요청"
        trcode = "opw00018"
        
        logger.info(f"{get_current_time_str()}: Requesting account info for {account_no} (TR: {trcode})")
        tr_result = self.kiwoom_helper.comm_rq_data(rqname, trcode, sPrevNext, screen_no)
        
        if tr_result and 'parsed_data' in tr_result:
            return tr_result['parsed_data']
        elif tr_result:
            logger.warning(f"{get_current_time_str()}: TR data received for account info but no specific parsed data available. Raw: {tr_result}")
            return {"message": "TR data received but no specific parsed data available.", "raw_tr_result": tr_result}
        else:
            return {"message": "Failed to retrieve account info TR data."}

    def request_current_price(self, stock_code, sPrevNext="0", screen_no="0002"):
        self.kiwoom_helper.set_input_value("종목코드", stock_code)
        
        rqname = "주식기본정보요청"
        trcode = "opt10001"
        
        logger.info(f"{get_current_time_str()}: Requesting current price for {stock_code} (TR: {trcode})")
        tr_result = self.kiwoom_helper.comm_rq_data(rqname, trcode, sPrevNext, screen_no)
        
        if tr_result and 'parsed_data' in tr_result:
            return tr_result['parsed_data']['현재가']
        elif tr_result:
            logger.warning(f"{get_current_time_str()}: Current price TR data received but no parsed_data: {tr_result}")
            return None
        else:
            logger.error(f"{get_current_time_str()}: Failed to retrieve current price TR data for {stock_code}.")
            return None