import requests
import os

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT = os.environ["TELEGRAM_CHAT_ID"]

def send_telegram(msg):

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"

    requests.post(
        url,
        json={
            "chat_id": CHAT,
            "text": msg
        }
    )
