def check_short_entry(df):

    if len(df) < 2:
        return False

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # EMA11, EMA123'ü yukarıdan aşağı keserse SHORT ENTRY
    cross_down_123 = prev["ema11"] >= prev["ema123"] and curr["ema11"] < curr["ema123"]

    return cross_down_123


def check_short_exit(df):

    if len(df) < 2:
        return False

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # 1️⃣ Öncelikli exit: EMA11, EMA29'u aşağıdan yukarı keserse
    cross_up_29 = prev["ema11"] <= prev["ema29"] and curr["ema11"] > curr["ema29"]

    if cross_up_29:
        return True

    # 2️⃣ Alternatif exit: fiyat EMA29 üstüne çıkarsa
    if curr["close"] > curr["ema29"]:
        return True

    return False
