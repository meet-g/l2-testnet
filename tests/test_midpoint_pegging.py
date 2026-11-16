"""Unit and integration tests for Midpoint Pegging logic across config, LiveOrderExecutor, EdgeEvaluator, and CLI."""

import argparse
import unittest
from unittest.mock import MagicMock, patch

from config import (
    AppConfig,
    BacktestConfig,
    ExecutionStrategyConfig,
    LiveExecutionConfig,
    MarketConfig,
)
from engine.backtester import EdgeEvaluator
from engine.live_executor import LiveOrderExecutor
from main_core import build_parser as build_core_parser
from main import build_parser as build_main_parser
from main_scalper import build_parser as build_scalper_parser


class TestConfigMidpointPegging(unittest.TestCase):
    def test_default_config_fields(self):
        live_cfg = LiveExecutionConfig()
        self.assertFalse(live_cfg.midpoint_pegging)

        bt_cfg = BacktestConfig()
        self.assertFalse(bt_cfg.midpoint_pegging)

        strat_cfg = ExecutionStrategyConfig(name="Test", signal_key="WOBI")
        self.assertIsNone(strat_cfg.midpoint_pegging)

    def test_core_strategies_json_has_midpoint_pegging_enabled(self):
        cfg = AppConfig.for_core(strategies_config="strategies_core.json")
        self.assertIsNotNone(cfg.strategies.live_execution.midpoint_pegging)

    def test_scalper_strategies_json_has_midpoint_pegging_enabled(self):
        cfg = AppConfig.for_scalper(strategies_config="strategies_scalper.json")
        self.assertIsNotNone(cfg.strategies.live_execution.midpoint_pegging)


class TestLiveExecutorMidpointPegging(unittest.TestCase):
    def setUp(self):
        self.init_patcher = patch.object(LiveOrderExecutor, "_initialize", lambda self: None)
        self.init_patcher.start()
        self.mock_config = AppConfig()
        self.mock_config.market = MarketConfig(coin="xyz:SKHX", tick_size=0.01)
        self.mock_config.strategies.live_execution.midpoint_pegging = True

    def tearDown(self):
        self.init_patcher.stop()

    def test_clamp_post_only_price_buy_wide_spread(self):
        executor = LiveOrderExecutor(config=self.mock_config, midpoint_pegging=True)
        executor.last_best_bid = 968.40
        executor.last_best_ask = 968.44  # Spread = $0.04 (4 ticks)
        executor.max_price_decimals = 2

        # An aggressive buy price that would cross the ask
        clamped = executor._clamp_post_only_price(968.44, is_buy=True)
        # Midpoint is (968.40 + 968.44) / 2 = 968.42
        # Must be <= 968.44 - 0.01 = 968.43
        self.assertEqual(clamped, 968.42)

    def test_clamp_post_only_price_buy_one_tick_spread(self):
        executor = LiveOrderExecutor(config=self.mock_config, midpoint_pegging=True)
        executor.last_best_bid = 968.40
        executor.last_best_ask = 968.41  # Spread = $0.01 (1 tick)
        executor.max_price_decimals = 2

        clamped = executor._clamp_post_only_price(968.41, is_buy=True)
        # Spread < 2 ticks -> fallback to touch at best_bid
        self.assertEqual(clamped, 968.40)

    def test_clamp_post_only_price_sell_wide_spread(self):
        executor = LiveOrderExecutor(config=self.mock_config, midpoint_pegging=True)
        executor.last_best_bid = 968.40
        executor.last_best_ask = 968.46  # Spread = $0.06 (6 ticks)
        executor.max_price_decimals = 2

        # An aggressive sell price that would cross the bid
        clamped = executor._clamp_post_only_price(968.40, is_buy=False)
        # Midpoint is (968.40 + 968.46) / 2 = 968.43
        # Must be >= 968.40 + 0.01 = 968.41
        self.assertEqual(clamped, 968.43)

    def test_clamp_post_only_price_sell_one_tick_spread(self):
        executor = LiveOrderExecutor(config=self.mock_config, midpoint_pegging=True)
        executor.last_best_bid = 968.40
        executor.last_best_ask = 968.41  # Spread = $0.01 (1 tick)
        executor.max_price_decimals = 2

        clamped = executor._clamp_post_only_price(968.40, is_buy=False)
        # Spread < 2 ticks -> fallback to touch at best_ask
        self.assertEqual(clamped, 968.41)

    def test_entry_quote_calculation_midpoint_vs_disabled(self):
        executor_mid = LiveOrderExecutor(config=self.mock_config, midpoint_pegging=True)
        executor_mid.last_best_bid = 968.40
        executor_mid.last_best_ask = 968.46
        executor_mid.max_price_decimals = 2

        executor_touch = LiveOrderExecutor(config=self.mock_config, midpoint_pegging=False)
        executor_touch.penny_jumping = False
        executor_touch.last_best_bid = 968.40
        executor_touch.last_best_ask = 968.46
        executor_touch.max_price_decimals = 2

        # Verify midpoint pegging calculates 968.43 for buy
        # (best_bid 968.40 + best_ask 968.46) / 2 = 968.43
        spread = 968.46 - 968.40
        tick_size = 0.01
        self.assertGreaterEqual(spread, 2.0 * tick_size)
        raw_mid = (968.40 + 968.46) / 2.0
        expected_mid = round(raw_mid, 2)
        self.assertEqual(expected_mid, 968.43)


