import os
import requests
import json
import logging
import threading
from flask import Flask, request as flask_request
from telegram import Bot
from dotenv import load_dotenv

# .env 로드
load_dotenv()

# --- 환경 변수 로딩 ---
LOCAL_API_SERVER_URL = os.getenv("LOCAL_API_SERVER_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_TELEGRAM_USER_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # ✅ 더 명확한 의미의 변수명으로 활용

# --- 유효성 검증 ---
if not TELEGRAM_BOT_TOKEN:
    print("[ERROR] TELEGRAM_BOT_TOKEN 환경 변수를 불러오지 못했습니다.")
if not ALLOWED_TELEGRAM_USER_ID:
    print("[ERROR] TELEGRAM_CHAT_ID (허용된 사용자 ID) 환경 변수를 불러오지 못했습니다.")
if not LOCAL_API_SERVER_URL:
    print("[WARN] LOCAL_API_SERVER_URL 값이 없습니다. ngrok URL이 자동 동기화되지 않았을 수 있습니다.")

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 텔레그램 봇 초기화 ---
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# --- Flask 앱 초기화 ---
app = Flask(__name__)

# --- 텔레그램 메시지 핸들러 ---
def handle_telegram_updates(update):
    if 'message' not in update or 'text' not in update['message']:
        logger.warning("⚠️ 메시지에 텍스트 없음. 무시.")
        return

    chat_id = str(update['message']['chat']['id'])
    user_message = update['message']['text']

    logger.info(f"[DEBUG] 사용자 chat_id: {chat_id} / 허용된 사용자: {ALLOWED_TELEGRAM_USER_ID}")

    if chat_id != str(ALLOWED_TELEGRAM_USER_ID):
        bot.send_message(chat_id=chat_id, text="🚫 접근 권한이 없습니다.")
        return

    if user_message == '/status':
        bot.send_message(chat_id=chat_id, text="⏳ 상태 조회 중입니다. 잠시만 기다려주세요.")
        threading.Thread(target=send_status_to_telegram, args=(chat_id,)).start()

    elif user_message == '/start_trade':
        try:
            response = requests.post(f"{LOCAL_API_SERVER_URL}/trade", json={"status": "start"}, timeout=10)
            msg = response.json().get("message", "매매 시작 요청 완료")
            bot.send_message(chat_id=chat_id, text=f"✅ {msg}")
        except Exception as e:
            logger.exception("❌ 매매 시작 실패")
            bot.send_message(chat_id=chat_id, text=f"❌ 매매 시작 실패: {e}")

    elif user_message == '/stop_trade':
        try:
            response = requests.post(f"{LOCAL_API_SERVER_URL}/trade", json={"status": "stop"}, timeout=10)
            msg = response.json().get("message", "매매 중지 요청 완료")
            bot.send_message(chat_id=chat_id, text=f"🛑 {msg}")
        except Exception as e:
            logger.exception("❌ 매매 중지 실패")
            bot.send_message(chat_id=chat_id, text=f"❌ 매매 중지 실패: {e}")

    else:
        bot.send_message(chat_id=chat_id, text="❓ 유효하지 않은 명령어입니다. `/status`, `/start_trade`, `/stop_trade` 중 하나를 사용해주세요.")

# --- 상태 전송 함수 ---
def send_status_to_telegram(chat_id):
    if not LOCAL_API_SERVER_URL:
        logger.error("LOCAL_API_SERVER_URL 환경변수가 설정되지 않았습니다.")
        bot.send_message(chat_id=chat_id, text="❌ LOCAL_API_SERVER_URL이 설정되지 않았습니다.")
        return

    try:
        logger.info(f"GET {LOCAL_API_SERVER_URL}/status 요청 시작")
        response = requests.get(f"{LOCAL_API_SERVER_URL}/status", timeout=15)
        response.raise_for_status()
        status_data = response.json()

        trade_status = status_data.get('trade_status', 'N/A')
        total_buy_amount = status_data.get('total_buy_amount', 0)
        total_eval_amount = status_data.get('total_eval_amount', 0)
        total_profit_loss = status_data.get('total_profit_loss', 0)
        total_profit_loss_rate = status_data.get('total_profit_loss_rate', 0.0)
        positions = status_data.get('positions', [])

        message = (
            f"🤖 *자동매매 상태*: `{trade_status}`\n"
            f"💰 *총 매입금액*: `{total_buy_amount:,}원`\n"
            f"📈 *총 평가금액*: `{total_eval_amount:,}원`\n"
            f"📊 *총 손익금액*: `{total_profit_loss:,}원`\n"
            f"🎯 *총 수익률*: `{total_profit_loss_rate:.2f}%`\n\n"
        )

        if positions:
            message += "📌 *보유 종목*:\n"
            for p in positions:
                message += f"- `{p.get('stock_name', 'N/A')}`: `{p.get('current_price', 0):,}원`, `{p.get('profit_loss_rate', 0.0):.2f}%`\n"
        else:
            message += "📂 보유 종목 없음."

        bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
        logger.info("✅ 텔레그램 전송 완료")

    except requests.exceptions.Timeout:
        logger.error("❌ 상태 요청 타임아웃")
        bot.send_message(chat_id=chat_id, text="❌ 요청 시간이 초과되었습니다. 서버 상태를 확인하세요.")
    except Exception as e:
        logger.exception("❌ 상태 요청 실패")
        bot.send_message(chat_id=chat_id, text=f"❌ 오류 발생: {e}")

# --- 웹훅 엔드포인트 ---
@app.route('/webhook', methods=['POST'])
def webhook():
    update_obj = flask_request.get_json()
    threading.Thread(target=handle_telegram_updates, args=(update_obj,)).start()
    return "ok", 200
