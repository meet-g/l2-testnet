"""Dual-WebSocket Order Comparator.

Compares order flow and resting book liquidity captured by Hyperliquid's
normal (20-level, lower frequency) and fast (5-level, high frequency) WebSocket feeds
over a configurable time interval.

Validates whether:
1. The fast stream captures intermediate resting orders, transient liquidity,
   and queue transitions that the normal stream misses.
2. The normal stream captures deep structural liquidity (levels 6-20) that
   the fast stream misses.
3. Quantifies the empirical lead-time latency advantage of the fast stream.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class OrderState:
    """Represents an order book price level / resting order state."""
    side: str   # "bid" or "ask"
    px: float   # Price level
    sz: float   # Aggregate size at level
    n: int      # Count of resting orders at level

    def __repr__(self) -> str:
        return f"{self.side.upper()} @ {self.px:.4f} (sz={self.sz:.4f}, n={self.n})"


@dataclass
class DualComparisonReport:
    """Detailed comparison report over an evaluation interval."""
    coin: str
    interval_secs: float
    start_time_s: float
    end_time_s: float

    normal_msg_count: int
    fast_msg_count: int
    normal_hz: float
    fast_hz: float

    unique_orders_fast: int
    unique_orders_normal: int
    common_orders_count: int

    fast_only_orders: List[OrderState]
    normal_only_orders: List[OrderState]
    common_orders: List[OrderState]

    fast_only_prices: List[Tuple[str, float]]
    normal_only_prices: List[Tuple[str, float]]

    fast_only_intermediate_updates: List[OrderState]
    normal_only_deep_orders: List[OrderState]

    lead_times_ms: List[float]
    avg_lead_time_ms: float
    max_lead_time_ms: float
    min_lead_time_ms: float

    queue_transitions_fast: int
    queue_transitions_normal: int

    def summary(self) -> str:
        """Generates a human-readable summary of the comparison."""
        lines = [
            "=" * 78,
            f"DUAL WEBSOCKET ORDER COMPARISON REPORT ({self.coin})",
            f"Evaluation Interval: {self.interval_secs:.2f}s",
            "=" * 78,
            f"Message Throughput:",
            f"  • Normal WebSocket : {self.normal_msg_count} msgs ({self.normal_hz:.2f} Hz, full 20 levels)",
            f"  • Fast WebSocket   : {self.fast_msg_count} msgs ({self.fast_hz:.2f} Hz, top 5 levels)",
            "-" * 78,
            f"Order Capture & Visibility:",
            f"  • Unique Order States seen by Fast   : {self.unique_orders_fast}",
            f"  • Unique Order States seen by Normal : {self.unique_orders_normal}",
            f"  • Shared / Common Order States       : {self.common_orders_count}",
            f"  • Fast-Only Orders (Missed by Normal): {len(self.fast_only_orders)}",
            f"      - Brand new price levels         : {len(self.fast_only_prices)}",
            f"      - Intermediate (size/count) steps: {len(self.fast_only_intermediate_updates)}",
            f"  • Normal-Only Orders (Missed by Fast): {len(self.normal_only_orders)}",
            f"      - Deep book levels (levels 6-20) : {len(self.normal_only_deep_orders)}",
            "-" * 78,
            f"Detection Latency Advantage (Lead Time):",
            f"  • Avg Lead Time (Fast vs Normal)     : {self.avg_lead_time_ms:.2f} ms",
            f"  • Max Lead Time                      : {self.max_lead_time_ms:.2f} ms",
            "=" * 78,
        ]
        return "\n".join(lines)


class DualWebSocketOrderComparator:
    """Collects and compares orders/book states from fast and normal WebSocket streams."""

    def __init__(self, coin: str = "BTC"):
        self.coin = coin
        self.reset()

    def reset(self) -> None:
        """Clears all accumulated observations."""
        self.normal_events: List[Tuple[float, Dict[str, Any]]] = []
        self.fast_events: List[Tuple[float, Dict[str, Any]]] = []

        # Maps stream_type -> dict: OrderState -> list of reception timestamps
        self.order_timestamps: Dict[str, Dict[OrderState, List[float]]] = {
            "normal": {},
            "fast": {},
        }

        # Maps stream_type -> dict: (side, px) -> list of (timestamp, sz, n)
        self.price_history: Dict[str, Dict[Tuple[str, float], List[Tuple[float, float, int]]]] = {
            "normal": {},
            "fast": {},
        }

        # First detection time of (side, px)
        self.first_price_detection: Dict[str, Dict[Tuple[str, float], float]] = {
            "normal": {},
            "fast": {},
        }

        # Depth level at which order was observed in Normal stream
        self.normal_order_depth: Dict[OrderState, int] = {}

    def process_message(self, stream_type: str, raw_or_dict: Any, recv_time_s: Optional[float] = None) -> None:
        """Processes an incoming l2Book message from either 'normal' or 'fast' stream."""
        if recv_time_s is None:
            recv_time_s = time.time()

        if isinstance(raw_or_dict, str):
            try:
                msg = json.loads(raw_or_dict)
            except Exception:
                return
        elif isinstance(raw_or_dict, dict):
            msg = raw_or_dict
        else:
            return

        if msg.get("channel") != "l2Book":
            return

        data = msg.get("data")
        if not data or not isinstance(data, dict):
            return

        if stream_type == "normal":
            self.normal_events.append((recv_time_s, data))
        elif stream_type == "fast":
            self.fast_events.append((recv_time_s, data))
        else:
            raise ValueError(f"Unknown stream_type: {stream_type}. Expected 'normal' or 'fast'.")

        levels = data.get("levels", [[], []])
        raw_bids = levels[0] if len(levels) > 0 else []
        raw_asks = levels[1] if len(levels) > 1 else []

        # Ingest Bids
        for idx, lvl in enumerate(raw_bids):
            px = float(lvl["px"])
            sz = float(lvl["sz"])
            n = int(lvl.get("n", 1))
            state = OrderState(side="bid", px=px, sz=sz, n=n)

            self.order_timestamps[stream_type].setdefault(state, []).append(recv_time_s)
            self.price_history[stream_type].setdefault(("bid", px), []).append((recv_time_s, sz, n))
            if ("bid", px) not in self.first_price_detection[stream_type]:
                self.first_price_detection[stream_type][("bid", px)] = recv_time_s

            if stream_type == "normal":
                self.normal_order_depth[state] = idx

        # Ingest Asks
        for idx, lvl in enumerate(raw_asks):
            px = float(lvl["px"])
            sz = float(lvl["sz"])
            n = int(lvl.get("n", 1))
            state = OrderState(side="ask", px=px, sz=sz, n=n)

            self.order_timestamps[stream_type].setdefault(state, []).append(recv_time_s)
            self.price_history[stream_type].setdefault(("ask", px), []).append((recv_time_s, sz, n))
            if ("ask", px) not in self.first_price_detection[stream_type]:
                self.first_price_detection[stream_type][("ask", px)] = recv_time_s

            if stream_type == "normal":
                self.normal_order_depth[state] = idx

    def generate_report(self, interval_secs: Optional[float] = None) -> DualComparisonReport:
        """Analyzes accumulated data and returns a DualComparisonReport."""
        all_timestamps = [t for t, _ in self.normal_events] + [t for t, _ in self.fast_events]
        start_t = min(all_timestamps) if all_timestamps else 0.0
        end_t = max(all_timestamps) if all_timestamps else 0.0
        actual_interval = (end_t - start_t) if interval_secs is None else interval_secs
        actual_interval = max(0.001, actual_interval)

        normal_cnt = len(self.normal_events)
        fast_cnt = len(self.fast_events)

        normal_hz = normal_cnt / actual_interval
        fast_hz = fast_cnt / actual_interval

        fast_orders_set: Set[OrderState] = set(self.order_timestamps["fast"].keys())
        normal_orders_set: Set[OrderState] = set(self.order_timestamps["normal"].keys())

        common_orders = sorted(list(fast_orders_set & normal_orders_set), key=lambda x: (x.side, x.px))
        fast_only = sorted(list(fast_orders_set - normal_orders_set), key=lambda x: (x.side, x.px))
        normal_only = sorted(list(normal_orders_set - fast_orders_set), key=lambda x: (x.side, x.px))

        fast_prices_set: Set[Tuple[str, float]] = set(self.price_history["fast"].keys())
        normal_prices_set: Set[Tuple[str, float]] = set(self.price_history["normal"].keys())

        fast_only_prices = sorted(list(fast_prices_set - normal_prices_set))
        normal_only_prices = sorted(list(normal_prices_set - fast_prices_set))

        # Categorize fast-only orders into brand new prices vs intermediate size/count transitions
        fast_only_intermediate = [
            order for order in fast_only if (order.side, order.px) in normal_prices_set
        ]

        # Categorize normal-only orders: depth >= 5 is structurally beyond fast depth (top 5)
        normal_only_deep = [
            order for order in normal_only if self.normal_order_depth.get(order, 0) >= 5
        ]

        # Lead time calculation: For prices observed in both streams, how much earlier did Fast see it?
        lead_times_ms: List[float] = []
        for price_key in fast_prices_set & normal_prices_set:
            t_fast = self.first_price_detection["fast"].get(price_key)
            t_normal = self.first_price_detection["normal"].get(price_key)
            if t_fast is not None and t_normal is not None:
                diff_ms = (t_normal - t_fast) * 1000.0
                lead_times_ms.append(diff_ms)

        avg_lead = sum(lead_times_ms) / len(lead_times_ms) if lead_times_ms else 0.0
        max_lead = max(lead_times_ms) if lead_times_ms else 0.0
        min_lead = min(lead_times_ms) if lead_times_ms else 0.0

        # Queue transitions: count of total distinct updates across shared prices
        queue_trans_fast = sum(len(hist) for hist in self.price_history["fast"].values())
        queue_trans_normal = sum(len(hist) for hist in self.price_history["normal"].values())

        return DualComparisonReport(
            coin=self.coin,
            interval_secs=actual_interval,
            start_time_s=start_t,
            end_time_s=end_t,
            normal_msg_count=normal_cnt,
            fast_msg_count=fast_cnt,
            normal_hz=normal_hz,
            fast_hz=fast_hz,
            unique_orders_fast=len(fast_orders_set),
            unique_orders_normal=len(normal_orders_set),
            common_orders_count=len(common_orders),
            fast_only_orders=fast_only,
            normal_only_orders=normal_only,
            common_orders=common_orders,
            fast_only_prices=fast_only_prices,
            normal_only_prices=normal_only_prices,
            fast_only_intermediate_updates=fast_only_intermediate,
            normal_only_deep_orders=normal_only_deep,
            lead_times_ms=lead_times_ms,
            avg_lead_time_ms=avg_lead,
            max_lead_time_ms=max_lead,
            min_lead_time_ms=min_lead,
            queue_transitions_fast=queue_trans_fast,
            queue_transitions_normal=queue_trans_normal,
        )

    async def run_live(
        self,
        interval_secs: float = 10.0,
        ws_url: str = "wss://api.hyperliquid.xyz/ws",
    ) -> DualComparisonReport:
        """Connects to live Hyperliquid WebSocket and captures both normal and fast feeds concurrently."""
        import websockets

        self.reset()
        is_running = True

        async def _ping_heartbeat(ws):
            while is_running:
                try:
                    await asyncio.sleep(15.0)
                    if hasattr(ws, "closed") and ws.closed:
                        break
                    await ws.send(json.dumps({"method": "ping"}))
                except Exception:
                    break

        async def _run_normal_ws():
            try:
                async with websockets.connect(
                    ws_url, ping_interval=20, ping_timeout=20, max_size=20_000_000
                ) as ws:
                    sub = {"method": "subscribe", "subscription": {"type": "l2Book", "coin": self.coin}}
                    await ws.send(json.dumps(sub))
                    ping_task = asyncio.create_task(_ping_heartbeat(ws))
                    try:
                        while is_running:
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                                self.process_message("normal", msg, time.time())
                            except asyncio.TimeoutError:
                                pass
                    finally:
                        ping_task.cancel()
            except (asyncio.CancelledError, Exception):
                pass

        async def _run_fast_ws():
            try:
                async with websockets.connect(
                    ws_url, ping_interval=20, ping_timeout=20, max_size=20_000_000
                ) as ws:
                    sub = {
                        "method": "subscribe",
                        "subscription": {"type": "l2Book", "coin": self.coin, "fast": True},
                    }
                    await ws.send(json.dumps(sub))
                    ping_task = asyncio.create_task(_ping_heartbeat(ws))
                    try:
                        while is_running:
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                                self.process_message("fast", msg, time.time())
                            except asyncio.TimeoutError:
                                pass
                    finally:
                        ping_task.cancel()
            except (asyncio.CancelledError, Exception):
                pass

        task_normal = asyncio.create_task(_run_normal_ws())
        task_fast = asyncio.create_task(_run_fast_ws())

        try:
            await asyncio.sleep(interval_secs)
        finally:
            is_running = False
            task_normal.cancel()
            task_fast.cancel()
            # Allow graceful socket shutdown
            await asyncio.gather(task_normal, task_fast, return_exceptions=True)
            await asyncio.sleep(0.05)

        return self.generate_report(interval_secs=interval_secs)
