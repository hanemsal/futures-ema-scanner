import requests
from datetime import datetime


def send_telegram_message(bot_token: str, chat_id: str, message: str):
    if not bot_token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram send error:", e)


def format_signal_message(
    symbol,
    price,
    side,
    timeframe,
    score,
    quality,
    setup_type,
    volume_ratio,
    breakout_level,
    change_1h,
    change_4h,
    ema_fast,
    ema_mid,
    ema_trend,
):

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    message = f"""
🚀 <b>PUMP HUNTER SIGNAL</b>

<b>Coin:</b> {symbol}
<b>Side:</b> {side}
<b>Price:</b> {price}

<b>Quality:</b> {quality}
<b>Score:</b> {score:.1f}

<b>Setup:</b> {setup_type}

<b>Volume Ratio:</b> {volume_ratio:.2f}

<b>Breakout Level:</b> {breakout_level}

<b>EMA Set:</b> {ema_fast} / {ema_mid} / {ema_trend}

<b>Momentum</b>
1h Change: {change_1h:.2f}%
4h Change: {change_4h:.2f}%

<b>Timeframe:</b> {timeframe}

<b>Time:</b> {now}

━━━━━━━━━━━━━━━━
"""

    return message
