"""Unit and integration tests for Dual-WebSocket Architecture.

Validates that:
1. CLI flags (--fast-ws, --no-fast-ws) configure the dual-stream behavior in both main.py and main_scalper.py.
2. L2EngineRunner auto-enables fast sidecar stream in scalper mode and disables in core execution mode.
3. The normal WebSocket stream connects with fast=False, updates full depth (20 levels), and records clean data to L2DataRecorder.
4. The sidecar fast WebSocket stream connects with fast=True, updates top touch levels (5 levels) while retaining deep levels,
   evaluates alpha and resting orders immediately, and strictly NEVER records to L2DataRecorder (preventing data skew).
5. Lifecycle cancellation properly cancels fast_ws_task upon runner shutdown.
6. Order capture comparison in a set interval: rigorously tests whether the fast WebSocket captures
   orders (transient orders, price changes, queue transitions) that the normal WebSocket misses,
   and whether the normal WebSocket captures deep resting orders (levels 6-20) that the fast WebSocket misses.
"""

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import AppConfig, MarketConfig
from core.dual_ws_comparator import DualWebSocketOrderComparator, OrderState
from core.orderbook import OrderBook
from main import L2EngineRunner, build_parser as build_main_parser
from main_scalper import build_parser as build_scalper_parser


class TestDualWebSocketCLI(unittest.TestCase):
    """Verifies CLI argument parsing for --fast-ws and --no-fast-ws."""

    def test_main_parser_default(self):
        parser = build_main_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.enable_fast_ws)

    def test_main_parser_fast_ws_flag(self):
        parser = build_main_parser()
        args = parser.parse_args(["--fast-ws"])
        self.assertTrue(args.enable_fast_ws)

    def test_main_parser_no_fast_ws_flag(self):
        parser = build_main_parser()
        args = parser.parse_args(["--no-fast-ws"])
        self.assertFalse(args.enable_fast_ws)

    def test_scalper_parser_default(self):
        parser = build_scalper_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.enable_fast_ws)

    def test_scalper_parser_fast_ws_flag(self):
        parser = build_scalper_parser()
        args = parser.parse_args(["--fast-ws"])
        self.assertTrue(args.enable_fast_ws)

    def test_scalper_parser_no_fast_ws_flag(self):
        parser = build_scalper_parser()
        args = parser.parse_args(["--no-fast-ws"])
        self.assertFalse(args.enable_fast_ws)


class TestDualWebSocketRunnerInit(unittest.TestCase):
    """Verifies L2EngineRunner initialization logic for enable_fast_ws."""

    def test_explicit_enable_fast_ws_true(self):
        cfg = AppConfig()
        runner = L2EngineRunner(config=cfg, record_data=False, enable_fast_ws=True)
        self.assertTrue(runner.enable_fast_ws)

    def test_explicit_enable_fast_ws_false(self):
        cfg = AppConfig()
        runner = L2EngineRunner(config=cfg, record_data=False, enable_fast_ws=False)
        self.assertFalse(runner.enable_fast_ws)

    def test_auto_enable_for_scalper_config(self):
        cfg = AppConfig.for_scalper()
        runner = L2EngineRunner(config=cfg, record_data=False)
        self.assertTrue(runner.enable_fast_ws)

    def test_auto_disable_for_core_config(self):
        cfg = AppConfig.for_core()
        runner = L2EngineRunner(config=cfg, record_data=False)
        self.assertFalse(runner.enable_fast_ws)


