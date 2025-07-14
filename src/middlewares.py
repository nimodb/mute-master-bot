import logging
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import TelegramObject, Message
from typing import Callable, Dict, Any, Awaitable

from . import config
from .utils.file_ops import load_json_file

logger = logging.getLogger(__name__)

# Load all messages at startup
MESSAGES = load_json_file(config.MESSAGES_FILE)
USER_SETTINGS = load_json_file(config.USER_SETTINGS_FILE, {str(config.ALLOWED_USER_ID): {"language": "en"}})

class LoggingContextMiddleware(BaseMiddleware):
    """Adds user_id and chat_id to the logging context for every update."""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Extract user and chat IDs if available
        user = data.get('event_from_user')
        chat = data.get('event_chat')
        
        data["logging_context"] = {
            "user_id": user.id if user else "N/A",
            "chat_id": chat.id if chat else "N/A"
        }
        return await handler(event, data)
    
    
class LanguageMiddleware(BaseMiddleware):
    """
    Injects user/group language and message templates into the data for handlers.
    Handles private chats and group chats differently.
    """
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        
        groups = data["groups"] # Get groups data passed from Dispatcher
        lang = "en" # Default language
        
        if event.chat.type == "private":
            user_id = str(event.from_user.id)
            lang = USER_SETTINGS.get(user_id, {}).get("language", "en")
        else: # group or supergroup
            chat_id = str(event.chat.id)
            lang = groups.get(chat_id, {}).get("language", "en")

        messages = MESSAGES.get(lang)
        if not messages:
            logger.error("Message templates for language '%s' not found.", lang)
            # Send a hardcoded error if message templates are missing
            await event.answer("Bot configuration error: Language files are missing. Please contact the administrator.")
            return

        data["lang"] = lang
        data["messages"] = messages
        return await handler(event, data)