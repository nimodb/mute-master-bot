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


# Custom filter for authorized user
class AdminFilter(Filter):
    def __init__(self, allowed_user_id: int):
        self.allowed_user_id = allowed_user_id

    async def __call__(self, message: Message) -> bool:
        return message.from_user.id == self.allowed_user_id


# Middleware to add context to logs
class LoggingContextMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id = getattr(event, 'from_user', None) and event.from_user.id or "N/A"
        chat_id = getattr(event, 'chat', None) and event.chat.id or "N/A"
        data["logging_context"] = {"user_id": user_id, "chat_id": chat_id}
        return await handler(event, data)

# Logging configuration
def setup_logging():
    log_level = logging.DEBUG if os.getenv("ENVIRONMENT", "development") == "development" else logging.INFO
    log_format = "%(asctime)s - %(levelname)s - [%(chat_id)s|%(user_id)s] - %(message)s"
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename="logs/mute_master_bot.log", when="midnight", interval=1, backupCount=7
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
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
BOT_TOKEN = os.getenv("BOT_TOKEN", None)
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
BOT_USERNAME = "@mute_master_bot"
MUTE_DURATION = 86400  # 24 hours in seconds

# File operations
def load_json_file(file_path: str, default: dict) -> dict:
    if not os.path.exists(file_path):
        logger.warning("%s does not exist. Creating with default content.", file_path)
        save_json_file(default, file_path)
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                logger.warning("%s is empty. Creating with default content.", file_path)
                save_json_file(default, file_path)
                return default
            data = json.loads(content)
        return {str(k): v for k, v in data.items()} if isinstance(data, dict) else default
    except (json.JSONDecodeError, PermissionError, OSError) as e:
        logger.error("Failed to load %s: %s. Using default.", file_path, e)
        save_json_file(default, file_path)
        return default


def save_json_file(data: dict, file_path: str) -> None:
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info("%s saved successfully.", file_path)
    except (PermissionError, OSError) as e:
        logger.error("Failed to save %s: %s", file_path, e)


SPECIFIC_GROUP_IDS = load_json_file("config/groups.json", {})
USER_SETTINGS = load_json_file("config/user_settings.json", {str(ALLOWED_USER_ID): {"language": "en"}})

# Configuration
WHITELISTED_DOMAINS: Set[str] = {"visametric.com"}
WHITELISTED_USERNAMES: Set[str] = {BOT_USERNAME, "@Vi_Ka1401", "@Tna_jy"}
WHITELISTED_TLDS: Set[str] = {".de"}

# Pre-compiled regex patterns
URL_PATTERN = re.compile(r'(?:https?://)?(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z]{2,}(?:/[^ ]*)?', re.IGNORECASE)
USERNAME_PATTERN = re.compile(r'@\w+', re.IGNORECASE)

