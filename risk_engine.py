import re
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
        Returns a symbol keyed map such as:
        {
          "HOOKUSDT": CoinRisk(...),
          "LRCUSDT": CoinRisk(...),
        }
        """
        spot_24h = self._get_spot_24h_stats()
        spot_delist_assets = self._get_spot_delist_assets_from_announcements()
        futures_symbols = self._get_futures_symbols()

        risk_map: Dict[str, CoinRisk] = {}

        for row in spot_24h:
            symbol = str(row.get("symbol") or "").upper()
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

            # 1) Official Binance delist announcement
            if base_asset in spot_delist_assets:
                score += 100
                spot_delist_flag = True
                futures_delist_flag = True
                reasons.append("Official Binance delist announcement match")

            # 2) Futures universe control
            # Our system only trades Binance USDT perpetual futures.
            # If the symbol is not present in active futures, it must stay out.
            if symbol not in futures_symbols:
                score += 80
                futures_missing_flag = True
                futures_delist_flag = True
                reasons.append("No active Binance USDT perpetual futures symbol found")

            # 3) Dead / weak market filter
            if quote_volume is not None and quote_volume < self.low_volume_usdt:
                score += 20
                reasons.append(f"Low 24h quote volume: {quote_volume:,.0f} USDT")

            # 4) Abnormal dump filter
            if price_change_percent is not None and price_change_percent <= self.crash_threshold_pct:
                score += 30
                reasons.append(f"24h crash: {price_change_percent:.2f}%")

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

    def is_blocked(self, symbol: str, risk_map: Optional[Dict[str, CoinRisk]] = None) -> bool:
        """
        Convenience helper. Treat DELIST as hard block.
        """
        if risk_map is None:
            risk_map = self.build_risk_map()
        key = str(symbol or "").upper().replace("/", "")
        if ":" in key:
            key = key.split(":")[0]
        risk = risk_map.get(key)
        if not risk:
            return False
        return risk.risk_level == "DELIST"

    # -----------------------------
    # Fetchers
    # -----------------------------
    def _get_spot_24h_stats(self) -> List[dict]:
        response = requests.get(
            BINANCE_SPOT_24HR_URL,
            headers=HEADERS,
            timeout=self.market_timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected /api/v3/ticker/24hr response format")
        return data

    def _get_futures_symbols(self) -> Set[str]:
        """
        Active Binance USDⓈ-M perpetual futures symbols.
        """
        response = requests.get(
            BINANCE_FUTURES_EXCHANGE_INFO_URL,
            headers=HEADERS,
            timeout=self.market_timeout,
        )
        response.raise_for_status()
        data = response.json()

        symbols: Set[str] = set()
        for item in data.get("symbols", []):
            symbol = str(item.get("symbol") or "").upper()
            status = str(item.get("status") or "").upper()
            contract_type = str(item.get("contractType") or "").upper()
            quote_asset = str(item.get("quoteAsset") or "").upper()
            if not symbol:
                continue
            if quote_asset != "USDT":
                continue
            if status != "TRADING":
                continue
            if contract_type != "PERPETUAL":
                continue
            symbols.add(symbol)

        return symbols

    def _get_spot_delist_assets_from_announcements(self) -> Set[str]:
        """
        Scrapes the Binance announcement list and extracts base assets from
        titles such as:
        'Binance Will Delist A2Z, FORTH, HOOK, IDEX, LRC, NTRN, RDNT, SXP on 2026-04-01'
        """
        response = requests.get(
            BINANCE_ANNOUNCEMENT_DELIST_URL,
            headers=HEADERS,
            timeout=self.announcement_timeout,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        assets: Set[str] = set()
        patterns = [
            r"Binance Will Delist ([A-Z0-9,\s]+?) on \d{4}-\d{2}-\d{2}",
            r"Binance Will Delist ([A-Z0-9,\s]+?)\b",
            r"will delist ([A-Z0-9,\s]+?) on \d{4}-\d{2}-\d{2}",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
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
    def _safe_float(value) -> Optional[float]:
        try:
            return float(value)
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

    rows = sorted(
        (asdict(v) for v in risk_map.values()),
        key=lambda x: (-x["risk_score"], x["symbol"]),
    )

    for row in rows[:50]:
        print(
            f'{row["symbol"]:12} | {row["risk_level"]:6} | '
            f'score={row["risk_score"]:3} | '
            f'24h={row["price_change_percent"]} | '
            f'vol={row["quote_volume"]} | '
            f'reasons={"; ".join(row["reasons"])}'
        )
