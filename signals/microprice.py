"""Stoikov Micro-Price Estimator and Fair-Value Drift Signal."""

import math
from typing import Optional

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult


class MicroPriceSignal(BaseSignal):
    """Stoikov (2018) Micro-Price Fair Value Estimator.
    
    Reference:
        Stoikov, S. (2018). "The Micro-Price: A High-Frequency Estimator of Future Prices",
        Quantitative Finance.
        
    Mathematical Formulation:
        Mid-price M = (P_a + P_b) / 2
        Spread S = P_a - P_b
        Imbalance I = (Q_b - Q_a) / (Q_b + Q_a)
        
        Weighted Mid-Price:
            P_w = P_b * (Q_a / (Q_b + Q_a)) + P_a * (Q_b / (Q_b + Q_a))
                = M + (S / 2) * I
                
        Stoikov's Micro-Price incorporates imbalance persistence:
            P_micro = M + (S / 2) * g(I)
            where g(I) = sign(I) * |I|^gamma (adjusting for non-linear state transition probability)
            
        Alpha metric:
            Delta = (P_micro - M) / (S / 2)  in [-1.0, 1.0]
    """

    def __init__(
        self,
        name: str = "MicroPrice",
        gamma_nonlinearity: float = 0.85,  # Sub-linear transition adjustment
        spread_scale_bps: float = 1.0,
    ):
        super().__init__(name)
        self.gamma = gamma_nonlinearity
        self.spread_scale_bps = spread_scale_bps

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        mid = book.mid_price
        spread = book.spread
        qb = book.best_bid_sz
        qa = book.best_ask_sz

        total_q = qb + qa
        if total_q <= 0 or spread <= 0:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        # Standard imbalance
        imbalance = (qb - qa) / total_q

        # Non-linear probability adjustment g(I)
        sign = 1.0 if imbalance >= 0 else -1.0
        g_imb = sign * (abs(imbalance) ** self.gamma)

        # Stoikov micro-price
        half_spread = spread / 2.0
        p_micro = mid + (half_spread * g_imb)

        # Drift difference in dollars
        micro_drift = p_micro - mid

        # Normalized drift score [-1.0, 1.0]
        score = max(-1.0, min(1.0, g_imb))

        # Confidence: higher when top-of-book depth is thick and spread is 1 tick
        confidence = min(1.0, (total_q / 2.0) * (1.0 / max(spread, 1.0)))

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=micro_drift,
            confidence=confidence,
            timestamp_ms=timestamp_ms or book.last_update_time_ms,
            metadata={
                "mid_price": mid,
                "micro_price": p_micro,
                "spread": spread,
                "spread_bps": book.spread_bps,
                "imbalance": imbalance,
                "micro_drift_usd": micro_drift,
            },
        )
