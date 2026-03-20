from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, Optional

from config import CHECK_TP_SL_ON_EACH_LOOP, DRY_RUN, LOOP_SLEEP_SECONDS, RELOAD_MARKETS_EVERY_MINUTES
from db import fetch_open_trades, init_db, update_trade
from scanner import BinanceFuturesScanner
from strategy import evaluate_signal
from telegram_bot import TelegramNotifier
from trade_manager import calc_tp_sl, can_open_trade, maybe_update_open_trade, open_trade
from utils import setup_logger

logger = setup_logger("ribbon.worker")


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

    def process_open_trades(self) -> None:
        open_trades = fetch_open_trades()
        if not open_trades:
            return

        logger.info("Checking %s open trades...", len(open_trades))
        for trade in open_trades:
            symbol = trade["symbol"]
            try:
                df = self.scanner.fetch_closed_candle_df(symbol)
                if df.empty:
                    continue
                last = df.iloc[-1].to_dict()
                outcome = maybe_update_open_trade(trade, last)
                if outcome and outcome.get("result") in {"tp", "sl"}:
                    trade["status"] = "closed"
                    trade["exit_price"] = outcome["exit_price"]
                    trade["result"] = outcome["result"]
                    # refresh summarized fields for telegram text
                    if trade["side"] == "long":
                        pnl_pct = ((outcome["exit_price"] - trade["entry_price"]) / trade["entry_price"]) * 100.0
                    else:
                        pnl_pct = ((trade["entry_price"] - outcome["exit_price"]) / trade["entry_price"]) * 100.0
                    trade["pnl_pct"] = round(pnl_pct, 4)
                    trade["roi_pct"] = round(pnl_pct * trade["leverage"], 4)
                    self.notifier.send_exit(trade)
                    logger.info("Closed trade %s %s => %s", trade["id"], symbol, outcome["result"])
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

                tp_price, sl_price = calc_tp_sl(signal.entry_price, signal.side)

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

                trade_id = open_trade(signal)
                self.notifier.send_signal(trade_id, signal, tp_price, sl_price)
                logger.info(
                    "Opened trade %s | %s %s entry=%.8f",
                    trade_id,
                    signal.side.upper(),
                    signal.symbol,
                    signal.entry_price,
                )
            except Exception as exc:
                logger.exception("Signal scan failed for %s: %s", symbol, exc)

    def run_forever(self) -> None:
        init_db()
        logger.info("Ribbon worker started. DRY_RUN=%s", DRY_RUN)

        while True:
            try:
                if CHECK_TP_SL_ON_EACH_LOOP:
                    self.process_open_trades()
                self.scan_new_signals()
            except Exception as exc:
                logger.exception("Worker loop error: %s", exc)
            time.sleep(LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    RibbonWorker().run_forever()
