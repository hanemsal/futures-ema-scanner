from flask import Flask, render_template_string, request
from storage import SessionLocal, Signal

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body { font-family: Arial; background:#0b0b0b; color:white; }

.card {
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-bottom:20px;
}

.stat {
  background:#111;
  padding:10px;
  border-radius:8px;
  flex:1;
  text-align:center;
}

.green { color:#00ff9f; }
.red { color:#ff4d4d; }
.yellow { color:#ffd700; }

table {
  width:100%;
  border-collapse:collapse;
  font-size:12px;
}

th, td {
  padding:8px;
  border-bottom:1px solid #222;
  text-align:center;
}

th { background:#111; }

tr:hover { background:#1a1a1a; }

.badge {
  padding:3px 6px;
  border-radius:4px;
  font-size:10px;
}

.long { background:#003300; }
.short { background:#330000; }

@media(max-width:768px){
  table { font-size:10px; }
}
</style>
</head>

<body>

<h2>🚀 Pump Hunter Dashboard</h2>

<form method="get">
<input name="symbol" placeholder="Coin ara">
<select name="side">
<option value="">Side</option>
<option value="LONG">LONG</option>
<option value="SHORT">SHORT</option>
</select>
<select name="status">
<option value="">Status</option>
<option value="OPEN">OPEN</option>
<option value="CLOSED">CLOSED</option>
</select>
<button type="submit">Filtrele</button>
</form>

<div class="card">
  <div class="stat">Toplam<br>{{total}}</div>
  <div class="stat green">Kazançlı<br>{{wins}}</div>
  <div class="stat red">Zararlı<br>{{loss}}</div>
  <div class="stat">Winrate<br>{{winrate}}%</div>
</div>

<table>
<tr>
<th>ID</th>
<th>Coin</th>
<th>Side</th>
<th>Group</th>
<th>Type</th>
<th>Entry</th>
<th>Exit</th>
<th>PnL</th>
<th>Max</th>
<th>Score</th>
<th>Status</th>
</tr>

{% for s in signals %}
<tr>
<td>{{s.id}}</td>
<td>{{s.symbol}}</td>
<td>
<span class="badge {{ 'long' if s.side=='LONG' else 'short' }}">
{{s.side}}
</span>
</td>
<td>{{s.signal_group}}</td>
<td>{{s.entry_type}}</td>
<td>{{s.entry}}</td>
<td>{{s.exit or '-'}}</td>

<td class="{{'green' if s.pnl and s.pnl>0 else 'red'}}">
{{s.pnl or '-'}}
</td>

<td class="green">{{s.max_profit or '-'}}</td>
<td>{{s.score}}</td>
<td>{{s.status}}</td>
</tr>
{% endfor %}

</table>

</body>
</html>
"""

@app.route("/")
def index():
    db = SessionLocal()
    query = db.query(Signal)

    symbol = request.args.get("symbol")
    side = request.args.get("side")
    status = request.args.get("status")

    if symbol:
        query = query.filter(Signal.symbol.contains(symbol))
    if side:
        query = query.filter(Signal.side == side)
    if status:
        query = query.filter(Signal.status == status)

    signals = query.order_by(Signal.id.desc()).limit(100).all()

    total = len(signals)
    wins = len([s for s in signals if s.pnl and s.pnl > 0])
    loss = len([s for s in signals if s.pnl and s.pnl < 0])

    winrate = round((wins / total * 100), 2) if total else 0

    return render_template_string(
        HTML,
        signals=signals,
        total=total,
        wins=wins,
        loss=loss,
        winrate=winrate
    )


if __name__ == "__main__":
    app.run(debug=True)
