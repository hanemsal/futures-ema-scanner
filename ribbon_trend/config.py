import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ----- Exchange -----
EXCHANGE_ID = "binance"
TIMEFRAME = os.getenv("RIBBON_TIMEFRAME", "15m")
OHLCV_LIMIT = int(os.getenv("RIBBON_OHLCV_LIMIT", "260"))
QUOTE_ASSET = os.getenv("RIBBON_QUOTE_ASSET", "USDT")
ONLY_PERPETUAL = os.getenv("RIBBON_ONLY_PERPETUAL", "true").lower() == "true"
ENABLE_RATE_LIMIT = True
REQUEST_TIMEOUT_MS = int(os.getenv("RIBBON_REQUEST_TIMEOUT_MS", "20000"))
SYMBOL_PAUSE_SECONDS = float(os.getenv("RIBBON_SYMBOL_PAUSE_SECONDS", "0.12"))
LOOP_SLEEP_SECONDS = int(os.getenv("RIBBON_LOOP_SLEEP_SECONDS", "30"))
RELOAD_MARKETS_EVERY_MINUTES = int(os.getenv("RIBBON_RELOAD_MARKETS_EVERY_MINUTES", "60"))

# ----- Strategy -----
EMA_FAST = 20
EMA_MID = 50
EMA_SLOW = 100
EMA_TREND = 200
EMA200_SLOPE_LOOKBACK = int(os.getenv("RIBBON_EMA200_SLOPE_LOOKBACK", "3"))
MAX_EXTENSION_PCT = float(os.getenv("RIBBON_MAX_EXTENSION_PCT", "3.0"))
MIN_CANDLE_BODY_PCT = float(os.getenv("RIBBON_MIN_CANDLE_BODY_PCT", "0.15"))
MIN_NOTIONAL_24H_USDT = float(os.getenv("RIBBON_MIN_NOTIONAL_24H_USDT", "1500000"))

# ----- Risk / TP / SL -----
LEVERAGE = float(os.getenv("RIBBON_LEVERAGE", "5"))
TP_MOVE_PCT = float(os.getenv("RIBBON_TP_MOVE_PCT", "2.0"))
SL_MOVE_PCT = float(os.getenv("RIBBON_SL_MOVE_PCT", "2.0"))
ALLOW_LONGS = os.getenv("RIBBON_ALLOW_LONGS", "true").lower() == "true"
ALLOW_SHORTS = os.getenv("RIBBON_ALLOW_SHORTS", "true").lower() == "true"
ONE_OPEN_TRADE_PER_SYMBOL = True

# ----- Storage -----
DB_PATH = os.getenv("RIBBON_DB_PATH", str(BASE_DIR / "ribbon_signals.db"))
LOG_PATH = os.getenv("RIBBON_LOG_PATH", str(BASE_DIR / "ribbon_worker.log"))

# ----- Telegram -----
TELEGRAM_BOT_TOKEN = os.getenv("RIBBON_TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("RIBBON_TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# ----- Dashboard -----
DASHBOARD_HOST = os.getenv("RIBBON_DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("RIBBON_DASHBOARD_PORT", "8091"))
PUMP_DASHBOARD_URL = os.getenv("PUMP_DASHBOARD_URL", "http://localhost:8080")
RIBBON_DASHBOARD_TITLE = os.getenv("RIBBON_DASHBOARD_TITLE", "Ribbon Trend Panel")

# ----- Worker behavior -----
DRY_RUN = os.getenv("RIBBON_DRY_RUN", "true").lower() == "true"
CHECK_TP_SL_ON_EACH_LOOP = True
PRINT_DEBUG = os.getenv("RIBBON_PRINT_DEBUG", "true").lower() == "true"
