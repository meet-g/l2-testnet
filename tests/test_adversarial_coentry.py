"""Adversarial Verification & Stress Test Suite for Co-Entry Dynamics,
Position Sizing Discounts, State Corruption Freedom, and Deadlock Absence.

Tests:
1. Long and Short conviction hurdle (+0.04) boundary conditions.
2. Position sizing discount (50% reduction) and boundary threshold anomalies.
3. Order-dependent asymmetry during simultaneous single-tick entries.
4. Opposite-direction co-existence (simultaneous long + short hedging).
5. State isolation and deadlock freedom during asynchronous lifecycle exits.
"""

import unittest
from typing import Dict, Any

from config import BacktestConfig, MarketConfig
from engine.backtester import EdgeEvaluator, StrategyState


class TestAdversarialCoEntry(unittest.TestCase):
    """Adversarial challenge tests for engine/backtester.py co-entry and sizing logic."""

    def setUp(self):
        self.market_cfg_btc = MarketConfig(coin="BTC", maker_fee_bps=1.5, taker_fee_bps=4.5)
        self.market_cfg_hype = MarketConfig(coin="HYPE", maker_fee_bps=1.5, taker_fee_bps=4.5)
        self.bt_cfg = BacktestConfig(
            order_size_btc=0.1,
            entry_threshold=0.80,
            take_profit_bps=20.0,
            stop_loss_bps=8.0,
            slippage_bps=0.2,
            max_spread_bps=5.0,
            horizons_seconds=[],
        )
        self.strategy_defs = {
            "Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER"),
            "Convexity_Cascade": ("ConvexityCascade", "MAKER"),
            "Momentum_Expansion": ("MomentumExpansion", "MAKER"),
            "Queue_Replenishment": ("QueueReplenishment", "HEDGED_MAKER"),
        }
        self.strategy_params = {
            "Hedged_Convexity": {"entry_threshold": 0.80, "order_size_btc": 0.1, "min_volatility_bps": 0.0, "coentry_group": "triad"},
            "Convexity_Cascade": {"entry_threshold": 0.80, "order_size_btc": 0.1, "min_volatility_bps": 0.0, "coentry_group": "triad"},
            "Momentum_Expansion": {"entry_threshold": 0.80, "order_size_btc": 0.1, "min_volatility_bps": 0.0, "coentry_group": "triad"},
            "Queue_Replenishment": {"entry_threshold": 0.80, "order_size_btc": 0.1, "min_volatility_bps": 0.0, "coentry_group": "triad"},
        }

    def test_01_hurdle_blocks_coentry_below_hurdle_long(self):
        """Verify that when Strat A is LONG, Strat B is blocked if score < entry_thresh + 0.04."""
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs=self.strategy_defs,
            strategy_params=self.strategy_params,
        )

        # Step 1: Strat A (Hedged_Convexity) enters LONG at t=1000 with score=0.85 (>= 0.80)
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.99,
            best_ask=100.01,
            signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.0},
        )
        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position)
        self.assertFalse(evaluator.strategies["Queue_Replenishment"].is_in_position)
        self.assertAlmostEqual(evaluator.strategies["Hedged_Convexity"].position_btc, 0.1)

        # Step 2: Strat B (Queue_Replenishment) triggers with score=0.82 (>= 0.80 but < 0.84 hurdle)
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.0,
            best_bid=99.99,
            best_ask=100.01,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": 0.82},
        )
        # Strat B MUST BE BLOCKED
        self.assertFalse(
            evaluator.strategies["Queue_Replenishment"].is_in_position,
            "Queue_Replenishment entered despite failing the +0.04 conviction hurdle!",
        )

    def test_02_hurdle_allows_coentry_at_or_above_hurdle_long(self):
        """Verify that when Strat A is LONG, Strat B enters if score >= entry_thresh + 0.04."""
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs=self.strategy_defs,
            strategy_params=self.strategy_params,
        )

        # Strat A enters LONG
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.0},
        )
        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position)

        # Strat B triggers with score = 0.841 (clears IEEE float 0.8400000000000001 hurdle)
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": 0.841},
        )
        self.assertTrue(
            evaluator.strategies["Queue_Replenishment"].is_in_position,
            "Queue_Replenishment was blocked even though score met entry_thresh + 0.04!",
        )
        # Position size must be discounted by 50% (0.1 * 0.5 = 0.05)
        self.assertAlmostEqual(
            evaluator.strategies["Queue_Replenishment"].position_btc,
            0.05,
            places=4,
            msg="Queue_Replenishment did not receive 50% position sizing discount on co-entry!",
        )

    def test_03_hurdle_blocks_and_allows_short(self):
        """Verify hurdle and 50% discount for bearish SHORT co-entries."""
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs=self.strategy_defs,
            strategy_params=self.strategy_params,
        )

        # Strat A enters SHORT at score = -0.85 (<= -0.80)
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": -0.85, "QueueReplenishment": 0.0},
        )
        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position)
        self.assertAlmostEqual(evaluator.strategies["Hedged_Convexity"].position_btc, -0.1)

        # Strat B gets score = -0.82 (> -0.84 hurdle) -> must be blocked
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": -0.82},
        )
        self.assertFalse(evaluator.strategies["Queue_Replenishment"].is_in_position)

        # Strat B gets score = -0.841 (<= -0.84 hurdle) -> enters SHORT with 50% size (-0.05)
        evaluator.record_step(
            timestamp_ms=3000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": -0.841},
        )
        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position)
        self.assertAlmostEqual(evaluator.strategies["Queue_Replenishment"].position_btc, -0.05, places=4)

    def test_04_opposite_direction_coexistence_no_hurdle_no_discount(self):
        """Verify that opposite direction positions (LONG vs SHORT) do NOT trigger hurdle or discount."""
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs=self.strategy_defs,
            strategy_params=self.strategy_params,
        )

        # Strat A enters LONG
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.0},
        )
        self.assertAlmostEqual(evaluator.strategies["Hedged_Convexity"].position_btc, 0.1)

        # Strat B gets BEARISH signal with score = -0.81 (valid entry, but < 0.84 hurdle)
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": -0.81},
        )
        # Should enter SHORT with FULL size (0.1) because directions are opposite!
        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position)
        self.assertAlmostEqual(
            evaluator.strategies["Queue_Replenishment"].position_btc,
            -0.1,
            places=4,
            msg="Opposite direction entry should have full size (-0.1), not discounted!",
        )

    def test_05_simultaneous_entry_order_asymmetry(self):
        """CRITICAL CHALLENGE: Simultaneous entry on the exact same tick.
        The first strategy in strategy_names gets full size (0.1) and normal threshold.
        The second strategy in strategy_names is treated as a co-entry (50% size and +0.04 hurdle).
        """
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs=self.strategy_defs,
            strategy_params=self.strategy_params,
        )

        # Both signal on tick t=1000 with score = 0.82
        # Hedged_Convexity is first in list -> enters with size 0.1
        # Queue_Replenishment is last in list -> sees Hedged_Convexity in position -> hurdle 0.84 -> BLOCKED!
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.82, "QueueReplenishment": 0.82},
        )

        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position)
        self.assertAlmostEqual(evaluator.strategies["Hedged_Convexity"].position_btc, 0.1)
        self.assertFalse(
            evaluator.strategies["Queue_Replenishment"].is_in_position,
            "Due to iteration order, the second strategy was blocked by the first on the exact same tick!",
        )

    def test_06_simultaneous_entry_order_inversion(self):
        """If strategy_defs order is inverted, Queue_Replenishment gets full size and Hedged_Convexity is blocked!"""
        inverted_defs = {
            "Queue_Replenishment": ("QueueReplenishment", "HEDGED_MAKER"),
            "Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER"),
        }
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs=inverted_defs,
            strategy_params=self.strategy_params,
        )

        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.82, "QueueReplenishment": 0.82},
        )

        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position)
        self.assertAlmostEqual(evaluator.strategies["Queue_Replenishment"].position_btc, 0.1)
        self.assertFalse(evaluator.strategies["Hedged_Convexity"].is_in_position)

    def test_07_state_isolation_and_no_deadlocks_on_exit(self):
        """Verify that when Strat A exits (via TP, SL, or hedge), Strat B's state remains intact,
        and subsequent entries for Strat A are unblocked without deadlocks.
        """
        params_with_custom_tp = {
            "Hedged_Convexity": {"entry_threshold": 0.80, "order_size_btc": 0.1, "take_profit_bps": 20.0, "min_volatility_bps": 0.0, "coentry_group": "triad"},
            "Queue_Replenishment": {"entry_threshold": 0.80, "order_size_btc": 0.1, "take_profit_bps": 40.0, "min_volatility_bps": 0.0, "coentry_group": "triad"},
        }
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs=self.strategy_defs,
            strategy_params=params_with_custom_tp,
        )

        # Both enter LONG (score 0.85 clears hurdle 0.84)
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.85},
        )
        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position)
        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position)
        self.assertAlmostEqual(evaluator.strategies["Hedged_Convexity"].position_btc, 0.1)
        self.assertAlmostEqual(evaluator.strategies["Queue_Replenishment"].position_btc, 0.05)

        # Price rises to 100.30 (+30 bps).
        # Hedged_Convexity has tp_bps=20 -> EXITS TAKE_PROFIT
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.30,
            best_bid=100.295,
            best_ask=100.305,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": 0.0},
        )
        self.assertFalse(evaluator.strategies["Hedged_Convexity"].is_in_position)
        # Verify Hedged_Convexity recorded a trade
        self.assertEqual(len(evaluator.strategies["Hedged_Convexity"].trades), 1)
        hc_trade = evaluator.strategies["Hedged_Convexity"].trades[0]
        self.assertEqual(hc_trade.exit_reason, "TAKE_PROFIT")
        self.assertGreater(hc_trade.net_pnl_usd, 0.0)

        # Queue_Replenishment is still open and uncorrupted
        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position)
        self.assertAlmostEqual(evaluator.strategies["Queue_Replenishment"].position_btc, 0.05)

        # Now price drops to 99.80 -> Queue_Replenishment exits via trailing stop or hedge
        evaluator.record_step(
            timestamp_ms=3000,
            mid_price=99.80,
            best_bid=99.795,
            best_ask=99.805,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": -0.50},
        )
        self.assertFalse(evaluator.strategies["Queue_Replenishment"].is_in_position)
        self.assertEqual(len(evaluator.strategies["Queue_Replenishment"].trades), 1)

        # Both strategies are now flat. Verify neither is locked or deadlocked.
        evaluator.strategies["Hedged_Convexity"].last_exit_was_loss = False
        evaluator.record_step(
            timestamp_ms=100_000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.0},
        )
        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position)
        self.assertAlmostEqual(evaluator.strategies["Hedged_Convexity"].position_btc, 0.1)

    def test_08_size_discount_boundary_anomaly(self):
        """CRITICAL CHALLENGE: Check if size discount on non-BTC coin causes size explosion
        if base order_size is around 1.5.
        Lines 611-618:
        sz = sz * 0.5
        if coin != 'BTC' and mid_price > 0 and sz <= 1.0:
            sz = round(sz * (85000.0 / mid_price), 2)
        elif sz > 1.0:
            sz = round(sz, 2)
        """
        strat_params_custom = {
            "Hedged_Convexity": {"entry_threshold": 0.80, "order_size_btc": 1.5, "min_volatility_bps": 0.0, "coentry_group": "triad"},
            "Queue_Replenishment": {"entry_threshold": 0.80, "order_size_btc": 1.5, "min_volatility_bps": 0.0, "coentry_group": "triad"},
        }
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_hype,  # HYPE, mid_price = 25.0
            bt_cfg=self.bt_cfg,
            strategy_defs={
                "Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER"),
                "Queue_Replenishment": ("QueueReplenishment", "HEDGED_MAKER"),
            },
            strategy_params=strat_params_custom,
        )

        # Strat A enters: sz = 1.5 > 1.0 -> sz = 1.5
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=25.0,
            best_bid=24.995,
            best_ask=25.005,
            signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.0},
        )
        sz_a = evaluator.strategies["Hedged_Convexity"].position_btc
        self.assertAlmostEqual(sz_a, 1.5)

        # Strat B enters with co-entry discount: base sz = 1.5 > 1.0 (is_coin_units=True).
        # Sizing discount halves size: 1.5 * 0.5 = 0.75 coins ($18.75 notional).
        # Does NOT trigger non-BTC scaling because is_coin_units was latched before discounting.
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=25.0,
            best_bid=24.995,
            best_ask=25.005,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": 0.85},
        )
        sz_b = evaluator.strategies["Queue_Replenishment"].position_btc
        self.assertEqual(sz_b, 0.75, "Expected 50% discount to 0.75 coins without scaling explosion!")

    def test_09_ieee754_hurdle_rejection_boundary(self):
        """CRITICAL CHALLENGE: Demonstrate that IEEE 754 float representation causes
        rejection at exact hurdle score (e.g. entry_threshold=0.80, hurdle=0.84, score=0.84).
        0.80 + 0.04 evaluates to 0.8400000000000001, so score < hurdle is TRUE!
        """
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs=self.strategy_defs,
            strategy_params=self.strategy_params,
        )

        # Strat A enters LONG
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.0},
        )
        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position)

        # Strat B triggers at EXACT score = 0.84
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": 0.84},
        )
        # Because of IEEE 754 precision fix (round(entry_thresh + 0.04, 6) with 1e-7 epsilon),
        # exact hurdle score (0.84) is accepted!
        is_in_pos = evaluator.strategies["Queue_Replenishment"].is_in_position
        self.assertTrue(
            is_in_pos,
            "Exact hurdle score (0.84) must be accepted with epsilon tolerance!",
        )

    def test_10_four_strategy_state_isolation_and_stress(self):
        """CRITICAL CHALLENGE: 4-Strategy simultaneous lifecycle stress test.
        Ensures all 4 strategies (HC, CC, ME, QR) can execute simultaneously,
        exit independently (TP, SL, Hedge, Trailing Stop), track equity cleanly,
        and never deadlock or corrupt shared evaluator state.
        """
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs=self.strategy_defs,
            strategy_params={
                "Hedged_Convexity": {"entry_threshold": 0.80, "order_size_btc": 0.1, "take_profit_bps": 20.0, "stop_loss_bps": 8.0, "hedge_trigger_loss_bps": -3.5, "hedge_reversal_threshold": 0.20, "coentry_group": "triad"},
                "Convexity_Cascade": {"entry_threshold": 0.80, "order_size_btc": 0.1, "take_profit_bps": 25.0, "stop_loss_bps": 8.0, "hedge_trigger_loss_bps": -4.0, "hedge_reversal_threshold": 0.15, "coentry_group": "triad"},
                "Momentum_Expansion": {"entry_threshold": 0.80, "order_size_btc": 0.1, "take_profit_bps": 30.0, "stop_loss_bps": 8.0, "hedge_trigger_loss_bps": -3.5, "hedge_reversal_threshold": 0.20, "coentry_group": "triad"},
                "Queue_Replenishment": {"entry_threshold": 0.80, "order_size_btc": 0.1, "take_profit_bps": 35.0, "stop_loss_bps": 8.0, "hedge_trigger_loss_bps": -3.5, "hedge_reversal_threshold": -0.15, "coentry_group": "triad"},
            },
        )

        # Step 1: All 4 signal strongly bullish (score = 0.88, clears 0.84 hurdle)
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={
                "HedgedConvexity": 0.88,
                "ConvexityCascade": 0.88,
                "MomentumExpansion": 0.88,
                "QueueReplenishment": 0.88,
            },
        )

        # Hedged_Convexity enters first -> full size 0.1
        self.assertAlmostEqual(evaluator.strategies["Hedged_Convexity"].position_btc, 0.1)
        # All subsequent strategies see HC in position -> 50% discount -> size 0.05
        self.assertAlmostEqual(evaluator.strategies["Convexity_Cascade"].position_btc, 0.05)
        self.assertAlmostEqual(evaluator.strategies["Momentum_Expansion"].position_btc, 0.05)
        self.assertAlmostEqual(evaluator.strategies["Queue_Replenishment"].position_btc, 0.05)

        # Step 2: Price rises to 100.22 (+22 bps)
        # Hedged_Convexity exits on TP (+20 bps). Others remain open!
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.22,
            best_bid=100.215,
            best_ask=100.225,
            signals={"HedgedConvexity": 0.0, "ConvexityCascade": 0.5, "MomentumExpansion": 0.5, "QueueReplenishment": 0.5},
        )
        self.assertFalse(evaluator.strategies["Hedged_Convexity"].is_in_position)
        self.assertEqual(evaluator.strategies["Hedged_Convexity"].trades[0].exit_reason, "TAKE_PROFIT")
        self.assertTrue(evaluator.strategies["Convexity_Cascade"].is_in_position)
        self.assertTrue(evaluator.strategies["Momentum_Expansion"].is_in_position)
        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position)

        # Step 3: Price rises to 100.27 (+27 bps)
        # Convexity_Cascade exits on TP (+25 bps). ME and QR remain open!
        evaluator.record_step(
            timestamp_ms=3000,
            mid_price=100.27,
            best_bid=100.265,
            best_ask=100.275,
            signals={"HedgedConvexity": 0.0, "ConvexityCascade": 0.0, "MomentumExpansion": 0.5, "QueueReplenishment": 0.5},
        )
        self.assertFalse(evaluator.strategies["Convexity_Cascade"].is_in_position)
        self.assertEqual(evaluator.strategies["Convexity_Cascade"].trades[0].exit_reason, "TAKE_PROFIT")
        self.assertTrue(evaluator.strategies["Momentum_Expansion"].is_in_position)
        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position)

        # Step 4: Rapid reversal: mid drops to 99.95 (-5 bps from entry) with score = -0.30
        # ME and QR hit DEFENSIVE_MAKER_HEDGE (loss <= -3.5 bps, reversal threshold met)
        evaluator.record_step(
            timestamp_ms=4000,
            mid_price=99.95,
            best_bid=99.945,
            best_ask=99.955,
            signals={"HedgedConvexity": 0.0, "ConvexityCascade": 0.0, "MomentumExpansion": -0.30, "QueueReplenishment": -0.30},
        )
        self.assertFalse(evaluator.strategies["Momentum_Expansion"].is_in_position)
        self.assertFalse(evaluator.strategies["Queue_Replenishment"].is_in_position)
        self.assertEqual(evaluator.strategies["Momentum_Expansion"].trades[0].exit_reason, "DEFENSIVE_MAKER_HEDGE")
        self.assertEqual(evaluator.strategies["Queue_Replenishment"].trades[0].exit_reason, "DEFENSIVE_MAKER_HEDGE")

        # Verify all 4 strategies have exactly 1 trade, positive/consistent cash accounting, and 0 deadlock
        for s_name, st in evaluator.strategies.items():
            self.assertEqual(len(st.trades), 1, f"{s_name} trade count mismatch")
            self.assertEqual(st.position_btc, 0.0, f"{s_name} still has open position")
            self.assertGreater(st.cash_usd, 0.0, f"{s_name} cash balance corrupted")

    def test_11_cross_group_decoupling_no_hurdle_no_discount(self):
        """Verify that strategies in decoupled coentry_groups (e.g. triad vs queue_replenishment)
        do not block each other with conviction hurdles and do not apply sizing discounts.
        """
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs=self.strategy_defs,
            strategy_params={
                "Hedged_Convexity": {"entry_threshold": 0.80, "order_size_btc": 0.1, "min_volatility_bps": 0.0, "coentry_group": "triad"},
                "Queue_Replenishment": {"entry_threshold": 0.80, "order_size_btc": 0.1, "min_volatility_bps": 0.0, "coentry_group": "queue_replenishment"},
            },
        )
        # Step 1: Strat A (Hedged_Convexity in triad) enters LONG
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.0},
        )
        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position)
        self.assertAlmostEqual(evaluator.strategies["Hedged_Convexity"].position_btc, 0.1)

        # Step 2: Strat B (Queue_Replenishment in queue_replenishment) triggers with score = 0.82
        # (clears base threshold 0.80, but would fail 0.84 hurdle if in the same group).
        # Because groups are decoupled, Strat B MUST enter and MUST NOT be discounted!
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": 0.82},
        )
        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position, "Cross-group coentry should not be blocked!")
        self.assertAlmostEqual(evaluator.strategies["Queue_Replenishment"].position_btc, 0.1, places=4, msg="Cross-group coentry should receive full size (0.1)!")


if __name__ == "__main__":
    unittest.main()

