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
HTF_MIN_CLOSE_DISTANCE_FROM_EMA200_PCT = 0.10

# -----------------------------
# v6 institutional filter knobs
# -----------------------------
HTF_MIN_RIBBON_EXPANSION_PCT = 0.18
HTF_MIN_EMA20_EMA50_GAP_PCT = 0.12
HTF_MIN_AVG_BODY_PCT = 0.18
HTF_BODY_LOOKBACK_BARS = 3

PULLBACK_LOOKBACK_BARS = 8
PULLBACK_EMA_PROXIMITY_PCT = 0.45
PULLBACK_MAX_CLOSE_BELOW_EMA100_PCT = 0.35

RECLAIM_LOOKBACK_BARS = 3
BREAKOUT_LOOKBACK_BARS = 6
BREAKOUT_BUFFER_PCT = 0.03

MAX_WICK_TO_BODY_RATIO = 1.80
MAX_OPPOSITE_WICK_PCT = 1.20


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
    candle_range = (df["high"] - df["low"]).replace(0, pd.NA)

    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]

    df["body_pct"] = (body / df["open"].replace(0, pd.NA)) * 100.0

    df["extension_pct"] = (
        (df["close"] - df["ema20"]) / df["ema20"].replace(0, pd.NA)
    ) * 100.0

    df["ribbon_expansion_pct"] = (
        (df["ema20"] - df["ema50"]).abs() / df["close"].replace(0, pd.NA)
    ) * 100.0

    df["close_vs_ema200_pct"] = (
        (df["close"] - df["ema200"]) / df["ema200"].replace(0, pd.NA)
    ) * 100.0

    df["close_vs_ema100_pct"] = (
        (df["close"] - df["ema100"]) / df["ema100"].replace(0, pd.NA)
    ) * 100.0

    df["ema20_ema50_gap_pct"] = (
        (df["ema20"] - df["ema50"]).abs() / df["close"].replace(0, pd.NA)
    ) * 100.0

    df["upper_wick_pct"] = (upper_wick / candle_range) * 100.0
    df["lower_wick_pct"] = (lower_wick / candle_range) * 100.0
    df["wick_to_body_ratio"] = upper_wick.where(
        df["close"] >= df["open"], lower_wick
    ) / body.replace(0, pd.NA)
    df["opposite_wick_to_body_ratio"] = lower_wick.where(
        df["close"] >= df["open"], upper_wick
    ) / body.replace(0, pd.NA)

    df = df.fillna(0)

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

    notional = float(ticker.get("quoteVolume") or 0.0)
    return notional >= MIN_NOTIONAL_24H_USDT


def _recent_avg_body_pct(df: pd.DataFrame, bars: int) -> float:
    if len(df) < bars:
        return 0.0
    return float(df["body_pct"].tail(bars).mean())


def _htf_regime_long_ok(htf: pd.DataFrame) -> bool:
    last = htf.iloc[-1]
    close_price = float(last["close"])
    ema20 = float(last["ema20"])
    ema50 = float(last["ema50"])
    ema100 = float(last["ema100"])
    ema200 = float(last["ema200"])
    close_vs_ema200_pct = float(last["close_vs_ema200_pct"])
    ribbon_expansion_pct = float(last["ribbon_expansion_pct"])
    ema20_ema50_gap_pct = float(last["ema20_ema50_gap_pct"])

    slope_pct = _ema_slope_pct(htf["ema200"], EMA200_SLOPE_LOOKBACK)
    ema200_up_confirmed = _is_monotonic_up(htf["ema200"], EMA_SLOPE_CONFIRM_BARS)
    avg_body_pct = _recent_avg_body_pct(htf, HTF_BODY_LOOKBACK_BARS)

    return all(
        [
            close_price > ema200,
            close_vs_ema200_pct >= HTF_MIN_CLOSE_DISTANCE_FROM_EMA200_PCT,
            slope_pct >= MIN_EMA200_SLOPE_PCT,
            ema200_up_confirmed,
            ema20 > ema50 > ema100 > ema200,
            ribbon_expansion_pct >= HTF_MIN_RIBBON_EXPANSION_PCT,
            ema20_ema50_gap_pct >= HTF_MIN_EMA20_EMA50_GAP_PCT,
            avg_body_pct >= HTF_MIN_AVG_BODY_PCT,
        ]
    )


