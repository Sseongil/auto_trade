# modules/notify.py (FINAL REVIEWED CODE)

import requests
import logging
# config.py에서 TELEGRAM_TOKEN과 TELEGRAM_CHAT_ID를 가져옵니다.
# 주의: 이 값들은 config.py에서 정의되어야 합니다.
from modules.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

# 로깅 설정: 기본 로깅 설정은 애플리케이션 시작 시 한 번만 하는 것이 좋습니다.
# 여기서는 다른 모듈에서 이미 basicConfig가 설정되어 있을 경우, 핸들러를 추가하지 않도록 합니다.
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def send_telegram_message(message: str):
    """
    지정된 텔레그램 봇과 채팅 ID를 사용하여 메시지를 전송합니다.
    토큰과 채팅 ID는 config.py에서 로드됩니다.

    Args:
        message (str): 전송할 메시지 내용.
    """
    # 토큰 또는 채팅 ID가 설정되지 않았다면 메시지 전송 시도하지 않음
    # config.py에서 값을 가져올 때 None이나 빈 문자열일 수 있으므로 이를 확인합니다.
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ 텔레그램 토큰 또는 채팅 ID가 설정되지 않아 메시지를 보낼 수 없습니다. config.py 또는 관련 환경 변수를 확인하세요.")
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            # "parse_mode": "HTML" # HTML 파싱 모드 추가 (선택 사항: 메시지에 HTML 태그 사용 가능)
            # parse_mode를 지정하지 않으면 기본적으로 일반 텍스트로 처리됩니다.
            # HTML 태그를 메시지에 포함하고 싶다면 주석을 해제하세요.
        }
        response = requests.post(url, data=payload)
        
        # HTTP 응답 상태 코드 확인
        if response.status_code == 200:
            # logger.info("✅ 텔레그램 메시지 전송 성공") # 너무 많은 성공 로그는 스팸이 될 수 있으므로, 필요 시 주석 해제
            pass # 성공 메시지는 대부분의 경우 로깅하지 않아도 됨
        else:
            logger.error(f"❌ 텔레그램 메시지 전송 실패 (HTTP {response.status_code}): {response.text}")
    except requests.exceptions.RequestException as e:
        # requests 라이브러리 관련 네트워크 또는 HTTP 오류 처리
        logger.error(f"❌ 텔레그램 메시지 전송 중 네트워크/요청 오류 발생: {e}", exc_info=True) # 스택 트레이스 추가
    except Exception as e:
        # 그 외 예상치 못한 오류 처리
        logger.critical(f"🚨 텔레그램 메시지 전송 중 치명적인 예외 발생: {e}", exc_info=True) # 스택 트레이스 추가

# 이 모듈은 일반적으로 다른 파일에서 임포트하여 사용되므로
# __name__ == "__main__" 블록은 간단한 테스트용으로만 사용합니다.
if __name__ == "__main__":
    print("텔레그램 메시지 테스트를 시작합니다. config.py에 올바른 토큰과 채팅 ID가 설정되어 있어야 합니다.")
    # 경고: 실제 실행 시 config.py에서 TELEGRAM_TOKEN, TELEGRAM_CHAT_ID가 로드되지 않으면 테스트 실패
    # send_telegram_message 함수가 config에서 값을 가져오므로, 여기서는 직접 토큰/ID 설정이 필요 없습니다.
    send_telegram_message("🤖 텔레그램 봇 테스트 메시지입니다.")
    print("테스트 완료.")