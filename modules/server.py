# modules/server.py
import os
import sys
import json
import logging
import asyncio
import requests

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- 초기 설정 ---
load_dotenv()
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import modules.common.config as config
from modules.common.config import get_env

# --- 로깅 설정 ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Flask 앱 ---
app = Flask(__name__)

# --- 환경 변수 로딩 및 검증 ---
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_env("TELEGRAM_CHAT_ID")
LOCAL_API_KEY_FOR_REQUEST = get_env("LOCAL_API_KEY")
INTERNAL_API_KEY = get_env("INTERNAL_API_KEY") # 내부용 API 키

# 필수 환경 변수 검증 강화
missing_env_vars = []
if not TELEGRAM_BOT_TOKEN: missing_env_vars.append("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_CHAT_ID: missing_env_vars.append("TELEGRAM_CHAT_ID")
if not LOCAL_API_KEY_FOR_REQUEST: missing_env_vars.append("LOCAL_API_KEY") # 로컬 API 서버로 요청 보낼 때 사용

if missing_env_vars:
    logger.critical(f"❌ 필수 환경 변수 누락: {', '.join(missing_env_vars)}. 서버를 종료합니다.")
    sys.exit(1)

# INTERNAL_API_KEY는 필수가 아닐 수 있음 (없으면 데코레이터에서 경고만)
if not INTERNAL_API_KEY:
    logger.warning("⚠️ INTERNAL_API_KEY 환경 변수가 설정되지 않았습니다. /update_ngrok_internal 엔드포인트가 보호되지 않습니다.")


# Telegram Application Builder
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# --- 내부 인증 데코레이터 ---
def internal_api_key_required(f):
    """내부 API 키가 요청 헤더에 포함되어 있는지 확인하는 데코레이터"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        # INTERNAL_API_KEY가 설정되지 않았다면 인증 건너뛰기 (경고는 위에 이미 출력됨)
        if not INTERNAL_API_KEY:
            return f(*args, **kwargs)

        key = request.headers.get('X-Internal-API-Key')
        if not key or key != INTERNAL_API_KEY: # 키가 없거나 일치하지 않을 때 모두 차단
            logger.warning(f"❌ 내부 API 인증 실패: 잘못된 또는 누락된 Internal API Key. 요청 IP: {request.remote_addr}")
            return jsonify({"status": "error", "message": "Unauthorized: Invalid or missing Internal API Key"}), 401
        return f(*args, **kwargs)
    return decorated

# --- 유틸리티 함수 ---
def is_valid_url(url: str) -> bool:
    """URL 형식이 유효한지 검사합니다."""
    # 간단한 http/https 시작 검사
    return url.startswith("http://") or url.startswith("https://")

# --- Flask 엔드포인트 ---
@app.route('/')
def home():
    return "Telegram Bot Server is running!"

@app.route('/health')
def health_check():
    """Render 헬스 체크용 엔드포인트."""
    return jsonify({"status": "ok", "message": "Bot server is healthy"}), 200

@app.route('/update_ngrok_internal', methods=["POST"])
@internal_api_key_required
def update_ngrok_internal():
    """ngrok URL을 자동으로 업데이트하는 내부 엔드포인트."""
    try:
        data = request.get_json()
        new_url = data.get("new_url", "").strip()

        if not is_valid_url(new_url):
            logger.warning(f"수신된 ngrok URL 형식 오류: {new_url}")
            return jsonify({"status": "error", "message": "Invalid URL format"}), 400
        
        # 이미 최신 URL인 경우 불필요한 업데이트 방지 및 알림
        if config.LOCAL_API_SERVER_URL == new_url:
            logger.info(f"✅ ngrok URL이 이미 최신 상태입니다: {new_url}")
            return jsonify({"status": "ok", "message": "ngrok URL is already up to date"}), 200

        config.LOCAL_API_SERVER_URL = new_url
        logger.info(f"✅ ngrok URL이 성공적으로 업데이트됨: {new_url}")
        
        # 텔레그램으로 알림 (선택 사항, 필요 시 활성화)
        # try:
        #     asyncio.run_coroutine_threadsafe(
        #         application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ 로컬 API URL 자동 업데이트:\n`{new_url}`", parse_mode='MarkdownV2'),
        #         application.loop # 봇의 이벤트 루프 사용
        #     )
        # except Exception as send_e:
        #     logger.warning(f"텔레그램 자동 업데이트 알림 실패: {send_e}")

        return jsonify({"status": "ok", "message": "ngrok URL updated"}), 200
    except Exception as e:
        logger.exception("❌ /update_ngrok_internal 처리 중 오류 발생:") # 예외 스택 트레이스 출력
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

@app.route('/telegram', methods=["POST"])
async def telegram_webhook():
    """Telegram Webhook을 처리합니다."""
    if request.method == "POST":
        try:
            update = Update.de_json(request.get_json(), application.bot)
            await application.process_update(update)
            logger.info(f"Telegram update 처리됨: {update.update_id}")
        except Exception as e:
            logger.error(f"❌ Telegram 업데이트 처리 중 오류: {e}", exc_info=True)
        return "ok"
    return "Method Not Allowed", 405 # POST가 아닌 요청에 대한 처리

# --- Telegram 봇 명령어 유틸 ---
async def check_chat_permission(update: Update) -> bool:
    """채팅 권한을 확인하고, 권한이 없으면 메시지를 보냅니다."""
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        logger.warning(f"❌ 권한 없는 채팅 접근 차단: Chat ID {update.effective_chat.id} (요청 유저: {update.effective_user.id})")
        await update.message.reply_text("⛔️ 이 봇은 특정 사용자/채팅에서만 사용 가능합니다.")
        return False
    return True

# --- Telegram 명령어 핸들러들 ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start 및 /help 명령 처리."""
    if not await check_chat_permission(update): return
    user_mention = update.effective_user.mention_html() if update.effective_user else "사용자"
    await update.message.reply_html(
        f"👋 안녕하세요, {user_mention}님! 주식 자동매매 봇입니다.\n"
        "다음 명령어를 사용해 보세요:\n"
        "/status - 로컬 API 서버 상태 및 계좌 정보 조회\n"
        "/buy [종목코드] [수량] [가격] - 주식 매수 (가격은 선택사항, 없으면 시장가)\n"
        "/sell [종목코드] [수량] [가격] - 주식 매도 (가격은 선택사항, 없으면 시장가)\n"
        "/update_ngrok [URL] - 새로운 ngrok URL로 수동 업데이트"
    )
    logger.info(f"Received /start or /help from {update.effective_user.id}")


async def update_ngrok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """수동으로 ngrok URL을 업데이트합니다."""
    if not await check_chat_permission(update): return
    
    args = context.args
    if not args or len(args) != 1:
        await update.message.reply_text("❌ 사용법: `/update_ngrok [새로운 ngrok URL]`\n예시: `/update_ngrok https://abcd.ngrok-free.app`", parse_mode='MarkdownV2')
        return

    new_url = args[0].strip()
    if not is_valid_url(new_url):
        await update.message.reply_text("❌ 유효한 URL 형식이 아닙니다. `http://` 또는 `https://`로 시작해야 합니다.")
        return
    
    if config.LOCAL_API_SERVER_URL == new_url:
        await update.message.reply_text(f"✅ 로컬 API 서버 URL이 이미 최신 상태입니다:\n`{new_url}`", parse_mode='MarkdownV2')
        logger.info(f"Manual ngrok URL update - already up to date: {new_url}")
        return

    config.LOCAL_API_SERVER_URL = new_url
    await update.message.reply_text(f"✅ 로컬 API 서버 URL이 `{new_url}` (으)로 수동 업데이트되었습니다.")
    logger.info(f"Local API server URL manually updated to: {new_url}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """로컬 API 서버의 상태를 요청하고 응답합니다."""
    if not await check_chat_permission(update): return
    
    current_url = config.LOCAL_API_SERVER_URL
    if not is_valid_url(current_url):
        await update.message.reply_text("❌ 로컬 API 서버 URL이 설정되지 않았습니다. `/update_ngrok [URL]` 명령으로 설정해주세요.")
        return

    await update.message.reply_text("로컬 API 서버 상태를 조회 중입니다...")
    logger.info(f"Calling local API server status: {current_url}/status")

    try:
        resp = requests.get(f"{current_url}/status", headers={'X-API-Key': LOCAL_API_KEY_FOR_REQUEST}, timeout=10)
        resp.raise_for_status() # HTTP 오류(4xx, 5xx) 발생 시 예외
        data = resp.json()

        if data.get("status") == "ok":
            positions = data.get("positions", [])
            
            message = (
                "✅ *로컬 API 서버 상태: OK*\n"
                f"🔗 연결된 URL: `{current_url}`\n"
                f"🕒 서버 시간: `{data.get('server_time', 'N/A')}`\n"
                f"📊 키움 연결 상태: {'연결됨' if data.get('kiwoom_connected') else '연결 끊김'}\n"
                f"💳 계좌 번호: `{data.get('account_number', 'N/A')}`\n"
                f"💰 예수금: `{data.get('balance', 0):,}`원\n"
                f"📈 총 평가 자산: `{data.get('total_asset', 0):,}`원\n\n"
            )

            if positions:
                message += "*보유 종목:*\n"
                for pos in positions:
                    # 마크다운V2에서 특수 문자 이스케이프 처리
                    stock_name = str(pos.get('종목명', 'N/A')).replace('.', '\.').replace('-', '\-').replace('(', '\(').replace(')', '\)').replace('!', '\!')
                    stock_code = str(pos.get('종목코드', 'N/A')).replace('.', '\.').replace('-', '\-').replace('(', '\(').replace(')', '\)')
                    quantity = str(pos.get('보유수량', 0))
                    profit_loss = str(f"{pos.get('평가손익', 0):,}")
                    
                    message += (
                        f" - `{stock_name}` \(`{stock_code}`\): "
                        f"{quantity}주, 평가손익: {profit_loss}원\n"
                    )
            else:
                message += "*보유 종목: 없음*\n"
            
            await update.message.reply_markdown_v2(message)
            logger.info("Status information sent to Telegram.")
        else:
            await update.message.reply_text(f"❌ 로컬 API 서버 오류: {data.get('message', '알 수 없는 오류')}")
            logger.error(f"Local API server returned error status: {data}")

    except requests.exceptions.Timeout:
        await update.message.reply_text("❌ 로컬 API 서버 응답 시간 초과. 서버가 실행 중인지 확인하세요.")
        logger.error("Local API server request timed out.")
    except requests.exceptions.ConnectionError:
        await update.message.reply_text("❌ 로컬 API 서버에 연결할 수 없습니다. 서버가 실행 중이거나 ngrok 터널이 활성화되었는지 확인하세요.")
        logger.error("Could not connect to local API server.")
    except requests.exceptions.HTTPError as http_err:
        if http_err.response.status_code == 401:
            await update.message.reply_text("❌ 인증 실패: 로컬 API 서버에 접근 권한이 없습니다. API 키를 확인해주세요.")
            logger.error(f"Unauthorized access to local API server: {http_err}")
        else:
            await update.message.reply_text(f"❌ 로컬 API 서버 HTTP 오류 발생: {http_err} - {http_err.response.text}")
            logger.error(f"HTTP error from local API server: {http_err}", exc_info=True)
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"❌ 로컬 API 서버 요청 중 오류 발생: {e}")
        logger.error(f"Request to local API server failed: {e}", exc_info=True)
    except Exception as e:
        await update.message.reply_text(f"❌ 상태 조회 중 알 수 없는 오류 발생: {e}")
        logger.error(f"Unknown error during status command: {e}", exc_info=True)


async def process_trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE, trade_type: str):
    """매수/매도 명령을 처리하는 범용 함수."""
    if not await check_chat_permission(update): return

    trade_type_ko = "매수" if trade_type == "buy" else "매도"
    
    try:
        args = context.args
        if not (2 <= len(args) <= 3):
            await update.message.reply_markdown_v2(f"❌ 사용법: `/{trade_type} [종목코드] [수량] [가격(선택)]`\n예시: `/{trade_type} 005930 10 70000` (지정가)\n예시: `/{trade_type} 005930 5` (시장가)")
            return
        
        stock_code = args[0].strip()
        if not stock_code.isdigit() or len(stock_code) != 6:
            await update.message.reply_markdown_v2("❌ 종목코드는 6자리 숫자여야 합니다.")
            return

        quantity = int(args[1])
        if quantity <= 0:
            await update.message.reply_text("❌ 수량은 0보다 큰 정수여야 합니다.")
            return
        
        price = 0 # 시장가 기본값
        order_type = "시장가"
        if len(args) == 3:
            price = int(args[2])
            if price < 0:
                await update.message.reply_text("❌ 가격은 음수일 수 없습니다.")
                return
            order_type = "지정가"

        # 로컬 API 서버 URL 검증
        current_url = config.LOCAL_API_SERVER_URL
        if not is_valid_url(current_url):
            await update.message.reply_text("❌ 로컬 API 서버 URL이 설정되지 않았습니다. `/update_ngrok [URL]` 명령으로 설정해주세요.")
            return

        payload = {
            "stock_code": stock_code,
            "quantity": quantity,
            "price": price,
            "order_type": order_type
        }

        await update.message.reply_text(f"{trade_type_ko} 주문 요청 중: 종목코드 `{stock_code}`, 수량 `{quantity}`개, 가격 `{price if price > 0 else '시장가'}`")
        logger.info(f"Sending {trade_type} order to local API: {payload}")

        resp = requests.post(f"{current_url}/{trade_type}", json=payload, headers={'X-API-Key': LOCAL_API_KEY_FOR_REQUEST}, timeout=15) # 타임아웃 15초로 늘림
        resp.raise_for_status()
        result = resp.json()

        if result.get("status") == "success" or result.get("status") == "ok":
            await update.message.reply_text(f"✅ {trade_type_ko} 성공: {result.get('message', '주문 완료')}\n상세: {result.get('result', 'N/A')}")
            logger.info(f"{trade_type_ko} order successful: {result}")
        else:
            await update.message.reply_text(f"❌ {trade_type_ko} 실패: {result.get('message', '알 수 없는 오류')}")
            logger.error(f"{trade_type_ko} order failed: {result}")

    except ValueError as ve:
        # 유효성 검사 실패 시 구체적인 메시지 출력
        await update.message.reply_markdown_v2(f"❌ 입력 오류: {ve}")
        logger.warning(f"Trade command validation error: {ve}")
    except requests.exceptions.Timeout:
        await update.message.reply_text(f"❌ 로컬 API 서버 응답 시간 초과. 서버가 실행 중인지 확인하세요.")
        logger.error(f"{trade_type_ko} order request timed out.")
    except requests.exceptions.ConnectionError:
        await update.message.reply_text(f"❌ 로컬 API 서버에 연결할 수 없습니다. 서버가 실행 중이거나 ngrok 터널이 활성화되었는지 확인하세요.")
        logger.error(f"Could not connect to local API server for {trade_type_ko} order.")
    except requests.exceptions.HTTPError as http_err:
        if http_err.response.status_code == 401:
            await update.message.reply_text(f"❌ 인증 실패: 로컬 API 서버 접근 권한 없음. API 키를 확인해주세요.")
            logger.error(f"Unauthorized access to local API server for {trade_type_ko}: {http_err}")
        else:
            await update.message.reply_text(f"❌ 로컬 API 서버 HTTP 오류: {http_err} - {http_err.response.text}")
            logger.error(f"HTTP error from local API server for {trade_type_ko}: {http_err}", exc_info=True)
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"❌ {trade_type_ko} 주문 요청 중 오류: {e}")
        logger.error(f"Request to local API server for {trade_type_ko} order failed: {e}", exc_info=True)
    except Exception as e:
        await update.message.reply_text(f"❌ {trade_type_ko} 주문 중 알 수 없는 오류: {e}")
        logger.error(f"Unknown error during {trade_type_ko} command: {e}", exc_info=True)


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/buy 명령어 핸들러."""
    await process_trade_command(update, context, "buy")

async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sell 명령어 핸들러."""
    await process_trade_command(update, context, "sell")


# --- 핸들러 등록 ---
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", start_command)) # /help도 /start와 동일하게 처리
application.add_handler(CommandHandler("status", status_command))
application.add_handler(CommandHandler("buy", buy_command))
application.add_handler(CommandHandler("sell", sell_command))
application.add_handler(CommandHandler("update_ngrok", update_ngrok_command))

# 명령어 외의 모든 텍스트 메시지에 대한 응답
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start_command))


# --- 서버 실행 ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Flask 앱 실행 중 ( Render용 ): http://0.0.0.0:{port}")
    # Render는 WSGI 서버(gunicorn 등)를 사용하므로, app.run()은 로컬 테스트용.
    # use_reloader=False는 개발 중 파일 변경 시 앱 재시작을 막아 Kiwoom API 등과의 충돌 방지.
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)