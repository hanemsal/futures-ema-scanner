import time
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
from config import TIMEFRAME, SLEEP_SECONDS, CANDLE_LIMIT, TOP_VOLUME_COUNT


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


def get_top_symbols_by_quote_volume(symbols, top_n=120):
    ranked = []

    for symbol in symbols:
        try:
            ticker = exchange.fetch_ticker(symbol)
            quote_volume = ticker.get("quoteVolume") or 0
            ranked.append((symbol, quote_volume))
            time.sleep(0.08)
        except Exception as e:
            print(f"Ticker alınamadı {symbol}: {e}", flush=True)

    ranked.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in ranked[:top_n]]


def get_long_exit_reason(df):
    prev = df.iloc[-2]
    curr = df.iloc[-1]

    cross_down_47 = prev["ema11"] >= prev["ema47"] and curr["ema11"] < curr["ema47"]
    if cross_down_47:
        return "EMA11 crossed below EMA47"

    return "Unknown"


def get_short_exit_reason(df):
    prev = df.iloc[-2]
    curr = df.iloc[-1]

    cross_up_29 = prev["ema11"] <= prev["ema29"] and curr["ema11"] > curr["ema29"]
    if cross_up_29:
        return "EMA11 crossed above EMA29"

    if curr["close"] > curr["ema29"]:
        return "Price rose above EMA29"

    return "Unknown"


def scan_once():
    global open_long_positions
    global open_short_positions

    print("USDT futures coin listesi alınıyor...", flush=True)
    all_symbols = get_usdt_futures_symbols()

    print("Hacme göre coin sıralaması yapılıyor...", flush=True)
    scan_symbols = get_top_symbols_by_quote_volume(all_symbols, top_n=TOP_VOLUME_COUNT)

    print(f"Taranacak coin sayısı: {len(scan_symbols)}", flush=True)

    for symbol in scan_symbols:
        try:
            df = fetch_ohlcv_df(symbol, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)

            if len(df) < 130:
                continue

            df = add_ema_indicators(df)
            current_price = float(df.iloc[-1]["close"])
            curr = df.iloc[-1]

            # LONG ENTRY
            if symbol not in open_long_positions:
                if check_long_entry(df):
                    open_long_positions[symbol] = {
                        "entry_price": current_price,
                        "entry_time": int(curr["timestamp"]),
                    }

                    msg = format_long_signal(
                        symbol=symbol,
                        price=current_price,
                        ema11=float(curr["ema11"]),
                        ema47=float(curr["ema47"]),
                        ema123=float(curr["ema123"]),
                    )

                    print(f"LONG SIGNAL: {symbol}", flush=True)
                    send_telegram_message(msg)

            # LONG EXIT
            else:
                if check_long_exit(df):
                    entry_price = open_long_positions[symbol]["entry_price"]
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100.0
                    reason = get_long_exit_reason(df)

                    msg = format_long_exit(
                        symbol=symbol,
                        price=current_price,
                        reason=reason,
                        pnl_pct=pnl_pct,
                    )

                    print(f"LONG EXIT: {symbol} | PnL: {pnl_pct:.2f}%", flush=True)
                    send_telegram_message(msg)

                    del open_long_positions[symbol]

            # SHORT ENTRY
            if symbol not in open_short_positions:
                if check_short_entry(df):
                    open_short_positions[symbol] = {
                        "entry_price": current_price,
                        "entry_time": int(curr["timestamp"]),
                    }

                    msg = format_short_signal(
                        symbol=symbol,
                        price=current_price,
                        ema11=float(curr["ema11"]),
                        ema29=float(curr["ema29"]),
                        ema123=float(curr["ema123"]),
                    )

                    print(f"SHORT SIGNAL: {symbol}", flush=True)
                    send_telegram_message(msg)

            # SHORT EXIT
            else:
                if check_short_exit(df):
                    entry_price = open_short_positions[symbol]["entry_price"]
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100.0
                    reason = get_short_exit_reason(df)

                    msg = format_short_exit(
                        symbol=symbol,
                        price=current_price,
                        reason=reason,
                        pnl_pct=pnl_pct,
                    )

                    print(f"SHORT EXIT: {symbol} | PnL: {pnl_pct:.2f}%", flush=True)
                    send_telegram_message(msg)

                    del open_short_positions[symbol]

            time.sleep(0.10)

        except Exception as e:
            print(f"Hata {symbol}: {e}", flush=True)


if __name__ == "__main__":
    print("EMA Scanner başlatıldı...", flush=True)
    send_telegram_message("🚀 EMA Scanner worker started")

    while True:
        try:
            scan_once()
        except Exception as e:
            print("Genel scan hatası:", e, flush=True)

        print(f"{SLEEP_SECONDS} saniye bekleniyor...", flush=True)
        time.sleep(SLEEP_SECONDS)
