from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None  # sqlite fallback


def _get_sqlite_path() -> str:
    try:
        from config import DB_PATH
        return DB_PATH
    except Exception:
        return "ribbon_signals.db"


def _get_db_url() -> str:
    return (
        os.getenv("RIBBON_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    )


DB_URL = _get_db_url()
USE_POSTGRES = DB_URL.startswith("postgres://") or DB_URL.startswith("postgresql://")


def _sqlite_dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {fields[idx]: row[idx] for idx in range(len(fields))}


@contextmanager
def get_conn():
    if USE_POSTGRES:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is required for Postgres but is not installed.")
        conn = psycopg2.connect(DB_URL)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(_get_sqlite_path())
        conn.row_factory = _sqlite_dict_factory
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _fetchone(cur):
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return row


def _fetchall(cur):
    rows = cur.fetchall()
    out = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
        else:
            try:
                out.append(dict(row))
            except Exception:
                out.append(row)
    return out


def _sqlite_has_column(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    names = []
    for row in rows:
        if isinstance(row, dict):
            names.append(row["name"])
        else:
            names.append(row[1])
    return column_name in names


def init_db() -> None:
    if USE_POSTGRES:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id BIGSERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    leverage DOUBLE PRECISION NOT NULL,
                    entry_price DOUBLE PRECISION NOT NULL,
                    tp_price DOUBLE PRECISION NOT NULL,
                    sl_price DOUBLE PRECISION NOT NULL,
                    exit_price DOUBLE PRECISION,
                    pnl_pct DOUBLE PRECISION,
                    roi_pct DOUBLE PRECISION,
                    result TEXT,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    signal_candle_time TEXT NOT NULL,
                    reason TEXT,
                    extension_pct DOUBLE PRECISION,
                    candle_body_pct DOUBLE PRECISION,
                    ema20 DOUBLE PRECISION,
                    ema50 DOUBLE PRECISION,
                    ema100 DOUBLE PRECISION,
                    ema200 DOUBLE PRECISION,
                    ema200_slope_pct DOUBLE PRECISION,
                    entry_note TEXT,
                    max_favor_pct DOUBLE PRECISION DEFAULT 0,
                    max_adverse_pct DOUBLE PRECISION DEFAULT 0,
                    close_reason TEXT,
                    recovery_mode BOOLEAN DEFAULT FALSE,
                    current_price DOUBLE PRECISION,
                    floating_pnl_pct DOUBLE PRECISION DEFAULT 0,
                    floating_roi_pct DOUBLE PRECISION DEFAULT 0,
                    last_price_time TEXT
                )
                """
            )
            cur.execute(
                "ALTER TABLE trades ADD COLUMN IF NOT EXISTS recovery_mode BOOLEAN DEFAULT FALSE"
            )
            cur.execute(
                "ALTER TABLE trades ADD COLUMN IF NOT EXISTS current_price DOUBLE PRECISION"
            )
            cur.execute(
                "ALTER TABLE trades ADD COLUMN IF NOT EXISTS floating_pnl_pct DOUBLE PRECISION DEFAULT 0"
            )
            cur.execute(
                "ALTER TABLE trades ADD COLUMN IF NOT EXISTS floating_roi_pct DOUBLE PRECISION DEFAULT 0"
            )
            cur.execute(
                "ALTER TABLE trades ADD COLUMN IF NOT EXISTS last_price_time TEXT"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_symbol_status ON trades(symbol, status)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)"
            )
    else:
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
                    close_reason TEXT,
                    recovery_mode INTEGER DEFAULT 0,
                    current_price REAL,
                    floating_pnl_pct REAL DEFAULT 0,
                    floating_roi_pct REAL DEFAULT 0,
                    last_price_time TEXT
                )
                """
            )
            if not _sqlite_has_column(conn, "trades", "recovery_mode"):
                conn.execute(
                    "ALTER TABLE trades ADD COLUMN recovery_mode INTEGER DEFAULT 0"
                )
            if not _sqlite_has_column(conn, "trades", "current_price"):
                conn.execute(
                    "ALTER TABLE trades ADD COLUMN current_price REAL"
                )
            if not _sqlite_has_column(conn, "trades", "floating_pnl_pct"):
                conn.execute(
                    "ALTER TABLE trades ADD COLUMN floating_pnl_pct REAL DEFAULT 0"
                )
            if not _sqlite_has_column(conn, "trades", "floating_roi_pct"):
                conn.execute(
                    "ALTER TABLE trades ADD COLUMN floating_roi_pct REAL DEFAULT 0"
                )
            if not _sqlite_has_column(conn, "trades", "last_price_time"):
                conn.execute(
                    "ALTER TABLE trades ADD COLUMN last_price_time TEXT"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_symbol_status ON trades(symbol, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)"
            )


def insert_trade(payload: Dict[str, Any]) -> int:
    keys = list(payload.keys())
    values = list(payload.values())

    if USE_POSTGRES:
        placeholders = ", ".join(["%s"] * len(keys))
        columns = ", ".join(keys)
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                f"INSERT INTO trades ({columns}) VALUES ({placeholders}) RETURNING id",
                values,
            )
            row = _fetchone(cur)
            return int(row["id"])
    else:
        placeholders = ", ".join(["?"] * len(keys))
        columns = ", ".join(keys)
        with get_conn() as conn:
            cur = conn.execute(
                f"INSERT INTO trades ({columns}) VALUES ({placeholders})",
                values,
            )
            return int(cur.lastrowid)