def _htf_regime_short_ok(htf: pd.DataFrame) -> bool:
    last = htf.iloc[-1]
    close_price = float(last["close"])
    ema20 = float(last["ema20"])
    ema50 = float(last["ema50"])
    ema100 = float(last["ema100"])
    ema200 = float(last["ema200"])
    close_vs_ema200_pct = float(last["close_vs_ema200_pct"])
    ribbon_expansion_pct = float(last["ribbon_expansion_pct"])
    ema20_ema50_gap_pct = float(last["ema20_ema50_gap_pct"])

    slope_pct = _ema_slope_pct(htf["ema200"], EMA200_SLOPE_LOOKBACK)
    ema200_down_confirmed = _is_monotonic_down(htf["ema200"], EMA_SLOPE_CONFIRM_BARS)
    avg_body_pct = _recent_avg_body_pct(htf, HTF_BODY_LOOKBACK_BARS)

    return all(
        [
            close_price < ema200,
            close_vs_ema200_pct <= -HTF_MIN_CLOSE_DISTANCE_FROM_EMA200_PCT,
            slope_pct <= -MIN_EMA200_SLOPE_PCT,
            ema200_down_confirmed,
            ema20 < ema50 < ema100 < ema200,
            ribbon_expansion_pct >= HTF_MIN_RIBBON_EXPANSION_PCT,
            ema20_ema50_gap_pct >= HTF_MIN_EMA20_EMA50_GAP_PCT,
            avg_body_pct >= HTF_MIN_AVG_BODY_PCT,
        ]
    )


def _htf_long_ok(htf_df: pd.DataFrame) -> bool:
    if htf_df.empty or len(htf_df) < 220:
        return False
    htf = _prepare(htf_df)
    return _htf_regime_long_ok(htf)


def _htf_short_ok(htf_df: pd.DataFrame) -> bool:
    if htf_df.empty or len(htf_df) < 220:
        return False
    htf = _prepare(htf_df)
    return _htf_regime_short_ok(htf)


def _long_pullback_ok(df: pd.DataFrame) -> bool:
    if len(df) < PULLBACK_LOOKBACK_BARS + 2:
        return False

    recent = df.iloc[-(PULLBACK_LOOKBACK_BARS + 1):-1].copy()

    near_ema20 = (
        ((recent["low"] - recent["ema20"]).abs() / recent["ema20"].replace(0, pd.NA))
        * 100.0
    ) <= PULLBACK_EMA_PROXIMITY_PCT

    near_ema50 = (
        ((recent["low"] - recent["ema50"]).abs() / recent["ema50"].replace(0, pd.NA))
        * 100.0
    ) <= PULLBACK_EMA_PROXIMITY_PCT

    close_too_deep = recent["close_vs_ema100_pct"] <= -PULLBACK_MAX_CLOSE_BELOW_EMA100_PCT

    return bool((near_ema20 | near_ema50).any() and not close_too_deep.any())


def _short_pullback_ok(df: pd.DataFrame) -> bool:
    if len(df) < PULLBACK_LOOKBACK_BARS + 2:
        return False

    recent = df.iloc[-(PULLBACK_LOOKBACK_BARS + 1):-1].copy()

    near_ema20 = (
        ((recent["high"] - recent["ema20"]).abs() / recent["ema20"].replace(0, pd.NA))
        * 100.0
    ) <= PULLBACK_EMA_PROXIMITY_PCT

    near_ema50 = (
        ((recent["high"] - recent["ema50"]).abs() / recent["ema50"].replace(0, pd.NA))
        * 100.0
    ) <= PULLBACK_EMA_PROXIMITY_PCT

    close_too_deep = recent["close_vs_ema100_pct"] >= PULLBACK_MAX_CLOSE_BELOW_EMA100_PCT

    return bool((near_ema20 | near_ema50).any() and not close_too_deep.any())


def _long_reclaim_ok(df: pd.DataFrame) -> bool:
    if len(df) < RECLAIM_LOOKBACK_BARS + 1:
        return False

    recent = df.tail(RECLAIM_LOOKBACK_BARS + 1).copy()
    prev = recent.iloc[:-1]
    last = recent.iloc[-1]

    had_pullback_close = bool((prev["close"] <= prev["ema20"]).any() or (prev["low"] <= prev["ema20"]).any())
    reclaimed = float(last["close"]) > float(last["ema20"])

    return had_pullback_close and reclaimed


def _short_reclaim_ok(df: pd.DataFrame) -> bool:
    if len(df) < RECLAIM_LOOKBACK_BARS + 1:
        return False

    recent = df.tail(RECLAIM_LOOKBACK_BARS + 1).copy()
    prev = recent.iloc[:-1]
    last = recent.iloc[-1]

    had_pullback_close = bool((prev["close"] >= prev["ema20"]).any() or (prev["high"] >= prev["ema20"]).any())
    reclaimed = float(last["close"]) < float(last["ema20"])

    return had_pullback_close and reclaimed


