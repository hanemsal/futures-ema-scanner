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


@app.route("/")
def home():
    return f"""
    <html>
    <head>
      <title>Trading Panels</title>
      <style>
        body {{
            background:#0f172a;
            color:white;
            font-family:Arial, sans-serif;
            padding:40px;
        }}
        .card {{
            background:#111827;
            padding:25px;
            border-radius:15px;
            margin:10px 0;
            border:1px solid #1f2937;
        }}
        a {{
            color:white;
            text-decoration:none;
        }}
        .btn {{
            display:inline-block;
            margin-top:10px;
            padding:10px 14px;
            border-radius:10px;
            background:#2563eb;
        }}
        .btn.secondary {{
            background:#059669;
        }}
      </style>
    </head>
    <body>
      <h1>Trading Panels</h1>

      <div class="card">
        <h2>EMA Scanner</h2>
        <a class="btn" href="{PUMP_DASHBOARD_URL}" target="_blank">Aç</a>
      </div>

      <div class="card">
        <h2>Ribbon System</h2>
        <a class="btn secondary" href="/ribbon">Aç</a>
      </div>
    </body>
    </html>
    """


@app.route("/ribbon")
def ribbon():
    init_db()

    side = request.args.get("side", "all")
    status = request.args.get("status", "all")

    stats = fetch_stats()
    trades = fetch_trades(limit=500)

    if side != "all":
        trades = [t for t in trades if t["side"] == side]

    if status != "all":
        trades = [t for t in trades if t["status"] == status]

    closed_long_count = sum(1 for t in trades if t.get("status") == "closed" and t.get("side") == "long")
    closed_short_count = sum(1 for t in trades if t.get("status") == "closed" and t.get("side") == "short")

    rows = ""
    for t in trades:
        roi_val = None if t.get("roi_pct") is None else float(t["roi_pct"])
        pnl_val = None if t.get("pnl_pct") is None else float(t["pnl_pct"])

        roi_color = "#22c55e" if roi_val is not None and roi_val > 0 else "#ef4444" if roi_val is not None and roi_val < 0 else "#e5e7eb"
        pnl_color = "#22c55e" if pnl_val is not None and pnl_val > 0 else "#ef4444" if pnl_val is not None and pnl_val < 0 else "#e5e7eb"

        side_badge = "#16a34a" if t["side"] == "long" else "#dc2626"
        status_badge = "#2563eb" if t["status"] == "open" else "#6b7280"

        rows += f"""
        <tr>
            <td>{t['id']}</td>
            <td>{t['symbol']}</td>
            <td><span class="badge" style="background:{side_badge}">{t['side'].upper()}</span></td>
            <td><span class="badge" style="background:{status_badge}">{t['status'].upper()}</span></td>
            <td>{_fmt_price(t.get('entry_price'))}</td>
            <td>{_fmt_price(t.get('tp_price'))}</td>
            <td>{_fmt_price(t.get('sl_price'))}</td>
            <td>{_fmt_price(t.get('exit_price'))}</td>
            <td style="color:{pnl_color}">{_fmt_pct(t.get('pnl_pct'))}</td>
            <td style="color:{roi_color}">{_fmt_pct(t.get('roi_pct'))}</td>
            <td>{_to_istanbul_time(t.get('entry_time'))}</td>
            <td>{_to_istanbul_time(t.get('exit_time'))}</td>
            <td>{_fmt_text(t.get('close_reason'))}</td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>{RIBBON_DASHBOARD_TITLE}</title>
        <meta http-equiv="refresh" content="30">
        <style>
            body {{
                background:#0b1220;
                color:white;
                font-family:Arial, sans-serif;
                padding:20px;
                margin:0;
            }}
            h1 {{
                margin:0 0 8px 0;
            }}
            .sub {{
                color:#9ca3af;
                margin-bottom:18px;
            }}
            .cards {{
                display:grid;
                grid-template-columns:repeat(4,1fr);
                gap:12px;
                margin-bottom:20px;
            }}
            .card {{
                background:#111827;
                padding:16px;
                border-radius:12px;
                border:1px solid #1f2937;
            }}
            .card .label {{
                font-size:12px;
                color:#9ca3af;
                margin-bottom:8px;
            }}
            .card .value {{
                font-size:28px;
                font-weight:700;
            }}
            .filters {{
                margin:14px 0 18px 0;
            }}
            .filters a {{
                color:#8ab4ff;
                margin-right:10px;
                text-decoration:none;
                font-weight:600;
            }}
            table {{
                width:100%;
                border-collapse:collapse;
                background:#0f172a;
            }}
            th, td {{
                padding:10px 8px;
                border-bottom:1px solid #1f2937;
                font-size:13px;
                text-align:left;
                white-space:nowrap;
            }}
            th {{
                background:#111827;
                position:sticky;
                top:0;
                z-index:2;
            }}
            .badge {{
                display:inline-block;
                padding:4px 8px;
                border-radius:999px;
                font-size:11px;
                font-weight:700;
                color:white;
            }}
            .top-links {{
                margin-bottom:12px;
            }}
            .top-links a {{
                color:#93c5fd;
                text-decoration:none;
            }}
            .table-wrap {{
                overflow-x:auto;
                border:1px solid #1f2937;
                border-radius:12px;
            }}
        </style>
    </head>
    <body>

    <div class="top-links">
        <a href="/">⬅ Ana Ekran</a>
    </div>

    <h1>{RIBBON_DASHBOARD_TITLE}</h1>
    <div class="sub">15m Binance Futures Ribbon Trend test paneli. Saatler İstanbul zamanıdır. Sayfa 30 saniyede bir yenilenir.</div>

    <div class="cards">
        <div class="card"><div class="label">Total</div><div class="value">{stats["total_trades"]}</div></div>
        <div class="card"><div class="label">Open</div><div class="value">{stats["open_trades"]}</div></div>
        <div class="card"><div class="label">Closed</div><div class="value">{stats["closed_trades"]}</div></div>
        <div class="card"><div class="label">Win Rate</div><div class="value">{stats["win_rate"]}%</div></div>

        <div class="card"><div class="label">ROI</div><div class="value">{stats["total_roi"]}%</div></div>
        <div class="card"><div class="label">Avg ROI</div><div class="value">{stats["avg_roi"]}%</div></div>
        <div class="card"><div class="label">Long</div><div class="value">{stats["long_count"]}</div></div>
        <div class="card"><div class="label">Short</div><div class="value">{stats["short_count"]}</div></div>

        <div class="card"><div class="label">Closed Long</div><div class="value">{closed_long_count}</div></div>
        <div class="card"><div class="label">Closed Short</div><div class="value">{closed_short_count}</div></div>
        <div class="card"><div class="label">Long Win Rate</div><div class="value">{stats["long_win_rate"]}%</div></div>
        <div class="card"><div class="label">Short Win Rate</div><div class="value">{stats["short_win_rate"]}%</div></div>
    </div>

    <div class="filters">
        <a href="/ribbon?side=all&status=all">All</a>
        <a href="/ribbon?side=long&status=all">Long</a>
        <a href="/ribbon?side=short&status=all">Short</a>
        <a href="/ribbon?side=all&status=open">Open</a>
        <a href="/ribbon?side=all&status=closed">Closed</a>
    </div>

    <div class="table-wrap">
        <table>
            <tr>
                <th>ID</th>
                <th>Coin</th>
                <th>Side</th>
                <th>Status</th>
                <th>Entry</th>
                <th>TP</th>
                <th>SL</th>
                <th>Exit</th>
                <th>PnL</th>
                <th>ROI</th>
                <th>Entry Time (İstanbul)</th>
                <th>Exit Time (İstanbul)</th>
                <th>Close Reason</th>
            </tr>
            {rows}
        </table>
    </div>

    </body>
    </html>
    """


if __name__ == "__main__":
    init_db()
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT)
