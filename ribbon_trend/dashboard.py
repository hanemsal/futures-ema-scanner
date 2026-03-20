from __future__ import annotations

from flask import Flask, request
from config import DASHBOARD_HOST, DASHBOARD_PORT, PUMP_DASHBOARD_URL, RIBBON_DASHBOARD_TITLE
from db import fetch_stats, fetch_trades, init_db

app = Flask(__name__)


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

    def fmt(v):
        return "-" if v is None else f"{float(v):.2f}%"

    rows = ""
    for t in trades:
        rows += f"""
        <tr>
            <td>{t['id']}</td>
            <td>{t['symbol']}</td>
            <td>{t['side']}</td>
            <td>{t['status']}</td>
            <td>{t['entry_price']:.6f}</td>
            <td>{t['tp_price']:.6f}</td>
            <td>{t['sl_price']:.6f}</td>
            <td>{'-' if not t['exit_price'] else f"{t['exit_price']:.6f}"}</td>
            <td>{fmt(t.get('pnl_pct'))}</td>
            <td>{fmt(t.get('roi_pct'))}</td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <title>{RIBBON_DASHBOARD_TITLE}</title>
        <meta http-equiv="refresh" content="15">
        <style>
            body {{ background:#0b1220; color:white; font-family:Arial; padding:20px }}
            table {{ width:100%; border-collapse:collapse }}
            th, td {{ padding:8px; border-bottom:1px solid #333 }}
            th {{ background:#111 }}
            .cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px }}
            .card {{ background:#111827; padding:15px; border-radius:10px }}
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
    </div>

    <br>

    <a href="/ribbon?side=all">All</a> |
    <a href="/ribbon?side=long">Long</a> |
    <a href="/ribbon?side=short">Short</a> |
    <a href="/ribbon?status=open">Open</a> |
    <a href="/ribbon?status=closed">Closed</a>

    <br><br>

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
        </tr>

        {rows}

    </table>

    </body>
    </html>
    """


if __name__ == "__main__":
    init_db()
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT)
