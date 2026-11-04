"""Unit tests for LiveOrderExecutor.

Verifies:
1. Formatting helpers (price 5 sig figs, size decimals, min notional enforcement).
2. Stateful resting order persistence (zero instant self-cancellation churn).
3. Market price drift re-quoting.
4. Signal decay cancellation with hysteresis.
5. Exit lifecycle (Take Profit, Stop Loss, Trailing Stop, Defensive Maker Hedge).
6. Exit quote resting persistence (no 100ms self-cancellation churn).
"""

import unittest
from unittest.mock import MagicMock, patch

from config import AppConfig
from engine.live_executor import LiveOrderExecutor


class TestLiveOrderExecutor(unittest.TestCase):
    def setUp(self):
        self.cfg = AppConfig()
        self.cfg.strategies.live_execution.priority_fee_bps = 0.0
        self.cfg.strategies.live_execution.force_market_orders = False
        # Mock eth_account and Hyperliquid network calls so tests run isolated & fast
        with patch("engine.live_executor.eth_account.Account.from_key"), \
             patch("engine.live_executor.Info"), \
             patch("engine.live_executor.Exchange"):
            self.executor = LiveOrderExecutor(config=self.cfg, strategy_name="Queue_Replenishment")
            self.executor.is_initialized = True
            self.executor.sz_decimals = 5
            self.executor.max_price_decimals = 1
            self.executor.coin = "BTC"

    def test_price_formatting(self):
        # Hyperliquid requires max 5 significant figures & max price decimals
        self.assertEqual(self.executor.format_price(81501.25), 81501.0)
        self.assertEqual(self.executor.format_price(82.2195), 82.2)

        # For HYPE with max_price_decimals = 4
        self.executor.max_price_decimals = 4
        self.assertEqual(self.executor.format_price(82.219), 82.219)

    def test_size_formatting_and_min_notional(self):
        self.executor.sz_decimals = 2
        self.assertEqual(self.executor.format_size(1.2345), 1.23)

        # Ensure min notional upgrades size when below $15.00
        # At price = $80, 0.05 units is $4.00 (< $15.00). Must upgrade to at least 20 / 80 = 0.25 units
        upgraded = self.executor.ensure_min_notional(0.05, 80.0)
        self.assertGreaterEqual(upgraded * 80.0, 15.0)

    def test_dynamic_capital_usd_sizing(self):
        # With capital_usd = $5000 and allocation_pct = 1.0 at price 80,000:
        # Size = 5000 / 80000 = 0.0625 BTC
        self.executor.capital_usd = 5000.0
        self.executor.allocation_pct = 1.0
        actions = []
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0, **kwargs: (
            actions.append(("PLACE", is_buy, size_btc, price)),
            {"status": "ok"}
        )[1]

        self.executor.on_signal_update(0.99, 80000.0, 80001.0, 1.0)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0][2], 0.0625)

    def test_resting_order_persistence_no_churn(self):
        actions = []
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0, **kwargs: (
            actions.append(("PLACE", is_buy, price)),
            setattr(self.executor, "active_order", {
                "oid": 101, "is_buy": is_buy, "price": price, "size": size_btc, "time": 100.0, "is_exit": False
            }),
            {"status": "ok"}
        )[2]
        self.executor.cancel_order = lambda oid: (actions.append(("CANCEL", oid)), setattr(self.executor, "active_order", None), True)[2]

        # Tick 1: Bullish signal triggers resting BUY quote
        self.executor.on_signal_update(0.99, 81500.0, 81501.0, 1.0)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0], ("PLACE", True, 81500.0))

        # Tick 2: Signal remains bullish at same price -> MUST NOT CANCEL (preserve queue priority!)
        actions.clear()
        self.executor.on_signal_update(0.99, 81500.0, 81501.0, 1.0)
        self.assertEqual(len(actions), 0, "Active resting order should NOT be cancelled on subsequent ticks with same price")

        # Tick 3: Best bid drifts to 81502.0 -> Must cancel stale order and re-quote
        actions.clear()
        self.executor.on_signal_update(0.99, 81502.0, 81503.0, 1.0)
        self.assertEqual(actions, [("CANCEL", 101), ("PLACE", True, 81502.0)])

        # Tick 4: Signal decays below hysteresis floor (0.10 < 0.985 * 0.45) -> Must cancel resting order
        actions.clear()
        self.executor.on_signal_update(0.10, 81502.0, 81503.0, 1.0)
        self.assertEqual(actions, [("CANCEL", 101)])

    def test_entry_hysteresis_preserves_quote_on_minor_dip(self):
        actions = []
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0, **kwargs: (
            actions.append(("PLACE", is_buy, price)),
            setattr(self.executor, "active_order", {
                "oid": 202, "is_buy": is_buy, "price": price, "size": size_btc, "time": 100.0, "is_exit": False
            }),
            {"status": "ok"}
        )[2]
        self.executor.cancel_order = lambda oid: (actions.append(("CANCEL", oid)), setattr(self.executor, "active_order", None), True)[2]

        # Tick 1: Signal triggers entry (0.99 > 0.985 threshold)
        self.executor.on_signal_update(0.99, 81500.0, 81501.0, 1.0)
        self.assertEqual(len(actions), 1)

        # Tick 2: Signal dips to 0.75 (below 0.985, but well above hysteresis floor of 0.44)
        # MUST PRESERVE QUOTE (no cancel churn!)
        actions.clear()
        self.executor.on_signal_update(0.75, 81500.0, 81501.0, 1.0)
        self.assertEqual(len(actions), 0, "Minor signal dip should not cancel resting quote")

    def test_position_exit_take_profit(self):
        actions = []
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0, **kwargs: (
            actions.append(("EXIT", is_buy, price, post_only)),
            {"status": "ok"}
        )[1]

        # In long position with entry at 80,000. Price moves to 80,250 (+31.2 bps > 20 bps TP)
        self.executor.cached_position = 0.0005
        self.executor.entry_price = 80000.0
        self.executor.peak_price = 80000.0

        self.executor.on_signal_update(0.50, 80249.0, 80250.0, 1.0)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0], ("EXIT", False, 80250.0, True))  # Maker limit sell at best ask

    def test_position_exit_quote_persistence_no_churn(self):
        actions = []
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0, **kwargs: (
            actions.append(("EXIT", is_buy, price, post_only)),
            setattr(self.executor, "active_order", {
                "oid": 303, "is_buy": is_buy, "price": price, "size": size_btc, "time": 100.0, "is_exit": True
            }),
            {"status": "ok"}
        )[2]
        self.executor.cancel_order = lambda oid: (actions.append(("CANCEL", oid)), setattr(self.executor, "active_order", None), True)[2]

        self.executor.cached_position = 0.0005
        self.executor.entry_price = 80000.0
        self.executor.peak_price = 80000.0

        # Tick 1: Take profit reached (+31.2 bps) -> posts maker exit sell
        self.executor.on_signal_update(0.50, 80249.0, 80250.0, 1.0)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0], ("EXIT", False, 80250.0, True))

        # Tick 2: Next tick 100ms later with same price -> MUST NOT CANCEL EXIT QUOTE!
        actions.clear()
        self.executor.on_signal_update(0.50, 80249.0, 80250.0, 1.0)
        self.assertEqual(len(actions), 0, "Active resting exit quote must NOT be cancelled on subsequent ticks with same price")

    def test_position_exit_stop_loss(self):
        actions = []
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0, **kwargs: (
            actions.append(("EXIT", is_buy, price, post_only)),
            {"status": "ok"}
        )[1]

        # In long position with entry at 80,000. Price drops to 79,900 (-12.5 bps < -8 bps SL)
        self.executor.cached_position = 0.0005
        self.executor.entry_price = 80000.0
        self.executor.peak_price = 80000.0

        self.executor.on_signal_update(0.50, 79900.0, 79901.0, 1.0)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0], ("EXIT", False, 79900.0, False))  # Taker emergency exit

    def test_position_exit_defensive_maker_hedge(self):
        actions = []
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0, **kwargs: (
            actions.append(("EXIT", is_buy, price, post_only)),
            {"status": "ok"}
        )[1]

        # In long position with Queue_Replenishment (hedge_reversal_threshold = -0.10)
        # Signal drops to -0.30 -> Triggers defensive maker hedge exit at best ask
        self.executor.cached_position = 0.0005
        self.executor.entry_price = 80000.0
        self.executor.peak_price = 80000.0

        self.executor.on_signal_update(-0.30, 80002.0, 80003.0, 1.0)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0], ("EXIT", False, 80003.0, True))  # Maker limit sell at best ask

    def test_modify_limit_order_atomic_batch(self):
        # Verify single-hop atomic modify_order calls Hyperliquid exchange.modify_order directly
        mock_exchange = MagicMock()
        mock_exchange.modify_order.return_value = {
            "status": "ok",
            "response": {
                "type": "batchModify",
                "data": {"statuses": [{"resting": {"oid": 555}}]}
            }
        }
        self.executor.exchange = mock_exchange
        self.executor.active_order_oids = [444]
        self.executor.active_order = {"oid": 444, "is_buy": True, "price": 80000.0, "size": 0.05, "time": 10.0}

        res = self.executor.modify_limit_order(
            oid=444,
            is_buy=True,
            size_btc=0.05,
            price=80010.0,
            post_only=True,
        )
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "ok")
        mock_exchange.modify_order.assert_called_once()
        self.assertEqual(self.executor.active_order["oid"], 555)
        self.assertIn(555, self.executor.active_order_oids)
        self.assertNotIn(444, self.executor.active_order_oids)

    def test_asset_id_caching_and_fast_lookup(self):
        # Verify pre-computation caches asset_id and avoids redundant dictionary lookups
        with patch("engine.live_executor.Info") as mock_info_cls, \
             patch("engine.live_executor.Exchange"):
            mock_info = mock_info_cls.return_value
            mock_info.name_to_asset.return_value = 42
            mock_info.meta.return_value = {"universe": [{"name": "BTC", "szDecimals": 5}]}
            self.executor._initialize()
            self.assertEqual(self.executor.asset_id, 42)
            # Fast lookup lambda returns cached asset directly without dictionary lookup overhead
            self.assertEqual(self.executor.info.name_to_asset("BTC"), 42)

    def test_non_blocking_order_dispatch(self):
        import time
        mock_exchange = MagicMock()
        mock_exchange.order.return_value = {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"resting": {"oid": 999}}]}
            }
        }
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = True

        res = self.executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            post_only=True,
        )
        # Returns immediately with pending status
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "ok")
        self.assertTrue(res.get("pending"))

        # Wait for thread pool worker to complete transmission
        time.sleep(0.05)
        mock_exchange.order.assert_called_once()
        self.assertEqual(self.executor.active_order["oid"], 999)
        self.assertIn(999, self.executor.active_order_oids)

    def test_non_blocking_cancel_order(self):
        import time
        mock_exchange = MagicMock()
        mock_exchange.cancel.return_value = {"status": "ok"}
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = True
        self.executor.active_order = {"oid": 777, "strategy_name": "Queue_Replenishment"}
        self.executor.active_order_oids = [777]

        res = self.executor.cancel_order(777)
        # Cancels immediately from local active_order
        self.assertTrue(res)
        self.assertIsNone(self.executor.active_order)
        self.assertNotIn(777, self.executor.active_order_oids)

        # Wait for thread pool worker to complete cancel transmission
        time.sleep(0.05)
        mock_exchange.cancel.assert_called_once_with("BTC", 777)

    def test_cancel_during_in_flight_order_dispatch(self):
        import time
        mock_exchange = MagicMock()

        def slow_order(*args, **kwargs):
            time.sleep(0.04)
            return {
                "status": "ok",
                "response": {
                    "type": "order",
                    "data": {"statuses": [{"resting": {"oid": 12345}}]}
                }
            }

        mock_exchange.order.side_effect = slow_order
        mock_exchange.cancel.return_value = {"status": "ok"}
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = True

        # 1. Place order (non-blocking)
        res = self.executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            post_only=True,
        )
        self.assertTrue(res.get("pending"))

        # 2. Cancel order while in wire transmission
        self.executor.cancel_order(-1)
        self.assertIsNone(self.executor.active_order)

        # 3. Wait for slow_order to finish
        time.sleep(0.08)

        # Order must be cancelled immediately on the exchange once OID is received
        mock_exchange.cancel.assert_called_once_with("BTC", 12345)
        self.assertIsNone(self.executor.active_order)
        self.assertEqual(len(self.executor.active_order_oids), 0)

    def test_cancel_during_in_flight_modify(self):
        import time
        mock_exchange = MagicMock()

        def slow_modify(*args, **kwargs):
            time.sleep(0.04)
            return {
                "status": "ok",
                "response": {
                    "type": "batchModify",
                    "data": {"statuses": [{"resting": {"oid": 55555}}]}
                }
            }

        mock_exchange.modify_order.side_effect = slow_modify
        mock_exchange.cancel.return_value = {"status": "ok"}
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = True
        self.executor.active_order = {"oid": 11111, "is_buy": True, "price": 80000.0, "size": 0.05, "time": 10.0}
        self.executor.active_order_oids = [11111]

        # 1. Start modify (non-blocking)
        self.executor.modify_limit_order(
            oid=11111,
            is_buy=True,
            size_btc=0.05,
            price=80010.0,
        )

        # 2. Cancel while modify is in flight
        self.executor.cancel_order(11111)
        self.assertIsNone(self.executor.active_order)

        # 3. Wait for slow_modify to finish
        time.sleep(0.08)

        # Replaced new order 55555 must be cancelled immediately on the exchange
        cancel_target_oids = [call.args[1] for call in mock_exchange.cancel.mock_calls if len(call.args) >= 2]
        self.assertIn(55555, cancel_target_oids)
        self.assertIsNone(self.executor.active_order)
        self.assertEqual(len(self.executor.active_order_oids), 0)

    def test_fast_fill_post_only_match_resubmits_with_gtc_for_exits(self):
        mock_exchange = MagicMock()
        mock_exchange.order.side_effect = [
            {
                "status": "ok",
                "response": {
                    "type": "order",
                    "data": {"statuses": [{"error": "Post only order would have immediately matched"}]}
                }
            },
            {
                "status": "ok",
                "response": {
                    "type": "order",
                    "data": {"statuses": [{"filled": {"oid": 9999, "avgPx": "80000.0", "totalSz": "0.05"}}]}
                }
            }
        ]
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = False
        self.executor.cached_position = 0.05

        res = self.executor.place_limit_order(
            is_buy=False,
            size_btc=0.05,
            price=80000.0,
            post_only=True,
            strategy_name="Queue_Replenishment_FastFill",
            is_exit=True,
        )
        self.assertEqual(mock_exchange.order.call_count, 2)
        self.assertEqual(res.get("status"), "ok")
        self.assertAlmostEqual(self.executor.cached_position, 0.0)

    def test_maker_entry_post_only_skips_gtc_resubmit(self):
        mock_exchange = MagicMock()
        mock_exchange.order.side_effect = [
            {
                "status": "ok",
                "response": {
                    "type": "order",
                    "data": {"statuses": [{"error": "Post only order would have immediately matched"}]}
                }
            }
        ]
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = False

        res = self.executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            post_only=True,
            strategy_name="Queue_Replenishment_FastFill",
            is_exit=False,
        )
        # Must not resubmit as GTC taker order for maker entry!
        self.assertEqual(mock_exchange.order.call_count, 1)
        self.assertIn("error", res["response"]["data"]["statuses"][0])
        self.assertIsNone(self.executor.active_order)
        self.assertAlmostEqual(self.executor.cached_position, 0.0)

    def test_in_flight_exit_order_flood_prevention(self):
        """Verifies that subsequent exit requests while an exit order is in-flight on the wire are suppressed."""
        import time
        mock_exchange = MagicMock()

        def slow_order(*args, **kwargs):
            time.sleep(0.05)
            return {
                "status": "ok",
                "response": {
                    "type": "order",
                    "data": {"statuses": [{"resting": {"oid": 77701}}]}
                }
            }

        mock_exchange.order.side_effect = slow_order
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = True
        self.executor.cached_position = 0.05
        self.executor.entry_price = 80000.0

        # Dispatch first exit order
        res1 = self.executor.place_limit_order(
            is_buy=False,
            size_btc=0.05,
            price=79900.0,
            post_only=False,
            is_exit=True,
            strategy_name="Queue_Replenishment",
        )
        self.assertTrue(res1.get("pending"))

        # Rapidly attempt 5 more exit orders while wire request is still running
        for _ in range(5):
            res_dup = self.executor.place_limit_order(
                is_buy=False,
                size_btc=0.05,
                price=79900.0,
                post_only=False,
                is_exit=True,
                strategy_name="Queue_Replenishment",
            )
            self.assertTrue(res_dup.get("pending"))

        # Wait for the in-flight wire call to finish
        time.sleep(0.08)

        # Exchange order must be called EXACTLY ONCE, not 6 times!
        self.assertEqual(mock_exchange.order.call_count, 1)

    def test_post_only_price_clamping_prevents_spread_crossing(self):
        """Verifies maker quotes never match or cross opposing top of book."""
        mock_exchange = MagicMock()
        mock_exchange.order.return_value = {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"resting": {"oid": 88801}}]}
            }
        }
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = False
        self.executor.last_best_bid = 50.0
        self.executor.last_best_ask = 50.1

        # Buy order at 50.15 (crossing best ask of 50.10) with post_only=True
        res_buy = self.executor.place_limit_order(
            is_buy=True,
            size_btc=1.0,
            price=50.15,
            post_only=True,
            is_exit=False,
            bypass_cooldown=True,
        )
        self.assertIsNotNone(res_buy)
        # Clamped limit price must be strictly < 50.10 (clamped to best_bid 50.0)
        call_kwargs = mock_exchange.order.call_args.kwargs
        self.assertLess(call_kwargs["limit_px"], 50.10)
        self.assertAlmostEqual(call_kwargs["limit_px"], 50.0)

        # Clear active order and sell order at 49.95 (crossing best bid of 50.0) with post_only=True
        self.executor.active_order = None
        res_sell = self.executor.place_limit_order(
            is_buy=False,
            size_btc=1.0,
            price=49.95,
            post_only=True,
            is_exit=False,
            bypass_cooldown=True,
        )
        self.assertIsNotNone(res_sell)
        call_kwargs_sell = mock_exchange.order.call_args.kwargs
        self.assertGreater(call_kwargs_sell["limit_px"], 50.0)
        self.assertAlmostEqual(call_kwargs_sell["limit_px"], 50.1)

    def test_live_trade_recording_and_accounting(self):
        """Verifies that entry and exit fills calculate PnL and record trade to auditor."""
        mock_exchange = MagicMock()
        mock_auditor = MagicMock()
        self.executor.exchange = mock_exchange
        self.executor.auditor = mock_auditor
        self.executor.non_blocking = False

        # 1. Entry Buy 0.05 BTC @ $80,000 fills immediately
        mock_exchange.order.return_value = {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": {"oid": 1001, "avgPx": "80000.0", "totalSz": "0.05"}}]}
            }
        }
        self.executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            post_only=False,
            is_exit=False,
            strategy_name="Queue_Replenishment",
        )
        self.assertAlmostEqual(self.executor.cached_position, 0.05)
        self.assertAlmostEqual(self.executor.entry_price, 80000.0)

        # 2. Exit Sell 0.05 BTC @ $80,200 fills immediately (+$10 gross)
        mock_exchange.order.return_value = {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": {"oid": 1002, "avgPx": "80200.0", "totalSz": "0.05"}}]}
            }
        }
        self.executor.place_limit_order(
            is_buy=False,
            size_btc=0.05,
            price=80200.0,
            post_only=False,
            is_exit=True,
            strategy_name="Queue_Replenishment",
            exit_reason="TAKE_PROFIT",
        )
        self.assertAlmostEqual(self.executor.cached_position, 0.0)
        self.assertEqual(len(self.executor.completed_trades), 1)
        tr = self.executor.completed_trades[0]
        self.assertAlmostEqual(tr["gross_pnl_usd"], 10.0)
        self.assertGreater(tr["net_pnl_usd"], 0.0)
        self.assertEqual(tr["exit_reason"], "TAKE_PROFIT")

        # Verify auditor.record_trade was called
        mock_auditor.record_trade.assert_called_once()
        audit_call = mock_auditor.record_trade.call_args.kwargs
        self.assertEqual(audit_call["strategy_name"], "Queue_Replenishment")
        self.assertEqual(audit_call["side"], "LONG")
        self.assertAlmostEqual(audit_call["gross_pnl_usd"], 10.0)
        self.assertEqual(audit_call["exit_reason"], "TAKE_PROFIT")
        self.assertEqual(audit_call["order_id"], 1002)

    def test_modify_limit_order_exit_fill_records_trade_accounting(self):
        """Verifies that an exit order filled via modify_limit_order computes PnL and records to auditor."""
        mock_exchange = MagicMock()
        mock_auditor = MagicMock()
        self.executor.exchange = mock_exchange
        self.executor.auditor = mock_auditor
        self.executor.non_blocking = False
        self.executor.cached_position = 0.05
        self.executor.entry_price = 80000.0
        self.executor.entry_fee_usd = 0.60
        self.executor.position_strategy = "Queue_Replenishment"

        mock_exchange.modify_order.return_value = {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": {"oid": 5501, "avgPx": "80400.0", "totalSz": "0.05"}}]}
            }
        }

        res = self.executor.modify_limit_order(
            oid=5500,
            is_buy=False,
            size_btc=0.05,
            price=80400.0,
            post_only=False,
            is_exit=True,
            strategy_name="Queue_Replenishment",
            exit_reason="TAKE_PROFIT_ESCALATE",
        )

        self.assertIsNotNone(res)
        self.assertAlmostEqual(self.executor.cached_position, 0.0)
        self.assertEqual(len(self.executor.completed_trades), 1)
        tr = self.executor.completed_trades[0]
        self.assertEqual(tr["strategy"], "Queue_Replenishment")
        self.assertEqual(tr["exit_reason"], "TAKE_PROFIT_ESCALATE")
        self.assertAlmostEqual(tr["gross_pnl_usd"], 20.0)  # (80400 - 80000) * 0.05 = 20.0
        self.assertGreater(tr["net_pnl_usd"], 0.0)

        mock_auditor.record_trade.assert_called_once()
        audit_call = mock_auditor.record_trade.call_args.kwargs
        self.assertEqual(audit_call["exit_reason"], "TAKE_PROFIT_ESCALATE")
        self.assertEqual(audit_call["order_id"], 5501)

    def test_passive_resting_fill_records_trade_when_szi_zero(self):
        """Verifies passive resting fill is detected in _do_sync even when Hyperliquid returns szi: 0.0 in assetPositions."""
        mock_info = MagicMock()
        mock_auditor = MagicMock()
        self.executor.info = mock_info
        self.executor.auditor = mock_auditor
        self.executor.cached_position = 0.10
        self.executor.entry_price = 80000.0
        self.executor.position_strategy = "Queue_Replenishment"
        self.executor.active_order = {"oid": 777, "price": 80100.0}

        # Hyperliquid returns assetPositions with the coin present, but szi: "0.0"
        mock_info.clearinghouse_state.return_value = {
            "marginSummary": {"accountValue": "10000.0", "totalMarginUsed": "0.0"},
            "assetPositions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "0.0",
                        "entryPx": "0.0",
                    }
                }
            ],
        }
        mock_info.open_orders.return_value = []

        self.executor.sync_state(force=True)

        self.assertAlmostEqual(self.executor.cached_position, 0.0)
        self.assertEqual(len(self.executor.completed_trades), 1)
        tr = self.executor.completed_trades[0]
        self.assertEqual(tr["exit_reason"], "PASSIVE_MAKER_FILL")
        self.assertEqual(tr["strategy"], "Queue_Replenishment")
        self.assertAlmostEqual(tr["gross_pnl_usd"], 10.0)  # (80100 - 80000) * 0.10 = 10.0

        mock_auditor.record_trade.assert_called_once()
        audit_call = mock_auditor.record_trade.call_args.kwargs
        self.assertEqual(audit_call["exit_reason"], "PASSIVE_MAKER_FILL")

    def test_reduce_only_rejection_clears_cached_position_and_syncs(self):
        """Verifies reduce-only rejection immediately zeros cached_position and triggers state sync."""
        mock_exchange = MagicMock()
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = False
        self.executor.cached_position = 0.05
        self.executor.entry_price = 80000.0
        self.executor.position_strategy = "Queue_Replenishment"
        self.executor.sync_state = MagicMock()

        mock_exchange.order.return_value = {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"error": "Reduce only order would increase position. asset=110022"}]}
            }
        }

        res = self.executor.place_limit_order(
            is_buy=False,
            size_btc=0.05,
            price=80200.0,
            post_only=False,
            is_exit=True,
            strategy_name="Queue_Replenishment",
        )

        self.assertAlmostEqual(self.executor.cached_position, 0.0)
        self.assertIsNone(self.executor.position_strategy)
        self.assertIsNone(self.executor.active_order)
        self.executor.sync_state.assert_called_with(force=True)

    def test_modify_limit_order_reduce_only_rejection_clears_position(self):
        """Verifies modify_limit_order reduce-only rejection immediately zeros cached_position and does not re-place."""
        mock_exchange = MagicMock()
        self.executor.exchange = mock_exchange
        self.executor.non_blocking = False
        self.executor.cached_position = 0.05
        self.executor.entry_price = 80000.0
        self.executor.position_strategy = "Queue_Replenishment"
        self.executor.sync_state = MagicMock()
        self.executor.place_limit_order = MagicMock()

        mock_exchange.modify_order.return_value = {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"error": "Reduce only order would increase position."}]}
            }
        }

        res = self.executor.modify_limit_order(
            oid=999,
            is_buy=False,
            size_btc=0.05,
            price=80200.0,
            post_only=False,
            is_exit=True,
            strategy_name="Queue_Replenishment",
        )

        self.assertAlmostEqual(self.executor.cached_position, 0.0)
        self.assertIsNone(self.executor.position_strategy)
        self.assertIsNone(self.executor.active_order)
        self.executor.place_limit_order.assert_not_called()
        self.executor.sync_state.assert_called_with(force=True)

    def test_post_only_price_clamping_with_missing_opposite_book_tick_step(self):
        """Verifies _clamp_post_only_price uses significant-figure tick step when opposite book is missing."""
        self.executor.last_best_bid = 0.0
        self.executor.last_best_ask = 80000.0
        self.executor.max_price_decimals = 1

        # Buy order at 80005 (above last_best_ask of 80000) with last_best_bid = 0
        clamped_px = self.executor._clamp_post_only_price(80005.0, is_buy=True)
        # Clamped price must be strictly < 80000.0, and rounded properly conforming to tick rules
        self.assertLess(clamped_px, 80000.0)
        self.assertAlmostEqual(clamped_px, 79999.0)


if __name__ == "__main__":
    unittest.main()
