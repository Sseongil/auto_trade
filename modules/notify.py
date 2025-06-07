# modules/notify.py
import requests

# 사용자 토큰과 챗 ID 입력
TOKEN = "8061227011:AAEYXF-09PBwRTgVbNhhOpjflGg5_vrPMW8"
CHAT_ID = "-4852020723"

def send_telegram_message(message: str):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message
        }
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("✅ 텔레그램 전송 성공")
        else:
            print(f"❌ 텔레그램 전송 실패: {response.text}")
    except Exception as e:
        print(f"[에러] 텔레그램 메시지 전송 실패: {e}")
