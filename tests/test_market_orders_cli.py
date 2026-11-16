"""Unit tests verifying --market and --slippage CLI arguments and market order execution mechanics."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config import (
    AppConfig,
    DEFAULT_STRATEGIES_JSON,
    DEFAULT_CORE_STRATEGIES_JSON,
    DEFAULT_SCALPER_STRATEGIES_JSON,
    StrategiesConfig,
    CoreStrategiesConfig,
    ScalperStrategiesConfig,
    BacktestConfig,
    MarketConfig,
)
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


class TestCoreMarketOrdersCLI(unittest.TestCase):
    """Verifies main_core.py CLI parsing and configuration of market order override toggles."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CORE_STRATEGIES_JSON, f, indent=2)
        self.temp_path = self.temp_file.name
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_path):
            try:
                os.remove(self.temp_path)
            except Exception:
                pass

    def test_core_market_flag_alone(self):
        """Verifies python main_core.py strategies --market enables forced market orders."""
        cmd = [
            sys.executable,
            "main_core.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("ENABLED (Taker IOC)", res.stdout)

    def test_core_market_true_and_slippage(self):
        """Verifies python main_core.py strategies --market true --slippage 1.5 configures market orders with 150 bps."""
        cmd = [
            sys.executable,
            "main_core.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market", "true",
            "--slippage", "1.5",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("ENABLED (Taker IOC)", res.stdout)
        self.assertIn("1.50%", res.stdout)
        self.assertIn("150.0", res.stdout)

    def test_core_no_market_flag(self):
        """Verifies python main_core.py strategies --no-market keeps market orders disabled."""
        cmd = [
            sys.executable,
            "main_core.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--no-market",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("DISABLED", res.stdout)

    def test_core_market_orders_alias(self):
        """Verifies python main_core.py strategies --market-orders alias enables market orders."""
        cmd = [
            sys.executable,
            "main_core.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market-orders",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("ENABLED (Taker IOC)", res.stdout)

    def test_core_save_config_persists_market_settings(self):
        """Verifies python main_core.py strategies --market true --slippage 1.2 --save-config writes to disk."""
        cmd = [
            sys.executable,
            "main_core.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market", "true",
            "--slippage", "1.2",
            "--save-config",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")

        cfg = CoreStrategiesConfig.load(self.temp_path)
        self.assertTrue(cfg.live_execution.force_market_orders)
        self.assertAlmostEqual(cfg.live_execution.market_slippage_pct, 0.012, places=4)


class TestScalperMarketOrdersCLI(unittest.TestCase):
    """Verifies main_scalper.py CLI parsing and configuration of market order override toggles."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SCALPER_STRATEGIES_JSON, f, indent=2)
        self.temp_path = self.temp_file.name
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_path):
            try:
                os.remove(self.temp_path)
            except Exception:
                pass

    def test_scalper_market_flag_alone(self):
        """Verifies python main_scalper.py strategies --market enables forced market orders."""
        cmd = [
            sys.executable,
            "main_scalper.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("ENABLED (Taker IOC)", res.stdout)

    def test_scalper_market_true_and_slippage(self):
        """Verifies python main_scalper.py strategies --market true --slippage 0.8 configures market orders with 80 bps."""
        cmd = [
            sys.executable,
            "main_scalper.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market", "true",
            "--slippage", "0.8",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("ENABLED (Taker IOC)", res.stdout)
        self.assertIn("0.80%", res.stdout)
        self.assertIn("80.0", res.stdout)

    def test_scalper_no_market_flag(self):
        """Verifies python main_scalper.py strategies --no-market keeps market orders disabled."""
        cmd = [
            sys.executable,
            "main_scalper.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--no-market",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("DISABLED", res.stdout)

    def test_scalper_market_orders_alias(self):
        """Verifies python main_scalper.py strategies --market-orders alias enables market orders."""
        cmd = [
            sys.executable,
            "main_scalper.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market-orders",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Forced Market Orders:", res.stdout)
        self.assertIn("ENABLED (Taker IOC)", res.stdout)

    def test_scalper_save_config_persists_market_settings(self):
        """Verifies python main_scalper.py strategies --market true --slippage 0.9 --save-config writes to disk."""
        cmd = [
            sys.executable,
            "main_scalper.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--market", "true",
            "--slippage", "0.9",
            "--save-config",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")

        cfg = ScalperStrategiesConfig.load(self.temp_path)
        self.assertTrue(cfg.live_execution.force_market_orders)
        self.assertAlmostEqual(cfg.live_execution.market_slippage_pct, 0.009, places=4)


class TestConfigMarketOrdersToggle(unittest.TestCase):
    """Verifies set_market_orders method on CoreStrategiesConfig, ScalperStrategiesConfig, and AppConfig."""

    def test_core_strategies_config_set_market_orders(self):
        cfg = CoreStrategiesConfig()
        self.assertFalse(cfg.live_execution.force_market_orders)
        cfg.set_market_orders(enabled=True, slippage_pct=0.002)
        self.assertTrue(cfg.live_execution.force_market_orders)
        self.assertEqual(cfg.live_execution.market_slippage_pct, 0.002)

        cfg.set_market_orders(enabled=False)
        self.assertFalse(cfg.live_execution.force_market_orders)

    def test_scalper_strategies_config_set_market_orders(self):
        cfg = ScalperStrategiesConfig()
        self.assertFalse(cfg.live_execution.force_market_orders)
        cfg.set_market_orders(enabled=True, slippage_pct=0.001)
        self.assertTrue(cfg.live_execution.force_market_orders)
        self.assertEqual(cfg.live_execution.market_slippage_pct, 0.001)

        cfg.set_market_orders(enabled=False)
        self.assertFalse(cfg.live_execution.force_market_orders)

    def test_app_config_set_market_orders_syncs_backtest(self):
        cfg = AppConfig.for_core()
        self.assertFalse(cfg.strategies.live_execution.force_market_orders)
        self.assertFalse(cfg.backtest.force_market_orders)

        cfg.set_market_orders(enabled=True, slippage_pct=0.005)
        self.assertTrue(cfg.strategies.live_execution.force_market_orders)
        self.assertTrue(cfg.backtest.force_market_orders)
        self.assertEqual(cfg.strategies.live_execution.market_slippage_pct, 0.005)
        self.assertEqual(cfg.backtest.market_slippage_pct, 0.005)


class TestPostOnlyMarketOrderSuppression(unittest.TestCase):
    """Verifies LiveOrderExecutor overrides post_only to False and sets tif to Ioc when force_market_orders is True."""

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_place_limit_order_suppresses_post_only(self, mock_info_cls, mock_exchange_cls):
        cfg = AppConfig()
        cfg.account.account_address = "0x1111111111111111111111111111111111111111"
        cfg.account.secret_key = "0x" + "2" * 64

        executor = LiveOrderExecutor(
            config=cfg,
            force_market_orders=True,
            market_slippage_pct=0.005,
            non_blocking=False,
        )
        executor.is_initialized = True
        executor.exchange = MagicMock()
        executor.sz_decimals = 4
        executor.max_price_decimals = 2

        # When force_market_orders is True, place_limit_order should execute as IOC taker (post_only=False)
        with patch.object(executor.exchange, "order") as mock_exchange_order:
            mock_exchange_order.return_value = {"status": "ok", "response": {"type": "order", "data": {"statuses": [{"resting": {"oid": 12345}}]}}}
            executor.place_limit_order(is_buy=True, size_btc=0.5, price=100.0, post_only=True)
            mock_exchange_order.assert_called_once()
            call_order_type = mock_exchange_order.call_args[1].get("order_type") or mock_exchange_order.call_args[0][2]
            self.assertEqual(call_order_type["limit"]["tif"], "Ioc")


if __name__ == "__main__":
    unittest.main()
