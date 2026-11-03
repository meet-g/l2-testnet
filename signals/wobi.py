"""Multi-Level Weighted Order Book Imbalance (WOBI) Signal with Order Count Filtering."""

import math
from typing import Optional

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult


class WOBISignal(BaseSignal):
    """Multi-Tier Weighted Order Book Imbalance with Anti-Spoofing Order Count Filtering.
    
    Mathematical Formulation:
        WOBI = sum(w_k * (Q_b,k - Q_a,k)) / sum(w_k * (Q_b,k + Q_a,k))
        where w_k = exp(-lambda * k)
        
    Hyperliquid Edge Addition:
        Adjusts raw resting volume by order count density (n):
        - A dense level with n=40 participants is genuine sticky liquidity.
        - An isolated level with n=1 (single whale) is penalized for potential phantom/spoof liquidity.
    """

    def __init__(
        self,
        name: str = "WOBI",
        decay_lambda: float = 0.35,
        max_levels: int = 10,
        whale_min_sz: float = 5.0,
    ):
        super().__init__(name)
        self.decay_lambda = decay_lambda
        self.max_levels = max_levels
        self.whale_min_sz = whale_min_sz

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        n_levels = min(self.max_levels, len(book.bids), len(book.asks))
        w_bids = 0.0
        w_asks = 0.0

        bids_spoof_penalty = 0.0
        asks_spoof_penalty = 0.0

        whale_sz = self.whale_min_sz * getattr(book, "notional_scale", 1.0)
        for i in range(n_levels):
            w = math.exp(-self.decay_lambda * i)
            b_lvl = book.bids[i]
            a_lvl = book.asks[i]

            # Anti-spoofing heuristic: If a level is dominated by 1 single order of huge size, penalize weight
            b_density_factor = 1.0
            if b_lvl.sz >= whale_sz and b_lvl.n <= 2:
                b_density_factor = 0.6  # Single whale wall penalty
                bids_spoof_penalty += 0.2

            a_density_factor = 1.0
            if a_lvl.sz >= whale_sz and a_lvl.n <= 2:
                a_density_factor = 0.6  # Single whale wall penalty
                asks_spoof_penalty += 0.2

            w_bids += b_lvl.sz * w * b_density_factor
            w_asks += a_lvl.sz * w * a_density_factor

        denom = w_bids + w_asks
        if denom <= 0:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        raw_imbalance = (w_bids - w_asks) / denom  # Range [-1.0, 1.0]

        # Top of book imbalance for comparison
        tob_b = book.best_bid_sz
        tob_a = book.best_ask_sz
        tob_imbalance = (tob_b - tob_a) / max(tob_b + tob_a, 1e-8)

        # Confidence is higher when spread is tight and depth is substantial
        scale = getattr(book, "notional_scale", 1.0)
        spread_factor = max(0.2, 1.0 - (book.spread_bps / 5.0))
        depth_factor = min(1.0, denom / (2.0 * scale))
        confidence = min(1.0, spread_factor * depth_factor)

        # Normalized score
        score = max(-1.0, min(1.0, raw_imbalance))

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=raw_imbalance,
            confidence=confidence,
            timestamp_ms=timestamp_ms or book.last_update_time_ms,
            metadata={
                "wobi_5": book.depth_imbalance(5),
                "wobi_20": book.depth_imbalance(20),
                "tob_imbalance": tob_imbalance,
                "bids_spoof_penalty": bids_spoof_penalty,
                "asks_spoof_penalty": asks_spoof_penalty,
                "bid_order_count_5": sum(l.n for l in book.bids[:5]),
                "ask_order_count_5": sum(l.n for l in book.asks[:5]),
            },
        )
