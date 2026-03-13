def check_long_entry(df):

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # EMA11 yukarı kesmiş mi
    cross_47 = prev["ema11"] <= prev["ema47"] and curr["ema11"] > curr["ema47"]
    cross_123 = prev["ema11"] <= prev["ema123"] and curr["ema11"] > curr["ema123"]

    if cross_47 and cross_123:
        return True

    # backup kural
    if curr["ema11"] > curr["ema47"] and curr["ema11"] > curr["ema123"]:
        return True

    return False


def check_long_exit(df):

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # EMA11 aşağı keserse
    cross_down = prev["ema11"] >= prev["ema47"] and curr["ema11"] < curr["ema47"]

    if cross_down:
        return True

    # fiyat ema47 altına düşerse
    if curr["close"] < curr["ema47"]:
        return True

    return False
