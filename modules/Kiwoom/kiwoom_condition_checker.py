import logging
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QObject, QEventLoop, pyqtSignal

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KiwoomConditionChecker(QObject):
    """
    키움증권 API를 사용하여 조건식을 관리하고 검색하는 클래스.
    """
    
    condition_list_received = pyqtSignal()
    condition_search_received = pyqtSignal()

    def __init__(self, kiwoom_api_caller):
        super().__init__()
        self.kiwoom_api_caller = kiwoom_api_caller
        
        self.condition_event_loop = QEventLoop()
        self.search_event_loop = QEventLoop()

        self.condition_names = {}  # {조건식ID: 조건식명}
        self.condition_search_result = []

        self._connect_signals()

    def _connect_signals(self):
        """키움 API 시그널과 메서드 연결"""
        self.kiwoom_api_caller.kiwoom_ocx.OnReceiveConditionVer.connect(self.on_receive_condition_ver)
        self.kiwoom_api_caller.kiwoom_ocx.OnReceiveTrCondition.connect(self.on_receive_tr_condition)
        
        self.condition_list_received.connect(self.condition_event_loop.quit)
        self.condition_search_received.connect(self.search_event_loop.quit)
        
        logger.info("✅ KiwoomConditionChecker 시그널 연결 완료.")

    def get_condition_names(self):
        """
        조건식 목록 요청 → 수신까지 대기
        Returns:
            dict: {조건식ID: 조건식명}
        """
        self.kiwoom_api_caller.get_condition_list()
        self.condition_event_loop.exec_()
        return self.condition_names

    def on_receive_condition_ver(self, ret, msg):
        """
        조건식 목록 수신 핸들러
        """
        if ret == 1:
            logger.info(f"✅ 조건식 목록 요청 성공. 메시지: {msg}")
            condition_list_string = self.kiwoom_api_caller.get_condition_name_list()
            if not condition_list_string:
                logger.warning("⚠️ 저장된 조건식이 없습니다.")
                self.condition_names = {}
            else:
                self.condition_names = {}
                for item in condition_list_string.split(";"):
                    if item:
                        parts = item.split("^")
                        if len(parts) == 2:
                            condition_id = int(parts[0])
                            condition_name = parts[1]
                            self.condition_names[condition_id] = condition_name
                logger.info(f"📋 조건식 목록 수신 완료: {self.condition_names}")
        else:
            logger.error(f"❌ 조건식 목록 요청 실패. 메시지: {msg}")
            
        self.condition_list_received.emit()

    def send_condition_search_request(self, condition_id, condition_name, search_type=1, screen_no="2000"):
        """
        조건식 검색 요청
        Args:
            condition_id (int): 조건식 ID
            condition_name (str): 조건식 이름
            search_type (int): 0 - 실시간, 1 - 일반 요청
            screen_no (str): 화면번호
        Returns:
            list[str]: 종목 코드 리스트
        """
        logger.info(f"🔍 조건식 검색 요청 시작: ID={condition_id}, 이름={condition_name}, 유형={search_type}")
        self.condition_search_result = []

        self.kiwoom_api_caller.send_condition(screen_no, condition_name, condition_id, search_type)

        if search_type == 1:
            self.search_event_loop.exec_()
        
        return self.condition_search_result

    def on_receive_tr_condition(self, screen_no, code_list, condition_name, condition_index, is_last):
        """
        조건식 검색 결과 수신 핸들러
        """
        logger.info(f"✅ 조건식 검색 결과 수신: 조건식명='{condition_name}', 마지막={is_last}")
        codes = code_list.split(';')[:-1]
        self.condition_search_result.extend(codes)

        if is_last == 2 or is_last == 0:
            logger.info(f"📊 종목 {len(self.condition_search_result)}개 수신됨: {self.condition_search_result}")
            self.condition_search_received.emit()


# === 테스트용 예제 실행 ===
if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication
    import sys

    class DummyKiwoomApiCaller(QObject):
        kiwoom_ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")

        def get_condition_list(self):
            self.kiwoom_ocx.OnReceiveConditionVer.emit(1, "성공")

        def get_condition_name_list(self):
            return "0^테스트조건1;1^테스트조건2;"

        def send_condition(self, screen_no, condition_name, condition_id, search_type):
            self.kiwoom_ocx.OnReceiveTrCondition.emit(screen_no, "005930;000660;", condition_name, str(condition_id), 2)

    app = QApplication(sys.argv)

    dummy_api = DummyKiwoomApiCaller()
    checker = KiwoomConditionChecker(dummy_api)

    condition_list = checker.get_condition_names()
    logger.info(f"🧪 조건식 목록: {condition_list}")

    if condition_list:
        first_id = list(condition_list.keys())[0]
        first_name = condition_list[first_id]
        results = checker.send_condition_search_request(first_id, first_name)
        logger.info(f"🧪 검색 결과: {results}")

    sys.exit(0)

