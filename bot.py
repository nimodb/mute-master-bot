import asyncio
import json
import re
import os
from functools import lru_cache
from dotenv import load_dotenv
from urllib.parse import urlparse
from typing import Optional, Dict, Set
from collections import defaultdict
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Message, ChatPermissions, MessageEntity, KeyboardButton, ReplyKeyboardMarkup
from aiogram.exceptions import TelegramAPIError


# Load environment variables
load_dotenv()

# Constants
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
BOT_TOKEN = os.getenv("BOT_TOKEN")
PROXY_URL = os.getenv("PROXY_URL")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
BOT_USERNAME = "@mute_master_bot"
MUTE_DURATION = 86400 # 24 hours in seconds

# Configuration
SPECIFIC_GROUP_IDS = {
    -1002336037736: {"active": True, "max_warnings": 3, "action": "mute"},
    -1002447378789: {"active": True, "max_warnings": 3, "action": "mute"},
}
WHITELISTED_DOMAINS: Set[str] = {"visametric.com", "teheran.diplo.de", "auswaertiges-amt.de"}
WHITELISTED_USERNAMES: Set[str] = {BOT_USERNAME, "@Vi_Ka1401", "@Tna_jy"}

# Pre-compiled regex patterns
URL_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z]{2,}(?:/[^ ]*)?',
    re.IGNORECASE
)
USERNAME_PATTERN = re.compile(r'@\w+', re.IGNORECASE)

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
        print(f"Error loading cuss words: {e}")
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
    
    # Check URLs
    url_match = URL_PATTERN.search(text_lower)
    if url_match:
        url = url_match.group(0)
        domain = urlparse(url if url.startswith("http") else "http://" + url).hostname
        if domain and not any(domain.endswith(wl) for wl in WHITELISTED_DOMAINS):
            return True

    # Check entities
    if entities:
        for entity in entities:
            if entity.type in ("url", "text_link"):
                url = entity.url if entity.type == "text_link" else text[entity.offset:entity.offset + entity.length]
                domain = urlparse(url).hostname
                if domain and not any(domain.endswith(wl) for wl in WHITELISTED_DOMAINS):
                    return True

    # Check cuss words
    if CUSS_WORDS_PATTERN.search(normalize_text(text_lower)):
        return True

    # Check usernames
    usernames = USERNAME_PATTERN.findall(text)
    return usernames and not all(u in WHITELISTED_USERNAMES for u in usernames)


def contains_link(text: str, entities: Optional[list[MessageEntity]] = None) -> bool:
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
    normalized_text = remove_duplicate_letters(text.lower())
    return bool(CUSS_WORDS_PATTERN.search(normalized_text))


def get_user_display_name(user) -> str:
    """Get user's display name."""
    return user.first_name or f"@{user.username}" or f"کاربر {user.id}"


# Bot setup
session = AiohttpSession(proxy=PROXY_URL) if ENVIRONMENT == "development" and PROXY_URL else None
bot = Bot(token=BOT_TOKEN, session=session) if session else Bot(token=BOT_TOKEN)
dispatcher = Dispatcher()

# Moderation actions
async def apply_restriction(message: Message, user_id: int, user_mention: str, 
                          max_warnings: int, action: str) -> None:
    """Apply mute or ban restriction."""
    try:
        if action == "mute":
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=int(message.date.timestamp()) + MUTE_DURATION
            )
            duration_text = f"{MUTE_DURATION // 3600} ساعت"
        else:  # ban
            await bot.ban_chat_member(chat_id=message.chat.id, user_id=user_id)
            duration_text = "همیشه"

        await message.answer(
            f"به دلیل {max_warnings} تخلف از قوانین گروه، {user_mention} برای {duration_text} محدود شد.",
            parse_mode="Markdown"
        )
    except TelegramAPIError as e:
        print(f"Failed to apply restriction: {e}")

# Handlers
@dispatcher.message(lambda m: m.chat.type in ("group", "supergroup"))
async def moderate_message(message: Message) -> None:
    if not message.text or not message.from_user or message.chat.id not in SPECIFIC_GROUP_IDS:
        return
    
    settings = SPECIFIC_GROUP_IDS[message.chat.id]
    if not settings["active"]:
        return
    
    user_id = message.from_user.id
    chat_member = await bot.get_chat_member(chat_id=message.chat.id, user_id=user_id)
    if chat_member.status in ("administrator", "creator"):
        return
    
    if contains_violation(message.text, message.entities):
        try:
            await message.delete()
            WARNINGS[user_id] += 1
            user_mention = f"[{get_user_display_name(message.from_user)}](tg://user?id={user_id})"

            if WARNINGS[user_id] >= settings["max_warnings"]:
                await apply_restriction(message, user_id, user_mention, 
                                     settings["max_warnings"], settings["action"])
                WARNINGS[user_id] = 0
            else:
                await message.answer(
                    f"اخطار {WARNINGS[user_id]}/{settings['max_warnings']} برای {user_mention}: "
                    "لینک‌ها، نام‌های کاربری غیرمجاز و کلمات نامناسب ممنوع است!",
                    parse_mode="Markdown"
                )
        except TelegramAPIError as e:
            print(f"Moderation error: {e}")
                    
@dispatcher.message(lambda m: m.chat.type == "private")
async def private_chat_handler(message: Message) -> None:
    
    if message.from_user.id != ALLOWED_USER_ID:
        await message.reply(
            "Sorry, only a specified user is allowed to message me in private.\n\n"
            "For contact with me, please first message my creator @nimodb."
        )
        return

    if message.text == "Add the bot to group":
        await message.reply(
            "🤖 To add the bot to your group, please click the provided link and select your desired group.\n\n"
            f"🌐 [Click here](https://t.me/{BOT_USERNAME.replace('@', '')}?startgroup=true&admin=delete_messages+restrict_members+invite_users)\n\n"
            "❗️To add the bot to a group, the 'Add Administrators' permission is required.\n"
            "If you can’t add the bot, you may need to ask the group owner to do it.",
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=None
        )
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Add the bot to group")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.reply(
            "Please add the bot to your group to use it:",
            reply_markup=keyboard
        )


# Startup and main
async def on_startup():
    print("Mute Master Bot is online!")

async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set!")
    
    try:
        await on_startup()
        await dispatcher.start_polling(bot)
    except Exception as e:
        print(f"Main loop error: {e}")
        raise
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())