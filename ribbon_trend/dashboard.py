from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, request

from config import DASHBOARD_HOST, DASHBOARD_PORT, PUMP_DASHBOARD_URL, RIBBON_DASHBOARD_TITLE
from db import fetch_open_trades, fetch_stats, fetch_trades, init_db

app = Flask(__name__)

ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")


def _parse_dt(value):
    if not value:
        return None

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

        return dt
    except Exception:
        return None


def _to_istanbul_time(value) -> str:
    dt = _parse_dt(value)
    if not dt:
        return "-"
    return dt.astimezone(ISTANBUL_TZ).strftime("%d.%m.%Y %H:%M:%S")


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


def _human_minutes(total_minutes: float) -> str:
    total_minutes = int(max(total_minutes, 0))
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours <= 0:
        return f"{minutes}m"
    return f"{hours}h {minutes}m"


def _calc_avg_trade_time_minutes(closed_trades: list[dict]) -> float:
    durations = []

    for t in closed_trades:
        entry_dt = _parse_dt(t.get("entry_time"))
        exit_dt = _parse_dt(t.get("exit_time"))

        if not entry_dt or not exit_dt:
            continue

        seconds = (exit_dt - entry_dt).total_seconds()
        if seconds >= 0:
            durations.append(seconds)

    if not durations:
        return 0.0

    avg_seconds = sum(durations) / len(durations)
    return round(avg_seconds / 60.0, 2)


