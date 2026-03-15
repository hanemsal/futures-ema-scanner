import pandas as pd


def calculate_ema(df: pd.DataFrame, period: int):
    return df["close"].ewm(span=period, adjust=False).mean()


def add_ema_set(df: pd.DataFrame, fast: int, mid: int, trend: int) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = calculate_ema(out, fast)
    out["ema_mid"] = calculate_ema(out, mid)
    out["ema_trend"] = calculate_ema(out, trend)
    return out


def add_legacy_ema_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Geriye dönük uyumluluk için eski kolonlar da dursun.
    Dashboard veya eski analizlerde lazım olabilir.
    """
    out = df.copy()
    out["ema11"] = calculate_ema(out, 11)
    out["ema29"] = calculate_ema(out, 29)
    out["ema47"] = calculate_ema(out, 47)
    out["ema123"] = calculate_ema(out, 123)
    return out
