"""Empirical Adversarial Stress Harness for M4 Remediation Re-Gate.

Testing:
1. Sizing order-of-operations boundary matrix:
   - Order sizes in (1.0, 2.0] coins under same-group coentry halving (assert sizes in (0.5, 1.0] coins, no multiplier explosion).
   - Order sizes in fractional BTC (0.001 to 1.0) under non-BTC coin conversion (HYPE, SOL, ETH, DOGE).
   - Exact boundary sz == 1.0 vs sz == 1.0001.
2. IEEE 754 precision tolerance at hurdle boundaries:
   - Floating point arithmetic exact bounds (0.80 + 0.04 = 0.84, 0.70 + 0.04 = 0.74, 0.86 + 0.04 = 0.90).
   - Epsilon boundaries (score == hurdle, score == hurdle - 1e-8, score == hurdle - 1e-7, score == hurdle - 2e-7).
   - Negative (short) hurdle symmetric precision.
3. Cross-group coentry decoupling:
   - Intra-group (same group) vs inter-group (triad vs queue_replenishment).
   - Order inversion (QR first then Triad, Triad first then QR).
   - Triad 3-strategy concurrent coentry dynamics (HC -> CC -> ME).
   - Re-entry role inversion after partial exit.
4. Robustness under abnormal market parameters:
   - Zero or negative mid_price (division by zero safety).
   - None or missing coentry_group parameters.
"""

import math
import unittest
from typing import Dict, Any

from config import BacktestConfig, MarketConfig
from engine.backtester import EdgeEvaluator


