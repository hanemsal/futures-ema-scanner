import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram_message(text: str):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram ayarlı değil, mesaj atlanıyor.", flush=True)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, data=payload, timeout=15)
        print("Telegram response:", response.status_code, response.text, flush=True)

    except Exception as e:
        print("Telegram gönderim hatası:", e, flush=True)


def format_long_signal(symbol: str, price: float, ema11: float, ema47: float, ema123: float):

    return (
        f"🟢 <b>LONG SIGNAL</b>\n\n"
        f"<b>Coin:</b> {symbol}\n"
        f"<b>Price:</b> {price:.6f}\n"
        f"<b>TF:</b> 15m\n\n"
        f"<b>EMA11:</b> {ema11:.6f}\n"
        f"<b>EMA47:</b> {ema47:.6f}\n"
        f"<b>EMA123:</b> {ema123:.6f}"
    )


def format_long_exit(symbol: str, price: float, reason: str, pnl_pct: float = 0.0):

    return (
        f"🔴 <b>LONG EXIT</b>\n\n"
        f"<b>Coin:</b> {symbol}\n"
        f"<b>Exit Price:</b> {price:.6f}\n"
        f"<b>Reason:</b> {reason}\n"
        f"<b>PnL:</b> {pnl_pct:.2f}%"
    )


def format_short_signal(symbol: str, price: float, ema11: float, ema29: float, ema123: float):

    return (
        f"🔻 <b>SHORT SIGNAL</b>\n\n"
        f"<b>Coin:</b> {symbol}\n"
        f"<b>Price:</b> {price:.6f}\n"
        f"<b>TF:</b> 15m\n\n"
        f"<b>EMA11:</b> {ema11:.6f}\n"
        f"<b>EMA29:</b> {ema29:.6f}\n"
        f"<b>EMA123:</b> {ema123:.6f}"
    )


def format_short_exit(symbol: str, price: float, reason: str, pnl_pct: float = 0.0):

    return (
        f"⚪ <b>SHORT EXIT</b>\n\n"
        f"<b>Coin:</b> {symbol}\n"
        f"<b>Exit Price:</b> {price:.6f}\n"
        f"<b>Reason:</b> {reason}\n"
        f"<b>PnL:</b> {pnl_pct:.2f}%"
    )
