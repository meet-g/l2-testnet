"""Order Book Convexity & Liquidity Hole Cascade (ConvexityCascade) Alpha Signal.

Microstructure Alpha Foundation:
Empirically discovered and calibrated across Hyperliquid BTC L2 order book data.
Capitalizes on the structural dynamics of Central Limit Order Books where price
cannot advance without first consuming or depleting resting touch queues.

When queue depletion at the touch coincides with:
1. Asymmetric multi-tier depth slope (Convexity)
2. Granular order count dispersion (Hyperliquid's 'n' field showing distributed support)
3. A vacuum / liquidity hole on the opposing side
4. Flow momentum confirmation (15s rolling CVD) without limit wall absorption traps

The strategy captures multi-tick expansions (15-35 bps) engineered specifically
to decisively overcome Hyperliquid's 3.0 bps VIP 0 round-trip maker fee hurdle.
"""

from collections import deque
import bisect
import math
from typing import Any, Deque, Dict, List, Optional, Tuple

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult
from signals.vpin import VPINSignal


class ConvexityCascadeSignal(BaseSignal):
    """Detects acute order book convexity imbalances and liquidity hole vacuums
    coinciding with order count dispersion, micro-price drift, and trade flow momentum.
    """

    def __init__(
        self,
        name: str = "ConvexityCascade",
        gamma_qr: float = 0.40,
        cvd_window_secs: float = 15.0,
        cvd_scale_btc: float = 2.5,
        hole_min_depth_btc: float = 5.0,
        hole_max_thin_btc: float = 1.0,
        w_touch: float = 0.35,
        w_d5: float = 0.30,
        w_slope: float = 0.20,
        w_n: float = 0.15,
        w_hole_bonus: float = 0.15,
        w_micro: float = 0.15,
        absorption_hurdle: float = 0.25,
    ):
        super().__init__(name)
        self.gamma_qr = gamma_qr
        self.cvd_window_secs = cvd_window_secs
        self.cvd_scale_btc = cvd_scale_btc
        self.hole_min_depth_btc = hole_min_depth_btc
        self.hole_max_thin_btc = hole_max_thin_btc

        self.w_touch = w_touch
        self.w_d5 = w_d5
        self.w_slope = w_slope
        self.w_n = w_n
        self.w_hole_bonus = w_hole_bonus
        self.w_micro = w_micro
        self.absorption_hurdle = absorption_hurdle

        self.vpin_signal = VPINSignal()
        self.depth_history: Deque[Tuple[int, float, float]] = deque(maxlen=60)
        self.price_history: List[Tuple[int, float]] = []
        self._head_idx: int = 0

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        now_ms = timestamp_ms or book.last_update_time_ms

        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0, timestamp_ms=now_ms)

        bids = book.bids
        asks = book.asks
        n_b = len(bids)
        n_a = len(asks)

        if n_b < 5 or n_a < 5:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0, timestamp_ms=now_ms)

        mid = book.mid_price
        scale = getattr(book, "notional_scale", 1.0)
        is_btc = (book.coin.upper() == "BTC")
        depth_scale = 1.0 if is_btc else 0.15
        eff_scale = scale * depth_scale

        # ---------------------------------------------------------------------
        # 1. Touch Queue Depletion Ratio (Scaled properly to asset notional)
        # ---------------------------------------------------------------------
        q_b1 = bids[0].sz
        q_a1 = asks[0].sz
        min_sz = 0.005 * scale
        qr = math.log(max(q_b1, min_sz) / max(q_a1, min_sz))
        s_touch = math.tanh(self.gamma_qr * qr)

        # ---------------------------------------------------------------------
        # 2. Multi-Tier Resting Depth Imbalance (Levels 1-5)
        # ---------------------------------------------------------------------
        k_levels = min(5, n_b, n_a)
        d5_b = sum(bids[j].sz for j in range(k_levels))
        d5_a = sum(asks[j].sz for j in range(k_levels))
        denom_d5 = d5_b + d5_a
        s_d5 = (d5_b - d5_a) / max(denom_d5, 1e-6)

        # ---------------------------------------------------------------------
        # 3. Order Book Depth Slope / Convexity
        # ---------------------------------------------------------------------
        # Measures how fast depth accumulates from level 1 to level 5
        slope_b = (d5_b - q_b1) / max(k_levels - 1, 1)
        slope_a = (d5_a - q_a1) / max(k_levels - 1, 1)
        denom_slope = slope_b + slope_a
        s_slope = (slope_b - slope_a) / max(denom_slope, 1e-6)

        # ---------------------------------------------------------------------
        # 4. Order Count Dispersion Imbalance (Hyperliquid 'n' Field)
        # ---------------------------------------------------------------------
        # High 'n' with high depth = distributed sticky support
        # Low 'n' with high depth = whale spoofing hazard
        n5_b = sum(bids[j].n for j in range(k_levels))
        n5_a = sum(asks[j].n for j in range(k_levels))
        s_n = (n5_b - n5_a) / max(n5_b + n5_a, 1)

        # ---------------------------------------------------------------------
        # 5. Liquidity Hole Vacuum (Relative Depth Asymmetry & Opposing Thinness)
        # ---------------------------------------------------------------------
        ratio_b = d5_b / max(denom_d5, 1e-6)
        ratio_a = d5_a / max(denom_d5, 1e-6)
        min_depth = self.hole_min_depth_btc if is_btc else 0.50 * scale
        thin_thresh = 1.0 if is_btc else 0.35 * scale
        hole_ask = (ratio_b >= 0.72 and d5_b >= min_depth and d5_a < thin_thresh)
        hole_bid = (ratio_a >= 0.72 and d5_a >= min_depth and d5_b < thin_thresh)
        s_hole = 1.0 if hole_ask else (-1.0 if hole_bid else 0.0)

        # ---------------------------------------------------------------------
        # 6. Dual-Horizon Trade Flow Impulse (CVD)
        # ---------------------------------------------------------------------
        cvd_fast, _, _ = trades.get_cvd_in_window(self.cvd_window_secs)
        cvd_slow, _, _ = trades.get_cvd_in_window(60.0)
        s_cvd_fast = math.tanh(cvd_fast / max(self.cvd_scale_btc * eff_scale, 0.1 * eff_scale))
        s_cvd_slow = math.tanh(cvd_slow / max(4.0 * eff_scale, 0.5 * eff_scale))
        s_cvd = 0.65 * s_cvd_fast + 0.35 * s_cvd_slow

        # ---------------------------------------------------------------------
        # 7. Stoikov Micro-Price Drift Confluence
        # ---------------------------------------------------------------------
        weighted_mid = book.weighted_mid_price
        mp_drift_bps = ((weighted_mid - mid) / mid) * 10_000.0 if mid > 0 else 0.0
        s_micro = math.tanh(mp_drift_bps / 0.5)

        # ---------------------------------------------------------------------
        # 8. Directional VPIN Toxicity & Hedge Risk Alert
        # ---------------------------------------------------------------------
        vpin_res = self.vpin_signal.compute(book, trades, now_ms)
        vpin_score = vpin_res.score  # Directional signed toxicity [-1.0, +1.0]
        vpin_raw = vpin_res.raw_value  # Absolute volume imbalance [0.0, 1.0]

        # Depth Fragility Tracking: Only alert on genuine whale wall cancellations (scale not eff_scale)
        self.depth_history.append((now_ms, d5_b, d5_a))
        wall_drop_b = False
        wall_drop_a = False
        if len(self.depth_history) >= 10:
            past_b = self.depth_history[0][1]
            past_a = self.depth_history[0][2]
            if past_b > 2.0 * scale and d5_b < past_b * 0.45:
                wall_drop_b = True
            if past_a > 2.0 * scale and d5_a < past_a * 0.45:
                wall_drop_a = True

        # Macro Trend Alignment (2-minute price drift)
        self.price_history.append((now_ms, mid))
        cutoff_ms = now_ms - 600_000
        while self._head_idx < len(self.price_history) and self.price_history[self._head_idx][0] < cutoff_ms:
            self._head_idx += 1

        if self._head_idx > 1000:
            self.price_history = self.price_history[self._head_idx:]
            self._head_idx = 0

        trend_cutoff = now_ms - 120_000
        idx = bisect.bisect_left(self.price_history, (trend_cutoff, -1.0), lo=self._head_idx)
        if idx < len(self.price_history):
            past_p = self.price_history[idx][1]
        else:
            past_p = self.price_history[self._head_idx][1]
        trend_bps = ((mid - past_p) / past_p) * 10_000.0 if past_p > 0 else 0.0
        trend_score = math.tanh(trend_bps / 6.0)

        # ---------------------------------------------------------------------
        # 9. Absorption Trap Shielding & Strict Confluence Gating
        # ---------------------------------------------------------------------
        is_bull_trap = (s_cvd > 0.15 and s_d5 < -self.absorption_hurdle)
        is_bear_trap = (s_cvd < -0.15 and s_d5 > self.absorption_hurdle)

        # Anti-Whale Spoofing Check:
        # If depth is positive but order count is strongly negative (whale wall trap)
        is_spoof_trap = (s_d5 > 0.35 and s_n < -0.15) or (s_d5 < -0.35 and s_n > 0.15)

        # Climax Exhaustion Check:
        is_exhaustion_climax = (trend_score > 0.85 and s_cvd > 0.70) or (trend_score < -0.85 and s_cvd < -0.70)

        book_score = (
            self.w_touch * s_touch
            + self.w_d5 * s_d5
            + self.w_slope * s_slope
            + self.w_n * s_n
        )
        if s_hole != 0.0:
            book_score = max(-1.0, min(1.0, book_score + self.w_hole_bonus * s_hole))

        if is_spoof_trap:
            book_score *= 0.3  # Heavily discount book score on whale spoofing

        has_active_flow = abs(s_cvd) >= 0.18
        # Sensible trend tolerance (-0.10 instead of -0.02)
        trend_aligned = (s_cvd > 0 and trend_score >= -0.10) or (s_cvd < 0 and trend_score <= 0.10)
        direction_agree = (book_score * s_cvd > 0) and has_active_flow and trend_aligned

        # Counter-trend suppression: if CVD impulse fights 2-min trend, suppress entry
        strong_counter_trend = (s_cvd > 0.12 and trend_score < -0.10) or (s_cvd < -0.12 and trend_score > 0.10)

        if is_bull_trap:
            raw_alpha = -0.35
            regime_flag = "BULL_ABSORPTION_TRAP"
            confidence = 0.70
        elif is_bear_trap:
            raw_alpha = 0.35
            regime_flag = "BEAR_ABSORPTION_TRAP"
            confidence = 0.70
        elif is_exhaustion_climax:
            raw_alpha = max(-0.55, min(0.55, 0.65 * book_score))
            confidence = 0.35
            regime_flag = "EXHAUSTION_CLIMAX_DAMPENED"
        elif strong_counter_trend:
            raw_alpha = max(-0.25, min(0.25, 0.15 * book_score))
            confidence = 0.15
            regime_flag = "COUNTER_TREND_SUPPRESSED"
        elif direction_agree and not is_spoof_trap:
            raw_alpha = 0.40 * book_score + 0.30 * s_cvd + 0.15 * s_micro + 0.15 * trend_score
            confidence = 0.35 * abs(book_score) + 0.30 * abs(s_cvd) + 0.20 * abs(s_micro) + 0.15 * abs(trend_score)
            regime_flag = "CONVEXITY_CASCADE"
        else:
            raw_alpha = max(-0.40, min(0.40, 0.25 * (book_score + s_cvd)))
            confidence = 0.20
            regime_flag = "WEAK_FLOW_DAMPENED"

        # ---------------------------------------------------------------------
        # 10. Directional Toxicity Shield & Defensive Hedge Alert
        # ---------------------------------------------------------------------
        # Protect passive maker entries from informed adverse selection
        if raw_alpha > 0 and vpin_score < -0.20:
            adverse_drag = min(1.0, abs(vpin_score) / 0.45)
            raw_alpha *= (1.0 - 0.75 * adverse_drag)
            if vpin_score < -0.35:
                raw_alpha = min(raw_alpha, 0.05)
        elif raw_alpha < 0 and vpin_score > 0.20:
            adverse_drag = min(1.0, abs(vpin_score) / 0.45)
            raw_alpha *= (1.0 - 0.75 * adverse_drag)
            if vpin_score > 0.35:
                raw_alpha = max(raw_alpha, -0.05)

        # Extreme Choppy Toxicity Gate: When unsigned VPIN is extreme without clear direction
        toxic_ceiling = 0.88 if is_btc else 0.75
        if vpin_raw >= toxic_ceiling and abs(vpin_score) < 0.25:
            raw_alpha *= 0.65

        # Depth Fragility Shield: if resting whale wall was rapidly pulled, dampen alpha
        if (raw_alpha > 0 and wall_drop_b) or (raw_alpha < 0 and wall_drop_a):
            raw_alpha = max(-0.30, min(0.30, raw_alpha * 0.20))

        score = max(-1.0, min(1.0, raw_alpha))

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=raw_alpha,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "s_touch": s_touch,
                "s_d5": s_d5,
                "s_slope": s_slope,
                "s_n": s_n,
                "s_hole": s_hole,
                "s_cvd": s_cvd,
                "s_micro": s_micro,
                "mp_drift_bps": mp_drift_bps,
                "vpin_score": vpin_score,
                "vpin_raw": vpin_raw,
                "regime_flag": regime_flag,
                "queue_ratio": math.exp(qr) if abs(qr) < 10 else (999.0 if qr > 0 else 0.001),
                "d5_bid": d5_b,
                "d5_ask": d5_a,
                "n5_bid": n5_b,
                "n5_ask": n5_a,
                "cvd_fast": cvd_fast,
            },
        )
