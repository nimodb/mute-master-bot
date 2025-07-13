# Mute Master Bot

A Telegram moderation bot built with Python and `aiogram` to filter inappropriate content (cuss words, unauthorized links, usernames) in specific groups.

## Features
- **Content Moderation**: Deletes messages with cuss words, non-whitelisted links, or unauthorized usernames.
- **Group-Specific Settings**: Configurable warning limits and actions (mute or ban) per group.
- **Admin Exemption**: Admins and group creators are exempt from moderation.
- **Private Chat Restriction**: Only the authorized user (`@nimodb`) can interact privately.
- **Whitelist Support**: Allows specific domains (e.g., `visametric.com`) and usernames (e.g., `@mute_master_bot`).

## Folder Structure
```
mute_master_bot/
├── src/
│   └── bot.py              # Main bot script
├── config/
│   ├── .env                # Environment variables
│   ├── groups.json         # Group settings
│   ├── user_settings.json  # User language settings
│   └── cuss_words.json     # Moderation word list
├── logs/
│   └── mute_master_bot.log # Log files
├── tests/
│   └── test_bot.py         # Unit tests
├── docs/
│   └── README.md           # Documentation
├── requirements.txt        # Dependencies
└── .gitignore              # Git ignore file
```

## Setup
1. Clone the repository.
2. Create a virtual environment: `python -m venv .venv`
3. Activate it: `source .venv/bin/activate` (Linux/Mac) or `.venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Set up `.env` in `config/` with `BOT_TOKEN`, `ALLOWED_USER_ID`, and `ENVIRONMENT=production`.
6. Create `config/cuss_words.json` with moderation words.
7. Run the bot: `python src/bot.py`

## Commands
- `/addgroup <group_id>`: Add a group for moderation.
- `/setwarnings <group_id> <number>`: Set maximum warnings.
- `/setaction <group_id> <mute|ban>`: Set violation action.
- `/toggleactive <group_id>`: Enable/disable moderation.
- `/setlanguage <group_id> <en|fa>`: Set group language.
- `/setuserlanguage <en|fa>`: Set user language.
- `/listgroups`: List monitored groups.
- `/removegroup <group_id>`: Remove a group from moderation.

## Deployment
- Use a process manager (e.g., `systemd`, `supervisord`) to keep the bot running.
- Ensure `config/` is writable for `groups.json` and `user_settings.json`.
- Monitor `logs/mute_master_bot.log` for errors.

## Notes
- Commands are restricted to the authorized user in private chat.
- Logs rotate daily with a 7-day backup.
- Ensure `config/.env` is not committed to version control.