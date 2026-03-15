import time
from datetime import datetime, timezone

import ccxt
import pandas as pd

from indicators import add_ema_set
from telegram_utils import (
    send_telegram_message,
    format_entry_signal,
    format_exit_signal,
)
from config import (
    TIMEFRAME,
    SLEEP_SECONDS,
    CANDLE_LIMIT,
    EXCLUDED_SYMBOLS,
    PUMP_MIN_QUOTEVOL24H,
    PUMP_MAX_QUOTEVOL24H,
    PUMP_MIN_MARKETCAP,
    PUMP_MAX_MARKETCAP,
    PUMP_EMA_FAST,
    PUMP_EMA_MID,
    PUMP_EMA_TREND,
    PUMP_MIN_VOL_RATIO,
    DIP_MIN_QUOTEVOL24H,
    DIP_MAX_QUOTEVOL24H,
    DIP_MIN_MARKETCAP,
    DIP_MAX_MARKETCAP,
    DIP_EMA_FAST,
    DIP_EMA_MID,
    DIP_EMA_TREND,
    DIP_MIN_VOL_RATIO,
)
from storage import init_db, create_trade, update_trade_metrics, close_trade

exchange = ccxt.binance({
    "options": {"defaultType": "future"},
    "enableRateLimit": True,
})

open_long_positions = {}
open_short_positions = {}


def normalize_symbol(symbol: str) -> str:
    return symbol.replace("/", "").replace(":", "").upper()


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

    print(f"Toplam futures coin bulundu: {len(symbols)}", flush=True)
    return symbols


def fetch_ohlcv_df(symbol: str, timeframe: str = "15m", limit: int = 200):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    return df


def fetch_all_tickers_map():
    try:
        return exchange.fetch_tickers()
    except Exception as e:
        print(f"Toplu ticker alınamadı: {e}", flush=True)
        return {}


def get_quote_volume_24h(ticker: dict) -> float:
    try:
        return float(
            ticker.get("quoteVolume")
            or ticker.get("baseVolumeQuote")
            or 0.0
        )
    except Exception:
        return 0.0


def get_market_cap(symbol: str, market: dict) -> float | None:
    """
    Binance futures verisinde güvenilir market cap yok.
    Alanı geleceğe hazır tutuyoruz.
    """
    try:
        info = market.get("info") or {}
        for key in ("marketCap", "market_cap", "marketcap"):
            if info.get(key) is not None:
                return float(info.get(key))
    except Exception:
        pass
    return None


def crosses_above(prev_fast, prev_mid, curr_fast, curr_mid) -> bool:
    return prev_fast <= prev_mid and curr_fast > curr_mid


def crosses_below(prev_fast, prev_mid, curr_fast, curr_mid) -> bool:
    return prev_fast >= prev_mid and curr_fast < curr_mid


def in_range(value, min_v, max_v) -> bool:
    if value is None:
        return False
    return min_v <= value <= max_v


def passes_marketcap_filter(market_cap, min_cap, max_cap) -> bool:
    if market_cap is None:
        return True
    return min_cap <= market_cap <= max_cap


def get_closed_signal_rows(df):
    if len(df) < 3:
        return None, None

    prev_closed = df.iloc[-3]
    last_closed = df.iloc[-2]
    return prev_closed, last_closed


def calc_live_metrics(side: str, entry_price: float, current_price: float, position: dict, entry_time: datetime):
    if side == "LONG":
        live_pnl = ((current_price - entry_price) / entry_price) * 100.0
    else:
        live_pnl = ((entry_price - current_price) / current_price) * 100.0

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

    return abs(float(last_closed["ema_fast"]) - float(last_closed["ema_trend"])) / price * 100.0


