"""Instant Fill (Flow Depletion & Immediate Sweep) Microstructure Alpha Signal.

Microstructure Alpha Foundation:
Prioritizes rapid execution and immediate fill probability by detecting when
the opposing Level-1 queue is severely depleted, aggressive market order flow (CVD)
is surging, and the Micro-Price fair value has drifted past the touch.

Designed specifically for ultra-fast scalping strategies (Instant_FastFill) where
entering passively at the back of the queue causes severe adverse selection,
queue delays, and unfilled alpha opportunities.
"""

from collections import deque
import math
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult


class InstantFillSignal(BaseSignal):
    """Flow Depletion, Queue Exhaustion, and Immediate Sweep Alpha Signal.
    
    Mathematical Formulation:
    1. Queue Thinning Ratio (R_thin):
       Measures the exhaustion of Level-1 depth relative to 5-level resting depth:
       R_bid = Q_b1 / (sum_{k=1}^5 Q_bk + eps)
       R_ask = Q_a1 / (sum_{k=1}^5 Q_ak + eps)
       S_thin = tanh( gamma_thin * (R_bid - R_ask) )
       When ask depth is depleted (R_ask << R_bid), the ask level is fragile.

    2. Trade Flow Acceleration & Impulse (S_flow):
       Calculates signed volume delta over short lookback (default 2.0s):
       CVD_short = sum_{t in [now-dt, now]} signed_vol(t)
       V_short   = sum_{t in [now-dt, now]} vol(t)
       S_flow    = CVD_short / max(V_short, eps) in [-1.0, 1.0]

    3. Micro-Price Dislocation (S_micro):
       P_micro = (Q_b1 * P_ask + Q_a1 * P_bid) / (Q_b1 + Q_a1 + eps)
       Dislocation = (P_micro - P_mid) / (0.5 * Spread + eps)
       S_micro = clip(Dislocation, -1.0, 1.0)
       When Q_b1 >> Q_a1, P_micro approaches P_ask, meaning fair value has crossed the touch.

    4. Level-1 Order Count Dispersion (S_count):
       S_count = (N_b1 - N_a1) / max(N_b1 + N_a1, 1)
       Verifies that the touch imbalance is supported by multiple market participants.

    5. Spread Elasticity Friction:
       Penalizes signal if spread is wider than max_favorable_spread_bps.

    Composite Instant Fill Score:
       Score = clip( w_flow * S_flow + w_thin * S_thin + w_micro * S_micro + w_count * S_count, -1.0, 1.0 )
    """

    def __init__(
        self,
        name: str = "InstantFill",
        w_flow: float = 0.40,
        w_thin: float = 0.30,
        w_micro: float = 0.20,
        w_count: float = 0.10,
        gamma_thin: float = 2.5,
        flow_window_secs: float = 2.0,
        max_favorable_spread_bps: float = 3.5,
    ):
        super().__init__(name)
        self.w_flow = w_flow
        self.w_thin = w_thin
        self.w_micro = w_micro
        self.w_count = w_count
        self.gamma_thin = gamma_thin
        self.flow_window_secs = flow_window_secs
        self.max_favorable_spread_bps = max_favorable_spread_bps

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        now_ms = timestamp_ms or book.last_update_time_ms
        best_bid = book.best_bid
        best_ask = book.best_ask
        mid_price = book.mid_price
        spread = book.spread

        if best_bid <= 0.0 or best_ask <= best_bid or mid_price <= 0.0:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0, timestamp_ms=now_ms)

        bids = book.bids
        asks = book.asks

        if not bids or not asks:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0, timestamp_ms=now_ms)

        # 1. Level-1 Queue Sizes and 5-Level Depth
        q_b1 = bids[0].sz
        q_a1 = asks[0].sz
        n_b1 = bids[0].n
        n_a1 = asks[0].n

        depth5_b = sum(lvl.sz for lvl in bids[:5])
        depth5_a = sum(lvl.sz for lvl in asks[:5])

        r_bid = q_b1 / max(depth5_b, 1e-6)
        r_ask = q_a1 / max(depth5_a, 1e-6)
        delta_r = r_bid - r_ask
        s_thin = math.tanh(self.gamma_thin * delta_r)

        # 2. Trade Flow Acceleration (Short-term CVD)
        cvd_short, buy_vol, sell_vol = trades.get_cvd_in_window(self.flow_window_secs, now_ms=now_ms)
        total_vol = buy_vol + sell_vol
        s_flow = (cvd_short / total_vol) if total_vol > 1e-6 else 0.0
        s_flow = max(-1.0, min(1.0, s_flow))

        # 3. Micro-Price Dislocation
        sum_q = q_b1 + q_a1
        if sum_q > 1e-6:
            p_micro = (q_b1 * best_ask + q_a1 * best_bid) / sum_q
            half_spread = spread / 2.0
            dislocation = (p_micro - mid_price) / max(half_spread, 1e-6)
            s_micro = max(-1.0, min(1.0, dislocation))
        else:
            s_micro = 0.0

        # 4. Order Count Dispersion at Touch
        sum_n = n_b1 + n_a1
        s_count = ((n_b1 - n_a1) / max(sum_n, 1)) if sum_n > 0 else 0.0
        s_count = max(-1.0, min(1.0, s_count))

        # 5. Spread Friction & Spread Elasticity Penalty
        spread_bps = (spread / mid_price) * 10_000.0
        spread_factor = 1.0
        if spread_bps > self.max_favorable_spread_bps:
            excess_spread = spread_bps - self.max_favorable_spread_bps
            spread_factor = max(0.20, 1.0 - (excess_spread / 5.0))

        # 6. Raw Composite Score
        raw_score = (
            self.w_flow * s_flow
            + self.w_thin * s_thin
            + self.w_micro * s_micro
            + self.w_count * s_count
        ) * spread_factor
        bounded_score = max(-1.0, min(1.0, raw_score))

        # 7. Confidence Metric: requires volume support and multi-factor concurrence
        flow_conviction = abs(s_flow)
        thin_conviction = abs(s_thin)
        micro_conviction = abs(s_micro)

        concurrence = 0.0
        if (s_flow > 0 and s_thin > 0 and s_micro > 0) or (s_flow < 0 and s_thin < 0 and s_micro < 0):
            concurrence = 0.25  # All 3 primary metrics point in identical direction

        vol_weight = min(1.0, total_vol / max(1.0, (depth5_b + depth5_a) * 0.10))
        confidence = min(
            1.0,
            max(0.0, 0.35 * flow_conviction + 0.25 * thin_conviction + 0.15 * micro_conviction + concurrence + 0.15 * vol_weight)
        )

        return SignalResult(
            name=self.name,
            score=bounded_score,
            raw_value=raw_score,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "s_flow": s_flow,
                "s_thin": s_thin,
                "s_micro": s_micro,
                "s_count": s_count,
                "r_bid": r_bid,
                "r_ask": r_ask,
                "cvd_short": cvd_short,
                "total_vol": total_vol,
                "spread_bps": spread_bps,
                "spread_factor": spread_factor,
            },
        )
