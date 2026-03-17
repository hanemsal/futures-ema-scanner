import requests
from datetime import datetime
from html import escape


def send_telegram_message(bot_token: str, chat_id: str, message: str):
    if not bot_token or not chat_id:
        print("Telegram ayarlı değil, mesaj atlanıyor.", flush=True)
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        print("Telegram response:", response.status_code, response.text, flush=True)
    except Exception as e:
        print("Telegram send error:", e, flush=True)


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

<b>Coin:</b> {escape(str(symbol))}
<b>Side:</b> {escape(str(side))}
<b>Price:</b> {escape(str(price))}

<b>Quality:</b> {escape(str(quality))}
<b>Score:</b> {score:.1f}

<b>Setup:</b> {escape(str(setup_type))}

<b>Volume Ratio:</b> {volume_ratio:.2f}

<b>Breakout Level:</b> {escape(str(breakout_level))}

<b>EMA Set:</b> {escape(str(ema_fast))} / {escape(str(ema_mid))} / {escape(str(ema_trend))}

<b>Momentum</b>
1h Change: {change_1h:.2f}%
4h Change: {change_4h:.2f}%

<b>Timeframe:</b> {escape(str(timeframe))}

<b>Time:</b> {escape(now)}

━━━━━━━━━━━━━━━━
"""
    return message.strip()


def format_exit_message(symbol, side, mode, exit_price, pnl_pct, reason):
    return f"""
🔴 <b>PUMP HUNTER EXIT</b>

<b>Coin:</b> {escape(str(symbol))}
<b>Side:</b> {escape(str(side))}
<b>Mode:</b> {escape(str(mode))}
<b>Exit Price:</b> {escape(str(round(exit_price, 8)))}
<b>PnL:</b> {pnl_pct:.2f}%
<b>Reason:</b> {escape(str(reason))}
""".strip()