class TestOrderBookDepthRetention(unittest.TestCase):
    """Verifies that 5-level fast updates do not drop the deeper 15 levels from normal 20-level snapshots."""

    def setUp(self):
        self.book = OrderBook(coin="xyz:SKHX")

    def test_fast_update_preserves_deeper_levels(self):
        # 1. Provide initial full 20-level normal snapshot
        normal_bids = [{"px": str(100.0 - i * 0.1), "sz": "1.0", "n": 1} for i in range(20)]
        normal_asks = [{"px": str(100.1 + i * 0.1), "sz": "1.0", "n": 1} for i in range(20)]
        normal_data = {
            "coin": "xyz:SKHX",
            "time": 1000,
            "levels": [normal_bids, normal_asks],
        }

        self.book.update_from_raw(normal_data, is_fast=False)
        self.assertEqual(len(self.book.bids), 20)
        self.assertEqual(len(self.book.asks), 20)
        self.assertAlmostEqual(self.book.best_bid, 100.0)
        self.assertAlmostEqual(self.book.best_ask, 100.1)
        self.assertAlmostEqual(self.book.bids[-1].px, 100.0 - 19 * 0.1)
        self.assertAlmostEqual(self.book.asks[-1].px, 100.1 + 19 * 0.1)

        # 2. Provide 5-level fast snapshot with shifted top-of-book
        fast_bids = [{"px": str(100.02 - i * 0.1), "sz": "2.5", "n": 2} for i in range(5)]
        fast_asks = [{"px": str(100.08 + i * 0.1), "sz": "3.0", "n": 3} for i in range(5)]
        fast_data = {
            "coin": "xyz:SKHX",
            "time": 1050,
            "levels": [fast_bids, fast_asks],
        }

        self.book.update_from_raw(fast_data, is_fast=True)

        # Top levels must match fast data
        self.assertAlmostEqual(self.book.best_bid, 100.02)
        self.assertAlmostEqual(self.book.best_ask, 100.08)
        self.assertAlmostEqual(self.book.bids[0].sz, 2.5)
        self.assertAlmostEqual(self.book.asks[0].sz, 3.0)

        # Total depth should retain deeper levels
        self.assertGreater(len(self.book.bids), 5)
        self.assertGreater(len(self.book.asks), 5)
        # Deepest bid and ask should still be intact from normal snapshot
        self.assertAlmostEqual(self.book.bids[-1].px, 100.0 - 19 * 0.1)
        self.assertAlmostEqual(self.book.asks[-1].px, 100.1 + 19 * 0.1)

    def test_normal_update_replaces_entire_depth(self):
        # Initial 20-level snapshot
        bids_1 = [{"px": str(100.0 - i * 0.1), "sz": "1.0", "n": 1} for i in range(20)]
        asks_1 = [{"px": str(100.1 + i * 0.1), "sz": "1.0", "n": 1} for i in range(20)]
        self.book.update_from_raw({"coin": "xyz:SKHX", "time": 1000, "levels": [bids_1, asks_1]}, is_fast=False)

        # Subsequent 20-level normal snapshot at totally different price
        bids_2 = [{"px": str(90.0 - i * 0.1), "sz": "5.0", "n": 1} for i in range(20)]
        asks_2 = [{"px": str(90.1 + i * 0.1), "sz": "5.0", "n": 1} for i in range(20)]
        self.book.update_from_raw({"coin": "xyz:SKHX", "time": 2000, "levels": [bids_2, asks_2]}, is_fast=False)

        self.assertEqual(len(self.book.bids), 20)
        self.assertEqual(len(self.book.asks), 20)
        self.assertAlmostEqual(self.book.best_bid, 90.0)
        self.assertAlmostEqual(self.book.best_ask, 90.1)

    def test_signal_computation_replay_depth_sensitivity(self):
        """Verifies that signals (QDAP, WOBI) execute cleanly without errors on both 20-level and 5-level books,
        and demonstrates that 20-level books activate deep structural alpha (levels 6-20)."""
        from signals.qdap import QDAPSignal
        from signals.wobi import WOBISignal
        from core.trade_stream import TradeManager

        trades = TradeManager(coin="xyz:SKHX")
        qdap = QDAPSignal()
        wobi = WOBISignal()

        # 20-level book snapshot with asymmetric deep liquidity
        bids_20 = [{"px": str(100.0 - i * 0.1), "sz": "1.0" if i < 5 else "10.0", "n": 2} for i in range(20)]
        asks_20 = [{"px": str(100.1 + i * 0.1), "sz": "1.0", "n": 2} for i in range(20)]
        self.book.update_from_raw({"coin": "xyz:SKHX", "time": 1000, "levels": [bids_20, asks_20]}, is_fast=False)

        res_qdap_20 = qdap.compute(self.book, trades, 1000)
        res_wobi_20 = wobi.compute(self.book, trades, 1000)

        # Truncated 5-level book snapshot (what fast: True delivers)
        bids_5 = bids_20[:5]
        asks_5 = asks_20[:5]
        book_5 = OrderBook(coin="xyz:SKHX")
        book_5.update_from_raw({"coin": "xyz:SKHX", "time": 1000, "levels": [bids_5, asks_5]}, is_fast=False)

        res_qdap_5 = qdap.compute(book_5, trades, 1000)
        res_wobi_5 = wobi.compute(book_5, trades, 1000)

        # Both compute without crashing
        self.assertIsNotNone(res_qdap_20.score)
        self.assertIsNotNone(res_qdap_5.score)

        # In 20-level book, deep buy walls (levels 5-20) push QDAP score significantly higher
        self.assertGreater(res_qdap_20.score, res_qdap_5.score)
        # WOBI with 10-level window captures more depth than 5-level window
        self.assertNotEqual(res_wobi_20.score, res_wobi_5.score)


