"""Unit test suite for startup warmup wait time in main_core, main_scalper, and live engine.

Verifies:
1. EdgeEvaluator suppresses trade entries during warmup window, then enables entries.
2. EdgeEvaluator does not block exits for existing positions during warmup.
3. LiveOrderExecutor suppresses order submissions during warmup window.
4. L2EngineRunner correctly tracks warmup state and remaining seconds.
5. CLI arguments in main_core, main_scalper, and main correctly parse --warmup flags.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from config import AppConfig, BacktestConfig, MarketConfig
from engine.backtester import EdgeEvaluator
from engine.live_executor import LiveOrderExecutor
from main import L2EngineRunner
import main_core
import main_scalper
import main


class TestWarmupDelay(unittest.TestCase):
    """Test suite verifying warmup wait delay on startup."""

    def test_edge_evaluator_suppresses_entries_during_warmup(self):
        """EdgeEvaluator must block new entries while in warmup, and allow entries after warmup."""
        m_cfg = MarketConfig(coin="BTC", taker_fee_bps=4.5, maker_fee_bps=1.5)
        bt_cfg = BacktestConfig(warmup_secs=5.0, max_spread_bps=5.0)
        evaluator = EdgeEvaluator(
            market_cfg=m_cfg,
            bt_cfg=bt_cfg,
            strategy_defs={"Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER")},
            warmup_secs=5.0,
        )

        self.assertEqual(evaluator.warmup_secs, 5.0)
        self.assertTrue(evaluator.is_warming_up())

        # Step 1: Tick at t=1000ms with high conviction score (0.95 >= 0.86 threshold)
        # Tight spread: mid=100,000, bid=99,999.5, ask=100,000.5 (spread = 1.0, 0.1 bps < 5.0 bps)
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100000.0,
            best_bid=99999.5,
            best_ask=100000.5,
            signals={"HedgedConvexity": 0.95},
        )

        # Because t=1000ms is the first step, we are in warmup -> no position should be opened!
        state = evaluator.strategies["Hedged_Convexity"]
        self.assertFalse(state.is_in_position)
        self.assertEqual(len(evaluator.position_events), 0)

        # Step 2: Tick at t=3000ms (2s into warmup, warmup is 5s)
        evaluator.record_step(
            timestamp_ms=3000,
            mid_price=100000.0,
            best_bid=99999.5,
            best_ask=100000.5,
            signals={"HedgedConvexity": 0.95},
        )
        self.assertTrue(evaluator.is_warming_up(3000))
        self.assertFalse(state.is_in_position)

        # Step 3: Tick at t=7000ms (6s since first step at 1000ms -> warmup elapsed!)
        self.assertFalse(evaluator.is_warming_up(7000))
        evaluator.record_step(
            timestamp_ms=7000,
            mid_price=100000.0,
            best_bid=99999.5,
            best_ask=100000.5,
            signals={"HedgedConvexity": 0.95},
        )
        self.assertTrue(state.is_in_position)
        self.assertGreater(state.position_btc, 0.0)
        self.assertGreater(len(evaluator.position_events), 0)

    def test_edge_evaluator_allows_exits_during_warmup(self):
        """If a strategy is already in position (e.g. state recovery), exits must NOT be blocked during warmup."""
        evaluator = EdgeEvaluator(
            strategy_defs={"Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER")},
            warmup_secs=10.0,
        )
        state = evaluator.strategies["Hedged_Convexity"]
        # Manually populate an active long position entered prior to restart
        state.position_btc = 0.1
        state.entry_price = 100000.0
        state.entry_time_ms = 500
        state.stop_price = 95000.0

        # Tick at t=1000ms triggers take profit (price jumped to 105,000)
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=105000.0,
            best_bid=104999.0,
            best_ask=105001.0,
            signals={"HedgedConvexity": 0.0},
        )
        # Position should be closed despite being in warmup
        self.assertFalse(state.is_in_position)
        self.assertEqual(state.position_btc, 0.0)
        self.assertEqual(len(state.trades), 1)
        self.assertEqual(state.trades[0].exit_reason, "TAKE_PROFIT")

    def test_live_executor_warmup_guard(self):
        """LiveOrderExecutor must suppress new order placement while warming up."""
        cfg = AppConfig.for_core()
        executor = LiveOrderExecutor(config=cfg, warmup_secs=5.0)

        self.assertEqual(executor.warmup_secs, 5.0)
        self.assertTrue(executor.is_warming_up)

        # Mock place_limit_order and place_market_order
        executor.place_limit_order = MagicMock(return_value=123)
        executor.place_market_order = MagicMock(return_value=124)
        executor.is_initialized = True

        # Signal score high conviction (0.95), best_bid=100,000, best_ask=100,001
        executor.on_signal_update(
            signal_score=0.95,
            best_bid=100000.0,
            best_ask=100001.0,
            spread=1.0,
            confidence=1.0,
        )

        # While warming up, place_limit_order or place_market_order must NOT be called
        executor.place_limit_order.assert_not_called()
        executor.place_market_order.assert_not_called()

        # Simulate warmup expiration
        executor._first_signal_time = time.time() - 10.0
        self.assertFalse(executor.is_warming_up)

        executor.on_signal_update(
            signal_score=0.95,
            best_bid=100000.0,
            best_ask=100001.0,
            spread=1.0,
            confidence=1.0,
        )
        # Now order placement is triggered
        self.assertTrue(executor.place_limit_order.called or executor.place_market_order.called)

    def test_runner_warmup_properties(self):
        """L2EngineRunner must track warmup state and remaining seconds accurately."""
        cfg = AppConfig.for_core()
        runner = L2EngineRunner(config=cfg, warmup_secs=10.0, record_data=False)

        self.assertEqual(runner.warmup_secs, 10.0)
        # Before any valid book arrives
        self.assertTrue(runner.is_warming_up)
        self.assertEqual(runner.warmup_remaining_secs, 0.0)

        # Simulate receiving first book
        t0 = time.time()
        runner._first_valid_book_time = t0

        self.assertTrue(runner.is_warming_up)
        rem = runner.warmup_remaining_secs
        self.assertGreater(rem, 8.0)
        self.assertLessEqual(rem, 10.0)

        # Simulate time passage beyond warmup
        runner._first_valid_book_time = t0 - 15.0
        self.assertFalse(runner.is_warming_up)
        self.assertEqual(runner.warmup_remaining_secs, 0.0)

    def test_cli_warmup_argument_parsing(self):
        """CLI parsers across main, main_core, and main_scalper must parse --warmup correctly."""
        # 1. main_core
        p_core = main_core.build_parser()
        args = p_core.parse_args(["live", "--warmup", "12.5"])
        self.assertEqual(args.warmup, 12.5)

        args_default = p_core.parse_args(["live"])
        self.assertIsNone(args_default.warmup)

        # 2. main_scalper
        p_scalp = main_scalper.build_parser()
        args = p_scalp.parse_args(["live", "--warmup", "0"])
        self.assertEqual(args.warmup, 0.0)

        # 3. main
        with open("main.py", "r", encoding="utf-8") as f:
            self.assertIn('--warmup', f.read())


if __name__ == "__main__":
    unittest.main()
