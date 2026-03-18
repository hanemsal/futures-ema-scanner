import re
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set

import requests
from bs4 import BeautifulSoup


BINANCE_SPOT_24HR_URL = "https://api.binance.com/api/v3/ticker/24hr"
BINANCE_FUTURES_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
BINANCE_ANNOUNCEMENT_DELIST_URL = "https://www.binance.com/en/support/announcement/list/161"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class CoinRisk:
    symbol: str
    base_asset: str
    risk_score: int
    risk_level: str
    reasons: List[str]
    price_change_percent: Optional[float] = None
    quote_volume: Optional[float] = None
    spot_delist_flag: bool = False
    futures_delist_flag: bool = False
    futures_missing_flag: bool = False


class BinanceRiskEngine:
    def __init__(
        self,
        crash_threshold_pct: float = -15.0,
        low_volume_usdt: float = 10_000_000,
        announcement_timeout: int = 12,
        market_timeout: int = 12,
    ):
        self.crash_threshold_pct = crash_threshold_pct
        self.low_volume_usdt = low_volume_usdt
        self.announcement_timeout = announcement_timeout
        self.market_timeout = market_timeout

    # -----------------------------
    # Public API
    # -----------------------------
    def build_risk_map(self) -> Dict[str, CoinRisk]:
        """
        Returns:
            {
              "HOOKUSDT": CoinRisk(...),
              "LRCUSDT": CoinRisk(...),
              ...
            }
        """
        spot_24h = self._get_spot_24h_stats()
        spot_delist_assets = self._get_spot_delist_assets_from_announcements()
        futures_symbols = self._get_futures_symbols()

        risk_map: Dict[str, CoinRisk] = {}

        for row in spot_24h:
            symbol = row.get("symbol", "")
            if not symbol.endswith("USDT"):
                continue

            base_asset = symbol[:-4]
            price_change_percent = self._safe_float(row.get("priceChangePercent"))
            quote_volume = self._safe_float(row.get("quoteVolume"))

            score = 0
            reasons: List[str] = []
            spot_delist_flag = False
            futures_delist_flag = False
            futures_missing_flag = False

            # 1) Official delist announcement match
            if base_asset in spot_delist_assets:
                score += 100
                spot_delist_flag = True
                reasons.append("Official Binance delist announcement match")

            # 2) Crash filter
            if price_change_percent is not None and price_change_percent <= self.crash_threshold_pct:
                score += 30
                reasons.append(f"24h crash: {price_change_percent:.2f}%")

            # 3) Low volume filter
            if quote_volume is not None and quote_volume < self.low_volume_usdt:
                score += 20
                reasons.append(f"Low 24h quote volume: {quote_volume:,.0f} USDT")

            # 4) Futures existence / missing signal
            #    Not every spot coin must have futures, so this is only a mild warning.
            futures_symbol = symbol
            if futures_symbol not in futures_symbols:
                score += 10
                futures_missing_flag = True
                reasons.append("No active USDT-M futures symbol found")

            # Level mapping
            level = self._map_level(score)

            risk_map[symbol] = CoinRisk(
                symbol=symbol,
                base_asset=base_asset,
                risk_score=score,
                risk_level=level,
                reasons=reasons,
                price_change_percent=price_change_percent,
                quote_volume=quote_volume,
                spot_delist_flag=spot_delist_flag,
                futures_delist_flag=futures_delist_flag,
                futures_missing_flag=futures_missing_flag,
            )

        return risk_map

    # -----------------------------
    # Fetchers
    # -----------------------------
    def _get_spot_24h_stats(self) -> List[dict]:
        r = requests.get(
            BINANCE_SPOT_24HR_URL,
            headers=HEADERS,
            timeout=self.market_timeout,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected /api/v3/ticker/24hr response format")
        return data

    def _get_futures_symbols(self) -> Set[str]:
        """
        Active USDⓈ-M futures symbols from official exchangeInfo.
        """
        r = requests.get(
            BINANCE_FUTURES_EXCHANGE_INFO_URL,
            headers=HEADERS,
            timeout=self.market_timeout,
        )
        r.raise_for_status()
        data = r.json()
        symbols = set()

        for item in data.get("symbols", []):
            symbol = item.get("symbol")
            status = item.get("status")
            contract_type = item.get("contractType")
            if symbol and status == "TRADING" and contract_type == "PERPETUAL":
                symbols.add(symbol)

        return symbols

    def _get_spot_delist_assets_from_announcements(self) -> Set[str]:
        """
        Scrapes Binance Delisting announcement page and extracts base assets from titles like:
        'Binance Will Delist A2Z, FORTH, HOOK, IDEX, LRC, NTRN, RDNT, SXP on 2026-04-01'
        """
        r = requests.get(
            BINANCE_ANNOUNCEMENT_DELIST_URL,
            headers=HEADERS,
            timeout=self.announcement_timeout,
        )
        r.raise_for_status()

        html = r.text
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        assets: Set[str] = set()

        # Main pattern: Binance Will Delist A2Z, FORTH, HOOK...
        patterns = [
            r"Binance Will Delist ([A-Z0-9,\s]+?) on \d{4}-\d{2}-\d{2}",
            r"Binance Will Delist ([A-Z0-9,\s]+?)\b",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                blob = match.group(1)
                for token in blob.split(","):
                    asset = token.strip().upper()
                    if self._looks_like_asset(asset):
                        assets.add(asset)

        return assets

    # -----------------------------
    # Helpers
    # -----------------------------
    @staticmethod
    def _safe_float(v) -> Optional[float]:
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _looks_like_asset(token: str) -> bool:
        if not token:
            return False
        if len(token) > 15:
            return False
        return re.fullmatch(r"[A-Z0-9]{2,15}", token) is not None

    @staticmethod
    def _map_level(score: int) -> str:
        if score >= 80:
            return "DELIST"
        if score >= 40:
            return "RISK"
        return "SAFE"


if __name__ == "__main__":
    engine = BinanceRiskEngine()
    risk_map = engine.build_risk_map()

    # Top risky USDT pairs
    rows = sorted(
        (asdict(v) for v in risk_map.values()),
        key=lambda x: (-x["risk_score"], x["symbol"])
    )

    for row in rows[:50]:
        print(
            f'{row["symbol"]:12} | {row["risk_level"]:6} | '
            f'score={row["risk_score"]:3} | '
            f'24h={row["price_change_percent"]} | '
            f'vol={row["quote_volume"]} | '
            f'reasons={"; ".join(row["reasons"])}'
        )
