from __future__ import annotations

import os
import requests


class TelegramNotifier:
    def __init__(self) -> None:
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.enabled = bool(self.bot_token and self.chat_id)
        self.url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage" if self.enabled else ""

    def _send(self, text: str) -> None:
        if not self.enabled:
            return
        try:
            requests.post(
                self.url,
                json={"chat_id": self.chat_id, "text": text},
                timeout=15,
            )
        except Exception as exc:
            print("Telegram send error:", exc)

    def send_signal(self, trade_id: int, payload: dict) -> None:
        version = payload.get("entry_note", "-")

        self._send(
            "\n".join(
                [
                    "🟢 EMA9 LONG" if payload["side"] == "long" else "🔴 EMA9 SHORT",
                    f"Trade ID: {trade_id}",
                    f"Coin: {payload['symbol']}",
                    f"TF: {payload['timeframe']}",
                    f"Version: {version}",
                    f"Entry: {payload['entry_price']}",
                    f"Lev: x{payload['leverage']}",
                    f"RSI: {payload.get('rsi_value', '-')}",
                    f"24h Vol: {payload.get('notional_24h_text', '-')}",
                    f"Reason: {payload['reason']}",
                ]
            )
        )

    def send_exit(self, trade: dict, close_reason: str) -> None:
        version = trade.get("entry_note", "-")

        self._send(
            "\n".join(
                [
                    "✅ EMA9 EXIT",
                    f"Coin: {trade['symbol']}",
                    f"Side: {str(trade['side']).upper()}",
                    f"Version: {version}",
                    f"Exit: {trade['exit_price']}",
                    f"PnL: {trade['pnl_pct']:.4f}%",
                    f"ROI: {trade['roi_pct']:.4f}%",
                    f"Reason: {close_reason}",
                ]
            )
        )
