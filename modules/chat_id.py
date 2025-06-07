from telegram import Bot

TOKEN = "8081086653:AAFbATaP5fUVOJztvPtxQWaMRF0WPEOkUqo"

bot = Bot(token=TOKEN)
updates = bot.get_updates()

for update in updates:
    print(update.message.chat.id)
