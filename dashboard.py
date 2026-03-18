from flask import Flask, render_template_string, request, Response
from sqlalchemy import desc
from io import StringIO
import csv

from storage import SessionLocal, Signal

app = Flask(__name__)

# 🔥 HTML (SADECE BUTON EKLENDİ)
HTML = """ 
""" + """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>Pump Hunter Dashboard</title>
</head>
<body>

<form method="get">
    <input name="symbol" placeholder="Coin ara" value="{{ filters.symbol }}">

    <select name="side">
        <option value="">Side</option>
        <option value="LONG" {% if filters.side=='LONG' %}selected{% endif %}>LONG</option>
        <option value="SHORT" {% if filters.side=='SHORT' %}selected{% endif %}>SHORT</option>
    </select>

    <select name="status">
        <option value="">Status</option>
        <option value="OPEN" {% if filters.status=='OPEN' %}selected{% endif %}>OPEN</option>
        <option value="CLOSED" {% if filters.status=='CLOSED' %}selected{% endif %}>CLOSED</option>
    </select>

    <select name="risk_level">
        <option value="">Risk</option>
        <option value="SAFE" {% if filters.risk_level=='SAFE' %}selected{% endif %}>SAFE</option>
        <option value="RISK" {% if filters.risk_level=='RISK' %}selected{% endif %}>RISK</option>
        <option value="DELIST" {% if filters.risk_level=='DELIST' %}selected{% endif %}>DELIST</option>
    </select>

    <input name="min_score" placeholder="Min score" value="{{ filters.min_score }}">

    <button type="submit">Filtrele</button>

    <a href="/">Sıfırla</a>

    <!-- 🔥 CSV BUTON -->
    <button type="button" onclick="downloadCSV()">CSV İndir</button>
</form>

<table border="1">
<tr>
<th>ID</th><th>Coin</th><th>Side</th><th>Status</th>
<th>Score</th><th>Risk</th><th>PnL</th>
</tr>

{% for s in signals %}
<tr>
<td>{{ s.id }}</td>
<td>{{ s.symbol }}</td>
<td>{{ s.side }}</td>
<td>{{ s.status }}</td>
<td>{{ s.score }}</td>
<td>{{ s.risk_level }}</td>
<td>{{ s.pnl }}</td>
</tr>
{% endfor %}

</table>

<script>
function downloadCSV() {
    const params = new URLSearchParams(window.location.search);
    window.open("/export_csv?" + params.toString(), "_blank");
}
</script>

</body>
</html>
"""


def parse_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except:
        return None


@app.route("/")
def index():
    db = SessionLocal()
    try:
        query = db.query(Signal)

        symbol = request.args.get("symbol", "").strip()
        side = request.args.get("side", "").strip()
        status = request.args.get("status", "").strip()
        risk_level = request.args.get("risk_level", "").strip()
        min_score = parse_float(request.args.get("min_score", ""))

        if symbol:
            query = query.filter(Signal.symbol.ilike(f"%{symbol}%"))
        if side:
            query = query.filter(Signal.side == side)
        if status:
            query = query.filter(Signal.status == status)
        if risk_level:
            query = query.filter(Signal.risk_level == risk_level)
        if min_score is not None:
            query = query.filter(Signal.score >= min_score)

        signals = query.order_by(desc(Signal.id)).limit(300).all()

        return render_template_string(
            HTML,
            signals=signals,
            filters={
                "symbol": symbol,
                "side": side,
                "status": status,
                "risk_level": risk_level,
                "min_score": request.args.get("min_score", ""),
            },
        )
    finally:
        db.close()


# 🔥 CSV EXPORT (FİLTREYLE AYNI)
@app.route("/export_csv")
def export_csv():
    db = SessionLocal()
    try:
        query = db.query(Signal)

        symbol = request.args.get("symbol", "").strip()
        side = request.args.get("side", "").strip()
        status = request.args.get("status", "").strip()
        risk_level = request.args.get("risk_level", "").strip()
        min_score = parse_float(request.args.get("min_score", ""))

        if symbol:
            query = query.filter(Signal.symbol.ilike(f"%{symbol}%"))
        if side:
            query = query.filter(Signal.side == side)
        if status:
            query = query.filter(Signal.status == status)
        if risk_level:
            query = query.filter(Signal.risk_level == risk_level)
        if min_score is not None:
            query = query.filter(Signal.score >= min_score)

        rows = query.order_by(desc(Signal.id)).all()

        si = StringIO()
        writer = csv.writer(si)

        writer.writerow([
            "ID","Coin","Side","Status","Score",
            "Risk","Risk Score","PnL","Entry","Exit"
        ])

        for r in rows:
            writer.writerow([
                r.id, r.symbol, r.side, r.status, r.score,
                r.risk_level, r.risk_score,
                r.pnl, r.entry, r.exit
            ])

        return Response(
            si.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=trades.csv"}
        )
    finally:
        db.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
