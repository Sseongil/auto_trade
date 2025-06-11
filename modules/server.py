from flask import Flask, request, jsonify
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import Bot
import requests # 이전에 추가했습니다.
import json
import os
import logging

# 로깅 설정
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- config 모듈 임포트 (상대 경로 유지) ---
from .config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, LOCAL_API_SERVER_URL

app = Flask(__name__)
bot = Bot(token=TELEGRAM_TOKEN)

# 텔레그램 업데이트 처리
def handle_telegram_updates(update):
    if update.message:
        chat_id = update.message.chat_id
        text = update.message.text
        logger.info(f"Received message from {chat_id}: {text}")

        # 봇에게 명령이 왔을 때만 처리 (예: /status, /trade)
        if text.startswith('/'):
            if text == '/status':
                send_status_to_telegram(chat_id)
            elif text == '/trade':
                toggle_trade_status_and_notify(chat_id)
            else:
                bot.send_message(chat_id=chat_id, text="알 수 없는 명령어입니다. /status 또는 /trade 를 사용해주세요.")
        else:
            # 봇이 특정 명령이 아닌 일반 메시지에 응답할 필요가 없다면 비워둘 수 있습니다.
            pass
    elif update.callback_query:
        # 콜백 쿼리 처리 (예: 인라인 키보드 버튼 클릭)
        query = update.callback_query
        query.answer() # 콜백 쿼리에 대한 응답
        chat_id = query.message.chat_id
        data = query.data
        logger.info(f"Received callback query from {chat_id}: {data}")

        if data == 'toggle_trade_status':
            toggle_trade_status_and_notify(chat_id)
        # 다른 콜백 데이터 처리

# 텔레그램으로 현재 상태 요청 및 전송
def send_status_to_telegram(chat_id):
    if not LOCAL_API_SERVER_URL:
        bot.send_message(chat_id=chat_id, text="⚠️ LOCAL_API_SERVER_URL이 설정되지 않았습니다. Render 환경 변수를 확인해주세요.")
        return

    try:
        # Windows PC의 로컬 API 서버로 /status 요청
        logger.info(f"Requesting status from local API server: {LOCAL_API_SERVER_URL}/status")
        response = requests.get(f"{LOCAL_API_SERVER_URL}/status")
        response.raise_for_status() # HTTP 오류가 발생하면 예외 발생

        status_data = response.json()

        # 상태 데이터가 있다면 메시지 생성
        if status_data:
            message = "📊 **현재 자동매매 상태** 📊\n\n"
            message += f"매매 스위치: `{status_data.get('trade_status', '알 수 없음')}`\n"
            message += f"총 매수 금액: `{status_data.get('total_buy_amount', 0):,}원`\n"
            message += f"총 평가 금액: `{status_data.get('total_eval_amount', 0):,}원`\n"
            message += f"총 평가 손익: `{status_data.get('total_profit_loss', 0):,}원`\n"
            message += f"총 수익률: `{status_data.get('total_profit_loss_rate', 0):.2f}%`\n"
            message += f"보유 종목 수: `{len(status_data.get('positions', []))}`개\n"

            # 보유 종목 상세 정보 (최대 5개까지)
            if status_data.get('positions'):
                message += "\n**보유 종목:**\n"
                for i, pos in enumerate(status_data['positions']):
                    if i >= 5: # 너무 길어지지 않게 최대 5개만 표시
                        message += f"... 외 {len(status_data['positions']) - 5}개 더\n"
                        break
                    message += f"- {pos['stock_name']}: {pos['current_price']:,}원 (수익률: {pos['profit_loss_rate']:.2f}%)\n"
            else:
                message += "\n보유 종목이 없습니다."

            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        else:
            bot.send_message(chat_id=chat_id, text="Windows API 서버로부터 상태 데이터를 가져오는 데 실패했습니다.")

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Windows API 서버 연결 실패: {e}")
        bot.send_message(chat_id=chat_id, text=f"❌ Windows API 서버와 통신할 수 없습니다.\n(오류: {e})")
    except requests.exceptions.RequestException as e:
        logger.error(f"Windows API 서버 요청 오류: {e}")
        bot.send_message(chat_id=chat_id, text=f"⚠️ Windows API 서버 요청 중 오류가 발생했습니다.\n(오류: {e})")
    except Exception as e:
        logger.error(f"상태 전송 중 알 수 없는 오류 발생: {e}")
        bot.send_message(chat_id=chat_id, text=f"알 수 없는 오류가 발생했습니다: {e}")

