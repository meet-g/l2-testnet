"""Momentum Expansion Alpha Signal (Empirically Calibrated & Multi-Depth Enhanced):
Combines multi-tier order book queue exhaustion, 25-level decayed depth support,
dual-horizon CVD acceleration, and active absorption trap protection to capture
structural momentum expansions while rigorously overcoming exchange fee hurdles.
"""

import bisect
from collections import deque
import math
from typing import Any, Deque, Dict, List, Optional, Tuple

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult
from signals.vpin import VPINSignal


class MomentumExpansionSignal(BaseSignal):
    """Detects high-conviction directional expansions where acute order book queue exhaustion
    coincides with aggressive taker order flow acceleration and deep resting book support,
    while actively shielding against institutional limit wall absorption traps.
    """

    def __init__(
        self,
        name: str = "MomentumExpansion",
        cvd_fast_secs: float = 15.0,
        cvd_slow_secs: float = 60.0,
        trend_window_secs: float = 120.0,
        cvd_fast_scale_btc: float = 1.5,
        cvd_slow_scale_btc: float = 4.0,
        trend_scale_bps: float = 6.0,
        w_book: float = 0.50,
        w_flow: float = 0.35,
        w_trend: float = 0.15,
        decay_lambda: float = 0.12,
        absorption_hurdle: float = 0.15,
        flow_hurdle: float = 0.35,
        min_trade_vol_window: float = 8.0,
    ):
        super().__init__(name)
        self.cvd_fast_secs = cvd_fast_secs
        self.cvd_slow_secs = cvd_slow_secs
        self.trend_window_secs = trend_window_secs
        self.cvd_fast_scale_btc = cvd_fast_scale_btc
        self.cvd_slow_scale_btc = cvd_slow_scale_btc
        self.trend_scale_bps = trend_scale_bps

        self.w_book = w_book
        self.w_flow = w_flow
        self.w_trend = w_trend
        self.decay_lambda = decay_lambda
        self.absorption_hurdle = absorption_hurdle
        self.flow_hurdle = flow_hurdle
        self.min_trade_vol_window = min_trade_vol_window

        self.vpin = VPINSignal()
        self.price_history: List[Tuple[int, float]] = []
        self._head_idx: int = 0
        self.depth_history: Deque[Tuple[int, float, float]] = deque(maxlen=60)

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        now_ms = timestamp_ms or book.last_update_time_ms

        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0, timestamp_ms=now_ms)

        mid_price = book.mid_price
        self.price_history.append((now_ms, mid_price))

        # Evict history beyond 10 minutes
        cutoff_ms = now_ms - 600_000
        while self._head_idx < len(self.price_history) and self.price_history[self._head_idx][0] < cutoff_ms:
            self._head_idx += 1

        if self._head_idx > 1000:
            self.price_history = self.price_history[self._head_idx:]
            self._head_idx = 0

        bids = book.bids
        asks = book.asks
        n_bids = len(bids)
        n_asks = len(asks)

        scale = getattr(book, "notional_scale", 1.0)
        is_btc = (book.coin.upper() == "BTC")
        depth_scale = 1.0 if is_btc else 0.15
        eff_scale = scale * depth_scale

        # ---------------------------------------------------------------------
        # 1. Multi-Tier Order Book Depth & Density (Levels 1-25)
        # ---------------------------------------------------------------------
        # A. Touch Queue Exhaustion: log(Q_b1 / Q_a1)
        b_sz_1 = bids[0].sz if n_bids > 0 else 0.01 * eff_scale
        a_sz_1 = asks[0].sz if n_asks > 0 else 0.01 * eff_scale
        qr = math.log(max(b_sz_1, 0.005 * eff_scale) / max(a_sz_1, 0.005 * eff_scale))
        touch_exhaustion = math.tanh(0.40 * qr)

        # B. Multi-Level Decayed Depth Imbalance (Up to 25 levels)
        k_levels = min(25, n_bids, n_asks)
        w_bids = 0.0
        w_asks = 0.0
        for i in range(k_levels):
            w = math.exp(-self.decay_lambda * i)
            w_bids += bids[i].sz * w
            w_asks += asks[i].sz * w
        denom_w = w_bids + w_asks
        wobi_score = (w_bids - w_asks) / max(denom_w, 1e-6)

        # C. Order Count Imbalance across all available levels (Anti-Whale Dispersion)
        tot_b_n = sum(bids[i].n for i in range(k_levels))
        tot_a_n = sum(asks[i].n for i in range(k_levels))
        n_imb_score = (tot_b_n - tot_a_n) / max(tot_b_n + tot_a_n, 1)

        # D. Macro Order Book Support (if available from nSigFigs=4 runtime pull)
        macro_score = 0.0
        if book.has_macro_book:
            macro_score = book.macro_weighted_imbalance(k_levels=20, decay_lambda=0.10)

        # Depth Tracking & Anti-Spoofing
        d5_b = sum(b.sz for b in bids[:min(5, n_bids)])
        d5_a = sum(a.sz for a in asks[:min(5, n_asks)])

        self.depth_history.append((now_ms, d5_b, d5_a))
        wall_drop_b = False
        wall_drop_a = False
        if len(self.depth_history) >= 10:
            past_b = self.depth_history[0][1]
            past_a = self.depth_history[0][2]
            if past_b > 2.0 * eff_scale and d5_b < past_b * 0.45:
                wall_drop_b = True
            if past_a > 2.0 * eff_scale and d5_a < past_a * 0.45:
                wall_drop_a = True

        s_hole = 0.0
        if b_sz_1 >= 2.0 * eff_scale and (d5_b - b_sz_1) < 0.8 * eff_scale:
            s_hole -= 0.20
        if a_sz_1 >= 2.0 * eff_scale and (d5_a - a_sz_1) < 0.8 * eff_scale:
            s_hole += 0.20

        # Anti-Whale Spoofing Check:
        is_spoof_trap = (wobi_score > 0.35 and n_imb_score < -0.15) or (wobi_score < -0.35 and n_imb_score > 0.15)

        # Composite Book Structure Score (Empirical IC > +0.30)
        if book.has_macro_book:
            book_score = (
                0.35 * wobi_score
                + 0.25 * touch_exhaustion
                + 0.20 * n_imb_score
                + 0.20 * macro_score
                + s_hole
            )
        else:
            book_score = (
                0.45 * wobi_score
                + 0.30 * touch_exhaustion
                + 0.25 * n_imb_score
                + s_hole
            )
        if is_spoof_trap:
            book_score *= 0.3

        # Clamp book_score to prevent s_hole from distorting the composite beyond [-1, 1]
        book_score = max(-1.0, min(1.0, book_score))

        # ---------------------------------------------------------------------
        # 2. Dual-Horizon Taker Order Flow Momentum & Acceleration (CVD Delta)
        # ---------------------------------------------------------------------
        cvd_fast, buy_fast, sell_fast = trades.get_cvd_in_window(self.cvd_fast_secs)
        cvd_slow, buy_slow, sell_slow = trades.get_cvd_in_window(self.cvd_slow_secs)
        tot_vol_slow = buy_slow + sell_slow

        flow_fast = math.tanh(cvd_fast / max(self.cvd_fast_scale_btc * eff_scale, 0.1 * eff_scale))
        flow_slow = math.tanh(cvd_slow / max(self.cvd_slow_scale_btc * eff_scale, 0.5 * eff_scale))

        # Composite flow: 65% fast impulse + 35% sustained trend
        flow_score = 0.65 * flow_fast + 0.35 * flow_slow

        # ---------------------------------------------------------------------
        # 3. Medium-Term Trend Alignment (2-minute price drift)
        # ---------------------------------------------------------------------
        trend_cutoff = now_ms - int(self.trend_window_secs * 1000)
        idx = bisect.bisect_left(self.price_history, (trend_cutoff, -1.0), lo=self._head_idx)
        if idx < len(self.price_history):
            past_price = self.price_history[idx][1]
        else:
            past_price = self.price_history[self._head_idx][1]
        if past_price > 0:
            trend_bps = ((mid_price - past_price) / past_price) * 10_000.0
            trend_score = math.tanh(trend_bps / max(self.trend_scale_bps, 1.0))
        else:
            trend_score = 0.0

        # ---------------------------------------------------------------------
        # 4. Active Absorption Trap Shield & Confluence Gating
        # ---------------------------------------------------------------------
        is_bull_trap = (flow_score > 0.12 and book_score < -self.absorption_hurdle)
        is_bear_trap = (flow_score < -0.12 and book_score > self.absorption_hurdle)

        # Climax Exhaustion Check:
        is_exhaustion_climax = (trend_score > 0.85 and flow_score > 0.70) or (trend_score < -0.85 and flow_score < -0.70)

        # Strict Confluence check: active taker volume must be present and aligned with book pressure and trend
        has_active_flow = abs(flow_score) >= self.flow_hurdle
        has_min_volume = (tot_vol_slow >= self.min_trade_vol_window * eff_scale) if self.min_trade_vol_window > 0 else True
        trend_aligned = (flow_score > 0 and trend_score >= -0.02) or (flow_score < 0 and trend_score <= 0.02)
        direction_agree = (book_score * flow_score > 0) and has_active_flow and has_min_volume and trend_aligned
        # Counter-trend suppression: suppress momentum entries against macro trend
        strong_counter_trend = (flow_score > 0.12 and trend_score < -0.10) or (flow_score < -0.12 and trend_score > 0.10)

        absorption_flag = "NONE"

        if is_bull_trap:
            # Veto long and flip to negative / absorption warning
            raw_score = -0.35
            confidence = 0.70
            absorption_flag = "BULL_ABSORPTION_TRAP"
        elif is_bear_trap:
            # Veto short and flip to positive / bounce warning
            raw_score = 0.35
            confidence = 0.70
            absorption_flag = "BEAR_ABSORPTION_TRAP"
        elif is_exhaustion_climax:
            raw_score = max(-0.30, min(0.30, 0.20 * book_score))
            confidence = 0.20
            absorption_flag = "EXHAUSTION_CLIMAX_SUPPRESSED"
        elif strong_counter_trend:
            raw_score = max(-0.25, min(0.25, 0.15 * book_score))
            confidence = 0.15
            absorption_flag = "COUNTER_TREND_SUPPRESSED"
        elif direction_agree and not is_spoof_trap:
            # Pure Momentum Confluence: flow and book in full agreement
            raw_score = (
                self.w_book * book_score
                + self.w_flow * flow_score
                + self.w_trend * trend_score
            )
            confidence = (
                0.40 * abs(book_score)
                + 0.35 * abs(flow_score)
                + 0.25 * abs(trend_score)
            )
            absorption_flag = "CONFLUENCE_EXPANSION"
        else:
            # Conflicting signals or weak volume: strictly cap below entry threshold
            raw_score = max(-0.40, min(0.40, 0.20 * (self.w_book * book_score + self.w_flow * flow_score)))
            confidence = 0.20
        # VPIN Toxicity Shield:
        # If order flow is toxic (VPIN >= 0.60), informed sweeps wipe out passive makers.
        vpin_res = self.vpin.compute(book, trades, now_ms)
        is_toxic = vpin_res.metadata.get("is_toxic", False)
        if is_toxic:
            raw_score = max(-0.30, min(0.30, raw_score * 0.15))

        # Directional Toxicity Shield: Protect passive maker entries from informed adverse selection
        vpin_score = vpin_res.score
        if raw_score > 0 and vpin_score < -0.20:
            adverse_drag = min(1.0, abs(vpin_score) / 0.45)
            raw_score *= (1.0 - 0.75 * adverse_drag)
            if vpin_score < -0.35:
                raw_score = min(raw_score, 0.10)
        elif raw_score < 0 and vpin_score > 0.20:
            adverse_drag = min(1.0, abs(vpin_score) / 0.45)
            raw_score *= (1.0 - 0.75 * adverse_drag)
            if vpin_score > 0.35:
                raw_score = max(raw_score, -0.10)

        # Depth Fragility Shield: if resting wall was rapidly pulled (spoof decay), dampen alpha
        if (raw_score > 0 and wall_drop_b) or (raw_score < 0 and wall_drop_a):
            raw_score = max(-0.30, min(0.30, raw_score * 0.20))

        score = max(-1.0, min(1.0, raw_score))
        confidence = max(0.1, min(1.0, confidence))

        # Check touch queue exhaustion condition
        is_ask_depleted = (a_sz_1 < 0.8 * scale and b_sz_1 > 2.0 * scale)
        is_bid_depleted = (b_sz_1 < 0.8 * scale and a_sz_1 > 2.0 * scale)

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=raw_score,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "book_score": book_score,
                "wobi_score": wobi_score,
                "n_imb_score": n_imb_score,
                "touch_exhaustion": touch_exhaustion,
                "macro_score": macro_score,
                "flow_fast": flow_fast,
                "flow_slow": flow_slow,
                "flow_score": flow_score,
                "trend_score": trend_score,
                "cvd_fast_btc": cvd_fast,
                "cvd_slow_btc": cvd_slow,
                "tot_vol_slow": tot_vol_slow,
                "flow_hurdle": self.flow_hurdle,
                "min_trade_vol_window": self.min_trade_vol_window,
                "absorption_flag": absorption_flag,
                "is_ask_depleted": is_ask_depleted,
                "is_bid_depleted": is_bid_depleted,
            },
        )
