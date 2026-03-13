def check_short_entry(df):

    if len(df) < 2:
        return False

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # EMA11, EMA123'ü yukarıdan aşağı kesiyor
    cross_down = prev["ema11"] >= prev["ema123"] and curr["ema11"] < curr["ema123"]

    if cross_down:
        return True

    return False


def check_short_exit(df):

    if len(df) < 2:
        return False

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # EMA11 aşağıdan yukarı EMA29 keserse
    cross_up = prev["ema11"] <= prev["ema29"] and curr["ema11"] > curr["ema29"]

    if cross_up:
        return True

    # fiyat EMA29 üstüne çıkarsa
    if curr["close"] > curr["ema29"]:
        return True

    return False
