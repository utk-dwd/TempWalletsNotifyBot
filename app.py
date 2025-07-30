import logging
import os
import asyncio
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set.")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing.")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Initialize Flask app
app = Flask(__name__)

# Global bot instance
bot = Bot(TOKEN)
application = None

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

def setup_application():
    """Setup the telegram application"""
    global application
    
    if application is None:
        application = Application.builder().token(TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("mychatid", my_chat_id))
        
        logger.info("Application setup complete")
    
    return application

def run_async(coro):
    """Run async function in a new event loop"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Error running async function: {e}")
        raise

# --- Flask Routes ---
@app.route('/')
def home():
    """Simple home route"""
    return jsonify({
        "status": "Bot is running",
        "webhook_url": f"{request.url_root}telegram-webhook" if request.url_root else "Not set"
    })

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    """Handles incoming Telegram updates via webhook."""
    try:
        # Setup application if not already done
        app_instance = setup_application()
        
        # Get update data
        update_json = request.get_json(force=True)
        if not update_json:
            logger.error("No JSON data received")
            return "No data", 400
        
        # Create update object
        update = Update.de_json(update_json, bot)
        if not update:
            logger.error("Failed to parse update")
            return "Invalid update", 400
        
        # Process the update
        async def process_update():
            await app_instance.initialize()
            await app_instance.process_update(update)
            await app_instance.shutdown()
        
        run_async(process_update())
        
        logger.info("Successfully processed update")
        return "OK"
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return "Error", 500

@app.route('/send_telegram_notification', methods=['POST'])
def send_telegram_notification():
    """Send a Telegram message to a specified chat ID."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        chat_id = data.get('chat_id')
        message_text = data.get('message')

        if not chat_id or not message_text:
            return jsonify({"error": "Missing chat_id or message"}), 400

        # Send message
        async def send_message():
            await bot.send_message(chat_id=chat_id, text=message_text)
        
        run_async(send_message())
        
        logger.info(f"Successfully sent message to {chat_id}")
        return jsonify({"status": "Message sent"}), 200
        
    except Exception as e:
        logger.error(f"Error sending message: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "bot_token_set": bool(TOKEN)})

@app.route('/set_webhook', methods=['POST'])
def set_webhook():
    """Manually set webhook"""
    try:
        if not WEBHOOK_URL:
            return jsonify({"error": "WEBHOOK_URL not configured"}), 400
            
        webhook_url = f"{WEBHOOK_URL}/telegram-webhook"
        
        async def set_wh():
            await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
        
        run_async(set_wh())
        
        logger.info(f"Webhook set to: {webhook_url}")
        return jsonify({"status": "Webhook set", "url": webhook_url})
        
    except Exception as e:
        logger.error(f"Error setting webhook: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# Set webhook on startup if URL is provided
if WEBHOOK_URL:
    try:
        webhook_url = f"{WEBHOOK_URL}/telegram-webhook"
        
        async def startup_webhook():
            await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
            logger.info(f"Startup webhook set to: {webhook_url}")
        
        run_async(startup_webhook())
    except Exception as e:
        logger.error(f"Failed to set startup webhook: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)