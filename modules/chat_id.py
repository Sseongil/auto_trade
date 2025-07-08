# modules/chat_id.py


from telegram import Bot
import sys # Import sys for better error handling if needed, though not strictly used here

# Your Telegram Bot Token. Keep this secure!
# DO NOT hardcode sensitive tokens in production code or commit them to public repositories.
# For local testing, it's fine, but consider environment variables for deployment.
TOKEN = "8081086653:AAFbATaP5fUVOJztvPtxQWaMRF0WPEOkUqo"
# You can replace this with your actual chat ID once you get it:
# CHAT_ID = "1866728370" 

def get_telegram_chat_id():
    """
    Connects to the Telegram Bot API, retrieves recent updates, and prints
    the chat ID from any messages received.

    To use this:
    1. Make sure your bot is started (send /start to your bot on Telegram).
    2. Send a message to your bot.
    3. Run this script. The chat ID should appear in your console.
    """
    print("🚀 텔레그램 챗 ID 가져오기 시작...")
    print("👉 봇에게 메시지를 보내고 이 스크립트를 실행하면 챗 ID가 출력됩니다.")

    try:
        bot = Bot(token=TOKEN)
        # Fetch updates. timeout can be adjusted if you expect many updates.
        # last_update_id can be used to get only new updates.
        updates = bot.get_updates(timeout=10) 

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
    get_telegram_chat_id()