import asyncio
import json
import logging.handlers
import re
import os
import logging
from functools import lru_cache
from dotenv import load_dotenv
from urllib.parse import urlparse
from typing import Optional, Set
from collections import defaultdict
from aiogram import Bot, Dispatcher
from aiogram.types import Message, ChatPermissions, MessageEntity, KeyboardButton, ReplyKeyboardMarkup, TelegramObject
from aiogram.filters import Command, Filter
from aiogram.exceptions import TelegramAPIError
from aiogram.dispatcher.middlewares.base import BaseMiddleware


class AdminFilter(Filter):
    def __init__(self, allowed_user_id: int):
        self.allowed_user_id = allowed_user_id

    async def __call__(self, message: Message) -> bool:
        return message.from_user.id == self.allowed_user_id


class LoggingContextMiddleware(BaseMiddleware):
    """Add user and chat IDs to logs."""
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id = getattr(event, 'from_user', None) and event.from_user.id or "N/A"
        chat_id = getattr(event, 'chat', None) and event.chat.id or "N/A"
        data["logging_context"] = {"user_id": user_id, "chat_id": chat_id}
        return await handler(event, data)


def setup_logging():
    """Configure logging based on ENVIRONMENT."""
    log_level = logging.DEBUG if os.getenv("ENVIRONMENT", "development") == "development" else logging.INFO
    log_format = "%(asctime)s - %(levelname)s - [%(chat_id)s|%(user_id)s] - %(message)s"
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename="mute_master_bot.log", when="midnight", interval=1, backupCount=7
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    
    logging.basicConfig(level=log_level, handlers=[console_handler, file_handler])
    
    class ContextFilter(logging.Filter):
        def filter(self, record):
            record.user_id = getattr(record, 'user_id', 'N/A')
            record.chat_id = getattr(record, 'chat_id', 'N/A')
            return True

    for handler in logging.getLogger().handlers:
        handler.addFilter(ContextFilter())


setup_logging()
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
BOT_TOKEN = os.getenv("BOT_TOKEN", None)
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
BOT_USERNAME = "@mute_master_bot"
MUTE_DURATION = 86400  # 24 hours in seconds

# Load group settings from JSON
def load_groups(file_path: str = "groups.json") -> dict:
    """Load group settings from JSON file."""
    logger.debug("Attempting to load groups from %s", file_path)
    if not os.path.exists(file_path):
        logger.warning("%s does not exist. Returning empty group settings.", file_path)
        return {}
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            if not content.strip():
                logger.warning("%s is empty. Returning empty group settings.", file_path)
                return {}
            groups = json.loads(content)
        groups_converted = {int(k): v for k, v in groups.items()}
        logger.debug("Loaded groups.")
        return groups_converted
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Failed to load %s: %s. Using empty group settings.", file_path, e)
        return {}
    except Exception as e:
        logger.error("Unexpected error loading %s: %s", file_path, e)
        return {}


def save_groups(groups: dict, file_path: str = "groups.json") -> None:
    """Save group settings to JSON file."""
    logger.debug("Saving groups to %s: %s", file_path, groups)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(groups, f, indent=4, ensure_ascii=False)
        logger.info("Group settings saved to %s", file_path)
    except Exception as e:
        logger.error("Failed to save %s: %s", file_path, e)


SPECIFIC_GROUP_IDS = load_groups()

# Configuration
WHITELISTED_DOMAINS: Set[str] = {"visametric.com"}
WHITELISTED_USERNAMES: Set[str] = {BOT_USERNAME, "@Vi_Ka1401", "@Tna_jy"}
WHITELISTED_TLDS: Set[str] = {".de"}

# Pre-compiled regex patterns
URL_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z]{2,}(?:/[^ ]*)?', re.IGNORECASE
)
USERNAME_PATTERN = re.compile(r'@\w+', re.IGNORECASE)

