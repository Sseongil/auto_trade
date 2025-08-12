# app.py
# Render 서버에 배포될 Flask 애플리케이션 (ngrok 제거 버전)

import os
import logging
from flask import Flask, request, jsonify
from datetime import datetime
from dotenv import load_dotenv

# 텔레그램 알림 함수
from modules.notify import send_telegram_message as notify_telegram_message

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 환경 변수 로드
load_dotenv()

app = Flask(__name__)

# 보안용 환경 변수
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not TELEGRAM_CHAT_ID:
    logger.critical("❌ TELEGRAM_CHAT_ID 환경 변수가 설정되지 않았습니다.")

@app.route('/')
def home():
    return "Render Backend Server is running and ready for Telegram webhooks!"

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    """
    텔레그램에서 오는 웹훅 요청을 처리
    """
    if not request.is_json:
        logger.warning("⚠️ Webhook: JSON 요청이 아님.")
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    update = request.get_json()
    message = update.get('message', {})
    chat_id = str(message.get('chat', {}).get('id', ""))
    text = message.get('text', '').strip()

    logger.info(f"📩 Telegram message from {chat_id}: {text}")

    # /status 명령 처리
    if text == '/status':
        if chat_id != str(TELEGRAM_CHAT_ID):
            notify_telegram_message(f"🚨 미승인 사용자({chat_id})가 /status 요청을 시도했습니다.")
            logger.warning(f"Unauthorized /status request from chat_id: {chat_id}")
            return jsonify({"status": "unauthorized"}), 200

        # Render 서버 자체 상태 응답
        status_message = (
            "📊 *자동 매매 백엔드 서버 상태:*\n"
            f"▪️ 상태: `정상 동작 중`\n"
            f"▪️ 서버 시간: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            "▪️ 로컬 서버 연동: `❌ (ngrok 제거)`\n"
        )

        notify_telegram_message(status_message)

    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    # Render는 보통 PORT 환경변수를 사용 (기본값 10000)
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