# 매매 스위치 토글 및 알림
def toggle_trade_status_and_notify(chat_id):
    if not LOCAL_API_SERVER_URL:
        bot.send_message(chat_id=chat_id, text="⚠️ LOCAL_API_SERVER_URL이 설정되지 않았습니다. Render 환경 변수를 확인해주세요.")
        return

    try:
        # 현재 상태를 먼저 가져와서 토글할 값 결정
        logger.info(f"Requesting current status to toggle from local API server: {LOCAL_API_SERVER_URL}/status")
        response_get = requests.get(f"{LOCAL_API_SERVER_URL}/status")
        response_get.raise_for_status()
        current_status_data = response_get.json()
        current_trade_status = current_status_data.get('trade_status', 'stop') # 기본값 'stop'

        new_trade_status = 'start' if current_trade_status == 'stop' else 'stop'

        # Windows PC의 로컬 API 서버로 /trade 요청 (상태 변경)
        logger.info(f"Sending toggle request to local API server: {LOCAL_API_SERVER_URL}/trade with status: {new_trade_status}")
        response_post = requests.post(f"{LOCAL_API_SERVER_URL}/trade", json={"status": new_trade_status})
        response_post.raise_for_status()

        result = response_post.json()
        message = f"자동매매 스위치가 `{new_trade_status}`로 변경되었습니다. (서버 응답: {result.get('message', 'N/A')})"
        bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Windows API 서버 연결 실패 (토글): {e}")
        bot.send_message(chat_id=chat_id, text=f"❌ Windows API 서버와 통신할 수 없어 상태를 변경할 수 없습니다.\n(오류: {e})")
    except requests.exceptions.RequestException as e:
        logger.error(f"Windows API 서버 요청 오류 (토글): {e}")
        bot.send_message(chat_id=chat_id, text=f"⚠️ Windows API 서버 요청 중 오류가 발생했습니다 (토글).\n(오류: {e})")
    except Exception as e:
        logger.error(f"토글 중 알 수 없는 오류 발생: {e}")
        bot.send_message(chat_id=chat_id, text=f"알 수 없는 오류가 발생했습니다 (토글): {e}")

# Flask 앱의 웹훅 처리 (Render에서 텔레그램으로부터 메시지를 받는 곳)
# 이 부분을 /webhook 경로로 변경했습니다.
@app.route('/webhook', methods=['POST']) # <-- 이 줄이 수정되었습니다.
def webhook():
    if request.method == 'POST':
        update = request.get_json()
        logger.info(f"Received webhook update: {update}")
        # 텔레그램 업데이트 객체를 직접 처리
        try:
            from telegram import Update
            update_obj = Update.de_json(update, bot)
            handle_telegram_updates(update_obj)
        except Exception as e:
            logger.error(f"Error handling Telegram update: {e}")
            # 오류 발생 시 텔레그램으로 메시지 보낼 수 있으나, 무한 루프 위험 있으므로 주의
            # bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"봇 처리 중 오류 발생: {e}")

        return jsonify({'status': 'ok'})
    return jsonify({'status': 'bad request'}), 400

# 서비스가 시작될 때 텔레그램으로 알림
# Render가 이 엔드포인트를 호출하도록 설정되어 있어야 합니다.
@app.route('/notify_startup', methods=['GET'])
def notify_startup():
    try:
        # TELEGRAM_CHAT_ID가 유효한지 확인
        if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == 0:
            logger.warning("TELEGRAM_CHAT_ID is not set or is 0. Skipping startup notification.")
            return jsonify({'status': 'warning', 'message': 'TELEGRAM_CHAT_ID is not set'})

        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 자동매매 봇이 Render에서 성공적으로 시작되었습니다!")
        logger.info("Startup notification sent.")
        return jsonify({'status': 'ok', 'message': 'Startup notification sent'})
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == "__main__":
    # Gunicorn 사용 시 이 부분은 직접 실행되지 않습니다.
    # Render의 시작 명령어 (Start Command)는 'gunicorn modules.server:app' 입니다.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)