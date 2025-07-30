import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask, request, jsonify
import asyncio
import threading # Still useful if you need to run sync code in async context via run_coroutine_threadsafe

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set. The bot will not function.")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing.")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    logger.warning("WEBHOOK_URL environment variable not set. Webhook will not be set automatically.")
    logger.warning("You will need to manually set the webhook using Telegram Bot API if deploying.")

# Initialize Flask app
app = Flask(__name__)

# Initialize the Telegram Bot Application
# This needs to be done at the module level so it runs when Gunicorn imports the app.
bot_application = Application.builder().token(TOKEN).build()

# --- Telegram Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm your notification bot. "
        "Send /mychatid to get your unique Telegram Chat ID."
    )
    logger.info(f"User {user.id} started the bot.")

async def my_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the user's chat ID when the command /mychatid is issued."""
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name if update.effective_user.first_name else "User"

    response_message = (
        f"Hello {user_name}!\n\n"
        f"Your Telegram Chat ID is: `{chat_id}`\n\n"
        "Please copy this ID and use it for your notifications."
    )
    await update.message.reply_text(response_message, parse_mode='Markdown')
    logger.info(f"User {user_name} ({chat_id}) requested chat ID.")

# Register command handlers with the bot application
bot_application.add_handler(CommandHandler("start", start))
bot_application.add_handler(CommandHandler("mychatid", my_chat_id))

# --- Flask Webhook Endpoint ---

@app.route('/telegram-webhook', methods=['POST'])
async def telegram_webhook():
    """Handles incoming Telegram updates via webhook."""
    if request.method == "POST":
        update_json = request.get_json(force=True)
        update = Update.de_json(update_json, bot_application.bot)
        
        # Process the update using the bot application's dispatcher
        await bot_application.process_update(update)
        
        logger.info(f"Received and processed update from Telegram.")
        return "ok"
    
    return "<h1>Telegram Webhook Endpoint - Listening for POST requests</h1>", 200

# --- Optional: API Endpoint for Sending Notifications ---
@app.route('/send_telegram_notification', methods=['POST'])
def send_telegram_notification():
    """
    API endpoint to send a Telegram message to a specified chat ID.
    Requires 'chat_id' and 'message' in the JSON request body.
    """
    data = request.json
    chat_id = data.get('chat_id')
    message_text = data.get('message')

    if not chat_id or not message_text:
        return jsonify({"error": "Missing chat_id or message"}), 400

    try:
        asyncio.run_coroutine_threadsafe(
            bot_application.bot.send_message(chat_id=chat_id, text=message_text),
            bot_application.loop
        ).result() 

        logger.info(f"Successfully sent Telegram message to {chat_id}")
        return jsonify({"status": "Message sent"}), 200
    except Exception as e:
        logger.error(f"Error sending Telegram message to {chat_id}: {e}")
        return jsonify({"error": str(e)}), 500

# --- Webhook Setup Function ---

async def set_telegram_webhook_async():
    """
    Asynchronously sets the Telegram webhook URL for the bot.
    This function is called once during application startup.
    """
    if WEBHOOK_URL:
        full_webhook_url = f"{WEBHOOK_URL}/telegram-webhook"
        logger.info(f"Attempting to set webhook to: {full_webhook_url}")
        try:
            await bot_application.bot.set_webhook(url=full_webhook_url, drop_pending_updates=True)
            logger.info("Telegram webhook set successfully.")
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}")
            raise # Re-raise to indicate a critical startup failure
    else:
        logger.warning("WEBHOOK_URL environment variable not set. Webhook will not be set automatically.")
        logger.warning("Manual webhook setup might be required or the bot will not receive updates.")

# --- Initialization Code (Runs when module is imported by Gunicorn) ---
# Initialize the bot application's internal structures, including its event loop.
# This must be called BEFORE any `process_update` or other bot-related async calls.
try:
    bot_application.initialize()
    # Set the webhook. This needs to be run in the event loop.
    # We get the current event loop and run the async function.
    # For Gunicorn, this will happen once when the worker process starts.
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_telegram_webhook_async())
except Exception as e:
    logger.critical(f"Critical error during bot initialization or webhook setup: {e}. "
                    "The application might not function correctly.")
    # In a production environment, you might want to exit here if this is a fatal error.
    # For now, we'll log and allow the Flask app to start, but it might not work.
    # raise # Uncomment this to make the app fail to start if init fails

# --- Main Application Entry Point (Only for local development) ---
if __name__ == "__main__":
    logger.info("Starting Flask API server for local development...")
    # For local testing, app.run() is fine.
    # When deploying with Gunicorn, Gunicorn will handle the server part.
    app.run(host='0.0.0.0', port=os.getenv("PORT", 5000), debug=False)

