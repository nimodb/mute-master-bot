import asyncio
import json
import re
import os
from dotenv import load_dotenv
from urllib.parse import urlparse
from typing import Optional
from collections import defaultdict
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Message, ChatPermissions, MessageEntity, KeyboardButton, ReplyKeyboardMarkup


load_dotenv()

# Environment detection
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
PROXY_URL = os.getenv("PROXY_URL")
BOT_USERNAME = "@mute_master_bot"

# Moderation settings
WARNINGS = defaultdict(int)
MUTE_DURATION = 86400 # 24 hours in seconds

# Load cuss words from file
def load_cuss_words(file_path: str = "cuss_words.json") -> re.Pattern:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            cuss_dict = json.load(f)
        # Flatten all cuss words into one list
        all_cuss_words = [word.lower() for lang_words in cuss_dict.values() for word in lang_words]
        # Escape special regex characters and join with | (OR), adding word boundaries
        pattern = r'\b(?:' + '|'.join(re.escape(word) for word in all_cuss_words) + r')\b'
        return re.compile(pattern)
    except FileNotFoundError:
        print(f"Error: File {file_path} not found. Using empty dictionary.")
        return re.compile(r'^$')  # Empty pattern if file missing
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}. Using empty dictionary.")
        return re.compile(r'^$')

CUSS_WORDS_PATTERN = load_cuss_words()
WHITELISTED_DOMAINS = {"visametric.com", "teheran.diplo.de", "auswaertiges-amt.de"}
WHITELISTED_USERNAMES = {BOT_USERNAME, "@Vi_Ka1401", "@Tna_jy"}
SPECIFIC_GROUP_IDS = {
    -1002336037736: {"active": True, "max_warnings": 3, "action": "mute"},
    -1002447378789: {"active": True, "max_warnings": 3, "action": "mute"},
}

URL_PATTERN = re.compile(
        r'(?:https?://)?'  # Optional http:// or https://
        r'(?:www\.)?'      # Optional www.
        r'[a-zA-Z0-9]'     # Domain must start with alphanumeric
        r'[a-zA-Z0-9-]*'   # Domain name characters
        r'\.[a-zA-Z]{2,}'  # TLD (e.g., .com, .org, .co.uk)
        r'(?:/[^ ]*)?'     # Optional path without spaces
    )
USERNAME_PATTERN = re.compile(r'@\w+')


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

def contains_username(text: str) -> bool:
    matches = USERNAME_PATTERN.findall(text)
    if not matches:
        return False
    return not all(match in WHITELISTED_USERNAMES for match in matches)

def get_user_display_name(message: Message) -> str:
    user = message.from_user
    if user.first_name:
        return user.first_name
    elif user.username:
        return f"@{user.username}"
    else:
        return f"کاربر {user.id}"


if ENVIRONMENT == "development" and PROXY_URL:
    session = AiohttpSession(proxy=PROXY_URL)
    bot = Bot(token=BOT_TOKEN,session=session)
else:
    bot = Bot(token=BOT_TOKEN)
    
dispatcher = Dispatcher()


async def mute_user(message: Message, user_id: int, user_mention: str, max_warnings: int) -> None:
    await bot.restrict_chat_member(
        chat_id=message.chat.id,
        user_id=user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=int(asyncio.get_event_loop().time()) + MUTE_DURATION,
        #! until_date=int(message.date.timestamp()) + MUTE_DURATION,
    )
    await message.answer(
        f"به دلیل {max_warnings} تخلف از قوانین گروه، {user_mention} برای {MUTE_DURATION // 60} دقیقه محدود شد.",
        parse_mode="Markdown"
    )


async def ban_user(message: Message, user_id: int, user_mention: str, max_warnings: int) -> None:
    await bot.ban_chat_member(
        chat_id=message.chat.id,
        user_id=user_id
    )
    await message.answer(
        f"به دلیل {max_warnings} تخلف از قوانین گروه، {user_mention} برای همیشه از گروه اخراج شد.",
        parse_mode="Markdown"
    )


# Group message handler
@dispatcher.message(lambda message: message.chat.type in ("group", "supergroup"))
async def moderate_message(message: Message) -> None:
    text = message.text
    chat_id = message.chat.id
    
    if not text or not message.from_user:
        return
    
    if chat_id not in SPECIFIC_GROUP_IDS or not SPECIFIC_GROUP_IDS[chat_id]["active"]:
        return
    
    user_id = message.from_user.id
    chat_member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    if chat_member.status in ("administrator", "creator"):
        return
    
    display_name = get_user_display_name(message)
    
    # Get group-specific settings
    group_settings = SPECIFIC_GROUP_IDS[chat_id]
    max_warnings = group_settings["max_warnings"]
    action_type = group_settings["action"]
    
    # Check for links and Cuss Words
    if contains_link(text, message.entities) or contains_cuss_word(text) or contains_username(text):
        try:
            await message.delete()
            WARNINGS[user_id] += 1
            user_mention = f"[{display_name}](tg://user?id={user_id})"
            
            if WARNINGS[user_id] >= max_warnings:
                if action_type == "mute":
                    await mute_user(message, user_id, user_mention, max_warnings)
                elif action_type == "ban":
                    await ban_user(message, user_id, user_mention, max_warnings)
                    
                WARNINGS[user_id] = 0 # Reset warning after mute
            else:
                await message.answer(
                    f"اخطار {WARNINGS[user_id]}/{max_warnings} برای {user_mention}: "
                    f"لینک‌ها و نام‌های کاربری (به جز موارد مجاز) و کلمات نامناسب در این گروه ممنوع است!",
                    parse_mode="Markdown"
                )
        except Exception as e:
            print(f"Error moderating message: {e}")


# Private chat message handler
@dispatcher.message(lambda message: message.chat.type == "private")
async def private_chat_handler(message: Message) -> None:
    ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")
    
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


# Startup message
async def on_startup():
    print("Mute Master Bot is online!")


# Main function
async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")
    try:
        await on_startup()
        await dispatcher.start_polling(bot)
    except Exception as e:
        print(f"Main loop error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())