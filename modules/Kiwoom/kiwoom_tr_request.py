# modules/Kiwoom/kiwoom_tr_request.py

import logging
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class KiwoomTrRequest:
    def __init__(self, kiwoom_helper):
        self.kiwoom_helper = kiwoom_helper
        logger.info(f"{get_current_time_str()}: KiwoomTrRequest initialized.")

    def send_order(self, rqname, screen_no, account_no, order_type, stock_code, quantity, price, hoga_gb, org_order_no=""):
        ret = self.kiwoom_helper.ocx.SendOrder(
            rqname,
            screen_no,
            account_no,
            order_type,
            stock_code,
            quantity,
            price,
            hoga_gb,
            org_order_no
        )
        if ret == 0:
            logger.info(f"{get_current_time_str()}: SendOrder Success.")
            return {"result": "success", "message": "주문 요청 성공"}
        else:
            error_msg = self.kiwoom_helper.ocx.GetErrorMessage(ret)
            logger.error(f"{get_current_time_str()}: SendOrder Failed. Error Code: {ret}, Message: {error_msg}")
            return {"result": "fail", "error_code": ret, "error_message": error_msg}

    def request_account_info(self, account_no, sPrevNext="0", screen_no="0001"):
        self.kiwoom_helper.set_input_value("계좌번호", account_no)
        self.kiwoom_helper.set_input_value("비밀번호", "")
        self.kiwoom_helper.set_input_value("상장폐지조회구분", "1")
        self.kiwoom_helper.set_input_value("비밀번호입력매체구분", "0")

        rqname = "계좌평가현황요청"
        trcode = "opw00018"

        logger.info(f"{get_current_time_str()}: Requesting account info for {account_no} (TR: {trcode})")
        tr_result = self.kiwoom_helper.comm_rq_data(rqname, trcode, sPrevNext, screen_no)

        if tr_result and 'parsed_data' in tr_result:
            return tr_result['parsed_data']
        return None

    def request_current_price(self, stock_code, sPrevNext="0", screen_no="0002"):
        self.kiwoom_helper.set_input_value("종목코드", stock_code)
        rqname = "주식기본정보요청"
        trcode = "opt10001"

        logger.info(f"{get_current_time_str()}: Requesting current price for {stock_code} (TR: {trcode})")
        tr_result = self.kiwoom_helper.comm_rq_data(rqname, trcode, sPrevNext, screen_no)

        if tr_result and 'parsed_data' in tr_result:
            return tr_result['parsed_data']['현재가']
        return None
