import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask, request, jsonify
import asyncio
import threading
from functools import wraps

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

# Global variables for bot application and event loop
bot_application = None
bot_loop = None
bot_thread = None

def run_async_in_thread(coro):
    """Helper function to run async coroutines in the bot's event loop"""
    if bot_loop is None:
        raise RuntimeError("Bot event loop not initialized")
    
    future = asyncio.run_coroutine_threadsafe(coro, bot_loop)
    return future.result(timeout=30)  # 30 second timeout

def init_bot():
    """Initialize the bot application in a separate thread"""
    global bot_application, bot_loop, bot_thread
    
    def bot_thread_func():
        global bot_loop
        # Create new event loop for this thread
        bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(bot_loop)
        
        async def setup_bot():
            global bot_application
            
            # Create and initialize the bot application
            bot_application = Application.builder().token(TOKEN).build()
            
            # Add command handlers
            bot_application.add_handler(CommandHandler("start", start))
            bot_application.add_handler(CommandHandler("mychatid", my_chat_id))
            
            # Initialize the application
            await bot_application.initialize()
            logger.info("Bot application initialized successfully")
            
            # Set webhook if URL is provided
            if WEBHOOK_URL:
                full_webhook_url = f"{WEBHOOK_URL}/telegram-webhook"
                logger.info(f"Setting webhook to: {full_webhook_url}")
                try:
                    await bot_application.bot.set_webhook(url=full_webhook_url, drop_pending_updates=True)
                    logger.info("Telegram webhook set successfully")
                except Exception as e:
                    logger.error(f"Failed to set webhook: {e}")
            
        # Run the setup and then keep the loop running
        bot_loop.run_until_complete(setup_bot())
        bot_loop.run_forever()
    
    # Start bot in separate thread
    bot_thread = threading.Thread(target=bot_thread_func, daemon=True)
    bot_thread.start()
    
    # Wait a moment for initialization
    import time
    time.sleep(2)
    
    if bot_application is None:
        raise RuntimeError("Failed to initialize bot application")
    
    logger.info("Bot initialization completed")

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

# --- Flask Routes ---

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    """Handles incoming Telegram updates via webhook."""
    if request.method == "POST":
        if bot_application is None:
            logger.error("Bot application not initialized")
            return "Bot not ready", 500
            
        try:
            update_json = request.get_json(force=True)
            update = Update.de_json(update_json, bot_application.bot)
            
            # Process the update in the bot's event loop
            run_async_in_thread(bot_application.process_update(update))
            
            logger.info("Received and processed update from Telegram")
            return "ok"
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return "Error", 500
    
    return "<h1>Telegram Webhook Endpoint - Listening for POST requests</h1>", 200

@app.route('/send_telegram_notification', methods=['POST'])
def send_telegram_notification():
    """
    API endpoint to send a Telegram message to a specified chat ID.
    Requires 'chat_id' and 'message' in the JSON request body.
    """
    if bot_application is None:
        return jsonify({"error": "Bot not ready"}), 500
        
    data = request.json
    chat_id = data.get('chat_id')
    message_text = data.get('message')

    if not chat_id or not message_text:
        return jsonify({"error": "Missing chat_id or message"}), 400

    try:
        run_async_in_thread(
            bot_application.bot.send_message(chat_id=chat_id, text=message_text)
        )
        
        logger.info(f"Successfully sent Telegram message to {chat_id}")
        return jsonify({"status": "Message sent"}), 200
    except Exception as e:
        logger.error(f"Error sending Telegram message to {chat_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    if bot_application is None:
        return jsonify({"status": "Bot not ready"}), 500
    return jsonify({"status": "OK", "bot_ready": True}), 200

# Initialize the bot when the module is imported
try:
    init_bot()
except Exception as e:
    logger.critical(f"Failed to initialize bot: {e}")
    # Don't raise here, let Flask start but bot won't work

if __name__ == "__main__":
    logger.info("Starting Flask API server for local development...")
    app.run(host='0.0.0.0', port=os.getenv("PORT", 5000), debug=False)