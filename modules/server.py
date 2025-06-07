from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler
import subprocess

# 🔑 토큰 및 chat ID
BOT_TOKEN = "8081086653:AAFbATaP5fUVOJztvPtxQWaMRF0WPEOkUqo"
AUTHORIZED_CHAT_ID = 1866728370

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot=bot, update_queue=None, workers=1, use_context=True)

# ✅ /trade 명령어 처리
def start_trade(update, context):
    chat_id = update.effective_chat.id
    print(f"👉 /trade 명령 수신: chat_id = {chat_id}")
    if chat_id != AUTHORIZED_CHAT_ID:
        bot.send_message(chat_id=chat_id, text="❌ 허가되지 않은 사용자입니다.")
        return

    keyboard = [
        [InlineKeyboardButton("🔁 자동매매 시작", callback_data='start')],
        [InlineKeyboardButton("⛔ 자동매매 중지", callback_data='stop')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.send_message(chat_id=chat_id, text="📊 자동매매 제어 패널", reply_markup=reply_markup)

# ✅ 버튼 클릭 처리
def handle_callback(update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    print(f"👉 버튼 클릭: {data} by {chat_id}")
    query.answer()

    if data == "start":
        subprocess.Popen(["python", "modules/auto_trade.py"])
        query.edit_message_text(text="✅ 자동매매를 시작합니다.")
    elif data == "stop":
        # TODO: 중지 기능은 다음 단계에서 구현
        query.edit_message_text(text="🛑 자동매매를 중지합니다.")

# ✅ 핸들러 등록
dispatcher.add_handler(CommandHandler("trade", start_trade))
dispatcher.add_handler(CallbackQueryHandler(handle_callback))

# ✅ Webhook 수신 처리
@app.route('/webhook', methods=['POST'])
def webhook_handler():
    print("✅ 웹훅 호출됨!")
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        if update.message:
            print(f"[메시지 수신] chat_id: {update.message.chat_id}, text: {update.message.text}")
        elif update.callback_query:
            print(f"[콜백 수신] {update.callback_query.data} from {update.callback_query.message.chat.id}")
        dispatcher.process_update(update)
    except Exception as e:
        print(f"[오류] 웹훅 처리 실패: {e}")
    return "ok"

@app.route('/', methods=['GET'])
def index():
    return "🟢 Telegram Auto Trader Bot Running!"

if __name__ == "__main__":
    print("✅ 서버 실행 중... /trade 입력으로 패널 표시")
    app.run(host='0.0.0.0', port=5000)
