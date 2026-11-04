"""Unit tests verifying Stoikov MicroPrice trend and CVD alignment filters and executor guards."""

import unittest
from unittest.mock import MagicMock, patch

from core.orderbook import OrderBook
from core.trade_stream import TradeManager
from signals.microprice import MicroPriceSignal
from engine.live_executor import LiveOrderExecutor
from engine.backtester import EdgeEvaluator
from config import AppConfig, BacktestConfig, MarketConfig, ExecutionStrategyConfig, ScalpingStrategyConfig


def make_l2_data(mid: float, qb: float, qa: float, t_ms: int):
    return {
        "coin": "xyz:SKHX",
        "time": t_ms,
        "levels": [
            [{"px": f"{mid - 0.05:.2f}", "sz": f"{qb:.3f}", "n": 5}],
            [{"px": f"{mid + 0.05:.2f}", "sz": f"{qa:.3f}", "n": 5}],
        ],
    }


class TestMicroPriceSignalTrendFilter(unittest.TestCase):
    """Verifies that MicroPriceSignal suppresses counter-trend touch imbalance spikes."""

    def setUp(self):
        self.signal = MicroPriceSignal(
            trend_filter_enabled=True,
            trend_window_secs=60.0,
            max_counter_trend_bps=1.0,
            require_cvd_alignment=True,
            cvd_window_secs=30.0,
        )
        self.book = OrderBook()
        self.trades = TradeManager()

    def test_suppress_buy_when_60s_trend_is_negative(self):
        """MicroPrice BUY must be suppressed when 60s price drift is down."""
        base_ms = 1_000_000

        # Feed declining prices over 60 seconds
        for step in range(10):
            t_ms = base_ms + step * 6000
            px = 1000.0 - step * 1.0  # Drops from 1000 to 991 (-90 bps)
            self.book.update_from_raw(make_l2_data(px, qb=5.0, qa=0.5, t_ms=t_ms))
            res = self.signal.compute(self.book, self.trades, timestamp_ms=t_ms)

        # On the 10th step, touch imbalance is very bullish (5.0 vs 0.5)
        # But 60s trend is negative (-90 bps) -> must be suppressed!
        self.assertTrue(res.metadata["counter_trend_suppressed"])
        self.assertLessEqual(res.score, 0.20)
        self.assertLessEqual(res.confidence, 0.25)
        self.assertIn("Trend", res.metadata["suppression_reason"])

    def test_suppress_buy_when_cvd_is_negative(self):
        """MicroPrice BUY must be suppressed when 30s CVD has heavy sell dumping."""
        base_ms = 1_000_000

        # Feed flat prices
        for step in range(8):
            t_ms = base_ms + step * 5000
            px = 1000.0
            self.book.update_from_raw(make_l2_data(px, qb=5.0, qa=0.5, t_ms=t_ms))
            res = self.signal.compute(self.book, self.trades, timestamp_ms=t_ms)

        # Ingest aggressive taker sell volume into TradeManager
        now_ms = base_ms + 40000
        self.trades.process_raw_trades([
            {"coin": "xyz:SKHX", "side": "A", "px": "999.9", "sz": "10.0", "time": now_ms - 5000, "hash": "h1"},
            {"coin": "xyz:SKHX", "side": "A", "px": "999.9", "sz": "25.0", "time": now_ms - 2000, "hash": "h2"},
        ])
        self.book.update_from_raw(make_l2_data(1000.0, qb=5.0, qa=0.5, t_ms=now_ms))
        res = self.signal.compute(self.book, self.trades, timestamp_ms=now_ms)

        self.assertTrue(res.metadata["counter_trend_suppressed"])
        self.assertLessEqual(res.score, 0.20)
        self.assertIn("CVD negative", res.metadata["suppression_reason"])

    def test_suppress_sell_when_60s_trend_is_positive(self):
        """MicroPrice SELL must be suppressed when 60s price drift is rallying up."""
        base_ms = 1_000_000

        # Feed rising prices over 60 seconds
        for step in range(10):
            t_ms = base_ms + step * 6000
            px = 1000.0 + step * 1.0  # Rallies from 1000 to 1009 (+90 bps)
            self.book.update_from_raw(make_l2_data(px, qb=0.5, qa=5.0, t_ms=t_ms))
            res = self.signal.compute(self.book, self.trades, timestamp_ms=t_ms)

        # Imbalance is bearish (0.5 vs 5.0 -> raw score ~ -0.90)
        # But 60s trend is positive -> must be suppressed!
        self.assertTrue(res.metadata["counter_trend_suppressed"])
        self.assertGreaterEqual(res.score, -0.20)
        self.assertLessEqual(res.confidence, 0.25)
        self.assertIn("Trend", res.metadata["suppression_reason"])

    def test_suppress_sell_when_cvd_is_positive(self):
        """MicroPrice SELL must be suppressed when 30s CVD has aggressive buying."""
        base_ms = 1_000_000

        for step in range(8):
            t_ms = base_ms + step * 5000
            px = 1000.0
            self.book.update_from_raw(make_l2_data(px, qb=0.5, qa=5.0, t_ms=t_ms))
            res = self.signal.compute(self.book, self.trades, timestamp_ms=t_ms)

        now_ms = base_ms + 40000
        self.trades.process_raw_trades([
            {"coin": "xyz:SKHX", "side": "B", "px": "1000.1", "sz": "15.0", "time": now_ms - 5000, "hash": "h1"},
            {"coin": "xyz:SKHX", "side": "B", "px": "1000.1", "sz": "30.0", "time": now_ms - 2000, "hash": "h2"},
        ])
        self.book.update_from_raw(make_l2_data(1000.0, qb=0.5, qa=5.0, t_ms=now_ms))
        res = self.signal.compute(self.book, self.trades, timestamp_ms=now_ms)

        self.assertTrue(res.metadata["counter_trend_suppressed"])
        self.assertGreaterEqual(res.score, -0.20)
        self.assertIn("CVD positive", res.metadata["suppression_reason"])

    def test_allow_trend_aligned_signals(self):
        """Signals aligned with trend must NOT be suppressed and keep high conviction."""
        base_ms = 1_000_000

        # Feed rising prices
        for step in range(10):
            t_ms = base_ms + step * 6000
            px = 1000.0 + step * 1.0
            # Bullish book aligned with uptrend
            self.book.update_from_raw({
                "coin": "xyz:SKHX",
                "time": t_ms,
                "levels": [
                    [{"px": f"{px - 0.05:.2f}", "sz": "5.0", "n": 5}, {"px": f"{px - 0.15:.2f}", "sz": "10.0", "n": 10}],
                    [{"px": f"{px + 0.05:.2f}", "sz": "0.5", "n": 2}, {"px": f"{px + 0.15:.2f}", "sz": "1.0", "n": 3}],
                ]
            })
            res = self.signal.compute(self.book, self.trades, timestamp_ms=t_ms)

        self.assertFalse(res.metadata["counter_trend_suppressed"])
        self.assertGreaterEqual(res.score, 0.80)
        self.assertGreater(res.confidence, 0.50)


