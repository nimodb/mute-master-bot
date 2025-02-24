# Mute Master Bot

A Telegram moderation bot designed to maintain order in specific groups by filtering out inappropriate content like cuss words, unauthorized links, and usernames. Built with Python and the `aiogram` library.

## Features
- **Content Moderation**: Automatically deletes messages containing cuss words, non-whitelisted links, or unauthorized usernames in specified groups.
- **Group-Specific Settings**: Customizable warning limits and actions (mute or ban) per group.
- **Admin Exemption**: Admins and group creators are exempt from moderation.
- **Private Chat Restriction**: Only a specified user can interact with the bot privately; others are directed to contact the creator.
- **Whitelist Support**: Allows specific domains (e.g., `visametric.com`) and usernames (e.g., `@mute_master_bot`).

## Requirements
- Python 3.7+
- `aiogram` library (`pip install aiogram`)
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- (Optional) `python-dotenv` for local development (`pip install python-dotenv`)

## Installation
1. **Clone the Repository:**

    ```bash
    git clone https://github.com/yourusername/mute-master-bot.git
    cd mute-master-bot
    ```

2. **Install Dependencies:**

    ```bash
    pip install -r requirements.txt
    ```
    (See "Create requirements.txt" below if you don’t have this yet.)

3. **Set Up Environment Variables:**

    Create a .env file in the root directory (not tracked by Git):
    ```bash
    # .env
    ENVIRONMENT=development  # or 'production'
    BOT_TOKEN=your_bot_token_here
    PROXY_URL=http://your_proxy_url  # Optional, for development
    ALLOWED_USER_ID=your_user_id_here
    ```
    (See "Create requirements.txt" below if you don’t have this yet.)

    Or set them in your environment manually:
    ```bash
    export ENVIRONMENT=development
    export BOT_TOKEN=your_bot_token_here
    export ALLOWED_USER_ID=your_user_id_here
    ```

4. **(Optional) Add Cuss Words:**

    Create a `cuss_words.json` file with a structure like:
    ```json
    {
        "english": ["badword1", "badword2"],
        "persian": ["کلمه_زشت1", "کلمه_زشت2"]
    }
    ```

5. **Run the Bot:**

    ```bash
    python bot.py
    ```


## Usage
- **Add to Group:** Use the bot’s invite link (shown in private chat with the allowed user) to add it to a group with admin rights (`delete_messages`, `restrict_members`, `invite_users`).
- **Moderation:** The bot will only moderate groups listed in `SPECIFIC_GROUP_IDS` in `bot.py`.
- **Private Chat:** Only the user with `ALLOWED_USER_ID` can interact with the bot privately; others are redirected to `@nimodb`.


## Configuration
- **Whitelisted Domains:** Edit `WHITELISTED_DOMAINS` in `bot.py`.
- **Whitelisted Usernames:** Edit `WHITELISTED_USERNAMES` in `bot.py`.
- **Group Settings:** Modify `SPECIFIC_GROUP_IDS` to add groups and customize settings (e.g., `max_warnings`, `action`).


## Development vs Production
- **Development:** Uses a proxy session if `PROXY_URL` is set and `ENVIRONMENT=development`.
- **Production:** Uses the default session when `ENVIRONMENT=production` (no proxy).