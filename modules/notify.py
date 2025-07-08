# modules/notify.py

import os
import requests
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv() # .env 파일에서 환경 변수 로드

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str):
    """
    텔레그램 봇을 통해 메시지를 전송합니다.
    TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID 환경 변수가 설정되어 있어야 합니다.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ 텔레그램 알림 설정이 완료되지 않았습니다 (TOKEN 또는 CHAT_ID 없음). 메시지를 전송할 수 없습니다.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"[Kiwoom AutoTrade]\n{message}",
        "parse_mode": "HTML" # HTML 태그를 사용하여 메시지 포맷팅 가능
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        # HTTP 상태 코드 확인 및 오류 발생 시 예외 발생
        response.raise_for_status() 
        logger.info(f"✅ 텔레그램 메시지 전송 성공: {message[:50]}...") # 메시지 일부만 로깅
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"❌ 텔레그램 응답 실패: HTTP {http_err.response.status_code}, 응답: {http_err.response.text}")
        # 텔레그램 API 자체 오류 메시지는 다시 텔레그램으로 보내지 않음 (무한 루프 방지)
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"❌ 텔레그램 메시지 전송 중 연결 오류 발생: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        logger.error(f"❌ 텔레그램 메시지 전송 중 타임아웃 오류 발생: {timeout_err}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ 텔레그램 메시지 전송 중 알 수 없는 요청 오류 발생: {e}")
    except Exception as e:
        logger.error(f"❌ 텔레그램 메시지 전송 중 예상치 못한 오류 발생: {e}")

if __name__ == '__main__':
    # 이 파일을 직접 실행하여 텔레그램 메시지 전송 테스트
    # .env 파일에 TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID를 설정 후 실행하세요.
    print("텔레그램 메시지 전송 테스트 중...")
    send_telegram_message("테스트 메시지입니다. 텔레그램 알림이 정상적으로 작동하는지 확인하세요.")
    print("테스트 완료. 텔레그램을 확인해주세요.")

