from aiogram.filters import Filter
from aiogram.types import Message
from . import config

class AdminFilter(Filter):
    """A custom filter to check if a message is from the authorized admin user."""
    
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id == config.ALLOWED_USER_ID