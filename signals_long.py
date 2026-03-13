def check_long_entry(df):

    # en az 2 mum gerekli
    if len(df) < 2:
        return False

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # EMA11 yukarı kesişimleri
    cross_47 = prev["ema11"] <= prev["ema47"] and curr["ema11"] > curr["ema47"]
    cross_123 = prev["ema11"] <= prev["ema123"] and curr["ema11"] > curr["ema123"]

    # trend filtresi
    trend_ok = curr["ema47"] > curr["ema123"]

    if cross_47 and cross_123 and trend_ok:
        return True

    return False


def check_long_exit(df):

    # en az 2 mum gerekli
    if len(df) < 2:
        return False

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # EMA11 aşağı keserse
    cross_down = prev["ema11"] >= prev["ema47"] and curr["ema11"] < curr["ema47"]

    if cross_down:
        return True

    # fiyat EMA47 altına düşerse
    if curr["close"] < curr["ema47"]:
        return True

    return False
