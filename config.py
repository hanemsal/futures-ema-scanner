import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

TIMEFRAME = os.getenv("TIMEFRAME", "15m")
SCAN_LIMIT = int(os.getenv("SCAN_LIMIT", "120"))
SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "60"))
CANDLE_LIMIT = int(os.getenv("CANDLE_LIMIT", "200"))
TOP_VOLUME_COUNT = int(os.getenv("TOP_VOLUME_COUNT", "120"))
