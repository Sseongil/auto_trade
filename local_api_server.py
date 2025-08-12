import sys
import logging
from flask import Flask
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QEventLoop
from threading import Thread

# 내부 모듈
from modules.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from modules.Kiwoom.kiwoom_api_caller import KiwoomApiCaller
from modules.Kiwoom.kiwoom_real_request import KiwoomRealRequest
from modules.telegram_bot import start_telegram_bot

# 로깅
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Flask (API 필요 시)
app = Flask(__name__)

@app.route("/")
def index():
    return "✅ Local API Server Running"

def connect_kiwoom(kiwoom_api_caller):
    """키움 로그인"""
    loop = QEventLoop()
    result = {"success": False}

    def on_login(err_code):
        if err_code == 0:
            logger.info("✅ 키움 로그인 성공")
            result["success"] = True
        else:
            logger.error(f"❌ 키움 로그인 실패: {err_code}")
        loop.quit()

    kiwoom_api_caller.kiwoom_ocx.OnEventConnect.connect(on_login)
    kiwoom_api_caller.comm_connect()
    loop.exec_()
    return result["success"]

def setup_qt_and_kiwoom():
    """메인 스레드에서 QApplication과 Kiwoom API 초기화"""
    logger.info("🔧 PyQt 애플리케이션 시작...")
    app_qt = QApplication(sys.argv)
    kiwoom_ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
    kiwoom_api_caller = KiwoomApiCaller(kiwoom_ocx)
    KiwoomRealRequest(kiwoom_api_caller)

    if not connect_kiwoom(kiwoom_api_caller):
        logger.critical("❌ 키움 로그인 실패 - 프로그램 종료")
        sys.exit(1)

    logger.info("✅ Kiwoom API 준비 완료")
    return app_qt, kiwoom_api_caller

def start_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

def main():
    # Flask 서버 스레드 실행
    flask_thread = Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # PyQt + Kiwoom
    app_qt, kiwoom_api_caller = setup_qt_and_kiwoom()

    # 텔레그램 봇 스레드 실행
    bot_thread = Thread(target=start_telegram_bot, args=(kiwoom_api_caller,), daemon=True)
    bot_thread.start()

    sys.exit(app_qt.exec_())

if __name__ == "__main__":
    main()

