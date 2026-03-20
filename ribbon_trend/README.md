# Ribbon Trend System

Ayrı çalışan Binance Futures 15m ribbon trend test sistemi.

## Kurulum

```bash
cd ribbon_trend_system
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Önemli

Varsayılan olarak `RIBBON_DRY_RUN=true` gelir. Bu durumda trade DB'ye açılmaz, sadece log üretir.
Gerçek kayıt için önce ortam değişkenini kapat:

```bash
export RIBBON_DRY_RUN=false
```

## Gerekli Telegram ayarları

```bash
export RIBBON_TELEGRAM_BOT_TOKEN=...
export RIBBON_TELEGRAM_CHAT_ID=...
```

## Worker çalıştırma

```bash
python worker.py
```

## Dashboard çalıştırma

```bash
python dashboard.py
```

## Sistem mantığı
- Long: close > EMA200, EMA200 slope up, EMA20 > EMA50 > EMA100 > EMA200, green candle
- Short: close < EMA200, EMA200 slope down, EMA20 < EMA50 < EMA100 < EMA200, red candle
- TP: %2 price move
- SL: %2 price move
- Leverage: x5 (ROI hesap için)
