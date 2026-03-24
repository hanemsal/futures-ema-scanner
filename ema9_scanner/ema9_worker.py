import time
import ccxt
import pandas as pd

from config import *
from storage import save_signal, get_open_position
from telegram_bot import send_telegram


exchange = getattr(ccxt, EXCHANGE_ID)({
    "enableRateLimit": True,
    "options": {"defaultType": "future"}
})


def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def rsi(series, length=14):

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def scan_symbol(symbol):

    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
    except Exception as e:
        print("OHLCV error:", symbol, e)
        return

    df = pd.DataFrame(
        ohlcv,
        columns=["time","open","high","low","close","volume"]
    )

    df["ema3"] = ema(df["close"], EMA_FAST)
    df["ema9"] = ema(df["close"], EMA_SLOW)

    df["rsi"] = rsi(df["close"], RSI_LENGTH)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = last["close"]

    ema3 = last["ema3"]
    ema9 = last["ema9"]

    prev_ema3 = prev["ema3"]
    prev_ema9 = prev["ema9"]

    rsi_val = last["rsi"]

    try:
        ticker = exchange.fetch_ticker(symbol)
        vol = ticker["quoteVolume"]
    except:
        return

    if vol < MIN_VOLUME:
        return

    pos = get_open_position(symbol)

    # LONG ENTRY
    if prev_ema3 <= prev_ema9 and ema3 > ema9 and rsi_val > RSI_LONG_THRESHOLD:

        if pos != "LONG":

            save_signal(symbol,"LONG",price)

            send_telegram(
                f"🟢 EMA9 LONG\n"
                f"Coin: {symbol}\n"
                f"TF: {TIMEFRAME}\n"
                f"Version: {VERSION}\n"
                f"Entry: {price}\n"
                f"RSI: {round(rsi_val,2)}\n"
                f"24h Vol: {round(vol/1e6,2)}M\n"
                f"Lev: x{LEVERAGE}"
            )

    # LONG EXIT
    if pos == "LONG" and prev_ema3 >= prev_ema9 and ema3 < ema9:

        save_signal(symbol,"EXIT",price)

        send_telegram(
            f"✅ EMA9 LONG EXIT\n"
            f"{symbol}\n"
            f"Version: {VERSION}\n"
            f"Exit: {price}"
        )

    # SHORT ENTRY
    if prev_ema3 >= prev_ema9 and ema3 < ema9:

        if pos != "SHORT":

            save_signal(symbol,"SHORT",price)

            send_telegram(
                f"🔴 EMA9 SHORT\n"
                f"Coin: {symbol}\n"
                f"TF: {TIMEFRAME}\n"
                f"Version: {VERSION}\n"
                f"Entry: {price}\n"
                f"RSI: {round(rsi_val,2)}\n"
                f"24h Vol: {round(vol/1e6,2)}M\n"
                f"Lev: x{LEVERAGE}"
            )

    # SHORT EXIT
    if pos == "SHORT" and prev_ema3 <= prev_ema9 and ema3 > ema9:

        save_signal(symbol,"EXIT",price)

        send_telegram(
            f"✅ EMA9 SHORT EXIT\n"
            f"{symbol}\n"
            f"Version: {VERSION}\n"
            f"Exit: {price}"
        )


def get_symbols():

    markets = exchange.load_markets()

    symbols = []

    for s in markets:

        if "/USDT" in s and markets[s]["contract"]:
            symbols.append(s)

    return symbols


def run():

    print("Loading markets...")

    symbols = get_symbols()

    print("Symbols loaded:", len(symbols))

    while True:

        for symbol in symbols:

            scan_symbol(symbol)

            time.sleep(SYMBOL_SLEEP)

        print("scan cycle complete")

        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    run()