# Localized messages
MESSAGES = {
    "en": {
        "chat_not_monitored": "This group is not monitored. Please contact @nimodb to enable moderation.",
        "group_inactive": "Moderation is disabled in this group. Contact @nimodb for assistance.",
        "private_unauthorized": "Sorry, only authorized users can interact with me privately. Contact @nimodb for support.",
        "add_to_group_prompt": (
            "To add me to your group, click the link below and select your group:\n"
            "[Add to Group](https://t.me/{bot_username}?startgroup=true&admin=delete_messages+restrict_members+invite_users)\n\n"
            "⚠️ *Note*: You need 'Add Administrators' permission to add me."
        ),
        "warning_issued": "Warning {current}/{max} for {user_mention}: Links, unauthorized usernames, or inappropriate words are not allowed.",
        "user_restricted": "Due to {max_warnings} violations, {user_mention} has been {action} for {duration}.",
        "invalid_private_message": (
            "Please use one of the following commands or select 'Add the bot to group':\n\n"
            "*Available Commands:*\n"
            "- `/addgroup <group_id>`: Add a group for moderation.\n"
            "- `/setwarnings <group_id> <number>`: Set maximum warnings for a group.\n"
            "- `/setaction <group_id> <mute|ban>`: Set the action for violations.\n"
            "- `/toggleactive <group_id>`: Enable or disable moderation.\n"
            "- `/setlanguage <group_id> <en|fa>`: Set group message language.\n"
            "- `/setuserlanguage <en|fa>`: Set your preferred language.\n"
            "- `/listgroups`: List all monitored groups.\n"
            "- `/removegroup <group_id>`: Remove a group from moderation."
        ),
        "group_added": "Group {group_id} added for moderation with default settings.",
        "group_already_monitored": "This group is already monitored.",
        "invalid_group_id": "Invalid group ID. Must be a group or supergroup.",
        "bot_not_member": "Bot is not a member of this group or invalid ID.",
        "usage_addgroup": "Usage: `/addgroup <group_id>`",
        "group_not_monitored": "This group is not monitored.",
        "warnings_must_be_positive": "Warnings must be positive.",
        "max_warnings_set": "Max warnings set to {warnings} for group {group_id}.",
        "usage_setwarnings": "Usage: `/setwarnings <group_id> <number>`",
        "action_must_be_mute_or_ban": "Action must be 'mute' or 'ban'.",
        "action_set": "Action set to {action} for group {group_id}.",
        "usage_setaction": "Usage: `/setaction <group_id> <mute|ban>`",
        "moderation_enabled": "Moderation enabled for group {group_id}.",
        "moderation_disabled": "Moderation disabled for group {group_id}.",
        "usage_toggleactive": "Usage: `/toggleactive <group_id>`",
        "language_must_be_en_or_fa": "Language must be 'en' or 'fa'.",
        "language_set": "Language set to {language} for group {group_id}.",
        "usage_setlanguage": "Usage: `/setlanguage <group_id> <en|fa>`",
        "no_groups_monitored": "No groups are monitored. Add groups using `/addgroup <group_id>`.",
        "error_listing_groups": "Error listing groups. Please check logs.",
        "group_removed": "Group {group_id} removed from moderation.",
        "usage_removegroup": "Usage: `/removegroup <group_id>`",
        "user_language_set": "Your language has been set to {language}.",
        "usage_setuserlanguage": "Usage: `/setuserlanguage <en|fa>`"
    },
    "fa": {
        "chat_not_monitored": "این گروه تحت نظارت نیست. لطفاً با @nimodb تماس بگیرید تا نظارت فعال شود.",
        "group_inactive": "نظارت در این گروه غیرفعال است. برای راهنمایی با @nimodb تماس بگیرید.",
        "private_unauthorized": "متأسفم، فقط کاربران مجاز می‌توانند به‌صورت خصوصی با من تعامل کنند. با @nimodb تماس بگیرید.",
        "add_to_group_prompt": (
            "برای افزودن من به گروه خود، روی لینک زیر کلیک کنید و گروه موردنظر را انتخاب کنید:\n"
            "[افزودن به گروه](https://t.me/{bot_username}?startgroup=true&admin=delete_messages+restrict_members+invite_users)\n\n"
            "⚠️ *توجه*: برای افزودن من نیاز به مجوز 'افزودن مدیران' دارید."
        ),
        "warning_issued": "اخطار {current}/{max} برای {user_mention}: لینک‌ها، نام‌های کاربری غیرمجاز یا کلمات نامناسب ممنوع است.",
        "user_restricted": "به دلیل {max_warnings} تخلف، {user_mention} به مدت {duration} {action} شد.",
        "invalid_private_message": (
            "لطفاً از یکی از دستورات زیر استفاده کنید یا گزینه 'افزودن ربات به گروه' را انتخاب کنید:\n\n"
            "*دستورات موجود:*\n"
            "- `/addgroup <group_id>`: افزودن یک گروه برای نظارت.\n"
            "- `/setwarnings <group_id> <number>`: تنظیم حداکثر اخطارها برای یک گروه.\n"
            "- `/setaction <group_id> <mute|ban>`: تنظیم اقدام برای تخلفات.\n"
            "- `/toggleactive <group_id>`: فعال یا غیرفعال کردن نظارت.\n"
            "- `/setlanguage <group_id> <en|fa>`: تنظیم زبان پیام‌های گروه.\n"
            "- `/setuserlanguage <en|fa>`: تنظیم زبان مورد نظر شما.\n"
            "- `/listgroups`: نمایش تمام گروه‌های تحت نظارت.\n"
            "- `/removegroup <group_id>`: حذف یک گروه از نظارت."
        ),
        "group_added": "گروه {group_id} با تنظیمات پیش‌فرض برای نظارت افزوده شد.",
        "group_already_monitored": "این گروه قبلاً تحت نظارت است.",
        "invalid_group_id": "آیدی گروه نامعتبر است. باید یک گروه یا سوپرگروه باشد.",
        "bot_not_member": "ربات عضو این گروه نیست یا آیدی نامعتبر است.",
        "usage_addgroup": "نحوه استفاده: `/addgroup <group_id>`",
        "group_not_monitored": "این گروه تحت نظارت نیست.",
        "warnings_must_be_positive": "اخطارها باید مثبت باشند.",
        "max_warnings_set": "حداکثر اخطارها به {warnings} برای گروه {group_id} تنظیم شد.",
        "usage_setwarnings": "نحوه استفاده: `/setwarnings <group_id> <number>`",
        "action_must_be_mute_or_ban": "اقدام باید 'mute' یا 'ban' باشد.",
        "action_set": "اقدام به {action} برای گروه {group_id} تنظیم شد.",
        "usage_setaction": "نحوه استفاده: `/setaction <group_id> <mute|ban>`",
        "moderation_enabled": "نظارت برای گروه {group_id} فعال شد.",
        "moderation_disabled": "نظارت برای گروه {group_id} غیرفعال شد.",
        "usage_toggleactive": "نحوه استفاده: `/toggleactive <group_id>`",
        "language_must_be_en_or_fa": "زبان باید 'en' یا 'fa' باشد.",
        "language_set": "زبان به {language} برای گروه {group_id} تنظیم شد.",
        "usage_setlanguage": "نحوه استفاده: `/setlanguage <group_id> <en|fa>`",
        "no_groups_monitored": "هیچ گروهی تحت نظارت نیست. با `/addgroup <group_id>` گروه اضافه کنید.",
        "error_listing_groups": "خطا در نمایش گروه‌ها. لاگ‌ها را بررسی کنید。",
        "group_removed": "گروه {group_id} از نظارت حذف شد.",
        "usage_removegroup": "نحوه استفاده: `/removegroup <group_id>`",
        "user_language_set": "زبان شما به {language} تنظیم شد.",
        "usage_setuserlanguage": "نحوه استفاده: `/setuserlanguage <en|fa>`"
    }
}

