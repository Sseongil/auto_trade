import os
import sys
import json
import time as time_module
import logging
from dotenv import load_dotenv
from flask import Flask
from modules.Kiwoom.kiwoom_query_helper import KiwoomQueryHelper
from modules.Kiwoom.kiwoom_tr_request import KiwoomTrRequest
from modules.Kiwoom.monitor_positions import MonitorPositions
from modules.Kiwoom.trade_manager import TradeManager
from modules.strategies.main_strategy_loop import run_daily_trading_cycle
from modules.common.config import API_SERVER_PORT
from modules.notify import send_telegram_message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
app_initialized = False

def initialize_kiwoom_api_in_background_thread():
    import pythoncom
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QAxContainer import QAxWidget

    pythoncom.CoInitialize()

    app = QApplication([])
    kiwoom_ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
    kiwoom_helper = KiwoomQueryHelper(kiwoom_ocx, app)

    if not kiwoom_helper.connect_kiwoom(timeout_ms=10000):
        logger.critical("❌ 키움 API 연결 실패")
        return None, None, None, None

    account_number = os.getenv("ACCOUNT_NUMBERS", "").split(',')[0].strip()
    account_password = os.getenv("ACCOUNT_PASSWORD", "").strip()

    kiwoom_tr_request = KiwoomTrRequest(kiwoom_helper, app, account_password)
    monitor_positions = MonitorPositions(kiwoom_helper, kiwoom_tr_request, None, account_number)
    trade_manager = TradeManager(kiwoom_helper, kiwoom_tr_request, monitor_positions, account_number)
    monitor_positions.set_trade_manager(trade_manager)

    global app_initialized
    app_initialized = True

    return kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager

def background_trading_loop():
    kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager = \
        initialize_kiwoom_api_in_background_thread()

    if not kiwoom_helper:
        logger.critical("❌ Kiwoom API 초기화 실패. 종료합니다.")
        sys.exit(1)

    while True:
        try:
            run_daily_trading_cycle(kiwoom_helper, kiwoom_tr_request, monitor_positions, trade_manager)
            time_module.sleep(30)
        except Exception as e:
            logger.error(f"백그라운드 트레이딩 루프 오류: {e}", exc_info=True)
            send_telegram_message(f"❌ 자동매매 루프 오류: {e}")
            time_module.sleep(60)

if __name__ == '__main__':
    trading_thread = threading.Thread(target=background_trading_loop, daemon=True)
    trading_thread.start()

    app.run(host="0.0.0.0", port=int(API_SERVER_PORT), debug=True, use_reloader=False)
