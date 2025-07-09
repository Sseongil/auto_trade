# modules/chat_id.py

from telegram import Bot
import sys
import os
from dotenv import load_dotenv
import asyncio # asyncio 모듈 임포트

load_dotenv() # .env 파일에서 환경 변수 로드

# Your Telegram Bot Token. Keep this secure!
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def get_telegram_chat_id(): # 함수를 async로 선언
    """
    Connects to the Telegram Bot API, retrieves recent updates, and prints
    the chat ID from any messages received.

    To use this:
    1. Make sure your bot is started (send /start to your bot on Telegram).
    2. Send a message to your bot.
    3. Run this script. The chat ID should appear in your console.
    """
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return None

    print("🚀 텔레그램 챗 ID 가져오기 시작...")
    print("👉 봇에게 메시지를 보내고 이 스크립트를 실행하면 챗 ID가 출력됩니다.")

    try:
        bot = Bot(token=TOKEN)
        # Fetch updates. timeout can be adjusted if you expect many updates.
        # await 키워드를 사용하여 비동기 함수 호출
        updates = await bot.get_updates(timeout=10) 

        if not updates:
            print("❌ 새로운 메시지를 찾을 수 없습니다. 봇에게 메시지를 보냈는지 확인하세요.")
            print("   (예: 텔레그램 봇에게 '안녕'이라고 메시지를 보낸 후 다시 실행)")
            return None

        found_ids = set() # Use a set to store unique chat IDs
        for update in updates:
            if update.message and update.message.chat:
                chat_id = update.message.chat.id
                if chat_id not in found_ids:
                    print(f"✅ 텔레그램 챗 ID: {chat_id} (이 ID를 설정 파일에 저장하세요)")
                    found_ids.add(chat_id)
        
        if not found_ids:
            print("❌ 메시지에서 챗 ID를 찾을 수 없습니다. 메시지가 텍스트 메시지인지 확인하세요.")
            
    except Exception as e:
        print(f"❌ 텔레그램 API 연결 또는 업데이트 가져오기 중 오류 발생: {e}")
        print("   (봇 토큰이 올바른지, 인터넷 연결이 안정적인지 확인하세요)")
    
    print("--- 텔레그램 챗 ID 가져오기 완료 ---")

if __name__ == "__main__":
    # asyncio.run()을 사용하여 비동기 함수 실행
    asyncio.run(get_telegram_chat_id())

