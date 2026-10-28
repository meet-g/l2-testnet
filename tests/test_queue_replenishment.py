"""Standalone Unit Verification Test Suite for QueueReplenishmentSignal.

Verifies:
1. Initialization & default hyperparameters
2. Degenerate books (empty, crossed, single-sided)
3. 1-tick static book stability
4. Asymmetric Level-1 and Level-3 replenishment (bullish and bearish)
5. Depletion latency persistence counter tracking
6. Multi-tier order cancellation asymmetry
7. Cross-coin dynamic notional scaling (BTC vs HYPE invariance)
8. Extreme trade stress, numerical overflow protection, NaN guards
9. Execution performance (< 0.1ms per compute call)
10. Strict SignalResult schema conformity & metadata keys
11. CompositeAlpha ensemble wiring & attribute parity

Run directly via:
    python tests/test_queue_replenishment.py
or:
    python -m unittest tests/test_queue_replenishment.py
"""

import math
import os
import sys
import time
import unittest
from typing import List

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.orderbook import L2Level, OrderBook
from core.trade_stream import Trade, TradeManager
from signals.base import SignalResult
from signals.queue_replenishment import QueueReplenishmentSignal
from signals.composite_alpha import CompositeAlphaSignal


class TestQueueReplenishmentSignal(unittest.TestCase):
    """Exhaustive test suite for QueueReplenishmentSignal microstructure alpha."""

    def setUp(self):
        self.signal = QueueReplenishmentSignal()

    def _create_mock_book(
        self,
        coin: str = "HYPE",
        mid_px: float = 25.00,
        spread: float = 0.01,
        depth_levels: int = 5,
        bid_sz: float = 100.0,
        ask_sz: float = 100.0,
        ts_ms: int = 1710000000000,
    ) -> OrderBook:
        """Helper to construct a deterministic OrderBook instance."""
        book = OrderBook(coin=coin, max_history=10, enable_history=False)
        half_spr = spread * 0.5
        bb = mid_px - half_spr
        ba = mid_px + half_spr

        bids: List[L2Level] = []
        asks: List[L2Level] = []
        for i in range(depth_levels):
            bids.append(L2Level(px=round(bb - i * spread, 6), sz=bid_sz * (1.0 + 0.1 * i), n=5 + i))
            asks.append(L2Level(px=round(ba + i * spread, 6), sz=ask_sz * (1.0 + 0.1 * i), n=5 + i))

        book.bids = bids
        book.asks = asks
        book.last_update_time_ms = ts_ms
        return book

    def _create_mock_trades(
        self,
        coin: str = "HYPE",
        trades_list: List[tuple] = None,
        base_ts_ms: int = 1710000000000,
    ) -> TradeManager:
        """Helper to construct a TradeManager with synthetic trades.
        trades_list is a list of (side, px, sz, offset_ms).
        """
        tm = TradeManager(coin=coin)
        if trades_list:
            raw = []
            for idx, (side, px, sz, offset_ms) in enumerate(trades_list):
                raw.append({
                    "coin": coin,
                    "side": side,
                    "px": str(px),
                    "sz": str(sz),
                    "time": base_ts_ms + offset_ms,
                    "tid": idx + 1,
                })
            tm.process_raw_trades(raw)
        return tm

    # =========================================================================
    # Test 1: Initialization & Defaults
    # =========================================================================
    def test_01_initialization_and_defaults(self):
        sig = QueueReplenishmentSignal()
        self.assertEqual(sig.name, "QueueReplenishment")
        self.assertTrue(hasattr(sig, "w_rep1"), "Missing w_rep1 attribute")
        self.assertTrue(hasattr(sig, "w_rep3"), "Missing w_rep3 attribute")
        self.assertTrue(hasattr(sig, "w_lat"), "Missing w_lat attribute")
        self.assertTrue(hasattr(sig, "w_canc"), "Missing w_canc attribute")

        # Verify weights sum to approximately 1.0
        total_w = sig.w_rep1 + sig.w_rep3 + sig.w_lat + sig.w_canc
        self.assertAlmostEqual(total_w, 1.0, places=4, msg="Sub-factor weights must sum to 1.0")

    # =========================================================================
    # Test 2: Degenerate Books (Empty, Uninitialized)
    # =========================================================================
    def test_02_empty_and_uninitialized_book(self):
        empty_book = OrderBook(coin="HYPE")
        empty_trades = TradeManager(coin="HYPE")
        res = self.signal.compute(empty_book, empty_trades)

        self.assertIsInstance(res, SignalResult)
        self.assertEqual(res.score, 0.0)
        self.assertEqual(res.raw_value, 0.0)
        self.assertEqual(res.confidence, 0.0)
        self.assertFalse(empty_book.is_valid)

    # =========================================================================
    # Test 3: Crossed and Single-Sided Books
    # =========================================================================
    def test_03_crossed_and_single_sided_book(self):
        # Crossed book: best bid > best ask
        book = OrderBook(coin="HYPE")
        book.bids = [L2Level(px=26.00, sz=100.0, n=5)]
        book.asks = [L2Level(px=25.00, sz=100.0, n=5)]
        book.last_update_time_ms = 1710000000000
        trades = TradeManager(coin="HYPE")

        res = self.signal.compute(book, trades)
        self.assertEqual(res.score, 0.0, "Crossed book must produce 0.0 score")
        self.assertEqual(res.confidence, 0.0)

        # Single-sided book: bids only
        book_bids_only = OrderBook(coin="HYPE")
        book_bids_only.bids = [L2Level(px=25.00, sz=100.0, n=5)]
        res_bids = self.signal.compute(book_bids_only, trades)
        self.assertEqual(res_bids.score, 0.0)

    # =========================================================================
    # Test 4: 1-Tick Static Book Stability (Zero Trades)
    # =========================================================================
    def test_04_static_1tick_book_stability(self):
        book = self._create_mock_book(mid_px=25.00, spread=0.01)
        trades = TradeManager(coin="HYPE")

        # First snapshot establishes baseline
        res1 = self.signal.compute(book, trades, timestamp_ms=1710000000000)
        self.assertIsInstance(res1, SignalResult)
        self.assertAlmostEqual(res1.score, 0.0, places=2)

        # Second snapshot: identical book, zero trades
        res2 = self.signal.compute(book, trades, timestamp_ms=1710000000100)
        self.assertAlmostEqual(res2.score, 0.0, places=3, msg="Static book with zero trades must yield neutral score")
        self.assertIn("l1_rep_bid", res2.metadata)
        self.assertIn("l1_rep_ask", res2.metadata)
        self.assertAlmostEqual(res2.metadata["l1_rep_bid"], 0.0, places=4)
        self.assertAlmostEqual(res2.metadata["l1_rep_ask"], 0.0, places=4)

    # =========================================================================
    # Test 5: Asymmetric Bid Replenishment (Bullish Conviction)
    # =========================================================================
    def test_05_asymmetric_bid_replenishment_bullish(self):
        sig = QueueReplenishmentSignal()
        t0 = 1710000000000

        # Snapshot 1: Baseline book (touch sizes = 100)
        book1 = self._create_mock_book(mid_px=25.00, spread=0.01, bid_sz=100.0, ask_sz=100.0, ts_ms=t0)
        trades = TradeManager(coin="HYPE")
        sig.compute(book1, trades, timestamp_ms=t0)

        # Inter-snapshot events:
        # Aggressive selling of 150.0 units hits the bid
        trades.process_raw_trades([
            {"coin": "HYPE", "side": "A", "px": "24.995", "sz": "150.0", "time": t0 + 50, "tid": 101}
        ])

        # Snapshot 2: Despite 150 units sold, bid touch replenishes to 200.0!
        # Meanwhile, ask touch drops to 20.0 with 0 buying volume
        book2 = self._create_mock_book(mid_px=25.00, spread=0.01, bid_sz=200.0, ask_sz=20.0, ts_ms=t0 + 100)
        res = sig.compute(book2, trades, timestamp_ms=t0 + 100)

        # R_b1 = (200 - 100) + 150 = 250.0 replenishment on bid
        # R_a1 = (20 - 100) + 0 = -80.0 replenishment on ask
        self.assertGreater(res.score, 0.0, "Heavy bid queue replenishment must generate positive (bullish) score")
        self.assertGreater(res.confidence, 0.0)
        self.assertGreater(res.metadata["l1_rep_bid"], res.metadata["l1_rep_ask"])

    # =========================================================================
    # Test 6: Asymmetric Ask Replenishment (Bearish Conviction)
    # =========================================================================
    def test_06_asymmetric_ask_replenishment_bearish(self):
        sig = QueueReplenishmentSignal()
        t0 = 1710000000000

        # Snapshot 1: Baseline
        book1 = self._create_mock_book(mid_px=25.00, spread=0.01, bid_sz=100.0, ask_sz=100.0, ts_ms=t0)
        trades = TradeManager(coin="HYPE")
        sig.compute(book1, trades, timestamp_ms=t0)

        # Inter-snapshot events:
        # Aggressive buying of 150.0 units hits the ask
        trades.process_raw_trades([
            {"coin": "HYPE", "side": "B", "px": "25.005", "sz": "150.0", "time": t0 + 50, "tid": 102}
        ])

        # Snapshot 2: Ask touch replenishes to 200.0; bid touch drops to 20.0
        book2 = self._create_mock_book(mid_px=25.00, spread=0.01, bid_sz=20.0, ask_sz=200.0, ts_ms=t0 + 100)
        res = sig.compute(book2, trades, timestamp_ms=t0 + 100)

        # R_a1 = (200 - 100) + 150 = 250.0 replenishment on ask
        # R_b1 = (20 - 100) + 0 = -80.0 replenishment on bid
        self.assertLess(res.score, 0.0, "Heavy ask queue replenishment must generate negative (bearish) score")
        self.assertGreater(res.confidence, 0.0)
        self.assertGreater(res.metadata["l1_rep_ask"], res.metadata["l1_rep_bid"])

    # =========================================================================
    # Test 7: Depletion Latency Persistence Tracker
    # =========================================================================
    def test_07_depletion_latency_persistence(self):
        sig = QueueReplenishmentSignal()
        t0 = 1710000000000
        trades = TradeManager(coin="HYPE")

        # Establish baseline with deep book
        book_base = self._create_mock_book(mid_px=25.00, bid_sz=500.0, ask_sz=500.0, ts_ms=t0)
        sig.compute(book_base, trades, timestamp_ms=t0)

        # Subsequent snapshots: ask depth is severely depleted (< 30% baseline) while bid is thick
        for step in range(1, 4):
            ts = t0 + step * 100
            book_depleted = self._create_mock_book(mid_px=25.00, bid_sz=500.0, ask_sz=50.0, ts_ms=ts)
            res = sig.compute(book_depleted, trades, timestamp_ms=ts)

        self.assertIn("latency_ask", res.metadata)
        self.assertIn("latency_bid", res.metadata)
        self.assertGreaterEqual(res.metadata["latency_ask"], res.metadata["latency_bid"])

    # =========================================================================
    # Test 8: Multi-Tier Cancellation Asymmetry
    # =========================================================================
    def test_08_cancellation_asymmetry(self):
        sig = QueueReplenishmentSignal()
        t0 = 1710000000000
        trades = TradeManager(coin="HYPE")

        # Snapshot 1: deep multi-tier book
        book1 = self._create_mock_book(mid_px=25.00, bid_sz=200.0, ask_sz=200.0, ts_ms=t0)
        sig.compute(book1, trades, timestamp_ms=t0)

        # Snapshot 2: Ask quotes pulled without trades (pure cancellation)
        # Bids remain resting intact
        book2 = self._create_mock_book(mid_px=25.00, bid_sz=200.0, ask_sz=50.0, ts_ms=t0 + 100)
        res = sig.compute(book2, trades, timestamp_ms=t0 + 100)

        self.assertIn("s_canc", res.metadata)
        self.assertGreater(res.metadata["s_canc"], 0.0, "Ask order cancellations must yield positive s_canc")

    # =========================================================================
    # Test 9: Dynamic Notional Scaling Invariance (BTC vs HYPE)
    # =========================================================================
    def test_09_dynamic_notional_scaling_invariance(self):
        """Verifies that identical USD notional liquidity shocks produce identical scores
        across assets with vastly different nominal prices (BTC at $85k vs HYPE at $85).
        """
        sig_btc = QueueReplenishmentSignal()
        sig_hype = QueueReplenishmentSignal()
        t0 = 1710000000000

        # BTC: P_mid = $85,000.0 -> notional_scale = 1.0
        # HYPE: P_mid = $85.00 -> notional_scale = 1000.0
        book_btc_1 = self._create_mock_book(coin="BTC", mid_px=85000.0, spread=1.0, bid_sz=1.0, ask_sz=1.0, ts_ms=t0)
        book_hype_1 = self._create_mock_book(coin="HYPE", mid_px=85.0, spread=0.01, bid_sz=1000.0, ask_sz=1000.0, ts_ms=t0)

        self.assertAlmostEqual(book_btc_1.notional_scale, 1.0, places=3)
        self.assertAlmostEqual(book_hype_1.notional_scale, 1000.0, places=3)

        trades_btc = TradeManager(coin="BTC")
        trades_hype = TradeManager(coin="HYPE")

        sig_btc.compute(book_btc_1, trades_btc, timestamp_ms=t0)
        sig_hype.compute(book_hype_1, trades_hype, timestamp_ms=t0)

        # Apply identical USD notional shock:
        # BTC receives 2.0 BTC replenishment ($170,000 USD)
        # HYPE receives 2,000.0 HYPE replenishment ($170,000 USD)
        t1 = t0 + 100
        book_btc_2 = self._create_mock_book(coin="BTC", mid_px=85000.0, spread=1.0, bid_sz=3.0, ask_sz=1.0, ts_ms=t1)
        book_hype_2 = self._create_mock_book(coin="HYPE", mid_px=85.0, spread=0.01, bid_sz=3000.0, ask_sz=1000.0, ts_ms=t1)

        res_btc = sig_btc.compute(book_btc_2, trades_btc, timestamp_ms=t1)
        res_hype = sig_hype.compute(book_hype_2, trades_hype, timestamp_ms=t1)

        # Scores should match closely due to dynamic notional scaling
        self.assertAlmostEqual(
            res_btc.score,
            res_hype.score,
            places=2,
            msg=f"Notional scaling invariant violated: BTC={res_btc.score:.4f}, HYPE={res_hype.score:.4f}",
        )

    # =========================================================================
    # Test 10: Extreme Stress & Overflow Robustness (Fuzzing)
    # =========================================================================
    def test_10_extreme_stress_and_fuzzing(self):
        sig = QueueReplenishmentSignal()
        t0 = 1710000000000

        # Massive volumes ($10^9), extreme order sizes
        book = self._create_mock_book(mid_px=25.00, bid_sz=1e8, ask_sz=1e8, ts_ms=t0)
        trades = TradeManager(coin="HYPE")
        trades.process_raw_trades([
            {"coin": "HYPE", "side": "B", "px": "25.005", "sz": "1000000000.0", "time": t0, "tid": 999}
        ])

        res = sig.compute(book, trades, timestamp_ms=t0)
        self.assertFalse(math.isnan(res.score), "Score must not be NaN")
        self.assertFalse(math.isinf(res.score), "Score must not be Inf")
        self.assertGreaterEqual(res.score, -1.0)
        self.assertLessEqual(res.score, 1.0)
        self.assertGreaterEqual(res.confidence, 0.0)
        self.assertLessEqual(res.confidence, 1.0)

    # =========================================================================
    # Test 11: High-Speed Performance Benchmark (< 0.1ms per compute call)
    # =========================================================================
    def test_11_performance_benchmark_sub_100us(self):
        sig = QueueReplenishmentSignal()
        book = self._create_mock_book(mid_px=25.00, spread=0.01)
        trades = TradeManager(coin="HYPE")
        trades.process_raw_trades([
            {"coin": "HYPE", "side": "B", "px": "25.005", "sz": "50.0", "time": 1710000000000, "tid": 1}
        ])

        # Warmup
        for i in range(100):
            sig.compute(book, trades, timestamp_ms=1710000000000 + i)

        # Benchmark 10,000 iterations
        n_iters = 10_000
        start = time.perf_counter()
        for i in range(n_iters):
            sig.compute(book, trades, timestamp_ms=1710000000100 + i)
        elapsed = time.perf_counter() - start

        avg_latency_s = elapsed / n_iters
        avg_latency_us = avg_latency_s * 1_000_000

        print(f"\n[BENCHMARK] QueueReplenishment compute latency: {avg_latency_us:.2f} us per call ({n_iters} iterations)")
        self.assertLess(
            avg_latency_s,
            0.0001,  # 0.1 ms = 100 us
            f"Latency exceeded 0.1ms threshold: {avg_latency_us:.2f} us",
        )

    # =========================================================================
    # Test 12: SignalResult Schema & Metadata Validation
    # =========================================================================
    def test_12_schema_and_metadata_conformity(self):
        book = self._create_mock_book(mid_px=25.00, spread=0.01)
        trades = TradeManager(coin="HYPE")
        res = self.signal.compute(book, trades, timestamp_ms=1710000000500)

        self.assertEqual(res.name, "QueueReplenishment")
        self.assertIsInstance(res.score, float)
        self.assertIsInstance(res.raw_value, float)
        self.assertIsInstance(res.confidence, float)
        self.assertIsInstance(res.timestamp_ms, int)
        self.assertIsInstance(res.metadata, dict)

        required_keys = [
            "l1_rep_bid",
            "l1_rep_ask",
            "l3_rep_bid",
            "l3_rep_ask",
            "latency_bid",
            "latency_ask",
            "s_canc",
            "cvd_fast",
            "trend_bps",
        ]
        for k in required_keys:
            self.assertIn(k, res.metadata, f"Missing required metadata key: {k}")

    # =========================================================================
    # Test 13: CompositeAlpha Integration & Attribute Parity
    # =========================================================================
    def test_13_composite_alpha_integration(self):
        alpha = CompositeAlphaSignal()
        self.assertTrue(hasattr(alpha, "signal_queue_replenishment"), "CompositeAlpha missing signal_queue_replenishment attribute")
        self.assertIsNotNone(alpha.signal_queue_replenishment)
        self.assertTrue(alpha.is_enabled("QueueReplenishment"))

        book = self._create_mock_book(mid_px=25.00, spread=0.01)
        trades = TradeManager(coin="HYPE")
        res = alpha.compute(book, trades, timestamp_ms=1710000000600)

        self.assertIn("sub_signals", res.metadata)
        sub_sigs = res.metadata["sub_signals"]
        self.assertIn("QueueReplenishment", sub_sigs)
        self.assertIsInstance(sub_sigs["QueueReplenishment"], SignalResult)


if __name__ == "__main__":
    unittest.main(verbosity=2)