# Localized messages
MESSAGES = {
    "en": {
        "chat_not_monitored": "This group is not monitored. Please contact @nimodb to enable moderation.",
        "group_inactive": "Moderation is disabled in this group. Contact @nimodb for assistance.",
        "private_unauthorized": (
            "Sorry, only authorized users can interact with me privately.\n"
            "Please contact my creator @nimodb for support."
        ),
        "add_to_group_prompt": (
            "To add me to your group, click the link below and select your group:\n"
            "[Add to Group](https://t.me/{bot_username}?startgroup=true&admin=delete_messages+restrict_members+invite_users)\n\n"
            "⚠️ *Note*: You need 'Add Administrators' permission to add me."
        ),
        "warning_issued": (
            "Warning {current}/{max} for {user_mention}:\n"
            "Links, unauthorized usernames, or inappropriate words are not allowed."
        ),
        "user_restricted": (
            "Due to {max_warnings} violations, {user_mention} has been {action} for {duration}."
        ),
        "invalid_private_message": (
            "Please use one of the following commands or select 'Add the bot to group':\n\n"
            "*Available Commands:*\n"
            "- `/addgroup <group_id>`: Add a group for moderation.\n"
            "- `/setwarnings <group_id> <number>`: Set maximum warnings for a group.\n"
            "- `/setaction <group_id> <mute|ban>`: Set the action (mute or ban) for violations.\n"
            "- `/toggleactive <group_id>`: Enable or disable moderation for a group.\n"
            "- `/setlanguage <group_id> <en|fa>`: Set the language for group messages.\n"
            "- `/listgroups`: List all monitored groups and their settings.\n"
            "- `/removegroup`: Remove a group for moderation.\n"
        ),
        "user_language_set": "Your language has been set to {language}."
    },
    "fa": {
        "chat_not_monitored": "این گروه تحت نظارت نیست. لطفاً با @nimodb تماس بگیرید تا نظارت فعال شود.",
        "group_inactive": "نظارت در این گروه غیرفعال است. برای راهنمایی با @nimodb تماس بگیرید.",
        "private_unauthorized": (
            "متأسفم، فقط کاربران مجاز می‌توانند به‌صورت خصوصی با من تعامل کنند.\n"
            "لطفاً برای پشتیبانی با سازنده من @nimodb تماس بگیرید."
        ),
        "add_to_group_prompt": (
            "برای افزودن من به گروه خود، روی لینک زیر کلیک کنید و گروه موردنظر را انتخاب کنید:\n"
            "[افزودن به گروه](https://t.me/{bot_username}?startgroup=true&admin=delete_messages+restrict_members+invite_users)\n\n"
            "⚠️ *توجه*: برای افزودن من نیاز به مجوز 'افزودن مدیران' دارید."
        ),
        "warning_issued": (
            "اخطار {current}/{max} برای {user_mention}:\n"
            "لینک‌ها، نام‌های کاربری غیرمجاز یا کلمات نامناسب ممنوع است."
        ),
        "user_restricted": (
            "به دلیل {max_warnings} تخلف، {user_mention} به مدت {duration} {action} شد."
        ),
        "invalid_private_message": (
            "لطفاً از یکی از دستورات زیر استفاده کنید یا گزینه 'افزودن ربات به گروه' را انتخاب کنید:\n\n"
            "*دستورات موجود:*\n"
            "- `/addgroup <group_id>`: افزودن یک گروه برای نظارت.\n"
            "- `/setwarnings <group_id> <number>`: تنظیم حداکثر تعداد اخطارها برای یک گروه.\n"
            "- `/setaction <group_id> <mute|ban>`: تنظیم اقدام (محدودیت یا مسدودیت) برای تخلفات.\n"
            "- `/toggleactive <group_id>`: فعال یا غیرفعال کردن نظارت برای یک گروه.\n"
            "- `/setlanguage <group_id> <en|fa>`: تنظیم زبان پیام‌های گروه.\n"
            "- `/listgroups`: نمایش تمام گروه‌های تحت نظارت و تنظیمات آن‌ها.\n"
            "- `/removegroup`: حذف یک گروه برای نظارت.\n"
        ),
        "user_language_set": "زبان شما به {language} تنظیم شد."
    }
}

