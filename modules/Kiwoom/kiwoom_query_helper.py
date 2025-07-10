# modules/Kiwoom/kiwoom_query_helper.py

import logging
import time
import pandas as pd
import pythoncom # COM 객체 초기화를 위해 필요
from PyQt5.QtCore import QEventLoop, QTimer, QObject, pyqtSignal # QObject, pyqtSignal 추가
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from modules.common.error_codes import get_error_message
from modules.Kiwoom.tr_event_loop import TrEventLoop # TR 이벤트 루프 임포트
from datetime import datetime
from modules.common.utils import get_current_time_str # <<-- 이 라인을 추가했습니다.

logger = logging.getLogger(__name__)

class KiwoomQueryHelper(QObject): # QObject 상속
    # 실시간 데이터 수신 시 외부로 시그널 전송
    real_time_signal = pyqtSignal(dict)
    # TR 데이터 수신 시 외부로 시그널 전송 (필요시)
    tr_data_signal = pyqtSignal(str, str, str, dict)
    # 실시간 조건 검색 편입/이탈 시그널
    real_condition_signal = pyqtSignal(str, str, str, str) # code, event_type, condition_name, condition_index

    def __init__(self, kiwoom_ocx: QAxWidget, pyqt_app: QApplication):
        super().__init__()
        self.kiwoom = kiwoom_ocx
        self.app = pyqt_app
        self.connected = False
        self.filtered_df = pd.DataFrame()
        self.is_condition_checked = False # 조건 검색 실행 여부 플래그
        self.real_time_data = {} # 실시간 데이터를 저장할 딕셔너리
        self.condition_list = {} # 조건식 목록을 저장할 딕셔너리 {조건식명: 인덱스}
        self.real_condition_hits = {} # 실시간 조건 검색 통과 종목 {stock_code: stock_name}
        self.screen_no_counter = 5000 # 화면번호 카운터 (5000번대부터 시작)

        self._set_event_handlers()
        logger.info(f"{get_current_time_str()}: KiwoomQueryHelper initialized.")

    def _set_event_handlers(self):
        self.kiwoom.OnEventConnect.connect(self._on_event_connect)
        self.kiwoom.OnReceiveTrData.connect(self._on_receive_tr_data)
        self.kiwoom.OnReceiveRealData.connect(self._on_receive_real_data)
        self.kiwoom.OnReceiveMsg.connect(self._on_receive_msg)
        self.kiwoom.OnReceiveChejanData.connect(self._on_receive_chejan_data)
        self.kiwoom.OnReceiveConditionVer.connect(self._on_receive_condition_ver)
        self.kiwoom.OnReceiveTrCondition.connect(self._on_receive_tr_condition)
        self.kiwoom.OnReceiveRealCondition.connect(self._on_receive_real_condition) # 실시간 조건 검색 이벤트 연결

    def connect_kiwoom(self, timeout_ms=10000):
        """Kiwoom API에 연결을 시도합니다."""
        if self.kiwoom.dynamicCall("CommConnect()"):
            logger.info("✅ Kiwoom API 연결 요청 성공.")
            # 연결 이벤트 처리를 위한 QEventLoop 사용
            loop = QEventLoop()
            self.kiwoom.OnEventConnect.connect(loop.quit)
            QTimer.singleShot(timeout_ms, loop.quit) # 타임아웃 설정
            loop.exec_() # 이벤트 루프 대기
        else:
            logger.error("❌ Kiwoom API 연결 요청 실패.")
            return False

        if self.connected:
            logger.info("✅ 키움 API 로그인 성공")
            return True
        else:
            logger.error("❌ 키움 API 로그인 실패 또는 타임아웃.")
            return False

    def _on_event_connect(self, err_code):
        """CommConnect() 결과 이벤트."""
        self.connected = (err_code == 0)
        logger.info(f"[로그인 이벤트] 코드: {err_code}, 메시지: {get_error_message(err_code)}")
        # QEventLoop가 대기 중이라면 종료 시그널을 보냄 (connect_kiwoom에서 사용)

    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, s_prev_next, data_len, err_code, msg, detail_msg):
        """TR 데이터 수신 이벤트."""
        logger.info(f"TR 데이터 수신: {rq_name}, {tr_code}, prev_next: {s_prev_next}")
        # TrEventLoop에 데이터 전달
        TrEventLoop.instance().set_tr_data(rq_name, tr_code, s_prev_next)

    def _on_receive_real_data(self, stock_code, real_type, real_data):
        """실시간 데이터 수신 이벤트."""
        # logger.debug(f"실시간 데이터 수신: 종목코드={stock_code}, 타입={real_type}")

        if real_type == "주식체결":
            # FID 값들을 사용하여 데이터 파싱
            current_price = int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 10).strip().replace('+', '').replace('-', '')) # 현재가
            change_from_prev_day = int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 11).strip().replace('+', '').replace('-', '')) # 전일대비
            change_rate = float(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 12).strip()) # 등락률
            accum_volume = int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 13).strip()) # 누적거래량
            chegyul_gangdo = float(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 228).strip()) # 체결강도
            total_buy_cvol = int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 290).strip()) # 매수체결량
            total_sell_cvol = int(self.kiwoom.dynamicCall("GetCommRealData(QString, int)", real_type, 291).strip()) # 매도체결량

            # 실시간 데이터 딕셔너리 업데이트
            self.real_time_data[stock_code] = {
                'current_price': current_price,
                'change_from_prev_day': change_from_prev_day,
                'change_rate': change_rate,
                'accum_volume': accum_volume,
                'chegyul_gangdo': chegyul_gangdo,
                'total_buy_cvol': total_buy_cvol,
                'total_sell_cvol': total_sell_cvol,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            # 외부로 실시간 데이터 시그널 전송
            self.real_time_signal.emit(self.real_time_data[stock_code])
            # logger.debug(f"실시간 주식체결 데이터 업데이트: {stock_code} - 현재가: {current_price}, 체결강도: {chegyul_gangdo}")

    def _on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        """수신 메시지 이벤트."""
        logger.info(f"📩 메시지 수신: [{screen_no}] {msg} (화면: {screen_no}, 요청: {rq_name}, TR: {tr_code})")

    def _on_receive_chejan_data(self, gubun, item_cnt, fid_list):
        """체결 잔고 통보 이벤트."""
        # logger.info(f"체결 잔고 데이터 수신: 구분={gubun}, 항목수={item_cnt}, FID={fid_list}")
        # 'gubun'에 따라 체결(0) 또는 잔고(1) 데이터 처리
        if gubun == "0": # 체결 데이터
            stock_code = self.kiwoom.dynamicCall("GetChejanData(int)", 9001).strip() # 종목코드
            stock_name = self.kiwoom.dynamicCall("GetChejanData(int)", 302).strip() # 종목명
            order_no = self.kiwoom.dynamicCall("GetChejanData(int)", 9203).strip() # 주문번호
            order_type = self.kiwoom.dynamicCall("GetChejanData(int)", 902).strip() # 주문구분 (매수/매도)
            contract_quantity = int(self.kiwoom.dynamicCall("GetChejanData(int)", 901).strip()) # 체결수량
            contract_price = int(self.kiwoom.dynamicCall("GetChejanData(int)", 910).strip()) # 체결가격
            # 매수/매도 구분
            trade_type = "매수" if "매수" in order_type else "매도"

            logger.info(f"💰 체결 발생: {stock_name}({stock_code}) {trade_type} {contract_quantity}주 @ {contract_price}원 (주문번호: {order_no})")
            # MonitorPositions의 체결 처리 로직 호출
            if self.trade_manager_instance: # trade_manager_instance가 설정되어 있는지 확인
                self.trade_manager_instance.handle_chejan_data(stock_code, stock_name, trade_type, contract_quantity, contract_price, order_no)
            else:
                logger.warning("TradeManager 인스턴스가 설정되지 않아 체결 데이터 처리를 건너뜀.")

        elif gubun == "1": # 잔고 데이터 (필요시 구현)
            pass

    def _on_receive_condition_ver(self, ret, msg):
        """조건식 버전 수신 이벤트."""
        logger.info(f"[조건식 버전] 결과: {ret}, 메시지: {msg}")
        if ret == 1:
            self.get_condition_list_names() # 조건식 목록 요청
        TrEventLoop.instance().set_condition_version_received(True)

    def _on_receive_tr_condition(self, screen_no, stock_code, condition_name, condition_index, search_type, event_type, current_cnt, total_cnt):
        """TR 조건 검색 결과 수신 이벤트."""
        # logger.info(f"[TR 조건 검색] 종목: {stock_code}, 조건명: {condition_name}, 타입: {search_type}, 이벤트: {event_type}")
        if event_type == "0": # 종목 편입
            if stock_code not in self.filtered_df["ticker"].values:
                stock_name = self.get_stock_name(stock_code)
                new_row = pd.DataFrame([{"ticker": stock_code, "name": stock_name, "price": self.get_current_price(stock_code)}])
                self.filtered_df = pd.concat([self.filtered_df, new_row], ignore_index=True)
                logger.info(f"✅ TR 조건검색 편입: {stock_name}({stock_code})")
        elif event_type == "1": # 종목 이탈
            if stock_code in self.filtered_df["ticker"].values:
                self.filtered_df = self.filtered_df[self.filtered_df["ticker"] != stock_code].reset_index(drop=True)
                stock_name = self.get_stock_name(stock_code)
                logger.info(f"❌ TR 조건검색 이탈: {stock_name}({code})")
        
        # TrEventLoop에 데이터 전달
        TrEventLoop.instance().set_tr_condition_data(stock_code, condition_name, condition_index, search_type, event_type, current_cnt, total_cnt)

    def _on_receive_real_condition(self, code, event_type, condition_name, condition_index):
        """
        실시간 조건 검색 종목 편입/이탈 이벤트 수신 시 호출됩니다.
        """
        stock_name = self.get_stock_name(code)
        event_msg = "편입" if event_type == "I" else "이탈" # I: 편입, D: 이탈
        logger.info(f"📡 [조건검색 이벤트] {condition_name} ({condition_index}) - {stock_name}({code}) {event_msg}")

        # RealTimeConditionManager로 시그널 전달
        self.real_condition_signal.emit(code, event_type, condition_name, condition_index)

    def get_stock_name(self, code):
        """종목 코드로 종목명을 반환합니다."""
        return self.kiwoom.dynamicCall("GetMasterCodeName(QString)", code)

    def get_code_list_by_market(self, market_code):
        """시장별 종목 코드를 반환합니다."""
        return self.kiwoom.dynamicCall("GetCodeListByMarket(QString)", market_code).split(';')[:-1]

    def get_stock_state(self, code):
        """종목 코드로 종목 상태를 반환합니다 (예: 관리종목, 투자주의 등)."""
        return self.kiwoom.dynamicCall("GetMasterStockState(QString)", code)

    def request_daily_ohlcv(self, stock_code, end_date):
        """일봉 데이터를 요청합니다 (opt10081)."""
        rq_name = f"opt10081_req_{stock_code}"
        tr_code = "opt10081"
        screen_no = self.generate_screen_no()

        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "종목코드", stock_code)
        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "기준일자", end_date)
        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "수정주가구분", "1") # 1: 수정주가 반영

        ret = self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", rq_name, tr_code, 0, screen_no)
        if ret == 0:
            logger.debug(f"TR 요청 성공: {rq_name} (종목코드: {stock_code})")
            data = TrEventLoop.instance().get_tr_data(rq_name, tr_code, screen_no)
            return data
        else:
            error_msg = get_error_message(ret)
            logger.error(f"❌ TR 요청 실패: {rq_name} (종목코드: {stock_code}), 오류: {error_msg}")
            return {"error": error_msg}

    def get_current_price(self, stock_code):
        """실시간 데이터에서 현재가를 가져오거나, 없으면 TR 요청으로 가져옵니다."""
        if stock_code in self.real_time_data and self.real_time_data[stock_code].get('current_price'):
            return self.real_time_data[stock_code]['current_price']
        else:
            # 실시간 데이터가 없으면 TR 요청으로 현재가 조회 (opt10001)
            rq_name = f"opt10001_req_{stock_code}"
            tr_code = "opt10001"
            screen_no = self.generate_screen_no()

            self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "종목코드", stock_code)
            ret = self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)", rq_name, tr_code, 0, screen_no)
            if ret == 0:
                data = TrEventLoop.instance().get_tr_data(rq_name, tr_code, screen_no)
                if data and data.get("data"):
                    # opt10001은 single data를 반환하므로 첫 번째 항목 사용
                    price_str = data["data"].get("현재가", "0").strip().replace('+', '').replace('-', '')
                    return int(price_str) if price_str.isdigit() else 0
            logger.warning(f"[{stock_code}] 실시간/TR 현재가 정보 없음.")
            return 0

    def generate_screen_no(self):
        """고유한 화면 번호를 생성합니다."""
        self.screen_no_counter += 1
        return str(self.screen_no_counter)

    def generate_real_time_screen_no(self):
        """실시간 데이터 등록용 고유 화면 번호를 생성합니다 (2000번대)."""
        # 실시간 데이터용 화면번호는 2000번대 사용 (예시)
        # Kiwoom API는 화면당 100개 종목 제한이 있으므로, 필요시 여러 화면번호 사용 고려
        return "2000" # 간단화를 위해 고정된 화면번호 사용

    def generate_condition_screen_no(self):
        """조건 검색 등록용 고유 화면 번호를 생성합니다 (1000번대)."""
        # 조건 검색용 화면번호는 1000번대 사용 (예시)
        return "1000" # 간단화를 위해 고정된 화면번호 사용

    def SetRealReg(self, screen_no, code_list, fid_list, real_type):
        """실시간 데이터 등록."""
        ret = self.kiwoom.dynamicCall("SetRealReg(QString, QString, QString, QString)", screen_no, code_list, fid_list, real_type)
        if ret == 0:
            logger.info(f"✅ 실시간 데이터 등록 성공: 화면={screen_no}, 종목={code_list}, FID={fid_list}")
            return True
        else:
            error_msg = get_error_message(ret)
            logger.error(f"❌ 실시간 데이터 등록 실패: 화면={screen_no}, 오류: {error_msg}")
            return False

    def SetRealRemove(self, screen_no, code):
        """실시간 데이터 해제."""
        self.kiwoom.dynamicCall("SetRealRemove(QString, QString)", screen_no, code)
        logger.info(f"✅ 실시간 데이터 해제: 화면={screen_no}, 종목={code}")

    def get_condition_list_names(self):
        """서버에 저장된 조건식 목록을 요청합니다."""
        ret = self.kiwoom.dynamicCall("GetConditionLoad()")
        if ret == 1:
            logger.info("✅ 조건식 목록 요청 성공.")
        else:
            error_msg = get_error_message(ret)
            logger.error(f"❌ 조건식 목록 요청 실패: {error_msg}")

    def _on_receive_condition_load(self, ret, msg):
        """조건식 목록 수신 이벤트 (GetConditionLoad() 결과)."""
        # 이 이벤트는 GetConditionLoad() 호출 시 자동으로 발생하며,
        # GetConditionNameList()를 호출할 준비가 되었음을 알립니다.
        # 실제 조건식 목록은 GetConditionNameList()로 가져옵니다.
        pass

    def get_condition_list(self):
        """저장된 조건식 목록을 딕셔너리 형태로 반환합니다."""
        data = self.kiwoom.dynamicCall("GetConditionNameList()")
        conditions = {}
        if data:
            for item in data.split(';'):
                if item:
                    parts = item.split('^')
                    if len(parts) == 2:
                        index = int(parts[0])
                        name = parts[1]
                        conditions[name] = index
        self.condition_list = conditions
        logger.info(f"✅ 조건식 목록 로드 완료: {len(conditions)}개")
        return self.condition_list

    def SendCondition(self, screen_no, condition_name, index, search_type):
        """
        조건검색을 실행하거나 해제합니다.
        search_type: 0 (조건검색 등록), 1 (조건검색 해제)
        """
        logger.info(f"🚀 조건검색 요청: {condition_name} (Index: {index}, 타입: {'등록' if search_type == 0 else '해제'})")
        ret = self.kiwoom.dynamicCall("SendCondition(QString, QString, int, int)",
                                       screen_no, condition_name, index, search_type)
        if ret == 1:
            logger.info(f"✅ 조건검색 요청 성공: {condition_name}")
            return True
        else:
            error_msg = get_error_message(ret)
            logger.error(f"❌ 조건검색 요청 실패: {condition_name}, 오류: {error_msg}")
            return False

    def _on_receive_real_condition(self, code, event_type, condition_name, condition_index):
        """
        실시간 조건 검색 종목 편입/이탈 이벤트 수신 시 호출됩니다.
        """
        stock_name = self.get_stock_name(code)
        event_msg = "편입" if event_type == "I" else "이탈" # I: 편입, D: 이탈
        logger.info(f"📡 [조건검색 이벤트] {condition_name} ({condition_index}) - {stock_name}({code}) {event_msg}")

        # RealTimeConditionManager로 시그널 전달
        self.real_condition_signal.emit(code, event_type, condition_name, condition_index)

    def set_trade_manager_instance(self, trade_manager):
        """TradeManager 인스턴스를 설정합니다 (순환 참조 방지)."""
        self.trade_manager_instance = trade_manager
        logger.info("TradeManager instance set in KiwoomQueryHelper.")