def evaluate_pump_signal(symbol, df, quote_vol_24h, market_cap, volume_ratio):
    if not in_range(quote_vol_24h, PUMP_MIN_QUOTEVOL24H, PUMP_MAX_QUOTEVOL24H):
        return None

    if not passes_marketcap_filter(market_cap, PUMP_MIN_MARKETCAP, PUMP_MAX_MARKETCAP):
        return None

    df = add_ema_set(df, PUMP_EMA_FAST, PUMP_EMA_MID, PUMP_EMA_TREND)
    prev_closed, last_closed = get_closed_signal_rows(df)
    if prev_closed is None:
        return None

    if (
        crosses_above(prev_closed["ema_fast"], prev_closed["ema_mid"], last_closed["ema_fast"], last_closed["ema_mid"])
        and last_closed["ema_mid"] > last_closed["ema_trend"]
        and last_closed["close"] > last_closed["ema_mid"]
        and volume_ratio >= PUMP_MIN_VOL_RATIO
    ):
        return {
            "mode": "PUMP",
            "side": "LONG",
            "ema_fast_len": PUMP_EMA_FAST,
            "ema_mid_len": PUMP_EMA_MID,
            "ema_trend_len": PUMP_EMA_TREND,
            "entry_reason": "pump_long_fast_cross_above_mid",
            "last_closed": last_closed,
        }

    if (
        crosses_below(prev_closed["ema_fast"], prev_closed["ema_mid"], last_closed["ema_fast"], last_closed["ema_mid"])
        and last_closed["ema_mid"] < last_closed["ema_trend"]
        and last_closed["close"] < last_closed["ema_mid"]
        and volume_ratio >= PUMP_MIN_VOL_RATIO
    ):
        return {
            "mode": "PUMP",
            "side": "SHORT",
            "ema_fast_len": PUMP_EMA_FAST,
            "ema_mid_len": PUMP_EMA_MID,
            "ema_trend_len": PUMP_EMA_TREND,
            "entry_reason": "pump_short_fast_cross_below_mid",
            "last_closed": last_closed,
        }

    return None


def evaluate_dip_signal(symbol, df, quote_vol_24h, market_cap, volume_ratio):
    if not in_range(quote_vol_24h, DIP_MIN_QUOTEVOL24H, DIP_MAX_QUOTEVOL24H):
        return None

    if not passes_marketcap_filter(market_cap, DIP_MIN_MARKETCAP, DIP_MAX_MARKETCAP):
        return None

    df = add_ema_set(df, DIP_EMA_FAST, DIP_EMA_MID, DIP_EMA_TREND)
    prev_closed, last_closed = get_closed_signal_rows(df)
    if prev_closed is None:
        return None

    mid_turning_up = last_closed["ema_mid"] >= prev_closed["ema_mid"]
    mid_turning_down = last_closed["ema_mid"] <= prev_closed["ema_mid"]

    if (
        crosses_above(prev_closed["ema_fast"], prev_closed["ema_mid"], last_closed["ema_fast"], last_closed["ema_mid"])
        and (last_closed["ema_mid"] >= last_closed["ema_trend"] or mid_turning_up)
        and last_closed["close"] > last_closed["ema_fast"]
        and volume_ratio >= DIP_MIN_VOL_RATIO
    ):
        return {
            "mode": "DIP",
            "side": "LONG",
            "ema_fast_len": DIP_EMA_FAST,
            "ema_mid_len": DIP_EMA_MID,
            "ema_trend_len": DIP_EMA_TREND,
            "entry_reason": "dip_long_fast_cross_above_mid",
            "last_closed": last_closed,
        }

    if (
        crosses_below(prev_closed["ema_fast"], prev_closed["ema_mid"], last_closed["ema_fast"], last_closed["ema_mid"])
        and (last_closed["ema_mid"] <= last_closed["ema_trend"] or mid_turning_down)
        and last_closed["close"] < last_closed["ema_fast"]
        and volume_ratio >= DIP_MIN_VOL_RATIO
    ):
        return {
            "mode": "DIP",
            "side": "SHORT",
            "ema_fast_len": DIP_EMA_FAST,
            "ema_mid_len": DIP_EMA_MID,
            "ema_trend_len": DIP_EMA_TREND,
            "entry_reason": "dip_short_fast_cross_below_mid",
            "last_closed": last_closed,
        }

    return None


