import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TIMEFRAME


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


def format_entry_signal(
    symbol: str,
    side: str,
    mode: str,
    price: float,
    ema_fast_val: float,
    ema_mid_val: float,
    ema_trend_val: float,
    ema_fast_len: int,
    ema_mid_len: int,
    ema_trend_len: int,
    vol_ratio: float,
    quote_vol_24h: float,
):
    icon = "🟢" if side == "LONG" else "🔻"
    return (
        f"{icon} <b>{side} SIGNAL</b>\n\n"
        f"<b>Coin:</b> {symbol}\n"
        f"<b>Mode:</b> {mode}\n"
        f"<b>Price:</b> {price:.6f}\n"
        f"<b>TF:</b> {TIMEFRAME}\n\n"
        f"<b>EMA Fast ({ema_fast_len}):</b> {ema_fast_val:.6f}\n"
        f"<b>EMA Mid ({ema_mid_len}):</b> {ema_mid_val:.6f}\n"
        f"<b>EMA Trend ({ema_trend_len}):</b> {ema_trend_val:.6f}\n"
        f"<b>Vol Ratio:</b> {vol_ratio:.2f}\n"
        f"<b>QuoteVol 24h:</b> {quote_vol_24h:.2f}"
    )


def format_exit_signal(
    symbol: str,
    side: str,
    mode: str,
    price: float,
    reason: str,
    pnl_pct: float = 0.0,
):
    icon = "🔴" if side == "LONG" else "⚪"
    return (
        f"{icon} <b>{side} EXIT</b>\n\n"
        f"<b>Coin:</b> {symbol}\n"
        f"<b>Mode:</b> {mode}\n"
        f"<b>Exit Price:</b> {price:.6f}\n"
        f"<b>Reason:</b> {reason}\n"
        f"<b>PnL:</b> {pnl_pct:.2f}%"
    )
