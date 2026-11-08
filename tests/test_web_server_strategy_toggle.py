"""Unit tests verifying web server strategy toggle and persistence without strategy disappearance."""

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from config import AppConfig, StrategiesConfig
from core.orderbook import OrderBook
from engine.backtester import EdgeEvaluator
from ui.web_server import (
    DashboardWebServer,
    ScalpingModeRequest,
    StrategyToggleRequest,
    TelemetryBroadcaster,
    create_web_app,
)


class TestWebServerStrategyToggle(unittest.TestCase):
    """Verifies that strategies can be turned on and off via web API without disappearing."""

    def setUp(self):
        # Create a temp strategies.json file to test persistence initialized from clean default
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        from config import DEFAULT_STRATEGIES_JSON
        with open(self.temp_file.name, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STRATEGIES_JSON, f, indent=2)
        self.strat_cfg = StrategiesConfig.load(self.temp_file.name)
        self.temp_file.close()

        # Mock runner
        self.runner = MagicMock()
        self.runner.config = AppConfig()
        self.runner.config.strategies = self.strat_cfg
        self.runner.book = OrderBook(coin="BTC")
        self.runner.trades = MagicMock()
        self.runner.trades.total_cvd = 1.25
        self.runner.live_orders = False
        self.runner.live_executor = None

        self.evaluator = EdgeEvaluator(
            strategy_defs=self.strat_cfg.get_enabled_strategy_defs(include_scalping=True),
            strategy_params=self.strat_cfg.get_strategy_params(include_scalping=True),
        )
        self.runner.evaluator = self.evaluator

        self.broadcaster = TelemetryBroadcaster(target_fps=10.0)
        self.app = create_web_app(lambda: self.runner, self.broadcaster)

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            try:
                os.remove(self.temp_file.name)
            except Exception:
                pass

    def _get_route_endpoint(self, path: str, method: str):
        """Helper to find route endpoint function on FastAPI app."""
        for route in self.app.routes:
            if hasattr(route, "path") and route.path == path:
                if method in route.methods:
                    return route.endpoint
        raise ValueError(f"Route {method} {path} not found")

    def test_get_strategies_endpoint(self):
        """Verifies /api/strategies returns all 12 strategies partitioned into execution and scalping."""
        endpoint = self._get_route_endpoint("/api/strategies", "GET")
        res = asyncio.run(endpoint())

        self.assertIn("strategies", res)
        self.assertIn("execution_strategies", res)
        self.assertIn("scalping_strategies", res)

        self.assertEqual(len(res["execution_strategies"]), 4)
        self.assertEqual(len(res["scalping_strategies"]), 11)
        self.assertEqual(len(res["strategies"]), 15)

        # Check category annotations
        for name in res["execution_strategies"]:
            self.assertEqual(res["strategies"][name]["category"], "execution")
        for name in res["scalping_strategies"]:
            self.assertEqual(res["strategies"][name]["category"], "scalping")

        self.assertIn("is_scalping_mode", res)
        self.assertFalse(res["is_scalping_mode"])

    def test_toggle_strategy_off_and_persistence(self):
        """Verifies turning a strategy off updates memory, config file, and preserves state."""
        toggle_endpoint = self._get_route_endpoint("/api/strategy/toggle", "POST")

        # 1. Turn Convexity_Cascade OFF
        req = StrategyToggleRequest(strategy="Convexity_Cascade", enabled=False)
        res = asyncio.run(toggle_endpoint(req))

        self.assertEqual(res["status"], "ok")
        self.assertFalse(res["enabled"])
        self.assertEqual(res["strategy"], "Convexity_Cascade")

        # Verify memory state
        self.assertFalse(self.strat_cfg.is_strategy_enabled("Convexity_Cascade"))
        self.assertNotIn("Convexity_Cascade", self.evaluator.strategy_names)

        # Verify disk persistence
        with open(self.temp_file.name, "r") as f:
            disk_data = json.load(f)
        self.assertFalse(disk_data["execution_strategies"]["Convexity_Cascade"]["enabled"])

        # 2. Check telemetry payload: Strategy MUST NOT disappear!
        server = DashboardWebServer(runner=self.runner)

        # Create snapshot manually using the same telemetry logic
        all_configured = self.runner.config.strategies.all_strategies
        self.assertIn("Convexity_Cascade", all_configured)
        self.assertFalse(all_configured["Convexity_Cascade"].enabled)

    def test_toggle_strategy_on_and_persistence(self):
        """Verifies turning a previously disabled scalping strategy ON."""
        toggle_endpoint = self._get_route_endpoint("/api/strategy/toggle", "POST")

        # Ensure QDAP_Maker starts OFF
        self.assertFalse(self.strat_cfg.is_strategy_enabled("QDAP_Maker"))

        # Turn QDAP_Maker ON
        req = StrategyToggleRequest(strategy="QDAP_Maker", enabled=True)
        res = asyncio.run(toggle_endpoint(req))

        self.assertEqual(res["status"], "ok")
        self.assertTrue(res["enabled"])
        self.assertEqual(res["strategy"], "QDAP_Maker")
        self.assertEqual(res["category"], "scalping")

        # Verify memory state
        self.assertTrue(self.strat_cfg.is_strategy_enabled("QDAP_Maker"))
        self.assertIn("QDAP_Maker", self.evaluator.strategy_names)

        # Verify disk persistence
        with open(self.temp_file.name, "r") as f:
            disk_data = json.load(f)
        self.assertTrue(disk_data["scalping_strategies"]["QDAP_Maker"]["enabled"])

    def test_telemetry_contains_all_strategies_regardless_of_enabled_state(self):
        """Verifies telemetry payload always includes all 12 strategies with explicit enabled states."""
        # Broadcast server
        server = DashboardWebServer(runner=self.runner)

        # Disable one execution strategy and enable one scalping strategy
        self.strat_cfg.execution_strategies["Momentum_Expansion"].enabled = False
        self.strat_cfg.scalping_strategies["WOBI_Maker"].enabled = True

        captured_snapshots = []
        async def mock_broadcast(data, force=False):
            captured_snapshots.append(data)

        server.broadcaster.broadcast_snapshot = mock_broadcast
        server.broadcaster.last_broadcast_time = 0.0  # Force broadcast bypass throttle

        asyncio.run(server.emit_telemetry(
            book=self.runner.book,
            trades=self.runner.trades,
            display_signals={"CompositeAlpha": 0.42},
            evaluator=self.evaluator,
            network="Testnet",
        ))

        self.assertEqual(len(captured_snapshots), 1)
        snap = captured_snapshots[0]
        self.assertIn("strategies", snap)

        strats = snap["strategies"]
        self.assertEqual(len(strats), 15, "Telemetry must contain all 15 strategies so none disappear")

        # Momentum_Expansion was disabled -> must be present with enabled=False
        self.assertIn("Momentum_Expansion", strats)
        self.assertFalse(strats["Momentum_Expansion"]["enabled"])
        self.assertEqual(strats["Momentum_Expansion"]["category"], "execution")

        # WOBI_Maker was enabled -> must be present with enabled=True
        self.assertIn("WOBI_Maker", strats)
        self.assertTrue(strats["WOBI_Maker"]["enabled"])
        self.assertEqual(strats["WOBI_Maker"]["category"], "scalping")

        self.assertIn("is_scalping_mode", snap)

    def test_bulk_scalping_mode_endpoint(self):
        """Verifies POST /api/strategies/mode/scalping bulk toggles strategies and persists."""
        endpoint = self._get_route_endpoint("/api/strategies/mode/scalping", "POST")

        # 1. Switch to scalping mode
        req = ScalpingModeRequest(scalping=True, save=True)
        res = asyncio.run(endpoint(req))

        self.assertEqual(res["status"], "ok")
        self.assertTrue(res["scalping_mode"])
        self.assertTrue(res["is_scalping_mode"])
        self.assertEqual(res["enabled_count"], 11)
        self.assertEqual(res["disabled_count"], 4)

        # Verify in memory
        self.assertTrue(self.strat_cfg.is_scalping_mode_active)
        for s_name, s_cfg in self.strat_cfg.scalping_strategies.items():
            self.assertTrue(s_cfg.enabled, f"{s_name} should be enabled")
            self.assertIn(s_name, self.evaluator.strategy_names)
        for s_name, s_cfg in self.strat_cfg.execution_strategies.items():
            self.assertFalse(s_cfg.enabled, f"{s_name} should be disabled")
            self.assertNotIn(s_name, self.evaluator.strategy_names)

        # Verify on disk
        with open(self.temp_file.name, "r") as f:
            disk_data = json.load(f)
        for s_name in disk_data["scalping_strategies"]:
            self.assertTrue(disk_data["scalping_strategies"][s_name]["enabled"])
        for s_name in disk_data["execution_strategies"]:
            self.assertFalse(disk_data["execution_strategies"][s_name]["enabled"])

        # 2. Switch back to Core mode
        req_core = ScalpingModeRequest(scalping=False, save=True)
        res_core = asyncio.run(endpoint(req_core))

        self.assertEqual(res_core["status"], "ok")
        self.assertFalse(res_core["scalping_mode"])
        self.assertFalse(res_core["is_scalping_mode"])
        self.assertEqual(res_core["enabled_count"], 3)  # Triad enabled, Queue_Replenishment off by default
        self.assertEqual(res_core["disabled_count"], 12)

        # Verify on disk
        with open(self.temp_file.name, "r") as f:
            disk_data = json.load(f)
        for s_name in disk_data["scalping_strategies"]:
            self.assertFalse(disk_data["scalping_strategies"][s_name]["enabled"])

    def test_live_orders_telemetry_strategy_cards_use_live_trades_not_paper_evaluator(self):
        """Verifies that in live orders mode, strategy cards display live trade metrics, not paper backtester metrics."""
        server = DashboardWebServer(runner=self.runner)

        # 1. Populate evaluator with simulated paper trades showing +$2.23 (11 trades, 81.8% win rate)
        paper_state = self.evaluator.strategies.get("Momentum_Expansion")
        if paper_state:
            mock_trade = MagicMock()
            mock_trade.realized_pnl_usd = 0.20
            mock_trade.net_pnl_usd = 0.20
            mock_trade.gross_pnl_usd = 0.21
            mock_trade.exit_time_ms = 1000
            mock_trade.entry_time_ms = 900
            mock_trade.size_btc = 0.05
            mock_trade.entry_price = 80000.0
            mock_trade.exit_price = 80004.0
            mock_trade.return_bps = 5.0
            mock_trade.exit_reason = "TAKE_PROFIT"
            mock_trade.strategy_name = "Momentum_Expansion"
            paper_state.trades = [mock_trade] * 11
            paper_state.realized_pnl_usd = 2.23

        # 2. Configure runner in LIVE MODE with 1 actual losing trade (-$1.50)
        self.runner.live_orders = True
        mock_lx = MagicMock()
        mock_lx.cached_position = 0.0
        mock_lx.entry_price = 0.0
        mock_lx.account_value = 100.0
        mock_lx.initial_account_value = 101.50
        mock_lx.session_realized_pnl = -1.50
        mock_lx.completed_trades = [
            {
                "strategy": "Momentum_Expansion",
                "side": "LONG",
                "size_btc": 0.05,
                "entry_price": 80000.0,
                "exit_price": 79970.0,
                "gross_pnl_usd": -1.50,
                "entry_fee_usd": 0.05,
                "exit_fee_usd": 0.05,
                "total_fees_usd": 0.10,
                "net_pnl_usd": -1.60,
                "return_bps": -20.0,
                "exit_reason": "STOP_LOSS",
                "entry_time_ms": 1000,
                "exit_time_ms": 2000,
            }
        ]
        self.runner.live_executor = mock_lx
        self.runner.auditor = None

        captured_snapshots = []
        async def mock_broadcast(data, force=False):
            captured_snapshots.append(data)

        server.broadcaster.broadcast_snapshot = mock_broadcast
        server.broadcaster.last_broadcast_time = 0.0

        asyncio.run(server.emit_telemetry(
            book=self.runner.book,
            trades=self.runner.trades,
            display_signals={"CompositeAlpha": 0.0},
            evaluator=self.evaluator,
            network="Testnet",
        ))

        self.assertEqual(len(captured_snapshots), 1)
        snap = captured_snapshots[0]

        # Verify Momentum_Expansion card shows LIVE trade metrics (-$1.60, 1 trade, 0.0% win rate), NOT paper metrics (+$2.23, 11 trades)
        mom_strat = snap["strategies"]["Momentum_Expansion"]
        self.assertEqual(mom_strat["trades"], 1, "Must report 1 live trade, NOT 11 paper trades")
        self.assertEqual(mom_strat["realized_pnl"], -1.60, "Must report -$1.60 live PnL, NOT +$2.23 paper PnL")
        self.assertEqual(mom_strat["win_rate"], 0.0, "Must report 0.0% win rate for live losses")

        # Verify portfolio summary uses live metrics
        port = snap["portfolio"]
        self.assertTrue(port["is_live"])
        self.assertEqual(port["total_trades"], 1)
        self.assertEqual(port["total_realized_pnl"], -1.50)


if __name__ == "__main__":
    unittest.main()