# Global state
WARNINGS = defaultdict(int)


@lru_cache(maxsize=1)
def load_cuss_words(file_path: str = "cuss_words.json") -> re.Pattern:
    """Load and compile cuss words pattern with caching."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            cuss_dict = json.load(f)
        all_cuss_words = [word.lower() for lang_words in cuss_dict.values() for word in lang_words]
        pattern = r'\b(?:' + '|'.join(map(re.escape, all_cuss_words)) + r')\b'
        return re.compile(pattern, re.IGNORECASE)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Failed to load cuss words from %s: %s", file_path, e)
        return re.compile(r'^$')

CUSS_WORDS_PATTERN = load_cuss_words()

# Utility functions
def normalize_text(text: str) -> str:
    """Remove duplicate letters from words."""
    return " ".join(
        "".join(char for i, char in enumerate(word) if i == 0 or char != word[i-1])
        for word in text.split()
    )


def contains_violation(text: str, entities: Optional[list[MessageEntity]] = None) -> bool:
    """Check if message contains violations."""
    text_lower = text.lower()
    
    url_match = URL_PATTERN.search(text_lower)
    if url_match:
        url = url_match.group(0)
        domain = urlparse(url if url.startswith("http") else "http://" + url).hostname
        if not (any(domain.endswith(tld) for tld in WHITELISTED_TLDS) or 
                any(domain.endswith(wl) for wl in WHITELISTED_DOMAINS)):
            logger.debug("Non-whitelisted URL detected: %s", url)
            return True

    if entities:
        for entity in entities:
            if entity.type in ("url", "text_link"):
                url = entity.url if entity.type == "text_link" else text[entity.offset:entity.offset + entity.length]
                domain = urlparse(url).hostname
                if domain and not (any(domain.endswith(tld) for tld in WHITELISTED_TLDS) or 
                                any(domain.endswith(wl) for wl in WHITELISTED_DOMAINS)):
                    logger.debug("Non-whitelisted entity URL detected: %s", url)
                    return True

    if CUSS_WORDS_PATTERN.search(normalize_text(text_lower)):
        logger.debug("Cuss word detected in message")
        return True

    usernames = USERNAME_PATTERN.findall(text)
    if usernames and not all(u in WHITELISTED_USERNAMES for u in usernames):
        logger.debug("Non-whitelisted username detected: %s", usernames)
        return True
    return False


def contains_link(text: str, entities: Optional[list[MessageEntity]] = None) -> bool:
    """Check if message contains a non-whitelisted link."""
    match = URL_PATTERN.search(text.lower())
    if match:
        url = match.group(0)
        domain = urlparse(url if url.startswith("http") else "http://" + url).hostname
        if domain:
            return not any(domain.endswith(whitelisted_domain) for whitelisted_domain in WHITELISTED_DOMAINS)

    if entities:
        for entity in entities:
            if entity.type in ("url", "text_link"):
                url = entity.url if entity.type == "text_link" else text[entity.offset:entity.offset + entity.length]
                domain = urlparse(url).hostname
                if domain:
                    return not any(domain.endswith(whitelisted_domain) for whitelisted_domain in WHITELISTED_DOMAINS)
    return False


def remove_duplicate_letters(text: str) -> str:
    """Remove duplicate letters from words."""
    words = text.split()
    normalized_words = []
    for word in words:
        result = ""
        prev_char = None
        for char in word:
            if char != prev_char:
                result += char
                prev_char = char
        normalized_words.append(result)
    return " ".join(normalized_words)


def contains_cuss_word(text: str) -> bool:
    """Check if text contains cuss words."""
    normalized_text = remove_duplicate_letters(text.lower())
    return bool(CUSS_WORDS_PATTERN.search(normalized_text))


def get_user_display_name(user) -> str:
    """Get user's display name."""
    return user.first_name or f"@{user.username}" or f"کاربر {user.id}"


