"""Volume Order Imbalance (VOI) Signal (Cont, Kukanov, Stoikov, 2014)."""

from collections import deque
import math
from typing import Deque, Optional, Tuple

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.base import BaseSignal, SignalResult


class VOISignal(BaseSignal):
    """Volume Order Imbalance (VOI) tracking top-of-book order flow dynamics.
    
    Reference:
        Cont, R., Kukanov, A., & Stoikov, S. (2014).
        "The Price Impact of Order Book Events", Journal of Financial Econometrics.
        
    Mathematical Formulation:
        delta_V_B = Q_b(t)               if P_b(t) > P_b(t-1)
                    Q_b(t) - Q_b(t-1)     if P_b(t) == P_b(t-1)
                    0                     if P_b(t) < P_b(t-1)

        delta_V_A = Q_a(t)               if P_a(t) < P_a(t-1)
                    Q_a(t) - Q_a(t-1)     if P_a(t) == P_a(t-1)
                    0                     if P_a(t) > P_a(t-1)

        VOI(t) = delta_V_B(t) - delta_V_A(t)
    """

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

        self.voi_history: Deque[float] = deque(maxlen=history_window)
        self.recent_30: Deque[float] = deque(maxlen=30)
        self.voi_time_history: Deque[Tuple[int, float]] = deque(maxlen=5000)
        self.rolling_voi_sum: float = 0.0

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

        # First snapshot initialization
        if self.prev_bid_px == 0.0 or self.prev_ask_px == 0.0:
            self.prev_bid_px = curr_bid_px
            self.prev_bid_sz = curr_bid_sz
            self.prev_ask_px = curr_ask_px
            self.prev_ask_sz = curr_ask_sz
            return SignalResult(name=self.name, score=0.0, raw_value=0.0, confidence=0.0)

        # 1. Calculate delta V_B
        if curr_bid_px > self.prev_bid_px:
            delta_vb = curr_bid_sz
        elif curr_bid_px == self.prev_bid_px:
            delta_vb = curr_bid_sz - self.prev_bid_sz
        else:
            delta_vb = 0.0

        # 2. Calculate delta V_A
        if curr_ask_px < self.prev_ask_px:
            delta_va = curr_ask_sz
        elif curr_ask_px == self.prev_ask_px:
            delta_va = curr_ask_sz - self.prev_ask_sz
        else:
            delta_va = 0.0

        # Instantaneous VOI
        instant_voi = delta_vb - delta_va

        # Update previous book state
        self.prev_bid_px = curr_bid_px
        self.prev_bid_sz = curr_bid_sz
        self.prev_ask_px = curr_ask_px
        self.prev_ask_sz = curr_ask_sz

        # Store in rolling windows (both count-based and time-based)
        self.voi_history.append(instant_voi)
        self.recent_30.append(instant_voi)

        use_time_window = False
        if now_ms and now_ms > 1000:
            self.voi_time_history.append((now_ms, instant_voi))
            cutoff_ms = now_ms - 120_000
            while self.voi_time_history and self.voi_time_history[0][0] < cutoff_ms:
                self.voi_time_history.popleft()
            if self.voi_time_history and (now_ms - self.voi_time_history[0][0]) >= 3000:
                use_time_window = True

        if use_time_window:
            recent_cutoff = now_ms - 30_000
            recent_vals = [v for t, v in self.voi_time_history if t >= recent_cutoff]
            cum_voi = sum(recent_vals)
            n_recent = max(1, len(recent_vals))
            all_vals = [v for _, v in self.voi_time_history]
            n_all = len(all_vals)
        else:
            cum_voi = sum(self.recent_30)
            n_recent = len(self.recent_30)
            all_vals = list(self.voi_history)
            n_all = len(self.voi_history)

        scale = getattr(book, "notional_scale", 1.0)
        spread_factor = max(0.2, 1.0 - (book.spread_bps / 5.0))

        # Standardize via rolling mean and standard deviation
        if n_all >= 15:
            mean_v = sum(all_vals) / n_all
            variance = sum((x - mean_v) ** 2 for x in all_vals) / n_all
            std_v = math.sqrt(variance) if variance > 1e-6 else 1.0

            z_score = (cum_voi - n_recent * mean_v) / (std_v * math.sqrt(n_recent))
            z_score = max(-self.z_score_clip, min(self.z_score_clip, z_score))
            # Smoothly map to [-1.0, 1.0] using tanh
            score = math.tanh(z_score / 1.5)
            confidence = min(1.0, (n_all / self.history_window) * spread_factor)
        else:
            score = math.tanh(cum_voi / max(2.0 * scale, 0.01))
            confidence = min(1.0, (n_all / 30.0) * spread_factor)

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
