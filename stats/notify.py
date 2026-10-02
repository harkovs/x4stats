import json
import urllib.parse
import urllib.request


class TelegramNotifier:
    """Sends event messages through a Telegram bot (Bot API sendMessage)."""

    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, text):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": self.chat_id, "text": text}).encode()
        try:
            with urllib.request.urlopen(url, data=data, timeout=10) as resp:
                return json.load(resp).get("ok", False)
        except Exception as e:
            # never let a failed notification break loading a save
            print(" * Telegram notification failed:", type(e).__name__, e)
            return False


def format_event(event):
    what = "destroyed" if event["kind"] == "destroyed" else "attacked and forced to flee"
    name = event["name"] + (f" ({event['code']})" if event.get("code") else "")
    lines = [f"X4: {name} was {what}"]
    for label, key in (("Location", "location"), ("Commander", "commander"), ("By", "attacker")):
        if event.get(key):
            lines.append(f"{label}: {event[key]}")
    return "\n".join(lines)
