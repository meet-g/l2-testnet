"""Adversarial Empirical Challenge Test Suite for QueueReplenishment.

Adversarially challenges:
1. Low/Zero Volatility Gating:
   - Verifies that when volatility < min_volatility_bps (4.5 bps), no spurious entries
     trigger regardless of signal saturation (+1.0 or -1.0).
   - Verifies sharp boundary threshold transitions (4.40 bps suppressed vs 4.60 bps permitted).
2. Flow Reversal Stress & Defensive Maker Hedging:
   - Verifies that defensive maker hedging triggers at -3.5 bps loss on signal reversal
     (<= -0.15 for long, >= +0.15 for short) saving 3.0 bps taker fee + 0.2 bps slippage.
   - Counter-factual verification: proves it prevents catastrophic taker stop loss (-8.0 bps).
   - Verified for both LONG and SHORT position directions.
3. Skew and Order Book Depth Collapse Numerical Robustness:
   - 10,000 adversarial stress iterations covering zero depth, 1e-18 depth, multi-tick sweeps,
     massive skew (1e8 vs 1e-8), cancellation cascades, and degenerate books.
   - Verifies zero NaNs, infinities, division by zero, or bounds violations in
     Rb1, Ra1, Rb3, Ra3, S_canc, score, and confidence.
"""

import math
import os
import random
import sys
import unittest
from typing import Dict, List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import BacktestConfig, MarketConfig
from core.orderbook import L2Level, OrderBook
from core.trade_stream import TradeManager
from engine.backtester import EdgeEvaluator
from signals.queue_replenishment import QueueReplenishmentSignal


