import os
import time
from datetime import datetime, timedelta, timezone

import ccxt
import pandas as pd
import requests
from sqlalchemy import desc

from storage import SessionLocal, Signal

# =========================
# CONFIG
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "30"))
TIMEFRAME = os.getenv("TIMEFRAME", "15m")
SCAN_LIMIT = int(os.getenv("SCAN_LIMIT", "250"))
CANDLE_LIMIT = int(os.getenv("CANDLE_LIMIT", "220"))

EMA_FAST = 8
EMA_MID = 18
EMA_TREND = 34

MIN_QUOTEVOL24H = float(os.getenv("MIN_QUOTEVOL24H", "5000000"))
SIGNAL_COOLDOWN_MINUTES = int(os.getenv("SIGNAL_COOLDOWN_MINUTES", "180"))

EXCLUDED_SYMBOLS = {
    s.strip().upper()
    for s in os.getenv(
        "EXCLUDED_SYMBOLS",
        "BTCUSDT,ETHUSDT,XRPUSDT,SOLUSDT,BNBUSDT",
    ).split(",")
    if s.strip()
}

exchange = ccxt.binance({
    "options": {"defaultType": "future"},
    "enableRateLimit": True,
})


# =========================
# TELEGRAM
# =========================
def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram ayarlı değil.", flush=True)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }

    try:
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        print("Telegram hatası:", e, flush=True)


# =========================
# HELPERS
# =========================
def normalize_symbol(symbol: str) -> str:
    return symbol.replace("/", "").replace(":", "").upper()


def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()


