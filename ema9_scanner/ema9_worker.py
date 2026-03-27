from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List

import ccxt
import pandas as pd

from config import (
    ENTRY_NOTE,
    EMA_FAST,
    EMA_SLOW,
    EXCHANGE_ID,
    LEVERAGE,
    MIN_NOTIONAL_24H_USDT,
    OHLCV_LIMIT,
    RSI_LENGTH,
    RSI_LONG_THRESHOLD,
    SCAN_INTERVAL_SECONDS,
    SYMBOL_SLEEP_SECONDS,
    TIMEFRAME,
)

from storage import (
    fetch_open_trade_for_symbol,
    fetch_open_trade_for_symbol_side,
    init_db,
    insert_trade,
    update_trade,
)

from telegram_bot import TelegramNotifier


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    """
    TradingView'e yakın Wilder / RMA RSI
    """
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    out = 100 - (100 / (1 + rs))

    return out.fillna(0)


def pct_change(new_value: float, old_value: float) -> float:
    if old_value == 0:
        return 0.0
    return ((new_value - old_value) / old_value) * 100.0


class EMA9Worker:
    def __init__(self) -> None:
        exchange_class = getattr(ccxt, EXCHANGE_ID)

        self.exchange = exchange_class(
            {
                "enableRateLimit": True,
                "timeout": 20000,
                "options": {"defaultType": "future"},
            }
        )

        self.notifier = TelegramNotifier()
        self.last_markets_load_ts = 0.0
        self.symbols_cache: List[str] = []

    def load_symbols(self, force: bool = False) -> List[str]:
        now = time.time()

        if self.symbols_cache and not force and (now - self.last_markets_load_ts) < 3600:
            return self.symbols_cache

        print("Loading markets...")

        markets = self.exchange.load_markets()
        symbols: List[str] = []

        for symbol, market in markets.items():
            if not market.get("active", True):
                continue
            if not market.get("contract"):
                continue
            if not market.get("swap"):
                continue
            if market.get("future"):
                continue
            if market.get("quote") != "USDT":
                continue

            symbols.append(symbol)

        symbols.sort()

        self.symbols_cache = symbols
        self.last_markets_load_ts = now

        print(f"Symbols loaded (USDT perpetual only): {len(symbols)}")
        return symbols

    def fetch_df(self, symbol: str) -> pd.DataFrame:
        ohlcv = self.exchange.fetch_ohlcv(
            symbol,
            timeframe=TIMEFRAME,
            limit=OHLCV_LIMIT,
        )

        df = pd.DataFrame(
            ohlcv,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
        )

        df["datetime"] = pd.to_datetime(
            df["timestamp"],
            unit="ms",
            utc=True,
        ).astype(str)

        return df

    def fetch_ticker(self, symbol: str) -> dict:
        return self.exchange.fetch_ticker(symbol)

    def close_trade(
        self,
        trade: dict,
        exit_price: float,
        close_reason: str,
    ) -> None:
        trade_id = int(trade["id"])
        side = str(trade["side"]).lower()
        entry_price = float(trade["entry_price"])

        if side == "long":
            pnl_pct = pct_change(exit_price, entry_price)
        else:
            pnl_pct = pct_change(entry_price, exit_price)

        roi_pct = pnl_pct * float(trade["leverage"])
        now_iso = datetime.now(timezone.utc).isoformat()

        payload = {
            "status": "closed",
            "exit_price": round(exit_price, 10),
            "exit_time": now_iso,
            "pnl_pct": round(pnl_pct, 4),
            "roi_pct": round(roi_pct, 4),
            "result": "cross_exit",
            "close_reason": close_reason,
            "current_price": round(exit_price, 10),
            "floating_pnl_pct": round(pnl_pct, 4),
            "floating_roi_pct": round(roi_pct, 4),
            "last_price_time": now_iso,
        }

        update_trade(trade_id, payload)

        trade["exit_price"] = payload["exit_price"]
        trade["pnl_pct"] = payload["pnl_pct"]
        trade["roi_pct"] = payload["roi_pct"]

        self.notifier.send_exit(trade, close_reason)

        print(f"Closed trade {trade_id} {trade['symbol']} reason={close_reason}")

    def maybe_open_trade(
        self,
        symbol: str,
        side: str,
        price: float,
        signal_candle_time: str,
        reason: str,
        ema3_value: float,
        ema9_value: float,
        rsi_value: float,
        notional_24h: float,
    ) -> None:
        same_side_open = fetch_open_trade_for_symbol_side(symbol, side)
        if same_side_open:
            return

        any_open = fetch_open_trade_for_symbol(symbol)
        if any_open:
            return

        now_iso = datetime.now(timezone.utc).isoformat()

        payload = {
            "symbol": symbol,
            "side": side,
            "status": "open",
            "timeframe": TIMEFRAME,
            "leverage": LEVERAGE,
            "entry_price": round(price, 10),
            "tp_price": 0.0,
            "sl_price": 0.0,
            "entry_time": now_iso,
            "signal_candle_time": signal_candle_time,
            "reason": reason,
            "extension_pct": round(((ema3_value - ema9_value) / price) * 100.0 if price else 0.0, 4),
            "ema20": round(ema3_value, 10),
            "ema50": round(ema9_value, 10),
            "entry_note": ENTRY_NOTE,
            "current_price": round(price, 10),
            "floating_pnl_pct": 0.0,
            "floating_roi_pct": 0.0,
            "last_price_time": now_iso,
            "rsi_value": round(rsi_value, 2),
            "notional_24h_text": f"{notional_24h / 1_000_000:.2f}M",
        }

        db_payload = {k: v for k, v in payload.items() if k not in {"rsi_value", "notional_24h_text"}}

        trade_id = insert_trade(db_payload)

        self.notifier.send_signal(trade_id, payload)

        print(
            f"Opened trade {trade_id} | {side.upper()} {symbol} | "
            f"RSI={round(rsi_value, 2)}"
        )

    def process_symbol(self, symbol: str) -> None:
        try:
            ticker = self.fetch_ticker(symbol)
            notional_24h = float(ticker.get("quoteVolume") or 0.0)

            if notional_24h < MIN_NOTIONAL_24H_USDT:
                return

            df = self.fetch_df(symbol)

            if df.empty or len(df) < 50:
                return

            df["ema3"] = ema(df["close"], EMA_FAST)
            df["ema9"] = ema(df["close"], EMA_SLOW)
            df["rsi"] = rsi(df["close"], RSI_LENGTH)

            # LIVE CROSS:
            # prev = son kapanmış mum
            # last = şu an açık olan canlı mum
            prev = df.iloc[-2]
            last = df.iloc[-1]

            prev_ema3 = float(prev["ema3"])
            prev_ema9 = float(prev["ema9"])

            ema3_now = float(last["ema3"])
            ema9_now = float(last["ema9"])

            price_now = float(last["close"])

            prev_rsi = float(prev["rsi"])
            rsi_now = float(last["rsi"])

            signal_candle_time = str(last["datetime"])

            long_cross = prev_ema3 <= prev_ema9 and ema3_now > ema9_now
            short_cross = prev_ema3 >= prev_ema9 and ema3_now < ema9_now

            ema9_slope_up = ema9_now > prev_ema9
            rsi_long_ok = rsi_now > RSI_LONG_THRESHOLD and rsi_now > prev_rsi and ema9_slope_up

            open_trade = fetch_open_trade_for_symbol(symbol)

            if open_trade:
                open_side = str(open_trade["side"]).lower()

                if open_side == "long" and short_cross:
                    self.close_trade(open_trade, price_now, "ema3_below_ema9")

                if open_side == "short" and long_cross and rsi_long_ok:
                    self.close_trade(open_trade, price_now, "ema3_above_ema9")

                    self.maybe_open_trade(
                        symbol,
                        "long",
                        price_now,
                        signal_candle_time,
                        "EMA3 crossed above EMA9 | RSI rising | EMA9 slope up",
                        ema3_now,
                        ema9_now,
                        rsi_now,
                        notional_24h,
                    )

                return

            if long_cross and rsi_long_ok:
                self.maybe_open_trade(
                    symbol,
                    "long",
                    price_now,
                    signal_candle_time,
                    "EMA3 crossed above EMA9 | RSI rising | EMA9 slope up",
                    ema3_now,
                    ema9_now,
                    rsi_now,
                    notional_24h,
                )

            if short_cross:
                self.maybe_open_trade(
                    symbol,
                    "short",
                    price_now,
                    signal_candle_time,
                    "EMA3 crossed below EMA9",
                    ema3_now,
                    ema9_now,
                    rsi_now,
                    notional_24h,
                )

        except Exception as exc:
            print(f"Signal scan failed for {symbol}: {exc}")

    def run_forever(self) -> None:
        init_db()

        print("EMA9 worker started.")

        while True:
            try:
                symbols = self.load_symbols()
                print(f"Scanning {len(symbols)} symbols...")

                for symbol in symbols:
                    self.process_symbol(symbol)
                    time.sleep(SYMBOL_SLEEP_SECONDS)

            except Exception as exc:
                print(f"Worker loop error: {exc}")

            time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    EMA9Worker().run_forever()
