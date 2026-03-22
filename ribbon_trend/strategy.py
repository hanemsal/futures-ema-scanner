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


EMA_SLOPE_CONFIRM_BARS = 3
EMA20_TREND_LOOKBACK = 2
EMA50_TREND_LOOKBACK = 3
MIN_CLOSE_DISTANCE_FROM_EMA200_PCT = 0.15

# HTF trend timeframe
HTF_TIMEFRAME = "1h"


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

    df["body_pct"] = (body / df["open"].replace(0, pd.NA)) * 100

    df["extension_pct"] = (
        (df["close"] - df["ema20"]) / df["ema20"].replace(0, pd.NA)
    ) * 100

    df["ribbon_expansion_pct"] = (
        (df["ema20"] - df["ema50"]).abs() / df["close"].replace(0, pd.NA)
    ) * 100

    df["close_vs_ema200_pct"] = (
        (df["close"] - df["ema200"]) / df["ema200"].replace(0, pd.NA)
    ) * 100

    return df


def _ema_slope_pct(series: pd.Series, lookback: int) -> float:

    if len(series) <= lookback:
        return 0.0

    now = float(series.iloc[-1])
    before = float(series.iloc[-1 - lookback])

    if before == 0:
        return 0.0

    return pct_change(now, before)


def _is_monotonic_up(series: pd.Series, bars: int) -> bool:

    if len(series) < bars + 1:
        return False

    recent = series.iloc[-(bars + 1):].tolist()

    return all(recent[i] > recent[i - 1] for i in range(1, len(recent)))


def _is_monotonic_down(series: pd.Series, bars: int) -> bool:

    if len(series) < bars + 1:
        return False

    recent = series.iloc[-(bars + 1):].tolist()

    return all(recent[i] < recent[i - 1] for i in range(1, len(recent)))


def _passes_common_filters(df: pd.DataFrame, ticker: dict) -> bool:

    if len(df) < 220:
        return False

    notional = float(ticker.get("quoteVolume") or 0)

    return notional >= MIN_NOTIONAL_24H_USDT


def evaluate_signal(symbol: str, df: pd.DataFrame, ticker: dict) -> Optional[SignalResult]:

    if df.empty:
        return None

    df = _prepare(df)

    if not _passes_common_filters(df, ticker):
        return None

    last = df.iloc[-1]

    close_price = float(last["close"])
    open_price = float(last["open"])

    ema20 = float(last["ema20"])
    ema50 = float(last["ema50"])
    ema100 = float(last["ema100"])
    ema200 = float(last["ema200"])

    extension_pct = float(last["extension_pct"])
    body_pct = float(last["body_pct"])
    ribbon_expansion_pct = float(last["ribbon_expansion_pct"])
    close_vs_ema200_pct = float(last["close_vs_ema200_pct"])

    signal_time = str(last["datetime"])

    slope_pct = _ema_slope_pct(df["ema200"], EMA200_SLOPE_LOOKBACK)

    ema20_slope_pct = _ema_slope_pct(df["ema20"], EMA20_TREND_LOOKBACK)
    ema50_slope_pct = _ema_slope_pct(df["ema50"], EMA50_TREND_LOOKBACK)

    ema200_up_confirmed = _is_monotonic_up(df["ema200"], EMA_SLOPE_CONFIRM_BARS)
    ema200_down_confirmed = _is_monotonic_down(df["ema200"], EMA_SLOPE_CONFIRM_BARS)

    ema20_up = ema20_slope_pct > 0
    ema20_down = ema20_slope_pct < 0

    ema50_up = ema50_slope_pct > 0
    ema50_down = ema50_slope_pct < 0

    green = close_price > open_price
    red = close_price < open_price

    # ----- LONG -----

    long_ok = all(
        [
            ALLOW_LONGS,
            close_price > ema200,
            close_vs_ema200_pct >= MIN_CLOSE_DISTANCE_FROM_EMA200_PCT,
            slope_pct >= MIN_EMA200_SLOPE_PCT,
            ema200_up_confirmed,
            ema20_up,
            ema50_up,
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
            reason="ribbon_long_v4_htf",
            extension_pct=round(extension_pct, 4),
            candle_body_pct=round(body_pct, 4),
            ema20=ema20,
            ema50=ema50,
            ema100=ema100,
            ema200=ema200,
            ema200_slope_pct=round(slope_pct, 5),
        )

    # ----- SHORT -----

    short_ok = all(
        [
            ALLOW_SHORTS,
            close_price < ema200,
            close_vs_ema200_pct <= -MIN_CLOSE_DISTANCE_FROM_EMA200_PCT,
            slope_pct <= -MIN_EMA200_SLOPE_PCT,
            ema200_down_confirmed,
            ema20_down,
            ema50_down,
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
            reason="ribbon_short_v4_htf",
            extension_pct=round(extension_pct, 4),
            candle_body_pct=round(body_pct, 4),
            ema20=ema20,
            ema50=ema50,
            ema100=ema100,
            ema200=ema200,
            ema200_slope_pct=round(slope_pct, 5),
        )

    return None
