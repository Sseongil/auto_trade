# pykiwoom/kiwoom.py

import os
import sys
from PyQt5.QtWidgets import *
from PyQt5.QAxContainer import *
from PyQt5.QtCore import *
import pandas as pd
import time
import logging

logger = logging.getLogger(__name__)

class Kiwoom(QAxWidget):
    def __init__(self):
        super().__init__()
        self.setControl("KHOPENAPI.KHOpenAPICtrl.1")
        self.connected = False
        self.ocx = self.dynamicCall("GetOcXInstance()")
        self.data_event_handlers = {}

        # Event handlers
        self.ocx.OnEventConnect.connect(self._on_event_connect)
        self.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        self.ocx.OnReceiveRealData.connect(self._on_receive_real_data)
        self.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data)
        self.ocx.OnReceiveMsg.connect(self._on_receive_msg)
        self.ocx.OnReceiveRealCondition.connect(self._on_receive_real_condition)

        # Event loops
        self.login_event_loop = QEventLoop()
        self.tr_event_loop = QEventLoop()

        # Data storage
        self.tr_data = {}
        self.rq_name = None
        self.tr_code = None
        self.next = False

    # --------------------------
    # Real-time handler registry
    # --------------------------
    def set_real_data_callback(self, handler_key: str, handler_func):
        self.data_event_handlers[handler_key] = handler_func
        logger.info(f"✅ Real-time callback registered for key: {handler_key}")

    # --------------------------
    # Real-time data dispatch
    # --------------------------
    def _on_receive_real_data(self, stock_code, real_type, real_data):
        if real_type in self.data_event_handlers:
            self.data_event_handlers[real_type](stock_code, real_type, real_data)
        elif 'default' in self.data_event_handlers:
            self.data_event_handlers['default'](stock_code, real_type, real_data)
        else:
            logger.debug(f"📩 실시간 데이터 수신: {stock_code}({real_type}) → 핸들러 없음")

    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        if gubun == '0' and 'stock_conclusion' in self.data_event_handlers:
            self.data_event_handlers['stock_conclusion'](gubun, item_cnt, fid_list)
        elif gubun == '1' and 'balance_change' in self.data_event_handlers:
            self.data_event_handlers['balance_change'](gubun, item_cnt, fid_list)
        elif 'default_chejan' in self.data_event_handlers:
            self.data_event_handlers['default_chejan'](gubun, item_cnt, fid_list)
        else:
            logger.debug(f"📩 체결/잔고 데이터 수신: gubun={gubun} → 핸들러 없음")

    # --------------------------
    # 로그인 처리
    # --------------------------
    def CommConnect(self, block=True):
        self.dynamicCall("CommConnect()")
        if block:
            self.login_event_loop.exec_()

    def _on_event_connect(self, err_code):
        if err_code == 0:
            self.connected = True
            logger.info("✅ 로그인 성공")
        else:
            self.connected = False
            logger.error(f"❌ 로그인 실패: 코드 {err_code}")
        self.login_event_loop.exit()

    # --------------------------
    # 실시간 데이터 가져오기
    # --------------------------
    def GetCommRealData(self, code, fid):
        return self.dynamicCall("GetCommRealData(QString, int)", code, fid)

    def GetChejanData(self, fid):
        return self.dynamicCall("GetChejanData(int)", fid)

    # --------------------------
    # 기타 이벤트 핸들러
    # --------------------------
    def _on_receive_tr_data(self, screen_no, rqname, trcode, recordname, prev_next):
        # 여기에 필요한 TR 처리 로직 구현
        pass

    def _on_receive_msg(self, screen_no, rqname, trcode, msg):
        logger.info(f"📩 메시지 수신: {msg}")

    def _on_receive_real_condition(self, code, event, cond_name, cond_index):
        logger.debug(f"📈 실시간 조건 검색: {code}, {cond_name}, {event}")

    # --------------------------
    # 연결 종료
    # --------------------------
    def Disconnect(self):
        if self.connected:
            self.dynamicCall("CommTerminate()")
            self.connected = False
            logger.info("🔌 Kiwoom API 연결 해제 완료")
