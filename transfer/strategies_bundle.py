"""Hyperliquid L2 Microstructure Alpha Engine - Complete Migration Strategy Bundle.

This is a self-contained, zero-dependency (standard library + numpy; optional scipy and lightgbm)
module containing all core L2 data structures, 8 alpha signals, 12-factor feature extractor,
online NLMS adaptive learner, configuration schemas, and dual execution engine / backtester.

Components included:
1. Core Data Models: L2Level, BookSnapshot, OrderBook, Trade, VolumeBucket, TradeManager
2. Signal Protocol: SignalResult, BaseSignal
3. Microstructure Alpha Signals:
   - WOBISignal (Multi-Level Weighted Order Book Imbalance with Anti-Spoofing Density)
   - VOISignal (Volume Order Imbalance with Cont-Kukanov-Stoikov state transitions)
   - MicroPriceSignal (Stoikov Fair-Value Micro-Price with Power Transform)
   - VPINSignal (Easley-Lopez de Prado-O'Hara Volume Toxicity Probability)
   - AbsorptionSignal (CVD Limit Order Absorption & Divergence Detector)
   - SweepSignal (Book Sweep & Post-Impact Replenishment Elasticity)
   - AdaptiveAlphaSignal (12-Factor ML with Online NLMS & Pre-Trained Ridge / LightGBM)
   - CompositeAlphaSignal (Dynamic Regime-Switching Ensemble with Sweep Kick)
4. ML Pipeline: FEATURE_NAMES, L2FeatureExtractor, OnlineAdaptiveLearner
5. Configuration Schemas: HyperliquidConfig, MarketConfig, SignalConfig, BacktestConfig, AppConfig
6. Dual Execution & Backtester: TradeRecord, StrategyState, SignalObservation, EdgeEvaluator, StrategyExecutionEngine
"""

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
import json
import math
import os
import time
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

import numpy as np

# Optional scientific imports with graceful fallbacks
try:
    from scipy import stats
    _HAS_SCIPY = True
except ImportError:
    stats = None
    _HAS_SCIPY = False

try:
    import lightgbm as lgb
    _HAS_LIGHTGBM = True
except ImportError:
    lgb = None
    _HAS_LIGHTGBM = False


# =============================================================================
# 1. CONFIGURATION SCHEMAS
# =============================================================================

@dataclass
class HyperliquidConfig:
    """Hyperliquid network connection parameters."""
    MAINNET_WS_URL: str = "wss://api.hyperliquid.xyz/ws"
    MAINNET_REST_URL: str = "https://api.hyperliquid.xyz/info"
    TESTNET_WS_URL: str = "wss://api.hyperliquid-testnet.xyz/ws"
    TESTNET_REST_URL: str = "https://api.hyperliquid-testnet.xyz/info"
    use_testnet: bool = False

    @property
    def ws_url(self) -> str:
        return self.TESTNET_WS_URL if self.use_testnet else self.MAINNET_WS_URL

    @property
    def rest_url(self) -> str:
        return self.TESTNET_REST_URL if self.use_testnet else self.MAINNET_REST_URL


@dataclass
class MarketConfig:
    """Market specifications and exchange fee schedules."""
    coin: str = "BTC"
    depth_levels: int = 20
    tick_size: float = 1.0
    lot_size: float = 0.0001
    taker_fee_bps: float = 3.5      # 0.035% taker fee
    maker_rebate_bps: float = -0.2  # -0.002% maker rebate (positive = fee, negative = rebate)


@dataclass
class SignalConfig:
    """Hyperparameters for all 8 alpha signal models."""
    # 1. WOBI
    wobi_decay_lambda: float = 0.35
    wobi_depth_tiers: List[int] = field(default_factory=lambda: [1, 5, 10, 20])
    whale_min_sz_btc: float = 5.0
    whale_concentration_threshold: float = 2.0

    # 2. VOI
    voi_rolling_window_secs: float = 10.0
    voi_zscore_window: int = 60

    # 3. MicroPrice
    microprice_adj_factor: float = 0.5
    microprice_gamma: float = 0.85

    # 4. VPIN
    vpin_bucket_size_btc: float = 5.0
    vpin_window_buckets: int = 30
    vpin_toxic_threshold: float = 0.65

    # 5. CVD Absorption
    cvd_window_secs: float = 30.0
    cvd_zscore_threshold: float = 2.0
    absorption_ratio_threshold: float = 2.5

    # 6. Sweep Elasticity
    sweep_min_levels: int = 2
    sweep_min_sz_btc: float = 1.5
    replenishment_eval_ms: int = 500

    # 7. Composite Alpha Weights (Normal Regime)
    weight_wobi: float = 0.25
    weight_voi: float = 0.25
    weight_microprice: float = 0.20
    weight_cvd_absorption: float = 0.15
    weight_vpin: float = 0.15


@dataclass
class BacktestConfig:
    """Execution simulation, fee gating, and risk management parameters."""
    horizons_seconds: List[int] = field(default_factory=lambda: [1, 3, 5, 10, 30, 60])
    initial_cash_usd: float = 10_000.0
    order_size_btc: float = 0.1
    max_position_btc: float = 0.5
    default_execution_mode: str = "MAKER"
    slippage_bps: float = 0.2
    max_spread_bps: float = 1.5

    # Passive Maker Execution (Avellaneda-Stoikov Micro-Scalp)
    entry_threshold: float = 0.35
    take_profit_bps: float = 2.0
    stop_loss_bps: float = 5.0
    trailing_stop_activation_bps: float = 1.0
    trailing_stop_distance_bps: float = 1.0
    exit_reversal_threshold: float = 0.25
    max_holding_time_secs: int = 20

    # Smart Taker Execution (High-Conviction Dislocation & Momentum)
    entry_threshold_taker: float = 0.50
    take_profit_bps_taker: float = 12.0
    stop_loss_bps_taker: float = 8.0
    trailing_stop_activation_bps_taker: float = 7.0
    trailing_stop_distance_bps_taker: float = 3.0
    exit_reversal_threshold_taker: float = 0.40
    max_holding_time_secs_taker: int = 60
    taker_exit_as_maker_on_tp: bool = True


