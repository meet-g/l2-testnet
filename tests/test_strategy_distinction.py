"""Unit tests verifying the distinction between the 4 new execution strategies and legacy scalping strategies."""

import json
import os
import tempfile
import unittest

from config import (
    DEFAULT_STRATEGIES_JSON,
    ExecutionStrategyConfig,
    LEGACY_SCALPING_STRATEGIES,
    NEW_EXECUTION_STRATEGIES,
    ScalpingStrategyConfig,
    StrategiesConfig,
)
from engine.backtester import EdgeEvaluator, StrategyState


class TestStrategyDistinction(unittest.TestCase):
    """Verifies strict separation and categorization between core execution and scalping strategies."""

    def test_strategy_constants(self):
        """Verifies definition of NEW_EXECUTION_STRATEGIES and LEGACY_SCALPING_STRATEGIES."""
        expected_new = (
            "Hedged_Convexity",
            "Convexity_Cascade",
            "Momentum_Expansion",
            "Queue_Replenishment",
            "Stock_Microstructure_Alpha",
        )
        expected_legacy = (
            "QDAP_Maker",
            "Composite_Maker",
            "AdaptiveML_Maker",
            "WOBI_Maker",
            "MicroPrice_Maker",
            "MicroPrice_FastFill",
            "Absorption_Fade",
            "AdaptiveML_Taker",
            "Composite_Taker",
            "Instant_FastFill",
            "Dynamic_Spread_Scalper",
        )

        self.assertEqual(NEW_EXECUTION_STRATEGIES, expected_new)
        self.assertEqual(LEGACY_SCALPING_STRATEGIES, expected_legacy)
        self.assertEqual(len(NEW_EXECUTION_STRATEGIES), len(NEW_EXECUTION_STRATEGIES))
        self.assertEqual(len(LEGACY_SCALPING_STRATEGIES), 11)

        # Ensure no overlap
        overlap = set(NEW_EXECUTION_STRATEGIES).intersection(set(LEGACY_SCALPING_STRATEGIES))
        self.assertEqual(len(overlap), 0, f"Strategies overlap: {overlap}")

    def test_default_json_distinction(self):
        """Verifies DEFAULT_STRATEGIES_JSON partitions strategies into execution_strategies and scalping_strategies."""
        self.assertIn("execution_strategies", DEFAULT_STRATEGIES_JSON)
        self.assertIn("scalping_strategies", DEFAULT_STRATEGIES_JSON)

        exec_names = tuple(DEFAULT_STRATEGIES_JSON["execution_strategies"].keys())
        scalp_names = tuple(DEFAULT_STRATEGIES_JSON["scalping_strategies"].keys())

        self.assertEqual(exec_names, NEW_EXECUTION_STRATEGIES)
        self.assertEqual(scalp_names, LEGACY_SCALPING_STRATEGIES)

    def test_strategies_config_loading(self):
        """Verifies StrategiesConfig loads strategies.json with distinct execution and scalping categories."""
        cfg = StrategiesConfig.load("strategies.json")

        self.assertEqual(len(cfg.execution_strategies), len(NEW_EXECUTION_STRATEGIES))
        for name in NEW_EXECUTION_STRATEGIES:
            self.assertIn(name, cfg.execution_strategies)
            strat = cfg.execution_strategies[name]
            self.assertIsInstance(strat, ExecutionStrategyConfig)
            self.assertFalse(strat.is_scalping)
            self.assertTrue(cfg.is_execution_strategy(name))
            self.assertFalse(cfg.is_scalping_strategy(name))
            self.assertEqual(cfg.get_strategy_category(name), "execution")

        self.assertEqual(len(cfg.scalping_strategies), 11)
        for name in LEGACY_SCALPING_STRATEGIES:
            self.assertIn(name, cfg.scalping_strategies)
            strat = cfg.scalping_strategies[name]
            self.assertIsInstance(strat, ScalpingStrategyConfig)
            self.assertTrue(strat.is_scalping)
            self.assertFalse(cfg.is_execution_strategy(name))
            self.assertTrue(cfg.is_scalping_strategy(name))
            self.assertEqual(cfg.get_strategy_category(name), "scalping")

        # Verify all_strategies union
        all_strats = cfg.all_strategies
        self.assertEqual(len(all_strats), len(NEW_EXECUTION_STRATEGIES) + len(LEGACY_SCALPING_STRATEGIES))
        for name in NEW_EXECUTION_STRATEGIES + LEGACY_SCALPING_STRATEGIES:
            self.assertIn(name, all_strats)
            self.assertIsNotNone(cfg.get_strategy(name))

    def test_parameter_extraction_by_category(self):
        """Verifies get_execution_strategy_params vs get_scalping_strategy_params."""
        cfg = StrategiesConfig.load("strategies.json")

        exec_params = cfg.get_execution_strategy_params()
        self.assertEqual(len(exec_params), len(NEW_EXECUTION_STRATEGIES))
        for name in NEW_EXECUTION_STRATEGIES:
            self.assertIn(name, exec_params)
            self.assertIn("entry_threshold", exec_params[name])

        scalp_params = cfg.get_scalping_strategy_params()
        self.assertEqual(len(scalp_params), 11)
        for name in LEGACY_SCALPING_STRATEGIES:
            self.assertIn(name, scalp_params)
            self.assertIn("entry_threshold", scalp_params[name])

    def test_backward_compatibility_migration(self):
        """Verifies that older JSON files containing legacy strategies under execution_strategies are auto-migrated."""
        old_format = {
            "version": "1.0",
            "execution_strategies": {
                "Hedged_Convexity": {"enabled": True, "entry_threshold": 0.86},
                "WOBI_Maker": {"enabled": True, "entry_threshold": 0.40},
                "AdaptiveML_Taker": {"enabled": False, "entry_threshold": 0.70},
            },
            "alpha_signals": {},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(old_format, f)
            temp_path = f.name

        try:
            cfg = StrategiesConfig.load(temp_path)
            self.assertIn("Hedged_Convexity", cfg.execution_strategies)
            self.assertNotIn("WOBI_Maker", cfg.execution_strategies)
            self.assertNotIn("AdaptiveML_Taker", cfg.execution_strategies)

            self.assertIn("WOBI_Maker", cfg.scalping_strategies)
            self.assertTrue(cfg.scalping_strategies["WOBI_Maker"].enabled)
            self.assertEqual(cfg.scalping_strategies["WOBI_Maker"].entry_threshold, 0.40)
            self.assertIn("AdaptiveML_Taker", cfg.scalping_strategies)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_serialization_round_trip(self):
        """Verifies to_dict and save maintain strict category separation."""
        cfg = StrategiesConfig.load("strategies.json")
        data = cfg.to_dict()

        self.assertIn("execution_strategies", data)
        self.assertIn("scalping_strategies", data)
        self.assertEqual(tuple(data["execution_strategies"].keys()), NEW_EXECUTION_STRATEGIES)
        self.assertEqual(tuple(data["scalping_strategies"].keys()), LEGACY_SCALPING_STRATEGIES)

    def test_edge_evaluator_categorization(self):
        """Verifies EdgeEvaluator annotates StrategyState with appropriate category."""
        evaluator = EdgeEvaluator()

        self.assertEqual(set(evaluator.execution_strategy_names), set(NEW_EXECUTION_STRATEGIES))
        self.assertEqual(set(evaluator.scalping_strategy_names), set(LEGACY_SCALPING_STRATEGIES))

        for name in NEW_EXECUTION_STRATEGIES:
            state = evaluator.strategies[name]
            self.assertEqual(state.category, "execution")

        for name in LEGACY_SCALPING_STRATEGIES:
            state = evaluator.strategies[name]
            self.assertEqual(state.category, "scalping")

    def test_set_scalping_mode_toggle(self):
        """Verifies set_scalping_mode(True) enables all 8 scalping and disables core, and vice versa."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(DEFAULT_STRATEGIES_JSON, f, indent=2)
            temp_path = f.name

        try:
            cfg = StrategiesConfig.load(temp_path)

            # 1. Enable scalping mode
            cfg.set_scalping_mode(enabled=True)
            self.assertTrue(cfg.is_scalping_mode_active)

            for name in LEGACY_SCALPING_STRATEGIES:
                self.assertTrue(cfg.scalping_strategies[name].enabled, f"{name} should be enabled in scalping mode")
            for name in NEW_EXECUTION_STRATEGIES:
                self.assertFalse(cfg.execution_strategies[name].enabled, f"{name} should be disabled in scalping mode")
            self.assertEqual(cfg.live_execution.active_strategy, "Composite_Maker")

            # 2. Disable scalping mode (return to core mode)
            cfg.set_scalping_mode(enabled=False)
            self.assertFalse(cfg.is_scalping_mode_active)

            for name in LEGACY_SCALPING_STRATEGIES:
                self.assertFalse(cfg.scalping_strategies[name].enabled, f"{name} should be disabled in core mode")
            for name in ("Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion", "Queue_Replenishment"):
                self.assertTrue(cfg.execution_strategies[name].enabled, f"{name} should be enabled in core mode")
            self.assertEqual(cfg.live_execution.active_strategy, "Hedged_Convexity")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_scalping_session_ended_then_normal_session_runs(self):
        """Verifies that when a scalping session ends, a subsequent normal session has scalping strategies disabled."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(DEFAULT_STRATEGIES_JSON, f, indent=2)
            default_path = f.name

        try:
            # 1. Simulate starting a scalping session via CLI (transient in-memory override)
            scalp_session_cfg = StrategiesConfig.load(default_path)
            scalp_session_cfg.set_scalping_mode(enabled=True, save=False)

            # Confirm scalping session had scalping enabled
            self.assertTrue(scalp_session_cfg.is_scalping_mode_active)
            for s in LEGACY_SCALPING_STRATEGIES:
                self.assertTrue(scalp_session_cfg.scalping_strategies[s].enabled)
            for s in NEW_EXECUTION_STRATEGIES:
                self.assertFalse(scalp_session_cfg.execution_strategies[s].enabled)

            # 2. Scalping session ends. User now starts a normal session:
            # Normal session loads default strategies.json without --scalping override
            normal_session_cfg = StrategiesConfig.load(default_path)

            # Confirm scalping strategies are strictly DISABLED in normal session
            self.assertFalse(normal_session_cfg.is_scalping_mode_active)
            for s in LEGACY_SCALPING_STRATEGIES:
                self.assertFalse(
                    normal_session_cfg.scalping_strategies[s].enabled,
                    f"Scalping strategy {s} must be disabled when normal session runs"
                )

            # Confirm core execution strategies are active
            for s in ("Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion"):
                self.assertTrue(
                    normal_session_cfg.execution_strategies[s].enabled,
                    f"Core execution strategy {s} must be active in normal session"
                )

            # Active live strategy must be a core strategy (Hedged_Convexity)
            self.assertEqual(normal_session_cfg.live_execution.active_strategy, "Hedged_Convexity")
            self.assertTrue(normal_session_cfg.is_execution_strategy(normal_session_cfg.live_execution.active_strategy))
        finally:
            if os.path.exists(default_path):
                os.remove(default_path)

    def test_effective_live_strategy_resolution(self):
        """Verifies get_effective_live_strategy dynamically resolves to enabled strategy when active_strategy is disabled."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(DEFAULT_STRATEGIES_JSON, f, indent=2)
            temp_path = f.name

        try:
            cfg = StrategiesConfig.load(temp_path)
            # Default: Hedged_Convexity is active and enabled
            self.assertEqual(cfg.get_effective_live_strategy(), "Hedged_Convexity")

            # Disable Hedged_Convexity while active_strategy is still Hedged_Convexity
            cfg.execution_strategies["Hedged_Convexity"].enabled = False
            # Should dynamically resolve to next enabled execution strategy
            self.assertEqual(cfg.get_effective_live_strategy(), "Convexity_Cascade")

            # Disable all execution strategies and enable MicroPrice_FastFill
            for s in cfg.execution_strategies.values():
                s.enabled = False
            cfg.scalping_strategies["MicroPrice_FastFill"].enabled = True
            cfg.live_execution.active_strategy = "Hedged_Convexity"  # still pointing to disabled
            self.assertEqual(cfg.get_effective_live_strategy(), "MicroPrice_FastFill")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
