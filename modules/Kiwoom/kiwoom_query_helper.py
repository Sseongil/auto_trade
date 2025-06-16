# C:\Users\user\stock_auto\modules\Kiwoom\kiwoom_query_helper.py

import pythoncom
import win32com.client
import ctypes
import pandas as pd
import time
import os
from datetime import datetime
import logging

# ✅ 임포트 경로 수정됨: common 폴더 안의 config와 utils
from modules.common.config import POSITIONS_FILE_PATH, DEFAULT_LOT_SIZE
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    def __init__(self):
        self.ocx = win32com.client.Dispatch("KHOPENAPI.KHOpenAPICtrl.1")
        self.event_handlers = {}
        self.tr_data = None
        self.tr_event_loop = None
        self.connect_event_loop = None
        self.connect_state = -1 # -1: 미연결, 0: 연결 성공
        self.current_fid = []

        # 이벤트 핸들러 연결
        self.ocx.OnEventConnect.connect(self._handler_connect)
        self.ocx.OnReceiveTrData.connect(self._handler_trdata)
        self.ocx.OnReceiveRealData.connect(self._handler_realdata)
        self.ocx.OnReceiveMsg.connect(self._handler_msg)
        self.ocx.OnReceiveChejanData.connect(self._handler_chejan)

        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def _handler_connect(self, err_code):
        logger.info(f"{get_current_time_str()}: Kiwoom Connection Status: {err_code}")
        self.connect_state = err_code
        if self.connect_event_loop:
            self.connect_event_loop.Set() # 이벤트 발생 신호

    def connect_kiwoom(self):
        if self.connect_state == 0:
            logger.info(f"{get_current_time_str()}: Kiwoom API is already connected.")
            return True

        if self.ocx.CommConnect():
            self.connect_event_loop = pythoncom.CreateEvent()
            pythoncom.WaitForSingleObject(self.connect_event_loop.handle, -1) # 이벤트가 발생할 때까지 무한 대기
            self.connect_event_loop = None # 사용 후 초기화
            
            if self.connect_state == 0:
                logger.info(f"{get_current_time_str()}: Kiwoom API Connected successfully.")
                return True
            else:
                logger.error(f"{get_current_time_str()}: Failed to connect Kiwoom API. Error code: {self.connect_state}")
                return False
        else:
            if self.ocx.GetConnectState() == 1: # 이미 연결되어 있는 경우
                logger.info(f"{get_current_time_str()}: CommConnect failed but Kiwoom API is already connected.")
                self.connect_state = 0
                return True
            else:
                logger.error(f"{get_current_time_str()}: CommConnect failed (API not ready or other issue).")
                return False

    def _handler_trdata(self, screen_no, rqname, trcode, record_name, sPrevNext, data_len, tr_data_record_name, tr_master_data, tr_slave_data):
        logger.info(f"{get_current_time_str()}: TR Data Received - Screen: {screen_no}, RQName: {rqname}, TRCode: {trcode}")
        self.tr_data = {'rqname': rqname, 'trcode': trcode, 'sPrevNext': sPrevNext}
        
        # 여기서 필요한 TR 데이터를 직접 파싱하여 self.tr_data에 추가할 수 있습니다.
        # 예: 계좌평가현황 (opw00018)의 경우
        if trcode == "opw00018":
            total_asset = self.get_comm_data(trcode, "계좌평가현황", 0, "총평가금액")
            total_purchase = self.get_comm_data(trcode, "계좌평가현황", 0, "총매입금액")
            self.tr_data['parsed_data'] = {
                "총평가금액": int(total_asset.replace(",", "")),
                "총매입금액": int(total_purchase.replace(",", ""))
            }
            # 종목별 데이터는 GetRepeatCnt와 GetCommData로 직접 가져와야 합니다.
            # 이 로직은 monitor_positions.py의 get_current_positions_from_kiwoom에 구현되어 있습니다.

        # 주식기본정보 (opt10001)의 경우
        elif trcode == "opt10001":
            current_price = self.get_comm_data(trcode, "주식기본정보", 0, "현재가")
            self.tr_data['parsed_data'] = {
                "현재가": abs(int(current_price.replace(",", "").replace("+", "").replace("-", "").strip()))
            }
        
        # 이벤트 루프 종료
        if self.tr_event_loop:
            self.tr_event_loop.Set() # 이벤트 발생 신호

    def _handler_realdata(self, stock_code, real_type, real_data):
        # 실시간 데이터 처리 로직 (현재는 사용하지 않음)
        pass

    def _handler_msg(self, sScrNo, sRQName, sTrCode, sMsg):
        logger.info(f"{get_current_time_str()}: Message Received - Screen: {sScrNo}, RQName: {sRQName}, TRCode: {sTrCode}, Message: {sMsg}")

    def _handler_chejan(self, gubun, item_cnt, fid_list):
        # 체결 데이터 처리 로직 (현재는 사용하지 않음)
        self.current_fid = fid_list.split(';')
        pass

    def set_input_value(self, id_name, value):
        self.ocx.SetInputValue(id_name, value)

    def comm_rq_data(self, rqname, trcode, prev_next, screen_no):
        self.tr_data = None # 이전 TR 데이터 초기화
        self.tr_event_loop = pythoncom.CreateEvent() # 새로운 이벤트 생성
        
        ret = self.ocx.CommRqData(rqname, trcode, prev_next, screen_no)
        
        if ret == 0:
            logger.debug(f"{get_current_time_str()}: CommRqData Success for {rqname} ({trcode}). Waiting for TR response...")
            # TR 이벤트가 발생할 때까지 대기
            pythoncom.WaitForSingleObject(self.tr_event_loop.handle, -1)
            self.tr_event_loop = None # 사용 후 초기화
            logger.debug(f"{get_current_time_str()}: TR response received for {rqname}.")
            return self.tr_data
        else:
            error_msg = self.ocx.GetErrorMessage(ret)
            logger.error(f"{get_current_time_str()}: CommRqData Failed for {rqname} ({trcode}). Error Code: {ret}, Message: {error_msg}")
            self.tr_event_loop = None # 실패했어도 이벤트 핸들 초기화
            return None

    def get_comm_data(self, trcode, record_name, index, item_name):
        return self.ocx.GetCommData(trcode, record_name, index, item_name).strip()

    def get_repeat_cnt(self, trcode, record_name):
        return self.ocx.GetRepeatCnt(trcode, record_name)

    def get_code_list_by_market(self, market_type):
        code_list_str = self.ocx.GetCodeListByMarket(market_type)
        if code_list_str:
            return code_list_str.split(';')[:-1]
        return []

    def get_master_code_name(self, code):
        return self.ocx.GetMasterCodeName(code)
    
    def get_chejan_data(self, fid):
        return self.ocx.GetChejanData(fid)

    def get_login_info(self, tag):
        """키움 API 로그인 정보를 요청합니다. ('ACCNO', 'USER_ID', 'USER_NAME' 등)"""
        return self.ocx.GetLoginInfo(tag)

    def disconnect_kiwoom(self):
        if self.ocx.GetConnectState() == 1:
            self.ocx.CommTerminate()
            self.connect_state = -1
            logger.info(f"{get_current_time_str()}: Kiwoom API disconnected.")
        else:
            logger.info(f"{get_current_time_str()}: Kiwoom API is already disconnected.")

    # 이 메서드는 kiwoom_tr_request로 이동하여 사용되어야 합니다.
    # 여기서는 더 이상 사용되지 않습니다.
    # def get_account_info(self):
    #     logger.info(f"{get_current_time_str()}: Requesting account info (placeholder)...")
    #     return {"current_balance": 0, "estimated_profit_loss": 0}

    # 이 메서드도 kiwoom_tr_request로 이동하여 사용되어야 합니다.
    # def get_current_price(self, stock_code):
    #     return 10000 # Placeholder for actual price query