# Global state
WARNINGS = defaultdict(int)

@lru_cache(maxsize=1)
def load_cuss_words(file_path: str = "config/cuss_words.json") -> re.Pattern:
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
    return " ".join(
        "".join(char for i, char in enumerate(word) if i == 0 or char != word[i-1])
        for word in text.split()
    )


def contains_violation(text: str, entities: Optional[list[MessageEntity]] = None) -> bool:
    text_lower = text.lower()
    
    url_match = URL_PATTERN.search(text_lower)
    if url_match:
        url = url_match.group(0)
        domain = urlparse(url if url.startswith("http") else "http://" + url).hostname
        if not (any(domain.endswith(tld) for tld in WHITELISTED_TLDS) or 
                any(domain.endswith(wl) for wl in WHITELISTED_DOMAINS)):
            logger.debug("Non-whitelisted URL detected")
            return True

    if entities:
        for entity in entities:
            if entity.type in ("url", "text_link"):
                url = entity.url if entity.type == "text_link" else text[entity.offset:entity.offset + entity.length]
                domain = urlparse(url).hostname
                if domain and not (any(domain.endswith(tld) for tld in WHITELISTED_TLDS) or 
                                any(domain.endswith(wl) for wl in WHITELISTED_DOMAINS)):
                    logger.debug("Non-whitelisted entity URL detected")
                    return True

    if CUSS_WORDS_PATTERN.search(normalize_text(text_lower)):
        logger.debug("Cuss word detected")
        return True

    usernames = USERNAME_PATTERN.findall(text)
    if usernames and not all(u in WHITELISTED_USERNAMES for u in usernames):
        logger.debug("Non-whitelisted username detected")
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

