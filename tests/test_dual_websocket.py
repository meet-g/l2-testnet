"""Unit and integration tests for Dual-WebSocket Architecture.

Validates that:
1. CLI flags (--fast-ws, --no-fast-ws) configure the dual-stream behavior in both main.py and main_scalper.py.
2. L2EngineRunner auto-enables fast sidecar stream in scalper mode and disables in core execution mode.
3. The normal WebSocket stream connects with fast=False, updates full depth (20 levels), and records clean data to L2DataRecorder.
4. The sidecar fast WebSocket stream connects with fast=True, updates top touch levels (5 levels) while retaining deep levels,
   evaluates alpha and resting orders immediately, and strictly NEVER records to L2DataRecorder (preventing data skew).
5. Lifecycle cancellation properly cancels fast_ws_task upon runner shutdown.
"""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from config import AppConfig, MarketConfig
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


if __name__ == "__main__":
    unittest.main()
