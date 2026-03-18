import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import ccxt
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk_engine import BinanceRiskEngine
from storage import SessionLocal, Signal

TIMEFRAME = os.getenv("TIMEFRAME", "15m")
LOOKBACK_CANDLES = int(os.getenv("BACKFILL_LOOKBACK_CANDLES", "40"))
ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")

exchange = ccxt.binance({
    "options": {"defaultType": "future"},
    "enableRateLimit": True,
})


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


def set_optional_attr(obj, name: str, value):
    if hasattr(obj, name):
        setattr(obj, name, value)


def classify_candle_type(body_ratio: float) -> str:
    if body_ratio >= 0.6:
        return "strong"
    if body_ratio >= 0.4:
        return "medium"
    return "weak"


def compute_body_ratio(row: pd.Series) -> float:
    candle_size = float(row["high"]) - float(row["low"])
    if candle_size <= 0:
        return 0.0
    body_size = abs(float(row["close"]) - float(row["open"]))
    return body_size / candle_size


def naive_istanbul_to_utc_ms(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    aware = dt.replace(tzinfo=ISTANBUL_TZ)
    return int(aware.astimezone(ZoneInfo("UTC")).timestamp() * 1000)


def fetch_context_df(symbol: str, target_ms: int | None) -> pd.DataFrame | None:
    if target_ms is None:
        return None

    try:
        tf_ms = exchange.parse_timeframe(TIMEFRAME) * 1000
        since = max(target_ms - (LOOKBACK_CANDLES * tf_ms), 0)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, since=since, limit=LOOKBACK_CANDLES)
        if not ohlcv:
            return None
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        if df.empty:
            return None
        df["quote_vol"] = df["close"] * df["volume"]
        return df
    except Exception:
        return None


def locate_candle_index(df: pd.DataFrame | None, target_ms: int | None) -> int | None:
    if df is None or df.empty or target_ms is None:
        return None

    eligible = df.index[df["timestamp"] <= target_ms].tolist()
    if not eligible:
        return None
    return int(eligible[-1])


def compute_ratios_for_time(symbol: str, target_dt: datetime | None):
    target_ms = naive_istanbul_to_utc_ms(target_dt)
    df = fetch_context_df(symbol, target_ms)
    idx = locate_candle_index(df, target_ms)

    if df is None or idx is None:
        return None, None, None

    row = df.iloc[idx]
    body_ratio = round(compute_body_ratio(row), 4)

    start_idx = max(0, idx - 20)
    prev = df.iloc[start_idx:idx]
    if prev.empty:
        vol_ratio = 1.0
    else:
        avg_quote_vol = float(prev["quote_vol"].mean())
        current_quote_vol = float(row["quote_vol"])
        vol_ratio = round(current_quote_vol / avg_quote_vol, 4) if avg_quote_vol > 0 else 1.0

    candle_type = classify_candle_type(body_ratio)
    return vol_ratio, body_ratio, candle_type


def main():
    db = SessionLocal()
    try:
        symbol_risk_map, base_asset_risk_map = build_maps()
        rows = db.query(Signal).all()

        updated = 0
        analytics_updated = 0

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

            entry_vol_ratio, entry_body_ratio, candle_type = compute_ratios_for_time(row.symbol, getattr(row, "created_at", None))
            exit_vol_ratio, exit_body_ratio, _ = compute_ratios_for_time(row.symbol, getattr(row, "exit_time", None))

            if entry_vol_ratio is not None:
                set_optional_attr(row, "vol_ratio_entry", entry_vol_ratio)
                analytics_updated += 1
            if entry_body_ratio is not None:
                set_optional_attr(row, "body_ratio_entry", entry_body_ratio)
            if candle_type is not None:
                set_optional_attr(row, "candle_type", candle_type)

            if exit_vol_ratio is not None:
                set_optional_attr(row, "vol_ratio_exit", exit_vol_ratio)
            if exit_body_ratio is not None:
                set_optional_attr(row, "body_ratio_exit", exit_body_ratio)

            updated += 1

        db.commit()
        print(f"Risk backfill tamamlandı. Güncellenen kayıt: {updated}")
        print(f"Analytics alanı doldurulan kayıt sayısı: {analytics_updated}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
