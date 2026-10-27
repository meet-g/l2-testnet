"""Volume-Synchronized Probability of Toxicity (VPIN) Signal (Easley, Lopez de Prado, O'Hara)."""

from typing import Optional, Tuple

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult


class VPINSignal(BaseSignal):
    """Volume-Synchronized Probability of Toxicity (VPIN).
    
    Reference:
        Easley, D., Lopez de Prado, M. M., & O'Hara, M. (2012).
        "Flow Toxicity and Liquidity in a High-Frequency World", The Review of Financial Studies.
        
    Mechanism:
        Quantifies the arrival rate of informed trades versus uninformed liquidity.
        Measures volume imbalance over fixed-volume buckets.
        Surges in VPIN precede aggressive price discovery, volatility breakouts, and maker wipeouts.
    """

    def __init__(
        self,
        name: str = "VPIN",
        n_buckets: int = 20,
        toxic_threshold: float = 0.60,
    ):
        super().__init__(name)
        self.n_buckets = n_buckets
        self.toxic_threshold = toxic_threshold
        # Cache state
        self._cached_bucket_key: Tuple[int, int] = (-1, -1)
        self._cached_res: Optional[Tuple[float, float, float, float, bool, float]] = None

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        now_ms = timestamp_ms or book.last_update_time_ms
        n_completed = len(trades.completed_buckets)

        if n_completed < 3:
            # Need minimum completed volume buckets
            return SignalResult(
                name=self.name,
                score=0.0,
                raw_value=0.0,
                confidence=0.1,
                timestamp_ms=now_ms,
                metadata={"buckets_ready": n_completed},
            )

        last_bucket_idx = trades.completed_buckets[-1].bucket_idx
        bucket_key = (n_completed, last_bucket_idx)

        if bucket_key != self._cached_bucket_key or self._cached_res is None:
            n = min(self.n_buckets, n_completed)
            recent_buckets = list(trades.completed_buckets)[-n:]

            total_abs_imbalance = sum(b.abs_imbalance for b in recent_buckets)
            total_signed_imbalance = sum(b.buy_vol - b.sell_vol for b in recent_buckets)
            total_vol = sum(b.total_vol for b in recent_buckets)

            if total_vol <= 0:
                return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0, timestamp_ms=now_ms)

            vpin_toxicity = total_abs_imbalance / total_vol  # Range [0.0, 1.0]
            signed_ratio = total_signed_imbalance / total_vol  # Range [-1.0, 1.0]

            # Score is directional toxicity: sign indicates flow direction, magnitude scaled by VPIN intensity
            score = signed_ratio * min(1.0, (vpin_toxicity / self.toxic_threshold))
            score = max(-1.0, min(1.0, score))

            confidence = min(1.0, n_completed / float(self.n_buckets))
            is_toxic = vpin_toxicity >= self.toxic_threshold

            self._cached_bucket_key = bucket_key
            self._cached_res = (score, vpin_toxicity, confidence, signed_ratio, is_toxic, total_vol)

        score, vpin_toxicity, confidence, signed_ratio, is_toxic, total_vol = self._cached_res

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=vpin_toxicity,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "vpin_toxicity": vpin_toxicity,
                "signed_ratio": signed_ratio,
                "is_toxic": is_toxic,
                "completed_buckets": n_completed,
                "total_volume_btc": total_vol,
            },
        )
