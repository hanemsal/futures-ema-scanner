from dataclasses import dataclass
from typing import Optional


@dataclass
class TradeRecord:
    id: Optional[int]
    symbol: str
    side: str
    status: str
    timeframe: str
    leverage: float
    entry_price: float
    tp_price: float
    sl_price: float
    exit_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    roi_pct: Optional[float] = None
    result: Optional[str] = None
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    signal_candle_time: Optional[str] = None
    reason: Optional[str] = None