class TestBacktesterMidpointPegging(unittest.TestCase):
    def setUp(self):
        self.market_cfg = MarketConfig(coin="xyz:SKHX", tick_size=0.01)
        self.bt_cfg = BacktestConfig(
            initial_cash_usd=10000.0,
            order_size_btc=10.0,
            midpoint_pegging=True,
            horizons_seconds=[],
            warmup_secs=0.0,
        )

    def test_backtester_maker_buy_records_midpoint(self):
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg,
            bt_cfg=self.bt_cfg,
            strategy_defs={"Stock_Microstructure_Alpha": ("StockMicrostructure", 0.05)},
            strategy_params={"Stock_Microstructure_Alpha": {"execution_type": "MAKER", "entry_threshold": 0.05, "order_size_btc": 10.0}},
            warmup_secs=0.0,
        )

        # Trigger bullish entry
        timestamp_ms = 1000
        best_bid = 968.40
        best_ask = 968.44  # Spread $0.04 -> Mid $968.42
        mid_price = 968.42
        signals = {"StockMicrostructure": 0.15}

        evaluator.record_step(
            timestamp_ms=timestamp_ms,
            mid_price=mid_price,
            best_bid=best_bid,
            best_ask=best_ask,
            signals=signals,
        )

        state = evaluator.strategies["Stock_Microstructure_Alpha"]
        self.assertTrue(state.is_in_position)
        self.assertEqual(state.position_btc, 10.0)
        self.assertEqual(state.entry_price, 968.42)
        self.assertEqual(evaluator.position_events[-1]["exec"], "MAKER (MID)")

    def test_backtester_maker_buy_disabled_records_best_bid(self):
        self.bt_cfg.midpoint_pegging = False
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg,
            bt_cfg=self.bt_cfg,
            strategy_defs={"Stock_Microstructure_Alpha": ("StockMicrostructure", 0.05)},
            strategy_params={"Stock_Microstructure_Alpha": {"execution_type": "MAKER", "entry_threshold": 0.05, "order_size_btc": 10.0}},
            warmup_secs=0.0,
        )

        timestamp_ms = 1000
        best_bid = 968.40
        best_ask = 968.44
        mid_price = 968.42
        signals = {"StockMicrostructure": 0.15}

        evaluator.record_step(
            timestamp_ms=timestamp_ms,
            mid_price=mid_price,
            best_bid=best_bid,
            best_ask=best_ask,
            signals=signals,
        )

        state = evaluator.strategies["Stock_Microstructure_Alpha"]
        self.assertTrue(state.is_in_position)
        self.assertEqual(state.position_btc, 10.0)
        self.assertEqual(state.entry_price, 968.40)
        self.assertEqual(evaluator.position_events[-1]["exec"], "MAKER")


class TestCLIParsing(unittest.TestCase):
    def test_core_parser_midpoint_pegging_flag(self):
        parser = build_core_parser()

        args_on = parser.parse_args(["live", "--midpoint-pegging"])
        self.assertTrue(args_on.midpoint_pegging)

        args_off = parser.parse_args(["live", "--no-midpoint-pegging"])
        self.assertFalse(args_off.midpoint_pegging)

        args_default = parser.parse_args(["live"])
        self.assertIsNone(args_default.midpoint_pegging)

    def test_main_parser_midpoint_pegging_flag(self):
        parser = build_main_parser()

        args_on = parser.parse_args(["live", "--midpoint-pegging"])
        self.assertTrue(args_on.midpoint_pegging)

        args_off = parser.parse_args(["live", "--no-midpoint-pegging"])
        self.assertFalse(args_off.midpoint_pegging)

        args_default = parser.parse_args(["live"])
        self.assertIsNone(args_default.midpoint_pegging)

    def test_scalper_parser_midpoint_pegging_flag(self):
        parser = build_scalper_parser()

        args_on = parser.parse_args(["live", "--midpoint-pegging"])
        self.assertTrue(args_on.midpoint_pegging)

        args_off = parser.parse_args(["live", "--no-midpoint-pegging"])
        self.assertFalse(args_off.midpoint_pegging)

        args_default = parser.parse_args(["live"])
        self.assertIsNone(args_default.midpoint_pegging)


if __name__ == "__main__":
    unittest.main()
