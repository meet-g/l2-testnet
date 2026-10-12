"""Base class and common types for L2 alpha signals."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time
from typing import Any, Dict, Optional

from core.orderbook import OrderBook
from core.trade_stream import TradeManager


@dataclass
class SignalResult:
    name: str
    score: float  # Normalized direction & conviction: range [-1.0, 1.0]. Positive = Bullish, Negative = Bearish
    raw_value: float  # Unbounded or underlying natural metric
    confidence: float  # Confidence level [0.0, 1.0]
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_bullish(self) -> bool:
        return self.score > 0.0

    @property
    def is_bearish(self) -> bool:
        return self.score < 0.0


class BaseSignal(ABC):
    """Abstract base class for all market microstructure alpha signals."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        """Computes the signal given the current L2 book and trade state."""
        pass
