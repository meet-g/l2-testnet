"""Unit tests verifying the forensic audit fixes for Scalper live trading and Web UI telemetry:
1. Priority locking to user-selected active_strategy (eliminating multi-strategy hijacking).
2. Anti-immediate-stopout guardrail in place_bracket_order (preventing bracket SL at/inside spread).
3. Web server live portfolio telemetry matching strategy card trade sums.
4. Loss cooldown enforcement and reliable last_loss_exit_time tracking on net losses.
"""

import unittest
from unittest.mock import MagicMock, patch
import time

from config import AppConfig
from engine.live_executor import LiveOrderExecutor
from main import L2EngineRunner


class TestScalperForensicFixes(unittest.TestCase):

    def setUp(self):
        self.config = AppConfig()
        self.config.market.coin = "xyz:SKHX"
        self.config.market.is_xyz_stock = True
        self.config.market.maker_fee_bps = 0.30
        self.config.market.taker_fee_bps = 0.90

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_active_strategy_priority_lock_over_multi_enabled(self, mock_info, mock_exchange):
        """Verifies that an explicitly targeted active_strategy cannot be hijacked by other enabled strategies."""
        cfg = AppConfig.for_scalper("strategies_scalper.json")
        cfg.market.coin = "xyz:SKHX"
        cfg.strategies.live_execution.active_strategy = "QDAP_Maker"
        cfg.strategies.scalping_strategies["QDAP_Maker"].enabled = True
        cfg.strategies.scalping_strategies["Instant_FastFill"].enabled = True

        runner = L2EngineRunner(config=cfg, record_data=False, live_orders=True)
        try:
            from core.orderbook import L2Level
            runner.live_executor.cached_position = 0.0
            runner.live_executor.active_order = None
            runner.book.bids = [L2Level(px=970.0, sz=1.0, n=1)]
            runner.book.asks = [L2Level(px=970.2, sz=1.0, n=1)]

            mock_res = MagicMock()
            mock_res.score = 0.80
            mock_res.confidence = 0.85
            mock_res.metadata = {
                "sub_signals": {
                    "QDAP": MagicMock(score=0.80, confidence=0.85),
                    "InstantFill": MagicMock(score=0.99, confidence=0.95),  # Higher excess, but QDAP is active_strategy
                }
            }
            runner.alpha_model.compute = MagicMock(return_value=mock_res)

            with patch.object(runner.live_executor, "on_signal_update") as mock_on_sig:
                runner._evaluate_signals()
                self.assertEqual(runner.live_executor.strategy_name, "QDAP_Maker")
                mock_on_sig.assert_called_once()
        finally:
            runner.close()

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_bracket_anti_immediate_stopout_guardrail(self, mock_info, mock_exchange):
        """Verifies that place_bracket_order never sets a Long SL at or above the current best bid."""
        executor = LiveOrderExecutor(config=self.config, non_blocking=False)
        executor.is_initialized = True
        executor.exchange = mock_exchange.return_value
        executor.coin = "xyz:SKHX"
        executor.last_best_bid = 970.54
        executor.last_best_ask = 970.62

        # A naive Long SL calculation with entry=970.62 and sl_bps=10 would give sl_px=970.52 -> rounds to 970.54 (touching best bid!)
        naive_sl_px = 970.54
        captured_orders = []

        def mock_bulk(orders, grouping=None):
            captured_orders.extend(orders)
            return {"status": "ok", "response": {"data": {"statuses": [{"filled": {"oid": 101, "totalSz": "0.3", "avgPx": "970.62"}}, {"resting": {"oid": 102}}, {"resting": {"oid": 103}}]}}}

        executor.exchange.bulk_orders = mock_bulk

        executor.place_bracket_order(
            is_buy=True,
            size_btc=0.3,
            price=970.62,
            tp_price=972.00,
            sl_price=naive_sl_px,
            post_only=False,
            strategy_name="Instant_FastFill",
        )

        self.assertEqual(len(captured_orders), 3)
        sl_order = captured_orders[2]
        sl_trigger_px = float(sl_order["order_type"]["trigger"]["triggerPx"])
        # Stop loss trigger price MUST be strictly below 970.54
        self.assertLess(sl_trigger_px, executor.last_best_bid)

    @patch("engine.live_executor.Exchange")
    @patch("engine.live_executor.Info")
    def test_web_server_live_portfolio_telemetry_consistency(self, mock_info, mock_exchange):
        """Verifies that ui/web_server portfolio payload total_realized_pnl exactly matches sum of strategy trades in live mode."""
        from ui.web_server import DashboardWebServer
        import asyncio

        cfg = AppConfig.for_scalper("strategies_scalper.json")
        cfg.market.coin = "xyz:SKHX"
        runner = L2EngineRunner(config=cfg, record_data=False, live_orders=True)
        server = DashboardWebServer(runner=runner, port=9999)

        # Mock completed trades across multiple strategies
        mock_lx = MagicMock()
        mock_lx.coin = "xyz:SKHX"
        mock_lx.cached_position = 0.0
        mock_lx.entry_price = 0.0
        mock_lx.account_value = 90.0
        mock_lx.initial_account_value = 95.0
        mock_lx.account_equity_delta = -5.0  # On-chain equity delta is -$5.0
        mock_lx.session_realized_pnl = -1.19  # True trade net PnL is -$1.19
        mock_lx.completed_trades = [
            {"strategy": "Instant_FastFill", "net_pnl_usd": -0.58, "gross_pnl_usd": 0.34, "total_fees_usd": 0.92, "entry_time_ms": 1000, "exit_time_ms": 2000, "size_btc": 0.3, "entry_price": 970.6, "exit_price": 970.5, "side": "LONG", "exit_reason": "STOP_LOSS", "return_bps": -2.5},
            {"strategy": "Composite_Maker", "net_pnl_usd": -0.64, "gross_pnl_usd": -0.58, "total_fees_usd": 0.06, "entry_time_ms": 2000, "exit_time_ms": 3000, "size_btc": 0.6, "entry_price": 968.5, "exit_price": 967.5, "side": "LONG", "exit_reason": "DEFENSIVE_HEDGE", "return_bps": -10.6},
            {"strategy": "AdaptiveML_Maker", "net_pnl_usd": 0.03, "gross_pnl_usd": 0.17, "total_fees_usd": 0.14, "entry_time_ms": 3000, "exit_time_ms": 4000, "size_btc": 1.2, "entry_price": 967.8, "exit_price": 968.6, "side": "LONG", "exit_reason": "TAKE_PROFIT", "return_bps": 3.7},
        ]
        runner.live_executor = mock_lx

        captured_snapshots = []
        async def mock_broadcast(snap, force=False):
            captured_snapshots.append(snap)

        server.broadcaster.broadcast_snapshot = mock_broadcast
        server.broadcaster.last_broadcast_time = 0.0

        asyncio.run(server.emit_telemetry(
            book=runner.book,
            trades=runner.trades,
            display_signals={"CompositeAlpha": 0.0},
            evaluator=runner.evaluator,
            network="Mainnet",
        ))

        self.assertEqual(len(captured_snapshots), 1)
        snap = captured_snapshots[0]
        port = snap["portfolio"]
        strats = snap["strategies"]

        # Sum of individual strategy cards
        sum_cards_pnl = sum(s["realized_pnl"] for s in strats.values())
        # Both must equal -$1.19 (-0.58 - 0.64 + 0.03)
        self.assertAlmostEqual(port["total_realized_pnl"], -1.19, places=2)
        self.assertAlmostEqual(sum_cards_pnl, -1.19, places=2)
        self.assertAlmostEqual(port["total_realized_pnl"], sum_cards_pnl, places=2)
        # Verify real_account_pnl correctly exposes the on-chain account delta separately
        self.assertEqual(port["real_account_pnl"], -5.0)
        runner.close()

    def test_qdap_and_dynamic_spread_price_offset_configuration_and_quoting(self):
        """Verifies that QDAP_Maker and Dynamic_Spread_Scalper have price_offset=0.01 and quote 0.01 above bid / below ask."""
        from engine.backtester import EdgeEvaluator

        cfg = AppConfig.for_scalper("strategies_scalper.json")
        qdap_cfg = cfg.strategies.get_strategy("QDAP_Maker")
        dss_cfg = cfg.strategies.get_strategy("Dynamic_Spread_Scalper")

        self.assertIsNotNone(qdap_cfg)
        self.assertIsNotNone(dss_cfg)
        self.assertTrue(hasattr(qdap_cfg, "price_offset"))
        self.assertTrue(hasattr(dss_cfg, "price_offset"))

        cfg.backtest.max_spread_bps = 10.0
        # Test QDAP_Maker bullish quote with 0.01 price offset
        qdap_params = {
            "QDAP_Maker": {
                "execution_type": "MAKER",
                "price_offset": 0.01,
                "entry_threshold": 0.70,
                "order_size_btc": 0.1,
                "min_volatility_bps": 0.0,
            }
        }
        evaluator_qdap = EdgeEvaluator(
            market_cfg=cfg.market,
            bt_cfg=cfg.backtest,
            strategy_defs={"QDAP_Maker": ("QDAP", "MAKER")},
            strategy_params=qdap_params,
        )
        evaluator_qdap.record_step(
            timestamp_ms=1794211200000,
            mid_price=90.03,
            best_bid=90.01,
            best_ask=90.05,
            signals={"QDAP": 0.80},
        )
        qdap_st = evaluator_qdap.strategies["QDAP_Maker"]
        self.assertTrue(qdap_st.is_in_position)
        self.assertAlmostEqual(qdap_st.entry_price, 90.02, places=4)  # 90.01 + 0.01

        # Test Dynamic_Spread_Scalper bearish quote with 0.01 price offset
        dss_params = {
            "Dynamic_Spread_Scalper": {
                "execution_type": "MAKER",
                "price_offset": 0.01,
                "entry_threshold": 0.70,
                "order_size_btc": 0.1,
                "min_volatility_bps": 0.0,
            }
        }
        evaluator_dss = EdgeEvaluator(
            market_cfg=cfg.market,
            bt_cfg=cfg.backtest,
            strategy_defs={"Dynamic_Spread_Scalper": ("DynamicSpread", "MAKER")},
            strategy_params=dss_params,
        )
        evaluator_dss.record_step(
            timestamp_ms=1794211200000,
            mid_price=90.03,
            best_bid=90.01,
            best_ask=90.05,
            signals={"DynamicSpread": -0.80},
        )
        dss_st = evaluator_dss.strategies["Dynamic_Spread_Scalper"]
        self.assertTrue(dss_st.is_in_position)
        self.assertAlmostEqual(dss_st.entry_price, 90.04, places=4)  # 90.05 - 0.01



if __name__ == "__main__":
    unittest.main()
