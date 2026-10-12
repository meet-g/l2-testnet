"""Adaptive Machine Learning Alpha Signal combining online adaptive learning and trained models."""

import os
from typing import Any, Dict, Optional

import numpy as np

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from ml.features import FEATURE_NAMES, L2FeatureExtractor
from ml.online_learner import OnlineAdaptiveLearner
from signals.base import BaseSignal, SignalResult


class AdaptiveAlphaSignal(BaseSignal):
    """Machine Learning Alpha Signal that learns optimal feature combinations directly from the data.
    
    Modes:
    - 'ONLINE': Continuously updates weights tick-by-tick as forward returns mature (NLMS).
    - 'TRAINED': Uses offline cross-validated Ridge/Lasso weights from models/l2_trained_weights.json.
    - 'HYBRID': Initializes online learner with trained batch priors and updates adaptively.
    """

    def __init__(
        self,
        name: str = "AdaptiveMLAlpha",
        mode: str = "HYBRID",
        horizon_secs: float = 5.0,
        trained_weights_path: str = "models/l2_trained_weights.json",
    ):
        super().__init__(name)
        self.mode = mode.upper()
        self.horizon_secs = horizon_secs
        self.extractor = L2FeatureExtractor()
        self.trained_weights_path = trained_weights_path

        # Initialize online learner
        self.online_learner = OnlineAdaptiveLearner(horizon_secs=horizon_secs)

        # Attempt loading trained weights if available
        if os.path.exists(trained_weights_path):
            success = self.online_learner.load_weights(trained_weights_path)
            if success:
                print(f"[{name}] Loaded pre-trained weights from {trained_weights_path}")

        # Attempt loading LightGBM booster if available
        self.lgb_booster = None
        lgb_path = os.path.splitext(trained_weights_path)[0] + "_lgb.txt"
        if os.path.exists(lgb_path):
            try:
                import lightgbm as lgb
                self.lgb_booster = lgb.Booster(model_file=lgb_path)
                print(f"[{name}] Loaded pre-trained LightGBM booster from {lgb_path}")
            except Exception as e:
                print(f"[{name}] Warning: Failed to load LightGBM booster: {e}")

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        now_ms = timestamp_ms or book.last_update_time_ms
        current_price = book.mid_price

        # 1. Extract feature vector
        feats = self.extractor.extract_features(book, trades, now_ms)
        if feats is None:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        # LightGBM tree prediction for non-linear feature interaction
        lgb_bps = 0.0
        if self.lgb_booster is not None:
            try:
                lgb_bps = float(self.lgb_booster.predict(feats.reshape(1, -1))[0])
            except Exception:
                lgb_bps = 0.0

        # Ingest into online learner and blend with LightGBM
        if self.mode in ("ONLINE", "HYBRID"):
            pred_score = self.online_learner.ingest_observation(now_ms, current_price, feats)
            pred_bps = self.online_learner.predict(feats)
            if self.mode == "HYBRID" and self.lgb_booster is not None:
                lgb_score = float(np.tanh(lgb_bps / 0.75))
                # 60% LightGBM boosted trees + 40% adaptive online linear prior
                pred_score = 0.60 * lgb_score + 0.40 * pred_score
                pred_bps = 0.60 * lgb_bps + 0.40 * pred_bps
        elif self.mode == "LGBM" and self.lgb_booster is not None:
            pred_bps = lgb_bps
            pred_score = float(np.tanh(lgb_bps / 0.75))
        else:
            # TRAINED mode: static inference without online update
            pred_score = self.online_learner.predict_score(feats)
            pred_bps = self.online_learner.predict(feats)

        # Top predictive drivers for explainability
        top_features = self.online_learner.get_top_features(top_k=3)
        metrics = self.online_learner.get_online_metrics()

        confidence = min(1.0, 0.4 + (metrics["total_updates"] / 100.0) * 0.6)

        return SignalResult(
            name=self.name,
            score=max(-1.0, min(1.0, pred_score)),
            raw_value=pred_bps,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "predicted_return_bps": pred_bps,
                "lgb_predicted_bps": lgb_bps,
                "top_features": top_features,
                "total_updates": metrics["total_updates"],
                "recent_hit_rate": metrics["recent_hit_rate_pct"],
                "recent_mae_bps": metrics["recent_mae_bps"],
                "mode": self.mode,
            },
        )
