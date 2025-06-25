# modules/Kiwoom/kiwoom_query_helper.py

import sys
import logging
from PyQt5.QtCore import QEventLoop, QTimer # 💡 QEventLoop와 QTimer 임포트

from modules.common.utils import get_current_time_str 

logger = logging.getLogger(__name__)

class KiwoomQueryHelper:
    # __init__ 메서드는 ocx_instance (QAxWidget)와 pyqt_app_instance (QApplication)를 인자로 받습니다.
    def __init__(self, ocx_instance, pyqt_app_instance):
        self.ocx = ocx_instance # 외부에서 생성된 QAxWidget 인스턴스를 받습니다.
        self.pyqt_app = pyqt_app_instance # 외부에서 생성된 QApplication 인스턴스를 받습니다.
        
        self.connected_state = -1 # 초기 상태: 미접속 (0: 연결 성공)
        
        # 💡 로그인 대기를 위한 전용 QEventLoop와 QTimer
        self.connect_event_loop = QEventLoop() 
        self.connect_timer = QTimer() 
        self.connect_timer.setSingleShot(True) # 타이머 1회성 설정
        self.connect_timer.timeout.connect(self._on_connect_timeout) # 타임아웃 시 콜백 연결
        
        # Kiwoom API 이벤트 연결
        self.ocx.OnEventConnect.connect(self._on_event_connect)
        self.ocx.OnReceiveRealData.connect(self._on_receive_real_data) # 💡 실시간 데이터 이벤트 연결
        self.ocx.OnReceiveMsg.connect(self._on_receive_msg) # 메시지 이벤트 연결
        self.ocx.OnReceiveChejanData.connect(self._on_receive_chejan_data) # 체결/잔고 이벤트 연결

        # 💡 실시간 데이터 저장용 딕셔너리
        # { '종목코드': {'current_price': 0, 'trading_volume': 0, 'chegyul_gangdo': 0.0, 'total_buy_cvol': 0, ...}, ... }
        self.real_time_data = {} 
        self.real_time_registered_screens = {} # {스크린번호: [종목코드, ...]}

        # 💡 시장 종목 코드 리스트 캐싱 (최초 1회만 조회)
        self._all_stock_codes = {"0": [], "10": []} # "0": KOSPI, "10": KOSDAQ

        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def _on_event_connect(self, err_code):
        """
        키움 API 로그인 연결 상태 변경 시 호출되는 이벤트 핸들러.
        """
        self.connected_state = err_code # 연결 상태 업데이트
        if err_code == 0:
            logger.info(f"[{get_current_time_str()}]: [✅] 로그인 성공")
        else:
            logger.error(f"[{get_current_time_str()}]: [❌] 로그인 실패 (에러 코드: {err_code})")
        
        # 💡 연결 타이머가 활성 상태라면 중지
        if self.connect_timer.isActive():
            self.connect_timer.stop()

        # 💡 로그인 대기 중인 이벤트 루프가 있다면 종료
        if self.connect_event_loop.isRunning():
            self.connect_event_loop.exit()

    def _on_connect_timeout(self):
        """로그인 연결 타임아웃 발생 시 호출되는 콜백."""
        if self.connect_event_loop.isRunning():
            logger.error(f"[{get_current_time_str()}]: ❌ Kiwoom API 연결 실패 - 타임아웃 ({self.connect_timer.interval()}ms)")
            self.connected_state = -999 # 타임아웃을 나타내는 임의의 에러 코드
            self.connect_event_loop.exit() # 이벤트 루프 강제 종료

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
                
                # 💡 추가된 FID 정보
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
        # 다른 real_type (예: "주식호가")에 대한 처리 로직도 추가 가능

    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        """
        💡 체결/잔고 데이터 수신 이벤트 핸들러.
        매매체결통보, 잔고편입/편출 통보 등을 수신합니다.
        (TradeManager가 이 이벤트를 연결하고 처리하는 것이 더 적절합니다.)
        """
        pass # TradeManager에서 주로 처리하므로 여기서는 pass

    def connect_kiwoom(self, timeout_ms=30000): # 💡 타임아웃 인자 추가 (기본 30초)
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
        
        # 💡 로그인 타임아웃 타이머 설정
        self.connect_timer.start(timeout_ms)
        
        # 💡 로그인 성공/실패 응답을 기다리기 위해 전용 QEventLoop 실행
        self.connect_event_loop.exec_()
        
        # 이벤트 루프가 종료된 후 연결 상태 확인
        if self.connected_state == 0: 
            return True
        else:
            logger.critical(f"❌ Kiwoom API 연결 실패 (에러 코드: {self.connected_state} 또는 타임아웃 발생)")
            return False

    def disconnect_kiwoom(self):
        """
        키움증권 API 연결을 종료합니다.
        """
        if self.ocx.dynamicCall("GetConnectState()") == 1: # 연결되어 있다면
            logger.info("🔌 Kiwoom API 연결 종료") # 메시지 변경
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

    # 💡 시장별 종목코드 리스트를 가져오는 메서드 추가
    def get_code_list_by_market(self, market_type="0"):
        """
        시장별(코스피, 코스닥 등) 종목 코드를 가져옵니다.
        API GetCodeListByMarket 함수 사용.
        Args:
            market_type (str): "0" (코스피), "10" (코스닥), "3" (ELW), "4" (뮤추얼펀드),
                               "8" (ETF), "50" (KONEX), "40" (선물), "60" (옵션)
        Returns:
            list: 해당 시장의 종목 코드 리스트 (예: ["005930", "000660", ...])
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
            self._all_stock_codes[market_type] = codes # 캐싱
            logger.info(f"✅ 시장 ({market_type}) 종목 코드 {len(codes)}개 로드 완료.")
            return codes
        except Exception as e:
            logger.error(f"❌ 시장 ({market_type}) 종목 코드 리스트 조회 실패: {e}", exc_info=True)
            return []

    def generate_real_time_screen_no(self):
        """
        실시간 데이터 등록에 사용할 고유한 화면번호를 생성합니다 (2000번대).
        """
        # 임의의 고유한 4자리 숫자 생성 (2000 ~ 9999 범위)
        # Kiwoom API는 화면번호를 문자열로 받으므로 str로 변환
        unique_part = str(int(time.time() * 100000))[-4:] # 현재 시간을 밀리초로 변환 후 뒤 4자리 사용
        screen_no = str(2000 + int(unique_part) % 7999) # 2000 ~ 9999 범위
        return screen_no

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
                    # 해당 화면번호에 등록된 모든 종목 코드를 가져와서 real_time_data에서 제거
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
                if stock_code in self.real_time_data: # 해당 종목의 실시간 데이터 제거
                    del self.real_time_data[stock_code]
                logger.info(f"🔴 화면번호 {screen_no}, 종목 {stock_code} 실시간 등록 해제 완료.")

        except Exception as e:
            logger.error(f"❌ 실시간 등록 해제 실패: 화면번호 {screen_no}, 종목 {stock_code} - {e}", exc_info=True)