@dataclass
class AppConfig:
    """Master application configuration."""
    hyperliquid: HyperliquidConfig = field(default_factory=HyperliquidConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    signals: SignalConfig = field(default_factory=SignalConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    data_dir: str = "data"
    log_dir: str = "logs"
    sample_rate_hz: float = 10.0


# =============================================================================
# 2. CORE DATA STRUCTURES & PROTOCOLS
# =============================================================================

@dataclass
class L2Level:
    """Represents a single price level in the order book.
    
    Attributes:
        px: Price level in quote currency (USD).
        sz: Total resting volume in base currency (BTC).
        n: Total number of active orders at this price level (Hyperliquid specific).
    """
    px: float
    sz: float
    n: int

    @property
    def avg_order_size(self) -> float:
        return self.sz / max(self.n, 1)

    @property
    def notional(self) -> float:
        return self.px * self.sz


@dataclass
class BookSnapshot:
    """Immutable snapshot of the order book at a specific timestamp."""
    timestamp_ms: int
    bids: List[L2Level]
    asks: List[L2Level]


class OrderBook:
    """Maintains real-time 20-level L2 order book for Hyperliquid.
    
    Provides high-speed microstructure calculations including weighted mid-price,
    multi-tier depth imbalances, order concentration metrics, and historical deltas.
    """

    def __init__(self, coin: str = "BTC", max_history: int = 500):
        self.coin = coin
        self.max_history = max_history
        self.bids: List[L2Level] = []
        self.asks: List[L2Level] = []
        self.last_update_time_ms: int = 0
        self.history: List[BookSnapshot] = []
        self.update_count: int = 0

    def update_from_raw(self, raw_data: Dict[str, Any]) -> None:
        """Parses and updates the order book from Hyperliquid WS or REST payload."""
        levels = raw_data.get("levels", [[], []])
        if len(levels) < 2:
            return

        raw_bids, raw_asks = levels[0], levels[1]
        timestamp = raw_data.get("time", int(time.time() * 1000))

        parsed_bids = [
            L2Level(px=float(l["px"]), sz=float(l["sz"]), n=int(l.get("n", 1)))
            for l in raw_bids
        ]
        parsed_bids.sort(key=lambda x: x.px, reverse=True)

        parsed_asks = [
            L2Level(px=float(l["px"]), sz=float(l["sz"]), n=int(l.get("n", 1)))
            for l in raw_asks
        ]
        parsed_asks.sort(key=lambda x: x.px)

        self.bids = parsed_bids
        self.asks = parsed_asks
        self.last_update_time_ms = timestamp
        self.update_count += 1

        snapshot = BookSnapshot(timestamp_ms=timestamp, bids=parsed_bids, asks=parsed_asks)
        self.history.append(snapshot)
        if len(self.history) > self.max_history:
            self.history.pop(0)

    @property
    def is_valid(self) -> bool:
        return (
            len(self.bids) > 0
            and len(self.asks) > 0
            and self.bids[0].px < self.asks[0].px
        )

    @property
    def best_bid(self) -> float:
        return self.bids[0].px if self.bids else 0.0

    @property
    def best_bid_sz(self) -> float:
        return self.bids[0].sz if self.bids else 0.0

    @property
    def best_bid_n(self) -> int:
        return self.bids[0].n if self.bids else 0

    @property
    def best_ask(self) -> float:
        return self.asks[0].px if self.asks else 0.0

    @property
    def best_ask_sz(self) -> float:
        return self.asks[0].sz if self.asks else 0.0

    @property
    def best_ask_n(self) -> int:
        return self.asks[0].n if self.asks else 0

    @property
    def mid_price(self) -> float:
        if not self.is_valid:
            return 0.0
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> float:
        if not self.is_valid:
            return 0.0
        return self.best_ask - self.best_bid

    @property
    def spread_bps(self) -> float:
        mid = self.mid_price
        if mid <= 0:
            return 0.0
        return (self.spread / mid) * 10_000.0

    @property
    def weighted_mid_price(self) -> float:
        """Top-of-book volume weighted mid-price (P_imb)."""
        if not self.is_valid:
            return 0.0
        qb = self.best_bid_sz
        qa = self.best_ask_sz
        total = qb + qa
        if total <= 0:
            return self.mid_price
        return (self.best_bid * qa + self.best_ask * qb) / total

    def get_depth_volume(self, k_levels: int = 5) -> Tuple[float, float]:
        """Returns total volume on bid and ask sides for top k levels."""
        bid_vol = sum(level.sz for level in self.bids[:k_levels])
        ask_vol = sum(level.sz for level in self.asks[:k_levels])
        return bid_vol, ask_vol

    def get_depth_order_counts(self, k_levels: int = 5) -> Tuple[int, int]:
        """Returns total order count 'n' on bid and ask sides for top k levels."""
        bid_n = sum(level.n for level in self.bids[:k_levels])
        ask_n = sum(level.n for level in self.asks[:k_levels])
        return bid_n, ask_n

    def depth_imbalance(self, k_levels: int = 5) -> float:
        """Standard unweighted order book imbalance: (B - A) / (B + A). Range [-1, 1]."""
        b_vol, a_vol = self.get_depth_volume(k_levels)
        total = b_vol + a_vol
        if total <= 0:
            return 0.0
        return (b_vol - a_vol) / total

    def weighted_imbalance(self, k_levels: int = 10, decay_lambda: float = 0.35) -> float:
        """Exponentially decayed multi-level depth imbalance."""
        if not self.is_valid:
            return 0.0

        n_levels = min(k_levels, len(self.bids), len(self.asks))
        w_bids = 0.0
        w_asks = 0.0

        for i in range(n_levels):
            w = math.exp(-decay_lambda * i)
            w_bids += self.bids[i].sz * w
            w_asks += self.asks[i].sz * w

        denominator = w_bids + w_asks
        if denominator <= 0:
            return 0.0
        return (w_bids - w_asks) / denominator

    def distance_weighted_imbalance(self, k_levels: int = 20) -> float:
        """Distance-weighted depth imbalance: weights inversely proportional to distance from mid."""
        if not self.is_valid:
            return 0.0

        mid = self.mid_price
        n_levels = min(k_levels, len(self.bids), len(self.asks))
        w_bids = 0.0
        w_asks = 0.0

        for i in range(n_levels):
            bid_dist = max(mid - self.bids[i].px, 0.5)
            ask_dist = max(self.asks[i].px - mid, 0.5)
            w_bids += self.bids[i].sz * (1.0 / bid_dist)
            w_asks += self.asks[i].sz * (1.0 / ask_dist)

        denom = w_bids + w_asks
        if denom <= 0:
            return 0.0
        return (w_bids - w_asks) / denom

    def order_count_imbalance(self, k_levels: int = 5) -> float:
        """Order count imbalance: (N_bid - N_ask) / (N_bid + N_ask). Range [-1, 1]."""
        b_n, a_n = self.get_depth_order_counts(k_levels)
        total = b_n + a_n
        if total <= 0:
            return 0.0
        return (b_n - a_n) / total

    def find_whale_walls(
        self, min_sz_btc: float = 5.0, min_aos: float = 2.0
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Detects resting whale walls and distinguishes single-player vs distributed walls."""
        walls: Dict[str, List[Dict[str, Any]]] = {"bids": [], "asks": []}

        for i, level in enumerate(self.bids):
            if level.sz >= min_sz_btc:
                is_single_whale = level.avg_order_size >= min_aos
                walls["bids"].append({
                    "level_idx": i,
                    "px": level.px,
                    "sz": level.sz,
                    "n": level.n,
                    "aos": level.avg_order_size,
                    "is_whale": is_single_whale,
                    "dist_from_mid_bps": (self.mid_price - level.px) / max(self.mid_price, 1) * 10000,
                })

        for i, level in enumerate(self.asks):
            if level.sz >= min_sz_btc:
                is_single_whale = level.avg_order_size >= min_aos
                walls["asks"].append({
                    "level_idx": i,
                    "px": level.px,
                    "sz": level.sz,
                    "n": level.n,
                    "aos": level.avg_order_size,
                    "is_whale": is_single_whale,
                    "dist_from_mid_bps": (level.px - self.mid_price) / max(self.mid_price, 1) * 10000,
                })

        return walls

    def get_previous_snapshot(self, offset: int = 1) -> Optional[BookSnapshot]:
        """Retrieves a historical book snapshot relative to current time."""
        idx = len(self.history) - 1 - offset
        if 0 <= idx < len(self.history):
            return self.history[idx]
        return None


@dataclass
class Trade:
    """Individual executed trade tick on Hyperliquid."""
    timestamp_ms: int
    price: float
    size: float
    side: str  # 'B' for aggressive buy (hits ask), 'A' for aggressive sell (hits bid)
    tid: int = 0
    hash: str = ""

    @property
    def is_buy(self) -> bool:
        return self.side == "B"

    @property
    def signed_size(self) -> float:
        return self.size if self.is_buy else -self.size

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass
class VolumeBucket:
    """Discrete constant-volume bucket for VPIN calculation."""
    bucket_idx: int
    target_vol: float
    buy_vol: float = 0.0
    sell_vol: float = 0.0
    start_time_ms: int = 0
    end_time_ms: int = 0
    start_price: float = 0.0
    end_price: float = 0.0

    @property
    def total_vol(self) -> float:
        return self.buy_vol + self.sell_vol

    @property
    def abs_imbalance(self) -> float:
        return abs(self.buy_vol - self.sell_vol)

    @property
    def is_full(self) -> bool:
        return self.total_vol >= self.target_vol - 1e-7


class TradeManager:
    """Processes incoming trade ticks from Hyperliquid WS/REST."""

    def __init__(
        self,
        coin: str = "BTC",
        max_trades: int = 5000,
        vpin_bucket_size_btc: float = 5.0,
        max_vpin_buckets: int = 100,
    ):
        self.coin = coin
        self.max_trades = max_trades
        self.vpin_bucket_size = vpin_bucket_size_btc
        self.max_vpin_buckets = max_vpin_buckets

        self.trades: Deque[Trade] = deque(maxlen=max_trades)
        self.total_cvd: float = 0.0
        self.total_volume: float = 0.0
        self.last_trade_time_ms: int = 0
        self.last_price: float = 0.0

        self.completed_buckets: Deque[VolumeBucket] = deque(maxlen=max_vpin_buckets)
        self.current_bucket: VolumeBucket = VolumeBucket(
            bucket_idx=0,
            target_vol=self.vpin_bucket_size,
            start_time_ms=int(time.time() * 1000),
        )

    def process_raw_trades(self, raw_trades: List[Dict[str, Any]]) -> List[Trade]:
        """Parses and ingests a list of raw trade dicts from Hyperliquid."""
        new_trades: List[Trade] = []
        for r in raw_trades:
            try:
                t = Trade(
                    timestamp_ms=int(r.get("time", time.time() * 1000)),
                    price=float(r["px"]),
                    size=float(r["sz"]),
                    side=str(r["side"]).upper(),
                    tid=int(r.get("tid", 0)),
                    hash=str(r.get("hash", "")),
                )
                self._add_trade(t)
                new_trades.append(t)
            except (ValueError, KeyError):
                continue
        return new_trades

    def _add_trade(self, trade: Trade) -> None:
        self.trades.append(trade)
        self.last_trade_time_ms = trade.timestamp_ms
        self.last_price = trade.price
        self.total_cvd += trade.signed_size
        self.total_volume += trade.size
        self._ingest_vpin_volume(trade)

    def _ingest_vpin_volume(self, trade: Trade) -> None:
        """Splits incoming trade volume into constant-volume buckets for VPIN."""
        remaining_vol = trade.size
        is_buy = trade.is_buy
        t_ms = trade.timestamp_ms
        px = trade.price

        while remaining_vol > 1e-8:
            if self.current_bucket.start_price == 0.0:
                self.current_bucket.start_price = px
                self.current_bucket.start_time_ms = t_ms

            needed = self.current_bucket.target_vol - self.current_bucket.total_vol

            if remaining_vol <= needed + 1e-8:
                if is_buy:
                    self.current_bucket.buy_vol += remaining_vol
                else:
                    self.current_bucket.sell_vol += remaining_vol

                self.current_bucket.end_price = px
                self.current_bucket.end_time_ms = t_ms
                remaining_vol = 0.0

                if self.current_bucket.is_full:
                    self.completed_buckets.append(self.current_bucket)
                    new_idx = self.current_bucket.bucket_idx + 1
                    self.current_bucket = VolumeBucket(
                        bucket_idx=new_idx,
                        target_vol=self.vpin_bucket_size,
                    )
            else:
                if is_buy:
                    self.current_bucket.buy_vol += needed
                else:
                    self.current_bucket.sell_vol += needed

                self.current_bucket.end_price = px
                self.current_bucket.end_time_ms = t_ms
                remaining_vol -= needed

                self.completed_buckets.append(self.current_bucket)
                new_idx = self.current_bucket.bucket_idx + 1
                self.current_bucket = VolumeBucket(
                    bucket_idx=new_idx,
                    target_vol=self.vpin_bucket_size,
                    start_time_ms=t_ms,
                    start_price=px,
                )

    def get_cvd_in_window(self, window_secs: float) -> Tuple[float, float, float]:
        """Calculates (CVD, BuyVol, SellVol) over the last N seconds."""
        now_ms = self.last_trade_time_ms or int(time.time() * 1000)
        cutoff_ms = now_ms - int(window_secs * 1000)

        cvd = 0.0
        buy_vol = 0.0
        sell_vol = 0.0

        for t in reversed(self.trades):
            if t.timestamp_ms < cutoff_ms:
                break
            if t.is_buy:
                buy_vol += t.size
                cvd += t.size
            else:
                sell_vol += t.size
                cvd -= t.size

        return cvd, buy_vol, sell_vol

    def get_recent_large_trades(
        self, min_sz_btc: float = 1.0, lookback_secs: float = 10.0
    ) -> List[Trade]:
        """Finds recent aggressive orders exceeding size threshold."""
        now_ms = self.last_trade_time_ms or int(time.time() * 1000)
        cutoff_ms = now_ms - int(lookback_secs * 1000)

        large = []
        for t in reversed(self.trades):
            if t.timestamp_ms < cutoff_ms:
                break
            if t.size >= min_sz_btc:
                large.append(t)
        return large

    def calculate_vpin(self, n_buckets: int = 30) -> Optional[float]:
        """Calculates Volume-Synchronized Probability of Toxicity."""
        if len(self.completed_buckets) < n_buckets:
            return None

        recent = list(self.completed_buckets)[-n_buckets:]
        total_imbalance = sum(b.abs_imbalance for b in recent)
        total_volume = sum(b.total_vol for b in recent)

        if total_volume <= 0:
            return 0.0

        return total_imbalance / total_volume


# =============================================================================
# 3. BASE SIGNAL PROTOCOL & CONCRETE ALPHA SIGNALS
# =============================================================================

@dataclass
class SignalResult:
    """Standardized output container returned by every alpha signal."""
    name: str
    score: float       # Normalized direction & conviction: [-1.0, 1.0]. +1.0 = Bullish, -1.0 = Bearish
    raw_value: float   # Unbounded or underlying natural metric
    confidence: float  # Confidence level [0.0, 1.0]
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_bullish(self) -> bool:
        return self.score > 0.0

    @property
    def is_bearish(self) -> bool:
        return self.score < 0.0


class BaseSignal(ABC):
    """Abstract base class for all market microstructure alpha signals."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        """Computes the signal given the current L2 book and trade state."""
        pass


class WOBISignal(BaseSignal):
    """Multi-Tier Weighted Order Book Imbalance with Anti-Spoofing Order Count Filtering."""

    def __init__(
        self,
        name: str = "WOBI",
        decay_lambda: float = 0.35,
        max_levels: int = 10,
        whale_min_sz: float = 5.0,
    ):
        super().__init__(name)
        self.decay_lambda = decay_lambda
        self.max_levels = max_levels
        self.whale_min_sz = whale_min_sz

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        n_levels = min(self.max_levels, len(book.bids), len(book.asks))
        w_bids = 0.0
        w_asks = 0.0
        bids_spoof_penalty = 0.0
        asks_spoof_penalty = 0.0

        for i in range(n_levels):
            w = math.exp(-self.decay_lambda * i)
            b_lvl = book.bids[i]
            a_lvl = book.asks[i]

            b_density_factor = 1.0
            if b_lvl.sz >= self.whale_min_sz and b_lvl.n <= 2:
                b_density_factor = 0.6
                bids_spoof_penalty += 0.2

            a_density_factor = 1.0
            if a_lvl.sz >= self.whale_min_sz and a_lvl.n <= 2:
                a_density_factor = 0.6
                asks_spoof_penalty += 0.2

            w_bids += b_lvl.sz * w * b_density_factor
            w_asks += a_lvl.sz * w * a_density_factor

        denom = w_bids + w_asks
        if denom <= 0:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        raw_imbalance = (w_bids - w_asks) / denom
        tob_b = book.best_bid_sz
        tob_a = book.best_ask_sz
        tob_imbalance = (tob_b - tob_a) / max(tob_b + tob_a, 1e-8)

        spread_factor = max(0.2, 1.0 - (book.spread_bps / 5.0))
        depth_factor = min(1.0, denom / 2.0)
        confidence = min(1.0, spread_factor * depth_factor)
        score = max(-1.0, min(1.0, raw_imbalance))

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=raw_imbalance,
            confidence=confidence,
            timestamp_ms=timestamp_ms or book.last_update_time_ms,
            metadata={
                "wobi_5": book.depth_imbalance(5),
                "wobi_20": book.depth_imbalance(20),
                "tob_imbalance": tob_imbalance,
                "bids_spoof_penalty": bids_spoof_penalty,
                "asks_spoof_penalty": asks_spoof_penalty,
                "bid_order_count_5": sum(l.n for l in book.bids[:5]),
                "ask_order_count_5": sum(l.n for l in book.asks[:5]),
            },
        )


class VOISignal(BaseSignal):
    """Volume Order Imbalance (Cont, Kukanov, Stoikov, 2014)."""

    def __init__(
        self,
        name: str = "VOI",
        history_window: int = 100,
        z_score_clip: float = 3.0,
    ):
        super().__init__(name)
        self.history_window = history_window
        self.z_score_clip = z_score_clip
        self.prev_bid_px: float = 0.0
        self.prev_bid_sz: float = 0.0
        self.prev_ask_px: float = 0.0
        self.prev_ask_sz: float = 0.0
        self.voi_history: Deque[Tuple[int, float]] = deque(maxlen=history_window)

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        curr_bid_px = book.best_bid
        curr_bid_sz = book.best_bid_sz
        curr_ask_px = book.best_ask
        curr_ask_sz = book.best_ask_sz
        now_ms = timestamp_ms or book.last_update_time_ms

        if self.prev_bid_px == 0.0 or self.prev_ask_px == 0.0:
            self.prev_bid_px = curr_bid_px
            self.prev_bid_sz = curr_bid_sz
            self.prev_ask_px = curr_ask_px
            self.prev_ask_sz = curr_ask_sz
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        if curr_bid_px > self.prev_bid_px:
            delta_vb = curr_bid_sz
        elif curr_bid_px == self.prev_bid_px:
            delta_vb = curr_bid_sz - self.prev_bid_sz
        else:
            delta_vb = 0.0

        if curr_ask_px < self.prev_ask_px:
            delta_va = curr_ask_sz
        elif curr_ask_px == self.prev_ask_px:
            delta_va = curr_ask_sz - self.prev_ask_sz
        else:
            delta_va = 0.0

        instant_voi = delta_vb - delta_va

        self.prev_bid_px = curr_bid_px
        self.prev_bid_sz = curr_bid_sz
        self.prev_ask_px = curr_ask_px
        self.prev_ask_sz = curr_ask_sz

        self.voi_history.append((now_ms, instant_voi))

        recent_values = [v for _, v in list(self.voi_history)[-30:]]
        cum_voi = sum(recent_values)
        k_samples = len(recent_values)

        if len(self.voi_history) >= 15:
            all_values = [v for _, v in self.voi_history]
            mean_v = sum(all_values) / len(all_values)
            variance = sum((x - mean_v) ** 2 for x in all_values) / len(all_values)
            std_v = math.sqrt(variance) if variance > 1e-6 else 1.0

            expected_sum = mean_v * k_samples
            z_score = (cum_voi - expected_sum) / (std_v * math.sqrt(k_samples))
            z_score = max(-self.z_score_clip, min(self.z_score_clip, z_score))
            score = math.tanh(z_score / 1.5)
            confidence = min(1.0, len(self.voi_history) / self.history_window)
        else:
            score = math.tanh(cum_voi / 2.0)
            confidence = len(self.voi_history) / 30.0

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=cum_voi,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "instant_voi": instant_voi,
                "delta_vb": delta_vb,
                "delta_va": delta_va,
                "cum_voi_30": cum_voi,
            },
        )


class MicroPriceSignal(BaseSignal):
    """Stoikov (2018) Micro-Price Fair Value Estimator."""

    def __init__(
        self,
        name: str = "MicroPrice",
        gamma_nonlinearity: float = 0.85,
        spread_scale_bps: float = 1.0,
    ):
        super().__init__(name)
        self.gamma = gamma_nonlinearity
        self.spread_scale_bps = spread_scale_bps

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

        imbalance = (qb - qa) / total_q
        sign = 1.0 if imbalance >= 0 else -1.0
        g_imb = sign * (abs(imbalance) ** self.gamma)

        half_spread = spread / 2.0
        p_micro = mid + (half_spread * g_imb)
        micro_drift = p_micro - mid

        score = max(-1.0, min(1.0, g_imb))
        confidence = min(1.0, (total_q / 2.0) * (1.0 / max(spread, 1.0)))

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=micro_drift,
            confidence=confidence,
            timestamp_ms=timestamp_ms or book.last_update_time_ms,
            metadata={
                "mid_price": mid,
                "micro_price": p_micro,
                "spread": spread,
                "spread_bps": book.spread_bps,
                "imbalance": imbalance,
                "micro_drift_usd": micro_drift,
            },
        )


class VPINSignal(BaseSignal):
    """Volume-Synchronized Probability of Toxicity (VPIN)."""

    def __init__(
        self,
        name: str = "VPIN",
        n_buckets: int = 20,
        toxic_threshold: float = 0.65,
    ):
        super().__init__(name)
        self.n_buckets = n_buckets
        self.toxic_threshold = toxic_threshold

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        now_ms = timestamp_ms or book.last_update_time_ms

        if len(trades.completed_buckets) < 3:
            return SignalResult(
                name=self.name,
                score=0.0,
                raw_value=0.0,
                confidence=0.1,
                timestamp_ms=now_ms,
                metadata={"buckets_ready": len(trades.completed_buckets)},
            )

        n = min(self.n_buckets, len(trades.completed_buckets))
        recent_buckets = list(trades.completed_buckets)[-n:]

        total_abs_imbalance = sum(b.abs_imbalance for b in recent_buckets)
        total_signed_imbalance = sum(b.buy_vol - b.sell_vol for b in recent_buckets)
        total_vol = sum(b.total_vol for b in recent_buckets)

        if total_vol <= 0:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        vpin_toxicity = total_abs_imbalance / total_vol
        signed_ratio = total_signed_imbalance / total_vol

        score = signed_ratio * min(1.0, (vpin_toxicity / self.toxic_threshold))
        confidence = min(1.0, len(trades.completed_buckets) / float(self.n_buckets))
        is_toxic = vpin_toxicity >= self.toxic_threshold

        return SignalResult(
            name=self.name,
            score=max(-1.0, min(1.0, score)),
            raw_value=vpin_toxicity,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "vpin_toxicity": vpin_toxicity,
                "signed_ratio": signed_ratio,
                "is_toxic": is_toxic,
                "completed_buckets": len(trades.completed_buckets),
                "total_volume_btc": total_vol,
            },
        )


class AbsorptionSignal(BaseSignal):
    """Detects Limit Order Absorption and CVD-Price Divergences."""

    def __init__(
        self,
        name: str = "Absorption",
        window_secs: float = 20.0,
        divergence_ratio_thresh: float = 2.0,
    ):
        super().__init__(name)
        self.window_secs = window_secs
        self.divergence_ratio_thresh = divergence_ratio_thresh
        self.price_history: Deque[Tuple[int, float]] = deque(maxlen=200)

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        now_ms = timestamp_ms or book.last_update_time_ms
        mid = book.mid_price
        self.price_history.append((now_ms, mid))

        cvd, buy_vol, sell_vol = trades.get_cvd_in_window(self.window_secs)
        total_vol = buy_vol + sell_vol
        if total_vol < 0.5:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.1)

        cutoff_ms = now_ms - int(self.window_secs * 1000)
        old_prices = [p for t, p in self.price_history if t <= cutoff_ms]
        old_price = old_prices[-1] if old_prices else self.price_history[0][1]
        price_delta_bps = ((mid - old_price) / max(old_price, 1.0)) * 10000.0

        cvd_ratio = cvd / total_vol
        score = 0.0
        pattern = "NEUTRAL"

        if cvd_ratio < -0.4 and price_delta_bps >= -0.5:
            absorption_intensity = abs(cvd_ratio) * (1.0 + max(0.0, price_delta_bps))
            score = min(1.0, absorption_intensity)
            pattern = "BULLISH_ABSORPTION"
        elif cvd_ratio > 0.4 and price_delta_bps <= 0.5:
            absorption_intensity = cvd_ratio * (1.0 + max(0.0, -price_delta_bps))
            score = -min(1.0, absorption_intensity)
            pattern = "BEARISH_ABSORPTION"
        elif abs(cvd_ratio) > 0.5 and abs(price_delta_bps) > 1.5:
            if cvd_ratio > 0 and price_delta_bps > 0:
                score = min(0.8, cvd_ratio)
                pattern = "BULLISH_MOMENTUM"
            elif cvd_ratio < 0 and price_delta_bps < 0:
                score = max(-0.8, cvd_ratio)
                pattern = "BEARISH_MOMENTUM"

        confidence = min(1.0, total_vol / 5.0)

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=cvd_ratio,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={
                "pattern": pattern,
                "cvd_btc": cvd,
                "total_vol_btc": total_vol,
                "cvd_ratio": cvd_ratio,
                "price_delta_bps": price_delta_bps,
            },
        )


class SweepSignal(BaseSignal):
    """Detects multi-level order book sweeps and replenishment elasticity."""

    def __init__(
        self,
        name: str = "SweepElasticity",
        min_sweep_btc: float = 1.5,
        sweep_window_ms: int = 500,
    ):
        super().__init__(name)
        self.min_sweep_btc = min_sweep_btc
        self.sweep_window_ms = sweep_window_ms
        self.last_bid_top: float = 0.0
        self.last_ask_top: float = 0.0

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        if not book.is_valid:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        now_ms = timestamp_ms or book.last_update_time_ms
        best_b = book.best_bid
        best_a = book.best_ask

        recent_large = trades.get_recent_large_trades(min_sz_btc=self.min_sweep_btc, lookback_secs=0.5)
        score = 0.0
        pattern = "STABLE"

        if recent_large:
            last_t = recent_large[0]
            if last_t.is_buy and self.last_ask_top > 0 and best_a > self.last_ask_top + 1.0:
                ask_top_sz = book.best_ask_sz
                if ask_top_sz >= 1.0:
                    score = -0.5
                    pattern = "SWEEP_BUY_REPLENISHED_FADE"
                else:
                    score = 0.6
                    pattern = "SWEEP_BUY_VOID_MOMENTUM"
            elif (not last_t.is_buy) and self.last_bid_top > 0 and best_b < self.last_bid_top - 1.0:
                bid_top_sz = book.best_bid_sz
                if bid_top_sz >= 1.0:
                    score = 0.5
                    pattern = "SWEEP_SELL_REPLENISHED_FADE"
                else:
                    score = -0.6
                    pattern = "SWEEP_SELL_VOID_MOMENTUM"

        self.last_bid_top = best_b
        self.last_ask_top = best_a
        confidence = 0.7 if pattern != "STABLE" else 0.1

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=score,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={"pattern": pattern},
        )


# =============================================================================
# 4. ML FEATURE EXTRACTION & ONLINE ADAPTIVE LEARNER
# =============================================================================

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
    """Extracts a comprehensive vector of stationary, standardized microstructure features."""

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

        tob_b, tob_a = book.best_bid_sz, book.best_ask_sz
        wobi_1 = (tob_b - tob_a) / max(tob_b + tob_a, 1e-8)
        wobi_5 = book.weighted_imbalance(k_levels=5, decay_lambda=0.35)
        wobi_20 = book.distance_weighted_imbalance(k_levels=20)
        order_count_imb_5 = book.order_count_imbalance(k_levels=5)

        wobi_res = self.wobi_sig.compute(book, trades, now_ms)
        whale_wall_skew = wobi_res.score

        voi_res = self.voi_sig.compute(book, trades, now_ms)
        voi_zscore = voi_res.score

        mp_res = self.micro_sig.compute(book, trades, now_ms)
        microprice_drift = mp_res.score

        spread_bps = max(0.0, book.spread - 1.0)
        tot_b_20, tot_a_20 = book.get_depth_volume(20)
        depth_log_ratio = math.log(max(tot_b_20, 0.01) / max(tot_a_20, 0.01))
        depth_log_ratio = max(-2.5, min(2.5, depth_log_ratio))

        abs_res = self.abs_sig.compute(book, trades, now_ms)
        cvd_30s_ratio = abs_res.raw_value

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


@dataclass
class PendingSample:
    sample_id: int
    timestamp_ms: int
    price: float
    features: np.ndarray
    predicted_return_bps: float


class OnlineAdaptiveLearner:
    """Online streaming learner for L2 microstructure updating feature weights in real time (NLMS)."""

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

        self.weights = np.zeros(self.n_features, dtype=np.float64)
        if initial_weights:
            for i, name in enumerate(FEATURE_NAMES):
                if name in initial_weights:
                    self.weights[i] = initial_weights[name]
        else:
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
        self.pending_samples: Deque[PendingSample] = deque(maxlen=2000)
        self.sample_counter: int = 0
        self.total_updates: int = 0
        self.recent_errors: Deque[float] = deque(maxlen=200)
        self.recent_hits: Deque[int] = deque(maxlen=200)

    def predict(self, features: np.ndarray) -> float:
        """Predicts forward return in basis points: y_hat = w . x + b."""
        return float(np.dot(self.weights, features) + self.bias)

    def predict_score(self, features: np.ndarray) -> float:
        """Normalized directional score in [-1.0, 1.0] using hyperbolic tangent."""
        pred_bps = self.predict(features)
        return float(math.tanh(pred_bps / 0.75))

    def ingest_observation(
        self,
        timestamp_ms: int,
        current_price: float,
        features: np.ndarray,
    ) -> float:
        """Ingests new feature vector, generates prediction, and updates on mature samples."""
        self._update_mature_samples(timestamp_ms, current_price)
        pred_bps = self.predict(features)
        pred_score = float(math.tanh(pred_bps / 0.75))

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
        horizon_ms = int(self.horizon_secs * 1000)

        while self.pending_samples:
            oldest = self.pending_samples[0]
            elapsed_ms = current_time_ms - oldest.timestamp_ms
            if elapsed_ms < horizon_ms:
                break

            sample = self.pending_samples.popleft()
            true_return_bps = ((current_price - sample.price) / sample.price) * 10_000.0
            error = true_return_bps - sample.predicted_return_bps

            is_hit = 1 if (np.sign(sample.predicted_return_bps) == np.sign(true_return_bps)) else 0
            self.recent_hits.append(is_hit)
            self.recent_errors.append(abs(error))

            x = sample.features
            norm_sq = float(np.dot(x, x)) + 1e-4
            step = (self.learning_rate * error) / norm_sq

            self.weights = (1.0 - self.l2_reg * self.learning_rate) * self.weights + (step * x)
            np.clip(self.weights, -2.5, 2.5, out=self.weights)

            self.bias += self.learning_rate * error * 0.1
            self.bias = max(-2.0, min(2.0, self.bias))
            self.total_updates += 1

    def get_feature_weights(self) -> Dict[str, float]:
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


class AdaptiveAlphaSignal(BaseSignal):
    """Machine Learning Alpha Signal combining online adaptive learning and trained models.
    
    Modes:
    - 'ONLINE': Continuously updates weights tick-by-tick as forward returns mature (NLMS).
    - 'TRAINED': Uses offline pre-trained Ridge weights from JSON.
    - 'HYBRID': Blends offline LightGBM tree predictions (60%) with adaptive online learner (40%).
    - 'LGBM': Pure LightGBM boosted tree inference.
    """

    def __init__(
        self,
        name: str = "AdaptiveMLAlpha",
        mode: str = "HYBRID",
        horizon_secs: float = 5.0,
        trained_weights_path: str = "transfer/l2_trained_weights.json",
        initial_weights: Optional[Dict[str, float]] = None,
    ):
        super().__init__(name)
        self.mode = mode.upper()
        self.horizon_secs = horizon_secs
        self.extractor = L2FeatureExtractor()
        self.trained_weights_path = trained_weights_path

        self.online_learner = OnlineAdaptiveLearner(
            horizon_secs=horizon_secs,
            initial_weights=initial_weights,
        )

        # Attempt loading trained weights
        if trained_weights_path and os.path.exists(trained_weights_path):
            self.online_learner.load_weights(trained_weights_path)

        # Attempt loading LightGBM booster if available
        self.lgb_booster = None
        if trained_weights_path:
            lgb_path = os.path.splitext(trained_weights_path)[0] + "_lgb.txt"
            if os.path.exists(lgb_path) and _HAS_LIGHTGBM and lgb is not None:
                try:
                    self.lgb_booster = lgb.Booster(model_file=lgb_path)
                except Exception:
                    self.lgb_booster = None

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

        feats = self.extractor.extract_features(book, trades, now_ms)
        if feats is None:
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        lgb_bps = 0.0
        if self.lgb_booster is not None:
            try:
                lgb_bps = float(self.lgb_booster.predict(feats.reshape(1, -1))[0])
            except Exception:
                lgb_bps = 0.0

        if self.mode in ("ONLINE", "HYBRID"):
            pred_score = self.online_learner.ingest_observation(now_ms, current_price, feats)
            pred_bps = self.online_learner.predict(feats)
            if self.mode == "HYBRID" and self.lgb_booster is not None:
                lgb_score = float(np.tanh(lgb_bps / 0.75))
                pred_score = 0.60 * lgb_score + 0.40 * pred_score
                pred_bps = 0.60 * lgb_bps + 0.40 * pred_bps
        elif self.mode == "LGBM" and self.lgb_booster is not None:
            pred_bps = lgb_bps
            pred_score = float(np.tanh(lgb_bps / 0.75))
        else:
            pred_score = self.online_learner.predict_score(feats)
            pred_bps = self.online_learner.predict(feats)

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


class CompositeAlphaSignal(BaseSignal):
    """Ensemble Composite Alpha Signal combining all multi-factor L2 microstructure predictors."""

    def __init__(
        self,
        name: str = "CompositeAlpha",
        w_wobi: float = 0.25,
        w_voi: float = 0.25,
        w_microprice: float = 0.20,
        w_absorption: float = 0.15,
        w_vpin: float = 0.15,
        trained_weights_path: str = "transfer/l2_trained_weights.json",
    ):
        super().__init__(name)
        self.w_wobi = w_wobi
        self.w_voi = w_voi
        self.w_microprice = w_microprice
        self.w_absorption = w_absorption
        self.w_vpin = w_vpin

        self.signal_wobi = WOBISignal()
        self.signal_voi = VOISignal()
        self.signal_microprice = MicroPriceSignal()
        self.signal_vpin = VPINSignal()
        self.signal_absorption = AbsorptionSignal()
        self.signal_sweep = SweepSignal()
        self.signal_adaptive = AdaptiveAlphaSignal(trained_weights_path=trained_weights_path)

    def compute(
        self,
        book: OrderBook,
        trades: TradeManager,
        timestamp_ms: Optional[int] = None,
    ) -> SignalResult:
        now_ms = timestamp_ms or book.last_update_time_ms

        res_wobi = self.signal_wobi.compute(book, trades, now_ms)
        res_voi = self.signal_voi.compute(book, trades, now_ms)
        res_mp = self.signal_microprice.compute(book, trades, now_ms)
        res_vpin = self.signal_vpin.compute(book, trades, now_ms)
        res_abs = self.signal_absorption.compute(book, trades, now_ms)
        res_sweep = self.signal_sweep.compute(book, trades, now_ms)
        res_adaptive = self.signal_adaptive.compute(book, trades, now_ms)

        is_toxic = res_vpin.metadata.get("is_toxic", False)
        regime = "NORMAL"

        if is_toxic:
            regime = "TOXIC_EXPANSION"
            adj_wobi = 0.10
            adj_voi = 0.35
            adj_mp = 0.10
            adj_abs = 0.25
            adj_vpin = 0.20
        else:
            adj_wobi = self.w_wobi
            adj_voi = self.w_voi
            adj_mp = self.w_microprice
            adj_abs = self.w_absorption
            adj_vpin = self.w_vpin

        total_weight = adj_wobi + adj_voi + adj_mp + adj_abs + adj_vpin

        composite_score = (
            adj_wobi * res_wobi.score
            + adj_voi * res_voi.score
            + adj_mp * res_mp.score
            + adj_abs * res_abs.score
            + adj_vpin * res_vpin.score
        ) / total_weight

        if abs(res_sweep.score) > 0.3:
            composite_score = 0.7 * composite_score + 0.3 * res_sweep.score

        composite_score = max(-1.0, min(1.0, composite_score))
        avg_confidence = (
            res_wobi.confidence + res_voi.confidence + res_mp.confidence + res_abs.confidence
        ) / 4.0

        return SignalResult(
            name=self.name,
            score=composite_score,
            raw_value=composite_score,
            confidence=avg_confidence,
            timestamp_ms=now_ms,
            metadata={
                "regime": regime,
                "sub_signals": {
                    "WOBI": res_wobi,
                    "VOI": res_voi,
                    "MicroPrice": res_mp,
                    "VPIN": res_vpin,
                    "Absorption": res_abs,
                    "Sweep": res_sweep,
                    "AdaptiveML": res_adaptive,
                },
            },
        )


# =============================================================================
# 5. DUAL EXECUTION ENGINE & PAPER TRADING EVALUATOR
# =============================================================================

@dataclass
class TradeRecord:
    strategy_name: str
    entry_time_ms: int
    exit_time_ms: int
    side: str  # 'LONG' or 'SHORT'
    entry_price: float
    exit_price: float
    size_btc: float
    gross_pnl_usd: float
    fees_usd: float
    net_pnl_usd: float
    return_bps: float
    exit_reason: str
    execution_type: str = "TAKER"


@dataclass
class StrategyState:
    name: str
    execution_type: str = "MAKER"  # 'MAKER' or 'SMART_TAKER'
    signal_key: str = "CompositeAlpha"
    position_btc: float = 0.0
    entry_price: float = 0.0
    entry_time_ms: int = 0
    cash_usd: float = 10_000.0
    trades: List[TradeRecord] = field(default_factory=list)
    peak_equity: float = 10_000.0
    max_drawdown_usd: float = 0.0

    entry_fee_usd: float = 0.0
    peak_price: float = 0.0
    trough_price: float = 1e9
    trailing_stop_active: bool = False
    stop_price: float = 0.0
    take_profit_price: float = 0.0

    @property
    def is_in_position(self) -> bool:
        return abs(self.position_btc) > 1e-6

    def current_equity(self, current_price: float) -> float:
        unrealized = self.position_btc * (current_price - self.entry_price)
        return self.cash_usd + unrealized


@dataclass
class SignalObservation:
    timestamp_ms: int
    price: float
    signals: Dict[str, float]
    evaluated_horizons: Set[int] = field(default_factory=set)


class EdgeEvaluator:
    """Rigorous market microstructure alpha evaluator and advanced execution simulator.
    
    1. Multi-Horizon Predictive Edge:
       - Evaluates Information Coefficient (IC), Rank IC, t-statistic, and directional accuracy
         across [1s, 3s, 5s, 10s, 30s, 60s].
         
    2. Dual Execution Simulation:
       - Maker Strategies: Post passive limit quotes at best bid/ask, earning spread and maker rebates.
       - Smart Taker Strategies: Enter with market orders on high conviction dislocations with
         dynamic trailing stops and fee-hurdle ratchets.
    """

    def __init__(
        self,
        market_cfg: Optional[MarketConfig] = None,
        bt_cfg: Optional[BacktestConfig] = None,
    ):
        self.market_cfg = market_cfg or MarketConfig()
        self.bt_cfg = bt_cfg or BacktestConfig()

        self.strategy_defs = {
            "AdaptiveML_Maker": ("AdaptiveML", "MAKER"),
            "Composite_Maker": ("CompositeAlpha", "MAKER"),
            "WOBI_Maker": ("WOBI", "MAKER"),
            "MicroPrice_Maker": ("MicroPrice", "MAKER"),
            "AdaptiveML_Taker": ("AdaptiveML", "SMART_TAKER"),
            "Composite_Taker": ("CompositeAlpha", "SMART_TAKER"),
            "Absorption_Fade": ("Absorption", "MAKER"),
        }
        self.strategy_names = list(self.strategy_defs.keys())

        self.strategies: Dict[str, StrategyState] = {
            s: StrategyState(
                name=s,
                execution_type=self.strategy_defs[s][1],
                signal_key=self.strategy_defs[s][0],
                cash_usd=self.bt_cfg.initial_cash_usd,
            )
            for s in self.strategy_names
        }

        self.observations: Deque[SignalObservation] = deque(maxlen=2000)
        unique_signals = set(sig_k for sig_k, _ in self.strategy_defs.values())
        unique_signals.update(["WOBI", "VOI", "MicroPrice", "VPIN", "Absorption", "Sweep", "CompositeAlpha", "AdaptiveML"])

        self.eval_data: Dict[str, Dict[int, List[Tuple[float, float]]]] = {
            s: {h: [] for h in self.bt_cfg.horizons_seconds}
            for s in unique_signals
        }
        self.position_events: Deque[Dict[str, Any]] = deque(maxlen=200)

    def record_step(
        self,
        timestamp_ms: int,
        mid_price: float,
        best_bid: float,
        best_ask: float,
        signals: Dict[str, float],
    ) -> None:
        """Called on every sample step (5-10 Hz). Updates forward returns and paper trading."""
        if mid_price <= 0:
            return

        obs = SignalObservation(
            timestamp_ms=timestamp_ms,
            price=mid_price,
            signals=signals.copy(),
        )
        self.observations.append(obs)
        self._update_forward_returns(timestamp_ms, mid_price)
        self._update_paper_trading(timestamp_ms, mid_price, best_bid, best_ask, signals)

    def step(
        self,
        timestamp_ms: int,
        mid_price: float,
        best_bid: float,
        best_ask: float,
        signals: Dict[str, float],
    ) -> None:
        """Alias for record_step for compatibility with execution simulation calls."""
        self.record_step(timestamp_ms, mid_price, best_bid, best_ask, signals)

    def _update_forward_returns(self, current_time_ms: int, current_price: float) -> None:
        for obs in self.observations:
            elapsed_secs = (current_time_ms - obs.timestamp_ms) / 1000.0
            for h in self.bt_cfg.horizons_seconds:
                if elapsed_secs >= h and h not in obs.evaluated_horizons:
                    obs.evaluated_horizons.add(h)
                    fwd_return = (current_price - obs.price) / obs.price
                    for s_name, s_val in obs.signals.items():
                        if s_name in self.eval_data and h in self.eval_data[s_name]:
                            data_list = self.eval_data[s_name][h]
                            if len(data_list) < 2000:
                                data_list.append((s_val, fwd_return))

    def _update_paper_trading(
        self,
        timestamp_ms: int,
        mid_price: float,
        best_bid: float,
        best_ask: float,
        signals: Dict[str, float],
    ) -> None:
        taker_fee_pct = self.market_cfg.taker_fee_bps / 10_000.0
        maker_rebate_pct = abs(self.market_cfg.maker_rebate_bps) / 10_000.0
        slippage_pct = self.bt_cfg.slippage_bps / 10_000.0
        spread_bps = ((best_ask - best_bid) / mid_price) * 10_000.0 if mid_price > 0 else 1.0

        for s_name in self.strategy_names:
            state = self.strategies[s_name]
            sig_k = state.signal_key
            score = signals.get(sig_k, 0.0)
            is_maker = (state.execution_type == "MAKER")

            if is_maker:
                entry_thresh = self.bt_cfg.entry_threshold
                tp_bps = self.bt_cfg.take_profit_bps
                sl_bps = self.bt_cfg.stop_loss_bps
                trail_act_bps = self.bt_cfg.trailing_stop_activation_bps
                trail_dist_bps = self.bt_cfg.trailing_stop_distance_bps
                reversal_thresh = self.bt_cfg.exit_reversal_threshold
                max_hold_secs = self.bt_cfg.max_holding_time_secs
            else:
                entry_thresh = self.bt_cfg.entry_threshold_taker
                tp_bps = self.bt_cfg.take_profit_bps_taker
                sl_bps = self.bt_cfg.stop_loss_bps_taker
                trail_act_bps = self.bt_cfg.trailing_stop_activation_bps_taker
                trail_dist_bps = self.bt_cfg.trailing_stop_distance_bps_taker
                reversal_thresh = self.bt_cfg.exit_reversal_threshold_taker
                max_hold_secs = self.bt_cfg.max_holding_time_secs_taker

            eq = state.current_equity(mid_price)
            if eq > state.peak_equity:
                state.peak_equity = eq
            dd = state.peak_equity - eq
            if dd > state.max_drawdown_usd:
                state.max_drawdown_usd = dd

            # Position Management & Exits
            if state.is_in_position:
                is_long = state.position_btc > 0
                holding_time_secs = (timestamp_ms - state.entry_time_ms) / 1000.0

                if is_long:
                    state.peak_price = max(state.peak_price, mid_price)
                    gain_bps = ((mid_price - state.entry_price) / state.entry_price) * 10_000.0

                    if gain_bps >= trail_act_bps:
                        state.trailing_stop_active = True
                        trailing_floor = state.peak_price * (1.0 - (trail_dist_bps / 10_000.0))
                        if not is_maker:
                            fee_pct = taker_fee_pct + (maker_rebate_pct if self.bt_cfg.taker_exit_as_maker_on_tp else taker_fee_pct)
                            fee_floor = state.entry_price * (1.0 + fee_pct)
                            if state.peak_price > fee_floor:
                                trailing_floor = max(trailing_floor, fee_floor)
                        safe_stop = min(mid_price * 0.9999, trailing_floor)
                        state.stop_price = max(state.stop_price, safe_stop)

                    exit_reason = None
                    if gain_bps >= tp_bps:
                        exit_reason = "TAKE_PROFIT"
                    elif mid_price <= state.stop_price:
                        exit_reason = "TRAILING_STOP" if state.trailing_stop_active else "STOP_LOSS"
                    elif score <= -reversal_thresh:
                        exit_reason = "SIGNAL_REVERSAL"
                    elif holding_time_secs >= max_hold_secs:
                        exit_reason = "TIME_LIMIT"

                    if exit_reason:
                        if is_maker and exit_reason != "STOP_LOSS":
                            exit_price = best_ask
                            fee = -abs(exit_price * state.position_btc * maker_rebate_pct)
                            exec_label = "MAKER"
                        elif not is_maker and exit_reason != "STOP_LOSS" and self.bt_cfg.taker_exit_as_maker_on_tp:
                            exit_price = best_ask
                            fee = -abs(exit_price * state.position_btc * maker_rebate_pct)
                            exec_label = f"MAKER ({exit_reason[:4]})"
                        else:
                            exit_price = best_bid * (1.0 - slippage_pct)
                            fee = exit_price * state.position_btc * taker_fee_pct
                            exec_label = "TAKER"

                        sz = state.position_btc
                        total_fees = state.entry_fee_usd + fee
                        gross_pnl = (exit_price - state.entry_price) * sz
                        net_pnl = gross_pnl - total_fees
                        state.cash_usd += (gross_pnl - fee)

                        record = TradeRecord(
                            strategy_name=s_name,
                            entry_time_ms=state.entry_time_ms,
                            exit_time_ms=timestamp_ms,
                            side="LONG",
                            entry_price=state.entry_price,
                            exit_price=exit_price,
                            size_btc=sz,
                            gross_pnl_usd=gross_pnl,
                            fees_usd=total_fees,
                            net_pnl_usd=net_pnl,
                            return_bps=(net_pnl / (state.entry_price * sz)) * 10_000.0,
                            exit_reason=exit_reason,
                            execution_type=exec_label,
                        )
                        state.trades.append(record)
                        self.position_events.append({
                            "time_ms": timestamp_ms,
                            "event": "CLOSE",
                            "strategy": s_name,
                            "side": "LONG",
                            "size_btc": sz,
                            "price": exit_price,
                            "exec": exec_label,
                            "reason": exit_reason,
                            "net_pnl": net_pnl,
                            "return_bps": (net_pnl / (state.entry_price * sz)) * 10_000.0,
                        })
                        state.position_btc = 0.0
                        state.entry_price = 0.0
                        state.entry_fee_usd = 0.0
                        state.trailing_stop_active = False
                        state.stop_price = 0.0

                else:
                    state.trough_price = min(state.trough_price, mid_price)
                    gain_bps = ((state.entry_price - mid_price) / state.entry_price) * 10_000.0

                    if gain_bps >= trail_act_bps:
                        state.trailing_stop_active = True
                        trailing_ceiling = state.trough_price * (1.0 + (trail_dist_bps / 10_000.0))
                        if not is_maker:
                            fee_pct = taker_fee_pct + (maker_rebate_pct if self.bt_cfg.taker_exit_as_maker_on_tp else taker_fee_pct)
                            fee_ceiling = state.entry_price * (1.0 - fee_pct)
                            if state.trough_price < fee_ceiling:
                                trailing_ceiling = min(trailing_ceiling, fee_ceiling)
                        safe_stop = max(mid_price * 1.0001, trailing_ceiling)
                        state.stop_price = min(state.stop_price, safe_stop)

                    exit_reason = None
                    if gain_bps >= tp_bps:
                        exit_reason = "TAKE_PROFIT"
                    elif mid_price >= state.stop_price:
                        exit_reason = "TRAILING_STOP" if state.trailing_stop_active else "STOP_LOSS"
                    elif score >= reversal_thresh:
                        exit_reason = "SIGNAL_REVERSAL"
                    elif holding_time_secs >= max_hold_secs:
                        exit_reason = "TIME_LIMIT"

                    if exit_reason:
                        if is_maker and exit_reason != "STOP_LOSS":
                            exit_price = best_bid
                            fee = -abs(exit_price * abs(state.position_btc) * maker_rebate_pct)
                            exec_label = "MAKER"
                        elif not is_maker and exit_reason != "STOP_LOSS" and self.bt_cfg.taker_exit_as_maker_on_tp:
                            exit_price = best_bid
                            fee = -abs(exit_price * abs(state.position_btc) * maker_rebate_pct)
                            exec_label = f"MAKER ({exit_reason[:4]})"
                        else:
                            exit_price = best_ask * (1.0 + slippage_pct)
                            fee = exit_price * abs(state.position_btc) * taker_fee_pct
                            exec_label = "TAKER"

                        sz = abs(state.position_btc)
                        total_fees = state.entry_fee_usd + fee
                        gross_pnl = (state.entry_price - exit_price) * sz
                        net_pnl = gross_pnl - total_fees
                        state.cash_usd += (gross_pnl - fee)

                        record = TradeRecord(
                            strategy_name=s_name,
                            entry_time_ms=state.entry_time_ms,
                            exit_time_ms=timestamp_ms,
                            side="SHORT",
                            entry_price=state.entry_price,
                            exit_price=exit_price,
                            size_btc=sz,
                            gross_pnl_usd=gross_pnl,
                            fees_usd=total_fees,
                            net_pnl_usd=net_pnl,
                            return_bps=(net_pnl / (state.entry_price * sz)) * 10_000.0,
                            exit_reason=exit_reason,
                            execution_type=exec_label,
                        )
                        state.trades.append(record)
                        self.position_events.append({
                            "time_ms": timestamp_ms,
                            "event": "CLOSE",
                            "strategy": s_name,
                            "side": "SHORT",
                            "size_btc": sz,
                            "price": exit_price,
                            "exec": exec_label,
                            "reason": exit_reason,
                            "net_pnl": net_pnl,
                            "return_bps": (net_pnl / (state.entry_price * sz)) * 10_000.0,
                        })
                        state.position_btc = 0.0
                        state.entry_price = 0.0
                        state.entry_fee_usd = 0.0
                        state.trailing_stop_active = False
                        state.stop_price = 0.0

            # Entry Gating
            else:
                if spread_bps > self.bt_cfg.max_spread_bps:
                    continue

                sz = self.bt_cfg.order_size_btc

                if score >= entry_thresh:
                    if is_maker:
                        entry_price = best_bid
                        fee = -abs(entry_price * sz * maker_rebate_pct)
                    else:
                        entry_price = best_ask * (1.0 + slippage_pct)
                        fee = entry_price * sz * taker_fee_pct

                    state.entry_fee_usd = fee
                    state.cash_usd -= fee
                    state.position_btc = sz
                    state.entry_price = entry_price
                    state.entry_time_ms = timestamp_ms
                    state.peak_price = entry_price
                    state.trailing_stop_active = False
                    state.stop_price = entry_price * (1.0 - (sl_bps / 10_000.0))

                    self.position_events.append({
                        "time_ms": timestamp_ms,
                        "event": "OPEN",
                        "strategy": s_name,
                        "side": "LONG",
                        "size_btc": sz,
                        "price": entry_price,
                        "exec": "MAKER" if is_maker else "TAKER",
                        "reason": f"Sig {score:+.2f}",
                        "stop_price": state.stop_price,
                        "net_pnl": 0.0,
                        "return_bps": 0.0,
                    })

                elif score <= -entry_thresh:
                    if is_maker:
                        entry_price = best_ask
                        fee = -abs(entry_price * sz * maker_rebate_pct)
                    else:
                        entry_price = best_bid * (1.0 - slippage_pct)
                        fee = entry_price * sz * taker_fee_pct

                    state.entry_fee_usd = fee
                    state.cash_usd -= fee
                    state.position_btc = -sz
                    state.entry_price = entry_price
                    state.entry_time_ms = timestamp_ms
                    state.trough_price = entry_price
                    state.trailing_stop_active = False
                    state.stop_price = entry_price * (1.0 + (sl_bps / 10_000.0))

                    self.position_events.append({
                        "time_ms": timestamp_ms,
                        "event": "OPEN",
                        "strategy": s_name,
                        "side": "SHORT",
                        "size_btc": sz,
                        "price": entry_price,
                        "exec": "MAKER" if is_maker else "TAKER",
                        "reason": f"Sig {score:+.2f}",
                        "stop_price": state.stop_price,
                        "net_pnl": 0.0,
                        "return_bps": 0.0,
                    })

    def get_signal_metrics(self, strategy_or_signal_name: str, horizon_secs: int = 5) -> Dict[str, Any]:
        """Calculates IC, Rank IC, t-stat, p-value, and directional hit rate for the underlying signal."""
        signal_key = strategy_or_signal_name
        if strategy_or_signal_name in self.strategy_defs:
            signal_key = self.strategy_defs[strategy_or_signal_name][0]

        pairs = self.eval_data.get(signal_key, {}).get(horizon_secs, [])
        if len(pairs) < 5:
            return {
                "samples": len(pairs),
                "ic": 0.0,
                "rank_ic": 0.0,
                "t_stat": 0.0,
                "p_val": 1.0,
                "hit_rate": 50.0,
            }

        sigs = np.array([p[0] for p in pairs])
        rets = np.array([p[1] for p in pairs])

        mask = np.abs(sigs) > 0.02
        if np.sum(mask) >= 3:
            hits = (np.sign(sigs[mask]) == np.sign(rets[mask]))
            hit_rate = float(np.mean(hits)) * 100.0
        else:
            hit_rate = 50.0

        if np.std(sigs) > 1e-7 and np.std(rets) > 1e-7:
            if _HAS_SCIPY and stats is not None:
                ic, p_val = stats.pearsonr(sigs, rets)
                rank_ic, _ = stats.spearmanr(sigs, rets)
            else:
                ic = float(np.corrcoef(sigs, rets)[0, 1])
                rank_sigs = np.argsort(np.argsort(sigs)).astype(float)
                rank_rets = np.argsort(np.argsort(rets)).astype(float)
                rank_ic = float(np.corrcoef(rank_sigs, rank_rets)[0, 1])
                p_val = 0.05
            n = len(sigs)
            t_stat = ic * math.sqrt((n - 2) / max(1e-6, 1.0 - ic**2))
        else:
            ic, rank_ic, t_stat, p_val = 0.0, 0.0, 0.0, 1.0

        return {
            "samples": len(pairs),
            "ic": float(ic),
            "rank_ic": float(rank_ic),
            "t_stat": float(t_stat),
            "p_val": float(p_val),
            "hit_rate": float(hit_rate),
        }

    def get_strategy_performance(self, strategy_name: str, current_price: float) -> Dict[str, Any]:
        """Computes comprehensive paper-trading performance metrics."""
        state = self.strategies.get(strategy_name)
        if not state:
            return {}

        trades = state.trades
        n_trades = len(trades)
        net_pnl = sum(t.net_pnl_usd for t in trades)
        unrealized = (
            state.position_btc * (current_price - state.entry_price)
            if state.is_in_position
            else 0.0
        )
        total_pnl = net_pnl + unrealized
        total_fees = sum(t.fees_usd for t in trades) + (state.entry_fee_usd if state.is_in_position else 0.0)

        if n_trades > 0:
            wins = [t for t in trades if t.net_pnl_usd > 0]
            losses = [t for t in trades if t.net_pnl_usd <= 0]
            win_rate = (len(wins) / n_trades) * 100.0
            gross_win = sum(t.net_pnl_usd for t in wins)
            gross_loss = abs(sum(t.net_pnl_usd for t in losses))
            profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 1.0)
            pnl_returns = [t.return_bps for t in trades]
            avg_return_bps = float(np.mean(pnl_returns))
            std_return_bps = float(np.std(pnl_returns)) if len(pnl_returns) > 1 else 1.0
            sharpe = (avg_return_bps / std_return_bps) * math.sqrt(252 * 24 * 60) if std_return_bps > 0 else 0.0
        else:
            win_rate = 0.0
            profit_factor = 0.0
            sharpe = 0.0
            avg_return_bps = 0.0

        return {
            "strategy": strategy_name,
            "type": state.execution_type,
            "trades": n_trades,
            "total_pnl_usd": total_pnl,
            "realized_pnl_usd": net_pnl,
            "unrealized_pnl_usd": unrealized,
            "fees_paid_usd": total_fees,
            "win_rate_pct": win_rate,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            "max_drawdown_usd": state.max_drawdown_usd,
            "in_position": state.is_in_position,
            "position_btc": state.position_btc,
            "avg_return_bps": avg_return_bps,
        }

    def get_active_positions(self, current_price: float, now_ms: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns details on all currently open strategy positions."""
        now = now_ms or int(time.time() * 1000)
        positions = []
        for s_name in self.strategy_names:
            state = self.strategies[s_name]
            if state.is_in_position:
                is_long = state.position_btc > 0
                sz = abs(state.position_btc)
                unrealized = state.position_btc * (current_price - state.entry_price)
                unrealized_bps = (
                    ((current_price - state.entry_price) / state.entry_price)
                    * 10_000.0
                    * (1.0 if is_long else -1.0)
                )
                hold_secs = max(0.0, (now - state.entry_time_ms) / 1000.0)
                positions.append({
                    "strategy": s_name,
                    "side": "LONG" if is_long else "SHORT",
                    "size_btc": sz,
                    "entry_price": state.entry_price,
                    "current_price": current_price,
                    "unrealized_pnl_usd": unrealized,
                    "unrealized_bps": unrealized_bps,
                    "stop_price": state.stop_price,
                    "trailing_active": state.trailing_stop_active,
                    "hold_secs": hold_secs,
                    "exec": state.execution_type,
                })
        return positions

    def get_recent_position_events(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Returns the most recent position lifecycle events (OPEN & CLOSE)."""
        return list(self.position_events)[-limit:]


class StrategyExecutionEngine(EdgeEvaluator):
    """Execution engine subclass for backward compatibility with simple .step() calls."""

    def __init__(
        self,
        order_size_btc: float = 0.1,
        initial_cash_usd: float = 10_000.0,
        taker_fee_bps: float = 3.5,
        maker_rebate_bps: float = -0.2,
        slippage_bps: float = 0.2,
    ):
        market_cfg = MarketConfig(
            taker_fee_bps=taker_fee_bps,
            maker_rebate_bps=maker_rebate_bps,
        )
        bt_cfg = BacktestConfig(
            order_size_btc=order_size_btc,
            initial_cash_usd=initial_cash_usd,
            slippage_bps=slippage_bps,
        )
        super().__init__(market_cfg=market_cfg, bt_cfg=bt_cfg)
