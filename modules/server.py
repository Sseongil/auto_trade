from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler
import logging
import json
import os # os 모듈 import

# ✅ config 모듈에서 텔레그램 설정 임포트
from modules.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID 
# ✅ 자동매매 함수 import (자동매매 시작은 이제 status.json 제어)
# from modules.auto_trade import run_auto_trade 

# 새로운 쿼리 헬퍼 임포트
# 주의: 이 모듈은 Kiwoom OpenAPI+ (Windows 전용)에 종속됩니다.
# Render(Linux) 환경에서 이 코드를 직접 실행하면 실패합니다.
# 실제 운영에서는 Windows PC의 프록시 API 서버를 통해 호출해야 합니다.
from modules.kiwoom_query_helper import KiwoomQueryHelper 
from modules.notify import send_telegram_message # notify 모듈이 있으니 활용

# 로깅 설정 (server.py 자체의 로깅)
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ✅ config.py에서 임포트한 값 사용
BOT_TOKEN = TELEGRAM_TOKEN
AUTHORIZED_CHAT_ID = TELEGRAM_CHAT_ID 

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot=bot, update_queue=None, workers=1, use_context=True)

# --- status.json 파일 관리 함수 (중복 코드를 줄이고 명확히 하기 위해) ---
STATUS_FILE = "status.json" # 현재 작업 디렉토리에 있다고 가정

def get_trade_status() -> str:
    """status.json에서 현재 자동매매 상태를 읽습니다."""
    try:
        if not os.path.exists(STATUS_FILE):
            logger.warning(f"⚠️ {STATUS_FILE} 파일이 존재하지 않습니다. 기본 상태 'stop'으로 초기화합니다.")
            set_trade_status("stop") # 파일이 없으면 기본적으로 중지 상태로 생성
            return "stop"

        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            status_data = json.load(f)
            return status_data.get("status", "stop")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"❌ status.json 읽기 오류: {e}", exc_info=True)
        return "stop"

def set_trade_status(status: str):
    """status.json에 자동매매 상태를 씁니다."""
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump({"status": status}, f, ensure_ascii=False, indent=4)
        logger.info(f"✅ 자동매매 상태를 '{status}'(으)로 설정했습니다.")
        # 상태 변경 알림 (선택 사항)
        send_telegram_message(bot, AUTHORIZED_CHAT_ID, f"🔄 자동매매 상태가 '{status.upper()}'(으)로 변경되었습니다.")
    except Exception as e:
        logger.error(f"❌ status.json 쓰기 오류: {e}", exc_info=True)

# --- Telegram Command Handlers ---

