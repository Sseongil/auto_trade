import logging
from PyQt5.QtCore import QObject, QEventLoop, pyqtSignal

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KiwoomApiCaller(QObject):
    """
    키움 Open API의 OCX 메서드를 호출하고 이벤트를 처리하는 헬퍼 클래스.
    """
    
    # 로그인 성공/실패 여부를 알리는 시그널
    login_state = pyqtSignal(bool)
    # TR 데이터 수신 시그널
    OnReceiveTrData = pyqtSignal(str, str, str, str, str)
    # 실시간 데이터 수신 시그널
    OnReceiveRealData = pyqtSignal(str, str, str)

    def __init__(self, kiwoom_ocx):
        """
        초기화 메서드.
        
        Args:
            kiwoom_ocx (QAxWidget): Kiwoom Open API OCX 객체.
        """
        super().__init__()
        # 수정: kiwoom_ocx 객체를 인스턴스 변수로 저장
        self.kiwoom_ocx = kiwoom_ocx
        
        # 이벤트 루프
        self.event_loop = QEventLoop()
        
        # 키움 OCX 시그널과 슬롯 연결
        self._connect_signals()
        
        # 상태 변수
        self.is_login_ok = False
        
        logger.info("✅ KiwoomApiCaller 초기화 완료.")
        
    def _connect_signals(self):
        """키움 OCX의 시그널과 클래스 메서드를 연결합니다."""
        self.kiwoom_ocx.OnEventConnect.connect(self._on_event_connect)
        self.kiwoom_ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        self.kiwoom_ocx.OnReceiveRealData.connect(self._on_receive_real_data)
        
    def comm_connect(self):
        """
        로그인 윈도우를 호출하여 로그인을 시도합니다.
        """
        logger.info("📡 로그인 시도...")
        self.kiwoom_ocx.dynamicCall("CommConnect()")
        self.event_loop.exec_()
        return self.is_login_ok

    def _on_event_connect(self, err_code):
        """로그인 결과 이벤트를 처리하는 슬롯."""
        if err_code == 0:
            logger.info("🔑 로그인 성공!")
            self.is_login_ok = True
        else:
            logger.error(f"❌ 로그인 실패! 오류 코드: {err_code}")
            self.is_login_ok = False
        
        self.login_state.emit(self.is_login_ok)
        self.event_loop.quit()

    def get_login_info(self, tag):
        """
        로그인 정보를 요청합니다.
        
        Args:
            tag (str): 요청할 로그인 정보 태그 ("ACCLIST" 등).
        
        Returns:
            str: 요청한 로그인 정보.
        """
        return self.kiwoom_ocx.dynamicCall("GetLoginInfo(QString)", tag)

    def comm_rq_data(self, tr_name, tr_code, prev_next, screen_no):
        """
        TR 데이터를 요청합니다.
        """
        self.kiwoom_ocx.dynamicCall("CommRqData(QString, QString, int, QString)", tr_name, tr_code, prev_next, screen_no)
        
    def get_comm_data(self, tr_code, record_name, index, item_name):
        """
        수신된 TR 데이터 중 특정 값을 반환합니다.
        """
        return self.kiwoom_ocx.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, record_name, index, item_name).strip(' \t\n\r')

    def get_repeat_cnt(self, tr_code, record_name):
        """
        수신된 TR 데이터의 반복 횟수를 반환합니다.
        """
        return self.kiwoom_ocx.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, record_name)
    
    def set_input_value(self, id, value):
        """
        TR 요청에 필요한 값을 설정합니다.
        """
        self.kiwoom_ocx.dynamicCall("SetInputValue(QString, QString)", id, value)

    def set_real_reg(self, screen_no, code_list, fid_list, real_type):
        """
        실시간 데이터 수신을 등록합니다.
        """
        self.kiwoom_ocx.dynamicCall("SetRealReg(QString, QString, QString, QString)", screen_no, code_list, fid_list, real_type)

    def get_comm_real_data(self, code, fid):
        """
        수신된 실시간 데이터 중 특정 값을 반환합니다.
        """
        return self.kiwoom_ocx.dynamicCall("GetCommRealData(QString, int)", code, fid)
    
    def _on_receive_tr_data(self, screen_no, tr_code, record_name, s_rq_name):
        """TR 데이터를 수신했을 때 발생하는 이벤트."""
        self.OnReceiveTrData.emit(screen_no, tr_code, record_name, s_rq_name)
        
    def _on_receive_real_data(self, code, real_type, real_data):
        """실시간 데이터를 수신했을 때 발생하는 이벤트."""
        self.OnReceiveRealData.emit(code, real_type, real_data)
