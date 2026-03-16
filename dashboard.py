from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from storage import get_dashboard_stats, init_db, format_duration_from_minutes

app = FastAPI()

init_db()

PAGE_SIZE = 50


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


def color_class_by_value(value):
    if value is None:
        return ""
    if value > 0:
        return "pos"
    if value < 0:
        return "neg"
    return "neu"


def color_class_by_rate(value):
    if value is None:
        return ""
    if value >= 50:
        return "pos"
    return "neg"


def safe_upper(value, default="ALL"):
    if value is None:
        return default
    return str(value).strip().upper()


def build_url(page, status, side, mode):
    return f"/?page={page}&status={status}&side={side}&mode={mode}"


@app.get("/", response_class=HTMLResponse)
def dashboard(
    page: int = Query(1, ge=1),
    status: str = Query("ALL"),
    side: str = Query("ALL"),
    mode: str = Query("ALL"),
):
    stats = get_dashboard_stats()

    status = safe_upper(status, "ALL")
    side = safe_upper(side, "ALL")
    mode = safe_upper(mode, "ALL")

    all_trades = stats["recent_trades"]

    filtered_trades = []
    for t in all_trades:
        if status != "ALL" and (t.status or "").upper() != status:
            continue
        if side != "ALL" and (t.side or "").upper() != side:
            continue
        if mode != "ALL" and (t.mode or "").upper() != mode:
            continue
        filtered_trades.append(t)

    total_rows = len(filtered_trades)
    total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

    if page > total_pages:
        page = total_pages

    start_idx = (page - 1) * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    paged_trades = filtered_trades[start_idx:end_idx]

    visible_closed = [t for t in filtered_trades if (t.status or "").upper() == "CLOSED"]
    visible_open = [t for t in filtered_trades if (t.status or "").upper() == "OPEN"]

    visible_closed_count = len(visible_closed)
    visible_open_count = len(visible_open)

    visible_wins = sum(1 for t in visible_closed if (t.pnl_pct or 0) > 0)
    visible_losses = sum(1 for t in visible_closed if (t.pnl_pct or 0) < 0)
    visible_total_pnl = sum((t.pnl_pct or 0) for t in visible_closed)
    visible_avg_pnl = (visible_total_pnl / visible_closed_count) if visible_closed_count > 0 else 0.0
    visible_win_rate = (visible_wins / visible_closed_count * 100) if visible_closed_count > 0 else 0.0

    html = f"""
    <html>
    <head>
        <title>EMA Scanner Dashboard</title>
        <style>
        body {{
            background:#0f0f0f;
            color:white;
            font-family:Arial, sans-serif;
            padding:24px;
            margin:0;
        }}
        h1, h2 {{
            margin-top:0;
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
        .pos {{
            color:#22c55e;
            font-weight:bold;
        }}
        .neg {{
            color:#ef4444;
            font-weight:bold;
        }}
        .neu {{
            color:#eab308;
            font-weight:bold;
        }}
        .muted {{
            color:#aaa;
        }}
        .toolbar {{
            display:flex;
            flex-wrap:wrap;
            gap:12px;
            margin-bottom:20px;
            padding:16px;
            background:#141414;
            border:1px solid #2a2a2a;
            border-radius:12px;
        }}
        .filter-group {{
            display:flex;
            flex-direction:column;
            gap:6px;
        }}
        .filter-label {{
            font-size:12px;
            color:#aaa;
        }}
        select {{
            background:#0f0f0f;
            color:white;
            border:1px solid #444;
            border-radius:8px;
            padding:8px 10px;
            min-width:140px;
        }}
        .apply-btn {{
            background:#2563eb;
            color:white;
            border:none;
            border-radius:8px;
            padding:10px 16px;
            cursor:pointer;
            font-weight:bold;
            margin-top:18px;
        }}
        .apply-btn:hover {{
            background:#1d4ed8;
        }}
        .reset-link {{
            display:inline-block;
            margin-top:18px;
            padding:10px 14px;
            border:1px solid #444;
            border-radius:8px;
            color:white;
            text-decoration:none;
            background:#181818;
        }}
        .reset-link:hover {{
            background:#222;
        }}
        .summary-cards {{
            display:grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap:12px;
            margin-bottom:24px;
        }}
        .card {{
            background:#141414;
            border:1px solid #2a2a2a;
            border-radius:12px;
            padding:16px;
        }}
        .card-title {{
            color:#aaa;
            font-size:12px;
            margin-bottom:6px;
        }}
        .card-value {{
            font-size:24px;
            font-weight:bold;
        }}
        .pagination {{
            display:flex;
            flex-wrap:wrap;
            gap:8px;
            margin-top:16px;
            margin-bottom:32px;
            align-items:center;
        }}
        .pagination a {{
            display:inline-block;
            padding:8px 12px;
            border:1px solid #444;
            color:white;
            text-decoration:none;
            border-radius:8px;
            background:#181818;
        }}
        .pagination a:hover {{
            background:#222;
        }}
        .pagination a.active {{
            background:#2563eb;
            border-color:#2563eb;
            font-weight:bold;
        }}
        .pagination a.disabled {{
            pointer-events:none;
            opacity:0.4;
        }}
        .section-note {{
            color:#aaa;
            margin-bottom:10px;
            font-size:13px;
        }}
        .chip-row {{
            display:flex;
            flex-wrap:wrap;
            gap:8px;
            margin-bottom:16px;
        }}
        .chip {{
            padding:8px 12px;
            border-radius:999px;
            border:1px solid #333;
            background:#161616;
            font-size:12px;
            color:#ddd;
        }}
        </style>
    </head>
    <body>

    <h1>🚀 EMA Scanner Dashboard</h1>

    <form method="get" action="/" class="toolbar">
        <div class="filter-group">
            <label class="filter-label">Status</label>
            <select name="status">
                <option value="ALL" {"selected" if status == "ALL" else ""}>ALL</option>
                <option value="OPEN" {"selected" if status == "OPEN" else ""}>OPEN</option>
                <option value="CLOSED" {"selected" if status == "CLOSED" else ""}>CLOSED</option>
            </select>
        </div>

        <div class="filter-group">
            <label class="filter-label">Side</label>
            <select name="side">
                <option value="ALL" {"selected" if side == "ALL" else ""}>ALL</option>
                <option value="LONG" {"selected" if side == "LONG" else ""}>LONG</option>
                <option value="SHORT" {"selected" if side == "SHORT" else ""}>SHORT</option>
            </select>
        </div>

        <div class="filter-group">
            <label class="filter-label">Mode</label>
            <select name="mode">
                <option value="ALL" {"selected" if mode == "ALL" else ""}>ALL</option>
                <option value="PUMP" {"selected" if mode == "PUMP" else ""}>PUMP</option>
                <option value="DIP" {"selected" if mode == "DIP" else ""}>DIP</option>
            </select>
        </div>

        <input type="hidden" name="page" value="1" />
        <button type="submit" class="apply-btn">Apply Filters</button>
        <a href="/" class="reset-link">Reset</a>
    </form>

    <div class="chip-row">
        <div class="chip">Status: <b>{status}</b></div>
        <div class="chip">Side: <b>{side}</b></div>
        <div class="chip">Mode: <b>{mode}</b></div>
        <div class="chip">Page Size: <b>{PAGE_SIZE}</b></div>
    </div>

    <h2>Filtrelenmiş Özet</h2>
    <div class="summary-cards">
        <div class="card">
            <div class="card-title">Filtered Signals</div>
            <div class="card-value">{total_rows}</div>
        </div>
        <div class="card">
            <div class="card-title">Filtered Closed</div>
            <div class="card-value">{visible_closed_count}</div>
        </div>
        <div class="card">
            <div class="card-title">Filtered Open</div>
            <div class="card-value">{visible_open_count}</div>
        </div>
        <div class="card">
            <div class="card-title">Filtered Win Rate</div>
            <div class="card-value {color_class_by_rate(visible_win_rate)}">{visible_win_rate:.2f}%</div>
        </div>
        <div class="card">
            <div class="card-title">Filtered Total PnL</div>
            <div class="card-value {color_class_by_value(visible_total_pnl)}">{visible_total_pnl:.2f}%</div>
        </div>
        <div class="card">
            <div class="card-title">Filtered Avg PnL</div>
            <div class="card-value {color_class_by_value(visible_avg_pnl)}">{visible_avg_pnl:.2f}%</div>
        </div>
        <div class="card">
            <div class="card-title">Winning Trades</div>
            <div class="card-value pos">{visible_wins}</div>
        </div>
        <div class="card">
            <div class="card-title">Losing Trades</div>
            <div class="card-value neg">{visible_losses}</div>
        </div>
    </div>

    <h2>Genel İstatistik</h2>
    <div class="wrap">
    <table>
        <tr><th>Total Signals</th><td>{stats['total_signals']}</td></tr>
        <tr><th>Closed Trades</th><td>{stats['total_closed']}</td></tr>
        <tr><th>Open Trades</th><td>{stats['total_open']}</td></tr>
        <tr><th>Win Rate</th><td class="{color_class_by_rate(stats['win_rate'])}">{stats['win_rate']:.2f}%</td></tr>
        <tr><th>Total PnL</th><td class="{color_class_by_value(stats['total_pnl'])}">{stats['total_pnl']:.2f}%</td></tr>
        <tr><th>Average PnL</th><td class="{color_class_by_value(stats['avg_pnl'])}">{stats['avg_pnl']:.2f}%</td></tr>
        <tr><th>Average Duration</th><td>{stats['avg_duration']:.2f} min</td></tr>
        <tr><th>Average Max Profit</th><td class="{color_class_by_value(stats['avg_mfe'])}">{stats['avg_mfe']:.2f}%</td></tr>
        <tr><th>Average Max Drawdown</th><td class="{color_class_by_value(stats['avg_mae'])}">{stats['avg_mae']:.2f}%</td></tr>
        <tr><th>Average RR Proxy</th><td class="{color_class_by_value(stats['avg_rr'])}">{stats['avg_rr']:.2f}</td></tr>
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
            <td class="{color_class_by_value(stats['long_pnl'])}">{stats['long_pnl']:.2f}%</td>
            <td class="{color_class_by_value(stats['short_pnl'])}">{stats['short_pnl']:.2f}%</td>
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
            <td class="{color_class_by_rate(stats['pump_win_rate'])}">{stats['pump_win_rate']:.2f}%</td>
            <td class="{color_class_by_rate(stats['dip_win_rate'])}">{stats['dip_win_rate']:.2f}%</td>
            <td class="{color_class_by_value(stats['pump_pnl'])}">{stats['pump_pnl']:.2f}%</td>
            <td class="{color_class_by_value(stats['dip_pnl'])}">{stats['dip_pnl']:.2f}%</td>
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
            <td class="{color_class_by_value(c['avg_profit'])}">{c['avg_profit']:.2f}%</td>
            <td class="{color_class_by_value(c['total_pnl'])}">{c['total_pnl']:.2f}%</td>
        </tr>
        """

    html += f"""
    </table>
    </div>

    <h2>Trades</h2>
    <div class="section-note">
        Filtreye göre toplam <b>{total_rows}</b> kayıt var. Sayfa başına <b>{PAGE_SIZE}</b> kayıt gösteriliyor.
        Şu an <b>{page}/{total_pages}</b> sayfasındasın.
    </div>

    <div class="wrap">
    <table>
    <tr>
        <th>ID</th>
        <th>Status</th>
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

    for t in paged_trades:
        ema_set = "-"
        if t.ema_fast is not None and t.ema_mid is not None and t.ema_trend is not None:
            ema_set = f"{t.ema_fast}/{t.ema_mid}/{t.ema_trend}"

        pnl_class = color_class_by_value(t.pnl_pct)
        max_profit_class = color_class_by_value(t.max_profit_pct)
        max_drawdown_class = color_class_by_value(t.max_drawdown_pct)
        rr_class = color_class_by_value(t.rr_ratio)

        status_class = "neu"
        if (t.status or "").upper() == "OPEN":
            status_class = "pos"
        elif (t.status or "").upper() == "CLOSED":
            status_class = "neg"

        html += f"""
        <tr>
            <td>{t.id}</td>
            <td class="{status_class}">{t.status}</td>
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
            <td class="{pnl_class}">{fmt_pct(t.pnl_pct, 2) if t.pnl_pct is not None else '-'}</td>
            <td>{format_duration_from_minutes(t.duration_minutes)}</td>
            <td class="{max_profit_class}">{fmt_pct(t.max_profit_pct, 2)}</td>
            <td class="{max_drawdown_class}">{fmt_pct(t.max_drawdown_pct, 2)}</td>
            <td class="{rr_class}">{fmt_num(t.rr_ratio, 2)}</td>
            <td>{t.entry_reason or '-'}</td>
            <td>{t.exit_reason or '-'}</td>
        </tr>
        """

    html += """
    </table>
    </div>

    <div class="pagination">
    """

    prev_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)

    prev_disabled = "disabled" if page <= 1 else ""
    next_disabled = "disabled" if page >= total_pages else ""

    html += f'<a class="{prev_disabled}" href="{build_url(prev_page, status, side, mode)}">← Previous</a>'

    page_window = 2
    start_page = max(1, page - page_window)
    end_page = min(total_pages, page + page_window)

    if start_page > 1:
        html += f'<a href="{build_url(1, status, side, mode)}">1</a>'
        if start_page > 2:
            html += '<a class="disabled" href="#">...</a>'

    for p in range(start_page, end_page + 1):
        active_class = "active" if p == page else ""
        html += f'<a class="{active_class}" href="{build_url(p, status, side, mode)}">{p}</a>'

    if end_page < total_pages:
        if end_page < total_pages - 1:
            html += '<a class="disabled" href="#">...</a>'
        html += f'<a href="{build_url(total_pages, status, side, mode)}">{total_pages}</a>'

    html += f'<a class="{next_disabled}" href="{build_url(next_page, status, side, mode)}">Next →</a>'

    html += """
    </div>

    </body>
    </html>
    """

    return html