def get_exit_reason(df, side: str) -> str:
    prev_closed, last_closed = get_closed_signal_rows(df)
    if prev_closed is None:
        return "Unknown"

    if side == "LONG":
        if crosses_below(prev_closed["ema_fast"], prev_closed["ema_mid"], last_closed["ema_fast"], last_closed["ema_mid"]):
            return "EMA fast crossed below EMA mid"
        return "EMA fast moved below EMA mid"

    if side == "SHORT":
        if crosses_above(prev_closed["ema_fast"], prev_closed["ema_mid"], last_closed["ema_fast"], last_closed["ema_mid"]):
            return "EMA fast crossed above EMA mid"
        return "EMA fast moved above EMA mid"

    return "Unknown"


def should_exit_trade(trade_meta: dict, raw_df: pd.DataFrame):
    df = add_ema_set(
        raw_df,
        trade_meta["ema_fast_len"],
        trade_meta["ema_mid_len"],
        trade_meta["ema_trend_len"],
    )
    prev_closed, last_closed = get_closed_signal_rows(df)
    if prev_closed is None:
        return False, "Unknown"

    if trade_meta["side"] == "LONG":
        if crosses_below(prev_closed["ema_fast"], prev_closed["ema_mid"], last_closed["ema_fast"], last_closed["ema_mid"]):
            return True, get_exit_reason(df, "LONG")
    else:
        if crosses_above(prev_closed["ema_fast"], prev_closed["ema_mid"], last_closed["ema_fast"], last_closed["ema_mid"]):
            return True, get_exit_reason(df, "SHORT")

    return False, "Unknown"