class TestDualWebSocketDataRecordingIsolation(unittest.IsolatedAsyncioTestCase):
    """Verifies that normal stream records full data while fast sidecar stream never writes to recorder."""

    async def asyncSetUp(self):
        self.cfg = AppConfig.for_scalper()
        self.runner = L2EngineRunner(config=self.cfg, record_data=False, enable_fast_ws=True)
        self.mock_recorder = MagicMock()
        self.runner.recorder = self.mock_recorder

    async def asyncTearDown(self):
        self.runner.close()

    async def test_normal_message_records_and_updates_book(self):
        normal_msg = json.dumps({
            "channel": "l2Book",
            "data": {
                "coin": self.cfg.market.coin,
                "time": 1234567890,
                "levels": [
                    [{"px": "100.0", "sz": "1.0", "n": 1}],
                    [{"px": "100.1", "sz": "1.0", "n": 1}],
                ],
            },
        })

        await self.runner._handle_message(normal_msg)

        # Must record event to disk
        self.mock_recorder.record_event.assert_called_once()
        args = self.mock_recorder.record_event.call_args[0]
        self.assertEqual(args[0], "l2Book")
        self.assertEqual(args[1]["time"], 1234567890)

        # Book must be updated with best bid / ask
        self.assertAlmostEqual(self.runner.book.best_bid, 100.0)
        self.assertAlmostEqual(self.runner.book.best_ask, 100.1)

    async def test_fast_message_does_not_record_but_updates_book_and_triggers_eval(self):
        fast_msg = json.dumps({
            "channel": "l2Book",
            "data": {
                "coin": self.cfg.market.coin,
                "time": 1234567999,
                "levels": [
                    [{"px": "100.05", "sz": "2.0", "n": 1}],
                    [{"px": "100.09", "sz": "2.0", "n": 1}],
                ],
            },
        })

        with patch.object(self.runner, "_evaluate_signals") as mock_eval:
            await self.runner._handle_fast_l2_message(fast_msg)

            # Strict requirement: self.recorder MUST NOT be called from fast message handler
            self.mock_recorder.record_event.assert_not_called()

            # Book touch must be updated to new fast prices
            self.assertAlmostEqual(self.runner.book.best_bid, 100.05)
            self.assertAlmostEqual(self.runner.book.best_ask, 100.09)

            # Signal evaluation must be triggered immediately
            mock_eval.assert_called_once()


class TestDualWebSocketLifecycle(unittest.IsolatedAsyncioTestCase):
    """Verifies fast_ws_task task cancellation on runner close."""

    async def test_close_cancels_fast_ws_task(self):
        runner = L2EngineRunner(config=AppConfig(), record_data=False, enable_fast_ws=True)

        async def dummy_stream():
            try:
                while True:
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                raise

        task = asyncio.create_task(dummy_stream())
        runner.fast_ws_task = task
        self.assertFalse(task.done())

        runner.close()
        # Allow the event loop a tick to process cancellation
        try:
            await asyncio.wait_for(task, timeout=0.1)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        self.assertTrue(task.cancelled())