class MockScaledOrderBook(OrderBook):
    """Custom OrderBook subclass to stress non-standard notional_scale values."""

    def __init__(self, scale_val: float = 1.0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._custom_scale = scale_val

    @property
    def notional_scale(self) -> float:
        return self._custom_scale


class TestAdversarialQueueReplenishment(unittest.TestCase):
    """Empirical adversarial challenger test suite."""

    def setUp(self):
        random.seed(42)

    def _create_mock_book(
        self,
        coin: str = "HYPE",
        mid_px: float = 25.00,
        spread: float = 0.002,  # 0.8 bps spread (well within 1.5 bps max_spread_bps)
        depth_levels: int = 5,
        bid_sz: float = 100.0,
        ask_sz: float = 100.0,
        ts_ms: int = 1710000000000,
        custom_scale: float = None,
    ) -> OrderBook:
        if custom_scale is not None:
            book = MockScaledOrderBook(scale_val=custom_scale, coin=coin, max_history=10, enable_history=False)
        else:
            book = OrderBook(coin=coin, max_history=10, enable_history=False)

        half_spr = spread * 0.5
        bb = mid_px - half_spr
        ba = mid_px + half_spr

        bids: List[L2Level] = []
        asks: List[L2Level] = []
        for i in range(depth_levels):
            bids.append(L2Level(px=round(bb - i * spread, 6), sz=bid_sz * (1.0 + 0.1 * i), n=5 + i))
            asks.append(L2Level(px=round(ba + i * spread, 6), sz=ask_sz * (1.0 + 0.1 * i), n=5 + i))

        book.bids = bids
        book.asks = asks
        book.last_update_time_ms = ts_ms
        return book

    def _create_mock_trades(
        self,
        coin: str = "HYPE",
        trades_list: List[tuple] = None,
        base_ts_ms: int = 1710000000000,
    ) -> TradeManager:
        tm = TradeManager(coin=coin)
        if trades_list:
            raw = []
            for idx, (side, px, sz, offset_ms) in enumerate(trades_list):
                raw.append({
                    "coin": coin,
                    "side": side,
                    "px": str(px),
                    "sz": str(sz),
                    "time": base_ts_ms + offset_ms,
                    "tid": idx + 1,
                })
            tm.process_raw_trades(raw)
        return tm

    def _create_backtester(self, min_vol_bps: float = 4.5) -> EdgeEvaluator:
        """Instantiate EdgeEvaluator configured with Queue_Replenishment parameters."""
        market_cfg = MarketConfig(
            coin="HYPE",
            maker_fee_bps=1.5,
            taker_fee_bps=4.5,
            maker_rebate_bps=1.5,
        )
        bt_cfg = BacktestConfig(
            initial_cash_usd=10000.0,
            slippage_bps=0.2,
            max_spread_bps=1.5,
            horizons_seconds=[],  # fast execution bypass
        )
        strategy_params = {
            "Queue_Replenishment": {
                "enabled": True,
                "execution_type": "HEDGED_MAKER",
                "entry_threshold": 0.985,
                "order_size_btc": 0.1,
                "take_profit_bps": 30.0,
                "stop_loss_bps": 8.0,
                "trailing_stop_activation_bps": 4.0,
                "trailing_stop_distance_bps": 1.5,
                "hedge_trigger_loss_bps": -3.5,
                "hedge_reversal_threshold": -0.15,
                "max_holding_time_secs": 180,
                "exit_reversal_threshold": 0.80,
                "min_volatility_bps": min_vol_bps,
                "loss_cooldown_secs": 120,
            }
        }
        engine = EdgeEvaluator(
            market_cfg=market_cfg,
            bt_cfg=bt_cfg,
            strategy_params=strategy_params,
            strategy_defs={"Queue_Replenishment": ("QueueReplenishment", "HEDGED_MAKER")},
        )
        return engine

    # =========================================================================
    # PART 1: LOW / ZERO VOLATILITY GATING EMPIRICAL STRESS
    # =========================================================================

    def test_zero_volatility_suppresses_all_entries(self):
        """Stress: 0.0 bps dead-flat market MUST suppress 100% of entries even with score = 1.0."""
        engine = self._create_backtester(min_vol_bps=4.5)
        state = engine.strategies["Queue_Replenishment"]

        # Run 20 warmup steps at flat price $25.00 (each step 1 sec apart)
        ts = 1710000000000
        for i in range(20):
            engine.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=25.0000,
                best_bid=24.9990,
                best_ask=25.0010,
                signals={"QueueReplenishment": 0.0},
            )

        # Confirm volatility dropped to 0.0 bps
        self.assertEqual(engine.current_volatility_bps, 0.0)

        # Now hammer with saturated bullish entry signals (+1.0)
        for i in range(20, 100):
            engine.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=25.0000,
                best_bid=24.9990,
                best_ask=25.0010,
                signals={"QueueReplenishment": 1.0},
            )

        self.assertFalse(state.is_in_position, "Spurious LONG entry triggered in 0 bps volatility!")
        self.assertEqual(len(state.trades), 0, "Trades executed in zero volatility!")

        # Now hammer with saturated bearish entry signals (-1.0)
        for i in range(100, 200):
            engine.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=25.0000,
                best_bid=24.9990,
                best_ask=25.0010,
                signals={"QueueReplenishment": -1.0},
            )

        self.assertFalse(state.is_in_position, "Spurious SHORT entry triggered in 0 bps volatility!")
        self.assertEqual(len(state.trades), 0, "Trades executed in zero volatility!")

    def test_sub_hurdle_micro_chop_suppresses_entries(self):
        """Stress: Micro-chop oscillating between 25.0000 and 25.0075 (3.0 bps < 4.5 bps hurdle)."""
        engine = self._create_backtester(min_vol_bps=4.5)
        state = engine.strategies["Queue_Replenishment"]

        ts = 1710000000000
        # 1. Warmup with 20 steps of micro-chop
        for i in range(20):
            price_offset = 0.0075 if (i % 2 == 0) else 0.0000
            mid = 25.0000 + price_offset
            engine.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=mid,
                best_bid=mid - 0.0010,
                best_ask=mid + 0.0010,
                signals={"QueueReplenishment": 0.0},
            )

        # After warmup, volatility is strictly <= 3.01 bps (< 4.5 bps hurdle)
        self.assertLess(engine.current_volatility_bps, 4.5)

        # 2. Hammer with 500 steps of saturated entry signals (+0.99, -0.99)
        for i in range(20, 520):
            price_offset = 0.0075 if (i % 2 == 0) else 0.0000
            mid = 25.0000 + price_offset
            sig_val = 0.99 if (i % 4 < 2) else -0.99

            engine.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=mid,
                best_bid=mid - 0.0010,
                best_ask=mid + 0.0010,
                signals={"QueueReplenishment": sig_val},
            )

        # All 500 post-warmup steps must have rejected entry
        self.assertFalse(state.is_in_position, "Spurious trade opened during 3.0 bps micro-chop!")
        self.assertEqual(len(state.trades), 0, "Trades recorded in sub-hurdle micro-chop!")

    def test_warmup_transition_to_volatility_gating(self):
        """Stress: Verify exact step (step 15) where volatility calculation activates and locks gating."""
        engine = self._create_backtester(min_vol_bps=4.5)

        ts = 1710000000000
        # Steps 0 to 13 (< 15 steps): engine stays in warmup mode (current_volatility_bps = 99.0)
        for i in range(14):
            engine.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=25.0000,
                best_bid=24.9990,
                best_ask=25.0010,
                signals={"QueueReplenishment": 0.0},
            )
            self.assertEqual(engine.current_volatility_bps, 99.0)

        # Step 14 (15th sample): engine reaches 15 samples and immediately evaluates true amplitude
        engine.record_step(
            timestamp_ms=ts + 14 * 1000,
            mid_price=25.0000,
            best_bid=24.9990,
            best_ask=25.0010,
            signals={"QueueReplenishment": 0.0},
        )
        self.assertEqual(engine.current_volatility_bps, 0.0, "Engine failed to transition to 0.0 bps at step 15!")

    def test_volatility_boundary_cliff(self):
        """Stress: Sharp boundary transition.
        At 4.40 bps (strictly < 4.50 bps) -> 0 entries.
        At 4.60 bps (strictly > 4.50 bps) -> entry triggers immediately.
        """
        engine = self._create_backtester(min_vol_bps=4.5)
        state = engine.strategies["Queue_Replenishment"]

        ts = 1710000000000
        # Warmup and establish 4.40 bps range: 25.0000 to 25.0110 (4.40 bps)
        for i in range(25):
            mid = 25.0000 if (i % 2 == 0) else 25.0110
            engine.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=mid,
                best_bid=mid - 0.0010,
                best_ask=mid + 0.0010,
                signals={"QueueReplenishment": 0.0},
            )

        self.assertAlmostEqual(engine.current_volatility_bps, 4.40, delta=0.05)
        self.assertLess(engine.current_volatility_bps, 4.50)

        # Attempt entry at 4.40 bps: MUST BE BLOCKED
        engine.record_step(
            timestamp_ms=ts + 26 * 1000,
            mid_price=25.0050,
            best_bid=25.0040,
            best_ask=25.0060,
            signals={"QueueReplenishment": 0.99},
        )
        self.assertFalse(state.is_in_position, "Entry triggered below 4.5 bps hurdle (4.40 bps)!")

        # Now expand price range to 4.60 bps: min 25.0000, max 25.0115 (4.60 bps)
        engine.record_step(
            timestamp_ms=ts + 27 * 1000,
            mid_price=25.0115,
            best_bid=25.0105,
            best_ask=25.0125,
            signals={"QueueReplenishment": 0.0},
        )
        self.assertGreater(engine.current_volatility_bps, 4.50)

        # Now attempt entry at 4.60 bps: MUST TRIGGER
        engine.record_step(
            timestamp_ms=ts + 28 * 1000,
            mid_price=25.0050,
            best_bid=25.0040,
            best_ask=25.0060,
            signals={"QueueReplenishment": 0.99},
        )
        self.assertTrue(state.is_in_position, "Entry failed to trigger when volatility exceeded hurdle (4.60 bps)!")
        self.assertGreater(state.position_btc, 0.0)

    # =========================================================================
    # PART 2: FLOW REVERSAL STRESS & DEFENSIVE MAKER HEDGING
    # =========================================================================

    def test_defensive_maker_hedge_long_vs_taker_stop_loss(self):
        """Stress: Long position facing severe adverse flow reversal.
        Verifies:
        1. When loss reaches -3.5 bps and signal reverses to <= -0.15,
           DEFENSIVE_MAKER_HEDGE triggers as MAKER at best_ask (1.5 bps fee).
        2. Paired Counter-factual: without hedge trigger, price continues down to -8.0 bps
           where catastrophic STOP_LOSS triggers as TAKER at best_bid * (1 - slippage) (4.5 bps fee + 0.2 bps slippage).
        3. Quantifies exact savings: Maker hedge preserves capital and avoids punitive taker slippage.
        """
        # --- RUN A: With Defensive Maker Hedge ---
        engine_a = self._create_backtester(min_vol_bps=4.5)
        state_a = engine_a.strategies["Queue_Replenishment"]

        ts = 1710000000000
        # Warmup with high volatility (8.0 bps)
        for i in range(20):
            mid = 25.0000 if (i % 2 == 0) else 25.0200
            engine_a.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=mid,
                best_bid=mid - 0.0010,
                best_ask=mid + 0.0010,
                signals={"QueueReplenishment": 0.0},
            )

        # Open Long Position at best_bid = 24.9990
        entry_ts = ts + 21 * 1000
        engine_a.record_step(
            timestamp_ms=entry_ts,
            mid_price=25.0000,
            best_bid=24.9990,
            best_ask=25.0010,
            signals={"QueueReplenishment": 0.99},
        )
        self.assertTrue(state_a.is_in_position)
        entry_price = state_a.entry_price
        self.assertEqual(entry_price, 24.9990)

        # Market experiences adverse flow reversal:
        # Drops to -3.6 bps: mid_price = entry_price * (1 - 0.00036) = 24.9900
        # Signal flips violently: score = -0.20 (<= -0.15 hedge_reversal_threshold)
        reversal_ts = entry_ts + 5000
        rev_mid = entry_price * (1.0 - 0.00036)
        rev_bid = rev_mid - 0.0010
        rev_ask = rev_mid + 0.0010

        engine_a.record_step(
            timestamp_ms=reversal_ts,
            mid_price=rev_mid,
            best_bid=rev_bid,
            best_ask=rev_ask,
            signals={"QueueReplenishment": -0.20},
        )

        # Verify Defensive Maker Hedge triggered
        self.assertFalse(state_a.is_in_position, "Position was not closed by maker hedge!")
        self.assertEqual(len(state_a.trades), 1)
        trade_a = state_a.trades[0]
        self.assertEqual(trade_a.exit_reason, "DEFENSIVE_MAKER_HEDGE")
        self.assertEqual(trade_a.execution_type, "MAKER")
        # Fee should be maker fee: 1.5 bps on entry and 1.5 bps on exit
        expected_entry_fee = trade_a.entry_price * trade_a.size_btc * 0.00015
        expected_exit_fee = rev_ask * trade_a.size_btc * 0.00015
        self.assertAlmostEqual(trade_a.fees_usd, expected_entry_fee + expected_exit_fee, delta=0.001)

        # --- RUN B: Counter-factual Without Signal Reversal (Drops to Stop Loss) ---
        engine_b = self._create_backtester(min_vol_bps=4.5)
        state_b = engine_b.strategies["Queue_Replenishment"]

        # Identical warmup
        for i in range(20):
            mid = 25.0000 if (i % 2 == 0) else 25.0200
            engine_b.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=mid,
                best_bid=mid - 0.0010,
                best_ask=mid + 0.0010,
                signals={"QueueReplenishment": 0.0},
            )

        # Identical entry
        engine_b.record_step(
            timestamp_ms=entry_ts,
            mid_price=25.0000,
            best_bid=24.9990,
            best_ask=25.0010,
            signals={"QueueReplenishment": 0.99},
        )

        # At -3.6 bps drop, signal does NOT reverse (stays at +0.50)
        engine_b.record_step(
            timestamp_ms=reversal_ts,
            mid_price=rev_mid,
            best_bid=rev_bid,
            best_ask=rev_ask,
            signals={"QueueReplenishment": 0.50},  # No reversal
        )
        self.assertTrue(state_b.is_in_position, "Should not exit if signal did not reverse!")

        # Price continues collapsing down to -8.1 bps: catastrophic stop loss hit!
        sl_mid = entry_price * (1.0 - 0.00081)
        sl_bid = sl_mid - 0.0010
        sl_ask = sl_mid + 0.0010
        sl_ts = entry_ts + 10000

        engine_b.record_step(
            timestamp_ms=sl_ts,
            mid_price=sl_mid,
            best_bid=sl_bid,
            best_ask=sl_ask,
            signals={"QueueReplenishment": 0.50},
        )

        self.assertFalse(state_b.is_in_position)
        self.assertEqual(len(state_b.trades), 1)
        trade_b = state_b.trades[0]
        self.assertEqual(trade_b.exit_reason, "STOP_LOSS")
        self.assertEqual(trade_b.execution_type, "TAKER")
        # Exit price is best_bid with dynamic volatility-calibrated slippage
        self.assertLess(trade_b.exit_price, sl_bid)
        self.assertAlmostEqual(trade_b.exit_price, sl_bid, delta=0.05)

        # Empirical Comparison
        net_loss_a = trade_a.net_pnl_usd
        net_loss_b = trade_b.net_pnl_usd
        self.assertGreater(net_loss_a, net_loss_b, "Defensive Maker Hedge must suffer less loss than Stop Loss!")
        capital_saved_usd = net_loss_a - net_loss_b
        return_bps_delta = trade_a.return_bps - trade_b.return_bps

        print(
            f"\n[EMPIRICAL PROOF] Defensive Maker Hedge vs Taker Stop Loss (LONG):\n"
            f"  - Maker Hedge Exit: PnL = ${net_loss_a:+.4f} USD ({trade_a.return_bps:+.2f} bps) [MAKER fee 1.5 bps]\n"
            f"  - Taker Stop Loss:  PnL = ${net_loss_b:+.4f} USD ({trade_b.return_bps:+.2f} bps) [TAKER fee 4.5 bps + 0.2 bps slippage]\n"
            f"  - Capital Preserved: ${capital_saved_usd:+.4f} USD (+{return_bps_delta:.2f} bps alpha delta)"
        )
        self.assertGreater(return_bps_delta, 5.0, "Maker Hedge should save at least 5 bps over catastrophic stop loss!")

    def test_defensive_maker_hedge_short_vs_taker_stop_loss(self):
        """Stress: Short position facing severe adverse flow reversal.
        Verifies:
        1. When loss reaches -3.5 bps and signal reverses to >= +0.15 (-hedge_reversal_threshold),
           DEFENSIVE_MAKER_HEDGE triggers as MAKER at best_bid (1.5 bps fee).
        2. Paired Counter-factual: without hedge trigger, price surges to -8.0 bps
           where catastrophic STOP_LOSS triggers as TAKER at best_ask * (1 + slippage).
        """
        engine_a = self._create_backtester(min_vol_bps=4.5)
        state_a = engine_a.strategies["Queue_Replenishment"]

        ts = 1710000000000
        # Warmup with high volatility
        for i in range(20):
            mid = 25.0000 if (i % 2 == 0) else 25.0200
            engine_a.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=mid,
                best_bid=mid - 0.0010,
                best_ask=mid + 0.0010,
                signals={"QueueReplenishment": 0.0},
            )

        # Open Short Position at best_ask = 25.0010
        entry_ts = ts + 21 * 1000
        engine_a.record_step(
            timestamp_ms=entry_ts,
            mid_price=25.0000,
            best_bid=24.9990,
            best_ask=25.0010,
            signals={"QueueReplenishment": -0.99},
        )
        self.assertTrue(state_a.is_in_position)
        self.assertLess(state_a.position_btc, 0.0)
        entry_price = state_a.entry_price
        self.assertEqual(entry_price, 25.0010)

        # Market surges against short:
        # Price increases by 3.6 bps: mid_price = entry_price * (1 + 0.00036) = 25.0100
        # Signal flips violently: score = +0.20 (>= +0.15)
        reversal_ts = entry_ts + 5000
        rev_mid = entry_price * (1.0 + 0.00036)
        rev_bid = rev_mid - 0.0010
        rev_ask = rev_mid + 0.0010

        engine_a.record_step(
            timestamp_ms=reversal_ts,
            mid_price=rev_mid,
            best_bid=rev_bid,
            best_ask=rev_ask,
            signals={"QueueReplenishment": 0.20},
        )

        self.assertFalse(state_a.is_in_position)
        self.assertEqual(len(state_a.trades), 1)
        trade_a = state_a.trades[0]
        self.assertEqual(trade_a.exit_reason, "DEFENSIVE_MAKER_HEDGE")
        self.assertEqual(trade_a.execution_type, "MAKER")
        self.assertEqual(trade_a.exit_price, rev_bid, "Short maker exit must fill at inside bid quote!")
        self.assertEqual(trade_a.side, "SHORT")

        # --- Paired Counter-factual for Short ---
        engine_b = self._create_backtester(min_vol_bps=4.5)
        state_b = engine_b.strategies["Queue_Replenishment"]

        for i in range(20):
            mid = 25.0000 if (i % 2 == 0) else 25.0200
            engine_b.record_step(
                timestamp_ms=ts + i * 1000,
                mid_price=mid,
                best_bid=mid - 0.0010,
                best_ask=mid + 0.0010,
                signals={"QueueReplenishment": 0.0},
            )

        engine_b.record_step(
            timestamp_ms=entry_ts,
            mid_price=25.0000,
            best_bid=24.9990,
            best_ask=25.0010,
            signals={"QueueReplenishment": -0.99},
        )

        # At -3.6 bps drop, signal remains bear (-0.50)
        engine_b.record_step(
            timestamp_ms=reversal_ts,
            mid_price=rev_mid,
            best_bid=rev_bid,
            best_ask=rev_ask,
            signals={"QueueReplenishment": -0.50},
        )
        self.assertTrue(state_b.is_in_position)

        # Price continues surging to +8.1 bps against short: hits Stop Loss
        sl_mid = entry_price * (1.0 + 0.00081)
        sl_bid = sl_mid - 0.0010
        sl_ask = sl_mid + 0.0010
        sl_ts = entry_ts + 10000

        engine_b.record_step(
            timestamp_ms=sl_ts,
            mid_price=sl_mid,
            best_bid=sl_bid,
            best_ask=sl_ask,
            signals={"QueueReplenishment": -0.50},
        )

        self.assertFalse(state_b.is_in_position)
        trade_b = state_b.trades[0]
        self.assertEqual(trade_b.exit_reason, "STOP_LOSS")
        self.assertEqual(trade_b.execution_type, "TAKER")
        self.assertGreater(trade_a.net_pnl_usd, trade_b.net_pnl_usd)

        return_bps_delta = trade_a.return_bps - trade_b.return_bps
        print(
            f"\n[EMPIRICAL PROOF] Defensive Maker Hedge vs Taker Stop Loss (SHORT):\n"
            f"  - Maker Hedge Exit: PnL = ${trade_a.net_pnl_usd:+.4f} USD ({trade_a.return_bps:+.2f} bps) [MAKER fee 1.5 bps]\n"
            f"  - Taker Stop Loss:  PnL = ${trade_b.net_pnl_usd:+.4f} USD ({trade_b.return_bps:+.2f} bps) [TAKER fee 4.5 bps + 0.2 bps slippage]\n"
            f"  - Capital Preserved: ${trade_a.net_pnl_usd - trade_b.net_pnl_usd:+.4f} USD (+{return_bps_delta:.2f} bps alpha delta)"
        )
        self.assertGreater(return_bps_delta, 5.0, "Short Maker Hedge should save at least 5 bps over stop loss!")

    # =========================================================================
    # PART 3: SKEW AND ORDER BOOK DEPTH COLLAPSE NUMERICAL ROBUSTNESS
    # =========================================================================

    def test_skew_and_depth_collapse_10k_iterations(self):
        """Stress: 10,000 iterations of extreme book skew, zero depth, rapid sweeps, and fuzzing.
        Verifies:
        - Zero NaNs, Infs, or ZeroDivisionErrors in Rb1, Ra1, Rb3, Ra3, S_canc, score, confidence.
        - Strict adherence to score in [-1.0, 1.0], confidence in [0.0, 1.0].
        """
        signal = QueueReplenishmentSignal()
        base_ts = 1710000000000

        scenarios = [
            "ZERO_DEPTH",
            "INFINITESIMAL_DEPTH",
            "MEGA_SKEW_BID",
            "MEGA_SKEW_ASK",
            "RAPID_SWEEPS",
            "CANCELLATION_CASCADE",
            "EMPTY_OR_DEGENERATE",
            "EXTREME_SPREAD",
            "MICRO_MID_PRICE",
            "MACRO_MID_PRICE",
        ]

        nan_or_inf_count = 0
        bound_violation_count = 0
        exception_count = 0

        for i in range(10000):
            scenario = random.choice(scenarios)
            ts = base_ts + i * 100
            custom_scale = random.choice([0.0, -1.0, 1e-12, 1e12]) if (random.random() < 0.10) else None

            try:
                # 1. Setup OrderBook based on scenario
                if scenario == "EMPTY_OR_DEGENERATE":
                    book = OrderBook(coin="HYPE")
                    if random.random() < 0.33:
                        book.bids = []
                        book.asks = []
                    elif random.random() < 0.66:
                        book.bids = [L2Level(px=25.0, sz=10.0, n=1)]
                        book.asks = [L2Level(px=25.1, sz=10.0, n=1)]
                    else:
                        # Crossed book
                        book.bids = [L2Level(px=26.0 - 0.1 * k, sz=10.0, n=1) for k in range(3)]
                        book.asks = [L2Level(px=24.0 + 0.1 * k, sz=10.0, n=1) for k in range(3)]
                    book.last_update_time_ms = ts

                elif scenario == "ZERO_DEPTH":
                    book = self._create_mock_book(bid_sz=0.0, ask_sz=0.0, ts_ms=ts, custom_scale=custom_scale)

                elif scenario == "INFINITESIMAL_DEPTH":
                    book = self._create_mock_book(bid_sz=1e-15, ask_sz=1e-15, ts_ms=ts, custom_scale=custom_scale)

                elif scenario == "MEGA_SKEW_BID":
                    book = self._create_mock_book(bid_sz=1e8, ask_sz=1e-8, ts_ms=ts, custom_scale=custom_scale)

                elif scenario == "MEGA_SKEW_ASK":
                    book = self._create_mock_book(bid_sz=1e-8, ask_sz=1e8, ts_ms=ts, custom_scale=custom_scale)

                elif scenario == "EXTREME_SPREAD":
                    # Spread blowout up to 5000 USD
                    book = self._create_mock_book(spread=random.uniform(10.0, 5000.0), ts_ms=ts, custom_scale=custom_scale)

                elif scenario == "MICRO_MID_PRICE":
                    # Sub-penny asset: mid = 0.00005
                    book = self._create_mock_book(mid_px=0.00005, spread=0.000001, ts_ms=ts, custom_scale=custom_scale)

                elif scenario == "MACRO_MID_PRICE":
                    # Mega price: mid = 1,000,000 USD
                    book = self._create_mock_book(mid_px=1_000_000.0, spread=100.0, ts_ms=ts, custom_scale=custom_scale)

                else:
                    # Normal book with random variations
                    book = self._create_mock_book(
                        bid_sz=random.uniform(1.0, 500.0),
                        ask_sz=random.uniform(1.0, 500.0),
                        ts_ms=ts,
                        custom_scale=custom_scale,
                    )

                # 2. Setup Trades based on scenario
                trades_list = []
                if scenario == "RAPID_SWEEPS":
                    # 50 high-volume aggressive sweeps
                    side = "A" if (i % 2 == 0) else "B"
                    for t_idx in range(50):
                        trades_list.append((side, 25.0, random.uniform(50.0, 5000.0), t_idx))

                elif scenario == "CANCELLATION_CASCADE":
                    # Large trades counteracting quote changes
                    trades_list.append(("A", 25.0, 1000.0, 0))
                    trades_list.append(("B", 25.0, 1000.0, 1))

                elif random.random() < 0.5:
                    trades_list.append((
                        random.choice(["A", "B"]),
                        25.0,
                        random.uniform(0.1, 50.0),
                        0,
                    ))

                tm = self._create_mock_trades(trades_list=trades_list, base_ts_ms=ts)

                # 3. Compute signal
                res = signal.compute(book=book, trades=tm, timestamp_ms=ts)

                # 4. Rigorous assertions on output
                if math.isnan(res.score) or math.isinf(res.score):
                    nan_or_inf_count += 1
                if math.isnan(res.confidence) or math.isinf(res.confidence):
                    nan_or_inf_count += 1
                if math.isnan(res.raw_value) or math.isinf(res.raw_value):
                    nan_or_inf_count += 1

                if not (-1.0 <= res.score <= 1.0):
                    bound_violation_count += 1
                if not (0.0 <= res.confidence <= 1.0):
                    bound_violation_count += 1

                # Verify metadata numerical integrity
                meta = res.metadata
                for k in ["l1_rep_bid", "l1_rep_ask", "l3_rep_bid", "l3_rep_ask", "s_canc"]:
                    val = meta.get(k, 0.0)
                    if math.isnan(val) or math.isinf(val):
                        nan_or_inf_count += 1

                # S_canc must be bounded in [-1.0, 1.0]
                s_canc = meta.get("s_canc", 0.0)
                if not (-1.0 <= s_canc <= 1.0):
                    bound_violation_count += 1

                # Latencies must be in [0, 50]
                tau_b = meta.get("latency_bid", 0)
                tau_a = meta.get("latency_ask", 0)
                if not (0 <= tau_b <= 50 and 0 <= tau_a <= 50):
                    bound_violation_count += 1

            except Exception as e:
                exception_count += 1
                print(f"[ERROR] Exception in iteration {i} (scenario {scenario}): {e}")

        print(
            f"\n[EMPIRICAL STRESS RESULTS: 10,000 ITERATIONS]\n"
            f"  - Total Iterations: 10,000\n"
            f"  - Exceptions: {exception_count}\n"
            f"  - NaN / Inf Violations: {nan_or_inf_count}\n"
            f"  - Bound Violations: {bound_violation_count}\n"
            f"  - Status: {'PASSED' if (exception_count == 0 and nan_or_inf_count == 0 and bound_violation_count == 0) else 'FAILED'}"
        )

        self.assertEqual(exception_count, 0, f"Encountered {exception_count} unhandled exceptions!")
        self.assertEqual(nan_or_inf_count, 0, f"Encountered {nan_or_inf_count} NaN or Inf violations!")
        self.assertEqual(bound_violation_count, 0, f"Encountered {bound_violation_count} score/confidence bound violations!")


if __name__ == "__main__":
    unittest.main()
