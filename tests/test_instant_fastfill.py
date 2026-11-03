"""Unit tests for InstantFill alpha signal and Instant_FastFill scalping strategy."""

import time
import unittest

from core.orderbook import L2Level, OrderBook
from core.trade_stream import Trade, TradeManager
from engine.backtester import EdgeEvaluator
from config import BacktestConfig, StrategiesConfig
from signals.instant_fill import InstantFillSignal


class TestInstantFill(unittest.TestCase):
    def setUp(self):
        self.signal = InstantFillSignal()
        self.book = OrderBook(coin="BTC", enable_history=False)
        self.trades = TradeManager(coin="BTC")

    def test_initialization(self):
        """Verifies default weights and hyperparameters."""
        self.assertEqual(self.signal.name, "InstantFill")
        self.assertEqual(self.signal.w_flow, 0.40)
        self.assertEqual(self.signal.w_thin, 0.30)
        self.assertEqual(self.signal.w_micro, 0.20)
        self.assertEqual(self.signal.w_count, 0.10)
        self.assertEqual(self.signal.flow_window_secs, 2.0)

    def test_bullish_depletion_and_sweep(self):
        """Verifies strong positive signal when ask queue is depleted and buy flow surges."""
        now_ms = int(time.time() * 1000)

        # Order book: Best ask has tiny quantity (0.1 BTC, 1 order), but deeper asks are thicker
        # Best bid has thick quantity (5.0 BTC, 10 orders)
        # Price is $1,000 with a $0.10 spread (1.0 bps, well within 3.5 bps favorable spread)
        self.book.bids = [
            L2Level(px=1000.0, sz=5.0, n=10),
            L2Level(px=999.9, sz=5.0, n=8),
            L2Level(px=999.8, sz=5.0, n=6),
            L2Level(px=999.7, sz=5.0, n=4),
            L2Level(px=999.6, sz=5.0, n=2),
        ]
        self.book.asks = [
            L2Level(px=1000.1, sz=0.1, n=1),  # Fragile / depleted queue at touch
            L2Level(px=1000.2, sz=4.0, n=6),
            L2Level(px=1000.3, sz=5.0, n=7),
            L2Level(px=1000.4, sz=5.0, n=8),
            L2Level(px=1000.5, sz=5.0, n=10),
        ]
        self.book.last_update_time_ms = now_ms

        # Recent trades: Aggressive buy burst
        self.trades.trades.append(Trade(timestamp_ms=now_ms - 200, price=1000.1, size=2.0, side="B"))
        self.trades.trades.append(Trade(timestamp_ms=now_ms - 100, price=1000.1, size=3.0, side="B"))
        self.trades.last_trade_time_ms = now_ms

        res = self.signal.compute(self.book, self.trades, timestamp_ms=now_ms)
        self.assertGreater(res.score, 0.65, f"Expected strong bullish score, got {res.score}")
        self.assertGreater(res.confidence, 0.60, f"Expected high confidence, got {res.confidence}")
        self.assertIn("s_thin", res.metadata)
        self.assertGreater(res.metadata["s_thin"], 0.0)
        self.assertGreater(res.metadata["s_flow"], 0.0)

    def test_bearish_depletion_and_sweep(self):
        """Verifies strong negative signal when bid queue is depleted and sell flow surges."""
        now_ms = int(time.time() * 1000)

        # Order book: Best bid has tiny quantity (0.1 BTC, 1 order)
        # Best ask has thick quantity (5.0 BTC, 10 orders)
        self.book.bids = [
            L2Level(px=1000.0, sz=0.1, n=1),  # Depleted bid queue
            L2Level(px=999.9, sz=4.0, n=6),
            L2Level(px=999.8, sz=5.0, n=6),
            L2Level(px=999.7, sz=5.0, n=4),
            L2Level(px=999.6, sz=5.0, n=2),
        ]
        self.book.asks = [
            L2Level(px=1000.1, sz=5.0, n=10),
            L2Level(px=1000.2, sz=5.0, n=8),
            L2Level(px=1000.3, sz=5.0, n=6),
            L2Level(px=1000.4, sz=5.0, n=4),
            L2Level(px=1000.5, sz=5.0, n=2),
        ]
        self.book.last_update_time_ms = now_ms

        # Recent trades: Aggressive sell burst
        self.trades.trades.append(Trade(timestamp_ms=now_ms - 200, price=1000.0, size=2.0, side="A"))
        self.trades.trades.append(Trade(timestamp_ms=now_ms - 100, price=1000.0, size=3.0, side="A"))
        self.trades.last_trade_time_ms = now_ms

        res = self.signal.compute(self.book, self.trades, timestamp_ms=now_ms)
        self.assertLess(res.score, -0.65, f"Expected strong bearish score, got {res.score}")
        self.assertGreater(res.confidence, 0.60, f"Expected high confidence, got {res.confidence}")
        self.assertLess(res.metadata["s_thin"], 0.0)
        self.assertLess(res.metadata["s_flow"], 0.0)

    def test_wide_spread_damping(self):
        """Verifies that an abnormally wide spread dampens score to avoid crossing wide spreads."""
        now_ms = int(time.time() * 1000)
        # Spread is 10.0 on a 1000.0 price = 100 bps (much wider than 3.5 bps)
        self.book.bids = [L2Level(px=1000.0, sz=5.0, n=10)]
        self.book.asks = [L2Level(px=1010.0, sz=0.1, n=1)]
        self.book.last_update_time_ms = now_ms

        res = self.signal.compute(self.book, self.trades, timestamp_ms=now_ms)
        self.assertLess(res.metadata["spread_factor"], 0.30)

    def test_strategy_configuration_loading(self):
        """Verifies Instant_FastFill is registered and loaded properly from strategies.json."""
        cfg = StrategiesConfig.load("strategies.json")
        self.assertIn("Instant_FastFill", cfg.scalping_strategies)
        strat = cfg.scalping_strategies["Instant_FastFill"]
        self.assertEqual(strat.signal_key, "InstantFill")
        self.assertIn(strat.execution_type, ("SMART_TAKER", "MAKER"))
        self.assertIn(strat.entry_threshold, (0.70, 0.75))
        self.assertTrue(strat.fast_fill_enabled)

    def test_instant_fastfill_execution_in_evaluator(self):
        """Verifies that Instant_FastFill enters as TAKER and exits as MAKER on Take Profit."""
        bt_cfg = BacktestConfig(max_spread_bps=2.5)
        evaluator = EdgeEvaluator(
            bt_cfg=bt_cfg,
            strategy_defs={"Instant_FastFill": ("InstantFill", "SMART_TAKER")},
            strategy_params={"Instant_FastFill": {
                "entry_threshold": 0.70,
                "take_profit_bps": 10.0,
                "stop_loss_bps": 10.0,
                "order_size_btc": 1.0,
            }},
        )

        now_ms = 10000
        # Step 1: Bullish trigger (spread is 1.0 bps <= max_spread_bps 2.5) -> Enters as TAKER at best_ask
        evaluator.record_step(
            timestamp_ms=now_ms,
            mid_price=1000.0,
            best_bid=999.95,
            best_ask=1000.05,
            signals={"InstantFill": 0.85},
            confidences={"InstantFill": 0.80},
        )

        st = evaluator.strategies["Instant_FastFill"]
        self.assertTrue(st.is_in_position)
        self.assertEqual(st.position_btc, 1.0)
        self.assertAlmostEqual(st.entry_price, 1000.05, places=1)
        self.assertEqual(evaluator.position_events[0]["exec"], "TAKER")

        # Step 2: Price advances by +15 bps -> Exits on Take Profit as MAKER
        evaluator.record_step(
            timestamp_ms=now_ms + 1000,
            mid_price=1001.6,
            best_bid=1001.55,
            best_ask=1001.65,
            signals={"InstantFill": 0.50},
            confidences={"InstantFill": 0.50},
        )

        self.assertFalse(st.is_in_position)
        self.assertEqual(len(st.trades), 1)
        trade = st.trades[0]
        self.assertIn("TAKE_PROFIT", trade.exit_reason)
        self.assertIn("MAKER", trade.execution_type)
        self.assertGreater(trade.net_pnl_usd, 0.0)


if __name__ == "__main__":
    unittest.main()
