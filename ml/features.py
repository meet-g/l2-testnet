"""Feature extraction pipeline transforming raw L2 OrderBook and Trade streams into standardized ML feature vectors."""

from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.absorption import AbsorptionSignal
from signals.microprice import MicroPriceSignal
from signals.voi import VOISignal
from signals.vpin import VPINSignal
from signals.wobi import WOBISignal


FEATURE_NAMES = [
    "wobi_1",               # Top of book depth imbalance [-1, 1]
    "wobi_5",               # 5-level exponentially weighted imbalance [-1, 1]
    "wobi_20",              # 20-level distance weighted imbalance [-1, 1]
    "order_count_imb_5",    # Order count density imbalance [-1, 1]
    "whale_wall_skew",      # Anti-spoofing filtered whale wall imbalance [-1, 1]
    "voi_zscore",           # Volume Order Imbalance standardized score [-1, 1]
    "microprice_drift",     # Stoikov micro-price drift relative to half-spread [-1, 1]
    "spread_bps",           # Current bid-ask spread in basis points [0, inf)
    "depth_log_ratio",      # Log ratio of total 20-level bid depth to ask depth
    "cvd_30s_ratio",        # 30-second Cumulative Volume Delta normalized ratio [-1, 1]
    "vpin_toxicity",        # Easley-Lopez de Prado VPIN toxicity [0, 1]
    "vpin_signed_flow",     # Directional toxic order flow [-1, 1]
]


class L2FeatureExtractor:
    """Extracts a comprehensive vector of stationary, standardized microstructure features from live L2 book & trades."""

    def __init__(self):
        self.wobi_sig = WOBISignal()
        self.voi_sig = VOISignal()
        self.micro_sig = MicroPriceSignal()
        self.vpin_sig = VPINSignal()
        self.abs_sig = AbsorptionSignal()

    def extract_features(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> Optional[np.ndarray]:
        """Returns 1D numpy array of features corresponding to FEATURE_NAMES, or None if book is invalid."""
        if not book.is_valid:
            return None

        now_ms = timestamp_ms or book.last_update_time_ms

        # 1. WOBI features
        tob_b, tob_a = book.best_bid_sz, book.best_ask_sz
        wobi_1 = (tob_b - tob_a) / max(tob_b + tob_a, 1e-8)
        wobi_5 = book.weighted_imbalance(k_levels=5, decay_lambda=0.35)
        wobi_20 = book.distance_weighted_imbalance(k_levels=20)
        order_count_imb_5 = book.order_count_imbalance(k_levels=5)

        wobi_res = self.wobi_sig.compute(book, trades, now_ms)
        whale_wall_skew = wobi_res.score

        # 2. VOI feature
        voi_res = self.voi_sig.compute(book, trades, now_ms)
        voi_zscore = voi_res.score

        # 3. MicroPrice drift
        mp_res = self.micro_sig.compute(book, trades, now_ms)
        microprice_drift = mp_res.score

        # 4. Spread and depth ratio (excess spread beyond 1-tick minimum)
        spread_bps = max(0.0, book.spread - 1.0)
        tot_b_20, tot_a_20 = book.get_depth_volume(20)
        depth_log_ratio = math.log(max(tot_b_20, 0.01) / max(tot_a_20, 0.01))
        # Clip depth ratio to [-2.5, 2.5]
        depth_log_ratio = max(-2.5, min(2.5, depth_log_ratio))

        # 5. CVD Absorption & Delta
        abs_res = self.abs_sig.compute(book, trades, now_ms)
        cvd_30s_ratio = abs_res.raw_value

        # 6. VPIN toxicity
        vpin_res = self.vpin_sig.compute(book, trades, now_ms)
        vpin_toxicity = vpin_res.raw_value
        vpin_signed_flow = vpin_res.score

        features = np.array([
            wobi_1,
            wobi_5,
            wobi_20,
            order_count_imb_5,
            whale_wall_skew,
            voi_zscore,
            microprice_drift,
            spread_bps,
            depth_log_ratio,
            cvd_30s_ratio,
            vpin_toxicity,
            vpin_signed_flow,
        ], dtype=np.float64)

        # Replace any potential NaNs or Infs
        np.nan_to_num(features, copy=False, nan=0.0, posinf=1.0, neginf=-1.0)
        return features

    def get_feature_dict(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> Dict[str, float]:
        """Convenience method returning named dictionary of feature values."""
        arr = self.extract_features(book, trades, timestamp_ms)
        if arr is None:
            return {name: 0.0 for name in FEATURE_NAMES}
        return {name: float(val) for name, val in zip(FEATURE_NAMES, arr)}
