import os
import re
import json
import logging
from functools import lru_cache
from dotenv import load_dotenv
from pathlib import Path
from typing import Set

# Load environment variables from .env file
load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")

# --- Core Settings ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parents[0]  # This will be the 'src/mute_master_bot' directory
CONFIG_DIR = BASE_DIR.parent.parent / "config"
LOGS_DIR = BASE_DIR.parent.parent / "logs"

GROUPS_FILE = CONFIG_DIR / "groups.json"
USER_SETTINGS_FILE = CONFIG_DIR / "user_settings.json"
MESSAGES_FILE = CONFIG_DIR / "messages.json"
CUSS_WORDS_FILE = CONFIG_DIR / "cuss_words.json"
LOG_FILE = LOGS_DIR / "mute_master_bot.log"

# --- Bot Constants ---
BOT_USERNAME = "@mute_master_bot"
MUTE_DURATION_SECONDS = 86400  # 24 hours

# --- Moderation Actions ---
ACTION_MUTE = "mute"
ACTION_BAN = "ban"
SUPPORTED_LANGUAGES = {"en", "fa"}

# --- Whitelists ---
WHITELISTED_DOMAINS: Set[str] = {"visametric.com"}
WHITELISTED_USERNAMES: Set[str] = {BOT_USERNAME, "@Vi_Ka1401", "@Tna_jy"}
WHITELISTED_TLDS: Set[str] = {".de"}

# --- Pre-compiled Regex Patterns ---
URL_PATTERN = re.compile(r'(?:https?://)?(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z]{2,}(?:/[^ ]*)?', re.IGNORECASE)
USERNAME_PATTERN = re.compile(r'@\w+', re.IGNORECASE)

# --- Cuss Words Pattern ---
@lru_cache(maxsize=1)
def load_cuss_words() -> re.Pattern:
    """Loads cuss words from JSON and compiles them into a single regex pattern."""
    try:
        with open(CUSS_WORDS_FILE, "r", encoding="utf-8") as f:
            cuss_dict = json.load(f)
        all_cuss_words = [word.lower() for lang_words in cuss_dict.values() for word in lang_words]
        if not all_cuss_words:
            return re.compile(r'^$') # Return a pattern that never matches
        pattern = r'\b(?:' + '|'.join(map(re.escape, all_cuss_words)) + r')\b'
        return re.compile(pattern, re.IGNORECASE)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.getLogger(__name__).error("Failed to load cuss words from %s: %s. No cuss word filtering will occur.", CUSS_WORDS_FILE, e)
        return re.compile(r'^$') # Return a pattern that never matches

CUSS_WORDS_PATTERN = load_cuss_words()