
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask, request, jsonify 
import asyncio
import threading


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_FALLBACK_DEV_TOKEN") 
if TOKEN == "YOUR_FALLBACK_DEV_TOKEN":
    logger.warning("TELEGRAM_BOT_TOKEN environment variable not set. Using fallback token. This is NOT recommended for production.")


app = Flask(__name__)


bot_application = Application.builder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm your notification bot. "
        "Send /mychatid to get your unique Telegram Chat ID."
    )

async def my_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name if update.effective_user.first_name else "User"

    response_message = (
        f"Hello {user_name}!\n\n"
        f"Your Telegram Chat ID is: `{chat_id}`\n\n"
        "Please copy this ID and paste it into the 'Telegram Notifications' section "
        "on the TempWallets website to enable transaction notifications."
    )
    await update.message.reply_text(response_message, parse_mode='Markdown')

# API Endpoint for sending notifications
@app.route('/send_telegram_notification', methods=['POST'])
def send_telegram_notification():
    data = request.json
    chat_id = data.get('chat_id')
    message_text = data.get('message')

    if not chat_id or not message_text:
        return jsonify({"error": "Missing chat_id or message"}), 400

    try:
        asyncio.run_coroutine_threadsafe(
            bot_application.bot.send_message(chat_id=chat_id, text=message_text),
            bot_application.loop
        )
        logger.info(f"Successfully triggered Telegram message to {chat_id}")
        return jsonify({"status": "Message queued for sending"}), 200
    except Exception as e:
        logger.error(f"Error triggering Telegram message to {chat_id}: {e}")
        return jsonify({"error": str(e)}), 500

def run_bot_polling():
    logger.info("Starting Telegram bot polling...")
    bot_application.add_handler(CommandHandler("start", start))
    bot_application.add_handler(CommandHandler("mychatid", my_chat_id))
    bot_application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Telegram bot polling stopped.")

if __name__ == "__main__":
    bot_application.initialize()
    bot_application.updater.bot.set_webhook() 
    bot_thread = threading.Thread(target=run_bot_polling, daemon=True) 
    bot_thread.start()

    logger.info("Starting Flask API server...")
    app.run(host='0.0.0.0', port=5000, debug=False) 