def start_trade_panel(update, context):
    """/trade 명령 시 자동매매 제어 패널을 표시합니다."""
    chat_id = update.effective_chat.id
    logger.info(f"👉 /trade 명령 수신: chat_id = {chat_id}")

    if chat_id != AUTHORIZED_CHAT_ID:
        bot.send_message(chat_id=chat_id, text="❌ 허가되지 않은 사용자입니다.")
        return

    current_status = get_trade_status()
    status_emoji = "🟢" if current_status == "start" else "🔴"

    keyboard = [
        [InlineKeyboardButton(f"🔁 자동매매 시작 ({status_emoji} 현재: {current_status.upper()})", callback_data='set_start')],
        [InlineKeyboardButton(f"⛔ 자동매매 중지 ({status_emoji} 현재: {current_status.upper()})", callback_data='set_stop')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.send_message(chat_id=chat_id, text="📊 자동매매 제어 패널", reply_markup=reply_markup)

def show_status_panel(update, context):
    """/status 명령 시 정보 조회 패널을 표시합니다."""
    chat_id = update.effective_chat.id
    logger.info(f"👉 /status 명령 수신: chat_id = {chat_id}")

    if chat_id != AUTHORIZED_CHAT_ID:
        bot.send_message(chat_id=chat_id, text="❌ 허가되지 않은 사용자입니다.")
        return

    keyboard = [
        [InlineKeyboardButton("💰 예수금 조회", callback_data='query_balance')],
        [InlineKeyboardButton("📈 보유 종목 현황", callback_data='query_positions')],
        [InlineKeyboardButton("📊 종합 현황", callback_data='query_summary')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.send_message(chat_id=chat_id, text="✨ 계좌 정보 조회 패널", reply_markup=reply_markup)


# --- Telegram Callback Handlers ---

def handle_callback_query(update, context):
    """인라인 키보드 버튼 클릭을 처리합니다."""
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    logger.info(f"👉 버튼 클릭: {data} by {chat_id}")
    query.answer() # 콜백 쿼리를 처리했음을 텔레그램에 알림

    if chat_id != AUTHORIZED_CHAT_ID:
        query.edit_message_text(text="❌ 허가되지 않은 사용자입니다.")
        return

    # 자동매매 시작/중지 제어
    if data == "set_start":
        set_trade_status("start")
        query.edit_message_text(text="✅ 자동매매 상태를 '시작'으로 설정했습니다.\n(실제 매매는 `run_all.py` 스케줄에 따라 실행됩니다.)")
    elif data == "set_stop":
        set_trade_status("stop")
        query.edit_message_text(text="🛑 자동매매 상태를 '중지'로 설정했습니다.")

    # 정보 조회 기능
    elif data in ["query_balance", "query_positions", "query_summary"]:
        query.edit_message_text(text="⏳ 조회 중... (키움 API 연동 필요)")
        
        # ⚠️ 중요: Render(Linux) 환경에서는 Kiwoom OpenAPI+ (Windows 전용)에 직접 연결할 수 없습니다.
        # 이 코드는 키움 API가 동일 시스템에서 실행된다는 가정하에 작성되었습니다.
        # 실제 배포 시에는 별도의 Windows 서버 또는 로컬 PC에서 Kiwoom API를 실행하고,
        # 해당 시스템과 통신하는 프록시/API 레이어를 구축해야 합니다.
        # KiwoomQueryHelper().get_deposit_balance() 등의 호출은 해당 프록시를 통해 이루어져야 합니다.
        
        try:
            helper = KiwoomQueryHelper() # 이 호출은 Linux에서 실패할 수 있습니다.
            
            if data == "query_balance":
                balance = helper.get_deposit_balance() # 헬퍼 인스턴스 생성 및 조회
                if balance != -1:
                    query.edit_message_text(text=f"💰 현재 예수금: {balance:,}원")
                else:
                    query.edit_message_text(text="❌ 예수금 조회에 실패했습니다. (키움 API 연결 및 Windows 환경 확인 필요)")

            elif data == "query_positions":
                df_positions = helper.get_account_positions() # 헬퍼 인스턴스 생성 및 조회
                if not df_positions.empty:
                    message = "📈 **보유 종목 현황**\n\n"
                    for _, row in df_positions.iterrows():
                        message += (
                            f"**{row['name']}** ({row['ticker']})\n"
                            f"  - 현재가: {row['current_price']:,}원\n"
                            f"  - 매입가: {row['buy_price']:,}원\n"
                            f"  - 수량: {row['quantity']:,}주\n"
                            f"  - 수익률: {row['pnl_pct']:.2f}%\n"
                            f"-----------------------------\n"
                        )
                    query.edit_message_text(text=message, parse_mode='Markdown')
                else:
                    query.edit_message_text(text="📂 현재 보유 중인 종목이 없습니다.")

            elif data == "query_summary":
                # 예수금 조회
                balance = helper.get_deposit_balance()
                balance_msg = f"💰 **현재 예수금**: {balance:,}원\n\n" if balance != -1 else "❌ **예수금 조회 실패**\n\n"

                # 보유 종목 조회
                df_positions = helper.get_account_positions()
                positions_msg = "📈 **보유 종목 현황**\n"
                if not df_positions.empty:
                    for _, row in df_positions.iterrows():
                        positions_msg += (
                            f"**{row['name']}** ({row['ticker']})\n"
                            f"  - 현재가: {row['current_price']:,}원\n"
                            f"  - 매입가: {row['buy_price']:,}원\n"
                            f"  - 수량: {row['quantity']:,}주\n"
                            f"  - 수익률: {row['pnl_pct']:.2f}%\n"
                            f"-----------------------------\n"
                        )
                else:
                    positions_msg += "📂 현재 보유 중인 종목이 없습니다.\n"

                full_message = f"📊 **종합 자동매매 현황**\n\n{balance_msg}{positions_msg}"
                query.edit_message_text(text=full_message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ 키움 API 연동 실패 (Linux 환경에서 키움 모듈 호출 시도): {e}", exc_info=True)
            query.edit_message_text(text="❌ 키움 API 연동 실패: Windows 환경에서 키움 OpenAPI+가 실행 중인지 확인하세요.")

# 디스패처 설정 --- ---
dispatcher.add_handler(CommandHandler("trade", start_trade_panel))
dispatcher.add_handler(CommandHandler("status", show_status_panel)) # 새 명령 추가
dispatcher.add_handler(CallbackQueryHandler(handle_callback_query))

# --- Flask 웹훅 경로 ---
@app.route('/webhook', methods=['POST'])
def webhook_handler():
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        if update.message:
            logger.info(f"[메시지 수신] chat_id: {update.message.chat_id}, 텍스트: {update.message.text}")
        elif update.callback_query:
            logger.info(f"[콜백 수신] {update.callback_query.data} from {update.callback_query.message.chat.id}")
        dispatcher.process_update(update)
    except Exception as e:
        logger.error(f"[오류] 웹훅 처리 실패: {e}", exc_info=True)
    return "ok"

@app.route('/', methods=['GET'])
def index():
    return "🟢 텔레그램 자동 트레이더 봇 실행 중!"

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000)) # Render 환경 변수 PORT 사용
    logger.info(f"✅ 서버 실행 중... 포트: {PORT}. /trade 또는 /status 입력으로 패널 표시")
    app.run(host='0.0.0.0', port=PORT) # PORT 환경 변수 적용