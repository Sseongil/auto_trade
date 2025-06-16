# C:\Users\user\stock_auto\modules\Kiwoom\monitor_positions.py

import json
import os
import time
import logging
from datetime import datetime

# ✅ 임포트 경로 수정됨: common 폴더 안의 config와 utils
from modules.common.config import POSITIONS_FILE_PATH, STOP_LOSS_PCT, TAKE_PROFIT_PCT, TRAIL_STOP_PCT, MAX_HOLD_DAYS, DEFAULT_LOT_SIZE
from modules.common.utils import get_current_time_str

# 필요한 경우, notify와 trade_logger 모듈을 modules 폴더에 추가해야 합니다.
# 없으면 이 줄들을 주석 처리하거나 빈 더미 함수로 대체해야 합니다.
try:
    from modules.notify import send_telegram_message # 기존: from ..notify
except ImportError:
    logging.warning("modules/notify.py not found. Telegram notifications will be disabled.")
    def send_telegram_message(message):
        logging.info(f"Telegram (simulated): {message}")

try:
    from modules.trade_logger import log_trade # 기존: from ..trade_logger
except ImportError:
    logging.warning("modules/trade_logger.py not found. Trade logging will be disabled.")
    def log_trade(code, name, price, quantity, trade_type, pnl=None):
        logging.info(f"Trade Log (simulated): {trade_type} - {name}({code}), Qty: {quantity}, Price: {price}, PnL: {pnl}")

logger = logging.getLogger(__name__)


# Kiwoom 응답 코드에 대한 간단한 설명 맵
KIWOOM_ERROR_CODES = {
    0: "정상 처리",
    -10: "미접속",
    -100: "계좌정보 없음",
    -101: "계좌 비밀번호 없음",
    -102: "비정상적인 모듈 호출",
    -103: "종목코드 없음",
    -104: "계좌증거금율 오류",
    -105: "조건 검색 오류",
    -106: "조건 검색 미신청",
    -107: "사용자 정보 없음",
    -108: "주문 가격 오류",
    -109: "주문 수량 오류",
    -110: "실시간 등록 오류",
    -111: "실시간 해제 오류",
    -112: "데이터 없음",
    -113: "API 미설정",
    -114: "알 수 없는 오류",
}