def get_user_display_name(user) -> str:
    return user.first_name or f"@{user.username}" or f"کاربر {user.id}"

# Bot setup
bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher()

# Moderation actions
async def apply_restriction(message: Message, user_id: int, user_mention: str, 
                            max_warnings: int, action: str, lang: str) -> None:
    try:
        if action == "mute":
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=int(message.date.timestamp()) + MUTE_DURATION
            )
            duration_text = f"{MUTE_DURATION // 3600} hours" if lang == "en" else f"{MUTE_DURATION // 3600} ساعت"
            action_text = "muted" if lang == "en" else "محدود"
        else:  # ban
            await bot.ban_chat_member(chat_id=message.chat.id, user_id=user_id)
            duration_text = "permanently" if lang == "en" else "همیشه"
            action_text = "banned" if lang == "en" else "مسدود"

        await message.answer(
            MESSAGES[lang]["user_restricted"].format(
                max_warnings=max_warnings,
                user_mention=user_mention,
                action=action_text,
                duration=duration_text
            ),
            parse_mode="Markdown"
        )
        logger.info("User %s %s in chat %s", user_id, action_text, message.chat.id)
    except TelegramAPIError as e:
        logger.error("Failed to restrict user %s in chat %s: %s", user_id, message.chat.id, e)

async def moderate_message(message: Message) -> None:
    settings = SPECIFIC_GROUP_IDS.get(str(message.chat.id), {})
    lang = settings.get("language", "fa")
    
    if not settings:
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
            logger.info("Violation by user %s, warning %s/%s", user_id, WARNINGS[user_id], settings["max_warnings"])
            
            if WARNINGS[user_id] >= settings["max_warnings"]:
                await apply_restriction(message, user_id, user_mention, settings["max_warnings"], settings["action"], lang)
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
    user_id = str(message.from_user.id)
    lang = USER_SETTINGS.get(user_id, {"language": "fa"})["language"]
    
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
        await message.reply(MESSAGES[lang]["invalid_private_message"], parse_mode="Markdown")
        logger.debug("Sent invalid_private_message response")

async def add_group(message: Message) -> None:
    user_id = str(message.from_user.id)
    lang = USER_SETTINGS.get(user_id, {"language": "fa"})["language"]
    try:
        group_id = int(message.text.split()[1])
        group_id_str = str(group_id)
        if group_id_str in SPECIFIC_GROUP_IDS:
            await message.reply(MESSAGES[lang]["group_already_monitored"], parse_mode="Markdown")
            return
        try:
            chat = await bot.get_chat(group_id)
            if chat.type not in ("group", "supergroup"):
                await message.reply(MESSAGES[lang]["invalid_group_id"], parse_mode="Markdown")
                return
        except TelegramAPIError:
            await message.reply(MESSAGES[lang]["bot_not_member"], parse_mode="Markdown")
            return
        SPECIFIC_GROUP_IDS[group_id_str] = {"active": True, "max_warnings": 3, "action": "mute", "language": "fa"}
        save_json_file(SPECIFIC_GROUP_IDS, "config/groups.json")
        await message.reply(MESSAGES[lang]["group_added"].format(group_id=group_id), parse_mode="Markdown")
        logger.info("Group %s added", group_id)
    except (IndexError, ValueError):
        await message.reply(MESSAGES[lang]["usage_addgroup"], parse_mode="Markdown")