class TestLiveExecutorTrendFilterGuard(unittest.TestCase):
    """Verifies that LiveOrderExecutor blocks counter-trend entries when trend_filter_enabled is True."""

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    @patch("engine.live_executor.eth_account.Account.from_key")
    def setUp(self, mock_from_key, mock_info_cls, mock_exchange_cls):
        mock_wallet = MagicMock()
        mock_wallet.address = "0x1234567890abcdef"
        mock_from_key.return_value = mock_wallet

        mock_info = MagicMock()
        mock_info.meta.return_value = {
            "universe": [{"name": "xyz:SKHX", "szDecimals": 3, "maxPriceDecimals": 2}]
        }
        mock_info.name_to_asset.return_value = 10001
        mock_info_cls.return_value = mock_info

        mock_exchange = MagicMock()
        mock_exchange.info = mock_info
        mock_exchange_cls.return_value = mock_exchange

        self.cfg = AppConfig()
        self.cfg.hyperliquid.secret_key = "0x" + "1" * 64
        self.cfg.market.coin = "xyz:SKHX"

        # Configure MicroPrice_FastFill with trend filter enabled
        self.cfg.strategies.scalping_strategies["MicroPrice_FastFill"] = ScalpingStrategyConfig(
            name="MicroPrice_FastFill",
            enabled=True,
            signal_key="MicroPrice",
            execution_type="SMART_TAKER",
            entry_threshold=0.80,
            trend_filter_enabled=True,
            trend_window_secs=60.0,
            max_counter_trend_bps=1.0,
            require_cvd_alignment=True,
        )

        self.executor = LiveOrderExecutor(config=self.cfg)
        self.executor.is_initialized = True
        self.executor.sync_state = MagicMock()
        self.executor.cached_position = 0.0
        self.executor.place_limit_order = MagicMock()
        self.executor.cancel_order = MagicMock()

    def test_executor_rejects_counter_trend_buy(self):
        """LiveOrderExecutor must reject BUY entry when price history has negative trend."""
        import time
        now = time.time()

        # Seed declining price history in executor
        for i in range(10):
            t_sec = now - 60.0 + i * 6.0
            px = 1050.0 - i * 1.5  # Drops from 1050 to 1036.5 (-128 bps)
            self.executor._price_history.append((t_sec, px))

        best_bid = 1036.4
        best_ask = 1036.6
        spread = 0.2

        self.executor.strategy_name = "MicroPrice_FastFill"
        # Receive strong bullish score (+0.95)
        self.executor.on_signal_update(
            signal_score=0.95,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
        )

        # Place order should NOT have been called due to negative trend!
        self.executor.place_limit_order.assert_not_called()

    def test_executor_permits_trend_aligned_buy(self):
        """LiveOrderExecutor permits BUY entry when price history has positive trend."""
        import time
        now = time.time()

        # Seed rising price history
        for i in range(10):
            t_sec = now - 60.0 + i * 6.0
            px = 1030.0 + i * 1.0  # Rises from 1030 to 1039 (+87 bps)
            self.executor._price_history.append((t_sec, px))

        best_bid = 1039.0
        best_ask = 1039.2
        spread = 0.2

        self.executor.strategy_name = "MicroPrice_FastFill"
        self.executor.on_signal_update(
            signal_score=0.95,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
        )

        # Place order MUST be called for trend-aligned entry
        self.executor.place_limit_order.assert_called_once()
        args, kwargs = self.executor.place_limit_order.call_args
        self.assertTrue(kwargs.get("is_buy"))


