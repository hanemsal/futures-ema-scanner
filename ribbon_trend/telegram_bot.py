from __future__ import annotations

import requests

from config import LEVERAGE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED, TIMEFRAME
from utils import setup_logger

logger = setup_logger("ribbon.telegram")


class TelegramNotifier:
    def __init__(self) -> None:
        self.enabled = TELEGRAM_ENABLED
        self.url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage" if self.enabled else ""

    def _send(self, text: str) -> None:
        if not self.enabled:
            return
        try:
            requests.post(
                self.url,
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
                timeout=15,
            ).raise_for_status()
        except Exception as exc:
            logger.exception("Telegram send failed: %s", exc)

    def send_signal(self, trade_id: int, signal, tp_price: float, sl_price: float) -> None:
        emoji = "🟢" if signal.side == "long" else "🔴"
        text = (
            f"{emoji} <b>RIBBON {signal.side.upper()}</b>\n"
            f"Coin: <b>{signal.symbol}</b>\n"
            f"TF: {TIMEFRAME}\n"
            f"Trade ID: {trade_id}\n"
            f"Entry: {signal.entry_price:.8f}\n"
            f"TP: {tp_price:.8f}\n"
            f"SL: {sl_price:.8f}\n"
            f"Lev: x{LEVERAGE:g}\n"
            f"EMA200 slope: {signal.ema200_slope_pct:.4f}%\n"
            f"Extension: {signal.extension_pct:.2f}%"
        )
        self._send(text)

    def send_exit(self, trade: dict) -> None:
        emoji = "✅" if trade.get("result") == "tp" else "⛔"
        text = (
            f"{emoji} <b>RIBBON EXIT</b>\n"
            f"Coin: <b>{trade['symbol']}</b>\n"
            f"Side: {trade['side'].upper()}\n"
            f"Result: {str(trade.get('result', '')).upper()}\n"
            f"Exit: {float(trade.get('exit_price') or 0):.8f}\n"
            f"PnL: {float(trade.get('pnl_pct') or 0):.2f}%\n"
            f"ROI: {float(trade.get('roi_pct') or 0):.2f}%"
        )
        self._send(text)
