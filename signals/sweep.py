"""Book Sweep and Liquidity Hole Elasticity Signal."""

from collections import deque
import time
from typing import Deque, Optional, Tuple

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult


class SweepSignal(BaseSignal):
    """Detects multi-level order book sweeps and tests post-impact book replenishment elasticity.
    
    Microstructure Edge:
    - Resilient Sweep (Fade / Mean Reversion):
        When a sweep takes out 2+ levels, if limit orders replenish the depth within 300ms,
        the price typically reverts back to the pre-sweep level.
    - Cascading Void (Liquidity Hole / Momentum):
        If resting liquidity evaporates (cancellations follow the sweep), price breaks out.
    """

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
        self.active_sweep: Optional[dict] = None

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

        # Detect sweep from recent trades
        recent_large = trades.get_recent_large_trades(min_sz_btc=self.min_sweep_btc, lookback_secs=0.5)

        score = 0.0
        pattern = "STABLE"

        scale = getattr(book, "notional_scale", 1.0)
        px_hurdle = max(book.mid_price * 1.2e-5, 0.001)

        if recent_large:
            last_t = recent_large[0]
            # Check if this large trade moved the top of book significantly
            if last_t.is_buy and self.last_ask_top > 0 and best_a > self.last_ask_top + px_hurdle:
                # Upward sweep occurred
                # Check top-of-book ask replenishment
                ask_top_sz = book.best_ask_sz
                if ask_top_sz >= 1.0 * scale:
                    # Quick replenishment -> fade (mean reversion downward)
                    score = -0.5
                    pattern = "SWEEP_BUY_REPLENISHED_FADE"
                else:
                    # Void -> momentum up
                    score = 0.6
                    pattern = "SWEEP_BUY_VOID_MOMENTUM"

            elif (not last_t.is_buy) and self.last_bid_top > 0 and best_b < self.last_bid_top - px_hurdle:
                # Downward sweep occurred
                bid_top_sz = book.best_bid_sz
                if bid_top_sz >= 1.0 * scale:
                    # Quick replenishment -> fade (mean reversion upward)
                    score = 0.5
                    pattern = "SWEEP_SELL_REPLENISHED_FADE"
                else:
                    # Void -> momentum down
                    score = -0.6
                    pattern = "SWEEP_SELL_VOID_MOMENTUM"

        self.last_bid_top = best_b
        self.last_ask_top = best_a

        spread_bps = (best_a - best_b) / max(book.mid_price, 1e-4) * 10000.0 if book.mid_price > 0 else 0.0
        spread_factor = 1.0 / (1.0 + max(0.0, spread_bps - 1.0) * 0.1)
        confidence = max(0.0, min(1.0, (0.75 * spread_factor) if pattern != "STABLE" else 0.1))

        return SignalResult(
            name=self.name,
            score=score,
            raw_value=score,
            confidence=confidence,
            timestamp_ms=now_ms,
            metadata={"pattern": pattern},
        )