class TestDualWebSocketOrderCaptureComparison(unittest.TestCase):
    """Compares order capture and visibility between Fast and Normal WebSocket feeds in set intervals."""

    def setUp(self):
        self.comparator = DualWebSocketOrderComparator(coin="BTC")

    def test_fast_captures_transient_orders_missed_by_normal(self):
        """Specifically verifies that orders appearing and disappearing between normal snapshots
        are captured by the fast WebSocket and completely missed by the normal WebSocket."""
        # 1. Normal snapshot at t = 0.0s (bids around 59000, asks around 59001)
        normal_t0 = {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": 1000,
                "levels": [
                    [{"px": "59000.0", "sz": "1.0", "n": 1}],
                    [{"px": "59001.0", "sz": "1.0", "n": 1}],
                ],
            },
        }
        self.comparator.process_message("normal", normal_t0, recv_time_s=0.0)
        self.comparator.process_message("fast", normal_t0, recv_time_s=0.0)

        # 2. Fast stream receives a flash resting bid at 59000.5 at t = 0.2s
        fast_t1 = {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": 1200,
                "levels": [
                    [{"px": "59000.5", "sz": "2.5", "n": 2}, {"px": "59000.0", "sz": "1.0", "n": 1}],
                    [{"px": "59001.0", "sz": "1.0", "n": 1}],
                ],
            },
        }
        self.comparator.process_message("fast", fast_t1, recv_time_s=0.2)

        # 3. Flash bid is amended to size 3.0, n=3 at t = 0.4s
        fast_t2 = {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": 1400,
                "levels": [
                    [{"px": "59000.5", "sz": "3.0", "n": 3}, {"px": "59000.0", "sz": "1.0", "n": 1}],
                    [{"px": "59001.0", "sz": "1.0", "n": 1}],
                ],
            },
        }
        self.comparator.process_message("fast", fast_t2, recv_time_s=0.4)

        # 4. Flash bid is filled/canceled before normal snapshot fires at t = 0.8s
        fast_t3 = {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": 1800,
                "levels": [
                    [{"px": "59000.0", "sz": "1.0", "n": 1}],
                    [{"px": "59001.0", "sz": "1.0", "n": 1}],
                ],
            },
        }
        self.comparator.process_message("fast", fast_t3, recv_time_s=0.8)

        # 5. Normal stream sends its periodic snapshot at t = 1.0s
        normal_t1 = {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": 2000,
                "levels": [
                    [{"px": "59000.0", "sz": "1.0", "n": 1}],
                    [{"px": "59001.0", "sz": "1.0", "n": 1}],
                ],
            },
        }
        self.comparator.process_message("normal", normal_t1, recv_time_s=1.0)

        # Generate report over 1.0s interval
        report = self.comparator.generate_report(interval_secs=1.0)

        # Assertions
        # 1. Fast captured the transient orders at 59000.5
        flash_order_1 = OrderState(side="bid", px=59000.5, sz=2.5, n=2)
        flash_order_2 = OrderState(side="bid", px=59000.5, sz=3.0, n=3)
        self.assertIn(flash_order_1, report.fast_only_orders)
        self.assertIn(flash_order_2, report.fast_only_orders)

        # 2. Normal NEVER saw price 59000.5 or either flash order
        self.assertIn(("bid", 59000.5), report.fast_only_prices)
        self.assertNotIn(flash_order_1, report.normal_only_orders)
        self.assertNotIn(flash_order_1, report.common_orders)

        # 3. Exactly proves fast stream captured unshared orders
        self.assertGreater(len(report.fast_only_orders), 0)
        self.assertEqual(len(report.fast_only_prices), 1)

    def test_normal_captures_deep_book_liquidity_missed_by_fast(self):
        """Verifies that the normal stream captures resting orders in the deep book (levels 6-20)
        that the fast stream (which only streams top 5) completely misses."""
        bids_20 = [{"px": str(100.0 - i * 0.1), "sz": "1.0", "n": 1} for i in range(20)]
        asks_20 = [{"px": str(100.1 + i * 0.1), "sz": "1.0", "n": 1} for i in range(20)]

        normal_msg = {
            "channel": "l2Book",
            "data": {"coin": "BTC", "time": 1000, "levels": [bids_20, asks_20]},
        }
        # Fast only delivers top 5 levels
        fast_msg = {
            "channel": "l2Book",
            "data": {"coin": "BTC", "time": 1000, "levels": [bids_20[:5], asks_20[:5]]},
        }

        self.comparator.process_message("normal", normal_msg, recv_time_s=1.0)
        self.comparator.process_message("fast", fast_msg, recv_time_s=1.0)

        report = self.comparator.generate_report(interval_secs=1.0)

        # Normal has 40 total orders (20 bids + 20 asks)
        # Fast has 10 total orders (5 bids + 5 asks)
        self.assertEqual(report.unique_orders_normal, 40)
        self.assertEqual(report.unique_orders_fast, 10)
        self.assertEqual(report.common_orders_count, 10)

        # Fast only misses the 30 deeper levels
        self.assertEqual(len(report.normal_only_orders), 30)
        self.assertEqual(len(report.normal_only_deep_orders), 30)
        self.assertEqual(len(report.fast_only_orders), 0)

    def test_queue_state_transitions_captured_by_fast_at_common_price(self):
        """Verifies that high-frequency queue replenishment and size transitions at the top of the book
        are captured by Fast while Normal only observes sampled start/end endpoints."""
        # Start state at t = 0.0s
        msg_t0 = {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": 1000,
                "levels": [[{"px": "100.0", "sz": "1.0", "n": 1}], [{"px": "100.1", "sz": "1.0", "n": 1}]],
            },
        }
        self.comparator.process_message("normal", msg_t0, recv_time_s=0.0)
        self.comparator.process_message("fast", msg_t0, recv_time_s=0.0)

        # Intermediate updates captured ONLY by Fast at t = 0.1s, 0.2s, 0.3s
        intermediate_sizes = [(2.5, 2), (5.0, 4), (1.5, 2)]
        for i, (sz, n) in enumerate(intermediate_sizes):
            fast_msg = {
                "channel": "l2Book",
                "data": {
                    "coin": "BTC",
                    "time": 1000 + (i + 1) * 100,
                    "levels": [[{"px": "100.0", "sz": str(sz), "n": n}], [{"px": "100.1", "sz": "1.0", "n": 1}]],
                },
            }
            self.comparator.process_message("fast", fast_msg, recv_time_s=0.1 * (i + 1))

        # End state at t = 1.0s seen by both
        msg_t1 = {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": 2000,
                "levels": [[{"px": "100.0", "sz": "3.0", "n": 3}], [{"px": "100.1", "sz": "1.0", "n": 1}]],
            },
        }
        self.comparator.process_message("normal", msg_t1, recv_time_s=1.0)
        self.comparator.process_message("fast", msg_t1, recv_time_s=1.0)

        report = self.comparator.generate_report(interval_secs=1.0)

        # Fast captured the 3 intermediate queue states at shared price 100.0
        self.assertEqual(len(report.fast_only_intermediate_updates), 3)
        for sz, n in intermediate_sizes:
            self.assertIn(OrderState(side="bid", px=100.0, sz=sz, n=n), report.fast_only_intermediate_updates)

    def test_lead_time_latency_advantage(self):
        """Verifies that when an order arrives, Fast detects it earlier than Normal."""
        msg = {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": 1000,
                "levels": [[{"px": "100.0", "sz": "1.0", "n": 1}], [{"px": "100.1", "sz": "1.0", "n": 1}]],
            },
        }
        # Fast receives it at t = 1.000s
        self.comparator.process_message("fast", msg, recv_time_s=1.000)
        # Normal receives it at t = 1.450s (450ms wire/throttle latency)
        self.comparator.process_message("normal", msg, recv_time_s=1.450)

        report = self.comparator.generate_report(interval_secs=1.0)
        self.assertAlmostEqual(report.avg_lead_time_ms, 450.0, places=1)
        self.assertAlmostEqual(report.max_lead_time_ms, 450.0, places=1)

    def test_live_interval_comparison_if_enabled(self):
        """Optional live test against Hyperliquid WebSocket if RUN_LIVE_WS_TEST=1 is configured."""
        if os.environ.get("RUN_LIVE_WS_TEST") != "1":
            self.skipTest("Live WebSocket test skipped (set RUN_LIVE_WS_TEST=1 to enable).")

        async def _run():
            comp = DualWebSocketOrderComparator(coin="BTC")
            rep = await comp.run_live(interval_secs=3.0)
            self.assertGreater(rep.fast_msg_count, 0)
            self.assertGreater(rep.normal_msg_count, 0)
            # Under live conditions, fast captures unshared orders
            self.assertGreater(len(rep.fast_only_orders), 0)

        asyncio.run(_run())


if __name__ == "__main__":
    import sys
    if "--live" in sys.argv:
        sys.argv.remove("--live")
        os.environ["RUN_LIVE_WS_TEST"] = "1"
    unittest.main()
