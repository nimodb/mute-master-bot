import logging
from typing import Dict

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

from .. import config
from ..filters import AdminFilter
from ..utils.file_ops import save_json_file, load_json_file
from ..middlewares import USER_SETTINGS # Import the loaded settings

logger = logging.getLogger(__name__)

async def add_group(message: Message, bot: Bot, groups: Dict, messages: Dict):
    try:
        group_id = int(message.text.split()[1])
        group_id_str = str(group_id)
        if group_id_str in groups:
            await message.reply(messages.get("group_already_monitored", "This group is already monitored."))
            return

        try:
            chat = await bot.get_chat(group_id)
            if chat.type not in ("group", "supergroup"):
                raise TelegramAPIError("Not a group or supergroup.")
        except TelegramAPIError:
            await message.reply(messages.get("bot_not_in_group", "Bot is not a member of this group or the ID is invalid."))
            return

        groups[group_id_str] = {"active": True, "max_warnings": 3, "action": "mute", "language": "en"}
        save_json_file(groups, config.GROUPS_FILE)
        await message.reply(messages.get("group_added", "Group added.").format(group_id=group_id))
        logger.info("Group %d added by admin %d.", group_id, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_addgroup", "Usage: /addgroup <group_id>"))

async def set_warnings(message: Message, groups: Dict, messages: Dict):
    try:
        _, group_id_str, warnings_str = message.text.split()
        if group_id_str not in groups:
            await message.reply(messages.get("group_not_monitored", "This group is not monitored."))
            return
        
        warnings = int(warnings_str)
        if warnings < 1:
            await message.reply(messages.get("warnings_must_be_positive", "Number of warnings must be a positive integer."))
            return
            
        groups[group_id_str]["max_warnings"] = warnings
        save_json_file(groups, config.GROUPS_FILE)
        await message.reply(messages.get("max_warnings_set", "Max warnings set.").format(warnings=warnings, group_id=group_id_str))
        logger.info("Max warnings for group %s set to %d by admin %d.", group_id_str, warnings, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_setwarnings", "Usage: /setwarnings <group_id> <number>"))

async def set_action(message: Message, groups: Dict, messages: Dict):
    try:
        _, group_id_str, action = message.text.split()
        action = action.lower()
        if group_id_str not in groups:
            await message.reply(messages.get("group_not_monitored", "This group is not monitored."))
            return
        if action not in (config.ACTION_MUTE, config.ACTION_BAN):
            await message.reply(messages.get("action_must_be_mute_or_ban", "Action must be 'mute' or 'ban'."))
            return
        
        groups[group_id_str]["action"] = action
        save_json_file(groups, config.GROUPS_FILE)
        await message.reply(messages.get("action_set", "Action set.").format(action=action, group_id=group_id_str))
        logger.info("Action for group %s set to '%s' by admin %d.", group_id_str, action, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_setaction", "Usage: /setaction <group_id> <mute|ban>"))

async def toggle_active(message: Message, groups: Dict, messages: Dict):
    try:
        _, group_id_str = message.text.split()
        if group_id_str not in groups:
            await message.reply(messages.get("group_not_monitored", "This group is not monitored."))
            return
            
        current_status = groups[group_id_str].get("active", False)
        groups[group_id_str]["active"] = not current_status
        save_json_file(groups, config.GROUPS_FILE)
        
        status_key = "moderation_enabled" if not current_status else "moderation_disabled"
        status_text = messages.get(status_key, f"Moderation {'enabled' if not current_status else 'disabled'}.")
        
        await message.reply(status_text.format(group_id=group_id_str))
        logger.info("Moderation for group %s %s by admin %d.", group_id_str, 'enabled' if not current_status else 'disabled', message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_toggleactive", "Usage: /toggleactive <group_id>"))

async def set_language(message: Message, groups: Dict, messages: Dict):
    try:
        _, group_id_str, lang = message.text.split()
        lang = lang.lower()
        if group_id_str not in groups:
            await message.reply(messages.get("group_not_monitored", "This group is not monitored."))
            return
        if lang not in config.SUPPORTED_LANGUAGES:
            await message.reply(messages.get("language_not_supported", "This language is not supported."))
            return

        groups[group_id_str]["language"] = lang
        save_json_file(groups, config.GROUPS_FILE)
        await message.reply(messages.get("language_set_group", "Group language set.").format(language=lang, group_id=group_id_str))
        logger.info("Language for group %s set to '%s' by admin %d.", group_id_str, lang, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_setlanguage", "Usage: /setlanguage <group_id> <en|fa>"))

async def set_user_language(message: Message, messages: Dict):
    try:
        _, lang = message.text.split()
        lang = lang.lower()
        if lang not in config.SUPPORTED_LANGUAGES:
            await message.reply(messages.get("language_not_supported", "This language is not supported."))
            return
        
        user_id_str = str(message.from_user.id)
        USER_SETTINGS[user_id_str] = {"language": lang}
        save_json_file(USER_SETTINGS, config.USER_SETTINGS_FILE)
        
        # We reply using the NEW language's message pack
        new_messages = load_json_file(config.MESSAGES_FILE).get(lang, {})
        await message.reply(new_messages.get("user_language_set", "Your language has been set.").format(language=lang))
        logger.info("Admin user %s set their language to '%s'.", user_id_str, lang)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_setuserlanguage", "Usage: /setuserlanguage <en|fa>"))

async def list_groups(message: Message, groups: Dict, messages: Dict):
    if not groups:
        await message.reply(messages.get("no_groups_monitored", "No groups are being monitored."))
        return
    
    group_list = [
        messages.get("list_group_item", "ID: `{gid}` - Active: {active}, Warns: {warns}, Action: {action}, Lang: {lang}").format(
            gid=gid,
            active=s.get("active", False),
            warns=s.get("max_warnings", "N/A"),
            action=s.get("action", "N/A"),
            lang=s.get("language", "N/A")
        )
        for gid, s in groups.items()
    ]
    
    response = messages.get("monitored_groups_header", "Monitored Groups:") + "\n\n" + "\n".join(group_list)
    await message.reply(response, parse_mode="Markdown")

async def remove_group(message: Message, groups: Dict, messages: Dict):
    try:
        _, group_id_str = message.text.split()
        if group_id_str not in groups:
            await message.reply(messages.get("group_not_monitored", "This group is not monitored."))
            return
        
        del groups[group_id_str]
        save_json_file(groups, config.GROUPS_FILE)
        await message.reply(messages.get("group_removed", "Group removed from monitoring.").format(group_id=group_id_str))
        logger.info("Group %s removed by admin %d.", group_id_str, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_removegroup", "Usage: /removegroup <group_id>"))

def register(dp: Dispatcher):
    """Registers all admin command handlers for private chat."""
    admin_filter = AdminFilter()
    dp.message.register(add_group, Command("addgroup"), admin_filter)
    dp.message.register(set_warnings, Command("setwarnings"), admin_filter)
    dp.message.register(set_action, Command("setaction"), admin_filter)
    dp.message.register(toggle_active, Command("toggleactive"), admin_filter)
    dp.message.register(set_language, Command("setlanguage"), admin_filter)
    dp.message.register(set_user_language, Command("setuserlanguage"), admin_filter)
    dp.message.register(list_groups, Command("listgroups"), admin_filter)
    dp.message.register(remove_group, Command("removegroup"), admin_filter)