def _long_breakout_ok(df: pd.DataFrame) -> bool:
    if len(df) < BREAKOUT_LOOKBACK_BARS + 1:
        return False

    last_close = float(df.iloc[-1]["close"])
    prev_high = float(df.iloc[-(BREAKOUT_LOOKBACK_BARS + 1):-1]["high"].max())
    min_breakout = prev_high * (1 + BREAKOUT_BUFFER_PCT / 100.0)

    return last_close >= min_breakout


def _short_breakout_ok(df: pd.DataFrame) -> bool:
    if len(df) < BREAKOUT_LOOKBACK_BARS + 1:
        return False

    last_close = float(df.iloc[-1]["close"])
    prev_low = float(df.iloc[-(BREAKOUT_LOOKBACK_BARS + 1):-1]["low"].min())
    max_breakdown = prev_low * (1 - BREAKOUT_BUFFER_PCT / 100.0)

    return last_close <= max_breakdown


def _long_wick_quality_ok(last: pd.Series) -> bool:
    wick_ratio = float(last.get("wick_to_body_ratio") or 0.0)
    opposite_ratio = float(last.get("opposite_wick_to_body_ratio") or 0.0)
    return wick_ratio <= MAX_WICK_TO_BODY_RATIO and opposite_ratio <= MAX_OPPOSITE_WICK_PCT


def _short_wick_quality_ok(last: pd.Series) -> bool:
    wick_ratio = float(last.get("wick_to_body_ratio") or 0.0)
    opposite_ratio = float(last.get("opposite_wick_to_body_ratio") or 0.0)
    return wick_ratio <= MAX_WICK_TO_BODY_RATIO and opposite_ratio <= MAX_OPPOSITE_WICK_PCT


def evaluate_signal(
    symbol: str,
    df: pd.DataFrame,
    htf_df: pd.DataFrame,
    ticker: dict,
) -> Optional[SignalResult]:
    if df.empty:
        return None

    df = _prepare(df)

    if not _passes_common_filters(df, ticker):
        return None

    if htf_df.empty or len(htf_df) < 220:
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

    htf_long_ok = _htf_long_ok(htf_df)
    htf_short_ok = _htf_short_ok(htf_df)

    long_pullback_ok = _long_pullback_ok(df)
    short_pullback_ok = _short_pullback_ok(df)

    long_reclaim_ok = _long_reclaim_ok(df)
    short_reclaim_ok = _short_reclaim_ok(df)

    long_breakout_ok = _long_breakout_ok(df)
    short_breakout_ok = _short_breakout_ok(df)

    long_wick_ok = _long_wick_quality_ok(last)
    short_wick_ok = _short_wick_quality_ok(last)

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
            htf_long_ok,
            long_pullback_ok,
            long_reclaim_ok,
            long_breakout_ok,
            long_wick_ok,
        ]
    )

    if long_ok:
        return SignalResult(
            side="long",
            symbol=symbol,
            entry_price=close_price,
            signal_candle_time=signal_time,
            reason=(
                "15m_long_v6 + 1h_regime_align, "
                "close>ema200_buffer, ema200_up_confirmed, "
                "ema20_up, ema50_up, ema20>ema50>ema100>ema200, "
                "ribbon_expanded, pullback_ok, reclaim_ok, breakout_ok, "
                "green_candle, wick_quality_ok, extension_in_range"
            ),
            extension_pct=round(extension_pct, 4),
            candle_body_pct=round(body_pct, 4),
            ema20=ema20,
            ema50=ema50,
            ema100=ema100,
            ema200=ema200,
            ema200_slope_pct=round(slope_pct, 5),
        )

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
            htf_short_ok,
            short_pullback_ok,
            short_reclaim_ok,
            short_breakout_ok,
            short_wick_ok,
        ]
    )

    if short_ok:
        return SignalResult(
            side="short",
            symbol=symbol,
            entry_price=close_price,
            signal_candle_time=signal_time,
            reason=(
                "15m_short_v6 + 1h_regime_align, "
                "close<ema200_buffer, ema200_down_confirmed, "
                "ema20_down, ema50_down, ema20<ema50<ema100<ema200, "
                "ribbon_expanded, pullback_ok, reclaim_ok, breakout_ok, "
                "red_candle, wick_quality_ok, extension_in_range"
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
