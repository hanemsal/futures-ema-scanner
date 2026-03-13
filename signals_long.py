def check_long_entry(df):

    # güvenlik
    if len(df) < 2:
        return False

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # EMA11, EMA123'ü aşağıdan yukarı kesiyor
    cross_up = prev["ema11"] <= prev["ema123"] and curr["ema11"] > curr["ema123"]

    if cross_up:
        return True

    return False


def check_long_exit(df):

    if len(df) < 2:
        return False

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # EMA11 yukarıdan aşağı EMA47 kesiyor
    cross_down = prev["ema11"] >= prev["ema47"] and curr["ema11"] < curr["ema47"]

    if cross_down:
        return True

    return False
