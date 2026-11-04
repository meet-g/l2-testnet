"""Stoikov Micro-Price Estimator and Fair-Value Drift Signal."""

import bisect
import math
from typing import List, Optional, Tuple

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

    Trend & CVD Filter:
        Suppresses counter-trend touch imbalance spikes when prevailing multi-horizon
        price drift (e.g. 60s/30s) or cumulative volume delta (CVD) strongly opposes
        the touch direction, eliminating knife-catching in structural market moves.
    """

    def __init__(
        self,
        name: str = "MicroPrice",
        gamma_nonlinearity: float = 0.85,  # Sub-linear transition adjustment
        spread_scale_bps: float = 1.0,
        trend_filter_enabled: bool = True,
        trend_window_secs: float = 60.0,
        max_counter_trend_bps: float = 1.0,
        require_cvd_alignment: bool = True,
        cvd_window_secs: float = 30.0,
    ):
        super().__init__(name)
        self.gamma = gamma_nonlinearity
        self.spread_scale_bps = spread_scale_bps
        self.trend_filter_enabled = trend_filter_enabled
        self.trend_window_secs = trend_window_secs
        self.max_counter_trend_bps = max_counter_trend_bps
        self.require_cvd_alignment = require_cvd_alignment
        self.cvd_window_secs = cvd_window_secs

        self.price_history: List[Tuple[int, float]] = []
        self._head_idx: int = 0

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

        now_ms = timestamp_ms or book.last_update_time_ms
        if now_ms and mid > 0:
            self.price_history.append((now_ms, mid))
            cutoff_ms = now_ms - 600_000
            while self._head_idx < len(self.price_history) and self.price_history[self._head_idx][0] < cutoff_ms:
                self._head_idx += 1
            if self._head_idx > 1000:
                self.price_history = self.price_history[self._head_idx:]
                self._head_idx = 0

        # Standard imbalance
        imbalance = (qb - qa) / total_q

        # Non-linear probability adjustment g(I)
        sign = 1.0 if imbalance >= 0 else -1.0
        g_imb = sign * (abs(imbalance) ** self.gamma)

        # Stoikov micro-price
        half_spread = spread / 2.0
        p_micro = mid + (half_spread * g_imb)

        # Drift difference in dollars and bps
        micro_drift = p_micro - mid
        micro_drift_bps = ((p_micro - mid) / mid) * 10_000.0 if mid > 0 else 0.0

        # Normalized drift score [-1.0, 1.0]
        score = max(-1.0, min(1.0, g_imb))

        # Multi-tier depth consensus (verify levels 1-5 support touch imbalance)
        d5_imb = book.depth_imbalance(5)
        consensus_factor = 1.0 if (imbalance * d5_imb >= 0) else max(0.2, 1.0 - abs(d5_imb))
        if imbalance * d5_imb < 0:
            score *= max(0.4, 1.0 - abs(d5_imb))

        # Compute rolling trend and CVD metrics
        trend_cutoff = now_ms - int(self.trend_window_secs * 1000)
        idx = bisect.bisect_left(self.price_history, (trend_cutoff, -1.0), lo=self._head_idx)
        if idx < len(self.price_history):
            past_px = self.price_history[idx][1]
        elif self.price_history:
            past_px = self.price_history[self._head_idx][1]
        else:
            past_px = mid
        trend_bps = ((mid - past_px) / past_px) * 10_000.0 if past_px > 0 else 0.0

        fast_cutoff = now_ms - 30_000
        idx_fast = bisect.bisect_left(self.price_history, (fast_cutoff, -1.0), lo=self._head_idx)
        past_px_fast = self.price_history[idx_fast][1] if idx_fast < len(self.price_history) else past_px
        trend_fast_bps = ((mid - past_px_fast) / past_px_fast) * 10_000.0 if past_px_fast > 0 else 0.0

        cvd_val = 0.0
        buy_vol = 0.0
        sell_vol = 0.0
        if trades is not None and hasattr(trades, "get_cvd_in_window"):
            cvd_val, buy_vol, sell_vol = trades.get_cvd_in_window(self.cvd_window_secs)

        # Counter-trend suppression logic
        counter_trend_suppressed = False
        suppression_reason = ""

        if self.trend_filter_enabled and (len(self.price_history) - self._head_idx) >= 5:
            if score > 0:  # Bullish signal attempt
                if trend_bps < -self.max_counter_trend_bps:
                    counter_trend_suppressed = True
                    suppression_reason = f"Trend {trend_bps:+.2f} bps < -{self.max_counter_trend_bps:.2f} bps"
                elif trend_fast_bps < -(self.max_counter_trend_bps * 1.5):
                    counter_trend_suppressed = True
                    suppression_reason = f"Fast trend {trend_fast_bps:+.2f} bps < -{self.max_counter_trend_bps*1.5:.2f} bps"
                elif self.require_cvd_alignment and cvd_val < -0.1 and sell_vol > buy_vol * 1.2:
                    counter_trend_suppressed = True
                    suppression_reason = f"CVD negative ({cvd_val:+.2f}, sell={sell_vol:.2f} > buy={buy_vol:.2f})"
                elif d5_imb < -0.20:
                    counter_trend_suppressed = True
                    suppression_reason = f"Deeper depth opposing (d5_imb={d5_imb:+.2f})"

                if counter_trend_suppressed:
                    score = min(score, 0.20)

            elif score < 0:  # Bearish signal attempt
                if trend_bps > self.max_counter_trend_bps:
                    counter_trend_suppressed = True
                    suppression_reason = f"Trend {trend_bps:+.2f} bps > +{self.max_counter_trend_bps:.2f} bps"
                elif trend_fast_bps > (self.max_counter_trend_bps * 1.5):
                    counter_trend_suppressed = True
                    suppression_reason = f"Fast trend {trend_fast_bps:+.2f} bps > +{self.max_counter_trend_bps*1.5:.2f} bps"
                elif self.require_cvd_alignment and cvd_val > 0.1 and buy_vol > sell_vol * 1.2:
                    counter_trend_suppressed = True
                    suppression_reason = f"CVD positive ({cvd_val:+.2f}, buy={buy_vol:.2f} > sell={sell_vol:.2f})"
                elif d5_imb > 0.20:
                    counter_trend_suppressed = True
                    suppression_reason = f"Deeper depth opposing (d5_imb={d5_imb:+.2f})"

                if counter_trend_suppressed:
                    score = max(score, -0.20)

        # Robust cross-asset confidence: higher when spread is tight (bps), depth is thick,
        # participants are distributed across top 3 tiers, and deeper book depth confirms the touch direction
        scale = getattr(book, "notional_scale", 1.0)
        spread_factor = max(0.1, min(1.0, 2.5 / max(book.spread_bps, 0.5)))
        d3_b, d3_a = book.get_depth_volume(3)
        d3_total = d3_b + d3_a
        touch_factor = min(1.0, total_q / max(0.35 * scale, 0.01))
        d3_factor = min(1.0, d3_total / max(1.20 * scale, 0.01))
        depth_factor = 0.50 * touch_factor + 0.50 * d3_factor

        n_b3, n_a3 = book.get_depth_order_counts(3)
        n_factor = min(1.0, max(0.3, (n_b3 + n_a3) / 8.0))
        confidence = min(1.0, spread_factor * depth_factor * (0.6 * consensus_factor + 0.4 * n_factor))
        if counter_trend_suppressed:
            confidence = min(confidence, 0.25)
        confidence = max(0.0, min(1.0, confidence))

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=micro_drift,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "mid_price": mid,
                "micro_price": p_micro,
                "spread": spread,
                "spread_bps": book.spread_bps,
                "imbalance": imbalance,
                "micro_drift_usd": micro_drift,
                "micro_drift_bps": micro_drift_bps,
                "d5_imb": d5_imb,
                "consensus_factor": consensus_factor,
                "trend_60s_bps": trend_bps,
                "trend_30s_bps": trend_fast_bps,
                "cvd_val": cvd_val,
                "counter_trend_suppressed": counter_trend_suppressed,
                "suppression_reason": suppression_reason,
            },
        )
