import os


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

TIMEFRAME = os.getenv("TIMEFRAME", "15m")
SCAN_LIMIT = env_int("SCAN_LIMIT", 120)
SLEEP_SECONDS = env_int("SLEEP_SECONDS", 60)
CANDLE_LIMIT = env_int("CANDLE_LIMIT", 200)

# Geriye uyumluluk için eski env kalsın
MIN_QUOTE_VOLUME_24H = env_float("MIN_QUOTE_VOLUME_24H", 10_000_000)

EXCLUDED_SYMBOLS = {
    s.strip().upper()
    for s in os.getenv(
        "EXCLUDED_SYMBOLS",
        "BTCUSDT,ETHUSDT,XRPUSDT,SOLUSDT,BNBUSDT",
    ).split(",")
    if s.strip()
}

# Pump mode
PUMP_MIN_QUOTEVOL24H = env_float("PUMP_MIN_QUOTEVOL24H", 15_000_000)
PUMP_MAX_QUOTEVOL24H = env_float("PUMP_MAX_QUOTEVOL24H", 250_000_000)
PUMP_MIN_MARKETCAP = env_float("PUMP_MIN_MARKETCAP", 100_000_000)
PUMP_MAX_MARKETCAP = env_float("PUMP_MAX_MARKETCAP", 5_000_000_000)
PUMP_EMA_FAST = env_int("PUMP_EMA_FAST", 9)
PUMP_EMA_MID = env_int("PUMP_EMA_MID", 21)
PUMP_EMA_TREND = env_int("PUMP_EMA_TREND", 55)
PUMP_MIN_VOL_RATIO = env_float("PUMP_MIN_VOL_RATIO", 1.8)

# Dip mode
DIP_MIN_QUOTEVOL24H = env_float("DIP_MIN_QUOTEVOL24H", 20_000_000)
DIP_MAX_QUOTEVOL24H = env_float("DIP_MAX_QUOTEVOL24H", 800_000_000)
DIP_MIN_MARKETCAP = env_float("DIP_MIN_MARKETCAP", 150_000_000)
DIP_MAX_MARKETCAP = env_float("DIP_MAX_MARKETCAP", 15_000_000_000)
DIP_EMA_FAST = env_int("DIP_EMA_FAST", 11)
DIP_EMA_MID = env_int("DIP_EMA_MID", 29)
DIP_EMA_TREND = env_int("DIP_EMA_TREND", 55)
DIP_MIN_VOL_RATIO = env_float("DIP_MIN_VOL_RATIO", 1.1)
