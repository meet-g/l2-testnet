"""Order book representation, tracking, and microstructure metric calculations."""

from collections import deque
from dataclasses import dataclass, field
import math
import time
from typing import Any, Deque, Dict, List, Optional, Tuple


@dataclass
class L2Level:
    px: float
    sz: float
    n: int  # Number of orders at this level (Hyperliquid specific feature)

    @property
    def avg_order_size(self) -> float:
        return self.sz / max(self.n, 1)

    @property
    def notional(self) -> float:
        return self.px * self.sz


@dataclass
class BookSnapshot:
    timestamp_ms: int
    bids: List[L2Level]
    asks: List[L2Level]


class OrderBook:
    """Maintains real-time granular L2 order book and deep macro order book for Hyperliquid.
    
    Provides high-speed microstructure calculations including weighted mid-price,
    multi-tier depth imbalances, order concentration metrics, macro resting walls,
    and historical deltas across both 1-tick touch levels and aggregated macro depth.
    """

    def __init__(self, coin: str = "BTC", max_history: int = 500):
        self.coin = coin
        self.max_history = max_history
        self.bids: List[L2Level] = []
        self.asks: List[L2Level] = []
        self.last_update_time_ms: int = 0
        self.history: Deque[BookSnapshot] = deque(maxlen=max_history)
        self.update_count: int = 0

        # Macro / Aggregated depth book (e.g. from nSigFigs=4 or deeper runtime subscription)
        self.macro_bids: List[L2Level] = []
        self.macro_asks: List[L2Level] = []
        self.last_macro_update_time_ms: int = 0
        self.macro_update_count: int = 0

        # Real-time Perpetual Market Context (from activeAssetCtx)
        self.funding_rate: float = 0.0
        self.open_interest: float = 0.0
        self.oracle_price: float = 0.0
        self.mark_price: float = 0.0
        self.premium_bps: float = 0.0
        self.day_ntl_vlm: float = 0.0
        self.last_ctx_time_ms: int = 0

    def update_asset_ctx(self, ctx_data: Dict[str, Any]) -> None:
        """Parses activeAssetCtx payload from Hyperliquid (funding, OI, oracle, premium)."""
        ctx = ctx_data.get("ctx", ctx_data)
        if not isinstance(ctx, dict):
            return
        try:
            self.funding_rate = float(ctx.get("funding", 0.0))
            self.open_interest = float(ctx.get("openInterest", 0.0))
            self.oracle_price = float(ctx.get("oraclePx", 0.0))
            self.mark_price = float(ctx.get("markPx", 0.0))
            self.day_ntl_vlm = float(ctx.get("dayNtlVlm", 0.0))
            premium_raw = float(ctx.get("premium", 0.0))
            self.premium_bps = premium_raw * 10_000.0
            self.last_ctx_time_ms = int(time.time() * 1000)
        except (ValueError, TypeError):
            pass

    @property
    def basis_bps(self) -> float:
        """Difference between top-of-book mid price and Pyth oracle price in basis points."""
        if self.oracle_price > 0 and self.mid_price > 0:
            return ((self.mid_price - self.oracle_price) / self.oracle_price) * 10_000.0
        return self.premium_bps

    def update_from_raw(self, raw_data: Dict[str, Any], is_macro: Optional[bool] = None) -> None:
        """Parses and updates the order book from Hyperliquid WS or REST payload.
        
        Supports both raw 1-tick order books and aggregated macro depth (e.g. nSigFigs=4).
        If is_macro is None, automatically detects macro book by analyzing level tick spacing.
        """
        levels = raw_data.get("levels", [[], []])
        if len(levels) < 2:
            return

        raw_bids, raw_asks = levels[0], levels[1]
        timestamp = raw_data.get("time", int(time.time() * 1000))

        # Parse bids (ensure sorted descending)
        parsed_bids = [
            L2Level(px=float(l["px"]), sz=float(l["sz"]), n=int(l.get("n", 1)))
            for l in raw_bids
        ]
        parsed_bids.sort(key=lambda x: x.px, reverse=True)

        # Parse asks (ensure sorted ascending)
        parsed_asks = [
            L2Level(px=float(l["px"]), sz=float(l["sz"]), n=int(l.get("n", 1)))
            for l in raw_asks
        ]
        parsed_asks.sort(key=lambda x: x.px)

        # Only treat as macro if explicitly requested via is_macro=True
        if is_macro:
            self.macro_bids = parsed_bids
            self.macro_asks = parsed_asks
            self.last_macro_update_time_ms = timestamp
            self.macro_update_count += 1
            if not self.bids:
                self.bids = parsed_bids
                self.asks = parsed_asks
                self.last_update_time_ms = timestamp
                self.update_count += 1
            return

        # Granular / Microstructure 1-tick book
        self.bids = parsed_bids
        self.asks = parsed_asks
        self.last_update_time_ms = timestamp
        self.update_count += 1

        # Store in rolling history for delta / VOI calculations
        snapshot = BookSnapshot(timestamp_ms=timestamp, bids=parsed_bids, asks=parsed_asks)
        self.history.append(snapshot)

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
    def notional_scale(self) -> float:
        """Dynamic notional scaling factor relative to baseline BTC ($85,000).
        
        Anchors size and depth thresholds (whales, liquidity holes, queue depletion)
        to equivalent USD notional value across any asset (e.g. HYPE, ETH, SOL).
        """
        if self.coin.upper() == "BTC" or self.mid_price <= 0:
            return 1.0
        return 85000.0 / max(self.mid_price, 1e-4)

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
        """Computes top-of-book volume weighted mid-price (P_imb).
        
        P_imb = P_b * (Q_a / (Q_b + Q_a)) + P_a * (Q_b / (Q_b + Q_a))
        Notice: if bid volume Q_b is larger, the price is pulled closer to P_a.
        """
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
        """Exponentially decayed multi-level depth imbalance.
        
        Weight of level k: w_k = exp(-decay_lambda * k).
        Closer levels have higher weight, but deeper resting liquidity is incorporated.
        """
        if not self.is_valid:
            return 0.0

        n_levels = min(k_levels, len(self.bids), len(self.asks))
        w_bids = 0.0
        w_asks = 0.0
        total_w = 0.0

        for i in range(n_levels):
            w = math.exp(-decay_lambda * i)
            w_bids += self.bids[i].sz * w
            w_asks += self.asks[i].sz * w
            total_w += w

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

            w_b = 1.0 / bid_dist
            w_a = 1.0 / ask_dist

            w_bids += self.bids[i].sz * w_b
            w_asks += self.asks[i].sz * w_a

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
        """Detects resting whale walls and distinguishes single-player vs distributed walls.
        
        Using Hyperliquid's order count 'n':
        - Single whale wall: high size, low order count (e.g. sz=10 BTC, n=1).
          High risk of spoofing/pulling when price approaches.
        - Distributed wall: high size, high order count (e.g. sz=10 BTC, n=40).
          Genuine structural liquidity defense.
        """
        scale = self.notional_scale
        scaled_min_sz = min_sz_btc * scale
        scaled_min_aos = min_aos * scale
        walls: Dict[str, List[Dict[str, Any]]] = {"bids": [], "asks": []}

        for i, level in enumerate(self.bids):
            if level.sz >= scaled_min_sz:
                is_single_whale = level.avg_order_size >= scaled_min_aos
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
            if level.sz >= scaled_min_sz:
                is_single_whale = level.avg_order_size >= scaled_min_aos
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

    @property
    def has_macro_book(self) -> bool:
        """Returns True if aggregated macro order book depth is active."""
        return len(self.macro_bids) > 0 and len(self.macro_asks) > 0

    def macro_depth_volume(self, k_levels: int = 10) -> Tuple[float, float]:
        """Returns total volume on macro bid and ask sides for top k levels."""
        if not self.has_macro_book:
            return 0.0, 0.0
        bid_vol = sum(level.sz for level in self.macro_bids[:k_levels])
        ask_vol = sum(level.sz for level in self.macro_asks[:k_levels])
        return bid_vol, ask_vol

    def macro_weighted_imbalance(self, k_levels: int = 20, decay_lambda: float = 0.12) -> float:
        """Exponentially decayed depth imbalance across the macro aggregated order book.
        
        Spans hundreds or thousands of dollars from mid price to capture macro resting walls.
        """
        if not self.has_macro_book:
            return 0.0

        n_levels = min(k_levels, len(self.macro_bids), len(self.macro_asks))
        w_bids = 0.0
        w_asks = 0.0
        for i in range(n_levels):
            w = math.exp(-decay_lambda * i)
            w_bids += self.macro_bids[i].sz * w
            w_asks += self.macro_asks[i].sz * w

        denom = w_bids + w_asks
        if denom <= 0:
            return 0.0
        return (w_bids - w_asks) / denom

    def combined_book_imbalance(
        self,
        granular_levels: int = 20,
        decay_granular: float = 0.20,
        macro_weight: float = 0.35,
    ) -> float:
        """Blends high-resolution touch order book imbalance with deep macro aggregated book imbalance."""
        granular_imb = self.weighted_imbalance(k_levels=granular_levels, decay_lambda=decay_granular)
        if not self.has_macro_book:
            return granular_imb
        macro_imb = self.macro_weighted_imbalance(k_levels=20, decay_lambda=0.12)
        return (1.0 - macro_weight) * granular_imb + macro_weight * macro_imb

    def find_macro_walls(self, min_sz_btc: float = 8.0) -> Dict[str, List[Dict[str, Any]]]:
        """Detects large macro walls in the aggregated order book."""
        scaled_min_sz = min_sz_btc * self.notional_scale
        walls: Dict[str, List[Dict[str, Any]]] = {"bids": [], "asks": []}
        if not self.has_macro_book:
            return walls

        for i, level in enumerate(self.macro_bids):
            if level.sz >= scaled_min_sz:
                walls["bids"].append({
                    "level_idx": i,
                    "px": level.px,
                    "sz": level.sz,
                    "n": level.n,
                    "dist_from_mid_bps": (self.mid_price - level.px) / max(self.mid_price, 1) * 10000,
                })

        for i, level in enumerate(self.macro_asks):
            if level.sz >= scaled_min_sz:
                walls["asks"].append({
                    "level_idx": i,
                    "px": level.px,
                    "sz": level.sz,
                    "n": level.n,
                    "dist_from_mid_bps": (level.px - self.mid_price) / max(self.mid_price, 1) * 10000,
                })

        return walls

    def get_previous_snapshot(self, offset: int = 1) -> Optional[BookSnapshot]:
        """Retrieves a historical book snapshot relative to current time."""
        idx = len(self.history) - 1 - offset
        if 0 <= idx < len(self.history):
            return self.history[idx]
        return None
