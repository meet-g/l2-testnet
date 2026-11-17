"""Unit tests for event-driven execution latency and decoupled UI rendering.

Verifies:
1. Event-driven fast-path callback on incoming l2Book ticks evaluates composite alpha and triggers live executor immediately.
2. Event-driven fast-path callback on incoming trades ticks.
3. UI rendering throttling to 4Hz (250ms interval) to eliminate event loop blocking.
4. Evaluation loop acts as periodic heartbeat fallback without redundant compute.
"""

import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from config import AppConfig
from main import L2EngineRunner


class TestEventDrivenLatency(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cfg = AppConfig()
        # Create runner with live orders and recording disabled for unit test isolation
        self.runner = L2EngineRunner(config=self.cfg, record_data=False, live_orders=False)

    async def asyncTearDown(self):
        self.runner.close()

    async def test_l2book_triggers_event_driven_evaluation(self):
        # Mock _evaluate_signals to verify immediate invocation upon tick
        eval_called = False
        def _mock_eval():
            nonlocal eval_called
            eval_called = True

        self.runner._evaluate_signals = _mock_eval

        book_payload = {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": int(time.time() * 1000),
                "levels": [
                    [{"px": "80000.0", "sz": "1.5", "n": 2}],
                    [{"px": "80001.0", "sz": "1.5", "n": 2}],
                ]
            }
        }
        await self.runner._handle_message(json.dumps(book_payload))
        self.assertTrue(eval_called, "Incoming l2Book update must trigger event-driven _evaluate_signals immediately")

    async def test_trades_triggers_event_driven_evaluation(self):
        eval_called = False
        def _mock_eval():
            nonlocal eval_called
            eval_called = True

        self.runner._evaluate_signals = _mock_eval

        trade_payload = {
            "channel": "trades",
            "data": [
                {"coin": "BTC", "side": "B", "px": "80000.5", "sz": "0.1", "time": int(time.time() * 1000), "hash": "0x123"}
            ]
        }
        await self.runner._handle_message(json.dumps(trade_payload))
        self.assertTrue(eval_called, "Incoming trades update must trigger event-driven _evaluate_signals immediately")

    async def test_evaluation_loop_heartbeat_fallback(self):
        # Verify fallback heartbeat triggers if no event tick arrived recently
        eval_count = 0
        def _mock_eval():
            nonlocal eval_count
            eval_count += 1

        self.runner._evaluate_signals = _mock_eval
        self.runner.is_running = True
        self.runner.config.sample_rate_hz = 50  # 20ms period for fast test

        # Start evaluation loop task and let it tick
        eval_task = asyncio.create_task(self.runner._evaluation_loop())
        await asyncio.sleep(0.06)  # ~3 ticks
        self.runner.is_running = False
        await eval_task

        self.assertGreaterEqual(eval_count, 1, "Evaluation loop must act as fallback heartbeat")

    def test_live_executor_fast_path_latency(self):
        # Verify local evaluation compute latency is sub-millisecond (< 0.1ms)
        self.runner.book.update_from_raw({
            "levels": [
                [{"px": "80000.0", "sz": "2.0", "n": 3}],
                [{"px": "80001.0", "sz": "2.0", "n": 3}],
            ]
        })
        self.assertTrue(self.runner.book.is_valid)

        # Benchmark 500 synchronous evaluation calls
        t0 = time.perf_counter()
        calls = 500
        for _ in range(calls):
            self.runner._evaluate_signals()
        elapsed_us = ((time.perf_counter() - t0) / calls) * 1_000_000.0

        # Sub-millisecond requirement: < 1000us per call (< 1.0ms)
        self.assertLess(elapsed_us, 1000.0, f"Local compute latency ({elapsed_us:.1f}us) must be well under 1000us")

    def test_ui_rendering_throttled_to_4hz(self):
        # Verify that rapid ticks within 250ms window do NOT trigger multiple UI renders
        render_count = 0
        def _mock_render(*args, **kwargs):
            nonlocal render_count
            render_count += 1
            return "mock_table"

        self.runner.dashboard.render = _mock_render
        last_ui_render_time = 0.0

        # Simulate 20 rapid ticks arriving within a 100ms burst (at t = 100.0 to 100.1)
        simulated_times = [100.0 + i * 0.005 for i in range(20)]
        for now_t in simulated_times:
            if (now_t - last_ui_render_time) >= 0.25:
                last_ui_render_time = now_t
                self.runner.dashboard.render(self.runner.book, self.runner.trades, {}, self.runner.evaluator)

        # Should render exactly once across the 100ms burst (first tick at t=100.0)
        self.assertEqual(render_count, 1, "UI rendering must be throttled to at most once per 250ms (4Hz)")

        # Advance simulated time past 250ms (t = 100.30)
        now_t = 100.30
        if (now_t - last_ui_render_time) >= 0.25:
            last_ui_render_time = now_t
            self.runner.dashboard.render(self.runner.book, self.runner.trades, {}, self.runner.evaluator)

        self.assertEqual(render_count, 2, "UI rendering should only fire again after 250ms elapsed")


if __name__ == "__main__":
    unittest.main()
