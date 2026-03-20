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


@app.route("/")
def home():
    return f"""
    <html>
    <head>
      <title>Trading Panels</title>
      <style>
        body {{ background:#0f172a; color:white; font-family:Arial; padding:40px }}
        .card {{ background:#111827; padding:25px; border-radius:15px; margin:10px }}
        a {{ color:white; text-decoration:none; }}
      </style>
    </head>
    <body>
      <h1>Trading Panels</h1>

      <div class="card">
        <h2>EMA Scanner</h2>
        <a href="{PUMP_DASHBOARD_URL}" target="_blank">Aç</a>
      </div>

      <div class="card">
        <h2>Ribbon System</h2>
        <a href="/ribbon">Aç</a>
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

    def fmt_pct(v):
        return "-" if v is None else f"{float(v):.2f}%"

    def fmt_price(v):
        return "-" if v is None else f"{float(v):.6f}"

    rows = ""
    for t in trades:
        rows += f"""
        <tr>
            <td>{t['id']}</td>
            <td>{t['symbol']}</td>
            <td>{t['side']}</td>
            <td>{t['status']}</td>
            <td>{fmt_price(t.get('entry_price'))}</td>
            <td>{fmt_price(t.get('tp_price'))}</td>
            <td>{fmt_price(t.get('sl_price'))}</td>
            <td>{fmt_price(t.get('exit_price'))}</td>
            <td>{fmt_pct(t.get('pnl_pct'))}</td>
            <td>{fmt_pct(t.get('roi_pct'))}</td>
            <td>{_to_istanbul_time(t.get('entry_time'))}</td>
            <td>{_to_istanbul_time(t.get('exit_time'))}</td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>{RIBBON_DASHBOARD_TITLE}</title>
        <meta http-equiv="refresh" content="15">
        <style>
            body {{
                background:#0b1220;
                color:white;
                font-family:Arial;
                padding:20px;
            }}
            table {{
                width:100%;
                border-collapse:collapse;
            }}
            th, td {{
                padding:8px;
                border-bottom:1px solid #333;
                font-size:13px;
            }}
            th {{
                background:#111;
                position:sticky;
                top:0;
            }}
            .cards {{
                display:grid;
                grid-template-columns:repeat(4,1fr);
                gap:10px;
            }}
            .card {{
                background:#111827;
                padding:15px;
                border-radius:10px;
            }}
            .filters a {{
                color:#8ab4ff;
                margin-right:10px;
                text-decoration:none;
            }}
        </style>
    </head>

    <body>

    <h1>{RIBBON_DASHBOARD_TITLE}</h1>

    <div class="cards">
        <div class="card">Total: {stats["total_trades"]}</div>
        <div class="card">Open: {stats["open_trades"]}</div>
        <div class="card">Closed: {stats["closed_trades"]}</div>
        <div class="card">Win Rate: {stats["win_rate"]}%</div>
        <div class="card">ROI: {stats["total_roi"]}%</div>
        <div class="card">Avg ROI: {stats["avg_roi"]}%</div>
        <div class="card">Long: {stats["long_count"]}</div>
        <div class="card">Short: {stats["short_count"]}</div>
        <div class="card">Closed Long Win Rate: {stats["long_win_rate"]}%</div>
        <div class="card">Closed Short Win Rate: {stats["short_win_rate"]}%</div>
    </div>

    <br>

    <div class="filters">
        <a href="/ribbon?side=all&status=all">All</a>
        <a href="/ribbon?side=long&status=all">Long</a>
        <a href="/ribbon?side=short&status=all">Short</a>
        <a href="/ribbon?side=all&status=open">Open</a>
        <a href="/ribbon?side=all&status=closed">Closed</a>
    </div>

    <br>

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
        </tr>

        {rows}

    </table>

    </body>
    </html>
    """


if __name__ == "__main__":
    init_db()
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT)
