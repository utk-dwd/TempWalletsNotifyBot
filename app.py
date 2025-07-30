import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask, request, jsonify
import asyncio
import threading

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
# Get the Telegram Bot Token from environment variables.
# It's crucial to set this in your deployment environment (e.g., Render, Heroku).
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set. The bot will not function.")
    # Exit or raise an error if the token is not set, as the bot cannot run without it.
    # For local development, you might set a fallback, but for deployment, it must be present.
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing.")

# Get the Webhook URL from environment variables.
# This will be the URL provided by your hosting service (e.g., Render's URL).
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    logger.warning("WEBHOOK_URL environment variable not set. Webhook will not be set automatically.")
    logger.warning("You will need to manually set the webhook using Telegram Bot API if deploying.")

# Initialize Flask app
app = Flask(__name__)

# Initialize the Telegram Bot Application
# The webhook setup will happen later after the Flask app is ready.
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
        # Get the JSON update from Telegram
        update_json = request.get_json(force=True)
        # Create an Update object from the JSON
        update = Update.de_json(update_json, bot_application.bot)
        
        # Process the update using the bot application's dispatcher
        # This will trigger the appropriate command handlers.
        await bot_application.process_update(update)
        
        logger.info(f"Received and processed update from Telegram.")
        return "ok" # Telegram expects "ok" as a response
    
    # For GET requests to the webhook URL, return a simple message.
    return "<h1>Telegram Webhook Endpoint - Listening for POST requests</h1>", 200

# --- Optional: API Endpoint for Sending Notifications ---
# This endpoint allows other services to send messages to a specific chat ID.
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
        # Since Flask runs synchronously by default and bot_application.bot.send_message is async,
        # we need to run it within the bot's event loop.
        # run_coroutine_threadsafe submits the coroutine to the bot's event loop and returns a Future.
        # .result() blocks until the coroutine completes or raises an exception.
        asyncio.run_coroutine_threadsafe(
            bot_application.bot.send_message(chat_id=chat_id, text=message_text),
            bot_application.loop # Use the event loop associated with the bot_application
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
            # Set the webhook, ensuring pending updates are cleared
            await bot_application.bot.set_webhook(url=full_webhook_url, drop_pending_updates=True)
            logger.info("Telegram webhook set successfully.")
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}")
            # Re-raise the exception to prevent the app from starting if webhook setup fails critically
            raise
    else:
        logger.warning("WEBHOOK_URL environment variable not set. Webhook will not be set automatically.")
        logger.warning("Manual webhook setup might be required or the bot will not receive updates.")

# --- Main Application Entry Point ---

if __name__ == "__main__":
    # Initialize the bot application's internal structures, including its event loop.
    # This is crucial before any async operations related to the bot.
    bot_application.initialize()

    # Set the webhook synchronously during startup.
    # We need to get the current event loop and run the async webhook setup function.
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(set_telegram_webhook_async())
    except Exception as e:
        logger.critical(f"Critical error during webhook setup: {e}. Exiting.")
        exit(1) # Exit if webhook setup fails

    logger.info("Starting Flask API server...")
    # Run the Flask app. In a production environment, you would typically use a WSGI server
    # like Gunicorn to run this Flask application.
    # For local testing, app.run() is fine.
    # When deploying with Gunicorn, Gunicorn will handle the server part,
    # and Flask's built-in server will not be used.
    app.run(host='0.0.0.0', port=os.getenv("PORT", 5000), debug=False)

    # In a webhook setup, the bot doesn't poll, so `run_polling` is not used.
    # The Flask app receives the updates and processes them.
    # A graceful shutdown mechanism for `bot_application` might be needed for more complex apps.