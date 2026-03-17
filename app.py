import time
from datetime import datetime, timezone

import ccxt
import pandas as pd

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TIMEFRAME,
    MOMENTUM_TIMEFRAME,
    SLEEP_SECONDS,
    CANDLE_LIMIT,
    EXCLUDED_SYMBOLS,
    ENABLE_PUMP_LONG,
    MIN_QUOTEVOL24H,
    PUMP_EMA_FAST,
    PUMP_EMA_MID,
    PUMP_EMA_TREND,
    MAX_EMA_FAST_MID_GAP_PCT,
    MAX_EMA_MID_TREND_GAP_PCT,
    BREAKOUT_LOOKBACK,
    BREAKOUT_NEAR_PCT,
    MIN_VOL_RATIO,
    STRONG_VOL_RATIO,
    MIN_CHANGE_1H_PRIORITY,
    MIN_CHANGE_4H_PRIORITY,
    SIGNAL_COOLDOWN_MINUTES,
    MIN_SIGNAL_SCORE,
    A_GRADE_SCORE,
    ARM_TRAILING_AT_PROFIT_PCT,
    TRAILING_GIVEBACK_PCT,
    HARD_STOP_PCT,
    HARD_TP1_PCT,
    HARD_TP2_PCT,
)
from indicators import add_ema_set
from storage import (
    init_db,
    create_trade,
    update_trade_metrics,
    close_trade,
    is_symbol_in_cooldown,
    compute_cooldown_until,
)
from telegram_utils import (
    send_telegram_message,
    format_signal_message,
    format_exit_message,
)

exchange = ccxt.binance({
    "options": {"defaultType": "future"},
    "enableRateLimit": True,
})

open_long_positions = {}


def normalize_symbol(symbol: str) -> str:
    return symbol.replace("/", "").replace(":", "").upper()


def get_usdt_futures_symbols():
    markets = exchange.load_markets()
    symbols = []

    for symbol, market in markets.items():
        try:
            if market["quote"] == "USDT" and market["type"] == "swap" and market.get("active", True):
                if normalize_symbol(symbol) in EXCLUDED_SYMBOLS:
                    continue
                symbols.append(symbol)
        except Exception:
            pass

    print(f"Toplam futures coin bulundu: {len(symbols)}", flush=True)
    return symbols


def fetch_ohlcv_df(symbol: str, timeframe: str, limit: int):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )


def fetch_all_tickers_map():
    try:
        return exchange.fetch_tickers()
    except Exception as e:
        print(f"Toplu ticker alınamadı: {e}", flush=True)
        return {}


def get_quote_volume_24h(ticker: dict) -> float:
    try:
        return float(ticker.get("quoteVolume") or ticker.get("baseVolumeQuote") or 0.0)
    except Exception:
        return 0.0


def get_closed_signal_rows(df: pd.DataFrame):
    if len(df) < 3:
        return None, None
    return df.iloc[-3], df.iloc[-2]


def crosses_above(prev_fast, prev_mid, curr_fast, curr_mid) -> bool:
    return prev_fast <= prev_mid and curr_fast > curr_mid


def calc_cross_candle_quote_volume(last_closed):
    return float(last_closed["close"]) * float(last_closed["volume"])


def calc_avg_quote_volume_last_10_closed(df):
    if len(df) < 13:
        return 0.0
    recent = df.iloc[-12:-2].copy()
    if recent.empty:
        return 0.0
    return float((recent["close"] * recent["volume"]).mean())


def calc_ema_distance(last_closed):
    price = float(last_closed["close"])
    if price <= 0:
        return 0.0
    return abs(float(last_closed["ema_fast"]) - float(last_closed["ema_trend"])) / price * 100.0


def pct_change(a, b):
    if b is None or b == 0:
        return 0.0
    return ((a - b) / b) * 100.0


def calc_change_from_lookback(df: pd.DataFrame, candles_back: int) -> float:
    if len(df) < candles_back + 2:
        return 0.0
    last_closed = df.iloc[-2]
    ref = df.iloc[-2 - candles_back]
    return pct_change(float(last_closed["close"]), float(ref["close"]))