def update_trade(trade_id: int, payload: Dict[str, Any]) -> None:
    if not payload:
        return

    keys = list(payload.keys())
    values = list(payload.values())

    if USE_POSTGRES:
        assignments = ", ".join([f"{key} = %s" for key in keys])
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                f"UPDATE trades SET {assignments} WHERE id = %s",
                values + [trade_id],
            )
    else:
        assignments = ", ".join([f"{key} = ?" for key in keys])
        with get_conn() as conn:
            conn.execute(
                f"UPDATE trades SET {assignments} WHERE id = ?",
                values + [trade_id],
            )


def fetch_open_trades() -> List[Dict[str, Any]]:
    query = "SELECT * FROM trades WHERE status = 'open' ORDER BY entry_time ASC"
    if USE_POSTGRES:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(query)
            return _fetchall(cur)
    else:
        with get_conn() as conn:
            return list(conn.execute(query).fetchall())


def fetch_open_trade_for_symbol_side(symbol: str, side: str) -> Optional[Dict[str, Any]]:
    if USE_POSTGRES:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM trades WHERE symbol = %s AND side = %s AND status = 'open' ORDER BY id DESC LIMIT 1",
                (symbol, side),
            )
            return _fetchone(cur)
    else:
        with get_conn() as conn:
            return conn.execute(
                "SELECT * FROM trades WHERE symbol = ? AND side = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                (symbol, side),
            ).fetchone()


def fetch_open_trade_for_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    if USE_POSTGRES:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM trades WHERE symbol = %s AND status = 'open' ORDER BY id DESC LIMIT 1",
                (symbol,),
            )
            return _fetchone(cur)
    else:
        with get_conn() as conn:
            return conn.execute(
                "SELECT * FROM trades WHERE symbol = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                (symbol,),
            ).fetchone()


def fetch_trades(limit: int = 500) -> List[Dict[str, Any]]:
    if USE_POSTGRES:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            return _fetchall(cur)
    else:
        with get_conn() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM trades ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )


def fetch_stats() -> Dict[str, Any]:
    if USE_POSTGRES:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("SELECT COUNT(*) AS n FROM trades")
            total = _fetchone(cur)["n"]

            cur.execute("SELECT COUNT(*) AS n FROM trades WHERE status='open'")
            open_n = _fetchone(cur)["n"]

            cur.execute("SELECT COUNT(*) AS n FROM trades WHERE status='closed'")
            closed_n = _fetchone(cur)["n"]

            cur.execute("SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND COALESCE(roi_pct, 0) > 0")
            winners = _fetchone(cur)["n"]

            cur.execute("SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND COALESCE(roi_pct, 0) <= 0")
            losers = _fetchone(cur)["n"]

            cur.execute("SELECT COUNT(*) AS n FROM trades WHERE side='long'")
            longs = _fetchone(cur)["n"]

            cur.execute("SELECT COUNT(*) AS n FROM trades WHERE side='short'")
            shorts = _fetchone(cur)["n"]

            cur.execute("SELECT COALESCE(SUM(roi_pct), 0) AS v FROM trades WHERE status='closed'")
            total_roi = _fetchone(cur)["v"]

            cur.execute("SELECT COALESCE(AVG(roi_pct), 0) AS v FROM trades WHERE status='closed'")
            avg_roi = _fetchone(cur)["v"]

            win_rate = (winners / closed_n * 100.0) if closed_n else 0.0

            cur.execute("SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND side='long'")
            long_closed = _fetchone(cur)["n"]

            cur.execute("SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND side='short'")
            short_closed = _fetchone(cur)["n"]

            cur.execute("SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND side='long' AND COALESCE(roi_pct, 0) > 0")
            long_win = _fetchone(cur)["n"]

            cur.execute("SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND side='short' AND COALESCE(roi_pct, 0) > 0")
            short_win = _fetchone(cur)["n"]

    else:
        with get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"]
            open_n = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE status='open'").fetchone()["n"]
            closed_n = conn.execute("SELECT COUNT(*) AS n FROM trades WHERE status='closed'").fetchone()["n"]
            winners = conn.execute(
                "SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND COALESCE(roi_pct, 0) > 0"
            ).fetchone()["n"]
            losers = conn.execute(
                "SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND COALESCE(roi_pct, 0) <= 0"
            ).fetchone()["n"]
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
                "SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND side='long' AND COALESCE(roi_pct, 0) > 0"
            ).fetchone()["n"]
            short_win = conn.execute(
                "SELECT COUNT(*) AS n FROM trades WHERE status='closed' AND side='short' AND COALESCE(roi_pct, 0) > 0"
            ).fetchone()["n"]

    return {
        "total_trades": int(total or 0),
        "open_trades": int(open_n or 0),
        "closed_trades": int(closed_n or 0),
        "winners": int(winners or 0),
        "losers": int(losers or 0),
        "win_rate": round(float(win_rate or 0), 2),
        "total_roi": round(float(total_roi or 0), 2),
        "avg_roi": round(float(avg_roi or 0), 2),
        "long_count": int(longs or 0),
        "short_count": int(shorts or 0),
        "long_win_rate": round((float(long_win) / float(long_closed) * 100.0), 2) if long_closed else 0.0,
        "short_win_rate": round((float(short_win) / float(short_closed) * 100.0), 2) if short_closed else 0.0,
    }
