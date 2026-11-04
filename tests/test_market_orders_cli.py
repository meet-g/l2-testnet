"""Unit tests verifying --market and --slippage CLI arguments and market order execution mechanics."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config import AppConfig, DEFAULT_STRATEGIES_JSON, StrategiesConfig, BacktestConfig, MarketConfig
from engine.live_executor import LiveOrderExecutor
from engine.backtester import EdgeEvaluator


class TestMarketOrdersCLI(unittest.TestCase):
    """Verifies CLI parsing and configuration of --market and --slippage flags."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STRATEGIES_JSON, f, indent=2)
        self.temp_path = self.temp_file.name
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_path):
            try:
                os.remove(self.temp_path)
            except Exception:
                pass

    def test_market_true_and_slippage_1_percent(self):
        """Verifies --market true --slippage 1.0 configures forced market orders with 1.0% (100 bps) slippage."""
        cmd = [
            sys.executable,
            "main.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market", "true",
            "--slippage", "1.0",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("ENABLED (Taker IOC)", res.stdout)
        self.assertIn("1.00%", res.stdout)
        self.assertIn("100.0", res.stdout)

    def test_market_flag_alone_enables_market_orders(self):
        """Verifies --market alone (nargs='?', const='true') enables forced market orders."""
        cmd = [
            sys.executable,
            "main.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("ENABLED (Taker IOC)", res.stdout)

    def test_slippage_flag_implies_market_true(self):
        """Verifies --slippage 0.5 activates market orders with 0.5% (50 bps) tolerance."""
        cmd = [
            sys.executable,
            "main.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--slippage", "0.5",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("ENABLED (Taker IOC)", res.stdout)
        self.assertIn("0.50%", res.stdout)
        self.assertIn("50.0", res.stdout)

    def test_market_false_overrides_slippage(self):
        """Verifies --market false keeps market orders disabled even if --slippage is passed."""
        cmd = [
            sys.executable,
            "main.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market", "false",
            "--slippage", "1.0",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("DISABLED (Standard Maker/Taker Hybrid)", res.stdout)

    def test_save_config_persists_market_settings(self):
        """Verifies --market true --slippage 2.0 --save-config persists to disk JSON."""
        cmd = [
            sys.executable,
            "main.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market", "true",
            "--slippage", "2.0",
            "--save-config",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")

        # Check loaded configuration from disk
        cfg = StrategiesConfig.load(self.temp_path)
        self.assertTrue(cfg.live_execution.force_market_orders)
        self.assertAlmostEqual(cfg.live_execution.market_slippage_pct, 0.02, places=4)


class TestLiveExecutorMarketOrders(unittest.TestCase):
    """Verifies LiveOrderExecutor aggressive market order mechanics crossing the book with slippage."""

    def setUp(self):
        self.cfg = AppConfig()
        self.cfg.account.account_address = "0x1111111111111111111111111111111111111111"
        self.cfg.account.secret_key = "0x" + "2" * 64

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_place_market_order_buy_and_sell(self, mock_info_cls, mock_exchange_cls):
        """Verifies place_market_order prices orders crossing the book by slippage percentage."""
        executor = LiveOrderExecutor(
            config=self.cfg,
            force_market_orders=True,
            market_slippage_pct=0.01,  # 1.0% = 100 bps
            non_blocking=False,
        )
        executor.is_initialized = True
        executor.exchange = MagicMock()
        executor.last_best_bid = 100.0
        executor.last_best_ask = 101.0
        executor.sz_decimals = 4
        executor.max_price_decimals = 2

        # 1. Market BUY order: crosses ask by 1% -> 101.0 * 1.01 = 102.01
        with patch.object(executor, "place_limit_order") as mock_place_lim:
            executor.place_market_order(is_buy=True, size_btc=0.5)
            mock_place_lim.assert_called_once()
            _, kwargs = mock_place_lim.call_args
            self.assertTrue(kwargs["is_buy"])
            self.assertAlmostEqual(kwargs["price"], 102.01, places=2)
            self.assertFalse(kwargs["post_only"])
            self.assertEqual(kwargs["tif"], "Ioc")

        # 2. Market SELL order: crosses bid by 1% -> 100.0 * 0.99 = 99.0
        with patch.object(executor, "place_limit_order") as mock_place_lim:
            executor.place_market_order(is_buy=False, size_btc=0.5)
            mock_place_lim.assert_called_once()
            _, kwargs = mock_place_lim.call_args
            self.assertFalse(kwargs["is_buy"])
            self.assertAlmostEqual(kwargs["price"], 99.0, places=2)
            self.assertFalse(kwargs["post_only"])
            self.assertEqual(kwargs["tif"], "Ioc")

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_on_signal_update_forced_market_entry(self, mock_info_cls, mock_exchange_cls):
        """Verifies on_signal_update executes entries immediately as market IOC when force_market_orders is True."""
        executor = LiveOrderExecutor(
            config=self.cfg,
            force_market_orders=True,
            market_slippage_pct=0.01,  # 1% slippage
            non_blocking=False,
        )
        executor.is_initialized = True
        executor.exchange = MagicMock()
        executor.sz_decimals = 4
        executor.max_price_decimals = 2
        executor.cached_position = 0.0  # Flat

        # Bullish entry trigger
        with patch.object(executor, "place_limit_order") as mock_place_lim:
            executor.on_signal_update(
                signal_score=0.90,  # Above threshold
                best_bid=100.0,
                best_ask=101.0,
                spread=1.0,
            )
            mock_place_lim.assert_called_once()
            _, kwargs = mock_place_lim.call_args
            self.assertTrue(kwargs["is_buy"])
            self.assertAlmostEqual(kwargs["price"], 102.01, places=2)  # 101.0 * 1.01
            self.assertFalse(kwargs["post_only"])
            self.assertEqual(kwargs["tif"], "Ioc")

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_on_signal_update_forced_market_tp_exit(self, mock_info_cls, mock_exchange_cls):
        """Verifies on_signal_update executes take profit as immediate market IOC when force_market_orders is True."""
        executor = LiveOrderExecutor(
            config=self.cfg,
            force_market_orders=True,
            market_slippage_pct=0.01,  # 1% slippage
            non_blocking=False,
        )
        executor.is_initialized = True
        executor.exchange = MagicMock()
        executor.sz_decimals = 4
        executor.max_price_decimals = 2
        executor.cached_position = 0.5  # Long 0.5 BTC
        executor.entry_price = 100.0

        # Best bid moves to 102.5 (+250 bps gain, well above typical TP threshold)
        with patch.object(executor, "place_limit_order") as mock_place_lim:
            executor.on_signal_update(
                signal_score=0.0,
                best_bid=102.5,
                best_ask=103.0,
                spread=0.5,
            )
            mock_place_lim.assert_called_once()
            _, kwargs = mock_place_lim.call_args
            self.assertFalse(kwargs["is_buy"])  # Sell to exit long
            self.assertTrue(kwargs["is_exit"])
            self.assertAlmostEqual(kwargs["price"], 101.48, places=1)  # 102.5 * 0.99 = 101.475
            self.assertFalse(kwargs["post_only"])
            self.assertEqual(kwargs["tif"], "Ioc")


class TestBacktesterMarketOrders(unittest.TestCase):
    """Verifies backtesting engine EdgeEvaluator respects forced market orders and applies slippage & taker fees."""

    def test_edge_evaluator_forced_market_orders(self):
        market_cfg = MarketConfig(coin="BTC", taker_fee_bps=4.5, maker_fee_bps=1.5)
        bt_cfg = BacktestConfig(
            force_market_orders=True,
            market_slippage_pct=0.01,  # 1% slippage
            entry_threshold=0.5,
            max_spread_bps=10.0,
        )
        evaluator = EdgeEvaluator(
            market_cfg=market_cfg,
            bt_cfg=bt_cfg,
            strategy_defs={"Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER")},
        )

        # Trigger bullish entry with realistic tight spread (0.2 bps)
        evaluator._update_paper_trading(
            timestamp_ms=1000,
            mid_price=100000.0,
            best_bid=99999.0,
            best_ask=100001.0,
            signals={"HedgedConvexity": 0.8},
        )

        strat_state = evaluator.strategies["Hedged_Convexity"]
        self.assertTrue(strat_state.is_in_position)
        # Entry price should be best_ask * (1.0 + 0.01) = 100001.0 * 1.01 = 101001.01
        expected_entry_px = 100001.0 * 1.01
        self.assertAlmostEqual(strat_state.entry_price, expected_entry_px, places=2)

        # Entry fee should be calculated at taker fee (4.5 bps), not maker fee (1.5 bps)
        expected_fee = expected_entry_px * strat_state.position_btc * (4.5 / 10000.0)
        self.assertAlmostEqual(strat_state.entry_fee_usd, expected_fee, places=4)


if __name__ == "__main__":
    unittest.main()
