import pandas as pd

def calculate_ema(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()

def add_ema_indicators(df):

    df["ema11"] = calculate_ema(df, 11)
    df["ema29"] = calculate_ema(df, 29)
    df["ema47"] = calculate_ema(df, 47)
    df["ema123"] = calculate_ema(df, 123)

    return df
