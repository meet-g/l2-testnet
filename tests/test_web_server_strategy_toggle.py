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
        # Create a temp strategies.json file to test persistence
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.strat_cfg = StrategiesConfig.load("strategies.json")
        self.strat_cfg.filepath = self.temp_file.name
        self.strat_cfg.save()
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
        self.assertEqual(len(res["scalping_strategies"]), 8)
        self.assertEqual(len(res["strategies"]), 12)

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
        self.assertEqual(len(strats), 12, "Telemetry must contain all 12 strategies so none disappear")

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
        self.assertEqual(res["enabled_count"], 8)
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
        self.assertEqual(res_core["disabled_count"], 9)

        # Verify on disk
        with open(self.temp_file.name, "r") as f:
            disk_data = json.load(f)
        for s_name in disk_data["scalping_strategies"]:
            self.assertFalse(disk_data["scalping_strategies"][s_name]["enabled"])


if __name__ == "__main__":
    unittest.main()
