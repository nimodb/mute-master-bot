import logging
from typing import Dict

from aiogram import Bot, Dispatcher, F
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

        groups[group_id_str] = {
            "active": True,
            "max_warnings": 3,
            "action": "mute",
            "language": "en",
            "name": chat.title if chat.title else "Unnamed Group",
            "mute_duration_seconds": config.DEFAULT_MUTE_DURATION_SECONDS,
            "whitelisted_domains": list(config.DEFAULT_WHITELISTED_DOMAINS),
            "whitelisted_usernames": list(config.DEFAULT_WHITELISTED_USERNAMES),
            "whitelisted_tlds": list(config.DEFAULT_WHITELISTED_TLDS)
        }
        save_json_file(groups, config.GROUPS_FILE)
        await message.reply(messages.get("group_added", "Group added.").format(group_id=group_id))
        logger.info("Group %d added by admin %d.", group_id, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_addgroup", "Usage: /addgroup <group_id>"))

async def set_mute_duration(message: Message, groups: Dict, messages: Dict):
    try:
        _, group_id_str, duration_str = message.text.split()
        if group_id_str not in groups:
            await message.reply(messages.get("group_not_monitored", "This group is not monitored."))
            return
        duration = int(duration_str)
        if duration <= 0:
            await message.reply(messages.get("duration_must_be_positive", "Duration must be a positive integer."))
            return
        groups[group_id_str]["mute_duration_seconds"] = duration
        save_json_file(groups, config.GROUPS_FILE)
        await message.reply(messages.get("mute_duration_set", "Mute duration set to {duration} seconds for group {group_id}.").format(duration=duration, group_id=group_id_str))
        logger.info("Mute duration for group %s set to %d by admin %d.", group_id_str, duration, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_setmuteduration", "Usage: /setmuteduration <group_id> <seconds>"))

async def set_whitelisted_domains(message: Message, groups: Dict, messages: Dict):
    try:
        _, group_id_str, *domains = message.text.split()
        if group_id_str not in groups:
            await message.reply(messages.get("group_not_monitored", "This group is not monitored."))
            return
        groups[group_id_str]["whitelisted_domains"] = domains
        save_json_file(groups, config.GROUPS_FILE)
        await message.reply(messages.get("whitelisted_domains_set", "Whitelisted domains set to {domains} for group {group_id}.").format(domains=", ".join(domains), group_id=group_id_str))
        logger.info("Whitelisted domains for group %s set to %s by admin %d.", group_id_str, domains, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_setwhitelisteddomains", "Usage: /setwhitelisteddomains <group_id> <domain1> <domain2> ..."))

async def set_whitelisted_usernames(message: Message, groups: Dict, messages: Dict):
    try:
        _, group_id_str, *usernames = message.text.split()
        if group_id_str not in groups:
            await message.reply(messages.get("group_not_monitored", "This group is not monitored."))
            return
        groups[group_id_str]["whitelisted_usernames"] = [u for u in usernames if u.startswith("@")]
        save_json_file(groups, config.GROUPS_FILE)
        await message.reply(messages.get("whitelisted_usernames_set", "Whitelisted usernames set to {usernames} for group {group_id}.").format(usernames=", ".join(usernames), group_id=group_id_str))
        logger.info("Whitelisted usernames for group %s set to %s by admin %d.", group_id_str, usernames, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_setwhitelistedusernames", "Usage: /setwhitelistedusernames <group_id> <@username1> <@username2> ..."))

async def set_whitelisted_tlds(message: Message, groups: Dict, messages: Dict):
    try:
        _, group_id_str, *tlds = message.text.split()
        if group_id_str not in groups:
            await message.reply(messages.get("group_not_monitored", "This group is not monitored."))
            return
        groups[group_id_str]["whitelisted_tlds"] = [tld for tld in tlds if tld.startswith(".")]
        save_json_file(groups, config.GROUPS_FILE)
        await message.reply(messages.get("whitelisted_tlds_set", "Whitelisted TLDs set to {tlds} for group {group_id}.").format(tlds=", ".join(tlds), group_id=group_id_str))
        logger.info("Whitelisted TLDs for group %s set to %s by admin %d.", group_id_str, tlds, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_setwhitelistedtlds", "Usage: /setwhitelistedtlds <group_id> <.tld1> <.tld2> ..."))

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
        messages.get("list_group_item", "ID: `{gid}` - Name: {name} - Active: {active}, Warns: {warns}, Action: {action}, Lang: {lang}, Mute Duration: {mute_duration}s").format(
            gid=gid,
            name=s.get("name", "N/A"),
            active=s.get("active", False),
            warns=s.get("max_warnings", "N/A"),
            action=s.get("action", "N/A"),
            lang=s.get("language", "N/A"),
            mute_duration=s.get("mute_duration_seconds", config.DEFAULT_MUTE_DURATION_SECONDS)
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

async def handle_private_message(message: Message, bot: Bot, groups: Dict, messages: Dict):
    """Handles private messages based on user authorization with detailed logging."""
    logger = logging.getLogger(__name__)
    user_id = message.from_user.id
    logger.info("Received private message from user %d: %s", user_id, message.text or "No text")

    if message.from_user.id == config.ALLOWED_USER_ID:
        logger.info("Authorized user %d accessed private commands", user_id)
        text = message.text or ""
        if not text.startswith("/"):
            await message.answer(
                messages.get("invalid_private_message", "Please use one of the following commands:\n\n*Available Commands:*\n- `/addgroup <group_id>`: Add a group for moderation.\n- `/setwarnings <group_id> <number>`: Set maximum warnings.\n- `/setaction <group_id> <mute|ban>`: Set action.\n- `/setmuteduration <group_id> <seconds>`: Set mute duration.\n- `/setwhitelisteddomains <group_id> <domain1> <domain2> ...`: Set whitelisted domains.\n- `/setwhitelistedusernames <group_id> <@username1> <@username2> ...`: Set whitelisted usernames.\n- `/setwhitelistedtlds <group_id> <.tld1> <.tld2> ...`: Set whitelisted TLDs.\n- `/toggleactive <group_id>`: Enable/disable moderation.\n- `/setlanguage <group_id> <en|fa>`: Set group language.\n- `/setuserlanguage <en|fa>`: Set user language.\n- `/listgroups`: List monitored groups.\n- `/removegroup <group_id>`: Remove a group."),
                parse_mode="Markdown"
            )
        else:
            logger.debug("Command '%s' processed for authorized user %d", text, user_id)
    else:
        user_info = {
            "user_id": user_id,
            "username": message.from_user.username or "N/A",
            "first_name": message.from_user.first_name or "N/A",
            "last_name": message.from_user.last_name or "N/A",
            "language_code": message.from_user.language_code or "N/A",
            "is_bot": message.from_user.is_bot,
            "message_text": message.text or "N/A"
        }
        logger.warning("Unauthorized user attempted private interaction: %s", user_info)
        await message.answer(messages.get("private_unauthorized", "Sorry, only authorized users can interact with me privately. Contact @nimodb for support."))

async def show_group_info(message: Message, groups: Dict, messages: Dict):
    """Displays detailed information for a specified group."""
    try:
        _, group_id_str = message.text.split()
        if group_id_str not in groups:
            await message.reply(messages.get("group_not_monitored", "This group is not monitored."))
            return
        
        group_info = groups[group_id_str]
        info_text = messages.get("group_info", "Group Info for ID: `{group_id}`\n- Name: {name}\n- Active: {active}\n- Max Warnings: {max_warnings}\n- Action: {action}\n- Language: {lang}\n- Mute Duration: {mute_duration} seconds\n- Whitelisted Domains: {domains}\n- Whitelisted Usernames: {usernames}\n- Whitelisted TLDs: {tlds}").format(
            group_id=group_id_str,
            name=group_info.get("name", "N/A"),
            active=group_info.get("active", False),
            max_warnings=group_info.get("max_warnings", "N/A"),
            action=group_info.get("action", "N/A"),
            lang=group_info.get("language", "N/A"),
            mute_duration=group_info.get("mute_duration_seconds", config.DEFAULT_MUTE_DURATION_SECONDS),
            domains=", ".join(group_info.get("whitelisted_domains", [])) or "None",
            usernames=", ".join(group_info.get("whitelisted_usernames", [])) or "None",
            tlds=", ".join(group_info.get("whitelisted_tlds", [])) or "None"
        )
        print(info_text)
        await message.reply(info_text)
        logger.info("Group info for %s displayed by admin %d.", group_id_str, message.from_user.id)
    except (IndexError, ValueError):
        await message.reply(messages.get("usage_showgroupinfo", "Usage: /showgroupinfo <group_id>"))
    except Exception as e:
        logger.error("Failed to show group info for %s: %s", group_id_str, e)
        await message.reply(messages.get("error_showing_group_info", "Error retrieving group information. Check logs."))

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
    dp.message.register(set_mute_duration, Command("setmuteduration"), admin_filter)
    dp.message.register(set_whitelisted_domains, Command("setwhitelisteddomains"), admin_filter)
    dp.message.register(set_whitelisted_usernames, Command("setwhitelistedusernames"), admin_filter)
    dp.message.register(set_whitelisted_tlds, Command("setwhitelistedtlds"), admin_filter)
    dp.message.register(show_group_info, Command("showgroupinfo"), admin_filter)
    dp.message.register(handle_private_message, F.chat.type == "private")
