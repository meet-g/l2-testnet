"""Unit tests for DynamicSpread alpha signal and Dynamic_Spread_Scalper scalping strategy."""

import time
import unittest

from core.orderbook import L2Level, OrderBook
from core.trade_stream import Trade, TradeManager
from engine.backtester import EdgeEvaluator
from config import BacktestConfig, MarketConfig, StrategiesConfig
from signals.dynamic_spread import DynamicSpreadSignal


class TestDynamicSpreadScalper(unittest.TestCase):
    def setUp(self):
        self.signal = DynamicSpreadSignal()
        self.book = OrderBook(coin="xyz:SKHX", enable_history=False)
        self.trades = TradeManager(coin="xyz:SKHX")

    def test_initialization(self):
        """Verifies default hyperparameters and dynamic TP settings."""
        self.assertEqual(self.signal.name, "DynamicSpread")
        self.assertEqual(self.signal.w_flow, 0.30)
        self.assertEqual(self.signal.w_thin, 0.25)
        self.assertEqual(self.signal.w_micro, 0.20)
        self.assertEqual(self.signal.w_wobi, 0.15)
        self.assertEqual(self.signal.w_count, 0.10)
        self.assertEqual(self.signal.dynamic_tp_min_bps, 4.0)
        self.assertEqual(self.signal.dynamic_tp_max_bps, 12.0)
        self.assertEqual(self.signal.dynamic_tp_spread_mult, 2.0)
        self.assertEqual(self.signal.dynamic_tp_vol_mult, 0.8)

    def test_bullish_depletion_and_flow(self):
        """Verifies strong bullish signal and dynamic TP metadata when ask queue is depleted."""
        now_ms = int(time.time() * 1000)

        # Bids: thick resting queue at touch (5.0 units, 10 orders)
        # Asks: thin fragile queue at touch (0.1 units, 1 order)
        # Spread: 1.5 bps ($0.15 on $1,000)
        self.book.bids = [
            L2Level(px=1000.0, sz=5.0, n=10),
            L2Level(px=999.85, sz=5.0, n=8),
            L2Level(px=999.70, sz=5.0, n=6),
            L2Level(px=999.55, sz=5.0, n=4),
            L2Level(px=999.40, sz=5.0, n=2),
        ]
        self.book.asks = [
            L2Level(px=1000.15, sz=0.1, n=1),
            L2Level(px=1000.30, sz=4.0, n=6),
            L2Level(px=1000.45, sz=5.0, n=7),
            L2Level(px=1000.60, sz=5.0, n=8),
            L2Level(px=1000.75, sz=5.0, n=10),
        ]
        self.book.last_update_time_ms = now_ms

        # Aggressive buy flow burst
        self.trades.trades.append(Trade(timestamp_ms=now_ms - 200, price=1000.15, size=2.0, side="B"))
        self.trades.trades.append(Trade(timestamp_ms=now_ms - 100, price=1000.15, size=3.0, side="B"))
        self.trades.last_trade_time_ms = now_ms

        res = self.signal.compute(self.book, self.trades, timestamp_ms=now_ms)
        self.assertGreater(res.score, 0.65, f"Expected strong bullish conviction, got {res.score}")
        self.assertGreater(res.confidence, 0.60, f"Expected high confidence, got {res.confidence}")
        self.assertIn("target_tp_bps", res.metadata)
        self.assertGreaterEqual(res.metadata["target_tp_bps"], 4.0)
        self.assertLessEqual(res.metadata["target_tp_bps"], 12.0)
        self.assertIn("trail_act_bps", res.metadata)
        self.assertIn("trail_dist_bps", res.metadata)

    def test_bearish_depletion_and_flow(self):
        """Verifies strong bearish signal when bid queue is depleted and sell flow surges."""
        now_ms = int(time.time() * 1000)

        # Bids: thin fragile queue at touch (0.1 units, 1 order)
        # Asks: thick resting queue at touch (5.0 units, 10 orders)
        self.book.bids = [
            L2Level(px=1000.0, sz=0.1, n=1),
            L2Level(px=999.85, sz=4.0, n=6),
            L2Level(px=999.70, sz=5.0, n=6),
            L2Level(px=999.55, sz=5.0, n=4),
            L2Level(px=999.40, sz=5.0, n=2),
        ]
        self.book.asks = [
            L2Level(px=1000.15, sz=5.0, n=10),
            L2Level(px=1000.30, sz=5.0, n=8),
            L2Level(px=1000.45, sz=5.0, n=6),
            L2Level(px=1000.60, sz=5.0, n=4),
            L2Level(px=1000.75, sz=5.0, n=2),
        ]
        self.book.last_update_time_ms = now_ms

        # Aggressive sell flow burst
        self.trades.trades.append(Trade(timestamp_ms=now_ms - 200, price=1000.0, size=2.0, side="A"))
        self.trades.trades.append(Trade(timestamp_ms=now_ms - 100, price=1000.0, size=3.0, side="A"))
        self.trades.last_trade_time_ms = now_ms

        res = self.signal.compute(self.book, self.trades, timestamp_ms=now_ms)
        self.assertLess(res.score, -0.65, f"Expected strong bearish conviction, got {res.score}")
        self.assertGreater(res.confidence, 0.60, f"Expected high confidence, got {res.confidence}")
        self.assertLess(res.metadata["s_flow"], 0.0)
        self.assertLess(res.metadata["s_thin"], 0.0)

    def test_spread_elasticity_damping(self):
        """Verifies wide spreads damp score to avoid crossing illiquid gaps."""
        now_ms = int(time.time() * 1000)
        # 15.0 bps spread (1.50 on 1000.0) >> 5.0 bps max favorable spread
        self.book.bids = [L2Level(px=1000.0, sz=5.0, n=10)]
        self.book.asks = [L2Level(px=1001.50, sz=0.1, n=1)]
        self.book.last_update_time_ms = now_ms

        res = self.signal.compute(self.book, self.trades, timestamp_ms=now_ms)
        self.assertLess(res.metadata["spread_factor"], 1.0)
        self.assertGreater(res.metadata["target_tp_bps"], 5.0)

    def test_configuration_loading(self):
        """Verifies Dynamic_Spread_Scalper is properly registered in strategies.json."""
        cfg = StrategiesConfig.load("strategies.json")
        self.assertIn("Dynamic_Spread_Scalper", cfg.scalping_strategies)
        strat = cfg.scalping_strategies["Dynamic_Spread_Scalper"]
        self.assertEqual(strat.signal_key, "DynamicSpread")
        self.assertEqual(strat.execution_type, "MAKER")
        self.assertTrue(strat.dynamic_tp_enabled)
        self.assertEqual(strat.dynamic_tp_min_bps, 4.0)
        self.assertEqual(strat.dynamic_tp_max_bps, 12.0)
        self.assertTrue(strat.tiered_trailing_ratchet)
        self.assertTrue(strat.exhaustion_exit_enabled)

    def test_variable_take_profit_execution_in_evaluator(self):
        """Verifies that Dynamic_Spread_Scalper hits dynamic TP at +6 bps instead of waiting for 20 bps."""
        m_cfg = MarketConfig(coin="xyz:SKHX", maker_fee_bps=0.30, taker_fee_bps=0.90)
        bt_cfg = BacktestConfig(max_spread_bps=3.0)
        evaluator = EdgeEvaluator(
            market_cfg=m_cfg,
            bt_cfg=bt_cfg,
            strategy_defs={"Dynamic_Spread_Scalper": ("DynamicSpread", "MAKER")},
            strategy_params={"Dynamic_Spread_Scalper": {
                "entry_threshold": 0.70,
                "take_profit_bps": 6.5,
                "stop_loss_bps": 10.0,
                "order_size_btc": 1.0,
                "dynamic_tp_enabled": True,
                "dynamic_tp_min_bps": 4.0,
                "dynamic_tp_max_bps": 10.0,
                "dynamic_tp_spread_mult": 2.0,
                "dynamic_tp_vol_mult": 0.5,
            }},
        )

        now_ms = 10_000
        # Step 1: Bullish entry trigger (MAKER Buy posted at best_bid)
        evaluator.record_step(
            timestamp_ms=now_ms,
            mid_price=1000.0,
            best_bid=999.90,
            best_ask=1000.10,  # Spread = 2.0 bps
            signals={"DynamicSpread": 0.85},
            confidences={"DynamicSpread": 0.80},
        )

        st = evaluator.strategies["Dynamic_Spread_Scalper"]
        self.assertTrue(st.is_in_position)
        self.assertEqual(st.position_btc, 85.0)
        self.assertEqual(st.entry_price, 999.90)
        self.assertEqual(evaluator.position_events[0]["exec"], "MAKER")

        # Step 2: Price advances by +6.0 bps (Mid = 1000.50, Ask = 1000.60)
        # A static 20 bps strategy would NOT exit here. But Dynamic_Spread_Scalper exits cleanly!
        evaluator.record_step(
            timestamp_ms=now_ms + 1000,
            mid_price=1000.50,
            best_bid=1000.40,
            best_ask=1000.60,
            signals={"DynamicSpread": 0.50},
            confidences={"DynamicSpread": 0.50},
        )

        self.assertFalse(st.is_in_position, "Position should have exited on dynamic variable take profit")
        self.assertEqual(len(st.trades), 1)
        tr = st.trades[0]
        self.assertEqual(tr.exit_reason, "TAKE_PROFIT")
        self.assertIn("MAKER", tr.execution_type)
        self.assertGreater(tr.net_pnl_usd, 0.0)
        self.assertGreater(tr.return_bps, 4.0)

    def test_order_flow_exhaustion_exit(self):
        """Verifies that an open position with positive excursion exits early when flow exhausts."""
        m_cfg = MarketConfig(coin="xyz:SKHX", maker_fee_bps=0.30, taker_fee_bps=0.90)
        bt_cfg = BacktestConfig(max_spread_bps=3.0)
        evaluator = EdgeEvaluator(
            market_cfg=m_cfg,
            bt_cfg=bt_cfg,
            strategy_defs={"Dynamic_Spread_Scalper": ("DynamicSpread", "MAKER")},
            strategy_params={"Dynamic_Spread_Scalper": {
                "entry_threshold": 0.70,
                "take_profit_bps": 12.0,  # Higher hurdle
                "stop_loss_bps": 10.0,
                "order_size_btc": 1.0,
                "dynamic_tp_enabled": True,
                "exhaustion_exit_enabled": True,
                "exhaustion_min_gain_bps": 3.0,
                "exhaustion_score_threshold": 0.15,
            }},
        )

        now_ms = 10_000
        # Step 1: Bullish Entry
        evaluator.record_step(
            timestamp_ms=now_ms,
            mid_price=1000.0,
            best_bid=999.90,
            best_ask=1000.10,
            signals={"DynamicSpread": 0.80},
        )

        st = evaluator.strategies["Dynamic_Spread_Scalper"]
        self.assertTrue(st.is_in_position)

        # Step 2: Modest gain (+4.0 bps, not enough for 12 bps TP), but signal score drops to 0.05 (momentum exhausted)
        evaluator.record_step(
            timestamp_ms=now_ms + 2000,
            mid_price=1000.30,
            best_bid=1000.20,
            best_ask=1000.40,
            signals={"DynamicSpread": 0.05},  # Conviction drops below 0.15 threshold
        )

        self.assertFalse(st.is_in_position, "Position should have exited via flow exhaustion before decaying")
        self.assertEqual(len(st.trades), 1)
        tr = st.trades[0]
        self.assertEqual(tr.exit_reason, "EXHAUSTION_EXIT")
        self.assertEqual(tr.exit_price, 1000.40)
        self.assertGreater(tr.net_pnl_usd, 0.0)
        self.assertGreater(tr.return_bps, 3.0)

    def test_short_order_flow_exhaustion_exit(self):
        """Verifies that an open short position exits cleanly at best bid when bearish flow exhausts."""
        m_cfg = MarketConfig(coin="xyz:SKHX", maker_fee_bps=0.30, taker_fee_bps=0.90)
        bt_cfg = BacktestConfig(max_spread_bps=3.0)
        evaluator = EdgeEvaluator(
            market_cfg=m_cfg,
            bt_cfg=bt_cfg,
            strategy_defs={"Dynamic_Spread_Scalper": ("DynamicSpread", "MAKER")},
            strategy_params={"Dynamic_Spread_Scalper": {
                "entry_threshold": 0.70,
                "take_profit_bps": 12.0,
                "stop_loss_bps": 10.0,
                "order_size_btc": 1.0,
                "dynamic_tp_enabled": True,
                "exhaustion_exit_enabled": True,
                "exhaustion_min_gain_bps": 3.0,
                "exhaustion_score_threshold": 0.15,
            }},
        )

        now_ms = 10_000
        # Step 1: Bearish Entry (Short)
        evaluator.record_step(
            timestamp_ms=now_ms,
            mid_price=1000.0,
            best_bid=999.90,
            best_ask=1000.10,
            signals={"DynamicSpread": -0.80},
        )

        st = evaluator.strategies["Dynamic_Spread_Scalper"]
        self.assertTrue(st.is_in_position)
        self.assertLess(st.position_btc, 0.0)

        # Step 2: Price drops to 999.70 (best_bid 999.60, best_ask 999.80), gain is +3 bps, conviction decays to -0.05
        evaluator.record_step(
            timestamp_ms=now_ms + 2000,
            mid_price=999.70,
            best_bid=999.60,
            best_ask=999.80,
            signals={"DynamicSpread": -0.05},
        )

        self.assertFalse(st.is_in_position, "Short position should have exited via flow exhaustion")
        self.assertEqual(len(st.trades), 1)
        tr = st.trades[0]
        self.assertEqual(tr.exit_reason, "EXHAUSTION_EXIT")
        self.assertEqual(tr.exit_price, 999.60)
        self.assertGreater(tr.net_pnl_usd, 0.0)
        self.assertGreater(tr.return_bps, 3.0)


if __name__ == "__main__":
    unittest.main()
