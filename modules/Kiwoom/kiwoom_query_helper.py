# modules/Kiwoom/kiwoom_query_helper.py

import sys
import logging
from PyQt5.QtCore import QEventLoop, QTimer 

from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    def __init__(self, ocx_instance, pyqt_app_instance):
        self.ocx = ocx_instance 
        self.pyqt_app = pyqt_app_instance 
        
        self.connected_state = -1 
        
        self.connect_event_loop = QEventLoop() 
        self.connect_timer = QTimer() 
        self.connect_timer.setSingleShot(True) 
        self.connect_timer.timeout.connect(self._on_connect_timeout) 
        
        # Kiwoom API 이벤트 연결
        self.ocx.OnEventConnect.connect(self._on_event_connect)
        self.ocx.OnReceiveRealData.connect(self._on_receive_real_data) # 💡 실시간 데이터 이벤트 연결
        self.ocx.OnReceiveMsg.connect(self._on_receive_msg) # 메시지 이벤트 연결
        self.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data) # 체결/잔고 이벤트 연결

        # 💡 실시간 데이터 저장용 딕셔너리
        # { '종목코드': {'현재가': 0, '시가': 0, '고가': 0, '저가': 0, '거래량': 0, ...}, ... }
        self.real_time_data = {} 
        self.real_time_registered_screens = {} # {스크린번호: [종목코드, ...]}

        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def _on_event_connect(self, err_code):
        self.connected_state = err_code 
        if err_code == 0:
            logger.info(f"[{get_current_time_str()}]: [✅] 로그인 성공")
        else:
            logger.error(f"[{get_current_time_str()}]: [❌] 로그인 실패 (에러 코드: {err_code})")
        
        if self.connect_timer.isActive():
            self.connect_timer.stop()

        if self.connect_event_loop.isRunning():
            self.connect_event_loop.exit()

    def _on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        """API로부터의 메시지를 수신했을 때 호출됩니다."""
        logger.info(f"[{get_current_time_str()}]: [API 메시지] [{rq_name}] {msg} (화면: {screen_no})")

    def _on_receive_real_data(self, stock_code, real_type, real_data):
        """
        💡 실시간 시세 데이터 수신 이벤트 핸들러.
        종목코드, 실시간 타입(주식체결, 주식호가 등), 실시간 데이터(FID 리스트)를 받습니다.
        """
        # logger.debug(f"실시간 데이터 수신: {stock_code}, 타입: {real_type}")
        
        # '주식체결' (real_type: "주식체결") 데이터를 예시로 처리
        if real_type == "주식체결":
            try:
                # FID 들이 문자열로 넘어오므로, GetCommRealData를 통해 하나씩 가져옵니다.
                current_price = abs(int(self.ocx.GetCommRealData(stock_code, 10).strip())) # 현재가 (절대값)
                trading_volume = abs(int(self.ocx.GetCommRealData(stock_code, 15).strip())) # 거래량 (누적)
                
                # 필요한 다른 FID들도 여기에 추가:
                # 20: 체결시간, 11: 전일대비, 12: 등락률, 13: 누적거래량, 14: 누적거래대금
                # 27: (최우선)매도호가, 28: (최우선)매수호가
                # 30: 매도호가1, 31: 매수호가1, 32: 매도잔량1, 33: 매수잔량1
                # ...
                
                if stock_code not in self.real_time_data:
                    self.real_time_data[stock_code] = {}
                
                self.real_time_data[stock_code].update({
                    'current_price': current_price,
                    'trading_volume': trading_volume,
                    # 다른 실시간 데이터도 필요하면 여기에 추가
                    'last_update_time': get_current_time_str()
                })
                # logger.debug(f"실시간 업데이트: {stock_code} - 현재가: {current_price:,}")

            except Exception as e:
                logger.error(f"❌ 실시간 데이터 처리 오류 ({stock_code}, {real_type}): {e}", exc_info=True)
        # 다른 real_type (예: "주식호가")에 대한 처리 로직도 추가 가능

    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        """
        💡 체결/잔고 데이터 수신 이벤트 핸들러.
        매매체결통보, 잔고편입/편출 통보 등을 수신합니다.
        TradeManager에서 처리하는 것이 일반적이지만, 여기에서도 수신은 가능.
        (TradeManager가 이 이벤트를 연결하고 처리하는 것이 더 적절합니다.)
        """
        # logger.debug(f"체결 데이터 수신 (Helper): Gubun: {gubun}, FID List: {fid_list}")
        pass # TradeManager에서 주로 처리하므로 여기서는 pass

    def CommConnect(self, timeout_ms=30000):
        if self.ocx.dynamicCall("GetConnectState()") == 1: 
            logger.info("✅ 키움 API 이미 연결됨.")
            self.connected_state = 0 
            return True

        logger.info("✅ 키움 API 로그인 시도 중...")
        self.ocx.dynamicCall("CommConnect()")
        
        self.connect_timer.start(timeout_ms)
        
        self.connect_event_loop.exec_()
        
        if self.connected_state == 0: 
            return True
        else:
            logger.critical(f"❌ Kiwoom API 연결 실패 (에러 코드: {self.connected_state} 또는 타임아웃 발생)")
            return False

    def _on_connect_timeout(self):
        if self.connect_event_loop.isRunning(): 
            logger.error(f"[{get_current_time_str()}]: ❌ Kiwoom API 연결 실패 - 타임아웃 ({self.connect_timer.interval()}ms)")
            self.connected_state = -999 
            self.connect_event_loop.exit()

    def Disconnect(self):
        if self.ocx.dynamicCall("GetConnectState()") == 1: 
            logger.info("🔌 Kiwoom API 연결 종료 시도...") 
            self.ocx.dynamicCall("CommTerminate()") 
            self.connected_state = -1 
            logger.info("🔌 Kiwoom API 연결 해제 완료.")
        else:
            logger.info("🔌 이미 연결되지 않은 상태입니다.")
        # 실시간 데이터 등록 해제 (필요시)
        self.SetRealRemove("ALL", "ALL") # 모든 화면번호의 모든 종목 실시간 등록 해제

    def get_login_info(self, tag):
        return self.ocx.dynamicCall("GetLoginInfo(QString)", tag)

    def get_stock_name(self, stock_code):
        name = self.ocx.dynamicCall("GetMasterCodeName(QString)", stock_code)
        if not name:
            logger.warning(f"종목명 조회 실패: {stock_code}")
            return "Unknown"
        return name

    # CommGetData 및 GetRepeatCnt는 TR 요청에서 사용됨 (KiwoomTrRequest에서 호출)
    # def CommGetData(self, tr_code, record_name, item_name, index):
    #     return self.ocx.CommGetData(tr_code, record_name, index, item_name)

    # def GetRepeatCnt(self, tr_code, record_name):
    #     return self.ocx.GetRepeatCnt(tr_code, record_name)

    # 💡 실시간 데이터 등록/해제 함수 추가
    def SetRealReg(self, screen_no, stock_code, fid_list, opt_type="0"):
        """
        실시간 데이터를 등록합니다.
        Args:
            screen_no (str): 화면번호 (2000~9999). 고유하게 관리해야 함.
            stock_code (str): 종목코드 (복수 등록 시 세미콜론(;)으로 구분)
            fid_list (str): 실시간으로 받을 FID 목록 (세미콜론(;)으로 구분).
                            예: "10;11;13;..." (현재가;전일대비;누적거래량)
            opt_type (str): "0"은 종목 추가, "1"은 종목 제거. (CommConnect 이전에 호출 시 "0"으로만 가능)
        """
        try:
            self.ocx.SetRealReg(screen_no, stock_code, fid_list, opt_type)
            if opt_type == "0": # 등록
                if screen_no not in self.real_time_registered_screens:
                    self.real_time_registered_screens[screen_no] = []
                # 기존에 등록된 종목은 무시하고 추가되는 종목만 리스트에 넣음 (SetRealReg의 특징)
                for code in stock_code.split(';'):
                    if code and code not in self.real_time_registered_screens[screen_no]:
                        self.real_time_registered_screens[screen_no].append(code)
                logger.info(f"🟢 실시간 등록 성공: 화면번호 {screen_no}, 종목: {stock_code}, FID: {fid_list}")
            elif opt_type == "1": # 해제
                # 실제 SetRealReg("화면번호", "종목코드", "", "1")로 해제 시 종목코드만 필요함
                # 여기서는 내부적으로 등록된 리스트에서 제거
                if screen_no in self.real_time_registered_screens:
                    for code in stock_code.split(';'):
                        if code in self.real_time_registered_screens[screen_no]:
                            self.real_time_registered_screens[screen_no].remove(code)
                    if not self.real_time_registered_screens[screen_no]:
                        del self.real_time_registered_screens[screen_no] # 비어있는 화면번호 제거
                logger.info(f"🔴 실시간 해제 성공: 화면번호 {screen_no}, 종목: {stock_code}")

        except Exception as e:
            logger.error(f"❌ 실시간 등록/해제 실패: {stock_code} (화면: {screen_no}, 타입: {opt_type}) - {e}", exc_info=True)

    def SetRealRemove(self, screen_no, stock_code):
        """
        등록된 실시간 데이터를 해제합니다.
        Args:
            screen_no (str): 화면번호 ("ALL" 또는 특정 화면번호)
            stock_code (str): 종목코드 ("ALL" 또는 특정 종목코드)
        """
        try:
            # SetRealRemove("ALL", "ALL")은 모든 실시간 등록을 해제합니다.
            # SetRealRemove("화면번호", "ALL")은 해당 화면번호의 모든 종목 실시간 등록 해제.
            # SetRealRemove("화면번호", "종목코드")는 해당 화면번호의 특정 종목 실시간 등록 해제.
            self.ocx.SetRealRemove(screen_no, stock_code)
            
            if screen_no == "ALL":
                self.real_time_registered_screens = {}
                self.real_time_data = {} # 모든 실시간 데이터 초기화
                logger.info("🔴 모든 화면의 모든 실시간 종목 등록 해제 완료.")
            elif stock_code == "ALL":
                if screen_no in self.real_time_registered_screens:
                    del self.real_time_registered_screens[screen_no]
                    # 해당 화면번호에 등록된 모든 종목의 실시간 데이터 제거 (self.real_time_data에서)
                    codes_to_remove = [c for c, data in self.real_time_data.items() if c in self.real_time_registered_screens.get(screen_no, [])] # 이 부분은 SetRealReg과 함께 관리 필요
                    # 좀 더 복잡한 로직이 필요하므로, 일단은 전체 삭제가 아니라 해당 화면번호의 종목만 제거하는 것으로 로직을 단순화
                    for c in codes_to_remove:
                        if c in self.real_time_data:
                            del self.real_time_data[c]
                logger.info(f"🔴 화면번호 {screen_no}의 모든 실시간 종목 등록 해제 완료.")
            else:
                if screen_no in self.real_time_registered_screens and stock_code in self.real_time_registered_screens[screen_no]:
                    self.real_time_registered_screens[screen_no].remove(stock_code)
                    if not self.real_time_registered_screens[screen_no]:
                        del self.real_time_registered_screens[screen_no]
                if stock_code in self.real_time_data: # 해당 종목의 실시간 데이터 제거
                    del self.real_time_data[stock_code]
                logger.info(f"🔴 화면번호 {screen_no}, 종목 {stock_code} 실시간 등록 해제 완료.")

        except Exception as e:
            logger.error(f"❌ 실시간 등록 해제 실패: 화면번호 {screen_no}, 종목 {stock_code} - {e}", exc_info=True)

    def generate_real_time_screen_no(self):
        """
        실시간 데이터 등록에 사용할 고유한 화면번호를 생성합니다 (2000번대).
        """
        # 임의의 고유한 4자리 숫자 생성 (2000 ~ 9999 범위)
        unique_part = str(int(time.time() * 100000))[-4:] # 현재 시간을 밀리초로 변환 후 뒤 4자리 사용
        screen_no = str(2000 + int(unique_part) % 7999) # 2000 ~ 9999 범위
        return screen_no

