"""Comprehensive unit tests for Hyperliquid Native TP/SL Bracket Architecture:
1. Slippage buffer calculation on market stop triggers (5-10% buffer to guarantee execution).
2. on_signal_update wiring of native bracket orders with hybrid protective architecture (+25 bps TP, configured SL).
3. Partial-fill watchdog & position-level trigger dispatch (grouping="positionTpsl").
4. Child trigger purging on early exits (DEFENSIVE_HEDGE, SIGNAL_REVERSAL, PROFIT_DECAY_EXIT, position close).
"""

import unittest
from unittest.mock import MagicMock, patch, call
from config import AppConfig, LiveExecutionConfig
from engine.live_executor import LiveOrderExecutor


class TestNativeBracketArchitecture(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.config.account.account_address = "0x76cfd21f8a84c670b09489d7b9015c92c4222416"
        self.config.account.secret_key = "0x" + "1" * 64
        self.config.market.coin = "BTC"
        self.config.live_execution = LiveExecutionConfig(
            active_strategy="WOBI_Maker",
            order_size_btc=0.05,
            penny_jumping=True,
            use_ioc_on_marketable=True,
            use_native_tpsl=True,
            priority_fee_bps=0.0,
            force_market_orders=False,
            market_slippage_pct=0.0005,
        )

    # -------------------------------------------------------------------------
    # 1. Slippage Buffer Calculation in place_bracket_order
    # -------------------------------------------------------------------------
    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_bracket_slippage_calculation_long_entry(self, mock_info, mock_exchange):
        """Verifies Long entry bracket: SL limit_px is 5% below triggerPx, TP limit_px is 5% below triggerPx."""
        mock_ex = mock_exchange.return_value
        mock_ex.bulk_orders.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 1001}}, {"resting": {"oid": 1002}}, {"resting": {"oid": 1003}}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex

        # Long entry at 80,000, emergency TP at 80,200 (+25 bps), SL at 79,900 (-12.5 bps)
        executor.place_bracket_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            tp_price=80200.0,
            sl_price=79900.0,
            post_only=True,
            emergency_slippage=0.05,
        )

        mock_ex.bulk_orders.assert_called_once()
        orders, kwargs = mock_ex.bulk_orders.call_args
        order_list = orders[0]
        self.assertEqual(len(order_list), 3)

        entry_order, tp_order, sl_order = order_list[0], order_list[1], order_list[2]

        # Entry order is buy
        self.assertTrue(entry_order["is_buy"])
        self.assertEqual(entry_order["limit_px"], 80000.0)

        # TP order is sell (exit_side = False)
        self.assertFalse(tp_order["is_buy"])
        self.assertTrue(tp_order["reduce_only"])
        self.assertEqual(tp_order["order_type"]["trigger"]["triggerPx"], 80200.0)
        # TP limit_px has 5% slippage buffer below trigger: 80200 * 0.95 = 76190.0
        expected_tp_limit = executor.format_price(80200.0 * 0.95)
        self.assertEqual(tp_order["limit_px"], expected_tp_limit)

        # SL order is sell (exit_side = False)
        self.assertFalse(sl_order["is_buy"])
        self.assertTrue(sl_order["reduce_only"])
        self.assertTrue(sl_order["order_type"]["trigger"]["isMarket"])
        self.assertEqual(sl_order["order_type"]["trigger"]["triggerPx"], 79900.0)
        # SL limit_px has 5% emergency slippage buffer below trigger: 79900 * 0.95 = 75905.0
        expected_sl_limit = executor.format_price(79900.0 * 0.95)
        self.assertEqual(sl_order["limit_px"], expected_sl_limit)
        self.assertLess(sl_order["limit_px"], sl_order["order_type"]["trigger"]["triggerPx"])

        # Grouping must be normalTpsl
        self.assertEqual(kwargs.get("grouping"), "normalTpsl")

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_bracket_slippage_calculation_short_entry(self, mock_info, mock_exchange):
        """Verifies Short entry bracket: SL limit_px is 10% above triggerPx (buying to cover)."""
        mock_ex = mock_exchange.return_value
        mock_ex.bulk_orders.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 2001}}, {"resting": {"oid": 2002}}, {"resting": {"oid": 2003}}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex

        # Short entry at 80,000, emergency TP at 79,800 (-25 bps), SL at 80,100 (+12.5 bps)
        executor.place_bracket_order(
            is_buy=False,
            size_btc=0.05,
            price=80000.0,
            tp_price=79800.0,
            sl_price=80100.0,
            post_only=True,
            emergency_slippage=0.10,  # 10% slippage
        )

        mock_ex.bulk_orders.assert_called_once()
        orders, kwargs = mock_ex.bulk_orders.call_args
        order_list = orders[0]
        entry_order, tp_order, sl_order = order_list[0], order_list[1], order_list[2]

        # Entry order is sell
        self.assertFalse(entry_order["is_buy"])
        self.assertEqual(entry_order["limit_px"], 80000.0)

        # TP order is buy (exit_side = True)
        self.assertTrue(tp_order["is_buy"])
        self.assertTrue(tp_order["reduce_only"])
        self.assertEqual(tp_order["order_type"]["trigger"]["triggerPx"], 79800.0)
        expected_tp_limit = executor.format_price(79800.0 * 1.10)
        self.assertEqual(tp_order["limit_px"], expected_tp_limit)

        # SL order is buy (exit_side = True)
        self.assertTrue(sl_order["is_buy"])
        self.assertTrue(sl_order["reduce_only"])
        self.assertEqual(sl_order["order_type"]["trigger"]["triggerPx"], 80100.0)
        # SL limit_px has 10% emergency slippage buffer above trigger: 80100 * 1.10 = 88110.0
        expected_sl_limit = executor.format_price(80100.0 * 1.10)
        self.assertEqual(sl_order["limit_px"], expected_sl_limit)
        self.assertGreater(sl_order["limit_px"], sl_order["order_type"]["trigger"]["triggerPx"])

    # -------------------------------------------------------------------------
    # 2. Wire Native Brackets into Live Order Execution (on_signal_update)
    # -------------------------------------------------------------------------
    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_on_signal_update_wires_native_bracket_bullish_and_bearish(self, mock_info, mock_exchange):
        """Verifies on_signal_update invokes place_bracket_order with emergency TP (+25 bps) and SL."""
        mock_ex = mock_exchange.return_value
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.use_native_tpsl = True
        executor.cached_position = 0.0

        placed_brackets = []

        def mock_place_bracket(*args, **kwargs):
            placed_brackets.append(kwargs)
            return {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 3001}}]}}}

        executor.place_bracket_order = mock_place_bracket

        # Bullish entry signal
        executor.on_signal_update(
            signal_score=0.85,
            best_bid=80000.0,
            best_ask=80001.0,
            spread=1.0,
        )

        self.assertEqual(len(placed_brackets), 1)
        b_entry = placed_brackets[0]
        self.assertTrue(b_entry["is_buy"])
        self.assertEqual(b_entry["price"], 80000.0)
        # Emergency TP should be +25 bps -> 80000 * (1 + 25/10000) = 80200.0
        self.assertEqual(b_entry["tp_price"], executor.format_price(80000.0 * 1.0025))
        # SL price should be at configured stop_loss_bps (e.g. 8.0 or 10.0 bps)
        self.assertLess(b_entry["sl_price"], 80000.0)

        # Clear and test Bearish entry signal
        placed_brackets.clear()
        executor.active_order = None
        executor.cached_position = 0.0

        executor.on_signal_update(
            signal_score=-0.85,
            best_bid=80000.0,
            best_ask=80001.0,
            spread=1.0,
        )

        self.assertEqual(len(placed_brackets), 1)
        s_entry = placed_brackets[0]
        self.assertFalse(s_entry["is_buy"])
        self.assertEqual(s_entry["price"], 80001.0)
        # Emergency TP should be -25 bps -> 80001 * (1 - 25/10000) = 79800.99
        self.assertEqual(s_entry["tp_price"], executor.format_price(80001.0 * (1.0 - 0.0025)))
        # SL price should be above 80001.0
        self.assertGreater(s_entry["sl_price"], 80001.0)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_on_signal_update_fallback_when_use_native_tpsl_false(self, mock_info, mock_exchange):
        """When use_native_tpsl is False, on_signal_update falls back to standard place_limit_order."""
        mock_ex = mock_exchange.return_value
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.use_native_tpsl = False
        executor.cached_position = 0.0

        limit_calls = []

        def mock_place_limit(*args, **kwargs):
            limit_calls.append(kwargs)
            return {"status": "ok"}

        executor.place_limit_order = mock_place_limit

        executor.on_signal_update(
            signal_score=0.85,
            best_bid=80000.0,
            best_ask=80001.0,
            spread=1.0,
        )

        self.assertEqual(len(limit_calls), 1)
        self.assertTrue(limit_calls[0]["is_buy"])
        self.assertFalse(limit_calls[0]["is_exit"])

    # -------------------------------------------------------------------------
    # 3. Partial-Fill Watchdog & Position-Level Trigger (positionTpsl)
    # -------------------------------------------------------------------------
    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_dispatch_position_tpsl_grouping(self, mock_info, mock_exchange):
        """Verifies dispatch_position_tpsl submits orders with grouping='positionTpsl' and correct slippage."""
        mock_ex = mock_exchange.return_value
        mock_ex.bulk_orders.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 4001}}, {"resting": {"oid": 4002}}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.cached_position = 0.05  # Long position of 0.05
        executor.entry_price = 80000.0

        res = executor.dispatch_position_tpsl(
            position_sz=0.05,
            tp_price=80200.0,
            sl_price=79900.0,
            strategy_name="WOBI_Maker",
            emergency_slippage=0.05,
        )

        self.assertIsNotNone(res)
        mock_ex.bulk_orders.assert_called_once()
        orders, kwargs = mock_ex.bulk_orders.call_args
        self.assertEqual(kwargs.get("grouping"), "positionTpsl")
        self.assertEqual(len(orders[0]), 2)  # TP and SL orders

        tp_order, sl_order = orders[0][0], orders[0][1]
        self.assertFalse(tp_order["is_buy"])  # Sell to close long
        self.assertFalse(sl_order["is_buy"])
        self.assertEqual(tp_order["order_type"]["trigger"]["triggerPx"], 80200.0)
        self.assertEqual(sl_order["order_type"]["trigger"]["triggerPx"], 79900.0)
        # Both child triggers should be tracked in _tracked_trigger_oids
        self.assertIn(4001, executor._tracked_trigger_oids)
        self.assertIn(4002, executor._tracked_trigger_oids)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_cancel_order_with_partial_fill_triggers_position_tpsl(self, mock_info, mock_exchange):
        """When an order with partial fill (cum_size > 0) is canceled, cancel_order dispatches positionTpsl."""
        mock_ex = mock_exchange.return_value
        mock_ex.cancel.return_value = {"status": "ok"}
        mock_ex.bulk_orders.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 5001}}, {"resting": {"oid": 5002}}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.cached_position = 0.02  # Partial fill position
        executor.entry_price = 80000.0

        # Simulate active bracket entry order with partial fill
        executor.active_order = {
            "oid": 9999,
            "is_buy": True,
            "price": 80000.0,
            "size": 0.03,  # remaining
            "cum_size": 0.02,  # partially filled
            "is_bracket": True,
            "is_exit": False,
            "tp_price": 80200.0,
            "sl_price": 79900.0,
            "strategy_name": "WOBI_Maker",
        }
        executor.active_order_oids = [9999]

        with patch.object(executor, "dispatch_position_tpsl", wraps=executor.dispatch_position_tpsl) as spy_dispatch:
            res = executor.cancel_order(9999, non_blocking=False)
            self.assertTrue(res)
            mock_ex.cancel.assert_called_once_with("BTC", 9999)
            spy_dispatch.assert_called_once_with(
                position_sz=0.02,
                tp_price=80200.0,
                sl_price=79900.0,
                strategy_name="WOBI_Maker",
            )
            mock_ex.bulk_orders.assert_called_once()
            _, kwargs = mock_ex.bulk_orders.call_args
            self.assertEqual(kwargs.get("grouping"), "positionTpsl")

    # -------------------------------------------------------------------------
    # 4. Trigger Purging on Early Exits
    # -------------------------------------------------------------------------
    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_purge_child_trigger_orders_cancels_tracked_and_frontend_orders(self, mock_info, mock_exchange):
        """Verifies purge_child_trigger_orders purges tracked OIDs and frontend open orders with triggers."""
        mock_ex = mock_exchange.return_value
        mock_ex.cancel.return_value = {"status": "ok"}

        mock_in = mock_info.return_value
        # Mock frontend open orders returning a trigger order and an order with children
        mock_in.frontend_open_orders.return_value = [
            {
                "coin": "BTC",
                "oid": 6001,
                "isTrigger": True,
                "children": [{"oid": 6002}],
            },
            {
                "coin": "BTC",
                "oid": 7001,
                "isTrigger": False,
                "children": [],
            },
        ]

        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.info = mock_in
        executor.account_address = "0x76cfd21f8a84c670b09489d7b9015c92c4222416"

        # Add a tracked trigger OID
        executor._tracked_trigger_oids.add(5555)

        purged_count = executor.purge_child_trigger_orders(non_blocking=False)

        # Should have purged 5555 (tracked), 6002 (child), and 6001 (trigger order)
        self.assertGreaterEqual(purged_count, 3)
        self.assertEqual(len(executor._tracked_trigger_oids), 0)
        cancelled_oids = [c.args[1] for c in mock_ex.cancel.call_args_list]
        self.assertIn(5555, cancelled_oids)
        self.assertIn(6001, cancelled_oids)
        self.assertIn(6002, cancelled_oids)
        self.assertNotIn(7001, cancelled_oids)  # Standard non-trigger order not purged

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_early_exits_trigger_child_purge(self, mock_info, mock_exchange):
        """Verifies early exits (SIGNAL_REVERSAL, DEFENSIVE_HEDGE, PROFIT_DECAY_EXIT) invoke purge_child_trigger_orders."""
        mock_ex = mock_exchange.return_value
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.cached_position = 0.05  # Long position
        executor.entry_price = 80000.0
        executor.peak_price = 80000.0

        with patch.object(executor, "purge_child_trigger_orders") as mock_purge, \
             patch.object(executor, "place_limit_order") as mock_place_limit:

            # 1. Signal Reversal (Alpha Conviction Inverted)
            executor.on_signal_update(
                signal_score=-0.80,  # <= -exit_reversal_threshold (0.35)
                best_bid=80000.0,
                best_ask=80001.0,
                spread=1.0,
            )
            mock_purge.assert_called()
            mock_purge.reset_mock()

            # 2. Defensive Hedge Escalation (pre-stop-loss blowout)
            executor.active_order = None
            executor.cached_position = 0.05
            executor.entry_price = 80000.0
            # Loss <= -sl_bps * 0.75 (sl_bps=8.0 -> -6.0 bps loss)
            # Price at 79950.0 is -6.25 bps
            executor.on_signal_update(
                signal_score=0.0,
                best_bid=79950.0,
                best_ask=79951.0,
                spread=1.0,
            )
            mock_purge.assert_called()
            mock_purge.reset_mock()

            # 3. Profit Decay Exit
            executor.active_order = None
            executor.cached_position = 0.05
            executor.entry_price = 80000.0
            executor.peak_unrealized_bps = 5.0  # Hit peak excursion >= 3.5 bps
            # Current price dropped to +0.2 bps (< 0.5 bps) with negative signal
            executor.on_signal_update(
                signal_score=-0.1,
                best_bid=80001.6,
                best_ask=80002.0,
                spread=0.4,
            )
            mock_purge.assert_called()

    # -------------------------------------------------------------------------
    # 5. Robustness & Edge Cases
    # -------------------------------------------------------------------------
    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_place_bracket_order_exchange_error_clears_active_order(self, mock_info, mock_exchange):
        """Verifies place_bracket_order clears active_order on exchange rejection or error."""
        mock_ex = mock_exchange.return_value
        mock_ex.bulk_orders.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"error": "Post only order would have immediately matched"}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=True)
        executor.is_initialized = True
        executor.exchange = mock_ex

        executor.place_bracket_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            tp_price=80200.0,
            sl_price=79900.0,
            post_only=True,
            non_blocking=False,
        )

        self.assertIsNone(executor.active_order)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_dispatch_position_tpsl_when_cached_position_zero(self, mock_info, mock_exchange):
        """Verifies dispatch_position_tpsl succeeds with position_sz even when cached_position is 0."""
        mock_ex = mock_exchange.return_value
        mock_ex.bulk_orders.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"waitingForTrigger": {"oid": 8001}}, {"waitingForTrigger": {"oid": 8002}}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.cached_position = 0.0  # Zero cached position
        executor.entry_price = 80000.0

        res = executor.dispatch_position_tpsl(
            position_sz=0.05,
            is_long=True,
            tp_price=80200.0,
            sl_price=79900.0,
        )

        self.assertIsNotNone(res)
        mock_ex.bulk_orders.assert_called_once()
        orders, kwargs = mock_ex.bulk_orders.call_args
        self.assertEqual(kwargs.get("grouping"), "positionTpsl")
        self.assertEqual(len(orders[0]), 2)
        # Verify waitingForTrigger OIDs were tracked
        self.assertIn(8001, executor._tracked_trigger_oids)
        self.assertIn(8002, executor._tracked_trigger_oids)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_cancel_order_partial_fill_with_zero_cached_pos(self, mock_info, mock_exchange):
        """When an order with cum_size > 0 is canceled while cached_position is 0, positionTpsl is dispatched."""
        mock_ex = mock_exchange.return_value
        mock_ex.cancel.return_value = {"status": "ok"}
        mock_ex.bulk_orders.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 8101}}, {"resting": {"oid": 8102}}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.cached_position = 0.0  # Sync not occurred yet
        executor.entry_price = 80000.0

        executor.active_order = {
            "oid": 7777,
            "is_buy": True,
            "price": 80000.0,
            "size": 0.02,
            "cum_size": 0.03,
            "is_bracket": True,
            "is_exit": False,
            "tp_price": 80200.0,
            "sl_price": 79900.0,
            "strategy_name": "WOBI_Maker",
        }
        executor.active_order_oids = [7777]

        with patch.object(executor, "dispatch_position_tpsl", wraps=executor.dispatch_position_tpsl) as spy_dispatch:
            res = executor.cancel_order(7777, non_blocking=False)
            self.assertTrue(res)
            spy_dispatch.assert_called_once_with(
                position_sz=0.03,
                tp_price=80200.0,
                sl_price=79900.0,
                strategy_name="WOBI_Maker",
            )

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_handle_user_fill_event_cancel_event_from_partial_fill_orders(self, mock_info, mock_exchange):
        """When WS receives cancellation for an order stored in _partial_fill_orders, dispatches positionTpsl."""
        mock_ex = mock_exchange.return_value
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.cached_position = 0.03
        executor.active_order = None  # active_order is None

        executor._partial_fill_orders[9991] = {
            "oid": 9991,
            "is_buy": True,
            "size": 0.02,
            "cum_size": 0.03,
            "is_bracket": True,
            "tp_price": 80200.0,
            "sl_price": 79900.0,
            "strategy_name": "WOBI_Maker",
        }

        with patch.object(executor, "dispatch_position_tpsl") as mock_dispatch:
            # WebSocket order cancel event
            executor.handle_user_fill_event({"status": "canceled", "oid": 9991})
            mock_dispatch.assert_called_once()
            args, kwargs = mock_dispatch.call_args
            self.assertEqual(kwargs.get("position_sz"), 0.03)
            self.assertEqual(kwargs.get("tp_price"), 80200.0)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_modify_limit_order_preserves_bracket_attributes(self, mock_info, mock_exchange):
        """Verifies modify_limit_order retains is_bracket, tp_price, sl_price, cum_size."""
        mock_ex = mock_exchange.return_value
        mock_ex.modify_order.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 9992}}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex

        executor.active_order = {
            "oid": 9991,
            "is_buy": True,
            "price": 80000.0,
            "size": 0.05,
            "time": 1000.0,
            "strategy_name": "WOBI_Maker",
            "is_exit": False,
            "is_bracket": True,
            "tp_price": 80200.0,
            "sl_price": 79900.0,
            "cum_size": 0.02,
        }
        executor.active_order_oids = [9991]

        res = executor.modify_limit_order(
            oid=9991,
            is_buy=True,
            size_btc=0.05,
            price=80001.0,
            post_only=True,
            non_blocking=False,
        )

        self.assertIsNotNone(res)
        self.assertIsNotNone(executor.active_order)
        self.assertEqual(executor.active_order["oid"], 9992)
        self.assertTrue(executor.active_order["is_bracket"])
        self.assertEqual(executor.active_order["tp_price"], 80200.0)
        self.assertEqual(executor.active_order["sl_price"], 79900.0)
        self.assertEqual(executor.active_order["cum_size"], 0.02)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_force_market_orders_wires_bracket_when_use_native_tpsl(self, mock_info, mock_exchange):
        """When force_market_orders=True and use_native_tpsl=True, on_signal_update places bracket order."""
        mock_ex = mock_exchange.return_value
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.force_market_orders = True
        executor.use_native_tpsl = True
        executor.cached_position = 0.0

        placed_brackets = []

        def mock_place_bracket(*args, **kwargs):
            placed_brackets.append(kwargs)
            return {"status": "ok"}

        executor.place_bracket_order = mock_place_bracket

        executor.on_signal_update(
            signal_score=0.85,
            best_bid=80000.0,
            best_ask=80001.0,
            spread=1.0,
        )

        self.assertEqual(len(placed_brackets), 1)
        self.assertFalse(placed_brackets[0]["post_only"])  # Market fill
        self.assertTrue(placed_brackets[0]["is_buy"])
        self.assertIsNotNone(placed_brackets[0]["tp_price"])
        self.assertIsNotNone(placed_brackets[0]["sl_price"])

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_purge_child_trigger_orders_with_trigger_px(self, mock_info, mock_exchange):
        """Verifies purge_child_trigger_orders purges frontend orders containing triggerPx."""
        mock_ex = mock_exchange.return_value
        mock_ex.cancel.return_value = {"status": "ok"}

        mock_in = mock_info.return_value
        mock_in.frontend_open_orders.return_value = [
            {
                "coin": "BTC",
                "oid": 9101,
                "orderType": "Stop Market",
                "triggerPx": "79900.0",
                "children": [],
            },
        ]

        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.info = mock_in
        executor.account_address = "0x76cfd21f8a84c670b09489d7b9015c92c4222416"

        purged_count = executor.purge_child_trigger_orders(non_blocking=False)

        self.assertEqual(purged_count, 1)
        mock_ex.cancel.assert_called_once_with("BTC", 9101)


if __name__ == "__main__":
    unittest.main()
