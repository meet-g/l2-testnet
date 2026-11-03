"""Tests for Hyperliquid execution speed optimizations:
1. Inside-Spread Penny-Jumping (Maker Queue Rank #1)
2. Dynamic Taker Crossing with TIF Ioc
3. Native On-Chain TPSL Bracket Orders (grouping='normalTpsl')
4. Priority Fee Sequencer Bidding (Optimization 5: PriorityGrouping {'p': int})
5. Priority ALO Reduce-Only Protocol Guard & Fast-Fill IOC Escalation
"""

import unittest
from unittest.mock import MagicMock, patch
from config import AppConfig, LiveExecutionConfig
from engine.live_executor import LiveOrderExecutor


class TestExecutionOptimizations(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.config.account.account_address = "0x76cfd21f8a84c670b09489d7b9015c92c4222416"
        self.config.account.secret_key = "0x" + "1" * 64
        self.config.market.coin = "BTC"
        self.config.live_execution = LiveExecutionConfig(
            active_strategy="Instant_FastFill",
            order_size_btc=0.05,
            penny_jumping=True,
            use_ioc_on_marketable=True,
            use_native_tpsl=True,
            priority_fee_bps=0.0,
        )

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_penny_jumping_inside_spread_captures_head_of_book(self, mock_info, mock_exchange):
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_exchange.return_value
        executor.last_best_bid = 80000.0
        executor.last_best_ask = 80005.0  # $5.00 wide spread

        # Clamping a buy order that attempted to match ask (80005.0)
        # Should penny-jump to 80000.0 + 1.0 = 80001.0 (Queue Rank #1)
        clamped_bid = executor._clamp_post_only_price(80005.0, is_buy=True)
        self.assertEqual(clamped_bid, 80001.0)

        # Clamping a sell order that attempted to match bid (80000.0)
        # Should penny-jump to 80005.0 - 1.0 = 80004.0 (Queue Rank #1)
        clamped_ask = executor._clamp_post_only_price(80000.0, is_buy=False)
        self.assertEqual(clamped_ask, 80004.0)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_dynamic_ioc_taker_escalation(self, mock_info, mock_exchange):
        mock_ex = mock_exchange.return_value
        mock_ex.order.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 9001}}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.use_ioc_on_marketable = True

        # Non-post-only entry should dynamically escalate to TIF 'Ioc'
        executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            post_only=False,
            strategy_name="Instant_FastFill",
        )

        mock_ex.order.assert_called_once()
        call_kwargs = mock_ex.order.call_args.kwargs
        self.assertEqual(call_kwargs["order_type"], {"limit": {"tif": "Ioc"}})

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_priority_fee_grouping_dispatch(self, mock_info, mock_exchange):
        mock_ex = mock_exchange.return_value
        mock_ex.bulk_orders.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 9002}}]}},
        }
        self.config.live_execution.priority_fee_bps = 1.0  # 1.0 bp priority fee -> p=10,000
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.priority_fee_bps = 1.0

        executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            post_only=True,
            strategy_name="Instant_FastFill",
        )

        mock_ex.bulk_orders.assert_called_once()
        args, kwargs = mock_ex.bulk_orders.call_args
        self.assertEqual(kwargs.get("grouping"), {"p": 10000})

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_tier_1_priority_fee_grouping_p_5000(self, mock_info, mock_exchange):
        mock_ex = mock_exchange.return_value
        mock_ex.bulk_orders.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 9008}}]}},
        }
        # Configure Tier 1 priority fee: 0.5 bps -> p = 5,000
        self.config.strategies.live_execution.priority_fee_bps = 0.5
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex

        # Verify executor resolved 0.5 bps
        self.assertEqual(executor.priority_fee_bps, 0.5)

        executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            post_only=True,
            strategy_name="Instant_FastFill",
        )

        mock_ex.bulk_orders.assert_called_once()
        args, kwargs = mock_ex.bulk_orders.call_args
        self.assertEqual(kwargs.get("grouping"), {"p": 5000})

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_priority_alo_reduce_only_downgrades_grouping_to_na(self, mock_info, mock_exchange):
        """Verifies Hyperliquid protocol guard: Priority ALO orders cannot be reduce only."""
        mock_ex = mock_exchange.return_value
        mock_ex.order.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 9015}}]}},
        }
        self.config.live_execution.priority_fee_bps = 1.0  # Priority fee enabled
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.priority_fee_bps = 1.0
        executor.cached_position = 0.05  # Active long position

        # Submitting passive exit with ALO and reduce_only
        executor.place_limit_order(
            is_buy=False,
            size_btc=0.05,
            price=80200.0,
            post_only=True,
            is_exit=True,
            reduce_only=True,
            strategy_name="Instant_FastFill",
        )

        # Should downgrade grouping to 'na' and call standard order() so Hyperliquid does not reject
        mock_ex.order.assert_called_once()
        mock_ex.bulk_orders.assert_not_called()

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_post_only_match_rejection_escalates_to_ioc_taker(self, mock_info, mock_exchange):
        """Verifies that Post-only match rejection escalates to IOC taker fill when fast_fill_enabled is True."""
        mock_ex = mock_exchange.return_value
        # First call fails with Post only order would have immediately matched, second succeeds
        mock_ex.order.side_effect = [
            {"status": "ok", "response": {"data": {"statuses": [{"error": "Post only order would have immediately matched, bbo was 80000.0@80000.0"}]}}},
            {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 9020}}]}}},
        ]
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex
        executor.priority_fee_bps = 0.0

        res = executor.place_limit_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            post_only=True,
            strategy_name="Instant_FastFill",
        )

        self.assertEqual(mock_ex.order.call_count, 2)
        # Second call must be post_only=False with TIF 'Ioc'
        second_call = mock_ex.order.call_args_list[1]
        self.assertEqual(second_call.kwargs["order_type"], {"limit": {"tif": "Ioc"}})

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_native_atomic_bracket_order_normalTpsl(self, mock_info, mock_exchange):
        mock_ex = mock_exchange.return_value
        mock_ex.bulk_orders.return_value = {
            "status": "ok",
            "response": {"data": {"statuses": [{"resting": {"oid": 9003}}, {"resting": {"oid": 9004}}, {"resting": {"oid": 9005}}]}},
        }
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_ex

        executor.place_bracket_order(
            is_buy=True,
            size_btc=0.05,
            price=80000.0,
            tp_price=80150.0,
            sl_price=79900.0,
            post_only=True,
            strategy_name="Instant_FastFill",
        )

        mock_ex.bulk_orders.assert_called_once()
        orders, kwargs = mock_ex.bulk_orders.call_args
        order_list = orders[0]
        self.assertEqual(len(order_list), 3)

        # Check Entry order
        self.assertTrue(order_list[0]["is_buy"])
        self.assertFalse(order_list[0]["reduce_only"])
        self.assertEqual(order_list[0]["order_type"], {"limit": {"tif": "Alo"}})

        # Check TP order
        self.assertFalse(order_list[1]["is_buy"])
        self.assertTrue(order_list[1]["reduce_only"])
        self.assertEqual(order_list[1]["order_type"]["trigger"]["tpsl"], "tp")
        self.assertEqual(order_list[1]["order_type"]["trigger"]["triggerPx"], 80150.0)

        # Check SL order
        self.assertFalse(order_list[2]["is_buy"])
        self.assertTrue(order_list[2]["reduce_only"])
        self.assertEqual(order_list[2]["order_type"]["trigger"]["tpsl"], "sl")
        self.assertEqual(order_list[2]["order_type"]["trigger"]["triggerPx"], 79900.0)

        # Check grouping parameter
        self.assertEqual(kwargs.get("grouping"), "normalTpsl")


if __name__ == "__main__":
    unittest.main()
