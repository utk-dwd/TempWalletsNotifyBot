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

# It's better to initialize the Application inside the main execution block
# after the webhook URL is potentially known, or at least before running the Flask app.
# For now, we'll keep it here, but the webhook setup will happen later.
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

# Register command handlers
bot_application.add_handler(CommandHandler("start", start))
bot_application.add_handler(CommandHandler("mychatid", my_chat_id))

# Define the webhook endpoint
@app.route('/telegram-webhook', methods=['POST'])
async def telegram_webhook():
    """Handle incoming Telegram updates via webhook."""
    # Ensure this is an async function to use await
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot_application.bot)
        await bot_application.process_update(update)
        return "ok"
    return "<h1>Telegram Webhook Endpoint</h1>", 200 # For GET requests, just return a status

# API Endpoint for sending notifications
@app.route('/send_telegram_notification', methods=['POST'])
def send_telegram_notification():
    data = request.json
    chat_id = data.get('chat_id')
    message_text = data.get('message')

    if not chat_id or not message_text:
        return jsonify({"error": "Missing chat_id or message"}), 400

    try:
        # We need to run this in the event loop of the bot_application
        # Since send_message is an async operation, it needs to be awaited.
        # We're running Flask in a synchronous thread, so we need to use
        # run_coroutine_threadsafe to submit the coroutine to the bot's event loop.
        asyncio.run_coroutine_threadsafe(
            bot_application.bot.send_message(chat_id=chat_id, text=message_text),
            bot_application.loop # Ensure you're using the correct event loop
        ).result() # .result() will block until the coroutine completes or raises an exception

        logger.info(f"Successfully sent Telegram message to {chat_id}")
        return jsonify({"status": "Message sent"}), 200
    except Exception as e:
        logger.error(f"Error sending Telegram message to {chat_id}: {e}")
        return jsonify({"error": str(e)}), 500

# Function to set the webhook
async def set_telegram_webhook():
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if WEBHOOK_URL:
        full_webhook_url = f"{WEBHOOK_URL}/telegram-webhook"
        logger.info(f"Attempting to set webhook to: {full_webhook_url}")
        try:
            await bot_application.bot.set_webhook(url=full_webhook_url)
            logger.info("Telegram webhook set successfully.")
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}")
    else:
        logger.warning("WEBHOOK_URL environment variable not set. Webhook will not be set automatically.")
        logger.warning("You will need to manually set the webhook using Telegram Bot API if you are deploying to a production environment.")

if __name__ == "__main__":
    # Initialize the bot application's internal structures, including the event loop
    # This must be done before setting up the webhook or starting the Flask app if they interact with the bot.
    bot_application.initialize()

    # Create a new event loop for setting the webhook
    # This is necessary because set_telegram_webhook is an async function
    # and we are outside of an async context.
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_telegram_webhook())

    # Start the Flask API server
    logger.info("Starting Flask API server...")
    # Using a separate thread to run the Flask app is generally not recommended
    # when Flask itself needs to handle asynchronous Telegram updates.
    # Flask with `async/await` and `asyncio.run` can run an async web server.
    # However, for simplicity and to leverage the existing `bot_application.loop` for sending messages,
    # we'll rely on Flask's built-in WSGI server here.
    # The `telegram-webhook` endpoint itself is now `async def`.
    app.run(host='0.0.0.0', port=5000, debug=False)

    # In a webhook setup, the bot doesn't poll, so `run_polling` is removed.
    # The Flask app receives the updates and processes them.
    # You might want to shut down the bot_application gracefully on Flask shutdown,
    # but for a typical web service, Flask's own shutdown will handle it.
    # If your application has background tasks managed by the bot_application,
    # you would need a more sophisticated shutdown mechanism.