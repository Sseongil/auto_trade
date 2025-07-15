# server.py
# Render 서버에 배포될 Flask 애플리케이션

import os
import logging
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

# modules.notify에서 send_telegram_message 함수 임포트
# Render 서버에서는 로컬 notify.py를 직접 임포트할 수 없으므로,
# send_telegram_message는 이 파일 내에서 직접 구현하거나,
# Render 환경에서 사용 가능한 방식으로 재정의해야 합니다.
# 여기서는 notify.py의 send_telegram_message와 동일한 기능을 수행하도록 직접 구현합니다.

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

# 내부 API 키 (로컬 서버에서 ngrok URL 업데이트 요청 시 사용될 키)
# Render 환경 변수에 INTERNAL_API_KEY로 설정되어 있어야 함
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY")
if not INTERNAL_API_KEY:
    logger.critical("❌ Render 서버: INTERNAL_API_KEY 환경 변수 미설정!")

# --- 헬퍼 함수: 텔레그램 메시지 전송 (Render 서버용) ---
def send_telegram_message_for_render(message: str):
    """
    Render 서버에서 텔레그램 봇을 통해 메시지를 전송합니다.
    TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID 환경 변수가 설정되어 있어야 합니다.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ 텔레그램 알림 설정이 완료되지 않았습니다 (TOKEN 또는 CHAT_ID 없음). 메시지를 전송할 수 없습니다.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"[Kiwoom AutoTrade - Render]\n{message}", # Render 서버에서 보낸 메시지임을 명시
        "parse_mode": "HTML" # HTML 태그를 사용하여 메시지 포맷팅 가능
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status() 
        logger.info(f"✅ 텔레그램 메시지 전송 성공 (Render): {message[:50]}...")
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"❌ 텔레그램 응답 실패 (Render): HTTP {http_err.response.status_code}, 응답: {http_err.response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"❌ 텔레그램 메시지 전송 중 연결 오류 발생 (Render): {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        logger.error(f"❌ 텔레그램 메시지 전송 중 타임아웃 오류 발생 (Render): {timeout_err}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ 텔레그램 메시지 전송 중 알 수 없는 요청 오류 발생 (Render): {e}")
    except Exception as e:
        logger.error(f"❌ 텔레그램 메시지 전송 중 예상치 못한 오류 발생 (Render): {e}")


# --- Render 서버 엔드포인트 ---

@app.route('/')
def home():
    return "Render Backend Server is running and ready for Telegram webhooks!"

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    """
    텔레그램 봇으로부터 메시지를 수신하는 웹훅 엔드포인트.
    """
    logger.debug("Received request on /telegram_webhook.") # ✅ Debug log
    if not request.is_json:
        logger.warning("⚠️ Webhook: Request is not JSON.")
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    update = request.get_json() # Use get_json() for incoming JSON
    logger.info(f"Received Telegram update: {update}")

    # 텔레그램 메시지 파싱
    message = update.get('message', {}) # get message from the update
    chat_id = message.get('chat', {}).get('id')
    text = message.get('text', '')

    logger.debug(f"Parsed chat_id: {chat_id}, text: {text}") # ✅ Debug log

    if chat_id and text:
        logger.info(f"Telegram message from {chat_id}: {text}")

        # TELEGRAM_CHAT_ID를 환경 변수에서 직접 가져옴
        telegram_chat_id_from_env = os.environ.get("TELEGRAM_CHAT_ID")
        logger.debug(f"TELEGRAM_CHAT_ID from env: {telegram_chat_id_from_env}") # ✅ Debug log

        if text == '/status':
            logger.debug(f"'/status' command received. Comparing chat_id: {str(chat_id)} vs {telegram_chat_id_from_env}") # ✅ Debug log
            # 텔레그램 채팅 ID가 설정된 ID와 일치하는지 확인 (보안 강화)
            if str(chat_id) != telegram_chat_id_from_env:
                send_telegram_message_for_render(f"🚨 경고: 알 수 없는 사용자({chat_id})로부터 /status 명령 수신. 허용되지 않은 접근.")
                logger.warning(f"Unauthorized /status command from chat_id: {chat_id}")
                return jsonify({"status": "unauthorized"}), 200 # Unauthorized 응답이지만 텔레그램에는 OK
                
            # NGROK_PUBLIC_URL을 환경 변수에서 직접 읽어옴
            NGROK_PUBLIC_URL_FROM_ENV = os.environ.get("LOCAL_API_SERVER_URL")
            logger.debug(f"LOCAL_API_SERVER_URL from env: {NGROK_PUBLIC_URL_FROM_ENV}") # ✅ Debug log

            if NGROK_PUBLIC_URL_FROM_ENV and NGROK_PUBLIC_URL_FROM_ENV != "N/A":
                # 로컬 API 서버의 /status 엔드포인트 호출
                local_status_url = f"{NGROK_PUBLIC_URL_FROM_ENV.rstrip('/')}/status"
                try:
                    logger.info(f"Fetching status from local API: {local_status_url}")
                    # Render 서버가 로컬 서버에 요청할 때 사용하는 API 키
                    headers = {'X-API-Key': os.environ.get("LOCAL_API_KEY", "")} 
                    logger.debug(f"Headers for local API call: {headers}") # ✅ Debug log
                    response = requests.get(local_status_url, headers=headers, timeout=10)
                    response.raise_for_status()
                    status_data = response.json()
                    logger.debug(f"Status data received from local API: {status_data}") # ✅ Debug log
                    
                    # 상태 정보를 보기 좋게 포맷팅하여 텔레그램으로 전송
                    status_message = (
                        f"📊 *자동 매매 시스템 상태:*\n"
                        f"▪️ 상태: `{status_data.get('status', 'N/A')}`\n"
                        f"▪️ 서버 시간: `{status_data.get('server_time', 'N/A')}`\n"
                        f"▪️ 계좌 번호: `{status_data.get('account_number', 'N/A')}`\n"
                        f"▪️ 예수금: `{status_data.get('balance', 0):,} KRW`\n"
                        f"▪️ 마지막 업데이트: `{status_data.get('last_kiwoom_update', 'N/A')}`\n"
                        f"▪️ 조건 검색 활성화: `{'✅' if status_data.get('condition_check_enabled') else '❌'}`\n"
                        f"▪️ 매수 전략 활성화: `{'✅' if status_data.get('buy_strategy_enabled') else '❌'}`\n"
                        f"▪️ 익절/손절 전략 활성화: `{'✅' if status_data.get('exit_strategy_enabled') else '❌'}`\n"
                        f"▪️ 현재 조건식: `{status_data.get('real_condition_name', '없음')}`\n"
                        f"▪️ ngrok URL: `{status_data.get('ngrok_url', 'N/A')}`\n"
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

                    send_telegram_message_for_render(status_message)

                except requests.exceptions.RequestException as e:
                    error_msg = f"❌ 로컬 API 서버 상태 조회 실패 (Render): {e}"
                    logger.error(error_msg, exc_info=True)
                    send_telegram_message_for_render(f"🚨 로컬 API 서버 상태 조회 실패: `{e}`. ngrok이 실행 중인지, 로컬 서버가 작동하는지 확인하세요.")
                except Exception as e:
                    error_msg = f"❌ 상태 메시지 처리 중 예기치 않은 오류 (Render): {e}"
                    logger.error(error_msg, exc_info=True)
                    send_telegram_message_for_render(f"🚨 상태 메시지 처리 중 오류: `{e}`")
            else:
                send_telegram_message_for_render("⚠️ Ngrok URL이 아직 Render 서버에 등록되지 않았습니다.")
                logger.warning("Ngrok URL not set on Render server.")
        else:
            # 다른 메시지는 무시하거나 기본 응답 제공
            pass 

    return jsonify({"status": "ok"}), 200 # 텔레그램에 200 OK 응답

# Flask 앱 시작 (Render에서 gunicorn 등으로 실행)
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000)) # Render는 보통 10000 포트 사용
    app.run(host='0.0.0.0', port=port)

