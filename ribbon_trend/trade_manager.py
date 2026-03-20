from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from config import LEVERAGE, ONE_OPEN_TRADE_PER_SYMBOL, SL_MOVE_PCT, TIMEFRAME, TP_MOVE_PCT
from db import (
    fetch_open_trade_for_symbol,
    insert_trade,
    update_trade,
)
from utils import pct_change


def calc_tp_sl(entry_price: float, side: str) -> tuple[float, float]:
    tp_move = TP_MOVE_PCT / 100.0
    sl_move = SL_MOVE_PCT / 100.0

    if side == "long":
        tp_price = entry_price * (1 + tp_move)
        sl_price = entry_price * (1 - sl_move)
    else:
        tp_price = entry_price * (1 - tp_move)
        sl_price = entry_price * (1 + sl_move)

    return tp_price, sl_price


def can_open_trade(symbol: str) -> bool:
    if not ONE_OPEN_TRADE_PER_SYMBOL:
        return True
    return fetch_open_trade_for_symbol(symbol) is None


def open_trade(signal) -> int:
    tp_price, sl_price = calc_tp_sl(signal.entry_price, signal.side)
    payload = {
        "symbol": signal.symbol,
        "side": signal.side,
        "status": "open",
        "timeframe": TIMEFRAME,
        "leverage": LEVERAGE,
        "entry_price": round(signal.entry_price, 10),
        "tp_price": round(tp_price, 10),
        "sl_price": round(sl_price, 10),
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "signal_candle_time": signal.signal_candle_time,
        "reason": signal.reason,
        "extension_pct": signal.extension_pct,
        "candle_body_pct": signal.candle_body_pct,
        "ema20": round(signal.ema20, 10),
        "ema50": round(signal.ema50, 10),
        "ema100": round(signal.ema100, 10),
        "ema200": round(signal.ema200, 10),
        "ema200_slope_pct": signal.ema200_slope_pct,
        "entry_note": "ribbon_signal",
    }
    return insert_trade(payload)


def compute_trade_excursions(trade: Dict, candle_high: float, candle_low: float) -> tuple[float, float]:
    entry = float(trade["entry_price"])
    side = trade["side"]
    current_favor = 0.0
    current_adverse = 0.0

    if side == "long":
        current_favor = pct_change(candle_high, entry)
        current_adverse = pct_change(candle_low, entry)
    else:
        current_favor = pct_change(entry, candle_low)
        current_adverse = pct_change(entry, candle_high)

    max_favor = max(float(trade.get("max_favor_pct") or 0.0), current_favor)
    min_adverse = min(float(trade.get("max_adverse_pct") or 0.0), current_adverse)
    return round(max_favor, 4), round(min_adverse, 4)


def close_trade(trade_id: int, trade: Dict, exit_price: float, result: str, close_reason: str) -> None:
    entry = float(trade["entry_price"])
    side = trade["side"]

    if side == "long":
        pnl_pct = pct_change(exit_price, entry)
    else:
        pnl_pct = pct_change(entry, exit_price)

    roi_pct = pnl_pct * LEVERAGE
    update_trade(
        trade_id,
        {
            "status": "closed",
            "exit_price": round(exit_price, 10),
            "exit_time": datetime.now(timezone.utc).isoformat(),
            "pnl_pct": round(pnl_pct, 4),
            "roi_pct": round(roi_pct, 4),
            "result": result,
            "close_reason": close_reason,
        },
    )


def maybe_update_open_trade(trade: Dict, closed_candle: Dict) -> Optional[Dict]:
    trade_id = int(trade["id"])
    side = trade["side"]
    tp_price = float(trade["tp_price"])
    sl_price = float(trade["sl_price"])
    high_price = float(closed_candle["high"])
    low_price = float(closed_candle["low"])
    close_price = float(closed_candle["close"])

    max_favor, max_adverse = compute_trade_excursions(trade, high_price, low_price)
    update_trade(trade_id, {"max_favor_pct": max_favor, "max_adverse_pct": max_adverse})

    if side == "long":
        if high_price >= tp_price:
            close_trade(trade_id, trade, tp_price, "tp", "tp_hit")
            return {"result": "tp", "exit_price": tp_price}
        if low_price <= sl_price:
            close_trade(trade_id, trade, sl_price, "sl", "sl_hit")
            return {"result": "sl", "exit_price": sl_price}
    else:
        if low_price <= tp_price:
            close_trade(trade_id, trade, tp_price, "tp", "tp_hit")
            return {"result": "tp", "exit_price": tp_price}
        if high_price >= sl_price:
            close_trade(trade_id, trade, sl_price, "sl", "sl_hit")
            return {"result": "sl", "exit_price": sl_price}

    # Optional: no force-close on candle end; keep running until TP/SL.
    return {"result": "open", "exit_price": close_price}
