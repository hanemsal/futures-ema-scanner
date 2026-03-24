from __future__ import annotations

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "ribbon_trend"))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

import pandas as pd

from config import (
    DRY_RUN,
    LOOP_SLEEP_SECONDS,
    RELOAD_MARKETS_EVERY_MINUTES,
    LEVERAGE,
    TIMEFRAME,
    TP_MOVE_PCT,
)
from db import fetch_open_trades, init_db, insert_trade, update_trade
from scanner import BinanceFuturesScanner
from telegram_bot import TelegramNotifier
from trade_manager import can_open_trade
from utils import pct_change, setup_logger

logger = setup_logger("ribbon.worker.v3_short_only")

# =========================================================
# VERSION / TELEGRAM TAG
# =========================================================
ENTRY_NOTE = "ribbon_signal_v3_short_only"
VERSION_TAG = "v3_short_only"
TELEGRAM_TAG = "RIBBON V3 SHORT"

# =========================================================
# EXIT PARAMS
# =========================================================
TP_ROI_TARGET = 10.0

RECOVERY_TRIGGER_ROI = -12.0
RECOVERY_EXIT_ROI = 2.0

EARLY_FAILURE_BARS = 8
EARLY_FAILURE_MIN_FAVOR_PCT = 0.6

MAX_HOLD_BARS = 24
RECOVERY_TIMEOUT_BARS = 12

BREAK_EVEN_ARM_ROI = 6.0
BREAK_EVEN_FLOOR_ROI = 0.3

PROFIT_GIVEBACK_TRIGGER_PCT = 1.8
PROFIT_GIVEBACK_EXIT_RATIO = 0.45

TRAIL_ARM_ROI = 8.0

# =========================================================
# ENTRY FILTERS
# =========================================================
HTF_TIMEFRAME = "1h"

MIN_NOTIONAL_24H_USDT = 10_000_000.0
EMA200_SLOPE_LOOKBACK = 6

# CSV analizine göre short edge
MIN_SLOPE_PCT = -0.15
MAX_SLOPE_PCT = 0.0

MIN_EXTENSION_PCT = -1.2
MAX_EXTENSION_PCT = -0.3

MIN_CANDLE_BODY_PCT = 0.18
MIN_RIBBON_EXPANSION_PCT = 0.10

# RSI FILTER
RSI_LENGTH = 14
RSI_MAX = 55.0


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
    rsi: float


def _calc_tp_price(entry_price: float, side: str) -> float:
    tp_move = TP_MOVE_PCT / 100.0
    if side == "long":
        return entry_price * (1 + tp_move)
    return entry_price * (1 - tp_move)


def _parse_timeframe_to_minutes(timeframe: str) -> int:
    tf = (timeframe or "").strip().lower()
    if not tf:
        return 15

    try:
        if tf.endswith("m"):
            return int(tf[:-1])
        if tf.endswith("h"):
            return int(tf[:-1]) * 60
        if tf.endswith("d"):
            return int(tf[:-1]) * 1440
    except Exception:
        logger.warning("Failed to parse timeframe=%s, fallback to 15m", timeframe)

    return 15


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        logger.warning("Could not parse datetime value=%s", value)
        return None


