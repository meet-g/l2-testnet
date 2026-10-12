"""Offline batch training pipeline: Ridge, Lasso, and Logistic Regression on recorded L2 data."""

import glob
import json
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats
from sklearn.linear_model import ElasticNetCV, LogisticRegression, RidgeCV
from sklearn.preprocessing import StandardScaler

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from ml.features import FEATURE_NAMES, L2FeatureExtractor


class L2DatasetBuilder:
    """Replays recorded L2 session files and constructs aligned (Features, Forward Return) datasets."""

    def __init__(self, data_dir: str = "data", coin: str = "BTC", horizon_secs: float = 5.0, sample_interval_ms: int = 200):
        self.data_dir = data_dir
        self.coin = coin.lower()
        self.horizon_secs = horizon_secs
        self.sample_interval_ms = sample_interval_ms
        self.extractor = L2FeatureExtractor()

    def build_dataset_from_files(self, filepaths: Optional[List[str]] = None, max_files: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray, List[int]]:
        """Processes recorded JSONL files and returns (X, y, timestamps)."""
        if not filepaths:
            # 1. Search coin subfolder: data/btc/hl_btc_l2_*.jsonl
            coin_dir = os.path.join(self.data_dir, self.coin)
            if os.path.isdir(coin_dir):
                filepaths = sorted(glob.glob(os.path.join(coin_dir, f"hl_{self.coin}_l2_*.jsonl")))
                if not filepaths:
                    filepaths = sorted(glob.glob(os.path.join(coin_dir, "*.jsonl")))

            # 2. Check uppercase coin subfolder: data/BTC/
            if not filepaths:
                coin_dir_upper = os.path.join(self.data_dir, self.coin.upper())
                if os.path.isdir(coin_dir_upper):
                    filepaths = sorted(glob.glob(os.path.join(coin_dir_upper, f"hl_{self.coin}_l2_*.jsonl")))
                    if not filepaths:
                        filepaths = sorted(glob.glob(os.path.join(coin_dir_upper, "*.jsonl")))

            # 3. Fallback to base data_dir: data/hl_btc_l2_*.jsonl
            if not filepaths:
                pattern = os.path.join(self.data_dir, f"hl_{self.coin}_l2_*.jsonl")
                filepaths = sorted(glob.glob(pattern))

            if not filepaths:
                filepaths = sorted(glob.glob(os.path.join(self.data_dir, "*.jsonl")))

            # 4. Recursive search
            if not filepaths:
                filepaths = sorted(glob.glob(os.path.join(self.data_dir, "**", f"hl_{self.coin}_l2_*.jsonl"), recursive=True))

            # Exclude quarantined snippets
            if filepaths:
                filepaths = [f for f in filepaths if "snippets" not in f.replace("\\", "/").split("/")]

        if not filepaths:
            raise FileNotFoundError(f"No JSONL recording files found for {self.coin.upper()} in {self.data_dir}")

        if max_files and len(filepaths) > max_files:
            step = max(1, len(filepaths) // max_files)
            filepaths = filepaths[::step][:max_files]

        raw_observations: List[Tuple[int, float, np.ndarray]] = []

        for fpath in filepaths:
            print(f"Ingesting {os.path.basename(fpath)}...")
            book = OrderBook(coin=self.coin.upper())
            trades = TradeManager(coin=self.coin.upper())
            last_sample_t = 0
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except Exception:
                        continue
                    ch = event.get("channel")
                    dt = event.get("data")
                    recv_ts = event.get("recv_ts", int(time.time() * 1000))

                    if ch == "l2Book":
                        book.update_from_raw(dt)
                    elif ch == "trades":
                        trades.process_raw_trades(dt)
                    elif ch == "activeAssetCtx":
                        book.update_asset_ctx(dt)

                    if book.is_valid and (recv_ts - last_sample_t) >= self.sample_interval_ms:
                        feats = self.extractor.extract_features(book, trades, recv_ts)
                        if feats is not None:
                            raw_observations.append((recv_ts, book.mid_price, feats))
                            last_sample_t = recv_ts

        print(f"Extracted {len(raw_observations)} raw observations. Aligning with {self.horizon_secs}s forward returns...")

        # Match with forward returns
        X_list = []
        y_list = []
        ts_list = []

        horizon_ms = int(self.horizon_secs * 1000)
        n_obs = len(raw_observations)

        # Two-pointer matching
        j = 0
        for i in range(n_obs):
            t_i, p_i, x_i = raw_observations[i]
            target_t = t_i + horizon_ms

            # Advance j until t_j >= target_t
            while j < n_obs and raw_observations[j][0] < target_t:
                j += 1

            if j >= n_obs:
                break

            t_j, p_j, _ = raw_observations[j]
            # Ensure time gap is within tolerance (e.g. +/- 500ms)
            if abs(t_j - target_t) <= 600:
                ret_bps = ((p_j - p_i) / p_i) * 10_000.0
                X_list.append(x_i)
                y_list.append(ret_bps)
                ts_list.append(t_i)

        if not X_list:
            raise ValueError("Insufficient observations to form target returns.")

        X = np.array(X_list, dtype=np.float64)
        y = np.array(y_list, dtype=np.float64)
        return X, y, ts_list


class L2BatchTrainer:
    """Trains regularized Machine Learning models on historical L2 features and evaluates out-of-sample edge."""

    def __init__(self, horizon_secs: float = 5.0):
        self.horizon_secs = horizon_secs
        self.scaler = StandardScaler()
        self.model: Optional[RidgeCV] = None
        self.weights: Dict[str, float] = {}

    def train_and_evaluate(
        self,
        X: np.ndarray,
        y: np.ndarray,
        test_size: float = 0.25,
    ) -> Dict[str, Any]:
        """Performs time-series train/test split with purge embargo, trains Ridge model, and computes metrics."""
        n = len(X)
        split_idx = int(n * (1.0 - test_size))

        # Purge window to prevent leakage
        purge_samples = 25  # ~5 seconds of buffer
        train_end = split_idx - purge_samples

        X_train, y_train = X[:train_end], y[:train_end]
        X_test, y_test = X[split_idx:], y[split_idx:]

        print(f"Train samples: {len(X_train)} | Test samples: {len(X_test)} (Purged {purge_samples} samples)")

        # Standardize features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Fit Ridge regression with CV on alpha
        alphas = np.logspace(-3, 3, 20)
        self.model = RidgeCV(alphas=alphas)
        self.model.fit(X_train_scaled, y_train)

        # Fit LightGBM Gradient Boosted Trees (handles non-linear interactions directly)
        import lightgbm as lgb
        self.lgb_model = lgb.LGBMRegressor(
            n_estimators=100,
            learning_rate=0.03,
            num_leaves=15,
            max_depth=4,
            min_child_samples=15,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            verbose=-1,
        )
        self.lgb_model.fit(X_train, y_train)

        # In-Sample & Out-of-Sample Predictions - Ridge
        y_train_pred_ridge = self.model.predict(X_train_scaled)
        y_test_pred_ridge = self.model.predict(X_test_scaled)

        # In-Sample & Out-of-Sample Predictions - LightGBM
        y_train_pred_lgb = self.lgb_model.predict(X_train)
        y_test_pred_lgb = self.lgb_model.predict(X_test)

        # Metrics - Ridge
        is_ic_ridge, _ = stats.pearsonr(y_train_pred_ridge, y_train) if np.std(y_train_pred_ridge) > 1e-7 else (0.0, 1.0)
        oos_ic_ridge, _ = stats.pearsonr(y_test_pred_ridge, y_test) if np.std(y_test_pred_ridge) > 1e-7 else (0.0, 1.0)
        oos_rank_ic_ridge, _ = stats.spearmanr(y_test_pred_ridge, y_test) if np.std(y_test_pred_ridge) > 1e-7 else (0.0, 1.0)
        oos_hits_ridge = np.mean(np.sign(y_test_pred_ridge) == np.sign(y_test)) * 100.0

        # Metrics - LightGBM
        is_ic_lgb, _ = stats.pearsonr(y_train_pred_lgb, y_train) if np.std(y_train_pred_lgb) > 1e-7 else (0.0, 1.0)
        oos_ic_lgb, _ = stats.pearsonr(y_test_pred_lgb, y_test) if np.std(y_test_pred_lgb) > 1e-7 else (0.0, 1.0)
        oos_rank_ic_lgb, _ = stats.spearmanr(y_test_pred_lgb, y_test) if np.std(y_test_pred_lgb) > 1e-7 else (0.0, 1.0)
        oos_hits_lgb = np.mean(np.sign(y_test_pred_lgb) == np.sign(y_test)) * 100.0

        # Active move directional hit rates (conditioned on |ret| > 0.01 bps)
        active_mask = np.abs(y_test) > 0.01
        oos_hits_ridge_active = float(np.mean(np.sign(y_test_pred_ridge[active_mask]) == np.sign(y_test[active_mask])) * 100.0) if np.sum(active_mask) > 10 else 50.0
        oos_hits_lgb_active = float(np.mean(np.sign(y_test_pred_lgb[active_mask]) == np.sign(y_test[active_mask])) * 100.0) if np.sum(active_mask) > 10 else 50.0

        # Robust unscaling to natural feature space
        safe_scales = np.maximum(self.scaler.scale_, 0.10)
        orig_weights = self.model.coef_ / safe_scales
        orig_weights = np.clip(orig_weights, -2.0, 2.0)
        self.weights = {name: float(w) for name, w in zip(FEATURE_NAMES, orig_weights)}

        unscaled_bias = float(self.model.intercept_ - np.sum(orig_weights * self.scaler.mean_))
        unscaled_bias = max(-5.0, min(5.0, unscaled_bias))
        self.bias = unscaled_bias

        # LightGBM feature importances (split gain)
        lgb_importances = self.lgb_model.feature_importances_
        lgb_importance_ranked = sorted(
            zip(FEATURE_NAMES, lgb_importances),
            key=lambda x: x[1],
            reverse=True,
        )

        sorted_importance = sorted(
            zip(FEATURE_NAMES, np.abs(self.model.coef_)),
            key=lambda x: x[1],
            reverse=True,
        )

        results = {
            "horizon_secs": self.horizon_secs,
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "best_alpha": float(self.model.alpha_),
            "in_sample_ic": float(is_ic_ridge),
            "out_of_sample_ic": float(oos_ic_ridge),
            "out_of_sample_rank_ic": float(oos_rank_ic_ridge),
            "out_of_sample_hit_rate_pct": float(oos_hits_ridge),
            "out_of_sample_active_hit_rate_pct": float(oos_hits_ridge_active),
            "ridge": {
                "in_sample_ic": float(is_ic_ridge),
                "out_of_sample_ic": float(oos_ic_ridge),
                "out_of_sample_rank_ic": float(oos_rank_ic_ridge),
                "out_of_sample_hit_rate_pct": float(oos_hits_ridge),
                "out_of_sample_active_hit_rate_pct": float(oos_hits_ridge_active),
            },
            "lightgbm": {
                "in_sample_ic": float(is_ic_lgb),
                "out_of_sample_ic": float(oos_ic_lgb),
                "out_of_sample_rank_ic": float(oos_rank_ic_lgb),
                "out_of_sample_hit_rate_pct": float(oos_hits_lgb),
                "out_of_sample_active_hit_rate_pct": float(oos_hits_lgb_active),
                "importance_ranked": [(name, float(imp)) for name, imp in lgb_importance_ranked],
            },
            "feature_weights": self.weights,
            "feature_importance_ranked": [(name, float(imp)) for name, imp in sorted_importance],
        }
        return results

    def save_model(self, filepath: str = "models/l2_trained_weights.json") -> None:
        """Saves model weights and scaling parameters, as well as LightGBM booster."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "horizon_secs": self.horizon_secs,
            "bias": self.bias,
            "weights": self.weights,
            "scaler_means": {name: float(m) for name, m in zip(FEATURE_NAMES, self.scaler.mean_)},
            "scaler_scales": {name: float(s) for name, s in zip(FEATURE_NAMES, self.scaler.scale_)},
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"Linear model saved to {filepath}")

        if hasattr(self, "lgb_model") and self.lgb_model is not None:
            lgb_path = os.path.splitext(filepath)[0] + "_lgb.txt"
            self.lgb_model.booster_.save_model(lgb_path)
            print(f"LightGBM booster saved to {lgb_path}")