def add_ema_set(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = calculate_ema(out, EMA_FAST)
    out["ema_mid"] = calculate_ema(out, EMA_MID)
    out["ema_trend"] = calculate_ema(out, EMA_TREND)
    return out


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def fetch_ohlcv_df(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    return df


def get_quote_volume_24h(ticker: dict) -> float:
    try:
        return float(ticker.get("quoteVolume") or ticker.get("baseVolumeQuote") or 0.0)
    except Exception:
        return 0.0


def get_usdt_futures_symbols():
    markets = exchange.load_markets()
    symbols = []

    for symbol, market in markets.items():
        try:
            if market["quote"] == "USDT" and market["type"] == "swap":
                if normalize_symbol(symbol) in EXCLUDED_SYMBOLS:
                    continue
                symbols.append(symbol)
        except Exception:
            pass

    return symbols


def crosses_above(prev_fast, prev_mid, curr_fast, curr_mid) -> bool:
    return prev_fast <= prev_mid and curr_fast > curr_mid


def crosses_below(prev_fast, prev_mid, curr_fast, curr_mid) -> bool:
    return prev_fast >= prev_mid and curr_fast < curr_mid


def get_closed_rows(df: pd.DataFrame):
    if len(df) < 3:
        return None, None
    return df.iloc[-3], df.iloc[-2]


def calc_quote_candle_vol(row) -> float:
    return float(row["close"]) * float(row["volume"])


def calc_avg_quote_vol_last_10_closed(df: pd.DataFrame) -> float:
    if len(df) < 13:
        return 0.0
    recent = df.iloc[-12:-2].copy()
    if recent.empty:
        return 0.0
    return float((recent["close"] * recent["volume"]).mean())


def pct_change(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return ((b - a) / a) * 100.0


def build_timeframe_metrics(symbol: str):
    metrics = {
        "rsi_monthly": None,
        "rsi_weekly": None,
        "rsi_daily": None,
        "rsi_4h": None,
        "change_1h": None,
        "change_4h": None,
        "is_new_coin": False,
    }

    try:
        df_1M = fetch_ohlcv_df(symbol, "1M", 40)
        if len(df_1M) >= 20:
            metrics["rsi_monthly"] = float(calculate_rsi(df_1M["close"]).iloc[-1])
        else:
            metrics["is_new_coin"] = True
    except Exception:
        metrics["is_new_coin"] = True

    try:
        df_1W = fetch_ohlcv_df(symbol, "1w", 40)
        if len(df_1W) >= 20:
            metrics["rsi_weekly"] = float(calculate_rsi(df_1W["close"]).iloc[-1])
        else:
            metrics["is_new_coin"] = True
    except Exception:
        metrics["is_new_coin"] = True

    try:
        df_1D = fetch_ohlcv_df(symbol, "1d", 60)
        if len(df_1D) >= 20:
            metrics["rsi_daily"] = float(calculate_rsi(df_1D["close"]).iloc[-1])
        else:
            metrics["is_new_coin"] = True
    except Exception:
        metrics["is_new_coin"] = True

    try:
        df_4h = fetch_ohlcv_df(symbol, "4h", 80)
        if len(df_4h) >= 20:
            metrics["rsi_4h"] = float(calculate_rsi(df_4h["close"]).iloc[-1])
        else:
            metrics["is_new_coin"] = True
    except Exception:
        metrics["is_new_coin"] = True

    try:
        df_1h = fetch_ohlcv_df(symbol, "1h", 10)
        if len(df_1h) >= 5:
            metrics["change_1h"] = float(pct_change(float(df_1h.iloc[-2]["close"]), float(df_1h.iloc[-1]["close"])))
            metrics["change_4h"] = float(pct_change(float(df_1h.iloc[-5]["close"]), float(df_1h.iloc[-1]["close"])))
        else:
            metrics["is_new_coin"] = True
    except Exception:
        metrics["is_new_coin"] = True

    return metrics


def classify_signal_group(metrics: dict, quote_vol_24h: float) -> str:
    rsi_m = metrics.get("rsi_monthly")
    rsi_w = metrics.get("rsi_weekly")
    rsi_d = metrics.get("rsi_daily")
    rsi_4h = metrics.get("rsi_4h")
    ch1 = metrics.get("change_1h")
    ch4 = metrics.get("change_4h")

    if metrics.get("is_new_coin"):
        return "NEW"

    if (
        rsi_m is not None and rsi_m <= 10
        and rsi_w is not None and rsi_w <= 20
        and rsi_d is not None and rsi_d < 50
        and rsi_4h is not None and rsi_4h < 50
    ):
        return "DIP"

    if (
        quote_vol_24h >= 10_000_000
        and ch1 is not None and ch1 > 2
        and ch4 is not None and ch4 > 5
        and rsi_4h is not None and 50 <= rsi_4h <= 70
    ):
        return "PUMP"

    return "OTHER"


def get_signal_score(signal_group: str, vol_ratio: float, metrics: dict) -> float:
    score = 50.0

    if signal_group == "PUMP":
        score += 20
    elif signal_group == "NEW":
        score += 15
    elif signal_group == "DIP":
        score += 10

    score += min(vol_ratio * 8, 20)

    ch1 = metrics.get("change_1h") or 0.0
    ch4 = metrics.get("change_4h") or 0.0
    score += min(max(ch1, 0), 5)
    score += min(max(ch4, 0), 10)

    return round(min(score, 99.0), 2)


def get_quality(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    return "C"


def get_last_signal(db, symbol: str, side: str):
    return (
        db.query(Signal)
        .filter(Signal.symbol == symbol, Signal.side == side)
        .order_by(desc(Signal.id))
        .first()
    )


def in_cooldown(last_signal: Signal | None) -> bool:
    if not last_signal or not last_signal.cooldown_until:
        return False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now < last_signal.cooldown_until


def create_signal(
    db,
    symbol: str,
    side: str,
    signal_group: str,
    entry_type: str,
    entry_price: float,
    score: float,
    quality: str,
    rsi_monthly,
    rsi_weekly,
    rsi_daily,
    rsi_4h,
    change_1h,
    change_4h,
    entry_reason: str,
):
    cooldown_until = datetime.utcnow() + timedelta(minutes=SIGNAL_COOLDOWN_MINUTES)

    row = Signal(
        symbol=symbol,
        side=side,
        signal_group=signal_group,
        entry_type=entry_type,
        entry=entry_price,
        status="OPEN",
        pnl=0.0,
        max_profit=0.0,
        score=score,
        quality=quality,
        rsi_monthly=rsi_monthly,
        rsi_weekly=rsi_weekly,
        rsi_daily=rsi_daily,
        rsi_4h=rsi_4h,
        change_1h=change_1h,
        change_4h=change_4h,
        ema_set=f"{EMA_FAST}/{EMA_MID}/{EMA_TREND}",
        entry_reason=entry_reason,
        exit_reason=None,
        cooldown_until=cooldown_until,
        created_at=datetime.utcnow(),
        exit_time=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_open_trade_metrics(db, signal: Signal, current_price: float):
    if signal.side == "LONG":
        pnl = ((current_price - signal.entry) / signal.entry) * 100.0
    else:
        pnl = ((signal.entry - current_price) / signal.entry) * 100.0

    signal.pnl = round(pnl, 2)
    signal.max_profit = round(max(signal.max_profit or 0.0, pnl), 2)
    db.commit()


def close_trade(db, signal: Signal, exit_price: float, reason: str):
    if signal.side == "LONG":
        pnl = ((exit_price - signal.entry) / signal.entry) * 100.0
    else:
        pnl = ((signal.entry - exit_price) / signal.entry) * 100.0

    signal.exit = exit_price
    signal.exit_time = datetime.utcnow()
    signal.status = "CLOSED"
    signal.pnl = round(pnl, 2)
    signal.exit_reason = reason
    signal.max_profit = round(signal.max_profit or 0.0, 2)
    db.commit()


def send_entry_alert(row: Signal):
    msg = (
        f"🚀 {row.side} SIGNAL\n"
        f"Coin: {row.symbol}\n"
        f"Group: {row.signal_group}\n"
        f"Type: {row.entry_type}\n"
        f"Entry: {row.entry:.6f}\n"
        f"Score: {row.score} | Quality: {row.quality}\n"
        f"Reason: {row.entry_reason}"
    )
    send_telegram_message(msg)


def send_exit_alert(row: Signal):
    msg = (
        f"🛑 {row.side} EXIT\n"
        f"Coin: {row.symbol}\n"
        f"Exit: {row.exit:.6f}\n"
        f"PnL: {row.pnl:.2f}%\n"
        f"Reason: {row.exit_reason}"
    )
    send_telegram_message(msg)


# =========================
# ENTRY / EXIT LOGIC
# =========================
def long_cross_entry(df: pd.DataFrame) -> bool:
    prev_row, last_row = get_closed_rows(df)
    if prev_row is None:
        return False

    return (
        crosses_above(prev_row["ema_fast"], prev_row["ema_mid"], last_row["ema_fast"], last_row["ema_mid"])
        and last_row["ema_mid"] > last_row["ema_trend"]
        and last_row["close"] > last_row["ema_mid"]
    )


def long_bounce_entry(df: pd.DataFrame) -> bool:
    if len(df) < 5:
        return False

    a = df.iloc[-5]
    b = df.iloc[-4]
    c = df.iloc[-3]
    d = df.iloc[-2]

    return (
        d["ema_mid"] > d["ema_trend"]
        and d["close"] > d["ema_mid"]
        and c["low"] <= c["ema_mid"] * 1.003
        and c["close"] >= c["ema_mid"]
        and d["ema_fast"] > c["ema_fast"]
        and d["close"] > c["high"]
    )


def short_cross_entry(df: pd.DataFrame) -> bool:
    prev_row, last_row = get_closed_rows(df)
    if prev_row is None:
        return False

    return (
        crosses_below(prev_row["ema_fast"], prev_row["ema_mid"], last_row["ema_fast"], last_row["ema_mid"])
        and last_row["ema_mid"] < last_row["ema_trend"]
        and last_row["close"] < last_row["ema_mid"]
    )


def short_bounce_entry(df: pd.DataFrame) -> bool:
    if len(df) < 5:
        return False

    a = df.iloc[-5]
    b = df.iloc[-4]
    c = df.iloc[-3]
    d = df.iloc[-2]

    return (
        d["ema_mid"] < d["ema_trend"]
        and d["close"] < d["ema_mid"]
        and c["high"] >= c["ema_mid"] * 0.997
        and c["close"] <= c["ema_mid"]
        and d["ema_fast"] < c["ema_fast"]
        and d["close"] < c["low"]
    )


def should_exit_long(df: pd.DataFrame) -> bool:
    _, last_row = get_closed_rows(df)
    if last_row is None:
        return False
    return last_row["close"] < last_row["ema_mid"]


def should_exit_short(df: pd.DataFrame) -> bool:
    _, last_row = get_closed_rows(df)
    if last_row is None:
        return False
    return last_row["close"] > last_row["ema_mid"]


# =========================
# SCAN
# =========================
def scan_once():
    db = SessionLocal()
    try:
        symbols = get_usdt_futures_symbols()
        tickers = exchange.fetch_tickers()

        print(f"Taranacak coin sayısı: {len(symbols)}", flush=True)

        for symbol in symbols[:SCAN_LIMIT]:
            try:
                ticker = tickers.get(symbol) or {}
                quote_vol_24h = get_quote_volume_24h(ticker)

                if quote_vol_24h < MIN_QUOTEVOL24H:
                    continue

                df = fetch_ohlcv_df(symbol, TIMEFRAME, CANDLE_LIMIT)
                if len(df) < 50:
                    continue

                df = add_ema_set(df)
                last_closed = df.iloc[-2]
                current_price = float(last_closed["close"])

                cross_candle_vol = calc_quote_candle_vol(last_closed)
                avg_qv_10 = calc_avg_quote_vol_last_10_closed(df)
                vol_ratio = (cross_candle_vol / avg_qv_10) if avg_qv_10 > 0 else 0.0

                metrics = build_timeframe_metrics(symbol)
                signal_group = classify_signal_group(metrics, quote_vol_24h)

                if signal_group == "OTHER":
                    continue

                score = get_signal_score(signal_group, vol_ratio, metrics)
                quality = get_quality(score)

                # OPEN trades yönet
                open_rows = (
                    db.query(Signal)
                    .filter(Signal.symbol == symbol, Signal.status == "OPEN")
                    .all()
                )

                for row in open_rows:
                    update_open_trade_metrics(db, row, current_price)

                    if row.side == "LONG" and should_exit_long(df):
                        close_trade(db, row, current_price, "Price closed below EMA18")
                        send_exit_alert(row)

                    elif row.side == "SHORT" and should_exit_short(df):
                        close_trade(db, row, current_price, "Price closed above EMA18")
                        send_exit_alert(row)

                # LONG
                last_long = get_last_signal(db, symbol, "LONG")
                if not in_cooldown(last_long):
                    if long_cross_entry(df):
                        row = create_signal(
                            db=db,
                            symbol=symbol,
                            side="LONG",
                            signal_group=signal_group,
                            entry_type="cross",
                            entry_price=current_price,
                            score=score,
                            quality=quality,
                            rsi_monthly=metrics["rsi_monthly"],
                            rsi_weekly=metrics["rsi_weekly"],
                            rsi_daily=metrics["rsi_daily"],
                            rsi_4h=metrics["rsi_4h"],
                            change_1h=metrics["change_1h"],
                            change_4h=metrics["change_4h"],
                            entry_reason="ema8_cross_above_ema18",
                        )
                        print(f"LONG CROSS: {symbol} | score={score} | group={signal_group}", flush=True)
                        send_entry_alert(row)

                    elif long_bounce_entry(df):
                        row = create_signal(
                            db=db,
                            symbol=symbol,
                            side="LONG",
                            signal_group=signal_group,
                            entry_type="bounce",
                            entry_price=current_price,
                            score=score,
                            quality=quality,
                            rsi_monthly=metrics["rsi_monthly"],
                            rsi_weekly=metrics["rsi_weekly"],
                            rsi_daily=metrics["rsi_daily"],
                            rsi_4h=metrics["rsi_4h"],
                            change_1h=metrics["change_1h"],
                            change_4h=metrics["change_4h"],
                            entry_reason="ema18_bounce_long",
                        )
                        print(f"LONG BOUNCE: {symbol} | score={score} | group={signal_group}", flush=True)
                        send_entry_alert(row)

                # SHORT
                last_short = get_last_signal(db, symbol, "SHORT")
                if not in_cooldown(last_short):
                    if short_cross_entry(df):
                        row = create_signal(
                            db=db,
                            symbol=symbol,
                            side="SHORT",
                            signal_group=signal_group,
                            entry_type="cross",
                            entry_price=current_price,
                            score=score,
                            quality=quality,
                            rsi_monthly=metrics["rsi_monthly"],
                            rsi_weekly=metrics["rsi_weekly"],
                            rsi_daily=metrics["rsi_daily"],
                            rsi_4h=metrics["rsi_4h"],
                            change_1h=metrics["change_1h"],
                            change_4h=metrics["change_4h"],
                            entry_reason="ema8_cross_below_ema18",
                        )
                        print(f"SHORT CROSS: {symbol} | score={score} | group={signal_group}", flush=True)
                        send_entry_alert(row)

                    elif short_bounce_entry(df):
                        row = create_signal(
                            db=db,
                            symbol=symbol,
                            side="SHORT",
                            signal_group=signal_group,
                            entry_type="bounce",
                            entry_price=current_price,
                            score=score,
                            quality=quality,
                            rsi_monthly=metrics["rsi_monthly"],
                            rsi_weekly=metrics["rsi_weekly"],
                            rsi_daily=metrics["rsi_daily"],
                            rsi_4h=metrics["rsi_4h"],
                            change_1h=metrics["change_1h"],
                            change_4h=metrics["change_4h"],
                            entry_reason="ema18_bounce_short",
                        )
                        print(f"SHORT BOUNCE: {symbol} | score={score} | group={signal_group}", flush=True)
                        send_entry_alert(row)

                time.sleep(0.05)

            except Exception as e:
                print(f"Hata {symbol}: {e}", flush=True)

    finally:
        db.close()


if __name__ == "__main__":
    print("v2 EMA worker başladı...", flush=True)
    send_telegram_message("🚀 v2 EMA worker started")

    while True:
        try:
            scan_once()
        except Exception as e:
            print("Genel worker hatası:", e, flush=True)

        print(f"{SLEEP_SECONDS} saniye bekleniyor...", flush=True)
        time.sleep(SLEEP_SECONDS)
