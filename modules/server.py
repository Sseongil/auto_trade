import os
import requests
import json
import logging
from telegram import Bot
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경 변수 설정
LOCAL_API_SERVER_URL = os.getenv("LOCAL_API_SERVER_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID") # 단일 채팅 ID만 사용한다고 가정

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 텔레그램 봇 초기화
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# --- 텔레그램으로 상태 전송 함수 ---
def send_status_to_telegram(chat_id):
    if not LOCAL_API_SERVER_URL:
        logger.error("LOCAL_API_SERVER_URL 환경 변수가 설정되지 않았습니다.")
        bot.send_message(chat_id=chat_id, text="❌ 서버 설정 오류: LOCAL_API_SERVER_URL이 설정되지 않았습니다.")
        return

    logger.info(f"로컬 API 서버에 상태 요청: {LOCAL_API_SERVER_URL}/status")
    try:
        # ✅ requests.get 호출에 명시적인 타임아웃 추가 (로컬 서버의 10초 타임아웃보다 길게 설정)
        response = requests.get(f"{LOCAL_API_SERVER_URL}/status", timeout=15) # 15초 타임아웃 설정
        response.raise_for_status() # HTTP 오류 (4xx, 5xx) 발생 시 예외 발생

        status_data = response.json()
        
        # 데이터 유효성 검사 및 기본값 설정
        trade_status = status_data.get('trade_status', '확인불가')
        total_buy_amount = status_data.get('total_buy_amount', 0)
        total_eval_amount = status_data.get('total_eval_amount', 0)
        total_profit_loss = status_data.get('total_profit_loss', 0)
        total_profit_loss_rate = status_data.get('total_profit_loss_rate', 0.0)
        positions = status_data.get('positions', [])

        message = (
            f"🤖 **현재 자동매매 상태**: `{trade_status}`\n"
            f"💰 **총 매입 금액**: `{total_buy_amount:,}원`\n"
            f"📈 **총 평가 금액**: `{total_eval_amount:,}원`\n"
            f"📊 **총 평가 손익**: `{total_profit_loss:,}원`\n"
            f"🎯 **총 수익률**: `{total_profit_loss_rate:.2f}%`\n\n"
        )

        if positions:
            message += "📊 **보유 종목**:\n"
            for p in positions:
                stock_name = p.get('stock_name', 'N/A')
                current_price = p.get('current_price', 0)
                profit_loss_rate = p.get('profit_loss_rate', 0.0)
                message += f"- `{stock_name}`: 현재가 `{current_price:,}원`, 수익률 `{profit_loss_rate:.2f}%`\n"
        else:
            message += "📈 보유 종목 없음.\n"

        bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        logger.info(f"상태 정보를 텔레그램 채팅 {chat_id}에 성공적으로 전송했습니다.")

    except requests.exceptions.Timeout:
        logger.error("로컬 API 서버 요청 시간 초과 (15초).")
        bot.send_message(chat_id=chat_id, text="❌ 로컬 API 서버 응답 시간 초과 (15초). Kiwoom HTS 및 서버 상태를 확인해주세요.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP 오류 발생: {e.response.status_code} - {e.response.text}")
        bot.send_message(chat_id=chat_id, text=f"❌ 로컬 API 서버에서 HTTP 오류 발생: `{e.response.status_code}`. 서버 로그를 확인해주세요.")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"로컬 API 서버 연결 오류: {e}. ngrok 터널이 활성화되어 있는지 확인하세요.")
        bot.send_message(chat_id=chat_id, text=f"❌ 로컬 API 서버에 연결할 수 없습니다. ngrok 터널이 활성화되어 있는지 확인해주세요.")
    except json.JSONDecodeError as e:
        logger.error(f"로컬 API 서버 응답 JSON 파싱 오류: {e}. 응답 텍스트: {response.text if 'response' in locals() else 'N/A'}")
        bot.send_message(chat_id=chat_id, text="❌ 로컬 API 서버 응답 형식 오류. 서버 로그를 확인해주세요.")
    except Exception as e:
        logger.error(f"send_status_to_telegram 함수에서 예상치 못한 오류 발생: {e}", exc_info=True)
        bot.send_message(chat_id=chat_id, text=f"❌ 상태 전송 중 예상치 못한 오류 발생: `{e}`")

