# delete_webhook.py

import os
import asyncio
from telegram import Bot
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# 텔레그램 봇 토큰 가져오기
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def delete_telegram_webhook():
    """
    텔레그램 봇의 현재 웹훅을 강제로 삭제합니다.
    """
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return

    print("� 텔레그램 웹훅 삭제 시도 중...")
    try:
        bot = Bot(token=TOKEN)
        # 웹훅 URL을 빈 문자열로 설정하여 웹훅을 삭제합니다.
        await bot.setWebhook(url="")
        print("✅ 텔레그램 웹훅이 성공적으로 삭제되었습니다.")
    except Exception as e:
        print(f"❌ 텔레그램 웹훅 삭제 중 오류 발생: {e}")
        print("   (봇 토큰이 올바른지, 인터넷 연결이 안정적인지 확인하세요)")

if __name__ == "__main__":
    asyncio.run(delete_telegram_webhook())
