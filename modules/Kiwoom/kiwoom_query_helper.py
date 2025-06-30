# modules/Kiwoom/kiwoom_query_helper.py

import logging
import pandas as pd
import time
from PyQt5.QtCore import QEventLoop, QTimer, pyqtSignal, QObject
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
import pythoncom # COM 초기화를 위해 필요

from modules.common.error_codes import get_error_message
from modules.common.utils import get_current_time_str
from modules.common.config import REALTIME_SCREEN_NO_PREFIX # REALTIME_SCREEN_NO_PREFIX 임포트

logger = logging.getLogger(__name__)

class KiwoomQueryHelper(QObject):
    # 실시간 데이터를 외부에 알리기 위한 시그널
    real_time_signal = pyqtSignal(dict) 
    # 실시간 조건검색 결과를 외부에 알리기 위한 시그널
    real_condition_signal = pyqtSignal(str, str, str, str) # 종목코드, 이벤트타입, 조건명, 조건인덱스

    def __init__(self, kiwoom_ocx, pyqt_app: QApplication):
        super().__init__()
        self.kiwoom = kiwoom_ocx
        self.app = pyqt_app
        self.connected = False
        self.filtered_df = pd.DataFrame()
        self.is_condition_checked = False
        self.real_time_data = {} # 실시간 데이터 저장 딕셔너리
        self.condition_list = {} # 조건검색식 목록 저장
        self._stock_name_cache = {} # 종목명 캐시 (새로 추가)
        self._real_time_screen_no_counter = int(REALTIME_SCREEN_NO_PREFIX + "00") # 실시간 화면번호 카운터 초기화 (새로 추가)

        # TR 요청 응답 대기용 이벤트 루프
        self.tr_event_loop = QEventLoop()
        self.tr_data = None # TR 응답 데이터

        # 로그인 이벤트 루프 및 상태
        self.login_event_loop = QEventLoop()
        self._login_done = False
        self._login_error = None

        # 키움 API 이벤트 연결
        self.kiwoom.OnEventConnect.connect(self._on_event_connect)
        self.kiwoom.OnReceiveTrData.connect(self._on_receive_tr_data)
        self.kiwoom.OnReceiveRealData.connect(self._on_receive_real_data)
        self.kiwoom.OnReceiveMsg.connect(self._on_receive_msg)
        self.kiwoom.OnReceiveChejanData.connect(self._on_receive_chejan_data)
        self.kiwoom.OnReceiveRealCondition.connect(self._on_receive_real_condition) # 실시간 조건검색 이벤트 연결

        logger.info("KiwoomQueryHelper initialized.")

    def connect_kiwoom(self, timeout_ms=10000):
        """
        키움 API에 로그인합니다.
        """
        logger.info("🔌 Attempting to connect to Kiwoom API (CommConnect call)")
        self.kiwoom.dynamicCall("CommConnect()")

        # Execute login event loop
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self.login_event_loop.quit)
        timer.start(timeout_ms)

        self.login_event_loop.exec_()

        if not self._login_done:
            self._login_error = "Login timeout"
            logger.error("❌ Login timeout")
            return False

        if self._login_error:
            logger.error(f"❌ Login failed: {self._login_error}")
            return False

        self.connected = True
        logger.info("✅ Kiwoom API connection successful")
        return True

    def disconnect_kiwoom(self):
        """키움 API 연결을 해제합니다."""
        if self.kiwoom.dynamicCall("GetConnectState()") == 1:
            self.kiwoom.dynamicCall("CommTerminate()")
            self.connected = False
            logger.info("🔌 Kiwoom API disconnected.")
        else:
            logger.info("🔌 Kiwoom API is already disconnected.")

    def _on_event_connect(self, err_code):
        """CommConnect 결과에 대한 이벤트 핸들러."""
        msg = get_error_message(err_code)
        if err_code == 0:
            self._login_done = True
            self._login_error = None
            logger.info(f"✅ Login event success: {msg}")
        else:
            self._login_done = True
            self._login_error = f"Error code {err_code} ({msg})"
            logger.error(f"❌ Login event failed: {self._login_error}")
        
        if self.login_event_loop.isRunning():
            self.login_event_loop.quit()

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, prev_next, data_len, error_code, message, splm_msg):
        """
        TR 데이터 수신 이벤트 핸들러.
        수신된 TR 데이터를 처리하고 tr_event_loop에 설정합니다.
        """
        logger.info(f"TR received: Screen No. {screen_no}, Request Name: {rq_name}, TR Code: {tr_code}")
        
        if tr_code == "opt10081": # 일봉 데이터
            df_columns = ["일자", "현재가", "거래량", "시가", "고가", "저가"]
            rows = []
            repeat_cnt = self.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name)
            
            for i in range(repeat_cnt):
                row_data = {}
                for col_name in df_columns:
                    data = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)",
                                                   tr_code, rq_name, i, col_name).strip()
                    row_data[col_name] = data
                rows.append(row_data)
            self.tr_data = pd.DataFrame(rows)
            
        elif tr_code == "opw00001": # 예수금 요청 TR
            deposit = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, 0, "예수금").strip()
            self.tr_data = {"예수금": int(deposit)}
        
        elif tr_code == "opw00018": # 계좌 잔고 TR
            account_data = {}
            account_data["총평가금액"] = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, 0, "총평가금액").strip()
            account_data["총손익금액"] = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, 0, "총손익금액").strip()
            
            positions = []
            repeat_cnt = self.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name)
            for i in range(repeat_cnt):
                item = {}
                item["종목코드"] = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "종목코드").strip()
                item["종목명"] = self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "종목명").strip()
                item["보유수량"] = int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "보유수량").strip())
                item["매입가"] = int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "매입가").strip())
                item["현재가"] = int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "현재가").strip())
                positions.append(item)
            account_data["보유종목"] = positions
            self.tr_data = account_data
        
        else:
            logger.warning(f"Unhandled TR code: {tr_code}")
            self.tr_data = {"error": f"Unhandled TR code: {tr_code}"}

        if self.tr_event_loop.isRunning():
            self.tr_event_loop.quit()

    def _on_receive_real_data(self, stock_code, real_type, real_data_str):
        """
        실시간 데이터 수신 이벤트 핸들러.
        실시간 데이터(FID)를 파싱하고 self.real_time_data에 저장한 후 시그널을 발생시킵니다.
        """
        try:
            current_price = abs(int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 10).strip())) # 현재가
            daily_change = int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 11).strip()) # 전일대비
            daily_change_pct = float(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 12).strip()) # 등락률
            accumulated_volume = int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 13).strip()) # 누적거래량
            open_price = abs(int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 16).strip())) # 시가
            high_price = abs(int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 17).strip())) # 고가
            low_price = abs(int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 18).strip())) # 저가
            chegyul_gangdo = float(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 229).strip()) # 체결강도
            total_buy_cvol = int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 272).strip()) # 매수총잔량
            total_sell_cvol = int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 273).strip()) # 매도총잔량
            accumulated_trading_value = int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", stock_code, 30).strip()) # 누적거래대금 (단위: 원)

            self.real_time_data[stock_code] = {
                "current_price": current_price,
                "daily_change": daily_change,
                "current_daily_change_pct": daily_change_pct, # 등락률
                "volume": accumulated_volume, # 누적거래량
                "open_price": open_price,
                "high_price": high_price,
                "low_price": low_price,
                "chegyul_gangdo": chegyul_gangdo,
                "total_buy_cvol": total_buy_cvol,
                "total_sell_cvol": total_sell_cvol,
                "trading_value": accumulated_trading_value, # 누적거래대금
                "timestamp": get_current_time_str()
            }
            
            # 실시간 데이터 업데이트를 외부 모듈에 알리기 위해 시그널 발생
            self.real_time_signal.emit({
                "stock_code": stock_code,
                "real_type": real_type,
                "data": self.real_time_data[stock_code]
            })
            logger.debug(f"Real-time data received and stored: {stock_code}, Current Price: {current_price}")
        except Exception as e:
            logger.error(f"Error parsing real-time data for {stock_code}: {e}", exc_info=True)


    def _on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        """
        키움 API 메시지 수신 이벤트 핸들러.
        """
        logger.info(f"📩 Message received: Screen No. {screen_no}, Request Name: {rq_name}, TR Code: {tr_code}, Message: {msg}")

    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        """
        체결/잔고 데이터 수신 이벤트 핸들러.
        이 부분은 TradeManager 또는 MonitorPositions에서 처리될 수 있습니다.
        """
        logger.info(f"📋 Conclusion/Balance data received: Division={gubun}, Item Count={item_cnt}, FID List={fid_list}")

    def _on_receive_real_condition(self, stock_code, event_type, condition_name, condition_index):
        """
        실시간 조건검색 이벤트 수신 핸들러.
        Args:
            stock_code (str): 종목코드
            event_type (str): "I" (편입), "D" (이탈)
            condition_name (str): 조건식 이름
            condition_index (str): 조건식 인덱스
        """
        stock_name = self.get_stock_name(stock_code) # 캐시된 종목명 사용
        event_msg = "편입" if event_type == "I" else "이탈"
        logger.info(f"📡 [Real-time Condition Event] {stock_name}({stock_code}) - {condition_name} ({condition_index}) {event_msg}")
        
        # RealTimeConditionManager로 이 이벤트를 전달하기 위해 시그널 발생
        self.real_condition_signal.emit(stock_code, event_type, condition_name, condition_index)

    def request_tr_data(self, tr_code, rq_name, input_values, prev_next, screen_no, timeout_ms=10000):
        """
        TR 요청을 보내고 응답을 기다리는 함수.
        Args:
            tr_code (str): TR 코드 (예: "opt10081")
            rq_name (str): 요청 이름
            input_values (dict): SetInputValue에 설정할 키-값 쌍
            prev_next (int): 연속 조회 (0: 처음, 2: 다음)
            screen_no (str): 화면번호
            timeout_ms (int): 타임아웃 (밀리초)
        Returns:
            Any: TR 응답 데이터 (DataFrame 또는 dict)
        """
        self.tr_data = None
        self.tr_event_loop = QEventLoop()

        for key, value in input_values.items():
            self.kiwoom.dynamicCall("SetInputValue(QString, QString)", key, str(value))
        
        ret = self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)",
                                      rq_name, tr_code, prev_next, screen_no)

        if ret != 0:
            error_msg = get_error_message(ret)
            logger.error(f"CommRqData call failed: {tr_code} - {error_msg}")
            return {"error": f"CommRqData failed: {error_msg}"}

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self.tr_event_loop.quit)
        timer.start(timeout_ms)
        self.tr_event_loop.exec_()

        if not timer.isActive() and self.tr_data is None:
            logger.error(f"TR response timeout or no data: {tr_code} - {rq_name}")
            return {"error": "TR request timeout or no data"}
        
        return self.tr_data

    def get_code_list_by_market(self, market):
        """시장별 종목코드 목록을 반환합니다."""
        codes = self.kiwoom.dynamicCall("GetCodeListByMarket(QString)", market)
        return codes.split(';') if codes else []

    def get_stock_name(self, code):
        """
        주어진 종목코드에 대한 종목명을 반환합니다.
        캐시를 사용하여 중복 API 호출을 방지합니다.
        """
        if code in self._stock_name_cache:
            return self._stock_name_cache[code]

        name = self.kiwoom.dynamicCall("GetMasterCodeName(QString)", code).strip()
        if name:
            self._stock_name_cache[code] = name
            return name
        return "Unknown"

    def get_master_stock_state(self, code):
        """
        주어진 종목코드에 대한 종목 상태(예: '관리종목', '투자경고')를 반환합니다.
        """
        try:
            state_info = self.kiwoom.dynamicCall("GetMasterStockState(QString)", code)
            return state_info.strip() if state_info else ""
        except Exception as e:
            logger.warning(f"GetMasterStockState call failed ({code}): {e}. Returning empty string.", exc_info=True)
            return ""

    def SetRealReg(self, screen_no, code_list, fid_list, real_type):
        """실시간 데이터를 등록합니다."""
        codes_str = ";".join(code_list) if isinstance(code_list, list) else code_list
        fids_str = ";".join(map(str, fid_list)) if isinstance(fid_list, list) else fid_list
        
        self.kiwoom.dynamicCall("SetRealReg(QString, QString, QString, QString)",
                                screen_no, codes_str, fids_str, real_type)
        logger.info(f"Real-time registration request: Screen No. {screen_no}, Stocks {codes_str}, FIDs {fids_str}, Type {real_type}")

    def SetRealRemove(self, screen_no, codes):
        """실시간 데이터를 해제합니다."""
        self.kiwoom.dynamicCall("SetRealRemove(QString, QString)", screen_no, codes)
        logger.info(f"Real-time unregistration request: Screen No. {screen_no}, Stocks {codes}")

    def generate_real_time_screen_no(self):
        """
        고유한 실시간 화면번호를 생성하여 반환합니다.
        REALTIME_SCREEN_NO_PREFIX (5000번대) 내에서 순환하며 사용합니다.
        """
        # 5000 ~ 5099 범위 내에서 순환
        min_screen_no = int(REALTIME_SCREEN_NO_PREFIX + "00")
        max_screen_no = int(REALTIME_SCREEN_NO_PREFIX + "99")

        self._real_time_screen_no_counter += 1
        if self._real_time_screen_no_counter > max_screen_no:
            self._real_time_screen_no_counter = min_screen_no
        
        return str(self._real_time_screen_no_counter)

    def get_condition_name_list(self):
        """
        사용자 저장 조건식 목록을 반환합니다.
        Returns:
            dict: {조건식 이름: 조건식 인덱스}
        """
        raw_str = self.kiwoom.dynamicCall("GetConditionNameList()")
        condition_map = {}
        if raw_str:
            for cond in raw_str.split(';'):
                if not cond.strip():
                    continue
                try:
                    index, name = cond.split('^')
                    condition_map[name.strip()] = int(index.strip())
                except ValueError:
                    logger.warning(f"Malformed condition string: {cond}")
                    continue
        self.condition_list = condition_map
        logger.info(f"📑 Loaded condition list: {list(condition_map.keys())}")
        return condition_map

    def SendCondition(self, screen_no, condition_name, index, search_type):
        """
        조건검색을 실행합니다.
        Args:
            screen_no (str): 화면번호
            condition_name (str): 조건식 이름
            index (int): 조건식 인덱스
            search_type (int): 0: 일반조회, 1: 실시간조회
        Returns:
            int: 1 성공, 0 실패
        """
        logger.info(f"🧠 Sending condition: {condition_name} (Index: {index}, Real-time: {search_type})")
        ret = self.kiwoom.dynamicCall("SendCondition(QString, QString, int, int)",
                                      screen_no, condition_name, index, search_type)
        if ret == 1:
            logger.info(f"✅ Condition '{condition_name}' sent successfully.")
        else:
            logger.error(f"❌ Failed to send condition '{condition_name}'. Return code: {ret}")
        return ret
    
    def GetCommRealData(self, code, fid):
        """
        특정 FID에 대한 실시간 데이터를 가져옵니다.
        이것은 기본 QAxWidget 메서드에 대한 래퍼입니다.
        """
        return self.kiwoom.dynamicCall("GetCommRealData(QString, int)", code, fid)