# --- 텔레그램 웹훅 처리 함수 ---
def handle_telegram_updates(update):
    # 'message' 객체 내부에 'text' 필드가 있는지 확인
    if 'message' not in update or 'text' not in update['message']:
        logger.warning("받은 업데이트에 메시지 텍스트가 없습니다. 스킵합니다.")
        return

    chat_id = update['message']['chat']['id']
    user_message = update['message']['text']
    logger.info(f"Received message from {chat_id}: {user_message}")

    if str(chat_id) != CHAT_ID: # 환경변수에 설정된 CHAT_ID와 일치하는지 확인
        logger.warning(f"허용되지 않은 사용자 ({chat_id})의 메시지: {user_message}")
        bot.send_message(chat_id=chat_id, text="죄송합니다. 이 봇은 허용된 사용자만 접근할 수 있습니다.")
        return

    if user_message == '/status':
        send_status_to_telegram(chat_id)
    elif user_message == '/start_trade':
        logger.info(f"로컬 API 서버에 매매 시작 요청: {LOCAL_API_SERVER_URL}/trade")
        try:
            # ✅ requests.post 호출에도 타임아웃 적용
            response = requests.post(f"{LOCAL_API_SERVER_URL}/trade", json={"status": "start"}, timeout=10) # 10초 타임아웃
            response.raise_for_status()
            result = response.json()
            bot.send_message(chat_id=chat_id, text=f"✅ {result.get('message', '매매 시작 요청 완료')}")
            logger.info(f"매매 시작 요청 성공: {result}")
        except requests.exceptions.Timeout:
            logger.error("로컬 API 서버 요청 시간 초과 (10초) - /start_trade.")
            bot.send_message(chat_id=chat_id, text="❌ 로컬 API 서버 응답 시간 초과 (10초). Kiwoom HTS 및 서버 상태를 확인해주세요.")
        except requests.exceptions.RequestException as e:
            logger.error(f"로컬 API 서버 통신 오류 - /start_trade: {e}")
            bot.send_message(chat_id=chat_id, text=f"❌ 매매 시작 요청 중 오류 발생: {e}")
        except Exception as e:
            logger.error(f"예상치 못한 오류 발생 - /start_trade: {e}")
            bot.send_message(chat_id=chat_id, text=f"❌ 예상치 못한 오류 발생: {e}")

    elif user_message == '/stop_trade':
        logger.info(f"로컬 API 서버에 매매 중지 요청: {LOCAL_API_SERVER_URL}/trade")
        try:
            # ✅ requests.post 호출에도 타임아웃 적용
            response = requests.post(f"{LOCAL_API_SERVER_URL}/trade", json={"status": "stop"}, timeout=10) # 10초 타임아웃
            response.raise_for_status()
            result = response.json()
            bot.send_message(chat_id=chat_id, text=f"✅ {result.get('message', '매매 중지 요청 완료')}")
            logger.info(f"매매 중지 요청 성공: {result}")
        except requests.exceptions.Timeout:
            logger.error("로컬 API 서버 요청 시간 초과 (10초) - /stop_trade.")
            bot.send_message(chat_id=chat_id, text="❌ 로컬 API 서버 응답 시간 초과 (10초). Kiwoom HTS 및 서버 상태를 확인해주세요.")
        except requests.exceptions.RequestException as e:
            logger.error(f"로컬 API 서버 통신 오류 - /stop_trade: {e}")
            bot.send_message(chat_id=chat_id, text=f"❌ 매매 중지 요청 중 오류 발생: {e}")
        except Exception as e:
            logger.error(f"예상치 못한 오류 발생 - /stop_trade: {e}")
            bot.send_message(chat_id=chat_id, text=f"❌ 예상치 못한 오류 발생: {e}")
    else:
        bot.send_message(chat_id=chat_id, text="알 수 없는 명령어입니다. `/status`, `/start_trade`, `/stop_trade` 중 하나를 입력해주세요.")


# Flask 앱 인스턴스 (Render 배포용)
from flask import Flask, request as flask_request # request 이름 충돌 방지
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    if flask_request.method == "POST":
        update_obj = flask_request.get_json()
        logger.info(f"Received webhook update: {update_obj}")
        # 새 스레드에서 업데이트 처리 (웹훅 응답 시간을 빠르게 하기 위함)
        threading.Thread(target=handle_telegram_updates, args=(update_obj,)).start()
        return "ok", 200 # 텔레그램 서버에 즉시 응답

# Render 시작 시 웹훅 설정 (옵션)
# Render 환경에서는 웹훅 URL이 계속 바뀌지 않으므로, 이 부분을 Build Command에 넣거나,
# 최초 1회만 수동으로 설정하는 것이 일반적입니다.
# 매번 앱 시작 시마다 설정할 필요는 없습니다.
# def set_webhook():
#     webhook_url = f"YOUR_RENDER_SERVICE_URL/webhook" # Render 서비스의 실제 URL
#     try:
#         set_webhook_response = bot.set_webhook(url=webhook_url)
#         logger.info(f"Webhook 설정 응답: {set_webhook_response}")
#     except Exception as e:
#         logger.error(f"웹훅 설정 오류: {e}")

# if __name__ == '__main__':
#     # 로컬에서 테스트할 때는 run() 함수를 사용하고, Render에서는 Gunicorn이 이 파일을 실행합니다.
#     # Render에서는 __name__ == '__main__' 블록이 실행되지 않습니다.
#     # set_webhook() # 필요하다면 여기서 웹훅을 설정할 수 있습니다.
#     app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))