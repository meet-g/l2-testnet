"""Real-time online adaptive microstructure learner (Normalized LMS / SGD with L2 regularization)."""

from collections import deque
from dataclasses import dataclass, field
import json
import math
import os
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

from ml.features import FEATURE_NAMES


@dataclass
class PendingSample:
    sample_id: int
    timestamp_ms: int
    price: float
    features: np.ndarray
    predicted_return_bps: float


class OnlineAdaptiveLearner:
    """Online streaming learner for L2 microstructure that updates feature weights in real time.
    
    Uses Normalized Least Mean Squares (NLMS) with L2 regularization and exponential forgetting.
    Zero lookahead bias:
    1. At time t, receives feature vector x_t and predicts forward return y_hat_t.
    2. Buffers the sample.
    3. At time t + horizon_secs, observes the true price P_{t+h} and calculates actual return y_t.
    4. Updates weight vector w dynamically:
       w <- (1 - lambda * eta) * w + eta * (e_t / (||x_t||^2 + eps)) * x_t
    """

    def __init__(
        self,
        horizon_secs: float = 5.0,
        learning_rate: float = 0.05,
        l2_reg: float = 0.001,
        initial_weights: Optional[Dict[str, float]] = None,
    ):
        self.horizon_secs = horizon_secs
        self.learning_rate = learning_rate
        self.l2_reg = l2_reg
        self.n_features = len(FEATURE_NAMES)

        # Initialize weight vector
        self.weights = np.zeros(self.n_features, dtype=np.float64)
        if initial_weights:
            for i, name in enumerate(FEATURE_NAMES):
                if name in initial_weights:
                    self.weights[i] = initial_weights[name]
        else:
            # Sane default priors based on microstructure theory
            priors = {
                "wobi_5": 0.30,
                "microprice_drift": 0.25,
                "voi_zscore": 0.20,
                "cvd_30s_ratio": 0.15,
                "whale_wall_skew": 0.10,
            }
            for i, name in enumerate(FEATURE_NAMES):
                self.weights[i] = priors.get(name, 0.0)

        self.bias: float = 0.0

        # Pending observations awaiting forward return resolution
        self.pending_samples: Deque[PendingSample] = deque(maxlen=2000)
        self.sample_counter: int = 0

        # Online evaluation metrics
        self.total_updates: int = 0
        self.rolling_mse: float = 0.0
        self.correct_direction_count: int = 0
        self.recent_errors: Deque[float] = deque(maxlen=200)
        self.recent_hits: Deque[int] = deque(maxlen=200)

    def predict(self, features: np.ndarray) -> float:
        """Predicts forward return in basis points: y_hat = w . x + b."""
        return float(np.dot(self.weights, features) + self.bias)

    def predict_score(self, features: np.ndarray) -> float:
        """Normalized directional score in [-1.0, 1.0] using hyperbolic tangent."""
        pred_bps = self.predict(features)
        # 0.75 bps expected move maps to ~0.76 score
        return float(math.tanh(pred_bps / 0.75))

    def ingest_observation(
        self,
        timestamp_ms: int,
        current_price: float,
        features: np.ndarray,
    ) -> float:
        """Ingests new feature vector, generates prediction, and updates model on mature pending samples.
        
        Returns the current prediction score [-1.0, 1.0].
        """
        # 1. Update model on pending samples whose horizon has now elapsed
        self._update_mature_samples(timestamp_ms, current_price)

        # 2. Generate prediction for the current sample
        pred_bps = self.predict(features)
        pred_score = float(math.tanh(pred_bps / 0.75))

        # 3. Buffer current sample for future evaluation
        self.sample_counter += 1
        sample = PendingSample(
            sample_id=self.sample_counter,
            timestamp_ms=timestamp_ms,
            price=current_price,
            features=features.copy(),
            predicted_return_bps=pred_bps,
        )
        self.pending_samples.append(sample)

        return pred_score

    def _update_mature_samples(self, current_time_ms: int, current_price: float) -> None:
        """Resolves forward returns and updates online weights via NLMS."""
        horizon_ms = int(self.horizon_secs * 1000)

        while self.pending_samples:
            oldest = self.pending_samples[0]
            elapsed_ms = current_time_ms - oldest.timestamp_ms

            if elapsed_ms < horizon_ms:
                # Still within horizon, keep waiting
                break

            # Sample has matured! Pop from queue
            sample = self.pending_samples.popleft()

            # Calculate true forward return in basis points
            true_return_bps = ((current_price - sample.price) / sample.price) * 10_000.0

            # Error: e_t = y_t - y_hat_t
            error = true_return_bps - sample.predicted_return_bps

            # Directional hit test
            is_hit = 1 if (np.sign(sample.predicted_return_bps) == np.sign(true_return_bps)) else 0
            self.recent_hits.append(is_hit)
            self.recent_errors.append(abs(error))

            # NLMS update step:
            # w <- (1 - l2 * eta) * w + eta * (e / (||x||^2 + eps)) * x
            x = sample.features
            norm_sq = float(np.dot(x, x)) + 1e-4
            step = (self.learning_rate * error) / norm_sq

            # Weight shrinkage (L2 regularization)
            self.weights = (1.0 - self.l2_reg * self.learning_rate) * self.weights + (step * x)
            # Clip weights to prevent runaway parameters
            np.clip(self.weights, -2.5, 2.5, out=self.weights)

            # Bias update
            self.bias += self.learning_rate * error * 0.1
            self.bias = max(-2.0, min(2.0, self.bias))

            self.total_updates += 1

    def get_feature_weights(self) -> Dict[str, float]:
        """Returns mapping of feature names to current learned weights."""
        return {name: float(w) for name, w in zip(FEATURE_NAMES, self.weights)}

    def get_top_features(self, top_k: int = 5) -> List[Tuple[str, float]]:
        """Returns top k most influential features sorted by absolute weight."""
        sorted_pairs = sorted(
            zip(FEATURE_NAMES, self.weights),
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        return [(name, float(w)) for name, w in sorted_pairs[:top_k]]

    def get_online_metrics(self) -> Dict[str, Any]:
        """Returns online learning performance statistics."""
        hit_rate = (sum(self.recent_hits) / len(self.recent_hits) * 100.0) if self.recent_hits else 50.0
        mae_bps = (sum(self.recent_errors) / len(self.recent_errors)) if self.recent_errors else 0.0

        return {
            "total_updates": self.total_updates,
            "pending_samples": len(self.pending_samples),
            "recent_hit_rate_pct": hit_rate,
            "recent_mae_bps": mae_bps,
            "bias": self.bias,
            "weights": self.get_feature_weights(),
        }

    def save_weights(self, filepath: str) -> None:
        """Saves current learned weights to a JSON file."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "horizon_secs": self.horizon_secs,
            "total_updates": self.total_updates,
            "bias": self.bias,
            "weights": self.get_feature_weights(),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def load_weights(self, filepath: str) -> bool:
        """Loads weights from a JSON file."""
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                payload = json.load(f)
            loaded_w = payload.get("weights", {})
            for i, name in enumerate(FEATURE_NAMES):
                if name in loaded_w:
                    self.weights[i] = loaded_w[name]
            self.bias = float(payload.get("bias", 0.0))
            return True
        except Exception:
            return False
