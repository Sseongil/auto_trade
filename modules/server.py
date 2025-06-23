# modules/server.py
# Render 서버에 배포될 Flask 애플리케이션

import os
import logging
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

# 로깅 설정 (Render 로그에 표시될 내용)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 환경 변수 로드 (Render 환경 변수에서 가져옴)
load_dotenv()

app = Flask(__name__)

# --- 환경 변수 로드 ---
# 텔레그램 봇 토큰 및 채팅 ID (Render 환경 변수에 설정되어야 함)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 로컬 API 서버의 현재 ngrok URL을 저장할 변수
# 초기값은 없지만, 로컬 서버가 업데이트 요청을 보내면 저장될 것임
NGROK_PUBLIC_URL = None 

# 내부 API 키 (로컬 서버에서 ngrok URL 업데이트 요청 시 사용될 키)
# Render 환경 변수에 INTERNAL_API_KEY로 설정되어 있어야 함
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY")
if not INTERNAL_API_KEY:
    logger.critical("❌ Render 서버: INTERNAL_API_KEY 환경 변수 미설정!")
    # 실제 프로덕션 환경에서는 sys.exit(1)로 종료할 수 있지만,
    # 여기서는 로그만 남기고 일단 진행 (테스트 편의상)

# --- 헬퍼 함수: 텔레그램 메시지 전송 ---
def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ Telegram bot token or chat ID not set. Cannot send message.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown" # 메시지 포맷팅을 위해 Markdown 사용
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        logger.info(f"✅ Telegram message sent successfully: {message[:50]}...")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send Telegram message: {e}")

# --- Render 서버 엔드포인트 ---

@app.route('/')
def home():
    return "Render Backend Server is running and ready for Telegram webhooks!"

@app.route('/update_ngrok_internal', methods=['POST'])
def update_ngrok_internal():
    """
    로컬 Flask 서버로부터 ngrok URL을 수신하여 저장하는 엔드포인트.
    내부 인증 키를 통해 접근을 제한합니다.
    """
    global NGROK_PUBLIC_URL
    
    # 내부 API 키 인증
    provided_key = request.headers.get('X-Internal-API-Key')
    if not provided_key or provided_key != INTERNAL_API_KEY:
        logger.warning(f"❌ 내부 API 인증 실패: 잘못된 또는 누락된 Internal API Key. 요청 IP: {request.remote_addr}")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json()
    new_url = data.get('new_url')

    if new_url:
        NGROK_PUBLIC_URL = new_url
        logger.info(f"✅ Ngrok URL 업데이트됨: {NGROK_PUBLIC_URL}")
        send_telegram_message(f"📡 Ngrok URL이 Render 서버에 업데이트됨:\n`{NGROK_PUBLIC_URL}`")
        return jsonify({"status": "ok", "message": "ngrok URL updated"}), 200
    else:
        logger.warning("⚠️ Ngrok URL 업데이트 요청에 new_url이 누락되었습니다.")
        return jsonify({"status": "error", "message": "Missing new_url"}), 400

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    """
    텔레그램 봇으로부터 메시지를 수신하는 웹훅 엔드포인트.
    """
    if not request.is_json:
        logger.warning("⚠️ Webhook: Request is not JSON.")
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    update = request.get_json()
    logger.info(f"Received Telegram update: {update}")

    # 텔레그램 메시지 파싱
    message = update.get('message', {})
    chat_id = message.get('chat', {}).get('id')
    text = message.get('text', '')

    if chat_id and text:
        logger.info(f"Telegram message from {chat_id}: {text}")

        if text == '/status':
            # 텔레그램 채팅 ID가 설정된 ID와 일치하는지 확인 (보안 강화)
            if str(chat_id) != TELEGRAM_CHAT_ID:
                send_telegram_message(f"🚨 경고: 알 수 없는 사용자({chat_id})로부터 /status 명령 수신. 허용되지 않은 접근.")
                logger.warning(f"Unauthorized /status command from chat_id: {chat_id}")
                return jsonify({"status": "unauthorized"}), 200 # Unauthorized 응답이지만 텔레그램에는 OK
                
            if NGROK_PUBLIC_URL:
                # 로컬 API 서버의 /status 엔드포인트 호출
                local_status_url = f"{NGROK_PUBLIC_URL.rstrip('/')}/status"
                try:
                    logger.info(f"Fetching status from local API: {local_status_url}")
                    headers = {'X-API-Key': os.environ.get("LOCAL_API_KEY", "")} # 로컬 서버용 API 키
                    response = requests.get(local_status_url, headers=headers, timeout=10)
                    response.raise_for_status()
                    status_data = response.json()
                    
                    # 상태 정보를 보기 좋게 포맷팅하여 텔레그램으로 전송
                    status_message = (
                        f"📊 *자동 매매 시스템 상태:*\n"
                        f"▪️ 상태: `{status_data.get('status', 'N/A')}`\n"
                        f"▪️ 서버 시간: `{status_data.get('server_time', 'N/A')}`\n"
                        f"▪️ 계좌 번호: `{status_data.get('account_number', 'N/A')}`\n"
                        f"▪️ 예수금: `{status_data.get('balance', 0):,} KRW`\n"
                        f"▪️ 마지막 업데이트: `{status_data.get('last_kiwoom_update', 'N/A')}`\n"
                    )
                    
                    positions = status_data.get('positions', {})
                    if positions:
                        status_message += "\n*📈 보유 종목:*\n"
                        for code, pos in positions.items():
                            status_message += (
                                f"  - `{pos.get('name', code)} ({code})`\n"
                                f"    수량: {pos.get('quantity', 0)}주, 매입가: {pos.get('purchase_price', 0):,}원\n"
                            )
                    else:
                        status_message += "\n_보유 종목 없음_\n"

                    send_telegram_message(status_message)

                except requests.exceptions.RequestException as e:
                    error_msg = f"❌ 로컬 API 서버 상태 조회 실패: {e}"
                    logger.error(error_msg, exc_info=True)
                    send_telegram_message(f"🚨 로컬 API 서버 상태 조회 실패: `{e}`. ngrok이 실행 중인지, 로컬 서버가 작동하는지 확인하세요.")
                except Exception as e:
                    error_msg = f"❌ 상태 메시지 처리 중 예기치 않은 오류: {e}"
                    logger.error(error_msg, exc_info=True)
                    send_telegram_message(f"🚨 상태 메시지 처리 중 오류: `{e}`")
            else:
                send_telegram_message("⚠️ Ngrok URL이 아직 Render 서버에 등록되지 않았습니다.")
                logger.warning("Ngrok URL not set on Render server.")
        else:
            # 다른 메시지는 무시하거나 기본 응답 제공
            # send_telegram_message("알 수 없는 명령입니다. /status를 입력해 주세요.")
            pass # 불필요한 응답 방지

    return jsonify({"status": "ok"}), 200 # 텔레그램에 200 OK 응답

# Flask 앱 시작 (Render에서 gunicorn 등으로 실행)
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000)) # Render는 보통 10000 포트 사용
    app.run(host='0.0.0.0', port=port)