class TestBacktesterTrendFilterGate(unittest.TestCase):
    """Verifies that EdgeEvaluator respects trend_filter_enabled."""

    def test_backtester_skips_counter_trend_buy(self):
        market_cfg = MarketConfig(coin="xyz:SKHX")
        bt_cfg = BacktestConfig(force_market_orders=True)

        strat_defs = {"MicroPrice_FastFill": ("MicroPrice", "SMART_TAKER")}
        strat_params = {
            "MicroPrice_FastFill": {
                "entry_threshold": 0.80,
                "trend_filter_enabled": True,
                "trend_window_secs": 60.0,
                "max_counter_trend_bps": 1.0,
                "order_size_btc": 0.1,
            }
        }

        evaluator = EdgeEvaluator(
            market_cfg=market_cfg,
            bt_cfg=bt_cfg,
            strategy_defs=strat_defs,
            strategy_params=strat_params,
        )

        base_ms = 1_000_000
        # Feed declining prices
        for step in range(10):
            t_ms = base_ms + step * 6000
            px = 1000.0 - step * 2.0  # Drops from 1000 to 982
            # At step 9, feed BUY signal (+0.90)
            score = 0.90 if step >= 8 else 0.0
            evaluator.record_step(
                timestamp_ms=t_ms,
                mid_price=px,
                best_bid=px - 0.1,
                best_ask=px + 0.1,
                signals={"MicroPrice": score},
            )

        # Counter-trend BUY should have been rejected by EdgeEvaluator
        state = evaluator.strategies["MicroPrice_FastFill"]
        self.assertEqual(len(state.trades), 0)
        self.assertFalse(state.is_in_position)


if __name__ == "__main__":
    unittest.main()
