from flask import Flask, render_template_string, request
from sqlalchemy import desc

from storage import SessionLocal, Signal

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pump Hunter Dashboard</title>
    <style>
        :root {
            --bg: #0b0f14;
            --panel: #121821;
            --panel-2: #18212b;
            --line: #263241;
            --text: #e8eef5;
            --muted: #93a4b8;
            --green: #22c55e;
            --red: #ef4444;
            --yellow: #eab308;
            --blue: #3b82f6;
            --purple: #a855f7;
            --cyan: #06b6d4;
            --orange: #f97316;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
        }

        .container {
            max-width: 1700px;
            margin: 0 auto;
            padding: 16px;
        }

        .header {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .title {
            font-size: 28px;
            font-weight: 700;
        }

        .subtitle {
            color: var(--muted);
            font-size: 13px;
            margin-top: 4px;
        }

        .toolbar {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 14px;
            margin-bottom: 16px;
        }

        .filters {
            display: grid;
            grid-template-columns: repeat(9, minmax(120px, 1fr));
            gap: 10px;
        }

        .filters input,
        .filters select,
        .filters button,
        .filters a {
            width: 100%;
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid var(--line);
            background: var(--panel-2);
            color: var(--text);
        }

        .filters button {
            background: var(--blue);
            border: none;
            cursor: pointer;
            font-weight: 700;
        }

        .filters button:hover {
            opacity: 0.9;
        }

        .filters .reset-btn {
            background: #334155;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }

        .cards {
            display: grid;
            grid-template-columns: repeat(6, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }

        .card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 14px;
        }

        .card .label {
            color: var(--muted);
            font-size: 12px;
            margin-bottom: 8px;
        }

        .card .value {
            font-size: 24px;
            font-weight: 700;
        }

        .green { color: var(--green); }
        .red { color: var(--red); }
        .yellow { color: var(--yellow); }
        .blue { color: var(--blue); }
        .purple { color: var(--purple); }
        .muted { color: var(--muted); }

        .table-wrap {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 14px;
            overflow: hidden;
        }

        .table-head {
            padding: 14px 14px 0 14px;
        }

        .table-title {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 4px;
        }

        .table-note {
            color: var(--muted);
            font-size: 12px;
            margin-bottom: 10px;
        }

        .table-scroll {
            overflow-x: auto;
        }

        table {
            width: 100%;
            min-width: 1800px;
            border-collapse: collapse;
            font-size: 13px;
        }

        th, td {
            padding: 10px 8px;
            border-bottom: 1px solid var(--line);
            text-align: center;
            white-space: nowrap;
        }

        th {
            position: sticky;
            top: 0;
            background: #0f1620;
            z-index: 1;
            color: #c7d2de;
        }

        tr:hover td {
            background: rgba(255,255,255,0.03);
        }

        .left { text-align: left; }

        .badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 5px 8px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 700;
            border: 1px solid transparent;
        }

        .badge-long {
            background: rgba(34,197,94,0.12);
            color: var(--green);
            border-color: rgba(34,197,94,0.35);
        }

        .badge-short {
            background: rgba(239,68,68,0.12);
            color: var(--red);
            border-color: rgba(239,68,68,0.35);
        }

        .badge-open {
            background: rgba(59,130,246,0.12);
            color: var(--blue);
            border-color: rgba(59,130,246,0.35);
        }

        .badge-closed {
            background: rgba(148,163,184,0.12);
            color: #cbd5e1;
            border-color: rgba(148,163,184,0.35);
        }

        .badge-pump {
            background: rgba(168,85,247,0.12);
            color: var(--purple);
            border-color: rgba(168,85,247,0.35);
        }

        .badge-dip {
            background: rgba(6,182,212,0.12);
            color: var(--cyan);
            border-color: rgba(6,182,212,0.35);
        }

        .badge-new {
            background: rgba(249,115,22,0.12);
            color: var(--orange);
            border-color: rgba(249,115,22,0.35);
        }

        .badge-a {
            background: rgba(34,197,94,0.12);
            color: var(--green);
            border-color: rgba(34,197,94,0.35);
        }

        .badge-b {
            background: rgba(234,179,8,0.12);
            color: var(--yellow);
            border-color: rgba(234,179,8,0.35);
        }

        .badge-c {
            background: rgba(239,68,68,0.12);
            color: var(--red);
            border-color: rgba(239,68,68,0.35);
        }

        .badge-risk-safe {
            background: rgba(34,197,94,0.12);
            color: var(--green);
            border-color: rgba(34,197,94,0.35);
        }

        .badge-risk-risk {
            background: rgba(234,179,8,0.12);
            color: var(--yellow);
            border-color: rgba(234,179,8,0.35);
        }

        .badge-risk-delist {
            background: rgba(239,68,68,0.12);
            color: var(--red);
            border-color: rgba(239,68,68,0.35);
        }

        .mobile-cards {
            display: none;
            gap: 12px;
            margin-top: 12px;
        }

        .signal-card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 14px;
        }

        .signal-card .top {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 10px;
            align-items: center;
        }

        .signal-card .symbol {
            font-size: 18px;
            font-weight: 700;
        }

        .signal-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(120px,1fr));
            gap: 8px;
            font-size: 13px;
        }

        .signal-grid .k {
            color: var(--muted);
        }

        @media (max-width: 1100px) {
            .filters {
                grid-template-columns: repeat(4, minmax(120px, 1fr));
            }
            .cards {
                grid-template-columns: repeat(3, minmax(160px, 1fr));
            }
        }

        @media (max-width: 720px) {
            .container { padding: 12px; }

            .filters {
                grid-template-columns: repeat(2, minmax(120px, 1fr));
            }

            .cards {
                grid-template-columns: repeat(2, minmax(140px, 1fr));
            }

            .table-wrap {
                display: none;
            }

            .mobile-cards {
                display: grid;
            }

            .title {
                font-size: 24px;
            }
        }
    </style>
