# src/mute_master_bot/utils/db.py
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[3] / "warnings.db"
print(DB_PATH)

def init_db():
    """Initialize the SQLite database with a warnings table."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS warnings (
                    user_id INTEGER,
                    chat_id INTEGER,
                    warning_count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, chat_id)
                )
            ''')
            conn.commit()
        logger.info("Database initialized at %s", DB_PATH)
    except sqlite3.Error as e:
        logger.error("Failed to initialize database: %s", e)

def get_warnings(user_id: int, chat_id: int) -> int:
    """Retrieve the warning count for a user in a chat."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT warning_count FROM warnings WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
            result = cursor.fetchone()
            return result[0] if result else 0
    except sqlite3.Error as e:
        logger.error("Failed to get warnings for user %d in chat %d: %s", user_id, chat_id, e)
        return 0

def increment_warning(user_id: int, chat_id: int) -> int:
    """Increment the warning count for a user in a chat."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO warnings (user_id, chat_id, warning_count) VALUES (?, ?, 1) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET warning_count = warning_count + 1",
                (user_id, chat_id)
            )
            conn.commit()
            return get_warnings(user_id, chat_id)
    except sqlite3.Error as e:
        logger.error("Failed to increment warning for user %d in chat %d: %s", user_id, chat_id, e)
        return 0

def reset_warnings(user_id: int, chat_id: int):
    """Reset the warning count for a user in a chat."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM warnings WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
            conn.commit()
        logger.info("Warnings reset for user %d in chat %d", user_id, chat_id)
    except sqlite3.Error as e:
        logger.error("Failed to reset warnings for user %d in chat %d: %s", user_id, chat_id, e)