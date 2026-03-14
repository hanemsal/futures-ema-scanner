import time
from datetime import datetime, timezone

import ccxt
import pandas as pd

from indicators import add_ema_indicators
from signals_long import check_long_entry, check_long_exit
from signals_short import check_short_entry, check_short_exit
from telegram_utils import (
    send_telegram_message,
    format_long_signal,
    format_long_exit,
    format_short_signal,
    format_short_exit,
)
from config import TIMEFRAME, SLEEP_SECONDS, CANDLE_LIMIT, MIN_QUOTE_VOLUME_24H
from storage import init_db, create_trade, update_trade_metrics, close_trade

exchange = ccxt.binance({
    "options": {"defaultType": "future"},
    "enableRateLimit": True,
})

open_long_positions = {}
open_short_positions = {}


def get_usdt_futures_symbols():
    markets = exchange.load_markets()
    symbols = []

    for symbol, market in markets.items():
        try:
            if market["quote"] == "USDT" and market["type"] == "swap":
                symbols.append(symbol)
        except Exception:
            pass

    print(f"Toplam futures coin bulundu: {len(symbols)}", flush=True)
    return symbols


def fetch_ohlcv_df(symbol: str, timeframe: str = "15m", limit: int = 200):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    return df


def get_filtered_symbols_by_quote_volume(symbols, min_quote_volume=10_000_000):
    filtered = []

    for symbol in symbols:
        try:
            ticker = exchange.fetch_ticker(symbol)
            quote_volume = float(ticker.get("quoteVolume") or 0.0)

            if quote_volume >= min_quote_volume:
                filtered.append((symbol, quote_volume))

            time.sleep(0.04)

        except Exception as e:
            print(f"Ticker alınamadı {symbol}: {e}", flush=True)

    filtered.sort(key=lambda x: x[1], reverse=True)
    return filtered


def get_closed_signal_rows(df):
    if len(df) < 3:
        return None, None

    prev_closed = df.iloc[-3]
    last_closed = df.iloc[-2]
    return prev_closed, last_closed


def get_long_exit_reason(df):
    prev_closed, last_closed = get_closed_signal_rows(df)
    if prev_closed is None:
        return "Unknown"

    cross_down_47 = (
        prev_closed["ema11"] >= prev_closed["ema47"]
        and last_closed["ema11"] < last_closed["ema47"]
    )

    if cross_down_47:
        return "EMA11 crossed below EMA47"

    return "Unknown"


def get_short_exit_reason(df):
    prev_closed, last_closed = get_closed_signal_rows(df)
    if prev_closed is None:
        return "Unknown"

    cross_up_29 = (
        prev_closed["ema11"] <= prev_closed["ema29"]
        and last_closed["ema11"] > last_closed["ema29"]
    )

    if cross_up_29:
        return "EMA11 crossed above EMA29"

    if last_closed["ema11"] > last_closed["ema29"]:
        return "EMA11 moved above EMA29"

    return "Unknown"


def calc_live_metrics(side: str, entry_price: float, current_price: float, position: dict, entry_time: datetime):
    if side == "LONG":
        live_pnl = ((current_price - entry_price) / entry_price) * 100.0
    else:
        live_pnl = ((entry_price - current_price) / entry_price) * 100.0

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

    return abs(float(last_closed["ema11"]) - float(last_closed["ema123"])) / price * 100.0