# Bot setup
bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher()

# Moderation actions
async def apply_restriction(message: Message, user_id: int, user_mention: str, 
                           max_warnings: int, action: str, lang: str = "fa") -> None:
    """Apply mute or ban restriction."""
    try:
        if action == "mute":
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=int(message.date.timestamp()) + MUTE_DURATION
            )
            duration_text = f"{MUTE_DURATION // 3600} ساعت" if lang == "fa" else f"{MUTE_DURATION // 3600} hours"
            action_text = "محدود" if lang == "fa" else "muted"
        else:  # ban
            await bot.ban_chat_member(chat_id=message.chat.id, user_id=user_id)
            duration_text = "همیشه" if lang == "fa" else "permanently"
            action_text = "مسدود" if lang == "fa" else "banned"

        await message.answer(
            MESSAGES[lang]["user_restricted"].format(
                max_warnings=max_warnings,
                user_mention=user_mention,
                action=action_text,
                duration=duration_text
            ),
            parse_mode="Markdown"
        )
        logger.info("User %s %s in chat %s for %s", user_id, action_text, message.chat.id, duration_text)
    except TelegramAPIError as e:
        logger.error("Failed to apply restriction for user %s in chat %s: %s", user_id, message.chat.id, e)


async def moderate_message(message: Message) -> None:
    """Handle group/supergroup messages for moderation."""
    settings = SPECIFIC_GROUP_IDS.get(message.chat.id, {})
    lang = settings.get("language", "fa")
    
    if message.chat.id not in SPECIFIC_GROUP_IDS:
        logger.warning("Unmonitored chat detected")
        await message.answer(MESSAGES[lang]["chat_not_monitored"], parse_mode="Markdown")
        return
    
    if not settings["active"]:
        logger.info("Inactive group for moderation")
        await message.answer(MESSAGES[lang]["group_inactive"], parse_mode="Markdown")
        return
    
    if not message.text or not message.from_user:
        logger.debug("Invalid message: no text or user")
        return
    
    user_id = message.from_user.id
    chat_member = await bot.get_chat_member(chat_id=message.chat.id, user_id=user_id)
    if chat_member.status in ("administrator", "creator"):
        logger.debug("Admin user %s exempt from moderation", user_id)
        return
    
    if contains_violation(message.text, message.entities):
        try:
            await message.delete()
            WARNINGS[user_id] += 1
            user_mention = f"[{get_user_display_name(message.from_user)}](tg://user?id={user_id})"
            logger.info("Violation detected from user %s, warning %s/%s", 
                        user_id, WARNINGS[user_id], settings["max_warnings"])
            
            if WARNINGS[user_id] >= settings["max_warnings"]:
                await apply_restriction(message, user_id, user_mention, 
                                      settings["max_warnings"], settings["action"], lang)
                WARNINGS[user_id] = 0
            else:
                await message.answer(
                    MESSAGES[lang]["warning_issued"].format(
                        current=WARNINGS[user_id],
                        max=settings["max_warnings"],
                        user_mention=user_mention
                    ),
                    parse_mode="Markdown"
                )
        except TelegramAPIError as e:
            logger.error("Moderation error for user %s: %s", user_id, e)


async def private_chat_handler(message: Message) -> None:
    """Handle non-command private chat messages."""
    logger.debug("Processing private_chat_handler, message: %s", message.text)
    lang = "en"
    
    if message.from_user.id != ALLOWED_USER_ID:
        logger.warning("Unauthorized private message")
        await message.reply(MESSAGES[lang]["private_unauthorized"], parse_mode="Markdown")
        return

    if message.text in ["Add the bot to group", "افزودن ربات به گروه"]:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Add the bot to group" if lang == "en" else "افزودن ربات به گروه")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.reply(
            MESSAGES[lang]["add_to_group_prompt"].format(bot_username=BOT_USERNAME.replace('@', '')),
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
        logger.debug("Sent add_to_group_prompt")
    else:
        await message.reply(
            MESSAGES[lang]["invalid_private_message"],
            parse_mode="Markdown"
        )
        logger.debug("Sent invalid_private_message response for: %s", message.text)


