# modules/notify.py

import requests
import logging
# config.py에서 TELEGRAM_TOKEN과 TELEGRAM_CHAT_ID를 가져옵니다.
from modules.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

# 로깅 설정
logger = logging.getLogger(__name__)

def send_telegram_message(message: str):
    """
    지정된 텔레그램 봇과 채팅 ID를 사용하여 메시지를 전송합니다.
    토큰과 채팅 ID는 config.py에서 환경 변수를 통해 로드됩니다.

    Args:
        message (str): 전송할 메시지 내용.
    """
    # 토큰 또는 채팅 ID가 설정되지 않았다면 메시지 전송 시도하지 않음
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ 텔레그램 토큰 또는 채팅 ID가 설정되지 않아 메시지를 보낼 수 없습니다. .env 파일을 확인하세요.")
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }
        response = requests.post(url, data=payload)
        
        # HTTP 응답 상태 코드 확인
        if response.status_code == 200:
            logger.info("✅ 텔레그램 메시지 전송 성공")
        else:
            logger.error(f"❌ 텔레그램 메시지 전송 실패 (HTTP {response.status_code}): {response.text}")
    except requests.exceptions.RequestException as e:
        # requests 라이브러리 관련 네트워크 또는 HTTP 오류 처리
        logger.error(f"❌ 텔레그램 메시지 전송 중 네트워크/요청 오류 발생: {e}")
    except Exception as e:
        # 그 외 예상치 못한 오류 처리
        logger.critical(f"🚨 텔레그램 메시지 전송 중 치명적인 예외 발생: {e}", exc_info=True)

# 이 모듈은 일반적으로 다른 파일에서 임포트하여 사용되므로
# __name__ == "__main__" 블록은 간단한 테스트용으로만 사용합니다.
if __name__ == "__main__":
    # 실제 환경 변수가 설정되어 있지 않으면 이 테스트는 실패할 수 있습니다.
    # 테스트 목적으로는 config.py 또는 .env 파일을 로드하는 코드를 추가할 수 있습니다.
    print("텔레그램 메시지 테스트를 시작합니다. .env에 올바른 토큰과 채팅 ID가 설정되어 있어야 합니다.")
    send_telegram_message("🤖 텔레그램 봇 테스트 메시지입니다.")
    print("테스트 완료.")