import os
import time
from datetime import datetime, timedelta, timezone

import ccxt
import pandas as pd
import requests
from sqlalchemy import desc

from risk_engine import BinanceRiskEngine
from storage import SessionLocal, Signal

# =========================
# CONFIG
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "120"))
TIMEFRAME = os.getenv("TIMEFRAME", "15m")
SCAN_LIMIT = int(os.getenv("SCAN_LIMIT", "800"))
CANDLE_LIMIT = int(os.getenv("CANDLE_LIMIT", "220"))

EMA_FAST = int(os.getenv("PUMP_EMA_FAST", "8"))
EMA_MID = int(os.getenv("PUMP_EMA_MID", "18"))
EMA_TREND = int(os.getenv("PUMP_EMA_TREND", "34"))

ENABLE_PUMP_LONG = os.getenv("ENABLE_PUMP_LONG", "true").strip().lower() == "true"
ENABLE_PUMP_SHORT = os.getenv("ENABLE_PUMP_SHORT", "true").strip().lower() == "true"

# Yeni: cross ve bounce ayrı kontrol
ENABLE_CROSS_LONG = os.getenv("ENABLE_CROSS_LONG", "true").strip().lower() == "true"
ENABLE_CROSS_SHORT = os.getenv("ENABLE_CROSS_SHORT", "true").strip().lower() == "true"
ENABLE_BOUNCE_LONG = os.getenv("ENABLE_BOUNCE_LONG", "true").strip().lower() == "true"
ENABLE_BOUNCE_SHORT = os.getenv("ENABLE_BOUNCE_SHORT", "true").strip().lower() == "true"

# Universe thresholds
MIN_DIP_QUOTEVOL24H = float(os.getenv("MIN_QUOTE_VOLUME_24H", "10000000"))     # 10M
MIN_NEW_QUOTEVOL24H = float(os.getenv("MIN_NEW_QUOTE_VOLUME_24H", "1000000"))  # 1M

# RSI thresholds
RSI_MONTH_MAX = float(os.getenv("RSI_MONTH_MAX", "10"))
RSI_WEEK_MAX = float(os.getenv("RSI_WEEK_MAX", "20"))
RSI_DAY_MAX = float(os.getenv("RSI_DAY_MAX", "50"))
RSI_4H_MAX = float(os.getenv("RSI_4H_MAX", "50"))

# Volume signal thresholds
MIN_VOL_RATIO = float(os.getenv("MIN_VOL_RATIO", "1.3"))
CROSS_MIN_VOL_RATIO = float(os.getenv("CROSS_MIN_VOL_RATIO", str(MIN_VOL_RATIO)))   # cross daha erken
PUMP_MIN_VOL_RATIO = float(os.getenv("PUMP_MIN_VOL_RATIO", "1.5"))                  # bounce daha sıkı
STRONG_VOL_RATIO = float(os.getenv("STRONG_VOL_RATIO", "3.0"))

SIGNAL_COOLDOWN_MINUTES = int(os.getenv("SIGNAL_COOLDOWN_MINUTES", "30"))

EXCLUDED_SYMBOLS = {
    s.strip().upper()
    for s in os.getenv(
        "EXCLUDED_SYMBOLS",
        "BTCUSDT,ETHUSDT,XRPUSDT,SOLUSDT,BNBUSDT,USDCUSDT,FDUSDUSDT",
    ).split(",")
    if s.strip()
}

exchange = ccxt.binance({
    "options": {"defaultType": "future"},
    "enableRateLimit": True,
})


# =========================
# TIME
# =========================
def utc_now_naive() -> datetime:
    return datetime.utcnow()


# =========================
# TELEGRAM
# =========================
def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram ayarlı değil.", flush=True)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}

    try:
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        print("Telegram hatası:", e, flush=True)


# =========================
# HELPERS
# =========================
def normalize_symbol(symbol: str) -> str:
    s = symbol.upper().strip()

    if ":" in s:
        s = s.split(":")[0]

    s = s.replace("/", "")
    return s


def extract_base_asset_from_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    if normalized.endswith("USDT"):
        return normalized[:-4]
    return normalized


def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()


