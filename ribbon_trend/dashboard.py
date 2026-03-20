from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, request

from config import DASHBOARD_HOST, DASHBOARD_PORT, PUMP_DASHBOARD_URL, RIBBON_DASHBOARD_TITLE
from db import fetch_stats, fetch_trades, init_db

app = Flask(__name__)

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")


def _to_istanbul_time(value) -> str:
    if not value:
        return "-"

    try:
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            if text.endswith("Z"):
                text = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        dt_local = dt.astimezone(ISTANBUL_TZ)
        return dt_local.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return str(value)


def _fmt_pct(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _fmt_price(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):.6f}"


def _fmt_text(value) -> str:
    if value is None or str(value).strip() == "":
        return "-"
    return str(value)


def _safe_float(value, default=0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


# -------------------------
# NEW METRIC
# -------------------------

def _calc_avg_trade_time(closed_trades: list[dict]) -> float:

    durations = []

    for t in closed_trades:

        entry = t.get("entry_time")
        exit = t.get("exit_time")

        if not entry or not exit:
            continue

        try:

            if entry.endswith("Z"):
                entry = entry.replace("Z", "+00:00")

            if exit.endswith("Z"):
                exit = exit.replace("Z", "+00:00")

            entry_dt = datetime.fromisoformat(entry)
            exit_dt = datetime.fromisoformat(exit)

            duration = (exit_dt - entry_dt).total_seconds()

            durations.append(duration)

        except Exception:
            continue

    if not durations:
        return 0.0

    avg_seconds = sum(durations) / len(durations)

    return round(avg_seconds / 60, 2)


# -------------------------
# EQUITY CURVE
# -------------------------

def _build_equity_curve_svg(closed_trades: list[dict], width: int = 1100, height: int = 260) -> str:

    if not closed_trades:
        return ""

    equity_values = []
    running = 0.0

    for t in closed_trades:
        running += _safe_float(t.get("roi_pct"))
        equity_values.append(running)

    min_v = min(equity_values)
    max_v = max(equity_values)

    if min_v == max_v:
        min_v -= 1
        max_v += 1

    left_pad = 50
    right_pad = 20
    top_pad = 20
    bottom_pad = 35

    plot_w = width - left_pad - right_pad
    plot_h = height - top_pad - bottom_pad

    def x_of(i):

        if len(equity_values) == 1:
            return left_pad + plot_w / 2

        return left_pad + (i / (len(equity_values) - 1)) * plot_w

    def y_of(v):

        ratio = (v - min_v) / (max_v - min_v)

        return top_pad + (1 - ratio) * plot_h

    points = " ".join(
        f"{x_of(i):.2f},{y_of(v):.2f}"
        for i, v in enumerate(equity_values)
    )

    last_equity = equity_values[-1]
    last_x = x_of(len(equity_values) - 1)
    last_y = y_of(last_equity)

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}">
        <polyline
            fill="none"
            stroke="#22c55e"
            stroke-width="3"
            points="{points}"
        />
        <circle cx="{last_x}" cy="{last_y}" r="4" fill="#22c55e" />
    </svg>
    """


# -------------------------
# STREAK
# -------------------------

def _calc_streaks(closed_trades):

    max_win = 0
    max_loss = 0

    cur_win = 0
    cur_loss = 0

    for t in closed_trades:

        roi = _safe_float(t.get("roi_pct"))

        if roi > 0:

            cur_win += 1
            cur_loss = 0

        else:

            cur_loss += 1
            cur_win = 0

        if cur_win > max_win:
            max_win = cur_win

        if cur_loss > max_loss:
            max_loss = cur_loss

    return max_win, max_loss


@app.route("/ribbon")
def ribbon():

    init_db()

    stats = fetch_stats()
    trades = fetch_trades(limit=500)

    closed_trades = [
        t for t in reversed(trades)
        if t.get("status") == "closed"
    ]

    max_win_streak, max_losing_streak = _calc_streaks(closed_trades)

    avg_trade_time = _calc_avg_trade_time(closed_trades)

    equity_curve_svg = _build_equity_curve_svg(closed_trades)

    rows = ""

    for t in trades:

        rows += f"""
        <tr>
            <td>{t['symbol']}</td>
            <td>{t['side']}</td>
            <td>{_fmt_pct(t.get('roi_pct'))}</td>
            <td>{_to_istanbul_time(t.get('entry_time'))}</td>
            <td>{_to_istanbul_time(t.get('exit_time'))}</td>
        </tr>
        """

    return f"""

<html>

<body style="background:#0b1220;color:white;font-family:Arial;padding:20px">

<h1>{RIBBON_DASHBOARD_TITLE}</h1>

<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px">

<div>Trades<br><b>{stats["total_trades"]}</b></div>
<div>Closed<br><b>{stats["closed_trades"]}</b></div>
<div>Win Rate<br><b>{stats["win_rate"]}%</b></div>
<div>Avg ROI<br><b>{stats["avg_roi"]}%</b></div>
<div>Avg Trade Time<br><b>{avg_trade_time} min</b></div>

<div>Max Win Streak<br><b>{max_win_streak}</b></div>
<div>Max Loss Streak<br><b>{max_losing_streak}</b></div>

</div>

<br><br>

{equity_curve_svg}

<table border="1" cellpadding="6">

<tr>
<th>Coin</th>
<th>Side</th>
<th>ROI</th>
<th>Entry</th>
<th>Exit</th>
</tr>

{rows}

</table>

</body>

</html>

"""


if __name__ == "__main__":
    init_db()
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT)
