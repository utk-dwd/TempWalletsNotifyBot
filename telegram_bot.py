import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Replace with your actual bot token obtained from BotFather
# Example: '123456:ABC-DEF1234ghIkl-zyx57W23u1PoQnOR'
TOKEN = "7173660283:AAHQkgoELkNwrVkBmZrD6UkMYYsHLQYqRgw" 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm your notification bot. "
        "Send /mychatid to get your unique Telegram Chat ID."
    )

async def my_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the user's chat ID and instructions when the command /mychatid is issued."""
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name if update.effective_user.first_name else "User"
    
    response_message = (
        f"Hello {user_name}!\n\n"
        f"Your Telegram Chat ID is: `{chat_id}`\n\n"
        "Please copy this ID and paste it into the 'Telegram Notifications' section "
        "on the TempWallets website to enable transaction notifications."
    )
    await update.message.reply_text(response_message, parse_mode='Markdown')

def main() -> None:
    """Start the bot."""
    # Create the Application and pass your bot's token.
    application = Application.builder().token(TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mychatid", my_chat_id))

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot started. Press Ctrl-C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()