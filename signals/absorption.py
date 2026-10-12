"""Cumulative Volume Delta (CVD) Absorption and Divergence Signal."""

from collections import deque
import math
from typing import Deque, Optional, Tuple

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult


class AbsorptionSignal(BaseSignal):
    """Detects Limit Order Absorption and CVD-Price Divergences.
    
    Microstructure Mechanism:
    - Bullish Absorption:
        Massive aggressive market selling (CVD deeply negative), but price fails to drop
        or bounces. Indicates strong institutional passive limit buyers absorbing all flow.
        High-probability bullish reversal edge.
    - Bearish Absorption:
        Heavy aggressive market buying (CVD strongly positive), but price fails to rise
        and gets capped. Indicates passive iceberg/resting limit sellers.
        High-probability bearish reversal edge.
    - CVD Momentum:
        Aggressive flow pushing in the same direction as price expansion through thin depth.
    """

    def __init__(
        self,
        name: str = "Absorption",
        window_secs: float = 20.0,
        divergence_ratio_thresh: float = 2.0,
    ):
        super().__init__(name)
        self.window_secs = window_secs
        self.divergence_ratio_thresh = divergence_ratio_thresh
        self.price_history: Deque[Tuple[int, float]] = deque(maxlen=200)

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        now_ms = timestamp_ms or book.last_update_time_ms
        mid = book.mid_price
        self.price_history.append((now_ms, mid))

        # Need at least 5 seconds of trade history
        cvd, buy_vol, sell_vol = trades.get_cvd_in_window(self.window_secs)
        total_vol = buy_vol + sell_vol
        if total_vol < 0.5:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.1)

        # Calculate price delta over the window
        cutoff_ms = now_ms - int(self.window_secs * 1000)
        old_prices = [p for t, p in self.price_history if t <= cutoff_ms]
        old_price = old_prices[-1] if old_prices else self.price_history[0][1]
        price_delta_bps = ((mid - old_price) / max(old_price, 1.0)) * 10000.0

        # Normalized CVD ratio: [-1.0, 1.0]
        cvd_ratio = cvd / total_vol

        score = 0.0
        pattern = "NEUTRAL"

        # Check for Absorption Divergences:
        # Case 1: Heavy selling, but price is flat or up -> Bullish Absorption
        if cvd_ratio < -0.4 and price_delta_bps >= -0.5:
            absorption_intensity = abs(cvd_ratio) * (1.0 + max(0.0, price_delta_bps))
            score = min(1.0, absorption_intensity)
            pattern = "BULLISH_ABSORPTION"

        # Case 2: Heavy buying, but price is flat or down -> Bearish Absorption
        elif cvd_ratio > 0.4 and price_delta_bps <= 0.5:
            absorption_intensity = cvd_ratio * (1.0 + max(0.0, -price_delta_bps))
            score = -min(1.0, absorption_intensity)
            pattern = "BEARISH_ABSORPTION"

        # Case 3: Momentum continuation (Flow and price move in harmony)
        elif abs(cvd_ratio) > 0.5 and abs(price_delta_bps) > 1.5:
            if cvd_ratio > 0 and price_delta_bps > 0:
                score = min(0.8, cvd_ratio)
                pattern = "BULLISH_MOMENTUM"
            elif cvd_ratio < 0 and price_delta_bps < 0:
                score = max(-0.8, cvd_ratio)
                pattern = "BEARISH_MOMENTUM"

        confidence = min(1.0, total_vol / 5.0)

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=cvd_ratio,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "pattern": pattern,
                "cvd_btc": cvd,
                "total_vol_btc": total_vol,
                "cvd_ratio": cvd_ratio,
                "price_delta_bps": price_delta_bps,
            },
        )
