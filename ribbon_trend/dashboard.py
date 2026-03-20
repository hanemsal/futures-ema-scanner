from __future__ import annotations

from flask import Flask, request

from config import DASHBOARD_HOST, DASHBOARD_PORT, PUMP_DASHBOARD_URL, RIBBON_DASHBOARD_TITLE
from db import fetch_stats, fetch_trades, init_db

app = Flask(__name__)


def _render_home() -> str:
    return f"""
    <html>
    <head>
      <title>Scanner Panels</title>
      <style>
        body {{ font-family: Arial, sans-serif; background:#0f172a; color:#e2e8f0; padding:40px; }}
        .wrap {{ max-width:900px; margin:0 auto; }}
        .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:30px; }}
        .card {{ background:#111827; border:1px solid #1f2937; border-radius:16px; padding:24px; }}
        .btn {{ display:inline-block; padding:12px 18px; border-radius:12px; background:#2563eb; color:#fff; text-decoration:none; font-weight:700; }}
        .btn.secondary {{ background:#059669; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <h1>Trading Scanner Panels</h1>
        <p>İki sistemi ayrı tutmak için giriş ekranı.</p>
        <div class="grid">
          <div class="card">
            <h2>EMA 8/18/34 Panel</h2>
            <p>Mevcut Pump Hunter paneline gider.</p>
            <a class="btn" href="{PUMP_DASHBOARD_URL}" target="_blank">Pump Hunter Aç</a>
          </div>
          <div class="card">
            <h2>Ribbon 20/50/100/200</h2>
            <p>Yeni Ribbon Trend paneline gider.</p>
            <a class="btn secondary" href="/ribbon">Ribbon Panel Aç</a>
          </div>
        </div>
      </div>
    </body>
    </html>
    """


@app.route("/")
def home():
    return _render_home()


@app.route("/ribbon")
def ribbon():
    init_db()
    side_filter = request.args.get("side", "all")
    status_filter = request.args.get("status", "all")

    stats = fetch_stats()
    trades = fetch_trades(limit=500)

    if side_filter != "all":
        trades = [t for t in trades if t["side"] == side_filter]
    if status_filter != "all":
        trades = [t for t in trades if t["status"] == status_filter]

    rows = []
    for t in trades:
        roi = "-" if t.get("roi_pct") is None else f"{float(t['roi_pct']):.2f}%"
        pnl = "-" if t.get("pnl_pct") is None else f"{float(t['pnl_pct']):.2f}%"
        rows.append(
            f"""
            <tr>
              <td>{t['id']}</td>
              <td>{t['symbol']}</td>
              <td>{t['side'].upper()}</td>
              <td>{t['status'].upper()}</td>
              <td>{float(t['entry_price']):.8f}</td>
              <td>{float(t['tp_price']):.8f}</td>
              <td>{float(t['sl_price']):.8f}</td>
              <td>{'-' if t.get('exit_price') is None else f"{float(t['exit_price']):.8f}"}</td>
              <td>{pnl}</td>
              <td>{roi}</td>
              <td>{t['entry_time']}</td>
              <td>{'-' if t.get('exit_time') is None else t['exit_time']}</td>
            </tr>
            """
        )

    cards = [
        ("Total Trades", stats["total_trades"]),
        ("Open Trades", stats["open_trades"]),
        ("Closed Trades", stats["closed_trades"]),
        ("Winners", stats["winners"]),
        ("Losers", stats["losers"]),
        ("Win Rate", f"{stats['win_rate']}%"),
        ("Total ROI", f"{stats['total_roi']}%"),
        ("Avg ROI", f"{stats['avg_roi']}%"),
        ("Long Count", stats["long_count"]),
        ("Short Count", stats["short_count"]),
        ("Long Win Rate", f"{stats['long_win_rate']}%"),
        ("Short Win Rate", f"{stats['short_win_rate']}%"),
    ]

    cards_html = "".join(
        [f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div></div>' for label, value in cards]
    )

    return f"""
    <html>
    <head>
      <title>{RIBBON_DASHBOARD_TITLE}</title>
      <meta http-equiv="refresh" content="30">
      <style>
        body {{ font-family: Arial, sans-serif; background:#0b1220; color:#e5e7eb; margin:0; padding:24px; }}
        h1 {{ margin:0 0 8px 0; }}
        .muted {{ color:#9ca3af; }}
        .cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:18px 0 20px; }}
        .card {{ background:#111827; border:1px solid #1f2937; border-radius:14px; padding:16px; }}
        .label {{ color:#9ca3af; font-size:12px; margin-bottom:8px; }}
        .value {{ font-size:24px; font-weight:700; }}
        .toolbar {{ margin:18px 0; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
        a.filter {{ color:#fff; text-decoration:none; background:#1f2937; padding:10px 14px; border-radius:10px; }}
        table {{ width:100%; border-collapse:collapse; background:#111827; border-radius:14px; overflow:hidden; }}
        th, td {{ border-bottom:1px solid #1f2937; padding:10px 8px; text-align:left; font-size:13px; }}
        th {{ background:#0f172a; position:sticky; top:0; }}
        .header-links a {{ color:#93c5fd; text-decoration:none; margin-right:14px; }}
      </style>
    </head>
    <body>
      <div class="header-links">
        <a href="/">⬅ Ana Ekran</a>
      </div>
      <h1>{RIBBON_DASHBOARD_TITLE}</h1>
      <div class="muted">15m Binance Futures Ribbon Trend test paneli. Sayfa 30 saniyede bir yenilenir.</div>

      <div class="cards">{cards_html}</div>

      <div class="toolbar">
        <a class="filter" href="/ribbon?side=all&status=all">Tümü</a>
        <a class="filter" href="/ribbon?side=long&status=all">Sadece Long</a>
        <a class="filter" href="/ribbon?side=short&status=all">Sadece Short</a>
        <a class="filter" href="/ribbon?side=all&status=open">Open</a>
        <a class="filter" href="/ribbon?side=all&status=closed">Closed</a>
      </div>

      <table>
        <thead>
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
            <th>Entry Time</th>
            <th>Exit Time</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </body>
    </html>
    """


if __name__ == "__main__":
    init_db()
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)
