"""Unit tests verifying the clean separation of Core strategies and Scalping strategies into two dedicated programs."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from config import (
    AppConfig,
    CoreStrategiesConfig,
    ScalperStrategiesConfig,
    ScalpingStrategiesConfig,
    StrategiesConfig,
    CORE_EXECUTION_STRATEGIES,
    SCALPING_STRATEGIES,
    NEW_EXECUTION_STRATEGIES,
    LEGACY_SCALPING_STRATEGIES,
    DEFAULT_CORE_STRATEGIES_JSON,
    DEFAULT_SCALPER_STRATEGIES_JSON,
)
from engine.backtester import EdgeEvaluator


class TestProgramSeparation(unittest.TestCase):
    """Verifies architectural, configuration, and entry-point separation between Core and Scalping programs."""

    def test_core_strategies_config_isolation(self):
        """Verifies CoreStrategiesConfig exclusively loads and manages the 4 core execution strategies."""
        cfg = CoreStrategiesConfig.load("strategies_core.json")

        self.assertIsInstance(cfg, CoreStrategiesConfig)
        self.assertIsInstance(cfg, StrategiesConfig)
        self.assertEqual(len(cfg.execution_strategies), len(CORE_EXECUTION_STRATEGIES))
        self.assertEqual(len(cfg.scalping_strategies), 0)
        self.assertEqual(len(cfg.all_strategies), len(CORE_EXECUTION_STRATEGIES))
        self.assertFalse(cfg.is_scalping_mode_active)

        for name in CORE_EXECUTION_STRATEGIES:
            self.assertIn(name, cfg.execution_strategies)
            self.assertTrue(cfg.is_execution_strategy(name))
            self.assertFalse(cfg.is_scalping_strategy(name))
            self.assertEqual(cfg.get_strategy_category(name), "execution")
            s = cfg.get_strategy(name)
            self.assertIsNotNone(s)
            self.assertFalse(s.is_scalping)

        for name in SCALPING_STRATEGIES:
            self.assertNotIn(name, cfg.execution_strategies)
            self.assertFalse(cfg.is_scalping_strategy(name))
            self.assertFalse(cfg.is_execution_strategy(name))
            self.assertIsNone(cfg.get_strategy(name))

        # Check effective live strategy
        self.assertEqual(cfg.get_effective_live_strategy(), "Hedged_Convexity")

        # Check parameters extraction
        params = cfg.get_strategy_params()
        self.assertEqual(len(params), len(CORE_EXECUTION_STRATEGIES))
        defs = cfg.get_enabled_strategy_defs()
        self.assertGreaterEqual(len(defs), 1)

    def test_scalper_strategies_config_isolation(self):
        """Verifies ScalperStrategiesConfig exclusively loads and manages the 11 scalping strategies."""
        cfg = ScalperStrategiesConfig.load("strategies_scalper.json")

        self.assertIsInstance(cfg, ScalperStrategiesConfig)
        self.assertIsInstance(cfg, StrategiesConfig)
        self.assertEqual(len(cfg.execution_strategies), 0)
        self.assertEqual(len(cfg.scalping_strategies), 11)
        self.assertEqual(len(cfg.all_strategies), 11)
        self.assertTrue(cfg.is_scalping_mode_active)

        for name in SCALPING_STRATEGIES:
            self.assertIn(name, cfg.scalping_strategies)
            self.assertTrue(cfg.is_scalping_strategy(name))
            self.assertFalse(cfg.is_execution_strategy(name))
            self.assertEqual(cfg.get_strategy_category(name), "scalping")
            s = cfg.get_strategy(name)
            self.assertIsNotNone(s)
            self.assertTrue(s.is_scalping)

        for name in CORE_EXECUTION_STRATEGIES:
            self.assertNotIn(name, cfg.scalping_strategies)
            self.assertFalse(cfg.is_execution_strategy(name))
            self.assertFalse(cfg.is_scalping_strategy(name))
            self.assertIsNone(cfg.get_strategy(name))

        # Check effective live strategy
        self.assertEqual(cfg.get_effective_live_strategy(), "Composite_Maker")

        # Check parameters extraction
        params = cfg.get_strategy_params()
        self.assertEqual(len(params), 11)
        defs = cfg.get_enabled_strategy_defs()
        self.assertGreaterEqual(len(defs), 1)

    def test_strategies_config_auto_dispatch(self):
        """Verifies StrategiesConfig.load auto-dispatches to Core or Scalper based on filepath or metadata."""
        core_loaded = StrategiesConfig.load("strategies_core.json")
        self.assertIsInstance(core_loaded, CoreStrategiesConfig)
        self.assertEqual(len(core_loaded.execution_strategies), len(CORE_EXECUTION_STRATEGIES))
        self.assertEqual(len(core_loaded.scalping_strategies), 0)

        scalp_loaded = StrategiesConfig.load("strategies_scalper.json")
        self.assertIsInstance(scalp_loaded, ScalperStrategiesConfig)
        self.assertEqual(len(scalp_loaded.execution_strategies), 0)
        self.assertEqual(len(scalp_loaded.scalping_strategies), 11)

    def test_app_config_factory_methods(self):
        """Verifies AppConfig.for_core() and AppConfig.for_scalper()."""
        app_core = AppConfig.for_core()
        self.assertIsInstance(app_core.strategies, CoreStrategiesConfig)
        self.assertEqual(len(app_core.strategies.execution_strategies), len(CORE_EXECUTION_STRATEGIES))

        app_scalp = AppConfig.for_scalper()
        self.assertIsInstance(app_scalp.strategies, ScalperStrategiesConfig)
        self.assertEqual(len(app_scalp.strategies.scalping_strategies), 11)

    def test_core_serialization_round_trip(self):
        """Verifies CoreStrategiesConfig serialization outputs only core strategies without scalping pollution."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            cfg = CoreStrategiesConfig.load("strategies_core.json")
            cfg.filepath = temp_path
            cfg.save()

            with open(temp_path, "r", encoding="utf-8") as f:
                saved_data = json.load(f)

            self.assertEqual(saved_data.get("program"), "core_execution")
            self.assertIn("execution_strategies", saved_data)
            self.assertNotIn("scalping_strategies", saved_data)
            self.assertEqual(tuple(saved_data["execution_strategies"].keys()), CORE_EXECUTION_STRATEGIES)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_scalper_serialization_round_trip(self):
        """Verifies ScalperStrategiesConfig serialization outputs only scalping strategies without core pollution."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            cfg = ScalperStrategiesConfig.load("strategies_scalper.json")
            cfg.filepath = temp_path
            cfg.save()

            with open(temp_path, "r", encoding="utf-8") as f:
                saved_data = json.load(f)

            self.assertEqual(saved_data.get("program"), "scalper")
            self.assertIn("scalping_strategies", saved_data)
            self.assertNotIn("execution_strategies", saved_data)
            self.assertEqual(tuple(saved_data["scalping_strategies"].keys()), SCALPING_STRATEGIES)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_main_core_cli_execution(self):
        """Verifies main_core.py CLI runs strategies mode cleanly showing only core strategies."""
        cmd = [sys.executable, "main_core.py", "strategies"]
        env = {**os.environ, "COLUMNS": "200"}
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(res.returncode, 0, f"main_core.py failed: {res.stderr}")
        self.assertIn("CORE EXECUTION STRATEGY CONFIGURATION", res.stdout)
        self.assertIn("Hedged_Convexity", res.stdout)
        self.assertIn("Convexity_Cascade", res.stdout)
        self.assertIn("Momentum_Expansion", res.stdout)
        self.assertIn("Queue_Replenishment", res.stdout)
        self.assertNotIn("WOBI_Maker", res.stdout)
        self.assertNotIn("MicroPrice_FastFill", res.stdout)

    def test_main_core_cli_strategy_validation(self):
        """Verifies main_core.py rejects scalping strategies when passed via --strategy."""
        cmd = [sys.executable, "main_core.py", "strategies", "--strategy", "WOBI_Maker"]
        env = {**os.environ, "COLUMNS": "200"}
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("not a Core execution strategy", res.stdout + res.stderr)

    def test_main_scalper_cli_execution(self):
        """Verifies main_scalper.py CLI runs strategies mode cleanly showing only scalping strategies."""
        cmd = [sys.executable, "main_scalper.py", "strategies"]
        env = {**os.environ, "COLUMNS": "200"}
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(res.returncode, 0, f"main_scalper.py failed: {res.stderr}")
        self.assertIn("SCALPING STRATEGY CONFIGURATION", res.stdout)
        self.assertIn("Composite_Maker", res.stdout)
        self.assertIn("WOBI_Maker", res.stdout)
        self.assertIn("Instant_FastFill", res.stdout)
        self.assertIn("Dynamic_Spread_Scalper", res.stdout)
        self.assertNotIn("Hedged_Convexity", res.stdout)
        self.assertNotIn("Queue_Replenishment", res.stdout)

    def test_scalper_alias_cli_execution(self):
        """Verifies scalper.py CLI alias runs identically to main_scalper.py."""
        cmd = [sys.executable, "scalper.py", "strategies"]
        env = {**os.environ, "COLUMNS": "200"}
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(res.returncode, 0, f"scalper.py failed: {res.stderr}")
        self.assertIn("SCALPING STRATEGY CONFIGURATION", res.stdout)

    def test_main_scalper_cli_strategy_validation(self):
        """Verifies main_scalper.py rejects core strategies when passed via --strategy."""
        cmd = [sys.executable, "main_scalper.py", "strategies", "--strategy", "Hedged_Convexity"]
        env = {**os.environ, "COLUMNS": "200"}
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("not a Scalping strategy", res.stdout + res.stderr)

    def test_edge_evaluator_with_core_program_app_config(self):
        """Verifies EdgeEvaluator initializes only core execution strategies when using Core program config."""
        cfg = AppConfig.for_core()
        defs = cfg.strategies.get_enabled_strategy_defs()
        params = cfg.strategies.get_strategy_params()

        evaluator = EdgeEvaluator(strategy_defs=defs, strategy_params=params)
        for s_name in evaluator.strategy_names:
            self.assertIn(s_name, CORE_EXECUTION_STRATEGIES)
            self.assertNotIn(s_name, SCALPING_STRATEGIES)

    def test_edge_evaluator_with_scalper_program_app_config(self):
        """Verifies EdgeEvaluator initializes only scalping strategies when using Scalper program config."""
        cfg = AppConfig.for_scalper()
        defs = cfg.strategies.get_enabled_strategy_defs()
        params = cfg.strategies.get_strategy_params()

        evaluator = EdgeEvaluator(strategy_defs=defs, strategy_params=params)
        for s_name in evaluator.strategy_names:
            self.assertIn(s_name, SCALPING_STRATEGIES)
            self.assertNotIn(s_name, CORE_EXECUTION_STRATEGIES)

    def test_program_name_properties(self):
        """Verifies program_name property is distinctly exposed across Core, Scalper, and Unified configs."""
        core_cfg = CoreStrategiesConfig.load("strategies_core.json")
        self.assertEqual(core_cfg.program_name, "core_execution")

        scalp_cfg = ScalperStrategiesConfig.load("strategies_scalper.json")
        self.assertEqual(scalp_cfg.program_name, "scalper")

        unified_cfg = StrategiesConfig.load("strategies.json")
        self.assertEqual(unified_cfg.program_name, "unified")

    def test_core_and_scalper_set_scalping_mode_guards(self):
        """Verifies set_scalping_mode guards preserve strategy integrity on isolated configurations."""
        core_cfg = CoreStrategiesConfig.load("strategies_core.json")
        initial_states = {name: core_cfg.execution_strategies[name].enabled for name in CORE_EXECUTION_STRATEGIES}
        # Trying to enable scalping on core config should not alter core strategy states
        core_cfg.set_scalping_mode(enabled=True)
        for name in CORE_EXECUTION_STRATEGIES:
            self.assertEqual(core_cfg.execution_strategies[name].enabled, initial_states[name])
        self.assertFalse(core_cfg.is_scalping_mode_active)

        scalp_cfg = ScalperStrategiesConfig.load("strategies_scalper.json")
        # Trying to disable scalping on scalper config should not disable scalping strategies
        scalp_cfg.set_scalping_mode(enabled=False)
        self.assertTrue(scalp_cfg.is_scalping_mode_active)
        self.assertEqual(len(scalp_cfg.execution_strategies), 0)

    def test_main_core_replay_execution(self):
        """Verifies main_core.py runs replay without TypeError on recorded L2 data."""
        sample_file = "data/btc/hl_btc_l2_20260927_184522.jsonl"
        if not os.path.exists(sample_file):
            self.skipTest(f"Replay test file {sample_file} not found")
        cmd = [sys.executable, "main_core.py", "replay", "--replay-file", sample_file, "--speed", "100.0"]
        env = {**os.environ, "COLUMNS": "200"}
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(res.returncode, 0, f"main_core.py replay failed: {res.stderr}")
        self.assertIn("Replaying", res.stdout)
        self.assertIn("Hedged_Convexity", res.stdout)
        self.assertNotIn("WOBI_Maker", res.stdout)

    def test_main_scalper_replay_execution(self):
        """Verifies main_scalper.py runs replay without TypeError on recorded L2 data."""
        sample_file = "data/btc/hl_btc_l2_20260927_184522.jsonl"
        if not os.path.exists(sample_file):
            self.skipTest(f"Replay test file {sample_file} not found")
        cmd = [sys.executable, "main_scalper.py", "replay", "--replay-file", sample_file, "--speed", "100.0"]
        env = {**os.environ, "COLUMNS": "200"}
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(res.returncode, 0, f"main_scalper.py replay failed: {res.stderr}")
        self.assertIn("Replaying", res.stdout)
        self.assertIn("WOBI_Maker", res.stdout)
        self.assertNotIn("Hedged_Convexity", res.stdout)

    def test_account_address_override_cli(self):
        """Verifies --account CLI flag sets cfg.account.account_address properly."""
        core_app = AppConfig.for_core()
        core_app.account.account_address = "0x1234567890123456789012345678901234567890"
        self.assertEqual(core_app.account.account_address, "0x1234567890123456789012345678901234567890")
        self.assertTrue(core_app.account.has_account)

    def test_breakout_prop_trader_core_strategies_integration(self):
        """Verifies breakout_prop_trader defaults to strategies_core.json with active core strategies."""
        from breakout_prop_trader import _init_prop_worker
        import breakout_prop_trader
        _init_prop_worker("strategies_core.json")
        cfg = breakout_prop_trader._GLOBAL_STRATEGIES_CFG
        self.assertIsNotNone(cfg)
        self.assertEqual(len(cfg.execution_strategies), len(CORE_EXECUTION_STRATEGIES))
        expected_enabled = {"Hedged_Convexity", "Convexity_Cascade"}
        for name in CORE_EXECUTION_STRATEGIES:
            self.assertIn(name, cfg.execution_strategies)
            self.assertEqual(cfg.execution_strategies[name].enabled, name in expected_enabled)


if __name__ == "__main__":
    unittest.main()