</head>
<body>
<div class="container">

    <div class="header">
        <div>
            <div class="title">🚀 Pump Hunter Dashboard</div>
            <div class="subtitle">EMA 8 / 18 / 34 • LONG / SHORT • Cross / Bounce • Risk gözlem kolonları dahil</div>
        </div>
    </div>

    <form method="get" class="toolbar">
        <div class="filters">
            <input type="text" name="symbol" placeholder="Coin ara" value="{{ filters.symbol }}">

            <select name="side">
                <option value="">Side</option>
                <option value="LONG" {% if filters.side == 'LONG' %}selected{% endif %}>LONG</option>
                <option value="SHORT" {% if filters.side == 'SHORT' %}selected{% endif %}>SHORT</option>
            </select>

            <select name="status">
                <option value="">Status</option>
                <option value="OPEN" {% if filters.status == 'OPEN' %}selected{% endif %}>OPEN</option>
                <option value="CLOSED" {% if filters.status == 'CLOSED' %}selected{% endif %}>CLOSED</option>
            </select>

            <select name="signal_group">
                <option value="">Group</option>
                <option value="PUMP" {% if filters.signal_group == 'PUMP' %}selected{% endif %}>PUMP</option>
                <option value="DIP" {% if filters.signal_group == 'DIP' %}selected{% endif %}>DIP</option>
                <option value="NEW" {% if filters.signal_group == 'NEW' %}selected{% endif %}>NEW</option>
            </select>

            <select name="entry_type">
                <option value="">Entry Type</option>
                <option value="cross" {% if filters.entry_type == 'cross' %}selected{% endif %}>cross</option>
                <option value="bounce" {% if filters.entry_type == 'bounce' %}selected{% endif %}>bounce</option>
            </select>

            <select name="quality">
                <option value="">Quality</option>
                <option value="A" {% if filters.quality == 'A' %}selected{% endif %}>A</option>
                <option value="B" {% if filters.quality == 'B' %}selected{% endif %}>B</option>
                <option value="C" {% if filters.quality == 'C' %}selected{% endif %}>C</option>
            </select>

            <select name="risk_level">
                <option value="">Risk</option>
                <option value="SAFE" {% if filters.risk_level == 'SAFE' %}selected{% endif %}>SAFE</option>
                <option value="RISK" {% if filters.risk_level == 'RISK' %}selected{% endif %}>RISK</option>
                <option value="DELIST" {% if filters.risk_level == 'DELIST' %}selected{% endif %}>DELIST</option>
            </select>

            <input type="number" step="0.01" name="min_score" placeholder="Min score" value="{{ filters.min_score }}">
            <button type="submit">Filtrele</button>
        </div>
        <div class="filters" style="margin-top:10px;">
            <a href="/" class="reset-btn">Sıfırla</a>
        </div>
    </form>

    <div class="cards">
        <div class="card">
            <div class="label">Toplam Kayıt</div>
            <div class="value">{{ stats.total }}</div>
        </div>
        <div class="card">
            <div class="label">Açık İşlem</div>
            <div class="value blue">{{ stats.open_count }}</div>
        </div>
        <div class="card">
            <div class="label">Kapalı İşlem</div>
            <div class="value">{{ stats.closed_count }}</div>
        </div>
        <div class="card">
            <div class="label">Kazanan</div>
            <div class="value green">{{ stats.wins }}</div>
        </div>
        <div class="card">
            <div class="label">Kaybeden</div>
            <div class="value red">{{ stats.losses }}</div>
        </div>
        <div class="card">
            <div class="label">Win Rate</div>
            <div class="value {% if stats.win_rate >= 50 %}green{% else %}red{% endif %}">{{ stats.win_rate }}%</div>
        </div>
        <div class="card">
            <div class="label">Toplam PnL</div>
            <div class="value {% if stats.total_pnl >= 0 %}green{% else %}red{% endif %}">{{ stats.total_pnl }}%</div>
        </div>
        <div class="card">
            <div class="label">Ortalama PnL</div>
            <div class="value {% if stats.avg_pnl >= 0 %}green{% else %}red{% endif %}">{{ stats.avg_pnl }}%</div>
        </div>
        <div class="card">
            <div class="label">LONG</div>
            <div class="value green">{{ stats.long_count }}</div>
        </div>
        <div class="card">
            <div class="label">SHORT</div>
            <div class="value red">{{ stats.short_count }}</div>
        </div>
        <div class="card">
            <div class="label">Cross</div>
            <div class="value">{{ stats.cross_count }}</div>
        </div>
        <div class="card">
            <div class="label">Bounce</div>
            <div class="value">{{ stats.bounce_count }}</div>
        </div>
    </div>

    <div class="table-wrap">
        <div class="table-head">
            <div class="table-title">Trades</div>
            <div class="table-note">
                Filtreye göre toplam {{ stats.total }} kayıt var. En yeni kayıtlar üstte.
            </div>
        </div>
        <div class="table-scroll">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Coin</th>
                        <th>Side</th>
                        <th>Status</th>
                        <th>Group</th>
                        <th>Entry Type</th>
                        <th>Quality</th>
                        <th>Score</th>
                        <th>Risk</th>
                        <th>Risk Score</th>
                        <th>Risk Notes</th>
                        <th>EMA</th>
                        <th>Entry</th>
                        <th>Exit</th>
                        <th>PnL</th>
                        <th>Max Profit</th>
                        <th>RSI M</th>
                        <th>RSI W</th>
                        <th>RSI D</th>
                        <th>RSI 4H</th>
                        <th>1H %</th>
                        <th>4H %</th>
                        <th>Entry Reason</th>
                        <th>Exit Reason</th>
                        <th>Cooldown</th>
                        <th>Created</th>
                        <th>Exit Time</th>
                    </tr>
                </thead>
                <tbody>
                    {% for s in signals %}
                    <tr>
                        <td>{{ s.id }}</td>
                        <td class="left"><b>{{ s.symbol }}</b></td>
                        <td>
                            <span class="badge {% if s.side == 'LONG' %}badge-long{% else %}badge-short{% endif %}">
                                {{ s.side }}
                            </span>
                        </td>
                        <td>
                            <span class="badge {% if s.status == 'OPEN' %}badge-open{% else %}badge-closed{% endif %}">
                                {{ s.status }}
                            </span>
                        </td>
                        <td>
                            <span class="badge
                                {% if s.signal_group == 'PUMP' %}badge-pump
                                {% elif s.signal_group == 'DIP' %}badge-dip
                                {% else %}badge-new{% endif %}">
                                {{ s.signal_group }}
                            </span>
                        </td>
                        <td>{{ s.entry_type or '-' }}</td>
                        <td>
                            <span class="badge
                                {% if s.quality == 'A' %}badge-a
                                {% elif s.quality == 'B' %}badge-b
                                {% else %}badge-c{% endif %}">
                                {{ s.quality or '-' }}
                            </span>
                        </td>
                        <td class="{% if s.score and s.score >= 85 %}green{% elif s.score and s.score >= 70 %}yellow{% else %}red{% endif %}">
                            {{ s.score if s.score is not none else '-' }}
                        </td>

                        <td>
                            {% if s.risk_level == 'DELIST' %}
                                <span class="badge badge-risk-delist">🔴 DELIST</span>
                            {% elif s.risk_level == 'RISK' %}
                                <span class="badge badge-risk-risk">🟡 RISK</span>
                            {% elif s.risk_level == 'SAFE' %}
                                <span class="badge badge-risk-safe">🟢 SAFE</span>
                            {% else %}
                                -
                            {% endif %}
                        </td>
                        <td>{{ s.risk_score if s.risk_score is not none else '-' }}</td>
                        <td class="left">{{ s.risk_reasons or '-' }}</td>

                        <td>{{ s.ema_set or '-' }}</td>
                        <td>{{ '%.6f'|format(s.entry) if s.entry is not none else '-' }}</td>
                        <td>{{ '%.6f'|format(s.exit) if s.exit is not none else '-' }}</td>
                        <td class="{% if s.pnl is not none and s.pnl > 0 %}green{% elif s.pnl is not none and s.pnl < 0 %}red{% else %}yellow{% endif %}">
                            {{ '%.2f'|format(s.pnl) if s.pnl is not none else '-' }}
                        </td>
                        <td class="green">{{ '%.2f'|format(s.max_profit) if s.max_profit is not none else '-' }}</td>
                        <td>{{ '%.2f'|format(s.rsi_monthly) if s.rsi_monthly is not none else '-' }}</td>
                        <td>{{ '%.2f'|format(s.rsi_weekly) if s.rsi_weekly is not none else '-' }}</td>
                        <td>{{ '%.2f'|format(s.rsi_daily) if s.rsi_daily is not none else '-' }}</td>
                        <td>{{ '%.2f'|format(s.rsi_4h) if s.rsi_4h is not none else '-' }}</td>
                        <td class="{% if s.change_1h is not none and s.change_1h > 0 %}green{% elif s.change_1h is not none and s.change_1h < 0 %}red{% else %}yellow{% endif %}">
                            {{ '%.2f'|format(s.change_1h) if s.change_1h is not none else '-' }}
                        </td>
                        <td class="{% if s.change_4h is not none and s.change_4h > 0 %}green{% elif s.change_4h is not none and s.change_4h < 0 %}red{% else %}yellow{% endif %}">
                            {{ '%.2f'|format(s.change_4h) if s.change_4h is not none else '-' }}
                        </td>
                        <td class="left">{{ s.entry_reason or '-' }}</td>
                        <td class="left">{{ s.exit_reason or '-' }}</td>
                        <td>{{ s.cooldown_until.strftime('%Y-%m-%d %H:%M') if s.cooldown_until else '-' }}</td>
                        <td>{{ s.created_at.strftime('%Y-%m-%d %H:%M') if s.created_at else '-' }}</td>
                        <td>{{ s.exit_time.strftime('%Y-%m-%d %H:%M') if s.exit_time else '-' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <div class="mobile-cards">
        {% for s in signals %}
        <div class="signal-card">
            <div class="top">
                <div>
                    <div class="symbol">{{ s.symbol }}</div>
                    <div class="muted">{{ s.created_at.strftime('%Y-%m-%d %H:%M') if s.created_at else '-' }}</div>
                </div>
                <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end;">
                    <span class="badge {% if s.side == 'LONG' %}badge-long{% else %}badge-short{% endif %}">{{ s.side }}</span>
                    <span class="badge {% if s.status == 'OPEN' %}badge-open{% else %}badge-closed{% endif %}">{{ s.status }}</span>
                </div>
            </div>

            <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px;">
                <span class="badge {% if s.signal_group == 'PUMP' %}badge-pump{% elif s.signal_group == 'DIP' %}badge-dip{% else %}badge-new{% endif %}">
                    {{ s.signal_group }}
                </span>
                <span class="badge {% if s.quality == 'A' %}badge-a{% elif s.quality == 'B' %}badge-b{% else %}badge-c{% endif %}">
                    {{ s.quality or '-' }}
                </span>
                <span class="badge badge-closed">{{ s.entry_type or '-' }}</span>

                {% if s.risk_level == 'DELIST' %}
                    <span class="badge badge-risk-delist">🔴 DELIST</span>
                {% elif s.risk_level == 'RISK' %}
                    <span class="badge badge-risk-risk">🟡 RISK</span>
                {% elif s.risk_level == 'SAFE' %}
                    <span class="badge badge-risk-safe">🟢 SAFE</span>
                {% endif %}
            </div>

            <div class="signal-grid">
                <div><div class="k">Score</div><div>{{ s.score if s.score is not none else '-' }}</div></div>
                <div><div class="k">Risk Score</div><div>{{ s.risk_score if s.risk_score is not none else '-' }}</div></div>
                <div><div class="k">EMA</div><div>{{ s.ema_set or '-' }}</div></div>
                <div><div class="k">Entry</div><div>{{ '%.6f'|format(s.entry) if s.entry is not none else '-' }}</div></div>
                <div><div class="k">Exit</div><div>{{ '%.6f'|format(s.exit) if s.exit is not none else '-' }}</div></div>
                <div><div class="k">PnL</div><div class="{% if s.pnl is not none and s.pnl > 0 %}green{% elif s.pnl is not none and s.pnl < 0 %}red{% else %}yellow{% endif %}">{{ '%.2f'|format(s.pnl) if s.pnl is not none else '-' }}</div></div>
                <div><div class="k">Max Profit</div><div class="green">{{ '%.2f'|format(s.max_profit) if s.max_profit is not none else '-' }}</div></div>
                <div><div class="k">1H %</div><div>{{ '%.2f'|format(s.change_1h) if s.change_1h is not none else '-' }}</div></div>
                <div><div class="k">4H %</div><div>{{ '%.2f'|format(s.change_4h) if s.change_4h is not none else '-' }}</div></div>
                <div><div class="k">RSI 4H</div><div>{{ '%.2f'|format(s.rsi_4h) if s.rsi_4h is not none else '-' }}</div></div>
                <div><div class="k">Cooldown</div><div>{{ s.cooldown_until.strftime('%m-%d %H:%M') if s.cooldown_until else '-' }}</div></div>
            </div>

            <div style="margin-top:10px; font-size:12px;">
                <div><span class="muted">Risk Notes:</span> {{ s.risk_reasons or '-' }}</div>
                <div><span class="muted">Entry Reason:</span> {{ s.entry_reason or '-' }}</div>
                <div><span class="muted">Exit Reason:</span> {{ s.exit_reason or '-' }}</div>
            </div>
        </div>
        {% endfor %}
    </div>

</div>
</body>
</html>
"""

def parse_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


@app.route("/")
def index():
    db = SessionLocal()
    try:
        query = db.query(Signal)

        symbol = request.args.get("symbol", "").strip()
        side = request.args.get("side", "").strip()
        status = request.args.get("status", "").strip()
        signal_group = request.args.get("signal_group", "").strip()
        entry_type = request.args.get("entry_type", "").strip()
        quality = request.args.get("quality", "").strip()
        risk_level = request.args.get("risk_level", "").strip()
        min_score = parse_float(request.args.get("min_score", "").strip())

        if symbol:
            query = query.filter(Signal.symbol.ilike(f"%{symbol}%"))
        if side:
            query = query.filter(Signal.side == side)
        if status:
            query = query.filter(Signal.status == status)
        if signal_group:
            query = query.filter(Signal.signal_group == signal_group)
        if entry_type:
            query = query.filter(Signal.entry_type == entry_type)
        if quality:
            query = query.filter(Signal.quality == quality)
        if risk_level:
            query = query.filter(Signal.risk_level == risk_level)
        if min_score is not None:
            query = query.filter(Signal.score >= min_score)

        signals = query.order_by(desc(Signal.id)).limit(300).all()

        total = len(signals)
        open_count = len([s for s in signals if s.status == "OPEN"])
        closed_count = len([s for s in signals if s.status == "CLOSED"])
        wins = len([s for s in signals if s.status == "CLOSED" and s.pnl is not None and s.pnl > 0])
        losses = len([s for s in signals if s.status == "CLOSED" and s.pnl is not None and s.pnl < 0])

        long_count = len([s for s in signals if s.side == "LONG"])
        short_count = len([s for s in signals if s.side == "SHORT"])
        cross_count = len([s for s in signals if s.entry_type == "cross"])
        bounce_count = len([s for s in signals if s.entry_type == "bounce"])

        pnl_values = [s.pnl for s in signals if s.status == "CLOSED" and s.pnl is not None]
        total_pnl = round(sum(pnl_values), 2) if pnl_values else 0.0
        avg_pnl = round(total_pnl / len(pnl_values), 2) if pnl_values else 0.0
        win_rate = round((wins / closed_count) * 100, 2) if closed_count else 0.0

        stats = {
            "total": total,
            "open_count": open_count,
            "closed_count": closed_count,
            "wins": wins,
            "losses": losses,
            "long_count": long_count,
            "short_count": short_count,
            "cross_count": cross_count,
            "bounce_count": bounce_count,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "win_rate": win_rate,
        }

        filters = {
            "symbol": symbol,
            "side": side,
            "status": status,
            "signal_group": signal_group,
            "entry_type": entry_type,
            "quality": quality,
            "risk_level": risk_level,
            "min_score": request.args.get("min_score", "").strip(),
        }

        return render_template_string(
            HTML,
            signals=signals,
            stats=stats,
            filters=filters,
        )
    finally:
        db.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
