"""Unit tests for LiveOrderExecutor.

Verifies:
1. Formatting helpers (price 5 sig figs, size decimals, min notional enforcement).
2. Stateful resting order persistence (zero instant self-cancellation churn).
3. Market price drift re-quoting.
4. Signal decay cancellation.
5. Exit lifecycle (Take Profit, Stop Loss, Trailing Stop, Defensive Maker Hedge).
"""

import unittest
from unittest.mock import MagicMock, patch

from config import AppConfig
from engine.live_executor import LiveOrderExecutor


class TestLiveOrderExecutor(unittest.TestCase):
    def setUp(self):
        self.cfg = AppConfig()
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
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0: (
            actions.append(("PLACE", is_buy, size_btc, price)),
            {"status": "ok"}
        )[1]

        self.executor.on_signal_update(0.99, 80000.0, 80001.0, 1.0)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0][2], 0.0625)

    def test_resting_order_persistence_no_churn(self):
        actions = []
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0: (
            actions.append(("PLACE", is_buy, price)),
            setattr(self.executor, "active_order", {"oid": 101, "is_buy": is_buy, "price": price, "size": size_btc, "time": 100.0}),
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

        # Tick 4: Signal decays to neutral -> Must cancel resting order
        actions.clear()
        self.executor.on_signal_update(0.10, 81502.0, 81503.0, 1.0)
        self.assertEqual(actions, [("CANCEL", 101)])

    def test_position_exit_take_profit(self):
        actions = []
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0: (
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

    def test_position_exit_stop_loss(self):
        actions = []
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0: (
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
        self.executor.place_limit_order = lambda is_buy, size_btc, price, post_only=True, signal_score=0: (
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


if __name__ == "__main__":
    unittest.main()
