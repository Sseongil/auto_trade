# modules/Kiwoom/monitor_positions.py

import os
import json
import logging
from datetime import datetime
import threading 
from modules.common.config import POSITIONS_FILE_PATH
from modules.common.utils import get_current_time_str

logger = logging.getLogger(__name__)

class MonitorPositions:
    def __init__(self, kiwoom_helper, kiwoom_tr_request, trade_manager_instance, account_number): 
        self.kiwoom_helper = kiwoom_helper
        self.kiwoom_tr_request = kiwoom_tr_request
        self.trade_manager = trade_manager_instance 
        self.account_number = account_number
        self.position_lock = threading.Lock() 
        self.positions = self.load_positions()
        logger.info(f"{get_current_time_str()}: MonitorPositions initialized for account {self.account_number}. Loaded {len(self.positions)} positions.")

    def set_trade_manager(self, trade_manager_instance):
        """TradeManager 인스턴스를 설정합니다 (순환 참조 방지용)."""
        self.trade_manager = trade_manager_instance
        logger.info(f"TradeManager instance set in MonitorPositions.")

    def load_positions(self):
        """
        저장된 포지션 데이터를 로드하고, 'buy_time' 필드가 없는
        이전 데이터의 호환성을 위해 현재 시간으로 보완합니다.
        """
        with self.position_lock: 
            if os.path.exists(POSITIONS_FILE_PATH):
                with open(POSITIONS_FILE_PATH, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        for pos_key, pos_data in data.items():
                            if "buy_time" not in pos_data:
                                pos_data["buy_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                logger.warning(f"Position for {pos_key} had no 'buy_time'. Initialized with current time.")
                            if "name" not in pos_data: 
                                pos_data["name"] = self.kiwoom_helper.get_stock_name(pos_key)
                        return data
                    except json.JSONDecodeError:
                        logger.error(f"JSONDecodeError when loading positions from {POSITIONS_FILE_PATH}. Returning empty positions.")
                        return {}
            logger.info(f"Positions file not found at {POSITIONS_FILE_PATH}. Starting with empty positions.")
            return {}

    def save_positions(self):
        """현재 포지션 데이터를 파일에 저장합니다."""
        with self.position_lock: 
            try:
                with open(POSITIONS_FILE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(self.positions, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error saving positions to {POSITIONS_FILE_PATH}: {e}")

    def sync_local_positions(self, api_holdings_data):
        """
        API에서 조회한 보유 종목 데이터와 로컬 포지션 데이터를 동기화합니다.
        주로 시스템 시작 시 호출되어 실제 보유 종목을 로컬에 반영합니다.
        Args:
            api_holdings_data (list of dict): API에서 조회한 보유 종목 데이터 (예: [{'종목코드': '005930', '보유수량': 10, ...}])
                                              또는 오류 메시지가 포함된 dict일 수 있습니다.
        """
        with self.position_lock:
            # 💡 api_holdings_data가 유효한 리스트인지 먼저 확인
            if not isinstance(api_holdings_data, list):
                logger.warning(f"Invalid api_holdings_data received for sync_local_positions: {api_holdings_data}. Skipping sync.")
                return # 유효하지 않은 데이터이므로 동기화 건너뜀

            old_positions = self.positions.copy()
            self.positions = {} 

            for item in api_holdings_data:
                stock_code = item.get("종목코드", "").strip()
                quantity = int(item.get("보유수량", 0))
                purchase_price = float(item.get("매입가", 0)) 

                if stock_code and quantity > 0:
                    stock_name = item.get("종목명", self.kiwoom_helper.get_stock_name(stock_code)) 
                    
                    existing_pos_data = old_positions.get(stock_code, {})
                    
                    self.positions[stock_code] = {
                        "quantity": quantity,
                        "purchase_price": purchase_price,
                        "total_purchase_amount": purchase_price * quantity, 
                        "buy_date": existing_pos_data.get("buy_date", datetime.today().strftime("%Y-%m-%d")),
                        "buy_time": existing_pos_data.get("buy_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        "half_exited": existing_pos_data.get("half_exited", False),
                        "trail_high": existing_pos_data.get("trail_high", purchase_price), 
                        "name": stock_name
                    }
                    logger.info(f"Synced API holdings: {stock_name}({stock_code}) - Qty: {quantity}, Price: {purchase_price:,}")
            self.save_positions()
            logger.info(f"Local positions synchronized with API holdings. Total {len(self.positions)} positions.")

    def register_all_positions_for_real_time_data(self):
        """현재 보유 중인 모든 종목을 실시간 데이터 수신에 등록합니다."""
        with self.position_lock:
            if not self.positions:
                logger.info("보유 종목이 없어 실시간 데이터 등록을 건너뜁니다.")
                return

            codes_to_register = list(self.positions.keys())
            
            screen_no = self.kiwoom_helper.generate_real_time_screen_no()
            fid_list = "10;15;228;851;852;27;28" 

            try:
                self.kiwoom_helper.SetRealReg(screen_no, ";".join(codes_to_register), fid_list, "0")
                logger.info(f"모든 보유 종목 {len(codes_to_register)}개를 실시간 데이터에 등록 완료 (화면번호: {screen_no}).")
            except Exception as e:
                logger.error(f"보유 종목 실시간 데이터 등록 실패: {e}", exc_info=True)

    def update_position_from_chejan(self, stock_code, new_quantity, new_purchase_price=None, new_buy_time=None):
        """
        체결 데이터 수신(OnReceiveChejanData) 후 포지션을 업데이트합니다.
        이 메서드는 TradeManager에서 호출될 것입니다.
        """
        stock_code = stock_code.strip()
        with self.position_lock:
            current_pos = self.positions.get(stock_code, {})
            current_qty = current_pos.get("quantity", 0)

            if new_quantity <= 0:
                self.remove_position(stock_code)
                logger.info(f"Chejan update: {stock_code} quantity is 0 or less. Position removed.")
                return

            if new_quantity > current_qty:
                if stock_code not in self.positions: 
                    stock_name = self.kiwoom_helper.get_stock_name(stock_code)
                    self.positions[stock_code] = {
                        "quantity": new_quantity,
                        "purchase_price": new_purchase_price if new_purchase_price is not None else 0.0,
                        "total_purchase_amount": new_purchase_price * new_quantity if new_purchase_price is not None else 0.0,
                        "buy_date": datetime.today().strftime("%Y-%m-%d"),
                        "buy_time": new_buy_time if new_buy_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "half_exited": False,
                        "trail_high": new_purchase_price if new_purchase_price is not None else 0.0,
                        "name": stock_name
                    }
                    logger.info(f"Chejan update: New position for {stock_code} added. Qty: {new_quantity}")
                else: 
                    old_total_amount = current_pos.get("total_purchase_amount", 0)
                    added_qty = new_quantity - current_qty
                    added_amount = added_qty * new_purchase_price if new_purchase_price is not None else 0 
                    
                    self.positions[stock_code]["quantity"] = new_quantity
                    self.positions[stock_code]["total_purchase_amount"] = old_total_amount + added_amount
                    if new_quantity > 0:
                        self.positions[stock_code]["purchase_price"] = self.positions[stock_code]["total_purchase_amount"] / new_quantity
                    
                    logger.info(f"Chejan update: {stock_code} position increased. New Qty: {new_quantity}, Avg Price: {self.positions[stock_code]['purchase_price']:.2f}")

            elif new_quantity < current_qty: 
                self.positions[stock_code]["quantity"] = new_quantity
                if new_quantity == 0:
                    self.remove_position(stock_code) 
                    logger.info(f"Chejan update: {stock_code} fully sold. Position removed.")
                else:
                    logger.info(f"Chejan update: {stock_code} position decreased. Remaining Qty: {new_quantity}")
            
            self.save_positions()

    def get_position(self, stock_code):
        """특정 종목의 포지션 데이터를 반환합니다."""
        with self.position_lock: 
            return self.positions.get(stock_code, None)

    def get_all_positions(self):
        """현재 보유 중인 모든 포지션 데이터를 반환합니다 (사본 반환)."""
        with self.position_lock: 
            return self.positions.copy() 

    def remove_position(self, stock_code):
        """특정 종목의 포지션 데이터를 삭제합니다 (보통 전량 매도 후 호출)."""
        with self.position_lock: 
            if stock_code in self.positions:
                self.kiwoom_helper.SetRealRemove("ALL", stock_code) 
                del self.positions[stock_code]
                self.save_positions()
                logger.info(f"Position for {stock_code} removed from monitoring and real-time. Remaining positions: {len(self.positions)}")
            else:
                logger.warning(f"Attempted to remove non-existent position: {stock_code}. No action taken.")

