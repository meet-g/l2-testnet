"""Queue Replenishment Latency & Dynamic Asymmetry (QRLA) Alpha Signal.

Microstructure Alpha Foundation:
Models the dynamic post-trade replenishment response of passive market makers,
depletion latency persistence across consecutive snapshots, and multi-tier order
cancellation asymmetry. Coupled with continuous taker flow (CVD) and macro trend
alignment to generate high-conviction maker entries and rapid defensive maker hedge alerts.
"""

from collections import deque
import bisect
import math
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult
from signals.vpin import VPINSignal


class QueueReplenishmentSignal(BaseSignal):
    """Dynamic Queue Replenishment Latency and Multi-Tier Cancellation Asymmetry Alpha Signal."""

    def __init__(
        self,
        name: str = "QueueReplenishment",
        kappa_touch_btc: float = 0.05,
        kappa_multi_btc: float = 0.10,
        kappa_lat: float = 2.0,
        depletion_threshold: float = 0.30,
        baseline_window: int = 30,
        cvd_window_secs: float = 15.0,
        cvd_scale_btc: float = 2.0,
        min_flow_hurdle: float = 0.18,
        trend_window_secs: float = 120.0,
        trend_scale_bps: float = 6.0,
        w_rep1: float = 0.40,
        w_rep3: float = 0.30,
        w_lat: float = 0.15,
        w_canc: float = 0.15,
    ):
        super().__init__(name)
        self.kappa_touch_btc = kappa_touch_btc
        self.kappa_multi_btc = kappa_multi_btc
        self.kappa_lat = kappa_lat
        self.depletion_threshold = depletion_threshold
        self.baseline_window = baseline_window
        self.cvd_window_secs = cvd_window_secs
        self.cvd_scale_btc = cvd_scale_btc
        self.min_flow_hurdle = min_flow_hurdle
        self.trend_window_secs = trend_window_secs
        self.trend_scale_bps = trend_scale_bps

        self.w_rep1 = w_rep1
        self.w_rep3 = w_rep3
        self.w_lat = w_lat
        self.w_canc = w_canc

        # Sub-signal for Directional Toxicity Shielding
        self.vpin_signal = VPINSignal()

        # State tracking buffers
        self.b1_history: Deque[float] = deque(maxlen=baseline_window)
        self.a1_history: Deque[float] = deque(maxlen=baseline_window)
        self.b1_time_history: Deque[Tuple[int, float]] = deque(maxlen=5000)
        self.a1_time_history: Deque[Tuple[int, float]] = deque(maxlen=5000)
        self.price_history: List[Tuple[int, float]] = []
        self._head_idx: int = 0

        self.prev_b1_sz: float = 0.0
        self.prev_a1_sz: float = 0.0
        self.prev_d3_b: float = 0.0
        self.prev_d3_a: float = 0.0
        self.prev_total_volume: float = 0.0
        self.prev_total_cvd: float = 0.0
        self.prev_update_count: int = -1
        self.prev_timestamp_ms: int = 0
        self.is_initialized: bool = False

        self.tau_b: int = 0
        self.tau_a: int = 0
        self.tau_b_start_ms: int = 0
        self.tau_a_start_ms: int = 0

        # Snapshot cache for between-snapshot evaluation ticks
        self.last_s_rep1: float = 0.0
        self.last_s_rep3: float = 0.0
        self.last_s_lat: float = 0.0
        self.last_s_canc: float = 0.0
        self.last_qrl_core: float = 0.0
        self.last_r_b1: float = 0.0
        self.last_r_a1: float = 0.0
        self.last_r_b3: float = 0.0
        self.last_r_a3: float = 0.0
        self.last_c_b: float = 0.0
        self.last_c_a: float = 0.0

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        now_ms = timestamp_ms or book.last_update_time_ms or int(time.time() * 1000)

        # Standard default metadata dictionary covering all schema requirements
        default_metadata = {
            "l1_rep_bid": 0.0,
            "l1_rep_ask": 0.0,
            "l3_rep_bid": 0.0,
            "l3_rep_ask": 0.0,
            "latency_bid": self.tau_b,
            "latency_ask": self.tau_a,
            "s_canc": 0.0,
            "cvd_fast": 0.0,
            "trend_bps": 0.0,
            "s_rep1": 0.0,
            "s_rep3": 0.0,
            "s_lat": 0.0,
            "qrl_core": 0.0,
            "s_cvd": 0.0,
            "trend_score": 0.0,
            "regime_flag": "INITIALIZATION",
            "r_b1": 0.0,
            "r_a1": 0.0,
            "r_b3": 0.0,
            "r_a3": 0.0,
            "tau_b": self.tau_b,
            "tau_a": self.tau_a,
            "c_b": 0.0,
            "c_a": 0.0,
            "total_vol_fast": 0.0,
            "regime": "INITIALIZATION",
            "vpin_score": 0.0,
            "vpin_raw": 0.0,
        }

        # Step 1: Structural validity guard
        if not book.is_valid:
            return SignalResult(
                name=self.name,
                score=0.0,
                raw_value=0.0,
                confidence=0.0,
                timestamp_ms=now_ms,
                metadata=default_metadata,
            )

        bids = book.bids
        asks = book.asks
        if len(bids) < 3 or len(asks) < 3:
            return SignalResult(
                name=self.name,
                score=0.0,
                raw_value=0.0,
                confidence=0.0,
                timestamp_ms=now_ms,
                metadata=default_metadata,
            )

        mid = book.mid_price
        if mid <= 0:
            return SignalResult(
                name=self.name,
                score=0.0,
                raw_value=0.0,
                confidence=0.0,
                timestamp_ms=now_ms,
                metadata=default_metadata,
            )

        # Dynamic cross-asset notional scaling
        scale = getattr(book, "notional_scale", 1.0)
        if scale <= 0:
            scale = 85000.0 / max(mid, 1e-4) if (book.coin.upper() != "BTC" and mid > 0) else 1.0

        q_b1 = bids[0].sz
        q_a1 = asks[0].sz
        d3_b = sum(bids[j].sz for j in range(min(3, len(bids))))
        d3_a = sum(asks[j].sz for j in range(min(3, len(asks))))

        # Step 2: First Snapshot Initialization
        if not self.is_initialized:
            self.prev_b1_sz = q_b1
            self.prev_a1_sz = q_a1
            self.prev_d3_b = d3_b
            self.prev_d3_a = d3_a
            self.prev_total_volume = getattr(trades, "total_volume", 0.0)
            self.prev_total_cvd = getattr(trades, "total_cvd", 0.0)
            self.prev_update_count = book.update_count
            self.prev_timestamp_ms = now_ms
            self.b1_history.append(q_b1)
            self.a1_history.append(q_a1)
            if now_ms > 0:
                self.b1_time_history.append((now_ms, q_b1))
                self.a1_time_history.append((now_ms, q_a1))
            self.price_history.append((now_ms, mid))
            self.is_initialized = True
            return SignalResult(
                name=self.name,
                score=0.0,
                raw_value=0.0,
                confidence=0.0,
                timestamp_ms=now_ms,
                metadata=default_metadata,
            )

        # Step 3: Snapshot Update Tracking
        snapshot_changed = (
            (book.update_count != self.prev_update_count)
            or (now_ms != self.prev_timestamp_ms)
            or (q_b1 != self.prev_b1_sz)
            or (q_a1 != self.prev_a1_sz)
        )

        if snapshot_changed:
            curr_v = getattr(trades, "total_volume", 0.0)
            curr_c = getattr(trades, "total_cvd", 0.0)
            if curr_v < self.prev_total_volume:
                # Session or file boundary reset
                delta_v = curr_v
                delta_c = curr_c
            else:
                delta_v = curr_v - self.prev_total_volume
                delta_c = curr_c - self.prev_total_cvd

            vol_bought = max(0.0, (delta_v + delta_c) * 0.5)
            vol_sold = max(0.0, (delta_v - delta_c) * 0.5)

            # Robust fallback: if delta_v == 0 but trades deque has recent trades
            if delta_v == 0.0 and hasattr(trades, "trades") and len(trades.trades) > 0:
                for t in reversed(trades.trades):
                    if t.timestamp_ms <= self.prev_timestamp_ms:
                        break
                    if t.side == "A":
                        vol_sold += t.size
                    elif t.side == "B":
                        vol_bought += t.size

            delta_q_b1 = q_b1 - self.prev_b1_sz
            delta_q_a1 = q_a1 - self.prev_a1_sz
            delta_d3_b = d3_b - self.prev_d3_b
            delta_d3_a = d3_a - self.prev_d3_a

            r_b1 = delta_q_b1 + vol_sold
            r_a1 = delta_q_a1 + vol_bought
            r_b3 = delta_d3_b + vol_sold
            r_a3 = delta_d3_a + vol_bought

            c_b = max(0.0, -(delta_d3_b + vol_sold))
            c_a = max(0.0, -(delta_d3_a + vol_bought))

            # Rolling median baseline calculation (60s rolling time baseline for 20 Hz frequency invariance)
            if now_ms > 0:
                cutoff_base = now_ms - 60_000
                while self.b1_time_history and self.b1_time_history[0][0] < cutoff_base:
                    self.b1_time_history.popleft()
                while self.a1_time_history and self.a1_time_history[0][0] < cutoff_base:
                    self.a1_time_history.popleft()

            if now_ms > 0 and len(self.b1_time_history) >= 10:
                sorted_b = sorted(v for _, v in self.b1_time_history)
                base_b = max(sorted_b[len(sorted_b) // 2], 0.01 * scale)
            elif self.b1_history:
                sorted_b = sorted(self.b1_history)
                base_b = max(sorted_b[len(sorted_b) // 2], 0.01 * scale)
            else:
                base_b = 0.20 * scale

            if now_ms > 0 and len(self.a1_time_history) >= 10:
                sorted_a = sorted(v for _, v in self.a1_time_history)
                base_a = max(sorted_a[len(sorted_a) // 2], 0.01 * scale)
            elif self.a1_history:
                sorted_a = sorted(self.a1_history)
                base_a = max(sorted_a[len(sorted_a) // 2], 0.01 * scale)
            else:
                base_a = 0.20 * scale

            # Depletion latency counter update (< 30% baseline)
            # Only record healthy depths to prevent baseline poisoning
            if q_b1 < self.depletion_threshold * base_b:
                if self.tau_b_start_ms == 0:
                    self.tau_b_start_ms = now_ms
                self.tau_b = min(self.tau_b + 1, 50)
                tau_b_sec = min(5.0, max(0.05, (now_ms - self.tau_b_start_ms) / 1000.0)) if (now_ms >= self.tau_b_start_ms and now_ms > 0) else (self.tau_b * 0.1)
            else:
                self.tau_b = 0
                self.tau_b_start_ms = 0
                tau_b_sec = 0.0
                self.b1_history.append(q_b1)
                if now_ms > 0 and (not self.b1_time_history or (now_ms - self.b1_time_history[-1][0] >= 500)):
                    self.b1_time_history.append((now_ms, q_b1))

            if q_a1 < self.depletion_threshold * base_a:
                if self.tau_a_start_ms == 0:
                    self.tau_a_start_ms = now_ms
                self.tau_a = min(self.tau_a + 1, 50)
                tau_a_sec = min(5.0, max(0.05, (now_ms - self.tau_a_start_ms) / 1000.0)) if (now_ms >= self.tau_a_start_ms and now_ms > 0) else (self.tau_a * 0.1)
            else:
                self.tau_a = 0
                self.tau_a_start_ms = 0
                tau_a_sec = 0.0
                self.a1_history.append(q_a1)
                if now_ms > 0 and (not self.a1_time_history or (now_ms - self.a1_time_history[-1][0] >= 500)):
                    self.a1_time_history.append((now_ms, q_a1))

            kappa_touch = max(self.kappa_touch_btc * scale, 1e-6)
            kappa_multi = max(self.kappa_multi_btc * scale, 1e-6)
            eps_canc = max(0.01 * scale, 1e-6)

            s_rep1 = math.tanh((r_b1 - r_a1) / kappa_touch)
            s_rep3 = math.tanh((r_b3 - r_a3) / kappa_multi)
            eff_kappa_lat = max(self.kappa_lat, 1e-4)
            # Use real elapsed seconds when available, otherwise scale snapshot count
            if tau_a_sec > 0.0 or tau_b_sec > 0.0:
                s_lat = math.tanh((tau_a_sec - tau_b_sec) / eff_kappa_lat)
            else:
                s_lat = math.tanh(((self.tau_a - self.tau_b) * 0.1) / eff_kappa_lat)
            s_canc = (c_a - c_b) / max(c_a + c_b + eps_canc, 1e-6)

            qrl_core = (
                self.w_rep1 * s_rep1
                + self.w_rep3 * s_rep3
                + self.w_lat * s_lat
                + self.w_canc * s_canc
            )

            # Update cached snapshot metrics
            self.prev_b1_sz = q_b1
            self.prev_a1_sz = q_a1
            self.prev_d3_b = d3_b
            self.prev_d3_a = d3_a
            self.prev_total_volume = curr_v
            self.prev_total_cvd = curr_c
            self.prev_update_count = book.update_count
            self.prev_timestamp_ms = now_ms

            self.last_s_rep1 = s_rep1
            self.last_s_rep3 = s_rep3
            self.last_s_lat = s_lat
            self.last_s_canc = s_canc
            self.last_qrl_core = qrl_core
            self.last_r_b1 = r_b1
            self.last_r_a1 = r_a1
            self.last_r_b3 = r_b3
            self.last_r_a3 = r_a3
            self.last_c_b = c_b
            self.last_c_a = c_a
        else:
            s_rep1 = self.last_s_rep1
            s_rep3 = self.last_s_rep3
            s_lat = self.last_s_lat
            s_canc = self.last_s_canc
            qrl_core = self.last_qrl_core
            r_b1 = self.last_r_b1
            r_a1 = self.last_r_a1
            r_b3 = self.last_r_b3
            r_a3 = self.last_r_a3
            c_b = self.last_c_b
            c_a = self.last_c_a

        # Step 4: High-Frequency CVD Flow
        cvd_fast, buy_vol_fast, sell_vol_fast = trades.get_cvd_in_window(self.cvd_window_secs, now_ms=now_ms)
        total_vol_fast = buy_vol_fast + sell_vol_fast
        s_cvd = math.tanh(cvd_fast / max(self.cvd_scale_btc * scale, 0.1 * scale))

        # Step 5: 2-Minute Macro Trend Alignment
        self.price_history.append((now_ms, mid))
        cutoff_ms = now_ms - 600_000
        while self._head_idx < len(self.price_history) and self.price_history[self._head_idx][0] < cutoff_ms:
            self._head_idx += 1
        if self._head_idx > 1000:
            self.price_history = self.price_history[self._head_idx:]
            self._head_idx = 0

        trend_cutoff = now_ms - int(self.trend_window_secs * 1000)
        idx = bisect.bisect_left(self.price_history, (trend_cutoff, -1.0), lo=self._head_idx)
        if idx < len(self.price_history):
            past_p = self.price_history[idx][1]
        else:
            past_p = self.price_history[self._head_idx][1]
        trend_bps = ((mid - past_p) / past_p) * 10_000.0 if past_p > 0 else 0.0
        trend_score = math.tanh(trend_bps / max(self.trend_scale_bps, 1e-4))

        # Step 6: Confluence & Directional Gating
        has_active_flow = abs(s_cvd) >= self.min_flow_hurdle
        trend_aligned = (s_cvd > 0 and trend_score >= -0.10) or (s_cvd < 0 and trend_score <= 0.10)
        direction_agree = (qrl_core * s_cvd > 0) and has_active_flow and trend_aligned

        if direction_agree:
            raw_alpha = 0.50 * qrl_core + 0.30 * s_cvd + 0.20 * trend_score
            confidence = 0.40 * abs(qrl_core) + 0.35 * abs(s_cvd) + 0.25 * abs(trend_score)
            regime_flag = "REPLENISHMENT_FLOW_ALIGNED"
        else:
            # Dampened regime: preserve replenishment direction without allowing entry threshold trigger
            raw_alpha = max(-0.35, min(0.35, 0.30 * qrl_core + 0.10 * s_cvd))
            confidence = 0.20
            regime_flag = "DAMPENED_FLOW_DISAGREEMENT"

        # Step 7: Directional VPIN Toxicity Shield & Defensive Hedge Alert
        vpin_res = self.vpin_signal.compute(book, trades, now_ms)
        vpin_score = vpin_res.score
        vpin_raw = vpin_res.raw_value

        if raw_alpha > 0 and vpin_score < -0.20:
            # Informed selling threatens maker buy order
            adverse_drag = min(1.0, abs(vpin_score) / 0.45)
            raw_alpha *= (1.0 - 0.75 * adverse_drag)
            confidence *= (1.0 - 0.50 * adverse_drag)
            if vpin_score < -0.35:
                raw_alpha = min(raw_alpha, 0.10)
        elif raw_alpha < 0 and vpin_score > 0.20:
            # Informed buying threatens maker sell order
            adverse_drag = min(1.0, abs(vpin_score) / 0.45)
            raw_alpha *= (1.0 - 0.75 * adverse_drag)
            confidence *= (1.0 - 0.50 * adverse_drag)
            if vpin_score > 0.35:
                raw_alpha = max(raw_alpha, -0.10)

        # Extreme Choppy Toxicity Gate: When unsigned VPIN is extreme without clear direction
        is_btc = (book.coin.upper() == "BTC")
        toxic_ceiling = 0.88 if is_btc else 0.75
        if vpin_raw >= toxic_ceiling and abs(vpin_score) < 0.25:
            raw_alpha *= 0.65
            confidence *= 0.70

        score = max(-1.0, min(1.0, raw_alpha))
        confidence = max(0.0, min(1.0, confidence))

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=raw_alpha,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "l1_rep_bid": r_b1,
                "l1_rep_ask": r_a1,
                "l3_rep_bid": r_b3,
                "l3_rep_ask": r_a3,
                "latency_bid": self.tau_b,
                "latency_ask": self.tau_a,
                "s_canc": s_canc,
                "cvd_fast": cvd_fast,
                "trend_bps": trend_bps,
                "s_rep1": s_rep1,
                "s_rep3": s_rep3,
                "s_lat": s_lat,
                "qrl_core": qrl_core,
                "s_cvd": s_cvd,
                "trend_score": trend_score,
                "regime_flag": regime_flag,
                "r_b1": r_b1,
                "r_a1": r_a1,
                "r_b3": r_b3,
                "r_a3": r_a3,
                "tau_b": self.tau_b,
                "tau_a": self.tau_a,
                "c_b": c_b,
                "c_a": c_a,
                "total_vol_fast": total_vol_fast,
                "regime": regime_flag,
                "vpin_score": vpin_score,
                "vpin_raw": vpin_raw,
            },
        )
