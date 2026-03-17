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


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

TIMEFRAME = os.getenv("TIMEFRAME", "15m")
MOMENTUM_TIMEFRAME = os.getenv("MOMENTUM_TIMEFRAME", "5m")

SLEEP_SECONDS = env_int("SLEEP_SECONDS", 30)
CANDLE_LIMIT = env_int("CANDLE_LIMIT", 220)

EXCLUDED_SYMBOLS = {
    s.strip().upper()
    for s in os.getenv(
        "EXCLUDED_SYMBOLS",
        "BTCUSDT,ETHUSDT,XRPUSDT,SOLUSDT,BNBUSDT",
    ).split(",")
    if s.strip()
}

# v2.0 kapsamı
ENABLE_PUMP_LONG = env_bool("ENABLE_PUMP_LONG", True)
ENABLE_PUMP_SHORT = env_bool("ENABLE_PUMP_SHORT", False)
ENABLE_DIP_MODE = env_bool("ENABLE_DIP_MODE", False)

# Universe
MIN_QUOTEVOL24H = env_float("MIN_QUOTEVOL24H", 5_000_000)

# EMA set
PUMP_EMA_FAST = env_int("PUMP_EMA_FAST", 9)
PUMP_EMA_MID = env_int("PUMP_EMA_MID", 21)
PUMP_EMA_TREND = env_int("PUMP_EMA_TREND", 55)

# Compression thresholds
MAX_EMA_FAST_MID_GAP_PCT = env_float("MAX_EMA_FAST_MID_GAP_PCT", 0.25)
MAX_EMA_MID_TREND_GAP_PCT = env_float("MAX_EMA_MID_TREND_GAP_PCT", 0.60)

# Breakout
BREAKOUT_LOOKBACK = env_int("BREAKOUT_LOOKBACK", 20)
BREAKOUT_NEAR_PCT = env_float("BREAKOUT_NEAR_PCT", 0.30)

# Volume
MIN_VOL_RATIO = env_float("MIN_VOL_RATIO", 1.8)
STRONG_VOL_RATIO = env_float("STRONG_VOL_RATIO", 2.2)

# Momentum priority
MIN_CHANGE_1H_PRIORITY = env_float("MIN_CHANGE_1H_PRIORITY", 4.0)
MIN_CHANGE_4H_PRIORITY = env_float("MIN_CHANGE_4H_PRIORITY", 8.0)

# Cooldown
SIGNAL_COOLDOWN_MINUTES = env_int("SIGNAL_COOLDOWN_MINUTES", 180)

# Scoring
MIN_SIGNAL_SCORE = env_float("MIN_SIGNAL_SCORE", 65.0)
A_GRADE_SCORE = env_float("A_GRADE_SCORE", 80.0)

# Exit
ARM_TRAILING_AT_PROFIT_PCT = env_float("ARM_TRAILING_AT_PROFIT_PCT", 8.0)
HARD_TP1_PCT = env_float("HARD_TP1_PCT", 8.0)
HARD_TP2_PCT = env_float("HARD_TP2_PCT", 15.0)
