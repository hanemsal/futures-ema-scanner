def check_short_entry(df):
    """
    Short entry:
    EMA11, EMA123'ü yukarıdan aşağı KAPANMIŞ mumda keserse.
    Son açık mum kullanılmaz.
    """
    if len(df) < 3:
        return False

    prev_closed = df.iloc[-3]
    last_closed = df.iloc[-2]

    cross_down_123 = (
        prev_closed["ema11"] >= prev_closed["ema123"]
        and last_closed["ema11"] < last_closed["ema123"]
    )

    return cross_down_123


def check_short_exit(df):
    """
    Short exit:
    1) Ana kural: EMA11, EMA29'u aşağıdan yukarı KAPANMIŞ mumda keserse
    2) Yedek kural: son kapanmış mumda EMA11, EMA29 üstüne çıkmışsa
    """
    if len(df) < 3:
        return False

    prev_closed = df.iloc[-3]
    last_closed = df.iloc[-2]

    cross_up_29 = (
        prev_closed["ema11"] <= prev_closed["ema29"]
        and last_closed["ema11"] > last_closed["ema29"]
    )

    if cross_up_29:
        return True

    if last_closed["ema11"] > last_closed["ema29"]:
        return True

    return False
