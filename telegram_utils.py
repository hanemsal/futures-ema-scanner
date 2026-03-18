import requests
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")


def _fmt_num(value, digits=2, default="-"):
    try:
        if value is None:
            return default
        return f"{float(value):.{digits}f}"
    except Exception:
        return default


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
    entry_reason,
    vol_ratio_entry,
    body_ratio_entry,
    candle_type,
    ema_fast=8,
    ema_mid=18,
    ema_trend=34,
    rsi_m=None,
    rsi_w=None,
    rsi_d=None,
    change_1h=None,
    change_4h=None,
):
    now = datetime.now(ISTANBUL_TZ).strftime("%Y-%m-%d %H:%M TRT")

    side_icon = "🟢" if str(side).upper() == "LONG" else "🔴"

    message = f"""
🚀 <b>PUMP HUNTER SIGNAL</b>

<b>Coin:</b> {escape(str(symbol))}
<b>Side:</b> {side_icon} {escape(str(side))}
<b>Entry Price:</b> {escape(str(price))}
<b>Timeframe:</b> {escape(str(timeframe))}

<b>Entry Reason:</b> {escape(str(entry_reason))}
<b>EMA Set:</b> {escape(str(ema_fast))} / {escape(str(ema_mid))} / {escape(str(ema_trend))}

<b>Volume Ratio:</b> {_fmt_num(vol_ratio_entry, 2)}
<b>Body Ratio:</b> {_fmt_num(body_ratio_entry, 2)}
<b>Candle Type:</b> {escape(str(candle_type or '-'))}

<b>RSI M / W / D:</b> {escape(_fmt_num(rsi_m, 2))} / {escape(_fmt_num(rsi_w, 2))} / {escape(_fmt_num(rsi_d, 2))}
<b>1H / 4H %:</b> {escape(_fmt_num(change_1h, 2))}% / {escape(_fmt_num(change_4h, 2))}%

<b>Time:</b> {escape(now)}
━━━━━━━━━━━━━━━━
"""
    return message.strip()



def format_exit_message(
    symbol,
    side,
    mode,
    exit_price,
    pnl_pct,
    reason,
    vol_ratio_exit=None,
    body_ratio_exit=None,
    candle_type=None,
):
    now = datetime.now(ISTANBUL_TZ).strftime("%Y-%m-%d %H:%M TRT")
    side_icon = "🟢" if str(side).upper() == "LONG" else "🔴"

    return f"""
🔴 <b>PUMP HUNTER EXIT</b>

<b>Coin:</b> {escape(str(symbol))}
<b>Side:</b> {side_icon} {escape(str(side))}
<b>Mode:</b> {escape(str(mode))}
<b>Exit Price:</b> {escape(str(round(float(exit_price), 8)) if exit_price is not None else '-')}
<b>PnL:</b> {_fmt_num(pnl_pct, 2)}%
<b>Reason:</b> {escape(str(reason))}

<b>Exit Vol Ratio:</b> {_fmt_num(vol_ratio_exit, 2)}
<b>Exit Body Ratio:</b> {_fmt_num(body_ratio_exit, 2)}
<b>Candle Type:</b> {escape(str(candle_type or '-'))}

<b>Time:</b> {escape(now)}
━━━━━━━━━━━━━━━━
""".strip()
