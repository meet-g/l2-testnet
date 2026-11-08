"""Unit tests verifying --scalping false and --scalping true CLI behavior, persistence, and conflict guards."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from config import DEFAULT_STRATEGIES_JSON, StrategiesConfig, LEGACY_SCALPING_STRATEGIES, NEW_EXECUTION_STRATEGIES


class TestScalpingFlagCLI(unittest.TestCase):
    """Verifies that --scalping false and --scalping true actually disable / enable all scalping strategies."""

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

    def test_scalping_false_disables_all_scalping_strategies(self):
        """Verifies that --scalping false disables every scalping strategy and saves to file."""
        cmd = [
            sys.executable,
            "main.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--scalping", "false",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("11 scalping strategies DISABLED", res.stdout)
        self.assertIn("Core execution strategies ENABLED", res.stdout)

        # Check loaded config from disk (persisted)
        cfg = StrategiesConfig.load(self.temp_path)
        self.assertFalse(cfg.is_scalping_mode_active)
        for s in cfg.scalping_strategies.values():
            self.assertFalse(s.enabled, f"Scalping strategy {s.name} should be DISABLED on disk")

        # Check that core strategies are enabled
        for name in ("Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion", "Queue_Replenishment"):
            self.assertTrue(cfg.execution_strategies[name].enabled, f"Core strategy {name} should be ENABLED on disk")

        self.assertEqual(cfg.live_execution.active_strategy, "Hedged_Convexity")

    def test_scalping_true_enables_all_scalping_strategies(self):
        """Verifies that --scalping true enables every scalping strategy and saves to file."""
        cmd = [
            sys.executable,
            "main.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--scalping", "true",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("11 scalping strategies ENABLED", res.stdout)
        self.assertIn("core execution strategies DISABLED", res.stdout)

        # Check loaded config from disk (persisted)
        cfg = StrategiesConfig.load(self.temp_path)
        self.assertTrue(cfg.is_scalping_mode_active)
        for s in cfg.scalping_strategies.values():
            self.assertTrue(s.enabled, f"Scalping strategy {s.name} should be ENABLED on disk")

        # Check that core strategies are disabled
        for s in cfg.execution_strategies.values():
            self.assertFalse(s.enabled, f"Core strategy {s.name} should be DISABLED on disk")

    def test_scalping_false_with_no_save_does_not_modify_file(self):
        """Verifies that --scalping false --no-save applies in-memory only and leaves disk untouched."""
        # Enable Instant_FastFill first
        cfg_init = StrategiesConfig.load(self.temp_path)
        cfg_init.scalping_strategies["Instant_FastFill"].enabled = True
        cfg_init.save()

        cmd = [
            sys.executable,
            "main.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--scalping", "false",
            "--no-save",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")

        # Check loaded config from disk: Instant_FastFill should STILL be enabled on disk because --no-save was used
        cfg_after = StrategiesConfig.load(self.temp_path)
        self.assertTrue(cfg_after.scalping_strategies["Instant_FastFill"].enabled)

    def test_strategy_conflict_guard_prevents_scalping_reactivation(self):
        """Verifies that passing --strategy Instant_FastFill with --scalping false does NOT re-enable Instant_FastFill."""
        cmd = [
            sys.executable,
            "main.py",
            "strategies",
            "--strategies-config", self.temp_path,
            "--strategy", "Instant_FastFill",
            "--scalping", "false",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command failed: {res.stderr}")
        self.assertIn("Conflict Guard", res.stdout)
        self.assertIn("Scalping strategies remain DISABLED", res.stdout)

        # Check on disk
        cfg = StrategiesConfig.load(self.temp_path)
        self.assertFalse(cfg.scalping_strategies["Instant_FastFill"].enabled)

    def test_default_mode_when_omitted(self):
        """Verifies that running 'main.py --scalping false' without positional mode works cleanly."""
        cmd = [
            sys.executable,
            "main.py",
            "--strategies-config", self.temp_path,
            "--scalping", "false",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(res.returncode, 0, f"Command without mode failed: {res.stderr}")
        self.assertIn("11 scalping strategies DISABLED", res.stdout)


if __name__ == "__main__":
    unittest.main()