def calc_ema55_slope_positive(df: pd.DataFrame) -> bool:
    if len(df) < 5:
        return False
    last_closed = df.iloc[-2]
    prev3 = df.iloc[-5]
    return float(last_closed["ema_trend"]) > float(prev3["ema_trend"])


def is_trend_ok(last_closed) -> bool:
    return (
        float(last_closed["ema_fast"]) > float(last_closed["ema_mid"])
        and float(last_closed["ema_mid"]) > float(last_closed["ema_trend"])
        and float(last_closed["close"]) > float(last_closed["ema_mid"])
    )


def is_compression_ok(last_closed) -> tuple[bool, float, float]:
    close_price = float(last_closed["close"])
    if close_price <= 0:
        return False, 999.0, 999.0

    fast_mid_gap_pct = abs(float(last_closed["ema_fast"]) - float(last_closed["ema_mid"])) / close_price * 100.0
    mid_trend_gap_pct = abs(float(last_closed["ema_mid"]) - float(last_closed["ema_trend"])) / close_price * 100.0

    ok = (
        fast_mid_gap_pct <= MAX_EMA_FAST_MID_GAP_PCT
        and mid_trend_gap_pct <= MAX_EMA_MID_TREND_GAP_PCT
    )
    return ok, fast_mid_gap_pct, mid_trend_gap_pct


def get_breakout_level(df: pd.DataFrame) -> float | None:
    if len(df) < BREAKOUT_LOOKBACK + 3:
        return None
    window = df.iloc[-(BREAKOUT_LOOKBACK + 2):-2]
    if window.empty:
        return None
    return float(window["high"].max())


def is_breakout_ok(last_closed, breakout_level: float | None) -> tuple[bool, bool]:
    if breakout_level is None or breakout_level <= 0:
        return False, False

    close_price = float(last_closed["close"])
    breakout_ok = close_price > breakout_level
    near_breakout_ok = close_price >= breakout_level * (1 - BREAKOUT_NEAR_PCT / 100.0)
    return breakout_ok, near_breakout_ok


def get_setup_type(compression_ok: bool, breakout_ok: bool, near_breakout_ok: bool, ema55_slope_ok: bool) -> str:
    if compression_ok and breakout_ok and ema55_slope_ok:
        return "Compression Breakout"
    if breakout_ok and ema55_slope_ok:
        return "Breakout Trend"
    if compression_ok and near_breakout_ok:
        return "Compression Near Breakout"
    return "Trend Continuation"


def quality_from_score(score: float) -> str:
    if score >= A_GRADE_SCORE:
        return "A"
    if score >= MIN_SIGNAL_SCORE:
        return "B"
    return "C"


def calc_signal_score(
    last_closed,
    compression_ok: bool,
    breakout_ok: bool,
    near_breakout_ok: bool,
    volume_ratio: float,
    change_1h: float,
    change_4h: float,
    ema55_slope_ok: bool,
) -> float:
    score = 0.0

    if float(last_closed["ema_mid"]) > float(last_closed["ema_trend"]):
        score += 8
    if float(last_closed["ema_fast"]) > float(last_closed["ema_mid"]):
        score += 6
    if float(last_closed["close"]) > float(last_closed["ema_mid"]):
        score += 6

    if compression_ok:
        score += 20

    if breakout_ok:
        score += 25
    elif near_breakout_ok:
        score += 10

    if volume_ratio >= STRONG_VOL_RATIO:
        score += 20
    elif volume_ratio >= MIN_VOL_RATIO:
        score += 15

    if ema55_slope_ok:
        score += 10

    if change_4h >= MIN_CHANGE_4H_PRIORITY:
        score += 5
    elif change_4h > 0:
        score += 3

    if change_1h >= MIN_CHANGE_1H_PRIORITY:
        score += 5
    elif change_1h > 0:
        score += 2

    return float(min(score, 100.0))


