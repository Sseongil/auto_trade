# server.py (Updated)

from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler
import logging
import json # status.json 관리를 위해 필요

# ✅ 자동매매 함수 import
# from modules.auto_trade import run_auto_trade # 자동매매 시작은 이제 status.json 제어

# 새로운 쿼리 헬퍼 임포트
from modules.kiwoom_query_helper import KiwoomQueryHelper
from modules.notify import send_telegram_message # notify 모듈이 있으니 활용

# 로깅 설정 (server.py 자체의 로깅)
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BOT_TOKEN = "8081086653:AAFbATaP5fUVOJztvPtxQWaMRF0WPEOkUqo"
AUTHORIZED_CHAT_ID = 1866728370 # 예시 (실제 사용자 ID로 변경)

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot=bot, update_queue=None, workers=1, use_context=True)

# --- status.json 파일 관리 함수 (중복 코드를 줄이고 명확히 하기 위해) ---
STATUS_FILE = "status.json"

def get_trade_status() -> str:
    """status.json에서 현재 자동매매 상태를 읽습니다."""
    try:
        if not os.path.exists(STATUS_FILE):
            return "stop" # 파일이 없으면 기본적으로 중지 상태

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
    elif data == "query_balance":
        query.edit_message_text(text="⏳ 예수금 조회 중...")
        balance = KiwoomQueryHelper().get_deposit_balance() # 헬퍼 인스턴스 생성 및 조회
        if balance != -1:
            query.edit_message_text(text=f"💰 현재 예수금: {balance:,}원")
        else:
            query.edit_message_text(text="❌ 예수금 조회에 실패했습니다.")

    elif data == "query_positions":
        query.edit_message_text(text="⏳ 보유 종목 현황 조회 중...")
        df_positions = KiwoomQueryHelper().get_account_positions() # 헬퍼 인스턴스 생성 및 조회
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
        query.edit_message_text(text="⏳ 종합 현황 조회 중...")
        helper = KiwoomQueryHelper()

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

# --- Dispatcher Setup ---
dispatcher.add_handler(CommandHandler("trade", start_trade_panel))
dispatcher.add_handler(CommandHandler("status", show_status_panel)) # 새 명령 추가
dispatcher.add_handler(CallbackQueryHandler(handle_callback_query))

# --- Flask Webhook Route ---
@app.route('/webhook', methods=['POST'])
def webhook_handler():
    # logger.info("✅ 웹훅 호출됨!") # 너무 빈번하게 찍힐 수 있음
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        if update.message:
            logger.info(f"[메시지 수신] chat_id: {update.message.chat_id}, text: {update.message.text}")
        elif update.callback_query:
            logger.info(f"[콜백 수신] {update.callback_query.data} from {update.callback_query.message.chat.id}")
        dispatcher.process_update(update)
    except Exception as e:
        logger.error(f"[오류] 웹훅 처리 실패: {e}", exc_info=True)
    return "ok"

@app.route('/', methods=['GET'])
def index():
    return "🟢 Telegram Auto Trader Bot Running!"

if __name__ == "__main__":
    logger.info("✅ 서버 실행 중... /trade 또는 /status 입력으로 패널 표시")
    # 주의: 외부에서 접근 가능한 환경에서는 debug=True를 사용하지 마세요.
    app.run(host='0.0.0.0', port=5000)