async def set_warnings(message: Message) -> None:
    user_id = str(message.from_user.id)
    lang = USER_SETTINGS.get(user_id, {"language": "fa"})["language"]
    try:
        group_id, warnings = map(int, message.text.split()[1:3])
        group_id_str = str(group_id)
        if group_id_str not in SPECIFIC_GROUP_IDS:
            await message.reply(MESSAGES[lang]["group_not_monitored"], parse_mode="Markdown")
            return
        if warnings < 1:
            await message.reply(MESSAGES[lang]["warnings_must_be_positive"], parse_mode="Markdown")
            return
        SPECIFIC_GROUP_IDS[group_id_str]["max_warnings"] = warnings
        save_json_file(SPECIFIC_GROUP_IDS, "config/groups.json")
        await message.reply(MESSAGES[lang]["max_warnings_set"].format(warnings=warnings, group_id=group_id), parse_mode="Markdown")
        logger.info("Max warnings set to %s for group %s", warnings, group_id)
    except (IndexError, ValueError):
        await message.reply(MESSAGES[lang]["usage_setwarnings"], parse_mode="Markdown")

async def set_action(message: Message) -> None:
    user_id = str(message.from_user.id)
    lang = USER_SETTINGS.get(user_id, {"language": "fa"})["language"]
    try:
        group_id, action = message.text.split()[1:3]
        group_id = int(group_id)
        action = action.lower()
        group_id_str = str(group_id)
        if group_id_str not in SPECIFIC_GROUP_IDS:
            await message.reply(MESSAGES[lang]["group_not_monitored"], parse_mode="Markdown")
            return
        if action not in ("mute", "ban"):
            await message.reply(MESSAGES[lang]["action_must_be_mute_or_ban"], parse_mode="Markdown")
            return
        SPECIFIC_GROUP_IDS[group_id_str]["action"] = action
        save_json_file(SPECIFIC_GROUP_IDS, "config/groups.json")
        await message.reply(MESSAGES[lang]["action_set"].format(action=action, group_id=group_id), parse_mode="Markdown")
        logger.info("Action set to %s for group %s", action, group_id)
    except (IndexError, ValueError):
        await message.reply(MESSAGES[lang]["usage_setaction"], parse_mode="Markdown")

async def toggle_active(message: Message) -> None:
    user_id = str(message.from_user.id)
    lang = USER_SETTINGS.get(user_id, {"language": "fa"})["language"]
    try:
        group_id = int(message.text.split()[1])
        group_id_str = str(group_id)
        if group_id_str not in SPECIFIC_GROUP_IDS:
            await message.reply(MESSAGES[lang]["group_not_monitored"], parse_mode="Markdown")
            return
        SPECIFIC_GROUP_IDS[group_id_str]["active"] = not SPECIFIC_GROUP_IDS[group_id_str]["active"]
        save_json_file(SPECIFIC_GROUP_IDS, "config/groups.json")
        status = "enabled" if SPECIFIC_GROUP_IDS[group_id_str]["active"] else "disabled"
        await message.reply(MESSAGES[lang][f"moderation_{status}"].format(group_id=group_id), parse_mode="Markdown")
        logger.info("Moderation %s for group %s", status, group_id)
    except (IndexError, ValueError):
        await message.reply(MESSAGES[lang]["usage_toggleactive"], parse_mode="Markdown")

