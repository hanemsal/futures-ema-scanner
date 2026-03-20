from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional

from config import DB_PATH


def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {fields[idx]: row[idx] for idx in range(len(fields))}


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                status TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                leverage REAL NOT NULL,
                entry_price REAL NOT NULL,
                tp_price REAL NOT NULL,
                sl_price REAL NOT NULL,
                exit_price REAL,
                pnl_pct REAL,
                roi_pct REAL,
                result TEXT,
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                signal_candle_time TEXT NOT NULL,
                reason TEXT,
                extension_pct REAL,
                candle_body_pct REAL,
                ema20 REAL,
                ema50 REAL,
                ema100 REAL,
                ema200 REAL,
                ema200_slope_pct REAL,
                entry_note TEXT,
                max_favor_pct REAL DEFAULT 0,
                max_adverse_pct REAL DEFAULT 0,
                close_reason TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trades_symbol_status ON trades(symbol, status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)"
        )


def insert_trade(payload: Dict[str, Any]) -> int:
    keys = ", ".join(payload.keys())
    placeholders = ", ".join(["?"] * len(payload))
    values = list(payload.values())
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO trades ({keys}) VALUES ({placeholders})",
            values,
        )
        return int(cur.lastrowid)


def update_trade(trade_id: int, payload: Dict[str, Any]) -> None:
    if not payload:
        return
    assignments = ", ".join([f"{key} = ?" for key in payload.keys()])
    values = list(payload.values()) + [trade_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE trades SET {assignments} WHERE id = ?", values)


def fetch_open_trades() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        return list(
            conn.execute(
                "SELECT * FROM trades WHERE status = 'open' ORDER BY entry_time ASC"
            ).fetchall()
        )


def fetch_open_trade_for_symbol_side(symbol: str, side: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM trades WHERE symbol = ? AND side = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (symbol, side),
        ).fetchone()


def fetch_open_trade_for_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM trades WHERE symbol = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (symbol,),
        ).fetchone()


def fetch_trades(limit: int = 500) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        return list(
            conn.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        )


def fetch_stats() -> Dict[str, Any]:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"]
        open_n = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE status='open'").fetchone()["n"]
        closed_n = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE status='closed'").fetchone()["n"]
        winners = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE result='tp'").fetchone()["n"]
        losers = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE result='sl'").fetchone()["n"]
        longs = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE side='long'").fetchone()["n"]
        shorts = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE side='short'").fetchone()["n"]
        total_roi = conn.execute(
            "SELECT COALESCE(SUM(roi_pct), 0) AS v FROM trades WHERE status='closed'"
        ).fetchone()["v"]
        avg_roi = conn.execute(
            "SELECT COALESCE(AVG(roi_pct), 0) AS v FROM trades WHERE status='closed'"
        ).fetchone()["v"]
        win_rate = (winners / closed_n * 100.0) if closed_n else 0.0

        long_closed = conn.execute(
            "SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND side='long'"
        ).fetchone()["n"]
        short_closed = conn.execute(
            "SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND side='short'"
        ).fetchone()["n"]
        long_win = conn.execute(
            "SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND side='long' AND result='tp'"
        ).fetchone()["n"]
        short_win = conn.execute(
            "SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND side='short' AND result='tp'"
        ).fetchone()["n"]

        return {
            "total_trades": total,
            "open_trades": open_n,
            "closed_trades": closed_n,
            "winners": winners,
            "losers": losers,
            "win_rate": round(win_rate, 2),
            "total_roi": round(float(total_roi or 0), 2),
            "avg_roi": round(float(avg_roi or 0), 2),
            "long_count": longs,
            "short_count": shorts,
            "long_win_rate": round((long_win / long_closed * 100.0), 2) if long_closed else 0.0,
            "short_win_rate": round((short_win / short_closed * 100.0), 2) if short_closed else 0.0,
        }
