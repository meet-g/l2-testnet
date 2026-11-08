"""Unit tests verifying the forensic remediation fixes for WOBI_Maker and LiveOrderExecutor.

Verifies:
1. Dynamic Take-Profit & Momentum Exhaustion calibration for WOBI_Maker.
2. Passive touch maker quoting on SIGNAL_REVERSAL with dwell window before escalation.
3. Order modify rejection handling (triggers sync_state(force=True) instead of blind place_limit_order fallback).
4. Reduce-only exit order validation when flat (eliminates phantom rejections).
5. Dynamic whale_sz calibration relative to avg_level_depth and rolling CVD trade flow gating.
6. Core execution strategies remain strictly disabled in strategies.json.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from config import AppConfig, DEFAULT_STRATEGIES_JSON
from core.orderbook import L2Level, OrderBook
from core.trade_stream import Trade, TradeManager
from engine.live_executor import LiveOrderExecutor
from signals.wobi import WOBISignal


class TestWOBIForensicRemediation(unittest.TestCase):
    def setUp(self):
        self.cfg = AppConfig()
        self.cfg.strategies.live_execution.priority_fee_bps = 0.0
        self.cfg.strategies.live_execution.force_market_orders = False
        with patch("engine.live_executor.eth_account.Account.from_key"), \
             patch("engine.live_executor.Info"), \
             patch("engine.live_executor.Exchange"):
            self.executor = LiveOrderExecutor(config=self.cfg, strategy_name="WOBI_Maker")
            self.executor.is_initialized = True
            self.executor.sz_decimals = 4
            self.executor.max_price_decimals = 2
            self.executor.coin = "BTC"

    def test_wobi_maker_config_calibration(self):
        """Verifies WOBI_Maker is calibrated with dynamic TP, exhaustion exit, and exit reversal threshold."""
        strat = self.cfg.strategies.get_strategy("WOBI_Maker")
        self.assertIsNotNone(strat)
        self.assertTrue(strat.dynamic_tp_enabled)
        self.assertEqual(strat.dynamic_tp_min_bps, 2.5)
        self.assertEqual(strat.dynamic_tp_max_bps, 6.0)
        self.assertTrue(strat.exhaustion_exit_enabled)
        self.assertEqual(strat.exhaustion_min_gain_bps, 2.0)
        self.assertEqual(strat.exhaustion_score_threshold, 0.15)
        self.assertEqual(strat.exit_reversal_threshold, 0.75)
        self.assertTrue(strat.require_cvd_alignment)

        # Check default strategies JSON in config
        default_wobi = DEFAULT_STRATEGIES_JSON["scalping_strategies"]["WOBI_Maker"]
        self.assertTrue(default_wobi["dynamic_tp_enabled"])
        self.assertEqual(default_wobi["dynamic_tp_min_bps"], 2.5)
        self.assertEqual(default_wobi["dynamic_tp_max_bps"], 6.0)
        self.assertTrue(default_wobi["exhaustion_exit_enabled"])
        self.assertEqual(default_wobi["exit_reversal_threshold"], 0.75)

    def test_core_execution_strategies_disabled_in_strategies_json(self):
        """Constraint verification: all 4 core execution strategies must remain strictly disabled."""
        strategies_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "strategies.json")
        with open(strategies_path, "r") as f:
            data = json.load(f)

        exec_strats = data.get("execution_strategies", {})
        for name in ("Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion", "Queue_Replenishment"):
            self.assertIn(name, exec_strats)
            self.assertFalse(
                exec_strats[name].get("enabled", True),
                f"Core execution strategy {name} must be disabled ('enabled': false) in strategies.json",
            )

    def test_reversal_exit_quotes_passive_maker_order_long(self):
        """Verifies SIGNAL_REVERSAL for long position places a passive maker order (post_only=True) at best ask."""
        self.executor.cached_position = 0.5
        self.executor.entry_price = 100.0
        self.executor.position_strategy = "WOBI_Maker"
        self.executor.force_market_orders = False

        placed_orders = []
        self.executor.place_limit_order = MagicMock(side_effect=lambda **kwargs: placed_orders.append(kwargs) or {"status": "ok"})

        # Long position: entry = 100.0. Best bid = 99.90, best ask = 100.0 -> mid = 99.95 (gain_bps = -5.0 bps)
        # Signal score = -0.80 (exceeds reversal threshold -0.75) -> triggers SIGNAL_REVERSAL
        self.executor.on_signal_update(
            signal_score=-0.80,
            best_bid=99.90,
            best_ask=100.0,
            spread=0.10,
        )

        self.assertEqual(len(placed_orders), 1)
        order = placed_orders[0]
        self.assertFalse(order["is_buy"])  # Sell to exit long
        self.assertTrue(order["post_only"])  # Must be passive maker quote
        self.assertTrue(order["is_exit"])
        self.assertEqual(order["exit_reason"], "SIGNAL_REVERSAL")
        # Spread is wide (0.10 > 0.015): spread-improves by 1 tick inside spread (99.99) for FIFO queue priority
        self.assertEqual(order["price"], 99.99)

    def test_reversal_exit_quotes_passive_maker_order_short(self):
        """Verifies SIGNAL_REVERSAL for short position places a passive maker order (post_only=True) at best bid."""
        self.executor.cached_position = -0.5
        self.executor.entry_price = 100.0
        self.executor.position_strategy = "WOBI_Maker"
        self.executor.force_market_orders = False

        placed_orders = []
        self.executor.place_limit_order = MagicMock(side_effect=lambda **kwargs: placed_orders.append(kwargs) or {"status": "ok"})

        # Short position: entry = 100.0. Best bid = 100.0, best ask = 100.10 -> mid = 100.05 (gain_bps = -5.0 bps)
        # Signal score = +0.80 (exceeds reversal threshold +0.75) -> triggers SIGNAL_REVERSAL
        self.executor.on_signal_update(
            signal_score=0.80,
            best_bid=100.0,
            best_ask=100.10,
            spread=0.10,
        )

        self.assertEqual(len(placed_orders), 1)
        order = placed_orders[0]
        self.assertTrue(order["is_buy"])  # Buy to exit short
        self.assertTrue(order["post_only"])  # Must be passive maker quote
        self.assertTrue(order["is_exit"])
        self.assertEqual(order["exit_reason"], "SIGNAL_REVERSAL")
        # Spread is wide (0.10 > 0.015): spread-improves by 1 tick inside spread (100.01) for FIFO queue priority
        self.assertEqual(order["price"], 100.01)

    def test_wobi_momentum_exhaustion_exit(self):
        """Verifies Dynamic TP Momentum Exhaustion exit takes profit early when gain >= 2.0 bps and score <= 0.15."""
        self.executor.cached_position = 0.5
        self.executor.entry_price = 100.0
        self.executor.position_strategy = "WOBI_Maker"
        self.executor.force_market_orders = False

        placed_orders = []
        self.executor.place_limit_order = MagicMock(side_effect=lambda **kwargs: placed_orders.append(kwargs) or {"status": "ok"})

        # Long position: entry = 100.0. Best bid = 100.02, best ask = 100.04 -> mid = 100.03 (gain = +3.0 bps >= 2.0 bps)
        # Signal score = 0.10 <= 0.15 (score threshold) -> triggers EXHAUSTION_EXIT
        self.executor.on_signal_update(
            signal_score=0.10,
            best_bid=100.02,
            best_ask=100.04,
            spread=0.02,
        )

        self.assertEqual(len(placed_orders), 1)
        order = placed_orders[0]
        self.assertFalse(order["is_buy"])
        self.assertTrue(order["post_only"])
        self.assertTrue(order["is_exit"])
        self.assertEqual(order["exit_reason"], "EXHAUSTION_EXIT")

    def test_reversal_exit_dwell_window_and_escalation(self):
        """Verifies that an unfilled reversal quote rests during dwell window, then escalates to market cross."""
        import time
        now = time.time()
        self.executor.cached_position = 0.5
        self.executor.entry_price = 100.0
        self.executor.position_strategy = "WOBI_Maker"
        self.executor.force_market_orders = False

        # Resting exit quote placed at best_ask = 100.0 (gain_bps = -5.0 bps)
        self.executor.active_order = {
            "oid": 8801,
            "is_buy": False,
            "price": 100.0,
            "size": 0.5,
            "time": now - 1.0,
            "is_exit": True,
            "strategy_name": "WOBI_Maker",
            "pending": False,
        }

        modified_orders = []
        self.executor.modify_limit_order = MagicMock(side_effect=lambda **kwargs: modified_orders.append(kwargs) or {"status": "ok"})
        self.executor.place_limit_order = MagicMock()

        # Tick 1: age = 1.0s < exit_escalate_secs (2.0s), price matches -> KEEP RESTING
        self.executor.on_signal_update(
            signal_score=-0.80,
            best_bid=99.90,
            best_ask=100.0,
            spread=0.10,
        )
        self.executor.modify_limit_order.assert_not_called()
        self.executor.place_limit_order.assert_not_called()

        # Tick 2: age = 2.5s >= exit_escalate_secs (2.0s) -> ESCALATE to market cross at best_bid
        self.executor.active_order["time"] = now - 2.5
        self.executor.on_signal_update(
            signal_score=-0.80,
            best_bid=99.90,
            best_ask=100.0,
            spread=0.10,
        )
        self.assertEqual(len(modified_orders), 1)
        mod = modified_orders[0]
        self.assertEqual(mod["oid"], 8801)
        self.assertEqual(mod["price"], 99.90)  # Crosses spread at best bid
        self.assertFalse(mod["post_only"])  # Taker escalation
        self.assertEqual(mod["exit_reason"], "REVERSAL_ESCALATE")

    def test_modify_order_rejection_triggers_sync_state_not_fresh_order(self):
        """Verifies rejected order modify calls sync_state(force=True) and does NOT place a fresh order."""
        mock_exchange = MagicMock()
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = False
        self.executor.active_order_oids = [7001]
        self.executor.active_order = {"oid": 7001, "pending": False}
        self.executor.sync_state = MagicMock()
        self.executor.place_limit_order = MagicMock()

        # Simulate exchange error: order does not exist or already filled
        mock_exchange.modify_order.return_value = {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"error": "Order does not exist or was already filled."}]},
            },
        }

        res = self.executor.modify_limit_order(
            oid=7001,
            is_buy=True,
            size_btc=0.1,
            price=80000.0,
            post_only=True,
            strategy_name="WOBI_Maker",
        )

        self.assertIsNotNone(res)
        self.assertIsNone(self.executor.active_order)
        self.assertNotIn(7001, self.executor.active_order_oids)
        # CRITICAL GUARD: sync_state(force=True) must be called, and NO fresh order placed
        self.executor.sync_state.assert_called_with(force=True)
        self.executor.place_limit_order.assert_not_called()

    def test_modify_order_status_err_triggers_sync_state(self):
        """Verifies modify returning status='err' triggers sync_state(force=True) without placing fresh order."""
        mock_exchange = MagicMock()
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = False
        self.executor.active_order_oids = [7002]
        self.executor.active_order = {"oid": 7002, "pending": False}
        self.executor.sync_state = MagicMock()
        self.executor.place_limit_order = MagicMock()

        mock_exchange.modify_order.return_value = {
            "status": "err",
            "response": "Order cancel failed: unknown order",
        }

        res = self.executor.modify_limit_order(
            oid=7002,
            is_buy=True,
            size_btc=0.1,
            price=80000.0,
            post_only=True,
            strategy_name="WOBI_Maker",
        )

        self.assertIsNone(self.executor.active_order)
        self.assertNotIn(7002, self.executor.active_order_oids)
        self.executor.sync_state.assert_called_with(force=True)
        self.executor.place_limit_order.assert_not_called()

    def test_reduce_only_guard_when_flat_in_place_and_modify(self):
        """Verifies reduce-only order is aborted locally when flat (abs(cached_position) <= 1e-6)."""
        mock_exchange = MagicMock()
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = False
        self.executor.cached_position = 0.0  # Flat!

        # Attempt to place exit order when flat
        place_res = self.executor.place_limit_order(
            is_buy=False,
            size_btc=0.1,
            price=80000.0,
            is_exit=True,
            reduce_only=True,
            strategy_name="WOBI_Maker",
        )
        self.assertIsNone(place_res)
        mock_exchange.order.assert_not_called()

        # Attempt to modify order as reduce_only when flat
        modify_res = self.executor.modify_limit_order(
            oid=7003,
            is_buy=False,
            size_btc=0.1,
            price=80000.0,
            is_exit=True,
            reduce_only=True,
            strategy_name="WOBI_Maker",
        )
        self.assertIsNone(modify_res)
        mock_exchange.modify_order.assert_not_called()

    def test_orderbook_avg_level_depth(self):
        """Verifies OrderBook.avg_level_depth computes correct average volume per level."""
        book = OrderBook(coin="HYPE", enable_history=False)
        book.bids = [
            L2Level(px=30.0, sz=20.0, n=5),
            L2Level(px=29.9, sz=30.0, n=8),
        ]
        book.asks = [
            L2Level(px=30.1, sz=10.0, n=4),
            L2Level(px=30.2, sz=40.0, n=12),
        ]
        # (20 + 30 + 10 + 40) / (2 * 2) = 100 / 4 = 25.0
        avg_depth = book.avg_level_depth(2)
        self.assertAlmostEqual(avg_depth, 25.0)

    def test_wobi_adaptive_anti_spoofing_dynamic_whale_sz(self):
        """Verifies WOBISignal calculates whale_sz dynamically off avg_level_depth and penalizes whale wall."""
        book = OrderBook(coin="HYPE", enable_history=False)
        # Average depth per level is 10.0
        # Dynamic whale_sz = max(10.0, 10.0 * 3.0) = 30.0
        book.bids = [
            L2Level(px=30.0, sz=10.0, n=5),
            L2Level(px=29.9, sz=50.0, n=1),  # Whale wall: sz=50 >= 30, n=1 <= 2 -> penalized!
        ]
        book.asks = [
            L2Level(px=30.1, sz=10.0, n=5),
            L2Level(px=30.2, sz=10.0, n=5),
        ]
        trades = TradeManager(coin="HYPE")
        signal = WOBISignal(whale_min_sz=10.0)
        res = signal.compute(book, trades)

        self.assertIn("whale_sz", res.metadata)
        self.assertEqual(res.metadata["whale_sz"], 60.0)  # total_vol=80, 2 levels -> avg=20, 20*3=60.0
        self.assertIn("avg_level_depth", res.metadata)
        self.assertEqual(res.metadata["avg_level_depth"], 20.0)

    def test_wobi_cvd_trade_flow_gating(self):
        """Verifies WOBISignal gates entries against opposing rolling trade flow (CVD)."""
        book = OrderBook(coin="BTC", enable_history=False)
        # Strong bid-heavy book imbalance (would normally yield score > 0.8)
        book.bids = [L2Level(px=80000.0, sz=5.0, n=10)]
        book.asks = [L2Level(px=80001.0, sz=0.5, n=2)]

        trades = TradeManager(coin="BTC")
        # Simulate heavy aggressive sell trades in the last 10s (CVD = -15.0 BTC)
        now_ms = 1_000_000
        for i in range(5):
            trades.trades.append(Trade(
                timestamp_ms=now_ms - 2000,
                price=80000.0,
                size=3.0,
                side="A",  # Aggressive Sell
                hash=f"0x{i}",
            ))

        signal = WOBISignal(require_cvd_alignment=True, cvd_window_secs=30.0)
        res = signal.compute(book, trades, timestamp_ms=now_ms)

        # Signal score must be suppressed to <= 0.20 due to negative CVD gating
        self.assertLessEqual(res.score, 0.20)
        self.assertTrue(res.metadata["cvd_suppressed"])
        self.assertIn("Negative CVD trade flow", res.metadata["suppression_reason"])

    def test_reversal_exit_reanchors_existing_take_profit_quote_with_fresh_dwell_window(self):
        """Verifies that if an order was already resting for TAKE_PROFIT (>2s), SIGNAL_REVERSAL does NOT immediately

        escalate to a market taker cross, but re-anchors to touch (post_only=True) and allows a full dwell window.
        """
        import time
        now = time.time()
        self.executor.cached_position = 0.5
        self.executor.entry_price = 100.0
        self.executor.position_strategy = "WOBI_Maker"
        self.executor.force_market_orders = False

        # Resting TP exit quote placed 5.0 seconds ago at $100.10
        self.executor.active_order = {
            "oid": 8802,
            "is_buy": False,
            "price": 100.10,
            "size": 0.5,
            "time": now - 5.0,  # Resting > exit_escalate_secs (2.0s)
            "is_exit": True,
            "strategy_name": "WOBI_Maker",
            "pending": False,
            "exit_reason": "TAKE_PROFIT",
        }

        modified_orders = []
        self.executor.modify_limit_order = MagicMock(
            side_effect=lambda **kwargs: modified_orders.append(kwargs) or {"status": "ok"}
        )
        self.executor.place_limit_order = MagicMock()

        # Tick 1: Reversal signal triggers (-0.80 <= -0.75).
        # MUST NOT escalate to market taker cross! MUST re-anchor quote to touch as passive maker!
        self.executor.on_signal_update(
            signal_score=-0.80,
            best_bid=99.90,
            best_ask=100.0,
            spread=0.10,
        )

        self.assertEqual(len(modified_orders), 1)
        mod = modified_orders[0]
        self.assertEqual(mod["oid"], 8802)
        self.assertTrue(mod["post_only"])  # MUST BE PASSIVE MAKER
        self.assertEqual(mod["exit_reason"], "SIGNAL_REVERSAL")
        self.assertEqual(self.executor.active_order["exit_reason"], "SIGNAL_REVERSAL")
        # Dwell timer must be reset to now
        self.assertAlmostEqual(self.executor.active_order["time"], now, delta=0.5)

        # Tick 2: 1.0s later (< 2.0s dwell window) -> KEEP RESTING as maker, NO taker escalation
        modified_orders.clear()
        self.executor.active_order["time"] = now - 1.0
        self.executor.active_order["price"] = mod["price"]
        self.executor.on_signal_update(
            signal_score=-0.80,
            best_bid=99.90,
            best_ask=100.0,
            spread=0.10,
        )
        self.assertEqual(len(modified_orders), 0)  # Still resting passively!

        # Tick 3: 2.5s later (>= 2.0s dwell window elapsed) -> ESCALATE to market cross at best_bid
        self.executor.active_order["time"] = now - 2.5
        self.executor.on_signal_update(
            signal_score=-0.80,
            best_bid=99.90,
            best_ask=100.0,
            spread=0.10,
        )
        self.assertEqual(len(modified_orders), 1)
        mod_esc = modified_orders[0]
        self.assertFalse(mod_esc["post_only"])  # Taker escalation
        self.assertEqual(mod_esc["price"], 99.90)  # Crossing spread at best_bid
        self.assertEqual(mod_esc["exit_reason"], "REVERSAL_ESCALATE")

    def test_reversal_exit_reanchors_existing_take_profit_quote_short(self):
        """Verifies symmetric re-anchoring of resting TP quote on SIGNAL_REVERSAL for SHORT position."""
        import time
        now = time.time()
        self.executor.cached_position = -0.5
        self.executor.entry_price = 100.0
        self.executor.position_strategy = "WOBI_Maker"
        self.executor.force_market_orders = False

        # Resting TP exit quote placed 4.0 seconds ago at $99.90
        self.executor.active_order = {
            "oid": 8803,
            "is_buy": True,
            "price": 99.90,
            "size": 0.5,
            "time": now - 4.0,  # Resting > 2.0s
            "is_exit": True,
            "strategy_name": "WOBI_Maker",
            "pending": False,
            "exit_reason": "TAKE_PROFIT",
        }

        modified_orders = []
        self.executor.modify_limit_order = MagicMock(
            side_effect=lambda **kwargs: modified_orders.append(kwargs) or {"status": "ok"}
        )

        # Bullish reversal triggers against short position (0.80 >= 0.75)
        self.executor.on_signal_update(
            signal_score=0.80,
            best_bid=100.0,
            best_ask=100.10,
            spread=0.10,
        )

        self.assertEqual(len(modified_orders), 1)
        mod = modified_orders[0]
        self.assertEqual(mod["oid"], 8803)
        self.assertTrue(mod["post_only"])  # MUST BE PASSIVE MAKER
        self.assertEqual(mod["exit_reason"], "SIGNAL_REVERSAL")
        self.assertEqual(self.executor.active_order["exit_reason"], "SIGNAL_REVERSAL")
        self.assertAlmostEqual(self.executor.active_order["time"], now, delta=0.5)

    def test_modify_limit_order_retains_exit_reason_in_active_order(self):
        """Verifies modify_limit_order stores and retains exit_reason in self.active_order upon successful response."""
        mock_exchange = MagicMock()
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = False
        self.executor.active_order_oids = [9001]
        self.executor.cached_position = 0.5

        mock_exchange.modify_order.return_value = {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"resting": {"oid": 9002}}]},
            },
        }

        res = self.executor.modify_limit_order(
            oid=9001,
            is_buy=False,
            size_btc=0.5,
            price=100.0,
            post_only=True,
            is_exit=True,
            strategy_name="WOBI_Maker",
            exit_reason="SIGNAL_REVERSAL",
        )

        self.assertIsNotNone(res)
        self.assertIsNotNone(self.executor.active_order)
        self.assertEqual(self.executor.active_order["oid"], 9002)
        self.assertEqual(self.executor.active_order["exit_reason"], "SIGNAL_REVERSAL")

    def test_wobi_cvd_gating_uninitialized_book_timestamp(self):
        """Verifies WOBISignal correctly falls back to None instead of 0 when book.last_update_time_ms is 0."""
        book = OrderBook(coin="BTC", enable_history=False)
        book.bids = [L2Level(px=80000.0, sz=5.0, n=10)]
        book.asks = [L2Level(px=80001.0, sz=0.5, n=2)]
        book.last_update_time_ms = 0  # Uninitialized!

        trades = TradeManager(coin="BTC")
        # compute without timestamp_ms and with book.last_update_time_ms=0
        signal = WOBISignal(require_cvd_alignment=True, cvd_window_secs=30.0)
        res = signal.compute(book, trades, timestamp_ms=None)
        self.assertIsNotNone(res)
        self.assertGreater(res.timestamp_ms, 0)

    def test_trailing_stop_executes_as_ioc_taker_exit(self):
        """Verifies trailing stop executes as an immediate IOC taker order (post_only=False, tif='Ioc')."""
        self.executor.cached_position = 0.5
        self.executor.entry_price = 100.0
        self.executor.peak_price = 100.05  # +5 bps excursion
        self.executor.peak_unrealized_bps = 5.0
        self.executor.trailing_stop_active = True
        self.executor.position_strategy = "WOBI_Maker"
        self.executor.force_market_orders = False

        placed_orders = []
        self.executor.place_limit_order = MagicMock(
            side_effect=lambda **kwargs: placed_orders.append(kwargs) or {"status": "ok"}
        )

        # Price dropped to 100.01 (gain decayed from +5 bps to +1 bps, breaching trail_floor)
        self.executor.on_signal_update(
            signal_score=0.20,
            best_bid=100.00,
            best_ask=100.02,
            spread=0.02,
        )

        self.assertEqual(len(placed_orders), 1)
        order = placed_orders[0]
        self.assertFalse(order["is_buy"])  # Sell to exit long
        self.assertFalse(order["post_only"])  # MUST be taker order (not passive maker)
        self.assertEqual(order["tif"], "Ioc")  # Immediate or cancel
        self.assertEqual(order["exit_reason"], "TRAILING_STOP")

    def test_profit_decay_exit_long(self):
        """Verifies profit decay exit triggers on long position when peak >= 3.5 bps and gain <= 0.5 bps."""
        self.executor.cached_position = 0.5
        self.executor.entry_price = 100.0
        self.executor.max_price_decimals = 3
        self.executor.peak_unrealized_bps = 3.6  # Exceeded 3.5 bps peak
        self.executor.position_strategy = "WOBI_Maker"
        self.executor.force_market_orders = False

        placed_orders = []
        self.executor.place_limit_order = MagicMock(
            side_effect=lambda **kwargs: placed_orders.append(kwargs) or {"status": "ok"}
        )

        # Gain decayed to +0.2 bps (mid = 100.002) and signal collapsed to -0.05 (<= 0.0)
        self.executor.on_signal_update(
            signal_score=-0.05,
            best_bid=99.992,
            best_ask=100.012,
            spread=0.02,
        )

        self.assertEqual(len(placed_orders), 1)
        order = placed_orders[0]
        self.assertFalse(order["is_buy"])
        self.assertFalse(order["post_only"])
        self.assertEqual(order["tif"], "Ioc")
        self.assertEqual(order["exit_reason"], "PROFIT_DECAY_EXIT")

    def test_profit_decay_exit_short(self):
        """Verifies profit decay exit triggers on short position when peak >= 3.5 bps and gain <= 0.5 bps."""
        self.executor.cached_position = -0.5
        self.executor.entry_price = 100.0
        self.executor.max_price_decimals = 3
        self.executor.peak_unrealized_bps = 3.6
        self.executor.position_strategy = "WOBI_Maker"
        self.executor.force_market_orders = False

        placed_orders = []
        self.executor.place_limit_order = MagicMock(
            side_effect=lambda **kwargs: placed_orders.append(kwargs) or {"status": "ok"}
        )

        # Gain decayed to +0.2 bps (mid = 99.998) and signal flipped bullish to +0.05 (>= 0.0)
        self.executor.on_signal_update(
            signal_score=0.05,
            best_bid=99.988,
            best_ask=100.008,
            spread=0.02,
        )

        self.assertEqual(len(placed_orders), 1)
        order = placed_orders[0]
        self.assertTrue(order["is_buy"])
        self.assertFalse(order["post_only"])
        self.assertEqual(order["tif"], "Ioc")
        self.assertEqual(order["exit_reason"], "PROFIT_DECAY_EXIT")

    def test_time_limit_exit(self):
        """Verifies holding time limit triggers exit when holding exceeds max_holding_time_secs with flat/negative gain."""
        import time
        now = time.time()
        self.executor.cached_position = 0.5
        self.executor.entry_price = 100.0
        self.executor.entry_time_ms = int((now - 200.0) * 1000)  # Held for 200s (> 180s max hold)
        self.executor.position_strategy = "WOBI_Maker"
        self.executor.force_market_orders = False

        placed_orders = []
        self.executor.place_limit_order = MagicMock(
            side_effect=lambda **kwargs: placed_orders.append(kwargs) or {"status": "ok"}
        )

        # Price flat at 100.0, signal neutral (0.05 <= 0.10)
        self.executor.on_signal_update(
            signal_score=0.05,
            best_bid=99.99,
            best_ask=100.01,
            spread=0.02,
        )

        self.assertEqual(len(placed_orders), 1)
        order = placed_orders[0]
        self.assertFalse(order["is_buy"])
        self.assertTrue(order["is_exit"])
        self.assertEqual(order["exit_reason"], "TIME_LIMIT")

    def test_stale_rest_position_guard_ignores_szi_after_local_exit(self):
        """Verifies _do_sync ignores non-zero REST szi within 5s of a local exit fill to avoid duplicate stop losses."""
        import time
        now = time.time()
        mock_info = MagicMock()
        self.executor.info = mock_info
        self.executor.cached_position = 0.0  # Local position already 0.0 after fill
        self.executor.last_fill_time = now  # Fill occurred just now!
        self.executor.entry_price = 0.0
        self.executor.active_order = None

        # Exchange REST API still reports stale position of 0.335
        mock_info.user_state.return_value = {
            "assetPositions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "0.335",
                        "entryPx": "100.0",
                    }
                }
            ],
            "marginSummary": {"accountValue": "1000.0", "totalMarginUsed": "0.0"},
            "withdrawable": "1000.0",
        }
        mock_info.open_orders.return_value = []

        self.executor._do_sync(now=now)

        # cached_position must remain 0.0 (NOT clobbered to 0.335!)
        self.assertEqual(self.executor.cached_position, 0.0)
        # No phantom trade should be recorded
        self.assertEqual(len(self.executor.completed_trades), 0)

    def test_dynamic_spread_compute_handles_none_trades(self):
        """Verifies DynamicSpreadSignal handles trades=None cleanly without exception."""
        from signals.dynamic_spread import DynamicSpreadSignal
        book = OrderBook(coin="BTC", enable_history=False)
        book.bids = [L2Level(px=100.0, sz=5.0, n=5)]
        book.asks = [L2Level(px=100.1, sz=5.0, n=5)]
        book.last_update_time_ms = 1_000_000

        signal = DynamicSpreadSignal()
        res = signal.compute(book, trades=None, timestamp_ms=1_000_000)
        self.assertIsNotNone(res)
        self.assertIsInstance(res.score, float)
        self.assertEqual(res.metadata["s_flow"], 0.0)


if __name__ == "__main__":
    unittest.main()
