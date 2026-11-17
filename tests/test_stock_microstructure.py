"""Unit tests verifying the Stock_Microstructure_Alpha strategy and StockMicrostructure signal."""

import unittest
from core.orderbook import OrderBook, L2Level
from core.trade_stream import TradeManager
from signals.stock_microstructure import StockMicrostructureSignal
from signals.composite_alpha import CompositeAlphaSignal
from config import (
    AppConfig,
    CoreStrategiesConfig,
    CORE_EXECUTION_STRATEGIES,
    XYZ_STOCK_MAKER_FEE_BPS,
    XYZ_STOCK_TAKER_FEE_BPS,
)
from engine.backtester import EdgeEvaluator


class TestStockMicrostructureStrategy(unittest.TestCase):
    """Test suite for StockMicrostructureSignal and Stock_Microstructure_Alpha core execution strategy."""

    def setUp(self):
        self.signal = StockMicrostructureSignal()
        self.book = OrderBook(coin="xyz:SKHX")
        self.trades = TradeManager()

    def _setup_valid_book(self, bid_px=840.0, ask_px=840.10, bid_sz=10.0, ask_sz=5.0):
        snapshot = {
            "coin": "xyz:SKHX",
            "time": 1794211200000,
            "levels": [
                [
                    {"px": str(bid_px - i * 0.1), "sz": str(bid_sz), "n": 3}
                    for i in range(10)
                ],
                [
                    {"px": str(ask_px + i * 0.1), "sz": str(ask_sz), "n": 2}
                    for i in range(10)
                ],
            ],
        }
        self.book.update_from_raw(snapshot)

    def test_invalid_book_returns_zero(self):
        """Signal must return 0 score and confidence when book is empty or invalid."""
        res = self.signal.compute(self.book, self.trades, 1794211200000)
        self.assertEqual(res.score, 0.0)
        self.assertEqual(res.confidence, 0.0)

    def test_spread_gating(self):
        """Signal must suppress entry (score 0.0, gated=True) when spread exceeds max_spread_bps."""
        # Spread: 840.0 to 843.0 = 3.0 on 841.5 = 35.6 bps > 2.0 bps
        self._setup_valid_book(bid_px=840.0, ask_px=843.0, bid_sz=10.0, ask_sz=5.0)
        res = self.signal.compute(self.book, self.trades, 1794211200000)
        self.assertEqual(res.score, 0.0)
        self.assertTrue(res.metadata.get("gated", False))

    def test_bullish_imbalance_and_drift(self):
        """Signal must produce a positive (bullish) score when bid queue and depth dominate."""
        # Spread is tight: $840.00 to $840.06 (~0.71 bps)
        # Bids have 20.0 sz per level, asks have only 2.0 sz per level
        self._setup_valid_book(bid_px=840.00, ask_px=840.06, bid_sz=20.0, ask_sz=2.0)
        res = self.signal.compute(self.book, self.trades, 1794211200000)
        self.assertGreater(res.score, 0.30)
        self.assertTrue(res.is_bullish)
        self.assertFalse(res.is_bearish)
        self.assertGreater(res.confidence, 0.50)

    def test_bearish_imbalance_and_drift(self):
        """Signal must produce a negative (bearish) score when ask queue and depth dominate."""
        # Spread is tight: $840.00 to $840.06 (~0.71 bps)
        # Bids have 2.0 sz per level, asks have 20.0 sz per level
        self._setup_valid_book(bid_px=840.00, ask_px=840.06, bid_sz=2.0, ask_sz=20.0)
        res = self.signal.compute(self.book, self.trades, 1794211200000)
        self.assertLess(res.score, -0.30)
        self.assertTrue(res.is_bearish)
        self.assertFalse(res.is_bullish)

    def test_composite_alpha_contains_stock_microstructure(self):
        """CompositeAlphaSignal must integrate StockMicrostructure in its sub_signals."""
        alpha = CompositeAlphaSignal()
        self._setup_valid_book(bid_px=840.00, ask_px=840.06, bid_sz=10.0, ask_sz=5.0)
        res = alpha.compute(self.book, self.trades, 1794211200000)
        sub_sigs = res.metadata.get("sub_signals", {})
        self.assertIn("StockMicrostructure", sub_sigs)
        self.assertIsInstance(sub_sigs["StockMicrostructure"].score, float)

    def test_core_strategy_configuration_registration(self):
        """Verifies Stock_Microstructure_Alpha is registered as a Core Execution Strategy."""
        self.assertIn("Stock_Microstructure_Alpha", CORE_EXECUTION_STRATEGIES)
        cfg = CoreStrategiesConfig.load("strategies_core.json")
        self.assertIn("Stock_Microstructure_Alpha", cfg.execution_strategies)
        s = cfg.execution_strategies["Stock_Microstructure_Alpha"]
        self.assertEqual(s.signal_key, "StockMicrostructure")
        self.assertEqual(s.execution_type, "HEDGED_MAKER")
        self.assertEqual(getattr(s, "price_offset", 0.0), 0.01)
        self.assertEqual(s.entry_threshold, 0.55)
        self.assertEqual(s.take_profit_bps, 7.0)
        self.assertEqual(s.stop_loss_bps, 5.5)
        self.assertEqual(s.trailing_stop_activation_bps, 1.8)
        self.assertEqual(s.trailing_stop_distance_bps, 0.8)
        self.assertEqual(s.min_volatility_bps, 0.0)

    def test_original_strategies_unmodified(self):
        """Verifies original 4 strategies remain strictly intact and unchanged."""
        cfg = CoreStrategiesConfig.load("strategies_core.json")
        orig_expected = {
            "Hedged_Convexity": (0.86, 20.0, 8.0, 4.5),
            "Convexity_Cascade": (0.80, 20.0, 8.0, 4.5),
            "Momentum_Expansion": (0.78, 20.0, 8.0, 4.5),
            "Queue_Replenishment": (0.985, 30.0, 8.0, 4.5),
        }
        for name, (th, tp, sl, min_v) in orig_expected.items():
            self.assertIn(name, cfg.execution_strategies)
            strat = cfg.execution_strategies[name]
            self.assertEqual(strat.entry_threshold, th, f"{name} threshold altered")
            self.assertEqual(strat.take_profit_bps, tp, f"{name} take profit altered")
            self.assertEqual(strat.stop_loss_bps, sl, f"{name} stop loss altered")
            self.assertEqual(strat.min_volatility_bps, min_v, f"{name} min volatility altered")

    def test_edge_evaluator_execution(self):
        """Verifies EdgeEvaluator accurately executes and logs Stock_Microstructure_Alpha."""
        app_cfg = AppConfig.for_core()
        app_cfg.market.coin = "xyz:SKHX"
        app_cfg.market.is_xyz_stock = True
        app_cfg.backtest.max_spread_bps = 10.0
        app_cfg.market.taker_fee_bps = XYZ_STOCK_TAKER_FEE_BPS
        app_cfg.market.maker_fee_bps = XYZ_STOCK_MAKER_FEE_BPS

        evaluator = EdgeEvaluator(
            market_cfg=app_cfg.market,
            bt_cfg=app_cfg.backtest,
            strategy_defs={"Stock_Microstructure_Alpha": ("StockMicrostructure", "HEDGED_MAKER")},
        )
        self.assertIn("Stock_Microstructure_Alpha", evaluator.strategies)

    def test_price_offset_execution(self):
        """Verifies entry prices buy 0.01 above best_bid and sell 0.01 below best_ask when price_offset=0.01."""
        app_cfg = AppConfig.for_core()
        app_cfg.market.coin = "xyz:SKHX"
        app_cfg.market.is_xyz_stock = True
        app_cfg.backtest.max_spread_bps = 10.0

        strat_params = {
            "Stock_Microstructure_Alpha": {
                "execution_type": "HEDGED_MAKER",
                "price_offset": 0.01,
                "entry_threshold": 0.50,
                "order_size_btc": 10.0,
            }
        }
        evaluator = EdgeEvaluator(
            market_cfg=app_cfg.market,
            bt_cfg=app_cfg.backtest,
            strategy_defs={"Stock_Microstructure_Alpha": ("StockMicrostructure", "HEDGED_MAKER")},
            strategy_params=strat_params,
        )

        # Trigger bullish entry with best_bid=90.01, best_ask=90.05
        evaluator.record_step(
            timestamp_ms=1794211200000,
            mid_price=90.03,
            best_bid=90.01,
            best_ask=90.05,
            signals={"StockMicrostructure": 0.60},
        )
        st = evaluator.strategies["Stock_Microstructure_Alpha"]
        self.assertTrue(st.is_in_position)
        self.assertAlmostEqual(st.entry_price, 90.02, places=4)  # 90.01 + 0.01

        # Reset and trigger bearish entry with best_bid=90.01, best_ask=90.05
        st.position_btc = 0.0
        st.entry_price = 0.0
        evaluator.record_step(
            timestamp_ms=1794211201000,
            mid_price=90.03,
            best_bid=90.01,
            best_ask=90.05,
            signals={"StockMicrostructure": -0.60},
        )
        self.assertTrue(st.is_in_position)
        self.assertAlmostEqual(st.entry_price, 90.04, places=4)  # 90.05 - 0.01

    def test_capital_usd_sizing_and_drawdown(self):
        """Verifies that capital_usd=100 scales trade size to ~$100 notional without 85x blowout and keeps drawdown correct."""
        app_cfg = AppConfig.for_core()
        app_cfg.market.coin = "xyz:SKHX"
        app_cfg.market.is_xyz_stock = True
        app_cfg.backtest.capital_usd = 100.0
        app_cfg.backtest.initial_cash_usd = 100.0
        app_cfg.backtest.max_spread_bps = 10.0

        strat_params = {
            "Stock_Microstructure_Alpha": {
                "execution_type": "HEDGED_MAKER",
                "price_offset": 0.01,
                "entry_threshold": 0.50,
                "order_size_btc": 10.0,
            }
        }

        evaluator = EdgeEvaluator(
            market_cfg=app_cfg.market,
            bt_cfg=app_cfg.backtest,
            strategy_defs={"Stock_Microstructure_Alpha": ("StockMicrostructure", "HEDGED_MAKER")},
            strategy_params=strat_params,
        )

        st = evaluator.strategies["Stock_Microstructure_Alpha"]
        self.assertEqual(st.peak_equity, 100.0)
        self.assertEqual(st.cash_usd, 100.0)

        # Trigger bullish entry @ mid=840.0
        evaluator.record_step(
            timestamp_ms=1794211200000,
            mid_price=840.0,
            best_bid=839.9,
            best_ask=840.1,
            signals={"StockMicrostructure": 0.85},
        )
        self.assertTrue(st.is_in_position)
        # 100 USD / 840.0 = ~0.119 shares ($99.96 notional)
        self.assertAlmostEqual(st.position_btc, 0.119, places=3)
        notional = st.position_btc * 840.0
        self.assertLessEqual(notional, 100.5)
        self.assertGreaterEqual(notional, 90.0)
        self.assertLess(st.max_drawdown_usd, 1.0)


if __name__ == "__main__":
    unittest.main()