def scan_once():
    global open_long_positions
    global open_short_positions

    print("USDT futures coin listesi alınıyor...", flush=True)
    all_symbols = get_usdt_futures_symbols()

    print("Quote volume filtresi uygulanıyor...", flush=True)
    scan_symbols = get_filtered_symbols_by_quote_volume(
        all_symbols,
        min_quote_volume=MIN_QUOTE_VOLUME_24H,
    )

    print(f"Taranacak coin sayısı: {len(scan_symbols)}", flush=True)

    for symbol, quote_volume_24h in scan_symbols:
        try:
            df = fetch_ohlcv_df(symbol, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)

            if len(df) < 130:
                continue

            df = add_ema_indicators(df)

            prev_closed, last_closed = get_closed_signal_rows(df)
            if prev_closed is None or last_closed is None:
                continue

            current_price = float(last_closed["close"])
            current_ts = datetime.now(timezone.utc)

            cross_time = datetime.fromtimestamp(
                int(last_closed["timestamp"]) / 1000,
                tz=timezone.utc,
            )
            cross_price = current_price
            cross_candle_volume = calc_cross_candle_quote_volume(last_closed)
            avg_qv_10 = calc_avg_quote_volume_last_10_closed(df)
            volume_ratio = (cross_candle_volume / avg_qv_10) if avg_qv_10 > 0 else 0.0
            ema_distance = calc_ema_distance(last_closed)

            if symbol not in open_long_positions and symbol not in open_short_positions:
                if check_long_entry(df):
                    trade_id = create_trade(
                        symbol=symbol,
                        side="LONG",
                        entry_price=current_price,
                        entry_time=current_ts,
                        timeframe=TIMEFRAME,
                        cross_time=cross_time,
                        cross_price=cross_price,
                        quote_volume_24h=float(quote_volume_24h),
                        cross_candle_volume=float(cross_candle_volume),
                        ema_distance=float(ema_distance),
                        volume_ratio=float(volume_ratio),
                    )

                    open_long_positions[symbol] = {
                        "trade_id": trade_id,
                        "entry_price": current_price,
                        "entry_time": current_ts,
                        "max_profit_pct": 0.0,
                        "max_drawdown_pct": 0.0,
                    }

                    msg = format_long_signal(
                        symbol=symbol,
                        price=current_price,
                        ema11=float(last_closed["ema11"]),
                        ema47=float(last_closed["ema47"]),
                        ema123=float(last_closed["ema123"]),
                    )

                    print(
                        f"LONG SIGNAL: {symbol} | qv24h={quote_volume_24h:.2f} | "
                        f"cross_vol={cross_candle_volume:.2f} | "
                        f"ema_dist={ema_distance:.4f}% | vol_ratio={volume_ratio:.2f}",
                        flush=True,
                    )
                    send_telegram_message(msg)

            elif symbol in open_long_positions:
                pos = open_long_positions[symbol]
                live_pnl, max_profit_pct, max_drawdown_pct, duration_minutes, rr_ratio = calc_live_metrics(
                    side="LONG",
                    entry_price=pos["entry_price"],
                    current_price=current_price,
                    position=pos,
                    entry_time=pos["entry_time"],
                )

                pos["max_profit_pct"] = max_profit_pct
                pos["max_drawdown_pct"] = max_drawdown_pct

                update_trade_metrics(
                    trade_id=pos["trade_id"],
                    max_profit_pct=max_profit_pct,
                    max_drawdown_pct=max_drawdown_pct,
                    duration_minutes=duration_minutes,
                    rr_ratio=rr_ratio,
                )

                if check_long_exit(df):
                    reason = get_long_exit_reason(df)

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

                    msg = format_long_exit(
                        symbol=symbol,
                        price=current_price,
                        reason=reason,
                        pnl_pct=live_pnl,
                    )

                    print(f"LONG EXIT: {symbol} | PnL: {live_pnl:.2f}%", flush=True)
                    send_telegram_message(msg)
                    del open_long_positions[symbol]

            if symbol not in open_short_positions and symbol not in open_long_positions:
                if check_short_entry(df):
                    trade_id = create_trade(
                        symbol=symbol,
                        side="SHORT",
                        entry_price=current_price,
                        entry_time=current_ts,
                        timeframe=TIMEFRAME,
                        cross_time=cross_time,
                        cross_price=cross_price,
                        quote_volume_24h=float(quote_volume_24h),
                        cross_candle_volume=float(cross_candle_volume),
                        ema_distance=float(ema_distance),
                        volume_ratio=float(volume_ratio),
                    )

                    open_short_positions[symbol] = {
                        "trade_id": trade_id,
                        "entry_price": current_price,
                        "entry_time": current_ts,
                        "max_profit_pct": 0.0,
                        "max_drawdown_pct": 0.0,
                    }

                    msg = format_short_signal(
                        symbol=symbol,
                        price=current_price,
                        ema11=float(last_closed["ema11"]),
                        ema29=float(last_closed["ema29"]),
                        ema123=float(last_closed["ema123"]),
                    )

                    print(
                        f"SHORT SIGNAL: {symbol} | qv24h={quote_volume_24h:.2f} | "
                        f"cross_vol={cross_candle_volume:.2f} | "
                        f"ema_dist={ema_distance:.4f}% | vol_ratio={volume_ratio:.2f}",
                        flush=True,
                    )
                    send_telegram_message(msg)

            elif symbol in open_short_positions:
                pos = open_short_positions[symbol]
                live_pnl, max_profit_pct, max_drawdown_pct, duration_minutes, rr_ratio = calc_live_metrics(
                    side="SHORT",
                    entry_price=pos["entry_price"],
                    current_price=current_price,
                    position=pos,
                    entry_time=pos["entry_time"],
                )

                pos["max_profit_pct"] = max_profit_pct
                pos["max_drawdown_pct"] = max_drawdown_pct

                update_trade_metrics(
                    trade_id=pos["trade_id"],
                    max_profit_pct=max_profit_pct,
                    max_drawdown_pct=max_drawdown_pct,
                    duration_minutes=duration_minutes,
                    rr_ratio=rr_ratio,
                )

                if check_short_exit(df):
                    reason = get_short_exit_reason(df)

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

                    msg = format_short_exit(
                        symbol=symbol,
                        price=current_price,
                        reason=reason,
                        pnl_pct=live_pnl,
                    )

                    print(f"SHORT EXIT: {symbol} | PnL: {live_pnl:.2f}%", flush=True)
                    send_telegram_message(msg)
                    del open_short_positions[symbol]

            time.sleep(0.03)

        except Exception as e:
            print(f"Hata {symbol}: {e}", flush=True)


if __name__ == "__main__":
    init_db()
    print("EMA Scanner başlatıldı...", flush=True)
    send_telegram_message("🚀 EMA Scanner worker started")

    while True:
        try:
            scan_once()
        except Exception as e:
            print("Genel scan hatası:", e, flush=True)

        print(f"{SLEEP_SECONDS} saniye bekleniyor...", flush=True)
        time.sleep(SLEEP_SECONDS)