async def set_language(message: Message) -> None:
    user_id = str(message.from_user.id)
    lang = USER_SETTINGS.get(user_id, {"language": "fa"})["language"]
    try:
        group_id, language = message.text.split()[1:3]
        group_id = int(group_id)
        language = language.lower()
        group_id_str = str(group_id)
        if group_id_str not in SPECIFIC_GROUP_IDS:
            await message.reply(MESSAGES[lang]["group_not_monitored"], parse_mode="Markdown")
            return
        if language not in ("en", "fa"):
            await message.reply(MESSAGES[lang]["language_must_be_en_or_fa"], parse_mode="Markdown")
            return
        SPECIFIC_GROUP_IDS[group_id_str]["language"] = language
        save_json_file(SPECIFIC_GROUP_IDS, "config/groups.json")
        await message.reply(MESSAGES[lang]["language_set"].format(language=language, group_id=group_id), parse_mode="Markdown")
        logger.info("Language set to %s for group %s", language, group_id)
    except (IndexError, ValueError):
        await message.reply(MESSAGES[lang]["usage_setlanguage"], parse_mode="Markdown")

async def set_user_language(message: Message) -> None:
    user_id = str(message.from_user.id)
    lang = USER_SETTINGS.get(user_id, {"language": "fa"})["language"]
    try:
        new_lang = message.text.split()[1].lower()
        if new_lang not in ("en", "fa"):
            await message.reply(MESSAGES[lang]["language_must_be_en_or_fa"], parse_mode="Markdown")
            return
        USER_SETTINGS[user_id] = {"language": new_lang}
        save_json_file(USER_SETTINGS, "config/user_settings.json")
        await message.reply(MESSAGES[new_lang]["user_language_set"].format(language=new_lang), parse_mode="Markdown")
        logger.info("User %s language set to %s", user_id, new_lang)
    except IndexError:
        await message.reply(MESSAGES[lang]["usage_setuserlanguage"], parse_mode="Markdown")

async def list_groups(message: Message) -> None:
    user_id = str(message.from_user.id)
    lang = USER_SETTINGS.get(user_id, {"language": "fa"})["language"]
    if not SPECIFIC_GROUP_IDS:
        await message.reply(MESSAGES[lang]["no_groups_monitored"], parse_mode="Markdown")
        return
    try:
        group_items = [
            f"ID: `{gid}`\n  - Active: {s['active']}, Warnings: {s['max_warnings']}, Action: {s['action']}, Lang: {s['language']}"
            for gid, s in SPECIFIC_GROUP_IDS.items()
        ]
        group_list = "\n".join(group_items)
        await message.reply(f"*Monitored groups:*\n{group_list}", parse_mode="Markdown")
        logger.info("Listed groups")
    except Exception as e:
        logger.error("Error listing groups: %s", e)
        await message.reply(MESSAGES[lang]["error_listing_groups"], parse_mode="Markdown")

async def remove_group(message: Message) -> None:
    user_id = str(message.from_user.id)
    lang = USER_SETTINGS.get(user_id, {"language": "fa"})["language"]
    try:
        group_id = int(message.text.split()[1])
        group_id_str = str(group_id)
        if group_id_str not in SPECIFIC_GROUP_IDS:
            await message.reply(MESSAGES[lang]["group_not_monitored"], parse_mode="Markdown")
            return
        del SPECIFIC_GROUP_IDS[group_id_str]
        save_json_file(SPECIFIC_GROUP_IDS, "config/groups.json")
        await message.reply(MESSAGES[lang]["group_removed"].format(group_id=group_id), parse_mode="Markdown")
        logger.info("Group %s removed", group_id)
    except (IndexError, ValueError):
        await message.reply(MESSAGES[lang]["usage_removegroup"], parse_mode="Markdown")

# Startup and main
async def on_startup():
    logger.info("Mute Master Bot is online!")

async def main():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set!")
        raise ValueError("BOT_TOKEN is not set!")
    
    dispatcher.update.middleware(LoggingContextMiddleware())
    
    dispatcher.message.register(moderate_message, lambda m: m.chat.type in ("group", "supergroup"))
    dispatcher.message.register(add_group, Command("addgroup"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(set_warnings, Command("setwarnings"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(set_action, Command("setaction"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(toggle_active, Command("toggleactive"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(set_language, Command("setlanguage"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
    dispatcher.message.register(set_user_language, Command("setuserlanguage"), lambda m: m.chat.type == "private", AdminFilter(ALLOWED_USER_ID))
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