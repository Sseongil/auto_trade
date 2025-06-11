import os

# --- 텔레그램 알림 설정 ---
# ✅ 환경 변수에서 값 로드. 없으면 하드코딩된 기본값 사용 (보안상 환경 변수 사용 강력 권장)

# Render 대시보드의 'Environment' 탭에서 TELEGRAM_TOKEN 환경 변수를 설정해야 합니다.
# 예시: Key (키): TELEGRAM_TOKEN, Value (값): 여러분의 실제 텔레그램 봇 토큰 (예: 1234567890:ABCDEFGHIJKLMN_OPQRSTUVWXYZ)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE") # 텔레그램 봇 토큰

# Render 대시보드의 'Environment' 탭에서 TELEGRAM_CHAT_ID 환경 변수를 설정해야 합니다.
# 예시: Key (키): TELEGRAM_CHAT_ID, Value (값): 여러분의 실제 채팅 ID (예: 1866728370, 숫자로만 입력)
# 환경 변수가 설정되지 않았을 경우를 대비한 기본값은 '0' (문자열)으로 설정하고 int로 변환합니다.
TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0")) # 메시지를 받을 채팅 ID (개인 채팅 또는 그룹 채팅 ID)

# --- Kiwoom API 서버 설정 (Windows PC에서 실행될 서버) ---
# Render 대시보드의 'Environment' 탭에서 LOCAL_API_SERVER_URL 환경 변수를 설정해야 합니다.
# 이 값은 ngrok이 제공하는 PUBLIC URL (예: https://abcdefg.ngrok-free.app)이 되어야 합니다.
LOCAL_API_SERVER_URL = os.environ.get("LOCAL_API_SERVER_URL", "http://localhost:5001") # Windows PC의 로컬 API 서버 URL