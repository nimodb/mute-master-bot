import logging
from collections import defaultdict
from urllib.parse import urlparse
from typing import Optional, List, Dict

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, MessageEntity, ChatPermissions, User


from .. import config

logger = logging.getLogger(__name__)

# In-memory warning store. For persistence, consider using a database (e.g., SQLite).
WARNINGS = defaultdict(lambda: defaultdict(int)) # WARNINGS[chat_id][user_id]

def normalize_text(text: str) -> str:
    """Reduces repeated characters to avoid bypasses. E.g., 'heeeellooo' -> 'helo'."""
    return " ".join(
        "".join(char for i, char in enumerate(word) if i == 0 or char.lower() != word[i-1].lower())
        for word in text.split()
    )

def contains_violation(text: str, entities: Optional[List[MessageEntity]] = None) -> bool:
    """Checks a message for any moderation violations (cuss words, links, usernames)."""
    text_lower = text.lower()

    # 1. Check for non-whitelisted URLs
    # First, check plain text URLs
    if url_match := config.URL_PATTERN.search(text_lower):
        url = url_match.group(0)
        domain = urlparse(url if url.startswith("http") else "http://" + url).hostname or ""
        if not (domain.endswith(tuple(config.WHITELISTED_TLDS)) or domain.endswith(tuple(config.WHITELISTED_DOMAINS))):
            logger.debug("Violation: Non-whitelisted plaintext URL detected: %s", domain)
            return True
            
    # Second, check rich text entities (hyperlinks)
    if entities:
        for entity in entities:
            if entity.type in ("url", "text_link"):
                url = entity.url if entity.type == "text_link" else text[entity.offset : entity.offset + entity.length]
                domain = urlparse(url).hostname or ""
                if not (domain.endswith(tuple(config.WHITELISTED_TLDS)) or domain.endswith(tuple(config.WHITELISTED_DOMAINS))):
                    logger.debug("Violation: Non-whitelisted entity URL detected: %s", domain)
                    return True

    # 2. Check for cuss words
    if config.CUSS_WORDS_PATTERN.search(normalize_text(text_lower)):
        logger.debug("Violation: Cuss word detected.")
        return True

    # 3. Check for non-whitelisted usernames
    if usernames := config.USERNAME_PATTERN.findall(text):
        if not all(u in config.WHITELISTED_USERNAMES for u in usernames):
            logger.debug("Violation: Non-whitelisted username detected.")
            return True
            
    return False

def get_user_display_name(user: User) -> str:
    """Generates a user's display name, preferring first_name."""
    return user.first_name or f"@{user.username}" or f"User {user.id}"

async def apply_restriction(bot: Bot, message: Message, user_id: int, user_mention: str, settings: Dict, messages: Dict):
    """Applies the configured restriction (mute or ban) to a user."""
    action = settings["action"]
    lang = settings["language"]
    max_warnings = settings["max_warnings"]
    
    try:
        if action == config.ACTION_MUTE:
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=message.date.timestamp() + config.MUTE_DURATION_SECONDS
            )
            duration_text = messages.get("duration_hours", f"{config.MUTE_DURATION_SECONDS // 3600} hours").format(hours=config.MUTE_DURATION_SECONDS // 3600)
            action_text = messages.get("action_muted", "muted")
        else:  # ban
            await bot.ban_chat_member(chat_id=message.chat.id, user_id=user_id)
            duration_text = messages.get("duration_permanently", "permanently")
            action_text = messages.get("action_banned", "banned")

        await message.answer(
            messages.get("user_restricted", "User restricted.").format(
                max_warnings=max_warnings,
                user_mention=user_mention,
                action=action_text,
                duration=duration_text
            ),
            parse_mode="Markdown"
        )
        logger.info("User %d %s in chat %d for reaching %d warnings.", user_id, action_text, message.chat.id, max_warnings)
    except TelegramAPIError as e:
        logger.error("Failed to apply action '%s' to user %d in chat %d: %s", action, user_id, message.chat.id, e)
        # Inform admin if restriction fails
        await bot.send_message(
            config.ALLOWED_USER_ID,
            f"Failed to apply action `{action}` to user `{user_id}` in chat `{message.chat.id}`. The bot may lack admin permissions to restrict users."
        )

async def moderate_message(message: Message, bot: Bot, groups: Dict, messages: Dict, lang: str):
    """The main handler for moderating incoming group messages."""
    chat_id_str = str(message.chat.id)
    settings = groups.get(chat_id_str)

    if not message.text or not message.from_user:
        return # Ignore messages without text or a user (e.g., service messages)

    # Check if the bot should be active in this group
    if not settings or not settings.get("active", False):
        return

    user_id = message.from_user.id
    
    # Exempt admins and creators
    try:
        member = await bot.get_chat_member(chat_id=message.chat.id, user_id=user_id)
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            logger.debug("User %d is an admin in chat %d, exempt from moderation.", user_id, message.chat.id)
            return
    except TelegramAPIError as e:
        logger.error("Could not get chat member status for user %d in chat %d: %s", user_id, message.chat.id, e)
        return # Fail safe if we can't check status

    # Perform violation check
    if contains_violation(message.text, message.entities):
        try:
            await message.delete()
        except TelegramAPIError as e:
            logger.error("Failed to delete message %d in chat %d: %s", message.message_id, message.chat.id, e)
            await bot.send_message(config.ALLOWED_USER_ID, f"Failed to delete a message in chat `{message.chat.id}`. The bot may lack admin permissions to delete messages.")
            return # Stop processing if we can't even delete the message

        # Manage warnings
        WARNINGS[message.chat.id][user_id] += 1
        current_warnings = WARNINGS[message.chat.id][user_id]
        max_warnings = settings.get("max_warnings", 3)
        user_mention = f"[{get_user_display_name(message.from_user)}](tg://user?id={user_id})"
        
        logger.info("Violation by user %d in chat %d. Warning %d/%d.", user_id, message.chat.id, current_warnings, max_warnings)

        if current_warnings >= max_warnings:
            await apply_restriction(bot, message, user_id, user_mention, settings, messages)
            WARNINGS[message.chat.id][user_id] = 0  # Reset warnings after action
        else:
            warning_msg = await message.answer(
                messages.get("warning_issued", "Warning issued.").format(
                    user_mention=user_mention,
                    current=current_warnings,
                    max=max_warnings
                ),
                parse_mode="Markdown"
            )
            # Optional: Delete the warning message after a few seconds
            # await asyncio.sleep(15)
            # await warning_msg.delete()


def register(dp: Dispatcher):
    """Registers all moderation handlers."""
    # This handler will catch all text messages in groups and supergroups.
    # The LanguageMiddleware will run first to provide context.
    dp.message.register(
        moderate_message,
        F.chat.type.in_(("group", "supergroup")),
        F.text
    )