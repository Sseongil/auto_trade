import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from modules.common.config import get_env
from modules.portfolio_manager import get_account_status, get_positions, get_cash_balance
from modules.trade_logger import get_today_trades, get_all_trades
from modules.trade_analyzer import analyze_trades

logger = logging.getLogger(__name__)

async def check_auth(update: Update) -> bool:
    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        await update.message.reply_text("🚫 권한이 없습니다.")
        return False
    return True

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    status_info = get_account_status()
    await update.message.reply_text(status_info)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    cash = get_cash_balance()
    await update.message.reply_text(f"💰 예수금: {cash:,}원")

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    pos = get_positions()
    await update.message.reply_text(pos)

async def log_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    trades = get_today_trades()
    await update.message.reply_text(trades)

async def log_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    file_path = get_all_trades()
    await update.message.reply_document(document=open(file_path, "rb"))

async def analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    result = analyze_trades()
    await update.message.reply_text(result)

def start_telegram_bot(kiwoom_api_caller):
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("잔고", positions))
    app.add_handler(CommandHandler("예수금", balance))
    app.add_handler(CommandHandler("log_today", log_today))
    app.add_handler(CommandHandler("log_all", log_all))
    app.add_handler(CommandHandler("analysis", analysis))

    logger.info("🤖 텔레그램 봇 시작")
    app.run_polling()
