from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict

from config import DRY_RUN, LOOP_SLEEP_SECONDS, RELOAD_MARKETS_EVERY_MINUTES, LEVERAGE, TIMEFRAME, TP_MOVE_PCT
from db import fetch_open_trades, init_db, insert_trade, update_trade
from scanner import BinanceFuturesScanner
from strategy import evaluate_signal
from telegram_bot import TelegramNotifier
from trade_manager import can_open_trade
from utils import pct_change, setup_logger

logger = setup_logger("ribbon.worker")

TP_ROI_TARGET = 10.0
RECOVERY_TRIGGER_ROI = -15.0
RECOVERY_EXIT_ROI = 1.0


def _calc_tp_price(entry_price: float, side: str) -> float:
    tp_move = TP_MOVE_PCT / 100.0
    if side == "long":
        return entry_price * (1 + tp_move)
    return entry_price * (1 - tp_move)


class RibbonWorker:
    def __init__(self) -> None:
        self.scanner = BinanceFuturesScanner()
        self.notifier = TelegramNotifier()
        self.last_processed_candle_by_symbol: Dict[str, str] = {}
        self.last_markets_reload = 0.0

    def reload_symbols_if_needed(self) -> list[str]:
        now = time.time()
        force = (now - self.last_markets_reload) >= RELOAD_MARKETS_EVERY_MINUTES * 60
        symbols = self.scanner.load_symbols(force=force)
        if force:
            self.last_markets_reload = now
        elif not self.last_markets_reload:
            self.last_markets_reload = now
        return symbols

    def _close_trade(self, trade: dict, exit_price: float, result: str, close_reason: str) -> None:
        trade_id = int(trade["id"])
        entry = float(trade["entry_price"])
        side = trade["side"]

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
                df = self.scanner.fetch_closed_candle_df(symbol)
                if df.empty or len(df) < 220:
                    continue

                last = df.iloc[-1]
                close_price = float(last["close"])
                high_price = float(last["high"])
                low_price = float(last["low"])
                ema200 = float(last["ema200"]) if "ema200" in last else None

                entry = float(trade["entry_price"])
                side = trade["side"]
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

                if current_roi_pct >= TP_ROI_TARGET:
                    self._close_trade(trade, close_price, "tp", "tp_roi_hit")
                    continue

                if (not recovery_mode) and current_roi_pct <= RECOVERY_TRIGGER_ROI:
                    update_trade(int(trade["id"]), {"recovery_mode": True})
                    trade["recovery_mode"] = True
                    recovery_mode = True
                    logger.info(
                        "Trade %s %s entered recovery mode at roi=%.2f%%",
                        trade["id"],
                        symbol,
                        current_roi_pct,
                    )

                if recovery_mode and current_roi_pct >= RECOVERY_EXIT_ROI:
                    self._close_trade(trade, close_price, "recovery", "recovery_exit")
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
                df = self.scanner.fetch_closed_candle_df(symbol)
                if df.empty or len(df) < 220:
                    continue

                signal_candle_time = str(df.iloc[-1]["datetime"])
                if self.last_processed_candle_by_symbol.get(symbol) == signal_candle_time:
                    continue

                ticker = self.scanner.fetch_ticker(symbol)
                signal = evaluate_signal(symbol, df, ticker)
                self.last_processed_candle_by_symbol[symbol] = signal_candle_time

                if not signal:
                    continue
                if not can_open_trade(symbol):
                    continue

                tp_price = _calc_tp_price(signal.entry_price, signal.side)
                sl_price = 0.0  # V2: hard SL yok
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
                    "entry_note": "ribbon_signal_v3_filtered",
                    "max_favor_pct": 0.0,
                    "max_adverse_pct": 0.0,
                    "recovery_mode": False,
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
