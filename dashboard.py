from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from storage import get_dashboard_stats, init_db, format_duration_from_minutes

app = FastAPI()

init_db()


def fmt_num(value, digits=4):
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def fmt_pct(value, digits=2):
    if value is None:
        return "-"
    return f"{value:.{digits}f}%"


def fmt_dt(value):
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M")


def fmt_big(value):
    if value is None:
        return "-"
    value = float(value)
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.2f}"


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
            padding:24px;
        }}
        table {{
            border-collapse: collapse;
            width:100%;
            margin-bottom:24px;
            font-size:13px;
        }}
        th, td {{
            border:1px solid #444;
            padding:8px;
            text-align:left;
            vertical-align:top;
            white-space:nowrap;
        }}
        th {{
            background:#222;
        }}
        tr:nth-child(even) {{
            background:#151515;
        }}
        .wrap {{
            overflow-x:auto;
        }}
        </style>
    </head>
    <body>

    <h1>🚀 EMA Scanner Dashboard</h1>

    <h2>Genel İstatistik</h2>
    <div class="wrap">
    <table>
        <tr><th>Total Signals</th><td>{stats['total_signals']}</td></tr>
        <tr><th>Closed Trades</th><td>{stats['total_closed']}</td></tr>
        <tr><th>Open Trades</th><td>{stats['total_open']}</td></tr>
        <tr><th>Win Rate</th><td>{stats['win_rate']:.2f}%</td></tr>
        <tr><th>Total PnL</th><td>{stats['total_pnl']:.2f}%</td></tr>
        <tr><th>Average PnL</th><td>{stats['avg_pnl']:.2f}%</td></tr>
        <tr><th>Average Duration</th><td>{stats['avg_duration']:.2f} min</td></tr>
        <tr><th>Average Max Profit</th><td>{stats['avg_mfe']:.2f}%</td></tr>
        <tr><th>Average Max Drawdown</th><td>{stats['avg_mae']:.2f}%</td></tr>
        <tr><th>Average RR Proxy</th><td>{stats['avg_rr']:.2f}</td></tr>
    </table>
    </div>

    <h2>Long / Short</h2>
    <div class="wrap">
    <table>
        <tr>
            <th>Long Trades</th>
            <th>Short Trades</th>
            <th>Long PnL</th>
            <th>Short PnL</th>
        </tr>
        <tr>
            <td>{stats['long_total']}</td>
            <td>{stats['short_total']}</td>
            <td>{stats['long_pnl']:.2f}%</td>
            <td>{stats['short_pnl']:.2f}%</td>
        </tr>
    </table>
    </div>

    <h2>Mode Performansı</h2>
    <div class="wrap">
    <table>
        <tr>
            <th>Pump Trades</th>
            <th>Dip Trades</th>
            <th>Pump Win Rate</th>
            <th>Dip Win Rate</th>
            <th>Pump PnL</th>
            <th>Dip PnL</th>
        </tr>
        <tr>
            <td>{stats['pump_total']}</td>
            <td>{stats['dip_total']}</td>
            <td>{stats['pump_win_rate']:.2f}%</td>
            <td>{stats['dip_win_rate']:.2f}%</td>
            <td>{stats['pump_pnl']:.2f}%</td>
            <td>{stats['dip_pnl']:.2f}%</td>
        </tr>
    </table>
    </div>

    <h2>Top Coin Performansı</h2>
    <div class="wrap">
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
            <td>{c['symbol']}</td>
            <td>{c['trades']}</td>
            <td>{c['avg_profit']:.2f}%</td>
            <td>{c['total_pnl']:.2f}%</td>
        </tr>
        """

    html += """
    </table>
    </div>

    <h2>Son Trades</h2>
    <div class="wrap">
    <table>
    <tr>
        <th>ID</th>
        <th>Symbol</th>
        <th>Side</th>
        <th>Mode</th>
        <th>Cross Time</th>
        <th>Cross Price</th>
        <th>Entry</th>
        <th>Exit</th>
        <th>Exit Time</th>
        <th>QuoteVol 24h</th>
        <th>MarketCap</th>
        <th>Cross Candle Vol</th>
        <th>Vol Ratio</th>
        <th>EMA Set</th>
        <th>EMA Distance</th>
        <th>PnL</th>
        <th>Duration</th>
        <th>Max Profit</th>
        <th>Max Drawdown</th>
        <th>RR</th>
        <th>Entry Reason</th>
        <th>Exit Reason</th>
    </tr>
    """

    for t in stats["recent_trades"]:
        ema_set = "-"
        if t.ema_fast is not None and t.ema_mid is not None and t.ema_trend is not None:
            ema_set = f"{t.ema_fast}/{t.ema_mid}/{t.ema_trend}"

        html += f"""
        <tr>
            <td>{t.id}</td>
            <td>{t.symbol}</td>
            <td>{t.side}</td>
            <td>{t.mode or '-'}</td>
            <td>{fmt_dt(t.cross_time)}</td>
            <td>{fmt_num(t.cross_price, 6)}</td>
            <td>{fmt_num(t.entry_price, 6)}</td>
            <td>{fmt_num(t.exit_price, 6) if t.exit_price is not None else '-'}</td>
            <td>{fmt_dt(t.exit_time)}</td>
            <td>{fmt_big(t.quote_volume_24h)}</td>
            <td>{fmt_big(t.market_cap)}</td>
            <td>{fmt_big(t.cross_candle_volume)}</td>
            <td>{fmt_num(t.volume_ratio, 2)}</td>
            <td>{ema_set}</td>
            <td>{fmt_pct(t.ema_distance, 4)}</td>
            <td>{fmt_pct(t.pnl_pct, 2) if t.pnl_pct is not None else '-'}</td>
            <td>{format_duration_from_minutes(t.duration_minutes)}</td>
            <td>{fmt_pct(t.max_profit_pct, 2)}</td>
            <td>{fmt_pct(t.max_drawdown_pct, 2)}</td>
            <td>{fmt_num(t.rr_ratio, 2)}</td>
            <td>{t.entry_reason or '-'}</td>
            <td>{t.exit_reason or '-'}</td>
        </tr>
        """

    html += """
    </table>
    </div>
    </body>
    </html>
    """

    return html
