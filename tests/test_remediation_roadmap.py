"""Unit tests verifying remediation roadmap implementations:
1. Elimination of ALO IOC auto-escalation on entries for MAKER strategies.
2. Dynamic emergency slippage buffer on STOP_LOSS and DEFENSIVE_HEDGE_ESCALATE.
3. Real-time WebSocket userFills handler (handle_user_fill_event) updating state synchronously.
4. Backtester EdgeEvaluator modeling trailing stops and stop losses as TAKER with dynamic slippage.
"""

import unittest
from unittest.mock import MagicMock, patch

from config import AppConfig, BacktestConfig, MarketConfig
from engine.backtester import EdgeEvaluator
from engine.live_executor import LiveOrderExecutor


class TestRemediationRoadmap(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.config.account.account_address = "0x76cfd21f8a84c670b09489d7b9015c92c4222416"
        self.config.account.secret_key = "0x" + "1" * 64
        self.config.market.coin = "xyz:SKHX"
        self.config.strategies.live_execution.force_market_orders = False
        self.config.strategies.live_execution.market_slippage_pct = 0.0005

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_maker_entry_alo_rejection_does_not_escalate_to_ioc(self, mock_info, mock_exchange):
        """Verifies that MAKER strategy ALO entry rejection does NOT escalate to IOC."""
        mock_ex = mock_exchange.return_value
        mock_ex.order.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"error": "Post only order would have immediately matched, bbo was 100.0@100.0"}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex

        # Hedged_Convexity is a HEDGED_MAKER strategy
        res = executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=100.0,
            post_only=True,
            is_exit=False,
            strategy_name="Hedged_Convexity",
        )

        # Exchange should only be called ONCE (no retry/escalation to IOC)
        self.assertEqual(mock_ex.order.call_count, 1)
        first_call = mock_ex.order.call_args_list[0]
        self.assertEqual(first_call.kwargs["order_type"], {"limit": {"tif": "Alo"}})

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_smart_taker_entry_alo_rejection_escalates_to_ioc(self, mock_info, mock_exchange):
        """Verifies that SMART_TAKER strategy ALO entry rejection DOES escalate to IOC."""
        mock_ex = mock_exchange.return_value
        mock_ex.order.side_effect = [
            {"status": "ok", "response": {"data": {"statuses": [{"error": "Post only order would have immediately matched"}]}}},
            {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 5001}}]}}},
        ]
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex

        # Instant_FastFill has execution_type == "SMART_TAKER"
        res = executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=100.0,
            post_only=True,
            is_exit=False,
            strategy_name="Instant_FastFill",
        )

        self.assertEqual(mock_ex.order.call_count, 2)
        second_call = mock_ex.order.call_args_list[1]
        self.assertEqual(second_call.kwargs["order_type"], {"limit": {"tif": "Ioc"}})

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_emergency_stop_loss_dynamic_slippage_buffer_long(self, mock_info, mock_exchange):
        """Verifies emergency stop loss calculates at least 5 bps / 3 ticks dynamic slippage buffer on Long exit."""
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_exchange.return_value
        executor.max_price_decimals = 3
        executor.max_px_decimals = 3
        executor.sz_decimals = 3
        executor.cached_position = 1.0
        executor.entry_price = 100.0
        executor.peak_price = 100.0

        actions = []
        executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0, **kwargs: (
            actions.append(("EXIT", is_buy, price, kwargs.get("exit_reason"))),
            {"status": "ok"}
        )[1]

        # Best bid = 99.0 (-100 bps drop, SL = -8 bps)
        # Mid price = 99.05
        # 3 ticks at 3 decimals = 0.003 -> 0.003 / 99.05 = ~0.00003
        # max(0.0005, 0.00003) = 0.0005 (5 bps buffer)
        # Exit px = 99.0 * (1 - 0.0005) = 98.9505 -> formatted: 98.95
        executor.on_signal_update(
            signal_score=0.0,
            best_bid=99.0,
            best_ask=99.1,
            spread=0.1,
        )

        self.assertEqual(len(actions), 1)
        side_exit, is_buy, exit_px, reason = actions[0]
        self.assertFalse(is_buy)  # Sell to close long
        self.assertEqual(reason, "STOP_LOSS")
        self.assertLess(exit_px, 99.0)  # Must be strictly below best bid
        self.assertAlmostEqual(exit_px, 98.95, delta=0.01)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_emergency_stop_loss_dynamic_slippage_buffer_short(self, mock_info, mock_exchange):
        """Verifies emergency stop loss calculates dynamic slippage buffer on Short exit."""
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_exchange.return_value
        executor.max_price_decimals = 3
        executor.max_px_decimals = 3
        executor.sz_decimals = 3
        executor.cached_position = -1.0
        executor.entry_price = 100.0
        executor.trough_price = 100.0

        actions = []
        executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0, **kwargs: (
            actions.append(("EXIT", is_buy, price, kwargs.get("exit_reason"))),
            {"status": "ok"}
        )[1]

        # Best ask = 101.0 (+100 bps rise against short)
        executor.on_signal_update(
            signal_score=0.0,
            best_bid=100.9,
            best_ask=101.0,
            spread=0.1,
        )

        self.assertEqual(len(actions), 1)
        side_exit, is_buy, exit_px, reason = actions[0]
        self.assertTrue(is_buy)  # Buy to close short
        self.assertEqual(reason, "STOP_LOSS")
        self.assertGreater(exit_px, 101.0)  # Must be strictly above best ask

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_handle_user_fill_event_synchronous_sync(self, mock_info, mock_exchange):
        """Verifies handle_user_fill_event updates position, entry price, preserves strategy and exit_reason, and clears active order."""
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_exchange.return_value
        executor.coin = "xyz:SKHX"
        executor.sz_decimals = 3
        executor.cached_position = 0.0
        executor.active_order = {"oid": 7777, "is_buy": True, "price": 100.0, "size": 0.5, "strategy_name": "QDAP_Maker"}
        executor.active_order_oids = [7777]

        # 1. Incoming BUY fill packet
        fill_event = {
            "channel": "userFills",
            "data": {
                "isSnapshot": False,
                "fills": [
                    {
                        "coin": "xyz:SKHX",
                        "px": "100.0",
                        "sz": "0.5",
                        "side": "B",
                        "oid": 7777,
                        "crossed": False,
                        "fee": "0.0015",
                        "time": 1700000000000,
                    }
                ]
            }
        }

        with patch.object(executor, "sync_state"):
            executor.handle_user_fill_event(fill_event["data"])

        self.assertAlmostEqual(executor.cached_position, 0.5)
        self.assertAlmostEqual(executor.entry_price, 100.0)
        self.assertEqual(executor.position_strategy, "QDAP_Maker")
        self.assertIsNone(executor.active_order)  # OID 7777 cleared!
        self.assertNotIn(7777, executor.active_order_oids)

        # 2. Place resting exit order and receive incoming SELL fill packet closing position
        executor.active_order = {"oid": 8888, "is_buy": False, "price": 100.5, "size": 0.5, "strategy_name": "QDAP_Maker", "exit_reason": "TAKE_PROFIT"}
        executor.active_order_oids = [8888]

        fill_close = {
            "isSnapshot": False,
            "fills": [
                {
                    "coin": "xyz:SKHX",
                    "px": "100.5",
                    "sz": "0.5",
                    "side": "A",
                    "oid": 8888,
                    "crossed": False,
                    "fee": "0.0015",
                    "time": 1700000010000,
                }
            ]
        }

        with patch.object(executor, "sync_state"):
            executor.handle_user_fill_event(fill_close)

        self.assertAlmostEqual(executor.cached_position, 0.0)
        self.assertEqual(len(executor.completed_trades), 1)
        self.assertAlmostEqual(executor.completed_trades[0]["gross_pnl_usd"], 0.25)  # (100.5 - 100.0) * 0.5
        # Crucial fix: exit_reason must be preserved from the active resting order!
        self.assertEqual(executor.completed_trades[0]["exit_reason"], "TAKE_PROFIT")

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_handle_user_fill_event_loss_updates_cooldown(self, mock_info, mock_exchange):
        """Verifies handle_user_fill_event updates last_loss_exit_time when closing at a loss."""
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_exchange.return_value
        executor.coin = "xyz:SKHX"
        executor.sz_decimals = 3
        executor.cached_position = 0.5
        executor.entry_price = 100.0
        executor.last_loss_exit_time = 0.0

        # Fill at 98.0 (loss)
        fill_loss = {
            "isSnapshot": False,
            "fills": [
                {
                    "coin": "xyz:SKHX",
                    "px": "98.0",
                    "sz": "0.5",
                    "side": "A",
                    "oid": 9999,
                    "crossed": True,
                    "fee": "0.0045",
                    "closedPnl": "-1.0",
                    "time": 1700000020000,
                }
            ]
        }

        with patch.object(executor, "sync_state"):
            executor.handle_user_fill_event(fill_loss)

        self.assertAlmostEqual(executor.cached_position, 0.0)
        self.assertGreater(executor.last_loss_exit_time, 0.0)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_handle_user_fill_event_partial_fill_retains_active_order(self, mock_info, mock_exchange):
        """Verifies handle_user_fill_event decrements remaining size and retains active order on partial fills."""
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_exchange.return_value
        executor.coin = "xyz:SKHX"
        executor.sz_decimals = 3
        executor.cached_position = 0.0
        executor.active_order = {"oid": 5555, "is_buy": True, "price": 100.0, "size": 1.0, "strategy_name": "QDAP_Maker"}
        executor.active_order_oids = [5555]

        # Partial fill of 0.4 out of 1.0
        partial_fill = {
            "isSnapshot": False,
            "fills": [
                {
                    "coin": "xyz:SKHX",
                    "px": "100.0",
                    "sz": "0.4",
                    "side": "B",
                    "oid": 5555,
                    "crossed": False,
                    "fee": "0.001",
                    "time": 1700000000000,
                }
            ]
        }

        with patch.object(executor, "sync_state"):
            executor.handle_user_fill_event(partial_fill)

        self.assertAlmostEqual(executor.cached_position, 0.4)
        self.assertIsNotNone(executor.active_order)
        self.assertAlmostEqual(executor.active_order["size"], 0.6)  # Remaining resting size
        self.assertIn(5555, executor.active_order_oids)

    def test_backtester_trailing_stop_taker_execution_and_dynamic_slippage(self):
        """Verifies EdgeEvaluator executes trailing stop as TAKER with dynamic slippage and taker fee."""
        m_cfg = MarketConfig(coin="xyz:SKHX", maker_fee_bps=0.30, taker_fee_bps=0.90)
        bt_cfg = BacktestConfig(
            take_profit_bps=20.0,
            trailing_stop_activation_bps=3.0,
            trailing_stop_distance_bps=1.0,
            stop_loss_bps=10.0,
            max_spread_bps=5.0,
            dynamic_slippage=True,
        )
        evaluator = EdgeEvaluator(
            market_cfg=m_cfg,
            bt_cfg=bt_cfg,
            strategy_defs={"QDAP_Maker": ("QDAP", "MAKER")},
            strategy_params={"QDAP_Maker": {
                "entry_threshold": 0.70,
                "take_profit_bps": 20.0,
                "trailing_stop_activation_bps": 3.0,
                "trailing_stop_distance_bps": 1.0,
                "stop_loss_bps": 10.0,
                "order_size_btc": 1.0,
                "min_volatility_bps": 0.0,
            }},
        )

        # 1. Warmup
        for i in range(10):
            evaluator.record_step(
                timestamp_ms=1000 + i * 100,
                mid_price=100.0,
                best_bid=99.99,
                best_ask=100.01,
                signals={"QDAP": 0.0},
            )

        # 2. Bullish Entry at 99.99 (Maker Buy)
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.0,
            best_bid=99.99,
            best_ask=100.01,
            signals={"QDAP": 0.85},
        )
        st = evaluator.strategies["QDAP_Maker"]
        self.assertTrue(st.is_in_position)
        self.assertAlmostEqual(st.entry_price, 99.99)

        # 3. Price rises to +5 bps (activates trailing stop)
        evaluator.record_step(
            timestamp_ms=2500,
            mid_price=100.05,
            best_bid=100.04,
            best_ask=100.06,
            signals={"QDAP": 0.50},
        )
        self.assertTrue(st.trailing_stop_active)

        # 4. Price falls back to trigger trailing stop
        evaluator.record_step(
            timestamp_ms=3000,
            mid_price=100.02,
            best_bid=100.01,
            best_ask=100.03,
            signals={"QDAP": 0.50},
        )

        self.assertFalse(st.is_in_position)
        self.assertEqual(len(st.trades), 1)
        tr = st.trades[0]
        self.assertEqual(tr.exit_reason, "TRAILING_STOP")
        # Execution type MUST be TAKER, not MAKER!
        self.assertIn("TAKER", tr.execution_type)
        # Exit fee must be taker fee (0.90 bps), not maker fee (0.30 bps)
        # Total fee = entry maker (0.3 bps) + exit taker (0.9 bps)
        expected_exit_fee = tr.exit_price * tr.size_btc * (0.90 / 10000.0)
        expected_entry_fee = tr.entry_price * tr.size_btc * (0.30 / 10000.0)
        self.assertAlmostEqual(tr.fees_usd, expected_entry_fee + expected_exit_fee, delta=0.001)
        # Exit price must be below best_bid due to slippage
        self.assertLess(tr.exit_price, 100.01)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_maker_entry_alo_rejection_cooldown_set(self, mock_info, mock_exchange):
        """Verifies ALO entry rejection sets full cooldown timestamp and resets position_strategy."""
        import time
        mock_ex = mock_exchange.return_value
        mock_ex.order.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"error": "Post only order would have immediately matched"}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.last_order_time = 0.0

        t_before = time.time()
        executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=100.0,
            post_only=True,
            is_exit=False,
            strategy_name="Hedged_Convexity",
        )
        t_after = time.time()

        self.assertGreaterEqual(executor.last_order_time, t_before)
        self.assertLessEqual(executor.last_order_time, t_after)
        self.assertIsNone(executor.position_strategy)

    def test_backtester_close_open_positions_dynamic_slippage(self):
        """Verifies close_open_positions uses dynamic slippage when dynamic_slippage is enabled."""
        m_cfg = MarketConfig(coin="xyz:SKHX", maker_fee_bps=0.30, taker_fee_bps=0.90)
        bt_cfg = BacktestConfig(
            take_profit_bps=20.0,
            stop_loss_bps=10.0,
            dynamic_slippage=True,
        )
        evaluator = EdgeEvaluator(
            market_cfg=m_cfg,
            bt_cfg=bt_cfg,
            strategy_defs={"QDAP_Maker": ("QDAP", "MAKER")},
        )
        st = evaluator.strategies["QDAP_Maker"]
        st.position_btc = 1.0
        st.entry_price = 100.0
        st.entry_fee_usd = 0.003
        st.entry_time_ms = 1000
        evaluator.current_volatility_bps = 10.0

        evaluator.close_open_positions(mid_price=100.0, timestamp_ms=5000, reason="SESSION_SHUTDOWN")
        self.assertEqual(len(st.trades), 1)
        tr = st.trades[0]
        # Dynamic slip for cur_vol=10 is max(0.5, 0.25*1.5 + 0.15*10) = 1.875 bps
        # Exit price should be 100.0 * (1 - 0.0001875) = 99.98125
        self.assertLess(tr.exit_price, 100.0 * (1.0 - 0.0001))
        self.assertAlmostEqual(tr.exit_price, 99.98125, delta=0.005)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_user_fill_deduplication_prevents_duplicate_processing(self, mock_info, mock_exchange):
        """Verifies WebSocket userFills drops fills for OIDs/TIDs already processed by REST."""
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_exchange.return_value
        executor.coin = "xyz:SKHX"
        executor.sz_decimals = 4
        executor.cached_position = 0.1060
        executor.entry_price = 942.0

        # Simulate that REST immediate fill already processed OID 595499300000
        executor._processed_fill_oids.add(595499300000)

        # Incoming WebSocket fill packet for the same OID
        fill_event = {
            "isSnapshot": False,
            "fills": [
                {
                    "coin": "xyz:SKHX",
                    "px": "942.0",
                    "sz": "0.1060",
                    "side": "A",
                    "oid": 595499300000,
                    "tid": 12345678,
                    "crossed": True,
                    "fee": "0.001",
                    "time": 1700000000000,
                }
            ]
        }

        with patch.object(executor, "sync_state"):
            executor.handle_user_fill_event(fill_event)

        # Position should remain untouched (NOT decremented again to 0.0 or negative phantom)
        self.assertAlmostEqual(executor.cached_position, 0.1060)
        self.assertEqual(len(executor.completed_trades), 0)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_do_sync_no_ghost_trade_when_entry_price_zero(self, mock_info, mock_exchange):
        """Verifies _do_sync does NOT record PASSIVE_MAKER_FILL when entry_price is 0.0 (phantom positions)."""
        mock_auditor = MagicMock()
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.info = mock_info.return_value
        executor.auditor = mock_auditor
        executor.coin = "xyz:SKHX"
        executor.cached_position = -0.1060
        executor.entry_price = 0.0  # No valid entry price
        executor.position_strategy = "WOBI_Maker"
        executor.active_order = None

        # Hyperliquid returns assetPositions with szi: "0.0"
        executor.info.user_state.return_value = {
            "marginSummary": {"accountValue": "100.0", "totalMarginUsed": "0.0"},
            "assetPositions": [
                {
                    "position": {
                        "coin": "xyz:SKHX",
                        "szi": "0.0",
                        "entryPx": "0.0",
                    }
                }
            ],
        }
        executor.info.open_orders.return_value = []

        executor.sync_state(force=True)

        self.assertAlmostEqual(executor.cached_position, 0.0)
        # Completed trades must NOT contain a phantom trade
        self.assertEqual(len(executor.completed_trades), 0)
        mock_auditor.record_trade.assert_not_called()

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_place_limit_order_cancels_orphaned_resting_orders(self, mock_info, mock_exchange):
        """Verifies place_limit_order proactively cancels resting order OIDs before placing new entry."""
        mock_ex = mock_exchange.return_value
        mock_ex.order.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 6001}}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.coin = "xyz:SKHX"
        executor.active_order_oids = [5001, 5002]

        with patch.object(executor, "cancel_order") as mock_cancel:
            executor.place_limit_order(
                is_buy=True,
                size_btc=0.05,
                price=100.0,
                post_only=True,
                is_exit=False,
                strategy_name="Dynamic_Spread_Scalper",
            )
            # Should have called cancel_order for both orphaned OIDs
            self.assertEqual(mock_cancel.call_count, 2)
            mock_cancel.assert_any_call(5001, non_blocking=False)
            mock_cancel.assert_any_call(5002, non_blocking=False)

    def test_dynamic_xyz_market_config(self):
        """Verifies setting MarketConfig.coin to xyz: stock dynamically applies stock fee tiers."""
        cfg = AppConfig()
        cfg.market.coin = "xyz:SKHX"
        self.assertTrue(cfg.market.is_xyz_stock)
        self.assertAlmostEqual(cfg.market.maker_fee_bps, 0.30)
        self.assertAlmostEqual(cfg.market.taker_fee_bps, 0.90)
        self.assertAlmostEqual(cfg.market.maker_rebate_bps, 0.30)

        # Switching to crypto resets
        cfg.market.coin = "BTC"
        self.assertFalse(cfg.market.is_xyz_stock)
        self.assertAlmostEqual(cfg.market.maker_fee_bps, 1.5)
        self.assertAlmostEqual(cfg.market.taker_fee_bps, 4.5)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_consecutive_partial_fills_same_oid_not_dropped(self, mock_info, mock_exchange):
        """Verifies consecutive partial fills with different TIDs on the same resting order OID are both processed."""
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_exchange.return_value
        executor.coin = "xyz:SKHX"
        executor.sz_decimals = 4
        executor.cached_position = 0.0
        executor.active_order = {"oid": 5555, "is_buy": True, "price": 100.0, "size": 1.0, "strategy_name": "Dynamic_Spread_Scalper"}
        executor.active_order_oids = [5555]

        # 1. Partial fill 1: 0.4 units
        f1 = {
            "isSnapshot": False,
            "fills": [
                {
                    "coin": "xyz:SKHX",
                    "px": "100.0",
                    "sz": "0.4",
                    "side": "B",
                    "oid": 5555,
                    "tid": 1001,
                    "crossed": False,
                    "fee": "0.001",
                    "time": 1700000000000,
                }
            ]
        }
        with patch.object(executor, "sync_state"):
            executor.handle_user_fill_event(f1)

        self.assertAlmostEqual(executor.cached_position, 0.4)
        self.assertIsNotNone(executor.active_order)
        self.assertAlmostEqual(executor.active_order["size"], 0.6)

        # 2. Partial fill 2: remaining 0.6 units
        f2 = {
            "isSnapshot": False,
            "fills": [
                {
                    "coin": "xyz:SKHX",
                    "px": "100.0",
                    "sz": "0.6",
                    "side": "B",
                    "oid": 5555,
                    "tid": 1002,
                    "crossed": False,
                    "fee": "0.0015",
                    "time": 1700000001000,
                }
            ]
        }
        with patch.object(executor, "sync_state"):
            executor.handle_user_fill_event(f2)

        # Position must be 1.0 and resting order cleared
        self.assertAlmostEqual(executor.cached_position, 1.0)
        self.assertIsNone(executor.active_order)
        self.assertNotIn(5555, executor.active_order_oids)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_do_sync_no_ghost_trade_when_active_order_none_even_if_entry_price_positive(self, mock_info, mock_exchange):
        """Verifies _do_sync does NOT record PASSIVE_MAKER_FILL when active_order is None, even if entry_price > 0."""
        mock_auditor = MagicMock()
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.info = mock_info.return_value
        executor.auditor = mock_auditor
        executor.coin = "xyz:SKHX"
        executor.cached_position = -0.1060
        executor.entry_price = 942.39  # Positive entry price as in the real incident
        executor.position_strategy = "WOBI_Maker"
        executor.active_order = None  # No active resting exit order

        executor.info.user_state.return_value = {
            "marginSummary": {"accountValue": "100.0", "totalMarginUsed": "0.0"},
            "assetPositions": [
                {
                    "position": {
                        "coin": "xyz:SKHX",
                        "szi": "0.0",
                        "entryPx": "0.0",
                    }
                }
            ],
        }
        executor.info.open_orders.return_value = []

        executor.sync_state(force=True)

        self.assertAlmostEqual(executor.cached_position, 0.0)
        self.assertEqual(len(executor.completed_trades), 0)
        mock_auditor.record_trade.assert_not_called()

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_main_evaluate_signals_priority_locks_active_strategy(self, mock_info, mock_exchange):
        """Verifies _evaluate_signals adheres to enabled active_strategy and does not let other strategies hijack."""
        from main import L2EngineRunner
        cfg = AppConfig()
        cfg.market.coin = "xyz:SKHX"
        cfg.strategies.live_execution.active_strategy = "Dynamic_Spread_Scalper"
        # Enable both Dynamic_Spread_Scalper and Instant_FastFill
        cfg.strategies.scalping_strategies["Dynamic_Spread_Scalper"].enabled = True
        cfg.strategies.scalping_strategies["Instant_FastFill"].enabled = True

        runner = L2EngineRunner(config=cfg, record_data=False, live_orders=True)
        try:
            from core.orderbook import L2Level
            runner.live_executor.cached_position = 0.0
            runner.live_executor.active_order = None
            runner.book.bids = [L2Level(px=940.0, sz=1.0, n=1)]
            runner.book.asks = [L2Level(px=940.2, sz=1.0, n=1)]

            mock_res = MagicMock()
            mock_res.score = 0.50
            mock_res.confidence = 0.85
            mock_res.metadata = {
                "sub_signals": {
                    "DynamicSpread": MagicMock(score=0.10, confidence=0.80),
                    "InstantFill": MagicMock(score=0.95, confidence=0.90),
                }
            }
            runner.alpha_model.compute = MagicMock(return_value=mock_res)

            with patch.object(runner.live_executor, "on_signal_update") as mock_on_sig:
                runner._evaluate_signals()
                self.assertEqual(runner.live_executor.strategy_name, "Dynamic_Spread_Scalper")
                mock_on_sig.assert_called_once()
                call_kwargs = mock_on_sig.call_args[1]
                self.assertEqual(call_kwargs["signal_score"], 0.10)
        finally:
            runner.close()


if __name__ == "__main__":
    unittest.main()