async def add_group(message: Message) -> None:
    """Add a group for moderation."""
    logger.debug("Processing /addgroup")
    try:
        group_id = int(message.text.split()[1])
        if group_id in SPECIFIC_GROUP_IDS:
            await message.reply("This group is already monitored.", parse_mode="Markdown")
            return
        try:
            chat = await bot.get_chat(group_id)
            if chat.type not in ("group", "supergroup"):
                await message.reply("Invalid group ID. Must be a group or supergroup.", parse_mode="Markdown")
                return
        except TelegramAPIError:
            await message.reply("Bot is not a member of this group or invalid ID.", parse_mode="Markdown")
            return
        SPECIFIC_GROUP_IDS[group_id] = {
            "active": True, "max_warnings": 3, "action": "mute", "language": "fa"
        }
        save_groups(SPECIFIC_GROUP_IDS)
        await message.reply(f"Group {group_id} added for moderation with default settings.", parse_mode="Markdown")
        logger.info("Group %s added", group_id)
    except (IndexError, ValueError):
        await message.reply("Usage: `/addgroup <group_id>`", parse_mode="Markdown")


async def set_warnings(message: Message) -> None:
    """Set maximum warnings for a group."""
    logger.debug("Processing /setwarnings")
    try:
        group_id, warnings = map(int, message.text.split()[1:3])
        if group_id not in SPECIFIC_GROUP_IDS:
            await message.reply("This group is not monitored.", parse_mode="Markdown")
            return
        if warnings < 1:
            raise ValueError("Warnings must be positive")
        SPECIFIC_GROUP_IDS[group_id]["max_warnings"] = warnings
        save_groups(SPECIFIC_GROUP_IDS)
        await message.reply(f"Max warnings set to {warnings} for group {group_id}.", parse_mode="Markdown")
        logger.info("Max warnings set to %s for group %s", warnings, group_id)
    except (IndexError, ValueError):
        await message.reply("Usage: `/setwarnings <group_id> <number>`", parse_mode="Markdown")


async def set_action(message: Message) -> None:
    """Set action (mute or ban) for a group."""
    logger.debug("Processing /setaction")
    try:
        group_id, action = message.text.split()[1:3]
        group_id = int(group_id)
        action = action.lower()
        if group_id not in SPECIFIC_GROUP_IDS:
            await message.reply("This group is not monitored.", parse_mode="Markdown")
            return
        if action not in ("mute", "ban"):
            raise ValueError("Action must be 'mute' or 'ban'")
        SPECIFIC_GROUP_IDS[group_id]["action"] = action
        save_groups(SPECIFIC_GROUP_IDS)
        await message.reply(f"Action set to {action} for group {group_id}.", parse_mode="Markdown")
        logger.info("Action set to %s for group %s", action, group_id)
    except (IndexError, ValueError):
        await message.reply("Usage: `/setaction <group_id> <mute|ban>`", parse_mode="Markdown")


async def toggle_active(message: Message) -> None:
    """Toggle moderation active status for a group."""
    logger.debug("Processing /toggleactive")
    try:
        group_id = int(message.text.split()[1])
        if group_id not in SPECIFIC_GROUP_IDS:
            await message.reply("This group is not monitored.", parse_mode="Markdown")
            return
        SPECIFIC_GROUP_IDS[group_id]["active"] = not SPECIFIC_GROUP_IDS[group_id]["active"]
        save_groups(SPECIFIC_GROUP_IDS)
        status = "enabled" if SPECIFIC_GROUP_IDS[group_id]["active"] else "disabled"
        await message.reply(f"Moderation {status} for group {group_id}.", parse_mode="Markdown")
        logger.info("Moderation %s for group %s", status, group_id)
    except (IndexError, ValueError):
        await message.reply("Usage: `/toggleactive <group_id>`", parse_mode="Markdown")


