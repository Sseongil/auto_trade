# modules/Kiwoom/real_time_condition_manager.py

import logging
from PyQt5.QtCore import pyqtSignal, QObject # pyqtSignal, QObject 임포트 추가

logger = logging.getLogger(__name__)

class RealTimeConditionManager:
    def __init__(self, kiwoom_helper):
        self.kiwoom_helper = kiwoom_helper
        self.active_conditions = {} # {screen_no: {"name": condition_name, "index": condition_index}}
        self.condition_stocks = {} # {condition_name: {stock_code: stock_name}}
        self._set_event_handlers()
        logger.info("RealTimeConditionManager initialized.")

    def _set_event_handlers(self):
        # 수정된 부분: self.kiwoom_helper.real_condition_signal -> self.kiwoom_helper.ocx.OnReceiveRealCondition
        self.kiwoom_helper.ocx.OnReceiveRealCondition.connect(self._on_receive_real_condition)
        logger.info("RealTimeConditionManager event handlers set.")

    def _on_receive_real_condition(self, stock_code, condition_name, condition_index, invest_gubun):
        """
        실시간 조건검색 편입/이탈 종목을 수신하는 이벤트
        :param stock_code: 종목코드
        :param condition_name: 조건식 이름
        :param condition_index: 조건식 인덱스 (실제 사용 시에는 문자열로 변환하여 사용)
        :param invest_gubun: 편입('I') / 이탈('D')
        """
        logger.info(f"[OnReceiveRealCondition] 종목코드: {stock_code}, 조건식: {condition_name}, 인덱스: {condition_index}, 구분: {invest_gubun}")

        if invest_gubun == "I": # 편입
            if condition_name not in self.condition_stocks:
                self.condition_stocks[condition_name] = {}
            # 종목명 조회 (필요시)
            stock_name = self.kiwoom_helper.get_master_code_name(stock_code)
            self.condition_stocks[condition_name][stock_code] = stock_name
            logger.info(f"✅ 종목 편입: [{condition_name}] {stock_name}({stock_code})")
            # TODO: 여기에 편입된 종목에 대한 매수 전략 실행 로직 추가
            # 예: self.kiwoom_helper.send_telegram_message(f"[{condition_name}] {stock_name}({stock_code}) 편입!")
        elif invest_gubun == "D": # 이탈
            if condition_name in self.condition_stocks and stock_code in self.condition_stocks[condition_name]:
                stock_name = self.condition_stocks[condition_name].pop(stock_code)
                logger.info(f"❌ 종목 이탈: [{condition_name}] {stock_name}({stock_code})")
                # TODO: 여기에 이탈된 종목에 대한 매도 전략 실행 로직 추가 (선택 사항)

    def start_real_condition_search(self, screen_no, condition_name, condition_index):
        """
        실시간 조건검색을 시작합니다.
        :param screen_no: 화면번호
        :param condition_name: 조건식 이름
        :param condition_index: 조건식 인덱스
        """
        # SendCondition의 search_type은 0(등록)
        success = self.kiwoom_helper.SendCondition(screen_no, condition_name, condition_index, 0)
        if success:
            self.active_conditions[screen_no] = {
                "name": condition_name,
                "index": condition_index
            }
            logger.info(f"✅ 실시간 조건검색 시작 요청 성공: 화면번호={screen_no}, 조건식='{condition_name}'")
        else:
            logger.error(f"❌ 실시간 조건검색 시작 요청 실패: 화면번호={screen_no}, 조건식='{condition_name}'")
        return success

    def stop_real_condition_search(self, screen_no, condition_name, condition_index):
        """
        실시간 조건검색을 중지합니다.
        :param screen_no: 화면번호
        :param condition_name: 조건식 이름
        :param condition_index: 조건식 인덱스
        """
        # SendCondition의 search_type은 1(해제)
        success = self.kiwoom_helper.SendCondition(screen_no, condition_name, condition_index, 1)
        if success:
            if screen_no in self.active_conditions:
                del self.active_conditions[screen_no]
            logger.info(f"✅ 실시간 조건검색 중지 요청 성공: 화면번호={screen_no}, 조건식='{condition_name}'")
        else:
            logger.error(f"❌ 실시간 조건검색 중지 요청 실패: 화면번호={screen_no}, 조건식='{condition_name}'")
        return success

    def get_active_condition_stocks(self, condition_name):
        """
        특정 조건식에 현재 편입되어 있는 종목 목록을 반환합니다.
        :param condition_name: 조건식 이름
        :return: {stock_code: stock_name} 딕셔너리
        """
        return self.condition_stocks.get(condition_name, {})

    def get_all_active_condition_stocks(self):
        """
        모든 활성 조건식에 편입되어 있는 종목 목록을 반환합니다.
        :return: {condition_name: {stock_code: stock_name}} 딕셔너리
        """
        return self.condition_stocks.copy()

