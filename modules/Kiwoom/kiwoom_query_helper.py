# modules/Kiwoom/kiwoom_query_helper.py (조건검색 기능 포함된 전체 수정본)

import logging
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, QEventLoop
from modules.Kiwoom.tr_event_loop import TrEventLoop
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class KiwoomQueryHelper(QObject):
    def __init__(self, ocx, app):
        super().__init__()
        self.ocx = ocx
        self.app = app
        self.tr_event_loop = TrEventLoop()
        self.real_time_data = {}  # 실시간 시세 데이터 저장용
        self.condition_list = {}  # 조건검색식 이름:인덱스 매핑

        # 실시간 조건검색 편입 이벤트 연결
        self.ocx.OnReceiveRealCondition.connect(self._on_receive_real_condition)

    def connect_kiwoom(self, timeout_ms=10000):
        self.ocx.dynamicCall("CommConnect()")
        loop = QEventLoop()
        self.ocx.OnEventConnect.connect(lambda err_code: loop.quit())
        loop.exec_()
        return True  # 연결 성공 여부는 이후 체크하도록

    def get_login_info(self, tag):
        return self.ocx.dynamicCall("GetLoginInfo(QString)", tag)

    def SetRealReg(self, screen_no, code_list, fid_list, real_type):
        self.ocx.dynamicCall("SetRealReg(QString, QString, QString, QString)",
                             screen_no, code_list, fid_list, real_type)

    def SetRealRemove(self, screen_no, code):
        self.ocx.dynamicCall("SetRealRemove(QString, QString)", screen_no, code)

    def get_stock_name(self, code):
        return self.ocx.dynamicCall("GetMasterCodeName(QString)", code)

    def generate_real_time_screen_no(self):
        return "5000"

    # ------------------ 조건검색 관련 메서드 ------------------

    def get_condition_list(self):
        """
        조건검색식 이름과 인덱스를 딕셔너리로 반환
        """
        raw_str = self.ocx.dynamicCall("GetConditionNameList()")
        condition_map = {}
        for cond in raw_str.split(';'):
            if not cond.strip():
                continue
            index, name = cond.split('^')
            condition_map[name.strip()] = int(index.strip())

        self.condition_list = condition_map
        logger.info(f"📑 조건검색식 목록 로드: {list(condition_map.keys())}")
        return condition_map

    def SendCondition(self, screen_no, condition_name, index, search_type):
        """
        조건검색 실행 및 실시간 등록
        - screen_no: 실시간 화면 번호 (예: '5000')
        - condition_name: 조건검색식 이름
        - index: 조건 인덱스
        - search_type: 0=일회성 검색, 1=실시간 등록
        """
        logger.info(f"🧠 조건검색 실행: {condition_name} (Index: {index}, 실시간: {search_type})")
        self.ocx.dynamicCall("SendCondition(QString, QString, int, int)",
                             screen_no, condition_name, index, search_type)

    def _on_receive_real_condition(self, code, event_type, condition_name, condition_index):
        """
        실시간 조건검색 편입/이탈 이벤트 수신
        """
        stock_name = self.get_stock_name(code)
        logger.info(f"📡 [조건검색 이벤트] {stock_name}({code}) - {event_type} ({condition_name})")

        if hasattr(self, "condition_callback") and callable(self.condition_callback):
            if event_type == "I":  # 편입
                self.condition_callback(code, stock_name)

    def set_condition_callback(self, callback_fn):
        self.condition_callback = callback_fn