async def set_language(message: Message) -> None:
    """Set language for group messages."""
    logger.debug("Processing /setlanguage")
    try:
        group_id, language = message.text.split()[1:3]
        group_id = int(group_id)
        language = language.lower()
        if group_id not in SPECIFIC_GROUP_IDS:
            await message.reply("This group is not monitored.", parse_mode="Markdown")
            return
        if language not in ("en", "fa"):
            raise ValueError("Language must be 'en' or 'fa'")
        SPECIFIC_GROUP_IDS[group_id]["language"] = language
        save_groups(SPECIFIC_GROUP_IDS)
        await message.reply(f"Language set to {language} for group {group_id}.", parse_mode="Markdown")
        logger.info("Language set to %s for group %s", language, group_id)
    except (IndexError, ValueError):
        await message.reply("Usage: `/setlanguage <group_id> <en|fa>`", parse_mode="Markdown")


async def list_groups(message: Message) -> None:
    """List all monitored groups."""
    logger.debug("Processing /listgroups, SPECIFIC_GROUP_IDS: %s", SPECIFIC_GROUP_IDS)
    if not SPECIFIC_GROUP_IDS:
        logger.info("No groups found in SPECIFIC_GROUP_IDS")
        await message.reply("No groups are monitored. Add groups using `/addgroup <group_id>`.", parse_mode="Markdown")
        return
    try:
        group_items = [
            f"ID: `{gid}`\n  - Active: {s['active']}, Warnings: {s['max_warnings']}, Action: {s['action']}, Lang: {s['language']}"
            for gid, s in SPECIFIC_GROUP_IDS.items()
        ]
        group_list = "\n".join(group_items)
        await message.reply(f"*Monitored groups:*\n{group_list}", parse_mode="Markdown")
        logger.info("Listed groups: %s", group_list)
    except Exception as e:
        logger.error("Error listing groups: %s", e)
        await message.reply("Error listing groups. Please check logs.", parse_mode="Markdown")


async def remove_group(message: Message) -> None:
    """Remove a group from moderation."""
    logger.debug("Processing /removegroup")
    try:
        group_id = int(message.text.split()[1])
        if group_id not in SPECIFIC_GROUP_IDS:
            await message.reply("This group is not monitored.", parse_mode="Markdown")
            return
        del SPECIFIC_GROUP_IDS[group_id]
        save_groups(SPECIFIC_GROUP_IDS)
        await message.reply(f"Group {group_id} removed from moderation.", parse_mode="Markdown")
        logger.info("Group %s removed", group_id)
    except (IndexError, ValueError):
        await message.reply("Usage: `/removegroup <group_id>`", parse_mode="Markdown")

# Startup and main
async def on_startup():
    logger.info("Mute Master Bot is online!")


async def main():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set!")
        raise ValueError("BOT_TOKEN is not set!")
    
    dispatcher.update.middleware(LoggingContextMiddleware())
    
    # Register handlers
    dispatcher.message.register(moderate_message, lambda m: m.chat.type in ("group", "supergroup"))
    dispatcher.message.register(add_group, Command("addgroup"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(set_warnings, Command("setwarnings"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(set_action, Command("setaction"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(toggle_active, Command("toggleactive"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(set_language, Command("setlanguage"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(list_groups, Command("listgroups"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(remove_group, Command("removegroup"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(private_chat_handler, lambda m: m.chat.type == "private" and m.text and not m.text.startswith('/'))
    
    try:
        await on_startup()
        await dispatcher.start_polling(bot)
    except Exception as e:
        logger.critical("Main loop error: %s", e)
        raise
    finally:
        await bot.session.close()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())