def calc_live_metrics(entry_price: float, current_price: float, position: dict, entry_time: datetime):
    live_pnl = ((current_price - entry_price) / entry_price) * 100.0

    max_profit_pct = max(position.get("max_profit_pct", 0.0), live_pnl)
    max_drawdown_pct = min(position.get("max_drawdown_pct", 0.0), live_pnl)

    duration_minutes = max(
        (datetime.now(timezone.utc) - entry_time).total_seconds() / 60.0,
        0.0,
    )

    rr_ratio = 0.0
    if abs(max_drawdown_pct) > 0:
        rr_ratio = max_profit_pct / abs(max_drawdown_pct)

    return live_pnl, max_profit_pct, max_drawdown_pct, duration_minutes, rr_ratio


def should_exit_trade(position: dict, raw_df_15m: pd.DataFrame):
    df = add_ema_set(raw_df_15m, PUMP_EMA_FAST, PUMP_EMA_MID, PUMP_EMA_TREND)
    prev_closed, last_closed = get_closed_signal_rows(df)
    if prev_closed is None:
        return False, "Unknown"

    close_price = float(last_closed["close"])
    ema_fast = float(last_closed["ema_fast"])
    ema_mid = float(last_closed["ema_mid"])

    live_pnl = position.get("live_pnl", 0.0)
    max_profit_pct = position.get("max_profit_pct", 0.0)

    if live_pnl <= HARD_STOP_PCT:
        return True, f"Hard stop hit ({HARD_STOP_PCT:.1f}%)"

    if max_profit_pct >= HARD_TP2_PCT:
        return True, f"Hard TP2 reached ({HARD_TP2_PCT:.1f}%)"

    if max_profit_pct >= ARM_TRAILING_AT_PROFIT_PCT:
        giveback = max_profit_pct - live_pnl
        if giveback >= TRAILING_GIVEBACK_PCT:
            return True, f"Trailing giveback {giveback:.2f}%"

    if max_profit_pct < ARM_TRAILING_AT_PROFIT_PCT:
        if ema_fast < ema_mid and close_price < ema_mid:
            return True, f"Fail exit: EMA{PUMP_EMA_FAST}<EMA{PUMP_EMA_MID} and close<EMA{PUMP_EMA_MID}"

    return False, "Hold"


def evaluate_pump_long_signal(symbol, df_15m, df_5m, quote_vol_24h):
    if not ENABLE_PUMP_LONG:
        return None

    if quote_vol_24h < MIN_QUOTEVOL24H:
        return None

    df_15m = add_ema_set(df_15m, PUMP_EMA_FAST, PUMP_EMA_MID, PUMP_EMA_TREND)
    prev_closed, last_closed = get_closed_signal_rows(df_15m)
    if prev_closed is None:
        return None

    if not is_trend_ok(last_closed):
        return None

    if not crosses_above(
        prev_closed["ema_fast"], prev_closed["ema_mid"],
        last_closed["ema_fast"], last_closed["ema_mid"]
    ):
        return None

    ema55_slope_ok = calc_ema55_slope_positive(df_15m)
    if not ema55_slope_ok:
        return None

    cross_candle_volume = calc_cross_candle_quote_volume(last_closed)
    avg_qv_10 = calc_avg_quote_volume_last_10_closed(df_15m)
    volume_ratio = (cross_candle_volume / avg_qv_10) if avg_qv_10 > 0 else 0.0
    if volume_ratio < MIN_VOL_RATIO:
        return None

    compression_ok, fast_mid_gap_pct, mid_trend_gap_pct = is_compression_ok(last_closed)
    if not compression_ok:
        return None

    breakout_level = get_breakout_level(df_15m)
    breakout_ok, near_breakout_ok = is_breakout_ok(last_closed, breakout_level)
    if not breakout_ok:
        return None

    change_1h = calc_change_from_lookback(df_5m, 12)
    change_4h = calc_change_from_lookback(df_15m, 16)

    score = calc_signal_score(
        last_closed=last_closed,
        compression_ok=compression_ok,
        breakout_ok=breakout_ok,
        near_breakout_ok=near_breakout_ok,
        volume_ratio=volume_ratio,
        change_1h=change_1h,
        change_4h=change_4h,
        ema55_slope_ok=ema55_slope_ok,
    )

    if score < MIN_SIGNAL_SCORE:
        return None

    setup_type = get_setup_type(compression_ok, breakout_ok, near_breakout_ok, ema55_slope_ok)
    quality = quality_from_score(score)

    return {
        "mode": "PUMP",
        "side": "LONG",
        "entry_reason": "pump_hunter_long_breakout_cross",
        "ema_fast_len": PUMP_EMA_FAST,
        "ema_mid_len": PUMP_EMA_MID,
        "ema_trend_len": PUMP_EMA_TREND,
        "last_closed": last_closed,
        "cross_candle_volume": float(cross_candle_volume),
        "volume_ratio": float(volume_ratio),
        "breakout_level": breakout_level,
        "change_1h": float(change_1h),
        "change_4h": float(change_4h),
        "signal_score": float(score),
        "setup_type": setup_type,
        "quality_tag": quality,
    }


