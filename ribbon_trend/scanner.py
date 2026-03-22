from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List

import ccxt
import pandas as pd

from config import (
    ENABLE_RATE_LIMIT,
    EXCHANGE_ID,
    OHLCV_LIMIT,
    ONLY_PERPETUAL,
    QUOTE_ASSET,
    REQUEST_TIMEOUT_MS,
    SYMBOL_PAUSE_SECONDS,
    TIMEFRAME,
)
from utils import setup_logger

logger = setup_logger("ribbon.scanner")


class BinanceFuturesScanner:
    def __init__(self) -> None:
        exchange_class = getattr(ccxt, EXCHANGE_ID)
        self.exchange = exchange_class(
            {
                "enableRateLimit": ENABLE_RATE_LIMIT,
                "timeout": REQUEST_TIMEOUT_MS,
                "options": {"defaultType": "future"},
            }
        )
        self._symbols_cache: List[str] = []
        self._markets_loaded_at = 0.0

    def load_symbols(self, force: bool = False) -> List[str]:
        if self._symbols_cache and not force:
            return self._symbols_cache

        logger.info("Loading Binance Futures markets...")
        markets = self.exchange.load_markets(reload=force)
        symbols: List[str] = []

        for symbol, market in markets.items():
            if not market.get("active", True):
                continue
            if market.get("quote") != QUOTE_ASSET:
                continue
            if market.get("spot"):
                continue
            if ONLY_PERPETUAL and not market.get("swap", False):
                continue
            if ":" in symbol:
                pass
            symbols.append(symbol)

        self._symbols_cache = sorted(symbols)
        self._markets_loaded_at = time.time()
        logger.info("Loaded %s futures symbols.", len(self._symbols_cache))
        return self._symbols_cache

    def fetch_ohlcv_df(
        self,
        symbol: str,
        timeframe: str | None = None,
        limit: int = OHLCV_LIMIT,
    ) -> pd.DataFrame:
        tf = timeframe or TIMEFRAME
        raw = self.exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
        time.sleep(SYMBOL_PAUSE_SECONDS)

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(
            raw,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def fetch_ticker(self, symbol: str) -> dict:
        ticker = self.exchange.fetch_ticker(symbol)
        time.sleep(SYMBOL_PAUSE_SECONDS)
        return ticker

    def fetch_closed_candle_df(
        self,
        symbol: str,
        timeframe: str | None = None,
        limit: int = OHLCV_LIMIT,
    ) -> pd.DataFrame:
        df = self.fetch_ohlcv_df(symbol, timeframe=timeframe, limit=limit)
        if df.empty or len(df) < 3:
            return df

        return df.iloc[:-1].copy().reset_index(drop=True)

    def current_utc(self) -> datetime:
        return datetime.now(timezone.utc)
