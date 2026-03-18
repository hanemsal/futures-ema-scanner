from risk_engine import BinanceRiskEngine
from storage import SessionLocal, Signal


def normalize_symbol(symbol: str) -> str:
    s = (symbol or "").upper().strip()
    if ":" in s:
        s = s.split(":")[0]
    return s.replace("/", "")


def extract_base_asset_from_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    if normalized.endswith("USDT"):
        return normalized[:-4]
    return normalized


def build_maps():
    engine = BinanceRiskEngine()
    symbol_risk_map = engine.build_risk_map()

    base_asset_risk_map = {}
    for sym, risk in symbol_risk_map.items():
        base_asset = getattr(risk, "base_asset", None)
        if base_asset:
            base_asset_risk_map[base_asset.upper()] = risk

    return symbol_risk_map, base_asset_risk_map


def resolve_risk(symbol: str, symbol_risk_map: dict, base_asset_risk_map: dict):
    normalized_symbol = normalize_symbol(symbol)
    base_asset = extract_base_asset_from_symbol(symbol)

    risk = symbol_risk_map.get(normalized_symbol)
    if risk:
        return risk

    risk = base_asset_risk_map.get(base_asset)
    if risk:
        return risk

    return None


def main():
    db = SessionLocal()
    try:
        symbol_risk_map, base_asset_risk_map = build_maps()
        rows = db.query(Signal).all()

        updated = 0

        for row in rows:
            risk = resolve_risk(row.symbol, symbol_risk_map, base_asset_risk_map)

            if risk:
                row.risk_level = risk.risk_level
                row.risk_score = float(risk.risk_score) if risk.risk_score is not None else 0.0
                row.risk_reasons = " | ".join(risk.reasons) if risk.reasons else "Matched risk map"
            else:
                row.risk_level = "SAFE"
                row.risk_score = 0.0
                row.risk_reasons = "No risk map match; backfilled default SAFE"

            updated += 1

        db.commit()
        print(f"Backfill tamamlandı. Güncellenen kayıt: {updated}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