class MonitorPositions:
    def __init__(self, kiwoom_helper, kiwoom_tr_request, trade_manager, account_number):
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.trade_manager = trade_manager # TradeManager 인스턴스 추가
        self.account_number = account_number
        self.positions = self.load_positions() # JSON 파일에서 로드
        logger.info(f"{get_current_time_str()}: MonitorPositions initialized for account {self.account_number}. Loaded {len(self.positions)} positions.")

    def load_positions(self):
        if os.path.exists(POSITIONS_FILE_PATH):
            with open(POSITIONS_FILE_PATH, 'r', encoding='utf-8') as f:
                try:
                    positions = json.load(f)
                    logger.info(f"{get_current_time_str()}: Positions loaded from {POSITIONS_FILE_PATH}.")
                    return positions
                except json.JSONDecodeError:
                    logger.warning(f"{get_current_time_str()}: Error decoding JSON from {POSITIONS_FILE_PATH}. Starting with empty positions.")
                    return {}
        logger.info(f"{get_current_time_str()}: {POSITIONS_FILE_PATH} not found. Starting with empty positions.")
        return {}

    def save_positions(self):
        with open(POSITIONS_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.positions, f, indent=4, ensure_ascii=False)
        logger.info(f"{get_current_time_str()}: Positions saved to {POSITIONS_FILE_PATH}.")

    def update_position(self, stock_code, quantity, purchase_price=0):
        """
        로컬 positions.json 파일을 업데이트합니다.
        trade_manager에서 매수/매도 주문 후 호출됩니다.
        """
        stock_code = stock_code.strip() # 공백 제거

        if stock_code not in self.positions:
            self.positions[stock_code] = {
                "quantity": 0,
                "purchase_price": 0.0,
                "total_purchase_amount": 0.0,
                "buy_date": datetime.today().strftime("%Y-%m-%d"),
                "half_exited": False,
                "trail_high": 0.0, # 초기값은 매수 시 설정
                "last_update": get_current_time_str()
            }

        current_qty = self.positions[stock_code]["quantity"]
        current_total_purchase = self.positions[stock_code]["total_purchase_amount"]
        current_buy_price = self.positions[stock_code]["purchase_price"]

        if quantity > 0: # 매수
            # 신규 매수 또는 추가 매수 시
            new_total_purchase_amount = current_total_purchase + (quantity * purchase_price)
            new_quantity = current_qty + quantity
            
            if new_quantity > 0:
                new_purchase_price = new_total_purchase_amount / new_quantity
            else: # 수량이 0이 되면 매입가도 0
                new_purchase_price = 0.0

            self.positions[stock_code]["quantity"] = new_quantity
            self.positions[stock_code]["total_purchase_amount"] = new_total_purchase_amount
            self.positions[stock_code]["purchase_price"] = new_purchase_price
            
            # trail_high 초기값 설정 (최초 매수 또는 추가 매수 시 현재가 반영)
            if self.positions[stock_code]["trail_high"] == 0.0 or self.positions[stock_code]["trail_high"] < purchase_price:
                self.positions[stock_code]["trail_high"] = purchase_price

            logger.info(f"{get_current_time_str()}: Updated position for {stock_code}: Buy {quantity} @ {purchase_price}. New Avg Price: {new_purchase_price:.2f}, Total Qty: {new_quantity}")

        elif quantity < 0: # 매도
            sell_qty = abs(quantity)
            if current_qty >= sell_qty:
                new_quantity = current_qty - sell_qty
                
                # 매도 시에는 매입 금액을 비율로 감소시킵니다.
                if current_qty > 0:
                    self.positions[stock_code]["total_purchase_amount"] -= (current_total_purchase / current_qty) * sell_qty
                
                self.positions[stock_code]["quantity"] = new_quantity
                
                if new_quantity == 0: # 수량이 0이 되면 모든 값 초기화
                    self.positions[stock_code]["total_purchase_amount"] = 0.0
                    self.positions[stock_code]["purchase_price"] = 0.0
                    self.positions[stock_code]["trail_high"] = 0.0
                    # 모든 수량 매도 시 half_exited 초기화
                    self.positions[stock_code]["half_exited"] = False 
                elif self.positions[stock_code]["total_purchase_amount"] < 0: # 음수가 되지 않도록 방지
                     self.positions[stock_code]["total_purchase_amount"] = 0.0
                
                # 매도 시 half_exited 플래그 업데이트
                # 만약 전체 수량의 절반 이상이 매도되었다면 half_exited를 True로 설정
                # 이 로직은 50% 익절 로직과 연동되어야 함
                # 여기서는 quantity < 0 일 때이므로, trade_manager에서 실제 50% 익절이 발생했을 때
                # 명시적으로 `half_exited`를 True로 설정하는 것이 더 정확합니다.
                # 이 `update_position` 함수는 단순히 수량 변화를 반영합니다.

                logger.info(f"{get_current_time_str()}: Updated position for {stock_code}: Sell {sell_qty}. New Qty: {new_quantity}")
            else:
                logger.warning(f"{get_current_time_str()}: Warning: Attempted to sell {sell_qty} of {stock_code}, but only {current_qty} available.")
                return False
        
        self.positions[stock_code]["last_update"] = get_current_time_str()
        self.save_positions()
        return True


    def get_position(self, stock_code):
        return self.positions.get(stock_code, {"quantity": 0, "purchase_price": 0.0, "total_purchase_amount": 0.0, "buy_date": "", "half_exited": False, "trail_high": 0.0})

    def get_all_positions(self):
        return self.positions

    def get_current_positions_from_kiwoom(self):
        """
        실제 키움 API에서 현재 계좌의 모든 보유 종목 정보를 조회하여 반환하고, 로컬 파일과 동기화합니다.
        """
        logger.info(f"{get_current_time_str()}: Requesting current positions from Kiwoom API for account: {self.account_number}")
        
        # opw00018 (계좌평가현황요청) TR을 사용하여 현재 보유 종목 리스트를 가져옵니다.
        # 이 TR은 계좌 전체의 평가 정보를 가져오고, 예수금, 종목별 평가손익 등을 포함합니다.
        # KiwoomTrRequest 인스턴스를 통해 TR 요청을 보냅니다.
        account_info_data = self.kiwoom_tr_request.request_account_info(self.account_number, sPrevNext="0", screen_no="0001")

        current_holdings = {}
        if account_info_data and isinstance(account_info_data, dict):
            # 계좌평가현황요청 (opw00018) TR 응답 데이터는 리스트 형태로 올 수 있습니다.
            # GetCommData로 반복해서 가져와야 합니다.
            # 이전에 kiwoom_tr_request._handler_trdata에서 parsed_data에 계좌요약 정보만 넣었는데,
            # 종목별 상세 정보를 가져오려면 _handler_trdata에서 반복 데이터를 처리하거나,
            # 여기에서 직접 kiwoom_helper.get_comm_data를 호출해야 합니다.
            
            # kiwoom_query_helper에 CommRqData 후 GetRepeatCnt 및 GetCommData 호출
            # TradeManager의 get_account_info에서 이미 TR 데이터를 받아오므로, 그 데이터를 활용합니다.
            
            trcode = "opw00018"
            repeat_cnt = self.kiwoom_helper.get_repeat_cnt(trcode, "계좌평가현황")
            logger.debug(f"opw00018 repeat count: {repeat_cnt}")
            
            for i in range(repeat_cnt):
                item_name = self.kiwoom_helper.get_comm_data(trcode, "계좌평가현황", i, "종목명").strip()
                stock_code = self.kiwoom_helper.get_comm_data(trcode, "계좌평가현황", i, "종목번호").strip()
                current_qty = int(self.kiwoom_helper.get_comm_data(trcode, "계좌평가현황", i, "보유수량").strip())
                purchase_price = int(self.kiwoom_helper.get_comm_data(trcode, "계좌평가현황", i, "매입단가").strip())
                current_price = int(self.kiwoom_helper.get_comm_data(trcode, "계좌평가현황", i, "현재가").strip())
                total_purchase_amount = int(self.kiwoom_helper.get_comm_data(trcode, "계좌평가현황", i, "매입금액").strip())
                
                # 종목코드에서 'A' 제거 (있다면)
                if stock_code.startswith('A'):
                    stock_code = stock_code[1:]

                if current_qty > 0:
                    current_holdings[stock_code] = {
                        "item_name": item_name,
                        "quantity": current_qty,
                        "purchase_price": purchase_price,
                        "current_price": current_price,
                        "total_purchase_amount": total_purchase_amount,
                        "estimated_profit_loss": (current_price - purchase_price) * current_qty,
                        "buy_date": datetime.today().strftime("%Y-%m-%d"), # Kiwoom TR은 매수일자를 직접 제공하지 않을 수 있어 임시로 오늘 날짜
                        "half_exited": False, # Kiwoom TR에서는 이 정보를 알 수 없음 (로컬 파일에서 관리)
                        "trail_high": current_price # 초기 추적 고점
                    }
            logger.info(f"INFO: Successfully fetched {len(current_holdings)} holdings from Kiwoom API.")
            
            # 로컬 positions.json 파일 동기화
            self.sync_local_positions(current_holdings)
            
            return current_holdings
        else:
            logger.error(f"ERROR: Failed to retrieve current positions from Kiwoom API for account {self.account_number}.")
            return {}

    def sync_local_positions(self, kiwoom_holdings: dict):
        """
        키움 API에서 가져온 보유 종목과 로컬 positions.json을 동기화합니다.
        키움에는 있는데 로컬에 없는 종목은 추가하고, 로컬에는 있는데 키움에 없는 (전량 매도된) 종목은 삭제합니다.
        로컬에 있는 종목은 수량과 매입단가를 키움 데이터로 업데이트합니다.
        """
        updated_local_positions = {}
        
        # 키움에서 가져온 데이터를 우선으로 반영
        for stock_code, kiwoom_data in kiwoom_holdings.items():
            if stock_code in self.positions:
                # 로컬에 이미 있는 경우, 수량 및 매입가 등을 키움 데이터로 업데이트
                # 단, buy_date, half_exited, trail_high는 로컬 정보를 유지 (키움 TR에 없음)
                local_data = self.positions[stock_code]
                local_data["quantity"] = kiwoom_data["quantity"]
                local_data["purchase_price"] = kiwoom_data["purchase_price"]
                local_data["total_purchase_amount"] = kiwoom_data["total_purchase_amount"]
                # trail_high는 현재가로 업데이트하거나, 기존 trail_high보다 높으면 업데이트
                if kiwoom_data["current_price"] > local_data["trail_high"]:
                    local_data["trail_high"] = kiwoom_data["current_price"]
                local_data["last_update"] = get_current_time_str()
                updated_local_positions[stock_code] = local_data
                logger.debug(f"Sync: Updated local position for {stock_code} from Kiwoom.")
            else:
                # 로컬에 없는 신규 종목은 추가
                new_position = {
                    "quantity": kiwoom_data["quantity"],
                    "purchase_price": kiwoom_data["purchase_price"],
                    "total_purchase_amount": kiwoom_data["total_purchase_amount"],
                    "buy_date": datetime.today().strftime("%Y-%m-%d"), # 임시 매수일자
                    "half_exited": False,
                    "trail_high": kiwoom_data["current_price"],
                    "last_update": get_current_time_str()
                }
                updated_local_positions[stock_code] = new_position
                logger.info(f"Sync: Added new position {stock_code} from Kiwoom to local.")

        # 로컬에는 있는데 키움에 없는 종목 (전량 매도된 경우) 삭제
        removed_count = 0
        keys_to_remove = []
        for stock_code in self.positions.keys():
            if stock_code not in kiwoom_holdings and self.positions[stock_code]["quantity"] > 0:
                # 키움에 없는데 로컬에 수량이 남아있으면 (오류 가능성) 경고
                logger.warning(f"Sync: Local position for {stock_code} (Qty: {self.positions[stock_code]['quantity']}) exists but not found in Kiwoom holdings. Removing from local.")
                keys_to_remove.append(stock_code)
                removed_count += 1
            elif stock_code not in kiwoom_holdings and self.positions[stock_code]["quantity"] == 0:
                 # 키움에 없고 로컬에 수량도 0이면 삭제
                keys_to_remove.append(stock_code)
                removed_count += 1
                logger.info(f"Sync: Removed zero-quantity local position for {stock_code}.")

        for key in keys_to_remove:
            if key in self.positions:
                del self.positions[key]

        self.positions = updated_local_positions
        self.save_positions()
        logger.info(f"Sync: Local positions synchronized with Kiwoom. {removed_count} positions removed, {len(updated_local_positions)} remaining.")

    def monitor_positions_strategy(self):
        """
        보유 중인 주식 포지션을 모니터링하고, 설정된 전략(손절, 익절, 트레일링 스탑, 최대 보유일)에 따라
        매도 주문을 실행합니다.
        """
        logger.info("🚀 포지션 모니터링 시작 (전략 기반)")

        # 키움 API 연결은 local_api_server에서 이미 되어있다고 가정
        if not self.kiwoom_helper.connected_state == 0: # 0: 연결 성공
             logger.critical("❌ 키움증권 API 연결 안됨. 모니터링을 중단합니다.")
             send_telegram_message("🚨 키움 API 연결 실패. 포지션 모니터링 중단.")
             return

        # 최신 보유 현황을 키움 API에서 가져와서 로컬 데이터와 동기화
        self.get_current_positions_from_kiwoom()
        df_positions_dict = self.positions # JSON 파일에서 로드된 딕셔너리 사용

        if not df_positions_dict:
            logger.info("📂 모니터링할 포지션이 없습니다 (키움 API 조회 결과).")
            return

        # 딕셔너리를 리스트로 변환하여 순회 (수정 용이성을 위해)
        positions_to_monitor = list(df_positions_dict.values())
        
        # for loop에서 수정 시 원본 딕셔너리를 수정하는 것은 위험하므로,
        # 각 종목을 딕셔너리로 만들어서 처리하고, 마지막에 다시 self.positions에 할당

        for stock_code, pos_data in df_positions_dict.items():
            # 각 포지션의 정보 추출 및 초기화
            code = stock_code
            name = pos_data.get("item_name", "Unknown") # Kiwoom API에서 가져온 이름
            buy_price = float(pos_data["purchase_price"])
            quantity = int(pos_data["quantity"])
            trail_high = float(pos_data["trail_high"])
            half_exited = bool(pos_data["half_exited"])
            
            # 매수일자 처리 및 보유일 계산
            try:
                # buy_date가 JSON 파일에 string으로 저장되어 있으므로 파싱
                buy_date_str = pos_data.get("buy_date", datetime.today().strftime("%Y-%m-%d"))
                buy_date = datetime.strptime(buy_date_str, "%Y-%m-%d")
                hold_days = (datetime.today() - buy_date).days
            except ValueError as e:
                logger.warning(f"❌ 날짜 형식 오류: {name}({code}) - buy_date: '{buy_date_str}' - {e}. 해당 포지션은 건너뛰고 다음 주기에 다시 확인합니다.")
                continue # 다음 포지션으로 넘어감

            # 수량이 0이거나 유효하지 않은 경우 로그 기록 후 건너뛰기 (이미 sync_local_positions에서 제거되었을 것)
            if quantity <= 0:
                logger.info(f"정보: {name}({code}) - 수량 0. (이미 처리되었거나 오류).")
                continue # 다음 포지션으로 넘어감

            # 현재가 조회 (kiwoom_tr_request를 통해)
            current_price = self.kiwoom_tr_request.request_current_price(code)
            if current_price is None or current_price == 0:
                logger.warning(f"경고: {name}({code}) 현재가 조회 실패. 이 종목은 다음 모니터링 주기에 다시 확인합니다.")
                continue # 다음 포지션으로 넘어감

            # 수익률 계산 (매수가 0인 경우 ZeroDivisionError 방지)
            pnl_pct = (current_price - buy_price) / buy_price * 100 if buy_price != 0 else 0

            logger.info(f"🔍 {name}({code}) | 현재가: {current_price:,}원, 수익률: {pnl_pct:.2f}%, 보유일: {hold_days}일, 추적고점: {trail_high:,}원")

            action_taken = False # 이번 반복에서 매도 액션이 발생했는지 추적

            # 1. 손절 조건 검사 (최우선 순위)
            if pnl_pct <= STOP_LOSS_PCT:
                logger.warning(f"❌ 손절 조건 충족: {name}({code}) 수익률 {pnl_pct:.2f}% (기준: {STOP_LOSS_PCT:.2f}%)")
                order_quantity = quantity # 전체 물량 매도
                if order_quantity > 0:
                    result = self.trade_manager.place_order(code, 2, order_quantity, 0, "03") # 시장가 매도
                    if result["status"] == "success":
                        send_telegram_message(f"❌ 손절: {name}({code}) | 수익률: {pnl_pct:.2f}% | 수량: {order_quantity}주")
                        log_trade(code, name, current_price, order_quantity, "STOP_LOSS", pnl_pct)
                        action_taken = True
                    else:
                        logger.error(f"🔴 손절 주문 실패: {name}({code}) {result.get('message', '알 수 없는 오류')}")
                else:
                    logger.warning(f"경고: {name}({code}) 손절 매도 수량 0주. (총 수량: {quantity}주)")
            
            # 매도 액션이 발생하지 않았을 경우에만 다음 조건들을 검사
            if not action_taken:
                # 2. 50% 익절 조건 검사
                if not half_exited and pnl_pct >= TAKE_PROFIT_PCT:
                    logger.info(f"🎯 50% 익절 조건 충족: {name}({code}) 수익률 {pnl_pct:.2f}% (기준: {TAKE_PROFIT_PCT:.2f}%)")
                    half_qty = (quantity // 2 // DEFAULT_LOT_SIZE) * DEFAULT_LOT_SIZE
                    
                    if half_qty > 0:
                        result = self.trade_manager.place_order(code, 2, half_qty, 0, "03") # 시장가 매도
                        if result["status"] == "success":
                            send_telegram_message(f"🎯 50% 익절: {name}({code}) | 수익률: {pnl_pct:.2f}% | 수량: {half_qty}주")
                            log_trade(code, name, current_price, half_qty, "TAKE_PROFIT_50", pnl_pct)
                            
                            # 포지션 데이터 업데이트: 남은 수량, half_exited 플래그, 추적 고점
                            # self.update_position이 내부적으로 수량 감소 및 저장 처리
                            # 하지만 half_exited와 trail_high는 명시적으로 설정해야 함
                            self.positions[code]["half_exited"] = True
                            self.positions[code]["trail_high"] = current_price # 50% 익절 후 추적 고점 업데이트
                            self.save_positions() # 수동 저장
                            
                            logger.info(f"업데이트: {name}({code}) 남은 수량: {self.positions[code]['quantity']}주, 추적고점: {self.positions[code]['trail_high']:,}원")
                            action_taken = True
                        else:
                            logger.error(f"🔴 50% 익절 주문 실패: {name}({code}) {result.get('message', '알 수 없는 오류')}")
                    else:
                        logger.warning(f"경고: {name}({code}) 50% 익절을 위한 최소 수량({DEFAULT_LOT_SIZE}주) 부족. 현재 수량: {quantity}주.")
                
            # 매도 액션이 발생하지 않았고, 이미 50% 익절이 된 상태에서 다음 조건 검사
            if not action_taken and half_exited:
                # 3. 트레일링 스탑 조건 검사
                if current_price > trail_high:
                    # 현재가가 추적 고점보다 높으면 고점 업데이트
                    self.positions[code]["trail_high"] = current_price
                    self.save_positions() # 업데이트된 트레일링 하이 저장
                    logger.debug(f"추적고점 업데이트: {name}({code}) -> {self.positions[code]['trail_high']:,}원")
                elif current_price <= trail_high * (1 - TRAIL_STOP_PCT / 100):
                    logger.warning(f"📉 트레일링 스탑 조건 충족: {name}({code}) 현재가 {current_price}원, 추적고점 {trail_high}원 (하락률: {((trail_high - current_price)/trail_high*100):.2f}%)")
                    order_quantity = quantity # 남은 전체 물량 매도
                    if order_quantity > 0:
                        pnl_on_exit = (current_price - buy_price) / buy_price * 100 # 청산 시점 수익률
                        result = self.trade_manager.place_order(code, 2, order_quantity, 0, "03") # 시장가 매도
                        if result["status"] == "success":
                            send_telegram_message(f"📉 트레일링 스탑: {name}({code}) | 수익률: {pnl_on_exit:.2f}% | 수량: {order_quantity}주")
                            log_trade(code, name, current_price, order_quantity, "TRAILING_STOP", pnl_on_exit)
                            action_taken = True
                        else:
                            logger.error(f"🔴 트레일링 스탑 주문 실패: {name}({code}) {result.get('message', '알 수 없는 오류')}")
                    else:
                        logger.warning(f"경고: {name}({code}) 트레일링 스탑 매도 수량 0주. (총 수량: {quantity}주)")

            # 매도 액션이 발생하지 않았을 경우에만 다음 조건 검사
            if not action_taken:
                # 4. 최대 보유일 초과 조건 검사 (가장 낮은 순위)
                if hold_days >= MAX_HOLD_DAYS:
                    logger.info(f"⌛ 보유일 초과 조건 충족: {name}({code}) 보유일 {hold_days}일 (기준: {MAX_HOLD_DAYS}일)")
                    order_quantity = quantity # 남은 전체 물량 매도
                    if order_quantity > 0:
                        pnl_on_exit = (current_price - buy_price) / buy_price * 100 # 청산 시점 수익률
                        result = self.trade_manager.place_order(code, 2, order_quantity, 0, "03") # 시장가 매도
                        if result["status"] == "success":
                            send_telegram_message(f"⌛ 보유일 초과 청산: {name}({code}) | 수익률: {pnl_on_exit:.2f}% | 수량: {order_quantity}주")
                            log_trade(code, name, current_price, order_quantity, "MAX_HOLD_DAYS_SELL", pnl_on_exit)
                            action_taken = True
                        else:
                            logger.error(f"🔴 보유일 초과 청산 주문 실패: {name}({code}) {result.get('message', '알 수 없는 오류')}")
                    else:
                        logger.warning(f"경고: {name}({code}) 보유일 초과 매도 수량 0주. (총 수량: {quantity}주)")
            
            # 처리 후 변경된 포지션 정보를 self.positions에 다시 할당
            # (update_position 또는 위에서 직접 self.positions[code]를 수정했으므로 별도 처리 불필요)

        logger.info("--- 포지션 모니터링 종료 ---")

# 이 모듈은 클래스로 변경되었으므로, 단독 실행 시 키움 객체를 생성하고 모니터링 로직을 호출해야 합니다.
if __name__ == "__main__":
    # 이 모듈만 단독으로 테스트할 경우를 위한 임시 로깅 설정
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # TODO: 키움 헬퍼, TR 요청, 트레이드 매니저 객체를 여기서 생성하고 모니터포지션에 전달해야 합니다.
    # 이는 복잡하므로, 일반적으로 local_api_server.py와 같은 메인 진입점에서 호출됩니다.
    # 단독 테스트를 위한 최소한의 로직을 작성합니다.
    
    # 임시 Mock 객체 (실제 Kiwoom 연동 없이 테스트)
    class MockKiwoomHelper:
        def __init__(self):
            self.connected_state = 0 # 연결된 상태로 가정
        def connect_kiwoom(self): return True
        def get_repeat_cnt(self, trcode, record_name): return 0 # 더미
        def get_comm_data(self, trcode, record_name, index, item_name): return "" # 더미
        def set_input_value(self, id_name, value): pass # 더미

    class MockKiwoomTrRequest:
        def __init__(self, kiwoom_helper): self.kiwoom_helper = kiwoom_helper
        def request_account_info(self, account_no, sPrevNext, screen_no): return {} # 더미
        def request_current_price(self, stock_code, sPrevNext="0", screen_no="0002"): 
            # 테스트용 현재가 (실제로는 API 조회)
            prices = {"005930": 78000, "035420": 175000}
            return prices.get(stock_code, 0)
        def send_order(self, *args, **kwargs):
            logger.info(f"Mock SendOrder called with: {kwargs}")
            return {"result": "success", "status": "Mock order placed."} # 더미

    class MockTradeManager:
        def __init__(self, kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number):
            self.kiwoom_helper = kiwoom_helper
            self.kiwoom_tr_request = kiwoom_tr_request
            self.monitor_positions = monitor_positions
            self.account_number = account_number
        def place_order(self, stock_code, order_type, quantity, price=0, hoga_gb="03", org_order_no=""):
            logger.info(f"Mock TradeManager.place_order for {stock_code}, Qty: {quantity}, Type: {order_type}")
            # Mock monitor_positions.update_position 호출 시뮬레이션
            if order_type == 1: # 매수
                self.monitor_positions.update_position(stock_code, quantity, price if price > 0 else self.kiwoom_tr_request.request_current_price(stock_code))
            elif order_type == 2: # 매도
                self.monitor_positions.update_position(stock_code, -quantity, 0)
            return {"status": "success", "order_result": "Mock order success"}

    # 테스트를 위해 임시로 positions.json 파일 생성 (실제 파일은 local_api_server가 관리)
    test_positions = {
        "005930": {"quantity": 10, "purchase_price": 75000.0, "total_purchase_amount": 750000.0, "buy_date": "2025-06-01", "half_exited": False, "trail_high": 75000.0, "item_name": "삼성전자"},
        "035420": {"quantity": 5, "purchase_price": 180000.0, "total_purchase_amount": 900000.0, "buy_date": "2025-06-05", "half_exited": False, "trail_high": 180000.0, "item_name": "네이버"}
    }
    # 일부러 손절/익절/트레일링 테스트를 위한 데이터 추가
    # 손절 테스트용 (현재가 10000, 매수가 11000, 손절 -5% = 10450)
    test_positions["123450"] = {"quantity": 10, "purchase_price": 11000.0, "total_purchase_amount": 110000.0, "buy_date": "2025-06-10", "half_exited": False, "trail_high": 11000.0, "item_name": "손절테스트"}
    # 50% 익절 테스트용 (현재가 12000, 매수가 10000, 익절 10% = 11000)
    test_positions["543210"] = {"quantity": 10, "purchase_price": 10000.0, "total_purchase_amount": 100000.0, "buy_date": "2025-06-12", "half_exited": False, "trail_high": 10000.0, "item_name": "익절테스트"}
    # 트레일링 스탑 테스트용 (이미 50% 익절 가정, 현재가 11000, 트레일 하이 12000, 트레일 스탑 -3% = 11640)
    test_positions["987650"] = {"quantity": 10, "purchase_price": 10000.0, "total_purchase_amount": 50000.0, "buy_date": "2025-06-12", "half_exited": True, "trail_high": 12000.0, "item_name": "트레일테스트"}

    # 테스트를 위해 임시 positions.json 파일 생성
    temp_positions_file = os.path.join(os.path.dirname(POSITIONS_FILE_PATH), "positions_test.json")
    with open(temp_positions_file, 'w', encoding='utf-8') as f:
        json.dump(test_positions, f, indent=4, ensure_ascii=False)
    logger.info(f"Temporary test positions created at: {temp_positions_file}")


    # Mock 객체들을 연결하여 MonitorPositions 인스턴스 생성
    mock_helper = MockKiwoomHelper()
    mock_tr_request = MockKiwoomTrRequest(mock_helper)
    mock_monitor_positions = MonitorPositions(mock_helper, mock_tr_request, None, "YOUR_MOCK_ACCOUNT") # TradeManager는 순환 참조 방지 위해 나중에 설정
    mock_trade_manager = MockTradeManager(mock_helper, mock_tr_request, mock_monitor_positions, "YOUR_MOCK_ACCOUNT")
    mock_monitor_positions.trade_manager = mock_trade_manager # 순환 참조 해결

    # POSITIONS_FILE_PATH를 임시 파일로 설정하여 테스트
    # 실제 실행 시에는 config에서 설정된 경로를 사용합니다.
    # 이 부분은 주석 처리하고, config.py의 POSITIONS_FILE_PATH를 사용하도록 설정하는 것이 좋습니다.
    # self.positions = self.load_positions()을 변경하여 파일 로딩을 오버라이드할 수 있습니다.
    mock_monitor_positions.positions = test_positions # 직접 테스트 데이터 할당

    logger.info("monitor_positions.py 테스트 실행 시작")
    mock_monitor_positions.monitor_positions_strategy()
    logger.info("monitor_positions.py 테스트 실행 완료")

    # 테스트 후 임시 파일 정리 (선택 사항)
    # if os.path.exists(temp_positions_file):
    #     os.remove(temp_positions_file)
    #     logger.info(f"Temporary test positions file removed: {temp_positions_file}")