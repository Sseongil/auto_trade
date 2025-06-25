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
        
        self.ocx.OnEventConnect.connect(self._on_event_connect)
        self.ocx.OnReceiveRealData.connect(self._on_receive_real_data) 
        self.ocx.OnReceiveMsg.connect(self._on_receive_msg) 
        self.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data) 

        self.real_time_data = {} 
        self.real_time_registered_screens = {} 

        self._all_stock_codes = {"0": [], "10": []} 

        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def _on_event_connect(self, err_code):
        """
        키움 API 로그인 연결 상태 변경 시 호출되는 이벤트 핸들러.
        """
        self.connected_state = err_code 
        if err_code == 0:
            logger.info(f"[{get_current_time_str()}]: [✅] 로그인 성공")
        else:
            logger.error(f"[{get_current_time_str()}]: [❌] 로그인 실패 (에러 코드: {err_code})")
        
        if self.connect_timer.isActive():
            self.connect_timer.stop()

        if self.connect_event_loop.isRunning():
            self.connect_event_loop.exit()

    def _on_connect_timeout(self):
        """로그인 연결 타임아웃 발생 시 호출되는 콜백."""
        if self.connect_event_loop.isRunning():
            logger.error(f"[{get_current_time_str()}]: ❌ Kiwoom API 연결 실패 - 타임아웃 ({self.connect_timer.interval()}ms)")
            self.connected_state = -999 
            self.connect_event_loop.exit() 

    def _on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        """API로부터의 메시지를 수신했을 때 호출됩니다."""
        logger.info(f"[{get_current_time_str()}]: [API 메시지] [{rq_name}] {msg} (화면: {screen_no})")

    def _on_receive_real_data(self, stock_code, real_type, real_data):
        """
        💡 실시간 시세 데이터 수신 이벤트 핸들러.
        종목코드, 실시간 타입(주식체결, 주식호가 등), 실시간 데이터(FID 리스트)를 받습니다.
        """
        if real_type == "주식체결":
            try:
                current_price = abs(int(self.ocx.GetCommRealData(stock_code, 10).strip())) # 현재가 (절대값)
                trading_volume = abs(int(self.ocx.GetCommRealData(stock_code, 15).strip())) # 거래량 (누적)
                
                chegyul_gangdo = float(self.ocx.GetCommRealData(stock_code, 228).strip()) if self.ocx.GetCommRealData(stock_code, 228).strip() else 0.0 # 체결강도
                total_buy_cvol = abs(int(self.ocx.GetCommRealData(stock_code, 851).strip())) # 총 매수 잔량
                total_sell_cvol = abs(int(self.ocx.GetCommRealData(stock_code, 852).strip())) # 총 매도 잔량
                highest_bid_price = abs(int(self.ocx.GetCommRealData(stock_code, 28).strip())) # 최우선 매수호가
                lowest_ask_price = abs(int(self.ocx.GetCommRealData(stock_code, 27).strip())) # 최우선 매도호가

                if stock_code not in self.real_time_data:
                    self.real_time_data[stock_code] = {}
                
                self.real_time_data[stock_code].update({
                    'current_price': current_price,
                    'trading_volume': trading_volume,
                    'chegyul_gangdo': chegyul_gangdo,
                    'total_buy_cvol': total_buy_cvol,
                    'total_sell_cvol': total_sell_cvol,
                    '최우선매수호가': highest_bid_price,
                    '최우선매도호가': lowest_ask_price,
                    'last_update_time': get_current_time_str()
                })
            except Exception as e:
                logger.error(f"❌ 실시간 데이터 처리 오류 ({stock_code}, {real_type}): {e}", exc_info=True)        

    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        """
        💡 체결/잔고 데이터 수신 이벤트 핸들러.
        매매체결통보, 잔고편입/편출 통보 등을 수신합니다.
        (TradeManager가 이 이벤트를 연결하고 처리하는 것이 더 적절합니다.)
        """
        pass 

    def connect_kiwoom(self, timeout_ms=30000): 
        """
        키움증권 API에 연결을 시도합니다.
        지정된 시간(timeout_ms) 내에 연결되지 않으면 타임아웃 처리됩니다.
        """
        if self.ocx.dynamicCall("GetConnectState()") == 0:
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

    def disconnect_kiwoom(self):
        """
        키움증권 API 연결을 종료합니다.
        """
        if self.ocx.dynamicCall("GetConnectState()") == 1: 
            logger.info("🔌 Kiwoom API 연결 종료") 
            self.connected_state = -1 
        else:
            logger.info("🔌 이미 연결되지 않은 상태입니다.")

    def get_login_info(self, tag):
        """
        로그인 정보를 요청합니다 (예: "ACCNO" for 계좌번호).
        """
        return self.ocx.dynamicCall("GetLoginInfo(QString)", tag)

    def get_stock_name(self, stock_code):
        """종목 코드를 이용해 종목명을 가져옵니다."""
        name = self.ocx.dynamicCall("GetMasterCodeName(QString)", stock_code)
        if not name:
            logger.warning(f"종목명 조회 실패: {stock_code}")
            return "Unknown"
        return name

    def get_code_list_by_market(self, market_type="0"):
        """
        시장별(코스피, 코스닥 등) 종목 코드를 가져옵니다.
        API GetCodeListByMarket 함수 사용.
        """
        if market_type in self._all_stock_codes and self._all_stock_codes[market_type]:
            logger.info(f"캐시된 종목 코드 리스트 반환 (시장: {market_type})")
            return self._all_stock_codes[market_type]

        if self.connected_state != 0:
            logger.error("❌ Kiwoom API에 연결되지 않아 종목 코드 리스트를 가져올 수 없습니다.")
            return []

        try:
            codes_str = self.ocx.dynamicCall("GetCodeListByMarket(QString)", market_type)
            codes = [code.strip() for code in codes_str.split(';') if code.strip()]
            self._all_stock_codes[market_type] = codes 
            logger.info(f"✅ 시장 ({market_type}) 종목 코드 {len(codes)}개 로드 완료.")
            return codes
        except Exception as e:
            logger.error(f"❌ 시장 ({market_type}) 종목 코드 리스트 조회 실패: {e}", exc_info=True)
            return []

    def generate_real_time_screen_no(self):
        """
        실시간 데이터 등록에 사용할 고유한 화면번호를 생성합니다 (2000번대).
        """
        import time # 함수 내에서 임포트하여 필요 시 로드
        unique_part = str(int(time.time() * 100000))[-4:] 
        screen_no = str(2000 + int(unique_part) % 7999) 
        return screen_no

    def SetRealReg(self, screen_no, stock_code, fid_list, opt_type="0"):
        """
        실시간 데이터를 등록합니다.
        """
        try:
            self.ocx.SetRealReg(screen_no, stock_code, fid_list, opt_type)
            if opt_type == "0": 
                if screen_no not in self.real_time_registered_screens:
                    self.real_time_registered_screens[screen_no] = []
                for code in stock_code.split(';'):
                    if code and code not in self.real_time_registered_screens[screen_no]:
                        self.real_time_registered_screens[screen_no].append(code)
                logger.info(f"🟢 실시간 등록 성공: 화면번호 {screen_no}, 종목: {stock_code}, FID: {fid_list}")
            elif opt_type == "1": 
                if screen_no in self.real_time_registered_screens:
                    for code in stock_code.split(';'):
                        if code in self.real_time_registered_screens[screen_no]:
                            self.real_time_registered_screens[screen_no].remove(code)
                    if not self.real_time_registered_screens[screen_no]:
                        del self.real_time_registered_screens[screen_no] 
                logger.info(f"🔴 실시간 해제 성공: 화면번호 {screen_no}, 종목: {stock_code}")

        except Exception as e:
            logger.error(f"❌ 실시간 등록/해제 실패: {stock_code} (화면: {screen_no}, 타입: {opt_type}) - {e}", exc_info=True)

    def SetRealRemove(self, screen_no, stock_code):
        """
        등록된 실시간 데이터를 해제합니다.
        """
        try:
            self.ocx.SetRealRemove(screen_no, stock_code)
            
            if screen_no == "ALL":
                self.real_time_registered_screens = {}
                self.real_time_data = {} 
                logger.info("🔴 모든 화면의 모든 실시간 종목 등록 해제 완료.")
            elif stock_code == "ALL":
                if screen_no in self.real_time_registered_screens:
                    codes_in_screen = self.real_time_registered_screens[screen_no]
                    for code in codes_in_screen:
                        if code in self.real_time_data:
                            del self.real_time_data[code]
                    del self.real_time_registered_screens[screen_no]
                logger.info(f"🔴 화면번호 {screen_no}의 모든 실시간 종목 등록 해제 완료.")
            else:
                if screen_no in self.real_time_registered_screens and stock_code in self.real_time_registered_screens[screen_no]:
                    self.real_time_registered_screens[screen_no].remove(stock_code)
                    if not self.real_time_registered_screens[screen_no]:
                        del self.real_time_registered_screens[screen_no]
                if stock_code in self.real_time_data: 
                    del self.real_time_data[stock_code]
                logger.info(f"🔴 화면번호 {screen_no}, 종목 {stock_code} 실시간 등록 해제 완료.")

        except Exception as e:
            logger.error(f"❌ 실시간 등록 해제 실패: 화면번호 {screen_no}, 종목 {stock_code} - {e}", exc_info=True)