def scan_once():
    global open_long_positions
    global open_short_positions

    print("USDT futures coin listesi alınıyor...", flush=True)
    all_symbols = get_usdt_futures_symbols()
    all_tickers = fetch_all_tickers_map()
    markets = exchange.markets or exchange.load_markets()

    print(f"Taranacak coin sayısı: {len(all_symbols)}", flush=True)

    for symbol in all_symbols:
        try:
            ticker = all_tickers.get(symbol) or {}
            quote_volume_24h = get_quote_volume_24h(ticker)
            market = markets.get(symbol) or {}
            market_cap = get_market_cap(symbol, market)

            # Universe'e hiç girmeyen coinleri komple atla
            passes_any_universe = (
                (
                    in_range(quote_volume_24h, PUMP_MIN_QUOTEVOL24H, PUMP_MAX_QUOTEVOL24H)
                    and passes_marketcap_filter(market_cap, PUMP_MIN_MARKETCAP, PUMP_MAX_MARKETCAP)
                )
                or
                (
                    in_range(quote_volume_24h, DIP_MIN_QUOTEVOL24H, DIP_MAX_QUOTEVOL24H)
                    and passes_marketcap_filter(market_cap, DIP_MIN_MARKETCAP, DIP_MAX_MARKETCAP)
                )
            )

            if not passes_any_universe:
                continue

            df = fetch_ohlcv_df(symbol, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)
            if len(df) < max(PUMP_EMA_TREND, DIP_EMA_TREND) + 5:
                continue

            prev_closed, last_closed_raw = get_closed_signal_rows(df)
            if prev_closed is None or last_closed_raw is None:
                continue

            current_price = float(last_closed_raw["close"])
            current_ts = datetime.now(timezone.utc)
            cross_time = datetime.fromtimestamp(
                int(last_closed_raw["timestamp"]) / 1000,
                tz=timezone.utc,
            )
            cross_price = current_price
            cross_candle_volume = calc_cross_candle_quote_volume(last_closed_raw)
            avg_qv_10 = calc_avg_quote_volume_last_10_closed(df)
            volume_ratio = (cross_candle_volume / avg_qv_10) if avg_qv_10 > 0 else 0.0

            if symbol not in open_long_positions and symbol not in open_short_positions:
                pump_signal = evaluate_pump_signal(
                    symbol=symbol,
                    df=df,
                    quote_vol_24h=quote_volume_24h,
                    market_cap=market_cap,
                    volume_ratio=volume_ratio,
                )
                dip_signal = evaluate_dip_signal(
                    symbol=symbol,
                    df=df,
                    quote_vol_24h=quote_volume_24h,
                    market_cap=market_cap,
                    volume_ratio=volume_ratio,
                )

                signal = pump_signal or dip_signal

                if signal:
                    signal_last = signal["last_closed"]
                    ema_distance = calc_ema_distance(signal_last)

                    trade_id = create_trade(
                        symbol=symbol,
                        side=signal["side"],
                        mode=signal["mode"],
                        entry_price=current_price,
                        entry_time=current_ts,
                        timeframe=TIMEFRAME,
                        cross_time=cross_time,
                        cross_price=cross_price,
                        quote_volume_24h=float(quote_volume_24h),
                        cross_candle_volume=float(cross_candle_volume),
                        ema_distance=float(ema_distance),
                        volume_ratio=float(volume_ratio),
                        market_cap=market_cap,
                        ema_fast=signal["ema_fast_len"],
                        ema_mid=signal["ema_mid_len"],
                        ema_trend=signal["ema_trend_len"],
                        entry_reason=signal["entry_reason"],
                    )

                    pos = {
                        "trade_id": trade_id,
                        "side": signal["side"],
                        "mode": signal["mode"],
                        "entry_price": current_price,
                        "entry_time": current_ts,
                        "max_profit_pct": 0.0,
                        "max_drawdown_pct": 0.0,
                        "ema_fast_len": signal["ema_fast_len"],
                        "ema_mid_len": signal["ema_mid_len"],
                        "ema_trend_len": signal["ema_trend_len"],
                    }

                    if signal["side"] == "LONG":
                        open_long_positions[symbol] = pos
                    else:
                        open_short_positions[symbol] = pos

                    msg = format_entry_signal(
                        symbol=symbol,
                        side=signal["side"],
                        mode=signal["mode"],
                        price=current_price,
                        ema_fast_val=float(signal_last["ema_fast"]),
                        ema_mid_val=float(signal_last["ema_mid"]),
                        ema_trend_val=float(signal_last["ema_trend"]),
                        ema_fast_len=signal["ema_fast_len"],
                        ema_mid_len=signal["ema_mid_len"],
                        ema_trend_len=signal["ema_trend_len"],
                        vol_ratio=float(volume_ratio),
                        quote_vol_24h=float(quote_volume_24h),
                    )

                    print(
                        f"{signal['mode']} {signal['side']} SIGNAL: {symbol} | "
                        f"qv24h={quote_volume_24h:.2f} | "
                        f"cross_vol={cross_candle_volume:.2f} | "
                        f"ema_set={signal['ema_fast_len']}/{signal['ema_mid_len']}/{signal['ema_trend_len']} | "
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

                exit_now, reason = should_exit_trade(pos, df)
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

                    msg = format_exit_signal(
                        symbol=symbol,
                        side="LONG",
                        mode=pos["mode"],
                        price=current_price,
                        reason=reason,
                        pnl_pct=live_pnl,
                    )

                    print(f"{pos['mode']} LONG EXIT: {symbol} | PnL: {live_pnl:.2f}%", flush=True)
                    send_telegram_message(msg)
                    del open_long_positions[symbol]

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

                exit_now, reason = should_exit_trade(pos, df)
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

                    msg = format_exit_signal(
                        symbol=symbol,
                        side="SHORT",
                        mode=pos["mode"],
                        price=current_price,
                        reason=reason,
                        pnl_pct=live_pnl,
                    )

                    print(f"{pos['mode']} SHORT EXIT: {symbol} | PnL: {live_pnl:.2f}%", flush=True)
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
