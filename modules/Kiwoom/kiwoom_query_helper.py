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

logger = logging.getLogger(__name__)

class KiwoomQueryHelper(QObject): # QObject 상속
    # 실시간 데이터 수신 시 외부로 시그널 전송
    real_time_signal = pyqtSignal(dict)
    # TR 데이터 수신 시 외부로 시그널 전송 (필요시)
    tr_data_signal = pyqtSignal(str, str, str, dict)
    # 실시간 조건 검색 종목 편입/이탈 시그널
    real_condition_signal = pyqtSignal(str, str, str, str) # code, event_type, condition_name, condition_index

    def __init__(self, kiwoom_ocx: QAxWidget, pyqt_app: QApplication):
        super().__init__()
        self.kiwoom = kiwoom_ocx
        self.app = pyqt_app
        self.connected = False
        self.filtered_df = pd.DataFrame()
        self.is_condition_checked = False # 조건 검색 실행 여부 플래그
        self.real_time_data = {} # 실시간 데이터를 저장할 딕셔너리
        self.condition_list = {} # 조건식 목록
        self.tr_event_loop = TrEventLoop() # TR 요청 대기용 이벤트 루프
        self._stock_name_cache = {} # 종목명 캐시
        self.current_tr_code = None # 현재 TR 요청 코드

        # Kiwoom OCX 이벤트 연결
        self.kiwoom.OnEventConnect.connect(self._on_event_connect)
        self.kiwoom.OnReceiveRealData.connect(self._on_receive_real_data)
        self.kiwoom.OnReceiveTrData.connect(self._on_receive_tr_data)
        self.kiwoom.OnReceiveRealCondition.connect(self._on_receive_real_condition) # 실시간 조건 검색 이벤트

    def connect_kiwoom(self, timeout_ms=10000):
        """키움 API에 연결을 시도하고 로그인 완료까지 대기합니다."""
        self.login_event_loop = QEventLoop()
        self.kiwoom.dynamicCall("CommConnect()")

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self.login_event_loop.quit)
        timer.start(timeout_ms)

        self.login_event_loop.exec_()
        timer.stop()

        if self.kiwoom.dynamicCall("GetConnectState()") == 1:
            logger.info("✅ 키움 API 로그인 성공")
            self.connected = True
            return True
        else:
            logger.critical("❌ 키움 API 로그인 실패")
            self.connected = False
            return False

    def _on_event_connect(self, err_code):
        """로그인 이벤트 수신 시 호출됩니다."""
        msg = get_error_message(err_code)
        logger.info(f"[로그인 이벤트] 코드: {err_code}, 메시지: {msg}")
        if hasattr(self, 'login_event_loop'):
            self.login_event_loop.quit()

    def get_login_info(self, tag: str) -> str:
        """로그인 정보를 반환합니다 (예: "ACCNO", "USER_ID")."""
        return self.kiwoom.dynamicCall("GetLoginInfo(QString)", tag).strip()

    def get_code_list_by_market(self, market: str) -> list:
        """
        시장별 종목 코드를 반환합니다.
        Args:
            market (str): 시장 구분 코드 ("0": 코스피, "10": 코스닥, "3": ELW, "4": 뮤추얼펀드, "8": ETF, "9": REITs, "12": ETN)
        Returns:
            list: 종목 코드 리스트
        """
        codes = self.kiwoom.dynamicCall("GetCodeListByMarket(QString)", market)
        return codes.split(';') if codes else []

    def get_stock_name(self, code: str) -> str:
        """
        종목 코드를 통해 종목명을 반환합니다. 캐시를 사용합니다.
        """
        if code in self._stock_name_cache:
            return self._stock_name_cache[code]
        name = self.kiwoom.dynamicCall("GetMasterCodeName(QString)", code).strip()
        if not name:
            logger.warning(f"종목명 조회 실패: {code}")
            return "Unknown"
        self._stock_name_cache[code] = name
        return name

    def get_stock_state(self, code: str) -> str:
        """
        종목 상태 정보를 반환합니다.
        예: "정상", "관리종목", "거래정지" 등
        """
        return self.kiwoom.dynamicCall("GetMasterStockState(QString)", code).strip()

    def generate_real_time_screen_no(self):
        """실시간 데이터 등록을 위한 고유 화면 번호를 생성합니다."""
        # 3000번대 화면번호 사용 (임의 지정)
        # 실제 운영에서는 더 체계적인 화면번호 관리가 필요할 수 있음
        return "3000"

    def generate_condition_screen_no(self):
        """조건 검색 실시간 등록을 위한 고유 화면 번호를 생성합니다."""
        return "5000" # 조건 검색 전용 화면번호

    def SetRealReg(self, screen_no: str, code_list: str, fid_list: str, real_type: str):
        """
        실시간 데이터 등록/해제 요청을 보냅니다.
        Args:
            screen_no (str): 화면 번호
            code_list (str): 종목 코드 목록 (세미콜론으로 구분)
            fid_list (str): FID 목록 (세미콜론으로 구분)
            real_type (str): "0" (등록), "1" (해제)
        """
        self.kiwoom.dynamicCall("SetRealReg(QString, QString, QString, QString)",
                                 screen_no, code_list, fid_list, real_type)
        logger.info(f"SetRealReg 호출: 화면번호 {screen_no}, 종목 {code_list}, FID {fid_list}, 타입 {real_type}")

    def SetRealRemove(self, screen_no: str, codes: str):
        """
        등록된 실시간 데이터를 해제합니다.
        Args:
            screen_no (str): 화면 번호 ("ALL" 가능)
            codes (str): 종목 코드 (세미콜론으로 구분, "ALL" 가능)
        """
        self.kiwoom.dynamicCall("SetRealRemove(QString, QString)", screen_no, codes)
        logger.info(f"SetRealRemove 호출: 화면번호 {screen_no}, 종목 {codes}")

    def _safe_get_real_data(self, code: str, fid: int, default=0, as_float=False):
        """빈 문자열 예외 방지를 위한 안전한 GetCommRealData 래퍼"""
        raw = self.kiwoom.dynamicCall("GetCommRealData(QString, int)", code, fid)
        if not raw.strip():
            return default
        try:
            # '+' 또는 '-' 부호가 포함될 수 있으므로 제거 후 변환
            cleaned_raw = raw.strip().replace('+', '').replace('-', '')
            return float(cleaned_raw) if as_float else abs(int(cleaned_raw))
        except ValueError:
            logger.warning(f"GetCommRealData 변환 실패: 코드={code}, FID={fid}, 값='{raw}'")
            return default

    def _on_receive_real_data(self, code: str, real_type: str, real_data: str):
        """
        실시간 시세 데이터 수신 시 호출됩니다.
        """
        # REALTIME_FID_LIST에 정의된 FID들을 사용하여 데이터 파싱
        # FID 10: 현재가, 11: 전일대비, 12: 등락률, 13: 누적거래량, 228: 체결강도, 290: 매수체결량, 291: 매도체결량
        current_price = self._safe_get_real_data(code, 10)
        total_volume = self._safe_get_real_data(code, 13)
        chegyul_gangdo = self._safe_get_real_data(code, 228, as_float=True)
        total_buy_cvol = self._safe_get_real_data(code, 290)
        total_sell_cvol = self._safe_get_real_data(code, 291)
        
        # 등락률 (FID 12) 추가
        change_pct = self._safe_get_real_data(code, 12, as_float=True)

        if code not in self.real_time_data:
            self.real_time_data[code] = {}

        self.real_time_data[code].update({
            'current_price': current_price,
            'total_volume': total_volume,
            'chegyul_gangdo': chegyul_gangdo,
            'total_buy_cvol': total_buy_cvol,
            'total_sell_cvol': total_sell_cvol,
            'change_pct': change_pct, # 등락률 추가
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        # 외부로 실시간 데이터 시그널 전송
        self.real_time_signal.emit({
            'code': code,
            'current_price': current_price,
            'chegyul_gangdo': chegyul_gangdo,
            'total_buy_cvol': total_buy_cvol,
            'total_sell_cvol': total_sell_cvol,
            'change_pct': change_pct
        })
        # logger.debug(f"실시간 데이터 수신: {code}, 현재가: {current_price}, 체결강도: {chegyul_gangdo}")


    def _on_receive_tr_data(self, screen_no, rq_name, tr_code, record_name, prev_next, data_len, error_code, message, splm_msg):
        """
        TR 요청 결과 수신 시 호출됩니다.
        """
        logger.info(f"TR 데이터 수신: {rq_name}, {tr_code}, prev_next: {prev_next}")
        data = {}
        try:
            if rq_name == "opt10081_req": # 일봉 데이터 요청
                cnt = self.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name)
                rows = []
                for i in range(cnt):
                    row = {
                        "날짜": self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "일자").strip(),
                        "현재가": abs(int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "현재가").strip())),
                        "거래량": abs(int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "거래량").strip())),
                        "시가": abs(int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "시가").strip())),
                        "고가": abs(int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "고가").strip())),
                        "저가": abs(int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "저가").strip())),
                    }
                    rows.append(row)
                data = {"data": rows, "prev_next": prev_next}
            elif rq_name == "opw00001_req": # 예수금 요청
                data["예수금"] = int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, 0, "예수금").strip())
                data["출금가능금액"] = int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, 0, "출금가능금액").strip())
                data["주문가능금액"] = int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, 0, "주문가능금액").strip())
            elif rq_name == "opw00018_req": # 계좌평가잔고내역 요청
                account_balance = {}
                account_balance["총평가금액"] = int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, 0, "총평가금액").strip())
                account_balance["총손익금액"] = int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, 0, "총손익금액").strip())
                account_balance["총수익률"] = float(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, 0, "총수익률").strip())

                cnt = self.kiwoom.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name)
                positions = []
                for i in range(cnt):
                    item = {
                        "종목코드": self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "종목번호").strip().replace('A', ''),
                        "종목명": self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "종목명").strip(),
                        "보유수량": int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "보유수량").strip()),
                        "매입가": int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "매입가").strip()),
                        "현재가": int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "현재가").strip()),
                        "평가손익": int(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "평가손익").strip()),
                        "수익률": float(self.kiwoom.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, i, "수익률").strip()),
                    }
                    positions.append(item)
                data["account_balance"] = account_balance
                data["positions"] = positions
            else:
                logger.warning(f"처리되지 않은 TR 요청: {rq_name}")

        except Exception as e:
            logger.error(f"TR 데이터 처리 중 오류 발생 ({rq_name}, {tr_code}): {e}", exc_info=True)
            data["error"] = str(e)

        self.tr_event_loop.set_data(data)
        self.tr_data_signal.emit(screen_no, rq_name, tr_code, data) # TR 데이터 시그널 전송

    def request_daily_ohlcv(self, stock_code: str, end_date: str, prev_next: str = "0") -> dict:
        """
        주어진 종목의 일봉 데이터를 요청합니다 (TR: opt10081).
        Args:
            stock_code (str): 종목 코드
            end_date (str): 조회 종료일 (YYYYMMDD)
            prev_next (str): "0": 처음 조회, "2": 다음 페이지 조회
        Returns:
            dict: 일봉 데이터 (DataFrame 형태) 및 prev_next 정보
        """
        self.current_tr_code = "opt10081"
        self.tr_event_loop.reset() # TR 요청 전에 루프 초기화

        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "종목코드", stock_code)
        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "기준일자", end_date)
        self.kiwoom.dynamicCall("SetInputValue(QString, QString)", "수정주가구분", "1") # 1: 수정주가 반영

        screen_no = "1000" # TR 요청용 화면번호 (임의 지정)
        ret = self.kiwoom.dynamicCall("CommRqData(QString, QString, int, QString)",
                                       "opt10081_req", "opt10081", int(prev_next), screen_no)

        if ret == 0:
            logger.info(f"일봉 데이터 요청 성공: {stock_code}, 기준일: {end_date}")
            if self.tr_event_loop.wait(timeout_ms=10000): # 응답 대기
                return self.tr_event_loop.get_data()
            else:
                logger.warning(f"일봉 데이터 요청 타임아웃: {stock_code}")
                return {"error": "Timeout"}
        else:
            error_msg = get_error_message(ret)
            logger.error(f"일봉 데이터 요청 실패: {stock_code}, 오류: {error_msg}")
            return {"error": error_msg}

    def get_condition_list(self) -> dict:
        """
        키움 증권에 저장된 조건식 목록을 가져옵니다.
        """
        raw_str = self.kiwoom.dynamicCall("GetConditionNameList()")
        condition_map = {}
        for cond in raw_str.split(';'):
            if not cond.strip():
                continue
            index, name = cond.split('^')
            condition_map[name.strip()] = int(index.strip())
        self.condition_list = condition_map
        logger.info(f"📑 조건검색식 목록 로드: {list(condition_map.keys())}")
        return condition_map

    def SendCondition(self, screen_no: str, condition_name: str, index: int, search_type: int):
        """
        조건 검색을 실행하거나 해제합니다.
        Args:
            screen_no (str): 화면 번호
            condition_name (str): 조건식 이름
            index (int): 조건식 인덱스
            search_type (int): 0: 실시간 등록, 1: 실시간 해제
        """
        logger.info(f"🧠 조건검색 실행/해제: {condition_name} (Index: {index}, 타입: {'등록' if search_type == 0 else '해제'})")
        ret = self.kiwoom.dynamicCall("SendCondition(QString, QString, int, int)",
                                       screen_no, condition_name, index, search_type)
        if ret == 1:
            logger.info(f"✅ 조건검색 요청 성공: {condition_name}")
            return True
        else:
            error_msg = get_error_message(ret)
            logger.error(f"❌ 조건검색 요청 실패: {condition_name}, 오류: {error_msg}")
            return False

    def SendConditionStop(self, screen_no: str, condition_name: str, index: int):
        """
        실시간 조건 검색을 중지합니다.
        """
        logger.info(f"🛑 실시간 조건검색 중지 요청: {condition_name} (Index: {index})")
        self.kiwoom.dynamicCall("SendConditionStop(QString, QString, int)",
                                 screen_no, condition_name, index)
        logger.info(f"✅ 실시간 조건검색 중지 요청 완료: {condition_name}")


    def _on_receive_real_condition(self, code, event_type, condition_name, condition_index):
        """
        실시간 조건 검색 종목 편입/이탈 이벤트 수신 시 호출됩니다.
        """
        stock_name = self.get_stock_name(code)
        event_msg = "편입" if event_type == "I" else "이탈" # I: 편입, D: 이탈
        logger.info(f"📡 [조건검색 이벤트] {condition_name} ({condition_index}) - {stock_name}({code}) {event_msg}")

        # 외부로 실시간 조건 변경 시그널 전송
        self.real_condition_signal.emit(code, event_type, condition_name, str(condition_index))

    def get_current_price(self, stock_code: str) -> int:
        """
        실시간 데이터에서 현재가를 가져옵니다.
        """
        return self.real_time_data.get(stock_code, {}).get('current_price', 0)