def scan_once():
    global open_long_positions

    print("USDT futures coin listesi alınıyor...", flush=True)
    all_symbols = get_usdt_futures_symbols()
    all_tickers = fetch_all_tickers_map()

    print(f"Taranacak coin sayısı: {len(all_symbols)}", flush=True)

    for symbol in all_symbols:
        try:
            ticker = all_tickers.get(symbol) or {}
            quote_volume_24h = get_quote_volume_24h(ticker)

            if quote_volume_24h < MIN_QUOTEVOL24H:
                continue

            df_15m = fetch_ohlcv_df(symbol, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)
            if len(df_15m) < max(PUMP_EMA_TREND, BREAKOUT_LOOKBACK) + 10:
                continue

            df_5m = fetch_ohlcv_df(symbol, timeframe=MOMENTUM_TIMEFRAME, limit=max(80, CANDLE_LIMIT // 2))
            if len(df_5m) < 30:
                continue

            prev_closed, last_closed_raw = get_closed_signal_rows(df_15m)
            if prev_closed is None or last_closed_raw is None:
                continue

            current_price = float(last_closed_raw["close"])
            current_ts = datetime.now(timezone.utc)
            cross_time = datetime.fromtimestamp(
                int(last_closed_raw["timestamp"]) / 1000,
                tz=timezone.utc,
            )
            cross_price = current_price

            if symbol not in open_long_positions:
                signal = evaluate_pump_long_signal(
                    symbol=symbol,
                    df_15m=df_15m,
                    df_5m=df_5m,
                    quote_vol_24h=quote_volume_24h,
                )

                if signal:
                    in_cooldown, cooldown_until_prev = is_symbol_in_cooldown(symbol, "LONG", current_ts)
                    if in_cooldown:
                        print(f"Cooldown aktif, atlanıyor: {symbol} LONG | until={cooldown_until_prev}", flush=True)
                        time.sleep(0.03)
                        continue

                    signal_last = signal["last_closed"]
                    ema_distance = calc_ema_distance(signal_last)
                    cooldown_until = compute_cooldown_until(current_ts, SIGNAL_COOLDOWN_MINUTES)

                    trade_id = create_trade(
                        symbol=symbol,
                        side="LONG",
                        mode="PUMP",
                        entry_price=current_price,
                        entry_time=current_ts,
                        timeframe=TIMEFRAME,
                        cross_time=cross_time,
                        cross_price=cross_price,
                        quote_volume_24h=float(quote_volume_24h),
                        cross_candle_volume=signal["cross_candle_volume"],
                        ema_distance=float(ema_distance),
                        volume_ratio=signal["volume_ratio"],
                        market_cap=None,
                        ema_fast=signal["ema_fast_len"],
                        ema_mid=signal["ema_mid_len"],
                        ema_trend=signal["ema_trend_len"],
                        entry_reason=signal["entry_reason"],
                        signal_score=signal["signal_score"],
                        setup_type=signal["setup_type"],
                        quality_tag=signal["quality_tag"],
                        breakout_level=signal["breakout_level"],
                        change_1h=signal["change_1h"],
                        change_4h=signal["change_4h"],
                        cooldown_until=cooldown_until,
                    )

                    pos = {
                        "trade_id": trade_id,
                        "side": "LONG",
                        "mode": "PUMP",
                        "entry_price": current_price,
                        "entry_time": current_ts,
                        "max_profit_pct": 0.0,
                        "max_drawdown_pct": 0.0,
                        "cooldown_until": cooldown_until,
                        "signal_score": signal["signal_score"],
                        "quality_tag": signal["quality_tag"],
                        "breakout_level": signal["breakout_level"],
                        "live_pnl": 0.0,
                    }
                    open_long_positions[symbol] = pos

                    msg = format_signal_message(
                        symbol=symbol,
                        price=round(current_price, 8),
                        side="LONG",
                        timeframe=TIMEFRAME,
                        score=signal["signal_score"],
                        quality=signal["quality_tag"],
                        setup_type=signal["setup_type"],
                        volume_ratio=signal["volume_ratio"],
                        breakout_level=round(signal["breakout_level"], 8) if signal["breakout_level"] else "-",
                        change_1h=signal["change_1h"],
                        change_4h=signal["change_4h"],
                        ema_fast=signal["ema_fast_len"],
                        ema_mid=signal["ema_mid_len"],
                        ema_trend=signal["ema_trend_len"],
                    )

                    print(
                        f"PUMP LONG SIGNAL: {symbol} | "
                        f"score={signal['signal_score']:.1f} | "
                        f"quality={signal['quality_tag']} | "
                        f"qv24h={quote_volume_24h:.2f} | "
                        f"vol_ratio={signal['volume_ratio']:.2f} | "
                        f"chg1h={signal['change_1h']:.2f}% | "
                        f"chg4h={signal['change_4h']:.2f}%",
                        flush=True,
                    )
                    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)

            elif symbol in open_long_positions:
                pos = open_long_positions[symbol]

                live_pnl, max_profit_pct, max_drawdown_pct, duration_minutes, rr_ratio = calc_live_metrics(
                    entry_price=pos["entry_price"],
                    current_price=current_price,
                    position=pos,
                    entry_time=pos["entry_time"],
                )

                pos["live_pnl"] = live_pnl
                pos["max_profit_pct"] = max_profit_pct
                pos["max_drawdown_pct"] = max_drawdown_pct

                update_trade_metrics(
                    trade_id=pos["trade_id"],
                    max_profit_pct=max_profit_pct,
                    max_drawdown_pct=max_drawdown_pct,
                    duration_minutes=duration_minutes,
                    rr_ratio=rr_ratio,
                )

                exit_now, reason = should_exit_trade(pos, df_15m)
                if exit_now:
                    close_trade(
                        trade_id=pos["trade_id"],
                        exit_price=current_price,
                        exit_time=current_ts,
                        exit_reason=reason,
                        pnl_pct=live_pnl,
                        max_profit_pct=max_profit_pct,
                        max_drawdown_pct=max_drawdown_pct,
                        duration_minutes=duration_minutes,
                        rr_ratio=rr_ratio,
                    )

                    exit_msg = format_exit_message(
                        symbol=symbol,
                        side="LONG",
                        mode="PUMP",
                        exit_price=current_price,
                        pnl_pct=live_pnl,
                        reason=reason,
                    )

                    print(
                        f"PUMP LONG EXIT: {symbol} | "
                        f"PnL={live_pnl:.2f}% | "
                        f"MaxProfit={max_profit_pct:.2f}% | "
                        f"Reason={reason}",
                        flush=True,
                    )
                    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, exit_msg)
                    del open_long_positions[symbol]

            time.sleep(0.03)

        except Exception as e:
            print(f"Hata {symbol}: {e}", flush=True)


if __name__ == "__main__":
    init_db()
    print("Pump Hunter v2.1 worker başlatıldı...", flush=True)

    send_telegram_message(
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_CHAT_ID,
        "🚀 <b>Pump Hunter v2.1 worker started</b>"
    )

    while True:
        try:
            scan_once()
        except Exception as e:
            print("Genel scan hatası:", e, flush=True)

        print(f"{SLEEP_SECONDS} saniye bekleniyor...", flush=True)
        time.sleep(SLEEP_SECONDS)
