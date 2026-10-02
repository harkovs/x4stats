# SAVE_LOCATION can be a specific file or a directory. When the update button on the dashboard is clicked, the program
# will check whether a file in the directory is newer than the current file or if the single file has been updated.
SAVE_LOCATION = r"C:\Users\<your_username>\Documents\Egosoft\X4\<random_number>\save"

# Optional settings (defaults shown)

# How often to check SAVE_LOCATION for a newer save in the background, in seconds. 0 = only on "Update save".
# AUTO_RELOAD_SECONDS = 60

# Local SQLite history of destroyed/attacked ships and stations, per game.
# EVENTS_DB = "stats/saves/events.sqlite"

# Telegram alerts for newly detected losses. Create a bot with @BotFather for the token; the chat id is your own
# user id (message the bot, then open https://api.telegram.org/bot<token>/getUpdates to find it).
# TELEGRAM_BOT_TOKEN = "123456:ABC..."
# TELEGRAM_CHAT_ID = "123456789"
# Also alert when a ship is attacked and forced to flee (can be noisy).
# TELEGRAM_NOTIFY_ATTACKS = False
