from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config import (
    ALLOW_LONGS,
    ALLOW_SHORTS,
    EMA_FAST,
    EMA_MID,
    EMA_SLOW,
    EMA_TREND,
    EMA200_SLOPE_LOOKBACK,
    MAX_EXTENSION_PCT,
    MIN_CANDLE_BODY_PCT,
    MIN_EMA200_SLOPE_PCT,
    MIN_EXTENSION_PCT,
    MIN_NOTIONAL_24H_USDT,
    MIN_RIBBON_EXPANSION_PCT,
)
from utils import ema, pct_change


@dataclass
class SignalResult:
    side: str
    symbol: str
    entry_price: float
    signal_candle_time: str
    reason: str
    extension_pct: float
    candle_body_pct: float
    ema20: float
    ema50: float
    ema100: float
    ema200: float
    ema200_slope_pct: float


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema20"] = ema(df["close"], EMA_FAST)
    df["ema50"] = ema(df["close"], EMA_MID)
    df["ema100"] = ema(df["close"], EMA_SLOW)
    df["ema200"] = ema(df["close"], EMA_TREND)

    body = (df["close"] - df["open"]).abs()
    df["body_pct"] = (body / df["open"].replace(0, pd.NA)) * 100.0

    df["extension_pct"] = ((df["close"] - df["ema20"]) / df["ema20"].replace(0, pd.NA)) * 100.0

    # Ribbon expansion:
    # abs(ema20 - ema50) / close * 100
    df["ribbon_expansion_pct"] = (
        (df["ema20"] - df["ema50"]).abs() / df["close"].replace(0, pd.NA)
    ) * 100.0

    return df


def _ema200_slope_pct(df: pd.DataFrame) -> float:
    if len(df) <= EMA200_SLOPE_LOOKBACK:
        return 0.0
    now = float(df.iloc[-1]["ema200"])
    before = float(df.iloc[-1 - EMA200_SLOPE_LOOKBACK]["ema200"])
    return pct_change(now, before)


def _passes_common_filters(df: pd.DataFrame, ticker: dict) -> bool:
    if len(df) < 220:
        return False

    notional = float(ticker.get("quoteVolume") or 0.0)
    return notional >= MIN_NOTIONAL_24H_USDT


def evaluate_signal(symbol: str, df: pd.DataFrame, ticker: dict) -> Optional[SignalResult]:
    if df.empty:
        return None

    df = _prepare(df)

    if not _passes_common_filters(df, ticker):
        return None

    last = df.iloc[-1]
    slope_pct = _ema200_slope_pct(df)

    close_price = float(last["close"])
    open_price = float(last["open"])
    ema20 = float(last["ema20"])
    ema50 = float(last["ema50"])
    ema100 = float(last["ema100"])
    ema200 = float(last["ema200"])

    extension_pct = float(last["extension_pct"])
    body_pct = float(last["body_pct"])
    ribbon_expansion_pct = float(last["ribbon_expansion_pct"])
    signal_time = str(last["datetime"])

    green = close_price > open_price
    red = close_price < open_price

    # LONG:
    # - trend yukarı
    # - ema200 slope yeterince güçlü
    # - ribbon sıralı
    # - ribbon yeterince açık
    # - candle body yeterli
    # - extension hem minimum hem maksimum sınırda
    long_ok = all(
        [
            ALLOW_LONGS,
            close_price > ema200,
            slope_pct >= MIN_EMA200_SLOPE_PCT,
            ema20 > ema50 > ema100 > ema200,
            ribbon_expansion_pct >= MIN_RIBBON_EXPANSION_PCT,
            green,
            body_pct >= MIN_CANDLE_BODY_PCT,
            extension_pct >= MIN_EXTENSION_PCT,
            extension_pct <= MAX_EXTENSION_PCT,
        ]
    )

    if long_ok:
        return SignalResult(
            side="long",
            symbol=symbol,
            entry_price=close_price,
            signal_candle_time=signal_time,
            reason=(
                "close>ema200, ema200_up_strong, "
                "ema20>ema50>ema100>ema200, "
                "ribbon_expanded, green_candle, "
                "extension_in_range"
            ),
            extension_pct=round(extension_pct, 4),
            candle_body_pct=round(body_pct, 4),
            ema20=ema20,
            ema50=ema50,
            ema100=ema100,
            ema200=ema200,
            ema200_slope_pct=round(slope_pct, 5),
        )

    # SHORT:
    # - trend aşağı
    # - ema200 slope yeterince güçlü
    # - ribbon sıralı
    # - ribbon yeterince açık
    # - candle body yeterli
    # - extension hem minimum hem maksimum sınırda
    short_ok = all(
        [
            ALLOW_SHORTS,
            close_price < ema200,
            slope_pct <= -MIN_EMA200_SLOPE_PCT,
            ema20 < ema50 < ema100 < ema200,
            ribbon_expansion_pct >= MIN_RIBBON_EXPANSION_PCT,
            red,
            body_pct >= MIN_CANDLE_BODY_PCT,
            extension_pct <= -MIN_EXTENSION_PCT,
            abs(extension_pct) <= MAX_EXTENSION_PCT,
        ]
    )

    if short_ok:
        return SignalResult(
            side="short",
            symbol=symbol,
            entry_price=close_price,
            signal_candle_time=signal_time,
            reason=(
                "close<ema200, ema200_down_strong, "
                "ema20<ema50<ema100<ema200, "
                "ribbon_expanded, red_candle, "
                "extension_in_range"
            ),
            extension_pct=round(extension_pct, 4),
            candle_body_pct=round(body_pct, 4),
            ema20=ema20,
            ema50=ema50,
            ema100=ema100,
            ema200=ema200,
            ema200_slope_pct=round(slope_pct, 5),
        )

    return None
