"""Dynamic Spread Scalper (Variable Take-Profit Microstructure Alpha Signal).

Microstructure Foundation:
Specifically designed for high-frequency scalping in tight-spread instruments (e.g. xyz:SKHX,
xyz:SKHY, BTC) where static 16-20 bps profit targets suffer from adverse decay.
Synthesizes:
1. Micro-Price Dislocation (Stoikov fair value pressure relative to touch)
2. Queue Depletion Asymmetry (thin touch relative to 5-level resting depth)
3. Order Flow Impulse (short-horizon CVD velocity and signed trade bursts)
4. Anti-Spoofing Order Count Dispersion (multi-participant touch confirmation)
5. Multi-Level Decaying Depth Imbalance (5-level exponential weight)
6. Dynamic Take-Profit & Volatility Amplitude Model:
   Estimates real-time optimal take-profit targets scaled off instantaneous spread,
   rolling return volatility, and flow exhaustion indicators.
"""

from collections import deque
import math
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult


class DynamicSpreadSignal(BaseSignal):
    """Adaptive Spread & Flow Scalper Alpha Signal with Variable Take-Profit Telemetry."""

    def __init__(
        self,
        name: str = "DynamicSpread",
        w_flow: float = 0.30,
        w_thin: float = 0.25,
        w_micro: float = 0.20,
        w_wobi: float = 0.15,
        w_count: float = 0.10,
        gamma_thin: float = 2.5,
        flow_window_secs: float = 2.0,
        max_favorable_spread_bps: float = 5.0,
        dynamic_tp_min_bps: float = 4.0,
        dynamic_tp_max_bps: float = 12.0,
        dynamic_tp_spread_mult: float = 2.0,
        dynamic_tp_vol_mult: float = 0.8,
    ):
        super().__init__(name)
        self.w_flow = w_flow
        self.w_thin = w_thin
        self.w_micro = w_micro
        self.w_wobi = w_wobi
        self.w_count = w_count
        self.gamma_thin = gamma_thin
        self.flow_window_secs = flow_window_secs
        self.max_favorable_spread_bps = max_favorable_spread_bps
        self.dynamic_tp_min_bps = dynamic_tp_min_bps
        self.dynamic_tp_max_bps = dynamic_tp_max_bps
        self.dynamic_tp_spread_mult = dynamic_tp_spread_mult
        self.dynamic_tp_vol_mult = dynamic_tp_vol_mult

        # Rolling mid-price cache for short-term realized volatility calculation
        self._price_history: Deque[Tuple[int, float]] = deque()
        self._cached_vol_bps: float = 3.5
        self._last_vol_calc_ms: int = 0

    def _update_price_history(self, now_ms: int, mid_price: float) -> None:
        """Maintains a rolling 60-second mid-price buffer to compute volatility."""
        if self._price_history and now_ms < self._price_history[-1][0]:
            self._price_history.clear()
            self._last_vol_calc_ms = 0

        self._price_history.append((now_ms, mid_price))
        cutoff_ms = now_ms - 60_000
        while self._price_history and self._price_history[0][0] < cutoff_ms:
            self._price_history.popleft()

    def _estimate_volatility_bps(self) -> float:
        """Estimates short-term volatility in basis points from rolling price history."""
        if len(self._price_history) < 5:
            return 3.5  # Sensible default for normal market conditions

        # Sample prices at roughly 1-second intervals to avoid high-frequency zero-return dilution
        samples = []
        last_t = -1
        for ts, px in self._price_history:
            if last_t < 0 or (ts - last_t) >= 1000:
                samples.append(px)
                last_t = ts

        if len(samples) < 5:
            # Fallback to raw prices if time intervals are small (e.g. synthetic test)
            samples = [p for _, p in self._price_history]

        returns_bps = []
        for i in range(1, len(samples)):
            p_prev = samples[i - 1]
            p_curr = samples[i]
            if p_prev > 0:
                ret = abs((p_curr - p_prev) / p_prev) * 10_000.0
                returns_bps.append(ret)

        if not returns_bps:
            return 3.5

        # Mean absolute deviation in bps scaled to pseudo-volatility
        mean_ret = sum(returns_bps) / len(returns_bps)
        variance = sum((r - mean_ret) ** 2 for r in returns_bps) / len(returns_bps)
        std_ret = math.sqrt(variance)
        return max(1.0, std_ret * 2.0)

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        now_ms = timestamp_ms or book.last_update_time_ms or int(time.time() * 1000)
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

        self._update_price_history(now_ms, mid_price)
        if now_ms - self._last_vol_calc_ms >= 1000 or self._last_vol_calc_ms == 0 or now_ms < self._last_vol_calc_ms:
            self._cached_vol_bps = self._estimate_volatility_bps()
            self._last_vol_calc_ms = now_ms
        current_vol_bps = self._cached_vol_bps
        spread_bps = (spread / mid_price) * 10_000.0

        # ---------------------------------------------------------------------
        # 1. Micro-Price Dislocation (S_micro)
        # ---------------------------------------------------------------------
        q_b1 = bids[0].sz
        q_a1 = asks[0].sz
        p_micro = (q_b1 * best_ask + q_a1 * best_bid) / (q_b1 + q_a1 + 1e-9)
        dislocation = (p_micro - mid_price) / (0.5 * spread + 1e-9)
        s_micro = max(-1.0, min(1.0, dislocation))

        # ---------------------------------------------------------------------
        # 2. Queue Thinning / Depletion Ratio (S_thin)
        # ---------------------------------------------------------------------
        depth_bid_5 = sum(b.sz for b in bids[:5])
        depth_ask_5 = sum(a.sz for a in asks[:5])

        r_bid = q_b1 / (depth_bid_5 + 1e-9)
        r_ask = q_a1 / (depth_ask_5 + 1e-9)
        s_thin = math.tanh(self.gamma_thin * (r_bid - r_ask))

        # ---------------------------------------------------------------------
        # 3. CVD Trade Flow Impulse (S_flow)
        # ---------------------------------------------------------------------
        buy_vol = 0.0
        sell_vol = 0.0
        if trades is not None and hasattr(trades, "trades"):
            cutoff_ms = now_ms - int(self.flow_window_secs * 1000)
            for tr in reversed(trades.trades):
                if tr.timestamp_ms < cutoff_ms:
                    break
                if tr.side == "B":
                    buy_vol += tr.size
                elif tr.side == "A":
                    sell_vol += tr.size

        tot_vol = buy_vol + sell_vol
        cvd_delta = buy_vol - sell_vol
        s_flow = (cvd_delta / max(tot_vol, 1e-9)) if tot_vol > 0.0 else 0.0
        s_flow = max(-1.0, min(1.0, s_flow))

        # ---------------------------------------------------------------------
        # 4. Anti-Spoofing Order Count Dispersion (S_count)
        # ---------------------------------------------------------------------
        n_b1 = bids[0].n
        n_a1 = asks[0].n
        total_n1 = n_b1 + n_a1
        s_count = ((n_b1 - n_a1) / max(total_n1, 1)) if total_n1 > 0 else 0.0
        s_count = max(-1.0, min(1.0, s_count))

        # ---------------------------------------------------------------------
        # 5. Multi-Level Decaying Depth Imbalance (S_wobi)
        # ---------------------------------------------------------------------
        w_b = sum((0.6 ** k) * bids[k].sz for k in range(min(5, len(bids))))
        w_a = sum((0.6 ** k) * asks[k].sz for k in range(min(5, len(asks))))
        s_wobi = (w_b - w_a) / max(w_b + w_a, 1e-9)
        s_wobi = max(-1.0, min(1.0, s_wobi))

        # ---------------------------------------------------------------------
        # 6. Spread Elasticity Friction Factor
        # ---------------------------------------------------------------------
        if spread_bps <= self.max_favorable_spread_bps:
            spread_factor = 1.0
        else:
            spread_factor = max(0.1, 1.0 - ((spread_bps - self.max_favorable_spread_bps) / 10.0))

        # Raw composite score before friction
        raw_composite = (
            self.w_flow * s_flow
            + self.w_thin * s_thin
            + self.w_micro * s_micro
            + self.w_wobi * s_wobi
            + self.w_count * s_count
        )
        score = max(-1.0, min(1.0, raw_composite * spread_factor))

        # ---------------------------------------------------------------------
        # 7. Dynamic Take-Profit & Trailing Stop Telemetry
        # ---------------------------------------------------------------------
        # Target TP scales dynamically with current spread and realized volatility
        computed_tp = (self.dynamic_tp_spread_mult * spread_bps) + (self.dynamic_tp_vol_mult * current_vol_bps)
        target_tp_bps = max(self.dynamic_tp_min_bps, min(self.dynamic_tp_max_bps, computed_tp))

        # Tiered trailing stop parameters
        trail_act_bps = max(2.5, target_tp_bps * 0.5)
        trail_dist_bps = max(1.0, target_tp_bps * 0.25)

        # ---------------------------------------------------------------------
        # 8. Confidence Metric
        # ---------------------------------------------------------------------
        # Evaluates touch order dispersion, volume support, and flow consistency
        count_conf = min(1.0, total_n1 / 6.0) if total_n1 > 0 else 0.5
        vol_conf = min(1.0, tot_vol / 1.0) if tot_vol > 0.0 else 0.5
        alignment = max(0.4, 1.0 - 0.4 * abs(s_flow - s_thin))
        confidence = max(0.1, min(1.0, 0.4 * count_conf + 0.3 * vol_conf + 0.3 * alignment))

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=raw_composite,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "target_tp_bps": target_tp_bps,
                "trail_act_bps": trail_act_bps,
                "trail_dist_bps": trail_dist_bps,
                "volatility_bps": current_vol_bps,
                "spread_bps": spread_bps,
                "spread_factor": spread_factor,
                "s_flow": s_flow,
                "s_thin": s_thin,
                "s_micro": s_micro,
                "s_wobi": s_wobi,
                "s_count": s_count,
            },
        )