def add_ema_set(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = calculate_ema(out, EMA_FAST)
    out["ema_mid"] = calculate_ema(out, EMA_MID)
    out["ema_trend"] = calculate_ema(out, EMA_TREND)
    return out


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def fetch_ohlcv_df(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )


def get_quote_volume_24h(ticker: dict) -> float:
    try:
        return float(ticker.get("quoteVolume") or ticker.get("baseVolumeQuote") or 0.0)
    except Exception:
        return 0.0


def pct_change(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return ((b - a) / a) * 100.0


def get_usdt_futures_symbols():
    markets = exchange.load_markets()
    symbols = []

    for symbol, market in markets.items():
        try:
            if market.get("quote") != "USDT":
                continue
            if market.get("type") != "swap":
                continue

            normalized = normalize_symbol(symbol)
            if normalized in EXCLUDED_SYMBOLS:
                continue

            if any(x in normalized for x in ["UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT"]):
                continue

            active = market.get("active", True)
            info = market.get("info") or {}
            status = str(info.get("status") or "").upper()

            if active is False:
                continue
            if status and status != "TRADING":
                continue

            symbols.append(symbol)
        except Exception:
            pass

    print(f"Toplam uygun USDT futures coin: {len(symbols)}", flush=True)
    return symbols


def crosses_above(prev_fast, prev_mid, curr_fast, curr_mid) -> bool:
    return prev_fast <= prev_mid and curr_fast > curr_mid


def crosses_below(prev_fast, prev_mid, curr_fast, curr_mid) -> bool:
    return prev_fast >= prev_mid and curr_fast < curr_mid


def get_closed_rows(df: pd.DataFrame):
    if len(df) < 3:
        return None, None
    return df.iloc[-3], df.iloc[-2]


def calc_quote_candle_vol(row) -> float:
    return float(row["close"]) * float(row["volume"])


def calc_avg_quote_vol_last_10_closed(df: pd.DataFrame) -> float:
    if len(df) < 13:
        return 0.0
    recent = df.iloc[-12:-2].copy()
    if recent.empty:
        return 0.0
    return float((recent["close"] * recent["volume"]).mean())


# =========================
# MULTI-TF METRICS / UNIVERSE
# =========================
def build_timeframe_metrics(symbol: str):
    metrics = {
        "rsi_monthly": None,
        "rsi_weekly": None,
        "rsi_daily": None,
        "rsi_4h": None,
        "change_1h": None,
        "change_4h": None,
        "is_new_coin": False,
    }

    try:
        df_1M = fetch_ohlcv_df(symbol, "1M", 40)
        if len(df_1M) >= 20:
            metrics["rsi_monthly"] = float(calculate_rsi(df_1M["close"]).iloc[-1])
    except Exception:
        pass

    try:
        df_1W = fetch_ohlcv_df(symbol, "1w", 40)
        if len(df_1W) >= 20:
            metrics["rsi_weekly"] = float(calculate_rsi(df_1W["close"]).iloc[-1])
    except Exception:
        pass

    try:
        df_1D = fetch_ohlcv_df(symbol, "1d", 60)
        if len(df_1D) >= 20:
            metrics["rsi_daily"] = float(calculate_rsi(df_1D["close"]).iloc[-1])
    except Exception:
        pass

    try:
        df_4h = fetch_ohlcv_df(symbol, "4h", 80)
        if len(df_4h) >= 20:
            metrics["rsi_4h"] = float(calculate_rsi(df_4h["close"]).iloc[-1])
    except Exception:
        pass

    if metrics["rsi_monthly"] is None and metrics["rsi_weekly"] is None:
        metrics["is_new_coin"] = True

    try:
        df_1h = fetch_ohlcv_df(symbol, "1h", 10)
        if len(df_1h) >= 5:
            metrics["change_1h"] = float(
                pct_change(float(df_1h.iloc[-2]["close"]), float(df_1h.iloc[-1]["close"]))
            )
            metrics["change_4h"] = float(
                pct_change(float(df_1h.iloc[-5]["close"]), float(df_1h.iloc[-1]["close"]))
            )
    except Exception:
        pass

    return metrics


def classify_signal_group(metrics: dict, quote_vol_24h: float) -> str:
    rsi_m = metrics.get("rsi_monthly")
    rsi_w = metrics.get("rsi_weekly")
    rsi_d = metrics.get("rsi_daily")
    rsi_4h = metrics.get("rsi_4h")
    is_new = metrics.get("is_new_coin", False)

    if is_new and quote_vol_24h >= MIN_NEW_QUOTEVOL24H:
        return "NEW"

    if (
        quote_vol_24h >= MIN_DIP_QUOTEVOL24H
        and rsi_m is not None and rsi_m <= RSI_MONTH_MAX
        and rsi_w is not None and rsi_w <= RSI_WEEK_MAX
        and rsi_d is not None and rsi_d <= RSI_DAY_MAX
        and rsi_4h is not None and rsi_4h <= RSI_4H_MAX
    ):
        return "DIP"

    return "OTHER"


# =========================
# SCORE / QUALITY
# =========================
def get_signal_score(signal_group: str, vol_ratio: float, metrics: dict) -> float:
    score = 50.0

    if signal_group == "NEW":
        score += 20
    elif signal_group == "DIP":
        score += 15

    if vol_ratio >= STRONG_VOL_RATIO:
        score += 20
    elif vol_ratio >= PUMP_MIN_VOL_RATIO:
        score += 12
    elif vol_ratio >= MIN_VOL_RATIO:
        score += 6

    ch1 = metrics.get("change_1h") or 0.0
    ch4 = metrics.get("change_4h") or 0.0

    score += min(max(ch1, 0.0), 5.0)
    score += min(max(ch4, 0.0), 9.0)

    return round(min(score, 99.0), 2)


def get_quality(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    return "C"


# =========================
# DB
# =========================
def get_last_signal(db, symbol: str, side: str):
    return (
        db.query(Signal)
        .filter(Signal.symbol == symbol, Signal.side == side)
        .order_by(desc(Signal.id))
        .first()
    )


def in_cooldown(last_signal: Signal | None) -> bool:
    if not last_signal or not last_signal.cooldown_until:
        return False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now < last_signal.cooldown_until


def has_open_signal(db, symbol: str, side: str) -> bool:
    row = (
        db.query(Signal)
        .filter(
            Signal.symbol == symbol,
            Signal.side == side,
            Signal.status == "OPEN",
        )
        .first()
    )
    return row is not None


def create_signal(
    db,
    symbol: str,
    side: str,
    signal_group: str,
    entry_type: str,
    entry_price: float,
    score: float,
    quality: str,
    metrics: dict,
    entry_reason: str,
    risk_level: str | None = None,
    risk_score: float | None = None,
    risk_reasons: str | None = None,
):
    cooldown_until = utc_now_naive() + timedelta(minutes=SIGNAL_COOLDOWN_MINUTES)

    row = Signal(
        symbol=symbol,
        side=side,
        signal_group=signal_group,
        entry_type=entry_type,
        entry=entry_price,
        exit=None,
        status="OPEN",
        pnl=0.0,
        max_profit=0.0,
        score=score,
        quality=quality,
        rsi_monthly=metrics.get("rsi_monthly"),
        rsi_weekly=metrics.get("rsi_weekly"),
        rsi_daily=metrics.get("rsi_daily"),
        rsi_4h=metrics.get("rsi_4h"),
        change_1h=metrics.get("change_1h"),
        change_4h=metrics.get("change_4h"),
        ema_set=f"{EMA_FAST}/{EMA_MID}/{EMA_TREND}",
        entry_reason=entry_reason,
        exit_reason=None,
        cooldown_until=cooldown_until,
        created_at=utc_now_naive(),
        exit_time=None,
        risk_level=risk_level,
        risk_score=risk_score,
        risk_reasons=risk_reasons,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_open_trade_metrics(db, signal: Signal, current_price: float):
    if signal.side == "LONG":
        pnl = ((current_price - signal.entry) / signal.entry) * 100.0
    else:
        pnl = ((signal.entry - current_price) / signal.entry) * 100.0

    signal.pnl = round(pnl, 2)
    signal.max_profit = round(max(signal.max_profit or 0.0, pnl), 2)
    db.commit()


def close_trade(db, signal: Signal, exit_price: float, reason: str):
    if signal.side == "LONG":
        pnl = ((exit_price - signal.entry) / signal.entry) * 100.0
    else:
        pnl = ((signal.entry - exit_price) / signal.entry) * 100.0

    signal.exit = exit_price
    signal.exit_time = utc_now_naive()
    signal.status = "CLOSED"
    signal.pnl = round(pnl, 2)
    signal.exit_reason = reason
    signal.max_profit = round(signal.max_profit or 0.0, 2)
    db.commit()


# =========================
# TELEGRAM FORMAT
# =========================
def send_entry_alert(row: Signal, vol_ratio: float):
    strength = "STRONG" if vol_ratio >= STRONG_VOL_RATIO else "NORMAL"
    msg = (
        f"🚀 {row.side} SIGNAL\n"
        f"Coin: {row.symbol}\n"
        f"Group: {row.signal_group}\n"
        f"Type: {row.entry_type}\n"
        f"Strength: {strength}\n"
        f"Entry: {row.entry:.6f}\n"
        f"EMA: {row.ema_set}\n"
        f"VolRatio: {vol_ratio:.2f}\n"
        f"Score: {row.score} | Quality: {row.quality}\n"
        f"Risk: {row.risk_level or '-'} ({row.risk_score if row.risk_score is not None else '-'})\n"
        f"Reason: {row.entry_reason}"
    )
    send_telegram_message(msg)


def send_exit_alert(row: Signal):
    msg = (
        f"🛑 {row.side} EXIT\n"
        f"Coin: {row.symbol}\n"
        f"Exit: {row.exit:.6f}\n"
        f"PnL: {row.pnl:.2f}%\n"
        f"Reason: {row.exit_reason}"
    )
    send_telegram_message(msg)


# =========================
# ENTRY / EXIT LOGIC
# =========================
def long_cross_entry(df: pd.DataFrame) -> bool:
    prev_row, last_row = get_closed_rows(df)
    if prev_row is None:
        return False

    return (
        crosses_above(
            prev_row["ema_fast"],
            prev_row["ema_mid"],
            last_row["ema_fast"],
            last_row["ema_mid"],
        )
        and last_row["ema_mid"] > last_row["ema_trend"]
        and last_row["close"] > last_row["ema_mid"]
    )


def long_bounce_entry(df: pd.DataFrame) -> bool:
    if len(df) < 5:
        return False

    c = df.iloc[-3]
    d = df.iloc[-2]

    return (
        d["ema_mid"] > d["ema_trend"]
        and d["close"] > d["ema_mid"]
        and c["low"] <= c["ema_mid"] * 1.003
        and c["close"] >= c["ema_mid"]
        and d["ema_fast"] > c["ema_fast"]
        and d["close"] > c["high"]
    )


def short_cross_entry(df: pd.DataFrame) -> bool:
    prev_row, last_row = get_closed_rows(df)
    if prev_row is None:
        return False

    return (
        crosses_below(
            prev_row["ema_fast"],
            prev_row["ema_mid"],
            last_row["ema_fast"],
            last_row["ema_mid"],
        )
        and last_row["ema_mid"] < last_row["ema_trend"]
        and last_row["close"] < last_row["ema_mid"]
    )


def short_bounce_entry(df: pd.DataFrame) -> bool:
    if len(df) < 5:
        return False

    c = df.iloc[-3]
    d = df.iloc[-2]

    return (
        d["ema_mid"] < d["ema_trend"]
        and d["close"] < d["ema_mid"]
        and c["high"] >= c["ema_mid"] * 0.997
        and c["close"] <= c["ema_mid"]
        and d["ema_fast"] < c["ema_fast"]
        and d["close"] < c["low"]
    )


def should_exit_long(df: pd.DataFrame) -> bool:
    _, last_row = get_closed_rows(df)
    if last_row is None:
        return False
    return last_row["close"] < last_row["ema_mid"]


def should_exit_short(df: pd.DataFrame) -> bool:
    _, last_row = get_closed_rows(df)
    if last_row is None:
        return False
    return last_row["close"] > last_row["ema_mid"]


# =========================
# RISK
# =========================
def build_risk_maps_safe():
    try:
        risk_engine = BinanceRiskEngine()
        symbol_risk_map = risk_engine.build_risk_map()

        base_asset_risk_map = {}
        for sym, risk in symbol_risk_map.items():
            base_asset = getattr(risk, "base_asset", None)
            if base_asset:
                base_asset_risk_map[base_asset.upper()] = risk

        print(
            f"Risk map hazır: symbol={len(symbol_risk_map)} | base_asset={len(base_asset_risk_map)}",
            flush=True,
        )
        return symbol_risk_map, base_asset_risk_map

    except Exception as e:
        print(f"Risk engine hatası: {e}", flush=True)
        return {}, {}


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


# =========================
# MAIN SCAN
# =========================
def scan_once():
    db = SessionLocal()
    try:
        symbol_risk_map, base_asset_risk_map = build_risk_maps_safe()
        symbols = get_usdt_futures_symbols()
        tickers = exchange.fetch_tickers()

        if SCAN_LIMIT > 0:
            symbols = symbols[:SCAN_LIMIT]

        print(f"Taranacak coin sayısı: {len(symbols)}", flush=True)

        for symbol in symbols:
            try:
                normalized_symbol = normalize_symbol(symbol)
                base_asset = extract_base_asset_from_symbol(symbol)
                risk = resolve_risk(symbol, symbol_risk_map, base_asset_risk_map)

                if risk:
                    print(
                        f"[RISK MATCH] {symbol} -> {normalized_symbol} | base={base_asset} | "
                        f"{risk.risk_level} | score={risk.risk_score} | reasons={risk.reasons}",
                        flush=True,
                    )
                else:
                    print(
                        f"[RISK DEFAULT] {symbol} -> {normalized_symbol} | base={base_asset} | no risk match",
                        flush=True,
                    )

                if risk and risk.spot_delist_flag:
                    print(f"[SKIP DELIST] {normalized_symbol}", flush=True)
                    continue

                ticker = tickers.get(symbol) or {}
                quote_vol_24h = get_quote_volume_24h(ticker)

                if quote_vol_24h < MIN_NEW_QUOTEVOL24H:
                    continue

                metrics = build_timeframe_metrics(symbol)
                signal_group = classify_signal_group(metrics, quote_vol_24h)

                if signal_group == "OTHER":
                    continue

                df = fetch_ohlcv_df(symbol, TIMEFRAME, CANDLE_LIMIT)
                if len(df) < 50:
                    continue

                df = add_ema_set(df)
                _, last_closed = get_closed_rows(df)
                if last_closed is None:
                    continue

                current_price = float(last_closed["close"])

                cross_candle_vol = calc_quote_candle_vol(last_closed)
                avg_qv_10 = calc_avg_quote_vol_last_10_closed(df)
                vol_ratio = (cross_candle_vol / avg_qv_10) if avg_qv_10 > 0 else 0.0

                if vol_ratio < MIN_VOL_RATIO:
                    continue

                score = get_signal_score(signal_group, vol_ratio, metrics)
                quality = get_quality(score)

                if risk:
                    risk_level = risk.risk_level
                    risk_score = float(risk.risk_score) if risk.risk_score is not None else 0.0
                    risk_reasons = " | ".join(risk.reasons) if risk.reasons else "Matched risk map"
                else:
                    risk_level = "SAFE"
                    risk_score = 0.0
                    risk_reasons = "No risk map match; default SAFE"

                open_rows = (
                    db.query(Signal)
                    .filter(Signal.symbol == symbol, Signal.status == "OPEN")
                    .all()
                )

                for row in open_rows:
                    update_open_trade_metrics(db, row, current_price)

                    if row.side == "LONG" and should_exit_long(df):
                        close_trade(db, row, current_price, "Price closed below EMA18")
                        send_exit_alert(row)

                    elif row.side == "SHORT" and should_exit_short(df):
                        close_trade(db, row, current_price, "Price closed above EMA18")
                        send_exit_alert(row)

                # ================= LONG ENTRY =================
                last_long = get_last_signal(db, symbol, "LONG")
                can_open_long = (not in_cooldown(last_long)) and (not has_open_signal(db, symbol, "LONG"))

                if ENABLE_PUMP_LONG and can_open_long:
                    if ENABLE_CROSS_LONG and vol_ratio >= CROSS_MIN_VOL_RATIO and long_cross_entry(df):
                        row = create_signal(
                            db=db,
                            symbol=symbol,
                            side="LONG",
                            signal_group=signal_group,
                            entry_type="cross",
                            entry_price=current_price,
                            score=score,
                            quality=quality,
                            metrics=metrics,
                            entry_reason="ema8_cross_above_ema18",
                            risk_level=risk_level,
                            risk_score=risk_score,
                            risk_reasons=risk_reasons,
                        )
                        print(
                            f"LONG CROSS: {symbol} | score={score} | group={signal_group} | "
                            f"vr={vol_ratio:.2f} | risk={risk_level}",
                            flush=True,
                        )
                        send_entry_alert(row, vol_ratio)

                    elif ENABLE_BOUNCE_LONG and vol_ratio >= PUMP_MIN_VOL_RATIO and long_bounce_entry(df):
                        row = create_signal(
                            db=db,
                            symbol=symbol,
                            side="LONG",
                            signal_group=signal_group,
                            entry_type="bounce",
                            entry_price=current_price,
                            score=score,
                            quality=quality,
                            metrics=metrics,
                            entry_reason="ema18_bounce_long",
                            risk_level=risk_level,
                            risk_score=risk_score,
                            risk_reasons=risk_reasons,
                        )
                        print(
                            f"LONG BOUNCE: {symbol} | score={score} | group={signal_group} | "
                            f"vr={vol_ratio:.2f} | risk={risk_level}",
                            flush=True,
                        )
                        send_entry_alert(row, vol_ratio)

                # ================= SHORT ENTRY =================
                last_short = get_last_signal(db, symbol, "SHORT")
                can_open_short = (not in_cooldown(last_short)) and (not has_open_signal(db, symbol, "SHORT"))

                if ENABLE_PUMP_SHORT and can_open_short:
                    if ENABLE_CROSS_SHORT and vol_ratio >= CROSS_MIN_VOL_RATIO and short_cross_entry(df):
                        row = create_signal(
                            db=db,
                            symbol=symbol,
                            side="SHORT",
                            signal_group=signal_group,
                            entry_type="cross",
                            entry_price=current_price,
                            score=score,
                            quality=quality,
                            metrics=metrics,
                            entry_reason="ema8_cross_below_ema18",
                            risk_level=risk_level,
                            risk_score=risk_score,
                            risk_reasons=risk_reasons,
                        )
                        print(
                            f"SHORT CROSS: {symbol} | score={score} | group={signal_group} | "
                            f"vr={vol_ratio:.2f} | risk={risk_level}",
                            flush=True,
                        )
                        send_entry_alert(row, vol_ratio)

                    elif ENABLE_BOUNCE_SHORT and vol_ratio >= PUMP_MIN_VOL_RATIO and short_bounce_entry(df):
                        row = create_signal(
                            db=db,
                            symbol=symbol,
                            side="SHORT",
                            signal_group=signal_group,
                            entry_type="bounce",
                            entry_price=current_price,
                            score=score,
                            quality=quality,
                            metrics=metrics,
                            entry_reason="ema18_bounce_short",
                            risk_level=risk_level,
                            risk_score=risk_score,
                            risk_reasons=risk_reasons,
                        )
                        print(
                            f"SHORT BOUNCE: {symbol} | score={score} | group={signal_group} | "
                            f"vr={vol_ratio:.2f} | risk={risk_level}",
                            flush=True,
                        )
                        send_entry_alert(row, vol_ratio)

                time.sleep(0.03)

            except Exception as e:
                print(f"Hata {symbol}: {e}", flush=True)

    finally:
        db.close()


if __name__ == "__main__":
    print("v2 final worker başladı...", flush=True)
    send_telegram_message("🚀 v2 final worker started")

    while True:
        try:
            scan_once()
        except Exception as e:
            print("Genel worker hatası:", e, flush=True)

        print(f"{SLEEP_SECONDS} saniye bekleniyor...", flush=True)
        time.sleep(SLEEP_SECONDS)
