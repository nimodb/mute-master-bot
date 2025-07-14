import asyncio
import logging
import logging.handlers
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

# Import from our new modular structure
from . import config
from .handlers import admin, moderation
from .middlewares import LoggingContextMiddleware, LanguageMiddleware
from .utils.file_ops import load_json_file

# --- Logging Setup ---
class ContextFilter(logging.Filter):
    """A filter to inject context from middlewares into log records."""
    def filter(self, record):
        # Default values if context is not available
        record.user_id = getattr(record, 'user_id', 'N/A')
        record.chat_id = getattr(record, 'chat_id', 'N/A')
        return True

def setup_logging():
    """Configures console and file logging."""
    log_level = logging.DEBUG if config.ENVIRONMENT == "development" else logging.INFO
    log_format = "%(asctime)s - %(levelname)s - [%(chat_id)s|%(user_id)s] - %(name)s - %(message)s"
    
    # Ensure logs directory exists
    config.LOGS_DIR.mkdir(exist_ok=True)
    
    # Create handlers
    console_handler = logging.StreamHandler(sys.stdout)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=config.LOG_FILE, when="midnight", interval=1, backupCount=14, encoding='utf-8'
    )
    error_handler = logging.FileHandler(config.LOGS_DIR / "error.log", encoding='utf-8')
    
    # Set formatters
    formatter = logging.Formatter(log_format)
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)
    
    # Get root logger and add handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Add context filter to all handlers
    for handler in root_logger.handlers:
        handler.addFilter(ContextFilter())

    # Set library log levels to be less verbose
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Configure error handler for ERROR and CRITICAL levels
    error_handler.setLevel(logging.ERROR)
    root_logger.addHandler(error_handler)

# --- Main Application ---
async def main():
    """Initializes and runs the bot."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Initialize database
    from .utils.db import init_db
    init_db()

    # --- Pre-startup Checks ---
    if not config.BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set in environment variables. Bot cannot start.")
        return
    if not config.ALLOWED_USER_ID:
        logger.warning("ALLOWED_USER_ID is not set. Admin commands will not work.")
    
    messages = load_json_file(config.MESSAGES_FILE)
    if not messages:
        logger.critical("messages.json is empty or could not be loaded. Bot cannot start.")
        return

    # --- Bot and Dispatcher Setup ---
    bot = Bot(token=config.BOT_TOKEN)
    
    # Load group settings and pass it to the dispatcher context
    groups_data = load_json_file(config.GROUPS_FILE)
    dp = Dispatcher(groups=groups_data)

    # --- Register Middlewares ---
    # The order is important: Logging context should be first.
    dp.update.middleware(LoggingContextMiddleware())
    # Language middleware runs on messages only, after logging context is set.
    dp.message.middleware(LanguageMiddleware())

    # --- Register Handlers ---
    logger.info("Registering handlers...")
    admin.register(dp)
    moderation.register(dp)
    logger.info("Handlers registered successfully.")

    # --- Start Polling ---
    try:
        logger.info("Starting Mute Master Bot...")
        await bot.delete_webhook(drop_pending_updates=True) # Recommended for polling bots
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical("A critical error occurred in the main loop: %s", e, exc_info=True)
    finally:
        await bot.session.close()
        logger.info("Bot session closed. Shutting down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped manually.")