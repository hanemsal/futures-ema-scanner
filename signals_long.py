def check_long_entry(df):
    """
    Long entry:
    EMA11, EMA123'ü aşağıdan yukarı KAPANMIŞ mumda keserse.
    Son açık mum kullanılmaz.
    """
    if len(df) < 3:
        return False

    prev_closed = df.iloc[-3]
    last_closed = df.iloc[-2]

    cross_up_123 = (
        prev_closed["ema11"] <= prev_closed["ema123"]
        and last_closed["ema11"] > last_closed["ema123"]
    )

    return cross_up_123


def check_long_exit(df):
    """
    Long exit:
    EMA11, EMA47'yi yukarıdan aşağı KAPANMIŞ mumda keserse.
    Son açık mum kullanılmaz.
    """
    if len(df) < 3:
        return False

    prev_closed = df.iloc[-3]
    last_closed = df.iloc[-2]

    cross_down_47 = (
        prev_closed["ema11"] >= prev_closed["ema47"]
        and last_closed["ema11"] < last_closed["ema47"]
    )

    return cross_down_47
