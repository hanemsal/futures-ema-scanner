from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from storage import get_dashboard_stats, init_db

app = FastAPI()

init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard():
    stats = get_dashboard_stats()

    html = f"""
    <html>
    <head>
        <title>EMA Scanner Dashboard</title>
        <style>
        body {{
            background:#0f0f0f;
            color:white;
            font-family:Arial;
            padding:40px;
        }}
        table {{
            border-collapse: collapse;
            width:100%;
            margin-bottom:24px;
        }}
        th, td {{
            border:1px solid #444;
            padding:8px;
            text-align:left;
        }}
        th {{
            background:#222;
        }}
        </style>
    </head>

    <body>

    <h1>🚀 EMA Scanner Dashboard</h1>

    <h2>Genel İstatistik</h2>

    <table>
        <tr><th>Total Signals</th><td>{stats["total_signals"]}</td></tr>
        <tr><th>Closed Trades</th><td>{stats["total_closed"]}</td></tr>
        <tr><th>Open Trades</th><td>{stats["total_open"]}</td></tr>
        <tr><th>Win Rate</th><td>{stats["win_rate"]:.2f}%</td></tr>
        <tr><th>Total PnL</th><td>{stats["total_pnl"]:.2f}%</td></tr>
        <tr><th>Average PnL</th><td>{stats["avg_pnl"]:.2f}%</td></tr>
        <tr><th>Average Duration</th><td>{stats["avg_duration"]:.2f} min</td></tr>
        <tr><th>Average Max Profit</th><td>{stats["avg_mfe"]:.2f}%</td></tr>
        <tr><th>Average Max Drawdown</th><td>{stats["avg_mae"]:.2f}%</td></tr>
        <tr><th>Average RR Proxy</th><td>{stats["avg_rr"]:.2f}</td></tr>
    </table>

    <h2>Long / Short</h2>

    <table>
        <tr>
        <th>Long Trades</th>
        <th>Short Trades</th>
        <th>Long PnL</th>
        <th>Short PnL</th>
        </tr>

        <tr>
        <td>{stats["long_total"]}</td>
        <td>{stats["short_total"]}</td>
        <td>{stats["long_pnl"]:.2f}%</td>
        <td>{stats["short_pnl"]:.2f}%</td>
        </tr>
    </table>

    <h2>Top Coin Performansı</h2>

    <table>
    <tr>
        <th>Coin</th>
        <th>Trades</th>
        <th>Avg Profit</th>
        <th>Total PnL</th>
    </tr>
    """

    for c in stats["coin_ranking"]:
        html += f"""
        <tr>
        <td>{c["symbol"]}</td>
        <td>{c["trades"]}</td>
        <td>{c["avg_profit"]:.2f}%</td>
        <td>{c["total_pnl"]:.2f}%</td>
        </tr>
        """

    html += "</table>"

    html += """
    <h2>Son Trades</h2>

    <table>
    <tr>
    <th>ID</th>
    <th>Symbol</th>
    <th>Side</th>
    <th>Entry</th>
    <th>Exit</th>
    <th>PnL</th>
    <th>Duration</th>
    <th>Max Profit</th>
    <th>Max Drawdown</th>
    <th>RR Proxy</th>
    </tr>
    """

    for t in stats["recent_trades"]:
        html += f"""
        <tr>
        <td>{t.id}</td>
        <td>{t.symbol}</td>
        <td>{t.side}</td>
        <td>{t.entry_price}</td>
        <td>{t.exit_price}</td>
        <td>{t.pnl_pct}</td>
        <td>{t.duration_minutes}</td>
        <td>{t.max_profit_pct}</td>
        <td>{t.max_drawdown_pct}</td>
        <td>{t.rr_ratio}</td>
        </tr>
        """

    html += "</table></body></html>"

    return html
