"""Real-time trade stream processor, volume delta (CVD) tracking, and VPIN bucketizer."""

from collections import deque
from dataclasses import dataclass
import time
from typing import Any, Deque, Dict, List, Optional, Tuple


@dataclass
class Trade:
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
    """Processes incoming trade ticks from Hyperliquid WS/REST.
    
    Maintains:
    - Recent tick history with millisecond timestamps
    - Rolling Cumulative Volume Delta (CVD) across multiple time horizons
    - Discrete fixed-volume buckets for Easley-Lopez de Prado-O'Hara VPIN calculation
    - Large trade burst / aggressive sweep detection
    """

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
        self._cvd_cache: Dict[float, Tuple[float, float, float]] = {}

        # VPIN Volume bucket tracking
        self.completed_buckets: Deque[VolumeBucket] = deque(maxlen=max_vpin_buckets)
        self.current_bucket: VolumeBucket = VolumeBucket(
            bucket_idx=0,
            target_vol=self.vpin_bucket_size,
            start_time_ms=int(time.time() * 1000),
        )

    def process_raw_trades(self, raw_trades: List[Dict[str, Any]]) -> List[Trade]:
        """Parses and ingests a list of raw trade dicts from Hyperliquid.
        
        Raw trade format:
        {
            "coin": "BTC",
            "side": "B" | "A",
            "px": "65000.0",
            "sz": "0.1",
            "time": 1710000000000,
            "hash": "0x...",
            "tid": 123456
        }
        """
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
        self._cvd_cache.clear()

        # Ingest into VPIN volume buckets
        self._ingest_vpin_volume(trade)

    def _ingest_vpin_volume(self, trade: Trade) -> None:
        """Splits trade volume into constant-volume buckets for VPIN."""
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
            else:
                # Fill the current bucket completely
                if is_buy:
                    self.current_bucket.buy_vol += needed
                else:
                    self.current_bucket.sell_vol += needed

                self.current_bucket.end_price = px
                self.current_bucket.end_time_ms = t_ms
                remaining_vol -= needed

                # Archive completed bucket
                self.completed_buckets.append(self.current_bucket)

                # Initialize next bucket
                # Initialize next bucket
                new_idx = self.current_bucket.bucket_idx + 1
                self.current_bucket = VolumeBucket(
                    bucket_idx=new_idx,
                    target_vol=self.vpin_bucket_size * self.notional_scale,
                    start_time_ms=t_ms,
                    start_price=px,
                )

    @property
    def notional_scale(self) -> float:
        """Dynamic notional scaling factor relative to baseline BTC ($85,000)."""
        if self.coin.upper() == "BTC" or self.last_price <= 0:
            return 1.0
        return 85000.0 / max(self.last_price, 1e-4)

    def get_cvd_in_window(self, window_secs: float) -> Tuple[float, float, float]:
        """Calculates (CVD, BuyVol, SellVol) over the last N seconds."""
        if window_secs in self._cvd_cache:
            return self._cvd_cache[window_secs]

        now_ms = self.last_trade_time_ms or int(time.time() * 1000)
        cutoff_ms = now_ms - int(window_secs * 1000)

        cvd = 0.0
        buy_vol = 0.0
        sell_vol = 0.0

        for t in reversed(self.trades):
            if t.timestamp_ms < cutoff_ms:
                break
            if t.side == "B":
                buy_vol += t.size
                cvd += t.size
            else:
                sell_vol += t.size
                cvd -= t.size

        res = (cvd, buy_vol, sell_vol)
        self._cvd_cache[window_secs] = res
        return res

    def get_recent_large_trades(
        self, min_sz_btc: float = 1.0, lookback_secs: float = 10.0
    ) -> List[Trade]:
        """Finds recent aggressive orders exceeding size threshold."""
        now_ms = self.last_trade_time_ms or int(time.time() * 1000)
        cutoff_ms = now_ms - int(lookback_secs * 1000)

        min_sz = min_sz_btc * self.notional_scale
        large = []
        for t in reversed(self.trades):
            if t.timestamp_ms < cutoff_ms:
                break
            if t.size >= min_sz:
                large.append(t)
        return large

    def calculate_vpin(self, n_buckets: int = 30) -> Optional[float]:
        """Calculates Easley, Lopez de Prado, O'Hara Volume-Synchronized Probability of Toxicity.
        
        VPIN = sum_{tau=1}^N |V_B - V_S| / (N * V)
        Returns a value between 0.0 (perfectly balanced volume) and 1.0 (pure toxic informed one-way flow).
        """
        if len(self.completed_buckets) < n_buckets:
            # Not enough buckets completed yet
            return None

        recent = list(self.completed_buckets)[-n_buckets:]
        total_imbalance = sum(b.abs_imbalance for b in recent)
        total_volume = sum(b.total_vol for b in recent)

        if total_volume <= 0:
            return 0.0

        return total_imbalance / total_volume
