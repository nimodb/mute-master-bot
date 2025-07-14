# Mute Master Bot

A Telegram moderation bot built with Python and `aiogram` to filter inappropriate content (cuss words, unauthorized links, usernames) in specific groups.

## Features
- **Content Moderation**: Deletes messages with cuss words, non-whitelisted links, or unauthorized usernames.
- **Group-Specific Settings**: Configurable warning limits and actions (mute or ban) per group.
- **Admin Exemption**: Admins and group creators are exempt from moderation.
- **Private Chat Restriction**: Only the authorized user (`@nimodb`) can interact privately.
- **Whitelist Support**: Allows specific domains (e.g., `visametric.com`) and usernames (e.g., `@mute_master_bot`).

## Installation
1. Clone the repository: `git clone <repository-url>`.
2. Navigate to the project directory: `cd MUTE_MASTER_BOT`.
3. Create a virtual environment: `python3 -m venv venv`.
4. Activate the virtual environment:
   - Linux/Mac: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`
5. Install dependencies: `pip install -r requirements.txt`.

## Configuration
- Create a `.env` file in the `config` directory with:
  ```
  BOT_TOKEN=your_telegram_bot_token
  ALLOWED_USER_ID=your_telegram_id
  ```
- Ensure `config/cuss_words.json`, `config/messages.json`, and `config/user_settings.json` exist with appropriate content (see example files or let the bot create defaults).

## Usage
- Run the bot: `python3 -m mute_master_bot.main`.
- Admin commands (usable only by `ALLOWED_USER_ID` in private chat):
  - `/addgroup <group_id>`: Add a group for moderation.
  - `/setwarnings <group_id> <number>`: Set maximum warnings.
  - `/setaction <group_id> <mute|ban>`: Set action for violations.
  - `/toggleactive <group_id>`: Enable/disable moderation.
  - `/setlanguage <group_id> <en|fa>`: Set group language.
  - `/setuserlanguage <en|fa>`: Set user language.
  - `/listgroups`: List monitored groups.
  - `/removegroup <group_id>`: Remove a group.

## Troubleshooting
- Check `logs/mute_master_bot.log` for errors.
- Ensure the bot has admin permissions (delete messages, restrict members) in groups.
- Verify JSON files are correctly formatted.

## Folder Structure
```
MUTE_MASTER_BOT/
├── config/
│   ├── .env
│   ├── cuss_words.json
│   ├── groups.json
│   ├── messages.json
│   └── user_settings.json
├── logs/
├── src/mute_master_bot/
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   └── moderation.py
│   ├── utils/
│   │   ├── __init__.py
│   │   └── file_ops.py
│   ├── __init__.py
│   ├── config.py
│   ├── filters.py
│   ├── main.py
│   └── middlewares.py
├── venv/
├── .gitignore
├── logo.jpg
├── README.md
└── requirements.txt
```

## License
[MIT License](LICENSE).