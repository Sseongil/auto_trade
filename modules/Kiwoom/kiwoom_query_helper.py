# modules/Kiwoom/kiwoom_query_helper.py

import logging
import time
from PyQt5.QtCore import QEventLoop, QTimer, pyqtSignal, QObject
from modules.common.error_codes import get_error_message
from modules.common.utils import get_current_time_str
from modules.common.config import REAL_TIME_FIDS # REALTIME_FID_LIST -> REAL_TIME_FIDS로 수정

logger = logging.getLogger(__name__)

class KiwoomQueryHelper(QObject):
    # TR 응답을 외부에 알리는 시그널
    tr_response_signal = pyqtSignal(str, dict)
    # 실시간 조건검색 이벤트를 외부에 알리는 시그널
    real_condition_signal = pyqtSignal(str, str, str, str) # 종목코드, 편입/이탈, 조건명, 조건인덱스

    def __init__(self, ocx, qt_app):
        super().__init__()
        self.kiwoom = ocx
        self.qt_app = qt_app # QApplication 인스턴스 저장
        self.connected = False
        self.login_event_loop = QEventLoop()
        self.tr_event_loops = {}  # 화면번호별 TR 이벤트 루프
        self.tr_data = {}         # 화면번호별 TR 데이터
        self.condition_list = {}  # 조건식 목록 (이름: 인덱스)
        self.real_time_data = {}  # 실시간 데이터를 저장할 딕셔너리 {종목코드: {FID: 값, ...}}
        self.real_time_screen_no_counter = 5000 # 실시간 데이터용 화면번호 카운터
        self.condition_screen_no_counter = 6000 # 조건검색 실시간용 화면번호 카운터
        self.filtered_df = None # 조건 검색을 통해 걸러진 종목들을 저장할 DataFrame

        self._set_event_handlers()
        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def _set_event_handlers(self):
        """이벤트 핸들러를 설정합니다."""
        logger.debug("Setting event handlers...")
        self.kiwoom.OnEventConnect.connect(self._on_event_connect)
        logger.debug("OnEventConnect connected.")
        self.kiwoom.OnReceiveTrData.connect(self._on_receive_tr_data)
        logger.debug("OnReceiveTrData connected.")
        self.kiwoom.OnReceiveConditionVer.connect(self._on_receive_condition_ver)
        logger.debug("OnReceiveConditionVer connected.")
        self.kiwoom.OnReceiveRealCondition.connect(self._on_receive_real_condition)
        logger.debug("OnReceiveRealCondition connected.") 
        self.kiwoom.OnReceiveRealData.connect(self._on_receive_real_data) # 실시간 데이터 이벤트 핸들러 연결
        logger.debug("OnReceiveRealData connected.")
        # OnReceiveMsg, OnReceiveChejanData는 TradeManager에서 처리하므로 여기서 연결하지 않음

    def connect_kiwoom(self, timeout_ms=20000): # ✅ 타임아웃 20초로 증가
        """
        키움 OpenAPI+에 연결을 요청하고 응답을 기다립니다.
        """
        if self.kiwoom.dynamicCall("GetConnectState()") == 0:
            logger.info("🧠 키움 API 연결 요청...")
            self.kiwoom.dynamicCall("CommConnect()")
            
            # QTimer를 사용하여 타임아웃 설정
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(self.login_event_loop.quit)
            timer.start(timeout_ms)

            self.login_event_loop.exec_() # 이벤트 루프 시작, 연결 또는 타임아웃까지 대기
            timer.stop() # 타이머 중지

            if self.connected:
                logger.info("✅ 키움 API 연결 성공.")
                return True
            else:
                logger.error("❌ 키움 API 연결 실패 또는 타임아웃.")
                return False
        else:
            self.connected = True
            logger.info("✅ 키움 API 이미 연결됨.")
            return True

    def _on_event_connect(self, err_code):
        """
        키움 OpenAPI+ 연결 상태 변경 시 발생하는 이벤트 핸들러.
        """
        if err_code == 0:
            self.connected = True
            logger.info("✅ CommConnect 연결 성공.")
        else:
            self.connected = False
            error_msg = get_error_message(err_code)
            logger.error(f"❌ CommConnect 연결 실패: {error_msg} (에러 코드: {err_code})")
        
        if self.login_event_loop.isRunning():
            self.login_event_loop.quit() # 이벤트 루프 종료

    def set_tr_response_event(self, screen_no):
        """TR 응답 대기 이벤트를 설정합니다."""
        self.tr_event_loops[screen_no] = QEventLoop()
        self.tr_data[screen_no] = {"single_data": {}, "multi_data": [], "error": None}

    def wait_for_tr_response(self, screen_no, timeout_ms=10000):
        """TR 응답을 기다립니다."""
        if screen_no not in self.tr_event_loops:
            logger.error(f"❌ TR 응답 대기 이벤트가 설정되지 않았습니다: {screen_no}")
            return False

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self.tr_event_loops[screen_no].quit)
        timer.start(timeout_ms)

        self.tr_event_loops[screen_no].exec_() # 이벤트 루프 시작
        timer.stop()

        # 타임아웃으로 종료되었는지 확인
        if self.tr_data[screen_no].get("error") == "Timeout":
            return False
        return True

    def get_tr_data(self, screen_no):
        """저장된 TR 데이터를 반환합니다."""
        data = self.tr_data.get(screen_no)
        # 데이터 사용 후 초기화 (선택 사항, 재사용 방지)
        # self.tr_data[screen_no] = {"single_data": {}, "multi_data": [], "error": None}
        return data

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, s_prev_next):
        """
        TR 데이터 수신 시 발생하는 이벤트 핸들러.
        """
        logger.debug(f"TR 데이터 수신: 화면번호={screen_no}, 요청이름={rq_name}, TR코드={tr_code}")
        
        # 단일 데이터 처리
        single_data = {}
        # opt10081 (일봉) TR은 GetCommData 대신 GetCommDataEx를 사용
        if tr_code == "opt10081":
            # 일봉 데이터는 멀티 데이터로만 존재
            pass 
        else:
            # 그 외 TR (예: opw00001, opw00018의 단일 데이터)
            # GetCommData(TR코드, 레코드명, 인덱스, 아이템이름)
            item_names = {
                "opw00001": ["예수금"],
                "opw00018": ["총매입금", "총평가금액", "총평가손익금액", "총수익률(%)", "추정예탁자산"]
            }
            for item_name in item_names.get(tr_code, []):
                data = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, record_name, 0, item_name)
                single_data[item_name] = data.strip()
            self.tr_data[screen_no]["single_data"] = single_data

        # 멀티 데이터 처리
        multi_data = []
        # GetRepeatCnt(TR코드, 레코드명)
        count = self.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name) # rq_name으로 변경
        
        # TR 코드에 따라 멀티 데이터 필드 정의
        if tr_code == "opt10081": # 일봉 데이터
            # "일자", "현재가", "거래량", "시가", "고가", "저가"
            fields = ["일자", "현재가", "거래량", "시가", "고가", "저가", "전일대비", "등락률", "거래원", "개인", "기관", "외인(소진율)", "외인", "상한가", "하한가", "기준가", "시가총액", "고가율", "저가율", "거래대금", "체결강도"]
        elif tr_code == "opw00018": # 보유 종목 데이터
            # "종목번호", "종목명", "보유수량", "매입가", "현재가", "평가손익", "수익률(%)", "매매가능수량"
            fields = ["종목번호", "종목명", "보유수량", "매입가", "현재가", "평가손익", "수익률(%)", "매매가능수량", "당일매수수량", "당일매도수량", "매입금액", "매매수수료", "매도세금"]
        else:
            fields = [] # 다른 TR에 대한 필드는 여기에 추가

        for i in range(count):
            row_data = {}
            for field in fields:
                data = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, record_name, i, field)
                row_data[field] = data.strip()
            multi_data.append(row_data)
        self.tr_data[screen_no]["multi_data"] = multi_data
        
        # 다음 페이지 유무 (s_prev_next)
        self.tr_data[screen_no]["s_prev_next"] = s_prev_next

        # 이벤트 루프 종료
        if screen_no in self.tr_event_loops and self.tr_event_loops[screen_no].isRunning():
            self.tr_event_loops[screen_no].quit()

    def _on_receive_condition_ver(self, ret, msg):
        """
        조건식 버전 수신 시 발생하는 이벤트 핸들러.
        """
        logger.info(f"조건식 버전 수신: {msg} (코드: {ret})")
        if ret == 1: # 성공
            self._get_condition_list_from_server() # 서버에서 조건식 목록 가져오기
        else:
            logger.error("❌ 조건식 버전 확인 실패.")
        
        # 조건식 버전 이벤트 루프가 실행 중이면 종료
        if hasattr(self, 'condition_ver_event_loop') and self.condition_ver_event_loop.isRunning():
            self.condition_ver_event_loop.quit()

    def _get_condition_list_from_server(self):
        """
        서버에 저장된 조건식 목록을 요청합니다.
        """
        logger.info("🧠 서버에서 조건식 목록 요청...")
        self.kiwoom.dynamicCall("GetConditionLoad()")
        # GetConditionLoad()는 OnReceiveConditionVer 이벤트를 발생시키지 않습니다.
        # 대신, 이 호출 이후 GetConditionNameList()를 통해 즉시 목록을 가져올 수 있습니다.
        # 따라서 별도의 이벤트 루프 대기는 필요 없습니다.
        self._parse_condition_name_list()


    def _parse_condition_name_list(self):
        """
        GetConditionLoad() 호출 후 조건식 목록을 파싱합니다.
        """
        data = self.kiwoom.dynamicCall("GetConditionNameList()")
        if data == "":
            logger.warning("⚠️ 서버에 저장된 조건식이 없습니다.")
            self.condition_list = {}
            return

        condition_list_raw = data.split(";")
        self.condition_list = {}
        for item in condition_list_raw:
            if item:
                parts = item.split("^")
                if len(parts) == 2:
                    index = int(parts[0])
                    name = parts[1]
                    self.condition_list[name] = index
        logger.info(f"✅ 조건식 목록 로드 완료: {len(self.condition_list)}개")
        for name, index in self.condition_list.items():
            logger.debug(f"  - {name} (인덱스: {index})")

    def get_condition_list(self):
        """
        현재 로드된 조건식 목록을 반환합니다.
        없으면 서버에서 로드를 시도합니다.
        """
        if not self.condition_list:
            logger.info("조건식 목록이 비어 있습니다. 서버에서 로드를 시도합니다.")
            self._get_condition_list_from_server() # 조건식 목록 로드 시도
            # 로드 후에도 비어있을 수 있으므로 다시 확인
            if not self.condition_list:
                logger.warning("⚠️ 조건식 목록 로드 실패 또는 서버에 조건식이 없습니다.")
        return self.condition_list

    def generate_real_time_screen_no(self):
        """실시간 데이터 요청용 고유 화면번호를 생성합니다."""
        self.real_time_screen_no_counter += 1
        if self.real_time_screen_no_counter > 5999: # 5000번대 사용
            self.real_time_screen_no_counter = 5000
        return str(self.real_time_screen_no_counter)

    def generate_condition_screen_no(self):
        """조건 검색 실시간 요청용 고유 화면번호를 생성합니다."""
        self.condition_screen_no_counter += 1
        if self.condition_screen_no_counter > 6999: # 6000번대 사용
            self.condition_screen_no_counter = 6000
        return str(self.condition_screen_no_counter)

    def SetRealReg(self, screen_no, stock_code, fid_list, real_type):
        """
        실시간 데이터 등록.
        """
        logger.info(f"🧠 실시간 데이터 등록 요청: 화면번호={screen_no}, 종목코드={stock_code}, FID={fid_list}, 타입={real_type}")
        ret = self.kiwoom.dynamicCall("SetRealReg(QString, QString, QString, QString)", screen_no, stock_code, fid_list, real_type)
        if ret == 0:
            logger.info(f"✅ 실시간 데이터 등록 성공: {stock_code}")
            return True
        else:
            error_msg = get_error_message(ret)
            logger.error(f"❌ 실시간 데이터 등록 실패 ({stock_code}): {error_msg}")
            return False

    def SetRealRemove(self, screen_no, stock_code="ALL"):
        """
        실시간 데이터 해제.
        """
        logger.info(f"� 실시간 데이터 해제 요청: 화면번호={screen_no}, 종목코드={stock_code}")
        self.kiwoom.dynamicCall("SetRealRemove(QString, QString)", screen_no, stock_code)
        logger.info(f"✅ 실시간 데이터 해제 완료: 화면번호={screen_no}, 종목코드={stock_code}")

    def _on_receive_real_data(self, stock_code, real_type, real_data):
        """
        실시간 데이터 수신 시 발생하는 이벤트 핸들러.
        """
        # logger.debug(f"실시간 데이터 수신: 종목={stock_code}, 타입={real_type}, 데이터={real_data}")
        
        # 현재가, 등락률, 체결강도 등 필요한 FID 값들을 가져와 저장
        # CommGetData(실시간 타입, FID)
        
        # '주식체결' (real_type: "주식체결")
        if real_type == "주식체결":
            current_price_str = self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 10).strip() # 현재가
            current_price = int(current_price_str.replace('+', '').replace('-', '')) # 부호 제거 후 정수 변환
            
            daily_change_str = self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 11).strip() # 전일대비
            daily_change = int(daily_change_str.replace('+', '').replace('-', ''))
            
            daily_change_pct_str = self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 12).strip() # 등락률
            daily_change_pct = float(daily_change_pct_str)
            
            total_volume_str = self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 13).strip() # 누적거래량
            total_volume = int(total_volume_str)

            chegyul_gangdo_str = self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 228).strip() # 체결강도
            chegyul_gangdo = float(chegyul_gangdo_str) if chegyul_gangdo_str else 0.0

            total_buy_cvol_str = self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 290).strip() # 매수체결량
            total_buy_cvol = int(total_buy_cvol_str) if total_buy_cvol_str else 0

            total_sell_cvol_str = self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 291).strip() # 매도체결량
            total_sell_cvol = int(total_sell_cvol_str) if total_sell_cvol_str else 0
            
            self.real_time_data[stock_code] = {
                "current_price": current_price,
                "daily_change": daily_change,
                "daily_change_pct": daily_change_pct,
                "total_volume": total_volume,
                "chegyul_gangdo": chegyul_gangdo,
                "total_buy_cvol": total_buy_cvol,
                "total_sell_cvol": total_sell_cvol,
                "timestamp": get_current_time_str()
            }
            # logger.debug(f"실시간 데이터 업데이트 [{stock_code}]: 현재가={current_price}, 체결강도={chegyul_gangdo:.2f}")

    def SendCondition(self, screen_no, condition_name, condition_index, search_type):
        """
        조건식 실시간 검색을 요청합니다.
        search_type: 0 (일반조회), 1 (실시간조회)
        """
        logger.info(f"🧠 조건식 검색 요청: 화면번호={screen_no}, 조건명='{condition_name}', 인덱스={condition_index}, 타입={search_type}")
        ret = self.kiwoom.dynamicCall("SendCondition(QString, QString, int, int)", 
                                      screen_no, condition_name, condition_index, search_type)
        if ret == 1: # 성공
            logger.info(f"✅ 조건식 검색 요청 성공: '{condition_name}'")
            return True
        else:
            error_msg = get_error_message(ret)
            logger.error(f"❌ 조건식 검색 요청 실패 ({condition_name}): {error_msg}")
            return False

    def SendConditionStop(self, screen_no, condition_name, condition_index):
        """
        조건식 실시간 검색을 중지합니다.
        """
        logger.info(f"🧠 조건식 검색 중지 요청: 화면번호={screen_no}, 조건명='{condition_name}', 인덱스={condition_index}")
        self.kiwoom.dynamicCall("SendConditionStop(QString, QString, int)", 
                                screen_no, condition_name, condition_index)
        logger.info(f"✅ 조건식 검색 중지 완료: '{condition_name}'")

    def _on_receive_real_condition(self, stock_code, event_type, condition_name, condition_index):
        """
        실시간 조건검색 종목 편입/이탈 시 발생하는 이벤트 핸들러.
        """
        logger.debug(f"실시간 조건 수신: 종목={stock_code}, 타입={event_type}, 조건명={condition_name}, 인덱스={condition_index}")
        # 이 시그널을 RealTimeConditionManager로 전달
        self.real_condition_signal.emit(stock_code, event_type, condition_name, condition_index)

    def get_stock_name(self, stock_code):
        """
        종목코드로 종목명을 반환합니다.
        """
        return self.kiwoom.dynamicCall("GetMasterCodeName(QString)", stock_code).strip()

    def get_code_list_by_market(self, market_code):
        """
        시장별 종목코드를 반환합니다.
        """
        data = self.kiwoom.dynamicCall("GetCodeListByMarket(QString)", market_code)
        codes = data.split(';')
        return [code.strip() for code in codes if code.strip()]

    def get_stock_state(self, stock_code):
        """
        종목코드로 종목 상태를 반환합니다. (예: 관리종목, 투자주의 등)
        """
        # GetMasterStockState는 종목 상태 문자열을 반환합니다.
        return self.kiwoom.dynamicCall("GetMasterStockState(QString)", stock_code).strip()

    def get_current_price(self, stock_code):
        """
        실시간 데이터에서 현재가를 가져오거나, 없으면 TR로 조회합니다.
        """
        # 실시간 데이터에 현재가가 있으면 사용
        if stock_code in self.real_time_data and self.real_time_data[stock_code].get("current_price") is not None:
            return self.real_time_data[stock_code]["current_price"]
        
        # 실시간 데이터가 없으면 TR 요청 (GetCommRealData는 실시간 등록된 종목만 가능)
        # TR 요청은 KiwoomTrRequest에서 담당하므로, 여기서는 직접 호출하지 않고 0을 반환합니다.
        logger.debug(f"현재가 정보 없음 (실시간 데이터): {stock_code}")
        return 0
