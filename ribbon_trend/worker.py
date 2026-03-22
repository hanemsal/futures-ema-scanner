from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, Optional

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
from strategy import evaluate_signal
from telegram_bot import TelegramNotifier
from trade_manager import can_open_trade
from utils import pct_change, setup_logger

logger = setup_logger("ribbon.worker")

TP_ROI_TARGET = 10.0

RECOVERY_TRIGGER_ROI = -12.0
RECOVERY_EXIT_ROI = 2.0

EARLY_FAILURE_BARS = 8
EARLY_FAILURE_MIN_FAVOR_PCT = 0.6

MAX_HOLD_BARS = 24
RECOVERY_TIMEOUT_BARS = 12

HTF_TIMEFRAME = "1h"


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


class RibbonWorker:
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

    def _fetch_df(self, symbol: str, timeframe: str):
        """
        Scanner farklı imzalar kullanıyorsa olabildiğince uyumlu dene.
        """
        try:
            return self.scanner.fetch_closed_candle_df(symbol, timeframe=timeframe)
        except TypeError:
            pass
        except Exception as exc:
            logger.warning("fetch_closed_candle_df(symbol, timeframe=%s) failed for %s: %s", timeframe, symbol, exc)

        try:
            return self.scanner.fetch_closed_candle_df(symbol, tf=timeframe)
        except TypeError:
            pass
        except Exception as exc:
            logger.warning("fetch_closed_candle_df(symbol, tf=%s) failed for %s: %s", timeframe, symbol, exc)

        # Son çare: mevcut timeframe için eski çağrı
        if timeframe == TIMEFRAME:
            try:
                return self.scanner.fetch_closed_candle_df(symbol)
            except Exception as exc:
                logger.warning("fetch_closed_candle_df(symbol) failed for %s: %s", symbol, exc)

        # Alternatif method isimleri için dene
        for method_name in ("fetch_candle_df", "fetch_ohlcv_df", "fetch_df"):
            method = getattr(self.scanner, method_name, None)
            if callable(method):
                try:
                    return method(symbol, timeframe=timeframe)
                except TypeError:
                    try:
                        return method(symbol, tf=timeframe)
                    except Exception:
                        pass
                except Exception:
                    pass

        return None

    def _close_trade(self, trade: dict, exit_price: float, result: str, close_reason: str) -> None:
        trade_id = int(trade["id"])
        entry = float(trade["entry_price"])
        side = str(trade["side"]).lower()

        if side == "long":
            pnl_pct = pct_change(exit_price, entry)
        else:
            pnl_pct = pct_change(entry, exit_price)

        roi_pct = pnl_pct * float(trade["leverage"])
        now_iso = datetime.now(timezone.utc).isoformat()

        update_trade(
            trade_id,
            {
                "status": "closed",
                "exit_price": round(exit_price, 10),
                "exit_time": now_iso,
                "pnl_pct": round(pnl_pct, 4),
                "roi_pct": round(roi_pct, 4),
                "result": result,
                "close_reason": close_reason,
                "current_price": round(exit_price, 10),
                "floating_pnl_pct": round(pnl_pct, 4),
                "floating_roi_pct": round(roi_pct, 4),
                "last_price_time": now_iso,
            },
        )

        trade["status"] = "closed"
        trade["exit_price"] = round(exit_price, 10)
        trade["pnl_pct"] = round(pnl_pct, 4)
        trade["roi_pct"] = round(roi_pct, 4)
        trade["result"] = result
        trade["close_reason"] = close_reason
        trade["current_price"] = round(exit_price, 10)
        trade["floating_pnl_pct"] = round(pnl_pct, 4)
        trade["floating_roi_pct"] = round(roi_pct, 4)
        trade["last_price_time"] = now_iso

        self.notifier.send_exit(trade)
        logger.info(
            "Closed trade %s %s => %s | roi=%.2f%% reason=%s",
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

        logger.info("Checking %s open trades...", len(open_trades))
        for trade in open_trades:
            symbol = trade["symbol"]

            try:
                df = self._fetch_df(symbol, TIMEFRAME)
                if df is None or df.empty or len(df) < 220:
                    continue

                last = df.iloc[-1]
                close_price = float(last["close"])
                high_price = float(last["high"])
                low_price = float(last["low"])
                ema200 = float(last["ema200"]) if "ema200" in last else None

                entry = float(trade["entry_price"])
                side = str(trade["side"]).lower()
                leverage = float(trade["leverage"])

                if side == "long":
                    current_pnl_pct = pct_change(close_price, entry)
                    current_favor = pct_change(high_price, entry)
                    current_adverse = pct_change(low_price, entry)
                else:
                    current_pnl_pct = pct_change(entry, close_price)
                    current_favor = pct_change(entry, low_price)
                    current_adverse = pct_change(entry, high_price)

                current_roi_pct = current_pnl_pct * leverage
                max_favor = max(float(trade.get("max_favor_pct") or 0.0), current_favor)
                max_adverse = min(float(trade.get("max_adverse_pct") or 0.0), current_adverse)
                now_iso = datetime.now(timezone.utc).isoformat()

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
                        "Trade %s %s entered recovery mode at roi=%.2f%%",
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

                if ema200 is not None:
                    if side == "long" and close_price < ema200:
                        self._close_trade(trade, close_price, "trend_break", "ema200_break")
                        continue
                    if side == "short" and close_price > ema200:
                        self._close_trade(trade, close_price, "trend_break", "ema200_break")
                        continue

            except Exception as exc:
                logger.exception("Open-trade check failed for %s: %s", symbol, exc)

    def scan_new_signals(self) -> None:
        symbols = self.reload_symbols_if_needed()
        logger.info("Scanning %s symbols...", len(symbols))

        for symbol in symbols:
            try:
                df = self._fetch_df(symbol, TIMEFRAME)
                if df is None or df.empty or len(df) < 220:
                    continue

                htf_df = self._fetch_df(symbol, HTF_TIMEFRAME)
                if htf_df is None or htf_df.empty or len(htf_df) < 220:
                    logger.info("Skipping %s because HTF dataframe is unavailable", symbol)
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
                        "DRY RUN | %s %s entry=%.8f tp=%.8f sl=%.8f",
                        signal.side.upper(),
                        signal.symbol,
                        signal.entry_price,
                        tp_price,
                        sl_price,
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
                    "entry_note": "ribbon_signal_v4_htf",
                    "max_favor_pct": 0.0,
                    "max_adverse_pct": 0.0,
                    "recovery_mode": False,
                    "recovery_mode_time": None,
                    "current_price": round(signal.entry_price, 10),
                    "floating_pnl_pct": 0.0,
                    "floating_roi_pct": 0.0,
                    "last_price_time": now_iso,
                }

                trade_id = insert_trade(payload)

                self.notifier.send_signal(trade_id, signal, tp_price, sl_price)
                logger.info(
                    "Opened trade %s | %s %s entry=%.8f tp=%.8f",
                    trade_id,
                    signal.side.upper(),
                    signal.symbol,
                    signal.entry_price,
                    tp_price,
                )
            except Exception as exc:
                logger.exception("Signal scan failed for %s: %s", symbol, exc)

    def run_forever(self) -> None:
        init_db()
        logger.info("Ribbon worker started. DRY_RUN=%s", DRY_RUN)

        while True:
            try:
                self.process_open_trades()
                self.scan_new_signals()
            except Exception as exc:
                logger.exception("Worker loop error: %s", exc)
            time.sleep(LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    RibbonWorker().run_forever()