def _build_equity_curve_svg(closed_trades: list[dict], width: int = 1100, height: int = 260) -> str:
    if not closed_trades:
        return f"""
        <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg">
            <rect x="0" y="0" width="{width}" height="{height}" fill="#0f172a" />
            <text x="{width/2}" y="{height/2}" text-anchor="middle" fill="#94a3b8" font-size="18">
                Henüz equity curve için kapalı işlem yok
            </text>
        </svg>
        """

    equity_values = []
    running = 0.0
    for t in closed_trades:
        running += _safe_float(t.get("roi_pct"))
        equity_values.append(running)

    min_v = min(equity_values)
    max_v = max(equity_values)

    if min_v == max_v:
        min_v -= 1.0
        max_v += 1.0

    left_pad = 50
    right_pad = 20
    top_pad = 20
    bottom_pad = 35
    plot_w = width - left_pad - right_pad
    plot_h = height - top_pad - bottom_pad

    def x_of(i: int) -> float:
        if len(equity_values) == 1:
            return left_pad + plot_w / 2
        return left_pad + (i / (len(equity_values) - 1)) * plot_w

    def y_of(v: float) -> float:
        ratio = (v - min_v) / (max_v - min_v)
        return top_pad + (1 - ratio) * plot_h

    points = " ".join(f"{x_of(i):.2f},{y_of(v):.2f}" for i, v in enumerate(equity_values))

    zero_y = None
    if min_v <= 0 <= max_v:
        zero_y = y_of(0)

    last_equity = equity_values[-1]
    last_x = x_of(len(equity_values) - 1)
    last_y = y_of(last_equity)

    y_ticks = []
    for k in range(5):
        val = min_v + (max_v - min_v) * (k / 4)
        y = y_of(val)
        y_ticks.append((val, y))

    grid_lines = ""
    labels = ""
    for val, y in y_ticks:
        grid_lines += f'<line x1="{left_pad}" y1="{y:.2f}" x2="{width-right_pad}" y2="{y:.2f}" stroke="#1f2937" stroke-width="1" />'
        labels += f'<text x="{left_pad-8}" y="{y+4:.2f}" text-anchor="end" fill="#94a3b8" font-size="11">{val:.1f}</text>'

    zero_line = ""
    if zero_y is not None:
        zero_line = f'<line x1="{left_pad}" y1="{zero_y:.2f}" x2="{width-right_pad}" y2="{zero_y:.2f}" stroke="#475569" stroke-dasharray="4 4" stroke-width="1.2" />'

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="{width}" height="{height}" rx="12" ry="12" fill="#0f172a" />
        {grid_lines}
        {zero_line}
        {labels}
        <polyline
            fill="none"
            stroke="#22c55e"
            stroke-width="3"
            points="{points}"
            stroke-linejoin="round"
            stroke-linecap="round"
        />
        <circle cx="{last_x:.2f}" cy="{last_y:.2f}" r="4.5" fill="#22c55e" />
        <text x="{last_x-10:.2f}" y="{last_y-12:.2f}" text-anchor="end" fill="#e5e7eb" font-size="12">
            {last_equity:.2f}%
        </text>
        <text x="{width/2}" y="16" text-anchor="middle" fill="#cbd5e1" font-size="14">
            Equity Curve (Kapalı İşlemler Birikimli ROI)
        </text>
        <text x="{width/2}" y="{height-8}" text-anchor="middle" fill="#94a3b8" font-size="11">
            İşlem Sırası
        </text>
    </svg>
    """


def _calc_streaks(closed_trades: list[dict]) -> tuple[int, int]:
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


def _calc_open_trade_health(open_trades: list[dict]) -> dict:
    now_utc = datetime.now(timezone.utc)

    open_long = 0
    open_short = 0
    recovery_count = 0

    durations_min = []
    oldest_trade = None
    oldest_minutes = 0.0

    age_lt_1h = 0
    age_1_3h = 0
    age_3_6h = 0
    age_6h_plus = 0

    open_profit_count = 0
    open_loss_count = 0
    open_breakeven_count = 0

    total_open_roi = 0.0
    total_open_pnl = 0.0

    best_open_roi_trade = None
    best_open_roi_value = None

    worst_open_roi_trade = None
    worst_open_roi_value = None

    touched_profit = 0
    touched_drawdown = 0

    best_favor_trade = None
    best_favor_value = None

    worst_adverse_trade = None
    worst_adverse_value = None

    total_max_favor = 0.0
    total_max_adverse = 0.0

    for t in open_trades:
        side = str(t.get("side", "")).lower()
        if side == "long":
            open_long += 1
        elif side == "short":
            open_short += 1

        if bool(t.get("recovery_mode")):
            recovery_count += 1

        entry_dt = _parse_dt(t.get("entry_time"))
        if entry_dt:
            age_min = max((now_utc - entry_dt).total_seconds() / 60.0, 0.0)
            durations_min.append(age_min)

            if age_min < 60:
                age_lt_1h += 1
            elif age_min < 180:
                age_1_3h += 1
            elif age_min < 360:
                age_3_6h += 1
            else:
                age_6h_plus += 1

            if age_min > oldest_minutes:
                oldest_minutes = age_min
                oldest_trade = t

        floating_roi = _safe_float(t.get("floating_roi_pct"))
        floating_pnl = _safe_float(t.get("floating_pnl_pct"))

        total_open_roi += floating_roi
        total_open_pnl += floating_pnl

        if floating_roi > 0.05:
            open_profit_count += 1
        elif floating_roi < -0.05:
            open_loss_count += 1
        else:
            open_breakeven_count += 1

        if best_open_roi_value is None or floating_roi > best_open_roi_value:
            best_open_roi_value = floating_roi
            best_open_roi_trade = t

        if worst_open_roi_value is None or floating_roi < worst_open_roi_value:
            worst_open_roi_value = floating_roi
            worst_open_roi_trade = t

        max_favor = _safe_float(t.get("max_favor_pct"))
        max_adverse = _safe_float(t.get("max_adverse_pct"))

        total_max_favor += max_favor
        total_max_adverse += max_adverse

        if max_favor > 0:
            touched_profit += 1

        if max_adverse < 0:
            touched_drawdown += 1

        if best_favor_value is None or max_favor > best_favor_value:
            best_favor_value = max_favor
            best_favor_trade = t

        if worst_adverse_value is None or max_adverse < worst_adverse_value:
            worst_adverse_value = max_adverse
            worst_adverse_trade = t

    open_total = len(open_trades)
    avg_open_duration_min = round(sum(durations_min) / len(durations_min), 2) if durations_min else 0.0
    avg_open_roi = round(total_open_roi / open_total, 2) if open_total else 0.0
    avg_open_pnl = round(total_open_pnl / open_total, 4) if open_total else 0.0

    return {
        "open_total": open_total,
        "open_long": open_long,
        "open_short": open_short,
        "recovery_count": recovery_count,
        "avg_open_duration_min": avg_open_duration_min,
        "oldest_trade": oldest_trade,
        "oldest_open_duration_min": round(oldest_minutes, 2),
        "age_lt_1h": age_lt_1h,
        "age_1_3h": age_1_3h,
        "age_3_6h": age_3_6h,
        "age_6h_plus": age_6h_plus,
        "open_profit_count": open_profit_count,
        "open_loss_count": open_loss_count,
        "open_breakeven_count": open_breakeven_count,
        "total_open_roi": round(total_open_roi, 2),
        "total_open_pnl": round(total_open_pnl, 4),
        "avg_open_roi": avg_open_roi,
        "avg_open_pnl": avg_open_pnl,
        "best_open_roi_value": round(best_open_roi_value or 0.0, 2),
        "best_open_roi_trade": best_open_roi_trade,
        "worst_open_roi_value": round(worst_open_roi_value or 0.0, 2),
        "worst_open_roi_trade": worst_open_roi_trade,
        "touched_profit": touched_profit,
        "touched_drawdown": touched_drawdown,
        "best_favor_value": round(best_favor_value or 0.0, 2),
        "best_favor_trade": best_favor_trade,
        "worst_adverse_value": round(worst_adverse_value or 0.0, 2),
        "worst_adverse_trade": worst_adverse_trade,
        "total_max_favor": round(total_max_favor, 2),
        "total_max_adverse": round(total_max_adverse, 2),
    }


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
    open_trades = fetch_open_trades()

    if side != "all":
        trades = [t for t in trades if t["side"] == side]

    if status != "all":
        trades = [t for t in trades if t["status"] == status]

    all_trades = fetch_trades(limit=500)
    closed_trades_for_stats = [t for t in reversed(all_trades) if t.get("status") == "closed"]

    closed_long_count = sum(1 for t in all_trades if t.get("status") == "closed" and t.get("side") == "long")
    closed_short_count = sum(1 for t in all_trades if t.get("status") == "closed" and t.get("side") == "short")

    max_win_streak, max_losing_streak = _calc_streaks(closed_trades_for_stats)
    avg_trade_time_min = _calc_avg_trade_time_minutes(closed_trades_for_stats)
    equity_curve_svg = _build_equity_curve_svg(closed_trades_for_stats)

    open_health = _calc_open_trade_health(open_trades)

    oldest_trade_symbol = _fmt_text(open_health["oldest_trade"].get("symbol")) if open_health["oldest_trade"] else "-"
    best_open_roi_symbol = _fmt_text(open_health["best_open_roi_trade"].get("symbol")) if open_health["best_open_roi_trade"] else "-"
    worst_open_roi_symbol = _fmt_text(open_health["worst_open_roi_trade"].get("symbol")) if open_health["worst_open_roi_trade"] else "-"
    best_favor_symbol = _fmt_text(open_health["best_favor_trade"].get("symbol")) if open_health["best_favor_trade"] else "-"
    worst_adverse_symbol = _fmt_text(open_health["worst_adverse_trade"].get("symbol")) if open_health["worst_adverse_trade"] else "-"

    rows = ""
    for t in trades:
        roi_val = None if t.get("roi_pct") is None else float(t["roi_pct"])
        pnl_val = None if t.get("pnl_pct") is None else float(t["pnl_pct"])
        floating_roi_val = None if t.get("floating_roi_pct") is None else float(t["floating_roi_pct"])
        floating_pnl_val = None if t.get("floating_pnl_pct") is None else float(t["floating_pnl_pct"])

        roi_color = "#22c55e" if roi_val is not None and roi_val > 0 else "#ef4444" if roi_val is not None and roi_val < 0 else "#e5e7eb"
        pnl_color = "#22c55e" if pnl_val is not None and pnl_val > 0 else "#ef4444" if pnl_val is not None and pnl_val < 0 else "#e5e7eb"
        floating_roi_color = "#22c55e" if floating_roi_val is not None and floating_roi_val > 0 else "#ef4444" if floating_roi_val is not None and floating_roi_val < 0 else "#e5e7eb"
        floating_pnl_color = "#22c55e" if floating_pnl_val is not None and floating_pnl_val > 0 else "#ef4444" if floating_pnl_val is not None and floating_pnl_val < 0 else "#e5e7eb"

        side_badge = "#16a34a" if t["side"] == "long" else "#dc2626"
        status_badge = "#2563eb" if t["status"] == "open" else "#6b7280"
        recovery_badge = "#f59e0b" if bool(t.get("recovery_mode")) else "#374151"
        row_bg = "#0b1324" if t["status"] == "open" else "transparent"

        rows += f"""
        <tr style="background:{row_bg}">
            <td>{t['id']}</td>
            <td>{t['symbol']}</td>
            <td><span class="badge" style="background:{side_badge}">{t['side'].upper()}</span></td>
            <td><span class="badge" style="background:{status_badge}">{t['status'].upper()}</span></td>
            <td><span class="badge" style="background:{recovery_badge}">{'RECOVERY' if bool(t.get('recovery_mode')) else 'NORMAL'}</span></td>
            <td>{_fmt_price(t.get('entry_price'))}</td>
            <td>{_fmt_price(t.get('tp_price'))}</td>
            <td>{_fmt_price(t.get('sl_price'))}</td>
            <td>{_fmt_price(t.get('current_price'))}</td>
            <td>{_fmt_price(t.get('exit_price'))}</td>
            <td style="color:{floating_pnl_color}">{_fmt_pct(t.get('floating_pnl_pct'))}</td>
            <td style="color:{floating_roi_color}">{_fmt_pct(t.get('floating_roi_pct'))}</td>
            <td style="color:{pnl_color}">{_fmt_pct(t.get('pnl_pct'))}</td>
            <td style="color:{roi_color}">{_fmt_pct(t.get('roi_pct'))}</td>
            <td>{_to_istanbul_time(t.get('entry_time'))}</td>
            <td>{_to_istanbul_time(t.get('last_price_time'))}</td>
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
            .section {{
                margin-bottom:20px;
            }}
            .section-title {{
                color:#cbd5e1;
                font-size:18px;
                font-weight:700;
                margin:8px 0 14px 0;
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
            .chart-card {{
                background:#111827;
                border:1px solid #1f2937;
                border-radius:12px;
                padding:14px;
                margin-bottom:20px;
            }}
            @media (max-width: 1200px) {{
                .cards {{
                    grid-template-columns:repeat(2,1fr);
                }}
            }}
            @media (max-width: 700px) {{
                .cards {{
                    grid-template-columns:1fr;
                }}
            }}
        </style>
    </head>
    <body>

    <div class="top-links">
        <a href="/">⬅ Ana Ekran</a>
    </div>

    <h1>{RIBBON_DASHBOARD_TITLE}</h1>
    <div class="sub">15m Binance Futures Ribbon Trend test paneli. Saatler İstanbul zamanıdır. Sayfa 30 saniyede bir yenilenir.</div>

    <div class="section">
        <div class="section-title">Closed Trade Summary</div>
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

            <div class="card"><div class="label">Max Winning Streak</div><div class="value">{max_win_streak}</div></div>
            <div class="card"><div class="label">Max Losing Streak</div><div class="value">{max_losing_streak}</div></div>
            <div class="card"><div class="label">Avg Trade Time</div><div class="value">{avg_trade_time_min} min</div></div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">Open Trade ROI Health</div>
        <div class="cards">
            <div class="card"><div class="label">Open Trades</div><div class="value">{open_health["open_total"]}</div></div>
            <div class="card"><div class="label">Open Long</div><div class="value">{open_health["open_long"]}</div></div>
            <div class="card"><div class="label">Open Short</div><div class="value">{open_health["open_short"]}</div></div>
            <div class="card"><div class="label">Recovery Mode</div><div class="value">{open_health["recovery_count"]}</div></div>

            <div class="card"><div class="label">Open Profit</div><div class="value">{open_health["open_profit_count"]}</div></div>
            <div class="card"><div class="label">Open Loss</div><div class="value">{open_health["open_loss_count"]}</div></div>
            <div class="card"><div class="label">Break-even Zone</div><div class="value">{open_health["open_breakeven_count"]}</div></div>
            <div class="card"><div class="label">Avg Open ROI</div><div class="value">{open_health["avg_open_roi"]}%</div></div>

            <div class="card"><div class="label">Total Open ROI</div><div class="value">{open_health["total_open_roi"]}%</div></div>
            <div class="card"><div class="label">Avg Open PnL</div><div class="value">{open_health["avg_open_pnl"]}%</div></div>
            <div class="card"><div class="label">Total Open PnL</div><div class="value">{open_health["total_open_pnl"]}%</div></div>
            <div class="card"><div class="label">Avg Open Duration</div><div class="value">{open_health["avg_open_duration_min"]} min</div></div>

            <div class="card"><div class="label">Oldest Open Trade</div><div class="value">{_human_minutes(open_health["oldest_open_duration_min"])}</div></div>
            <div class="card"><div class="label">Oldest Coin</div><div class="value">{oldest_trade_symbol}</div></div>
            <div class="card"><div class="label">Best Open ROI</div><div class="value">{open_health["best_open_roi_value"]}%</div></div>
            <div class="card"><div class="label">Best ROI Coin</div><div class="value">{best_open_roi_symbol}</div></div>

            <div class="card"><div class="label">Worst Open ROI</div><div class="value">{open_health["worst_open_roi_value"]}%</div></div>
            <div class="card"><div class="label">Worst ROI Coin</div><div class="value">{worst_open_roi_symbol}</div></div>
            <div class="card"><div class="label">Touched Profit</div><div class="value">{open_health["touched_profit"]}</div></div>
            <div class="card"><div class="label">Touched Drawdown</div><div class="value">{open_health["touched_drawdown"]}</div></div>

            <div class="card"><div class="label">Best Max Favor</div><div class="value">{open_health["best_favor_value"]}%</div></div>
            <div class="card"><div class="label">Best Favor Coin</div><div class="value">{best_favor_symbol}</div></div>
            <div class="card"><div class="label">Worst Max Adverse</div><div class="value">{open_health["worst_adverse_value"]}%</div></div>
            <div class="card"><div class="label">Worst Adverse Coin</div><div class="value">{worst_adverse_symbol}</div></div>

            <div class="card"><div class="label">Open Age &lt; 1h</div><div class="value">{open_health["age_lt_1h"]}</div></div>
            <div class="card"><div class="label">Open Age 1-3h</div><div class="value">{open_health["age_1_3h"]}</div></div>
            <div class="card"><div class="label">Open Age 3-6h</div><div class="value">{open_health["age_3_6h"]}</div></div>
            <div class="card"><div class="label">Open Age 6h+</div><div class="value">{open_health["age_6h_plus"]}</div></div>
        </div>
    </div>

    <div class="chart-card">
        {equity_curve_svg}
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
                <th>Mode</th>
                <th>Entry</th>
                <th>TP</th>
                <th>SL</th>
                <th>Current</th>
                <th>Exit</th>
                <th>Floating PnL</th>
                <th>Floating ROI</th>
                <th>Closed PnL</th>
                <th>Closed ROI</th>
                <th>Entry Time</th>
                <th>Last Price Time</th>
                <th>Exit Time</th>
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