class TestAdversarialBoundaryStress(unittest.TestCase):
    """Deep empirical stress testing of backtester coentry, sizing, and precision logic."""

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

    # =========================================================================
    # 1. SIZING ORDER-OF-OPERATIONS: SIZES IN (1.0, 2.0] COINS
    # =========================================================================

    def test_sizing_in_one_to_two_coins_boundary_matrix(self):
        """Stress-test a dense sweep of sizes in (1.0, 2.0] coins under non-BTC coins.
        Assert:
        - When entering solo, sz is exactly equal to round(sz_base, 2).
        - When entering as co-entry, sz is halved to round(sz_base * 0.5, 2) in (0.5, 1.0].
        - Under NO circumstance does sz explode to thousands of coins (e.g. sz * 85000 / 25).
        """
        test_sizes = [
            1.0001, 1.01, 1.10, 1.25, 1.33, 1.50, 1.66, 1.75, 1.90, 1.99, 1.9999, 2.00
        ]
        mid_prices = [1.0, 5.0, 25.0, 100.0, 1500.0]

        for p_mid in mid_prices:
            for sz_base in test_sizes:
                with self.subTest(mid_price=p_mid, sz_base=sz_base):
                    strat_defs = {
                        "Strat_A": ("HedgedConvexity", "HEDGED_MAKER"),
                        "Strat_B": ("QueueReplenishment", "HEDGED_MAKER"),
                    }
                    strat_params = {
                        "Strat_A": {"entry_threshold": 0.80, "order_size_btc": sz_base, "coentry_group": "test_grp"},
                        "Strat_B": {"entry_threshold": 0.80, "order_size_btc": sz_base, "coentry_group": "test_grp"},
                    }
                    evaluator = EdgeEvaluator(
                        market_cfg=self.market_cfg_hype,
                        bt_cfg=self.bt_cfg,
                        strategy_defs=strat_defs,
                        strategy_params=strat_params,
                    )

                    spread_half = p_mid * 0.00005
                    best_bid = p_mid - spread_half
                    best_ask = p_mid + spread_half

                    # Tick 1: Strat_A enters solo
                    evaluator.record_step(
                        timestamp_ms=1000,
                        mid_price=p_mid,
                        best_bid=best_bid,
                        best_ask=best_ask,
                        signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.0},
                    )
                    pos_a = evaluator.strategies["Strat_A"].position_btc
                    expected_a = round(sz_base, 2)
                    self.assertEqual(
                        pos_a, expected_a,
                        f"Solo size failed for sz_base={sz_base}: got {pos_a}, expected {expected_a}"
                    )

                    # Tick 2: Strat_B enters as same-group co-entry (score 0.85 >= hurdle 0.84)
                    evaluator.record_step(
                        timestamp_ms=2000,
                        mid_price=p_mid,
                        best_bid=best_bid,
                        best_ask=best_ask,
                        signals={"HedgedConvexity": 0.0, "QueueReplenishment": 0.85},
                    )
                    pos_b = evaluator.strategies["Strat_B"].position_btc
                    expected_b = round(sz_base * 0.5, 2)
                    self.assertEqual(
                        pos_b, expected_b,
                        f"Coentry size exploded or miscalculated for sz_base={sz_base}, mid={p_mid}: got {pos_b}, expected {expected_b}"
                    )
                    # Absolute invariant check: pos_b must be strictly <= 1.0 and >= 0.5
                    self.assertTrue(
                        0.5 <= pos_b <= 1.0,
                        f"pos_b={pos_b} out of expected range [0.5, 1.0] for sz_base={sz_base}"
                    )
                    # Verify no explosion: if exploded, pos_b would be >= (0.5 * 85000 / 25) = 1700
                    self.assertLess(pos_b, 10.0, f"Dangerous size explosion detected: pos_b={pos_b}")

    def test_sizing_exact_one_boundary(self):
        """Test boundary condition sz == 1.0.
        Convention: sz > 1.0 is coin units, while sz <= 1.0 is fractional BTC.
        Therefore, at sz = 1.0 on HYPE ($25), 1.0 BTC should scale to 3,400 HYPE coins.
        Co-entry halving should scale 0.5 BTC to 1,700 HYPE coins.
        """
        strat_defs = {
            "Strat_A": ("HedgedConvexity", "HEDGED_MAKER"),
            "Strat_B": ("QueueReplenishment", "HEDGED_MAKER"),
        }
        strat_params = {
            "Strat_A": {"entry_threshold": 0.80, "order_size_btc": 1.0, "coentry_group": "test_grp"},
            "Strat_B": {"entry_threshold": 0.80, "order_size_btc": 1.0, "coentry_group": "test_grp"},
        }
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_hype,
            bt_cfg=self.bt_cfg,
            strategy_defs=strat_defs,
            strategy_params=strat_params,
        )

        # Tick 1: Strat A enters (1.0 BTC -> 3400 HYPE)
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=25.0,
            best_bid=24.998,
            best_ask=25.002,
            signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.0},
        )
        self.assertEqual(evaluator.strategies["Strat_A"].position_btc, 3400.0)

        # Tick 2: Strat B enters coentry (0.5 BTC -> 1700 HYPE)
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=25.0,
            best_bid=24.998,
            best_ask=25.002,
            signals={"HedgedConvexity": 0.0, "QueueReplenishment": 0.85},
        )
        self.assertEqual(evaluator.strategies["Strat_B"].position_btc, 1700.0)

    def test_fractional_btc_scaling_across_various_coins(self):
        """Verify fractional BTC scaling (0.01, 0.05, 0.1, 0.25) across diverse coin prices.
        Assert that co-entry discount always produces exactly 50% notional position.
        """
        btc_sizes = [0.01, 0.05, 0.10, 0.25]
        test_prices = [5.0, 25.0, 150.0, 2500.0]

        for p_mid in test_prices:
            spread_half = p_mid * 0.00005
            for btc_sz in btc_sizes:
                with self.subTest(mid_price=p_mid, btc_sz=btc_sz):
                    evaluator = EdgeEvaluator(
                        market_cfg=self.market_cfg_hype,
                        bt_cfg=self.bt_cfg,
                        strategy_defs={
                            "Strat_A": ("HedgedConvexity", "HEDGED_MAKER"),
                            "Strat_B": ("QueueReplenishment", "HEDGED_MAKER"),
                        },
                        strategy_params={
                            "Strat_A": {"entry_threshold": 0.80, "order_size_btc": btc_sz, "coentry_group": "g1"},
                            "Strat_B": {"entry_threshold": 0.80, "order_size_btc": btc_sz, "coentry_group": "g1"},
                        },
                    )
                    # Strat A enters
                    evaluator.record_step(
                        timestamp_ms=1000,
                        mid_price=p_mid,
                        best_bid=p_mid - spread_half,
                        best_ask=p_mid + spread_half,
                        signals={"HedgedConvexity": 0.85, "QueueReplenishment": 0.0},
                    )
                    pos_a = evaluator.strategies["Strat_A"].position_btc
                    expected_a = round(btc_sz * (85000.0 / p_mid), 2)
                    self.assertEqual(pos_a, expected_a)

                    # Strat B enters with 50% discount
                    evaluator.record_step(
                        timestamp_ms=2000,
                        mid_price=p_mid,
                        best_bid=p_mid - spread_half,
                        best_ask=p_mid + spread_half,
                        signals={"HedgedConvexity": 0.0, "QueueReplenishment": 0.85},
                    )
                    pos_b = evaluator.strategies["Strat_B"].position_btc
                    expected_b = round((btc_sz * 0.5) * (85000.0 / p_mid), 2)
                    self.assertEqual(pos_b, expected_b)

    # =========================================================================
    # 2. IEEE 754 PRECISION TOLERANCE AT HURDLE BOUNDARIES
    # =========================================================================

    def test_hurdle_epsilon_admittance_boundary(self):
        """Exhaustively test float precision at entry_thresh + 0.04.
        In Python float arithmetic:
        0.80 + 0.04 = 0.8400000000000001.
        Verify that exact float calculations and small epsilon neighborhoods:
        - 0.84 is admitted.
        - 0.80 + 0.04 is admitted.
        - 0.84 - 1e-8 is admitted.
        - 0.84 - 5e-8 is admitted.
        - 0.84 - 1e-7 is admitted (at the edge).
        - 0.84 - 2e-7 is REJECTED.
        - 0.8399 is REJECTED.
        """
        hurdle_tests = [
            (0.84, True, "exact literal 0.84"),
            (0.80 + 0.04, True, "float expression 0.80 + 0.04"),
            (0.84 - 1e-8, True, "1e-8 below hurdle (within 1e-7 tolerance)"),
            (0.84 - 5e-8, True, "5e-8 below hurdle (within 1e-7 tolerance)"),
            (0.84 - 1.000001e-7, False, "just beyond 1e-7 tolerance"),
            (0.84 - 2e-7, False, "2e-7 below hurdle"),
            (0.83999, False, "well below hurdle"),
            (0.84001, True, "above hurdle"),
        ]

        for score_val, expected_admitted, desc in hurdle_tests:
            with self.subTest(desc=desc, score=score_val):
                evaluator = EdgeEvaluator(
                    market_cfg=self.market_cfg_btc,
                    bt_cfg=self.bt_cfg,
                    strategy_defs={
                        "Strat_A": ("HedgedConvexity", "HEDGED_MAKER"),
                        "Strat_B": ("ConvexityCascade", "HEDGED_MAKER"),
                    },
                    strategy_params={
                        "Strat_A": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "triad"},
                        "Strat_B": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "triad"},
                    },
                )
                # Strat A enters
                evaluator.record_step(
                    timestamp_ms=1000,
                    mid_price=100.0,
                    best_bid=99.99,
                    best_ask=100.01,
                    signals={"HedgedConvexity": 0.85, "ConvexityCascade": 0.0},
                )
                self.assertTrue(evaluator.strategies["Strat_A"].is_in_position)

                # Strat B triggers with score_val
                evaluator.record_step(
                    timestamp_ms=2000,
                    mid_price=100.0,
                    best_bid=99.99,
                    best_ask=100.01,
                    signals={"HedgedConvexity": 0.0, "ConvexityCascade": score_val},
                )
                actual_admitted = evaluator.strategies["Strat_B"].is_in_position
                self.assertEqual(
                    actual_admitted, expected_admitted,
                    f"Hurdle check failed for score={score_val} ({desc}): expected {expected_admitted}, got {actual_admitted}"
                )

    def test_negative_hurdle_epsilon_admittance_boundary(self):
        """Exhaustively test negative (bearish/short) float precision at -hurdle.
        Verify:
        - -0.84 is admitted.
        - -(0.80 + 0.04) is admitted.
        - -0.84 + 1e-8 is admitted.
        - -0.84 + 5e-8 is admitted.
        - -0.84 + 2e-7 is REJECTED.
        - -0.8399 is REJECTED.
        """
        short_tests = [
            (-0.84, True, "exact literal -0.84"),
            (-(0.80 + 0.04), True, "float expression -(0.80 + 0.04)"),
            (-0.84 + 1e-8, True, "1e-8 above -0.84 (within 1e-7 tolerance)"),
            (-0.84 + 5e-8, True, "5e-8 above -0.84 (within 1e-7 tolerance)"),
            (-0.84 + 1.000001e-7, False, "just beyond 1e-7 tolerance"),
            (-0.84 + 2e-7, False, "2e-7 above -0.84"),
            (-0.83999, False, "well above -0.84 (weaker short conviction)"),
            (-0.84001, True, "stronger short conviction"),
        ]

        for score_val, expected_admitted, desc in short_tests:
            with self.subTest(desc=desc, score=score_val):
                evaluator = EdgeEvaluator(
                    market_cfg=self.market_cfg_btc,
                    bt_cfg=self.bt_cfg,
                    strategy_defs={
                        "Strat_A": ("HedgedConvexity", "HEDGED_MAKER"),
                        "Strat_B": ("ConvexityCascade", "HEDGED_MAKER"),
                    },
                    strategy_params={
                        "Strat_A": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "triad"},
                        "Strat_B": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "triad"},
                    },
                )
                # Strat A enters SHORT
                evaluator.record_step(
                    timestamp_ms=1000,
                    mid_price=100.0,
                    best_bid=99.99,
                    best_ask=100.01,
                    signals={"HedgedConvexity": -0.85, "ConvexityCascade": 0.0},
                )
                self.assertTrue(evaluator.strategies["Strat_A"].is_in_position)
                self.assertAlmostEqual(evaluator.strategies["Strat_A"].position_btc, -0.1)

                # Strat B triggers SHORT with score_val
                evaluator.record_step(
                    timestamp_ms=2000,
                    mid_price=100.0,
                    best_bid=99.99,
                    best_ask=100.01,
                    signals={"HedgedConvexity": 0.0, "ConvexityCascade": score_val},
                )
                actual_admitted = evaluator.strategies["Strat_B"].is_in_position
                self.assertEqual(
                    actual_admitted, expected_admitted,
                    f"Negative hurdle check failed for score={score_val} ({desc}): expected {expected_admitted}, got {actual_admitted}"
                )

    def test_hurdle_at_all_triad_thresholds(self):
        """Verify hurdle behavior across each Triad strategy's production entry threshold:
        - Momentum_Expansion: 0.70 -> hurdle 0.74
        - Convexity_Cascade: 0.80 -> hurdle 0.84
        - Hedged_Convexity: 0.86 -> hurdle 0.90
        """
        thresholds = [
            (0.70, 0.74),
            (0.80, 0.84),
            (0.86, 0.90),
        ]
        for thresh, expected_hurdle in thresholds:
            with self.subTest(thresh=thresh, expected_hurdle=expected_hurdle):
                evaluator = EdgeEvaluator(
                    market_cfg=self.market_cfg_btc,
                    bt_cfg=self.bt_cfg,
                    strategy_defs={
                        "Strat_A": ("HedgedConvexity", "HEDGED_MAKER"),
                        "Strat_B": ("ConvexityCascade", "HEDGED_MAKER"),
                    },
                    strategy_params={
                        "Strat_A": {"entry_threshold": thresh, "order_size_btc": 0.1, "coentry_group": "triad"},
                        "Strat_B": {"entry_threshold": thresh, "order_size_btc": 0.1, "coentry_group": "triad"},
                    },
                )
                # Strat A enters
                evaluator.record_step(
                    timestamp_ms=1000,
                    mid_price=100.0,
                    best_bid=99.99,
                    best_ask=100.01,
                    signals={"HedgedConvexity": thresh + 0.05, "ConvexityCascade": 0.0},
                )
                # Sub-hurdle score -> blocked
                evaluator.record_step(
                    timestamp_ms=2000,
                    mid_price=100.0,
                    best_bid=99.99,
                    best_ask=100.01,
                    signals={"HedgedConvexity": 0.0, "ConvexityCascade": expected_hurdle - 0.005},
                )
                self.assertFalse(evaluator.strategies["Strat_B"].is_in_position)

                # Exact hurdle score -> admitted
                evaluator.record_step(
                    timestamp_ms=3000,
                    mid_price=100.0,
                    best_bid=99.99,
                    best_ask=100.01,
                    signals={"HedgedConvexity": 0.0, "ConvexityCascade": expected_hurdle},
                )
                self.assertTrue(evaluator.strategies["Strat_B"].is_in_position)

    # =========================================================================
    # 3. CROSS-GROUP COENTRY DECOUPLING & ISOLATION
    # =========================================================================

    def test_order_inversion_qr_first_then_triad(self):
        """Test reverse sequence: Queue_Replenishment enters first, then Triad strategy triggers.
        Triad MUST enter with FULL size and WITHOUT hurdle restriction.
        """
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs={
                "Queue_Replenishment": ("QueueReplenishment", "HEDGED_MAKER"),
                "Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER"),
            },
            strategy_params={
                "Queue_Replenishment": {"entry_threshold": 0.985, "order_size_btc": 0.1, "coentry_group": "queue_replenishment"},
                "Hedged_Convexity": {"entry_threshold": 0.86, "order_size_btc": 0.1, "coentry_group": "triad"},
            },
        )

        # Step 1: Queue_Replenishment enters LONG with score = 0.99
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.99,
            best_ask=100.01,
            signals={"QueueReplenishment": 0.99, "HedgedConvexity": 0.0},
        )
        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position)
        self.assertEqual(evaluator.strategies["Queue_Replenishment"].position_btc, 0.1)

        # Step 2: Hedged_Convexity triggers with score = 0.87 (above 0.86, but below 0.90 hurdle)
        # Because Hedged_Convexity is in "triad" and QR is in "queue_replenishment",
        # Hedged_Convexity MUST NOT be blocked and MUST NOT be discounted!
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.0,
            best_bid=99.99,
            best_ask=100.01,
            signals={"QueueReplenishment": 0.0, "HedgedConvexity": 0.87},
        )
        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position, "Hedged_Convexity was wrongly blocked by QR!")
        self.assertEqual(
            evaluator.strategies["Hedged_Convexity"].position_btc, 0.1,
            "Hedged_Convexity wrongly suffered a 50% discount from cross-group QR!"
        )

    def test_default_group_assignments_when_unspecified(self):
        """Verify backtester fallback logic when coentry_group is NOT specified in params.
        Line 599:
        my_group = params.get("coentry_group", "triad" if s_name in ("Hedged_Convexity", "Convexity_Cascade", "Momentum_Expansion") else s_name)
        """
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs={
                "Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER"),
                "Convexity_Cascade": ("ConvexityCascade", "HEDGED_MAKER"),
                "Queue_Replenishment": ("QueueReplenishment", "HEDGED_MAKER"),
            },
            strategy_params={
                # coentry_group deliberately omitted!
                "Hedged_Convexity": {"entry_threshold": 0.80, "order_size_btc": 0.1},
                "Convexity_Cascade": {"entry_threshold": 0.80, "order_size_btc": 0.1},
                "Queue_Replenishment": {"entry_threshold": 0.80, "order_size_btc": 0.1},
            },
        )

        # 1. Hedged_Convexity enters
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.99,
            best_ask=100.01,
            signals={"HedgedConvexity": 0.85, "ConvexityCascade": 0.0, "QueueReplenishment": 0.0},
        )
        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position)

        # 2. Convexity_Cascade triggers with 0.82 (sub-hurdle 0.84) -> MUST BE BLOCKED (default triad group)
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.0,
            best_bid=99.99,
            best_ask=100.01,
            signals={"HedgedConvexity": 0.0, "ConvexityCascade": 0.82, "QueueReplenishment": 0.0},
        )
        self.assertFalse(evaluator.strategies["Convexity_Cascade"].is_in_position, "Default fallback should group CC into triad!")

        # 3. Queue_Replenishment triggers with 0.82 (sub-hurdle 0.84) -> MUST ENTER FULL SIZE (default QR group != triad)
        evaluator.record_step(
            timestamp_ms=3000,
            mid_price=100.0,
            best_bid=99.99,
            best_ask=100.01,
            signals={"HedgedConvexity": 0.0, "ConvexityCascade": 0.0, "QueueReplenishment": 0.82},
        )
        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position, "Default fallback should decouple QR from triad!")
        self.assertEqual(evaluator.strategies["Queue_Replenishment"].position_btc, 0.1)

    def test_dynamic_role_inversion_and_reentry(self):
        """Verify dynamic role inversion:
        - Strat A enters first (full size 0.1)
        - Strat B enters second (discounted 0.05)
        - Strat A exits
        - Strat A re-enters while Strat B is still open:
          Now Strat A is the SECOND strategy, so Strat A must receive the 50% discount!
        """
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs={
                "Strat_A": ("HedgedConvexity", "HEDGED_MAKER"),
                "Strat_B": ("ConvexityCascade", "HEDGED_MAKER"),
            },
            strategy_params={
                "Strat_A": {"entry_threshold": 0.80, "order_size_btc": 0.1, "take_profit_bps": 10.0, "coentry_group": "triad"},
                "Strat_B": {"entry_threshold": 0.80, "order_size_btc": 0.1, "take_profit_bps": 50.0, "coentry_group": "triad"},
            },
        )

        # 1. Strat A enters first -> 0.1
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.99,
            best_ask=100.01,
            signals={"HedgedConvexity": 0.85, "ConvexityCascade": 0.0},
        )
        self.assertEqual(evaluator.strategies["Strat_A"].position_btc, 0.1)

        # 2. Strat B enters second -> 0.05
        evaluator.record_step(
            timestamp_ms=2000,
            mid_price=100.0,
            best_bid=99.99,
            best_ask=100.01,
            signals={"HedgedConvexity": 0.0, "ConvexityCascade": 0.85},
        )
        self.assertEqual(evaluator.strategies["Strat_B"].position_btc, 0.05)

        # 3. Mid price rises to 100.15 (+15 bps) -> Strat A hits TP (+10 bps) and exits
        evaluator.record_step(
            timestamp_ms=3000,
            mid_price=100.15,
            best_bid=100.14,
            best_ask=100.16,
            signals={"HedgedConvexity": 0.0, "ConvexityCascade": 0.0},
        )
        self.assertFalse(evaluator.strategies["Strat_A"].is_in_position)
        self.assertTrue(evaluator.strategies["Strat_B"].is_in_position)

        # 4. Strat A triggers re-entry with score = 0.85
        evaluator.strategies["Strat_A"].last_exit_was_loss = False
        evaluator.record_step(
            timestamp_ms=4000,
            mid_price=100.15,
            best_bid=100.14,
            best_ask=100.16,
            signals={"HedgedConvexity": 0.85, "ConvexityCascade": 0.0},
        )
        self.assertTrue(evaluator.strategies["Strat_A"].is_in_position)
        # Strat A must now receive the 50% discount because Strat B is in position!
        self.assertEqual(
            evaluator.strategies["Strat_A"].position_btc, 0.05,
            "Role inversion failed: re-entering strategy was not discounted when peer was in position!"
        )

    # =========================================================================
    # 4. ROBUSTNESS UNDER ABNORMAL MARKET PARAMETERS
    # =========================================================================

    def test_zero_and_negative_mid_price_safety(self):
        """Test engine safety when mid_price <= 0 (e.g. data corruption or empty book).
        Engine must not throw ZeroDivisionError and must gracefully handle sizing.
        """
        for bad_price in [0.0, -1.0, -100.0]:
            with self.subTest(bad_price=bad_price):
                evaluator = EdgeEvaluator(
                    market_cfg=self.market_cfg_hype,
                    bt_cfg=self.bt_cfg,
                    strategy_defs={
                        "Strat_A": ("HedgedConvexity", "HEDGED_MAKER"),
                    },
                    strategy_params={
                        "Strat_A": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "triad"},
                    },
                )
                try:
                    evaluator.record_step(
                        timestamp_ms=1000,
                        mid_price=bad_price,
                        best_bid=bad_price - 0.01,
                        best_ask=bad_price + 0.01,
                        signals={"HedgedConvexity": 0.85},
                    )
                except ZeroDivisionError:
                    self.fail(f"ZeroDivisionError raised on mid_price={bad_price}!")


    def test_multi_strategy_same_tick_cross_group_collision(self):
        """CRITICAL CHALLENGE: 4 strategies fire SIMULTANEOUSLY on tick t=1000 with score=0.82.
        - Triad strategies: Hedged_Convexity, Convexity_Cascade, Momentum_Expansion (coentry_group: 'triad').
        - Orthogonal strategy: Queue_Replenishment (coentry_group: 'queue_replenishment').
        
        Expected Behavior:
        - Hedged_Convexity (evaluated 1st) enters LONG with full size 0.1.
        - Convexity_Cascade (evaluated 2nd) sees HC in position in same group 'triad' -> requires 0.84 hurdle -> BLOCKED!
        - Momentum_Expansion (evaluated 3rd) sees HC in position in same group 'triad' -> requires 0.84 hurdle -> BLOCKED!
        - Queue_Replenishment (evaluated 4th) sees HC in position in DIFFERENT group 'queue_replenishment'
          -> same_dir_active is FALSE -> requires base 0.80 -> ENTERS with FULL size 0.1!
        """
        evaluator = EdgeEvaluator(
            market_cfg=self.market_cfg_btc,
            bt_cfg=self.bt_cfg,
            strategy_defs={
                "Hedged_Convexity": ("HedgedConvexity", "HEDGED_MAKER"),
                "Convexity_Cascade": ("ConvexityCascade", "HEDGED_MAKER"),
                "Momentum_Expansion": ("MomentumExpansion", "HEDGED_MAKER"),
                "Queue_Replenishment": ("QueueReplenishment", "HEDGED_MAKER"),
            },
            strategy_params={
                "Hedged_Convexity": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "triad"},
                "Convexity_Cascade": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "triad"},
                "Momentum_Expansion": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "triad"},
                "Queue_Replenishment": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "queue_replenishment"},
            },
        )

        # All 4 trigger with score = 0.82
        evaluator.record_step(
            timestamp_ms=1000,
            mid_price=100.0,
            best_bid=99.995,
            best_ask=100.005,
            signals={
                "HedgedConvexity": 0.82,
                "ConvexityCascade": 0.82,
                "MomentumExpansion": 0.82,
                "QueueReplenishment": 0.82,
            },
        )

        # Assert Hedged_Convexity entered with full size
        self.assertTrue(evaluator.strategies["Hedged_Convexity"].is_in_position)
        self.assertAlmostEqual(evaluator.strategies["Hedged_Convexity"].position_btc, 0.1)

        # Assert Convexity_Cascade and Momentum_Expansion were BLOCKED by intra-group hurdle
        self.assertFalse(evaluator.strategies["Convexity_Cascade"].is_in_position, "CC should be blocked by HC intra-group hurdle!")
        self.assertFalse(evaluator.strategies["Momentum_Expansion"].is_in_position, "ME should be blocked by HC intra-group hurdle!")

        # Assert Queue_Replenishment ENTERED with FULL size 0.1 because it is decoupled!
        self.assertTrue(evaluator.strategies["Queue_Replenishment"].is_in_position, "QR should NOT be blocked across decoupled groups!")
        self.assertAlmostEqual(evaluator.strategies["Queue_Replenishment"].position_btc, 0.1, places=4, msg="QR should have FULL size (0.1)!")

    def test_sub_tick_float_noise_tolerance(self):
        """Stress-test sub-micro epsilon noise around the 0.84 boundary."""
        noise_cases = [
            (0.84 - 1e-9, True, "1 nanounit below hurdle (well within 1e-7 tolerance)"),
            (0.84 - 9e-8, True, "90 nanounits below hurdle (within 1e-7 tolerance)"),
            (0.84 - 1e-7 + 1e-12, True, "at the knife-edge of 1e-7 tolerance"),
            (0.84 - 1.1e-7, False, "10 nanounits beyond 1e-7 tolerance -> must reject"),
            (0.84 - 1e-6, False, "1 microunit below hurdle -> must reject"),
        ]
        for score_val, expected, desc in noise_cases:
            with self.subTest(score=score_val, desc=desc):
                evaluator = EdgeEvaluator(
                    market_cfg=self.market_cfg_btc,
                    bt_cfg=self.bt_cfg,
                    strategy_defs={
                        "Strat_A": ("HedgedConvexity", "HEDGED_MAKER"),
                        "Strat_B": ("ConvexityCascade", "HEDGED_MAKER"),
                    },
                    strategy_params={
                        "Strat_A": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "triad"},
                        "Strat_B": {"entry_threshold": 0.80, "order_size_btc": 0.1, "coentry_group": "triad"},
                    },
                )
                evaluator.record_step(
                    timestamp_ms=1000,
                    mid_price=100.0,
                    best_bid=99.995,
                    best_ask=100.005,
                    signals={"HedgedConvexity": 0.85, "ConvexityCascade": 0.0},
                )
                evaluator.record_step(
                    timestamp_ms=2000,
                    mid_price=100.0,
                    best_bid=99.995,
                    best_ask=100.005,
                    signals={"HedgedConvexity": 0.0, "ConvexityCascade": score_val},
                )
                self.assertEqual(evaluator.strategies["Strat_B"].is_in_position, expected, f"Failed for {desc} (score={score_val})")

    def test_knife_edge_one_point_zero_sizing_boundary(self):
        """Test knife edge around 1.0 on HYPE ($25):
        - 1.000001 coins (> 1.0) -> is_coin_units=True:
          Normal = 1.0 coins ($25 notional)
          Coentry = 0.50 coins ($12.50 notional)
        - 0.999999 btc (<= 1.0) -> is_coin_units=False:
          Normal = round(0.999999 * 3400, 2) = 3400.0 coins ($85,000 notional)
          Coentry = round(0.4999995 * 3400, 2) = 1700.0 coins ($42,500 notional)
        """
        eval_above = EdgeEvaluator(
            market_cfg=self.market_cfg_hype,
            bt_cfg=self.bt_cfg,
            strategy_defs={"S_A": ("HedgedConvexity", "HEDGED_MAKER"), "S_B": ("QueueReplenishment", "HEDGED_MAKER")},
            strategy_params={
                "S_A": {"entry_threshold": 0.80, "order_size_btc": 1.000001, "coentry_group": "g1"},
                "S_B": {"entry_threshold": 0.80, "order_size_btc": 1.000001, "coentry_group": "g1"},
            },
        )
        eval_above.record_step(1000, 25.0, 24.998, 25.002, {"HedgedConvexity": 0.85, "QueueReplenishment": 0.0})
        self.assertEqual(eval_above.strategies["S_A"].position_btc, 1.0)
        eval_above.record_step(2000, 25.0, 24.998, 25.002, {"HedgedConvexity": 0.0, "QueueReplenishment": 0.85})
        self.assertEqual(eval_above.strategies["S_B"].position_btc, 0.50)

        eval_below = EdgeEvaluator(
            market_cfg=self.market_cfg_hype,
            bt_cfg=self.bt_cfg,
            strategy_defs={"S_A": ("HedgedConvexity", "HEDGED_MAKER"), "S_B": ("QueueReplenishment", "HEDGED_MAKER")},
            strategy_params={
                "S_A": {"entry_threshold": 0.80, "order_size_btc": 0.999999, "coentry_group": "g1"},
                "S_B": {"entry_threshold": 0.80, "order_size_btc": 0.999999, "coentry_group": "g1"},
            },
        )
        eval_below.record_step(1000, 25.0, 24.998, 25.002, {"HedgedConvexity": 0.85, "QueueReplenishment": 0.0})
        self.assertEqual(eval_below.strategies["S_A"].position_btc, 3400.0)
        eval_below.record_step(2000, 25.0, 24.998, 25.002, {"HedgedConvexity": 0.0, "QueueReplenishment": 0.85})
        self.assertEqual(eval_below.strategies["S_B"].position_btc, 1700.0)


if __name__ == "__main__":
    unittest.main()