def _bars_since(start_iso: Optional[str], timeframe_minutes: int) -> int:
    start_dt = _parse_iso_datetime(start_iso)
    if not start_dt:
        return 0

    now_dt = datetime.now(timezone.utc)
    seconds = max((now_dt - start_dt).total_seconds(), 0)
    bar_seconds = max(timeframe_minutes * 60, 60)
    return int(seconds // bar_seconds)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))

    # loss 0 ise RSI 100 olsun
    rsi = rsi.fillna(100)
    return rsi


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()

    x["ema20"] = _ema(x["close"], 20)
    x["ema50"] = _ema(x["close"], 50)
    x["ema100"] = _ema(x["close"], 100)
    x["ema200"] = _ema(x["close"], 200)

    x["rsi"] = _rsi(x["close"], length=RSI_LENGTH)

    x["extension_pct"] = (
        (x["close"] - x["ema20"]) / x["close"].replace(0, pd.NA)
    ) * 100.0

    x["body_pct"] = (
        (x["close"] - x["open"]).abs() / x["open"].replace(0, pd.NA)
    ) * 100.0

    x["ribbon_expansion_pct"] = (
        (x["ema20"] - x["ema50"]).abs() / x["close"].replace(0, pd.NA)
    ) * 100.0

    return x


def _ema200_slope_pct(df: pd.DataFrame) -> float:
    if len(df) <= EMA200_SLOPE_LOOKBACK:
        return 0.0
    now_val = float(df.iloc[-1]["ema200"])
    before_val = float(df.iloc[-1 - EMA200_SLOPE_LOOKBACK]["ema200"])
    return pct_change(now_val, before_val)


def _passes_common_filters(df: pd.DataFrame, ticker: dict) -> bool:
    if df.empty or len(df) < 220:
        return False

    notional = float(ticker.get("quoteVolume") or 0.0)
    if notional < MIN_NOTIONAL_24H_USDT:
        return False

    return True


def evaluate_signal(
    symbol: str,
    df: pd.DataFrame,
    htf_df: pd.DataFrame,
    ticker: dict,
) -> Optional[SignalResult]:
    if df.empty or htf_df.empty:
        return None

    df = _prepare(df)
    htf_df = _prepare(htf_df)

    if not _passes_common_filters(df, ticker):
        return None

    last = df.iloc[-1]
    htf_last = htf_df.iloc[-1]

    if pd.isna(last["rsi"]):
        return None

    close_price = float(last["close"])
    open_price = float(last["open"])

    ema20 = float(last["ema20"])
    ema50 = float(last["ema50"])
    ema100 = float(last["ema100"])
    ema200 = float(last["ema200"])

    htf_close = float(htf_last["close"])
    htf_ema200 = float(htf_last["ema200"])

    extension_pct = float(last["extension_pct"])
    body_pct = float(last["body_pct"])
    ribbon_expansion_pct = float(last["ribbon_expansion_pct"])
    slope_pct = _ema200_slope_pct(df)
    htf_slope_pct = _ema200_slope_pct(htf_df)
    rsi = float(last["rsi"])

    signal_time = str(last["datetime"])
    red = close_price < open_price

    short_ok = all(
        [
            close_price < ema200,
            htf_close < htf_ema200,
            ema20 < ema50 < ema100 < ema200,
            red,
            body_pct >= MIN_CANDLE_BODY_PCT,
            ribbon_expansion_pct >= MIN_RIBBON_EXPANSION_PCT,
            extension_pct >= MIN_EXTENSION_PCT,
            extension_pct <= MAX_EXTENSION_PCT,
            slope_pct >= MIN_SLOPE_PCT,
            slope_pct <= MAX_SLOPE_PCT,
            htf_slope_pct <= 0,
            rsi < RSI_MAX,
        ]
    )

    if not short_ok:
        return None

    reason = (
        f"[{TELEGRAM_TAG}] "
        "short_only, close<ema200, htf_close<htf_ema200, "
        "ema20<ema50<ema100<ema200, red_candle, "
        f"extension_in_range({MIN_EXTENSION_PCT}..{MAX_EXTENSION_PCT}), "
        f"slope_in_range({MIN_SLOPE_PCT}..{MAX_SLOPE_PCT}), "
        f"rsi<{RSI_MAX}, "
        "ribbon_expanded"
    )

    return SignalResult(
        side="short",
        symbol=symbol,
        entry_price=close_price,
        signal_candle_time=signal_time,
        reason=reason,
        extension_pct=round(extension_pct, 4),
        candle_body_pct=round(body_pct, 4),
        ema20=ema20,
        ema50=ema50,
        ema100=ema100,
        ema200=ema200,
        ema200_slope_pct=round(slope_pct, 5),
        rsi=round(rsi, 2),
    )


class RibbonWorkerV3ShortOnly:
    def __init__(self) -> None:
        self.scanner = BinanceFuturesScanner()
        self.notifier = TelegramNotifier()
        self.last_processed_candle_by_symbol: Dict[str, str] = {}
        self.last_markets_reload = 0.0
        self.timeframe_minutes = _parse_timeframe_to_minutes(TIMEFRAME)

    def reload_symbols_if_needed(self) -> list[str]:
        now = time.time()
        force = (now - self.last_markets_reload) >= RELOAD_MARKETS_EVERY_MINUTES * 60
        symbols = self.scanner.load_symbols(force=force)

        if force:
            self.last_markets_reload = now
        elif not self.last_markets_reload:
            self.last_markets_reload = now

        return symbols

    def _safe_send_signal(self, trade_id: int, signal: SignalResult, tp_price: float, sl_price: float) -> None:
        try:
            self.notifier.send_signal(trade_id, signal, tp_price, sl_price)
        except Exception:
            logger.exception(
                "[%s] send_signal failed for trade_id=%s symbol=%s",
                TELEGRAM_TAG,
                trade_id,
                signal.symbol,
            )

    def _safe_send_exit(self, trade: dict) -> None:
        try:
            self.notifier.send_exit(trade)
        except Exception:
            logger.exception(
                "[%s] send_exit failed for trade_id=%s symbol=%s",
                TELEGRAM_TAG,
                trade.get("id"),
                trade.get("symbol"),
            )

    def _close_trade(self, trade: dict, exit_price: float, result: str, close_reason: str) -> None:
        trade_id = int(trade["id"])
        entry = float(trade["entry_price"])
        side = str(trade["side"]).lower()

        if side == "long":
            pnl_pct = pct_change(exit_price, entry)
        else:
            pnl_pct = pct_change(entry, exit_price)

        roi_pct = pnl_pct * float(trade["leverage"])

        payload = {
            "status": "closed",
            "exit_price": round(exit_price, 10),
            "exit_time": datetime.now(timezone.utc).isoformat(),
            "pnl_pct": round(pnl_pct, 4),
            "roi_pct": round(roi_pct, 4),
            "result": result,
            "close_reason": close_reason,
            "current_price": round(exit_price, 10),
            "floating_pnl_pct": round(pnl_pct, 4),
            "floating_roi_pct": round(roi_pct, 4),
            "last_price_time": datetime.now(timezone.utc).isoformat(),
        }

        update_trade(trade_id, payload)

        trade["status"] = "closed"
        trade["exit_price"] = payload["exit_price"]
        trade["pnl_pct"] = payload["pnl_pct"]
        trade["roi_pct"] = payload["roi_pct"]
        trade["result"] = result
        trade["close_reason"] = close_reason

        self._safe_send_exit(trade)

        logger.info(
            "[%s] Closed trade %s %s => %s | roi=%.2f%% reason=%s",
            TELEGRAM_TAG,
            trade_id,
            trade["symbol"],
            result,
            roi_pct,
            close_reason,
        )

    def process_open_trades(self) -> None:
        open_trades = fetch_open_trades()
        if not open_trades:
            return

        open_trades = [
            t for t in open_trades
            if str(t.get("entry_note", "")) == ENTRY_NOTE
        ]

        if not open_trades:
            return

        logger.info("[%s] Checking %s open trades...", TELEGRAM_TAG, len(open_trades))

        for trade in open_trades:
            symbol = trade["symbol"]

            try:
                df = self.scanner.fetch_closed_candle_df(symbol, timeframe=TIMEFRAME)
                if df.empty or len(df) < 220:
                    continue

                df = _prepare(df)
                last = df.iloc[-1]

                close_price = float(last["close"])
                ema20 = float(last["ema20"])
                ema200 = float(last["ema200"])

                side = str(trade["side"]).lower()
                entry_price = float(trade["entry_price"])
                leverage = float(trade["leverage"])

                if side == "long":
                    current_pnl_pct = pct_change(close_price, entry_price)
                else:
                    current_pnl_pct = pct_change(entry_price, close_price)

                current_roi_pct = current_pnl_pct * leverage
                now_iso = datetime.now(timezone.utc).isoformat()

                max_favor = max(float(trade.get("max_favor_pct") or 0.0), current_pnl_pct)
                max_adverse = min(float(trade.get("max_adverse_pct") or 0.0), current_pnl_pct)

                update_trade(
                    int(trade["id"]),
                    {
                        "current_price": round(close_price, 10),
                        "floating_pnl_pct": round(current_pnl_pct, 4),
                        "floating_roi_pct": round(current_roi_pct, 4),
                        "last_price_time": now_iso,
                        "max_favor_pct": round(max_favor, 4),
                        "max_adverse_pct": round(max_adverse, 4),
                    },
                )

                trade["current_price"] = round(close_price, 10)
                trade["floating_pnl_pct"] = round(current_pnl_pct, 4)
                trade["floating_roi_pct"] = round(current_roi_pct, 4)
                trade["last_price_time"] = now_iso
                trade["max_favor_pct"] = round(max_favor, 4)
                trade["max_adverse_pct"] = round(max_adverse, 4)

                recovery_mode = bool(trade.get("recovery_mode") or False)
                entry_bars_open = _bars_since(trade.get("entry_time"), self.timeframe_minutes)
                recovery_bars_open = _bars_since(trade.get("recovery_mode_time"), self.timeframe_minutes)

                max_favor_roi = max_favor * leverage
                giveback_pct = max_favor - current_pnl_pct

                if current_roi_pct >= TP_ROI_TARGET:
                    self._close_trade(trade, close_price, "tp", "tp_roi_hit")
                    continue

                if (not recovery_mode) and current_roi_pct <= RECOVERY_TRIGGER_ROI:
                    update_trade(
                        int(trade["id"]),
                        {
                            "recovery_mode": True,
                            "recovery_mode_time": now_iso,
                        },
                    )
                    trade["recovery_mode"] = True
                    trade["recovery_mode_time"] = now_iso
                    recovery_mode = True
                    recovery_bars_open = 0

                    logger.info(
                        "[%s] Trade %s %s entered recovery mode at roi=%.2f%%",
                        TELEGRAM_TAG,
                        trade["id"],
                        symbol,
                        current_roi_pct,
                    )

                if recovery_mode and current_roi_pct >= RECOVERY_EXIT_ROI:
                    self._close_trade(trade, close_price, "recovery", "recovery_exit")
                    continue

                if (not recovery_mode) and entry_bars_open >= EARLY_FAILURE_BARS:
                    if max_favor < EARLY_FAILURE_MIN_FAVOR_PCT:
                        self._close_trade(trade, close_price, "time_exit", "early_failure_exit")
                        continue

                if recovery_mode and recovery_bars_open >= RECOVERY_TIMEOUT_BARS:
                    self._close_trade(trade, close_price, "recovery_timeout", "recovery_timeout_exit")
                    continue

                if (not recovery_mode) and entry_bars_open >= MAX_HOLD_BARS:
                    self._close_trade(trade, close_price, "time_exit", "max_hold_exit")
                    continue

                if (
                    (not recovery_mode)
                    and max_favor_roi >= BREAK_EVEN_ARM_ROI
                    and current_roi_pct <= BREAK_EVEN_FLOOR_ROI
                ):
                    self._close_trade(trade, close_price, "profit_lock", "break_even_lock_exit")
                    continue

                if (
                    (not recovery_mode)
                    and max_favor >= PROFIT_GIVEBACK_TRIGGER_PCT
                    and max_favor > 0
                    and giveback_pct >= (max_favor * PROFIT_GIVEBACK_EXIT_RATIO)
                    and current_pnl_pct > 0
                ):
                    self._close_trade(trade, close_price, "profit_lock", "profit_giveback_exit")
                    continue

                if (not recovery_mode) and max_favor_roi >= TRAIL_ARM_ROI:
                    if side == "short" and close_price > ema20:
                        self._close_trade(trade, close_price, "trail_exit", "ema20_trail_break")
                        continue

                if side == "short" and close_price > ema200:
                    self._close_trade(trade, close_price, "trend_break", "ema200_break")
                    continue

            except Exception as exc:
                logger.exception("[%s] Open-trade check failed for %s: %s", TELEGRAM_TAG, symbol, exc)

    def scan_new_signals(self) -> None:
        symbols = self.reload_symbols_if_needed()
        logger.info("[%s] Scanning %s symbols...", TELEGRAM_TAG, len(symbols))

        for symbol in symbols:
            try:
                df = self.scanner.fetch_closed_candle_df(symbol, timeframe=TIMEFRAME)
                if df.empty or len(df) < 220:
                    continue

                htf_df = self.scanner.fetch_closed_candle_df(symbol, timeframe=HTF_TIMEFRAME)
                if htf_df.empty or len(htf_df) < 220:
                    continue

                signal_candle_time = str(df.iloc[-1]["datetime"])
                if self.last_processed_candle_by_symbol.get(symbol) == signal_candle_time:
                    continue

                ticker = self.scanner.fetch_ticker(symbol)
                signal = evaluate_signal(symbol, df, htf_df, ticker)
                self.last_processed_candle_by_symbol[symbol] = signal_candle_time

                if not signal:
                    continue

                if not can_open_trade(symbol):
                    continue

                tp_price = _calc_tp_price(signal.entry_price, signal.side)
                sl_price = 0.0
                now_iso = datetime.now(timezone.utc).isoformat()

                if DRY_RUN:
                    logger.info(
                        "[%s] DRY RUN | %s %s entry=%.8f tp=%.8f sl=%.8f slope=%.5f ext=%.4f rsi=%.2f",
                        TELEGRAM_TAG,
                        signal.side.upper(),
                        signal.symbol,
                        signal.entry_price,
                        tp_price,
                        sl_price,
                        signal.ema200_slope_pct,
                        signal.extension_pct,
                        signal.rsi,
                    )
                    continue

                payload = {
                    "symbol": signal.symbol,
                    "side": signal.side,
                    "status": "open",
                    "timeframe": TIMEFRAME,
                    "leverage": LEVERAGE,
                    "entry_price": round(signal.entry_price, 10),
                    "tp_price": round(tp_price, 10),
                    "sl_price": round(sl_price, 10),
                    "entry_time": now_iso,
                    "signal_candle_time": signal.signal_candle_time,
                    "reason": signal.reason,
                    "extension_pct": signal.extension_pct,
                    "candle_body_pct": signal.candle_body_pct,
                    "ema20": round(signal.ema20, 10),
                    "ema50": round(signal.ema50, 10),
                    "ema100": round(signal.ema100, 10),
                    "ema200": round(signal.ema200, 10),
                    "ema200_slope_pct": signal.ema200_slope_pct,
                    "entry_note": ENTRY_NOTE,
                    "max_favor_pct": 0.0,
                    "max_adverse_pct": 0.0,
                    "recovery_mode": False,
                    "current_price": round(signal.entry_price, 10),
                    "floating_pnl_pct": 0.0,
                    "floating_roi_pct": 0.0,
                    "last_price_time": now_iso,
                }

                trade_id = insert_trade(payload)
                self._safe_send_signal(trade_id, signal, tp_price, sl_price)

                logger.info(
                    "[%s] Opened trade %s | %s %s entry=%.8f tp=%.8f slope=%.5f ext=%.4f rsi=%.2f",
                    TELEGRAM_TAG,
                    trade_id,
                    signal.side.upper(),
                    signal.symbol,
                    signal.entry_price,
                    tp_price,
                    signal.ema200_slope_pct,
                    signal.extension_pct,
                    signal.rsi,
                )

            except Exception as exc:
                logger.exception("[%s] Signal scan failed for %s: %s", TELEGRAM_TAG, symbol, exc)

    def run_forever(self) -> None:
        init_db()
        logger.info(
            "[%s] Ribbon V3 Short-Only worker started. DRY_RUN=%s | entry_note=%s | version=%s",
            TELEGRAM_TAG,
            DRY_RUN,
            ENTRY_NOTE,
            VERSION_TAG,
        )

        while True:
            try:
                self.process_open_trades()
                self.scan_new_signals()
            except Exception as exc:
                logger.exception("[%s] Worker loop error: %s", TELEGRAM_TAG, exc)

            time.sleep(LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    RibbonWorkerV3ShortOnly().run_forever()
